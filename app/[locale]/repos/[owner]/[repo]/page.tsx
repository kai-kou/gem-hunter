import type { Metadata } from 'next'
import { notFound } from 'next/navigation'
import { getSessionAccessToken, isAuthConfigured } from '@/src/composition/auth'
import { getRepositoryDetailUseCase } from '@/src/composition/container'
import { DomainError, RateLimitExceededError, type ErrorKind } from '@/src/domain/errors'
import { isLocale, locale as toLocale, type Locale } from '@/src/domain/model/locale'
import { getMessages } from '@/src/shared/i18n/messages'
import { toErrorPresentation } from '@/src/ui/i18n/error-message'
import { buildSearchUrl } from '@/src/ui/url/build-search-url'
import { parseSearchParams, type RawSearchParams } from '@/src/ui/url/search-params'
import { BackLink } from '@/src/ui/back-link'
import { ErrorNotice } from '@/src/ui/error-notice'
import { LocaleSwitcher } from '@/src/ui/locale-switcher'
import { RepositoryDetail } from '@/src/ui/repository-detail'
import { SetDocumentTitle } from '@/src/ui/set-document-title'

/**
 * 独立 URL の詳細ページ（AC-4 / US-16 / US-17 / FR-5 / FR-6）。
 *
 * 動的セグメント（owner / repo）の値は Next.js により decodeURIComponent 済みで渡るため、
 * ここで追加のデコードは行わない（ドット入りリポジトリ名等もそのまま扱える）。
 *
 * `searchParams`（SP-7）: 一覧から遷移してきたときに検索条件（keyword/page/sort/perPage）が
 * `repository-list.tsx` の詳細リンクからクエリとして継ぎ足されて届く。ここで受け取り、
 * 一覧へ戻るリンク（`backHref`）へそのまま乗せ直す（`RepositoryDetail` → `BackLink`）。
 * 直接この URL を開いた場合（検索条件なし）は既定値へ倒れ、`buildSearchUrl` が
 * クエリなしの `/{locale}` を返す（`BackLink` の既定と同じ挙動）。
 *
 * 🔴 **本ページに `<Suspense>`（および `loading.tsx`）を置かない**（SP-9 で検討のうえ見送り）。
 * 取得結果が `null` のとき `notFound()` で **HTTP 404 を返す** のが `AC-5` の要件で、
 * Suspense fallback が描画された時点でレスポンスヘッダが送出済みになり 404 を返せなくなる
 * （Next.js `file-conventions/loading.md`「Place `notFound()` before those boundaries」）。
 * 読み込み中表示（US-22）は検索一覧側（`app/[locale]/page.tsx`）で担保する。
 */
export default async function RepositoryDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string; owner: string; repo: string }>
  searchParams: Promise<RawSearchParams>
}) {
  const { locale: rawLocale, owner, repo } = await params
  if (!isLocale(rawLocale)) {
    notFound()
  }
  const locale: Locale = toLocale(rawLocale)
  const messages = getMessages(locale)

  const rawSearchParams = await searchParams
  const searchState = parseSearchParams(rawSearchParams)
  const backHref = buildSearchUrl(`/${locale}`, searchState)
  /**
   * 自分自身の URL（再試行・言語切替の行き先）。
   *
   * 🔴 検索条件（`page` / `sort` / `per_page`）を **落とさない**（落とすと再試行後の
   * 「一覧へ戻る」が 1 ページ目・既定ソートに戻り `SP-7` の成果を壊す）。
   * 🔴 `owner` / `repo` は Next.js が decodeURIComponent 済みで渡すため、URL へ戻すときは
   * 必ず再エンコードする（`..` や `/` を含む値を踏ませたときに行き先がずれるのを防ぐ）。
   */
  const detailPath = `/${locale}/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}`
  const currentPath = buildSearchUrl(detailPath, searchState)

  const accessToken = await getSessionAccessToken()
  let repository
  try {
    repository = await getRepositoryDetailUseCase(accessToken)({ owner, repo })
  } catch (error) {
    if (error instanceof DomainError) {
      // 🔴 `error.message`（開発者向けの内部文言）は画面へ出さず、種別から文言を組み立てる
      //    （NFR-9 / prd.md §7 / Issue #107）。
      const kind: ErrorKind = error.kind
      const rateLimit = error instanceof RateLimitExceededError ? error : undefined
      const showAuthLink = isAuthConfigured()
      return (
        <main className="mx-auto w-full max-w-3xl px-4 py-10">
          {/*
            🔴 エラー時も見出し・言語切替を失わない（`NFR-12` / `US-26`）。これらを落とすと
            見出しが 1 つも無い文書になり、スクリーンリーダーの見出しナビゲーションで到達できない。
            また `role="alert"` は「動的な挿入・変化」で発火する仕様のため、初期 HTML に最初から
            存在するこのケースでは読み上げられない。通常の見出し + 本文として構成し、
            `role="alert"` に依存せずに内容が伝わるようにする。
            見出しは対象リポジトリ名（成功パスの `RepositoryDetail` と同じ粒度）で、
            `messages/*.json` へキーを増やさずに構成できる。
          */}
          <LocaleSwitcher
            currentLocale={locale}
            currentPath={currentPath}
            labels={{
              navLabel: messages.common.localeSwitcher.navLabel,
              localeNames: messages.common.localeSwitcher.localeNames,
            }}
          />
          <h1 className="mb-4 text-2xl font-semibold">{`${owner}/${repo}`}</h1>
          <ErrorNotice
            presentation={toErrorPresentation(kind, messages, {
              locale,
              retryAfter: rateLimit?.retryAfter,
              retryAfterSeconds: rateLimit?.retryAfterSeconds,
              isLoggedIn: accessToken !== null,
            })}
            // 再試行手段（US-24）: いま失敗した詳細 URL をそのまま開き直す。
            retryHref={currentPath}
            retryLabel={messages.common.retry}
            loginHref={showAuthLink ? '/api/auth/login' : undefined}
            loginLabel={showAuthLink ? messages.common.auth.login : undefined}
          />
          {/* 失敗しても行き止まりにしない（一覧へ戻れる・not-found.tsx と同じ導線）。 */}
          <div className="mt-6">
            <BackLink
              locale={locale}
              labels={{ backLink: messages.detail.backLink }}
              href={backHref}
            />
          </div>
        </main>
      )
    }
    throw error
  }

  if (repository === null) {
    notFound()
  }

  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-10">
      {/* `generateMetadata`（下記）は URL セグメントから SSR 時点の <title> を出すが、
          ハイドレーション後に document.title が親レイアウトの既定値へ巻き戻らないことまでは
          保証しないため、クライアント側でも確実に設定する（not-found.tsx / PR #127 と同じパターン）。
          fullName は API 由来の正規表記（owner の大文字小文字を含む）で generateMetadata より正確。 */}
      <SetDocumentTitle title={repository.fullName} />
      <LocaleSwitcher
        currentLocale={locale}
        currentPath={currentPath}
        labels={{
          navLabel: messages.common.localeSwitcher.navLabel,
          localeNames: messages.common.localeSwitcher.localeNames,
        }}
      />
      <RepositoryDetail
        repository={repository}
        labels={{
          backLink: messages.detail.backLink,
          language: messages.detail.language,
          starCount: messages.detail.starCount,
          watcherCount: messages.detail.watcherCount,
          forkCount: messages.detail.forkCount,
          openIssueCount: messages.detail.openIssueCount,
        }}
        locale={locale}
        backHref={backHref}
      />
    </main>
  )
}

/**
 * ルート変更時のフォーカス移動・ライブリージョンとは別軸の対応（ui-ux-guidelines.md §7.1）:
 * Next.js の route announcer は `document.title` の変化のみを見て発火するため、一覧→詳細の
 * クライアント遷移でも SSR 段階から正しいタイトルを出す（E-15）。
 *
 * 🔴 `getRepositoryDetailUseCase` を呼び直してリポジトリ本体を再取得しない: `generateMetadata` は
 * ページ本体のレンダリングとは独立して評価されうるため、ここで同じユースケースを呼ぶとキャッシュ
 * TTL 内でも往復が増える（`src/composition/container.ts` の `sharedCache` は HIT するが、
 * セッショントークンの再解決など無駄な非同期処理が増える）。`fullName` は通常 `owner/repo` と
 * 一致する（GitHub の大文字小文字の正規化差はタイトルの実用上無視できる）ため、
 * デコード済みの URL セグメントをそのままタイトルに使う。404 の場合は同ディレクトリの
 * `not-found.tsx` が自身の `generateMetadata` で上書きするため、ここでは意識しない。
 */
export async function generateMetadata({
  params,
}: {
  params: Promise<{ owner: string; repo: string }>
}): Promise<Metadata> {
  const { owner, repo } = await params
  return { title: `${owner}/${repo}` }
}
