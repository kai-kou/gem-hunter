import { Button } from './components/button'
import { Input } from './components/input'

/**
 * 検索フォーム（US-6 / AC-2）。
 * GET フォームなのでクライアント JS を持たない（E-8 / NFR-3）。
 * 送信でキーワードが URL のクエリに反映される。
 */
export function SearchForm({ keyword }: { keyword: string }) {
  return (
    <form action="/" method="get" role="search" className="flex gap-2">
      <label htmlFor="q" className="sr-only">
        検索キーワード
      </label>
      <Input
        id="q"
        name="q"
        type="search"
        defaultValue={keyword}
        placeholder="キーワードで GitHub を検索（例: react）"
        className="flex-1"
      />
      <Button type="submit">検索</Button>
    </form>
  )
}
