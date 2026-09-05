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
 */

/** GitHub REST API のベース URL（テストでは差し替えない・`fetchImpl` 側で完結させる）。 */
export const GITHUB_API_ORIGIN = 'https://api.github.com'

/** 既定のリトライ回数（初回試行を含まない）。Ecosyste.ms 層より小さくする（300 件規模の直列実行のため）。 */
export const DEFAULT_MAX_RETRIES = 2

/** 指数バックオフの基準待機時間（ミリ秒）。 */
const BACKOFF_BASE_MS = 500

/** GitHub API に送る User-Agent（GitHub は必須ヘッダとして要求する）。 */
export const USER_AGENT = 'gem-hunter/0.1 (+https://github.com/kai-kou/gem-hunter)'

/**
 * 既定の待機実装（テストでは `sleepImpl` で差し替える）。
 * @param {number} ms
 * @returns {Promise<void>}
 */
const defaultSleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

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

/** `retry-after` ヘッダ（秒）を待機ミリ秒へ変換する。解釈できなければ null。 */
function retryAfterMs(res) {
  const raw = res?.headers?.get?.('retry-after')
  if (raw == null) return null
  const seconds = Number(raw)
  if (!Number.isFinite(seconds) || seconds < 0) return null
  return Math.round(seconds * 1000)
}

/**
 * primary rate limit を使い切ったレスポンスかどうか（`x-ratelimit-remaining: 0`）。
 * GitHub 公式: 403/429 のどちらでも返りうるため status では判定しない。
 */
function isRateLimitExhausted(res) {
  return res?.headers?.get?.('x-ratelimit-remaining') === '0'
}

function backoffMs(attempt) {
  return BACKOFF_BASE_MS * 2 ** attempt
}

/**
 * 1 件のリポジトリの `stargazers_count` を取得する。
 *
 * - `404`（リポジトリの改名・削除・非公開化）はリトライしない（即座に失敗）。
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
 * @throws {Error & {attempts:number, rateLimited?:boolean}}
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

  let attempts = 0
  let lastMessage = '原因不明'

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    attempts++
    let waitMs = backoffMs(attempt)
    let rateLimited = false
    let notFound = false
    try {
      const res = await fetchImpl(url, { headers })
      if (res?.ok) {
        const body = await res.json()
        const stars = body?.stargazers_count
        if (Number.isFinite(stars) && stars >= 0) {
          return { stars, attempts }
        }
        lastMessage = `レスポンスに stargazers_count が含まれていません（${repositoryFullName}）`
      } else if (res?.status === 404) {
        lastMessage = `リポジトリが見つかりません（${repositoryFullName}）`
        notFound = true
      } else if (res?.status === 403 || res?.status === 429) {
        if (isRateLimitExhausted(res)) {
          lastMessage = `GitHub API のレート制限に達しました（${repositoryFullName}）`
          rateLimited = true
        } else {
          lastMessage = `HTTP ${res.status}（secondary rate limit の可能性・${repositoryFullName}）`
          waitMs = retryAfterMs(res) ?? waitMs
        }
      } else {
        lastMessage = `HTTP ${res?.status ?? '不明'}（${repositoryFullName}）`
      }
    } catch (err) {
      lastMessage = err instanceof Error ? err.message : String(err)
    }

    if (notFound || rateLimited) {
      const error = new Error(lastMessage)
      error.attempts = attempts
      error.rateLimited = rateLimited
      throw error
    }
    // 最後の試行で失敗したときは待たずに抜ける
    if (attempt < maxRetries) await sleepImpl(waitMs)
  }

  const error = new Error(`star 数の取得に失敗しました（${repositoryFullName}）: ${lastMessage}`)
  error.attempts = attempts
  throw error
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
 * @param {(info:{repositoryFullName:string, ok:boolean, stars?:number, message?:string, rateLimited?:boolean})=>void} [args.onProgress]
 * @returns {Promise<{
 *   records: object[],
 *   requestCount: number,
 *   refreshedCount: number,
 *   failures: {repositoryFullName:string, message:string}[],
 *   rateLimited: boolean,
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
  let refreshedCount = 0

  for (const candidate of candidates) {
    if (rateLimited) {
      records.push(candidate)
      failures.push({
        repositoryFullName: candidate?.repositoryFullName ?? '(unknown)',
        message: 'GitHub API のレート制限に達したためスキップしました（既存値を保持）',
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
      onProgress?.({
        repositoryFullName: candidate?.repositoryFullName,
        ok: false,
        message,
        rateLimited: !!err?.rateLimited,
      })
    }
  }

  return { records, requestCount, refreshedCount, failures, rateLimited }
}
