import type { GemIndex } from '../model/gem-index'

/**
 * Gem 候補プール（レジストリ別シャードの全量・`D-38`）に対する照会口（`SP-18`）。
 *
 * 検索結果（GitHub Search API）に Gem バッジを出すため、**リポジトリ名の集合を渡して
 * プールに載っているものだけを引く** ための最小面（`lookup()` 1 本・YAGNI）。
 * プール全量の配信・キャッシュ方式（静的アセットの並列取得 + isolate 内メモリ）は
 * インフラ側の関心であり、ここには漏らさない。
 *
 * ⚠️ `GemDigestPort` は「上位 N 件のスライス」を返す別のポートで、母集団が違う
 * （`gem-digest-port.ts` の注記を参照）。バッジ判定にダイジェストの候補を使わない。
 */
export interface GemIndexPort {
  /**
   * 与えた `repositoryFullName` 群のうち、Gem 候補プールに載っているものだけを返す。
   *
   * - 返り値のキーは **入力で渡された文字列そのもの**（呼び出し側が `map.get(item.fullName)`
   *   でそのまま引ける。プール側の綴りへ読み替える責務を呼び出し側に持たせない）
   * - 照合は **大文字小文字を無視する**（プール側は小文字化して dedupe されており、
   *   GitHub 検索結果は元の綴りで返ってくる）
   * - 見つからないものはキーごと入れない（`undefined` を値に持つエントリを作らない）
   * - 🔴 読み込みに失敗しても **例外を投げず空 Map を返す**（バッジが出ないだけで検索は
   *   動き続ける。`D-28` の SPOF 方針と同じ）
   */
  lookup(repositoryFullNames: readonly string[]): Promise<ReadonlyMap<string, GemIndex>>
}
