import { DomainValidationError } from '../errors'

export const MAX_OWNER_LENGTH = 39
export const MAX_REPO_LENGTH = 100

const OWNER_PATTERN = /^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?$/
const REPO_PATTERN = /^[A-Za-z0-9._-]+$/

declare const brand: unique symbol

/** GitHub のリポジトリ完全名（"owner/repo"）。 */
export type RepositoryFullName = string & { readonly [brand]: 'RepositoryFullName' }

function isValidOwner(owner: string): boolean {
  return owner.length > 0 && owner.length <= MAX_OWNER_LENGTH && OWNER_PATTERN.test(owner)
}

function isValidRepo(repo: string): boolean {
  return (
    repo.length > 0 &&
    repo.length <= MAX_REPO_LENGTH &&
    REPO_PATTERN.test(repo) &&
    repo !== '.' &&
    repo !== '..'
  )
}

/**
 * owner・repo それぞれの GitHub 命名規則に適合しない値は DomainValidationError（domain-model.md §4）。
 *
 * ## 🔴 本ファイルに 2 系統の判定が同居する理由（GitHub リポジトリ実データ 62,783 件で実測・#141 系）
 *
 * `repositoryFullName` / `tryRepositoryFullName`（本関数系統・**厳格版**）は GitHub の命名規則
 * そのもの（owner は英数字・ハイフンのみ・先頭末尾ハイフン禁止・repo は `[A-Za-z0-9._-]+`）を
 * 検証する。一方 `isLenientRepositoryFullName` / `tryParseLenientRepositoryFullName`（本ファイル
 * 下部・**許容版**）は「スラッシュで 2 分割でき、空白を含まず、`.` / `..` セグメントでない」
 * ことだけを見る、ずっと緩い判定である。
 *
 * **なぜ緩い方が要るか**: 実データ 62,783 件を両系統で全件突合したところ、**厳格版は 26 件
 * （ユニーク owner 25 件）を拒否した**。すべて「owner が末尾ハイフンで終わる実在リポジトリ」
 * （例: `Qix-/color-convert`・`qix-/node-is-arrayish`・`main--/rust-timerfd`）。GitHub 自体は
 * 現在ハイフン終わりの owner 名の作成を禁止しているが、命名規則変更前に作られた既存アカウントは
 * 生き残っている。候補プール（インフラ層が読む配信データ）や一覧画面（UI 層が描く行）は
 * この実データをそのまま扱うため、厳格版で弾くと **実在する正当な行が消える／リンクが壊れる**。
 *
 * **使い分け**:
 * - **実データの読み取り**（配信 JSON のパース・一覧行の描画・検索の同伴指定 URL 解釈など）
 *   → 許容版（`isLenientRepositoryFullName` / `tryParseLenientRepositoryFullName`）を使う
 * - **GitHub の命名規則そのものを検証したい**（新規作成時の入力検証・ドメインの不変条件として
 *   "正しい owner/repo 名" を保証したい）→ 本関数系統（厳格版）を使う
 *
 * 🔴 **厳格版はインフラ層・UI 層の実データ読み取りには使わないこと**。上記のとおり実在データの
 * 一部を拒否し、一覧からの消失・リンク破損を招く（`static-gem-index.ts` / `static-gem-digest.ts` /
 * `gem-list.tsx` は過去に独自の緩い判定を重複実装していたが、本ファイルの許容版へ統合済み）。
 */
export function repositoryFullName(owner: string, repo: string): RepositoryFullName {
  if (!isValidOwner(owner) || !isValidRepo(repo)) {
    throw new DomainValidationError(
      'RepositoryFullName',
      `${owner}/${repo}`,
      'リポジトリ名の形式が正しくありません',
    )
  }
  return `${owner}/${repo}` as RepositoryFullName
}

/** URL 由来の値のように「不正なら諦めてよい」文脈で使う。 */
export function tryRepositoryFullName(
  owner: string | null | undefined,
  repo: string | null | undefined,
): RepositoryFullName | null {
  if (owner == null || repo == null) {
    return null
  }
  try {
    return repositoryFullName(owner, repo)
  } catch {
    return null
  }
}

export function ownerOf(name: RepositoryFullName): string {
  return name.slice(0, name.indexOf('/'))
}

export function repoOf(name: RepositoryFullName): string {
  return name.slice(name.indexOf('/') + 1)
}

/**
 * `owner/repo` の **緩い**（GitHub 命名規則ではなく形だけの）判定パターン。
 * スラッシュ 1 個で 2 分割でき、両セグメントが空白を含まないことだけを見る。
 *
 * 🔴 このパターン **だけでは** ドットだけのセグメント（`.` / `..`）を弾けない
 * （`[^/\s]+` は `.` にも `..` にも一致する）ため、判定関数側で別途チェックする。
 */
const LENIENT_REPOSITORY_FULL_NAME_PATTERN = /^[^/\s]+\/[^/\s]+$/

/**
 * `owner/repo` として受理してよい値か（**許容版**・実データ読み取り用）。
 *
 * GitHub の命名規則（先頭末尾ハイフン禁止・許可文字種）は見ない。実データに末尾ハイフンの
 * owner が実在する事情は本ファイル冒頭の {@link repositoryFullName} JSDoc を参照。
 * パス走査に使われる `.` / `..` セグメントだけは明示的に拒否する（`owner/..` のような値が
 * 通ると、詳細ページへのリンクが URL 正規化で別のページへ化けるため）。
 *
 * 🔴 **用途**: 配信データ（候補プール JSON）のパース・一覧行の描画・検索の同伴指定 URL
 * 解釈など、GitHub 側で既に存在が確定している実データを読み取る場面で使う。新規作成時の
 * 入力検証には使わない（{@link repositoryFullName} の厳格版を使う）。
 */
export function isLenientRepositoryFullName(value: string): boolean {
  if (!LENIENT_REPOSITORY_FULL_NAME_PATTERN.test(value)) {
    return false
  }
  // パターン上ちょうど 2 セグメントなので、それぞれがドットだけでないことを見れば足りる。
  return value.split('/').every((segment) => segment !== '.' && segment !== '..')
}

/**
 * `owner/repo` を許容版の規則で分解する（**許容版**）。分解できなければ `null`。
 *
 * `isLenientRepositoryFullName` と同じ判定を行ったうえで `{ owner, name }` に分割して返す
 * （フィールド名は移設元の `gem-list.tsx` の呼び出し側に合わせている）。UI 層でリンクの
 * 組み立てに使う想定（`ownerOf` / `repoOf` は `RepositoryFullName` 型専用で検証を持たないため、
 * 生の `string` を扱う場面ではこちらを使う）。
 */
export function tryParseLenientRepositoryFullName(
  value: string,
): { readonly owner: string; readonly name: string } | null {
  if (!isLenientRepositoryFullName(value)) {
    return null
  }
  const separatorIndex = value.indexOf('/')
  return { owner: value.slice(0, separatorIndex), name: value.slice(separatorIndex + 1) }
}
