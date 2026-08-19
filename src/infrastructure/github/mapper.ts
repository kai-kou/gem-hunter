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
    // 🔴 totalCount は API が返した値をそのまま保つ（下の private 除外で書き換えない）。
    //    GitHub 側の総件数とページングの整合を崩さないため。
    totalCount: dto.total_count,
    incompleteResults: dto.incomplete_results ?? false,
    // 🔴 多層防御: 検索クエリの `is:public`（github-repository-query.ts）が将来効かなくなっても
    //    非公開リポジトリを画面へ出さないための保険（prd.md L171「公開リポジトリの検索」）。
    //    `private` は optional なので、明示的に true のものだけを除外する（undefined は公開扱い）。
    items: dto.items
      .filter((item) => item.private !== true)
      .map((item): RepositorySummary => ({
        id: item.id,
        name: item.name,
        fullName: item.full_name,
        owner: { login: item.owner.login, avatarUrl: item.owner.avatar_url },
        description: item.description,
        primaryLanguage: item.language,
        stars: item.stargazers_count,
        // 🔴 「最終更新日」は pushed_at を使う（メタデータ更新で動く updated_at ではない・domain-model.md §2.2）。
        //    pushed_at が null（コミット履歴のない空リポジトリ）の場合のみ updated_at にフォールバックする。
        lastPushedAt: new Date(item.pushed_at ?? item.updated_at),
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
