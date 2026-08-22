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
 *
 * 実行環境: Node 22+（ESM・fetch はグローバル）。
 * ⚠️ CI での自動実行はしない（更新は `D-28` どおり Cloudflare の外で回して git commit → デプロイ）。
 */

import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { collectAll } from './gem-pool/collect.mjs'
import {
  buildDailyDigestDoc,
  buildMeta,
  buildRegistryShards,
  buildShardIndex,
  writeJsonFile,
} from './gem-pool/output.mjs'
import { buildPool, projectPackage } from './gem-pool/pipeline.mjs'
import { REGISTRIES } from './gem-pool/registries.mjs'

/** レジストリごとの取得枠（`D-37` (1) の固定枠。母数比例枠は採らない）。 */
const DEFAULT_QUOTA = 15000
const DEFAULT_PER_PAGE = 1000
/** 汚染フィルタ: star 数がこれ未満のものは Gem 候補に載せない（`D-37` (2)）。 */
const DEFAULT_MIN_STARS = 1
/** 汚染フィルタ: 被依存数の「上位帯」をパーセンタイルで定義する（真の star=0 × 高被依存は repo 誤紐付けの疑い）。 */
const DEFAULT_HIGH_DEPENDENT_RANK = 10
const DEFAULT_DIGEST_LIMIT = 300
const DEFAULT_OUT_DIR = 'public/data/gem-index'
const DEFAULT_DIGEST_OUT = 'public/data/daily-digest.json'
/** #388 が「どのシャードがあるか」を知る入口。 */
const INDEX_FILE_NAME = 'index.json'
const TOP_ROWS = 20

const REPO_ROOT = resolve(fileURLToPath(import.meta.url), '..', '..')

const HELP = `Usage: node tools/generate_gem_digest.mjs [options]

Options:
  --quota N                 レジストリごとの取得枠（既定 ${DEFAULT_QUOTA}）
  --per-page N              1 リクエストあたりの件数（既定 ${DEFAULT_PER_PAGE}）
  --registries a,b,c        対象レジストリ名をカンマ区切りで指定（既定は全 ${REGISTRIES.length} 件）
  --min-stars N             汚染フィルタ: star 数の下限（既定 ${DEFAULT_MIN_STARS}）
  --high-dependent-rank N   汚染フィルタ: 被依存数の上位帯をパーセンタイルで定義（既定 ${DEFAULT_HIGH_DEPENDENT_RANK}）
  --digest-limit N          daily-digest.json に載せる件数（既定 ${DEFAULT_DIGEST_LIMIT}）
  --out-dir path            シャード出力先ディレクトリ（既定 ${DEFAULT_OUT_DIR}）
  --digest-out path         今日の Gem の候補プール出力先（既定 ${DEFAULT_DIGEST_OUT}）
  --report path             実行統計を JSON で書き出す
  --dry-run                 ファイルを書かず統計だけ出す
  -h, --help                このヘルプを表示する

対象レジストリ: ${REGISTRIES.map((r) => r.name).join(', ')}`

function parseArgs(argv) {
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
 * payload の形はモジュール側の実装詳細なので、**存在するフィールドだけを拾う**
 * （キー名を決め打ちすると、収集側の小さな変更で進捗表示だけが静かに壊れる）。
 */
function describeProgress(info) {
  if (!info || typeof info !== 'object') return ''
  const parts = []
  const registry = info.registry?.name ?? info.registry
  if (typeof registry === 'string') parts.push(registry)
  if (Number.isFinite(info.page)) parts.push(`page=${info.page}`)
  const count = firstFinite(info.fetchedCount, info.total, info.count, info.records?.length)
  if (count !== null) parts.push(`fetched=${count}`)
  if (Number.isFinite(info.requestCount)) parts.push(`requests=${info.requestCount}`)
  return parts.join(' ')
}

function firstFinite(...values) {
  for (const v of values) if (Number.isFinite(v)) return v
  return null
}

/** 半角前提の簡易テーブル（目視確認用・完了条件 2）。 */
function renderTable(headers, rows) {
  const widths = headers.map((h, i) =>
    Math.max(String(h).length, ...rows.map((r) => String(r[i] ?? '').length)),
  )
  const line = (cells) =>
    cells.map((c, i) => String(c ?? '').padEnd(widths[i])).join('  ').trimEnd()
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

async function main() {
  const args = parseArgs(process.argv.slice(2))
  const registries = args.registries ?? REGISTRIES
  const startedAt = Date.now()
  const now = new Date()

  progress(
    `収集開始: ${registries.length} レジストリ × 最大 ${args.quota} 件（per_page=${args.perPage}）`,
  )

  const collected = await collectAll({
    registries,
    quota: args.quota,
    perPage: args.perPage,
    fetchImpl: fetch,
    project: projectPackage,
    onPage: (info) => {
      const text = describeProgress(info)
      if (text) progress(`${text} (+${elapsedSec(startedAt)}s)`)
    },
    onRegistryDone: (info) => {
      const text = describeProgress(info)
      progress(`done ${text || '(registry)'} (+${elapsedSec(startedAt)}s)`)
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

  const { records, stats } = buildPool(collected.byRegistry, {
    minStars: args.minStars,
    highDependentRankPercentile: args.highDependentRank,
  })

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

  /** @type {{path:string, bytes:number}[]} */
  const outputs = []
  for (const shard of shards) {
    outputs.push(await emit(resolve(outDir, shard.fileName), shard.doc, args.dryRun, false))
  }
  outputs.push(await emit(resolve(outDir, INDEX_FILE_NAME), index, args.dryRun, true))
  outputs.push(await emit(digestOut, digest, args.dryRun, true))

  const durationMs = Date.now() - startedAt
  const summary = buildSummary({ args, registries, collected, records, stats, outputs, durationMs, meta })

  if (args.report) {
    // レポートは dry-run でも書く（実測を README / PR に貼るのが目的で、配信データではないため）。
    const reportPath = resolve(REPO_ROOT, args.report)
    await writeJsonFile(reportPath, summary, { pretty: true })
    progress(`レポートを書き出しました → ${reportPath}`)
  }

  process.stdout.write(renderSummary(summary, args) + '\n')
}

/** 1 ファイル書き出す（dry-run のときは書かずにサイズだけ測る）。 */
async function emit(path, doc, dryRun, pretty) {
  if (dryRun) {
    const bytes = Buffer.byteLength(JSON.stringify(doc, null, pretty ? 2 : 0) + '\n', 'utf8')
    return { path, bytes }
  }
  return writeJsonFile(path, doc, { pretty })
}

/** stdout サマリーと `--report` JSON の共通の中身。 */
function buildSummary({ args, registries, collected, records, stats, outputs, durationMs, meta }) {
  const byRegistry = new Map()
  for (const r of records) byRegistry.set(r.registry, (byRegistry.get(r.registry) ?? 0) + 1)

  return {
    generatedAt: meta.generatedAt,
    durationMs,
    dryRun: args.dryRun,
    options: {
      quota: args.quota,
      perPage: args.perPage,
      registries: registries.map((r) => r.name),
      minStars: args.minStars,
      highDependentRank: args.highDependentRank,
      digestLimit: args.digestLimit,
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
    // 形を決め打ちできないので `buildShardIndex` と同じ経路で JSON 化する。
    stats: buildShardIndex([], meta, stats).stats,
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
  lines.push(`実行時間: ${formatDuration(s.durationMs)}${s.dryRun ? '（dry-run: 書き込みなし）' : ''}`)
  lines.push(`総リクエスト数: ${s.requestCount ?? '(不明)'}`)
  lines.push(`総取得パッケージ数: ${s.fetchedCount ?? '(不明)'}`)
  lines.push(`プール件数: ${s.poolCount}（ユニーク repo: ${s.uniqueRepositoryCount}）`)
  if (s.failures.length > 0) {
    lines.push(`失敗レジストリ: ${s.failures.map((f) => f.registry).join(', ')}`)
  }

  lines.push('')
  lines.push(`出力ファイル: ${s.outputs.length} 件（合計 ${formatBytes(s.totalBytes)}）`)
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

  if (args.dryRun) lines.push('', '※ --dry-run のためファイルは書き込んでいません。')
  return lines.join('\n')
}

try {
  await main()
} catch (err) {
  process.stderr.write(
    `[generate_gem_digest] error: ${err instanceof Error ? err.message : String(err)}\n`,
  )
  process.exit(1)
}
