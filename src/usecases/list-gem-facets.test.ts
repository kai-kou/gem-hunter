import { describe, expect, it } from 'vitest'

import type { DigestMeta, Gem } from '../domain/model/gem'
import { gemIndex, gemIndexValue } from '../domain/model/gem-index'
import type { GemDigestPort } from '../domain/ports/gem-digest-port'
import { makeListGemFacets } from './list-gem-facets'

const meta: DigestMeta = {
  source: 'Ecosyste.ms',
  license: 'CC BY-SA 4.0',
  sourceLicenseUrl: 'https://creativecommons.org/licenses/by-sa/4.0/',
  generatedAt: '2026-08-20T00:00:00Z',
}

function gem(repositoryFullName: string, gi: number, dependentCount = 100): Gem {
  return {
    packageName: repositoryFullName.split('/')[1],
    repositoryFullName,
    dependentCount,
    stars: 10,
    gemIndex: gemIndex(gi),
  }
}

function fakePort(candidates: readonly Gem[]): GemDigestPort {
  return {
    async listCandidates() {
      return { candidates, meta }
    },
  }
}

describe('listGemFacets', () => {
  it('候補プールを gemFacetKey → GemFacet のマップへ変換する', async () => {
    const listGemFacets = makeListGemFacets({
      gems: fakePort([gem('facebook/react', -0.5, 500)]),
    })

    const facets = await listGemFacets()

    expect(facets.size).toBe(1)
    const facet = facets.get('facebook/react')
    expect(facet).toBeDefined()
    expect(gemIndexValue(facet!.gemIndex)).toBe(-0.5)
    expect(facet!.dependentCount).toBe(500)
  })

  it('突合キーは owner/repo を小文字化する（GitHub の大文字小文字非区別）', async () => {
    const listGemFacets = makeListGemFacets({
      gems: fakePort([gem('Facebook/React', -0.5)]),
    })

    const facets = await listGemFacets()

    expect(facets.has('facebook/react')).toBe(true)
  })

  it('同一リポジトリが複数パッケージで重複するときは Gem Index が小さい方を残す', async () => {
    const listGemFacets = makeListGemFacets({
      gems: fakePort([gem('owner/repo', -0.2), gem('owner/repo', -0.9)]),
    })

    const facets = await listGemFacets()

    expect(gemIndexValue(facets.get('owner/repo')!.gemIndex)).toBe(-0.9)
  })

  it('候補プールが空でも空マップを返す', async () => {
    const listGemFacets = makeListGemFacets({ gems: fakePort([]) })

    const facets = await listGemFacets()

    expect(facets.size).toBe(0)
  })
})
