# ADR 0005: Cache Port を YAGNI の意図的な例外として維持し、TTL 暫定値を確定する

- **状態**: **承認**
- **日付**: 2026-08-19 JST
- **対応要件**: `NFR-5` / `NFR-17` / `NFR-18` / `E-3` / `R-5` / `D-5` / `ARCH-2` / `ARCH-3` / `ARCH-4`
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

---

## 4. 却下した選択肢

| 選択肢 | 却下理由 |
|---|---|
| **ユースケースに `CachePort` を直接引数注入する案** | 呼び出し元（`search-repositories.ts` / `get-repository-detail.ts`）が増えるたびに配線が重複し、キャッシュキー生成の責務がユースケースへ漏れる（§3.2） |
| **`CachePort.get` の戻り値を `{ value, status }` に広げる案** | `NFR-17` が定めるポート面積（`get` / `set` / `invalidate` + TTL）を破り、ドメイン境界のポートに HIT/MISS というインフラ都合の情報が漏れる |
| **`SearchResult` にキャッシュメタデータ（HIT/MISS）を持たせる案** | ドメイン型にインフラ概念が漏れる。`architecture-rules.md` の DDD 語彙規律に反する |
| **TTL を環境変数化する案** | `R-5`（必要レート枠の逆算）が未確定な段階で運用面だけを増やす YAGNI |
| **検索と詳細で同一 TTL にする案** | `NFR-5` が別 TTL を要求している |

---

## 5. 結果（この決定がもたらすもの）

### 良い方向

- `D-5` の設計制約（外部キャッシュへ後から差し替え可能）を満たしたまま、`SP-5` の受け入れ条件（キャッシュヒットの外部検証）を達成できる
- `src/usecases/*` を無改修のまま `CachingRepositoryQuery` を composition root で着脱でき、`ARCH-2` / `ARCH-3` / `ARCH-4` を維持できる
- ポート面積を広げないため、`NFR-17` の歯止め（汎用キャッシュライブラリを自作しない）を保てる

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
| [`cloudflare-infrastructure.md`](../03_design/infrastructure/cloudflare-infrastructure.md) §4 | キャッシュ層設計の正本（L2 の主役を本 ADR と同じ理由で `CachePort` 実装へ改訂済み） |
| [`architecture-rules.md`](../rules/architecture-rules.md) `ARCH-2` / `ARCH-3` / `ARCH-4` | 依存規則（ポート引数注入・内向き依存・事業者固有バインディングの隔離） |
| [議論記録](../../content/discussions/sp5-cache-design-20260819/whiteboard.md) | 争点 C・D の 3 レンズ・3 ラウンドの敵対的相互検証の全文 |
