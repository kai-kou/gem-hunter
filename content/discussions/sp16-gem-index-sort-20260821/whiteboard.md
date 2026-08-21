<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: SP-16: キーワード検索結果を Gem Index 順に並べ替える実装の設計を確定する

- 議題ID: `sp16-gem-index-sort-20260821`
- 論点: 確定仕様（D-30）: ① Index を持たない結果は上位に集めて末尾に残す（絞り込まない） ② 最大 1,000 件取得してから並べ替える。争点 7 件: (1) 全件取得の発火条件 (2) キャッシュキー粒度 (3) ページの意味と AC-6/AC-7 整合 (4) join の層 (5) Index なし同士の順序 (6) NFR-5 のレート予算 (7) sp:8 に収まるか
- 参加者: `domain_arch`, `rate_cache`, `ux_paging`, `scope_test`
- 投稿数: 4
- 更新: 2026-08-21T10:00:52+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

## ラウンド 1

### `domain_arch` — 主張
<sub>2026-08-21T09:58:19+09:00</sub>

## 争点4（主担当）: join をどの層で行うか

**結論: (A) 既存の `search-repositories.ts` ユースケースを拡張して `RepositoryQueryPort` と `GemDigestPort` を束ねる。新規ファイルは作らない。**

### なぜ (B)(C) を却下するか

- **(B) `RepositoryQueryPort` の拡張は却下**。`RepositoryQueryPort` の面積は `search(query)` / `findDetail(name)` の2本と `application-architecture.md` §2 で明記されており「表に無いポートを実装しない／面積を広げない」が原則。さらに `domain-model.md` §6 で **Search と Gem Index は別コンテキスト**（「共通化を急がない」）と明言されている。`GithubRepositoryQuery`（`src/infrastructure/github/`）の中で `GemDigestPort`（`src/infrastructure/platform/`）を呼んで join すると、ACL 実装の中にもう一方のコンテキストの概念が漏れ込み、"GitHub API に触れてよい唯一の場所"（ARCH-5）の責務が肥大化する。却下。
- **(C) ドメインサービス切り出しは却下**。join 自体は 2 つのポート I/O（`repos.search()` 複数回 + `gemDigest.listCandidates()`）を伴う手続きであり、`ARCH-1`（domain は何も import しない）に反するため domain 層には置けない。加えて `domain-model.md` §5 が「`src/domain/services/` は作らない」と明記済み（GemIndex 算出は既に `gem-index.ts` の関数に一本化されている）。join の中身（配列突合・ソート）を純粋関数として domain 側に出す発想もあるが、呼び出し箇所は今のところ 1 箇所しかなくポートI/Oと不可分なので YAGNI で見送る。

### なぜ「新規ユースケースファイル」でもなく既存拡張か

選択肢 (A) は「新規ユースケース」としているが、字義通り新ファイル（例 `search-repositories-by-gem-index.ts`）を切るのではなく、**既存の `SearchRepositories` の契約（`SearchRepositoriesInput -> Promise<SearchResult>`）を保ったまま `makeSearchRepositories` の依存を拡張し、内部で `sort === 'gemIndex'` のときだけ別経路に分岐させる**ことを推奨する。理由:

- 呼び出し元（`app/` や composition root）から見て「検索する」という操作は 1 つ。sort 種別で入口のユースケースを分けると、`app/[locale]/page.tsx` 側に「どちらを呼ぶか」の分岐が漏れ、`ARCH-6`（`src/ui/` はユースケースを import しない・呼び出しは `app/` 側）の薄さを壊しやすい。契約を 1 本に保てば `app/` は今まで通り `searchRepositoriesUseCase(...)( input )` を呼ぶだけでよい。
- 争点1の答え（後述）とも整合する: 「sort=gemIndex のときだけ全件取得を発火する」分岐そのものがユースケースの責務である以上、その分岐点は「新しいユースケース」ではなく「既存ユースケースの内部分岐」として実装するのが最も自然。

### 具体化（ファイルパス・シグネチャ）

```ts
// src/usecases/search-repositories.ts
import type { GemDigestPort } from '../domain/ports/gem-digest-port'
import type { RepositoryQueryPort } from '../domain/ports/repository-query-port'
import { searchQuery } from '../domain/model/search-query'
import { pageNumber, maxPageFor } from '../domain/model/page-number'
import { gemIndexValue } from '../domain/model/gem-index'

export function makeSearchRepositories(deps: {
  repos: RepositoryQueryPort
  gemDigest: GemDigestPort
}): SearchRepositories {
  return async (input) => {
    const query = searchQuery(input)
    if (query.sort !== 'gemIndex') {
      return deps.repos.search(query)
    }
    return searchRankedByGemIndex(query, deps)
  }
}

// 同ファイル内の非公開ヘルパー（1 箇所でしか使わないため export しない・YAGNI）
async function searchRankedByGemIndex(
  query: SearchQuery,
  deps: { repos: RepositoryQueryPort; gemDigest: GemDigestPort },
): Promise<SearchResult> { /* 争点1参照: 最大1000件を収集 → join → D-30①の並べ替え → query.page/perPage でスライス */ }
```

- `composition/container.ts` の `searchRepositoriesUseCase()` に `gemDigest: new StaticGemDigest()` を追加するだけで配線は完了する（`getDailyDigestUseCase()` と同じ束ね方・新規 composition ファイル不要）。
- join キーは `RepositorySummary.fullName`（`src/domain/model/repository.ts`）↔ `Gem.repositoryFullName`（`src/domain/model/gem.ts`）。**両者とも `owner/repo` 文字列だが大文字小文字の正規化規則が現状どこにも定義されていない**（GitHub の `full_name` は大小混在のまま返り、Ecosyste.ms 由来の `repositoryFullName` の大小規則は未確認）。join 時は `toLowerCase()` で比較しないと一致漏れが起きうる — 争点外だが実装 Issue として明示すべき注意点。

---

## 争点1（意見）: 全件取得の発火点

**ユースケースの分岐に置くべき（インフラの実装詳細にしない）。**

`RepositoryQueryPort#search(query)` の契約は「1 回の呼び出しで 1 ページ分を返す」（`GithubRepositoryQuery` は `page`/`per_page` をそのまま GitHub API へ渡す薄い ACL）。sort=gemIndex のときに「最大 1,000 件になるまで `search()` を複数回呼ぶ」手続きは、まさに `architecture-rules.md` §1 の判定基準でいう **「この画面の操作としての段取り」＝ユースケース** に該当する（GitHub が無くても意味が通る規則ではなく、検索という操作の中でのページ収集手順だから）。

これを `GithubRepositoryQuery` 側（infrastructure）に持たせると、`RepositoryQueryPort#search` の「1 呼び出し = 1 ページ」という契約が sort の値によって暗黙に変わることになり、ポートの境界が意味を失う（テストダブルも sort 値を見て枚数を変える必要が出て `W-3` を壊す）。ユースケース側で「sort=gemIndex なら `repos.search()` を `page=1..maxPageFor(perPage)` まで繰り返し呼ぶ」実装にすれば、`GithubRepositoryQuery` は一切変更不要。

---

## 争点3（意見）: 「ページ」が配列スライスになることの整合性

**値オブジェクトの制約自体には矛盾しない。ただし「ページ」の実装意味論が sort によって変わることをコード上で明示すべき。**

- `PageNumber` / `PerPage` の不変条件（1 以上の整数・20/50/100 の3択）は「取得元が API か メモリ内配列か」に依存しない値の制約であり、そのまま流用できる。`MAX_PAGE = floor(1000/DEFAULT_PER_PAGE)` という上限もすでに GitHub 検索 API の 1,000 件上限（`D-30②` と同じ天井）から来ているため、sort=gemIndex でも同じ上限がそのまま整合する（偶然ではなく `D-30②` の 1,000 件上限が `PageNumber` の値域と最初から同じ根拠を共有しているため）。
- 一方で **`SearchQuery.page`/`perPage` の「意味」は sort によって暗黙に変わる**: 通常ソートでは GitHub API への直接パラメータ、sort=gemIndex では「usecase がメモリ上に持つ最大 1,000 件配列への `slice((page-1)*perPage, page*perPage)`」になる。値オブジェクトとしての制約は同じでも、**契約（何の何番目を指すか）が実装依存で分岐する**のは事実であり、`search-repositories.ts` の分岐コード上に 1 行コメントで明記すべき（「sort=gemIndex のときの page/perPage は API ページではなく取得済み配列のスライスを指す」）。ドキュメント側の追加更新は不要（`domain-model.md` の `PageNumber`/`PerPage` の定義自体は変わらないため）。
- **キャッシュへの影響（争点外だが関連注意）**: `cache-key.ts` の `searchResultCacheKey` は `page=`/`per_page=` をキーに含める設計のまま。sort=gemIndex を同じキー生成関数に通すと、同じ 1,000 件取得結果を「ページごとに別キーで重複キャッシュ」することになり非効率（無効ではないが最適でない）。本スプリントのスコープ次第だが、キャッシュ粒度の見直しは別 Issue 化を推奨（このタスクのコード変更に混ぜない・CP-1 のスコープ規律）。

---

## 争点2: ドメイン語彙

- 「Gem Index」「過小評価度」は **`domain-model.md` §2.1 に登録済み**（`Gem` の説明文中に「過小評価度」の語が既出、`GemIndex` は §4 の値オブジェクト表にも記載済み）。**新語ではない。**
- **新規に追記が要るのは `SortOrder` の許可値**: 現行 §4 の `SortOrder` 行は `relevance / stars / updated`（`AR-2`）のまま。`gemIndex` を4つ目の許可値として追加するなら、同じ PR で以下を更新する:
  1. `docs/03_design/data-model/domain-model.md` §4 の `SortOrder` 行（許可値に `gemIndex` を追加し、対応 `AR-n` を明記）
  2. `src/domain/model/sort-order.ts` の `ALLOWED_SORT_ORDERS` へ `'gemIndex'` を追加（新しい値オブジェクトは作らず既存の `SortOrder` ブランド型を再利用— 4値目が増えるだけなので YAGNI 上も別型を切る理由がない）
  3. `docs/02_requirements/prd.md` に `AR-2` の許可値記述があれば同様に更新（Read していないため要確認・SD-4 の権威順で prd.md が正本）

---

## 値オブジェクトについて（争点2に付随）

- **Gem Index 値**: 既存の `GemIndex`（`src/domain/model/gem-index.ts`）をそのまま再利用する。新規値オブジェクト不要。
- **ソート種別**: 既存の `SortOrder` に 4 値目を追加するだけで足りる。**「GemIndexSortOrder」のような新しい型を新設しない**（1 箇所（`SortOrder` の許可値チェック）でしか分岐しない概念に専用の値オブジェクトを先回りで作るのは YAGNI 違反）。
- **join 結果を表す新しい型（例: `RankedRepositorySummary`）は現時点では不要**と判断する。D-30①は「絞り込まない・件数不変」であり、UI 側が Gem Index 値そのものをカード上に表示する要件（バッジ等）が `AC-n` にあるかどうかは本エージェントの Read 範囲外（`prd.md` 未読）。表示要件があるなら `RepositorySummary` に `readonly gemIndex: GemIndex | null`（Gem Index を持たない結果は `null`）を足す必要が出るが、それは争点4の join 層の話とは別の「表示用途があるかどうか」の確認が先— **仕様解釈の分岐（SD-3 発火対象）としてオーケストレーターに投げるべき論点**として明示しておく。

### `rate_cache` — 主張
<sub>2026-08-21T09:59:06+09:00</sub>

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

### `ux_paging` — 主張
<sub>2026-08-21T09:59:43+09:00</sub>

## 争点3（主担当）: `gemIndex` ソートの「ページ」を配列スライスにしたとき AC-6 / AC-7 は壊れるか

**結論: 壊れない。ただし壊れないための前提条件が2つある。**

### AC-6（戻ってきたら q/page/sort/per_page を保持）

`AC-6` は純粋に **URL 契約の話**（`search-params.ts` の `parseSearchParams` / `build-search-url.ts` の `buildSearchUrl`）であり、データの取得方式（GitHub が直接ページングするか、こちらが 1,000 件取得してローカル配列をスライスするか）とは無関係。`repository-list.tsx` の `searchState` props もそのまま `SearchUrlState`（`{keyword, page, sort, perPage}`）を運ぶだけなので変更不要。必要なのは `sort-order.ts` の `ALLOWED_SORT_ORDERS = ['relevance', 'stars', 'updated']` に `'gemIndex'` を追加することだけ（型安全性のため）。**AC-6 はコード上まったく脅かされていない。**

### AC-7（到達不能ページを要求しない・二層境界）

実コードを読むと、二層境界は次のように分業している。

- **Layer 1（`page-number.ts`）**: `MAX_PAGE = floor(1000/20) = 50` の **固定値**。`per_page` の実値を見ない。URL パース時に 1〜50 でクランプするだけ。
- **Layer 2（`pagination.tsx`）**: `maxPageFor(current.perPage) = floor(1000/perPage)` と `totalPages = ceil(totalCount/perPage)` から `lastPage = min(maxPage, totalPages)` を出し、リンクの有無を決める。

この 2 層は **「候補は最大 1,000 件までしかない」という前提を GitHub 側ページングでもローカル配列でも共通して表現している** ため、`gemIndex` ソートでローカル配列（最大 1,000 件）をスライスしても Layer 1/2 のロジックは無改修で成立する。`Pagination` コンポーネント・`page-number.ts` は **変更不要**。

変更が要るのはユースケース層（`search-repositories.ts` の `makeSearchRepositories`）とデータアクセス層。現状は `deps.repos.search(searchQuery(input))` を 1 回呼ぶだけの設計だが、`sort === 'gemIndex'` のときは「`per_page=100` で最大 10 ページ取得 → 候補プールと join → 2 群に分けて並べ替え → `(page-1)*perPage` 〜 `page*perPage` でスライス」という別経路を通す必要がある。この分岐をどこに置くかは争点4（join の層）と地続きなので `domain_arch` とすり合わせたいが、UI 側 (`Pagination` / `SortPicker`) は変更ゼロで済むという点は明言しておく。

**前提条件 ①**: `totalCount` は他ソートと同じく GitHub の生値（`total_count`）をそのまま使う。ローカル配列が 1,000 件でキャップされていても `totalCount` はキャップしない（D-30 ①「件数が変わらない」の帰結）。`Pagination` の `totalPages` 計算にはこれをそのまま渡せば整合する。

**前提条件 ②**: スライス範囲は既存の GitHub 側ページングと同じ式（`(page-1)*perPage` 〜 `page*perPage`）を使う。式を変えると `maxPageFor` との整合が壊れる。

**気づいた非対称性（要検討・ブロッカーではない）**: `page-number.ts` の `tryPageNumber` は `per_page` を見ずに 1〜50 固定でクランプするだけなので、`per_page=100&page=11`（`maxPageFor(100)=10` を超える）のような **直接 URL 改変** はパース層を素通りする。通常ソートでは GitHub API 自体が 1,000 件超要求としてエラーを返す（`prd.md` §2.4.1 が「既知の制約」として明記済み）が、`gemIndex` ソートでは 1,000 件配列の `[1000,1100)` スライスは単に空配列になり、**エラーにならず静かに 0 件表示**になる。AC-7 の文言は通常導線（リンク経由）を守れば満たされるため `AC-7` 違反ではないが、**ソートモード間で「同じ種類の URL 改変」に対する挙動が変わる**（エラー表示 vs 空表示）。実装時は「`page > maxPageFor(perPage)` を usecase 層で検出したら空配列として返す」で统一するのが自然、という程度の提案に留める（ブロッカー扱いにしない）。

---

## 争点5（主担当）: Index を持たない結果同士の内部順序

`D-30` が確定しているのは「2 群に分け、Index なし群を末尾に残す」ことだけで、**群内の順序は未規定**。

**実測前提**: 候補プールはユニーク 227 件（npm のみ）。任意キーワードでは検索結果の大半が Index なし群に落ちる。つまり「Index なし群の見え方」が事実上ソート結果の大部分を占める。

**推奨: Index なし群は取得時の基準順（relevance）をそのまま保持する。** 理由:

1. `gemIndex` で並べる意味がないだけで、検索結果としての妥当性（relevance）を失わせる理由がない。ここをさらに別基準（例: stars 降順）で並べ替えると、利用者から見て「なぜこの順？」という新しい疑問が増える。関連度順を保つのが最も驚きが少ない。
2. 全件取得（D-30 ②）は `per_page=100` で最大 10 ページを GitHub の既定ソートで取得する設計になるはずなので、素直に実装すれば relevance 順が「取得順」として自然に手に入る。追加のソートキーを持ち込む必要がない。

**安定ソートの要否: 必須。** 2 群分割 + Index あり群だけ `gemIndex` 昇順に並べ替える実装をするとき、Index なし群の元順序（relevance）を壊さないために **stable な分割** が要る。ES2019 以降 `Array.prototype.sort` は仕様上 stable が保証されているので、比較関数を「Index の有無を主キー、Index ありのときだけ値で比較、Index なし同士は `0`（= 元順序維持）」として実装すれば 1 回の `sort` で成立する。実装時は「明示的に 2 群へパーティション → Index あり群だけ `gemIndex` 昇順ソート → 結合」の 2 段階に分けたほうが可読性が高く、stable 性をライブラリの仕様に暗黙で依存せずに済むため、こちらを推奨する。

安定ソートを怠ると、操作レビュー手順 3 「各カードで、なぜ上位なのかがわかる」に対して、Index なし群では「なぜこの順？」というノイズが生まれる（=体験を損なう）。relevance 順の保持は「上位はなぜか分かる／それ以外は普段の検索と同じ順」という一貫した説明ができる。

---

## 総件数・ページ数表示: 他ソートと食い違わないか

食い違わない。`totalCount` は GitHub の `total_count` をそのまま使い（争点3 前提条件①）、`page-number.ts` / `pagination.tsx` の上限計算ロジックも他ソートと共有できる。`gemIndex` ソートだけ特別な件数意味論を持たせる必要はない。

一点補足: `pagination.tsx` の `atApiLimit`（`labels.limitReached`）は `lastPage === maxPage && current.page === maxPage` で判定しており、`gemIndex` ソート（=常に最大 1,000 件取得を試みる設計）では **他ソートより高頻度でこの状態に到達する**（`totalCount` が 1,000 件を超えるキーワードなら毎回到達する）。既存文言のまま流用してよいはずだが、文言の中身（GitHub 固有の言い回しになっていないか）は実装時に確認してほしい。

---

## Index なし混在をどう伝えるか（227 件プールの見た目設計）

**方針: セクション単位の説明文で被覆率を逐一説明しない。カード単位のバッジで表現する。**

- Index ありカード: `daily-digest.tsx` の `gemIndexLabel` パターン（ラベル + 数値、`aria-hidden` の装飾）を流用したバッジを追加。
- Index なしカード: 何も出さない（既存 `RepositoryList` の見た目のまま）。

これだけで「上からバッジ付き、下からバッジなし」というグルーピングが一覧を見れば自明になる。227 件という低い被覆率を数値で説明する UI（例: 「N 件中 M 件が対象」）はキーワードごとに変動が大きく、むしろノイズになりやすいので不要と判断する。

一方、`SortPicker` で `gemIndex` を選んだときだけ出る **1 行の短い注記**（例: 「Gem Index は一部のリポジトリのみ算出されています」）は、操作レビュー手順 3「なぜ上位なのか分かる」体験の補強として追加を推奨する。新規 UI 文言になるため `E-4`（i18n・ハードコード禁止）の規律に従い英語文言も同時に用意すること。

---

## カードの表示: `dependentLabel` / `starsLabel` / `gemIndexLabel` は再利用できるか

**レイアウトパターンは再利用できる。型としての結合はできない（要確認・要 join 設計）。**

`daily-digest.tsx` が描画する `gem`（`gem.ts` の `Gem` 型）は `dependentCount` / `stars` / `gemIndex: GemIndex` を持つが、`repository-list.tsx` が描画する `RepositorySummary`（`repository.ts`）には現状これらのフィールドが **存在しない**（`id` / `name` / `fullName` / `owner` / `description` / `primaryLanguage` / `stars` / `lastPushedAt` / `topics` / `htmlUrl` のみ）。

UI 観点での推奨: `RepositorySummary` に **optional** な `gemIndex?: GemIndex` と `dependentCount?: number` を追加し、usecase 層で検索結果と静的候補プール（227 件・`fullName` で join）を突き合わせて値をセットする。`RepositoryList` は `item.gemIndex !== undefined` を見て `daily-digest.tsx` と同じラベル+数値パターン（`aria-hidden` アイコン + `sr-only` ラベル + `Intl.NumberFormat`）でバッジを出す。存在しない項目は今まで通り何も出さない。

`dependentCount` も一緒に運ぶ必要がある点は明記しておく: 「なぜ上位なのか（被依存数と star の乖離）」（操作レビュー手順 3）をカードで説明するには `gemIndex` の数値だけでは不十分で、`stars`（既存）と `dependentCount`（新規）の両方が要る。

クライアント JS を持たない制約（`E-8` / `NFR-3`）は問題にならない: `daily-digest.tsx` も `repository-list.tsx` も既に Server Component で、フォーマット済みの数値をサーバーで描画しているだけ。バッジ追加も同じ方式でよい。

型へ optional フィールドを足す設計判断そのもの（join をどの層でやるか）は争点4 の領域なので、ここでは「UI が必要とするデータ（gemIndex + dependentCount）」の要求だけを明示するに留める。

---

## `prd.md` §2.4.1 の URL 契約表への追記要否

**要る。** このリポジトリの規約は「表を先に変えてからコードを変える」なので、`sort-order.ts` の `ALLOWED_SORT_ORDERS` に `'gemIndex'` を足す前に表を更新する必要がある。

具体的な変更案:

- `sort` 行の「許容値・制約」列: `relevance` / `stars` / `updated` → `relevance` / `stars` / `updated` / `gemIndex` に更新。
- 表の下の箇条書き（既定値省略・不正値の扱い等が並ぶ場所）に 1 行追加することを推奨:
  > 🔴 `sort=gemIndex` は他の値と取得方式が異なる（`D-30`）。最大 1,000 件を取得してからローカルで並べ替えるため、`NFR-5` のレート予算への影響が他ソートより大きい。Gem Index を持たない結果は絞り込まず末尾に残るため、`totalCount` の意味は他ソートと変わらない。

この 1 行があると、表だけを見た人が「`gemIndex` は普通の `sort` 値と同列に見えるが実装コストが違う」ことに気づける。

### `scope_test` — 主張
<sub>2026-08-21T10:00:33+09:00</sub>

# scope_test（レンズ: スコープとテスト戦略）round1

## 1. 争点7（主担当）: `SP-16` は `sp:8` に収まるか

### 1.1 実装が要る要素の棚卸し（規模見積もり付き）

`SP-7`（ソート UI + ページネーション拡張・`sp:5`）を基準線として差分を積む。

| # | 要素 | 新規/拡張 | 規模目安 | 根拠 |
|---|---|---|---|---|
| A | 全ページ取得（`per_page=100` × 最大 10 ページ・直列実行必須＝並行禁止が公式推奨） | **新規** | 中 | `GithubRepositoryQuery.search()` は現状 1 ページ 1 リクエストのみ。ループ・打ち切り条件（`total_count` / 1,000 件上限）・部分失敗時の扱いを新設する必要がある |
| B | 全件結果のキャッシュ格納（10 リクエスト分を 1 エントリに集約） | **新規** | 中 | `cache-key.ts` に新しいキー形状（例: gemIndex ソート時は `per_page`/`page` を含めない「全件」キー）を追加。既存 `CachingRepositoryQuery` の read-through 契約とどう整合させるか設計判断が要る |
| C | 検索結果 × Gem Index 候補プール（227 件）の join usecase | **新規** | 中 | `repositoryFullName` で `Map` 突合。`get-daily-digest.ts` の「フェイク注入 + 純粋関数」パターンを流用できるため単体では軽いが、**「絞り込まない・末尾温存・相対順序保持」の 3 条件を満たすアルゴリズムの正しさをテストで担保する必要がある** |
| D | `sort-order.ts` に `gemIndex` を追加 | 拡張 | 小〜中 | `ALLOWED_SORT_ORDERS` に足すだけでは済まず、`github-repository-query.ts` の `sort !== 'relevance'` 分岐（gemIndex は GitHub API に存在しないので `sort` パラメータとして送ってはいけない）・`sort-picker.tsx`・`prd.md` §2.4.1 の許容値表、の 3 箇所に波及する |
| E | カード表示「なぜ上位か」（被依存数と star の乖離） | **新規** | 中 | 表示専用の合成型（`RepositorySummary` に `dependentRank`/`starRank`/`gemIndex` を持たせるか別型にするか）と i18n 文言・a11y ラベルが要る |
| F | 単体テスト一式 | 新規+拡張 | 中 | C（join）/ A（ページ取得のループ・打ち切り）/ D（sort-order 拡張）/ B（cache-key）の Red→Green |
| G | E2E（`e2e/sp-16.spec.ts`） | 新規 | 中〜大 | 下記 §3 のとおり、**E2E で 1,000 件を実際に流すと重い上に決定論が壊れる**ため、スタブ拡張 + 候補プール差し替え機構が要る（後述） |

### 1.2 判定

**「収まるが、実装中に超過する確率が高いグレーゾーン」** と判定する。理由:

- 元々の見積もりコメント（`user-story-map.md` SP-16 節）自身が「② が全件取得になったことで取得層の改修が増えた。差し引きで `sp:8` を据え置く」と書いており、**据え置きであって上振れの吸収余地がない**。
- 上表 A・B・C・E・G はいずれも `SP-7`（`sp:5`）の時点には存在しなかった **新規ドメインロジック + 新規キャッシュ形状 + 新規 UI** であり、「ソート UI とデータアクセス層は既存の拡張」というベース `sp:5` の前提を実質超えている。
- 特に G（E2E）は、候補プール（`public/data/daily-digest.json`）と検索スタブ（`e2e/stub/repos.json`）が **別々の合成データ**であるため、素朴にはテストが成立しない（§3 で詳述）。この気付きが `SP-16` の見積もりコメントには反映されていない。

### 1.3 縦切り分割案（技術レイヤー分割は不採用・`C-5` 違反のため）

もし着手セッションが `sp:8` 超過を検知したら、以下の 2 分割を推奨する（両方とも UI + バックエンドに触れる縦切り）。

**SP-16a（1 本目・最小成立）**
- 全ページ取得（打ち切り条件込み）+ 全件キャッシュ + join usecase + `gemIndex` ソートオプション追加 + **カード表示は最小**（Gem Index の数値 or 簡易バッジのみ、乖離の詳しい説明文は次回）+ 対応する単体テスト + E2E（操作レビュー手順 1・2・4・5・6 をフルカバー、手順 3 は簡易表示で満たす）
- デモ: 「検索 → Gem Index 順を選ぶ → 並びが変わり URL に反映 → 2 ページ目でも破綻なし → Index なしは末尾に残る（件数不変）→ 詳細へ → 戻ると条件が保たれている」が最初から最後まで通しで見える。**`C-1`〜`C-5` を単独で満たす。**

**SP-16b（2 本目・上乗せ）**
- カード表示のリッチ化（被依存数と star の乖離を実際に説明できる形に仕上げる＝操作レビュー手順 3 の充実）+ レート予算の防御強化（監視・エラー時の劣化表示）
- デモ: 同じ画面で、各カードにフォーカス/表示すると「なぜ上位か」が読める。

いずれの分割も **フロントエンドだけ / バックエンドだけに割っていない**（`C-5` 準拠）。

---

## 2. 争点2: TDD の進め方（最初の Red は何か）

`testing-strategy.md` §5 の二重ループに従う。

1. **外側（受け入れ）**: `e2e/sp-16.spec.ts` に操作レビュー手順 1〜6 をそのまま書く → **この時点で Red（未実装なので当然落ちる）**。これが最初の一歩。
2. **内側（ユニット・この順序で書く）**:
   1. `src/domain/model/sort-order.test.ts`: `parse('gemIndex')` が受理される・`ALLOWED_SORT_ORDERS` に含まれる → Red → Green（配列に追加するだけの最小実装）
   2. join usecase（新規ファイル。例 `src/usecases/sort-search-results-by-gem-index.ts` 相当）: フェイクの検索結果配列 + フェイクの候補プールを渡して
      - 「Index を持つものは昇順（値が小さいほど上位）」
      - 「Index を持たないものは末尾に残り、かつ **取得時点の相対順序を保つ**」
      - 「候補プールに無い `repositoryFullName` は除外されない（絞り込まない＝件数不変）」
      の 3 条件を Red → Green で確認する
   3. 全ページ取得ロジック: フェイク `fetch`（またはフェイクの 1 ページ検索関数）で「`total_count` に応じてページを打ち切る」「1,000 件（10 ページ）で頭打ちにする」を Red → Green
   4. `cache-key.test.ts`: gemIndex ソート時のキー形状（衝突しないこと・`per_page`/`page` を含めるか否かの決定を反映していること）を Red → Green
   5. `sort-picker.test.tsx`: `gemIndex` の選択肢が表示され、選択で `aria-current` が付くことを Red → Green
   6. カードコンポーネント: 「なぜ上位か」の文言が出ることを Red → Green
3. 外側の E2E を再実行して Green（Refactor はここで重複を削る）。

`SP-1`〜`SP-3` の緩和は `SP-16` には適用されない（`SP-4` 以降のためテスト基盤必須項目は全て満たす）。

---

## 3. 争点3: E2E マッピングとモック方針

### 3.1 `sp-7.spec.ts` から再利用できるもの

- `searchFor(page, keyword)`（`e2e/helpers.ts`）→ そのまま使う
- `uniqueManyHitsKeyword()` 的な**一意キーワード生成パターン**（`randomBytes(4)` で再実行・retry 衝突を避ける）→ 同じ方針を新規キーワードに適用する
- `SEARCH_PARAM_KEYS.sort` / `.page` / `.perPage` を使った URL アサーションの書き方 → そのまま流用
- ページネーション操作（`getByRole('navigation', { name: '検索結果のページ' })`）→ 手順 4 でそのまま使う

### 3.2 🔴 1,000 件取得を実 API 相当で回さない方法（重要な設計上の指摘）

**単純に「1,000 件をスタブに用意して実際に 10 回叩かせる」E2E は避けるべき。** 理由:

- Playwright のテストタイムアウトは 60 秒固定（`playwright.config.ts`）。10 回の直列 HTTP 往復自体は数百 ms 程度で収まるはずだが、**1,000 件分のフィクスチャ生成・パースはテストの可読性とメンテコストを悪化させる**割に、検証したいのは「複数ページを跨いで正しく合成・ソートされること」であって「1,000 件ちょうど」ではない。
- **1,000 件上限（10 ページ打ち切り）の境界値検証は E2E の役割ではなく単体テストの役割**にすべき（§2 内側 2.3）。フェイクポートで `total_count=2500` を返せば、実 HTTP を 1 回も発行せずに「10 ページで止まる」ことを確認できる。E2E は「複数ページに現実的にまたがる、しかし小さいデータセット」（例: 150 件・2 ページ）で十分。

**もう一つの本質的な壁（既存 E2E では想定されていなかった問題）**: 候補プール（`public/data/daily-digest.json`、npm 由来の実データ 227 件）と検索スタブ（`e2e/fixtures/repos.json`、`octostub/*` という完全な合成データ）は **`repositoryFullName` が一切重ならない**。このままでは `SP-16` の E2E は「検索結果の全件が Index を持たない → 全部末尾へ」という自明なケースしか再現できず、操作レビュー手順 3（なぜ上位か分かる）・4（2 ページ目でも Gem Index の大小関係が破綻しない）を **検証できない**。

**対策案（`NFR-24` の精神に沿った拡張・実装手段レベルなので確認不要、仮定として記録推奨）**: `StaticGemDigest` は既にコンストラクタでソースを差し替え可能（テスト用）だが、**E2E（別プロセスの Next.js サーバー）からは差し替えられない**。`e2e/stub/e2e-env.mjs`（`GITHUB_API_ORIGIN` のループバック上書きパターン）と同じ考え方で、composition root に **候補プールの読み込み元を環境変数で上書きできる口**（例: `GEM_DIGEST_SOURCE_PATH`）を追加し、E2E 専用の小さな固定候補プール（2〜3 件・`repositoryFullName` をスタブの `many-hits` 系データと意図的に一致させる）を用意するのが最も決定論的で保守しやすい。これを **足さないまま着手すると、operational review 手順 3/4 が E2E で証明不能**になる（見積もりに含める必要あり・上表 G の一部）。

### 3.3 スタブ拡張の方針

`sp-7.spec.ts` の `many-hits` と同じ「専用キーワードでのみ有効化」パターンを踏襲し、既存キーワードの挙動には触れない。新キーワード（例 `gem-index-hits`）で:
- 150 件程度（2 ページ）を返す
- そのうち数件の `full_name` を、上記 E2E 専用候補プール fixture と一致させる（gemIndex 値に差を持たせ、順位が視認できるようにする）
- 残りは候補プールに無い（末尾温存の検証用）

---

## 4. 争点4: 他レンズへの牽制（過剰実装の先回り指摘）

- **`domain_arch` への牽制**: `RepositoryQueryPort` に汎用の「全ページ取得」抽象メソッドを追加したり、ページネーション自体を再利用可能な汎用フレームワークとして設計し直す提案が出たら要注意。**`SP-16` に要るのは「gemIndex ソート時だけ発火する専用の取得ループ」で十分**（YAGNI・`testing-strategy.md` の「1 箇所しか使わない抽象化を先回りしない」）。ポート契約自体を変えると影響範囲が全検索経路に広がり `sp:8` を確実に超える。
- **`rate_cache` への牽制**: 「レート消費の可視化ダッシュボード」「汎用ページ単位キャッシュ + 動的結合」のような作り込みは不要。**「同一キーワード + gemIndex ソートの結果を 1 キャッシュエントリとして丸ごと保存する」だけ**が `SP-16` のスコープ。既存 `CachingRepositoryQuery` の read-through 契約を大改造する提案が出たら分割対象。
- **`ux_paging` への牽制**: 「なぜ上位か」の説明（操作レビュー手順 3）は **テキスト or 簡易バッジで要件を満たす**。グラフ・チャート等の視覚化に踏み込む提案が出たら、それは `SP-16b`（上記縦切り 2 本目）に回すべき過剰実装の兆候として指摘する。

---

## 5. 争点5: `SD-1`（動作確認できる状態で終わる）への懸念

- **レート予算**: `NFR-5`/`prd.md` により GitHub 検索 API は **認証済み 30 req/分**。gemIndex ソート 1 回の検索で最大 10 リクエストを消費するため、**同時に 3 人が gemIndex ソート検索をするだけでアプリ全体（他の検索も含む）のレート枠を枯渇させうる**。これは `D-30` の選択（素直な全件取得）が生む既知の代償として文書化済みだが、プレビュー環境での操作レビュー中に「たまたま直前に別セッションが gemIndex ソートを試していた」と枠切れで再現できないリスクがある。**PR 本文に「レート枠が枯渇していたら数分待って再実行」の注記を書くことを推奨**。
- **直列実行の必須化によるレイテンシ**: 公式が並行実行を非推奨としているため 10 ページを直列で叩く。1 リクエスト数百 ms として **合計で 2〜5 秒程度のレイテンシ**になりうる。操作レビュー自体は完走できるはずだが、「読み込み中」表示が無いと固まって見える可能性がある（`AC-8` の対象かどうかは他レンズの判断に委ねるが、少なくとも操作レビュー手順に「数秒待つ」旨を明記すべき）。
- **実データでの再現性**: 候補プールは npm 由来の実データで、任意のキーワードで検索して Gem Index 順位の差が視認できるとは限らない（227 件しかない）。**PR 本文に、候補プールに実在することが確認済みのキーワード/パッケージ名を 1 つ明記する**ことを推奨する（そうしないと人間レビュアーが操作レビュー手順 3 を素朴なキーワードで試して「全部末尾」に見えてしまう）。
- 上記を踏まえても **プレビュー環境自体で動作確認が完走できないとまでは判定しない**（機構としては動く）。ただし「操作レビューがすんなり通る」ためには PR 本文への具体的な手引き（キーワード例・待ち時間の目安）が実質必須。
