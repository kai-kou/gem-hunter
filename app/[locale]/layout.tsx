import type { Metadata, Viewport } from 'next'
import { Geist, Geist_Mono } from 'next/font/google'
import Link from 'next/link'
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
        {/*
          Issue #334 F-1/F-2: ツールタイトルを共有ヘッダーに 1 箇所だけ置き、全ページから
          同じ挙動（クリックで /{locale} へ遷移し未検索状態へ戻る）を提供する
          （whiteboard `feedback334_detail_readme_20260821` round3 lead 裁定）。
          🔴 リンク先は `buildSearchUrl` を経由しない固定 `/{locale}`（検索条件を捨てて
          未検索状態へ戻るのが F-1 の要件であり、条件を引き継ぐ挙動と矛盾する）。
          h1 はこのタイトルだけが持つ（各ページの自前 h1 は撤去・h2 へ降格済み）。
        */}
        <header className="flex items-center justify-between px-4 py-2">
          <h1 className="text-base font-semibold">
            <Link
              href={`/${locale}`}
              className="text-primary rounded-sm underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring"
            >
              {messages.home.title}
            </Link>
          </h1>
          {showAuthLink ? (
            <LoginLink
              isLoggedIn={isLoggedIn}
              labels={{ login: messages.common.auth.login, logout: messages.common.auth.logout }}
            />
          ) : null}
        </header>
        {children}
      </body>
    </html>
  )
}
