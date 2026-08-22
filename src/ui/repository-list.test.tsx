import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { type GemIndex, gemIndex } from '../domain/model/gem-index'
import { locale } from '../domain/model/locale'
import type { RepositorySummary } from '../domain/model/repository'
import { RepositoryList } from './repository-list'

const labels = {
  empty: '条件に合うリポジトリは見つかりませんでした。キーワードを変えて試してください。',
  starCount: 'star 数',
  updatedAt: '最終更新',
}

const items: RepositorySummary[] = [
  {
    id: 10270250,
    fullName: 'facebook/react',
    name: 'react',
    owner: { login: 'facebook', avatarUrl: 'https://avatars.githubusercontent.com/u/69631?v=4' },
    description: 'The library for web and native user interfaces.',
    primaryLanguage: 'JavaScript',
    stars: 233000,
    lastPushedAt: new Date('2026-08-18T09:00:00Z'),
    topics: ['javascript'],
    htmlUrl: 'https://github.com/facebook/react',
  },
]

describe('RepositoryList', () => {
  it('オーナーアイコンとリポジトリ名を表示する（AC-3）', () => {
    const { container } = render(
      <RepositoryList items={items} labels={labels} locale={locale('ja')} />,
    )

    expect(screen.getByRole('link', { name: /facebook\/react/ })).toBeInTheDocument()
    // オーナー名は fullName としてカード内にテキスト隣接表示されるため alt="" にしており、
    // 装飾画像扱い（role=presentation）になる（ui-ux-guidelines §7.4）→ getByRole('img') は使えない
    const img = container.querySelector('img')
    expect(img).toHaveAttribute('src', expect.stringContaining('avatars.githubusercontent.com'))
    expect(img).toHaveAttribute('alt', '')
  })

  it('カードは独立 URL の詳細ページへのリンクになっている（モーダルではない・AC-4）', () => {
    render(<RepositoryList items={items} labels={labels} locale={locale('ja')} />)

    expect(screen.getByRole('link', { name: /facebook\/react/ })).toHaveAttribute(
      'href',
      '/ja/repos/facebook/react',
    )
  })

  it('リポジトリ名にドットを含む場合も正しい href になる（例: user.github.io）', () => {
    const dotted: RepositorySummary[] = [
      {
        id: 1,
        fullName: 'octocat/octocat.github.io',
        name: 'octocat.github.io',
        owner: { login: 'octocat', avatarUrl: 'https://avatars.githubusercontent.com/u/1?v=4' },
        description: null,
        primaryLanguage: null,
        stars: 1,
        lastPushedAt: new Date('2026-08-18T09:00:00Z'),
        topics: [],
        htmlUrl: 'https://github.com/octocat/octocat.github.io',
      },
    ]

    render(<RepositoryList items={dotted} labels={labels} locale={locale('ja')} />)

    expect(screen.getByRole('link', { name: /octocat\/octocat\.github\.io/ })).toHaveAttribute(
      'href',
      '/ja/repos/octocat/octocat.github.io',
    )
  })

  it('説明・主要言語・star 数・topics を表示する（AR-1）', () => {
    render(<RepositoryList items={items} labels={labels} locale={locale('ja')} />)

    expect(screen.getByText(/The library for web and native user interfaces\./)).toBeInTheDocument()
    expect(screen.getByText('JavaScript')).toBeInTheDocument()
    expect(screen.getByText('233,000')).toBeInTheDocument()
    expect(screen.getByText('javascript')).toBeInTheDocument()
  })

  it('結果ゼロ件のときは該当なしを伝える', () => {
    render(<RepositoryList items={[]} labels={labels} locale={locale('ja')} />)

    expect(screen.getByText(/見つかりませんでした/)).toBeInTheDocument()
  })

  it('searchState を渡すと詳細リンクへ検索条件がクエリとして継ぎ足される（SP-7・詳細→戻る用）', () => {
    render(
      <RepositoryList
        items={items}
        labels={labels}
        locale={locale('ja')}
        searchState={{ keyword: 'react', page: 2, sort: 'stars', perPage: 50 }}
      />,
    )

    const href = screen.getByRole('link', { name: /facebook\/react/ }).getAttribute('href') ?? ''
    const [path, qs] = href.split('?')
    const params = new URLSearchParams(qs)

    expect(path).toBe('/ja/repos/facebook/react')
    expect(params.get('q')).toBe('react')
    expect(params.get('page')).toBe('2')
    expect(params.get('sort')).toBe('stars')
    expect(params.get('per_page')).toBe('50')
  })

  it('searchState を渡さない場合は既存どおりクエリなしのリンクになる（後方互換）', () => {
    render(<RepositoryList items={items} labels={labels} locale={locale('ja')} />)

    expect(screen.getByRole('link', { name: /facebook\/react/ })).toHaveAttribute(
      'href',
      '/ja/repos/facebook/react',
    )
  })

  it('labels props から star 数・最終更新のラベル文言が反映される（E-4）', () => {
    render(
      <RepositoryList
        items={items}
        labels={{ empty: 'No repositories matched.', starCount: 'stars', updatedAt: 'Updated' }}
        locale={locale('en')}
      />,
    )

    expect(screen.getByText('stars', { exact: false })).toBeInTheDocument()
    expect(screen.getByText(/Updated/)).toBeInTheDocument()
  })

  it('ja ロケールでは星数・更新日を日本式書式（YYYY/MM/DD）で表示する（🔴 CRITICAL 修正）', () => {
    render(<RepositoryList items={items} labels={labels} locale={locale('ja')} />)

    expect(screen.getByText('233,000')).toBeInTheDocument()
    expect(screen.getByText(/2026\/08\/18/)).toBeInTheDocument()
  })

  it('en ロケールでは英語ラベルと英語式日付（MM/DD/YYYY）が両方揃って表示される（🔴 CRITICAL 修正）', () => {
    render(
      <RepositoryList
        items={items}
        labels={{ empty: 'No repositories matched.', starCount: 'stars', updatedAt: 'Updated' }}
        locale={locale('en')}
      />,
    )

    expect(screen.getByText('233,000')).toBeInTheDocument()
    expect(screen.getByText(/08\/18\/2026/)).toBeInTheDocument()
    expect(screen.getByText(/Updated/)).toBeInTheDocument()
  })

  it('0 件のときは role="status" で支援技術にも伝える（US-23 / US-26 / NFR-12）', () => {
    render(<RepositoryList items={[]} labels={labels} locale={locale('ja')} />)

    expect(screen.getByRole('status')).toHaveTextContent(labels.empty)
  })

  it('0 件のときの装飾画像は alt="" かつ role="status" の要素の外（兄弟）にある（Issue #347）', () => {
    const { container } = render(
      <RepositoryList items={[]} labels={labels} locale={locale('ja')} />,
    )

    // alt="" の img はアクセシビリティツリーから除外され role="img" にならないため、
    // DOM から直接 querySelector で拾う（a11y_i18n round3 確定マークアップの検証手段）。
    const img = container.querySelector('img')
    expect(img).not.toBeNull()
    expect(img).toHaveAttribute('alt', '')
    expect(img).toHaveAttribute('src', '/images/empty-result.webp')

    // 🔴 構造契約: img は role="status" の要素の内側に無いこと（外＝兄弟であること）。
    // 内側にあると再検索のたびに aria-atomic で画像ごと再構成される恐れがある。
    const status = screen.getByRole('status')
    expect(status.contains(img)).toBe(false)
    expect(img?.parentElement).toBe(status.parentElement)
  })
})

describe('RepositoryList — Gem バッジ（SP-18 / D-36）', () => {
  const gemLabels = {
    ...labels,
    gemBadge: 'Gem',
    gemBadgeSrHint: 'star の数のわりに、多くのパッケージから使われている候補です',
    gemBadgeNote:
      'Gem の印は 12 のパッケージレジストリから集めた限定的なデータに基づきます。印が付かないことは、そのリポジトリの評価が低いことを意味しません。',
  }

  /** 並び順の検証に使う複数件。`items[0]` は Gem 候補プールに載っていない想定。 */
  const threeItems: RepositorySummary[] = [
    {
      id: 1,
      fullName: 'facebook/react',
      name: 'react',
      owner: { login: 'facebook', avatarUrl: 'https://avatars.githubusercontent.com/u/69631?v=4' },
      description: null,
      primaryLanguage: 'JavaScript',
      stars: 233000,
      lastPushedAt: new Date('2026-08-18T09:00:00Z'),
      topics: [],
      htmlUrl: 'https://github.com/facebook/react',
    },
    {
      id: 2,
      fullName: 'sindresorhus/is-color-stop',
      name: 'is-color-stop',
      owner: { login: 'sindresorhus', avatarUrl: 'https://avatars.githubusercontent.com/u/170270?v=4' },
      description: null,
      primaryLanguage: 'JavaScript',
      stars: 12,
      lastPushedAt: new Date('2026-08-10T09:00:00Z'),
      topics: [],
      htmlUrl: 'https://github.com/sindresorhus/is-color-stop',
    },
    {
      id: 3,
      fullName: 'arkworks-rs/algebra',
      name: 'algebra',
      owner: { login: 'arkworks-rs', avatarUrl: 'https://avatars.githubusercontent.com/u/3?v=4' },
      description: null,
      primaryLanguage: 'Rust',
      stars: 40,
      lastPushedAt: new Date('2026-08-01T09:00:00Z'),
      topics: [],
      htmlUrl: 'https://github.com/arkworks-rs/algebra',
    },
  ]

  const gemIndexes = new Map<string, GemIndex>([
    ['sindresorhus/is-color-stop', gemIndex(-0.42)],
    ['arkworks-rs/algebra', gemIndex(-0.31)],
  ])

  /** カード（`<li>`）ごとの「Gem バッジを持っているか」を items の並び順で返す。 */
  function badgePresenceByCard(container: HTMLElement): boolean[] {
    return Array.from(container.querySelectorAll('li')).map((li) =>
      Array.from(li.querySelectorAll('span')).some((span) => span.textContent === 'Gem'),
    )
  }

  it('gemIndexes に載っているカードにだけバッジが出る', () => {
    const { container } = render(
      <RepositoryList
        items={threeItems}
        labels={gemLabels}
        locale={locale('ja')}
        gemIndexes={gemIndexes}
      />,
    )

    expect(badgePresenceByCard(container)).toEqual([false, true, true])
    expect(screen.getAllByText('Gem')).toHaveLength(2)
  })

  it('バッジには意味を説明する sr-only 文言が添えられる（色だけに頼らない・§7）', () => {
    render(
      <RepositoryList
        items={threeItems}
        labels={gemLabels}
        locale={locale('ja')}
        gemIndexes={gemIndexes}
      />,
    )

    // カードごとに 1 つずつ（＝バッジと同数）。全カードに配って読み上げを増やさない。
    expect(screen.getAllByText(gemLabels.gemBadgeSrHint)).toHaveLength(2)
  })

  it('gemIndexes を渡さないとバッジも注記も出ない（既存呼び出しとの後方互換）', () => {
    const { container } = render(
      <RepositoryList items={threeItems} labels={labels} locale={locale('ja')} />,
    )

    expect(badgePresenceByCard(container)).toEqual([false, false, false])
    expect(screen.queryByText('Gem')).not.toBeInTheDocument()
    expect(screen.queryByText(/評価が低いことを意味しません/)).not.toBeInTheDocument()
  })

  it('🔴 バッジの有無で並び順を変えない（items の順序をそのまま描画する・D-36）', () => {
    const { container } = render(
      <RepositoryList
        items={threeItems}
        labels={gemLabels}
        locale={locale('ja')}
        gemIndexes={gemIndexes}
      />,
    )

    const renderedOrder = Array.from(container.querySelectorAll('li a')).map(
      (a) => a.textContent ?? '',
    )
    expect(renderedOrder).toEqual(threeItems.map((item) => item.fullName))
  })

  it('🔴 Gem Index の値の大小でも並び替えない（gemIndexes の順序に引きずられない）', () => {
    // gemIndexes 側の並びを逆にしても描画順は items のまま。
    const reversed = new Map<string, GemIndex>([
      ['arkworks-rs/algebra', gemIndex(-0.31)],
      ['sindresorhus/is-color-stop', gemIndex(-0.42)],
    ])

    const { container } = render(
      <RepositoryList
        items={threeItems}
        labels={gemLabels}
        locale={locale('ja')}
        gemIndexes={reversed}
      />,
    )

    const renderedOrder = Array.from(container.querySelectorAll('li a')).map(
      (a) => a.textContent ?? '',
    )
    expect(renderedOrder).toEqual(['facebook/react', 'sindresorhus/is-color-stop', 'arkworks-rs/algebra'])
  })

  it('「付かない＝低評価ではない」注記は一覧に 1 回だけ出る（カードごとに出さない）', () => {
    render(
      <RepositoryList
        items={threeItems}
        labels={gemLabels}
        locale={locale('ja')}
        gemIndexes={gemIndexes}
      />,
    )

    expect(screen.getAllByText(gemLabels.gemBadgeNote)).toHaveLength(1)
  })

  it('注記は一覧（ul）の外に置き、カードの中に混ぜない', () => {
    const { container } = render(
      <RepositoryList
        items={threeItems}
        labels={gemLabels}
        locale={locale('ja')}
        gemIndexes={gemIndexes}
      />,
    )

    const note = screen.getByText(gemLabels.gemBadgeNote)
    expect(container.querySelector('ul')?.contains(note)).toBe(false)
  })

  it('バッジが 0 件のときは注記を出さない（無関係な説明でノイズを増やさない）', () => {
    render(
      <RepositoryList
        items={threeItems}
        labels={gemLabels}
        locale={locale('ja')}
        gemIndexes={new Map<string, GemIndex>()}
      />,
    )

    expect(screen.queryByText('Gem')).not.toBeInTheDocument()
    expect(screen.queryByText(gemLabels.gemBadgeNote)).not.toBeInTheDocument()
  })

  it('0 件表示の経路は Gem 用 props を渡しても壊れない（labels.empty がそのまま出る）', () => {
    render(
      <RepositoryList
        items={[]}
        labels={gemLabels}
        locale={locale('ja')}
        gemIndexes={gemIndexes}
      />,
    )

    expect(screen.getByRole('status')).toHaveTextContent(gemLabels.empty)
    expect(screen.queryByText('Gem')).not.toBeInTheDocument()
    expect(screen.queryByText(gemLabels.gemBadgeNote)).not.toBeInTheDocument()
  })

  it('照合は fullName の完全一致で行う（大文字小文字違い・部分一致では付かない）', () => {
    const { container } = render(
      <RepositoryList
        items={threeItems}
        labels={gemLabels}
        locale={locale('ja')}
        gemIndexes={new Map<string, GemIndex>([['Sindresorhus/Is-Color-Stop', gemIndex(-0.42)]])}
      />,
    )

    expect(badgePresenceByCard(container)).toEqual([false, false, false])
  })
})
