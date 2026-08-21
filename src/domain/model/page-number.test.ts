import { describe, expect, it } from 'vitest'

import { DomainValidationError } from '../errors'
import { API_RESULT_LIMIT, DEFAULT_PAGE, MAX_PAGE, pageNumber, tryPageNumber } from './page-number'

describe('pageNumber', () => {
  it('範囲内の整数を受け入れる', () => {
    expect(pageNumber(1)).toBe(1)
    expect(pageNumber(MAX_PAGE)).toBe(MAX_PAGE)
  })

  it('範囲外・非整数を拒否する', () => {
    expect(() => pageNumber(0)).toThrow(DomainValidationError)
    expect(() => pageNumber(MAX_PAGE + 1)).toThrow(DomainValidationError)
    expect(() => pageNumber(1.5)).toThrow(DomainValidationError)
  })
})

describe('tryPageNumber', () => {
  it('不正値・未指定は既定ページへ倒す', () => {
    expect(tryPageNumber('abc')).toBe(DEFAULT_PAGE)
    expect(tryPageNumber(null)).toBe(DEFAULT_PAGE)
    expect(tryPageNumber('0')).toBe(DEFAULT_PAGE)
    expect(tryPageNumber('3')).toBe(3)
  })
})

describe('API_RESULT_LIMIT', () => {
  // GitHub 検索 API の「1,000 件上限」を単一の定義元にする。
  it('1,000 件として export されている（MAX_PAGE の算出元と一致する）', () => {
    expect(API_RESULT_LIMIT).toBe(1000)
    expect(MAX_PAGE).toBe(Math.floor(API_RESULT_LIMIT / 20))
  })
})
