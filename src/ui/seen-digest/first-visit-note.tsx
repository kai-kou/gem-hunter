'use client'

import { useSeenDigest } from './seen-digest-provider'

/**
 * 「初回として全件を表示している」旨の注記（`US-32`）。
 *
 * localStorage が空・消去・破損している場合（Safari ITP の 7 日ストレージ削除を含む）も
 * `isFirstVisit: true` に自然劣化するため、エラーや空画面を出さずに済む（必須要件）。
 *
 * `role="status"` で支援技術にも伝える（`RepositoryList` / `DailyDigest` の 0 件と同じ作法）。
 */
export function FirstVisitNote({ label }: { label: string }) {
  const state = useSeenDigest()

  if (state.status !== 'ready' || !state.isFirstVisit) {
    return null
  }

  return (
    <p role="status" className="text-muted-foreground mt-1 text-xs">
      {label}
    </p>
  )
}
