import { HttpResponse, http } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

import { DEFAULT_REFILL_TTL_SECONDS } from '../infrastructure/platform/layered-cache'
import { fakeCacheStorage } from '../infrastructure/platform/workers-cache.test-fake'
import {
  TTL_DETAIL_SECONDS,
  TTL_SEARCH_SECONDS,
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

/**
 * `items` を 1 件持つ検索レスポンス（Issue #121 のキャッシュ経路テスト用）。
 *
 * 🔴 **`pushed_at` を持たせるのが要点**: マッパーはこれを `RepositorySummary.lastPushedAt`
 * （`Date`）へ写すため、キャッシュ往復で `Date` が壊れる欠陥（JSON 直列化で ISO 文字列に
 * 化ける）を戻り値の型で検知できる。空 `items` のレスポンスでは検知できない。
 */
const searchResponseWithOneItem = {
  total_count: 1,
  incomplete_results: false,
  items: [
    {
      id: 10270250,
      name: 'react',
      full_name: 'facebook/react',
      html_url: 'https://github.com/facebook/react',
      description: 'The library for web and native user interfaces.',
      language: 'JavaScript',
      stargazers_count: 233000,
      updated_at: '2026-08-18T09:00:00Z',
      pushed_at: '2026-08-15T03:00:00Z',
      private: false,
      topics: ['javascript', 'react'],
      owner: { login: 'facebook', avatar_url: 'https://avatars.githubusercontent.com/u/69631?v=4' },
    },
  ],
}
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

/**
 * PR #926 Layer 1 セルフレビュー指摘 #9: `container.test.ts` に `etag` / `If-None-Match`
 * の言及が 0 件で、composition root の ETag 配線（`container.ts` が `GithubRepositoryQuery`
 * へ `etag: { cache: sharedCache, ttlSeconds: TTL_DETAIL_ETAG_SECONDS }` を渡す配線）を
 * 消しても単体テストは全て緑のまま通ってしまう欠落があった。
 *
 * 公開エクスポート（`getRepositoryDetailUseCase`）経由で実際に `If-None-Match` が送られる
 * ことを確認する。`CachingRepositoryQuery` の本文 TTL キャッシュ（`TTL_DETAIL_SECONDS` = 300 秒）
 * が経路を塞ぐため、`Date` だけを偽装して本文 TTL を経過させ、外側キャッシュを MISS へ
 * 戻す（ETag ストア側の TTL は 24 時間のため生存する・`cache-key.ts` の invalidate 契約と同型）。
 * `setTimeout` 等は fake 化しない（`toFake: ['Date']`）ため msw 経由の fetch は通常どおり動く。
 */
describe('composition root: GithubRepositoryQuery への ETag 配線（PR #926 レビュー指摘 #9）', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('本文 TTL 経過後の再取得で If-None-Match ヘッダーが送られる（配線が生きていることの確認）', async () => {
    vi.stubEnv('GITHUB_APP_CLIENT_ID', '')
    vi.stubEnv('GITHUB_APP_INSTALLATION_ID', '')
    vi.stubEnv('GITHUB_APP_PRIVATE_KEY_PKCS8', '')

    const owner = 'octostub'
    const repo = 'container-etag-wiring-check'
    let etagSent = false
    server.use(
      http.get('https://api.github.com/repos/:owner/:repo', ({ request }) => {
        if (request.headers.has('if-none-match')) {
          etagSent = true
          return new HttpResponse(null, { status: 304 })
        }
        return HttpResponse.json(
          {
            ...detailFixture,
            full_name: `${owner}/${repo}`,
            name: repo,
            owner: { ...detailFixture.owner, login: owner },
          },
          { headers: { etag: 'W/"container-wiring-etag"' } },
        )
      }),
    )

    const first = await getRepositoryDetailUseCase('user-etag-wiring-token')({ owner, repo })
    expect(first?.fullName).toBe(`${owner}/${repo}`)
    expect(etagSent).toBe(false)

    // 本文 TTL（300 秒）を経過させ、CachingRepositoryQuery の外側キャッシュを MISS に
    // 戻す。ETag ストア（24 時間 TTL）は同じ sharedCache 上の別名前空間なので生存する。
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(Date.now() + (TTL_DETAIL_SECONDS + 1) * 1000)

    const second = await getRepositoryDetailUseCase('user-etag-wiring-token')({ owner, repo })

    expect(etagSent).toBe(true)
    expect(second?.fullName).toBe(`${owner}/${repo}`)
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

  /**
   * `caches.default` の fake は `workers-cache.test.ts` と **同じ実装を共有する**
   * （`workers-cache.test-fake.ts`）。
   *
   * 🔴 以前ここに置いていた自前の fake は `Cache-Control` を一切見ない劣化コピーで、
   * `max-age` の計算を壊す変異が container 側では緑のまま通っていた（PR #874 レビュー F9）。
   * 共有 fake は `max-age` を解釈して期限判定するため、TTL 経過で MISS になることも試せる。
   */

  const originalCachesDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'caches')

  /** installation token の資格情報を明示的に未設定にする（環境差で余計な通信を起こさない）。 */
  function stubGithubAppEnvEmpty() {
    vi.stubEnv('GITHUB_APP_CLIENT_ID', '')
    vi.stubEnv('GITHUB_APP_INSTALLATION_ID', '')
    vi.stubEnv('GITHUB_APP_PRIVATE_KEY_PKCS8', '')
  }

  /**
   * 上流 GitHub 検索 API のハンドラを張り、呼ばれた回数を返す。
   *
   * 🔴 既定で **`items` を 1 件返す**（`pushed_at` 付き）。空配列を返していると
   * `WorkersCache.get` を `return {} as T` に潰す変異でも「上流呼び出し回数」と
   * `X-Cache-Status` だけは一致してしまい、2 段目 HIT が壊れていることを検知できない
   * （`Date` が ISO 文字列へ化ける欠陥もここをすり抜けた・PR #874 レビュー F8）。
   */
  function countUpstreamSearchCalls(): { get count(): number } {
    let calls = 0
    server.use(
      http.get('https://api.github.com/search/repositories', () => {
        calls += 1
        return HttpResponse.json(searchResponseWithOneItem)
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
    const fake = fakeCacheStorage()
    ;(globalThis as CachesGlobal).caches = { default: fake.storage }
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
    expect(fake.puts[0]!.url).toMatch(/^https:\/\/cache\.gem-hunter\.internal\//)

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
    const fake = fakeCacheStorage()
    ;(globalThis as CachesGlobal).caches = { default: fake.storage }
    const keyword = 'container-cache-cross-isolate'

    vi.resetModules()
    const containerA = await import('./container')
    const upstream = countUpstreamSearchCalls()
    const first = await containerA.searchRepositoriesUseCase()({ keyword })
    expect(upstream.count).toBe(1)

    vi.resetModules()
    const containerB = await import('./container')
    const cached = containerB.searchRepositoriesWithCacheStatus()
    const second = await cached.search({ keyword })

    expect(cached.getCacheStatus()).toBe('HIT')
    // 上流 API は増えない（Cache API 経由で別 isolate へ引き継がれた）
    expect(upstream.count).toBe(1)
    expect(fake.matches).toHaveLength(2)

    // 🔴 **戻り値そのものを突き合わせる**（PR #874 レビュー F8）。`X-Cache-Status` と
    //    上流呼び出し回数だけを見ていると、2 段目が壊れた値（`{}` や ISO 文字列化した
    //    `Date`）を返していても全緑になる。
    expect(second.totalCount).toBe(first.totalCount)
    expect(second.items).toHaveLength(first.items.length)
    expect(second.items[0]!.fullName).toBe(first.items[0]!.fullName)
    expect(second.items[0]!.stars).toBe(first.items[0]!.stars)
    // 🔴 `Date` は JSON 往復で復元されない。`instanceof` と実値の両方を見る
    //    （`toEqual` だけだと ISO 文字列との差を見逃す場合がある）。
    expect(second.items[0]!.lastPushedAt).toBeInstanceOf(Date)
    expect(second.items[0]!.lastPushedAt.getTime()).toBe(first.items[0]!.lastPushedAt.getTime())
    expect(second.items[0]!.lastPushedAt.getTime()).toBe(Date.parse('2026-08-15T03:00:00Z'))
  })

  it('2 段目のエントリも TTL で失効する（別 isolate でも TTL 経過後は MISS）', async () => {
    stubGithubAppEnvEmpty()
    const fake = fakeCacheStorage()
    ;(globalThis as CachesGlobal).caches = { default: fake.storage }
    const keyword = 'container-cache-secondary-ttl'

    vi.resetModules()
    const containerA = await import('./container')
    const upstream = countUpstreamSearchCalls()
    await containerA.searchRepositoriesUseCase()({ keyword })
    expect(upstream.count).toBe(1)

    // 検索 TTL（60 秒）を跨がせる。fake は `Cache-Control: max-age` を解釈して期限判定する。
    fake.advance((TTL_SEARCH_SECONDS + 1) * 1000)

    vi.resetModules()
    const containerB = await import('./container')
    const cached = containerB.searchRepositoriesWithCacheStatus()
    await cached.search({ keyword })

    expect(cached.getCacheStatus()).toBe('MISS')
    expect(upstream.count).toBe(2)
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
    const fake = fakeCacheStorage()
    let cachesAccesses = 0
    Object.defineProperty(globalThis, 'caches', {
      configurable: true,
      get() {
        cachesAccesses += 1
        return { default: fake.storage }
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

  it('Cache API が使えないときは判定をメモ化しない（後から注入されたら 2 段目を使う）', async () => {
    stubGithubAppEnvEmpty()
    delete (globalThis as CachesGlobal).caches
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    try {
      vi.resetModules()
      const container = await import('./container')
      const upstream = countUpstreamSearchCalls()

      // 1 回目: `caches` が無いのでフォールバック（2 段目は無い）。
      await container.searchRepositoriesUseCase()({ keyword: 'container-cache-late-inject-1' })

      // 🔴 実行環境が後から `caches` を注入する（判定を実行時へ遅らせた狙い）。
      const fake = fakeCacheStorage()
      ;(globalThis as CachesGlobal).caches = { default: fake.storage }
      await container.searchRepositoriesUseCase()({ keyword: 'container-cache-late-inject-2' })

      // フォールバック結果までメモ化していると、この isolate は永久に 2 段目を失う。
      expect(fake.puts.length).toBeGreaterThanOrEqual(1)
      expect(upstream.count).toBe(2)
      // 警告は毎回ではなく 1 回だけ（ログ氾濫を避ける）。
      expect(warn).toHaveBeenCalledTimes(1)
    } finally {
      warn.mockRestore()
    }
  })

  it('LayeredCache の充填 TTL は検索 TTL（TTL_SEARCH_SECONDS）を超えない', () => {
    // 🔴 `container.ts` が `refillTtlSeconds: TTL_SEARCH_SECONDS` を明示注入している前提の
    //    上限ガード（PR #874 レビュー F6 / F10）。既定値が検索 TTL より長くなると、充填した
    //    primary のコピーが「今 secondary へ新規に書いた場合の寿命」を超えて生き残る。
    expect(DEFAULT_REFILL_TTL_SECONDS).toBeLessThanOrEqual(TTL_SEARCH_SECONDS)
  })
})
