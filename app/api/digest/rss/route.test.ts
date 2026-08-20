import { beforeEach, describe, expect, it, vi } from 'vitest'

import { gemIndex } from '@/src/domain/model/gem-index'
import type { DailyDigest } from '@/src/domain/model/gem'
import { GET } from './route'

/**
 * `getDailyDigestUseCase()`（composition root）をモックし、実際の候補プール JSON /
 * 日付シードのシャッフルに依存せず決定論的に検証する。
 */
const getDailyDigestMock = vi.fn()
vi.mock('@/src/composition/container', () => ({
  getDailyDigestUseCase: () => getDailyDigestMock,
}))

function makeDigest(): DailyDigest {
  return {
    date: '20260820' as DailyDigest['date'],
    items: [
      {
        packageName: 'left-pad',
        repositoryFullName: 'left-pad-owner/left-pad',
        dependentCount: 100,
        stars: 5,
        gemIndex: gemIndex(-10),
      },
    ],
    meta: {
      source: 'Ecosyste.ms',
      license: 'CC BY-SA 4.0',
      sourceLicenseUrl: 'https://creativecommons.org/licenses/by-sa/4.0/',
      generatedAt: '2026-08-20T00:00:00.000Z',
    },
  }
}

describe('GET /api/digest/rss', () => {
  beforeEach(() => {
    getDailyDigestMock.mockReset()
  })

  it('200 で RSS 2.0 の content-type を返す', async () => {
    getDailyDigestMock.mockResolvedValue(makeDigest())

    const response = await GET(new Request('https://gem-hunter.example.com/api/digest/rss'))

    expect(response.status).toBe(200)
    expect(response.headers.get('content-type')).toBe('application/rss+xml; charset=utf-8')
  })

  it('本文に RSS ルート要素とダイジェストの packageName を含む', async () => {
    getDailyDigestMock.mockResolvedValue(makeDigest())

    const response = await GET(new Request('https://gem-hunter.example.com/api/digest/rss'))
    const body = await response.text()

    expect(body).toContain('<rss version="2.0">')
    expect(body).toContain('<title>left-pad</title>')
    expect(body).toContain(
      '<link>https://gem-hunter.example.com/ja/repos/left-pad-owner/left-pad</link>',
    )
  })

  it('トップページと同じ limit（5 件）を usecase へ渡す', async () => {
    getDailyDigestMock.mockResolvedValue(makeDigest())

    await GET(new Request('https://gem-hunter.example.com/api/digest/rss'))

    expect(getDailyDigestMock).toHaveBeenCalledWith(
      expect.objectContaining({ limit: 5 }),
    )
  })

  it('許可ホストが設定されているとき、偽装 Host は許可ホストへ丸められる（cache poisoning 対策）', async () => {
    // `resolveLandingHost()` は `GITHUB_OAUTH_CALLBACK_URL` から許可ホストを導出する
    // （`src/composition/auth.ts`）。設定済みの状態で偽装 Host を送っても、RSS の
    // <link> / <guid> には許可ホストが入る（`app/api/auth/callback/route.ts` と同じ方針）。
    vi.stubEnv('GITHUB_OAUTH_CALLBACK_URL', 'https://gem-hunter.example/api/auth/callback')
    getDailyDigestMock.mockResolvedValue(makeDigest())

    const response = await GET(new Request('https://evil.example/api/digest/rss'))
    const body = await response.text()

    expect(body).toContain('<link>https://gem-hunter.example</link>')
    expect(body).not.toContain('evil.example')

    vi.unstubAllEnvs()
  })

  it('usecase が例外を投げても 500 にせず空の RSS を返す', async () => {
    getDailyDigestMock.mockRejectedValue(new Error('候補プール読み込み失敗'))

    const response = await GET(new Request('https://gem-hunter.example.com/api/digest/rss'))
    const body = await response.text()

    expect(response.status).toBe(200)
    expect(body).toContain('<rss version="2.0">')
    expect(body.match(/<item>/g)).toBeNull()
  })
})
