#!/usr/bin/env node
/**
 * generate_gem_digest.mjs — Gem 候補プール（`public/data/daily-digest.json` +
 * レジストリ別シャード `public/data/gem-index/*.json`）を生成する CLI（`SP-17`）。
 *
 * 収集（Ecosyste.ms REST API・`tools/gem-pool/collect.mjs`）・変換（正規化・汚染フィルタ・
 * 順位再計算・`tools/gem-pool/pipeline.mjs`）・出力（`tools/gem-pool/output.mjs`）を束ねる
 * 薄いオーケストレーションのみをここに置く（実装本体は各モジュールが持つ・`D-37`）。
 *
 * 使い方:
 *   node tools/generate_gem_digest.mjs                         # 既定: 全 12 レジストリ・quota 15000
 *   node tools/generate_gem_digest.mjs --registries npm,pypi   # 一部レジストリだけ
 *   node tools/generate_gem_digest.mjs --cache-dir .gem-cache  # 収集結果をレジストリ別 JSON に保存し再利用
 *   node tools/generate_gem_digest.mjs --digest-limit 500 --quota 20000
 *
 * 実行環境: Node 21+（ESM・fetch はグローバル）。
 * ⚠️ CI での自動実行はしない（cron は別レーン）。ここでは実行手段だけ用意する。
 * ⚠️ 12 レジストリ × quota 15000 件のフル収集は 10 分近くかかる（`--cache-dir` で再実行コストを下げる）。
 */

import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { collectRegistry } from './gem-pool/collect.mjs'
import { buildDailyDigest, buildShards, writeOutputs } from './gem-pool/output.mjs'
import { DEFAULT_ZERO_STAR_DEPENDENT_THRESHOLD, buildPool, poolStats } from './gem-pool/pipeline.mjs'
import { DEFAULT_PER_PAGE, DEFAULT_QUOTA, REGISTRIES, findRegistry } from './gem-pool/registries.mjs'

const DEFAULT_DIGEST_LIMIT = 300
const DEFAULT_OUT_DIR = 'public/data'

const HELP = `Usage: node tools/generate_gem_digest.mjs [options]

  --quota N                          レジストリあたりの取得件数（既定 ${DEFAULT_QUOTA}）
  --registries id,id,...             対象レジストリ（既定: 全 ${REGISTRIES.length} 件・${REGISTRIES.map((r) => r.id).join(',')}）
  --digest-limit N                   daily-digest.json に載せる件数（既定 ${DEFAULT_DIGEST_LIMIT}）
  --zero-star-dependent-threshold N  star=0 汚染判定の被依存数閾値（既定 ${DEFAULT_ZERO_STAR_DEPENDENT_THRESHOLD}）
  --out-dir path                     出力先ディレクトリ（既定 ${DEFAULT_OUT_DIR}）
  --no-shards                        レジストリ別シャード JSON を書かない（digest のみ）
  --cache-dir path                   収集結果をレジストリ別 JSON でキャッシュし、次回はそこから読む
  --help, -h                         このヘルプを表示
`

function parsePositiveInt(raw, flag) {
  const v = Number(raw)
  if (!Number.isFinite(v) || v <= 0) {
    throw new Error(`${flag} には正の整数を指定してください（受け取った値: ${raw}）`)
  }
  return Math.floor(v)
}

function parseArgs(argv) {
  const out = {
    quota: DEFAULT_QUOTA,
    registries: REGISTRIES,
    digestLimit: DEFAULT_DIGEST_LIMIT,
    zeroStarDependentThreshold: DEFAULT_ZERO_STAR_DEPENDENT_THRESHOLD,
    outDir: DEFAULT_OUT_DIR,
    writeShards: true,
    cacheDir: null,
  }

  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (a === '--quota') {
      out.quota = parsePositiveInt(argv[++i], '--quota')
    } else if (a === '--registries') {
      const ids = (argv[++i] ?? '').split(',').map((s) => s.trim()).filter(Boolean)
      if (ids.length === 0) throw new Error('--registries には 1 件以上のレジストリ id を指定してください')
      out.registries = ids.map(findRegistry)
    } else if (a === '--digest-limit') {
      out.digestLimit = parsePositiveInt(argv[++i], '--digest-limit')
    } else if (a === '--zero-star-dependent-threshold') {
      out.zeroStarDependentThreshold = parsePositiveInt(argv[++i], '--zero-star-dependent-threshold')
    } else if (a === '--out-dir') {
      out.outDir = argv[++i]
      if (!out.outDir) throw new Error('--out-dir にパスを指定してください')
    } else if (a === '--no-shards') {
      out.writeShards = false
    } else if (a === '--cache-dir') {
      out.cacheDir = argv[++i]
      if (!out.cacheDir) throw new Error('--cache-dir にパスを指定してください')
    } else if (a === '--help' || a === '-h') {
      console.log(HELP)
      process.exit(0)
    } else {
      throw new Error(`未知の引数: ${a}`)
    }
  }
  return out
}

async function readCache(cachePath) {
  try {
    return JSON.parse(await readFile(cachePath, 'utf8'))
  } catch (err) {
    if (err.code === 'ENOENT') return null
    throw err
  }
}

/**
 * `--cache-dir` があればレジストリ別にキャッシュを読み書きしながら収集する。
 * 10 分近くかかる収集を試行錯誤のたびに走らせないための退避経路（契約 §5）。
 */
async function collectWithCache({ registries, quota, perPage, cacheDir, requestTally }) {
  const collected = []
  for (const registry of registries) {
    const cachePath = cacheDir ? resolve(cacheDir, `${registry.id}.json`) : null
    const cached = cachePath ? await readCache(cachePath) : null

    if (cached !== null) {
      console.error(`[generate_gem_digest] cache hit: ${registry.id}（${cached.length} 件・収集スキップ）`)
      collected.push({ registry: registry.id, packages: cached })
      continue
    }

    const packages = await collectRegistry({
      registry,
      quota,
      perPage,
      onProgress: () => {
        requestTally.count += 1
      },
    })

    if (cachePath) {
      await mkdir(dirname(cachePath), { recursive: true })
      await writeFile(cachePath, JSON.stringify(packages), 'utf8')
    }
    collected.push({ registry: registry.id, packages })
  }
  return collected
}

function resolveOutDir(outDir) {
  const here = dirname(fileURLToPath(import.meta.url))
  return resolve(here, '..', outDir)
}

async function main() {
  const args = parseArgs(process.argv.slice(2))
  const startedAt = Date.now()
  const requestTally = { count: 0 }

  const collected = await collectWithCache({
    registries: args.registries,
    quota: args.quota,
    perPage: DEFAULT_PER_PAGE,
    cacheDir: args.cacheDir,
    requestTally,
  })

  const candidates = buildPool(collected, {
    zeroStarDependentThreshold: args.zeroStarDependentThreshold,
  })
  const stats = poolStats(candidates)

  const now = new Date()
  const shards = buildShards(candidates, { generatedAt: now.toISOString() })
  const digest = buildDailyDigest(candidates, { limit: args.digestLimit, now })

  const { written } = await writeOutputs({
    shards,
    digest,
    outDir: resolveOutDir(args.outDir),
    writeShards: args.writeShards,
  })

  const elapsedSec = ((Date.now() - startedAt) / 1000).toFixed(1)
  const byRegistryLine = Object.entries(stats.byRegistry)
    .map(([id, n]) => `${id}=${n}`)
    .join(' ')

  process.stdout.write(
    [
      `[generate_gem_digest] 実行時間: ${elapsedSec}s / リクエスト数: ${requestTally.count}`,
      `[generate_gem_digest] レジストリ別件数（プール採用後）: ${byRegistryLine}`,
      `[generate_gem_digest] 最終件数: ${stats.total}（star=0 の比率: ${(stats.starZeroRatio * 100).toFixed(1)}%）`,
      `[generate_gem_digest] wrote ${written.length} files: ${written.join(', ')}`,
      '',
    ].join('\n'),
  )
}

try {
  await main()
} catch (err) {
  process.stderr.write(
    `[generate_gem_digest] error: ${err instanceof Error ? err.message : String(err)}\n`,
  )
  process.exit(1)
}
