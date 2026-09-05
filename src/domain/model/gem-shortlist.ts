import type { Gem } from './gem'
import { gemIndexValue } from './gem-index'

/**
 * 日次シャッフルの母集団サイズ（Gem Index 上位帯・shortlist）。
 *
 * 🔵 **較正根拠を差し替えた（2026-09-06 JST・Issue #335）**: 旧根拠は `SP-14` 時点の候補プール
 * （npm 限定 294 件）の star 分布からの逆算（N=60 で star 中央値 約 706・70% が star<1000）だったが、
 * `SP-17`（`D-36` / `D-37`）が候補プールを 12 レジストリへ入れ替えたことで **star を根拠にできなく
 * なった**。現行プール（`public/data/daily-digest.json` の `candidates` 300 件）は生成時点で既に
 * Gem Index 上位帯へ絞り込まれており、**全件が star<100（最大 38）** に密集している。N を 5 から
 * 300 まで動かしても star 中央値は 5.0 → 7.0 とほぼ平坦で、旧プールで見られた「N を上げると star
 * 中央値が跳ね上がる（N=100 で 1,162）」という効果は存在しない。
 *
 * 🔵 **現行の根拠はレジストリ多様性とローテーション母数の 2 点**（`tools/analyze_shortlist_distribution.mjs`
 * による 2026-09-06 実測・プール 300 件）:
 *
 * | N | stars 中央値 | stars 最大 | レジストリ種数（全 12 中） | `limit=5` に対する母数倍率 |
 * |---|---|---|---|---|
 * | 5 | 5.0 | 6 | 4 | 1 倍 |
 * | 20 | 5.0 | 14 | 9 | 4 倍 |
 * | **60** | **5.5** | **17** | **11** | **12 倍** |
 * | 100 | 6.0 | 23 | 12 | 20 倍 |
 * | 300（全体） | 7.0 | 38 | 12 | 60 倍 |
 *
 * N=60 は「12 レジストリ中 11 種を含みつつ母数を絞る」バランス点であり、`limit=5` に対して 12 倍の
 * 母数を保って `US-31`（毎日顔ぶれが変わる）を維持できる。全 12 レジストリを含めるには N=100 が
 * 要るが、母数が 20 倍になり再登場周期が伸びる（顔ぶれの入れ替わりが遅くなる）ため、本改訂では
 * **60 を据え置き**、N=100 は次回較正時の選択肢として記録するに留めた。
 *
 * 🔴 **候補プールの取得軸を変えたら測り直すこと**（`ADR 0014` §2.2.2 の再評価トリガー）。手順は
 * `node tools/analyze_shortlist_distribution.mjs` を実行するだけでよい（この定数を使う実装関数を
 * そのまま import して計測するため、実装と計測がずれない）。取得軸そのものの見直しは #990。
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
