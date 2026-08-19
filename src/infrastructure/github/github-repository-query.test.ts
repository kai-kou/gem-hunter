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
    expect(requests[0].searchParams.get('per_page')).toBe('20')
  })

  it('perPage を per_page パラメータへそのまま渡す', async () => {
    await makeQuery().search(searchQuery({ keyword: 'react', perPage: 100 }))

    expect(requests[0].searchParams.get('per_page')).toBe('100')
  })

  it('sort が relevance のときは sort / order パラメータを付けない（GitHub の既定挙動に委ねる）', async () => {
    await makeQuery().search(searchQuery({ keyword: 'react', sort: 'relevance' }))

    expect(requests[0].searchParams.has('sort')).toBe(false)
    expect(requests[0].searchParams.has('order')).toBe(false)
  })

  it('sort が stars のときは sort=stars&order=desc を付ける', async () => {
    await makeQuery().search(searchQuery({ keyword: 'react', sort: 'stars' }))

    expect(requests[0].searchParams.get('sort')).toBe('stars')
    expect(requests[0].searchParams.get('order')).toBe('desc')
  })

  it('sort が updated のときは sort=updated&order=desc を付ける', async () => {
    await makeQuery().search(searchQuery({ keyword: 'react', sort: 'updated' }))

    expect(requests[0].searchParams.get('sort')).toBe('updated')
    expect(requests[0].searchParams.get('order')).toBe('desc')
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

describe('GITHUB_API_ORIGIN 環境変数によるオリジン切り替え（E2E でスタブへ向けるため）', () => {
  const STUB_ORIGIN = 'http://127.0.0.1:8788'
  const originalEnv = process.env.GITHUB_API_ORIGIN

  afterEach(() => {
    if (originalEnv === undefined) {
      delete process.env.GITHUB_API_ORIGIN
    } else {
      process.env.GITHUB_API_ORIGIN = originalEnv
    }
  })

  it('GITHUB_API_ORIGIN が設定されていれば、そのオリジンへ検索リクエストする', async () => {
    process.env.GITHUB_API_ORIGIN = STUB_ORIGIN
    server.use(
      http.get(`${STUB_ORIGIN}/search/repositories`, ({ request }) => {
        requests.push(new URL(request.url))
        return HttpResponse.json(fixture)
      }),
    )

    const result = await makeQuery().search(searchQuery({ keyword: 'react' }))

    expect(result.items).toHaveLength(2)
    expect(requests[0].origin).toBe(STUB_ORIGIN)
  })

  it('GITHUB_API_ORIGIN が設定されていれば、そのオリジンへ詳細リクエストする', async () => {
    process.env.GITHUB_API_ORIGIN = STUB_ORIGIN
    server.use(
      http.get(`${STUB_ORIGIN}/repos/:owner/:repo`, ({ request }) => {
        requests.push(new URL(request.url))
        return HttpResponse.json(detailFixture)
      }),
    )

    const result = await makeQuery().findDetail(repositoryFullName('facebook', 'react'))

    expect(result?.fullName).toBe('facebook/react')
    expect(requests[0].origin).toBe(STUB_ORIGIN)
  })

  it('GITHUB_API_ORIGIN 未設定なら既定の https://api.github.com へリクエストする（回帰防止）', async () => {
    delete process.env.GITHUB_API_ORIGIN

    await makeQuery().search(searchQuery({ keyword: 'react' }))

    expect(requests[0].origin).toBe('https://api.github.com')
  })

  it('GITHUB_API_ORIGIN がループバック（http://localhost:8788）ならそのオリジンへリクエストする', async () => {
    const origin = 'http://localhost:8788'
    process.env.GITHUB_API_ORIGIN = origin
    server.use(
      http.get(`${origin}/search/repositories`, ({ request }) => {
        requests.push(new URL(request.url))
        return HttpResponse.json(fixture)
      }),
    )

    const result = await makeQuery().search(searchQuery({ keyword: 'react' }))

    expect(result.items).toHaveLength(2)
    expect(requests[0].origin).toBe(origin)
  })

  // 注: msw（path-to-regexp）が `[::1]` を含む URL のハンドラ登録に対応していないため、
  // ここでは「オリジン検証を通過し実際に fetch まで進むか」だけを確認する（実接続の成否は問わない）。
  it('GITHUB_API_ORIGIN が ::1（IPv6 ループバック）でも拒否されない（接続失敗はしてよい）', async () => {
    process.env.GITHUB_API_ORIGIN = 'http://[::1]:8788'

    await expect(makeQuery().search(searchQuery({ keyword: 'react' }))).rejects.not.toThrow(
      /GITHUB_API_ORIGIN/,
    )
  })

  it('GITHUB_API_ORIGIN に外部ホストを設定すると、トークン漏洩防止のため例外を投げる', async () => {
    process.env.GITHUB_API_ORIGIN = 'https://attacker.example'

    await expect(makeQuery().search(searchQuery({ keyword: 'react' }))).rejects.toThrow(
      /GITHUB_API_ORIGIN/,
    )
  })

  it('GITHUB_API_ORIGIN が不正な URL 形式だと例外を投げる', async () => {
    process.env.GITHUB_API_ORIGIN = 'not a url'

    await expect(makeQuery().search(searchQuery({ keyword: 'react' }))).rejects.toThrow(
      /GITHUB_API_ORIGIN/,
    )
  })
})
