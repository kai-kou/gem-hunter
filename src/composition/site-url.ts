const DEFAULT_SITE_URL = 'https://gem-hunter.kinamocchi-tech.workers.dev'

/**
 * サイトの正準オリジン（`app/[locale]/layout.tsx` の `metadataBase` 用・Issue #347 追加タスク）。
 *
 * `metadataBase` が未設定だと Next.js は `opengraph-image` 等の相対 URL を解決できず既定の
 * `http://localhost:3000` へフォールバックする（実デプロイの `curl` で確認済み）。SNS クローラーは
 * localhost を取得できないため、OG 画像が本番で永久に表示されなくなる。
 *
 * `SITE_URL` 環境変数が未設定の場合は本番 URL（`wrangler.jsonc` の Worker 名から確定する
 * `*.workers.dev` ドメイン）へフォールバックする（`docs/rules/env-vars.md` に追記）。
 *
 * 🔴 **`SITE_URL` はビルド時変数**（実測で確認済み）: `app/[locale]/layout.tsx` の `metadata` は
 * 静的オブジェクトのため `getSiteUrl()` は `next build`/`opennextjs-cloudflare build` を実行する
 * シェルの `process.env` を読んで値がバンドルへ焼き込まれる。デプロイ後に `wrangler versions
 * upload --var` や Cloudflare の Worker 環境変数（ランタイムバインディング）で `SITE_URL` を
 * 変えても反映されない（同じビルド成果物を再アップロードしても値は変わらないことを実デプロイで確認済み）。
 * 上書きしたい場合はビルドコマンドの**前**に export すること。
 *
 * 🔴 `headers()` から `Host` ヘッダを見て実行時に動的組み立てはしない（lead 裁定）: `layout.tsx` の
 * `metadata`/`generateMetadata` で `headers()` を呼ぶとツリー全体が静的生成から外れ、
 * `generateStaticParams`（ja/en 2 パラメータ）の効果を潰す退行になる。この割り切りにより
 * **プレビュー環境（`pr-N` エイリアス等）では `og:image` が本番ドメインを指す**——画像内容は
 * ロケールが同じなら本番と同一で実害が小さく、プレビュー URL の SNS プレビュー表示は
 * 実用上の要件ではないため許容する（lead 裁定）。
 */
export function getSiteUrl(): string {
  return process.env.SITE_URL ?? DEFAULT_SITE_URL
}
