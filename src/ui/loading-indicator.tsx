/**
 * 処理中であることを伝える表示専用コンポーネント（`AC-8` / `US-22` / `US-26`）。
 *
 * `role="status"`（暗黙で `polite` + `atomic`）に `aria-live="polite"` を明示併記する。
 * 🔴 `role="alert"` + `aria-live="assertive"` の組み合わせは使わない
 * （iOS VoiceOver で二重読み上げになる・`ui-ux-guidelines.md` §7.2）。
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
    <p
      role="status"
      aria-live="polite"
      className="text-muted-foreground animate-pulse py-8 text-sm motion-reduce:animate-none"
    >
      {label}
    </p>
  )
}
