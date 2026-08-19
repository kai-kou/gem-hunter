import { notFound } from 'next/navigation'
import { getRepositoryDetailUseCase } from '@/src/composition/container'
import { DomainError } from '@/src/domain/errors'
import { isLocale, locale as toLocale, type Locale } from '@/src/domain/model/locale'
import { formatMessage } from '@/src/shared/i18n/format-message'
import { getMessages } from '@/src/shared/i18n/messages'
import { RepositoryDetail } from '@/src/ui/repository-detail'

/**
 * 独立 URL の詳細ページ（AC-4 / US-16 / US-17 / FR-5 / FR-6）。
 *
 * 動的セグメント（owner / repo）の値は Next.js により decodeURIComponent 済みで渡るため、
 * ここで追加のデコードは行わない（ドット入りリポジトリ名等もそのまま扱える）。
 */
export default async function RepositoryDetailPage({
  params,
}: {
  params: Promise<{ locale: string; owner: string; repo: string }>
}) {
  const { locale: rawLocale, owner, repo } = await params
  if (!isLocale(rawLocale)) {
    notFound()
  }
  const locale: Locale = toLocale(rawLocale)
  const messages = getMessages(locale)

  let repository
  try {
    repository = await getRepositoryDetailUseCase()({ owner, repo })
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
      />
    </main>
  )
}
