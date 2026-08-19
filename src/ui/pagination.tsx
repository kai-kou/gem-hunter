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
 * `maxPageFor(current.perPage)`（GitHub 検索 API が返せる 1,000 件と実際の表示件数から
 * 決まる上限・`page-number.ts`）を超えるページへは絶対にリンクを出さない（AC-7）。
 * あわせて `totalCount` から算出した実際の最終ページも尊重し、結果が尽きた次ページへもリンクを出さない。
 *
 * `<nav aria-label>` でラップし、現在ページはリンクにせず `aria-current="page"` を付与する
 * （ui-ux-guidelines.md §4.5）。
 */
export function Pagination({ basePath, current, totalCount, labels }: PaginationProps) {
  const totalPages = totalCount > 0 ? Math.ceil(totalCount / current.perPage) : current.page
  const maxPage = maxPageFor(current.perPage)
  const lastPage = Math.min(maxPage, totalPages)
  const hasPrev = current.page > 1
  const hasNext = current.page < lastPage
  const atApiLimit = lastPage === maxPage && current.page === maxPage

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
