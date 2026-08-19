import { InvalidSearchQueryError } from '../errors'

/** GitHub 検索 API が返せる最大件数（1,000 件）と 1 ページの件数から決まる上限。 */
export const PER_PAGE = 30
export const MAX_PAGE = Math.floor(1000 / PER_PAGE)
export const MAX_KEYWORD_LENGTH = 256

/** 検索条件の値オブジェクト。不変条件はここだけで守る。 */
export class SearchQuery {
  private constructor(
    readonly keyword: string,
    readonly page: number,
  ) {}

  static create(input: { keyword: string; page?: number }): SearchQuery {
    const keyword = input.keyword.trim()
    if (keyword.length === 0) {
      throw new InvalidSearchQueryError('検索キーワードを入力してください')
    }
    if (keyword.length > MAX_KEYWORD_LENGTH) {
      throw new InvalidSearchQueryError(
        `検索キーワードは ${MAX_KEYWORD_LENGTH} 文字以内で入力してください`,
      )
    }

    const page = input.page ?? 1
    if (!Number.isInteger(page) || page < 1 || page > MAX_PAGE) {
      throw new InvalidSearchQueryError(`ページ番号は 1〜${MAX_PAGE} の整数で指定してください`)
    }

    return new SearchQuery(keyword, page)
  }

  equals(other: SearchQuery): boolean {
    return this.keyword === other.keyword && this.page === other.page
  }
}
