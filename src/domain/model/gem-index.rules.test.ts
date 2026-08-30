import { describe, expect, it } from 'vitest'

import {
  RANK_MAX,
  RANK_MIN,
  computeGemIndexValue,
  isValidRank,
} from './gem-index.rules.mjs'

describe('gem-index.rules（算出式と値域規則の単一正本）', () => {
  describe('isValidRank', () => {
    it('境界値（0 / 100）を受け入れる', () => {
      expect(isValidRank(RANK_MIN)).toBe(true)
      expect(isValidRank(RANK_MAX)).toBe(true)
      expect(isValidRank(50)).toBe(true)
    })

    it('値域外（負数・100 超）を拒否する', () => {
      expect(isValidRank(-0.001)).toBe(false)
      expect(isValidRank(100.001)).toBe(false)
    })

    it('非有限数（NaN / ±Infinity）を拒否する', () => {
      expect(isValidRank(Number.NaN)).toBe(false)
      expect(isValidRank(Number.POSITIVE_INFINITY)).toBe(false)
      expect(isValidRank(Number.NEGATIVE_INFINITY)).toBe(false)
    })

    it('数値以外を拒否する（外部 API 由来の値が素通りしない）', () => {
      expect(isValidRank(undefined as unknown as number)).toBe(false)
      expect(isValidRank(null as unknown as number)).toBe(false)
      expect(isValidRank('50' as unknown as number)).toBe(false)
    })
  })

  describe('computeGemIndexValue', () => {
    it('被依存数の順位 − star の順位を返す（丸めない）', () => {
      expect(computeGemIndexValue(0.0005476, 0.6435)).toBeCloseTo(0.0005476 - 0.6435, 10)
    })

    it('同順位なら 0', () => {
      expect(computeGemIndexValue(50, 50)).toBe(0)
    })

    it('🔴 向きの正本: 被依存数が上位（小さい）・star が下位（大きい）なら負値', () => {
      // 値が小さいほど過小評価度が高い（`ADR 0009` §2.1 / `D-28` 訂正注記）。
      expect(computeGemIndexValue(0, 100)).toBe(-100)
      expect(computeGemIndexValue(100, 0)).toBe(100)
    })
  })

  it('値域定数が rankings の仕様（0 が最上位・0〜100）と一致する', () => {
    expect(RANK_MIN).toBe(0)
    expect(RANK_MAX).toBe(100)
  })
})
