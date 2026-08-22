import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { gemIndexValue } from '../../domain/model/gem-index'

import type { AssetReader } from './asset-reader'
import { FALLBACK_META } from './static-gem-digest'
import { StaticGemIndex, resetGemIndexCacheForTest } from './static-gem-index'

/**
 * `tokenizeIdentifier` の呼び出し回数を数えるためのカウンタ（`vi.hoisted` で `vi.mock` の
 * ファクトリより先に初期化する）。
 *
 * 🔴 これは「照合用トークンを **cold start で 1 回だけ** 計算しているか」を担保するための計測。
 * warm のリクエストで再 tokenize していると、62,483 件 × リクエスト数だけ CPU を食う。
 * ⚠️ `vi.fn` ではなく素の関数でラップする（`vi.restoreAllMocks()` に実装を消されないため）。
 */
const tokenize = vi.hoisted(() => ({ calls: 0 }))

vi.mock('../../domain/model/gem-keyword', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../domain/model/gem-keyword')>()
  return {
    ...actual,
    tokenizeIdentifier: (value: string) => {
      tokenize.calls += 1
      return actual.tokenizeIdentifier(value)
    },
  }
})

const INDEX_PATH = '/data/gem-index/index.json'

/** `index.json` の最小形（`shards[].fileName` だけを本実装は見る）。 */
function indexJson(fileNames: readonly string[]): string {
  return JSON.stringify({
    totalCount: 0,
    shards: fileNames.map((fileName) => ({
      registry: fileName.replace(/\.json$/, ''),
      ecosystem: 'test',
      fileName,
      count: 0,
    })),
  })
}

/** シャードの最小形（`columns` の並びは呼び出し側が指定できる）。 */
function shardJson(
  entries: readonly (readonly unknown[])[],
  columns: readonly string[] = [
    'repositoryFullName',
    'packageName',
    'dependentCount',
    'stars',
    'gemIndex',
  ],
): string {
  return JSON.stringify({ registry: 'test', ecosystem: 'test', columns, entries })
}

/** ファイル名 → 本文のマップから `AssetReader` スタブを作る（呼び出し回数を数えられる）。 */
function stubReader(files: Record<string, string>): AssetReader & { calls: string[] } {
  const calls: string[] = []
  const reader = (async (path: string) => {
    calls.push(path)
    return files[path] ?? null
  }) as AssetReader & { calls: string[] }
  reader.calls = calls
  return reader
}

const twoShards = {
  [INDEX_PATH]: indexJson(['a.json', 'b.json']),
  '/data/gem-index/a.json': shardJson([
    ['owner/alpha', 'alpha', 100, 5, -80.5],
    ['owner/beta', 'beta', 50, 3, -40.25],
  ]),
  '/data/gem-index/b.json': shardJson([['other/gamma', 'gamma', 20, 1, -10]]),
}

describe('StaticGemIndex', () => {
  beforeEach(() => {
    resetGemIndexCacheForTest()
    tokenize.calls = 0
    vi.spyOn(console, 'warn').mockImplementation(() => undefined)
  })

  afterEach(() => {
    resetGemIndexCacheForTest()
    vi.restoreAllMocks()
  })

  it('複数シャードをマージして lookup で引ける', async () => {
    const reader = stubReader(twoShards)
    const port = new StaticGemIndex(reader)

    const found = await port.lookup(['owner/alpha', 'other/gamma'])

    expect([...found.keys()].sort()).toEqual(['other/gamma', 'owner/alpha'])
    expect(gemIndexValue(found.get('owner/alpha')!)).toBe(-80.5)
    expect(gemIndexValue(found.get('other/gamma')!)).toBe(-10)
  })

  it('大文字小文字を無視して引け、返り値のキーは入力の綴りそのもの', async () => {
    const port = new StaticGemIndex(stubReader(twoShards))

    const found = await port.lookup(['Owner/Alpha'])

    expect([...found.keys()]).toEqual(['Owner/Alpha'])
    expect(gemIndexValue(found.get('Owner/Alpha')!)).toBe(-80.5)
    expect(found.has('owner/alpha')).toBe(false)
  })

  it('プールに載っていないものはキーごと入れない', async () => {
    const port = new StaticGemIndex(stubReader(twoShards))

    const found = await port.lookup(['owner/alpha', 'nobody/unknown'])

    expect(found.has('nobody/unknown')).toBe(false)
    expect(found.size).toBe(1)
  })

  it('singleton: 2 回続けて lookup しても AssetReader の呼び出し回数が増えない', async () => {
    const reader = stubReader(twoShards)
    const port = new StaticGemIndex(reader)

    await port.lookup(['owner/alpha'])
    const afterFirst = [...reader.calls]
    await port.lookup(['owner/beta'])

    expect(afterFirst).toHaveLength(3) // index.json + シャード 2 本
    expect(reader.calls).toEqual(afterFirst)
  })

  it('warm 時の join は Map.get() のみ（2 回目の lookup で AssetReader が一度も呼ばれない）', async () => {
    const reader = stubReader(twoShards)
    const port = new StaticGemIndex(reader)

    await port.lookup(['owner/alpha'])
    reader.calls.length = 0
    const found = await port.lookup(['owner/beta'])

    expect(reader.calls).toEqual([])
    expect(gemIndexValue(found.get('owner/beta')!)).toBe(-40.25)
  })

  it('並行到達しても取得は 1 セットだけ（singleton promise）', async () => {
    const reader = stubReader(twoShards)
    const port = new StaticGemIndex(reader)

    const [first, second] = await Promise.all([
      port.lookup(['owner/alpha']),
      port.lookup(['other/gamma']),
    ])

    expect(reader.calls).toHaveLength(3)
    expect(first.size).toBe(1)
    expect(second.size).toBe(1)
  })

  it('インスタンスが別でもモジュールスコープの singleton を共有する', async () => {
    const reader = stubReader(twoShards)

    await new StaticGemIndex(reader).lookup(['owner/alpha'])
    await new StaticGemIndex(reader).lookup(['owner/beta'])

    expect(reader.calls).toHaveLength(3)
  })

  it('columns の並びが違うシャードでも正しく読める', async () => {
    const reader = stubReader({
      [INDEX_PATH]: indexJson(['reordered.json']),
      '/data/gem-index/reordered.json': shardJson(
        [[-12.5, 'owner/reordered', 7]],
        ['gemIndex', 'repositoryFullName', 'stars'],
      ),
    })

    const found = await new StaticGemIndex(reader).lookup(['owner/reordered'])

    expect(gemIndexValue(found.get('owner/reordered')!)).toBe(-12.5)
  })

  it('index.json が読めなければ空 Map（throw しない）', async () => {
    const found = await new StaticGemIndex(stubReader({})).lookup(['owner/alpha'])

    expect(found.size).toBe(0)
  })

  it('index.json が壊れた JSON でも空 Map（throw しない）', async () => {
    const reader = stubReader({ [INDEX_PATH]: '{ broken' })

    await expect(new StaticGemIndex(reader).lookup(['owner/alpha'])).resolves.toEqual(new Map())
  })

  it('シャードが 1 つ壊れていても残りのシャードは使える', async () => {
    const reader = stubReader({
      [INDEX_PATH]: indexJson(['a.json', 'broken.json', 'missing.json']),
      '/data/gem-index/a.json': twoShards['/data/gem-index/a.json'],
      '/data/gem-index/broken.json': '{ not json',
    })

    const found = await new StaticGemIndex(reader).lookup(['owner/alpha', 'owner/beta'])

    expect(found.size).toBe(2)
  })

  it('columns に必要な列が無いシャードはスキップして警告する', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    const reader = stubReader({
      [INDEX_PATH]: indexJson(['a.json', 'noColumns.json']),
      '/data/gem-index/a.json': twoShards['/data/gem-index/a.json'],
      '/data/gem-index/noColumns.json': shardJson(
        [['owner/x', 1]],
        ['repositoryFullName', 'stars'],
      ),
    })

    const found = await new StaticGemIndex(reader).lookup(['owner/alpha', 'owner/x'])

    expect(found.has('owner/alpha')).toBe(true)
    expect(found.has('owner/x')).toBe(false)
    expect(warn).toHaveBeenCalled()
  })

  it('gemIndex が有限数でないエントリはスキップする', async () => {
    const reader = stubReader({
      [INDEX_PATH]: indexJson(['a.json']),
      '/data/gem-index/a.json': shardJson([
        ['owner/ok', 'ok', 1, 1, -1],
        ['owner/ng', 'ng', 1, 1, 'not-a-number'],
        [null, 'ng2', 1, 1, -2],
      ]),
    })

    const found = await new StaticGemIndex(reader).lookup(['owner/ok', 'owner/ng', 'owner/ng2'])

    expect([...found.keys()]).toEqual(['owner/ok'])
  })

  it('初期化に失敗した Promise はキャッシュしない（次の lookup で再試行して成功する）', async () => {
    let files: Record<string, string> = {}
    const reader: AssetReader = async (path) => files[path] ?? null
    const port = new StaticGemIndex(reader)

    expect((await port.lookup(['owner/alpha'])).size).toBe(0)

    files = twoShards
    const retried = await port.lookup(['owner/alpha'])

    expect(gemIndexValue(retried.get('owner/alpha')!)).toBe(-80.5)
  })

  it('index.json は読めても全シャードが失敗したらキャッシュせず、次の lookup で再試行して成功する', async () => {
    // 入口だけ読める状態（シャードは 1 本も無い）。ここを「成功」としてキャッシュすると
    // その isolate の生存期間ずっとバッジが出なくなる。
    let files: Record<string, string> = { [INDEX_PATH]: indexJson(['a.json', 'b.json']) }
    const calls: string[] = []
    const reader: AssetReader = async (path) => {
      calls.push(path)
      return files[path] ?? null
    }
    const port = new StaticGemIndex(reader)

    expect((await port.lookup(['owner/alpha'])).size).toBe(0)
    expect(calls).toHaveLength(3) // index.json + シャード 2 本

    files = twoShards
    const retried = await port.lookup(['owner/alpha'])

    expect(gemIndexValue(retried.get('owner/alpha')!)).toBe(-80.5)
    expect(calls).toHaveLength(6) // 再試行でもう 1 セット取得している
  })

  it('部分成功（一部シャードだけ失敗）はキャッシュして再取得しない', async () => {
    const reader = stubReader({
      [INDEX_PATH]: indexJson(['a.json', 'missing.json']),
      '/data/gem-index/a.json': twoShards['/data/gem-index/a.json'],
    })
    const port = new StaticGemIndex(reader)

    expect((await port.lookup(['owner/alpha'])).size).toBe(1)
    const afterFirst = [...reader.calls]
    await port.lookup(['owner/beta'])

    expect(reader.calls).toEqual(afterFirst)
  })

  it('同一 repo が複数シャードにあるときは Gem Index が小さい方を採る（大文字小文字も同一視）', async () => {
    const reader = stubReader({
      [INDEX_PATH]: indexJson(['first.json', 'second.json']),
      // dup は先に大きい値、dup2 は先に小さい値（読み込み順に依存しないことを両向きで固定する）。
      '/data/gem-index/first.json': shardJson([
        ['Owner/Dup', 'dup', 10, 1, -10],
        ['owner/dup2', 'dup2', 10, 1, -90],
      ]),
      '/data/gem-index/second.json': shardJson([
        ['owner/dup', 'dup', 20, 2, -90],
        ['Owner/Dup2', 'dup2', 20, 2, -10],
      ]),
    })

    const found = await new StaticGemIndex(reader).lookup(['owner/dup', 'owner/dup2'])

    expect(found.size).toBe(2)
    expect(gemIndexValue(found.get('owner/dup')!)).toBe(-90)
    expect(gemIndexValue(found.get('owner/dup2')!)).toBe(-90)
  })

  it('AssetReader が例外を投げても空 Map に倒す', async () => {
    const reader: AssetReader = async () => {
      throw new Error('boom')
    }

    await expect(new StaticGemIndex(reader).lookup(['owner/alpha'])).resolves.toEqual(new Map())
  })
})
