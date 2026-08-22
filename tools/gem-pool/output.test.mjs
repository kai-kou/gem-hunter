/**
 * output.mjs のユニットテスト（`SP-17` / Issue #387）。
 *
 * ここで検証するのは **fs を叩かない純粋関数だけ**（`writeJsonFile` は薄い fs ラッパーなので対象外）。
 * `registries.mjs` / `collect.mjs` / `pipeline.mjs` は直接 import しない（他の役が並行実装中のため）。
 * `output.mjs` が内部で `registries.mjs` を使う分だけは間接的に依存する。
 */
import { describe, expect, it } from 'vitest'

import {
  SHARD_COLUMNS,
  buildDailyDigestDoc,
  buildMeta,
  buildRegistryShards,
  buildShardIndex,
  serializeJson,
} from './output.mjs'

/** テスト用の RankedRecord を 1 件作る（`pipeline.buildPool` の出力と同じ形）。 */
function rec(registry, packageName, repositoryFullName, dependentCount, stars, gemIndex) {
  return {
    registry,
    packageName,
    repositoryFullName,
    dependentCount,
    stars,
    dependentRank: 0.1,
    starRank: 0.2,
    gemIndex,
  }
}

const META = Object.freeze({
  source: 'Ecosyste.ms',
  sourceUrl: 'https://ecosyste.ms/',
  license: 'CC BY-SA 4.0',
  sourceLicenseUrl: 'https://creativecommons.org/licenses/by-sa/4.0/',
  generatedAt: '2026-08-22T00:00:00.000Z',
})

/** gemIndex 昇順で並んだ 3 件（2 レジストリ）。 */
const RECORDS = Object.freeze([
  rec('npmjs.org', 'typescript', 'microsoft/TypeScript', 488056, 110165, -0.05),
  rec('rubygems.org', 'rake', 'ruby/rake', 12000, 2000, -0.02),
  rec('npmjs.org', 'left-pad', 'stevemao/left-pad', 900, 1000, 0.1),
])

describe('buildMeta', () => {
  it('`D-29` の出典メタデータ 5 フィールドを返す', () => {
    const meta = buildMeta('2026-08-22T00:00:00.000Z')
    expect(meta).toEqual({
      source: 'Ecosyste.ms',
      sourceUrl: 'https://ecosyste.ms/',
      license: 'CC BY-SA 4.0',
      sourceLicenseUrl: 'https://creativecommons.org/licenses/by-sa/4.0/',
      generatedAt: '2026-08-22T00:00:00.000Z',
    })
  })

  it('Date を渡すと ISO 8601 文字列へ正規化する', () => {
    const meta = buildMeta(new Date(Date.UTC(2026, 7, 22, 1, 2, 3)))
    expect(meta.generatedAt).toBe('2026-08-22T01:02:03.000Z')
  })

  it('生成時刻を省略・不正値のときも帰属表示は落とさない（generatedAt だけ空にする）', () => {
    expect(buildMeta(undefined).generatedAt).toBe('')
    expect(buildMeta(new Date('nope')).generatedAt).toBe('')
    expect(buildMeta(undefined).source).toBe('Ecosyste.ms')
  })
})

describe('buildRegistryShards', () => {
  it('レジストリごとに 1 ファイルへ分け、ファイル名はスラッグ + .json になる', () => {
    const shards = buildRegistryShards(RECORDS, META)
    expect(shards.map((s) => s.fileName)).toEqual(['npmjs-org.json', 'rubygems-org.json'])
  })

  it('シャードの順序はレジストリ名の昇順で決定論になる（入力順に依存しない）', () => {
    const reversed = [...RECORDS].reverse()
    expect(buildRegistryShards(reversed, META).map((s) => s.doc.registry)).toEqual([
      'npmjs.org',
      'rubygems.org',
    ])
  })

  it('#388 との契約どおり registry / ecosystem / meta / columns / entries を持つ', () => {
    const [npm] = buildRegistryShards(RECORDS, META)
    expect(npm.doc.registry).toBe('npmjs.org')
    expect(npm.doc.ecosystem).toBe('npm')
    expect(npm.doc.meta).toEqual(META)
    expect(npm.doc.columns).toEqual(SHARD_COLUMNS)
    expect(SHARD_COLUMNS).toEqual([
      'repositoryFullName',
      'packageName',
      'dependentCount',
      'stars',
      'gemIndex',
    ])
  })

  it('entries は columns の順に並んだタプルで、gemIndex 昇順になる', () => {
    const [npm] = buildRegistryShards(RECORDS, META)
    expect(npm.doc.entries).toEqual([
      ['microsoft/TypeScript', 'typescript', 488056, 110165, -0.05],
      ['stevemao/left-pad', 'left-pad', 900, 1000, 0.1],
    ])
  })

  it('入力が gemIndex 昇順でなくてもシャード内で昇順へ整える', () => {
    const shuffled = [RECORDS[2], RECORDS[0]]
    const [npm] = buildRegistryShards(shuffled, META)
    expect(npm.doc.entries.map((e) => e[4])).toEqual([-0.05, 0.1])
  })

  it('gemIndex が同値のときは repositoryFullName → packageName で決定論に並べる', () => {
    const ties = [
      rec('npmjs.org', 'b-pkg', 'zzz/repo', 1, 1, 0),
      rec('npmjs.org', 'a-pkg', 'aaa/repo', 1, 1, 0),
    ]
    const [npm] = buildRegistryShards(ties, META)
    expect(npm.doc.entries.map((e) => e[0])).toEqual(['aaa/repo', 'zzz/repo'])
  })

  it('未知のレジストリでも落とさず ecosystem を null にする', () => {
    const shards = buildRegistryShards([rec('example.test', 'p', 'o/r', 1, 1, 0)], META)
    expect(shards).toHaveLength(1)
    expect(shards[0].doc.ecosystem).toBeNull()
    expect(shards[0].fileName.endsWith('.json')).toBe(true)
  })

  it('レコードが空なら空配列を返す', () => {
    expect(buildRegistryShards([], META)).toEqual([])
  })
})

describe('buildDailyDigestDoc', () => {
  it('既存の daily-digest.json の shape（date / meta / candidates）を保つ', () => {
    const doc = buildDailyDigestDoc(RECORDS, META, { date: '20260822', limit: 10 })
    expect(Object.keys(doc)).toEqual(['date', 'meta', 'candidates'])
    expect(doc.date).toBe('20260822')
    expect(doc.meta).toEqual(META)
  })

  it('候補は Gem Index 上位から limit 件で、registry を追加した既存フィールドを持つ', () => {
    const doc = buildDailyDigestDoc(RECORDS, META, { date: '20260822', limit: 2 })
    expect(doc.candidates).toEqual([
      {
        packageName: 'typescript',
        repositoryFullName: 'microsoft/TypeScript',
        dependentCount: 488056,
        stars: 110165,
        gemIndex: -0.05,
        registry: 'npmjs.org',
      },
      {
        packageName: 'rake',
        repositoryFullName: 'ruby/rake',
        dependentCount: 12000,
        stars: 2000,
        gemIndex: -0.02,
        registry: 'rubygems.org',
      },
    ])
  })

  it('入力順が崩れていても gemIndex 昇順で切り出す', () => {
    const doc = buildDailyDigestDoc([...RECORDS].reverse(), META, { date: '20260822', limit: 1 })
    expect(doc.candidates.map((c) => c.packageName)).toEqual(['typescript'])
  })

  it('Date を渡すと UTC の YYYYMMDD へ正規化する', () => {
    const doc = buildDailyDigestDoc(RECORDS, META, {
      date: new Date(Date.UTC(2026, 7, 22, 23, 59)),
      limit: 1,
    })
    expect(doc.date).toBe('20260822')
  })

  it('limit がレコード数を超えても全件で止まる', () => {
    expect(
      buildDailyDigestDoc(RECORDS, META, { date: '20260822', limit: 99 }).candidates,
    ).toHaveLength(3)
  })
})

describe('buildShardIndex', () => {
  it('シャード一覧・総件数・meta・stats を載せる', () => {
    const shards = buildRegistryShards(RECORDS, META)
    const index = buildShardIndex(shards, META, { total: 3, excluded: { missingStars: 7 } })

    expect(index.meta).toEqual(META)
    expect(index.totalCount).toBe(3)
    // ecosystem の値は `registries.mjs` が正本なので、ここでは契約に明記された npm だけを固定検証する。
    expect(
      index.shards.map(({ registry, fileName, count }) => ({ registry, fileName, count })),
    ).toEqual([
      { registry: 'npmjs.org', fileName: 'npmjs-org.json', count: 2 },
      { registry: 'rubygems.org', fileName: 'rubygems-org.json', count: 1 },
    ])
    expect(index.shards[0].ecosystem).toBe('npm')
    expect(index.shards.every((s) => Object.hasOwn(s, 'ecosystem'))).toBe(true)
    expect(index.stats).toEqual({ total: 3, excluded: { missingStars: 7 } })
  })

  it('stats は JSON 往復で情報が落ちない（`buildPool()` はプレーンな値だけを返す）', () => {
    // buildPool() の stats は「プレーンオブジェクト + 数値」だけなので、そのまま載せて往復できる
    const stats = { total: 3, byRegistry: { 'npmjs.org': { collected: 10, kept: 2 } } }
    const index = buildShardIndex([], META, stats)
    expect(JSON.parse(JSON.stringify(index.stats))).toEqual(stats)
  })

  it('stats 未指定でも空オブジェクトで通す', () => {
    expect(buildShardIndex([], META).stats).toEqual({})
    expect(buildShardIndex([], META).totalCount).toBe(0)
  })
})

describe('serializeJson', () => {
  it('末尾に改行を 1 つ付けた JSON 文字列を返す', () => {
    const text = serializeJson({ a: 1 })
    expect(text).toBe('{"a":1}\n')
    expect(JSON.parse(text)).toEqual({ a: 1 })
  })

  it('pretty: true のときだけ 2 スペースで整形する（既定は非整形）', () => {
    const doc = { a: 1, b: { c: 2 } }
    expect(serializeJson(doc, { pretty: true })).toBe(
      '{\n  "a": 1,\n  "b": {\n    "c": 2\n  }\n}\n',
    )
    expect(serializeJson(doc, { pretty: false })).toBe(serializeJson(doc))
    expect(serializeJson(doc, { pretty: true }).length).toBeGreaterThan(serializeJson(doc).length)
  })
})
