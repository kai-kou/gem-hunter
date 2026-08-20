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

  it('修飾子構文（名前:値）を含む入力を拒否する（クエリ修飾子インジェクション対策）', () => {
    for (const raw of [
      'react is:private',
      'user:kai-kou',
      '-is:public',
      'react -user:someone',
      'org:acme react',
      'fork:only',
      'react repo:acme/secret',
    ]) {
      expect(() => searchKeyword(raw), raw).toThrow(DomainValidationError)
    }
  })

  it('大文字のブール演算子（NOT / OR / AND）を含む入力を拒否する（末尾修飾子の否定・反転対策）', () => {
    for (const raw of ['react NOT', 'foo OR bar', 'foo AND bar', 'NOT react']) {
      expect(() => searchKeyword(raw), raw).toThrow(DomainValidationError)
    }
  })

  it('通常のキーワードは通す（過剰拒否の回帰防止）', () => {
    for (const raw of [
      'react',
      'next.js',
      'C# tutorial',
      '日本語 検索',
      'foo and bar',
      'cats not dogs',
      'a or b',
      'NOTABLE',
      'ORM',
      'ANDROID',
      '12:30 timer',
      'ラベル：値',
    ]) {
      expect(searchKeyword(raw), raw).toBe(raw)
    }
  })
})

describe('trySearchKeyword', () => {
  it('不正値は null に倒す（URL 由来の値を 500 にしない）', () => {
    expect(trySearchKeyword('  ')).toBeNull()
    expect(trySearchKeyword('react is:private')).toBeNull()
    expect(trySearchKeyword(undefined)).toBeNull()
    expect(trySearchKeyword('react')).toBe('react')
  })
})
