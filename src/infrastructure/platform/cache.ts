import type { CacheKey, CachePort } from '../../domain/ports/cache-port'
import type { ClockPort } from '../../domain/ports/clock-port'
import { SystemClock } from '../system-clock'
import { assertPositiveTtlSeconds } from './ttl'

type Entry = {
  readonly value: unknown
  readonly expiresAt: number
}

/**
 * CachePort の最小実装（Issue #67「Cache Port の器」）。
 *
 * ⚠️ **範囲**: isolate 内メモリのみに保持する土台実装。Workers Caching / `Cache-Control`
 * ヘッダへの実適用（TTL 値の確定・レスポンスへの付与）は `E-3` / `SP-5` のスコープ（未実施）。
 * `SP-5` で `src/composition/container.ts` の `sharedCache`（モジュールスコープの単一インスタンス）
 * として実際に配線済み（`CachingRepositoryQuery` から呼ばれる）。
 */
export class InMemoryCache implements CachePort {
  private readonly store = new Map<CacheKey, Entry>()

  constructor(private readonly clock: ClockPort = new SystemClock()) {}

  async get<T>(key: CacheKey): Promise<T | null> {
    const entry = this.store.get(key)
    if (!entry) {
      return null
    }
    if (entry.expiresAt <= this.clock.now().getTime()) {
      this.store.delete(key)
      return null
    }
    return entry.value as T
  }

  async set<T>(key: CacheKey, value: T, ttlSeconds: number): Promise<void> {
    assertPositiveTtlSeconds(ttlSeconds)
    this.store.set(key, { value, expiresAt: this.clock.now().getTime() + ttlSeconds * 1000 })
  }

  async invalidate(key: CacheKey): Promise<void> {
    this.store.delete(key)
  }
}
