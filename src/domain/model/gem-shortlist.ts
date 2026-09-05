import type { Gem } from './gem'
import {
  GEM_INDEX_SHORTLIST_SIZE as GEM_INDEX_SHORTLIST_SIZE_UNTYPED,
  byGemIndexAsc as byGemIndexAscUntyped,
  selectGemIndexShortlist as selectGemIndexShortlistUntyped,
} from './gem-shortlist.rules.mjs'

/**
 * 日次シャッフルの母集団サイズ（Gem Index 上位帯・shortlist）。
 *
 * 🔴 **選定ロジックの実体は [`gem-shortlist.rules.mjs`](./gem-shortlist.rules.mjs) が単一正本**
 * （`gem-index.ts` / `gem-index.rules.mjs` と同じ分離。Issue #335）。本ファイルはそこへ `Gem` の
 * 型を被せる薄いラッパーで、ロジックを写さない。
 *
 * **`= 60` の較正根拠（結論のみ・詳細は正本を参照）**: 🔴 **旧根拠（`SP-14` 時点の候補プール・
 * npm 限定 294 件の star 分布からの逆算）は `SP-17` の候補プール入れ替え（`D-36` / `D-37`）で
 * 失効している**。現行の根拠はレジストリ多様性（`N=60` で全 12 種中 11 種を含む）と
 * ローテーション母数（`limit=5` に対して 12 倍・`US-31`）の 2 点。表・全文は
 * `ADR 0014` §2.2.3 が正本（本ファイルでは重複記載しない）。再測定コマンド:
 * `node tools/analyze_shortlist_distribution.mjs`（この定数を使う実装関数をそのまま import して
 * 計測するため、実装と計測がずれない）。候補プールの取得軸を変えたら測り直すこと
 * （`ADR 0014` §2.2.2 の再評価トリガー・取得軸そのものの見直しは #990）。
 */
export const GEM_INDEX_SHORTLIST_SIZE: number = GEM_INDEX_SHORTLIST_SIZE_UNTYPED

/**
 * Gem Index 昇順の比較関数（値が小さいほど過小評価度が高い＝上位）。タイブレークなし。
 *
 * 同値の扱いが結果に影響する場面（shortlist の選定境界）では `selectGemIndexShortlist` が
 * 別途 packageName asc でタイブレークする。既に確定した部分集合（例: 選ばれた `limit` 件）の
 * 表示順を決めるだけの用途では、同値の入力順依存はそもそも表面化しない。
 *
 * 実体は `gem-shortlist.rules.mjs` の同名関数（ブランド剥がしはキャストのみで実行時処理を
 * 持たないため、`GemIndex` は構造的な `number` としてそのまま渡せる）。
 */
export function byGemIndexAsc(a: Gem, b: Gem): number {
  return byGemIndexAscUntyped(a, b)
}

/**
 * 候補群から Gem Index 上位 `size` 件を選ぶ（＝日次シャッフルの母集団を Gem Index 上位帯だけに
 * 絞る）。同値は packageName asc でタイブレークし、入力順に依存させない。
 *
 * `size` が候補数以上のときは全件を返し、`size` が 0 以下のときは空配列を返す。
 *
 * 実体は `gem-shortlist.rules.mjs` の同名関数。
 */
export function selectGemIndexShortlist(candidates: readonly Gem[], size: number): readonly Gem[] {
  return selectGemIndexShortlistUntyped(candidates, size) as readonly Gem[]
}
