import { DomainValidationError } from '../errors'

export const MAX_KEYWORD_LENGTH = 256

declare const brand: unique symbol

/** 検索キーワード（空白のみ不可・前後トリム・長さ上限）。 */
export type SearchKeyword = string & { readonly [brand]: 'SearchKeyword' }

export function searchKeyword(raw: string): SearchKeyword {
  const trimmed = raw.trim()
  if (trimmed.length === 0) {
    throw new DomainValidationError('SearchKeyword', raw, '検索キーワードを入力してください')
  }
  if (trimmed.length > MAX_KEYWORD_LENGTH) {
    throw new DomainValidationError(
      'SearchKeyword',
      raw,
      `検索キーワードは ${MAX_KEYWORD_LENGTH} 文字以内で入力してください`,
    )
  }
  return trimmed as SearchKeyword
}

/** URL 由来の値のように「不正なら諦めてよい」文脈で使う。 */
export function trySearchKeyword(raw: string | null | undefined): SearchKeyword | null {
  if (raw == null) {
    return null
  }
  try {
    return searchKeyword(raw)
  } catch {
    return null
  }
}
