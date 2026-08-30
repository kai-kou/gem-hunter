#!/usr/bin/env python3
"""check_agent_diff_claim.py — サブエージェントの完了報告と実 diff を突合し虚偽報告・報告漏れを検知する（#99）

## なぜ必要か

委譲したサブエージェントが「3 ファイルを修正し検証済み」と詳細な報告を返したが、ディスク上の
ファイルは 1 つも変更されていなかった事例が発生した（SP-2 レトロスペクティブ・PR #96）。親が
`git status` / `git diff` で突合して初めて発覚しており、この突合は完全に人手だった。本ツールは
「サブエージェントの完了報告に書かれた変更ファイル一覧」と「実際の作業ツリーの差分」を機械的に
突合する。

## 検査方法（読み取り専用）

実 diff は以下 3 コマンドを `subprocess` で実行し **読み取りのみ** で取得する（書き込み系 git
コマンドは一切呼ばない）:

- `git status --short`（追跡外ファイルも含む変更全体）
- `git diff --stat`（未ステージの変更）
- `git diff --cached --stat`（ステージ済みの変更）

3 つの出力からファイルパスを抽出した和集合を「実 diff ファイル集合」とする。

## 入力形式

`--stdin` でサブエージェントの完了報告テキストをそのまま標準入力に流し込む
（オーケストレーターが Bash から 1 コマンドで叩けることを最優先にした唯一の形式）。
テキスト中からパスらしき文字列（`git status --short` 形式の行・バッククォート囲みのパス・
スラッシュと拡張子を含むトークン）を正規表現で抽出する（ヒューリスティックのため 100% ではない）。

    cat agent_report.txt | python3 tools/check_agent_diff_claim.py --stdin

## 判定

- 「報告にあるが実 diff に無い」（`missing_from_diff`）: 虚偽報告・未反映の疑い → 警告
- 「実 diff にあるが報告に無い」（`missing_from_report`）: 報告漏れ。親が見落としやすい方向
  のため **より重い警告** として扱う
- どちらか一方でも非空なら exit 1

## 使い方

    python3 tools/check_agent_diff_claim.py --stdin < agent_report.txt
    python3 tools/check_agent_diff_claim.py --stdin --json < agent_report.txt
    python3 tools/check_agent_diff_claim.py --self-test
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# パスらしきトークン: 英数字/アンダースコアで始まり、スラッシュ・ドット・ハイフン・角括弧を含み、
# 最後に "." + 拡張子で終わる文字列。
# 角括弧（`[` `]`）は Next.js App Router の動的セグメント（`app/[locale]/page.tsx` 等）で
# 実際にこのリポジトリのパスに使われているため必須（Issue #712）。`git ls-files` で確認した限り
# 本リポジトリのパスに現れる記号は `[` `]` `.` `-` `_` `/` のみで、`(` `)` `@` `+` `~` 等は
# 使われていない（含めると日本語文中の記号を誤って拾うリスクが増すため見送る）。
_PATH_TOKEN_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_./\[\]-]*\.[A-Za-z0-9_]+")
_URL_RE = re.compile(r"https?://\S+")  # ドメイン名がパストークンとして誤抽出されるのを防ぐため事前に除去する


def extract_claimed_paths(text: str) -> set[str]:
    """完了報告の自由文からパスらしきトークンを抽出する（ヒューリスティック）。

    URL 全体を先に除去してから走査するため「https://example.com/path.html」のような
    ドメイン名を誤ってパス扱いしない。バージョン番号（"2.1.198" や "v2.1.198"）は、
    拡張子相当の末尾セグメントが数字のみ（`ext.isdigit()`）になるため同じチェックで除外される
    （専用の正規表現は不要 — フルマッチする文字列は定義上必ず末尾が数字のみになる）。
    """
    text = _URL_RE.sub(" ", text)
    candidates: set[str] = set()
    for tok in _PATH_TOKEN_RE.findall(text):
        tok = tok.strip("`'\"()[],;:")
        tok = tok.lstrip("./")
        if not tok:
            continue
        ext = tok.rsplit(".", 1)[-1]
        if ext.isdigit():
            continue
        candidates.add(tok)
    return candidates


def run_git(args: list[str], cwd: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, check=True,
        )
        return proc.stdout
    except FileNotFoundError as e:
        raise RuntimeError("git コマンドが見つかりません") from e
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"git {' '.join(args)} が失敗: {e.stderr.strip()}") from e


def parse_status_short(output: str) -> set[str]:
    """`git status --short` 出力からファイルパスを抽出する（リネームは新パスを採用）。"""
    files: set[str] = set()
    for line in output.splitlines():
        if not line.strip():
            continue
        rest = line[3:] if len(line) > 3 else line.strip()
        if " -> " in rest:
            rest = rest.split(" -> ", 1)[1]
        rest = rest.strip().strip('"')
        if rest:
            files.add(rest)
    return files


def parse_diff_stat(output: str) -> set[str]:
    """`git diff --stat` 出力からファイルパスを抽出する（末尾のサマリー行は "|" が無く自動除外）。"""
    files: set[str] = set()
    for line in output.splitlines():
        if "|" not in line:
            continue
        path = line.split("|", 1)[0].strip()
        if path:
            files.add(path)
    return files


def get_real_diff_files(root: Path) -> dict:
    status_out = run_git(["status", "--short"], root)
    diff_out = run_git(["diff", "--stat"], root)
    cached_out = run_git(["diff", "--cached", "--stat"], root)
    files: set[str] = set()
    files |= parse_status_short(status_out)
    files |= parse_diff_stat(diff_out)
    files |= parse_diff_stat(cached_out)
    return {
        "files": files,
        "raw": {"status": status_out, "diff_stat": diff_out, "diff_cached_stat": cached_out},
    }


def compare(claimed: set[str], real: set[str]) -> dict:
    missing_from_diff = sorted(claimed - real)
    missing_from_report = sorted(real - claimed)
    return {
        "claimed": sorted(claimed),
        "real": sorted(real),
        "missing_from_diff": missing_from_diff,
        "missing_from_report": missing_from_report,
        "mismatch": bool(missing_from_diff or missing_from_report),
    }


def print_report(result: dict) -> None:
    print(f"報告ファイル: {len(result['claimed'])} 件 / 実 diff ファイル: {len(result['real'])} 件")
    if result["missing_from_diff"]:
        print("⚠️  報告にあるが実 diff に無い（虚偽報告・未反映の疑い）:")
        for f in result["missing_from_diff"]:
            print(f"    - {f}")
    if result["missing_from_report"]:
        print("❌ 実 diff にあるが報告に無い（報告漏れ・親が見落としやすい方向・より重い）:")
        for f in result["missing_from_report"]:
            print(f"    - {f}")
    if not result["mismatch"]:
        print("✅ 報告と実 diff は一致")


# ──────────────────────────────────────────────
# セルフテスト
# ──────────────────────────────────────────────


def run_self_test() -> int:
    passed, failed = 0, 0

    def check(label: str, cond: bool, detail: str = "") -> None:
        nonlocal passed, failed
        if cond:
            passed += 1
        else:
            failed += 1
            print(f"FAIL: {label}" + (f" — {detail}" if detail else ""))

    # parse_status_short: 追跡外・変更・リネームを正しく拾う
    status_sample = " M tools/foo.py\n?? tools/new_file.py\nR  tools/old.py -> tools/renamed.py\n"
    got = parse_status_short(status_sample)
    check(
        "parse_status_short 通常/追跡外/リネーム",
        got == {"tools/foo.py", "tools/new_file.py", "tools/renamed.py"},
        str(got),
    )

    # parse_diff_stat: サマリー行（"|" 無し）を含めない
    stat_sample = (
        " tools/foo.py      | 10 +++++-----\n"
        " path/to/bar.py    | 3 +--\n"
        " 2 files changed, 8 insertions(+), 5 deletions(-)\n"
    )
    got2 = parse_diff_stat(stat_sample)
    check("parse_diff_stat サマリー行除外", got2 == {"tools/foo.py", "path/to/bar.py"}, str(got2))

    # extract_claimed_paths: 完了報告の自由文からパスを抽出
    report_text = (
        "## 変更ファイル一覧\n"
        " M tools/check_agent_scope_overlap.py\n"
        "?? tools/check_agent_diff_claim.py\n"
        "本文中で `docs/rules/agent-team-summary.md` にも触れています。\n"
        "v2.1.198 で検証済み。詳細は https://example.com/path.html を参照。\n"
    )
    got3 = extract_claimed_paths(report_text)
    check(
        "extract_claimed_paths 抽出（バージョン/URL除外）",
        got3
        == {
            "tools/check_agent_scope_overlap.py",
            "tools/check_agent_diff_claim.py",
            "docs/rules/agent-team-summary.md",
        },
        str(got3),
    )

    # extract_claimed_paths: 角括弧を含む Next.js App Router 動的セグメントパスを
    # 切り詰めずに、かつ 2 件を同じ文字列に潰さず別々に抽出できること（Issue #712）
    bracket_report_text = (
        "役3（#549）新規作成: app/[locale]/page.test.tsx\n"
        "役3（#549）新規作成: app/[locale]/repos/[owner]/[repo]/page.test.tsx\n"
    )
    got_bracket = extract_claimed_paths(bracket_report_text)
    check(
        "extract_claimed_paths 角括弧パスを切り詰めず別々に抽出（#712）",
        got_bracket
        == {
            "app/[locale]/page.test.tsx",
            "app/[locale]/repos/[owner]/[repo]/page.test.tsx",
        },
        str(got_bracket),
    )

    # compare: 一致
    r_match = compare({"a.py", "b.py"}, {"a.py", "b.py"})
    check("compare 一致で mismatch=False", r_match["mismatch"] is False, str(r_match))

    # compare: 双方向の不一致を検出
    r_mismatch = compare({"a.py", "b.py"}, {"a.py", "c.py"})
    check(
        "compare 双方向不一致を検出",
        r_mismatch["missing_from_diff"] == ["b.py"]
        and r_mismatch["missing_from_report"] == ["c.py"]
        and r_mismatch["mismatch"] is True,
        str(r_mismatch),
    )

    print(f"\nセルフテスト: {passed} passed, {failed} failed / {passed + failed} cases")
    return 0 if failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stdin", action="store_true", help="標準入力から完了報告テキストを読みパスらしき文字列を抽出する")
    parser.add_argument("--json", action="store_true", help="結果を JSON で出力する")
    # selftest-wiring-ok: サブエージェント委譲直後に親が手動で叩く運用ツールで、PR 前の品質ゲートではない
    parser.add_argument("--self-test", action="store_true", help="セルフテストを実行")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    if not args.stdin:
        parser.print_help()
        return 2

    claimed: set[str] = extract_claimed_paths(sys.stdin.read())

    try:
        real = get_real_diff_files(REPO_ROOT)
    except RuntimeError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 2

    result = compare(claimed, real["files"])

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_report(result)

    return 1 if result["mismatch"] else 0


if __name__ == "__main__":
    sys.exit(main())
