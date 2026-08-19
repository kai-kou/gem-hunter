import { describe, expect, it } from 'vitest'

import { UpstreamError } from '../../domain/errors'
import detailFixture from './__fixtures__/repository-detail.json'
import fixture from './__fixtures__/search-repositories.json'
import { toRepositoryDetail, toSearchResult } from './mapper'

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
    // 🔴 lastPushedAt は pushed_at 由来（フィクスチャの updated_at とは異なる値で区別する・domain-model.md §2.2）
    expect(react.lastPushedAt.toISOString()).toBe('2026-08-15T03:00:00.000Z')
    expect(react.topics).toEqual(['javascript', 'react'])
  })

  it('description・language の null を欠損として扱う', () => {
    const [, routerRepo] = toSearchResult(fixture).items

    expect(routerRepo.description).toBeNull()
    expect(routerRepo.primaryLanguage).toBeNull()
    expect(routerRepo.topics).toEqual([])
  })

  it('pushed_at が null（コミット履歴のない空リポジトリ）でも例外を投げず updated_at にフォールバックする', () => {
    // GitHub API の repository スキーマでは pushed_at は nullable（空リポジトリで null になりうる）。
    // 検索結果 30 件中 1 件でも null が混ざると zod パース全体が失敗しないことを検証する。
    const raw = {
      total_count: 1,
      incomplete_results: false,
      items: [
        {
          id: 999,
          name: 'empty-repo',
          full_name: 'octostub/empty-repo',
          html_url: 'https://github.com/octostub/empty-repo',
          description: null,
          language: null,
          stargazers_count: 0,
          updated_at: '2026-08-01T00:00:00Z',
          pushed_at: null,
          topics: [],
          owner: { login: 'octostub', avatar_url: 'https://example.com/a.png' },
        },
      ],
    }

    const result = toSearchResult(raw)

    expect(result.items).toHaveLength(1)
    expect(result.items[0].lastPushedAt.toISOString()).toBe('2026-08-01T00:00:00.000Z')
  })

  it('スキーマに合わない外部データをドメインエラーへ翻訳する', () => {
    // 上位層は zod を知らないため ZodError を層の外へ出さない（ACL の契約）
    expect(() => toSearchResult({ total_count: 'たくさん', items: [] })).toThrow(UpstreamError)
  })
})

describe('toRepositoryDetail', () => {
  it('GitHub の詳細レスポンスをドメインモデルへ変換する', () => {
    const detail = toRepositoryDetail(detailFixture)

    expect(detail.fullName).toBe('facebook/react')
    expect(detail.owner.login).toBe('facebook')
    expect(detail.description).toBe('The library for web and native user interfaces.')
    expect(detail.primaryLanguage).toBe('JavaScript')
    expect(detail.forks).toBe(48000)
    expect(detail.openIssues).toBe(1200)
    expect(detail.topics).toEqual(['javascript', 'react'])
    expect(detail.updatedAt.toISOString()).toBe('2026-08-18T00:00:00.000Z')
  })

  it('watchers は subscribers_count を使い、star のミラーである watchers_count は使わない', () => {
    // フィクスチャは watchers_count(=stargazers_count) と subscribers_count が別値（誤実装検出用）
    const detail = toRepositoryDetail(detailFixture)

    expect(detail.stars).toBe(233000)
    expect(detail.watchers).toBe(6600)
    expect(detail.watchers).not.toBe(detail.stars)
  })

  it('スキーマに合わない外部データをドメインエラーへ翻訳する', () => {
    expect(() => toRepositoryDetail({ id: 'not-a-number' })).toThrow(UpstreamError)
  })
})
