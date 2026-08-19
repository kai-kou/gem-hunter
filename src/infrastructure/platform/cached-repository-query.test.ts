import { describe, expect, it } from 'vitest'

import type { RepositoryDetail, SearchResult } from '../../domain/model/repository'
import { repositoryFullName } from '../../domain/model/repository-full-name'
import { searchQuery } from '../../domain/model/search-query'
import type { ClockPort } from '../../domain/ports/clock-port'
import type { RepositoryQueryPort } from '../../domain/ports/repository-query-port'
import { CachingRepositoryQuery } from './cached-repository-query'
import { InMemoryCache } from './cache'

/** テスト用の `ClockPort` フェイク（可変時刻）。cache.test.ts と同じ形。 */
function fakeClock(initialMs: number): ClockPort & { advance(ms: number): void } {
  let current = initialMs
  return {
    now: () => new Date(current),
    advance: (ms: number) => {
      current += ms
    },
  }
}

function makeSearchResult(overrides: Partial<SearchResult> = {}): SearchResult {
  return {
    totalCount: 0,
    incompleteResults: false,
    items: [],
    ...overrides,
  }
}

function makeRepositoryDetail(overrides: Partial<RepositoryDetail> = {}): RepositoryDetail {
  return {
    id: 1,
    name: 'react',
    fullName: 'facebook/react',
    owner: { login: 'facebook', avatarUrl: 'https://example.com/a.png' },
    description: null,
    primaryLanguage: null,
    stars: 0,
    watchers: 0,
    forks: 0,
    openIssues: 0,
    updatedAt: new Date('2020-01-01T00:00:00Z'),
    topics: [],
    htmlUrl: 'https://github.com/facebook/react',
    ...overrides,
  }
}

/** 手書きフェイクの RepositoryQueryPort（呼び出し回数を数える）。 */
function fakeRepositoryQueryPort(): RepositoryQueryPort & {
  searchCallCount: number
  findDetailCallCount: number
} {
  return {
    searchCallCount: 0,
    findDetailCallCount: 0,
    async search() {
      this.searchCallCount += 1
      return makeSearchResult({ totalCount: 1 })
    },
    async findDetail(name) {
      this.findDetailCallCount += 1
      if (name === repositoryFullName('missing', 'repo')) {
        return null
      }
      return makeRepositoryDetail({ fullName: name })
    },
  }
}

const TTL = { search: 60, detail: 300 }

describe('CachingRepositoryQuery#search', () => {
  it('MISS 時は inner.search を呼び、結果を返す', async () => {
    const inner = fakeRepositoryQueryPort()
    const cache = new InMemoryCache()
    const decorated = new CachingRepositoryQuery({ inner, cache, ttlSeconds: TTL })

    const result = await decorated.search(searchQuery({ keyword: 'react' }))

    expect(inner.searchCallCount).toBe(1)
    expect(result.totalCount).toBe(1)
  })

  it('同じ SearchQuery で 2 回目は inner.search を呼ばない', async () => {
    const inner = fakeRepositoryQueryPort()
    const cache = new InMemoryCache()
    const decorated = new CachingRepositoryQuery({ inner, cache, ttlSeconds: TTL })
    const query = searchQuery({ keyword: 'react' })

    await decorated.search(query)
    await decorated.search(query)

    expect(inner.searchCallCount).toBe(1)
  })

  it('TTL 経過後は inner.search を再度呼ぶ', async () => {
    const inner = fakeRepositoryQueryPort()
    const clock = fakeClock(0)
    const cache = new InMemoryCache(clock)
    const decorated = new CachingRepositoryQuery({ inner, cache, ttlSeconds: TTL })
    const query = searchQuery({ keyword: 'react' })

    await decorated.search(query)
    clock.advance(TTL.search * 1000)
    await decorated.search(query)

    expect(inner.searchCallCount).toBe(2)
  })

  it('keyword が異なれば別キーとしてそれぞれ inner.search を呼ぶ', async () => {
    const inner = fakeRepositoryQueryPort()
    const cache = new InMemoryCache()
    const decorated = new CachingRepositoryQuery({ inner, cache, ttlSeconds: TTL })

    await decorated.search(searchQuery({ keyword: 'react' }))
    await decorated.search(searchQuery({ keyword: 'vue' }))

    expect(inner.searchCallCount).toBe(2)
  })

  it('page が異なれば別キーとしてそれぞれ inner.search を呼ぶ', async () => {
    const inner = fakeRepositoryQueryPort()
    const cache = new InMemoryCache()
    const decorated = new CachingRepositoryQuery({ inner, cache, ttlSeconds: TTL })

    await decorated.search(searchQuery({ keyword: 'react', page: 1 }))
    await decorated.search(searchQuery({ keyword: 'react', page: 2 }))

    expect(inner.searchCallCount).toBe(2)
  })

  it('onCacheStatus が MISS → HIT の順で呼ばれる', async () => {
    const inner = fakeRepositoryQueryPort()
    const cache = new InMemoryCache()
    const statuses: Array<'HIT' | 'MISS'> = []
    const decorated = new CachingRepositoryQuery({
      inner,
      cache,
      ttlSeconds: TTL,
      onCacheStatus: (status) => statuses.push(status),
    })
    const query = searchQuery({ keyword: 'react' })

    await decorated.search(query)
    await decorated.search(query)

    expect(statuses).toEqual(['MISS', 'HIT'])
  })

  it('同一キーへの並行リクエストは inner.search を 1 回しか呼ばない（single-flight）', async () => {
    // resolve 関数を呼び出し発生前に確定させておく（inner.search が実際に呼ばれる
    // までのマイクロタスク段数に依存させないため。gate.promise を先に作り、呼ばれた
    // 側はそれをそのまま返すだけにする）。
    let resolveFetch!: (value: SearchResult) => void
    const gate = new Promise<SearchResult>((resolve) => {
      resolveFetch = resolve
    })
    let callCount = 0
    const inner: RepositoryQueryPort = {
      search: async () => {
        callCount += 1
        return gate
      },
      findDetail: async () => {
        throw new Error('このテストでは使わない')
      },
    }
    const cache = new InMemoryCache()
    const decorated = new CachingRepositoryQuery({ inner, cache, ttlSeconds: TTL })
    const query = searchQuery({ keyword: 'react' })

    const p1 = decorated.search(query)
    const p2 = decorated.search(query)
    resolveFetch(makeSearchResult({ totalCount: 7 }))
    const [r1, r2] = await Promise.all([p1, p2])

    expect(callCount).toBe(1)
    expect(r1.totalCount).toBe(7)
    expect(r2.totalCount).toBe(7)
  })

  it('inner.search が失敗すると in-flight エントリが残らず、次の呼び出しで再試行できる', async () => {
    let callCount = 0
    const inner: RepositoryQueryPort = {
      search: async () => {
        callCount += 1
        if (callCount === 1) {
          throw new Error('boom')
        }
        return makeSearchResult({ totalCount: 9 })
      },
      findDetail: async () => {
        throw new Error('このテストでは使わない')
      },
    }
    const cache = new InMemoryCache()
    const decorated = new CachingRepositoryQuery({ inner, cache, ttlSeconds: TTL })
    const query = searchQuery({ keyword: 'react' })

    await expect(decorated.search(query)).rejects.toThrow('boom')
    const result = await decorated.search(query)

    expect(result.totalCount).toBe(9)
    expect(callCount).toBe(2)
  })
})

describe('CachingRepositoryQuery#findDetail', () => {
  it('同じ owner/repo で 2 回目は inner.findDetail を呼ばない', async () => {
    const inner = fakeRepositoryQueryPort()
    const cache = new InMemoryCache()
    const decorated = new CachingRepositoryQuery({ inner, cache, ttlSeconds: TTL })
    const name = repositoryFullName('facebook', 'react')

    await decorated.findDetail(name)
    await decorated.findDetail(name)

    expect(inner.findDetailCallCount).toBe(1)
  })

  it('404（null）はキャッシュしない（毎回 inner.findDetail を呼ぶ）', async () => {
    const inner = fakeRepositoryQueryPort()
    const cache = new InMemoryCache()
    const decorated = new CachingRepositoryQuery({ inner, cache, ttlSeconds: TTL })
    const name = repositoryFullName('missing', 'repo')

    const first = await decorated.findDetail(name)
    const second = await decorated.findDetail(name)

    expect(first).toBeNull()
    expect(second).toBeNull()
    expect(inner.findDetailCallCount).toBe(2)
  })

  it('同一 owner/repo への並行リクエストは inner.findDetail を 1 回しか呼ばない（single-flight）', async () => {
    // 上の search テストと同じ理由で、resolve 関数を呼び出し発生前に確定させておく。
    let resolveFetch!: (value: RepositoryDetail) => void
    const gate = new Promise<RepositoryDetail>((resolve) => {
      resolveFetch = resolve
    })
    let callCount = 0
    const inner: RepositoryQueryPort = {
      search: async () => {
        throw new Error('このテストでは使わない')
      },
      findDetail: async () => {
        callCount += 1
        return gate
      },
    }
    const cache = new InMemoryCache()
    const decorated = new CachingRepositoryQuery({ inner, cache, ttlSeconds: TTL })
    const name = repositoryFullName('facebook', 'react')

    const p1 = decorated.findDetail(name)
    const p2 = decorated.findDetail(name)
    resolveFetch(makeRepositoryDetail({ fullName: name, stars: 42 }))
    const [r1, r2] = await Promise.all([p1, p2])

    expect(callCount).toBe(1)
    expect(r1?.stars).toBe(42)
    expect(r2?.stars).toBe(42)
  })

  it('inner.findDetail が失敗すると in-flight エントリが残らず、次の呼び出しで再試行できる', async () => {
    let callCount = 0
    const name = repositoryFullName('facebook', 'react')
    const inner: RepositoryQueryPort = {
      search: async () => {
        throw new Error('このテストでは使わない')
      },
      findDetail: async () => {
        callCount += 1
        if (callCount === 1) {
          throw new Error('boom')
        }
        return makeRepositoryDetail({ fullName: name })
      },
    }
    const cache = new InMemoryCache()
    const decorated = new CachingRepositoryQuery({ inner, cache, ttlSeconds: TTL })

    await expect(decorated.findDetail(name)).rejects.toThrow('boom')
    const result = await decorated.findDetail(name)

    expect(result?.fullName).toBe(name)
    expect(callCount).toBe(2)
  })
})
