import { z } from 'zod'

/**
 * GitHub API のレスポンススキーマ（NFR-19）。
 * 🔴 アプリが実際に使うフィールドだけを宣言する（全項目を写さない）。
 */
/**
 * `href` へ流す URL の検証（`NFR-19` の入力検証・多層防御の最上流）。
 *
 * 🔴 `z.string()` のままでは `javascript:` / `data:` のような擬似スキームを素通しする。
 *    `html_url` は詳細画面のタイトルリンク（`src/ui/repository-detail.tsx`）で `href` に
 *    直結するため、URL 形式と https スキームをここで確定させる。
 * 🔴 **fail-closed**: 実 GitHub API は常に `https://github.com/...` を返すので、外れる応答は
 *    「安全な既定値へ丸める」のではなく上流異常（`UpstreamError`）として倒す（`private`
 *    フィールドと同じ判断）。UI 層で毎回スキームを確かめる分岐を増やさずに済む。
 */
const httpsUrl = z.url().refine((value) => value.startsWith('https://'), {
  message: 'must use the https scheme',
})

export const ownerDto = z.object({
  login: z.string(),
  avatar_url: z.string(),
})

export const repositoryDto = z.object({
  id: z.number(),
  name: z.string(),
  full_name: z.string(),
  html_url: httpsUrl,
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
  html_url: httpsUrl,
  description: z.string().nullable(),
  language: z.string().nullable(),
  stargazers_count: z.number(),
  subscribers_count: z.number(),
  forks_count: z.number(),
  open_issues_count: z.number(),
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
