import { describe, expect, it } from 'vitest'
import { resolveLocalizedPath } from './resolve-locale-path'

describe('resolveLocalizedPath', () => {
  it('ルートは既定ロケール（ja）配下へマッピングする', () => {
    expect(resolveLocalizedPath('/')).toBe('/ja')
  })

  it('ロケール未指定のパスは既定ロケールを前置する', () => {
    expect(resolveLocalizedPath('/about')).toBe('/ja/about')
  })

  it('既に ja を含むパスはリダイレクト不要（null）', () => {
    expect(resolveLocalizedPath('/ja')).toBeNull()
    expect(resolveLocalizedPath('/ja/about')).toBeNull()
  })

  it('既に en を含むパスはリダイレクト不要（null）', () => {
    expect(resolveLocalizedPath('/en')).toBeNull()
    expect(resolveLocalizedPath('/en/about')).toBeNull()
  })

  it('ロケール名を接頭辞に持つが区切りが無い別セグメントは誤判定しない', () => {
    expect(resolveLocalizedPath('/january')).toBe('/ja/january')
  })
})
