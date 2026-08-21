import type { GemIndex } from '../domain/model/gem-index'
import { gemIndexValue } from '../domain/model/gem-index'
import { maxPageFor, pageNumber } from '../domain/model/page-number'
import { type PerPage, parse as parsePerPage } from '../domain/model/per-page'
import type { RepositorySummary, SearchResult } from '../domain/model/repository'
import { searchQuery, type SearchQuery } from '../domain/model/search-query'
import { DEFAULT_SORT_ORDER } from '../domain/model/sort-order'
import type { GemDigestPort } from '../domain/ports/gem-digest-port'
import type { RepositoryQueryPort } from '../domain/ports/repository-query-port'

export type SearchRepositoriesInput = {
  keyword: string
  page?: number
  sort?: string
  perPage?: number
}

export type SearchRepositories = (input: SearchRepositoriesInput) => Promise<SearchResult>

/**
 * 内部の全件取得（`sort=gemIndex` 専用）が使う raw fetch のページサイズ（GitHub 検索 API 上限）。
 * 表示側の `PerPage`（20/50/100・`AR-3`）とは無関係の固定値（`SP-16` whiteboard round1 `rate_cache`）。
 */
const RAW_PER_PAGE: PerPage = parsePerPage(100)

/**
 * raw fetch の最大ページ数。`page-number.ts` の 1,000 件上限（`API_RESULT_LIMIT`）を
 * `maxPageFor()` 経由で共有する（マジックナンバーの重複を避ける・`D-30②`）。
 */
const RAW_MAX_PAGES = maxPageFor(RAW_PER_PAGE)

/** キーワードでリポジトリを検索する（US-6・`SP-16` で `sort=gemIndex` を追加）。 */
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

/**
 * `sort=gemIndex` 専用の経路（`SP-16` / `D-30`）。
 *
 * 1. 最大 1,000 件（`per_page=100` × 最大 10 ページ）を **直列**に取得する
 *    （公式が並行実行を非推奨としているため・whiteboard round1 `scope_test` 争点5）。
 * 2. 取得結果を Gem Index 候補プール（`GemDigestPort`）と `fullName` で突合する。
 * 3. Index を持つ結果を Gem Index 昇順（値が小さいほど過小評価度が高い）で並べ、
 *    Index を持たない結果は絞り込まずに末尾へ残す。持たない結果同士は取得順（relevance）を保つ。
 * 4. 並べ替え後の配列から、利用者が指定した `page`/`perPage` の範囲を切り出す
 *    （`totalCount` は GitHub の生値のまま・スライスで置き換えない）。
 */
async function searchRankedByGemIndex(
  query: SearchQuery,
  deps: { repos: RepositoryQueryPort; gemDigest: GemDigestPort },
): Promise<SearchResult> {
  const [{ items, totalCount, incompleteResults }, { candidates }] = await Promise.all([
    fetchUpToApiLimit(query, deps.repos),
    deps.gemDigest.listCandidates(),
  ])

  const candidateByFullName = new Map(
    candidates.map((candidate) => [candidate.repositoryFullName.toLowerCase(), candidate]),
  )

  const joined: RepositorySummary[] = items.map((item) => {
    const candidate = candidateByFullName.get(item.fullName.toLowerCase())
    return candidate === undefined
      ? item
      : { ...item, gemIndex: candidate.gemIndex, dependentCount: candidate.dependentCount }
  })

  // D-30①: 絞り込まない。Index あり群を先頭に、Index なし群を末尾に残す（2 段階パーティション）。
  const withIndex = joined.filter(hasGemIndex)
  const withoutIndex = joined.filter((item) => !hasGemIndex(item))
  withIndex.sort((a, b) => gemIndexValue(b.gemIndex) - gemIndexValue(a.gemIndex))
  const ranked = [...withIndex, ...withoutIndex]

  // gemIndex ソートの「ページ」は取得済み配列のスライス（whiteboard round3 決定 5）。
  const start = (query.page - 1) * query.perPage
  const pageItems = ranked.slice(start, start + query.perPage)

  return { totalCount, incompleteResults, items: pageItems }
}

function hasGemIndex(
  item: RepositorySummary,
): item is RepositorySummary & { gemIndex: GemIndex } {
  return item.gemIndex !== undefined
}

/**
 * `per_page=100` で最大 `RAW_MAX_PAGES`（10）ページを直列取得する。
 *
 * 🔴 **critical**: ここで組み立てる内部 `SearchQuery` の `sort` は必ず `DEFAULT_SORT_ORDER`
 * （`relevance`）に固定する。`query.sort`（`'gemIndex'`）をそのまま渡すと
 * `GithubRepositoryQuery.search()` が `url.searchParams.set('sort', 'gemIndex')` して
 * 無効な値を GitHub API へ送ってしまう（422 相当・whiteboard round3 決定・critical）。
 * `perPage` も `RAW_PER_PAGE`（100）に固定することで、既存の
 * `search:v2:{keyword}:page={n}:sort=relevance:per_page=100` キャッシュキーにそのまま乗る
 * （`cache-key.ts` / `cached-repository-query.ts` は無改修・whiteboard round3 決定 2）。
 */
async function fetchUpToApiLimit(
  query: SearchQuery,
  repos: RepositoryQueryPort,
): Promise<{ items: RepositorySummary[]; totalCount: number; incompleteResults: boolean }> {
  const items: RepositorySummary[] = []
  let totalCount = 0
  let incompleteResults = false

  for (let page = 1; page <= RAW_MAX_PAGES; page += 1) {
    const rawQuery: SearchQuery = {
      keyword: query.keyword,
      page: pageNumber(page),
      sort: DEFAULT_SORT_ORDER,
      perPage: RAW_PER_PAGE,
    }
    const result = await repos.search(rawQuery)

    if (page === 1) {
      totalCount = result.totalCount
    }
    incompleteResults = incompleteResults || result.incompleteResults
    items.push(...result.items)

    if (result.items.length < RAW_PER_PAGE) {
      break // GitHub 側の残件がこれ以上ない（最終ページに到達）
    }
  }

  return { items, totalCount, incompleteResults }
}

