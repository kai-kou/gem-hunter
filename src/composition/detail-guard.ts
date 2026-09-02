import { headers } from 'next/headers'
import type { RepositoryDetail } from '../domain/model/repository'
import type { GetRepositoryDetailInput } from '../usecases/get-repository-detail'
import { getRepositoryDetailUseCase } from './container'
import { enforceDetailRateLimit } from './rate-limit'

/**
 * composition root（Issue #190）。`app/[locale]/repos/[owner]/[repo]/page.tsx` にオーケストレー
 * ションとして書かれていた「詳細取得の自リクエスト間引き（Issue #122 の `RateLimitPort`）→
 * 実際の取得（`getRepositoryDetailUseCase`）」という順序判断を、検索経路の `prepareSearchKeyword`
 * （`src/composition/search-guard.ts`）と同じ形で 1 本へ集約する（`app/` は composition root から
 * ユースケースを取り結果を渡すだけ、という `application-architecture.md` の層規律を満たすため）。
 *
 * 命名は姉妹関数 `prepareSearchKeyword` に倣いたかったが、この関数は変換ではなく取得そのものを
 * 返す（呼び出し側は戻り値をそのまま `repository` として使う）ため、「取得する」という語感が
 * 呼び出し側の意図に一番近いと判断し `fetch` を選んだ（本プロジェクトの既存命名
 * `enforce*` / `prepare*` / `get*UseCase` のうち、値を実際に取ってくる関数は `get*` /
 * `fetch*` 系に寄せている）。
 *
 * 🔴 **順序が仕様**: 間引きは必ず取得（GitHub API 呼び出し）より前に行う。超過時に投げる
 * `RateLimitExceededError` はそのまま伝播させ、呼び出し側の `catch (error instanceof
 * DomainError)` に委ねる（詳細取得自体の失敗＝`rateLimitPrimary` 等と同じローカライズ済み
 * `ErrorNotice` 表示を再利用し、新しい表示分岐を増やさない）。
 *
 * 🔵 **`headers()` は呼び出し側から受け取らず、ここで自分で呼ぶ**。`getSessionAccessToken()`
 * （`src/infrastructure/platform/session-cookie.ts` が内部で `cookies()` を呼ぶ）と同じ流儀
 * （Next.js のリクエストスコープ API はページ側へ運ばず composition 層に隠す）を踏襲する。
 * `prepareSearchKeyword` が外部から `headers` を受け取るのは、画面 (`await headers()`) と
 * API Route (`request.headers`) の 2 つの取得元を切り替える必要があるため（本関数の呼び出し元は
 * 画面 1 箇所のみで、切り替えの要がない）。
 *
 * @param accessToken セッションのアクセストークン（未ログインは `null`）。SP-8: 渡すとユーザー
 *   自身のレート枠で取得する（省略時は installation token）。
 * @param input 対象リポジトリ（owner/repo）。
 * @returns 取得できたリポジトリ詳細（見つからない場合は `null`）。
 */
export async function fetchRepositoryDetail(
  accessToken: string | null,
  input: GetRepositoryDetailInput,
): Promise<RepositoryDetail | null> {
  await enforceDetailRateLimit(await headers())
  return getRepositoryDetailUseCase(accessToken)(input)
}

/**
 * 素通し re-export（README 取得。レート制限の対象外・本ファイルの関心とは無関係）。
 *
 * 詳細ページ（`app/[locale]/repos/[owner]/[repo]/page.tsx`）が composition root から必要とする
 * 呼び出し口を本ファイル 1 モジュールへまとめ、ページ側の import 文を 1 行に保つための単純な
 * 転送。ページ側が `container.ts` と本ファイルの 2 モジュールを個別に import すると、
 * `tools/check_app_thinness.py`（`app/` の行数上限）を機能追加のたびに押し上げてしまうため
 * （Issue #190 セルフレビュー指摘・詳細は同 Issue のコメント）。
 */
export { getRepositoryReadmeUseCase } from './container'
