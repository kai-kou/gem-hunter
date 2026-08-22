/**
 * collect.mjs — Ecosyste.ms REST API からレジストリ別に生パッケージ一覧を取得する。
 *
 * ここでは「取ってくるだけ」に徹する（正規化・フィルタ・順位計算は pipeline.mjs の役割・
 * SP-17 契約 §4）。1 レジストリの障害で他 11 レジストリの収集まで巻き込んで落とさない
 * ことを最優先にしている（`NFR-8` の思想）。
 */

import { DEFAULT_PER_PAGE, DEFAULT_QUOTA, REGISTRIES } from './registries.mjs'

export const API_BASE = 'https://packages.ecosyste.ms/api/v1/registries'
export const USER_AGENT = 'gem-hunter/0.1 (+https://github.com/kai-kou/gem-hunter)'

// 429 / 5xx（および fetch 自体の失敗）に対する指数バックオフの上限回数と初期待機時間。
// 1s → 2s → 4s の 3 回リトライ（契約 §3）。
const MAX_RETRIES = 3
const BASE_BACKOFF_MS = 1000

// 匿名アクセスのレート枠（5,000 req/時）を守るための、1 リクエストごとの既定スリープ。
const REQUEST_INTERVAL_MS = 250

function defaultSleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function buildPageUrl(registry, page, perPage) {
  const url = new URL(`${API_BASE}/${registry.name}/packages`)
  url.searchParams.set('sort', 'dependent_packages_count')
  url.searchParams.set('order', 'desc')
  url.searchParams.set('per_page', String(perPage))
  url.searchParams.set('page', String(page))
  return url
}

/**
 * 1 ページ分を取得する。成功したら JSON 配列を返し、恒久失敗（4xx・リトライ尽き）なら
 * null を返す（例外を投げない＝呼び出し側の collectRegistry がレジストリ単位で握り潰せるように
 * する。ここで throw すると collectAll のループ自体が止まってしまう）。
 */
async function fetchPage({ registry, page, perPage, fetchImpl, sleep }) {
  const url = buildPageUrl(registry, page, perPage)
  let attempt = 0

  while (true) {
    let res
    let networkError = null
    try {
      res = await fetchImpl(url, {
        headers: { 'user-agent': USER_AGENT, accept: 'application/json' },
      })
    } catch (err) {
      // ネットワーク断そのものは 5xx と同様に一時障害として扱い、リトライ対象にする。
      networkError = err
    }

    if (!networkError && res.ok) {
      return res.json()
    }

    const status = networkError ? null : res.status
    const retriable = networkError !== null || status === 429 || status >= 500
    if (!retriable) {
      // 4xx（429 以外）はリトライしても直らない類のエラーなので即中断する。
      console.warn(
        `[gem-pool/collect] ${registry.id}: HTTP ${status} @ page=${page}（リトライ対象外・中断）`,
      )
      return null
    }

    if (attempt >= MAX_RETRIES) {
      const reason = networkError ? networkError.message : `HTTP ${status}`
      console.warn(
        `[gem-pool/collect] ${registry.id}: ${reason} @ page=${page}（${MAX_RETRIES} 回リトライ後も失敗・中断）`,
      )
      return null
    }

    const backoffMs = BASE_BACKOFF_MS * 2 ** attempt
    await sleep(backoffMs)
    attempt += 1
  }
}

/**
 * 1 レジストリ分を被依存数降順で quota 件まで取得する。
 * ページが perPage 未満・空配列・quota 到達のいずれかで打ち切る。
 * 恒久失敗時はそのレジストリだけ空配列を返す（呼び出し側は Error を受け取らない）。
 */
export async function collectRegistry({
  registry,
  quota,
  perPage,
  fetchImpl = fetch,
  onProgress,
  sleep = defaultSleep,
}) {
  const effectiveQuota = quota ?? DEFAULT_QUOTA
  const effectivePerPage = perPage ?? DEFAULT_PER_PAGE

  const results = []
  let page = 1

  while (results.length < effectiveQuota) {
    const body = await fetchPage({
      registry,
      page,
      perPage: effectivePerPage,
      fetchImpl,
      sleep,
    })

    if (body === null) {
      // fetchPage 側で警告済み。ここでは「このレジストリは丸ごと諦める」ことだけ確定させる。
      return []
    }
    if (!Array.isArray(body) || body.length === 0) break

    results.push(...body)
    onProgress?.({ registry: registry.id, page, fetched: results.length })
    // 10 分近くかかる処理なので、進捗を沈黙させずに 1 行だけ出す（契約 §3）。
    console.error(`[gem-pool/collect] ${registry.id}: page=${page} fetched=${results.length}`)

    if (body.length < effectivePerPage) break
    if (results.length >= effectiveQuota) break

    page += 1
    await sleep(REQUEST_INTERVAL_MS)
  }

  return results.slice(0, effectiveQuota)
}

/**
 * 全レジストリを順に収集する（並列化しない＝レート枠を素直に守るため）。
 * 1 レジストリが失敗しても他のレジストリの収集は続行する。
 */
export async function collectAll({
  registries = REGISTRIES,
  quota,
  perPage,
  fetchImpl,
  onProgress,
  sleep,
} = {}) {
  const out = []
  for (const registry of registries) {
    const packages = await collectRegistry({
      registry,
      quota,
      perPage,
      fetchImpl,
      onProgress,
      sleep,
    })
    out.push({ registry: registry.id, packages })
  }
  return out
}
