import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { SearchForm } from './search-form'

describe('SearchForm', () => {
  it('ラベルを視覚的にも提示する（プレースホルダをラベル代わりにしない・WCAG 3.3.2）', () => {
    render(<SearchForm keyword="" />)

    const label = screen.getByText('キーワード')
    expect(label).toBeInTheDocument()
    expect(label.className).not.toContain('sr-only')
    expect(screen.getByLabelText('キーワード')).toHaveAttribute('name', 'q')
  })

  it('プレースホルダはラベルの言い換えではなく入力例を示す', () => {
    render(<SearchForm keyword="" />)

    const placeholder = screen.getByLabelText('キーワード').getAttribute('placeholder')
    expect(placeholder).toMatch(/例:/)
    expect(placeholder).not.toContain('検索')
  })

  it('入力欄と送信ボタンが同じコントロール高さトークンを使う（44px・タッチ操作性）', () => {
    render(<SearchForm keyword="" />)

    expect(screen.getByLabelText('キーワード').className).toContain('h-control-md')
    expect(screen.getByRole('button', { name: '検索' }).className).toContain('h-control-md')
  })

  it('狭い画面では縦積み・sm 以上で横並びにする（320px 幅で横並びが破綻するため）', () => {
    const { container } = render(<SearchForm keyword="" />)

    const form = container.querySelector('form')
    expect(form?.className).toContain('flex-col')
    expect(form?.className).toContain('sm:flex-row')
  })

  it('送信ボタンは縦積み時に幅いっぱいへ広げる（タップ領域の最大化）', () => {
    render(<SearchForm keyword="" />)

    const submit = screen.getByRole('button', { name: '検索' })
    expect(submit.className).toContain('w-full')
    expect(submit.className).toContain('sm:w-auto')
  })

  it('GET フォームとして検索キーワードを URL に反映する（E-8 / NFR-2）', () => {
    const { container } = render(<SearchForm keyword="react" />)

    const form = container.querySelector('form')
    expect(form).toHaveAttribute('method', 'get')
    expect(form).toHaveAttribute('role', 'search')
    expect(screen.getByLabelText('キーワード')).toHaveValue('react')
  })
})
