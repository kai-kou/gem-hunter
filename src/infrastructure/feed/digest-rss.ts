import type { DailyDigest, Gem } from '../../domain/model/gem'

/**
 * 日次ダイジェストを RSS 2.0 XML 文字列へレンダリングする純粋関数（`US-33`）。
 *
 * 🔴 DOM / ネットワーク非依存（infrastructure 層の純粋関数・`architecture-rules.md`）。
 * 🔴 **D-29**: Ecosyste.ms の生テキスト（description 等）は `Gem` 型に存在しないため、
 * ここで組み立てる `<description>` は数値・識別子のみの自作文に限る（構造的に混入不可能）。
 * 🔴 帰属表示（source / license / sourceLicenseUrl）は `<channel>` レベルに必ず含める
 * （`DigestMeta` の帰属表示義務）。
 */

export type RenderDigestRssOptions = {
  /** RSS を配信するオリジン（例 `https://gem-hunter.example.com`）。item の link 組み立てに使う。 */
  readonly origin: string
}

const CHANNEL_TITLE = 'gem-hunter — 今日の Gem'
const GENERATOR = 'gem-hunter digest-rss'

export function renderDigestRss(digest: DailyDigest, opts: RenderDigestRssOptions): string {
  const origin = stripTrailingSlash(opts.origin)
  const channelDescription = buildChannelDescription(digest)
  const lastBuildDate = toRfc822(digest.meta.generatedAt)

  const itemsXml = digest.items.map((gem) => renderItem(gem, digest.date, origin)).join('')

  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<rss version="2.0">',
    '<channel>',
    `<title>${escapeXml(CHANNEL_TITLE)}</title>`,
    `<link>${escapeXml(origin)}</link>`,
    `<description>${escapeXml(channelDescription)}</description>`,
    lastBuildDate ? `<lastBuildDate>${escapeXml(lastBuildDate)}</lastBuildDate>` : '',
    `<generator>${escapeXml(GENERATOR)}</generator>`,
    `<copyright>${escapeXml(buildAttribution(digest))}</copyright>`,
    itemsXml,
    '</channel>',
    '</rss>',
  ]
    .filter((line) => line.length > 0)
    .join('')
}

function renderItem(gem: Gem, date: string, origin: string): string {
  const [owner, repo] = splitRepositoryFullName(gem.repositoryFullName)
  const link = `${origin}/ja/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}`
  const guid = `${date}:${gem.packageName}`
  const description = buildItemDescription(gem)

  return [
    '<item>',
    `<title>${escapeXml(gem.packageName)}</title>`,
    `<link>${escapeXml(link)}</link>`,
    `<guid isPermaLink="false">${escapeXml(guid)}</guid>`,
    `<description>${escapeXml(description)}</description>`,
    '</item>',
  ].join('')
}

/** `owner/repo` を最初の `/` で 2 分割する（`StaticGemDigest` が既に owner/repo 形式を保証済み）。 */
function splitRepositoryFullName(fullName: string): readonly [string, string] {
  const slashIndex = fullName.indexOf('/')
  if (slashIndex === -1) {
    return [fullName, '']
  }
  return [fullName.slice(0, slashIndex), fullName.slice(slashIndex + 1)]
}

/** 数値・識別子のみの自作文（`D-29`：生テキストを組み込まない）。 */
function buildItemDescription(gem: Gem): string {
  return `被依存数 ${gem.dependentCount}・star ${gem.stars}・Gem Index ${gem.gemIndex}`
}

function buildChannelDescription(digest: DailyDigest): string {
  return `${digest.date} 時点の日次ダイジェスト（${digest.items.length} 件）`
}

function buildAttribution(digest: DailyDigest): string {
  const { source, license, sourceLicenseUrl } = digest.meta
  return `Data via ${source} (${license}). Values are derived/aggregated by gem-hunter. ${sourceLicenseUrl}`
}

/** ISO 8601 文字列を RFC 822（RSS `lastBuildDate` の必須形式）へ変換する。不正・空は省略する。 */
function toRfc822(isoDate: string): string | null {
  if (!isoDate) return null
  const date = new Date(isoDate)
  if (Number.isNaN(date.getTime())) return null
  // `toUTCString()` は RFC 822 互換の 'Thu, 20 Aug 2026 16:56:03 GMT' 形式を返す（RSS の
  // `<lastBuildDate>` / `<pubDate>` はこの形式を要求する）。追加の変換は不要。
  return date.toUTCString()
}

function stripTrailingSlash(value: string): string {
  return value.endsWith('/') ? value.slice(0, -1) : value
}

const XML_ESCAPE_MAP: Readonly<Record<string, string>> = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&apos;',
}

/** XML 特殊文字をエスケープする（`&` を最初に処理し二重エスケープを防ぐ）。 */
function escapeXml(value: string): string {
  return String(value).replace(/[&<>"']/g, (char) => XML_ESCAPE_MAP[char] ?? char)
}
