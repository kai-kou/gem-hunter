import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { DigestMeta, GemPoolEntry } from '../domain/model/gem'
import { gemIndex } from '../domain/model/gem-index'
import { locale } from '../domain/model/locale'
import type { GemPoolSearchResult } from '../domain/ports/gem-index-port'
import { GemList, type GemListLabels } from './gem-list'

const labels: GemListLabels = {
  heading: '「{query}」の Gem',
  empty:
    'この検索語に一致する Gem はありませんでした。この一覧は 12 のパッケージレジストリの被依存数上位から作った限定的な候補プールが対象です。ここに載らないことは評価が低いことを意味しません。',
  relaxedNotice: 'すべての語では見つからなかったため、「{token}」だけで絞り込みました。',
  totalCount: '{count} 件',
  starCount: 'star 数',
  dependentCount: '被依存パッケージ数',
  gemIndexLabel: 'Gem Index',
  registryLabel: 'レジストリ',
  attribution: 'このデータについて: {source}（{license}）のオープンデータをもとにしています。',
}

const meta: DigestMeta = {
  source: 'Ecosyste.ms',
  sourceUrl: 'https://ecosyste.ms/',
  license: 'CC BY-SA 4.0',
  sourceLicenseUrl: 'https://creativecommons.org/licenses/by-sa/4.0/',
  generatedAt: '2026-08-20T00:00:00Z',
}

const entries: GemPoolEntry[] = [
  {
    packageName: 'left-pad',
    repositoryFullName: 'stevemao/left-pad',
    dependentCount: 12345,
    stars: 1234,
    gemIndex: gemIndex(-42.55),
    registry: 'npmjs.org',
  },
]

function resultOf(overrides: Partial<GemPoolSearchResult> = {}): GemPoolSearchResult {
  return {
    items: entries,
    totalCount: entries.length,
    usedTokens: ['pad'],
    relaxed: false,
    meta,
    ...overrides,
  }
}

describe('GemList', () => {
  it('検索語入りの見出しを出す（{query} を置換する）', () => {
    render(<GemList result={resultOf()} query="left pad" locale={locale('ja')} labels={labels} />)

    expect(screen.getByRole('heading', { name: '「left pad」の Gem' })).toBeInTheDocument()
  })

  it('各行にリポジトリ名・パッケージ名・レジストリ・star 数・被依存数・Gem Index を出す', () => {
    render(<GemList result={resultOf()} query="pad" locale={locale('ja')} labels={labels} />)

    const row = screen.getByRole('listitem')
    expect(within(row).getByRole('link', { name: /stevemao\/left-pad/ })).toBeInTheDocument()
    expect(within(row).getByText('left-pad')).toBeInTheDocument()
    expect(within(row).getByText(/npmjs\.org/)).toBeInTheDocument()
    expect(within(row).getByText('1,234')).toBeInTheDocument()
    expect(within(row).getByText('12,345')).toBeInTheDocument()
    // Gem Index は小数 1 桁に丸めて出す（-42.55 → -42.6 / -42.5 のどちらでも 1 桁であること）
    expect(within(row).getByText(/-42\.[56]/)).toBeInTheDocument()
    // sr-only ラベル（数値だけでは意味が伝わらない）
    expect(within(row).getByText('star 数', { exact: false })).toBeInTheDocument()
    expect(within(row).getByText('被依存パッケージ数', { exact: false })).toBeInTheDocument()
  })

  it('各行に生値の data 属性を出す（E2E が並び順を表記ゆれ無しで検証できるようにする）', () => {
    render(<GemList result={resultOf()} query="pad" locale={locale('ja')} labels={labels} />)

    const row = screen.getByRole('listitem')
    expect(row).toHaveAttribute('data-gem-index', '-42.55')
    expect(row).toHaveAttribute('data-repository-full-name', 'stevemao/left-pad')
    // 一覧はトップレベルに 1 本だけ（E2E が `:scope > li` で件数を取る前提）
    expect(screen.getAllByRole('list')).toHaveLength(1)
  })

  it('総件数を表示する（ページネーション UI は持たない）', () => {
    render(
      <GemList
        result={resultOf({ totalCount: 1234 })}
        query="pad"
        locale={locale('ja')}
        labels={labels}
      />,
    )

    expect(screen.getByText('1,234 件')).toBeInTheDocument()
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument()
  })

  it('詳細リンクは /{locale}/repos/{owner}/{name} で始まり、戻り先クエリを持つ', () => {
    render(<GemList result={resultOf()} query="left pad" locale={locale('ja')} labels={labels} />)

    const href = screen.getByRole('link', { name: /stevemao\/left-pad/ }).getAttribute('href')
    expect(href).not.toBeNull()
    expect(href?.startsWith('/ja/repos/stevemao/left-pad?')).toBe(true)
    const query = new URLSearchParams(href?.split('?')[1] ?? '')
    expect(query.get('from')).toBe('gems')
    expect(query.get('q')).toBe('left pad')
  })

  it('page を渡すと戻り先クエリにページ番号も載る（既定ページなら省略する）', () => {
    const { rerender } = render(
      <GemList result={resultOf()} query="pad" locale={locale('ja')} labels={labels} page={3} />,
    )
    const href = screen.getByRole('link', { name: /stevemao\/left-pad/ }).getAttribute('href')
    expect(new URLSearchParams(href?.split('?')[1] ?? '').get('page')).toBe('3')

    rerender(
      <GemList result={resultOf()} query="pad" locale={locale('ja')} labels={labels} page={1} />,
    )
    const first = screen.getByRole('link', { name: /stevemao\/left-pad/ }).getAttribute('href')
    expect(new URLSearchParams(first?.split('?')[1] ?? '').has('page')).toBe(false)
  })

  it('repositoryFullName が owner/name 形式でないときはリンクにせずテキストで出す', () => {
    const broken: GemPoolEntry[] = [
      { ...entries[0], repositoryFullName: 'not-a-full-name', packageName: 'broken' },
    ]

    render(
      <GemList
        result={resultOf({ items: broken, totalCount: 1 })}
        query="pad"
        locale={locale('ja')}
        labels={labels}
      />,
    )

    expect(screen.getByText('not-a-full-name')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /not-a-full-name/ })).not.toBeInTheDocument()
  })

  it('0 件のときは role="status" で母集団を明示した文言を出す（role="alert" は使わない）', () => {
    render(
      <GemList
        result={resultOf({ items: [], totalCount: 0, usedTokens: [] })}
        query="pad"
        locale={locale('ja')}
        labels={labels}
      />,
    )

    expect(screen.getByRole('status')).toHaveTextContent(/限定的な候補プール/)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
  })

  it('relaxed=true のとき緩和の注記を出し、false のときは出さない', () => {
    const { rerender } = render(
      <GemList
        result={resultOf({ relaxed: true, usedTokens: ['pad'] })}
        query="left pad"
        locale={locale('ja')}
        labels={labels}
      />,
    )

    expect(screen.getByText(/「pad」だけで絞り込みました/)).toBeInTheDocument()

    rerender(
      <GemList
        result={resultOf({ relaxed: false })}
        query="left pad"
        locale={locale('ja')}
        labels={labels}
      />,
    )

    expect(screen.queryByText(/だけで絞り込みました/)).not.toBeInTheDocument()
  })

  it('帰属表示に出典元とライセンスをリンクとして出す（D-29）', () => {
    render(<GemList result={resultOf()} query="pad" locale={locale('ja')} labels={labels} />)

    expect(screen.getByRole('link', { name: 'Ecosyste.ms' })).toHaveAttribute(
      'href',
      'https://ecosyste.ms/',
    )
    expect(screen.getByRole('link', { name: 'CC BY-SA 4.0' })).toHaveAttribute(
      'href',
      'https://creativecommons.org/licenses/by-sa/4.0/',
    )
  })

  it('http(s) 以外の出典 URL はリンクにせずテキストで出す（javascript: を href に流さない）', () => {
    render(
      <GemList
        result={resultOf({
          meta: {
            ...meta,
            // 危険な URL を弾くことの回帰テスト（href へ流さないことを固定する）
            sourceUrl: 'javascript:alert(1)',
            sourceLicenseUrl: 'javascript:alert(2)',
          },
        })}
        query="pad"
        locale={locale('ja')}
        labels={labels}
      />,
    )

    expect(screen.queryByRole('link', { name: 'Ecosyste.ms' })).not.toBeInTheDocument()
    expect(screen.getByText(/Ecosyste\.ms/)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'CC BY-SA 4.0' })).not.toBeInTheDocument()
  })

  it('数値は locale に追従して整形する（en でも素の数値文字列にしない）', () => {
    render(
      <GemList
        result={resultOf()}
        query="pad"
        locale={locale('en')}
        labels={{
          ...labels,
          totalCount: '{count} results',
          heading: 'Gems for "{query}"',
        }}
      />,
    )

    const row = screen.getByRole('listitem')
    expect(within(row).getByText('12,345')).toBeInTheDocument()
    expect(within(row).queryByText('12345')).not.toBeInTheDocument()
  })
})
