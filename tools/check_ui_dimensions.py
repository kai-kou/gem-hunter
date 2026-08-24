#!/usr/bin/env python3
"""check_ui_dimensions.py — UI コントロールの寸法（高さ・フォントサイズ）ゲート

SSOT: `docs/03_design/ui-ux/ui-ux-guidelines.md` §2.4（コントロールサイズトークン）。
実装仕様: `content/discussions/form-uiux-design-review-20260819/` の lead 確定仕様 §5。

検査（Error）:
  1. `src/ui/components/button.tsx` / `input.tsx` の cva `size` テーブルの各 variant 文字列に、
     生の `h-\\d+` / `size-\\d+` / `h-[...]` / `size-[...]` が直書きされていないこと
     （`h-(--size-control-*)` / `size-(--size-control-*)` のトークン参照のみ許可）
  2. `input.tsx` の**無プレフィックス**（モバイル既定）の `text-*` が、`app/globals.css` の
     `--text-control-min` 宣言値未満でないこと（ボタンは対象外）
  3. `app/globals.css` の `--size-control-xs` 宣言値が 24px（WCAG 2.5.8 フロア）未満でないこと。
     `--text-control-min` 宣言値が 16px（iOS Safari 自動ズーム回避）未満でないこと
  4. 登録済み呼び出しサイト（既定: `src/ui/search-form.tsx`）のリテラル `className` に
     `h-*` / `text-*` が含まれていない（サイズの上書き禁止）
  5. 登録済み呼び出しサイトが要求 tier 未満のコンポーネント size variant を使っていないこと
     （既定: `search-form.tsx` は Input / Button ともに `xl` tier 以上）

Warning（`run_checks.sh` を止めない）:
  - `src/ui/components/` 配下に未登録の新規コンポーネントファイルがあり、生の `h-\\d+` を含む場合
  - 登録済み呼び出しサイトの `className={...}`（式形式）に、変数展開・関数戻り値など
    静的に解決できない部分が含まれる場合（誤検知で止めないため Error にしない）
  - `app/globals.css` の対象変数が宣言されているが、値を px/rem として解決できない場合
    （黙ってスキップせず Warning で可視化する）

🔴 Python は px 数値をハードコードしない（WCAG 24px / iOS 16px という「判定基準の定数」を除く）。
   tier ごとの実効 px 値は `app/globals.css` の宣言値から都度読み取る。Python が持つのは
   「tier の順序（xs<sm<md<lg<xl）」「どの tier が WCAG 必須か」「呼び出しサイト → 必要 tier」の
   対応表のみ。

使い方:
  python3 tools/check_ui_dimensions.py                # 登録済み対象ファイルを検査
  python3 tools/check_ui_dimensions.py --self-test     # 検査ロジックの自己テスト
  違反（Error）があれば exit 1。対象ファイルが 1 つも存在しなければ黙って PASS（exit 0）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ts_source import find_matching_brace, find_tag_end, strip_comments  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent

# --------------------------------------------------------------------------- 対応表（SSOT はここだけ）

COMPONENT_FILES = [
    "src/ui/components/button.tsx",
    "src/ui/components/input.tsx",
]
FONT_CHECK_FILES = [
    "src/ui/components/input.tsx",
]
GLOBALS_CSS = "app/globals.css"
COMPONENTS_DIR = "src/ui/components/"

# 呼び出しサイト → { コンポーネント名: 必要な最低 tier }
CALL_SITE_REQUIREMENTS: dict[str, dict[str, str]] = {
    "src/ui/search-form.tsx": {"Input": "xl", "Button": "xl"},
    # エラー通知の導線（ui-ux-guidelines.md §5.2「再試行ボタン」）。再試行は主要導線 = xl、
    # ログイン導線はそれに次ぐ lg。下限は小さい方の tier を登録する（両方が lg 以上であること）。
    "src/ui/error-notice.tsx": {"Button": "lg"},
}

# tier の順序（小 → 大）。px 値ではなく「順序」のみを Python が持つ。
TIER_ORDER = ["xs", "sm", "md", "lg", "xl"]

# cva の size variant 名 → tier 名（Button の `default` / Input の `default` は tier "md" に対応）
# icon 系（正方形の icon variant）も同じ tier 表に載せる（未登録だと tier 不足が検出されずすり抜ける）。
# 🔴 `icon-xl` は button.tsx から削除済み（YAGNI）のためここにも追加しない。
VARIANT_TIER = {
    "xs": "xs",
    "sm": "sm",
    "default": "md",
    "lg": "lg",
    "xl": "xl",
    "icon": "md",
    "icon-xs": "xs",
    "icon-sm": "sm",
    "icon-lg": "lg",
}

# WCAG / iOS の判定基準定数（トークンの実効値ではなく「判定基準」そのもの。ハードコード対象外ではない）
WCAG_MIN_TARGET_PX = 24.0  # WCAG 2.2 2.5.8（AA）target size minimum
IOS_ZOOM_MIN_FONT_PX = 16.0  # iOS Safari の自動ズーム回避フロア

# Tailwind v4 既定フォントスケール（無プレフィックス `text-*` の判定用）
TEXT_SCALE_PX = {
    "xs": 12.0, "sm": 14.0, "base": 16.0, "lg": 18.0, "xl": 20.0,
    "2xl": 24.0, "3xl": 30.0, "4xl": 36.0, "5xl": 48.0,
    "6xl": 60.0, "7xl": 72.0, "8xl": 96.0, "9xl": 128.0,
}

RAW_H_SIZE_TOKEN_RE = re.compile(r"^(?:h|size)-(?:\d|\[)")
BARE_TEXT_TOKEN_RE = re.compile(
    r"^text-(" + "|".join(re.escape(k) for k in TEXT_SCALE_PX) + r")$"
)
CALL_SITE_H_TEXT_RE = re.compile(r"^(?:h-|text-)")


# --------------------------------------------------------------------------- 共通ユーティリティ
# strip_comments は tools/ts_source.py（共通モジュール・Issue #612）からの import に統一済み。


def lineno_at(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def css_var_raw(css_text: str, var_name: str) -> str | None:
    """`--var-name: <値>;` の `<値>` 部分（前後空白除去済み）を返す。未宣言なら None。"""
    m = re.search(rf"--{re.escape(var_name)}\s*:\s*([^;]+);", css_text)
    return m.group(1).strip() if m else None


def css_var_px(css_text: str, var_name: str) -> float | None:
    """`--var-name: 24px;` / `--var-name: 1rem;` を px に解決する（1rem = 16px）。

    単位表記の大文字小文字は問わない（`24PX` 等）。変数が未宣言、または
    単位が px/rem 以外・数値として解釈できない場合は None（呼び出し側で
    「解決できなかった」ことを検出できるよう、値の有無と解決可否を区別する）。
    """
    raw = css_var_raw(css_text, var_name)
    if raw is None:
        return None
    m = re.match(r"^([\d.]+)\s*(px|rem)$", raw, re.IGNORECASE)
    if not m:
        return None
    value = float(m.group(1))
    return value * 16.0 if m.group(2).lower() == "rem" else value


def tier_order_index(tier: str) -> int | None:
    return TIER_ORDER.index(tier) if tier in TIER_ORDER else None


# --------------------------------------------------------------------------- 検査 1: cva size テーブルの生値

def check_raw_size_literals(rel: str, text: str) -> list[str]:
    errors: list[str] = []
    code = strip_comments(text)
    for block_m in re.finditer(r"\bsize:\s*\{(.*?)\n\s*\}", code, re.DOTALL):
        block = block_m.group(1)
        block_start = block_m.start(1)
        for lit_m in re.finditer(r"(['\"])(.*?)\1", block, re.DOTALL):
            content = lit_m.group(2)
            lit_offset = block_start + lit_m.start(2)
            for tok_m in re.finditer(r"\S+", content):
                stripped_tok = tok_m.group(0)
                if RAW_H_SIZE_TOKEN_RE.match(stripped_tok):
                    ln = lineno_at(code, lit_offset + tok_m.start())
                    errors.append(
                        f"{rel}:{ln} UI-DIM-1: cva size テーブルに生の高さ指定 `{stripped_tok}` があります"
                        "（`h-(--size-control-*)` / `size-(--size-control-*)` のトークン参照にしてください）"
                    )
    return errors


# --------------------------------------------------------------------------- 検査 2: 無プレフィックス text-* フロア

def check_bare_small_text(rel: str, text: str, min_px: float) -> list[str]:
    errors: list[str] = []
    code = strip_comments(text)
    for lit_m in re.finditer(r"(['\"])(.*?)\1", code, re.DOTALL):
        content = lit_m.group(2)
        lit_offset = lit_m.start(2)
        for tok_m in re.finditer(r"\S+", content):
            stripped_tok = tok_m.group(0)
            m = BARE_TEXT_TOKEN_RE.match(stripped_tok)
            if not m:
                continue
            px = TEXT_SCALE_PX[m.group(1)]
            if px < min_px:
                ln = lineno_at(code, lit_offset + tok_m.start())
                errors.append(
                    f"{rel}:{ln} UI-DIM-2: 無プレフィックスの `{stripped_tok}`（{px:g}px）が "
                    f"--text-control-min（{min_px:g}px）未満です（iOS 自動ズーム回避）"
                )
    return errors


# --------------------------------------------------------------------------- 検査 3: globals.css のフロア実体

def check_globals_floor(css_text: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    def _check(var_name: str, floor_px: float, floor_label: str) -> None:
        raw = css_var_raw(css_text, var_name)
        if raw is None:
            return  # 未宣言はこの検査の対象外（宣言必須は別の関心事）
        px = css_var_px(css_text, var_name)
        if px is None:
            warnings.append(
                f"{GLOBALS_CSS} UI-DIM-3: --{var_name} の値 `{raw}` を px/rem として"
                "解決できません（フロア判定をスキップしました。単位を px か rem にしてください）"
            )
            return
        if px < floor_px:
            errors.append(
                f"{GLOBALS_CSS} UI-DIM-3: --{var_name} が {px:g}px で "
                f"{floor_label}フロア（{floor_px:g}px）未満です"
            )

    _check("size-control-xs", WCAG_MIN_TARGET_PX, "WCAG 2.5.8")
    _check("text-control-min", IOS_ZOOM_MIN_FONT_PX, "iOS 自動ズーム回避")
    return errors, warnings


# --------------------------------------------------------------------------- 検査 4: 呼び出しサイトの className 上書き禁止

CLASSNAME_LITERAL_RE = re.compile(r'className\s*=\s*"([^"]*)"')
CLASSNAME_EXPR_START_RE = re.compile(r"className\s*=\s*\{")


def _scan_classname_expr(rel: str, expr: str, base_offset: int, code: str) -> tuple[list[str], bool]:
    """`className={...}` の式本体を検査する。

    文字列リテラル・テンプレートリテラルの静的部分は禁止クラス判定にかけて Error 化する。
    変数展開（`${...}`）や、リテラルを除去してもなお残る識別子（関数呼び出し名を除く）が
    あれば「静的に解決できない」と判定し、呼び出し元へ `has_dynamic=True` を返す
    （Error にはせず、呼び出し元で Warning を積む）。
    """
    errors: list[str] = []
    n = len(expr)
    skeleton = list(expr)
    saw_dynamic_interp = False

    def check_segment(seg_text: str, seg_offset: int) -> None:
        for tok_m in re.finditer(r"\S+", seg_text):
            tok = tok_m.group(0)
            if CALL_SITE_H_TEXT_RE.match(tok):
                ln = lineno_at(code, seg_offset + tok_m.start())
                errors.append(
                    f"{rel}:{ln} UI-DIM-4: className={{...}} 内のリテラルに `{tok}` があります"
                    "（サイズは cva の size variant 経由で指定し、呼び出し側で上書きしないでください）"
                )

    i = 0
    while i < n:
        ch = expr[i]
        if ch in "\"'":
            q = ch
            j = i + 1
            while j < n and expr[j] != q:
                j += 2 if expr[j] == "\\" else 1
            check_segment(expr[i + 1 : j], base_offset + i + 1)
            for k in range(i, min(j + 1, n)):
                skeleton[k] = " "
            i = j + 1
            continue
        if ch == "`":
            j = i + 1
            seg_start = j
            while j < n and expr[j] != "`":
                if expr[j] == "\\":
                    j += 2
                    continue
                if expr[j] == "$" and j + 1 < n and expr[j + 1] == "{":
                    check_segment(expr[seg_start:j], base_offset + seg_start)
                    close = find_matching_brace(expr, j + 1)
                    saw_dynamic_interp = True
                    j = close + 1
                    seg_start = j
                    continue
                j += 1
            check_segment(expr[seg_start:j], base_offset + seg_start)
            for k in range(i, min(j + 1, n)):
                skeleton[k] = " "
            i = j + 1
            continue
        i += 1

    has_dynamic = saw_dynamic_interp
    if not has_dynamic:
        remainder = "".join(skeleton)
        for id_m in re.finditer(r"[A-Za-z_$][A-Za-z0-9_$]*", remainder):
            k = id_m.end()
            while k < n and remainder[k].isspace():
                k += 1
            if k < n and remainder[k] == "(":
                continue  # 関数呼び出し名（例: cn(...)）は素通しし、中の引数だけを見る
            has_dynamic = True
            break
    return errors, has_dynamic


def check_call_site_classname(rel: str, text: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    code = strip_comments(text)

    for m in CLASSNAME_LITERAL_RE.finditer(code):
        content = m.group(1)
        base_offset = m.start(1)
        for tok_m in re.finditer(r"\S+", content):
            stripped_tok = tok_m.group(0)
            if CALL_SITE_H_TEXT_RE.match(stripped_tok):
                ln = lineno_at(code, base_offset + tok_m.start())
                errors.append(
                    f"{rel}:{ln} UI-DIM-4: リテラル className に `{stripped_tok}` があります"
                    "（サイズは cva の size variant 経由で指定し、呼び出し側で上書きしないでください）"
                )

    for m in CLASSNAME_EXPR_START_RE.finditer(code):
        brace_start = m.end() - 1
        close = find_matching_brace(code, brace_start)
        expr = code[brace_start + 1 : close]
        expr_errors, has_dynamic = _scan_classname_expr(rel, expr, brace_start + 1, code)
        errors.extend(expr_errors)
        if has_dynamic:
            ln = lineno_at(code, brace_start)
            warnings.append(
                f"{rel}:{ln} UI-DIM-4: className={{...}} の一部が静的に解決できません"
                "（サイズ影響 className が静的に解決できません。size variant で指定してください）"
            )

    return errors, warnings


# --------------------------------------------------------------------------- 検査 5: 呼び出しサイトの tier 下限

def check_call_site_tier(rel: str, text: str, requirements: dict[str, str]) -> list[str]:
    errors: list[str] = []
    code = strip_comments(text)
    for component, required_tier in requirements.items():
        required_idx = tier_order_index(required_tier)
        if required_idx is None:
            continue
        for open_m in re.finditer(rf"<{re.escape(component)}\b", code):
            tag_start = open_m.start()
            attrs_start = open_m.end()
            # 非貪欲正規表現 `(.*?)(?:/>|>)` は onClick={() => f()} の `=>` の `>` を
            # タグ終端と誤認する（属性の並び順で結果が変わる偽陽性の原因）。深さ・クォートを
            # 追跡する find_tag_end で実際のタグ終端だけを終端と判定する（Issue #612）。
            tag_end = find_tag_end(code, attrs_start)
            if tag_end == -1:
                continue  # 対応するタグ終端が見つからない（壊れた/切り詰められた入力）。誤検知を避けて素通りする。
            attrs = code[attrs_start:tag_end]
            size_m = re.search(r'size\s*=\s*"([^"]+)"', attrs)
            variant_name = size_m.group(1) if size_m else "default"
            used_tier = VARIANT_TIER.get(variant_name)
            if used_tier is None:
                continue  # 未知の variant 名は判定不能。誤検知を避けて素通りする。
            used_idx = tier_order_index(used_tier)
            if used_idx is None or used_idx >= required_idx:
                continue
            ln = lineno_at(code, tag_start)
            errors.append(
                f"{rel}:{ln} UI-DIM-5: <{component}> が size=\"{variant_name}\"（tier {used_tier}）"
                f"を使っていますが、この呼び出しサイトは tier {required_tier} 以上が必要です"
            )
    return errors


# --------------------------------------------------------------------------- Warning: 未登録コンポーネントの生値

def check_unregistered_component_warning(rel: str, text: str) -> list[str]:
    warnings: list[str] = []
    code = strip_comments(text)
    for m in re.finditer(r"['\"]([^'\"]*)['\"]", code, re.DOTALL):
        for tok_m in re.finditer(r"\S+", m.group(1)):
            stripped_tok = tok_m.group(0)
            if re.match(r"^h-\d", stripped_tok):
                warnings.append(
                    f"{rel} が {COMPONENTS_DIR} 配下の未登録コンポーネントで、生の高さ指定 "
                    f"`{stripped_tok}` を含みます（tools/check_ui_dimensions.py の "
                    "COMPONENT_FILES / CALL_SITE_REQUIREMENTS に登録してください）"
                )
                break
        else:
            continue
        break
    return warnings


# --------------------------------------------------------------------------- 統合実行（I/O フリー・self-test の注入口）

def run_checks(files: dict[str, str]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    css_text = files.get(GLOBALS_CSS)

    for rel in COMPONENT_FILES:
        text = files.get(rel)
        if text is None:
            continue
        errors.extend(check_raw_size_literals(rel, text))

    if css_text is not None:
        text_min_px = css_var_px(css_text, "text-control-min")
        if text_min_px is not None:
            for rel in FONT_CHECK_FILES:
                text = files.get(rel)
                if text is None:
                    continue
                errors.extend(check_bare_small_text(rel, text, text_min_px))
        floor_errors, floor_warnings = check_globals_floor(css_text)
        errors.extend(floor_errors)
        warnings.extend(floor_warnings)

    for rel, requirements in CALL_SITE_REQUIREMENTS.items():
        text = files.get(rel)
        if text is None:
            continue
        classname_errors, classname_warnings = check_call_site_classname(rel, text)
        errors.extend(classname_errors)
        warnings.extend(classname_warnings)
        errors.extend(check_call_site_tier(rel, text, requirements))

    registered = set(COMPONENT_FILES)
    for rel, text in files.items():
        if not rel.startswith(COMPONENTS_DIR):
            continue
        if rel in registered:
            continue
        if ".test." in Path(rel).name or ".spec." in Path(rel).name:
            continue
        warnings.extend(check_unregistered_component_warning(rel, text))

    return errors, warnings


# --------------------------------------------------------------------------- self-test

def _good_files() -> dict[str, str]:
    globals_css = (
        "@theme inline {\n"
        "  --size-control-xs: 24px;\n"
        "  --size-control-sm: 28px;\n"
        "  --size-control-md: 32px;\n"
        "  --size-control-lg: 40px;\n"
        "  --size-control-xl: 44px;\n"
        "  --text-control-min: 1rem;\n"
        "}\n"
    )
    button = (
        "const buttonVariants = cva(\n"
        "  \"base classes\",\n"
        "  {\n"
        "    variants: {\n"
        "      size: {\n"
        "        default: 'h-(--size-control-md) gap-1.5 px-2.5',\n"
        "        xs: \"h-(--size-control-xs) gap-1 px-2 text-xs [&_svg:not([class*='size-'])]:size-3\",\n"
        "        sm: 'h-(--size-control-sm) gap-1 px-2.5',\n"
        "        lg: 'h-(--size-control-lg) gap-1.5 px-2.5',\n"
        "        xl: 'h-(--size-control-xl) gap-2 px-4 text-base',\n"
        "        icon: 'size-(--size-control-md)',\n"
        "        'icon-xs': \"size-(--size-control-xs) [&_svg:not([class*='size-'])]:size-3\",\n"
        "        'icon-lg': 'size-(--size-control-lg)',\n"
        "      },\n"
        "    },\n"
        "  },\n"
        ")\n"
    )
    input_tsx = (
        "const inputVariants = cva(\n"
        "  'h-(--size-control-md) w-full text-base px-2.5 py-1',\n"
        "  {\n"
        "    variants: {\n"
        "      size: {\n"
        "        default: 'h-(--size-control-md) px-2.5 py-1',\n"
        "        lg: 'h-(--size-control-lg) px-3',\n"
        "        xl: 'h-(--size-control-xl) px-3',\n"
        "      },\n"
        "    },\n"
        "    defaultVariants: { size: 'default' },\n"
        "  },\n"
        ")\n"
    )
    search_form = (
        "export function SearchForm({ keyword }) {\n"
        "  return (\n"
        "    <form action=\"/\" method=\"get\" role=\"search\" className=\"flex gap-2\">\n"
        "      <Input id=\"q\" name=\"q\" size=\"xl\" className=\"flex-1\" defaultValue={keyword} />\n"
        "      <Button type=\"submit\" size=\"xl\">検索</Button>\n"
        "    </form>\n"
        "  )\n"
        "}\n"
    )
    return {
        "src/ui/components/button.tsx": button,
        "src/ui/components/input.tsx": input_tsx,
        "app/globals.css": globals_css,
        "src/ui/search-form.tsx": search_form,
    }


CASES: list[tuple[str, dict[str, str], int, int]] = []


def _case(label: str, mutate, want_e: int, want_w: int) -> None:
    files = _good_files()
    mutate(files)
    CASES.append((label, files, want_e, want_w))


_case("baseline: 全ファイル正常", lambda f: None, 0, 0)

_case(
    "検査1: button.tsx の xs variant に生の h-6",
    lambda f: f.__setitem__(
        "src/ui/components/button.tsx",
        f["src/ui/components/button.tsx"].replace(
            "h-(--size-control-xs)", "h-6"
        ),
    ),
    1, 0,
)

_case(
    "検査1: button.tsx の icon-lg variant に任意値 size-[40px]",
    lambda f: f.__setitem__(
        "src/ui/components/button.tsx",
        f["src/ui/components/button.tsx"].replace(
            "'icon-lg': 'size-(--size-control-lg)',", "'icon-lg': 'size-[40px]',"
        ),
    ),
    1, 0,
)

_case(
    "検査1: svg アイコン内側の size-3 はセレクタ配下なので許可",
    lambda f: None,  # baseline がすでに [&_svg:not(...)]:size-3 を含む
    0, 0,
)

_case(
    "検査2: input.tsx に無プレフィックスの text-sm",
    lambda f: f.__setitem__(
        "src/ui/components/input.tsx",
        f["src/ui/components/input.tsx"].replace(
            "'h-(--size-control-md) w-full text-base px-2.5 py-1',",
            "'h-(--size-control-md) w-full text-sm px-2.5 py-1',",
        ),
    ),
    1, 0,
)

_case(
    "検査2: md: プレフィックス付き text-sm は無視（プレフィックス判定漏れ検知用）",
    lambda f: f.__setitem__(
        "src/ui/components/input.tsx",
        f["src/ui/components/input.tsx"].replace(
            "'h-(--size-control-md) w-full text-base px-2.5 py-1',",
            "'h-(--size-control-md) w-full text-base px-2.5 py-1 md:text-sm',",
        ),
    ),
    0, 0,
)

_case(
    "検査3: globals.css の --size-control-xs が 20px（WCAG フロア未満）",
    lambda f: f.__setitem__(
        "app/globals.css",
        f["app/globals.css"].replace("--size-control-xs: 24px;", "--size-control-xs: 20px;"),
    ),
    1, 0,
)

_case(
    "検査3: globals.css の --text-control-min が 0.75rem（12px・iOS フロア未満）",
    lambda f: f.__setitem__(
        "app/globals.css",
        f["app/globals.css"].replace("--text-control-min: 1rem;", "--text-control-min: 0.75rem;"),
    ),
    1, 0,
)

_case(
    "検査3: globals.css の --size-control-xs が 20PX（フロア未満・大文字単位）",
    lambda f: f.__setitem__(
        "app/globals.css",
        f["app/globals.css"].replace("--size-control-xs: 24px;", "--size-control-xs: 20PX;"),
    ),
    1, 0,
)

_case(
    "検査3: globals.css の値が px/rem 以外の単位で解決できない場合は Warning（fail-open しない）",
    lambda f: f.__setitem__(
        "app/globals.css",
        f["app/globals.css"].replace("--size-control-xs: 24px;", "--size-control-xs: 1.5em;"),
    ),
    0, 1,
)

_case(
    "検査4: search-form.tsx のリテラル className に h-10",
    lambda f: f.__setitem__(
        "src/ui/search-form.tsx",
        f["src/ui/search-form.tsx"].replace('className="flex-1"', 'className="flex-1 h-10"'),
    ),
    1, 0,
)

_case(
    "検査4: search-form.tsx のリテラル className に text-sm",
    lambda f: f.__setitem__(
        "src/ui/search-form.tsx",
        f["src/ui/search-form.tsx"].replace('className="flex gap-2"', 'className="flex gap-2 text-sm"'),
    ),
    1, 0,
)

_case(
    "検査4: className={cn(\"flex-1\", \"h-10\")} の式形式が Error として検出される",
    lambda f: f.__setitem__(
        "src/ui/search-form.tsx",
        f["src/ui/search-form.tsx"].replace(
            'className="flex-1"', 'className={cn("flex-1", "h-10")}'
        ),
    ),
    1, 0,
)

_case(
    "検査4: className={`flex-1 h-10`}（テンプレートリテラル）が Error として検出される",
    lambda f: f.__setitem__(
        "src/ui/search-form.tsx",
        f["src/ui/search-form.tsx"].replace(
            'className="flex-1"', 'className={`flex-1 h-10`}'
        ),
    ),
    1, 0,
)

_case(
    "検査4: className={someVar}（静的に解決不能）は Error にせず Warning",
    lambda f: f.__setitem__(
        "src/ui/search-form.tsx",
        f["src/ui/search-form.tsx"].replace(
            'className="flex-1"', 'className={someVar}'
        ),
    ),
    0, 1,
)

_case(
    "検査5: search-form.tsx の Input が size 未指定（既定 tier md < 必要 xl）",
    lambda f: f.__setitem__(
        "src/ui/search-form.tsx",
        f["src/ui/search-form.tsx"].replace(' size="xl" className="flex-1"', ' className="flex-1"'),
    ),
    1, 0,
)

_case(
    "検査5: search-form.tsx の Button が size=\"sm\"（必要 xl 未満）",
    lambda f: f.__setitem__(
        "src/ui/search-form.tsx",
        f["src/ui/search-form.tsx"].replace('<Button type="submit" size="xl">', '<Button type="submit" size="sm">'),
    ),
    1, 0,
)

_case(
    "検査5: search-form.tsx の Button が size=\"icon-xs\"（tier xs < 必要 xl）",
    lambda f: f.__setitem__(
        "src/ui/search-form.tsx",
        f["src/ui/search-form.tsx"].replace(
            '<Button type="submit" size="xl">', '<Button type="submit" size="icon-xs">'
        ),
    ),
    1, 0,
)

# --- 検査5 反例（Issue #612・タグ終端の誤認による偽陽性の固定）-----------------
# 非貪欲正規表現 `.*?(?:/>|>)` は onClick={() => f()} の `=>` の `>` をタグ終端と
# 誤認し、それより後ろにある size="xl" を読み落として tier 不足の偽陽性を出す
# （属性の並び順だけで結果が変わっていた実バグ）。find_tag_end による深さ追跡で
# 正しくタグ全体を捉え、並び順に関わらず size="xl" を読み取れることを固定する。

_case(
    "検査5 反例（偽陽性）: アロー関数を含む属性が size より前にあっても size=\"xl\" を正しく読み取れる",
    lambda f: f.__setitem__(
        "src/ui/search-form.tsx",
        f["src/ui/search-form.tsx"].replace(
            'size="xl" className="flex-1"', 'onClick={() => {}} size="xl" className="flex-1"'
        ),
    ),
    0, 0,
)

_case(
    "検査5 反例（偽陽性）: 属性値の文字列内の `>` をタグ終端と誤認せず、後続の size=\"xl\" を正しく読み取れる",
    lambda f: f.__setitem__(
        "src/ui/search-form.tsx",
        f["src/ui/search-form.tsx"].replace(
            'size="xl" className="flex-1"', 'title="a > b" size="xl" className="flex-1"'
        ),
    ),
    0, 0,
)

_case(
    "検査5 反例（偽陰性ガード）: アロー関数を含む属性があっても本当の tier 違反（size=\"sm\"）は検出できる",
    lambda f: f.__setitem__(
        "src/ui/search-form.tsx",
        f["src/ui/search-form.tsx"].replace(
            'size="xl" className="flex-1"', 'onClick={() => {}} size="sm" className="flex-1"'
        ),
    ),
    1, 0,
)

_case(
    "対象ファイル不在: button.tsx / input.tsx が無ければ黙って PASS",
    lambda f: (f.pop("src/ui/components/button.tsx", None), f.pop("src/ui/components/input.tsx", None)),
    0, 0,
)

_case(
    "検査1は globals.css 不在でも独立して機能する",
    lambda f: (
        f.pop("app/globals.css", None),
        f.__setitem__(
            "src/ui/components/button.tsx",
            f["src/ui/components/button.tsx"].replace("h-(--size-control-xs)", "h-6"),
        ),
    ),
    1, 0,
)

_case(
    "Warning: 未登録コンポーネントに生の h-10",
    lambda f: f.__setitem__(
        "src/ui/components/badge.tsx",
        "export function Badge() { return <span className=\"h-10 inline-flex\">x</span> }\n",
    ),
    0, 1,
)

_case(
    "Warning対象外: 未登録コンポーネントでもトークン参照のみなら Warning なし",
    lambda f: f.__setitem__(
        "src/ui/components/badge.tsx",
        "export function Badge() { return <span className=\"h-(--size-control-md) inline-flex\">x</span> }\n",
    ),
    0, 0,
)


def run_self_test() -> int:
    failures: list[str] = []
    for label, files, want_e, want_w in CASES:
        errs, warns = run_checks(files)
        if len(errs) != want_e or len(warns) != want_w:
            failures.append(
                f"  {label}: want errors={want_e} warnings={want_w}, "
                f"got errors={len(errs)} warnings={len(warns)} :: {errs + warns}"
            )
    if failures:
        print("❌ check_ui_dimensions --self-test FAILED")
        print("\n".join(failures))
        return 1
    print(f"✅ check_ui_dimensions --self-test PASSED（{len(CASES)} ケース）")
    return 0


# --------------------------------------------------------------------------- ディスク読み込み・main

def collect_disk_files() -> dict[str, str]:
    rels: set[str] = set(COMPONENT_FILES) | set(FONT_CHECK_FILES) | {GLOBALS_CSS}
    rels |= set(CALL_SITE_REQUIREMENTS.keys())

    components_dir = REPO_ROOT / COMPONENTS_DIR
    if components_dir.is_dir():
        for p in components_dir.rglob("*"):
            if p.suffix in (".ts", ".tsx") and p.is_file():
                rels.add(p.relative_to(REPO_ROOT).as_posix())

    files: dict[str, str] = {}
    for rel in rels:
        path = REPO_ROOT / rel
        if not path.is_file() or path.is_symlink():
            continue
        try:
            files[rel] = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
    return files


def main() -> int:
    argv = sys.argv[1:]
    if "--self-test" in argv:
        return run_self_test()

    files = collect_disk_files()
    if not files:
        print("ℹ️ 検査対象の UI コンポーネント / globals.css がありません")
        return 0

    errors, warnings = run_checks(files)
    for w in warnings:
        print(f"⚠️ {w}")
    for e in errors:
        print(f"❌ {e}")
    if errors:
        print(
            f"\nUI 寸法検査違反 {len(errors)} 件。"
            "SSOT: docs/03_design/ui-ux/ui-ux-guidelines.md §2.4"
        )
        return 1
    print(f"✅ UI 寸法検査 OK（Warning {len(warnings)} 件）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
