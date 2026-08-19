import Link from 'next/link'
import type { Locale } from '../domain/model/locale'

/**
 * 一覧（`/{locale}`）へ戻るリンク。詳細画面（`repository-detail.tsx`）と
 * Not Found 画面（`app/[locale]/repos/[owner]/[repo]/not-found.tsx`）の両方から使う
 * 共有コンポーネント。`href`/`className` のコピペ重複を防ぎ、意匠変更を 1 箇所に集約する
 * （PR #127 セルフレビュー指摘2・WARNING）。
 *
 * ARCH-6: `src/ui/` は `src/usecases/` を import しない（本コンポーネントは表示のみ）。
 */
export function BackLink({
  locale,
  labels,
}: {
  locale: Locale
  labels: { backLink: string }
}) {
  return (
    <Link href={`/${locale}`} className="text-primary text-sm underline-offset-4 hover:underline">
      {labels.backLink}
    </Link>
  )
}
