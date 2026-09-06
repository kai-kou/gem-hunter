#!/usr/bin/env python3
"""ts_source.py — TypeScript / JSX ソースを正規表現で走査する検査スクリプト群の共通補助処理。

【なぜ必要か・Issue #612】
`tools/check_*.py` の複数の検査スクリプトが、同じ補助処理（コメント除去・波括弧の対応・
JSX タグ終端の検出・関数本文の終端の検出）を **各自で独立に再実装** していた。その結果、
`check_prefetchable_side_effects.py` にだけ `find_tag_end`（JSX タグ終端検出）が実装されて
おり、`check_ui_dimensions.py` にはそれが無いため `onClick={() => f()}` の `=>` をタグ終端と
誤認するバグを **抱えたまま** になっていた。同種の「片方だけ直って、もう片方に同じバグが残る」
事故を防ぐため、本モジュールへ 1 箇所に集約する。

【集約した 4 関数と、元の実装】
  - `strip_comments`            : `check_prefetchable_side_effects.py:77` /
                                   `check_ui_dimensions.py:103` /
                                   `check_rate_limit_wiring.py:311`（3 実装）
  - `find_matching_brace`       : `check_prefetchable_side_effects.py:125` /
                                   `check_ui_dimensions.py:174`（`_find_matching_brace`。2 実装）
  - `find_tag_end`              : `check_prefetchable_side_effects.py:159`（1 実装のみ。
                                   `check_ui_dimensions.py` には存在せず、上記のバグを持っていた）
  - `find_function_body_end`    : `check_rate_limit_wiring.py:427`（`_find_function_body_end`。
                                   1 実装のみ）

【等価性の判定結果（実行で確認済み・詳細は PR / セッション報告を参照）】

  `strip_comments`（3 実装）: **完全には等価でなかった**。
  `check_prefetchable_side_effects.py` と `check_ui_dimensions.py` の実装は **バイト単位で
  同一**（docstring のみ差分）で、文字単位のスキャナがソース全体を 1 本のクォート状態で
  舐める設計。一方 `check_rate_limit_wiring.py` の実装は行単位のスキャナで、対にならない
  アポストロフィ（`<p>Don't worry</p>`）や正規表現リテラル（`/'/g`）に遭遇した行だけ
  「消しすぎる方向」に安全側で倒す設計になっている（同スクリプトの docstring 参照）。
  文字単位版は、対にならないクォートに遭遇すると **ファイル終端まで** クォート状態から
  抜けられなくなり、以降のコメントを一切除去できなくなる（`// await enforce...RateLimit(...)`
  のようなコメントアウトされた呼び出しを「配線済み」と誤認する＝偽陰性）。
  行単位版に差し替えて `check_rate_limit_wiring.py --self-test` を実行したところ、この既知の
  反例（正規表現リテラル直後 / アポストロフィ直後のコメントアウト検出）が **2 件 FAIL** した
  （文字単位版のバグが実際に再現することを確認済み）。
  逆に行単位版を `check_prefetchable_side_effects.py` / `check_ui_dimensions.py` の実際の
  検査対象ファイル全件（`src/**/*.ts` `src/**/*.tsx` `app/**/*.tsx` 178 ファイル）に通しても、
  `check_file` / `run_checks` の検査結果（違反件数・内容）は **1 件も変わらなかった**
  （生の除去後テキストは 178 件中 146 件で byte 単位に異なるが、それは主に「除去した
  コメント跡を同じ幅の空白で埋めるか、1 行内で詰めるか」という見た目の差であり、行数は
  常に保存されるため、検査が使う行番号計算 `text.count("\n", 0, offset)` には影響しない）。
  よって **行単位版（より保守的・偽陰性が少ない）を本モジュールの正本として採用**し、
  文字単位版はこの限界を持つ旧実装として `strip_comments` の docstring に差分を明記する。

  `find_matching_brace`（2 実装）: **実質的に等価**。文字単位のクォート追跡という設計は
  共通で、テンプレートリテラル内 `${...}` の扱いだけ流儀が違う（`check_prefetchable_side_effects`
  版はバックティックをただの引用符として扱い次のバックティックまで丸ごと不透過にする。
  `check_ui_dimensions` 版は `${` を見つけたら自分自身を再帰呼び出しして中身を正しく読み飛ばす）。
  8 種の合成テストケース（ネストしたオブジェクト・文字列内の中括弧・テンプレートリテラル内の
  ネストしたオブジェクト式・ネストしたバックティック等）と、実際のリポジトリの
  `src/**/*.ts(x)` `app/**/*.tsx` 178 ファイルに現れる全 5,151 個の `{` を対象に両実装へ
  実行して突き合わせたところ、**唯一の差分は「対応する `}` が見つからない（壊れた入力）」
  ケースの戻り値だけ**（`check_prefetchable_side_effects` 版は `len(text) - 1`、
  `check_ui_dimensions` 版は `len(text)` を返す）で、実ファイルで差分が出た 3 箇所は
  いずれも「文字列リテラルの中に現れる `{`」（例: `'{ broken'` のようなテストフィクスチャの
  JSON 破損文字列）を `open_idx` に渡した場合の縮退ケースであり、**どちらの検査スクリプトも
  実際にはこの位置を `open_idx` として渡さない**（両スクリプトとも `size:\s*\{` や関数宣言の
  `(...)` の直後の `{` など、事前に構文的な文脈を絞り込んだ上でしか呼び出さない）。両実装の
  呼び出し元コードでの実際の使い方（`text[open : close + 1]` でスライスする／`code[open+1 : close]`
  でスライスする）を突き合わせても、`len(text)-1` と `len(text)` はスライス演算で同じ範囲
  （末尾まで）を返すため実害が無いことを確認済み。よって **単一の実装に統合可能**と判定し、
  戻り値の規約は `len(text)`（見つからない場合は「1 つ後ろのインデックス」＝ Python の
  スライスに素直に馴染む規約）に統一した。

  `find_tag_end`: 元々重複していないため等価性の判定は不要。ロジックは変更せず、そのまま
  本モジュールへ移植した（コピーであり改善はしていない）。

  `find_function_body_end`: 移植時点ではロジックを変更していなかったが、その後のセルフ
  レビューで「最初に出会った `{` を関数本体の開始とみなす」実装が **分割代入パラメータ
  （`{ headers }: { headers: Headers }`）・デフォルト値のオブジェクトリテラル（`x = { a: 1 }`）・
  戻り値型のオブジェクト型注釈（`(): { ok: boolean } {`）を持つ関数**で本体抽出を誤る欠陥が
  見つかったため追加修正した（詳細は本関数の docstring 参照）。既存の検査結果
  （`check_rate_limit_wiring.py` / `check_ui_dimensions.py` / `check_prefetchable_side_effects.py`
  の出力）はこの修正の前後で一致することを確認済み。

使い方（self-test のみ。本体はライブラリとして import される想定）:
  python3 tools/ts_source.py --self-test
"""

from __future__ import annotations

import re
import sys

# ---------------------------------------------------------------------------
# JS / TS の識別子パターン（共通定数）
# ---------------------------------------------------------------------------
# ECMAScript の識別子（ASCII 範囲）。字句解析をする検査スクリプトが「識別子の直後に何が
# 来るか」を判定するのに使う。`check_ui_dimensions.py`（識別子直後の `(` で関数呼び出しを
# 見分ける）と `check_duplicate_source_patterns.py`（識別子直後の `/` が除算か正規表現かを
# 見分ける）が同じパターンを独立に持っていたため、ここへ集約した（Issue #612）。
JS_IDENTIFIER_RE = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")

# ---------------------------------------------------------------------------
# strip_comments（正本: check_rate_limit_wiring.py の行単位実装）
# ---------------------------------------------------------------------------

_LINE_COMMENT = "//"
_BLOCK_OPEN = "/*"
_BLOCK_CLOSE = "*/"


def _strip_line_tracking_quotes(
    line: str, quote: str | None, in_block: bool
) -> tuple[str, str | None, bool]:
    """1 行からコメントを除く（文字列リテラルの中身は保つ）。(出力, 行末 quote, 行末 in_block)。"""
    out: list[str] = []
    i, n = 0, len(line)
    while i < n:
        if in_block:
            end = line.find(_BLOCK_CLOSE, i)
            if end == -1:
                i = n
                break
            in_block = False
            i = end + 2
            continue
        ch = line[i]
        if quote:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(line[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "'\"`":
            quote = ch
            out.append(ch)
            i += 1
            continue
        if line.startswith(_LINE_COMMENT, i):
            break  # 行末まで捨てる
        if line.startswith(_BLOCK_OPEN, i):
            in_block = True
            out.append(" ")
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out), quote, in_block


def _strip_line_ignoring_quotes(line: str, in_block: bool) -> tuple[str, bool]:
    """クォート追跡を諦めて **消しすぎる方向** に倒す（`//` 以降と `/* */` を無条件で捨てる）。"""
    out: list[str] = []
    i, n = 0, len(line)
    while i < n:
        if in_block:
            end = line.find(_BLOCK_CLOSE, i)
            if end == -1:
                i = n
                break
            in_block = False
            i = end + 2
            continue
        if line.startswith(_LINE_COMMENT, i):
            break
        if line.startswith(_BLOCK_OPEN, i):
            in_block = True
            out.append(" ")
            i += 2
            continue
        out.append(line[i])
        i += 1
    return "".join(out), in_block


def strip_comments(source: str) -> str:
    """TS/TSX から行コメント・ブロックコメントを取り除く（文字列リテラルの中身は保つ）。

    コメント内・文字列内の `<Link href="/api/...">` や `cookies.delete(` や
    `enforce*RateLimit(` を誤検出しないための前処理。素朴に `//` で切ると
    `'https://…'` を壊すため、文字列リテラルを跨がないスキャナにしている。

    🔴 **行単位で走査する**（誤検出の実害を 1 行に閉じ込めるため）。ソース全体を 1 本の
    クォート状態で舐める素朴な実装は、対にならないアポストロフィ（`<p>Don't worry</p>`）や
    正規表現リテラル（`/'/g`）を「文字列の開始」と誤解し、**以降のファイル全体でコメントが
    除去されなくなる**（コメントアウトして戻し忘れたコードを「有効なコード」と誤認する
    ＝偽陰性）。JS/TS の非テンプレート文字列は行をまたげないので、改行に到達したら
    クォート状態を捨ててよい（テンプレートリテラルだけは跨げるので維持する）。

    さらに、行末でクォートが閉じていない行は追跡結果自体が信用できないため、その行だけ
    **消しすぎる方向（= 呼び出し・タグを見失い違反として検出する安全側）** に倒して読み直す。
    正規表現リテラル（`/https:\\/\\//`）を完全に解釈することは字句解析なしには不可能なので、
    「見逃して緑になる」より「消しすぎて赤くなる」を選ぶ。

    ⚠️ **他実装との既知の差分（Issue #612 の等価性判定で確認済み）**: 本実装は削除した
    コメント跡を同じ幅の空白で埋めない（1 行の中で文字位置＝列がずれる）。行数（`\n` の数）
    だけは常に保存するため、`text.count("\n", 0, offset)` による行番号計算には影響しない。
    実際に本リポジトリの検査対象ファイル全件（178 ファイル）で確認したところ、この差は
    どの検査スクリプトの違反検出結果にも影響しなかった（詳細はモジュール docstring）。
    """
    out: list[str] = []
    quote: str | None = None
    in_block = False
    for raw_line in source.splitlines(keepends=True):
        if raw_line.endswith("\n"):
            body, eol = raw_line[:-1], "\n"
        else:
            body, eol = raw_line, ""
        text, next_quote, next_block = _strip_line_tracking_quotes(body, quote, in_block)
        if next_quote is not None and next_quote != "`":
            # 行内でクォートが閉じない = アポストロフィか正規表現リテラルを文字列の開始と
            # 誤解した。この行の追跡は信用できないので安全側（消しすぎる方向）へ倒す。
            text, next_block = _strip_line_ignoring_quotes(body, in_block)
            next_quote = None
        out.append(text + eol)
        quote, in_block = next_quote, next_block
    return "".join(out)


# ---------------------------------------------------------------------------
# find_matching_brace（正本: check_ui_dimensions.py の再帰版。戻り値規約は len(text)）
# ---------------------------------------------------------------------------


def find_matching_brace(text: str, open_idx: int) -> int:
    """`text[open_idx] == '{'` として、対応する `}` のインデックスを返す。

    文字列リテラル（`"` `'`）・テンプレートリテラル（`` ` ``、`${...}` の再帰含む）の
    中身は中括弧としてカウントしない。**呼び出し前に `strip_comments` 済みのテキストを渡す
    想定**（コメント内の `{` `}` は考慮しない）。

    対応する閉じ括弧が見つからない場合は `len(text)` を返す（見つからない＝壊れた/切り詰め
    られた入力で、実際の呼び出し元は事前に正規表現などで構文的な文脈を絞り込んだ `{` にしか
    `open_idx` を渡さないため、通常この分岐には到達しない）。

    ⚠️ **他実装との既知の差分**: `check_prefetchable_side_effects.py` の旧実装は、この
    「見つからない」場合に `len(text) - 1` を返していた（テンプレートリテラルの `${...}` も
    再帰せず、バックティックを普通の引用符と同様に次のバックティックまで丸ごと不透過にする
    という設計だった）。実行で確認した限り、この差はどちらも「呼び出し元が `text[open_idx :
    close + 1]` のようにスライスする」使い方では同じ範囲（末尾まで）を返すため実害が無く、
    ネストしたテンプレートリテラル・オブジェクト式を含む 8 種の合成ケースおよび本リポジトリの
    実ファイル全件（`{` 5,151 個）でも、正当な呼び出し（文字列内の `{` を `open_idx` として
    渡さない）の範囲では出力が完全に一致した。詳細はモジュール docstring。
    """
    n = len(text)
    depth = 0
    i = open_idx
    while i < n:
        ch = text[i]
        if ch == "{":
            depth += 1
            i += 1
            continue
        if ch == "}":
            depth -= 1
            i += 1
            if depth == 0:
                return i - 1
            continue
        if ch in "\"'":
            q = ch
            i += 1
            while i < n and text[i] != q:
                i += 2 if text[i] == "\\" else 1
            i += 1
            continue
        if ch == "`":
            i += 1
            while i < n and text[i] != "`":
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == "$" and i + 1 < n and text[i + 1] == "{":
                    i = find_matching_brace(text, i + 1) + 1
                    continue
                i += 1
            i += 1
            continue
        i += 1
    return n


# ---------------------------------------------------------------------------
# extract_comments（新設・Issue #992 フォローアップ）
# ---------------------------------------------------------------------------

# `extract_comments` の正規表現リテラル判定に使う「直前の意味のあるトークンが値か」の
# ヒューリスティック。`check_duplicate_source_patterns.py` の `_KEYWORDS_EXPR_START` と
# 同じ判断基準（このキーワード群の直後の `/` は除算ではありえない）。用途が異なる別モジュール
# 内の判定のため、結合度を上げないためにあえて再定義している（同じ実測結果に基づく定数）。
_REGEX_CONTEXT_KEYWORDS = {
    "return", "typeof", "instanceof", "in", "of", "new", "delete", "void", "throw",
    "case", "do", "else", "yield", "await", "if", "while", "for", "switch", "extends",
    "default", "export", "const", "let", "var", "function", "class", "import", "from",
    "async", "static", "get", "set", "catch", "finally", "try", "break", "continue",
}


def _skip_backtick_literal(source: str, start: int) -> int | None:
    """`source[start] == '`'` として、対応する終端バッククォートの **直後** のインデックスを
    返す。`${...}` 補間の中括弧対応は `find_matching_brace`（正本を再利用・二重実装しない）に
    委譲する。終端が見つからない、または補間式が閉じない場合は `None`（解析失敗）を返す。
    """
    n = len(source)
    i = start + 1
    while i < n:
        ch = source[i]
        if ch == "\\" and i + 1 < n:
            i += 2
            continue
        if ch == "`":
            return i + 1
        if ch == "$" and i + 1 < n and source[i + 1] == "{":
            close = find_matching_brace(source, i + 1)
            if close >= n:
                return None  # 補間式 ${...} が閉じない = 解析失敗
            i = close + 1
            continue
        i += 1
    return None  # 終端のバッククォートが見つからない = 解析失敗


def extract_comments(source: str) -> list[str] | None:
    """JS/TS ソース全体から `//` 行コメント・`/* ... */` ブロックコメントの本文
    （区切り記号を除いた中身）だけを抽出する（`tools/check_selftest_wiring.py` の
    `selftest-wiring-ok` マーカー検出用・Issue #992 フォローアップ）。

    🔴 **なぜ `strip_comments` を直接は再利用しないか**: `strip_comments` は「除去」だけが
    目的で、コメント本文そのものを保持しない（`/* ... */` を空白 1 文字に潰す）ため、本関数の
    目的（コメント本文からマーカーを探す）には使えない。加えて `strip_comments` の行単位
    スキャナは **正規表現リテラルを認識しない**（`/` を常に「除算 or コメント境界」としてしか
    見ない）ため、`const SEP_RE = /[/*]/;` のような正規表現リテラルの内部に現れる `/*` を
    ブロックコメント開始と誤認し、以降の行（本物のコメント・マーカーを含む）を巻き込んで
    誤って「まだ閉じていないブロックコメントの続き」として飲み込んでしまう
    （`strip_comments` 自身も潜在的にこの欠陥を持つが、既存 178 ファイルの実測では
    一度も顕在化していないため本 Issue のスコープでは手を入れない。将来別ファイルで
    顕在化したら `strip_comments` 側の改修を別 Issue で検討する）。

    本関数は `check_duplicate_source_patterns.py` の `iter_ts_regex_literals` と同じ
    「直前の意味のあるトークンが値かどうか」ヒューリスティックで正規表現リテラルを
    不透明な単位として読み飛ばし、この誤認を避ける。文字列・テンプレートリテラルの中身も
    同様にコメントとして扱わない（`marker_reason()` が文字列内の偽マーカーを拾わないための
    前提）。

    構文的に閉じられない文字列・テンプレートリテラル・ブロックコメント・正規表現の補間式に
    遭遇した場合はクラッシュせず `None` を返す（安全側フォールバック。呼び出し側は
    `tokenize` 失敗時と同じく「マーカーなし」として扱う）。単一行文字列 `'...'` / `"..."`
    が改行までに閉じない場合も解析失敗として `None` を返す（正当な JS/TS 構文では単一行
    文字列は改行を跨げないため、これは入力破損のシグナルであり `strip_comments` の
    「対にならないクォート」安全側判定と同じ思想）。
    """
    comments: list[str] = []
    i, n = 0, len(source)
    last_value = False  # 直前の意味のあるトークンが「値」（除算文脈）かどうか
    while i < n:
        ch = source[i]
        if ch in " \t\r\n":
            i += 1
            continue
        if ch in "'\"":
            quote = ch
            j = i + 1
            closed = False
            while j < n:
                c = source[j]
                if c == "\\" and j + 1 < n:
                    j += 2
                    continue
                if c == "\n":
                    break
                if c == quote:
                    j += 1
                    closed = True
                    break
                j += 1
            if not closed:
                return None  # 単一行文字列が閉じられないまま改行/EOF = 解析失敗
            i = j
            last_value = True
            continue
        if ch == "`":
            end = _skip_backtick_literal(source, i)
            if end is None:
                return None
            i = end
            last_value = True
            continue
        if ch.isdigit():
            j = i
            while j < n and (source[j].isalnum() or source[j] in "._"):
                j += 1
            i = j
            last_value = True
            continue
        m = JS_IDENTIFIER_RE.match(source, i)
        if m:
            word = m.group(0)
            i = m.end()
            last_value = word not in _REGEX_CONTEXT_KEYWORDS
            continue
        if ch == "/":
            nxt = source[i + 1] if i + 1 < n else ""
            # `//` `/*` は「直前が値かどうか」に関わらず常にコメント境界である
            # （空の正規表現リテラル `//` も `/*` から始まる正規表現も JS 構文上存在しない）。
            # この判定を regex-vs-division の分岐より先に行うことで、`/[/*]/` のような
            # 正規表現リテラルの中身を安全に読み飛ばした後、その直後にある `//`/`/*` は
            # 従来どおり正しくコメントとして認識できる。
            if nxt == "/":
                nl = source.find("\n", i + 2)
                if nl == -1:
                    comments.append(source[i + 2 :])
                    i = n
                else:
                    comments.append(source[i + 2 : nl])
                    i = nl
                last_value = False
                continue
            if nxt == "*":
                close = source.find("*/", i + 2)
                if close == -1:
                    return None  # 未終端のブロックコメント = 解析失敗
                comments.append(source[i + 2 : close])
                i = close + 2
                last_value = False
                continue
            if last_value:
                # 除算演算子（例: `a / b`）
                i += 1
                last_value = False
                continue
            # 正規表現リテラルとしてパースを試みる（iter_ts_regex_literals と同じロジック。
            # ここで本体を丸ごと読み飛ばすことで、本体内部の `/*` 等をコメント境界と
            # 誤認しない）。
            j = i + 1
            in_class = False
            ok = False
            while j < n:
                c = source[j]
                if c == "\\":
                    j += 2
                    continue
                if c == "\n":
                    break  # 改行を跨ぐ正規表現リテラルは存在しない → 不正な入力として諦める
                if c == "[":
                    in_class = True
                elif c == "]":
                    in_class = False
                elif c == "/" and not in_class:
                    ok = True
                    j += 1
                    break
                j += 1
            if ok:
                k = j
                while k < n and source[k].isalpha():
                    k += 1
                i = k
                last_value = True
                continue
            # 対応する終端 `/` が見つからない → 正規表現ではなく除算とみなして 1 文字進める
            i += 1
            last_value = False
            continue
        if ch in ")]":
            i += 1
            last_value = True
            continue
        i += 1
        last_value = False
    return comments


# ---------------------------------------------------------------------------
# find_tag_end（正本: check_prefetchable_side_effects.py。ロジック変更なしの移植）
# ---------------------------------------------------------------------------


def find_tag_end(text: str, start_idx: int) -> int:
    """`text[start_idx]` 以降で、深さ 0 のタグ終端 `>` のインデックスを返す。

    JSX 属性は `{...}`（式）や `(...)`（関数呼び出し・アロー関数）を含みうり、その中には
    `onClick={() => doThing()}` のアロー演算子 `=>` や比較式 `{a > b}` のように `>` が
    現れうる。非貪欲正規表現の `.*?/?>` はこれをタグ終端と誤認してしまうため、`{}` / `()`
    の深さと文字列クォートを追跡しながら 1 文字ずつ走査し、深さ 0 の `>` だけをタグ終端と
    みなす。見つからなければ -1 を返す。

    🔴 元は `check_prefetchable_side_effects.py` にのみ存在し、`check_ui_dimensions.py` には
    無かった（Issue #612）。そのため `check_ui_dimensions.py` 側は `onClick={() => f()}` の
    `=>` をタグ終端と誤認するバグを抱えたままだった。ロジックは変更していない（移植のみ）。
    """
    i = start_idx
    n = len(text)
    brace_depth = 0
    paren_depth = 0
    quote: str | None = None
    while i < n:
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "\"'`":
            quote = ch
            i += 1
            continue
        if ch == "{":
            brace_depth += 1
        elif ch == "}":
            brace_depth = max(0, brace_depth - 1)
        elif ch == "(":
            paren_depth += 1
        elif ch == ")":
            paren_depth = max(0, paren_depth - 1)
        elif ch == ">" and brace_depth == 0 and paren_depth == 0:
            return i
        i += 1
    return -1


# ---------------------------------------------------------------------------
# find_function_body_end（正本: check_rate_limit_wiring.py。ロジック変更なしの移植）
# ---------------------------------------------------------------------------


def find_matching_paren(text: str, open_idx: int) -> int:
    """`text[open_idx] == '('` として、対応する `)` のインデックスを返す。

    クォート（`'` `"` `` ` ``）の中の括弧は数えない。中に現れる `{` `}` はそもそも
    数えない（分割代入パラメータ・デフォルト値のオブジェクトリテラルはそれ自身で完結して
    おり、外側の `(` `)` の対応関係を崩さないため、無視してよい）。

    対応する `)` が見つからない場合は **`-1` を返す**（`find_tag_end` と同じ「未発見は -1」
    契約。見つかった場合は `find_matching_brace` と同じ「閉じ文字そのもののインデックス」を
    返す規約に揃える）。

    🔴 なぜ新設したか（Issue #828 Layer 1 CRITICAL 指摘）: `check_prefetchable_side_effects.py`
    が独自に持つ `find_matching_paren`（未発見時 `n - 1` を返す）とも、本モジュール内部専用の
    `_find_matching_paren`（未発見時 `len(text)` を返す・関数本体探索の内部実装に依存した契約）
    とも戻り値の意味が違う。`_find_matching_paren` の「未発見時は末尾扱いで処理を継続する」
    契約は `_skip_parameter_list` が正しく依存しているため変更しない（本関数へ委譲するだけの
    薄いラッパーに変えた）。一方 `check_ui_dimensions.py` 側は「未発見（壊れた/切り詰められた
    入力）を確実にスキップする」ために `-1` という **実在のインデックスと衝突しない値** が
    必要だった（`len(text)` は一見実在のインデックスに見えてしまい、`close <= open_paren` の
    ような事後チェックを別途書かないと安全に判定できず、そのガード自体にバグが混入していた
    ＝実際に本 Issue の CRITICAL 指摘の原因）。
    """
    n = len(text)
    depth = 0
    i = open_idx
    quote: str | None = None
    while i < n:
        ch = text[i]
        if quote:
            if ch == "\\" and i + 1 < n:
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "'\"`":
            quote = ch
            i += 1
            continue
        if ch == "(":
            depth += 1
            i += 1
            continue
        if ch == ")":
            depth -= 1
            i += 1
            if depth == 0:
                return i - 1
            continue
        i += 1
    return -1


def _find_matching_paren(text: str, open_idx: int) -> int:
    """`text[open_idx] == '('` として、対応する `)` の直後のインデックスを返す。

    🔴 **内部専用**（本モジュール内の `_skip_parameter_list` 専用）。未発見時に `len(text)` を
    返す契約に `_skip_parameter_list` が依存している（見つからなければ「仮引数リストがソース
    末尾まで続く」ものとして扱い、`find_function_body_end` 側の以降の走査を自然に打ち切らせる
    ため）。**この契約を変更しない**。外部（`check_ui_dimensions.py` 等）から呼ぶ場合は
    `find_matching_paren`（未発見時 `-1` を返す公開版）を使うこと。実装は `find_matching_paren`
    へ委譲し、その戻り値（見つかった場合は `)` 自身のインデックス／見つからない場合は `-1`）を
    本関数の契約（`)` の直後のインデックス／見つからない場合は `len(text)`）に変換するだけの
    薄いラッパー。
    """
    close = find_matching_paren(text, open_idx)
    return len(text) if close == -1 else close + 1


def _find_unquoted_char(text: str, start: int, end: int, target: str) -> int:
    """`text[start:end]` の範囲で、クォート外に現れる最初の `target` のインデックスを返す
    （見つからなければ `end`）。"""
    i = start
    quote: str | None = None
    while i < end:
        ch = text[i]
        if quote:
            if ch == "\\" and i + 1 < end:
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "'\"`":
            quote = ch
            i += 1
            continue
        if ch == target:
            return i
        i += 1
    return end


# `EXPORT_RE` / `GENERIC_EXPORT_RE`（呼び出し元 `check_rate_limit_wiring.py`）が要求する
# `export [async] (function|const) NAME` という接頭辞の直後に続く仮引数リストの開始 `(` を
# 検出する。`export const NAME = someFactory(...)` のような **関数式ではない初期化子**
# （`=` の直後がいきなり `(` ではなく識別子）には意図的にマッチしない ── 呼び出し式の
# 引数リストを仮引数リストと誤認し、走査範囲を不当に広げる事故を避けるため。
_PARAM_LIST_HEAD_RE = re.compile(
    r"export\s+(?:async\s+)?"
    r"(?:"
    r"function\s*\*?\s*[A-Za-z_$][\w$]*\s*(?:<[^(){}]*>)?\s*"
    r"|"
    r"const\s+[A-Za-z_$][\w$]*\s*(?::[^=]*)?=\s*(?:async\s+)?"
    r")\("
)


def _skip_parameter_list(source: str, start: int) -> int:
    """`start`（`export` の開始位置）に仮引数リスト `(...)` が続く場合、それを読み飛ばした
    直後のオフセットを返す（続かない場合は `start` をそのまま返す）。

    🔴 なぜ要るか: 仮引数リストが分割代入パターン（`{ headers }: { headers: Headers }`）や
    デフォルト値のオブジェクトリテラル（`x = { a: 1 }`）を含むと、後続の `find_function_body_end`
    がそれらの `{` を関数本体の開始と誤認してしまい、対応する `}`（分割代入パターン自身の
    閉じ括弧）で本体抽出を打ち切ってしまう（本来の本体・呼び出し・接頭辞リテラルが丸ごと
    欠落する）。仮引数リストの中身は `(` `)` の対応関係だけで丸ごと読み飛ばし、その中の
    `{` `}` を関数本体探索の対象から外す。
    """
    match = _PARAM_LIST_HEAD_RE.match(source, start)
    if not match:
        return start
    open_idx = match.end() - 1  # マッチ末尾の '(' 自身
    return _find_matching_paren(source, open_idx)


def find_function_body_end(source: str, start: int, fallback_end: int) -> int:
    """`start`（export 宣言などの開始位置）から、対応する関数本体の閉じ括弧の直後の
    オフセットを返す（波括弧の対応を追跡する簡易ブレースカウンタ）。

    🔴 なぜ要るか（Issue #604 フォローアップ）: 「本文の終端 = 次の export 宣言の開始位置」
    という単純なテキストスライスだと、export と export の間に非 export のトップレベル関数
    （ヘルパー等）が置かれている場合、そのヘルパーの中身が直前の export の本文として一緒に
    取り込まれてしまい、ヘルパー側の呼び出しが export のものとして **誤帰属** する
    （export の本体は実際には呼んでいないのに「配線あり」と誤って認識される＝偽陰性）。

    🔴 **さらに追加修正（分割代入パラメータ対応）**: 「最初に出会った `{` を関数本体の開始と
    みなす」だけでは、次の 3 パターンで本体抽出が壊れる。
      1. 分割代入パラメータ（`function f({ headers }: { headers: Headers }) { ... }`）
      2. デフォルト値のオブジェクトリテラル（`function f(x = { a: 1 }) { ... }`）
      3. 戻り値型のオブジェクト型注釈（`function f(): { ok: boolean } { ... }`）
    いずれも、実際の関数本体より **前** に自己完結した `{...}` が現れ、素朴なブレース
    カウンタはその閉じ括弧で本体が終わったと誤認する。これに対して 2 段階で対処する:
      - まず `_skip_parameter_list` で仮引数リスト `(...)` を丸ごと読み飛ばす
        （パターン 1・2 はこれで解決する。仮引数リスト内の `{` `}` は候補から外れる）。
      - 続けて見つけた `{...}` 候補について、その閉じ `}` の直後（空白のみ許容）に
        **さらに `{` が続く場合**、この候補は関数本体ではなく戻り値型のオブジェクト型注釈
        （パターン 3）とみなし、続く `{` を新たな候補として選び直す。真の関数本体の閉じ `}`
        の直後に別の `{` が空白のみを挟んで直接続くことは、実在の TypeScript 構文としては
        事実上起こらない（起きるとすれば次の宣言のキーワード・識別子・コメント等が必ず挟まる）。

    波括弧の対応を文字単位で数え、**クォート（`'` `"` `` ` ``）の中の `{` `}` は数えない**
    （文字列リテラル中の中括弧で対応がずれるのを避ける・エスケープ文字も 1 文字読み飛ばす）。
    完全な字句解析ではないため正規表現リテラル中の `{n,m}` のような量指定子までは判別できないが、
    それは `strip_comments` と同じ「完璧なパーサは持たない」割り切りに合わせている。

    最初の `{` に到達する前に走査が尽きた場合（例: 本体を持たない一行の `export const x = 5`、
    または `export const x = someFactory(...)` のような関数式ではない初期化子）は対応する
    閉じ括弧が無いので `fallback_end`（次の export 宣言の開始位置、無ければソース終端）を返す。
    """
    n = len(source)
    i = _skip_parameter_list(source, start)
    while True:
        open_idx = _find_unquoted_char(source, i, n, "{")
        if open_idx >= n:
            return fallback_end
        close_idx = find_matching_brace(source, open_idx)
        if close_idx >= n:
            return fallback_end
        k = close_idx + 1
        while k < n and source[k] in " \t\r\n":
            k += 1
        if k < n and source[k] == "{":
            # 戻り値型のオブジェクト型注釈（パターン 3）とみなし、続く { を選び直す。
            i = k
            continue
        return close_idx + 1


# ---------------------------------------------------------------------------
# self-test
# ---------------------------------------------------------------------------


def _run_self_test() -> int:
    failures: list[str] = []

    def check(label: str, got, want) -> None:
        if got != want:
            failures.append(f"  {label}: want {want!r}, got {got!r}")

    # ---------------- strip_comments ----------------

    # 正常系: 通常の // と /* */ コメントを除去する
    check(
        "strip_comments/normal_line_comment",
        strip_comments("const a = 1 // comment\n").strip(),
        "const a = 1",
    )
    check(
        "strip_comments/normal_block_comment",
        strip_comments("const a = /* c */ 1\n").replace(" ", ""),
        "consta=1\n".replace(" ", ""),
    )

    # 偽陽性の反例: 文字列リテラル内のコメント記号は保護される（要求ケース）
    check(
        "strip_comments/string_literal_protects_comment_marker",
        strip_comments('const s = "// not a comment"\n'),
        'const s = "// not a comment"\n',
    )
    check(
        "strip_comments/string_literal_protects_block_marker",
        strip_comments("const s = '/* not a comment */'\n"),
        "const s = '/* not a comment */'\n",
    )
    # テンプレートリテラル内の ${} とコメント記号は保護される
    check(
        "strip_comments/template_literal_interp_and_comment_marker",
        strip_comments("const s = `a ${1 + 2} // not-comment b`\n"),
        "const s = `a ${1 + 2} // not-comment b`\n",
    )
    # エスケープされたクォートを正しく扱う（クォートの終端を誤認しない）
    check(
        "strip_comments/escaped_quote",
        strip_comments('const s = "a \\" b" // trailing comment\n').rstrip(),
        'const s = "a \\" b"',
    )
    # 複数行テンプレートリテラル（改行を跨ぐ）はクォート状態を維持する
    check(
        "strip_comments/multiline_template_literal",
        strip_comments("const q = `line1\nline2 // not a comment`\nawait f()\n"),
        "const q = `line1\nline2 // not a comment`\nawait f()\n",
    )

    # 偽陰性の反例（今回の事故の本質）: 対にならないアポストロフィ・正規表現リテラルの
    # 「あと」にあるコメントアウトされたコードを、有効なコードと誤認しない
    stripped = strip_comments(
        "export default function Page() {\n  return <p>Don't worry</p>\n}\n"
        "// await enforceGemListRateLimit(await headers())\n"
    )
    if "enforceGemListRateLimit" in stripped:
        failures.append(
            "strip_comments/apostrophe_does_not_hide_later_comment: "
            "アポストロフィの後ろのコメントアウトされた呼び出しが除去されず残っている"
            f"（偽陰性）: {stripped!r}"
        )
    stripped2 = strip_comments(
        "const slug = raw.replace(/'/g, '')\n// await enforceGemListRateLimit(await headers())\n"
    )
    if "enforceGemListRateLimit" in stripped2:
        failures.append(
            "strip_comments/regex_literal_does_not_hide_later_comment: "
            "正規表現リテラルの後ろのコメントアウトされた呼び出しが除去されず残っている"
            f"（偽陰性）: {stripped2!r}"
        )

    # ---------------- find_matching_brace ----------------

    def brace_span(text: str) -> int:
        return find_matching_brace(text, text.index("{"))

    check("find_matching_brace/simple", brace_span("{ a: 1, b: 2 }"), 13)
    check("find_matching_brace/nested_object", brace_span("{ a: { b: 1 }, c: 2 }"), 20)
    # 偽陽性の反例: 文字列リテラル内の中括弧を対応関係の一部として数えない
    check(
        "find_matching_brace/string_with_unbalanced_braces",
        brace_span('{ a: "x } y {" , b: 2 }'),
        22,
    )
    # テンプレートリテラルの ${} 内のネストしたオブジェクト式も正しく読み飛ばす
    check(
        "find_matching_brace/template_interp_with_object",
        brace_span("{ a: `x${ ({b:1}) } y` }"),
        23,
    )
    # ネストしたバックティック（テンプレートリテラルの中のテンプレートリテラル）
    check(
        "find_matching_brace/nested_backtick_in_interp",
        brace_span("{ a: `x ${ `y ${1}` } z` , b: 2 }"),
        32,
    )
    # エスケープされたクォートの中の中括弧を数えない
    check(
        "find_matching_brace/escaped_quote_inside",
        brace_span('{ a: "x \\" } y" }'),
        16,
    )
    # 対応する閉じ括弧が無い（壊れた入力）→ len(text) を返す
    broken = "{ a: 1"
    check("find_matching_brace/unmatched_returns_len", find_matching_brace(broken, 0), len(broken))

    # ---------------- find_tag_end ----------------

    # 必須ケース1: アロー関数を含む属性があってもタグ全体（/> まで）を正しく取れる
    tag1 = '<Input onClick={() => f()} size="xl" />'
    idx1 = find_tag_end(tag1, tag1.index("Input") + len("Input"))
    check("find_tag_end/arrow_function_attr_full_tag", tag1[idx1], ">")
    check("find_tag_end/arrow_function_attr_position", idx1, len(tag1) - 1)

    # 必須ケース2: 属性値の文字列内に > があっても誤ってタグ終端と判定しない
    tag2 = '<A title="a > b" />'
    idx2 = find_tag_end(tag2, tag2.index("A ") + 1)
    check("find_tag_end/gt_inside_string_attr", idx2, len(tag2) - 1)

    # 偽陽性の反例: 比較式 {a > b} の > をタグ終端と誤認しない
    tag3 = '<Box cond={a > b} label="x" />'
    idx3 = find_tag_end(tag3, tag3.index("Box") + len("Box"))
    check("find_tag_end/gt_inside_expr_comparison", idx3, len(tag3) - 1)

    # 偽陰性の反例（実バグ再現）: 非貪欲正規表現 `.*?/?>` は onClick 内の => を
    # タグ終端と誤認し、後続の href を取りこぼす。find_tag_end はこれを起こさない。
    tag4 = '<Link onClick={() => doThing()} href="/api/auth/logout">out</Link>'
    idx4 = find_tag_end(tag4, tag4.index("Link") + len("Link"))
    attrs4 = tag4[tag4.index("Link") + len("Link") : idx4]
    if "/api/auth/logout" not in attrs4:
        failures.append(
            "find_tag_end/arrow_in_attr_does_not_truncate: "
            f"href を含む前で誤ってタグ終端と判定した（偽陰性）: attrs={attrs4!r}"
        )

    # 見つからない場合は -1
    check("find_tag_end/not_found", find_tag_end("<Foo bar=1", 4), -1)

    # ---------------- find_matching_paren（公開版・未発見は -1・Issue #828） ----------------

    def paren_span(text: str) -> int:
        return find_matching_paren(text, text.index("("))

    check("find_matching_paren/simple", paren_span("(a, b)"), 5)
    check("find_matching_paren/nested", paren_span("(a, (b, c), d)"), 13)
    # 文字列リテラル内の括弧は対応関係の一部として数えない
    check(
        "find_matching_paren/string_with_unbalanced_parens",
        paren_span('(a, "x ) y (" , b)'),
        17,
    )
    # 対応する閉じ括弧が最後の文字であっても正しく見つかる（off-by-one の反例）
    check("find_matching_paren/close_is_last_char", paren_span("(a)"), 2)
    # 対応する閉じ括弧が無い（壊れた/切り詰められた入力）→ -1（len(text) ではない）
    check("find_matching_paren/unmatched_returns_neg_one", find_matching_paren("(a, b", 0), -1)
    # `_find_matching_paren`（内部版・委譲先）は従来どおり len(text) を返す契約を維持する
    check(
        "find_matching_paren/internal_wrapper_still_returns_len_on_unmatched",
        _find_matching_paren("(a, b", 0),
        len("(a, b"),
    )
    check(
        "find_matching_paren/internal_wrapper_matches_close_plus_one",
        _find_matching_paren("(a)", 0),
        3,
    )

    # ---------------- find_function_body_end ----------------

    # 必須ケース: export の直後に非 export のヘルパー関数が続く。export の本文が
    # 対応する } で正しく終わり、ヘルパーの中身を取り込まない（偽陰性の反例）。
    src = (
        "export async function prepareSearchKeyword(raw) {\n"
        "  const keyword = parse(raw)\n"
        "  return keyword\n"
        "}\n"
        "\n"
        "function debugLogRateLimitProbe(headers) {\n"
        "  void enforceSearchRateLimit(headers)\n"
        "}\n"
    )
    start = src.index("export")
    fallback = len(src)
    end = find_function_body_end(src, start, fallback)
    body = src[start:end]
    if "enforceSearchRateLimit" in body:
        failures.append(
            "find_function_body_end/does_not_swallow_following_helper: "
            f"export の外側にあるヘルパーの呼び出しが本文に取り込まれている（誤帰属）: {body!r}"
        )
    if "return keyword" not in body:
        failures.append(
            f"find_function_body_end/includes_own_body: export 自身の本文が欠けている: {body!r}"
        )

    # 偽陽性の反例: 文字列リテラル中の { } で対応がずれない
    src2 = 'export function f() {\n  const s = "a { b } c"\n  return s\n}\n'
    end2 = find_function_body_end(src2, src2.index("export"), len(src2))
    check("find_function_body_end/string_braces_do_not_confuse", src2[end2 - 1], "}")

    # 本体を持たない一行の宣言は fallback_end を返す
    src3 = "export const x = 5\nexport const y = 6\n"
    fallback3 = src3.index("export", 1)
    end3 = find_function_body_end(src3, 0, fallback3)
    check("find_function_body_end/no_body_uses_fallback", end3, fallback3)

    # ---------------- find_function_body_end: 分割代入パラメータ等の反例（本 PR） ----------------
    # 🔴 「最初に出会った { を関数本体の開始とみなす」実装は、実際の本体より前に自己完結した
    # { ... } が現れるパターンで本体抽出が壊れる（詳細は本関数 docstring）。以下 7 パターンを
    # 網羅する（末尾の g / h は特にパラメータリストの外側に { が現れる要注意ケース）。

    def body_of(source: str) -> str:
        start = source.index("export")
        end = find_function_body_end(source, start, len(source))
        return source[start:end]

    # a) 通常の関数（回帰確認・分割代入なし）
    src_a = "export function a(x: string) { return f(x) }\n"
    check("find_function_body_end/destructure_a_normal", body_of(src_a).strip(), src_a.strip())

    # b) 分割代入パラメータ（実バグ再現。本体が丸ごと欠落していた）
    src_b = "export function b({ headers }: { headers: Headers }) { return f() }\n"
    check("find_function_body_end/destructure_b_object_param", body_of(src_b).strip(), src_b.strip())

    # c) 複数の分割代入パラメータ
    src_c = "export function c({ a, b }: T, { c }: U) { return f() }\n"
    check(
        "find_function_body_end/destructure_c_multiple_object_params",
        body_of(src_c).strip(),
        src_c.strip(),
    )

    # d) アロー関数 + 分割代入パラメータ
    src_d = "export const d = ({ x }: P) => { return f(x) }\n"
    check(
        "find_function_body_end/destructure_d_arrow_object_param", body_of(src_d).strip(), src_d.strip()
    )

    # e) 本体が式（ブロックでない）アロー関数 → { が無いので fallback_end を返す
    src_e = "export const e = (x) => f(x)\nexport const zNext = 1\n"
    fallback_e = src_e.index("export", 1)
    end_e = find_function_body_end(src_e, src_e.index("export"), fallback_e)
    check("find_function_body_end/destructure_e_arrow_expression_body_uses_fallback", end_e, fallback_e)

    # g) デフォルト値がオブジェクトリテラル（パラメータリスト内側だが分割代入と同型の罠）
    src_g = "export function g(x = { a: 1 }) { return f(x) }\n"
    check(
        "find_function_body_end/destructure_g_default_object_value", body_of(src_g).strip(), src_g.strip()
    )

    # h) 戻り値型がオブジェクト型（パラメータリストの外側に { が現れる・最重要の要注意ケース）
    src_h = "export function h(): { ok: boolean } { return f() }\n"
    check(
        "find_function_body_end/destructure_h_object_return_type", body_of(src_h).strip(), src_h.strip()
    )

    # ---------------- extract_comments（新設・Issue #992 フォローアップ） ----------------

    # 正常系: `//` 行コメント本文をそのまま返す（区切り記号は含まない）
    check(
        "extract_comments/line_comment_basic",
        extract_comments("const a = 1 // hello\n"),
        [" hello"],
    )
    # 正常系: `/* */` ブロックコメント本文をそのまま返す（複数行もひとかたまり）
    check(
        "extract_comments/block_comment_basic",
        extract_comments("const a = /* c */ 1\n"),
        [" c "],
    )
    check(
        "extract_comments/block_comment_multiline",
        extract_comments("/*\n * marker: x\n */\nconst a = 1\n"),
        ["\n * marker: x\n "],
    )
    # 複数コメントを出現順に全て返す
    check(
        "extract_comments/multiple_comments_in_order",
        extract_comments("// first\nconst a = 1 /* second */\n// third\n"),
        [" first", " second ", " third"],
    )

    # 偽陽性の反例（F1 反例 1）: 文字列リテラル内の `selftest-wiring-ok:` 風の文字列を
    # コメントとして拾わない（fail-open の再発防止）
    comments_str = extract_comments(
        'const RE = /^(?:https?):\\/\\//i; const msg = "selftest-wiring-ok: これはコード";\n'
    )
    check("extract_comments/string_literal_not_captured_as_comment", comments_str, [])

    # 偽陰性の反例（F1 反例 2・本 Issue の核心）: 正規表現リテラル内部に `/*` が現れても
    # ブロックコメント開始と誤認せず、その後ろの本物の行コメントを正しく抽出できる
    comments_regex_then_comment = extract_comments(
        "const SEP_RE = /[/*]/;\n// selftest-wiring-ok: 理由\n"
    )
    check(
        "extract_comments/regex_literal_with_slash_star_does_not_swallow_later_comment",
        comments_regex_then_comment,
        [" selftest-wiring-ok: 理由"],
    )

    # 同型の反例（別の正規表現リテラル）: `/['"]/g` のようなクォート文字クラスでも同様
    comments_quote_class_then_comment = extract_comments(
        "const QUOTE_RE = /['\"]/g;\n// selftest-wiring-ok: 別の理由\n"
    )
    check(
        "extract_comments/regex_literal_with_quote_class_does_not_swallow_later_comment",
        comments_quote_class_then_comment,
        [" selftest-wiring-ok: 別の理由"],
    )

    # ネストしたテンプレートリテラル（URL の `//` を含む）が破綻しないこと（F1 要件）。
    # 内側のバッククォート・URL はコメントとして誤抽出されず、後続の本物のコメントだけを返す。
    nested_template_src = "const s = `outer ${`http://example.com`} end`\n// after\n"
    comments_nested_template = extract_comments(nested_template_src)
    check(
        "extract_comments/nested_template_literal_does_not_break",
        comments_nested_template,
        [" after"],
    )

    # 未終端のブロックコメント → 解析失敗として None
    check(
        "extract_comments/unterminated_block_comment_returns_none",
        extract_comments("/* not closed\nfoo()\n"),
        None,
    )
    # 未終端の単一行文字列（改行までに閉じない）→ 解析失敗として None
    check(
        "extract_comments/unterminated_single_line_string_returns_none",
        extract_comments('const s = "not closed\nfoo()\n'),
        None,
    )
    # 未終端のテンプレートリテラル → 解析失敗として None
    check(
        "extract_comments/unterminated_template_literal_returns_none",
        extract_comments("const s = `not closed\nfoo()\n"),
        None,
    )

    if failures:
        print("❌ ts_source --self-test FAILED")
        print("\n".join(failures))
        return 1
    print("✅ ts_source --self-test PASSED（extract_comments 追加分を含む）")
    return 0


def main() -> int:
    if "--self-test" in sys.argv[1:]:
        return _run_self_test()
    print(
        "ts_source.py は tools/check_*.py から import して使う共通ライブラリです。"
        " 単体では --self-test のみ受け付けます。"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
