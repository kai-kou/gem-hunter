import { Suspense } from 'react'
import { notFound } from 'next/navigation'
import { getSessionAccessToken, isAuthConfigured } from '@/src/composition/auth'
import { searchRepositoriesUseCase } from '@/src/composition/container'
import { DomainError, RateLimitExceededError, type ErrorKind } from '@/src/domain/errors'
import { isLocale, locale as toLocale, type Locale } from '@/src/domain/model/locale'
import { tryPageNumber } from '@/src/domain/model/page-number'
import { tryParse as tryPerPage } from '@/src/domain/model/per-page'
import type { SearchResult } from '@/src/domain/model/repository'
import { searchKeyword } from '@/src/domain/model/search-keyword'
import { tryParse as trySortOrder } from '@/src/domain/model/sort-order'
import { formatMessage } from '@/src/shared/i18n/format-message'
import { toIntlLocaleTag } from '@/src/ui/i18n/intl-locale-tag'
import { getMessages, type Messages } from '@/src/shared/i18n/messages'
import { toErrorPresentation } from '@/src/ui/i18n/error-message'
import { buildSearchUrl } from '@/src/ui/url/build-search-url'
import { parseSearchParams, rawKeywordOf, type RawSearchParams } from '@/src/ui/url/search-params'
import { ErrorNotice } from '@/src/ui/error-notice'
import { LoadingIndicator } from '@/src/ui/loading-indicator'
import { LocaleSwitcher } from '@/src/ui/locale-switcher'
import { Pagination } from '@/src/ui/pagination'
import { PerPagePicker } from '@/src/ui/per-page-picker'
import { RepositoryList } from '@/src/ui/repository-list'
import { SearchForm } from '@/src/ui/search-form'
import { SortPicker } from '@/src/ui/sort-picker'

/**
 * 検索の 4 状態（`ui-ux-guidelines.md` §4.4）。
 *
 * 🔴 エラーは **種別（`kind`）だけ** を持ち、`Error.message`（開発者向けの内部文言）は
 * 画面へ運ばない（`NFR-9` / Issue #107）。利用者向けの文言は `toErrorPresentation` が
 * kind + メッセージカタログから組み立てる（`prd.md` §7 の対応表）。
 * 読み込み中（`loading`）は状態値ではなく `<Suspense>` の fallback が担う。
 */
type SearchState =
  | { status: 'idle' }
  | { status: 'ok'; result: SearchResult }
  | { status: 'error'; kind: ErrorKind; retryAfter?: Date; retryAfterSeconds?: number }

async function runSearch(
  rawKeyword: string,
  rawPage: number,
  rawSort: string,
  rawPerPage: number,
  accessToken: string | null,
): Promise<SearchState> {
  // キーワード未入力は「まだ検索していない」状態であってエラーではない（AC-2）。
  if (rawKeyword.trim().length === 0) {
    return { status: 'idle' }
  }

  try {
    // 境界（URL）で値オブジェクトへ変換する（domain-model.md §4）。
    // 🔴 不正値を黙って握りつぶさない（`trySearchKeyword` を使わない）。修飾子入りキーワード
    //    （`react is:private` 等）は `DomainValidationError`（kind: 'validation'）になるので、
    //    下の catch で「検索キーワードを確認してください」相当として画面に出す。null へ倒すと
    //    未入力と同じ idle 表示になり、拒否された事実がユーザーに伝わらない。
    const keyword = searchKeyword(rawKeyword)

    // SP-8: ログイン中はユーザー自身のアクセストークンで叩く（レート枠の切替）。トークンの
    // 供給元が変わっても経路は `GithubRepositoryQuery`（ACL）のままなので、`is:public` 付与と
    // mapper の private 除外という公開限定の防御はそのまま効く（NFR-33 / AC-12）。
    const result = await searchRepositoriesUseCase(accessToken)({
      keyword,
      page: tryPageNumber(rawPage),
      sort: trySortOrder(rawSort),
      perPage: tryPerPage(rawPerPage),
    })
    return { status: 'ok', result }
  } catch (error) {
    if (error instanceof RateLimitExceededError) {
      // 一次（復帰時刻）と二次（再試行秒数）で提示内容が変わる（prd.md §7 / US-25）。
      return {
        status: 'error',
        kind: error.kind,
        retryAfter: error.retryAfter,
        retryAfterSeconds: error.retryAfterSeconds,
      }
    }
    if (error instanceof DomainError) {
      return { status: 'error', kind: error.kind }
    }
    throw error
  }
}

/**
 * 検索の実行と結果表示（`<Suspense>` 配下・US-22）。
 *
 * 🔴 見出し・検索欄（LCP 対象要素）を遅いデータに依存させないため、**待つ部分だけ** を
 * 本コンポーネントへ切り出して `<Suspense>` で包む（`ui-ux-guidelines.md` §8.1）。
 * ルートセグメントの `loading.tsx` は「ページ全体」を fallback へ差し替えてしまい
 * LCP 要素まで消える上に、Loading UI は params を受け取れない仕様（Next.js の
 * `file-conventions/loading.md`「Loading UI components do not accept any parameters」）で
 * ロケール対応の読み込み文言を出せないため、こちらの経路を採る。
 */
async function SearchResults({
  rawKeyword,
  basePath,
  currentPath,
  searchState,
  locale,
  messages,
  accessToken,
  showAuthLink,
}: {
  rawKeyword: string
  basePath: string
  currentPath: string
  searchState: { keyword: string; page: number; sort: string; perPage: number }
  locale: Locale
  messages: Messages
  accessToken: string | null
  showAuthLink: boolean
}) {
  const state = await runSearch(
    rawKeyword,
    searchState.page,
    searchState.sort,
    searchState.perPage,
    accessToken,
  )

  return (
    <>
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
          <ErrorNotice
            presentation={toErrorPresentation(state.kind, messages, {
              locale,
              retryAfter: state.retryAfter,
              retryAfterSeconds: state.retryAfterSeconds,
              isLoggedIn: accessToken !== null,
            })}
            // 再試行手段（US-24）: いま失敗した検索 URL をそのまま開き直す。素の <a> なので
            // クライアント JS を持たない（NFR-3）。
            retryHref={currentPath}
            retryLabel={messages.common.retry}
            // ログイン導線は OAuth 設定が揃っているときだけ（layout.tsx と同じ判定）。
            // 実際に出すかは `loginHint` の有無（= レート制限かつ未ログイン）で ErrorNotice が決める。
            loginHref={showAuthLink ? '/api/auth/login' : undefined}
            loginLabel={showAuthLink ? messages.common.auth.login : undefined}
          />
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
    </>
  )
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
  // 🔴 検索の実行にはキーワードの生値を使う（`parseSearchParams` は不正値を `''` へ倒すため、
  //    そのまま渡すと拒否理由が「未入力」にすり替わる）。入力欄の表示も生値にして、
  //    エラーを見たユーザーが自分の入力を直せるようにする。
  const rawKeyword = rawKeywordOf(rawSearchParams)
  const accessToken = await getSessionAccessToken()
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
        keyword={rawKeyword}
        action={basePath}
        labels={{
          inputLabel: messages.home.searchLabel,
          placeholder: messages.home.searchPlaceholder,
          submit: messages.home.searchSubmit,
        }}
      />

      {/*
        読み込み中（US-22）。検索が解決するまで fallback がストリーミングで先に届く。
        0 件表示（`RepositoryList` の role="status"）とは別要素・別文言なので区別できる（AC-8）。
      */}
      <Suspense fallback={<LoadingIndicator label={messages.common.loading} />}>
        <SearchResults
          rawKeyword={rawKeyword}
          basePath={basePath}
          currentPath={currentPath}
          searchState={searchState}
          locale={locale}
          messages={messages}
          accessToken={accessToken}
          showAuthLink={isAuthConfigured()}
        />
      </Suspense>
    </main>
  )
}
