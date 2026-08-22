/**
 * output.test.mjs — output.mjs（純関数 + 書き出し）のテスト。
 *
 * 🔴 他役（registries.mjs / collect.mjs / pipeline.mjs）には依存しない。
 * SP-17 契約 §5 の GemCandidate 形（{ registry, packageName, repositoryFullName,
 * dependentCount, stars, gemIndex }）をこのファイルの中でリテラルに組み立てて使う。
 */
import { mkdtemp, readFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { SHARD_COLUMNS, buildDailyDigest, buildMeta, buildShards, writeOutputs } from './output.mjs'

/** テスト用 GemCandidate を最小差分で作るヘルパー。 */
function candidate(overrides) {
  return {
    registry: 'npm',
    packageName: 'pkg',
    repositoryFullName: 'owner/pkg',
    dependentCount: 100,
    stars: 10,
    gemIndex: 0,
    ...overrides,
  }
}

describe('buildMeta', () => {
  it('D-29 の帰属メタデータを固定形で返す', () => {
    const meta = buildMeta('2026-08-22T00:00:00.000Z')
    expect(meta).toEqual({
      source: 'Ecosyste.ms',
      sourceUrl: 'https://ecosyste.ms/',
      license: 'CC BY-SA 4.0',
      sourceLicenseUrl: 'https://creativecommons.org/licenses/by-sa/4.0/',
      generatedAt: '2026-08-22T00:00:00.000Z',
    })
  })
})

describe('SHARD_COLUMNS', () => {
  it('契約 §5 の列順を固定する（#388 の配信契約）', () => {
    expect(SHARD_COLUMNS).toEqual([
      'repositoryFullName',
      'packageName',
      'dependentCount',
      'stars',
      'gemIndex',
    ])
  })
})

describe('buildShards', () => {
  it('registry ごとに分割し、rows は gemIndex 昇順・列は SHARD_COLUMNS の並びにする', () => {
    const candidates = [
      candidate({ registry: 'npm', packageName: 'b', repositoryFullName: 'o/b', gemIndex: 5 }),
      candidate({ registry: 'pypi', packageName: 'x', repositoryFullName: 'o/x', gemIndex: 1 }),
      candidate({ registry: 'npm', packageName: 'a', repositoryFullName: 'o/a', gemIndex: -3 }),
    ]

    const shards = buildShards(candidates, { generatedAt: '2026-08-22T00:00:00.000Z' })

    // レジストリ id 昇順で決定論的に並べる（入力順に依存させない・実装判断）。
    expect(shards.map((s) => s.registry)).toEqual(['npm', 'pypi'])

    const npmShard = shards.find((s) => s.registry === 'npm')
    expect(npmShard.doc.columns).toEqual(SHARD_COLUMNS)
    expect(npmShard.doc.meta).toEqual(buildMeta('2026-08-22T00:00:00.000Z'))
    // gemIndex 昇順: a(-3) → b(5)
    expect(npmShard.doc.rows).toEqual([
      ['o/a', 'a', 100, 10, -3],
      ['o/b', 'b', 100, 10, 5],
    ])

    const pypiShard = shards.find((s) => s.registry === 'pypi')
    expect(pypiShard.doc.rows).toEqual([['o/x', 'x', 100, 10, 1]])
  })

  it('候補が空でも空配列を返す（例外にしない）', () => {
    expect(buildShards([], { generatedAt: '2026-08-22T00:00:00.000Z' })).toEqual([])
  })
})

describe('buildDailyDigest', () => {
  it('gemIndex 昇順の上位 limit 件を返し、date は UTC の YYYYMMDD にする', () => {
    const candidates = [
      candidate({ packageName: 'high', repositoryFullName: 'o/high', gemIndex: 10 }),
      candidate({ packageName: 'low', repositoryFullName: 'o/low', gemIndex: -10 }),
      candidate({ packageName: 'mid', repositoryFullName: 'o/mid', gemIndex: 0 }),
    ]
    const now = new Date('2026-08-22T23:59:59.999Z')

    const digest = buildDailyDigest(candidates, { limit: 2, now })

    expect(digest.date).toBe('20260822')
    expect(digest.meta).toEqual(buildMeta(now.toISOString()))
    expect(digest.candidates).toEqual([
      {
        registry: 'npm',
        packageName: 'low',
        repositoryFullName: 'o/low',
        dependentCount: 100,
        stars: 10,
        gemIndex: -10,
      },
      {
        registry: 'npm',
        packageName: 'mid',
        repositoryFullName: 'o/mid',
        dependentCount: 100,
        stars: 10,
        gemIndex: 0,
      },
    ])
  })

  it('limit を既定値 300 として扱う', () => {
    const candidates = Array.from({ length: 5 }, (_, i) =>
      candidate({ packageName: `p${i}`, repositoryFullName: `o/p${i}`, gemIndex: i }),
    )
    const digest = buildDailyDigest(candidates, { now: new Date('2026-08-22T00:00:00.000Z') })
    expect(digest.candidates).toHaveLength(5)
  })

  it('date 境界: UTC 日跨ぎのタイムゾーンでも UTC 日付になる', () => {
    // JST 2026-08-23 08:59 = UTC 2026-08-22 23:59（datetime-rules: 機械処理用は UTC 維持）
    const now = new Date('2026-08-22T23:59:00.000Z')
    const digest = buildDailyDigest([], { now })
    expect(digest.date).toBe('20260822')
  })
})

describe('writeOutputs', () => {
  let dir

  beforeEach(async () => {
    dir = await mkdtemp(join(tmpdir(), 'gem-pool-output-'))
  })

  afterEach(async () => {
    await rm(dir, { recursive: true, force: true })
  })

  it('digest と shard を outDir 配下へ書き出し、written に書き込んだパスを返す', async () => {
    const shards = [
      {
        registry: 'npm',
        doc: { meta: buildMeta('2026-08-22T00:00:00.000Z'), columns: SHARD_COLUMNS, rows: [] },
      },
      {
        registry: 'pypi',
        doc: { meta: buildMeta('2026-08-22T00:00:00.000Z'), columns: SHARD_COLUMNS, rows: [] },
      },
    ]
    const digest = {
      date: '20260822',
      meta: buildMeta('2026-08-22T00:00:00.000Z'),
      candidates: [],
    }

    const { written } = await writeOutputs({ shards, digest, outDir: dir })

    expect(written).toHaveLength(3)

    const digestOnDisk = JSON.parse(await readFile(join(dir, 'daily-digest.json'), 'utf8'))
    expect(digestOnDisk).toEqual(digest)

    const npmOnDisk = JSON.parse(await readFile(join(dir, 'gem-index', 'npm.json'), 'utf8'))
    expect(npmOnDisk).toEqual(shards[0].doc)

    const pypiOnDisk = JSON.parse(await readFile(join(dir, 'gem-index', 'pypi.json'), 'utf8'))
    expect(pypiOnDisk).toEqual(shards[1].doc)
  })

  it('writeShards: false のとき shard を書かず digest のみ書く', async () => {
    const shards = [
      { registry: 'npm', doc: { meta: buildMeta('x'), columns: SHARD_COLUMNS, rows: [] } },
    ]
    const digest = { date: '20260822', meta: buildMeta('x'), candidates: [] }

    const { written } = await writeOutputs({ shards, digest, outDir: dir, writeShards: false })

    expect(written).toHaveLength(1)
    expect(written[0]).toContain('daily-digest.json')
    await expect(readFile(join(dir, 'gem-index', 'npm.json'), 'utf8')).rejects.toThrow()
  })

  it('末尾に改行付きの整形 JSON を書く（既存 generate_gem_digest.mjs の慣習と合わせる）', async () => {
    const digest = { date: '20260822', meta: buildMeta('x'), candidates: [] }
    await writeOutputs({ shards: [], digest, outDir: dir })

    const raw = await readFile(join(dir, 'daily-digest.json'), 'utf8')
    expect(raw.endsWith('\n')).toBe(true)
    expect(raw).toContain('\n  ')
  })
})
