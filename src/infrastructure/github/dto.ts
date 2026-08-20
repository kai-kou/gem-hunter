import { z } from 'zod'

/**
 * GitHub API のレスポンススキーマ（NFR-19）。
 * 🔴 アプリが実際に使うフィールドだけを宣言する（全項目を写さない）。
 */
export const ownerDto = z.object({
  login: z.string(),
  avatar_url: z.string(),
})

export const repositoryDto = z.object({
  id: z.number(),
  name: z.string(),
  full_name: z.string(),
  html_url: z.string(),
  description: z.string().nullable(),
  language: z.string().nullable(),
  stargazers_count: z.number(),
  // 🔴 コミット履歴のない空リポジトリでは null になる（GitHub API 仕様）。
  //    mapper.ts の toSearchResult で updated_at へのフォールバック元として使う。
  updated_at: z.string(),
  // 🔴 nullable（コミットが一度もない空リポジトリでは null になりうる）。
  //    非 null 前提で必須にすると、検索結果 30 件中 1 件でも該当した瞬間に zod パース全体が失敗する。
  pushed_at: z.string().nullable(),
  // 🔴 非公開リポジトリの判別に使う（installation token で認証すると、トークンから見える
  //    private リポジトリまで API の可視範囲に入るため・prd.md L171「公開リポジトリの検索」）。
  //    🔴 **必須**（fail-closed）: 欠落は「公開」と推定せず、上流異常（UpstreamError）として倒す。
  //    optional にすると、上流やプロキシがこのフィールドを落とした瞬間に NFR-33 の多層防御のうち
  //    2 層（検索結果の除外・詳細の 404 化）が同時に無効化される。実 GitHub API は常に返す。
  private: z.boolean(),
  topics: z.array(z.string()).optional(),
  owner: ownerDto,
})

export const searchRepositoriesDto = z.object({
  total_count: z.number(),
  incomplete_results: z.boolean().optional(),
  items: z.array(repositoryDto),
})

export type SearchRepositoriesDto = z.infer<typeof searchRepositoriesDto>

/**
 * GET /repos/{owner}/{repo} のレスポンススキーマ。
 * 🔴 Watcher 数は subscribers_count（watchers_count は star のミラーで誤用禁止・prd.md FR-4 注記）。
 */
export const repositoryDetailDto = z.object({
  id: z.number(),
  name: z.string(),
  full_name: z.string(),
  html_url: z.string(),
  description: z.string().nullable(),
  language: z.string().nullable(),
  stargazers_count: z.number(),
  subscribers_count: z.number(),
  forks_count: z.number(),
  open_issues_count: z.number(),
  updated_at: z.string(),
  // 🔴 非公開リポジトリの判別に使う（installation token で認証すると、トークンから見える
  //    private リポジトリまで API の可視範囲に入るため・prd.md L171「公開リポジトリの検索」）。
  //    🔴 **必須**（fail-closed）: 欠落は「公開」と推定せず、上流異常（UpstreamError）として倒す。
  //    optional にすると、上流やプロキシがこのフィールドを落とした瞬間に NFR-33 の多層防御のうち
  //    2 層（検索結果の除外・詳細の 404 化）が同時に無効化される。実 GitHub API は常に返す。
  private: z.boolean(),
  topics: z.array(z.string()).optional(),
  owner: ownerDto,
})

export type RepositoryDetailDto = z.infer<typeof repositoryDetailDto>
