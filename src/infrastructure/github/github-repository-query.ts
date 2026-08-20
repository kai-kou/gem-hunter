import {
  AuthError,
  type DomainError,
  NetworkError,
  NotFoundError,
  RateLimitExceededError,
  SearchQueryRejectedError,
  UpstreamError,
} from '../../domain/errors'
import type { RepositoryDetail, SearchResult } from '../../domain/model/repository'
import { ownerOf, repoOf, type RepositoryFullName } from '../../domain/model/repository-full-name'
import type { SearchQuery } from '../../domain/model/search-query'
import type { RepositoryQueryPort } from '../../domain/ports/repository-query-port'
import { resolveLoopbackOverridableOrigin } from './loopback-origin'
import { toPublicRepositoryDetail, toSearchResult } from './mapper'

const DEFAULT_API_ORIGIN = 'https://api.github.com'

function apiOrigin(): string {
  return resolveLoopbackOverridableOrigin('GITHUB_API_ORIGIN', DEFAULT_API_ORIGIN)
}

/**
 * 🔴 検索クエリへ必ず付与する公開限定の修飾子。
 * GitHub App の installation token（Bearer）で認証すると、そのトークンから見える private
 * リポジトリまで `GET /search/repositories` の可視範囲に入ってしまう。本プロダクトの仕様は
 * 「GitHub 公開リポジトリの検索」（prd.md L171）なので、検索の時点で公開に閉じる。
 */
const PUBLIC_ONLY_QUALIFIER = 'is:public'

/** アクセストークンの供給口。未認証で叩く場合は null を返す。 */
export type TokenProvider = () => Promise<string | null>

/**
 * 🔴 GitHub API に触れてよい唯一の場所（ACL・NFR-16 / TR-4）。
 * データソースは GET /search/repositories と GET /repos/{owner}/{repo} に限定する（E-2）。
 */
export class GithubRepositoryQuery implements RepositoryQueryPort {
  constructor(private readonly deps: { token: TokenProvider }) {}

  async search(query: SearchQuery): Promise<SearchResult> {
    const url = new URL('/search/repositories', apiOrigin())
    // 🔴 公開限定の修飾子は **キーワードより前** に置く（多層防御の 2 層目）。
    //    1 層目はドメイン側で、キーワードに検索式の構文（`名前:値`・大文字の `NOT` / `OR` /
    //    `AND`）を含められないようにしている（`domain/model/search-keyword.ts`）。それでも
    //    末尾に置く形は、キーワード末尾のトークン次第でこの修飾子が後置演算子の作用範囲へ
    //    入りうる（例: 末尾 `NOT` に否定され「公開でないもの」＝ private 限定へ反転する）。
    //    先頭に置けば、キーワード側に何が来ても公開限定条件が単独のトークンとして残る。
    url.searchParams.set('q', `${PUBLIC_ONLY_QUALIFIER} ${query.keyword}`)
    url.searchParams.set('page', String(query.page))
    url.searchParams.set('per_page', String(query.perPage))
    // 🔴 仮定（実装手段レベル・SD-3 対象外）: relevance は GitHub API の既定挙動のため
    // sort/order パラメータを付けない。stars/updated は星の多い順・更新が新しい順が自然なため
    // order=desc を固定で付与する。
    if (query.sort !== 'relevance') {
      url.searchParams.set('sort', query.sort)
      url.searchParams.set('order', 'desc')
    }

    const response = await this.request(url)
    return toSearchResult(await response.json())
  }

  async findDetail(name: RepositoryFullName): Promise<RepositoryDetail | null> {
    const url = new URL(
      `/repos/${encodeURIComponent(ownerOf(name))}/${encodeURIComponent(repoOf(name))}`,
      apiOrigin(),
    )

    const response = await this.request(url, { notFoundAsNull: true })
    if (response === null) {
      return null
    }

    // 🔴 非公開リポジトリを「見つからない」として扱う判定は ACL（mapper）に集約している
    //    （検索側の is:public だけでは詳細エンドポイントの直接アクセスを防げないため・NFR-33 / AC-12）。
    return toPublicRepositoryDetail(await response.json())
  }

  private async request(url: URL, options: { notFoundAsNull: true }): Promise<Response | null>
  private async request(url: URL, options?: { notFoundAsNull?: false }): Promise<Response>
  private async request(
    url: URL,
    options?: { notFoundAsNull?: boolean },
  ): Promise<Response | null> {
    const token = await this.deps.token()
    const headers: Record<string, string> = {
      accept: 'application/vnd.github+json',
      'x-github-api-version': '2022-11-28',
      'user-agent': 'gem-hunter',
    }
    if (token) {
      headers.authorization = `Bearer ${token}`
    }

    let response: Response
    try {
      response = await fetch(url, { headers })
    } catch (cause) {
      throw new NetworkError('GitHub API へ到達できませんでした', { cause })
    }

    if (response.ok) {
      return response
    }
    if (options?.notFoundAsNull && response.status === 404) {
      return null
    }
    throw toDomainError(response, url)
  }
}

/**
 * 🔴 HTTP 応答を prd.md §7「エラー種別の判別仕様」の種別へ落とす。**判定順序は同表の行順に従う**
 * （403 は一次レート制限・二次レート制限・認証エラーのどれにもなりうるため、先に一次
 * （`x-ratelimit-remaining: 0`）、次に二次（`retry-after`）、最後に認証エラーの順で判定する）。
 */
function toDomainError(response: Response, url: URL): DomainError {
  const { status } = response

  if (status === 404) {
    return new NotFoundError(`GitHub API が対象を返しませんでした（HTTP 404 ${url.pathname}）`)
  }

  if (status === 403 || status === 429) {
    const seconds = retryAfterSeconds(response)
    if (response.headers.get('x-ratelimit-remaining') === '0') {
      // 🔴 一次レート制限（枠の枯渇）を先に判定する。x-ratelimit-reset が復帰時刻。
      //    両ヘッダが同時に付く応答を二次へ倒すと、一次のときだけ出る「ログインで枠を増やせる
      //    案内」（US-25 / AR-5）が消えるため、この順序は prd.md §7 の表どおりに保つ。
      //    retry-after も返っていれば補助情報として一緒に持たせる（提示の主役は復帰時刻）。
      return new RateLimitExceededError('rateLimitPrimary', {
        retryAfter: resetAt(response) ?? undefined,
        retryAfterSeconds: seconds ?? undefined,
      })
    }
    if (seconds !== null) {
      // 二次レート制限（短時間の集中）。retry-after 秒後に再試行できる。
      return new RateLimitExceededError('rateLimitSecondary', { retryAfterSeconds: seconds })
    }
    if (status === 429) {
      // 再試行情報が無い 429。枠は残っているため二次レート制限として扱う（秒数は不明）。
      return new RateLimitExceededError('rateLimitSecondary')
    }
  }

  if (status === 401 || status === 403) {
    // 🔴 内部情報を出さない汎用エラーとして扱う（サーバー設定の問題であり利用者は対処できない）。
    return new AuthError(`GitHub API の認証・権限に問題があります（HTTP ${status}）`)
  }

  if (status === 422) {
    return new SearchQueryRejectedError(
      userKeywordOf(url),
      'GitHub API が検索クエリを受理しませんでした（HTTP 422）',
    )
  }

  return new UpstreamError(`GitHub API がエラーを返しました（HTTP ${status}）`)
}

/**
 * 422 のエラーへ載せる「利用者入力に由来するキーワード」を取り出す。
 * 🔴 送信したクエリ（`q`）には ACL が付与した公開限定修飾子（`is:public`）が含まれるため、
 * それを取り除いた残りだけを返す（内部の防御実装を外へ持ち出さない・NFR-33）。
 */
function userKeywordOf(url: URL): string | null {
  const q = url.searchParams.get('q')
  if (q === null) {
    return null
  }
  return q.startsWith(`${PUBLIC_ONLY_QUALIFIER} `) ? q.slice(PUBLIC_ONLY_QUALIFIER.length + 1) : q
}

/**
 * `retry-after` を待機秒数へ落とす。**秒数（delta-seconds）と HTTP-date の両形式が有効**
 * （RFC 9110 §10.2.3）なので両方を解釈する。ヘッダが無い・どちらの形式としても読めない場合は null。
 */
function retryAfterSeconds(response: Response): number | null {
  const retryAfter = response.headers.get('retry-after')?.trim()
  if (!retryAfter) {
    return null
  }

  const seconds = Number(retryAfter)
  if (Number.isFinite(seconds)) {
    // delta-seconds は非負整数（RFC 9110 §10.2.3）なので、負値は壊れた値として捨てる。
    return seconds >= 0 ? seconds : null
  }

  const epochMillis = Date.parse(retryAfter)
  if (Number.isNaN(epochMillis)) {
    return null
  }
  // 🟡 このクラスは ClockPort を注入されていない（deps は token のみ）ため、ここだけ Date.now()
  //    を直接使う。HTTP-date は絶対時刻なので、待機秒数へ落とすには "今" が要る。
  //    既に過ぎた時刻は「待機不要」＝ 0 秒として扱う（負値の delta-seconds と違い、過去の
  //    HTTP-date は「もう再試行してよい」という有効な表現）。
  return Math.max(0, Math.round((epochMillis - Date.now()) / 1000))
}

/**
 * `x-ratelimit-reset`（エポック秒）を復帰時刻へ落とす。
 * 🔴 秒ではなくミリ秒が入っている等の壊れた値は Invalid Date になる。そのまま返すと呼び出し側の
 * `toISOString()` / `Intl.DateTimeFormat` が RangeError を投げて 500 になるため null へ倒し、
 * 「復帰時刻不明」の提示（`rateLimitPrimaryUnknownReset`）に乗せる。
 */
function resetAt(response: Response): Date | null {
  const reset = response.headers.get('x-ratelimit-reset')
  if (!reset) {
    return null
  }
  const seconds = Number(reset)
  if (!Number.isFinite(seconds)) {
    return null
  }
  const date = new Date(seconds * 1000)
  return Number.isNaN(date.getTime()) ? null : date
}
