/**
 * http-retry.mjs — `collect.mjs`（Ecosyste.ms）と `github-stars.mjs`（GitHub API）で
 * 重複していたリトライ骨格・`retryAfterMs` ヘッダ解釈・`USER_AGENT` を切り出した共有モジュール
 * （Issue #950）。
 *
 * 🔴 **API ごとに異なる判定はここに持ち込まない**（意図的な差）。
 * - `collect.mjs`（Ecosyste.ms）: 429 は `retry-after` を尊重してリトライ、それ以外の非 2xx・
 *   fetch 例外もすべてリトライ対象。「即座に失敗（非リトライ）」の概念を持たない。
 * - `github-stars.mjs`（GitHub API）: 404 / 401 / primary rate limit（`x-ratelimit-remaining: 0`）
 *   はリトライせず即座に失敗する。secondary rate limit・5xx・fetch 例外はリトライする。
 *
 * この違いを吸収するのが `shouldRetry` コールバック（DI）である。`withRetry` 自身は
 * 「レスポンス（または fetch 例外）を 1 回受け取り、成功値 / リトライ可否 / 即時失敗を判定して
 * もらい、ループと待機を回すだけ」の骨格しか持たない。
 */

/** GitHub API・Ecosyste.ms の両方へ送る User-Agent（両 API とも同一文字列を要求）。 */
export const USER_AGENT = 'gem-hunter/0.1 (+https://github.com/kai-kou/gem-hunter)'

/** 既定のリトライ回数（初回試行を含まない）。呼び出し側で API ごとに上書きする。 */
export const DEFAULT_MAX_RETRIES = 3

/** 指数バックオフの既定の基準待機時間（ミリ秒）。呼び出し側で API ごとに上書きする。 */
export const DEFAULT_BACKOFF_BASE_MS = 1000

/**
 * 既定の待機実装（テストでは `sleepImpl` で差し替える）。
 * @param {number} ms
 * @returns {Promise<void>}
 */
const defaultSleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

/**
 * `retry-after` レスポンスヘッダを待機ミリ秒へ変換する。
 *
 * 🔴 **秒数表記のみ対応**（`collect.mjs` / `github-stars.mjs` の元実装と同じ挙動）。
 * HTTP-date 形式（例 `Wed, 21 Oct 2026 07:28:00 GMT`）は `Number()` が `NaN` を返すため
 * `null` に倒れ、呼び出し側は指数バックオフへフォールバックする（安全側・見逃しではなく
 * 「秒数として解釈できないので既定の待機を使う」という既定動作）。負値・非数も同様に `null`。
 *
 * @param {{ headers?: { get?: (name: string) => string|null } }} res
 * @returns {number|null}
 */
export function retryAfterMs(res) {
  const raw = res?.headers?.get?.('retry-after')
  if (raw == null) return null
  const seconds = Number(raw)
  if (!Number.isFinite(seconds) || seconds < 0) return null
  return Math.round(seconds * 1000)
}

/**
 * 指数バックオフの待機ミリ秒（`backoffBaseMs * 2 ** attempt`）。
 * @param {number} attempt 0 始まりの試行回数
 * @param {number} backoffBaseMs
 * @returns {number}
 */
function backoffMs(attempt, backoffBaseMs) {
  return backoffBaseMs * 2 ** attempt
}

/**
 * @typedef {Object} RetryOutcome
 * @property {true} [ok] 成功。`value` を `withRetry` の戻り値にする
 * @property {*} [value] `ok: true` のときの成功値
 * @property {boolean} [retryable] `ok` が無いとき必須。`false` なら即座に失敗として throw する
 * @property {string} [message] 失敗理由（リトライ継続時は次の待機ログに、即時失敗時は Error message に使う）
 * @property {number} [waitMs] このラウンドの待機を上書きする（`retry-after` 等）
 * @property {object} [extra] 即時失敗の Error に付与する追加プロパティ（`rateLimited` / `authError` 等）
 */

/**
 * HTTP フェッチを `maxRetries` 回までリトライする汎用ヘルパー（Issue #950）。
 *
 * API ごとの判定差は `shouldRetry` コールバックに閉じ込める。`fetchImpl` が例外を投げた場合
 * （ネットワークエラー等）は `shouldRetry` を呼ばず **常にリトライ対象** として扱う
 * （`collect.mjs` / `github-stars.mjs` とも fetch 例外は無条件リトライだったため、この骨格に
 * 共通判定として引き上げてよい・両ファイルの元実装と同じ挙動）。
 *
 * @param {Object} args
 * @param {string} args.url
 * @param {typeof fetch} args.fetchImpl 既定なし（呼び出し側が必ず渡す。テストではスタブ）
 * @param {Record<string,string>} [args.headers]
 * @param {number} [args.maxRetries] 既定 `DEFAULT_MAX_RETRIES`
 * @param {(ms:number)=>Promise<void>} [args.sleepImpl] 既定は実待機（テストで差し替える）
 * @param {number} [args.backoffBaseMs] 既定 `DEFAULT_BACKOFF_BASE_MS`
 * @param {(res: Response) => (RetryOutcome | Promise<RetryOutcome>)} args.shouldRetry
 *   レスポンスを 1 回受け取り、成功値・リトライ可否・即時失敗を判定する（API ごとの差の注入点）。
 *   `res.json()` 等の非同期読み取りが要るときは async 関数として渡してよい。
 * @param {(message:string, extra:object)=>void} [args.onNonRetryable]
 *   `shouldRetry` が `retryable: false` を返したときの通知（省略可・ログ用途）
 * @returns {Promise<{value:*, attempts:number}>} `attempts` はリトライを含む実リクエスト数
 * @throws {Error & {attempts:number, [key:string]:*}}
 *   リトライ上限まで失敗した場合、または `shouldRetry` が `retryable:false` を返した場合
 *   （後者は `extra` のプロパティを Error にコピーする）
 */
export async function withRetry({
  url,
  fetchImpl,
  headers,
  maxRetries = DEFAULT_MAX_RETRIES,
  sleepImpl = defaultSleep,
  backoffBaseMs = DEFAULT_BACKOFF_BASE_MS,
  shouldRetry,
  onNonRetryable,
}) {
  if (typeof shouldRetry !== 'function') {
    throw new TypeError('shouldRetry には判定関数を指定してください（依存性注入・API ごとの差の注入点）')
  }
  if (typeof fetchImpl !== 'function') {
    throw new TypeError('fetchImpl が利用できません（テストではスタブを渡してください）')
  }

  let attempts = 0
  let lastMessage = '原因不明'

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    attempts++
    let waitMs = backoffMs(attempt, backoffBaseMs)

    let res
    try {
      res = await fetchImpl(url, { headers })
    } catch (err) {
      // fetch 例外は shouldRetry を経由せず常にリトライ対象（両 API の元実装と同じ挙動）
      lastMessage = err instanceof Error ? err.message : String(err)
      if (attempt < maxRetries) await sleepImpl(waitMs)
      continue
    }

    const outcome = await shouldRetry(res)

    if (outcome?.ok) {
      return { value: outcome.value, attempts }
    }

    lastMessage = outcome?.message ?? lastMessage

    if (outcome?.retryable === false) {
      const error = new Error(lastMessage)
      error.attempts = attempts
      if (outcome.extra) Object.assign(error, outcome.extra)
      onNonRetryable?.(lastMessage, outcome.extra ?? {})
      throw error
    }

    waitMs = outcome?.waitMs ?? waitMs
    // 最後の試行で失敗したときは待たずに抜ける
    if (attempt < maxRetries) await sleepImpl(waitMs)
  }

  const error = new Error(lastMessage)
  error.attempts = attempts
  throw error
}
