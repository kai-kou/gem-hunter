import { NextRequest } from 'next/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { SearchResult } from '@/src/domain/model/repository'

/**
 * `GithubRepositoryQuery` を丸ごとモックする（`vi.mock` はファイル先頭へホイストされるため
 * `describe` の外に置く）。
 *
 * 理由: `src/composition/container.ts` の `sharedCache` はモジュールスコープの単一インスタンス
 * （isolate 内で使い回す意図的な設計・`SP-5` whiteboard 決定）だが、そのままではテストケース間で
 * HIT/MISS の状態が漏れ、本ファイルの「MISS → HIT」assert が壊れる。`container.ts` は
 * テスト用の注入口を持たず（本タスクの担当スコープ外・変更禁止）、代わりに `beforeEach` で
 * `vi.resetModules()` して `./route` を動的 import し直すことで、テストごとに新しいモジュール
 * グラフ（＝新しい `sharedCache` インスタンス）を作る。GitHub への実 HTTP 発行を避けるため
 * `GithubRepositoryQuery` はこのモックに差し替える（`makeInstallationTokenProvider` は
 * コンストラクタ引数として渡されるだけで、モック実装内では参照されないため未設定の
 * env 変数があっても副作用は起きない）。
 */
const searchMock = vi.fn()
const findDetailMock = vi.fn()

vi.mock('@/src/infrastructure/github/github-repository-query', () => ({
  GithubRepositoryQuery: vi.fn().mockImplementation(() => ({
    search: searchMock,
    findDetail: findDetailMock,
  })),
}))

function makeSearchResult(overrides: Partial<SearchResult> = {}): SearchResult {
  return {
    totalCount: 0,
    incompleteResults: false,
    items: [],
    ...overrides,
  }
}

/** `vi.resetModules()` 後に `./route` の `GET` を取り直す（毎テストで新しい `sharedCache`）。 */
async function freshGet() {
  const mod = await import('./route')
  return mod.GET
}

beforeEach(() => {
  vi.resetModules()
  searchMock.mockReset()
  findDetailMock.mockReset()
})

describe('GET /api/search — X-Cache-Status', () => {
  it('同一キーワードで 1 回目は MISS、2 回目は HIT を報告する', async () => {
    searchMock.mockResolvedValue(makeSearchResult({ totalCount: 3 }))
    const GET = await freshGet()

    const first = await GET(new NextRequest('http://localhost/api/search?q=react'))
    expect(first.headers.get('X-Cache-Status')).toBe('MISS')

    const second = await GET(new NextRequest('http://localhost/api/search?q=react'))
    expect(second.headers.get('X-Cache-Status')).toBe('HIT')

    // キャッシュが効いていれば inner (GithubRepositoryQuery) は 1 回しか呼ばれない
    expect(searchMock).toHaveBeenCalledTimes(1)
  })
})

describe('GET /api/search — domainErrorStatus のステータス分岐', () => {
  it('DomainValidationError（空キーワード）は 400 を返す', async () => {
    const GET = await freshGet()

    const res = await GET(new NextRequest('http://localhost/api/search?q='))

    expect(res.status).toBe(400)
    const body = (await res.json()) as { error: string }
    expect(body.error).toContain('検索キーワードを入力してください')
  })

  it('NotFoundError は 404 を返す', async () => {
    const { NotFoundError } = await import('@/src/domain/errors')
    searchMock.mockRejectedValue(new NotFoundError('見つかりません'))
    const GET = await freshGet()

    const res = await GET(new NextRequest('http://localhost/api/search?q=react'))

    expect(res.status).toBe(404)
  })

  it('RateLimitExceededError は 429 と Retry-After ヘッダ（HTTP-date）を返す', async () => {
    const { RateLimitExceededError } = await import('@/src/domain/errors')
    const resetAt = new Date('2026-08-19T12:00:00.000Z')
    searchMock.mockRejectedValue(new RateLimitExceededError('レート制限', resetAt))
    const GET = await freshGet()

    const res = await GET(new NextRequest('http://localhost/api/search?q=react'))

    expect(res.status).toBe(429)
    expect(res.headers.get('Retry-After')).toBe(resetAt.toUTCString())
  })

  it('RateLimitExceededError で retryAfter が無い場合は Retry-After ヘッダを付けない', async () => {
    const { RateLimitExceededError } = await import('@/src/domain/errors')
    searchMock.mockRejectedValue(new RateLimitExceededError('レート制限'))
    const GET = await freshGet()

    const res = await GET(new NextRequest('http://localhost/api/search?q=react'))

    expect(res.status).toBe(429)
    expect(res.headers.get('Retry-After')).toBeNull()
  })

  it('UpstreamError は 502 を返す', async () => {
    const { UpstreamError } = await import('@/src/domain/errors')
    searchMock.mockRejectedValue(new UpstreamError('上流エラー'))
    const GET = await freshGet()

    const res = await GET(new NextRequest('http://localhost/api/search?q=react'))

    expect(res.status).toBe(502)
  })
})
