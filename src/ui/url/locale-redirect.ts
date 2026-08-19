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
