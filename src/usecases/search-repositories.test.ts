import { describe, expect, it } from 'vitest'

import { DomainValidationError } from '../domain/errors'
import type { RepositorySummary, SearchResult } from '../domain/model/repository'
import type { SearchQuery } from '../domain/model/search-query'
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
  updatedAt: new Date('2026-08-18T00:00:00Z'),
  topics: ['javascript', 'react'],
  htmlUrl: 'https://github.com/facebook/react',
}

function fakePort(received: SearchQuery[]): RepositoryQueryPort {
  return {
    async search(query) {
      received.push(query)
      return { totalCount: 1, incompleteResults: false, items: [summary] } satisfies SearchResult
    },
  }
}

describe('searchRepositories', () => {
  it('キーワードを値オブジェクトへ変換してポートへ渡す', async () => {
    const received: SearchQuery[] = []
    const searchRepositories = makeSearchRepositories({ repos: fakePort(received) })

    const result = await searchRepositories({ keyword: ' react ', page: 2 })

    expect(received).toHaveLength(1)
    expect(received[0].keyword).toBe('react')
    expect(received[0].page).toBe(2)
    expect(result.items[0].fullName).toBe('facebook/react')
  })

  it('不正なキーワードではポートを呼ばずに落とす', async () => {
    const received: SearchQuery[] = []
    const searchRepositories = makeSearchRepositories({ repos: fakePort(received) })

    await expect(searchRepositories({ keyword: '' })).rejects.toThrow(DomainValidationError)
    expect(received).toHaveLength(0)
  })
})
