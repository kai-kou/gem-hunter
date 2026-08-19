import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { MAX_PAGE } from '@/src/domain/model/page-number'
import { Pagination } from './pagination'

const labels = {
  navLabel: '検索結果のページ',
  prev: '前のページへ',
  next: '次のページへ',
  current: '{page} ページ目',
  limitReached: '表示できる最終ページです。',
}

describe('Pagination', () => {
  it('現在ページを表示し、前後ページへのリンクを出す', () => {
    render(
      <Pagination
        basePath="/ja"
        current={{ keyword: 'react', page: 2, sort: 'relevance', perPage: 20 }}
        totalCount={500}
        labels={labels}
      />,
    )

    expect(screen.getByRole('navigation', { name: '検索結果のページ' })).toBeInTheDocument()
    expect(screen.getByText('2 ページ目')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '前のページへ' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '次のページへ' })).toBeInTheDocument()
  })

  it('1 ページ目では前ページリンクを出さない', () => {
    render(
      <Pagination
        basePath="/ja"
        current={{ keyword: 'react', page: 1, sort: 'relevance', perPage: 20 }}
        totalCount={500}
        labels={labels}
      />,
    )

    expect(screen.queryByRole('link', { name: '前のページへ' })).not.toBeInTheDocument()
    expect(screen.getByText('前のページへ')).toHaveAttribute('aria-disabled', 'true')
  })

  it('totalCount から算出した最終ページでは次ページリンクを出さない', () => {
    render(
      <Pagination
        basePath="/ja"
        current={{ keyword: 'react', page: 1, sort: 'relevance', perPage: 20 }}
        totalCount={15}
        labels={labels}
      />,
    )

    expect(screen.queryByRole('link', { name: '次のページへ' })).not.toBeInTheDocument()
  })

  it('MAX_PAGE を超えるページへのリンクを出さない（AC-7）', () => {
    render(
      <Pagination
        basePath="/ja"
        current={{ keyword: 'react', page: MAX_PAGE, sort: 'relevance', perPage: 20 }}
        totalCount={10000}
        labels={labels}
      />,
    )

    expect(screen.queryByRole('link', { name: '次のページへ' })).not.toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('表示できる最終ページです。')
  })

  it('次ページリンクの href は page が 1 つ進み、他の条件はそのまま', () => {
    render(
      <Pagination
        basePath="/ja"
        current={{ keyword: 'react', page: 2, sort: 'stars', perPage: 50 }}
        totalCount={500}
        labels={labels}
      />,
    )

    const href = screen.getByRole('link', { name: '次のページへ' }).getAttribute('href') ?? ''
    const params = new URLSearchParams(href.split('?')[1])

    expect(params.get('page')).toBe('3')
    expect(params.get('sort')).toBe('stars')
    expect(params.get('per_page')).toBe('50')
    expect(params.get('q')).toBe('react')
  })

  it('現在ページはリンクではなく aria-current="page" のテキストで表示する（ui-ux-guidelines §4.5）', () => {
    render(
      <Pagination
        basePath="/ja"
        current={{ keyword: 'react', page: 2, sort: 'relevance', perPage: 20 }}
        totalCount={500}
        labels={labels}
      />,
    )

    const current = screen.getByText('2 ページ目')
    expect(current).toHaveAttribute('aria-current', 'page')
    expect(current.tagName).not.toBe('A')
  })
})
