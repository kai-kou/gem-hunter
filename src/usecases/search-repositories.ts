import { toGemFacetMap, sortByGemIndex } from '../domain/model/gem-index'
import { API_RESULT_LIMIT } from '../domain/model/page-number'
import type { SearchResult } from '../domain/model/repository'
import { searchQuery } from '../domain/model/search-query'
import { GEM_INDEX_SORT_ORDER } from '../domain/model/sort-order'
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
 * gem-index 順ソートで内部的に取得する 1 ページあたりの件数。
 * GitHub 検索 API は 1 検索あたり最大 1,000 件（`API_RESULT_LIMIT`・`per_page` × `page`）までしか
 * 返さないため、100 件 × 最大 10 ページで打ち切る（`SP-16` 飼い主決定②・
 * `content/discussions/sp16-gem-index-sort-20260821/whiteboard.md` D-I）。
 */
const GEM_INDEX_FETCH_PER_PAGE = 100

/**
 * `API_RESULT_LIMIT ÷ GEM_INDEX_FETCH_PER_PAGE` が取得ページ数の上限。
 * 🔴 単一の定義元（SSOT）は `page-number.ts` の `API_RESULT_LIMIT`（PR #293 セルフレビュー
 * 指摘・修正③）。ここで別の 1,000 を直書きしない。`enforceSearchRateLimit` のレート消費コスト
 * （PR #293 セルフレビュー指摘・修正②）とも本定数を共有し、値をずらさない。
 */
export const GEM_INDEX_FETCH_MAX_PAGES = Math.floor(API_RESULT_LIMIT / GEM_INDEX_FETCH_PER_PAGE)

/**
 * キーワードでリポジトリを検索する（US-6）。
 *
 * `sort=gem-index`（`SP-16`）のときだけ挙動が変わる: GitHub 検索 API に `gem-index` という並び順は
 * 存在しない自前指標のため、最大 1,000 件（100 件 × 10 ページ）を逐次取得してから、Gem Index を
 * 持たない結果を末尾に残したまま並べ替え（飼い主決定①・`sortByGemIndex`）、要求された表示ページ分だけ
 * 切り出して返す。それ以外の `sort` では従来どおり 1 回の `deps.repos.search()` 呼び出しのみ。
 */
export function makeSearchRepositories(deps: {
  repos: RepositoryQueryPort
  gems: GemDigestPort
}): SearchRepositories {
  return async (input) => {
    const query = searchQuery(input)

    if (query.sort !== GEM_INDEX_SORT_ORDER) {
      return deps.repos.search(query)
    }

    return searchByGemIndex(deps, query.keyword, query.page, query.perPage)
  }
}

async function searchByGemIndex(
  deps: { repos: RepositoryQueryPort; gems: GemDigestPort },
  keyword: string,
  displayPage: number,
  displayPerPage: number,
): Promise<SearchResult> {
  let totalCount = 0
  let incompleteResults = false
  const collected: SearchResult['items'][number][] = []
  const seenIds = new Set<number>()

  // 1 ページ目の totalCount から実際に必要なページ数へ差し替える（D-I の二重条件のうち片方）。
  // 初期値は仕様上限の 10。1 ページ目取得後に Math.min(10, ceil(totalCount / 100)) へ縮める。
  let maxPages = GEM_INDEX_FETCH_MAX_PAGES
  // ①CRITICAL 修正（PR #293 セルフレビュー指摘）: ループが「結果を汲み尽くして」自然終了した
  // (= per_page 未満の応答で break した) かどうかを覚えておく。
  let brokeEarly = false

  for (let page = 1; page <= maxPages; page += 1) {
    // 🔴 逐次取得（`NFR-7` ③・並列にしない）。途中ページの失敗は握り潰さずそのまま伝播する
    //    （fail-closed・`NFR-8`。部分データで並べ替えて返さない）。
    const result = await deps.repos.search(
      searchQuery({
        keyword,
        page,
        perPage: GEM_INDEX_FETCH_PER_PAGE,
        sort: GEM_INDEX_SORT_ORDER,
      }),
    )

    if (page === 1) {
      totalCount = result.totalCount
      maxPages = Math.min(GEM_INDEX_FETCH_MAX_PAGES, Math.ceil(totalCount / GEM_INDEX_FETCH_PER_PAGE))
    }
    incompleteResults = incompleteResults || result.incompleteResults

    // ページ間の鮮度ずれで同一リポジトリが複数ページに跨って現れることがあるため id で重複排除する
    // （先に現れた方を残す・`whiteboard` D-F）。
    for (const item of result.items) {
      if (!seenIds.has(item.id)) {
        seenIds.add(item.id)
        collected.push(item)
      }
    }

    // 応答件数が per_page 未満なら最終ページ（D-I の二重条件のもう片方）。
    if (result.items.length < GEM_INDEX_FETCH_PER_PAGE) {
      brokeEarly = true
      break
    }
  }

  const { candidates } = await deps.gems.listCandidates()
  const facets = toGemFacetMap(candidates)
  const sorted = sortByGemIndex(collected, facets)

  const start = (displayPage - 1) * displayPerPage
  const items = sorted.slice(start, start + displayPerPage)

  // ①CRITICAL 修正（PR #293 セルフレビュー指摘）: `totalCount` に GitHub の生の `total_count`
  // をそのまま返すと、id 重複排除で収集件数が縮んだ場合に `Pagination` が空ページへのリンクを
  // 出してしまう（totalCount=200 なのに実体 100 件 → 2 ページ目が「200 件中 0 件」で行き止まり）。
  //
  // 「結果を汲み尽くして終わった」= (a) per_page 未満の応答で自然終了した、または
  // (b) 1 ページ目の totalCount から算出した必要ページ数が仕様上限 10 未満だった、のいずれか
  // （= `maxPages` が仕様上限まで消費されていない）場合だけ、実際に提供できる件数へクランプする。
  // 10 ページ上限に達して打ち切った場合（`maxPages === GEM_INDEX_FETCH_MAX_PAGES` かつ自然終了
  // していない）は、まだ取得していない結果が残っている可能性があるため、他の並び順と同じく
  // 生の値をそのまま返す（`maxPageFor` が到達範囲を抑えるため矛盾しない）。
  const exhausted = brokeEarly || maxPages < GEM_INDEX_FETCH_MAX_PAGES
  const resolvedTotalCount = exhausted ? Math.min(totalCount, collected.length) : totalCount

  return { totalCount: resolvedTotalCount, incompleteResults, items }
}
