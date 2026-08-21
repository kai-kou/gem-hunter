# ADR 0005: Cache Port を YAGNI の意図的な例外として維持し、TTL 暫定値を確定する

- **状態**: **承認**
- **日付**: 2026-08-19 JST
- **対応要件**: `NFR-5` / `NFR-17` / `NFR-18` / `E-3` / `R-5` / `D-5` / `D-18` / `D-24` / `ARCH-2` / `ARCH-3` / `ARCH-4`
- **関連**: [Cloudflare インフラ設計](../03_design/infrastructure/cloudflare-infrastructure.md) §4 / [ユーザーストーリーマップ](../02_requirements/user-story-map.md) §5.3 `SP-5` / [議論記録](../../content/discussions/sp5-cache-design-20260819/whiteboard.md)（round 3・lead 判定・争点 C・D）

---

## 1. 文脈

`SP-5`（`user-story-map.md` §5.3）のゴールは「同じキーワードで 2 回続けて検索したとき、2 回目は GitHub API を呼ばない」ことを、レスポンスヘッダ `X-Cache-Status: HIT` で外から検証できる状態にすることである。

既存資産として `src/domain/ports/cache-port.ts` に `CachePort`（`get` / `set` / `invalidate` + `ttlSeconds`）が、`src/infrastructure/platform/cache.ts` に `InMemoryCache`（isolate 内メモリのみ・composition root 未配線）が既にあったが、キャッシュ参照をどの層に差し込むか、`InMemoryCache` をどう生存させるか、TTL をいくつにするかは未確定だった。専門チーム（`clean_arch` / `verify_test` / `runtime_edge` の 3 レンズ・3 ラウンドの敵対的相互検証）で争点 C（差し込み層）・争点 D（TTL）を検証した結果を以下に記録する。

---

## 2. 決定

### 2.1. Cache Port は維持する（YAGNI の意図的な例外）

`CachePort`（`get` / `set` / `invalidate` + TTL）を撤廃せず維持する。実装は `src/infrastructure/platform/cache.ts` の `InMemoryCache` を使い、**composition root（`src/composition/container.ts`）のモジュールスコープで 1 インスタンスだけ生成し、全リクエストで共有する singleton** にする（関数内で毎回 `new` すると、isolate の生存期間以前にリクエストごとに空の `Map` となり常に `MISS` になるため）。

キャッシュ参照は **`CachingRepositoryQuery`**（`RepositoryQueryPort` を実装するデコレータ・`src/infrastructure/platform/cached-repository-query.ts` に新設）を composition root で合成する形で差し込む。`src/usecases/*` は無改修とし、`CachePort` / `RepositoryQueryPort` のポート面積も広げない。HIT / MISS の呼び出し元への伝達は、デコレータのコンストラクタ引数 `onCacheStatus?: (status: "HIT" | "MISS") => void` コールバックで行う。404（`null`）はキャッシュしない。`invalidate` は本スプリントでは呼び出し箇所を作らない。

### 2.2. TTL 暫定値

| 対象 | TTL | 定数名 |
|---|---|---|
| 検索結果 | 60 秒 | `TTL_SEARCH_SECONDS`（`src/composition/container.ts`） |
| リポジトリ詳細 | 300 秒 | `TTL_DETAIL_SECONDS`（`src/composition/container.ts`） |

### 2.3. 観測経路の決定（`X-Cache-Status` をどこに付与するか）

`SP-5` の受け入れ条件「2 回目は GitHub API を呼んでいないことを外から検証できる」を満たすヘッダ `X-Cache-Status: HIT` / `MISS` の付与位置を、**`GET /api/search`（Route Handler）の応答** に決定する。画面（`app/[locale]/page.tsx` の Server Component が返す SSR 応答）には付与しない。

1. **SSR 応答への付与を試みて不成立だった**: 当初案は画面の SSR 応答へ直接 `X-Cache-Status` を動的付与する経路だった。Server Component は Web 標準の `Response` を経由せずレンダリングされるため、`wrangler` の `main` を自前エントリへ差し替え `node:async_hooks` の `AsyncLocalStorage` で HIT/MISS を Worker の外側（エントリ層）へ運ぶ方式を実装し、`wrangler dev --local` + スタブ GitHub API で実機検証したが、OpenNext 生成物が挟む非同期継続を `AsyncLocalStorage` の store が越えられず、composition root のコールバックが呼ばれる時点で `getStore()` が常に `undefined` だった（デバッグログで実測確認済み。原因は workerd の `nodejs_compat` 実装が Next.js 内部の継続を計装できていない可能性が高いが未確定）。一方でキャッシュ本体（L2 `CachePort`）自体は実機で正しく動作しており、壊れていたのは観測手段のみだった。
2. **採用した Route Handler 方式**: `app/api/search/route.ts`（新設）を検索の実処理経路とし、`NextResponse` に `headers.set('X-Cache-Status', ...)` で HIT/MISS を付与する。Route Handler は Web 標準 `Response` / `NextResponse` を直接返すため動的ヘッダ付与に制約がない。
3. **却下した案（UI を client fetch に作り替える案）**: 画面（`SearchForm` → `/${locale}` への GET → ページ全体の SSR）自体を「クライアントから `/api/search` を fetch し結果を描画する」構成へ作り替え、画面の応答にもヘッダ相当の情報を反映させる案は、`SP-5` のスコープ（同じ検索で GitHub API を二度叩かないことの検証手段の確保）を超えて UI アーキテクチャ全体を変更するスコープ侵食のため却下する。既存の Server Component 経由の検索フローはそのまま維持し、`X-Cache-Status` の確認は `/api/search` を直接叩く（または DevTools の Network タブで検索リクエストを選ぶ）経路に限定する。

詳細な検証過程は議論記録 [`content/discussions/sp5-cache-design-20260819/whiteboard.md`](../../content/discussions/sp5-cache-design-20260819/whiteboard.md) を参照。

---

## 3. 理由

### 3.1. なぜ Cache Port を YAGNI の例外として許すか

1 箇所しか使わない抽象化レイヤーを先回りで追加しないのが原則（`CLAUDE.md`「やってはいけないこと」）だが、`NFR-17` は「MVP は Next.js のキャッシュ機構相当を実装として使い、外部キャッシュへ差し替え可能にする」ことを **`D-5` の意図的な YAGNI 例外** として明記している。`D-5`（データアーキテクチャ）は「インフラ（キャッシュ基盤・デプロイ先）は現時点で決定しない。ただし外部キャッシュを後から差し込めることを設計制約とする」と決めており、キャッシュ抽象そのものを外すと `D-5` の設計制約が満たせなくなる。

例外を認める代わりに **歯止め** を 2 つ課す。

1. ポート面積を `get` / `set` / `invalidate` + TTL のみに限定し、汎用キャッシュライブラリを自作しない（`NFR-17` のとおり）
2. HIT/MISS の伝達を `CachePort.get` の戻り値やドメイン型の拡張ではなく、インフラ層内で完結するコールバックに閉じる（§4 の却下案を参照）

### 3.2. なぜ `CachingRepositoryQuery` デコレータで差し込むか

ユースケース（`src/usecases/search-repositories.ts` / `get-repository-detail.ts`）に `CachePort` を直接引数注入する案は、呼び出し元が増えるたびに配線が重複し、キャッシュキー生成（`NFR-18`）の責務がユースケース側に漏れる。`RepositoryQueryPort` を実装するデコレータとして `CachingRepositoryQuery` を composition root で合成すれば、ユースケースは `RepositoryQueryPort` を受け取るだけで済み（`ARCH-2` を維持）、`src/infrastructure/` の中だけでキャッシュの有無を切り替えられる（`ARCH-3` / `ARCH-4` を維持）。

### 3.3. TTL 暫定値の根拠

- **検索結果 60 秒**: `NFR-5` は検索結果と詳細で別 TTL を求めている。検索結果は利用者が条件を変えて何度も打ち直す性質があり、新着リポジトリの反映速度への期待も相対的に高いため、短い TTL を割り当てる
- **詳細 300 秒**: リポジトリ詳細（star 数・説明文・topics 等）は検索結果に比べて更新頻度が低く、体感される鮮度要求も緩いため、長い TTL を割り当ててヒット率を優先する
- 両値とも `R-5`（1 検索あたりの API 呼び出し数 × 想定利用者数からレート枠を逆算する未決事項）が未確定な段階の **暫定値** であり、テストの安定性には影響しない（結合テストはフェイク時計を使い、E2E は TTL 内で完結する連続実行のため）

### 3.4. 再決定条件

`R-5`（必要レート枠の逆算）が確定した時点で、この暫定値を実測ベースの値に見直す。見直しは本 ADR の追補、または新規 ADR で記録する。

#### 追補（2026-08-20・`R-5` 実施）

`M-4`（公開判断ゲート）の通過判定として `R-5` を実施した。**逆算の結果、暫定値のままで必要枠を満たす** ため **検索 60 秒 / 詳細 300 秒を確定値とする**。逆算の前提・計算・残余リスクは[パブリック化レビュー](../05_release/repository-publication-review.md) §7 が正本であり、ここには複製しない。

🔴 **次に見直す条件**: 同時実利用者が 20 名規模に達したことを実測で確認したとき、または `InMemoryCache`（isolate 内メモリ）より広い共有キャッシュ（L3）を導入したとき（[Cloudflare インフラ設計](../03_design/infrastructure/cloudflare-infrastructure.md) §4.4 の判定条件）。

#### 追補（2026-08-21・`SP-16` 実施）

`SP-16`（Gem Index 順ソート）は `sort=gem-index` の経路だけ、1 検索あたり最大 10 リクエスト（`per_page=100 × 最大 10 ページ`・飼い主決定）になる。§3.3 が「1 検索 = 1 API 呼び出し」を前提に逆算した検索 TTL 60 秒の計算根拠が、この経路に限っては成り立たなくなる。

**本 ADR の対応**: `sort=gem-index` の経路も既存の `TTL_SEARCH_SECONDS`（60 秒）をそのまま使う。キャッシュキーは既存の `searchResultCacheKey`（`page` / `sort` / `per_page` を含む）を変更せずに使うため、10 回のループのうち再訪問分は透過的にキャッシュヒットする（`sp16-gem-index-sort-20260821` 議論記録 決定 `D-F`）。**TTL の数値は変更しない**。

🔴 **再逆算は本スプリントのスコープ外**（`sort=gem-index` の経路だけ 1 検索あたりの API 呼び出し数が最大 10 倍になったことを踏まえた `R-5` 相当の逆算のやり直しは、別 Issue で追う）。

---

## 4. 却下した選択肢

| 選択肢 | 却下理由 |
|---|---|
| **ユースケースに `CachePort` を直接引数注入する案** | 呼び出し元（`search-repositories.ts` / `get-repository-detail.ts`）が増えるたびに配線が重複し、キャッシュキー生成の責務がユースケースへ漏れる（§3.2） |
| **`CachePort.get` の戻り値を `{ value, status }` に広げる案** | `NFR-17` が定めるポート面積（`get` / `set` / `invalidate` + TTL）を破り、ドメイン境界のポートに HIT/MISS というインフラ都合の情報が漏れる |
| **`SearchResult` にキャッシュメタデータ（HIT/MISS）を持たせる案** | ドメイン型にインフラ概念が漏れる。`architecture-rules.md` の DDD 語彙規律に反する |
| **TTL を環境変数化する案** | `R-5`（必要レート枠の逆算）が未確定な段階で運用面だけを増やす YAGNI |
| **検索と詳細で同一 TTL にする案** | `NFR-5` が別 TTL を要求している |
| **`AsyncLocalStorage` で Worker エントリから SSR レンダリング内部へ HIT/MISS を運ぶ案** | 実機検証（`wrangler dev --local` + スタブ GitHub API）で store が伝播せず不成立（§2.3 の 1） |
| **画面（Server Component）を client fetch 構成に作り替え、SSR 応答にも観測手段を持たせる案** | `SP-5` のスコープを超える UI アーキテクチャ変更（スコープ侵食・§2.3 の 3） |
| **HTTP `Cache-Control` + Workers Caching を L2 の主役にする（`D-18` 原案）** | §4.5 の動的ヘッダ付与と両立しないため撤回（エッジキャッシュが HIT すると Worker 自体が実行されず `X-Cache-Status` を付与できない。`D-24` で改訂） |

---

## 5. 結果（この決定がもたらすもの）

### 良い方向

- `D-5` の設計制約（外部キャッシュへ後から差し替え可能）を満たしたまま、`SP-5` の受け入れ条件（キャッシュヒットの外部検証）を達成できる
- `src/usecases/*` を無改修のまま `CachingRepositoryQuery` を composition root で着脱でき、`ARCH-2` / `ARCH-3` / `ARCH-4` を維持できる
- ポート面積を広げないため、`NFR-17` の歯止め（汎用キャッシュライブラリを自作しない）を保てる
- `CachingRepositoryQuery` は `search` / `findDetail` それぞれにキー単位の in-flight `Promise` マップを持ち、同一キーへの並行リクエストを **single-flight**（先行 `Promise` への相乗り）で単一化する。`NFR-7`（request coalescing）は、`D-24` でエッジキャッシュ側の格上げが撤回された後も、**アプリ層（`CachingRepositoryQuery`）でこの形で担保** される

### 受け入れる代償

| 代償 | 緩和策 |
|---|---|
| `InMemoryCache` は isolate をまたいで永続しない | 本スプリントでは追わない設計判断（[`cloudflare-infrastructure.md`](../03_design/infrastructure/cloudflare-infrastructure.md) §4.2）。将来の格上げ候補として Cache API（`caches.default`）の能動利用を記録するに留める |
| TTL が暫定値で根拠が実測でない | `R-5` 確定後に見直す再決定条件を明記（§3.4） |

---

## 6. 参照

| ドキュメント | 関係 |
|---|---|
| [`prd.md`](../02_requirements/prd.md) `NFR-5` / `NFR-17` / `NFR-18` | 要件の正本 |
| [`open-questions.md`](../02_requirements/open-questions.md) `D-5` | YAGNI 例外・外部キャッシュ差し替え可能という設計制約の決定ログ |
| [`open-questions.md`](../02_requirements/open-questions.md) `D-18` / `D-24` | MVP キャッシュの当初方針（`D-18`）と、本 ADR の検証結果を受けた L2 実装の改訂（`D-24`）の決定ログ |
| [`cloudflare-infrastructure.md`](../03_design/infrastructure/cloudflare-infrastructure.md) §4 | キャッシュ層設計の正本（L2 の主役を本 ADR と同じ理由で `CachePort` 実装へ改訂済み） |
| [`architecture-rules.md`](../rules/architecture-rules.md) `ARCH-2` / `ARCH-3` / `ARCH-4` | 依存規則（ポート引数注入・内向き依存・事業者固有バインディングの隔離） |
| [議論記録](../../content/discussions/sp5-cache-design-20260819/whiteboard.md) | 争点 C・D の 3 レンズ・3 ラウンドの敵対的相互検証の全文 |
