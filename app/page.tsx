import { searchRepositoriesUseCase } from '@/src/composition/container'
import { DomainError } from '@/src/domain/errors'
import { tryPageNumber } from '@/src/domain/model/page-number'
import type { SearchResult } from '@/src/domain/model/repository'
import { trySearchKeyword } from '@/src/domain/model/search-keyword'
import { RepositoryList } from '@/src/ui/repository-list'
import { SearchForm } from '@/src/ui/search-form'

type SearchState =
  { status: 'idle' } | { status: 'ok'; result: SearchResult } | { status: 'error'; message: string }

async function runSearch(rawKeyword: string, rawPage: string | undefined): Promise<SearchState> {
  // 境界（URL）で値オブジェクトへ変換する（domain-model.md §4）
  const keyword = trySearchKeyword(rawKeyword)
  if (keyword === null) {
    return { status: 'idle' }
  }

  try {
    const result = await searchRepositoriesUseCase()({
      keyword,
      page: tryPageNumber(rawPage),
    })
    return { status: 'ok', result }
  } catch (error) {
    if (error instanceof DomainError) {
      return { status: 'error', message: `検索できませんでした: ${error.message}` }
    }
    throw error
  }
}

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value
}

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{ q?: string | string[]; page?: string | string[] }>
}) {
  const params = await searchParams
  const keyword = first(params.q) ?? ''
  const state = await runSearch(keyword, first(params.page))

  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-10">
      <h1 className="text-2xl font-semibold">gem-hunter</h1>
      <p className="text-muted-foreground mt-1 mb-6 text-sm">
        キーワードで GitHub のリポジトリを検索します。
      </p>

      <SearchForm keyword={keyword} />

      <section className="mt-6" aria-live="polite">
        {state.status === 'idle' ? (
          <p className="text-muted-foreground text-sm">キーワードを入力して検索してください。</p>
        ) : null}

        {state.status === 'error' ? (
          <p role="alert" className="text-destructive text-sm">
            {state.message}
          </p>
        ) : null}

        {state.status === 'ok' ? (
          <>
            <p className="text-muted-foreground text-sm">
              {state.result.totalCount.toLocaleString('ja-JP')} 件中 {state.result.items.length}{' '}
              件を表示
            </p>
            <RepositoryList items={state.result.items} />
          </>
        ) : null}
      </section>
    </main>
  )
}
