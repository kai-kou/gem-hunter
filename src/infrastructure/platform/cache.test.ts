import { describe, expect, it } from 'vitest'

import { InMemoryCache } from './cache'

describe('InMemoryCache', () => {
  it('set した値を get で取得できる', async () => {
    const cache = new InMemoryCache()
    await cache.set('k', { hello: 'world' }, 60)
    await expect(cache.get('k')).resolves.toEqual({ hello: 'world' })
  })

  it('未設定のキーは null を返す', async () => {
    const cache = new InMemoryCache()
    await expect(cache.get('missing')).resolves.toBeNull()
  })

  it('TTL 経過後は null を返す（期限切れエントリは破棄される）', async () => {
    let now = 0
    const cache = new InMemoryCache(() => now)
    await cache.set('k', 'v', 10)
    now += 10_000
    await expect(cache.get('k')).resolves.toBeNull()
  })

  it('TTL 経過前は値を返す', async () => {
    let now = 0
    const cache = new InMemoryCache(() => now)
    await cache.set('k', 'v', 10)
    now += 9_999
    await expect(cache.get('k')).resolves.toBe('v')
  })

  it('invalidate で明示的に削除できる', async () => {
    const cache = new InMemoryCache()
    await cache.set('k', 'v', 60)
    await cache.invalidate('k')
    await expect(cache.get('k')).resolves.toBeNull()
  })

  it('存在しないキーの invalidate はエラーにならない', async () => {
    const cache = new InMemoryCache()
    await expect(cache.invalidate('missing')).resolves.toBeUndefined()
  })
})
