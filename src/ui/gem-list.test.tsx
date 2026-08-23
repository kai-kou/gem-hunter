import { render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { DigestMeta, GemPoolEntry } from '../domain/model/gem'
import { gemIndex } from '../domain/model/gem-index'
import { locale } from '../domain/model/locale'
import { GemList, type GemListLabels, type GemListViewModel } from './gem-list'

const labels: GemListLabels = {
  heading: '「{query}」の Gem',
  empty:
    'この検索語に一致する Gem はありませんでした。この一覧は 12 のパッケージレジストリの被依存数上位から作った限定的な候補プールが対象です。ここに載らないことは評価が低いことを意味しません。',
  unmatchableQuery:
    'この検索語からは絞り込みに使える語を取り出せませんでした。照合はパッケージ名・リポジトリ名（英数字の識別子）の単語境界一致で行っています。英語のキーワードで試してみてください。',
  relaxedNotice: 'すべての語では見つからなかったため、「{token}」だけで絞り込みました。',
  totalCount: '{count} 件',
  starCount: 'star 数',
  dependentCount: '利用パッケージ数',
  gemIndexLabel: 'Gem Index',
  registryLabel: 'レジストリ',
  attribution: 'このデータについて: {source}（{license}）のオープンデータをもとにしています。',
  includedFromSearch: 'うち {count} 件は検索結果の Gem 印から同伴されました。',
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

function viewOf(overrides: Partial<GemListViewModel> = {}): GemListViewModel {
  return {
    items: entries,
    totalCount: entries.length,
    effectivePage: 1,
    relaxedToken: null,
    unmatchableQuery: false,
    includedCount: 0,
    meta,
    ...overrides,
  }
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('GemList', () => {
  it('検索語入りの見出しを出す（{query} を置換する）', () => {
    render(<GemList view={viewOf()} query="left pad" locale={locale('ja')} labels={labels} />)

    expect(screen.getByRole('heading', { name: '「left pad」の Gem' })).toBeInTheDocument()
  })

  /**
   * 🔴 ページ送り完了をフォーカス移動で伝えるための受け口（`ui-ux-guidelines.md` §7.1）。
   * `app/` 側の `FocusOnNavigate` が `getElementById` で探すため、id と `tabIndex` の両方が要る。
   */
  it('見出しはフォーカス可能な受け口（id + tabIndex=-1）を持つ', () => {
    render(<GemList view={viewOf()} query="pad" locale={locale('ja')} labels={labels} />)

    const heading = screen.getByRole('heading', { level: 2 })
    expect(heading).toHaveAttribute('id', 'gems-heading')
    expect(heading).toHaveAttribute('tabindex', '-1')
  })

  it('各行にリポジトリ名・パッケージ名・レジストリ・star 数・利用パッケージ数・Gem Index を出す', () => {
    render(<GemList view={viewOf()} query="pad" locale={locale('ja')} labels={labels} />)

    const row = screen.getByRole('listitem')
    expect(within(row).getByRole('link', { name: /stevemao\/left-pad/ })).toBeInTheDocument()
    expect(within(row).getByText('left-pad')).toBeInTheDocument()
    expect(within(row).getByText(/npmjs\.org/)).toBeInTheDocument()
    expect(within(row).getByText('1,234')).toBeInTheDocument()
    // Gem Index は小数 1 桁に丸めて出す（-42.55 → -42.6 / -42.5 のどちらでも 1 桁であること）
    expect(within(row).getByText(/-42\.[56]/)).toBeInTheDocument()
    // star は `★` の意味が言語間で伝わらないため sr-only ラベルを添える
    expect(within(row).getByText('star 数', { exact: false })).toBeInTheDocument()
  })

  /**
   * 🔴 メタ情報は可視ラベルを添える（`ui-ux-guidelines.md` §4.2）。裸の数値のままだと
   * 支援技術なしの利用者だけが「何の数値か」を読み取れない逆転が起きる。
   */
  it('利用パッケージ数は可視ラベル付きで出し、sr-only では出さない', () => {
    const { container } = render(
      <GemList view={viewOf()} query="pad" locale={locale('ja')} labels={labels} />,
    )

    expect(screen.getByText('利用パッケージ数 12,345')).toBeInTheDocument()
    const srOnlyTexts = [...container.querySelectorAll('.sr-only')].map((el) => el.textContent)
    expect(srOnlyTexts.some((text) => text?.includes('利用パッケージ数'))).toBe(false)
  })

  it('各行に生値の data 属性を出す（E2E が並び順を表記ゆれ無しで検証できるようにする）', () => {
    render(<GemList view={viewOf()} query="pad" locale={locale('ja')} labels={labels} />)

    const row = screen.getByRole('listitem')
    expect(row).toHaveAttribute('data-gem-index', '-42.55')
    expect(row).toHaveAttribute('data-repository-full-name', 'stevemao/left-pad')
    // 一覧はトップレベルに 1 本だけ（E2E が `:scope > li` で件数を取る前提）
    expect(screen.getAllByRole('list')).toHaveLength(1)
  })

  /**
   * 🔴 React の key は `repositoryFullName`（`packageName` は欠損時に空文字で埋まる仕様なので
   * 同一ページ内で衝突する）。重複 key は React が `console.error` で警告するため、
   * **警告が出ないこと** を回帰として固定する。
   */
  it('複数件を渡された順序どおりに描画し、key 重複の警告を出さない', () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const items: GemPoolEntry[] = [
      { ...entries[0], repositoryFullName: 'alpha/one', packageName: 'one' },
      { ...entries[0], repositoryFullName: 'beta/two', packageName: 'two' },
      { ...entries[0], repositoryFullName: 'gamma/three', packageName: 'three' },
    ]

    render(
      <GemList
        view={viewOf({ items, totalCount: 3 })}
        query="pad"
        locale={locale('ja')}
        labels={labels}
      />,
    )

    const rows = screen.getAllByRole('listitem')
    expect(rows.map((row) => row.getAttribute('data-repository-full-name'))).toEqual([
      'alpha/one',
      'beta/two',
      'gamma/three',
    ])
    expect(errorSpy).not.toHaveBeenCalled()
  })

  it('packageName が欠損（空文字）した同一レジストリの複数件でも key 重複の警告を出さない', () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const items: GemPoolEntry[] = [
      { ...entries[0], repositoryFullName: 'alpha/one', packageName: '' },
      { ...entries[0], repositoryFullName: 'beta/two', packageName: '' },
    ]

    render(
      <GemList
        view={viewOf({ items, totalCount: 2 })}
        query="pad"
        locale={locale('ja')}
        labels={labels}
      />,
    )

    expect(screen.getAllByRole('listitem')).toHaveLength(2)
    expect(errorSpy).not.toHaveBeenCalled()
  })

  it('総件数を表示する（ページネーション UI は持たない）', () => {
    render(
      <GemList
        view={viewOf({ totalCount: 1234 })}
        query="pad"
        locale={locale('ja')}
        labels={labels}
      />,
    )

    expect(screen.getByText('1,234 件')).toBeInTheDocument()
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument()
  })

  it('詳細リンクは /{locale}/repos/{owner}/{name} で始まり、戻り先クエリを持つ', () => {
    render(<GemList view={viewOf()} query="left pad" locale={locale('ja')} labels={labels} />)

    const href = screen.getByRole('link', { name: /stevemao\/left-pad/ }).getAttribute('href')
    expect(href).not.toBeNull()
    expect(href?.startsWith('/ja/repos/stevemao/left-pad?')).toBe(true)
    const query = new URLSearchParams(href?.split('?')[1] ?? '')
    expect(query.get('from')).toBe('gems')
    expect(query.get('q')).toBe('left pad')
    // 検索一覧専用の条件（sort / per_page）は Gem 一覧では既定値なので載らない
    expect(query.has('sort')).toBe(false)
    expect(query.has('per_page')).toBe(false)
  })

  it('effectivePage を戻り先クエリに載せる（既定ページなら省略する）', () => {
    const { rerender } = render(
      <GemList
        view={viewOf({ effectivePage: 3 })}
        query="pad"
        locale={locale('ja')}
        labels={labels}
      />,
    )
    const href = screen.getByRole('link', { name: /stevemao\/left-pad/ }).getAttribute('href')
    expect(new URLSearchParams(href?.split('?')[1] ?? '').get('page')).toBe('3')

    rerender(
      <GemList
        view={viewOf({ effectivePage: 1 })}
        query="pad"
        locale={locale('ja')}
        labels={labels}
      />,
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
        view={viewOf({ items: broken, totalCount: 1 })}
        query="pad"
        locale={locale('ja')}
        labels={labels}
      />,
    )

    expect(screen.getByText('not-a-full-name')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /not-a-full-name/ })).not.toBeInTheDocument()
  })

  /**
   * 🔴 `encodeURIComponent` はドットをエスケープしないため、`../x` を素通しすると
   * `/ja/repos/../x` が URL 正規化で別ページへ解決され、項目名と遷移先が食い違う。
   */
  it('パス走査になりうるセグメント（. / ..）を含む値はリンクにしない', () => {
    const traversal: GemPoolEntry[] = [
      { ...entries[0], repositoryFullName: '../settings', packageName: 'evil' },
      { ...entries[0], repositoryFullName: 'owner/.', packageName: 'evil2' },
    ]

    render(
      <GemList
        view={viewOf({ items: traversal, totalCount: 2 })}
        query="pad"
        locale={locale('ja')}
        labels={labels}
      />,
    )

    expect(screen.queryAllByRole('link', { name: /settings|owner/ })).toHaveLength(0)
    expect(screen.getByText('../settings')).toBeInTheDocument()
  })

  it('0 件のときは role="status" で母集団を明示した文言を出す（role="alert" は使わない）', () => {
    render(
      <GemList
        view={viewOf({ items: [], totalCount: 0 })}
        query="pad"
        locale={locale('ja')}
        labels={labels}
      />,
    )

    expect(screen.getByRole('status')).toHaveTextContent(/限定的な候補プール/)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
  })

  /**
   * 🔴 0 件には理由が 2 つある（候補プールに載っていない / 照合自体ができなかった）。
   * 説明も次の行動も違うため、**取り違えていないこと** を両方向で固定する。
   */
  it('照合不能のときは専用の案内を出し、母集団の説明（empty）は出さない', () => {
    render(
      <GemList
        view={viewOf({ items: [], totalCount: 0, unmatchableQuery: true })}
        query="画像処理"
        locale={locale('ja')}
        labels={labels}
      />,
    )

    const status = screen.getByRole('status')
    expect(status).toHaveTextContent(/絞り込みに使える語を取り出せませんでした/)
    // 照合規則と次に取れる行動が読める（`D-37` の照合規則を利用者へ説明する）。
    expect(status).toHaveTextContent(/単語境界一致/)
    expect(status).toHaveTextContent(/英語のキーワード/)
    // 母集団の説明（候補プールに載っていない場合の文言）へすり替わっていない。
    expect(screen.queryByText(/限定的な候補プール/)).not.toBeInTheDocument()
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
  })

  it('通常の 0 件のときは母集団の説明を出し、照合不能の案内は出さない', () => {
    render(
      <GemList
        view={viewOf({ items: [], totalCount: 0, unmatchableQuery: false })}
        query="zzgemhunterzz"
        locale={locale('ja')}
        labels={labels}
      />,
    )

    expect(screen.getByRole('status')).toHaveTextContent(/限定的な候補プール/)
    expect(screen.queryByText(/絞り込みに使える語を取り出せませんでした/)).not.toBeInTheDocument()
  })

  /**
   * 🔴 「ヒットはあるがこのページには無い」は候補プール不在ではない。`empty` を出すと
   * **誤った理由** を伝えることになるため、この状態では空状態の文言を出さない。
   */
  it('ヒットはあるがページ内が空のときは 0 件の文言を出さない（誤った理由を伝えない）', () => {
    render(
      <GemList
        view={viewOf({ items: [], totalCount: 669, effectivePage: 40 })}
        query="react"
        locale={locale('ja')}
        labels={labels}
      />,
    )

    expect(screen.queryByText(/限定的な候補プール/)).not.toBeInTheDocument()
    expect(screen.queryByText(/絞り込みに使える語を取り出せませんでした/)).not.toBeInTheDocument()
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
    // 総件数は事実なので出し続ける（ページネーションは `app/` 側が描く）。
    expect(screen.getByText('669 件')).toBeInTheDocument()
  })

  /**
   * 🔴 Issue #453（案3'）: 検索結果でバッジが付いたが AND 不一致で一覧から漏れていた fullName を
   * URL 経由で同伴させたときの注記。`includedCount > 0` のときだけ出し、0 のときは出さない
   * （既存の 0 件・件数表示の `role="status"` と同時に読み上げられる二重ライブリージョンを
   * 作らないため、`relaxedNotice` と同じくこの注記自体には role を付けない）。
   */
  it('includedCount が 1 件以上のとき同伴の注記を出す', () => {
    render(
      <GemList
        view={viewOf({ includedCount: 2 })}
        query="next.js"
        locale={locale('ja')}
        labels={labels}
      />,
    )

    expect(screen.getByText('うち 2 件は検索結果の Gem 印から同伴されました。')).toBeInTheDocument()
  })

  it('includedCount が 0 のとき同伴の注記を出さない', () => {
    render(
      <GemList
        view={viewOf({ includedCount: 0 })}
        query="next.js"
        locale={locale('ja')}
        labels={labels}
      />,
    )

    expect(screen.queryByText(/同伴されました/)).not.toBeInTheDocument()
  })

  it('relaxedToken が入っているとき緩和の注記を出し、null のときは出さない', () => {
    const { rerender } = render(
      <GemList
        view={viewOf({ relaxedToken: 'pad' })}
        query="left pad"
        locale={locale('ja')}
        labels={labels}
      />,
    )

    expect(screen.getByText(/「pad」だけで絞り込みました/)).toBeInTheDocument()

    rerender(
      <GemList
        view={viewOf({ relaxedToken: null })}
        query="left pad"
        locale={locale('ja')}
        labels={labels}
      />,
    )

    expect(screen.queryByText(/だけで絞り込みました/)).not.toBeInTheDocument()
  })

  it('帰属表示に出典元とライセンスをリンクとして出す（D-29）', () => {
    render(<GemList view={viewOf()} query="pad" locale={locale('ja')} labels={labels} />)

    expect(screen.getByRole('link', { name: 'Ecosyste.ms' })).toHaveAttribute(
      'href',
      'https://ecosyste.ms/',
    )
    expect(screen.getByRole('link', { name: 'CC BY-SA 4.0' })).toHaveAttribute(
      'href',
      'https://creativecommons.org/licenses/by-sa/4.0/',
    )
  })

  /** `{generatedAt}` を含まない文言なので、生成時刻のノードは描かれない（共有実装の分岐）。 */
  it('帰属表示の文言に {generatedAt} が無いときは生成時刻を描かない', () => {
    const { container } = render(
      <GemList view={viewOf()} query="pad" locale={locale('ja')} labels={labels} />,
    )

    expect(container.querySelector('time')).toBeNull()
    expect(screen.getByText(/このデータについて/)).toBeInTheDocument()
  })

  it('http(s) 以外の出典 URL はリンクにせずテキストで出す（javascript: を href に流さない）', () => {
    render(
      <GemList
        view={viewOf({
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
        view={viewOf()}
        query="pad"
        locale={locale('en')}
        labels={{
          ...labels,
          totalCount: '{count} results',
          heading: 'Gems for "{query}"',
          dependentCount: 'Used by',
        }}
      />,
    )

    const row = screen.getByRole('listitem')
    expect(within(row).getByText('Used by 12,345')).toBeInTheDocument()
    expect(within(row).queryByText('12345')).not.toBeInTheDocument()
  })
})
