import Link from 'next/link'
import { maxPageFor } from '@/src/domain/model/page-number'
import { formatMessage } from '@/src/shared/i18n/format-message'
import { buttonVariants } from './components/button'
import { buildSearchUrl, type SearchUrlState } from './url/build-search-url'

type PaginationLabels = {
  navLabel: string
  prev: string
  next: string
  /** `{page}` プレースホルダーを含む文言（例: `{page} ページ目`）。 */
  current: string
  limitReached: string
}

type PaginationProps = {
  basePath: string
  current: SearchUrlState
  totalCount: number
  labels: PaginationLabels
  /**
   * ページ番号の上限。省略時は `maxPageFor(current.perPage)`（GitHub 検索 API の 1,000 件上限）。
   *
   * 🔴 GitHub 検索 API を経由しない面（Gem 一覧は静的な候補プールが母集団）はこの上限に
   * 縛られないため、`Math.ceil(totalCount / perPage)` のような**その面の実際の最終ページ**を
   * 渡す。渡した場合は「API 上限に達した」注記（`limitReached`）を出さない — その面に
   * API 上限は存在せず、出せば嘘の理由を伝えることになる。
   */
  maxPage?: number
  /**
   * ページ送りリンクへ引き継ぐ付帯パラメータ（例: Gem 一覧の `badged`・Issue #453）。
   *
   * 🔴 **`SearchUrlState` には混ぜない**: `Pagination` は検索一覧・Gem 一覧の両方から使う汎用
   * コンポーネントで、`badged` は Gem 一覧固有の概念（同伴 fullName）。専用フィールドを足すと
   * `Pagination` 自体が Gem 一覧の語彙を知ることになるため、`buildSearchUrl` が既に持つ
   * `extraParams`（検索 4 条件以外の付帯パラメータを載せる受け口・`build-search-url.ts`）を
   * そのまま右から左へ渡すだけに留める。省略時は従来どおり付帯パラメータなし（既存呼び出しを壊さない）。
   */
  extraParams?: Readonly<Record<string, string>>
}

const linkClassName = buttonVariants({ variant: 'ghost', size: 'default' })
const disabledClassName = buttonVariants({
  variant: 'ghost',
  size: 'default',
  className: 'pointer-events-none text-muted-foreground/50',
})

/**
 * ページネーション（SP-7 / AC-7）。前後ページへの GET リンク + 現在ページ表示。
 *
 * 既定では `maxPageFor(current.perPage)`（GitHub 検索 API が返せる 1,000 件と実際の表示件数から
 * 決まる上限・`page-number.ts`）を超えるページへは絶対にリンクを出さない（AC-7）。
 * API を経由しない面は `maxPage` で上限を上書きする。
 * あわせて `totalCount` から算出した実際の最終ページも尊重し、結果が尽きた次ページへもリンクを出さない。
 *
 * `<nav aria-label>` でラップし、現在ページはリンクにせず `aria-current="page"` を付与する
 * （ui-ux-guidelines.md §4.5）。
 */
export function Pagination({
  basePath,
  current,
  totalCount,
  labels,
  maxPage: maxPageOverride,
  extraParams = {},
}: PaginationProps) {
  const totalPages = totalCount > 0 ? Math.ceil(totalCount / current.perPage) : current.page
  const maxPage = maxPageOverride ?? maxPageFor(current.perPage)
  const lastPage = Math.min(maxPage, totalPages)
  const hasPrev = current.page > 1
  const hasNext = current.page < lastPage
  // 上限を明示的に渡された面には GitHub 検索 API の 1,000 件上限が存在しない（上記 JSDoc）。
  const atApiLimit =
    maxPageOverride === undefined && lastPage === maxPage && current.page === maxPage

  return (
    <nav
      aria-label={labels.navLabel}
      className="mt-4 flex flex-wrap items-center justify-center gap-3"
    >
      {hasPrev ? (
        <Link
          href={buildSearchUrl(basePath, { ...current, page: current.page - 1 }, extraParams)}
          className={linkClassName}
        >
          {labels.prev}
        </Link>
      ) : (
        <span aria-disabled="true" className={disabledClassName}>
          {labels.prev}
        </span>
      )}

      <span aria-current="page" className="text-sm font-medium">
        {formatMessage(labels.current, { page: String(current.page) })}
      </span>

      {hasNext ? (
        <Link
          href={buildSearchUrl(basePath, { ...current, page: current.page + 1 }, extraParams)}
          className={linkClassName}
        >
          {labels.next}
        </Link>
      ) : (
        <span aria-disabled="true" className={disabledClassName}>
          {labels.next}
        </span>
      )}

      {atApiLimit ? (
        <p role="status" className="basis-full text-center text-xs text-muted-foreground">
          {labels.limitReached}
        </p>
      ) : null}
    </nav>
  )
}
