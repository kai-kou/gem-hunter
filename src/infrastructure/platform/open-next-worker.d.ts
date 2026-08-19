/**
 * `.open-next/worker.js`（`npx opennextjs-cloudflare build` が生成するビルド成果物・
 * リポジトリ非追跡）のアンビエント型宣言。
 *
 * ビルド前（`.open-next/` が存在しない状態）でも `npx tsc --noEmit` を通すための宣言で、
 * `worker-entry.ts` からの相対 import 1 箇所だけを対象にする。物理ファイルの有無に関わらず
 * この宣言が優先されるため、`@ts-expect-error` のような「ビルド成果物が存在するかどうかで
 * エラーの有無が変わる」脆い抑制を避けられる。
 */
declare module '../../../.open-next/worker.js' {
  const worker: {
    fetch(request: Request, env: unknown, ctx: ExecutionContext): Promise<Response>
  }
  export default worker
}
