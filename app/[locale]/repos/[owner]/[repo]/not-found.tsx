import type { Metadata } from 'next'
import { locale as getRootLocale } from 'next/root-params'
import { tryLocale } from '@/src/domain/model/locale'
import { getMessages } from '@/src/shared/i18n/messages'
import { BackLink } from '@/src/ui/back-link'
import { SetDocumentTitle } from '@/src/ui/set-document-title'

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
      {/* `generateMetadata` だけではハイドレーション後に title が巻き戻る（下記コメント参照）ため、
          クライアント側で確実に上書きする */}
      <SetDocumentTitle title={messages.detail.notFound} />
      <h1 className="text-2xl font-semibold">{messages.detail.notFound}</h1>
      <p className="mt-4">
        <BackLink locale={locale} labels={messages.detail} />
      </p>
    </main>
  )
}

/**
 * document title を確実に変化させ、ルートアナウンサー
 * （`node_modules/next/dist/client/components/app-router-announcer.js` 52-59 行目）に
 * クライアント遷移での 404 到達を伝える（PR #127 セルフレビュー指摘1・CRITICAL）。
 * `document.title` が truthy だと h1 フォールバックが発生せず、title 不変のままだと
 * スクリーンリーダーに何も announce されない。
 *
 * `not-found.js` のデフォルトエクスポート（React コンポーネント）自体は props を受け取らない
 * 仕様だが、`generateMetadata` はこの制約の対象外: メタデータ解決
 * （`node_modules/next/dist/lib/metadata/resolve-metadata.js` の `collectMetadata` /
 * `resolveMetadataItemsImpl`）はツリーをルートから当該セグメントまで辿りながら `params` を
 * 累積して渡すため、`app/[locale]/repos/[owner]/[repo]/not-found.tsx` の `generateMetadata` には
 * `{ locale, owner, repo }` が届く。ロケール別文言が目的で `owner`/`repo` は使わないため型には含めない。
 * `next/root-params` は使わない（generateMetadata 内での対応関係が公式ドキュメントで明言されておらず、
 * こちらの標準 `params` 経路の方が確実なため）。
 *
 * ルートパラメータ同様、値は URL セグメントをそのまま返す（`isLocale` の再検証はされていない）ため
 * `tryLocale()` で不正値を既定ロケールへ倒す。
 */
export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>
}): Promise<Metadata> {
  const { locale: rawLocale } = await params
  const locale = tryLocale(rawLocale)
  const messages = getMessages(locale)

  return { title: messages.detail.notFound }
}
