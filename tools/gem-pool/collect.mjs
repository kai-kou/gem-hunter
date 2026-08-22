/**
 * collect.mjs — Ecosyste.ms の一覧 API から候補プールを収集する層（`SP-17` / Issue #387）。
 *
 * 決定の正本は `docs/02_requirements/open-questions.md` の `D-36` / `D-37`、
 * 実測記録は `docs/01_research/data/20260822-dependency-data-sources.md` §4。
 *
 * この層の責務は **「取ってきて、投影関数に渡して、配列で返す」だけ**。
 * ランク付け・dedupe・汚染フィルタ（star の 3 状態判定を含む）は
 * `pipeline.mjs` 側の責務であり、ここには持ち込まない。
 *
 * 設計上の約束:
 * - 投影関数 `project` は **依存性注入**（この層は投影の中身を知らない）
 * - 生 JSON をため込まない（1 ページ 100MB 級になる実測がある。ページごとに投影して push する）
 * - `console.log` を出さない（進捗は `onPage` / `onRegistryDone` コールバックで通知する）
 * - 複数レジストリは **逐次**（Ecosyste.ms への同時接続を増やさない）
 */

/** Ecosyste.ms の registries API のベース URL */
export const API_BASE = 'https://packages.ecosyste.ms/api/v1/registries'

/** polite pool（連絡先付き UA）で 15,000 req/時。匿名は 5,000 req/時 */
export const USER_AGENT = 'gem-hunter/0.1 (+https://github.com/kai-kou/gem-hunter)'

/** 一覧 API は per_page=1000 が通る（実測・2026-08-22） */
export const DEFAULT_PER_PAGE = 1000

/**
 * 一覧 API が受け付ける `per_page` の上限（実測・2026-08-22）。
 *
 * `per_page=1500` を投げても **エラーにならず 200 で 1000 件だけ返る**。
 * 上限超過をそのまま投げると「返却件数 < 要求件数」が常に成立してしまうため、
 * 要求値はここで切り詰める（`clampPerPage`）。
 */
export const MAX_PER_PAGE = 1000

/**
 * 1 ページのレスポンスとして受け入れる最大バイト数（256 MiB）。
 *
 * `res.json()` は全量をメモリへ載せるため、相手側の不具合で数 GB が返ると生成ホストが
 * OOM で落ち、日次のプール再生成そのものが止まる。`content-length` が上限を超えるページは
 * 取得失敗として扱い、既存のリトライ／`failures` の経路に乗せる。
 *
 * ⚠️ `content-length` が付かない（chunked）レスポンスには追加の対策をしない
 * （ストリーム読みで逐次カウントする作り替えは本スプリントのスコープ外）。
 */
export const MAX_RESPONSE_BYTES = 256 * 1024 * 1024

/** 既定のリトライ回数（初回試行を含まない） */
const DEFAULT_MAX_RETRIES = 3

/** 指数バックオフの基準待機時間（ミリ秒） */
const BACKOFF_BASE_MS = 1000

/**
 * 既定の待機実装（テストでは `sleepImpl` で差し替える）。
 * @param {number} ms
 * @returns {Promise<void>}
 */
const defaultSleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

/**
 * 1 ページぶんのリクエスト URL を組み立てる（この層の内部実装）。
 *
 * 外部からは `collectRegistry` / `collectAll` 経由でしか使わないため export しない
 * （URL の形はテストでも `fetchImpl` スタブが受け取った URL から検証する）。
 *
 * @param {string} registry レジストリ名
 * @param {number} page 1 始まりのページ番号
 * @param {number} perPage 1 ページあたりの件数
 * @returns {string}
 */
function buildPageUrl(registry, page, perPage) {
  const url = new URL(`${API_BASE}/${encodeURIComponent(registry)}/packages`)
  url.searchParams.set('sort', 'dependent_packages_count')
  url.searchParams.set('order', 'desc')
  url.searchParams.set('per_page', String(perPage))
  url.searchParams.set('page', String(page))
  return url.toString()
}

/**
 * `retry-after` ヘッダ（秒）を待機ミリ秒へ変換する。解釈できなければ null。
 * @param {{ headers?: { get?: (name: string) => string|null } }} res
 * @returns {number|null}
 */
function retryAfterMs(res) {
  const raw = res?.headers?.get?.('retry-after')
  if (raw == null) return null
  const seconds = Number(raw)
  if (!Number.isFinite(seconds) || seconds < 0) return null
  return Math.round(seconds * 1000)
}

/**
 * `content-length` ヘッダをバイト数として読む。無い・解釈できないときは null。
 * @param {{ headers?: { get?: (name: string) => string|null } }} res
 * @returns {number|null}
 */
function contentLengthBytes(res) {
  const raw = res?.headers?.get?.('content-length')
  if (raw == null) return null
  const bytes = Number(raw)
  if (!Number.isFinite(bytes) || bytes < 0) return null
  return bytes
}

/**
 * 要求された `perPage` を API 上限（`MAX_PER_PAGE`）で切り詰める。
 *
 * 例外にはしない（上限超過は「無効な設定」ではなく「そのままでは 1 ページ目で最終ページと
 * 誤判定される危険な設定」であり、切り詰めれば正しく動く）。切り詰めたことは `onWarn` で伝える。
 *
 * @param {number|undefined} perPage
 * @param {((message:string)=>void)|undefined} onWarn
 * @returns {number|undefined} 切り詰め後の値（不正値はそのまま返し、呼び出し側の検証に委ねる）
 */
function clampPerPage(perPage, onWarn) {
  if (typeof perPage !== 'number' || !Number.isFinite(perPage) || perPage <= MAX_PER_PAGE) {
    return perPage
  }
  onWarn?.(
    `per_page=${perPage} は API 上限 ${MAX_PER_PAGE} を超えるため ${MAX_PER_PAGE} に切り詰めました`,
  )
  return MAX_PER_PAGE
}

/**
 * 指数バックオフの待機ミリ秒（`1000 * 2 ** attempt`）。
 * @param {number} attempt 0 始まりの試行回数
 * @returns {number}
 */
function backoffMs(attempt) {
  return BACKOFF_BASE_MS * 2 ** attempt
}

/**
 * 1 ページを取得する（HTTP エラー・fetch 例外を `maxRetries` 回までリトライする）。
 * 429 は `retry-after`（秒）を尊重し、無ければ指数バックオフへフォールバックする。
 * `content-length` が `MAX_RESPONSE_BYTES` を超えるページは本文を読まずに失敗扱いにする。
 *
 * @returns {Promise<{payload: unknown, attempts: number}>} attempts はリトライを含む実リクエスト数
 */
async function fetchPageWithRetry({ url, fetchImpl, maxRetries, sleepImpl }) {
  let attempts = 0
  let lastMessage = '原因不明'

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    attempts++
    let waitMs = backoffMs(attempt)
    try {
      const res = await fetchImpl(url, {
        headers: { 'user-agent': USER_AGENT, accept: 'application/json' },
      })
      if (res?.ok) {
        const bytes = contentLengthBytes(res)
        // content-length が無いときは判定しない（ストリーム読みへの作り替えはスコープ外）
        if (bytes !== null && bytes > MAX_RESPONSE_BYTES) {
          lastMessage = `レスポンスが大きすぎます（content-length=${bytes} > ${MAX_RESPONSE_BYTES}）`
        } else {
          return { payload: await res.json(), attempts }
        }
      } else {
        lastMessage = `HTTP ${res?.status ?? '不明'}`
        if (res?.status === 429) {
          waitMs = retryAfterMs(res) ?? waitMs
        }
      }
    } catch (err) {
      lastMessage = err instanceof Error ? err.message : String(err)
    }
    // 最後の試行で失敗したときは待たずに抜ける
    if (attempt < maxRetries) await sleepImpl(waitMs)
  }

  const error = new Error(`ページ取得に失敗しました（${url}）: ${lastMessage}`)
  error.attempts = attempts
  throw error
}

/**
 * 1 レジストリぶんを被依存数降順で quota 件まで収集し、投影済みレコード配列を返す。
 *
 * 🔴 **`quota` は「取得件数（fetch した生パッケージ数）」の枠であり、投影後レコード数の枠ではない。**
 * `D-37` の「各レジストリから同数を取る固定枠」は取得件数の固定枠を指すため、
 * `project` が `null` を返して捨てられた分を **ページを追加してまで埋め直さない**
 * （埋め直すとレジストリごとに巡回深度が変わり、成層化の前提が崩れる）。
 * 投影後レコードが `quota` を超えることもない（生を quota 件で切ってから投影するため）。
 *
 * ページングは次のいずれかで停止する:
 * 1. 取得件数が `quota` に達した
 * 2. 空配列が返った
 * 3. 返却件数が **1 ページ目で実測したページサイズ** を下回った（＝最終ページ）
 *
 * 🔴 停止判定に要求値 `perPage` を使わない。Ecosyste.ms は `per_page` を 1000 で頭打ちにする
 * （`per_page=1500` でも 200 で 1000 件）ため、要求値と比べると **1 ページ目で必ず最終ページと
 * 誤判定** し、各レジストリ 1000 件しか取れないまま正常終了してしまう。実測値を基準にすれば、
 * サーバ側が上限を変えても正しくページをめくれる（`perPage` 自体も `MAX_PER_PAGE` で切り詰める）。
 *
 * @param {Object} args
 * @param {string} args.registry      レジストリ名（例 `npmjs.org`）
 * @param {number} args.quota         取得上限件数（例 15000。投影後件数ではなく取得件数の枠）
 * @param {number} [args.perPage]     既定 1000（`MAX_PER_PAGE` を超える値は切り詰める）
 * @param {typeof fetch} [args.fetchImpl]  既定 globalThis.fetch（テストで差し替える）
 * @param {(raw:unknown, registry:string)=>(object|null)} args.project  投影関数（DI・`pipeline.mjs` が持つ）
 * @param {(info:{registry:string,page:number,fetched:number,kept:number,elapsedMs:number})=>void} [args.onPage]
 * @param {(message:string)=>void} [args.onWarn] 警告通知（`perPage` の切り詰め等）
 * @param {number} [args.maxRetries]  既定 3（初回試行を含まないリトライ回数）
 * @param {(ms:number)=>Promise<void>} [args.sleepImpl] リトライ待機（テストで差し替える）
 * @returns {Promise<{registry:string, records:object[], requestCount:number, fetchedCount:number}>}
 *   `requestCount` はリトライを含む実リクエスト数（レート枠の把握に使う）
 * @throws {Error} リトライ上限まで失敗した場合、または API が配列以外を返した場合
 *   （`error.requestCount` / `error.fetchedCount` に中断時点の実績を載せる）
 */
export async function collectRegistry({
  registry,
  quota,
  perPage = DEFAULT_PER_PAGE,
  fetchImpl = globalThis.fetch,
  project,
  onPage,
  onWarn,
  maxRetries = DEFAULT_MAX_RETRIES,
  sleepImpl = defaultSleep,
}) {
  if (typeof registry !== 'string' || registry === '') {
    throw new TypeError('registry には空でない文字列を指定してください')
  }
  if (!Number.isFinite(quota) || quota <= 0) {
    throw new TypeError(`quota には正の数を指定してください（受け取った値: ${quota}）`)
  }
  if (!Number.isFinite(perPage) || perPage <= 0) {
    throw new TypeError(`perPage には正の数を指定してください（受け取った値: ${perPage}）`)
  }
  if (typeof project !== 'function') {
    throw new TypeError('project には投影関数を指定してください（依存性注入）')
  }
  if (typeof fetchImpl !== 'function') {
    throw new TypeError('fetchImpl が利用できません（Node 22+ / テストではスタブを渡してください）')
  }

  const effectivePerPage = clampPerPage(perPage, onWarn)

  /** @type {object[]} */
  const records = []
  let page = 1
  let requestCount = 0
  let fetchedCount = 0
  /** 1 ページ目で実測したページサイズ（停止判定の基準・要求値は使わない） */
  let observedPageSize = null

  try {
    while (fetchedCount < quota) {
      const startedAt = Date.now()
      const url = buildPageUrl(registry, page, effectivePerPage)
      const { payload, attempts } = await fetchPageWithRetry({
        url,
        fetchImpl,
        maxRetries,
        sleepImpl,
      })
      requestCount += attempts

      if (!Array.isArray(payload)) {
        throw new Error(`API が配列以外を返しました（${url}）`)
      }
      if (payload.length === 0) break
      // 1 ページ目の実測件数を以降の「満員ページ」の基準にする
      if (observedPageSize === null) observedPageSize = payload.length

      // quota は取得件数の枠なので、はみ出す分はここで切る（生配列は保持しない）
      const takeCount = Math.min(payload.length, quota - fetchedCount)
      let kept = 0
      for (let i = 0; i < takeCount; i++) {
        const projected = project(payload[i], registry)
        if (projected != null) {
          records.push(projected)
          kept++
        }
      }
      fetchedCount += takeCount

      onPage?.({
        registry,
        page,
        fetched: takeCount,
        kept,
        elapsedMs: Date.now() - startedAt,
      })

      if (payload.length < observedPageSize) break // 最終ページ
      page++
    }
  } catch (err) {
    // 中断時点の実績を添えて投げ直す（collectAll がレート枠の集計に使う）
    err.requestCount = requestCount + (err.attempts ?? 0)
    err.fetchedCount = fetchedCount
    err.message = `[${registry}] ${err.message}`
    throw err
  }

  return { registry, records, requestCount, fetchedCount }
}

/**
 * 複数レジストリを逐次で収集する（Ecosyste.ms への同時接続を増やさない）。
 *
 * 1 レジストリの失敗で全体を落とさず、`failures` に記録して次へ進む
 * （12 レジストリのうち 1 つが落ちても残り 11 のプールは価値があるため）。
 *
 * @param {Object} args
 * @param {ReadonlyArray<string|{name:string}>} args.registries レジストリ名、または `{ name }` を持つ定義の配列
 * @param {number} args.quota  1 レジストリあたりの取得上限件数（固定枠）
 * @param {number} [args.perPage]
 * @param {typeof fetch} [args.fetchImpl]
 * @param {(raw:unknown, registry:string)=>(object|null)} args.project
 * @param {(info:{registry:string,page:number,fetched:number,kept:number,elapsedMs:number})=>void} [args.onPage]
 * @param {(info:{registry:string,ok:boolean,kept:number,fetched:number,requestCount:number,message?:string})=>void} [args.onRegistryDone]
 * @param {(message:string)=>void} [args.onWarn] 警告通知（`perPage` の切り詰め等）
 * @param {number} [args.maxRetries]
 * @param {(ms:number)=>Promise<void>} [args.sleepImpl]
 * @returns {Promise<{byRegistry: Map<string, object[]>, requestCount:number, fetchedCount:number, failures:{registry:string,message:string}[]}>}
 */
export async function collectAll({
  registries,
  quota,
  perPage,
  fetchImpl,
  project,
  onPage,
  onRegistryDone,
  onWarn,
  maxRetries,
  sleepImpl,
}) {
  if (!Array.isArray(registries)) {
    throw new TypeError('registries には配列を指定してください')
  }

  // 全レジストリで同じ値を使うので、警告はここで 1 回だけ出す（各レジストリで再警告しない）
  const effectivePerPage = clampPerPage(perPage, onWarn)

  /** @type {Map<string, object[]>} */
  const byRegistry = new Map()
  /** @type {{registry:string,message:string}[]} */
  const failures = []
  let requestCount = 0
  let fetchedCount = 0

  for (const entry of registries) {
    const registry = typeof entry === 'string' ? entry : entry?.name
    try {
      const result = await collectRegistry({
        registry,
        quota,
        perPage: effectivePerPage,
        fetchImpl,
        project,
        onPage,
        onWarn,
        maxRetries,
        sleepImpl,
      })
      byRegistry.set(registry, result.records)
      requestCount += result.requestCount
      fetchedCount += result.fetchedCount
      onRegistryDone?.({
        registry,
        ok: true,
        kept: result.records.length,
        fetched: result.fetchedCount,
        requestCount: result.requestCount,
      })
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      // 失敗レジストリで消費したリクエストもレート枠には効くので計上する
      requestCount += err?.requestCount ?? 0
      fetchedCount += err?.fetchedCount ?? 0
      failures.push({ registry: String(registry), message })
      onRegistryDone?.({
        registry: String(registry),
        ok: false,
        kept: 0,
        fetched: err?.fetchedCount ?? 0,
        requestCount: err?.requestCount ?? 0,
        message,
      })
    }
  }

  return { byRegistry, requestCount, fetchedCount, failures }
}
