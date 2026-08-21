import { DomainValidationError } from '../errors'

/** 並び順として許可する値（`AR-2`）。`gemIndex` は `SP-16`（Gem Index 順・`D-30`）。 */
export const ALLOWED_SORT_ORDERS = ['relevance', 'stars', 'updated', 'gemIndex'] as const
export const DEFAULT_SORT_ORDER: SortOrder = 'relevance' as SortOrder

declare const brand: unique symbol

/** 検索結果の並び順（関連度 / star 数 / 更新日時 / Gem Index）。 */
export type SortOrder = (typeof ALLOWED_SORT_ORDERS)[number] & { readonly [brand]: 'SortOrder' }

function isAllowedSortOrder(value: string): value is (typeof ALLOWED_SORT_ORDERS)[number] {
  return (ALLOWED_SORT_ORDERS as readonly string[]).includes(value)
}

export function parse(raw: string): SortOrder {
  if (!isAllowedSortOrder(raw)) {
    throw new DomainValidationError(
      'SortOrder',
      raw,
      `並び順は ${ALLOWED_SORT_ORDERS.join('/')} のいずれかで指定してください`,
    )
  }
  return raw as SortOrder
}

/** URL 改変で 500 にしないため、不正値は既定並び順へ倒す（domain-model.md §4）。 */
export function tryParse(raw: string | null | undefined): SortOrder {
  if (raw == null || raw === '') {
    return DEFAULT_SORT_ORDER
  }
  try {
    return parse(raw)
  } catch {
    return DEFAULT_SORT_ORDER
  }
}
