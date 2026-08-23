import { Gem } from 'lucide-react'
import Link from 'next/link'
import { buttonVariants } from './components/button'

/**
 * 検索結果から Gem 一覧（`/{locale}/gems`）への導線（`SP-19`）。表示だけを持つ
 * Server Component で、文言は props 経由（`E-4`）。
 *
 * `href` の組み立て（ロケール・検索語のクエリ化）は呼び出し側（`app/` の配線）の責務。
 * ここで URL を組み立てると、検索条件の正本が `app/` と `src/ui/` の 2 箇所に分かれる。
 *
 * 見た目は `pagination.tsx` / `login-link.tsx` と同じ ghost ボタン（`buttonVariants`）に
 * 合流させる（議論型レビューで確定・飼い主フィードバック: 直前の説明文と同じ `text-sm`
 * テキストリンクに埋もれていた）。`bg-primary`（filled）にしないのは、検索ボタン
 * （`--size-control-xl` の主要 CTA）と主張が競合するため。二次導線なので
 * `size='default'`（`--size-control-md`）で十分。アイコンは装飾（`aria-hidden="true"`）で、
 * 可視ラベルが常に主。アプリのロゴ画像（`public/images/logo.webp`）は流用しない
 * （ブランドマークの転用は「ホームへのリンクでは」という誤読を招くうえ、固定色ラスターで
 * `currentColor` に追従しない）。
 *
 * 高さ・フォントサイズは `buttonVariants` の `size` variant 経由でのみ決まり、生の
 * `h-*` / `text-*` を呼び出し側 `className` に書かない（`ui-ux-guidelines.md` 必須規約）。
 */
export function GemListLink({ href, label }: { href: string; label: string }) {
  return (
    <Link
      href={href}
      className={buttonVariants({ variant: 'ghost', size: 'default', className: 'gap-1.5' })}
    >
      <Gem aria-hidden="true" className="size-4 shrink-0" />
      {label}
    </Link>
  )
}
