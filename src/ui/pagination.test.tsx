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

  it('perPage=100 のとき MAX_PAGE（perPage=20 基準の50）ではなく実際の到達可能上限（10）を超えたら次ページリンクを出さない（AC-7）', () => {
    render(
      <Pagination
        basePath="/ja"
        current={{ keyword: 'react', page: 10, sort: 'relevance', perPage: 100 }}
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

  /**
   * 🔴 Gem 一覧で `badged`（同伴 fullName・Issue #453）を維持したままページ送りできることの回帰。
   * `extraParams` は `buildSearchUrl` 自身の付帯パラメータ機構をそのまま再利用する（`SearchUrlState`
   * に混ぜない理由: `badged` は検索 4 条件ではなく、Pagination を Gem 一覧専用の概念に染めたくない）。
   */
  describe('extraParams（badged 等の付帯パラメータを引き継ぐ）', () => {
    it('前後ページのリンクへ extraParams をそのまま引き継ぐ', () => {
      render(
        <Pagination
          basePath="/ja/gems"
          current={{ keyword: 'next.js', page: 2, sort: 'relevance', perPage: 20 }}
          totalCount={500}
          labels={labels}
          extraParams={{ badged: 'vercel/next.js' }}
        />,
      )

      const prevHref = screen.getByRole('link', { name: '前のページへ' }).getAttribute('href') ?? ''
      const nextHref = screen.getByRole('link', { name: '次のページへ' }).getAttribute('href') ?? ''
      expect(new URLSearchParams(prevHref.split('?')[1]).get('badged')).toBe('vercel/next.js')
      expect(new URLSearchParams(nextHref.split('?')[1]).get('badged')).toBe('vercel/next.js')
    })

    it('extraParams を省略した既存の呼び出しは従来どおり付帯パラメータなしで動く', () => {
      render(
        <Pagination
          basePath="/ja"
          current={{ keyword: 'react', page: 2, sort: 'relevance', perPage: 20 }}
          totalCount={500}
          labels={labels}
        />,
      )

      const nextHref = screen.getByRole('link', { name: '次のページへ' }).getAttribute('href') ?? ''
      expect(new URLSearchParams(nextHref.split('?')[1]).has('badged')).toBe(false)
    })
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
  /**
   * 🔴 GitHub 検索 API を経由しない面（Gem 一覧）は 1,000 件上限に縛られない。
   * `maxPage` を渡した場合は上限を上書きし、API 上限の注記も出さない。
   */
  describe('maxPage で上限を上書きする（API を経由しない面）', () => {
    it('MAX_PAGE を超えるページへもリンクを出す', () => {
      render(
        <Pagination
          basePath="/ja/gems"
          current={{ keyword: 'core', page: MAX_PAGE, sort: 'relevance', perPage: 20 }}
          totalCount={1631}
          labels={labels}
          maxPage={Math.ceil(1631 / 20)}
        />,
      )

      const href = screen.getByRole('link', { name: '次のページへ' }).getAttribute('href') ?? ''
      expect(new URLSearchParams(href.split('?')[1]).get('page')).toBe(String(MAX_PAGE + 1))
    })

    it('上書きした上限の最終ページでも API 上限の注記は出さない（誤った理由を伝えない）', () => {
      render(
        <Pagination
          basePath="/ja/gems"
          current={{ keyword: 'core', page: MAX_PAGE, sort: 'relevance', perPage: 20 }}
          totalCount={MAX_PAGE * 20}
          labels={labels}
          maxPage={MAX_PAGE}
        />,
      )

      expect(screen.queryByRole('status')).not.toBeInTheDocument()
      expect(screen.queryByRole('link', { name: '次のページへ' })).not.toBeInTheDocument()
    })

    it('maxPage を省略した既存の呼び出しは従来どおり API 上限で振る舞う', () => {
      render(
        <Pagination
          basePath="/ja"
          current={{ keyword: 'react', page: MAX_PAGE, sort: 'relevance', perPage: 20 }}
          totalCount={100000}
          labels={labels}
        />,
      )

      expect(screen.queryByRole('link', { name: '次のページへ' })).not.toBeInTheDocument()
      expect(screen.getByRole('status')).toHaveTextContent('表示できる最終ページです。')
    })
  })
})
