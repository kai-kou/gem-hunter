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


def _find_matching_paren(text: str, open_idx: int) -> int:
    """`text[open_idx] == '('` として、対応する `)` の直後のインデックスを返す。

    クォート（`'` `"` `` ` ``）の中の括弧は数えない。中に現れる `{` `}` はそもそも
    数えない（分割代入パラメータ・デフォルト値のオブジェクトリテラルはそれ自身で完結して
    おり、外側の `(` `)` の対応関係を崩さないため、無視してよい）。対応する `)` が
    見つからない場合は `len(text)` を返す。
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
                return i
            continue
        i += 1
    return n


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

    if failures:
        print("❌ ts_source --self-test FAILED")
        print("\n".join(failures))
        return 1
    print("✅ ts_source --self-test PASSED（33 ケース）")
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
