import { DomainValidationError } from '../errors'

/**
 * 過小評価度スコア `Gem Index`（`ADR 0009` §2.1）。
 * 「被依存数のパーセンタイル順位 − star のパーセンタイル順位」。並び順（ランキング）にのみ
 * 使い、健全性（`criticality_score` / Scorecard）とは 1 つのスコアに合算しない（`ADR 0009` §2.2）。
 *
 * ブランド型 + スマートコンストラクタ（`domain-model.md` §4）。値そのものは算出済みの数値を
 * 運ぶだけで、算出（rankings → 差）は `computeGemIndex` が行う。
 *
 * ⚠️ 本ファイルの関数本体は契約確定用のスタブ。TDD（Red → Green）で実装役が置き換える。
 */

declare const brand: unique symbol

export type GemIndex = number & { readonly [brand]: 'GemIndex' }

/**
 * 算出済みの Gem Index 値を検証して包む。有限数でなければ `DomainValidationError`。
 */
export function gemIndex(value: number): GemIndex {
  if (!Number.isFinite(value)) {
    throw new DomainValidationError('GemIndex', value, 'Gem Index は有限数で指定してください')
  }
  return value as GemIndex
}

/** ブランドを外して素の数値に戻す（表示・ソート比較用）。 */
export function gemIndexValue(value: GemIndex): number {
  return value as number
}

/**
 * Ecosyste.ms の `rankings`（パーセンタイル順位・0〜100・0 が最上位）から Gem Index を算出する。
 * 被依存数の順位が上位（値が小さい）ほど、star の順位が下位（値が大きい）ほど過小評価度が高い。
 *
 * ⚠️ スタブ。順位の向き・値域の正本は `ADR 0009` §2.1。実装役が同 ADR に照らして確定する。
 */
export function computeGemIndex(_dependentRank: number, _starRank: number): GemIndex {
  throw new Error('computeGemIndex: not implemented (SP-14 実装役が TDD で埋める)')
}
