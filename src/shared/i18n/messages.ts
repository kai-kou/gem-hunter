import en from '@/messages/en.json'
import ja from '@/messages/ja.json'

/**
 * `src/shared/` は domain を含むどの層にも依存してはならない（ARCH-7 /
 * application-architecture.md §1.2）。`domain/model/locale.ts` の `Locale`
 * （`'ja' | 'en'` のブランド型）はここでは import せず、代わりに
 * その部分型であるプレーンなリテラル型を持つ（ブランド型の値はそのまま渡せる）。
 */
type MessageLocale = 'ja' | 'en'

const dictionaries = { ja, en } satisfies Record<MessageLocale, typeof ja>

export type Messages = typeof ja

/** ロケールに対応するメッセージカタログを返す（依存を増やさない自前実装・E-4）。 */
export function getMessages(locale: MessageLocale): Messages {
  return dictionaries[locale]
}
