import { describe, expect, it } from 'vitest'

import { searchQuery } from '../../domain/model/search-query'
import { CACHE_SCHEMA_VERSION, repositoryCacheKey, searchResultCacheKey } from './cache-key'

describe('searchResultCacheKey', () => {
  it('検索結果は search 名前空間になる', () => {
    const key = searchResultCacheKey(searchQuery({ keyword: 'gem hunter' }))
    expect(key.startsWith('search:')).toBe(true)
  })

  it('キーワードの前後空白・大文字小文字の違いは同じキーに正規化される', () => {
    const a = searchResultCacheKey(searchQuery({ keyword: '  Next.js  ' }))
    const b = searchResultCacheKey(searchQuery({ keyword: 'next.js' }))
    expect(a).toBe(b)
  })

  it('ページ番号が異なれば別キーになる', () => {
    const page1 = searchResultCacheKey(searchQuery({ keyword: 'next', page: 1 }))
    const page2 = searchResultCacheKey(searchQuery({ keyword: 'next', page: 2 }))
    expect(page1).not.toBe(page2)
  })

  it('キーワードが異なれば別キーになる', () => {
    const a = searchResultCacheKey(searchQuery({ keyword: 'foo' }))
    const b = searchResultCacheKey(searchQuery({ keyword: 'bar' }))
    expect(a).not.toBe(b)
  })

  // フィールドが増えたら `searchResultCacheKey` の構成要素を見直す（NFR-18）。
  it('SearchQuery のフィールド集合は keyword / page / sort / perPage の 4 つである（増えたら searchResultCacheKey の更新漏れを検知するガード）', () => {
    const query = searchQuery({ keyword: 'x' })
    expect(Object.keys(query).sort()).toEqual(['keyword', 'page', 'perPage', 'sort'])
  })

  it('ソート順が異なれば別キーになる（AR-2: キャッシュ断片化防止のため構成要素に含める）', () => {
    const relevance = searchResultCacheKey(searchQuery({ keyword: 'next', sort: 'stars' }))
    const updated = searchResultCacheKey(searchQuery({ keyword: 'next', sort: 'updated' }))
    expect(relevance).not.toBe(updated)
  })

  it('表示件数が異なれば別キーになる（AR-3: キャッシュ断片化防止のため構成要素に含める）', () => {
    const perPage20 = searchResultCacheKey(searchQuery({ keyword: 'next', perPage: 20 }))
    const perPage50 = searchResultCacheKey(searchQuery({ keyword: 'next', perPage: 50 }))
    expect(perPage20).not.toBe(perPage50)
  })
})

describe('repositoryCacheKey', () => {
  it('単一リポジトリは repository 名前空間になる（search とキーが衝突しない）', () => {
    const key = repositoryCacheKey('facebook', 'react')
    expect(key.startsWith('repository:')).toBe(true)
  })

  it('owner/name の大文字小文字・前後空白は正規化される', () => {
    const a = repositoryCacheKey('  Facebook  ', 'React')
    const b = repositoryCacheKey('facebook', 'react')
    expect(a).toBe(b)
  })

  it('owner が異なれば別キーになる', () => {
    const a = repositoryCacheKey('facebook', 'react')
    const b = repositoryCacheKey('vuejs', 'react')
    expect(a).not.toBe(b)
  })

  it('name が異なれば別キーになる', () => {
    const a = repositoryCacheKey('facebook', 'react')
    const b = repositoryCacheKey('facebook', 'relay')
    expect(a).not.toBe(b)
  })

  it('利用者識別子を含まない（NFR-18）', () => {
    const key = repositoryCacheKey('facebook', 'react')
    expect(key).not.toMatch(/viewer|user|session/i)
  })

  it('検索結果のキーと衝突しない（NFR-18: 名前空間分離）', () => {
    const searchKey = searchResultCacheKey(searchQuery({ keyword: 'react' }))
    const repoKey = repositoryCacheKey('facebook', 'react')
    expect(searchKey).not.toBe(repoKey)
  })

  it('合成済み文字と分解形の Unicode 表現は同じキーに正規化される（NFC 正規化）', () => {
    const composedOwner = 'caf\u00e9' // \u00e9 = U+00E9（合成済み）
    const decomposedOwner = 'caf\u0065\u0301' // e + U+0301（結合文字による分解形）
    expect(composedOwner).not.toBe(decomposedOwner) // 前提: 2 つの入力は文字列として異なる

    const composed = repositoryCacheKey(composedOwner, 'react')
    const decomposed = repositoryCacheKey(decomposedOwner, 'react')
    expect(composed).toBe(decomposed)
  })
})

describe('CACHE_SCHEMA_VERSION', () => {
  it('スキーマバージョンは v から始まる非空の識別子である', () => {
    expect(CACHE_SCHEMA_VERSION).toMatch(/^v\d+$/)
  })

  it('検索結果のキーは名前空間の直後にスキーマバージョンを含む', () => {
    const key = searchResultCacheKey(searchQuery({ keyword: 'next' }))
    expect(key.startsWith(`search:${CACHE_SCHEMA_VERSION}:`)).toBe(true)
  })

  it('単一リポジトリのキーは名前空間の直後にスキーマバージョンを含む', () => {
    const key = repositoryCacheKey('facebook', 'react')
    expect(key.startsWith(`repository:${CACHE_SCHEMA_VERSION}:`)).toBe(true)
  })

  it('スキーマバージョン導入後もキーワードの正規化（トリム・小文字化）は保たれる', () => {
    const a = searchResultCacheKey(searchQuery({ keyword: '  Next.js  ' }))
    const b = searchResultCacheKey(searchQuery({ keyword: 'next.js' }))
    expect(a).toBe(b)
    expect(a).toBe(`search:${CACHE_SCHEMA_VERSION}:next.js:page=1:sort=stars:per_page=20`)
  })

  it('スキーマバージョン導入後も owner/name の正規化・エンコードは保たれる', () => {
    const key = repositoryCacheKey('  Face book  ', 'React')
    expect(key).toBe(`repository:${CACHE_SCHEMA_VERSION}:face%20book/react`)
  })

  it('スキーマバージョンが変わると同じ入力でも別キーになる（旧エントリを論理的に無効化できる）', () => {
    const key = searchResultCacheKey(searchQuery({ keyword: 'next' }))
    const legacyKey = key.replace(`:${CACHE_SCHEMA_VERSION}:`, ':v0:')
    expect(key).not.toBe(legacyKey)
  })
})
