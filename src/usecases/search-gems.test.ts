import { describe, expect, it } from 'vitest'

import type { DigestMeta } from '../domain/model/gem'
import type {
  GemIndexPort,
  GemPoolSearchInput,
  GemPoolSearchResult,
} from '../domain/ports/gem-index-port'
import { DEFAULT_PAGE, MAX_PAGE } from '../domain/model/page-number'
import { DEFAULT_PER_PAGE } from '../domain/model/per-page'
import { makeSearchGems } from './search-gems'

const meta: DigestMeta = {
  source: 'Ecosyste.ms',
  sourceUrl: 'https://ecosyste.ms/',
  license: 'CC BY-SA 4.0',
  sourceLicenseUrl: 'https://creativecommons.org/licenses/by-sa/4.0/',
  generatedAt: '2026-08-22T06:04:21.791Z',
}

const emptyResult: GemPoolSearchResult = {
  items: [],
  totalCount: 0,
  usedTokens: [],
  relaxed: false,
  meta,
}

/**
 * `GemIndexPort` のフェイク。`vi.mock` は使わない（`architecture-rules.md` §4:
 * 上位層のテストでモックしたくなったら設計を直す＝フェイクのポート実装を渡す）。
 */
function fakePort(received: GemPoolSearchInput[]): GemIndexPort {
  return {
    async lookup() {
      return new Map()
    },
    async search(input) {
      received.push(input)
      return emptyResult
    },
  }
}

describe('searchGems', () => {
  it('検索語をトークン列へ正規化してポートへ渡す（単語境界で分割・小文字化）', async () => {
    const received: GemPoolSearchInput[] = []
    const searchGems = makeSearchGems({ gems: fakePort(received) })

    await searchGems({ query: '  Kafka-Client  ' })

    expect(received).toHaveLength(1)
    expect(received[0].tokens).toEqual(['kafka', 'client'])
  })

  it('ページ・表示件数を省略すると既定値でポートを呼ぶ', async () => {
    const received: GemPoolSearchInput[] = []
    const searchGems = makeSearchGems({ gems: fakePort(received) })

    await searchGems({ query: 'kafka' })

    expect(received[0].page).toBe(DEFAULT_PAGE)
    expect(received[0].perPage).toBe(DEFAULT_PER_PAGE)
  })

  it('URL 由来の生値（文字列）を受け取り、値オブジェクトへ変換してから渡す', async () => {
    const received: GemPoolSearchInput[] = []
    const searchGems = makeSearchGems({ gems: fakePort(received) })

    await searchGems({ query: 'kafka', page: '3', perPage: '50' })

    expect(received[0].page).toBe(3)
    expect(received[0].perPage).toBe(50)
  })

  it('不正なページ・表示件数は例外にせず既定値へ倒す（URL 改変で 500 にしない）', async () => {
    const received: GemPoolSearchInput[] = []
    const searchGems = makeSearchGems({ gems: fakePort(received) })

    await searchGems({ query: 'kafka', page: '-1', perPage: '7' })

    expect(received[0].page).toBe(DEFAULT_PAGE)
    expect(received[0].perPage).toBe(DEFAULT_PER_PAGE)
  })

  it('到達可能な最終ページを超える指定も既定ページへ倒す', async () => {
    const received: GemPoolSearchInput[] = []
    const searchGems = makeSearchGems({ gems: fakePort(received) })

    await searchGems({ query: 'kafka', page: MAX_PAGE + 1 })

    expect(received[0].page).toBe(DEFAULT_PAGE)
  })

  it('検索語が空・記号だけならトークン空配列（＝絞り込みなし）で渡す', async () => {
    const received: GemPoolSearchInput[] = []
    const searchGems = makeSearchGems({ gems: fakePort(received) })

    await searchGems({ query: '  --  ' })

    expect(received[0].tokens).toEqual([])
  })

  it('ポートの結果をそのまま返す（並べ替え・絞り込みを二重に行わない）', async () => {
    const searchGems = makeSearchGems({ gems: fakePort([]) })

    const result = await searchGems({ query: 'kafka' })

    expect(result).toBe(emptyResult)
  })
})
