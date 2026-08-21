'use client'

import { useEffect, useRef } from 'react'

// モジュールスコープ。ドキュメントのライフサイクル（フルロード/フルリロード）に紐づくため、
// 通常のクライアント遷移（一覧→詳細・詳細→404 等）で <LocaleSwitchAnnouncer> 自体が
// remount されてもこの値は保持される（コンポーネント単位の useRef と違い、remount で
// リセットされない）。
//
// 🔴 判定基準は「マウント回数」ではなく「直前にレンダーされた currentLocale と今回が
// 異なるか」にする（#347 追加タスクのセルフレビュー指摘）。ヘッダーが layout.tsx ではなく
// 各 page.tsx / not-found.tsx の配下にあるため、ロケールを跨がない通常のクライアント遷移
// （例: 一覧 → 詳細）でも本コンポーネントは remount される。「2 回目以降のマウントか」だけを
// 見る実装だと、この最頻出操作のたびに「言語を切り替えました」と誤発火する。
//
// - `previousLocale === undefined`（このドキュメントで初めて評価される）→ 何もアナウンスしない
//   （ページを開いただけで「切り替えました」と言わない）。
// - `previousLocale !== undefined && previousLocale !== currentLocale`
//   → 実際にロケールが変わった → アナウンスする。
// - `previousLocale === currentLocale`（remount されただけでロケールは同じ）→ 発火しない。
// - フルリロード → モジュールが再評価されて `undefined` に戻る → 発火しない。
// - React Strict Mode の mount 二重実行（`next dev`）でも、1 回目の実行で
//   `previousLocale` が `currentLocale` に更新されるため、2 回目の合成実行は
//   「変わっていない」と判定され発火しない。
let previousLocale: string | undefined

/**
 * ロケール切替（`[locale]` セグメントを跨ぐ next/link 遷移）の完了を支援技術へ伝える。
 *
 * Next.js の route announcer は `document.title` の変化だけを見て読み上げを判断するが
 * （`focus-on-navigate.tsx` 冒頭コメント参照）、本アプリの `document.title` は `'gem-hunter'`
 * 固定でロケール非依存のため、言語切替では一切アナウンスされない
 * （`content/discussions/ui_image_assets_20260821` a11y_i18n round3 §4 指摘）。
 *
 * `ui-ux-guidelines.md` §7.2 のライブリージョン規律（初期 DOM に空で常設し、中身だけを
 * 書き換える）を踏襲し、実際にロケールが変わったときだけ内容を書き込む。
 *
 * 🔴 フォーカスは動かさない: `LocaleSwitcher` の各 `<Link key={option}>` は remount されない
 * 設計（`LOCALES` の固定配列・key 不変）で、クリックした要素はブラウザの既定動作でフォーカスを
 * 保持し続ける。ここで forced focus() を呼ぶと、既に正しく「現在のロケールリンク」に乗っている
 * フォーカスを意味なく奪う恐れの方が実害として大きいため、通知専任にする
 * （`FocusOnNavigate` を流用しない理由）。
 */
export function LocaleSwitchAnnouncer({
  currentLocale,
  announcedLabel,
}: {
  currentLocale: string
  announcedLabel: string
}) {
  const liveRef = useRef<HTMLSpanElement>(null)

  useEffect(() => {
    const changed = previousLocale !== undefined && previousLocale !== currentLocale
    previousLocale = currentLocale

    if (changed && liveRef.current) {
      liveRef.current.textContent = announcedLabel
    }
  }, [currentLocale, announcedLabel])

  return <span ref={liveRef} role="status" aria-live="polite" className="sr-only" />
}
