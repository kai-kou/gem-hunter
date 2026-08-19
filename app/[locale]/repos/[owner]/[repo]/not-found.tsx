import { locale as getRootLocale } from 'next/root-params'
import Link from 'next/link'
import { tryLocale } from '@/src/domain/model/locale'
import { getMessages } from '@/src/shared/i18n/messages'

/**
 * `page.tsx` が `repository === null` のとき呼ぶ `notFound()` の専用 UI（AC-5 / US-19 手順 4）。
 *
 * `not-found.js` は props（`params`）を一切受け取らない仕様のため（file-conventions/not-found.md
 * §Reference §Props）、ロケールは `next/root-params` の `locale` ゲッターで取得する。ルートレイアウトが
 * `app/[locale]/layout.tsx` にあるため `locale` はルートパラメータとして扱われ、
 * この Server Component から直接呼び出せる（next/root-params 導入・v16.3.0）。
 *
 * ルートパラメータの値は URL セグメントをそのまま返す（`isLocale` の再検証はされていない）ため、
 * `tryLocale()` で不正値を既定ロケールへ倒す（domain-model.md §4「URL 由来の値」の方針）。
 */
export default async function NotFound() {
  const rawLocale = await getRootLocale()
  const locale = tryLocale(rawLocale)
  const messages = getMessages(locale)

  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-10">
      <h1 className="text-2xl font-semibold">{messages.detail.notFound}</h1>
      <p className="mt-4">
        <Link
          href={`/${locale}`}
          className="text-primary text-sm underline-offset-4 hover:underline"
        >
          {messages.detail.backLink}
        </Link>
      </p>
    </main>
  )
}
