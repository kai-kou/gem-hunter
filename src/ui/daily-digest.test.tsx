import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { locale } from '../domain/model/locale'
import type { DailyDigest as DailyDigestModel } from '../domain/model/gem'
import { gemIndex } from '../domain/model/gem-index'
import { DailyDigest } from './daily-digest'

const labels = {
  heading: '今日の Gem',
  empty: '今日は表示できる Gem がありません',
  dependentLabel: '被依存数',
  starsLabel: 'star',
  gemIndexLabel: 'Gem Index',
}

function makeDigest(items: DailyDigestModel['items']): DailyDigestModel {
  return {
    date: '20260820',
    items,
    meta: {
      source: 'Ecosyste.ms',
      license: 'CC BY-SA 4.0',
      sourceLicenseUrl: 'https://creativecommons.org/licenses/by-sa/4.0/',
      generatedAt: '2026-08-20T00:00:00Z',
    },
  }
}

describe('DailyDigest', () => {
  it('セクション見出し「今日の Gem」を h2 として表示する（ADR 0014 §2.1）', () => {
    const digest = makeDigest([
      {
        packageName: 'chalk',
        repositoryFullName: 'chalk/chalk',
        dependentCount: 130085,
        stars: 22000,
        gemIndex: gemIndex(-63.9),
      },
    ])

    render(<DailyDigest digest={digest} labels={labels} locale={locale('ja')} />)

    expect(screen.getByRole('heading', { name: '今日の Gem', level: 2 })).toBeInTheDocument()
  })

  it('items を <ol>（順序付きリスト）として並び順どおりに描画する（AR-9 / ADR 0014 §2.2）', () => {
    const digest = makeDigest([
      {
        packageName: 'chalk',
        repositoryFullName: 'chalk/chalk',
        dependentCount: 130085,
        stars: 22000,
        gemIndex: gemIndex(-63.9),
      },
      {
        packageName: 'debug',
        repositoryFullName: 'debug-js/debug',
        dependentCount: 92000,
        stars: 11000,
        gemIndex: gemIndex(-70.2),
      },
    ])

    render(<DailyDigest digest={digest} labels={labels} locale={locale('ja')} />)

    const list = screen.getByRole('list')
    expect(list.tagName.toLowerCase()).toBe('ol')

    const items = within(list).getAllByRole('listitem')
    expect(items).toHaveLength(2)
    // 並び順を検証（1 番目が chalk / 2 番目が debug）。
    expect(within(items[0]).getByRole('link', { name: 'chalk' })).toBeInTheDocument()
    expect(within(items[1]).getByRole('link', { name: 'debug' })).toBeInTheDocument()
  })

  it('各 Gem のリンクは詳細ページ（/{locale}/repos/{owner}/{repo}）を指す（AC-4）', () => {
    const digest = makeDigest([
      {
        packageName: 'ansi-styles',
        repositoryFullName: 'chalk/ansi-styles',
        dependentCount: 41000,
        stars: 500,
        gemIndex: gemIndex(-85.4),
      },
    ])

    render(<DailyDigest digest={digest} labels={labels} locale={locale('ja')} />)

    expect(screen.getByRole('link', { name: 'ansi-styles' })).toHaveAttribute(
      'href',
      '/ja/repos/chalk/ansi-styles',
    )
  })

  it('被依存数・star 数・Gem Index を数値付きで表示する（AR-9）', () => {
    const digest = makeDigest([
      {
        packageName: 'chalk',
        repositoryFullName: 'chalk/chalk',
        dependentCount: 130085,
        stars: 22000,
        gemIndex: gemIndex(-63.9),
      },
    ])

    render(<DailyDigest digest={digest} labels={labels} locale={locale('ja')} />)

    // ja ロケールなので `Intl.NumberFormat('ja-JP')` の書式（3 桁カンマ区切り）。
    expect(screen.getByText(/130,085/)).toBeInTheDocument()
    expect(screen.getByText(/22,000/)).toBeInTheDocument()
    // Gem Index は有理数（負値）そのまま表示する。
    expect(screen.getByText(/-63\.9/)).toBeInTheDocument()
    // 視覚ラベルも並んでいる（sr-only / 通常表示のいずれか）
    expect(screen.getByText(/被依存数/)).toBeInTheDocument()
    expect(screen.getByText(/Gem Index/)).toBeInTheDocument()
  })

  it('空 items のときは role="status" で「今日は表示できる Gem がありません」を伝える（US-23 / ui-ux-guidelines §7.2）', () => {
    const digest = makeDigest([])

    render(<DailyDigest digest={digest} labels={labels} locale={locale('ja')} />)

    expect(screen.getByRole('status')).toHaveTextContent('今日は表示できる Gem がありません')
    // 空のときはリストを描画しない
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
  })

  it('見出しは id="daily-digest-heading" を持ち section の aria-labelledby から参照される（SP-14 手順 5）', () => {
    const digest = makeDigest([
      {
        packageName: 'chalk',
        repositoryFullName: 'chalk/chalk',
        dependentCount: 1,
        stars: 1,
        gemIndex: gemIndex(0),
      },
    ])

    render(<DailyDigest digest={digest} labels={labels} locale={locale('ja')} />)

    const heading = screen.getByRole('heading', { name: '今日の Gem', level: 2 })
    expect(heading).toHaveAttribute('id', 'daily-digest-heading')
    // focus() する側（`FocusOnNavigate`）がまだ居ないので `tabIndex` は持たない（YAGNI）。
    // 日付切替を next/link で実装するスプリントで配線とセットで復活させる。
    expect(heading).not.toHaveAttribute('tabIndex')
    expect(screen.getByRole('region', { name: '今日の Gem' })).toBeInTheDocument()
  })

  it('en ロケールでは英語書式（3 桁カンマ）・英語ラベル文言が反映される（E-4）', () => {
    const digest = makeDigest([
      {
        packageName: 'lodash',
        repositoryFullName: 'lodash/lodash',
        dependentCount: 175000,
        stars: 60000,
        gemIndex: gemIndex(-20.4),
      },
    ])

    render(
      <DailyDigest
        digest={digest}
        labels={{
          heading: "Today's Gems",
          empty: 'No gems to show today.',
          dependentLabel: 'Used by',
          starsLabel: 'stars',
          gemIndexLabel: 'Gem Index',
        }}
        locale={locale('en')}
      />,
    )

    expect(screen.getByRole('heading', { name: "Today's Gems", level: 2 })).toBeInTheDocument()
    expect(screen.getByText(/Used by/)).toBeInTheDocument()
    // en-US も 3 桁カンマ区切り
    expect(screen.getByText(/175,000/)).toBeInTheDocument()
    expect(screen.getByText('lodash/lodash')).toBeInTheDocument()
  })
})
