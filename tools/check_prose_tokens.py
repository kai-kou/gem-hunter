#!/usr/bin/env python3
"""check_prose_tokens.py — `--tw-prose-*` トークンへのリテラル色混入検査（Issue #339）

SSOT: `content/discussions/readme_typography_20260821/whiteboard.md` round3 `lead` の合意・裁定
（争点 A・条件 1〜3）。`@tailwindcss/typography` の `--tw-prose-*`（18 項目）を本プロジェクトの
セマンティックトークンへ全マッピングする方針において、**書き忘れがプラグイン既定の gray スケールへ
静かにフォールバックする** ことを検知するための機械ゲート。

検査内容:
  `app/globals.css` 内の `--tw-prose-*` 宣言の **値** を全件抽出し、以下のいずれかであることを確認する。
    - `var(--color-*)` への参照（フォールバック値にもリテラル色が無いこと）
    - 無彩な keyword（`transparent` / `none` / `inherit` / `unset` / `revert` / `initial` /
      `currentcolor`）
  上記のどちらでもない値（`oklch(...)` / `#RRGGBB` / `rgb(...)` / `rgba(...)` / `hsl(...)` /
  `hsla(...)` などのリテラル色、Tailwind の gray スケール直書き、`red` 等の CSS 名前付きカラー
  直書き）は違反として報告する。`var(--color-fg, red)` のように **フォールバック値へ名前付き
  カラーを紛れ込ませた場合も同様に違反とする**（Layer 1 セルフレビュー指摘対応・2026-08-21）。

🔴 **`--tw-prose-*` が 1 つも無い状態でも異常終了しない**（PASS を返す）。typography プラグイン
導入前（本チェック追加時点）でも `run_checks.sh` を壊さないための必須要件。

使い方:
  python3 tools/check_prose_tokens.py             # app/globals.css を検査
  python3 tools/check_prose_tokens.py --self-test  # 検出ロジックの自己テスト（ネットワーク不要）
  違反があれば exit 1（該当行を表示）。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CSS_PATH = REPO_ROOT / "app" / "globals.css"

# `--tw-prose-xxx: 値;` を丸ごと拾う（値の中に `;` を含まない前提。CSS カスタムプロパティの
# 値としてセミコロンを含むケース＝ `content: ";"` 等は typography トークンでは発生しない）。
PROSE_DECL_RE = re.compile(r"(--tw-prose-[a-zA-Z0-9-]+)\s*:\s*([^;]+);")

# リテラル色として弾く関数記法・16進カラー。
FORBIDDEN_COLOR_PATTERNS = [
    re.compile(r"oklch\(", re.IGNORECASE),
    re.compile(r"oklab\(", re.IGNORECASE),
    re.compile(r"lab\(", re.IGNORECASE),
    re.compile(r"lch\(", re.IGNORECASE),
    re.compile(r"color-mix\(", re.IGNORECASE),
    re.compile(r"rgba?\(", re.IGNORECASE),
    re.compile(r"hsla?\(", re.IGNORECASE),
    re.compile(r"#[0-9a-fA-F]{3,8}\b"),
]

# 無彩色として許可する keyword（大文字小文字を区別しない）。
ALLOWED_KEYWORDS = {"transparent", "none", "inherit", "unset", "revert", "initial", "currentcolor"}

# 許可するトークン参照（セマンティックトークンへの `var()` 参照）。
ALLOWED_VAR_RE = re.compile(r"var\(\s*--color-[a-zA-Z0-9-]+")

# Layer 1 セルフレビュー指摘対応（WARNING）: `var(--color-accent, red)` のように、フォールバック値
# へ CSS 名前付きカラー（裸の識別子）を紛れ込ませる抜け道を塞ぐための検出。
# 147 色の名前付きカラー一覧を維持する代わりに「拒否リスト方式」を採る: カスタムプロパティ参照
# （`--color-fg` 等）と `var` という関数名そのものを取り除いた残りに、無彩 keyword 以外の
# 裸のアルファベット識別子が 1 つでも残っていれば違反とみなす。
CUSTOM_PROP_TOKEN_RE = re.compile(r"--[a-zA-Z0-9-]+")
BARE_WORD_RE = re.compile(r"[a-zA-Z]{2,}")
BARE_WORD_ALLOWLIST = {"var"}


def _strip_important(value: str) -> str:
    """末尾の `!important` を除いた値を返す（判定対象を実質値だけに揃える）。"""
    return re.sub(r"!\s*important\s*$", "", value, flags=re.IGNORECASE).strip()


def contains_forbidden_color(value: str) -> bool:
    """値の中にリテラル色（関数記法 / 16進）が混入していれば True。"""
    return any(pattern.search(value) for pattern in FORBIDDEN_COLOR_PATTERNS)


def contains_bare_named_color(value: str) -> bool:
    """`var(--color-fg, red)` のように、フォールバックへ CSS 名前付きカラー（裸の識別子）が
    紛れ込んでいれば True。

    カスタムプロパティ参照（`--color-fg` 等）と `var` という関数名自体を取り除いた残りに、
    無彩 keyword（`ALLOWED_KEYWORDS`）以外の裸のアルファベット識別子が 1 つでも残っていれば
    違反とみなす。147 色の CSS 名前付きカラー一覧を維持しなくても、この対象（`--tw-prose-*`
    はすべて色専用のカスタムプロパティ）では「裸の識別子は許可キーワード以外あり得ない」ため
    拒否リスト方式で十分に検出できる。
    """
    without_custom_props = CUSTOM_PROP_TOKEN_RE.sub("", value)
    for word in BARE_WORD_RE.findall(without_custom_props):
        lowered = word.lower()
        if lowered in BARE_WORD_ALLOWLIST or lowered in ALLOWED_KEYWORDS:
            continue
        return True
    return False


def is_allowed_value(raw_value: str) -> bool:
    """`--tw-prose-*` の値として許可できるかを判定する。

    許可: ① 無彩な keyword そのもの ② `var(--color-*)` 参照（かつフォールバックにも
    リテラル色が無いこと）。それ以外（リテラル色・裸の gray スケール名など）はすべて不許可。
    """
    value = _strip_important(raw_value)
    if value.lower() in ALLOWED_KEYWORDS:
        return True
    if ALLOWED_VAR_RE.search(value):
        # var(--color-fg, #000) / var(--color-fg, red) のように、フォールバックへリテラル色
        # （関数記法・16進・名前付きカラー）を紛れ込ませていないか確認する。
        if contains_forbidden_color(value):
            return False
        return not contains_bare_named_color(value)
    return False


def find_violations(css_text: str) -> list[tuple[int, str, str]]:
    """`css_text` 中の `--tw-prose-*` 宣言のうち、許可されない値を持つものを列挙する。

    戻り値: (行番号, プロパティ名, 値) のリスト。
    """
    violations: list[tuple[int, str, str]] = []
    for match in PROSE_DECL_RE.finditer(css_text):
        name, value = match.group(1), match.group(2).strip()
        if is_allowed_value(value):
            continue
        line_no = css_text.count("\n", 0, match.start()) + 1
        violations.append((line_no, name, value))
    return violations


def run_check() -> int:
    if not CSS_PATH.exists():
        print(f"[check_prose_tokens] FAIL: {CSS_PATH} が見つかりません", file=sys.stderr)
        return 1

    css_text = CSS_PATH.read_text(encoding="utf-8")
    declared = PROSE_DECL_RE.findall(css_text)

    if not declared:
        # 🔴 typography プラグイン導入前（`--tw-prose-*` が 1 つも無い）は異常ではなく
        #    「まだ対象が無い」だけなので PASS を返す（run_checks.sh を壊さない必須要件）。
        print("[check_prose_tokens] PASS: --tw-prose-* は未定義（0 件・検査対象なしのため合格）")
        return 0

    violations = find_violations(css_text)
    if violations:
        rel = CSS_PATH.relative_to(REPO_ROOT)
        for line_no, name, value in violations:
            print(f"{rel}:{line_no}: リテラル色が混入しています: {name}: {value};")
        print(
            f"\n[check_prose_tokens] FAIL: {len(violations)} 件のリテラル色混入を検出"
            f"（{len(declared)} 件中）。\n"
            "   var(--color-*) へのセマンティックトークン参照、または transparent / none / "
            "inherit 等の無彩 keyword のみ許可されます。",
            file=sys.stderr,
        )
        return 1

    print(f"[check_prose_tokens] PASS: --tw-prose-* {len(declared)} 件すべてトークン参照/無彩値")
    return 0


# --------------------------------------------------------------------------- self-test

def self_test() -> int:
    failures: list[str] = []
    total = 0

    def check(name: str, cond: bool) -> None:
        nonlocal total
        total += 1
        if not cond:
            failures.append(name)

    # 1. --tw-prose-* が 1 つも無い CSS は PASS（異常終了しない）。
    no_decl_css = ":root {\n  --color-fg: oklch(0.2 0 0);\n}\n"
    check(
        "宣言なし -> 違反ゼロ",
        find_violations(no_decl_css) == [],
    )

    # 2. var(--color-*) 参照は許可。
    check(
        "var(--color-fg) は許可",
        is_allowed_value("var(--color-fg)") is True,
    )

    # 3. 無彩 keyword は許可（大文字小文字を区別しない）。
    for kw in ["transparent", "none", "inherit", "unset", "revert", "initial", "CurrentColor"]:
        check(f"keyword 許可: {kw}", is_allowed_value(kw) is True)

    # 4. リテラル色は不許可（oklch / hex / rgb / rgba / hsl / hsla）。
    check("oklch(...) は不許可", is_allowed_value("oklch(0.2 0 0)") is False)
    check("#RRGGBB は不許可", is_allowed_value("#3b82f6") is False)
    check("#RGB は不許可", is_allowed_value("#fff") is False)
    check("rgb(...) は不許可", is_allowed_value("rgb(255 0 0)") is False)
    check("rgba(...) は不許可", is_allowed_value("rgba(255, 0, 0, .5)") is False)
    check("hsl(...) は不許可", is_allowed_value("hsl(200 50% 50%)") is False)

    # 5. gray スケール名の直書き（var() 経由でない）は不許可。
    check("裸のキーワード（gray スケール等）は不許可", is_allowed_value("gray") is False)

    # 6. var(--color-*) のフォールバックにリテラル色が混入していれば不許可。
    check(
        "var() フォールバックへのリテラル色混入は不許可",
        is_allowed_value("var(--color-fg, #000000)") is False,
    )

    # 6.5. Layer 1 セルフレビュー指摘対応: var() フォールバックへの CSS 名前付きカラー混入も不許可
    #      （修正前は is_allowed_value("var(--color-accent, red)") が True を返す抜け道だった）。
    check(
        "var() フォールバックへの名前付きカラー(red)混入は不許可",
        is_allowed_value("var(--color-accent, red)") is False,
    )
    check(
        "var() フォールバックへの名前付きカラー(blue)混入は不許可（別トークン名でも検出）",
        is_allowed_value("var(--color-fg, blue)") is False,
    )
    check(
        "contains_bare_named_color: var(--color-fg, red) は True",
        contains_bare_named_color("var(--color-fg, red)") is True,
    )
    check(
        "contains_bare_named_color: var(--color-fg) 単体は False（誤検知しない）",
        contains_bare_named_color("var(--color-fg)") is False,
    )
    check(
        "contains_bare_named_color: var(--color-fg, transparent) は無彩 keyword なので False",
        contains_bare_named_color("var(--color-fg, transparent)") is False,
    )

    # 7. !important が付いていても判定できる。
    check(
        "!important 付き var() は許可",
        is_allowed_value("var(--color-fg) !important") is True,
    )
    check(
        "!important 付きリテラル色は不許可",
        is_allowed_value("oklch(0.2 0 0) !important") is False,
    )

    # 8. find_violations: 正常な CSS 全体からは違反を検出しない（行番号も含めて回帰確認）。
    clean_css = (
        ":root {\n"
        "  --color-fg: oklch(0.2 0 0);\n"
        "}\n"
        ".prose {\n"
        "  --tw-prose-body: var(--color-fg);\n"
        "  --tw-prose-headings: var(--color-fg);\n"
        "  --tw-prose-hr: transparent;\n"
        "}\n"
    )
    check("正常な CSS は違反ゼロ", find_violations(clean_css) == [])

    # 9. find_violations: 違反行が正しく検出され、行番号も一致する。
    bad_css = (
        ":root {\n"
        "  --color-fg: oklch(0.2 0 0);\n"
        "}\n"
        ".prose {\n"
        "  --tw-prose-body: var(--color-fg);\n"
        "  --tw-prose-links: oklch(0.5 0.2 250);\n"
        "  --tw-prose-code: #ff0000;\n"
        "}\n"
    )
    bad_violations = find_violations(bad_css)
    check("違反 2 件を検出", len(bad_violations) == 2)
    check(
        "違反箇所のプロパティ名が一致",
        {v[1] for v in bad_violations} == {"--tw-prose-links", "--tw-prose-code"},
    )
    check(
        "違反行番号が正しい（6・7 行目）",
        {v[0] for v in bad_violations} == {6, 7},
    )

    # 10. --tw-prose- 以外の CSS 変数は検査対象に含めない。
    unrelated_css = ":root {\n  --color-fg: #ff0000;\n  --tw-prose-body: var(--color-fg);\n}\n"
    check(
        "--tw-prose- 以外の宣言は検査対象外",
        find_violations(unrelated_css) == [],
    )

    if failures:
        print("[check_prose_tokens --self-test] FAIL:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"[check_prose_tokens --self-test] PASS（{total} 件のアサーション全て成功）")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--self-test", action="store_true", help="ネットワーク不要のユニットテストを実行")
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    return run_check()


if __name__ == "__main__":
    sys.exit(main())
