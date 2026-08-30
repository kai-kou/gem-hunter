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
