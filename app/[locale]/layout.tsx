import type { Metadata, Viewport } from 'next'
import { Geist, Geist_Mono } from 'next/font/google'
import { notFound } from 'next/navigation'
import { getSiteUrl } from '@/src/composition/site-url'
import { isLocale, locale as toLocale, tryLocale, LOCALES } from '@/src/domain/model/locale'
import { getMessages } from '@/src/shared/i18n/messages'
import '../globals.css'

const geistSans = Geist({
  variable: '--font-geist-sans',
  subsets: ['latin'],
})

const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
})

/**
 * 🔴 `description` はロケール依存（Issue #352）なので静的な `metadata` ではなく
 * `generateMetadata` にする（両方は同一ルートセグメントで共存できない・Next.js 仕様）。
 * 不正なロケールは `LocaleLayout` 本体側が `notFound()` を返すため、ここでは
 * 既定ロケールへ倒すだけでよい（`tryLocale`・`app/[locale]/gems/page.tsx` と同じ流儀）。
 */
export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>
}): Promise<Metadata> {
  const { locale: rawLocale } = await params
  const messages = getMessages(tryLocale(rawLocale))
  return {
    // 🔴 `metadataBase` 未設定だと `opengraph-image` 等の相対 URL 解決が既定の
    // `http://localhost:3000` にフォールバックし、SNS クローラーが OG 画像を取得できなくなる
    // （実デプロイの curl で確認済み・Issue #347 追加タスク）。`getSiteUrl()` は `headers()` を
    // 使わない（`src/composition/site-url.ts` のコメント参照・lead 裁定）。
    metadataBase: new URL(getSiteUrl()),
    title: 'gem-hunter',
    description: messages.home.description,
  }
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

  return (
    <html lang={locale} className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  )
}
