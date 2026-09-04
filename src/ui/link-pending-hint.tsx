'use client'

import { useLinkStatus } from 'next/link'

import { cn } from '@/src/shared/cn'

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
 * 🔴 `role="status"` / `aria-live` は **持たない**（`ui-ux-guidelines.md` §7.2）。
 * ライブリージョンは画面に唯一・常設という規約に対し、本コンポーネントは詳細リンクごとに
 * 1 個ずつ描画される（一覧 1 ページで数十個）。全部がライブリージョンになると規約が壊れる。
 * したがって支援技術には何も伝えない純粋な視覚ヒント（`aria-hidden="true"`）に留める
 * ——`LoadingIndicator` が担う「読み込み中」の読み上げとは役割が異なる。
 * この理由から可視ラベルの `label` props も持たない（`aria-hidden` の内側に置いた文言は
 * 支援技術に届かず、i18n 文言を 3 つの一覧コンポーネントへ通すコストに見合わない）。
 *
 * 🔴 **DOM には常設し、`pending` で可視性（opacity）だけを切り替える**。`display:none` で
 * 出し入れするとリンク行の幅が遷移のたびに変わり、クリック直後にレイアウトシフトが起きる。
 *
 * ⚠️ **`<Link>` の子孫でしか機能しない**（`useLinkStatus` は直近の `<Link>` の遷移状態を読む）。
 * 文言そのものをアニメーションさせない方針は `loading-indicator.tsx` と同じだが、本実装は
 * テキストを持たないため、コントラスト（`NFR-13`）の懸念自体が発生しない。
 */
export function LinkPendingHint() {
  const { pending } = useLinkStatus()

  return (
    <span
      data-testid="link-pending-hint"
      data-pending={pending ? 'true' : 'false'}
      aria-hidden="true"
      className={cn(
        'ml-1 inline-block size-3 shrink-0 align-middle transition-opacity',
        pending ? 'opacity-100' : 'opacity-0',
      )}
    >
      <span
        className={cn(
          'block size-3 rounded-full border-2 border-current border-t-transparent',
          // 非 pending 時は回さない（不可視の要素を回し続けても意味がない）。
          // `motion-reduce` は「動きを減らす」設定の利用者への配慮（`NFR-13` 系）。
          pending && 'motion-reduce:animate-none animate-spin',
        )}
      />
    </span>
  )
}
