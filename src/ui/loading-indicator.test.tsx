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

  /**
   * 🔴 Issue #364 で実測した退行の回帰テスト。
   *
   * ラベルに `animate-pulse` を付けると opacity が周期的に下がり、脈動の谷で
   * `--color-fg-muted` の実効コントラストが **4.35:1**（AA の 4.5:1 未満）まで落ちて
   * axe の `color-contrast`（serious / wcag143）に掛かる。テキストのコントラストは
   * **アニメーションの全位相で**満たす必要がある（`ui-ux-guidelines.md` §2.2 / `NFR-13`）。
   *
   * `e2e/sp-9-a11y.spec.ts` の axe スキャンは 1 時点しか見ないため、**谷を踏んだときだけ
   * 落ちる**（実際にフルスイートでのみ再現し、単独実行では 45 回連続で緑になった）。
   * 間欠的なテストを再発検知の頼りにしないよう、ここで決定論的に固定する。
   */
  it('ラベルに opacity を animate するクラスを付けない（脈動の谷で AA コントラストを割るため・Issue #364）', () => {
    render(<LoadingIndicator label="読み込み中" />)

    expect(screen.getByText('読み込み中')).not.toHaveClass('animate-pulse')
  })
})
