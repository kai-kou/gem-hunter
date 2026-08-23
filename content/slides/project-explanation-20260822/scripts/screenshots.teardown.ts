import { lstatSync, unlinkSync } from 'node:fs'

/**
 * 撮影のために張った `.open-next/assets` → `public` の symlink を外す。
 *
 * 🔴 張りっぱなしにすると、同じセッションで `wrangler versions upload` を
 * **`opennextjs-cloudflare build` を挟まずに**実行したとき、wrangler が
 * `wrangler.jsonc` の `assets.directory`（`.open-next/assets`）＝ `public/` を
 * そのまま assets として取り込む。`_next/static` も `BUILD_ID` も含まれないため
 * プレビュー URL は JS/CSS が 404 の壊れた画面になり、**wrangler も Playwright も
 * 何のエラーも出さない**。
 *
 * 自分が張った symlink のときだけ外す（実体のディレクトリがある環境＝
 * 既に OpenNext ビルド済みの作業ツリーには触らない）。
 */
export default async function globalTeardown(): Promise<void> {
  try {
    if (lstatSync('.open-next/assets').isSymbolicLink()) {
      unlinkSync('.open-next/assets')
    }
  } catch {
    // 元から無い・既に外れている場合は何もしない（後始末の失敗で撮影結果を落とさない）。
  }
}
