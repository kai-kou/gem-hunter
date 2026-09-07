#!/usr/bin/env python3
"""check_css_variable_cycles.py — CSS カスタムプロパティの自己参照・循環参照の検査（Issue #1012）

## なぜ必要か

CSS 変数の解決失敗は **例外にならず、値が無いまま素通りする**（fail-open）。
Issue #858 では `app/globals.css` の `@theme inline` に
`--font-sans: var(--font-sans);` という **自己参照** があり、Tailwind v4 がこの宣言を
無効値として黙って無視したため、アプリ全体が Geist Sans ではなく UA 既定フォントで
描画されていた。ブラウザにも CI にもエラーが出ないため、検出しなければ恒久的に壊れたまま残る。

## 何を検査するか

- **直接自己参照**: `--foo: var(--foo)`（#858 の形）
- **間接サイクル**: `--a: var(--b)` / `--b: var(--a)`（2 段以上の閉路。有向グラフの閉路検出）

## 何を検査しないか（スコープ外・意図的）

- **未定義参照**（`var(--baz)` の `--baz` がどこにも定義されていない）は対象外。
  `next/font` が実行時に注入する変数（`--font-geist-sans` / `--font-geist-mono`）は
  CSS ファイル内に定義が無く、誤検知を避けるための allowlist の出所を確定できないため
  （Issue #1012 の「要検討」項目。必要になったら別 Issue で allowlist つきで足す）。

## 終了コード

- `0` = PASS（対象 CSS を実際に読み、自己参照・循環が 1 件も無かった）
- `1` = 違反あり（自己参照または循環を検出した）
- `2` = 判定不能（対象 CSS が 0 件 / 変数定義が 0 件 / ファイルを読めない）
       — 対象 0 件を `0` に丸めない（fail-closed・`docs/rules/check-tool-design-rules.md` §2）

## 使い方

    python3 tools/check_css_variable_cycles.py            # リポジトリ全体の .css を検査
    python3 tools/check_css_variable_cycles.py PATH...    # ファイル / ディレクトリを明示指定
    python3 tools/check_css_variable_cycles.py --self-test
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

EXCLUDED_DIRS = {
    ".git",
    "node_modules",
    ".next",
    ".open-next",
    ".wrangler",
    "dist",
    "build",
    "out",
    "coverage",
    ".venv",
    "venv",
    "__pycache__",
}


# --------------------------------------------------------------------------- CSS パース

# コメント除去は check_contrast.py にも同名関数があるが、そちらは改行ごと落とすため
# 行番号つきで違反を報告できない（役割が違うので流用せず、行を保つ実装をここに置く）。
_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)

# 宣言: `--name : value` で、値の終端は `;` / `}` / 入力末尾。
# `[^;{}]*` は改行を含むため、改行を跨いだ宣言も 1 件として拾える。
_DECL_RE = re.compile(r"(--[A-Za-z0-9_-]+)\s*:\s*([^;{}]*?)\s*(?=[;}]|\Z)")

# 参照: 関数名 `var` は CSS 上 大文字小文字を区別しない（`VAR(--x)` も有効）。
# 変数名側は区別する（`--Foo` と `--foo` は別変数）ので、文字クラスで両方を明示する。
_VAR_REF_RE = re.compile(r"var\(\s*(--[A-Za-z0-9_-]+)", re.IGNORECASE)


def strip_css_comments(text: str) -> str:
    """`/* ... */` を除去する。除去部分の改行は残し、行番号をずらさない。"""
    return _COMMENT_RE.sub(lambda m: "\n" * m.group(0).count("\n"), text)


def parse_declarations(text: str) -> list[tuple[str, str, int]]:
    """`(変数名, 値, 1 始まりの行番号)` の一覧を返す（コメントは除去してから走査する）。"""
    stripped = strip_css_comments(text)
    out: list[tuple[str, str, int]] = []
    for m in _DECL_RE.finditer(stripped):
        line = stripped.count("\n", 0, m.start()) + 1
        out.append((m.group(1), m.group(2), line))
    return out


def extract_var_refs(value: str) -> list[str]:
    """値の中の `var(--x)` 参照名を出現順に返す。

    `var(--a, var(--b))` のフォールバック側も辺として数える（フォールバックが評価される
    経路でも循環しうるため。fail-closed 側に倒す）。
    """
    return _VAR_REF_RE.findall(value)


def find_css_files(paths: list[Path]) -> list[Path]:
    """ファイル / ディレクトリの指定から `.css` を集める。存在しないパスは FileNotFoundError。"""
    found: list[Path] = []
    for p in paths:
        if not p.exists():
            raise FileNotFoundError(str(p))
        if p.is_file():
            if p.suffix == ".css":
                found.append(p)
            continue
        for f in sorted(p.rglob("*.css")):
            if any(part in EXCLUDED_DIRS for part in f.relative_to(p).parts):
                continue
            found.append(f)
    # 同じファイルを 2 度数えない（ファイルとその親ディレクトリを同時に指定した場合）
    seen: set[Path] = set()
    uniq: list[Path] = []
    for f in found:
        rp = f.resolve()
        if rp in seen:
            continue
        seen.add(rp)
        uniq.append(f)
    return uniq


def find_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    """有向グラフの閉路を列挙する（自己ループは呼び出し側が除いてから渡す）。

    回転を正規化して同じ閉路を 1 度だけ返す。
    """
    cycles: set[tuple[str, ...]] = set()
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {n: WHITE for n in graph}

    def canonical(cycle: list[str]) -> tuple[str, ...]:
        i = cycle.index(min(cycle))
        return tuple(cycle[i:] + cycle[:i])

    for start in sorted(graph):
        if color[start] != WHITE:
            continue
        # 明示スタックの反復 DFS（深い依存でも再帰上限に当たらない）
        stack: list[tuple[str, list[str]]] = [(start, [])]
        path: list[str] = []
        while stack:
            node, remaining = stack.pop()
            if remaining == []:
                if color.get(node, WHITE) == GRAY:
                    # 既に path 上にある = 閉路
                    idx = path.index(node)
                    cycles.add(canonical(path[idx:]))
                    continue
                if color.get(node, WHITE) == BLACK:
                    continue
                color[node] = GRAY
                path.append(node)
                stack.append((node, ["__done__"]))
                for nxt in sorted(graph.get(node, ()), reverse=True):
                    stack.append((nxt, []))
            else:
                color[node] = BLACK
                if path and path[-1] == node:
                    path.pop()
    return [list(c) for c in sorted(cycles)]


def analyze(files: list[Path]) -> tuple[list[str], int]:
    """違反メッセージ一覧と、読み取った変数宣言の件数を返す。"""
    graph: dict[str, set[str]] = {}
    edge_site: dict[tuple[str, str], str] = {}
    self_refs: list[str] = []
    decl_count = 0

    for f in files:
        text = f.read_text(encoding="utf-8")
        try:
            rel = f.resolve().relative_to(REPO_ROOT)
            label = str(rel)
        except ValueError:
            label = str(f)
        for name, value, line in parse_declarations(text):
            decl_count += 1
            graph.setdefault(name, set())
            for ref in extract_var_refs(value):
                graph.setdefault(ref, set())
                if ref == name:
                    self_refs.append(
                        f"{label}:{line} 自己参照: {name} が自分自身を参照しています"
                        f"（`{name}: {value.strip()}`）。CSS はこの宣言を無効値として黙って捨てます"
                    )
                    continue
                graph[name].add(ref)
                edge_site.setdefault((name, ref), f"{label}:{line}")

    violations = list(self_refs)
    for cycle in find_cycles(graph):
        hops = []
        for i, node in enumerate(cycle):
            nxt = cycle[(i + 1) % len(cycle)]
            hops.append(f"{node} -> {nxt}（{edge_site.get((node, nxt), '?')}）")
        violations.append("循環参照: " + " / ".join(hops))
    return violations, decl_count


def run_check(paths: list[Path]) -> int:
    try:
        files = find_css_files(paths)
    except FileNotFoundError as e:
        print(
            f"[check_css_variable_cycles] 判定不能: 指定パスが存在しません: {e}",
            file=sys.stderr,
        )
        return 2

    # 対象 0 件は fail-closed（check-tool-design-rules.md §2）。
    # 「本当に CSS が無い」のか「対象の選択が壊れている」のかを終了コードで区別できないため。
    if not files:
        print(
            "[check_css_variable_cycles] 判定不能: 検査対象の .css が 1 件も見つかりません。"
            "対象の選択が意図どおりか確認してください",
            file=sys.stderr,
        )
        return 2

    try:
        violations, decl_count = analyze(files)
    except OSError as e:
        print(
            f"[check_css_variable_cycles] 判定不能: CSS を読み取れません: {e}",
            file=sys.stderr,
        )
        return 2

    if decl_count == 0:
        print(
            f"[check_css_variable_cycles] 判定不能: {len(files)} 件の .css に CSS 変数の宣言が"
            " 1 件もありません。対象の選択が意図どおりか確認してください",
            file=sys.stderr,
        )
        return 2

    if violations:
        print(f"[check_css_variable_cycles] ❌ {len(violations)} 件の違反:")
        for v in violations:
            print(f"  - {v}")
        print(
            "  ヒント: CSS 変数の解決失敗はエラーにならず値が消えるだけです（Issue #858 の"
            " --font-sans: var(--font-sans) が実例）",
        )
        return 1

    print(
        f"[check_css_variable_cycles] PASS（{len(files)} ファイル / {decl_count} 宣言 —"
        " 自己参照・循環参照なし）"
    )
    return 0


# --------------------------------------------------------------------------- self-test


def _write(tmpdir: Path, name: str, body: str) -> Path:
    p = tmpdir / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def self_test() -> int:
    failures: list[str] = []
    total = 0

    def check(label: str, cond: bool) -> None:
        nonlocal total
        total += 1
        if not cond:
            failures.append(label)

    import io
    import contextlib

    def run_main(argv: list[str]) -> tuple[int, str]:
        """本番の入口 main() を経由して終了コードと出力を得る（内部関数の直呼びにしない）。"""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            code = main(argv)
        return code, buf.getvalue()

    CLEAN_TAIL = ":root {\n  --background: oklch(1 0 0);\n}\n"

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # --- 1. #858 回帰ケース: 修正前の app/globals.css の先頭 16 行を逐語で再現し、
        #        自己参照が **13 行目** として報告されることまで固定する。
        #        4〜5 行目の複数行コメントを含むので、コメント除去が行番号をずらさないことも同時に見る。
        f = _write(
            tmp,
            "regress858.css",
            "@import 'tailwindcss';\n"
            "@import 'tw-animate-css';\n"
            "@import 'shadcn/tailwind.css';\n"
            "/* README 本文（第三者 HTML）の書式付与に使う。Tailwind v4 は tailwind.config.js を\n"
            "   持たないため CSS 側の @plugin ディレクティブでプラグインを読み込む（Issue #339）。 */\n"
            '@plugin "@tailwindcss/typography";\n'
            "\n"
            "@custom-variant dark (&:is(.dark *));\n"
            "\n"
            "@theme inline {\n"
            "  --color-background: var(--background);\n"
            "  --color-foreground: var(--foreground);\n"
            "  --font-sans: var(--font-sans);\n"  # ← #858 の修正前（13 行目）
            "  --font-mono: var(--font-geist-mono);\n"
            "  --font-heading: var(--font-sans);\n"
            "}\n" + CLEAN_TAIL,
        )
        code, out = run_main([str(f)])
        check("1. #858 の自己参照で exit 1", code == 1)
        check(
            "1-b. 違反が --font-sans の 13 行目として報告される",
            "--font-sans" in out and "regress858.css:13" in out,
        )
        # 自己参照は「循環参照」ではなく専用メッセージで報告する（自己ループは閉路検出でも
        # 拾えてしまうため、この assert が無いと自己参照の判定分岐が変異で消えても気づけない）
        check(
            "1-c. 自己参照として報告される（循環参照メッセージへの退行を防ぐ）",
            "自己参照" in out and "循環参照" not in out,
        )

        # --- 2. 空白・改行・大文字のバリアント
        for i, body in enumerate(
            [
                "a{--foo:var(--foo)}\n" + CLEAN_TAIL,  # 空白なし・末尾 ; なし
                ":root{\n  --foo: var( --foo )\n  ;\n}\n"
                + CLEAN_TAIL,  # var( 内側空白 )・改行跨ぎ
                ":root{ --foo: VAR(--foo); }\n"
                + CLEAN_TAIL,  # 関数名は大文字小文字非依存
            ]
        ):
            f = _write(tmp, f"variant{i}.css", body)
            code, _ = run_main([str(f)])
            check(f"2-{i}. 自己参照バリアントで exit 1", code == 1)

        # --- 3. 間接サイクル（2 段 / 3 段）
        f = _write(
            tmp, "cycle2.css", ":root{ --a: var(--b); --b: var(--a); }\n" + CLEAN_TAIL
        )
        code, out = run_main([str(f)])
        check("3. 2 段サイクルで exit 1", code == 1)
        check("3-b. 循環経路が出力される", "--a" in out and "--b" in out)

        f = _write(
            tmp,
            "cycle3.css",
            ":root{ --a: var(--b); --b: var(--c); --c: var(--a); }\n" + CLEAN_TAIL,
        )
        code, _ = run_main([str(f)])
        check("4. 3 段サイクルで exit 1", code == 1)

        # --- 5. 正常系（エイリアス連鎖・未定義参照は違反にしない）
        f = _write(
            tmp,
            "clean.css",
            "@theme inline {\n"
            "  --font-sans: var(--font-geist-sans);\n"  # 未定義参照（next/font 注入）→ 違反にしない
            "  --font-heading: var(--font-sans);\n"
            "  --color-bg: var(--background);\n"
            "}\n" + CLEAN_TAIL,
        )
        code, out = run_main([str(f)])
        check("5. 正常な CSS で exit 0", code == 0)

        # --- 6. 境界の外側（前方一致では同一に見えるが別変数）
        f = _write(
            tmp,
            "prefix.css",
            ":root{ --foo: var(--foobar); --foobar: oklch(1 0 0); }\n",
        )
        code, out = run_main([str(f)])
        check("6. --foo -> --foobar は自己参照でない（exit 0）", code == 0)
        f = _write(
            tmp, "prefix2.css", ":root{ --foobar: var(--foo); --foo: var(--foobar); }\n"
        )
        code, _ = run_main([str(f)])
        check("6-b. --foo <-> --foobar は本物の循環なので exit 1", code == 1)
        # 参照名が定義名の前方一致（`--foobar`.startswith(`--foo`)）でも自己参照ではない。
        # 等値比較が前方一致へ退行すると、この正常系が誤検知で落ちる。
        f = _write(
            tmp, "prefix3.css", ":root{ --foobar: var(--foo); --foo: oklch(1 0 0); }\n"
        )
        code, out = run_main([str(f)])
        check("6-c. --foobar: var(--foo) を自己参照と誤判定しない（exit 0）", code == 0)

        # --- 7. コメント内の自己参照は違反にしない
        f = _write(
            tmp,
            "comment.css",
            ":root{\n  /* 旧値は --foo: var(--foo); だった（#858 で是正） */\n"
            "  --foo: oklch(1 0 0);\n}\n",
        )
        code, _ = run_main([str(f)])
        check("7. コメント内の自己参照は違反にしない（exit 0）", code == 0)

        # --- 8. fallback 構文の中の参照も辺として数える
        f = _write(
            tmp, "fallback.css", ":root{ --a: var(--b, 1px); --b: var(--a, 2px); }\n"
        )
        code, _ = run_main([str(f)])
        check(
            "8. var(--x, fallback) の中の参照も循環として検出する（exit 1）", code == 1
        )
        # フォールバック **の内側** にネストした参照（`var(--x, var(--b))`）も辺として数える。
        # 第 1 引数だけを見る実装へ退行すると、この循環を見落とす。
        f = _write(
            tmp,
            "fallback_nested.css",
            ":root{ --a: var(--x, var(--b)); --b: var(--a); }\n",
        )
        code, _ = run_main([str(f)])
        check(
            "8-b. フォールバック内側にネストした参照も循環として検出する（exit 1）",
            code == 1,
        )

        # --- 9. 対象 0 件は fail-closed
        empty_dir = tmp / "empty"
        empty_dir.mkdir()
        code, out = run_main([str(empty_dir)])
        check("9. CSS ファイル 0 件で exit 2", code == 2)

        f = _write(tmp, "novars.css", "body { color: red; }\n")
        code, out = run_main([str(f)])
        check("10. 変数定義 0 件で exit 2", code == 2)

        # --- 11. 存在しないパスは判定不能
        code, _ = run_main([str(tmp / "does-not-exist.css")])
        check("11. 存在しないパスで exit 2", code == 2)

        # --- 12. スクリプト実体を subprocess 起動し `sys.exit(main())` まで貫通させる
        f = _write(tmp, "sub.css", ":root{ --x: var(--x); }\n")
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), str(f)],
            capture_output=True,
            text=True,
        )
        check(
            "12. subprocess 起動でも exit 1 が返る（sys.exit(main()) 経路）",
            proc.returncode == 1,
        )

    if failures:
        print("[check_css_variable_cycles --self-test] FAIL:")
        for f_ in failures:
            print(f"  - {f_}")
        return 1
    print(
        f"[check_css_variable_cycles --self-test] PASS（{total} 件のアサーション全て成功）"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--self-test" in args:
        return self_test()
    paths = [Path(a) for a in args if not a.startswith("-")]
    if not paths:
        paths = [REPO_ROOT]
    return run_check(paths)


if __name__ == "__main__":
    sys.exit(main())
