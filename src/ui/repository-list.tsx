import type { RepositorySummary } from '../domain/model/repository'

const numberFormat = new Intl.NumberFormat('ja-JP')
const dateFormat = new Intl.DateTimeFormat('ja-JP', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  timeZone: 'Asia/Tokyo',
})

/** 検索結果の一覧（AC-3 / AR-1）。表示だけを持つ Server Component。 */
export function RepositoryList({ items }: { items: readonly RepositorySummary[] }) {
  if (items.length === 0) {
    return (
      <p className="text-muted-foreground py-8 text-sm">
        条件に合うリポジトリは見つかりませんでした。キーワードを変えて試してください。
      </p>
    )
  }

  return (
    <ul className="divide-border divide-y">
      {items.map((item) => (
        <li key={item.id} className="flex gap-3 py-4">
          {/* next/image の最適化は使わない（INF-11）。GitHub のサイズパラメータをそのまま使う */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={`${item.owner.avatarUrl}${item.owner.avatarUrl.includes('?') ? '&' : '?'}s=80`}
            alt={item.owner.login}
            width={40}
            height={40}
            className="size-10 shrink-0 rounded-full"
            loading="lazy"
          />
          <div className="min-w-0 flex-1">
            <a
              href={item.htmlUrl}
              className="text-primary font-medium underline-offset-4 hover:underline"
              rel="noreferrer noopener"
              target="_blank"
            >
              {item.fullName}
            </a>
            {item.description ? (
              <p className="text-muted-foreground mt-1 text-sm">{item.description}</p>
            ) : null}
            <p className="text-muted-foreground mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs">
              {item.primaryLanguage ? <span>{item.primaryLanguage}</span> : null}
              <span>
                <span aria-hidden="true">★ </span>
                <span className="sr-only">star 数 </span>
                {numberFormat.format(item.stars)}
              </span>
              <span>最終更新 {dateFormat.format(item.updatedAt)}</span>
            </p>
            {item.topics.length > 0 ? (
              <ul className="mt-2 flex flex-wrap gap-1">
                {item.topics.slice(0, 5).map((topic) => (
                  <li
                    key={topic}
                    className="bg-muted text-muted-foreground rounded-full px-2 py-0.5 text-xs"
                  >
                    {topic}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        </li>
      ))}
    </ul>
  )
}
