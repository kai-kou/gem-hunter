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
 * 日次ダイジェストを決定論的に生成する（`ADR 0014` §2.2）。
 *
 * ### 並び方の設計判断（コメントで明記）
 *
 * ADR 0014 §2.2 は「同じ日は全ユーザーで同じ並び・翌日で入れ替わる」を要求し、`AR-9` / `US-31`
 * は「毎日の顔ぶれが変わる」を要求する。一方 `ADR 0009` §2.1 の Gem Index はランキング指標であり、
 * 表示順に「意味」がある（値が小さいほど過小評価度が高い）。
 *
 * この 2 つを両立させるため **2 段階** で並べる。
 *   1. 候補プール全体を **seed で決定論的シャッフル**（SHA-256(seed:packageName) をソートキー）
 *   2. 先頭 `limit` 件を選び、**選ばれたサブセットの内部を Gem Index asc**（値が小さいほど上位）で並べる
 *
 * これにより「顔ぶれは日ごとに変わる」（1. の効果）と「その日の中の並び順は説明可能」（2. の
 * 効果・Gem Index の意味を潰さない）を両立する。`Math.random()` は使わない（テスト決定性・L-113）。
 */
export function makeGetDailyDigest(deps: { port: GemDigestPort }): GetDailyDigest {
  return async ({ seed, limit }) => {
    const { candidates, meta } = await deps.port.listCandidates()

    if (candidates.length === 0 || limit <= 0) {
      return { date: seed, items: [], meta }
    }

    // 1. seed 由来のソートキーを各候補に付与（決定論的シャッフル）
    const withKeys = await Promise.all(
      candidates.map(async (gem) => ({
        gem,
        key: await deterministicKey(`${seed}:${gem.packageName}`),
      })),
    )
    withKeys.sort((a, b) => (a.key < b.key ? -1 : a.key > b.key ? 1 : 0))

    // 2. 先頭 limit 件を Gem Index asc（値が小さいほど過小評価度が高い）で並べる
    const picked = withKeys.slice(0, limit).map((x) => x.gem)
    const items: readonly Gem[] = [...picked].sort(
      (a, b) => gemIndexValue(a.gemIndex) - gemIndexValue(b.gemIndex),
    )

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
