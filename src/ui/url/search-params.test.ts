import { describe, expect, it } from 'vitest'

import {
  GEM_LIST_SOURCE_PARAM_KEY,
  GEM_LIST_SOURCE_PARAM_VALUE,
  SEARCH_PARAM_KEYS,
  parseSearchParams,
  rawKeywordOf,
} from './search-params'

describe('SEARCH_PARAM_KEYS', () => {
  it('keyword は q、page は page、sort は sort、perPage は per_page、badged は badged に固定されている', () => {
    expect(SEARCH_PARAM_KEYS).toEqual({
      keyword: 'q',
      page: 'page',
      sort: 'sort',
      perPage: 'per_page',
      badged: 'badged',
    })
  })
})

/**
 * 🔴 URL 契約（外部に共有・ブックマークされる）の正本は本ファイル。表示コンポーネント側に
 * 名前を持たせない（`prd.md` §2.4.1 が仕様の正本）。
 */
describe('Gem 一覧の出所マーカー', () => {
  it('from=gems に固定されている', () => {
    expect(GEM_LIST_SOURCE_PARAM_KEY).toBe('from')
    expect(GEM_LIST_SOURCE_PARAM_VALUE).toBe('gems')
  })

  it('検索 4 条件のキーと衝突しない', () => {
    expect(Object.values(SEARCH_PARAM_KEYS)).not.toContain(GEM_LIST_SOURCE_PARAM_KEY)
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
    expect(parseSearchParams({ sort: ['stars', 'updated'] })).toEqual({
      ...DEFAULTS,
      sort: 'stars',
    })
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

describe('rawKeywordOf', () => {
  it('妥当性判定をせずに生の値を返す（未入力とエラーを画面で区別するため）', () => {
    // parseSearchParams は不正値を '' へ倒すが、こちらは倒さない
    expect(parseSearchParams({ q: 'react is:private' }).keyword).toBe('')
    expect(rawKeywordOf({ q: 'react is:private' })).toBe('react is:private')
  })

  it('未指定は空文字・配列は先頭の値を採る', () => {
    expect(rawKeywordOf({})).toBe('')
    expect(rawKeywordOf({ q: ['react', 'vue'] })).toBe('react')
  })
})
