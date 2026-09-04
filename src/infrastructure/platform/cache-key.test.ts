import { describe, expect, it } from 'vitest'

import { searchQuery } from '../../domain/model/search-query'
import {
  CACHE_SCHEMA_VERSION,
  readmeCacheKey,
  readmeEtagCacheKey,
  repositoryCacheKey,
  repositoryEtagCacheKey,
  searchResultCacheKey,
} from './cache-key'

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

describe('readmeCacheKey', () => {
  it('README は readme 名前空間になる（repository と衝突しない）', () => {
    const key = readmeCacheKey('facebook', 'react')
    expect(key.startsWith('readme:')).toBe(true)
  })

  it('owner/name の大文字小文字・前後空白は正規化される', () => {
    const a = readmeCacheKey('  Facebook  ', 'React')
    const b = readmeCacheKey('facebook', 'react')
    expect(a).toBe(b)
  })

  it('owner が異なれば別キーになる', () => {
    const a = readmeCacheKey('facebook', 'react')
    const b = readmeCacheKey('vuejs', 'react')
    expect(a).not.toBe(b)
  })

  it('単一リポジトリのキー（repository 名前空間）と衝突しない', () => {
    const readmeKey = readmeCacheKey('facebook', 'react')
    const repoKey = repositoryCacheKey('facebook', 'react')
    expect(readmeKey).not.toBe(repoKey)
  })
})

describe('repositoryEtagCacheKey / readmeEtagCacheKey（Issue #170: ETag エントリの名前空間）', () => {
  it('repositoryEtagCacheKey は repository-etag 名前空間になる', () => {
    const key = repositoryEtagCacheKey('facebook', 'react')
    expect(key.startsWith('repository-etag:')).toBe(true)
  })

  it('readmeEtagCacheKey は readme-etag 名前空間になる', () => {
    const key = readmeEtagCacheKey('facebook', 'react')
    expect(key.startsWith('readme-etag:')).toBe(true)
  })

  it('repositoryEtagCacheKey は本文キャッシュ（repositoryCacheKey）と衝突しない', () => {
    const etagKey = repositoryEtagCacheKey('facebook', 'react')
    const bodyKey = repositoryCacheKey('facebook', 'react')
    expect(etagKey).not.toBe(bodyKey)
  })

  it('readmeEtagCacheKey は本文キャッシュ（readmeCacheKey）と衝突しない', () => {
    const etagKey = readmeEtagCacheKey('facebook', 'react')
    const bodyKey = readmeCacheKey('facebook', 'react')
    expect(etagKey).not.toBe(bodyKey)
  })

  it('repositoryEtagCacheKey と readmeEtagCacheKey も衝突しない', () => {
    const repoEtag = repositoryEtagCacheKey('facebook', 'react')
    const readmeEtag = readmeEtagCacheKey('facebook', 'react')
    expect(repoEtag).not.toBe(readmeEtag)
  })

  it('owner/name の正規化は本文キャッシュと同じ規則に従う', () => {
    const a = repositoryEtagCacheKey('  Facebook  ', 'React')
    const b = repositoryEtagCacheKey('facebook', 'react')
    expect(a).toBe(b)
  })
})

describe('CACHE_SCHEMA_VERSION', () => {
  /**
   * 🔴 期待値はすべて文字列リテラルで固定する（`CACHE_SCHEMA_VERSION` から組み立てない）。
   *    バージョンを埋め込む自己参照の期待値だと、bump を巻き戻しても全テストが緑のままになり、
   *    「既存キャッシュを論理的に無効化した」という意図をテストが守れない。
   *
   * 🔴 **bump するときは、この describe のリテラル（`v2` の箇所）も一緒に更新すること。**
   *    そのひと手間が「バージョンを上げたのは意図的である」という明示になる。
   */
  it('現在のスキーマバージョンは v2 である（巻き戻し・意図しない変更を検出するガード）', () => {
    expect(CACHE_SCHEMA_VERSION).toBe('v2')
  })

  it('検索結果のキーは名前空間の直後にスキーマバージョンを含む', () => {
    const key = searchResultCacheKey(searchQuery({ keyword: 'next' }))
    expect(key).toBe('search:v2:next:page=1:sort=relevance:per_page=20')
  })

  it('単一リポジトリのキーは名前空間の直後にスキーマバージョンを含む', () => {
    const key = repositoryCacheKey('facebook', 'react')
    expect(key).toBe('repository:v2:facebook/react')
  })

  it('README のキーは名前空間の直後にスキーマバージョンを含む', () => {
    const key = readmeCacheKey('facebook', 'react')
    expect(key).toBe('readme:v2:facebook/react')
  })

  it('スキーマバージョン導入後もキーワードの正規化（トリム・小文字化）は保たれる', () => {
    const a = searchResultCacheKey(
      searchQuery({ keyword: '  Next.js  ', page: 1, sort: 'stars', perPage: 20 }),
    )
    const b = searchResultCacheKey(
      searchQuery({ keyword: 'next.js', page: 1, sort: 'stars', perPage: 20 }),
    )
    expect(a).toBe(b)
    expect(a).toBe('search:v2:next.js:page=1:sort=stars:per_page=20')
  })

  it('スキーマバージョン導入後も owner/name の正規化・エンコードは保たれる', () => {
    const key = repositoryCacheKey('  Face book  ', 'React')
    expect(key).toBe('repository:v2:face%20book/react')
  })
})
