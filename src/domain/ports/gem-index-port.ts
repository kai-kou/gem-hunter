import type { DigestMeta, GemPoolEntry } from '../model/gem'
import type { GemIndex } from '../model/gem-index'
import type { PerPage } from '../model/per-page'

/**
 * Gem 候補プールの絞り込み条件（`SP-19` / `D-37`）。
 */
export type GemPoolSearchInput = {
  /** 正規化済みの検索トークン（`tokenizeQuery` の出力）。空配列なら絞り込みなし＝全件。 */
  readonly tokens: readonly string[]
  /**
   * 1 始まりのページ番号。範囲外は実装側が **最終ページへクランプ** し、実際に返したページを
   * `effectivePage` で報告する（1 ページ目へは倒さない・`F-02`）。
   *
   * 🔴 **`PageNumber`（`domain/model/page-number.ts`）を使わない**。あのブランド型の上限
   * （`MAX_PAGE` = 50）は **GitHub 検索 API が 1,000 件までしか返せない** ことに由来する制約で、
   * 候補プールは GitHub API を介さない静的データなのでその上限は当てはまらない
   * （実データで `com` 8,913 件・`github` 8,156 件と 1,000 件超のトークンが実在する）。
   * ⚠️ ここを `PageNumber` に「揃える」と 50 ページ目より後ろが到達不能になる。規約違反ではなく
   * **意図的な非採用** である（`ARCH-R2` の例外としてこの JSDoc が根拠）。
   */
  readonly page: number
  /**
   * 表示件数。🔴 ブランド型で受ける（`AR-3`: 20 / 50 / 100 のみ）。生の `number` にすると
   * `perPage: 100000` が型検査を素通りし、1 リクエストで 10 万件のスライスと写経が走る（`F-13`）。
   */
  readonly perPage: PerPage
}

/**
 * Gem 候補プールの絞り込み結果（`SP-19` / `D-37`）。
 */
export type GemPoolSearchResult = {
  /** `gemIndex` 昇順（値が小さいほど過小評価度が高い）。同値は `repositoryFullName` 昇順。 */
  readonly items: readonly GemPoolEntry[]
  /** 絞り込み後の総件数（ページングの母数）。 */
  readonly totalCount: number
  /**
   * 実際に返したページ（1 始まり）。入力 `page` が範囲外なら **クランプ後の値**（`F-02`）。
   *
   * `lastPage = Math.max(1, Math.ceil(totalCount / perPage))` として
   * `effectivePage = Math.min(Math.max(1, Math.trunc(page) || 1), lastPage)`。
   * `totalCount === 0` のときは `1`。UI はページャの現在地にこの値を使う（入力値ではなく）。
   */
  readonly effectivePage: number
  /** 実際に AND 一致へ使ったトークン（緩和が起きたときは 1 語だけ）。 */
  readonly usedTokens: readonly string[]
  /** 🔴 全語 AND が 0 件で「最も選択的な 1 語」へ緩めたか（`D-37`）。UI が明示するために返す。 */
  readonly relaxed: boolean
  /** 出典メタデータ（`D-29` / `GR-6`）。一覧にも帰属表示を出すため返す。 */
  readonly meta: DigestMeta
}

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

  /**
   * 検索語で Gem 候補プールを絞り込み、`gemIndex` 昇順の 1 ページ分を返す（`SP-19`）。
   *
   * - 🔴 **照合規則の正本は `src/domain/model/gem-keyword.ts`**（repo 名・パッケージ名の
   *   単語境界一致・全語 AND・0 件時のみ「最も選択的な 1 語」へ緩和・`D-37`）。実装側で
   *   独自の照合（部分一致・あいまい一致）を足さない
   * - 緩和が起きたかは `relaxed`、実際に使ったトークンは `usedTokens` で返す（UI が
   *   「全語では 0 件だったので 1 語で絞り込んだ」ことを明示できるようにするため）
   * - `tokens` が空配列なら絞り込みなし＝プール全件が母数になる
   * - 🔵 **範囲外のページは最終ページへクランプする**（1 ページ目へ倒さない）。実際に返した
   *   ページは `effectivePage` で報告する（`F-02`。`?page=999` を直打ちしても「最後のページ」が
   *   見え、ページャの現在地もそこに合う）
   * - 🔵 一覧の母集団は **一覧用の列（`packageName` / `dependentCount` / `stars`）が揃った
   *   レコードだけ**。列が欠けたシャードのレコードは `lookup()`（バッジ）では引けるが、
   *   ここには出さない（欠損を既定値で埋めた数値を事実として表示しない・`ARCH-R1` / `F-17`）
   * - 🔴 **`gemIndex` の閾値では絞らない**。一覧に載るのは **プールに載っているもの全部** で、
   *   `gemIndex` は **順序** にだけ使う（値は母集団相対なので、閾値の意味が母集団ごとに変わる）
   * - 🔴 読み込みに失敗しても **例外を投げず空の結果を返す**（`items: []` / `totalCount: 0` /
   *   `effectivePage: 1` / `usedTokens: []` / `relaxed: false` / `meta` は既定値）。一覧が空になるだけで
   *   アプリは動き続ける（`lookup()` と同じ `D-28` の SPOF 方針）
   */
  search(input: GemPoolSearchInput): Promise<GemPoolSearchResult>
}
