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
  updated_at: z.string(),
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
  topics: z.array(z.string()).optional(),
  owner: ownerDto,
})

export type RepositoryDetailDto = z.infer<typeof repositoryDetailDto>
