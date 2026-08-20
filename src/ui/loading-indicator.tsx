/**
 * 処理中であることを伝える表示専用コンポーネント（`AC-8` / `US-22` / `US-26`）。
 *
 * 🔴 `role="status"` / `aria-live` は自身で持たない（#180・`ui-ux-guidelines.md` §7.2）。
 * このコンポーネントは常に `app/[locale]/page.tsx` の `<section id="search-status"
 * role="status" aria-live="polite">` の内側にだけ `<Suspense>` の fallback として現れる。
 * 以前は自身にも `role="status"` を持っていたため、外側の `section` と入れ子になり、
 * 支援技術に対して未定義動作（二重読み上げ／無視のいずれも起こりうる）を生んでいた。
 * ライブリージョンは画面に唯一（外側の `section`）とし、本コンポーネントは
 * その中身を差し替えるテキスト表示だけを担う。
 *
 * 文言は視覚的にも表示し（`sr-only` にしない）、0 件・エラーと同じ領域で
 * 見た目が区別できるようにする。
 *
 * ⚠️ `ui-ux-guidelines.md` §4.4 が読み込み中に定める 🔵 推奨（実データと同一寸法の
 * カード形状スケルトン・0〜300ms は何も出さない）は **まだ満たしていない**。本実装はテキスト
 * 1 行であり、§4.4 は現状を支持する根拠ではない（🔵 は必須ではないため本スプリントの範囲外）。
 * スケルトン化は別 Issue で対応する。
 */
export function LoadingIndicator({ label }: { label: string }) {
  return (
    <p className="text-muted-foreground animate-pulse py-8 text-sm motion-reduce:animate-none">
      {label}
    </p>
  )
}
