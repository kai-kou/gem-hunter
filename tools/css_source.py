#!/usr/bin/env python3
"""css_source.py — CSS ソースのコメント除去を集約する共通モジュール（Issue #1012 / #1031 の PR 内で新設）。

## なぜ必要か

CSS コメント（`/* ... */`）を落とす正規表現 `/\\*.*?\\*/`（`re.DOTALL`）が、次の 2 ファイルに
**独立に実装** されていた:

  - `tools/check_contrast.py` の `strip_css_comments`（除去部分を空文字へ落とす）
  - `tools/check_css_variable_cycles.py` の `strip_css_comments`（除去部分の改行だけ残す）

`tools/check_duplicate_source_patterns.py --strict` が未許可の重複として検出した。両者は
**改行を保つかどうか** だけが違い、字句解析としては同じ処理である。`ts_source.py`（JS/TS）・
`py_source.py`（Python）・`md_fence.py`（Markdown）と同じく「同じ字句解析を各ツールが独自実装
した結果、同じ欠陥が複数箇所に生まれる」形（#612）を避けるため、ここへ 1 本化する。

## 改行を保つかどうかは呼び出し側が選ぶ（`preserve_lines` 引数）

どちらが正しいかはツールの性質による。

    preserve_lines=False : 除去部分を丸ごと落とす（行番号を報告しないツール向け）
    preserve_lines=True  : 除去部分に含まれていた改行だけ残す（行番号つきで違反を報告する
                           ツール向け。落としてしまうと以降の行番号が全てずれる）

コメントの中身を「実宣言」として読み取ってしまう事故（例: `/* 旧値は --sidebar-ring: ... だった */`
がコメント外の実値を後勝ちで上書きする）を防ぐため、CSS を正規表現で走査するツールは
**パースの入口で必ずここを通す**。

## 対応しない構文

CSS のコメントは `/* ... */` のみ（`//` 行コメントは CSS の仕様に無い。Sass/Less のような
プリプロセッサ構文は本リポジトリで使っていないため対象外）。文字列リテラル内に現れる
`/*`（例: `content: "/*"`）は稀かつ本リポジトリの実データに存在しないため考慮しない。
必要になったら本モジュールを拡張して両ツールへ同時に反映する（それがこの集約の目的）。
"""

from __future__ import annotations

import sys

import re

# 唯一の CSS コメントパターン（重複実装を作らないため、他ファイルで再定義しない）。
_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


def strip_css_comments(text: str, *, preserve_lines: bool = False) -> str:
    """CSS コメント（`/* ... */`）を除去する。

    `preserve_lines=True` のとき、除去したコメントに含まれていた改行の数だけ `\\n` を残し、
    以降の行番号がずれないようにする（行番号つきで違反を報告するツール向け）。
    """
    if preserve_lines:
        return _COMMENT_RE.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    return _COMMENT_RE.sub("", text)


def _run_self_test() -> int:
    failures: list[str] = []

    def check(label: str, got: object, want: object) -> None:
        if got != want:
            failures.append(f"{label}: want={want!r}, got={got!r}")

    # 1. 単純なコメント除去（両モード共通）
    check("1 単一行", strip_css_comments("a /* c */ b"), "a  b")
    check("1-b 単一行/改行保持", strip_css_comments("a /* c */ b", preserve_lines=True), "a  b")

    # 2. 複数行コメント: preserve_lines の有無で行数が変わる
    src = "--a: 1;\n/* 行を\nまたぐ\nコメント */\n--b: 2;"
    check("2 改行を落とす", strip_css_comments(src).count("\n"), 2)
    check("2-b 改行を保つ", strip_css_comments(src, preserve_lines=True).count("\n"), 4)

    # 2-c 行番号がずれないこと（本モジュールが preserve_lines を持つ理由そのもの）
    stripped = strip_css_comments(src, preserve_lines=True)
    idx = stripped.find("--b")
    check("2-c --b の行番号", stripped.count("\n", 0, idx) + 1, 5)

    # 3. コメント内の宣言が消える（後勝ち上書き事故の防止）
    css = "--x: red;\n/* 旧値は --x: blue; だった */\n"
    check("3 コメント内宣言の除去", "blue" in strip_css_comments(css), False)
    check(
        "3-b コメント内宣言の除去/改行保持",
        "blue" in strip_css_comments(css, preserve_lines=True),
        False,
    )

    # 4. 複数コメント（非貪欲マッチ: 2 つのコメントの「間」を巻き込まない）
    check("4 非貪欲", strip_css_comments("/*a*/KEEP/*b*/"), "KEEP")

    # 5. 閉じられていないコメントは除去されない（不正な CSS を黙って書き換えない）
    check("5 未閉鎖", strip_css_comments("a /* unterminated"), "a /* unterminated")

    # 6. コメントが無い入力は素通し（境界の外側）
    check("6 コメントなし", strip_css_comments("--a: 1;"), "--a: 1;")
    check("6-b 空文字", strip_css_comments(""), "")

    # 7. `/*` に見えるが別物（除算やアスタリスクの単独出現）を壊さない
    check("7 単独アスタリスク", strip_css_comments("* { margin: 0 }"), "* { margin: 0 }")

    if failures:
        print("❌ css_source --self-test FAILED")
        print("\n".join(failures))
        return 1
    print("✅ css_source --self-test PASSED")
    return 0


def main() -> int:
    if "--self-test" in sys.argv[1:]:
        return _run_self_test()
    print(
        "css_source.py は tools/check_*.py から import して使う共通ライブラリです。"
        " 単体では --self-test のみ受け付けます。"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
