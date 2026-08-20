import type { DigestMeta } from '../domain/model/gem'
import type { Locale } from '../domain/model/locale'
import { formatMessage } from '../shared/i18n/format-message'
import { toIntlLocaleTag } from './i18n/intl-locale-tag'

type AttributionNoticeLabels = {
  /**
   * 出典表示テンプレート（プレースホルダ: `{source}` / `{license}` / `{generatedAt}`）。
   * ライセンス名の後段は「並び順は日付シードで再算出しています」（改変の明示・`D-29`）まで
   * 含める（辞書側の文言を分割せず 1 本にしたい・切れ目で改行しない）。
   */
  attribution: string
}

/**
 * データ出典と改変の明示（`ADR 0014` §2.6 の `D-29` 帰属表示）。
 * Ecosyste.ms（CC BY-SA 4.0）のパーセンタイル順位を入力に、こちらで日付シードで
 * 再算出した並び順を表示している旨を伝える。
 *
 * 単純な `<p>` + `<a>` + `<time>`。ARIA の追加ロールは不要（本文中の脚注扱い）。
 *
 * 🔴 生成時刻は **JST 表示**（`docs/rules/datetime-rules.md` §0）。書式は既存の
 * `repository-list.tsx` と同じ `Intl.DateTimeFormat(localeTag, { timeZone: 'Asia/Tokyo' })`
 * に揃え、機械可読値（ISO 8601 UTC）は `<time dateTime>` 側に残す。
 */
export function AttributionNotice({
  meta,
  labels,
  locale,
}: {
  meta: DigestMeta
  labels: AttributionNoticeLabels
  locale: Locale
}) {
  const localeTag = toIntlLocaleTag(locale)
  const dateTimeFormat = new Intl.DateTimeFormat(localeTag, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Asia/Tokyo',
  })

  // 候補プール JSON が壊れていると `generatedAt` は空文字・非 ISO 文字列になりうる
  // （`StaticGemDigest` はそこで throw せずフォールバックする）。`Intl` は Invalid Date で
  // RangeError を投げるので、パースできた場合だけ整形し、それ以外は生値をそのまま出す。
  const generatedAtDate = toValidDate(meta.generatedAt)
  const generatedAtNode = generatedAtDate ? (
    <time dateTime={meta.generatedAt}>{`${dateTimeFormat.format(generatedAtDate)} JST`}</time>
  ) : (
    <>{meta.generatedAt}</>
  )

  // ライセンス URL は `sourceLicenseUrl`（例: CC BY-SA 4.0 の deed 頁）。ラベル文字列の中の
  // `{license}` / `{generatedAt}` プレースホルダ位置を要素へ置き換えるため、事前分割する。
  const [beforeLicense, afterLicense] = splitOn(labels.attribution, '{license}')
  const [beforeHead, beforeTail] = splitOn(beforeLicense, '{generatedAt}')
  const [afterHead, afterTail] = splitOn(afterLicense, '{generatedAt}')
  const fill = (template: string) => formatMessage(template, { source: meta.source })

  return (
    <p className="text-muted-foreground mt-6 text-xs">
      {fill(beforeHead)}
      {beforeLicense.includes('{generatedAt}') ? generatedAtNode : null}
      {fill(beforeTail)}
      <a
        href={meta.sourceLicenseUrl}
        rel="noopener noreferrer"
        target="_blank"
        className="text-primary rounded-sm underline underline-offset-4 outline-none focus-visible:ring-3 focus-visible:ring-ring"
      >
        {meta.license}
      </a>
      {fill(afterHead)}
      {afterLicense.includes('{generatedAt}') ? generatedAtNode : null}
      {fill(afterTail)}
    </p>
  )
}

/**
 * `template` を `token` の最初の出現位置で 2 分割する（`String.prototype.split(limit)` は
 * 残りを捨てるため使わない）。見つからなければ `[template, '']` を返す。
 */
function splitOn(template: string, token: string): [string, string] {
  const idx = template.indexOf(token)
  if (idx < 0) return [template, '']
  return [template.slice(0, idx), template.slice(idx + token.length)]
}

/** ISO 8601 としてパースできれば `Date`、できなければ `null`（Invalid Date を外へ出さない）。 */
function toValidDate(value: string): Date | null {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}
