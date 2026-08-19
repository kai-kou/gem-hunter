import { DomainValidationError } from '../errors'

/** 表示件数として許可する値（`AR-3`）。任意値はキャッシュ断片化を招くため 3 択に固定する。 */
export const ALLOWED_PER_PAGE = [20, 50, 100] as const
export const DEFAULT_PER_PAGE = 20

declare const brand: unique symbol

/** 検索結果の表示件数（20 / 50 / 100 のみ）。 */
export type PerPage = (typeof ALLOWED_PER_PAGE)[number] & { readonly [brand]: 'PerPage' }

function isAllowedPerPage(value: number): value is (typeof ALLOWED_PER_PAGE)[number] {
  return (ALLOWED_PER_PAGE as readonly number[]).includes(value)
}

export function parse(raw: number): PerPage {
  if (!isAllowedPerPage(raw)) {
    throw new DomainValidationError(
      'PerPage',
      raw,
      `表示件数は ${ALLOWED_PER_PAGE.join('/')} のいずれかで指定してください`,
    )
  }
  return raw as PerPage
}

/** URL 改変で 500 にしないため、不正値は既定表示件数へ倒す（domain-model.md §4）。 */
export function tryParse(raw: string | number | null | undefined): PerPage {
  if (raw == null || raw === '') {
    return DEFAULT_PER_PAGE as PerPage
  }
  const value = typeof raw === 'number' ? raw : Number(raw)
  try {
    return parse(value)
  } catch {
    return DEFAULT_PER_PAGE as PerPage
  }
}
