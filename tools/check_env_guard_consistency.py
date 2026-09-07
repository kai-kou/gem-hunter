#!/usr/bin/env python3
"""tools/check_env_guard_consistency.py — .env ガードの定義一貫性検査（Issue #493）

`.env` 系ファイルの「何を塞ぎ、何を通すか」の定義は次の 2 箇所に存在する:

  1. `.claude/settings.json` の `permissions.deny`（ファイルツールの第1層・具体名の列挙）
  2. `.claude/hooks/lib/env_allowlist.sh` の `hook_env_guard_verdict`
     （Bash / ファイルツール共通の第2層・SSOT。pre-tool-use-router.sh と
     pre-file-tool-env-guard.sh の両方がこれを source する）

本ツールは 1 と 2 が矛盾していないか（deny に載っている `.env` 系の名前が実際に
第2層でもブロックされるか／ひな形として明示的に許可している名前が deny にも
紛れ込んでいないか）を、`hook_env_guard_verdict` を実際に bash 経由で呼び出して検査する。
あわせて、deny 側に `.env` を含みながら抽出パターンの範囲外にある未対応形式のエントリ
（verb 違い・`**/` prefix 付き等）と、共有ライブラリのひな形一覧が独立の承認済みリスト
（`APPROVED_TEMPLATE_NAMES`）の外に出ていないかも検査する（#493 レビュー指摘 2 / 4）。

**第3の軸（Issue #1090 レビュー指摘）**: `.claude/settings.json` の `hooks.PreToolUse` が
`pre-file-tool-env-guard.sh` を実行する matcher に、同フックが判定対象にするツール
（`.tool_input.file_path` / `.notebook_path` / `.path` を持つ Read / Write / Edit /
NotebookEdit / Grep / Glob）を **すべて配線しているか** を検査する。PR #1090 で matcher へ
`|Grep|Glob` を足したが、この配線が将来削られても上記 1・2 の検査（bash 呼び出しベース）は
settings.json を一切読まないため気づけないことが変異テストで実測された。本軸はその穴を塞ぐ。

終了コード:
  0 = 合格（矛盾なし・matcher の配線も欠けなし）
  1 = 違反あり（deny の名前が第2層でブロックされない／ひな形が deny にも列挙されている／
      deny に未対応形式の `.env` エントリがある／ひな形一覧が承認済みリストの外にある／
      matcher が空 or 必要ツールが欠けている／該当エントリが存在しない 等）
  2 = 判定不能（settings.json / env_allowlist.sh が読めない・パース失敗・bash 呼び出し失敗・
      hooks.PreToolUse の構造が想定外・.env 系の deny エントリが 1 件も無い〔対象 0 件〕。
      いずれも fail-closed で非ゼロにする）
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SETTINGS_PATH = REPO_ROOT / ".claude" / "settings.json"
LIB_PATH = REPO_ROOT / ".claude" / "hooks" / "lib" / "env_allowlist.sh"

# 承認済みひな形名の独立ソース（#493 レビュー指摘 4）。
# `env_allowlist.sh` の `hook_env_guard_template_names()` が返す名前は、本リストに
# 含まれるものだけを正当とみなす。ライブラリが読めないときの退避値も兼ねるが、
# 役割の主はこちら（「検査対象自身から ground truth を取る」自己言及を避けるため、
# 新しいひな形を追加するときはこの定数を同じ PR で更新することを要求する）。
APPROVED_TEMPLATE_NAMES = [".env.example", ".env.sample", ".env.template", ".env.dist"]

# `Read` / `Write` / `Edit` のいずれかで、任意の `**/` prefix を伴う `.env...` を拾う。
# 範囲外の deny エントリ（未対応の verb・prefix 形式）は黙って除外せず、
# ENV_MENTION_PATTERN で別途検出して違反として報告する（#493 レビュー指摘 2）。
DENY_ENV_PATTERN = re.compile(r"^(?:Read|Write|Edit)\((?:\*\*/)?(\.env[^)]*)\)$")
ENV_MENTION_PATTERN = re.compile(r"\.env")

# --- 第3の軸: PreToolUse matcher の配線検査（Issue #1090） -----------------------------
#
# `pre-file-tool-env-guard.sh` は stdin JSON の `.tool_input.file_path` /
# `.notebook_path` / `.path` を判定対象にする（同スクリプト本体のコメント参照）。
# これらのフィールドを持つツールは以下の 6 つで、matcher に **リテラルに列挙**
# されていなければ、そのツール経由の呼び出しではフック自体が起動しない
# （settings.json の matcher は正規表現の一部と解釈されるが、本検査は「今後
# このハードコードした必要集合から外れたら FAIL にする」というリテラル一致の
# 監査であり、`.*` のような包括的パターンで代替されているケースまでは救わない
# — それ自体を検出できるようにするのが本軸の目的であり、意図的な設計判断）。
REQUIRED_ENV_GUARD_MATCHER_TOOLS = ["Read", "Write", "Edit", "NotebookEdit", "Grep", "Glob"]
ENV_GUARD_HOOK_SCRIPT = "pre-file-tool-env-guard.sh"


# `hook_env_guard_verdict` の期待値表（Issue #1031）。
# self-test の入力バリアント検証と、変異テストの「壊すと落ちる」判定の両方から使う。
# True = ブロック対象 / False = 対象外。
VERDICT_EXPECTATIONS: list[tuple[str, bool]] = [
    # 本物の .env（大文字小文字のバリアント込み・#1031-2）
    (".env", True),
    (".env.local", True),
    (".env.stg", True),
    (".env.qa", True),
    ("path/to/.env", True),
    ("./.env", True),
    (".ENV", True),
    (".Env.Local", True),
    (".eNv.PRODUCTION", True),
    ("path/to/.ENV", True),
    # ひな形を騙る名前（旧 `.env.example.*` ワイルドカードの穴・#1031-1）
    (".env.example.secret", True),
    (".env.example.prod-actual", True),
    (".ENV.EXAMPLE.SECRET", True),
    (".env.example.j", True),
    (".env.example.jpn", True),
    (".env.example.ja.local", True),
    # ロケール変種の例外は削除済み（レビュー指摘 1）。`.env.example.[a-z][a-z]` は
    # 「2 文字の言語コード」のつもりで任意の小文字 2 文字 676 通りを通す fail-open だった。
    (".env.example.ja", True),
    (".env.example.en", True),
    (".env.example.ci", True),
    (".env.example.qa", True),
    (".env.example.pr", True),
    # 大文字表記でひな形を騙る名前（ひな形は元表記の完全一致のみ・レビュー指摘 2 の設計）
    (".ENV.EXAMPLE", True),
    (".Env.Example", True),
    (".Env.Example.Ja", True),
    # ひな形（固定 4 種の完全一致のみ）
    (".env.example", False),
    (".env.sample", False),
    (".env.template", False),
    (".env.dist", False),
    # 境界の外側（`.env` で始まるが本物の env ファイルではない名前・#750）
    (".environment", False),
    (".env-notes.md", False),
    ("environment.ts", False),
]


def default_bash_runner(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=10)


def hook_verdict(path: str, lib_path: Path, runner=default_bash_runner) -> bool | None:
    """共有ライブラリの hook_env_guard_verdict を実際に bash で呼び出す。

    戻り値: True = ブロック対象 / False = 対象外 / None = 呼び出し失敗（判定不能）
    """
    if not lib_path.is_file():
        return None
    # パスはシェル文字列へ直接補間せず `shlex.quote` で引用する（レビュー指摘 4）。
    # `TMPDIR` 等に `"` / `$(` を含むパスが来ると `bash -c` の文字列内で展開され、
    # コマンド注入になる（判定対象パス自体は `$1` 渡しなので元から安全）。
    script = f'source {shlex.quote(str(lib_path))}; hook_env_guard_verdict "$1"'
    try:
        proc = runner(["bash", "-c", script, "bash", path])
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode not in (0, 1):
        # hook_env_guard_verdict は 0/1 しか返さない契約。想定外は判定不能へ倒す
        # （check-tool-design-rules.md §3: 外部コマンドの終了コードを 0/1 へ勝手に丸めない）
        return None
    return proc.returncode == 0


def template_names(lib_path: Path, runner=default_bash_runner) -> list[str] | None:
    """lib/env_allowlist.sh の hook_env_guard_template_names() を実行して取得する。
    取得できなければ None（判定不能）。
    """
    if not lib_path.is_file():
        return None
    script = f'source {shlex.quote(str(lib_path))}; hook_env_guard_template_names'
    try:
        proc = runner(["bash", "-c", script, "bash"])
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    names = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    return names or None


def verdict_mismatches(lib_path: Path, runner=default_bash_runner) -> list[str]:
    """VERDICT_EXPECTATIONS を lib_path に対して実行し、期待と異なるものを返す。"""
    mismatches: list[str] = []
    for path, expect_block in VERDICT_EXPECTATIONS:
        got = hook_verdict(path, lib_path, runner=runner)
        if got is not expect_block:
            mismatches.append(f"'{path}': got={got} want={expect_block}")
    return mismatches


def load_deny_names(settings_path: Path) -> tuple[list[str], list[str]] | None:
    """settings.json の permissions.deny から `.env` 系エントリを抽出する。

    戻り値: (names, unrecognized) のタプル。読み込み・パース自体に失敗したら None。
      - names: `DENY_ENV_PATTERN`（Read|Write|Edit の `**/` prefix 付き `.env...`）に
        一致した具体パターン文字列のリスト（0件含む）
      - unrecognized: `.env` という文字列を含むが `DENY_ENV_PATTERN` に一致しなかった
        deny エントリの原文リスト（範囲外の verb/prefix 形式が監査対象から黙って
        除外されるのを防ぐ・#493 レビュー指摘 2）
    """
    if not settings_path.is_file():
        return None
    try:
        raw = settings_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    deny = data.get("permissions", {}).get("deny", [])
    if not isinstance(deny, list):
        return None
    names: list[str] = []
    unrecognized: list[str] = []
    for entry in deny:
        if not isinstance(entry, str):
            continue
        m = DENY_ENV_PATTERN.match(entry)
        if m:
            names.append(m.group(1))
        elif ENV_MENTION_PATTERN.search(entry):
            unrecognized.append(entry)
    return names, unrecognized


def find_env_guard_pretooluse_matchers(settings_path: Path) -> list[str] | None:
    """settings.json の `hooks.PreToolUse` から、`ENV_GUARD_HOOK_SCRIPT` を実行する
    エントリの `matcher` 文字列を全て抽出する（既存の `load_deny_names()` と同じ
    読み込み・エラー処理の作法を踏襲する）。

    戻り値:
      - list[str]: 見つかった matcher の一覧（0 件の可能性あり。空文字列の matcher も
        そのまま含める — 呼び出し側が「空 matcher」を違反として報告するため）
      - None: settings.json が読めない・パースできない、または `hooks` /
        `hooks.PreToolUse` / 各エントリの `hooks` 配列の構造が想定外（判定不能）。
        見逃し経路（miss）の列挙: ファイル不在・非 UTF-8・JSON 破損・トップレベルが
        dict でない・`hooks` が dict でない・`PreToolUse` が list でない、をすべて
        個別に判定し、想定外の型はどれも `None` へ倒す（`0`/`1` に丸めない）。
    """
    if not settings_path.is_file():
        return None
    try:
        raw = settings_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    hooks = data.get("hooks", {})
    if not isinstance(hooks, dict):
        return None
    pre_entries = hooks.get("PreToolUse", [])
    if not isinstance(pre_entries, list):
        return None

    matchers: list[str] = []
    for entry in pre_entries:
        if not isinstance(entry, dict):
            continue
        entry_hooks = entry.get("hooks", [])
        if not isinstance(entry_hooks, list):
            continue
        references_guard = False
        for h in entry_hooks:
            if not isinstance(h, dict):
                continue
            command = h.get("command", "")
            if isinstance(command, str) and ENV_GUARD_HOOK_SCRIPT in command:
                references_guard = True
                break
        if references_guard:
            matcher = entry.get("matcher", "")
            matchers.append(matcher if isinstance(matcher, str) else "")
    return matchers


def check_env_guard_matcher_wiring(settings_path: Path) -> tuple[int, list[str]]:
    """PreToolUse の matcher が `pre-file-tool-env-guard.sh` を必要ツール全てに
    配線しているかを検査する（Issue #1090 レビュー指摘: matcher からツールが
    削られても bash 呼び出しベースの検査〔`hook_verdict` 等〕は settings.json を
    一切読まないため気づけない、という穴を塞ぐ）。

    本関数は `subprocess` を使わない（settings.json の静的な構造解析のみ）。

    判定:
      - matcher 抽出そのものが判定不能（`find_env_guard_pretooluse_matchers` が
        None）→ 2
      - `ENV_GUARD_HOOK_SCRIPT` を実行するエントリが 1 件も無い → 1（違反。
        「対象 0 件」だが、これは §2 の「対象選択の壊れ」ではなく「配線そのものが
        存在しない」という確定した違反であるため、判定不能〔2〕ではなく違反〔1〕
        として明確に報告する）
      - matcher が空文字列のエントリがある → 1
      - 複数エントリに分かれていてもよい（`|` で union を取る）。union が
        `REQUIRED_ENV_GUARD_MATCHER_TOOLS` を満たさなければ → 1
      - 全て満たす → 0
    """
    matchers = find_env_guard_pretooluse_matchers(settings_path)
    if matchers is None:
        return 2, [
            f"settings.json の hooks.PreToolUse を読み取れない・パースできない（判定不能）: {settings_path}"
        ]
    if not matchers:
        return 1, [
            f"{ENV_GUARD_HOOK_SCRIPT} を実行する PreToolUse エントリが settings.json に見つからない"
        ]

    violations: list[str] = []
    covered: set[str] = set()
    for matcher in matchers:
        if not matcher.strip():
            violations.append(f"{ENV_GUARD_HOOK_SCRIPT} を実行するエントリの matcher が空文字列")
            continue
        covered.update(t.strip() for t in matcher.split("|") if t.strip())

    missing = [t for t in REQUIRED_ENV_GUARD_MATCHER_TOOLS if t not in covered]
    if missing:
        violations.append(
            f"{ENV_GUARD_HOOK_SCRIPT} の matcher に必要ツールが欠けている: {missing}"
            f"（見つかった matcher: {matchers}）"
        )

    if violations:
        return 1, violations
    return 0, []


def instantiate(pattern: str) -> str:
    """glob を含む deny パターン（例: `.env.*.local`）を検証用の具体パスへ変換する。
    ひな形の固定名（`.env.example` 等）と衝突しない値（`x`）に置換する。
    """
    return pattern.replace("*", "x") if "*" in pattern else pattern


def check_consistency(
    deny_names: list[str],
    lib_path: Path,
    runner=default_bash_runner,
) -> tuple[int, list[str]]:
    """deny_names（settings.json 由来）と lib_path（共有 allowlist）の矛盾を検査する。

    戻り値: (exit_code, violations)
    """
    violations: list[str] = []

    if not lib_path.is_file():
        return 2, [f"共有ライブラリが存在しない（判定不能）: {lib_path}"]

    tmpl_names = template_names(lib_path, runner=runner)
    if tmpl_names is None:
        tmpl_names = APPROVED_TEMPLATE_NAMES

    if not deny_names:
        return 2, ["settings.json の permissions.deny に .env 系エントリが 1 件も無い（対象 0 件・判定不能）"]

    # 0) env_allowlist.sh のひな形一覧が、独立の承認済みリスト（APPROVED_TEMPLATE_NAMES）の
    #    外側に出ていないか（#493 レビュー指摘 4: 検査対象自身から ground truth を取るのは
    #    自己言及的で、ひな形側に新しい分岐を足しても整合してしまえば検出できない）
    unapproved_tmpl = sorted(set(tmpl_names) - set(APPROVED_TEMPLATE_NAMES))
    if unapproved_tmpl:
        violations.append(
            "env_allowlist.sh のひな形一覧に、独立の承認済みリスト（APPROVED_TEMPLATE_NAMES）に無い名前がある: "
            f"{unapproved_tmpl}（新しいひな形を追加するときは "
            "tools/check_env_guard_consistency.py の APPROVED_TEMPLATE_NAMES も同じ PR で更新すること）"
        )

    # 1) deny に載っている .env 名が、共有 allowlist で実際にブロックされるか
    for pattern in deny_names:
        test_path = instantiate(pattern)
        verdict = hook_verdict(test_path, lib_path, runner=runner)
        if verdict is None:
            return 2, [f"共有ライブラリの呼び出しに失敗（判定不能）: {test_path}"]
        if verdict is False:
            violations.append(
                f"settings.json の deny に Read({pattern}) があるが、"
                f"共有 allowlist（env_allowlist.sh）は '{test_path}' をブロック対象としていない"
            )

    # 2) ひな形（allowlist が明示的に通す名前）が deny に紛れ込んでいないか、
    #    かつ共有 allowlist 側でも実際に通過するか
    for name in tmpl_names:
        if name in deny_names:
            violations.append(
                f"ひな形 '{name}' が settings.json の permissions.deny にも列挙されている（定義が矛盾）"
            )
        verdict = hook_verdict(name, lib_path, runner=runner)
        if verdict is None:
            return 2, [f"共有ライブラリの呼び出しに失敗（判定不能）: {name}"]
        if verdict is True:
            violations.append(
                f"ひな形 '{name}' が共有 allowlist（env_allowlist.sh）でブロック対象になっている"
            )

    # 3) 要素間の関係が不正な負ケース（#896 相当）: 各名前は単体では妥当だが、
    #    deny とひな形 allowlist の両方に同じ名前が存在するのは定義として矛盾している
    overlap = sorted(set(deny_names) & set(tmpl_names))
    if overlap:
        violations.append(f"deny とひな形 allowlist の両方に同じ名前が存在する: {overlap}")

    if violations:
        return 1, violations
    return 0, []


def run_checks(
    settings_path: Path = SETTINGS_PATH,
    lib_path: Path = LIB_PATH,
    runner=default_bash_runner,
) -> tuple[int, list[str]]:
    extraction = load_deny_names(settings_path)
    if extraction is None:
        return 2, [f"settings.json を読み取れない・パースできない（判定不能）: {settings_path}"]
    deny_names, unrecognized = extraction
    code, violations = check_consistency(deny_names, lib_path, runner=runner)

    # deny に `.env` を含みながら抽出パターンの範囲外にあるエントリは黙って除外せず
    # 違反として報告する（#493 レビュー指摘 2: 将来 Write/Edit や別 prefix の .env 系
    # エントリが追加されても監査対象から静かに漏れないようにする）
    if unrecognized:
        violations = violations + [
            f"deny エントリ '{e}' は `.env` を含むが認識パターン"
            "（Read|Write|Edit の (**/ ).env... 形式）に一致しない"
            "（監査対象から漏れている可能性があるため確認が必要）"
            for e in unrecognized
        ]
        if code == 0:
            code = 1

    # 第3の軸: PreToolUse matcher の配線検査（#1090）。上記の deny × allowlist 検査とは
    # 独立の判定なので、結果はマージ（違反は連結・終了コードは深刻度が高い方を採用）する。
    # 2（判定不能） > 1（違反） > 0（合格）の順で深刻度が高いため max() で正しく合成できる。
    wiring_code, wiring_violations = check_env_guard_matcher_wiring(settings_path)
    violations = violations + wiring_violations
    code = max(code, wiring_code)

    return code, violations


def self_test() -> int:
    failures: list[str] = []
    calls: list[list[str]] = []

    def recording_runner(args: list[str]) -> subprocess.CompletedProcess:
        calls.append(list(args))
        return subprocess.run(args, capture_output=True, text=True, timeout=10)

    # 指摘1（CRITICAL）の防御ネット: この関数が本番の共有フック実体を一切
    # 書き換えないことを、事前に取得したスナップショットと事後比較で機械保証する。
    lib_snapshot = LIB_PATH.read_text(encoding="utf-8") if LIB_PATH.is_file() else None

    # --- 0) 前提: 実データを読み込めること ---
    real_extraction = load_deny_names(SETTINGS_PATH)
    if real_extraction is None:
        failures.append("実際の settings.json から deny を読み込めなかった（自己診断不能）")
        real_deny, real_unrecognized = [], []
    else:
        real_deny, real_unrecognized = real_extraction
    if real_unrecognized:
        failures.append(
            f"実際の settings.json に未対応形式の .env deny エントリがある（想定外・要確認）: {real_unrecognized}"
        )
    real_tmpl = template_names(LIB_PATH, runner=recording_runner) or APPROVED_TEMPLATE_NAMES

    # --- 1) 正常系: 実際の settings.json / env_allowlist.sh は矛盾していないはず ---
    if real_deny:
        code, violations = check_consistency(real_deny, LIB_PATH, runner=recording_runner)
        if code != 0:
            failures.append(f"実データが矛盾なしのはずが code={code} violations={violations}")

    # --- 2) 失敗経路: settings.json が読めない／パース不能／deny が list でない ---
    with tempfile.TemporaryDirectory() as td:
        missing = Path(td) / "does-not-exist.json"
        code, violations = run_checks(settings_path=missing, lib_path=LIB_PATH, runner=recording_runner)
        if code != 2:
            failures.append(f"settings.json 不在で判定不能(2)にならなかった: code={code}")

        broken = Path(td) / "broken.json"
        broken.write_text("{not valid json", encoding="utf-8")
        code, violations = run_checks(settings_path=broken, lib_path=LIB_PATH, runner=recording_runner)
        if code != 2:
            failures.append(f"JSON パース失敗で判定不能(2)にならなかった: code={code}")

        non_list = Path(td) / "non_list.json"
        non_list.write_text(json.dumps({"permissions": {"deny": "not-a-list"}}), encoding="utf-8")
        code, violations = run_checks(settings_path=non_list, lib_path=LIB_PATH, runner=recording_runner)
        if code != 2:
            failures.append(f"deny が list でない場合に判定不能(2)にならなかった: code={code}")

        # 対象 0 件（.env 系 deny エントリが無い）→ fail-closed
        zero = Path(td) / "zero.json"
        zero.write_text(json.dumps({"permissions": {"deny": ["Read(**/*.pem)"]}}), encoding="utf-8")
        code, violations = run_checks(settings_path=zero, lib_path=LIB_PATH, runner=recording_runner)
        if code != 2:
            failures.append(f".env 系 deny エントリ 0 件で判定不能(2)にならなかった: code={code}")

        # 共有ライブラリ不在 → 判定不能
        missing_lib = Path(td) / "missing_lib.sh"
        code, violations = run_checks(settings_path=SETTINGS_PATH, lib_path=missing_lib, runner=recording_runner)
        if code != 2:
            failures.append(f"共有ライブラリ不在で判定不能(2)にならなかった: code={code}")

    # --- 3) 負例: ひな形が deny にも紛れ込んでいるケース（要素間の関係が不正・#896 相当）---
    code, violations = check_consistency(real_deny + [".env.example"], LIB_PATH, runner=recording_runner)
    if code != 1:
        failures.append("ひな形が deny に混入しても違反として検出されなかった")
    elif not any("矛盾" in v or "紛れ込んで" in v for v in violations):
        failures.append(f"検出はしたが理由の文言が想定と異なる: {violations}")

    # --- 4) 負例: deny 名が第2層でブロックされないケース（ひな形名だけを deny として渡す）---
    code, violations = check_consistency([".env.sample"], LIB_PATH, runner=recording_runner)
    if code != 1:
        failures.append("deny 名がブロックされないケースを検出できなかった")

    # --- 4b) 負例（純粋分岐1）: 非ひな形の deny 名が第2層でブロックされないケース。
    #     上の 4) は `.env.sample` がひな形一覧にも含まれるため、overlap 検出（3の分岐）
    #     でも code=1 になり得て、「deny が未ブロック」を検出する分岐1を独立に検証できない
    #     （overlap 検出を無効化しても 4) は緑のまま通ってしまう・fail-closed の抜け穴）。
    #     ここでは実際の deny エントリのうち `.env.production`（ひな形ではない）を選び、
    #     共有ライブラリをそれだけ「ブロックしない」よう変異させた一時コピーで検証する。
    if LIB_PATH.is_file() and ".env.production" in real_deny:
        original4b = LIB_PATH.read_text(encoding="utf-8")
        target4b = "    .env|.env.*) return 0 ;;"
        if target4b not in original4b:
            failures.append("変異テスト4bの事前条件不成立: 置換対象の文字列が源文に見つからない")
        else:
            mutated4b = original4b.replace(
                target4b,
                "    .env.production) return 1 ;;\n    .env|.env.*) return 0 ;;",
            )
            if mutated4b == original4b:
                failures.append("変異テスト4bの事後条件不成立: 置換しても内容が変わらなかった")
            else:
                with tempfile.TemporaryDirectory() as td4b:
                    mutated_lib4b = Path(td4b) / "env_allowlist.sh"
                    mutated_lib4b.write_text(mutated4b, encoding="utf-8")
                    v4b = hook_verdict(".env.production", mutated_lib4b, runner=recording_runner)
                    code4b, violations4b = check_consistency(
                        real_deny, mutated_lib4b, runner=recording_runner
                    )
                    if v4b is not False:
                        failures.append(
                            f"変異テスト4bの前提不成立: '.env.production' が変異版でも "
                            f"ブロック対象のままだった（verdict={v4b}）"
                        )
                    elif code4b != 1 or not any(
                        ".env.production" in v and "ブロック対象としていない" in v for v in violations4b
                    ):
                        failures.append(
                            "非ひな形の deny 名が第2層でブロックされない状態を分岐1が検出しなかった"
                            f"（overlap 検出だけに依存していないかの回帰）: code={code4b} violations={violations4b}"
                        )
    else:
        failures.append("変異テスト4bの前提不成立: LIB_PATH 不在、または実データに .env.production が無い")

    # --- 5) 入力バリアントの展開（期待値表 VERDICT_EXPECTATIONS が SSOT・#1031） ---
    for mismatch in verdict_mismatches(LIB_PATH, runner=recording_runner):
        failures.append(f"入力バリアントの判定が期待と異なる: {mismatch}")
    # glob を含む deny パターン由来の具体化パスも 1 件は通す（instantiate() の経路確認）
    v_glob = hook_verdict(instantiate(".env.*.local"), LIB_PATH, runner=recording_runner)
    if v_glob is not True:
        failures.append(f"deny の glob パターン '.env.*.local' の具体化が block にならない: got={v_glob}")

    # --- 6) 正当なドキュメント編集を誤ってブロックしないこと（#495 系の負ケース） ---
    for doc_path in ["docs/rules/env-vars.md", "README.md", "src/infrastructure/github/oauth.ts"]:
        v = hook_verdict(doc_path, LIB_PATH, runner=recording_runner)
        if v is not False:
            failures.append(f"ドキュメント/非 .env パスが誤ってブロック対象と判定された: {doc_path}")

    # --- 7) 変異テスト: env_allowlist.sh の本番コードパスを実際に壊して FAIL することを確認 ---
    #     （check-tool-design-rules.md §4: 終了コードを返す経路を必ず 1 つ変異対象に含める）
    #     🔴 指摘1（CRITICAL）対応: 本物の LIB_PATH には一切書き込まない。一時ディレクトリへ
    #     変異版をコピーし、それを lib_path として各関数へ渡す（並行セッション・Ctrl-C/OOM・
    #     Stop フックの WIP 自動コミットが本番の .env ガードを壊れた状態のまま拾う事故を防ぐ）。
    if LIB_PATH.is_file():
        original = LIB_PATH.read_text(encoding="utf-8")
        target = "    .env.example|.env.sample|.env.template|.env.dist) return 1 ;;"
        # 事前条件: 置換対象の文字列が源文に存在するか
        if target not in original:
            failures.append("変異テスト7の事前条件不成立: 置換対象の文字列が源文に見つからない")
        else:
            mutated = original.replace(
                target,
                "    .env.example|.env.sample|.env.template|.env.dist) return 0 ;;",
            )
            # 事後条件: 置換で内容が変わったか
            if mutated == original:
                failures.append("変異テスト7の事後条件不成立: 置換しても内容が変わらなかった")
            else:
                with tempfile.TemporaryDirectory() as td7:
                    mutated_lib = Path(td7) / "env_allowlist.sh"
                    mutated_lib.write_text(mutated, encoding="utf-8")
                    v = hook_verdict(".env.example", mutated_lib, runner=recording_runner)
                    # 変異後は「ひな形なのにブロックされる」ため、check_consistency が違反検出するはず
                    mcode, mviol = check_consistency(real_deny or [".env"], mutated_lib, runner=recording_runner)
                    if v is not True or mcode != 1:
                        failures.append(
                            f"変異テスト7（ひな形の分岐を反転）が self-test を FAIL させなかった: "
                            f"verdict={v} check_consistency_code={mcode} violations={mviol}"
                        )
    else:
        failures.append("変異テスト7の対象 env_allowlist.sh が見つからない")

    # --- 8) 指摘2: 拡張した DENY_ENV_PATTERN と未対応形式の検出 ---
    with tempfile.TemporaryDirectory() as td8:
        mismatched_settings = Path(td8) / "mismatched.json"
        mismatched_settings.write_text(
            json.dumps(
                {
                    "permissions": {
                        "deny": [
                            "Read(**/.env.production)",  # `**/` prefix 付き → 拾えるはず
                            "Write(.env.local)",  # verb 違い（Write）→ 拾えるはず
                            "Bash(cat .env)",  # `.env` を含むが認識パターン外 → unrecognized
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
        extraction8 = load_deny_names(mismatched_settings)
        if extraction8 is None:
            failures.append("拡張パターンのテストで settings.json をパースできなかった")
        else:
            names8, unrecognized8 = extraction8
            if ".env.production" not in names8 or ".env.local" not in names8:
                failures.append(
                    f"拡張した DENY_ENV_PATTERN が Read(**/…) / Write(...) 形式を拾えていない: names={names8}"
                )
            if not any("cat .env" in u for u in unrecognized8):
                failures.append(f".env を含む未対応形式の deny エントリが検出されなかった: {unrecognized8}")

        code8, violations8 = run_checks(
            settings_path=mismatched_settings, lib_path=LIB_PATH, runner=recording_runner
        )
        if code8 == 0:
            failures.append("未対応形式の deny エントリがあるのに run_checks() が合格(0)を返した")
        elif not any("認識パターン" in v for v in violations8):
            failures.append(f"未対応形式の deny エントリが violations に反映されていない: {violations8}")

    # --- 9) 指摘4: ひな形一覧が独立の承認済みリスト（APPROVED_TEMPLATE_NAMES）の外に
    #        出たときに検出できるか（検査対象自身から ground truth を取る自己言及の解消） ---
    if LIB_PATH.is_file():
        original9 = LIB_PATH.read_text(encoding="utf-8")
        verdict_target9 = "    .env.example|.env.sample|.env.template|.env.dist) return 1 ;;"
        tmpl_target9 = ".env.example\n.env.sample\n.env.template\n.env.dist\nEOF"
        if verdict_target9 not in original9 or tmpl_target9 not in original9:
            failures.append("変異テスト9の事前条件不成立: 置換対象の文字列が源文に見つからない")
        else:
            mutated9 = original9.replace(
                verdict_target9,
                "    .env.example|.env.sample|.env.template|.env.dist|.env.internal) return 1 ;;",
            ).replace(
                tmpl_target9,
                ".env.example\n.env.sample\n.env.template\n.env.dist\n.env.internal\nEOF",
            )
            if mutated9 == original9:
                failures.append("変異テスト9の事後条件不成立: 置換しても内容が変わらなかった")
            else:
                with tempfile.TemporaryDirectory() as td9:
                    mutated_lib9 = Path(td9) / "env_allowlist.sh"
                    mutated_lib9.write_text(mutated9, encoding="utf-8")
                    tnames9 = template_names(mutated_lib9, runner=recording_runner)
                    if tnames9 is None or ".env.internal" not in tnames9:
                        failures.append(
                            f"変異テスト9の前提不成立: 変異版から .env.internal が取得できなかった: {tnames9}"
                        )
                    else:
                        mcode9, mviol9 = check_consistency(
                            real_deny or [".env"], mutated_lib9, runner=recording_runner
                        )
                        if mcode9 != 1 or not any(
                            ".env.internal" in v and "承認済み" in v for v in mviol9
                        ):
                            failures.append(
                                f"未承認のひな形 '.env.internal' が独立リストとの突合で検出されなかった: "
                                f"code={mcode9} violations={mviol9}"
                            )
    else:
        failures.append("変異テスト9の対象 env_allowlist.sh が見つからない")

    # --- 10) fake runner の argv 検証（#710） ---
    if not calls:
        failures.append("fake runner が一度も呼び出されなかった")
    else:
        for c in calls:
            if not (len(c) >= 3 and c[0] == "bash" and c[1] == "-c"):
                failures.append(f"想定外のサブコマンド呼び出し: {c}")
            elif "hook_env_guard_verdict" not in c[2] and "hook_env_guard_template_names" not in c[2]:
                failures.append(f"判定関数を呼んでいない呼び出し: {c}")

    # --- 11) main() からの実到達（正常系: エントリポイント経由の exit code） ---
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve())],
        capture_output=True, text=True, timeout=30,
    )
    if proc.returncode not in (0, 1, 2):
        failures.append(f"素の CLI 実行の exit code が標準の3値に収まらない: {proc.returncode}")
    if proc.returncode != 0:
        failures.append(
            f"本番の settings.json / env_allowlist.sh を素の CLI 実行した結果が PASS(0) でない: "
            f"code={proc.returncode} stdout={proc.stdout!r} stderr={proc.stderr!r}"
        )

    # --- 12) 指摘3: main() の終了コード写像 — 判定不能(2)経路を CLI 全体で貫通確認 ---
    #      （check-tool-design-rules.md §4: main() から sys.exit() までを変異対象に含める）
    with tempfile.TemporaryDirectory() as td12:
        missing_lib_cli = Path(td12) / "does-not-exist-lib.sh"
        proc12 = subprocess.run(
            [
                sys.executable, str(Path(__file__).resolve()),
                "--settings-path", str(SETTINGS_PATH),
                "--lib-path", str(missing_lib_cli),
            ],
            capture_output=True, text=True, timeout=30,
        )
        if proc12.returncode != 2:
            failures.append(
                f"main() 経由で共有ライブラリ不在を渡しても exit code が 2 にならなかった: "
                f"code={proc12.returncode} stdout={proc12.stdout!r} stderr={proc12.stderr!r}"
            )

    # --- 13) 指摘3: main() の終了コード写像 — 違反(1)経路を CLI 全体で貫通確認 ---
    with tempfile.TemporaryDirectory() as td13:
        mismatched_cli_settings = Path(td13) / "mismatched-cli.json"
        mismatched_cli_settings.write_text(
            json.dumps({"permissions": {"deny": ["Read(.env.example)"]}}), encoding="utf-8"
        )
        proc13 = subprocess.run(
            [
                sys.executable, str(Path(__file__).resolve()),
                "--settings-path", str(mismatched_cli_settings),
                "--lib-path", str(LIB_PATH),
            ],
            capture_output=True, text=True, timeout=30,
        )
        if proc13.returncode != 1:
            failures.append(
                f"main() 経由でひな形名を deny に渡しても exit code が 1 にならなかった: "
                f"code={proc13.returncode} stdout={proc13.stdout!r} stderr={proc13.stderr!r}"
            )

    # --- 14) 変異テスト（#1031-2）: 小文字正規化を外すと期待値表が FAIL することを実測 ---
    if LIB_PATH.is_file():
        original14 = LIB_PATH.read_text(encoding="utf-8")
        target14 = """  _heg_lower=$(printf '%s' "$_heg_base" | tr '[:upper:]' '[:lower:]')\n"""
        if target14 not in original14:
            failures.append("変異テスト14の事前条件不成立: 小文字正規化の行が源文に見つからない")
        else:
            mutated14 = original14.replace(target14, '  _heg_lower="$_heg_base"\n')
            if mutated14 == original14:
                failures.append("変異テスト14の事後条件不成立: 置換しても内容が変わらなかった")
            else:
                with tempfile.TemporaryDirectory() as td14:
                    mutated_lib14 = Path(td14) / "env_allowlist.sh"
                    mutated_lib14.write_text(mutated14, encoding="utf-8")
                    v14 = hook_verdict(".ENV", mutated_lib14, runner=recording_runner)
                    mism14 = verdict_mismatches(mutated_lib14, runner=recording_runner)
                    if v14 is not False:
                        failures.append(f"変異テスト14の前提不成立: 変異版でも '.ENV' がブロックされた（verdict={v14}）")
                    elif not any("'.ENV'" in m for m in mism14):
                        failures.append(f"小文字正規化を外しても期待値表が検出しなかった: {mism14}")
    else:
        failures.append("変異テスト14の対象 env_allowlist.sh が見つからない")

    # --- 15) 変異テスト（#1031-1 / レビュー指摘 1）: ひな形分岐を緩めると FAIL するか ---
    #     3 種の退行を個別に実測する:
    #       15a: 旧ワイルドカード `.env.example*` への退行（任意の名前を通す）
    #       15b: 削除したロケール変種 `.env.example.[a-z][a-z]` の再導入（`.ci` / `.qa` を通す）
    #       15c: ひな形判定を小文字正規化後の値で行う（`.ENV.EXAMPLE` を通す・指摘 2 の設計）
    TEMPLATE_BRANCH = "    .env.example|.env.sample|.env.template|.env.dist) return 1 ;;"
    TEMPLATE_CASE_HEAD = '  case "$_heg_base" in'
    mutations15: list[tuple[str, str, str, str]] = [
        (
            "15a（旧ワイルドカードへの退行）",
            TEMPLATE_BRANCH,
            "    .env.example*|.env.sample|.env.template|.env.dist) return 1 ;;",
            ".env.example.secret",
        ),
        (
            "15b（削除したロケール変種の再導入）",
            TEMPLATE_BRANCH,
            TEMPLATE_BRANCH + "\n    .env.example.[a-z][a-z]) return 1 ;;",
            ".env.example.ci",
        ),
        (
            "15c（ひな形判定を小文字正規化後の値で行う）",
            TEMPLATE_CASE_HEAD,
            '  case "$_heg_lower" in',
            ".ENV.EXAMPLE",
        ),
    ]
    if LIB_PATH.is_file():
        original15 = LIB_PATH.read_text(encoding="utf-8")
        for label15, src15, dst15, leaked15 in mutations15:
            # 事前条件: 置換対象の文字列が源文に存在するか
            if src15 not in original15:
                failures.append(f"変異テスト{label15}の事前条件不成立: 置換対象の文字列が源文に見つからない")
                continue
            mutated15 = original15.replace(src15, dst15)
            # 事後条件: 置換で内容が変わったか
            if mutated15 == original15:
                failures.append(f"変異テスト{label15}の事後条件不成立: 置換しても内容が変わらなかった")
                continue
            with tempfile.TemporaryDirectory() as td15:
                mutated_lib15 = Path(td15) / "env_allowlist.sh"
                mutated_lib15.write_text(mutated15, encoding="utf-8")
                v15 = hook_verdict(leaked15, mutated_lib15, runner=recording_runner)
                mism15 = verdict_mismatches(mutated_lib15, runner=recording_runner)
                if v15 is not False:
                    failures.append(
                        f"変異テスト{label15}の前提不成立: 変異版でも '{leaked15}' がブロックされた（verdict={v15}）"
                    )
                elif not any(f"'{leaked15}'" in m for m in mism15):
                    failures.append(
                        f"変異テスト{label15}（'{leaked15}' が素通し）を期待値表が検出しなかった: {mism15}"
                    )
    else:
        failures.append("変異テスト15の対象 env_allowlist.sh が見つからない")

    # --- 16) 負ケース: ひな形定義を「片方だけ」更新した状態（要素間の関係が不正・#896 相当）---
    #     hook_env_guard_template_names にだけ `.env.internal` を足し、verdict 側は
    #     従来どおりブロックしたままにする（両方更新する 9) とは別の分岐を突く）。
    if LIB_PATH.is_file():
        original16 = LIB_PATH.read_text(encoding="utf-8")
        tmpl_target16 = ".env.example\n.env.sample\n.env.template\n.env.dist\nEOF"
        if tmpl_target16 not in original16:
            failures.append("負ケース16の事前条件不成立: ひな形一覧が源文に見つからない")
        else:
            mutated16 = original16.replace(
                tmpl_target16,
                ".env.example\n.env.sample\n.env.template\n.env.dist\n.env.internal\nEOF",
            )
            if mutated16 == original16:
                failures.append("負ケース16の事後条件不成立: 置換しても内容が変わらなかった")
            else:
                with tempfile.TemporaryDirectory() as td16:
                    mutated_lib16 = Path(td16) / "env_allowlist.sh"
                    mutated_lib16.write_text(mutated16, encoding="utf-8")
                    code16, viol16 = check_consistency(
                        real_deny or [".env"], mutated_lib16, runner=recording_runner
                    )
                    if code16 != 1:
                        failures.append(f"ひな形一覧の片側更新が違反として検出されなかった: code={code16}")
                    elif not any(".env.internal" in v and "ブロック対象になっている" in v for v in viol16):
                        failures.append(
                            f"片側更新（一覧だけ追加・verdict は未追随）の矛盾が violations に出ていない: {viol16}"
                        )
    else:
        failures.append("負ケース16の対象 env_allowlist.sh が見つからない")

    # --- 17) レビュー指摘 4: lib_path をシェル文字列へ直接補間しないこと（コマンド注入の回帰）---
    #     `TMPDIR` が `/tmp/a"$(touch /tmp/pwned)"/` のような値でも、`bash -c` の文字列内で
    #     展開されず、かつ正しく source できることを実測する。
    with tempfile.TemporaryDirectory() as td17:
        # 注入が起きたときの痕跡は cwd 相対で作らせる（ディレクトリ名に `/` を入れられないため）。
        # そのため本テスト専用に cwd=td17 の runner を使う。
        def cwd_runner(args: list[str]) -> subprocess.CompletedProcess:
            calls.append(list(args))
            return subprocess.run(args, capture_output=True, text=True, timeout=10, cwd=td17)

        canary = Path(td17) / "canary.txt"
        hostile_dir = Path(td17) / 'a"$(touch canary.txt)"b'
        hostile_dir.mkdir()
        hostile_lib = hostile_dir / "env_allowlist.sh"
        hostile_lib.write_text(LIB_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        v17 = hook_verdict(".env", hostile_lib, runner=cwd_runner)
        t17 = template_names(hostile_lib, runner=cwd_runner)
        if canary.exists():
            failures.append(
                "lib_path に埋め込んだコマンド置換が実行された"
                "（shlex.quote によるシェル引用の回帰・レビュー指摘 4）"
            )
        if v17 is not True:
            failures.append(f"引用が必要なパスの共有ライブラリを source できなかった: verdict={v17}")
        if t17 != APPROVED_TEMPLATE_NAMES:
            failures.append(f"引用が必要なパスからひな形一覧を取得できなかった: {t17}")

    # --- 18〜32) 第3の軸: PreToolUse matcher の配線検査（#1090） ------------------------
    #     見逃し経路の列挙（本節が個別に検証するもの）:
    #       - settings.json 不在／JSON パース失敗／トップレベルが dict でない
    #       - hooks が dict でない／PreToolUse が list でない
    #       - ENV_GUARD_HOOK_SCRIPT を実行するエントリが 1 件も無い（部分一致で誤検出しないか）
    #       - matcher が空文字列
    #       - 必要ツールの一部だけが欠けている（複数バリアント）
    #       - matcher が複数エントリに分散していても union で判定できるか
    #       - 要素間の関係が不正（#896 相当）: 「全ツールを列挙した matcher」を持つが
    #         別スクリプトを実行するエントリに惑わされないか
    #       - matcher のツール順序・空白の揺れ
    #       - 変異テスト: 実際の matcher から `|Grep|Glob` を削る（#1090 の実際の退行を再現）
    #       - 変異テスト: run_checks() から本軸の呼び出しを外す（本番の主コードパス）

    real_settings_data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))

    def _settings_with_pretooluse(pre_entries: list) -> dict:
        """実際の settings.json の `permissions` 等はそのままに、`hooks.PreToolUse` だけを
        差し替えた辞書を返す（deny × allowlist 側の判定結果を固定したまま、matcher 配線
        検査だけを独立に動かすため）。"""
        data = json.loads(json.dumps(real_settings_data))  # deep copy
        data.setdefault("hooks", {})["PreToolUse"] = pre_entries
        return data

    GUARD_ENTRY_FULL = {
        "matcher": "Read|Write|Edit|NotebookEdit|Grep|Glob",
        "hooks": [{"type": "command", "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/pre-file-tool-env-guard.sh"}],
    }

    # --- 18) 正常系: 実際の settings.json は matcher 配線に不足が無いはず ---
    code18, viol18 = check_env_guard_matcher_wiring(SETTINGS_PATH)
    if code18 != 0:
        failures.append(f"実際の settings.json の matcher 配線が不足なしのはずが code={code18} violations={viol18}")

    with tempfile.TemporaryDirectory() as td_wire:
        # --- 19) 失敗経路: settings.json 不在 ---
        missing19 = Path(td_wire) / "missing19.json"
        code19, _ = check_env_guard_matcher_wiring(missing19)
        if code19 != 2:
            failures.append(f"settings.json 不在で matcher 配線検査が判定不能(2)にならなかった: code={code19}")

        # --- 20) 失敗経路: JSON パース失敗 ---
        broken20 = Path(td_wire) / "broken20.json"
        broken20.write_text("{not valid json", encoding="utf-8")
        code20, _ = check_env_guard_matcher_wiring(broken20)
        if code20 != 2:
            failures.append(f"JSON パース失敗で matcher 配線検査が判定不能(2)にならなかった: code={code20}")

        # --- 21) 失敗経路: hooks が dict でない ---
        bad_hooks21 = Path(td_wire) / "bad_hooks21.json"
        bad_hooks21.write_text(json.dumps({"hooks": "not-a-dict"}), encoding="utf-8")
        code21, _ = check_env_guard_matcher_wiring(bad_hooks21)
        if code21 != 2:
            failures.append(f"hooks が dict でない場合に判定不能(2)にならなかった: code={code21}")

        # --- 22) 失敗経路: PreToolUse が list でない ---
        bad_pre22 = Path(td_wire) / "bad_pre22.json"
        bad_pre22.write_text(json.dumps({"hooks": {"PreToolUse": "not-a-list"}}), encoding="utf-8")
        code22, _ = check_env_guard_matcher_wiring(bad_pre22)
        if code22 != 2:
            failures.append(f"PreToolUse が list でない場合に判定不能(2)にならなかった: code={code22}")

        # --- 23) エントリ0件: ENV_GUARD_HOOK_SCRIPT を参照するエントリが無い ---
        no_entry23 = Path(td_wire) / "no_entry23.json"
        no_entry23.write_text(
            json.dumps(_settings_with_pretooluse(
                [{"matcher": "Bash", "hooks": [{"type": "command", "command": "some-other-hook.sh"}]}]
            )),
            encoding="utf-8",
        )
        code23, viol23 = check_env_guard_matcher_wiring(no_entry23)
        if code23 != 1:
            failures.append(f"エントリ不在が違反(1)として検出されなかった: code={code23}")
        elif not any("見つからない" in v for v in viol23):
            failures.append(f"エントリ不在の理由が violations に反映されていない: {viol23}")

        # --- 24) matcher が空文字列 ---
        empty_matcher24 = Path(td_wire) / "empty_matcher24.json"
        empty_matcher24.write_text(
            json.dumps(_settings_with_pretooluse([{**GUARD_ENTRY_FULL, "matcher": ""}])),
            encoding="utf-8",
        )
        code24, viol24 = check_env_guard_matcher_wiring(empty_matcher24)
        if code24 != 1:
            failures.append(f"matcher 空文字列が違反(1)として検出されなかった: code={code24}")
        elif not any("空文字列" in v for v in viol24):
            failures.append(f"matcher 空文字列の理由が violations に反映されていない: {viol24}")

        # --- 25) 必要ツールの一部欠落（バリアント3種） ---
        for missing_matcher, expect_missing in [
            ("Read|Write|Edit|NotebookEdit|Glob", ["Grep"]),
            ("Read|Write|Edit|NotebookEdit|Grep", ["Glob"]),
            ("Read|Write|Edit", ["NotebookEdit", "Grep", "Glob"]),
        ]:
            p25 = Path(td_wire) / f"partial25_{'_'.join(expect_missing)}.json"
            p25.write_text(
                json.dumps(_settings_with_pretooluse([{**GUARD_ENTRY_FULL, "matcher": missing_matcher}])),
                encoding="utf-8",
            )
            code25, viol25 = check_env_guard_matcher_wiring(p25)
            if code25 != 1:
                failures.append(
                    f"matcher '{missing_matcher}' の欠落ツールが違反(1)として検出されなかった: code={code25}"
                )
            elif not any(all(m in v for m in expect_missing) for v in viol25):
                failures.append(
                    f"matcher '{missing_matcher}' の欠落ツール {expect_missing} が violations に反映されていない: {viol25}"
                )

        # --- 26) 複数エントリに分散していても union で判定できる ---
        split26 = Path(td_wire) / "split26.json"
        split26.write_text(
            json.dumps(_settings_with_pretooluse([
                {"matcher": "Read|Write|Edit", "hooks": [GUARD_ENTRY_FULL["hooks"][0]]},
                {"matcher": "NotebookEdit|Grep|Glob", "hooks": [GUARD_ENTRY_FULL["hooks"][0]]},
            ])),
            encoding="utf-8",
        )
        code26, viol26 = check_env_guard_matcher_wiring(split26)
        if code26 != 0:
            failures.append(f"matcher が複数エントリに分散した union が合格(0)にならなかった: code={code26} violations={viol26}")

        # --- 27) 負ケース（#896 相当）: 全ツールを列挙した matcher を持つが別スクリプトの
        #     エントリに惑わされず、guard 参照エントリ側の不足を検出できるか ---
        confuse27 = Path(td_wire) / "confuse27.json"
        confuse27.write_text(
            json.dumps(_settings_with_pretooluse([
                {
                    "matcher": "Read|Write|Edit|NotebookEdit|Grep|Glob",
                    "hooks": [{"type": "command", "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/some-other-hook.sh"}],
                },
                {
                    "matcher": "Read|Write",
                    "hooks": [GUARD_ENTRY_FULL["hooks"][0]],
                },
            ])),
            encoding="utf-8",
        )
        code27, viol27 = check_env_guard_matcher_wiring(confuse27)
        if code27 != 1:
            failures.append(
                f"別スクリプトの完全な matcher に惑わされて guard 側の不足を見逃した: code={code27} violations={viol27}"
            )
        elif not any("Grep" in v and "Glob" in v for v in viol27):
            failures.append(f"負ケース27の欠落ツールが violations に正しく反映されていない: {viol27}")

        # --- 28) matcher のツール順序・空白の揺れは判定に影響しない ---
        loose28 = Path(td_wire) / "loose28.json"
        loose28.write_text(
            json.dumps(_settings_with_pretooluse([
                {"matcher": " Glob | Grep|NotebookEdit|Edit|Write | Read ", "hooks": [GUARD_ENTRY_FULL["hooks"][0]]},
            ])),
            encoding="utf-8",
        )
        code28, viol28 = check_env_guard_matcher_wiring(loose28)
        if code28 != 0:
            failures.append(f"matcher の順序・空白の揺れで誤って違反判定になった: code={code28} violations={viol28}")

        # --- 29) main() 経由（CLI 全体）で wiring 違反時に exit 1 になることを実測 ---
        cli29_settings = Path(td_wire) / "cli29.json"
        cli29_settings.write_text(
            json.dumps(_settings_with_pretooluse(
                [{**GUARD_ENTRY_FULL, "matcher": "Read|Write|Edit|NotebookEdit"}]
            )),
            encoding="utf-8",
        )
        proc29 = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--settings-path", str(cli29_settings), "--lib-path", str(LIB_PATH)],
            capture_output=True, text=True, timeout=30,
        )
        if proc29.returncode != 1:
            failures.append(
                f"main() 経由で matcher 欠落を渡しても exit code が 1 にならなかった: "
                f"code={proc29.returncode} stdout={proc29.stdout!r} stderr={proc29.stderr!r}"
            )
        elif "Grep" not in proc29.stderr or "Glob" not in proc29.stderr:
            failures.append(f"main() 経由の出力に欠落ツール(Grep/Glob)が含まれていない: stderr={proc29.stderr!r}")

    # --- 30) 変異テスト（#1090 の実際の退行を再現）: 実際の settings.json のテキストから
    #     `|Grep|Glob` を削ると、matcher 配線検査が missing=['Grep','Glob'] を検出するか ---
    real_settings_text = SETTINGS_PATH.read_text(encoding="utf-8")
    target30 = '"matcher": "Read|Write|Edit|NotebookEdit|Grep|Glob"'
    if target30 not in real_settings_text:
        failures.append("変異テスト30の事前条件不成立: 実際の settings.json に元の matcher 文字列が見つからない")
    else:
        mutated30 = real_settings_text.replace(target30, '"matcher": "Read|Write|Edit|NotebookEdit"')
        if mutated30 == real_settings_text:
            failures.append("変異テスト30の事後条件不成立: 置換しても内容が変わらなかった")
        else:
            with tempfile.TemporaryDirectory() as td30:
                mutated_settings30 = Path(td30) / "mutated30.json"
                mutated_settings30.write_text(mutated30, encoding="utf-8")
                code30, viol30 = check_env_guard_matcher_wiring(mutated_settings30)
                if code30 != 1:
                    failures.append(
                        f"変異テスト30（実際の matcher から |Grep|Glob を削る）が検出されなかった: code={code30}"
                    )
                elif not any("Grep" in v and "Glob" in v for v in viol30):
                    failures.append(f"変異テスト30の欠落ツールが violations に正しく反映されていない: {viol30}")

    # --- 31) 変異テスト（本番の主コードパス）: run_checks() から本軸の呼び出しを外すと
    #     main() 経由の判定が wiring 違反を見逃すようになることを実測する
    #     （check-tool-design-rules.md §4: 終了コードを返す経路〔main()〜sys.exit()〕を
    #     変異対象に必ず 1 つ含める）。本ファイル自身のソースを一時コピーへ変異させ、
    #     元ファイルには一切書き込まない。 ---
    self_src31 = Path(__file__).read_text(encoding="utf-8")
    target31 = (
        "    wiring_code, wiring_violations = check_env_guard_matcher_wiring(settings_path)\n"
        "    violations = violations + wiring_violations\n"
        "    code = max(code, wiring_code)\n"
    )
    if target31 not in self_src31:
        failures.append("変異テスト31の事前条件不成立: run_checks() の wiring 統合コードが源文に見つからない")
    else:
        mutated31 = self_src31.replace(target31, "")
        if mutated31 == self_src31:
            failures.append("変異テスト31の事後条件不成立: 置換しても内容が変わらなかった")
        else:
            with tempfile.TemporaryDirectory() as td31:
                mutated_script31 = Path(td31) / "check_env_guard_consistency_mutated.py"
                mutated_script31.write_text(mutated31, encoding="utf-8")
                broken_wiring_settings31 = Path(td31) / "broken_wiring31.json"
                broken_wiring_settings31.write_text(
                    json.dumps(_settings_with_pretooluse(
                        [{**GUARD_ENTRY_FULL, "matcher": "Read|Write|Edit|NotebookEdit"}]
                    )),
                    encoding="utf-8",
                )
                proc31 = subprocess.run(
                    [
                        sys.executable, str(mutated_script31),
                        "--settings-path", str(broken_wiring_settings31),
                        "--lib-path", str(LIB_PATH),
                    ],
                    capture_output=True, text=True, timeout=30,
                )
                if proc31.returncode != 0:
                    failures.append(
                        "変異テスト31の前提不成立: run_checks() の統合を外した変異版が、"
                        f"それでも wiring 違反を検出してしまった（期待は誤って PASS すること）: "
                        f"code={proc31.returncode} stdout={proc31.stdout!r} stderr={proc31.stderr!r}"
                    )
                # 対比: 変異していない本物のスクリプトなら同じ入力で exit 1 になるはず
                proc31_orig = subprocess.run(
                    [
                        sys.executable, str(Path(__file__).resolve()),
                        "--settings-path", str(broken_wiring_settings31),
                        "--lib-path", str(LIB_PATH),
                    ],
                    capture_output=True, text=True, timeout=30,
                )
                if proc31_orig.returncode != 1:
                    failures.append(
                        "変異テスト31の対比不成立: 変異していない本物のスクリプトが同じ壊れた wiring "
                        f"入力に対して exit 1 を返さなかった: code={proc31_orig.returncode}"
                    )

    # --- 32) 要素間の関係性の負ケース（#896・§6 とは別分岐）: matcher に必要ツールは
    #     全て入っているが、そのエントリが実行するのは別のフックスクリプトである負ケース。
    #     27) はここに「別スクリプト側は正しい・guard 側は不足」という組み合わせだったが、
    #     本節は「guard を参照するエントリが 1 つも無く、matcher だけは完璧なエントリが
    #     別スクリプト用に存在する」という、より紛らわしい構成を単独で検証する。 ---
    with tempfile.TemporaryDirectory() as td32:
        only_other_settings32 = Path(td32) / "only_other32.json"
        only_other_settings32.write_text(
            json.dumps(_settings_with_pretooluse([
                {
                    "matcher": "Read|Write|Edit|NotebookEdit|Grep|Glob",
                    "hooks": [{"type": "command", "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/pre-tool-use-router.sh"}],
                },
            ])),
            encoding="utf-8",
        )
        code32, viol32 = check_env_guard_matcher_wiring(only_other_settings32)
        if code32 != 1:
            failures.append(
                f"guard を参照しないエントリの完璧な matcher に惑わされてエントリ不在を見逃した: code={code32}"
            )
        elif not any("見つからない" in v for v in viol32):
            failures.append(f"負ケース32の理由が violations に反映されていない: {viol32}")

    # 指摘1の最終確認: ここまでの全シナリオを通じて本番の共有フック実体が
    # 一切変更されていないことを実測する（一時ファイル化が漏れなく効いていることの保証）。
    lib_after = LIB_PATH.read_text(encoding="utf-8") if LIB_PATH.is_file() else None
    if lib_snapshot != lib_after:
        failures.append(
            "self-test が本番の .claude/hooks/lib/env_allowlist.sh を変更してしまった"
            "（指摘1 CRITICAL の回帰）"
        )

    if failures:
        print("[check_env_guard_consistency][self-test] FAIL", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"[check_env_guard_consistency][self-test] OK（fake runner 呼び出し {len(calls)} 件）")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help="self-test を実行する")
    parser.add_argument("--json", action="store_true", help="結果を JSON で出力する")
    parser.add_argument(
        "--settings-path",
        type=Path,
        default=SETTINGS_PATH,
        help="検査対象の settings.json パス（既定: リポジトリの .claude/settings.json。主に self-test 用）",
    )
    parser.add_argument(
        "--lib-path",
        type=Path,
        default=LIB_PATH,
        help="検査対象の env_allowlist.sh パス（既定: リポジトリの共有ライブラリ。主に self-test 用）",
    )
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    code, violations = run_checks(settings_path=args.settings_path, lib_path=args.lib_path)
    if args.json:
        print(json.dumps({"exit_code": code, "violations": violations}, ensure_ascii=False))
        return code

    if code == 0:
        print("[check_env_guard_consistency] PASS（.env deny 列挙と共有 allowlist は矛盾なし）")
    else:
        label = "FAIL" if code == 1 else "判定不能"
        print(f"[check_env_guard_consistency] {label}", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
