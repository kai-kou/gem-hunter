import type { GemIndex } from './gem-index'

/** リポジトリのオーナー（個人・Organization を区別しない）。 */
export type Owner = {
  readonly login: string
  readonly avatarUrl: string
}

/**
 * 一覧に出す粒度のリポジトリ。詳細画面の粒度は SP-3 で別途定義する。
 *
 * 🔴 `gemIndex` / `dependentCount` は例外的に Gem Index コンテキストから注入される
 * optional フィールド（`SP-16`・`domain-model.md` §3 / §6）。usecase 層の join で埋まらな
 * かった場合（候補プールに存在しない・`sort !== 'gemIndex'` で join 自体を行わない）は
 * `undefined` のままにする。この 2 フィールド以外は Gem Index コンテキストの属性を持ち込まない。
 */
export type RepositorySummary = {
  readonly id: number
  readonly name: string
  readonly fullName: string
  readonly owner: Owner
  readonly description: string | null
  readonly primaryLanguage: string | null
  readonly stars: number
  readonly lastPushedAt: Date
  readonly topics: readonly string[]
  readonly htmlUrl: string
  /** 過小評価度（`ADR 0009`）。候補プールに存在しないリポジトリは `undefined`。 */
  readonly gemIndex?: GemIndex
  /** 被依存パッケージ数（Ecosyste.ms `dependent_packages_count`）。`gemIndex` と同時にのみ埋まる。 */
  readonly dependentCount?: number
}

/** 検索の結果セット。 */
export type SearchResult = {
  readonly totalCount: number
  readonly incompleteResults: boolean
  readonly items: readonly RepositorySummary[]
}

/** 詳細画面の粒度のリポジトリ（prd.md §8.2）。 */
export type RepositoryDetail = {
  readonly id: number
  readonly name: string
  readonly fullName: string
  readonly owner: Owner
  readonly description: string | null
  readonly primaryLanguage: string | null
  readonly stars: number
  /** 🔴 Watcher 数は subscribers_count（watchers_count は star のミラーで誤用禁止・prd.md FR-4 注記） */
  readonly watcherCount: number
  readonly forkCount: number
  /** GitHub の open_issues_count は Pull Request を含む（domain-model.md §2.2）。 */
  readonly openIssueCount: number
  readonly topics: readonly string[]
  readonly htmlUrl: string
}
