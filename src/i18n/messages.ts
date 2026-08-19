import en from '@/messages/en.json'
import ja from '@/messages/ja.json'
import type { Locale } from './config'

const dictionaries = { ja, en } satisfies Record<Locale, typeof ja>

export type Messages = typeof ja

/** ロケールに対応するメッセージカタログを返す（依存を増やさない自前実装・E-4）。 */
export function getMessages(locale: Locale): Messages {
  return dictionaries[locale]
}
