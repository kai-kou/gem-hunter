import Link from 'next/link'
import type { Locale } from '../domain/model/locale'
import type { DailyDigest } from '../domain/model/gem'
import { gemIndexValue } from '../domain/model/gem-index'
import { ownerOf, repoOf, type RepositoryFullName } from '../domain/model/repository-full-name'
import { toIntlLocaleTag } from './i18n/intl-locale-tag'

type DailyDigestLabels = {
  /** セクション見出し（例: 「今日の Gem」）。 */
  heading: string
  /** 候補が 0 件のときの案内文（role="status" に載る）。 */
  empty: string
  /** 被依存数の視覚ラベル（数値の隣に添える短い語）。 */
  dependentLabel: string
  /** star 数の視覚ラベル。 */
  starsLabel: string
  /** Gem Index の視覚ラベル。 */
  gemIndexLabel: string
}

/**
 * 発見面: キーワードを入力しなくても、その日の Gem が有限件数で並ぶ
 * （`ADR 0014` §2.1〜§2.6・`SP-14` / `AR-9` / `US-30`〜`US-32`）。
 *
 * 表示専用の Server Component。データ取得・並び替えは usecase 側（`get-daily-digest.ts`）が
 * 決定論的シード（`DateSeed`）を唯一の入力として済ませる（`ADR 0014` §2.2）ため、本
 * コンポーネントはそれを **順序どおり** に描画するだけで良い（クライアント JS を持たない・
 * `NFR-3`）。
 *
 * a11y:
 * - 見出しは `<h2>` で `id="daily-digest-heading"`（`aria-labelledby` の参照先）
 * - 一覧は `<ol>` で並び順に意味を持たせる（順序不定のセットではない）
 * - 空配列時は `role="status"` の `<p>` で「今日は表示できる Gem がありません」を伝える
 *   （`RepositoryList` の 0 件と同じ作法・`ui-ux-guidelines.md` §7.2）
 * - 詳細画面へのリンクは既存の `RepositoryList` と同じ `focus-visible` 実装
 *   （太さ 2px 相当以上・`ui-ux-guidelines.md` §7.3）
 * - 日付切替を `next/link` で実装するスプリントで、見出しへの `tabIndex={-1}` +
 *   `focus-visible` リングを `FocusOnNavigate`（`targetId="daily-digest-heading"`）の配線と
 *   セットで復活させる（現時点では focus() する側が居ないため置かない・YAGNI）
 *
 * 表示条件: **キーワード未入力時のみ描画される**。表示 / 非表示の判断は呼び出し側
 * （`app/[locale]/page.tsx`）が持ち、本コンポーネントは条件を知らない。
 * 理由: 検索結果一覧と Gem 一覧の `<ol>` が同時に DOM へ並ぶと、既存 E2E の
 * `getByRole('list').first()` が Gem 側を拾ってしまい `SP-1` / `SP-7` / `SP-10` が壊れるため。
 */
export function DailyDigest({
  digest,
  labels,
  locale,
}: {
  digest: DailyDigest
  labels: DailyDigestLabels
  locale: Locale
}) {
  const localeTag = toIntlLocaleTag(locale)
  const numberFormat = new Intl.NumberFormat(localeTag)

  return (
    <section aria-labelledby="daily-digest-heading" className="mt-6">
      <h2 id="daily-digest-heading" className="text-lg font-semibold">
        {labels.heading}
      </h2>

      {digest.items.length === 0 ? (
        // 0 件は視覚だけでなく支援技術にも伝える（`RepositoryList` の 0 件と同じ作法）。
        <p role="status" className="text-muted-foreground py-8 text-sm">
          {labels.empty}
        </p>
      ) : (
        <ol className="divide-border mt-3 divide-y">
          {digest.items.map((gem, index) => {
            // `owner/repo` の分割はドメインの関数へ寄せる（`split('/')[1] ?? ''` を UI に散らさない）。
            // 形式検証はインフラ層（`static-gem-digest.ts`）が済ませており、満たさない候補は
            // そもそもここへ届かない（届いていれば `owner/repo` である）。
            const fullName = gem.repositoryFullName as RepositoryFullName
            const owner = ownerOf(fullName)
            const repo = repoOf(fullName)

            return (
              <li key={gem.packageName} className="relative flex gap-3 py-4">
                <span
                  aria-hidden="true"
                  className="text-muted-foreground w-6 shrink-0 text-right text-sm tabular-nums"
                >
                  {index + 1}.
                </span>
                <div className="min-w-0 flex-1">
                  {/*
                    詳細ページへの遷移（AC-4・独立 URL・モーダルではない）。
                    カード全体を tap 領域にするため ::after でクリック領域を拡張する
                    （`repository-list.tsx` と同じ作法）。
                  */}
                  <Link
                    href={`/${locale}/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}`}
                    className="text-primary rounded-sm font-medium underline-offset-4 outline-none after:absolute after:inset-0 hover:underline focus-visible:ring-3 focus-visible:ring-ring"
                  >
                    {gem.packageName}
                  </Link>
                  <p className="text-muted-foreground mt-1 text-xs">{gem.repositoryFullName}</p>
                  <p className="text-muted-foreground mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs">
                    <span>
                      {labels.dependentLabel} {numberFormat.format(gem.dependentCount)}
                    </span>
                    <span>
                      <span aria-hidden="true">★ </span>
                      <span className="sr-only">{labels.starsLabel} </span>
                      {numberFormat.format(gem.stars)}
                    </span>
                    <span>
                      {labels.gemIndexLabel} {numberFormat.format(gemIndexValue(gem.gemIndex))}
                    </span>
                  </p>
                </div>
              </li>
            )
          })}
        </ol>
      )}
    </section>
  )
}
