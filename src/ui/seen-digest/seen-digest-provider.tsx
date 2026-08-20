'use client'

import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

import { computeDigestDiff } from '../../domain/model/digest-diff'
import { readSeen, writeSeen } from './seen-digest-store'

type SeenDigestState =
  | { status: 'pending' }
  | { status: 'ready'; newNames: ReadonlySet<string>; isFirstVisit: boolean }

const SeenDigestContext = createContext<SeenDigestState>({ status: 'pending' })

/**
 * 再訪時の差分表示（`US-32`）を配る Context Provider。
 *
 * 🔴 **初期状態（サーバー描画・初回クライアント描画）は必ず `'pending'`**。`localStorage` は
 * クライアント専有の情報でサーバーは持たないため、サーバーが返した HTML と初回クライアント
 * レンダーの DOM を一致させる（ハイドレーション不一致を避ける）には、marshalling 前は
 * 「何も出さない」状態で揃える必要がある。`useEffect`（マウント後）で読み出し、`newNames` /
 * `isFirstVisit` が確定してから子（`NewSinceLastVisitBadge` / `FirstVisitNote`）が描画される。
 */
export function SeenDigestProvider({
  currentPackageNames,
  date,
  children,
}: {
  currentPackageNames: readonly string[]
  date: string
  children: ReactNode
}) {
  const [state, setState] = useState<SeenDigestState>({ status: 'pending' })

  useEffect(() => {
    const seen = readSeen()
    const diff = computeDigestDiff(currentPackageNames, seen)
    setState({ status: 'ready', newNames: diff.newNames, isFirstVisit: diff.isFirstVisit })
    writeSeen({ date, packageNames: currentPackageNames })
    // マウント時（今回のダイジェストが確定した時点）に 1 回だけ実行する。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return <SeenDigestContext.Provider value={state}>{children}</SeenDigestContext.Provider>
}

/** `SeenDigestProvider` 配下で差分状態を読む。Provider の外では常に `'pending'`。 */
export function useSeenDigest(): SeenDigestState {
  return useContext(SeenDigestContext)
}
