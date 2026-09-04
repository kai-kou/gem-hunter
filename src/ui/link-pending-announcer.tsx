'use client'

import { createContext, useCallback, useContext, useState, type JSX, type ReactNode } from 'react'

type LinkPendingReport = (pending: boolean) => void

/**
 * Provider の外側で `LinkPendingHint` を使ってもエラーにしないための no-op 既定値
 * （視覚ヒントだけが機能し、読み上げは行われない）。
 */
const noop: LinkPendingReport = () => {}

const LinkPendingReportContext = createContext<LinkPendingReport>(noop)

/**
 * 配下のリンクが遷移待ちかどうかを `LinkPendingAnnouncer` へ報告する関数を返す。
 *
 * `report(true)` と `report(false)` は **対で呼ぶ**（`useEffect` のクリーンアップで
 * `report(false)` する）。同時に複数リンクが遷移待ちになりうるため、Announcer 側は
 * 真偽値ではなく件数で保持する。
 */
export function useLinkPendingReport(): LinkPendingReport {
  return useContext(LinkPendingReportContext)
}

/**
 * 配下の `LinkPendingHint` が検知した遷移待ちを、**支援技術へ 1 か所でまとめて** 伝える
 * （`US-22` / `AC-8` / `NFR-12`）。
 *
 * 🔴 **なぜ `LinkPendingHint` 自身をライブリージョンにしないのか**:
 * 詳細リンクは一覧 1 ページに数十個あり、それぞれがライブリージョンになると同種の
 * `role="status"` が大量に並ぶ。ライブリージョンは配下のリンク群に対して **1 個だけ** 置き、
 * 中身の文字列を差し替える。`LinkPendingHint` は `aria-hidden="true"` の視覚ヒント専任のまま
 * 残し、読み上げ経路だけをここへ集約する。
 *
 * 🔴 **要素ごと動的挿入しない**（`ui-ux-guidelines.md` §7.2「ライブリージョンは初期 DOM に
 * 空で常設し、中身を書き換える」）。`pending` の有無で `<span>` を出し入れすると、
 * 挿入直後の変更が `aria-live` の通知として発火しない実装があり読み上げが届かなくなる。
 * 実装の作法は同じく sr-only のライブリージョンを常設する `locale-switch-announcer.tsx` に揃える。
 *
 * 🔵 **既存のライブリージョンとは入れ子にしない**（§7.2 が禁じているのは入れ子と動的挿入で、
 * ライブリージョンが画面に複数あること自体ではない）。トップページでは
 * `<section id="search-status">` と `RepositoryList` の `role="status"` が既に **兄弟として**
 * 共存している（`app/[locale]/page.tsx` の該当コメントが正本）。本コンポーネントも
 * `children` の **後ろの兄弟** としてライブリージョンを 1 個置く。
 * 読み込み中の主表示（`LoadingIndicator` 自身は role を持たない・§4.4 の #180 回帰防止）とは
 * 別文言・別要素なので、遷移中であることと検索結果の状態を取り違えない。
 *
 * ⚠️ **`data-testid` を持たせている理由**（慣行の無自覚な拡大を防ぐための明記）:
 * 1 ページには他にも `role="status"`（検索状態・0 件表示・ロケール切替アナウンス等）が
 * 常設されており、E2E からはロールだけでは本ライブリージョンを一意に特定できない。
 * ロール選択が原理的に効かないこの 1 点のみを理由とする例外であり、`src/ui/` の他要素へ
 * 広げない（ユニットテストは従来どおりロール・文言で検証する）。
 */
export function LinkPendingAnnouncer({
  label,
  children,
}: {
  label: string
  children: ReactNode
}): JSX.Element {
  // 真偽値ではなく件数で持つ。複数リンクが同時に遷移待ちになったとき、先に解決した 1 個の
  // クリーンアップで読み上げが消えてしまうのを防ぐ。
  const [pendingCount, setPendingCount] = useState(0)

  // 参照を安定させる（報告側の `useEffect` の依存に入るため、毎回変わると無限ループになる）。
  const report = useCallback<LinkPendingReport>((pending) => {
    setPendingCount((count) => (pending ? count + 1 : Math.max(0, count - 1)))
  }, [])

  return (
    <LinkPendingReportContext.Provider value={report}>
      {children}
      <span
        data-testid="link-pending-announcer"
        role="status"
        aria-live="polite"
        className="sr-only"
      >
        {pendingCount > 0 ? label : ''}
      </span>
    </LinkPendingReportContext.Provider>
  )
}
