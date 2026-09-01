#!/usr/bin/env python3
"""check_markdown_table_columns.py - GFM テーブルの列数不整合／終端パイプ後ろの取りこぼしを検出する

背景（Issue #395 / PR #390）:
  GFM テーブルの行末パイプ `|` より後ろに追記を書いてしまい、GitHub が黙って
  落とした事故があった。GFM はヘッダの列数を超えるセルを描画しないため、
  追記した内容が画面上に一切出ないままコミットされる。

検出する違反は 2 種別:
  - column_count     : ヘッダが定める列数とセル数が食い違う
  - trailing_content : 終端パイプの後ろに内容があり、GitHub が黙って落とす

使い方:
  python3 tools/check_markdown_table_columns.py <file.md> [<file2.md> ...]
  python3 tools/check_markdown_table_columns.py --changed
  python3 tools/check_markdown_table_columns.py --changed --under docs/
  python3 tools/check_markdown_table_columns.py --under docs/
  python3 tools/check_markdown_table_columns.py --self-test

終了コード: 0=違反なし / 1=違反あり（self-test 失敗も 1） / 2=ツール異常（誤用）
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import NamedTuple

import git_diff_utils

EXCLUDED_DIRS = {".git", "node_modules", ".next", "__pycache__", ".venv", "dist", "build"}

KIND_COLUMN_COUNT = "column_count"
KIND_TRAILING_CONTENT = "trailing_content"


class TableIssue(NamedTuple):
    """テーブル行の違反 1 件"""
    file: Path
    line_number: int
    kind: str          # KIND_COLUMN_COUNT | KIND_TRAILING_CONTENT
    row_type: str      # "header" | "separator" | "data"
    expected_cols: int
    actual_cols: int
    dropped: str       # trailing_content のとき GitHub が落とす内容
    content: str       # 行そのもの


def split_cells(line: str) -> tuple[list[str], bool] | None:
    """GFM テーブル行をセルへ分割する。

    戻り値: (cells, had_trailing_pipe)。テーブル行でなければ None。

    セル区切りとして数えないもの:
      - エスケープされたパイプ `\\|`
      - インラインコード（`...`）の内側のパイプ
    """
    s = line.strip()
    if not s.startswith("|"):
        return None

    # インラインコードを退避（内側のパイプを区切りとして数えないため）
    code_blocks: list[str] = []

    def _stash(m: re.Match) -> str:
        code_blocks.append(m.group(0))
        return f"\x00C{len(code_blocks) - 1}\x00"

    protected = re.sub(r"`[^`]*`", _stash, s)

    # エスケープされたパイプを退避（区切りとして数えないため）
    protected = protected.replace(r"\|", "\x00E\x00")

    body = protected[1:]  # 先頭のパイプを外す
    had_trailing_pipe = body.endswith("|")
    if had_trailing_pipe:
        body = body[:-1]

    def _restore(text: str) -> str:
        for idx, code in enumerate(code_blocks):
            text = text.replace(f"\x00C{idx}\x00", code)
        return text.replace("\x00E\x00", r"\|")

    cells = [_restore(c).strip() for c in body.split("|")]
    return cells, had_trailing_pipe


def is_separator_row(line: str) -> bool:
    """区切り行（| --- | :---: | ---: |）かどうか。終端パイプは任意（GFM 準拠）"""
    parsed = split_cells(line)
    if parsed is None:
        return False
    cells, _ = parsed
    if not cells:
        return False
    return all(re.match(r"^:?-+:?$", c) for c in cells)


def is_in_code_fence(line_idx: int, lines: list[str]) -> bool:
    """その行がコードフェンス（``` / ~~~）の内側か"""
    count = sum(1 for i in range(line_idx) if re.match(r"^\s*(```|~~~)", lines[i]))
    return count % 2 == 1


def _row_issue(
    path: Path, lineno: int, row_type: str, cells: list[str], had_pipe: bool, expected: int, raw: str
) -> TableIssue | None:
    """1 行分を判定して違反を返す（違反なしなら None）"""
    actual = len(cells)
    if actual == expected:
        return None
    # 終端パイプが無く、かつヘッダの列数を超える → GitHub が末尾を黙って落とす
    if not had_pipe and actual > expected:
        return TableIssue(
            path, lineno, KIND_TRAILING_CONTENT, row_type, expected, actual,
            " | ".join(cells[expected:]), raw.rstrip(),
        )
    return TableIssue(path, lineno, KIND_COLUMN_COUNT, row_type, expected, actual, "", raw.rstrip())


def check_file(path: Path) -> list[TableIssue]:
    """ファイル内の GFM テーブルを検査する"""
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    except Exception as e:  # noqa: BLE001 - 読めないファイルは黙って落とさず通知する
        print(f"⚠️  {path}: 読み込み失敗: {e}", file=sys.stderr)
        return []

    issues: list[TableIssue] = []
    i = 0
    while i < len(lines):
        if is_in_code_fence(i, lines):
            i += 1
            continue

        header = split_cells(lines[i])
        if header is None or i + 1 >= len(lines) or not is_separator_row(lines[i + 1]):
            i += 1
            continue

        header_cells, header_had_pipe = header
        sep_cells, _ = split_cells(lines[i + 1])  # is_separator_row を通っているので None にならない

        # ヘッダ自身の終端パイプ後ろに内容があるケースは、区切り行を列数の拠り所にする
        expected = len(header_cells)
        if not header_had_pipe and len(header_cells) > len(sep_cells):
            expected = len(sep_cells)
            issues.append(
                TableIssue(
                    path, i + 1, KIND_TRAILING_CONTENT, "header", expected, len(header_cells),
                    " | ".join(header_cells[expected:]), lines[i].rstrip(),
                )
            )

        if len(sep_cells) != expected:
            issues.append(
                TableIssue(path, i + 2, KIND_COLUMN_COUNT, "separator", expected, len(sep_cells), "",
                           lines[i + 1].rstrip())
            )

        j = i + 2
        while j < len(lines) and not is_in_code_fence(j, lines):
            if not lines[j].strip():
                break
            parsed = split_cells(lines[j])
            if parsed is None:
                break
            cells, had_pipe = parsed
            issue = _row_issue(path, j + 1, "data", cells, had_pipe, expected, lines[j])
            if issue is not None:
                issues.append(issue)
            j += 1

        i = j

    return issues


def walk_md_under(unders: list[str]) -> list[str]:
    """--under 配下を再帰的に走査して .md を列挙する（生成物・第三者著作物は除外）"""
    out: list[str] = []
    for under in unders:
        base = Path(under)
        if not base.is_dir():
            continue
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
            out.extend(os.path.join(root, f) for f in files if f.endswith(".md"))
    return sorted(set(out))


def _truncate(text: str, limit: int = 100) -> str:
    """長すぎる行は省略記号付きで切り詰める（切れていることが読み手に分かる形にする）"""
    text = text.strip()
    return text if len(text) <= limit else text[:limit] + " …"


def format_issue(issue: TableIssue) -> str:
    """違反 1 件を人が読める形にする"""
    head = f"  {issue.file}:{issue.line_number} ({issue.row_type})"
    if issue.kind == KIND_TRAILING_CONTENT:
        body = (
            "終端パイプの後ろに内容があります（GitHub は黙って落とします）: "
            f"{_truncate(issue.dropped, 80)}"
        )
    else:
        body = f"列数が合いません: 期待 {issue.expected_cols} 列 / 実際 {issue.actual_cols} 列"
    return f"{head} {body}\n    {_truncate(issue.content)}"


def run_self_test() -> bool:
    """self-test: 期待する検出結果と実際の検出結果を突き合わせる"""
    Case = tuple[str, list[tuple[int, str, str, int, int]], str]
    tests: list[Case] = [
        (
            "| H1 | H2 | H3 |\n| --- | --- | --- |\n| A | B | C |\n| D | E | F |\n",
            [],
            "正常なテーブル",
        ),
        (
            "| A | B |\n| --- | --- | --- |\n| 1 | 2 | 3 |\n",
            [(2, KIND_COLUMN_COUNT, "separator", 2, 3), (3, KIND_COLUMN_COUNT, "data", 2, 3)],
            "列数ズレ（区切り行・データ行）",
        ),
        (
            "| A | B | C |\n| --- | --- | --- |\n| 1 | 2 |\n",
            [(3, KIND_COLUMN_COUNT, "data", 3, 2)],
            "データ行の列数不足",
        ),
        (
            "| C | O |\n| --- | --- |\n| a \\| b | works |\n",
            [],
            "エスケープされたパイプは区切りに数えない",
        ),
        (
            "| C | O |\n| --- | --- |\n| a \\| b | c | d |\n",
            [(3, KIND_COLUMN_COUNT, "data", 2, 3)],
            "エスケープ混在行の列数（保護が外れると 4 列になる）",
        ),
        (
            "| C | O |\n| --- | --- |\n| `a | b` | works |\n",
            [],
            "インラインコード内のパイプは区切りに数えない",
        ),
        (
            "| L | C | R |\n| :--- | :---: | ---: |\n| A | B | C |\n",
            [],
            "アライメント付き区切り行（:--- / :---: / ---:）",
        ),
        (
            "| L | R |\n| :--- | ---: |\n| 1 | 2 | 3 |\n",
            [(3, KIND_COLUMN_COUNT, "data", 2, 3)],
            "アライメント付き区切り行を認識して違反を出す",
        ),
        (
            "| Code | Desc |\n| --- | --- |\n| a \\| b \\| c | output |\n",
            [],
            "複数のエスケープパイプ",
        ),
        (
            "| 項目 | 内容 |\n| --- | --- |\n| 設定方法 | 環境変数 | <!-- refcheck:ignore -->\n",
            [(3, KIND_TRAILING_CONTENT, "data", 2, 3)],
            "PR #390: 終端パイプの後ろに内容（データ行）",
        ),
        (
            "| A | B | <!-- x -->\n| --- | --- |\n| 1 | 2 |\n",
            [(1, KIND_TRAILING_CONTENT, "header", 2, 3)],
            "終端パイプの後ろに内容（ヘッダ行）",
        ),
        (
            "| A | B |\n| --- | --- |\n| 1 | 2\n",
            [],
            "終端パイプ無しの正当な GFM テーブルは誤検知しない",
        ),
        (
            "```\n| A | B |\n| --- | --- | --- |\n| 1 | 2 | 3 |\n```\n",
            [],
            "コードフェンス内のテーブルは検査しない",
        ),
    ]

    passed = True
    tmp = Path("/tmp/check_markdown_table_columns_selftest.md")
    for content, expected, desc in tests:
        tmp.write_text(content, encoding="utf-8")
        actual = [
            (i.line_number, i.kind, i.row_type, i.expected_cols, i.actual_cols)
            for i in check_file(tmp)
        ]
        if actual == expected:
            print(f"✅ {desc}")
        else:
            print(f"❌ {desc}")
            print(f"   期待: {expected}")
            print(f"   実際: {actual}")
            passed = False
    if tmp.exists():
        tmp.unlink()

    # 落ちる内容がメッセージに出ることも検証する（表示の退行を防ぐ）
    tmp.write_text("| A | B |\n| --- | --- |\n| 1 | 2 | <!-- dropped -->\n", encoding="utf-8")
    issues = check_file(tmp)
    if len(issues) == 1 and "<!-- dropped -->" in format_issue(issues[0]) \
            and "終端パイプの後ろに内容があります" in format_issue(issues[0]):
        print("✅ 終端パイプ違反のメッセージに落ちる内容が出る")
    else:
        print("❌ 終端パイプ違反のメッセージに落ちる内容が出る")
        print(f"   実際: {[format_issue(i) for i in issues]}")
        passed = False
    tmp.unlink()

    return passed


def main() -> int:
    parser = argparse.ArgumentParser(description="GFM テーブルの列数・終端パイプ検査")
    parser.add_argument("files", nargs="*", help="検査対象の .md")
    parser.add_argument("--changed", action="store_true", help="git 変更ファイルのみ対象")
    parser.add_argument("--under", action="append", dest="under_dirs", help="配下に限定（複数可）")
    parser.add_argument("--self-test", action="store_true", help="セルフテスト")
    args = parser.parse_args()

    if args.self_test:
        return 0 if run_self_test() else 1

    if args.changed:
        changed = git_diff_utils.collect_changed_files(require_existing=False)
        target_files = [f for f in changed if f.endswith(".md") and Path(f).is_file()]
    elif args.files:
        target_files = list(args.files)
    elif args.under_dirs:
        target_files = walk_md_under(args.under_dirs)
    else:
        print("エラー: ファイル指定 / --changed / --under のいずれかが必要です", file=sys.stderr)
        return 2

    # --changed / 明示指定と --under の併用は絞り込みとして働く
    if args.under_dirs and (args.changed or args.files):
        bases = [Path(d).resolve() for d in args.under_dirs]
        kept = []
        for f in target_files:
            rf = Path(f).resolve()
            if any(rf == b or b in rf.parents for b in bases):
                kept.append(f)
        target_files = kept

    issues: list[TableIssue] = []
    for f in target_files:
        issues.extend(check_file(Path(f)))

    if issues:
        n_trailing = sum(1 for i in issues if i.kind == KIND_TRAILING_CONTENT)
        n_column = len(issues) - n_trailing
        print(
            f"❌ Markdown テーブル違反: {len(issues)} 件"
            f"（終端パイプ後ろの取りこぼし {n_trailing} 件 / 列数不一致 {n_column} 件）"
        )
        for issue in issues:
            print(format_issue(issue))
        return 1

    if target_files:
        print(f"✅ Markdown テーブル: OK（{len(target_files)} ファイル）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
