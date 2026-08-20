import Link from 'next/link'
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
 * リンクは素の `<a href>` なのでクライアント JS 不要（`SearchForm` と同じ方針・NFR-3）。
 *
 * `buttonVariants({ variant: 'ghost', size: 'sm' })` 経由で描画する（`ui-ux-guidelines.md` §2.4
 * 必須「高さとフォントサイズは cva の size variant 経由でのみ指定する」・PR #141 レビュー指摘）。
 */
export function LoginLink({ isLoggedIn, labels }: LoginLinkProps) {
  const className = buttonVariants({ variant: 'ghost', size: 'sm' })

  if (isLoggedIn) {
    return (
      <Link href="/api/auth/logout" className={className}>
        {labels.logout}
      </Link>
    )
  }

  return (
    <Link href="/api/auth/login" className={className}>
      {labels.login}
    </Link>
  )
}
