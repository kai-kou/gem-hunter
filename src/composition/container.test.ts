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

/**
 * Issue #121: `sharedCache` の実装選択（Cloudflare Cache API / isolate 内メモリ）。
 *
 * 🔴 **「どのクラスの instanceof か」ではなく「実際に何を呼んだか」で判定する**
 * （型だけ合っていて呼ばれていない配線を素通りさせないため）。Cache API 側は fake の
 * `put` / `match` が実際に呼ばれたかを、フォールバック側は上流 API の呼び出し回数と
 * `console.warn` の発火で観測する。
 *
 * `sharedCache` はモジュールスコープの単一インスタンスで、実装の解決結果も
 * モジュール内でメモ化されるため、各ケースは `vi.resetModules()` + 動的 import で
 * 「まっさらな isolate 起動」を再現する。
 */
describe('sharedCache の実装選択（Cache API の有無・Issue #121）', () => {
  type CachesGlobal = { caches?: unknown }

  /** `caches.default` の fake（呼び出しを記録する。終了値の差し替えだけにしない）。 */
  function fakeCacheApi() {
    const entries = new Map<string, string>()
    const puts: string[] = []
    const matches: string[] = []
    const deletes: string[] = []
    return {
      puts,
      matches,
      deletes,
      default: {
        async put(request: Request, response: Response): Promise<void> {
          puts.push(request.url)
          entries.set(request.url, await response.text())
        },
        async match(request: Request): Promise<Response | undefined> {
          matches.push(request.url)
          const body = entries.get(request.url)
          return body === undefined ? undefined : new Response(body)
        },
        async delete(request: Request): Promise<boolean> {
          deletes.push(request.url)
          return entries.delete(request.url)
        },
      },
    }
  }

  const originalCachesDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'caches')

  /** installation token の資格情報を明示的に未設定にする（環境差で余計な通信を起こさない）。 */
  function stubGithubAppEnvEmpty() {
    vi.stubEnv('GITHUB_APP_CLIENT_ID', '')
    vi.stubEnv('GITHUB_APP_INSTALLATION_ID', '')
    vi.stubEnv('GITHUB_APP_PRIVATE_KEY_PKCS8', '')
  }

  /** 上流 GitHub 検索 API のハンドラを張り、呼ばれた回数を返す。 */
  function countUpstreamSearchCalls(): { get count(): number } {
    let calls = 0
    server.use(
      http.get('https://api.github.com/search/repositories', () => {
        calls += 1
        return HttpResponse.json(emptySearchResponse)
      }),
    )
    return {
      get count() {
        return calls
      },
    }
  }

  afterEach(() => {
    // 他テストへ漏らさない（`caches` は本 describe 内でしか差し替えない）。
    if (originalCachesDescriptor) {
      Object.defineProperty(globalThis, 'caches', originalCachesDescriptor)
    } else {
      delete (globalThis as CachesGlobal).caches
    }
    vi.resetModules()
  })

  it('caches.default が使える環境では 2 段目（Cache API）へ実際に put / match する', async () => {
    stubGithubAppEnvEmpty()
    const fake = fakeCacheApi()
    ;(globalThis as CachesGlobal).caches = { default: fake.default }
    vi.resetModules()
    const container = await import('./container')
    const upstream = countUpstreamSearchCalls()
    const keyword = 'container-cache-api-hit'

    const first = container.searchRepositoriesWithCacheStatus()
    await first.search({ keyword })

    expect(first.getCacheStatus()).toBe('MISS')
    // 型ではなく「Cache API が実際に呼ばれたか」で配線を判定する。
    // 1 段目（isolate 内メモリ）が MISS したので 2 段目が引かれ、両段へ書かれる。
    expect(fake.matches).toHaveLength(1)
    expect(fake.puts).toHaveLength(1)
    expect(fake.puts[0]).toMatch(/^https:\/\/cache\.gem-hunter\.internal\//)

    const second = container.searchRepositoriesWithCacheStatus()
    await second.search({ keyword })

    expect(second.getCacheStatus()).toBe('HIT')
    // 🔴 2 回目は 1 段目で HIT するので Cache API は引かれない（往復を省く）。
    expect(fake.matches).toHaveLength(1)
    expect(upstream.count).toBe(1)
  })

  it('Cache API 側は isolate をまたいで共有される（別 isolate 相当の再 import で HIT する）', async () => {
    stubGithubAppEnvEmpty()
    // fake は同一インスタンスのまま、container だけ読み込み直す
    // （= isolate 内メモリは空・Cache API のエントリは残っている状況を再現する）。
    const fake = fakeCacheApi()
    ;(globalThis as CachesGlobal).caches = { default: fake.default }
    const keyword = 'container-cache-cross-isolate'

    vi.resetModules()
    const containerA = await import('./container')
    const upstream = countUpstreamSearchCalls()
    await containerA.searchRepositoriesUseCase()({ keyword })
    expect(upstream.count).toBe(1)

    vi.resetModules()
    const containerB = await import('./container')
    const second = containerB.searchRepositoriesWithCacheStatus()
    await second.search({ keyword })

    expect(second.getCacheStatus()).toBe('HIT')
    // 上流 API は増えない（Cache API 経由で別 isolate へ引き継がれた）
    expect(upstream.count).toBe(1)
    expect(fake.matches).toHaveLength(2)
  })

  it('caches が無い環境では InMemoryCache へフォールバックし、console.warn で表明する', async () => {
    stubGithubAppEnvEmpty()
    delete (globalThis as CachesGlobal).caches
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    try {
      vi.resetModules()
      const container = await import('./container')
      const upstream = countUpstreamSearchCalls()
      const keyword = 'container-cache-fallback'

      const first = container.searchRepositoriesWithCacheStatus()
      await first.search({ keyword })
      const second = container.searchRepositoriesWithCacheStatus()
      await second.search({ keyword })

      // フォールバックしても機能としてのキャッシュは効く（isolate 内では HIT する）。
      expect(first.getCacheStatus()).toBe('MISS')
      expect(second.getCacheStatus()).toBe('HIT')
      expect(upstream.count).toBe(1)

      // 🔴 フォールバックが黙って隠れないこと（本番 Workers で出ていたら判定が壊れている）。
      expect(warn).toHaveBeenCalledTimes(1)
      expect(String(warn.mock.calls[0]?.[0])).toContain('[cache]')
    } finally {
      warn.mockRestore()
    }
  })

  it('caches.default がメソッドを揃えていなければフォールバックする（put is not a function を実行時に出さない）', async () => {
    stubGithubAppEnvEmpty()
    ;(globalThis as CachesGlobal).caches = { default: { match: () => undefined } }
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    try {
      vi.resetModules()
      const container = await import('./container')
      const upstream = countUpstreamSearchCalls()
      const keyword = 'container-cache-partial-default'

      const first = container.searchRepositoriesWithCacheStatus()
      await first.search({ keyword })
      const second = container.searchRepositoriesWithCacheStatus()
      await second.search({ keyword })

      expect(second.getCacheStatus()).toBe('HIT')
      expect(upstream.count).toBe(1)
      expect(warn).toHaveBeenCalledTimes(1)
    } finally {
      warn.mockRestore()
    }
  })

  it('実装の判定は初回利用時の 1 回だけで、2 回目以降は再判定しない（メモ化）', async () => {
    stubGithubAppEnvEmpty()
    const fake = fakeCacheApi()
    let cachesAccesses = 0
    Object.defineProperty(globalThis, 'caches', {
      configurable: true,
      get() {
        cachesAccesses += 1
        return { default: fake.default }
      },
    })
    vi.resetModules()
    const container = await import('./container')
    countUpstreamSearchCalls()

    await container.searchRepositoriesUseCase()({ keyword: 'container-cache-memo-1' })
    await container.searchRepositoriesUseCase()({ keyword: 'container-cache-memo-2' })

    // `set` / `get` が複数回走っても、`globalThis.caches` を読むのは初回解決の 1 度だけ。
    expect(cachesAccesses).toBe(1)
    expect(fake.matches.length).toBeGreaterThanOrEqual(2)
  })
})
