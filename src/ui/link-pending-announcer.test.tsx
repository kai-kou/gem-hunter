import { render, screen } from '@testing-library/react'
import { useEffect, type ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const linkStatus = vi.hoisted(() => ({ pending: false }))

vi.mock('next/link', () => ({
  __esModule: true,
  default: ({ children }: { children: ReactNode }) => children,
  useLinkStatus: () => ({ pending: linkStatus.pending }),
}))

import { LinkPendingAnnouncer, useLinkPendingReport } from './link-pending-announcer'
import { LinkPendingHint } from './link-pending-hint'

const LABEL = '詳細ページを読み込んでいます'

/** `LinkPendingHint` と同じ作法で Context へ報告するだけの検証用ダミー。 */
function ReportingProbe({ pending }: { pending: boolean }) {
  const report = useLinkPendingReport()

  useEffect(() => {
    if (!pending) return
    report(true)
    return () => {
      report(false)
    }
  }, [pending, report])

  return null
}

describe('LinkPendingAnnouncer', () => {
  beforeEach(() => {
    linkStatus.pending = false
  })

  it('ライブリージョンを 1 個だけ常設し、初期状態では空にする（§7.2）', () => {
    render(
      <LinkPendingAnnouncer label={LABEL}>
        <div>子要素</div>
      </LinkPendingAnnouncer>,
    )

    const liveRegions = screen.getAllByRole('status')
    expect(liveRegions).toHaveLength(1)
    expect(liveRegions[0]).toHaveAttribute('aria-live', 'polite')
    expect(liveRegions[0]).toHaveClass('sr-only')
    expect(liveRegions[0]).toHaveTextContent('')
    // E2E から一意に掴むためのハンドル（ページ内に他の role="status" が複数あるため）。
    expect(liveRegions[0]).toBe(screen.getByTestId('link-pending-announcer'))
  })

  it('ライブリージョンは children の後ろ（兄弟位置）に置かれる', () => {
    const { container } = render(
      <LinkPendingAnnouncer label={LABEL}>
        <div data-testid="child">子要素</div>
      </LinkPendingAnnouncer>,
    )

    const child = screen.getByTestId('child')
    const live = screen.getByRole('status')
    expect(live.parentElement).toBe(container)
    // 入れ子ではなく兄弟であること（§7.2: ライブリージョンを入れ子にしない）。
    expect(child.contains(live)).toBe(false)
    expect(child.compareDocumentPosition(live) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('pending が報告されている間だけラベルを読み上げ領域へ書き込む', () => {
    const { rerender } = render(
      <LinkPendingAnnouncer label={LABEL}>
        <ReportingProbe pending={false} />
      </LinkPendingAnnouncer>,
    )

    expect(screen.getByRole('status')).toHaveTextContent('')

    rerender(
      <LinkPendingAnnouncer label={LABEL}>
        <ReportingProbe pending={true} />
      </LinkPendingAnnouncer>,
    )
    expect(screen.getByRole('status')).toHaveTextContent(LABEL)

    rerender(
      <LinkPendingAnnouncer label={LABEL}>
        <ReportingProbe pending={false} />
      </LinkPendingAnnouncer>,
    )
    expect(screen.getByRole('status')).toHaveTextContent('')
  })

  it('要素ごと動的挿入せず、同じ DOM ノードの中身だけを書き換える（§7.2）', () => {
    const { rerender } = render(
      <LinkPendingAnnouncer label={LABEL}>
        <ReportingProbe pending={false} />
      </LinkPendingAnnouncer>,
    )

    const before = screen.getByRole('status')

    rerender(
      <LinkPendingAnnouncer label={LABEL}>
        <ReportingProbe pending={true} />
      </LinkPendingAnnouncer>,
    )

    expect(screen.getAllByRole('status')).toHaveLength(1)
    expect(screen.getByRole('status')).toBe(before)
  })

  it('複数リンクが同時に pending のとき、1 つ解決してもラベルを保つ（件数カウンタ）', () => {
    const { rerender } = render(
      <LinkPendingAnnouncer label={LABEL}>
        <ReportingProbe pending={true} />
        <ReportingProbe pending={true} />
      </LinkPendingAnnouncer>,
    )
    expect(screen.getByRole('status')).toHaveTextContent(LABEL)

    rerender(
      <LinkPendingAnnouncer label={LABEL}>
        <ReportingProbe pending={false} />
        <ReportingProbe pending={true} />
      </LinkPendingAnnouncer>,
    )
    expect(screen.getByRole('status')).toHaveTextContent(LABEL)

    rerender(
      <LinkPendingAnnouncer label={LABEL}>
        <ReportingProbe pending={false} />
        <ReportingProbe pending={false} />
      </LinkPendingAnnouncer>,
    )
    expect(screen.getByRole('status')).toHaveTextContent('')
  })

  it('pending のまま消えた（アンマウントされた）リンクの分もクリーンアップされる', () => {
    const { rerender } = render(
      <LinkPendingAnnouncer label={LABEL}>
        <ReportingProbe pending={true} />
      </LinkPendingAnnouncer>,
    )
    expect(screen.getByRole('status')).toHaveTextContent(LABEL)

    rerender(<LinkPendingAnnouncer label={LABEL}>{null}</LinkPendingAnnouncer>)
    expect(screen.getByRole('status')).toHaveTextContent('')
  })

  describe('LinkPendingHint との結線（AC-8 / NFR-12）', () => {
    it('Hint の pending がライブリージョンへ伝わる', () => {
      linkStatus.pending = true

      const { rerender } = render(
        <LinkPendingAnnouncer label={LABEL}>
          <LinkPendingHint />
        </LinkPendingAnnouncer>,
      )
      expect(screen.getByRole('status')).toHaveTextContent(LABEL)

      linkStatus.pending = false
      rerender(
        <LinkPendingAnnouncer label={LABEL}>
          <LinkPendingHint />
        </LinkPendingAnnouncer>,
      )
      expect(screen.getByRole('status')).toHaveTextContent('')
    })

    /**
     * 🔴 干渉検証（`agent-team-summary.md` #725）: 本 PR は「1 要素統合」と「Context 報告」を
     * 同時に入れる。片方（統合）が他方（報告）の前提を壊していないこと、および統合が
     * `data-pending` / `opacity` / 固定寸法という既存の DOM 契約（E2E が依存）を壊して
     * いないことを、**同じ pending 遷移の中で** まとめて確かめる。
     */
    it('1 要素統合後の DOM 契約と Context 報告が同時に成立する（干渉検証）', () => {
      linkStatus.pending = true

      const { rerender } = render(
        <LinkPendingAnnouncer label={LABEL}>
          <LinkPendingHint />
        </LinkPendingAnnouncer>,
      )

      const busy = screen.getByTestId('link-pending-hint')
      expect(busy).toHaveAttribute('data-pending', 'true')
      expect(busy).toHaveAttribute('aria-hidden', 'true')
      expect(busy).toHaveClass('size-3', 'opacity-100', 'animate-spin')
      expect(busy).not.toHaveClass('hidden')
      expect(screen.getByRole('status')).toHaveTextContent(LABEL)

      linkStatus.pending = false
      rerender(
        <LinkPendingAnnouncer label={LABEL}>
          <LinkPendingHint />
        </LinkPendingAnnouncer>,
      )

      const idle = screen.getByTestId('link-pending-hint')
      expect(idle).toHaveAttribute('data-pending', 'false')
      expect(idle).toHaveClass('size-3', 'opacity-0')
      expect(idle).not.toHaveClass('animate-spin')
      expect(idle).not.toHaveClass('hidden')
      expect(screen.getByRole('status')).toHaveTextContent('')
    })

    it('Announcer の外でも LinkPendingHint は動く（Context 既定値は no-op）', () => {
      linkStatus.pending = true

      expect(() => render(<LinkPendingHint />)).not.toThrow()
      expect(screen.getByTestId('link-pending-hint')).toHaveAttribute('data-pending', 'true')
      expect(screen.queryByRole('status')).not.toBeInTheDocument()
    })
  })
})
