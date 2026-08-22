import type { DigestMeta, GemPoolEntry } from '../../domain/model/gem'
import {
  matchesAllTokens,
  selectMostSelectiveToken,
  tokenizeIdentifier,
} from '../../domain/model/gem-keyword'
import { type GemIndex, gemIndex, gemIndexValue } from '../../domain/model/gem-index'
import type {
  GemIndexPort,
  GemPoolSearchInput,
  GemPoolSearchResult,
} from '../../domain/ports/gem-index-port'

import { type AssetReader, resolveAssetReader } from './asset-reader'
import { FALLBACK_META } from './static-gem-digest'

/**
 * Gem 候補プールのレジストリ別シャード（静的アセット）を読む `GemIndexPort` 実装
 * （`SP-18` で `lookup` / `SP-19` で `search` を追加・`D-36` / `D-37` / `D-38`）。
 *
 * 🔴 **配信方式（`D-38` の決定）**: レジストリ別の静的 JSON（`public/data/gem-index/`）を
 * isolate の cold start で `Promise.all` により **並列取得** して単一の索引にマージし、
 * 以降はメモリ上の索引だけで応答する。D1 の `IN` クエリ・ハッシュ分割シャード・
 * Range 二分探索・バンドル焼き込みはいずれも却下済み（理由は `open-questions.md` `D-38`）。
 *
 * 🔴 **アセットは 1 セットのまま・parse も 1 回のまま**（`SP-19` の制約）。所属照会（`lookup`）と
 * 絞り込み一覧（`search`）は **同じ 1 回の parse から作った同じ索引** を共有する。
 * 一覧に必要な `packageName` / `stars` / `dependentCount` / `registry` のためにアセットを
 * 増やしたり 2 回目の parse を走らせたりしない。
 *
 * 🔵 **cold start で作るもの（リクエスト時にやり直さないもの）**:
 * - `records`: **`gemIndex` 昇順・同値は `repositoryFullName` 昇順** に並べ替え済みの全レコード配列。
 *   一覧の並び順はプール全体で不変なので、ここで 1 回だけ並べておけばリクエスト側は
 *   「絞り込んで slice する」だけで済む（毎回 62,483 件を並べ替えない）。
 * - `tokens`: 照合用トークン列（`repositoryFullName` と `packageName` の単語和集合）。
 *   リクエストごとに全件を tokenize し直すと CPU 予算（`limits.cpu_ms`）を食う。
 *
 * 🔵 **singleton promise パターン**: 構築中の Promise を **モジュールスコープ** に保持し、
 * cold start 直後に同一 isolate へ並行到達したリクエストは同じ Promise を await するだけにする。
 * これをしないと並行リクエストがそれぞれ 12 本ずつ取得を走らせる。
 * ⚠️ cold start は「デプロイ直後の 1 回」ではなく **isolate ごとに継続的に発生する**。
 *
 * 🔴 **初期化に失敗した Promise はキャッシュしない**。失敗を抱え込むと、デプロイ直後の一時障害で
 * その isolate の生存期間ずっとバッジも一覧も出なくなる。失敗時は次のリクエストで再試行する。
 *
 * 🔴 **例外を投げない**（`GemIndexPort` の契約 / `D-28` の SPOF 方針）。壊れた入力・取得失敗は
 * `console.warn` でログだけ残し、**読めた分だけ**で索引を作る（全滅なら空の索引）。
 */

/** シャード置き場（`public/data/gem-index/`）の絶対パス。 */
const GEM_INDEX_DIR = '/data/gem-index'
/** 入口。`shards[].fileName` に各レジストリのシャード名が並ぶ。 */
const INDEX_PATH = `${GEM_INDEX_DIR}/index.json`

/** シャードのタプル配列から引く列名（`columns` の位置は決め打ちしない）。 */
const COLUMN_REPOSITORY_FULL_NAME = 'repositoryFullName'
const COLUMN_GEM_INDEX = 'gemIndex'
const COLUMN_PACKAGE_NAME = 'packageName'
const COLUMN_DEPENDENT_COUNT = 'dependentCount'
const COLUMN_STARS = 'stars'

/** ページングの防御既定値（ドメイン側で検証済みの値が来る前提だが、壊れた入力でも落とさない）。 */
const DEFAULT_PER_PAGE = 20

/**
 * 索引 1 件。`GemPoolEntry`（一覧が必要とする全項目）に、cold start で 1 回だけ計算した
 * 照合用の派生値を足したもの。
 *
 * - `tokens`: `repositoryFullName` と `packageName` を単語境界で割った **和集合**（重複は畳む）
 * - `lowerName`: 小文字化した `repositoryFullName`。dedupe・大文字小文字を無視した照合・
 *   ソートのタイブレークを **すべて同じ基準** で行うために持つ
 *
 * 🔴 これらは内部の派生値なので `search()` の返り値には載せない（`toEntry()` で素の
 * `GemPoolEntry` へ写す）。載せると UI へそのまま渡ったときにトークン列まで転送される。
 */
type GemPoolRecord = GemPoolEntry & {
  readonly tokens: readonly string[]
  readonly lowerName: string
}

/** cold start で 1 回だけ作る索引。`lookup` も `search` もこれだけを見る。 */
type GemPool = {
  /** `gemIndex` 昇順・同値は `lowerName`（小文字 `owner/repo`）昇順に並べ替え済みの全レコード。 */
  readonly records: readonly GemPoolRecord[]
  /** 小文字 `owner/repo` → レコード。`lookup()` の O(1) 照会用。 */
  readonly byRepo: ReadonlyMap<string, GemPoolRecord>
  /** 出典表示（`D-29` / `GR-6`）。`index.json` の `meta`。 */
  readonly meta: DigestMeta
}

const EMPTY_POOL: GemPool = {
  records: [],
  byRepo: new Map<string, GemPoolRecord>(),
  meta: FALLBACK_META,
}

/**
 * 構築結果。`ok=false` は **キャッシュしてはいけない失敗**（次のリクエストで再試行する）。
 *
 * 🔴 `ok` は「`index.json` が読めたか」ではなく **「シャードを 1 本でも読めたか」** で決める。
 * 入口だけ読めてシャードが全滅した状態を成功として singleton promise に固定すると、
 * その isolate の生存期間ずっと空プールのままになる（本ファイル冒頭の不変条件が
 * シャード層で破れる）。
 * 🔵 逆に **部分成功（例: 12 本中 11 本）はキャッシュしたままにする**。1 本の欠落で毎リクエスト
 * 12 本の再取得を走らせる方が害が大きく、読めた分だけで一覧もバッジも成立する。
 */
type PoolBuild = {
  readonly pool: GemPool
  readonly ok: boolean
}

/**
 * モジュールスコープの singleton promise。isolate の生存期間だけ生き、リクエストをまたいで共有される。
 * 🔴 ここを instance フィールドにすると、リクエストごとに索引を作り直して `D-38` の前提が崩れる。
 */
let cachedPool: Promise<GemPool> | undefined

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
    if (pool.byRepo.size === 0) {
      return found
    }

    for (const name of repositoryFullNames) {
      if (typeof name !== 'string' || name.length === 0) {
        continue
      }
      // 照合は索引側の正規化（小文字）に合わせる。返り値のキーは **入力の綴りのまま**。
      const record = pool.byRepo.get(name.toLowerCase())
      if (record === undefined) {
        continue
      }
      found.set(name, record.gemIndex)
    }
    return found
  }

  /**
   * 検索語のトークン列でプールを絞り込み、Gem Index 順の 1 ページ分を返す（`SP-19` / `D-36`）。
   *
   * 🔴 **`gemIndex` の閾値では絞らない**（一覧の母集団はプール全件。`D-36` が「一覧の中では
   * 全件が Gem なので Gem Index 順ソートが成立する」と定めた形）。
   * 🔵 **全語 AND → 0 件なら最も選択的な 1 語へ緩和**（`D-37`）。`image processing` のような
   * 概念語は AND では 1 件しかヒットしない実測があるため、0 件で終わらせない。
   */
  async search(input: GemPoolSearchInput): Promise<GemPoolSearchResult> {
    const pool = await this.pool()
    const tokens = normalizeTokens(input.tokens)

    // 🔴 読み込み失敗（プールが空）は `GemIndexPort#search` の契約どおり
    //    「`usedTokens: []` / `relaxed: false` の空結果」にする（緩和も試みない）。
    if (pool.records.length === 0) {
      return { items: [], totalCount: 0, usedTokens: [], relaxed: false, meta: pool.meta }
    }

    let matched: readonly GemPoolRecord[]
    let usedTokens: readonly string[] = tokens
    let relaxed = false

    if (tokens.length === 0) {
      // 検索語なし = 絞り込みなし（プール全件を Gem Index 順に見せる）。
      matched = pool.records
    } else {
      matched = pool.records.filter((record) => matchesAllTokens(record.tokens, tokens))
      // 🔵 `D-37`: 全語 AND が 0 件のときだけ「最も選択的な 1 語」へ緩める。
      if (matched.length === 0) {
        relaxed = true
        const fallbackToken = selectMostSelectiveToken(countSingleTokenHits(pool.records, tokens))
        if (fallbackToken === null) {
          // どの語も単独で 1 件もヒットしない → 緩めても空。
          usedTokens = []
        } else {
          const single: readonly string[] = [fallbackToken]
          matched = pool.records.filter((record) => matchesAllTokens(record.tokens, single))
          usedTokens = single
        }
      }
    }

    // `records` は cold start で並べ替え済みなので、絞り込み結果は既に
    // 「`gemIndex` 昇順・同値は `repositoryFullName` 昇順」を保っている（ここで並べ替えない）。
    const perPage = positiveIntOr(input.perPage, DEFAULT_PER_PAGE)
    const page = positiveIntOr(input.page, 1)
    const start = (page - 1) * perPage

    return {
      items: matched.slice(start, start + perPage).map(toEntry),
      totalCount: matched.length,
      usedTokens,
      relaxed,
      meta: pool.meta,
    }
  }

  /** singleton promise を返す（未構築なら構築を開始する）。 */
  private pool(): Promise<GemPool> {
    const cached = cachedPool
    if (cached !== undefined) {
      return cached
    }

    const pending: Promise<GemPool> = this.build().then(
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
        return EMPTY_POOL
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
function forget(pending: Promise<GemPool>): void {
  if (cachedPool === pending) {
    cachedPool = undefined
  }
}

/** 内部の派生値（`tokens` / `lowerName`）を落として、外へ出す形に写す。 */
function toEntry(record: GemPoolRecord): GemPoolEntry {
  return {
    packageName: record.packageName,
    repositoryFullName: record.repositoryFullName,
    dependentCount: record.dependentCount,
    stars: record.stars,
    gemIndex: record.gemIndex,
    registry: record.registry,
  }
}

/** 各トークンが **単独で** 何件に当たるかを 1 パスで数える（0 件の語は候補から外す）。 */
function countSingleTokenHits(
  records: readonly GemPoolRecord[],
  tokens: readonly string[],
): ReadonlyMap<string, number> {
  const singles = tokens.map((token) => [token, [token] as readonly string[]] as const)
  const counts = new Map<string, number>(tokens.map((token) => [token, 0]))
  for (const record of records) {
    for (const [token, single] of singles) {
      if (matchesAllTokens(record.tokens, single)) {
        counts.set(token, (counts.get(token) ?? 0) + 1)
      }
    }
  }
  // 🔵 1 件も当たらない語を残すと「最も選択的（＝件数最小）」がその語になり、緩和しても
  //    必ず 0 件になる。緩和の意味がなくなるので、ヒットのある語だけを候補にする。
  for (const [token, count] of counts) {
    if (count === 0) {
      counts.delete(token)
    }
  }
  return counts
}

/** 入力トークンの防御的な正規化（非空文字列のみ・重複は畳む・順序は維持）。 */
function normalizeTokens(tokens: readonly string[] | undefined): readonly string[] {
  if (!Array.isArray(tokens)) {
    return []
  }
  const seen = new Set<string>()
  for (const token of tokens) {
    if (typeof token === 'string' && token.length > 0) {
      seen.add(token)
    }
  }
  return [...seen]
}

/** 1 以上の整数へ丸める（非有限・0 以下は既定値へ倒す）。 */
function positiveIntOr(value: number, fallback: number): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return fallback
  }
  const floored = Math.floor(value)
  return floored >= 1 ? floored : fallback
}

/** `index.json` → 各シャードを並列取得 → 単一の索引にマージする。 */
async function buildPool(read: AssetReader): Promise<PoolBuild> {
  const indexRaw = await read(INDEX_PATH)
  if (indexRaw === null) {
    warn(`${INDEX_PATH} を読めませんでした。Gem バッジ・Gem 一覧なしで継続します。`)
    return { pool: EMPTY_POOL, ok: false }
  }

  const index = tryParseJson(indexRaw, INDEX_PATH)
  const meta = parseMeta(isObject(index) ? index.meta : undefined)
  const emptyWithMeta: PoolBuild = { pool: { ...EMPTY_POOL, meta }, ok: false }

  if (!isObject(index) || !Array.isArray(index.shards)) {
    warn(`${INDEX_PATH} の shards が配列ではありません。Gem バッジ・Gem 一覧なしで継続します。`)
    return emptyWithMeta
  }

  const fileNames = index.shards
    .map((shard) => (isObject(shard) && typeof shard.fileName === 'string' ? shard.fileName : null))
    .filter((fileName): fileName is string => fileName !== null && fileName.length > 0)

  // 🔵 `D-38`: cold start で全シャードを **並列**（`Promise.all`）に取得する。
  const shards = await Promise.all(fileNames.map((fileName) => loadShard(read, fileName)))
  const loaded = shards.filter((shard): shard is readonly GemPoolRecord[] => shard !== null)

  const byRepo = new Map<string, GemPoolRecord>()
  for (const shard of loaded) {
    for (const record of shard) {
      const current = byRepo.get(record.lowerName)
      // 同一リポジトリが複数レジストリに出る場合は **値が小さい方（より過小評価）** を採る。
      // シャードの読み込み順に依存しない決定論的な選択にするための規則。
      if (current === undefined || record.gemIndex < current.gemIndex) {
        byRepo.set(record.lowerName, record)
      }
    }
  }

  // 🔴 並べ替えは cold start の 1 回だけ（`gemIndex` 昇順 → 同値は `lowerName` 昇順）。
  const records = [...byRepo.values()].sort(compareRecords)
  const pool: GemPool = { records, byRepo, meta }

  // 全滅（1 本も読めなかった）のときだけ失敗扱いにして再試行対象にする。部分成功はキャッシュする。
  if (loaded.length === 0) {
    warn(
      'シャードを 1 本も読めませんでした。Gem バッジ・Gem 一覧なしで継続し、' +
        '次のリクエストで再試行します。',
    )
    return { pool, ok: false }
  }
  return { pool, ok: true }
}

/**
 * 一覧の並び順（決定論）。`gemIndex` 昇順（小さいほど過小評価が強い＝上位）、
 * 同値は小文字化した `repositoryFullName` 昇順。
 */
function compareRecords(a: GemPoolRecord, b: GemPoolRecord): number {
  const diff = gemIndexValue(a.gemIndex) - gemIndexValue(b.gemIndex)
  if (diff !== 0) {
    return diff
  }
  return a.lowerName < b.lowerName ? -1 : a.lowerName > b.lowerName ? 1 : 0
}

/**
 * 1 シャードを読んでレコード配列にする。
 * 🔴 **読めなかった場合は `null`**（空配列と区別する）。呼び出し側が「全滅か部分成功か」を
 * 判定できなくなるため、失敗を空配列に潰さない。
 */
async function loadShard(
  read: AssetReader,
  fileName: string,
): Promise<readonly GemPoolRecord[] | null> {
  const path = `${GEM_INDEX_DIR}/${fileName}`
  const raw = await read(path)
  if (raw === null) {
    warn(`シャード ${fileName} を読めませんでした。このレジストリを除いて継続します。`)
    return null
  }

  const shard = tryParseJson(raw, path)
  if (!isObject(shard) || !Array.isArray(shard.columns) || !Array.isArray(shard.entries)) {
    warn(`シャード ${fileName} の形が想定と違います（columns / entries）。スキップします。`)
    return null
  }

  // 🔴 一覧はレジストリ名を表示する（`GemPoolEntry.registry`）。シャード文書の `registry` が
  //    無いと表示できないため、そのシャードは丸ごとスキップする（空文字で埋めない）。
  const registry = shard.registry
  if (typeof registry !== 'string' || registry.length === 0) {
    warn(`シャード ${fileName} に registry がありません。スキップします。`)
    return null
  }

  // 🔴 列の位置を決め打ちしない（`SP-17` が `columns` を同梱しているのは位置依存を避けるため）。
  const nameIndex = shard.columns.indexOf(COLUMN_REPOSITORY_FULL_NAME)
  const valueIndex = shard.columns.indexOf(COLUMN_GEM_INDEX)
  if (nameIndex < 0 || valueIndex < 0) {
    warn(
      `シャード ${fileName} の columns に ${COLUMN_REPOSITORY_FULL_NAME} / ${COLUMN_GEM_INDEX} が` +
        ' ありません。スキップします。',
    )
    return null
  }

  // 🔵 一覧用の列（`packageName` / `dependentCount` / `stars`）は **無くてもスキップしない**。
  //    所属照会（バッジ）は `repositoryFullName` と `gemIndex` だけで成立するため、
  //    ここで必須にすると古い形のシャードでバッジまで落ちる。欠けた列は既定値で埋める。
  const packageIndex = shard.columns.indexOf(COLUMN_PACKAGE_NAME)
  const dependentIndex = shard.columns.indexOf(COLUMN_DEPENDENT_COUNT)
  const starsIndex = shard.columns.indexOf(COLUMN_STARS)
  if (packageIndex < 0 || dependentIndex < 0 || starsIndex < 0) {
    warn(
      `シャード ${fileName} の columns に一覧用の列（${COLUMN_PACKAGE_NAME} /` +
        ` ${COLUMN_DEPENDENT_COUNT} / ${COLUMN_STARS}）が揃っていません。` +
        '所属判定のみに使い、欠けた項目は既定値で埋めます。',
    )
  }

  const records: GemPoolRecord[] = []
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

    const packageName = stringAt(entry, packageIndex)
    const lowerName = fullName.toLowerCase()
    records.push({
      packageName,
      repositoryFullName: fullName,
      dependentCount: finiteAt(entry, dependentIndex),
      stars: finiteAt(entry, starsIndex),
      gemIndex: gemIndex(value),
      registry,
      // 🔴 照合用トークンは cold start で 1 回だけ計算する（リクエストごとに全件を
      //    tokenize し直すと `limits.cpu_ms` を食う）。repo 名とパッケージ名の和集合。
      tokens: mergeTokens(lowerName, packageName),
      lowerName,
    })
  }
  return records
}

/** `repositoryFullName` と `packageName` の単語を重複なく 1 本の配列に畳む。 */
function mergeTokens(repositoryFullName: string, packageName: string): readonly string[] {
  const tokens = tokenizeIdentifier(repositoryFullName)
  if (packageName.length === 0) {
    return dedupe(tokens)
  }
  return dedupe([...tokens, ...tokenizeIdentifier(packageName)])
}

function dedupe(tokens: readonly string[]): readonly string[] {
  // 重複が無いケース（大半）で配列を作り直さない。
  const unique = new Set(tokens)
  return unique.size === tokens.length ? tokens : [...unique]
}

function stringAt(entry: readonly unknown[], index: number): string {
  if (index < 0) {
    return ''
  }
  const value = entry[index]
  return typeof value === 'string' ? value : ''
}

function finiteAt(entry: readonly unknown[], index: number): number {
  if (index < 0) {
    return 0
  }
  const value = entry[index]
  return typeof value === 'number' && Number.isFinite(value) ? value : 0
}

/**
 * `index.json` の `meta` を出典表示（`D-29`）へ落とす。フィールド単位でフォールバックする
 * （1 つ壊れても他の帰属情報は活かす）。既定値は `StaticGemDigest` と **同じもの** を使う
 * （出典・ライセンスは同一バッチが書く固定値なので、2 か所に別々の既定を置かない）。
 */
function parseMeta(raw: unknown): DigestMeta {
  if (!isObject(raw)) {
    warn(`${INDEX_PATH} の meta が読めません。既定の帰属表示へフォールバックします。`)
    return FALLBACK_META
  }
  return {
    source: nonEmptyStringOr(raw.source, FALLBACK_META.source),
    // 🔴 `javascript:` / `data:` スキームは `<a href>` へ流さない（React 19 は
    //    `javascript:` href でレンダリング例外を投げ、画面全体が 500 になる）。
    sourceUrl: httpUrlOr(raw.sourceUrl, FALLBACK_META.sourceUrl),
    license: nonEmptyStringOr(raw.license, FALLBACK_META.license),
    sourceLicenseUrl: httpUrlOr(raw.sourceLicenseUrl, FALLBACK_META.sourceLicenseUrl),
    generatedAt: nonEmptyStringOr(raw.generatedAt, FALLBACK_META.generatedAt),
  }
}

function nonEmptyStringOr(value: unknown, fallback: string): string {
  return typeof value === 'string' && value.length > 0 ? value : fallback
}

/** `http:` / `https:` のみ許可する（スキーム経由の XSS・レンダリング例外を入口で止める）。 */
function httpUrlOr(value: unknown, fallback: string): string {
  if (typeof value === 'string') {
    try {
      const url = new URL(value)
      if (url.protocol === 'http:' || url.protocol === 'https:') {
        return value
      }
    } catch {
      // URL としてパースできない → 下のフォールバックへ落とす。
    }
  }
  return fallback
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
