'use client'

import { useSeenDigest } from './seen-digest-provider'

/**
 * 「初回として全件を表示している」旨の注記（`US-32`）。
 *
 * localStorage が空・消去・破損している場合（Safari ITP の 7 日ストレージ削除を含む）も
 * `isFirstVisit: true` に自然劣化するため、エラーや空画面を出さずに済む（必須要件）。
 *
 * 🔴 **ライブリージョン（`role="status"`）は初期 DOM に空で常設し、中身だけを書き換える**
 * （`ui-ux-guidelines.md` §7.2・`app/[locale]/page.tsx` の検索ステータスと同じ作法）。
 * 要素ごと後から挿入すると、多くの支援技術は「読み込み時に存在しなかったライブリージョンへの
 * 挿入」を監視できず、初回訪問の注記が読み上げられない（`NFR-12` / `AC-8`）。
 * サーバー描画・ハイドレーション直後は `pending` で中身が空になるため、DOM 構造は一致する。
 */
export function FirstVisitNote({ label }: { label: string }) {
  const state = useSeenDigest()
  const shouldShow = state.status === 'ready' && state.isFirstVisit

  return (
    <p role="status" className="text-muted-foreground mt-1 text-xs">
      {shouldShow ? label : null}
    </p>
  )
}
