import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const linkStatus = vi.hoisted(() => ({ pending: false }))

vi.mock('next/link', () => ({
  __esModule: true,
  default: ({ children }: { children: ReactNode }) => children,
  useLinkStatus: () => ({ pending: linkStatus.pending }),
}))

import { LinkPendingHint } from './link-pending-hint'

describe('LinkPendingHint', () => {
  beforeEach(() => {
    linkStatus.pending = false
  })

  /**
   * 🔴 モジュール全体を差し替えているため、`useLinkStatus` が **実際に** `next/link` から
   * export されているかはモックからは分からない（Next.js 側で改名されてもテストは緑のまま）。
   * 実モジュールを直接読み込んで API の実在を固定する（PR #915 Layer 1 指摘）。
   */
  it('useLinkStatus は next/link の実 export である（モックが API ドリフトを隠さない）', async () => {
    const actual = await vi.importActual<typeof import('next/link')>('next/link')

    expect(typeof actual.useLinkStatus).toBe('function')
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
   * 🔴 スピナーの意匠そのものを固定する。以前は寸法予約用の外側ラッパと回転する内側要素の
   * 2 要素に分かれており、内側が丸ごと消えても全テストが緑のままだった（PR #915 Layer 1 指摘）。
   * 1 要素へ統合したうえで、円形ボーダー・回転・寸法を同じ要素で検証する。
   */
  it('pending の間だけ回転し、円形スピナーの意匠と固定寸法を保つ', () => {
    const { rerender } = render(<LinkPendingHint />)

    const idle = screen.getByTestId('link-pending-hint')
    expect(idle).toHaveClass('size-3', 'rounded-full', 'border-2', 'border-current')
    expect(idle).toHaveClass('border-t-transparent')
    expect(idle).not.toHaveClass('animate-spin')

    linkStatus.pending = true
    rerender(<LinkPendingHint />)

    const busy = screen.getByTestId('link-pending-hint')
    // 寸法は pending でも変わらない（レイアウトシフト防止）。
    expect(busy).toHaveClass('size-3', 'rounded-full', 'border-2', 'border-current')
    expect(busy).toHaveClass('border-t-transparent')
    expect(busy).toHaveClass('animate-spin')
    // 「動きを減らす」設定の利用者には回転させない（`NFR-13` 系）。
    expect(busy).toHaveClass('motion-reduce:animate-none')
  })

  it('寸法予約用のラッパを重ねず 1 要素で完結する（二重定義による寸法ドリフト防止）', () => {
    linkStatus.pending = true
    render(<LinkPendingHint />)

    expect(screen.getByTestId('link-pending-hint').children).toHaveLength(0)
  })

  /**
   * 🔴 本コンポーネント自身はライブリージョンにしない。詳細リンクごとに 1 個ずつ描画される
   * （一覧 1 ページで数十個）ため、ここに `role="status"` を持たせると同種のライブリージョンが
   * 大量に並ぶ。読み上げは祖先に 1 個だけ常設した `LinkPendingAnnouncer` が担い、本要素は
   * `aria-hidden="true"` の純粋な視覚ヒントに留める（`ui-ux-guidelines.md` §7.2）。
   *
   * 🔴 検証には `queryByRole` を使わない: `aria-hidden="true"` 配下は Testing Library の
   * ロールクエリから常に除外されるため、実装が `role="status"` を持っても pass してしまう
   * （PR #915 Layer 1 指摘）。DOM セレクタで直接確かめる。
   */
  it('自身は role="status" / aria-live を持たず aria-hidden である（§7.2）', () => {
    linkStatus.pending = true
    const { container } = render(<LinkPendingHint />)

    const hint = screen.getByTestId('link-pending-hint')
    expect(hint).toHaveAttribute('aria-hidden', 'true')
    expect(hint).not.toHaveAttribute('aria-live')
    expect(hint).not.toHaveAttribute('role')
    expect(container.querySelector('[role="status"]')).toBeNull()
    expect(container.querySelector('[aria-live]')).toBeNull()
  })
})
