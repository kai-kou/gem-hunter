/**
 * 再訪時の差分表示（`US-32`）のための純粋関数。
 *
 * 前回訪問時に localStorage へ保存した `SeenDigest`（1 世代のみ保持）と、今回のダイジェスト
 * の `packageName` 一覧を突き合わせ、「新着（前回は無かった）」候補集合と「初回訪問か」を
 * 決定する。DOM・localStorage には一切触れない（`domain-model.md` §4・依存規則）。
 */

/** 前回訪問時に見たダイジェストのスナップショット（`gem-hunter:seen-digest` の値）。 */
export type SeenDigest = {
  /** 前回のダイジェストの日付（`YYYYMMDD`）。 */
  readonly date: string
  /** 前回のダイジェストに含まれていた `packageName` 一覧。 */
  readonly packageNames: readonly string[]
}

export type DigestDiff = {
  /** 今回のダイジェストのうち、前回は見ていなかった `packageName` の集合。 */
  readonly newNames: ReadonlySet<string>
  /** `seen` が無い（= 初回訪問 / ストレージ喪失）ときに `true`。 */
  readonly isFirstVisit: boolean
}

/**
 * 今回の `packageName` 一覧と前回の `SeenDigest` を突き合わせる。
 *
 * - `seen === null`（初回訪問・またはストレージが空/消去/破損している場合の自然劣化）
 *   → 個別の新着マークは付けない（`newNames` は空集合）。`isFirstVisit: true` として
 *     呼び出し側が「初回として全件表示」の注記を出す。
 * - `seen !== null` → 前回の `packageNames` に無かったものだけを `newNames` に含める。
 */
export function computeDigestDiff(
  currentPackageNames: readonly string[],
  seen: SeenDigest | null,
): DigestDiff {
  if (seen === null) {
    return { newNames: new Set(), isFirstVisit: true }
  }

  const seenNames = new Set(seen.packageNames)
  const newNames = new Set(currentPackageNames.filter((name) => !seenNames.has(name)))
  return { newNames, isFirstVisit: false }
}
