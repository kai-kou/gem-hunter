import { describe, expect, it } from 'vitest'

import { readSeen, writeSeen } from './seen-digest-store'

/** テスト用のフェイク `Storage`（Map ベース）。 */
function makeFakeStorage(initial: Record<string, string> = {}): Storage {
  const map = new Map(Object.entries(initial))
  return {
    getItem: (key: string) => map.get(key) ?? null,
    setItem: (key: string, value: string) => {
      map.set(key, value)
    },
    removeItem: (key: string) => {
      map.delete(key)
    },
    clear: () => map.clear(),
    key: (index: number) => Array.from(map.keys())[index] ?? null,
    get length() {
      return map.size
    },
  }
}

/** `getItem` / `setItem` が常に throw するフェイク（Safari プライベートモード相当）。 */
function makeThrowingStorage(): Storage {
  return {
    getItem: () => {
      throw new Error('SecurityError')
    },
    setItem: () => {
      throw new Error('QuotaExceededError')
    },
    removeItem: () => undefined,
    clear: () => undefined,
    key: () => null,
    length: 0,
  }
}

describe('readSeen', () => {
  it('ストレージが空（未保存）のとき null を返す', () => {
    const storage = makeFakeStorage()
    expect(readSeen(storage)).toBeNull()
  })

  it('保存済みの妥当な JSON があれば SeenDigest を返す', () => {
    const storage = makeFakeStorage({
      'gem-hunter:seen-digest': JSON.stringify({ date: '20260819', packageNames: ['chalk'] }),
    })

    expect(readSeen(storage)).toEqual({ date: '20260819', packageNames: ['chalk'] })
  })

  it('JSON として壊れている値は null を返す（例外を投げない）', () => {
    const storage = makeFakeStorage({ 'gem-hunter:seen-digest': '{invalid-json' })
    expect(readSeen(storage)).toBeNull()
  })

  it('型が一致しない値（packageNames が文字列配列でない等）は null を返す', () => {
    const storage = makeFakeStorage({
      'gem-hunter:seen-digest': JSON.stringify({ date: '20260819', packageNames: [1, 2] }),
    })
    expect(readSeen(storage)).toBeNull()

    const storage2 = makeFakeStorage({
      'gem-hunter:seen-digest': JSON.stringify({ notDate: true }),
    })
    expect(readSeen(storage2)).toBeNull()
  })

  it('getItem が throw する（Safari プライベートモード等）場合も null を返す', () => {
    expect(readSeen(makeThrowingStorage())).toBeNull()
  })

  it('storage 未指定時に globalThis.localStorage が無ければ null を返す', () => {
    const original = globalThis.localStorage
    // @ts-expect-error テストのため一時的に削除する
    delete globalThis.localStorage
    try {
      expect(readSeen()).toBeNull()
    } finally {
      globalThis.localStorage = original
    }
  })
})

describe('writeSeen', () => {
  it('SeenDigest を JSON 文字列としてストレージへ保存する', () => {
    const storage = makeFakeStorage()
    writeSeen({ date: '20260820', packageNames: ['chalk', 'debug'] }, storage)

    expect(storage.getItem('gem-hunter:seen-digest')).toBe(
      JSON.stringify({ date: '20260820', packageNames: ['chalk', 'debug'] }),
    )
  })

  it('setItem が throw しても例外を外へ投げない（no-op）', () => {
    const storage = makeThrowingStorage()
    expect(() => writeSeen({ date: '20260820', packageNames: [] }, storage)).not.toThrow()
  })

  it('storage 未指定時に globalThis.localStorage が無ければ何もしない', () => {
    const original = globalThis.localStorage
    // @ts-expect-error テストのため一時的に削除する
    delete globalThis.localStorage
    try {
      expect(() => writeSeen({ date: '20260820', packageNames: [] })).not.toThrow()
    } finally {
      globalThis.localStorage = original
    }
  })

  it('storage 未指定時は globalThis.localStorage（jsdom）へ書き込む', () => {
    globalThis.localStorage.removeItem('gem-hunter:seen-digest')
    writeSeen({ date: '20260820', packageNames: ['chalk'] })
    expect(globalThis.localStorage.getItem('gem-hunter:seen-digest')).toBe(
      JSON.stringify({ date: '20260820', packageNames: ['chalk'] }),
    )
    globalThis.localStorage.removeItem('gem-hunter:seen-digest')
  })
})
