import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { LoadingIndicator } from './loading-indicator'

describe('LoadingIndicator', () => {
  it('読み込み中のラベルを表示する（US-22 / US-26 / NFR-12）', () => {
    render(<LoadingIndicator label="読み込み中" />)

    expect(screen.getByText('読み込み中')).toBeInTheDocument()
  })

  it('自身は role="status" / aria-live を持たない（外側のライブリージョンへ一本化・#180・ui-ux-guidelines.md §7.2）', () => {
    render(<LoadingIndicator label="読み込み中" />)

    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('ラベルは視覚的にも表示する（0 件・エラーと区別できる・AC-8）', () => {
    render(<LoadingIndicator label="Loading" />)

    expect(screen.getByText('Loading')).not.toHaveClass('sr-only')
  })

  it('読み込み中専用の装飾イラストを alt="" で表示する（Issue #359 T-2）', () => {
    render(<LoadingIndicator label="読み込み中" />)

    const image = screen.getByAltText('')
    expect(image).toHaveAttribute('src', '/images/loading.webp')
  })
})
