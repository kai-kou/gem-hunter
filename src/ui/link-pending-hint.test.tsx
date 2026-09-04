import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const linkStatus = vi.hoisted(() => ({ pending: false }))

vi.mock('next/link', () => ({
  __esModule: true,
  default: ({ children }: { children: React.ReactNode }) => children,
  useLinkStatus: () => ({ pending: linkStatus.pending }),
}))

import { LinkPendingHint } from './link-pending-hint'

describe('LinkPendingHint', () => {
  beforeEach(() => {
    linkStatus.pending = false
  })

  it('遷移待ちでなくても DOM に常設される（レイアウトシフト防止・US-22）', () => {
    render(<LinkPendingHint />)

    const hint = screen.getByTestId('link-pending-hint')
    expect(hint).toBeInTheDocument()
    expect(hint).toHaveAttribute('data-pending', 'false')
  })

  it('遷移待ちの間だけ data-pending="true" になる（US-22 / AC-8）', () => {
    linkStatus.pending = true
    render(<LinkPendingHint />)

    expect(screen.getByTestId('link-pending-hint')).toHaveAttribute('data-pending', 'true')
  })

  it('可視性は opacity で切り替え、display で消さない（寸法を保ちレイアウトシフトを避ける）', () => {
    const { rerender } = render(<LinkPendingHint />)

    const idle = screen.getByTestId('link-pending-hint')
    expect(idle).toHaveClass('opacity-0')
    expect(idle).not.toHaveClass('hidden')

    linkStatus.pending = true
    rerender(<LinkPendingHint />)

    const busy = screen.getByTestId('link-pending-hint')
    expect(busy).toHaveClass('opacity-100')
    expect(busy).not.toHaveClass('hidden')
  })

  /**
   * 🔴 ライブリージョンは画面に唯一・常設という規約（`ui-ux-guidelines.md` §7.2）を守る。
   * 本コンポーネントは詳細リンクごとに 1 個ずつ描画されるため、`role="status"` /
   * `aria-live` を持たせると 1 画面に何十個ものライブリージョンが生まれる。
   * 支援技術へは何も伝えない純粋な視覚ヒント（`aria-hidden="true"`）に留める。
   */
  it('自身は role="status" / aria-live を持たず aria-hidden である（§7.2）', () => {
    linkStatus.pending = true
    render(<LinkPendingHint />)

    const hint = screen.getByTestId('link-pending-hint')
    expect(hint).toHaveAttribute('aria-hidden', 'true')
    expect(hint).not.toHaveAttribute('aria-live')
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})
