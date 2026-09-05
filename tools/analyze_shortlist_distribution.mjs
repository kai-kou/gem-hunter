#!/usr/bin/env node
/**
 * shortlist（Gem Index 上位帯・`GEM_INDEX_SHORTLIST_SIZE`）の N 別分布を実データで計測するツール
 * （Issue #335 射程 2）。
 *
 * 🔴 shortlist 選定ロジックは再実装しない。`src/domain/model/gem-shortlist.rules.mjs`
 * （`gem-index.rules.mjs` と同じ「TypeScript を読めない側は型を剥がした共有実装を直接 import する」
 * 解法）を直接 import し、実装と計測がずれないようにする。
 *
 * Usage:
 *   node tools/analyze_shortlist_distribution.mjs [--input <path>] [--json]
 *   node tools/analyze_shortlist_distribution.mjs --self-test
 */

import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

import { selectGemIndexShortlist } from '../src/domain/model/gem-shortlist.rules.mjs'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = path.resolve(__dirname, '..')
const DEFAULT_INPUT_PATH = path.join(REPO_ROOT, 'public/data/daily-digest.json')

const CANDIDATE_N_VALUES = [5, 10, 20, 30, 60, 100, 150, 200, 300]

/** 数値配列から有限数のみを取り出す（欠損・非数値の除外）。 */
function finiteOnly(values) {
  return values.filter((v) => Number.isFinite(v))
}

/** 数値配列の中央値（偶数件は中央 2 件の平均）。空配列は NaN を返す。 */
function median(values) {
  if (values.length === 0) return NaN
  const sorted = [...values].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  if (sorted.length % 2 === 0) {
    return (sorted[mid - 1] + sorted[mid]) / 2
  }
  return sorted[mid]
}

/** 数値配列の平均。空配列は NaN。 */
function mean(values) {
  if (values.length === 0) return NaN
  return values.reduce((a, b) => a + b, 0) / values.length
}

/**
 * パーセンタイル（線形補間・R-7 と同等の一般的な定義）。`p` は 0〜100。空配列は NaN。
 */
function percentile(values, p) {
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
function proportion(values, predicate) {
  if (values.length === 0) return NaN
  return values.filter(predicate).length / values.length
}

/**
 * レジストリ別の件数を集計し、ユニーク数と上位 3 件の構成比（{registry, count, share}）を返す。
 */
function summarizeRegistryDiversity(gems) {
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
 *
 * 🔴 **欠損値（`undefined` / 非数値）は統計関数へ渡す前に除外する**（Issue #335 セルフレビュー
 * CRITICAL 指摘）。除外せず `sort((a,b)=>a-b)` に `undefined` が混じると比較関数が `NaN` を返し、
 * `median` / `percentile` だけが「壊れて見えない誤値」を返す（`mean`/`min`/`max` は `NaN` に
 * 落ちて可視化されるが、`median`/`percentile` は数値のまま静かに誤る）。除外件数は
 * `excludedCount` として出力に明示する（黙って捨てるのも別種の fail-open のため）。
 */
function summarizeGemGroup(gems) {
  const starsRaw = gems.map((g) => g.stars)
  const gemIndexesRaw = gems.map((g) =>
    typeof g.gemIndex === 'number' ? g.gemIndex : Number(g.gemIndex),
  )
  const stars = finiteOnly(starsRaw)
  const gemIndexes = finiteOnly(gemIndexesRaw)
  return {
    count: gems.length,
    stars: {
      excludedCount: starsRaw.length - stars.length,
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
      excludedCount: gemIndexesRaw.length - gemIndexes.length,
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
function analyzeDistribution(
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

/** 欠損除外があった場合だけ `(欠損N件除外)` サフィックスを付ける。無ければ空文字。 */
function formatExcludedSuffix(excludedCount) {
  return excludedCount > 0 ? `(欠損${excludedCount}件除外)` : ''
}

function renderHumanReadable(result) {
  const lines = []
  lines.push(`## shortlist 分布分析（候補プール件数: ${result.poolSize}）`)
  lines.push('')
  lines.push('### プール全体')
  lines.push(
    `stars: median=${formatNumber(result.poolSummary.stars.median)} mean=${formatNumber(result.poolSummary.stars.mean)} min=${formatNumber(result.poolSummary.stars.min, 0)} max=${formatNumber(result.poolSummary.stars.max, 0)} p25=${formatNumber(result.poolSummary.stars.p25)} p75=${formatNumber(result.poolSummary.stars.p75)} <1000=${formatShare(result.poolSummary.stars.shareUnder1000)} <100=${formatShare(result.poolSummary.stars.shareUnder100)} ==0=${formatShare(result.poolSummary.stars.shareZero)}${formatExcludedSuffix(result.poolSummary.stars.excludedCount)}`,
  )
  lines.push(
    `gemIndex: median=${formatNumber(result.poolSummary.gemIndex.median, 2)} min=${formatNumber(result.poolSummary.gemIndex.min, 2)} max=${formatNumber(result.poolSummary.gemIndex.max, 2)}${formatExcludedSuffix(result.poolSummary.gemIndex.excludedCount)}`,
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

function assertIncludes(haystack, needle, message) {
  if (!haystack.includes(needle)) {
    throw new Error(
      `self-test failed: ${message}\n  期待した部分文字列が含まれない: ${JSON.stringify(needle)}`,
    )
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

/**
 * `main()` を通した本番実行パス（`readFileSync` → `JSON.parse` → `Array.isArray` ガード →
 * `analyzeDistribution` → 出力）を実際に検証する。`console.log` を一時的に差し替えて標準出力を
 * 捕捉する。作った一時ファイルは必ず後始末する（成功・失敗いずれの経路でも）。
 */
async function runMainEntryPointTests() {
  const failures = []
  const check = (name, fn) => {
    try {
      fn()
    } catch (err) {
      failures.push(`- ${name}: ${err.message}`)
    }
  }

  const tmpDir = mkdtempSync(path.join(tmpdir(), 'analyze-shortlist-self-test-'))
  const tmpInputPath = path.join(tmpDir, 'synthetic-candidates.json')
  // 意図的に stars に欠損値（undefined → JSON では省略）を 1 件混ぜ、
  // 欠損値フィルタが本番パス経由でも効くことを検証する。
  const synthetic = {
    candidates: [
      makeGem({ packageName: 'alpha', gemIndex: -10, stars: 5, registry: 'npmjs.org' }),
      makeGem({ packageName: 'beta', gemIndex: -8, stars: 6, registry: 'pypi.org' }),
      makeGem({ packageName: 'gamma', gemIndex: -5, stars: undefined, registry: 'npmjs.org' }),
      makeGem({ packageName: 'delta', gemIndex: -3, stars: 8, registry: 'proxy.golang.org' }),
      makeGem({ packageName: 'epsilon', gemIndex: 0, stars: 20, registry: 'pypi.org' }),
    ],
  }
  writeFileSync(tmpInputPath, JSON.stringify(synthetic), 'utf-8')

  const originalLog = console.log
  try {
    // --- 1. 本番パス（人間可読出力） ---
    let humanOutput = ''
    console.log = (msg) => {
      humanOutput += `${msg}\n`
    }
    await main(['--input', tmpInputPath])
    console.log = originalLog

    check('main(): 本番パスが renderHumanReadable の出力を標準出力に出す', () => {
      assertIncludes(humanOutput, 'shortlist 分布分析（候補プール件数: 5）', 'human 出力の見出し')
    })
    check('main(): 欠損値（stars=undefined）を除外件数として明示する', () => {
      assertIncludes(humanOutput, '(欠損1件除外)', '欠損サフィックス')
    })
    check('main(): baseLimit=5 の N=5 行が実データから計算されている', () => {
      // 5 件全部を shortlist(N=5) にすると gemIndex asc で全件並ぶ。stars は [5,6,8,20]（undefined 除外）。
      // median of [5,6,8,20] = (6+8)/2 = 7.0
      assertIncludes(humanOutput, '| 5 | 1.0 | 7.0 |', 'N=5 行の stars 中央値')
    })

    // --- 2. 本番パス（JSON 出力） ---
    let jsonOutput = ''
    console.log = (msg) => {
      jsonOutput += msg
    }
    await main(['--input', tmpInputPath, '--json'])
    console.log = originalLog

    check('main(): --json が有効な JSON を出す', () => {
      const parsed = JSON.parse(jsonOutput)
      assertEqual(parsed.poolSize, 5)
    })
    check('main(): --json も欠損除外件数を持つ', () => {
      const parsed = JSON.parse(jsonOutput)
      assertEqual(parsed.poolSummary.stars.excludedCount, 1)
    })

    // --- 3. renderHumanReadable 単体（列順・見出しとデータの対応） ---
    check('renderHumanReadable: 既知データに対する見出し・特定行の数値', () => {
      const candidates = [
        makeGem({ packageName: 'a', gemIndex: -10, stars: 100, registry: 'npmjs.org' }),
        makeGem({ packageName: 'b', gemIndex: -5, stars: 200, registry: 'pypi.org' }),
      ]
      const result = analyzeDistribution(candidates, { nValues: [2], shortlistFn: fakeShortlist })
      const rendered = renderHumanReadable(result)
      assertIncludes(rendered, '候補プール件数: 2', 'プール件数の見出し')
      assertIncludes(rendered, 'registry: unique=2', 'レジストリユニーク数')
      // N=2: poolMultiplier=2/5=0.4, stars median=(100+200)/2=150.0, min=100, max=200
      assertIncludes(rendered, '| 2 | 0.4 | 150.0 | 150.0 | 100 | 200 |', 'N=2 行の列対応')
    })

    // --- 4. --input 値欠落ガード ---
    check('main(): --input の値欠落は分かりやすいメッセージ + exitCode=1', () => {
      const originalError = console.error
      const originalExitCode = process.exitCode
      let errOutput = ''
      console.error = (msg) => {
        errOutput += `${msg}\n`
      }
      process.exitCode = undefined
      try {
        // main() は非同期だが --input 値欠落は同期的な parseArgs 直後で検知するため await 不要でも良いが、
        // main のシグネチャに合わせて await する。
        void main(['--input'])
      } finally {
        console.error = originalError
      }
      assertIncludes(errOutput, '--input には値が必要です', '値欠落メッセージ')
      assertEqual(process.exitCode, 1, '値欠落時の exitCode')
      process.exitCode = originalExitCode
    })

    // --- 5. candidates 配列なしの JSON ---
    check('main(): candidates 配列が無い JSON は既存のメッセージ + exitCode=1', () => {
      const badInputPath = path.join(tmpDir, 'no-candidates.json')
      writeFileSync(badInputPath, JSON.stringify({ notCandidates: [] }), 'utf-8')
      const originalError = console.error
      const originalExitCode = process.exitCode
      let errOutput = ''
      console.error = (msg) => {
        errOutput += `${msg}\n`
      }
      process.exitCode = undefined
      try {
        void main(['--input', badInputPath])
      } finally {
        console.error = originalError
      }
      assertIncludes(errOutput, 'candidates 配列が見つからない', 'candidates 欠落メッセージ')
      assertEqual(process.exitCode, 1, 'candidates 欠落時の exitCode')
      process.exitCode = originalExitCode
    })

    // --- 6. 不明なフラグ ---
    check('main(): 不明なフラグはエラー + exitCode=1（値欠落・candidates欠落とは別ケース）', () => {
      const originalError = console.error
      const originalExitCode = process.exitCode
      let errOutput = ''
      console.error = (msg) => {
        errOutput += `${msg}\n`
      }
      process.exitCode = undefined
      try {
        void main(['--input', tmpInputPath, '--wat'])
      } finally {
        console.error = originalError
      }
      assertIncludes(errOutput, '不明な引数', '不明フラグのメッセージ')
      assertEqual(process.exitCode, 1, '不明フラグ時の exitCode')
      process.exitCode = originalExitCode
    })

    // --- 7. `--input --json` のように次トークンがフラグの場合、値として消費しない ---
    check('parseArgs: --input の次がフラグ（--json）なら値として奪わずエラーにする', () => {
      const originalError = console.error
      const originalExitCode = process.exitCode
      let errOutput = ''
      console.error = (msg) => {
        errOutput += `${msg}\n`
      }
      process.exitCode = undefined
      try {
        void main(['--input', '--json'])
      } finally {
        console.error = originalError
      }
      assertIncludes(errOutput, '--input には値が必要です', '次トークンがフラグのときのメッセージ')
      assertEqual(process.exitCode, 1, '次トークンがフラグのときの exitCode')
      process.exitCode = originalExitCode
    })
  } finally {
    console.log = originalLog
    rmSync(tmpDir, { recursive: true, force: true })
  }

  return failures
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
  check('summarizeRegistryDiversity: 同数タイは registry 名の asc でタイブレークする', () => {
    // npmjs.org と pypi.org が同数（2件ずつ）タイ。registry の文字列 asc で並ぶはず
    // （'npmjs.org' < 'pypi.org'）。3 位は proxy.golang.org（1件）。
    const gems = [
      makeGem({ registry: 'pypi.org' }),
      makeGem({ registry: 'pypi.org' }),
      makeGem({ registry: 'npmjs.org' }),
      makeGem({ registry: 'npmjs.org' }),
      makeGem({ registry: 'proxy.golang.org' }),
    ]
    const result = summarizeRegistryDiversity(gems)
    assertEqual(result.top3[0].registry, 'npmjs.org')
    assertEqual(result.top3[1].registry, 'pypi.org')
    assertEqual(result.top3[2].registry, 'proxy.golang.org')
  })

  // --- summarizeGemGroup: 合成フィールドの取り違え検知 ---
  check('summarizeGemGroup: p25/p75/shareUnder*/shareZero/gemIndex.* を既知値で検証する', () => {
    const gems = [
      makeGem({ stars: 0, gemIndex: -10 }),
      makeGem({ stars: 50, gemIndex: -5 }),
      makeGem({ stars: 500, gemIndex: 0 }),
      makeGem({ stars: 5000, gemIndex: 5 }),
    ]
    const result = summarizeGemGroup(gems)
    // stars = [0, 50, 500, 5000]
    assertClose(result.stars.p25, percentile([0, 50, 500, 5000], 25), 'p25')
    assertClose(result.stars.p75, percentile([0, 50, 500, 5000], 75), 'p75')
    assertClose(result.stars.shareUnder1000, 0.75, 'shareUnder1000') // 0,50,500 の3件
    assertClose(result.stars.shareUnder100, 0.5, 'shareUnder100') // 0,50 の2件
    assertClose(result.stars.shareZero, 0.25, 'shareZero') // 0 のみ1件
    assertClose(result.gemIndex.median, -2.5, 'gemIndex.median') // median([-10,-5,0,5]) = -2.5
    assertClose(result.gemIndex.min, -10, 'gemIndex.min')
    assertClose(result.gemIndex.max, 5, 'gemIndex.max')
  })
  check('summarizeGemGroup: 欠損値（undefined）を除外し excludedCount に反映する', () => {
    const gems = [
      makeGem({ stars: 5 }),
      makeGem({ stars: 5 }),
      makeGem({ stars: 6 }),
      makeGem({ stars: undefined }),
      makeGem({ stars: 5 }),
      makeGem({ stars: 5 }),
      makeGem({ stars: 8 }),
      makeGem({ stars: 5 }),
      makeGem({ stars: 6 }),
      makeGem({ stars: 7 }),
    ]
    const result = summarizeGemGroup(gems)
    // 有効 9 値 [5,5,5,5,5,6,6,7,8] の正しい中央値は 5（欠損を除外しないと NaN 混入で 5.5 になる）
    assertEqual(result.stars.excludedCount, 1)
    assertClose(result.stars.median, 5, '欠損を除外した median')
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
    assertEqual(result.perN[0].stars.excludedCount, 1)
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

  // --- 実装（gem-shortlist.rules.mjs）との結合: 実際に import して比較する ---
  check(
    '実装結合: selectGemIndexShortlist が gemIndex 昇順・packageName タイブレークで選ぶ',
    () => {
      const candidates = [
        makeGem({ packageName: 'b', gemIndex: 5 }),
        makeGem({ packageName: 'a', gemIndex: 5 }),
        makeGem({ packageName: 'c', gemIndex: 1 }),
      ]
      const shortlist = selectGemIndexShortlist(candidates, 2)
      assertEqual(
        shortlist.map((g) => g.packageName),
        ['c', 'a'],
      )
    },
  )

  // --- CLI 入口 main() を実際に経由する検証（本番パス・renderHumanReadable・異常系） ---
  const mainEntryPointFailures = await runMainEntryPointTests()
  failures.push(...mainEntryPointFailures)

  return failures
}

// ---------------------------------------------------------------------------
// CLI エントリポイント
// ---------------------------------------------------------------------------

/** フラグらしい文字列か（`--` で始まる）。値として消費してよいかの判定に使う。 */
function looksLikeFlag(token) {
  return typeof token === 'string' && token.startsWith('--')
}

function parseArgs(argv) {
  const args = { input: DEFAULT_INPUT_PATH, json: false, selfTest: false, error: null }
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i]
    if (arg === '--input') {
      const next = argv[i + 1]
      if (next === undefined || looksLikeFlag(next)) {
        args.error = '--input には値が必要です（例: --input path/to/candidates.json）'
        return args
      }
      args.input = next
      i++
    } else if (arg === '--json') {
      args.json = true
    } else if (arg === '--self-test') {
      args.selfTest = true
    } else {
      args.error = `不明な引数です: ${arg}`
      return args
    }
  }
  return args
}

export async function main(argv = process.argv.slice(2)) {
  const args = parseArgs(argv)
  if (args.error) {
    console.error(args.error)
    process.exitCode = 1
    return
  }

  if (args.selfTest) {
    const failures = await runSelfTest()
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
    shortlistFn: selectGemIndexShortlist,
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
