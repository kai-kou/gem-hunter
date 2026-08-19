import { DomainValidationError } from '../errors'

/** サポートするロケール一覧。既定は日本語（US-9 / E-4 / domain-model.md §4: `AR-4`）。 */
export const LOCALES = ['ja', 'en'] as const

type LocaleLiteral = (typeof LOCALES)[number]

declare const brand: unique symbol

/** ロケール（`ja` / `en`）。 */
export type Locale = LocaleLiteral & { readonly [brand]: 'Locale' }

export const DEFAULT_LOCALE = 'ja' as Locale

export function isLocale(value: string): value is LocaleLiteral {
  return (LOCALES as readonly string[]).includes(value)
}

export function locale(raw: string): Locale {
  if (!isLocale(raw)) {
    throw new DomainValidationError(
      'Locale',
      raw,
      `ロケールは ${LOCALES.join(' / ')} のみ指定できます`,
    )
  }
  return raw as Locale
}

/** URL 由来の値のように「不正なら既定ロケールへ倒してよい」文脈で使う（domain-model.md §4）。 */
export function tryLocale(raw: string | null | undefined): Locale {
  if (raw == null) {
    return DEFAULT_LOCALE
  }
  try {
    return locale(raw)
  } catch {
    return DEFAULT_LOCALE
  }
}
