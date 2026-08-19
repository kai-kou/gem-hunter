import { describe, expect, it } from 'vitest'

import { DomainValidationError } from '../errors'
import { DEFAULT_PAGE } from './page-number'
import { equalsSearchQuery, searchQuery } from './search-query'

describe('searchQuery', () => {
  it('キーワードとページを値オブジェクトへ変換する', () => {
    const query = searchQuery({ keyword: '  react ', page: 3 })

    expect(query.keyword).toBe('react')
    expect(query.page).toBe(3)
  })

  it('ページ未指定なら既定ページになる', () => {
    expect(searchQuery({ keyword: 'react' }).page).toBe(DEFAULT_PAGE)
  })

  it('不正なキーワードは値オブジェクトの段階で落とす', () => {
    expect(() => searchQuery({ keyword: '' })).toThrow(DomainValidationError)
  })

  it('同じ値なら等価と判定する', () => {
    const a = searchQuery({ keyword: 'react', page: 2 })

    expect(equalsSearchQuery(a, searchQuery({ keyword: 'react', page: 2 }))).toBe(true)
    expect(equalsSearchQuery(a, searchQuery({ keyword: 'vue', page: 2 }))).toBe(false)
  })
})
