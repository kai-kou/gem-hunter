'use client'

import { useSeenDigest } from './seen-digest-provider'

/**
 * 「前回訪問時には無かった新着」を示すバッジ（`US-32`）。
 *
 * `SeenDigestProvider` が `'ready'` かつ `packageName` が今回の新着集合に含まれるときだけ
 * 描画する。初回訪問（`isFirstVisit: true`）では `newNames` が常に空集合なので、個別の
 * 新着マークは自然に付かない（`computeDigestDiff` の契約）。
 *
 * a11y: 可視テキスト（絵文字ではなく短い語）で色だけに頼らず伝える。
 */
export function NewSinceLastVisitBadge({
  packageName,
  label,
}: {
  packageName: string
  label: string
}) {
  const state = useSeenDigest()

  if (state.status !== 'ready' || !state.newNames.has(packageName)) {
    return null
  }

  return (
    <span className="bg-primary/10 text-primary rounded-full px-2 py-0.5 text-xs font-medium">
      {label}
    </span>
  )
}
