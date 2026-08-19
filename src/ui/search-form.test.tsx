import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { SearchForm } from './search-form'

describe('SearchForm', () => {
  it('検索入力欄と送信ボタンがアクセシブルな名前で取得できる', () => {
    render(<SearchForm keyword="" />)

    expect(screen.getByRole('searchbox')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '検索' })).toBeInTheDocument()
  })

  it('role="search" の GET フォームで q パラメータを送信する（US-6 / AC-2 / E-8）', () => {
    render(<SearchForm keyword="" />)

    const form = screen.getByRole('search')
    expect(form).toHaveAttribute('action', '/')
    expect(form).toHaveAttribute('method', 'get')
    expect(screen.getByRole('searchbox')).toHaveAttribute('name', 'q')
  })

  it('keyword が入力欄の defaultValue に反映される', () => {
    render(<SearchForm keyword="react" />)

    expect(screen.getByRole('searchbox')).toHaveValue('react')
  })

  it('主要導線として Input と Button に data-size="xl" が付いている', () => {
    render(<SearchForm keyword="" />)

    expect(screen.getByRole('searchbox')).toHaveAttribute('data-size', 'xl')
    expect(screen.getByRole('button', { name: '検索' })).toHaveAttribute('data-size', 'xl')
  })
})
