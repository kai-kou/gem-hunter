import { describe, expect, it } from 'vitest'

import { InvalidSearchQueryError } from '../errors'
import { MAX_PAGE, SearchQuery } from './search-query'

describe('SearchQuery', () => {
  it('キーワードの前後の空白を落として保持する', () => {
    const query = SearchQuery.create({ keyword: '  react  ' })

    expect(query.keyword).toBe('react')
    expect(query.page).toBe(1)
  })

  it('ページ番号を指定できる', () => {
    expect(SearchQuery.create({ keyword: 'react', page: 3 }).page).toBe(3)
  })

  it('空文字・空白のみのキーワードを拒否する', () => {
    expect(() => SearchQuery.create({ keyword: '   ' })).toThrow(InvalidSearchQueryError)
  })

  it('256 文字を超えるキーワードを拒否する', () => {
    expect(() => SearchQuery.create({ keyword: 'a'.repeat(257) })).toThrow(InvalidSearchQueryError)
  })

  it('1 未満・上限超のページ番号を拒否する', () => {
    expect(() => SearchQuery.create({ keyword: 'react', page: 0 })).toThrow(InvalidSearchQueryError)
    expect(() => SearchQuery.create({ keyword: 'react', page: MAX_PAGE + 1 })).toThrow(
      InvalidSearchQueryError,
    )
  })

  it('整数でないページ番号を拒否する', () => {
    expect(() => SearchQuery.create({ keyword: 'react', page: 1.5 })).toThrow(
      InvalidSearchQueryError,
    )
  })

  it('同じ値なら等価と判定する', () => {
    const a = SearchQuery.create({ keyword: 'react', page: 2 })
    const b = SearchQuery.create({ keyword: 'react', page: 2 })

    expect(a.equals(b)).toBe(true)
    expect(a.equals(SearchQuery.create({ keyword: 'vue', page: 2 }))).toBe(false)
  })
})
