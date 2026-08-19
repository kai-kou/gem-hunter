#!/usr/bin/env python3
"""check_contrast.py — セマンティックカラートークンのコントラスト比 実測ゲート（E-9 / NFR-13）

SSOT: `docs/03_design/ui-ux/ui-ux-guidelines.md` §2.1 / §2.2。

`app/globals.css` の `:root`（ライト）/ `.dark`（ダーク）ブロックから
セマンティックトークンの実体（既存 shadcn raw 変数 `--background` / `--muted` / `--foreground` /
`--muted-foreground` / `--border` / `--accent` / `--accent-foreground` / `--destructive` /
`--destructive-foreground`。`@theme inline` の `--color-bg` 等はこれらへのエイリアス）を読み取り、
WCAG 2.x の相対輝度式でコントラスト比を計算する。oklch() 記法のため、oklch → 線形 sRGB → sRGB の
変換を自前実装する（外部ライブラリ・ネットワーク接続は使わない）。

検査するペア（§2.1 の表に対応。計 9 ペア × ライト/ダーク = 18 判定）:
  fg        vs bg         (>= 4.5:1)  本文
  fg        vs bg-subtle  (>= 4.5:1)  本文（カード面）
  fg-muted  vs bg         (>= 4.5:1)  メタ情報
  fg-muted  vs bg-subtle  (>= 4.5:1)  メタ情報（カード面）
  border    vs bg         (>= 3.0:1)  カード枠・区切り線
  accent    vs bg         (>= 4.5:1)  リンク・アクセント文字色
  accent-fg vs accent     (>= 4.5:1)  アクセント面上のテキスト（主ボタン）
  danger    vs bg         (>= 4.5:1)  エラー文字色
  danger-fg vs danger     (>= 4.5:1)  エラー面上のテキスト

使い方:
  python3 tools/check_contrast.py            # app/globals.css を検査
  python3 tools/check_contrast.py --self-test  # 変換・計算ロジックの自己テスト（ネットワーク不要）
  しきい値を下回るペアがあれば exit 1。
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CSS_PATH = REPO_ROOT / "app" / "globals.css"

# --------------------------------------------------------------------------- oklch → sRGB 変換

_OKLCH_RE = re.compile(
    r"oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)"
    r"(?:\s*/\s*([\d.]+%?))?\s*\)"
)


def parse_oklch(value: str) -> tuple[float, float, float, float]:
    """'oklch(L C H)' / 'oklch(L C H / A%)' を (L, C, H, alpha) にパースする。alpha 省略時は 1.0。"""
    m = _OKLCH_RE.search(value.strip())
    if not m:
        raise ValueError(f"oklch() として解釈できません: {value!r}")
    L = float(m.group(1))
    C = float(m.group(2))
    H = float(m.group(3))
    alpha_raw = m.group(4)
    if alpha_raw is None:
        alpha = 1.0
    elif alpha_raw.endswith("%"):
        alpha = float(alpha_raw[:-1]) / 100.0
    else:
        alpha = float(alpha_raw)
    return (L, C, H, alpha)


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _linear_to_srgb(c: float) -> float:
    if c <= 0.0031308:
        return 12.92 * c
    return 1.055 * (c ** (1.0 / 2.4)) - 0.055


def oklch_to_srgb(L: float, C: float, H: float) -> tuple[float, float, float]:
    """OKLCH -> 線形 sRGB -> ガンマ補正 sRGB（0-1、クランプ済み）。

    変換式は Björn Ottosson の OKLab/OKLCH 定義（CSS Color Module 4 が採用する一次仕様）に
    基づく。既知値は --self-test で検証する。
    """
    hrad = math.radians(H)
    a = C * math.cos(hrad)
    b = C * math.sin(hrad)

    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b

    l = l_ ** 3
    m = m_ ** 3
    s = s_ ** 3

    r_lin = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g_lin = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    b_lin = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s

    r = _clamp01(_linear_to_srgb(r_lin))
    g = _clamp01(_linear_to_srgb(g_lin))
    bl = _clamp01(_linear_to_srgb(b_lin))
    return (r, g, bl)


def oklch_str_to_srgb(value: str) -> tuple[float, float, float]:
    """oklch() 文字列 -> sRGB 0-1 タプル（alpha は無視。単独色の変換用）。"""
    L, C, H, _alpha = parse_oklch(value)
    return oklch_to_srgb(L, C, H)


def blend_over(fg_srgb: tuple[float, float, float], alpha: float,
                bg_srgb: tuple[float, float, float]) -> tuple[float, float, float]:
    """fg（alpha 付き）を bg の上に単純アルファ合成する（sRGB ガンマ空間で合成。CSS 既定挙動）。"""
    return tuple(alpha * f + (1 - alpha) * b for f, b in zip(fg_srgb, bg_srgb))  # type: ignore[return-value]


# --------------------------------------------------------------------------- WCAG 相対輝度・コントラスト比

def relative_luminance(srgb: tuple[float, float, float]) -> float:
    def chan(c: float) -> float:
        if c <= 0.03928:
            return c / 12.92
        return ((c + 0.055) / 1.055) ** 2.4

    r, g, b = srgb
    return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)


def contrast_ratio(srgb1: tuple[float, float, float], srgb2: tuple[float, float, float]) -> float:
    l1 = relative_luminance(srgb1)
    l2 = relative_luminance(srgb2)
    lighter, darker = (l1, l2) if l1 >= l2 else (l2, l1)
    return (lighter + 0.05) / (darker + 0.05)


# --------------------------------------------------------------------------- CSS パース

def extract_block(css_text: str, selector: str) -> str:
    """`selector { ... }` の直近 1 ブロックの中身を返す（ネストなし前提。globals.css の実構造に対応）。

    `selector` の後ろに（空白を挟んで）`{` が続く出現だけを対象にする。`.dark` は
    `@custom-variant dark (&:is(.dark *));` のような他行にも部分一致するため、
    厳密な `セレクタ + 空白* + {` パターンでのみマッチさせる。
    """
    pattern = re.compile(re.escape(selector) + r"\s*\{")
    m = pattern.search(css_text)
    if not m:
        raise ValueError(f"セレクタが見つかりません: {selector!r}")
    brace_start = css_text.index("{", m.start())
    if brace_start == -1:
        raise ValueError(f"セレクタ {selector!r} の開き波括弧が見つかりません")
    depth = 0
    for i in range(brace_start, len(css_text)):
        if css_text[i] == "{":
            depth += 1
        elif css_text[i] == "}":
            depth -= 1
            if depth == 0:
                return css_text[brace_start + 1:i]
    raise ValueError(f"セレクタ {selector!r} の閉じ波括弧が見つかりません")


_DECL_RE = re.compile(r"--([\w-]+)\s*:\s*([^;]+);")


def parse_declarations(block: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for m in _DECL_RE.finditer(block):
        result[m.group(1)] = m.group(2).strip()
    return result


# --------------------------------------------------------------------------- セマンティックトークン定義

# raw 変数名（app/globals.css の :root / .dark に実値を置く既存 shadcn 変数を意味づけとして再利用）
# 対応表: --color-bg=background / --color-bg-subtle=muted / --color-fg=foreground /
#        --color-fg-muted=muted-foreground / --color-border=border / --color-accent=accent /
#        --color-accent-fg=accent-foreground / --color-danger=destructive /
#        --color-danger-fg=destructive-foreground
SEMANTIC_VARS = [
    "background",
    "muted",
    "foreground",
    "muted-foreground",
    "border",
    "accent",
    "accent-foreground",
    "destructive",
    "destructive-foreground",
]

# (fg変数, bg変数, しきい値, ラベル)
CHECK_PAIRS = [
    ("foreground", "background", 4.5, "--color-fg vs --color-bg（本文）"),
    ("foreground", "muted", 4.5, "--color-fg vs --color-bg-subtle（本文・カード面）"),
    ("muted-foreground", "background", 4.5, "--color-fg-muted vs --color-bg（メタ情報）"),
    ("muted-foreground", "muted", 4.5, "--color-fg-muted vs --color-bg-subtle（メタ情報・カード面）"),
    ("border", "background", 3.0, "--color-border vs --color-bg（カード枠・区切り線）"),
    ("accent", "background", 4.5, "--color-accent vs --color-bg（リンク文字色）"),
    ("accent-foreground", "accent", 4.5, "--color-accent-fg vs --color-accent（主ボタン文字色）"),
    ("destructive", "background", 4.5, "--color-danger vs --color-bg（エラー文字色）"),
    ("destructive-foreground", "destructive", 4.5, "--color-danger-fg vs --color-danger（エラー面文字色）"),
]


def resolve_srgb(var_name: str, decls: dict[str, str], bg_context_srgb: tuple[float, float, float]) -> tuple[float, float, float]:
    """変数を sRGB へ解決する。alpha < 1 の場合は bg_context_srgb の上に合成する。"""
    if var_name not in decls:
        raise ValueError(f"変数が宣言されていません: --{var_name}")
    L, C, H, alpha = parse_oklch(decls[var_name])
    srgb = oklch_to_srgb(L, C, H)
    if alpha < 1.0:
        srgb = blend_over(srgb, alpha, bg_context_srgb)
    return srgb


def evaluate_theme(theme_name: str, decls: dict[str, str]) -> tuple[bool, list[str]]:
    ok = True
    lines: list[str] = []
    missing = [v for v in SEMANTIC_VARS if v not in decls]
    if missing:
        lines.append(f"[{theme_name}] 未宣言の変数: {', '.join('--' + v for v in missing)}")
        return False, lines

    bg_srgb = oklch_to_srgb(*parse_oklch(decls["background"])[:3])

    for fg_var, bg_var, threshold, label in CHECK_PAIRS:
        bg_context = bg_srgb if bg_var == "background" else resolve_srgb(bg_var, decls, bg_srgb)
        fg_srgb = resolve_srgb(fg_var, decls, bg_context)
        bg_resolved = resolve_srgb(bg_var, decls, bg_srgb)
        ratio = contrast_ratio(fg_srgb, bg_resolved)
        status = "PASS" if ratio >= threshold else "FAIL"
        if status == "FAIL":
            ok = False
        lines.append(
            f"[{theme_name}] {label}: {ratio:.2f}:1（しきい値 {threshold}:1）... {status}"
        )
    return ok, lines


def run_check() -> int:
    if not CSS_PATH.exists():
        print(f"[check_contrast] FAIL: {CSS_PATH} が見つかりません")
        return 1

    css_text = CSS_PATH.read_text(encoding="utf-8")
    try:
        root_block = extract_block(css_text, ":root")
        dark_block = extract_block(css_text, ".dark")
    except ValueError as e:
        print(f"[check_contrast] FAIL: {e}")
        return 1

    root_decls = parse_declarations(root_block)
    dark_decls = parse_declarations(dark_block)

    ok_light, lines_light = evaluate_theme("ライト", root_decls)
    ok_dark, lines_dark = evaluate_theme("ダーク", dark_decls)

    for line in lines_light + lines_dark:
        print(line)

    if ok_light and ok_dark:
        print("[check_contrast] PASS: 9 トークン × ライト/ダーク 計 18 ペア、全てしきい値を満たしています")
        return 0

    print("[check_contrast] FAIL: しきい値を下回るペアがあります")
    return 1


# --------------------------------------------------------------------------- self-test

def self_test() -> int:
    failures: list[str] = []
    total = 0

    def check(name: str, cond: bool):
        nonlocal total
        total += 1
        if not cond:
            failures.append(name)

    # 既知値: oklch(1 0 0) は白
    r, g, b = oklch_str_to_srgb("oklch(1 0 0)")
    check("oklch(1 0 0) -> 白", abs(r - 1.0) < 1e-3 and abs(g - 1.0) < 1e-3 and abs(b - 1.0) < 1e-3)

    # 既知値: oklch(0 0 0) は黒
    r, g, b = oklch_str_to_srgb("oklch(0 0 0)")
    check("oklch(0 0 0) -> 黒", abs(r) < 1e-3 and abs(g) < 1e-3 and abs(b) < 1e-3)

    # 既知の有彩色ケース（C=0 の無彩色では l_ = m_ = s_ = L となり LMS 係数・
    # a = C・cosH / b = C・sinH の経路が一切評価されないため、C > 0 の値で検証する）。
    # 変換値は https://oklch.com / colorjs.io の実装と照合した既知の sRGB 対応（srgb 0-255 換算）。
    # 許容誤差は各チャンネル ±2/255（≒0.0078）。
    def check_rgb(label: str, oklch_value: str, expected_255: tuple[int, int, int]) -> None:
        r_, g_, b_ = oklch_str_to_srgb(oklch_value)
        got_255 = (round(r_ * 255), round(g_ * 255), round(b_ * 255))
        tol = 2 / 255
        ok = (
            abs(r_ - expected_255[0] / 255) < tol
            and abs(g_ - expected_255[1] / 255) < tol
            and abs(b_ - expected_255[2] / 255) < tol
        )
        check(f"{label}: {oklch_value} -> rgb{expected_255}（実測 rgb{got_255}）", ok)

    check_rgb("有彩色（赤）", "oklch(0.627955 0.257683 29.2338)", (255, 0, 0))
    check_rgb("有彩色（緑）", "oklch(0.86644 0.294827 142.495)", (0, 255, 0))
    check_rgb("有彩色（青）", "oklch(0.452013 0.313214 264.052)", (0, 0, 255))

    # 白 vs 黒のコントラスト比は 21:1
    ratio = contrast_ratio((1.0, 1.0, 1.0), (0.0, 0.0, 0.0))
    check(f"白 vs 黒のコントラスト比 21:1（実測 {ratio:.4f}）", abs(ratio - 21.0) < 0.01)

    # 同色のコントラスト比は 1:1
    ratio_same = contrast_ratio((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))
    check(f"同色のコントラスト比 1:1（実測 {ratio_same:.4f}）", abs(ratio_same - 1.0) < 1e-6)

    # alpha パース: '/ 10%' 形式
    L, C, H, alpha = parse_oklch("oklch(1 0 0 / 10%)")
    check("alpha '10%' -> 0.1", abs(alpha - 0.1) < 1e-6)

    # alpha パース: 数値形式
    L, C, H, alpha = parse_oklch("oklch(1 0 0 / 0.5)")
    check("alpha '0.5' -> 0.5", abs(alpha - 0.5) < 1e-6)

    # alpha 省略時は 1.0
    L, C, H, alpha = parse_oklch("oklch(0.5 0.1 200)")
    check("alpha 省略 -> 1.0", abs(alpha - 1.0) < 1e-6)

    # alpha 合成: 白 10% を黒背景に乗せると黒に極めて近い（低コントラスト）
    white = oklch_str_to_srgb("oklch(1 0 0)")
    black = oklch_str_to_srgb("oklch(0 0 0)")
    blended = blend_over(white, 0.1, black)
    ratio_blend = contrast_ratio(blended, black)
    check(f"alpha 10% 白 on 黒 のコントラスト比は低い（実測 {ratio_blend:.2f} < 2.0）", ratio_blend < 2.0)

    # CSS ブロック抽出のパース自己テスト
    sample_css = ":root {\n  --a: oklch(1 0 0);\n  --b: oklch(0 0 0);\n}\n.dark {\n  --a: oklch(0 0 0);\n}\n"
    root_block = extract_block(sample_css, ":root")
    decls = parse_declarations(root_block)
    check("CSS ブロック抽出: --a", decls.get("a") == "oklch(1 0 0)")
    check("CSS ブロック抽出: --b", decls.get("b") == "oklch(0 0 0)")
    dark_block = extract_block(sample_css, ".dark")
    dark_decls = parse_declarations(dark_block)
    check("CSS ブロック抽出（.dark）は :root を混入しない", "b" not in dark_decls)

    if failures:
        print("[check_contrast --self-test] FAIL:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"[check_contrast --self-test] PASS（{total} 件のアサーション全て成功）")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    return run_check()


if __name__ == "__main__":
    sys.exit(main())
