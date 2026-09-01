import type { ComponentProps, ReactNode } from 'react'
import type { Metadata } from 'next'
import { headers } from 'next/headers'
import { notFound } from 'next/navigation'
import { getSessionAccessToken, isAuthConfigured } from '@/src/composition/auth'
import { searchGemsUseCase } from '@/src/composition/container'
import { enforceGemListRateLimit } from '@/src/composition/rate-limit'
import { RateLimitExceededError } from '@/src/domain/errors'
import { isLocale, locale as toLocale, tryLocale, type Locale } from '@/src/domain/model/locale'
import { DEFAULT_PAGE } from '@/src/domain/model/page-number'
import { DEFAULT_PER_PAGE } from '@/src/domain/model/per-page'
import { DEFAULT_SORT_ORDER } from '@/src/domain/model/sort-order'
import { getMessages } from '@/src/shared/i18n/messages'
import { normalizeIncludeFullNames, toGemListPage } from '@/src/usecases/search-gems'
import { BackLink } from '@/src/ui/back-link'
import { ErrorNotice } from '@/src/ui/error-notice'
import { FocusOnNavigate } from '@/src/ui/focus-on-navigate'
import { GemList, GEM_LIST_HEADING_ID, type GemListViewModel } from '@/src/ui/gem-list'
import { toErrorPresentation } from '@/src/ui/i18n/error-message'
import { Pagination } from '@/src/ui/pagination'
import { SiteHeader } from '@/src/ui/site-header'
import { buildSearchUrl, type SearchUrlState } from '@/src/ui/url/build-search-url'
import { rawBadgedOf } from '@/src/ui/url/gem-list-url'
import { rawKeywordOf, SEARCH_PARAM_KEYS, type RawSearchParams } from '@/src/ui/url/search-params'

/**
 * フォーカス受け口（`GEM_LIST_HEADING_ID` を持つ `h2`）の意匠。
 *
 * 🔴 **`GemList` の見出し（`src/ui/gem-list.tsx`）と同じ見た目・同じ挙動にする**。この面では
 * 一覧・0 件・照合不能を `GemList` の `h2` が、それ以外の分岐（検索語なし・レート制限・取得失敗）を
 * 本ファイルの `h2` が出すが、**利用者から見れば同じ 1 つの受け口** なので、意匠がずれると
 * 「同じページの同じ見出しなのに分岐でフォーカスリングが変わる」ことになる。
 */
const HEADING_CLASS =
  'rounded-sm text-lg font-semibold outline-none focus-visible:ring-3 focus-visible:ring-ring'

/**
 * 検索語を引き継いだ Gem 一覧（`SP-19` / `US-34` / `GR-4` / `D-37`）。
 *
 * 検索結果（GitHub Search API の動的な結果）と違い、ここに出るのは **候補プールに載っている
 * ものだけ** なので、一覧の中では全件が Gem であり `gemIndex` による並べ替えが意味を持つ
 * （`D-36`: 検索結果側の並び順は変えない、という決定と対になる面）。
 *
 * URL 契約:
 * - `?q=` 検索語（必須相当。未指定・空白のみなら `gems.queryRequired` を出して検索へ戻す）
 * - `?page=` 1 始まりのページ番号（省略時 1・不正値は既定へ倒す）。🔴 **GitHub 検索 API の
 *   上限（50 ページ）は適用しない**（候補プールは 1 語で 8,913 件に達する・F-02）。範囲外の
 *   ページは実装側が最終ページへ丸め、実際に返したページが `effectivePage` で返る
 *
 * 🔴 **表示件数は固定（`DEFAULT_PER_PAGE`）**。`SP-19` に表示件数切替の要件は無く、
 * `per_page` を受けるとページ URL の組み合わせだけが増える。必要になった時点で
 * 検索一覧（`app/[locale]/page.tsx`）と同じ `PerPagePicker` を足す（YAGNI）。
 *
 * 🔵 `params` / `searchParams` はどちらも `Promise`（Next.js 16 の規約）。既存の
 * `app/[locale]/page.tsx` / `app/[locale]/repos/[owner]/[repo]/page.tsx` と同じ流儀に揃える。
 */
export default async function GemListPage({
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
  /**
   * 🔴 絞り込みには **キーワードの生値** を使う（`parseSearchParams` は検索キーワードの
   * 不変条件（修飾子の排除等）を満たさない値を `''` へ倒すため、そのまま渡すと拒否理由が
   * 「未入力」にすり替わる）。Gem 一覧の照合は `tokenizeQuery`（`D-37`）が行い、
   * 記号・非 ASCII は区切りとして落ちるので、生値をそのまま渡して安全。
   */
  const rawQuery = rawKeywordOf(rawSearchParams)
  /**
   * 🔴 検索結果でバッジが付いたが AND 不一致で漏れていた `fullName` の同伴（`badged`・Issue #453
   * 案3'）。正規化・上限件数・不正形式のスキップはユースケース（`makeSearchGems`）の責務なので、
   * ここでは URL の生値をそのまま渡す（分割・検証をしない）。
   *
   * 🔴 **ページ送り・言語切替・その他この面の自 URL では引き継ぐが、「検索に戻る」には載せない**
   * （`backToSearchHref` は検索語だけを引き継ぐ既存仕様のまま・引き継ぐと検索一覧側が知らない
   * クエリを URL に残すことになる）。引き継がないと Pagination でページ 2 を開いた瞬間に
   * 同伴分が消え、総件数が同じ URL で変わってしまう。
   */
  const rawBadged = rawBadgedOf(rawSearchParams)
  /**
   * 🔴 ページ送り・言語切替・再試行リンクへ埋め込む値は **正規化後**（`normalizeIncludeFullNames`）
   * を使う。絞り込みに使われる値（`searchGemsUseCase` へ渡す `rawBadged`）と生値のまま食い違うと、
   * 不正形式・21 件目以降・極端に長い値がそのまま URL に複製され続ける。`buildSearchUrl` は
   * 空文字の値を省略する契約なので、正規化結果が空配列（`join(',')` が `''`）なら `badged`
   * パラメータ自体が付かない。
   */
  const badgedExtraParams = { badged: normalizeIncludeFullNames(rawBadged).join(',') }
  /**
   * 🔴 ページ番号も `parseSearchParams`（`tryPageNumber`）を使わない。あちらは GitHub 検索 API の
   * 1,000 件上限から決まる 50 ページ上限を持ち、**それを超える指定を 1 ページ目へ倒す**ため、
   * 1,631 件ヒットする `?q=core&page=51` が最終ページではなく 1 ページ目を返していた（F-02）。
   */
  const requestedPage = toGemListPage(rawSearchParams[SEARCH_PARAM_KEYS.page])

  const basePath = `/${locale}/gems`
  /** 検索へ戻る導線（`gems.backToSearch`）。検索語は引き継ぎ、ページは 1 に戻す。 */
  const backToSearchHref = buildSearchUrl(`/${locale}`, {
    keyword: rawQuery,
    page: DEFAULT_PAGE,
    sort: DEFAULT_SORT_ORDER,
    perPage: DEFAULT_PER_PAGE,
  })

  const accessToken = await getSessionAccessToken()
  const showAuthLink = isAuthConfigured()
  /**
   * 共通ヘッダー。`currentPath`（言語切替の行き先）は分岐ごとに変わる（検索語なし・取得失敗・
   * 一覧表示で「現在のページ」が違う）ため、パスを受け取って組み立てる。
   */
  const renderHeader = (currentPath: string) => (
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
  )
  const backToSearch = (
    <div className="mt-6">
      <BackLink
        locale={locale}
        labels={{ backLink: messages.gems.backToSearch }}
        href={backToSearchHref}
      />
    </div>
  )

  /**
   * 全分岐で共通のページ骨格（ヘッダー + 本文 + フォーカス移動）。
   *
   * 🔴 **`FocusOnNavigate` はここ 1 箇所にだけ置く**（分岐ごとに置かない）。`isFirstRender`
   * （`src/ui/focus-on-navigate.tsx`）は「初回描画ではフォーカスを奪わない」ための状態を
   * `useRef` で持つため、分岐ごとに別々に置くと success ↔ error の遷移で remount されて
   * 初回判定が真に戻り、**遷移のたびにフォーカス移動がスキップされる**。骨格を 1 つに揃えて
   * `main` の同じ位置に置けば、どの分岐へ遷移しても props（`watch`）だけが更新される。
   *
   * 🔴 受け口（`GEM_LIST_HEADING_ID` の `h2`）は **全分岐に必ず存在する**: 一覧・0 件・照合不能は
   * `GemList` が、それ以外は本ファイルの `h2` が出す。どの分岐にも無いと `getElementById` が
   * `null` を返してフォーカスが `body` に残り、無言で失敗する（`app/[locale]/page.tsx` の
   * 未入力時と同じ落とし穴）。
   *
   * 🔴 **なぜフォーカス移動が要るのか**（`ui-ux-guidelines.md` §7.1 の必須要件・F-04）:
   * `<title>` は固定なので route announcer は無言、総件数の `role="status"` もページ間で同一
   * 文字列（「1,631 件」）のため変更通知が発火しない。さらにページ送りリンク（`Pagination`）は
   * エラー分岐へ倒れた瞬間に DOM ごと消えるため、押したリンクにフォーカスが留まることすらなく
   * `document.body` へ落ちる。つまりフォーカス移動だけが「画面が変わった・再試行導線がある」を
   * 支援技術へ伝える唯一の手段になる（`NFR-12` / `AC-8`）。検索一覧（`app/[locale]/page.tsx`）と
   * 同じ `FocusOnNavigate` + `tabIndex={-1}` の見出しで揃える。
   */
  const renderPage = (currentPath: string, body: ReactNode) => (
    <>
      {renderHeader(currentPath)}
      <main id="main-content" tabIndex={-1} className="mx-auto w-full max-w-3xl px-4 py-10">
        {body}
        {/* `watch` はページ送り・分岐の切り替わりのたびに値が変わる（`currentPath`）。 */}
        <FocusOnNavigate watch={currentPath} targetId={GEM_LIST_HEADING_ID} />
      </main>
    </>
  )

  /**
   * エラー 2 分岐（レート制限・取得失敗）の共通本文。構造（見出し → `ErrorNotice` → 検索へ戻る）は
   * 同じで、変わるのは `ErrorNotice` へ渡す 3 つだけなので、分岐側には「どの状態か」を決める
   * 引数と理由コメントだけを残す。
   */
  const renderErrorBody = ({
    kind,
    presentation,
    retryHref,
  }: {
    kind: ComponentProps<typeof ErrorNotice>['kind']
    presentation: ComponentProps<typeof ErrorNotice>['presentation']
    retryHref: string
  }) => (
    <>
      {/* エラー時も見出し（＝フォーカス受け口）を失わない（`NFR-12`・上の `renderPage` 参照）。 */}
      <h2 id={GEM_LIST_HEADING_ID} tabIndex={-1} className={`mb-4 ${HEADING_CLASS}`}>
        {messages.gems.title}
      </h2>
      <ErrorNotice
        kind={kind}
        presentation={presentation}
        // 再試行手段（`US-24`）: いま失敗した一覧 URL をそのまま開き直す。
        retryHref={retryHref}
        retryLabel={messages.common.retry}
      />
      {backToSearch}
    </>
  )

  // 検索語なしで直接開かれた場合（`AC-2` と同じ思想: 未入力はエラーではない）。
  // 500 にも 404 にもせず、何が足りないかと戻り先を示す。
  if (rawQuery.trim().length === 0) {
    return renderPage(
      basePath,
      <>
        {/*
          🔴 この分岐にも見出しを置く（F-21）。他の分岐は `GemList` が `h2` を出すため、
          ここだけ本文に見出しが無いと、同じ URL でも検索語の有無で見出し構造が変わり、
          スクリーンリーダーの見出しジャンプで本文へ到達できない（`NFR-12`）。
          `h1` は共有ヘッダーが持つので増やさない。
          `id` / `tabIndex` はフォーカス受け口の要件（`renderPage` 参照）。検索語を消して
          この分岐へ遷移したときも「画面が変わった」ことが伝わる。
        */}
        <h2 id={GEM_LIST_HEADING_ID} tabIndex={-1} className={HEADING_CLASS}>
          {messages.gems.title}
        </h2>
        <p className="text-muted-foreground mt-2 text-sm">{messages.gems.queryRequired}</p>
        {backToSearch}
      </>,
    )
  }

  /**
   * Issue #442: Gem 一覧の自リクエスト間引き（`NFR-7`）。
   *
   * 🔴 **位置は「検索語なしの早期 return より後・候補プールの読み込みより前」**。検索経路が
   * 「値オブジェクトへの変換が通った入力だけを対象にする」（不正入力で枠を消費しない・
   * `app/api/search/route.test.ts`）のと同じ規律で、`gems.queryRequired` に倒れる入力では
   * 枠を消費しない。逆に消費の判定は重い処理（`searchGemsUseCase()`）より前に済ませ、
   * 間引きの目的（負荷の抑制）を果たす。
   *
   * 🔵 枠は検索経路と独立（`enforceGemListRateLimit` が別キーを使う）。同じ IP からの検索と
   * 一覧閲覧が互いの枠を食い合うと、片方の操作でもう片方が使えなくなる。
   *
   * 超過時は `RateLimitExceededError` を投げるので、下の取得失敗分岐と同じ `ErrorNotice` へ倒す。
   * それ以外の例外は握り潰さずそのまま投げ直す（`headers()` 由来の障害等を隠さない）。
   */
  try {
    await enforceGemListRateLimit(await headers())
  } catch (error) {
    if (!(error instanceof RateLimitExceededError)) {
      throw error
    }
    /**
     * 🔴 再試行先は `effectivePage` ではなく `requestedPage` で組み立てる（取得自体を行って
     * いないため実際のページが分からない）。取得失敗分岐が `currentPage` のフォールバックに
     * `requestedPage` を使うのと同じ扱い。
     */
    const requestedPath = buildSearchUrl(basePath, {
      keyword: rawQuery,
      page: requestedPage,
      sort: DEFAULT_SORT_ORDER,
      perPage: DEFAULT_PER_PAGE,
    })
    return renderPage(
      requestedPath,
      renderErrorBody({
        kind: error.kind,
        // 文言・秒数のローカライズは `toErrorPresentation` に委ねる（`NFR-9`: 例外の
        // 内部文言は画面へ運ばない）。ログイン導線は二次レート制限では出ない
        // （`loginHint` が付くのは一次レート制限のみ）ため、`isAuthConfigured` の値は
        // 結果に影響しない。`renderErrorBody` が `loginHref`/`loginLabel` を渡さない
        // こととも一致させるため固定で `false` を渡す（`showAuthLink` は渡さない）。
        presentation: toErrorPresentation(error.kind, messages, {
          locale,
          retryAfterSeconds: error.retryAfterSeconds,
          isLoggedIn: accessToken !== null,
          isAuthConfigured: false,
        }),
        // 再試行先は、いま弾かれた一覧 URL そのもの（上の `requestedPath` のコメント参照）。
        retryHref: requestedPath,
      }),
    )
  }

  const result = await searchGemsUseCase()({
    query: rawQuery,
    page: requestedPage,
    perPage: DEFAULT_PER_PAGE,
    includeFullNames: rawBadged,
  })

  /**
   * 🔴 URL の `page` と **実際に返ったページ** はズレうる（範囲外の指定は実装側が最終ページへ
   * 丸める）。ページネーション・言語切替・再試行の行き先には `effectivePage` を使い、
   * 画面が「いま出ているページ」と一致した状態を指すようにする。
   */
  const currentPage = result.status === 'ok' ? result.effectivePage : requestedPage
  /**
   * ページネーション・言語切替・詳細からの復帰で使う URL 状態。`sort` / `perPage` は既定値の
   * ままなので `buildSearchUrl` が省略し、URL には `q` と `page` だけが載る（`SP-7` と同じ規約を
   * 再利用し、Gem 一覧専用の URL 組み立てを新設しない）。
   */
  const urlState: SearchUrlState = {
    keyword: rawQuery,
    page: currentPage,
    sort: DEFAULT_SORT_ORDER,
    perPage: DEFAULT_PER_PAGE,
  }
  // 🔴 `badged` を引き継ぐ（言語切替・再試行・ページ送りの行き先すべてに使う自ページ URL）。
  //    「検索に戻る」（`backToSearchHref`）は上で別途組み立てており、ここへは影響しない。
  const currentPath = buildSearchUrl(basePath, urlState, badgedExtraParams)

  /**
   * 🔴 **取得失敗は 0 件と別の状態として出す**（F-05 / `ui-ux-guidelines.md` §4.4・§5.2）。
   * 候補プールを読めていないのに「この検索語に一致する Gem 候補はありませんでした」と出すと、
   * 一時障害を「自分のキーワードには Gem が無い」と誤認させ、しかも再試行導線が無い。
   * 🔵 `role="alert"`（`ErrorNotice`）と `role="status"`（`GemList` の 0 件・件数表示）は
   * 同時に描画しない（この分岐は `GemList` を出さない）。
   */
  if (result.status === 'failed') {
    return renderPage(
      currentPath,
      renderErrorBody({
        // 🔴 文言は `gems.loadFailed`。`common.errors.upstream`（「GitHub 側で問題が
        // 起きています」）は流用しない — 障害元は GitHub ではなく自前の静的アセット
        // （`public/data/gem-index/`）で、利用者に誤った原因を伝えることになる。
        // `kind` は装飾イラストの出し分けにのみ使われるので `upstream` のままでよい。
        kind: 'upstream',
        presentation: { message: messages.gems.loadFailed },
        // 再試行先は、いま失敗した一覧 URL そのもの。
        retryHref: currentPath,
      }),
    )
  }

  const view: GemListViewModel = {
    items: result.items,
    totalCount: result.totalCount,
    effectivePage: result.effectivePage,
    // 緩和していなければ `null`（`GemList` は注記を出さない）。
    relaxedToken: result.relaxed ? (result.usedTokens[0] ?? null) : null,
    /**
     * 🔴 0 件の理由が「照合不能」（検索語は空でないのに、照合に使える英数字の語を 1 つも
     * 取り出せなかった）かどうか。判定は `searchGems` ユースケースが持ち、ここは受け取って
     * 渡すだけ（`GemList` が空状態の文言を切り替える）。
     */
    unmatchableQuery: result.unmatchableQuery,
    meta: result.meta,
  }

  return renderPage(
    currentPath,
    <>
      {/*
        この分岐の見出し（＝フォーカス受け口・`GEM_LIST_HEADING_ID`）は `GemList` が出す。
        一覧・0 件・照合不能のいずれの状態でも描画されるため、受け口が欠ける状態は無い。
      */}
      <GemList
        view={view}
        query={rawQuery}
        locale={locale}
        labels={{
          heading: messages.gems.heading,
          empty: messages.gems.empty,
          unmatchableQuery: messages.gems.unmatchableQuery,
          relaxedNotice: messages.gems.relaxedNotice,
          totalCount: messages.gems.totalCount,
          starCount: messages.gems.starCount,
          dependentCount: messages.gems.dependentCount,
          gemIndexLabel: messages.gems.gemIndexLabel,
          registryLabel: messages.gems.registryLabel,
          attribution: messages.gems.attribution,
          opensInNewTab: messages.common.opensInNewTab,
        }}
      />

      {/*
        ページネーションは検索一覧と同じ `src/ui/pagination.tsx` を再利用する（Gem 一覧専用の
        コンポーネントを先回りで作らない・YAGNI）。ラベルも `home.pagination*` を共用する
        （「前のページへ / 次のページへ / N ページ目」は面に依らない汎用文言）。

        🔴 **描画条件は `totalCount > 0`**（`items.length > 0` ではない・F-03）。範囲外ページの
        クランプで手前のページへ戻れなくなる状況を作らない。
        🔴 **`maxPage` は候補プールの実際の最終ページ**（`Math.ceil(totalCount / perPage)`）。
        既定の `maxPageFor(perPage)` は GitHub 検索 API の 1,000 件上限（＝50 ページ）由来で、
        候補プールには存在しない制約である: 実データには 1 語で 1,000 件を超えるトークンが 10 個
        あり（`com` 8,913 / `github` 8,156 / `core` 1,631 ほか）、50 ページで打ち切ると
        `q=core` の 631 件が閲覧不能になる（F-02）。`maxPage` を明示すると API 上限の注記
        （`limitReached`）は描画されない（この面に API 上限は無いため）。
      */}
      {result.totalCount > 0 ? (
        <Pagination
          basePath={basePath}
          current={urlState}
          totalCount={result.totalCount}
          maxPage={Math.ceil(result.totalCount / DEFAULT_PER_PAGE)}
          extraParams={badgedExtraParams}
          labels={{
            navLabel: messages.home.paginationLabel,
            prev: messages.home.pagePrev,
            next: messages.home.pageNext,
            current: messages.home.pageCurrent,
            limitReached: messages.home.pageLimitReached,
          }}
        />
      ) : null}

      {backToSearch}
    </>,
  )
}

/**
 * ルート変更時の route announcer は `document.title` の変化のみを見て発火する（`E-15`）ため、
 * SSR 段階から一覧固有のタイトルを出す（詳細ページの `generateMetadata` と同じ理由）。
 * 検索語はタイトルへ入れない（利用者の入力をそのまま `<title>` へ載せない・`gems.title` は固定文言）。
 */
export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>
}): Promise<Metadata> {
  const { locale: rawLocale } = await params
  // 不正なロケールは本体側が `notFound()` を返すため、ここでは既定ロケールへ倒すだけでよい。
  const messages = getMessages(tryLocale(rawLocale))
  return { title: messages.gems.title, description: messages.gems.description }
}
