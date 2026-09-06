import { afterEach, describe, expect, it } from 'vitest'
import { getSiteUrl } from './site-url'

const ORIGINAL = process.env.SITE_URL

afterEach(() => {
  if (ORIGINAL === undefined) {
    delete process.env.SITE_URL
  } else {
    process.env.SITE_URL = ORIGINAL
  }
})

describe('getSiteUrl', () => {
  it('SITE_URL 未設定時は本番 URL へフォールバックする', () => {
    delete process.env.SITE_URL
    expect(getSiteUrl()).toBe('https://gem-hunter.kinamocchi-tech.workers.dev')
  })

  it('SITE_URL が設定されていればその値を返す', () => {
    process.env.SITE_URL = 'https://example.test'
    expect(getSiteUrl()).toBe('https://example.test')
  })

  it('SITE_URL が空文字のときは本番 URL へフォールバックする（Issue #489）', () => {
    process.env.SITE_URL = ''
    expect(getSiteUrl()).toBe('https://gem-hunter.kinamocchi-tech.workers.dev')
  })

  it('SITE_URL が空白のみのときは本番 URL へフォールバックする（Issue #489）', () => {
    process.env.SITE_URL = '   '
    expect(getSiteUrl()).toBe('https://gem-hunter.kinamocchi-tech.workers.dev')
  })

  it('SITE_URL の前後の空白（タブ・改行含む）を取り除いた値を返す（Issue #489）', () => {
    process.env.SITE_URL = '\t\nhttps://example.test\n '
    expect(getSiteUrl()).toBe('https://example.test')
  })
})
