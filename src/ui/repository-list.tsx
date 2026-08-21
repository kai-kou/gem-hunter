import Link from 'next/link'
import { Fragment } from 'react'
import type { GemFacet } from '../domain/model/gem'
import { gemFacetKey, gemIndexValue } from '../domain/model/gem-index'
import type { Locale } from '../domain/model/locale'
import type { RepositorySummary } from '../domain/model/repository'
import { toIntlLocaleTag } from './i18n/intl-locale-tag'
import { buildSearchUrl, type SearchUrlState } from './url/build-search-url'

type RepositoryListLabels = {
  empty: string
  starCount: string
  updatedAt: string
  /** Gem Index の値ラベル（`gemFacets` 経由で表示するときのみ使う・`SP-16` / `D-L` / `D-N`）。 */
  gemIndexValueLabel?: string
  /** 被依存数のラベル（同上）。 */
  gemIndexDependentLabel?: string
  /** Gem Index を持たない結果群の直前に挿入する区切り見出し（同上・`D-M`）。 */
  gemIndexUnavailableHeading?: string
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
  gemFacets,
  unrankedContinuedFromPreviousPage,
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
  /**
   * `repositoryFullName`（小文字化キー）→ `GemFacet` の突合マップ（`SP-16`）。
   * 呼び出し側（`page.tsx`）は `sort=gem-index` のときだけ渡す。渡されたときだけ、
   * facet を持つカードへ Gem Index 値・被依存数を追記し（`D-L`）、
   * facet を持たない結果群の直前に区切り見出しを 1 本だけ挿入する（`D-M`）。
   * 並べ替え自体は usecase 側が済ませた順序をそのまま描画するだけで、
   * 本コンポーネントは再ソートしない（`items` の順序を信頼する）。
   */
  gemFacets?: ReadonlyMap<string, GemFacet>
  /**
   * 🔴 PR #293 セルフレビュー指摘・修正④（WARNING）: ranked / unranked の境界が
   * ページ境界と一致する（このページの先頭要素が unranked）と、`idx > 0` 基準の
   * `dividerIndex` では区切り見出しが 1 度も出ない。呼び出し側（`page.tsx`）が
   * 「前のページに Gem Index を持つ結果があった」ことを渡すと、先頭要素（idx===0）が
   * unranked のときも区切りを出す。省略時・`false` は従来どおり（回帰なし）。
   */
  unrankedContinuedFromPreviousPage?: boolean
}) {
  if (items.length === 0) {
    // 0 件は「視覚表現だけ」にせず role="status" で支援技術にも伝える（US-23 / US-26 / NFR-12）。
    // role="alert" は使わない（0 件は緊急の割り込みではない・ui-ux-guidelines.md §7.2）。
    return (
      <p role="status" className="text-muted-foreground py-8 text-sm">
        {labels.empty}
      </p>
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

  // SP-16: facet の有無だけを先に引いておく（レンダー中に毎回 Map.get し直さない）。
  // usecase 側が既にランク済み → 非ランクの順で並べて返す前提（domain の sortByGemIndex）なので、
  // ここでは並べ替えず「最初に ranked → unranked へ切り替わる箇所」を 1 箇所だけ探す（D-M）。
  const facets = gemFacets
    ? items.map((item) => gemFacets.get(gemFacetKey(item.fullName)))
    : undefined
  const dividerIndex =
    facets?.findIndex((facet, idx) => {
      if (facet !== undefined) {
        return false
      }
      // ④: idx===0 は「前ページに ranked があった」と呼び出し側から明示されたときだけ区切る
      // （このページ内には比較対象の前要素が無いため idx>0 の基準を使えない）。
      if (idx === 0) {
        return unrankedContinuedFromPreviousPage === true
      }
      return facets[idx - 1] !== undefined
    }) ?? -1

  return (
    <ul className="divide-border divide-y">
      {items.map((item, index) => {
        const facet = facets?.[index]
        const card = (
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
                {/*
                SP-16 / D-L: facet を持つカードだけ Gem Index 値・被依存数を追記する
                （`daily-digest.tsx` と同じ書式・生値をそのまま出す方針）。
              */}
                {facet ? (
                  <>
                    <span>
                      {labels.gemIndexValueLabel}{' '}
                      {numberFormat.format(gemIndexValue(facet.gemIndex))}
                    </span>
                    <span>
                      {labels.gemIndexDependentLabel} {numberFormat.format(facet.dependentCount)}
                    </span>
                  </>
                ) : null}
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
        )

        // SP-16 / D-M: ranked → unranked へ切り替わる境目にだけ区切り見出しを 1 本挿入する。
        // <ul> は分割しない（件数表示・既存構造を壊さないため・タスク仕様）。
        if (index === dividerIndex) {
          return (
            <Fragment key={item.id}>
              <li className="text-muted-foreground border-border mt-2 border-t pt-3 pb-1 text-sm font-medium">
                {labels.gemIndexUnavailableHeading}
              </li>
              {card}
            </Fragment>
          )
        }
        return card
      })}
    </ul>
  )
}
