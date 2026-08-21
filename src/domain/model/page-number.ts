import { DomainValidationError } from '../errors'
import { DEFAULT_PER_PAGE } from './per-page'

/**
 * GitHub 検索 API が返せる最大件数（1,000 件）。
 * 🔴 単一の定義元（SSOT・PR #293 セルフレビュー指摘・修正③）。`gem-index` 順ソートの内部取得
 * 上限ページ数（`src/usecases/search-repositories.ts` の `GEM_INDEX_FETCH_MAX_PAGES`）も
 * ここから導出する。数値を 2 箇所に直書きしない。
 */
export const API_RESULT_LIMIT = 1000

/** GitHub 検索 API が返せる最大件数（1,000 件）と既定表示件数（`PerPage` の既定値）から決まる上限。 */
export const MAX_PAGE = Math.floor(API_RESULT_LIMIT / DEFAULT_PER_PAGE)
export const DEFAULT_PAGE = 1

/** 実際に選択された `PerPage` に応じた到達可能な最終ページ（AC-7: 1,000 件を超えるページを要求しない）。 */
export function maxPageFor(perPage: number): number {
  return Math.floor(API_RESULT_LIMIT / perPage)
}

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
