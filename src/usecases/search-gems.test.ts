import { describe, expect, it } from 'vitest'

import type { DigestMeta } from '../domain/model/gem'
import { gemIndex } from '../domain/model/gem-index'
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
 * 「絞り込みなし＝全件」でポートが返してくる結果の縮小版（`tokens: []` のときの契約）。
 * 実データでは 62,483 件が返る。ここでは 1 件で「全件が素通しされていないこと」を見る。
 */
const allEntriesResult: GemPoolSearchResult = {
  items: [
    {
      packageName: 'left-pad',
      repositoryFullName: 'stevemao/left-pad',
      dependentCount: 12345,
      stars: 1234,
      gemIndex: gemIndex(-42.5),
      registry: 'npmjs.org',
    },
  ],
  totalCount: 62483,
  usedTokens: [],
  relaxed: false,
  meta,
}

/**
 * `GemIndexPort` のフェイク。`vi.mock` は使わない（`architecture-rules.md` §4:
 * 上位層のテストでモックしたくなったら設計を直す＝フェイクのポート実装を渡す）。
 */
function fakePort(
  received: GemPoolSearchInput[],
  result: GemPoolSearchResult = emptyResult,
): GemIndexPort {
  return {
    async lookup() {
      return new Map()
    },
    async search(input) {
      received.push(input)
      return result
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

    // 照合可否のフラグだけを積み増し、items は同一参照のまま（並べ替え直していない）。
    expect(result).toEqual({ ...emptyResult, unmatchableQuery: false })
    expect(result.items).toBe(emptyResult.items)
  })

  /**
   * 🔴 日本語だけの検索語は `tokenizeQuery` が空配列を返すため、ポートの契約では
   * 「絞り込みなし＝全件」になる。画面が「『画像処理』の Gem」と名乗って候補プール全件
   * （実測 62,483 件）を出すのは端的な誤表示なので、ユースケースが 0 件へ倒す。
   */
  it('日本語だけの検索語は全件ではなく 0 件へ倒し、照合不能として識別できる', async () => {
    const received: GemPoolSearchInput[] = []
    const searchGems = makeSearchGems({ gems: fakePort(received, allEntriesResult) })

    const result = await searchGems({ query: '画像処理' })

    expect(result.unmatchableQuery).toBe(true)
    expect(result.totalCount).toBe(0)
    expect(result.items).toEqual([])
    expect(result.usedTokens).toEqual([])
    expect(result.relaxed).toBe(false)
    // 出典表示は 0 件の画面でも出す（`D-29` / `GR-6`）ため、メタデータは捨てない。
    expect(result.meta).toEqual(meta)
  })

  it('ASCII を含む検索語は従来どおり絞り込む（照合不能にしない）', async () => {
    const received: GemPoolSearchInput[] = []
    const searchGems = makeSearchGems({ gems: fakePort(received, allEntriesResult) })

    const result = await searchGems({ query: 'JSON パーサー' })

    expect(received[0].tokens).toEqual(['json'])
    expect(result.unmatchableQuery).toBe(false)
    expect(result.totalCount).toBe(allEntriesResult.totalCount)
    expect(result.items).toBe(allEntriesResult.items)
  })

  it('空文字・空白だけの検索語は従来どおりの扱い（照合不能にしない・呼び出し側が先に弾く）', async () => {
    const received: GemPoolSearchInput[] = []
    const searchGems = makeSearchGems({ gems: fakePort(received, allEntriesResult) })

    const blank = await searchGems({ query: '   ' })
    const empty = await searchGems({ query: '' })

    expect(received[0].tokens).toEqual([])
    expect(blank.unmatchableQuery).toBe(false)
    expect(blank.totalCount).toBe(allEntriesResult.totalCount)
    expect(empty.unmatchableQuery).toBe(false)
  })

  it('記号だけの検索語は照合不能として扱う（英数字の識別子を 1 語も取り出せない）', async () => {
    const searchGems = makeSearchGems({ gems: fakePort([], allEntriesResult) })

    const result = await searchGems({ query: '--' })

    expect(result.unmatchableQuery).toBe(true)
    expect(result.totalCount).toBe(0)
  })
})
