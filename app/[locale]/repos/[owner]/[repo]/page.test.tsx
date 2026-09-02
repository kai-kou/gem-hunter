import { isValidElement, type ReactElement, type ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { RateLimitExceededError } from '@/src/domain/errors'
import { ErrorNotice } from '@/src/ui/error-notice'
import type { ErrorPresentation } from '@/src/ui/i18n/error-message'
import RepositoryDetailPage from './page'

/**
 * リポジトリ詳細（`/{locale}/repos/{owner}/{repo}`）の `showAuthLink`（= `isAuthConfigured()`）配線
 * （Issue #365 / #549）を固定するテスト。検査方式・E2E を使わない理由は
 * `app/[locale]/page.test.tsx` の JSDoc と同じ（#629 / #681 によりこの実行環境では Playwright が
 * 全滅する）。本ページはエラー描画が `RepositoryDetailPage` 自身の返り値に直接現れる
 * （`app/[locale]/page.tsx` と異なりネストした `async` 子コンポーネントを経由しない）ため、
 * `app/[locale]/gems/page.test.tsx` と同じ 1 段の要素ツリー検査で足りる。
 */

vi.mock('@/src/composition/auth', () => ({
  getSessionAccessToken: async () => null,
  isAuthConfigured: () => isAuthConfiguredMock(),
}))
const isAuthConfiguredMock = vi.fn<() => boolean>()

const getRepositoryDetailMock = vi.fn<() => Promise<unknown>>()
vi.mock('@/src/composition/container', () => ({
  getRepositoryDetailUseCase:
    () =>
    (...args: unknown[]) =>
      getRepositoryDetailMock(...(args as [])),
  // エラー分岐では README 取得まで到達しないため中身は空でよい。
  getRepositoryReadmeUseCase: () => async () => null,
}))

// Issue #190: 詳細取得のレート制限配線。`app/[locale]/gems/page.test.tsx` と同じ検査方式
// （配線の順序・条件を返り値の要素ツリーで確かめる。理由は同ファイルの JSDoc を参照）。
const enforceDetailRateLimitMock = vi.fn<(headers: Headers) => Promise<void>>()
vi.mock('@/src/composition/rate-limit', () => ({
  enforceDetailRateLimit: (...args: [Headers]) => enforceDetailRateLimitMock(...args),
}))

// `headers()` は Workers/Next のリクエストスコープでしか動かないため空の `Headers` を返す。
// 中身はモックした `enforceDetailRateLimit` が受け取るだけで、判定には使われない。
vi.mock('next/headers', () => ({
  headers: async () => new Headers(),
}))

function renderPage(owner: string, repo: string) {
  return RepositoryDetailPage({
    params: Promise.resolve({ locale: 'ja', owner, repo }),
    searchParams: Promise.resolve({}),
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

beforeEach(() => {
  isAuthConfiguredMock.mockReset()
  isAuthConfiguredMock.mockReturnValue(false)
  getRepositoryDetailMock.mockReset()
  getRepositoryDetailMock.mockRejectedValue(
    new RateLimitExceededError('rateLimitPrimary', {
      retryAfter: new Date('2026-08-30T00:00:00Z'),
    }),
  )
  enforceDetailRateLimitMock.mockReset()
  enforceDetailRateLimitMock.mockResolvedValue(undefined)
})

describe('RepositoryDetailPage — showAuthLink の配線（Issue #365 / #549）', () => {
  it('isAuthConfigured() が true のとき、一次レート制限エラーに loginHint が付く', async () => {
    isAuthConfiguredMock.mockReturnValue(true)

    const tree = await renderPage('facebook', 'react')

    const notice = findByType(tree, ErrorNotice)
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

    const tree = await renderPage('facebook', 'react')

    const notice = findByType(tree, ErrorNotice)
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

describe('RepositoryDetailPage — 詳細取得のレート制限配線（Issue #190）', () => {
  it('正常時は enforceDetailRateLimit が 1 回だけ、かつ取得より先に呼ばれる', async () => {
    getRepositoryDetailMock.mockResolvedValue({
      fullName: 'facebook/react',
      htmlUrl: 'https://github.com/facebook/react',
    })

    await renderPage('facebook', 'react')

    expect(enforceDetailRateLimitMock).toHaveBeenCalledTimes(1)
    expect(getRepositoryDetailMock).toHaveBeenCalledTimes(1)
    // 🔴 「重い処理（GitHub API 呼び出し）の前で判定する」という配線の主張そのもの
    //    （順序が逆だと間引きの意味がない）。
    expect(enforceDetailRateLimitMock.mock.invocationCallOrder[0]).toBeLessThan(
      getRepositoryDetailMock.mock.invocationCallOrder[0] as number,
    )
  })

  it('超過（RateLimitExceededError）時は取得へ進まず、ローカライズ済みの ErrorNotice を出す', async () => {
    enforceDetailRateLimitMock.mockRejectedValue(
      new RateLimitExceededError('rateLimitSecondary', { retryAfterSeconds: 60 }),
    )

    const tree = await renderPage('facebook', 'react')

    // 詳細取得（getRepositoryDetailUseCase）自体は呼ばれない（レート制限が先に弾く）。
    expect(getRepositoryDetailMock).not.toHaveBeenCalled()
    const notice = findByType(tree, ErrorNotice)
    expect(notice).toBeDefined()
    const props = notice?.props as { presentation: ErrorPresentation; retryHref?: string }
    // 一次（`rateLimitPrimary`）と異なる二次レート制限の文言が既存の `toErrorPresentation`
    // 経由で組み立てられている（新しい表示分岐を増やさず既存のエラー処理へ合流している証拠）。
    expect(props.presentation.message).toBeDefined()
    expect(props.presentation.loginHint).toBeUndefined()
    // 再試行先はいま弾かれた詳細 URL（`US-24`）。
    expect(props.retryHref).toContain('/repos/facebook/react')
  })

  it('レート制限以外の例外は握り潰さずそのまま投げ直す', async () => {
    enforceDetailRateLimitMock.mockRejectedValue(new Error('headers() が使えない実行環境'))

    await expect(renderPage('facebook', 'react')).rejects.toThrow('headers() が使えない実行環境')
    expect(getRepositoryDetailMock).not.toHaveBeenCalled()
  })
})
