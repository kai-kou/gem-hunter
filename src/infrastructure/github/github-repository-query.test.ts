import { HttpResponse, http } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'

import {
  AuthError,
  DomainValidationError,
  NetworkError,
  NotFoundError,
  RateLimitExceededError,
  SearchQueryRejectedError,
  UpstreamError,
} from '../../domain/errors'
import { repositoryFullName } from '../../domain/model/repository-full-name'
import { searchQuery } from '../../domain/model/search-query'
import { InMemoryCache } from '../platform/cache'
import {
  readmeEtagCacheKey,
  repositoryCacheKey,
  repositoryEtagCacheKey,
} from '../platform/cache-key'
import { CachingRepositoryQuery } from '../platform/cached-repository-query'
import detailFixture from './__fixtures__/repository-detail.json'
import fixture from './__fixtures__/search-repositories.json'
import { GithubRepositoryQuery } from './github-repository-query'

const requests: URL[] = []
const requestHeaders: Headers[] = []
const server = setupServer(
  http.get('https://api.github.com/search/repositories', ({ request }) => {
    requests.push(new URL(request.url))
    return HttpResponse.json(fixture)
  }),
  http.get('https://api.github.com/repos/:owner/:repo', ({ request }) => {
    requests.push(new URL(request.url))
    return HttpResponse.json(detailFixture)
  }),
  http.get('https://api.github.com/repos/:owner/:repo/readme', ({ request }) => {
    requests.push(new URL(request.url))
    requestHeaders.push(request.headers)
    return HttpResponse.text('<h1 id="user-content-react">React</h1>')
  }),
)

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => {
  server.resetHandlers()
  requests.length = 0
  requestHeaders.length = 0
})
afterAll(() => server.close())

function makeQuery() {
  return new GithubRepositoryQuery({ token: async () => 'ghs_dummy' })
}

describe('GithubRepositoryQuery', () => {
  it('検索 API を呼び出してドメインモデルを返す', async () => {
    const result = await makeQuery().search(searchQuery({ keyword: 'react', page: 2 }))

    expect(result.items).toHaveLength(2)
    // 公開リポジトリに閉じるため is:public が先頭に付与される（下の専用テストも参照）
    expect(requests[0].searchParams.get('q')).toBe('is:public react')
    expect(requests[0].searchParams.get('page')).toBe('2')
    expect(requests[0].searchParams.get('per_page')).toBe('20')
  })

  it('検索クエリの先頭に is:public を置いて公開リポジトリに閉じる（installation token の可視範囲対策）', async () => {
    await makeQuery().search(searchQuery({ keyword: 'react' }))

    // 🔴 完全一致で検証する。末尾に置くと、キーワード側の未知の構文（末尾の `NOT` 等）に
    //    この修飾子が吸収・否定されうるため、位置そのものが防御の一部になっている。
    //    なお修飾子構文そのものはキーワード側で拒否される（`search-keyword.ts`）。
    expect(requests[0].searchParams.get('q')).toBe('is:public react')
  })

  it('キーワード側は修飾子構文を含められない（ドメインで拒否・多層防御の 1 層目）', () => {
    expect(() => searchQuery({ keyword: 'react is:private' })).toThrow(DomainValidationError)
  })

  it('上流が private: true を含む検索結果を返しても search() の戻り値からは除外され、totalCount は上流値のまま（多層防御・AC-12）', async () => {
    // 🔴 `is:public`（クエリ側の 1 層目）が効かなくなった状況の再現。
    //    total_count は items 件数（3）と一致しない値にして、「総件数はフィルタで書き換えない」
    //    契約が実装で守られていることを検証できるようにする。
    server.use(
      http.get('https://api.github.com/search/repositories', () =>
        HttpResponse.json({
          total_count: 999,
          incomplete_results: false,
          items: [
            ...fixture.items,
            {
              ...fixture.items[0],
              id: 4242,
              name: 'secret',
              full_name: 'acme/secret',
              html_url: 'https://github.com/acme/secret',
              private: true,
            },
          ],
        }),
      ),
    )

    const result = await makeQuery().search(searchQuery({ keyword: 'react' }))

    expect(result.items.map((item) => item.fullName)).not.toContain('acme/secret')
    expect(result.items).toHaveLength(2)
    expect(result.totalCount).toBe(999)
  })

  it('perPage を per_page パラメータへそのまま渡す', async () => {
    await makeQuery().search(searchQuery({ keyword: 'react', perPage: 100 }))

    expect(requests[0].searchParams.get('per_page')).toBe('100')
  })

  it('sort が relevance のときは sort / order パラメータを付けない（GitHub の既定挙動に委ねる）', async () => {
    await makeQuery().search(searchQuery({ keyword: 'react', sort: 'relevance' }))

    expect(requests[0].searchParams.has('sort')).toBe(false)
    expect(requests[0].searchParams.has('order')).toBe(false)
  })

  it('sort が stars のときは sort=stars&order=desc を付ける', async () => {
    await makeQuery().search(searchQuery({ keyword: 'react', sort: 'stars' }))

    expect(requests[0].searchParams.get('sort')).toBe('stars')
    expect(requests[0].searchParams.get('order')).toBe('desc')
  })

  it('sort が updated のときは sort=updated&order=desc を付ける', async () => {
    await makeQuery().search(searchQuery({ keyword: 'react', sort: 'updated' }))

    expect(requests[0].searchParams.get('sort')).toBe('updated')
    expect(requests[0].searchParams.get('order')).toBe('desc')
  })

  it('403 かつレート制限枯渇なら RateLimitExceededError を投げる', async () => {
    server.use(
      http.get('https://api.github.com/search/repositories', () =>
        HttpResponse.json(
          { message: 'rate limit' },
          { status: 403, headers: { 'x-ratelimit-remaining': '0' } },
        ),
      ),
    )

    await expect(makeQuery().search(searchQuery({ keyword: 'react' }))).rejects.toThrow(
      RateLimitExceededError,
    )
  })

  it('その他の失敗は UpstreamError に包む', async () => {
    server.use(
      http.get('https://api.github.com/search/repositories', () =>
        HttpResponse.json({ message: 'boom' }, { status: 500 }),
      ),
    )

    await expect(makeQuery().search(searchQuery({ keyword: 'react' }))).rejects.toThrow(
      UpstreamError,
    )
  })
})

describe('GithubRepositoryQuery#findDetail', () => {
  it('詳細 API を呼び出してドメインモデルを返す', async () => {
    const result = await makeQuery().findDetail(repositoryFullName('facebook', 'react'))

    expect(result?.fullName).toBe('facebook/react')
    expect(requests[0].pathname).toBe('/repos/facebook/react')
  })

  it('404 は例外にせず null を返す', async () => {
    server.use(
      http.get('https://api.github.com/repos/:owner/:repo', () =>
        HttpResponse.json({ message: 'Not Found' }, { status: 404 }),
      ),
    )

    const result = await makeQuery().findDetail(repositoryFullName('facebook', 'does-not-exist'))

    expect(result).toBeNull()
  })

  it('private: true の詳細レスポンスは null を返す（URL 直打ちで非公開リポジトリを読めないようにする・AC-12）', async () => {
    server.use(
      http.get('https://api.github.com/repos/:owner/:repo', () =>
        HttpResponse.json({ ...detailFixture, private: true }),
      ),
    )

    const result = await makeQuery().findDetail(repositoryFullName('acme', 'secret'))

    expect(result).toBeNull()
  })

  it('private: false の詳細レスポンスは従来どおり詳細を返す', async () => {
    server.use(
      http.get('https://api.github.com/repos/:owner/:repo', () =>
        HttpResponse.json({ ...detailFixture, private: false }),
      ),
    )

    const result = await makeQuery().findDetail(repositoryFullName('facebook', 'react'))

    expect(result?.fullName).toBe('facebook/react')
  })

  it('スキーマ不一致は UpstreamError を投げる', async () => {
    server.use(
      http.get('https://api.github.com/repos/:owner/:repo', () =>
        HttpResponse.json({ id: 'not-a-number' }),
      ),
    )

    await expect(makeQuery().findDetail(repositoryFullName('facebook', 'react'))).rejects.toThrow(
      UpstreamError,
    )
  })

  it('ドット入りのリポジトリ名を正しくエスケープして URL を組み立てる', async () => {
    await makeQuery().findDetail(repositoryFullName('example', 'user.github.io'))

    expect(requests[0].pathname).toBe('/repos/example/user.github.io')
  })
})

describe('GithubRepositoryQuery#findReadme', () => {
  it('README API を Accept: application/vnd.github.html+json で呼び出し、HTML 文字列を返す', async () => {
    const result = await makeQuery().findReadme(repositoryFullName('facebook', 'react'))

    expect(result).toBe('<h1 id="user-content-react">React</h1>')
    expect(requests[0].pathname).toBe('/repos/facebook/react/readme')
    expect(requestHeaders[0].get('accept')).toBe('application/vnd.github.html+json')
  })

  it('404（README が存在しない）は例外にせず null を返す', async () => {
    server.use(
      http.get('https://api.github.com/repos/:owner/:repo/readme', () =>
        HttpResponse.json({ message: 'Not Found' }, { status: 404 }),
      ),
    )

    const result = await makeQuery().findReadme(repositoryFullName('facebook', 'no-readme'))

    expect(result).toBeNull()
  })

  it('ドット入りのリポジトリ名を正しくエスケープして URL を組み立てる', async () => {
    await makeQuery().findReadme(repositoryFullName('example', 'user.github.io'))

    expect(requests[0].pathname).toBe('/repos/example/user.github.io/readme')
  })

  it('検索・詳細と同じくレート制限は RateLimitExceededError として投げる', async () => {
    server.use(
      http.get('https://api.github.com/repos/:owner/:repo/readme', () =>
        HttpResponse.json(
          { message: 'rate limit' },
          { status: 403, headers: { 'x-ratelimit-remaining': '0' } },
        ),
      ),
    )

    await expect(makeQuery().findReadme(repositoryFullName('facebook', 'react'))).rejects.toThrow(
      RateLimitExceededError,
    )
  })
})

/**
 * Issue #170 残射程: ETag / 条件付きリクエスト（`findDetail` / `findReadme` のみ）。
 * `search` は Search 専用レート枠（30 req/min）を条件付きリクエストが消費しないという明記が
 * GitHub 公式に無いため対象外（ https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api ）。
 */
describe('GithubRepositoryQuery のETag / 条件付きリクエスト（Issue #170）', () => {
  const ETAG_TTL_SECONDS = 3600

  function makeQueryWithCache(
    token: () => Promise<string | null> = async () => 'ghs_dummy',
    cache = new InMemoryCache(),
  ) {
    return {
      query: new GithubRepositoryQuery({ token, etag: { cache, ttlSeconds: ETAG_TTL_SECONDS } }),
      cache,
    }
  }

  /**
   * PR #926 Layer 1 セルフレビュー指摘 #1: `etag` を複合 optional にしたことで
   * 「片方だけ渡す」ことは型で不可能になったが、`ttlSeconds` の値域（正の有限数）は
   * 実行時にしか守れない。コンストラクタで検証し `RangeError` を fail-loud で投げる
   * （`architecture-rules.md` §1.6・`CachePort.set` と同じ値域）。
   */
  describe('コンストラクタの値域検証（PR #926 レビュー指摘 #1）', () => {
    it.each([0, -1, Number.NaN, Number.POSITIVE_INFINITY])(
      'etag.ttlSeconds が %s（値域外）なら RangeError を投げる',
      (ttlSeconds) => {
        expect(
          () =>
            new GithubRepositoryQuery({
              token: async () => 'ghs_dummy',
              etag: { cache: new InMemoryCache(), ttlSeconds },
            }),
        ).toThrow(RangeError)
      },
    )

    it('etag.ttlSeconds が正の有限数なら例外を投げない', () => {
      expect(
        () =>
          new GithubRepositoryQuery({
            token: async () => 'ghs_dummy',
            etag: { cache: new InMemoryCache(), ttlSeconds: 60 },
          }),
      ).not.toThrow()
    })

    it('etag を渡さない場合は検証されず、従来どおり ETag 経路無効で動作する', () => {
      expect(() => new GithubRepositoryQuery({ token: async () => 'ghs_dummy' })).not.toThrow()
    })
  })

  describe('findDetail', () => {
    it('ETag 保存済み + 認証済み → If-None-Match が送られる', async () => {
      const { query, cache } = makeQueryWithCache()
      await cache.set(
        repositoryEtagCacheKey('facebook', 'react'),
        { etag: 'W/"stored-etag"', body: detailFixture },
        ETAG_TTL_SECONDS,
      )
      server.use(
        http.get('https://api.github.com/repos/:owner/:repo', ({ request }) => {
          requestHeaders.push(request.headers)
          return new HttpResponse(null, { status: 304 })
        }),
      )

      await query.findDetail(repositoryFullName('facebook', 'react'))

      expect(requestHeaders[0].get('if-none-match')).toBe('W/"stored-etag"')
    })

    it('304 応答 → 上流本文を再取得せずキャッシュ済み payload を返す', async () => {
      const { query, cache } = makeQueryWithCache()
      await cache.set(
        repositoryEtagCacheKey('facebook', 'react'),
        { etag: 'W/"stored-etag"', body: detailFixture },
        ETAG_TTL_SECONDS,
      )
      server.use(
        http.get(
          'https://api.github.com/repos/:owner/:repo',
          () => new HttpResponse(null, { status: 304 }),
        ),
      )

      const result = await query.findDetail(repositoryFullName('facebook', 'react'))

      expect(result?.fullName).toBe('facebook/react')
    })

    it('200 応答 → 新しい ETag と生レスポンスが保存される', async () => {
      const { query, cache } = makeQueryWithCache()
      server.use(
        http.get('https://api.github.com/repos/:owner/:repo', () =>
          HttpResponse.json(detailFixture, { headers: { etag: 'W/"new-etag"' } }),
        ),
      )

      await query.findDetail(repositoryFullName('facebook', 'react'))

      const stored = await cache.get<{ etag: string; body: unknown }>(
        repositoryEtagCacheKey('facebook', 'react'),
      )
      expect(stored?.etag).toBe('W/"new-etag"')
      expect(stored?.body).toEqual(detailFixture)
    })

    it('未認証（token が null）→ ETag 保存済みでも If-None-Match を送らない', async () => {
      const { query, cache } = makeQueryWithCache(async () => null)
      await cache.set(
        repositoryEtagCacheKey('facebook', 'react'),
        { etag: 'W/"stored-etag"', body: detailFixture },
        ETAG_TTL_SECONDS,
      )
      server.use(
        http.get('https://api.github.com/repos/:owner/:repo', ({ request }) => {
          requestHeaders.push(request.headers)
          return HttpResponse.json(detailFixture)
        }),
      )

      await query.findDetail(repositoryFullName('facebook', 'react'))

      expect(requestHeaders[0].has('if-none-match')).toBe(false)
    })

    it('cache 未注入 → 現在とまったく同じ挙動（If-None-Match を送らない）', async () => {
      server.use(
        http.get('https://api.github.com/repos/:owner/:repo', ({ request }) => {
          requestHeaders.push(request.headers)
          return HttpResponse.json(detailFixture)
        }),
      )

      await makeQuery().findDetail(repositoryFullName('facebook', 'react'))

      expect(requestHeaders[0].has('if-none-match')).toBe(false)
    })

    it('ETag ストアに値があるが 304 ではなく 404 が返った → 従来どおり null', async () => {
      const { query, cache } = makeQueryWithCache()
      await cache.set(
        repositoryEtagCacheKey('facebook', 'react'),
        { etag: 'W/"stored-etag"', body: detailFixture },
        ETAG_TTL_SECONDS,
      )
      server.use(
        http.get('https://api.github.com/repos/:owner/:repo', () =>
          HttpResponse.json({ message: 'Not Found' }, { status: 404 }),
        ),
      )

      const result = await query.findDetail(repositoryFullName('facebook', 'does-not-exist'))

      expect(result).toBeNull()
    })

    it('If-None-Match を送っていないのに 304 が返るのは異常応答として UpstreamError にする', async () => {
      const { query } = makeQueryWithCache()
      // ETag ストアが空 = If-None-Match を送っていない状態で 304 を返す壊れた上流を模す
      server.use(
        http.get(
          'https://api.github.com/repos/:owner/:repo',
          () => new HttpResponse(null, { status: 304 }),
        ),
      )

      await expect(query.findDetail(repositoryFullName('facebook', 'react'))).rejects.toThrow(
        UpstreamError,
      )
    })

    /**
     * PR #926 Layer 1 セルフレビュー指摘 #2: `cache.get<EtagEntry<T>>()` の戻り値を
     * ランタイムで検証せず信頼していた。`body` が壊れて `null` になっていると
     * `findDetail` が「対象が存在しない」と誤判定してしまう（実在する公開リポジトリが
     * 404 相当になる）。型ガードで弾き、通常のフルフェッチへフォールバックすることを固定する。
     */
    it('ETag ストアの body が壊れて null になっている → 型ガードで弾きフルフェッチへフォールバックする（304 ではなく 200 を返す上流）', async () => {
      const { query, cache } = makeQueryWithCache()
      await cache.set(
        repositoryEtagCacheKey('facebook', 'react'),
        // 🔴 意図的に壊れたエントリ（body が null）を注入する。
        { etag: 'W/"corrupted"', body: null },
        ETAG_TTL_SECONDS,
      )
      let sawIfNoneMatch = false
      server.use(
        http.get('https://api.github.com/repos/:owner/:repo', ({ request }) => {
          sawIfNoneMatch = request.headers.has('if-none-match')
          return HttpResponse.json(detailFixture, { headers: { etag: 'W/"fresh-etag"' } })
        }),
      )

      const result = await query.findDetail(repositoryFullName('facebook', 'react'))

      // 壊れたエントリを信頼していれば If-None-Match を送っていたはず。弾けていれば送らない。
      expect(sawIfNoneMatch).toBe(false)
      expect(result?.fullName).toBe('facebook/react')
    })

    it('ETag ストアの etag が空文字列に壊れている → 型ガードで弾きフルフェッチへフォールバックする', async () => {
      const { query, cache } = makeQueryWithCache()
      await cache.set(
        repositoryEtagCacheKey('facebook', 'react'),
        { etag: '', body: detailFixture },
        ETAG_TTL_SECONDS,
      )
      let sawIfNoneMatch = false
      server.use(
        http.get('https://api.github.com/repos/:owner/:repo', ({ request }) => {
          sawIfNoneMatch = request.headers.has('if-none-match')
          return HttpResponse.json(detailFixture, { headers: { etag: 'W/"fresh-etag"' } })
        }),
      )

      const result = await query.findDetail(repositoryFullName('facebook', 'react'))

      expect(sawIfNoneMatch).toBe(false)
      expect(result?.fullName).toBe('facebook/react')
    })

    /**
     * PR #926 Layer 1 セルフレビュー指摘 #3（セキュリティ・NFR-33 / AC-12 の回帰）:
     * ETag ストアの `body` は ACL 適用前の生 JSON。private リポジトリの生データが
     * 何らかの経路（TTL 経過前の再共有等）で紛れ込んでいても、304 応答から復元した
     * `body` を `toPublicRepositoryDetail`（呼び出し元の `findDetail`）へ渡す限り、
     * private ゲートは通常のフルフェッチ経路と同じく必ず適用される。
     */
    it('ETag ストアに private: true の生 JSON が入っていても、304 応答からの復元後に private ゲートで null になる（NFR-33 / AC-12 回帰）', async () => {
      const { query, cache } = makeQueryWithCache()
      const privateRawJson = { ...detailFixture, private: true }
      await cache.set(
        repositoryEtagCacheKey('acme', 'secret'),
        { etag: 'W/"private-etag"', body: privateRawJson },
        ETAG_TTL_SECONDS,
      )
      server.use(
        http.get(
          'https://api.github.com/repos/:owner/:repo',
          () => new HttpResponse(null, { status: 304 }),
        ),
      )

      const result = await query.findDetail(repositoryFullName('acme', 'secret'))

      expect(result).toBeNull()
    })
  })

  describe('findReadme', () => {
    it('ETag 保存済み + 認証済み → If-None-Match が送られ、304 応答でキャッシュ済み HTML を返す', async () => {
      const { query, cache } = makeQueryWithCache()
      await cache.set(
        readmeEtagCacheKey('facebook', 'react'),
        { etag: 'W/"readme-etag"', body: '<h1>cached</h1>' },
        ETAG_TTL_SECONDS,
      )
      server.use(
        http.get('https://api.github.com/repos/:owner/:repo/readme', ({ request }) => {
          requestHeaders.push(request.headers)
          return new HttpResponse(null, { status: 304 })
        }),
      )

      const result = await query.findReadme(repositoryFullName('facebook', 'react'))

      expect(requestHeaders[0].get('if-none-match')).toBe('W/"readme-etag"')
      expect(result).toBe('<h1>cached</h1>')
    })

    it('200 応答 → 新しい ETag と本文が保存される', async () => {
      const { query, cache } = makeQueryWithCache()
      server.use(
        http.get('https://api.github.com/repos/:owner/:repo/readme', () =>
          HttpResponse.text('<h1>fresh</h1>', { headers: { etag: 'W/"fresh-etag"' } }),
        ),
      )

      const result = await query.findReadme(repositoryFullName('facebook', 'react'))

      expect(result).toBe('<h1>fresh</h1>')
      const stored = await cache.get<{ etag: string; body: string }>(
        readmeEtagCacheKey('facebook', 'react'),
      )
      expect(stored).toEqual({ etag: 'W/"fresh-etag"', body: '<h1>fresh</h1>' })
    })

    it('未認証（token が null）→ If-None-Match を送らない', async () => {
      const cache = new InMemoryCache()
      const { query } = makeQueryWithCache(async () => null, cache)
      await cache.set(
        readmeEtagCacheKey('facebook', 'react'),
        { etag: 'W/"readme-etag"', body: '<h1>cached</h1>' },
        ETAG_TTL_SECONDS,
      )
      server.use(
        http.get('https://api.github.com/repos/:owner/:repo/readme', ({ request }) => {
          requestHeaders.push(request.headers)
          return HttpResponse.text('<h1>fresh from upstream</h1>')
        }),
      )

      await query.findReadme(repositoryFullName('facebook', 'react'))

      expect(requestHeaders[0].has('if-none-match')).toBe(false)
    })

    /**
     * PR #926 Layer 1 セルフレビュー指摘 #10: `findDetail` にある 3 ケース
     * （404 で null / ストア空 + 304 で UpstreamError / cache 未注入で従来動作）を
     * `findReadme` にも対称に用意する（異常系テストの非対称を解消）。
     */
    it('404（README が存在しない・ETag 有効時）は例外にせず null を返す', async () => {
      const { query, cache } = makeQueryWithCache()
      await cache.set(
        readmeEtagCacheKey('facebook', 'does-not-exist'),
        { etag: 'W/"readme-etag"', body: '<h1>cached</h1>' },
        ETAG_TTL_SECONDS,
      )
      server.use(
        http.get('https://api.github.com/repos/:owner/:repo/readme', () =>
          HttpResponse.json({ message: 'Not Found' }, { status: 404 }),
        ),
      )

      const result = await query.findReadme(repositoryFullName('facebook', 'does-not-exist'))

      expect(result).toBeNull()
    })

    it('If-None-Match を送っていないのに 304 が返るのは異常応答として UpstreamError にする', async () => {
      const { query } = makeQueryWithCache()
      // ETag ストアが空 = If-None-Match を送っていない状態で 304 を返す壊れた上流を模す
      server.use(
        http.get(
          'https://api.github.com/repos/:owner/:repo/readme',
          () => new HttpResponse(null, { status: 304 }),
        ),
      )

      await expect(query.findReadme(repositoryFullName('facebook', 'react'))).rejects.toThrow(
        UpstreamError,
      )
    })

    it('cache 未注入 → 現在とまったく同じ挙動（If-None-Match を送らない）', async () => {
      server.use(
        http.get('https://api.github.com/repos/:owner/:repo/readme', ({ request }) => {
          requestHeaders.push(request.headers)
          return HttpResponse.text('<h1>fresh from upstream</h1>')
        }),
      )

      const result = await makeQuery().findReadme(repositoryFullName('facebook', 'react'))

      expect(requestHeaders[0].has('if-none-match')).toBe(false)
      expect(result).toBe('<h1>fresh from upstream</h1>')
    })
  })

  describe('干渉検証（#725: 独立した対策同士のデータフロー干渉）', () => {
    it('ETag 経路が入っても CachingRepositoryQuery の single-flight（同一キー並行リクエストは上流を 1 回しか叩かない）は壊れていない', async () => {
      const sharedCache = new InMemoryCache()
      const inner = new GithubRepositoryQuery({
        token: async () => 'ghs_dummy',
        etag: { cache: sharedCache, ttlSeconds: ETAG_TTL_SECONDS },
      })
      const decorated = new CachingRepositoryQuery({
        inner,
        cache: sharedCache,
        ttlSeconds: { search: 60, detail: 300 },
      })

      await Promise.all([
        decorated.findDetail(repositoryFullName('facebook', 'react')),
        decorated.findDetail(repositoryFullName('facebook', 'react')),
      ])

      expect(requests).toHaveLength(1)
    })

    it('ETag 保存領域（repository-etag 名前空間）と本文 TTL キャッシュ（repository 名前空間）は同じ CachePort を共有しても互いを上書きしない', async () => {
      const sharedCache = new InMemoryCache()
      const inner = new GithubRepositoryQuery({
        token: async () => 'ghs_dummy',
        etag: { cache: sharedCache, ttlSeconds: ETAG_TTL_SECONDS },
      })
      const decorated = new CachingRepositoryQuery({
        inner,
        cache: sharedCache,
        ttlSeconds: { search: 60, detail: 300 },
      })
      server.use(
        http.get('https://api.github.com/repos/:owner/:repo', () =>
          HttpResponse.json(detailFixture, { headers: { etag: 'W/"interference-etag"' } }),
        ),
      )

      await decorated.findDetail(repositoryFullName('facebook', 'react'))

      const bodyEntry = await sharedCache.get(repositoryCacheKey('facebook', 'react'))
      const etagEntry = await sharedCache.get<{ etag: string; body: unknown }>(
        repositoryEtagCacheKey('facebook', 'react'),
      )
      // 本文 TTL キャッシュはマッピング済みドメイン値（fullName を持つ）を保持する
      expect((bodyEntry as { fullName?: string } | null)?.fullName).toBe('facebook/react')
      // ETag キャッシュは生レスポンス（マッピング前・fullName を持たない GitHub 形式）を保持する
      expect((etagEntry?.body as { full_name?: string } | undefined)?.full_name).toBe(
        'facebook/react',
      )
      expect(etagEntry?.etag).toBeDefined()
    })

    /**
     * PR #926 レビュー対応の干渉検証: このタスクは独立した複数の対策
     * （① `etag` の複合 optional 化 ② ETag エントリの型ガード ③ ヘッダ/fetch 共通ヘルパー化
     * ④ `cache-key.ts` のキー生成共通化）を含む。①〜③ は同じデータフロー
     * （`fetchWithConditionalCache` 内で「型ガードを通過 → ヘッダ組み立て → fetch」の順に
     * 通る）ので、型ガードが正当なエントリを弾いていないこと、かつヘッダ共通化後も
     * `If-None-Match` が正しく送られることを 1 本のテストで確認する。
     */
    it('型ガード通過後もヘッダ共通化ヘルパーが If-None-Match / Authorization を正しく組み立てる（①②③の干渉検証）', async () => {
      const sharedCache = new InMemoryCache()
      await sharedCache.set(
        repositoryEtagCacheKey('facebook', 'react'),
        { etag: 'W/"valid-stored-etag"', body: detailFixture },
        ETAG_TTL_SECONDS,
      )
      const inner = new GithubRepositoryQuery({
        token: async () => 'ghs_dummy',
        etag: { cache: sharedCache, ttlSeconds: ETAG_TTL_SECONDS },
      })
      let capturedHeaders: Headers | undefined
      server.use(
        http.get('https://api.github.com/repos/:owner/:repo', ({ request }) => {
          capturedHeaders = request.headers
          return new HttpResponse(null, { status: 304 })
        }),
      )

      const result = await inner.findDetail(repositoryFullName('facebook', 'react'))

      // 型ガードが正当なエントリを誤って弾いていれば If-None-Match は送られない。
      expect(capturedHeaders?.get('if-none-match')).toBe('W/"valid-stored-etag"')
      // ヘッダ共通化ヘルパーが認証ヘッダも引き続き組み立てている。
      expect(capturedHeaders?.get('authorization')).toBe('Bearer ghs_dummy')
      expect(result?.fullName).toBe('facebook/react')
    })
  })
})

describe('GITHUB_API_ORIGIN 環境変数によるオリジン切り替え（E2E でスタブへ向けるため）', () => {
  const STUB_ORIGIN = 'http://127.0.0.1:8788'
  const originalEnv = process.env.GITHUB_API_ORIGIN

  afterEach(() => {
    if (originalEnv === undefined) {
      delete process.env.GITHUB_API_ORIGIN
    } else {
      process.env.GITHUB_API_ORIGIN = originalEnv
    }
  })

  it('GITHUB_API_ORIGIN が設定されていれば、そのオリジンへ検索リクエストする', async () => {
    process.env.GITHUB_API_ORIGIN = STUB_ORIGIN
    server.use(
      http.get(`${STUB_ORIGIN}/search/repositories`, ({ request }) => {
        requests.push(new URL(request.url))
        return HttpResponse.json(fixture)
      }),
    )

    const result = await makeQuery().search(searchQuery({ keyword: 'react' }))

    expect(result.items).toHaveLength(2)
    expect(requests[0].origin).toBe(STUB_ORIGIN)
  })

  it('GITHUB_API_ORIGIN が設定されていれば、そのオリジンへ詳細リクエストする', async () => {
    process.env.GITHUB_API_ORIGIN = STUB_ORIGIN
    server.use(
      http.get(`${STUB_ORIGIN}/repos/:owner/:repo`, ({ request }) => {
        requests.push(new URL(request.url))
        return HttpResponse.json(detailFixture)
      }),
    )

    const result = await makeQuery().findDetail(repositoryFullName('facebook', 'react'))

    expect(result?.fullName).toBe('facebook/react')
    expect(requests[0].origin).toBe(STUB_ORIGIN)
  })

  it('GITHUB_API_ORIGIN 未設定なら既定の https://api.github.com へリクエストする（回帰防止）', async () => {
    delete process.env.GITHUB_API_ORIGIN

    await makeQuery().search(searchQuery({ keyword: 'react' }))

    expect(requests[0].origin).toBe('https://api.github.com')
  })

  it('GITHUB_API_ORIGIN がループバック（http://localhost:8788）ならそのオリジンへリクエストする', async () => {
    const origin = 'http://localhost:8788'
    process.env.GITHUB_API_ORIGIN = origin
    server.use(
      http.get(`${origin}/search/repositories`, ({ request }) => {
        requests.push(new URL(request.url))
        return HttpResponse.json(fixture)
      }),
    )

    const result = await makeQuery().search(searchQuery({ keyword: 'react' }))

    expect(result.items).toHaveLength(2)
    expect(requests[0].origin).toBe(origin)
  })

  // 注: msw（path-to-regexp）が `[::1]` を含む URL のハンドラ登録に対応していないため、
  // ここでは「オリジン検証を通過し実際に fetch まで進むか」だけを確認する（実接続の成否は問わない）。
  it('GITHUB_API_ORIGIN が ::1（IPv6 ループバック）でも拒否されない（接続失敗はしてよい）', async () => {
    process.env.GITHUB_API_ORIGIN = 'http://[::1]:8788'

    await expect(makeQuery().search(searchQuery({ keyword: 'react' }))).rejects.not.toThrow(
      /GITHUB_API_ORIGIN/,
    )
  })

  it('GITHUB_API_ORIGIN に外部ホストを設定すると、トークン漏洩防止のため例外を投げる', async () => {
    process.env.GITHUB_API_ORIGIN = 'https://attacker.example'

    await expect(makeQuery().search(searchQuery({ keyword: 'react' }))).rejects.toThrow(
      /GITHUB_API_ORIGIN/,
    )
  })

  it('GITHUB_API_ORIGIN が不正な URL 形式だと例外を投げる', async () => {
    process.env.GITHUB_API_ORIGIN = 'not a url'

    await expect(makeQuery().search(searchQuery({ keyword: 'react' }))).rejects.toThrow(
      /GITHUB_API_ORIGIN/,
    )
  })
})

/**
 * prd.md §7「エラー種別の判別仕様」の判別ロジック（SP-9）。
 * 判定順序そのものが仕様なので、条件が重なるケース（`retry-after` と
 * `x-ratelimit-remaining: 0` の両方が付く 403 等）も含めて検証する。
 */
describe('エラー種別の判別（prd.md §7）', () => {
  function stubSearch(response: () => Response) {
    server.use(http.get('https://api.github.com/search/repositories', response))
  }

  async function searchError(): Promise<unknown> {
    return makeQuery()
      .search(searchQuery({ keyword: 'react' }))
      .then(
        () => {
          throw new Error('エラーが投げられなかった')
        },
        (error: unknown) => error,
      )
  }

  it('fetch 自体が失敗したら NetworkError（kind=network）', async () => {
    stubSearch(() => HttpResponse.error())

    const error = await searchError()

    expect(error).toBeInstanceOf(NetworkError)
    expect((error as NetworkError).kind).toBe('network')
  })

  it('404（notFoundAsNull なし）は NotFoundError（kind=notFound）', async () => {
    stubSearch(() => HttpResponse.json({ message: 'Not Found' }, { status: 404 }))

    const error = await searchError()

    expect(error).toBeInstanceOf(NotFoundError)
    expect((error as NotFoundError).kind).toBe('notFound')
  })

  it('403 かつ retry-after ありは二次レート制限（秒数を保持する）', async () => {
    stubSearch(() =>
      HttpResponse.json(
        { message: 'secondary' },
        { status: 403, headers: { 'retry-after': '60' } },
      ),
    )

    const error = (await searchError()) as RateLimitExceededError

    expect(error).toBeInstanceOf(RateLimitExceededError)
    expect(error.kind).toBe('rateLimitSecondary')
    expect(error.retryAfterSeconds).toBe(60)
  })

  it('429 かつ retry-after ありも二次レート制限', async () => {
    stubSearch(() =>
      HttpResponse.json({ message: 'secondary' }, { status: 429, headers: { 'retry-after': '5' } }),
    )

    const error = (await searchError()) as RateLimitExceededError

    expect(error.kind).toBe('rateLimitSecondary')
    expect(error.retryAfterSeconds).toBe(5)
  })

  // 🔴 prd.md §7 の表は一次（`x-ratelimit-remaining: 0`）を二次（`retry-after`）より先に置く。
  //    両方付いた応答を二次に倒すと、一次のときだけ出る「ログインで枠を増やせる案内」
  //    （`US-25` / `AR-5`・`toErrorPresentation` の `loginHint`）が消えるため順序が仕様の一部。
  it('retry-after と x-ratelimit-remaining: 0 が同時に付いたら一次レート制限を優先する（判定順序・prd.md §7）', async () => {
    const resetEpochSeconds = 1_800_000_000
    stubSearch(() =>
      HttpResponse.json(
        { message: 'both' },
        {
          status: 403,
          headers: {
            'retry-after': '30',
            'x-ratelimit-remaining': '0',
            'x-ratelimit-reset': String(resetEpochSeconds),
          },
        },
      ),
    )

    const error = (await searchError()) as RateLimitExceededError

    expect(error.kind).toBe('rateLimitPrimary')
    expect(error.retryAfter).toEqual(new Date(resetEpochSeconds * 1000))
    // 秒数は補助情報として保持してよい（提示の主役は復帰時刻）
    expect(error.retryAfterSeconds).toBe(30)
  })

  it('retry-after: 0 は二次レート制限として 0 秒を保持する（ヘッダ無しと区別する）', async () => {
    stubSearch(() =>
      HttpResponse.json({ message: 'secondary' }, { status: 403, headers: { 'retry-after': '0' } }),
    )

    const error = (await searchError()) as RateLimitExceededError

    expect(error.kind).toBe('rateLimitSecondary')
    expect(error.retryAfterSeconds).toBe(0)
  })

  // `retry-after` は delta-seconds と HTTP-date の両形式が有効（RFC 9110 §10.2.3）。
  it('retry-after が HTTP-date（未来）なら現在時刻との差を秒数として保持する', async () => {
    const future = new Date(Date.now() + 120_000)
    stubSearch(() =>
      HttpResponse.json(
        { message: 'secondary' },
        { status: 429, headers: { 'retry-after': future.toUTCString() } },
      ),
    )

    const error = (await searchError()) as RateLimitExceededError

    expect(error.kind).toBe('rateLimitSecondary')
    // 秒未満の丸めとテスト実行のずれを許容する
    expect(error.retryAfterSeconds).toBeGreaterThan(110)
    expect(error.retryAfterSeconds).toBeLessThanOrEqual(120)
  })

  it('retry-after が過去の HTTP-date なら待機不要（0 秒）として扱う', async () => {
    stubSearch(() =>
      HttpResponse.json(
        { message: 'secondary' },
        { status: 429, headers: { 'retry-after': 'Wed, 21 Oct 2015 07:28:00 GMT' } },
      ),
    )

    const error = (await searchError()) as RateLimitExceededError

    expect(error.kind).toBe('rateLimitSecondary')
    expect(error.retryAfterSeconds).toBe(0)
  })

  it('retry-after が負値・解釈不能なら再試行情報として扱わない（403 は AuthError へ倒す）', async () => {
    stubSearch(() =>
      HttpResponse.json({ message: 'broken' }, { status: 403, headers: { 'retry-after': '-5' } }),
    )

    const error = await searchError()

    expect(error).toBeInstanceOf(AuthError)
  })

  it('x-ratelimit-reset が壊れていても一次レート制限として扱い、復帰時刻は不明にする（Invalid Date を作らない）', async () => {
    stubSearch(() =>
      HttpResponse.json(
        { message: 'primary' },
        {
          status: 403,
          headers: {
            'x-ratelimit-remaining': '0',
            // ミリ秒が混入した値。秒として解釈すると Date のレンジを外れて Invalid Date になる
            'x-ratelimit-reset': '99999999999999',
          },
        },
      ),
    )

    const error = (await searchError()) as RateLimitExceededError

    expect(error.kind).toBe('rateLimitPrimary')
    expect(error.retryAfter).toBeUndefined()
  })

  it('403 かつ x-ratelimit-remaining: 0 は一次レート制限（reset から復帰時刻を算出する）', async () => {
    const resetEpochSeconds = 1_800_000_000
    stubSearch(() =>
      HttpResponse.json(
        { message: 'primary' },
        {
          status: 403,
          headers: { 'x-ratelimit-remaining': '0', 'x-ratelimit-reset': String(resetEpochSeconds) },
        },
      ),
    )

    const error = (await searchError()) as RateLimitExceededError

    expect(error.kind).toBe('rateLimitPrimary')
    expect(error.retryAfter).toEqual(new Date(resetEpochSeconds * 1000))
    expect(error.retryAfterSeconds).toBeUndefined()
  })

  it('429 で再試行情報が無ければ二次レート制限（秒数不明）', async () => {
    stubSearch(() => HttpResponse.json({ message: 'too many' }, { status: 429 }))

    const error = (await searchError()) as RateLimitExceededError

    expect(error.kind).toBe('rateLimitSecondary')
    expect(error.retryAfterSeconds).toBeUndefined()
  })

  it('401 は AuthError（kind=auth・内部情報を出さない汎用エラー）', async () => {
    stubSearch(() => HttpResponse.json({ message: 'Bad credentials' }, { status: 401 }))

    const error = await searchError()

    expect(error).toBeInstanceOf(AuthError)
    expect((error as AuthError).kind).toBe('auth')
  })

  it('レート制限以外の 403 は AuthError', async () => {
    stubSearch(() => HttpResponse.json({ message: 'Forbidden' }, { status: 403 }))

    const error = await searchError()

    expect(error).toBeInstanceOf(AuthError)
    expect((error as AuthError).kind).toBe('auth')
  })

  // 🔴 422 は「上流がクエリを受理しなかった」であって値オブジェクトの不変条件違反ではないため
  //    `DomainValidationError` には写さない（`SearchQuery` は domain-model.md §4 の値オブジェクト
  //    表に無い）。載せるのは利用者入力に由来するキーワードだけで、ACL が付与した公開限定修飾子
  //    （`is:public`・`NFR-33`）は含めない。
  it('422 は SearchQueryRejectedError（kind=validation・入力の修正を促す）', async () => {
    stubSearch(() => HttpResponse.json({ message: 'Validation Failed' }, { status: 422 }))

    const error = await searchError()

    expect(error).toBeInstanceOf(SearchQueryRejectedError)
    expect(error).not.toBeInstanceOf(DomainValidationError)
    expect((error as SearchQueryRejectedError).kind).toBe('validation')
    expect((error as SearchQueryRejectedError).keyword).toBe('react')
  })

  it('5xx は UpstreamError（kind=upstream）', async () => {
    stubSearch(() => HttpResponse.json({ message: 'boom' }, { status: 503 }))

    const error = await searchError()

    expect(error).toBeInstanceOf(UpstreamError)
    expect((error as UpstreamError).kind).toBe('upstream')
  })

  it('notFoundAsNull 付きの findDetail では 404 が従来どおり null（例外に変えない）', async () => {
    server.use(
      http.get('https://api.github.com/repos/:owner/:repo', () =>
        HttpResponse.json({ message: 'Not Found' }, { status: 404 }),
      ),
    )

    await expect(makeQuery().findDetail(repositoryFullName('facebook', 'nope'))).resolves.toBeNull()
  })
})
