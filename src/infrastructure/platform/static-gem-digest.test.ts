import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { gemIndexValue } from '../../domain/model/gem-index'
import { StaticGemDigest } from './static-gem-digest'

const validMeta = {
  source: 'Ecosyste.ms',
  license: 'CC BY-SA 4.0',
  sourceLicenseUrl: 'https://creativecommons.org/licenses/by-sa/4.0/',
  generatedAt: '2026-08-20T00:00:00Z',
}

function withCandidates(candidates: unknown): unknown {
  return { date: '20260820', meta: validMeta, candidates }
}

describe('StaticGemDigest', () => {
  // 不正入力は `console.warn` でログだけ残す設計なので、テスト出力を汚さないよう黙らせる。
  beforeEach(() => {
    vi.spyOn(console, 'warn').mockImplementation(() => undefined)
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('本物の public/data/daily-digest.json を通しで読み込める（件数 > 0）', async () => {
    const port = new StaticGemDigest()
    const { candidates, meta } = await port.listCandidates()

    expect(candidates.length).toBeGreaterThan(0)
    expect(meta.source).toBeTruthy()
    expect(meta.license).toBeTruthy()
    expect(meta.sourceLicenseUrl).toMatch(/^https?:\/\//)
    expect(meta.generatedAt).toMatch(/^\d{4}-\d{2}-\d{2}T/)
    // 本物のデータは 1 件もスキップされない（バッチ出力が契約を満たしている）。
    expect(console.warn).not.toHaveBeenCalled()
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
      expect(gem.repositoryFullName).toMatch(/^[^/\s]+\/[^/\s]+$/)
      expect(Number.isFinite(gem.dependentCount)).toBe(true)
      expect(Number.isFinite(gem.stars)).toBe(true)
      expect(typeof gemIndexValue(gem.gemIndex)).toBe('number')
    }
  })

  it('candidates が空配列でも例外を吐かない（D-28 SPOF 方針: 配信自体は止めず鮮度のみ劣化させる）', async () => {
    const port = new StaticGemDigest(withCandidates([]))
    const { candidates, meta } = await port.listCandidates()

    expect(candidates).toEqual([])
    expect(meta.source).toBe('Ecosyste.ms')
  })

  describe('壊れた JSON でも例外を投げずフォールバックする（GemDigestPort の契約 / D-28）', () => {
    it('meta が欠落していても既定の帰属表示へフォールバックする', async () => {
      const port = new StaticGemDigest({ date: '20260820', candidates: [] })

      await expect(port.listCandidates()).resolves.toEqual({
        candidates: [],
        meta: {
          source: 'Ecosyste.ms',
          license: 'CC BY-SA 4.0',
          sourceLicenseUrl: 'https://creativecommons.org/licenses/by-sa/4.0/',
          generatedAt: '',
        },
      })
    })

    it('candidates が配列でなくても空配列へ倒す', async () => {
      const port = new StaticGemDigest(withCandidates('not-an-array'))
      const { candidates, meta } = await port.listCandidates()

      expect(candidates).toEqual([])
      expect(meta.source).toBe('Ecosyste.ms')
    })

    it('トップレベルが配列（オブジェクトでない）JSON でも空の候補プールを返す', async () => {
      const port = new StaticGemDigest([])
      const { candidates, meta } = await port.listCandidates()

      expect(candidates).toEqual([])
      expect(meta.generatedAt).toBe('')
    })

    it('数値であるべきフィールドが壊れたエントリだけをスキップし、正常なエントリは残す', async () => {
      const port = new StaticGemDigest(
        withCandidates([
          {
            packageName: 'chalk',
            repositoryFullName: 'chalk/chalk',
            dependentCount: 'not-a-number',
            stars: 22000,
            gemIndex: -63.9,
          },
          {
            packageName: 'debug',
            repositoryFullName: 'debug-js/debug',
            dependentCount: 92000,
            stars: 11000,
            gemIndex: -70.2,
          },
        ]),
      )
      const { candidates } = await port.listCandidates()

      expect(candidates.map((gem) => gem.packageName)).toEqual(['debug'])
    })

    it('gemIndex が非有限（NaN / Infinity）のエントリはスキップする（gemIndex の throw を持ち込まない）', async () => {
      const port = new StaticGemDigest(
        withCandidates([
          {
            packageName: 'foo',
            repositoryFullName: 'org/foo',
            dependentCount: 1,
            stars: 1,
            gemIndex: Number.POSITIVE_INFINITY,
          },
        ]),
      )

      await expect(port.listCandidates()).resolves.toMatchObject({ candidates: [] })
    })

    it.each([
      ['no-slash-here'],
      ['owner/'],
      ['/repo'],
      ['owner/repo/sub'],
      ['owner repo'],
      ['../..'],
      ['owner/..'],
      ['./repo'],
    ])(
      'repositoryFullName が %s のエントリはスキップする（壊れた詳細リンクを作らない）',
      async (fullName) => {
        const port = new StaticGemDigest(
          withCandidates([
            {
              packageName: 'foo',
              repositoryFullName: fullName,
              dependentCount: 1,
              stars: 1,
              gemIndex: 0,
            },
          ]),
        )

        await expect(port.listCandidates()).resolves.toMatchObject({ candidates: [] })
      },
    )

    it.each([
      ['javascript:alert(1)'],
      ['data:text/html,<script>alert(1)</script>'],
      ['not a url'],
      [42],
    ])(
      'meta.sourceLicenseUrl が %s のときは http(s) の既定 URL へ倒す（javascript: を <a href> に流さない）',
      async (sourceLicenseUrl) => {
        const port = new StaticGemDigest({
          date: '20260820',
          meta: { ...validMeta, sourceLicenseUrl },
          candidates: [],
        })
        const { meta } = await port.listCandidates()

        expect(meta.sourceLicenseUrl).toBe('https://creativecommons.org/licenses/by-sa/4.0/')
      },
    )

    it('meta.sourceLicenseUrl が http URL ならそのまま通す', async () => {
      const port = new StaticGemDigest({
        date: '20260820',
        meta: { ...validMeta, sourceLicenseUrl: 'http://example.com/license' },
        candidates: [],
      })
      const { meta } = await port.listCandidates()

      expect(meta.sourceLicenseUrl).toBe('http://example.com/license')
    })
  })
})
