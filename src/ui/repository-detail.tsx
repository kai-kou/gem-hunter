import { CalendarClock, CircleDot, Eye, GitFork, Star } from 'lucide-react'
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
  /** 最終更新の可視ラベル（Issue #334 F-3・`detail` 名前空間。`home.updatedAt` は横断参照しない）。 */
  updatedAt: string
  opensInNewTab: string
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
  // 一覧（repository-list.tsx）と同じ書式・タイムゾーンで揃える（Issue #334 F-3）。
  const dateFormat = new Intl.DateTimeFormat(localeTag, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    timeZone: 'Asia/Tokyo',
  })

  const numericStats = [
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
          {/* 🔴 h1 は共有ヘッダー（layout.tsx）のツールタイトルが持つため h2 へ降格する
              （Issue #334 F-1/F-2・whiteboard round3 lead 裁定。1 ページ 1 h1 を保つ）。 */}
          <h2 className="text-2xl font-semibold break-words">
            {/* GitHub の該当リポジトリページへの外部リンク（Issue #148）。新しいタブで開くことを
                sr-only 文言で支援技術にも伝える。🔴 sr-only は `<a>` の **内側** に置く
                （外に出すとリンク自体のアクセシブルネームに入らず、リンク一覧で読み上げたときに
                新しいタブで開くことが伝わらない・ui-ux-guidelines §7.4a）。
                noopener/noreferrer は新規タブからの window.opener 悪用・リファラー漏洩を防ぐ。 */}
            <a
              href={repository.htmlUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary rounded-sm underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring"
            >
              {repository.fullName}
              {/* 🔴 文言は括弧で始まる（`（新しいタブで開きます）` / `(opens in a new tab)`）。
                  アクセシブルネームの計算はインライン要素の境界で空白を入れないため、区切りを
                  半角スペースに頼ると「fullName新しいタブで開きます」と連結される。 */}
              <span className="sr-only">{labels.opensInNewTab}</span>
            </a>
          </h2>
          {repository.primaryLanguage ? (
            <p className="text-muted-foreground mt-1 text-sm">
              <span className="sr-only">{labels.language}: </span>
              {repository.primaryLanguage}
            </p>
          ) : null}
        </div>
      </div>

      {/* Issue #334 F-3: 一覧（repository-list.tsx）にあるのに詳細に無かった概要を補う。
          一覧と同じ作法でラベルなしの <p>（description が null の場合は出さない）。 */}
      {repository.description ? (
        <p className="text-muted-foreground mt-1 text-sm break-words">{repository.description}</p>
      ) : null}

      <dl className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {numericStats.map((stat) => (
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
        {/* 5 項目目: 最終更新（Issue #334 F-3）。他の統計と同じ「アイコン + 可視ラベル + 値」の形。 */}
        <div className="bg-muted/50 rounded-md p-3">
          <dt className="text-muted-foreground flex items-center gap-1 text-xs font-medium">
            <CalendarClock aria-hidden="true" className="size-4 shrink-0" />
            {labels.updatedAt}
          </dt>
          <dd className="text-foreground mt-1 text-lg font-semibold">
            {dateFormat.format(repository.lastPushedAt)}
          </dd>
        </div>
      </dl>
    </div>
  )
}
