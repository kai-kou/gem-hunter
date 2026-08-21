import sanitizeHtml from 'sanitize-html'

/**
 * GitHub がレンダリング済みの README HTML（未サニタイズ・第三者由来）を、表示してよい形へ
 * 1 パスで変換する（Issue #334 F-4・`content/discussions/feedback334_detail_readme_20260821/whiteboard.md`
 * round3 lead 裁定）。
 *
 * 変換内容（すべて 1 回の `sanitize-html` 呼び出しで完結させる）:
 * - 許可リスト方式でタグ・属性を絞る（`script` / `style` / `iframe` / `object` / `embed` /
 *   `form` / `input` と `on*` 属性、`javascript:` 等の危険スキームは確実に落とす）
 * - 相対リンク・相対画像を絶対 URL へ解決する（解決できない・スキームが安全でないものは
 *   リンクなら素のテキストへ、画像なら丸ごと落とす）
 * - 外部リンクに `target="_blank" rel="noopener noreferrer"` を付ける
 * - 見出しを +2 シフトする（`h1→h3` … `h5`/`h6` は `h6` で cap。タグ名そのものを書き換える。
 *   `id="user-content-*"` は保持し README 内アンカーを機能させ続ける）
 * - テキスト長を変換パス内で累積し、上限（`README_TRUNCATE_LENGTH`）を超えたら以降を切り詰める
 *   （サニタイズ前後での文字数カットは行わない。パーサが開いたタグを最後まで閉じるため、
 *   このやり方なら常に整形式の HTML が残る）
 *
 * 🔴 `parseStyleAttributes: false` で postcss 経路自体を切る（style 属性を一切解釈しない）。
 */

/** README 本文の切り詰め上限（文字数）。約 30,000 文字（表示上限の暫定値）。 */
export const README_TRUNCATE_LENGTH = 30_000

/** 見出しの降格先（+2 シフト・h6 で cap）。 */
const HEADING_SHIFT: Record<string, string> = {
  h1: 'h3',
  h2: 'h4',
  h3: 'h5',
  h4: 'h6',
  h5: 'h6',
  h6: 'h6',
}

/** href / src として許可するスキーム。`javascript:` / `data:` 等は含めない。 */
const SAFE_URL_SCHEMES = new Set(['http:', 'https:'])

/**
 * 許可リストの外へ追い出すための、決して許可しないタグ名。
 * `disallowedTagsMode`（既定 `'discard'`）により、タグ自体は消えるが子要素・テキストは
 * 引き続き出力される（＝リンクは「素のテキスト」として残る）。
 */
const DROPPED_TAG = 'gem-hunter-readme-dropped'

const ALLOWED_TAGS = [
  'p',
  'br',
  'hr',
  'b',
  'strong',
  'i',
  'em',
  's',
  'del',
  'ins',
  'u',
  'mark',
  'small',
  'sub',
  'sup',
  'code',
  'pre',
  'kbd',
  'samp',
  'blockquote',
  'q',
  'ul',
  'ol',
  'li',
  'dl',
  'dt',
  'dd',
  'table',
  'thead',
  'tbody',
  'tfoot',
  'tr',
  'th',
  'td',
  'caption',
  'colgroup',
  'col',
  'a',
  'img',
  'h3',
  'h4',
  'h5',
  'h6',
  'div',
  'span',
]

const ALLOWED_ATTRIBUTES: Record<string, string[]> = {
  a: ['href', 'target', 'rel', 'id'],
  img: ['src', 'alt', 'width', 'height'],
  h3: ['id'],
  h4: ['id'],
  h5: ['id'],
  h6: ['id'],
  ol: ['start'],
  th: ['colspan', 'rowspan'],
  td: ['colspan', 'rowspan'],
}

export type SanitizeReadmeHtmlOptions = {
  /** 相対リンク（`docs/a.md` 等）を解決する基準 URL（例: `https://github.com/{owner}/{repo}/blob/HEAD/`）。 */
  linkBaseUrl: string
  /** 相対画像（`./screenshot.png` 等）を解決する基準 URL（例: `https://raw.githubusercontent.com/{owner}/{repo}/HEAD/`）。 */
  imageBaseUrl: string
}

export type SanitizeReadmeHtmlResult = {
  /** サニタイズ済みの HTML（`dangerouslySetInnerHTML` にそのまま渡してよい）。 */
  html: string
  /** テキスト長の上限（`README_TRUNCATE_LENGTH`）に達し、以降を切り詰めたら true。 */
  truncated: boolean
}

/** フラグメントのみ（`#user-content-...`）か / スキーム付き絶対 URL かを判定して解決する。 */
function resolveUrl(value: string, base: string): string | null {
  // フラグメントのみの href は README 内アンカー（保持している見出しの id）への参照なので、
  // 絶対 URL へ書き換えず素通しする（そうしないとページ内リンクとして機能しなくなる）。
  if (value.startsWith('#')) {
    return value
  }
  try {
    const resolved = new URL(value, base)
    if (!SAFE_URL_SCHEMES.has(resolved.protocol)) {
      return null
    }
    return resolved.toString()
  } catch {
    return null
  }
}

export function sanitizeReadmeHtml(
  rawHtml: string,
  options: SanitizeReadmeHtmlOptions,
): SanitizeReadmeHtmlResult {
  let consumedLength = 0
  let truncated = false

  const html = sanitizeHtml(rawHtml, {
    allowedTags: ALLOWED_TAGS,
    allowedAttributes: ALLOWED_ATTRIBUTES,
    allowedSchemes: ['http', 'https'],
    // 🔴 style 属性の CSS パース（postcss 経路）を丸ごと切る。README の見た目はこちらの
    //    ページのスタイルに従わせる方針であり、第三者由来の CSS を解釈させる必要がない。
    parseStyleAttributes: false,
    transformTags: {
      h1: (_tagName, attribs) => headingTag(HEADING_SHIFT.h1, attribs),
      h2: (_tagName, attribs) => headingTag(HEADING_SHIFT.h2, attribs),
      h3: (_tagName, attribs) => headingTag(HEADING_SHIFT.h3, attribs),
      h4: (_tagName, attribs) => headingTag(HEADING_SHIFT.h4, attribs),
      h5: (_tagName, attribs) => headingTag(HEADING_SHIFT.h5, attribs),
      h6: (_tagName, attribs) => headingTag(HEADING_SHIFT.h6, attribs),
      a: (_tagName, attribs) => {
        const href = attribs.href
        if (href === undefined) {
          // href の無い a タグはリンクとして意味を持たないため、タグだけ落として
          // 内側のテキストは残す（許可リスト外のタグ名へ逃がす＝ discard の挙動を利用）。
          return { tagName: DROPPED_TAG, attribs: {} }
        }
        const resolved = resolveUrl(href, options.linkBaseUrl)
        if (resolved === null) {
          return { tagName: DROPPED_TAG, attribs: {} }
        }
        const nextAttribs: Record<string, string> = { href: resolved }
        // フラグメントのみ（ページ内アンカー）は新しいタブで開く対象ではない。
        if (!resolved.startsWith('#')) {
          nextAttribs.target = '_blank'
          nextAttribs.rel = 'noopener noreferrer'
        }
        return { tagName: 'a', attribs: nextAttribs }
      },
      img: (_tagName, attribs) => {
        const src = attribs.src
        if (src === undefined) {
          return { tagName: DROPPED_TAG, attribs: {} }
        }
        const resolved = resolveUrl(src, options.imageBaseUrl)
        if (resolved === null) {
          return { tagName: DROPPED_TAG, attribs: {} }
        }
        const nextAttribs: Record<string, string> = { src: resolved }
        if (attribs.alt !== undefined) {
          nextAttribs.alt = attribs.alt
        }
        if (attribs.width !== undefined) {
          nextAttribs.width = attribs.width
        }
        if (attribs.height !== undefined) {
          nextAttribs.height = attribs.height
        }
        return { tagName: 'img', attribs: nextAttribs }
      },
    },
    // 🔴 切り詰めの本体。変換パス内でテキスト長を累積し、上限を超えた時点で以降のテキストを
    //    すべて空文字にする。タグの開閉自体は htmlparser2 が最後まで面倒を見るため、
    //    テキストだけを止めても常に整形式の HTML が残る（サニタイズ前後での文字数カットは
    //    タグの途中で切れるおそれがあるため採らない・whiteboard round3 裁定）。
    textFilter: (text) => {
      if (truncated) {
        return ''
      }
      const remaining = README_TRUNCATE_LENGTH - consumedLength
      if (remaining <= 0) {
        truncated = true
        return ''
      }
      consumedLength += text.length
      if (text.length > remaining) {
        truncated = true
        return sliceWithoutSplittingSurrogatePair(text, remaining)
      }
      return text
    },
  })

  return { html, truncated }
}

/**
 * `text` を先頭から `length` コード単位で切る。ただし切断位置がサロゲートペアの **中間** に
 * 来る場合は 1 コード単位手前で切る（Issue #334 Layer 1 レビュー指摘）。
 *
 * JS の文字列は UTF-16 コード単位の列なので、素の `slice` は絵文字（U+10000 以上）を割って
 * 孤立サロゲートを残す。孤立サロゲートは UTF-8 エンコード時に例外ではなく `U+FFFD`（`\uFFFD`）へ
 * 静かに置換されるため、切れ目の 1 文字が文字化けした状態で表示される。
 */
function sliceWithoutSplittingSurrogatePair(text: string, length: number): string {
  if (length <= 0) {
    return ''
  }
  const isHighSurrogate = (code: number) => code >= 0xd800 && code <= 0xdbff
  const isLowSurrogate = (code: number) => code >= 0xdc00 && code <= 0xdfff
  const splitsPair =
    isHighSurrogate(text.charCodeAt(length - 1)) && isLowSurrogate(text.charCodeAt(length))
  return text.slice(0, splitsPair ? length - 1 : length)
}

function headingTag(
  tagName: string,
  attribs: Record<string, string>,
): { tagName: string; attribs: Record<string, string> } {
  const nextAttribs: Record<string, string> = {}
  if (attribs.id !== undefined) {
    nextAttribs.id = attribs.id
  }
  return { tagName, attribs: nextAttribs }
}
