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

describe('GET /api/search — domainErrorStatus のステータス分岐', () => {
  it('DomainValidationError（空キーワード）は 400 を返す', async () => {
    const res = await GET(new NextRequest('http://localhost/api/search?q='))

    expect(res.status).toBe(400)
    const body = (await res.json()) as { error: string }
    expect(body.error).toContain('検索キーワードを入力してください')
  })

  it('NotFoundError は 404 を返す', async () => {
    const { NotFoundError } = await import('@/src/domain/errors')
    searchMock.mockRejectedValue(new NotFoundError('見つかりません'))

    const res = await GET(new NextRequest('http://localhost/api/search?q=not-found-check'))

    expect(res.status).toBe(404)
  })

  it('RateLimitExceededError は 429 と Retry-After ヘッダ（HTTP-date）を返す', async () => {
    const { RateLimitExceededError } = await import('@/src/domain/errors')
    const resetAt = new Date('2026-08-19T12:00:00.000Z')
    searchMock.mockRejectedValue(new RateLimitExceededError('レート制限', resetAt))

    const res = await GET(new NextRequest('http://localhost/api/search?q=rate-limit-check'))

    expect(res.status).toBe(429)
    expect(res.headers.get('Retry-After')).toBe(resetAt.toUTCString())
  })

  it('RateLimitExceededError で retryAfter が無い場合は Retry-After ヘッダを付けない', async () => {
    const { RateLimitExceededError } = await import('@/src/domain/errors')
    searchMock.mockRejectedValue(new RateLimitExceededError('レート制限'))

    const res = await GET(new NextRequest('http://localhost/api/search?q=rate-limit-no-header-check'))

    expect(res.status).toBe(429)
    expect(res.headers.get('Retry-After')).toBeNull()
  })

  it('UpstreamError は 502 を返す', async () => {
    const { UpstreamError } = await import('@/src/domain/errors')
    searchMock.mockRejectedValue(new UpstreamError('上流エラー'))

    const res = await GET(new NextRequest('http://localhost/api/search?q=upstream-check'))

    expect(res.status).toBe(502)
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
