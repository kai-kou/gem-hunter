#!/usr/bin/env python3
"""check_rate_limit_wiring.py — レート制限の「配線し忘れ」を止める双方向ゲート（Issue #442）

【なぜ必要か】
Cloudflare Rate Limiting binding（`wrangler.jsonc` の `ratelimits`）は **宣言しただけでは何も起きない**。
実際に `limit()` を呼ぶ配線（`src/composition/rate-limit.ts` の `enforce*RateLimit`）がアプリコード側に要る。
さらにこの機能は **フェイルオープン設計**（IP 不明 / `RATE_LIMIT_SALT` 未設定 / binding 未提供のとき黙って通す）
なので、**「配線し忘れ」と「正常」が実行時に区別できない**。だから機械検査が要る。

実際に起きた事故:
  1. `SP-19` で新設された `/{locale}/gems` に配線し忘れ、仕様（`cloudflare-infrastructure.md` §3.3）の
     適用経路表も更新されなかった。誰も気づかなかった
  2. Issue #442 起票時、`src/` 配下だけを grep して「どこからも呼ばれていない」と誤結論した
     （本リポジトリの App Router は **リポジトリルート直下の `app/`**。`src/app/` は存在しない）

【正本】
適用経路の正本は `docs/03_design/infrastructure/cloudflare-infrastructure.md` の
`<!-- rate-limit-wiring:begin -->` 〜 `<!-- rate-limit-wiring:end -->` に囲まれた表。
本スクリプトは「何経路あるべきか」を自分では持たず、その表と実コードを突き合わせるだけ。

【検査（すべて Error・`run_checks.sh` を止める）】
  1. ✅ 適用 行の検証: そのファイルに `enforce*RateLimit(` の呼び出しが実在する
  2. ❌ 対象外 行の検証: そのファイルに呼び出しが **存在しない**（対象外と書いて実は掛かっている逆ドリフト）
  3. 🔴 網羅性の検証（核心）: `app/` 配下で **URL を生みコードが走る全ファイル**（`page` / `route` に加え
     `opengraph-image` 等のコード生成メタデータルート）を実際に列挙し、
     表に載っていないものがあれば FAIL する（`/gems` を取りこぼした構造そのものを止める）
  4. 死蔵の検証: `src/composition/rate-limit.ts` が export する `enforce*RateLimit` のうち、
     表のどの ✅ 行からも使われていないものがあれば FAIL する
  5. キー接頭辞の一致検証: 表が宣言した接頭辞（`search:` / `gems:`）が実装に文字列として存在し、
     かつ ✅ 行が呼んでいる関数の実装接頭辞と食い違っていない

使い方:
    python3 tools/check_rate_limit_wiring.py              # 本判定（0=PASS / 1=FAIL）
    python3 tools/check_rate_limit_wiring.py --self-test  # 検査ロジック自身のテスト（実ファイル非依存）
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

DOC_PATH = REPO_ROOT / "docs" / "03_design" / "infrastructure" / "cloudflare-infrastructure.md"
APP_DIR = REPO_ROOT / "app"
COMPOSITION_PATH = REPO_ROOT / "src" / "composition" / "rate-limit.ts"

BEGIN_MARKER = "<!-- rate-limit-wiring:begin -->"
END_MARKER = "<!-- rate-limit-wiring:end -->"

# App Router が **URL を生み、リクエストごとに自前のコードを実行する** 特殊ファイルの語幹。
# 出典: `node_modules/next/dist/docs/01-app/03-api-reference/03-file-conventions/`
#       （`page.md` / `route.md` と `01-metadata/` 配下の opengraph-image・app-icons・sitemap・robots・manifest）。
#
# 🔴 なぜ「`page.tsx` / `route.ts` の 2 つ」ではダメか（Issue #442 の再発防止の本体）:
#    `app/[locale]/opengraph-image.tsx` は URL を持ち、リクエストのたびに画像生成コードが走る
#    （= CPU を消費する経路）のに、ファイル名を 2 種類ハードコードしていたせいで **検査対象からも
#    正本表からも漏れていた**。ファイル種別の軸に穴があると「新経路の載せ忘れ」を止められない。
#
# 【この集合に含めるもの】コードで生成する（＝ `.ts` / `.tsx` で書く）メタデータルートと、
#    `page` / `route`。いずれも実行時に自前のコードが走るので、間引きの要否を判断する意味がある。
# 【意図的に含めないもの】
#    - 静的アセット版のメタデータ（`icon.png` / `favicon.ico` / `opengraph-image.png` など）:
#      ビルド成果物をそのまま配るだけでアプリのコードが走らない。`enforce*RateLimit(` を書く場所が
#      無いので表に並べても永久に「❌ 対象外」が増えるだけのノイズになる（本リポジトリの
#      `app/favicon.ico` / `app/icon.png` がこれに当たる）
#    - 描画の部品（`layout` / `template` / `loading` / `error` / `not-found` / `default`）:
#      単独では URL を持たず、`page` の描画の一部として走る。入口は `page` 側で数えれば足りる
#      （本リポジトリの `app/[locale]/layout.tsx` / `not-found.tsx` がこれに当たる）
#    - 同じ階層に同居する実装補助ファイル（`og-background-data.ts` 等）とテスト（`*.test.ts`）:
#      語幹が一致しないため自然に除外される
ROUTE_PRODUCING_STEMS = (
    "page",            # UI ルート
    "route",           # Route Handler
    "opengraph-image",  # 以下は「コードで生成するメタデータルート」（01-metadata/）
    "twitter-image",
    "icon",
    "apple-icon",
    "sitemap",
    "robots",
    "manifest",
)
ROUTE_PRODUCING_EXTENSIONS = (".ts", ".tsx")
ENTRYPOINT_FILE_NAMES = tuple(
    f"{stem}{ext}" for stem in ROUTE_PRODUCING_STEMS for ext in ROUTE_PRODUCING_EXTENSIONS
)

# 表のセルで「実ファイルを指していない」placeholder（`...` の行など）
PLACEHOLDER_CELLS = {"", "...", "…", "—", "-", "–"}

APPLIED_MARK = "✅"
EXCLUDED_MARK = "❌"

# `enforceSearchRateLimit(` のような **呼び出し**（import 文は `(` が続かないので拾わない）
CALL_RE = re.compile(r"\b(enforce\w*RateLimit)\s*\(")
# `export async function enforceGemListRateLimit` / `export const enforceX = ...`
EXPORT_RE = re.compile(r"^export\s+(?:async\s+)?(?:function|const)\s+(enforce\w*RateLimit)\b", re.MULTILINE)
# `'search:'` のようなコロン終わりの文字列リテラル
PREFIX_LITERAL_RE = re.compile(r"""['"]([A-Za-z0-9_.\-]+:)['"]""")

EXIT_OK = 0
EXIT_VIOLATION = 1


# ---------------------------------------------------------------------------
# 純粋関数（self-test はここへ文字列を直接渡す。実リポジトリのファイルは書き換えない）
# ---------------------------------------------------------------------------

def _strip_cell(cell: str) -> str:
    """表セルの前後空白と装飾（バッククォート・太字）を落とす。"""
    return cell.strip().strip("`").replace("**", "").strip()


def extract_wiring_table(markdown: str) -> tuple[list[str], str | None]:
    """マーカーで囲まれた表の行だけを返す。マーカーが無ければ (＿, エラー文) を返す。"""
    begin = markdown.find(BEGIN_MARKER)
    end = markdown.find(END_MARKER)
    if begin == -1 or end == -1 or end < begin:
        return [], (
            f"{DOC_PATH.name}: {BEGIN_MARKER} / {END_MARKER} の適用経路表が見つからない"
            " → 適用経路の正本表をこのマーカーで囲んで記載する"
        )
    body = markdown[begin + len(BEGIN_MARKER) : end]
    return [line for line in body.splitlines() if line.strip().startswith("|")], None


def parse_wiring_rows(table_lines: list[str], errors: list[str]) -> dict[str, dict]:
    """表の行を {ファイルパス: {"applied": bool, "prefix": str|None, "label": str}} へ落とす。"""
    rows: dict[str, dict] = {}
    for line in table_lines:
        cells = [c for c in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        label, path_cell, applied_cell, prefix_cell = (
            _strip_cell(cells[0]),
            _strip_cell(cells[1]),
            cells[2].strip(),
            _strip_cell(cells[3]),
        )
        # 見出し行・区切り行・placeholder 行は読み飛ばす
        if set(path_cell) <= {"-", ":", " "} or path_cell in PLACEHOLDER_CELLS:
            continue
        if path_cell == "ファイル" or label == "経路":
            continue

        applied = APPLIED_MARK in applied_cell
        excluded = EXCLUDED_MARK in applied_cell
        if applied == excluded:  # どちらも無い / どちらも有る
            errors.append(
                f"{path_cell}: 「レート制限」列が {APPLIED_MARK} 適用 / {EXCLUDED_MARK} 対象外 のどちらでもない"
                f"（実際: {applied_cell.strip()!r}） → どちらかに直す"
            )
            continue
        if path_cell in rows:
            errors.append(f"{path_cell}: 正本表に重複行がある → 1 ファイル 1 行に統合する")
            continue

        prefix = None if prefix_cell in PLACEHOLDER_CELLS else prefix_cell
        if applied and prefix is None:
            errors.append(
                f"{path_cell}: 「{APPLIED_MARK} 適用」なのに「キー接頭辞」列が空 / — になっている"
                " → 実装が使う接頭辞（例 `search:`）を書く"
            )
        if not applied and prefix is not None:
            errors.append(
                f"{path_cell}: 「{EXCLUDED_MARK} 対象外」なのに接頭辞 `{prefix}` が書かれている → — に直す"
            )
        rows[path_cell] = {"applied": applied, "prefix": prefix, "label": label}
    return rows


def strip_comments(source: str) -> str:
    """TS/TSX から行コメント・ブロックコメントを取り除く（文字列リテラルの中身は保つ）。

    コメントアウトされた `// await enforceGemListRateLimit(...)` を「配線済み」と誤認しないための前処理。
    素朴に `//` で切ると `'https://…'` を壊すため、文字列リテラル（`'` / `"` / テンプレート）を跨がない
    最小限のスキャナにしている。
    """
    out: list[str] = []
    i, n = 0, len(source)
    quote: str | None = None
    while i < n:
        ch = source[i]
        if quote:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(source[i + 1])
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
        if source.startswith("//", i):
            while i < n and source[i] != "\n":
                i += 1
            continue
        if source.startswith("/*", i):
            end = source.find("*/", i + 2)
            i = n if end == -1 else end + 2
            out.append(" ")
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def extract_calls(source: str) -> set[str]:
    """ソース中の `enforce*RateLimit(` 呼び出し名の集合（import 文・コメントは含まない）。"""
    return set(CALL_RE.findall(strip_comments(source)))


def extract_exported_enforcers(source: str) -> dict[str, str | None]:
    """`src/composition/rate-limit.ts` の export 名 → その実装が使うキー接頭辞（不明なら None）。"""
    source = strip_comments(source)
    matches = list(EXPORT_RE.finditer(source))
    result: dict[str, str | None] = {}
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(source)
        body = source[match.start() : end]
        literal = PREFIX_LITERAL_RE.search(body)
        result[match.group(1)] = literal.group(1) if literal else None
    return result


def check_wiring(
    doc_markdown: str,
    entrypoint_sources: dict[str, str],
    composition_source: str,
) -> list[str]:
    """正本表・エントリポイント実装・composition root を突き合わせて違反メッセージを返す。

    引数はすべて文字列（＝ファイル I/O から独立）なので、self-test はここを直接叩ける。
    `entrypoint_sources` のキーが「`app/` 配下に実在するエントリポイントの全集合」である。
    """
    errors: list[str] = []

    table_lines, marker_error = extract_wiring_table(doc_markdown)
    if marker_error:
        errors.append(marker_error)
        return errors

    rows = parse_wiring_rows(table_lines, errors)
    if not rows:
        errors.append(
            f"{DOC_PATH.name}: 適用経路表に 1 行も読み取れる行が無い"
            " → `| 経路 | ファイル | レート制限 | キー接頭辞 |` 形式で経路を列挙する"
        )
        return errors

    exported = extract_exported_enforcers(composition_source)
    implementation_prefixes = set(PREFIX_LITERAL_RE.findall(strip_comments(composition_source)))
    used_by_table: set[str] = set()

    # --- 1 / 2. 表の宣言と実コードの双方向突き合わせ --------------------------
    for path, row in sorted(rows.items()):
        source = entrypoint_sources.get(path)
        if source is None:
            errors.append(
                f"{path}: 正本表に載っているが実ファイルが存在しない（`app/` 配下のエントリポイントではない）"
                " → 表から削除するか、パスの誤りを直す"
            )
            continue

        calls = extract_calls(source)
        if row["applied"] and not calls:
            errors.append(
                f"{path}: 表は「{APPLIED_MARK} 適用」だが `enforce*RateLimit(` の呼び出しが無い（配線し忘れ）"
                " → 同ファイルで `enforce...RateLimit(...)` を呼ぶか、表を「❌ 対象外」に直す"
            )
        if not row["applied"] and calls:
            errors.append(
                f"{path}: 表は「{EXCLUDED_MARK} 対象外」だが {', '.join(sorted(calls))} を呼んでいる（逆ドリフト）"
                " → 表を「✅ 適用」に直すか、呼び出しを外す"
            )

        if not row["applied"]:
            continue
        used_by_table |= calls

        # --- 5. キー接頭辞の一致 ---------------------------------------------
        prefix = row["prefix"]
        if prefix is None:
            continue
        if prefix not in implementation_prefixes:
            errors.append(
                f"{path}: 表が宣言した接頭辞 `{prefix}` が {COMPOSITION_PATH.name} の実装に文字列として存在しない"
                " → 実装のキー接頭辞と表を一致させる"
            )
        for call in sorted(calls):
            actual = exported.get(call)
            if actual is not None and actual != prefix:
                errors.append(
                    f"{path}: 表は接頭辞 `{prefix}` と宣言しているが、呼んでいる {call} の実装は `{actual}` を使う"
                    " → 表と実装のどちらが正しいか決めて揃える"
                )

    # --- 3. 網羅性（表に載っていないエントリポイント）------------------------
    for path in sorted(set(entrypoint_sources) - set(rows)):
        errors.append(
            f"{path}: `app/` 配下のエントリポイントだが正本表に載っていない（新経路の載せ忘れ）"
            f" → {DOC_PATH.name} の {BEGIN_MARKER} 表に 1 行追加する（✅ 適用 / ❌ 対象外 を明記）"
        )

    # --- 4. 死蔵（export したが表のどの ✅ 行からも使われていない）------------
    for name in sorted(set(exported) - used_by_table):
        errors.append(
            f"{name}: {COMPOSITION_PATH.name} が export しているが表の「{APPLIED_MARK} 適用」行の"
            "どこからも呼ばれていない（死蔵） → 対象経路へ配線するか export を削除する"
        )

    return errors


# ---------------------------------------------------------------------------
# 実リポジトリの読み取り
# ---------------------------------------------------------------------------

def collect_entrypoint_sources(app_dir: Path, repo_root: Path = REPO_ROOT) -> dict[str, str]:
    """`app/` 配下の `page.tsx` / `route.ts` を実際に列挙して {相対パス: ソース} を返す。"""
    sources: dict[str, str] = {}
    if not app_dir.is_dir():
        return sources
    for extension in ROUTE_PRODUCING_EXTENSIONS:
        for path in app_dir.rglob(f"*{extension}"):
            if path.name in ENTRYPOINT_FILE_NAMES:
                sources[path.relative_to(repo_root).as_posix()] = path.read_text(encoding="utf-8")
    return sources


def run_checks(
    doc_path: Path = DOC_PATH,
    app_dir: Path = APP_DIR,
    composition_path: Path = COMPOSITION_PATH,
) -> list[str]:
    """実ファイルを読んで検査する。読めないファイルは違反として報告する（黙って PASS にしない）。"""
    errors: list[str] = []

    try:
        doc_markdown = doc_path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"{doc_path}: 適用経路表の正本を読めない（{exc}） → ファイルの存在とパスを確認する"]

    try:
        composition_source = composition_path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(
            f"{composition_path}: レート制限の composition root を読めない（{exc}）"
            " → `enforce*RateLimit` の実装先を確認する"
        )
        composition_source = ""

    if not app_dir.is_dir():
        errors.append(
            f"{app_dir}: App Router のディレクトリが見つからない"
            " → 本リポジトリの App Router はリポジトリルート直下の `app/`（`src/app/` ではない）"
        )

    entrypoints = collect_entrypoint_sources(app_dir)
    return errors + check_wiring(doc_markdown, entrypoints, composition_source)


# ---------------------------------------------------------------------------
# --self-test（実ファイル非依存。検査が「違反を実際に検出できること」を確かめる）
# ---------------------------------------------------------------------------

_DOC_OK = f"""
## 3.3 レート制限の適用経路

{BEGIN_MARKER}
| 経路 | ファイル | レート制限 | キー接頭辞 |
|---|---|---|---|
| 検索画面 | `app/[locale]/page.tsx` | ✅ 適用 | `search:` |
| Gem 一覧 | `app/[locale]/gems/page.tsx` | ✅ 適用 | `gems:` |
| ログアウト | `app/api/auth/logout/route.ts` | ❌ 対象外 | — |
{END_MARKER}
"""

_COMPOSITION_OK = """
async function enforceRateLimit(headers: Headers, keyPrefix: string): Promise<void> {}

export async function enforceSearchRateLimit(headers: Headers): Promise<void> {
  await enforceRateLimit(headers, 'search:')
}

export async function enforceGemListRateLimit(headers: Headers): Promise<void> {
  await enforceRateLimit(headers, 'gems:')
}
"""

_SOURCES_OK = {
    "app/[locale]/page.tsx": (
        "import { enforceSearchRateLimit } from '@/src/composition/rate-limit'\n"
        "await enforceSearchRateLimit(await headers())\n"
    ),
    "app/[locale]/gems/page.tsx": (
        "import { enforceGemListRateLimit } from '@/src/composition/rate-limit'\n"
        "await enforceGemListRateLimit(await headers())\n"
    ),
    "app/api/auth/logout/route.ts": "export async function POST() { return new Response() }\n",
}


def self_test() -> int:
    failures: list[str] = []

    def expect_ok(label: str, errors: list[str]) -> None:
        if errors:
            failures.append(f"{label}: 違反ゼロを期待したが {errors}")

    def expect_fail(label: str, errors: list[str], keyword: str) -> None:
        if not errors:
            failures.append(f"{label}: 違反を検出できていない（検査が素通りしている）")
        elif not any(keyword in e for e in errors):
            failures.append(f"{label}: 期待キーワード {keyword!r} を含む違反が無い: {errors}")

    # 1) 正常構成は素通りする（検査が常に赤いだけの飾りでないことの確認）
    expect_ok("正常構成", check_wiring(_DOC_OK, dict(_SOURCES_OK), _COMPOSITION_OK))

    # 2) マーカーが無い（表の実装待ち・削除）→ 黙って PASS にしない
    expect_fail(
        "マーカー欠落",
        check_wiring("## 3.3 レート制限\n本文だけ\n", dict(_SOURCES_OK), _COMPOSITION_OK),
        "見つからない",
    )

    # 3) ✅ 適用と書かれたファイルに呼び出しが無い（＝ 今回の事故そのもの）
    no_call = dict(_SOURCES_OK)
    no_call["app/[locale]/gems/page.tsx"] = "export default function Page() { return null }\n"
    expect_fail("✅ なのに未配線", check_wiring(_DOC_OK, no_call, _COMPOSITION_OK), "配線し忘れ")

    # 4) ❌ 対象外と書かれたファイルに呼び出しがある（逆ドリフト）
    stray_call = dict(_SOURCES_OK)
    stray_call["app/api/auth/logout/route.ts"] = "await enforceSearchRateLimit(request.headers)\n"
    expect_fail("❌ なのに配線済み", check_wiring(_DOC_OK, stray_call, _COMPOSITION_OK), "逆ドリフト")

    # 5) `app/` に実在するエントリポイントが表に載っていない（網羅性・本検査の核心）
    new_route = dict(_SOURCES_OK)
    new_route["app/api/trending/route.ts"] = "export async function GET() { return new Response() }\n"
    expect_fail("表に無い新経路", check_wiring(_DOC_OK, new_route, _COMPOSITION_OK), "載っていない")

    # 5-b) 🔴 コード生成メタデータルート（`opengraph-image.tsx`）の載せ忘れ（統合検証で見つかった穴）。
    #      `page.tsx` / `route.ts` だけを列挙していた頃はこの経路が検査対象から丸ごと漏れていた。
    og_route = dict(_SOURCES_OK)
    og_route["app/[locale]/opengraph-image.tsx"] = (
        "export default async function Image() { return new ImageResponse(<div />) }\n"
    )
    expect_fail("表に無い OG 画像ルート", check_wiring(_DOC_OK, og_route, _COMPOSITION_OK), "opengraph-image.tsx")

    # 5-c) 列挙対象の語幹集合そのものの回帰テスト（穴が再び開いていないこと）
    for required in ("page.tsx", "route.ts", "opengraph-image.tsx", "sitemap.ts", "robots.ts"):
        if required not in ENTRYPOINT_FILE_NAMES:
            failures.append(f"列挙対象に {required} が含まれていない（ファイル種別の軸に穴がある）")
    for excluded in ("layout.tsx", "not-found.tsx", "icon.png", "favicon.ico", "og-background-data.ts"):
        if excluded in ENTRYPOINT_FILE_NAMES:
            failures.append(f"列挙対象に {excluded} が混ざっている（URL を生まない / コードが走らない）")

    # 6) export された `enforce*RateLimit` が表のどの ✅ 行からも使われていない（死蔵）
    dead_export = _COMPOSITION_OK + (
        "\nexport async function enforceDigestRateLimit(headers: Headers): Promise<void> {\n"
        "  await enforceRateLimit(headers, 'digest:')\n}\n"
    )
    expect_fail("死蔵 export", check_wiring(_DOC_OK, dict(_SOURCES_OK), dead_export), "死蔵")

    # 7) 表が宣言した接頭辞が実装に文字列として存在しない
    doc_bad_prefix = _DOC_OK.replace("| `gems:` |", "| `gemlist:` |")
    expect_fail(
        "宣言接頭辞が実装に無い",
        check_wiring(doc_bad_prefix, dict(_SOURCES_OK), _COMPOSITION_OK),
        "文字列として存在しない",
    )

    # 8) 接頭辞が「呼んでいる関数の実装」と食い違う（実装には存在するが割り当てが逆）
    doc_swapped = _DOC_OK.replace(
        "| Gem 一覧 | `app/[locale]/gems/page.tsx` | ✅ 適用 | `gems:` |",
        "| Gem 一覧 | `app/[locale]/gems/page.tsx` | ✅ 適用 | `search:` |",
    )
    expect_fail(
        "接頭辞の割り当て食い違い",
        check_wiring(doc_swapped, dict(_SOURCES_OK), _COMPOSITION_OK),
        "実装は `gems:` を使う",
    )

    # 9) 表に載っているが実ファイルが存在しない（削除されたページの行が残っている）
    doc_ghost = _DOC_OK.replace(
        END_MARKER, "| 旧ページ | `app/[locale]/old/page.tsx` | ❌ 対象外 | — |\n" + END_MARKER
    )
    expect_fail("実ファイル不在の行", check_wiring(doc_ghost, dict(_SOURCES_OK), _COMPOSITION_OK), "実ファイルが存在しない")

    # 10) 「レート制限」列が ✅ / ❌ のどちらでもない
    doc_unknown_mark = _DOC_OK.replace("| ✅ 適用 | `gems:` |", "| 検討中 | `gems:` |")
    expect_fail("適用列が不正", check_wiring(doc_unknown_mark, dict(_SOURCES_OK), _COMPOSITION_OK), "どちらでもない")

    # 11) ✅ 適用なのに接頭辞列が空（枠の分離が宣言されていない）
    doc_no_prefix = _DOC_OK.replace("| ✅ 適用 | `gems:` |", "| ✅ 適用 | — |")
    expect_fail("✅ なのに接頭辞なし", check_wiring(doc_no_prefix, dict(_SOURCES_OK), _COMPOSITION_OK), "空 / — になっている")

    # 12) 同一ファイルの重複行
    doc_dup = _DOC_OK.replace(
        END_MARKER, "| Gem 一覧（重複） | `app/[locale]/gems/page.tsx` | ✅ 適用 | `gems:` |\n" + END_MARKER
    )
    expect_fail("重複行", check_wiring(doc_dup, dict(_SOURCES_OK), _COMPOSITION_OK), "重複行")

    # 13) import しただけ（呼び出していない）は「配線済み」と誤認しない
    import_only = dict(_SOURCES_OK)
    import_only["app/[locale]/gems/page.tsx"] = (
        "import { enforceGemListRateLimit } from '@/src/composition/rate-limit'\n"
        "export default function Page() { return null }\n"
    )
    expect_fail("import だけで未呼び出し", check_wiring(_DOC_OK, import_only, _COMPOSITION_OK), "配線し忘れ")

    # 14) コメントアウトされた呼び出しを「配線済み」と誤認しない
    commented_out = dict(_SOURCES_OK)
    commented_out["app/[locale]/gems/page.tsx"] = (
        "import { enforceGemListRateLimit } from '@/src/composition/rate-limit'\n"
        "// await enforceGemListRateLimit(await headers())\n"
        "/* await enforceGemListRateLimit(await headers()) */\n"
    )
    expect_fail("コメントアウトされた呼び出し", check_wiring(_DOC_OK, commented_out, _COMPOSITION_OK), "配線し忘れ")

    # 15) コメント除去が URL を含む文字列リテラルを壊さない（誤って呼び出しを消さない）
    with_url = dict(_SOURCES_OK)
    with_url["app/[locale]/gems/page.tsx"] = (
        "const doc = 'https://developers.cloudflare.com/'\n"
        "await enforceGemListRateLimit(await headers())\n"
    )
    expect_ok("URL 文字列があっても呼び出しを見失わない", check_wiring(_DOC_OK, with_url, _COMPOSITION_OK))

    # 16) 補助関数の単体検証
    if extract_calls("import { enforceSearchRateLimit } from 'x'\n") != set():
        failures.append("extract_calls: import 文を呼び出しとして誤検出している")
    if extract_calls("await enforceSearchRateLimit(h)") != {"enforceSearchRateLimit"}:
        failures.append("extract_calls: 呼び出しを検出できていない")
    if extract_exported_enforcers(_COMPOSITION_OK) != {
        "enforceSearchRateLimit": "search:",
        "enforceGemListRateLimit": "gems:",
    }:
        failures.append("extract_exported_enforcers: export 名と接頭辞の対応を取り出せていない")

    if failures:
        for label in failures:
            print(f"[rate-limit-wiring] SELF-TEST FAIL: {label}", file=sys.stderr)
        print(f"[rate-limit-wiring] self-test NG（{len(failures)} 件）", file=sys.stderr)
        return EXIT_VIOLATION
    print("[rate-limit-wiring] self-test OK（18 ケース: 正常 2 / 反例 14 / 補助関数・列挙集合 2）")
    return EXIT_OK


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--self-test", action="store_true", help="ネットワーク・実ファイル不要のユニットテストを実行する")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    errors = run_checks()
    if errors:
        for message in errors:
            print(f"[rate-limit-wiring] ERROR: {message}", file=sys.stderr)
        print(f"[rate-limit-wiring] NG（{len(errors)} 件）", file=sys.stderr)
        return EXIT_VIOLATION

    print("[rate-limit-wiring] OK（適用経路表と実配線・キー接頭辞・網羅性が一致）")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
