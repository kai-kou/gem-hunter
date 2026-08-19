import type { CachePort } from '../../domain/ports/cache-port'

type Entry = {
  readonly value: unknown
  readonly expiresAt: number
}

/**
 * CachePort の最小実装（Issue #67「Cache Port の器」）。
 *
 * ⚠️ **範囲**: isolate 内メモリのみに保持する土台実装。Workers Caching / `Cache-Control`
 * ヘッダへの実適用（TTL 値の確定・レスポンスへの付与）は `E-3` / `SP-5` のスコープ（未実施）。
 * 現時点では composition root に配線せず、どのユースケースからも呼ばれない（YAGNI）。
 */
export class InMemoryCache implements CachePort {
  private readonly store = new Map<string, Entry>()

  constructor(private readonly now: () => number = Date.now) {}

  async get<T>(key: string): Promise<T | null> {
    const entry = this.store.get(key)
    if (!entry) {
      return null
    }
    if (entry.expiresAt <= this.now()) {
      this.store.delete(key)
      return null
    }
    return entry.value as T
  }

  async set<T>(key: string, value: T, ttlSeconds: number): Promise<void> {
    this.store.set(key, { value, expiresAt: this.now() + ttlSeconds * 1000 })
  }

  async invalidate(key: string): Promise<void> {
    this.store.delete(key)
  }
}
