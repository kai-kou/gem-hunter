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
 * 検索の実行結果を待つ 2 つの表示（ライブリージョンの文言・結果本体）。
 *
 * 🔴 `<Suspense>` は **ライブリージョンの内側** に置く（`ui-ux-guidelines.md` §7.2:
 * 「ライブリージョンは初期 DOM に空で常設し、中身を書き換える。要素ごと動的挿入しない」）。
 * リージョン要素ごと動的挿入すると「読み込み中 → 157 件中 20 件を表示」の遷移が
 * スクリーンリーダーへ一切通知されない（`NFR-12` / `US-26`）。
 *
 * 結果リスト本体と `ErrorNotice`（`role="alert"`）はライブリージョンの **外** に置き、
 * polite リージョンへ assertive を入れ子にしない（同 §7.2）。そのため待つ処理は 2 箇所に
 * 分かれるが、`runSearch()` の Promise を 1 本だけ作って両方へ渡すので検索は 1 回しか走らない。
 */
async function SearchStatusText({
  statePromise,
  locale,
  messages,
}: {
  statePromise: Promise<SearchState>
  locale: Locale
  messages: Messages
}) {
  const state = await statePromise

  if (state.status === 'idle') {
    return <>{messages.home.idle}</>
  }
  if (state.status === 'error') {
    // エラー文言は `ErrorNotice`（role="alert"）が担当する。ここへ重ねると二重読み上げになる。
    return null
  }
  return (
    <>
      {formatMessage(messages.home.resultCount, {
        total: state.result.totalCount.toLocaleString(toIntlLocaleTag(locale)),
        shown: String(state.result.items.length),
      })}
    </>
  )
}

async function SearchBody({
  statePromise,
  basePath,
  currentPath,
  searchState,
  locale,
  messages,
  isLoggedIn,
  showAuthLink,
}: {
  statePromise: Promise<SearchState>
  basePath: string
  currentPath: string
  searchState: { keyword: string; page: number; sort: string; perPage: number }
  locale: Locale
  messages: Messages
  isLoggedIn: boolean
  showAuthLink: boolean
}) {
  const state = await statePromise

  if (state.status === 'error') {
    return (
      <ErrorNotice
        presentation={toErrorPresentation(state.kind, messages, {
          locale,
          retryAfter: state.retryAfter,
          retryAfterSeconds: state.retryAfterSeconds,
          isLoggedIn,
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
    )
  }

  if (state.status !== 'ok') {
    return null
  }

  return (
    <>
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
  const hasKeyword = rawKeyword.trim().length > 0

  /**
   * 🔴 `<Suspense>` に検索条件由来の `key` を与える（`US-22`）。React は transition 中の
   * **既存の** 境界へ fallback を再表示しないため、key が無いとページング・ソート変更・
   * 表示件数変更（`next/link` のクライアント遷移）で「読み込み中」が出ず、古い一覧が
   * 残ったままになる。生キーワードを含めて作る（`currentPath` は不正値を丸めるため、
   * 別の不正キーワードへ変えても key が変わらない）。
   */
  const suspenseKey = buildSearchUrl(basePath, { ...searchState, keyword: rawKeyword })

  // 🔴 Promise は 1 本だけ作り、ライブリージョン側と結果本体側の両方へ渡す（検索は 1 回）。
  //    どちらの await より前に reject しても unhandled rejection にしないため、no-op を 1 つ張る。
  const statePromise = runSearch(rawKeyword, page, sort, perPage, accessToken)
  void statePromise.catch(() => undefined)

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
        検索欄の直下に横並びのコントロール行（ソート切替 + 表示件数切替）を置く
        （ui-ux-guidelines.md §4.1）。モバイルでは flex-wrap で縦積みに落ちる。
        🔴 `<Suspense>` の外に置く: 結果待ちやエラーでコントロールが DOM から消えると
        レイアウトが上下に動き、Tab 順序が不安定になり、エラー時は「ソートを変えて
        やり直す」回復手段まで絶たれる。現在値は searchParams から取れるので結果を待つ必要はない。
      */}
      {hasKeyword ? (
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

      {/*
        ライブリージョン（初期 DOM に常設し、中身だけを書き換える・ui-ux-guidelines.md §7.2）。
        読み込み中（US-22）は fallback がストリーミングで先に届き、解決後は件数表示へ
        書き換わる。0 件表示（`RepositoryList` の role="status"）とは別要素・別文言なので
        区別できる（AC-8）。
      */}
      <section id="search-status" aria-live="polite" className="text-muted-foreground mt-6 text-sm">
        <Suspense  fallback={<LoadingIndicator label={messages.common.loading} />}>
          <SearchStatusText statePromise={statePromise} locale={locale} messages={messages} />
        </Suspense>
      </section>

      <Suspense  fallback={null}>
        <SearchBody
          statePromise={statePromise}
          basePath={basePath}
          currentPath={currentPath}
          searchState={searchState}
          locale={locale}
          messages={messages}
          isLoggedIn={accessToken !== null}
          showAuthLink={isAuthConfigured()}
        />
      </Suspense>
    </main>
  )
}
