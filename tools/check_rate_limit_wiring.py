#!/usr/bin/env python3
"""check_rate_limit_wiring.py — レート制限の「配線し忘れ」を止める双方向ゲート（Issue #442）

【なぜ必要か】
Cloudflare Rate Limiting binding（`wrangler.jsonc` の `ratelimits`）は **宣言しただけでは何も起きない**。
実際に `limit()` を呼ぶ配線（`src/composition/rate-limit.ts` の `enforce*RateLimit`）がアプリコード側に要る。
さらにこの機能は **フェイルオープン設計**（IP 不明 / binding 未提供 / `RATE_LIMIT_SALT` 未設定 のとき黙って通す）
なので、**「配線し忘れ」と「正常」が実行時に区別できない**。だから機械検査が要る。
（判定順の正本は `src/composition/rate-limit.ts`。binding があるのに salt が無い場合だけ警告を出すため、
 binding 取得を salt 確認より先に置いている）

実際に起きた事故:
  1. `SP-19` で新設された `/{locale}/gems` に配線し忘れ、仕様（`cloudflare-infrastructure.md` §3.3）の
     適用経路表も更新されなかった。誰も気づかなかった
  2. Issue #442 起票時、`src/` 配下だけを grep して「どこからも呼ばれていない」と誤結論した
     （本リポジトリの App Router は **リポジトリルート直下の `app/`**。`src/app/` は存在しない）

【間接呼び出し（ラッパー経由）を認める理由・Issue #604】
`app/[locale]/page.tsx` と `app/api/search/route.ts` に重複していた「値オブジェクト変換 →
`enforceSearchRateLimit()`」という順序判断を `src/composition/search-guard.ts` の
`prepareSearchKeyword()` へ集約するリファクタ（コミット `fd23f99`）が入り、両ファイルから
`enforce*RateLimit(` の **直接呼び出し** が消えた。文字列一致だけを見ていた本スクリプトは
これを「配線し忘れ・死蔵」と誤検知した。実際には配線されている（`prepareSearchKeyword` が
内部で `await enforceSearchRateLimit(headers)` を呼ぶ）ため、`src/composition/*.ts` を走査して
「`enforce*RateLimit(` を `await` 付きで呼ぶ export 関数」を **ラッパー** として抽出し、
エントリポイント側のラッパー呼び出しも「配線あり」と認める（詳細は `extract_composition_wrappers`）。
ラッパー内部の `await` 欠落・呼び出し側の `await` 欠落はいずれも従来どおり ERROR にし、検査の強度は
落とさない（直接呼び出しと同じ 5 項目の検査を間接呼び出しにも適用する）。

【正本】
適用経路の正本は `docs/03_design/infrastructure/cloudflare-infrastructure.md` の
`<!-- rate-limit-wiring:begin -->` 〜 `<!-- rate-limit-wiring:end -->` に囲まれた表。
本スクリプトは「何経路あるべきか」を自分では持たず、その表と実コードを突き合わせるだけ。

【検査（すべて Error・`run_checks.sh` を止める）】
  1. ✅ 適用 行の検証: そのファイルに `enforce*RateLimit(` の呼び出しが実在する。あわせて
     1-a. 呼び出しに `await`（または `void` / `return`）が付いている（付いていないと
          `RateLimitExceededError` が unhandled rejection になり **一切間引かれない**。
          型情報なし ESLint も `tsc --noEmit` もこれを検出しないので本スクリプトが唯一のゲート）
     1-b. 呼び出しが usecase 呼び出し（`*UseCase(`）より **前** にある（重い処理を走らせてから
          間引くのは Issue #442 と同型の抜け。usecase が無いファイルはこの検査をスキップする）
  2. ❌ 対象外 行の検証: そのファイルに呼び出しが **存在しない**（対象外と書いて実は掛かっている逆ドリフト）
  3. 🔴 網羅性の検証（核心）: `app/` 配下で **URL を生みコードが走る全ファイル**（`page` / `route` に加え
     `opengraph-image` 等のコード生成メタデータルート）を実際に列挙し、
     表に載っていないものがあれば FAIL する（`/gems` を取りこぼした構造そのものを止める）
  4. 死蔵の検証: `src/composition/rate-limit.ts` が export する `enforce*RateLimit` のうち、
     表のどの ✅ 行からも使われていないものがあれば FAIL する
  5. キー接頭辞の一致検証: 表が宣言した接頭辞（`search:` / `gems:`）が実装に文字列として存在し、
     かつ ✅ 行が呼んでいる関数の実装接頭辞と食い違っていない
  6. 🔴 binding 宣言の検証（Issue #480）: `wrangler.jsonc` の `ratelimits[]` に binding 名の宣言が
     少なくとも 1 件あり、その名前が `src/infrastructure/platform/cloudflare-bindings.ts` の
     `rateLimiterBinding()` が参照する `env.RATE_LIMITER` の名前と一致する。上記 1〜5 は
     「アプリコードが binding を正しく呼んでいるか」を見るだけで、**binding 宣言自体が
     削除・リネーム・環境別 override で欠けても検出できない**（フェイルオープン設計のため
     `rateLimiterBinding()` は `undefined` を返すだけで例外にならず、全経路が黙って
     素通りする）。この検査はその抜けを塞ぐ

使い方:
    python3 tools/check_rate_limit_wiring.py              # 本判定（0=PASS / 1=FAIL）
    python3 tools/check_rate_limit_wiring.py --self-test  # 検査ロジック自身のテスト（実ファイル非依存）

【既知の限界（字句解析のみで完全な静的解析はしていない・Issue #604 レビュー指摘）】
本スクリプトは AST を持たず正規表現とブレースカウンタによる字句解析だけで判定する。以下 2 点は
意図的に対応していない（過剰実装を避けるため）。**composition ラッパー（`src/composition/*.ts`
の export 関数）へ分岐や紛らわしい文字列を持ち込む変更は、この限界により機械検査だけでは
配線状態を保証できないため、人手レビューが要る**:
  1. 文字列リテラル内に書かれた `await enforce*RateLimit(...)` のような記述を、実際の呼び出しと
     誤認しうる（`strip_comments` はコメントだけを取り除き、文字列リテラルの中身はそのまま保つ設計
     のため）。エラーメッセージ・ログ文言・テストの説明文字列などに関数名をそのまま書くと誤検出しうる。
  2. 到達可能性解析はしない。`if (false) { await enforce*RateLimit(...) }` のように実行時には
     絶対に到達しない分岐の内側にあっても、呼び出しが「存在する」というだけで配線ありと数える
     （直接呼び出しの検査も元々同じ限界を持つ・本改修はこの限界を拡大も縮小もしていない）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ts_source import find_function_body_end, strip_comments  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent

DOC_PATH = REPO_ROOT / "docs" / "03_design" / "infrastructure" / "cloudflare-infrastructure.md"
APP_DIR = REPO_ROOT / "app"
COMPOSITION_PATH = REPO_ROOT / "src" / "composition" / "rate-limit.ts"
# 🔴 ラッパー走査対象（Issue #604）。`prepareSearchKeyword` のような間接呼び出しを認識するため、
# `src/composition/` 配下全体（テストファイルと `rate-limit.ts` 自身を除く）を走査する。
COMPOSITION_DIR = REPO_ROOT / "src" / "composition"
# 🔴 binding 宣言の検証対象（Issue #480）。
WRANGLER_PATH = REPO_ROOT / "wrangler.jsonc"
BINDINGS_PATH = REPO_ROOT / "src" / "infrastructure" / "platform" / "cloudflare-bindings.ts"

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
# App Router はルート特殊ファイルを `.js` / `.jsx` / `.mjs` でも受け付ける
# （出典: `node_modules/next/dist/docs/01-app/03-api-reference/03-file-conventions/page.md` /
#  `route.md` の "File Extensions"）。本リポジトリに該当ファイルは無いが、
# 拡張子の軸に穴があると「新経路の載せ忘れ」を止められない（`ROUTE_PRODUCING_STEMS` と同じ理由）。
ROUTE_PRODUCING_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs")
ENTRYPOINT_FILE_NAMES = tuple(
    f"{stem}{ext}" for stem in ROUTE_PRODUCING_STEMS for ext in ROUTE_PRODUCING_EXTENSIONS
)

# 表のセルで「実ファイルを指していない」placeholder（`...` の行など）
PLACEHOLDER_CELLS = {"", "...", "…", "—", "-", "–"}

APPLIED_MARK = "✅"
EXCLUDED_MARK = "❌"

# `enforceSearchRateLimit(` のような **呼び出し**（import 文は `(` が続かないので拾わない）
CALL_RE = re.compile(r"\b(enforce\w*RateLimit)\s*\(")
# 呼び出しの **結果を捨てていない** 形だけを「配線済み」と認める。
# `enforce*RateLimit()` は `RateLimitExceededError` を reject で返すため、`await`（または
# `void` / `return`）が無いと例外が呼び出し元の try/catch に入らず unhandled rejection になり、
# 429 応答にならないまま **一切間引かれない**。型情報なし ESLint（`no-floating-promises` 不在）も
# `tsc --noEmit` もこれを検出しないので、本スクリプトが唯一のゲートになる。
AWAITED_CALL_RE = re.compile(r"\b(?:await|void|return)\s+(?:await\s+)?(enforce\w*RateLimit)\s*\(")
# usecase 呼び出し（`searchGemsUseCase(` 等）。間引きは「重い処理より前」で行う必要がある。
USECASE_CALL_RE = re.compile(r"\b(\w+UseCase)\s*\(")
# `export async function enforceGemListRateLimit` / `export const enforceX = ...`
EXPORT_RE = re.compile(r"^export\s+(?:async\s+)?(?:function|const)\s+(enforce\w*RateLimit)\b", re.MULTILINE)
# `'search:'` のようなコロン終わりの文字列リテラル
PREFIX_LITERAL_RE = re.compile(r"""['"]([A-Za-z0-9_.\-]+:)['"]""")

# 🔴 binding 宣言の検証用（Issue #480）。`cloudflare-bindings.ts` の `env?.RATE_LIMITER` のように
# `env` から optional chaining で読み出している識別子名を拾う。`rateLimiterBinding()` が実際に
# 参照している binding 名の唯一の一次情報源（型定義の `EnvWithRateLimiter` はコメントアウトで
# 別名を書かれても実行時の挙動には影響しないため、実際に読み出している式を見る）。
ENV_BINDING_ACCESS_RE = re.compile(r"\benv\?\.(\w+)\b")

# 🔴 ラッパー検出用（Issue #604）。`EXPORT_RE` は名前を `enforce\w*RateLimit` に絞っているため
# `prepareSearchKeyword` のような **任意の名前のラッパー export** を拾えない。ここでは名前を
# 絞らず export 宣言だけを拾い、本文が実際に `enforce*RateLimit(` を呼んでいるかは
# `extract_composition_wrappers` 側で判定する。
GENERIC_EXPORT_RE = re.compile(r"^export\s+(?:async\s+)?(?:function|const)\s+(\w+)\b", re.MULTILINE)

EXIT_OK = 0
EXIT_VIOLATION = 1


# ---------------------------------------------------------------------------
# 純粋関数（self-test はここへ文字列を直接渡す。実リポジトリのファイルは書き換えない）
# ---------------------------------------------------------------------------

def _strip_cell(cell: str) -> str:
    """表セルの前後空白と装飾（バッククォート・太字）を落とす。

    🔴 順序が重要: 太字（`**`）を先に落とさないと ``**`gems:`**`` のような
    「太字 + コード記法」のセルでバッククォートが外側に残らず、`gems:` ではなく
    ``` `gems:` ``` が値になる。すると「表は `` `gems:` `` と宣言しているが実装は `gems:` を使う」
    という **見た目が同一の値を突きつける** 無意味なエラーになる。
    """
    return cell.replace("**", "").strip().strip("`").strip()


def extract_wiring_table(markdown: str) -> tuple[list[str], str | None]:
    """マーカーで囲まれた表の行だけを返す。マーカーが無ければ (＿, エラー文) を返す。"""
    # マーカーが 2 組以上あると「最初の 1 組」しか読まれず、2 組目に列挙した経路が
    # 「表に載っていない（新経路の載せ忘れ）」と誤報される。黙って無視せず FAIL させる。
    if markdown.count(BEGIN_MARKER) > 1 or markdown.count(END_MARKER) > 1:
        return [], (
            f"{DOC_PATH.name}: {BEGIN_MARKER} / {END_MARKER} が複数組ある"
            f"（begin {markdown.count(BEGIN_MARKER)} 個 / end {markdown.count(END_MARKER)} 個）"
            " → 適用経路表は 1 ブロックに統合する（最初の 1 組しか読まれず 2 組目が誤報になる）"
        )
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


def extract_calls(source: str) -> set[str]:
    """ソース中の `enforce*RateLimit(` 呼び出し名の集合（import 文・コメントは含まない）。"""
    return set(CALL_RE.findall(strip_comments(source)))


def extract_awaited_calls(source: str) -> set[str]:
    """`await` / `void` / `return` を伴う `enforce*RateLimit(` 呼び出し名の集合。"""
    return set(AWAITED_CALL_RE.findall(strip_comments(source)))


def find_ordering_violation(
    source: str, wrapper_names: set[str] | None = None
) -> tuple[str, str] | None:
    """`enforce*RateLimit(`（または既知のラッパー呼び出し）が最初の usecase 呼び出しより
    後ろなら (呼び出し名, usecase 名) を返す。

    完全な到達性解析はしない（字句解析なしには不可能）。「同じファイルの中で、間引きが重い処理より
    **前に書かれている** こと」だけを文字オフセットで比べる。Issue #442 の事故は「呼び出しが
    usecase の後ろへ移動する / 不到達な分岐の内側へ入る」形で再発しうるが、ファイル内のどこかに
    呼び出しがあるかだけを見る検査ではそれを止められない。

    🔴 Issue #604: `wrapper_names` を渡すと、直接呼び出しに加えてラッパー呼び出し（例
    `prepareSearchKeyword(`）の位置も比較対象にする（間接呼び出しでも同じ検査を維持する）。

    🔴 usecase 呼び出しが 1 つも見つからないファイル（`app/api/search/route.ts` は
    `searchRepositoriesWithCacheStatus()` を呼ぶ等、命名が `*UseCase` でない）ではこの検査を
    **スキップする**（誤検出させない）。
    """
    stripped = strip_comments(source)
    candidates = [m for m in (CALL_RE.search(stripped),) if m]
    wrapper_re = _name_call_re(wrapper_names) if wrapper_names else None
    if wrapper_re:
        wrapper_match = wrapper_re.search(stripped)
        if wrapper_match:
            candidates.append(wrapper_match)
    usecase = USECASE_CALL_RE.search(stripped)
    if not candidates or usecase is None:
        return None
    call = min(candidates, key=lambda m: m.start())
    if call.start() < usecase.start():
        return None
    return call.group(1), usecase.group(1)


def extract_exported_enforcers(source: str) -> dict[str, str | None]:
    """`src/composition/rate-limit.ts` の export 名 → その実装が使うキー接頭辞（不明なら None）。

    🔴 本文の終端は `find_function_body_end`（対応する閉じ括弧までのブレースカウンタ）で
    厳密に決める（Issue #612 フォローアップ）。旧実装は「次の export 宣言の開始位置までの
    単純なテキストスライス」だったため、export と export の間に非 export のヘルパー関数が
    置かれていると、そのヘルパーの中身が直前の export の本文として一緒に取り込まれ、
    ヘルパー内の無関係な接頭辞リテラルを export の実装接頭辞として誤帰属していた
    （`extract_composition_wrappers` で PR #609 に修正したのと同型のバグ）。
    """
    source = strip_comments(source)
    matches = list(EXPORT_RE.finditer(source))
    result: dict[str, str | None] = {}
    for i, match in enumerate(matches):
        fallback_end = matches[i + 1].start() if i + 1 < len(matches) else len(source)
        end = find_function_body_end(source, match.start(), fallback_end)
        body = source[match.start() : end]
        literal = PREFIX_LITERAL_RE.search(body)
        result[match.group(1)] = literal.group(1) if literal else None
    return result


def _name_call_re(names: set[str]) -> re.Pattern[str] | None:
    """与えた識別子集合のいずれかへの呼び出し（`name(`）にマッチする正規表現を作る。

    `CALL_RE` / `AWAITED_CALL_RE` は `enforce\\w*RateLimit` という **名前の形** に依存しているため、
    `prepareSearchKeyword` のような任意名のラッパーには使えない。ラッパー名の集合が確定した後に
    その場で組み立てる（Issue #604）。名前が空集合なら `None`（呼び出し側は「ラッパーなし」として
    直接呼び出しの検査だけを行う）。
    """
    if not names:
        return None
    alternation = "|".join(re.escape(name) for name in sorted(names, key=len, reverse=True))
    return re.compile(rf"\b({alternation})\s*\(")


def _name_awaited_call_re(names: set[str]) -> re.Pattern[str] | None:
    """`_name_call_re` の `await` / `void` / `return` 付き版。"""
    if not names:
        return None
    alternation = "|".join(re.escape(name) for name in sorted(names, key=len, reverse=True))
    return re.compile(rf"\b(?:await|void|return)\s+(?:await\s+)?({alternation})\s*\(")


def extract_composition_wrappers(
    wrapper_sources: dict[str, str], known_enforcers: set[str]
) -> tuple[dict[str, set[str]], list[str]]:
    """`src/composition/*.ts`（`rate-limit.ts` 自身を除く）を走査し、`enforce*RateLimit(` を
    `await` 付きで呼ぶ export 関数を「ラッパー」として抽出する（Issue #604）。

    `prepareSearchKeyword()` のように、値オブジェクト変換とレート制限の順序判断をまとめて
    集約した関数がこれに当たる。呼び出し元（`app/` 側）はラッパー名だけを呼び、実体の
    `enforce*RateLimit` を直接呼ばなくなるため、これを「配線あり」と認識できないと
    誤って「配線し忘れ・死蔵」を報告してしまう。

    🔴 本文の終端は `find_function_body_end`（対応する閉じ括弧までのブレースカウンタ）で
    厳密に決める。export の **外側**（次の export 宣言より前にある非 export のトップレベル
    ヘルパー等）のコードは本文に含めない（修正項目 1・上記 docstring 参照）。

    Returns:
        wrappers: {ラッパー関数名: 転送先の `enforce*RateLimit` 名の集合}
                  （本文中で **確実に `await` されている** 場合のみ登録する）
        errors: ラッパー本文が `enforce*RateLimit(` を呼んでいるのに `await`/`void`/`return` が
                付いていない場合の違反（このラッパーは無効として `wrappers` に登録しない。
                `await` を落としたラッパーを配線済みと認めると、そのラッパーを経由するすべての
                呼び出し元で unhandled rejection が起きうる）
    """
    wrappers: dict[str, set[str]] = {}
    errors: list[str] = []
    for path, source in sorted(wrapper_sources.items()):
        stripped = strip_comments(source)
        matches = list(GENERIC_EXPORT_RE.finditer(stripped))
        for i, match in enumerate(matches):
            name = match.group(1)
            fallback_end = matches[i + 1].start() if i + 1 < len(matches) else len(stripped)
            end = find_function_body_end(stripped, match.start(), fallback_end)
            body = stripped[match.start() : end]
            called = set(CALL_RE.findall(body)) & known_enforcers
            if not called:
                continue  # enforce*RateLimit を呼んでいない export はラッパーではない
            awaited = set(AWAITED_CALL_RE.findall(body)) & known_enforcers
            missing = called - awaited
            if missing:
                errors.append(
                    f"{path}: ラッパー `{name}` が {', '.join(sorted(missing))} を呼んでいるが "
                    "`await` が付いていない（ラッパー自体が unhandled rejection を起こしうるため、"
                    "これを経由するファイルを配線済みとして認めない）"
                    " → ラッパー内部を `await enforce...RateLimit(...)` にする"
                )
                continue
            wrappers[name] = called
    return wrappers, errors


def extract_calls_via_wrappers(
    source: str, wrappers: dict[str, set[str]]
) -> tuple[set[str], set[str], set[str]]:
    """直接の `enforce*RateLimit(` 呼び出しと、既知ラッパー経由の間接呼び出しの両方を認識する。

    Returns:
        raw_matched: 実際に呼ばれている名前の集合（直接名 or ラッパー名。`await` の有無は問わない）
        raw_awaited: そのうち `await`/`void`/`return` が付いている名前の集合
        resolved: `raw_matched` をラッパー経由分も含めて実体の `enforce*RateLimit` 名へ展開した集合
                  （死蔵検証・キー接頭辞検証はこの実体名で行う）
    """
    stripped = strip_comments(source)
    direct_matched = set(CALL_RE.findall(stripped))
    direct_awaited = set(AWAITED_CALL_RE.findall(stripped))

    wrapper_names = set(wrappers)
    wrapper_call_re = _name_call_re(wrapper_names)
    wrapper_awaited_re = _name_awaited_call_re(wrapper_names)
    wrapper_matched = set(wrapper_call_re.findall(stripped)) if wrapper_call_re else set()
    wrapper_awaited = set(wrapper_awaited_re.findall(stripped)) if wrapper_awaited_re else set()

    resolved: set[str] = set(direct_matched)
    for name in wrapper_matched:
        resolved |= wrappers[name]

    return direct_matched | wrapper_matched, direct_awaited | wrapper_awaited, resolved


def check_wiring(
    doc_markdown: str,
    entrypoint_sources: dict[str, str],
    composition_source: str,
    wrapper_sources: dict[str, str] | None = None,
) -> list[str]:
    """正本表・エントリポイント実装・composition root を突き合わせて違反メッセージを返す。

    引数はすべて文字列（＝ファイル I/O から独立）なので、self-test はここを直接叩ける。
    `entrypoint_sources` のキーが「`app/` 配下に実在するエントリポイントの全集合」である。

    🔴 `wrapper_sources`（Issue #604）: `src/composition/*.ts`（`rate-limit.ts` 以外）の
    {相対パス: ソース}。`enforce*RateLimit(` を `await` 付きで呼ぶ export 関数（例
    `prepareSearchKeyword`）を「ラッパー」として抽出し、エントリポイント側のラッパー呼び出しも
    直接呼び出しと同じ 5 項目（存在・`await`・呼び出し順・逆ドリフト・接頭辞）で検査する。
    省略時は空 dict 扱い（間接呼び出しを一切認めない＝従来どおりの直接呼び出し限定の検査）。
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

    # --- 0. ラッパー抽出（Issue #604・間接呼び出しの認識）----------------------
    wrappers, wrapper_errors = extract_composition_wrappers(wrapper_sources or {}, set(exported))
    errors.extend(wrapper_errors)
    wrapper_names = set(wrappers)

    # --- 1 / 2. 表の宣言と実コードの双方向突き合わせ --------------------------
    for path, row in sorted(rows.items()):
        source = entrypoint_sources.get(path)
        if source is None:
            errors.append(
                f"{path}: 正本表に載っているが実ファイルが存在しない（`app/` 配下のエントリポイントではない）"
                " → 表から削除するか、パスの誤りを直す"
            )
            continue

        # `raw_matched` / `raw_awaited` は「呼ばれている名前」そのもの（直接名 or ラッパー名）。
        # `calls` はラッパー経由分を実体の `enforce*RateLimit` 名へ展開した集合（死蔵・接頭辞検証用）。
        raw_matched, raw_awaited, calls = extract_calls_via_wrappers(source, wrappers)
        if row["applied"] and not calls:
            errors.append(
                f"{path}: 表は「{APPLIED_MARK} 適用」だが `enforce*RateLimit(` の呼び出しが無い（配線し忘れ・"
                "既知のラッパー経由の呼び出しも見つからない）"
                " → 同ファイルで `enforce...RateLimit(...)` を呼ぶか、"
                "`src/composition/*.ts` の確実に `await` するラッパー経由で呼ぶか、表を「❌ 対象外」に直す"
            )
        elif row["applied"]:
            # --- 2. 呼び出しの結果を捨てていないか（`await` 落ち・直接/間接とも）--------
            floating = raw_matched - raw_awaited
            if floating:
                errors.append(
                    f"{path}: {', '.join(sorted(floating))} に `await` が付いていない"
                    "（`RateLimitExceededError` が try/catch の外で unhandled rejection になり、"
                    "429 を返せないまま一切間引かれない）"
                    " → `await enforce...RateLimit(...)` にする（意図的に捨てるなら `void` / `return`）"
                )
            # --- 6. 呼び出し位置（重い処理より前か・間接呼び出しでも同じ）--------------
            ordering = find_ordering_violation(source, wrapper_names)
            if ordering:
                call_name, usecase_name = ordering
                errors.append(
                    f"{path}: `{call_name}(` が usecase 呼び出し `{usecase_name}(` より後ろにある"
                    "（重い処理を走らせてから間引くので Issue #442 と同型の抜けになる）"
                    " → 間引きを usecase 呼び出しより前へ移す"
                )
        if not row["applied"] and calls:
            errors.append(
                f"{path}: 表は「{EXCLUDED_MARK} 対象外」だが {', '.join(sorted(calls))} を呼んでいる（逆ドリフト。"
                "ラッパー経由の間接呼び出しも含む）"
                " → 表を「✅ 適用」に直すか、呼び出しを外す"
            )

        if not row["applied"]:
            continue
        used_by_table |= calls

        # --- 5. キー接頭辞の一致（直接/間接とも実体の enforce*RateLimit 名で判定）------
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

    # --- 4. 死蔵（export したが表のどの ✅ 行からも使われていない・直接/間接とも）------
    for name in sorted(set(exported) - used_by_table):
        errors.append(
            f"{name}: {COMPOSITION_PATH.name} が export しているが表の「{APPLIED_MARK} 適用」行の"
            "どこからも呼ばれていない（直接呼び出しにもラッパー経由の間接呼び出しにも到達しない・死蔵）"
            " → 対象経路へ配線するか export を削除する"
        )

    return errors


# ---------------------------------------------------------------------------
# 6. binding 宣言の検証（Issue #480・純粋関数。self-test はここへ文字列を直接渡す）
# ---------------------------------------------------------------------------

def parse_wrangler_jsonc(source: str) -> tuple[dict | None, str | None]:
    """`wrangler.jsonc`（JSONC）をパースして dict を返す。

    JSONC は `//` 行コメント・`/* */` ブロックコメントを許すが素の `json.loads` は
    パースできないため、既存の `strip_comments`（TS/TSX 用だが `//` `/* */` の除去は
    JSON にもそのまま使える）でコメントを取り除いてから `json.loads` する。

    パースに失敗したら `(None, エラー文)` を返す（**fail-closed**）。「宣言が読めないので
    合格」にすると、`wrangler.jsonc` が壊れて binding 宣言ごと消えた事故を見逃す。

    🔴 【既知の制限（フォールスポジティブになりうる・自己文書化・指摘 3）】
    本関数はコメント除去後に素の `json.loads` を使うため、JSONC が一般に許容する
    **末尾カンマ**（trailing comma）を受け付けない（例: `{ "a": 1, }` は `JSONDecodeError`）。
    `wrangler.jsonc` 自体は Wrangler CLI 側の JSONC パーサ（末尾カンマ許容）で読まれるため、
    **Wrangler では正常に動く設定ファイルでも、末尾カンマがあると本検査だけが FAIL しうる**。
    倒れる向きは fail-closed（検査が赤くなるだけでガードは緩まない）なので実害は限定的で、
    現行の `wrangler.jsonc` に末尾カンマは無い。パーサの許容範囲拡張は別 Issue で扱う（本関数の
    実装はそのままにする）。
    """
    stripped = strip_comments(source)
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as exc:
        return None, (
            f"{WRANGLER_PATH.name}: JSONC のパースに失敗した（コメント除去後: {exc}）"
            " → コメント除去後も有効な JSON になっているか確認する（末尾カンマ等）"
        )
    if not isinstance(data, dict):
        return None, f"{WRANGLER_PATH.name}: トップレベルが JSON オブジェクトでない"
    return data, None


def extract_ratelimit_names(wrangler_json: dict) -> tuple[list[str], list[str]]:
    """`wrangler.jsonc` の `ratelimits[]` から `name` の一覧を返す。(names, errors)。

    🔴 対象 0 件は fail-closed（`check-tool-design-rules.md` §2）: `ratelimits` キー自体が
    無い・空配列・`name` を持つエントリが 1 件も無い、のいずれも違反として報告する
    （「宣言が 1 件も見つからない」を黙って PASS にすると、宣言まるごとの削除を見逃す）。
    """
    errors: list[str] = []
    ratelimits = wrangler_json.get("ratelimits")
    if not isinstance(ratelimits, list) or not ratelimits:
        errors.append(
            f"{WRANGLER_PATH.name}: `ratelimits` に binding 宣言が 1 件も無い"
            "（キー自体が無い、または空配列）"
            " → `{ \"name\": \"RATE_LIMITER\", ... }` を宣言する（フェイルオープン設計のため、"
            "宣言が欠けると全経路が例外にならず黙って通ってしまう）"
        )
        return [], errors

    names: list[str] = []
    for i, entry in enumerate(ratelimits):
        name = entry.get("name") if isinstance(entry, dict) else None
        if not name:
            errors.append(
                f"{WRANGLER_PATH.name}: `ratelimits[{i}]` に `name` フィールドが無い / 空"
                " → binding 名（例 `RATE_LIMITER`）を宣言する"
            )
            continue
        names.append(name)

    if not names:
        errors.append(
            f"{WRANGLER_PATH.name}: `ratelimits` はあるが `name` を持つエントリが 1 件も無い"
        )
        return [], errors

    # 6. 複数要素間の関係性の負ケース（各要素は妥当だが name が重複＝どちらを見ればよいか
    #    決まらない）。構造としては壊れていないため上のチェックだけでは通ってしまう。
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        errors.append(
            f"{WRANGLER_PATH.name}: `ratelimits[]` の `name` に重複がある（{duplicates}）"
            " → binding 名は一意にする（重複があると、どの宣言が有効な binding かが環境依存になる）"
        )

    return names, errors


def extract_binding_env_key(bindings_source: str) -> str | None:
    """`cloudflare-bindings.ts` が `env?.NAME` で読み出している binding 名を返す（無ければ None）。

    複数マッチする場合は最初の 1 件を使う（本ファイルはレート制限の binding 1 つだけを
    公開する設計。将来複数種の binding を持つ場合はこの関数の呼び出し側で明示的に絞り込む）。
    """
    match = ENV_BINDING_ACCESS_RE.search(strip_comments(bindings_source))
    return match.group(1) if match else None


def check_wrangler_binding_wiring(wrangler_source: str, bindings_source: str) -> list[str]:
    """`wrangler.jsonc` の binding 宣言と `cloudflare-bindings.ts` の参照名を突き合わせる（Issue #480）。

    引数はすべて文字列（＝ファイル I/O から独立）なので self-test はここを直接叩ける。
    """
    errors: list[str] = []

    wrangler_json, parse_error = parse_wrangler_jsonc(wrangler_source)
    if parse_error:
        return [parse_error]
    assert wrangler_json is not None  # parse_error が None ならここで必ず dict

    names, name_errors = extract_ratelimit_names(wrangler_json)
    errors.extend(name_errors)
    if not names:
        return errors

    referenced = extract_binding_env_key(bindings_source)
    if referenced is None:
        errors.append(
            f"{BINDINGS_PATH.name}: `rateLimiterBinding()` が `env?.NAME` の形で binding を"
            "参照している箇所が見つからない → 実装を確認する（本検査は実装から binding 名を"
            "読み取れないと宣言との一致を検証できない）"
        )
        return errors

    if referenced not in names:
        errors.append(
            f"{WRANGLER_PATH.name} の `ratelimits[].name`（{names}）に "
            f"{BINDINGS_PATH.name} が参照する `env.{referenced}` が含まれていない"
            "（binding 宣言の削除・リネーム・環境別 override による欠落。"
            "フェイルオープン設計のため `rateLimiterBinding()` は例外にならず黙って `undefined` "
            "を返し、レート制限が全経路で無効化される）"
            " → `wrangler.jsonc` の `ratelimits[].name` を実装の参照名と一致させる"
        )

    return errors


# ---------------------------------------------------------------------------
# 実リポジトリの読み取り
# ---------------------------------------------------------------------------

def collect_entrypoint_sources(app_dir: Path, repo_root: Path = REPO_ROOT) -> dict[str, str]:
    """`app/` 配下の **URL を生みコードが走る全ファイル** を実際に列挙して {相対パス: ソース} を返す。

    対象は `ROUTE_PRODUCING_STEMS`（`page` / `route` に加え `opengraph-image` 等のコード生成
    メタデータルート）× `ROUTE_PRODUCING_EXTENSIONS` の組み合わせ。
    🔴 「`page.tsx` / `route.ts` の 2 つ」に狭めてはいけない（モジュール docstring の
    Issue #442 再発防止の本体）。対象集合を変えるときは `ROUTE_PRODUCING_STEMS` の
    コメントと `--self-test` の列挙集合テスト（5-c）を必ず一緒に更新する。
    """
    sources: dict[str, str] = {}
    if not app_dir.is_dir():
        return sources
    for extension in ROUTE_PRODUCING_EXTENSIONS:
        for path in app_dir.rglob(f"*{extension}"):
            if path.name in ENTRYPOINT_FILE_NAMES:
                sources[path.relative_to(repo_root).as_posix()] = path.read_text(encoding="utf-8")
    return sources


def collect_composition_wrapper_sources(
    composition_dir: Path = COMPOSITION_DIR,
    exclude: Path = COMPOSITION_PATH,
    repo_root: Path = REPO_ROOT,
) -> dict[str, str]:
    """`src/composition/*.ts`（テストファイルと `exclude`＝`rate-limit.ts` 自身を除く）を
    列挙して {相対パス: ソース} を返す（Issue #604・間接呼び出しの認識対象）。

    テストファイル（`*.test.ts`）を除くのは、テストコード内のモック呼び出しをラッパーの
    実体と誤認しないため。`rate-limit.ts` 自身を除くのは、そこは `composition_source` として
    別途渡され `extract_exported_enforcers` が担当するため（含めても実害は無いが二重管理を避ける）。
    """
    sources: dict[str, str] = {}
    if not composition_dir.is_dir():
        return sources
    exclude_resolved = exclude.resolve()
    for path in sorted(composition_dir.glob("*.ts")):
        if path.name.endswith(".test.ts"):
            continue
        if path.resolve() == exclude_resolved:
            continue
        sources[path.relative_to(repo_root).as_posix()] = path.read_text(encoding="utf-8")
    return sources


def run_checks(
    doc_path: Path = DOC_PATH,
    app_dir: Path = APP_DIR,
    composition_path: Path = COMPOSITION_PATH,
    composition_dir: Path = COMPOSITION_DIR,
    wrangler_path: Path = WRANGLER_PATH,
    bindings_path: Path = BINDINGS_PATH,
) -> list[str]:
    """実ファイルを読んで検査する。読めないファイルは違反として報告する（黙って PASS にしない）。"""
    errors: list[str] = []

    try:
        wrangler_source = wrangler_path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(
            f"{wrangler_path}: wrangler.jsonc を読めない（{exc}） → ファイルの存在とパスを確認する"
        )
        wrangler_source = None

    try:
        bindings_source = bindings_path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(
            f"{bindings_path}: cloudflare-bindings.ts を読めない（{exc}） → ファイルの存在とパスを確認する"
        )
        bindings_source = None

    if wrangler_source is not None and bindings_source is not None:
        errors.extend(check_wrangler_binding_wiring(wrangler_source, bindings_source))

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
    wrapper_sources = collect_composition_wrapper_sources(composition_dir, composition_path)
    return errors + check_wiring(doc_markdown, entrypoints, composition_source, wrapper_sources)


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

# 🔴 Issue #604: 間接呼び出し（ラッパー経由）の self-test 用フィクスチャ。
# `src/composition/search-guard.ts` の `prepareSearchKeyword()` を模した、内部で確実に
# `await enforceSearchRateLimit(...)` するラッパー。
_WRAPPER_OK = {
    "src/composition/search-guard.ts": (
        "import { enforceSearchRateLimit } from './rate-limit'\n\n"
        "export async function prepareSearchKeyword(rawKeyword: string, headers: Headers) {\n"
        "  const keyword = parseKeyword(rawKeyword)\n"
        "  await enforceSearchRateLimit(headers)\n"
        "  return keyword\n"
        "}\n"
    ),
}

# 同じラッパーだが内部の `enforceSearchRateLimit(` に `await` が付いていない壊れた版。
_WRAPPER_MISSING_AWAIT = {
    "src/composition/search-guard.ts": (
        "export async function prepareSearchKeyword(rawKeyword: string, headers: Headers) {\n"
        "  const keyword = parseKeyword(rawKeyword)\n"
        "  enforceSearchRateLimit(headers)\n"  # await 抜け
        "  return keyword\n"
        "}\n"
    ),
}

# 🔴 修正項目 1 の反例フィクスチャ: export 本体は `enforce*RateLimit` を呼ばず、
# export の **外側**（次の export より前）にある非 export のヘルパーだけが呼ぶ。
# 旧実装（本文の終端 = 次の export の開始位置という単純スライス）だと、このヘルパーの
# 呼び出しが `prepareSearchKeyword` の本文へ誤って取り込まれ、実際には配線していない
# ラッパーを「配線あり」と誤認していた。
_WRAPPER_MISATTRIBUTED_HELPER_CALL = {
    "src/composition/search-guard.ts": (
        "export async function prepareSearchKeyword(rawKeyword: string, headers: Headers) {\n"
        "  const keyword = parseKeyword(rawKeyword)\n"
        "  return keyword\n"
        "}\n"
        "\n"
        "// export の外側にある非 export のヘルパー。prepareSearchKeyword の本文には含まれない。\n"
        "function debugLogRateLimitProbe(headers: Headers) {\n"
        "  void enforceSearchRateLimit(headers)\n"
        "}\n"
    ),
}

# 🔴 任務 1 の反例フィクスチャ（本 PR）: `extract_exported_enforcers` 版の同型バグ。
# `enforceSearchRateLimit` の本体には接頭辞リテラルが無く（動的生成）、その **外側**
# （次の export より前）にある非 export のヘルパーだけが `'gems:'` を持つ。
# 旧実装（本文の終端 = 次の export の開始位置という単純スライス）だと、このヘルパーの
# 中の無関係な文字列が `enforceSearchRateLimit` の実装接頭辞として誤帰属し、
# 本来 `None`（判定不能）であるべきところを `'gems:'` と誤って返していた。
_COMPOSITION_ENFORCER_MISATTRIBUTED_HELPER_LITERAL = """
export async function enforceSearchRateLimit(headers: Headers): Promise<void> {
  return await enforceRateLimitDynamic(headers, buildSearchPrefix())
}

function debugLogRateLimitProbe(headers: Headers): void {
  void enforceGemListRateLimit(headers, 'gems:')
}

export async function enforceGemListRateLimit(headers: Headers): Promise<void> {
  await enforceRateLimit(headers, 'gems:')
}
"""

# 🔴 任務 1 の反例フィクスチャ（本 PR・分割代入パラメータ）: `extract_exported_enforcers` が
# 分割代入パラメータ（`{ headers }: { headers: Headers }`）を関数本体の開始と誤認しないこと。
# 誤認すると `find_function_body_end` が分割代入パターン自身の閉じ `}` で本体抽出を打ち切り、
# 本文（呼び出し・接頭辞リテラル `'gems:'`）が丸ごと欠落する。実装は正しく `'gems:'` を
# 使っているのに「接頭辞不明」（`None`）と誤判定される偽陰性を再現する。
_COMPOSITION_DESTRUCTURED_PARAM = """
export async function enforceGemListRateLimit({ headers }: { headers: Headers }): Promise<void> {
  await enforceRateLimit(headers, 'gems:')
}
"""

# 🔴 任務 1 の反例フィクスチャ（本 PR・分割代入パラメータ）: `extract_composition_wrappers` が
# 分割代入パラメータを持つラッパー関数を未認識にしないこと。誤認すると本文が丸ごと欠落し、
# 内部の `await enforceSearchRateLimit(...)` を見つけられず、正しく配線されたラッパーが
# 「未配線・死蔵」の偽陽性として誤って CI を赤くする（`_WRAPPER_MISATTRIBUTED_HELPER_CALL`
# の同型バグ・`extract_exported_enforcers` 側の版）。
_WRAPPER_DESTRUCTURED_PARAM = {
    "src/composition/search-guard.ts": (
        "export async function prepareSearchKeyword("
        "{ rawKeyword, headers }: { rawKeyword: string; headers: Headers }"
        ") {\n"
        "  const keyword = parseKeyword(rawKeyword)\n"
        "  await enforceSearchRateLimit(headers)\n"
        "  return keyword\n"
        "}\n"
    ),
}


# --- Issue #480: binding 宣言検証用フィクスチャ -----------------------------

_WRANGLER_OK = """
{
  // 行末コメント
  "$schema": "./node_modules/wrangler/config-schema.json",
  "name": "gem-hunter",
  /* ブロックコメント
     複数行 */
  "ratelimits": [
    { "name": "RATE_LIMITER", "namespace_id": "1001", "simple": { "limit": 60, "period": 60 } }
  ]
}
"""

_BINDINGS_OK = """
type EnvWithRateLimiter = {
  RATE_LIMITER?: RateLimiterBinding
}

export async function rateLimiterBinding(): Promise<RateLimiterBinding | undefined> {
  try {
    const env = context?.env as EnvWithRateLimiter | undefined
    return env?.RATE_LIMITER
  } catch {
    return undefined
  }
}
"""


def self_test() -> int:
    failures: list[str] = []
    # 🔴 表示件数は実測から出す（手書きの内訳は数え直すたびにズレる・Issue #999 と同型の再発防止）。
    # `expect_ok` / `expect_fail` の呼び出し回数そのものをカウンタで積み上げ、末尾の PASS 出力は
    # このカウンタだけを見て組み立てる（手書きの合計・内訳を一切残さない）。
    ok_count = 0
    fail_count = 0

    def expect_ok(label: str, errors: list[str]) -> None:
        nonlocal ok_count
        ok_count += 1
        if errors:
            failures.append(f"{label}: 違反ゼロを期待したが {errors}")

    def expect_fail(label: str, errors: list[str], keyword: str) -> None:
        nonlocal fail_count
        fail_count += 1
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

    # 14-b) 🔴 正規表現リテラル（`/'/g`）の後ろでコメント除去が止まらない（修正項目 1 の再現入力）。
    #       ソース全体を 1 本のクォート状態で舐めていた頃は、`'` を文字列の開始と誤解して
    #       以降の `//` を除去できず、コメントアウトされた呼び出しを「配線済み」と誤認していた。
    regex_literal = dict(_SOURCES_OK)
    regex_literal["app/[locale]/gems/page.tsx"] = (
        "const slug = raw.replace(/'/g, '')\n"
        "// await enforceGemListRateLimit(await headers())\n"
    )
    expect_fail(
        "正規表現リテラル後のコメントアウト",
        check_wiring(_DOC_OK, regex_literal, _COMPOSITION_OK),
        "配線し忘れ",
    )

    # 14-c) 🔴 対にならないアポストロフィ（JSX の `Don't`）でも同じ（修正項目 1 の再現入力）。
    apostrophe = dict(_SOURCES_OK)
    apostrophe["app/[locale]/gems/page.tsx"] = (
        "export default function Page() {\n"
        "  return <p>Don't worry</p>\n"
        "}\n"
        "// await enforceGemListRateLimit(await headers())\n"
    )
    expect_fail(
        "アポストロフィ後のコメントアウト",
        check_wiring(_DOC_OK, apostrophe, _COMPOSITION_OK),
        "配線し忘れ",
    )

    # 14-d) 上記の安全側倒しが、正常な複数行テンプレートリテラルを壊していないこと
    template_literal = dict(_SOURCES_OK)
    template_literal["app/[locale]/gems/page.tsx"] = (
        "const q = `line1\n"
        "line2 // not a comment`\n"
        "await enforceGemListRateLimit(await headers())\n"
    )
    expect_ok("複数行テンプレートリテラル", check_wiring(_DOC_OK, template_literal, _COMPOSITION_OK))

    # 17) 🟡 `await` 落ち（修正項目 2）。呼び出しはあるが結果を捨てているので
    #     `RateLimitExceededError` が unhandled rejection になり一切間引かれない。
    #     ESLint（型情報なし）も `tsc --noEmit` も検出しないため、ここが唯一のゲート。
    floating = dict(_SOURCES_OK)
    floating["app/[locale]/gems/page.tsx"] = "enforceGemListRateLimit(await headers())\n"
    expect_fail("await 落ち", check_wiring(_DOC_OK, floating, _COMPOSITION_OK), "`await` が付いていない")

    # 17-b) 意図的に捨てる `void` / 呼び出し元へ返す `return` は配線とみなす
    void_call = dict(_SOURCES_OK)
    void_call["app/[locale]/gems/page.tsx"] = "void enforceGemListRateLimit(await headers())\n"
    expect_ok("void 呼び出し", check_wiring(_DOC_OK, void_call, _COMPOSITION_OK))
    return_call = dict(_SOURCES_OK)
    return_call["app/[locale]/gems/page.tsx"] = "return enforceGemListRateLimit(await headers())\n"
    expect_ok("return 呼び出し", check_wiring(_DOC_OK, return_call, _COMPOSITION_OK))

    # 18) 🟡 太字 + コード記法のセル（修正項目 3）。`_strip_cell` の順序が逆だと
    #     バッククォートが残り「表は `` `gems:` `` だが実装は `gems:`」という
    #     見た目が同一の値を突きつける無意味な FAIL になる。
    doc_decorated = _DOC_OK.replace("| `gems:` |", "| **`gems:`** |").replace(
        "| `app/[locale]/gems/page.tsx` |", "| **`app/[locale]/gems/page.tsx`** |"
    )
    expect_ok("太字 + コード記法のセル", check_wiring(doc_decorated, dict(_SOURCES_OK), _COMPOSITION_OK))

    # 19) 🟡 マーカーが 2 組ある（修正項目 4）。最初の 1 組しか読まれず、2 組目に列挙した
    #     経路が「表に載っていない」と誤報される。黙って無視せず専用エラーにする。
    doc_two_blocks = _DOC_OK + f"\n{BEGIN_MARKER}\n| 追加 | `app/api/x/route.ts` | ❌ 対象外 | — |\n{END_MARKER}\n"
    expect_fail(
        "マーカーが複数組",
        check_wiring(doc_two_blocks, dict(_SOURCES_OK), _COMPOSITION_OK),
        "1 ブロックに統合",
    )

    # 20) 🟡 呼び出し位置が usecase より後ろ（修正項目 6）。重い処理を走らせてから間引くので
    #     Issue #442 と同型の抜けになる。存在チェックだけでは緑のままになる。
    late_call = dict(_SOURCES_OK)
    late_call["app/[locale]/gems/page.tsx"] = (
        "const result = await searchGemsUseCase()({ page })\n"
        "await enforceGemListRateLimit(await headers())\n"
    )
    expect_fail("usecase より後ろの呼び出し", check_wiring(_DOC_OK, late_call, _COMPOSITION_OK), "より後ろにある")

    # 20-b) usecase 呼び出しより前なら通る（正常な並び）
    early_call = dict(_SOURCES_OK)
    early_call["app/[locale]/gems/page.tsx"] = (
        "await enforceGemListRateLimit(await headers())\n"
        "const result = await searchGemsUseCase()({ page })\n"
    )
    expect_ok("usecase より前の呼び出し", check_wiring(_DOC_OK, early_call, _COMPOSITION_OK))

    # 20-c) 🔴 usecase 呼び出しが 1 つも無いファイル（`app/api/search/route.ts` の
    #       `searchRepositoriesWithCacheStatus()` のように命名が `*UseCase` でない）では
    #       位置検査をスキップする（誤検出させない）
    no_usecase = dict(_SOURCES_OK)
    no_usecase["app/[locale]/gems/page.tsx"] = (
        "const { search } = searchRepositoriesWithCacheStatus(token)\n"
        "await enforceGemListRateLimit(await headers())\n"
        "const result = await search({ keyword })\n"
    )
    expect_ok("usecase 呼び出しが無いファイル", check_wiring(_DOC_OK, no_usecase, _COMPOSITION_OK))

    # 21) ⚪ `.js` / `.jsx` / `.mjs` も App Router のルート特殊ファイルとして受け付ける（修正項目 5）
    for required_js in ("page.js", "route.js", "page.jsx", "sitemap.mjs"):
        if required_js not in ENTRYPOINT_FILE_NAMES:
            failures.append(f"列挙対象に {required_js} が含まれていない（拡張子の軸に穴がある）")

    # --- Issue #604: 間接呼び出し（ラッパー経由）の検査 ---------------------------

    # 22) 🔴 間接呼び出しを「配線あり」と認識できること（今回の事故そのものの再現・最重要）。
    #     `app/[locale]/page.tsx` は `enforceSearchRateLimit(` を直接呼ばず、
    #     `prepareSearchKeyword()`（`src/composition/search-guard.ts`）経由で呼ぶ。
    indirect_ok = dict(_SOURCES_OK)
    indirect_ok["app/[locale]/page.tsx"] = (
        "import { prepareSearchKeyword } from '@/src/composition/search-guard'\n"
        "const keyword = await prepareSearchKeyword(rawKeyword, await headers())\n"
    )
    expect_ok(
        "間接呼び出し（ラッパー経由）を配線ありと認識",
        check_wiring(_DOC_OK, indirect_ok, _COMPOSITION_OK, _WRAPPER_OK),
    )

    # 23) 🔴 ラッパー内部で `await` が抜けていたら落ちること。ラッパー自体が unhandled
    #     rejection を起こしうるため、これを経由するファイルを配線済みとして認めてはいけない。
    expect_fail(
        "ラッパー内部の await 抜け",
        check_wiring(_DOC_OK, indirect_ok, _COMPOSITION_OK, _WRAPPER_MISSING_AWAIT),
        "ラッパー",
    )

    # 24) 🔴 `❌ 対象外` のファイルが間接呼び出し（ラッパー経由）をしていたら落ちること（逆ドリフト）。
    indirect_stray = dict(_SOURCES_OK)
    indirect_stray["app/api/auth/logout/route.ts"] = (
        "import { prepareSearchKeyword } from '@/src/composition/search-guard'\n"
        "await prepareSearchKeyword(rawKeyword, request.headers)\n"
    )
    expect_fail(
        "❌ 対象外なのに間接呼び出し",
        check_wiring(_DOC_OK, indirect_stray, _COMPOSITION_OK, _WRAPPER_OK),
        "逆ドリフト",
    )

    # 25) 🟡 呼び出し側（エントリポイント）がラッパーを `await` せずに呼んでいたら落ちること
    #     （ラッパー自体は正常でも、呼び出し側で結果を捨てると unhandled rejection になる）。
    indirect_floating = dict(_SOURCES_OK)
    indirect_floating["app/[locale]/page.tsx"] = (
        "import { prepareSearchKeyword } from '@/src/composition/search-guard'\n"
        "prepareSearchKeyword(rawKeyword, headers)\n"  # await 抜け
    )
    expect_fail(
        "呼び出し側でラッパーに await が付いていない",
        check_wiring(_DOC_OK, indirect_floating, _COMPOSITION_OK, _WRAPPER_OK),
        "`await` が付いていない",
    )

    # 26) 🟡 間接呼び出しでも usecase 呼び出しより後ろなら落ちること（呼び出し順の検査が
    #     ラッパー経由でも維持されていること）。
    indirect_late = dict(_SOURCES_OK)
    indirect_late["app/[locale]/page.tsx"] = (
        "import { prepareSearchKeyword } from '@/src/composition/search-guard'\n"
        "const result = await searchRepositoriesUseCase()({ page })\n"
        "const keyword = await prepareSearchKeyword(rawKeyword, await headers())\n"
    )
    expect_fail(
        "間接呼び出しが usecase より後ろ",
        check_wiring(_DOC_OK, indirect_late, _COMPOSITION_OK, _WRAPPER_OK),
        "より後ろにある",
    )

    # 27) 🔴 間接呼び出しでも接頭辞の食い違いを検出できること（死蔵・接頭辞検証がラッパー
    #     経由の実体名まで正しく展開されていることの確認）。
    doc_indirect_swapped = _DOC_OK.replace(
        "| 検索画面 | `app/[locale]/page.tsx` | ✅ 適用 | `search:` |",
        "| 検索画面 | `app/[locale]/page.tsx` | ✅ 適用 | `gems:` |",
    )
    expect_fail(
        "間接呼び出しの接頭辞食い違い",
        check_wiring(doc_indirect_swapped, indirect_ok, _COMPOSITION_OK, _WRAPPER_OK),
        "実装は `search:` を使う",
    )

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

    # 🔴 任務 1（本 PR）の反例: export 外側の非 export ヘルパー内の文字列を、
    # 直前の export（`enforceSearchRateLimit`）の実装接頭辞として誤帰属しないこと。
    # 本来 `enforceSearchRateLimit` は接頭辞不明（動的生成）なので `None` であるべき。
    misattributed = extract_exported_enforcers(_COMPOSITION_ENFORCER_MISATTRIBUTED_HELPER_LITERAL)
    if misattributed.get("enforceSearchRateLimit") is not None:
        failures.append(
            "extract_exported_enforcers: export 外側のヘルパー内の文字列を export 本体の"
            f"接頭辞として誤帰属している（期待 None、実際 {misattributed.get('enforceSearchRateLimit')!r}）"
        )
    if misattributed.get("enforceGemListRateLimit") != "gems:":
        failures.append(
            "extract_exported_enforcers: 反例フィクスチャで自身の接頭辞まで壊れている"
            f"（{misattributed!r}）"
        )

    # 🔴 任務 1（本 PR）の反例: 分割代入パラメータを持つ export の本体が丸ごと欠落しないこと。
    destructured = extract_exported_enforcers(_COMPOSITION_DESTRUCTURED_PARAM)
    if destructured.get("enforceGemListRateLimit") != "gems:":
        failures.append(
            "extract_exported_enforcers: 分割代入パラメータを持つ export の本体が正しく抽出できて"
            f"いない（期待 'gems:'、実際 {destructured.get('enforceGemListRateLimit')!r}）"
        )

    # Issue #604: ラッパー抽出・間接呼び出し解決の補助関数の単体検証
    known = {"enforceSearchRateLimit", "enforceGemListRateLimit"}
    wrappers_ok, wrapper_errs_ok = extract_composition_wrappers(_WRAPPER_OK, known)
    if wrappers_ok != {"prepareSearchKeyword": {"enforceSearchRateLimit"}} or wrapper_errs_ok:
        failures.append(
            f"extract_composition_wrappers: 正常なラッパーを抽出できていない（{wrappers_ok!r} / {wrapper_errs_ok!r}）"
        )
    wrappers_bad, wrapper_errs_bad = extract_composition_wrappers(_WRAPPER_MISSING_AWAIT, known)
    if wrappers_bad or not wrapper_errs_bad:
        failures.append(
            "extract_composition_wrappers: await 抜けのラッパーを無効化できていない"
            f"（wrappers={wrappers_bad!r} / errors={wrapper_errs_bad!r}）"
        )

    # 🔴 修正項目 1（CRITICAL）の反例: export の外側にあるヘルパーの呼び出しを、
    # 直前の export の本文として誤帰属しないこと（偽陰性の再発防止）。
    wrappers_helper, wrapper_errs_helper = extract_composition_wrappers(
        _WRAPPER_MISATTRIBUTED_HELPER_CALL, known
    )
    if "prepareSearchKeyword" in wrappers_helper or wrapper_errs_helper:
        failures.append(
            "extract_composition_wrappers: export 外側のヘルパー呼び出しを export 本体へ誤帰属している"
            f"（wrappers={wrappers_helper!r} / errors={wrapper_errs_helper!r}）"
        )

    # 🔴 任務 1（本 PR）の反例: 分割代入パラメータを持つラッパーが未認識にならないこと。
    wrappers_destructured, wrapper_errs_destructured = extract_composition_wrappers(
        _WRAPPER_DESTRUCTURED_PARAM, known
    )
    if (
        wrappers_destructured != {"prepareSearchKeyword": {"enforceSearchRateLimit"}}
        or wrapper_errs_destructured
    ):
        failures.append(
            "extract_composition_wrappers: 分割代入パラメータを持つラッパーが未認識になっている"
            f"（wrappers={wrappers_destructured!r} / errors={wrapper_errs_destructured!r}）"
        )

    raw_matched, raw_awaited, resolved = extract_calls_via_wrappers(
        "await prepareSearchKeyword(k, h)\n", {"prepareSearchKeyword": {"enforceSearchRateLimit"}}
    )
    if raw_matched != {"prepareSearchKeyword"} or raw_awaited != {"prepareSearchKeyword"} or resolved != {
        "enforceSearchRateLimit"
    }:
        failures.append(
            "extract_calls_via_wrappers: ラッパー経由の呼び出しを実体名へ展開できていない"
            f"（raw_matched={raw_matched!r} / raw_awaited={raw_awaited!r} / resolved={resolved!r}）"
        )

    # --- Issue #480: binding 宣言の検証（6 番目の検査）----------------------------

    # 28) 正常構成: コメント入り JSONC も素通りする
    expect_ok(
        "binding 宣言: 正常構成",
        check_wrangler_binding_wiring(_WRANGLER_OK, _BINDINGS_OK),
    )

    # 29) 🔴 `ratelimits` キー自体が無い（宣言ブロックごと削除）→ fail-closed
    wrangler_no_key = _WRANGLER_OK.replace(
        '"ratelimits": [\n    { "name": "RATE_LIMITER", "namespace_id": "1001",'
        ' "simple": { "limit": 60, "period": 60 } }\n  ]',
        '"dummy": true',
    )
    expect_fail(
        "binding 宣言: ratelimits キーが無い",
        check_wrangler_binding_wiring(wrangler_no_key, _BINDINGS_OK),
        "1 件も無い",
    )

    # 30) 🔴 `ratelimits` が空配列 → 対象 0 件は fail-closed
    wrangler_empty = _WRANGLER_OK.replace(
        '[\n    { "name": "RATE_LIMITER", "namespace_id": "1001",'
        ' "simple": { "limit": 60, "period": 60 } }\n  ]',
        "[]",
    )
    expect_fail(
        "binding 宣言: ratelimits が空配列",
        check_wrangler_binding_wiring(wrangler_empty, _BINDINGS_OK),
        "1 件も無い",
    )

    # 31) 🔴 `name` キーが欠落したエントリだけ → 「宣言はあるが読み取れる名前が無い」も fail-closed
    wrangler_no_name = _WRANGLER_OK.replace(
        '{ "name": "RATE_LIMITER", "namespace_id": "1001", "simple": { "limit": 60, "period": 60 } }',
        '{ "namespace_id": "1001", "simple": { "limit": 60, "period": 60 } }',
    )
    expect_fail(
        "binding 宣言: name フィールド欠落",
        check_wrangler_binding_wiring(wrangler_no_name, _BINDINGS_OK),
        "フィールドが無い",
    )

    # 32) 名前が別値（リネーム・環境別 override による欠落を再現）。
    #     宣言側 `RATE_LIMITER_V2` / 実装参照 `RATE_LIMITER`（Issue #750 型の反例・前半）。
    wrangler_renamed = _WRANGLER_OK.replace('"name": "RATE_LIMITER"', '"name": "RATE_LIMITER_V2"')
    expect_fail(
        "binding 宣言: 実装が参照する名前が含まれていない",
        check_wrangler_binding_wiring(wrangler_renamed, _BINDINGS_OK),
        "含まれていない",
    )

    # 32-b) 🔴 32) の逆方向（Issue #750 型の反例・後半・指摘 2）: 宣言側は変えず `RATE_LIMITER`
    #       のまま、実装参照だけが拡張された別名 `RATE_LIMITER_V2` を指す。
    #       突合を `declared.startswith(referenced)` へ緩めると 32) は拾えるが本ケースは拾えず、
    #       逆に `referenced.startswith(declared)` へ緩めると本ケースは拾えるが 32) は拾えない
    #       ——前方一致への退行は向きによって片方の反例だけでは検知できないため、両方向を固定する。
    bindings_v2_ref = _BINDINGS_OK.replace("env?.RATE_LIMITER", "env?.RATE_LIMITER_V2")
    expect_fail(
        "binding 宣言: 実装参照が拡張された別名（前方一致への退行検知・32 の逆方向）",
        check_wrangler_binding_wiring(_WRANGLER_OK, bindings_v2_ref),
        "含まれていない",
    )

    # 33) 🔴 複数要素間の関係性の負ケース（#896）: 各エントリ単体は妥当（name あり）だが、
    #     同じ名前が重複している（構造は壊れていないため 29〜31 のチェックだけでは通ってしまう）。
    wrangler_dup = _WRANGLER_OK.replace(
        '{ "name": "RATE_LIMITER", "namespace_id": "1001", "simple": { "limit": 60, "period": 60 } }',
        '{ "name": "RATE_LIMITER", "namespace_id": "1001", "simple": { "limit": 60, "period": 60 } },\n'
        '    { "name": "RATE_LIMITER", "namespace_id": "1002", "simple": { "limit": 30, "period": 60 } }',
    )
    expect_fail(
        "binding 宣言: name の重複",
        check_wrangler_binding_wiring(wrangler_dup, _BINDINGS_OK),
        "重複",
    )

    # 34) 実装側に `env?.NAME` の参照が見つからない（読み取り不能・fail-closed）
    bindings_no_ref = _BINDINGS_OK.replace("return env?.RATE_LIMITER", "return undefined")
    expect_fail(
        "binding 宣言: 実装側の参照が見つからない",
        check_wrangler_binding_wiring(_WRANGLER_OK, bindings_no_ref),
        "見つからない",
    )

    # 35) 🔴 JSONC のパースに失敗する（末尾カンマ等の壊れた JSON）→ fail-closed（黙って PASS にしない）
    wrangler_broken = _WRANGLER_OK.replace('"name": "gem-hunter",', '"name": "gem-hunter",,')
    expect_fail(
        "binding 宣言: JSONC パース失敗",
        check_wrangler_binding_wiring(wrangler_broken, _BINDINGS_OK),
        "パースに失敗",
    )

    # 36) コメントが行末・ブロック・複数バリアントに散らばっていても正しくパースできる
    #     （入力バリアントの展開）。文字列値の中に "//" を含むケースも壊さないこと。
    wrangler_comment_variants = """
{
  "name": "gem-hunter", // 行末コメント
  "homepage": "https://example.com/path//with//slashes", // URL 文字列を巻き込まない
  /* 複数行の
     ブロックコメント */
  "ratelimits": [
    { "name": "RATE_LIMITER", "namespace_id": "1001", "simple": { "limit": 60, "period": 60 } }
  ]
}
"""
    expect_ok(
        "binding 宣言: コメントバリアント（行末・ブロック・URL 文字列内の //）",
        check_wrangler_binding_wiring(wrangler_comment_variants, _BINDINGS_OK),
    )

    # 37) 補助関数の単体検証: parse_wrangler_jsonc / extract_ratelimit_names / extract_binding_env_key
    parsed, parse_err = parse_wrangler_jsonc(_WRANGLER_OK)
    if parse_err or parsed is None or parsed.get("name") != "gem-hunter":
        failures.append(f"parse_wrangler_jsonc: 正常な JSONC をパースできていない（{parse_err!r}）")
    names_ok, name_errors_ok = extract_ratelimit_names(parsed or {})
    if names_ok != ["RATE_LIMITER"] or name_errors_ok:
        failures.append(
            f"extract_ratelimit_names: 正常構成から名前を取り出せていない（{names_ok!r} / {name_errors_ok!r}）"
        )
    if extract_binding_env_key(_BINDINGS_OK) != "RATE_LIMITER":
        failures.append("extract_binding_env_key: env?.RATE_LIMITER を抽出できていない")
    if extract_binding_env_key("return undefined") is not None:
        failures.append("extract_binding_env_key: 参照が無いのに何かを返している")

    if failures:
        for label in failures:
            print(f"[rate-limit-wiring] SELF-TEST FAIL: {label}", file=sys.stderr)
        print(f"[rate-limit-wiring] self-test NG（{len(failures)} 件）", file=sys.stderr)
        return EXIT_VIOLATION
    print(
        f"[rate-limit-wiring] self-test OK（{ok_count + fail_count} ケース: "
        f"正常 {ok_count} / 反例 {fail_count}。ほかに補助関数・列挙集合の単体検証あり）"
    )
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
