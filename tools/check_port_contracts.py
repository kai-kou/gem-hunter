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
     JSDoc に値域の記述がある（`@param` 行、または「値域」「正の有限数」「空でない」「有効な」
     「範囲」のいずれかを含む本文行）。
  3. **JSDoc が存在すれば常に**、JSDoc に異常時の振る舞いの記述がある（`@throws`、
     または「throw」「fail-open」「フォールバック」「投げ」「例外」「送出」のいずれかを含む本文行）。

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
`tools/check_datetime_tz.py` の `# tz-ok` と同じ作法）。

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

# item 2（値域）: @param 行、または以下のキーワードを含む本文行。
ITEM2_KEYWORDS = ("@param", "値域", "正の有限数", "空でない", "有効な", "範囲")

# item 3（異常時の振る舞い）: @throws、または以下のキーワード（ASCII は大文字小文字を無視）。
# 🔴 「送出」を追加（#800 fail-open 是正）: 「例外を送出する」は「例外を投げる」と同義の
# 日本語技術用語（Java/TypeScript の JSDoc・エラーハンドリング文書で実際に使われる言い回し）。
# 既存の「投げ」「例外」だけでは「エラーを送出する」のように動詞が「投げる」でも「例外」でも
# ない実在の表現形を拾えない取りこぼしがあるため追加する（広げすぎ防止のため、この 1 語のみ）。
ITEM3_KEYWORDS_JP = ("@throws", "フォールバック", "投げ", "例外", "送出")
ITEM3_KEYWORDS_EN_CI = ("throw", "fail-open")

PRIMITIVE_TYPES = {"string", "number", "boolean", "bigint"}

IFACE_RE = re.compile(r"export\s+interface\s+(\w+Port)\b[^{]*\{")
METHOD_RE = re.compile(r"^\s*(?:readonly\s+)?([A-Za-z_$][\w$]*)\s*\??\s*(?:<[^>]*>)?\s*\(")

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
    suppressed: bool  # contract-ok マーカーの有無


def _net_delta(line: str) -> int:
    return sum(1 for c in line if c in _OPEN_CHARS) - sum(1 for c in line if c in _CLOSE_CHARS)


def _split_top_level(text: str, sep: str = ",") -> list[str]:
    """`(){}[]` の深さを無視しないトップレベル区切りで分割する（`<>` は数えない・呼び出し元と同じ理由）。"""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in text:
        if ch in _OPEN_CHARS:
            depth += 1
        elif ch in _CLOSE_CHARS:
            depth = max(0, depth - 1)
        if ch == sep and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
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


def _has_primitive_param(param_list_text: str) -> bool:
    return any(t in PRIMITIVE_TYPES for t in _param_types(param_list_text))


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


def _contains_item2_keyword(jsdoc_text: str) -> bool:
    return any(kw in jsdoc_text for kw in ITEM2_KEYWORDS)


def _contains_item3_keyword(jsdoc_text: str) -> bool:
    if any(kw in jsdoc_text for kw in ITEM3_KEYWORDS_JP):
        return True
    lowered = jsdoc_text.lower()
    return any(kw in lowered for kw in ITEM3_KEYWORDS_EN_CI)


def extract_methods(source: str) -> list[MethodInfo]:
    """ソース全体（1 ファイル分）から `export interface *Port` の各メソッドを抽出する。

    見逃し経路への配慮:
      - `export interface` に一致する行が 0 件でも例外にせず空リストを返す（呼び出し元が
        「対象 0 件」を集計する）。
      - メソッドシグネチャが複数行にまたがっても（開き括弧の対応が閉じるまで）1 メソッドとして扱う。
      - ネストしたオブジェクト型の中のメソッド様シグネチャ（例:
        `foo(opts: { bar(): void }): void` のように行が分かれるケース）を、深さ 0 のときだけ
        メソッドとして扱うことで誤って独立メソッド扱いしない（境界の外側の負ケース）。
    """
    stripped = strip_comments(source)
    raw_lines = source.splitlines()
    stripped_lines = stripped.splitlines()
    if len(raw_lines) != len(stripped_lines):
        # strip_comments は行数を保存する契約（ts_source.py docstring）。崩れたら判定不能。
        raise ScanError("strip_comments の行数がソースと一致しない（内部矛盾）")

    methods: list[MethodInfo] = []
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
        i = body_start_line
        while i <= body_end_line:
            line = stripped_lines[i - 1]
            if depth == 0:
                mm = METHOD_RE.match(line)
                if mm:
                    method_name = mm.group(1)
                    start_line = i
                    # メソッドシグネチャの終端（括弧の対応が閉じる行）まで消費する。
                    span_depth = _net_delta(line)
                    end_line = start_line
                    while span_depth > 0 and end_line < body_end_line:
                        end_line += 1
                        span_depth += _net_delta(stripped_lines[end_line - 1])
                    sig_stripped = "\n".join(stripped_lines[start_line - 1 : end_line])
                    open_paren = sig_stripped.find("(")
                    if open_paren != -1:
                        close_paren = find_matching_paren(sig_stripped, open_paren)
                        param_list_text = sig_stripped[open_paren + 1 : close_paren]
                    else:
                        param_list_text = ""

                    jsdoc_text = _find_jsdoc(raw_lines, start_line, body_start_line)
                    sig_raw = "\n".join(raw_lines[start_line - 1 : end_line])
                    neighbor_lines = []
                    if start_line - 1 >= 1:
                        neighbor_lines.append(raw_lines[start_line - 2])
                    if end_line + 1 <= len(raw_lines):
                        neighbor_lines.append(raw_lines[end_line])
                    suppressed = _contains_marker(sig_raw, CONTRACT_OK_MARKER) or any(
                        CONTRACT_OK_MARKER in nl for nl in neighbor_lines
                    ) or (jsdoc_text is not None and CONTRACT_OK_MARKER in jsdoc_text)

                    methods.append(
                        MethodInfo(
                            interface_name=iface_name,
                            method_name=method_name,
                            line=start_line,
                            jsdoc_text=jsdoc_text,
                            has_primitive_param=_has_primitive_param(param_list_text),
                            suppressed=suppressed,
                        )
                    )
                    i = end_line + 1
                    continue
            depth += _net_delta(line)
            i += 1
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
        if meth.has_primitive_param and not _contains_item2_keyword(meth.jsdoc_text):
            violations.append(
                f"{meth.line}: {label}: primitive 型引数を取るが値域の記述が JSDoc に無い"
                "（item 2・@param 行または『値域』『正の有限数』等のキーワードが必要）"
            )
        if not _contains_item3_keyword(meth.jsdoc_text):
            violations.append(
                f"{meth.line}: {label}: 異常時の振る舞いの記述が JSDoc に無い"
                "（item 3・@throws または『throw』『fail-open』『フォールバック』等のキーワードが必要）"
            )
    return violations


def _port_files() -> list[Path]:
    return sorted(REPO_ROOT.glob(PORTS_GLOB))


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

    if failures:
        print("FAIL: check_port_contracts self-test", file=sys.stderr)
        for f in failures:
            print(f, file=sys.stderr)
        return 1

    print("OK: check_port_contracts self-test 全ケース通過")
    return 0


if __name__ == "__main__":
    sys.exit(main())
