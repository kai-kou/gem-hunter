import { describe, expect, it } from 'vitest'

import { SEARCH_PARAM_KEYS, parseSearchParams } from './search-params'

describe('SEARCH_PARAM_KEYS', () => {
  it('keyword は q、page は page、sort は sort、perPage は per_page に固定されている', () => {
    expect(SEARCH_PARAM_KEYS).toEqual({ keyword: 'q', page: 'page', sort: 'sort', perPage: 'per_page' })
  })
})

const DEFAULTS = { keyword: '', page: 1, sort: 'relevance', perPage: 20 }

describe('parseSearchParams', () => {
  it('q と page をそのまま読み取る', () => {
    expect(parseSearchParams({ q: 'react', page: '2' })).toEqual({
      ...DEFAULTS,
      keyword: 'react',
      page: 2,
    })
  })

  it('q が未指定なら keyword は空文字になる', () => {
    expect(parseSearchParams({})).toEqual(DEFAULTS)
  })

  it('q が前後空白付きならトリムされる（trySearchKeyword に委譲）', () => {
    expect(parseSearchParams({ q: '  react  ' })).toEqual({ ...DEFAULTS, keyword: 'react' })
  })

  it('q が空白のみなら空文字に正規化される（trySearchKeyword が null を返す）', () => {
    expect(parseSearchParams({ q: '   ' })).toEqual(DEFAULTS)
  })

  it('q が配列で来たら先頭の値を採る', () => {
    expect(parseSearchParams({ q: ['first', 'second'] })).toEqual({
      ...DEFAULTS,
      keyword: 'first',
    })
  })

  it('page が配列で来たら先頭の値を採る', () => {
    expect(parseSearchParams({ page: ['3', '4'] })).toEqual({ ...DEFAULTS, page: 3 })
  })

  it('page が数値でない文字列なら 1 に正規化される（tryPageNumber に委譲）', () => {
    expect(parseSearchParams({ page: 'abc' })).toEqual(DEFAULTS)
  })

  it('page が 0 以下なら 1 に正規化される', () => {
    expect(parseSearchParams({ page: '0' })).toEqual(DEFAULTS)
    expect(parseSearchParams({ page: '-5' })).toEqual(DEFAULTS)
  })

  it('page が未指定なら 1 になる', () => {
    expect(parseSearchParams({ q: 'react' })).toEqual({ ...DEFAULTS, keyword: 'react' })
  })

  it('page が上限を超えたら上限に丸められる代わりに 1 に正規化される（tryPageNumber の既定挙動）', () => {
    // MAX_PAGE を超える値は tryPageNumber が DEFAULT_PAGE (1) へ倒す
    expect(parseSearchParams({ page: '99999' })).toEqual(DEFAULTS)
  })

  it('sort をそのまま読み取り、不正値・未指定は relevance に正規化される', () => {
    expect(parseSearchParams({ sort: 'stars' })).toEqual({ ...DEFAULTS, sort: 'stars' })
    expect(parseSearchParams({ sort: 'updated' })).toEqual({ ...DEFAULTS, sort: 'updated' })
    expect(parseSearchParams({ sort: 'invalid' })).toEqual(DEFAULTS)
    expect(parseSearchParams({})).toEqual(DEFAULTS)
  })

  it('sort が配列で来たら先頭の値を採る', () => {
    expect(parseSearchParams({ sort: ['stars', 'updated'] })).toEqual({ ...DEFAULTS, sort: 'stars' })
  })

  it('per_page をそのまま読み取り、不正値・未指定は 20 に正規化される', () => {
    expect(parseSearchParams({ per_page: '50' })).toEqual({ ...DEFAULTS, perPage: 50 })
    expect(parseSearchParams({ per_page: '100' })).toEqual({ ...DEFAULTS, perPage: 100 })
    expect(parseSearchParams({ per_page: '30' })).toEqual(DEFAULTS)
    expect(parseSearchParams({ per_page: 'abc' })).toEqual(DEFAULTS)
  })

  it('per_page が配列で来たら先頭の値を採る', () => {
    expect(parseSearchParams({ per_page: ['50', '100'] })).toEqual({ ...DEFAULTS, perPage: 50 })
  })
})
