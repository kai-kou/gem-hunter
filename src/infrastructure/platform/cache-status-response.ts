/**
 * SP-5: `X-Cache-Status` ヘッダ付与ロジック（`worker-entry.ts` から切り出し）。
 *
 * `worker-entry.ts` はビルド成果物 `.open-next/worker.js`（リポジトリ非追跡・`.gitignore` 対象）を
 * 静的 import するため、そのファイル自体を import すると `.open-next/worker.js` の解決が必要になり、
 * ビルド前（CI の fresh checkout・`.open-next/` 未生成）ではユニットテストが実行できない。
 * ヘッダ付与ロジックはビルド成果物に一切依存しない（`OpenNextWorker` という最小限の形の引数を
 * 受け取るだけ）ため、この専用ファイルへ切り出し、単体テストを独立させる。
 */
import { cacheStatusStore, type CacheStatus } from './cache-status-context'

export interface OpenNextWorker {
  fetch(request: Request, env: unknown, ctx: ExecutionContext): Promise<Response>
}

/**
 * `worker` の応答を `cacheStatusStore` 経由で観測した HIT/MISS で包み、`X-Cache-Status` ヘッダを
 * 付与する。
 */
export async function fetchWithCacheStatusHeader(
  worker: OpenNextWorker,
  request: Request,
  env: unknown,
  ctx: ExecutionContext,
): Promise<Response> {
  let cacheStatus: CacheStatus | undefined

  const response = await cacheStatusStore.run({ status: undefined }, async () => {
    const innerResponse = await worker.fetch(request, env, ctx)
    // composition root（`container.ts`）の `onCacheStatus` コールバックが
    // レンダリング中に `recordCacheStatus()` を呼んでいれば、ここで読み出せる。
    cacheStatus = cacheStatusStore.getStore()?.status
    return innerResponse
  })

  const headers = new Headers(response.headers)

  // 値が無い（= このリクエストの処理中に一度もキャッシュ参照が発生しなかった）場合は
  // ヘッダを付けない。付けるとすれば "MISS" が候補だが、それは「キャッシュを引いて
  // 外れた」という意味であり、「そもそもキャッシュを引く処理が走らなかった」（静的
  // アセット・検索を伴わないページ等）とは意味が異なる。存在しない事実を MISS という
  // 具体値で断定するより、ヘッダ自体を省略する方が正直な表現になる。
  if (cacheStatus !== undefined) {
    headers.set('X-Cache-Status', cacheStatus)
  }

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  })
}
