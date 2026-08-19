/**
 * SP-5: リクエストスコープで HIT/MISS を伝播するための `AsyncLocalStorage` の受け口。
 *
 * `worker-entry.ts`（Cloudflare Workers 外殻・`.open-next/worker.js` を import する）と
 * `container.ts`（composition root）の両方から参照される共有コンテキストだけをここに
 * 切り出す。`container.ts` が `worker-entry.ts` を直接 import すると、ビルド成果物
 * （`.open-next/worker.js`・リポジトリ非追跡）への依存が composition root にまで
 * 波及し危険なため、両者はこのファイルだけを介して疎結合になる（lead 裁定・
 * `content/discussions/sp5-cache-design-20260819/whiteboard.md` round3 決定 B）。
 *
 * `node:async_hooks` は Cloudflare Workers（`nodejs_compat` 有効時）だけでなく
 * Node.js（`next start` / vitest）でも動く。ただし store が確立されていない経路
 * （`cacheStatusStore.run()` の外側で呼ばれた場合。ローカル `next start` や
 * composition root 単体のユニットテストがこれに当たる）では `getStore()` が
 * `undefined` を返す。呼び出し側はこれを正常系として扱い、例外を投げずに
 * 素通りする（本ファイルの関数はいずれも `undefined` を許容する）。
 */
import { AsyncLocalStorage } from 'node:async_hooks'

export type CacheStatus = 'HIT' | 'MISS'

export interface CacheStatusStore {
  status: CacheStatus | undefined
}

export const cacheStatusStore = new AsyncLocalStorage<CacheStatusStore>()

/**
 * store が確立されていれば HIT/MISS を書き込む。store が無い経路
 * （`cacheStatusStore.run()` の外側・Node の `next start` / vitest 等）では
 * 何もしない（例外を投げない）。
 */
export function recordCacheStatus(status: CacheStatus): void {
  const store = cacheStatusStore.getStore()
  if (store !== undefined) {
    store.status = status
  }
}

/** store が確立されていれば現在の HIT/MISS を返す。無ければ `undefined`。 */
export function getCacheStatus(): CacheStatus | undefined {
  return cacheStatusStore.getStore()?.status
}
