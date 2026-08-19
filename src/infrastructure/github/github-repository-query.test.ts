import { HttpResponse, http } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'

import { RateLimitExceededError, UpstreamError } from '../../domain/errors'
import { repositoryFullName } from '../../domain/model/repository-full-name'
import { searchQuery } from '../../domain/model/search-query'
import detailFixture from './__fixtures__/repository-detail.json'
import fixture from './__fixtures__/search-repositories.json'
import { GithubRepositoryQuery } from './github-repository-query'

const requests: URL[] = []
const server = setupServer(
  http.get('https://api.github.com/search/repositories', ({ request }) => {
    requests.push(new URL(request.url))
    return HttpResponse.json(fixture)
  }),
  http.get('https://api.github.com/repos/:owner/:repo', ({ request }) => {
    requests.push(new URL(request.url))
    return HttpResponse.json(detailFixture)
  }),
)

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => {
  server.resetHandlers()
  requests.length = 0
})
afterAll(() => server.close())

function makeQuery() {
  return new GithubRepositoryQuery({ token: async () => 'ghs_dummy' })
}

describe('GithubRepositoryQuery', () => {
  it('検索 API を呼び出してドメインモデルを返す', async () => {
    const result = await makeQuery().search(searchQuery({ keyword: 'react', page: 2 }))

    expect(result.items).toHaveLength(2)
    expect(requests[0].searchParams.get('q')).toBe('react')
    expect(requests[0].searchParams.get('page')).toBe('2')
    expect(requests[0].searchParams.get('per_page')).toBe('30')
  })

  it('403 かつレート制限枯渇なら RateLimitExceededError を投げる', async () => {
    server.use(
      http.get('https://api.github.com/search/repositories', () =>
        HttpResponse.json(
          { message: 'rate limit' },
          { status: 403, headers: { 'x-ratelimit-remaining': '0' } },
        ),
      ),
    )

    await expect(makeQuery().search(searchQuery({ keyword: 'react' }))).rejects.toThrow(
      RateLimitExceededError,
    )
  })

  it('その他の失敗は UpstreamError に包む', async () => {
    server.use(
      http.get('https://api.github.com/search/repositories', () =>
        HttpResponse.json({ message: 'boom' }, { status: 500 }),
      ),
    )

    await expect(makeQuery().search(searchQuery({ keyword: 'react' }))).rejects.toThrow(
      UpstreamError,
    )
  })
})

describe('GithubRepositoryQuery#findDetail', () => {
  it('詳細 API を呼び出してドメインモデルを返す', async () => {
    const result = await makeQuery().findDetail(repositoryFullName('facebook', 'react'))

    expect(result?.fullName).toBe('facebook/react')
    expect(requests[0].pathname).toBe('/repos/facebook/react')
  })

  it('404 は例外にせず null を返す', async () => {
    server.use(
      http.get('https://api.github.com/repos/:owner/:repo', () =>
        HttpResponse.json({ message: 'Not Found' }, { status: 404 }),
      ),
    )

    const result = await makeQuery().findDetail(repositoryFullName('facebook', 'does-not-exist'))

    expect(result).toBeNull()
  })

  it('スキーマ不一致は UpstreamError を投げる', async () => {
    server.use(
      http.get('https://api.github.com/repos/:owner/:repo', () =>
        HttpResponse.json({ id: 'not-a-number' }),
      ),
    )

    await expect(makeQuery().findDetail(repositoryFullName('facebook', 'react'))).rejects.toThrow(
      UpstreamError,
    )
  })

  it('ドット入りのリポジトリ名を正しくエスケープして URL を組み立てる', async () => {
    await makeQuery().findDetail(repositoryFullName('example', 'user.github.io'))

    expect(requests[0].pathname).toBe('/repos/example/user.github.io')
  })
})
