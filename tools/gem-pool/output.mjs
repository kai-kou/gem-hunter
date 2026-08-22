/**
 * output.mjs — Gem 候補プールの **配信形（生成物）** を組み立てるモジュール（`SP-17` / Issue #387）。
 *
 * 責務は 2 つだけ:
 *   1. `pipeline.buildPool()` が返した `RankedRecord[]` を、配信する JSON ドキュメントへ整形する（純粋関数）
 *   2. そのドキュメントをファイルへ書き出す（薄い fs ラッパー・`writeJsonFile`）
 *
 * 収集（`collect.mjs`）・順位付け（`pipeline.mjs`）は持たない。ここが純粋関数に寄っているのは、
 * 10 分級のネットワーク実行なしに「生成物の形」を単体テストできるようにするため。
 *
 * 生成物は 2 系統ある:
 *   - **レジストリ別シャード**（`public/data/gem-index/{slug}.json`）: #388 が isolate の cold start で
 *     並列取得してメモリへ載せる配信データ（`D-38`）。キー名の反復を消すためタプル形式にする
 *   - **今日の Gem の候補プール**（`public/data/daily-digest.json`）: 既存のトップページが読む形
 *     （`src/infrastructure/platform/static-gem-digest.ts`）。shape は変えず `registry` だけ足す（`D-36`）
 */

import { mkdir, writeFile } from 'node:fs/promises'
import { dirname } from 'node:path'

import { REGISTRIES, registryFileSlug } from './registries.mjs'

/**
 * シャードの `entries` タプルの列定義（#388 との契約）。
 *
 * 読む側が位置に依存しなくてよいよう、シャード JSON にも `columns` として同梱する。
 */
export const SHARD_COLUMNS = Object.freeze([
  'repositoryFullName',
  'packageName',
  'dependentCount',
  'stars',
  'gemIndex',
])

/** 出典メタデータの固定部分（`D-29`・帰属表示は省略できない）。 */
const ATTRIBUTION = Object.freeze({
  source: 'Ecosyste.ms',
  sourceUrl: 'https://ecosyste.ms/',
  license: 'CC BY-SA 4.0',
  sourceLicenseUrl: 'https://creativecommons.org/licenses/by-sa/4.0/',
})

/** レジストリ名 → ecosystem の索引（`registries.mjs` が正本）。 */
const ECOSYSTEM_BY_REGISTRY = new Map(
  (Array.isArray(REGISTRIES) ? REGISTRIES : []).map((r) => [r?.name, r?.ecosystem ?? null]),
)

/**
 * 出典メタデータ（`D-29`）を作る。
 *
 * @param {Date|string|undefined} generatedAt 生成時刻（Date か ISO 8601 文字列）
 * @returns {{source:string, sourceUrl:string, license:string, sourceLicenseUrl:string, generatedAt:string}}
 */
export function buildMeta(generatedAt) {
  return { ...ATTRIBUTION, generatedAt: toIsoString(generatedAt) }
}

/**
 * レジストリ別シャード（#388 が消費する配信形式・`D-38`）を組み立てる。
 *
 * シャードの並びはレジストリ名の昇順、`entries` は `gemIndex` 昇順（同値は
 * `repositoryFullName` → `packageName`）で **入力順に依存しない決定論** にする。
 * 生成のたびに並びが揺れると、内容が同じでも git の差分が出て「更新されたのか」が読めなくなる。
 *
 * @param {ReadonlyArray<object>} records `buildPool()` の `records`
 * @param {object} meta `buildMeta()` の戻り値
 * @returns {{fileName:string, doc:object}[]}
 */
export function buildRegistryShards(records, meta) {
  /** @type {Map<string, object[]>} */
  const byRegistry = new Map()
  for (const record of records ?? []) {
    const registry = record?.registry
    if (typeof registry !== 'string' || registry.length === 0) continue
    const bucket = byRegistry.get(registry)
    if (bucket) bucket.push(record)
    else byRegistry.set(registry, [record])
  }

  return [...byRegistry.keys()]
    .sort(compareString)
    .map((registry) => ({
      fileName: `${registryFileSlug(registry)}.json`,
      doc: {
        registry,
        ecosystem: ECOSYSTEM_BY_REGISTRY.get(registry) ?? null,
        meta,
        columns: [...SHARD_COLUMNS],
        entries: sortRecords(byRegistry.get(registry)).map(toTuple),
      },
    }))
}

/**
 * 「今日の Gem」の候補プール（`public/data/daily-digest.json`）を組み立てる。
 *
 * 既存の shape（`date` / `meta` / `candidates`）を保つ。`StaticGemDigest` は未知フィールドを
 * 無視して読むので、`registry` の追加だけなら現行の読み手を壊さない（`D-36` の緊急除外用）。
 *
 * @param {ReadonlyArray<object>} records `buildPool()` の `records`
 * @param {object} meta `buildMeta()` の戻り値
 * @param {{date: Date|string, limit: number}} options
 */
export function buildDailyDigestDoc(records, meta, { date, limit } = {}) {
  const max = Number.isFinite(limit) && limit > 0 ? Math.floor(limit) : 0
  const candidates = sortRecords(records)
    .slice(0, max)
    .map((r) => ({
      packageName: r.packageName,
      repositoryFullName: r.repositoryFullName,
      dependentCount: r.dependentCount,
      stars: r.stars,
      gemIndex: r.gemIndex,
      registry: r.registry,
    }))

  return { date: toYyyymmdd(date), meta, candidates }
}

/**
 * 生成物のインデックス（#388 が「どのシャードがあるか」を知る入口）。
 *
 * @param {ReadonlyArray<{fileName:string, doc:object}>} shards
 * @param {object} meta
 * @param {object} [stats] `buildPool()` の `stats`（プレーンオブジェクトと数値だけの JSON 安全な値）
 */
export function buildShardIndex(shards, meta, stats) {
  const list = (shards ?? []).map(({ fileName, doc }) => ({
    registry: doc.registry,
    ecosystem: doc.ecosystem ?? null,
    fileName,
    count: doc.entries.length,
  }))

  return {
    meta,
    totalCount: list.reduce((sum, s) => sum + s.count, 0),
    shards: list,
    stats: stats ?? {},
  }
}

/**
 * 配信 JSON の直列化（**この形が生成物のバイト列の唯一の正本**）。
 *
 * 🔴 **dry-run のサイズ算出も必ずこれを使うこと（直列化を 2 箇所に持たない）。**
 * CLI 側が `JSON.stringify(...)` をコピーして持つと、整形を変えたときに `--dry-run` /
 * `--report` が報告するバイト数だけが実ファイルとずれ、嘘の実測が README / PR に残る。
 *
 * @param {unknown} doc 直列化するドキュメント
 * @param {{pretty?: boolean}} [options] `pretty: true` で 2 スペースインデント
 * @returns {string} 末尾に改行を 1 つ付けた JSON 文字列
 */
export function serializeJson(doc, { pretty = false } = {}) {
  return JSON.stringify(doc, null, pretty ? 2 : 0) + '\n'
}

/**
 * JSON を 1 ファイルへ書き出す（親ディレクトリは自動作成・末尾に改行）。
 *
 * シャードは既定で **非整形**（`pretty: false`）にする。10 万件級ではインデントが転送量と
 * `JSON.parse` の CPU（`D-38` の論点）にそのまま乗るため。git 差分を読みたい小さな生成物
 * （`daily-digest.json` / `index.json` / レポート）だけ `pretty: true` で呼ぶ。
 *
 * @returns {Promise<{path:string, bytes:number}>} 書き込んだバイト数（実測サマリー用）
 */
export async function writeJsonFile(path, doc, { pretty = false } = {}) {
  const text = serializeJson(doc, { pretty })
  await mkdir(dirname(path), { recursive: true })
  await writeFile(path, text, 'utf8')
  return { path, bytes: Buffer.byteLength(text, 'utf8') }
}

/** `gemIndex` 昇順（同値は repo 名 → パッケージ名）で並べ替えたコピーを返す。 */
function sortRecords(records) {
  return [...(records ?? [])].sort(
    (a, b) =>
      a.gemIndex - b.gemIndex ||
      compareString(a.repositoryFullName, b.repositoryFullName) ||
      compareString(a.packageName, b.packageName),
  )
}

function compareString(a, b) {
  const left = String(a ?? '')
  const right = String(b ?? '')
  return left < right ? -1 : left > right ? 1 : 0
}

/** `SHARD_COLUMNS` の順に並べたタプルへ落とす。 */
function toTuple(record) {
  return [
    record.repositoryFullName,
    record.packageName,
    record.dependentCount,
    record.stars,
    record.gemIndex,
  ]
}

/** Date | ISO 文字列 → ISO 8601。読めない値のときは空文字（帰属表示自体は落とさない）。 */
function toIsoString(value) {
  const date = toDate(value)
  return date ? date.toISOString() : ''
}

/** Date | 'YYYYMMDD' | ISO 文字列 → UTC の `YYYYMMDD`。 */
function toYyyymmdd(value) {
  if (typeof value === 'string' && /^\d{8}$/.test(value)) return value
  const date = toDate(value)
  if (!date) return ''
  const y = date.getUTCFullYear()
  const m = String(date.getUTCMonth() + 1).padStart(2, '0')
  const d = String(date.getUTCDate()).padStart(2, '0')
  return `${y}${m}${d}`
}

function toDate(value) {
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value
  if (typeof value === 'string' && value.length > 0) {
    const parsed = new Date(value)
    return Number.isNaN(parsed.getTime()) ? null : parsed
  }
  return null
}
