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
  href,
}: {
  locale: Locale
  labels: { backLink: string }
  /**
   * 戻り先 URL の明示指定（SP-7）。検索条件（keyword/page/sort/perPage）を保持したまま
   * 一覧へ戻りたい呼び出し元（`repository-detail.tsx`）が `build-search-url.ts` で組み立てて渡す。
   * 省略時は従来どおり `/${locale}`（検索条件を持たない呼び出し元・`not-found.tsx` 等）。
   */
  href?: string
}) {
  return (
    <Link
      href={href ?? `/${locale}`}
      // 🔴 ネイティブ <a> のブラウザ既定フォーカス（outline: auto）は太さが約 1px しかなく
      // `ui-ux-guidelines.md` §7.3 の「太さ 2px 相当以上」を満たさない（SP-10 実測で判明）。
      // button.tsx / input.tsx / 結果見出し（page.tsx）と同じ `ring-3` パターンへ揃える。
      // 🔴 ネイティブ <a> のブラウザ既定フォーカス（outline: auto）は太さが約 1px しかなく
      // `ui-ux-guidelines.md` §7.3 の「太さ 2px 相当以上」を満たさない（SP-10 実測で判明）。
      // button.tsx / input.tsx / 結果見出し（page.tsx）と同じ `ring-3` パターンへ揃える。
      className="text-primary rounded-sm text-sm underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring"
    >
      {labels.backLink}
    </Link>
  )
}
