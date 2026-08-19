import { describe, expect, it } from 'vitest'

import { SEARCH_PARAM_KEYS, parseSearchParams } from './search-params'

describe('SEARCH_PARAM_KEYS', () => {
  it('keyword は q、page は page に固定されている', () => {
    expect(SEARCH_PARAM_KEYS).toEqual({ keyword: 'q', page: 'page' })
  })
})

describe('parseSearchParams', () => {
  it('q と page をそのまま読み取る', () => {
    expect(parseSearchParams({ q: 'react', page: '2' })).toEqual({ keyword: 'react', page: 2 })
  })

  it('q が未指定なら keyword は空文字になる', () => {
    expect(parseSearchParams({})).toEqual({ keyword: '', page: 1 })
  })

  it('q が前後空白付きならトリムされる（trySearchKeyword に委譲）', () => {
    expect(parseSearchParams({ q: '  react  ' })).toEqual({ keyword: 'react', page: 1 })
  })

  it('q が空白のみなら空文字に正規化される（trySearchKeyword が null を返す）', () => {
    expect(parseSearchParams({ q: '   ' })).toEqual({ keyword: '', page: 1 })
  })

  it('q が配列で来たら先頭の値を採る', () => {
    expect(parseSearchParams({ q: ['first', 'second'] })).toEqual({ keyword: 'first', page: 1 })
  })

  it('page が配列で来たら先頭の値を採る', () => {
    expect(parseSearchParams({ page: ['3', '4'] })).toEqual({ keyword: '', page: 3 })
  })

  it('page が数値でない文字列なら 1 に正規化される（tryPageNumber に委譲）', () => {
    expect(parseSearchParams({ page: 'abc' })).toEqual({ keyword: '', page: 1 })
  })

  it('page が 0 以下なら 1 に正規化される', () => {
    expect(parseSearchParams({ page: '0' })).toEqual({ keyword: '', page: 1 })
    expect(parseSearchParams({ page: '-5' })).toEqual({ keyword: '', page: 1 })
  })

  it('page が未指定なら 1 になる', () => {
    expect(parseSearchParams({ q: 'react' })).toEqual({ keyword: 'react', page: 1 })
  })

  it('page が上限を超えたら上限に丸められる代わりに 1 に正規化される（tryPageNumber の既定挙動）', () => {
    // MAX_PAGE を超える値は tryPageNumber が DEFAULT_PAGE (1) へ倒す
    expect(parseSearchParams({ page: '99999' })).toEqual({ keyword: '', page: 1 })
  })
})
