/**
 * registries.mjs — Gem 候補プールの収集対象レジストリ定義（`SP-17` / Issue #387）。
 *
 * 決定の正本は `docs/02_requirements/open-questions.md` の `D-36` / `D-37`。
 * `D-37` の **レジストリ別成層化**（各レジストリから被依存数降順で同数を取る固定枠）を
 * 前提に、対象を 12 レジストリへ固定する。母数比例枠は採らない
 * （npm が枠の大半を占め、1 レジストリ支配を再現するため）。
 *
 * `name` は Ecosyste.ms の registry 名（`GET /api/v1/registries` の `name`）そのもの。
 * 2026-08-22 に実 API で全 12 件の値と `ecosystem` を確認済み。
 */

/**
 * @typedef {Object} RegistryDef
 * @property {string} name       Ecosyste.ms の registry 名（API パスに載る値）
 * @property {string} ecosystem  Ecosyste.ms の ecosystem 名（表示・分類用）
 */

/**
 * 収集対象の 12 レジストリ（被依存数降順で同数ずつ取る固定枠の対象）。
 * 並び順はパッケージ総数の多い順ではなく、リサーチ記録
 * `docs/01_research/data/20260822-dependency-data-sources.md` §4 の記載順に合わせている。
 * @type {ReadonlyArray<RegistryDef>}
 */
export const REGISTRIES = Object.freeze([
  Object.freeze({ name: 'npmjs.org', ecosystem: 'npm' }),
  Object.freeze({ name: 'pypi.org', ecosystem: 'pypi' }),
  Object.freeze({ name: 'crates.io', ecosystem: 'cargo' }),
  Object.freeze({ name: 'rubygems.org', ecosystem: 'rubygems' }),
  Object.freeze({ name: 'packagist.org', ecosystem: 'packagist' }),
  Object.freeze({ name: 'proxy.golang.org', ecosystem: 'go' }),
  Object.freeze({ name: 'repo1.maven.org', ecosystem: 'maven' }),
  Object.freeze({ name: 'nuget.org', ecosystem: 'nuget' }),
  Object.freeze({ name: 'hex.pm', ecosystem: 'hex' }),
  Object.freeze({ name: 'pub.dev', ecosystem: 'pub' }),
  Object.freeze({ name: 'metacpan.org', ecosystem: 'cpan' }),
  Object.freeze({ name: 'cran.r-project.org', ecosystem: 'cran' }),
])

/**
 * レジストリ名を静的アセットのファイル名に使える slug へ変換する。
 *
 * `.` を含むレジストリ名（`npmjs.org` / `cran.r-project.org`）をそのままファイル名にすると
 * 拡張子と紛らわしく、パス区切りや大文字が混ざると配信先で事故るため、
 * **`[a-z0-9-]` 以外を残さない**（連続する非英数字は 1 つの `-` に畳む）。
 *
 * @param {string} name レジストリ名（例 `npmjs.org`）
 * @returns {string} slug（例 `npmjs-org` / `cran-r-project-org`）
 * @throws {TypeError} 文字列でない場合
 * @throws {Error} 変換結果が空になる場合（ファイル名として使えないため）
 */
export function registryFileSlug(name) {
  if (typeof name !== 'string') {
    throw new TypeError(
      `registryFileSlug には文字列を渡してください（受け取った型: ${typeof name}）`,
    )
  }
  const slug = name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
  if (slug === '') {
    throw new Error(`ファイル名に使える文字が残りません（入力: ${JSON.stringify(name)}）`)
  }
  return slug
}
