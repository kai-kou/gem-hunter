import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { locale } from '../domain/model/locale'
import type { RepositorySummary } from '../domain/model/repository'
import { RepositoryList } from './repository-list'

const labels = {
  empty: '条件に合うリポジトリは見つかりませんでした。キーワードを変えて試してください。',
  starCount: 'star 数',
  updatedAt: '最終更新',
}

const items: RepositorySummary[] = [
  {
    id: 10270250,
    fullName: 'facebook/react',
    name: 'react',
    owner: { login: 'facebook', avatarUrl: 'https://avatars.githubusercontent.com/u/69631?v=4' },
    description: 'The library for web and native user interfaces.',
    primaryLanguage: 'JavaScript',
    stars: 233000,
    lastPushedAt: new Date('2026-08-18T09:00:00Z'),
    topics: ['javascript'],
    htmlUrl: 'https://github.com/facebook/react',
  },
]

describe('RepositoryList', () => {
  it('オーナーアイコンとリポジトリ名を表示する（AC-3）', () => {
    render(<RepositoryList items={items} labels={labels} locale={locale('ja')} />)

    expect(screen.getByRole('link', { name: /facebook\/react/ })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'facebook' })).toHaveAttribute(
      'src',
      expect.stringContaining('avatars.githubusercontent.com'),
    )
  })

  it('カードは独立 URL の詳細ページへのリンクになっている（モーダルではない・AC-4）', () => {
    render(<RepositoryList items={items} labels={labels} locale={locale('ja')} />)

    expect(screen.getByRole('link', { name: /facebook\/react/ })).toHaveAttribute(
      'href',
      '/ja/repos/facebook/react',
    )
  })

  it('リポジトリ名にドットを含む場合も正しい href になる（例: user.github.io）', () => {
    const dotted: RepositorySummary[] = [
      {
        id: 1,
        fullName: 'octocat/octocat.github.io',
        name: 'octocat.github.io',
        owner: { login: 'octocat', avatarUrl: 'https://avatars.githubusercontent.com/u/1?v=4' },
        description: null,
        primaryLanguage: null,
        stars: 1,
        lastPushedAt: new Date('2026-08-18T09:00:00Z'),
        topics: [],
        htmlUrl: 'https://github.com/octocat/octocat.github.io',
      },
    ]

    render(<RepositoryList items={dotted} labels={labels} locale={locale('ja')} />)

    expect(screen.getByRole('link', { name: /octocat\/octocat\.github\.io/ })).toHaveAttribute(
      'href',
      '/ja/repos/octocat/octocat.github.io',
    )
  })

  it('説明・主要言語・star 数・topics を表示する（AR-1）', () => {
    render(<RepositoryList items={items} labels={labels} locale={locale('ja')} />)

    expect(screen.getByText(/The library for web and native user interfaces\./)).toBeInTheDocument()
    expect(screen.getByText('JavaScript')).toBeInTheDocument()
    expect(screen.getByText('233,000')).toBeInTheDocument()
    expect(screen.getByText('javascript')).toBeInTheDocument()
  })

  it('結果ゼロ件のときは該当なしを伝える', () => {
    render(<RepositoryList items={[]} labels={labels} locale={locale('ja')} />)

    expect(screen.getByText(/見つかりませんでした/)).toBeInTheDocument()
  })

  it('labels props から star 数・最終更新のラベル文言が反映される（E-4）', () => {
    render(
      <RepositoryList
        items={items}
        labels={{ empty: 'No repositories matched.', starCount: 'stars', updatedAt: 'Updated' }}
        locale={locale('en')}
      />,
    )

    expect(screen.getByText('stars', { exact: false })).toBeInTheDocument()
    expect(screen.getByText(/Updated/)).toBeInTheDocument()
  })

  it('ja ロケールでは星数・更新日を日本式書式（YYYY/MM/DD）で表示する（🔴 CRITICAL 修正）', () => {
    render(<RepositoryList items={items} labels={labels} locale={locale('ja')} />)

    expect(screen.getByText('233,000')).toBeInTheDocument()
    expect(screen.getByText(/2026\/08\/18/)).toBeInTheDocument()
  })

  it('en ロケールでは英語ラベルと英語式日付（MM/DD/YYYY）が両方揃って表示される（🔴 CRITICAL 修正）', () => {
    render(
      <RepositoryList
        items={items}
        labels={{ empty: 'No repositories matched.', starCount: 'stars', updatedAt: 'Updated' }}
        locale={locale('en')}
      />,
    )

    expect(screen.getByText('233,000')).toBeInTheDocument()
    expect(screen.getByText(/08\/18\/2026/)).toBeInTheDocument()
    expect(screen.getByText(/Updated/)).toBeInTheDocument()
  })
})
