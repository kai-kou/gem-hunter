import type { SeenDigest } from '../../domain/model/digest-diff'

/**
 * `localStorage` へ「前回訪問時に見たダイジェスト」を 1 世代だけ保持する（`US-32`）。
 *
 * 🔴 **失敗は全て `null` / no-op に倒す**（`readSeen` が例外を投げることは無い）。Safari の
 * プライベートブラウズモード・ITP の 7 日ストレージ削除・容量超過（quota）・不正な JSON・
 * 想定と異なる型のいずれでも「ストレージが空だった」と同じ扱いにする（初回として全件表示・
 * エラー画面や空画面を出さない・必須要件）。
 */

const STORAGE_KEY = 'gem-hunter:seen-digest'

function resolveStorage(storage: Storage | undefined): Storage | undefined {
  if (storage !== undefined) return storage
  if (typeof globalThis.localStorage === 'undefined') return undefined
  return globalThis.localStorage
}

/** 前回訪問時の `SeenDigest` を読み出す。読めない・壊れている場合は必ず `null`。 */
export function readSeen(storage?: Storage): SeenDigest | null {
  try {
    const target = resolveStorage(storage)
    if (target === undefined) return null

    const raw = target.getItem(STORAGE_KEY)
    if (raw === null) return null

    const parsed: unknown = JSON.parse(raw)
    if (!isSeenDigestShape(parsed)) return null

    return { date: parsed.date, packageNames: parsed.packageNames }
  } catch {
    // JSON.parse の失敗・getItem の throw（プライベートモード等）を含め、全て「未保存」扱い。
    return null
  }
}

/** 今回のダイジェストを次回訪問向けに保存する。書き込めなくても例外を投げない（no-op）。 */
export function writeSeen(seen: SeenDigest, storage?: Storage): void {
  try {
    const target = resolveStorage(storage)
    if (target === undefined) return

    target.setItem(STORAGE_KEY, JSON.stringify(seen))
  } catch {
    // quota 超過・プライベートモードの setItem 拒否等。保存できなくても致命的ではない
    // （次回訪問が初回相当になるだけ）ので握りつぶす。
  }
}

function isSeenDigestShape(value: unknown): value is SeenDigest {
  if (typeof value !== 'object' || value === null) return false
  const record = value as Record<string, unknown>
  if (typeof record.date !== 'string') return false
  if (!Array.isArray(record.packageNames)) return false
  return record.packageNames.every((name) => typeof name === 'string')
}
