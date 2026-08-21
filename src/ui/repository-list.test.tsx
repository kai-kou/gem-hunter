import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { gemIndex } from '../domain/model/gem-index'
import { locale } from '../domain/model/locale'
import type { RepositorySummary } from '../domain/model/repository'
import { RepositoryList } from './repository-list'

const labels = {
  empty: '条件に合うリポジトリは見つかりませんでした。キーワードを変えて試してください。',
  starCount: 'star 数',
  updatedAt: '最終更新',
  dependentLabel: '被依存数',
  gemIndexLabel: 'Gem Index',
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
    const { container } = render(<RepositoryList items={items} labels={labels} locale={locale('ja')} />)

    expect(screen.getByRole('link', { name: /facebook\/react/ })).toBeInTheDocument()
    // オーナー名は fullName としてカード内にテキスト隣接表示されるため alt="" にしており、
    // 装飾画像扱い（role=presentation）になる（ui-ux-guidelines §7.4）→ getByRole('img') は使えない
    const img = container.querySelector('img')
    expect(img).toHaveAttribute('src', expect.stringContaining('avatars.githubusercontent.com'))
    expect(img).toHaveAttribute('alt', '')
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

  it('searchState を渡すと詳細リンクへ検索条件がクエリとして継ぎ足される（SP-7・詳細→戻る用）', () => {
    render(
      <RepositoryList
        items={items}
        labels={labels}
        locale={locale('ja')}
        searchState={{ keyword: 'react', page: 2, sort: 'stars', perPage: 50 }}
      />,
    )

    const href = screen.getByRole('link', { name: /facebook\/react/ }).getAttribute('href') ?? ''
    const [path, qs] = href.split('?')
    const params = new URLSearchParams(qs)

    expect(path).toBe('/ja/repos/facebook/react')
    expect(params.get('q')).toBe('react')
    expect(params.get('page')).toBe('2')
    expect(params.get('sort')).toBe('stars')
    expect(params.get('per_page')).toBe('50')
  })

  it('searchState を渡さない場合は既存どおりクエリなしのリンクになる（後方互換）', () => {
    render(<RepositoryList items={items} labels={labels} locale={locale('ja')} />)

    expect(screen.getByRole('link', { name: /facebook\/react/ })).toHaveAttribute(
      'href',
      '/ja/repos/facebook/react',
    )
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

  it('0 件のときは role="status" で支援技術にも伝える（US-23 / US-26 / NFR-12）', () => {
    render(<RepositoryList items={[]} labels={labels} locale={locale('ja')} />)

    expect(screen.getByRole('status')).toHaveTextContent(labels.empty)
  })

  it('gemIndex を持つ結果は被依存数・star・Gem Index の 3 数値を並置する（SP-16・操作レビュー手順3）', () => {
    const withGemIndex: RepositorySummary[] = [
      {
        ...items[0],
        gemIndex: gemIndex(-1.234),
        dependentCount: 42,
      },
    ]

    render(<RepositoryList items={withGemIndex} labels={labels} locale={locale('ja')} />)

    // daily-digest.test.tsx と同じ作法（ラベル + 数値が別テキストノードに分かれるため正規表現で拾う）。
    expect(screen.getByText(/42/)).toBeInTheDocument()
    expect(screen.getByText('233,000')).toBeInTheDocument()
    expect(screen.getByText(/-1\.234/)).toBeInTheDocument()
    expect(screen.getByText(new RegExp(labels.dependentLabel))).toBeInTheDocument()
    expect(screen.getByText(new RegExp(labels.gemIndexLabel))).toBeInTheDocument()
  })

  it('gemIndex を持たない結果は 3 数値バッジを出さない（候補プール外・既存表示のまま）', () => {
    render(<RepositoryList items={items} labels={labels} locale={locale('ja')} />)

    expect(screen.queryByText(labels.dependentLabel, { exact: false })).not.toBeInTheDocument()
    expect(screen.queryByText(labels.gemIndexLabel, { exact: false })).not.toBeInTheDocument()
  })
})
