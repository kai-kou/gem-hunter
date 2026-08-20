import { describe, expect, it } from 'vitest'

import { DomainValidationError } from '../errors'
import { computeGemIndex, gemIndex, gemIndexValue } from './gem-index'

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
