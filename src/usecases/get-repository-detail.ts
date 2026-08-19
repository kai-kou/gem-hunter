import type { RepositoryDetail } from '../domain/model/repository'
import { tryRepositoryFullName } from '../domain/model/repository-full-name'
import type { RepositoryQueryPort } from '../domain/ports/repository-query-port'

export type GetRepositoryDetailInput = { owner: string; repo: string }

export type GetRepositoryDetail = (input: GetRepositoryDetailInput) => Promise<RepositoryDetail | null>

/** 独立 URL の詳細ページのためにリポジトリを単独取得する（US-16 / US-17 / AC-4）。 */
export function makeGetRepositoryDetail(deps: { repos: RepositoryQueryPort }): GetRepositoryDetail {
  return async (input) => {
    const name = tryRepositoryFullName(input.owner, input.repo)
    if (name === null) {
      return null
    }
    return deps.repos.findDetail(name)
  }
}
