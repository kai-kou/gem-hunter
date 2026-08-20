import { SEARCH_PARAM_KEYS } from './url/search-params'
import { Button } from './components/button'
import { Input } from './components/input'

type SearchFormLabels = {
  inputLabel: string
  placeholder: string
  submit: string
}

type SearchFormProps = {
  keyword: string
  action: string
  labels: SearchFormLabels
}

/**
 * 検索フォーム（US-9 / AC-2）。
 * GET フォームなのでクライアント JS を持たない（E-8 / NFR-3）。
 * 送信でキーワードが URL のクエリに反映される（パラメータ名の正本は prd.md §2.4.1 で、
 * SEARCH_PARAM_KEYS はその実装。名前を他ファイルへ直書きしない）。
 */
export function SearchForm({ keyword, action, labels }: SearchFormProps) {
  return (
    <form action={action} method="get" role="search" className="flex gap-2">
      <label htmlFor={SEARCH_PARAM_KEYS.keyword} className="sr-only">
        {labels.inputLabel}
      </label>
      <Input
        id={SEARCH_PARAM_KEYS.keyword}
        name={SEARCH_PARAM_KEYS.keyword}
        type="search"
        size="xl"
        defaultValue={keyword}
        placeholder={labels.placeholder}
        className="flex-1"
      />
      <Button type="submit" size="xl">
        {labels.submit}
      </Button>
    </form>
  )
}
