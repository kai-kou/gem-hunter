#!/usr/bin/env python3
"""check_markdown_table_columns.py - GFM テーブルの列数不整合／終端パイプ後ろの取りこぼしを検出する

背景（Issue #395 / PR #390）:
  GFM テーブルの行末パイプ `|` より後ろに追記を書いてしまい、GitHub が黙って
  落とした事故があった。GFM はヘッダの列数を超えるセルを描画しないため、
  追記した内容が画面上に一切出ないままコミットされる。

検出する違反は 2 種別:
  - column_count     : ヘッダが定める列数とセル数が食い違う
  - trailing_content : 終端パイプの後ろに内容があり、GitHub が黙って落とす

PR #772 Layer 1 セルフレビューで潰した fail-open（いずれも実測で再現済み）:
  1. コードフェンス判定の偶奇カウント: ``` の中に `~~~` が 1 行あると以降のファイル全体が
     無検査になり、```` の中の ``` は誤検知していた。加えて行ごとに先頭から再走査する
     O(n^2)（実測 20,000 行で 100 秒）。→ `md_fence.fence_flags()`（CommonMark 準拠・1 パス）
     を `check_file` の先頭で 1 回だけ計算して添字参照する。
  2. 区切り行の終端パイプ後ろに内容があるとテーブル認識自体が落ちて全行無検査だった。
     → 区切り行は「先頭から連続する区切りセル」で判定し、余剰セルは区切り行の
     trailing_content として報告する（認識を落とさない）。
  3. HTML コメントのみの終端内容は誤検知だった（本リポジトリは `<!-- refcheck:ignore -->`
     等を機械可読マーカーとして意図的に使う）。HTML コメントは描画されないので
     「黙って落とされる」実害が無い。→ 終端の余剰セルが全て HTML コメントなら除外する。
  4. インラインコード保護が 1 連バッククォート限定で ``` ``a | b`` ``` を守れなかった。
     → `md_fence.mask_inline_code()`（連数可変・長さ保存）へ置き換え。
  5. 読み込み失敗が exit 0（fail-open）だった。→ 解析不能を集計して非ゼロ終了にする
     （`check_datetime_tz.py` と同じ形・#445）。stderr の先頭記号で区別する:
       ❌ = 違反あり / ⚠️ = 解析不能（違反の有無を判定できていない）
  6. `--under` の 0 件が黙って PASS（fail-open）だった。除外集合も `check_cjk_markdown.py`
     の正本から乖離していた。→ 対象解決を `check_cjk_markdown.resolve_targets()` へ委譲し、
     0 件時の警告 + exit 1・除外ディレクトリ・第三者著作物パス（#233）を正本と共有する。

既知の未対応（意図的に検査しない範囲・#772）:
  - 先頭パイプを省略した GFM テーブル（`A | B` / `--- | ---` / `1 | 2`）は検査しない。
    本文中の `a | b`（シェルのパイプライン・TypeScript のユニオン型など）と機械的に区別できず
    誤検知面積が大きい一方、本リポジトリの .md には該当形が 1 件も存在しないため
    （`^ *:?-{3,}:? *\|` のリポジトリ全文検索が 0 件）、検出価値より誤検知コストが上回る。
  - 4 スペースインデントのコードブロック内のテーブルは除外しない。リスト項目内の
    4 スペースインデントは「コードブロックではなく継続行」であり、両者を段落文脈なしに
    区別すると本物のテーブルを取りこぼす（fail-open 化する）ため、あえて検査対象に残す。
  いずれも self-test に「既知の未対応」ケースとして現挙動を固定してある。

使い方:
  python3 tools/check_markdown_table_columns.py <file.md> [<file2.md> ...]
  python3 tools/check_markdown_table_columns.py --changed
  python3 tools/check_markdown_table_columns.py --changed --under docs/
  python3 tools/check_markdown_table_columns.py --under docs/
  python3 tools/check_markdown_table_columns.py --self-test

終了コード: 0=違反なし / 1=違反あり・解析不能あり・--under 0 件（self-test 失敗も 1） / 2=ツール異常（誤用）
"""
from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path
from typing import NamedTuple

# 対象ファイル解決（--changed / --under / 除外集合）の正本は check_cjk_markdown.py 側にある。
# #772 指摘 6: 除外集合（EXCLUDED_DIRS 12 件 / EXCLUDED_PATHS）と 0 件時の fail-closed 挙動を
# 二重定義すると必ず乖離するため、再実装せず import して再利用する（同ツールは編集しない）。
import check_cjk_markdown as cjk
from md_fence import fence_flags, mask_inline_code

KIND_COLUMN_COUNT = "column_count"
KIND_TRAILING_CONTENT = "trailing_content"

# 区切りセル（--- / :--- / :---: / ---:）
SEPARATOR_CELL_RE = re.compile(r"^:?-+:?$")

# HTML コメント（描画されない＝終端に残っても「黙って落とされる」実害が無い・#772 指摘 3）
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


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
      - インラインコード（`...` / ``...`` / ```...```）の内側のパイプ

    インラインコードの退避は `md_fence.mask_inline_code()`（長さ保存）に任せ、区切り位置だけを
    退避後の文字列から求めて **元の文字列** を切り出す。これで復元処理そのものが不要になる
    （旧実装はプレースホルダを復元しており、1 連バッククォート限定の正規表現だった・#772 指摘 4）。
    """
    s = line.strip()
    if not s.startswith("|"):
        # 先頭パイプ省略形は既知の未対応（モジュール docstring 参照）
        return None

    masked = mask_inline_code(s)
    delims = [
        i for i, ch in enumerate(masked)
        if ch == "|" and (i == 0 or masked[i - 1] != "\\")
    ]
    if not delims:
        return None

    had_trailing_pipe = delims[-1] == len(s) - 1
    cells = [s[a + 1:b].strip() for a, b in zip(delims, delims[1:])]
    if not had_trailing_pipe:
        cells.append(s[delims[-1] + 1:].strip())
    if not cells:
        return None
    return cells, had_trailing_pipe


def separator_run_length(cells: list[str]) -> int:
    """先頭から連続する区切りセルの数を返す（#772 指摘 2）"""
    n = 0
    for c in cells:
        if not SEPARATOR_CELL_RE.match(c):
            break
        n += 1
    return n


def parse_separator_row(line: str) -> tuple[int, list[str], bool] | None:
    """区切り行なら (先頭連続区切りセル数, 全セル, 終端パイプの有無) を返す。

    #772 指摘 2: 旧実装は「全セルが区切りセル」を要求したため、
    `| --- | --- | <!-- x -->` のように終端パイプの後ろに内容がある区切り行で
    テーブル認識そのものが落ち、そのテーブル全体が無検査（fail-open）になっていた。
    先頭からの連続で判定し、余剰セルは呼び出し側が trailing_content として扱う。
    """
    parsed = split_cells(line)
    if parsed is None:
        return None
    cells, had_pipe = parsed
    run = separator_run_length(cells)
    if run == 0:
        return None
    return run, cells, had_pipe


def is_separator_row(line: str) -> bool:
    """区切り行（| --- | :---: | ---: |）かどうか。終端パイプは任意（GFM 準拠）"""
    return parse_separator_row(line) is not None


def is_html_comment_only(text: str) -> bool:
    """文字列が HTML コメントだけで構成されるか（前後・間の空白は許容）"""
    t = text.strip()
    if not t:
        return False
    return not HTML_COMMENT_RE.sub("", t).strip()


def all_html_comment_cells(cells: list[str]) -> bool:
    """終端に残った余剰セルが全て HTML コメントか（#772 指摘 3 の除外条件）"""
    return bool(cells) and all(is_html_comment_only(c) for c in cells)


def _trailing_issue(
    path: Path, lineno: int, row_type: str, cells: list[str], expected: int, raw: str
) -> TableIssue | None:
    """終端パイプ後ろの取りこぼしを 1 件組み立てる（HTML コメントのみなら None）"""
    extra = cells[expected:]
    if all_html_comment_cells(extra):
        # HTML コメントは描画されない。落とされても読み手に見える情報が失われないので
        # 違反にしない（機械可読マーカー `<!-- refcheck:ignore -->` 等の正当な用法・#772 指摘 3）
        return None
    return TableIssue(
        path, lineno, KIND_TRAILING_CONTENT, row_type, expected, len(cells),
        " | ".join(extra), raw.rstrip(),
    )


def _row_issue(
    path: Path, lineno: int, row_type: str, cells: list[str], had_pipe: bool, expected: int, raw: str
) -> TableIssue | None:
    """1 行分を判定して違反を返す（違反なしなら None）"""
    actual = len(cells)
    if actual == expected:
        return None
    # 終端パイプが無く、かつヘッダの列数を超える → GitHub が末尾を黙って落とす
    if not had_pipe and actual > expected:
        return _trailing_issue(path, lineno, row_type, cells, expected, raw)
    return TableIssue(path, lineno, KIND_COLUMN_COUNT, row_type, expected, actual, "", raw.rstrip())


def check_file(path: Path, *, errors: list[str] | None = None) -> list[TableIssue]:
    """ファイル内の GFM テーブルを検査する。

    errors: 解析不能（読み込み失敗）を呼び出し側へ伝えるための出力リスト。
            #772 指摘 5: 解析不能を「違反なし」として exit 0 にすると偽陰性になるため、
            main() は 1 件でもあれば非ゼロ終了にする（`check_datetime_tz.py` と同じ形・#445）。
    """
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    except Exception as e:  # noqa: BLE001 - 読めないファイルは黙って落とさず通知する
        print(f"⚠️  {path}: 解析不能のため検査できませんでした（{e}）", file=sys.stderr)
        if errors is not None:
            errors.append(str(path))
        return []

    # コードフェンス内フラグを 1 パスで前計算する（旧実装の行ごと再走査 O(n^2) を解消・#772 指摘 1）
    flags = fence_flags(lines)

    issues: list[TableIssue] = []
    i = 0
    while i < len(lines):
        if flags[i]:
            i += 1
            continue

        header = split_cells(lines[i])
        if header is None or i + 1 >= len(lines) or flags[i + 1]:
            i += 1
            continue
        sep = parse_separator_row(lines[i + 1])
        if sep is None:
            i += 1
            continue

        header_cells, header_had_pipe = header
        sep_run, sep_cells, sep_had_pipe = sep

        # ヘッダ自身の終端パイプ後ろに内容があるケースは、区切り行を列数の拠り所にする
        expected = len(header_cells)
        if not header_had_pipe and len(header_cells) > sep_run:
            expected = sep_run
            issue = _trailing_issue(path, i + 1, "header", header_cells, expected, lines[i])
            if issue is not None:
                issues.append(issue)

        sep_issue = _row_issue(
            path, i + 2, "separator", sep_cells, sep_had_pipe, expected, lines[i + 1]
        )
        if sep_issue is not None:
            issues.append(sep_issue)

        j = i + 2
        while j < len(lines) and not flags[j]:
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


def _run_cli(argv: list[str]) -> int:
    """self-test から main() を終了コードごと検証するためのヘルパー"""
    saved = sys.argv
    sys.argv = ["check_markdown_table_columns.py", *argv]
    try:
        return main()
    finally:
        sys.argv = saved


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
        # --- #772 指摘 4: 連数可変のインラインコード ---
        (
            "| C | O |\n| --- | --- |\n| ``a | b`` | works |\n",
            [],
            "#772-4: 2 連バッククォート内のパイプも区切りに数えない",
        ),
        (
            "| C | O |\n| --- | --- |\n| ```a | b | c``` | works |\n",
            [],
            "#772-4: 3 連バッククォート内のパイプも区切りに数えない",
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
            "| 項目 | 内容 |\n| --- | --- |\n| 設定方法 | 環境変数 | 補足テキスト\n",
            [(3, KIND_TRAILING_CONTENT, "data", 2, 3)],
            "PR #390: 終端パイプの後ろに内容（データ行）",
        ),
        (
            "| A | B | 補足テキスト\n| --- | --- |\n| 1 | 2 |\n",
            [(1, KIND_TRAILING_CONTENT, "header", 2, 3)],
            "終端パイプの後ろに内容（ヘッダ行）",
        ),
        # --- #772 指摘 3: HTML コメントのみの終端内容は誤検知しない ---
        (
            "| 項目 | 内容 |\n| --- | --- |\n| 設定方法 | 環境変数 | <!-- refcheck:ignore -->\n",
            [],
            "#772-3: 終端が HTML コメントのみなら検出しない（データ行）",
        ),
        (
            "| A | B | <!-- lanecheck:x -->\n| --- | --- |\n| 1 | 2 |\n",
            [],
            "#772-3: 終端が HTML コメントのみなら検出しない（ヘッダ行）",
        ),
        (
            "| A | B |\n| --- | --- |\n| 1 | 2 | <!-- x --> 見える文字\n",
            [(3, KIND_TRAILING_CONTENT, "data", 2, 3)],
            "#772-3: HTML コメント以外の内容が混ざれば検出する",
        ),
        # --- #772 指摘 2: 区切り行の終端パイプ後ろでテーブル認識を落とさない ---
        (
            "| A | B | 補足\n| --- | --- | 補足\n| 1 | 2 | 3 | 4 |\n",
            [
                (1, KIND_TRAILING_CONTENT, "header", 2, 3),
                (2, KIND_TRAILING_CONTENT, "separator", 2, 3),
                (3, KIND_COLUMN_COUNT, "data", 2, 4),
            ],
            "#772-2: 区切り行の終端パイプ後ろに内容があってもテーブルを検査する",
        ),
        (
            "| A | B | <!-- x -->\n| --- | --- | <!-- x -->\n| 1 | 2 | 3 | 4 |\n",
            [(3, KIND_COLUMN_COUNT, "data", 2, 4)],
            "#772-2/3: 区切り行の終端が HTML コメントでもデータ行の列数は検査する",
        ),
        (
            "| A | B |\n| --- | --- | --- |\n| 1 | 2 |\n",
            [(2, KIND_COLUMN_COUNT, "separator", 2, 3)],
            "#772-2: 終端パイプ付きで区切りセルが多いのは列数不一致（trailing ではない）",
        ),
        # --- #772 指摘 1: コードフェンス判定 ---
        (
            "```\n| A | B |\n| --- | --- | --- |\n| 1 | 2 | 3 |\n```\n",
            [],
            "コードフェンス内のテーブルは検査しない",
        ),
        (
            "```text\n~~~\n```\n| A | B |\n| --- | --- | --- |\n| 1 | 2 | 3 |\n",
            [(5, KIND_COLUMN_COUNT, "separator", 2, 3), (6, KIND_COLUMN_COUNT, "data", 2, 3)],
            "#772-1: ``` の中の ~~~ で以降が無検査にならない（偶奇判定の fail-open）",
        ),
        (
            "````\n```\n| A | B |\n| --- | --- | --- |\n```\n````\n",
            [],
            "#772-1: ```` の中の ``` を閉じ扱いして誤検知しない（fail-closed）",
        ),
        (
            "~~~\n| A | B |\n| --- | --- | --- |\n~~~\n",
            [],
            "#772-1: ~~~ フェンス内のテーブルも検査しない",
        ),
        # --- 既知の未対応（現挙動の固定・モジュール docstring 参照）---
        (
            "A | B\n--- | ---\n1 | 2 | 3\n",
            [],
            "既知の未対応: 先頭パイプ省略形のテーブルは検査しない",
        ),
        (
            "text\n\n    | A | B |\n    | --- | --- | --- |\n    | 1 | 2 | 3 |\n",
            [(4, KIND_COLUMN_COUNT, "separator", 2, 3), (5, KIND_COLUMN_COUNT, "data", 2, 3)],
            "既知の未対応: 4 スペースインデントのコードブロックは除外せず検査する",
        ),
    ]

    passed = True
    with tempfile.TemporaryDirectory(prefix="check_md_table_") as td:
        # #772 指摘 8: 固定パス /tmp/... は symlink 攻撃（CWE-377）と並行実行時の相互破壊を招く
        tmpdir = Path(td)
        tmp = tmpdir / "selftest.md"
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

        # 落ちる内容がメッセージに出ることも検証する（表示の退行を防ぐ）
        tmp.write_text("| A | B |\n| --- | --- |\n| 1 | 2 | 落ちる追記\n", encoding="utf-8")
        issues = check_file(tmp)
        if (
            len(issues) == 1
            and "落ちる追記" in format_issue(issues[0])
            and "終端パイプの後ろに内容があります" in format_issue(issues[0])
        ):
            print("✅ 終端パイプ違反のメッセージに落ちる内容が出る")
        else:
            print("❌ 終端パイプ違反のメッセージに落ちる内容が出る")
            print(f"   実際: {[format_issue(i) for i in issues]}")
            passed = False

        # --- #772 指摘 5: 解析不能（読み込み失敗）は「違反なし」にしない ---
        broken = tmpdir / "broken.md"
        broken.write_bytes(b"| A | B |\n| --- | --- |\n| \xff\xfe | 2 |\n")
        errors: list[str] = []
        broken_issues = check_file(broken, errors=errors)
        if broken_issues == [] and len(errors) == 1:
            print("✅ #772-5: 解析不能ファイルを errors へ伝播する")
        else:
            print("❌ #772-5: 解析不能ファイルを errors へ伝播する")
            print(f"   実際: issues={broken_issues} errors={errors}")
            passed = False

        rc = _run_cli([str(broken)])
        if rc == 1:
            print("✅ #772-5: 解析不能ファイルだけでも exit 1（fail-open にしない）")
        else:
            print(f"❌ #772-5: 解析不能ファイルだけでも exit 1（実際の終了コード: {rc}）")
            passed = False

        # --- #772 指摘 6: --under の 0 件を黙って PASS にしない ---
        empty_dir = tmpdir / "empty"
        empty_dir.mkdir()
        rc = _run_cli(["--under", str(empty_dir)])
        if rc == 1:
            print("✅ #772-6: --under 配下に .md が 0 件なら exit 1")
        else:
            print(f"❌ #772-6: --under 配下に .md が 0 件なら exit 1（実際の終了コード: {rc}）")
            passed = False

        rc = _run_cli(["--under", str(tmpdir / "does-not-exist")])
        if rc == 1:
            print("✅ #772-6: 存在しない --under ディレクトリでも exit 1")
        else:
            print(f"❌ #772-6: 存在しない --under ディレクトリでも exit 1（実際の終了コード: {rc}）")
            passed = False

        ok_dir = tmpdir / "ok"
        ok_dir.mkdir()
        (ok_dir / "fine.md").write_text("| A | B |\n| --- | --- |\n| 1 | 2 |\n", encoding="utf-8")
        rc = _run_cli(["--under", str(ok_dir)])
        if rc == 0:
            print("✅ #772-6: --under 配下に正常な .md があれば exit 0")
        else:
            print(f"❌ #772-6: --under 配下に正常な .md があれば exit 0（実際の終了コード: {rc}）")
            passed = False

        # 除外集合が check_cjk_markdown.py（正本）と同一であること（乖離の再発防止・#772 指摘 6）
        if "venv" in cjk.EXCLUDED_DIRS and ".open-next" in cjk.EXCLUDED_DIRS:
            print("✅ #772-6: 除外ディレクトリ集合を check_cjk_markdown.py と共有している")
        else:
            print("❌ #772-6: 除外ディレクトリ集合を check_cjk_markdown.py と共有している")
            passed = False

    return passed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="GFM テーブルの列数・終端パイプ検査",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "既知の未対応（意図的に検査しない範囲・#772）:\n"
            "  - 先頭パイプを省略した GFM テーブル（`A | B` / `--- | ---`）。本文中の\n"
            "    `a | b`（シェルのパイプ・型のユニオン）と区別できず誤検知面積が大きいため。\n"
            "  - 4 スペースインデントのコードブロック内のテーブル。リスト項目の継続行と\n"
            "    区別できず、除外すると本物のテーブルを取りこぼすため検査対象に残している。\n"
            "終了コード: 0=違反なし / 1=違反・解析不能・--under 0 件 / 2=誤用"
        ),
    )
    parser.add_argument("files", nargs="*", help="検査対象の .md")
    parser.add_argument("--changed", action="store_true", help="git 変更ファイルのみ対象")
    parser.add_argument(
        "--under", action="append", dest="under_dirs", default=[],
        metavar="DIR", help="配下に限定（複数可・単独指定なら配下の .md を再帰選択）",
    )
    parser.add_argument("--self-test", action="store_true", help="セルフテスト")
    args = parser.parse_args()

    if args.self_test:
        return 0 if run_self_test() else 1

    # 対象解決は check_cjk_markdown.py（正本）へ委譲する。0 件時の fail-closed（#706 / #711）と
    # 除外集合（生成物ディレクトリ・第三者著作物 #233）をそのまま引き継ぐ（#772 指摘 6）。
    target_files, mode = cjk.resolve_targets(args.files, args.changed, args.under_dirs)

    if not target_files:
        if mode == "none":
            print(
                "エラー: ファイル指定 / --changed / --under のいずれかが必要です",
                file=sys.stderr,
            )
            return 2
        if mode == "under-only":
            print(
                f"⚠️  --under で指定した配下に .md ファイルが 1 件もありません: {args.under_dirs}\n"
                "   → パス指定の誤りがないか確認してください（黙って PASS 扱いにしない）",
                file=sys.stderr,
            )
            return 1
        if mode == "filtered-to-zero":
            print(
                "⚠️  明示ファイル指定 / --changed 由来の対象は存在しましたが、"
                f"--under {args.under_dirs} の絞り込みで 0 件になりました\n"
                "   → 対象と --under のディレクトリが一致しているか確認してください",
                file=sys.stderr,
            )
            return 1
        # mode == "other": --changed で変更 .md が無いのは日常的な正常系
        print("対象ファイルなし（変更された .md が無い・OK）", file=sys.stderr)
        return 0

    issues: list[TableIssue] = []
    errors: list[str] = []
    for f in target_files:
        issues.extend(check_file(Path(f), errors=errors))

    if issues:
        n_trailing = sum(1 for i in issues if i.kind == KIND_TRAILING_CONTENT)
        n_column = len(issues) - n_trailing
        print(
            f"❌ Markdown テーブル違反: {len(issues)} 件"
            f"（終端パイプ後ろの取りこぼし {n_trailing} 件 / 列数不一致 {n_column} 件）"
        )
        for issue in issues:
            print(format_issue(issue))
        print(f"\n❌ Markdown テーブル違反 {len(issues)} 件（{len(target_files)} ファイル走査）",
              file=sys.stderr)

    if errors:
        # 解析不能は「違反なし」ではない。黙って PASS にしない（#445 と同じ形・#772 指摘 5）。
        # stderr の先頭記号で区別する: ❌ = 違反あり / ⚠️ = 解析不能
        print(
            f"\n⚠️  {len(errors)} 件の .md を読み込めず検査不能"
            f"（{len(target_files)} ファイル走査）。解析不能は「違反なし」ではないため PASS にしない。\n"
            "   対象ファイルを修正するか、検査対象から外す運用上の理由を明記すること。",
            file=sys.stderr,
        )

    if issues or errors:
        return 1

    print(f"✅ Markdown テーブル: OK（{len(target_files)} ファイル）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
