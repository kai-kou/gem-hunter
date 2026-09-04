import Link from 'next/link'
import type { GemIndex } from '../domain/model/gem-index'
import type { Locale } from '../domain/model/locale'
import type { RepositorySummary } from '../domain/model/repository'
import { GemBadge } from './gem-badge'
import { toIntlLocaleTag } from './i18n/intl-locale-tag'
import { LinkPendingAnnouncer } from './link-pending-announcer'
import { LinkPendingHint } from './link-pending-hint'
import { buildSearchUrl, type SearchUrlState } from './url/build-search-url'

type RepositoryListLabels = {
  empty: string
  starCount: string
  updatedAt: string
  /**
   * 詳細ページへの遷移中であることを支援技術へ伝える 1 文（`sr-only` のライブリージョンに載る）。
   * 理由の正本は `link-pending-hint.tsx` / `link-pending-announcer.tsx` の JSDoc（Issue #167）。
   */
  linkPending: string
  /** Gem バッジの可視ラベル（短い語・例「Gem」）。`gemIndexes` と対で渡す（SP-18 / D-36）。 */
  gemBadge?: string
  /** Gem バッジの意味を支援技術へ伝える 1 文（`sr-only`）。区切りの括弧は文言側に含める（§7.4a）。 */
  gemBadgeSrHint?: string
  /**
   * 🔴 バッジが付かないことが低評価を意味しない旨の注記（`D-36` の明示要件）。一覧に 1 回だけ出す。
   * **これを渡さないとバッジ自体が出ない**（`gemBadge` / `gemBadgeSrHint` と 3 点セットで渡す）。
   */
  gemBadgeNote?: string
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
  gemIndexes,
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
   * Gem 候補プールに載っているリポジトリの `fullName` → Gem Index（SP-18 / D-36）。
   * 渡すと該当カードにだけ Gem バッジを出す。省略時はバッジも注記も出ない（後方互換）。
   *
   * 🔴 **キーは `item.fullName` をそのまま使う**（大文字小文字の畳み込み等、照合の正規化は
   * データ側の責務。ここで正規化すると照合規則の正本が 2 箇所に分かれる）。
   * 🔴 **値（Gem Index）を並び替えに使わない**。`D-36` は「ソート軸としての体験破綻」を理由に
   * `sort=gem-index` を却下しており、バッジは並び順を変えない注釈である。
   */
  gemIndexes?: ReadonlyMap<string, GemIndex>
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

  // バッジを出せるのは文言が **3 つとも** 揃っているときだけ（`gemIndexes` だけでは描画しない）。
  // 🔴 `gemBadgeNote` を条件に含めるのが要点: 3 つは独立した optional なので、注記だけ渡し忘れた
  //    呼び出しがあると「バッジは出るのに『付かない＝低評価ではない』注記が出ない」状態になる。
  //    これは `D-36` が明示要件とした注記の欠落そのものなので、描画側で構造的に防ぐ。
  const gemBadgeLabel = labels.gemBadge
  const gemBadgeSrHint = labels.gemBadgeSrHint
  const gemBadgeNote = labels.gemBadgeNote
  const canShowGemBadge =
    gemIndexes !== undefined &&
    gemBadgeLabel !== undefined &&
    gemBadgeSrHint !== undefined &&
    gemBadgeNote !== undefined
  // 注記は「バッジが 1 つ以上出ているとき」だけ、一覧に 1 回だけ出す（カードごとに出さない）。
  const shownGemBadgeCount = canShowGemBadge
    ? items.filter((item) => gemIndexes.has(item.fullName)).length
    : 0

  return (
    <>
      {/* 遷移中の読み上げは一覧に 1 個だけ（`link-pending-announcer.tsx` の JSDoc・Issue #167）。 */}
      <LinkPendingAnnouncer label={labels.linkPending}>
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
              {/* 第三者由来テキスト（`description` には改行機会ゼロの長い URL が入りうる）の
                  折り返し。この `<div>` は `min-w-0` で floor を外した flex アイテムなので、
                  ここに 1 回当てれば配下の `<a>` / `<p>` まで継承で届く（`ui-ux-guidelines.md` §3・
                  退行検知は `e2e/overflow-guard.spec.ts`）。 */}
              <div className="min-w-0 flex-1 break-words">
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
                  {/* 遷移中の視覚ヒント。理由の正本は `link-pending-hint.tsx` の JSDoc（Issue #167）。 */}
                  <LinkPendingHint />
                </Link>
                {/*
                Gem バッジはリポジトリ名リンクの直後（同じ行）に置く（SP-18 / D-36）。
                🔴 リンクの **外**（兄弟）に置く: 内側に入れるとリンクのアクセシブルネームに
                `srHint` が混ざり、リンク一覧の読み上げが冗長になる（§7.4a の裏返し）。
                非フォーカス要素なので、カード全体を覆う `::after` のクリック領域と競合しない（§4.3）。
              */}
                {canShowGemBadge && gemIndexes.has(item.fullName) ? (
                  <>
                    {' '}
                    <GemBadge label={gemBadgeLabel} srHint={gemBadgeSrHint} />
                  </>
                ) : null}
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
                        /* この `<li>` は `ul.flex.flex-wrap` の flex アイテムなので、祖先から
                           継承した `break-words` では閉じない（理由は `ui-ux-guidelines.md` §3 の表）。
                           GitHub の topic は空白・ハイフンなしの単一トークンで最大 50 文字あり得る。 */
                        className="bg-muted text-muted-foreground rounded-full px-2 py-0.5 text-xs wrap-anywhere"
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
      </LinkPendingAnnouncer>
      {/*
        🔴 `D-36` の明示要件: バッジが付かないことが低評価を意味しない旨の注記。
        Gem Index は 12 レジストリの被依存数上位に限った **限定母集団** に対するカバレッジ指標で、
        実測でも一般語の検索上位 100 件のうち平均 34.5% しか載らない（`D-36` の SP-17 実測追記）。
        一覧の外（`ul` の兄弟）に 1 回だけ置き、カードごとの重複読み上げを避ける。
      */}
      {shownGemBadgeCount > 0 && gemBadgeNote !== undefined ? (
        <p className="text-muted-foreground mt-3 text-xs">{gemBadgeNote}</p>
      ) : null}
    </>
  )
}
