#!/usr/bin/env python3
"""check_delegation_preamble.py — 委譲テンプレートを持つスキルに「並行安全プリアンブル」の展開指示があるかを検査する（Issue #816）

## なぜ必要か

サブエージェントは `CLAUDE.md` も `docs/rules/` も自動では読まない。並行実行中の破壊的 git 操作の
禁止（#93 / #768）は **委譲プロンプトに実テキストで再掲したときだけ** 相手に届く。正本は
`docs/rules/agent-team-summary.md` の節「🔴 並行安全プリアンブル（委譲プロンプトへ貼る実テキスト・SSOT・#816）」で、
各スキルはこの節を Read して実テキスト展開する運用に統一されている。

この運用は「新しく委譲テンプレートを持つスキルを追加したとき、再掲を忘れる」という静かな
失敗モードを持つ。忘れても何もエラーにならず、サブエージェントが `git checkout <branch>` を
実行して親の作業ツリーを壊すまで誰も気づかない。本ツールはその再発を機械検知する。

## 判定契約（何をもって「展開指示がある」とみなすか）

🔴 **`並行安全プリアンブル` と `実テキスト` の 2 語が同じ行に現れる行が 1 行以上あること**（`MARKER_WORDS`）。
展開手順は運用上かならず「…『並行安全プリアンブル』節を Read し、その中身を **実テキストのまま** 展開する」
という **1 行** として書かれるため、この 2 語の同一行共起を充足条件とする。

ファイル全体への素の部分文字列一致（旧実装）は **fail-open** だった: 委譲テンプレートから展開指示が
消えても、説明文・変更履歴・否定文（「以前は並行安全プリアンブルを貼っていたが今は使っていない」）に
語が残っていれば PASS してしまう。2 語同一行判定はこの主要な抜け道を塞ぐ。

加えて **HTML コメント（`<!-- ... -->`）の内側は判定対象から除外する**（複数行にまたがるものも、
閉じられていない `<!--` 以降も除去する）。抑止コメントやコメントアウトされた「悪い例」を
充足の根拠に使わせないため。

### 🔴 本ツールの限界（過信しないこと）

- 検出できるのは **静的テキスト（展開手順の記述）の消失** までである。
  **実行時に実テキストが本当に展開されたか（サブエージェントに届いたか）は検出できない。**
- 2 語同一行判定も **否定文脈を完全には排除できない**。「並行安全プリアンブルを実テキストで貼るのは
  やめた」のように 2 語が同一行に並ぶ否定文は、依然として充足と判定される。
  最終的な担保は人のレビュー（Layer 1 セルフレビュー）であり、本ツールはその前段の粗いネットである。

## 何をどう検査するか（2 段構成）

### 1. 明示リスト検査（fail-closed・主判定・exit code に反映）

「委譲テンプレートを持つファイル」の明示リスト（`REQUIRED_GROUPS`）を定数として持ち、
各グループが上記の判定契約を満たすことを検査する。満たさなければ **違反**。

グループは「いずれか 1 つを満たせばよい」単位である（OR 判定）。`retrospective` のように
委譲テンプレートを `reference.md` 側に持つ構造のスキルは、`SKILL.md` と `reference.md` の
どちらか一方に展開指示があれば充足とする。

### 2. 網羅性メタチェック（ヒューリスティック・警告のみ・exit code を変えない）

`.claude/skills/**/*.md`（サブディレクトリ配下の補助 Markdown を含む）を走査し、委譲テンプレートを
持つ兆候（`DELEGATION_SIGNAL_PATTERNS`・正規表現）があるのに、明示リストにも展開指示にも現れない
ファイルを **警告** として報告する（新規スキル追加時の検知）。ここは誤検知しうるため警告に留め、
終了コードは変えない（fail-open にするのは 1 段目が fail-closed で守っているため）。

正当な例外は、そのファイルの任意の行に次の抑止コメントを書くと警告から除外できる:

    <!-- delegation-preamble: n/a {なぜ再掲が不要かの理由} -->

理由が空のマーカーは無効として扱い、除外しない（人が判断した形跡を残させるのが目的。
`check_selftest_wiring.py` の `selftest-wiring-ok` と同じ思想）。

## 「見逃し（miss）」に至りうる経路（実装前に列挙し、それぞれ塞いだ）

- M-1: 展開指示がコードスパン・見出し・箇条書きの内側にある → 行内の語の共起だけを見る（装飾を問わない）
- M-2: 明示リストの要素がリポジトリから消えている → ファイル不在は「充足」ではなく **違反** に倒す
- M-3: ファイルが非 UTF-8 / 読み取り不能 → 黙って「参照なし」にせず **exit 2（判定不能）** に倒す
- M-4: 網羅性メタチェックの警告が主判定の exit code を上書きする → 警告は exit code に一切関与させない
- M-5: 抑止コメントが理由なしで乱用される → 理由が空のマーカーは無効
- M-6: 展開指示が消えても説明文・否定文に語が残る（旧実装の fail-open） → 2 語同一行判定にした
- M-7: HTML コメント内の記述（抑止コメント・悪い例）で充足してしまう → コメントを除去してから判定する
- M-8: 委譲テンプレートがサブディレクトリの補助 Markdown にある → 走査を `**/*.md` へ広げた
- M-9: 兆候語の平文リストが実在の表現（`` `Agent` ツール ``・`background Agent`・`fan-out`）を取り逃す
       → 正規表現ベースの緩いマッチにした
- M-10: `REQUIRED_GROUPS` に同じパスを重複登録し、判定対象を取り違える → 起動時に重複を検出し exit 2

## 使い方

    python3 tools/check_delegation_preamble.py            # 人間向けテキスト（既定）
    python3 tools/check_delegation_preamble.py --json     # 機械可読 JSON
    python3 tools/check_delegation_preamble.py --root DIR # 検査対象のルートを差し替える（テスト用）
    python3 tools/check_delegation_preamble.py --self-test

## 終了コード

- 0: PASS（明示リストの全グループが判定契約を満たす。警告があっても 0）
- 1: 違反あり（展開指示を欠くグループがある。対象パスを stderr に列挙）
- 2: 判定不能（ファイル読み取り不能・非 UTF-8・`REQUIRED_GROUPS` の重複等。fail-closed。黙って PASS にしない）
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# 正本（docs/rules/agent-team-summary.md）の節見出しに含まれる語。表示・JSON の `marker` に使う。
REFERENCE_MARKER = "並行安全プリアンブル"

# 🔴 判定契約: この 2 語が **同じ行** に現れる行が 1 行以上あれば「展開指示あり」とみなす。
# 語を減らす・片方だけの部分文字列一致へ戻すと fail-open に退行する（M-6）。
MARKER_WORDS: tuple[str, ...] = ("並行安全プリアンブル", "実テキスト")

# 明示リスト（fail-closed・主判定）。
# 各要素は (グループ名, そのグループに属するパス群) で、**いずれか 1 つ** が
# 判定契約を満たせば充足とする（OR 判定）。
REQUIRED_GROUPS: list[tuple[str, tuple[str, ...]]] = [
    (
        "retrospective",
        (
            ".claude/skills/retrospective/SKILL.md",
            ".claude/skills/retrospective/reference.md",
        ),
    ),
    ("discussion-review", (".claude/skills/discussion-review/SKILL.md",)),
    ("waiting-user-handler", (".claude/skills/waiting-user-handler/SKILL.md",)),
    ("self-improvement-loop", (".claude/skills/self-improvement-loop/SKILL.md",)),
    ("code-review", (".claude/skills/code-review/SKILL.md",)),
    # Sprint Review を fan-out 2 役割で起動する（#821）
    ("pr-review-watcher", (".claude/skills/pr-review-watcher/SKILL.md",)),
    # Skill(code-review) 失敗時にサブエージェント直接起動へフォールバックする（#821）
    ("self-reviewer", (".claude/skills/self-reviewer/SKILL.md",)),
]

# 網羅性メタチェックの兆候（委譲テンプレートを持つ疑いがあることを示す）。
# 平文リストは実在の表現を取り逃したため（M-9）、正規表現ベースの緩いマッチにしてある。
# (ラベル, パターン) の組。ラベルは JSON の `warnings[].signals` に出る。
DELEGATION_SIGNAL_PATTERNS: tuple[tuple[str, str], ...] = (
    ("subagent_type", r"subagent_type"),
    ("Agent ツール", r"`?Agent`?\s*ツール"),
    ("background Agent", r"background\s+`?Agent`?"),
    ("Agent(", r"\bAgent\s*\("),
    ("並列サブエージェント", r"並列サブエージェント"),
    ("委譲プロンプト", r"委譲プロンプト"),
    ("fan-out", r"fan-?out"),
)

_SIGNAL_RES: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (label, re.compile(pat, re.IGNORECASE)) for label, pat in DELEGATION_SIGNAL_PATTERNS
)

# 抑止コメント: <!-- delegation-preamble: n/a 理由 -->（理由が空のものは無効）
SUPPRESSION_RE = re.compile(
    r"<!--\s*delegation-preamble:\s*n/a\s+(?P<reason>\S[^>]*?)\s*-->"
)

# HTML コメント（複数行対応）。閉じられていない `<!--` 以降も除去する（fail-closed 方向）。
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_UNCLOSED_COMMENT_RE = re.compile(r"<!--.*\Z", re.DOTALL)


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


class UndecidableError(Exception):
    """判定不能（exit 2）。黙って PASS にしないためのシグナル。"""


def read_text(path: Path) -> str:
    """UTF-8 で読む。読めなければ UndecidableError にして fail-closed にする。"""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise UndecidableError(f"{path}: 非 UTF-8 として読み取れません（{exc}）") from exc
    except OSError as exc:
        raise UndecidableError(f"{path}: 読み取りに失敗しました（{exc}）") from exc


def strip_html_comments(text: str) -> str:
    """HTML コメントを除去する（複数行・未閉鎖を含む）。judge 対象から外すため（M-7）。"""
    stripped = _HTML_COMMENT_RE.sub("\n", text)
    return _UNCLOSED_COMMENT_RE.sub("\n", stripped)


def has_marker(text: str) -> bool:
    """判定契約: HTML コメントを除いた本文に、MARKER_WORDS を **すべて含む 1 行** があるか。"""
    for line in strip_html_comments(text).splitlines():
        if all(word in line for word in MARKER_WORDS):
            return True
    return False


def suppression_reason(text: str) -> str | None:
    """抑止コメントは HTML コメントそのものなので、**除去前の原文** から探す。"""
    m = SUPPRESSION_RE.search(text)
    if not m:
        return None
    reason = m.group("reason").strip()
    return reason or None  # 理由が空のマーカーは無効（除外しない）


def validate_required_groups() -> str | None:
    """`REQUIRED_GROUPS` の健全性（パス重複）を検査する。問題があれば理由文字列を返す。"""
    seen: dict[str, str] = {}
    dups: list[str] = []
    for name, paths in REQUIRED_GROUPS:
        for rel in paths:
            if rel in seen:
                dups.append(f"{rel}（{seen[rel]} と {name}）")
            else:
                seen[rel] = name
    if dups:
        return "REQUIRED_GROUPS に重複パスがあります: " + " / ".join(dups)
    return None


def check_required(root: Path) -> list[dict]:
    """明示リスト検査（主判定）。グループ単位の結果を返す。"""
    results: list[dict] = []
    for name, paths in REQUIRED_GROUPS:
        members: list[dict] = []
        satisfied = False
        for rel in paths:
            p = root / rel
            if not p.is_file():
                members.append({"path": rel, "exists": False, "has_marker": False})
                continue
            found = has_marker(read_text(p))
            members.append({"path": rel, "exists": True, "has_marker": found})
            if found:
                satisfied = True
        results.append({"group": name, "satisfied": satisfied, "members": members})
    return results


def collect_skill_files(root: Path) -> list[Path]:
    """`.claude/skills/` 配下の Markdown をサブディレクトリ込みで走査する（M-8）。"""
    skills = root / ".claude" / "skills"
    if not skills.is_dir():
        return []
    return sorted(p for p in skills.glob("*/**/*.md") if p.is_file())


def detect_signals(text: str) -> list[str]:
    return [label for label, rx in _SIGNAL_RES if rx.search(text)]


def check_coverage(root: Path, required_paths: set[str]) -> list[dict]:
    """網羅性メタチェック（警告のみ）。exit code には一切関与しない。"""
    warnings: list[dict] = []
    for p in collect_skill_files(root):
        rel = p.relative_to(root).as_posix()
        if rel in required_paths:
            continue
        text = read_text(p)
        if has_marker(text):
            continue
        reason = suppression_reason(text)
        if reason:
            continue
        signals = detect_signals(strip_html_comments(text))
        if signals:
            warnings.append({"path": rel, "signals": signals})
    return warnings


def render_text(groups: list[dict], warnings: list[dict]) -> int:
    unsatisfied = [g for g in groups if not g["satisfied"]]
    for w in warnings:
        print(
            f"⚠️ 委譲テンプレートの兆候があるのに「{REFERENCE_MARKER}」の実テキスト展開指示がありません"
            f"（ヒューリスティック・要確認）: {w['path']} — 兆候: {', '.join(w['signals'])}",
            file=sys.stderr,
        )
    if unsatisfied:
        print(
            f"❌ 委譲テンプレートに「{REFERENCE_MARKER}」の実テキスト展開指示がありません（Issue #816）:",
            file=sys.stderr,
        )
        for g in unsatisfied:
            paths = " / ".join(m["path"] for m in g["members"])
            print(f"  - {g['group']}: {paths}", file=sys.stderr)
        print(
            "  → 正本: docs/rules/agent-team-summary.md の「🔴 並行安全プリアンブル」節を"
            "Read して実テキストを展開すること"
            f"（判定契約: {' と '.join(MARKER_WORDS)} が同じ行にあること）",
            file=sys.stderr,
        )
        return 1
    print(
        f"✅ 明示リスト {len(groups)} グループすべてに「{REFERENCE_MARKER}」の実テキスト展開指示があります"
        + (f"（警告 {len(warnings)} 件）" if warnings else "")
    )
    return 0


# --------------------------------------------------------------------------
# self-test（フィクスチャを一時ディレクトリへ作り、本番の入口 main() を経由させる・#686）
# --------------------------------------------------------------------------

_SKILL_DIR = ".claude/skills"

# フィクスチャ既定の充足行（2 語が同一行）。
_OK_LINE = "「並行安全プリアンブル」節を Read し、その中身を実テキストのまま展開する"

_FIXTURE_SINGLES = (
    "discussion-review",
    "waiting-user-handler",
    "self-improvement-loop",
    "code-review",
    "pr-review-watcher",
    "self-reviewer",
)


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _build_fixture(root: Path, marker_text: str = _OK_LINE) -> None:
    """明示リストの全グループを充足させた最小フィクスチャを作る。"""
    _write(root, f"{_SKILL_DIR}/retrospective/SKILL.md", "# retrospective\n")
    _write(
        root,
        f"{_SKILL_DIR}/retrospective/reference.md",
        f"# reference\n{marker_text}\n",
    )
    for name in _FIXTURE_SINGLES:
        _write(root, f"{_SKILL_DIR}/{name}/SKILL.md", f"# {name}\n{marker_text}\n")


def _run_main(root: Path, extra: list[str] | None = None) -> tuple[int, str, str]:
    """本番の入口 main() を argv 経由で呼び、exit code と stdout/stderr を返す。"""
    import contextlib
    import io

    out, err = io.StringIO(), io.StringIO()
    argv = ["--root", str(root)] + (extra or [])
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


def run_self_test() -> int:  # noqa: C901
    import subprocess
    import tempfile

    failures = 0

    def check(label: str, cond: bool, detail: str = "") -> None:
        nonlocal failures
        if cond:
            print(f"  ✅ {label}")
        else:
            failures += 1
            print(f"  ❌ {label}" + (f"\n     {detail}" if detail else ""))

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _build_fixture(root)
        code, out, err = _run_main(root)
        check("全グループ充足なら exit 0", code == 0, f"code={code} err={err}")

    # T-2: 1 グループが展開指示を欠くと exit 1（主判定・fail-closed）
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _build_fixture(root)
        _write(root, f"{_SKILL_DIR}/code-review/SKILL.md", "# code-review\n（再掲なし）\n")
        code, out, err = _run_main(root)
        check("展開指示を欠くグループがあると exit 1", code == 1, f"code={code}")
        check("違反グループ名が stderr に出る", "code-review" in err, err)

    # T-3: グループは OR 判定（SKILL.md に無く reference.md にあれば充足）
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _build_fixture(root)
        code, _, err = _run_main(root)
        check("グループは OR 判定（片方に展開指示があれば充足）", code == 0, f"code={code} err={err}")

    # T-3b: OR 判定は「先頭のファイルだけが持つ」場合も充足する
    #       （AND への反転・「最後のファイルで上書き」型の実装ミスを検知する）
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _build_fixture(root)
        _write(root, f"{_SKILL_DIR}/retrospective/SKILL.md", f"# retrospective\n{_OK_LINE}\n")
        _write(root, f"{_SKILL_DIR}/retrospective/reference.md", "# reference\n（再掲なし）\n")
        code, _, err = _run_main(root)
        check("グループ先頭のファイルだけが持つ場合も充足", code == 0, f"code={code} err={err}")

    # T-3c: 判定契約はリテラル 2 語の同一行共起である
    #       （定数を短縮・部分化・1 語化する変異を検知する。期待値はテスト側にリテラルで固定）
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _build_fixture(root, marker_text="並行安全プリアンブルを実テキストのまま展開する")
        code, _, err = _run_main(root)
        check("リテラル 2 語が同一行にあれば充足", code == 0, f"code={code} err={err}")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _build_fixture(root, marker_text="安全プリアンブルを実テキストのまま展開する")  # 先頭欠落
        code, _, err = _run_main(root)
        check("惜しい別語『安全プリアンブル』では充足しない", code == 1, f"code={code}")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _build_fixture(root, marker_text="並行安全プリアンブルを展開する")  # 実テキストが無い
        code, _, err = _run_main(root)
        check("『実テキスト』が無ければ充足しない（1 語一致への退行を検知）", code == 1, f"code={code}")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _build_fixture(root, marker_text="並行安全プリアンブル\nを、その中身へ実テキストのまま展開する")
        code, _, err = _run_main(root)
        check("2 語が別の行に分かれていると充足しない（行単位判定）", code == 1, f"code={code}")

    # T-3d【CRITICAL 回帰・#821】否定文脈: 展開指示が消え、語の言及だけが残っても充足しない
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _build_fixture(root)
        _write(
            root,
            f"{_SKILL_DIR}/code-review/SKILL.md",
            "# code-review\n"
            "## 変更履歴\n"
            "- 以前は並行安全プリアンブルを貼っていたが、今は使っていない\n"
            "- 実テキストの展開は行わない方針に変更した\n",
        )
        code, _, err = _run_main(root)
        check("否定文脈の言及だけでは充足しない（fail-open の封鎖）", code == 1, f"code={code}")
        check("否定文脈のとき違反グループ名が出る", "code-review" in err, err)

    # T-3e【CRITICAL 回帰・#821】HTML コメント内の記述は充足に使えない（単一行・複数行とも）
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _build_fixture(root)
        _write(
            root,
            f"{_SKILL_DIR}/code-review/SKILL.md",
            "# code-review\n"
            f"<!-- 悪い例: {_OK_LINE} -->\n",
        )
        code, _, err = _run_main(root)
        check("単一行 HTML コメント内の記述では充足しない", code == 1, f"code={code}")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _build_fixture(root)
        _write(
            root,
            f"{_SKILL_DIR}/code-review/SKILL.md",
            "# code-review\n<!--\nかつての手順:\n" + _OK_LINE + "\n-->\n本文には無い\n",
        )
        code, _, err = _run_main(root)
        check("複数行 HTML コメント内の記述では充足しない", code == 1, f"code={code}")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _build_fixture(root)
        _write(
            root,
            f"{_SKILL_DIR}/code-review/SKILL.md",
            "# code-review\n<!-- 閉じ忘れコメント\n" + _OK_LINE + "\n",
        )
        code, _, err = _run_main(root)
        check("未閉鎖 HTML コメント以降も充足に使えない", code == 1, f"code={code}")

    # T-4: OR 判定でグループ内の全ファイルが欠けると違反（AND↔OR 反転の検知も兼ねる）
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _build_fixture(root)
        _write(root, f"{_SKILL_DIR}/retrospective/reference.md", "# reference\n（再掲なし）\n")
        code, _, err = _run_main(root)
        check("グループ内の全ファイルが欠けると exit 1", code == 1, f"code={code}")

    # T-5: 明示リストのファイルが存在しない場合も違反（M-2・不在を充足にしない）
    for missing in ("discussion-review", "pr-review-watcher", "self-reviewer"):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _build_fixture(root)
            (root / _SKILL_DIR / missing / "SKILL.md").unlink()
            code, _, err = _run_main(root)
            check(f"明示リストのファイル不在は違反（{missing}）", code == 1, f"code={code}")
            check(f"違反グループ名が出る（{missing}）", missing in err, err)

    # T-6: 非 UTF-8 は判定不能（M-3・黙って PASS にしない）
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _build_fixture(root)
        (root / _SKILL_DIR / "code-review" / "SKILL.md").write_bytes(b"\xff\xfe\x00binary")
        code, _, err = _run_main(root)
        check("明示リストの非 UTF-8 は exit 2（判定不能）", code == 2, f"code={code} err={err}")

    # T-6b【回帰・#821】明示リスト外のファイルが非 UTF-8 でも判定不能（check_coverage 経路）
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _build_fixture(root)
        (root / _SKILL_DIR / "other-skill").mkdir(parents=True, exist_ok=True)
        (root / _SKILL_DIR / "other-skill" / "SKILL.md").write_bytes(b"\xff\xfe\x00binary")
        code, _, err = _run_main(root)
        check("明示リスト外の非 UTF-8 も exit 2（check_coverage 経路）", code == 2, f"code={code} err={err}")

    # T-7: 展開指示の出現形バリアント（#474 ②・見出し / コードスパン / 箇条書き）
    for label, variant in (
        ("見出し内", "## 🔴 並行安全プリアンブル（委譲プロンプトへ実テキストで貼る）"),
        ("コードスパン内", "`並行安全プリアンブル` の中身を `実テキスト` のまま展開する"),
        ("箇条書き内", "- 委譲前に **並行安全プリアンブル** を **実テキスト** で展開する"),
    ):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _build_fixture(root, marker_text=variant)
            code, _, err = _run_main(root)
            check(f"展開指示が{label}にあっても充足", code == 0, f"code={code} err={err}")

    # T-8: 網羅性メタチェック（兆候ありで展開指示なしの非リストスキル → 警告のみ・exit 0）
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _build_fixture(root)
        _write(root, f"{_SKILL_DIR}/new-skill/SKILL.md", "# new\nsubagent_type: general-purpose\n")
        code, _, err = _run_main(root)
        check("兆候ありの新規スキルを警告する", "new-skill" in err and "⚠️" in err, err)
        check("警告だけでは exit 0 のまま（exit code を変えない）", code == 0, f"code={code}")

    # T-8b【WARNING 回帰・#821】兆候語は実在の表現を拾えること（正規表現化の実効性）
    for label, body in (
        ("`Agent` ツール", "本スキルは `Agent` ツールで並列起動する"),
        ("background Agent", "参加者は name 付き background Agent として起動する"),
        ("fan-out", "Sprint Review を fan-out 2 役割で起動する"),
        ("Agent(", "Agent(subagent: general-purpose) を呼ぶ"),
        ("委譲プロンプト", "委譲プロンプトには次を書く"),
    ):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _build_fixture(root)
            _write(root, f"{_SKILL_DIR}/sig-skill/SKILL.md", f"# sig\n{body}\n")
            code, _, err = _run_main(root)
            check(f"兆候『{label}』を拾う", "sig-skill" in err, f"code={code} err={err}")

    # T-8c【WARNING 回帰・#821】サブディレクトリ配下の補助 Markdown も走査対象
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _build_fixture(root)
        _write(root, f"{_SKILL_DIR}/deep-skill/prompts/delegate.md", "# deep\nsubagent_type\n")
        code, _, err = _run_main(root)
        check("サブディレクトリ配下の .md も走査する", "deep-skill/prompts/delegate.md" in err, err)
        check("走査拡大でも exit 0 のまま（警告のみ）", code == 0, f"code={code}")

    # T-9: 兆候が無ければ警告しない（過剰検知の防止）
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _build_fixture(root)
        _write(root, f"{_SKILL_DIR}/plain-skill/SKILL.md", "# plain\n普通の手順書\n")
        code, _, err = _run_main(root)
        check("兆候が無ければ警告しない", "plain-skill" not in err, err)

    # T-10: 抑止コメント（理由あり → 除外 / 理由なし → 除外しない）
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _build_fixture(root)
        _write(
            root,
            f"{_SKILL_DIR}/exempt-skill/SKILL.md",
            "# exempt\n委譲プロンプト\n<!-- delegation-preamble: n/a 読み取り専用で委譲しない -->\n",
        )
        _write(
            root,
            f"{_SKILL_DIR}/bad-exempt/SKILL.md",
            "# bad\n委譲プロンプト\n<!-- delegation-preamble: n/a -->\n",
        )
        code, _, err = _run_main(root)
        check("理由付き抑止コメントは警告を除外する", "exempt-skill" not in err, err)
        check("理由なし抑止コメントは無効（警告が残る）", "bad-exempt" in err, err)

    # T-10b【干渉検証・#725】HTML コメント除去が抑止コメントの検出を壊していないこと
    #   （suppression は原文から、has_marker は除去後から読む契約）
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _build_fixture(root)
        _write(
            root,
            f"{_SKILL_DIR}/exempt2/SKILL.md",
            "# exempt2\nsubagent_type\n"
            "<!-- delegation-preamble: n/a 並行安全プリアンブルの実テキスト展開は親が行う -->\n",
        )
        code, _, err = _run_main(root)
        check("干渉検証: コメント除去後も抑止コメントは有効", "exempt2" not in err, err)
        check("干渉検証: 抑止コメント内の 2 語は充足に使われない（exit 0 のまま）", code == 0, f"code={code}")

    # T-11【干渉検証・#725】明示リスト検査と網羅性メタチェックを同居させても互いを壊さない。
    #   ・警告が主判定の exit code を上書きしない（M-4）
    #   ・主判定が違反でも網羅性の走査が打ち切られない
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _build_fixture(root)
        _write(root, f"{_SKILL_DIR}/code-review/SKILL.md", "# code-review\n（再掲なし）\n")
        _write(root, f"{_SKILL_DIR}/new-skill/SKILL.md", "# new\n並列サブエージェント\n")
        code, _, err = _run_main(root)
        check("干渉検証: 違反と警告が同時に出ても exit 1", code == 1, f"code={code}")
        check("干渉検証: 違反時も網羅性警告が失われない", "new-skill" in err, err)
        check("干渉検証: 警告が違反報告を隠さない", "code-review" in err, err)

    # T-11b【干渉検証・#725】走査拡大が明示リスト判定の結果を変えないこと
    #   （REQUIRED_GROUPS のスキル配下に展開指示なしの補助 .md を置いても、グループは充足のまま）
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _build_fixture(root)
        _write(root, f"{_SKILL_DIR}/code-review/prompts/aux.md", "# aux\n委譲プロンプト\n")
        code, _, err = _run_main(root)
        check("干渉検証: 走査拡大は明示リスト判定を変えない（exit 0）", code == 0, f"code={code} err={err}")
        check("干渉検証: 走査拡大分は警告として現れる", "code-review/prompts/aux.md" in err, err)

    # T-14【NIT・#821】REQUIRED_GROUPS のパス重複は判定不能（exit 2）
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _build_fixture(root)
        global REQUIRED_GROUPS
        original = REQUIRED_GROUPS
        try:
            REQUIRED_GROUPS = original + [
                ("dup-group", (".claude/skills/code-review/SKILL.md",))
            ]
            code, _, err = _run_main(root)
        finally:
            REQUIRED_GROUPS = original
        check("REQUIRED_GROUPS のパス重複は exit 2", code == 2, f"code={code} err={err}")
        check("重複パスが stderr に出る", "code-review/SKILL.md" in err, err)
        code, _, err = _run_main(root)
        check("重複を戻せば exit 0（グローバル復元の確認）", code == 0, f"code={code} err={err}")

    # T-12: --json 出力の構造
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _build_fixture(root)
        _write(root, f"{_SKILL_DIR}/new-skill/SKILL.md", "# new\nsubagent_type\n")
        code, out, _ = _run_main(root, ["--json"])
        try:
            payload = json.loads(out)
            ok = (
                len(payload["groups"]) == len(REQUIRED_GROUPS)
                and payload["unsatisfied"] == []
                and any(w["path"].endswith("new-skill/SKILL.md") for w in payload["warnings"])
            )
        except Exception as exc:  # noqa: BLE001
            ok, payload = False, str(exc)
        check("--json が groups / unsatisfied / warnings を返す", ok, str(payload)[:300])

    # T-13: エントリポイントから実 exit code まで貫通しているか（#474 ③・subprocess 実行）
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _build_fixture(root)
        r_ok = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--root", str(root)],
            capture_output=True, text=True,
        )
        _write(root, f"{_SKILL_DIR}/code-review/SKILL.md", "# code-review\n")
        r_ng = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--root", str(root)],
            capture_output=True, text=True,
        )
        (root / _SKILL_DIR / "code-review" / "SKILL.md").write_bytes(b"\xff\xfe")
        r_un = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--root", str(root)],
            capture_output=True, text=True,
        )
        check("実プロセスの exit code: PASS=0", r_ok.returncode == 0, r_ok.stderr)
        check("実プロセスの exit code: 違反=1", r_ng.returncode == 1, r_ng.stderr)
        check("実プロセスの exit code: 判定不能=2", r_un.returncode == 2, r_un.stderr)

    print(f"\n{'✅ self-test PASS' if not failures else f'❌ self-test FAIL: {failures} 件'}")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="機械可読 JSON で出力")
    parser.add_argument("--root", default=None, help="検査対象のルート（既定: リポジトリルート）")
    parser.add_argument(
        "--self-test", action="store_true", help="フィクスチャに対する自己テストを実行する"
    )
    args = parser.parse_args(argv)

    # 定数の健全性を最初に確かめる（重複パスは判定対象の取り違えを生む・M-10）
    problem = validate_required_groups()
    if problem:
        print(f"⚠️ 判定不能: {problem}", file=sys.stderr)
        return 2

    if args.self_test:
        return run_self_test()

    root = Path(args.root).resolve() if args.root else repo_root()
    required_paths = {rel for _, paths in REQUIRED_GROUPS for rel in paths}
    try:
        groups = check_required(root)
        warnings = check_coverage(root, required_paths)
    except UndecidableError as exc:
        print(f"⚠️ 判定不能: {exc}", file=sys.stderr)
        return 2

    unsatisfied = [g["group"] for g in groups if not g["satisfied"]]
    if args.json:
        print(
            json.dumps(
                {"marker": REFERENCE_MARKER, "marker_words": list(MARKER_WORDS),
                 "groups": groups, "unsatisfied": unsatisfied, "warnings": warnings},
                ensure_ascii=False, indent=2,
            )
        )
        return 1 if unsatisfied else 0
    return render_text(groups, warnings)


if __name__ == "__main__":
    sys.exit(main())
