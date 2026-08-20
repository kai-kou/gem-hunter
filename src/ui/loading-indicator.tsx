/**
 * 処理中であることを伝える表示専用コンポーネント（`AC-8` / `US-22` / `US-26`）。
 *
 * `role="status"`（暗黙で `polite` + `atomic`）に `aria-live="polite"` を明示併記する。
 * 🔴 `role="alert"` + `aria-live="assertive"` の組み合わせは使わない
 * （iOS VoiceOver で二重読み上げになる・`ui-ux-guidelines.md` §7.2）。
 *
 * 文言は視覚的にも表示し（`sr-only` にしない）、0 件・エラーと同じ領域で
 * 見た目が区別できるようにする（`ui-ux-guidelines.md` §4.4）。
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
