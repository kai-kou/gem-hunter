import type { WorkersCacheStorage } from './workers-cache'

/**
 * `caches.default`（Cloudflare Cache API）の fake。**テスト専用**（`.test-fake.ts` は Vitest の
 * `include`（`*.{test,spec}.ts`）に一致しないので、それ自体がテストスイートとして走ることはない）。
 *
 * 🔴 **終了値を差し替えるだけの fake にしない**（`sprint-development-rules.md` `SD-2` / #710）:
 * `put` / `match` / `delete` が **実際に受け取った `Request` の URL と `Cache-Control`** を
 * 記録し、テスト側で assert できるようにする。TTL は `Cache-Control: max-age` を fake が
 * 解釈して期限判定するので、実装が誤った `max-age` を書けばテストが落ちる。
 *
 * 🔴 **`workers-cache.test.ts` と `container.test.ts` で共有する**（PR #874 レビュー F9）:
 * container 側に劣化コピー（`Cache-Control` を一切見ない fake）を置いていたため、
 * `max-age` の計算を壊す変異が container 側では緑のまま通っていた。
 */
export function fakeCacheStorage(initialMs = 0) {
  let now = initialMs
  const entries = new Map<string, { body: string; expiresAt: number }>()
  const puts: PutRecord[] = []
  const matches: string[] = []
  const deletes: string[] = []
  let throwOnMatch: Error | undefined
  let throwOnPut: Error | undefined
  let throwOnDelete: Error | undefined

  const storage: WorkersCacheStorage = {
    async put(request: Request, response: Response): Promise<void> {
      if (throwOnPut) throw throwOnPut
      const cacheControl = response.headers.get('Cache-Control')
      const body = await response.text()
      puts.push({ url: request.url, method: request.method, cacheControl, body })
      const maxAge = /max-age=(\d+)$/.exec(cacheControl ?? '')
      if (!maxAge) {
        // max-age が無い / 不正な delta-seconds（`max-age=1e+21` 等）のレスポンスは保存しない
        // （実装が TTL を書き忘れる・指数表記に化けさせると HIT しなくなる）。
        return
      }
      entries.set(request.url, { body, expiresAt: now + Number(maxAge[1]) * 1000 })
    },
    async match(request: Request): Promise<Response | undefined> {
      if (throwOnMatch) throw throwOnMatch
      matches.push(request.url)
      const entry = entries.get(request.url)
      if (!entry) return undefined
      if (entry.expiresAt <= now) {
        entries.delete(request.url)
        return undefined
      }
      return new Response(entry.body)
    },
    async delete(request: Request): Promise<boolean> {
      if (throwOnDelete) throw throwOnDelete
      deletes.push(request.url)
      return entries.delete(request.url)
    },
  }

  return {
    storage,
    puts,
    matches,
    deletes,
    advance(ms: number) {
      now += ms
    },
    failMatchWith(error: Error) {
      throwOnMatch = error
    },
    failPutWith(error: Error) {
      throwOnPut = error
    },
    failDeleteWith(error: Error) {
      throwOnDelete = error
    },
    /** Cache API が壊れた JSON を返す状況（他者が書いた・スキーマが変わった等）を作る */
    seedRaw(url: string, body: string, ttlSeconds: number) {
      entries.set(url, { body, expiresAt: now + ttlSeconds * 1000 })
    },
  }
}

export type PutRecord = {
  readonly url: string
  readonly method: string
  readonly cacheControl: string | null
  readonly body: string
}
