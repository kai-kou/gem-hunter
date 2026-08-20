import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { FocusOnNavigate } from './focus-on-navigate'

function Target() {
  return (
    <h2 id="results-heading" tabIndex={-1}>
      検索結果
    </h2>
  )
}

describe('FocusOnNavigate', () => {
  it('初回描画ではフォーカスを奪わない（ページを開いた瞬間に見出しへ飛ばない・E-15）', () => {
    render(
      <>
        <Target />
        <FocusOnNavigate watch="a" targetId="results-heading" />
      </>,
    )

    expect(document.activeElement).not.toBe(screen.getByRole('heading', { level: 2 }))
  })

  it('watch の値が変わったら対象要素へフォーカスを移す（ページ送り・ソート・件数切替後）', () => {
    const { rerender } = render(
      <>
        <Target />
        <FocusOnNavigate watch="a" targetId="results-heading" />
      </>,
    )

    rerender(
      <>
        <Target />
        <FocusOnNavigate watch="b" targetId="results-heading" />
      </>,
    )

    expect(document.activeElement).toBe(screen.getByRole('heading', { level: 2 }))
  })

  it('watch の値が変わらない再描画ではフォーカスを移さない', () => {
    const { rerender } = render(
      <>
        <Target />
        <FocusOnNavigate watch="a" targetId="results-heading" />
      </>,
    )
    ;(screen.getByRole('heading', { level: 2 }) as HTMLElement).blur()

    rerender(
      <>
        <Target />
        <FocusOnNavigate watch="a" targetId="results-heading" />
      </>,
    )

    expect(document.activeElement).not.toBe(screen.getByRole('heading', { level: 2 }))
  })

  it('対象要素が存在しなくても例外を投げない', () => {
    const { rerender } = render(<FocusOnNavigate watch="a" targetId="missing-id" />)

    expect(() => rerender(<FocusOnNavigate watch="b" targetId="missing-id" />)).not.toThrow()
  })
})
