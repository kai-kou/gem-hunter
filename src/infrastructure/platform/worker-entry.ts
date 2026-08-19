/**
 * Cloudflare Workers 用の薄いカスタムエントリポイント（案 2 スパイク）。
 *
 * OpenNext がビルドする `.open-next/worker.js` の default export（`fetch` ハンドラ）を
 * そのまま呼び出し、返ってきた `Response` を包んで `X-Cache-Status` ヘッダを付与して返す。
 *
 * Server Component からは動的にレスポンスヘッダを付けられない（`next/headers` は read-only）ため、
 * この Worker の最外層でヘッダを足す方式を取る。
 *
 * HIT/MISS の実値は `node:async_hooks` の `AsyncLocalStorage`（`cacheStatusStore`）を経由して
 * レンダリング内部から this ファイルまで運ぶ想定。現時点（スパイク段階）では実値連携は行わず、
 * 固定値 "MISS" を返す。
 *
 * NOTE: `.open-next/worker.js` は `npx opennextjs-cloudflare build` が生成する成果物であり、
 * リポジトリには含まれない（.gitignore 対象）。ローカル/CI で `wrangler dev` や `wrangler deploy` を
 * 実行する前に必ずビルドを走らせること。
 */
import { AsyncLocalStorage } from "node:async_hooks";
// @ts-expect-error: `.open-next/worker.js` は `opennextjs-cloudflare build` が生成するビルド成果物。
// 型定義を持たないため any 相当として扱う（このファイルはこの import 以外で any を持ち込まない）。
import openNextWorker from "../../../.open-next/worker.js";

export type CacheStatus = "HIT" | "MISS";

interface CacheStatusStore {
  status: CacheStatus;
}

/**
 * レンダリング内部（composition root 側）から HIT/MISS を書き込むための受け口。
 * 実値連携は親セッションが後段で実装する。
 */
export const cacheStatusStore = new AsyncLocalStorage<CacheStatusStore>();

interface OpenNextWorker {
  fetch(request: Request, env: unknown, ctx: ExecutionContext): Promise<Response>;
}

const worker = openNextWorker as OpenNextWorker;

export default {
  async fetch(request: Request, env: unknown, ctx: ExecutionContext): Promise<Response> {
    const response = await worker.fetch(request, env, ctx);

    // 固定値（スパイク段階）。実値連携は cacheStatusStore.getStore()?.status を参照する形に後段で差し替える。
    const cacheStatus: CacheStatus = "MISS";

    const headers = new Headers(response.headers);
    headers.set("X-Cache-Status", cacheStatus);

    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers,
    });
  },
};
