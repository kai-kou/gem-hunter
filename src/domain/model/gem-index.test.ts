import { describe, expect, it } from 'vitest'

import { DomainValidationError } from '../errors'
import type { Gem } from './gem'
import {
  computeGemIndex,
  gemFacetKey,
  gemIndex,
  gemIndexValue,
  sortByGemIndex,
  toGemFacetMap,
} from './gem-index'

describe('gemIndex', () => {
  it('有限数を包める（負値・ゼロ・正値）', () => {
    expect(gemIndexValue(gemIndex(0.5))).toBe(0.5)
    expect(gemIndexValue(gemIndex(-0.3))).toBe(-0.3)
    expect(gemIndexValue(gemIndex(0))).toBe(0)
  })

  it('有限数以外（NaN / ±Infinity）は DomainValidationError', () => {
    expect(() => gemIndex(Number.NaN)).toThrow(DomainValidationError)
    expect(() => gemIndex(Number.POSITIVE_INFINITY)).toThrow(DomainValidationError)
    expect(() => gemIndex(Number.NEGATIVE_INFINITY)).toThrow(DomainValidationError)
  })

  it('gemIndexValue でブランドを外して素の数値に戻せる', () => {
    const g = gemIndex(0.42)
    const v: number = gemIndexValue(g)
    expect(v).toBe(0.42)
  })
})

describe('computeGemIndex', () => {
  // Ecosyste.ms の rankings は 0〜100 で 0 が最上位（open-questions.md D-28 訂正注記）。
  // 被依存数が上位（値が小さい）・star が下位（値が大きい）なら差は負になり、
  // 「値が小さいほど過小評価度が高い（= Gem として上位）」の並び意味になる。
  it('chalk 相当（dependentRank=0.0005476 / starRank=0.6435）で強い負値を返す', () => {
    const g = computeGemIndex(0.0005476, 0.6435)
    // 🔴 期待値は丸めた定数ではなく式で書く。`toBeCloseTo(-0.643, 4)` は許容誤差 5e-5 に対し
    //    実差が約 4.8e-5（許容幅の 95%）で、実装が僅かに変わるだけで偽陽性・偽陰性に転ぶ。
    expect(gemIndexValue(g)).toBeCloseTo(0.0005476 - 0.6435, 10)
    expect(gemIndexValue(g)).toBeLessThan(0)
  })

  it('被依存数と star が同順位なら 0（過小評価なし）', () => {
    expect(gemIndexValue(computeGemIndex(50, 50))).toBe(0)
  })

  it('被依存数が下位・star が上位なら正値（過大評価）', () => {
    // GitHub Trending 的な「star ばかり多く実利用が少ない」ケース
    const g = computeGemIndex(80, 5)
    expect(gemIndexValue(g)).toBe(75)
    expect(gemIndexValue(g)).toBeGreaterThan(0)
  })

  it('値域外（負数・100 超・NaN）を拒否する', () => {
    expect(() => computeGemIndex(-1, 50)).toThrow(DomainValidationError)
    expect(() => computeGemIndex(50, -0.001)).toThrow(DomainValidationError)
    expect(() => computeGemIndex(101, 50)).toThrow(DomainValidationError)
    expect(() => computeGemIndex(50, 100.001)).toThrow(DomainValidationError)
    expect(() => computeGemIndex(Number.NaN, 50)).toThrow(DomainValidationError)
    expect(() => computeGemIndex(50, Number.NaN)).toThrow(DomainValidationError)
    expect(() => computeGemIndex(Number.POSITIVE_INFINITY, 50)).toThrow(DomainValidationError)
  })

  it('境界値（0 / 100）を受け入れる', () => {
    expect(gemIndexValue(computeGemIndex(0, 100))).toBe(-100)
    expect(gemIndexValue(computeGemIndex(100, 0))).toBe(100)
    expect(gemIndexValue(computeGemIndex(0, 0))).toBe(0)
    expect(gemIndexValue(computeGemIndex(100, 100))).toBe(0)
  })
})

function makeGem(overrides: {
  repositoryFullName: string
  gemIndex: number
  packageName?: string
  dependentCount?: number
  stars?: number
}): Gem {
  return {
    packageName: overrides.packageName ?? `pkg-${overrides.repositoryFullName}`,
    repositoryFullName: overrides.repositoryFullName,
    dependentCount: overrides.dependentCount ?? 0,
    stars: overrides.stars ?? 0,
    gemIndex: gemIndex(overrides.gemIndex),
  }
}

describe('gemFacetKey', () => {
  it('大文字小文字差を吸収する', () => {
    expect(gemFacetKey('Facebook/React')).toBe(gemFacetKey('facebook/react'))
  })

  it('同じ入力に対して決定論的である', () => {
    expect(gemFacetKey('acme/widget')).toBe(gemFacetKey('acme/widget'))
  })
})

describe('toGemFacetMap', () => {
  it('候補プールからキー → GemFacet のマップを作る', () => {
    const candidates: readonly Gem[] = [
      makeGem({ repositoryFullName: 'facebook/react', gemIndex: -10, dependentCount: 500 }),
      makeGem({ repositoryFullName: 'acme/widget', gemIndex: 5, dependentCount: 3 }),
    ]

    const map = toGemFacetMap(candidates)

    expect(map.get(gemFacetKey('facebook/react'))).toEqual({
      gemIndex: gemIndex(-10),
      dependentCount: 500,
    })
    expect(map.get(gemFacetKey('acme/widget'))).toEqual({
      gemIndex: gemIndex(5),
      dependentCount: 3,
    })
  })

  it('突合キーは大文字小文字差を吸収する', () => {
    const candidates: readonly Gem[] = [
      makeGem({ repositoryFullName: 'Facebook/React', gemIndex: -10, dependentCount: 500 }),
    ]

    const map = toGemFacetMap(candidates)

    expect(map.get(gemFacetKey('facebook/react'))).toEqual({
      gemIndex: gemIndex(-10),
      dependentCount: 500,
    })
  })

  it('同一リポジトリが複数パッケージで重複する場合、Gem Index が小さい方（より過小評価な方）を残す', () => {
    const candidates: readonly Gem[] = [
      makeGem({
        repositoryFullName: 'acme/widget',
        packageName: 'widget-a',
        gemIndex: 5,
        dependentCount: 1,
      }),
      makeGem({
        repositoryFullName: 'acme/widget',
        packageName: 'widget-b',
        gemIndex: -20,
        dependentCount: 2,
      }),
      makeGem({
        repositoryFullName: 'acme/widget',
        packageName: 'widget-c',
        gemIndex: 3,
        dependentCount: 3,
      }),
    ]

    const map = toGemFacetMap(candidates)

    expect(map.get(gemFacetKey('acme/widget'))).toEqual({
      gemIndex: gemIndex(-20),
      dependentCount: 2,
    })
  })

  it('空配列に対しては空のマップを返す', () => {
    expect(toGemFacetMap([]).size).toBe(0)
  })
})

describe('sortByGemIndex', () => {
  type Item = { readonly fullName: string; readonly label: string }

  it('facets を持つ項目を Gem Index 昇順（値が小さいほど上位）で並べる', () => {
    const items: readonly Item[] = [
      { fullName: 'a/a', label: 'a' },
      { fullName: 'b/b', label: 'b' },
      { fullName: 'c/c', label: 'c' },
    ]
    const facets = new Map([
      [gemFacetKey('a/a'), { gemIndex: gemIndex(5), dependentCount: 0 }],
      [gemFacetKey('b/b'), { gemIndex: gemIndex(-5), dependentCount: 0 }],
      [gemFacetKey('c/c'), { gemIndex: gemIndex(0), dependentCount: 0 }],
    ])

    const sorted = sortByGemIndex(items, facets)

    expect(sorted.map((x) => x.label)).toEqual(['b', 'c', 'a'])
  })

  it('facets に無い項目は元の相対順を保ったまま末尾へ回す（安定ソート）', () => {
    const items: readonly Item[] = [
      { fullName: 'no-facet-1', label: 'nf1' },
      { fullName: 'has-facet', label: 'hf' },
      { fullName: 'no-facet-2', label: 'nf2' },
    ]
    const facets = new Map([[gemFacetKey('has-facet'), { gemIndex: gemIndex(1), dependentCount: 0 }]])

    const sorted = sortByGemIndex(items, facets)

    expect(sorted.map((x) => x.label)).toEqual(['hf', 'nf1', 'nf2'])
  })

  it('facets が空なら元の相対順のまま全件が末尾（＝先頭から）に残る', () => {
    const items: readonly Item[] = [
      { fullName: 'x/x', label: 'x' },
      { fullName: 'y/y', label: 'y' },
    ]

    const sorted = sortByGemIndex(items, new Map())

    expect(sorted.map((x) => x.label)).toEqual(['x', 'y'])
  })

  it('大文字小文字が異なる fullName でも facets と突合できる', () => {
    const items: readonly Item[] = [{ fullName: 'Facebook/React', label: 'react' }]
    const facets = new Map([
      [gemFacetKey('facebook/react'), { gemIndex: gemIndex(-1), dependentCount: 0 }],
    ])

    const sorted = sortByGemIndex(items, facets)

    expect(sorted.map((x) => x.label)).toEqual(['react'])
  })

  it('同じ Gem Index を持つ項目同士は元の相対順を保つ（安定ソート）', () => {
    const items: readonly Item[] = [
      { fullName: 'a/a', label: 'a' },
      { fullName: 'b/b', label: 'b' },
    ]
    const facets = new Map([
      [gemFacetKey('a/a'), { gemIndex: gemIndex(1), dependentCount: 0 }],
      [gemFacetKey('b/b'), { gemIndex: gemIndex(1), dependentCount: 0 }],
    ])

    const sorted = sortByGemIndex(items, facets)

    expect(sorted.map((x) => x.label)).toEqual(['a', 'b'])
  })

  it('入力配列を変更しない（イミュータブル）', () => {
    const items: readonly Item[] = [
      { fullName: 'a/a', label: 'a' },
      { fullName: 'b/b', label: 'b' },
    ]
    const original = [...items]
    const facets = new Map([
      [gemFacetKey('a/a'), { gemIndex: gemIndex(5), dependentCount: 0 }],
      [gemFacetKey('b/b'), { gemIndex: gemIndex(-5), dependentCount: 0 }],
    ])

    sortByGemIndex(items, facets)

    expect(items).toEqual(original)
  })
})
