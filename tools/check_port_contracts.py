#!/usr/bin/env python3
"""check_port_contracts.py — ポートの JSDoc 契約（値域・異常時の振る舞い）を機械検査する（Issue #800）。

`docs/rules/architecture-rules.md` §1.6 は「`src/domain/ports/*.ts` の各メソッドには
① 引数の値域 ② 値域違反・異常時の振る舞い（throw するのか、フォールバックするのか）を
JSDoc に書く」と定めるが、これを検査する機械的な手段が無かった（Issue #67 / #92 で 2 回、
この空白が実際に実装の欠陥を生んでいる）。本ツールはこの規律を機械検査する。

検査対象: `src/domain/ports/*.ts` の各 `export interface *Port` のメソッドシグネチャ。

検査項目:
  1. 各メソッドに JSDoc コメントブロック（`/** ... */`）が存在する（ハード必須）。
  2. **JSDoc が存在すれば常に**、メソッドが値域を持ちうる素の primitive 型引数
     （`string` / `number` / `boolean` / `bigint` の完全一致。配列・ジェネリック・値オブジェクト・
     `interface`/`type` は対象外＝それ自身の型定義側で値域を表現する設計のため）を取る場合、
     JSDoc に値域の記述がある（「値域」「正の有限数」「空でない」「有効な」「範囲」のいずれかを
     含む本文行。`@param <name>` の説明部分に書かれていてもよい）。
     🔴 **Issue #1071 是正**: 旧実装は `@param` タグの **存在だけ** を許容条件に含んでおり、
     `@param value 値。` のように値域を一切説明しない空疎な `@param` でも item2 を満たした
     ことになる fail-open が実測された（primitive 引数を取るメソッドは何らかの `@param` を
     書くのが自然なため、この一致条件があるだけで item2 は事実上ほぼ常に PASS していた）。
     `@param` 単体は不採用にし、値域を表す具体キーワードの有無で判定する。
     🔴 **PR #1074 是正**: 上記の「本文行」は JSDoc **全文**ではなく、対象引数に対応する
     `@param <name>` の説明範囲（またはタグを使わない本文＝preamble）に限定する。旧実装は
     JSDoc 全文への部分一致だったため、`@returns` や `@throws`、無関係な別の `@param` の
     説明に値域っぽい語が出現しただけで item2 が PASS する fail-open が実測された。
  3. **JSDoc が存在すれば常に**、JSDoc に異常時の振る舞いの記述がある（`@throws`、
     「フォールバック」「例外」「fail-open」のいずれかを含む本文行、「例外を投げ」
     「例外を送出」「エラーを投げ」「エラーを送出」のいずれかのフレーズ、または
     語境界つきの「throw」（`throw away` のような無関係な熟語は除く）を含む本文行）。
     🔴 **PR #1070 是正**: 旧実装は「投げ」「送出」「throw」を **語境界なしの部分一致** で
     採用しており、`ask()` の「質問を投げかける」・`send()` の「リクエストを送出する」・
     英語 doc の "do not throw away user data" のように **異常時の振る舞いと無関係な文** が
     item3 を満たしたことになる fail-open が実測された。「例外」「エラー」を伴わない裸の
     「投げ」「送出」、および `throw away` を拾う裸の「throw」は採用しない。

🔴 **「substantial」ゲート（1 行 JSDoc は item2/3 を免除する）は廃止した（Issue #800 の
運用で fail-open と判明・再設計）**: 1 行 `/** ...する。 */` を「値域・異常時の振る舞いを
意図的に省いたトリビアルな一言メソッド」と区別なく免除すると、新規ポートを 1 行 doc で
追加するだけで item2/item3 が永久に課されない穴になる（実測: `AuthPort.exchangeAuthorizationCode`
/ `RepositoryQueryPort.search` / `RepositoryQueryPort.findDetail` の 3 件が現存コードで
この穴に落ちていた）。1 行かどうかは「トリビアルさ」の証拠にならないため、JSDoc の有無
（item1）だけを免除条件にし、存在すれば行数・タグ有無に関わらず item2/item3 を常に課す。
真にトリビアルで契約を書く必要が無いメソッドは `// contract-ok` で個別に抑止する
（レビュー済みの明示的な判断を残す・#800 冒頭の抑止コメント仕様と同じ運用）。

抑止コメント: `// contract-ok`（メソッドのシグネチャ行、その前後の行、または JSDoc 本文中）が
あれば item 2 / item 3 の検査をそのメソッドに限り抑止する（item 1 = JSDoc の存在は抑止しない・
`tools/check_datetime_tz.py` の `# tz-ok` と同じ作法）。🔴 **PR #1070 是正**: 「前後の行」は
**他のメソッドのシグネチャ・スパンに属する行を含まない**（旧実装は隣接メソッドのマーカーが
漏れて誤抑止する fail-open があった。抽出済みメソッドのスパンと突き合わせて弾く）。

検査対象の構文は TS のメソッドショートハンド（`foo(x: number): void`）と、プロパティ関数型
（`foo: (x: number) => void`）の両方をカバーする（🔴 **PR #1070 是正**: 旧実装はメソッド
ショートハンドにしか一致せず、プロパティ関数型で宣言されたメソッドが検査対象から丸ごと
消えていた＝新規ポートをこの構文で追加すると検査が無効化される穴だった）。

終了コード:
  0 = 違反なし（対象ファイルが 1 件以上あり、実際に検査した）
  1 = 違反あり、または一部ファイルが解析不能（parse failure を「違反なし」に丸めない）
  2 = 判定不能（`src/domain/ports/*.ts` が 1 件も見つからない＝対象選択が壊れている可能性・
      fail-closed。`docs/rules/check-tool-design-rules.md` §2）

使い方:
  python3 tools/check_port_contracts.py             # src/domain/ports/*.ts を検査
  python3 tools/check_port_contracts.py --self-test  # ネットワーク非依存のユニットテスト
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ts_source import find_matching_brace, find_matching_paren, strip_comments  # noqa: E402

PORTS_GLOB = "src/domain/ports/*.ts"

CONTRACT_OK_MARKER = "contract-ok"

# item 2（値域）: 以下のキーワードを含む本文行（`@param` 行の説明部分に書かれていてもよい）。
# 🔴 **Issue #1071 是正**: 旧実装は `@param` タグの **存在だけ** を許容条件に含んでおり、
# `@param value 値。` のように値域を一切説明しない空疎な `@param` でも item2 を満たしたことに
# なる fail-open が実測された（primitive 引数を取るメソッドは何らかの `@param` を書くのが
# 自然なため、この一致条件があるだけで item2 は事実上ほぼ常に PASS していた）。`@param` 単体を
# 外し、値域を表す具体キーワードが本文（`@param` の説明部分を含む）に現れることを要求する。
ITEM2_KEYWORDS = ("値域", "正の有限数", "空でない", "有効な", "範囲")

# item 3（異常時の振る舞い）: @throws、または以下のキーワード（ASCII は大文字小文字を無視）。
# 🔴 **PR #1070 是正**: 「投げ」「送出」を裸の部分一致キーワードとして採用しない（「質問を
# 投げかける」「リクエストを送出する」のように異常時の振る舞いと無関係な文でも item3 を
# 満たしたことになる fail-open が実測された）。代わりに「例外」「エラー」を主語に伴う
# フレーズ（`_ITEM3_PHRASE_RE`）としてのみ採用する。「例外」自体は単独キーワードとして残す
# （「例外にせず null を返す」等、動詞が「投げる」「送出する」以外の表現形もあるため）。
ITEM3_KEYWORDS_JP = ("@throws", "フォールバック", "例外", "fail-open")
# 🔴 **PR #1070 是正**: 「例外を投げ」「例外を送出」「エラーを投げ」「エラーを送出」の
# フレーズ一致（「例外」「エラー」を伴わない裸の「投げ」「送出」は不採用）。
_ITEM3_PHRASE_RE = re.compile(r"(?:例外|エラー)を(?:投げ|送出)")
# 🔴 **PR #1070 是正**: 裸の "throw" 部分一致は "throw away"（無関係な熟語）を拾ってしまう
# ため、語境界つき・"throw away" を除外する正規表現に置き換える（大文字小文字は無視）。
_ITEM3_THROW_EN_RE = re.compile(r"\bthrow\b(?!\s+away)")

PRIMITIVE_TYPES = {"string", "number", "boolean", "bigint"}

IFACE_RE = re.compile(r"export\s+interface\s+(\w+Port)\b[^{]*\{")
# メソッドショートハンド構文: `foo(x: number): void` / `readonly foo(): void`
METHOD_RE = re.compile(r"^\s*(?:readonly\s+)?([A-Za-z_$][\w$]*)\s*\??\s*(?:<[^>]*>)?\s*\(")
# 🔴 **PR #1070 是正（CRITICAL 3）**: プロパティ関数型構文
# `foo: (x: number) => void` / `readonly foo?: (x: number) => void` も検査対象に含める
# （TS ではどちらの構文も合法かつ一般的で、METHOD_RE だけでは新規ポートをこの構文で
# 追加すると検査が丸ごと無効化される穴になっていた）。
PROPERTY_METHOD_RE = re.compile(
    r"^\s*(?:readonly\s+)?([A-Za-z_$][\w$]*)\s*\??\s*:\s*(?:<[^>]*>\s*)?\("
)

# 括弧の対応で使う開閉文字（<> は比較演算子との曖昧さがあるため意図的に数えない）。
_OPEN_CHARS = "({["
_CLOSE_CHARS = ")}]"


class ScanError(Exception):
    """ファイル読み込み・構造解析に失敗したことを表す（#445 の naive datetime 検査と同じ扱い）。

    黙って「違反なし」に丸めない（fail-closed）。呼び出し側で捕捉し、非ゼロ終了へ反映する。
    """


@dataclass(frozen=True)
class MethodInfo:
    """検査対象の 1 メソッド。"""

    interface_name: str
    method_name: str
    line: int  # 1-indexed（メソッドシグネチャ開始行）
    jsdoc_text: str | None  # None なら JSDoc なし
    has_primitive_param: bool
    primitive_param_names: tuple[str, ...]  # item2 の @param 名対応付けに使う（PR #1074 是正）
    suppressed: bool  # contract-ok マーカーの有無


def _net_delta(line: str, quote: str | None = None) -> tuple[int, str | None]:
    """`(){}[]` の深さ変化を返す（文字列・テンプレートリテラルの中身は数えない・W2 是正）。

    🔴 **PR #1070 是正（WARNING 2）**: 旧実装は生テキストをそのまま数えており、
    `readonly kind: '{' | '}'` のような文字列リテラル型に含まれる `{` `}` を実際の
    ネスト構造の開閉と誤認していた（後続メソッドの取りこぼし＝fail-open、あるいは
    誤検出＝fail-closed のいずれにも転びうる）。`quote` は直前の行から継続している
    クォート種別（呼び出し元がループで引き回す）。戻り値は `(net_delta, 行末時点のクォート状態)`。
    """
    delta = 0
    i, n = 0, len(line)
    while i < n:
        ch = line[i]
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
        if ch in _OPEN_CHARS:
            delta += 1
        elif ch in _CLOSE_CHARS:
            delta -= 1
        i += 1
    return delta, quote


def _split_top_level(text: str, sep: str = ",") -> list[str]:
    """`(){}[]` に加え `<>` の深さも数えないトップレベル区切りで分割する。

    🔴 **PR #1070 是正（WARNING 1）**: 呼び出し元（メソッド境界の走査）が意図的に `<>` を
    数えない設計（比較演算子との曖昧さ）とは別の関心事。ここは「既に括弧の対応で切り出し
    済みのパラメータリスト文字列」を対象にパラメータ境界（トップレベルのカンマ）を探すだけ
    なので、`Record<string, unknown>` のようなジェネリック型引数のカンマを誤ってパラメータの
    区切りとして扱わないよう `<` `>` も深さに含める。アロー関数の `=>` に含まれる `>` は
    ジェネリックの閉じではないため、直前の文字が `=` のときは深さを減らさない。
    """
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    prev_ch = ""
    for ch in text:
        if ch in _OPEN_CHARS or ch == "<":
            depth += 1
        elif ch in _CLOSE_CHARS:
            depth = max(0, depth - 1)
        elif ch == ">":
            if prev_ch != "=":
                depth = max(0, depth - 1)
        if ch == sep and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
        prev_ch = ch
    tail = "".join(current)
    if tail.strip():
        parts.append(tail)
    return [p for p in parts if p.strip()]


def _param_types(param_list_text: str) -> list[str]:
    """パラメータリストの生テキスト（丸括弧の中身）から各パラメータの型注釈を抽出する。

    型注釈が無い（デフォルト値のみ等）パラメータは空文字列を返す（primitive 判定では
    非一致として扱われるため安全側）。
    """
    types: list[str] = []
    for raw_param in _split_top_level(param_list_text):
        # デフォルト値（トップレベル `=`）を落とす。
        no_default = _split_top_level(raw_param, sep="=")[0] if "=" in raw_param else raw_param
        if ":" not in no_default:
            types.append("")
            continue
        # 最初のトップレベル `:` で分割（型注釈内のネストした `:` は無視してよい想定）。
        _, _, type_text = no_default.partition(":")
        types.append(type_text.strip())
    return types


_SIMPLE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_$][\w$]*$")


def _param_names_and_types(param_list_text: str) -> list[tuple[str, str]]:
    """パラメータリストの生テキストから `(パラメータ名, 型注釈)` のペア一覧を返す。

    🔴 **PR #1074 是正（item2 の @param 名対応付けに使う）**: `_param_types` は型だけを返すため
    「値域キーワードがどの @param に対応するか」を判定できない。分割代入パターン
    （`{ headers }: T`）のように単純な識別子でない名前は空文字列にする（呼び出し側は
    名前が空のものをどの `@param` とも対応させない＝安全側）。
    """
    pairs: list[tuple[str, str]] = []
    for raw_param in _split_top_level(param_list_text):
        no_default = _split_top_level(raw_param, sep="=")[0] if "=" in raw_param else raw_param
        no_default = no_default.strip()
        if ":" not in no_default:
            name_candidate = no_default.rstrip("?").strip()
            name = name_candidate if _SIMPLE_IDENTIFIER_RE.match(name_candidate) else ""
            pairs.append((name, ""))
            continue
        name_part, _, type_text = no_default.partition(":")
        name_candidate = name_part.strip().rstrip("?").strip()
        name = name_candidate if _SIMPLE_IDENTIFIER_RE.match(name_candidate) else ""
        pairs.append((name, type_text.strip()))
    return pairs


def _primitive_param_names(param_list_text: str) -> tuple[str, ...]:
    """primitive 型を持つパラメータの名前一覧を返す（名前が単純識別子でないものは含まない）。"""
    return tuple(
        name for name, t in _param_names_and_types(param_list_text) if name and t in PRIMITIVE_TYPES
    )


def _has_primitive_param(param_list_text: str) -> bool:
    return bool(_primitive_param_names(param_list_text))


def _has_any_param(param_list_text: str) -> bool:
    return bool(param_list_text.strip())


def _contains_marker(text: str, marker: str) -> bool:
    return marker in text


def _find_jsdoc(raw_lines: list[str], method_line: int, body_start_line: int) -> str | None:
    """メソッド開始行に付随する JSDoc テキストを探す（見つからなければ None）。

    1. 同一行の先頭に `/** ... */` があればそれを使う（インライン形式）。
    2. それ以外は、直前の空行を読み飛ばして最初に見つかる非空行が `*/` で終わっていれば、
       そこから遡って `/**` で始まる行までを JSDoc ブロックとして結合する。
    """
    raw_method_line = raw_lines[method_line - 1]
    inline_match = re.match(r"^\s*(/\*\*.*?\*/)", raw_method_line)
    if inline_match:
        return inline_match.group(1)

    i = method_line - 1
    while i >= body_start_line and raw_lines[i - 1].strip() == "":
        i -= 1
    if i < body_start_line:
        return None
    end_line = i
    if not raw_lines[end_line - 1].strip().endswith("*/"):
        return None

    start_line = end_line
    while start_line >= body_start_line and not raw_lines[start_line - 1].strip().startswith("/**"):
        start_line -= 1
    if start_line < body_start_line:
        return None

    return "\n".join(raw_lines[start_line - 1 : end_line])


# item2 を「対象引数に対応する @param の説明範囲」に限定するためのタグ分割（PR #1074 是正）。
# 🔴 **CRITICAL 是正の背景**: 旧実装は `kw in jsdoc_text` で JSDoc **全文**（`@returns` /
# `@throws` / 無関係な別の `@param` の説明を含む）を対象にしていたため、値域キーワードが
# 対象引数の説明とは無関係な箇所に出現しただけで item2 が PASS する fail-open があった
# （実測: `@returns` に「有効な範囲の…」とだけ書かれた `FooPort.foo` が誤って PASS した）。
_JSDOC_TAG_RE = re.compile(r"@(\w+)")
_JSDOC_PARAM_NAME_RE = re.compile(r"@param\s*(?:\{[^}]*\}\s*)?(\[?[A-Za-z_$][\w$]*\]?)")


def _jsdoc_sections(jsdoc_text: str) -> tuple[str, list[tuple[str, str]]]:
    """JSDoc 本文を `(preamble, [(タグ名, セクション本文), ...])` に分割する。

    `@` タグが 1 つも無ければ `(jsdoc_text 全体, [])` を返す（`@param` を使わず本文に
    値域を書くスタイル・既存 self-test ケース 34/35 を引き続き通すための経路）。
    各タグのセクション本文は、そのタグの開始位置から次の `@タグ` の直前まで（末尾のタグは
    JSDoc 終端まで）。継続行（インデントされた次行）は自然にこのセクションへ含まれる。
    """
    tag_matches = list(_JSDOC_TAG_RE.finditer(jsdoc_text))
    if not tag_matches:
        return jsdoc_text, []
    preamble = jsdoc_text[: tag_matches[0].start()]
    sections: list[tuple[str, str]] = []
    for idx, tm in enumerate(tag_matches):
        start = tm.start()
        end = tag_matches[idx + 1].start() if idx + 1 < len(tag_matches) else len(jsdoc_text)
        sections.append((tm.group(1), jsdoc_text[start:end]))
    return preamble, sections


def _contains_item2_keyword(jsdoc_text: str, primitive_param_names: tuple[str, ...]) -> bool:
    """item2（値域の記述）を、対象引数に対応する `@param` の説明範囲に限定して判定する。

    判定対象:
      - `@` タグの外側にある本文（preamble。`@param` を使わないスタイルの経路）。
      - `primitive_param_names` のいずれかと名前が一致する `@param` セクションの本文。
    `@returns` / `@throws` / 名前が一致しない別の `@param` のセクションは対象外
    （PR #1074 是正・fail-open の再発防止）。
    """
    preamble, sections = _jsdoc_sections(jsdoc_text)
    if any(kw in preamble for kw in ITEM2_KEYWORDS):
        return True
    for tag_name, section_text in sections:
        if tag_name != "param":
            continue
        name_m = _JSDOC_PARAM_NAME_RE.match(section_text)
        if not name_m:
            continue
        raw_name = name_m.group(1).strip("[]")
        if raw_name not in primitive_param_names:
            continue
        if any(kw in section_text for kw in ITEM2_KEYWORDS):
            return True
    return False


def _contains_item3_keyword(jsdoc_text: str) -> bool:
    if any(kw in jsdoc_text for kw in ITEM3_KEYWORDS_JP):
        return True
    if _ITEM3_PHRASE_RE.search(jsdoc_text):
        return True
    return bool(_ITEM3_THROW_EN_RE.search(jsdoc_text.lower()))


def extract_methods(source: str) -> list[MethodInfo]:
    """ソース全体（1 ファイル分）から `export interface *Port` の各メソッドを抽出する。

    見逃し経路への配慮:
      - `export interface` に一致する行が 0 件でも例外にせず空リストを返す（呼び出し元が
        「対象 0 件」を集計する）。
      - メソッドシグネチャが複数行にまたがっても（開き括弧の対応が閉じるまで）1 メソッドとして扱う。
      - ネストしたオブジェクト型の中のメソッド様シグネチャ（例:
        `foo(opts: { bar(): void }): void` のように行が分かれるケース）を、深さ 0 のときだけ
        メソッドとして扱うことで誤って独立メソッド扱いしない（境界の外側の負ケース）。
      - メソッドショートハンド（`foo(): void`）とプロパティ関数型（`foo: () => void`）の
        両方を検査対象とする（PR #1070 CRITICAL 3 是正）。
      - 括弧・波括弧・角括弧の深さは文字列・テンプレートリテラルの中身を数えない
        （PR #1070 WARNING 2 是正）。

    2 フェーズで抽出する（PR #1070 CRITICAL 1 是正）:
      Phase 1: 各メソッドの位置（開始行・終了行）とシグネチャ・JSDoc を収集する
               （`// contract-ok` の抑止判定はまだ行わない）。
      Phase 2: 収集済みの全メソッドのスパン一覧と突き合わせ、「メソッド開始行の直前 1 行」
               「終了行の直後 1 行」が **他のメソッドのスパンに属していない場合に限り**
               neighbor として抑止マーカーを探す。旧実装は無条件に neighbor 扱いしており、
               隣接するメソッドに書かれた `// contract-ok` が自分の抑止に漏れる fail-open が
               実測された（例: `b()` と `c() // contract-ok` が隣接すると `b()` まで抑止される）。
    """
    stripped = strip_comments(source)
    raw_lines = source.splitlines()
    stripped_lines = stripped.splitlines()
    if len(raw_lines) != len(stripped_lines):
        # strip_comments は行数を保存する契約（ts_source.py docstring）。崩れたら判定不能。
        raise ScanError("strip_comments の行数がソースと一致しない（内部矛盾）")

    # --- Phase 1: 位置・シグネチャ・JSDoc の収集（抑止判定は後回し） ---
    raw_entries: list[dict] = []
    for m in IFACE_RE.finditer(stripped):
        iface_name = m.group(1)
        brace_open_idx = m.end() - 1
        brace_close_idx = find_matching_brace(stripped, brace_open_idx)
        open_line = stripped.count("\n", 0, brace_open_idx) + 1
        close_line = stripped.count("\n", 0, min(brace_close_idx, len(stripped))) + 1
        body_start_line = open_line + 1
        body_end_line = close_line - 1  # inclusive
        if body_end_line < body_start_line:
            continue

        depth = 0
        quote_state: str | None = None
        i = body_start_line
        while i <= body_end_line:
            line = stripped_lines[i - 1]
            if depth == 0:
                mm = METHOD_RE.match(line) or PROPERTY_METHOD_RE.match(line)
                if mm:
                    method_name = mm.group(1)
                    start_line = i
                    # メソッドシグネチャの終端（括弧の対応が閉じる行）まで消費する。
                    span_depth, quote_state = _net_delta(line, quote_state)
                    end_line = start_line
                    while span_depth > 0 and end_line < body_end_line:
                        end_line += 1
                        d, quote_state = _net_delta(stripped_lines[end_line - 1], quote_state)
                        span_depth += d
                    sig_stripped = "\n".join(stripped_lines[start_line - 1 : end_line])
                    open_paren = sig_stripped.find("(")
                    if open_paren != -1:
                        close_paren = find_matching_paren(sig_stripped, open_paren)
                        if close_paren == -1:
                            # PR #1070 CRITICAL 4 是正: 「見つからない」を「末尾から 1 文字
                            # 除いた範囲」という別の意味に化けさせず、fail-closed で判定不能に倒す。
                            raise ScanError(
                                f"{iface_name}.{method_name}()（{start_line} 行目）: "
                                "パラメータリストの閉じ括弧が見つからない（構文解析失敗）"
                            )
                        param_list_text = sig_stripped[open_paren + 1 : close_paren]
                    else:
                        param_list_text = ""

                    jsdoc_text = _find_jsdoc(raw_lines, start_line, body_start_line)
                    sig_raw = "\n".join(raw_lines[start_line - 1 : end_line])

                    raw_entries.append(
                        {
                            "interface_name": iface_name,
                            "method_name": method_name,
                            "start_line": start_line,
                            "end_line": end_line,
                            "jsdoc_text": jsdoc_text,
                            "has_primitive_param": _has_primitive_param(param_list_text),
                            "primitive_param_names": _primitive_param_names(param_list_text),
                            "sig_raw": sig_raw,
                        }
                    )
                    i = end_line + 1
                    continue
            d, quote_state = _net_delta(line, quote_state)
            depth += d
            i += 1

    # --- Phase 2: 他メソッドのスパンを避けた neighbor 判定で抑止マーカーを確定する ---
    spans = [(e["start_line"], e["end_line"]) for e in raw_entries]

    def _line_in_other_span(line_no: int, self_idx: int) -> bool:
        return any(
            idx != self_idx and s <= line_no <= e for idx, (s, e) in enumerate(spans)
        )

    methods: list[MethodInfo] = []
    for idx, e in enumerate(raw_entries):
        start_line = e["start_line"]
        end_line = e["end_line"]
        jsdoc_text = e["jsdoc_text"]
        neighbor_lines: list[str] = []
        before_ln = start_line - 1
        after_ln = end_line + 1
        if before_ln >= 1 and not _line_in_other_span(before_ln, idx):
            neighbor_lines.append(raw_lines[before_ln - 1])
        if after_ln <= len(raw_lines) and not _line_in_other_span(after_ln, idx):
            neighbor_lines.append(raw_lines[after_ln - 1])
        suppressed = _contains_marker(e["sig_raw"], CONTRACT_OK_MARKER) or any(
            CONTRACT_OK_MARKER in nl for nl in neighbor_lines
        ) or (jsdoc_text is not None and CONTRACT_OK_MARKER in jsdoc_text)

        methods.append(
            MethodInfo(
                interface_name=e["interface_name"],
                method_name=e["method_name"],
                line=start_line,
                jsdoc_text=jsdoc_text,
                has_primitive_param=e["has_primitive_param"],
                primitive_param_names=e["primitive_param_names"],
                suppressed=suppressed,
            )
        )
    return methods


def check_methods(methods: list[MethodInfo]) -> list[str]:
    """抽出済みメソッド一覧を検査し、違反メッセージのリストを返す（行番号昇順）。"""
    violations: list[str] = []
    for meth in methods:
        label = f"{meth.interface_name}.{meth.method_name}()"
        if meth.jsdoc_text is None:
            violations.append(f"{meth.line}: {label}: JSDoc コメントが存在しない（item 1）")
            continue
        if meth.suppressed:
            continue
        if meth.has_primitive_param and not _contains_item2_keyword(
            meth.jsdoc_text, meth.primitive_param_names
        ):
            violations.append(
                f"{meth.line}: {label}: primitive 型引数を取るが値域の記述が JSDoc に無い"
                "（item 2・『値域』『正の有限数』『空でない』等のキーワードが本文に必要。"
                "『@param』タグの存在だけでは満たさない）"
            )
        if not _contains_item3_keyword(meth.jsdoc_text):
            violations.append(
                f"{meth.line}: {label}: 異常時の振る舞いの記述が JSDoc に無い"
                "（item 3・@throws または『throw』『fail-open』『フォールバック』等のキーワードが必要）"
            )
    return violations


def _port_files() -> list[Path]:
    # 🔴 **PR #1070 是正（WARNING 3）**: `PORTS_GLOB` は `*.test.ts` も拾ってしまう
    # （実測: `cache-port.test.ts` が走査対象に含まれていた）。テストファイル内のモック用
    # `export interface FakeXPort` を検査対象外にする（無関係な CI 失敗を防ぐ）。
    return sorted(p for p in REPO_ROOT.glob(PORTS_GLOB) if not p.name.endswith(".test.ts"))


def scan_file(path: Path) -> list[str]:
    try:
        source = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as e:
        raise ScanError(f"{path}: 読み込みに失敗（{e.__class__.__name__}: {e}）") from e
    methods = extract_methods(source)
    return check_methods(methods)


def _run(files: list[Path], root: Path) -> int:
    if not files:
        print(
            f"⚠️ {PORTS_GLOB} に一致するファイルが 1 件もありません。対象選択が壊れている"
            "可能性があるため判定不能として非ゼロ終了します（fail-closed・#800）。",
            file=sys.stderr,
        )
        return 2

    total_violations = 0
    parse_failures = 0
    for f in files:
        rel = f.relative_to(root) if f.is_absolute() else f
        try:
            violations = scan_file(f)
        except ScanError as e:
            parse_failures += 1
            print(f"⚠️ {rel}: 解析不能のため検査対象外（{e}）", file=sys.stderr)
            continue
        for v in violations:
            total_violations += 1
            print(f"{rel}:{v}")

    if total_violations:
        print(
            f"\n❌ {total_violations} 件のポート契約違反を検出（{len(files)} ファイル走査）。"
            "\n   docs/rules/architecture-rules.md §1.6 に従い、引数の値域・異常時の振る舞いを"
            "JSDoc へ書く。レビュー済みの正当な例外は `// contract-ok` で抑止できる。",
            file=sys.stderr,
        )
    if parse_failures:
        print(
            f"\n⚠️ {parse_failures} 件のファイルを解析できず検査不能（{len(files)} ファイル走査）。"
            "解析不能は「違反なし」ではないため PASS にしない。",
            file=sys.stderr,
        )
    if total_violations or parse_failures:
        return 1
    print(f"✅ ポート契約違反は検出なし（{len(files)} ファイル走査）。")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return run_self_test()
    return _run(_port_files(), REPO_ROOT)


# ---------------------------------------------------------------------------
# self-test
# ---------------------------------------------------------------------------


def run_self_test() -> int:
    failures: list[str] = []

    def check_extract(name: str, source: str, expect_count: int) -> list[MethodInfo]:
        methods = extract_methods(source)
        if len(methods) != expect_count:
            failures.append(
                f"- {name}: メソッド数 expected {expect_count}, got {len(methods)} "
                f"({[m.method_name for m in methods]})"
            )
        return methods

    def check_violations(name: str, source: str, expect_violation_count: int) -> list[str]:
        methods = extract_methods(source)
        violations = check_methods(methods)
        if len(violations) != expect_violation_count:
            failures.append(
                f"- {name}: 違反数 expected {expect_violation_count}, got "
                f"{len(violations)} ({violations})"
            )
        return violations

    # --- 1. 完全に契約が書かれたメソッド → 違反 0 ---
    src_ok = """
export interface SamplePort {
  /**
   * サンプルを消費する。
   *
   * @param key 判定単位の識別子（正の有限数のみ許可）。
   * @returns 何か。
   *
   * 🔴 異常時の振る舞い: throw する（不正値は RangeError）。
   */
  consume(key: number): Promise<void>
}
"""
    check_violations("1. 完全な契約は違反0", src_ok, 0)

    # --- 2. JSDoc が全く無い（item1 違反） ---
    src_no_doc = """
export interface SamplePort {
  consume(key: number): Promise<void>
}
"""
    check_violations("2. JSDocなし→item1違反", src_no_doc, 1)

    # --- 3. substantial だが primitive 引数の値域記述が無い（item2 違反） ---
    src_no_domain = """
export interface SamplePort {
  /**
   * サンプルを消費する。
   *
   * @returns 何か。
   *
   * 🔴 異常時の振る舞い: throw する。
   */
  consume(key: number): Promise<void>
}
"""
    check_violations("3. 値域記述なし→item2違反", src_no_domain, 1)

    # --- 4. #92 再現: RateLimitPort.consume 相当から異常時の振る舞い段落を削った入力 ---
    src_rate_limit_full = """
export interface RateLimitPort {
  /**
   * 1 リクエスト分を消費して可否を返す。
   *
   * @param key 判定単位の識別子（空でない文字列）。
   * @returns 許可なら allowed:true。
   *
   * 🔴 異常時の振る舞い（fail-open・throw しない）: binding が未提供 / reject / throw
   * した場合でも allowed:true を返す。
   */
  consume(key: string): Promise<{ allowed: boolean }>
}
"""
    check_violations("4a. #92 修正後（fail-open記述あり）→違反0", src_rate_limit_full, 0)

    src_rate_limit_mutated = """
export interface RateLimitPort {
  /**
   * 1 リクエスト分を消費して可否を返す。
   *
   * @param key 判定単位の識別子（空でない文字列）。
   * @returns 許可なら allowed:true。
   */
  consume(key: string): Promise<{ allowed: boolean }>
}
"""
    check_violations(
        "4b. #92 再現（fail-open記述を削除）→item3違反を検知する", src_rate_limit_mutated, 1
    )

    # --- 5. 回帰ガード（#800 fail-open 是正）: thin（1 行）JSDoc + primitive 引数、
    #        値域/異常時記述なしは item2 と item3 の両方に違反する（旧実装は `_is_substantial`
    #        ゲートで 1 行 JSDoc を丸ごとスキップし違反 0 にしていた＝新規ポートを 1 行 doc で
    #        追加すれば item2/3 が永久に課されない穴だった。実測: `AuthPort.
    #        exchangeAuthorizationCode` 等が旧実装ではこの経路で検査をすり抜けていた）。
    #        thin かどうかで免除しないことを固定するのが本ケースの目的（`_is_substantial`
    #        相当のスキップを復活させる変異で本ケースが FAIL することを変異テストで確認する）。
    src_thin = """
export interface SamplePort {
  /** 何かをする。 */
  doThing(x: number): void
}
"""
    check_violations("5. thinでもitem2/3を免除しない→違反2（item2+item3）", src_thin, 2)

    # --- 6. contract-ok マーカーで item2/3 を抑止する ---
    src_contract_ok = """
export interface SamplePort {
  /**
   * サンプルを消費する。
   *
   * @returns 何か。
   */
  consume(key: number): Promise<void> // contract-ok: レビュー済み・契約詳細は省略
}
"""
    check_violations("6. contract-okマーカーでitem2/3抑止→違反0", src_contract_ok, 0)

    # --- 7. 境界の外側の負ケース: ネストしたオブジェクト型内のメソッド様シグネチャを
    #        独立メソッドとして誤検出しない（複数行に分かれるケース） ---
    src_nested = """
export interface SamplePort {
  /**
   * サンプル。
   *
   * @param opts 何か。
   * @returns 何か。
   *
   * 🔴 異常時の振る舞い: throw する。
   */
  foo(opts: {
    bar(): void
  }): void
}
"""
    check_extract("7a. ネストしたメソッド様シグネチャを二重検出しない", src_nested, 1)
    check_violations("7b. 同上（違反0のまま）", src_nested, 0)

    # --- 7c. 同一行に埋め込まれたネストケース（バリアント展開） ---
    src_nested_inline = """
export interface SamplePort {
  /**
   * サンプル。
   *
   * @param opts 何か。
   *
   * 🔴 異常時の振る舞い: throw する。
   */
  foo(opts: { bar(): void }): void
}
"""
    check_extract("7c. 同一行ネストも1メソッドとして扱う", src_nested_inline, 1)

    # --- 7d. depth ゲート専用の負ケース: メソッドではないプロパティ（`(` が識別子直後に
    #        来ないため METHOD_RE 自体が非一致）の中にネストしたメソッド様の行がある場合、
    #        その行を独立メソッドとして誤検出しない。7a/7c は「メソッドの span 消費」で
    #        たまたり隠れてしまうため、depth==0 ゲートの実効性そのものは検証できない
    #        （変異テストで確認済み・#800 完了条件）。本ケースはプロパティ側が METHOD_RE に
    #        一致しないので span 消費に頼れず、depth ゲートが無いと `bar` を誤って
    #        独立メソッドとして拾ってしまう。 ---
    src_nested_property = """
export interface SamplePort {
  /**
   * サンプル。
   *
   * @returns 何か。
   *
   * 🔴 異常時の振る舞い: throw する。
   */
  readonly opts: {
    bar(): void
  }
}
"""
    check_extract("7d. depthゲート: メソッドでないプロパティ内のネストを拾わない", src_nested_property, 0)

    # --- 8. 複数行にまたがるメソッドシグネチャ（バリアント展開） ---
    src_multiline_sig = """
export interface SamplePort {
  /**
   * サンプル検索。
   *
   * @param input 何か。
   *
   * 🔴 異常時の振る舞い: 例外を投げず空配列を返す。
   */
  search(
    input: SearchInput,
  ): Promise<SearchResult>
}
"""
    methods_ml = check_extract("8. 複数行シグネチャを1メソッドとして抽出", src_multiline_sig, 1)
    if methods_ml and methods_ml[0].method_name != "search":
        failures.append(f"- 8b. メソッド名誤り: got {methods_ml[0].method_name!r}")

    # --- 9. インライン形式の JSDoc（同一行に /** ... */ とメソッドが並ぶ・バリアント展開） ---
    src_inline_doc = """
export interface SamplePort {
  /** サンプルを消費する。@param key 正の有限数。🔴 throw する。 */ consume(key: number): void
}
"""
    check_violations("9. インライン形式JSDocも検出する→違反0", src_inline_doc, 0)

    # --- 10. 単一 `*`（非 JSDoc）ブロックコメントは JSDoc として認めない（item1 違反） ---
    src_plain_comment = """
export interface SamplePort {
  /* これは JSDoc ではない */
  consume(key: number): void
}
"""
    check_violations("10. 非JSDocブロックコメントはitem1違反", src_plain_comment, 1)

    # --- 11. 非 Port 命名のインターフェースは対象外（境界の外側の負ケース その2） ---
    src_not_port = """
export interface SampleService {
  consume(key: number): void
}
"""
    check_extract("11. Port接尾辞なしは対象外", src_not_port, 0)

    # --- 12. 非primitive（値オブジェクト）引数は item2 の対象外 ---
    src_value_object = """
export interface SamplePort {
  /**
   * 取得する。
   *
   * @returns 何か。
   *
   * 🔴 異常時の振る舞い: 例外にせず null を返す。
   */
  find(name: RepositoryFullName): Promise<Detail | null>
}
"""
    check_violations("12. 値オブジェクト引数はitem2対象外→違反0", src_value_object, 0)

    # --- _run() 統合テスト（対象0件の fail-closed・parse_failures 集計） ---
    import contextlib
    import io
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_dir:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = _run([], Path(tmp_dir))
        if code != 2:
            failures.append(f"- 13. 対象0件はexit2(fail-closed) expected, got {code}")
        if "⚠️" not in (out.getvalue() + err.getvalue()):
            failures.append("- 13b. 対象0件の出力に⚠️が含まれない")

        ok_file = Path(tmp_dir) / "ok.ts"
        ok_file.write_text(src_ok, encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = _run([ok_file], Path(tmp_dir))
        if code != 0:
            failures.append(f"- 14. 違反なしファイルはexit0 expected, got {code}")

        bad_file = Path(tmp_dir) / "bad.ts"
        bad_file.write_text(src_no_doc, encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = _run([bad_file], Path(tmp_dir))
        if code != 1:
            failures.append(f"- 15. 違反ありファイルはexit1 expected, got {code}")

        # 読み込み不能ファイル（存在しないパスを渡す＝OSError系）→ parse_failures 扱いで exit1。
        missing_file = Path(tmp_dir) / "missing.ts"
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = _run([missing_file], Path(tmp_dir))
        if code != 1:
            failures.append(f"- 16. 読み込み不能ファイルはexit1(parse_failures) expected, got {code}")
        combined = out.getvalue() + err.getvalue()
        if "解析不能" not in combined:
            failures.append(f"- 16b. 出力に『解析不能』が含まれない: {combined!r}")

    # --- 17. 実ファイル（現在の main）で本判定が緑になることを確認する（回帰の一次防衛線） ---
    real_files = _port_files()
    if real_files:
        real_violations: list[str] = []
        real_parse_errors: list[str] = []
        for f in real_files:
            try:
                real_violations.extend(scan_file(f))
            except ScanError as e:
                real_parse_errors.append(str(e))
        if real_violations or real_parse_errors:
            failures.append(
                f"- 17. 実ファイル（{PORTS_GLOB}）で違反/解析不能を検出（本来は現在の main で"
                f"緑のはず）: violations={real_violations} parse_errors={real_parse_errors}"
            )

    # --- 17b. W3 是正: `.test.ts` が _port_files() の走査対象に含まれない ---
    #         （本リポジトリには実在の `src/domain/ports/cache-port.test.ts` があり、
    #         除外できていなければ本ケースが実データで検出する）。
    if any(p.name.endswith(".test.ts") for p in real_files):
        failures.append(
            "- 17b. W3: `.test.ts` が _port_files() の走査対象から除外されていない"
            f"（{[p.name for p in real_files if p.name.endswith('.test.ts')]}）"
        )

    # --- 18. CRITICAL 1 是正: `// contract-ok` の neighbor 判定は他メソッドのスパンへ漏れない ---
    # 18a: 実測の再現入力（c の行末マーカーが b の後続 neighbor へ漏れて b まで抑止されていた）。
    src_neighbor_leak = """
export interface SamplePort {
  /** 何かする。 */
  b(y: number): void
  c(z: number): void // contract-ok: c だけ意図的に省略
}
"""
    check_violations(
        "18a. CRITICAL1: cのマーカーがbへ漏れない→合計3"
        "(b:item2+item3違反2 + c:JSDocなしitem1違反1)",
        src_neighbor_leak,
        3,
    )

    # 18b: 逆方向（b の行末マーカーが c の before-neighbor へ漏れる）。
    #      c はインライン JSDoc を自分の行に持つ（item1 で早期 continue させず item2/3 を検証するため）。
    src_neighbor_leak_reverse = """
export interface SamplePort {
  b(y: number): void // contract-ok: b だけ意図的に省略
  /** 何かする。 */ c(z: number): void
}
"""
    check_violations(
        "18b. CRITICAL1(逆方向): bのマーカーがcのbeforeへ漏れない→合計3"
        "(b:item1違反1 + c:item2/3違反2)",
        src_neighbor_leak_reverse,
        3,
    )

    # 18c: U1 陽性対照。隣接メソッドが無いときは after-neighbor の抑止が引き続き機能する
    #      （neighbor 判定そのものを壊す変異では本ケースが FAIL する）。
    src_own_after_neighbor = """
export interface SamplePort {
  /**
   * サンプルを消費する。
   *
   * @param key 判定単位の識別子（正の有限数のみ許可）。
   */
  consume(key: number): void
  // contract-ok: レビュー済み・異常時の振る舞いは自明なため省略
}
"""
    check_violations(
        "18c. U1陽性対照: 隣接メソッドが無いafter-neighborの抑止は機能する→違反0",
        src_own_after_neighbor,
        0,
    )

    # --- 19〜21. CRITICAL 2 是正: item3 キーワードの部分一致誤爆（実測の 3 例） ---
    src_ask_false_positive = """
export interface SamplePort {
  /**
   * ユーザーに質問を投げかける。
   *
   * @param question 投げかける質問文（空でない文字列）。
   */
  ask(question: string): Promise<string>
}
"""
    check_violations(
        "19. CRITICAL2: 『投げ』の部分一致は不採用(ask)→item3違反1", src_ask_false_positive, 1
    )

    src_send_false_positive = """
export interface SamplePort {
  /**
   * リクエストを送出する。
   *
   * @param url 送信先 URL（有効な URL 文字列）。
   */
  send(url: string): Promise<void>
}
"""
    check_violations(
        "20. CRITICAL2: 『送出』の部分一致は不採用(send)→item3違反1", src_send_false_positive, 1
    )

    src_cleanup_en_false_positive = """
export interface SamplePort {
  /**
   * Remove temp files; do not throw away user data during cleanup.
   *
   * @param dir Directory to clean（空でない絶対パス）。
   */
  cleanup(dir: string): Promise<void>
}
"""
    check_violations(
        "21. CRITICAL2: 『throw away』はthrowの部分一致で拾わない(cleanup)→item3違反1"
        "（#1071是正後もitem2は@paramの日本語キーワードで満たす）",
        src_cleanup_en_false_positive,
        1,
    )

    # --- 22. CRITICAL 2 陽性対照: 『例外を投げ』『エラーを送出』はフレーズとして採用する ---
    src_phrase_positive = """
export interface SamplePort {
  /**
   * 何かする。
   *
   * @param id 対象の識別子（空でない文字列）。
   * 異常時はエラーを送出する。
   */
  doThing(id: string): void
}
"""
    check_violations(
        "22. CRITICAL2陽性対照: 『エラーを送出』はフレーズとして採用する→違反0",
        src_phrase_positive,
        0,
    )

    # --- 23. CRITICAL 3 是正: プロパティ関数型構文もメソッドとして抽出する ---
    src_property_arrow = """
export interface SamplePort {
  doThing: (x: number) => void
}
"""
    check_extract("23a. CRITICAL3: プロパティ関数型構文もメソッドとして抽出する", src_property_arrow, 1)
    check_violations(
        "23b. 同上: JSDocなし・値域/異常時記述も皆無→item1違反1件のみ検出", src_property_arrow, 1
    )

    src_property_arrow_documented = """
export interface SamplePort {
  /**
   * 何かする。
   *
   * @param x 対象の数値（正の有限数）。
   *
   * 🔴 異常時の振る舞い: throw する。
   */
  doThing: (x: number) => void
}
"""
    check_violations(
        "23c. プロパティ関数型でも契約が揃っていれば違反0", src_property_arrow_documented, 0
    )

    # --- 24. CRITICAL 4 是正: パラメータリストの閉じ括弧が見つからない場合は ScanError ---
    src_broken_paren = """
export interface SamplePort {
  broken(x: number
}
"""
    try:
        extract_methods(src_broken_paren)
        failures.append(
            "- 24. CRITICAL4: 閉じ括弧未検出でも ScanError が送出されない（fail-closed 違反）"
        )
    except ScanError:
        pass

    with tempfile.TemporaryDirectory() as tmp_dir2:
        broken_paren_file = Path(tmp_dir2) / "broken.ts"
        broken_paren_file.write_text(src_broken_paren, encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = _run([broken_paren_file], Path(tmp_dir2))
        if code != 1:
            failures.append(
                f"- 24b. CRITICAL4: 閉じ括弧未検出ファイルはexit1(parse_failures)expected, got {code}"
            )
        combined2 = out.getvalue() + err.getvalue()
        if "解析不能" not in combined2:
            failures.append(f"- 24c. CRITICAL4: 出力に『解析不能』が含まれない: {combined2!r}")

    # --- 25. WARNING 1 是正: `_split_top_level` はジェネリクスのカンマを分割しない ---
    #     （直接 `_split_top_level` を検証する。`_param_types` はデフォルト値分割の際に
    #     `=` を素朴な部分一致で検出するため、`=>` を含むアロー関数型パラメータを混ぜると
    #     本 W1 修正とは別の既存欠陥（デフォルト値分割）を踏んでしまい、W1 の検証にならない）。
    generic_split = _split_top_level("opts: Record<string, unknown>, id: string")
    if generic_split != ["opts: Record<string, unknown>", " id: string"]:
        failures.append(f"- 25. WARNING1: ジェネリクスを含むトップレベル分割が誤り: {generic_split!r}")

    generic_types = _param_types("opts: Record<string, unknown>, id: string")
    if generic_types != ["Record<string, unknown>", "string"]:
        failures.append(f"- 25c. WARNING1: ジェネリクスを含むパラメータ分割が誤り: {generic_types!r}")

    # --- 26. U3: ネスト型注釈を含む複数パラメータの分割（既存 {} 深さ機構の回帰ガード） ---
    nested_types = _param_types("a: string, opts: { page: number }")
    if nested_types != ["string", "{ page: number }"]:
        failures.append(f"- 26. U3: ネスト型注釈を含む複数パラメータの分割が誤り: {nested_types!r}")

    # --- 27. WARNING 2 是正: 文字列リテラル型内の `{` を深さに数えない ---
    src_string_literal_brace = """
export interface SamplePort {
  readonly opener: '{'
  /**
   * 何かする。
   *
   * @param id 対象の識別子（空でない文字列）。
   *
   * 🔴 異常時の振る舞い: throw する。
   */
  consume(id: string): void
}
"""
    check_extract(
        "27a. WARNING2: 文字列リテラル内の『{』を深さに数えない→consumeを検出する",
        src_string_literal_brace,
        1,
    )
    check_violations("27b. 同上→違反0", src_string_literal_brace, 0)

    # --- 29. U2: JSDoc とシグネチャの間に空行があっても JSDoc を紐付ける ---
    src_blank_line_jsdoc_gap = """
export interface SamplePort {
  /**
   * サンプルを消費する。
   *
   * @param key 判定単位の識別子（正の有限数のみ許可）。
   *
   * 🔴 異常時の振る舞い: throw する。
   */

  consume(key: number): Promise<void>
}
"""
    check_violations(
        "29. U2: JSDocとシグネチャの間に空行があってもJSDocを紐付ける→違反0",
        src_blank_line_jsdoc_gap,
        0,
    )

    # --- 30. 干渉検証: CRITICAL1（neighbor のスパン除外）と CRITICAL2（item3 フレーズ化）が
    #         同じ入力・同じ変数（raw_entries / spans / jsdoc_text）を通っても互いの効果を
    #         打ち消していないことを確認する。ask() は「投げかける」という語を含む JSDoc を
    #         持つが自分の行の contract-ok で抑止され、隣接する doThing() は ask の抑止マーカーを
    #         neighbor 経由で継承せず、かつ『何かする。』という JSDoc だけでは item3 を満たさない
    #         （CRITICAL2 のキーワード厳格化が効いている）ことを同時に検証する。
    src_interference_check = """
export interface SamplePort {
  /**
   * 質問を投げかける。
   *
   * @param question 質問文（空でない文字列）。
   */
  ask(question: string): Promise<string> // contract-ok: ask は意図的に契約省略
  /**
   * 何かする。
   */
  doThing(x: number): void
}
"""
    check_violations(
        "30. 干渉検証: CRITICAL1のneighbor除外とCRITICAL2のキーワード厳格化は共存する"
        "→合計2(askは抑止/doThingはitem2+item3)",
        src_interference_check,
        2,
    )

    # --- 31〜35. Issue #1071 是正: `@param` タグ単体は item2 を満たさない ---

    # 31. Issue #1071 本文の EchoPort.echo 実例そのもの（空疎な @param）。
    #     `// throw する` は JSDoc の外側（行コメント）なので item3 にも寄与しない。
    src_echo_bare_param = """
export interface EchoPort {
  /**
   * @param value 値。
   */
  echo(value: string): Promise<string>  // throw する
}
"""
    check_violations(
        "31. #1071: EchoPort.echo実例(空疎な@param)→item2+item3の2件を検知",
        src_echo_bare_param,
        2,
    )

    # 32. バリアント: 型注釈つき @param（`{string}`）でも語彙が無ければ item2 違反のまま
    #     （型注釈の有無で判定が変わらないことの確認）。
    src_param_typed_no_keyword = """
export interface EchoPort {
  /**
   * @param {string} value この値を使う。
   *
   * 🔴 異常時の振る舞い: throw する。
   */
  echo(value: string): Promise<string>
}
"""
    check_violations(
        "32. #1071バリアント: 型注釈つき@paramでも語彙が無ければitem2違反",
        src_param_typed_no_keyword,
        1,
    )

    # 33. バリアント: @param の説明が複数行にまたがり、値域キーワードが継続行にある場合
    #     でも検出できる（本文全体を走査する設計を維持していることの確認）。
    src_param_multiline_keyword = """
export interface EchoPort {
  /**
   * @param value 判定単位の識別子として使う
   *   空でない文字列。
   *
   * 🔴 異常時の振る舞い: throw する。
   */
  echo(value: string): Promise<string>
}
"""
    check_violations(
        "33. #1071バリアント: @param説明が複数行でも継続行のキーワードを検出→違反0",
        src_param_multiline_keyword,
        0,
    )

    # 34. 陽性対照: @param の説明部分に値域キーワードがあれば item2 は満たす
    #     （厳格化のしすぎで正当な記述まで弾いていないことの確認）。
    src_param_with_keyword = """
export interface EchoPort {
  /**
   * @param value 空でない文字列。
   *
   * 🔴 異常時の振る舞い: throw する。
   */
  echo(value: string): Promise<string>
}
"""
    check_violations(
        "34. #1071陽性対照: @param説明部分に値域キーワードがあれば違反0", src_param_with_keyword, 0
    )

    # 35. `@param` タグそのものが無くても、本文の他の行に値域キーワードがあれば item2 は
    #     満たす（旧来の「本文行キーワード」判定との統合を維持していることの確認）。
    src_no_param_tag_but_keyword = """
export interface EchoPort {
  /**
   * echo する。引数は空でない文字列を渡すこと。
   *
   * 🔴 異常時の振る舞い: throw する。
   */
  echo(value: string): Promise<string>
}
"""
    check_violations(
        "35. #1071: @paramタグ無しでも本文キーワードがあれば違反0（統合維持）",
        src_no_param_tag_but_keyword,
        0,
    )

    # --- 36〜39. PR #1074 Layer 1 セルフレビュー是正（CRITICAL・fail-open）:
    #     item2 を JSDoc 全文への部分一致にすると、値域キーワードが対象引数の説明と無関係な
    #     箇所（@returns・@throws・別の @param）に出現しただけで PASS してしまう。

    # 36. 実測された fail-open の再現そのもの: @returns にのみ値域っぽい語がある。
    src_item2_leak_via_returns = """
export interface FooPort {
  /**
   * @param value 何かの値。
   * @returns 有効な範囲のキャッシュTTLに基づいて処理する（valueとは無関係）。
   *
   * 🔴 異常時の振る舞い: throw する。
   */
  foo(value: string): Promise<string>
}
"""
    check_violations(
        "36. #1074: @returnsのみに値域キーワード→item2は満たさない(item2違反1件)",
        src_item2_leak_via_returns,
        1,
    )

    # 37. バリアント: @throws にのみ値域っぽい語がある。
    src_item2_leak_via_throws = """
export interface FooBarPort {
  /**
   * @param value 何かの値。
   * @throws {RangeError} 有効な範囲外の値を渡すと例外を送出する。
   */
  foo(value: string): Promise<string>
}
"""
    check_violations(
        "37. #1074バリアント: @throwsのみに値域キーワード→item2は満たさない(item2違反1件)",
        src_item2_leak_via_throws,
        1,
    )

    # 38. バリアント: 無関係な別の @param（実引数に存在しない名前）にのみ値域っぽい語がある。
    src_item2_leak_via_unrelated_param = """
export interface BazPort {
  /**
   * @param value 何かの値。
   * @param label 空でないラベル文字列（実際には存在しないパラメータ）。
   *
   * 🔴 異常時の振る舞い: throw する。
   */
  baz(value: string): Promise<string>
}
"""
    check_violations(
        "38. #1074バリアント: 無関係な別の@paramのみに値域キーワード→item2は満たさない"
        "(item2違反1件)",
        src_item2_leak_via_unrelated_param,
        1,
    )

    # 39. 陽性対照: 複数 primitive 引数のうち、対応する @param 自身に値域キーワードがあれば
    #     正しく item2 を満たす（厳格化のしすぎで正当な記述まで弾いていないことの確認）。
    src_item2_correct_param_among_many = """
export interface QuxPort {
  /**
   * @param value 空でない文字列。
   * @param label 何かのラベル。
   *
   * 🔴 異常時の振る舞い: throw する。
   */
  qux(value: string, label: string): Promise<void>
}
"""
    check_violations(
        "39. #1074陽性対照: 複数paramのうち対応する@param自身に値域キーワード→違反0",
        src_item2_correct_param_among_many,
        0,
    )

    if failures:
        print("FAIL: check_port_contracts self-test", file=sys.stderr)
        for f in failures:
            print(f, file=sys.stderr)
        return 1

    print("OK: check_port_contracts self-test 全ケース通過")
    return 0


if __name__ == "__main__":
    sys.exit(main())
