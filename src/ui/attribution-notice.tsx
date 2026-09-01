import type { DigestMeta } from '../domain/model/gem'
import type { Locale } from '../domain/model/locale'
import { toIntlLocaleTag } from './i18n/intl-locale-tag'
import { INLINE_LINK_CLASS_NAME, isHttpUrl, splitOn } from './inline-template'

const GENERATED_AT_PLACEHOLDER = '{generatedAt}'

type AttributionNoticeLabels = {
  /**
   * 出典表示テンプレート（プレースホルダ: `{source}` / `{license}` / `{generatedAt}`）。
   * ライセンス名の後段は、数値が取得時点の参考値であることと「並び順は日付をもとに毎日算出
   * しています」（改変の明示・`D-29`）まで含める（辞書側の文言を分割せず 1 本にしたい・
   * 切れ目で改行しない）。🔴 文言は `D-33`（#308）で初見ユーザー向けに刷新済み。
   *
   * 🔵 `{generatedAt}` は **任意**。含まれていなければ生成時刻のノードを描かない
   * （Gem 一覧の `gems.attribution` のように生成時刻を出さない面でも同じ実装を使えるようにする）。
   */
  attribution: string
  /**
   * 「新しいタブで開きます」の sr-only 告知文言（`messages/{locale}.json` の
   * `common.opensInNewTab` 由来。ハードコードしない・§3 の i18n 方針）。
   *
   * 🔴 `SafeLink` が描くリンクは **すべて** `target="_blank"` なので、出典元
   * （`sourceUrl`）・ライセンス（`sourceLicenseUrl`）の **両方** に添える。
   * §7.4a は「新しいタブで開くリンクを実装するときは 3 点を必ず満たす」と
   * 無条件に定めており、対象をライセンスリンクへ絞ってはいない（節見出しの
   * 括弧書きは適用例の列挙）。片方だけに付けると、告知のないリンクは同一タブで
   * 開くと誤って推論される（Issue #287・PR #765 Layer 1 レビュー指摘）。
   */
  opensInNewTab: string
}

/**
 * データ出典と改変の明示（`ADR 0014` §2.6 の `D-29` 帰属表示）。
 * Ecosyste.ms（CC BY-SA 4.0）のパーセンタイル順位を入力に、こちらで日付から
 * 再算出した並び順を表示している旨を伝える。あわせて、表示している数値が取得時点の
 * 参考値であり詳細画面（GitHub API のライブ値）と差があることも同じ文で伝える（`D-33`）。
 *
 * 単純な `<p>` + `<a>` + `<time>`。ARIA の追加ロールは不要（本文中の脚注扱い）。
 *
 * 🔴 **帰属表示の実装はこの 1 本だけ**（トップページと Gem 一覧が共用する）。面ごとに
 * 派生版を作らない（PR #440 Layer 1 指摘: 同じ `D-29` 要件の実装が 2 つに割れていた）。
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

  // 出典元 URL は `sourceUrl`（例: Ecosyste.ms トップページ）、ライセンス URL は
  // `sourceLicenseUrl`（例: CC BY-SA 4.0 の deed 頁）。ラベル文字列の中の `{source}` /
  // `{license}` / `{generatedAt}` プレースホルダ位置を要素へ置き換えるため、この順で
  // 逐次分割する（実際の辞書文言はこの順で並ぶ・`messages/ja.json` `home.digest.attribution`）。
  const [beforeSource, afterSource] = splitOn(labels.attribution, '{source}')
  const [beforeLicense, afterLicense] = splitOn(afterSource, '{license}')
  const hasGeneratedAt = afterLicense.includes(GENERATED_AT_PLACEHOLDER)
  const [beforeGeneratedAt, afterGeneratedAt] = splitOn(afterLicense, GENERATED_AT_PLACEHOLDER)

  return (
    <p className="text-muted-foreground mt-6 text-xs">
      {beforeSource}
      <SafeLink
        href={meta.sourceUrl}
        text={meta.source}
        opensInNewTabLabel={labels.opensInNewTab}
      />
      {beforeLicense}
      <SafeLink
        href={meta.sourceLicenseUrl}
        text={meta.license}
        opensInNewTabLabel={labels.opensInNewTab}
      />
      {/*
        🔵 `{generatedAt}` を含まない文言（Gem 一覧）では時刻ノードごと描かない。
        含まないのに描くと、文の末尾へ日時が接ぎ木されて意味の通らない文になる。
      */}
      {hasGeneratedAt ? (
        <>
          {beforeGeneratedAt}
          <GeneratedAt value={meta.generatedAt} format={dateTimeFormat} />
          {afterGeneratedAt}
        </>
      ) : (
        beforeGeneratedAt
      )}
    </p>
  )
}

/**
 * 生成時刻。候補プール JSON が壊れていると `generatedAt` は空文字・非 ISO 文字列になりうる
 * （`StaticGemDigest` はそこで throw せずフォールバックする）。`Intl` は Invalid Date で
 * RangeError を投げるので、パースできた場合だけ整形し、それ以外は生値をそのまま出す。
 */
function GeneratedAt({ value, format }: { value: string; format: Intl.DateTimeFormat }) {
  const date = toValidDate(value)
  if (!date) return <>{value}</>
  return <time dateTime={value}>{`${format.format(date)} JST`}</time>
}

/**
 * `http(s)` のときだけリンクにし、それ以外はテキストのまま出す。
 *
 * 🔴 候補プール JSON は外部データ由来なので、URL を無検査で `href` へ渡さない
 * （`javascript:` を `href` に流さない）。
 *
 * `opensInNewTabLabel` が渡されたときだけ、新しいタブで開く旨の `sr-only` 告知を
 * `<a>` の **内側** に添える（§7.4a）。外側（兄弟要素）に置くとリンクの
 * アクセシブルネームに入らない。文言側が括弧で始まる前提で、間に空白を挟まず
 * 連結する（§7.4a 4 点目・JSX の空白落ちに頼らない）。
 */
function SafeLink({
  href,
  text,
  opensInNewTabLabel,
}: {
  href: string
  text: string
  opensInNewTabLabel?: string
}) {
  if (!isHttpUrl(href)) {
    return <>{text}</>
  }
  return (
    <a href={href} rel="noopener noreferrer" target="_blank" className={INLINE_LINK_CLASS_NAME}>
      {text}
      {opensInNewTabLabel ? <span className="sr-only">{opensInNewTabLabel}</span> : null}
    </a>
  )
}

/** ISO 8601 としてパースできれば `Date`、できなければ `null`（Invalid Date を外へ出さない）。 */
function toValidDate(value: string): Date | null {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}
