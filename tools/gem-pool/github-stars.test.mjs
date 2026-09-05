/**
 * github-stars.test.mjs — 「今日の Gem」候補の star 数取り直し層のユニットテスト（Issue #310）。
 *
 * 🔴 ネットワークを叩かない: `fetchImpl` と `sleepImpl` は必ずスタブで注入する。
 */
import { describe, expect, it, vi } from 'vitest'

import {
  DEFAULT_MAX_RETRIES,
  GITHUB_API_ORIGIN,
  fetchRepoStars,
  parseRepositoryFullName,
  refreshStars,
} from './github-stars.mjs'

/** 成功レスポンス（Response 互換の最小スタブ） */
function okResponse(body, headers = {}) {
  return { ok: true, status: 200, headers: new Headers(headers), json: async () => body }
}

/** エラーレスポンス（Response 互換の最小スタブ） */
function errorResponse(status, headers = {}) {
  return {
    ok: false,
    status,
    headers: new Headers(headers),
    json: async () => ({ message: `HTTP ${status}` }),
  }
}

/** レスポンス列（1 リクエスト目から順の配列）を返す fetch スタブを作る。 */
function makeFetchImpl(responses) {
  const calls = []
  const fetchImpl = vi.fn(async (url, init) => {
    calls.push({ url: String(url), init })
    const next = responses[calls.length - 1]
    if (next === undefined) throw new Error(`想定外の追加リクエスト: ${url}`)
    if (next instanceof Error) throw next
    return next
  })
  return { fetchImpl, calls }
}

function makeSleepImpl() {
  const waited = []
  const sleepImpl = vi.fn(async (ms) => {
    waited.push(ms)
  })
  return { sleepImpl, waited }
}

describe('parseRepositoryFullName', () => {
  it('owner/repo を分解する', () => {
    expect(parseRepositoryFullName('facebook/react')).toEqual({ owner: 'facebook', repo: 'react' })
  })

  it('スラッシュがない・複数ある・どちらかが空文字なら null', () => {
    expect(parseRepositoryFullName('facebook-react')).toBeNull()
    expect(parseRepositoryFullName('a/b/c')).toBeNull()
    expect(parseRepositoryFullName('/react')).toBeNull()
    expect(parseRepositoryFullName('facebook/')).toBeNull()
    expect(parseRepositoryFullName(123)).toBeNull()
    expect(parseRepositoryFullName(null)).toBeNull()
  })
})

describe('fetchRepoStars', () => {
  it('成功時に stargazers_count を返し、1 回だけリクエストする', async () => {
    const { fetchImpl, calls } = makeFetchImpl([okResponse({ stargazers_count: 42 })])
    const result = await fetchRepoStars({
      repositoryFullName: 'facebook/react',
      fetchImpl,
      sleepImpl: makeSleepImpl().sleepImpl,
    })
    expect(result).toEqual({ stars: 42, attempts: 1 })
    expect(calls).toHaveLength(1)
    expect(calls[0].url).toBe(`${GITHUB_API_ORIGIN}/repos/facebook/react`)
  })

  it('token を渡すと Authorization ヘッダを付ける・渡さないと付けない', async () => {
    const withToken = makeFetchImpl([okResponse({ stargazers_count: 1 })])
    await fetchRepoStars({
      repositoryFullName: 'a/b',
      fetchImpl: withToken.fetchImpl,
      token: 'ghs_dummy',
    })
    expect(withToken.calls[0].init.headers.authorization).toBe('Bearer ghs_dummy')

    const withoutToken = makeFetchImpl([okResponse({ stargazers_count: 1 })])
    await fetchRepoStars({ repositoryFullName: 'a/b', fetchImpl: withoutToken.fetchImpl })
    expect(withoutToken.calls[0].init.headers.authorization).toBeUndefined()
  })

  it('不正な repositoryFullName はネットワークへ行かず即座に失敗する', async () => {
    const { fetchImpl, calls } = makeFetchImpl([])
    await expect(fetchRepoStars({ repositoryFullName: 'not-a-repo', fetchImpl })).rejects.toThrow(
      /形式が不正/,
    )
    expect(calls).toHaveLength(0)
  })

  it('404 はリトライせず即座に失敗する（rateLimited は立たない）', async () => {
    const { fetchImpl, calls } = makeFetchImpl([errorResponse(404)])
    const sleep = makeSleepImpl()
    const err = await fetchRepoStars({
      repositoryFullName: 'ghost/repo',
      fetchImpl,
      sleepImpl: sleep.sleepImpl,
    }).catch((e) => e)
    expect(err).toBeInstanceOf(Error)
    expect(err.attempts).toBe(1)
    expect(err.rateLimited).toBeFalsy()
    expect(calls).toHaveLength(1)
    expect(sleep.waited).toEqual([])
  })

  it('primary rate limit 枯渇（x-ratelimit-remaining: 0）はリトライせず rateLimited フラグを立てる', async () => {
    const { fetchImpl, calls } = makeFetchImpl([
      errorResponse(403, { 'x-ratelimit-remaining': '0' }),
    ])
    const sleep = makeSleepImpl()
    const err = await fetchRepoStars({
      repositoryFullName: 'a/b',
      fetchImpl,
      sleepImpl: sleep.sleepImpl,
    }).catch((e) => e)
    expect(err.rateLimited).toBe(true)
    expect(err.attempts).toBe(1)
    expect(calls).toHaveLength(1)
    expect(sleep.waited).toEqual([])
  })

  it('primary rate limit 枯渇（429・x-ratelimit-remaining: 0）もリトライせず rateLimited フラグを立てる', async () => {
    // 判定は `res.status === 403 || res.status === 429` の OR 条件（実装コメント: GitHub は
    // 403/429 のどちらでも返しうる）。403 側だけテストがあり `|| res.status === 429` を削っても
    // 全緑になっていた（PR #949 セルフレビュー WARNING 指摘）。
    const { fetchImpl, calls } = makeFetchImpl([
      errorResponse(429, { 'x-ratelimit-remaining': '0' }),
    ])
    const sleep = makeSleepImpl()
    const err = await fetchRepoStars({
      repositoryFullName: 'a/b',
      fetchImpl,
      sleepImpl: sleep.sleepImpl,
    }).catch((e) => e)
    expect(err.rateLimited).toBe(true)
    expect(err.attempts).toBe(1)
    expect(calls).toHaveLength(1)
    expect(sleep.waited).toEqual([])
  })

  it('401（認証エラー）はリトライせず即座に失敗する（authError フラグを立てる）', async () => {
    const { fetchImpl, calls } = makeFetchImpl([errorResponse(401)])
    const sleep = makeSleepImpl()
    const err = await fetchRepoStars({
      repositoryFullName: 'a/b',
      fetchImpl,
      sleepImpl: sleep.sleepImpl,
    }).catch((e) => e)
    expect(err).toBeInstanceOf(Error)
    expect(err.attempts).toBe(1)
    expect(err.authError).toBe(true)
    expect(err.rateLimited).toBeFalsy()
    expect(calls).toHaveLength(1)
    expect(sleep.waited).toEqual([])
  })

  it('ネットワーク例外（fetchImpl が Error を throw）は指数バックオフでリトライし、最終的に成功する', async () => {
    const { fetchImpl, calls } = makeFetchImpl([
      new Error('ECONNRESET'),
      okResponse({ stargazers_count: 55 }),
    ])
    const sleep = makeSleepImpl()
    const result = await fetchRepoStars({
      repositoryFullName: 'a/b',
      fetchImpl,
      sleepImpl: sleep.sleepImpl,
      maxRetries: 2,
    })
    expect(result).toEqual({ stars: 55, attempts: 2 })
    expect(calls).toHaveLength(2)
    expect(sleep.waited).toEqual([500])
  })

  it('ネットワーク例外（fetchImpl が Error を throw）がリトライ回数を使い切ったら失敗する', async () => {
    const { fetchImpl, calls } = makeFetchImpl([
      new Error('ECONNRESET'),
      new Error('ETIMEDOUT'),
      new Error('ECONNRESET'),
    ])
    const sleep = makeSleepImpl()
    const err = await fetchRepoStars({
      repositoryFullName: 'a/b',
      fetchImpl,
      sleepImpl: sleep.sleepImpl,
      maxRetries: 2,
    }).catch((e) => e)
    expect(err).toBeInstanceOf(Error)
    expect(err.message).toMatch(/ECONNRESET/)
    expect(err.attempts).toBe(3)
    expect(calls).toHaveLength(3)
    expect(sleep.waited).toEqual([500, 1000])
  })

  it('secondary rate limit（403 だが remaining 0 でない）は retry-after を尊重してリトライする', async () => {
    const { fetchImpl, calls } = makeFetchImpl([
      errorResponse(403, { 'retry-after': '2' }),
      okResponse({ stargazers_count: 7 }),
    ])
    const sleep = makeSleepImpl()
    const result = await fetchRepoStars({
      repositoryFullName: 'a/b',
      fetchImpl,
      sleepImpl: sleep.sleepImpl,
      maxRetries: 2,
    })
    expect(result).toEqual({ stars: 7, attempts: 2 })
    expect(calls).toHaveLength(2)
    expect(sleep.waited).toEqual([2000])
  })

  it('5xx は指数バックオフでリトライ回数まで試し、尽きたら失敗する', async () => {
    const { fetchImpl, calls } = makeFetchImpl([
      errorResponse(500),
      errorResponse(500),
      errorResponse(500),
    ])
    const sleep = makeSleepImpl()
    const err = await fetchRepoStars({
      repositoryFullName: 'a/b',
      fetchImpl,
      sleepImpl: sleep.sleepImpl,
      maxRetries: 2,
    }).catch((e) => e)
    expect(err.attempts).toBe(3)
    expect(calls).toHaveLength(3)
    expect(sleep.waited).toEqual([500, 1000])
  })

  it('レスポンスに stargazers_count が無い/不正なら失敗として扱う', async () => {
    const { fetchImpl } = makeFetchImpl([okResponse({ full_name: 'a/b' })])
    await expect(
      fetchRepoStars({ repositoryFullName: 'a/b', fetchImpl, maxRetries: 0 }),
    ).rejects.toThrow(/stargazers_count/)
  })

  it('既定の maxRetries は DEFAULT_MAX_RETRIES', async () => {
    const responses = Array.from({ length: DEFAULT_MAX_RETRIES + 1 }, () => errorResponse(500))
    const { fetchImpl, calls } = makeFetchImpl(responses)
    await fetchRepoStars({
      repositoryFullName: 'a/b',
      fetchImpl,
      sleepImpl: makeSleepImpl().sleepImpl,
    }).catch(() => {})
    expect(calls).toHaveLength(DEFAULT_MAX_RETRIES + 1)
  })
})

describe('refreshStars（完了条件 2: 失敗してもバッチ全体を止めない）', () => {
  const candidates = [
    { repositoryFullName: 'a/one', packageName: 'one', stars: 10 },
    { repositoryFullName: 'a/two', packageName: 'two', stars: 20 },
    { repositoryFullName: 'a/three', packageName: 'three', stars: 30 },
  ]

  it('全件成功したら stars を書き換え、失敗ゼロで返す', async () => {
    const { fetchImpl } = makeFetchImpl([
      okResponse({ stargazers_count: 100 }),
      okResponse({ stargazers_count: 200 }),
      okResponse({ stargazers_count: 300 }),
    ])
    const result = await refreshStars({ candidates, fetchImpl })
    expect(result.records.map((r) => r.stars)).toEqual([100, 200, 300])
    // 他フィールドは保持する（packageName 等）
    expect(result.records[0]).toMatchObject({ repositoryFullName: 'a/one', packageName: 'one' })
    expect(result.failures).toEqual([])
    expect(result.refreshedCount).toBe(3)
    expect(result.requestCount).toBe(3)
    expect(result.rateLimited).toBe(false)
  })

  it('1 件が 404 で失敗しても、他の候補の取得を続ける（旧値を保持してスキップ）', async () => {
    const { fetchImpl } = makeFetchImpl([
      okResponse({ stargazers_count: 100 }),
      errorResponse(404),
      okResponse({ stargazers_count: 300 }),
    ])
    const result = await refreshStars({ candidates, fetchImpl })
    expect(result.records.map((r) => r.stars)).toEqual([100, 20, 300]) // 2 件目は旧値 20 のまま
    expect(result.failures).toHaveLength(1)
    expect(result.failures[0].repositoryFullName).toBe('a/two')
    expect(result.refreshedCount).toBe(2)
  })

  it('primary rate limit 枯渇を検知したら、以降の候補へネットワークリクエストを行わず旧値のままスキップする', async () => {
    const { fetchImpl, calls } = makeFetchImpl([
      okResponse({ stargazers_count: 100 }),
      errorResponse(403, { 'x-ratelimit-remaining': '0' }),
      // 3 件目のレスポンスは用意しない（呼ばれたら makeFetchImpl が例外を投げてテストが落ちる）
    ])
    const result = await refreshStars({ candidates, fetchImpl })
    expect(result.records.map((r) => r.stars)).toEqual([100, 20, 30]) // 2, 3 件目は旧値のまま
    expect(calls).toHaveLength(2) // 3 件目はネットワークへ行っていない
    expect(result.rateLimited).toBe(true)
    expect(result.failures.map((f) => f.repositoryFullName)).toEqual(['a/two', 'a/three'])
    expect(result.failures[1].message).toMatch(/スキップ/)
  })

  it('401（認証エラー）を検知したら、以降の候補へネットワークリクエストを行わず旧値のままスキップする（トークン不正はバッチ全体で恒久的なため）', async () => {
    const { fetchImpl, calls } = makeFetchImpl([
      okResponse({ stargazers_count: 100 }),
      errorResponse(401),
      // 3 件目のレスポンスは用意しない（呼ばれたら makeFetchImpl が例外を投げてテストが落ちる）
    ])
    const result = await refreshStars({ candidates, fetchImpl })
    expect(result.records.map((r) => r.stars)).toEqual([100, 20, 30]) // 2, 3 件目は旧値のまま（完了条件 2）
    expect(calls).toHaveLength(2) // 3 件目はネットワークへ行っていない
    expect(result.authError).toBe(true)
    expect(result.rateLimited).toBe(false) // 認証エラーとレート制限は別要因
    expect(result.failures.map((f) => f.repositoryFullName)).toEqual(['a/two', 'a/three'])
    expect(result.failures[1].message).toMatch(/スキップ/)
  })
})
