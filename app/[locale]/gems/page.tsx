import type { Metadata } from 'next'
import { notFound } from 'next/navigation'
import { getSessionAccessToken, isAuthConfigured } from '@/src/composition/auth'
import { searchGemsUseCase } from '@/src/composition/container'
import { isLocale, locale as toLocale, tryLocale, type Locale } from '@/src/domain/model/locale'
import { DEFAULT_PAGE } from '@/src/domain/model/page-number'
import { DEFAULT_PER_PAGE } from '@/src/domain/model/per-page'
import { DEFAULT_SORT_ORDER } from '@/src/domain/model/sort-order'
import { getMessages } from '@/src/shared/i18n/messages'
import { BackLink } from '@/src/ui/back-link'
import { GemList } from '@/src/ui/gem-list'
import { Pagination } from '@/src/ui/pagination'
import { SiteHeader } from '@/src/ui/site-header'
import { buildSearchUrl, type SearchUrlState } from '@/src/ui/url/build-search-url'
import { parseSearchParams, rawKeywordOf, type RawSearchParams } from '@/src/ui/url/search-params'

/**
 * 検索語を引き継いだ Gem 一覧（`SP-19` / `US-34` / `GR-4` / `D-37`）。
 *
 * 検索結果（GitHub Search API の動的な結果）と違い、ここに出るのは **候補プールに載っている
 * ものだけ** なので、一覧の中では全件が Gem であり `gemIndex` による並べ替えが意味を持つ
 * （`D-36`: 検索結果側の並び順は変えない、という決定と対になる面）。
 *
 * URL 契約:
 * - `?q=` 検索語（必須相当。未指定・空白のみなら `gems.queryRequired` を出して検索へ戻す）
 * - `?page=` 1 始まりのページ番号（省略時 1・不正値は既定へ倒す）
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
  const { page } = parseSearchParams(rawSearchParams)

  const basePath = `/${locale}/gems`
  /**
   * ページネーション・言語切替・詳細からの復帰で使う URL 状態。`sort` / `perPage` は既定値の
   * ままなので `buildSearchUrl` が省略し、URL には `q` と `page` だけが載る（`SP-7` と同じ規約を
   * 再利用し、Gem 一覧専用の URL 組み立てを新設しない）。
   */
  const urlState: SearchUrlState = {
    keyword: rawQuery,
    page,
    sort: DEFAULT_SORT_ORDER,
    perPage: DEFAULT_PER_PAGE,
  }
  const currentPath = buildSearchUrl(basePath, urlState)
  /** 検索へ戻る導線（`gems.backToSearch`）。検索語は引き継ぎ、ページは 1 に戻す。 */
  const backToSearchHref = buildSearchUrl(`/${locale}`, {
    keyword: rawQuery,
    page: DEFAULT_PAGE,
    sort: DEFAULT_SORT_ORDER,
    perPage: DEFAULT_PER_PAGE,
  })

  const accessToken = await getSessionAccessToken()
  const showAuthLink = isAuthConfigured()
  const header = (
    <SiteHeader
      locale={locale}
      currentPath={currentPath}
      title={messages.home.title}
      localeSwitcherLabels={messages.common.localeSwitcher}
      isLoggedIn={accessToken !== null}
      showAuthLink={showAuthLink}
      authLabels={showAuthLink ? messages.common.auth : undefined}
    />
  )

  // 検索語なしで直接開かれた場合（`AC-2` と同じ思想: 未入力はエラーではない）。
  // 500 にも 404 にもせず、何が足りないかと戻り先を示す。
  if (rawQuery.trim().length === 0) {
    return (
      <>
        {header}
        <main className="mx-auto w-full max-w-3xl px-4 py-10">
          <p className="text-muted-foreground text-sm">{messages.gems.queryRequired}</p>
          <div className="mt-6">
            <BackLink
              locale={locale}
              labels={{ backLink: messages.gems.backToSearch }}
              href={backToSearchHref}
            />
          </div>
        </main>
      </>
    )
  }

  /**
   * 🔴 **二重防御**: `GemIndexPort#search` は契約上失敗しても例外を投げず空の結果を返すが、
   * ここでも `.catch(() => null)` を張り「候補プールの取得失敗がページ全体を 500 にする」経路を
   * 塞ぐ（`app/` 配下に `error.tsx` は無い・トップページの `dailyDigest` と同じ思想）。
   * `null` は下で「絞り込み結果なし」と同じ空表示に倒れる（出典メタデータを取れないため
   * `GemList` は描画せず、文言だけを出す）。
   */
  const result = await searchGemsUseCase()({
    query: rawQuery,
    page,
    perPage: DEFAULT_PER_PAGE,
  }).catch(() => null)

  return (
    <>
      {header}
      <main className="mx-auto w-full max-w-3xl px-4 py-10">
        {result === null ? (
          <p role="status" className="text-muted-foreground text-sm">
            {messages.gems.empty}
          </p>
        ) : (
          <GemList
            result={result}
            query={rawQuery}
            locale={locale}
            // 詳細へ入って戻ったときに同じページへ帰れるよう、現在のページを渡す（操作レビュー手順 4）。
            page={page}
            labels={{
              heading: messages.gems.heading,
              empty: messages.gems.empty,
              relaxedNotice: messages.gems.relaxedNotice,
              totalCount: messages.gems.totalCount,
              starCount: messages.gems.starCount,
              dependentCount: messages.gems.dependentCount,
              gemIndexLabel: messages.gems.gemIndexLabel,
              registryLabel: messages.gems.registryLabel,
              attribution: messages.gems.attribution,
            }}
          />
        )}

        {/*
          ページネーションは検索一覧と同じ `src/ui/pagination.tsx` を再利用する（Gem 一覧専用の
          コンポーネントを先回りで作らない・YAGNI）。ラベルも `home.pagination*` を共用する
          （「前のページへ / 次のページへ / N ページ目」は面に依らない汎用文言）。
          🔵 `limitReached`（GitHub 検索 API の 1,000 件上限の注記）は `page === maxPageFor(perPage)`
          に到達したときだけ出る。候補プールの実測最大ヒット数は 1,000 件未満なので実際には
          到達しないが、URL 直打ちで踏んだ場合に「これ以上進めない」ことが伝わる方が無害。
        */}
        {result !== null && result.items.length > 0 ? (
          <Pagination
            basePath={basePath}
            current={urlState}
            totalCount={result.totalCount}
            labels={{
              navLabel: messages.home.paginationLabel,
              prev: messages.home.pagePrev,
              next: messages.home.pageNext,
              current: messages.home.pageCurrent,
              limitReached: messages.home.pageLimitReached,
            }}
          />
        ) : null}

        <div className="mt-6">
          <BackLink
            locale={locale}
            labels={{ backLink: messages.gems.backToSearch }}
            href={backToSearchHref}
          />
        </div>
      </main>
    </>
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
