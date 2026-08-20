import { DomainValidationError } from '../errors'

/**
 * 日次ダイジェストの唯一のシード（`ADR 0014` §2.2）。UTC 日付文字列 `YYYYMMDD`。
 * 同じ `DateSeed` は全ユーザーで同じ並びを、リロードで同じ再現を、翌日で入れ替わりを保証する。
 *
 * ブランド型 + スマートコンストラクタ（`domain-model.md` §4）。境界（URL の `?date=` /
 * 現在時刻）で必ずこの型へ変換してから usecase へ渡す。
 */

declare const brand: unique symbol

export type DateSeed = string & { readonly [brand]: 'DateSeed' }

const YYYYMMDD_RE = /^(\d{4})(\d{2})(\d{2})$/

/**
 * `YYYYMMDD` 文字列を厳密に検証して包む。形式不一致・存在しない日付（例 `20260231`）は
 * `DomainValidationError`。空白トリムは行わない（境界で必要なら呼び出し側でやる）。
 */
export function parse(raw: string): DateSeed {
  const m = YYYYMMDD_RE.exec(raw)
  if (!m) {
    throw new DomainValidationError(
      'DateSeed',
      raw,
      'DateSeed は YYYYMMDD の 8 桁数字で指定してください',
    )
  }
  const year = Number(m[1])
  const month = Number(m[2])
  const day = Number(m[3])

  // 実在する UTC 日付か（`Date.UTC` はロールオーバーするため、往復で一致確認する）
  const epoch = Date.UTC(year, month - 1, day)
  const d = new Date(epoch)
  if (
    d.getUTCFullYear() !== year ||
    d.getUTCMonth() !== month - 1 ||
    d.getUTCDate() !== day
  ) {
    throw new DomainValidationError(
      'DateSeed',
      raw,
      'DateSeed は実在する UTC 日付で指定してください',
    )
  }
  return raw as DateSeed
}

/**
 * `?date=` の生値を寛容に解釈する。不正値・未指定は `now` の指す当日（UTC）へフォールバック
 * する（`ADR 0014` §2.2: 本番の挙動をパラメータ未指定時と同一に保つ）。
 */
export function tryParse(raw: string | null | undefined, now: Date): DateSeed {
  if (raw == null || raw === '') return toYyyymmdd(now)
  try {
    return parse(raw)
  } catch {
    return toYyyymmdd(now)
  }
}

/** `Date`（UTC）を `YYYYMMDD` の `DateSeed` へ落とす（0 埋め 8 桁）。 */
export function toYyyymmdd(now: Date): DateSeed {
  const yyyy = String(now.getUTCFullYear()).padStart(4, '0')
  const mm = String(now.getUTCMonth() + 1).padStart(2, '0')
  const dd = String(now.getUTCDate()).padStart(2, '0')
  return `${yyyy}${mm}${dd}` as DateSeed
}
