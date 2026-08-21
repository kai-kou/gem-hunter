import type { Metadata } from 'next'
import { locale as getRootLocale } from 'next/root-params'
import { getSessionAccessToken, isAuthConfigured } from '@/src/composition/auth'
import { tryLocale } from '@/src/domain/model/locale'
import { getMessages } from '@/src/shared/i18n/messages'
import { BackLink } from '@/src/ui/back-link'
import { SetDocumentTitle } from '@/src/ui/set-document-title'
import { SiteHeader } from '@/src/ui/site-header'

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
 *
 * `isLoggedIn` / `showAuthLink` は `params` を経由しない `getSessionAccessToken()` /
 * `isAuthConfigured()` の直接呼び出しで新規に配線する（`app/[locale]/page.tsx` 冒頭と
 * 同じパターン。どちらも Cookie/環境変数からしか値を取らないため `not-found.js` の
 * props 制約に抵触しない・whiteboard round3 frontend_arch 決定）。
 */
export default async function NotFound() {
  const rawLocale = await getRootLocale()
  const locale = tryLocale(rawLocale)
  const messages = getMessages(locale)

  // not-found.js は searchParams を持てないため検索条件を保持する実利が無い。
  // buildLocaleUrl が既に想定する「クエリなしの /{locale}」をそのまま currentPath として使う。
  const currentPath = `/${locale}`

  const showAuthLink = isAuthConfigured()
  const isLoggedIn = showAuthLink && (await getSessionAccessToken()) !== null

  return (
    <>
      <SiteHeader
        locale={locale}
        currentPath={currentPath}
        title={messages.home.title}
        localeSwitcherLabels={{
          navLabel: messages.common.localeSwitcher.navLabel,
          localeNames: messages.common.localeSwitcher.localeNames,
          switchedAnnouncement: messages.common.localeSwitcher.switchedAnnouncement,
        }}
        isLoggedIn={isLoggedIn}
        showAuthLink={showAuthLink}
        authLabels={
          showAuthLink
            ? { login: messages.common.auth.login, logout: messages.common.auth.logout }
            : undefined
        }
      />
      <main className="mx-auto w-full max-w-3xl px-4 py-10">
        {/* `generateMetadata` だけではハイドレーション後に title が巻き戻る（下記コメント参照）ため、
            クライアント側で確実に上書きする */}
        <SetDocumentTitle title={messages.detail.notFound} />
        {/* 404 イラスト（装飾・alt="" 固定・ロケール非依存 1 枚）。h2 の直前に置く。
            この画面には role="status"/role="alert" が一切存在しないため、0 件表示で必要な
            「ライブリージョンの外に出す」制約自体がそもそも発生しない
            （whiteboard round3 a11y_i18n 確定マークアップ）。 */}
        {/* eslint-disable-next-line @next/next/no-img-element -- INF-11 */}
        <img
          src="/images/not-found.webp"
          alt=""
          width={320}
          height={320}
          loading="eager"
          decoding="async"
          className="mx-auto mb-4 h-auto w-40"
        />
        {/* 🔴 h1 は共有ヘッダー（`src/ui/site-header.tsx`・page から呼ぶ）が持つため h2 へ降格
            （Issue #334 F-1/F-2・whiteboard round3 lead 裁定）。 */}
        <h2 className="text-2xl font-semibold">{messages.detail.notFound}</h2>
        <p className="mt-4">
          <BackLink locale={locale} labels={messages.detail} />
        </p>
      </main>
    </>
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
