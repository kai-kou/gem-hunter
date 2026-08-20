import type { DigestMeta } from '../domain/model/gem'

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
 * 単純な `<p>` + `<a>`。ARIA の追加ロールは不要（本文中の脚注扱い）。
 */
export function AttributionNotice({
  meta,
  labels,
}: {
  meta: DigestMeta
  labels: AttributionNoticeLabels
}) {
  // ライセンス URL は `sourceLicenseUrl`（例: CC BY-SA 4.0 の deed 頁）。ラベル文字列の中の
  // `{license}` プレースホルダ位置を `<a>` に置き換えるため、テンプレートを事前分割する。
  const template = labels.attribution
  // `{source}` / `{license}` / `{generatedAt}` の 3 プレースホルダを保持したまま `{license}` の
  // 前後で split し、リンクだけを差し込む。他プレースホルダは差し込み後に順次置換する。
  const parts = splitOn(template, '{license}')
  const before = fillPlaceholders(parts[0] ?? '', {
    source: meta.source,
    generatedAt: meta.generatedAt,
  })
  const after = fillPlaceholders(parts[1] ?? '', {
    source: meta.source,
    generatedAt: meta.generatedAt,
  })

  return (
    <p className="text-muted-foreground mt-6 text-xs">
      {before}
      <a
        href={meta.sourceLicenseUrl}
        rel="noopener noreferrer"
        target="_blank"
        className="text-primary rounded-sm underline underline-offset-4 outline-none focus-visible:ring-3 focus-visible:ring-ring"
      >
        {meta.license}
      </a>
      {after}
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

/**
 * `{key}` プレースホルダを値で置換する（`formatMessage` と同じ規約だが、`{license}` を
 * 触らないため個別実装）。`$&` 等の特殊置換パターンを無害化するため置換関数形式を使う。
 */
function fillPlaceholders(template: string, values: Record<string, string>): string {
  return template.replace(/\{(\w+)\}/g, (matched: string, key: string) =>
    Object.prototype.hasOwnProperty.call(values, key) ? values[key] : matched,
  )
}
