import { UpstreamError } from '../../domain/errors'
import type {
  RepositoryDetail,
  RepositorySummary,
  SearchResult,
} from '../../domain/model/repository'
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
        lastPushedAt: lastPushedAtOf(item.pushed_at, item.updated_at),
        topics: item.topics ?? [],
        htmlUrl: item.html_url,
      })),
  }
}

/**
 * 「最終更新日」の算出規則（`domain-model.md` §2.2）。
 *
 * 🔴 メタデータ更新でも動く `updated_at` ではなく `pushed_at` を使う。`pushed_at` が null
 * （コミット履歴のない空リポジトリ）の場合のみ `updated_at` へフォールバックする。
 * 🔴 一覧（`toSearchResult`）と詳細（`toPublicRepositoryDetail`）で **同じ関数を使う**
 * （同一概念に別の算出規則が混ざると、画面遷移で「最終更新」の意味が変わって見える・Issue #334）。
 * 🔴 上流が日付として不正な文字列を返しても `Invalid Date` を持ち出さない（Issue #338）。
 *    `new Date(invalid)` をそのまま `Intl.DateTimeFormat` に渡すと `RangeError` で 500 になるため、
 *    `pushed_at` が不正なら `updated_at` へ、それも不正なら epoch（1970-01-01）へ倒す
 *    （`github-repository-query.ts` の `resetAt()` と同じ「壊れた値は安全な既定値に丸める」防御）。
 *    1 件のリポジトリの不正データで一覧・詳細全体を落とさない（docs/02_requirements/minimum-requirements.md §4.1「握り潰さず継続利用可能に保つ」）。
 */
function lastPushedAtOf(pushedAt: string | null, updatedAt: string): Date {
  const primary = pushedAt === null ? null : toValidDate(pushedAt)
  return primary ?? toValidDate(updatedAt) ?? new Date(0)
}

function toValidDate(value: string): Date | null {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
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
    // 🔴 watchers_count（star のミラー）ではなく subscribers_count を使う（domain-model.md §2.2）
    watcherCount: dto.subscribers_count,
    forkCount: dto.forks_count,
    openIssueCount: dto.open_issues_count,
    lastPushedAt: lastPushedAtOf(dto.pushed_at, dto.updated_at),
    topics: dto.topics ?? [],
    htmlUrl: dto.html_url,
  }
}
