/**
 * pipeline.mjs — 収集済みの生パッケージ配列（`collect.mjs` の出力）を Gem 候補プールへ
 * 変換する純関数群。`D-37`（`docs/02_requirements/open-questions.md`）の 3 施策
 * （レジストリ別成層化・汚染フィルタ・repo 単位 dedupe）をここで実装する。
 *
 * 🔴 I/O・ネットワーク・乱数・現在時刻に一切触れない（すべて入力 → 出力の純関数）。
 * テストがネットワークなしで書けることと、収集（`collect.mjs`）と再計算の再実行が
 * 安価であることの両方を担保するため。
 */

// star の判定は「repo_metadata が無い」「repo_metadata はあるが stargazers_count が数値でない」
// 「stargazers_count === 0」「それ以外の有限数」の 4 分岐。① と ② は「欠損」として同じ
// 'missing' に畳む（欠損と真の 0 を区別しないと、Maven で実測 22% のデータを
// 「star=0（過小評価の証拠）」と誤認する・`D-37`）。
export function classifyStars(raw) {
  const meta = raw?.repo_metadata
  if (!meta || typeof meta !== 'object') return 'missing'

  const stars = meta.stargazers_count
  if (typeof stars !== 'number' || !Number.isFinite(stars)) return 'missing'
  if (stars === 0) return 'zero'
  return 'positive'
}

/**
 * GitHub URL（https / git+https / git@github.com:）から owner/repo を抜き出す。
 * `tools/generate_gem_digest.mjs`（旧実装）と同じ規則（SP-17 契約 §4）。
 */
export function extractGithubFullName(url) {
  if (typeof url !== 'string') return null
  const cleaned = url.replace(/^git\+/, '').replace(/\.git$/, '')
  const m =
    /^https?:\/\/github\.com\/([^/]+)\/([^/#?]+)/i.exec(cleaned) ||
    /^git@github\.com:([^/]+)\/([^/#?]+)/i.exec(cleaned)
  if (!m) return null
  return `${m[1]}/${m[2]}`
}

/**
 * Ecosyste.ms の生レコード 1 件を `NormalizedPackage` へ変換する。
 * GitHub 以外・name 不正・dependentCount 非数・star 欠損のいずれかに該当したら候補から落とす
 * （null）。star が「真の 0」であるケースはここでは落とさず `stars: 0` として残す
 * （汚染判定は `isContaminated` が別途担う）。
 */
export function normalizeRecord(raw, registryId) {
  const repositoryFullName = extractGithubFullName(raw?.repository_url)
  if (!repositoryFullName) return null

  const packageName = typeof raw?.name === 'string' && raw.name.trim() !== '' ? raw.name : null
  if (!packageName) return null

  const dependentCount = raw?.dependent_packages_count
  if (typeof dependentCount !== 'number' || !Number.isFinite(dependentCount)) return null

  const starState = classifyStars(raw)
  if (starState === 'missing') return null
  const stars = starState === 'zero' ? 0 : raw.repo_metadata.stargazers_count

  return { registry: registryId, packageName, repositoryFullName, dependentCount, stars }
}

// 汚染フィルタの既定閾値。star=0 かつ被依存数がこの件数以上のパッケージは、
// repo 誤紐付け・自動生成ミラー（例: Maven WebJars）の疑いとして除外する（`D-37`）。
export const DEFAULT_ZERO_STAR_DEPENDENT_THRESHOLD = 1000

/**
 * 「star=0 と高被依存数の組み合わせ」を repo 誤紐付けの疑いとして検出する。
 * 閾値ちょうど（`>=`）も汚染とみなす（境界を安全側に倒す）。
 */
export function isContaminated(pkg, { zeroStarDependentThreshold = DEFAULT_ZERO_STAR_DEPENDENT_THRESHOLD } = {}) {
  return pkg.stars === 0 && pkg.dependentCount >= zeroStarDependentThreshold
}

/**
 * 同一 repository（`repositoryFullName`）を横断的に 1 件へ集約する。
 * 代表は被依存数最大の flagship パッケージ（`D-37`: `min`/`max`/`sum` は却下済み）。
 * 同値のときは packageName 昇順で決定論的にタイブレークする（各候補との単純な
 * 「より小さいか」の比較を積み重ねるだけなので、入力の並び順に結果が依存しない）。
 *
 * 🔴 dedupe は **レジストリを横断して** 行う（同じ repo が npm と pypi 両方に出るケースがある）。
 */
export function dedupeByRepository(items) {
  const byRepo = new Map()
  for (const item of items) {
    const key = item.repositoryFullName
    const existing = byRepo.get(key)
    if (!existing) {
      byRepo.set(key, item)
      continue
    }
    if (
      item.dependentCount > existing.dependentCount ||
      (item.dependentCount === existing.dependentCount && item.packageName < existing.packageName)
    ) {
      byRepo.set(key, item)
    }
  }
  // 出力順も決定論的にする（Map の反復順は挿入順＝入力順に依存するため、そのまま返さない）。
  return [...byRepo.values()].sort(
    (a, b) =>
      a.repositoryFullName.localeCompare(b.repositoryFullName) ||
      a.packageName.localeCompare(b.packageName),
  )
}

/**
 * 降順順位（0-indexed・同値は最小順位方式）を計算する。
 * `rank[i]` = 「values[i] より真に大きい値を持つ要素の個数」（0 が最上位）。
 * O(n log n)（ソートしてから同値区間をまとめて埋める）。
 */
function computeDescRanks(values) {
  const n = values.length
  const order = values.map((_, i) => i).sort((a, b) => values[b] - values[a])
  const ranks = new Array(n)
  let i = 0
  while (i < n) {
    let j = i
    while (j < n && values[order[j]] === values[order[i]]) j += 1
    for (let k = i; k < j; k += 1) ranks[order[k]] = i
    i = j
  }
  return ranks
}

function round2(value) {
  return Math.round(value * 100) / 100
}

/**
 * レジストリ **ごと** に自前プール内でパーセンタイル順位を再計算し、`gemIndex` を算出する
 * （`D-37`: グローバル再計算は却下済み・上位が npm に支配される）。
 *
 * - `dependentRank` / `starRank`: 降順順位を 0〜100 の連続値へ線形写像（0 が最上位）。
 *   同値は同順位（最小順位方式・`computeDescRanks`）。n===1 のときは両方 0（順位が定義できない）。
 * - `gemIndex = round2(dependentRank - starRank)`
 *   （被依存数が上位＝小さい値、star が下位＝大きい値ほど強い負値になり「過小評価」を表す。
 *   `src/domain/model/gem-index.ts` の `computeGemIndex` と同じ向き）。
 */
export function recomputeRanks(items) {
  const byRegistry = new Map()
  for (const item of items) {
    if (!byRegistry.has(item.registry)) byRegistry.set(item.registry, [])
    byRegistry.get(item.registry).push(item)
  }

  const result = []
  for (const group of byRegistry.values()) {
    const n = group.length
    const depRanks = computeDescRanks(group.map((g) => g.dependentCount))
    const starRanks = computeDescRanks(group.map((g) => g.stars))

    for (let idx = 0; idx < n; idx += 1) {
      const dependentRank = n === 1 ? 0 : (depRanks[idx] / (n - 1)) * 100
      const starRank = n === 1 ? 0 : (starRanks[idx] / (n - 1)) * 100
      const item = group[idx]
      result.push({
        registry: item.registry,
        packageName: item.packageName,
        repositoryFullName: item.repositoryFullName,
        dependentCount: item.dependentCount,
        stars: item.stars,
        gemIndex: round2(dependentRank - starRank),
      })
    }
  }
  return result
}

/**
 * 収集済みレジストリ配列から Gem 候補プールを構築する（B のエントリポイント）。
 * normalize → 汚染フィルタ → dedupe（横断）→ recomputeRanks（レジストリ別）→ gemIndex 昇順。
 */
export function buildPool(collected, options = {}) {
  const { zeroStarDependentThreshold = DEFAULT_ZERO_STAR_DEPENDENT_THRESHOLD } = options

  const normalized = []
  for (const { registry, packages } of collected) {
    for (const raw of packages) {
      const item = normalizeRecord(raw, registry)
      if (item) normalized.push(item)
    }
  }

  const clean = normalized.filter((item) => !isContaminated(item, { zeroStarDependentThreshold }))
  const deduped = dedupeByRepository(clean)
  const ranked = recomputeRanks(deduped)
  ranked.sort((a, b) => a.gemIndex - b.gemIndex)
  return ranked
}

/**
 * 実測ログ・README 記録用の統計値を返す（純関数・副作用なし）。
 */
export function poolStats(candidates) {
  const total = candidates.length
  const byRegistry = {}
  let zeroCount = 0
  let min = Infinity
  let max = -Infinity

  for (const c of candidates) {
    byRegistry[c.registry] = (byRegistry[c.registry] ?? 0) + 1
    if (c.stars === 0) zeroCount += 1
    if (c.gemIndex < min) min = c.gemIndex
    if (c.gemIndex > max) max = c.gemIndex
  }

  return {
    total,
    byRegistry,
    starZeroRatio: total === 0 ? 0 : zeroCount / total,
    gemIndexRange: total === 0 ? [0, 0] : [min, max],
  }
}
