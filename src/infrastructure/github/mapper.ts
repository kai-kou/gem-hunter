import { UpstreamError } from '../../domain/errors'
import type { RepositoryDetail, RepositorySummary, SearchResult } from '../../domain/model/repository'
import { repositoryDetailDto, searchRepositoriesDto } from './dto'

/**
 * 外部データを検証したうえでドメインモデルへ変換する（ACL）。
 * 🔴 スキーマ不一致は外へ漏らさずドメインエラーへ翻訳する（上位層は zod を知らない）。
 */
export function toSearchResult(raw: unknown): SearchResult {
  const parsed = searchRepositoriesDto.safeParse(raw)
  if (!parsed.success) {
    throw new UpstreamError('GitHub API のレスポンスが想定と異なります', { cause: parsed.error })
  }
  const dto = parsed.data

  return {
    totalCount: dto.total_count,
    incompleteResults: dto.incomplete_results ?? false,
    items: dto.items.map((item): RepositorySummary => ({
      id: item.id,
      name: item.name,
      fullName: item.full_name,
      owner: { login: item.owner.login, avatarUrl: item.owner.avatar_url },
      description: item.description,
      primaryLanguage: item.language,
      stars: item.stargazers_count,
      updatedAt: new Date(item.updated_at),
      topics: item.topics ?? [],
      htmlUrl: item.html_url,
    })),
  }
}

/**
 * 外部データを検証したうえで詳細画面のドメインモデルへ変換する（ACL）。
 * 🔴 スキーマ不一致は外へ漏らさずドメインエラーへ翻訳する（上位層は zod を知らない）。
 */
export function toRepositoryDetail(raw: unknown): RepositoryDetail {
  const parsed = repositoryDetailDto.safeParse(raw)
  if (!parsed.success) {
    throw new UpstreamError('GitHub API のレスポンスが想定と異なります', { cause: parsed.error })
  }
  const dto = parsed.data

  return {
    id: dto.id,
    name: dto.name,
    fullName: dto.full_name,
    owner: { login: dto.owner.login, avatarUrl: dto.owner.avatar_url },
    description: dto.description,
    primaryLanguage: dto.language,
    stars: dto.stargazers_count,
    // 🔴 watchers_count（star のミラー）ではなく subscribers_count を使う
    watchers: dto.subscribers_count,
    forks: dto.forks_count,
    openIssues: dto.open_issues_count,
    updatedAt: new Date(dto.updated_at),
    topics: dto.topics ?? [],
    htmlUrl: dto.html_url,
  }
}
