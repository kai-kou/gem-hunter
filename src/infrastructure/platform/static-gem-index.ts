import { type GemIndex, gemIndex } from '../../domain/model/gem-index'
import type { GemIndexPort } from '../../domain/ports/gem-index-port'

import { type AssetReader, resolveAssetReader } from './asset-reader'

/**
 * Gem 候補プールのレジストリ別シャード（静的アセット）を読む `GemIndexPort` 実装（`SP-18` / `D-38`）。
 *
 * 🔴 **配信方式（`D-38` の決定）**: レジストリ別の静的 JSON（`public/data/gem-index/`）を
 * isolate の cold start で `Promise.all` により **並列取得** して単一 `Map` にマージし、
 * 以降は `Map.get()` で join する。D1 の `IN` クエリ・ハッシュ分割シャード・Range 二分探索・
 * バンドル焼き込みはいずれも却下済み（理由は `open-questions.md` `D-38`）。
 *
 * 🔵 **singleton promise パターン**: 構築中の Promise を **モジュールスコープ** に保持し、
 * cold start 直後に同一 isolate へ並行到達したリクエストは同じ Promise を await するだけにする。
 * これをしないと並行リクエストがそれぞれ 12 本ずつ取得を走らせる。
 * ⚠️ cold start は「デプロイ直後の 1 回」ではなく **isolate ごとに継続的に発生する**。
 *
 * 🔴 **初期化に失敗した Promise はキャッシュしない**。失敗を抱え込むと、デプロイ直後の一時障害で
 * その isolate の生存期間ずっとバッジが出なくなる。失敗時は次のリクエストで再試行する。
 *
 * 🔴 **例外を投げない**（`GemIndexPort` の契約 / `D-28` の SPOF 方針）。壊れた入力・取得失敗は
 * `console.warn` でログだけ残し、**読めた分だけ**で Map を作る（全滅なら空 Map）。
 */

/** シャード置き場（`public/data/gem-index/`）の絶対パス。 */
const GEM_INDEX_DIR = '/data/gem-index'
/** 入口。`shards[].fileName` に各レジストリのシャード名が並ぶ。 */
const INDEX_PATH = `${GEM_INDEX_DIR}/index.json`

/** シャードのタプル配列から引く列名（`columns` の位置は決め打ちしない）。 */
const COLUMN_REPOSITORY_FULL_NAME = 'repositoryFullName'
const COLUMN_GEM_INDEX = 'gemIndex'

/** 小文字化した `owner/repo` → Gem Index の生値。 */
type GemIndexPool = ReadonlyMap<string, number>

/** 構築結果。`ok=false` は「入口ごと読めなかった」＝ キャッシュしてはいけない失敗。 */
type PoolBuild = {
  readonly pool: GemIndexPool
  readonly ok: boolean
}

/**
 * モジュールスコープの singleton promise。isolate の生存期間だけ生き、リクエストをまたいで共有される。
 * 🔴 ここを instance フィールドにすると、リクエストごとに `Map` を作り直して `D-38` の前提が崩れる。
 */
let cachedPool: Promise<GemIndexPool> | undefined

/** テスト用: モジュールスコープの singleton promise を捨てる。 */
export function resetGemIndexCacheForTest(): void {
  cachedPool = undefined
}

export class StaticGemIndex implements GemIndexPort {
  /**
   * `AssetReader` を注入できるようにしておく（テスト用）。省略すると実行環境に応じた
   * reader（Workers Static Assets / ファイルシステム）を `resolveAssetReader()` が選ぶ。
   */
  constructor(private readonly reader?: AssetReader) {}

  async lookup(repositoryFullNames: readonly string[]): Promise<ReadonlyMap<string, GemIndex>> {
    const pool = await this.pool()
    const found = new Map<string, GemIndex>()
    if (pool.size === 0) {
      return found
    }

    for (const name of repositoryFullNames) {
      if (typeof name !== 'string' || name.length === 0) {
        continue
      }
      // 照合はプール側の正規化（小文字）に合わせる。返り値のキーは **入力の綴りのまま**。
      const value = pool.get(name.toLowerCase())
      if (value === undefined) {
        continue
      }
      found.set(name, gemIndex(value))
    }
    return found
  }

  /** singleton promise を返す（未構築なら構築を開始する）。 */
  private pool(): Promise<GemIndexPool> {
    const cached = cachedPool
    if (cached !== undefined) {
      return cached
    }

    const pending: Promise<GemIndexPool> = this.build().then(
      (build) => {
        if (!build.ok) {
          // 失敗はキャッシュしない（次のリクエストで再試行できるようにする）。
          forget(pending)
        }
        return build.pool
      },
      (error: unknown) => {
        forget(pending)
        warn(`候補プールの初期化に失敗しました: ${describe(error)}`)
        return new Map<string, number>()
      },
    )
    cachedPool = pending
    return pending
  }

  private async build(): Promise<PoolBuild> {
    const read = this.reader ?? (await resolveAssetReader())
    return buildPool(read)
  }
}

/** 自分が置いた Promise だけを取り下げる（別の構築が既に始まっていたらそれを壊さない）。 */
function forget(pending: Promise<GemIndexPool>): void {
  if (cachedPool === pending) {
    cachedPool = undefined
  }
}

/** `index.json` → 各シャードを並列取得 → 単一 Map にマージする。 */
async function buildPool(read: AssetReader): Promise<PoolBuild> {
  const empty: PoolBuild = { pool: new Map<string, number>(), ok: false }

  const indexRaw = await read(INDEX_PATH)
  if (indexRaw === null) {
    warn(`${INDEX_PATH} を読めませんでした。Gem バッジなしで継続します。`)
    return empty
  }

  const index = tryParseJson(indexRaw, INDEX_PATH)
  if (!isObject(index) || !Array.isArray(index.shards)) {
    warn(`${INDEX_PATH} の shards が配列ではありません。Gem バッジなしで継続します。`)
    return empty
  }

  const fileNames = index.shards
    .map((shard) => (isObject(shard) && typeof shard.fileName === 'string' ? shard.fileName : null))
    .filter((fileName): fileName is string => fileName !== null && fileName.length > 0)

  // 🔵 `D-38`: cold start で全シャードを **並列**（`Promise.all`）に取得する。
  const shards = await Promise.all(fileNames.map((fileName) => loadShard(read, fileName)))

  const pool = new Map<string, number>()
  for (const shard of shards) {
    for (const [fullName, value] of shard) {
      const current = pool.get(fullName)
      // 同一リポジトリが複数レジストリに出る場合は **値が小さい方（より過小評価）** を採る。
      // シャードの読み込み順に依存しない決定論的な選択にするための規則。
      if (current === undefined || value < current) {
        pool.set(fullName, value)
      }
    }
  }

  return { pool, ok: true }
}

/** 1 シャードを読んで `[小文字の owner/repo, Gem Index]` の配列にする。読めなければ空配列。 */
async function loadShard(read: AssetReader, fileName: string): Promise<readonly [string, number][]> {
  const path = `${GEM_INDEX_DIR}/${fileName}`
  const raw = await read(path)
  if (raw === null) {
    warn(`シャード ${fileName} を読めませんでした。このレジストリを除いて継続します。`)
    return []
  }

  const shard = tryParseJson(raw, path)
  if (!isObject(shard) || !Array.isArray(shard.columns) || !Array.isArray(shard.entries)) {
    warn(`シャード ${fileName} の形が想定と違います（columns / entries）。スキップします。`)
    return []
  }

  // 🔴 列の位置を決め打ちしない（`SP-17` が `columns` を同梱しているのは位置依存を避けるため）。
  const nameIndex = shard.columns.indexOf(COLUMN_REPOSITORY_FULL_NAME)
  const valueIndex = shard.columns.indexOf(COLUMN_GEM_INDEX)
  if (nameIndex < 0 || valueIndex < 0) {
    warn(
      `シャード ${fileName} の columns に ${COLUMN_REPOSITORY_FULL_NAME} / ${COLUMN_GEM_INDEX} が` +
        ' ありません。スキップします。',
    )
    return []
  }

  const rows: [string, number][] = []
  for (const entry of shard.entries) {
    if (!Array.isArray(entry)) {
      continue
    }
    const fullName = entry[nameIndex]
    const value = entry[valueIndex]
    if (typeof fullName !== 'string' || fullName.length === 0) {
      continue
    }
    // 非有限数は `gemIndex()`（スマートコンストラクタ）が throw するため、ここで先に弾く。
    if (typeof value !== 'number' || !Number.isFinite(value)) {
      continue
    }
    rows.push([fullName.toLowerCase(), value])
  }
  return rows
}

function tryParseJson(raw: string, path: string): unknown {
  try {
    return JSON.parse(raw)
  } catch (error) {
    warn(`${path} を JSON として解釈できませんでした: ${describe(error)}`)
    return null
  }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function describe(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function warn(message: string): void {
  console.warn(`[StaticGemIndex] ${message}`)
}
