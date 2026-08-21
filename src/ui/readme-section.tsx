import type { ReactElement } from 'react'
import { sanitizeReadmeHtml, type SanitizeReadmeHtmlOptions } from './readme-html'

export type ReadmeStatusLabels = {
  /** README の取得・描画が完了したことを伝える文言（`aria-live` の遷移通知）。 */
  loaded: string
  /** README が無い・取得に失敗したときの案内文（`ReadmeSectionLabels.unavailable` と同じ文言でよい）。 */
  unavailable: string
}

/**
 * README ライブリージョン（`<section role="status" aria-live="polite">`）の **中身**（Issue #334）。
 *
 * 🔴 呼び出し元はこのコンポーネントを **ライブリージョン要素の内側** の `<Suspense>` に置く
 * （`ui-ux-guidelines.md` §7.2「ライブリージョンは初期 DOM に空で常設し、**中身を書き換える**。
 * 要素ごと動的挿入しない」）。fallback（読み込み中の文言）→ 本コンポーネント（完了文言）と
 * 同じリージョンの中身が入れ替わることで、遷移が支援技術へ通知される。トップページの
 * `#search-status`（`app/[locale]/page.tsx`）と同型。
 *
 * 視覚表示は別の `<Suspense>`（`ReadmeSection`）が担い、こちらは sr-only の通知だけを担当する。
 * README 到着時にフォーカスは移動しない（ユーザー操作起因でない後追い描画のため）。
 */
export async function ReadmeStatusText({
  readmePromise,
  labels,
}: {
  readmePromise: Promise<string | null>
  labels: ReadmeStatusLabels
}): Promise<ReactElement> {
  const rawHtml = await awaitReadmeOrNull(readmePromise)
  return <>{rawHtml === null ? labels.unavailable : labels.loaded}</>
}

export type ReadmeSectionLabels = {
  /** セクション見出し（例: 「README」）。 */
  heading: string
  /** README が無い・取得に失敗したときの案内文（内部エラー文言は出さない・NFR-9）。 */
  unavailable: string
  /** GitHub 側で全文を読むリンクの文言（切り詰め時・取得失敗時の全文導線）。 */
  viewOnGithub: string
  /** `viewOnGithub` リンクが新しいタブで開くことを伝える sr-only 文言。 */
  opensInNewTab: string
}

const GITHUB_HTML_ORIGIN = 'https://github.com/'
const GITHUB_RAW_ORIGIN = 'https://raw.githubusercontent.com/'

/**
 * `htmlUrl`（`https://github.com/{owner}/{repo}`）から README 内の相対リンク・相対画像を
 * 解決する基準 URL を組み立てる。
 *
 * 🟡 `htmlUrl` は DTO の `httpsUrl` 検証（https スキームのみ）を通っているだけでホストは
 * 保証されない。実際の GitHub API は常に `https://github.com/...` を返すため通常はこの分岐に
 * 乗るが、想定外のホストが来た場合は `htmlUrl` 自体を基準にフォールバックする
 * （相対パスの解決精度は落ちるが、危険なスキームは `sanitizeReadmeHtml` 側で弾かれるため安全側）。
 */
function deriveReadmeUrlBases(htmlUrl: string): SanitizeReadmeHtmlOptions {
  if (htmlUrl.startsWith(GITHUB_HTML_ORIGIN)) {
    const repoPath = htmlUrl.slice(GITHUB_HTML_ORIGIN.length)
    return {
      linkBaseUrl: `${GITHUB_HTML_ORIGIN}${repoPath}/blob/HEAD/`,
      imageBaseUrl: `${GITHUB_RAW_ORIGIN}${repoPath}/HEAD/`,
    }
  }
  const base = htmlUrl.endsWith('/') ? htmlUrl : `${htmlUrl}/`
  return { linkBaseUrl: base, imageBaseUrl: base }
}

/** `readmePromise` を待ち、失敗（例外）は null として扱う（NFR-9: 内部エラー文言を出さない）。 */
async function awaitReadmeOrNull(readmePromise: Promise<string | null>): Promise<string | null> {
  try {
    return await readmePromise
  } catch {
    return null
  }
}

/** サニタイズも失敗しうる前提で握る（README 本文の描画失敗で詳細ページ全体を落とさない）。 */
function sanitizeOrNull(
  rawHtml: string,
  htmlUrl: string,
): { html: string; truncated: boolean } | null {
  try {
    return sanitizeReadmeHtml(rawHtml, deriveReadmeUrlBases(htmlUrl))
  } catch {
    return null
  }
}

/**
 * 詳細画面の README セクション（Issue #334 F-4）。
 *
 * 呼び出し元（`app/[locale]/repos/[owner]/[repo]/page.tsx`）が `<Suspense>` で包む前提の
 * async Server Component（`'use client'` を付けない）。`readmePromise` は呼び出し元が
 * **await せずに渡すだけ**（`findDetail` 確定後に作るだけで発火させ、統計表示のブロッキング
 * パスに乗せない・whiteboard round3 lead 裁定）。
 *
 * README が存在しない・private・取得失敗（例外）のいずれでも「本文なし + GitHub で読む
 * リンクのみ」に倒す（内部エラー文言は画面に出さない・NFR-9）。詳細ページ全体を巻き込んで
 * 落とさないよう、取得・サニタイズの両方を try/catch で握る。
 */
export async function ReadmeSection({
  readmePromise,
  htmlUrl,
  labels,
}: {
  readmePromise: Promise<string | null>
  htmlUrl: string
  labels: ReadmeSectionLabels
}): Promise<ReactElement> {
  const rawHtml = await awaitReadmeOrNull(readmePromise)
  const sanitized = rawHtml === null ? null : sanitizeOrNull(rawHtml, htmlUrl)

  return (
    <section aria-labelledby="readme-heading" className="mt-6">
      <h2 id="readme-heading" className="text-lg font-semibold">
        {labels.heading}
      </h2>

      {sanitized === null ? (
        <p className="text-muted-foreground mt-2 text-sm">{labels.unavailable}</p>
      ) : (
        // 🔴 dangerouslySetInnerHTML に渡すのは sanitizeReadmeHtml を経由した文字列のみ
        //    （readme-html.ts の 1 パス変換で script / on* 属性 / javascript: 等を除去済み）。
        // 🟡 `@tailwindcss/typography` は未導入（新規依存の追加禁止・タスクスコープ外）のため
        //    `prose` は使わない。見出し・段落・リストは既定のブラウザスタイルに委ねる。
        <div
          className="mt-2 max-w-none space-y-3 text-sm leading-relaxed break-words"
          dangerouslySetInnerHTML={{ __html: sanitized.html }}
        />
      )}

      <p className="mt-2 text-sm">
        <a
          href={htmlUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="text-primary rounded-sm underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring"
        >
          {labels.viewOnGithub}
          <span className="sr-only">{labels.opensInNewTab}</span>
        </a>
      </p>
    </section>
  )
}
