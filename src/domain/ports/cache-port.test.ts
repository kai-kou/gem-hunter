import { describe, expect, it } from 'vitest'

import type { CacheKey, CachePort } from './cache-port'

/**
 * `CachePort` 契約の型テスト（Issue #89）。
 *
 * 🔴 **目的**: `CachePort.get` / `set` / `invalidate` が `CacheKey`（生成関数以外で
 * 組み立てられないブランド型）を要求し、生の `string` を渡すとコンパイルエラーになることを
 * 固定する。実行時アサーションではなく `@ts-expect-error` による型検査が本体（型が緩んで
 * `string` を再び受け付けるようになったら `@ts-expect-error` が「不要なエラー抑制」として
 * 検出され `tsc --noEmit` が失敗する）。
 */
function makeFakeCachePort(): CachePort {
  const store = new Map<CacheKey, unknown>()
  return {
    async get<T>(key: CacheKey): Promise<T | null> {
      return store.has(key) ? (store.get(key) as T) : null
    },
    async set<T>(key: CacheKey, value: T): Promise<void> {
      store.set(key, value)
    },
    async invalidate(key: CacheKey): Promise<void> {
      store.delete(key)
    },
  }
}

describe('CachePort の型契約', () => {
  it('生成関数を経た CacheKey は get/set/invalidate に渡せる', async () => {
    const cache = makeFakeCachePort()
    const key = 'search:v2:react:page=1' as CacheKey
    await cache.set(key, 'value', 60)
    await expect(cache.get(key)).resolves.toBe('value')
    await cache.invalidate(key)
    await expect(cache.get(key)).resolves.toBeNull()
  })

  it('生の string は get に渡せない（コンパイルエラー）', async () => {
    const cache = makeFakeCachePort()
    // @ts-expect-error 生の string は CacheKey ではない（Issue #89: 生成関数を経ないキーを型で拒否する）
    await cache.get('raw-string-key')
  })

  it('生の string は set に渡せない（コンパイルエラー）', async () => {
    const cache = makeFakeCachePort()
    // @ts-expect-error 生の string は CacheKey ではない（Issue #89: 生成関数を経ないキーを型で拒否する）
    await cache.set('raw-string-key', 'value', 60)
  })

  it('生の string は invalidate に渡せない（コンパイルエラー）', async () => {
    const cache = makeFakeCachePort()
    // @ts-expect-error 生の string は CacheKey ではない（Issue #89: 生成関数を経ないキーを型で拒否する）
    await cache.invalidate('raw-string-key')
  })
})
