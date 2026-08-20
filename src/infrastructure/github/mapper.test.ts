import { describe, expect, it } from 'vitest'

import { UpstreamError } from '../../domain/errors'
import detailFixture from './__fixtures__/repository-detail.json'
import fixture from './__fixtures__/search-repositories.json'
import { toPublicRepositoryDetail, toSearchResult } from './mapper'

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
          private: false,
          topics: [],
          owner: { login: 'octostub', avatar_url: 'https://example.com/a.png' },
        },
      ],
    }

    const result = toSearchResult(raw)

    expect(result.items).toHaveLength(1)
    expect(result.items[0].lastPushedAt.toISOString()).toBe('2026-08-01T00:00:00.000Z')
  })

  it('private: true のアイテムを除外し、totalCount は API の値をそのまま保つ（is:public が効かなくなった場合の多層防御）', () => {
    // 🔴 total_count は items 件数と **一致しない値**（999）にする。
    //    items 件数と同じ値だと `totalCount: items.length` へ変異させてもテストが緑のままになり、
    //    「総件数はフィルタで書き換えない」という契約を検証できない。
    const raw = {
      total_count: 999,
      incomplete_results: false,
      items: [
        ...(fixture as { items: unknown[] }).items,
        {
          id: 4242,
          name: 'secret',
          full_name: 'acme/secret',
          html_url: 'https://github.com/acme/secret',
          description: null,
          language: null,
          stargazers_count: 0,
          updated_at: '2026-08-01T00:00:00Z',
          pushed_at: '2026-08-01T00:00:00Z',
          topics: [],
          private: true,
          owner: { login: 'acme', avatar_url: 'https://example.com/a.png' },
        },
      ],
    }

    const result = toSearchResult(raw)

    expect(result.items.map((item) => item.fullName)).not.toContain('acme/secret')
    // フィクスチャの 2 件（private: false）だけが残る
    expect(result.items).toHaveLength(2)
    // 🔴 totalCount は API の値をそのまま保つ（フィルタ後の件数で書き換えない）
    expect(result.totalCount).toBe(999)
  })

  it('private: false のアイテムは公開として扱う', () => {
    const raw = {
      total_count: 1,
      incomplete_results: false,
      items: [
        {
          id: 4243,
          name: 'open',
          full_name: 'acme/open',
          html_url: 'https://github.com/acme/open',
          description: null,
          language: null,
          stargazers_count: 0,
          updated_at: '2026-08-01T00:00:00Z',
          pushed_at: '2026-08-01T00:00:00Z',
          topics: [],
          private: false,
          owner: { login: 'acme', avatar_url: 'https://example.com/a.png' },
        },
      ],
    }

    expect(toSearchResult(raw).items).toHaveLength(1)
    expect(toSearchResult(fixture).items).toHaveLength(2)
  })

  it('private が欠落したアイテムは公開と推定せず UpstreamError にする（fail-closed）', () => {
    // 🔴 上流やプロキシが private を落としたときに「公開扱い」へ倒れると、NFR-33 の多層防御が
    //    黙って 1 層失われる。DTO を必須にして上流異常として検出する。
    const withoutPrivate: Record<string, unknown> = {
      ...(fixture as { items: Record<string, unknown>[] }).items[0],
    }
    delete withoutPrivate.private

    expect(() =>
      toSearchResult({ total_count: 1, incomplete_results: false, items: [withoutPrivate] }),
    ).toThrow(UpstreamError)
  })

  it('スキーマに合わない外部データをドメインエラーへ翻訳する', () => {
    // 上位層は zod を知らないため ZodError を層の外へ出さない（ACL の契約）
    expect(() => toSearchResult({ total_count: 'たくさん', items: [] })).toThrow(UpstreamError)
  })
})

describe('toPublicRepositoryDetail', () => {
  it('GitHub の詳細レスポンスをドメインモデルへ変換する', () => {
    const detail = toPublicRepositoryDetail(detailFixture)

    expect(detail?.fullName).toBe('facebook/react')
    expect(detail?.owner.login).toBe('facebook')
    expect(detail?.description).toBe('The library for web and native user interfaces.')
    expect(detail?.primaryLanguage).toBe('JavaScript')
    expect(detail?.forks).toBe(48000)
    expect(detail?.openIssues).toBe(1200)
    expect(detail?.topics).toEqual(['javascript', 'react'])
    expect(detail?.updatedAt.toISOString()).toBe('2026-08-18T00:00:00.000Z')
  })

  it('watchers は subscribers_count を使い、star のミラーである watchers_count は使わない', () => {
    // フィクスチャは watchers_count(=stargazers_count) と subscribers_count が別値（誤実装検出用）
    const detail = toPublicRepositoryDetail(detailFixture)

    expect(detail?.stars).toBe(233000)
    expect(detail?.watchers).toBe(6600)
    expect(detail?.watchers).not.toBe(detail?.stars)
  })

  it('private: true の詳細は null（＝見つからない）として返す（詳細 URL 直打ちを塞ぐ・AC-12）', () => {
    // 🔴 「公開に閉じる」判定を ACL に集約しているため、この 1 箇所を通せば呼び出し側は素通しでよい。
    expect(toPublicRepositoryDetail({ ...detailFixture, private: true })).toBeNull()
  })

  it('private が欠落した詳細は公開と推定せず UpstreamError にする（fail-closed）', () => {
    const withoutPrivate: Record<string, unknown> = {
      ...(detailFixture as Record<string, unknown>),
    }
    delete withoutPrivate.private

    expect(() => toPublicRepositoryDetail(withoutPrivate)).toThrow(UpstreamError)
  })

  it('スキーマに合わない外部データをドメインエラーへ翻訳する', () => {
    expect(() => toPublicRepositoryDetail({ id: 'not-a-number' })).toThrow(UpstreamError)
  })
})
