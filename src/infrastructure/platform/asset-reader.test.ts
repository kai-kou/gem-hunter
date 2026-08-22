import { mkdtemp, mkdir, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { createFileSystemAssetReader, createWorkersAssetReader } from './asset-reader'

/**
 * 生文字列には `..` が現れないのに、`new URL()` の正規化でディレクトリ脱出・別オリジンに化ける
 * 入力。**両経路とも同じ判定で拒否する**（経路によって受理される入力が変わらない）。
 */
const TRAVERSAL_PATHS = [
  '/data/gem-index/%2e%2e/%2e%2e/secret.json', // → '/secret.json'
  '/data/gem-index/%2E%2E/etc.json', // → '/data/etc.json'
  '//evil.com/x.json', // → 別オリジン
] as const

describe('createFileSystemAssetReader', () => {
  let baseDir: string

  beforeEach(async () => {
    baseDir = await mkdtemp(join(tmpdir(), 'asset-reader-'))
    await mkdir(join(baseDir, 'data', 'gem-index'), { recursive: true })
    await writeFile(join(baseDir, 'data', 'gem-index', 'index.json'), '{"totalCount":1}', 'utf8')
    // ベースディレクトリの外側に置いたファイル（トラバーサルで到達されてはいけない）。
    await writeFile(join(baseDir, '..', 'asset-reader-outside.txt'), 'secret', 'utf8')
    vi.spyOn(console, 'warn').mockImplementation(() => undefined)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('ベースディレクトリ配下のファイルを本文として読める', async () => {
    const read = createFileSystemAssetReader(baseDir)

    await expect(read('/data/gem-index/index.json')).resolves.toBe('{"totalCount":1}')
  })

  it('存在しないファイルは例外ではなく null を返す', async () => {
    const read = createFileSystemAssetReader(baseDir)

    await expect(read('/data/gem-index/missing.json')).resolves.toBeNull()
  })

  it('`..` を含むパスは読まずに null を返す（パストラバーサル防止）', async () => {
    const read = createFileSystemAssetReader(baseDir)

    await expect(read('/../asset-reader-outside.txt')).resolves.toBeNull()
    await expect(read('/data/../../asset-reader-outside.txt')).resolves.toBeNull()
  })

  it('先頭スラッシュのない相対パスは受け付けない', async () => {
    const read = createFileSystemAssetReader(baseDir)

    await expect(read('data/gem-index/index.json')).resolves.toBeNull()
  })

  it.each(TRAVERSAL_PATHS)('正規化で階層を移動するパスは受け付けない: %s', async (path) => {
    const read = createFileSystemAssetReader(baseDir)

    await expect(read(path)).resolves.toBeNull()
  })
})

describe('createWorkersAssetReader', () => {
  beforeEach(() => {
    vi.spyOn(console, 'warn').mockImplementation(() => undefined)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('binding の fetch が 200 を返せば本文を返す', async () => {
    const requested: URL[] = []
    const fetch = vi.fn(async (input: URL) => {
      requested.push(input)
      return new Response('{"ok":true}', { status: 200 })
    })
    const read = createWorkersAssetReader({ fetch })

    await expect(read('/data/gem-index/index.json')).resolves.toBe('{"ok":true}')
    expect(String(requested[0])).toBe('https://assets.local/data/gem-index/index.json')
  })

  it('404 は null（例外にしない）', async () => {
    const fetch = vi.fn(async () => new Response('not found', { status: 404 }))
    const read = createWorkersAssetReader({ fetch })

    await expect(read('/data/gem-index/missing.json')).resolves.toBeNull()
  })

  it('fetch が例外を投げても null に倒す', async () => {
    const fetch = vi.fn(async () => {
      throw new Error('binding unavailable')
    })
    const read = createWorkersAssetReader({ fetch })

    await expect(read('/data/gem-index/index.json')).resolves.toBeNull()
  })

  it('不正なパスは binding を呼ばずに null を返す', async () => {
    const fetch = vi.fn(async () => new Response('{}', { status: 200 }))
    const read = createWorkersAssetReader({ fetch })

    await expect(read('/data/../secret.json')).resolves.toBeNull()
    await expect(read('data/gem-index/index.json')).resolves.toBeNull()
    expect(fetch).not.toHaveBeenCalled()
  })

  it.each(TRAVERSAL_PATHS)(
    '正規化で階層を移動するパスは binding を呼ばずに null: %s',
    async (path) => {
      const fetch = vi.fn(async () => new Response('secret', { status: 200 }))
      const read = createWorkersAssetReader({ fetch })

      await expect(read(path)).resolves.toBeNull()
      expect(fetch).not.toHaveBeenCalled()
    },
  )

  it('AbortSignal.timeout が使える環境では signal を渡す', async () => {
    let received: { signal?: AbortSignal } | undefined
    const fetch = vi.fn(async (input: URL, init?: { signal?: AbortSignal }) => {
      received = init
      return new Response(String(input), { status: 200 })
    })
    const read = createWorkersAssetReader({ fetch })

    await read('/data/gem-index/index.json')

    if (typeof AbortSignal.timeout === 'function') {
      expect(received?.signal).toBeInstanceOf(AbortSignal)
      expect(received?.signal?.aborted).toBe(false)
    } else {
      expect(received).toBeUndefined()
    }
  })

  it('binding.fetch が応答を返さなくても上限時間で null に倒す（ハング対策）', async () => {
    vi.useFakeTimers()
    try {
      // 決して解決しない fetch（reject もしないため呼び出し側の catch では拾えない）。
      const fetch = vi.fn(() => new Promise<Response>(() => undefined))
      const read = createWorkersAssetReader({ fetch })

      const pending = read('/data/gem-index/index.json')
      // 上限（2,000ms）までタイマーを進めれば解決するので、テスト自体は待たない。
      await vi.advanceTimersByTimeAsync(2_000)

      await expect(pending).resolves.toBeNull()
    } finally {
      vi.useRealTimers()
    }
  })
})
