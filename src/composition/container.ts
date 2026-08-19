import { GithubRepositoryQuery } from '../infrastructure/github/github-repository-query'
import { makeInstallationTokenProvider } from '../infrastructure/github/installation-token'
import { SystemClock } from '../infrastructure/system-clock'
import { makeGetRepositoryDetail, type GetRepositoryDetail } from '../usecases/get-repository-detail'
import { makeSearchRepositories, type SearchRepositories } from '../usecases/search-repositories'

/**
 * composition root。実装をポートへ束ねてよい唯一の場所（architecture §2.1）。
 * DI コンテナは使わない（YAGNI）。
 */
export function searchRepositoriesUseCase(): SearchRepositories {
  const clock = new SystemClock()
  return makeSearchRepositories({
    repos: new GithubRepositoryQuery({ token: makeInstallationTokenProvider({ clock }) }),
  })
}

/** SP-3: 独立 URL の詳細画面用ユースケースの組み立て（US-16 / US-17 / AC-4）。 */
export function getRepositoryDetailUseCase(): GetRepositoryDetail {
  const clock = new SystemClock()
  return makeGetRepositoryDetail({
    repos: new GithubRepositoryQuery({ token: makeInstallationTokenProvider({ clock }) }),
  })
}
