import { describe, expect, it } from 'vitest'

import { DomainValidationError } from '../errors'
import { MAX_KEYWORD_LENGTH, searchKeyword, trySearchKeyword } from './search-keyword'

describe('searchKeyword', () => {
  it('前後の空白を落として保持する', () => {
    expect(searchKeyword('  react  ')).toBe('react')
  })

  it('空文字・空白のみを拒否する', () => {
    expect(() => searchKeyword('   ')).toThrow(DomainValidationError)
  })

  it('長さ上限を超える値を拒否する', () => {
    expect(() => searchKeyword('a'.repeat(MAX_KEYWORD_LENGTH + 1))).toThrow(DomainValidationError)
  })
})

describe('trySearchKeyword', () => {
  it('不正値は null に倒す（URL 由来の値を 500 にしない）', () => {
    expect(trySearchKeyword('  ')).toBeNull()
    expect(trySearchKeyword(undefined)).toBeNull()
    expect(trySearchKeyword('react')).toBe('react')
  })
})
