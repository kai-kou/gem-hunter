/** サポートするロケール一覧。既定は日本語（US-9 / E-4）。 */
export const LOCALES = ['ja', 'en'] as const

export type Locale = (typeof LOCALES)[number]

export const DEFAULT_LOCALE: Locale = 'ja'

export function isLocale(value: string): value is Locale {
  return (LOCALES as readonly string[]).includes(value)
}
