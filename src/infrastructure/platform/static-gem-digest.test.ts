import { describe, expect, it } from 'vitest'

import { DomainValidationError } from '../../domain/errors'
import { gemIndexValue } from '../../domain/model/gem-index'
import { StaticGemDigest } from './static-gem-digest'

describe('StaticGemDigest', () => {
  it('本物の public/data/daily-digest.json を通しで読み込める（件数 > 0）', async () => {
    const port = new StaticGemDigest()
    const { candidates, meta } = await port.listCandidates()

    expect(candidates.length).toBeGreaterThan(0)
    expect(meta.source).toBeTruthy()
    expect(meta.license).toBeTruthy()
    expect(meta.sourceLicenseUrl).toMatch(/^https?:\/\//)
    expect(meta.generatedAt).toMatch(/^\d{4}-\d{2}-\d{2}T/)
  })

  it('meta の 4 フィールド（source / license / sourceLicenseUrl / generatedAt）が全て string で揃う（D-29）', async () => {
    const port = new StaticGemDigest()
    const { meta } = await port.listCandidates()

    expect(typeof meta.source).toBe('string')
    expect(typeof meta.license).toBe('string')
    expect(typeof meta.sourceLicenseUrl).toBe('string')
    expect(typeof meta.generatedAt).toBe('string')
  })

  it('各候補は Gem 型の shape を満たし gemIndex は number として取り出せる（ブランド化されている）', async () => {
    const port = new StaticGemDigest()
    const { candidates } = await port.listCandidates()

    for (const gem of candidates) {
      expect(typeof gem.packageName).toBe('string')
      expect(gem.packageName.length).toBeGreaterThan(0)
      expect(gem.repositoryFullName).toMatch(/.+\/.+/)
      expect(Number.isFinite(gem.dependentCount)).toBe(true)
      expect(Number.isFinite(gem.stars)).toBe(true)
      expect(typeof gemIndexValue(gem.gemIndex)).toBe('number')
    }
  })

  it('candidates が空配列でも例外を吐かない（D-28 SPOF 方針: 配信自体は止めず鮮度のみ劣化させる）', async () => {
    const emptyish = {
      date: '20260820',
      meta: {
        source: 'Ecosyste.ms',
        license: 'CC BY-SA 4.0',
        sourceLicenseUrl: 'https://creativecommons.org/licenses/by-sa/4.0/',
        generatedAt: '2026-08-20T00:00:00Z',
      },
      candidates: [],
    }
    const port = new StaticGemDigest(emptyish)
    const { candidates, meta } = await port.listCandidates()

    expect(candidates).toEqual([])
    expect(meta.source).toBe('Ecosyste.ms')
  })

  it('meta が欠落している JSON は DomainValidationError で拒否する', async () => {
    const port = new StaticGemDigest({ date: '20260820', candidates: [] })
    await expect(port.listCandidates()).rejects.toThrow(DomainValidationError)
  })

  it('candidates 内で数値であるべきフィールドが欠落した場合は DomainValidationError', async () => {
    const port = new StaticGemDigest({
      date: '20260820',
      meta: {
        source: 'Ecosyste.ms',
        license: 'CC BY-SA 4.0',
        sourceLicenseUrl: 'https://creativecommons.org/licenses/by-sa/4.0/',
        generatedAt: '2026-08-20T00:00:00Z',
      },
      candidates: [
        {
          packageName: 'chalk',
          repositoryFullName: 'chalk/chalk',
          dependentCount: 'not-a-number',
          stars: 22000,
          gemIndex: -63.9,
        },
      ],
    })
    await expect(port.listCandidates()).rejects.toThrow(DomainValidationError)
  })

  it('repositoryFullName が owner/repo 形式でない場合は DomainValidationError', async () => {
    const port = new StaticGemDigest({
      date: '20260820',
      meta: {
        source: 'Ecosyste.ms',
        license: 'CC BY-SA 4.0',
        sourceLicenseUrl: 'https://creativecommons.org/licenses/by-sa/4.0/',
        generatedAt: '2026-08-20T00:00:00Z',
      },
      candidates: [
        {
          packageName: 'foo',
          repositoryFullName: 'no-slash-here',
          dependentCount: 1,
          stars: 1,
          gemIndex: 0,
        },
      ],
    })
    await expect(port.listCandidates()).rejects.toThrow(DomainValidationError)
  })

  it('gemIndex が非有限（NaN / Infinity）の場合は gemIndex スマートコンストラクタが弾く', async () => {
    const port = new StaticGemDigest({
      date: '20260820',
      meta: {
        source: 'Ecosyste.ms',
        license: 'CC BY-SA 4.0',
        sourceLicenseUrl: 'https://creativecommons.org/licenses/by-sa/4.0/',
        generatedAt: '2026-08-20T00:00:00Z',
      },
      candidates: [
        {
          packageName: 'foo',
          repositoryFullName: 'org/foo',
          dependentCount: 1,
          stars: 1,
          gemIndex: Number.POSITIVE_INFINITY,
        },
      ],
    })
    await expect(port.listCandidates()).rejects.toThrow(DomainValidationError)
  })

  it('トップレベルが配列（オブジェクトでない）JSON は DomainValidationError', async () => {
    const port = new StaticGemDigest([])
    await expect(port.listCandidates()).rejects.toThrow(DomainValidationError)
  })
})
