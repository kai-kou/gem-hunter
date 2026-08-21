import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { SortPicker } from './sort-picker'

const labels = {
  navLabel: '並び順',
  options: {
    relevance: '関連度',
    stars: 'star 数',
    updated: '更新日時',
    'gem-index': 'Gem Index 順',
  },
}

describe('SortPicker', () => {
  it('relevance / stars / updated / gem-index の 4 リンクを表示する（SP-16）', () => {
    render(
      <SortPicker
        basePath="/ja"
        current={{ keyword: 'react', page: 1, sort: 'relevance', perPage: 20 }}
        labels={labels}
      />,
    )

    expect(screen.getByRole('link', { name: '関連度' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'star 数' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '更新日時' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Gem Index 順' })).toBeInTheDocument()
  })

  it('gem-index リンクの href に sort=gem-index が乗り、ページは 1 に戻る（SP-16）', () => {
    render(
      <SortPicker
        basePath="/ja"
        current={{ keyword: 'react', page: 3, sort: 'relevance', perPage: 50 }}
        labels={labels}
      />,
    )

    const href = screen.getByRole('link', { name: 'Gem Index 順' }).getAttribute('href') ?? ''
    const params = new URLSearchParams(href.split('?')[1])

    expect(params.get('q')).toBe('react')
    expect(params.get('sort')).toBe('gem-index')
    expect(params.get('per_page')).toBe('50')
    expect(params.has('page')).toBe(false)
  })

  it('現在の並び順に aria-current="true" が付く', () => {
    render(
      <SortPicker
        basePath="/ja"
        current={{ keyword: 'react', page: 1, sort: 'stars', perPage: 20 }}
        labels={labels}
      />,
    )

    expect(screen.getByRole('link', { name: 'star 数' })).toHaveAttribute('aria-current', 'true')
    expect(screen.getByRole('link', { name: '関連度' })).not.toHaveAttribute('aria-current')
  })

  it('star 数リンクの href に sort=stars とキーワードが載り、ページは 1 に戻る（SP-7）', () => {
    render(
      <SortPicker
        basePath="/ja"
        current={{ keyword: 'react', page: 3, sort: 'relevance', perPage: 50 }}
        labels={labels}
      />,
    )

    const href = screen.getByRole('link', { name: 'star 数' }).getAttribute('href') ?? ''
    const params = new URLSearchParams(href.split('?')[1])

    expect(params.get('q')).toBe('react')
    expect(params.get('sort')).toBe('stars')
    expect(params.get('per_page')).toBe('50')
    expect(params.has('page')).toBe(false)
  })
})
