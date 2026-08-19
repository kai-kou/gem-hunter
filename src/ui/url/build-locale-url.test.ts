import { describe, expect, it } from 'vitest'

import { locale } from '../../domain/model/locale'
import { buildLocaleUrl } from './build-locale-url'

describe('buildLocaleUrl', () => {
  it('ルート（クエリなし）の言語プレフィックスだけを差し替える', () => {
    expect(buildLocaleUrl('/ja', locale('en'))).toBe('/en')
  })

  it('詳細ページ等、複数セグメントのパスも言語プレフィックスだけを差し替える', () => {
    expect(buildLocaleUrl('/ja/repos/octostub/octo-widgets', locale('en'))).toBe(
      '/en/repos/octostub/octo-widgets',
    )
  })

  it('クエリパラメータ（検索条件）を保持したまま言語プレフィックスだけを差し替える（SP-7 と同じ検索条件保持方針）', () => {
    expect(buildLocaleUrl('/ja?q=react&page=2', locale('en'))).toBe('/en?q=react&page=2')
  })

  it('複数セグメント + クエリの組み合わせでも言語プレフィックスだけを差し替える', () => {
    expect(buildLocaleUrl('/ja/repos/octostub/octo-widgets?from=list', locale('en'))).toBe(
      '/en/repos/octostub/octo-widgets?from=list',
    )
  })

  it('現在と同じロケールを指定すると同じ URL を返す（現在地リンクとして使える）', () => {
    expect(buildLocaleUrl('/ja/repos/octostub/octo-widgets', locale('ja'))).toBe(
      '/ja/repos/octostub/octo-widgets',
    )
  })
})
