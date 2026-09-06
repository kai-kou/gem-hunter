#!/usr/bin/env python3
"""wiring_marker.py — `check_selftest_wiring.py` と `check_tool_wiring.py` が共有する、
シェルコメント除去とマーカー走査の共通ヘルパー（Issue #933）。

## なぜ必要か

`tools/check_selftest_wiring.py`（`--self-test` の配線漏れ検査）と `tools/check_tool_wiring.py`
（本判定の配線漏れ検査）は、① クォート追跡型のシェル 1 行コメント除去 ② 言語別
（`py` / `js` / `sh`）のコメント抽出ディスパッチ ③ `# {token}-ok: {理由}` マーカー走査、の
3 点をそれぞれ独立に実装していた（準逐語重複）。`run_checks.sh` にヒアドキュメントが増える等で
一方のコメント除去だけ直すと、もう一方は静かに元の欠陥（コメント内の呼び出しを実行と誤認する等）
を抱えたまま残る fail-open を構造的に埋め込んでいた。本モジュールへ 1 箇所に集約し、直す先を
1 箇所に絞る。

`Verdict` / `Report` / `render_*`（人間可読・JSON 出力の語彙）は両検査で意味が異なる
（片方は「配線漏れ」、もう片方は「死蔵」）ため、あえて共通化していない。本モジュールが持つのは
入力（ソース文字列）からコメント本文・マーカー理由を取り出すところまでの、意味論が完全に
一致する部分だけである。

## シェルコメント除去の挙動差（意図的に温存する・パラメータ化で吸収する）

2 検査のシェルコメント除去は、`#` をコメント開始とみなす直前文字の許容集合が異なっていた
（`check_selftest_wiring.py` は空白のみ、`check_tool_wiring.py` はメタ文字
`; | & (` の直後も許容する — bash の仕様上どちらも正しい部分挙動で、後者は「コマンド位置の
実行呼び出し検出」でメタ文字直後に置かれた呼び出しを見逃さないための拡張だった）。
本モジュールへの統合にあたって **どちらの挙動も変えない**: `strip_shell_line_comment()` の
`extra_comment_start_after` 引数で呼び出し側ごとに許容集合を指定する（既定は空白のみ）。

## 言語別マーカー書式

- `py` / `sh`: `# {token}: {理由}`（`#` 直後にしか一致しない実コメント）
- `js`（`.mjs` / `.mts`）: コメント本文の先頭（ブロックコメントの `*` 継続行を許容）に
  アンカーされた `{token}: {理由}`（`ts_source.extract_comments()` が `//` / `/* */` の
  区切り記号を除去済みの本文だけを返すため、`#` は不要）

使い方（self-test のみ。本体はライブラリとして import される想定）:
    python3 tools/wiring_marker.py --self-test
"""

from __future__ import annotations

import io
import re
import sys
import tokenize
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ts_source  # noqa: E402 — JS/TS のコメント抽出はここへ委譲する（#612 / #992）


# ─────────────────────────────────────────────────────────────
# シェルコメント除去（クォート追跡・行単位）
# ─────────────────────────────────────────────────────────────


def strip_shell_line_comment(line: str, extra_comment_start_after: str = "") -> str:
    """bash の 1 行から、クォート外の `#` 以降（シェルコメント）を取り除く。

    シングルクォート `'...'` とダブルクォート `"..."` の中身は保持する（例:
    `echo "## run_checks 結果"` の `#` はコメントとして解釈しない）。`#` は「行頭、または
    直前が空白（`extra_comment_start_after` を渡した場合はそれに含まれる文字も含む）」の
    ときだけコメント開始とみなす。

    `extra_comment_start_after`（既定は空文字＝空白のみ）: bash はメタ文字
    （`; | & (` 等）の直後の `#` もコメント開始として扱う。呼び出し側がコマンド位置の
    実行呼び出しまで検出したい場合は `";|&()"` を渡す（`${VAR#pattern}` / `$#` の `#`
    はメタ文字の直後ではないため、渡しても誤って落とさない）。

    既知の限界（ヒアドキュメントに加えて）: ANSI-C クォーティング `$'...'` 内でエスケープ
    された `\\'`（例: `$'it\\'s a test'`）は非対応。シングルクォートの開始/終了を単純な
    ペアとして追跡するため `\\'` を終端クォートと誤認し、実際にはクォート内部にある `#`
    以降を誤ってコメント扱いする場合がある（#933 移設前からの既存挙動・対象スクリプトに
    実例なし）。
    """
    quote: str | None = None
    prev: str | None = None
    out: list[str] = []
    allowed_prev = " \t" + extra_comment_start_after
    i, n = 0, len(line)
    while i < n:
        ch = line[i]
        if quote:
            out.append(ch)
            if quote == '"' and ch == "\\" and i + 1 < n:
                out.append(line[i + 1])
                prev = line[i + 1]
                i += 2
                continue
            if ch == quote:
                quote = None
            prev = ch
            i += 1
            continue
        if ch in "'\"":
            quote = ch
            out.append(ch)
            prev = ch
            i += 1
            continue
        if ch == "#" and (prev is None or prev in allowed_prev):
            break
        out.append(ch)
        prev = ch
        i += 1
    return "".join(out)


def shell_comment_texts(content: str) -> list[str]:
    """`content`（bash スクリプト全体）から `#` コメント本文（`#` 自身を含み行末までの
    1 行）を抽出する（マーカー走査対象の `.sh` 用）。空白直後の `#` だけをコメント開始と
    みなす（`strip_shell_line_comment` の既定挙動）。
    """
    comments: list[str] = []
    for raw_line in content.splitlines():
        stripped = strip_shell_line_comment(raw_line)
        if len(stripped) < len(raw_line):
            comments.append(raw_line[len(stripped) :])
    return comments


def strip_shell_comments(content: str, extra_comment_start_after: str = "") -> str:
    """bash スクリプト全体からシェルコメントを取り除く（行単位。ヒアドキュメント非対応）。

    既知の限界: ANSI-C クォーティング `$'...'` 内のバックスラッシュエスケープ（`\\'` 等）は
    非対応。クォート追跡はシングルクォート `'...'` を単純な開始/終了ペアとして扱うため、
    `$'it\\'s a test # not a comment'` のような文字列があると `\\'` を終端クォートと誤認し、
    本来クォート内部にある `#` 以降を実コメントとして切り落としてしまう（本 PR 時点で対象
    スクリプトに実例なし・非顕在。#933 移設前からの既存挙動で新規回帰ではない）。
    """
    out: list[str] = []
    for raw_line in content.splitlines(keepends=True):
        if raw_line.endswith("\n"):
            body, eol = raw_line[:-1], "\n"
        else:
            body, eol = raw_line, ""
        out.append(strip_shell_line_comment(body, extra_comment_start_after) + eol)
    return "".join(out)


# ─────────────────────────────────────────────────────────────
# 言語別コメント抽出ディスパッチ
# ─────────────────────────────────────────────────────────────


def python_comment_texts(content: str) -> list[str] | None:
    """Python としてトークナイズし、実コメントトークンの文字列だけを返す。

    docstring / 文字列リテラルの中身（マーカー書式を説明する地の文など）はコメントトークン
    ではないため含まれない。構文エラー・NUL バイト混入等でトークナイズ自体が失敗した場合は
    クラッシュせず `None` を返す（呼び出し側は安全側＝「マーカーなし」として扱う）。
    """
    try:
        return [
            tok.string
            for tok in tokenize.generate_tokens(io.StringIO(content).readline)
            if tok.type == tokenize.COMMENT
        ]
    except Exception:
        # tokenize は SyntaxError / IndentationError / tokenize.TokenError / ValueError など
        # 様々な例外を送出しうる。本モジュールは配線漏れ検出の下請けであり構文検証ではない
        # ため、どんな理由であれクラッシュしてはならない。
        return None


def comment_texts_for_lang(content: str, lang: str) -> list[str] | None:
    """言語別にコメント本文だけを抽出する。

    `lang`: `"py"`（既定・tokenize ベース）/ `"js"`（`.mjs`/`.mts`・`ts_source.extract_comments`
    へ委譲）/ `"sh"`（`shell_comment_texts`）。未知の値は `"py"` と同じ扱いにする
    （呼び出し側は対象拡張子を事前に絞り込み済みのため実運用では到達しない）。
    """
    if lang == "js":
        return ts_source.extract_comments(content)
    if lang == "sh":
        return shell_comment_texts(content)
    return python_comment_texts(content)


# ─────────────────────────────────────────────────────────────
# マーカー走査
# ─────────────────────────────────────────────────────────────


@dataclass
class MarkerScan:
    """1 ファイルぶんのマーカー走査結果。"""

    reasons: list[str]  # 実コメントとして書かれた、理由が非空のマーカーの理由文字列（出現順）
    has_empty: bool  # 理由が空の（無効な）マーカーが 1 つでもあったか
    tokenize_failed: bool  # コメント抽出が失敗し、安全側で「マーカーなし」にフォールバックしたか


# `# {token}: {理由}` 形式（py / sh）。理由は同じ行の行末までとする。コメント本文の先頭
# （行頭の空白のみ許容）にアンカーする。非アンカーだと「コメント内でマーカー書式を地の文で
# 説明しただけの実コメント」（例: `# 除外するにはこう書く: # selftest-wiring-ok: <理由>`）まで
# `re.search` が途中の `#` を拾って有効なマーカーと誤認する（fail-open）。直下の
# `_JS_MARKER_TEMPLATE` は当初からアンカー済みで、本テンプレートだけ移設時に無アンカーの
# まま残っていた。
_HASH_MARKER_TEMPLATE = r"^[ \t]*#[ \t]*{token}:[ \t]*(.*)$"

# `{token}: {理由}` 形式・コメント本文の先頭にアンカー（js）。ブロックコメントの `*` 継続行
# （` * {token}: ...`）だけを許容する（`\*?` は最大 1 個）。非アンカーだと地の文での言及
# （「// See docs/... for the {token}: marker format.」）まで有効なマーカーと誤認する
# （fail-open・#992 フォローアップで実際に踏んだ穴）。
_JS_MARKER_TEMPLATE = r"^[ \t]*\*?[ \t]*{token}:[ \t]*(.*)$"


def _marker_re(token: str, lang: str) -> re.Pattern[str]:
    template = _JS_MARKER_TEMPLATE if lang == "js" else _HASH_MARKER_TEMPLATE
    return re.compile(template.format(token=re.escape(token)), re.MULTILINE)


def scan_markers(content: str, token: str, lang: str = "py") -> MarkerScan:
    """`content` の実コメントから `{token}: {理由}` マーカーを走査する。

    `token` はマーカー語（例: `"selftest-wiring-ok"` / `"tool-wiring-ok"`）。`lang` は
    `"py"`（既定）/ `"js"` / `"sh"`。
    """
    comments = comment_texts_for_lang(content, lang)
    if comments is None:
        return MarkerScan(reasons=[], has_empty=False, tokenize_failed=True)
    marker_re = _marker_re(token, lang)
    reasons: list[str] = []
    has_empty = False
    for comment in comments:
        m = marker_re.search(comment)
        if not m:
            continue
        reason = m.group(1).strip()
        if reason:
            reasons.append(reason)
        else:
            has_empty = True
    return MarkerScan(reasons=reasons, has_empty=has_empty, tokenize_failed=False)


def marker_reason(content: str, token: str, lang: str = "py") -> str | None:
    """有効な `{token}` マーカー（実コメントとして書かれたもの）の理由文字列を返す。

    マーカーが無い、全てのマーカーの理由が空（無効マーカー）、またはコメント抽出自体が
    失敗した場合は `None` を返す（= 除外されない・安全側）。複数マーカーがあり、どれか
    1 つでも理由が非空なら、その理由を返す。
    """
    reasons = scan_markers(content, token, lang).reasons
    return reasons[0] if reasons else None


def has_invalid_empty_marker(content: str, token: str, lang: str = "py") -> bool:
    """理由が空の `{token}` マーカーが（有効な理由付きマーカーとは別に）存在するか。"""
    return scan_markers(content, token, lang).has_empty


# ─────────────────────────────────────────────────────────────
# --self-test（ネットワーク・実ファイル不要のユニットテスト）
# ─────────────────────────────────────────────────────────────


def _self_test() -> int:
    failures: list[str] = []
    assertions = 0

    def check(label: str, cond: bool) -> None:
        nonlocal assertions
        assertions += 1
        if not cond:
            failures.append(label)

    # ── strip_shell_line_comment: クォート追跡 ──
    check(
        "A1: クォート内の # は保持する",
        strip_shell_line_comment('echo "## run_checks 結果"') == 'echo "## run_checks 結果"',
    )
    check(
        "A2: クォート外の # 以降は除去する",
        strip_shell_line_comment("run_check foo # comment") == "run_check foo ",
    )
    check(
        "A3: 行頭の # はコメント開始",
        strip_shell_line_comment("# whole line comment") == "",
    )
    check(
        "A4: 識別子中の # はコメント開始とみなさない（既定・メタ文字拡張なし）",
        strip_shell_line_comment("true;#python3 tools/check_alpha.py")
        == "true;#python3 tools/check_alpha.py",
    )
    check(
        "A5: extra_comment_start_after にメタ文字を渡すと ';#' 直後もコメント開始になる"
        "（check_tool_wiring.py の拡張挙動を再現）",
        strip_shell_line_comment("true;#python3 tools/check_alpha.py", ";|&()") == "true;",
    )
    for prefix in ("|", "&", "("):
        check(
            f"A5: '{prefix}#' もメタ文字拡張で検出する",
            strip_shell_line_comment(f"true {prefix}#python3 tools/check_alpha.py", ";|&()")
            == f"true {prefix}",
        )
    check(
        "A6: ${VAR#pattern} をコメント開始と誤認しない（メタ文字拡張時も）",
        strip_shell_line_comment('NAME="${FILE#tools/}"; echo hi', ";|&()")
        == 'NAME="${FILE#tools/}"; echo hi',
    )
    check(
        "A7: エスケープされたダブルクォートを正しく扱う",
        strip_shell_line_comment('echo "a \\" b" # trailing') == 'echo "a \\" b" ',
    )

    # ── shell_comment_texts / strip_shell_comments ──
    check(
        "B1: shell_comment_texts はコメント本文（# を含む）を返す",
        shell_comment_texts("code # selftest-wiring-ok: reason\n") == ["# selftest-wiring-ok: reason"],
    )
    check(
        "B2: コメントが無い行は含まれない",
        shell_comment_texts("code only\n") == [],
    )
    check(
        "B3: strip_shell_comments は改行を保ったままコメントを除去する",
        strip_shell_comments("a # c\nb\n") == "a \nb\n",
    )

    # ── comment_texts_for_lang / scan_markers（py） ──
    src_py = "#!/usr/bin/env python3\n# selftest-wiring-ok: 理由\nprint(1)\n"
    check(
        "C1: py のコメント抽出はマーカー行を含む",
        any("selftest-wiring-ok" in c for c in (comment_texts_for_lang(src_py, "py") or [])),
    )
    check(
        "C2: py の marker_reason が理由を返す",
        marker_reason(src_py, "selftest-wiring-ok", "py") == "理由",
    )
    check(
        "C3: docstring 内の言及はマーカーとみなさない（tokenize が実コメントだけを返す）",
        marker_reason(
            '"""# selftest-wiring-ok: 地の文"""\nprint(1)\n', "selftest-wiring-ok", "py"
        )
        is None,
    )
    check(
        "C4: 構文エラーは tokenize_failed=True（クラッシュしない）",
        scan_markers("def f(:\n", "selftest-wiring-ok", "py").tokenize_failed,
    )
    check(
        "C5: py の地の文（実コメントだがマーカー書式を説明しているだけ）はマーカーと"
        "みなさない（境界の外側の負ケース・#750 流儀・アンカー漏れの反例）",
        marker_reason(
            "#!/usr/bin/env python3\n"
            "# 除外するにはこう書く: # selftest-wiring-ok: <理由>\n"
            "print(1)\n",
            "selftest-wiring-ok",
            "py",
        )
        is None,
    )

    # ── sh ──
    src_sh = "#!/usr/bin/env bash\n# tool-wiring-ok: 手動運用ツール\necho hi\n"
    check(
        "D1: sh の marker_reason が理由を返す",
        marker_reason(src_sh, "tool-wiring-ok", "sh") == "手動運用ツール",
    )
    check(
        "D2: sh の空理由マーカーは has_invalid_empty_marker=True",
        has_invalid_empty_marker("# tool-wiring-ok:\necho hi\n", "tool-wiring-ok", "sh"),
    )
    check(
        "D3: sh の地の文（実コメントだがマーカー書式を説明しているだけ）はマーカーと"
        "みなさない（境界の外側の負ケース・アンカー漏れの反例）",
        marker_reason(
            "#!/usr/bin/env bash\n"
            "# NOTE: to skip add: # tool-wiring-ok: <reason>\n"
            "echo hi\n",
            "tool-wiring-ok",
            "sh",
        )
        is None,
    )

    # ── js（アンカー・正規表現リテラルの反例は ts_source.py 側の self-test が担保するため
    #    ここでは wiring_marker としての「トークン差し替え」だけを確認する） ──
    src_js = "// tool-wiring-ok: js の理由\nfoo('--self-test')\n"
    check(
        "E1: js の marker_reason（token 差し替えても正しく動く）",
        marker_reason(src_js, "tool-wiring-ok", "js") == "js の理由",
    )
    src_js_prose = "// See docs for the tool-wiring-ok: marker format.\nfoo()\n"
    check(
        "E2: js の地の文（先頭アンカー外）はマーカーとみなさない",
        marker_reason(src_js_prose, "tool-wiring-ok", "js") is None,
    )
    check(
        "E3: 未終端ブロックコメントは js でも tokenize_failed=True",
        scan_markers("/* not closed\nfoo()\n", "tool-wiring-ok", "js").tokenize_failed,
    )

    # ── F: 境界の外側（token を変えても互いに誤爆しない・#750 流儀） ──
    src_both_tokens = "# selftest-wiring-ok: A\n# tool-wiring-ok: B\n"
    check(
        "F1: selftest-wiring-ok トークンで検索すると tool-wiring-ok 側は拾わない",
        marker_reason(src_both_tokens, "selftest-wiring-ok", "py") == "A",
    )
    check(
        "F2: tool-wiring-ok トークンで検索すると selftest-wiring-ok 側は拾わない",
        marker_reason(src_both_tokens, "tool-wiring-ok", "py") == "B",
    )

    if failures:
        print("❌ wiring_marker --self-test FAILED:")
        for f in failures:
            print(f"    - {f}")
        return 1
    print(f"✅ wiring_marker --self-test PASSED（{assertions} 件のアサーション全て成功）")
    return 0


def main() -> int:
    if "--self-test" in sys.argv[1:]:
        return _self_test()
    print(
        "wiring_marker.py は check_selftest_wiring.py / check_tool_wiring.py から import して"
        " 使う共通ライブラリです。単体では --self-test のみ受け付けます。"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
