import { Button } from './components/button'
import { Input } from './components/input'

/**
 * 検索フォーム（US-6 / AC-2）。
 * GET フォームなのでクライアント JS を持たない（E-8 / NFR-3）。
 * 送信でキーワードが URL のクエリに反映される。
 *
 * レイアウトは狭い画面で縦積み、`sm` 以上で横並び。
 * 320px 幅（WCAG 1.4.10 の判定基準点）では入力欄と 44px のボタンを
 * 横並びにすると収まらないため（ui-ux-guidelines.md §4.1）。
 */
export function SearchForm({ keyword }: { keyword: string }) {
  return (
    <form
      action="/"
      method="get"
      role="search"
      className="flex flex-col gap-3 sm:flex-row sm:items-end sm:gap-2"
    >
      <div className="flex-1">
        <label htmlFor="q" className="mb-1 block text-sm font-medium">
          キーワード
        </label>
        <Input id="q" name="q" type="search" defaultValue={keyword} placeholder="例: react" />
      </div>
      <Button type="submit" className="w-full px-6 sm:w-auto">
        検索
      </Button>
    </form>
  )
}
