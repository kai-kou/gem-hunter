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
 * 経由して、レンダリング内部（composition root の `onCacheStatus` コールバック）からここまで運ぶ
 * “想定”だった。ヘッダ付与ロジック自体は `cache-status-response.ts`（`fetchWithCacheStatusHeader`）に
 * 切り出してあり、このファイルは「実際のビルド成果物をそこへ結線するだけ」の薄い層に留める
 * （ビルド成果物への依存を持たないユニットテストは `cache-status-response.test.ts` を参照）。
 *
 * 🔴 **実機スパイクで不成立と確認済み（2026-08-19）**: `wrangler dev --local` + スタブ GitHub API で
 * 実際に検証した結果、`cacheStatusStore.run()`（このファイル）で確立した store は、
 * `.open-next/worker.js` 内部の Next.js SSR レンダリングを経由して composition root の
 * `onCacheStatus` コールバックが呼ばれる時点では `cacheStatusStore.getStore()` が常に
 * `undefined` を返す（=伝播しない）。一方で `CachingRepositoryQuery` 自体のキャッシュロジック
 * （同一 isolate 内で 2 回目以降 `inner.search` を呼ばない）は実機でも正しく動作しており
 * （`recordCacheStatus('HIT')` が実際に呼ばれることをログで確認済み）、壊れているのは
 * 「observability（HIT/MISS を外へ伝える経路）」だけで「correctness（二重フェッチしない）」は
 * 健全。原因はおそらく workerd の `nodejs_compat` AsyncLocalStorage が、Next.js の内部
 * レンダリング（RSC ストリーミング等でネイティブの Streams/スケジューラを経由する箇所）を
 * Node の async_hooks が計装していないコンテキストとして扱っているため（未確定・追加調査は
 * 別 Issue 向け）。**lead 裁定どおり「不成立なら案 3（`app/api/search/route.ts` を観測経路にする）へ
 * フォールバック」を発動する必要がある**（`app/` 配下は本ファイルの担当スコープ外）。
 *
 * 現状の挙動: `cacheStatus` は常に `undefined` になるため `X-Cache-Status` ヘッダは常に省略される
 * （虚偽の値を返すよりは安全側）。将来 workerd 側でこの制約が解消されれば、このファイルのコードは
 * 無改修のまま動き出す設計になっている。
 *
 * NOTE: `.open-next/worker.js` は `npx opennextjs-cloudflare build` が生成する成果物であり、
 * リポジトリには含まれない（.gitignore 対象）。ローカル/CI で `wrangler dev` や `wrangler deploy` を
 * 実行する前に必ずビルドを走らせること。
 */
// @ts-expect-error: `.open-next/worker.js` は `opennextjs-cloudflare build` が生成するビルド成果物。
// 型定義を持たないため any 相当として扱う（このファイルはこの import 以外で any を持ち込まない。
// 下記 `OpenNextWorker` へキャストして以降の呼び出しに型を戻す）。`tools/run_checks.sh` は
// ビルドより前に `tsc --noEmit` を実行する運用のため、通常はこの行で TS2307 が出る
// （＝この抑制が「使われている」状態になる）。手元でビルド後に単独で tsc を走らせると
// 「Unused '@ts-expect-error'」が出ることがあるが、ビルド成果物が存在する一時的なローカル状態に
// よるものであり、CI の実行順序では発生しない。
import openNextWorker from "../../../.open-next/worker.js";
import { fetchWithCacheStatusHeader, type OpenNextWorker } from "./cache-status-response";

export { cacheStatusStore } from "./cache-status-context";
export type { CacheStatus } from "./cache-status-context";
export { fetchWithCacheStatusHeader } from "./cache-status-response";
export type { OpenNextWorker } from "./cache-status-response";

const worker = openNextWorker as OpenNextWorker;

const workerEntry = {
  fetch(request: Request, env: unknown, ctx: ExecutionContext): Promise<Response> {
    return fetchWithCacheStatusHeader(worker, request, env, ctx);
  },
};

export default workerEntry;
