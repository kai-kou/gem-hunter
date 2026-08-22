import type { Gem } from './gem'
import { gemIndexValue } from './gem-index'

/**
 * 日次シャッフルの母集団サイズ（Gem Index 上位帯・shortlist）。
 *
 * 実データ 294 件での分布検証（Issue #331・`public/data/daily-digest.json` 時点のスナップショット
 * 値）: shortlist を N=60 にすると star 中央値 約 706（下側 705 / 上側 706 の平均 705.5）・70% が
 * star<1000 に収まる。`limit=5` に対して 12 倍の母数があり日次ローテーション（`US-31`）を保てる。
 * N=20〜30 は低 star に寄る代わりに顔ぶれの循環が短くなり、N=100 以上は star 中央値が 1,162（下側
 * 1,155 / 上側 1,169 の平均）まで上がって改善効果が薄れるため、両端の中間である 60 を採る。
 *
 * 🔴 **この較正根拠は `SP-14` 時点の候補プール（npm 限定・294 件）に対するものであり、
 * `SP-17`（#387・`D-36` / `D-37`）が入れ替えた 12 レジストリの新プールでは無効になっている**
 * （新 `daily-digest.json` の上位 60 件は実測で star 中央値 5.0・最大 17。上記の「star 中央値
 * 約 706 / 70% が star<1000」という分布はもう成り立たない）。
 * `N` を変更する前に、**新プールで分布を測り直してから**決めること（値 60 自体は測り直しまで
 * 据え置く。根拠が無効なだけで、60 が悪いと判明したわけではない）。
 */
export const GEM_INDEX_SHORTLIST_SIZE = 60

/**
 * Gem Index 昇順の比較関数（値が小さいほど過小評価度が高い＝上位）。タイブレークなし。
 *
 * 同値の扱いが結果に影響する場面（shortlist の選定境界）では `selectGemIndexShortlist` が
 * 別途 packageName asc でタイブレークする。既に確定した部分集合（例: 選ばれた `limit` 件）の
 * 表示順を決めるだけの用途では、同値の入力順依存はそもそも表面化しない。
 */
export function byGemIndexAsc(a: Gem, b: Gem): number {
  return gemIndexValue(a.gemIndex) - gemIndexValue(b.gemIndex)
}

/**
 * 候補群から Gem Index 上位 `size` 件を選ぶ（＝日次シャッフルの母集団を Gem Index 上位帯だけに
 * 絞る）。同値は packageName asc でタイブレークし、入力順に依存させない。
 *
 * `size` が候補数以上のときは全件を返し、`size` が 0 以下のときは空配列を返す。
 */
export function selectGemIndexShortlist(candidates: readonly Gem[], size: number): readonly Gem[] {
  if (size <= 0) return []
  return [...candidates]
    .sort((a, b) => {
      const diff = byGemIndexAsc(a, b)
      if (diff !== 0) return diff
      return a.packageName < b.packageName ? -1 : a.packageName > b.packageName ? 1 : 0
    })
    .slice(0, size)
}
