import { HttpResponse, http } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

import {
  getRepositoryDetailUseCase,
  lookupGemIndexes,
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
  // 🔴 `private` は詳細 DTO で必須（NFR-33 / AC-12 の fail-closed 判定に使う）。実 API の
  //    `GET /repos/{owner}/{repo}` は常にこの値を返すため、フィクスチャにも必ず持たせる。
  private: false,
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

/**
 * SP-18: 検索結果カードの Gem バッジ（`D-36` / `D-38`）が引く照会口の配線。
 *
 * 🔴 **実データの中身に依存させない**（`public/data/gem-index/` の候補プールは
 * `tools/gem-pool/pipeline.mjs` が定期再生成するため、「この名前は必ず載っている」を
 * 前提にすると再生成のたびにテストが落ちる）。ここで固定するのは母集団が変わっても
 * 成立する不変条件だけ:
 *   ① 例外を投げない（`GemIndexPort` の SPOF 方針: 失敗しても空 Map・検索は止めない）
 *   ② 返り値が `Map` である（呼び出し側が `.get()` / `.has()` で引ける）
 *   ③ プールに載っていない名前はキーに入らない
 * ネットワークを踏まないことは、このファイル冒頭の msw
 * （`onUnhandledRequest: 'error'`）が未登録リクエストを失敗させることで担保される。
 */
describe('lookupGemIndexes — Gem バッジ判定材料の照会（SP-18）', () => {
  it('空配列を渡しても throw せず、空の Map を返す', async () => {
    const indexes = await lookupGemIndexes([])

    expect(indexes).toBeInstanceOf(Map)
    expect(indexes.size).toBe(0)
  })

  it('候補プールに載っていない名前を渡しても throw せず、その名前をキーに持たない Map を返す', async () => {
    // E2E スタブと同じ架空のオーナー。実プール（Ecosyste.ms 由来）には存在し得ない。
    const missing = 'octostub/not-in-the-gem-pool'

    const indexes = await lookupGemIndexes([missing])

    expect(indexes).toBeInstanceOf(Map)
    expect(indexes.has(missing)).toBe(false)
    expect(indexes.get(missing)).toBeUndefined()
  })

  it('同じ照会口（モジュールスコープの単一インスタンス）を 2 回呼んでも結果が変わらない', async () => {
    // `sharedGemIndexPort` を関数内で `new` すると（= 使い回しをやめると）シャードの
    // 再パースが毎回走る。結果の同一性を固定して、その退行を検知できるようにする。
    const names = ['octostub/not-in-the-gem-pool']

    const first = await lookupGemIndexes(names)
    const second = await lookupGemIndexes(names)

    expect([...second.keys()]).toEqual([...first.keys()])
  })
})
