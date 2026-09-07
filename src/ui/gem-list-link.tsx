import { Gem } from 'lucide-react'
import Link from 'next/link'
import { cn } from '@/src/shared/cn'
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
 *
 * 🔴 折り返し許容（Issue #831）: ラベル文言（`この検索語の Gem 候補を一覧で見る`）は
 * `buttonVariants` 既定の `whitespace-nowrap` のままだと、狭い viewport（320px）で
 * WCAG 2.2 SC 1.4.12 Text Spacing の `letter-spacing` 上書きを受けたときに画面幅から
 * はみ出す（`e2e/a11y-text-spacing.spec.ts` が実測で検出）。ここでは幅をコンテナ幅に
 * 収め（`w-full`）、ラベルを折り返し可能にする（`whitespace-normal` + ラベル用 `<span>` に
 * `min-w-0`。flex item は既定で `min-width: auto`〈テキストの最長単語幅〉を取り、
 * 直接の子テキストノードのままだと折り返しが利かない場合があるため、明示的に
 * `min-width: 0` を与える）。折り返しても高さがクリップされないよう、`button.tsx` 側の
 * `size` variant は固定高さでなく最小高さ（`min-h-*`）にしてある（同 Issue）。
 * `buttonVariants()` の戻り値は cva の内部 `clsx` 連結でしかなく重複クラスを解決しないため、
 * `cn()`（`twMerge`）を通して `whitespace-nowrap` を確実に上書きする。
 *
 * 🔴 `w-full` は `sm:`（640px）未満だけに限定する（Layer 1 セルフレビュー指摘・PR #1074）。
 * 無条件の `w-full` は `<main>`（`max-w-3xl` = 768px）まで導線を強制的に全幅化し、広い
 * viewport ではコンパクトな ghost リンクだったものが横長バーになる視覚回帰を起こす。
 * 320px での折り返し・はみ出し対策が要るのは狭い viewport だけなので、`sm:w-auto` で
 * 元の shrink-to-fit（コンテンツ幅）へ戻す。
 */
export function GemListLink({ href, label }: { href: string; label: string }) {
  return (
    <Link
      href={href}
      className={cn(
        buttonVariants({ variant: 'ghost', size: 'default' }),
        'w-full gap-1.5 whitespace-normal sm:w-auto',
      )}
    >
      <Gem aria-hidden="true" className="size-4 shrink-0" />
      <span className="min-w-0">{label}</span>
    </Link>
  )
}
