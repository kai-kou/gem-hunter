import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { DigestMeta } from '../domain/model/gem'
import { locale } from '../domain/model/locale'
import { AttributionNotice } from './attribution-notice'

const meta: DigestMeta = {
  source: 'Ecosyste.ms',
  sourceUrl: 'https://ecosyste.ms/',
  license: 'CC BY-SA 4.0',
  sourceLicenseUrl: 'https://creativecommons.org/licenses/by-sa/4.0/',
  generatedAt: '2026-08-20T00:00:00Z',
}

const labels = {
  attribution:
    'Data via {source}（{license}）· 生成: {generatedAt} · 並び順は日付シードで再算出しています',
  opensInNewTab: '（新しいタブで開きます）',
}

describe('AttributionNotice', () => {
  it('出典（source / license / generatedAt）を全て表示する（D-29）', () => {
    render(<AttributionNotice meta={meta} labels={labels} locale={locale('ja')} />)

    // source は F-6 でリンク化された（`{source}` プレースホルダはリンクテキストになる）。
    expect(
      screen.getByRole('link', { name: 'Ecosyste.ms（新しいタブで開きます）' }),
    ).toBeInTheDocument()
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
          opensInNewTab: '(opens in a new tab)',
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
        labels={{
          attribution: 'src={source} lic={license} at=[{generatedAt}]',
          opensInNewTab: labels.opensInNewTab,
        }}
        locale={locale('ja')}
      />,
    )

    expect(container.querySelector('time')).toBeNull()
    expect(screen.getByText(/at=\[\]/)).toBeInTheDocument()
  })

  it('ライセンスは sourceLicenseUrl を指すリンクになっている（改変元へ辿れる・D-29）', () => {
    render(<AttributionNotice meta={meta} labels={labels} locale={locale('ja')} />)

    const link = screen.getByRole('link', { name: `CC BY-SA 4.0${labels.opensInNewTab}` })
    expect(link).toHaveAttribute('href', 'https://creativecommons.org/licenses/by-sa/4.0/')
    // 外部リンクなので target=_blank + noopener を付ける
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'))
  })

  /**
   * 🔴 §7.4a: 新しいタブで開くリンクは sr-only 文言をアクセシブルネームに含める（Issue #287）。
   * `sr-only` 要素は `<a>` の内側に置くため、視覚テキストだけでなくアクセシブルネームにも
   * 含まれる（スクリーンリーダーのリンク一覧で新規タブで開くことが伝わる）。
   */
  it('ライセンスリンクのアクセシブルネームに「新しいタブで開きます」の告知を含む（§7.4a・Issue #287）', () => {
    render(<AttributionNotice meta={meta} labels={labels} locale={locale('ja')} />)

    const link = screen.getByRole('link', { name: `CC BY-SA 4.0${labels.opensInNewTab}` })
    const srOnly = link.querySelector('.sr-only')
    expect(srOnly).not.toBeNull()
    expect(srOnly?.textContent).toBe(labels.opensInNewTab)
  })

  it('en ロケールでもライセンスリンクのアクセシブルネームに opens in a new tab の告知を含む（§7.4a）', () => {
    const enOpensInNewTab = '(opens in a new tab)'
    render(
      <AttributionNotice
        meta={meta}
        labels={{ attribution: labels.attribution, opensInNewTab: enOpensInNewTab }}
        locale={locale('en')}
      />,
    )

    expect(screen.getByRole('link', { name: `CC BY-SA 4.0${enOpensInNewTab}` })).toBeInTheDocument()
  })

  /**
   * 出典元（source）リンクも `SafeLink` 経由で `target="_blank"` になるため、§7.4a の
   * 「新しいタブで開くリンクは 3 点を必ず満たす」に従い告知を持つ。片方だけに付けると
   * 告知のないリンクが同一タブで開くと誤って推論される（回帰防止）。
   */
  it('出典元リンクのアクセシブルネームにも告知文言が入る（§7.4a は target=_blank の全リンクが対象）', () => {
    render(<AttributionNotice meta={meta} labels={labels} locale={locale('ja')} />)

    expect(
      screen.getByRole('link', { name: `Ecosyste.ms${labels.opensInNewTab}` }),
    ).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Ecosyste.ms' })).not.toBeInTheDocument()
  })

  it('出典元は sourceUrl を指すリンクになっている（Ecosyste.ms 本体へ辿れる・F-6）', () => {
    render(<AttributionNotice meta={meta} labels={labels} locale={locale('ja')} />)

    const link = screen.getByRole('link', { name: 'Ecosyste.ms（新しいタブで開きます）' })
    expect(link).toHaveAttribute('href', 'https://ecosyste.ms/')
    // ライセンスリンクと同じ作法（外部リンクなので target=_blank + noopener）。
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
          opensInNewTab: '(opens in a new tab)',
        }}
        locale={locale('en')}
      />,
    )

    expect(
      screen.getByRole('link', { name: 'Ecosyste.ms(opens in a new tab)' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'CC BY-SA 4.0(opens in a new tab)' })).toHaveAttribute(
      'href',
      'https://creativecommons.org/licenses/by-sa/4.0/',
    )
    expect(screen.getByText(/Order is recomputed/)).toBeInTheDocument()
  })

  it('特殊置換パターン（$&, $1）が値に含まれても壊さない（JSX の直接描画なので置換処理を経由しない）', () => {
    render(
      <AttributionNotice
        meta={{ ...meta, source: 'A $& B' }}
        labels={{ attribution: 'src={source} lic={license}', opensInNewTab: labels.opensInNewTab }}
        locale={locale('ja')}
      />,
    )

    // {source} は文字列置換ではなく React の子要素としてそのまま描画されるため、
    // `$&` 等の特殊置換パターンが解釈されることはない。
    expect(screen.getByRole('link', { name: `A $& B${labels.opensInNewTab}` })).toBeInTheDocument()
  })
  /**
   * 🔵 `{generatedAt}` を含まない文言（Gem 一覧の `gems.attribution`）でも同じ実装を使えること。
   * 含まないのに時刻ノードを描くと、文末へ日時が接ぎ木されて意味の通らない文になる。
   */
  it('{generatedAt} を含まない文言では生成時刻のノードを描かない', () => {
    const { container } = render(
      <AttributionNotice
        meta={meta}
        labels={{
          attribution: 'このデータについて: {source}（{license}）をもとにしています。',
          opensInNewTab: labels.opensInNewTab,
        }}
        locale={locale('ja')}
      />,
    )

    expect(container.querySelector('time')).toBeNull()
    expect(screen.getByText(/をもとにしています。/)).toBeInTheDocument()
    expect(screen.queryByText(/JST/)).not.toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: 'Ecosyste.ms（新しいタブで開きます）' }),
    ).toBeInTheDocument()
  })

  /**
   * 🔴 出典 URL は配信 JSON（外部データ）由来なので無検査で `href` へ流さない。
   */
  it('http(s) 以外の URL はリンクにせずテキストのまま出す（javascript: を href に流さない）', () => {
    render(
      <AttributionNotice
        meta={{
          ...meta,
          sourceUrl: 'javascript:alert(1)',
          sourceLicenseUrl: 'javascript:alert(2)',
        }}
        labels={labels}
        locale={locale('ja')}
      />,
    )

    expect(
      screen.queryByRole('link', { name: 'Ecosyste.ms（新しいタブで開きます）' }),
    ).not.toBeInTheDocument()
    expect(screen.getByText(/Ecosyste\.ms/)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'CC BY-SA 4.0' })).not.toBeInTheDocument()
  })
})
