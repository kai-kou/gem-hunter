import { describe, expect, it } from 'vitest'

import { buildGemListUrl, rawBadgedOf } from './gem-list-url'

const DEFAULTS = { keyword: '', page: 1, sort: 'relevance', perPage: 20 }

describe('buildGemListUrl', () => {
  it('badgedFullNames が空配列なら badged クエリを付けない', () => {
    const url = buildGemListUrl('/ja/gems', { ...DEFAULTS, keyword: 'next' }, [])

    expect(url).toBe('/ja/gems?q=next')
    expect(new URLSearchParams(url.split('?')[1]).has('badged')).toBe(false)
  })

  it('複数件の fullName をカンマ区切りで載せ、rawBadgedOf で往復できる', () => {
    const badgedFullNames = ['vercel/next.js', 'facebook/react']
    const url = buildGemListUrl('/ja/gems', { ...DEFAULTS, keyword: 'next.js' }, badgedFullNames)

    const params = new URLSearchParams(url.split('?')[1])
    expect(params.get('badged')).toBe('vercel/next.js,facebook/react')
    expect(rawBadgedOf({ badged: params.get('badged') ?? undefined })).toBe(
      'vercel/next.js,facebook/react',
    )
  })

  it('既存クエリ（q / page）と共存する', () => {
    const url = buildGemListUrl('/ja/gems', { ...DEFAULTS, keyword: 'left pad', page: 3 }, [
      'stevemao/left-pad',
    ])

    const params = new URLSearchParams(url.split('?')[1])
    expect(params.get('q')).toBe('left pad')
    expect(params.get('page')).toBe('3')
    expect(params.get('badged')).toBe('stevemao/left-pad')
  })
})

describe('rawBadgedOf', () => {
  it('badged が未指定なら空文字を返す', () => {
    expect(rawBadgedOf({})).toBe('')
  })

  it('配列で来たら先頭の値を採る（rawKeywordOf と同じ流儀）', () => {
    expect(rawBadgedOf({ badged: ['a/b', 'c/d'] })).toBe('a/b')
  })

  it('単一値をそのまま返す', () => {
    expect(rawBadgedOf({ badged: 'a/b,c/d' })).toBe('a/b,c/d')
  })
})
