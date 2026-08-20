import type { Locale } from '@/src/domain/model/locale'
import { formatMessage } from '@/src/shared/i18n/format-message'
import type { Messages } from '@/src/shared/i18n/messages'
import { toIntlLocaleTag } from './intl-locale-tag'

/**
 * 利用者に提示するエラー種別（`prd.md` §7 の対応表）。
 *
 * `src/domain/` の判別結果と 1:1 で対応するが、ここでは domain の型を import せず
 * 同等のリテラルユニオンを持つ（`src/shared/i18n/messages.ts` の `MessageLocale` と同じ方針・ARCH-6/7）。
 * `src/ui/` は表示専用なので、エラーオブジェクトから種別を判定する責務は呼び出し側（`app/` 側の結線）にある。
 */
export type ErrorKind =
  | 'network'
  | 'rateLimitPrimary'
  | 'rateLimitSecondary'
  | 'auth'
  | 'validation'
  | 'notFound'
  | 'upstream'

export type ErrorPresentation = {
  /** 利用者向けの本文（プレースホルダー補間済み）。 */
  message: string
  /**
   * 一次レート制限かつ未ログインのときだけ入る、ログイン導線の説明文（`US-25` / `AR-5`）。
   * ここが `undefined` のときは呼び出し側もログインリンクを出さない。
   */
  loginHint?: string
}

type ErrorPresentationParams = {
  locale: 'ja' | 'en'
  /** 一次レート制限の復帰時刻（`x-ratelimit-reset` 由来）。取れない場合は省略する。 */
  retryAfter?: Date
  /** 二次レート制限の再試行までの秒数（`retry-after` 由来）。取れない場合は省略する。 */
  retryAfterSeconds?: number
  /** ログイン済みならログイン導線を出さない（枠は既に増えているため）。 */
  isLoggedIn: boolean
}

/**
 * 復帰時刻の表示書式。日付をまたぐ可能性があるため月日も出す。
 * タイムゾーンは一覧の更新日（`repository-list.tsx`）と揃えて `Asia/Tokyo` に固定する。
 */
function formatResetAt(retryAfter: Date, locale: 'ja' | 'en'): string {
  // `toIntlLocaleTag` はブランド型 `Locale` を受け取るが、値の実体は 'ja' | 'en' の
  // リテラルなのでそのまま渡せる（検証は URL 解決時に済んでいる）。
  return new Intl.DateTimeFormat(toIntlLocaleTag(locale as Locale), {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Asia/Tokyo',
  }).format(retryAfter)
}

/**
 * エラー種別を利用者向けの表示内容へ変換する純関数（`prd.md` §7 / `AC-8` / `US-24`〜`US-25`）。
 *
 * - 内部情報（例外メッセージ・HTTP ステータス）は一切載せない（`NFR-9` / `ui-ux-guidelines.md` §5.1）
 * - 一次レート制限で復帰時刻が取れないとき / 二次レート制限で秒数が取れないときは
 *   それぞれ `...UnknownReset` / `...UnknownRetry` の文言へフォールバックする
 */
export function toErrorPresentation(
  kind: ErrorKind,
  messages: Messages,
  params: ErrorPresentationParams,
): ErrorPresentation {
  const errors = messages.common.errors

  switch (kind) {
    case 'rateLimitPrimary': {
      const message = params.retryAfter
        ? formatMessage(errors.rateLimitPrimary, {
            resetAt: formatResetAt(params.retryAfter, params.locale),
          })
        : errors.rateLimitPrimaryUnknownReset

      return params.isLoggedIn
        ? { message }
        : { message, loginHint: errors.rateLimitPrimaryLoginHint }
    }
    case 'rateLimitSecondary': {
      const message =
        params.retryAfterSeconds === undefined
          ? errors.rateLimitSecondaryUnknownRetry
          : formatMessage(errors.rateLimitSecondary, {
              retryAfterSeconds: String(params.retryAfterSeconds),
            })

      return { message }
    }
    case 'network':
      return { message: errors.network }
    case 'auth':
      return { message: errors.auth }
    case 'validation':
      return { message: errors.validation }
    case 'notFound':
      return { message: errors.notFound }
    case 'upstream':
      return { message: errors.upstream }
  }
}
