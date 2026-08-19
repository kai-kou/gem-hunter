import { describe, expect, it } from 'vitest'

import { DomainValidationError } from '../errors'
import { DEFAULT_SORT_ORDER, parse, tryParse } from './sort-order'

describe('parse', () => {
  it('relevance / stars / updated を受け入れる', () => {
    expect(parse('relevance')).toBe('relevance')
    expect(parse('stars')).toBe('stars')
    expect(parse('updated')).toBe('updated')
  })

  it('許可されていない値を拒否する', () => {
    expect(() => parse('forks')).toThrow(DomainValidationError)
    expect(() => parse('')).toThrow(DomainValidationError)
  })
})

describe('tryParse', () => {
  it('不正値・未指定は既定並び順へ倒す', () => {
    expect(tryParse('forks')).toBe(DEFAULT_SORT_ORDER)
    expect(tryParse(null)).toBe(DEFAULT_SORT_ORDER)
    expect(tryParse(undefined)).toBe(DEFAULT_SORT_ORDER)
    expect(tryParse('')).toBe(DEFAULT_SORT_ORDER)
    expect(tryParse('stars')).toBe('stars')
  })
})
