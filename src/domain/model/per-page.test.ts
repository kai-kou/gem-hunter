import { describe, expect, it } from 'vitest'

import { DomainValidationError } from '../errors'
import { DEFAULT_PER_PAGE, parse, tryParse } from './per-page'

describe('parse', () => {
  it('20 / 50 / 100 を受け入れる', () => {
    expect(parse(20)).toBe(20)
    expect(parse(50)).toBe(50)
    expect(parse(100)).toBe(100)
  })

  it('許可されていない値を拒否する', () => {
    expect(() => parse(30)).toThrow(DomainValidationError)
    expect(() => parse(0)).toThrow(DomainValidationError)
    expect(() => parse(1000)).toThrow(DomainValidationError)
  })
})

describe('tryParse', () => {
  it('不正値・未指定は既定表示件数へ倒す', () => {
    expect(tryParse('abc')).toBe(DEFAULT_PER_PAGE)
    expect(tryParse(null)).toBe(DEFAULT_PER_PAGE)
    expect(tryParse(undefined)).toBe(DEFAULT_PER_PAGE)
    expect(tryParse('30')).toBe(DEFAULT_PER_PAGE)
    expect(tryParse('50')).toBe(50)
    expect(tryParse(100)).toBe(100)
  })
})
