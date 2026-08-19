/**
 * Cloudflare Workers 用の薄いカスタムエントリポイント（SP-5・lead 裁定「争点 B」第 1 候補）。
 *
 * OpenNext がビルドする `.open-next/worker.js` の default export（`fetch` ハンドラ）を
 * そのまま呼び出し、返ってきた `Response` を包んで `X-Cache-Status` ヘッダを付与して返す。
 *
 * Server Component からは動的にレスポンスヘッダを付けられない（`next/headers` は read-only、
 * `next.config.ts` の `headers()` は静的テーブル、`defineCloudflareConfig()` にレスポンスラップの
 * フックが無い）ため、この Worker の最外層でヘッダを足す方式を取る
 * （`content/discussions/sp5-cache-design-20260819/whiteboard.md` round3 決定）。
 *
 * HIT/MISS の実値は `cache-status-context.ts` の `AsyncLocalStorage`（`cacheStatusStore`）を
 * 経由して、レンダリング内部（composition root の `onCacheStatus` コールバック）から
 * この外側ラッパーまで運ぶ。1 リクエストの処理全体を `cacheStatusStore.run()` で包み、
 * その中で書き込まれた値を読み出す。
 *
 * NOTE: `.open-next/worker.js` は `npx opennextjs-cloudflare build` が生成する成果物であり、
 * リポジトリには含まれない（.gitignore 対象）。ローカル/CI で `wrangler dev` や `wrangler deploy` を
 * 実行する前に必ずビルドを走らせること。ビルド前でも `tsc --noEmit` が通るよう、型は
 * `open-next-worker.d.ts`（同ディレクトリ）のアンビエント宣言を参照する。
 */
import openNextWorker from "../../../.open-next/worker.js";
import { cacheStatusStore, type CacheStatus } from "./cache-status-context";

export { cacheStatusStore } from "./cache-status-context";
export type { CacheStatus } from "./cache-status-context";

interface OpenNextWorker {
  fetch(request: Request, env: unknown, ctx: ExecutionContext): Promise<Response>;
}

const worker = openNextWorker as OpenNextWorker;

export default {
  async fetch(request: Request, env: unknown, ctx: ExecutionContext): Promise<Response> {
    let cacheStatus: CacheStatus | undefined;

    const response = await cacheStatusStore.run({ status: undefined }, async () => {
      const innerResponse = await worker.fetch(request, env, ctx);
      // composition root（`container.ts`）の `onCacheStatus` コールバックが
      // レンダリング中に `recordCacheStatus()` を呼んでいれば、ここで読み出せる。
      cacheStatus = cacheStatusStore.getStore()?.status;
      return innerResponse;
    });

    const headers = new Headers(response.headers);

    // 値が無い（= このリクエストの処理中に一度もキャッシュ参照が発生しなかった）場合は
    // ヘッダを付けない。付けるとすれば "MISS" が候補だが、それは「キャッシュを引いて
    // 外れた」という意味であり、「そもそもキャッシュを引く処理が走らなかった」（静的
    // アセット・検索を伴わないページ等）とは意味が異なる。存在しない事実を MISS という
    // 具体値で断定するより、ヘッダ自体を省略する方が正直な表現になる。
    if (cacheStatus !== undefined) {
      headers.set("X-Cache-Status", cacheStatus);
    }

    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers,
    });
  },
};
