import { CircleDot, Eye, GitFork, Star } from 'lucide-react'
import type { Locale } from '../domain/model/locale'
import type { RepositoryDetail as RepositoryDetailModel } from '../domain/model/repository'
import { BackLink } from './back-link'
import { toIntlLocaleTag } from './i18n/intl-locale-tag'

type RepositoryDetailLabels = {
  backLink: string
  language: string
  starCount: string
  watcherCount: string
  forkCount: string
  openIssueCount: string
}

/**
 * 詳細画面（AC-5 / prd.md §8.2）。表示だけを持つ Server Component。文言は labels props 経由（E-4）。
 * 数値の書式は `locale` props に追従する。
 *
 * 🔴 Watcher 数は `repository.watcherCount`（GitHub の `subscribers_count` 由来。`domain-model.md` §2.2）。
 * Star 数と同じ値にならないことをテストで検証している（AC-5）。
 */
export function RepositoryDetail({
  repository,
  labels,
  locale,
  backHref,
}: {
  repository: RepositoryDetailModel
  labels: RepositoryDetailLabels
  locale: Locale
  /**
   * 一覧へ戻るリンクの検索条件付き URL（SP-7）。呼び出し元（`app/[locale]/repos/[owner]/[repo]/page.tsx`）が
   * 詳細ページへ渡ってきた検索条件クエリから組み立てる。省略時は `BackLink` の既定（`/${locale}`）。
   */
  backHref?: string
}) {
  const localeTag = toIntlLocaleTag(locale)
  const numberFormat = new Intl.NumberFormat(localeTag)

  const stats = [
    { key: 'stars', label: labels.starCount, value: repository.stars, Icon: Star },
    { key: 'watchers', label: labels.watcherCount, value: repository.watcherCount, Icon: Eye },
    { key: 'forks', label: labels.forkCount, value: repository.forkCount, Icon: GitFork },
    { key: 'openIssues', label: labels.openIssueCount, value: repository.openIssueCount, Icon: CircleDot },
  ] as const

  return (
    <div>
      {/* SP-7: 検索条件を保持した戻り先（backHref）。未指定時は BackLink の既定（/{locale}）にフォールバックする */}
      <BackLink locale={locale} labels={labels} href={backHref} />

      <div className="mt-4 flex items-center gap-4">
        {/* next/image の最適化は使わない（INF-11）。GitHub のサイズパラメータをそのまま使う */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={`${repository.owner.avatarUrl}${repository.owner.avatarUrl.includes('?') ? '&' : '?'}s=128`}
          // オーナー名は fullName としてテキストで隣接表示されるため装飾扱い（ui-ux-guidelines §7.4）
          alt=""
          width={64}
          height={64}
          className="size-16 shrink-0 rounded-full"
        />
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold break-words">{repository.fullName}</h1>
          {repository.primaryLanguage ? (
            <p className="text-muted-foreground mt-1 text-sm">
              <span className="sr-only">{labels.language}: </span>
              {repository.primaryLanguage}
            </p>
          ) : null}
        </div>
      </div>

      <dl className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {stats.map((stat) => (
          <div key={stat.key} className="bg-muted/50 rounded-md p-3">
            <dt className="text-muted-foreground flex items-center gap-1 text-xs font-medium">
              <stat.Icon aria-hidden="true" className="size-4 shrink-0" />
              {stat.label}
            </dt>
            <dd className="text-foreground mt-1 text-lg font-semibold">
              {numberFormat.format(stat.value)}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  )
}
