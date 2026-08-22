import Link from 'next/link'

/**
 * 検索結果から Gem 一覧（`/{locale}/gems`）への導線（`SP-19`）。表示だけを持つ
 * Server Component で、文言は props 経由（`E-4`）。
 *
 * `href` の組み立て（ロケール・検索語のクエリ化）は呼び出し側（`app/` の配線）の責務。
 * ここで URL を組み立てると、検索条件の正本が `app/` と `src/ui/` の 2 箇所に分かれる。
 */
export function GemListLink({ href, label }: { href: string; label: string }) {
  return (
    <Link
      href={href}
      // ネイティブ <a> の既定フォーカス（outline: auto）は太さが約 1px しかなく
      // `ui-ux-guidelines.md` §7.3 の「太さ 2px 相当以上」を満たさないため `ring-3` に揃える
      // （`back-link.tsx` / `repository-list.tsx` と同じパターン）。
      className="text-primary rounded-sm text-sm underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring"
    >
      {label}
    </Link>
  )
}
