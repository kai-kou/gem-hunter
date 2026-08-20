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
 * viewport export が無いと Next.js は `<meta name="viewport">` を一切出力せず、
 * モバイルブラウザは既定の仮想ビューポート（980px 前後）でレイアウトしてしまい、
 * 375px 幅の実測が成立しない（E-16 / NFR-15）。
 * 🔴 `maximum-scale` / `user-scalable=no` は付けない（拡大を禁止すると
 * WCAG 1.4.4 Resize Text 違反になる・ui-ux-guidelines.md §2.4）。
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
