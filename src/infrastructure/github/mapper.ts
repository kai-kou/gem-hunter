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
    //    非公開リポジトリを画面へ出さないための保険（prd.md L171「公開リポジトリの検索」・NFR-33）。
    //    `private` は DTO で必須にしているため、欠落したレスポンスはここへ届く前に UpstreamError で倒れる。
    items: dto.items
      .filter((item) => !item.private)
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
 * 🔴 「公開に閉じる」ポリシーはこの ACL に集約する（呼び出し側で生 JSON を覗いて判定しない）。
 *    非公開リポジトリは `null`（＝見つからない）として返し、詳細 URL の直打ちを塞ぐ（NFR-33 / AC-12）。
 *    判定は必ず zod 検証の **後**（型付き値）で行う（検証前の手書きキャストは private の欠落・
 *    型崩れを黙って公開扱いへ倒すため）。
 */
export function toPublicRepositoryDetail(raw: unknown): RepositoryDetail | null {
  const parsed = repositoryDetailDto.safeParse(raw)
  if (!parsed.success) {
    throw new UpstreamError('GitHub API のレスポンスが想定と異なります', { cause: parsed.error })
  }
  const dto = parsed.data

  if (dto.private) {
    return null
  }

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
