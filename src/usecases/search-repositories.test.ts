import { describe, expect, it } from 'vitest'

import { DomainValidationError } from '../domain/errors'
import type { DigestMeta, Gem } from '../domain/model/gem'
import { gemIndex } from '../domain/model/gem-index'
import type { RepositorySummary, SearchResult } from '../domain/model/repository'
import type { SearchQuery } from '../domain/model/search-query'
import type { GemDigestPort } from '../domain/ports/gem-digest-port'
import type { RepositoryQueryPort } from '../domain/ports/repository-query-port'
import { GEM_INDEX_FETCH_MAX_PAGES, makeSearchRepositories } from './search-repositories'

const summary: RepositorySummary = {
  id: 10270250,
  fullName: 'facebook/react',
  name: 'react',
  owner: { login: 'facebook', avatarUrl: 'https://avatars.githubusercontent.com/u/69631?v=4' },
  description: 'The library for web and native user interfaces.',
  primaryLanguage: 'JavaScript',
  stars: 233000,
  lastPushedAt: new Date('2026-08-18T00:00:00Z'),
  topics: ['javascript', 'react'],
  htmlUrl: 'https://github.com/facebook/react',
}

const digestMeta: DigestMeta = {
  source: 'Ecosyste.ms',
  license: 'CC BY-SA 4.0',
  sourceLicenseUrl: 'https://creativecommons.org/licenses/by-sa/4.0/',
  generatedAt: '2026-08-20T00:00:00Z',
}

function fakePort(received: SearchQuery[]): RepositoryQueryPort {
  return {
    async search(query) {
      received.push(query)
      return { totalCount: 1, incompleteResults: false, items: [summary] } satisfies SearchResult
    },
    async findDetail() {
      return null
    },
  }
}

/** 未使用時は空の候補プールを返すだけの gem-index 経路以外のテスト用フェイク。 */
function emptyGemsPort(): GemDigestPort {
  return {
    async listCandidates() {
      return { candidates: [], meta: digestMeta }
    },
  }
}

/** id 連番のリポジトリ結果を作る（gem-index 経路のページ合成テスト用）。 */
function summaryWithId(id: number, fullName: string): RepositorySummary {
  return {
    id,
    fullName,
    name: fullName.split('/')[1],
    owner: { login: fullName.split('/')[0], avatarUrl: 'https://example.test/avatar.png' },
    description: null,
    primaryLanguage: null,
    stars: 0,
    lastPushedAt: new Date('2026-08-18T00:00:00Z'),
    topics: [],
    htmlUrl: `https://github.com/${fullName}`,
  }
}

/** 候補プールの Gem を 1 件作る（gemFacetKey は repositoryFullName を小文字化したもの）。 */
function gem(repositoryFullName: string, gi: number): Gem {
  return {
    packageName: repositoryFullName.split('/')[1],
    repositoryFullName,
    dependentCount: 100,
    stars: 10,
    gemIndex: gemIndex(gi),
  }
}

/**
 * ページ番号 → 応答 を返す関数からページング可能な `RepositoryQueryPort` フェイクを作る。
 * `received` に呼び出されたクエリを積む（回数・引数の検証用）。
 */
function pagedPort(
  received: SearchQuery[],
  responder: (page: number) => SearchResult,
): RepositoryQueryPort {
  return {
    async search(query) {
      received.push(query)
      return responder(query.page)
    },
    async findDetail() {
      return null
    },
  }
}

function gemsPort(candidates: readonly Gem[]): GemDigestPort {
  return {
    async listCandidates() {
      return { candidates, meta: digestMeta }
    },
  }
}

/** 指定件数ぶんの id 連番アイテムを持つ 1 ページ分の応答を作る。 */
function page(items: RepositorySummary[], totalCount: number, incomplete = false): SearchResult {
  return { totalCount, incompleteResults: incomplete, items }
}

describe('searchRepositories', () => {
  it('キーワードを値オブジェクトへ変換してポートへ渡す', async () => {
    const received: SearchQuery[] = []
    const searchRepositories = makeSearchRepositories({
      repos: fakePort(received),
      gems: emptyGemsPort(),
    })

    const result = await searchRepositories({ keyword: ' react ', page: 2 })

    expect(received).toHaveLength(1)
    expect(received[0].keyword).toBe('react')
    expect(received[0].page).toBe(2)
    expect(result.items[0].fullName).toBe('facebook/react')
  })

  it('sort / perPage を値オブジェクトへ変換してポートへ渡す', async () => {
    const received: SearchQuery[] = []
    const searchRepositories = makeSearchRepositories({
      repos: fakePort(received),
      gems: emptyGemsPort(),
    })

    await searchRepositories({ keyword: 'react', sort: 'stars', perPage: 50 })

    expect(received).toHaveLength(1)
    expect(received[0].sort).toBe('stars')
    expect(received[0].perPage).toBe(50)
  })

  it('sort / perPage 省略時は既定値になる', async () => {
    const received: SearchQuery[] = []
    const searchRepositories = makeSearchRepositories({
      repos: fakePort(received),
      gems: emptyGemsPort(),
    })

    await searchRepositories({ keyword: 'react' })

    expect(received[0].sort).toBe('relevance')
    expect(received[0].perPage).toBe(20)
  })

  it('不正なキーワードではポートを呼ばずに落とす', async () => {
    const received: SearchQuery[] = []
    const searchRepositories = makeSearchRepositories({
      repos: fakePort(received),
      gems: emptyGemsPort(),
    })

    await expect(searchRepositories({ keyword: '' })).rejects.toThrow(DomainValidationError)
    expect(received).toHaveLength(0)
  })

  describe('sort=gem-index', () => {
    it('gem-index 以外のときは search を1回しか呼ばない（回帰）', async () => {
      const received: SearchQuery[] = []
      const searchRepositories = makeSearchRepositories({
        repos: fakePort(received),
        gems: emptyGemsPort(),
      })

      await searchRepositories({ keyword: 'react', sort: 'stars' })

      expect(received).toHaveLength(1)
    })

    it('1ページ目の totalCount から早期打ち切りする（30件 → 1回だけ）', async () => {
      const received: SearchQuery[] = []
      const items = Array.from({ length: 30 }, (_, i) => summaryWithId(i, `owner/repo-${i}`))
      const repos = pagedPort(received, () => page(items, 30))
      const searchRepositories = makeSearchRepositories({ repos, gems: emptyGemsPort() })

      await searchRepositories({ keyword: 'react', sort: 'gem-index' })

      expect(received).toHaveLength(1)
      expect(received[0].perPage).toBe(100)
    })

    it('10ページ上限で止まる（1ページ100件ちょうどが延々続く場合）', async () => {
      const received: SearchQuery[] = []
      const repos = pagedPort(received, (p) => {
        const items = Array.from({ length: 100 }, (_, i) =>
          summaryWithId(p * 1000 + i, `owner/repo-${p}-${i}`),
        )
        return page(items, 5000)
      })
      const searchRepositories = makeSearchRepositories({ repos, gems: emptyGemsPort() })

      await searchRepositories({ keyword: 'react', sort: 'gem-index', perPage: 100 })

      expect(received).toHaveLength(10)
      expect(received.map((q) => q.page)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    })

    it('応答件数が per_page 未満なら最終ページとして打ち切る', async () => {
      const received: SearchQuery[] = []
      const repos = pagedPort(received, (p) => {
        if (p === 1) {
          const items = Array.from({ length: 100 }, (_, i) => summaryWithId(i, `owner/repo-a-${i}`))
          return page(items, 150)
        }
        const items = Array.from({ length: 50 }, (_, i) => summaryWithId(1000 + i, `owner/repo-b-${i}`))
        return page(items, 150)
      })
      const searchRepositories = makeSearchRepositories({ repos, gems: emptyGemsPort() })

      await searchRepositories({ keyword: 'react', sort: 'gem-index' })

      expect(received).toHaveLength(2)
    })

    it('Gem Index を持たない結果は絞り込まず末尾に残り、件数が変わらない', async () => {
      const received: SearchQuery[] = []
      const items = [
        summaryWithId(1, 'owner/no-index-a'),
        summaryWithId(2, 'owner/has-index'),
        summaryWithId(3, 'owner/no-index-b'),
      ]
      const repos = pagedPort(received, () => page(items, 3))
      const gems = gemsPort([gem('owner/has-index', -0.5)])
      const searchRepositories = makeSearchRepositories({ repos, gems })

      const result = await searchRepositories({ keyword: 'react', sort: 'gem-index' })

      expect(result.items).toHaveLength(3)
      expect(result.items.map((x) => x.fullName)).toEqual([
        'owner/has-index',
        'owner/no-index-a',
        'owner/no-index-b',
      ])
    })

    it('途中ページのエラーはそのまま伝播する（fail-closed）', async () => {
      const received: SearchQuery[] = []
      const failure = new Error('upstream failed on page 2')
      const repos: RepositoryQueryPort = {
        async search(query) {
          received.push(query)
          if (query.page === 1) {
            const items = Array.from({ length: 100 }, (_, i) => summaryWithId(i, `owner/repo-${i}`))
            return page(items, 250)
          }
          throw failure
        },
        async findDetail() {
          return null
        },
      }
      const searchRepositories = makeSearchRepositories({ repos, gems: emptyGemsPort() })

      await expect(searchRepositories({ keyword: 'react', sort: 'gem-index' })).rejects.toBe(
        failure,
      )
    })

    it('表示ページ2のスライスが正しい', async () => {
      const received: SearchQuery[] = []
      // 25 件（gem-index 昇順で並ぶよう gemIndex を 0..24 に割り当て）。
      const items = Array.from({ length: 25 }, (_, i) => summaryWithId(i, `owner/repo-${i}`))
      const repos = pagedPort(received, () => page(items, 25))
      const gems = gemsPort(items.map((item, i) => gem(item.fullName, i)))
      const searchRepositories = makeSearchRepositories({ repos, gems })

      const result = await searchRepositories({
        keyword: 'react',
        sort: 'gem-index',
        page: 2,
        perPage: 20,
      })

      expect(result.items).toHaveLength(5)
      expect(result.items.map((x) => x.fullName)).toEqual(
        Array.from({ length: 5 }, (_, i) => `owner/repo-${20 + i}`),
      )
      expect(result.totalCount).toBe(25)
    })

    it('GEM_INDEX_FETCH_MAX_PAGES は API_RESULT_LIMIT から導出される（③・二重定義の解消）', async () => {
      const { API_RESULT_LIMIT } = await import('../domain/model/page-number')
      expect(GEM_INDEX_FETCH_MAX_PAGES).toBe(10)
      expect(GEM_INDEX_FETCH_MAX_PAGES).toBe(Math.floor(API_RESULT_LIMIT / 100))
    })

    it('①CRITICAL: 重複排除で収集件数が totalCount を下回り、自然終了した場合は実件数へクランプする', async () => {
      const received: SearchQuery[] = []
      const repos = pagedPort(received, (p) => {
        if (p === 1) {
          const items = Array.from({ length: 100 }, (_, i) => summaryWithId(i, `owner/repo-${i}`))
          return page(items, 150)
        }
        // 2ページ目は 60 件中 20 件が page1 と id 重複・40 件が新規。
        // 応答件数 60 < per_page(100) なので最終ページとして自然終了する。
        const overlap = Array.from({ length: 20 }, (_, i) => summaryWithId(i, `owner/dup-${i}`))
        const fresh = Array.from({ length: 40 }, (_, i) =>
          summaryWithId(100 + i, `owner/repo-${100 + i}`),
        )
        return page([...overlap, ...fresh], 150)
      })
      const searchRepositories = makeSearchRepositories({ repos, gems: emptyGemsPort() })

      const result = await searchRepositories({ keyword: 'react', sort: 'gem-index', perPage: 100 })

      // 収集: page1 の 100 件 + page2 の新規 40 件 = 140 件（totalCount=150 には届かない）。
      expect(result.totalCount).toBe(140)
    })

    it('①: 10 ページ上限で打ち切った場合は、重複排除で件数が縮んでも totalCount をクランプしない', async () => {
      const received: SearchQuery[] = []
      const repos = pagedPort(received, () => {
        // 毎ページ同じ id 0〜99 を返す（重複排除後の収集件数は 100 件のみに縮む）。
        const items = Array.from({ length: 100 }, (_, i) => summaryWithId(i, `owner/repo-${i}`))
        return page(items, 5000)
      })
      const searchRepositories = makeSearchRepositories({ repos, gems: emptyGemsPort() })

      const result = await searchRepositories({ keyword: 'react', sort: 'gem-index', perPage: 100 })

      expect(received).toHaveLength(GEM_INDEX_FETCH_MAX_PAGES)
      // 10 ページ上限で打ち切っただけで、まだ取得していない結果が残っている可能性があるため
      // 生の totalCount（5000）をそのまま返す（実収集件数 100 へクランプしない）。
      expect(result.totalCount).toBe(5000)
    })

    it('重複した id はページ間で排除する（先に現れた方を残す）', async () => {
      const received: SearchQuery[] = []
      const repos = pagedPort(received, (p) => {
        if (p === 1) {
          const items = Array.from({ length: 100 }, (_, i) => summaryWithId(i, `owner/repo-${i}`))
          return page(items, 110)
        }
        // 2ページ目は id=0〜4 が重複し、残り id=100〜104 が新規（ページ間の鮮度ずれを模倣）。
        // 応答件数 10 < per_page(100) なので最終ページとして打ち切られる。
        const overlap = Array.from({ length: 5 }, (_, i) => summaryWithId(i, `owner/dup-${i}`))
        const fresh = Array.from({ length: 5 }, (_, i) => summaryWithId(100 + i, `owner/repo-${100 + i}`))
        return page([...overlap, ...fresh], 110)
      })
      const searchRepositories = makeSearchRepositories({ repos, gems: emptyGemsPort() })

      // 表示 1 ページ目（perPage 上限の 100 件）: 1ページ目の 100 件がそのまま出る。
      const first = await searchRepositories({ keyword: 'react', sort: 'gem-index', perPage: 100 })
      expect(first.items).toHaveLength(100)
      // 重複した id=0 は「先に現れた方（1ページ目の owner/repo-0）」を残す。
      expect(first.items.find((x) => x.id === 0)?.fullName).toBe('owner/repo-0')

      // 表示 2 ページ目: 重複排除後に残った新規 5 件（id=100〜104）だけが出る。
      const second = await searchRepositories({
        keyword: 'react',
        sort: 'gem-index',
        perPage: 100,
        page: 2,
      })
      expect(second.items).toHaveLength(5)
      expect(second.items.map((x) => x.id)).toEqual([100, 101, 102, 103, 104])
    })
  })
})
