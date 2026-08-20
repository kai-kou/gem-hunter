import { DomainValidationError } from '../errors'

export const MAX_KEYWORD_LENGTH = 256

/**
 * 🔴 検索式の修飾子構文（`名前:値` と否定形 `-名前:値`）。
 *
 * キーワードは検索クエリ文字列へそのまま載る（`GithubRepositoryQuery.search()`）。修飾子を
 * 書けてしまうと、アプリが付ける公開限定条件と同じ種類の条件をユーザー側から重ねられ、
 * 検索の意味そのものを差し替えられる（インジェクション）。検索式は「キーワードだけ」を
 * 受け取る契約にして、構文を持ち込ませない。
 *
 * 判定は修飾子名を列挙せずパターンで行う（特定検索エンジンの語彙をドメインへ持ち込まない・
 * 未知/新設の修飾子も自動的に塞げる）。
 */
const QUALIFIER_PATTERN = /(^|\s)-?[A-Za-z_]+:/

/**
 * 🔴 大文字のブール演算子（単独トークンのときだけ演算子として解釈される）。
 *
 * 末尾が `NOT` のキーワードは、後ろに続くトークンを否定してしまう。小文字（`not` / `or` /
 * `and`）は通常語として扱われるので拒否しない（`cats not dogs` を弾かない）。
 */
const BOOLEAN_OPERATOR_PATTERN = /(^|\s)(NOT|OR|AND)(\s|$)/

declare const brand: unique symbol

/** 検索キーワード（空白のみ不可・前後トリム・長さ上限・検索式の構文を含まない）。 */
export type SearchKeyword = string & { readonly [brand]: 'SearchKeyword' }

export function searchKeyword(raw: string): SearchKeyword {
  const trimmed = raw.trim()
  if (trimmed.length === 0) {
    throw new DomainValidationError('SearchKeyword', raw, '検索キーワードを入力してください')
  }
  if (trimmed.length > MAX_KEYWORD_LENGTH) {
    throw new DomainValidationError(
      'SearchKeyword',
      raw,
      `検索キーワードは ${MAX_KEYWORD_LENGTH} 文字以内で入力してください`,
    )
  }
  if (QUALIFIER_PATTERN.test(trimmed)) {
    throw new DomainValidationError(
      'SearchKeyword',
      raw,
      '検索キーワードに修飾子（名前:値 の形式）は使用できません。キーワードだけを入力してください',
    )
  }
  if (BOOLEAN_OPERATOR_PATTERN.test(trimmed)) {
    throw new DomainValidationError(
      'SearchKeyword',
      raw,
      '検索キーワードに大文字の演算子（NOT / OR / AND）は使用できません。小文字で入力してください',
    )
  }
  return trimmed as SearchKeyword
}

/** URL 由来の値のように「不正なら諦めてよい」文脈で使う。 */
export function trySearchKeyword(raw: string | null | undefined): SearchKeyword | null {
  if (raw == null) {
    return null
  }
  try {
    return searchKeyword(raw)
  } catch {
    return null
  }
}
