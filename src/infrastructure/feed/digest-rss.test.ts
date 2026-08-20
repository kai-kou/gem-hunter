import { describe, expect, it } from 'vitest'

import { gemIndex } from '../../domain/model/gem-index'
import type { DailyDigest } from '../../domain/model/gem'
import type { DateSeed } from '../../domain/model/date-seed'
import { renderDigestRss } from './digest-rss'

function makeDigest(overrides: Partial<DailyDigest> = {}): DailyDigest {
  return {
    date: '20260820' as DateSeed,
    items: [
      {
        packageName: 'left-pad',
        repositoryFullName: 'left-pad-owner/left-pad',
        dependentCount: 12345,
        stars: 42,
        gemIndex: gemIndex(-30),
      },
      {
        packageName: 'is-odd & is-even <fancy>',
        repositoryFullName: 'odd-owner/is-odd-repo',
        dependentCount: 1,
        stars: 0,
        gemIndex: gemIndex(10),
      },
    ],
    meta: {
      source: 'Ecosyste.ms',
      license: 'CC BY-SA 4.0',
      sourceLicenseUrl: 'https://creativecommons.org/licenses/by-sa/4.0/',
      generatedAt: '2026-08-20T00:00:00.000Z',
    },
    ...overrides,
  }
}

describe('renderDigestRss', () => {
  it('RSS 2.0 のルート要素と channel メタを含む', () => {
    const xml = renderDigestRss(makeDigest(), { origin: 'https://gem-hunter.example.com' })

    expect(xml.startsWith('<?xml version="1.0" encoding="UTF-8"?>')).toBe(true)
    expect(xml).toContain('<rss version="2.0"')
    expect(xml).toContain('<channel>')
    expect(xml).toContain('<link>https://gem-hunter.example.com</link>')
    expect(xml).toContain('<generator>')
  })

  it('meta.generatedAt を RFC 822 の lastBuildDate に変換する', () => {
    const xml = renderDigestRss(makeDigest(), { origin: 'https://example.com' })

    // 2026-08-20T00:00:00.000Z -> Thu, 20 Aug 2026 00:00:00 GMT
    expect(xml).toContain('<lastBuildDate>Thu, 20 Aug 2026 00:00:00 GMT</lastBuildDate>')
  })

  it('出典（source/license/sourceLicenseUrl）を帰属表示として含む（D-29）', () => {
    const xml = renderDigestRss(makeDigest(), { origin: 'https://example.com' })

    expect(xml).toContain('Ecosyste.ms')
    expect(xml).toContain('CC BY-SA 4.0')
    expect(xml).toContain('https://creativecommons.org/licenses/by-sa/4.0/')
  })

  it('items の件数が digest.items と一致する', () => {
    const digest = makeDigest()
    const xml = renderDigestRss(digest, { origin: 'https://example.com' })

    const itemCount = (xml.match(/<item>/g) ?? []).length
    expect(itemCount).toBe(digest.items.length)
  })

  it('item の title に packageName、link に repositoryFullName 由来の詳細ページ URL を使う', () => {
    const xml = renderDigestRss(makeDigest(), { origin: 'https://example.com' })

    expect(xml).toContain('<title>left-pad</title>')
    expect(xml).toContain('<link>https://example.com/ja/repos/left-pad-owner/left-pad</link>')
  })

  it('description は数値のみの自作文で、生テキスト（description 等）を含まない', () => {
    const xml = renderDigestRss(makeDigest(), { origin: 'https://example.com' })

    // 生テキストを domain に持たないため混入自体が不可能だが、数値が反映されていることは確認する
    expect(xml).toContain('12345')
    expect(xml).toContain('42')
    expect(xml).toContain('-30')
  })

  it('guid は isPermaLink=false で date + packageName ベースの一意な値', () => {
    const xml = renderDigestRss(makeDigest(), { origin: 'https://example.com' })

    expect(xml).toContain('<guid isPermaLink="false">20260820:left-pad</guid>')
  })

  it('XML 特殊文字（& < > " \'）をエスケープする（二重エスケープしない）', () => {
    const xml = renderDigestRss(makeDigest(), { origin: 'https://example.com' })

    expect(xml).toContain('is-odd &amp; is-even &lt;fancy&gt;')
    expect(xml).not.toContain('&amp;amp;')
    expect(xml).not.toContain('&amp;lt;')
  })

  it('items が空配列でも channel だけの妥当な RSS を返す', () => {
    const xml = renderDigestRss(makeDigest({ items: [] }), { origin: 'https://example.com' })

    expect(xml).toContain('<channel>')
    expect(xml.match(/<item>/g)).toBeNull()
  })
})
