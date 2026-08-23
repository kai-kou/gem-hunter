import { isValidElement, type ReactElement, type ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { RateLimitExceededError } from '@/src/domain/errors'
import type { SearchGemsResult } from '@/src/usecases/search-gems'
import { ErrorNotice } from '@/src/ui/error-notice'
import { FocusOnNavigate } from '@/src/ui/focus-on-navigate'
import { GemList, GEM_LIST_HEADING_ID } from '@/src/ui/gem-list'
import GemListPage from './page'

/**
 * Gem 一覧（`/{locale}/gems`）のレート制限配線（Issue #442 / `NFR-7`）を固定するテスト。
 *
 * 🔴 **なぜ E2E ではなくここで検証するのか**（`testing-strategy.md` §3 は `async` Server
 * Component を E2E の担当としている）: レート制限は `rateLimiterBinding()` が Workers 実行環境の
 * 外では `undefined` を返す＝フェイルオープンする設計（`src/composition/rate-limit.ts`）なので、
 * **Playwright ではこの分岐に到達できない**。一方で本ファイルが固定する 4 点は「配線の順序と
 * 条件」であり、描画結果ではない。検索経路（`app/api/search/route.test.ts:293,304,319`）が同じ
 * 主張を実測で固定しているのに、画面側だけコメントの宣言で済ませている非対称を解消する。
 *
 * 🔵 **検査の方式**: `render()`（RTL）は使わず、**ページ関数を直接 `await` して返り値の React
 * 要素ツリーを検査する**。`async` Server Component は RTL が公式に非対応（§1）だが、返り値は
 * 「未描画の要素ツリー」なので、子コンポーネント（`ErrorNotice` 等）は **型と props をそのまま
 * 保持したまま** 現れる。つまり `retryHref` のような配線の結果を DOM を介さず直接読める
 * （描画を試みないため §3 の「ユニットで描画しようとしない」に抵触しない）。文言・見た目の検証は
 * 引き続き各コンポーネントのテスト（`src/ui/*.test.tsx`）と E2E の担当。
 */

const enforceGemListRateLimitMock = vi.fn<(headers: Headers) => Promise<void>>()
vi.mock('@/src/composition/rate-limit', () => ({
  enforceGemListRateLimit: (...args: [Headers]) => enforceGemListRateLimitMock(...args),
}))

/**
 * 候補プールの読み込み（静的アセット）を避けるため composition root ごと差し替える。
 * 🔴 呼び出し順の比較に使うのは **内側の `searchGemsMock`**（実際に検索が走った時点）であって、
 * ファクトリ（`searchGemsUseCase`）ではない。
 */
const searchGemsMock = vi.fn<() => Promise<SearchGemsResult>>()
vi.mock('@/src/composition/container', () => ({
  searchGemsUseCase:
    () =>
    (...args: unknown[]) =>
      searchGemsMock(...(args as [])),
}))

vi.mock('@/src/composition/auth', () => ({
  getSessionAccessToken: async () => null,
  isAuthConfigured: () => false,
}))

// `headers()` は Workers/Next のリクエストスコープでしか動かないため空の `Headers` を返す。
// 中身はモックした `enforceGemListRateLimit` が受け取るだけで、判定には使われない。
vi.mock('next/headers', () => ({
  headers: async () => new Headers(),
}))

/** 検索が成功した最小の結果（本ファイルは配線だけを見るので中身は空でよい）。 */
function okResult(): SearchGemsResult {
  return {
    status: 'ok',
    items: [],
    totalCount: 0,
    effectivePage: 1,
    usedTokens: ['react'],
    relaxed: false,
    unmatchableQuery: false,
    includedCount: 0,
    meta: {
      source: 'Ecosyste.ms',
      sourceUrl: 'https://ecosyste.ms/',
      license: 'CC BY-SA 4.0',
      sourceLicenseUrl: 'https://creativecommons.org/licenses/by-sa/4.0/',
      generatedAt: '2026-08-01T00:00:00.000Z',
    },
  }
}

function renderPage(searchParams: Record<string, string>) {
  return GemListPage({
    params: Promise.resolve({ locale: 'ja' }),
    searchParams: Promise.resolve(searchParams),
  })
}

/**
 * 返り値の要素ツリーを深さ優先で平坦化する。未描画のツリーなので、子コンポーネントは
 * 「型 + props」のまま列挙され、`element.type === ErrorNotice` で同定できる。
 */
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
  enforceGemListRateLimitMock.mockReset()
  enforceGemListRateLimitMock.mockResolvedValue(undefined)
  searchGemsMock.mockReset()
  searchGemsMock.mockResolvedValue(okResult())
})

describe('GemListPage — レート制限の配線（Issue #442 / NFR-7）', () => {
  it('検索語なし（`gems.queryRequired` へ倒れる入力）では枠を消費しない', async () => {
    const tree = await renderPage({ q: '   ' })

    expect(enforceGemListRateLimitMock).not.toHaveBeenCalled()
    // 候補プールの読み込みにも進まない（早期 return）。
    expect(searchGemsMock).not.toHaveBeenCalled()
    // 受け口（フォーカス移動先）はこの分岐にも存在する（`NFR-12`）。
    const heading = flatten(tree).find((element) => element.type === 'h2')
    expect(heading?.props).toMatchObject({ id: GEM_LIST_HEADING_ID, tabIndex: -1 })
  })

  it('正常時は enforceGemListRateLimit が 1 回だけ、かつ検索より先に呼ばれる', async () => {
    const tree = await renderPage({ q: 'react' })

    expect(enforceGemListRateLimitMock).toHaveBeenCalledTimes(1)
    expect(searchGemsMock).toHaveBeenCalledTimes(1)
    // 🔴 「重い処理の前で判定する」という配線の主張そのもの（順序が逆だと間引きの意味がない）。
    expect(enforceGemListRateLimitMock.mock.invocationCallOrder[0]).toBeLessThan(
      searchGemsMock.mock.invocationCallOrder[0] as number,
    )
    expect(findByType(tree, GemList)).toBeDefined()
  })

  it('超過（RateLimitExceededError）時は検索へ進まず、再試行リンク付きの ErrorNotice を出す', async () => {
    enforceGemListRateLimitMock.mockRejectedValue(
      new RateLimitExceededError('rateLimitSecondary', { retryAfterSeconds: 60 }),
    )

    const tree = await renderPage({ q: 'react', page: '3' })

    expect(searchGemsMock).not.toHaveBeenCalled()
    const notice = findByType(tree, ErrorNotice)
    expect(notice).toBeDefined()
    // 再試行先は「いま弾かれた URL」＝検索語とページ番号を保持している（`US-24`）。
    const { retryHref } = notice?.props as { retryHref: string }
    expect(retryHref).toContain('q=react')
    expect(retryHref).toContain('page=3')
    // エラー分岐でもフォーカスの行き先が消えない（受け口 + 移動役が揃っている・`NFR-12`）。
    const heading = flatten(tree).find((element) => element.type === 'h2')
    expect(heading?.props).toMatchObject({ id: GEM_LIST_HEADING_ID, tabIndex: -1 })
    expect((findByType(tree, FocusOnNavigate)?.props as { targetId: string }).targetId).toBe(
      GEM_LIST_HEADING_ID,
    )
  })

  it('レート制限以外の例外は握り潰さずそのまま投げ直す', async () => {
    enforceGemListRateLimitMock.mockRejectedValue(new Error('headers() が使えない実行環境'))

    await expect(renderPage({ q: 'react' })).rejects.toThrow('headers() が使えない実行環境')
    expect(searchGemsMock).not.toHaveBeenCalled()
  })
})
