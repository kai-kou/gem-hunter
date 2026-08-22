import { describe, expect, it } from 'vitest'

import {
  MAX_QUERY_LENGTH,
  MAX_QUERY_TOKENS,
  matchesAllTokens,
  selectMostSelectiveToken,
  tokenizeIdentifier,
  tokenizeQuery,
} from './gem-keyword'

describe('tokenizeIdentifier', () => {
  it('スコープ付き npm パッケージ名を `@` `/` で分割する', () => {
    expect(tokenizeIdentifier('@stdlib/bench')).toEqual(['stdlib', 'bench'])
  })

  it('Go モジュールパスを `.` `/` で分割する', () => {
    expect(tokenizeIdentifier('github.com/jackc/pgpassfile')).toEqual([
      'github',
      'com',
      'jackc',
      'pgpassfile',
    ])
  })

  it('大文字混在の repo 名を小文字化する', () => {
    expect(tokenizeIdentifier('RevolutionAnalytics/iterators')).toEqual([
      'revolutionanalytics',
      'iterators',
    ])
  })

  it('キャメルケースは分割しない（`D-37` は単語境界一致であって形態素解析ではない）', () => {
    // 仕様: `tensor` では `TensorRT` を引けない。区切り文字が無いものは 1 トークン。
    expect(tokenizeIdentifier('TensorRT')).toEqual(['tensorrt'])
  })

  it('連続した区切り文字で空トークンを作らない', () => {
    expect(tokenizeIdentifier('a--b__c..d')).toEqual(['a', 'b', 'c', 'd'])
  })

  it('前後の区切り文字を落とす', () => {
    expect(tokenizeIdentifier('/left-pad2/')).toEqual(['left', 'pad2'])
  })

  it('記号だけの入力は空配列にする（例外を投げない）', () => {
    expect(tokenizeIdentifier('---')).toEqual([])
    expect(tokenizeIdentifier('@/.')).toEqual([])
  })

  it('空文字は空配列にする', () => {
    expect(tokenizeIdentifier('')).toEqual([])
  })

  it('極端に長い入力でも例外を投げない', () => {
    const long = `${'a'.repeat(10_000)}/${'b'.repeat(10_000)}`
    expect(() => tokenizeIdentifier(long)).not.toThrow()
    expect(tokenizeIdentifier(long)).toHaveLength(2)
  })
})

describe('単語境界一致の回帰テスト（`D-37`）', () => {
  it('`orm` は `normalize` にマッチしない（部分一致ノイズを単語境界で消す）', () => {
    const haystack = tokenizeIdentifier('sindresorhus/normalize-url')
    expect(matchesAllTokens(haystack, tokenizeQuery('orm'))).toBe(false)
  })

  it('`cli` は `client` にマッチしない', () => {
    const haystack = tokenizeIdentifier('@octokit/rest-client')
    expect(matchesAllTokens(haystack, tokenizeQuery('cli'))).toBe(false)
  })

  it('単語として現れていればマッチする', () => {
    expect(matchesAllTokens(tokenizeIdentifier('doctrine/orm'), tokenizeQuery('orm'))).toBe(true)
    expect(matchesAllTokens(tokenizeIdentifier('cli/cli'), tokenizeQuery('cli'))).toBe(true)
  })
})

describe('tokenizeQuery', () => {
  it('複数語を空白で分割する', () => {
    expect(tokenizeQuery('image processing')).toEqual(['image', 'processing'])
  })

  it('連続空白・前後空白を無視する', () => {
    expect(tokenizeQuery('  image \t  processing \n')).toEqual(['image', 'processing'])
  })

  it('識別子と同じ正規化（小文字化・区切り分割）を通す', () => {
    expect(tokenizeQuery('Node.js Server')).toEqual(['node', 'js', 'server'])
  })

  it('重複トークンを畳む（順序は入力順を保つ）', () => {
    expect(tokenizeQuery('orm ORM tool orm')).toEqual(['orm', 'tool'])
  })

  it('空入力・記号だけの入力は空配列にする', () => {
    expect(tokenizeQuery('')).toEqual([])
    expect(tokenizeQuery('   ')).toEqual([])
    expect(tokenizeQuery('!!! ---')).toEqual([])
  })
})

describe('tokenizeQuery の上限（CPU 枯渇の防止・`F-01`）', () => {
  it(`トークン数が ${MAX_QUERY_TOKENS} 語を超えたら先頭から切り捨てる（例外にも 0 件にもしない）`, () => {
    const words = Array.from({ length: MAX_QUERY_TOKENS + 8 }, (_, i) => `w${i}`)

    const tokens = tokenizeQuery(words.join(' '))

    expect(tokens).toHaveLength(MAX_QUERY_TOKENS)
    expect(tokens).toEqual(words.slice(0, MAX_QUERY_TOKENS))
  })

  it(`ちょうど ${MAX_QUERY_TOKENS} 語は切り詰めない（境界）`, () => {
    const words = Array.from({ length: MAX_QUERY_TOKENS }, (_, i) => `w${i}`)

    expect(tokenizeQuery(words.join(' '))).toEqual(words)
  })

  it('重複を畳んだ後の語数で数える（同じ語を並べても上限に食われない）', () => {
    const query = Array.from({ length: MAX_QUERY_TOKENS + 50 }, () => 'orm').join(' ')

    expect(tokenizeQuery(query)).toEqual(['orm'])
  })

  it(`生値が ${MAX_QUERY_LENGTH} 文字を超えたら先に切る（区切りだけの長大入力で語数上限を素通りさせない）`, () => {
    // 1 語 1 文字 + 区切り 1 文字。上限文字数を超えた分は tokenize 前に落ちる。
    const raw = Array.from({ length: MAX_QUERY_LENGTH }, (_, i) => `${i % 10}`).join(' ')
    expect(raw.length).toBeGreaterThan(MAX_QUERY_LENGTH)

    const tokens = tokenizeQuery(raw)

    // 切り取った 256 文字の中に現れる 1 文字語は最大 10 種類（0〜9・重複は畳む）。
    expect(tokens.length).toBeLessThanOrEqual(10)
    expect(tokens.length).toBeGreaterThan(0)
  })

  it('切り詰めても既存の照合は壊れない（先頭側の語で従来どおり AND 一致する）', () => {
    const haystack = tokenizeIdentifier('doctrine/orm-tool')
    const noise = Array.from({ length: MAX_QUERY_TOKENS + 30 }, (_, i) => `zq${i}`).join(' ')

    expect(matchesAllTokens(haystack, tokenizeQuery('orm tool'))).toBe(true)
    // 上限を超えるノイズ語を後ろに並べても、先頭 2 語の解釈は変わらない。
    expect(tokenizeQuery(`orm tool ${noise}`).slice(0, 2)).toEqual(['orm', 'tool'])
  })

  it('上限は照合対象側（tokenizeIdentifier）には掛けない', () => {
    const identifier = Array.from({ length: MAX_QUERY_TOKENS + 10 }, (_, i) => `p${i}`).join('/')

    expect(tokenizeIdentifier(identifier)).toHaveLength(MAX_QUERY_TOKENS + 10)
  })
})

describe('matchesAllTokens', () => {
  it('全語が含まれていれば成立する（AND 一致）', () => {
    expect(matchesAllTokens(['image', 'magick', 'processing'], ['image', 'processing'])).toBe(true)
  })

  it('1 語でも欠けたら成立しない', () => {
    expect(matchesAllTokens(['image', 'magick'], ['image', 'processing'])).toBe(false)
  })

  it('空トークン列は常に成立する（絞り込みなし）', () => {
    expect(matchesAllTokens(['image'], [])).toBe(true)
    expect(matchesAllTokens([], [])).toBe(true)
  })

  it('空の haystack はトークンがあれば成立しない', () => {
    expect(matchesAllTokens([], ['image'])).toBe(false)
  })
})

describe('selectMostSelectiveToken', () => {
  it('単独ヒット件数が最小のトークンを返す', () => {
    const counts = new Map([
      ['image', 500],
      ['processing', 3],
    ])
    expect(selectMostSelectiveToken(counts)).toBe('processing')
  })

  it('0 件のトークンは選ばない（緩めても 0 件になるため）', () => {
    const counts = new Map([
      ['machine', 0],
      ['learning', 7],
    ])
    expect(selectMostSelectiveToken(counts)).toBe('learning')
  })

  it('同数のタイブレークは決定論（トークン昇順）', () => {
    const counts = new Map([
      ['beta', 2],
      ['alpha', 2],
      ['gamma', 2],
    ])
    expect(selectMostSelectiveToken(counts)).toBe('alpha')
    // 入力順を変えても同じ結果になる
    const reordered = new Map([
      ['gamma', 2],
      ['alpha', 2],
      ['beta', 2],
    ])
    expect(selectMostSelectiveToken(reordered)).toBe('alpha')
  })

  it('どのトークンも 0 件なら null', () => {
    expect(selectMostSelectiveToken(new Map([['a', 0]]))).toBeNull()
  })

  it('空の Map なら null', () => {
    expect(selectMostSelectiveToken(new Map())).toBeNull()
  })
})
