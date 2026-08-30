/**
 * Gem Index の **算出式と値域規則の単一正本**（Issue #276）。
 *
 * 🔴 **なぜドメイン層に `.mjs` を置くのか**: 同じ規則を使う経路が 2 つあり、片方が TypeScript を
 * 読めないため。
 *
 * - アプリ（`src/domain/model/gem-index.ts` の `computeGemIndex`）: 型と `DomainValidationError` を伴う
 * - 本番の候補プール生成（`tools/gem-pool/pipeline.mjs`）: `node tools/... .mjs` で直接実行されるため
 *   TypeScript を import できない（型ストリップは依存する `src/domain/errors.ts` の
 *   パラメータプロパティが非対応で、全実行経路にフラグ追加が必要になる）
 *
 * かつては両者が式（`dependentRank - starRank`）と値域（0〜100）を **別々に写して** 持っており、
 * 「テストが通るのはアプリ側だけ、本番の値を作るのはバッチ側」という状態だった。本ファイルを
 * 両者の唯一の実装元にすることで、式や値域を変えたときに片方だけ取り残される事故を構造的に消す。
 *
 * 🔵 **本ファイルは例外を投げない**。値域違反を **どの例外型で表現するかは呼び出し側の契約** で、
 * アプリは `DomainValidationError`、バッチは `RangeError` を投げる。ここが持つのは
 * 「何が妥当か（`isValidRank`）」と「どう算出するか（`computeGemIndexValue`）」だけ。
 *
 * 🔵 依存ゼロの純粋関数のみで構成する（`import` を足さない）。ドメイン層の依存規則
 * （`docs/rules/architecture-rules.md`）どおり、ここは何にも依存しない。
 */

/** パーセンタイル順位の下限。Ecosyste.ms の `rankings` は **0 が最上位**。 */
export const RANK_MIN = 0

/** パーセンタイル順位の上限。 */
export const RANK_MAX = 100

/**
 * パーセンタイル順位が不変条件（`RANK_MIN`〜`RANK_MAX` の有限数）を満たすか判定する。
 *
 * @param {number} value 判定対象（外部 API 由来の値が渡りうるため型は信用しない）
 * @returns {boolean}
 */
export function isValidRank(value) {
  return typeof value === 'number' && Number.isFinite(value) && value >= RANK_MIN && value <= RANK_MAX
}

/**
 * Gem Index の値を算出する（`ADR 0009` §2.1）。
 *
 * 定義: `Gem Index = dependentRank − starRank`。
 * 🔴 **向きの正本**: 値が **小さいほど上位**（過小評価度が高い）。被依存数が上位（順位が小さい）で
 * star が下位（順位が大きい）ほど強い負値になる。丸めは行わない（丸め方は呼び出し側の都合）。
 *
 * @param {number} dependentRank 被依存数のパーセンタイル順位（0 が最上位）
 * @param {number} starRank      star のパーセンタイル順位（0 が最上位）
 * @returns {number}
 */
export function computeGemIndexValue(dependentRank, starRank) {
  return dependentRank - starRank
}
