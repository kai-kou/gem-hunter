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
const tokenize = vi.hoisted(() => ({ calls: 0, fail: false }))

vi.mock('../../domain/model/gem-keyword', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../domain/model/gem-keyword')>()
  return {
    ...actual,
    tokenizeIdentifier: (value: string) => {
      tokenize.calls += 1
      if (tokenize.fail) {
        // 検索インデックス（第 2 段）の構築失敗を再現するための注入。
        throw new Error('tokenize boom')
      }
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
    tokenize.fail = false
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

/** 一覧（`search`）用の出典メタデータ（`index.json` の `meta`）。 */
const POOL_META = {
  source: 'Ecosyste.ms',
  sourceUrl: 'https://ecosyste.ms/',
  license: 'CC BY-SA 4.0',
  sourceLicenseUrl: 'https://creativecommons.org/licenses/by-sa/4.0/',
  generatedAt: '2026-08-22T06:04:21.791Z',
}

/** `meta` 付きの `index.json`（一覧は出典表示を返すため・`D-29` / `GR-6`）。 */
function indexJsonWithMeta(fileNames: readonly string[]): string {
  return JSON.stringify({
    meta: POOL_META,
    totalCount: 0,
    shards: fileNames.map((fileName) => ({ fileName })),
  })
}

/** レジストリ名を明示したシャード（一覧は `registry` を表示する）。 */
function registryShardJson(registry: string, entries: readonly (readonly unknown[])[]): string {
  return JSON.stringify({
    registry,
    ecosystem: registry,
    columns: ['repositoryFullName', 'packageName', 'dependentCount', 'stars', 'gemIndex'],
    entries,
  })
}

/**
 * 一覧テスト用のプール（Gem Index 昇順に並べると
 * `acme/orm-core`(-70) → `acme/http-client`(-60) → `beta/orm-client`(-60) →
 * `Gamma/Image-Tools`(-50) → `delta/solo`(-10)。-60 の 2 件は repo 名昇順のタイブレーク）。
 */
const searchFiles = {
  [INDEX_PATH]: indexJsonWithMeta(['npm.json', 'pypi.json']),
  '/data/gem-index/npm.json': registryShardJson('npmjs.org', [
    ['acme/orm-core', 'orm-core', 100, 5, -70],
    ['acme/http-client', 'http-client', 90, 4, -60],
    ['Gamma/Image-Tools', 'image-processing', 80, 3, -50],
  ]),
  '/data/gem-index/pypi.json': registryShardJson('pypi.org', [
    ['beta/orm-client', 'orm_client', 70, 2, -60],
    ['delta/solo', 'solo', 60, 1, -10],
  ]),
}

/** 並び順を確かめやすいように `repositoryFullName` だけ取り出す。 */
function names(items: readonly { readonly repositoryFullName: string }[]): readonly string[] {
  return items.map((item) => item.repositoryFullName)
}

describe('StaticGemIndex#search', () => {
  beforeEach(() => {
    resetGemIndexCacheForTest()
    tokenize.calls = 0
    tokenize.fail = false
    vi.spyOn(console, 'warn').mockImplementation(() => undefined)
  })

  afterEach(() => {
    resetGemIndexCacheForTest()
    vi.restoreAllMocks()
  })

  it('検索語なし（tokens 空）は絞り込みなしで全件を Gem Index 昇順に返す（同値は repo 名昇順）', async () => {
    const port = new StaticGemIndex(stubReader(searchFiles))

    const result = await port.search({ tokens: [], page: 1, perPage: 10 })

    expect(result.totalCount).toBe(5)
    expect(names(result.items)).toEqual([
      'acme/orm-core',
      'acme/http-client', // -60 の同値タイブレーク（acme/... < beta/...）
      'beta/orm-client',
      'Gamma/Image-Tools',
      'delta/solo',
    ])
    expect(result.relaxed).toBe(false)
    expect(result.usedTokens).toEqual([])
  })

  it('全語 AND で絞り込む（部分一致では引かない）', async () => {
    const port = new StaticGemIndex(stubReader(searchFiles))

    const result = await port.search({ tokens: ['orm', 'client'], page: 1, perPage: 10 })

    expect(names(result.items)).toEqual(['beta/orm-client'])
    expect(result.totalCount).toBe(1)
    expect(result.relaxed).toBe(false)
    expect(result.usedTokens).toEqual(['orm', 'client'])
  })

  it('大文字小文字を無視して照合する（プール側の綴りが大文字でも引ける）', async () => {
    const port = new StaticGemIndex(stubReader(searchFiles))

    const result = await port.search({ tokens: ['gamma'], page: 1, perPage: 10 })

    expect(names(result.items)).toEqual(['Gamma/Image-Tools'])
  })

  it('パッケージ名側の単語でも引ける（repo 名との和集合で照合する）', async () => {
    const port = new StaticGemIndex(stubReader(searchFiles))

    // `processing` は repo 名（Gamma/Image-Tools）には無く、パッケージ名にだけある語。
    const result = await port.search({ tokens: ['processing'], page: 1, perPage: 10 })

    expect(names(result.items)).toEqual(['Gamma/Image-Tools'])
  })

  it('全語 AND が 0 件なら「最も選択的な 1 語」へ緩める（relaxed / usedTokens で明示する）', async () => {
    const port = new StaticGemIndex(stubReader(searchFiles))

    // image=1 件 / client=2 件 → 件数の少ない image が選ばれる。
    const result = await port.search({ tokens: ['image', 'client'], page: 1, perPage: 10 })

    expect(result.relaxed).toBe(true)
    expect(result.usedTokens).toEqual(['image'])
    expect(names(result.items)).toEqual(['Gamma/Image-Tools'])
    expect(result.totalCount).toBe(1)
  })

  it('どの語も単独で 0 件なら空結果（緩和は起きていないので relaxed は false）', async () => {
    const port = new StaticGemIndex(stubReader(searchFiles))

    const result = await port.search({ tokens: ['zzz', 'qqq'], page: 1, perPage: 10 })

    expect(result.items).toEqual([])
    expect(result.totalCount).toBe(0)
    // 🔴 `relaxed` は「実際に 1 語へ緩めたか」。試みただけで true にすると、UI が空の語で
    //    「『』だけで絞り込んだ」と注記してしまう（完全 0 件の空状態が壊れる）。
    expect(result.relaxed).toBe(false)
    expect(result.usedTokens).toEqual([])
  })

  it('1 語だけの検索がヒットしないときも relaxed は false（緩和の余地がない）', async () => {
    const port = new StaticGemIndex(stubReader(searchFiles))

    const result = await port.search({ tokens: ['zzz'], page: 1, perPage: 10 })

    expect(result.totalCount).toBe(0)
    expect(result.relaxed).toBe(false)
    expect(result.usedTokens).toEqual([])
  })

  it('一覧に必要な項目（packageName / stars / dependentCount / registry）が揃って返る', async () => {
    const port = new StaticGemIndex(stubReader(searchFiles))

    const result = await port.search({ tokens: ['solo'], page: 1, perPage: 10 })

    expect(result.items).toHaveLength(1)
    const item = result.items[0]!
    expect(item.packageName).toBe('solo')
    expect(item.repositoryFullName).toBe('delta/solo')
    expect(item.dependentCount).toBe(60)
    expect(item.stars).toBe(1)
    expect(item.registry).toBe('pypi.org')
    expect(gemIndexValue(item.gemIndex)).toBe(-10)
  })

  it('内部の派生値（照合用トークン等）は返り値に載せない', async () => {
    const port = new StaticGemIndex(stubReader(searchFiles))

    const result = await port.search({ tokens: ['solo'], page: 1, perPage: 10 })

    expect(Object.keys(result.items[0]!).sort()).toEqual([
      'dependentCount',
      'gemIndex',
      'packageName',
      'registry',
      'repositoryFullName',
      'stars',
    ])
  })

  it('page / perPage でスライスし、totalCount は絞り込み後の全件数を返す', async () => {
    const port = new StaticGemIndex(stubReader(searchFiles))

    const page2 = await port.search({ tokens: [], page: 2, perPage: 2 })
    const page3 = await port.search({ tokens: [], page: 3, perPage: 2 })

    expect(names(page2.items)).toEqual(['beta/orm-client', 'Gamma/Image-Tools'])
    expect(page2.totalCount).toBe(5)
    expect(names(page3.items)).toEqual(['delta/solo'])
    expect(page3.totalCount).toBe(5)
  })

  it('範囲外のページは空配列（totalCount は変わらない）', async () => {
    const port = new StaticGemIndex(stubReader(searchFiles))

    const result = await port.search({ tokens: [], page: 99, perPage: 2 })

    expect(result.items).toEqual([])
    expect(result.totalCount).toBe(5)
  })

  it('出典メタデータ（index.json の meta）を返す', async () => {
    const port = new StaticGemIndex(stubReader(searchFiles))

    const result = await port.search({ tokens: [], page: 1, perPage: 1 })

    expect(result.meta).toEqual(POOL_META)
  })

  it('読み込みに失敗しても throw せず空結果を返す（meta は既定値）', async () => {
    const port = new StaticGemIndex(stubReader({}))

    const result = await port.search({ tokens: ['orm'], page: 1, perPage: 10 })

    expect(result.items).toEqual([])
    expect(result.totalCount).toBe(0)
    expect(result.usedTokens).toEqual([])
    expect(result.relaxed).toBe(false)
    expect(result.meta).toEqual(FALLBACK_META)
  })

  it('AssetReader が例外を投げても空結果に倒す', async () => {
    const reader: AssetReader = async () => {
      throw new Error('boom')
    }

    await expect(
      new StaticGemIndex(reader).search({ tokens: ['orm'], page: 1, perPage: 10 }),
    ).resolves.toEqual({
      items: [],
      totalCount: 0,
      usedTokens: [],
      relaxed: false,
      meta: FALLBACK_META,
    })
  })

  it('registry の無いシャードはスキップして警告する（一覧はレジストリ名を表示するため）', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    const reader = stubReader({
      [INDEX_PATH]: indexJsonWithMeta(['ok.json', 'noRegistry.json']),
      '/data/gem-index/ok.json': registryShardJson('npmjs.org', [
        ['acme/keep', 'keep', 1, 1, -1],
      ]),
      '/data/gem-index/noRegistry.json': JSON.stringify({
        columns: ['repositoryFullName', 'packageName', 'dependentCount', 'stars', 'gemIndex'],
        entries: [['acme/drop', 'drop', 1, 1, -2]],
      }),
    })

    const result = await new StaticGemIndex(reader).search({ tokens: [], page: 1, perPage: 10 })

    expect(names(result.items)).toEqual(['acme/keep'])
    expect(warn).toHaveBeenCalled()
  })

  it('同一 repo が複数レジストリにあっても 1 件に畳む（Gem Index が小さい方を採る）', async () => {
    const reader = stubReader({
      [INDEX_PATH]: indexJsonWithMeta(['first.json', 'second.json']),
      '/data/gem-index/first.json': registryShardJson('npmjs.org', [
        ['Acme/Dup', 'dup-npm', 10, 1, -10],
      ]),
      '/data/gem-index/second.json': registryShardJson('pypi.org', [
        ['acme/dup', 'dup-pypi', 20, 2, -90],
      ]),
    })

    const result = await new StaticGemIndex(reader).search({ tokens: ['dup'], page: 1, perPage: 10 })

    expect(result.totalCount).toBe(1)
    expect(gemIndexValue(result.items[0]!.gemIndex)).toBe(-90)
    expect(result.items[0]!.registry).toBe('pypi.org')
  })

  it('照合用トークンは初回 search の 1 回だけ計算する（warm の search で再 tokenize しない）', async () => {
    const reader = stubReader(searchFiles)
    const port = new StaticGemIndex(reader)

    await port.search({ tokens: ['orm'], page: 1, perPage: 10 })
    const afterFirstSearch = tokenize.calls
    expect(afterFirstSearch).toBeGreaterThan(0)

    await port.search({ tokens: ['client'], page: 1, perPage: 10 })
    await port.search({ tokens: ['image', 'client'], page: 1, perPage: 10 })

    expect(tokenize.calls).toBe(afterFirstSearch)
    expect(reader.calls).toHaveLength(3) // index.json + シャード 2 本（取得も 1 セットだけ）
  })

  it('🔴 lookup だけを呼んだときは tokenize を一度も走らせない（一覧専用コストの遅延化）', async () => {
    const reader = stubReader(searchFiles)
    const port = new StaticGemIndex(reader)

    await port.lookup(['acme/orm-core'])
    await port.lookup(['delta/solo'])

    // 検索インデックス（tokenize + 並べ替え・実測で約 122ms）は search が来るまで作らない。
    expect(tokenize.calls).toBe(0)
    expect(reader.calls).toHaveLength(3) // プール（第 1 段）は作られている
  })

  it('lookup の後に search しても検索インデックスの構築は 1 回だけ', async () => {
    const port = new StaticGemIndex(stubReader(searchFiles))

    await port.lookup(['acme/orm-core'])
    expect(tokenize.calls).toBe(0)

    await port.search({ tokens: ['orm'], page: 1, perPage: 10 })
    const afterFirstSearch = tokenize.calls
    await port.search({ tokens: ['orm'], page: 1, perPage: 10 })

    expect(afterFirstSearch).toBeGreaterThan(0)
    expect(tokenize.calls).toBe(afterFirstSearch)
  })

  it('並行に search しても検索インデックスは 1 回しか作らない（第 2 段も singleton）', async () => {
    const port = new StaticGemIndex(stubReader(searchFiles))
    const serial = new StaticGemIndex(stubReader(searchFiles))

    // 直列 1 回分の tokenize 回数を基準にする。
    await serial.search({ tokens: ['orm'], page: 1, perPage: 10 })
    const oneBuild = tokenize.calls
    resetGemIndexCacheForTest()
    tokenize.calls = 0

    const [first, second] = await Promise.all([
      port.search({ tokens: ['orm'], page: 1, perPage: 10 }),
      port.search({ tokens: ['client'], page: 1, perPage: 10 }),
    ])

    expect(tokenize.calls).toBe(oneBuild) // 2 本走っても構築は 1 回
    expect(first.totalCount).toBe(2)
    expect(second.totalCount).toBe(2)
  })

  it('インスタンスが別でも検索インデックスの singleton を共有する', async () => {
    const reader = stubReader(searchFiles)

    await new StaticGemIndex(reader).search({ tokens: ['orm'], page: 1, perPage: 10 })
    const afterFirst = tokenize.calls
    await new StaticGemIndex(reader).search({ tokens: ['client'], page: 1, perPage: 10 })

    expect(tokenize.calls).toBe(afterFirst)
  })

  it('🔴 検索インデックスの構築が失敗しても lookup は従来どおり動く（段が独立している）', async () => {
    const reader = stubReader(searchFiles)
    const port = new StaticGemIndex(reader)
    tokenize.fail = true

    const result = await port.search({ tokens: ['orm'], page: 1, perPage: 10 })
    const found = await port.lookup(['acme/orm-core', 'delta/solo'])

    expect(result.items).toEqual([])
    expect(result.totalCount).toBe(0)
    expect(result.meta).toEqual(POOL_META) // プール（第 1 段）は生きているので出典は返せる
    expect(found.size).toBe(2)
    expect(gemIndexValue(found.get('acme/orm-core')!)).toBe(-70)
  })

  it('検索インデックスの構築に失敗した Promise はキャッシュしない（次の search で再試行して成功する）', async () => {
    const port = new StaticGemIndex(stubReader(searchFiles))
    tokenize.fail = true

    expect((await port.search({ tokens: ['orm'], page: 1, perPage: 10 })).totalCount).toBe(0)

    tokenize.fail = false
    const retried = await port.search({ tokens: ['orm'], page: 1, perPage: 10 })

    expect(retried.totalCount).toBe(2)
    expect(names(retried.items)).toEqual(['acme/orm-core', 'beta/orm-client'])
  })

  it('lookup と search は同じ 1 回の読み込み・parse を共有する（アセットを増やさない）', async () => {
    const reader = stubReader(searchFiles)
    const port = new StaticGemIndex(reader)

    const found = await port.lookup(['acme/orm-core'])
    const afterLookup = [...reader.calls]
    const result = await port.search({ tokens: ['orm'], page: 1, perPage: 10 })

    expect(gemIndexValue(found.get('acme/orm-core')!)).toBe(-70)
    expect(result.totalCount).toBe(2)
    expect(reader.calls).toEqual(afterLookup)
    expect(afterLookup).toHaveLength(3)
  })
})
