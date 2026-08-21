import type { GemFacet } from '../domain/model/gem'
import { toGemFacetMap } from '../domain/model/gem-index'
import type { GemDigestPort } from '../domain/ports/gem-digest-port'

export type ListGemFacets = () => Promise<ReadonlyMap<string, GemFacet>>

/**
 * カード表示用に、候補プールから Gem Index ファセット（`gemFacetKey` → `GemFacet`）を返す（`SP-16`）。
 *
 * `gem-index` 順ソートのときだけ UI がカードへ Gem Index 値と被依存数を追記する（`whiteboard` D-L）。
 * 突合ロジック（重複時は Gem Index が小さい方を残す）は `toGemFacetMap` が持つため、本ユースケースは
 * `GemDigestPort` から候補を読んでそのまま渡すだけの薄い層に留める（YAGNI）。
 */
export function makeListGemFacets(deps: { gems: GemDigestPort }): ListGemFacets {
  return async () => {
    const { candidates } = await deps.gems.listCandidates()
    return toGemFacetMap(candidates)
  }
}
