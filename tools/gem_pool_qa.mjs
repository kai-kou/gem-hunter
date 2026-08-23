#!/usr/bin/env node
/**
 * gem_pool_qa.mjs — Gem 候補プール生成物の QA と no-op 判定を行う CLI（Issue #458・`D-39`）。
 *
 * `.github/workflows/gem-pool-refresh.yml`（週次バッチ）が `node tools/generate_gem_digest.mjs`
 * を実行した **直後**、コミット・ブランチ作成の前に呼ぶ。決めることは 2 つだけ:
 *   1. `--check`  … 生成物が壊れていないか（壊れていれば PR を作らせない・fail-closed）
 *   2. `--no-op`  … 前回コミットと実質同じ内容なら、無駄な PR を作らせない
 *
 * 【なぜ jq に依存しないか】
 * GitHub-hosted runner に jq がプリインストールされているかは一次情報で確認できていない
 * （議論ホワイトボード `content/discussions/gem-pool-actions-schedule-20260823/whiteboard.md`
 * round 1 `actions_facts` を参照）。一方 Node 22 はバッチ本体が必須とするため確実に存在する。
 * 判定ロジックはすべて Node の組み込みモジュールだけで完結させる（外部依存ゼロ）。
 *
 * 【設計規律】
 * 判定ロジックは純関数に切り出し、I/O（`git show` / `readFileSync`）と分離する
 * （`tools/check_gem_shards.py` / `tools/check_prod_drift.py` と同じ作法）。これにより
 * `--self-test` はネットワーク・実データ非依存で完走できる。
 *
 * 【`--check` が検査する内容（1 つでも違反すれば exit 1）】
 *   1. 差分パスの限定: 変更・新規ファイルが `public/data/gem-index/` 配下と
 *      `public/data/daily-digest.json` だけであること（生成スクリプトの想定外副作用の検出）
 *   2. レジストリの消失・ゼロ化: 前回 `index.json` の `shards[]` に居た `registry` が、
 *      今回の `shards[]` から消えている、または `count === 0` になっていたら違反
 *   3. レジストリ単位の急減: 各レジストリで `count_今回 / count_前回 < 0.7`（30% 超の減少）なら違反
 *   4. 全体の急減・急増: `totalCount_今回 / totalCount_前回` が `0.85` 未満または `1.15` 超なら違反
 *
 * `--check --json` の出力には合否判定に加えて `comparison`（前回比・レジストリ別件数）を
 * 常に含める。PR 本文が「コミット後に再計算した意味のない差分ゼロ値」を貼らずに済むよう、
 * 呼び出し側（ワークフロー）はこの JSON を生成直後・コミット前に 1 回だけファイルへ保存し、
 * 後続のステップ（PR 本文組み立て）ではそのファイルを読むだけにする（再計算しない）。
 *
 * 🔴 **閾値（0.7 / 0.85 / 1.15）は初期ヒューリスティックであり、実運転で較正し直す前提**である。
 * 根拠は `generate_gem_digest.mjs` の docstring に載っている実測（`minStars` を 1→5 に変えると
 * 88,981→62,565 ＝ 約 30% 減）。これは「意図的な閾値変更」のレジームであり、同一設定の週次運転で
 * ここまで動くのは異常、という桁感でしかない。較正の追跡は Issue（follow-up）を参照。
 *
 * HEAD 側に `index.json` が無い（初回実行）ときは 2〜4 をスキップして PASS にする。
 *
 * 【`--no-op` が判定する内容】
 * `index.json` の `meta.generatedAt` と `daily-digest.json` の `date` は実行のたびに必ず変わる
 * （実行時刻・生成日）。これを正規化してから HEAD 版と比較し、実質差分ゼロなら `no_op=true` を返す。
 * どちらでも exit 0（判定結果は呼び出し側のワークフローが `no_op` フィールドで読む）。
 * 🔴 本モード自身は `git checkout --` を実行しない（副作用を持たせない）。ファイルを戻すのは
 * ワークフロー側の責務（判定結果を見て `git checkout -- public/data/gem-index public/data/daily-digest.json`
 * を実行するかどうかを決める）。
 *
 * 時刻表記: 表示・記録用は JST（`YYYY-MM-DD HH:MM JST`）、機械処理用は UTC を維持
 * （`docs/rules/datetime-rules.md`）。
 *
 * 使い方:
 *   node tools/gem_pool_qa.mjs --check             # 生成物の QA（違反があれば exit 1）
 *   node tools/gem_pool_qa.mjs --check --json       # 機械可読な JSON で結果を出力
 *   node tools/gem_pool_qa.mjs --no-op              # 実質差分ゼロ判定（結果に関わらず exit 0）
 *   node tools/gem_pool_qa.mjs --no-op --json       # 機械可読な JSON で結果を出力
 *   node tools/gem_pool_qa.mjs --self-test          # ネットワーク・実データ不要のユニットテスト
 */

import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

// ── 設定値（generate_gem_digest.mjs / output.mjs と同じパスを正本として参照する） ──
export const SHARD_DIR = 'public/data/gem-index'
export const INDEX_PATH = `${SHARD_DIR}/index.json`
export const DIGEST_PATH = 'public/data/daily-digest.json'

// 🔴 初期ヒューリスティック（docstring 参照・較正は follow-up issue）
export const REGISTRY_MIN_RATIO = 0.7 // 各レジストリの件数が前回比でこれ未満なら違反（30% 超の減少）
export const TOTAL_MIN_RATIO = 0.85 // 全体件数の前回比の下限
export const TOTAL_MAX_RATIO = 1.15 // 全体件数の前回比の上限

const REPO_ROOT = resolve(fileURLToPath(new URL('.', import.meta.url)), '..')

// ============================================================
// 純関数（I/O から分離。--self-test はここだけを検証する）
// ============================================================

/**
 * 差分パスが許可された配下だけかを判定する。
 *
 * @param {string[]} changedPaths `git diff --name-only` + `git ls-files --others --exclude-standard` の結果
 * @returns {{ok: boolean, offending: string[]}} 許可外パスがあれば ok=false・offending に列挙
 */
export function checkDiffScope(changedPaths) {
  const offending = (changedPaths ?? []).filter((p) => !isAllowedPath(p))
  return { ok: offending.length === 0, offending }
}

/** 許可されたパス（`public/data/gem-index/` 配下 または `public/data/daily-digest.json`）か。 */
function isAllowedPath(path) {
  const p = String(path ?? '').trim()
  if (p.length === 0) return true // 空行は無視（差分なし扱い）
  if (p === DIGEST_PATH) return true
  return p.startsWith(`${SHARD_DIR}/`)
}

/**
 * `index.json` の `shards[]` を前回・今回で突き合わせ、レジストリのゼロ化・消失・急減・
 * 全体の急減急増を検出する。
 *
 * @param {{totalCount:number, shards:{registry:string, count:number}[]}|null} prevIndex
 *   HEAD 版の index.json（初回実行なら null）
 * @param {{totalCount:number, shards:{registry:string, count:number}[]}} currIndex 今回の index.json
 * @returns {{ok: boolean, violations: string[]}}
 */
export function checkRegistryCounts(prevIndex, currIndex) {
  // HEAD 側に index.json が無い（初回実行）ときは比較のしようがないため PASS 扱い。
  if (!prevIndex || typeof prevIndex !== 'object') {
    return { ok: true, violations: [] }
  }

  const violations = []
  const prevByRegistry = new Map((prevIndex.shards ?? []).map((s) => [s.registry, s.count]))
  const currByRegistry = new Map((currIndex.shards ?? []).map((s) => [s.registry, s.count]))

  for (const [registry, prevCount] of prevByRegistry) {
    if (!(prevCount > 0)) continue // 前回時点で既に 0 件だったレジストリは急減判定の対象外
    const currCount = currByRegistry.get(registry)
    if (currCount === undefined) {
      violations.push(`registry "${registry}" が shards[] から消失しました（前回 ${prevCount} 件）`)
      continue
    }
    if (currCount === 0) {
      violations.push(`registry "${registry}" が 0 件になりました（前回 ${prevCount} 件）`)
      continue
    }
    const ratio = currCount / prevCount
    if (ratio < REGISTRY_MIN_RATIO) {
      violations.push(
        `registry "${registry}" が ${prevCount} → ${currCount} 件に急減しました（比率 ${ratio.toFixed(3)} < ${REGISTRY_MIN_RATIO}）`,
      )
    }
  }

  const prevTotal = Number(prevIndex.totalCount)
  const currTotal = Number(currIndex.totalCount)
  if (Number.isFinite(prevTotal) && prevTotal > 0 && Number.isFinite(currTotal)) {
    const ratio = currTotal / prevTotal
    if (ratio < TOTAL_MIN_RATIO || ratio > TOTAL_MAX_RATIO) {
      violations.push(
        `totalCount が ${prevTotal} → ${currTotal} に変化しました（比率 ${ratio.toFixed(3)} は許容範囲 [${TOTAL_MIN_RATIO}, ${TOTAL_MAX_RATIO}] 外）`,
      )
    }
  }

  return { ok: violations.length === 0, violations }
}

/**
 * 前回・今回の `index.json` を突き合わせ、PR 本文用の比較データ（前回比・レジストリ別件数）を作る。
 *
 * 🔴 これは合否判定（`checkRegistryCounts`）とは別の関数にする。判定に通っても報告用の
 * スナップショットは必要（PR 本文が「差分ゼロの無意味な値」を貼らないための唯一の情報源に
 * なる。コミット後に再計算すると HEAD が新コミットを指してしまい前回比が消えるため、
 * 呼び出し側はこの結果を生成直後・コミット前に 1 回だけファイルへ保存して使い回すこと）。
 *
 * @param {{totalCount:number, shards:{registry:string, count:number}[]}|null} prevIndex
 * @param {{totalCount:number, shards:{registry:string, count:number}[]}} currIndex
 * @returns {{totalCount: {prev: number|null, curr: number|null, ratio: number|null}, registries: {registry:string, prevCount: number|null, currCount: number|null}[]}}
 */
export function buildComparison(prevIndex, currIndex) {
  const prevByRegistry = new Map((prevIndex?.shards ?? []).map((s) => [s.registry, s.count]))
  const currByRegistry = new Map((currIndex?.shards ?? []).map((s) => [s.registry, s.count]))
  const allRegistries = new Set([...prevByRegistry.keys(), ...currByRegistry.keys()])
  const registries = [...allRegistries].sort().map((registry) => ({
    registry,
    prevCount: prevByRegistry.has(registry) ? prevByRegistry.get(registry) : null,
    currCount: currByRegistry.has(registry) ? currByRegistry.get(registry) : null,
  }))

  const prevTotal =
    prevIndex && Number.isFinite(Number(prevIndex.totalCount)) ? Number(prevIndex.totalCount) : null
  const currTotal = Number.isFinite(Number(currIndex?.totalCount)) ? Number(currIndex.totalCount) : null
  const ratio = prevTotal !== null && prevTotal > 0 && currTotal !== null ? currTotal / prevTotal : null

  return { totalCount: { prev: prevTotal, curr: currTotal, ratio }, registries }
}

/**
 * `--check` の全検査を統合する。`comparison` は合否に関わらず常に含める（PR 本文用のスナップショット）。
 *
 * @param {{changedPaths: string[], prevIndex: object|null, currIndex: object}} input
 * @returns {{ok: boolean, diffScope: object, registryCounts: object, comparison: object}}
 */
export function runCheck({ changedPaths, prevIndex, currIndex }) {
  const diffScope = checkDiffScope(changedPaths)
  const registryCounts = checkRegistryCounts(prevIndex, currIndex)
  const comparison = buildComparison(prevIndex, currIndex)
  return { ok: diffScope.ok && registryCounts.ok, diffScope, registryCounts, comparison }
}

/**
 * JSON ドキュメントから `meta.generatedAt` / `date` を正規化する（no-op 判定用）。
 * 元オブジェクトは変更しない（immutable）。
 *
 * @param {object|null} doc
 * @returns {object|null}
 */
export function normalizeForDiff(doc) {
  if (!doc || typeof doc !== 'object') return doc
  const clone = structuredClone(doc)
  if (clone.meta && typeof clone.meta === 'object' && 'generatedAt' in clone.meta) {
    clone.meta.generatedAt = 'NORMALIZED'
  }
  if ('date' in clone) {
    clone.date = 'NORMALIZED'
  }
  return clone
}

/**
 * 正規化後の内容が完全一致するかを比較する（決定論的な JSON なので構造比較で足りる）。
 *
 * @param {object|null} prevDoc HEAD 版（存在しなければ null＝新規ファイル＝実差分扱い）
 * @param {object} currDoc 今回のドキュメント
 * @returns {boolean} 実質差分なしなら true
 */
export function docsEqualIgnoringTimestamps(prevDoc, currDoc) {
  if (prevDoc === null || prevDoc === undefined) return false // 新規ファイル＝実差分
  return JSON.stringify(normalizeForDiff(prevDoc)) === JSON.stringify(normalizeForDiff(currDoc))
}

/**
 * 複数ファイル分の no-op 判定を集約する。
 *
 * @param {{path: string, prevDoc: object|null, currDoc: object}[]} files
 * @returns {{noOp: boolean, changedFiles: string[]}}
 */
export function evaluateNoOp(files) {
  const changedFiles = (files ?? [])
    .filter((f) => !docsEqualIgnoringTimestamps(f.prevDoc, f.currDoc))
    .map((f) => f.path)
  return { noOp: changedFiles.length === 0, changedFiles }
}

// ============================================================
// I/O ヘルパー（git show / ファイル読み込み）
// ============================================================

/** `git show HEAD:<path>` の内容を JSON として読む。存在しなければ null。 */
function readHeadJson(relPath) {
  try {
    const text = execFileSync('git', ['show', `HEAD:${relPath}`], {
      cwd: REPO_ROOT,
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore'],
    })
    return JSON.parse(text)
  } catch {
    return null // 新規ファイル、または HEAD に存在しない
  }
}

/** 作業ツリーの JSON を読む。存在しなければ null。 */
function readWorktreeJson(relPath) {
  try {
    return JSON.parse(readFileSync(resolve(REPO_ROOT, relPath), 'utf8'))
  } catch {
    return null
  }
}

/** `git diff --name-only`（作業ツリー変更） + 未追跡ファイルの一覧を取得する。 */
function listChangedPaths() {
  const tracked = execFileSync('git', ['diff', '--name-only'], {
    cwd: REPO_ROOT,
    encoding: 'utf8',
  })
    .split('\n')
    .filter((l) => l.trim().length > 0)
  const untracked = execFileSync(
    'git',
    ['ls-files', '--others', '--exclude-standard'],
    { cwd: REPO_ROOT, encoding: 'utf8' },
  )
    .split('\n')
    .filter((l) => l.trim().length > 0)
  return [...tracked, ...untracked]
}

/** すべてのシャードファイル名（今回の index.json の shards[].fileName）を列挙する。 */
function listShardFileNames(index) {
  return (index?.shards ?? []).map((s) => s.fileName).filter((f) => typeof f === 'string')
}

// ============================================================
// JST 表示ヘルパー（datetime-rules.md 準拠。人間向け表示のみ・機械処理は UTC のまま扱う）
// ============================================================

function nowJstLabel() {
  const fmt = new Intl.DateTimeFormat('sv-SE', {
    timeZone: 'Asia/Tokyo',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date())
  return `${fmt.replace(' ', ' ')} JST`
}

// ============================================================
// モード実装
// ============================================================

function runCheckMode({ json }) {
  const currIndex = readWorktreeJson(INDEX_PATH)
  if (!currIndex) {
    // 生成物が無い＝ generate_gem_digest.mjs 側が既に失敗している状態のはず。
    // QA としても検査対象が無いので違反として扱う（fail-closed）。
    const result = {
      ok: false,
      reason: `${INDEX_PATH} が見つかりません（生成が完走していない可能性があります）`,
      checkedAt: nowJstLabel(),
    }
    printResult(result, json)
    process.exit(1)
  }

  const prevIndex = readHeadJson(INDEX_PATH)
  const changedPaths = listChangedPaths()
  const result = {
    ...runCheck({ changedPaths, prevIndex, currIndex }),
    checkedAt: nowJstLabel(),
  }
  printResult(result, json)
  process.exit(result.ok ? 0 : 1)
}

function runNoOpMode({ json }) {
  const currIndex = readWorktreeJson(INDEX_PATH)
  const currDigest = readWorktreeJson(DIGEST_PATH)
  if (!currIndex || !currDigest) {
    const result = {
      no_op: false,
      reason: '生成物（index.json / daily-digest.json）が見つかりません',
      checkedAt: nowJstLabel(),
    }
    printResult(result, json)
    process.exit(0) // no-op 判定モード自体は失敗ではないので exit 0（判定は呼び出し側が読む）
  }

  const prevIndex = readHeadJson(INDEX_PATH)
  const prevDigest = readHeadJson(DIGEST_PATH)

  const evaluation = evaluateNoOp([
    { path: INDEX_PATH, prevDoc: prevIndex, currDoc: currIndex },
    { path: DIGEST_PATH, prevDoc: prevDigest, currDoc: currDigest },
  ])

  const result = {
    no_op: evaluation.noOp,
    changedFiles: evaluation.changedFiles,
    checkedAt: nowJstLabel(),
  }
  printResult(result, json)
  process.exit(0)
}

function printResult(result, json) {
  if (json) {
    process.stdout.write(`${JSON.stringify(result)}\n`)
    return
  }
  if ('no_op' in result) {
    if (result.no_op) {
      console.log(`no-op: 実質差分なし（${result.checkedAt}）`)
    } else {
      console.log(`差分あり: ${(result.changedFiles ?? []).join(', ')}（${result.checkedAt}）`)
    }
    return
  }
  if (result.ok) {
    console.log(`PASS: Gem 候補プール QA（${result.checkedAt}）`)
    return
  }
  console.log(`FAIL: Gem 候補プール QA（${result.checkedAt}）`)
  if (result.reason) console.log(`  - ${result.reason}`)
  for (const p of result.diffScope?.offending ?? []) {
    console.log(`  - 許可外パスの差分: ${p}`)
  }
  for (const v of result.registryCounts?.violations ?? []) {
    console.log(`  - ${v}`)
  }
}

// ============================================================
// self-test（ネットワーク・実データ非依存）
// ============================================================

function selfTest() {
  const failures = []
  const assert = (label, cond) => {
    if (!cond) failures.push(label)
  }

  // --- checkDiffScope ---
  assert(
    'checkDiffScope: 許可パスのみなら ok',
    checkDiffScope([`${SHARD_DIR}/npmjs-org.json`, DIGEST_PATH, `${SHARD_DIR}/index.json`]).ok === true,
  )
  assert(
    'checkDiffScope: 許可外パスがあれば ok=false',
    checkDiffScope([`${SHARD_DIR}/index.json`, 'tools/generate_gem_digest.mjs']).ok === false,
  )
  assert('checkDiffScope: 空配列は ok', checkDiffScope([]).ok === true)
  assert(
    'checkDiffScope: 空文字列を含んでも無視される',
    checkDiffScope(['', `${SHARD_DIR}/a.json`]).ok === true,
  )

  // --- checkRegistryCounts ---
  assert(
    'checkRegistryCounts: prevIndex が null なら PASS（初回実行）',
    checkRegistryCounts(null, { totalCount: 100, shards: [{ registry: 'npmjs.org', count: 100 }] }).ok === true,
  )
  {
    const prev = {
      totalCount: 1000,
      shards: [
        { registry: 'npmjs.org', count: 600 },
        { registry: 'rubygems.org', count: 400 },
      ],
    }
    const currOk = {
      totalCount: 980,
      shards: [
        { registry: 'npmjs.org', count: 590 },
        { registry: 'rubygems.org', count: 390 },
      ],
    }
    assert('checkRegistryCounts: 軽微な増減は PASS', checkRegistryCounts(prev, currOk).ok === true)

    const currZero = {
      totalCount: 600,
      shards: [{ registry: 'npmjs.org', count: 600 }],
    }
    const zeroResult = checkRegistryCounts(prev, currZero)
    assert('checkRegistryCounts: レジストリ消失は violation', zeroResult.ok === false)
    assert(
      'checkRegistryCounts: 消失メッセージに registry 名を含む',
      zeroResult.violations.some((v) => v.includes('rubygems.org')),
    )

    const currRegistryDrop = {
      totalCount: 750,
      shards: [
        { registry: 'npmjs.org', count: 600 },
        { registry: 'rubygems.org', count: 150 }, // 400 → 150 = 62.5%減 > 30%
      ],
    }
    const dropResult = checkRegistryCounts(prev, currRegistryDrop)
    assert('checkRegistryCounts: 30% 超の急減は violation', dropResult.ok === false)

    const currTotalSpike = {
      totalCount: 1300, // 1000 → 1300 = 比率 1.3 > 1.15
      shards: [
        { registry: 'npmjs.org', count: 750 },
        { registry: 'rubygems.org', count: 550 },
      ],
    }
    const spikeResult = checkRegistryCounts(prev, currTotalSpike)
    assert('checkRegistryCounts: 全体急増は violation', spikeResult.ok === false)

    const currRegistryZeroCount = {
      totalCount: 600,
      shards: [
        { registry: 'npmjs.org', count: 600 },
        { registry: 'rubygems.org', count: 0 },
      ],
    }
    assert(
      'checkRegistryCounts: count===0（配列には残るがゼロ）も violation',
      checkRegistryCounts(prev, currRegistryZeroCount).ok === false,
    )

    const prevWithZero = {
      totalCount: 600,
      shards: [
        { registry: 'npmjs.org', count: 600 },
        { registry: 'gone.org', count: 0 },
      ],
    }
    assert(
      'checkRegistryCounts: 前回時点で既に 0 件だったレジストリの消失は対象外',
      checkRegistryCounts(prevWithZero, { totalCount: 600, shards: [{ registry: 'npmjs.org', count: 600 }] }).ok ===
        true,
    )
  }

  // --- buildComparison ---
  {
    const prev = {
      totalCount: 1000,
      shards: [
        { registry: 'npmjs.org', count: 600 },
        { registry: 'rubygems.org', count: 400 },
      ],
    }
    const curr = {
      totalCount: 950,
      shards: [
        { registry: 'npmjs.org', count: 600 },
        { registry: 'crates.io', count: 350 },
      ],
    }
    const cmp = buildComparison(prev, curr)
    assert('buildComparison: totalCount.prev/curr が入る', cmp.totalCount.prev === 1000 && cmp.totalCount.curr === 950)
    assert('buildComparison: ratio が計算される', Math.abs(cmp.totalCount.ratio - 0.95) < 1e-9)
    assert(
      'buildComparison: 消失レジストリは currCount=null',
      cmp.registries.find((r) => r.registry === 'rubygems.org')?.currCount === null,
    )
    assert(
      'buildComparison: 新規レジストリは prevCount=null',
      cmp.registries.find((r) => r.registry === 'crates.io')?.prevCount === null,
    )
    assert(
      'buildComparison: registries はレジストリ名昇順',
      cmp.registries.map((r) => r.registry).join(',') === 'crates.io,npmjs.org,rubygems.org',
    )

    const cmpFirstRun = buildComparison(null, curr)
    assert('buildComparison: 初回実行（prevIndex=null）は totalCount.prev/ratio が null', cmpFirstRun.totalCount.prev === null && cmpFirstRun.totalCount.ratio === null)
  }

  // --- runCheck 統合 ---
  {
    const prevIndex = { totalCount: 100, shards: [{ registry: 'npmjs.org', count: 100 }] }
    const currIndex = { totalCount: 98, shards: [{ registry: 'npmjs.org', count: 98 }] }
    const ok = runCheck({
      changedPaths: [`${SHARD_DIR}/npmjs-org.json`, `${SHARD_DIR}/index.json`],
      prevIndex,
      currIndex,
    })
    assert('runCheck: 正常系は ok', ok.ok === true)

    const bad = runCheck({
      changedPaths: [`${SHARD_DIR}/index.json`, 'README.md'],
      prevIndex,
      currIndex,
    })
    assert('runCheck: 許可外パスがあれば ok=false', bad.ok === false)
  }

  // --- normalizeForDiff / docsEqualIgnoringTimestamps ---
  {
    const a = { meta: { generatedAt: '2026-08-22T06:00:00.000Z', source: 'x' }, totalCount: 5 }
    const b = { meta: { generatedAt: '2026-08-29T06:00:00.000Z', source: 'x' }, totalCount: 5 }
    assert(
      'docsEqualIgnoringTimestamps: generatedAt だけ違えば同一扱い',
      docsEqualIgnoringTimestamps(a, b) === true,
    )
    assert('normalizeForDiff: 元オブジェクトを変更しない', a.meta.generatedAt === '2026-08-22T06:00:00.000Z')

    const c = { date: '20260822', meta: { generatedAt: 'x' }, candidates: [1, 2] }
    const d = { date: '20260829', meta: { generatedAt: 'y' }, candidates: [1, 2] }
    assert('docsEqualIgnoringTimestamps: date だけ違えば同一扱い（digest）', docsEqualIgnoringTimestamps(c, d) === true)

    const e = { date: '20260829', meta: { generatedAt: 'y' }, candidates: [1, 2, 3] }
    assert('docsEqualIgnoringTimestamps: candidates が違えば実差分', docsEqualIgnoringTimestamps(c, e) === false)

    assert('docsEqualIgnoringTimestamps: prevDoc が null なら実差分（新規ファイル）', docsEqualIgnoringTimestamps(null, c) === false)
  }

  // --- evaluateNoOp ---
  {
    const files = [
      {
        path: INDEX_PATH,
        prevDoc: { meta: { generatedAt: 'a' }, totalCount: 5 },
        currDoc: { meta: { generatedAt: 'b' }, totalCount: 5 },
      },
      {
        path: DIGEST_PATH,
        prevDoc: { date: '20260822', meta: { generatedAt: 'a' }, candidates: [] },
        currDoc: { date: '20260829', meta: { generatedAt: 'b' }, candidates: [] },
      },
    ]
    const evalOk = evaluateNoOp(files)
    assert('evaluateNoOp: 両方 timestamp だけ違えば no_op=true', evalOk.noOp === true)

    files[1].currDoc.candidates = [{ x: 1 }]
    const evalChanged = evaluateNoOp(files)
    assert('evaluateNoOp: 片方に実差分があれば no_op=false', evalChanged.noOp === false)
    assert(
      'evaluateNoOp: changedFiles に対象パスが載る',
      evalChanged.changedFiles.includes(DIGEST_PATH) && !evalChanged.changedFiles.includes(INDEX_PATH),
    )
  }

  // --- listShardFileNames（純関数として export はしていないが、内部ロジックの健全性を index 経由で確認） ---
  assert(
    'listShardFileNames 相当: shards[].fileName を列挙できる',
    listShardFileNames({ shards: [{ fileName: 'a.json' }, { fileName: 'b.json' }] }).join(',') === 'a.json,b.json',
  )

  if (failures.length > 0) {
    console.error(`FAIL: gem_pool_qa.mjs --self-test（${failures.length} 件失敗）`)
    for (const f of failures) console.error(`  - ${f}`)
    process.exit(1)
  }
  console.log(`PASS: gem_pool_qa.mjs --self-test（${nowJstLabel()}）`)
  process.exit(0)
}

// ============================================================
// CLI エントリポイント
// ============================================================

function main() {
  const argv = process.argv.slice(2)
  const json = argv.includes('--json')

  if (argv.includes('--self-test')) {
    selfTest()
    return
  }
  if (argv.includes('--check')) {
    runCheckMode({ json })
    return
  }
  if (argv.includes('--no-op')) {
    runNoOpMode({ json })
    return
  }

  console.error('使い方: node tools/gem_pool_qa.mjs [--check|--no-op|--self-test] [--json]')
  process.exit(2)
}

const isMain =
  typeof process.argv[1] === 'string' && resolve(process.argv[1]) === resolve(fileURLToPath(import.meta.url))
if (isMain) {
  main()
}
