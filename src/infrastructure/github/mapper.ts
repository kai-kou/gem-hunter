import type { RepositorySummary, SearchResult } from '../../domain/model/repository'
import { searchRepositoriesDto } from './dto'

/** 外部データを検証したうえでドメインモデルへ変換する（ACL）。 */
export function toSearchResult(raw: unknown): SearchResult {
  const dto = searchRepositoriesDto.parse(raw)

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
