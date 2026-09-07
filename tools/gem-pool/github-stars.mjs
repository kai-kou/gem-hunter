/**
 * github-stars.mjs — 「今日の Gem」候補の star 数を GitHub API で取り直す層（Issue #310）。
 *
 * 背景: `daily-digest.json` の `stars` はこれまで Ecosyste.ms が独自クロールした値で、
 * 銘柄ごとに `last_synced_at` が大きくばらつく（サンプル 20 件中 6 件が 700 日超・
 * 最大 2.7 年前）。詳細画面は GitHub API のライブ値を出すため、一覧と詳細で数字が
 * 食い違って見える。本モジュールは **候補プール全体（数万件）ではなく、
 * `daily-digest.json` に載る件数（既定 300 件）だけ** を対象に、生成時点の
 * `stargazers_count` を GitHub API から取り直す（Gem Index の並び順・レジストリ別
 * シャードは対象外・Issue #310 のスコープ注記）。
 *
 * 設計は `collect.mjs`（Ecosyste.ms 収集層）の様式を踏襲する:
 * - `fetchImpl` / `sleepImpl` は DI（テストでネットワークを叩かない）
 * - 1 件の失敗で全体を止めない（**失敗したエントリは Ecosyste.ms 由来の旧値を保持してスキップ**）
 * - リトライは指数バックオフ + `retry-after` 尊重
 *
 * Ecosyste.ms 層と違う点が 1 つだけある: **primary rate limit の枯渇を検知したら、
 * 以降の候補は一切リクエストせず即座にスキップへ回す**。GitHub の primary rate limit は
 * `x-ratelimit-remaining: 0` で明示され、リセットまで待っても数十分単位になりうるため、
 * 残り候補 1 件ずつにリトライを試みるのは時間の無駄かつ相手サーバへの負荷になる。
 *
 * リトライ骨格・`retryAfterMs` ヘッダ解釈・`USER_AGENT` は `http-retry.mjs`（Issue #950）に
 * 切り出し済み。この層に残るのは GitHub 固有の判定（404 / 401 / primary rate limit の
 * 即時失敗・secondary rate limit の `retry-after` 尊重）だけ。
 */
import { USER_AGENT, retryAfterMs, withRetry } from './http-retry.mjs'

/** GitHub REST API のベース URL（テストでは差し替えない・`fetchImpl` 側で完結させる）。 */
export const GITHUB_API_ORIGIN = 'https://api.github.com'

/** 既定のリトライ回数（初回試行を含まない）。Ecosyste.ms 層より小さくする（300 件規模の直列実行のため）。 */
export const DEFAULT_MAX_RETRIES = 2

/** 指数バックオフの基準待機時間（ミリ秒）。 */
const BACKOFF_BASE_MS = 500

// GitHub API に送る User-Agent（GitHub は必須ヘッダとして要求する。`http-retry.mjs` の値を再輸出）
export { USER_AGENT }

/**
 * `owner/repo` 形式を分解する。スラッシュがちょうど 1 つでない、どちらかが空文字のときは
 * `null`（呼び出し元はネットワークへ行かず即座に失敗として扱う）。
 *
 * @param {unknown} repositoryFullName
 * @returns {{owner:string, repo:string}|null}
 */
export function parseRepositoryFullName(repositoryFullName) {
  if (typeof repositoryFullName !== 'string') return null
  const parts = repositoryFullName.split('/')
  if (parts.length !== 2) return null
  const [owner, repo] = parts
  if (owner.length === 0 || repo.length === 0) return null
  return { owner, repo }
}

/** `GET /repos/{owner}/{repo}` の URL を組み立てる。 */
function buildRepoUrl(owner, repo) {
  return `${GITHUB_API_ORIGIN}/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}`
}

/** テストでは `sleepImpl` を必ず注入するため、実待機はここでしか使わない（`withRetry` の既定と同じ実装）。 */
const defaultSleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

/**
 * primary rate limit を使い切ったレスポンスかどうか（`x-ratelimit-remaining: 0`）。
 * GitHub 公式: 403/429 のどちらでも返りうるため status では判定しない。
 */
function isRateLimitExhausted(res) {
  return res?.headers?.get?.('x-ratelimit-remaining') === '0'
}

/**
 * 1 件のリポジトリの `stargazers_count` を取得する。
 *
 * - `404`（リポジトリの改名・削除・非公開化）はリトライしない（即座に失敗）。
 * - `401`（トークン不正・失効）もリトライしない（`error.authError = true` を立てて即座に失敗・
 *   恒久的な設定誤りでリトライしても結果は変わらないため。PR #949 セルフレビュー NIT 指摘）。
 * - primary rate limit 枯渇はリトライしない（`error.rateLimited = true` を立てて即座に失敗）。
 * - それ以外の失敗（5xx・secondary rate limit・network error）は `maxRetries` 回まで
 *   指数バックオフでリトライする（`retry-after` があれば優先）。
 *
 * @param {Object} args
 * @param {string} args.repositoryFullName `owner/repo`
 * @param {typeof fetch} args.fetchImpl
 * @param {string|null} [args.token] GitHub API トークン（省略時は未認証・レート枠が小さい）
 * @param {number} [args.maxRetries]
 * @param {(ms:number)=>Promise<void>} [args.sleepImpl]
 * @returns {Promise<{stars:number, attempts:number}>}
 * @throws {Error & {attempts:number, rateLimited?:boolean, authError?:boolean}}
 */
export async function fetchRepoStars({
  repositoryFullName,
  fetchImpl,
  token = null,
  maxRetries = DEFAULT_MAX_RETRIES,
  sleepImpl = defaultSleep,
}) {
  const parsed = parseRepositoryFullName(repositoryFullName)
  if (parsed === null) {
    const error = new Error(`repositoryFullName の形式が不正です: ${String(repositoryFullName)}`)
    error.attempts = 0
    throw error
  }
  if (typeof fetchImpl !== 'function') {
    throw new TypeError('fetchImpl が利用できません（テストではスタブを渡してください）')
  }

  const url = buildRepoUrl(parsed.owner, parsed.repo)
  const headers = {
    'user-agent': USER_AGENT,
    accept: 'application/vnd.github+json',
    'x-github-api-version': '2022-11-28',
  }
  if (typeof token === 'string' && token.length > 0) {
    headers.authorization = `Bearer ${token}`
  }

  try {
    const { value, attempts } = await withRetry({
      url,
      fetchImpl,
      headers,
      maxRetries,
      sleepImpl,
      backoffBaseMs: BACKOFF_BASE_MS,
      shouldRetry: async (res) => {
        if (res?.ok) {
          const body = await res.json()
          const stars = body?.stargazers_count
          if (Number.isFinite(stars) && stars >= 0) {
            return { ok: true, value: stars }
          }
          return {
            retryable: true,
            message: `レスポンスに stargazers_count が含まれていません（${repositoryFullName}）`,
          }
        }
        if (res?.status === 404) {
          return {
            retryable: false,
            message: `リポジトリが見つかりません（${repositoryFullName}）`,
            // `terminal` は withRetry を経由した呼び出し元（下の catch）が「即時失敗」と
            // 「リトライ上限到達」を区別するための内部マーカー（呼び出し元でメッセージの
            // 二重ラップを避けるためだけに使う。tests が参照する契約ではない）。
            extra: { rateLimited: false, authError: false, terminal: true },
          }
        }
        if (res?.status === 401) {
          // トークン不正・失効は恒久的な設定誤りで、リトライしても結果は変わらない（404 と同様に即座に失敗）。
          return {
            retryable: false,
            message: `GitHub API の認証に失敗しました（401・トークン不正の可能性・${repositoryFullName}）`,
            extra: { rateLimited: false, authError: true, terminal: true },
          }
        }
        if (res?.status === 403 || res?.status === 429) {
          if (isRateLimitExhausted(res)) {
            return {
              retryable: false,
              message: `GitHub API のレート制限に達しました（${repositoryFullName}）`,
              extra: { rateLimited: true, authError: false, terminal: true },
            }
          }
          return {
            retryable: true,
            message: `HTTP ${res.status}（secondary rate limit の可能性・${repositoryFullName}）`,
            waitMs: retryAfterMs(res) ?? undefined,
          }
        }
        return { retryable: true, message: `HTTP ${res?.status ?? '不明'}（${repositoryFullName}）` }
      },
    })
    return { stars: value, attempts }
  } catch (err) {
    if (err.terminal) {
      delete err.terminal
      throw err
    }
    const error = new Error(`star 数の取得に失敗しました（${repositoryFullName}）: ${err.message}`)
    error.attempts = err.attempts
    throw error
  }
}

/**
 * 候補配列の `stars` を GitHub API で取り直す。
 *
 * 🔴 **失敗しても全体を止めない（完了条件 2）**: 個別リポジトリの取得に失敗したエントリは
 * `stars` を書き換えず、元の値（Ecosyste.ms 由来）のまま `records` へ含める。
 * primary rate limit の枯渇を検知した以降は、残り候補への **ネットワークリクエストを行わず**
 * 即座にスキップへ回す（`failures` には理由付きで記録するので、どこから枯渇したか追跡できる）。
 *
 * @param {Object} args
 * @param {ReadonlyArray<{repositoryFullName:string, stars:number}>} args.candidates
 * @param {typeof fetch} args.fetchImpl
 * @param {string|null} [args.token]
 * @param {number} [args.maxRetries]
 * @param {(ms:number)=>Promise<void>} [args.sleepImpl]
 * @param {(info:{repositoryFullName:string, ok:boolean, stars?:number, message?:string, rateLimited?:boolean, authError?:boolean})=>void} [args.onProgress]
 * @returns {Promise<{
 *   records: object[],
 *   requestCount: number,
 *   refreshedCount: number,
 *   failures: {repositoryFullName:string, message:string}[],
 *   rateLimited: boolean,
 *   authError: boolean,
 * }>}
 */
export async function refreshStars({
  candidates,
  fetchImpl,
  token = null,
  maxRetries = DEFAULT_MAX_RETRIES,
  sleepImpl = defaultSleep,
  onProgress,
}) {
  if (!Array.isArray(candidates)) {
    throw new TypeError('candidates には配列を指定してください')
  }

  const records = []
  const failures = []
  let requestCount = 0
  let rateLimited = false
  // 🔴 401（トークン不正・失効）はレート制限と同じ「以降の候補も恒久的に失敗する」性質を持つため、
  // rateLimited と同様にバッチを早期スキップへ倒す（残り候補分の無駄なリクエストと待機を避ける・
  // PR #949 セルフレビュー NIT 指摘）。原因が別なので rateLimited とは別フラグで報告する。
  let authError = false
  let refreshedCount = 0

  for (const candidate of candidates) {
    if (rateLimited || authError) {
      records.push(candidate)
      failures.push({
        repositoryFullName: candidate?.repositoryFullName ?? '(unknown)',
        message: rateLimited
          ? 'GitHub API のレート制限に達したためスキップしました（既存値を保持）'
          : 'GitHub API の認証エラー（401）が続いているためスキップしました（既存値を保持）',
      })
      continue
    }

    try {
      const { stars, attempts } = await fetchRepoStars({
        repositoryFullName: candidate?.repositoryFullName,
        fetchImpl,
        token,
        maxRetries,
        sleepImpl,
      })
      requestCount += attempts
      refreshedCount++
      records.push({ ...candidate, stars })
      onProgress?.({ repositoryFullName: candidate?.repositoryFullName, ok: true, stars })
    } catch (err) {
      requestCount += err?.attempts ?? 0
      const message = err instanceof Error ? err.message : String(err)
      failures.push({ repositoryFullName: candidate?.repositoryFullName ?? '(unknown)', message })
      records.push(candidate)
      if (err?.rateLimited) rateLimited = true
      if (err?.authError) authError = true
      onProgress?.({
        repositoryFullName: candidate?.repositoryFullName,
        ok: false,
        message,
        rateLimited: !!err?.rateLimited,
        authError: !!err?.authError,
      })
    }
  }

  return { records, requestCount, refreshedCount, failures, rateLimited, authError }
}
