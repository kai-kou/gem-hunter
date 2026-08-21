import type { RepositoryDetail, SearchResult } from '../model/repository'
import type { RepositoryFullName } from '../model/repository-full-name'
import type { SearchQuery } from '../model/search-query'

/**
 * リポジトリ情報の取得口（NFR-16）。
 * 実装は src/infrastructure/ 側に置き、composition root で束ねる。
 */
export interface RepositoryQueryPort {
  /** 検索条件に合致するリポジトリの一覧を取得する。 */
  search(query: SearchQuery): Promise<SearchResult>
  /** 単一リポジトリを owner/repo で取得する。存在しない場合は例外にせず null を返す（404 → null）。 */
  findDetail(name: RepositoryFullName): Promise<RepositoryDetail | null>
  /**
   * 単一リポジトリの README を **GitHub がレンダリング済みの HTML 文字列** として取得する
   * （Issue #334 F-4）。README が存在しない場合は例外にせず null を返す（404 → null）。
   *
   * 🔴 戻り値は **未サニタイズの第三者由来 HTML** である。表示前に必ずサニタイズすること
   * （`src/ui/` 側の責務。ACL は取得のみを行い、表示都合の加工を持ち込まない）。
   * 🔴 非公開リポジトリの遮断は本メソッドでは行えない（README のレスポンスに `private` が無い）。
   * 呼び出しは必ず `findDetail` の判定を通す usecase（`get-repository-readme.ts`）経由にする
   * （`NFR-33` / `AC-12`）。
   */
  findReadme(name: RepositoryFullName): Promise<string | null>
}
