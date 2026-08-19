import Link from 'next/link'
import { ALLOWED_PER_PAGE } from '@/src/domain/model/per-page'
import { DEFAULT_PAGE } from '@/src/domain/model/page-number'
import { formatMessage } from '@/src/shared/i18n/format-message'
import { buttonVariants } from './components/button'
import { buildSearchUrl, type SearchUrlState } from './url/build-search-url'

type PerPagePickerLabels = {
  navLabel: string
  /** `{count}` プレースホルダーを含む文言（例: `{count} 件`）。 */
  optionLabel: string
}

type PerPagePickerProps = {
  basePath: string
  current: SearchUrlState
  labels: PerPagePickerLabels
}

/**
 * 表示件数切替（SP-7 / US-9 / AR-3）。GET リンクの集合として実装（NFR-3）。
 * 件数を変えたら 1 ページ目へ戻す（既存のページ位置は新しい件数と対応しなくなるため）。
 *
 * 固定幅のセグメントコントロールにしない（ui-ux-guidelines.md §3）。
 */
export function PerPagePicker({ basePath, current, labels }: PerPagePickerProps) {
  return (
    <nav aria-label={labels.navLabel} className="flex flex-wrap items-center gap-1">
      {ALLOWED_PER_PAGE.map((option) => {
        const isCurrent = option === current.perPage
        const href = buildSearchUrl(basePath, {
          keyword: current.keyword,
          page: DEFAULT_PAGE,
          sort: current.sort,
          perPage: option,
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
            {formatMessage(labels.optionLabel, { count: String(option) })}
          </Link>
        )
      })}
    </nav>
  )
}
