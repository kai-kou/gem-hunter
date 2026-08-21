import type { DateSeed } from '../domain/model/date-seed'
import type { DailyDigest, Gem } from '../domain/model/gem'
import { gemIndexValue } from '../domain/model/gem-index'
import type { GemDigestPort } from '../domain/ports/gem-digest-port'

export type GetDailyDigestInput = {
  readonly seed: DateSeed
  readonly limit: number
}

export type GetDailyDigest = (input: GetDailyDigestInput) => Promise<DailyDigest>

/**
 * 日次シャッフルの母集団サイズ（Gem Index 上位帯・shortlist）。
 *
 * 実データ 294 件での分布検証（Issue #331）: shortlist を N=60 にすると star 中央値 706・
 * 70% が star<1000 に収まる。`limit=5` に対して 12 倍の母数があり日次ローテーション（`US-31`）を
 * 保てる。N=20〜30 は低 star に寄る代わりに顔ぶれの循環が短くなり、N=100 以上は star 中央値が
 * 1,169 まで上がって改善効果が薄れるため、両端の中間である 60 を採る。
 */
export const GEM_INDEX_SHORTLIST_SIZE = 60

/**
 * 日次ダイジェストを決定論的に生成する（`ADR 0014` §2.2）。
 *
 * ### 並び方の設計判断（コメントで明記）
 *
 * ADR 0014 §2.2 は「同じ日は全ユーザーで同じ並び・翌日で入れ替わる」を要求し、`AR-9` / `US-31`
 * は「毎日の顔ぶれが変わる」を要求する。一方 `ADR 0009` §2.1 の Gem Index はランキング指標であり、
 * 表示順に「意味」がある（値が小さいほど過小評価度が高い）。さらに Issue #331 で判明したとおり、
 * 候補プール全体（被依存数トップ層＝有名パッケージ集合）を母集団に一様抽出すると、Gem Index が
 * 「選定」に一切関与せず star の多い有名リポジトリばかり並んでしまう。
 *
 * この 3 つを両立させるため **3 段階** で並べる。
 *   1. 候補プールを **Gem Index asc**（値が小さいほど過小評価度が高い・同値は packageName asc で
 *      タイブレーク）で並べ、先頭 `GEM_INDEX_SHORTLIST_SIZE` 件を shortlist とする
 *      （＝日次シャッフルの母集団を Gem Index 上位帯だけに絞る）
 *   2. shortlist を **seed で決定論的シャッフル**（SHA-256(seed:packageName) をソートキー）し、
 *      先頭 `limit` 件を選ぶ
 *   3. 選ばれた `limit` 件を再び **Gem Index asc** で並べて返す（表示順の意味づけ）
 *
 * これにより「選ばれるのは常に Gem Index 上位帯」（1. の効果・本来の目的）と「その中で顔ぶれは
 * 日ごとに変わる」（2. の効果・`US-31`）と「その日の中の並び順は説明可能」（3. の効果・Gem Index
 * の意味を潰さない）を両立する。`Math.random()` は使わない（テスト決定性・L-113）。
 */
export function makeGetDailyDigest(deps: { port: GemDigestPort }): GetDailyDigest {
  return async ({ seed, limit }) => {
    const { candidates, meta } = await deps.port.listCandidates()

    if (candidates.length === 0 || limit <= 0) {
      return { date: seed, items: [], meta }
    }

    // 1. Gem Index asc（同値は packageName asc でタイブレーク・入力順に依存させない）で並べ、
    //    先頭 GEM_INDEX_SHORTLIST_SIZE 件を shortlist（日次シャッフルの母集団）とする。
    const shortlist = [...candidates]
      .sort((a, b) => {
        const diff = gemIndexValue(a.gemIndex) - gemIndexValue(b.gemIndex)
        if (diff !== 0) return diff
        return a.packageName < b.packageName ? -1 : a.packageName > b.packageName ? 1 : 0
      })
      .slice(0, GEM_INDEX_SHORTLIST_SIZE)

    // 2. shortlist に seed 由来のソートキーを付与し決定論的シャッフルする
    const withKeys = await Promise.all(
      shortlist.map(async (gem) => ({
        gem,
        key: await deterministicKey(`${seed}:${gem.packageName}`),
      })),
    )
    withKeys.sort((a, b) => (a.key < b.key ? -1 : a.key > b.key ? 1 : 0))

    // 3. 先頭 limit 件を Gem Index asc（値が小さいほど過小評価度が高い）で並べる
    //
    // 🔴 ただし候補プールが limit 以下のときは Gem Index の再ソートを **しない**。全件が必ず
    //    選ばれるため、決定論的シャッフル（2.）の結果を Gem Index asc で上書きすると順序が
    //    日付に依存しなくなり、`US-31`（毎日顔ぶれが変わる）が静かに壊れる（候補プールが
    //    バッチ障害等で縮退したときに顕在化する）。この場合はシャッフル順をそのまま出す。
    const picked = withKeys.slice(0, limit).map((x) => x.gem)
    const items: readonly Gem[] =
      candidates.length <= limit
        ? picked
        : [...picked].sort((a, b) => gemIndexValue(a.gemIndex) - gemIndexValue(b.gemIndex))

    return { date: seed, items, meta }
  }
}

/**
 * SHA-256 ハッシュの 16 進表現。Node 20+ と Cloudflare Workers の両方で `globalThis.crypto.subtle`
 * が使える（`Math.random` は決定論性を壊すため使わない）。
 */
async function deterministicKey(source: string): Promise<string> {
  const bytes = new TextEncoder().encode(source)
  const digest = await crypto.subtle.digest('SHA-256', bytes)
  const view = new Uint8Array(digest)
  let hex = ''
  for (const byte of view) {
    hex += byte.toString(16).padStart(2, '0')
  }
  return hex
}
