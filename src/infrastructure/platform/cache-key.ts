import type { SearchQuery } from '../../domain/model/search-query'

/**
 * キャッシュキーの命名規約（NFR-18）。
 * - 検索結果と単一リポジトリで名前空間を分ける（`search:` / `repository:`）
 * - 利用者識別子を含めない
 * - 前後空白・大文字小文字を正規化する
 *
 * 🔴 生成関数（本ファイル）以外でキーを組み立てない（domain-model.md §4）。
 */
const NAMESPACE_SEARCH = 'search'
const NAMESPACE_REPOSITORY = 'repository'

declare const brand: unique symbol

/** 名前空間つき・正規化済みのキャッシュキー。 */
export type CacheKey = string & { readonly [brand]: 'CacheKey' }

function normalizeSegment(segment: string): string {
  return encodeURIComponent(segment.normalize('NFC').trim().toLowerCase())
}

/**
 * 検索結果のキャッシュキー（クエリ + ページ + ソート順 + 表示件数）。
 * ソート順（AR-2）・表示件数（AR-3）はキャッシュ断片化を招くため構成要素に含める（domain-model.md §4）。
 */
export function searchResultCacheKey(query: SearchQuery): CacheKey {
  return `${NAMESPACE_SEARCH}:${normalizeSegment(query.keyword)}:page=${query.page}:sort=${query.sort}:per_page=${query.perPage}` as CacheKey
}

/** 単一リポジトリのキャッシュキー（owner/name）。 */
export function repositoryCacheKey(owner: string, name: string): CacheKey {
  return `${NAMESPACE_REPOSITORY}:${normalizeSegment(owner)}/${normalizeSegment(name)}` as CacheKey
}
