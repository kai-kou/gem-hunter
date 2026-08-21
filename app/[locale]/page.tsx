import { Suspense } from 'react'
import { headers } from 'next/headers'
import { notFound } from 'next/navigation'
import { getSessionAccessToken, isAuthConfigured } from '@/src/composition/auth'
import { getDailyDigestUseCase, searchRepositoriesUseCase } from '@/src/composition/container'
import { DAILY_DIGEST_LIMIT } from '@/src/composition/digest-feed'
import { enforceSearchRateLimit } from '@/src/composition/rate-limit'
import { DomainError, RateLimitExceededError, type ErrorKind } from '@/src/domain/errors'
import { tryParse as tryDateSeed } from '@/src/domain/model/date-seed'
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
import { AttributionNotice } from '@/src/ui/attribution-notice'
import { DailyDigest } from '@/src/ui/daily-digest'
import { ErrorNotice } from '@/src/ui/error-notice'
import { FocusOnNavigate } from '@/src/ui/focus-on-navigate'
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

    // Issue #122: 自リクエストの間引き（RateLimitPort）。未入力（idle・上の early return）
    // では枠を消費せず、値オブジェクトへの変換が通った（= 400 にならない）キーワードだけを
    // 対象にする。超過時は `RateLimitExceededError` を投げ、下の catch がそのまま
    // ローカライズ済み表示（`toErrorPresentation`）に繋げる（新しい分岐は足さない）。
    // `headers()` の呼び出しでこのページは動的レンダリングになるが、既に `searchParams`
    // を使っているため元から動的である（新たな制約ではない）。
    // 🔴 SP-16 争点6: `rawSort` を渡し、`sort=gemIndex`（最大 10 倍の upstream 呼び出し）なら
    // 別スロット・低い上限で消費させる（`src/composition/rate-limit.ts` が分岐する）。
    await enforceSearchRateLimit(await headers(), rawSort)

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
          dependentLabel: messages.home.digest.dependentLabel,
          gemIndexLabel: messages.home.digest.gemIndexLabel,
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

  // SP-14: 日次ダイジェスト（キーワード非依存の発見面・`ADR 0014` §2.2）。
  // `?date=YYYYMMDD` は不正値・未指定を当日（UTC）へフォールバックする（`tryParse` 契約）。
  //
  // 🔴 **キーワード検索中は非表示にする**（ADR 0014 §2.1「開いた瞬間に見える」は未検索状態の
  //    要件で、検索実行中まで並置する要件はない）。検索結果一覧と Gem 一覧が同時に `<ol>` として
  //    DOM に並ぶと、既存 E2E の `getByRole('list').first()` が Gem 一覧を先に拾って検索結果を
  //    取れなくなる（SP-1/SP-7/SP-10 と衝突）。「発見面」と「検索面」を排他表示にする。
  //    データ取得はサーバー側で await するが、静的 JSON + slice + sort で安価。
  const rawDate = Array.isArray(rawSearchParams.date)
    ? rawSearchParams.date[0]
    : rawSearchParams.date
  const dateSeed = tryDateSeed(rawDate, new Date())
  //
  // 🔴 **二重防御**: 候補プールの読み込みは `StaticGemDigest` 側で例外を投げない設計だが、
  //    ここでも `.catch(() => null)` を張って「ダイジェストの失敗がトップページ全体を
  //    500 にする」経路を塞ぐ（`app/` 配下に `error.tsx` は無く、失敗すれば既存の検索機能まで
  //    巻き添えになる）。`null` は下の既存分岐でそのまま非表示に倒れる。
  const dailyDigest = hasKeyword
    ? null
    : await getDailyDigestUseCase()({ seed: dateSeed, limit: DAILY_DIGEST_LIMIT }).catch(() => null)

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
        SP-14: 発見面（`ADR 0014`）。検索フォームの直下・コントロール行より前に置き、
        キーワード未入力のときだけ表示する（上のコメント参照）。出典表示（`D-29`）は
        同じ排他条件で表示し、ライセンス URL と改変明示を伴う。
      */}
      {dailyDigest !== null ? (
        <>
          <DailyDigest
            digest={dailyDigest}
            locale={locale}
            labels={{
              heading: messages.home.digest.heading,
              empty: messages.home.digest.empty,
              dependentLabel: messages.home.digest.dependentLabel,
              starsLabel: messages.home.digest.starsLabel,
              gemIndexLabel: messages.home.digest.gemIndexLabel,
              newBadge: messages.home.digest.newBadge,
              firstVisitNote: messages.home.digest.firstVisitNote,
              rssLink: messages.home.digest.rssLink,
            }}
          />
          <AttributionNotice
            meta={dailyDigest.meta}
            locale={locale}
            labels={{ attribution: messages.home.digest.attribution }}
          />
        </>
      ) : null}

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
        結果一覧の見出し（`E-15` / `ui-ux-guidelines.md` §7.1）。`tabIndex={-1}` を付け、
        ページ送り・ソート・件数切替（next/link のクライアント遷移）の完了後に
        `FocusOnNavigate` からここへ focus() を移す。検索フォームのネイティブ GET 送信
        （フルリロード）は対象外（本コンポーネントごと初回マウントからやり直しになるため、
        `FocusOnNavigate` 側の「初回描画では focus しない」設計がそのまま対象外を実現する）。
      */}
      <h2
        id="results-heading"
        tabIndex={-1}
        className="mt-6 text-lg font-semibold outline-none focus-visible:ring-3 focus-visible:ring-ring rounded-sm"
      >
        {messages.home.resultsHeading}
      </h2>

      {/*
        ライブリージョン（初期 DOM に常設し、中身だけを書き換える・ui-ux-guidelines.md §7.2）。
        読み込み中（US-22）は fallback がストリーミングで先に届き、解決後は件数表示へ
        書き換わる。0 件表示（`RepositoryList` の role="status"）とは別要素・別文言なので
        区別できる（AC-8）。
        🔴 訂正（PR #183 実測・0 件時は下記の `RepositoryList` 側 `role="status"` と 2 つ同時に
        存在するため「唯一」は事実ではない）: この `section` が守るのは **入れ子にしない** こと。
        `LoadingIndicator` は自身の role/aria-live を持たない表示専用コンポーネントへ変更済みで、
        この `section`（`aria-live="polite"`）の **内側** に別のライブリージョンを重ねない
        （`RepositoryList` の `role="status"` は本 `section` の **外**・兄弟要素であり、
        入れ子ではないので問題ない・§7.2）。
      */}
      <section
        id="search-status"
        role="status"
        aria-live="polite"
        className="text-muted-foreground mt-6 text-sm"
      >
        <Suspense key={suspenseKey} fallback={<LoadingIndicator label={messages.common.loading} />}>
          <SearchStatusText statePromise={statePromise} locale={locale} messages={messages} />
        </Suspense>
      </section>

      <Suspense key={suspenseKey} fallback={null}>
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

      {/*
        `key={suspenseKey}` の Suspense 境界の外（= remount されない位置）に置く。
        `watch={currentPath}` はページ送り・ソート・件数切替のたびに値が変わるため、
        このコンポーネント自身は remount されずに props だけが更新され、初回判定
        （`useRef`）が遷移を跨いで機能する（`focus-on-navigate.tsx` 参照）。
      */}
      <FocusOnNavigate watch={currentPath} targetId="results-heading" />
    </main>
  )
}
