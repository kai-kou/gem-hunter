import { tryRepositoryFullName } from '../domain/model/repository-full-name'
import type { RepositoryQueryPort } from '../domain/ports/repository-query-port'

export type GetRepositoryReadmeInput = { owner: string; repo: string }

/**
 * README を **GitHub がレンダリング済みの未サニタイズ HTML** として返す（Issue #334 F-4）。
 * README が存在しない・取得に失敗した場合は null（サニタイズは呼び出し元の `src/ui/` 側の責務）。
 */
export type GetRepositoryReadme = (input: GetRepositoryReadmeInput) => Promise<string | null>

/**
 * README 取得の private ゲート（`NFR-33` / `AC-12`・whiteboard round3 lead 裁定）。
 *
 * 🔴 `findReadme` のレスポンスには `private` フィールドが無く、それ単体では非公開リポジトリを
 * 判別できない。必ず `findDetail`（公開判定済み・非公開なら null を返す ACL）を先に経由し、
 * `null` なら `findReadme` を **呼ばずに** null を返す。呼び出し元の順序に依存させないため、
 * このゲートは usecase 内に埋め込む（`get-repository-detail.ts` を先に呼ぶ規約に頼らない）。
 */
export function makeGetRepositoryReadme(deps: { repos: RepositoryQueryPort }): GetRepositoryReadme {
  return async (input) => {
    const name = tryRepositoryFullName(input.owner, input.repo)
    if (name === null) {
      return null
    }

    const detail = await deps.repos.findDetail(name)
    if (detail === null) {
      return null
    }

    return deps.repos.findReadme(name)
  }
}
