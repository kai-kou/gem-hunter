#!/usr/bin/env node
/**
 * shortlist（Gem Index 上位帯・`GEM_INDEX_SHORTLIST_SIZE`）の N 別分布を実データで計測するツール
 * （Issue #335 射程 2）。
 *
 * 🔴 shortlist 選定ロジックは再実装しない。`src/domain/model/gem-shortlist.ts` の
 * `selectGemIndexShortlist` / `byGemIndexAsc` を esbuild でその場トランスパイルして import し、
 * 実装と計測がずれないようにする（新規 npm 依存は追加しない・`esbuild` は既存 devDependency）。
 *
 * Usage:
 *   node tools/analyze_shortlist_distribution.mjs [--input <path>] [--json]
 *   node tools/analyze_shortlist_distribution.mjs --self-test
 */

import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = path.resolve(__dirname, '..')
const SHORTLIST_MODULE_PATH = path.join(REPO_ROOT, 'src/domain/model/gem-shortlist.ts')
const DEFAULT_INPUT_PATH = path.join(REPO_ROOT, 'public/data/daily-digest.json')

const CANDIDATE_N_VALUES = [5, 10, 20, 30, 60, 100, 150, 200, 300]

/**
 * `src/domain/model/gem-shortlist.ts` を esbuild でバンドル・トランスパイルし、
 * data: URL 経由で ESM として import する（実装コードと計測ロジックの二重化を避ける）。
 */
async function loadShortlistModule() {
  // esbuild は devDependency（`package.json`）として既に存在する。新規依存を足さない。
  const esbuild = await import('esbuild')
  const result = await esbuild.build({
    entryPoints: [SHORTLIST_MODULE_PATH],
    bundle: true,
    format: 'esm',
    platform: 'node',
    write: false,
    logLevel: 'silent',
  })
  const code = result.outputFiles[0].text
  const dataUrl = 'data:text/javascript;base64,' + Buffer.from(code).toString('base64')
  return import(dataUrl)
}

/** 数値配列の中央値（偶数件は中央 2 件の平均）。空配列は NaN を返す。 */
export function median(values) {
  if (values.length === 0) return NaN
  const sorted = [...values].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  if (sorted.length % 2 === 0) {
    return (sorted[mid - 1] + sorted[mid]) / 2
  }
  return sorted[mid]
}

/** 数値配列の平均。空配列は NaN。 */
export function mean(values) {
  if (values.length === 0) return NaN
  return values.reduce((a, b) => a + b, 0) / values.length
}

/**
 * パーセンタイル（線形補間・R-7 と同等の一般的な定義）。`p` は 0〜100。空配列は NaN。
 */
export function percentile(values, p) {
  if (values.length === 0) return NaN
  const sorted = [...values].sort((a, b) => a - b)
  if (sorted.length === 1) return sorted[0]
  const rank = (p / 100) * (sorted.length - 1)
  const lower = Math.floor(rank)
  const upper = Math.ceil(rank)
  if (lower === upper) return sorted[lower]
  const weight = rank - lower
  return sorted[lower] * (1 - weight) + sorted[upper] * weight
}

/** 条件を満たす件数の割合（0〜1）。空配列は NaN。 */
export function proportion(values, predicate) {
  if (values.length === 0) return NaN
  return values.filter(predicate).length / values.length
}

/**
 * レジストリ別の件数を集計し、ユニーク数と上位 3 件の構成比（{registry, count, share}）を返す。
 */
export function summarizeRegistryDiversity(gems) {
  const counts = new Map()
  for (const gem of gems) {
    const registry = gem.registry ?? '(unknown)'
    counts.set(registry, (counts.get(registry) ?? 0) + 1)
  }
  const total = gems.length
  const sorted = [...counts.entries()]
    .map(([registry, count]) => ({ registry, count, share: total > 0 ? count / total : NaN }))
    .sort((a, b) => b.count - a.count || (a.registry < b.registry ? -1 : 1))
  return {
    uniqueRegistryCount: counts.size,
    top3: sorted.slice(0, 3),
  }
}

/**
 * 1 集団（shortlist または母集団全体）の統計サマリーを計算する。
 */
export function summarizeGemGroup(gems) {
  const stars = gems.map((g) => g.stars)
  const gemIndexes = gems.map((g) =>
    typeof g.gemIndex === 'number' ? g.gemIndex : Number(g.gemIndex),
  )
  return {
    count: gems.length,
    stars: {
      median: median(stars),
      mean: mean(stars),
      min: stars.length > 0 ? Math.min(...stars) : NaN,
      max: stars.length > 0 ? Math.max(...stars) : NaN,
      p25: percentile(stars, 25),
      p75: percentile(stars, 75),
      shareUnder1000: proportion(stars, (s) => s < 1000),
      shareUnder100: proportion(stars, (s) => s < 100),
      shareZero: proportion(stars, (s) => s === 0),
    },
    gemIndex: {
      median: median(gemIndexes),
      min: gemIndexes.length > 0 ? Math.min(...gemIndexes) : NaN,
      max: gemIndexes.length > 0 ? Math.max(...gemIndexes) : NaN,
    },
    registryDiversity: summarizeRegistryDiversity(gems),
  }
}

/**
 * 候補プール全体に対して、指定した N 値ごとの shortlist 統計を計算する。
 * N がプール件数を超える値は自動的に除外する。プール件数と同じ N は残す（全件 shortlist の意味を持つため）。
 */
export function analyzeDistribution(
  candidates,
  { nValues = CANDIDATE_N_VALUES, baseLimit = 5, shortlistFn } = {},
) {
  const poolSize = candidates.length
  const applicableN = nValues.filter((n) => n <= poolSize)
  const perN = applicableN.map((n) => {
    const shortlist = shortlistFn(candidates, n)
    return {
      n,
      poolMultiplier: baseLimit > 0 ? n / baseLimit : NaN,
      ...summarizeGemGroup(shortlist),
    }
  })
  return {
    poolSize,
    poolSummary: summarizeGemGroup(candidates),
    perN,
  }
}

function formatNumber(value, digits = 1) {
  if (Number.isNaN(value)) return 'n/a'
  return value.toFixed(digits)
}

function formatShare(value) {
  if (Number.isNaN(value)) return 'n/a'
  return `${(value * 100).toFixed(1)}%`
}

function renderHumanReadable(result) {
  const lines = []
  lines.push(`## shortlist 分布分析（候補プール件数: ${result.poolSize}）`)
  lines.push('')
  lines.push('### プール全体')
  lines.push(
    `stars: median=${formatNumber(result.poolSummary.stars.median)} mean=${formatNumber(result.poolSummary.stars.mean)} min=${formatNumber(result.poolSummary.stars.min, 0)} max=${formatNumber(result.poolSummary.stars.max, 0)} p25=${formatNumber(result.poolSummary.stars.p25)} p75=${formatNumber(result.poolSummary.stars.p75)} <1000=${formatShare(result.poolSummary.stars.shareUnder1000)} <100=${formatShare(result.poolSummary.stars.shareUnder100)} ==0=${formatShare(result.poolSummary.stars.shareZero)}`,
  )
  lines.push(
    `gemIndex: median=${formatNumber(result.poolSummary.gemIndex.median, 2)} min=${formatNumber(result.poolSummary.gemIndex.min, 2)} max=${formatNumber(result.poolSummary.gemIndex.max, 2)}`,
  )
  lines.push(
    `registry: unique=${result.poolSummary.registryDiversity.uniqueRegistryCount} top3=${result.poolSummary.registryDiversity.top3
      .map((r) => `${r.registry}(${formatShare(r.share)})`)
      .join(', ')}`,
  )
  lines.push('')
  lines.push(
    '| N | 倍率(/5) | stars中央値 | stars平均 | min | max | p25 | p75 | <1000 | <100 | ==0 | gemIndex中央値 | gemIndex min | gemIndex max | registry種数 | 上位3レジストリ構成比 |',
  )
  lines.push('|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|')
  for (const row of result.perN) {
    const top3 = row.registryDiversity.top3
      .map((r) => `${r.registry}:${formatShare(r.share)}`)
      .join(' / ')
    lines.push(
      `| ${row.n} | ${formatNumber(row.poolMultiplier)} | ${formatNumber(row.stars.median)} | ${formatNumber(row.stars.mean)} | ${formatNumber(row.stars.min, 0)} | ${formatNumber(row.stars.max, 0)} | ${formatNumber(row.stars.p25)} | ${formatNumber(row.stars.p75)} | ${formatShare(row.stars.shareUnder1000)} | ${formatShare(row.stars.shareUnder100)} | ${formatShare(row.stars.shareZero)} | ${formatNumber(row.gemIndex.median, 2)} | ${formatNumber(row.gemIndex.min, 2)} | ${formatNumber(row.gemIndex.max, 2)} | ${row.registryDiversity.uniqueRegistryCount} | ${top3} |`,
    )
  }
  return lines.join('\n')
}

// ---------------------------------------------------------------------------
// self-test（ネットワーク不要・固定の小さな合成データ。CLI 入口 main() 経由で実行する）
// ---------------------------------------------------------------------------

function assertEqual(actual, expected, message) {
  const a = JSON.stringify(actual)
  const e = JSON.stringify(expected)
  if (a !== e) {
    throw new Error(`self-test failed: ${message}\n  actual:   ${a}\n  expected: ${e}`)
  }
}

function assertClose(actual, expected, message, epsilon = 1e-9) {
  if (Number.isNaN(expected)) {
    if (!Number.isNaN(actual)) {
      throw new Error(`self-test failed: ${message}\n  actual:   ${actual}\n  expected: NaN`)
    }
    return
  }
  if (Math.abs(actual - expected) > epsilon) {
    throw new Error(`self-test failed: ${message}\n  actual:   ${actual}\n  expected: ${expected}`)
  }
}

function fakeShortlist(candidates, size) {
  if (size <= 0) return []
  return [...candidates].sort((a, b) => a.gemIndex - b.gemIndex).slice(0, size)
}

function makeGem(overrides) {
  return {
    packageName: 'pkg',
    repositoryFullName: 'owner/pkg',
    dependentCount: 1,
    stars: 0,
    gemIndex: 0,
    registry: 'npmjs.org',
    ...overrides,
  }
}

async function runSelfTest() {
  const failures = []
  const check = (name, fn) => {
    try {
      fn()
    } catch (err) {
      failures.push(`- ${name}: ${err.message}`)
    }
  }

  // --- median / mean / percentile / proportion の基礎検証 ---
  check('median: 奇数件', () => assertEqual(median([3, 1, 2]), 2))
  check('median: 偶数件', () => assertEqual(median([1, 2, 3, 4]), 2.5))
  check('median: 空配列は NaN', () => assertClose(median([]), NaN))
  check('mean: 単純平均', () => assertEqual(mean([1, 2, 3]), 2))
  check('percentile: p0/p100 は min/max', () => {
    assertEqual(percentile([10, 20, 30, 40], 0), 10)
    assertEqual(percentile([10, 20, 30, 40], 100), 40)
  })
  check('percentile: p50 は median と一致', () =>
    assertEqual(percentile([1, 2, 3, 4], 50), median([1, 2, 3, 4])),
  )
  check('proportion: 条件一致割合', () =>
    assertEqual(
      proportion([1, 2, 3, 4], (v) => v < 3),
      0.5,
    ),
  )
  check('proportion: 空配列は NaN', () =>
    assertClose(
      proportion([], () => true),
      NaN,
    ),
  )

  // --- registry 多様性 ---
  check('summarizeRegistryDiversity: ユニーク数と上位3構成比', () => {
    const gems = [
      makeGem({ registry: 'npmjs.org' }),
      makeGem({ registry: 'npmjs.org' }),
      makeGem({ registry: 'pypi.org' }),
      makeGem({ registry: 'proxy.golang.org' }),
    ]
    const result = summarizeRegistryDiversity(gems)
    assertEqual(result.uniqueRegistryCount, 3)
    assertEqual(result.top3[0].registry, 'npmjs.org')
    assertClose(result.top3[0].share, 0.5)
  })
  check('summarizeRegistryDiversity: 空配列は share が NaN にならず 0 件扱い', () => {
    const result = summarizeRegistryDiversity([])
    assertEqual(result.uniqueRegistryCount, 0)
    assertEqual(result.top3.length, 0)
  })

  // --- analyzeDistribution: N の切り詰め（境界の外側） ---
  check('analyzeDistribution: N がプール件数超は除外される', () => {
    const candidates = [
      makeGem({ packageName: 'a', gemIndex: 1, stars: 10 }),
      makeGem({ packageName: 'b', gemIndex: 2, stars: 20 }),
    ]
    const result = analyzeDistribution(candidates, {
      nValues: [1, 2, 5, 10],
      shortlistFn: fakeShortlist,
    })
    assertEqual(
      result.perN.map((r) => r.n),
      [1, 2],
    )
  })
  check('analyzeDistribution: N=0 相当（nValues に 0 を含めても空 shortlist を返す）', () => {
    const candidates = [makeGem({ packageName: 'a', gemIndex: 1, stars: 10 })]
    const result = analyzeDistribution(candidates, { nValues: [0], shortlistFn: fakeShortlist })
    assertEqual(result.perN[0].count, 0)
    assertClose(result.perN[0].stars.median, NaN)
  })
  check('analyzeDistribution: 空プールは poolSize=0 で全統計が NaN/0', () => {
    const result = analyzeDistribution([], { nValues: [5], shortlistFn: fakeShortlist })
    assertEqual(result.poolSize, 0)
    assertEqual(result.perN.length, 0) // 5 > poolSize(0) なので除外される
    assertClose(result.poolSummary.stars.median, NaN)
    assertEqual(result.poolSummary.registryDiversity.uniqueRegistryCount, 0)
  })
  check('analyzeDistribution: stars 欠落（undefined）でも例外を投げない', () => {
    const candidates = [makeGem({ packageName: 'a', gemIndex: 1, stars: undefined })]
    const result = analyzeDistribution(candidates, { nValues: [1], shortlistFn: fakeShortlist })
    assertClose(result.perN[0].stars.min, NaN)
  })
  check(
    'analyzeDistribution: baseLimit=0 のとき poolMultiplier は NaN（0 除算を起こさない）',
    () => {
      const candidates = [makeGem({ packageName: 'a', gemIndex: 1, stars: 10 })]
      const result = analyzeDistribution(candidates, {
        nValues: [1],
        baseLimit: 0,
        shortlistFn: fakeShortlist,
      })
      assertClose(result.perN[0].poolMultiplier, NaN)
    },
  )

  // --- 実装（gem-shortlist.ts）との結合: 実際に import して比較する ---
  check(
    '実装結合: selectGemIndexShortlist が gemIndex 昇順・packageName タイブレークで選ぶ',
    () => {
      const mod = globalThis.__shortlistModuleForSelfTest
      const candidates = [
        makeGem({ packageName: 'b', gemIndex: 5 }),
        makeGem({ packageName: 'a', gemIndex: 5 }),
        makeGem({ packageName: 'c', gemIndex: 1 }),
      ]
      const shortlist = mod.selectGemIndexShortlist(candidates, 2)
      assertEqual(
        shortlist.map((g) => g.packageName),
        ['c', 'a'],
      )
    },
  )
  check(
    '実装結合: GEM_INDEX_SHORTLIST_SIZE は現行値 60（据え置き根拠は JSDoc・変更時はこの数値も更新する）',
    () => {
      const mod = globalThis.__shortlistModuleForSelfTest
      assertEqual(mod.GEM_INDEX_SHORTLIST_SIZE, 60)
    },
  )

  return failures
}

// ---------------------------------------------------------------------------
// CLI エントリポイント
// ---------------------------------------------------------------------------

function parseArgs(argv) {
  const args = { input: DEFAULT_INPUT_PATH, json: false, selfTest: false }
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i]
    if (arg === '--input') {
      args.input = argv[++i]
    } else if (arg === '--json') {
      args.json = true
    } else if (arg === '--self-test') {
      args.selfTest = true
    }
  }
  return args
}

export async function main(argv = process.argv.slice(2)) {
  const args = parseArgs(argv)
  const shortlistModule = await loadShortlistModule()

  if (args.selfTest) {
    // 実装結合テストが `globalThis` 経由でモジュールを参照できるようにする
    // （self-test は CLI 入口 main() を経由させる要件のため、ここで橋渡しする）。
    globalThis.__shortlistModuleForSelfTest = shortlistModule
    const failures = await runSelfTest()
    delete globalThis.__shortlistModuleForSelfTest
    if (failures.length > 0) {
      console.error(`self-test FAILED (${failures.length} 件):`)
      for (const f of failures) console.error(f)
      process.exitCode = 1
      return
    }
    console.log('self-test PASSED (all checks green)')
    return
  }

  const raw = readFileSync(args.input, 'utf-8')
  const data = JSON.parse(raw)
  const candidates = data.candidates
  if (!Array.isArray(candidates)) {
    console.error(`入力 JSON に candidates 配列が見つからない: ${args.input}`)
    process.exitCode = 1
    return
  }

  const result = analyzeDistribution(candidates, {
    nValues: CANDIDATE_N_VALUES,
    baseLimit: 5,
    shortlistFn: shortlistModule.selectGemIndexShortlist,
  })

  if (args.json) {
    console.log(JSON.stringify(result, null, 2))
  } else {
    console.log(renderHumanReadable(result))
  }
}

const isMainModule = pathToFileURL(process.argv[1] ?? '').href === import.meta.url
if (isMainModule) {
  main().catch((err) => {
    console.error(err)
    process.exitCode = 1
  })
}
