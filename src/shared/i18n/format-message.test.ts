import { describe, expect, it } from 'vitest'

import { formatMessage } from './format-message'

describe('formatMessage', () => {
  it('{key} プレースホルダーを値で置き換える', () => {
    expect(formatMessage('{total} 件中 {shown} 件', { total: '10', shown: '3' })).toBe(
      '10 件中 3 件',
    )
  })

  it('未知のプレースホルダーはそのまま残す', () => {
    expect(formatMessage('{unknown} です', {})).toBe('{unknown} です')
  })

  it('プレースホルダーを含まないテンプレートはそのまま返す', () => {
    expect(formatMessage('固定文言', { message: 'x' })).toBe('固定文言')
  })

  it('値に $& を含んでいても特殊置換パターンとして展開されない（String.replace の罠を回避）', () => {
    expect(formatMessage('検索できませんでした: {message}', { message: '$&' })).toBe(
      '検索できませんでした: $&',
    )
  })

  it('値に $$ を含んでいても特殊置換パターンとして展開されない', () => {
    expect(formatMessage('検索できませんでした: {message}', { message: '$$' })).toBe(
      '検索できませんでした: $$',
    )
  })

  it('値に $1 のようなグループ参照風の文字列を含んでいても素通しする', () => {
    expect(formatMessage('検索できませんでした: {message}', { message: '$1 not found' })).toBe(
      '検索できませんでした: $1 not found',
    )
  })
})
