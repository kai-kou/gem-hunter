import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { DateSeed } from '../domain/model/date-seed'
import type { DailyDigest, DigestMeta, Gem } from '../domain/model/gem'
import { gemIndex, gemIndexValue } from '../domain/model/gem-index'
import { GEM_INDEX_SHORTLIST_SIZE } from '../domain/model/gem-shortlist'
import type { GemDigestPort } from '../domain/ports/gem-digest-port'
import {
  makeGetDailyDigest,
  type GetDailyDigest,
  type GetDailyDigestInput,
} from './get-daily-digest'

/**
 * `GetDailyDigest` は取得失敗時に `null` を返す契約（Issue #392）。以下の既存テストは
 * 「取得できたとき」の振る舞いを検証するものなので、null でないことを確かめてから中身を見る
 * （null を握り潰して緑にしないため、ここで明示的に失敗させる）。
 */
async function runDigest(run: GetDailyDigest, input: GetDailyDigestInput): Promise<DailyDigest> {
  const result = await run(input)
  if (result === null) {
    throw new Error('ダイジェストが null（取得失敗の契約に落ちた）: ' + JSON.stringify(input))
  }
  return result
}

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
  sourceUrl: 'https://ecosyste.ms/',
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

    const a = await runDigest(getDailyDigest, { seed, limit: 5 })
    const b = await runDigest(getDailyDigest, { seed, limit: 5 })

    expect(a.items.map((x) => x.packageName)).toEqual(b.items.map((x) => x.packageName))
  })

  it('連続する 2 日（20260820 → 20260821）で顔ぶれが必ず変わる（US-31 の本質）', async () => {
    const getDailyDigest = makeGetDailyDigest({ port: fakePort(candidates) })

    const a = await runDigest(getDailyDigest, { seed: '20260820' as DateSeed, limit: 5 })
    const b = await runDigest(getDailyDigest, { seed: '20260821' as DateSeed, limit: 5 })

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
        const r = await runDigest(getDailyDigest, { seed: seed as DateSeed, limit: 5 })
        return r.items.map((x) => x.packageName).join(',')
      }),
    )

    // 決定論的なので「たまたま通る」ことはない（毎回同じ入力・同じ出力）。
    expect(new Set(names).size).toBe(seeds.length)
  })

  it('limit で先頭 N 件に切り詰める', async () => {
    const getDailyDigest = makeGetDailyDigest({ port: fakePort(candidates) })

    const result = await runDigest(getDailyDigest, { seed: '20260820' as DateSeed, limit: 3 })

    expect(result.items).toHaveLength(3)
  })

  it('候補プールが空でも例外を投げず items:[] を返す（D-28 SPOF 方針）', async () => {
    const getDailyDigest = makeGetDailyDigest({ port: fakePort([]) })

    const result = await runDigest(getDailyDigest, { seed: '20260820' as DateSeed, limit: 5 })

    expect(result.items).toEqual([])
    expect(result.date).toBe('20260820')
    expect(result.meta).toEqual(meta)
  })

  it('候補数 <= limit のときは全件返す', async () => {
    const small = candidates.slice(0, 3)
    const getDailyDigest = makeGetDailyDigest({ port: fakePort(small) })

    const result = await runDigest(getDailyDigest, { seed: '20260820' as DateSeed, limit: 5 })

    expect(result.items).toHaveLength(3)
  })

  it('候補プールが limit 以下のときは Gem Index で再ソートせず、日付ごとに並びが変わる', async () => {
    // 🔴 縮退分岐（`get-daily-digest.ts` の `candidates.length <= limit`）の回帰テスト。
    //    全件が必ず選ばれるため、ここで Gem Index asc に上書きすると並びが日付に依存しなくなり
    //    US-31（毎日顔ぶれが変わる）が静かに壊れる。候補 5 件 / limit 5 で検証する。
    const small = candidates.slice(0, 5)
    const getDailyDigest = makeGetDailyDigest({ port: fakePort(small) })

    const day1 = await runDigest(getDailyDigest, { seed: '20260820' as DateSeed, limit: 5 })
    const day2 = await runDigest(getDailyDigest, { seed: '20260821' as DateSeed, limit: 5 })

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

    const result = await runDigest(getDailyDigest, { seed: '20260820' as DateSeed, limit: 5 })

    expect(candidates.length).toBeGreaterThan(5)
    const values = result.items.map((x) => gemIndexValue(x.gemIndex))
    expect(values).toEqual([...values].sort((a, b) => a - b))
  })

  it('選ばれたサブセット内は Gem Index asc（過小評価度が高い順）で並ぶ', async () => {
    const getDailyDigest = makeGetDailyDigest({ port: fakePort(candidates) })

    const result = await runDigest(getDailyDigest, { seed: '20260820' as DateSeed, limit: 5 })

    const values = result.items.map((x) => gemIndexValue(x.gemIndex))
    const sorted = [...values].sort((a, b) => a - b)
    expect(values).toEqual(sorted)
  })

  it('meta と date を素通しする', async () => {
    const getDailyDigest = makeGetDailyDigest({ port: fakePort(candidates) })

    const result = await runDigest(getDailyDigest, { seed: '20260820' as DateSeed, limit: 5 })

    expect(result.meta).toEqual(meta)
    expect(result.date).toBe('20260820')
  })

  it('limit <= 0 なら items:[]（Math.random 非依存の防御）', async () => {
    const getDailyDigest = makeGetDailyDigest({ port: fakePort(candidates) })

    const result = await runDigest(getDailyDigest, { seed: '20260820' as DateSeed, limit: 0 })

    expect(result.items).toEqual([])
  })

  describe('Gem Index shortlist（案 A・Issue #331）', () => {
    // 200 件・gemIndex は昇順に厳密単調（i が小さいほど過小評価度が高い）。
    // shortlist（上位 GEM_INDEX_SHORTLIST_SIZE 件）は必ず pkg-000..pkg-059 に一致する。
    const largePool: Gem[] = Array.from({ length: 200 }, (_, i) =>
      gem(`pkg-${String(i).padStart(3, '0')}`, i),
    )
    const shortlistNames = new Set(
      largePool.slice(0, GEM_INDEX_SHORTLIST_SIZE).map((g) => g.packageName),
    )

    it('候補プールが shortlist サイズを大きく超えるとき、選ばれる items は必ず Gem Index 上位帯（shortlist）に含まれる', async () => {
      const getDailyDigest = makeGetDailyDigest({ port: fakePort(largePool) })
      const seeds = ['20260820', '20260821', '20260822', '20260901', '20261231'] as const

      for (const seed of seeds) {
        const result = await runDigest(getDailyDigest, { seed: seed as DateSeed, limit: 5 })
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
      const tiedNames = [
        'zeta',
        'yankee',
        'xray',
        'whiskey',
        'victor',
        'uniform',
        'tango',
        'sierra',
        'romeo',
        'quebec',
        'papa',
        'oscar',
        'november',
        'mike',
        'lima',
      ]
      const tiedPart: Gem[] = tiedNames.map((name) => gem(`tied-${name}`, 0))
      const expectedShortlistTiedNames = [...tiedNames]
        .sort((a, b) => a.localeCompare(b))
        .slice(0, GEM_INDEX_SHORTLIST_SIZE - distinctPart.length)
        .map((name) => `tied-${name}`)

      const poolOrderA = [...distinctPart, ...tiedPart]
      const poolOrderB = [...distinctPart, ...[...tiedPart].reverse()]

      // shortlist.length(60) <= limit(60) なので母集団基準では縮退ケースだが、本テストは同一 seed
      // 内の入力順非依存性のみを検証しており分岐の選択には依存しない。
      const digestA = makeGetDailyDigest({ port: fakePort(poolOrderA) })
      const digestB = makeGetDailyDigest({ port: fakePort(poolOrderB) })
      const seed = '20260820' as DateSeed

      const resultA = await runDigest(digestA, { seed, limit: GEM_INDEX_SHORTLIST_SIZE })
      const resultB = await runDigest(digestB, { seed, limit: GEM_INDEX_SHORTLIST_SIZE })

      const namesA = resultA.items.map((x) => x.packageName)
      const namesB = resultB.items.map((x) => x.packageName)

      // 入力順を変えても結果は完全に同一（順序含む・タイブレークが入力順非依存の証拠）。
      expect(namesA).toEqual(namesB)

      const tiedNamesInResult = namesA.filter((n) => n.startsWith('tied-'))
      expect(tiedNamesInResult.sort()).toEqual([...expectedShortlistTiedNames].sort())
    })
  })

  describe('shortlist サイズと limit の相互作用（PR #333 Layer 1 指摘・回帰）', () => {
    it('limit が GEM_INDEX_SHORTLIST_SIZE を超え、候補プールが limit 以下のとき全件返す（件数欠落の回帰）', async () => {
      // 候補 80 件・limit 100。shortlist を固定 60 で切ると 20 件が無警告で欠落する
      // （「プールが limit 以下なら全件返す」契約違反）。
      const pool: Gem[] = Array.from({ length: 80 }, (_, i) =>
        gem(`pkg-${String(i).padStart(3, '0')}`, i),
      )
      const getDailyDigest = makeGetDailyDigest({ port: fakePort(pool) })

      const result = await runDigest(getDailyDigest, { seed: '20260820' as DateSeed, limit: 100 })

      expect(result.items).toHaveLength(80)
    })

    it('limit === GEM_INDEX_SHORTLIST_SIZE で候補プールがそれを超えるとき、異なる seed で並びが変わる（並び固定化の回帰）', async () => {
      // 候補 70 件・limit 60。shortlist が固定 60 だと全件が必ず選ばれる縮退ケースなのに
      // candidates.length(70) > limit(60) で誤って Gem Index asc 再ソートされ、日替わりの並びが
      // 凍結する。母集団（shortlist）基準で判定すれば shortlist.length(60) <= limit(60) となり
      // 縮退ケースとして扱われ、シャッフル順（日替わり）が保たれる。
      const pool: Gem[] = Array.from({ length: 70 }, (_, i) =>
        gem(`pkg-${String(i).padStart(3, '0')}`, i),
      )
      const getDailyDigest = makeGetDailyDigest({ port: fakePort(pool) })

      const seeds = ['20260820', '20260821', '20260822'] as const
      const orderings = await Promise.all(
        seeds.map(async (seed) => {
          const result = await runDigest(getDailyDigest, {
            seed: seed as DateSeed,
            limit: GEM_INDEX_SHORTLIST_SIZE,
          })
          return result.items.map((x) => x.packageName).join(',')
        }),
      )

      // 全件（70 件 pool のうち Gem Index 上位 60 件）が毎回選ばれるので顔ぶれは同じだが、
      // 並び順（シャッフル順）は seed ごとに異なるはず。2 つ以上の seed が一致したら縮退分岐が
      // 誤判定され、Gem Index asc に固定化されている。
      expect(new Set(orderings).size).toBeGreaterThan(1)
    })
  })
})

describe('GemDigestPort が例外を投げたとき（Issue #392）', () => {
  // 失敗時は `console.warn` でログを残す設計なので、テスト出力を汚さないよう黙らせる
  // （`static-gem-digest.test.ts` と同じ方針）。
  beforeEach(() => {
    vi.spyOn(console, 'warn').mockImplementation(() => undefined)
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  function throwingPort(error: unknown): GemDigestPort {
    return {
      async listCandidates() {
        throw error
      },
    }
  }

  it('例外を投げても reject せず null を返す（ダイジェスト部分だけを欠落させる・多層防御の 2 層目）', async () => {
    const getDailyDigest = makeGetDailyDigest({ port: throwingPort(new Error('boom')) })

    const result = await getDailyDigest({ seed: '20260820' as DateSeed, limit: 5 })

    // 🔴 items:[] ではなく null。出典メタデータ（`DigestMeta`）はポートからしか得られず、
    //    捏造すると帰属表示（`D-29`）が虚偽になるため「セクションごと出さない」に倒す。
    expect(result).toBeNull()
  })

  it('Promise が reject したときも null を返す（throw 以外の失敗形）', async () => {
    const port: GemDigestPort = {
      listCandidates: () => Promise.reject(new Error('rejected')),
    }
    const getDailyDigest = makeGetDailyDigest({ port })

    await expect(getDailyDigest({ seed: '20260820' as DateSeed, limit: 5 })).resolves.toBeNull()
  })

  it('Error 以外（文字列 throw）でも null を返す', async () => {
    const getDailyDigest = makeGetDailyDigest({ port: throwingPort('not an error') })

    await expect(getDailyDigest({ seed: '20260820' as DateSeed, limit: 0 })).resolves.toBeNull()
  })

  it('null に畳んだことを console.warn で残す（無音で握り潰さない）', async () => {
    const getDailyDigest = makeGetDailyDigest({ port: throwingPort(new Error('boom')) })

    await expect(getDailyDigest({ seed: '20260820' as DateSeed, limit: 5 })).resolves.toBeNull()

    // 🔴 「null を返す」だけを検証すると、ログを消す変更が無警告で通る（ダイジェストが恒久的に
    //    欠落しても観測できなくなる）。プレフィックスと例外オブジェクトの両方を固定する。
    expect(console.warn).toHaveBeenCalledWith(
      expect.stringContaining('[getDailyDigest]'),
      expect.any(Error),
    )
  })

  it('候補取得後（ハッシュ計算段）で失敗しても null を返す + 警告を残す', async () => {
    // 🔴 `try` の範囲が `port.listCandidates()` だけに狭まる退行の回帰テスト。
    //    ポートは正常に返り、後段の `deterministicKey`（`crypto.subtle.digest`）だけが落ちる。
    vi.spyOn(crypto.subtle, 'digest').mockRejectedValue(new Error('subtle unavailable'))
    const getDailyDigest = makeGetDailyDigest({ port: fakePort(candidates) })

    await expect(getDailyDigest({ seed: '20260820' as DateSeed, limit: 5 })).resolves.toBeNull()
    expect(console.warn).toHaveBeenCalledWith(
      expect.stringContaining('[getDailyDigest]'),
      expect.any(Error),
    )
  })
})
