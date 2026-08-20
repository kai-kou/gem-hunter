import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { locale } from '../domain/model/locale'
import type { RepositoryDetail as RepositoryDetailModel } from '../domain/model/repository'
import { RepositoryDetail } from './repository-detail'

const labels = {
  backLink: '一覧へ戻る',
  language: '主要言語',
  starCount: 'star 数',
  watcherCount: 'watcher 数',
  forkCount: 'fork 数',
  openIssueCount: 'issue 数',
}

const repository: RepositoryDetailModel = {
  id: 10270250,
  name: 'react',
  fullName: 'facebook/react',
  owner: { login: 'facebook', avatarUrl: 'https://avatars.githubusercontent.com/u/69631?v=4' },
  description: 'The library for web and native user interfaces.',
  primaryLanguage: 'JavaScript',
  stars: 233000,
  watcherCount: 6800,
  forkCount: 48000,
  openIssueCount: 1100,
  topics: ['javascript'],
  htmlUrl: 'https://github.com/facebook/react',
}

describe('RepositoryDetail', () => {
  it('リポジトリ名・オーナーアイコン・言語・4 つの統計値を表示する（AC-5）', () => {
    const { container } = render(
      <RepositoryDetail repository={repository} labels={labels} locale={locale('ja')} />,
    )

    expect(screen.getByRole('heading', { level: 1, name: 'facebook/react' })).toBeInTheDocument()
    // オーナー名が fullName としてテキスト隣接表示されるため alt="" にしており、
    // 装飾画像扱い（role=presentation）になる（ui-ux-guidelines §7.4）→ getByRole('img') は使えない
    expect(container.querySelector('img')).toHaveAttribute(
      'src',
      expect.stringContaining('avatars.githubusercontent.com'),
    )
    expect(screen.getByText('JavaScript')).toBeInTheDocument()
    expect(screen.getByText('233,000')).toBeInTheDocument()
    expect(screen.getByText('6,800')).toBeInTheDocument()
    expect(screen.getByText('48,000')).toBeInTheDocument()
    expect(screen.getByText('1,100')).toBeInTheDocument()
  })

  it('Star 数と Watcher 数が別の値として表示される（watchers_count 誤用防止・AC-5）', () => {
    render(<RepositoryDetail repository={repository} labels={labels} locale={locale('ja')} />)

    // dl/dt/dd は ARIA の term/definition ロールを持つため、ラベル（dt）から
    // 対応する値（dd）を辿ることで「正しいラベルの下に正しい数値がある」ことを検証する。
    const starTerm = screen.getByText(labels.starCount).closest('dt')
    const watcherTerm = screen.getByText(labels.watcherCount).closest('dt')
    const starValue = starTerm?.nextElementSibling
    const watcherValue = watcherTerm?.nextElementSibling

    expect(starValue).toHaveTextContent('233,000')
    expect(watcherValue).toHaveTextContent('6,800')
    expect(starValue).not.toBeNull()
    expect(starValue?.textContent).not.toBe(watcherValue?.textContent)
  })

  it('統計値は項目名（label）と数値（value）の対で表示される', () => {
    render(<RepositoryDetail repository={repository} labels={labels} locale={locale('ja')} />)

    expect(screen.getByText(labels.starCount)).toBeInTheDocument()
    expect(screen.getByText(labels.watcherCount)).toBeInTheDocument()
    expect(screen.getByText(labels.forkCount)).toBeInTheDocument()
    expect(screen.getByText(labels.openIssueCount)).toBeInTheDocument()
  })

  it('一覧へ戻る導線が /{locale} を指す（FR-6・SP-3 は検索条件を保持しない）', () => {
    render(<RepositoryDetail repository={repository} labels={labels} locale={locale('ja')} />)

    expect(screen.getByRole('link', { name: labels.backLink })).toHaveAttribute('href', '/ja')
  })

  it('en ロケールでも戻る導線が /en を指し、labels props の文言が反映される', () => {
    const enLabels = {
      backLink: 'Back to results',
      language: 'Language',
      starCount: 'stars',
      watcherCount: 'watchers',
      forkCount: 'forks',
      openIssueCount: 'open issues',
    }
    render(<RepositoryDetail repository={repository} labels={enLabels} locale={locale('en')} />)

    expect(screen.getByRole('link', { name: 'Back to results' })).toHaveAttribute('href', '/en')
    expect(screen.getByText('stars')).toBeInTheDocument()
  })

  it('backHref を渡すと戻る導線がそちらを指す（SP-7・検索条件保持）', () => {
    render(
      <RepositoryDetail
        repository={repository}
        labels={labels}
        locale={locale('ja')}
        backHref="/ja?q=react&page=2&sort=stars&per_page=50"
      />,
    )

    expect(screen.getByRole('link', { name: labels.backLink })).toHaveAttribute(
      'href',
      '/ja?q=react&page=2&sort=stars&per_page=50',
    )
  })

  it('primaryLanguage が null の場合は言語表示を出さない', () => {
    render(
      <RepositoryDetail
        repository={{ ...repository, primaryLanguage: null }}
        labels={labels}
        locale={locale('ja')}
      />,
    )

    expect(screen.queryByText(labels.language, { exact: false })).not.toBeInTheDocument()
  })
})
