import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { DigestMeta } from '../domain/model/gem'
import { locale } from '../domain/model/locale'
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
    render(<AttributionNotice meta={meta} labels={labels} locale={locale('ja')} />)

    expect(screen.getByText(/Data via Ecosyste\.ms/)).toBeInTheDocument()
    // 生成時刻は JST 表示（datetime-rules.md §0）。UTC 00:00 は JST 09:00。
    expect(screen.getByText(/2026\/08\/20 09:00 JST/)).toBeInTheDocument()
  })

  it('生成時刻は JST 表記で、機械可読値（ISO 8601 UTC）は <time dateTime> に残す（datetime-rules.md §0）', () => {
    const { container } = render(
      <AttributionNotice meta={meta} labels={labels} locale={locale('ja')} />,
    )

    const time = container.querySelector('time')
    expect(time).not.toBeNull()
    expect(time).toHaveAttribute('dateTime', '2026-08-20T00:00:00Z')
    expect(time?.textContent).toBe('2026/08/20 09:00 JST')
    // 生の ISO 8601 をそのまま画面へ出さない
    expect(screen.queryByText(/2026-08-20T00:00:00Z/)).not.toBeInTheDocument()
  })

  it('en ロケールでは en-US 書式 + JST 明示で整形する（E-4 / datetime-rules.md §0）', () => {
    const { container } = render(
      <AttributionNotice
        meta={meta}
        labels={{
          attribution:
            "Data via {source} ({license}) · Generated: {generatedAt} · Order is recomputed from the day's seed.",
        }}
        locale={locale('en')}
      />,
    )

    const time = container.querySelector('time')
    expect(time?.textContent).toMatch(/2026/)
    expect(time?.textContent).toMatch(/09:00/)
    expect(time?.textContent).toMatch(/JST$/)
  })

  it('generatedAt が壊れている（空文字・非 ISO）ときも例外にせず生値をそのまま出す', () => {
    const { container } = render(
      <AttributionNotice
        meta={{ ...meta, generatedAt: '' }}
        labels={{ attribution: 'src={source} lic={license} at=[{generatedAt}]' }}
        locale={locale('ja')}
      />,
    )

    expect(container.querySelector('time')).toBeNull()
    expect(screen.getByText(/at=\[\]/)).toBeInTheDocument()
  })

  it('ライセンスは sourceLicenseUrl を指すリンクになっている（改変元へ辿れる・D-29）', () => {
    render(<AttributionNotice meta={meta} labels={labels} locale={locale('ja')} />)

    const link = screen.getByRole('link', { name: 'CC BY-SA 4.0' })
    expect(link).toHaveAttribute('href', 'https://creativecommons.org/licenses/by-sa/4.0/')
    // 外部リンクなので target=_blank + noopener を付ける
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'))
  })

  it('改変の明示（日付シードで再算出）を含む（D-29 の改変明示要件）', () => {
    render(<AttributionNotice meta={meta} labels={labels} locale={locale('ja')} />)

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
        locale={locale('en')}
      />,
    )

    expect(screen.getByText(/Data via Ecosyste\.ms/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'CC BY-SA 4.0' })).toHaveAttribute(
      'href',
      'https://creativecommons.org/licenses/by-sa/4.0/',
    )
    expect(screen.getByText(/Order is recomputed/)).toBeInTheDocument()
  })

  it('特殊置換パターン（$&, $1）が値に含まれても壊さない（formatMessage の安全性を共有する）', () => {
    render(
      <AttributionNotice
        meta={{ ...meta, source: 'A $& B' }}
        labels={{ attribution: 'src={source} lic={license}' }}
        locale={locale('ja')}
      />,
    )

    expect(screen.getByText(/src=A \$& B lic=/)).toBeInTheDocument()
  })
})
