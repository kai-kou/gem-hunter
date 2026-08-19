import { describe, expect, it } from 'vitest'

import { localeRedirectExclusionPattern } from './locale-redirect'

const LOCALES = ['ja', 'en'] as const

/**
 * `next.config.ts` の `redirects()` `source` に渡る正規表現の実挙動を、
 * 実際に `RegExp` で評価して検証する（`:path(...)` が捕捉する「先頭の `/` を除いた文字列」を渡す）。
 */
function isRedirectTarget(pathWithoutLeadingSlash: string): boolean {
  const pattern = new RegExp(`^${localeRedirectExclusionPattern(LOCALES)}$`)
  return pattern.test(pathWithoutLeadingSlash)
}

describe('localeRedirectExclusionPattern', () => {
  it('ロケール接頭辞パス（/ja, /en/foo）はリダイレクト対象外', () => {
    expect(isRedirectTarget('ja')).toBe(false)
    expect(isRedirectTarget('en/foo')).toBe(false)
  })

  it('api・_next 配下はリダイレクト対象外', () => {
    expect(isRedirectTarget('api/x')).toBe(false)
    expect(isRedirectTarget('_next/static/a.js')).toBe(false)
  })

  it('末尾セグメントが静的ファイル拡張子のパスはリダイレクト対象外', () => {
    expect(isRedirectTarget('favicon.ico')).toBe(false)
  })

  it('ロケール接頭辞に似ているだけの非ロケールパスはリダイレクト対象', () => {
    expect(isRedirectTarget('january')).toBe(true)
  })

  it('パス途中にドットを含むが拡張子ではない（GitHub リポジトリ名等）パスはリダイレクト対象', () => {
    expect(isRedirectTarget('repos/foo/user.github.io')).toBe(true)
  })

  it('通常のアプリ内パスはリダイレクト対象', () => {
    expect(isRedirectTarget('repos/facebook/react')).toBe(true)
  })
})
