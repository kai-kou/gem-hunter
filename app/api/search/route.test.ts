import { NextRequest } from 'next/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { SearchResult } from '@/src/domain/model/repository'
import { GET } from './route'

/**
 * `GithubRepositoryQuery` を丸ごとモックする（`vi.mock` はファイル先頭へホイストされるため
 * `describe` の外に置く）。GitHub への実 HTTP 発行を避けるための差し替え。
 * `makeInstallationTokenProvider` はコンストラクタ引数として渡されるだけでモック実装内では
 * 参照されないため、GitHub App の env 変数が未設定でも副作用は起きない。
 */
const searchMock = vi.fn()
const findDetailMock = vi.fn()
// SP-8: `GithubRepositoryQuery` のコンストラクタへ渡された `token`（`TokenProvider`）を捕まえる
// （レート枠切替・T-7 が正しい TokenProvider を container.ts から渡しているかの検証用）。
let capturedTokenProvider: (() => Promise<string | null>) | null = null

// `vi.fn().mockImplementation(() => ({...}))` を `new` すると tinyspy 経由の関数モックが
// コンストラクタ呼び出しを正しく扱えず「is not a constructor」で失敗するケースがあったため、
// 素の class を返す factory にする（`new` の意味論をそのまま満たす・素直で壊れにくい）。
vi.mock('@/src/infrastructure/github/github-repository-query', () => ({
  GithubRepositoryQuery: class {
    constructor(deps: { token: () => Promise<string | null> }) {
      capturedTokenProvider = deps.token
    }
    search(...args: unknown[]) {
      return searchMock(...args)
    }
    findDetail(...args: unknown[]) {
      return findDetailMock(...args)
    }
  },
}))

// SP-8: セッション Cookie の復号（本ファイルは Cookie を送らない既存テストが大半のため、
// 既定では null を返す実装のままにし、必要なテストだけ `mockResolvedValueOnce` で上書きする）。
const decodeSessionCookieMock = vi.fn().mockResolvedValue(null)
vi.mock('@/src/composition/auth', () => ({
  decodeSessionCookie: (...args: unknown[]) => decodeSessionCookieMock(...args),
  SESSION_COOKIE_NAME: 'gem_hunter_session',
}))

// Issue #122: `enforceSearchRateLimit`（composition root の RateLimitPort 配線）をモックする。
// 既定では超過なし（resolve）とし、超過を検証するテストだけ `mockRejectedValueOnce` で上書きする。
const enforceSearchRateLimitMock = vi.fn().mockResolvedValue(undefined)
vi.mock('@/src/composition/rate-limit', () => ({
  enforceSearchRateLimit: (...args: unknown[]) => enforceSearchRateLimitMock(...args),
}))

/**
 * `src/composition/container.ts` の `sharedCache` はモジュールスコープの単一インスタンス
 * （isolate 内で使い回す意図的な設計・`SP-5` whiteboard 決定）で、本テストファイル全体を通じて
 * 1 つを共有する（`container.ts` はテスト用の注入口を持たず、本タスクの担当スコープ外のため
 * 変更しない）。共有インスタンスでもテストが干渉しないよう、**各テストケースで一意な
 * キーワード** を使ってキャッシュキーの衝突を避ける（`vi.resetModules()` で
 * モジュールごと作り直すアプローチは、動的 re-import 後に `vi.mock` の差し替えが
 * 正しく効かないケースがあり不安定だったため採用しない）。
 */
function makeSearchResult(overrides: Partial<SearchResult> = {}): SearchResult {
  return {
    totalCount: 0,
    incompleteResults: false,
    items: [],
    ...overrides,
  }
}

beforeEach(() => {
  searchMock.mockReset()
  findDetailMock.mockReset()
  capturedTokenProvider = null
  decodeSessionCookieMock.mockReset()
  decodeSessionCookieMock.mockResolvedValue(null)
  enforceSearchRateLimitMock.mockReset()
  enforceSearchRateLimitMock.mockResolvedValue(undefined)
})

describe('GET /api/search — X-Cache-Status', () => {
  it('同一キーワードで 1 回目は MISS、2 回目は HIT を報告する', async () => {
    searchMock.mockResolvedValue(makeSearchResult({ totalCount: 3 }))

    const first = await GET(new NextRequest('http://localhost/api/search?q=cache-status-check'))
    expect(first.headers.get('X-Cache-Status')).toBe('MISS')

    const second = await GET(new NextRequest('http://localhost/api/search?q=cache-status-check'))
    expect(second.headers.get('X-Cache-Status')).toBe('HIT')

    // キャッシュが効いていれば inner (GithubRepositoryQuery#search) は 1 回しか呼ばれない
    expect(searchMock).toHaveBeenCalledTimes(1)
  })
})

/**
 * エラー応答の共通検証（Issue #107 の再発防止）。載せてよいのは `ErrorKind` と再試行情報だけで、
 * 開発者向けの `message` / `error` を含めないことを **全エラーケースで** 固定する。
 */
async function expectSafeErrorBody(res: Response, expected: Record<string, unknown>) {
  const body = await res.json()

  expect(body).not.toHaveProperty('message')
  expect(body).not.toHaveProperty('error')
  expect(body).toEqual(expected)
}

/**
 * SP-9: エラー応答は `ErrorKind`（prd.md §7）だけを返し、**生の `error.message` は載せない**
 * （内部情報の漏洩防止・Issue #107）。利用者向けの文言は画面側が kind から i18n で引く。
 */
describe('GET /api/search — エラー応答（kind とステータスの対応）', () => {
  it('DomainValidationError（空キーワード）は 400 と kind=validation を返す', async () => {
    const res = await GET(new NextRequest('http://localhost/api/search?q='))

    expect(res.status).toBe(400)
    await expectSafeErrorBody(res, { kind: 'validation' })
  })

  it('エラー応答に生の error.message を含めない（内部情報を出さない・Issue #107）', async () => {
    const { UpstreamError } = await import('@/src/domain/errors')
    searchMock.mockRejectedValue(new UpstreamError('内部の詳細メッセージ'))

    const res = await GET(new NextRequest('http://localhost/api/search?q=no-message-leak-check'))

    expect(res.status).toBe(502)
    await expectSafeErrorBody(res, { kind: 'upstream' })
  })

  it('NetworkError は 502 と kind=network を返す', async () => {
    const { NetworkError } = await import('@/src/domain/errors')
    searchMock.mockRejectedValue(new NetworkError('到達できません'))

    const res = await GET(new NextRequest('http://localhost/api/search?q=network-check'))

    expect(res.status).toBe(502)
    await expectSafeErrorBody(res, { kind: 'network' })
  })

  it('AuthError は 502 と kind=auth を返す（利用者は対処できないため汎用エラー扱い）', async () => {
    const { AuthError } = await import('@/src/domain/errors')
    searchMock.mockRejectedValue(new AuthError('認証エラー'))

    const res = await GET(new NextRequest('http://localhost/api/search?q=auth-check'))

    expect(res.status).toBe(502)
    await expectSafeErrorBody(res, { kind: 'auth' })
  })

  it('NotFoundError は 404 と kind=notFound を返す', async () => {
    const { NotFoundError } = await import('@/src/domain/errors')
    searchMock.mockRejectedValue(new NotFoundError('見つかりません'))

    const res = await GET(new NextRequest('http://localhost/api/search?q=not-found-check'))

    expect(res.status).toBe(404)
    await expectSafeErrorBody(res, { kind: 'notFound' })
  })

  it('一次レート制限は 429・復帰時刻・Retry-After ヘッダ（HTTP-date）を返す', async () => {
    const { RateLimitExceededError } = await import('@/src/domain/errors')
    const retryAfter = new Date('2026-08-19T12:00:00.000Z')
    searchMock.mockRejectedValue(new RateLimitExceededError('rateLimitPrimary', { retryAfter }))

    const res = await GET(new NextRequest('http://localhost/api/search?q=rate-limit-check'))

    expect(res.status).toBe(429)
    // `Retry-After` は秒数（delta-seconds）と HTTP-date のどちらでも有効（RFC 9110 §10.2.3）。
    // 一次レート制限は絶対時刻を持つため、"今" を計算に持ち込まない HTTP-date を使う。
    expect(res.headers.get('Retry-After')).toBe(retryAfter.toUTCString())
    await expectSafeErrorBody(res, {
      kind: 'rateLimitPrimary',
      retryAfter: retryAfter.toISOString(),
    })
  })

  it('二次レート制限は 429・待機秒数・Retry-After ヘッダ（秒数）を返す', async () => {
    const { RateLimitExceededError } = await import('@/src/domain/errors')
    searchMock.mockRejectedValue(
      new RateLimitExceededError('rateLimitSecondary', { retryAfterSeconds: 60 }),
    )

    const res = await GET(
      new NextRequest('http://localhost/api/search?q=rate-limit-secondary-check'),
    )

    expect(res.status).toBe(429)
    expect(res.headers.get('Retry-After')).toBe('60')
    await expectSafeErrorBody(res, { kind: 'rateLimitSecondary', retryAfterSeconds: 60 })
  })

  it('再試行情報の無いレート制限は Retry-After ヘッダを付けない', async () => {
    const { RateLimitExceededError } = await import('@/src/domain/errors')
    searchMock.mockRejectedValue(new RateLimitExceededError('rateLimitSecondary'))

    const res = await GET(
      new NextRequest('http://localhost/api/search?q=rate-limit-no-header-check'),
    )

    expect(res.status).toBe(429)
    expect(res.headers.get('Retry-After')).toBeNull()
    await expectSafeErrorBody(res, { kind: 'rateLimitSecondary' })
  })

  it('復帰時刻が不正な Date でも 500 にせず、復帰時刻不明として扱う（Invalid Date 防御）', async () => {
    const { RateLimitExceededError } = await import('@/src/domain/errors')
    searchMock.mockRejectedValue(
      new RateLimitExceededError('rateLimitPrimary', {
        retryAfter: new Date(Number.NaN),
        retryAfterSeconds: 30,
      }),
    )

    const res = await GET(new NextRequest('http://localhost/api/search?q=invalid-reset-check'))

    expect(res.status).toBe(429)
    // Invalid Date を `toISOString()` に通すと RangeError（未処理例外 → 500）になるため、
    // 復帰時刻は載せず秒数だけを返す。
    expect(res.headers.get('Retry-After')).toBe('30')
    await expectSafeErrorBody(res, { kind: 'rateLimitPrimary', retryAfterSeconds: 30 })
  })

  it('UpstreamError は 502 と kind=upstream を返す', async () => {
    const { UpstreamError } = await import('@/src/domain/errors')
    searchMock.mockRejectedValue(new UpstreamError('上流エラー'))

    const res = await GET(new NextRequest('http://localhost/api/search?q=upstream-check'))

    expect(res.status).toBe(502)
    await expectSafeErrorBody(res, { kind: 'upstream' })
  })
})

describe('GET /api/search — SP-8: レート枠切替（セッション Cookie → TokenProvider）', () => {
  it('セッション Cookie が無ければ TokenProvider はユーザートークンを返さない（installation token 側へ委ねる）', async () => {
    searchMock.mockResolvedValue(makeSearchResult())

    await GET(new NextRequest('http://localhost/api/search?q=no-session-check'))

    expect(decodeSessionCookieMock).not.toHaveBeenCalled()
  })

  it('セッション Cookie を復号できたら、その accessToken を返す TokenProvider で検索する', async () => {
    decodeSessionCookieMock.mockResolvedValueOnce({ accessToken: 'gho_session_token' })
    searchMock.mockResolvedValue(makeSearchResult())

    await GET(
      new NextRequest('http://localhost/api/search?q=session-check', {
        headers: { cookie: 'gem_hunter_session=encrypted-value' },
      }),
    )

    expect(decodeSessionCookieMock).toHaveBeenCalledWith('encrypted-value')
    expect(capturedTokenProvider).not.toBeNull()
    await expect(capturedTokenProvider!()).resolves.toBe('gho_session_token')
  })

  it('セッション Cookie の復号に失敗（null）した場合は installation token 側へ委ねる', async () => {
    decodeSessionCookieMock.mockResolvedValueOnce(null)
    searchMock.mockResolvedValue(makeSearchResult())

    await GET(
      new NextRequest('http://localhost/api/search?q=invalid-session-check', {
        headers: { cookie: 'gem_hunter_session=tampered-value' },
      }),
    )

    expect(decodeSessionCookieMock).toHaveBeenCalledWith('tampered-value')
  })
})

/**
 * Issue #122: composition root の `enforceSearchRateLimit`（RateLimitPort の配線）が
 * 検証後・GitHub API 呼び出し前の位置で実際に呼ばれること、超過時に既存の
 * `RateLimitExceededError` ハンドリング（429 + Retry-After・prd.md §7）へそのまま乗ることを検証する。
 */
describe('GET /api/search — Issue #122: RateLimitPort の配線', () => {
  it('レート制限超過時に 429・Retry-After（秒数）・kind=rateLimitSecondary を返す', async () => {
    const { RateLimitExceededError } = await import('@/src/domain/errors')
    enforceSearchRateLimitMock.mockRejectedValueOnce(
      new RateLimitExceededError('rateLimitSecondary', { retryAfterSeconds: 60 }),
    )

    const res = await GET(new NextRequest('http://localhost/api/search?q=rate-limit-port-check'))

    expect(res.status).toBe(429)
    expect(res.headers.get('Retry-After')).toBe('60')
    await expectSafeErrorBody(res, { kind: 'rateLimitSecondary', retryAfterSeconds: 60 })
    // 超過時は GitHub API を叩く前に間引かれるため、内側の search() は呼ばれない。
    expect(searchMock).not.toHaveBeenCalled()
  })

  it('レート制限が超過していなければ従来どおり 200 を返し、enforceSearchRateLimit が1回だけ呼ばれる', async () => {
    searchMock.mockResolvedValue(makeSearchResult({ totalCount: 1 }))

    const res = await GET(new NextRequest('http://localhost/api/search?q=rate-limit-port-ok-check'))

    expect(res.status).toBe(200)
    expect(enforceSearchRateLimitMock).toHaveBeenCalledTimes(1)
  })

  it('入力が不正（空キーワード）で 400 になるときは enforceSearchRateLimit を呼ばない（枠を消費しない）', async () => {
    const res = await GET(new NextRequest('http://localhost/api/search?q='))

    expect(res.status).toBe(400)
    expect(enforceSearchRateLimitMock).not.toHaveBeenCalled()
  })

  it('撤去済みの ?sort=gem-index を付けても 500 にならず 200 を返す（SortOrder のフォールバックで relevance 扱い・後方互換）', async () => {
    searchMock.mockResolvedValue(makeSearchResult())

    const res = await GET(
      new NextRequest('http://localhost/api/search?q=gem-index-removed-check&sort=gem-index'),
    )

    expect(res.status).toBe(200)
    expect(enforceSearchRateLimitMock).toHaveBeenCalledTimes(1)
  })
})
