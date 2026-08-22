/**
 * collect.test.mjs — 収集レイヤー（registries.mjs / collect.mjs）のユニットテスト。
 *
 * 🔴 ネットワークを叩かない: `fetchImpl` と `sleepImpl` を必ずスタブで注入する。
 * 投影関数 `project` も DI なので、ここでは「投影の中身」ではなく
 * 「収集レイヤーが投影結果をどう扱うか」だけを検証する。
 */

import { describe, expect, it, vi } from 'vitest'

import { API_BASE, DEFAULT_PER_PAGE, USER_AGENT, collectAll, collectRegistry } from './collect.mjs'
import { REGISTRIES, registryFileSlug } from './registries.mjs'

/** 投影関数のスタブ: 生レコードをそのまま通す（null を返さない） */
const passThrough = (raw) => raw

/** テスト用の生パッケージを n 件作る */
function makeRawPage(prefix, n) {
  return Array.from({ length: n }, (_, i) => ({ name: `${prefix}-${i}` }))
}

/** 成功レスポンス（Response 互換の最小スタブ） */
function okResponse(body) {
  return { ok: true, status: 200, headers: new Headers(), json: async () => body }
}

/** エラーレスポンス（Response 互換の最小スタブ） */
function errorResponse(status, headers = {}) {
  return {
    ok: false,
    status,
    headers: new Headers(headers),
    json: async () => ({ error: `HTTP ${status}` }),
  }
}

/**
 * ページ列（1 ページ目から順の配列）を返す fetch スタブを作る。
 * 要素が Error なら reject、Response 互換オブジェクトならそのまま解決する。
 */
function makeFetchImpl(pages) {
  const calls = []
  const fetchImpl = vi.fn(async (url, init) => {
    calls.push({ url: String(url), init })
    const next = pages[calls.length - 1]
    if (next === undefined) throw new Error(`想定外の追加リクエスト: ${url}`)
    if (next instanceof Error) throw next
    return next
  })
  return { fetchImpl, calls }
}

/** sleepImpl のスタブ（待機せず待機ミリ秒だけ記録する） */
function makeSleepImpl() {
  const waited = []
  const sleepImpl = vi.fn(async (ms) => {
    waited.push(ms)
  })
  return { sleepImpl, waited }
}

describe('registries.mjs', () => {
  it('12 レジストリを Ecosyste.ms の正確な registry 名で定義する', () => {
    expect(REGISTRIES).toHaveLength(12)
    expect(REGISTRIES.map((r) => r.name)).toEqual([
      'npmjs.org',
      'pypi.org',
      'crates.io',
      'rubygems.org',
      'packagist.org',
      'proxy.golang.org',
      'repo1.maven.org',
      'nuget.org',
      'hex.pm',
      'pub.dev',
      'metacpan.org',
      'cran.r-project.org',
    ])
  })

  it('各要素が name / ecosystem を持ち、name は重複しない', () => {
    for (const entry of REGISTRIES) {
      expect(typeof entry.name).toBe('string')
      expect(entry.name.length).toBeGreaterThan(0)
      expect(typeof entry.ecosystem).toBe('string')
      expect(entry.ecosystem.length).toBeGreaterThan(0)
    }
    expect(new Set(REGISTRIES.map((r) => r.name)).size).toBe(REGISTRIES.length)
  })

  it('registryFileSlug が "." を "-" に置換する', () => {
    expect(registryFileSlug('npmjs.org')).toBe('npmjs-org')
    expect(registryFileSlug('cran.r-project.org')).toBe('cran-r-project-org')
    expect(registryFileSlug('repo1.maven.org')).toBe('repo1-maven-org')
    expect(registryFileSlug('crates.io')).toBe('crates-io')
  })

  it('registryFileSlug の結果はファイル名として安全な文字だけになる（全 12 レジストリ）', () => {
    for (const { name } of REGISTRIES) {
      const slug = registryFileSlug(name)
      expect(slug).toMatch(/^[a-z0-9-]+$/)
      expect(slug.startsWith('-')).toBe(false)
      expect(slug.endsWith('-')).toBe(false)
    }
    // slug も一意（静的アセットのファイル名が衝突しない）
    expect(new Set(REGISTRIES.map((r) => registryFileSlug(r.name))).size).toBe(REGISTRIES.length)
  })

  it('registryFileSlug が危険な文字（パス区切り・大文字・空白）を落とす', () => {
    expect(registryFileSlug('../etc/passwd')).toBe('etc-passwd')
    expect(registryFileSlug('Foo Bar.ORG')).toBe('foo-bar-org')
    expect(registryFileSlug('a__b')).toBe('a-b')
  })

  it('registryFileSlug は空文字・非文字列を拒否する', () => {
    expect(() => registryFileSlug('')).toThrow()
    expect(() => registryFileSlug('...')).toThrow()
    expect(() => registryFileSlug(null)).toThrow()
  })
})

describe('collectRegistry', () => {
  it('URL に正しいクエリパラメータとヘッダが載る', async () => {
    const { fetchImpl, calls } = makeFetchImpl([okResponse(makeRawPage('a', 3))])

    await collectRegistry({
      registry: 'npmjs.org',
      quota: 10,
      perPage: 5,
      fetchImpl,
      project: passThrough,
    })

    expect(calls).toHaveLength(1)
    const url = new URL(calls[0].url)
    expect(`${url.origin}${url.pathname}`).toBe(`${API_BASE}/npmjs.org/packages`)
    expect(url.searchParams.get('sort')).toBe('dependent_packages_count')
    expect(url.searchParams.get('order')).toBe('desc')
    expect(url.searchParams.get('per_page')).toBe('5')
    expect(url.searchParams.get('page')).toBe('1')

    const headers = calls[0].init.headers
    expect(headers['user-agent']).toBe(USER_AGENT)
    expect(headers.accept).toBe('application/json')
  })

  it('perPage を省略すると DEFAULT_PER_PAGE を使う', async () => {
    const { fetchImpl, calls } = makeFetchImpl([okResponse([])])

    await collectRegistry({ registry: 'hex.pm', quota: 10, fetchImpl, project: passThrough })

    expect(new URL(calls[0].url).searchParams.get('per_page')).toBe(String(DEFAULT_PER_PAGE))
  })

  it('ページングして quota ちょうどで打ち切る（取得件数の枠）', async () => {
    const { fetchImpl, calls } = makeFetchImpl([
      okResponse(makeRawPage('p1', 10)),
      okResponse(makeRawPage('p2', 10)),
      okResponse(makeRawPage('p3', 10)),
    ])

    const result = await collectRegistry({
      registry: 'npmjs.org',
      quota: 25,
      perPage: 10,
      fetchImpl,
      project: passThrough,
    })

    expect(calls).toHaveLength(3)
    expect(calls.map((c) => new URL(c.url).searchParams.get('page'))).toEqual(['1', '2', '3'])
    expect(result.fetchedCount).toBe(25)
    expect(result.records).toHaveLength(25)
    expect(result.requestCount).toBe(3)
    expect(result.registry).toBe('npmjs.org')
  })

  it('最終ページ（返却件数が perPage 未満）で停止する', async () => {
    const { fetchImpl, calls } = makeFetchImpl([
      okResponse(makeRawPage('p1', 10)),
      okResponse(makeRawPage('p2', 4)),
    ])

    const result = await collectRegistry({
      registry: 'cran.r-project.org',
      quota: 1000,
      perPage: 10,
      fetchImpl,
      project: passThrough,
    })

    expect(calls).toHaveLength(2)
    expect(result.fetchedCount).toBe(14)
    expect(result.records).toHaveLength(14)
  })

  it('空配列が返ったら停止する', async () => {
    const { fetchImpl, calls } = makeFetchImpl([okResponse(makeRawPage('p1', 10)), okResponse([])])

    const result = await collectRegistry({
      registry: 'metacpan.org',
      quota: 1000,
      perPage: 10,
      fetchImpl,
      project: passThrough,
    })

    expect(calls).toHaveLength(2)
    expect(result.fetchedCount).toBe(10)
    expect(result.records).toHaveLength(10)
    expect(result.requestCount).toBe(2)
  })

  it('project が null を返したレコードは除外する（捨てた分をページ追加で埋め直さない）', async () => {
    const { fetchImpl, calls } = makeFetchImpl([
      okResponse(makeRawPage('p1', 10)),
      okResponse(makeRawPage('p2', 10)),
    ])

    const result = await collectRegistry({
      registry: 'pypi.org',
      quota: 20,
      perPage: 10,
      fetchImpl,
      // 偶数番だけ通す
      project: (raw) => (Number(raw.name.split('-').pop()) % 2 === 0 ? raw : null),
    })

    expect(calls).toHaveLength(2) // 10 件しか残らなくても 3 ページ目を取りに行かない
    expect(result.fetchedCount).toBe(20)
    expect(result.records).toHaveLength(10)
  })

  it('project にはレジストリ名が第 2 引数で渡る', async () => {
    const { fetchImpl } = makeFetchImpl([okResponse(makeRawPage('p1', 2))])
    const project = vi.fn((raw) => raw)

    await collectRegistry({ registry: 'pub.dev', quota: 2, perPage: 2, fetchImpl, project })

    expect(project).toHaveBeenCalledTimes(2)
    expect(project.mock.calls[0][1]).toBe('pub.dev')
  })

  it('onPage が 1 ページごとに進捗を通知する', async () => {
    const { fetchImpl } = makeFetchImpl([okResponse(makeRawPage('p1', 4))])
    const onPage = vi.fn()

    await collectRegistry({
      registry: 'nuget.org',
      quota: 4,
      perPage: 4,
      fetchImpl,
      project: (raw) => (raw.name.endsWith('0') ? null : raw),
      onPage,
    })

    expect(onPage).toHaveBeenCalledTimes(1)
    const info = onPage.mock.calls[0][0]
    expect(info.registry).toBe('nuget.org')
    expect(info.page).toBe(1)
    expect(info.fetched).toBe(4)
    expect(info.kept).toBe(3)
    expect(typeof info.elapsedMs).toBe('number')
  })

  it('500 が返ってもリトライして成功する（指数バックオフ）', async () => {
    const { fetchImpl, calls } = makeFetchImpl([
      errorResponse(500),
      errorResponse(500),
      okResponse(makeRawPage('p1', 2)),
    ])
    const { sleepImpl, waited } = makeSleepImpl()

    const result = await collectRegistry({
      registry: 'npmjs.org',
      quota: 2,
      perPage: 10,
      fetchImpl,
      project: passThrough,
      sleepImpl,
    })

    expect(calls).toHaveLength(3)
    expect(waited).toEqual([1000, 2000]) // 1000 * 2 ** attempt
    expect(result.records).toHaveLength(2)
    expect(result.requestCount).toBe(3) // リトライ分も要求数に含める
  })

  it('fetch が例外を投げてもリトライする', async () => {
    const { fetchImpl, calls } = makeFetchImpl([
      new Error('socket hang up'),
      okResponse(makeRawPage('p1', 1)),
    ])
    const { sleepImpl, waited } = makeSleepImpl()

    const result = await collectRegistry({
      registry: 'hex.pm',
      quota: 1,
      perPage: 10,
      fetchImpl,
      project: passThrough,
      sleepImpl,
    })

    expect(calls).toHaveLength(2)
    expect(waited).toEqual([1000])
    expect(result.records).toHaveLength(1)
  })

  it('リトライ上限を超えたら例外を投げる（maxRetries 回までリトライ）', async () => {
    const { fetchImpl, calls } = makeFetchImpl([
      errorResponse(503),
      errorResponse(503),
      errorResponse(503),
    ])
    const { sleepImpl, waited } = makeSleepImpl()

    await expect(
      collectRegistry({
        registry: 'crates.io',
        quota: 10,
        perPage: 10,
        fetchImpl,
        project: passThrough,
        maxRetries: 2,
        sleepImpl,
      }),
    ).rejects.toThrow(/crates\.io/)

    expect(calls).toHaveLength(3) // 初回 + リトライ 2 回
    expect(waited).toEqual([1000, 2000]) // 最後の失敗のあとは待たない
  })

  it('429 は retry-after ヘッダ（秒）を尊重して待つ', async () => {
    const { fetchImpl } = makeFetchImpl([
      errorResponse(429, { 'retry-after': '7' }),
      okResponse(makeRawPage('p1', 1)),
    ])
    const { sleepImpl, waited } = makeSleepImpl()

    await collectRegistry({
      registry: 'packagist.org',
      quota: 1,
      perPage: 10,
      fetchImpl,
      project: passThrough,
      sleepImpl,
    })

    expect(waited).toEqual([7000])
  })

  it('429 に retry-after が無ければ指数バックオフにフォールバックする', async () => {
    const { fetchImpl } = makeFetchImpl([errorResponse(429), okResponse(makeRawPage('p1', 1))])
    const { sleepImpl, waited } = makeSleepImpl()

    await collectRegistry({
      registry: 'packagist.org',
      quota: 1,
      perPage: 10,
      fetchImpl,
      project: passThrough,
      sleepImpl,
    })

    expect(waited).toEqual([1000])
  })

  it('配列以外が返ったらリトライせず例外を投げる', async () => {
    const { fetchImpl, calls } = makeFetchImpl([okResponse({ error: 'not found' })])
    const { sleepImpl } = makeSleepImpl()

    await expect(
      collectRegistry({
        registry: 'npmjs.org',
        quota: 10,
        fetchImpl,
        project: passThrough,
        sleepImpl,
      }),
    ).rejects.toThrow(/配列/)

    expect(calls).toHaveLength(1)
  })

  it('引数が不正なら即座に例外を投げる', async () => {
    const { fetchImpl } = makeFetchImpl([])
    await expect(
      collectRegistry({ registry: '', quota: 10, fetchImpl, project: passThrough }),
    ).rejects.toThrow()
    await expect(
      collectRegistry({ registry: 'npmjs.org', quota: 0, fetchImpl, project: passThrough }),
    ).rejects.toThrow()
    await expect(
      collectRegistry({ registry: 'npmjs.org', quota: 10, fetchImpl, project: null }),
    ).rejects.toThrow()
    await expect(
      collectRegistry({
        registry: 'npmjs.org',
        quota: 10,
        perPage: 0,
        fetchImpl,
        project: passThrough,
      }),
    ).rejects.toThrow()
  })
})

describe('collectAll', () => {
  it('複数レジストリを逐次で収集して byRegistry にまとめる', async () => {
    const order = []
    const fetchImpl = vi.fn(async (url) => {
      const registry = new URL(url).pathname.split('/')[4]
      order.push(registry)
      return okResponse(makeRawPage(registry, 2))
    })

    const result = await collectAll({
      registries: [{ name: 'npmjs.org' }, { name: 'pypi.org' }],
      quota: 2,
      perPage: 10,
      fetchImpl,
      project: passThrough,
    })

    expect(order).toEqual(['npmjs.org', 'pypi.org']) // 逐次（同時接続を増やさない）
    expect([...result.byRegistry.keys()]).toEqual(['npmjs.org', 'pypi.org'])
    expect(result.byRegistry.get('npmjs.org')).toHaveLength(2)
    expect(result.requestCount).toBe(2)
    expect(result.fetchedCount).toBe(4)
    expect(result.failures).toEqual([])
  })

  it('レジストリ名の文字列配列も受け付ける', async () => {
    const fetchImpl = vi.fn(async () => okResponse(makeRawPage('x', 1)))

    const result = await collectAll({
      registries: ['hex.pm'],
      quota: 1,
      perPage: 10,
      fetchImpl,
      project: passThrough,
    })

    expect([...result.byRegistry.keys()]).toEqual(['hex.pm'])
  })

  it('1 レジストリの失敗を failures に記録して次へ進む', async () => {
    const fetchImpl = vi.fn(async (url) => {
      const registry = new URL(url).pathname.split('/')[4]
      if (registry === 'pypi.org') return errorResponse(500)
      return okResponse(makeRawPage(registry, 3))
    })
    const { sleepImpl } = makeSleepImpl()
    const onRegistryDone = vi.fn()

    const result = await collectAll({
      registries: ['npmjs.org', 'pypi.org', 'crates.io'],
      quota: 3,
      perPage: 10,
      fetchImpl,
      project: passThrough,
      maxRetries: 1,
      sleepImpl,
      onRegistryDone,
    })

    expect([...result.byRegistry.keys()]).toEqual(['npmjs.org', 'crates.io'])
    expect(result.failures).toHaveLength(1)
    expect(result.failures[0].registry).toBe('pypi.org')
    expect(typeof result.failures[0].message).toBe('string')
    expect(result.failures[0].message.length).toBeGreaterThan(0)
    // 失敗レジストリで消費したリクエストも要求数に計上する（レート枠の把握のため）
    expect(result.requestCount).toBe(4) // 1 + 2（失敗 2 回）+ 1
    expect(result.fetchedCount).toBe(6)
    expect(onRegistryDone).toHaveBeenCalledTimes(3)
    expect(onRegistryDone.mock.calls.map((c) => c[0].ok)).toEqual([true, false, true])
  })

  it('registries が空なら何も収集せず空の結果を返す', async () => {
    const fetchImpl = vi.fn()
    const result = await collectAll({
      registries: [],
      quota: 10,
      fetchImpl,
      project: passThrough,
    })

    expect(fetchImpl).not.toHaveBeenCalled()
    expect(result.byRegistry.size).toBe(0)
    expect(result.requestCount).toBe(0)
    expect(result.failures).toEqual([])
  })
})
