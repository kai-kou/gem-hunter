/** リポジトリのオーナー（個人・Organization を区別しない）。 */
export type Owner = {
  readonly login: string
  readonly avatarUrl: string
}

/** 一覧に出す粒度のリポジトリ。詳細画面の粒度は SP-3 で別途定義する。 */
export type RepositorySummary = {
  readonly id: number
  readonly name: string
  readonly fullName: string
  readonly owner: Owner
  readonly description: string | null
  readonly primaryLanguage: string | null
  readonly stars: number
  readonly updatedAt: Date
  readonly topics: readonly string[]
  readonly htmlUrl: string
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
  readonly watchers: number
  readonly forks: number
  readonly openIssues: number
  readonly updatedAt: Date
  readonly topics: readonly string[]
  readonly htmlUrl: string
}
