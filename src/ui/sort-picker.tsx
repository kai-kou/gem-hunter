import Link from 'next/link'
import { ALLOWED_SORT_ORDERS } from '@/src/domain/model/sort-order'
import { DEFAULT_PAGE } from '@/src/domain/model/page-number'
import { buttonVariants } from './components/button'
import { buildSearchUrl, type SearchUrlState } from './url/build-search-url'

type SortPickerLabels = {
  navLabel: string
  options: Record<(typeof ALLOWED_SORT_ORDERS)[number], string>
}

type SortPickerProps = {
  basePath: string
  current: SearchUrlState
  labels: SortPickerLabels
}

/**
 * 並び順切替（SP-7 / US-9）。GET リンクの集合として実装し、クライアント JS を持たない
 * （NFR-3・`search-form.tsx` と同じ方針）。並び順を変えたら 1 ページ目へ戻す。
 *
 * 固定幅のセグメントコントロールにしない（ui-ux-guidelines.md §3・日英の文字列長差対策）。
 */
export function SortPicker({ basePath, current, labels }: SortPickerProps) {
  return (
    <nav aria-label={labels.navLabel} className="flex flex-wrap items-center gap-1">
      {ALLOWED_SORT_ORDERS.map((option) => {
        const isCurrent = option === current.sort
        const href = buildSearchUrl(basePath, {
          keyword: current.keyword,
          page: DEFAULT_PAGE,
          sort: option,
          perPage: current.perPage,
        })

        return (
          <Link
            key={option}
            href={href}
            aria-current={isCurrent ? 'true' : undefined}
            className={buttonVariants({
              variant: isCurrent ? 'secondary' : 'ghost',
              size: 'default',
              className: 'whitespace-normal',
            })}
          >
            {labels.options[option]}
          </Link>
        )
      })}
    </nav>
  )
}
