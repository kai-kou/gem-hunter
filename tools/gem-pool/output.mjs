/**
 * output.mjs — Gem 候補プールをシャード JSON / daily-digest.json へ変換・書き出す。
 *
 * SP-17 契約 §5。入力は role B（pipeline.mjs）の出力である GemCandidate[] のみを想定し、
 * 収集（役 A）・変換（役 B）には依存しない（このファイルのテストが他役のファイル未完成でも
 * 独立して通ることを優先している）。
 */
import { mkdir, writeFile } from 'node:fs/promises'
import { join, resolve } from 'node:path'

/** D-29: 帰属表示の固定メタデータ。既存 public/data/daily-digest.json と同一キー。 */
export function buildMeta(generatedAt) {
  return {
    source: 'Ecosyste.ms',
    sourceUrl: 'https://ecosyste.ms/',
    license: 'CC BY-SA 4.0',
    sourceLicenseUrl: 'https://creativecommons.org/licenses/by-sa/4.0/',
    generatedAt,
  }
}

// #388 が消費する配信契約。列の意味・順序を変えない（増やす場合は #388 側と合意してから）。
export const SHARD_COLUMNS = [
  'repositoryFullName',
  'packageName',
  'dependentCount',
  'stars',
  'gemIndex',
]

function toRow(candidate) {
  return [
    candidate.repositoryFullName,
    candidate.packageName,
    candidate.dependentCount,
    candidate.stars,
    candidate.gemIndex,
  ]
}

/**
 * レジストリ別にシャード分割する。
 * 🔴 シャードの並び順は registry id の昇順で固定する（実装判断）: output.mjs は
 * registries.mjs の REGISTRIES 順序を持たない（役割分担で依存させない・契約 §0）ため、
 * 入力 candidates の出現順に依存しない決定論的な並びとしてアルファベット順を採る。
 */
export function buildShards(candidates, { generatedAt }) {
  const meta = buildMeta(generatedAt)
  const byRegistry = new Map()
  for (const candidate of candidates) {
    if (!byRegistry.has(candidate.registry)) byRegistry.set(candidate.registry, [])
    byRegistry.get(candidate.registry).push(candidate)
  }

  return [...byRegistry.keys()].sort().map((registry) => {
    const rows = byRegistry
      .get(registry)
      .slice()
      .sort((a, b) => a.gemIndex - b.gemIndex)
      .map(toRow)
    return { registry, doc: { meta, columns: SHARD_COLUMNS, rows } }
  })
}

function yyyymmddUtc(now) {
  const y = now.getUTCFullYear()
  const mo = String(now.getUTCMonth() + 1).padStart(2, '0')
  const d = String(now.getUTCDate()).padStart(2, '0')
  return `${y}${mo}${d}`
}

/**
 * 既存 public/data/daily-digest.json と同一スキーマ（registry の追加のみ）。
 * gemIndex 昇順の上位 limit 件に絞る。
 */
export function buildDailyDigest(candidates, { limit = 300, now = new Date() } = {}) {
  const top = candidates
    .slice()
    .sort((a, b) => a.gemIndex - b.gemIndex)
    .slice(0, limit)
    .map((c) => ({
      registry: c.registry,
      packageName: c.packageName,
      repositoryFullName: c.repositoryFullName,
      dependentCount: c.dependentCount,
      stars: c.stars,
      gemIndex: c.gemIndex,
    }))

  return {
    date: yyyymmddUtc(now),
    meta: buildMeta(now.toISOString()),
    candidates: top,
  }
}

function toPrettyJson(doc) {
  return JSON.stringify(doc, null, 2) + '\n'
}

/**
 * 実ファイル書き出しはここだけ（役 C の他関数はすべて純関数）。
 * shard は `{outDir}/gem-index/{registry}.json`、digest は `{outDir}/daily-digest.json`。
 */
export async function writeOutputs({ shards, digest, outDir = 'public/data', writeShards = true }) {
  const written = []

  const digestPath = resolve(outDir, 'daily-digest.json')
  await mkdir(resolve(outDir), { recursive: true })
  await writeFile(digestPath, toPrettyJson(digest), 'utf8')
  written.push(digestPath)

  if (writeShards) {
    const shardDir = resolve(outDir, 'gem-index')
    await mkdir(shardDir, { recursive: true })
    for (const shard of shards) {
      const shardPath = join(shardDir, `${shard.registry}.json`)
      await writeFile(shardPath, toPrettyJson(shard.doc), 'utf8')
      written.push(shardPath)
    }
  }

  return { written }
}
