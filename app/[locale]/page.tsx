import { notFound } from 'next/navigation'
import { getSessionAccessToken } from '@/src/composition/auth'
import { searchRepositoriesUseCase } from '@/src/composition/container'
import { DomainError } from '@/src/domain/errors'
import { isLocale, locale as toLocale, type Locale } from '@/src/domain/model/locale'
import { tryPageNumber } from '@/src/domain/model/page-number'
import { tryParse as tryPerPage } from '@/src/domain/model/per-page'
import type { SearchResult } from '@/src/domain/model/repository'
import { trySearchKeyword } from '@/src/domain/model/search-keyword'
import { tryParse as trySortOrder } from '@/src/domain/model/sort-order'
import { formatMessage } from '@/src/shared/i18n/format-message'
import { toIntlLocaleTag } from '@/src/ui/i18n/intl-locale-tag'
import { getMessages, type Messages } from '@/src/shared/i18n/messages'
import { buildSearchUrl } from '@/src/ui/url/build-search-url'
import { parseSearchParams, type RawSearchParams } from '@/src/ui/url/search-params'
import { LocaleSwitcher } from '@/src/ui/locale-switcher'
import { Pagination } from '@/src/ui/pagination'
import { PerPagePicker } from '@/src/ui/per-page-picker'
import { RepositoryList } from '@/src/ui/repository-list'
import { SearchForm } from '@/src/ui/search-form'
import { SortPicker } from '@/src/ui/sort-picker'

type SearchState =
  | { status: 'idle' }
  | { status: 'ok'; result: SearchResult }
  | { status: 'error'; message: string }

async function runSearch(
  rawKeyword: string,
  rawPage: number,
  rawSort: string,
  rawPerPage: number,
  messages: Messages,
  accessToken: string | null,
): Promise<SearchState> {
  // 境界（URL）で値オブジェクトへ変換する（domain-model.md §4）
  const keyword = trySearchKeyword(rawKeyword)
  if (keyword === null) {
    return { status: 'idle' }
  }

  try {
    const result = await searchRepositoriesUseCase(accessToken)({
      keyword,
      page: tryPageNumber(rawPage),
      sort: trySortOrder(rawSort),
      perPage: tryPerPage(rawPerPage),
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
  const { keyword, page, sort, perPage } = parseSearchParams(rawSearchParams)
  const accessToken = await getSessionAccessToken()
  const state = await runSearch(keyword, page, sort, perPage, messages, accessToken)
  const basePath = `/${locale}`
  const searchState = { keyword, page, sort, perPage }
  const currentPath = buildSearchUrl(basePath, searchState)

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
      <h1 className="text-2xl font-semibold">{messages.home.title}</h1>
      <p className="text-muted-foreground mt-1 mb-6 text-sm">{messages.home.description}</p>

      <SearchForm
        keyword={keyword}
        action={basePath}
        labels={{
          inputLabel: messages.home.searchLabel,
          placeholder: messages.home.searchPlaceholder,
          submit: messages.home.searchSubmit,
        }}
      />

      {state.status === 'ok' ? (
        // 検索欄の直下に横並びのコントロール行（ソート切替 + 表示件数切替）を置く
        // （ui-ux-guidelines.md §4.1）。モバイルでは flex-wrap で縦積みに落ちる。
        <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-2">
          <SortPicker
            basePath={basePath}
            current={searchState}
            labels={{
              navLabel: messages.home.sortLabel,
              options: messages.home.sortOptions,
            }}
          />
          <PerPagePicker
            basePath={basePath}
            current={searchState}
            labels={{
              navLabel: messages.home.perPageLabel,
              optionLabel: messages.home.perPageOptionLabel,
            }}
          />
        </div>
      ) : null}

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
              searchState={searchState}
            />
            {state.result.items.length > 0 ? (
              <Pagination
                basePath={basePath}
                current={searchState}
                totalCount={state.result.totalCount}
                labels={{
                  navLabel: messages.home.paginationLabel,
                  prev: messages.home.pagePrev,
                  next: messages.home.pageNext,
                  current: messages.home.pageCurrent,
                  limitReached: messages.home.pageLimitReached,
                }}
              />
            ) : null}
          </>
        ) : null}
      </section>
    </main>
  )
}
