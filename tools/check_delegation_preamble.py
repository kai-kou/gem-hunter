#!/usr/bin/env python3
"""check_delegation_preamble.py — 委譲テンプレートを持つスキルに「並行安全プリアンブル」の再掲があるかを検査する（Issue #816）

## なぜ必要か

サブエージェントは `CLAUDE.md` も `docs/rules/` も自動では読まない。並行実行中の破壊的 git 操作の
禁止（#93 / #768）は **委譲プロンプトに実テキストで再掲したときだけ** 相手に届く。正本は
`docs/rules/agent-team-summary.md` の節「🔴 並行安全プリアンブル（委譲プロンプトへ貼る実テキスト・SSOT・#816）」で、
各スキルはこの節を Read して実テキスト展開する運用に統一されている。

この運用は「新しく委譲テンプレートを持つスキルを追加したとき、再掲を忘れる」という静かな
失敗モードを持つ。忘れても何もエラーにならず、サブエージェントが `git checkout <branch>` を
実行して親の作業ツリーを壊すまで誰も気づかない。本ツールはその再発を機械検知する。

## 何をどう検査するか（2 段構成）

### 1. 明示リスト検査（fail-closed・主判定・exit code に反映）

「委譲テンプレートを持つファイル」の明示リスト（`REQUIRED_GROUPS`）を定数として持ち、
各グループが参照文字列 `並行安全プリアンブル` を含むことを検査する。含まなければ **違反**。

グループは「いずれか 1 つを満たせばよい」単位である（OR 判定）。`retrospective` のように
委譲テンプレートを `reference.md` 側に持つ構造のスキルは、`SKILL.md` と `reference.md` の
どちらか一方に参照があれば充足とする。

### 2. 網羅性メタチェック（ヒューリスティック・警告のみ・exit code を変えない）

`.claude/skills/*/SKILL.md` と `.claude/skills/*/reference.md` を走査し、委譲テンプレートを
持つ兆候語（`DELEGATION_SIGNALS`）があるのに、明示リストにも参照文字列にも現れないファイルを
**警告** として報告する（新規スキル追加時の検知）。ここは誤検知しうるため警告に留め、
終了コードは変えない（fail-open にするのは 1 段目が fail-closed で守っているため）。

正当な例外は、そのファイルの任意の行に次の抑止コメントを書くと警告から除外できる:

    <!-- delegation-preamble: n/a {なぜ再掲が不要かの理由} -->

理由が空のマーカーは無効として扱い、除外しない（人が判断した形跡を残させるのが目的。
`check_selftest_wiring.py` の `selftest-wiring-ok` と同じ思想）。

## 「見逃し（miss）」に至りうる経路（実装前に列挙し、それぞれ塞いだ）

- M-1: 参照文字列がコードスパン・見出し・箇条書きの内側にある → 行構造を見ず素の部分文字列検索にした
- M-2: 明示リストの要素がリポジトリから消えている → ファイル不在は「充足」ではなく **違反** に倒す
- M-3: ファイルが非 UTF-8 / 読み取り不能 → 黙って「参照なし」にせず **exit 2（判定不能）** に倒す
- M-4: 網羅性メタチェックの警告が主判定の exit code を上書きする → 警告は exit code に一切関与させない
- M-5: 抑止コメントが理由なしで乱用される → 理由が空のマーカーは無効

## 使い方

    python3 tools/check_delegation_preamble.py            # 人間向けテキスト（既定）
    python3 tools/check_delegation_preamble.py --json     # 機械可読 JSON
    python3 tools/check_delegation_preamble.py --root DIR # 検査対象のルートを差し替える（テスト用）
    python3 tools/check_delegation_preamble.py --self-test

## 終了コード

- 0: PASS（明示リストの全グループが参照文字列を含む。警告があっても 0）
- 1: 違反あり（参照文字列を欠くグループがある。対象パスを stderr に列挙）
- 2: 判定不能（ファイル読み取り不能・非 UTF-8 等。fail-closed。黙って PASS にしない）
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# 正本（docs/rules/agent-team-summary.md）の節見出しに含まれる語。
# 各スキルの委譲テンプレートは、この語で正本を参照するか実テキストを展開している。
REFERENCE_MARKER = "並行安全プリアンブル"

# 明示リスト（fail-closed・主判定）。
# 各要素は (グループ名, そのグループに属するパス群) で、**いずれか 1 つ** が
# REFERENCE_MARKER を含めば充足とする（OR 判定）。
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
]

# 網羅性メタチェックの兆候語（委譲テンプレートを持つ疑いがあることを示す）。
DELEGATION_SIGNALS: tuple[str, ...] = (
    "subagent_type",
    "並列サブエージェント",
    "委譲プロンプト",
    "Agent(",
    "Agent ツール",
)

# 抑止コメント: <!-- delegation-preamble: n/a 理由 -->（理由が空のものは無効）
SUPPRESSION_RE = re.compile(
    r"<!--\s*delegation-preamble:\s*n/a\s+(?P<reason>\S[^>]*?)\s*-->"
)


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def read_text(path: Path) -> str:
    """UTF-8 で読む。読めなければ UndecidableError にして fail-closed にする。"""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise UndecidableError(f"{path}: 非 UTF-8 として読み取れません（{exc}）") from exc
    except OSError as exc:
        raise UndecidableError(f"{path}: 読み取りに失敗しました（{exc}）") from exc


class UndecidableError(Exception):
    """判定不能（exit 2）。黙って PASS にしないためのシグナル。"""


def has_marker(text: str) -> bool:
    """参照文字列の有無。行構造（見出し・コードスパン・箇条書き）を問わない素の部分文字列判定。"""
    return REFERENCE_MARKER in text


def suppression_reason(text: str) -> str | None:
    m = SUPPRESSION_RE.search(text)
    if not m:
        return None
    reason = m.group("reason").strip()
    return reason or None  # 理由が空のマーカーは無効（除外しない）


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
    skills = root / ".claude" / "skills"
    if not skills.is_dir():
        return []
    found: list[Path] = []
    for name in ("SKILL.md", "reference.md"):
        found.extend(sorted(skills.glob(f"*/{name}")))
    return sorted(found)


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
        signals = [s for s in DELEGATION_SIGNALS if s in text]
        if signals:
            warnings.append({"path": rel, "signals": signals})
    return warnings


def render_text(groups: list[dict], warnings: list[dict]) -> int:
    unsatisfied = [g for g in groups if not g["satisfied"]]
    for w in warnings:
        print(
            f"⚠️ 委譲テンプレートの兆候があるのに「{REFERENCE_MARKER}」の再掲がありません"
            f"（ヒューリスティック・要確認）: {w['path']} — 兆候: {', '.join(w['signals'])}",
            file=sys.stderr,
        )
    if unsatisfied:
        print(
            f"❌ 委譲テンプレートに「{REFERENCE_MARKER}」の再掲がありません（Issue #816）:",
            file=sys.stderr,
        )
        for g in unsatisfied:
            paths = " / ".join(m["path"] for m in g["members"])
            print(f"  - {g['group']}: {paths}", file=sys.stderr)
        print(
            "  → 正本: docs/rules/agent-team-summary.md の「🔴 並行安全プリアンブル」節を"
            "Read して実テキストを展開すること",
            file=sys.stderr,
        )
        return 1
    print(
        f"✅ 明示リスト {len(groups)} グループすべてに「{REFERENCE_MARKER}」の再掲があります"
        + (f"（警告 {len(warnings)} 件）" if warnings else "")
    )
    return 0


# --------------------------------------------------------------------------
# self-test（フィクスチャを一時ディレクトリへ作り、本番の入口 main() を経由させる・#686）
# --------------------------------------------------------------------------

_SKILL_DIR = ".claude/skills"


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _build_fixture(root: Path, marker_text: str = REFERENCE_MARKER) -> None:
    """明示リストの全グループを充足させた最小フィクスチャを作る。"""
    _write(root, f"{_SKILL_DIR}/retrospective/SKILL.md", "# retrospective\n")
    _write(
        root,
        f"{_SKILL_DIR}/retrospective/reference.md",
        f"# reference\n{marker_text} を貼る\n",
    )
    for name in ("discussion-review", "waiting-user-handler", "self-improvement-loop", "code-review"):
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


def run_self_test() -> int:
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

    # T-2: 1 グループが参照文字列を欠くと exit 1（主判定・fail-closed）
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _build_fixture(root)
        _write(root, f"{_SKILL_DIR}/code-review/SKILL.md", "# code-review\n（再掲なし）\n")
        code, out, err = _run_main(root)
        check("参照文字列を欠くグループがあると exit 1", code == 1, f"code={code}")
        check("違反グループ名が stderr に出る", "code-review" in err, err)

    # T-3: グループは OR 判定（SKILL.md に無く reference.md にあれば充足）
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _build_fixture(root)
        code, _, err = _run_main(root)
        check("グループは OR 判定（片方に再掲があれば充足）", code == 0, f"code={code} err={err}")

    # T-3b: OR 判定は「先頭のファイルだけが持つ」場合も充足する
    #       （AND への反転・「最後のファイルで上書き」型の実装ミスを検知する）
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _build_fixture(root)
        _write(root, f"{_SKILL_DIR}/retrospective/SKILL.md", f"# retrospective\n{REFERENCE_MARKER}\n")
        _write(root, f"{_SKILL_DIR}/retrospective/reference.md", "# reference\n（再掲なし）\n")
        code, _, err = _run_main(root)
        check("グループ先頭のファイルだけが持つ場合も充足", code == 0, f"code={code} err={err}")

    # T-3c: 参照文字列はリテラル一致である（定数を短縮・部分化する変異を検知する）
    #       期待値をテスト側にリテラルで固定し、実装定数と二重管理にすることで
    #       「定数から 1 語削っても self-test が緑」という無音化を防ぐ。
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _build_fixture(root, marker_text="並行安全プリアンブル")  # リテラル
        code, _, err = _run_main(root)
        check("リテラル『並行安全プリアンブル』で充足する", code == 0, f"code={code} err={err}")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _build_fixture(root, marker_text="安全プリアンブル")  # 惜しい別語（先頭欠落）
        code, _, err = _run_main(root)
        check("惜しい別語『安全プリアンブル』では充足しない", code == 1, f"code={code}")

    # T-4: OR 判定でグループ内の全ファイルが欠けると違反（AND↔OR 反転の検知も兼ねる）
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _build_fixture(root)
        _write(root, f"{_SKILL_DIR}/retrospective/reference.md", "# reference\n（再掲なし）\n")
        code, _, err = _run_main(root)
        check("グループ内の全ファイルが欠けると exit 1", code == 1, f"code={code}")

    # T-5: 明示リストのファイルが存在しない場合も違反（M-2・不在を充足にしない）
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _build_fixture(root)
        (root / _SKILL_DIR / "discussion-review" / "SKILL.md").unlink()
        code, _, err = _run_main(root)
        check("明示リストのファイル不在は違反（exit 1）", code == 1, f"code={code}")

    # T-6: 非 UTF-8 は判定不能（M-3・黙って PASS にしない）
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _build_fixture(root)
        (root / _SKILL_DIR / "code-review" / "SKILL.md").write_bytes(b"\xff\xfe\x00binary")
        code, _, err = _run_main(root)
        check("非 UTF-8 は exit 2（判定不能）", code == 2, f"code={code} err={err}")

    # T-7: 参照文字列の出現形バリアント（#474 ②・見出し / コードスパン / 箇条書き）
    for label, variant in (
        ("見出し内", f"## 🔴 {REFERENCE_MARKER}（委譲プロンプトへ貼る実テキスト）"),
        ("コードスパン内", f"`{REFERENCE_MARKER}`"),
        ("箇条書き内", f"- 委譲前に **{REFERENCE_MARKER}** を展開する"),
    ):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _build_fixture(root, marker_text=variant)
            code, _, err = _run_main(root)
            check(f"参照文字列が{label}にあっても充足", code == 0, f"code={code} err={err}")

    # T-8: 網羅性メタチェック（兆候語ありで再掲なしの非リストスキル → 警告のみ・exit 0）
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _build_fixture(root)
        _write(root, f"{_SKILL_DIR}/new-skill/SKILL.md", "# new\nsubagent_type: general-purpose\n")
        code, _, err = _run_main(root)
        check("兆候語ありの新規スキルを警告する", "new-skill" in err and "⚠️" in err, err)
        check("警告だけでは exit 0 のまま（exit code を変えない）", code == 0, f"code={code}")

    # T-9: 兆候語が無ければ警告しない（過剰検知の防止）
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _build_fixture(root)
        _write(root, f"{_SKILL_DIR}/plain-skill/SKILL.md", "# plain\n普通の手順書\n")
        code, _, err = _run_main(root)
        check("兆候語が無ければ警告しない", "plain-skill" not in err, err)

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
                {"marker": REFERENCE_MARKER, "groups": groups,
                 "unsatisfied": unsatisfied, "warnings": warnings},
                ensure_ascii=False, indent=2,
            )
        )
        return 1 if unsatisfied else 0
    return render_text(groups, warnings)


if __name__ == "__main__":
    sys.exit(main())
