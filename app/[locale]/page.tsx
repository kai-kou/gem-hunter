import { notFound } from 'next/navigation'
import { searchRepositoriesUseCase } from '@/src/composition/container'
import { DomainError } from '@/src/domain/errors'
import { isLocale, locale as toLocale, type Locale } from '@/src/domain/model/locale'
import { tryPageNumber } from '@/src/domain/model/page-number'
import type { SearchResult } from '@/src/domain/model/repository'
import { trySearchKeyword } from '@/src/domain/model/search-keyword'
import { formatMessage } from '@/src/shared/i18n/format-message'
import { toIntlLocaleTag } from '@/src/ui/i18n/intl-locale-tag'
import { getMessages, type Messages } from '@/src/shared/i18n/messages'
import { parseSearchParams, type RawSearchParams } from '@/src/ui/url/search-params'
import { RepositoryList } from '@/src/ui/repository-list'
import { SearchForm } from '@/src/ui/search-form'

type SearchState =
  | { status: 'idle' }
  | { status: 'ok'; result: SearchResult }
  | { status: 'error'; message: string }

async function runSearch(
  rawKeyword: string,
  rawPage: number,
  messages: Messages,
): Promise<SearchState> {
  // 境界（URL）で値オブジェクトへ変換する（domain-model.md §4）
  const keyword = trySearchKeyword(rawKeyword)
  if (keyword === null) {
    return { status: 'idle' }
  }

  try {
    const result = await searchRepositoriesUseCase()({
      keyword,
      page: tryPageNumber(rawPage),
    })
    return { status: 'ok', result }
  } catch (error) {
    if (error instanceof DomainError) {
      return {
        status: 'error',
        message: formatMessage(messages.home.searchError, { message: error.message }),
      }
    }
    throw error
  }
}

export default async function LocaleHome({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>
  searchParams: Promise<RawSearchParams>
}) {
  const { locale: rawLocale } = await params
  if (!isLocale(rawLocale)) {
    notFound()
  }
  const locale: Locale = toLocale(rawLocale)
  const messages = getMessages(locale)

  const rawSearchParams = await searchParams
  const { keyword, page } = parseSearchParams(rawSearchParams)
  const state = await runSearch(keyword, page, messages)

  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-10">
      <h1 className="text-2xl font-semibold">{messages.home.title}</h1>
      <p className="text-muted-foreground mt-1 mb-6 text-sm">{messages.home.description}</p>

      <SearchForm
        keyword={keyword}
        action={`/${locale}`}
        labels={{
          inputLabel: messages.home.searchLabel,
          placeholder: messages.home.searchPlaceholder,
          submit: messages.home.searchSubmit,
        }}
      />

      <section className="mt-6" aria-live="polite">
        {state.status === 'idle' ? (
          <p className="text-muted-foreground text-sm">{messages.home.idle}</p>
        ) : null}

        {state.status === 'error' ? (
          <p role="alert" className="text-destructive text-sm">
            {state.message}
          </p>
        ) : null}

        {state.status === 'ok' ? (
          <>
            <p className="text-muted-foreground text-sm">
              {formatMessage(messages.home.resultCount, {
                total: state.result.totalCount.toLocaleString(toIntlLocaleTag(locale)),
                shown: String(state.result.items.length),
              })}
            </p>
            <RepositoryList
              items={state.result.items}
              labels={{
                empty: messages.home.empty,
                starCount: messages.home.starCount,
                updatedAt: messages.home.updatedAt,
              }}
              locale={locale}
            />
          </>
        ) : null}
      </section>
    </main>
  )
}
