import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { DigestMeta } from '../domain/model/gem'
import { AttributionNotice } from './attribution-notice'

const meta: DigestMeta = {
  source: 'Ecosyste.ms',
  license: 'CC BY-SA 4.0',
  sourceLicenseUrl: 'https://creativecommons.org/licenses/by-sa/4.0/',
  generatedAt: '2026-08-20T00:00:00Z',
}

const labels = {
  attribution:
    'Data via {source}（{license}）· 生成: {generatedAt} · 並び順は日付シードで再算出しています',
}

describe('AttributionNotice', () => {
  it('出典（source / license / generatedAt）を全て表示する（D-29）', () => {
    render(<AttributionNotice meta={meta} labels={labels} />)

    expect(screen.getByText(/Data via Ecosyste\.ms/)).toBeInTheDocument()
    expect(screen.getByText(/2026-08-20T00:00:00Z/)).toBeInTheDocument()
  })

  it('ライセンスは sourceLicenseUrl を指すリンクになっている（改変元へ辿れる・D-29）', () => {
    render(<AttributionNotice meta={meta} labels={labels} />)

    const link = screen.getByRole('link', { name: 'CC BY-SA 4.0' })
    expect(link).toHaveAttribute('href', 'https://creativecommons.org/licenses/by-sa/4.0/')
    // 外部リンクなので target=_blank + noopener を付ける
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'))
  })

  it('改変の明示（日付シードで再算出）を含む（D-29 の改変明示要件）', () => {
    render(<AttributionNotice meta={meta} labels={labels} />)

    expect(screen.getByText(/日付シードで再算出/)).toBeInTheDocument()
  })

  it('en ロケール向けの文言テンプレートでも同じ 3 要素を差し込める（E-4）', () => {
    render(
      <AttributionNotice
        meta={meta}
        labels={{
          attribution:
            "Data via {source} ({license}) · Generated: {generatedAt} · Order is recomputed from the day's seed.",
        }}
      />,
    )

    expect(screen.getByText(/Data via Ecosyste\.ms/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'CC BY-SA 4.0' })).toHaveAttribute(
      'href',
      'https://creativecommons.org/licenses/by-sa/4.0/',
    )
    expect(screen.getByText(/Generated: 2026-08-20T00:00:00Z/)).toBeInTheDocument()
    expect(screen.getByText(/Order is recomputed/)).toBeInTheDocument()
  })

  it('特殊置換パターン（$&, $1）が値に含まれても壊さない（formatMessage と同等の安全性）', () => {
    render(
      <AttributionNotice
        meta={{ ...meta, source: 'A $& B' }}
        labels={{ attribution: 'src={source} lic={license}' }}
      />,
    )

    expect(screen.getByText(/src=A \$& B lic=/)).toBeInTheDocument()
  })
})
