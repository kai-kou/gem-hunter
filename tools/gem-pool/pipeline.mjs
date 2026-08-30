/**
 * Gem 候補プールの変換パイプライン（`SP-17` / Issue #387）。
 *
 * 決定の正本は [`open-questions.md`](../../docs/02_requirements/open-questions.md) の **`D-37`**:
 * Gem Index の母集団は **(1) レジストリ別成層化 + (2) 汚染フィルタ + (3) repo 単位 dedupe** を必須とする。
 * Gem Index の定義は [`ADR 0009`](../../docs/adr/0009-hidden-gem-score-definition.md) §2.1 と
 * `src/domain/model/gem-index.ts`（`Gem Index = 被依存数の順位 − star の順位`・**値が小さいほど過小評価度が高い**）。
 * 🔴 算出式と値域規則の実体は `src/domain/model/gem-index.rules.mjs` が **単一正本**（Issue #276）。
 * 本モジュールと domain の両方がそこから import するため、規則をここへ写さないこと。
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

import {
  RANK_MAX,
  RANK_MIN,
  computeGemIndexValue,
  isValidRank,
} from '../../src/domain/model/gem-index.rules.mjs'

/** `dropped` に載る除外理由。 */
const DROP_REASONS = /** @type {const} */ ([
  'missing-stars',
  'no-dependents',
  'suspicious-zero-star',
  'duplicate-repository',
])

/**
 * プロトタイプ汚染の入口になりうるキー。外部 API 由来の文字列をそのまま集計オブジェクトのキーに
 * するため、通常オブジェクトへの代入時に `Object.prototype` を書き換えられないよう弾く
 * （集計オブジェクト自体も `Object.create(null)` にする多層防御）。
 */
const FORBIDDEN_KEYS = new Set(['__proto__', 'constructor', 'prototype'])

/**
 * パッケージ名の上限長。npm の 214 文字を全レジストリ共通の上限として使う
 * （他レジストリはこれより短い制限しか持たないため、超過分は API の異常値とみなしてよい）。
 */
const MAX_PACKAGE_NAME_LENGTH = 214

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

/** キーだけを持つ空の集計オブジェクト（プロトタイプ汚染の入口を作らない）。 */
function emptyRecord() {
  return Object.create(null)
}

/**
 * 表示を詐称できる文字を含むか。C0/C1 制御文字と双方向制御文字（`U+200E`-`200F` /
 * `U+202A`-`202E` / `U+2066`-`2069`）を対象にする。
 *
 * パッケージ名はトップページのリンクラベルとして表示するため、双方向制御文字が混ざると
 * 表示上の詐称（別パッケージ名に見せる）やレイアウト破壊が成立しうる
 * （React が HTML エスケープするので XSS にはならないが、表示の信頼性は別問題）。
 */
function hasUnsafeCharacter(value) {
  for (const char of value) {
    const code = char.codePointAt(0)
    if (code <= 0x1f || (code >= 0x7f && code <= 0x9f)) return true // C0 / C1 制御文字
    if (code === 0x200e || code === 0x200f) return true // LRM / RLM
    if (code >= 0x202a && code <= 0x202e) return true // LRE / RLE / PDF / LRO / RLO
    if (code >= 0x2066 && code <= 0x2069) return true // LRI / RLI / FSI / PDI
  }
  return false
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
 * 🔵 **`packageName` は外部 API 由来のまま配信物へ載る**ため、他フィールド（`repositoryFullName` の
 * 正規表現・数値の有限性チェック）と同水準で検証する（長さ上限・制御文字 / 双方向制御文字の排除）。
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
  // レジストリ名は集計オブジェクトのキーになる。外部由来の `__proto__` 等はここで弾く。
  if (FORBIDDEN_KEYS.has(registryName)) return null

  const packageName = typeof raw.name === 'string' ? raw.name.trim() : ''
  if (packageName === '') return null
  if (packageName.length > MAX_PACKAGE_NAME_LENGTH) return null
  if (hasUnsafeCharacter(packageName)) return null

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
 * 順位の不変条件（`RANK_MIN`〜`RANK_MAX` の有限数・0 が最上位）を検証する。
 *
 * 🔴 判定そのものは `src/domain/model/gem-index.rules.mjs` の `isValidRank` が **単一正本**
 * （Issue #276）。domain の `computeGemIndex` も同じ関数を使うため、値域を変えるときに
 * 片方だけ取り残されることは起こらない。ここが持つのは「違反をバッチの例外型（`RangeError`）と
 * 対象レコードつきのメッセージで表現する」という契約だけ。
 */
function assertRank(name, value, record) {
  if (!isValidRank(value)) {
    throw new RangeError(
      `${name} は ${RANK_MIN}〜${RANK_MAX} の有限数でなければならない（rankings は 0 が最上位）: ` +
        `${record.registry}/${record.packageName} = ${value}`,
    )
  }
}

/**
 * `D-37 (1)` レジストリ別成層化。**レジストリごとに独立して** パーセンタイル順位を再計算する。
 *
 * - `dependentCount` 降順 / `stars` 降順で **別々に** 順位を付ける（0 が最上位）。
 * - `gemIndex = round2(dependentRank - starRank)`。
 * - 🔴 `stars` が欠損（`null` / 非有限数）のレコードは **ランク計算の母集団に入れず、出力からも落とす**
 *   （落とした件数は `buildPool` の `stats.byRegistry[*].missingStars` に出る）。
 * - 出力の `dependentRank` / `starRank` は 0〜100 の値域を **アサートする**（外れたら例外・上記 `assertRank`）。
 *
 * 🔵 **母集団を渡す側の責任**: 順位は「渡した集合の中での相対位置」でしかない。除外（汚染フィルタ・
 * dedupe）を通した **生き残りだけ** を渡すこと（除外率がレジストリ間で違うと、除外前に振った順位は
 * レジストリごとに違う量だけ切り詰められ、`gemIndex` が系統的に偏る）。`buildPool` は最終順位を
 * 生き残りに対して再計算する。
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
      assertRank('dependentRank', dependentRank, record)
      assertRank('starRank', starRank, record)
      result.push({
        ...record,
        dependentRank,
        starRank,
        gemIndex: round2(computeGemIndexValue(dependentRank, starRank)),
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
 * 🔵 **渡すのは repo dedupe 後の代表レコード**（`buildPool` の段順）。dedupe より前に判定すると、
 * 同一 repo の flagship だけが落ちて被依存数の小さい兄弟パッケージが代表として生き残る。
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
 * 🔵 **キーは小文字化して突き合わせる**（GitHub の owner / repo は大文字小文字を区別しないため、
 * `perl/perl5` と `Perl/perl5` は同一 repo。実測シャード 62,565 件中 65 repo が case 違いで重複していた）。
 * 出力する `repositoryFullName` は **代表レコードの元の綴り** をそのまま保つ。
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
    const key = record.repositoryFullName.toLowerCase()
    const current = representatives.get(key)
    if (current === undefined || isFlagshipOver(record, current)) {
      representatives.set(key, record)
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
 * 変換パイプライン全体。段順は **除外を全部終わらせてから最終順位を振る**:
 *
 * 1. 投影済み入力を受け取る
 * 2. `stars` 欠損を落とす（reason `'missing-stars'`）
 * 3. `dependentCount === 0` を落とす（reason `'no-dependents'`）
 * 4. **暫定順位** を計算する（汚染フィルタの「高被依存帯」判定にだけ使う）
 * 5. **repo 単位 dedupe**（代表 = 被依存数最大の flagship・`D-37 (3)`）
 * 6. **汚染フィルタ**（代表レコードに対して判定・`D-37 (2)`）
 * 7. **最終順位を生き残りだけで再計算**（`restratifyByRegistry`・`D-37 (1)`）
 * 8. `gemIndex` 昇順（同値は `repositoryFullName` 昇順）で返す
 *
 * 🔴 **7 を最後に置く理由**: 除外率はレジストリごとに大きく違う（実測で npm 4.8% 〜 metacpan 86.9%）。
 * 除外前に振った順位のままだと、除外率の高いレジストリは生き残りの `starRank` が上側へ切り詰められて
 * `gemIndex` が正へ寄り、**最終プールの構成比が均衡していても上位帯だけが少数レジストリに支配される**
 * （実測: 上位 300 件が npm + Maven で 84%・6 レジストリが 0 件）。`D-37 (1)` が成層化で避けたはずの
 * 1 レジストリ支配が配信面で再発するため、順位は必ず生き残り集合の中で再計算する。
 *
 * 🔴 **5 を 6 より前に置く理由**: 逆順だと同一 repo の flagship だけが汚染判定で落ち、被依存数の小さい
 * 兄弟パッケージが代表として生き残る（実測で再現）。dedupe を先に置けば判定対象は常に代表になる。
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

  // 集計オブジェクトのキーは外部由来（レジストリ名）になりうるため、`Object.create(null)` を使う。
  // 通常オブジェクトだと `__proto__` キーの代入が `Object.prototype` へ抜ける（プロトタイプ汚染）。
  /** @type {Record<string, {collected:number, missingStars:number, filtered:number, deduped:number, kept:number}>} */
  const statsByRegistry = emptyRecord()
  /** @type {Record<string, number>} */
  const droppedByReason = emptyRecord()
  for (const reason of DROP_REASONS) droppedByReason[reason] = 0

  /** 該当レジストリの集計値を 1 増やす（未知のレジストリは無視する）。 */
  const bump = (registry, key) => {
    const stat = statsByRegistry[registry]
    if (stat !== undefined) stat[key] += 1
  }

  /** ① 投影済み入力 → ② star 欠損の除去 → ③ 被依存 0 件の除去 */
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
      if (record.dependentCount === 0) {
        // 被依存 0 件は Gem 候補になりえない。暫定順位の母集団からも外す。
        statsByRegistry[registry].filtered += 1
        droppedByReason['no-dependents'] += 1
        continue
      }
      // レジストリ名は入力のグループキーを正本とする（入力レコードは破壊しない）。
      projected.push({ ...record, registry })
    }
  }

  // ④ 暫定順位（汚染フィルタの「高被依存帯」判定にだけ使う。最終順位は ⑦ で振り直す）
  const provisional = restratifyByRegistry(projected)

  // ⑤ repo 単位 dedupe（汚染フィルタより前。判定対象を常に代表 = flagship にするため）
  const representatives = dedupeByRepository(provisional)
  const survivors = new Set(representatives)
  for (const record of provisional) {
    if (survivors.has(record)) continue
    droppedByReason['duplicate-repository'] += 1
    bump(record.registry, 'deduped')
  }

  // ⑥ 汚染フィルタ（代表レコードに対して判定）
  const { kept, dropped } = applyPollutionFilter(representatives, options)
  for (const { reason, record } of dropped) {
    droppedByReason[reason] = (droppedByReason[reason] ?? 0) + 1
    bump(record.registry, 'filtered')
  }

  // ⑦ 最終順位を生き残りだけで再計算 → ⑧ gemIndex 昇順
  const records = restratifyByRegistry(kept).sort(
    (a, b) => a.gemIndex - b.gemIndex || compareString(a.repositoryFullName, b.repositoryFullName),
  )
  for (const record of records) bump(record.registry, 'kept')

  const totalUnique = records.length
  /** @type {Record<string, number>} 最終プールのレジストリ別構成比（%・kept が 0 のレジストリは載せない） */
  const registryShare = emptyRecord()
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
