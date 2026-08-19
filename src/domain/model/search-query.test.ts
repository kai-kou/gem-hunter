import { describe, expect, it } from 'vitest'

import { DomainValidationError } from '../errors'
import { DEFAULT_PAGE } from './page-number'
import { DEFAULT_PER_PAGE } from './per-page'
import { equalsSearchQuery, searchQuery } from './search-query'
import { DEFAULT_SORT_ORDER } from './sort-order'

describe('searchQuery', () => {
  it('キーワード・ページ・ソート・表示件数を値オブジェクトへ変換する', () => {
    const query = searchQuery({ keyword: '  react ', page: 3, sort: 'stars', perPage: 50 })

    expect(query.keyword).toBe('react')
    expect(query.page).toBe(3)
    expect(query.sort).toBe('stars')
    expect(query.perPage).toBe(50)
  })

  it('ページ・ソート・表示件数が未指定なら既定値になる', () => {
    const query = searchQuery({ keyword: 'react' })

    expect(query.page).toBe(DEFAULT_PAGE)
    expect(query.sort).toBe(DEFAULT_SORT_ORDER)
    expect(query.perPage).toBe(DEFAULT_PER_PAGE)
  })

  it('不正なキーワードは値オブジェクトの段階で落とす', () => {
    expect(() => searchQuery({ keyword: '' })).toThrow(DomainValidationError)
  })

  it('不正なソート順・表示件数は値オブジェクトの段階で落とす', () => {
    expect(() => searchQuery({ keyword: 'react', sort: 'forks' })).toThrow(DomainValidationError)
    expect(() => searchQuery({ keyword: 'react', perPage: 30 })).toThrow(DomainValidationError)
  })

  it('同じ値なら等価と判定する', () => {
    const a = searchQuery({ keyword: 'react', page: 2, sort: 'stars', perPage: 50 })

    expect(
      equalsSearchQuery(a, searchQuery({ keyword: 'react', page: 2, sort: 'stars', perPage: 50 })),
    ).toBe(true)
    expect(
      equalsSearchQuery(a, searchQuery({ keyword: 'vue', page: 2, sort: 'stars', perPage: 50 })),
    ).toBe(false)
    expect(
      equalsSearchQuery(
        a,
        searchQuery({ keyword: 'react', page: 2, sort: 'updated', perPage: 50 }),
      ),
    ).toBe(false)
    expect(
      equalsSearchQuery(a, searchQuery({ keyword: 'react', page: 2, sort: 'stars', perPage: 100 })),
    ).toBe(false)
  })
})
