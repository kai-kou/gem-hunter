import { describe, expect, it } from 'vitest'

import { DomainValidationError } from '../errors'
import { DEFAULT_LOCALE, LOCALES, isLocale, locale, tryLocale } from './locale'

describe('LOCALES / DEFAULT_LOCALE', () => {
  it('ja / en のみをサポートし、既定は ja', () => {
    expect(LOCALES).toEqual(['ja', 'en'])
    expect(DEFAULT_LOCALE).toBe('ja')
  })
})

describe('isLocale', () => {
  it('サポート対象のロケールを判定する', () => {
    expect(isLocale('ja')).toBe(true)
    expect(isLocale('en')).toBe(true)
    expect(isLocale('fr')).toBe(false)
    expect(isLocale('')).toBe(false)
  })
})

describe('locale', () => {
  it('ja / en を受け入れる', () => {
    expect(locale('ja')).toBe('ja')
    expect(locale('en')).toBe('en')
  })

  it('サポート外の値を拒否する', () => {
    expect(() => locale('fr')).toThrow(DomainValidationError)
    expect(() => locale('')).toThrow(DomainValidationError)
  })
})

describe('tryLocale', () => {
  it('不正値・未指定は既定ロケールへ倒す（domain-model.md §4）', () => {
    expect(tryLocale('fr')).toBe(DEFAULT_LOCALE)
    expect(tryLocale('')).toBe(DEFAULT_LOCALE)
    expect(tryLocale(undefined)).toBe(DEFAULT_LOCALE)
    expect(tryLocale(null)).toBe(DEFAULT_LOCALE)
  })

  it('正しい値はそのまま返す', () => {
    expect(tryLocale('en')).toBe('en')
  })
})
