import { Suspense } from 'react'
import { headers } from 'next/headers'
import { notFound } from 'next/navigation'
import { getSessionAccessToken, isAuthConfigured } from '@/src/composition/auth'
import {
  DAILY_DIGEST_LIMIT,
  getDailyDigestUseCase,
  lookupGemIndexes,
  searchRepositoriesUseCase,
} from '@/src/composition/container'
import { prepareSearchKeyword } from '@/src/composition/search-guard'
import { DomainError, RateLimitExceededError, type ErrorKind } from '@/src/domain/errors'
import { tryParse as tryDateSeed } from '@/src/domain/model/date-seed'
import { isLocale, locale as toLocale, type Locale } from '@/src/domain/model/locale'
import { DEFAULT_PAGE, tryPageNumber } from '@/src/domain/model/page-number'
import { DEFAULT_PER_PAGE, tryParse as tryPerPage } from '@/src/domain/model/per-page'
import type { SearchResult } from '@/src/domain/model/repository'
import { DEFAULT_SORT_ORDER, tryParse as trySortOrder } from '@/src/domain/model/sort-order'
import { formatMessage } from '@/src/shared/i18n/format-message'
import { toIntlLocaleTag } from '@/src/ui/i18n/intl-locale-tag'
import { getMessages, type Messages } from '@/src/shared/i18n/messages'
import { toErrorPresentation } from '@/src/ui/i18n/error-message'
import { MAX_INCLUDE_FULL_NAMES } from '@/src/usecases/search-gems'
import { buildSearchUrl } from '@/src/ui/url/build-search-url'
import { buildGemListUrl } from '@/src/ui/url/gem-list-url'
import { parseSearchParams, rawKeywordOf, type RawSearchParams } from '@/src/ui/url/search-params'
import { AttributionNotice } from '@/src/ui/attribution-notice'
import { DailyDigest } from '@/src/ui/daily-digest'
import { ErrorNotice } from '@/src/ui/error-notice'
import { GemListLink } from '@/src/ui/gem-list-link'
import { FocusOnNavigate } from '@/src/ui/focus-on-navigate'
import { LoadingIndicator } from '@/src/ui/loading-indicator'
import { Pagination } from '@/src/ui/pagination'
import { PerPagePicker } from '@/src/ui/per-page-picker'
import { RepositoryList } from '@/src/ui/repository-list'
import { SearchForm } from '@/src/ui/search-form'
import { SiteHeader } from '@/src/ui/site-header'
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
    //
    // 「変換 → Issue #122 の自リクエスト間引き（RateLimitPort）」の順序自体が仕様（未入力は
    // 枠を消費しない・400 で弾かれる入力にも枠を使わせない）で、この画面と API route の
    // 両方に重複していたため `prepareSearchKeyword`（composition root）へ集約した。理由の
    // 全文は同関数の JSDoc（`src/composition/search-guard.ts`）を参照。
    // `headers()` の呼び出しでこのページは動的レンダリングになるが、既に `searchParams`
    // を使っているため元から動的である（新たな制約ではない）。
    const keyword = await prepareSearchKeyword(rawKeyword, await headers())
    const sort = trySortOrder(rawSort)

    // SP-8: ログイン中はユーザー自身のアクセストークンで叩く（レート枠の切替）。トークンの
    // 供給元が変わっても経路は `GithubRepositoryQuery`（ACL）のままなので、`is:public` 付与と
    // mapper の private 除外という公開限定の防御はそのまま効く（NFR-33 / AC-12）。
    const result = await searchRepositoriesUseCase(accessToken)({
      keyword,
      page: tryPageNumber(rawPage),
      sort,
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

  // 🔴 `idle`（キーワード未入力）はこのコンポーネントごと描画されない（呼び出し側が
  // `hasKeyword` で囲む）。到達しても表示すべき文言がないため何も出さない。
  if (state.status === 'idle') {
    return null
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
        kind={state.kind}
        presentation={toErrorPresentation(state.kind, messages, {
          locale,
          retryAfter: state.retryAfter,
          retryAfterSeconds: state.retryAfterSeconds,
          isLoggedIn,
          isAuthConfigured: showAuthLink,
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

  /*
    SP-18: 検索結果カードの Gem バッジ（`D-36` / `D-38`）。

    🔴 **並び順は一切変えない**（`D-36`: `sort=gem-index` は復活させない）。ここで引くのは
       「この `fullName` が候補プールに載っているか」だけで、`state.result.items` の順序は
       上流（GitHub Search API の関連度順・またはユーザー指定のソート）のまま `RepositoryList`
       へ渡す。
    🔴 **検索の Promise は増やさない**（上位の `runSearch()` は 1 本のまま）。結果が出て初めて
       `fullName` が分かるので、`await statePromise` の **後** にこの 1 本だけを追加で待つ。
    🔴 **二重防御**: `GemIndexPort` は契約上失敗しても空 Map を返すが、ここでも
       `.catch(() => undefined)` を張り「Gem Index の取得失敗が検索結果を巻き添えにして 500 に
       する」経路を塞ぐ（`dailyDigest` と同じ思想）。`undefined` はバッジ無しで描画される。
    0 件のときは引く対象が無いので呼ばない（無駄な cold start を避ける。エラー時・キーワード
    未入力時（`idle`）はそもそもこの行に到達しない）。
  */
  const gemIndexes =
    state.result.items.length > 0
      ? await lookupGemIndexes(state.result.items.map((item) => item.fullName)).catch(
          () => undefined,
        )
      : undefined

  /**
   * Issue #453（案3' scoped hybrid）: 実際にバッジが付いた `fullName`（= `gemIndexes` に
   * 載っているもの）を Gem 一覧へ URL で同伴させる。GitHub API の追加呼び出しはしない。
   * 🔴 `gemIndexes` が `undefined`（取得失敗）なら同伴しない（空配列を渡すと `badged` 自体が
   * 付かない・`buildGemListUrl` の契約）。AND 不一致かどうかの判定はここでは行わず、渡した名前の
   * うち実際に不足していた分だけを足すのはユースケース（`makeSearchGems`）の責務。
   * 🔴 生成側でも `MAX_INCLUDE_FULL_NAMES` で切り詰める: 消費側（`normalizeIncludeFullNames`）が
   * 同じ上限で黙って先頭 20 件へ切り詰めるため、ここで切らないと `per_page=100` でバッジが
   * 20 件を超えたときに 21 件目以降が説明なく消える（生成側・消費側で同じ定数を共有し、
   * どちらで切っても結果が変わらないようにする）。
   */
  const badgedFullNames =
    gemIndexes !== undefined
      ? state.result.items
          .filter((item) => gemIndexes.has(item.fullName))
          .map((item) => item.fullName)
          .slice(0, MAX_INCLUDE_FULL_NAMES)
      : []

  return (
    <>
      {/*
        SP-19: 検索語を引き継いだ Gem 一覧（`/{locale}/gems`）への導線（`US-34` / `GR-4`）。
        🔴 **結果一覧より前（上部）に置く**（`user-story-map.md` §5.3 `SP-19` 操作レビュー手順 2
        「検索結果の **上部** にある『この検索語の Gem 候補を一覧で見る』導線を押す」）。
        🔵 行き先の URL は既定値（1 ページ目・既定ソート・既定表示件数）で組み立てる。いまの検索の
        `page` / `sort` / `per_page` を持ち込むと、Gem 一覧が解釈しない条件が URL に載るため。
        0 件のときは引き継ぐ意味がないので出さない。

        F-2（Issue #453）: Gem 印の意味の説明（`gemBadge.intro`）を導線の直前に 1 文で出す。
        新しい見出しは作らない（`NFR-12`）。バッジが 1 件も付かなくても、検索結果が 1 件以上
        あれば出す（説明そのものはバッジの有無に依存しない）。
        🔴 **`gemIndexes` の取得自体が失敗（`undefined`）していても分岐しない**（`D-28` の縮退設計）。
        「0 件付いた」と「取得に失敗した」を画面上で区別すると、`badgedFullNames` の分岐に加えて
        この説明文にも同じ条件分岐が要り、縮退時の見た目が本 UI 全体で一貫しなくなる。取得失敗は
        バッジが 0 件のときと同じ見た目（説明文だけが出る）に倒す、という意図的な選択。
      */}
      {state.result.items.length > 0 ? (
        <>
          <p className="text-muted-foreground mt-2 text-sm">{messages.home.gemBadge.intro}</p>
          {/* 説明文と導線の間に余白を置く（4px グリッド準拠）。余白は配置の責務なので
              `GemListLink` 側には持たせない（部品の責務ではない）。 */}
          <div className="mt-2">
            <GemListLink
              href={buildGemListUrl(
                `/${locale}/gems`,
                {
                  keyword: searchState.keyword,
                  page: DEFAULT_PAGE,
                  sort: DEFAULT_SORT_ORDER,
                  perPage: DEFAULT_PER_PAGE,
                },
                badgedFullNames,
              )}
              label={messages.home.gemListLink.label}
            />
          </div>
        </>
      ) : null}
      <RepositoryList
        items={state.result.items}
        gemIndexes={gemIndexes}
        labels={{
          empty: messages.home.empty,
          starCount: messages.home.starCount,
          updatedAt: messages.home.updatedAt,
          gemBadge: messages.home.gemBadge.label,
          gemBadgeSrHint: messages.home.gemBadge.srHint,
          gemBadgeNote: messages.home.gemBadge.note,
          linkPending: messages.common.linkPending,
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
  // 🔴 **三重防御**: 候補プールの読み込みは `StaticGemDigest` 側で例外を投げない設計であり、
  //    usecase（`makeGetDailyDigest`）も例外を `null` に畳む（Issue #392）。ここでも
  //    `.catch(() => null)` を張って「ダイジェストの失敗がトップページ全体を 500 にする」
  //    経路を塞ぐ（`app/` 配下に `error.tsx` は無く、失敗すれば既存の検索機能まで巻き添えに
  //    なる）。`null` は下の既存分岐でそのまま非表示に倒れる（回帰テストは `page.test.tsx`
  //    の「日次ダイジェストの失敗がトップページを 500 にしない」）。
  const dailyDigest = hasKeyword
    ? null
    : await getDailyDigestUseCase()({ seed: dateSeed, limit: DAILY_DIGEST_LIMIT }).catch(() => null)

  const showAuthLink = isAuthConfigured()

  return (
    <>
      <SiteHeader
        locale={locale}
        currentPath={currentPath}
        title={messages.home.title}
        localeSwitcherLabels={messages.common.localeSwitcher}
        isLoggedIn={accessToken !== null}
        showAuthLink={showAuthLink}
        authLabels={showAuthLink ? messages.common.auth : undefined}
        skipLinkLabel={messages.common.skipLink}
      />
      <main id="main-content" tabIndex={-1} className="mx-auto w-full max-w-3xl px-4 py-10">
        {hasKeyword ? null : (
          // eslint-disable-next-line @next/next/no-img-element -- INF-11: next/image の最適化は使わない
          <img
            src="/images/hero-idle.webp"
            alt=""
            width={768}
            height={432}
            loading="eager"
            // Issue #355: 未検索画面の LCP 要素であることを実測済み（根拠・内訳は ADR 0015 §5）。
            fetchPriority="high"
            decoding="async"
            className="mx-auto mb-4 h-auto w-full max-w-xs"
          />
        )}
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
                lead: messages.home.digest.lead,
                empty: messages.home.digest.empty,
                dependentLabel: messages.home.digest.dependentLabel,
                starsLabel: messages.home.digest.starsLabel,
                newBadge: messages.home.digest.newBadge,
                firstVisitNote: messages.home.digest.firstVisitNote,
                linkPending: messages.common.linkPending,
              }}
            />
            <AttributionNotice
              meta={dailyDigest.meta}
              locale={locale}
              labels={{
                attribution: messages.home.digest.attribution,
                opensInNewTab: messages.common.opensInNewTab,
              }}
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
        🔴 キーワード未入力時は「検索結果」見出しと結果本体を描画しない（飼い主決定・初見
        フィードバック⑥）。以前の idle 表示（「キーワードを入力して検索してください。」）は撤去し、
        まだ検索していない状態では検索フォームと日次ダイジェストだけを見せる。

        🔴 ただし **ライブリージョン（`<section id="search-status">`）だけは条件描画にしない**
        （`ui-ux-guidelines.md` §7.2 の必須要件「ライブリージョンは初期 DOM に空で常設し、中身を
        書き換える。要素ごと動的挿入しない」）。要素ごと出し入れすると、キーワードなしの URL へ
        クライアント遷移した後に再度検索したとき `aria-live` の変更通知が発火しない実装があり、
        「読み込み中 → N 件中 M 件を表示」がスクリーンリーダーへ届かなくなる（`NFR-12` / `US-26`）。
        見出しは `<h2>` であってライブリージョンではないため、条件描画してよい。
      */}
        {hasKeyword ? (
          <h2
            id="results-heading"
            tabIndex={-1}
            className="mt-6 text-lg font-semibold outline-none focus-visible:ring-3 focus-visible:ring-ring rounded-sm"
          >
            {messages.home.resultsHeading}
          </h2>
        ) : null}

        <>
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
            {/* 未入力時は要素を残したまま中身だけ空にする（§7.2・上のコメント参照）。 */}
            {hasKeyword ? (
              <Suspense
                key={suspenseKey}
                fallback={<LoadingIndicator label={messages.common.loading} />}
              >
                <SearchStatusText statePromise={statePromise} locale={locale} messages={messages} />
              </Suspense>
            ) : null}
          </section>

          {hasKeyword ? (
            <Suspense key={suspenseKey} fallback={null}>
              <SearchBody
                statePromise={statePromise}
                basePath={basePath}
                currentPath={currentPath}
                searchState={searchState}
                locale={locale}
                messages={messages}
                isLoggedIn={accessToken !== null}
                showAuthLink={showAuthLink}
              />
            </Suspense>
          ) : null}
        </>

        {/*
        `key={suspenseKey}` の Suspense 境界の外（= remount されない位置）に置く。
        `watch={currentPath}` はページ送り・ソート・件数切替のたびに値が変わるため、
        このコンポーネント自身は remount されずに props だけが更新され、初回判定
        （`useRef`）が遷移を跨いで機能する（`focus-on-navigate.tsx` 参照）。
      */}
        {/* 🔴 未入力時は `results-heading` が存在しないため描画しない（無条件に置くと
          `getElementById` が null を返し、フォーカスが body に残ったまま無言で失敗する）。 */}
        {hasKeyword ? <FocusOnNavigate watch={currentPath} targetId="results-heading" /> : null}
      </main>
    </>
  )
}
