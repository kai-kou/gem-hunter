import type { CacheKey } from '../../domain/ports/cache-port'
import type { SearchQuery } from '../../domain/model/search-query'

export type { CacheKey } from '../../domain/ports/cache-port'

/**
 * キャッシュキーの命名規約（NFR-18）。
 * - 検索結果と単一リポジトリで名前空間を分ける（`search:` / `repository:`）
 * - 名前空間の直後にキャッシュスキーマバージョンを置く（`CACHE_SCHEMA_VERSION`）
 * - 利用者識別子を含めない
 * - 前後空白・大文字小文字を正規化する
 *
 * 🔴 生成関数（本ファイル）以外でキーを組み立てない（domain-model.md §4）。
 * `CacheKey` 型自体は `src/domain/ports/cache-port.ts` が定義する（`CachePort` の
 * 引数として型で強制するため・Issue #89）。ここでは生成関数のみを持つ。
 */
const NAMESPACE_SEARCH = 'search'
const NAMESPACE_REPOSITORY = 'repository'
const NAMESPACE_README = 'readme'
const NAMESPACE_REPOSITORY_ETAG = 'repository-etag'
const NAMESPACE_README_ETAG = 'readme-etag'

/**
 * キャッシュスキーマバージョン（全キャッシュキーの共通セグメント）。
 *
 * 🔴 **キャッシュ値の「意味」が変わる変更をしたら、必ずこの定数を上げること。**
 * 対象は「取得範囲・フィルタ条件・レスポンスのマッピング」の変更。
 * キーの構成要素（キーワード・ページ・ソート順・表示件数）が同じままでも、
 * 同じキーに対して返るべき値の内容が変われば bump が必要。
 *
 * なぜ必要か（Issue #142）: キーが検索条件だけで構成されていると、修正をデプロイしても
 * **古い意味の値が入ったキャッシュエントリが TTL 切れまでヒットし続ける**。契機は
 * リポジトリオーナー（ユーザー）からの「自分のプライベートリポジトリが検索対象になっている」
 * という報告で、それを受けて installation token の可視範囲を調査・修正した
 * （⚠️ こちら側で API 応答を採取して混入を実測した記録は無い・`docs/adr/0003-github-app-authentication.md` §5.4）。
 * 可視範囲を絞る修正だけでは、修正前の意味で書かれた結果が返り続ける期間が残る。
 * バージョンを上げれば全キーが別物になり、既存エントリを一括で論理的に無効化できる
 * （明示的なパージ不要）。
 *
 * - `v1`: 欠番。バージョンセグメント導入前のキーはこのセグメント自体を持たなかったため、
 *   `v1` を含むキーは一度も生成されていない（`domain-model.md` §4）
 * - `v2`: 検索を public リポジトリ限定（`is:public`）にしたことで、同じ検索条件に対する
 *   結果の意味（含まれるリポジトリの範囲）が変わったため引き上げ（Issue #142）
 *
 * 🔴 **可視範囲・ACL に関わる是正をデプロイするときは必ず bump する（PR #874 以降は必須）**:
 * 2 段目に Cloudflare Cache API を重ねた（`workers-cache.ts` / `ADR 0016`）ため、
 * **キャッシュエントリはデプロイを跨いで生き残る**。旧挙動（isolate 内メモリのみ）では
 * 新しい isolate が空の `Map` で起動するのでデプロイが事実上のパージとして働いていたが、
 * その暗黙の安全網はもう無い。可視範囲を絞る修正をデプロイしても、**本定数を上げない限り
 * 旧い意味で書かれた値が TTL 切れまで返り続ける**（Issue #142 と同じ事象が、より長く続く）。
 */
export const CACHE_SCHEMA_VERSION = 'v2'

function normalizeSegment(segment: string): string {
  return encodeURIComponent(segment.normalize('NFC').trim().toLowerCase())
}

/**
 * 検索結果のキャッシュキー（スキーマバージョン + クエリ + ページ + ソート順 + 表示件数）。
 * ソート順（AR-2）・表示件数（AR-3）はキャッシュ断片化を招くため構成要素に含める（domain-model.md §4）。
 */
export function searchResultCacheKey(query: SearchQuery): CacheKey {
  return `${NAMESPACE_SEARCH}:${CACHE_SCHEMA_VERSION}:${normalizeSegment(query.keyword)}:page=${query.page}:sort=${query.sort}:per_page=${query.perPage}` as CacheKey
}

/** 単一リポジトリのキャッシュキー（スキーマバージョン + owner/name）。 */
export function repositoryCacheKey(owner: string, name: string): CacheKey {
  return `${NAMESPACE_REPOSITORY}:${CACHE_SCHEMA_VERSION}:${normalizeSegment(owner)}/${normalizeSegment(name)}` as CacheKey
}

/**
 * README のキャッシュキー（スキーマバージョン + owner/name）。単一リポジトリ（`repository:`）とは
 * 別の名前空間にする（Issue #334 F-4・whiteboard round3 裁定）。**未サニタイズの生 HTML** を
 * キャッシュする値として使う（表示都合のサニタイズはキャッシュ層の外・`src/ui/` 側の責務）。
 */
export function readmeCacheKey(owner: string, name: string): CacheKey {
  return `${NAMESPACE_README}:${CACHE_SCHEMA_VERSION}:${normalizeSegment(owner)}/${normalizeSegment(name)}` as CacheKey
}

/**
 * `GET /repos/{owner}/{repo}` の条件付きリクエスト（`If-None-Match` / ETag）用エントリのキー。
 * 本文キャッシュ（`repositoryCacheKey`）とは **別の名前空間** にする（Issue #170）。
 * 本文キャッシュは「マッピング済みドメイン値」を TTL 保持するのに対し、こちらは
 * 「上流の生レスポンス + ETag」を保持し、本文 TTL 切れ後の再検証（primary rate limit の節約）
 * に使う。同じキーにすると片方の書き込みがもう片方を破壊するため、必ず分ける。
 */
export function repositoryEtagCacheKey(owner: string, name: string): CacheKey {
  return `${NAMESPACE_REPOSITORY_ETAG}:${CACHE_SCHEMA_VERSION}:${normalizeSegment(owner)}/${normalizeSegment(name)}` as CacheKey
}

/**
 * `GET /repos/{owner}/{repo}/readme` の条件付きリクエスト用エントリのキー。
 * `readmeCacheKey`（本文 TTL キャッシュ）とは別の名前空間にする（`repositoryEtagCacheKey` と同じ理由）。
 */
export function readmeEtagCacheKey(owner: string, name: string): CacheKey {
  return `${NAMESPACE_README_ETAG}:${CACHE_SCHEMA_VERSION}:${normalizeSegment(owner)}/${normalizeSegment(name)}` as CacheKey
}
