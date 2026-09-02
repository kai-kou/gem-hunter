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
  4. 登録済み呼び出しサイト（既定: `src/ui/search-form.tsx`）の、そのコンポーネントの呼び出し箇所
     （JSX 属性 `<Button className="...">` / 関数呼び出し引数 `buttonVariants({ className: '...' })`
     の**どちらか**）のリテラル `className` に `h-*` / `text-*` が含まれていない（サイズの上書き禁止）。
     🔴 ファイル全体ではなく呼び出しサイトの範囲だけを見る（無関係な要素の typography クラスを
     誤検知しないため・Issue #83）
  5. 登録済み呼び出しサイトが要求 tier 未満のコンポーネント size variant を使っていないこと
     （既定: `search-form.tsx` は Input / Button ともに `xl` tier 以上）。JSX タグ形式
     （`<Button size="...">`）と関数呼び出し形式（`buttonVariants({ size: '...' })`）の両方を検出する

Warning（`run_checks.sh` を止めない）:
  - `src/ui/components/` 配下に未登録の新規コンポーネントファイルがあり、生の `h-\\d+` を含む場合
  - `src/ui/` 直下（サブディレクトリ・`components/` を除く）に Button / buttonVariants を使用して
    いるのに `CALL_SITE_REQUIREMENTS` に未登録のファイルがある場合（登録漏れの検知漏れ対策・Issue #83）
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
from ts_source import (  # noqa: E402
    JS_IDENTIFIER_RE,
    find_matching_brace,
    find_matching_paren,
    find_tag_end,
    strip_comments,
)

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
# `src/ui/` 直下（サブディレクトリを除く）を「呼び出しサイトの登録漏れ」検査のスキャン対象にする。
UI_DIR = "src/ui/"

# 呼び出しサイト → { コンポーネント名: 必要な最低 tier }
CALL_SITE_REQUIREMENTS: dict[str, dict[str, str]] = {
    "src/ui/search-form.tsx": {"Input": "xl", "Button": "xl"},
    # エラー通知の導線（ui-ux-guidelines.md §5.2「再試行ボタン」）。再試行は主要導線 = xl、
    # ログイン導線はそれに次ぐ lg。下限は小さい方の tier を登録する（両方が lg 以上であること）。
    "src/ui/error-notice.tsx": {"Button": "lg"},
    # 二次的なナビゲーション導線（ui-ux-guidelines.md §2.4 🔵 推奨「二次的なコントロールは md 以上」）。
    # 3 ファイルとも `buttonVariants({ size: 'default' })` 経由で tier md を使用済み（Issue #83）。
    "src/ui/pagination.tsx": {"Button": "md"},
    "src/ui/sort-picker.tsx": {"Button": "md"},
    "src/ui/per-page-picker.tsx": {"Button": "md"},
}

# コンポーネント名 → JSX を使わず cva variants 関数を直接呼び出す呼び出しサイトで使う関数名。
# `<Button ...>` の代わりに `buttonVariants({ size: '...', className: '...' })` のように
# 関数呼び出しで className 文字列を組み立てる箇所（`pagination.tsx` 等）を検出するために使う。
COMPONENT_CALL_FN: dict[str, str] = {
    "Button": "buttonVariants",
    "Input": "inputVariants",
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


# --------------------------------------------------------------------------- 呼び出しサイト検出（JSX タグ / variants 関数呼び出しの両対応）


def find_call_site_spans(code: str, component: str) -> list[tuple[int, int, int]]:
    """コンポーネントの呼び出しサイトを `(報告用位置, 本体テキスト開始, 本体テキスト終了)` で返す。

    2 つの形を検出する:
      - JSX タグ形式 `<Button size="lg">`（本体 = タグの属性文字列）
      - 関数呼び出し形式 `buttonVariants({ size: 'lg', className: '...' })`
        （本体 = 呼び出しの引数文字列。`COMPONENT_CALL_FN` に登録されたコンポーネントのみ検出）

    対応する終端（タグ終端 `>` / 閉じ括弧 `)`）が見つからない壊れた入力は、誤検知を避けて
    黙ってスキップする（既存の `check_call_site_tier` と同じ方針）。
    """
    spans: list[tuple[int, int, int]] = []

    for open_m in re.finditer(rf"<{re.escape(component)}\b", code):
        attrs_start = open_m.end()
        tag_end = find_tag_end(code, attrs_start)
        if tag_end == -1:
            continue
        spans.append((open_m.start(), attrs_start, tag_end))

    fn_name = COMPONENT_CALL_FN.get(component)
    if fn_name:
        for call_m in re.finditer(rf"\b{re.escape(fn_name)}\s*\(", code):
            open_paren = call_m.end() - 1
            # `find_matching_paren` は未発見時に確実に `-1` を返す（Issue #828 CRITICAL 指摘）。
            # 旧実装は `_find_matching_paren`（未発見時 `len(text)` を返す内部専用契約）を誤って
            # 呼び出しており、TS/TSX はファイル末尾付近にほぼ必ず `)` があるため
            # `close <= open_paren or code[close - 1] != ")"` のガードが「見つかった」と
            # 誤判定していた（本体 span がファイル末尾までの巨大な範囲になる偽陰性）。
            close = find_matching_paren(code, open_paren)
            if close == -1:
                continue  # 対応する閉じ括弧が見つからない（壊れた/切り詰められた入力）
            spans.append((call_m.start(), open_paren + 1, close))

    return spans


def _pos_in_spans(spans: list[tuple[int, int, int]], pos: int) -> bool:
    return any(body_start <= pos < body_end for _, body_start, body_end in spans)


# --------------------------------------------------------------------------- 検査 4: 呼び出しサイトの className 上書き禁止

CLASSNAME_LITERAL_RE = re.compile(r'className\s*=\s*"([^"]*)"')
CLASSNAME_EXPR_START_RE = re.compile(r"className\s*=\s*\{")
# オブジェクトリテラルのプロパティ構文（`buttonVariants({ className: '...' })` のように
# JSX 属性ではなく関数呼び出し引数の中で使われる形）。`CLASSNAME_LITERAL_RE`（`className="..."`。
# JSX 属性専用）は `:` 区切りにマッチしないため、これを見落としていた（Issue #828 CRITICAL
# 指摘）。シングル/ダブルどちらのクォートにも対応する。
CLASSNAME_PROP_LITERAL_RE = re.compile(r"""className\s*:\s*(['"])((?:(?!\1).)*)\1""", re.DOTALL)


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
        for id_m in JS_IDENTIFIER_RE.finditer(remainder):
            k = id_m.end()
            while k < n and remainder[k].isspace():
                k += 1
            if k < n and remainder[k] == "(":
                continue  # 関数呼び出し名（例: cn(...)）は素通しし、中の引数だけを見る
            has_dynamic = True
            break
    return errors, has_dynamic


def check_call_site_classname(
    rel: str, text: str, components: list[str]
) -> tuple[list[str], list[str]]:
    """登録済みコンポーネントの呼び出しサイト（JSX 属性 / 関数呼び出し引数）に限定して検査する。

    🔴 ファイル全体を無差別に走査しない（Issue #83）: `pagination.tsx` のように、対象コンポーネント
    とは無関係な要素（ページ番号表示の `<span className="text-sm ...">` 等）が同じファイル内に
    あると、ファイル全体走査ではそれらの正当な typography クラスまで誤検知する。呼び出しサイトの
    本体テキスト範囲（`find_call_site_spans`）に位置するマッチだけを対象にすることで、無関係な
    JSX を誤って弾かずに済ませる。
    """
    errors: list[str] = []
    warnings: list[str] = []
    code = strip_comments(text)

    spans: list[tuple[int, int, int]] = []
    for component in components:
        spans.extend(find_call_site_spans(code, component))
    if not spans:
        return errors, warnings

    for m in CLASSNAME_LITERAL_RE.finditer(code):
        if not _pos_in_spans(spans, m.start(1)):
            continue
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

    for m in CLASSNAME_PROP_LITERAL_RE.finditer(code):
        if not _pos_in_spans(spans, m.start(2)):
            continue
        content = m.group(2)
        base_offset = m.start(2)
        for tok_m in re.finditer(r"\S+", content):
            stripped_tok = tok_m.group(0)
            if CALL_SITE_H_TEXT_RE.match(stripped_tok):
                ln = lineno_at(code, base_offset + tok_m.start())
                errors.append(
                    f"{rel}:{ln} UI-DIM-4: className: プロパティのリテラルに `{stripped_tok}` があります"
                    "（サイズは cva の size variant 経由で指定し、呼び出し側で上書きしないでください）"
                )

    for m in CLASSNAME_EXPR_START_RE.finditer(code):
        if not _pos_in_spans(spans, m.start()):
            continue
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

SIZE_PROP_RE = re.compile(r"""size\s*[:=]\s*['"]([^'"]+)['"]""")


def _brace_depth_at_each_pos(body: str) -> list[int]:
    """`body` の各文字位置における `{}` ネスト深さ（文字列リテラルの中は無視）を返す。

    `len(body) + 1` 要素（末尾位置も含む）。`check_call_site_tier` が「呼び出しサイト本体の
    トップレベルにある `size` を優先する」ために使う（Issue #828 CRITICAL 指摘: `.search()` は
    最初に出現した `size` を無条件で採用するため、`onClick={() => track({ size: 'xl' })}` の
    ようにネストしたオブジェクトリテラル内の `size` を先に拾い、本当の `size="xs"` を
    見逃していた）。
    """
    depths = [0] * (len(body) + 1)
    depth = 0
    i = 0
    n = len(body)
    quote: str | None = None
    while i < n:
        depths[i] = depth
        ch = body[i]
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
        if ch == "{":
            depth += 1
            i += 1
            continue
        if ch == "}":
            depth = max(0, depth - 1)
            i += 1
            continue
        i += 1
    depths[n] = depth
    return depths


def _shallowest_size_match(body: str) -> re.Match[str] | None:
    """`body` 内の `size` 指定のうち、`{}` ネスト深さが最も浅い（同点なら最初に出現した）
    ものを返す。JSX タグ形式ではタグ直下の属性（深さ 0）を、関数呼び出し形式では引数
    オブジェクトのトップレベルプロパティ（本体の最小深さ）を選び、途中に挟まる
    `onClick={() => track({ size: 'xl' })}` のようなネストした `size` に惑わされない。
    """
    depths = _brace_depth_at_each_pos(body)
    best: re.Match[str] | None = None
    best_depth: int | None = None
    for size_m in SIZE_PROP_RE.finditer(body):
        d = depths[size_m.start()]
        if best_depth is None or d < best_depth:
            best_depth = d
            best = size_m
    return best


def check_call_site_tier(rel: str, text: str, requirements: dict[str, str]) -> list[str]:
    errors: list[str] = []
    code = strip_comments(text)
    for component, required_tier in requirements.items():
        required_idx = tier_order_index(required_tier)
        if required_idx is None:
            continue
        # JSX タグ `<Button size="lg">` と関数呼び出し `buttonVariants({ size: 'lg' })` の
        # 両方の呼び出しサイトを検出する（Issue #83・pagination.tsx 等は後者の形のみを使う）。
        for report_start, body_start, body_end in find_call_site_spans(code, component):
            body = code[body_start:body_end]
            size_m = _shallowest_size_match(body)
            variant_name = size_m.group(1) if size_m else "default"
            used_tier = VARIANT_TIER.get(variant_name)
            if used_tier is None:
                continue  # 未知の variant 名は判定不能。誤検知を避けて素通りする。
            used_idx = tier_order_index(used_tier)
            if used_idx is None or used_idx >= required_idx:
                continue
            ln = lineno_at(code, report_start)
            errors.append(
                f"{rel}:{ln} UI-DIM-5: <{component}> が size=\"{variant_name}\"（tier {used_tier}）"
                f"を使っていますが、この呼び出しサイトは tier {required_tier} 以上が必要です"
            )
    return errors


# --------------------------------------------------------------------------- Warning: 未登録の呼び出しサイト（src/ui/ 直下）


def _build_unregistered_call_site_re() -> re.Pattern[str]:
    """`COMPONENT_CALL_FN` のキー（JSX タグ名）・値（関数呼び出し名）からコンポーネント名の
    列挙を動的に組み立てる（Issue #828 CRITICAL 指摘）。

    旧実装は `<Button\\b|\\bbuttonVariants\\s*\\(` をハードコードしており、同じ
    `COMPONENT_CALL_FN` に既に登録済みの `Input` / `inputVariants` を見落としていた
    （`search-form.tsx` は Input の tier 要件を持つのに、他ファイルで Input を未登録のまま
    使っても Warning が出ない穴があった）。列挙をここへ集約したことで、新規コンポーネントを
    `COMPONENT_CALL_FN` に足すだけで本 Warning にも自動反映される。
    """
    tag_alt = "|".join(re.escape(name) for name in COMPONENT_CALL_FN)
    fn_alt = "|".join(re.escape(fn) for fn in COMPONENT_CALL_FN.values())
    return re.compile(rf"<(?:{tag_alt})\b|\b(?:{fn_alt})\s*\(")


UNREGISTERED_CALL_SITE_RE = _build_unregistered_call_site_re()

# 対象コンポーネントの登録済み文字列表現（Warning メッセージ用。COMPONENT_CALL_FN から動的生成）。
_UNREGISTERED_CALL_SITE_NAMES = " / ".join(
    sorted(set(COMPONENT_CALL_FN) | set(COMPONENT_CALL_FN.values()))
)

# `import { buttonVariants as bv } from './components/button'` のような named import の
# ローカル別名を解決するための正規表現（Issue #828 CRITICAL 指摘）。
_IMPORT_NAMED_RE = re.compile(r"""import\s*\{([^}]*)\}\s*from\s*['"]([^'"]*)['"]""")
_IMPORT_ALIAS_ITEM_RE = re.compile(r"^([A-Za-z_$][\w$]*)\s+as\s+([A-Za-z_$][\w$]*)$")
# namespace import（`import * as NS from '...'`）は「NS.buttonVariants(...)」のような
# メンバアクセス呼び出しになり、本モジュールの正規表現ベースの走査では静的に解決できない
# ため、黙って素通りさせず Warning で可視化する（解決できない import 形式の検出）。
_IMPORT_NAMESPACE_RE = re.compile(
    r"""import\s+\*\s+as\s+[A-Za-z_$][\w$]*\s+from\s*['"]([^'"]*)['"]"""
)
# COMPONENT_FILES（`src/ui/components/button.tsx` 等）のモジュール名（拡張子なしの
# ファイル名）。namespace import の指定パスがコンポーネントモジュールを指しているかどうかの
# 判定に使う（`import * as React from 'react'` のような無関係な namespace import まで
# 誤検知しないため、スコープをコンポーネントモジュールに限定する）。
_COMPONENT_MODULE_STEMS = {Path(p).stem for p in COMPONENT_FILES}


def _resolve_call_fn_aliases(code: str) -> dict[str, str]:
    """`import { buttonVariants as bv } from '...'` のような named import のローカル別名を
    `{ ローカル名: 元の関数名 }` で返す（`COMPONENT_CALL_FN` の値に一致するものだけ）。

    「同ディレクトリからの named import のローカル別名を解決する」という Issue #828 の
    要求のうち、named import の別名解決部分をここで満たす。
    """
    known_fns = set(COMPONENT_CALL_FN.values())
    aliases: dict[str, str] = {}
    for imp_m in _IMPORT_NAMED_RE.finditer(code):
        for item in imp_m.group(1).split(","):
            item = item.strip()
            if not item:
                continue
            alias_m = _IMPORT_ALIAS_ITEM_RE.match(item)
            if alias_m and alias_m.group(1) in known_fns:
                aliases[alias_m.group(2)] = alias_m.group(1)
    return aliases


def _has_unresolved_component_namespace_import(code: str) -> bool:
    """コンポーネントモジュール（`COMPONENT_FILES`）を指す namespace import があるかを返す。

    `import * as ButtonNs from './components/button'` の後に `ButtonNs.buttonVariants(...)`
    と呼ばれると、本モジュールの正規表現ベースの走査では解決できない。黙ってスキップせず
    Warning として可視化する（Issue #828: 「解決できない import 形式を検出したら Warning を
    出す」要求を満たす）。
    """
    for ns_m in _IMPORT_NAMESPACE_RE.finditer(code):
        spec = ns_m.group(1).rstrip("/")
        stem = spec.rsplit("/", 1)[-1] if "/" in spec else spec
        if stem in _COMPONENT_MODULE_STEMS:
            return True
    return False


def _unregistered_call_site_message(rel: str, detail: str = "") -> str:
    base = (
        f"{rel} が {UI_DIR} 直下で {_UNREGISTERED_CALL_SITE_NAMES} を使用していますが "
        "CALL_SITE_REQUIREMENTS に未登録です（tools/check_ui_dimensions.py に tier 要件を登録してください）"
    )
    return f"{base}{detail}"


def check_unregistered_call_site_warning(rel: str, text: str, registered: set[str]) -> list[str]:
    """`src/ui/` 直下（`COMPONENTS_DIR` を除く）で Button / Input（および `COMPONENT_CALL_FN`
    に登録された他コンポーネント）を使っているのに `CALL_SITE_REQUIREMENTS` に未登録の
    ファイルを Warning にする（Issue #83 / #828）。

    既存の「未登録コンポーネント Warning」（`check_unregistered_component_warning`）は
    `COMPONENTS_DIR` 配下の新規コンポーネントファイル自体の生値のみを見ており、
    `src/ui/` 直下の呼び出しサイト（`pagination.tsx` 等）は範囲外だった
    （`CALL_SITE_REQUIREMENTS` 未登録なら Error 検査自体が走らずサイレントに素通りする穴）。
    本関数はその穴を Warning で塞ぐ。生の `h-\\d` の有無に関わらず、コンポーネントを
    使っている時点で警告する（tier 要件の登録漏れ自体を検知したいため。既存 Warning のような
    生値限定にしない）。エイリアス import・namespace import の扱いは Issue #828 参照。
    """
    if rel in registered:
        return []
    code = strip_comments(text)
    if UNREGISTERED_CALL_SITE_RE.search(code):
        return [_unregistered_call_site_message(rel)]

    aliases = _resolve_call_fn_aliases(code)
    for local_name, original_fn in aliases.items():
        if re.search(rf"\b{re.escape(local_name)}\s*\(", code):
            return [
                _unregistered_call_site_message(
                    rel, f"（`{original_fn} as {local_name}` のエイリアス経由）"
                )
            ]

    if _has_unresolved_component_namespace_import(code):
        return [
            f"{rel} がコンポーネントモジュールを namespace import（`import * as ... from "
            "'...'`）していますが、本検査はそのメンバアクセス呼び出しを静的に解決できません"
            "（Button / Input 相当の呼び出しを見落としている可能性があります。named import "
            "またはエイリアス import に変更するか、手動で CALL_SITE_REQUIREMENTS への登録要否を"
            "確認してください）"
        ]

    return []


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
        classname_errors, classname_warnings = check_call_site_classname(
            rel, text, list(requirements.keys())
        )
        errors.extend(classname_errors)
        warnings.extend(classname_warnings)
        errors.extend(check_call_site_tier(rel, text, requirements))

    registered_components = set(COMPONENT_FILES)
    for rel, text in files.items():
        if not rel.startswith(COMPONENTS_DIR):
            continue
        if rel in registered_components:
            continue
        if ".test." in Path(rel).name or ".spec." in Path(rel).name:
            continue
        warnings.extend(check_unregistered_component_warning(rel, text))

    registered_call_sites = set(CALL_SITE_REQUIREMENTS.keys())
    for rel, text in files.items():
        if not rel.startswith(UI_DIR) or rel.startswith(COMPONENTS_DIR):
            continue
        if "/" in rel[len(UI_DIR) :]:
            continue  # 「直下」のみ対象（url/ 等のサブディレクトリは対象外）
        if ".test." in Path(rel).name or ".spec." in Path(rel).name:
            continue
        warnings.extend(check_unregistered_call_site_warning(rel, text, registered_call_sites))

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
    # 関数呼び出し形式（`<Button>` JSX を使わず `buttonVariants({...})` で className 文字列を
    # 組み立てる呼び出しサイト。`pagination.tsx` 等・Issue #83）を模した最小フィクスチャ。
    # 対象コンポーネントと無関係な `<span className="text-sm ...">` を意図的に含める
    # （ファイル全体走査に戻ると誤検知することを固定するための回帰ケース・下記 CASES 参照）。
    pagination = (
        "const linkClassName = buttonVariants({ variant: 'ghost', size: 'default' })\n"
        "export function Pagination({ current }) {\n"
        "  return (\n"
        "    <nav>\n"
        "      <span className={linkClassName}>prev</span>\n"
        "      <span aria-current=\"page\" className=\"text-sm font-medium\">\n"
        "        {current.page}\n"
        "      </span>\n"
        "    </nav>\n"
        "  )\n"
        "}\n"
    )
    return {
        "src/ui/components/button.tsx": button,
        "src/ui/components/input.tsx": input_tsx,
        "app/globals.css": globals_css,
        "src/ui/search-form.tsx": search_form,
        "src/ui/pagination.tsx": pagination,
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
    "検査4: search-form.tsx の Input の リテラル className に text-sm",
    lambda f: f.__setitem__(
        "src/ui/search-form.tsx",
        f["src/ui/search-form.tsx"].replace('className="flex-1"', 'className="flex-1 text-sm"'),
    ),
    1, 0,
)

_case(
    "回帰ケース（Issue #83）: search-form.tsx の <form> タグ（Input/Button 以外）の "
    "className は呼び出しサイト範囲外なので、text-* を足しても誤検知しない"
    "（呼び出しサイトスコープ化前はファイル全体走査で誤検知していた）",
    lambda f: f.__setitem__(
        "src/ui/search-form.tsx",
        f["src/ui/search-form.tsx"].replace('className="flex gap-2"', 'className="flex gap-2 text-sm"'),
    ),
    0, 0,
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
    "検査4回帰（Issue #828 CRITICAL #1）: オブジェクトリテラルの className: プロパティ構文"
    "（`buttonVariants({ className: '...' })`）に h-*/text-* があれば検出する（`className=` の"
    "JSX 属性構文しか見ていなかった旧実装は検知できていなかった）",
    lambda f: f.__setitem__(
        "src/ui/search-form.tsx",
        f["src/ui/search-form.tsx"].replace(
            '<Button type="submit" size="xl">検索</Button>',
            '<Button type="submit" size="xl" data-x={buttonVariants({ '
            "variant: 'ghost', size: 'xl', className: 'h-20 text-xl whitespace-normal' "
            "})}>検索</Button>",
        ),
    ),
    2, 0,  # h-20 と text-xl の 2 トークン（size は xl にして UI-DIM-5 を誘発しないようにする）
)

_case(
    "検査4回帰（Issue #828 CRITICAL #1）: pagination.tsx（buttonVariants 関数呼び出し形式）の "
    "className: プロパティに h-8 を追加すると検出する",
    lambda f: f.__setitem__(
        "src/ui/pagination.tsx",
        f["src/ui/pagination.tsx"].replace(
            "buttonVariants({ variant: 'ghost', size: 'default' })",
            "buttonVariants({ variant: 'ghost', size: 'default', className: 'h-8' })",
        ),
    ),
    1, 0,
)

_case(
    "検査4回帰: className: プロパティのシングルクォート文字列でも検出できる（ダブルクォートに限らない）",
    lambda f: f.__setitem__(
        "src/ui/pagination.tsx",
        f["src/ui/pagination.tsx"].replace(
            "buttonVariants({ variant: 'ghost', size: 'default' })",
            'buttonVariants({ variant: "ghost", size: "default", className: "h-8" })',
        ),
    ),
    1, 0,
)

_case(
    "検査5回帰（Issue #828 CRITICAL #2）: JSX タグ属性の中にネストした `size:` "
    "（`onClick={() => track({ size: 'xl' })}`）があっても、本当の tier 不足（size=\"xs\"）を "
    "正しく検出できる（ネストした size に惑わされて見逃さない）",
    lambda f: f.__setitem__(
        "src/ui/search-form.tsx",
        f["src/ui/search-form.tsx"].replace(
            '<Button type="submit" size="xl">検索</Button>',
            "<Button type=\"submit\" onClick={() => track({ size: 'xl', label: 'x' })} "
            'size="xs">検索</Button>',
        ),
    ),
    1, 0,
)

_case(
    "検査5回帰（Issue #828 CRITICAL #2・逆順）: ネストした size がタグ属性の size より前にあっても "
    "誤検知しない（正当な size=\"xl\" を正しく採用する）",
    lambda f: f.__setitem__(
        "src/ui/search-form.tsx",
        f["src/ui/search-form.tsx"].replace(
            '<Input id="q" name="q" size="xl" className="flex-1" defaultValue={keyword} />',
            "<Input id=\"q\" name=\"q\" onClick={() => track({ size: 'xs' })} size=\"xl\" "
            'className="flex-1" defaultValue={keyword} />',
        ),
    ),
    0, 0,
)

_case(
    "干渉検証（Issue #828 CRITICAL #1×#2）: 同じ呼び出しサイト本体にネストした "
    "`size:`（onClick 内の track({size:'md'})）と className: プロパティのリテラル `h-10` が "
    "同時にあっても、tier 判定（トップレベルの size=\"xl\" を正しく採用し違反なしと判定）と "
    "className 判定（h-10 を正しく検出）が互いの前提を壊さず両立する",
    lambda f: f.__setitem__(
        "src/ui/pagination.tsx",
        f["src/ui/pagination.tsx"].replace(
            "buttonVariants({ variant: 'ghost', size: 'default' })",
            "buttonVariants({ variant: 'ghost', onClick: () => track({ size: 'xs' }), "
            "size: 'xl', className: 'h-10' })",
        ),
    ),
    1, 0,  # h-10 の className 違反のみ（tier は xl >= 必要 md なので違反なし）
)

_case(
    "検査3回帰（Issue #828 CRITICAL #3）: 閉じ括弧の無い壊れた `buttonVariants(` の後に "
    "無関係な `)` がファイル末尾付近にあっても「見つかった」と誤判定せず安全にスキップする"
    "（旧ガード `code[close-1] != \")\"` は TS/TSX ではファイル末尾付近にほぼ必ず `)` があるため "
    "誤判定していた・本体 span がファイル末尾までの巨大な範囲になり無関係な text-* まで誤検知する）",
    lambda f: f.__setitem__(
        "src/ui/pagination.tsx",
        # 末尾を意図的に ')' で終わらせる（旧ガードの誤判定条件を再現するため）。
        f["src/ui/pagination.tsx"]
        + "\nconst broken = buttonVariants({ size: 'default'\n"
        + "const unrelatedTail = (1 + 2)",
    ),
    0, 0,
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

# --- 検査4/5: 関数呼び出し形式（`buttonVariants({...})`）の呼び出しサイト対応（Issue #83）----

_case(
    "検査5: pagination.tsx（buttonVariants 関数呼び出し形式）の size を tier 不足（xs）に変える",
    lambda f: f.__setitem__(
        "src/ui/pagination.tsx",
        f["src/ui/pagination.tsx"].replace("size: 'default'", "size: 'xs'"),
    ),
    1, 0,
)

_case(
    "回帰ケース（Issue #83）: pagination.tsx の Button/buttonVariants と無関係な "
    "<span className=\"text-lg\"> はファイル全体走査に戻すと誤検知するが、呼び出しサイト範囲"
    "スコープなら誤検知しない",
    lambda f: f.__setitem__(
        "src/ui/pagination.tsx",
        f["src/ui/pagination.tsx"].replace(
            'className="text-sm font-medium"', 'className="text-lg font-medium"'
        ),
    ),
    0, 0,
)

_case(
    "Warning: src/ui/ 直下の未登録ファイルが buttonVariants を使用",
    lambda f: f.__setitem__(
        "src/ui/some-widget.tsx",
        "export function SomeWidget() {\n"
        "  return <a className={buttonVariants({ size: 'default' })}>x</a>\n"
        "}\n",
    ),
    0, 1,
)

_case(
    "Warning: src/ui/ 直下の未登録ファイルが <Button> JSX を使用",
    lambda f: f.__setitem__(
        "src/ui/some-widget.tsx",
        "export function SomeWidget() {\n"
        "  return <Button size=\"sm\">x</Button>\n"
        "}\n",
    ),
    0, 1,
)

_case(
    "Warning対象外: src/ui/ のサブディレクトリ（直下ではない）は未登録呼び出しサイト検査の対象外",
    lambda f: f.__setitem__(
        "src/ui/url/some-widget.tsx",
        "export function SomeWidget() {\n"
        "  return <a className={buttonVariants({ size: 'default' })}>x</a>\n"
        "}\n",
    ),
    0, 0,
)

_case(
    "Warning: src/ui/ 直下の未登録ファイルが <Input> JSX を使用"
    "（Issue #828 CRITICAL #4: 旧実装は Button/buttonVariants しか見ておらず "
    "COMPONENT_CALL_FN に既に登録済みの Input を見落としていた）",
    lambda f: f.__setitem__(
        "src/ui/some-widget.tsx",
        "export function SomeWidget() {\n  return <Input size=\"sm\" />\n}\n",
    ),
    0, 1,
)

_case(
    "Warning: src/ui/ 直下の未登録ファイルが inputVariants 関数呼び出しを使用",
    lambda f: f.__setitem__(
        "src/ui/some-widget.tsx",
        "export function SomeWidget() {\n"
        "  return <input className={inputVariants({ size: 'sm' })} />\n"
        "}\n",
    ),
    0, 1,
)

_case(
    "Warning: src/ui/ 直下の未登録ファイルが named import のエイリアス "
    "（`import { buttonVariants as bv }`）経由で呼び出している（Issue #828 CRITICAL #4）",
    lambda f: f.__setitem__(
        "src/ui/some-widget.tsx",
        "import { buttonVariants as bv } from './components/button'\n"
        "export function SomeWidget() {\n"
        "  return <a className={bv({ size: 'default' })}>x</a>\n"
        "}\n",
    ),
    0, 1,
)

_case(
    "Warning対象外: エイリアスが COMPONENT_CALL_FN の関数名と無関係なら誤検知しない",
    lambda f: f.__setitem__(
        "src/ui/some-widget.tsx",
        "import { someUnrelatedFn as x } from './lib/util'\n"
        "export function SomeWidget() {\n  return <a>{x()}</a>\n}\n",
    ),
    0, 0,
)

_case(
    "Warning: src/ui/ 直下の未登録ファイルが namespace import 経由の JSX 名前空間タグ "
    "（`<ButtonNs.Button>`）でコンポーネントを使用している（正規表現ベースでは解決できないため "
    "見落とし方向に倒さず Warning で可視化する・Issue #828 CRITICAL #4）",
    lambda f: f.__setitem__(
        "src/ui/some-widget.tsx",
        "import * as ButtonNs from './components/button'\n"
        "export function SomeWidget() {\n"
        "  return <ButtonNs.Button size=\"sm\">x</ButtonNs.Button>\n"
        "}\n",
    ),
    0, 1,
)

_case(
    "Warning対象外: コンポーネントモジュールと無関係な namespace import "
    "（`import * as React from 'react'`）は誤検知しない",
    lambda f: f.__setitem__(
        "src/ui/some-widget.tsx",
        "import * as React from 'react'\n"
        "export function SomeWidget() {\n  return React.createElement('div')\n}\n",
    ),
    0, 0,
)

_case(
    "Warning対象外: .test.tsx は未登録呼び出しサイト検査の対象外",
    lambda f: f.__setitem__(
        "src/ui/some-widget.test.tsx",
        "export function SomeWidget() {\n"
        "  return <a className={buttonVariants({ size: 'default' })}>x</a>\n"
        "}\n",
    ),
    0, 0,
)

_case(
    "Warning対象外: CALL_SITE_REQUIREMENTS 登録済みファイル（pagination.tsx）は "
    "未登録呼び出しサイト警告の対象外",
    lambda f: None,  # baseline の pagination.tsx が既に登録済み
    0, 0,
)


def _direct_span_assertions() -> list[str]:
    """`CASES`（`run_checks` のエラー/警告件数だけを見る表駆動テスト）では判別しづらい、
    `find_call_site_spans` 自体の境界条件を直接検証する（Issue #828 CRITICAL #3）。

    表駆動の「検査3回帰」ケースは `run_checks` 経由で 0 エラー / 0 警告になることまでは
    確認できるが、それだけでは「正しく span を作らなかった（fix）」のか「span は暴走したが
    たまたま中身に禁止トークンが無かった（bug のまま）」のかを区別できない。ここでは
    `find_call_site_spans` の戻り値そのものを直接検証し、両者を確実に区別する。
    """
    failures: list[str] = []
    broken_src = "buttonVariants({ size: 'default'\nconst unrelatedTail = (1 + 2)"
    spans = find_call_site_spans(strip_comments(broken_src), "Button")
    if spans:
        failures.append(
            "find_call_site_spans/broken_paren_before_unrelated_close_paren: "
            "閉じ括弧の無い `buttonVariants(` の後方に無関係な `)` があると、本体 span が"
            f"そこまで暴走して誤検出された（旧ガードの偽陽性が再現している）: {spans!r}"
        )
    return failures


def run_self_test() -> int:
    failures: list[str] = []
    failures.extend(_direct_span_assertions())
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

    # `src/ui/` 直下（サブディレクトリを除く）も読み込む: 未登録呼び出しサイト Warning
    # （`check_unregistered_call_site_warning`）の対象を disk から拾うため（Issue #83）。
    # 🔴 `.ts`（`.tsx` のみ）も走査する（Issue #828 CRITICAL 指摘）: `COMPONENTS_DIR` 側は
    # `.ts` / `.tsx` の両方を rglob しているのに、`UI_DIR` 側は `.tsx` のみで揃っていなかった。
    # `src/ui/inline-template.ts` のような `.ts` ファイルが Button/Input を関数呼び出し形式で
    # 使っても検知できないまま素通りする穴になっていた。
    ui_dir = REPO_ROOT / UI_DIR
    if ui_dir.is_dir():
        for pattern in ("*.ts", "*.tsx"):
            for p in ui_dir.glob(pattern):
                if p.is_file():
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
