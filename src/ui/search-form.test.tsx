import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { SEARCH_PARAM_KEYS } from '../shared/url/search-params'
import { SearchForm } from './search-form'

const labels = {
  inputLabel: '検索キーワード',
  placeholder: 'キーワードで GitHub を検索（例: react）',
  submit: '検索',
}

describe('SearchForm', () => {
  it('検索入力欄と送信ボタンがアクセシブルな名前で取得できる', () => {
    render(<SearchForm keyword="" action="/ja" labels={labels} />)

    expect(screen.getByRole('searchbox')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '検索' })).toBeInTheDocument()
  })

  it('role="search" の GET フォームで action props のパスへ送信する（US-9 / AC-2 / E-8）', () => {
    render(<SearchForm keyword="" action="/ja" labels={labels} />)

    const form = screen.getByRole('search')
    expect(form).toHaveAttribute('action', '/ja')
    expect(form).toHaveAttribute('method', 'get')
  })

  it('input の name が SEARCH_PARAM_KEYS.keyword（契約由来）になっている', () => {
    render(<SearchForm keyword="" action="/ja" labels={labels} />)

    expect(screen.getByRole('searchbox')).toHaveAttribute('name', SEARCH_PARAM_KEYS.keyword)
  })

  it('keyword が入力欄の defaultValue に反映される', () => {
    render(<SearchForm keyword="react" action="/ja" labels={labels} />)

    expect(screen.getByRole('searchbox')).toHaveValue('react')
  })

  it('labels props からラベル・プレースホルダー・送信ボタン文言が反映される', () => {
    render(
      <SearchForm
        keyword=""
        action="/en"
        labels={{ inputLabel: 'Search keyword', placeholder: 'Search GitHub', submit: 'Search' }}
      />,
    )

    expect(screen.getByRole('searchbox', { name: 'Search keyword' })).toHaveAttribute(
      'placeholder',
      'Search GitHub',
    )
    expect(screen.getByRole('button', { name: 'Search' })).toBeInTheDocument()
  })

  it('主要導線として Input と Button に data-size="xl" が付いている', () => {
    render(<SearchForm keyword="" action="/ja" labels={labels} />)

    expect(screen.getByRole('searchbox')).toHaveAttribute('data-size', 'xl')
    expect(screen.getByRole('button', { name: '検索' })).toHaveAttribute('data-size', 'xl')
  })
})
