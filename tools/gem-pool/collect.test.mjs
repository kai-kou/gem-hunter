// collect.test.mjs — 収集レイヤー（registries.mjs / collect.mjs）のユニットテスト。
// 🔴 実ネットワークに一切触れない。fetch と sleep はすべてテストダブルで注入する。

import { describe, expect, it, vi } from 'vitest'
import { DEFAULT_PER_PAGE, DEFAULT_QUOTA, REGISTRIES, findRegistry } from './registries.mjs'
import { API_BASE, collectAll, collectRegistry } from './collect.mjs'

const NPM = findRegistry('npm')
const PYPI = findRegistry('pypi')

function jsonResponse(body, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: `status-${status}`,
    json: async () => body,
  }
}

function makePackages(n, offset = 0) {
  return Array.from({ length: n }, (_, i) => ({ name: `pkg-${offset + i}` }))
}

function noopSleep() {
  return Promise.resolve()
}

describe('registries.mjs', () => {
  it('REGISTRIES は契約どおり 12 件・この順序', () => {
    expect(REGISTRIES.map((r) => r.id)).toEqual([
      'npm',
      'pypi',
      'cargo',
      'rubygems',
      'packagist',
      'go',
      'maven',
      'nuget',
      'hex',
      'pub',
      'cpan',
      'cran',
    ])
    expect(REGISTRIES.find((r) => r.id === 'npm').name).toBe('npmjs.org')
    expect(REGISTRIES.find((r) => r.id === 'maven').name).toBe('repo1.maven.org')
  })

  it('findRegistry: 既知 id は RegistryDef を返す', () => {
    expect(findRegistry('npm')).toEqual({ id: 'npm', name: 'npmjs.org' })
  })

  it('findRegistry: 未知 id は Error を投げる（静かに無視しない）', () => {
    expect(() => findRegistry('does-not-exist')).toThrow(/未知のレジストリ/)
  })

  it('DEFAULT_QUOTA / DEFAULT_PER_PAGE の既定値', () => {
    expect(DEFAULT_QUOTA).toBe(15000)
    expect(DEFAULT_PER_PAGE).toBe(1000)
  })
})

describe('collectRegistry: ページング打ち切り', () => {
  it('perPage 未満のページが返ったら打ち切る', async () => {
    const fetchImpl = vi.fn(async (url) => {
      const page = Number(new URL(url).searchParams.get('page'))
      if (page === 1) return jsonResponse(makePackages(3))
      if (page === 2) return jsonResponse(makePackages(2)) // perPage(3) 未満 → 最終ページ
      throw new Error('これ以上呼ばれないはず')
    })

    const result = await collectRegistry({
      registry: NPM,
      quota: 100,
      perPage: 3,
      fetchImpl,
      sleep: noopSleep,
    })

    expect(result).toHaveLength(5)
    expect(fetchImpl).toHaveBeenCalledTimes(2)
  })

  it('空配列が返ったら打ち切る', async () => {
    const fetchImpl = vi.fn(async (url) => {
      const page = Number(new URL(url).searchParams.get('page'))
      if (page === 1) return jsonResponse(makePackages(3))
      return jsonResponse([])
    })

    const result = await collectRegistry({
      registry: NPM,
      quota: 100,
      perPage: 3,
      fetchImpl,
      sleep: noopSleep,
    })

    expect(result).toHaveLength(3)
  })

  it('URL に sort=dependent_packages_count&order=desc&per_page&page を積む', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse([]))
    await collectRegistry({ registry: PYPI, quota: 10, perPage: 5, fetchImpl, sleep: noopSleep })

    const calledUrl = new URL(fetchImpl.mock.calls[0][0])
    expect(calledUrl.pathname).toBe('/api/v1/registries/pypi.org/packages')
    expect(calledUrl.searchParams.get('sort')).toBe('dependent_packages_count')
    expect(calledUrl.searchParams.get('order')).toBe('desc')
    expect(calledUrl.searchParams.get('per_page')).toBe('5')
    expect(calledUrl.searchParams.get('page')).toBe('1')
  })
})

describe('collectRegistry: quota スライス', () => {
  it('quota 到達で打ち切り、quota 件へ slice する', async () => {
    const fetchImpl = vi.fn(async (url) => {
      const page = Number(new URL(url).searchParams.get('page'))
      return jsonResponse(makePackages(10, (page - 1) * 10))
    })

    const result = await collectRegistry({
      registry: NPM,
      quota: 25,
      perPage: 10,
      fetchImpl,
      sleep: noopSleep,
    })

    expect(result).toHaveLength(25)
    // quota 到達直後に打ち切るので 3 ページ目までしか叩かない（10+10+10=30 >= 25）
    expect(fetchImpl).toHaveBeenCalledTimes(3)
    expect(result[0].name).toBe('pkg-0')
    expect(result[24].name).toBe('pkg-24')
  })
})

describe('collectRegistry: 429 リトライ', () => {
  it('429 が 2 回続いても 3 回目で成功すれば結果を返す', async () => {
    let calls = 0
    const fetchImpl = vi.fn(async () => {
      calls += 1
      if (calls <= 2) return jsonResponse(null, 429)
      return jsonResponse(makePackages(2))
    })
    const sleep = vi.fn(noopSleep)

    const result = await collectRegistry({
      registry: NPM,
      quota: 10,
      perPage: 10,
      fetchImpl,
      sleep,
    })

    expect(result).toHaveLength(2)
    expect(fetchImpl).toHaveBeenCalledTimes(3)
    // 指数バックオフ 1s → 2s
    expect(sleep).toHaveBeenNthCalledWith(1, 1000)
    expect(sleep).toHaveBeenNthCalledWith(2, 2000)
  })

  it('5xx も同様にリトライ対象になる', async () => {
    let calls = 0
    const fetchImpl = vi.fn(async () => {
      calls += 1
      if (calls === 1) return jsonResponse(null, 503)
      return jsonResponse(makePackages(1))
    })

    const result = await collectRegistry({
      registry: NPM,
      quota: 10,
      perPage: 10,
      fetchImpl,
      sleep: noopSleep,
    })

    expect(result).toHaveLength(1)
  })
})

describe('collectRegistry: 恒久失敗時の扱い', () => {
  it('429 が 3 回リトライ後も失敗し続けたら Error を投げず空配列を返す', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(null, 429))
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})

    const result = await collectRegistry({
      registry: NPM,
      quota: 10,
      perPage: 10,
      fetchImpl,
      sleep: noopSleep,
    })

    expect(result).toEqual([])
    // 初回 + 3 リトライ = 4 回叩いてから諦める
    expect(fetchImpl).toHaveBeenCalledTimes(4)
    expect(warnSpy).toHaveBeenCalled()
    warnSpy.mockRestore()
  })

  it('429 以外の 4xx は即中断してそのレジストリを空にする（リトライしない）', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(null, 404))
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})

    const result = await collectRegistry({
      registry: NPM,
      quota: 10,
      perPage: 10,
      fetchImpl,
      sleep: noopSleep,
    })

    expect(result).toEqual([])
    expect(fetchImpl).toHaveBeenCalledTimes(1)
    warnSpy.mockRestore()
  })

  it('途中ページで恒久失敗しても、それ以前に取得済みの分は捨てずに返す', async () => {
    // 1 ページ目は成功（3 件）、2 ページ目が 429 を出し続けてリトライも尽きるケース。
    // 「1 ページの一時障害でレジストリ丸ごと 0 件」を防ぐのが目的（指摘 2）。
    const fetchImpl = vi.fn(async (url) => {
      const page = Number(new URL(url).searchParams.get('page'))
      if (page === 1) return jsonResponse(makePackages(3))
      return jsonResponse(null, 429)
    })
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    const result = await collectRegistry({
      registry: NPM,
      quota: 100,
      perPage: 3,
      fetchImpl,
      sleep: noopSleep,
    })

    expect(result).toEqual(makePackages(3))
    expect(warnSpy).toHaveBeenCalled()
    warnSpy.mockRestore()
    errorSpy.mockRestore()
  })

  it('quota に届く前に恒久失敗しても、取得済み件数が quota 未満のまま返る（slice で水増ししない）', async () => {
    const fetchImpl = vi.fn(async (url) => {
      const page = Number(new URL(url).searchParams.get('page'))
      if (page === 1) return jsonResponse(makePackages(2))
      return jsonResponse(null, 500)
    })
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    const result = await collectRegistry({
      registry: NPM,
      quota: 50,
      perPage: 2,
      fetchImpl,
      sleep: noopSleep,
    })

    expect(result).toHaveLength(2)
    warnSpy.mockRestore()
    errorSpy.mockRestore()
  })

  it('collectAll: 1 レジストリが恒久失敗しても他レジストリの収集は続行する', async () => {
    const fetchImpl = vi.fn(async (url) => {
      const requested = new URL(url)
      // 🔴 部分一致（`pathname.includes('npmjs.org')`）は「前後に任意のホストが来てもよい」
      //   判定になり CodeQL の Incomplete URL substring sanitization に引っかかる。
      //   パスをセグメントに割ってから完全一致で見る。
      expect(requested.href.startsWith(API_BASE)).toBe(true)
      const segments = requested.pathname.split('/').filter(Boolean)
      const isNpm = segments.includes('npmjs.org')
      if (isNpm) return jsonResponse(null, 500)
      return jsonResponse(makePackages(2))
    })
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    const result = await collectAll({
      registries: [NPM, PYPI],
      quota: 10,
      perPage: 10,
      fetchImpl,
      sleep: noopSleep,
    })

    expect(result).toEqual([
      { registry: 'npm', packages: [] },
      { registry: 'pypi', packages: makePackages(2) },
    ])
    warnSpy.mockRestore()
    errorSpy.mockRestore()
  })
})

describe('collectRegistry: onProgress とレート制御', () => {
  it('ページ取得ごとに onProgress を呼ぶ', async () => {
    const fetchImpl = vi.fn(async (url) => {
      const page = Number(new URL(url).searchParams.get('page'))
      if (page === 1) return jsonResponse(makePackages(3))
      return jsonResponse([])
    })
    const onProgress = vi.fn()
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    await collectRegistry({
      registry: NPM,
      quota: 10,
      perPage: 3,
      fetchImpl,
      sleep: noopSleep,
      onProgress,
    })

    expect(onProgress).toHaveBeenCalledWith({ registry: 'npm', page: 1, fetched: 3 })
    errorSpy.mockRestore()
  })

  it('次ページ取得前に既定 250ms スリープする（sleep 注入で検証）', async () => {
    const fetchImpl = vi.fn(async (url) => {
      const page = Number(new URL(url).searchParams.get('page'))
      if (page === 1) return jsonResponse(makePackages(3))
      return jsonResponse([])
    })
    const sleep = vi.fn(noopSleep)
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    await collectRegistry({
      registry: NPM,
      quota: 10,
      perPage: 3,
      fetchImpl,
      sleep,
    })

    expect(sleep).toHaveBeenCalledWith(250)
    errorSpy.mockRestore()
  })
})

describe('collectRegistry: fetchImpl 自体が reject するケース', () => {
  // 実 fetch は ECONNRESET 等で Promise を reject することがあり、
  // 疑似 Response（jsonResponse）を返すだけのテストではこの経路が一切通らない
  // （try/catch を丸ごと消しても既存テストは全部緑のままになる・指摘 3）。
  it('reject を 5xx と同様にリトライし、成功すれば結果を返す', async () => {
    let calls = 0
    const fetchImpl = vi.fn(async () => {
      calls += 1
      if (calls <= 1) throw new Error('ECONNRESET')
      return jsonResponse(makePackages(2))
    })
    const sleep = vi.fn(noopSleep)

    const result = await collectRegistry({
      registry: NPM,
      quota: 10,
      perPage: 10,
      fetchImpl,
      sleep,
    })

    expect(result).toEqual(makePackages(2))
    expect(fetchImpl).toHaveBeenCalledTimes(2)
    expect(sleep).toHaveBeenNthCalledWith(1, 1000)
  })

  it('reject し続けたら指数バックオフで 3 回リトライし、最終的に例外を投げず空配列を返す', async () => {
    const fetchImpl = vi.fn(async () => {
      throw new Error('ECONNRESET')
    })
    const sleep = vi.fn(noopSleep)
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})

    const result = await collectRegistry({
      registry: NPM,
      quota: 10,
      perPage: 10,
      fetchImpl,
      sleep,
    })

    expect(result).toEqual([])
    // 初回 + 3 リトライ = 4 回
    expect(fetchImpl).toHaveBeenCalledTimes(4)
    expect(sleep).toHaveBeenNthCalledWith(1, 1000)
    expect(sleep).toHaveBeenNthCalledWith(2, 2000)
    expect(sleep).toHaveBeenNthCalledWith(3, 4000)
    expect(warnSpy).toHaveBeenCalled()
    warnSpy.mockRestore()
  })
})
