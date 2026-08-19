import { beforeEach, describe, expect, it, vi } from 'vitest'
import { recordCacheStatus } from './cache-status-context'
import { fetchWithCacheStatusHeader, type OpenNextWorker } from './cache-status-response'

function makeFakeWorker(fetchImpl: OpenNextWorker['fetch']): OpenNextWorker {
  return { fetch: vi.fn(fetchImpl) }
}

describe('fetchWithCacheStatusHeader', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('cacheStatusStore に何も書き込まれなければ X-Cache-Status ヘッダを付けない', async () => {
    const worker = makeFakeWorker(async () => new Response('ok', { status: 200 }))

    const response = await fetchWithCacheStatusHeader(
      worker,
      new Request('http://localhost/static/asset.js'),
      {},
      {} as ExecutionContext,
    )

    expect(response.headers.get('X-Cache-Status')).toBeNull()
  })

  it('レンダリング中に recordCacheStatus("MISS") が呼ばれれば X-Cache-Status: MISS を付ける', async () => {
    const worker = makeFakeWorker(async () => {
      recordCacheStatus('MISS')
      return new Response('ok', { status: 200 })
    })

    const response = await fetchWithCacheStatusHeader(
      worker,
      new Request('http://localhost/ja?q=test'),
      {},
      {} as ExecutionContext,
    )

    expect(response.headers.get('X-Cache-Status')).toBe('MISS')
  })

  it('2 回目の呼び出しで recordCacheStatus("HIT") が呼ばれれば X-Cache-Status: HIT を付ける（1 回目の store を引き継がない）', async () => {
    const worker = makeFakeWorker(async () => new Response('ok', { status: 200 }))
    ;(worker.fetch as ReturnType<typeof vi.fn>)
      .mockImplementationOnce(async () => {
        recordCacheStatus('MISS')
        return new Response('ok', { status: 200 })
      })
      .mockImplementationOnce(async () => {
        recordCacheStatus('HIT')
        return new Response('ok', { status: 200 })
      })

    const request = new Request('http://localhost/ja?q=test')
    const first = await fetchWithCacheStatusHeader(worker, request, {}, {} as ExecutionContext)
    const second = await fetchWithCacheStatusHeader(worker, request, {}, {} as ExecutionContext)

    expect(first.headers.get('X-Cache-Status')).toBe('MISS')
    expect(second.headers.get('X-Cache-Status')).toBe('HIT')
  })

  it('元のレスポンスの status / body / 既存ヘッダを保持する', async () => {
    const worker = makeFakeWorker(
      async () => new Response('body-content', { status: 404, headers: { 'content-type': 'text/plain' } }),
    )

    const response = await fetchWithCacheStatusHeader(
      worker,
      new Request('http://localhost/not-found'),
      {},
      {} as ExecutionContext,
    )

    expect(response.status).toBe(404)
    expect(response.headers.get('content-type')).toBe('text/plain')
    expect(await response.text()).toBe('body-content')
  })

  it('worker.fetch を呼ぶときに request / env / ctx をそのまま渡す', async () => {
    const worker = makeFakeWorker(async () => new Response('ok'))
    const request = new Request('http://localhost/ja?q=test')
    const env = { SOME_BINDING: 'value' }
    const ctx = {} as ExecutionContext

    await fetchWithCacheStatusHeader(worker, request, env, ctx)

    expect(worker.fetch).toHaveBeenCalledWith(request, env, ctx)
  })
})
