import { describe, expect, it } from 'vitest'

import { DomainValidationError } from '../errors'
import { parse, toYyyymmdd, tryParse } from './date-seed'

describe('parse', () => {
  it('YYYYMMDD 形式で実在する UTC 日付を受け入れる', () => {
    expect(parse('20260820')).toBe('20260820')
    expect(parse('20240229')).toBe('20240229') // うるう年
    expect(parse('20000229')).toBe('20000229') // 400 年ルール（うるう年）
    expect(parse('20261231')).toBe('20261231')
  })

  it('存在しない日付は DomainValidationError', () => {
    expect(() => parse('20260231')).toThrow(DomainValidationError) // 2月31日
    expect(() => parse('20260230')).toThrow(DomainValidationError)
    expect(() => parse('20260431')).toThrow(DomainValidationError) // 4月31日
    expect(() => parse('20230229')).toThrow(DomainValidationError) // 平年の2月29日
    expect(() => parse('19000229')).toThrow(DomainValidationError) // 100 年ルール（平年）
    expect(() => parse('20261301')).toThrow(DomainValidationError) // 13月
    expect(() => parse('20260001')).toThrow(DomainValidationError) // 0月
    expect(() => parse('20260800')).toThrow(DomainValidationError) // 0日
  })

  it('形式不一致（区切り・桁数・非数字・空）は DomainValidationError', () => {
    expect(() => parse('2026-08-20')).toThrow(DomainValidationError)
    expect(() => parse('2026/08/20')).toThrow(DomainValidationError)
    expect(() => parse('202608')).toThrow(DomainValidationError)
    expect(() => parse('202608200')).toThrow(DomainValidationError)
    expect(() => parse('abcdefgh')).toThrow(DomainValidationError)
    expect(() => parse('')).toThrow(DomainValidationError)
    expect(() => parse(' 20260820')).toThrow(DomainValidationError)
    expect(() => parse('20260820 ')).toThrow(DomainValidationError)
  })
})

describe('tryParse', () => {
  const now = new Date('2026-08-20T00:00:00Z')

  it('null / undefined / 空文字は当日（UTC）へフォールバック', () => {
    expect(tryParse(null, now)).toBe('20260820')
    expect(tryParse(undefined, now)).toBe('20260820')
    expect(tryParse('', now)).toBe('20260820')
  })

  it('不正値も当日（UTC）へフォールバック（ADR 0014 §2.2）', () => {
    expect(tryParse('2026-08-20', now)).toBe('20260820')
    expect(tryParse('20260231', now)).toBe('20260820')
    expect(tryParse('abc', now)).toBe('20260820')
    expect(tryParse('999', now)).toBe('20260820')
  })

  it('正常値はそのまま採用する', () => {
    expect(tryParse('20250101', now)).toBe('20250101')
    expect(tryParse('20261231', now)).toBe('20261231')
  })
})

describe('toYyyymmdd', () => {
  it('UTC 日付を YYYYMMDD に落とす（0 埋め 8 桁）', () => {
    expect(toYyyymmdd(new Date('2026-08-20T00:00:00Z'))).toBe('20260820')
    expect(toYyyymmdd(new Date('2026-01-05T23:59:59Z'))).toBe('20260105')
    expect(toYyyymmdd(new Date('2026-12-31T12:00:00Z'))).toBe('20261231')
  })

  it('UTC 前提で計算する（JST 15:00Z は UTC ではまだ当日）', () => {
    // 2026-08-20T15:00:00Z は JST では 2026-08-21 00:00 だが UTC では 2026-08-20
    expect(toYyyymmdd(new Date('2026-08-20T15:00:00Z'))).toBe('20260820')
  })

  it('parse で受理できる形式を返す（往復可能）', () => {
    const seed = toYyyymmdd(new Date('2026-08-20T00:00:00Z'))
    expect(parse(seed)).toBe(seed)
  })
})
