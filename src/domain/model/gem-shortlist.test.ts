import { describe, expect, it } from 'vitest'

import type { Gem } from './gem'
import { gemIndex, gemIndexValue } from './gem-index'
import { GEM_INDEX_SHORTLIST_SIZE, byGemIndexAsc, selectGemIndexShortlist } from './gem-shortlist'

function gem(packageName: string, gi: number): Gem {
  return {
    packageName,
    repositoryFullName: `owner/${packageName}`,
    dependentCount: 100,
    stars: 10,
    gemIndex: gemIndex(gi),
  }
}

describe('byGemIndexAsc', () => {
  it('Gem Index が小さいほど上位（昇順）に並べる', () => {
    const items = [gem('b', 0.5), gem('a', -0.5), gem('c', 0)]
    const sorted = [...items].sort(byGemIndexAsc)
    expect(sorted.map((g) => g.packageName)).toEqual(['a', 'c', 'b'])
  })

  it('同値のときは 0 を返す（タイブレークしない）', () => {
    expect(byGemIndexAsc(gem('a', 0), gem('b', 0))).toBe(0)
  })
})

describe('selectGemIndexShortlist', () => {
  it('Gem Index asc で上位 size 件を選ぶ', () => {
    const candidates = Array.from({ length: 10 }, (_, i) => gem(`pkg-${i}`, -10 + i))

    const shortlist = selectGemIndexShortlist(candidates, 3)

    expect(shortlist.map((g) => g.packageName)).toEqual(['pkg-0', 'pkg-1', 'pkg-2'])
    expect(shortlist.map((g) => gemIndexValue(g.gemIndex))).toEqual([-10, -9, -8])
  })

  it('同値は packageName asc でタイブレークする（入力順に依存しない）', () => {
    const tied = ['zeta', 'alpha', 'mike'].map((name) => gem(name, 0))

    const shortlistA = selectGemIndexShortlist(tied, 2)
    const shortlistB = selectGemIndexShortlist([...tied].reverse(), 2)

    expect(shortlistA.map((g) => g.packageName)).toEqual(['alpha', 'mike'])
    expect(shortlistB.map((g) => g.packageName)).toEqual(['alpha', 'mike'])
  })

  it('size が候補数を超えるときは全件を返す', () => {
    const candidates = Array.from({ length: 3 }, (_, i) => gem(`pkg-${i}`, i))

    const shortlist = selectGemIndexShortlist(candidates, 100)

    expect(shortlist).toHaveLength(3)
  })

  it('size が候補数と等しいときは全件を Gem Index asc で返す', () => {
    const candidates = [gem('b', 1), gem('a', 0)]

    const shortlist = selectGemIndexShortlist(candidates, 2)

    expect(shortlist.map((g) => g.packageName)).toEqual(['a', 'b'])
  })

  it('size が 0 以下のときは空配列を返す', () => {
    const candidates = Array.from({ length: 3 }, (_, i) => gem(`pkg-${i}`, i))

    expect(selectGemIndexShortlist(candidates, 0)).toEqual([])
    expect(selectGemIndexShortlist(candidates, -1)).toEqual([])
  })

  it('候補が空のときは空配列を返す', () => {
    expect(selectGemIndexShortlist([], GEM_INDEX_SHORTLIST_SIZE)).toEqual([])
  })

  it('入力配列を変更しない（非破壊）', () => {
    const candidates = [gem('b', 1), gem('a', 0)]
    const originalOrder = candidates.map((g) => g.packageName)

    selectGemIndexShortlist(candidates, 1)

    expect(candidates.map((g) => g.packageName)).toEqual(originalOrder)
  })
})
