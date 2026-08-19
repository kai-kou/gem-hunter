import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { PerPagePicker } from './per-page-picker'

const labels = {
  navLabel: '表示件数',
  optionLabel: '{count} 件',
}

describe('PerPagePicker', () => {
  it('20 / 50 / 100 件の 3 リンクを表示する', () => {
    render(
      <PerPagePicker
        basePath="/ja"
        current={{ keyword: 'react', page: 1, sort: 'relevance', perPage: 20 }}
        labels={labels}
      />,
    )

    expect(screen.getByRole('link', { name: '20 件' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '50 件' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '100 件' })).toBeInTheDocument()
  })

  it('現在の表示件数に aria-current="true" が付く', () => {
    render(
      <PerPagePicker
        basePath="/ja"
        current={{ keyword: 'react', page: 1, sort: 'relevance', perPage: 50 }}
        labels={labels}
      />,
    )

    expect(screen.getByRole('link', { name: '50 件' })).toHaveAttribute('aria-current', 'true')
    expect(screen.getByRole('link', { name: '20 件' })).not.toHaveAttribute('aria-current')
  })

  it('100 件リンクの href に per_page=100 が載り、ページは 1 に戻る（SP-7）', () => {
    render(
      <PerPagePicker
        basePath="/ja"
        current={{ keyword: 'react', page: 4, sort: 'stars', perPage: 20 }}
        labels={labels}
      />,
    )

    const href = screen.getByRole('link', { name: '100 件' }).getAttribute('href') ?? ''
    const params = new URLSearchParams(href.split('?')[1])

    expect(params.get('per_page')).toBe('100')
    expect(params.get('sort')).toBe('stars')
    expect(params.has('page')).toBe(false)
  })
})
