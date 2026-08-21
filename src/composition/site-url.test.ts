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
})
