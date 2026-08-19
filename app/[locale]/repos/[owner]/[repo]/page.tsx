import { notFound } from 'next/navigation'
import { getSessionAccessToken } from '@/src/composition/auth'
import { getRepositoryDetailUseCase } from '@/src/composition/container'
import { DomainError } from '@/src/domain/errors'
import { isLocale, locale as toLocale, type Locale } from '@/src/domain/model/locale'
import { formatMessage } from '@/src/shared/i18n/format-message'
import { getMessages } from '@/src/shared/i18n/messages'
import { buildSearchUrl } from '@/src/ui/url/build-search-url'
import { parseSearchParams, type RawSearchParams } from '@/src/ui/url/search-params'
import { LocaleSwitcher } from '@/src/ui/locale-switcher'
import { RepositoryDetail } from '@/src/ui/repository-detail'

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
  const currentPath = `/${locale}/repos/${owner}/${repo}`

  const accessToken = await getSessionAccessToken()
  let repository
  try {
    repository = await getRepositoryDetailUseCase(accessToken)({ owner, repo })
  } catch (error) {
    if (error instanceof DomainError) {
      return (
        <main className="mx-auto w-full max-w-3xl px-4 py-10">
          <p role="alert" className="text-destructive text-sm">
            {formatMessage(messages.detail.loadError, { message: error.message })}
          </p>
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
