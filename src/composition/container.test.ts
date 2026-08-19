import { HttpResponse, http } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

import {
  getRepositoryDetailUseCase,
  searchRepositoriesUseCase,
  searchRepositoriesWithCacheStatus,
} from './container'

/**
 * SP-8: レート枠切替（`accessToken` を渡すと installation token ではなくユーザーの
 * アクセストークンで GitHub API を叩く）。`sharedCache` はモジュールスコープの単一
 * インスタンスなので、テストケースごとに一意なキーワード/リポジトリ名を使って
 * キャッシュ衝突を避ける（`app/api/search/route.test.ts` と同じ方針）。
 */
const emptySearchResponse = { total_count: 0, incomplete_results: false, items: [] }
const detailFixture = {
  id: 1,
  name: 'octo-token-check',
  full_name: 'octostub/octo-token-check',
  html_url: 'https://github.com/octostub/octo-token-check',
  description: null,
  language: null,
  stargazers_count: 0,
  watchers_count: 0,
  subscribers_count: 0,
  forks_count: 0,
  open_issues_count: 0,
  updated_at: '2026-01-01T00:00:00Z',
  pushed_at: '2026-01-01T00:00:00Z',
  topics: [],
  owner: { login: 'octostub', avatar_url: 'https://example.test/avatar.png' },
}

const server = setupServer()

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => {
  server.resetHandlers()
  vi.unstubAllEnvs()
})
afterAll(() => server.close())

describe('searchRepositoriesUseCase — TokenProvider 切替', () => {
  it('accessToken を渡すと installation token ではなくその値で Authorization ヘッダを送る', async () => {
    // installation token 側の資格情報を明示的に未設定にする（環境差でテストが揺れないように）。
    vi.stubEnv('GITHUB_APP_CLIENT_ID', '')
    vi.stubEnv('GITHUB_APP_INSTALLATION_ID', '')
    vi.stubEnv('GITHUB_APP_PRIVATE_KEY_PKCS8', '')

    let capturedAuth: string | null = null
    server.use(
      http.get('https://api.github.com/search/repositories', ({ request }) => {
        capturedAuth = request.headers.get('authorization')
        return HttpResponse.json(emptySearchResponse)
      }),
    )

    await searchRepositoriesUseCase('user-access-token-1')({ keyword: 'container-token-check-1' })

    expect(capturedAuth).toBe('Bearer user-access-token-1')
  })

  it('accessToken を渡さない場合は installation token 資格情報が無ければ Authorization ヘッダを付けない', async () => {
    vi.stubEnv('GITHUB_APP_CLIENT_ID', '')
    vi.stubEnv('GITHUB_APP_INSTALLATION_ID', '')
    vi.stubEnv('GITHUB_APP_PRIVATE_KEY_PKCS8', '')

    let capturedAuth: string | null = null
    server.use(
      http.get('https://api.github.com/search/repositories', ({ request }) => {
        capturedAuth = request.headers.get('authorization')
        return HttpResponse.json(emptySearchResponse)
      }),
    )

    await searchRepositoriesUseCase()({ keyword: 'container-token-check-2' })

    expect(capturedAuth).toBeNull()
  })
})

describe('getRepositoryDetailUseCase — TokenProvider 切替', () => {
  it('accessToken を渡すとその値で詳細取得の Authorization ヘッダを送る', async () => {
    let capturedAuth: string | null = null
    server.use(
      http.get('https://api.github.com/repos/:owner/:repo', ({ request }) => {
        capturedAuth = request.headers.get('authorization')
        return HttpResponse.json(detailFixture)
      }),
    )

    await getRepositoryDetailUseCase('user-access-token-2')({
      owner: 'octostub',
      repo: 'octo-token-check-detail',
    })

    expect(capturedAuth).toBe('Bearer user-access-token-2')
  })
})

describe('searchRepositoriesWithCacheStatus — TokenProvider 切替', () => {
  it('accessToken を渡すとその値で Authorization ヘッダを送る（X-Cache-Status 観測と両立する）', async () => {
    let capturedAuth: string | null = null
    server.use(
      http.get('https://api.github.com/search/repositories', ({ request }) => {
        capturedAuth = request.headers.get('authorization')
        return HttpResponse.json(emptySearchResponse)
      }),
    )

    const { search, getCacheStatus } = searchRepositoriesWithCacheStatus('user-access-token-3')
    await search({ keyword: 'container-token-check-3' })

    expect(capturedAuth).toBe('Bearer user-access-token-3')
    expect(getCacheStatus()).toBe('MISS')
  })
})
