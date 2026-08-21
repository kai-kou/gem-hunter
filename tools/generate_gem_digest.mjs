#!/usr/bin/env node
/**
 * generate_gem_digest.mjs — Ecosyste.ms REST API から Gem 候補プールを生成する CLI。
 *
 * ADR 0014 §2.2 / open-questions.md D-28 訂正注記に従い、Ecosyste.ms REST API の
 * `rankings` フィールド（各指標のパーセンタイル順位を Ecosyste.ms 側で日次計算済み・
 * 値域 0〜100・0 が最上位）を Gem Index の入力として信頼する。
 *
 * 使い方:
 *   node tools/generate_gem_digest.mjs                 # 既定: 50 件・public/data/daily-digest.json
 *   node tools/generate_gem_digest.mjs --limit 100
 *   node tools/generate_gem_digest.mjs --out /tmp/out.json
 *
 * 実行環境: Node 21+（ESM・fetch はグローバル）。
 * ⚠️ CI での自動実行はしない（cron は別レーン）。ここでは実行手段だけ用意する。
 */

import { writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { mkdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

const API_BASE = 'https://packages.ecosyste.ms/api/v1/registries/npmjs.org/packages'
const DEFAULT_LIMIT = 50
const DEFAULT_OUT = 'public/data/daily-digest.json'
const PER_PAGE = 100
const USER_AGENT = 'gem-hunter/0.1 (+https://github.com/kai-kou/gem-hunter)'

function parseArgs(argv) {
  const out = { limit: DEFAULT_LIMIT, out: DEFAULT_OUT }
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (a === '--limit') {
      const v = Number(argv[++i])
      if (!Number.isFinite(v) || v <= 0) {
        throw new Error(`--limit には正の整数を指定してください（受け取った値: ${argv[i]}）`)
      }
      out.limit = Math.floor(v)
    } else if (a === '--out') {
      out.out = argv[++i]
      if (!out.out) throw new Error('--out にパスを指定してください')
    } else if (a === '--help' || a === '-h') {
      console.log(
        'Usage: node tools/generate_gem_digest.mjs [--limit N] [--out path/to/daily-digest.json]',
      )
      process.exit(0)
    } else {
      throw new Error(`未知の引数: ${a}`)
    }
  }
  return out
}

/**
 * Ecosyste.ms から被依存数の多い順に候補を取得する。
 * 100 件ページングで limit を満たすまでめくる。
 */
async function fetchCandidates(limit) {
  const results = []
  let page = 1
  while (results.length < limit) {
    const url = new URL(API_BASE)
    url.searchParams.set('sort', 'dependent_packages_count')
    url.searchParams.set('order', 'desc')
    url.searchParams.set('per_page', String(PER_PAGE))
    url.searchParams.set('page', String(page))

    const res = await fetch(url, {
      headers: { 'user-agent': USER_AGENT, accept: 'application/json' },
    })
    if (!res.ok) {
      throw new Error(`Ecosyste.ms ${res.status} ${res.statusText} @ page=${page}`)
    }
    const body = await res.json()
    if (!Array.isArray(body) || body.length === 0) break
    results.push(...body)
    if (body.length < PER_PAGE) break
    page += 1
  }
  return results.slice(0, limit)
}

/**
 * 1 件のパッケージ生 JSON から Gem shape へ変換する。
 * repositoryFullName が解決できない（rankings が欠落・GitHub URL でない）ものは null で捨てる。
 */
function toGem(pkg) {
  const repo = extractGithubFullName(pkg?.repository_url)
  if (!repo) return null

  const rankings = pkg?.rankings
  if (!rankings || typeof rankings !== 'object') return null
  const depRank = numberOrNull(rankings.dependent_packages_count)
  const starRank = numberOrNull(rankings.stargazers_count)
  if (depRank === null || starRank === null) return null
  // 🔴 値域を検証してから採用する（`src/domain/model/gem-index.ts` の `assertRank` と同じ不変条件）。
  //    Ecosyste.ms が rankings の値域・向きを変えた場合、無検証だと壊れたスコアが静かに配信され続ける。
  //    .mjs から TS の `computeGemIndex` を import できないため同じ規則をここに写している
  //    （算出の一本化は別 Issue。ここでは「壊れた値を配信しない」ことを優先する）。
  if (depRank < 0 || depRank > 100 || starRank < 0 || starRank > 100) return null

  const dependentCount = numberOrNull(pkg.dependent_packages_count) ?? 0
  // 🔴 star 数はトップレベルではなく `repo_metadata.stargazers_count` にある（実測確認）。
  //    `pkg.stargazers_count` は存在しないため、参照すると全件 0 になり「star が少ない Gem」
  //    という表示自体が嘘になる（生成物を実データで検証して初めて分かる類の欠陥）。
  const stars = numberOrNull(pkg?.repo_metadata?.stargazers_count) ?? 0
  // ADR 0009 §2.1: Gem Index = 被依存数の順位 − star の順位（0 が最上位・値が小さいほど上位）
  const gemIndex = depRank - starRank

  return {
    packageName: String(pkg.name),
    repositoryFullName: repo,
    dependentCount,
    stars,
    gemIndex,
  }
}

function numberOrNull(v) {
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}

/** GitHub URL（https / git+https / git@github.com:）から owner/repo を抜き出す。 */
function extractGithubFullName(url) {
  if (typeof url !== 'string') return null
  const cleaned = url.replace(/^git\+/, '').replace(/\.git$/, '')
  const m =
    /^https?:\/\/github\.com\/([^/]+)\/([^/#?]+)/i.exec(cleaned) ||
    /^git@github\.com:([^/]+)\/([^/#?]+)/i.exec(cleaned)
  if (!m) return null
  return `${m[1]}/${m[2]}`
}

function yyyymmddUtc(now) {
  const y = now.getUTCFullYear()
  const mo = String(now.getUTCMonth() + 1).padStart(2, '0')
  const d = String(now.getUTCDate()).padStart(2, '0')
  return `${y}${mo}${d}`
}

async function main() {
  const args = parseArgs(process.argv.slice(2))
  const now = new Date()
  const raw = await fetchCandidates(args.limit)
  const candidates = raw.map(toGem).filter((g) => g !== null)

  const doc = {
    date: yyyymmddUtc(now),
    meta: {
      source: 'Ecosyste.ms',
      sourceUrl: 'https://ecosyste.ms/',
      license: 'CC BY-SA 4.0',
      sourceLicenseUrl: 'https://creativecommons.org/licenses/by-sa/4.0/',
      generatedAt: now.toISOString(),
    },
    candidates,
  }

  const here = dirname(fileURLToPath(import.meta.url))
  const outPath = resolve(here, '..', args.out)
  await mkdir(dirname(outPath), { recursive: true })
  await writeFile(outPath, JSON.stringify(doc, null, 2) + '\n', 'utf8')

  process.stdout.write(
    `[generate_gem_digest] wrote ${candidates.length} candidates → ${outPath}\n`,
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
