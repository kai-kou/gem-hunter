'use client'

import { useEffect, useRef } from 'react'

// モジュールスコープ。ドキュメントのライフサイクル（フルロード/フルリロード）に紐づくため、
// [locale] を跨ぐソフトナビゲーションで <LocaleSwitchAnnouncer> 自体が remount されても
// この値は保持される（コンポーネント単位の useRef と違い、remount でリセットされない）。
//
// - 初回ドキュメント読み込み（フルロード）→ モジュールが新規評価されるので false
//   → 何もアナウンスしない（正しい。ページを開いただけで「切り替えました」と言わない）。
// - 言語切替（ソフトナビゲーション・[locale] セグメント遷移）→ モジュール状態は生きているので
//   true → アナウンスする（これが直したい挙動。#347 追加タスクで実測確認済み）。
// - フルリロード → モジュールが再評価されて false → アナウンスしない（正しい）。
let hasMountedInThisDocument = false

/**
 * ロケール切替（`[locale]` セグメントを跨ぐ next/link 遷移）の完了を支援技術へ伝える。
 *
 * Next.js の route announcer は `document.title` の変化だけを見て読み上げを判断するが
 * （`focus-on-navigate.tsx` 冒頭コメント参照）、本アプリの `document.title` は `'gem-hunter'`
 * 固定でロケール非依存のため、言語切替では一切アナウンスされない
 * （`content/discussions/ui_image_assets_20260821` a11y_i18n round3 §4 指摘）。
 *
 * `ui-ux-guidelines.md` §7.2 のライブリージョン規律（初期 DOM に空で常設し、中身だけを
 * 書き換える）を踏襲し、初回マウント時は発火しないガードで、ロケールが変化したときだけ
 * 内容を書き込む。
 *
 * 🔴 初回判定はコンポーネント単位の `useRef` ではなく **モジュールスコープの変数** で持つ
 * （本ファイルのみの実装詳細）: `[locale]` は root layout 自身のパラメータであり、ロケール切替の
 * ソフトナビゲーションで本コンポーネントが remount される（`useRef` が再初期化され「初回」と
 * 誤判定してその回のアナウンスが握り潰される）ことが実機 E2E で確認された
 * （a11y_i18n round3 §4.1 の「未検証事項」が実際に踏まれた・#347 追加タスク）。
 * モジュールスコープならフルドキュメントロード（このモジュールが新規評価される）でだけ
 * `false` に戻り、同一ドキュメント内の remount では値が保持されるため、正しく区別できる。
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
    if (!hasMountedInThisDocument) {
      // このドキュメント内で初めてマウントされた（フルロード直後）。まだアナウンスしない。
      hasMountedInThisDocument = true
      return
    }
    if (liveRef.current) {
      liveRef.current.textContent = announcedLabel
    }
  }, [currentLocale, announcedLabel])

  return <span ref={liveRef} role="status" aria-live="polite" className="sr-only" />
}
