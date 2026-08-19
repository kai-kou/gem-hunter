import { RateLimitExceededError, UpstreamError } from '../../domain/errors'
import type { RepositoryDetail, SearchResult } from '../../domain/model/repository'
import { PER_PAGE } from '../../domain/model/page-number'
import { ownerOf, repoOf, type RepositoryFullName } from '../../domain/model/repository-full-name'
import type { SearchQuery } from '../../domain/model/search-query'
import type { RepositoryQueryPort } from '../../domain/ports/repository-query-port'
import { toRepositoryDetail, toSearchResult } from './mapper'

const DEFAULT_API_ORIGIN = 'https://api.github.com'

/**
 * 🔴 リクエスト時に毎回読む（モジュール読み込み時に固定しない）。
 * `next build` 時点で焼き付くのを避け、E2E からローカルスタブへ向けられるようにする（E-11・SP-4）。
 */
function apiOrigin(): string {
  return process.env.GITHUB_API_ORIGIN ?? DEFAULT_API_ORIGIN
}

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
    url.searchParams.set('q', query.keyword)
    url.searchParams.set('page', String(query.page))
    url.searchParams.set('per_page', String(PER_PAGE))

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
    return toRepositoryDetail(await response.json())
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
