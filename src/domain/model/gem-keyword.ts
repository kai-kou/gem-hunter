/**
 * Gem 候補プールの絞り込み照合規則（`D-37`・`SP-19`）。
 *
 * 🔴 **本ファイルが照合規則の正本**（`GemIndexPort#search` の実装はここの純粋関数だけを使う）。
 * `D-37` は「絞り込みの照合は repo 名・パッケージ名の **単語境界一致** のみ」と定めており、
 * 部分一致（`orm` が `normalize` に当たる類のノイズ）を構造的に消すことが目的である。
 * 複数語クエリは **全語 AND 一致を既定** とし、0 件になったときだけ
 * `selectMostSelectiveToken` が選ぶ「最も選択的な 1 語」へ緩める。
 *
 * 依存なし・例外なしの純粋関数だけを置く（`ARCH-1`: ドメイン層はフレームワークを import しない）。
 */

/**
 * トークンの構成文字（ASCII 英数字）以外を区切りとみなす。
 *
 * `-` `_` `/` `.` `@` `+` 空白などはすべて区切りになる。
 * ⚠️ 非 ASCII（日本語等）も区切り扱いになるため、日本語だけの検索語は空トークン列になる
 * （＝絞り込みなし＝全件）。照合対象は repo 名・パッケージ名という ASCII 識別子であり
 * 非 ASCII を残しても一致し得ない（`D-37` は `topics` を配信データに載せない）。
 */
const SEPARATOR = /[^a-z0-9]+/

/**
 * 検索語の **生値** として受け付ける最大文字数（超過分は切り捨てる）。
 *
 * 🔵 `src/domain/model/search-keyword.ts` の `MAX_KEYWORD_LENGTH`（256）と **同値** だが、
 * 本ファイルは「他モジュールに依存しない照合規則の正本」という設計のため import せずローカルに持つ。
 * 🔴 **値がズレたときは `MAX_KEYWORD_LENGTH` が正本**（利用者入力の上限の正本はあちら）。本定数は
 * それを超える経路（`/gems` は `searchKeyword` を通さず生値を受ける）を塞ぐための独立した防御なので、
 * あちらより **大きくしない**。
 */
export const MAX_QUERY_LENGTH = 256

/**
 * 検索語から取り出す最大トークン数（超過分は切り捨てる）。
 *
 * 🔴 **なぜ上限があるか（`F-01`）**: 全語 AND が 0 件のときの緩和候補カウントは、トークン数に比例した
 * 仕事量になりうる。上限が無いと `?q=zq0+zq1+…` と語を並べるだけで 1 リクエストが CPU を使い切れる
 * （プレビュー実機で **800 語（URL 4.8KB）→ `error code: 1102`（HTTP 503）** を再現済み）。
 * 16 語あれば実用上の複合語検索（実測の中央値は 1〜2 語）は十分に表現でき、これを超える入力は
 * 検索意図ではなく総当たりとみなして切り捨てる。
 */
export const MAX_QUERY_TOKENS = 16

/**
 * 識別子（repo 名・パッケージ名）を単語境界で分割し、小文字のトークン列にする。
 *
 * 例:
 * - `@stdlib/bench` → `['stdlib', 'bench']`
 * - `github.com/jackc/pgpassfile` → `['github', 'com', 'jackc', 'pgpassfile']`
 * - `RevolutionAnalytics/iterators` → `['revolutionanalytics', 'iterators']`
 *
 * 🔴 **キャメルケースでは分割しない**（`TensorRT` → `['tensorrt']`）。`D-37` が定めるのは
 * 「単語境界一致」であって形態素解析ではないため、区切り文字を持たない綴りは 1 語として扱う。
 * したがって **`tensor` で `TensorRT` は引けない**（バグではなく仕様）。
 *
 * 例外は投げない。空文字・記号だけの入力は空配列になる。
 */
export function tokenizeIdentifier(value: string): readonly string[] {
  return value
    .toLowerCase()
    .split(SEPARATOR)
    .filter((token) => token.length > 0)
}

/**
 * 利用者が入力した検索語を、照合に使うトークン列へ正規化する。
 *
 * 識別子と **同じ正規化**（小文字化・単語境界での分割）を通したうえで、重複トークンを畳む
 * （順序は入力順を保つ）。同じ語を 2 回書いても AND 条件は増えない。
 *
 * 空文字・空白だけ・記号だけの入力は空配列になる。空配列は「絞り込みなし＝全件」を意味する
 * （`matchesAllTokens` が常に `true` を返す）。例外は投げない。
 *
 * 🔴 **上限（`F-01`・CPU 枯渇の防止）**: 生値は先頭 `MAX_QUERY_LENGTH` 文字まで、トークンは
 * 重複を畳んだ後の先頭 `MAX_QUERY_TOKENS` 語までを見る。**超過分は切り捨てる**（例外を投げず、
 * 0 件にも倒さない — 利用者から見れば「長すぎる分が無視された」だけで検索は成立する）。
 * 上限に達したことは返り値では通知しない（呼び出し側に分岐を増やさないため）。
 * 🔵 上限を課すのは **検索語側だけ**。照合対象側（`tokenizeIdentifier`）には課さない
 * （そちらは配信データ由来で、語数はレコードの実態に従う必要がある）。
 */
export function tokenizeQuery(query: string): readonly string[] {
  // 🔴 語数上限より先に生値長で切る。区切り文字だけを大量に並べた入力（`a b c d …`）は
  //    1 語あたり 2 文字なので、文字数で切らないと語数上限に達する前の走査量が青天井になる。
  const bounded = query.length > MAX_QUERY_LENGTH ? query.slice(0, MAX_QUERY_LENGTH) : query
  const seen = new Set<string>()
  const tokens: string[] = []
  for (const token of tokenizeIdentifier(bounded)) {
    if (seen.has(token)) continue
    seen.add(token)
    tokens.push(token)
    if (tokens.length >= MAX_QUERY_TOKENS) break
  }
  return tokens
}

/**
 * `tokens` が **すべて** `haystack`（トークン列）に含まれるか（AND 一致）。
 *
 * 比較はトークン単位の完全一致であり、部分文字列は一致しない（`orm` は `normalize` に
 * 当たらない・`D-37`）。`tokens` が空なら常に `true`（絞り込みなし）。
 */
export function matchesAllTokens(haystack: readonly string[], tokens: readonly string[]): boolean {
  return tokens.every((token) => haystack.includes(token))
}

/**
 * 全語 AND が 0 件だったときに使う「最も選択的な 1 語」を選ぶ（`D-37` の緩和規則）。
 *
 * `counts` は各トークンの **単独ヒット件数**。1 件以上ヒットするもののうち **件数が最小** の
 * トークンを返す（`image processing` なら概念語の `image` ではなく件数の少ない側が残る）。
 * 同数のタイブレークはトークン昇順で決定論にする。どのトークンも 0 件、または `counts` が
 * 空なら `null`（緩めても 0 件のままなので、呼び出し側は 0 件として扱う）。
 */
export function selectMostSelectiveToken(counts: ReadonlyMap<string, number>): string | null {
  let selected: string | null = null
  let selectedCount = Number.POSITIVE_INFINITY
  for (const [token, count] of counts) {
    if (count <= 0) continue
    if (
      count < selectedCount ||
      (count === selectedCount && selected !== null && token < selected)
    ) {
      selected = token
      selectedCount = count
    }
  }
  return selected
}
