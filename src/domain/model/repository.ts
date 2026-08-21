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
  readonly lastPushedAt: Date
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
  readonly watcherCount: number
  readonly forkCount: number
  /** GitHub の open_issues_count は Pull Request を含む（domain-model.md §2.2）。 */
  readonly openIssueCount: number
  /**
   * 最終更新日時。一覧（`RepositorySummary.lastPushedAt`）と **同じ算出規則**（`pushed_at`。
   * null の場合のみ `updated_at` へフォールバック）を使う（`domain-model.md` §2.2）。
   * 一覧と詳細で「最終更新」という同一概念に別のフィールドを当てると、画面遷移で値の意味が
   * 変わったように見えるため（Issue #334 F-3）。
   */
  readonly lastPushedAt: Date
  readonly topics: readonly string[]
  readonly htmlUrl: string
}
