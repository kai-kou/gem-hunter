import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { LoadingIndicator } from './loading-indicator'

describe('LoadingIndicator', () => {
  it('role="status" + aria-live="polite" で読み込み中を伝える（US-22 / US-26 / NFR-12）', () => {
    render(<LoadingIndicator label="読み込み中" />)

    const status = screen.getByRole('status')
    expect(status).toHaveAttribute('aria-live', 'polite')
    expect(status).toHaveTextContent('読み込み中')
  })

  it('ラベルは視覚的にも表示する（0 件・エラーと区別できる・AC-8）', () => {
    render(<LoadingIndicator label="Loading" />)

    expect(screen.getByText('Loading')).not.toHaveClass('sr-only')
  })
})
