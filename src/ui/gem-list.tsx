import Link from 'next/link'

import { DEFAULT_PAGE } from '@/src/domain/model/page-number'
import { formatMessage } from '@/src/shared/i18n/format-message'
import { gemIndexValue } from '../domain/model/gem-index'
import type { Locale } from '../domain/model/locale'
import type { GemPoolSearchResult } from '../domain/ports/gem-index-port'
import { toIntlLocaleTag } from './i18n/intl-locale-tag'
import { SEARCH_PARAM_KEYS } from './url/search-params'

/**
 * Gem 一覧（`/{locale}/gems`）の文言。**UI コンポーネントに日本語を直書きしない**（`E-4`）。
 * テンプレート文字列のプレースホルダ（`{query}` / `{token}` / `{count}` / `{source}` /
 * `{license}`）は本コンポーネントが置換する（呼び出し側で置換済みの文字列を渡しても
 * 単に置換対象が無いだけで壊れない）。
 */
export type GemListLabels = {
  /** 見出し。検索語を埋める `{query}` を含む。 */
  heading: string
  /**
   * 0 件時の本文。🔴 **母集団を明示する文言を渡す**（`D-36`）: この一覧は 12 のパッケージ
   * レジストリの被依存数上位から作った限定的な候補プールが対象であり、載っていないことは
   * 評価が低いことを意味しない。
   *
   * ⚠️ こちらは **候補プールに載っていなかった** ときの説明。照合そのものができなかったとき
   * （日本語だけの検索語など）は `unmatchableQuery` を出す（2 つの空状態を取り違えない）。
   */
  empty: string
  /**
   * 照合不能時の本文（`unmatchableQuery` プロパティが `true` のとき）。🔴 **照合規則
   * （パッケージ名・リポジトリ名という英数字識別子に対する単語境界一致・`D-37`）と、
   * 利用者が次に取れる行動（英語のキーワードで試す）を含む文言を渡す**。
   */
  unmatchableQuery: string
  /** 全語 AND が 0 件で 1 語へ緩めたときの注記。使ったトークンを埋める `{token}` を含む。 */
  relaxedNotice: string
  /** 総件数の表示。整形済みの件数を埋める `{count}` を含む。 */
  totalCount: string
  /** star 数の `sr-only` ラベル（数値だけでは意味が伝わらないため）。 */
  starCount: string
  /** 被依存パッケージ数の `sr-only` ラベル。 */
  dependentCount: string
  /** Gem Index の見出し語（可視）。 */
  gemIndexLabel: string
  /** レジストリの見出し語（可視）。 */
  registryLabel: string
  /** 帰属表示（`D-29`）。`{source}` / `{license}` を含む。 */
  attribution: string
}

/**
 * 詳細ページから Gem 一覧へ戻るための出所マーカー。
 * 🔴 **文字列を各所へ直書きしない**（戻り先判定は `app/` 側の責務だが、名前の正本はここ）。
 */
export const GEM_LIST_SOURCE_PARAM_KEY = 'from'
export const GEM_LIST_SOURCE_PARAM_VALUE = 'gems'

/**
 * Gem 候補プールの絞り込み結果一覧（`SP-19` / `D-37`）。表示だけを持つ Server Component。
 *
 * - 並び順は `result.items` の順序そのまま（`gemIndex` 昇順）。**ここで並べ替えない**
 *   （`gemIndex` は母集団相対の値で、UI で閾値・順序を作り直すと正本が 2 箇所に分かれる）
 * - ページネーション UI は持たない（`app/` 側の配線が扱う）。総件数の表示までにとどめる
 */
export function GemList({
  result,
  query,
  locale,
  labels,
  page = DEFAULT_PAGE,
  unmatchableQuery = false,
}: {
  result: GemPoolSearchResult
  /** 画面に出ている検索語（見出しと戻り先クエリに使う）。 */
  query: string
  locale: Locale
  labels: GemListLabels
  /**
   * 🔴 **0 件の理由が「照合不能」か**（検索語は空でないのに照合に使えるトークンが 1 つも
   * 取れなかった。日本語だけの検索語など）。判定の正本は `src/usecases/search-gems.ts`
   * （生の検索語 → トークン列の変換を持つ層）で、ここは受け取って文言を切り替えるだけ。
   * `result` に混ぜず独立した prop で受けるのは、`GemPoolSearchResult` が
   * `GemIndexPort` の契約であり UI 都合で広げないため。
   */
  unmatchableQuery?: boolean
  /**
   * 現在のページ番号（省略時は 1）。詳細ページから戻ったときに同じページへ帰れるよう、
   * 戻り先クエリへ載せる。既定ページのときは省略する（`build-search-url.ts` と同じ作法）。
   */
  page?: number
}) {
  const localeTag = toIntlLocaleTag(locale)
  const numberFormat = new Intl.NumberFormat(localeTag)
  // Gem Index は差分スコアで小数・負値をとる。桁を揃えて小数 1 桁に丸める。
  const gemIndexFormat = new Intl.NumberFormat(localeTag, {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })

  // 戻り先の保持（`SP-7` と同じ考え方）。`build-search-url.ts` は検索ページの 4 条件
  // （q/page/sort/per_page）専用で `from` を持てないため、キー名だけ `SEARCH_PARAM_KEYS`
  // から借りて最小限のクエリを組み立てる（新しい URL 抽象は先回りで作らない）。
  const backQuery = buildBackQuery(query, page)

  return (
    <>
      <h2 className="text-lg font-semibold">{formatMessage(labels.heading, { query })}</h2>
      {/*
        全語 AND が 0 件だったため 1 語へ緩めたことの明示（`D-37`）。一覧の **前** に出す。
        ライブリージョンにはしない（0 件の `role="status"` と二重に読み上げられるのを避ける・
        `ui-ux-guidelines.md` §7.2「ライブリージョンは 1 つ」）。
      */}
      {result.relaxed ? (
        <p className="text-muted-foreground mt-2 text-sm">
          {formatMessage(labels.relaxedNotice, { token: result.usedTokens[0] ?? '' })}
        </p>
      ) : null}
      {result.items.length === 0 ? (
        // 0 件は視覚表現だけにせず `role="status"` で支援技術にも伝える（§7.2）。
        // `role="alert"` は使わない（0 件は緊急の割り込みではない）。
        // 🔴 0 件には **理由が 2 つ** ある。候補プールに載っていない（`empty`）のか、照合自体が
        // できなかった（`unmatchableQuery`）のかで説明も次の行動も違うため、文言を切り替える。
        <p role="status" className="text-muted-foreground mt-4 text-sm">
          {unmatchableQuery ? labels.unmatchableQuery : labels.empty}
        </p>
      ) : (
        <>
          <p role="status" className="text-muted-foreground mt-2 text-sm">
            {formatMessage(labels.totalCount, { count: numberFormat.format(result.totalCount) })}
          </p>
          <ul className="divide-border mt-2 divide-y">
            {result.items.map((entry) => {
              const repo = splitRepositoryFullName(entry.repositoryFullName)
              return (
                <li
                  key={`${entry.registry}/${entry.packageName}`}
                  className="relative py-4"
                  // E2E（`e2e/sp-19.spec.ts`）が並び順を機械的に検証するための値。可視テキストは
                  // ロケール桁区切り・丸めで表記が変わるため、生値を `data-` 属性で出す。
                  data-gem-index={String(gemIndexValue(entry.gemIndex))}
                  data-repository-full-name={entry.repositoryFullName}
                >
                  {/*
                    詳細ページ（独立 URL・`AC-4`）への遷移。カード全体をクリック可能にするが
                    `<a>` で全体を包まず、リポジトリ名だけをリンクにして `::after` で領域を
                    広げる（`ui-ux-guidelines.md` §4.3）。
                    🔴 `repositoryFullName` が `owner/name` に割れない値のときはリンクを作らない
                    （壊れたリンクを出すより、テキストとして見せる方が害が小さい）。
                  */}
                  {repo ? (
                    <Link
                      href={`/${locale}/repos/${encodeURIComponent(repo.owner)}/${encodeURIComponent(repo.name)}${backQuery}`}
                      // ネイティブ <a> の既定フォーカスは太さが足りないため `ring-3` に揃える（§7.3）。
                      className="text-primary rounded-sm font-medium underline-offset-4 outline-none after:absolute after:inset-0 hover:underline focus-visible:ring-3 focus-visible:ring-ring"
                    >
                      {entry.repositoryFullName}
                    </Link>
                  ) : (
                    <span className="font-medium">{entry.repositoryFullName}</span>
                  )}
                  <p className="text-muted-foreground mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs">
                    <span>{entry.packageName}</span>
                    <span>
                      {labels.registryLabel} {entry.registry}
                    </span>
                    <span>
                      <span aria-hidden="true">★ </span>
                      <span className="sr-only">{labels.starCount} </span>
                      {numberFormat.format(entry.stars)}
                    </span>
                    <span>
                      <span className="sr-only">{labels.dependentCount} </span>
                      {numberFormat.format(entry.dependentCount)}
                    </span>
                    <span>
                      {labels.gemIndexLabel} {gemIndexFormat.format(gemIndexValue(entry.gemIndex))}
                    </span>
                  </p>
                </li>
              )
            })}
          </ul>
        </>
      )}
      <Attribution meta={result.meta} template={labels.attribution} />
    </>
  )
}

/**
 * 帰属表示（`D-29`）。`{source}` / `{license}` の位置をリンクへ差し替える。
 *
 * 🔴 **`http(s)` 以外の URL はリンクにしない**（`javascript:` を `href` に流さない）。候補プール
 * JSON は外部データ由来なので、URL を無検査で `href` へ渡さない。
 *
 * 新しいタブでは開かない: `ui-ux-guidelines.md` §7.4a が `target="_blank"` に `sr-only` 文言を
 * 必須としており、本コンポーネントの文言キーはコントラクトで固定されているため（追加キーを
 * 勝手に増やさない）、同一タブ遷移にして §7.4a の要件自体を発生させない。
 */
function Attribution({ meta, template }: { meta: GemPoolSearchResult['meta']; template: string }) {
  const [beforeSource, afterSource] = splitOn(template, '{source}')
  const [beforeLicense, afterLicense] = splitOn(afterSource, '{license}')

  return (
    <p className="text-muted-foreground mt-6 text-xs">
      {beforeSource}
      <SafeLink href={meta.sourceUrl} text={meta.source} />
      {beforeLicense}
      <SafeLink href={meta.sourceLicenseUrl} text={meta.license} />
      {afterLicense}
    </p>
  )
}

const INLINE_LINK_CLASS_NAME =
  'text-primary rounded-sm underline underline-offset-4 outline-none focus-visible:ring-3 focus-visible:ring-ring'

/** `http(s)` のときだけリンクにし、それ以外はテキストのまま出す。 */
function SafeLink({ href, text }: { href: string; text: string }) {
  if (!isHttpUrl(href)) {
    return <>{text}</>
  }
  return (
    <a href={href} className={INLINE_LINK_CLASS_NAME}>
      {text}
    </a>
  )
}

function isHttpUrl(value: string): boolean {
  try {
    const url = new URL(value)
    return url.protocol === 'http:' || url.protocol === 'https:'
  } catch {
    return false
  }
}

/** 戻り先クエリ（`?from=gems&q=...&page=...`）。既定ページ・空の検索語は省略する。 */
function buildBackQuery(query: string, page: number): string {
  const params = new URLSearchParams()
  params.set(GEM_LIST_SOURCE_PARAM_KEY, GEM_LIST_SOURCE_PARAM_VALUE)
  if (query !== '') {
    params.set(SEARCH_PARAM_KEYS.keyword, query)
  }
  if (page !== DEFAULT_PAGE) {
    params.set(SEARCH_PARAM_KEYS.page, String(page))
  }
  return `?${params.toString()}`
}

/** `owner/name` を分解する。分解できなければ `null`（リンクを作らない）。 */
function splitRepositoryFullName(fullName: string): { owner: string; name: string } | null {
  const parts = fullName.split('/')
  if (parts.length !== 2) return null
  const [owner, name] = parts
  if (owner === '' || name === '') return null
  return { owner, name }
}

/** `template` を `token` の最初の出現位置で 2 分割する。見つからなければ `[template, '']`。 */
function splitOn(template: string, token: string): [string, string] {
  const idx = template.indexOf(token)
  if (idx < 0) return [template, '']
  return [template.slice(0, idx), template.slice(idx + token.length)]
}
