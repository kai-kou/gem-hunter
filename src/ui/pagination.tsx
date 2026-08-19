import Link from 'next/link'
import { MAX_PAGE } from '@/src/domain/model/page-number'
import { formatMessage } from '@/src/shared/i18n/format-message'
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
}

const linkClassName =
  'rounded-md px-2.5 py-1 text-sm text-muted-foreground underline-offset-4 outline-none hover:bg-muted hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50'
const disabledClassName = 'rounded-md px-2.5 py-1 text-sm text-muted-foreground/50'

/**
 * ページネーション（SP-7 / AC-7）。前後ページへの GET リンク + 現在ページ表示。
 *
 * `PageNumber.MAX_PAGE`（GitHub 検索 API が返せる 1,000 件からの上限・`page-number.ts`）を
 * 超えるページへは絶対にリンクを出さない（AC-7）。あわせて `totalCount` から算出した
 * 実際の最終ページも尊重し、結果が尽きた次ページへもリンクを出さない。
 *
 * `<nav aria-label>` でラップし、現在ページはリンクにせず `aria-current="page"` を付与する
 * （ui-ux-guidelines.md §4.5）。
 */
export function Pagination({ basePath, current, totalCount, labels }: PaginationProps) {
  const totalPages = totalCount > 0 ? Math.ceil(totalCount / current.perPage) : current.page
  const lastPage = Math.min(MAX_PAGE, totalPages)
  const hasPrev = current.page > 1
  const hasNext = current.page < lastPage
  const atApiLimit = lastPage === MAX_PAGE && current.page === MAX_PAGE

  return (
    <nav aria-label={labels.navLabel} className="mt-4 flex flex-wrap items-center justify-center gap-3">
      {hasPrev ? (
        <Link
          href={buildSearchUrl(basePath, { ...current, page: current.page - 1 })}
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
          href={buildSearchUrl(basePath, { ...current, page: current.page + 1 })}
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
