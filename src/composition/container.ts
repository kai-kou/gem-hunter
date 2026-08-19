import { GithubRepositoryQuery } from '../infrastructure/github/github-repository-query'
import { installationTokenProvider } from '../infrastructure/github/installation-token'
import { makeSearchRepositories, type SearchRepositories } from '../usecases/search-repositories'

/**
 * composition root。実装をポートへ束ねてよい唯一の場所（architecture §2.1）。
 * DI コンテナは使わない（YAGNI）。
 */
export function searchRepositoriesUseCase(): SearchRepositories {
  return makeSearchRepositories({
    repos: new GithubRepositoryQuery({ token: installationTokenProvider }),
  })
}
