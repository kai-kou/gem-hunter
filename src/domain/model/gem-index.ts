import { DomainValidationError } from '../errors'
import type { Gem, GemFacet } from './gem'

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
 *
 * 🔴 **並び順の向き（正本）**: **値が小さいほど上位（昇順ソート）**。`open-questions.md` の
 * `D-28` 訂正注記が同じ向きを記録している。`ADR 0009` §3.1 の「star を水増しすると値が
 * *下がる*」という文言は、パーセンタイルを「大きいほど上位」と読む前提で書かれたもので、
 * Ecosyste.ms の順位（0 が最上位）を入力にする本実装では「値が *上がる*」が正しい
 * （結論であるランキングからの脱落は同じ）。
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

/**
 * 候補プール（`Gem`）の `repositoryFullName` を突合キーへ正規化する（`SP-16`）。
 * GitHub のリポジトリ完全名（`owner/repo`）は大文字小文字を区別しないため、検索結果側
 * （`RepositorySummary.fullName`）との突合キーは小文字化して吸収する。
 */
export function gemFacetKey(repositoryFullName: string): string {
  return repositoryFullName.toLowerCase()
}

/**
 * 候補プールから突合用のマップ（`gemFacetKey` → `GemFacet`）を作る（`SP-16`）。
 * 同一リポジトリが複数パッケージ（`packageName` 違い）で重複する場合は、**Gem Index が
 * 小さい方（より過小評価な方）を残す** — 検索結果の並べ替えは「このリポジトリはどれだけ
 * 過小評価されているか」の最良値を見せるべきであり、後勝ち・先勝ちのような取得順依存の
 * 挙動は避ける。
 */
export function toGemFacetMap(candidates: readonly Gem[]): ReadonlyMap<string, GemFacet> {
  const map = new Map<string, GemFacet>()
  for (const candidate of candidates) {
    const key = gemFacetKey(candidate.repositoryFullName)
    const facet: GemFacet = {
      gemIndex: candidate.gemIndex,
      dependentCount: candidate.dependentCount,
    }
    const existing = map.get(key)
    if (existing === undefined || gemIndexValue(candidate.gemIndex) < gemIndexValue(existing.gemIndex)) {
      map.set(key, facet)
    }
  }
  return map
}

/**
 * Gem Index 昇順（値が小さいほど上位・§本ファイル冒頭コメントの正本どおり）に並べ替える
 * （`SP-16`）。`facets` に無い項目（候補プールに Gem Index を持たない結果）は絞り込まず、
 * **元の相対順を保ったまま末尾へ回す**（飼い主決定・仕様①）。
 *
 * 実装: `facets` を持つ項目と持たない項目に分けたうえで、持つ項目だけを `Array.prototype.sort`
 * （ES2019+ で安定ソートが仕様として保証されている）で並べ替える。同順位・非保有分の元の
 * 相対順が保たれるのはこの安定性による。入力配列・`facets` は変更しない。
 */
export function sortByGemIndex<T extends { readonly fullName: string }>(
  items: readonly T[],
  facets: ReadonlyMap<string, GemFacet>,
): readonly T[] {
  const ranked: { readonly item: T; readonly facet: GemFacet }[] = []
  const unranked: T[] = []

  for (const item of items) {
    const facet = facets.get(gemFacetKey(item.fullName))
    if (facet === undefined) {
      unranked.push(item)
    } else {
      ranked.push({ item, facet })
    }
  }

  ranked.sort((a, b) => gemIndexValue(a.facet.gemIndex) - gemIndexValue(b.facet.gemIndex))

  return [...ranked.map((entry) => entry.item), ...unranked]
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
