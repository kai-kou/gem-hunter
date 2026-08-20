import { describe, expect, it } from 'vitest'

import { repositoryDetailDto, repositoryDto } from './dto'

/**
 * `html_url` の入力検証（NFR-19）。
 *
 * 🔴 この値は詳細画面のタイトルリンク（`src/ui/repository-detail.tsx`）で `href` に直結する。
 * `z.string()` のままだと `javascript:` のような擬似スキームを素通しするため、URL 形式と
 * https スキームを最上流で確定させる（多層防御）。実 GitHub API は常に `https://github.com/...`
 * を返すので、外れる応答は上流異常として倒す（fail-closed・`private` フィールドと同じ判断）。
 */
const validSearchItem = {
  id: 10270250,
  name: 'react',
  full_name: 'facebook/react',
  html_url: 'https://github.com/facebook/react',
  description: null,
  language: 'JavaScript',
  stargazers_count: 233000,
  updated_at: '2026-08-01T00:00:00Z',
  pushed_at: '2026-08-01T00:00:00Z',
  private: false,
  owner: { login: 'facebook', avatar_url: 'https://avatars.githubusercontent.com/u/69631?v=4' },
}

describe('html_url の検証', () => {
  it.each([
    ['javascript スキーム', 'javascript:alert(1)'],
    ['data スキーム', 'data:text/html,<script>alert(1)</script>'],
    ['平文 http', 'http://github.com/facebook/react'],
    ['URL ですらない文字列', 'not-a-url'],
  ])('%s の html_url は検索結果 DTO のパースで弾く', (_name, htmlUrl) => {
    expect(repositoryDto.safeParse({ ...validSearchItem, html_url: htmlUrl }).success).toBe(false)
  })

  it('https の GitHub URL は通る', () => {
    expect(repositoryDto.safeParse(validSearchItem).success).toBe(true)
  })

  it('詳細 DTO でも同じ検証が効く', () => {
    const detail = {
      ...validSearchItem,
      watchers_count: 6800,
      subscribers_count: 6800,
      forks_count: 48000,
      open_issues_count: 1100,
      topics: ['javascript'],
    }

    expect(repositoryDetailDto.safeParse(detail).success).toBe(true)
    expect(
      repositoryDetailDto.safeParse({ ...detail, html_url: 'javascript:alert(1)' }).success,
    ).toBe(false)
  })
})
