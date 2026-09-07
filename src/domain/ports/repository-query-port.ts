import type { RepositoryDetail, SearchResult } from '../model/repository'
import type { RepositoryFullName } from '../model/repository-full-name'
import type { SearchQuery } from '../model/search-query'

/**
 * リポジトリ情報の取得口（NFR-16）。
 * 実装は src/infrastructure/ 側に置き、composition root で束ねる。
 */
export interface RepositoryQueryPort {
  /**
   * 検索条件に合致するリポジトリの一覧を取得する。
   *
   * @param query 検索条件（`SearchQuery` 値オブジェクト。キーワード・ページ・並び順等の
   *   値域はその生成関数側で保証済み）。
   * @returns 合致したリポジトリの一覧（ページ分）。
   *
   * 🔴 **異常時の振る舞い**: 例外を投げる。上流 API 呼び出しが非 2xx・ネットワーク到達不能・
   *   レート制限等で失敗した場合、`NetworkError` / `NotFoundError` / `RateLimitExceededError` /
   *   `AuthError` / `SearchQueryRejectedError` / `UpstreamError`（`src/domain/errors.ts`）の
   *   いずれかを throw する（実装: `src/infrastructure/github/github-repository-query.ts` の
   *   `search` / `toDomainError`）。空配列へフォールバックすることはしない。
   */
  search(query: SearchQuery): Promise<SearchResult>
  /**
   * 単一リポジトリを owner/repo で取得する。
   *
   * @param name 取得対象のリポジトリ完全名（`RepositoryFullName` 値オブジェクト。owner/repo の
   *   形式的妥当性はその生成関数側で保証済み）。
   * @returns 対象が存在すればその詳細、**存在しない場合（HTTP 404）は例外にせず `null`** を返す。
   *
   * 🔴 **異常時の振る舞い**: 404 以外の失敗（ネットワーク到達不能・非 2xx・レート制限等）は
   *   例外を投げる。`null` は「対象が存在しない」専用であり、異常系をここに紛れ込ませない
   *   （実装: `src/infrastructure/github/github-repository-query.ts` の `findDetail` /
   *   `fetchWithConditionalCache`）。
   */
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
