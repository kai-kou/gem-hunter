/**
 * TTL（秒）の値域検証。`CachePort` の実装 3 つ（`InMemoryCache` / `WorkersCache` /
 * `LayeredCache`）で **同一条件・同一メッセージ** の検証をコピーしていたのを 1 箇所に寄せる。
 *
 * 🔴 **なぜ共通化が必要か**: 1 箇所だけ直し忘れると「`LayeredCache` は受理するのに
 * `WorkersCache` だけ throw し、その `RangeError` が `LayeredCache.set` の `catch` に
 * 握り潰されて **primary にだけ書かれる非対称** が無音で起きる」という壊れ方をする
 * （どちらの層にも書かれない／両方に書かれる、のどちらでもない中間状態）。
 *
 * ⚠️ **メッセージ文言は変えない**（既存テストが `RangeError` の型と文言に依存している）。
 *
 * @param value 検証する TTL（秒）
 * @param label エラーメッセージに出す引数名（`refillTtlSeconds` 等）
 * @throws {RangeError} 正の有限数でないとき
 */
export function assertPositiveTtlSeconds(value: number, label = 'ttlSeconds'): void {
  if (!Number.isFinite(value) || value <= 0) {
    throw new RangeError(`${label} は正の有限数である必要があります（受け取った値: ${value}）`)
  }
}
