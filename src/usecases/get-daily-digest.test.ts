import { describe, expect, it } from 'vitest'

import type { DateSeed } from '../domain/model/date-seed'
import type { DigestMeta, Gem } from '../domain/model/gem'
import { gemIndex, gemIndexValue } from '../domain/model/gem-index'
import type { GemDigestPort } from '../domain/ports/gem-digest-port'
import { makeGetDailyDigest } from './get-daily-digest'

function gem(packageName: string, gi: number): Gem {
  return {
    packageName,
    repositoryFullName: `owner/${packageName}`,
    dependentCount: 100,
    stars: 10,
    gemIndex: gemIndex(gi),
  }
}

const meta: DigestMeta = {
  source: 'Ecosyste.ms',
  license: 'CC BY-SA 4.0',
  sourceLicenseUrl: 'https://creativecommons.org/licenses/by-sa/4.0/',
  generatedAt: '2026-08-20T00:00:00Z',
}

function fakePort(candidates: readonly Gem[]): GemDigestPort {
  return {
    async listCandidates() {
      return { candidates, meta }
    },
  }
}

// 20 件の候補プール。Gem Index はそれぞれ -0.5 .. -0.31（asc で並ぶ）
const candidates: Gem[] = Array.from({ length: 20 }, (_, i) =>
  gem(`pkg-${String(i).padStart(2, '0')}`, -0.5 + i * 0.01),
)

describe('getDailyDigest', () => {
  it('同じ seed では毎回同じ items を返す（決定論性・ADR 0014 §2.2）', async () => {
    const seed = '20260820' as DateSeed
    const getDailyDigest = makeGetDailyDigest({ port: fakePort(candidates) })

    const a = await getDailyDigest({ seed, limit: 5 })
    const b = await getDailyDigest({ seed, limit: 5 })

    expect(a.items.map((x) => x.packageName)).toEqual(b.items.map((x) => x.packageName))
  })

  it('違う seed では顔ぶれが変わる（US-31）', async () => {
    const getDailyDigest = makeGetDailyDigest({ port: fakePort(candidates) })

    const a = await getDailyDigest({ seed: '20260820' as DateSeed, limit: 5 })
    const b = await getDailyDigest({ seed: '20260821' as DateSeed, limit: 5 })
    const c = await getDailyDigest({ seed: '20260901' as DateSeed, limit: 5 })

    const namesA = a.items.map((x) => x.packageName).join(',')
    const namesB = b.items.map((x) => x.packageName).join(',')
    const namesC = c.items.map((x) => x.packageName).join(',')

    // 3 seed のうち少なくとも 1 組は違う顔ぶれになる（SHA-256 の分散を前提とする決定論的検証）
    const distinct = new Set([namesA, namesB, namesC]).size
    expect(distinct).toBeGreaterThanOrEqual(2)
  })

  it('limit で先頭 N 件に切り詰める', async () => {
    const getDailyDigest = makeGetDailyDigest({ port: fakePort(candidates) })

    const result = await getDailyDigest({ seed: '20260820' as DateSeed, limit: 3 })

    expect(result.items).toHaveLength(3)
  })

  it('候補プールが空でも例外を投げず items:[] を返す（D-28 SPOF 方針）', async () => {
    const getDailyDigest = makeGetDailyDigest({ port: fakePort([]) })

    const result = await getDailyDigest({ seed: '20260820' as DateSeed, limit: 5 })

    expect(result.items).toEqual([])
    expect(result.date).toBe('20260820')
    expect(result.meta).toEqual(meta)
  })

  it('候補数 <= limit のときは全件返す', async () => {
    const small = candidates.slice(0, 3)
    const getDailyDigest = makeGetDailyDigest({ port: fakePort(small) })

    const result = await getDailyDigest({ seed: '20260820' as DateSeed, limit: 5 })

    expect(result.items).toHaveLength(3)
  })

  it('選ばれたサブセット内は Gem Index asc（過小評価度が高い順）で並ぶ', async () => {
    const getDailyDigest = makeGetDailyDigest({ port: fakePort(candidates) })

    const result = await getDailyDigest({ seed: '20260820' as DateSeed, limit: 5 })

    const values = result.items.map((x) => gemIndexValue(x.gemIndex))
    const sorted = [...values].sort((a, b) => a - b)
    expect(values).toEqual(sorted)
  })

  it('meta と date を素通しする', async () => {
    const getDailyDigest = makeGetDailyDigest({ port: fakePort(candidates) })

    const result = await getDailyDigest({ seed: '20260820' as DateSeed, limit: 5 })

    expect(result.meta).toEqual(meta)
    expect(result.date).toBe('20260820')
  })

  it('limit <= 0 なら items:[]（Math.random 非依存の防御）', async () => {
    const getDailyDigest = makeGetDailyDigest({ port: fakePort(candidates) })

    const result = await getDailyDigest({ seed: '20260820' as DateSeed, limit: 0 })

    expect(result.items).toEqual([])
  })
})
