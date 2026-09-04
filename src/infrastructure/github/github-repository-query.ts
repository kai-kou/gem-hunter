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
import type { CachePort } from '../../domain/ports/cache-port'
import type { RepositoryQueryPort } from '../../domain/ports/repository-query-port'
import { readmeEtagCacheKey, repositoryEtagCacheKey, type CacheKey } from '../platform/cache-key'
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
 * ETag 条件付きリクエストのキャッシュエントリ（上流の生レスポンス + ETag）。
 *
 * 🔴 **`body` は ACL 適用前・トークン非依存キーで共有される生データである**（Issue #170 /
 * PR #926 レビュー指摘 #3）。`cache-key.ts` のキー（`repository-etag:` / `readme-etag:`）は
 * 利用者識別子を持たないため、private リポジトリの生 JSON が一時的にこのエントリへ
 * 保存された場合でも、そのまま画面へ出してはならない。**呼び出し元（`findDetail` /
 * `findReadme`）は必ず ACL（`toPublicRepositoryDetail` 等）を経由してから使うこと**
 * （`fetchWithConditionalCache` はキャッシュ透過の配管に徹し、ACL 判定を持たない）。
 */
type EtagEntry<T> = { readonly etag: string; readonly body: T }

/**
 * `unknown` を `EtagEntry<T>` として信頼してよいかをランタイムで検証する（PR #926 レビュー
 * 指摘 #2）。`CachePort.get` は「異常時は throw せず値を返す」契約のため、保存後に値が
 * 破損しても（実装バグ・手動での書き込み等）例外にはならない。破損したエントリを
 * そのまま信頼すると、`body` が `null` に壊れているケースで `findDetail` が
 * 「対象が存在しない」と誤判定し、実在する公開リポジトリが 404 相当になってしまう。
 *
 * 検証するのは構造だけ（`etag` が非空文字列 / `body` が null・undefined でない）。
 * `body` の中身（ドメインスキーマとの一致）は呼び出し元の ACL（`toPublicRepositoryDetail` 等）
 * が別途 zod で検証するため、ここで二重に検証しない。
 */
function isValidEtagEntry<T>(candidate: unknown): candidate is EtagEntry<T> {
  if (typeof candidate !== 'object' || candidate === null) {
    return false
  }
  const value = candidate as { etag?: unknown; body?: unknown }
  return typeof value.etag === 'string' && value.etag !== '' && value.body != null
}

/** `token` が実際に送信してよい値（`null` でも空文字列でもない）かを判定する。 */
function isUsableToken(token: string | null): token is string {
  return token !== null && token !== ''
}

/**
 * `findDetail` / `findReadme` / `search` 共通のリクエストヘッダを組み立てる
 * （PR #926 レビュー指摘 #4: `fetchWithConditionalCache` と `request` の重複を解消）。
 * 認証ヘッダは `isUsableToken` で統一判定する（レビュー指摘 #5: `sendConditional` の
 * `token !== null` 判定と食い違わせない）。
 */
function buildRequestHeaders(
  accept: string | undefined,
  token: string | null,
): Record<string, string> {
  const headers: Record<string, string> = {
    accept: accept ?? 'application/vnd.github+json',
    'x-github-api-version': '2022-11-28',
    'user-agent': 'gem-hunter',
  }
  if (isUsableToken(token)) {
    headers.authorization = `Bearer ${token}`
  }
  return headers
}

/**
 * `fetch` を実行し、ネットワーク層の失敗（DNS 解決不能・接続拒否等）を `NetworkError` へ
 * 変換する共通ヘルパー（PR #926 レビュー指摘 #4）。HTTP レベルのエラー（4xx/5xx）は
 * ここでは判定しない（呼び出し元が `response.status` を見て判断する）。
 */
async function fetchOrThrowNetworkError(
  url: URL,
  headers: Record<string, string>,
): Promise<Response> {
  try {
    return await fetch(url, { headers })
  } catch (cause) {
    throw new NetworkError('GitHub API へ到達できませんでした', { cause })
  }
}

/**
 * 🔴 GitHub API に触れてよい唯一の場所（ACL・NFR-16 / TR-4）。
 * データソースは GET /search/repositories と GET /repos/{owner}/{repo} に限定する（E-2）。
 * 🔵 GET /repos/{owner}/{repo}/readme を追加（Issue #334 F-4・whiteboard round3 裁定）。
 */
export class GithubRepositoryQuery implements RepositoryQueryPort {
  constructor(
    private readonly deps: {
      token: TokenProvider
      /**
       * ETag / 条件付きリクエストの設定一式（Issue #170 / PR #926 レビュー指摘 #1）。
       * 対象は `findDetail` / `findReadme` のみ（`search` は下記 JSDoc の理由で対象外）。
       *
       * 🔴 **値域**: 渡す場合、`ttlSeconds` は **正の有限数**（秒）でなければならない
       * （`0` / 負値 / `NaN` / `Infinity` は不正・`CachePort.set` と同じ値域）。
       * 🔴 **異常時の振る舞い**: 値域外の `ttlSeconds` を渡すとコンストラクタが
       * `RangeError` を **即座に throw する**（fail-loud）。以前は `cache` /
       * `etagTtlSeconds` を独立した省略可能フィールドにしていたため「片方だけ渡す」
       * （例: `etagTtlSeconds` が `0` で `cache` だけ渡す）ことが型上可能で、
       * `Boolean(cache && etagTtlSeconds)` という値域非対称な判定（`0`/`NaN` は無音で
       * 無効化するが負値/`Infinity` は `cache.set` まで到達して `RangeError` になる）を
       * 生んでいた。1 つの複合フィールドへまとめることで「片方だけ渡す」を型で
       * 不可能にし、値域チェックもコンストラクタへ前倒しする。
       *
       * 省略時（`undefined`）は条件付きリクエストを一切行わず、従来どおり毎回フル GET する。
       */
      etag?: { cache: CachePort; ttlSeconds: number }
    },
  ) {
    if (deps.etag !== undefined && !isPositiveFiniteNumber(deps.etag.ttlSeconds)) {
      throw new RangeError(
        `GithubRepositoryQuery: etag.ttlSeconds は正の有限数である必要があります（受け取った値: ${deps.etag.ttlSeconds}）`,
      )
    }
  }

  /**
   * 🔴 **ETag / 条件付きリクエストの対象外**（Issue #170 の意図的なスコープ縮小）。
   * `GET /search/repositories` は 304 を返しうるが、GitHub 公式は「条件付きリクエストで
   * 304 が返ると primary rate limit を消費しない」としか明記しておらず、Search 専用枠
   * （30 req/min）を消費しないとは明記していない
   * （ https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api ）。
   * 節約できる保証が無い枠に ETag 保存のコストを払わないため、対象は `findDetail` /
   * `findReadme` の 2 経路（`GET /repos/{owner}/{repo}` 系・primary 枠）のみに限定する。
   */
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

    const json = await this.fetchWithConditionalCache<unknown>(
      url,
      repositoryEtagCacheKey(ownerOf(name), repoOf(name)),
      {},
    )
    if (json === null) {
      return null
    }

    // 🔴 非公開リポジトリを「見つからない」として扱う判定は ACL（mapper）に集約している
    //    （検索側の is:public だけでは詳細エンドポイントの直接アクセスを防げないため・NFR-33 / AC-12）。
    return toPublicRepositoryDetail(json)
  }

  /**
   * README を GitHub がレンダリング済みの HTML として取得する（Issue #334 F-4）。
   * `Accept: application/vnd.github.html+json` を指定すると、GitHub 側が Markdown を HTML へ
   * 変換したものをそのまま返す（自前で Markdown レンダラを持ち込まない・whiteboard round3 裁定）。
   *
   * 🔴 戻り値は未サニタイズの第三者由来 HTML。サニタイズは呼び出し側（`src/ui/`）の責務。
   * 🔴 レスポンスに `private` フィールドが無いため、非公開判定はこのメソッドではできない
   *    （呼び出しは `src/usecases/get-repository-readme.ts` の private ゲート経由に限る）。
   */
  async findReadme(name: RepositoryFullName): Promise<string | null> {
    const url = new URL(
      `/repos/${encodeURIComponent(ownerOf(name))}/${encodeURIComponent(repoOf(name))}/readme`,
      apiOrigin(),
    )

    return this.fetchWithConditionalCache<string>(
      url,
      readmeEtagCacheKey(ownerOf(name), repoOf(name)),
      {
        accept: 'application/vnd.github.html+json',
        parse: (response) => response.text(),
      },
    )
  }

  /**
   * `findDetail` / `findReadme` 共通の条件付きリクエスト（ETag）手順（Issue #170）。
   * `cache` / `etagTtlSeconds` の両方が渡されているときだけ有効化する（片方欠けは無効扱い・
   * fail-closed）。
   *
   * 手順:
   * 1. 有効かつ **認証済み**（`token` が非 null）のときだけ、保存済み ETag があれば
   *    `If-None-Match` を送る（🔴 未認証では 304 でも primary rate limit を消費してしまう
   *    仕様のため、未認証時に送る意味が無い）。
   * 2. `304` が返り、送った ETag に対応する保存値があれば、それを再取得せず返す。
   *    `304` が返ったのに保存値が無い（＝ `If-None-Match` を送っていない）場合は、上流が
   *    仕様外の応答をしたとみなし `UpstreamError` にする（呼び出し側の型契約
   *    `Promise<T | null>` の `null` は「対象が存在しない」専用のため、異常応答をそこに
   *    紛れ込ませない）。
   * 3. `404` は従来どおり `null`。
   * 4. `200` なら本文をパースし、`etag` レスポンスヘッダがあれば ETag ストアへ保存する。
   */
  private async fetchWithConditionalCache<T>(
    url: URL,
    cacheKey: CacheKey,
    options: { accept?: string; parse?: (response: Response) => Promise<T> },
  ): Promise<T | null> {
    const parse = options.parse ?? ((response: Response) => response.json() as Promise<T>)
    const { etag } = this.deps

    const token = await this.deps.token()
    // 🔴 未認証（token が null・空文字列）では If-None-Match を送らない（GitHub 公式
    //    best-practices: 条件付きリクエストが primary rate limit を消費しないのは
    //    認証済みリクエストに限る）。判定は `isUsableToken` に一本化し（レビュー指摘 #5）、
    //    下の Authorization ヘッダ付与判定と食い違わせない。
    const sendConditional = etag !== undefined && isUsableToken(token)

    let stored: EtagEntry<T> | null = null
    if (sendConditional) {
      const candidate = await etag.cache.get<EtagEntry<T>>(cacheKey)
      // 🔴 ランタイムで破損したエントリを信頼しない（レビュー指摘 #2）。弾いた場合は
      //    `stored = null` のまま通常のフルフェッチへフォールバックする。
      stored = isValidEtagEntry<T>(candidate) ? candidate : null
    }

    const headers = buildRequestHeaders(options.accept, token)
    if (sendConditional && stored) {
      headers['if-none-match'] = stored.etag
    }

    const response = await fetchOrThrowNetworkError(url, headers)

    if (response.status === 304) {
      if (sendConditional && stored) {
        return stored.body
      }
      throw new UpstreamError(
        `GitHub API が If-None-Match 未送信のリクエストに 304 を返しました（${url.pathname}）`,
      )
    }

    if (response.status === 404) {
      return null
    }

    if (!response.ok) {
      throw toDomainError(response, url)
    }

    const body = await parse(response)
    if (etag) {
      const etagHeader = response.headers.get('etag')
      if (etagHeader) {
        await etag.cache.set<EtagEntry<T>>(cacheKey, { etag: etagHeader, body }, etag.ttlSeconds)
      }
    }
    return body
  }

  /**
   * `search()` 専用のリクエスト実行（ETag 非対応・NotFoundError を throw する）。
   * `findDetail` / `findReadme` は `fetchWithConditionalCache` を使う（本メソッドは使わない）。
   */
  private async request(url: URL): Promise<Response> {
    const token = await this.deps.token()
    const headers = buildRequestHeaders(undefined, token)

    const response = await fetchOrThrowNetworkError(url, headers)

    if (response.ok) {
      return response
    }
    throw toDomainError(response, url)
  }
}

/** `ttlSeconds` の値域（`CachePort.set` と同じ＝正の有限数）を満たすかを判定する。 */
function isPositiveFiniteNumber(value: number): boolean {
  return Number.isFinite(value) && value > 0
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
