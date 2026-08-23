#!/usr/bin/env node
/**
 * generate_gem_digest.mjs — Ecosyste.ms の 12 レジストリから Gem 候補プールを生成する CLI（`SP-17` / Issue #387）。
 *
 * `D-36` / `D-37` / `D-38`（`docs/02_requirements/open-questions.md` が決定の正本）に従い、
 * npm 限定・上位数百件だった候補プールを **12 レジストリ・10 万リポジトリ級** へ刷新する。
 *
 * 処理の流れ（各段は `tools/gem-pool/` のモジュールが持ち、本 CLI は配線と報告だけを担う）:
 *   1. 収集   `collect.collectAll()`  — レジストリごとに被依存数降順で固定枠（既定 15,000 件）を取る（`D-37` (1)）
 *   2. 整形   `pipeline.projectPackage()` — 生 JSON → PoolRecord（DI で収集へ渡す）
 *   3. 順位   `pipeline.buildPool()`   — 汚染フィルタ + repo 単位 dedupe + レジストリ別順位（`D-37` (2)(3)）
 *   4. 出力   `output.*`               — レジストリ別シャード + 今日の Gem の候補プール（`D-38`）
 *
 * 使い方:
 *   node tools/generate_gem_digest.mjs                      # 既定（12 レジストリ・約 10 分）
 *   node tools/generate_gem_digest.mjs --dry-run            # 書き込まず統計だけ見る
 *   node tools/generate_gem_digest.mjs --registries npmjs.org,rubygems.org --quota 2000
 *                                                           # 部分実行（既定では配信データを書き換えない）
 *   node tools/generate_gem_digest.mjs --registries npmjs.org --allow-partial-write
 *                                                           # 部分実行で書き換える（孤児シャードは削除される）
 *
 * 実行環境: Node 22+（ESM・fetch はグローバル）。
 * ⚠️ 定期実行は GitHub Actions の日次スケジュール（`.github/workflows/gem-pool-refresh.yml`）が本 CLI を
 * 既定オプションで毎日呼び出す。`main` への反映（PR 作成）は生成物が 7 日以上前のときだけ行う（日次実行 + 週次反映・
 * `D-28` の「Cloudflare の外で回す」を Actions が担う。マージ頻度を抑えて git 履歴コストを避けるため）。
 * `--allow-partial-write` は孤児シャードを削除するため定期実行では使わない（手動の部分再実行専用）。
 */

import { readdir, rm } from 'node:fs/promises'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { DEFAULT_PER_PAGE, MAX_PER_PAGE, collectAll } from './gem-pool/collect.mjs'
import {
  buildDailyDigestDoc,
  buildMeta,
  buildRegistryShards,
  buildShardIndex,
  serializeJson,
  writeJsonFile,
} from './gem-pool/output.mjs'
import { buildPool, projectPackage } from './gem-pool/pipeline.mjs'
import { REGISTRIES } from './gem-pool/registries.mjs'

/** レジストリごとの取得枠（`D-37` (1) の固定枠。母数比例枠は採らない）。 */
export const DEFAULT_QUOTA = 15000
// `--per-page` の既定と上限は収集側（`collect.mjs`）が正本。CLI では再定義せず import する。
export { DEFAULT_PER_PAGE }
/**
 * 汚染フィルタ: star 数がこれ未満のものは Gem 候補に載せない（`D-37` (2)）。
 *
 * 🔴 **既定 5 は実測で決めた**（2026-08-22・12 レジストリ × 15,000 件 = 180,000 パッケージ）。
 * `D-37` の文言は「真の 0（`stars=0`）× 高被依存」を除外対象にしているが、**本プールは
 * 各レジストリの被依存数上位 15,000 件だけを集めた集合なので、全件が構造的に高被依存帯にある**。
 * 閾値をスイープして生成物の上位 20 件を目視した結果は次のとおり（`D-36` の失敗判定条件は
 * 「上位 20 件に `stars=0` の自動生成ミラー・repo 誤紐付けが 3 件以上混ざっていない」）:
 *
 * | 設定 | プール件数 | 上位 20 件の汚染 |
 * |---|---|---|
 * | `minStars=1` / 上位帯 10% | 88,981 | ❌ 5 件（`mdickysnara/aryacil` `Aylaistiani22/anakayam` `exoego/scalajs-test-helper` の star=0 spam と、`juven/git-demo` `rizkychi/discorudo` の repo 誤紐付け） |
 * | `minStars=1` / 全帯 | 76,454 | ❌ 3 件（`juven/git-demo` `rizkychi/discorudo` ほか） |
 * | `minStars=2` / 全帯 | 70,951 | ❌ 1 件（`rizkychi/discorudo`・被依存 1,817 で star 2） |
 * | `minStars=3` / 全帯 | 67,280 | ✅ 0 件（ただし観測されたノイズ帯（star ≤ 2）との余裕がない） |
 * | **`minStars=5` / 全帯（採用）** | **62,565** | ✅ 0 件 |
 *
 * `3` でも条件は満たすが、ノイズ帯の上端（star=2）との差が 1 しかなく日次再生成のぶれを吸収できない。
 * プール件数の差は 7% にとどまるため、余裕のある `5` を既定にする。閾値を変えるときは
 * `python3 tools/measure_gem_coverage.py` で被覆率を測り直して決定ログへ追記する（`D-37`）。
 */
export const DEFAULT_MIN_STARS = 5
/**
 * 汚染フィルタ: 被依存数の「上位帯」をパーセンタイルで定義する。
 * 既定 `100`（= 全帯）。上記のとおり本プールは全件が高被依存帯にあたるため、帯で絞ると
 * 低被依存側に残った spam（star=0 で被依存 2,000 級の npm パッケージ）を取りこぼす。
 */
export const DEFAULT_HIGH_DEPENDENT_RANK = 100
export const DEFAULT_DIGEST_LIMIT = 300
export const DEFAULT_OUT_DIR = 'public/data/gem-index'
export const DEFAULT_DIGEST_OUT = 'public/data/daily-digest.json'
/** #388 が「どのシャードがあるか」を知る入口。 */
const INDEX_FILE_NAME = 'index.json'
const TOP_ROWS = 20

const REPO_ROOT = resolve(fileURLToPath(import.meta.url), '..', '..')

const HELP = `Usage: node tools/generate_gem_digest.mjs [options]

Options:
  --quota N                 レジストリごとの取得枠（既定 ${DEFAULT_QUOTA}）
  --per-page N              1 リクエストあたりの件数（既定 ${DEFAULT_PER_PAGE} / 上限 ${MAX_PER_PAGE}）
  --registries a,b,c        対象レジストリ名をカンマ区切りで指定（既定は全 ${REGISTRIES.length} 件）
  --min-stars N             汚染フィルタ: star 数の下限（既定 ${DEFAULT_MIN_STARS}）
  --high-dependent-rank N   汚染フィルタ: 被依存数の上位帯をパーセンタイルで定義（既定 ${DEFAULT_HIGH_DEPENDENT_RANK}）
  --digest-limit N          daily-digest.json に載せる件数（既定 ${DEFAULT_DIGEST_LIMIT}）
  --out-dir path            シャード出力先ディレクトリ（既定 ${DEFAULT_OUT_DIR}）
  --digest-out path         今日の Gem の候補プール出力先（既定 ${DEFAULT_DIGEST_OUT}）
  --report path             実行統計を JSON で書き出す（部分実行でも書く）
  --allow-partial-write     部分実行（--registries 指定 / 収集失敗あり）でも配信データを書き換える
                            ※ 索引に載らない孤児シャードは削除される
  --dry-run                 ファイルを書かず統計だけ出す
  -h, --help                このヘルプを表示する

対象レジストリ: ${REGISTRIES.map((r) => r.name).join(', ')}`

/**
 * CLI 引数を解析する。**ここで組み立てた既定値が出荷値の正本**（README の表は `--help` の写し）。
 *
 * @param {string[]} argv `process.argv.slice(2)` 相当
 */
export function parseArgs(argv) {
  const out = {
    quota: DEFAULT_QUOTA,
    perPage: DEFAULT_PER_PAGE,
    registries: null,
    minStars: DEFAULT_MIN_STARS,
    highDependentRank: DEFAULT_HIGH_DEPENDENT_RANK,
    digestLimit: DEFAULT_DIGEST_LIMIT,
    outDir: DEFAULT_OUT_DIR,
    digestOut: DEFAULT_DIGEST_OUT,
    report: null,
    dryRun: false,
    allowPartialWrite: false,
  }

  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (a === '--quota') out.quota = positiveInt(a, argv[++i])
    else if (a === '--per-page') out.perPage = positiveInt(a, argv[++i])
    else if (a === '--min-stars') out.minStars = nonNegativeInt(a, argv[++i])
    else if (a === '--high-dependent-rank') out.highDependentRank = percentile(a, argv[++i])
    else if (a === '--digest-limit') out.digestLimit = positiveInt(a, argv[++i])
    else if (a === '--out-dir') out.outDir = requiredPath(a, argv[++i])
    else if (a === '--digest-out') out.digestOut = requiredPath(a, argv[++i])
    else if (a === '--report') out.report = requiredPath(a, argv[++i])
    else if (a === '--registries') out.registries = parseRegistryList(argv[++i])
    else if (a === '--dry-run') out.dryRun = true
    else if (a === '--allow-partial-write') out.allowPartialWrite = true
    else if (a === '--help' || a === '-h') {
      process.stdout.write(HELP + '\n')
      process.exit(0)
    } else throw new Error(`未知の引数: ${a}`)
  }
  return out
}

function positiveInt(flag, value) {
  const n = Number(value)
  if (!Number.isFinite(n) || n <= 0) {
    throw new Error(`${flag} には正の整数を指定してください（受け取った値: ${value}）`)
  }
  return Math.floor(n)
}

function nonNegativeInt(flag, value) {
  const n = Number(value)
  if (!Number.isFinite(n) || n < 0) {
    throw new Error(`${flag} には 0 以上の整数を指定してください（受け取った値: ${value}）`)
  }
  return Math.floor(n)
}

function percentile(flag, value) {
  const n = Number(value)
  if (!Number.isFinite(n) || n < 0 || n > 100) {
    throw new Error(`${flag} には 0〜100 の数値を指定してください（受け取った値: ${value}）`)
  }
  return n
}

function requiredPath(flag, value) {
  if (!value || value.startsWith('--')) throw new Error(`${flag} にパスを指定してください`)
  return value
}

/** `--registries` を検証して REGISTRIES の部分集合に解決する（緊急除外・部分再生成用・`D-36`）。 */
function parseRegistryList(value) {
  if (!value || value.startsWith('--')) {
    throw new Error('--registries にはレジストリ名をカンマ区切りで指定してください')
  }
  const names = value
    .split(',')
    .map((s) => s.trim())
    .filter((s) => s.length > 0)
  if (names.length === 0) {
    throw new Error('--registries にはレジストリ名を 1 つ以上指定してください')
  }
  const known = new Map(REGISTRIES.map((r) => [r.name, r]))
  const unknown = names.filter((n) => !known.has(n))
  if (unknown.length > 0) {
    throw new Error(
      `--registries に未知のレジストリが含まれています: ${unknown.join(', ')}（指定できるのは ${[...known.keys()].join(', ')}）`,
    )
  }
  // 重複指定は畳む（同じレジストリを 2 回収集しない）。
  return [...new Set(names)].map((n) => known.get(n))
}

/* ------------------------------------------------------------------ 純粋な判断ロジック */

/**
 * CLI 引数を `buildPool()` のオプションへ変換する。
 *
 * 🔴 **キー名 `highDependentRankPercentile` は `pipeline.buildPool()` の契約**。取り違えると
 * `buildPool` 側のモジュール既定（全帯ではない値）へ静かにフォールバックし、汚染が復活する。
 * 出荷値の固定はテスト（`generate_gem_digest.test.mjs`）が担う。
 *
 * @param {{minStars:number, highDependentRank:number}} args
 * @returns {{minStars:number, highDependentRankPercentile:number}}
 */
export function toBuildPoolOptions(args) {
  return {
    minStars: args.minStars,
    highDependentRankPercentile: args.highDependentRank,
  }
}

/**
 * 配信データ（シャード・`index.json`・`daily-digest.json`）を書き換えてよいかを判定する。
 *
 * **部分実行**（`--registries` で一部だけ指定した／収集に失敗したレジストリがある）で書き込むと、
 * `index.json` の `shards` が今回集めた分だけに置き換わり、**索引から消えたシャードが孤児として
 * ディスクに残る**（#388 は索引経由で読むためレジストリが消え、`measure_gem_coverage.py` は
 * ディレクトリ内の全 JSON を読むため被覆率が水増しされる）。よって既定では拒否する。
 *
 * @param {Object} args
 * @param {number} args.selectedRegistryCount 今回の対象レジストリ数
 * @param {number} args.totalRegistryCount    全レジストリ数（`REGISTRIES.length`）
 * @param {number} args.failureCount          収集に失敗したレジストリ数
 * @param {boolean} [args.allowPartialWrite]  `--allow-partial-write`
 * @param {boolean} [args.dryRun]             `--dry-run`
 * @returns {{partial:boolean, write:boolean, blocked:boolean, reason:string|null}}
 */
export function decideOutputWrite({
  selectedRegistryCount,
  totalRegistryCount,
  failureCount,
  allowPartialWrite = false,
  dryRun = false,
}) {
  const missing = Math.max(0, totalRegistryCount - selectedRegistryCount)
  const partial = missing > 0 || failureCount > 0

  if (dryRun) {
    return { partial, write: false, blocked: false, reason: 'dry-run のため書き込みません' }
  }
  if (!partial) return { partial: false, write: true, blocked: false, reason: null }
  if (allowPartialWrite) {
    return {
      partial: true,
      write: true,
      blocked: false,
      reason: '--allow-partial-write が指定されたため部分結果で書き込みます',
    }
  }

  const causes = []
  if (missing > 0) causes.push(`対象外レジストリ ${missing} 件（--registries 指定）`)
  if (failureCount > 0) causes.push(`収集失敗 ${failureCount} 件`)
  return {
    partial: true,
    write: false,
    blocked: true,
    reason:
      `全 ${totalRegistryCount} レジストリぶんが揃っていないため配信データを書き換えません` +
      `（${causes.join(' / ')}）。意図した部分更新なら --allow-partial-write を付けてください`,
  }
}

/**
 * 出力ディレクトリに残った **孤児シャード**（今回の索引に載らない `*.json`）を選ぶ。
 *
 * 索引とディスクの不一致を作らないための後始末。`index.json` 自身は常に残す。
 *
 * @param {ReadonlyArray<string>} existingFiles 出力ディレクトリのファイル名一覧
 * @param {ReadonlyArray<string>} keepFileNames 今回書き出したファイル名（索引を含む）
 * @returns {string[]} 削除対象のファイル名（名前順）
 */
export function selectOrphanShards(existingFiles, keepFileNames) {
  const keep = new Set(keepFileNames)
  return [...(existingFiles ?? [])]
    .filter((name) => name.endsWith('.json') && !keep.has(name))
    .sort()
}

/* ------------------------------------------------------------------ 進捗・整形 */

function progress(message) {
  process.stderr.write(`[gem-pool] ${message}\n`)
}

function warn(message) {
  process.stderr.write(`[gem-pool] warn: ${message}\n`)
}

/** 経過秒（小数 1 桁）。10 分級の実行なので「今どこまで来たか」を秒で出す。 */
function elapsedSec(startedAt) {
  return ((Date.now() - startedAt) / 1000).toFixed(1)
}

function formatDuration(ms) {
  const total = Math.round(ms / 1000)
  const m = Math.floor(total / 60)
  const s = total % 60
  return m > 0 ? `${m}m ${s}s` : `${s}s`
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`
  return `${(bytes / 1024 / 1024).toFixed(2)} MiB`
}

/**
 * `collectAll` のコールバック payload から人間が読める 1 行を作る。
 *
 * 🔵 **payload の契約の正本は `tools/gem-pool/collect.mjs`**（`onPage` は
 * `{registry, page, fetched, kept, elapsedMs}`・`onRegistryDone` は
 * `{registry, ok, kept, fetched, requestCount, message?}`）。キー名はここで決め打ちする
 * （推測で拾っても収集側の変更時に表示が静かに空へ縮退するだけで、防御にならない）。
 */
function describeProgress(info) {
  if (!info || typeof info !== 'object') return ''
  const parts = []
  if (typeof info.registry === 'string') parts.push(info.registry)
  if (Number.isFinite(info.page)) parts.push(`page=${info.page}`)
  if (Number.isFinite(info.fetched)) parts.push(`fetched=${info.fetched}`)
  if (Number.isFinite(info.kept)) parts.push(`kept=${info.kept}`)
  if (Number.isFinite(info.requestCount)) parts.push(`requests=${info.requestCount}`)
  return parts.join(' ')
}

/** 半角前提の簡易テーブル（目視確認用・完了条件 2）。 */
function renderTable(headers, rows) {
  const widths = headers.map((h, i) =>
    Math.max(String(h).length, ...rows.map((r) => String(r[i] ?? '').length)),
  )
  const line = (cells) =>
    cells
      .map((c, i) => String(c ?? '').padEnd(widths[i]))
      .join('  ')
      .trimEnd()
  return [line(headers), line(widths.map((w) => '-'.repeat(w))), ...rows.map(line)].join('\n')
}

/** `buildPool()` の stats を（形を決め打ちせずに）インデント付きで並べる。 */
function renderStats(stats, indent = '  ') {
  const lines = []
  for (const [key, value] of Object.entries(stats ?? {})) {
    if (value !== null && typeof value === 'object') {
      const entries = Object.entries(value)
      if (entries.length === 0) continue
      lines.push(`${indent}${key}:`)
      lines.push(renderStats(value, indent + '  '))
    } else {
      lines.push(`${indent}${key}: ${value}`)
    }
  }
  return lines.filter((l) => l.length > 0).join('\n')
}

/* ------------------------------------------------------------------ 本体 */

/**
 * CLI 本体。**テストから import しても走らないよう、実行はエントリポイント判定の下だけで行う**。
 *
 * @returns {Promise<number>} 終了コード（0 = 正常 / 1 = 配信データの書き込みを拒否した）
 */
export async function main() {
  const args = parseArgs(process.argv.slice(2))
  const registries = args.registries ?? REGISTRIES
  const startedAt = Date.now()
  const now = new Date()

  progress(
    `収集開始: ${registries.length} レジストリ × 最大 ${args.quota} 件（per_page=${args.perPage}）`,
  )

  // 10 分級の実行になるため、ページ単位で「どこまで来たか」を stderr に出し続ける（無出力にしない）。
  // 累計はコールバック payload に無い（ページ単位の件数しか来ない）ため、ここで積み上げる。
  let cumulative = 0
  const collected = await collectAll({
    registries,
    quota: args.quota,
    perPage: args.perPage,
    fetchImpl: fetch,
    project: projectPackage,
    onPage: (info) => {
      if (Number.isFinite(info?.kept)) cumulative += info.kept
      else if (Number.isFinite(info?.fetched)) cumulative += info.fetched
      const text = describeProgress(info)
      if (text) progress(`${text} total=${cumulative} (+${elapsedSec(startedAt)}s)`)
    },
    onRegistryDone: (info) => {
      const text = describeProgress(info)
      progress(`done ${text || '(registry)'} total=${cumulative} (+${elapsedSec(startedAt)}s)`)
    },
  })

  const failures = collected.failures ?? []
  for (const f of failures) {
    // 1 レジストリ落ちても配信は止めない（`NFR-8` と同じ思想）。全滅のときだけ下で非ゼロ終了する。
    warn(`レジストリ ${f?.registry ?? '(unknown)'} の収集に失敗しました: ${f?.message ?? ''}`)
  }
  if (failures.length >= registries.length) {
    throw new Error(
      `全 ${registries.length} レジストリの収集に失敗したため中止します（生成物は更新していません）`,
    )
  }

  progress(
    `収集完了: requests=${collected.requestCount} fetched=${collected.fetchedCount} (${formatDuration(Date.now() - startedAt)})`,
  )

  const { records, stats } = buildPool(collected.byRegistry, toBuildPoolOptions(args))

  if (records.length === 0) {
    throw new Error(
      '候補プールが 0 件になりました（フィルタ条件か収集結果を確認してください）。生成物は更新していません',
    )
  }
  progress(`プール構築完了: ${records.length} 件`)

  const meta = buildMeta(now)
  const shards = buildRegistryShards(records, meta)
  const index = buildShardIndex(shards, meta, stats)
  const digest = buildDailyDigestDoc(records, meta, { date: now, limit: args.digestLimit })

  const outDir = resolve(REPO_ROOT, args.outDir)
  const digestOut = resolve(REPO_ROOT, args.digestOut)

  // 部分収集の結果で配信物を壊さない（判定は純粋関数側・理由は必ず stderr に出す）。
  const decision = decideOutputWrite({
    selectedRegistryCount: registries.length,
    totalRegistryCount: REGISTRIES.length,
    failureCount: failures.length,
    allowPartialWrite: args.allowPartialWrite,
    dryRun: args.dryRun,
  })
  if (decision.blocked) warn(decision.reason)
  else if (decision.partial && decision.write) warn(decision.reason)

  /** @type {{path:string, bytes:number}[]} */
  const outputs = []
  for (const shard of shards) {
    outputs.push(await emit(resolve(outDir, shard.fileName), shard.doc, decision.write, false))
  }
  outputs.push(await emit(resolve(outDir, INDEX_FILE_NAME), index, decision.write, true))
  outputs.push(await emit(digestOut, digest, decision.write, true))

  // 索引に載らないシャードをディスクに残さない（レジストリ構成が変わったときの残留・部分更新の孤児）。
  const removedFiles = decision.write
    ? await removeOrphanShards(outDir, [...shards.map((s) => s.fileName), INDEX_FILE_NAME])
    : []
  for (const name of removedFiles) progress(`孤児シャードを削除しました: ${name}`)

  const durationMs = Date.now() - startedAt
  const summary = buildSummary({
    args,
    registries,
    collected,
    records,
    stats,
    outputs,
    durationMs,
    meta,
    decision,
    removedFiles,
  })

  if (args.report) {
    // レポートは dry-run / 書き込み拒否のときでも書く
    // （実測を README / PR に貼るのが目的で、配信データではないため）。
    const reportPath = resolve(REPO_ROOT, args.report)
    await writeJsonFile(reportPath, summary, { pretty: true })
    progress(`レポートを書き出しました → ${reportPath}`)
  }

  process.stdout.write(renderSummary(summary, args) + '\n')

  if (decision.blocked) {
    warn(decision.reason)
    return 1
  }
  return 0
}

/** 出力ディレクトリの孤児シャードを削除して、削除したファイル名を返す。 */
async function removeOrphanShards(outDir, keepFileNames) {
  /** @type {string[]} */
  let existing
  try {
    existing = await readdir(outDir)
  } catch (err) {
    if (err?.code === 'ENOENT') return []
    throw err
  }
  const orphans = selectOrphanShards(existing, keepFileNames)
  for (const name of orphans) await rm(resolve(outDir, name), { force: true })
  return orphans
}

/**
 * 1 ファイル書き出す（書かないときは `output.serializeJson` でサイズだけ測る）。
 *
 * サイズ算出は必ず `serializeJson` を通す（`writeJsonFile` と同じ直列化）。整形方法を
 * 文字列レベルでコピーすると、整形を変えたときに報告バイト数だけ実ファイルとずれて
 * 嘘の実測が README / PR に残る。
 */
async function emit(path, doc, write, pretty) {
  if (!write) {
    return { path, bytes: Buffer.byteLength(serializeJson(doc, { pretty }), 'utf8') }
  }
  return writeJsonFile(path, doc, { pretty })
}

/** stdout サマリーと `--report` JSON の共通の中身。 */
function buildSummary({
  args,
  registries,
  collected,
  records,
  stats,
  outputs,
  durationMs,
  meta,
  decision,
  removedFiles,
}) {
  const byRegistry = new Map()
  for (const r of records) byRegistry.set(r.registry, (byRegistry.get(r.registry) ?? 0) + 1)

  return {
    generatedAt: meta.generatedAt,
    durationMs,
    dryRun: args.dryRun,
    // 部分実行だったか / 実際に配信データを書いたか（実測レポートを後から読む人向け）。
    partial: decision.partial,
    wroteOutputs: decision.write,
    blocked: decision.blocked,
    writeDecisionReason: decision.reason,
    removedFiles: removedFiles ?? [],
    options: {
      quota: args.quota,
      perPage: args.perPage,
      registries: registries.map((r) => r.name),
      minStars: args.minStars,
      highDependentRank: args.highDependentRank,
      digestLimit: args.digestLimit,
      allowPartialWrite: args.allowPartialWrite,
    },
    requestCount: collected.requestCount ?? null,
    fetchedCount: collected.fetchedCount ?? null,
    poolCount: records.length,
    uniqueRepositoryCount: new Set(records.map((r) => r.repositoryFullName)).size,
    failures: (collected.failures ?? []).map((f) => ({
      registry: f?.registry ?? null,
      message: f?.message ?? null,
    })),
    byRegistry: [...byRegistry.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([registry, count]) => ({
        registry,
        count,
        share: Number(((count / records.length) * 100).toFixed(2)),
      })),
    outputs: outputs.map((o) => ({ path: o.path, bytes: o.bytes })),
    totalBytes: outputs.reduce((sum, o) => sum + o.bytes, 0),
    // `buildPool` の `stats` はプレーンオブジェクトと数値だけ（`pipeline.mjs` の契約）なので
    // そのまま載せる。以前は `buildShardIndex([], meta, stats).stats` と空配列を渡して
    // 内部の JSON 変換だけを借りていたが、無関係な関数の実装変更で `--report` が壊れるため外した。
    stats: stats ?? {},
    top: records.slice(0, TOP_ROWS).map((r, i) => ({
      rank: i + 1,
      repositoryFullName: r.repositoryFullName,
      packageName: r.packageName,
      registry: r.registry,
      dependentCount: r.dependentCount,
      stars: r.stars,
      gemIndex: r.gemIndex,
    })),
  }
}

function renderSummary(s, args) {
  const lines = []
  lines.push('=== gem-pool 生成サマリー ===')
  lines.push(
    `実行時間: ${formatDuration(s.durationMs)}${s.dryRun ? '（dry-run: 書き込みなし）' : ''}`,
  )
  lines.push(`総リクエスト数: ${s.requestCount ?? '(不明)'}`)
  lines.push(`総取得パッケージ数: ${s.fetchedCount ?? '(不明)'}`)
  lines.push(`プール件数: ${s.poolCount}（ユニーク repo: ${s.uniqueRepositoryCount}）`)
  if (s.failures.length > 0) {
    lines.push(`失敗レジストリ: ${s.failures.map((f) => f.registry).join(', ')}`)
  }

  lines.push('')
  lines.push(
    `出力ファイル: ${s.outputs.length} 件（合計 ${formatBytes(s.totalBytes)}）` +
      (s.wroteOutputs ? '' : '（書き込みなし・サイズのみ算出）'),
  )
  lines.push(
    renderTable(
      ['file', 'bytes', 'size'],
      s.outputs.map((o) => [o.path.replace(REPO_ROOT + '/', ''), o.bytes, formatBytes(o.bytes)]),
    ),
  )

  lines.push('')
  lines.push('レジストリ別構成比:')
  lines.push(
    renderTable(
      ['registry', 'count', 'share'],
      s.byRegistry.map((r) => [r.registry, r.count, `${r.share}%`]),
    ),
  )

  const statsText = renderStats(s.stats)
  if (statsText) {
    lines.push('')
    lines.push('buildPool 統計（除外理由別件数を含む）:')
    lines.push(statsText)
  }

  lines.push('')
  lines.push(`Gem Index 上位 ${s.top.length} 件:`)
  lines.push(
    renderTable(
      ['#', 'repository', 'package', 'registry', 'dependents', 'stars', 'gemIndex'],
      s.top.map((t) => [
        t.rank,
        t.repositoryFullName,
        t.packageName,
        t.registry,
        t.dependentCount,
        t.stars,
        typeof t.gemIndex === 'number' ? t.gemIndex.toFixed(4) : t.gemIndex,
      ]),
    ),
  )

  if (s.removedFiles.length > 0) {
    lines.push('')
    lines.push(`孤児シャードを削除: ${s.removedFiles.length} 件`)
    for (const name of s.removedFiles) lines.push(`  - ${name}`)
  }

  if (args.dryRun) lines.push('', '※ --dry-run のためファイルは書き込んでいません。')
  else if (s.blocked) lines.push('', `※ ${s.writeDecisionReason}`)
  else if (s.partial) lines.push('', `※ ${s.writeDecisionReason}`)
  return lines.join('\n')
}

/** `node tools/generate_gem_digest.mjs` として起動されたときだけ実行する（import では走らせない）。 */
const isEntryPoint =
  typeof process.argv[1] === 'string' &&
  resolve(process.argv[1]) === resolve(fileURLToPath(import.meta.url))

if (isEntryPoint) {
  try {
    process.exit(await main())
  } catch (err) {
    process.stderr.write(
      `[generate_gem_digest] error: ${err instanceof Error ? err.message : String(err)}\n`,
    )
    process.exit(1)
  }
}
