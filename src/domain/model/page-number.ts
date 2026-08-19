import { DomainValidationError } from '../errors'

/** GitHub 検索 API が返せる最大件数（1,000 件）と 1 ページの件数から決まる上限。 */
export const PER_PAGE = 30
export const MAX_PAGE = Math.floor(1000 / PER_PAGE)
export const DEFAULT_PAGE = 1

declare const brand: unique symbol

/** ページ番号（1 以上・GitHub 検索の到達可能範囲まで）。 */
export type PageNumber = number & { readonly [brand]: 'PageNumber' }

export function pageNumber(raw: number): PageNumber {
  if (!Number.isInteger(raw) || raw < 1 || raw > MAX_PAGE) {
    throw new DomainValidationError(
      'PageNumber',
      raw,
      `ページ番号は 1〜${MAX_PAGE} の整数で指定してください`,
    )
  }
  return raw as PageNumber
}

/** URL 改変で 500 にしないため、不正値は既定ページへ倒す（domain-model.md §4）。 */
export function tryPageNumber(raw: string | number | null | undefined): PageNumber {
  if (raw == null || raw === '') {
    return DEFAULT_PAGE as PageNumber
  }
  const value = typeof raw === 'number' ? raw : Number(raw)
  try {
    return pageNumber(value)
  } catch {
    return DEFAULT_PAGE as PageNumber
  }
}
