// 相対 import を使う（`@/` エイリアス）。`next.config.ts` は SWC の require hook で
// このファイルを直接 require するが、ネストしたファイルではエイリアス解決が
// 正しく計算されず `Cannot find module './src/domain/model/locale'` になる
// （next.config.ts 自身からの相対パスとして誤って解決される・実機検証済み）。
import { LOCALES } from '../../domain/model/locale'

/**
 * 静的アセットとして扱う拡張子（末尾セグメントの拡張子判定にのみ使う）。
 * `owner.github.io` のような、ドットを含むが拡張子ではない GitHub リポジトリ名
 * （US-9 / `repos/[owner]/[repo]` ルート）を誤って除外しないよう、
 * 「パスにドットが含まれるか」ではなく「既知の拡張子で終わるか」で判定する。
 */
const STATIC_FILE_EXTENSIONS = [
  'ico',
  'png',
  'jpg',
  'jpeg',
  'gif',
  'svg',
  'webp',
  'avif',
  'css',
  'js',
  'mjs',
  'json',
  'xml',
  'txt',
  'map',
  'woff',
  'woff2',
  'ttf',
  'otf',
  'eot',
  'wasm',
  'pdf',
] as const

/**
 * ロケール接頭辞リダイレクト対象パスの正規表現パターン（`next.config.ts` の
 * `redirects()` の `source` にそのまま渡せる文字列・純粋関数）。
 * ロケール接頭辞（/ja, /en, ...）・`_next` 配下・`api` 配下・
 * 末尾セグメントが静的ファイル拡張子のパスを除く全パスにマッチする。
 */
export function localeRedirectExclusionPattern(
  locales: readonly string[] = LOCALES,
): string {
  const localeAlternation = locales.join('|')
  const extensionAlternation = STATIC_FILE_EXTENSIONS.join('|')

  return (
    `(?!(?:${localeAlternation})(?:/|$))` +
    `(?!_next(?:/|$))` +
    `(?!api(?:/|$))` +
    `(?!.*\\.(?:${extensionAlternation})$)` +
    `.*`
  )
}

/** `next.config.ts` の `redirects()` にそのまま渡せる `source` 文字列。 */
export function buildLocaleRedirectSource(locales: readonly string[] = LOCALES): string {
  return `/:path(${localeRedirectExclusionPattern(locales)})`
}

/**
 * `next.config.ts` の `redirects()` にそのまま渡せる `destination` 文字列
 * （PR #96・プレビュー 500 障害の修正）。
 *
 * `:path` を素のトークンのまま宛先に書くと、Cloudflare プレビュー
 * （OpenNext Cloudflare アダプタ = `@opennextjs/aws` の
 * `dist/core/routing/matcher.js` `handleRewrites()`）が `path-to-regexp` の
 * `compile()` を **検証オプション既定（`validate` 省略 = true）** で呼ぶため、
 * 宛先側の `:path` はデフォルトパターン `[^\/#\?]+?`（スラッシュを含まない
 * 単一セグメントのみ）で値を検証してしまう。`source` 側の `:path(...)` は
 * スラッシュを含む多セグメント値（例: `repos/foo/bar`）を正しく捕捉できるが、
 * その値を宛先の素の `:path` に渡すと `compile()` が
 * `TypeError: Expected "path" to match "[^\/#\?]+?", but got "repos/foo/bar"`
 * を投げ、`routingHandler` の catch 節が `/500` を返す（実機検証済み）。
 *
 * ローカルの `next start`（Next.js 自身のルーティング。
 * `shared/lib/router/utils/prepare-destination.js` の `compileNonPath` は
 * `path-to-regexp` の `compile()` を `{ validate: false }` で呼ぶため
 * この検証に引っかからない）では再現しないため見落としやすい。
 *
 * 対策として宛先の `:path` にも「任意文字列」を許すカスタムパターン `(.*)` を
 * 明示し、`compile()` の検証を通す。
 */
export function buildLocaleRedirectDestination(defaultLocale: string): string {
  return `/${defaultLocale}/:path(.*)`
}
