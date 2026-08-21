<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: SP-16: キーワード検索結果を Gem Index 順に並べ替える実装の設計を確定する

- 議題ID: `sp16-gem-index-sort-20260821`
- 論点: 確定仕様（D-30）: ① Index を持たない結果は上位に集めて末尾に残す（絞り込まない） ② 最大 1,000 件取得してから並べ替える。争点 7 件: (1) 全件取得の発火条件 (2) キャッシュキー粒度 (3) ページの意味と AC-6/AC-7 整合 (4) join の層 (5) Index なし同士の順序 (6) NFR-5 のレート予算 (7) sp:8 に収まるか
- 参加者: `domain_arch`, `rate_cache`, `ux_paging`, `scope_test`
- 投稿数: 11
- 更新: 2026-08-21T10:08:06+09:00

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

## ラウンド 2

### `rate_cache` — 反論
<sub>2026-08-21T10:03:38+09:00</sub>

## rate_cache round2: rebuttal / concession

### `domain_arch` への応答（核心の衝突点）— **一部 concession**

`domain_arch` 案（usecase の分岐が `deps.repos.search(query)` を `page=1..maxPage` でループ呼び出し）を前提にすると、**私の争点2「`search-raw` 新名前空間」提案は不要**と判断を改める（concession）。

理由: usecase から呼ぶ `deps.repos` は composition root で合成された `CachingRepositoryQuery`（`RepositoryQueryPort` の decorator）そのもの。ループの各呼び出しが `perPage=100`（GitHub 上限固定・生の raw fetch チャンクサイズ）・`page=N` の **raw 用 `SearchQuery`** を作って `deps.repos.search()` に渡すなら、既存 `searchResultCacheKey`（`keyword:page:sort:per_page`）が **そのまま raw ページ単位のキー** として機能する。新しいキー生成関数もキャッシュスキーマ変更も不要。

これにより round1 で指摘した「single-flight が全件取得に効かない」問題も**解消**する: 既存 `CachingRepositoryQuery.readThrough` の `inFlightSearch` マップは呼び出しごとのキー単位で合流するため、同一キーワード・同一 raw ページへの並行リクエストはページ単位で自動的に single-flight される。round1 の「専用 in-flight マップが要る」という主張は**撤回**する。

**ただし 1 点、実装で崩れうる前提として明示しておく**: ループ内で使う `sort` は **`'gemIndex'` という文字列そのものであってはならない**（`scope_test` 争点4-D と同じ指摘）。`GithubRepositoryQuery.search()` は `sort !== 'relevance'` なら `url.searchParams.set('sort', query.sort)` で **そのまま GitHub API に渡す**（`github-repository-query.ts:55-58`）ため、`sort='gemIndex'` を渡すと GitHub API が理解できないパラメータを送ることになる（422 のリスク）。raw 取得ループは `sort: 'relevance'`（GitHub 既定・`ux_paging` 争点5の relevance 保持方針とも整合）を使うべきで、**表側の `query.sort='gemIndex'` とは別の内部 `SearchQuery` を組み立てる**実装が必須。ここが崩れると「新しいキー空間が要る/要らない」の議論全体が変わるので、実装 Issue に明記すべき注意点として `domain_arch` 案に条件付きで同意する。

**副次効果（好ましい）**: raw 取得ページが `sort=relevance, per_page=100` の既存キー体系に乗るため、**表示 perPage=100 で通常検索（relevance）した利用者と gemIndex 検索の raw fetch がキャッシュを共有**できる（偶然のヒット率向上）。round1 の「keyword 単位の巨大 blob」案より部分再利用性が高く、こちらのほうが優れている。

**それでも変わらない点（メモリ懸念は継続）**: page 単位に分割しても、1 検索あたり最大 1,000 件分のデータ総量は変わらない（10 エントリに分散するだけ）。`InMemoryCache` に上限・LRU が無い点（round1 指摘）は `domain_arch` 案でも未解決。実装 Issue に持ち越すべき。

---

### `ux_paging` への応答

争点3 前提条件①「`totalCount` は GitHub の生値を保つ」は私のキャッシュ設計と衝突しない。`totalCount` はキー生成にもキャッシュ判定にも使わない値（`SearchResult` のペイロード内の一データ）なので、raw ページ単位キャッシュ（上記 concession 後の設計）でも usecase が 1 ページ目の `totalCount` をそのまま最終結果へ転記すれば足りる。10 ページの応答間で `total_count` が食い違う可能性（TTL 60 秒内でも GitHub 側の状態変化はありうる）は既存の「キャッシュミス最悪ケースで見積もる」方針の範囲内で無視してよいレベルとみる（`repository-publication-review.md` §7.2 も同じ割り切り）。

---

### `scope_test` への応答

**1. `enforceSearchRateLimit` の修正は `SP-16a` に入れるべき（`SP-16b` へ回すと本番でレート枠を焼く）。**

`SP-16a` の定義（「全ページ取得（打ち切り条件込み）+ 全件キャッシュ + join usecase + gemIndex ソートオプション追加」）は、**まさに multi-page fetch が有効になる境界そのもの**。`enforceSearchRateLimit`（`rate-limit.ts:20`）が `sort` を見ずに「1 リクエスト = 1 消費」で回している限り、`SP-16a` が単独でマージされた瞬間から「1 クライアントが 60 秒間に 60 回 gemIndex 検索 → upstream 最大 600 call/分」の穴が本番に露出する。`SP-16b`（カード表示リッチ化・表示専用の差分）にはこの穴を防ぐ理由が一切無いので、切り分けの基準（表示 vs 挙動）にも合致する形で **`SP-16a` 必須項目**として明記してほしい。

**2. `scope_test` 争点5 の「同時 3 人で枯渇」と私の「2.3 名で頭打ち」は別の 2 つのリスクで、両方とも `SP-16a` の対象。**

`scope_test` の 3 人瞬間バーストの見積り（30 req/分 ÷ 10 call ≒ 3 検索が限界）と、私の継続的同時実利用者モデル（30 ÷ (1.3 検索/分/人 × 10) ≒ 2.3 名）は**近い数値で相互に補強**している（正常利用・複数の異なる利用者による共有枠の枯渇）。これは「D-30 の選択が生む既知の代償」であり、`enforceSearchRateLimit` を直しても消えない（アプリ全体の共有 30 req/分という総量自体は変わらないため）。

一方、私が争点6で指摘したのは**これとは別の穴**: 単一クライアント（1 IP）が悪意・誤操作で連射した場合に、現行の per-IP 自己スロット（60 req/60秒）が **一切歯止めにならない**という構造的欠落。前者（総量の自然な枯渇）は PR 本文への注記で運用回避できる性質のものだが、後者（単一クライアントの連射）は**注記では防げない**（利用者は PR 本文を読まない）。よって `SP-16a` には最低限、`enforceSearchRateLimit` に `sort` を渡し gemIndex 用の別スロット（`wrangler.jsonc` に低い上限のエントリを追加）を持たせる変更を含めるべき、という結論は変えない。

**3. 1,000 件取得のプレビュー環境での現実性**: `scope_test` の見積り（レイテンシ 2〜5 秒・直列実行必須）は妥当と見る。私のレンズからの追加情報は「メカニズムとしては動くが、レート枠は共有総量なので**操作レビュー中に他セッションの試行と鉢合わせると 429 になりうる**」点で、これは `scope_test` 自身が争点5で既に書いている残余リスクと同じ結論。付け加えるとすれば、**`SP-16a` に `enforceSearchRateLimit` の gemIndex 別スロット修正が入っていれば**、少なくとも「PR レビュー中の 1 人の連続操作」が自分自身の枠を食い潰して再現不能になるケースは緩和できる（別スロットの上限を操作レビューの往復回数に見合う値にしておけば）。

### `ux_paging` — 反論
<sub>2026-08-21T10:04:08+09:00</sub>

## `rate_cache` への回答: 「全件取得は `sort=gemIndex` 限定」で挙動差は受け入れられるか

**受け入れられる。数値面（総件数・ページ数）は変わらず、変わるのは応答時間だけであり、それは既に確定仕様の代償として明示済みだから。**

- **総件数**: `D-30①`「件数は変わらない」により `totalCount` は常に GitHub の生値。ソートを切り替えても同じキーワードなら同じ数字が出る。不整合なし。
- **ページ数（上限）**: 自分の round1 分析どおり `maxPageFor(perPage) = floor(1000/perPage)` は GitHub 検索 API 自体の 1,000 件上限に由来する **ソート非依存の定数** であり、`rate_cache` の「gemIndex 選択時だけ 10 call」案でも `lastPage` の計算式は変わらない。ソート切替でページ数表示がガタつくことはない。
- **応答時間**: これが唯一実際に変わる指標（scope_test 見積もりで 2〜5 秒）。ここは受け入れる。理由は 3 つ:
  1. 検索・ソート切替はいずれも `SortPicker` の GET リンクによる **フルページ遷移**（`NFR-3`・クライアント JS なし）であり、gemIndex 以外のソート切替も含め「明示的な操作の直後に新しいページが読み込まれる」体験は元から同じ。応答時間の絶対値が伸びるだけで、体験の *種類* は変わらない。
  2. `AC-8` が要求する「読み込み中の表示」はソート値に関わらず適用される既存要件であり、gemIndex 専用の新しい状態を作る必要がない（実装層＝Suspense/`loading.tsx` かどうかは自分のレンズ外なので `domain_arch`/`scope_test` に委ねる）。
  3. `D-30②` の決定文自体が「素直な挙動を優先し代償は吸収策で緩和する」という前提で確定しているため、応答時間差はスプリントの前提として既に飼い主合意済み。

一方で **UI 側で 1 つだけ追加を推奨する**: `SortPicker` の `gemIndex` 選択肢の近くに 1 行の短い注記（例:「取得に数秒かかることがあります」）を出す。round1 で提案した被覆率の注記と合わせて 1 つの注記に統合してよい。これは新規 UI 文言なので `E-4`（i18n）に従い英語文言も同時用意（実装手段レベルなので確認不要・仮定として記録）。

**却下する代案**: 「gemIndex を既定 sort にする」「常時全件取得にする」はいずれも `rate_cache` の争点1 分析（23 名→2.3 名）で否定済みであり、UX 観点からもこちらから代案を出す必要はない。`rate_cache` 案（gemIndex 選択時限定）を支持する。

---

## `scope_test` への回答: `SP-16a`（最小カード表示）だけで操作レビュー手順 3 を満たせるか

**満たせない。反対する — ただし分割案そのものではなく、`SP-16a` の「最小」の定義に反対する。**

操作レビュー手順 3 の原文（`user-story-map.md` §5.3・round1 で確認済み）:
> 各カードで、なぜ上位なのか（被依存数と star の乖離）がわかる

`scope_test` の `SP-16a` 定義（争点7・1.3 節）は「カード表示は最小（Gem Index の数値 or 簡易バッジのみ）」「乖離の詳しい説明文は次回（`SP-16b`）」としている。ここが問題:

- **Gem Index の数値だけを出すバッジ**（例: 「Gem Index: -1.234」）は、それ単体では「被依存数と star の乖離」を **表していない**。Gem Index は 2 つの順位差から算出された派生スコアであり、生の数字だけを見ても利用者は「なぜ」を読み取れない（式を知っている前提になってしまう）。これは手順 3 の括弧書きが明示的に要求している 2 要素（被依存数・star）が画面上に無いことを意味する。
- 一方、**被依存数（`dependentCount`）+ star（既存フィールド）+ Gem Index の 3 つの生数値を並べて出す**（`daily-digest.tsx` の `dependentLabel`/`starsLabel`/`gemIndexLabel` と同じレイアウトパターンをそのまま流用）だけで、手順 3 は説明文なしで満たせる。利用者は「被依存数が多いのに star が少ない」を数字の比較から読み取れる。**これは "詳しい説明文"（散文的な理由付け）ではなく "生データの並置" であり、`scope_test` が `SP-16b` に想定している「リッチ化」の水準には達していない。**
- コスト面でも問題にならない: `dependentCount` は `scope_test` 自身が `SP-16a` に含めている C（join usecase）で候補プールから取得可能な値（`gem.ts` の `Gem` 型が既に `dependentCount` を持つ）。つまり **join を実装した時点で `dependentCount` はメモリ上に既にある**。それを表示に一行足すだけなので、`SP-16a` の見積もりに実質増分はない。

**結論**: `SP-16a` の「最小カード表示」を「Gem Index の数値のみ」と定義するなら手順 3 を満たせないため反対する。「被依存数 + star + Gem Index の 3 数値を並べる（説明文なし）」へ定義を修正すれば、追加コストほぼゼロで `SP-16a` は手順 3 を満たせるので分割案自体には賛成に回る。1.3 節のデモ説明（`SP-16a` は「手順 3 は簡易表示で満たす」）は「簡易表示 = 3 数値の並置」に明文化してほしい。`SP-16b` に残すのは、それでもなお散文的な説明文やグラフ等の視覚化に踏み込む場合のみ（これは `scope_test` 自身が私への牽制で書いている境界と一致する — 私はグラフ化を提案していない）。

---

## `domain_arch` への回答: Gem Index の UI 表示可否は「仕様解釈の分岐」か

**分岐ではない。すでに `user-story-map.md` §5.3 の操作レビュー手順 3 が表示を明文で要求している。確認不要（`SD-3` 対象外）。**

`domain_arch` は「値オブジェクトについて」節末尾で、「join 結果に Gem Index 値を表示するかは `prd.md` 未読のため仕様解釈の分岐としてオーケストレーターに投げるべき」としているが、round1 で自分が実際に読んだ手順 3 の原文（上記引用）が答えを与えている: **各カードで「なぜ上位か（被依存数と star の乖離）」が分かることは必須の操作レビュー手順であり、任意のオプションではない。**

`SD-3` の発火ラインは「仕様解釈が 2 通り以上あり、選択で成果物が変わるとき」に限定される（`sprint-development-rules.md`）。ここは 2 通りの解釈が存在せず、単に **ドキュメントを読めば分かること** なので、`SD-4`「書いてあることを聞かない」が優先し、確認に回すのは CP-6 違反になる。

したがって `domain_arch` の値オブジェクト設計判断（`RepositorySummary` に `readonly gemIndex: GemIndex | null` を足すか）は **確認待ちにせず前提として確定してよい**。加えて上記 `scope_test` への回答のとおり `dependentCount`（`number | null` 相当）も同じフィールド追加の対象に含めてほしい（gemIndex だけでは手順 3 を満たせないため）。

---

## `scope_test` の E2E 決定論性の穴は、私が提案した表示仕様の検証に影響するか

**直接影響する。`scope_test` の指摘を全面的に支持する。**

自分が round1 で提案した表示仕様（Index ありカードにバッジ、`dependentCount`+star+gemIndex の並置）は、**候補プールと検索スタブが `repositoryFullName` で 1 件も重ならない現状の E2E fixture では検証不能**。既存の `e2e/fixtures/repos.json`（`octostub/*`）だけでテストすると、join 結果は常に「全件 Index なし」になり、バッジが出る分岐そのものが一度も実行されない — つまり手順 3 の E2E 検証は静かにスキップされたまま Green になる（偽陰性ならぬ「偽 Green」）。`scope_test` が 3.2 節で提案する `GEM_DIGEST_SOURCE_PATH` 的な口 + E2E 専用の小さな固定候補プール（`repositoryFullName` をスタブ側と一致させる）は、私の表示仕様が正しく実装されたことを確認する **唯一の経路**なので、この対策を見積もりから外さないよう重ねて要望する。

補足（軽量な代替経路）: E2E とは別に、`RepositoryList` の **コンポーネント単体テスト**（`repository-list.test.tsx` の拡張）でも、`gemIndex`/`dependentCount` を持つ `RepositorySummary` のフェイクを 1 件渡してバッジ描画を検証できる。こちらは E2E の環境変数機構を待たずに Red→Green で先に書けるため、`scope_test` 提案の §2 内側ループ（争点2・TDD の進め方）にステップとして 1 つ足すことを推奨する（E2E の穴を埋める代替ではなく、実装を早める補完）。

### `scope_test` — 反論
<sub>2026-08-21T10:04:39+09:00</sub>

# scope_test（レンズ: スコープとテスト戦略）round2 rebuttal

## 0. 結論から: round1 の判定は維持する。ただし SP-16a/SP-16b の境界線は修正する

**3 レンズ案を合算しても `sp:8`（グレーゾーン・超過リスク高）の判定は変わらない。** ただし内訳が round1 時点の想定から変わった。要点:

- `domain_arch` の「既存 `RepositoryQueryPort.search()` をユースケース内で 10 回ループする」設計は、**キャッシュ・single-flight を無改修で流用できる**ため、`rate_cache` が提案した新キャッシュ名前空間（`search-raw:`）+ 専用 in-flight マップの新設分がまるごと不要になる。これは大きな削減。
- 一方で `rate_cache` の `enforceSearchRateLimit` 欠落指摘は **別 Issue に逃がせない**（後述 §2）。小さいが確実な追加。
- `ux_paging` の反論（バッジに `dependentCount` も要る）は **認める**。round1 で「カード表示は最小限（gemIndex 数値のみ）を `SP-16a` に残し、リッチ化は `SP-16b`」としていたが、これは操作レビュー手順 3 の文言（「被依存数と star の乖離がわかる」）を満たさない。ただし `daily-digest.tsx` の既存パターン流用のため、想定していたほど高くつかない。

差し引きすると **合計実装量は round1 の見積もりからほぼ横ばい**（キャッシュ新設の削減 ≒ バッジ前倒し + レート制限修正の追加）。判定は維持: 「収まるが超過リスクの高いグレーゾーン。縦切り分割案は用意しておく」。

---

## 1. `domain_arch` vs `rate_cache`: キャッシュ層の衝突は `domain_arch` 案の方が実装量が小さい（第三者判定）

`container.ts:78-79` を確認した:

```ts
export function searchRepositoriesUseCase(accessToken?: string | null): SearchRepositories {
  return makeSearchRepositories({ repos: makeCachingRepositoryQuery({ accessToken }) })
}
```

**`makeSearchRepositories` に渡る `deps.repos` は既に `CachingRepositoryQuery`（キャッシュ + single-flight 込み）である。** つまり `domain_arch` が言う「ユースケース内で `deps.repos.search()` を `page=1..10` 分ループする」を素直に実装すると、**10 回の呼び出しそれぞれが既存の `search:v2:kw:page=N:sort=X:per_page=100` キーで自動的にキャッシュされ、既存の `inFlightSearch`（per-page 単位）で single-flight もタダで効く**。新しいキャッシュキー関数も、新しい in-flight マップも、`cached-repository-query.ts` の改修も **一切不要**。

これは `rate_cache` が指摘した「争点2: `search-raw` 名前空間 + 専用 in-flight マップが要る」を丸ごと代替する。しかも副作用として `rate_cache` が争点6の補足で挙げた懸念（「`search-raw` 名前空間には既存 single-flight マップが効かない、ページ番号違いで合流しない」）も **最初から発生しない**: 内部ループが常に固定の内部ページ集合（`per_page=100 固定・page=1..10`）を叩く設計にすれば、利用者が選んだ表示 `page`/`perPage`（20/50/100 の任意組み合わせ）に関わらず、同じキーワードの gemIndex 検索は常に同じ 10 個の内部キャッシュキーへ収束する。表示ページが違っても single-flight は合流する。

**第三者としての判定: `domain_arch` 案（既存ポートをループで再利用）を採用すべき。** 理由は 3 つ:
1. 新規コード量が明確に少ない（`cache-key.ts` / `cached-repository-query.ts` 無改修）
2. `rate_cache` 案より **single-flight の合流粒度が広い**（`rate_cache` 案はキーワード単位の新規 in-flight マップを別途正しく実装する必要があるが、既存流用なら実装ミスの余地自体が無い）
3. `cache-key.ts` の docstring が「生成関数以外でキーを組み立てない」と明記しており、名前空間を増やすたびにこの docstring の対象を広げる設計変更は最小に留めたい（`domain-model.md` §4 の精神）

**ただし懸念点を 1 つ指摘する**: `domain_arch` の実装例コード（round1 コードスニペット）は内部ループで `deps.repos.search(query)` を呼ぶ際に **`query.sort` をそのまま渡す設計に読める**。`query.sort === 'gemIndex'` のまま `GithubRepositoryQuery.search()` に渡ると、`github-repository-query.ts` の `if (query.sort !== 'relevance') { url.searchParams.set('sort', query.sort) ... }` 分岐に引っかかり、**`sort=gemIndex` という無効な値が実際に GitHub API へ送られ 422 相当のエラーになる**（`domain_arch` 自身が「`GithubRepositoryQuery` は無改修」と明言しているにもかかわらず、これは無改修のままでは壊れる）。内部ループ用の `SearchQuery` は `sort` を `'relevance'`（または固定の安全な値）に上書きして構築する必要がある——実装手段レベルの修正で規模には影響しないが、**単体テストで「内部フェッチが `sort=gemIndex` を GitHub 側へ漏らさないこと」を Red→Green で明示的に確認する項目として `§2 の内側 2.3` に追加する**。

**TTL の一貫性について（`rate_cache` 争点2への補足）**: `rate_cache` は「10 call を 1 エントリに集約しないと、TTL 境界で個々のページが別タイミングで失効し combined 結果が不整合になる」と暗に懸念しうるが、`domain_arch` 案採用でもこの懸念は残る（10 回の `cache.get`/`cache.set` は逐次実行なので、フェッチ中に前のページの TTL（60 秒）が切れることは通常の応答時間（数秒）では起きない）。実害はほぼ無いと判断し、これを理由に `rate_cache` 案へ戻す必要はない。

---

## 2. `rate_cache` の争点6（`enforceSearchRateLimit` 欠落）: **`SP-16a` のスコープ内**と判定する（別 Issue にしない）

`CLAUDE.md` `core-principles.md` CP-1 の判定基準:

> 自分がこのタスクで変更したコードパス上の壊れ（自分の変更で落ちたテスト・自分が編集したファイルの参照先が不在・自分が追加した処理が動かない等）は 報告ではなく即修正する

`enforceSearchRateLimit` の「1 検索 = 1 upstream call」という暗黙の前提は、**`SP-16` がまさに壊す前提そのもの**（`sort=gemIndex` を追加した瞬間に 1 検索 = 最大 10 call になる）。これは「無関係な既存の壊れ」ではなく、**このスプリントの変更が直接作り出す壊れ**（sort の選択肢を増やす変更と、レート制限が sort を見ない実装が、同じ PR の中で矛盾を起こす）。放置すると本番で「1 クライアントが upstream 30 req/分の共有枠を 1 人で 20 倍消費できる」実害のある穴を新規に開けたまま出荷することになり、`project-mission.md` の運用継続性（無料枠に収まる・レート制限で破綻しない）という品質ゲートにも反する。**別 Issue へ切り出す判断は採らない。**

**ただしフルスコープの `rate_cache` 提案（新スロット名 + `wrangler.jsonc` エントリ追加 + LRU 上限設計）を全部 `SP-16a` に含める必要はない**、と切り分ける:

- **`SP-16a` に含める（必須・小規模）**: `enforceSearchRateLimit` に `sort`（または内部コスト）を渡せるようにし、`sort === 'gemIndex'` のときは **別スロット・低い上限**で消費する。`app/api/search/route.ts` / `app/[locale]/page.tsx` で `sort` を早期パースする変更、`wrangler.jsonc` へ 1 エントリ追加。いずれも変更箇所は数ファイル・数行単位で、`rate-limit.ts` の既存構造（`WorkersRateLimit.consume(key)`）を壊さない加算的変更。
- **別 Issue へ切り出す（本スプリント外）**: `InMemoryCache` の LRU 上限・メモリ使用量の全体設計。これは `SP-16` 固有の壊れではなく、`SP-5`（キャッシュ導入時）から存在する **既存の設計前提**（軽量な 1 ページ分のみを想定）に対する一般的な指摘であり、`gemIndex` 実装が引き金にはなるが「このタスクで変更したコードパス」そのものではない（境界は 上記 CP-1 の「自分の変更が作ったか」で判定）。1,000 件 × 想定同時キーワード数程度なら実測ベースでは即座に破綻する規模ではなく（`rate_cache` 自身も「要確認」止まりで実測数値を出していない）、`SP-16` の完了条件には含めない。

---

## 3. `ux_paging` の反論（バッジに `dependentCount` が要る）を認め、分割案を修正する

`ux_paging` の指摘は正しい: 操作レビュー手順 3 は「**被依存数と star の乖離**がわかる」と明記しており、`gemIndex` の数値 1 個だけの表示では「乖離」（2 項目の比較）を説明できない。round1 の `SP-16a`（最小カード＝ Index 数値のみ）はこの手順を満たさない。**この点は撤回する。**

**分割案の修正**（`C-1`〜`C-5` を単独スプリントで満たす必要があるため、境界を引き直す）:

**`SP-16a`（1 本目・修正版）**: 全ページ取得（内部ループ・`domain_arch` 案採用・§1）+ join usecase + `gemIndex` ソートオプション + `enforceSearchRateLimit` の sort 別スロット化（§2）+ **`RepositorySummary` への `gemIndex?` / `dependentCount?` optional フィールド追加 + `daily-digest.tsx` のバッジパターンを流用したカード表示**（`ux_paging` 提案どおり。**新規デザインではなく既存パターンの再配線**なので当初懸念していたほど重くない）+ 対応する単体テスト + E2E（操作レビュー手順 1〜6 を **フルカバー**、手順 3 も含む）。

**`SP-16b`（2 本目・縮小）**: `SortPicker` で `gemIndex` を選んだときだけ出る注記文言（「Gem Index は一部のみ算出されています」・`ux_paging` 提案）の追加と i18n 仕上げ、および `dependentRank`/`starRank` の視覚的な比較表現（棒グラフ的な強調など、テキストバッジを超える表現）が要ると判断された場合の拡張。

**この修正により、`SP-16a` 単独で操作レビュー手順 1〜6 が全て通しで確認できる**（`ux_paging` の反論は解消され、分割案は成立する）。`SP-16a` の見積もりは round1 時点より上がる（バッジ + `dependentCount` 配線 + レート制限修正の分）が、§1 のキャッシュ簡素化で相殺されるため、**単独スプリント（分割しない場合の `SP-16` 全体）の合計規模としては round1 判定から大きく動かない**。

---

## 4. 再見積もり（3 レンズ案 + 上記の取捨選択を反映）

| 要素 | round1 見積もり | round2 修正後 |
|---|---|---|
| 全ページ取得ループ | 中 | 中（変わらず。ただし sort 漏れ防止のテスト項目を追加） |
| 全件キャッシュ | 中（新設） | **削除**（既存ポートの流用で不要・§1） |
| join usecase | 中 | 中（変わらず。`domain_arch` 案で「既存ユースケース内分岐」に確定・新規ファイルなし） |
| sort-order 拡張 + 波及 | 小〜中 | 小〜中（変わらず） |
| カード表示（バッジ） | 中（`SP-16b` 送り想定だった） | 小〜中（`SP-16a` へ前倒し。ただし既存パターン流用のため単価は下がる） |
| `enforceSearchRateLimit` の sort 別スロット化 | （round1 では未検討） | **新規・小**（§2） |
| 単体テスト | 中 | 中（対象が増えた分やや増） |
| E2E | 中〜大 | 中〜大（変わらず・§3.2 の候補プール差し替え機構は依然必要） |

**合計判定: round1 と同じく「収まるが超過リスクの高いグレーゾーン」を維持する。** キャッシュ簡素化による削減と、レート制限修正・バッジ前倒しによる追加がほぼ相殺し、正味の変動は小さい。着手セッションは §3 の修正済み `SP-16a`/`SP-16b` 分割を初手から用意しておくことを推奨する（「1 firing で `SD-1` に届かなければ次 firing で分割」の待機ではなく、最初から境界を決めておいた方が手戻りが小さい）。

### `domain_arch` — 反論
<sub>2026-08-21T10:04:49+09:00</sub>

## 1. `scope_test` の `SP-16a`/`SP-16b` 分割: 自分の層構成は `SP-16a` 単体で成立するか

**成立する。中途半端にならない。** 私が round1 で提案した層構成（`search-repositories.ts` の `makeSearchRepositories` に `GemDigestPort` を追加し内部分岐、`composition/container.ts` で束ねる）は、`SP-16a` の要件（全ページ取得 + 全件キャッシュ + join usecase + `gemIndex` ソートオプション追加 + カード表示は最小 + テスト + E2E）のうち **「join usecase」と「ソートオプション追加」の部分をそのまま満たす**。`SP-16b`（カードのリッチ化・レート予算防御強化）へ回すのは表示層（争点4の付随論点で私が挙げた `RepositorySummary` への optional フィールド追加の要否）とレート限定強化のみで、**usecase 層の設計はどちらの分割でも一切変わらない**（`SP-16b` で追加するのは表示用データと防御コードだけで、join のアルゴリズム自体に手を入れない）。分割してもユースケース層が二度書きになったり中間状態で不整合になったりしない設計だと確認できた。

## 2. `scope_test` の過剰実装牽制（domain_arch 名指し）への回答

牽制内容: 「`RepositoryQueryPort` に汎用の全ページ取得抽象メソッドを追加したり、ページネーション自体を再利用可能フレームワークとして設計し直す提案が出たら要注意」。

**該当なし。** round1 で明示的に (B)（`RepositoryQueryPort` の拡張）を却下しており、`RepositoryQueryPort#search` の「1 呼び出し = 1 ページ」契約は一切変更しない前提で設計している。全ページ取得ループは `search-repositories.ts`（usecase 層）の **private ヘルパー関数 1 本**（`export` しない・YAGNI）に閉じており、他の検索経路（`sort=relevance/stars/updated`）や `RepositoryQueryPort` の型そのものには影響しない。牽制の対象にはなっていないことを確認として記録する（concession ではなく合意の明示）。

## 3. `rate_cache` の「keyword 単位の新キャッシュ名前空間（`search-raw:`）」案との整合性

**部分的に反論する。私の層構成では新しい名前空間そのものは不要と考える。**

`rate_cache` の案は「10 call ぶんの生データを 1 キャッシュエントリに集約する」ことが目的だが、それを実現する前提として **usecase が `CachePort` を直接叩く**（または `RepositoryQueryPort` を経由せず生の `GithubRepositoryQuery` を叩く）新しい依存経路が要る。これは usecase の依存が `RepositoryQueryPort` + `GemDigestPort` の2本から `CachePort` 込みの3本に増え、「usecase は手続きに徹しキャッシュ管理をしない」という `W-3` の精神から外れる。

**対案**: 私の round1 のヘルパー（`searchRankedByGemIndex`）は、10 回のループを **既存の `deps.repos.search()`（= composition root で束ねた `CachingRepositoryQuery`）をそのまま呼ぶ**。ただし round1 では見落としていた点を 1 つ修正する（`scope_test` D への回答も兼ねる。§5 参照）: 内部ループが構築する `SearchQuery` は `sort: DEFAULT_SORT_ORDER`（`relevance`。`gemIndex` を GitHub API へ送ってはいけないため）・`perPage: 100`（`parsePerPage(100)`）に固定する。これにより各ページ呼び出しは `cache-key.ts` の **既存の `search:` 名前空間**（`search:v2:{keyword}:page={n}:sort=relevance:per_page=100`）にそのまま乗る。

この設計だと:
- **新しいキー形状・`cache-key.ts` の変更が不要**（`rate_cache` の提案する `search-raw:` 名前空間を作らずに済む）。
- 通常の `relevance` ソートを `per_page=100` で検索した利用者がいれば、**同じキャッシュエントリを再利用できる**（新規名前空間だと得られないメリット）。
- `rate_cache` が争点6の隣で指摘した「既存 `inFlightSearch` は `search-raw` の粒度に効かない」という懸念は、**新しい名前空間を作らない前提では発生しない**。既存の single-flight（`CachingRepositoryQuery` の in-flight マップ）が page 単位でそのまま効く。

**認める点**: この設計は「10 回のキャッシュ読み取り」になる（`rate_cache` の「1 エントリに集約」なら 1 回で済む）。読み取り自体は `InMemoryCache`（素の `Map`）なので待ち時間としては無視できる規模だが、`rate_cache` が争点2で挙げた TTL 再検証・`search-raw` エントリ数上限の議論は、私の対案では「ページ単位で既存 `search:` 名前空間に混ざる」形になるため、**メモリ影響の見積もり（§「キャッシュのメモリ影響」）は名前空間を変えても変えなくても同程度に成立する**（1,000件 = 1〜2MB/keyword という試算は名前空間の粒度に依存しない）。ここは `rate_cache` の見積もりをそのまま採用してよい。

**結論**: 新規名前空間の追加は不要という反論を維持しつつ、TTL・メモリ上限の懸念自体は正当なので実装 Issue に残すべき、という点では合意する。

## 4. `ux_paging` の `RepositorySummary` への optional フィールド追加案

`domain-model.md` §3 は「`RepositorySummary` は検索レスポンス**だけ**で作れる」ことを `RepositoryDetail` との分離基準にしている。候補プール（`GemDigestPort`）はネットワーク往復を伴わない静的 JSON の join なので、この基準（追加 API 呼び出しの有無）には抵触しない。

一方で `domain-model.md` §6 は Search と Gem Index を **別コンテキスト**とし「共通化を急がない」と明言し、§2.2 でも `starCount` と `Gem.stars` の命名衝突を「別コンテキストの同名概念」として **意図的に統合を見送っている**。`RepositorySummary`（Search コンテキストの型）に `gemIndex`/`dependentCount`（Gem Index コンテキストの属性）を直接生やすことは、この既存方針と正面から矛盾する。

ここは **`concession` として別途投稿する**（詳細はそちらを参照）。結論だけ先出しすると: optional `gemIndex` フィールドの追加自体は認めるが、`dependentCount` の追加には反対し、`domain-model.md` §3/§6 に「この 1 フィールドに限りコンテキスト越境を許容する」旨を明記することを条件にする。

## 5. `scope_test` の E2E 決定論性の穴（候補プールと検索スタブが `repositoryFullName` で重ならない）は自分の層構成で解決できるか

**解決できる。むしろ私の層構成の方が `scope_test` の対策案と相性が良い。**

`scope_test` の対策案（`GEM_DIGEST_SOURCE_PATH` で composition root から候補プールの読み込み元を差し替え可能にする）は、私が round1 で提案した配線（`searchRepositoriesUseCase()` にも `gemDigest: new StaticGemDigest()` を composition root から注入する）と **同じ差し替え口を共有できる**。具体的には:

```ts
// src/composition/container.ts
function makeGemDigestPort(): GemDigestPort {
  const overridePath = process.env.GEM_DIGEST_SOURCE_PATH
  return overridePath ? new StaticGemDigest(readJsonSync(overridePath)) : new StaticGemDigest()
}

export function getDailyDigestUseCase(): GetDailyDigest {
  return makeGetDailyDigest({ port: makeGemDigestPort() })
}

export function searchRepositoriesUseCase(accessToken?: string | null): SearchRepositories {
  return makeSearchRepositories({
    repos: makeCachingRepositoryQuery({ accessToken }),
    gemDigest: makeGemDigestPort(),
  })
}
```

`makeGemDigestPort()` を 1 箇所に共通化するだけで、`getDailyDigestUseCase()` と新設の `searchRepositoriesUseCase()` の join の両方が **同一の E2E 専用候補プール**（`repositoryFullName` をスタブ `many-hits`/新規 `gem-index-hits` と一致させたもの）を参照できる。これは round1 で私が「新規 composition ファイル不要、`container.ts` に薄く追加するだけ」と言った設計方針の自然な延長であり、`scope_test` が挙げた決定論性の穴を **usecase 層・composition root の変更だけで**（infrastructure 側や `StaticGemDigest` 自体の変更なしで）解消できる。同意し、実装時にこの共通化を Issue に明記することを提案する。

### `domain_arch` — 譲歩
<sub>2026-08-21T10:04:49+09:00</sub>

## `ux_paging` の `RepositorySummary` optional フィールド案への譲歩

`ux_paging` の「`RepositorySummary` に `gemIndex?: GemIndex` を足し、usecase 層で候補プールと join して埋める」という設計方針そのものは **`gemIndex` フィールド 1 つに限り採用する**。理由:

- カード表示で「なぜ上位か」を示す要件（操作レビュー手順3・`scope_test` の `SP-16a` 最小構成でも「Gem Index の数値 or 簡易バッジ」は残る）がある以上、**join の結果（Gem Index 値そのもの）を UI まで運ぶ経路がどこかに必要**で、`SearchRepositories` の入出力契約（`SearchRepositoriesInput -> SearchResult`）を変えない私の round1 方針と両立させるには、`SearchResult.items`（＝ `RepositorySummary[]`）にフィールドを足す以外の現実的な経路がない。
- `domain-model.md` §3 の「`RepositorySummary` は追加 API 呼び出しなしで作れる」という分離基準には抵触しない（候補プールは静的 JSON でネットワーク往復を伴わない）。

**ただし 2 点、条件を付けて一部は譲らない**:

1. **`dependentCount` は追加しない**。`ux_paging` は「なぜ上位か（被依存数と star の乖離）」の説明に `stars`（既存）と `dependentCount`（新規）の両方が要るとしているが、`gemIndex` 値自体が両者の差分を既に集約した指標であり、`stars`（既存フィールド）+ `gemIndex`（新規1フィールド）だけで「差が大きいほど過小評価」という説明は成立する。`dependentCount` の生値まで `RepositorySummary` へ持ち込むのは Gem Index コンテキストの属性をさらに 1 つ Search コンテキストへ漏らすことになり、`domain-model.md` §6（「共通化を急がない」）への抵触を最小限に留めるため、**最初の実装では見送り、UI 文言で不足と判明したら別途追加を検討**する（`SP-16b` 相当・YAGNI）。
2. **`domain-model.md` の更新を同じ PR の必須項目にする**。§3 の「`RepositorySummary` は検索レスポンスだけで作れる」という記述の直後に、「`gemIndex`（`GemIndex | undefined`）のみ例外的に Gem Index コンテキストの候補プールから注入する。`dependentCount` 等の他属性は持ち込まない」旨を追記し、§6 の「共通化を急がない」原則に対する **意図的でスコープを限定した例外**であることを明記する（§2.2 が `starCount`/`Gem.stars` の衝突を「別コンテキストの同名概念」として記録しているのと同じ扱い方で、今回は「1 フィールドだけ越境させた」という決定を残す）。これを書かずに実装だけ進めると、次にこのファイルを読む人が「いつの間にか2コンテキストが混ざっている」と誤読する。

以上の条件（`gemIndex` のみ・`domain-model.md` 更新を伴う）で `ux_paging` の設計方針に同意する。

## ラウンド 3

### `lead` — 合意
<sub>2026-08-21T10:06:57+09:00</sub>

## 合意点（4 レンズが一致した事項）

1. **join の層**: `search-repositories.ts` の `makeSearchRepositories` に `GemDigestPort` を追加し、内部で `sort === 'gemIndex'` を分岐する。`RepositoryQueryPort` の「1 呼び出し = 1 ページ」契約は**変更しない**。全ページ取得ループは usecase 層の private ヘルパー 1 本に閉じる（`export` しない・YAGNI）。`scope_test` が第三者判定でこの案を「実装量が最小」と評価し、`rate_cache` も新名前空間案を撤回した。

2. **キャッシュは新設不要**（`rate_cache` の concession）。内部ループが `sort: 'relevance'` / `perPage: 100` に固定した**内部 `SearchQuery`** を組み立てて既存の `deps.repos.search()`（= composition root で束ねた `CachingRepositoryQuery`）を呼べば、既存の `search:v2:{keyword}:page={n}:sort=relevance:per_page=100` キーにそのまま乗る。`cache-key.ts` / `cached-repository-query.ts` は無改修。`CACHE_SCHEMA_VERSION` のバンプも不要。既存の `inFlightSearch` による single-flight もページ単位でそのまま効く。**副次効果**: 通常の relevance 検索（`per_page=100`）とキャッシュエントリを共有できる。

3. 🔴 **`sort='gemIndex'` を GitHub API へ漏らしてはならない**（3 レンズが独立に指摘）。`github-repository-query.ts` は `sort !== 'relevance'` なら値をそのまま `url.searchParams` に載せるため、無改修のままだと無効な `sort=gemIndex` が送られて 422 相当になる。内部ループ用 `SearchQuery` の `sort` を `relevance` に上書きすることが**必須**。

4. **全件取得は `sort=gemIndex` 選択時のみ**（常時化しない）。`rate_cache` の試算では、常時化すると upstream 30 req/分の枠で耐えられる同時実利用者が **23 名 → 2.3 名**まで劣化する。`ux_paging` は「総件数・ページ数は不変で応答時間だけが変わる」ため UX 上受け入れ可能と判定した。

5. **ページは取得済み配列のスライス**にする。`AC-6` は純粋に URL 契約の話なので影響を受けない。`AC-7` の二層境界（`page-number.ts` の固定上限と `maxPageFor`）もローカルスライスと自然に整合する。**前提条件**: `totalCount` は GitHub の生値を保つこと、スライス式を既存のページング計算と揃えること。UI コンポーネント（`Pagination` / `SortPicker`）は**無改修**で済む。

6. **Index を持たない結果同士は relevance 順を安定ソートで維持する**（`ux_paging` の主担当判定）。

7. **`enforceSearchRateLimit` の欠落は `SP-16` のスコープ内**（`rate_cache` が発見・`scope_test` が判定）。`rate-limit.ts` は `sort` を見ておらず、1 検索 = 最大 10 upstream call になることを数えられない。これは「無関係な既存の壊れ」ではなく **`SP-16` 自身が作り出す壊れ**（`CP-1` の判定基準「自分の変更が作ったか」に該当）なので、別 Issue に逃がさず本スプリントで直す。

8. **E2E の決定論性**: 候補プール（227 件）と検索スタブが `repositoryFullName` で重ならないと、Gem Index 付きの結果が 1 件も出ず操作レビューを検証できない。`container.ts` に共通の `makeGemDigestPort()` を切り出し、環境変数で候補プールの読み込み元を差し替えられるようにする（`getDailyDigestUseCase()` と検索経路の両方が同じ差し替え口を共有する）。

## 対立点と lead 裁定

### 🔴 カードに `dependentCount`（被依存数）を出すか

- **`ux_paging`**: 出すべき。`gemIndex` 値だけでは「被依存数と star の乖離」を示せず、操作レビュー手順 3 を満たさない。日次ダイジェストの既存パターン流用なので追加コストはほぼゼロ
- **`domain_arch`**: 出さない。`gemIndex` が既に両者の差分を集約した指標であり `stars`（既存）+ `gemIndex`（新規 1 フィールド）で説明は成立する。`dependentCount` まで持ち込むと Gem Index コンテキストの属性をさらに Search コンテキストへ漏らすことになり `domain-model.md` §6（共通化を急がない）への抵触が増える

**裁定: `ux_paging` を採る（`dependentCount` も出す）。** 根拠:

1. **仕様の文言が正本**（`SD-4` の権威順: 仕様 > テスト > 現行コード）。`user-story-map.md` §5.3 の操作レビュー手順 3 は「**被依存数と star の乖離**がわかる」と明示している。被依存数を出さずにこの手順を「完走できた」とは言えない
2. `gemIndex` は `-6.734〜0.003` という**無次元の値**で、単体では利用者に意味が伝わらない。「被依存数は上位なのに star は下位」という具体が並んで初めて「なぜ上位か」が伝わる
3. 日次ダイジェストが既に同じ 3 数値を並べており、**表示パターンを再利用できる**（`ux_paging` が実コードで確認済み）

**ただし `domain_arch` の懸念は正当なので条件を付ける**: `domain-model.md` §3 / §6 に「`RepositorySummary` には `gemIndex` と `dependentCount` の 2 フィールドに限り Gem Index コンテキストから注入する。他の属性は持ち込まない」旨を**同じ PR で明記する**（`§2.2` が `starCount` / `Gem.stars` の衝突を記録しているのと同じ扱い）。これを書かずに実装だけ進めると、次に読む人が「いつの間にか 2 コンテキストが混ざっている」と誤読する。

### 分割するか（`scope_test` の `SP-16a` / `SP-16b`）

**裁定: 分割せず 1 本で着手する。** `scope_test` の判定は「収まるがグレーゾーン」であって「超える」ではなく、キャッシュ新設が不要になった分の削減が、バッジ前倒しとレート制限修正の追加とほぼ相殺している。ただし **`SP-14` と同じ規則を適用**する: 3 回の firing を跨いでも `SD-1`（プレビュー URL で操作レビュー完走）に到達しない場合は、`scope_test` の分割案（`SP-16a` = 検索 → 並べ替え → 詳細 → 復帰が完走できる最小 / `SP-16b` = 表示のリッチ化とレート防御の強化）へ縦切りで分割する。

### `InMemoryCache` の LRU 上限・メモリ全体設計

**裁定: 別 Issue**（`scope_test` の切り分けを採用）。これは `SP-5`（キャッシュ導入）から存在する既存の設計前提に対する一般的な指摘であり、`SP-16` が引き金にはなるが「このタスクで変更したコードパス」そのものではない（`CP-1` の境界線）。

## 確認不要と確定した論点

`domain_arch` が「join 結果の Gem Index 値を UI 表示するかは仕様解釈の分岐点ではないか」と提起したが、**`ux_paging` の回答どおり操作レビュー手順 3 が既に表示を要求しており、仕様として確定済み**。`SD-3` 第 2 系統の確認は発火しない。

### `lead` — 判定
<sub>2026-08-21T10:08:06+09:00</sub>

{
  "decisions": [
    {
      "issue": "争点 4: 検索結果 × 候補プールの join をどの層で行うか",
      "design": "usecase 層で行う。src/usecases/search-repositories.ts の makeSearchRepositories の deps に GemDigestPort を追加し、内部で sort === 'gemIndex' を分岐する。全ページ取得と join は同ファイル内の private ヘルパー 1 本に閉じる（export しない）。RepositoryQueryPort の『1 呼び出し = 1 ページ』契約は変更しない。ドメインサービス（domain/services/）は I/O を持てないため採らない。",
      "evidence": ["ARCH-1〜ARCH-7（architecture-rules.md）", "domain-model.md §3 / §6", "container.ts:78-79 の既存配線"],
      "artifacts": ["src/usecases/search-repositories.ts（改修）", "src/composition/container.ts（改修）"],
      "rejected": "(B) RepositoryQueryPort の拡張 = ポート面積が広がりコンテキストが混在する。(C) ドメインサービス = ドメイン層が I/O を持てず domain/services/ 廃止方針とも矛盾する。"
    },
    {
      "issue": "争点 1: 最大 1,000 件の取得をいつ発火させるか",
      "design": "sort === 'gemIndex' を選んだときだけ発火させる。他のソート（relevance / stars / updated）は従来どおり単一ページ取得のまま変えない。分岐は usecase 層に置く（インフラの実装詳細にしない）。",
      "evidence": ["NFR-5", "rate_cache の試算: 常時化すると upstream 30 req/分の枠で耐えられる同時実利用者が 23 名 → 2.3 名へ劣化"],
      "artifacts": ["src/usecases/search-repositories.ts（改修）"],
      "rejected": "常時 1,000 件取得 = レート予算を 10 倍消費し、Gem Index を使わない大多数の検索まで巻き込む。"
    },
    {
      "issue": "争点 2: 全件取得結果のキャッシュキー粒度",
      "design": "新しい名前空間を作らない。内部ループが sort: 'relevance' / perPage: 100 に固定した内部 SearchQuery を組み立てて既存の deps.repos.search() を呼ぶことで、既存の search:v2:{keyword}:page={n}:sort=relevance:per_page=100 キーにそのまま乗せる。cache-key.ts / cached-repository-query.ts は無改修。CACHE_SCHEMA_VERSION のバンプも不要。既存の inFlightSearch による single-flight がページ単位でそのまま効く。",
      "evidence": ["ADR 0005", "cached-repository-query.ts の readThrough / inFlightSearch", "cache-key.ts の docstring（生成関数以外でキーを組み立てない）"],
      "artifacts": ["（新規ファイルなし・既存キー体系を再利用）"],
      "rejected": "keyword 単位の新名前空間 search-raw: = usecase が CachePort を直接叩く新依存が要り『usecase はキャッシュ管理をしない』方針から外れる。既存 single-flight も効かなくなる。rate_cache 自身が round 2 で撤回した。"
    },
    {
      "issue": "争点 2 の実装上の必須注意（3 レンズが独立に指摘）",
      "design": "内部ループ用 SearchQuery の sort を必ず 'relevance' に上書きする。github-repository-query.ts は sort !== 'relevance' の値をそのまま url.searchParams へ載せるため、sort='gemIndex' のまま渡すと無効なパラメータが GitHub API へ送られ 422 相当になる。単体テストで『内部フェッチが sort=gemIndex を GitHub 側へ漏らさないこと』を Red → Green で明示的に確認する。",
      "evidence": ["github-repository-query.ts:55-58 の分岐"],
      "artifacts": ["src/usecases/search-repositories.ts（改修）", "src/usecases/search-repositories.test.ts（テスト追加）"],
      "rejected": "GithubRepositoryQuery 側で gemIndex を無視する防御を入れる案 = 無効値の知識をインフラ層へ漏らすため採らない。"
    },
    {
      "issue": "争点 3: gemIndex ソート時の『ページ』の意味と AC-6 / AC-7 の整合",
      "design": "取得済み配列のスライスにする。AC-6 は URL 契約の話なのでスライス方式の影響を受けない。AC-7 の二層境界（page-number.ts の固定上限と pagination.tsx の maxPageFor）もローカルスライスと整合する。前提条件は 2 つ: (1) totalCount は GitHub の生値を保つ (2) スライス式を既存のページング計算と揃える。UI コンポーネント（Pagination / SortPicker）は無改修。",
      "evidence": ["AC-6 / AC-7（prd.md §6）", "page-number.ts / per-page.ts の既存境界ロジック"],
      "artifacts": ["src/usecases/search-repositories.ts（改修）"],
      "rejected": "ページごとに GitHub API を再クエリする案 = 全件ソートの意味をなさない。"
    },
    {
      "issue": "争点 5: Gem Index を持たない結果同士の内部順序",
      "design": "元の relevance 順を安定ソートで維持する。Index を持つ群を先頭に、持たない群を末尾に置き、群内の相対順序は取得順のまま変えない。",
      "evidence": ["D-30 ①（末尾に残す・件数不変）", "ux_paging の主担当判定"],
      "artifacts": ["src/usecases/search-repositories.ts（改修）"],
      "rejected": "Index なし群を star 順などで並べ替える案 = 利用者が選んだソート軸と無関係な順序が混ざり説明できない。"
    },
    {
      "issue": "争点 6: NFR-5 のレート予算の守り方",
      "design": "SP-16 のスコープ内で必須修正とする（別 Issue にしない）。enforceSearchRateLimit に sort（または内部コスト）を渡せるようにし、sort === 'gemIndex' のときは別スロット・低い上限で消費する。sort の早期パースを呼び出し側（app/api/search/route.ts / app/[locale]/page.tsx）へ入れ、wrangler.jsonc に rate limiter エントリを 1 つ追加する。rate-limit.ts の既存構造（WorkersRateLimit.consume(key)）は壊さない加算的変更に留める。",
      "evidence": ["rate-limit.ts:20 が sort を見ておらず 1 検索 = 最大 10 upstream call を数えられない（rate_cache の発見）", "CP-1 の判定基準『自分の変更が作った壊れか』= SP-16 自身が 1 検索 = 1 call の前提を壊す", "project-mission.md の品質ゲート（レート制限で破綻しない）"],
      "artifacts": ["src/infrastructure/platform/rate-limit.ts（改修）", "app/api/search/route.ts（改修）", "app/[locale]/page.tsx（改修）", "wrangler.jsonc（改修）"],
      "rejected": "別 Issue へ切り出す案 = 単一クライアントが共有枠を 20 倍消費できる穴を新規に開けたまま出荷することになる。PR の注記では防げない。"
    },
    {
      "issue": "カード表示（操作レビュー手順 3）— lead 裁定を要した対立",
      "design": "被依存数・star・Gem Index の 3 数値を並置する。RepositorySummary に optional な gemIndex と dependentCount を追加し、usecase の join で埋める。表示は日次ダイジェストの既存パターン（dependentLabel / starsLabel / gemIndexLabel）を再利用する。🔴 条件: domain-model.md §3 / §6 に『RepositorySummary には gemIndex と dependentCount の 2 フィールドに限り Gem Index コンテキストから注入する。他の属性は持ち込まない』旨を同じ PR で明記する。",
      "evidence": ["user-story-map.md §5.3 SP-16 の操作レビュー手順 3『被依存数と star の乖離がわかる』（SD-4 の権威順で仕様が正本）", "gemIndex は -6.734〜0.003 の無次元値で単体では意味が伝わらない", "日次ダイジェストに同じ 3 数値の表示前例がある"],
      "artifacts": ["src/domain/model/repository-summary.ts（改修）", "src/ui/（カード表示の改修）", "docs/03_design/data-model/domain-model.md §3 / §6（改修・必須）"],
      "rejected": "domain_arch の『gemIndex 1 フィールドのみ・dependentCount は見送る』案 = 操作レビュー手順 3 の文言（被依存数と star の乖離）を満たせない。ただし同案が挙げたコンテキスト越境の懸念は正当なので、domain-model.md への例外明記を条件として採り入れた。"
    },
    {
      "issue": "E2E の決定論性",
      "design": "container.ts に共通の makeGemDigestPort() を切り出し、環境変数で候補プールの読み込み元を差し替えられるようにする。getDailyDigestUseCase() と検索経路の両方が同じ差し替え口を共有する。E2E では検索スタブの repositoryFullName と重なる候補プールを注入し、Gem Index 付きの結果が必ず出る状態を作る。",
      "evidence": ["候補プールは 227 リポジトリしかなく、スタブと重ならないと Gem Index 付きの結果が 0 件になる（scope_test の発見）", "NFR-24（外部 API は必ずモック化する）"],
      "artifacts": ["src/composition/container.ts（改修）", "e2e/sp-16.spec.ts（新規）"],
      "rejected": "実 API と実候補プールで E2E を回す案 = 1,000 件取得を実行することになりレート枠を消費し、結果も非決定論的になる。"
    },
    {
      "issue": "争点 7: sp:8 に収まるか / 分割の要否",
      "design": "分割せず 1 本で着手する。キャッシュ新設が不要になった分の削減が、カード表示の前倒しとレート制限修正の追加とほぼ相殺している。ただし SP-14 と同じ規則を適用し、3 回の firing を跨いでも SD-1（プレビュー URL で操作レビュー完走）に到達しない場合は縦切りで分割する: SP-16a = 検索 → 並べ替え → 詳細 → 復帰が完走できる最小 / SP-16b = 表示のリッチ化とレート防御の強化。",
      "evidence": ["scope_test の判定『収まるがグレーゾーン・超過リスク高』", "user-story-map.md §5.3 SP-14 の分割規則", "C-5（技術レイヤー分割は採らない）"],
      "artifacts": ["（分割時のみ user-story-map.md §5.3 を改修）"],
      "rejected": "最初から分割する案 = 現時点の見積もりでは分割の必要が確定しておらず、先回りで 2 スプリントに割ると SP-16a 単体のレビュー価値が薄くなる。"
    }
  ],
  "split": {
    "needed": "false",
    "plan": "1 本で着手する。3 回の firing を跨いでも SD-1 に到達しない場合のみ SP-16a（最小の完走経路）/ SP-16b（表示のリッチ化とレート防御の強化）へ縦切りで分割する。"
  },
  "critical": [
    "内部ループ用 SearchQuery の sort を 'relevance' に上書きしないと、無効な sort=gemIndex が GitHub API へ送られて 422 相当になる（github-repository-query.ts:55-58 が値を素通しするため）。単体テストで漏れないことを明示的に確認すること",
    "enforceSearchRateLimit（rate-limit.ts:20）が sort を見ておらず 1 検索 = 最大 10 upstream call を数えられない。修正せずに出荷すると単一クライアントが共有枠を 20 倍消費できる穴が開く",
    "E2E で候補プール（227 件）と検索スタブが repositoryFullName で重ならないと Gem Index 付きの結果が 0 件になり、操作レビュー手順を検証できない。composition root に差し替え口が要る"
  ],
  "open_questions": []
}
