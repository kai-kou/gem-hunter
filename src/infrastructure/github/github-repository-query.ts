import { RateLimitExceededError, UpstreamError } from '../../domain/errors'
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
      throw new UpstreamError('GitHub API へ到達できませんでした', { cause })
    }

    if (response.ok) {
      return response
    }
    if (options?.notFoundAsNull && response.status === 404) {
      return null
    }
    if (isRateLimited(response)) {
      throw new RateLimitExceededError(
        'GitHub API のレート制限に達しました',
        resetAt(response) ?? undefined,
      )
    }
    throw new UpstreamError(`GitHub API がエラーを返しました（HTTP ${response.status}）`)
  }
}

function isRateLimited(response: Response): boolean {
  if (response.status !== 403 && response.status !== 429) {
    return false
  }
  return response.headers.get('x-ratelimit-remaining') === '0' || response.status === 429
}

function resetAt(response: Response): Date | null {
  const reset = response.headers.get('x-ratelimit-reset')
  if (!reset) {
    return null
  }
  const seconds = Number(reset)
  return Number.isFinite(seconds) ? new Date(seconds * 1000) : null
}
