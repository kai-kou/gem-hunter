/**
 * registries.mjs — Gem 候補プールが対象とするパッケージレジストリの定義。
 *
 * Ecosyste.ms は 1 つの REST API で多数のレジストリを横断的に提供している
 * （`https://packages.ecosyste.ms/api/v1/registries/{name}/packages`）。
 * `id` は本プロジェクト内の短縮キー（出力ファイル名・CLI の `--registries` に使う）、
 * `name` は Ecosyste.ms 側の registry 名（実 API で名称確認済み・SP-17 契約 §2.1）。
 *
 * 🔴 順序は契約 §2.1 のまま維持する（出力の決定性・レビュー時の突合しやすさのため）。
 */

export const REGISTRIES = [
  { id: 'npm', name: 'npmjs.org' },
  { id: 'pypi', name: 'pypi.org' },
  { id: 'cargo', name: 'crates.io' },
  { id: 'rubygems', name: 'rubygems.org' },
  { id: 'packagist', name: 'packagist.org' },
  { id: 'go', name: 'proxy.golang.org' },
  { id: 'maven', name: 'repo1.maven.org' },
  { id: 'nuget', name: 'nuget.org' },
  { id: 'hex', name: 'hex.pm' },
  { id: 'pub', name: 'pub.dev' },
  { id: 'cpan', name: 'metacpan.org' },
  { id: 'cran', name: 'cran.r-project.org' },
]

// レジストリあたりの取得件数（固定枠・D-37）。
// Ecosyste.ms のページングで被依存数降順に取り、この件数に達したら打ち切る。
export const DEFAULT_QUOTA = 15000

export const DEFAULT_PER_PAGE = 1000

/**
 * id から RegistryDef を引く。未知 id は Error（静かに無視すると
 * `--registries` の typo が「0 件のレジストリを収集して正常終了」という
 * 一番気づきにくい壊れ方をするため、必ず例外にする）。
 */
export function findRegistry(id) {
  const found = REGISTRIES.find((r) => r.id === id)
  if (!found) {
    throw new Error(
      `未知のレジストリ id: ${id}（利用可能: ${REGISTRIES.map((r) => r.id).join(', ')}）`,
    )
  }
  return found
}
