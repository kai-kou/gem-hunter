import { describe, expect, it } from 'vitest'

import type { DateSeed } from '../domain/model/date-seed'
import type { DigestMeta, Gem } from '../domain/model/gem'
import { gemIndex, gemIndexValue } from '../domain/model/gem-index'
import type { GemDigestPort } from '../domain/ports/gem-digest-port'
import { GEM_INDEX_SHORTLIST_SIZE, makeGetDailyDigest } from './get-daily-digest'

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

  it('連続する 2 日（20260820 → 20260821）で顔ぶれが必ず変わる（US-31 の本質）', async () => {
    const getDailyDigest = makeGetDailyDigest({ port: fakePort(candidates) })

    const a = await getDailyDigest({ seed: '20260820' as DateSeed, limit: 5 })
    const b = await getDailyDigest({ seed: '20260821' as DateSeed, limit: 5 })

    const namesA = a.items.map((x) => x.packageName)
    const namesB = b.items.map((x) => x.packageName)

    // 🔴 「3 seed 中 2 つ以上が異なる」という緩い判定にしない。US-31 が要求するのは
    //    「翌日にはもう違う」ことであり、連続する 2 日が同一なら機能として壊れている。
    expect(namesB).not.toEqual(namesA)
  })

  it('3 つの異なる seed がすべて異なる顔ぶれ / 並びになる（US-31）', async () => {
    const getDailyDigest = makeGetDailyDigest({ port: fakePort(candidates) })

    const seeds = ['20260820', '20260821', '20260901'] as const
    const names = await Promise.all(
      seeds.map(async (seed) => {
        const r = await getDailyDigest({ seed: seed as DateSeed, limit: 5 })
        return r.items.map((x) => x.packageName).join(',')
      }),
    )

    // 決定論的なので「たまたま通る」ことはない（毎回同じ入力・同じ出力）。
    expect(new Set(names).size).toBe(seeds.length)
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

  it('候補プールが limit 以下のときは Gem Index で再ソートせず、日付ごとに並びが変わる', async () => {
    // 🔴 縮退分岐（`get-daily-digest.ts` の `candidates.length <= limit`）の回帰テスト。
    //    全件が必ず選ばれるため、ここで Gem Index asc に上書きすると並びが日付に依存しなくなり
    //    US-31（毎日顔ぶれが変わる）が静かに壊れる。候補 5 件 / limit 5 で検証する。
    const small = candidates.slice(0, 5)
    const getDailyDigest = makeGetDailyDigest({ port: fakePort(small) })

    const day1 = await getDailyDigest({ seed: '20260820' as DateSeed, limit: 5 })
    const day2 = await getDailyDigest({ seed: '20260821' as DateSeed, limit: 5 })

    const names1 = day1.items.map((x) => x.packageName)
    const names2 = day2.items.map((x) => x.packageName)

    // 全件が出るので「顔ぶれ」は同じ。変わるのは **並び順**。
    expect([...names1].sort()).toEqual([...names2].sort())
    expect(names2).not.toEqual(names1)

    // Gem Index asc で上書きされていない（= シャッフル順のまま）ことを明示する。
    const values1 = day1.items.map((x) => gemIndexValue(x.gemIndex))
    expect(values1).not.toEqual([...values1].sort((a, b) => a - b))
  })

  it('候補プールが limit より多いときは選ばれたサブセットを Gem Index asc に並べる', async () => {
    // 上のテストの対（候補 20 件 / limit 5）。縮退分岐に入らない側では再ソートが効く。
    const getDailyDigest = makeGetDailyDigest({ port: fakePort(candidates) })

    const result = await getDailyDigest({ seed: '20260820' as DateSeed, limit: 5 })

    expect(candidates.length).toBeGreaterThan(5)
    const values = result.items.map((x) => gemIndexValue(x.gemIndex))
    expect(values).toEqual([...values].sort((a, b) => a - b))
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

  describe('Gem Index shortlist（案 A・Issue #331）', () => {
    // 200 件・gemIndex は昇順に厳密単調（i が小さいほど過小評価度が高い）。
    // shortlist（上位 GEM_INDEX_SHORTLIST_SIZE 件）は必ず pkg-000..pkg-059 に一致する。
    const largePool: Gem[] = Array.from({ length: 200 }, (_, i) =>
      gem(`pkg-${String(i).padStart(3, '0')}`, i),
    )
    const shortlistNames = new Set(largePool.slice(0, GEM_INDEX_SHORTLIST_SIZE).map((g) => g.packageName))

    it('候補プールが shortlist サイズを大きく超えるとき、選ばれる items は必ず Gem Index 上位帯（shortlist）に含まれる', async () => {
      const getDailyDigest = makeGetDailyDigest({ port: fakePort(largePool) })
      const seeds = ['20260820', '20260821', '20260822', '20260901', '20261231'] as const

      for (const seed of seeds) {
        const result = await getDailyDigest({ seed: seed as DateSeed, limit: 5 })
        for (const item of result.items) {
          expect(shortlistNames.has(item.packageName)).toBe(true)
        }
      }
    })

    it('shortlist の境界（同値タイブレーク）は packageName 昇順で決定論的に決まる（入力順に依存しない）', async () => {
      // 55 件は distinct な gemIndex（境界より確実に上位）。残り 15 件は境界をまたぐ同値グループで、
      // shortlist に入れるかどうかは packageName 昇順タイブレークで決まる（60 - 55 = 5 件のみ採用）。
      const distinctPart: Gem[] = Array.from({ length: 55 }, (_, i) =>
        gem(`distinct-${String(i).padStart(3, '0')}`, -1000 + i),
      )
      const tiedNames = ['zeta', 'yankee', 'xray', 'whiskey', 'victor', 'uniform', 'tango', 'sierra', 'romeo', 'quebec', 'papa', 'oscar', 'november', 'mike', 'lima']
      const tiedPart: Gem[] = tiedNames.map((name) => gem(`tied-${name}`, 0))
      const expectedShortlistTiedNames = [...tiedNames]
        .sort((a, b) => a.localeCompare(b))
        .slice(0, GEM_INDEX_SHORTLIST_SIZE - distinctPart.length)
        .map((name) => `tied-${name}`)

      const poolOrderA = [...distinctPart, ...tiedPart]
      const poolOrderB = [...distinctPart, ...[...tiedPart].reverse()]

      // limit === GEM_INDEX_SHORTLIST_SIZE なので shuffle は shortlist 全件を選ぶ（縮退分岐ではない
      // ことは candidates.length(70) > limit(60) で保証される）。
      const digestA = makeGetDailyDigest({ port: fakePort(poolOrderA) })
      const digestB = makeGetDailyDigest({ port: fakePort(poolOrderB) })
      const seed = '20260820' as DateSeed

      const resultA = await digestA({ seed, limit: GEM_INDEX_SHORTLIST_SIZE })
      const resultB = await digestB({ seed, limit: GEM_INDEX_SHORTLIST_SIZE })

      const namesA = resultA.items.map((x) => x.packageName)
      const namesB = resultB.items.map((x) => x.packageName)

      // 入力順を変えても結果は完全に同一（順序含む・タイブレークが入力順非依存の証拠）。
      expect(namesA).toEqual(namesB)

      const tiedNamesInResult = namesA.filter((n) => n.startsWith('tied-'))
      expect(tiedNamesInResult.sort()).toEqual([...expectedShortlistTiedNames].sort())
    })
  })
})
