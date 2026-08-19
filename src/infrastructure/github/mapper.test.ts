import { describe, expect, it } from 'vitest'

import { UpstreamError } from '../../domain/errors'
import fixture from './__fixtures__/search-repositories.json'
import { toSearchResult } from './mapper'

describe('toSearchResult', () => {
  it('GitHub の検索レスポンスをドメインモデルへ変換する', () => {
    const result = toSearchResult(fixture)

    expect(result.totalCount).toBe(2)
    expect(result.incompleteResults).toBe(false)
    expect(result.items).toHaveLength(2)

    const [react] = result.items
    expect(react.fullName).toBe('facebook/react')
    expect(react.owner.login).toBe('facebook')
    expect(react.owner.avatarUrl).toBe('https://avatars.githubusercontent.com/u/69631?v=4')
    expect(react.stars).toBe(233000)
    expect(react.primaryLanguage).toBe('JavaScript')
    expect(react.updatedAt.toISOString()).toBe('2026-08-18T09:00:00.000Z')
    expect(react.topics).toEqual(['javascript', 'react'])
  })

  it('description・language の null を欠損として扱う', () => {
    const [, routerRepo] = toSearchResult(fixture).items

    expect(routerRepo.description).toBeNull()
    expect(routerRepo.primaryLanguage).toBeNull()
    expect(routerRepo.topics).toEqual([])
  })

  it('スキーマに合わない外部データをドメインエラーへ翻訳する', () => {
    // 上位層は zod を知らないため ZodError を層の外へ出さない（ACL の契約）
    expect(() => toSearchResult({ total_count: 'たくさん', items: [] })).toThrow(UpstreamError)
  })
})
