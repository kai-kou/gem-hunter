import { mkdtemp, mkdir, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { createFileSystemAssetReader, createWorkersAssetReader } from './asset-reader'

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
})

describe('createWorkersAssetReader', () => {
  beforeEach(() => {
    vi.spyOn(console, 'warn').mockImplementation(() => undefined)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('binding の fetch が 200 を返せば本文を返す', async () => {
    const fetch = vi.fn(async () => new Response('{"ok":true}', { status: 200 }))
    const read = createWorkersAssetReader({ fetch })

    await expect(read('/data/gem-index/index.json')).resolves.toBe('{"ok":true}')
    const requested = fetch.mock.calls[0]?.[0] as URL
    expect(String(requested)).toBe('https://assets.local/data/gem-index/index.json')
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
})
