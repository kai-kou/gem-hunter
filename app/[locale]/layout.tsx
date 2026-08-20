import type { Metadata, Viewport } from 'next'
import { Geist, Geist_Mono } from 'next/font/google'
import { notFound } from 'next/navigation'
import { getSessionAccessToken, isAuthConfigured } from '@/src/composition/auth'
import { isLocale, locale as toLocale, LOCALES } from '@/src/domain/model/locale'
import { getMessages } from '@/src/shared/i18n/messages'
import { LoginLink } from '@/src/ui/login-link'
import '../globals.css'

const geistSans = Geist({
  variable: '--font-geist-sans',
  subsets: ['latin'],
})

const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
})

export const metadata: Metadata = {
  title: 'gem-hunter',
  description: 'GitHub から埋もれた良質なリポジトリを見つける',
}

/**
 * 🔴 訂正（PR #183 実測・#next/dist/docs/01-app/02-guides/migrating/from-create-react-app.md）:
 * この export を丸ごと削除しても Next.js 16.3.1 は既定で同内容の
 * `<meta name="viewport" content="width=device-width, initial-scale=1" />` を自動出力する
 * （公式ドキュメントが明記。旧コメントの「export が無いと一切出力しない」は誤り・実測で反証済み）。
 * それでも本 export を明示的に残す理由は「既定値へ依存しているという事実」を暗黙にしないためと、
 * 次の禁止事項を宣言的に固定するため。
 * 🔴 `maximum-scale` / `user-scalable=no` は付けない（拡大を禁止すると
 * WCAG 1.4.4 Resize Text 違反になる・ui-ux-guidelines.md §2.4。`e2e/sp-10.spec.ts`
 * 「手順2/3 の前提」が SSR 応答の `<meta name="viewport">` を直接検証し、この 2 つの
 * 混入を退行として検知する）。
 */
export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
}

/** サポートロケール分の静的パラメータ（ja / en）。 */
export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }))
}

export default async function LocaleLayout({
  children,
  params,
}: {
  children: React.ReactNode
  params: Promise<{ locale: string }>
}) {
  const { locale: rawLocale } = await params
  if (!isLocale(rawLocale)) {
    notFound()
  }
  const locale = toLocale(rawLocale)
  const messages = getMessages(locale)

  // ログイン導線は OAuth 3 変数 + セッション暗号鍵が揃っているときだけ表示する
  // （`infrastructure-design.md` §8.1: 環境変数未設定でプレビュー環境から静かに消える）。
  const showAuthLink = isAuthConfigured()
  const isLoggedIn = showAuthLink && (await getSessionAccessToken()) !== null

  return (
    <html lang={locale} className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col">
        {showAuthLink ? (
          <div className="flex justify-end px-4 py-2">
            <LoginLink
              isLoggedIn={isLoggedIn}
              labels={{ login: messages.common.auth.login, logout: messages.common.auth.logout }}
            />
          </div>
        ) : null}
        {children}
      </body>
    </html>
  )
}
