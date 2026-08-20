import { DomainValidationError } from '../errors'

/**
 * 過小評価度スコア `Gem Index`（`ADR 0009` §2.1）。
 * 「被依存数のパーセンタイル順位 − star のパーセンタイル順位」。並び順（ランキング）にのみ
 * 使い、健全性（`criticality_score` / Scorecard）とは 1 つのスコアに合算しない（`ADR 0009` §2.2）。
 *
 * ブランド型 + スマートコンストラクタ（`domain-model.md` §4）。値そのものは算出済みの数値を
 * 運ぶだけで、算出（rankings → 差）は `computeGemIndex` が行う。
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
 * Ecosyste.ms の `rankings`（パーセンタイル順位・0〜100・**0 が最上位**）から Gem Index を算出する。
 *
 * - `dependentRank`: 被依存数の順位（値が小さいほど実利用が多い＝上位）
 * - `starRank`:      star の順位（値が小さいほど注目度が高い＝上位）
 *
 * 定義: `Gem Index = dependentRank − starRank`（`ADR 0009` §2.1）。
 * 被依存数が上位（小さい）かつ star が下位（大きい）ほど差が **強い負値** になり、
 * 「過小評価度が高い」ことを意味する。ソート時は **値が小さいほど上位（asc）** で並べる。
 *
 * 値域外（負数・100 超・非有限数）は `DomainValidationError`。母集団外の順位は算出前に弾く。
 */
export function computeGemIndex(dependentRank: number, starRank: number): GemIndex {
  assertRank('dependentRank', dependentRank)
  assertRank('starRank', starRank)
  return gemIndex(dependentRank - starRank)
}

function assertRank(name: string, value: number): void {
  if (!Number.isFinite(value) || value < 0 || value > 100) {
    throw new DomainValidationError(
      'GemIndex',
      value,
      `${name} は 0〜100 の有限数で指定してください（rankings は 0 が最上位）`,
    )
  }
}
