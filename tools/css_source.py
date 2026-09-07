#!/usr/bin/env python3
"""css_source.py — CSS ソースの字句除去（コメント / 文字列リテラル）を集約する共通モジュール。

## なぜ必要か

CSS コメント（`/* ... */`）を落とす正規表現 `/\\*.*?\\*/`（`re.DOTALL`）が、次の 2 ファイルに
**独立に実装** されていた:

  - `tools/check_contrast.py` の `strip_css_comments`（除去部分を空文字へ落とす）
  - `tools/check_css_variable_cycles.py` の `strip_css_comments`（除去部分の改行だけ残す）

`tools/check_duplicate_source_patterns.py --strict` が未許可の重複として検出した。両者は
**改行を保つかどうか** だけが違い、字句解析としては同じ処理である。`ts_source.py`（JS/TS）・
`py_source.py`（Python）・`md_fence.py`（Markdown）と同じく「同じ字句解析を各ツールが独自実装
した結果、同じ欠陥が複数箇所に生まれる」形（#612）を避けるため、ここへ 1 本化する。

## 文字列リテラルを認識する（fail-open の除去）

コメントだけを正規表現で落とすと、**文字列リテラルの中の `/*`** をコメント開始と誤認する。

    :root { --quote: "/*"; --self: var(--self); --end: "*/"; }

素朴な実装ではこの 1 行から `"/*"` 〜 `"*/` までが丸ごと消え、**実在する `--self` の自己参照が
検査から消滅して PASS になる**（fail-open）。逆に `.x { content: "/* x */ --d: var(--d);" }`
では文字列の中身が実宣言として読まれ、誤検知（fail-closed 側の誤り）になる。

そこで本モジュールは **文字列リテラルとコメントを 1 本の正規表現で同時に走査** し、先に現れた
方をトークンとして確定させる（レキサと同じ順序）。文字列の中の `/*` はコメント開始にならず、
コメントの中の `"` / `'` は文字列開始にならない。

CSS の文字列は **エスケープされていない改行を含めない**（含むと bad-string-token になり、その
行で文字列が打ち切られる）。本モジュールもそれに合わせ、生の改行を跨ぐ引用符は「文字列」と
みなさない。これにより、閉じ忘れた引用符（`content: "unterminated`）が以降のコメントや宣言を
飲み込む事故が起きない。閉じられていないコメント（`a /* unterminated`）も従来どおり除去しない
（不正な CSS を黙って書き換えない）。

## 呼び出し側が選ぶ 2 つの軸

    preserve_lines=False : 除去部分を丸ごと落とす（行番号を報告しないツール向け）
    preserve_lines=True  : 除去部分に含まれていた改行だけ残す（行番号つきで違反を報告する
                           ツール向け。落としてしまうと以降の行番号が全てずれる）

    blank_strings=False  : 文字列リテラルはそのまま残す（既定。中身を読みたいツール向け）
    blank_strings=True   : 文字列リテラルの **中身だけ** を空にし、引用符は残す
                           （`--x: var(--x)` のような字面を「宣言」として走査するツール向け。
                            文字列の中身を実宣言として誤読するのを防ぐ）

コメントの中身を「実宣言」として読み取ってしまう事故（例: `/* 旧値は --sidebar-ring: ... だった */`
がコメント外の実値を後勝ちで上書きする）を防ぐため、CSS を正規表現で走査するツールは
**パースの入口でここを通す**。

## 現在ここを通しているツール（実態・宣言だけ先に置かない）

- `tools/check_contrast.py`（`preserve_lines=False` / `blank_strings=False`）
- `tools/check_css_variable_cycles.py`（`preserve_lines=True` / `blank_strings=True`）
- `tools/check_ui_dimensions.py`（`css_var_raw`・`preserve_lines=True` / `blank_strings=False`）
  — Issue #1084 で接続。行番号つきで報告する経路があるため改行を保つ。
- `tools/check_prose_tokens.py`（`PROSE_DECL_RE` の走査対象・`preserve_lines=False` /
  `blank_strings=False`）— Issue #1084 で接続。`check_contrast.py` と同じ扱い（行番号は
  目安表示のみで厳密一致を要求しない）。

## 対応しない構文

CSS のコメントは `/* ... */` のみ（`//` 行コメントは CSS の仕様に無い。Sass/Less のような
プリプロセッサ構文は本リポジトリで使っていないため対象外）。引用符を伴わない `url(...)` の
中身（`url(http://example.com/*x*/)`）はトークンとして扱わない（本リポジトリの実データに
存在せず、`url()` の完全な字句規則を持ち込む価値が無いため）。必要になったら本モジュールを
拡張して呼び出し側へ同時に反映する（それがこの集約の目的）。
"""

from __future__ import annotations

import sys

import re

# 唯一の CSS 字句パターン（重複実装を作らないため、他ファイルで再定義しない）。
# 文字列リテラル（二重引用符 / 単一引用符）とコメントを同時に走査し、先に現れた方を採る。
# 文字列の中身は「エスケープ列（`\` + 任意の 1 文字。CRLF は 1 つとして消費）」または
# 「引用符・バックスラッシュ・生の改行以外の 1 文字」の繰り返し（CSS の string-token 準拠）。
_TOKEN_RE = re.compile(
    r'"(?:\\(?:\r\n|.)|[^"\\\r\n])*"'
    r"|'(?:\\(?:\r\n|.)|[^'\\\r\n])*'"
    r"|/\*.*?\*/",
    re.DOTALL,
)


def strip_css_comments(
    text: str, *, preserve_lines: bool = False, blank_strings: bool = False
) -> str:
    """CSS コメント（`/* ... */`）を除去する（文字列リテラルの中は保護する）。

    `preserve_lines=True` のとき、除去したコメントに含まれていた改行の数だけ `\\n` を残し、
    以降の行番号がずれないようにする（行番号つきで違反を報告するツール向け）。

    `blank_strings=True` のとき、文字列リテラルの **中身** を空にして引用符だけ残す
    （`content: "--x: var(--x)"` を宣言として誤読しないため）。
    """

    def _sub(m: re.Match[str]) -> str:
        s = m.group(0)
        if not s.startswith("/*"):
            # 文字列リテラル: 既定はそのまま残す（中の `/*` をコメント開始にしないことが目的）。
            if not blank_strings:
                return s
            inner = "\n" * s.count("\n") if preserve_lines else ""
            return s[0] + inner + s[-1]
        return "\n" * s.count("\n") if preserve_lines else ""

    return _TOKEN_RE.sub(_sub, text)


def _run_self_test() -> int:
    failures: list[str] = []

    def check(label: str, got: object, want: object) -> None:
        if got != want:
            failures.append(f"{label}: want={want!r}, got={got!r}")

    # 1. 単純なコメント除去（両モード共通）
    check("1 単一行", strip_css_comments("a /* c */ b"), "a  b")
    check(
        "1-b 単一行/改行保持",
        strip_css_comments("a /* c */ b", preserve_lines=True),
        "a  b",
    )

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
    check(
        "7 単独アスタリスク", strip_css_comments("* { margin: 0 }"), "* { margin: 0 }"
    )

    # --- 8. 文字列リテラルの中の `/*` をコメント開始と誤認しない（fail-open の本丸）
    #        素朴な実装ではここで `--self` の自己参照が strip 後に消え、検査が PASS に化ける。
    s8 = ':root { --quote: "/*"; --self: var(--self); --end: "*/"; }'
    check("8 文字列内 /* を保護", strip_css_comments(s8), s8)
    check("8-b 同上/改行保持", strip_css_comments(s8, preserve_lines=True), s8)
    check("8-c 自己参照が残る", "var(--self)" in strip_css_comments(s8), True)
    # 単一引用符でも同じ
    s8d = ":root { --q: '/*'; --s: var(--s); --e: '*/'; }"
    check("8-d 単一引用符でも保護", strip_css_comments(s8d), s8d)

    # --- 9. コメントの中の引用符は文字列開始にならない（逆向きの誤認）
    check("9 コメント内アポストロフィ", strip_css_comments("a /* it's */ b"), "a  b")
    check("9-b コメント内二重引用符", strip_css_comments('a /* say "hi" */ b'), "a  b")
    # コメント内の引用符が「開いたまま」でも、後続の実宣言を巻き込まない
    check(
        "9-c コメント内の未閉鎖引用符",
        strip_css_comments("/* it's */ --x: var(--x);"),
        " --x: var(--x);",
    )

    # --- 10. エスケープされた引用符は文字列を終わらせない
    check(
        "10 エスケープ引用符",
        strip_css_comments('--a: "x\\"/* y */"; --b: 1;'),
        '--a: "x\\"/* y */"; --b: 1;',
    )

    # --- 11. 生の改行を跨ぐ引用符は「文字列」ではない（CSS の bad-string-token）
    #         閉じ忘れた引用符が以降のコメントを飲み込まないことを固定する。
    check(
        "11 未閉鎖文字列",
        strip_css_comments('content: "unterminated\n/* c */ --x: 1;'),
        'content: "unterminated\n --x: 1;',
    )
    # 11-b/11-c: 後続に **別の引用符がある** ときが本番。生の改行で打ち切らないと、閉じ忘れた
    # 引用符が「次の引用符」までを 1 個の文字列として飲み込み、間のコメント除去や実宣言が
    # 丸ごと失われる（fail-open）。
    check(
        "11-b 未閉鎖文字列がコメントを飲み込まない",
        strip_css_comments('a: "unterminated\n/* c */ b: "x";'),
        'a: "unterminated\n b: "x";',
    )
    check(
        "11-c 未閉鎖文字列が実宣言を飲み込まない",
        "var(--x)"
        in strip_css_comments(
            'a: "unterminated\n--x: var(--x);\nb: "ok";', blank_strings=True
        ),
        True,
    )

    # --- 12. blank_strings: 文字列の中身だけを空にする（引用符は残す）
    check(
        "12 中身を空に",
        strip_css_comments(
            '.x { content: "/* x */ --d: var(--d);" }', blank_strings=True
        ),
        '.x { content: "" }',
    )
    check(
        "12-b 宣言として読めなくなる",
        "var(--d)"
        in strip_css_comments(
            '.x { content: "/* x */ --d: var(--d);" }', blank_strings=True
        ),
        False,
    )
    # 文字列の外側の実宣言は残る
    check(
        "12-c 外側の宣言は残る",
        strip_css_comments('--a: "/*"; --b: var(--b);', blank_strings=True),
        '--a: ""; --b: var(--b);',
    )
    # blank_strings でも行番号がずれない（`\` + 改行の行継続を含む文字列）
    s12 = '--a: "x\\\ny";\n--b: var(--b);'
    check(
        "12-d 行継続を含む文字列/改行保持",
        strip_css_comments(s12, preserve_lines=True).count("\n"),
        s12.count("\n"),
    )

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
