import Link from 'next/link'
import type { Locale } from '../domain/model/locale'
import type { RepositorySummary } from '../domain/model/repository'
import { toIntlLocaleTag } from './i18n/intl-locale-tag'
import { buildSearchUrl, type SearchUrlState } from './url/build-search-url'

type RepositoryListLabels = {
  empty: string
  starCount: string
  updatedAt: string
}

/**
 * 検索結果の一覧（AC-3 / AR-1）。表示だけを持つ Server Component。文言は labels props 経由（E-4）。
 * 数値・日付の書式は `locale` props に追従する（`en` で日本式書式にならないようにする）。
 */
export function RepositoryList({
  items,
  labels,
  locale,
  searchState,
}: {
  items: readonly RepositorySummary[]
  labels: RepositoryListLabels
  locale: Locale
  /**
   * 現在の検索条件（SP-7）。渡すと詳細ページへのリンクへクエリとして継ぎ足し、
   * 詳細 → 戻る で検索条件を保持できるようにする（`back-link.tsx` と対になる）。
   * 省略時はクエリなしのパスのまま（既存呼び出しとの後方互換）。
   */
  searchState?: SearchUrlState
}) {
  if (items.length === 0) {
    // 0 件は「視覚表現だけ」にせず role="status" で支援技術にも伝える（US-23 / US-26 / NFR-12）。
    // role="alert" は使わない（0 件は緊急の割り込みではない・ui-ux-guidelines.md §7.2）。
    //
    // 🔴 装飾画像は role="status" の要素の外（兄弟）に置く（Issue #347・a11y_i18n round3
    // 確定マークアップ）。再検索のたびに role="status" の暗黙 aria-atomic でこの要素の
    // 中身が丸ごと再構成されるため、内側に画像（有意味 alt 付き）を置くと毎回読み上げ直される
    // 恐れがある。alt="" 固定の現状は実害ゼロだが、将来の改変からこの不変条件を構造で守る。
    return (
      <div className="flex flex-col items-center gap-3 py-8 text-center">
        {/* eslint-disable-next-line @next/next/no-img-element -- INF-11: next/image 最適化は使わない */}
        <img
          src="/images/empty-result.webp"
          // 装飾。labels.empty が既に同じ意味を文章で伝えているため代替テキスト不要（1.1.1）。
          alt=""
          width={256}
          height={256}
          loading="lazy"
          decoding="async"
          className="h-auto w-24"
        />
        <p role="status" className="text-muted-foreground text-sm">
          {labels.empty}
        </p>
      </div>
    )
  }

  const localeTag = toIntlLocaleTag(locale)
  const numberFormat = new Intl.NumberFormat(localeTag)
  const dateFormat = new Intl.DateTimeFormat(localeTag, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    timeZone: 'Asia/Tokyo',
  })

  return (
    <ul className="divide-border divide-y">
      {items.map((item) => (
        <li key={item.id} className="relative flex gap-3 py-4">
          {/* next/image の最適化は使わない（INF-11）。GitHub のサイズパラメータをそのまま使う */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={`${item.owner.avatarUrl}${item.owner.avatarUrl.includes('?') ? '&' : '?'}s=80`}
            // オーナー名は owner/repo 形式でカード内にテキスト隣接表示されるため装飾扱い
            // （ui-ux-guidelines.md §7.4・詳細ページ repository-detail.tsx と同じ方針）
            alt=""
            width={40}
            height={40}
            className="size-10 shrink-0 rounded-full"
            loading="lazy"
          />
          <div className="min-w-0 flex-1">
            {/*
              独立 URL の詳細ページへの遷移（AC-4・モーダルではない）。
              カード全体をクリック可能にするが、<a> でカード全体を包むと
              説明文・メタ情報までスクリーンリーダーが読み上げてしまうため、
              見出し（リポジトリ名）だけをリンクにし ::after でクリック領域を
              カード全体へ拡張する（ui-ux-guidelines.md §4.3）。
            */}
            <Link
              href={`/${locale}/repos/${encodeURIComponent(item.owner.login)}/${encodeURIComponent(item.name)}${searchState ? buildSearchUrl('', searchState) : ''}`}
              // 🔴 ネイティブ <a> のブラウザ既定フォーカス（outline: auto）は太さが約 1px しかなく
              // `ui-ux-guidelines.md` §7.3 の「太さ 2px 相当以上」を満たさない（SP-10 実測で判明）。
              // button.tsx / input.tsx / 結果見出し（page.tsx）と同じ `ring-3` パターンへ揃える。
              className="text-primary rounded-sm font-medium underline-offset-4 outline-none after:absolute after:inset-0 hover:underline focus-visible:ring-3 focus-visible:ring-ring"
            >
              {item.fullName}
            </Link>
            {item.description ? (
              <p className="text-muted-foreground mt-1 text-sm">{item.description}</p>
            ) : null}
            <p className="text-muted-foreground mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs">
              {item.primaryLanguage ? <span>{item.primaryLanguage}</span> : null}
              <span>
                <span aria-hidden="true">★ </span>
                <span className="sr-only">{labels.starCount} </span>
                {numberFormat.format(item.stars)}
              </span>
              <span>
                {labels.updatedAt} {dateFormat.format(item.lastPushedAt)}
              </span>
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
