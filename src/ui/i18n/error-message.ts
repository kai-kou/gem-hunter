import type { ErrorKind } from '@/src/domain/errors'
import type { Locale } from '@/src/domain/model/locale'
import { formatMessage } from '@/src/shared/i18n/format-message'
import type { Messages } from '@/src/shared/i18n/messages'
import { toIntlLocaleTag } from './intl-locale-tag'

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
  locale: Locale
  /** 一次レート制限の復帰時刻（`x-ratelimit-reset` 由来）。取れない場合は省略する。 */
  retryAfter?: Date
  /** 二次レート制限の再試行までの秒数（`retry-after` 由来）。取れない場合は省略する。 */
  retryAfterSeconds?: number
  /** ログイン済みならログイン導線を出さない（枠は既に増えているため）。 */
  isLoggedIn: boolean
  /**
   * OAuth が本番で設定されているか（`isAuthConfigured()`・`src/composition/auth.ts`）。
   * false のときは `isLoggedIn` の値に関わらずログイン導線を出さない — 未設定の環境では
   * ログイン自体ができないため、案内文だけを表示すると行き止まりの導線になる（Issue #365）。
   */
  isAuthConfigured: boolean
}

/**
 * 復帰時刻の表示書式。日付をまたぐ可能性があるため月日も出す。
 * タイムゾーンは一覧の更新日（`repository-list.tsx`）と揃えて `Asia/Tokyo` に固定する。
 *
 * 🔴 `timeZoneName: 'short'`（ja: `JST` / en: `GMT+9`）で基準を必ず併記する。表示が JST 固定なのに
 * 基準が出ないと、日本国外の利用者が自分のローカル時刻と誤読し、まだ復帰していない時刻に
 * 再試行して再び失敗する（`datetime-rules.md`: 人が読む日時は JST + 基準の明示）。
 */
function formatResetAt(retryAfter: Date, locale: Locale): string {
  return new Intl.DateTimeFormat(toIntlLocaleTag(locale), {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Asia/Tokyo',
    timeZoneName: 'short',
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

      return params.isLoggedIn || !params.isAuthConfigured
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
