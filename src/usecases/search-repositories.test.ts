import { describe, expect, it } from 'vitest'

import { DomainValidationError } from '../domain/errors'
import { gemIndex } from '../domain/model/gem-index'
import type { RepositorySummary, SearchResult } from '../domain/model/repository'
import type { SearchQuery } from '../domain/model/search-query'
import type { Gem } from '../domain/model/gem'
import type { GemDigestPort } from '../domain/ports/gem-digest-port'
import type { RepositoryQueryPort } from '../domain/ports/repository-query-port'
import { makeSearchRepositories } from './search-repositories'

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

function repo(fullName: string, overrides: Partial<RepositorySummary> = {}): RepositorySummary {
  const [, name] = fullName.split('/')
  return {
    ...summary,
    id: hashId(fullName),
    fullName,
    name,
    owner: { login: fullName.split('/')[0], avatarUrl: summary.owner.avatarUrl },
    htmlUrl: `https://github.com/${fullName}`,
    ...overrides,
  }
}

function hashId(value: string): number {
  let hash = 0
  for (let i = 0; i < value.length; i += 1) {
    hash = (hash * 31 + value.charCodeAt(i)) | 0
  }
  return Math.abs(hash)
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

/** ページ単位でスタブ結果を返すフェイクポート（gemIndex 全件取得ループの検証用）。 */
function pagedFakePort(pages: RepositorySummary[][], received: SearchQuery[]): RepositoryQueryPort {
  return {
    async search(query) {
      received.push(query)
      const items = pages[query.page - 1] ?? []
      return {
        totalCount: pages.reduce((sum, page) => sum + page.length, 0),
        incompleteResults: false,
        items,
      } satisfies SearchResult
    },
    async findDetail() {
      return null
    },
  }
}

function fakeGemDigest(candidates: Gem[]): GemDigestPort {
  return {
    async listCandidates() {
      return {
        candidates,
        meta: {
          source: 'Ecosyste.ms',
          license: 'CC BY-SA 4.0',
          sourceLicenseUrl: 'https://creativecommons.org/licenses/by-sa/4.0/',
          generatedAt: '2026-08-21T00:00:00Z',
        },
      }
    },
  }
}

/** `listCandidates()` が必ず失敗する `GemDigestPort`（fail-soft 検証用）。 */
function throwingGemDigest(): GemDigestPort {
  return {
    async listCandidates() {
      throw new Error('gem digest source unavailable')
    },
  }
}

function gem(repositoryFullName: string, indexValue: number, dependentCount = 100): Gem {
  return {
    packageName: repositoryFullName.split('/')[1],
    repositoryFullName,
    dependentCount,
    stars: 10,
    gemIndex: gemIndex(indexValue),
  }
}

const emptyGemDigest = fakeGemDigest([])

describe('searchRepositories', () => {
  it('キーワードを値オブジェクトへ変換してポートへ渡す', async () => {
    const received: SearchQuery[] = []
    const searchRepositories = makeSearchRepositories({
      repos: fakePort(received),
      gemDigest: emptyGemDigest,
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
      gemDigest: emptyGemDigest,
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
      gemDigest: emptyGemDigest,
    })

    await searchRepositories({ keyword: 'react' })

    expect(received[0].sort).toBe('relevance')
    expect(received[0].perPage).toBe(20)
  })

  it('不正なキーワードではポートを呼ばずに落とす', async () => {
    const received: SearchQuery[] = []
    const searchRepositories = makeSearchRepositories({
      repos: fakePort(received),
      gemDigest: emptyGemDigest,
    })

    await expect(searchRepositories({ keyword: '' })).rejects.toThrow(DomainValidationError)
    expect(received).toHaveLength(0)
  })

  describe('sort=gemIndex', () => {
    it('内部フェッチが sort=gemIndex を GitHub 側へ漏らさない（critical）', async () => {
      const received: SearchQuery[] = []
      const searchRepositories = makeSearchRepositories({
        repos: pagedFakePort([[repo('a/one')]], received),
        gemDigest: emptyGemDigest,
      })

      await searchRepositories({ keyword: 'react', sort: 'gemIndex' })

      expect(received.length).toBeGreaterThan(0)
      for (const query of received) {
        expect(query.sort).toBe('relevance')
        expect(query.perPage).toBe(100)
      }
    })

    it('Index を持つ結果は昇順（値が小さいほど上位）に並び、持たない結果は末尾に残る（絞り込まない）', async () => {
      const received: SearchQuery[] = []
      const page1 = [repo('a/high'), repo('b/no-index'), repo('c/low'), repo('d/mid')]
      const searchRepositories = makeSearchRepositories({
        repos: pagedFakePort([page1], received),
        gemDigest: fakeGemDigest([gem('a/high', -1), gem('c/low', -5), gem('d/mid', -3)]),
      })

      const result = await searchRepositories({ keyword: 'react', sort: 'gemIndex', perPage: 20 })

      expect(result.items.map((item) => item.fullName)).toEqual([
        'c/low',
        'd/mid',
        'a/high',
        'b/no-index',
      ])
      // 件数は変わらない（D-30①）。
      expect(result.items).toHaveLength(4)
      expect(result.items[3].gemIndex).toBeUndefined()
    })

    it('Index を持たない結果同士は取得時点の相対順序（relevance）を保つ', async () => {
      const received: SearchQuery[] = []
      const page1 = [repo('a/first'), repo('b/second'), repo('c/third')]
      const searchRepositories = makeSearchRepositories({
        repos: pagedFakePort([page1], received),
        gemDigest: emptyGemDigest,
      })

      const result = await searchRepositories({ keyword: 'react', sort: 'gemIndex' })

      expect(result.items.map((item) => item.fullName)).toEqual(['a/first', 'b/second', 'c/third'])
    })

    it('候補プールに無いリポジトリは除外されない（件数不変）', async () => {
      const received: SearchQuery[] = []
      const page1 = [repo('a/one'), repo('b/two'), repo('c/three')]
      const searchRepositories = makeSearchRepositories({
        repos: pagedFakePort([page1], received),
        gemDigest: fakeGemDigest([gem('a/one', -2)]),
      })

      const result = await searchRepositories({ keyword: 'react', sort: 'gemIndex' })

      expect(result.items).toHaveLength(3)
    })

    it('join は fullName の大文字小文字を区別しない', async () => {
      const received: SearchQuery[] = []
      const page1 = [repo('Facebook/React')]
      const searchRepositories = makeSearchRepositories({
        repos: pagedFakePort([page1], received),
        gemDigest: fakeGemDigest([gem('facebook/react', -4, 500)]),
      })

      const result = await searchRepositories({ keyword: 'react', sort: 'gemIndex' })

      expect(result.items[0].gemIndex).toBeDefined()
      expect(result.items[0].dependentCount).toBe(500)
    })

    it('101 件以上ある場合は 2 ページ目まで取得する（100 件で打ち切らない）', async () => {
      const received: SearchQuery[] = []
      const page1 = Array.from({ length: 100 }, (_, i) => repo(`org/repo-${i}`))
      const page2 = [repo('org/last')]
      const searchRepositories = makeSearchRepositories({
        repos: pagedFakePort([page1, page2], received),
        gemDigest: emptyGemDigest,
      })

      // 表示 page=2・perPage=100 → 取得済み配列の 101 件目（=raw 2 ページ目の内容）が見える。
      const result = await searchRepositories({
        keyword: 'react',
        sort: 'gemIndex',
        page: 2,
        perPage: 100,
      })

      expect(received).toHaveLength(2) // raw fetch は 2 ページとも行われる（100 件ちょうどで打ち切らない）
      expect(result.totalCount).toBe(101)
      expect(result.items).toEqual([expect.objectContaining({ fullName: 'org/last' })])
    })

    it('GemDigestPort#listCandidates() が失敗しても検索結果は返す（Gem Index なしで続行・fail-soft）', async () => {
      const received: SearchQuery[] = []
      const page1 = [repo('a/one'), repo('b/two')]
      const searchRepositories = makeSearchRepositories({
        repos: pagedFakePort([page1], received),
        gemDigest: throwingGemDigest(),
      })

      const result = await searchRepositories({ keyword: 'react', sort: 'gemIndex' })

      // 例外が伝播せず、候補プール空として扱われる＝取得順のまま両方とも Index なしで返る。
      expect(result.items.map((item) => item.fullName)).toEqual(['a/one', 'b/two'])
      expect(result.items.every((item) => item.gemIndex === undefined)).toBe(true)
    })

    it('101 ページ目にあたる 10 ページ目まで全件 100 件で埋まっていても 11 ページ目を要求しない（1,000 件で頭打ち）', async () => {
      const received: SearchQuery[] = []
      const RAW_MAX_PAGES = 10
      const pages = Array.from({ length: RAW_MAX_PAGES }, (_, p) =>
        Array.from({ length: 100 }, (_, i) => repo(`org/p${p}-r${i}`)),
      )
      const searchRepositories = makeSearchRepositories({
        repos: pagedFakePort(pages, received),
        gemDigest: emptyGemDigest,
      })

      const result = await searchRepositories({
        keyword: 'react',
        sort: 'gemIndex',
        page: 1,
        perPage: 100,
      })

      // 10 ページとも 100 件ちょうどで埋まっているため break 条件（`items.length < RAW_PER_PAGE`）
      // には引っかからないが、`RAW_MAX_PAGES` の for ループ上限自体が 11 ページ目の要求を止める。
      expect(received).toHaveLength(RAW_MAX_PAGES)
      expect(received.every((query) => query.page <= RAW_MAX_PAGES)).toBe(true)
      expect(result.totalCount).toBe(1000)
      expect(result.items).toHaveLength(100) // page=1, perPage=100 のスライス
    })

    it('ページ番号・表示件数に応じて取得済み配列をスライスする（totalCount は生値のまま）', async () => {
      const received: SearchQuery[] = []
      const page1 = Array.from({ length: 5 }, (_, i) => repo(`org/repo-${i}`))
      const searchRepositories = makeSearchRepositories({
        repos: pagedFakePort([page1], received),
        gemDigest: emptyGemDigest,
      })

      const result = await searchRepositories({
        keyword: 'react',
        sort: 'gemIndex',
        page: 2,
        perPage: 20,
      })

      expect(result.items).toHaveLength(0)
      expect(result.totalCount).toBe(5)
    })
  })
})
