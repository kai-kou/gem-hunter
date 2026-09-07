#!/usr/bin/env python3
"""py_source.py — Python ソースの `tokenize` による COMMENT / STRING 抽出を集約する共通モジュール
（Issue #1007）。

## なぜ必要か

`tokenize` で Python の COMMENT / STRING トークンを抜き出す処理が、次の 3 ファイルに
**独立に実装** されていた（`tools/ts_source.py` / `tools/md_fence.py`（#612 / PR #772）が
「同じ字句解析を各ツールが独自実装した結果、同じ欠陥が複数箇所に生まれた」として共有化した
前例と正面から矛盾していた）:

  - `tools/check_selftest_wiring.py` の `_comment_texts` → **既に解消済み**（#933・PR #1021 で
    `tools/wiring_marker.py` の `python_comment_texts()` へ統合されていた。本 Issue 起票時点の
    記述は古い）
  - `tools/check_tool_wiring.py` の `_comment_texts` → 同上（既に `wiring_marker.py` 経由）
  - `tools/check_module_contract_drift.py` の `explanatory_text` / `_py_tokens` → **本モジュールで
    ここへ統合する**

3 実装は **tokenize 失敗時の方針が食い違っていた**（`wiring_marker.python_comment_texts` は
`None` へ丸める fail-open、`check_module_contract_drift.py` は `UndecidableError`（exit 2）で
fail-closed）。Python 3.12（PEP 701）以降、f-string の中身が `STRING` トークンではなく
`FSTRING_START` / `FSTRING_MIDDLE` / `FSTRING_END` として出るため、この字句解析そのものを
複数箇所で独立に持つと「片方だけ直って残りにバグが残る」事故が再発する（#612 が根絶したはずの
形）。

## 失敗時の方針は呼び出し側が選ぶ（`on_failure` 引数）

fail-open / fail-closed のどちらが正しいかはツールの性質による（配線漏れ検出は「見逃しても
実害が小さい」ので fail-open、契約鮮度検出は「陳腐化を見逃すと索引が腐る」ので fail-closed）。
本モジュールは **字句解析そのもの**（`tokenize.generate_tokens` の呼び出しと例外処理）だけを
1 箇所に集約し、失敗時にどちらへ倒すかは呼び出し側が `on_failure` で選べるようにする
（現状の 3 通りの食い違いを統一する判断は本 Issue のスコープ外・呼び出し側で維持する）。

    on_failure="none"  : トークナイズ失敗時は `None` を返す（fail-open）
    on_failure="raise" : トークナイズ失敗時は `TokenizeFailure` を送出する（fail-closed）

`py_tokens()` 自体は常に `TokenizeFailure` を送出する（丸めない）。丸めるかどうかは
`comment_texts()` / `explanatory_text()` が `on_failure` に従って行う。

## なぜ `except Exception` で広く受けるか

`tokenize.generate_tokens` は `tokenize.TokenError` / `SyntaxError` / `IndentationError` /
`ValueError` 以外にも、入力の壊れ方次第で予期しない例外（`UnicodeDecodeError` 等）を送出しうる。
本モジュールは字句解析の下請けであり構文検証ではないため、どんな理由であれ **クラッシュせず
`TokenizeFailure` として一様に扱う**（`wiring_marker.python_comment_texts` の旧実装が
明文化していた方針をそのまま踏襲・より安全側に倒す）。narrow な例外リストで捕捉していた
`check_module_contract_drift.py` 側も、捕捉範囲が広がるだけで「捕捉していた例外を捕捉し損ねる」
方向の退行は無い（`0`/`1` への丸めではなく `2`（判定不能）が増える方向の変化であり、
`docs/rules/check-tool-design-rules.md` §1 の「想定外は 2 へ倒す」に整合する）。

使い方（self-test のみ。本体はライブラリとして import される想定）:
    python3 tools/py_source.py --self-test
"""

from __future__ import annotations

import io
import sys
import tokenize

# ---------------------------------------------------------------------------
# 例外
# ---------------------------------------------------------------------------


class TokenizeFailure(Exception):
    """Python テキストがトークナイズできなかったことを表す。

    `py_tokens()` は常にこれを送出する（fail-open/fail-closed の判断は下流の
    `comment_texts()` / `explanatory_text()` が `on_failure` 引数で行う）。
    """


# ---------------------------------------------------------------------------
# 字句解析（正本: この 1 関数だけが `tokenize.generate_tokens` を呼ぶ）
# ---------------------------------------------------------------------------


def py_tokens(text: str) -> list[tokenize.TokenInfo]:
    """`text` を Python としてトークナイズし、トークン列を返す。

    失敗したら常に `TokenizeFailure` を送出する（`None` へ丸めない・`0`/`1` に丸めない）。
    呼び出し側が生トークン列（位置情報つき）を必要とする場合はこちらを直接使う
    （例: `check_module_contract_drift.py` の行カバレッジ計算）。
    """
    try:
        return list(tokenize.generate_tokens(io.StringIO(text).readline))
    except Exception as exc:  # noqa: BLE001 — 字句解析の下請けはクラッシュしない（上記 docstring）
        raise TokenizeFailure(str(exc)) from exc


def _check_on_failure(on_failure: str) -> None:
    if on_failure not in ("none", "raise"):
        raise ValueError(f"on_failure must be 'none' or 'raise': {on_failure!r}")


# ---------------------------------------------------------------------------
# COMMENT だけの抽出（旧: wiring_marker.python_comment_texts の正本）
# ---------------------------------------------------------------------------


def comment_texts(text: str, *, on_failure: str = "none") -> list[str] | None:
    """`text` から COMMENT トークンの文字列だけを抽出する（出現順・区切り記号 `#` を含む）。

    docstring / 文字列リテラルの中身（マーカー書式を説明する地の文など）はコメントトークン
    ではないため含まれない。

    on_failure="none"（既定・fail-open）: トークナイズ失敗時は `None` を返す。
    on_failure="raise"（fail-closed）: `TokenizeFailure` をそのまま送出する。
    """
    _check_on_failure(on_failure)
    try:
        tokens = py_tokens(text)
    except TokenizeFailure:
        if on_failure == "raise":
            raise
        return None
    return [tok.string for tok in tokens if tok.type == tokenize.COMMENT]


# ---------------------------------------------------------------------------
# COMMENT (+ STRING) の抽出（旧: check_module_contract_drift.explanatory_text の正本）
# ---------------------------------------------------------------------------


def explanatory_text(text: str, *, include_strings: bool = True, on_failure: str = "raise") -> str | None:
    """「説明文」（コメント本文。既定では文字列リテラルも含む）を改行区切りで連結して返す。

    `include_strings=True`（既定）: COMMENT + STRING を対象にする（docstring・文字列リテラルの
    中身も「利用側に残る説明」として扱いたい呼び出し側向け）。
    `include_strings=False`: COMMENT のみ（`comment_texts()` と同じ集合だが、戻り値が
    「文字列のリスト」ではなく「改行連結した 1 文字列」である点が異なる）。

    on_failure="raise"（既定・fail-closed）: トークナイズ失敗時は `TokenizeFailure` を送出する。
    on_failure="none"（fail-open）: `None` を返す。

    🔴 **f-string の扱いには実行系バージョン依存の既知の差異がある**（PEP 701・Python 3.12+）。
    3.11 以前は `f"hello {name}"` 全体が単一の `STRING` トークンなので、式部分（`{name}`）ごと
    抽出される。3.12 以降は `FSTRING_START` / `FSTRING_MIDDLE` / `FSTRING_END` へ分解されるため、
    本関数は **リテラル部分（`FSTRING_MIDDLE`）だけ** を抽出し、式部分（`NAME` / `OP` 等）は
    抽出しない。式部分はコードそのものであって「説明文」ではないので後者の挙動が意図した形だが、
    3.11 との完全一致にはならない（3.11 では式部分も混ざる）。この差異が判定結果を変えうるのは
    「説明文が f-string の中にしか無い」ファイルに限られる。`FSTRING_MIDDLE` を拾わずにいると
    3.12 で説明文が丸ごと落ちて `check_module_contract_drift.py` が fail-closed（exit 2）へ倒れる
    ため、`getattr` による存在チェック付きで対象に含めている。
    """
    _check_on_failure(on_failure)
    try:
        tokens = py_tokens(text)
    except TokenizeFailure:
        if on_failure == "raise":
            raise
        return None
    types = {tokenize.COMMENT}
    if include_strings:
        types.add(tokenize.STRING)
        # PEP 701（Python 3.12+）: f-string のリテラル部分は STRING ではなく FSTRING_MIDDLE。
        # 3.11 以前には存在しないトークン種別なので getattr で存在を確認してから足す。
        fstring_middle = getattr(tokenize, "FSTRING_MIDDLE", None)
        if fstring_middle is not None:
            types.add(fstring_middle)
    return "\n".join(tok.string for tok in tokens if tok.type in types)


# ---------------------------------------------------------------------------
# self-test
# ---------------------------------------------------------------------------


def _run_self_test() -> int:
    failures: list[str] = []

    def check(label: str, got, want) -> None:
        if got != want:
            failures.append(f"  {label}: want {want!r}, got {got!r}")

    # ---------------- py_tokens ----------------

    # 正常系: トークン列が返る（NEWLINE 等を含む生トークン）
    toks = py_tokens("x = 1\n")
    check("py_tokens/returns_tokens_for_valid_source", any(t.type == tokenize.OP for t in toks), True)

    # 構文エラーは TokenizeFailure（クラッシュしない）
    try:
        py_tokens("def f(:\n")
        failures.append("py_tokens/syntax_error_raises: 例外が送出されなかった")
    except TokenizeFailure:
        pass
    except Exception as exc:  # noqa: BLE001
        failures.append(f"py_tokens/syntax_error_raises: 想定外の例外型 {type(exc).__name__}: {exc}")

    # トークナイザが例外を出す壊れた入力（未終端の複数行文字列 = tokenize.TokenError）も TokenizeFailure
    try:
        py_tokens('"""not closed\n')
        failures.append("py_tokens/unterminated_triple_quote_raises: 例外が送出されなかった")
    except TokenizeFailure:
        pass
    except Exception as exc:  # noqa: BLE001
        failures.append(
            f"py_tokens/unterminated_triple_quote_raises: 想定外の例外型 {type(exc).__name__}: {exc}"
        )

    # ---------------- comment_texts（fail-open 既定・COMMENT のみ） ----------------

    check(
        "comment_texts/basic",
        comment_texts("x = 1  # hello\n"),
        ["# hello"],
    )
    # docstring はコメントトークンではないので含まれない
    check(
        "comment_texts/docstring_not_included",
        comment_texts('"""# not a comment"""\nprint(1)\n'),
        [],
    )
    # 複数コメントを出現順に全て返す
    check(
        "comment_texts/multiple_in_order",
        comment_texts("# first\nx = 1  # second\n# third\n"),
        ["# first", "# second", "# third"],
    )
    # fail-open 既定: 構文エラーは None（クラッシュしない）
    check("comment_texts/on_failure_none_default", comment_texts("def f(:\n"), None)
    # fail-closed 指定: TokenizeFailure を送出する
    try:
        comment_texts("def f(:\n", on_failure="raise")
        failures.append("comment_texts/on_failure_raise: 例外が送出されなかった")
    except TokenizeFailure:
        pass

    # 不正な on_failure 値は ValueError（誤用を静かに握り潰さない）
    try:
        comment_texts("x = 1\n", on_failure="bogus")
        failures.append("comment_texts/invalid_on_failure_value: ValueError が送出されなかった")
    except ValueError:
        pass

    # ---------------- explanatory_text（fail-closed 既定・COMMENT + STRING） ----------------

    check(
        "explanatory_text/comment_and_string",
        explanatory_text('x = "hello"  # note\n'),
        '"hello"\n# note',
    )
    # include_strings=False なら STRING を含まない（comment_texts と同じ集合）
    check(
        "explanatory_text/include_strings_false",
        explanatory_text('x = "hello"  # note\n', include_strings=False),
        "# note",
    )
    # docstring は STRING トークンなので include_strings=True では含まれる
    check(
        "explanatory_text/docstring_included_when_include_strings_true",
        '"""説明"""' in (explanatory_text('"""説明"""\nprint(1)\n') or ""),
        True,
    )
    # fail-closed 既定: 構文エラーは TokenizeFailure を送出する
    try:
        explanatory_text("def f(:\n")
        failures.append("explanatory_text/on_failure_raise_default: 例外が送出されなかった")
    except TokenizeFailure:
        pass
    # on_failure="none" を指定すれば None（fail-open へ切り替え可能）
    check(
        "explanatory_text/on_failure_none_opt_in",
        explanatory_text("def f(:\n", on_failure="none"),
        None,
    )

    # ---------------- 構造要件は満たすが意味的に壊れている入力（#896 流儀の負ケース） ----------------
    # 同じ行にコメントと文字列が同居し、かつコメント本体がマーカー風の文字列を含む場合でも、
    # STRING と COMMENT が別トークンとして正しく分離されること（取り違えて片方だけ消えない）。
    mixed = 'x = "# selftest-wiring-ok: not-a-real-comment"  # real: 理由\n'
    mixed_comments = comment_texts(mixed)
    if mixed_comments != ["# real: 理由"]:
        failures.append(
            f"comment_texts/string_content_not_misclassified_as_comment: got={mixed_comments!r}"
        )
    mixed_explanatory = explanatory_text(mixed)
    if mixed_explanatory is None or "selftest-wiring-ok" not in mixed_explanatory:
        failures.append(
            "explanatory_text/string_content_still_included_when_include_strings_true: "
            f"got={mixed_explanatory!r}"
        )

    # ---------------- PEP 701（f-string を含むソースでの COMMENT / STRING 抽出） ----------------
    # Python 3.12+ では f-string の中身が FSTRING_START/MIDDLE/END に分解される。
    # (a) COMMENT 抽出は f-string の有無に影響されない（両バージョン共通の期待値）。
    fstring_src = 'name = "x"\ny = f"hello {name}"  # a comment\n'
    fstring_comments = comment_texts(fstring_src)
    check("comment_texts/fstring_input_still_extracts_trailing_comment", fstring_comments, ["# a comment"])

    # (b) 🔴 リスクのある経路は explanatory_text(include_strings=True) 側である（COMMENT ではなく
    # STRING / FSTRING_* の区別が効くのはこちら）。バージョンで期待値が変わるので分岐して固定する。
    # ここを COMMENT だけのケースで済ませると「PEP 701 対応済み」の見た目だけが付く（PR #1064
    # の Layer 1 セルフレビュー指摘）。
    fstring_explanatory = explanatory_text(fstring_src)
    if fstring_explanatory is None:
        failures.append("explanatory_text/fstring: None が返った（トークナイズ失敗）")
    else:
        # どちらのバージョンでも「リテラル部分」と「コメント」は必ず抽出される。
        for needle, label in (("hello", "リテラル部分"), ("# a comment", "コメント")):
            if needle not in fstring_explanatory:
                failures.append(
                    f"explanatory_text/fstring_contains_{label}: {needle!r} が抽出されない "
                    f"（got={fstring_explanatory!r}・python={sys.version_info[:2]}）"
                )
        # 式部分（{name}）の扱いだけがバージョンで変わる。3.11 以前は単一 STRING なので混ざり、
        # 3.12 以降は FSTRING_MIDDLE だけを拾うので混ざらない。
        expr_included = "{name}" in fstring_explanatory
        want_expr_included = sys.version_info < (3, 12)
        if expr_included != want_expr_included:
            failures.append(
                "explanatory_text/fstring_expression_part: "
                f"want_included={want_expr_included}, got_included={expr_included} "
                f"（got={fstring_explanatory!r}・python={sys.version_info[:2]}）"
            )

    if failures:
        print("❌ py_source --self-test FAILED")
        print("\n".join(failures))
        return 1
    print("✅ py_source --self-test PASSED")
    return 0


def main() -> int:
    if "--self-test" in sys.argv[1:]:
        return _run_self_test()
    print(
        "py_source.py は tools/check_*.py / tools/wiring_marker.py から import して使う"
        " 共通ライブラリです。単体では --self-test のみ受け付けます。"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
