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

終了コード:
  0 = 合格（矛盾なし）
  1 = 矛盾あり（deny の名前が第2層でブロックされない／ひな形が deny にも列挙されている／
      deny に未対応形式の `.env` エントリがある／ひな形一覧が承認済みリストの外にある 等）
  2 = 判定不能（settings.json / env_allowlist.sh が読めない・パース失敗・bash 呼び出し失敗・
      .env 系の deny エントリが 1 件も無い〔対象 0 件〕。いずれも fail-closed で非ゼロにする）
"""

from __future__ import annotations

import argparse
import json
import re
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


def default_bash_runner(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=10)


def hook_verdict(path: str, lib_path: Path, runner=default_bash_runner) -> bool | None:
    """共有ライブラリの hook_env_guard_verdict を実際に bash で呼び出す。

    戻り値: True = ブロック対象 / False = 対象外 / None = 呼び出し失敗（判定不能）
    """
    if not lib_path.is_file():
        return None
    script = f'source "{lib_path}"; hook_env_guard_verdict "$1"'
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
    script = f'source "{lib_path}"; hook_env_guard_template_names'
    try:
        proc = runner(["bash", "-c", script, "bash"])
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    names = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    return names or None


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
        target4b = (
            ".env.example|.env.sample|.env.template|.env.dist|.env.example.*) return 1 ;;\n"
            "    .env|.env.*) return 0 ;;"
        )
        if target4b not in original4b:
            failures.append("変異テスト4bの事前条件不成立: 置換対象の文字列が源文に見つからない")
        else:
            mutated4b = original4b.replace(
                target4b,
                target4b.replace(
                    "    .env|.env.*) return 0 ;;",
                    "    .env.production) return 1 ;;\n    .env|.env.*) return 0 ;;",
                ),
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

    # --- 5) 入力バリアントの展開 ---
    for pattern, expect_block in [
        (".env.*.local", True),
        (".env.stg", True),
        (".env.qa", True),
        ("path/to/.env", True),
        ("./.env", True),
        (".env.example.ja", False),
    ]:
        v = hook_verdict(instantiate(pattern), LIB_PATH, runner=recording_runner)
        if v is not expect_block:
            failures.append(f"入力バリアント '{pattern}' の判定が期待と異なる: got={v} want={expect_block}")

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
        target = ".env.example|.env.sample|.env.template|.env.dist|.env.example.*) return 1 ;;"
        # 事前条件: 置換対象の文字列が源文に存在するか
        if target not in original:
            failures.append("変異テスト7の事前条件不成立: 置換対象の文字列が源文に見つからない")
        else:
            mutated = original.replace(
                target,
                ".env.example|.env.sample|.env.template|.env.dist|.env.example.*) return 0 ;;",
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
        verdict_target9 = ".env.example|.env.sample|.env.template|.env.dist|.env.example.*) return 1 ;;"
        tmpl_target9 = ".env.example\n.env.sample\n.env.template\n.env.dist\nEOF"
        if verdict_target9 not in original9 or tmpl_target9 not in original9:
            failures.append("変異テスト9の事前条件不成立: 置換対象の文字列が源文に見つからない")
        else:
            mutated9 = original9.replace(
                verdict_target9,
                ".env.example|.env.sample|.env.template|.env.dist|.env.example.*|.env.internal) return 1 ;;",
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
