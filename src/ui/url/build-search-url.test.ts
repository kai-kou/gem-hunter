import { describe, expect, it } from 'vitest'

import { buildSearchUrl } from './build-search-url'

describe('buildSearchUrl', () => {
  it('全項目が既定値のときはクエリなしの basePath を返す', () => {
    expect(buildSearchUrl('/ja', { keyword: '', page: 1, sort: 'relevance', perPage: 20 })).toBe(
      '/ja',
    )
  })

  it('keyword を q として載せる', () => {
    expect(
      buildSearchUrl('/ja', { keyword: 'react', page: 1, sort: 'relevance', perPage: 20 }),
    ).toBe('/ja?q=react')
  })

  it('既定値と異なる page/sort/perPage だけをクエリへ載せる', () => {
    const url = buildSearchUrl('/ja', {
      keyword: 'react',
      page: 2,
      sort: 'stars',
      perPage: 50,
    })
    const params = new URLSearchParams(url.split('?')[1])

    expect(params.get('q')).toBe('react')
    expect(params.get('page')).toBe('2')
    expect(params.get('sort')).toBe('stars')
    expect(params.get('per_page')).toBe('50')
  })

  it('basePath を空文字にするとクエリ文字列だけ（先頭 ? 付き）を返す', () => {
    expect(buildSearchUrl('', { keyword: 'react', page: 3, sort: 'relevance', perPage: 20 })).toBe(
      '?q=react&page=3',
    )
  })

  it('basePath を空文字にし全項目既定値なら空文字を返す（パス継ぎ足し用途で ? だけ付かない）', () => {
    expect(buildSearchUrl('', { keyword: '', page: 1, sort: 'relevance', perPage: 20 })).toBe('')
  })

  it('往復しても同じ状態に戻る（既定値省略は tryParse 側の既定値と一致する）', () => {
    const url = buildSearchUrl('/ja', { keyword: '', page: 1, sort: 'relevance', perPage: 100 })
    expect(url).toBe('/ja?per_page=100')
  })
  describe('extraParams（検索 4 条件以外の付帯パラメータ）', () => {
    it('検索条件の後ろに付帯パラメータを載せる', () => {
      const url = buildSearchUrl(
        '',
        { keyword: 'left pad', page: 3, sort: 'relevance', perPage: 20 },
        { from: 'gems' },
      )
      const params = new URLSearchParams(url.split('?')[1])

      expect(params.get('q')).toBe('left pad')
      expect(params.get('page')).toBe('3')
      expect(params.get('from')).toBe('gems')
    })

    it('検索条件が全て既定値でも付帯パラメータがあればクエリを返す', () => {
      expect(
        buildSearchUrl(
          '',
          { keyword: '', page: 1, sort: 'relevance', perPage: 20 },
          { from: 'gems' },
        ),
      ).toBe('?from=gems')
    })

    it('空文字の付帯パラメータは載せない', () => {
      expect(
        buildSearchUrl(
          '/ja',
          { keyword: '', page: 1, sort: 'relevance', perPage: 20 },
          { from: '' },
        ),
      ).toBe('/ja')
    })
  })
})
