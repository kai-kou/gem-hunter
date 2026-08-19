import { beforeEach, describe, expect, it, vi } from 'vitest'

// `.open-next/worker.js` はビルド成果物（リポジトリ非追跡）のため、テストでは仮想モックに差し替える。
const innerFetch = vi.fn<(request: Request, env: unknown, ctx: ExecutionContext) => Promise<Response>>()

vi.mock('../../../.open-next/worker.js', () => ({
  default: { fetch: (...args: Parameters<typeof innerFetch>) => innerFetch(...args) },
}))

describe('worker-entry', () => {
  beforeEach(() => {
    innerFetch.mockReset()
  })

  it('cacheStatusStore に何も書き込まれなければ X-Cache-Status ヘッダを付けない', async () => {
    innerFetch.mockResolvedValue(new Response('ok', { status: 200 }))
    const { default: entry } = await import('./worker-entry')

    const response = await entry.fetch(
      new Request('http://localhost/static/asset.js'),
      {},
      {} as ExecutionContext,
    )

    expect(response.headers.get('X-Cache-Status')).toBeNull()
  })

  it('レンダリング中に recordCacheStatus("MISS") が呼ばれれば X-Cache-Status: MISS を付ける', async () => {
    const { recordCacheStatus } = await import('./cache-status-context')
    innerFetch.mockImplementation(async () => {
      recordCacheStatus('MISS')
      return new Response('ok', { status: 200 })
    })
    const { default: entry } = await import('./worker-entry')

    const response = await entry.fetch(new Request('http://localhost/ja?q=test'), {}, {} as ExecutionContext)

    expect(response.headers.get('X-Cache-Status')).toBe('MISS')
  })

  it('2 回目の呼び出しで recordCacheStatus("HIT") が呼ばれれば X-Cache-Status: HIT を付ける（1 回目の store を引き継がない）', async () => {
    const { recordCacheStatus } = await import('./cache-status-context')
    innerFetch
      .mockImplementationOnce(async () => {
        recordCacheStatus('MISS')
        return new Response('ok', { status: 200 })
      })
      .mockImplementationOnce(async () => {
        recordCacheStatus('HIT')
        return new Response('ok', { status: 200 })
      })
    const { default: entry } = await import('./worker-entry')

    const first = await entry.fetch(new Request('http://localhost/ja?q=test'), {}, {} as ExecutionContext)
    const second = await entry.fetch(new Request('http://localhost/ja?q=test'), {}, {} as ExecutionContext)

    expect(first.headers.get('X-Cache-Status')).toBe('MISS')
    expect(second.headers.get('X-Cache-Status')).toBe('HIT')
  })

  it('元のレスポンスの status / body / 既存ヘッダを保持する', async () => {
    innerFetch.mockResolvedValue(
      new Response('body-content', { status: 404, headers: { 'content-type': 'text/plain' } }),
    )
    const { default: entry } = await import('./worker-entry')

    const response = await entry.fetch(new Request('http://localhost/not-found'), {}, {} as ExecutionContext)

    expect(response.status).toBe(404)
    expect(response.headers.get('content-type')).toBe('text/plain')
    expect(await response.text()).toBe('body-content')
  })
})
