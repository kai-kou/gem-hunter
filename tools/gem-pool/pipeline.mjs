/**
 * Gem 候補プールの変換パイプライン（`SP-17` / Issue #387）。
 *
 * 決定の正本は [`open-questions.md`](../../docs/02_requirements/open-questions.md) の **`D-37`**:
 * Gem Index の母集団は **(1) レジストリ別成層化 + (2) 汚染フィルタ + (3) repo 単位 dedupe** を必須とする。
 * Gem Index の定義は [`ADR 0009`](../../docs/adr/0009-hidden-gem-score-definition.md) §2.1 と
 * `src/domain/model/gem-index.ts`（`Gem Index = 被依存数の順位 − star の順位`・**値が小さいほど過小評価度が高い**）。
 *
 * 本モジュールは **すべて純粋関数** で構成する（`fetch` も `fs` も使わない）。収集（I/O）は収集側の
 * モジュールが担い、ここは「取ってきた生データ → 配信用レコード」の変換だけを持つ。
 *
 * @typedef {Object} PoolRecord            `projectPackage` の出力（ランク付け前）
 * @property {string} registry             レジストリ名（`npm` / `maven` / `cargo` ...）
 * @property {string} packageName          パッケージ名
 * @property {string} repositoryFullName   `owner/repo`
 * @property {number} dependentCount       有限数・0 以上
 * @property {number|null} stars           `null` = 欠損（`D-37 (2)` の ① ②）
 *
 * @typedef {PoolRecord & {dependentRank:number, starRank:number, gemIndex:number}} RankedRecord
 * `dependentRank` / `starRank` は自前プール内・**レジストリ別**に再計算した 0〜100 の
 * パーセンタイル（0 が最上位）。`gemIndex` は `dependentRank - starRank` を小数第 2 位に丸めた値。
 *
 * @typedef {Object} PollutionFilterOptions
 * @property {number} [minStars=1]                     この値未満の star を「疑わしい」とみなす下限
 * @property {number} [highDependentRankPercentile=10] 「高被依存帯」とみなす `dependentRank` の上限
 */

/** `dropped` に載る除外理由。 */
const DROP_REASONS = /** @type {const} */ ([
  'missing-stars',
  'no-dependents',
  'suspicious-zero-star',
  'duplicate-repository',
])

/**
 * GitHub の URL（`https://` / `git+https://` / `git://` / `ssh://` / スキーム省略）から
 * `owner/repo` を取り出すパターン。末尾の `.git` とスラッシュは任意。
 */
const GITHUB_URL_PATTERN =
  /^(?:git\+)?(?:(?:https?|git|ssh):\/\/)?(?:[^@/\s]+@)?(?:www\.)?github\.com\/([^/\s]+)\/([^/\s]+?)(?:\.git)?\/?$/i

/** `git@github.com:owner/repo.git` 形式（SCP ライク）。 */
const GITHUB_SCP_PATTERN =
  /^(?:git\+)?(?:ssh:\/\/)?[^@/\s]+@github\.com:([^/\s]+)\/([^/\s]+?)(?:\.git)?\/?$/i

/** GitHub の owner / repo として許容する文字種。 */
const SEGMENT_PATTERN = /^[A-Za-z0-9._-]+$/

/** 小数第 2 位に丸める（`-0` を作らない）。 */
function round2(value) {
  const rounded = Math.round(value * 100) / 100
  return Object.is(rounded, -0) ? 0 : rounded
}

/** 文字列の昇順比較（タイブレークを決定論にするため常に同じ規則を使う）。 */
function compareString(a, b) {
  return a < b ? -1 : a > b ? 1 : 0
}

/** 有限数かどうか。 */
function isFiniteNumber(value) {
  return typeof value === 'number' && Number.isFinite(value)
}

/**
 * `repository_url` から GitHub の `owner/repo` を解決する。
 * GitHub 以外・解決不能・owner / repo に空白や追加スラッシュが混ざるものは `null`。
 *
 * @param {unknown} repositoryUrl
 * @returns {string|null}
 */
export function parseGitHubRepository(repositoryUrl) {
  if (typeof repositoryUrl !== 'string') return null
  const trimmed = repositoryUrl.trim()
  if (trimmed === '') return null

  const matched = GITHUB_SCP_PATTERN.exec(trimmed) ?? GITHUB_URL_PATTERN.exec(trimmed)
  if (matched === null) return null

  const [, owner, repo] = matched
  if (!SEGMENT_PATTERN.test(owner) || !SEGMENT_PATTERN.test(repo)) return null
  if (repo === '.' || repo === '..' || owner === '.' || owner === '..') return null

  return `${owner}/${repo}`
}

/**
 * Ecosyste.ms の一覧 API のレコード 1 件を `PoolRecord` へ投影する。
 *
 * 🔴 **API が返す `rankings` は使わない**（レジストリ全量に対する順位であり、成層化した自前プールとは
 * 母集団が違う。順位は `restratifyByRegistry` が自前プール内でレジストリ別に再計算する・`D-37 (1)`）。
 *
 * 🔴 **star は 3 状態を区別する**（`D-37 (2)`・実 API で確認済み）:
 * 1. `repo_metadata` 自体が無い → **欠損**（`stars: null`）
 * 2. `repo_metadata` はあるが `stargazers_count` キーが無い / 非有限数 → **欠損**（Maven の実測で 100 件中 22 件）
 * 3. `stargazers_count: 0` が明示 → **真の 0**（`stars: 0`）
 *
 * @param {Record<string, unknown>} raw   一覧 API の 1 レコード
 * @param {string} [registry]             レジストリ名（省略時は `raw.registry.name` を使う）
 * @returns {PoolRecord|null}             投影できないものは `null`
 */
export function projectPackage(raw, registry) {
  if (raw === null || typeof raw !== 'object') return null

  const registryName =
    typeof registry === 'string' && registry !== ''
      ? registry
      : typeof raw.registry === 'object' &&
          raw.registry !== null &&
          typeof raw.registry.name === 'string'
        ? raw.registry.name
        : null
  if (registryName === null) return null

  const packageName = typeof raw.name === 'string' ? raw.name.trim() : ''
  if (packageName === '') return null

  const repositoryFullName = parseGitHubRepository(raw.repository_url)
  if (repositoryFullName === null) return null

  const dependentCount = raw.dependent_packages_count
  // 有限数でないものに加え、負値（API 仕様上は存在しないが混入すると順位を壊す）も弾く。
  if (!isFiniteNumber(dependentCount) || dependentCount < 0) return null

  const metadata = raw.repo_metadata
  const hasMetadata = typeof metadata === 'object' && metadata !== null
  const rawStars = hasMetadata ? metadata.stargazers_count : undefined
  const stars = isFiniteNumber(rawStars) && rawStars >= 0 ? rawStars : null

  return { registry: registryName, packageName, repositoryFullName, dependentCount, stars }
}

/**
 * 値の降順で 0〜100 のパーセンタイル順位を割り当てる（0 が最上位）。
 * `n` 件中の 0 始まりインデックス `i` に対し `rank = n <= 1 ? 0 : (i / (n - 1)) * 100`。
 * **同値は同じランク**（その値が最初に現れるインデックスを使う）。
 *
 * @param {ReadonlyArray<PoolRecord>} records
 * @param {(record: PoolRecord) => number} valueOf
 * @returns {Map<PoolRecord, number>} レコード参照 → ランク
 */
function assignPercentileRanks(records, valueOf) {
  const sorted = [...records].sort(
    (a, b) => valueOf(b) - valueOf(a) || compareString(a.packageName, b.packageName),
  )
  const total = sorted.length
  const ranks = new Map()

  let firstIndexOfValue = 0
  let previousValue = Number.NaN
  sorted.forEach((record, index) => {
    const value = valueOf(record)
    if (index === 0 || value !== previousValue) {
      firstIndexOfValue = index
      previousValue = value
    }
    ranks.set(record, total <= 1 ? 0 : round2((firstIndexOfValue / (total - 1)) * 100))
  })

  return ranks
}

/**
 * `D-37 (1)` レジストリ別成層化。**レジストリごとに独立して** パーセンタイル順位を再計算する。
 *
 * - `dependentCount` 降順 / `stars` 降順で **別々に** 順位を付ける（0 が最上位）。
 * - `gemIndex = round2(dependentRank - starRank)`。
 * - 🔴 `stars` が欠損（`null` / 非有限数）のレコードは **ランク計算の母集団に入れず、出力からも落とす**
 *   （落とした件数は `buildPool` の `stats.byRegistry[*].missingStars` に出る）。
 *
 * 出力は決定論的（レジストリ名昇順 → `dependentCount` 降順 → `packageName` 昇順）。
 *
 * @param {ReadonlyArray<PoolRecord>} records
 * @returns {RankedRecord[]}
 */
export function restratifyByRegistry(records) {
  /** @type {Map<string, PoolRecord[]>} */
  const groups = new Map()
  for (const record of records ?? []) {
    if (!isFiniteNumber(record?.stars)) continue // star 欠損は母集団に入れない
    const group = groups.get(record.registry)
    if (group === undefined) groups.set(record.registry, [record])
    else group.push(record)
  }

  /** @type {RankedRecord[]} */
  const result = []
  for (const registry of [...groups.keys()].sort(compareString)) {
    const group = groups.get(registry)
    const dependentRanks = assignPercentileRanks(group, (record) => record.dependentCount)
    const starRanks = assignPercentileRanks(group, (record) => record.stars)

    const ordered = [...group].sort(
      (a, b) => b.dependentCount - a.dependentCount || compareString(a.packageName, b.packageName),
    )
    for (const record of ordered) {
      const dependentRank = dependentRanks.get(record)
      const starRank = starRanks.get(record)
      result.push({
        ...record,
        dependentRank,
        starRank,
        gemIndex: round2(dependentRank - starRank),
      })
    }
  }

  return result
}

/**
 * `D-37 (2)` 汚染フィルタ。`stars=0` を無検証で「過小評価の証拠」として採用しない。
 *
 * - `dependentCount === 0` → 除外（reason `'no-dependents'`）。
 * - `stars < minStars` **かつ** `dependentRank <= highDependentRankPercentile` → repo 誤紐付けの疑いとして
 *   除外（reason `'suspicious-zero-star'`）。
 * - star が欠損のまま渡された場合は除外（reason `'missing-stars'`。通常は `restratifyByRegistry` が先に落とす）。
 *
 * **2 つのつまみ**（親セッションが実測で閾値を決めるため、どちらも独立に効く）:
 * - `highDependentRankPercentile: 100` → 全帯が対象になる（被依存帯による絞り込みを無効化）。
 * - `minStars: Infinity` → `stars < minStars` が常に真になり、対象帯のものを star の値に関係なく全部落とす。
 *
 * @param {ReadonlyArray<RankedRecord>} records
 * @param {PollutionFilterOptions} [options]
 * @returns {{kept: RankedRecord[], dropped: Array<{reason: string, record: RankedRecord}>}}
 */
export function applyPollutionFilter(records, options = {}) {
  const { minStars = 1, highDependentRankPercentile = 10 } = options

  /** @type {RankedRecord[]} */
  const kept = []
  /** @type {Array<{reason: string, record: RankedRecord}>} */
  const dropped = []

  for (const record of records ?? []) {
    if (!isFiniteNumber(record?.stars)) {
      dropped.push({ reason: 'missing-stars', record })
      continue
    }
    if (record.dependentCount === 0) {
      dropped.push({ reason: 'no-dependents', record })
      continue
    }
    if (record.stars < minStars && record.dependentRank <= highDependentRankPercentile) {
      dropped.push({ reason: 'suspicious-zero-star', record })
      continue
    }
    kept.push(record)
  }

  return { kept, dropped }
}

/**
 * `D-37 (3)` repo 単位 dedupe。同一 `repositoryFullName` の代表は
 * **`dependentCount` が最大の flagship パッケージ**。同値のタイブレークは `packageName` 昇順（決定論）。
 *
 * 🔴 `D-37` が却下したため **実装しない**: `sum` 集約（workspace 分割による被依存数の水増し）/
 * `min`・`max`（`gemIndex`）による代表選定（`arkworks-rs/algebra` でベンチマーク用付属クレートが
 * 代表になり、実際に 1,829 件から依存される `ark-ff` を取りこぼす）。
 *
 * @param {ReadonlyArray<RankedRecord>} records
 * @returns {RankedRecord[]} `repositoryFullName` 昇順
 */
export function dedupeByRepository(records) {
  /** @type {Map<string, RankedRecord>} */
  const representatives = new Map()

  for (const record of records ?? []) {
    const current = representatives.get(record.repositoryFullName)
    if (current === undefined || isFlagshipOver(record, current)) {
      representatives.set(record.repositoryFullName, record)
    }
  }

  return [...representatives.values()].sort((a, b) =>
    compareString(a.repositoryFullName, b.repositoryFullName),
  )
}

/** `candidate` が `current` より flagship としてふさわしいか（被依存数最大 → packageName 昇順）。 */
function isFlagshipOver(candidate, current) {
  if (candidate.dependentCount !== current.dependentCount) {
    return candidate.dependentCount > current.dependentCount
  }
  return compareString(candidate.packageName, current.packageName) < 0
}

/**
 * レジストリ別の投影済み入力を正規化する。`Map` / `{registry, records}[]` / プレーンオブジェクトを受け付ける。
 *
 * @param {Map<string, ReadonlyArray<PoolRecord>>|Array<{registry: string, records: ReadonlyArray<PoolRecord>}>|Record<string, ReadonlyArray<PoolRecord>>} byRegistry
 * @returns {Array<{registry: string, records: ReadonlyArray<PoolRecord>}>}
 */
function normalizeByRegistry(byRegistry) {
  if (byRegistry instanceof Map) {
    return [...byRegistry.entries()].map(([registry, records]) => ({
      registry,
      records: records ?? [],
    }))
  }
  if (Array.isArray(byRegistry)) {
    return byRegistry
      .filter((entry) => entry !== null && typeof entry === 'object')
      .map((entry) => ({ registry: entry.registry, records: entry.records ?? [] }))
  }
  if (byRegistry !== null && typeof byRegistry === 'object') {
    return Object.entries(byRegistry).map(([registry, records]) => ({
      registry,
      records: records ?? [],
    }))
  }
  return []
}

/**
 * 変換パイプライン全体。順序は
 * **投影済み入力 → 欠損 star の除去 → 成層化（レジストリ別ランク再計算）→ 汚染フィルタ → repo dedupe**。
 *
 * 出力 `records` は `gemIndex` 昇順（**値が小さいほど上位＝過小評価度が高い**）で並べ、
 * 同値は `repositoryFullName` 昇順でタイブレークする。入力（`Map` / 配列 / レコード）は破壊しない。
 *
 * @param {Map<string, ReadonlyArray<PoolRecord>>|Array<{registry: string, records: ReadonlyArray<PoolRecord>}>|Record<string, ReadonlyArray<PoolRecord>>} byRegistry
 * @param {PollutionFilterOptions} [options]
 * @returns {{records: RankedRecord[], stats: {
 *   byRegistry: Record<string, {collected: number, missingStars: number, filtered: number, deduped: number, kept: number}>,
 *   totalCollected: number, totalUnique: number,
 *   droppedByReason: Record<string, number>,
 *   registryShare: Record<string, number>
 * }}}
 */
export function buildPool(byRegistry, options = {}) {
  const groups = normalizeByRegistry(byRegistry)

  /** @type {Record<string, {collected:number, missingStars:number, filtered:number, deduped:number, kept:number}>} */
  const statsByRegistry = {}
  /** @type {Record<string, number>} */
  const droppedByReason = Object.fromEntries(DROP_REASONS.map((reason) => [reason, 0]))

  /** @type {PoolRecord[]} */
  const projected = []
  for (const { registry, records } of groups) {
    statsByRegistry[registry] ??= {
      collected: 0,
      missingStars: 0,
      filtered: 0,
      deduped: 0,
      kept: 0,
    }
    for (const record of records) {
      statsByRegistry[registry].collected += 1
      if (!isFiniteNumber(record?.stars)) {
        // `D-37 (2)` の欠損（`repo_metadata` 無し / `stargazers_count` キー無し）は Gem 候補から外す。
        statsByRegistry[registry].missingStars += 1
        droppedByReason['missing-stars'] += 1
        continue
      }
      // レジストリ名は入力のグループキーを正本とする（入力レコードは破壊しない）。
      projected.push({ ...record, registry })
    }
  }

  const ranked = restratifyByRegistry(projected)
  const { kept, dropped } = applyPollutionFilter(ranked, options)
  for (const { reason, record } of dropped) {
    droppedByReason[reason] = (droppedByReason[reason] ?? 0) + 1
    if (statsByRegistry[record.registry] !== undefined)
      statsByRegistry[record.registry].filtered += 1
  }

  const deduped = dedupeByRepository(kept)
  const survivors = new Set(deduped)
  for (const record of kept) {
    if (survivors.has(record)) continue
    droppedByReason['duplicate-repository'] += 1
    if (statsByRegistry[record.registry] !== undefined)
      statsByRegistry[record.registry].deduped += 1
  }

  const records = [...deduped].sort(
    (a, b) => a.gemIndex - b.gemIndex || compareString(a.repositoryFullName, b.repositoryFullName),
  )
  for (const record of records) {
    if (statsByRegistry[record.registry] !== undefined) statsByRegistry[record.registry].kept += 1
  }

  const totalUnique = records.length
  /** @type {Record<string, number>} 最終プールのレジストリ別構成比（%・kept が 0 のレジストリは載せない） */
  const registryShare = {}
  for (const [registry, stat] of Object.entries(statsByRegistry)) {
    if (stat.kept > 0) registryShare[registry] = round2((stat.kept / totalUnique) * 100)
  }

  const totalCollected = Object.values(statsByRegistry).reduce(
    (sum, stat) => sum + stat.collected,
    0,
  )

  return {
    records,
    stats: {
      byRegistry: statsByRegistry,
      totalCollected,
      totalUnique,
      droppedByReason,
      registryShare,
    },
  }
}
