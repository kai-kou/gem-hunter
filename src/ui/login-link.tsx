import { buttonVariants } from './components/button'

export type LoginLinkLabels = {
  login: string
  logout: string
}

type LoginLinkProps = {
  isLoggedIn: boolean
  labels: LoginLinkLabels
}

/**
 * ログイン/ログアウトの導線を出し分ける表示コンポーネント（AR-5・D-6）。
 *
 * `isLoggedIn`（セッション Cookie の有無=真偽値）だけで出し分ける最小実装。
 * ユーザー名・レート枠数値は表示しない（AC 未記載・YAGNI・
 * whiteboard `sp8-auth-i18n-20260819` 争点 C 決定）。
 *
 * Cookie の読み取りは呼び出し側（統合担当が `app/[locale]/layout.tsx` から配線する際）が
 * composition root 経由で行う。本コンポーネントは純粋な表示に徹する
 * （`src/ui/` は「外部世界」である Cookie を直接読まない・ARCH-6）。
 *
 * `/api/auth/*` は Cookie を書き換える副作用を持つため、`next/link` の `<Link>` で
 * プリフェッチさせない（本番ビルドはビューポート内リンクを自動プリフェッチし、表示しただけで
 * GET が実行されてしまう）。ログインは副作用のある GET のため素の `<a href>` にとどめ、
 * ログアウトは副作用のある操作を GET に置かない方針（`route.ts` 側の POST 化）に合わせ、
 * クライアント JS 不要のプレーンな `<form method="post">` から叩く。
 *
 * `buttonVariants()` の size variant 経由で描画する（`ui-ux-guidelines.md` §2.4
 * 必須「高さとフォントサイズは cva の size variant 経由でのみ指定する」・PR #141 レビュー指摘）。
 */
export function LoginLink({ isLoggedIn, labels }: LoginLinkProps) {
  // 高さ tier は md（`--size-control-md` = 32px）に引き上げ済み（Issue #842）。
  // `site-header.tsx` で隣接する `LocaleSwitcher`（tier md・text-sm 14px）と揃える。
  // 旧 sm tier（28px・text-[0.8rem]=12.8px）は §2.3 の 5 段階タイポスケール（12/14/16/20/24px）に
  // 存在しない中間値で描画されており、「意図的な情報設計上の格下げ」として書き直すには根拠が
  // 立たなかった（sm 自体がスケール逸脱であり、隣接差はその副産物）。Issue #829 の追認は本 Issue で撤回する。
  const className = buttonVariants({ variant: 'ghost', size: 'default' })

  if (isLoggedIn) {
    return (
      <form method="post" action="/api/auth/logout" className="contents">
        <button type="submit" className={className}>
          {labels.logout}
        </button>
      </form>
    )
  }

  return (
    // `/api/auth/login` はページではなく副作用のある API ルート（Cookie 発行）。
    // `next/link` のプリフェッチ対象にしたくないため意図的に素の `<a>` にする。
    // eslint-disable-next-line @next/next/no-html-link-for-pages
    <a href="/api/auth/login" className={className}>
      {labels.login}
    </a>
  )
}
