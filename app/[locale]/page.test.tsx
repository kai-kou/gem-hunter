import { isValidElement, type ReactElement, type ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { RateLimitExceededError } from '@/src/domain/errors'
import type { SearchResult } from '@/src/domain/model/repository'
import { DailyDigest } from '@/src/ui/daily-digest'
import { ErrorNotice } from '@/src/ui/error-notice'
import { SearchForm } from '@/src/ui/search-form'
import type { ErrorPresentation } from '@/src/ui/i18n/error-message'
import LocaleHome from './page'

/**
 * 検索結果一覧（`/{locale}`）の `showAuthLink`（= `isAuthConfigured()`）配線（Issue #365 / #549）を
 * 固定するテスト。
 *
 * 🔴 **なぜここで検証するのか**（`testing-strategy.md` §3 は `async` Server Component を
 * E2E の担当としている）: GitHub Issue #629 / #681（未解決・lessons 未昇格）のとおりこの実行環境では
 * Playwright がブラウザ不一致で全滅するため、E2E での担保が取れない。一方 `toErrorPresentation()`
 * の呼び出し元（本ファイル）に `isAuthConfigured` を配線し忘れても、純関数テスト
 * （`error-message.test.ts`）は呼び出し元の配線ミスを検知しない。`app/[locale]/gems/page.test.tsx`
 * と同じ検査方式（未描画の要素ツリーを直接検査）で配線だけを固定する。
 *
 * 🔵 **検査の方式**: `LocaleHome()` を直接 `await` して返り値の要素ツリーを取得する（RTL は使わない・
 * `async` Server Component は非対応）。エラー描画自体は `LocaleHome` の内側にネストした
 * `async` 関数コンポーネント `SearchBody`（非 export）が担うため、ツリーから `SearchBody` 要素を
 * 関数名で同定し、`element.type(element.props)` として **直接呼び出す**（React に描画させず、
 * ただの関数呼び出しとして評価する）。これにより 2 段目の要素ツリーを取得でき、`ErrorNotice` の
 * `presentation` を DOM を介さず直接読める。
 */

vi.mock('@/src/composition/auth', () => ({
  getSessionAccessToken: async () => null,
  isAuthConfigured: () => isAuthConfiguredMock(),
}))
const isAuthConfiguredMock = vi.fn<() => boolean>()

/**
 * 候補プールの読み込み（静的アセット）を避けるため composition root ごと差し替える
 * （`gems/page.test.tsx` と同じ方針）。エラー分岐では `lookupGemIndexes` /
 * `getDailyDigestUseCase` は呼ばれないため中身は空でよい。
 */
const searchRepositoriesMock = vi.fn<() => Promise<SearchResult>>()
const getDailyDigestMock = vi.fn<() => Promise<unknown>>()
vi.mock('@/src/composition/container', () => ({
  DAILY_DIGEST_LIMIT: 5,
  getDailyDigestUseCase: () => () => getDailyDigestMock(),
  lookupGemIndexes: async () => new Map(),
  searchRepositoriesUseCase:
    () =>
    (...args: unknown[]) =>
      searchRepositoriesMock(...(args as [])),
}))

// `headers()` は Workers/Next のリクエストスコープでしか動かないため空の `Headers` を返す
// （`prepareSearchKeyword` 経由の自リクエスト間引きはローカル実行ではフェイルオープンする）。
vi.mock('next/headers', () => ({
  headers: async () => new Headers(),
}))

function renderPage(searchParams: Record<string, string>) {
  return LocaleHome({
    params: Promise.resolve({ locale: 'ja' }),
    searchParams: Promise.resolve(searchParams),
  })
}

/** 返り値の要素ツリーを深さ優先で平坦化する（`gems/page.test.tsx` と同じ実装）。 */
function flatten(node: ReactNode): ReactElement[] {
  if (Array.isArray(node)) {
    return node.flatMap(flatten)
  }
  if (!isValidElement(node)) {
    return []
  }
  const { children } = node.props as { children?: ReactNode }
  return [node, ...flatten(children)]
}

function findByType(tree: ReactNode, type: unknown): ReactElement | undefined {
  return flatten(tree).find((element) => element.type === type)
}

/**
 * `LocaleHome` の返り値には、エラー描画を担う `async` 関数コンポーネント `SearchBody`（非 export）が
 * **未評価の要素** として現れる（`element.type` は関数そのもの・`element.props` は渡された props）。
 * 関数名で同定し、React に描画させず直接呼び出すことで 2 段目のツリーを取得する。
 */
async function renderSearchBody(tree: ReactNode): Promise<ReactNode> {
  const searchBodyElement = flatten(tree).find(
    (element) => typeof element.type === 'function' && element.type.name === 'SearchBody',
  )
  if (searchBodyElement === undefined) {
    throw new Error('SearchBody 要素が見つからない（page.tsx の構造が変わった可能性がある）')
  }
  const componentFn = searchBodyElement.type as (props: unknown) => Promise<ReactNode>
  return componentFn(searchBodyElement.props)
}

beforeEach(() => {
  isAuthConfiguredMock.mockReset()
  isAuthConfiguredMock.mockReturnValue(false)
  getDailyDigestMock.mockReset()
  getDailyDigestMock.mockResolvedValue(null)
  searchRepositoriesMock.mockReset()
  searchRepositoriesMock.mockRejectedValue(
    new RateLimitExceededError('rateLimitPrimary', {
      retryAfter: new Date('2026-08-30T00:00:00Z'),
    }),
  )
})

describe('LocaleHome — showAuthLink の配線（Issue #365 / #549）', () => {
  it('isAuthConfigured() が true のとき、一次レート制限エラーに loginHint が付く', async () => {
    isAuthConfiguredMock.mockReturnValue(true)

    const tree = await renderPage({ q: 'react' })
    const searchBodyTree = await renderSearchBody(tree)

    const notice = findByType(searchBodyTree, ErrorNotice)
    expect(notice).toBeDefined()
    const props = notice?.props as {
      presentation: ErrorPresentation
      loginHref?: string
      loginLabel?: string
    }
    expect(props.presentation.loginHint).toBeDefined()
    expect(props.loginHref).toBe('/api/auth/login')
    expect(props.loginLabel).toBeDefined()
  })

  it('isAuthConfigured() が false のとき、一次レート制限エラーに loginHint が付かない', async () => {
    isAuthConfiguredMock.mockReturnValue(false)

    const tree = await renderPage({ q: 'react' })
    const searchBodyTree = await renderSearchBody(tree)

    const notice = findByType(searchBodyTree, ErrorNotice)
    expect(notice).toBeDefined()
    const props = notice?.props as {
      presentation: ErrorPresentation
      loginHref?: string
      loginLabel?: string
    }
    expect(props.presentation.loginHint).toBeUndefined()
    expect(props.loginHref).toBeUndefined()
    expect(props.loginLabel).toBeUndefined()
  })
})

/**
 * 日次ダイジェスト経路の失敗が **トップページ全体を 500 にしない** ことを固定する（Issue #392）。
 *
 * 契約: `GemDigestPort` は例外を投げない設計だが、投げた場合は usecase が `null` に畳み、
 * ページは **ダイジェスト部分だけを欠落させて** 描画を完了する（`app/` 配下に `error.tsx` は
 * 無いため、ここで漏らすと既存の検索機能まで巻き添えで 500 になる）。
 */
describe('LocaleHome — 日次ダイジェストの失敗がトップページを 500 にしない（Issue #392）', () => {
  it('ダイジェスト取得が reject してもページ描画は成功し、ダイジェストは描画されない', async () => {
    getDailyDigestMock.mockRejectedValue(new Error('digest boom'))

    // reject すればここで throw する（= 500 相当）。resolve すること自体が本テストの主張。
    const tree = await renderPage({})

    expect(findByType(tree, DailyDigest)).toBeUndefined()
    // ページの他の部分（検索フォーム）は生きている（ダイジェストだけが欠落する）。
    expect(findByType(tree, SearchForm)).toBeDefined()
  })

  it('ダイジェストが取得できたときは描画される（上のテストの対・欠落の意味を固定する）', async () => {
    getDailyDigestMock.mockResolvedValue({
      date: '20260820',
      items: [],
      meta: {
        source: 'Ecosyste.ms',
        sourceUrl: 'https://ecosyste.ms/',
        license: 'CC BY-SA 4.0',
        sourceLicenseUrl: 'https://creativecommons.org/licenses/by-sa/4.0/',
        generatedAt: '2026-08-20T00:00:00Z',
      },
    })

    const tree = await renderPage({})

    expect(findByType(tree, DailyDigest)).toBeDefined()
  })
})
