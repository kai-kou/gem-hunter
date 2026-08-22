/**
 * generate_gem_digest.test.mjs — CLI オーケストレーション（引数解析・キャッシュ制御）のテスト。
 *
 * PR #423 セルフレビュー指摘 1（CRITICAL）対応: 本ファイルが存在するまで `parseArgs` /
 * `collectWithCache` 等は 1 つも export されておらず、しかもモジュール読み込み時に
 * トップレベルで `main()` が起動してしまい、import するだけで実ネットワーク収集・実ファイル
 * 書き込みが走る構造だった。本ファイルの import はその実行ガード（`isDirectRun()`）が
 * 効いていることの前提でもある（効いていなければ最初の import で本番処理が走って壊れる）。
 *
 * 🔴 実ネットワークに触れない: `collectWithCache` の収集関数は必ず注入する。
 */
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import {
  collectWithCache,
  parseArgs,
  parseIntOption,
  resolveOutDir,
} from './generate_gem_digest.mjs'
import {
  DEFAULT_MIN_DOWNLOADS_PER_DEPENDENT,
  DEFAULT_ZERO_STAR_DEPENDENT_THRESHOLD,
} from './gem-pool/pipeline.mjs'
import { DEFAULT_QUOTA, REGISTRIES, findRegistry } from './gem-pool/registries.mjs'

describe('parseIntOption', () => {
  it('min 以上の数値を floor して返す', () => {
    expect(parseIntOption('5', '--x', { min: 1 })).toBe(5)
    expect(parseIntOption('5.9', '--x', { min: 1 })).toBe(5)
  })

  it('min 未満は throw する', () => {
    expect(() => parseIntOption('0', '--x', { min: 1 })).toThrow('--x')
    expect(() => parseIntOption('-1', '--x', { min: 0 })).toThrow('--x')
  })

  it('min: 0 のとき 0 を許す（無効化フラグ用途）', () => {
    expect(parseIntOption('0', '--min-downloads-per-dependent', { min: 0 })).toBe(0)
  })

  it('数値でない入力は throw する', () => {
    expect(() => parseIntOption('abc', '--x', { min: 1 })).toThrow('--x')
    expect(() => parseIntOption(undefined, '--x', { min: 1 })).toThrow('--x')
  })
})

describe('parseArgs', () => {
  it('引数なしなら既定値を返す（各モジュールの既定値と一致すること）', () => {
    const out = parseArgs([])
    expect(out.quota).toBe(DEFAULT_QUOTA)
    expect(out.registries).toEqual(REGISTRIES)
    expect(out.digestLimit).toBe(300)
    expect(out.zeroStarDependentThreshold).toBe(DEFAULT_ZERO_STAR_DEPENDENT_THRESHOLD)
    expect(out.minDownloadsPerDependent).toBe(DEFAULT_MIN_DOWNLOADS_PER_DEPENDENT)
    expect(out.outDir).toBe('public/data')
    expect(out.writeShards).toBe(true)
    expect(out.cacheDir).toBeNull()
  })

  it('全フラグを正しくマップする', () => {
    const out = parseArgs([
      '--quota',
      '500',
      '--registries',
      'npm,pypi',
      '--digest-limit',
      '10',
      '--zero-star-dependent-threshold',
      '200',
      '--min-downloads-per-dependent',
      '5',
      '--out-dir',
      '/tmp/out',
      '--no-shards',
      '--cache-dir',
      '/tmp/cache',
    ])

    expect(out.quota).toBe(500)
    expect(out.registries).toEqual([findRegistry('npm'), findRegistry('pypi')])
    expect(out.digestLimit).toBe(10)
    expect(out.zeroStarDependentThreshold).toBe(200)
    expect(out.minDownloadsPerDependent).toBe(5)
    expect(out.outDir).toBe('/tmp/out')
    expect(out.writeShards).toBe(false)
    expect(out.cacheDir).toBe('/tmp/cache')
  })

  it('--min-downloads-per-dependent 0 は通る（無効化できる）', () => {
    const out = parseArgs(['--min-downloads-per-dependent', '0'])
    expect(out.minDownloadsPerDependent).toBe(0)
  })

  it('--quota 0 は弾かれる（この非対称が仕様）', () => {
    expect(() => parseArgs(['--quota', '0'])).toThrow('--quota')
  })

  it('未知の引数は throw する', () => {
    expect(() => parseArgs(['--bogus'])).toThrow('未知の引数')
  })

  it('不正な数値は throw する', () => {
    expect(() => parseArgs(['--quota', 'abc'])).toThrow('--quota')
  })

  it('--registries に未知 id を渡すと findRegistry 由来のエラーが伝播する', () => {
    expect(() => parseArgs(['--registries', 'npm,nope'])).toThrow('未知のレジストリ id')
  })
})

describe('resolveOutDir', () => {
  it('リポジトリルートからの相対パスを絶対パスへ解決する', () => {
    const resolved = resolveOutDir('public/data')
    expect(resolved.endsWith(join('public', 'data'))).toBe(true)
    expect(resolved).not.toBe('public/data') // 絶対パス化されている
  })
})

describe('collectWithCache', () => {
  let dir

  beforeEach(async () => {
    dir = await mkdtemp(join(tmpdir(), 'gem-digest-cache-'))
  })

  afterEach(async () => {
    await rm(dir, { recursive: true, force: true })
  })

  it('キャッシュヒット時は収集関数を呼ばない', async () => {
    const registry = findRegistry('npm')
    await writeFile(join(dir, 'npm.json'), JSON.stringify([{ name: 'cached-pkg' }]), 'utf8')

    let calls = 0
    const collect = async () => {
      calls += 1
      return [{ name: 'network-pkg' }]
    }

    const collected = await collectWithCache({
      registries: [registry],
      quota: 10,
      perPage: 10,
      cacheDir: dir,
      collect,
    })

    expect(calls).toBe(0)
    expect(collected).toEqual([{ registry: 'npm', packages: [{ name: 'cached-pkg' }] }])
  })

  it('キャッシュミス時は収集関数を呼び、結果をキャッシュへ書き込む', async () => {
    const registry = findRegistry('pypi')
    let calls = 0
    const requestTally = { count: 0 }
    const collect = async ({ onProgress }) => {
      calls += 1
      onProgress?.({ registry: registry.id, page: 1, fetched: 1 })
      return [{ name: 'fresh-pkg' }]
    }

    const collected = await collectWithCache({
      registries: [registry],
      quota: 10,
      perPage: 10,
      cacheDir: dir,
      collect,
      requestTally,
    })

    expect(calls).toBe(1)
    expect(requestTally.count).toBe(1)
    expect(collected).toEqual([{ registry: 'pypi', packages: [{ name: 'fresh-pkg' }] }])

    const cachedOnDisk = JSON.parse(await readFile(join(dir, 'pypi.json'), 'utf8'))
    expect(cachedOnDisk).toEqual([{ name: 'fresh-pkg' }])
  })

  it('cacheDir なしなら常に収集関数を呼び、ファイルは書かない', async () => {
    const registry = findRegistry('cargo')
    let calls = 0
    const collect = async () => {
      calls += 1
      return [{ name: 'no-cache-pkg' }]
    }

    const collected = await collectWithCache({
      registries: [registry],
      quota: 10,
      perPage: 10,
      cacheDir: null,
      collect,
    })

    expect(calls).toBe(1)
    expect(collected).toEqual([{ registry: 'cargo', packages: [{ name: 'no-cache-pkg' }] }])
  })

  it('複数レジストリをキャッシュ有無混在で処理する', async () => {
    const npm = findRegistry('npm')
    const pypi = findRegistry('pypi')
    await writeFile(join(dir, 'npm.json'), JSON.stringify([{ name: 'cached' }]), 'utf8')

    let calls = 0
    const collect = async ({ registry }) => {
      calls += 1
      return [{ name: `fresh-${registry.id}` }]
    }

    const collected = await collectWithCache({
      registries: [npm, pypi],
      quota: 10,
      perPage: 10,
      cacheDir: dir,
      collect,
    })

    expect(calls).toBe(1) // pypi だけ収集が走る
    expect(collected).toEqual([
      { registry: 'npm', packages: [{ name: 'cached' }] },
      { registry: 'pypi', packages: [{ name: 'fresh-pypi' }] },
    ])
  })
})
