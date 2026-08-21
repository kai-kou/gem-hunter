import type { DateSeed } from '../domain/model/date-seed'
import type { DailyDigest, Gem } from '../domain/model/gem'
import {
  GEM_INDEX_SHORTLIST_SIZE,
  byGemIndexAsc,
  selectGemIndexShortlist,
} from '../domain/model/gem-shortlist'
import type { GemDigestPort } from '../domain/ports/gem-digest-port'

export type GetDailyDigestInput = {
  readonly seed: DateSeed
  readonly limit: number
}

export type GetDailyDigest = (input: GetDailyDigestInput) => Promise<DailyDigest>

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
 *   1. 候補プールから **Gem Index asc**（値が小さいほど過小評価度が高い・同値は packageName asc
 *      でタイブレーク）で shortlist（`selectGemIndexShortlist`）を選ぶ
 *      （＝日次シャッフルの母集団を Gem Index 上位帯だけに絞る）。母集団サイズは
 *      `GEM_INDEX_SHORTLIST_SIZE` を基本としつつ、`limit` がそれを超えるときは `limit` に合わせて
 *      広げる（さもないと「候補プールが limit 以下なら全件返す」契約が壊れ、件数が無警告で
 *      欠落する）
 *   2. shortlist を **seed で決定論的シャッフル**（SHA-256(seed:packageName) をソートキー）し、
 *      先頭 `limit` 件を選ぶ
 *   3. 選ばれた `limit` 件を再び **Gem Index asc**（`byGemIndexAsc`）で並べて返す（表示順の意味
 *      づけ）
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

    // 1. shortlist（日次シャッフルの母集団）を選ぶ。母集団サイズは GEM_INDEX_SHORTLIST_SIZE と
    //    limit の大きい方にする（limit が母集団サイズを超えると、後段でシャッフル母集団自体が
    //    limit 未満になり「候補プールが limit 以下なら全件返す」契約が壊れるため）。
    const shortlist = selectGemIndexShortlist(candidates, Math.max(GEM_INDEX_SHORTLIST_SIZE, limit))

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
    // 🔴 ただし shortlist（実際のシャッフル母集団）が limit 以下のときは Gem Index の再ソートを
    //    **しない**。shortlist 全件が必ず選ばれるため、決定論的シャッフル（2.）の結果を
    //    Gem Index asc で上書きすると順序が日付に依存しなくなり、`US-31`（毎日顔ぶれが変わる）が
    //    静かに壊れる（候補プールがバッチ障害等で縮退した、または limit が母集団サイズ以上に
    //    広がったときに顕在化する）。この場合はシャッフル順をそのまま出す。
    const picked = withKeys.slice(0, limit).map((x) => x.gem)
    const items: readonly Gem[] =
      shortlist.length <= limit ? picked : [...picked].sort(byGemIndexAsc)

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
