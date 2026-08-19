'use client'

import { useEffect } from 'react'

/**
 * `document.title` を確実に設定するクライアント専用コンポーネント。
 *
 * `app/[locale]/repos/[owner]/[repo]/page.tsx` が実行時に呼ぶ `notFound()` は、React の
 * NotFoundBoundary によるコンポーネント差し替えとして処理される。同ディレクトリの
 * `not-found.tsx` が持つ `generateMetadata` は非ストリーミング応答の初回 SSR `<head><title>` には
 * 効くが、ハイドレーション後の `document.title` の確実性まではメタデータ API の責務外のため、
 * クライアント側でも明示的に設定する（実機検証: ハイドレーション直後の一瞬だけ親レイアウトの
 * 既定値「gem-hunter」が表示され、本コンポーネントの effect が発火して正しい文言に上書きする。
 * PR #127 セルフレビュー指摘1・CRITICAL）。
 *
 * ルートアナウンサー（`node_modules/next/dist/client/components/app-router-announcer.js` 52-59 行目）は
 * `document.title` の変化だけを見て読み上げを判断するため、確実な設定が必須。
 */
export function SetDocumentTitle({ title }: { title: string }) {
  useEffect(() => {
    document.title = title
  }, [title])

  return null
}
