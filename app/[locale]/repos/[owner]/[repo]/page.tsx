import type { Metadata } from 'next'
import { Suspense } from 'react'
import { headers } from 'next/headers'
import { notFound } from 'next/navigation'
import { getSessionAccessToken, isAuthConfigured } from '@/src/composition/auth'
import { fetchRepositoryDetail, getRepositoryReadmeUseCase } from '@/src/composition/detail-guard'
import { DomainError, RateLimitExceededError, type ErrorKind } from '@/src/domain/errors'
import { isLocale, locale as toLocale, type Locale } from '@/src/domain/model/locale'
import { DEFAULT_PER_PAGE } from '@/src/domain/model/per-page'
import { DEFAULT_SORT_ORDER } from '@/src/domain/model/sort-order'
import { getMessages } from '@/src/shared/i18n/messages'
import { toErrorPresentation } from '@/src/ui/i18n/error-message'
import { buildSearchUrl } from '@/src/ui/url/build-search-url'
import {
  GEM_LIST_SOURCE_PARAM_KEY,
  GEM_LIST_SOURCE_PARAM_VALUE,
  parseSearchParams,
  rawKeywordOf,
  SEARCH_PARAM_KEYS,
  type RawSearchParams,
} from '@/src/ui/url/search-params'
import { toGemListPage } from '@/src/usecases/search-gems'
import { BackLink } from '@/src/ui/back-link'
import { ErrorNotice } from '@/src/ui/error-notice'
import { ReadmeSection, ReadmeStatusText } from '@/src/ui/readme-section'
import { RepositoryDetail } from '@/src/ui/repository-detail'
import { SetDocumentTitle } from '@/src/ui/set-document-title'
import { SiteHeader } from '@/src/ui/site-header'

/**
 * 独立 URL の詳細ページ（AC-4 / US-16 / US-17 / FR-5 / FR-6）。
 *
 * 動的セグメント（owner / repo）の値は Next.js により decodeURIComponent 済みで渡るため、
 * ここで追加のデコードは行わない（ドット入りリポジトリ名等もそのまま扱える）。
 *
 * `searchParams`（SP-7）: 一覧から遷移してきたときに検索条件（keyword/page/sort/perPage）が
 * `repository-list.tsx` の詳細リンクからクエリで届く。一覧へ戻るリンク（`backHref`）へそのまま
 * 乗せ直す。直接開いた場合（検索条件なし）は既定値へ倒れ `buildSearchUrl` がクエリなしの
 * `/{locale}` を返す（`BackLink` の既定と同じ挙動）。
 *
 * 🔴 **`<Suspense>` は必ず `notFound()` の後にのみ置く**（Issue #334 F-4 の README 遅延表示。
 * 取得結果が `null` のとき `notFound()` で **HTTP 404 を返す** のが `AC-5` の要件で、fallback が
 * 描画された時点でヘッダが送出済みになり 404 を返せなくなる。Next.js `file-conventions/loading.md`
 * 「Place `notFound()` before those boundaries」）。`loading.tsx` は route segment 全体を
 * Suspense 境界で包み判定前に fallback が流れるため、本ページには置かない。
 *
 * 🔴 **サーバー側の読み込み中表示が `AC-5` と両立しないのは「`notFound()` 判定が確定するまでの
 * 窓」だけ**（確定後は上記の `<Suspense>` で README スケルトンを本ページ内に描画している）。
 * その窓ぶんの読み込み中表示（`US-22` の詳細取得分）は遷移元の一覧側が担保する:
 * `LinkPendingHint`（詳細リンク内の `aria-hidden` な視覚ヒント）と、一覧ごとに 1 個だけ常設する
 * `LinkPendingAnnouncer`（支援技術向けライブリージョン）を `src/ui/` の 3 一覧に組み込んである。
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
  /**
   * SP-19: どの一覧から来たかで戻り先を変える（`user-story-map.md` §5.3 `SP-19` 操作レビュー
   * 手順 4「一覧から詳細へ入り、戻ると一覧の状態（検索語・ページ）が保たれている」）。
   *
   * 🔴 **既定の挙動は変えない**。`from` が **既知の値と完全一致** したときだけ Gem 一覧
   * （`/{locale}/gems`）へ戻す。未知の値・空・配列（同名クエリの重複指定）はすべて従来どおり
   * 検索結果一覧（`/{locale}`）へ倒す（`from` は URL 由来の外部入力なので許可リスト方式にする）。
   * 🔵 `q` / `page` の検証規則は据え置き（`parseSearchParams` / `tryPageNumber`）。ただし Gem 一覧の
   * 検索語は **生値** を使う: 一覧側の照合は `tokenizeQuery`（`D-37`）であり、検索キーワードの
   * 不変条件（修飾子の排除等）に縛られない。`parseSearchParams` の丸めを通すと、そこで弾かれる
   * 語で開いた一覧へ戻れなくなる。
   */
  const rawFrom = rawSearchParams[GEM_LIST_SOURCE_PARAM_KEY]
  const cameFromGemList = !Array.isArray(rawFrom) && rawFrom === GEM_LIST_SOURCE_PARAM_VALUE
  /**
   * 🔴 Gem 一覧の状態は **ここで 1 回だけ導出する**（`backHref` と `currentPath` で別々に
   * 組み立てない・F-06）。戻り先が生値の `q` を持つのに自分自身の URL が検証済みの
   * `searchState.keyword` を使っていたため、`?q=go NOT rust` のように `trySearchKeyword` が
   * 弾く検索語だと、言語切替・再試行を 1 回踏んだ瞬間に `q` が消え、「Gem 一覧へ戻る」が
   * `/{locale}/gems`（検索語なし＝`gems.queryRequired` の画面）へ落ちて一覧へ戻れなくなっていた。
   * 🔵 ページ番号も `searchState.page`（GitHub 検索 API 由来の 50 ページ上限つき）ではなく
   * Gem 一覧と同じ解釈（上限なし・`toGemListPage`）を使う。1,000 件を超える検索語では
   * 51 ページ目以降から入った詳細ページの戻り先が 1 ページ目に化けるため（F-02 と同根）。
   */
  const gemListState = {
    keyword: rawKeywordOf(rawSearchParams),
    page: toGemListPage(rawSearchParams[SEARCH_PARAM_KEYS.page]),
    sort: DEFAULT_SORT_ORDER,
    perPage: DEFAULT_PER_PAGE,
  }
  const backHref = cameFromGemList
    ? buildSearchUrl(`/${locale}/gems`, gemListState)
    : buildSearchUrl(`/${locale}`, searchState)
  /** 戻り先が変わるならラベルも変える（「一覧へ戻る」だけではどちらの一覧か分からない）。 */
  const backLinkLabel = cameFromGemList ? messages.detail.backToGemList : messages.detail.backLink
  /**
   * 自分自身の URL（再試行・言語切替の行き先）。
   *
   * 🔴 検索条件（`page` / `sort` / `per_page`）を **落とさない**（落とすと再試行後の
   * 「一覧へ戻る」が 1 ページ目・既定ソートに戻り `SP-7` の成果を壊す）。
   * 🔴 `owner` / `repo` は Next.js が decodeURIComponent 済みで渡すため、URL へ戻すときは
   * 必ず再エンコードする（`..` や `/` を含む値を踏ませたときに行き先がずれるのを防ぐ）。
   * 🔴 SP-19: 出所マーカー（`from=gems`）も落とさない。落とすと言語切替・再試行を挟んだ瞬間に
   * 「Gem 一覧へ戻る」が検索結果一覧へすり替わる（上と同じ理由）。値は本ファイルが import した
   * 定数そのもので、外部入力をそのまま連結しない。`?` / `&` の手組みはせず `buildSearchUrl` の
   * 追加パラメータ引数へ寄せる（区切り文字の分岐を各所に増やさない）。
   * 🔴 Gem 一覧から来たときの検索語・ページは `gemListState`（上で 1 回だけ導出）を使う。
   * `backHref` と別々に組み立てると導出がズレる（F-06）。
   */
  const detailPath = `/${locale}/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}`
  const currentPath = cameFromGemList
    ? buildSearchUrl(detailPath, gemListState, {
        [GEM_LIST_SOURCE_PARAM_KEY]: GEM_LIST_SOURCE_PARAM_VALUE,
      })
    : buildSearchUrl(detailPath, searchState)

  const accessToken = await getSessionAccessToken()
  const showAuthLink = isAuthConfigured()
  /**
   * 一覧・詳細・404 共通のヘッダー（`src/ui/site-header.tsx`・Issue #347）。
   * 成功パス・エラー分岐の 2 つの `return` から参照するため、ここで 1 回だけ組み立てる
   * （重複コード最小化・whiteboard round3 frontend_arch 決定）。
   */
  const header = (
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

  let repository
  try {
    repository = await fetchRepositoryDetail(accessToken, await headers(), { owner, repo }) // 間引き込み・Issue #190
  } catch (error) {
    if (error instanceof DomainError) {
      // 🔴 `error.message`（開発者向けの内部文言）は画面へ出さず、種別から文言を組み立てる
      //    （NFR-9 / prd.md §7 / Issue #107）。
      const kind: ErrorKind = error.kind
      const rateLimit = error instanceof RateLimitExceededError ? error : undefined
      return (
        <>
          {header}
          <main id="main-content" tabIndex={-1} className="mx-auto w-full max-w-3xl px-4 py-10">
            {/*
              🔴 エラー時も見出しを失わない（`NFR-12` / `US-26`）。見出しが 1 つも無い文書になると
              スクリーンリーダーの見出しナビゲーションで到達できない。また `role="alert"` は
              「動的な挿入・変化」で発火する仕様のため、初期 HTML に最初から存在するこのケースでは
              読み上げられない。通常の見出し + 本文として構成し、`role="alert"` に依存せずに
              内容が伝わるようにする。見出しは対象リポジトリ名（成功パスの `RepositoryDetail` と
              同じ粒度）で、`messages/*.json` へキーを増やさずに構成できる。
              言語切替・ログイン導線は `header`（`SiteHeader`・上で共通組み立て）が担う。
            */}
            <h2 className="mb-4 text-2xl font-semibold">{`${owner}/${repo}`}</h2>
            <ErrorNotice
              kind={kind}
              presentation={toErrorPresentation(kind, messages, {
                locale,
                retryAfter: rateLimit?.retryAfter,
                retryAfterSeconds: rateLimit?.retryAfterSeconds,
                isLoggedIn: accessToken !== null,
                isAuthConfigured: showAuthLink,
              })}
              // 再試行手段（US-24）: いま失敗した詳細 URL をそのまま開き直す。
              retryHref={currentPath}
              retryLabel={messages.common.retry}
              loginHref={showAuthLink ? '/api/auth/login' : undefined}
              loginLabel={showAuthLink ? messages.common.auth.login : undefined}
            />
            {/* 失敗しても行き止まりにしない（一覧へ戻れる・not-found.tsx と同じ導線）。 */}
            <div className="mt-6">
              <BackLink locale={locale} labels={{ backLink: backLinkLabel }} href={backHref} />
            </div>
          </main>
        </>
      )
    }
    throw error
  }

  if (repository === null) {
    notFound()
  }

  /**
   * Issue #334 F-4: README は `notFound()` 確定後に Promise を **作るだけ**（await しない）。
   * `findDetail` の await 完了後に作ることで、README 側の `findReadme` usecase が内部で経由する
   * `findDetail` がキャッシュ HIT する（GitHub への往復は最大 2 回・whiteboard round3 lead 裁定）。
   * README の遅延・失敗を統計表示のブロッキングパスに乗せないため、下の `<Suspense>` へ渡す。
   * どちらの await より前に reject しても unhandled rejection にしないよう no-op を張る
   * （トップページの `statePromise` と同じ作法）。
   */
  const readmePromise = getRepositoryReadmeUseCase(accessToken)({ owner, repo })
  void readmePromise.catch(() => undefined)

  return (
    <>
      {header}
      <main id="main-content" tabIndex={-1} className="mx-auto w-full max-w-3xl px-4 py-10">
        {/* `generateMetadata`（下記）は URL セグメントから SSR 時点の <title> を出すが、
            ハイドレーション後に document.title が親レイアウトの既定値へ巻き戻らないことまでは
            保証しないため、クライアント側でも確実に設定する（not-found.tsx / PR #127 と同じパターン）。
            fullName は API 由来の正規表記（owner の大文字小文字を含む）で generateMetadata より正確。 */}
        <SetDocumentTitle title={repository.fullName} />
        <RepositoryDetail
          repository={repository}
          labels={{
            backLink: backLinkLabel,
            language: messages.detail.language,
            starCount: messages.detail.starCount,
            watcherCount: messages.detail.watcherCount,
            forkCount: messages.detail.forkCount,
            openIssueCount: messages.detail.openIssueCount,
            updatedAt: messages.detail.updatedAt,
            opensInNewTab: messages.detail.opensInNewTab,
          }}
          locale={locale}
          backHref={backHref}
        />

        {/*
          Issue #334 F-4: README（`ui-ux-guidelines.md` §7.2 と同型のライブリージョン）。
          🔴 `<Suspense>` は必ず `notFound()` の後にのみ置く（`AC-5` の同期 404 判定を壊さない）。
          `<Suspense>` の fallback だけでは後追い挿入が支援技術へ伝わらないため、
          `role="status" aria-live="polite"` の sr-only 常設要素（内側に `<Suspense>`）で
          通知と視覚表示を分離する
          （README 到着時にフォーカスは移動しない・ユーザー操作起因でない後追い描画のため）。
        */}
        <section id="readme-status" role="status" aria-live="polite" className="sr-only">
          {/*
            🔴 ライブリージョンは **要素として常設** し、`<Suspense>` は **その内側** に置く
            （`ui-ux-guidelines.md` §7.2「初期 DOM に常設し中身を書き換える。要素ごと動的挿入しない」）。
            fallback（読み込み中）→ `ReadmeStatusText`（完了 / 取得できず）と同じリージョンの中身が
            入れ替わることで遷移が支援技術へ通知される。トップページの `#search-status` と同型。
          */}
          <Suspense fallback={messages.detail.readme.loading}>
            <ReadmeStatusText
              readmePromise={readmePromise}
              labels={{
                loaded: messages.detail.readme.loaded,
                unavailable: messages.detail.readme.unavailable,
              }}
            />
          </Suspense>
        </section>
        <Suspense
          fallback={
            <div aria-hidden="true" className="mt-8 animate-pulse space-y-2">
              <div className="bg-muted h-5 w-24 rounded" />
              <div className="bg-muted h-4 w-full rounded" />
              <div className="bg-muted h-4 w-full rounded" />
              <div className="bg-muted h-4 w-2/3 rounded" />
            </div>
          }
        >
          <ReadmeSection
            readmePromise={readmePromise}
            htmlUrl={repository.htmlUrl}
            labels={{
              heading: messages.detail.readme.heading,
              unavailable: messages.detail.readme.unavailable,
              viewOnGithub: messages.detail.readme.viewOnGithub,
              opensInNewTab: messages.detail.opensInNewTab,
            }}
          />
        </Suspense>
      </main>
    </>
  )
}

/**
 * ルート変更時のフォーカス移動・ライブリージョンとは別軸の対応（ui-ux-guidelines.md §7.1）:
 * Next.js の route announcer は `document.title` の変化のみを見て発火するため、一覧→詳細の
 * クライアント遷移でも SSR 段階から正しいタイトルを出す（E-15）。
 *
 * 🔴 `fetchRepositoryDetail` を呼び直してリポジトリ本体を再取得しない: `generateMetadata` は
 * ページ本体のレンダリングとは独立して評価されうるため、ここで同じ取得を呼ぶと間引き判定
 * （`enforceDetailRateLimit`）とキャッシュ往復が余分に増える。`fullName` は通常 `owner/repo` と
 * 一致する（大文字小文字の正規化差はタイトルの実用上無視できる）ため、デコード済みの URL
 * セグメントをそのままタイトルに使う。404 は `not-found.tsx` が自身の `generateMetadata` で
 * 上書きするため、ここでは意識しない。
 */
export async function generateMetadata({
  params,
}: {
  params: Promise<{ owner: string; repo: string }>
}): Promise<Metadata> {
  const { owner, repo } = await params
  return { title: `${owner}/${repo}` }
}
