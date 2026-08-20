import { DomainValidationError } from '../errors'

/**
 * 日次ダイジェストの唯一のシード（`ADR 0014` §2.2）。UTC 日付文字列 `YYYYMMDD`。
 * 同じ `DateSeed` は全ユーザーで同じ並びを、リロードで同じ再現を、翌日で入れ替わりを保証する。
 *
 * ブランド型 + スマートコンストラクタ（`domain-model.md` §4）。境界（URL の `?date=` /
 * 現在時刻）で必ずこの型へ変換してから usecase へ渡す。
 *
 * ⚠️ 本ファイルの関数本体は契約確定用のスタブ。TDD で実装役が置き換える。
 */

declare const brand: unique symbol

export type DateSeed = string & { readonly [brand]: 'DateSeed' }

/**
 * `YYYYMMDD` 文字列を厳密に検証して包む。形式不一致・存在しない日付（例 `20260231`）は
 * `DomainValidationError`。
 *
 * ⚠️ スタブ。実装役が TDD で埋める。
 */
export function parse(_raw: string): DateSeed {
  throw new Error('date-seed.parse: not implemented (SP-14 実装役が TDD で埋める)')
}

/**
 * `?date=` の生値を寛容に解釈する。不正値・未指定は `clock` の指す当日（UTC）へフォールバック
 * する（`ADR 0014` §2.2: 本番の挙動をパラメータ未指定時と同一に保つ）。
 *
 * ⚠️ スタブ。実装役が TDD で埋める。
 */
export function tryParse(_raw: string | null | undefined, _now: Date): DateSeed {
  throw new Error('date-seed.tryParse: not implemented (SP-14 実装役が TDD で埋める)')
}

/** `Date`（UTC）を `YYYYMMDD` の `DateSeed` へ落とす。 */
export function toYyyymmdd(_now: Date): DateSeed {
  throw new Error('date-seed.toYyyymmdd: not implemented (SP-14 実装役が TDD で埋める)')
}
