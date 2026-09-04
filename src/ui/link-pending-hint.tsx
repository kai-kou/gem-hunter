'use client'

import { useLinkStatus } from 'next/link'
import { useEffect } from 'react'

import { useLinkPendingReport } from './link-pending-announcer'

/**
 * 一覧から詳細ページへ遷移している間だけ点灯する、リンク付随の視覚ヒント（`US-22` / `AC-8`）。
 *
 * 🔴 **なぜ詳細ページ側の `loading.tsx` / `<Suspense>` ではないのか**（Issue #167）:
 * 詳細ページ（`app/[locale]/repos/[owner]/[repo]/page.tsx`）は `AC-5` により
 * `repository === null` のとき `notFound()` を **同期的に** 返して 404 の HTTP ステータスを
 * 保つ必要がある。`loading.tsx` を置く／本体を `<Suspense>` で包むと、レスポンスの
 * ヘッダーが先に流れてしまい 404 を返せなくなる（同ページ冒頭の 🔴 コメントが正本）。
 * そのためサーバー側では読み込み中を表現せず、**遷移元（一覧）のクライアント側ペンディング
 * 表示** で「詳細の取得が進行中である」ことを伝える。Next.js 公式も `useLinkStatus` の
 * 用途として「遷移先が動的ルートで `loading.js` を持たない場合」を明示している。
 *
 * 🔴 **本要素自身は `role="status"` / `aria-live` を持たない**。詳細リンクごとに 1 個ずつ
 * 描画される（一覧 1 ページで数十個）ため、ここにライブリージョンを持たせると同種の
 * `role="status"` が大量に並ぶ。代わりに `useLinkStatus()` の `pending` を
 * `LinkPendingAnnouncer`（祖先に 1 個だけ常設した sr-only のライブリージョン）へ報告し、
 * 支援技術への通知はそちらが一手に担う（`AC-8`「いずれの状態変化も `aria-live` で支援技術に
 * 伝えられる」/ `NFR-12`「視覚表現だけにしない」）。本要素は `aria-hidden="true"` の
 * 純粋な視覚表現に留まるので、可視ラベルの `label` props も持たない。
 * ⚠️ `ui-ux-guidelines.md` §7.2 が禁じているのは「要素ごとの動的挿入」と「ライブリージョンの
 * 入れ子」であって、画面にライブリージョンが複数あること自体ではない（`app/[locale]/page.tsx`
 * では `<section id="search-status">` と `RepositoryList` の `role="status"` が兄弟として共存する）。
 *
 * 🔴 **DOM には常設し、`pending` で可視性（opacity）だけを切り替える**。`display:none` で
 * 出し入れするとリンク行の幅が遷移のたびに変わり、クリック直後にレイアウトシフトが起きる。
 * 寸法・意匠・回転はすべて **この 1 要素** に載せる（外側ラッパと内側スピナーに分けると、
 * 寸法クラスが 2 か所に重複し片方だけ変更したときに予約幅が崩れる）。
 *
 * ⚠️ **`data-testid` を使う理由**: `aria-hidden="true"` の要素は Testing Library / Playwright の
 * ロールクエリから常に除外されるため、ロールでは掴めない。`src/ui/` の本番コードで
 * `data-testid` を使うのはこの制約が理由の例外であり、他要素へ広げない。
 *
 * ⚠️ **`<Link>` の子孫でしか機能しない**（`useLinkStatus` は直近の `<Link>` の遷移状態を読む）。
 * 文言そのものをアニメーションさせない方針は `loading-indicator.tsx` と同じだが、本実装は
 * テキストを持たないため、コントラスト（`NFR-13`）の懸念自体が発生しない。
 */
export function LinkPendingHint() {
  const { pending } = useLinkStatus()
  const report = useLinkPendingReport()

  useEffect(() => {
    // 遷移待ちの間だけ「1 件」として数えてもらい、解決・アンマウント時に取り下げる。
    // `pending` が false の間は何も報告しない（他リンクの計数を巻き添えで減らさないため）。
    if (!pending) return
    report(true)
    return () => {
      report(false)
    }
  }, [pending, report])

  return (
    <span
      data-testid="link-pending-hint"
      data-pending={pending ? 'true' : 'false'}
      aria-hidden="true"
      className={`ml-1 inline-block size-3 shrink-0 rounded-full border-2 border-current border-t-transparent align-middle transition-opacity ${
        // 非 pending 時は回さない（不可視の要素を回し続けても意味がない）。
        // `motion-reduce` は「動きを減らす」設定の利用者への配慮（`NFR-13` 系）。
        pending ? 'motion-reduce:animate-none animate-spin opacity-100' : 'opacity-0'
      }`}
    />
  )
}
