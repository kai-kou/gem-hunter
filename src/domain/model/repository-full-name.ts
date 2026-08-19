import { DomainValidationError } from '../errors'

export const MAX_OWNER_LENGTH = 39
export const MAX_REPO_LENGTH = 100

const OWNER_PATTERN = /^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?$/
const REPO_PATTERN = /^[A-Za-z0-9._-]+$/

declare const brand: unique symbol

/** GitHub のリポジトリ完全名（"owner/repo"）。 */
export type RepositoryFullName = string & { readonly [brand]: 'RepositoryFullName' }

function isValidOwner(owner: string): boolean {
  return owner.length > 0 && owner.length <= MAX_OWNER_LENGTH && OWNER_PATTERN.test(owner)
}

function isValidRepo(repo: string): boolean {
  return (
    repo.length > 0 &&
    repo.length <= MAX_REPO_LENGTH &&
    REPO_PATTERN.test(repo) &&
    repo !== '.' &&
    repo !== '..'
  )
}

/** owner・repo それぞれの GitHub 命名規則に適合しない値は DomainValidationError（domain-model.md §4）。 */
export function repositoryFullName(owner: string, repo: string): RepositoryFullName {
  if (!isValidOwner(owner) || !isValidRepo(repo)) {
    throw new DomainValidationError(
      'RepositoryFullName',
      `${owner}/${repo}`,
      'リポジトリ名の形式が正しくありません',
    )
  }
  return `${owner}/${repo}` as RepositoryFullName
}

/** URL 由来の値のように「不正なら諦めてよい」文脈で使う。 */
export function tryRepositoryFullName(
  owner: string | null | undefined,
  repo: string | null | undefined,
): RepositoryFullName | null {
  if (owner == null || repo == null) {
    return null
  }
  try {
    return repositoryFullName(owner, repo)
  } catch {
    return null
  }
}

export function ownerOf(name: RepositoryFullName): string {
  return name.slice(0, name.indexOf('/'))
}

export function repoOf(name: RepositoryFullName): string {
  return name.slice(name.indexOf('/') + 1)
}
