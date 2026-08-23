'use client'

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useSyncExternalStore,
  type ReactNode,
} from 'react'

import { computeDigestDiff } from '../../domain/model/digest-diff'
import { readSeen, writeSeen } from './seen-digest-store'

type SeenDigestState =
  { status: 'pending' } | { status: 'ready'; newNames: ReadonlySet<string>; isFirstVisit: boolean }

const SeenDigestContext = createContext<SeenDigestState>({ status: 'pending' })

/**
 * 再訪時の差分表示（`US-32`）を配る Context Provider。
 *
 * 🔴 **初期状態（サーバー描画・初回クライアント描画）は必ず `'pending'`**。`localStorage` は
 * クライアント専有の情報でサーバーは持たないため、サーバーが返した HTML と初回クライアント
 * レンダーの DOM を一致させる（ハイドレーション不一致を避ける）には、marshalling 前は
 * 「何も出さない」状態で揃える必要がある。マウント後に `useSyncExternalStore` の
 * `getSnapshot`（クライアント側でのみ返す ready 状態）を参照し、`newNames` / `isFirstVisit`
 * が確定してから子（`NewSinceLastVisitBadge` / `FirstVisitNote`）が描画される。
 *
 * 🔵 `useEffect` 内で `setState` を直呼びしない（`react-hooks/set-state-in-effect`）ため、
 * 外部ストアの購読モデル（`useSyncExternalStore`）で「サーバーは pending / クライアントは ready」
 * を表現する。write（seen の書き込み）だけを `useEffect` で 1 回実行する（副作用のみ）。
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
  // 入力（currentPackageNames）を安定化して、`getSnapshot` の同一性維持に使う。
  const namesKey = currentPackageNames.join('\x00')

  const readyState = useMemo<SeenDigestState>(() => {
    const seen = readSeen()
    const diff = computeDigestDiff(currentPackageNames, seen)
    return { status: 'ready', newNames: diff.newNames, isFirstVisit: diff.isFirstVisit }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [namesKey])

  const pendingState = useMemo<SeenDigestState>(() => ({ status: 'pending' }), [])

  // useSyncExternalStore: 変更を通知しない no-op subscribe で「サーバー=pending / クライアント=ready」を切り替える。
  const state = useSyncExternalStore(
    subscribeNoop,
    () => readyState,
    () => pendingState,
  )

  // seen の書き込みだけを副作用として実行（マウント時 1 回・状態遷移は起こさない）。
  useEffect(() => {
    writeSeen({ date, packageNames: currentPackageNames })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [namesKey, date])

  return <SeenDigestContext.Provider value={state}>{children}</SeenDigestContext.Provider>
}

/** `getSnapshot` の変更を通知しない購読関数。状態は入力（`currentPackageNames`）でのみ変わる。 */
function subscribeNoop(): () => void {
  return () => {}
}

/** `SeenDigestProvider` 配下で差分状態を読む。Provider の外では常に `'pending'`。 */
export function useSeenDigest(): SeenDigestState {
  return useContext(SeenDigestContext)
}
