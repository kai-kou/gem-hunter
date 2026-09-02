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

/**
 * Issue #190 / セルフレビュー指摘 6（PR #849）: `fetchRepositoryDetail`
 * （`src/composition/detail-guard.ts`）は「自リクエスト間引き → 詳細取得」を 1 関数へ集約するが、
 * `headers`（`Headers`）は姉妹経路（`rate-limit.ts` の `enforce*RateLimit` / `search-guard.ts` の
 * `prepareSearchKeyword`）と同じく **呼び出し側（本ページ）が `await headers()` で取得して渡す**。
 * その配線の順序・条件そのものは `src/composition/detail-guard.test.ts` が固定するので、
 * 本ファイルは「ページが `fetchRepositoryDetail` の結果をどう描画するか」と、`headers()` の
 * 戻り値をそのまま渡していることだけを検査する。
 */
const fetchRepositoryDetailMock = vi.fn<() => Promise<unknown>>()
vi.mock('@/src/composition/detail-guard', () => ({
  fetchRepositoryDetail: (...args: unknown[]) => fetchRepositoryDetailMock(...(args as [])),
  // エラー分岐では README 取得まで到達しないため中身は空でよい。
  getRepositoryReadmeUseCase: () => async () => null,
}))

// `headers()` は Workers/Next のリクエストスコープでしか動かないため固定の `Headers` を返す
// （`gems/page.test.tsx` と同じ流儀）。空の `Headers` だと `new Headers()` と構造的に区別が付かず
// （どちらも entries が空）、`headers()` を経由せず素通りさせる変異を検知できない。中身を持たせ、
// `toHaveBeenCalledWith` の深い等価比較で区別できるようにする（変異テストで実測・PR #849）。
const FIXED_HEADERS = new Headers({ 'x-test-marker': 'repository-detail-page' })
vi.mock('next/headers', () => ({
  headers: async () => FIXED_HEADERS,
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
  fetchRepositoryDetailMock.mockReset()
  fetchRepositoryDetailMock.mockRejectedValue(
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

describe('RepositoryDetailPage — 詳細取得のレート制限配線（Issue #190）', () => {
  it('正常時は fetchRepositoryDetail の結果をそのまま描画する', async () => {
    fetchRepositoryDetailMock.mockResolvedValue({
      fullName: 'facebook/react',
      htmlUrl: 'https://github.com/facebook/react',
    })

    const tree = await renderPage('facebook', 'react')

    expect(fetchRepositoryDetailMock).toHaveBeenCalledTimes(1)
    expect(fetchRepositoryDetailMock).toHaveBeenCalledWith(null, FIXED_HEADERS, {
      owner: 'facebook',
      repo: 'react',
    })
    expect(findByType(tree, ErrorNotice)).toBeUndefined()
  })

  it('超過（RateLimitExceededError）時は既存の DomainError 分岐へ合流し、ローカライズ済みの ErrorNotice を出す', async () => {
    fetchRepositoryDetailMock.mockRejectedValue(
      new RateLimitExceededError('rateLimitSecondary', { retryAfterSeconds: 60 }),
    )

    const tree = await renderPage('facebook', 'react')

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
    fetchRepositoryDetailMock.mockRejectedValue(new Error('detail-guard 側の想定外の失敗'))

    await expect(renderPage('facebook', 'react')).rejects.toThrow('detail-guard 側の想定外の失敗')
  })
})
