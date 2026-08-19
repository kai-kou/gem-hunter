import { compile, match } from 'path-to-regexp'
import { describe, expect, it } from 'vitest'

import {
  buildLocaleRedirectDestination,
  buildLocaleRedirectSource,
  localeRedirectExclusionPattern,
} from './locale-redirect'

const LOCALES = ['ja', 'en'] as const
const DEFAULT_LOCALE = 'ja'

/**
 * `next.config.ts` の `redirects()` `source` に渡る正規表現の実挙動を、
 * 実際に `RegExp` で評価して検証する（`:path(...)` が捕捉する「先頭の `/` を除いた文字列」を渡す）。
 */
function isRedirectTarget(pathWithoutLeadingSlash: string): boolean {
  const pattern = new RegExp(`^${localeRedirectExclusionPattern(LOCALES)}$`)
  return pattern.test(pathWithoutLeadingSlash)
}

describe('localeRedirectExclusionPattern', () => {
  it('ロケール接頭辞パス（/ja, /en/foo）はリダイレクト対象外', () => {
    expect(isRedirectTarget('ja')).toBe(false)
    expect(isRedirectTarget('en/foo')).toBe(false)
  })

  it('api・_next 配下はリダイレクト対象外', () => {
    expect(isRedirectTarget('api/x')).toBe(false)
    expect(isRedirectTarget('_next/static/a.js')).toBe(false)
  })

  it('末尾セグメントが静的ファイル拡張子のパスはリダイレクト対象外', () => {
    expect(isRedirectTarget('favicon.ico')).toBe(false)
  })

  it('ロケール接頭辞に似ているだけの非ロケールパスはリダイレクト対象', () => {
    expect(isRedirectTarget('january')).toBe(true)
  })

  it('パス途中にドットを含むが拡張子ではない（GitHub リポジトリ名等）パスはリダイレクト対象', () => {
    expect(isRedirectTarget('repos/foo/user.github.io')).toBe(true)
  })

  it('通常のアプリ内パスはリダイレクト対象', () => {
    expect(isRedirectTarget('repos/facebook/react')).toBe(true)
  })
})

/**
 * `buildLocaleRedirectSource` / `buildLocaleRedirectDestination` の組を、
 * OpenNext Cloudflare アダプタ（`@opennextjs/aws` の `routing/matcher.js`）が
 * 実際に行う `path-to-regexp` の `match(source)(path)` →
 * `compile(destination)(params)` の往復と同じ手順で評価する回帰テスト
 * （PR #96・プレビュー 500 障害の再発防止。ローカル `next start` は
 * Next.js 自身のルーティング（`compile()` を `{ validate: false }` で呼ぶ）
 * を使うため、この経路の破壊はローカルでは再現しない）。
 */
function redirectDestinationFor(pathWithLeadingSlash: string): string {
  const source = buildLocaleRedirectSource(LOCALES)
  const destination = buildLocaleRedirectDestination(DEFAULT_LOCALE)

  const matched = match(source)(pathWithLeadingSlash)
  if (!matched) {
    throw new Error(`source did not match: ${pathWithLeadingSlash}`)
  }
  // OpenNext と同じく、検証を無効化しない素の `compile()` を使う。
  return compile(destination)(matched.params)
}

describe('buildLocaleRedirectDestination（OpenNext の match→compile 往復）', () => {
  it('単一セグメントパスを例外なく変換できる', () => {
    expect(redirectDestinationFor('/about')).toBe('/ja/about')
  })

  it('スラッシュを含む多セグメントパスでも compile() が例外を投げない', () => {
    expect(redirectDestinationFor('/repos/foo/bar')).toBe('/ja/repos/foo/bar')
  })

  it('パス途中にドットを含む多セグメントパス（GitHub リポジトリ名）でも例外を投げない', () => {
    expect(redirectDestinationFor('/repos/foo/user.github.io')).toBe(
      '/ja/repos/foo/user.github.io',
    )
  })
})
