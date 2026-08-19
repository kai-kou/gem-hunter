import { describe, expect, it } from 'vitest'

import { locale } from '@/src/domain/model/locale'
import { toIntlLocaleTag } from './intl-locale-tag'

describe('toIntlLocaleTag', () => {
  it('ja は ja-JP へ変換する', () => {
    expect(toIntlLocaleTag(locale('ja'))).toBe('ja-JP')
  })

  it('en は en-US へ変換する', () => {
    expect(toIntlLocaleTag(locale('en'))).toBe('en-US')
  })
})
