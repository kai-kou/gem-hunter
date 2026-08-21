import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { gemIndex } from '../domain/model/gem-index'
import type { GemFacet } from '../domain/model/gem'
import { locale } from '../domain/model/locale'
import type { RepositorySummary } from '../domain/model/repository'
import { RepositoryList } from './repository-list'

const labels = {
  empty: '条件に合うリポジトリは見つかりませんでした。キーワードを変えて試してください。',
  starCount: 'star 数',
  updatedAt: '最終更新',
  gemIndexValueLabel: 'Gem Index',
  gemIndexDependentLabel: '被依存数',
  gemIndexUnavailableHeading: 'Gem Index 情報なし',
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

  describe('gemFacets（SP-16・Gem Index 順ソート時のみ）', () => {
    const twoItems: RepositorySummary[] = [
      {
        id: 1,
        fullName: 'octostub/ranked-one',
        name: 'ranked-one',
        owner: { login: 'octostub', avatarUrl: 'https://avatars.githubusercontent.com/u/1?v=4' },
        description: null,
        primaryLanguage: null,
        stars: 10,
        lastPushedAt: new Date('2026-08-18T09:00:00Z'),
        topics: [],
        htmlUrl: 'https://github.com/octostub/ranked-one',
      },
      {
        id: 2,
        fullName: 'octostub/unranked-two',
        name: 'unranked-two',
        owner: { login: 'octostub', avatarUrl: 'https://avatars.githubusercontent.com/u/2?v=4' },
        description: null,
        primaryLanguage: null,
        stars: 20,
        lastPushedAt: new Date('2026-08-18T09:00:00Z'),
        topics: [],
        htmlUrl: 'https://github.com/octostub/unranked-two',
      },
    ]

    function facetMap(): ReadonlyMap<string, GemFacet> {
      return new Map([
        ['octostub/ranked-one', { gemIndex: gemIndex(-0.42), dependentCount: 12345 }],
      ])
    }

    it('gemFacets を渡さない場合は Gem Index 情報を一切表示しない（回帰なし）', () => {
      render(<RepositoryList items={twoItems} labels={labels} locale={locale('ja')} />)

      expect(screen.queryByText(labels.gemIndexUnavailableHeading)).not.toBeInTheDocument()
      expect(screen.queryByText(/-0\.42/)).not.toBeInTheDocument()
    })

    it('facet を持つカードには Gem Index 値と被依存数を追記する（D-L）', () => {
      render(
        <RepositoryList
          items={twoItems}
          labels={labels}
          locale={locale('ja')}
          gemFacets={facetMap()}
        />,
      )

      expect(screen.getByText(/-0\.42/)).toBeInTheDocument()
      expect(screen.getByText(/12,345/)).toBeInTheDocument()
    })

    it('facet を持たないカードには Gem Index 値を出さない', () => {
      render(
        <RepositoryList
          items={twoItems}
          labels={labels}
          locale={locale('ja')}
          gemFacets={facetMap()}
        />,
      )

      const unrankedCard = screen
        .getByRole('link', { name: /octostub\/unranked-two/ })
        .closest('li')
      expect(unrankedCard).not.toBeNull()
      expect(unrankedCard).not.toHaveTextContent('-0.42')
    })

    it('両グループが存在するときだけ、非保有分の直前に区切り見出しを 1 本挿入する（D-M）', () => {
      render(
        <RepositoryList
          items={twoItems}
          labels={labels}
          locale={locale('ja')}
          gemFacets={facetMap()}
        />,
      )

      expect(screen.getAllByText(labels.gemIndexUnavailableHeading)).toHaveLength(1)
    })

    it('全件が facet を持つ場合は区切り見出しを出さない', () => {
      const allRanked = new Map([
        ['octostub/ranked-one', { gemIndex: gemIndex(-0.42), dependentCount: 1 }],
        ['octostub/unranked-two', { gemIndex: gemIndex(-0.1), dependentCount: 2 }],
      ])
      render(
        <RepositoryList
          items={twoItems}
          labels={labels}
          locale={locale('ja')}
          gemFacets={allRanked}
        />,
      )

      expect(screen.queryByText(labels.gemIndexUnavailableHeading)).not.toBeInTheDocument()
    })

    it('全件が facet を持たない場合は区切り見出しを出さない', () => {
      render(
        <RepositoryList
          items={twoItems}
          labels={labels}
          locale={locale('ja')}
          gemFacets={new Map()}
        />,
      )

      expect(screen.queryByText(labels.gemIndexUnavailableHeading)).not.toBeInTheDocument()
    })

    /**
     * ④WARNING 修正（PR #293 セルフレビュー指摘）: ranked / unranked の境界がページ境界と
     * 一致すると（このページの先頭要素が unranked）、従来の `dividerIndex`（`idx > 0` 条件）
     * では区切り見出しが 1 度も出ない。呼び出し側から「前のページに Gem Index を持つ結果が
     * あった」ことを `unrankedContinuedFromPreviousPage` で渡せば idx===0 でも区切りを出せる。
     */
    describe('unrankedContinuedFromPreviousPage（④・ページ境界での区切り欠落対策）', () => {
      const allUnranked: RepositorySummary[] = [
        {
          id: 3,
          fullName: 'octostub/unranked-only-a',
          name: 'unranked-only-a',
          owner: { login: 'octostub', avatarUrl: 'https://avatars.githubusercontent.com/u/3?v=4' },
          description: null,
          primaryLanguage: null,
          stars: 5,
          lastPushedAt: new Date('2026-08-18T09:00:00Z'),
          topics: [],
          htmlUrl: 'https://github.com/octostub/unranked-only-a',
        },
        {
          id: 4,
          fullName: 'octostub/unranked-only-b',
          name: 'unranked-only-b',
          owner: { login: 'octostub', avatarUrl: 'https://avatars.githubusercontent.com/u/4?v=4' },
          description: null,
          primaryLanguage: null,
          stars: 6,
          lastPushedAt: new Date('2026-08-18T09:00:00Z'),
          topics: [],
          htmlUrl: 'https://github.com/octostub/unranked-only-b',
        },
      ]

      it('true を渡すと、全件 unranked のページでも先頭に区切り見出しを 1 本だけ出す', () => {
        render(
          <RepositoryList
            items={allUnranked}
            labels={labels}
            locale={locale('ja')}
            gemFacets={new Map()}
            unrankedContinuedFromPreviousPage
          />,
        )

        expect(screen.getAllByText(labels.gemIndexUnavailableHeading)).toHaveLength(1)
        // 区切りは先頭要素の直前（= 最初のカードより上）に出る。
        const list = screen.getByRole('link', { name: /octostub\/unranked-only-a/ }).closest('ul')
        const children = list ? Array.from(list.children) : []
        expect(children[0]).toHaveTextContent(labels.gemIndexUnavailableHeading)
      })

      it('省略時（既定 undefined）は全件 unranked のページで区切りを出さない（回帰なし）', () => {
        render(
          <RepositoryList
            items={allUnranked}
            labels={labels}
            locale={locale('ja')}
            gemFacets={new Map()}
          />,
        )

        expect(screen.queryByText(labels.gemIndexUnavailableHeading)).not.toBeInTheDocument()
      })

      it('false を渡した場合も区切りを出さない', () => {
        render(
          <RepositoryList
            items={allUnranked}
            labels={labels}
            locale={locale('ja')}
            gemFacets={new Map()}
            unrankedContinuedFromPreviousPage={false}
          />,
        )

        expect(screen.queryByText(labels.gemIndexUnavailableHeading)).not.toBeInTheDocument()
      })

      it('true でも先頭要素が facet を持つ（ranked）場合は区切りを出さない', () => {
        const allRanked = new Map([
          ['octostub/unranked-only-a', { gemIndex: gemIndex(-0.1), dependentCount: 1 }],
          ['octostub/unranked-only-b', { gemIndex: gemIndex(-0.2), dependentCount: 2 }],
        ])
        render(
          <RepositoryList
            items={allUnranked}
            labels={labels}
            locale={locale('ja')}
            gemFacets={allRanked}
            unrankedContinuedFromPreviousPage
          />,
        )

        expect(screen.queryByText(labels.gemIndexUnavailableHeading)).not.toBeInTheDocument()
      })

      it('idx>0 の既存の境界検出（前ページ非依存）と共存する', () => {
        render(
          <RepositoryList
            items={twoItems}
            labels={labels}
            locale={locale('ja')}
            gemFacets={facetMap()}
            unrankedContinuedFromPreviousPage={false}
          />,
        )

        expect(screen.getAllByText(labels.gemIndexUnavailableHeading)).toHaveLength(1)
      })
    })

    it('fullName の大文字小文字が違っても突合できる（gemFacetKey の小文字化）', () => {
      const mixedCaseItems: RepositorySummary[] = [
        { ...twoItems[0], fullName: 'Octostub/Ranked-One' },
      ]
      render(
        <RepositoryList
          items={mixedCaseItems}
          labels={labels}
          locale={locale('ja')}
          gemFacets={facetMap()}
        />,
      )

      expect(screen.getByText(/-0\.42/)).toBeInTheDocument()
    })
  })
})
