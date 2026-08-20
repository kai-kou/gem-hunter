'use client'

import { useEffect, useRef } from 'react'

/**
 * ルート変更（ページ送り・ソート・件数切替）の完了後、指定した要素へフォーカスを移す
 * （`E-15` / `ui-ux-guidelines.md` §7.1）。
 *
 * Next.js の route announcer は `document.title` の変化だけを見て読み上げを判断するため
 * （`node_modules/next/dist/client/components/app-router-announcer.js`）、`searchParams`
 * だけが変わるページ送り・ソート・件数切替では何もアナウンスされない。加えて
 * `app/[locale]/page.tsx` の `suspenseKey` remount により `Pagination` を含む結果本体が
 * unmount されるため、押したリンク自体が消えてフォーカスが `document.body` へ落ちる
 * （実地調査で確認済み・SP-10 議論ラウンド 1・a11y_impl）。
 *
 * 🔴 検索フォームのネイティブ GET 送信（フルリロード）は対象外（§7.1 の適用範囲）。
 * フルリロードでは本コンポーネントごと初回マウントからやり直しになるため、
 * 「初回描画では focus() を呼ばない」設計がそのまま対象外を実現する（別途の分岐は不要）。
 *
 * `watch` には遷移のたびに値が変わる文字列（例: 現在の検索条件から組み立てた URL）を渡す。
 * `pagination` / `sort-picker` / `per-page-picker` はいずれも `next/link` によるクライアント
 * 遷移で、このコンポーネント自体は remount されずに props（`watch`）だけが更新されるため、
 * `useRef` による初回判定が遷移を跨いで機能する。`targetId` は `tabIndex={-1}` を持つ
 * フォーカス対象要素（結果一覧の見出し）の `id`。
 */
export function FocusOnNavigate({ watch, targetId }: { watch: string; targetId: string }) {
  const isFirstRender = useRef(true)

  useEffect(() => {
    if (isFirstRender.current) {
      // 初回ロード時に勝手にフォーカスを奪わない（ページを開いた瞬間に見出しへ飛ぶのは誤り）。
      isFirstRender.current = false
      return
    }
    document.getElementById(targetId)?.focus()
  }, [watch, targetId])

  return null
}
