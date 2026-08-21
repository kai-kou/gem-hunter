<!--entry
author: rate_cache
round: 1
kind: claim
ts: 2026-08-21T09:59:06+09:00
-->

## rate_cache: レート予算とキャッシュ設計（争点 1・2・6 主担当）

### 争点1（主担当）: 全件取得は「gemIndex 選択時だけ」発火させるべき（常時化は不可）

**実測値の根拠**（`docs/05_release/repository-publication-review.md` §7.2・[ADR 0005](../adr/0005-cache-port-yagni-exception-and-ttl.md) §3.4 追補）:

| 項目 | 値 |
|---|---|
| 検索 API 枠（アプリ全体で共有・認証済み） | **30 req/分** |
| 想定利用者の検索頻度 | 約 **1.3 検索/分/人** |
| 現行の逆算結果（1 検索 = 1 upstream call） | 30 ÷ 1.3 ≒ **同時実利用者 23 名** が上限 |

`D-30`② により `sort=gemIndex` は 1 検索あたり最大 **10** upstream call（`per_page=100 × 10 ページ`）になる。これを**常時**（sort 無関係に全検索で）発火させた場合:

```
30 req/分 ÷ (1.3 検索/分/人 × 10) ≒ 同時実利用者 2.3 名 が上限
```

**23 名 → 2.3 名で約 90% の容量喪失**。公開判断ゲート（`M-4`）は「想定同時実利用者が 23 名を大きく下回る」ことを前提に暫定 TTL のままで通過判定した（§7.2）。常時化はこの前提を覆し、**再度 `R-5` の逆算・`M-4` 判定をやり直す必要が生じる**規模の劣化。

🔴 **結論**: 全件取得（10 call）は `sort=gemIndex` が明示選択されたときだけに限定する。既定 sort（`relevance`/`stars`/`updated`）の検索は従来どおり 1 call のまま温存し、23 名の余裕を維持する。`sort=gemIndex` を **既定 sort にはしない**（既定化した瞬間に上の 2.3 名ケースへ収束するため、AR-2 の既定値選定にも波及する判断であり、UI 側と要合意）。

---

### 争点2（主担当）: キャッシュキー設計

現行 `searchResultCacheKey`（`src/infrastructure/platform/cache-key.ts:52-54`）は `keyword:page:sort:per_page` を全て含む合成キーで、gemIndex 全件取得の結果（最大 1,000 件・ページ横断）の再利用には使えない（page/perPage が変わるたびに別キーになり、10 call を毎回やり直す）。

**提案**: (A) の変形として、**新しい名前空間** `search-raw`（仮）を `keyword` のみでキー化して追加する。

```ts
export function searchRawResultCacheKey(keyword: SearchKeyword): CacheKey {
  return `search-raw:${CACHE_SCHEMA_VERSION}:${normalizeSegment(keyword)}` as CacheKey
}
```

- **`perPage` は含めない**（選択肢 A の原案「keyword+perPage」から一部修正）: 全件取得の upstream 呼び出しは常に `per_page=100` 固定（GitHub API 上限・D-30②）であり、**表示側の perPage（AR-3・20/50/100）とは無関係**。表示 perPage をキーに含めると同じ全件データを 3 通りに複製してキャッシュすることになり、ヒット率が落ちるだけでメリットがない。ページ・並び替え・表示件数はキャッシュ済みの生データを取り出した後に**メモリ上でスライス**すれば済む。
- 既存の `search:` 名前空間（`searchResultCacheKey`）はそのまま温存し、gemIndex 以外の sort はそちらを使い続ける（1 call 経路を壊さない）。
- **`CACHE_SCHEMA_VERSION` のバンプは不要**: `cache-key.ts:18-21` の docstring どおり、バンプが要るのは「同じキーに対して返るべき値の意味が変わる」変更のとき。今回は**新しい名前空間の追加**であり、既存 `search:` キーの意味は変えない。
- **TTL**: 現行 `TTL_SEARCH_SECONDS = 60`（`docs/adr/0005-cache-port-yagni-exception-and-ttl.md` §2.2）と同値を踏襲するのが妥当。理由は 2 つ: ① `NFR-5` の「検索結果は鮮度要求が高い」という位置づけは gemIndex 全件データも変わらない ② ADR 0005 §4 が「TTL を環境変数化する案」を YAGNI として却下済みで、gemIndex 専用の別定数を今すぐ増やすのも同じ理由で避けたい。ただし全件取得のコストが 10 倍である以上、**60 秒のままでヒット率が足りるかは `R-5` 同様に実測で再検証すべき**（争点1 で 23 名 → 2.3 名の劣化が起きる以上、TTL を伸ばす（例: 300 秒）ことが唯一の追加防御レバーになりうる。実装 Issue 側で計測フックを残すことを推奨）。

---

### 争点6（主担当）: `enforceSearchRateLimit` は 10 call を数えられていない（構造的な欠落）

`src/composition/rate-limit.ts:20` の `enforceSearchRateLimit(headers)` を実装確認した。

```ts
export async function enforceSearchRateLimit(headers: Headers): Promise<void> {
  ...
  const decision = await limiter.consume(key)   // consume に cost/weight 引数なし
  ...
}
```

呼び出し箇所は `app/api/search/route.ts:64` と `app/[locale]/page.tsx:73` の 2 箇所で、**`query`（sort を含む）を渡していない**。`limiter.consume(key)` は `WorkersRateLimit.consume`（`src/infrastructure/platform/rate-limit.ts:32`）を経由し、最終的に Cloudflare Rate Limiting binding の `limit({ key })`（`RateLimiterBinding.limit`・同ファイル 7-9 行目）を呼ぶが、この binding の型自体に **cost/weight パラメータが存在しない**（`{ key: string }` のみ）。

つまり `enforceSearchRateLimit` は「1 論理検索 = 1 リクエスト」としてクライアント単位のスロット（`wrangler.jsonc` の `RATE_LIMITER: { limit: 60, period: 60 }`）を 1 消費するだけで、**sort が `gemIndex` かどうか・内部で何回 upstream を叩くかを一切見ていない**。SP-16 以前は「1 検索 = 1 upstream call」だったため偶然 1:1 で整合していたが、gemIndex 導入後はこの前提が崩れる。

**実害**: 1 クライアント（1 IP）が `sort=gemIndex` で 60 秒間に上限の 60 検索を打てば、自スロットは通過扱いのまま **upstream へ最大 600 call/分**（アプリ全体の共有枠 30 req/分の 20 倍）を発生させられる。これは「クライアント単位の間引きが上流の総量を守らない」という `repository-publication-review.md` §7.2 の既知の残余リスクを、**同一クライアントだけで即座に具現化**させる規模の悪化。

**修正箇所（具体）**:
1. `src/composition/rate-limit.ts:20` の関数シグネチャに `sort`（または `cost: number`）を追加し、`sort === 'gemIndex'` のときは別スロット（別 key 名前空間、例 `gemindex-search:<hash>`）かつ低い上限（10 call 相当に合わせるなら `wrangler.jsonc` 側で `limit: 6, period: 60` = 60÷10）で消費する。Cloudflare Simple Rate Limiting の `limit()` に cost 引数が無いため、**同一スロットを重み付けする方式は取れない**（1 呼び出し = 1 カウントのみ）。別スロット化が現実的な実装手段。
2. `app/api/search/route.ts:64` と `app/[locale]/page.tsx:73` の呼び出し箇所で、`enforceSearchRateLimit` 呼び出し時点で `sort` が確定しているか要確認（route.ts は現状 `keyword` しかパースしていないため、`sort` も `parseSearchParams`/`SEARCH_PARAM_KEYS` 経由で早期に取り出す変更が要る）。
3. `wrangler.jsonc:15` に gemIndex 専用の `ratelimits` エントリを追加。

---

### single-flight（争点主担当外だが実測確認）

`CachingRepositoryQuery.readThrough`（`cached-repository-query.ts:70-110`）の in-flight マップは `searchResultCacheKey(query)`（page/sort/perPage 込み）をキーにしている。**争点2で提案した `search-raw` 名前空間の全件取得には、この single-flight マップがそのままでは効かない**（別の場所・別のキー体系で新設する fetch のため）。同一キーワードを同時に複数ユーザーが gemIndex 検索した場合、**表示ページ番号が違うだけで single-flight が合流せず**、それぞれが独立に 10 call を発行しうる。全件取得の実装は `search-raw` キー単位（keyword のみ）で**専用の in-flight マップ**を持たせる必要がある（既存 `inFlightSearch` の流用は不可・キーの粒度が違うため）。

---

### キャッシュのメモリ影響

`InMemoryCache`（`src/infrastructure/platform/cache.ts:18-45`）は素の `Map` で **上限・LRU 一切なし**。`get` 時に期限切れなら遅延削除するだけで、書き込み時のサイズ管理は無い。

`RepositorySummary`（`src/infrastructure/github/mapper.ts:30-43`）は `id/name/fullName/owner{login,avatarUrl}/description/primaryLanguage/stars/lastPushedAt/topics[]/htmlUrl` を保持する。1 件あたり V8 のオブジェクト・文字列オーバーヘッド込みで概算 **1〜2KB**、1,000 件で **1〜2MB/キーワード**。

争点1の逆算どおり同時実利用者を 23 名程度（うち gemIndex 選択者はその一部）と見ても、TTL 60 秒の窓内で異なるキーワードが数十件同時にキャッシュされれば **数十MB規模**に達しうる。Cloudflare Workers の isolate メモリ制約下では、Next.js/OpenNext ランタイム自体の常駐メモリと合算した際の余裕を要確認。`InMemoryCache` に上限がない設計は SP-5 時点では軽量な `SearchResult`（1 ページ分・最大 100 件）を前提にしていたはずで、1,000 件の全件データを同じ無制限 `Map` に載せるのは **設計前提の逸脱**。最低限、`search-raw` エントリ数に上限（例: 直近 N キーワードの LRU）を設けることを実装 Issue に含めるべき。
