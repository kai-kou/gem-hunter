import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { RepositorySummary } from '../domain/model/repository'
import { RepositoryList } from './repository-list'

const items: RepositorySummary[] = [
  {
    id: 10270250,
    fullName: 'facebook/react',
    name: 'react',
    owner: { login: 'facebook', avatarUrl: 'https://avatars.githubusercontent.com/u/69631?v=4' },
    description: 'The library for web and native user interfaces.',
    primaryLanguage: 'JavaScript',
    stars: 233000,
    updatedAt: new Date('2026-08-18T09:00:00Z'),
    topics: ['javascript'],
    htmlUrl: 'https://github.com/facebook/react',
  },
]

describe('RepositoryList', () => {
  it('オーナーアイコンとリポジトリ名を表示する（AC-3）', () => {
    render(<RepositoryList items={items} />)

    expect(screen.getByRole('link', { name: /facebook\/react/ })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'facebook' })).toHaveAttribute(
      'src',
      expect.stringContaining('avatars.githubusercontent.com'),
    )
  })

  it('説明・主要言語・star 数・topics を表示する（AR-1）', () => {
    render(<RepositoryList items={items} />)

    expect(screen.getByText(/The library for web and native user interfaces\./)).toBeInTheDocument()
    expect(screen.getByText('JavaScript')).toBeInTheDocument()
    expect(screen.getByText('233,000')).toBeInTheDocument()
    expect(screen.getByText('javascript')).toBeInTheDocument()
  })

  it('結果ゼロ件のときは該当なしを伝える', () => {
    render(<RepositoryList items={[]} />)

    expect(screen.getByText(/見つかりませんでした/)).toBeInTheDocument()
  })
})
