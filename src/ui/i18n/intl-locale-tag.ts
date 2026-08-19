import type { Locale } from '@/src/domain/model/locale'

/**
 * ドメインの `Locale` を `Intl.NumberFormat` / `Intl.DateTimeFormat` 向けの
 * ロケールタグへ変換する（唯一の変換箇所。他の場所で三項演算子を書かない）。
 */
const INTL_LOCALE_TAGS: Record<'ja' | 'en', string> = {
  ja: 'ja-JP',
  en: 'en-US',
}

export function toIntlLocaleTag(locale: Locale): string {
  // ブランド型（unique symbol 交差）はインデックスアクセスのキーとして直接使えないため、
  // 実体である 'ja' | 'en' へ戻す（`locale()` により値は既に検証済み）。
  return INTL_LOCALE_TAGS[locale as 'ja' | 'en']
}
