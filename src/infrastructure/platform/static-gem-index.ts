import type { DigestMeta, GemPoolEntry } from '../../domain/model/gem'
import {
  MAX_QUERY_TOKENS,
  matchesAllTokens,
  selectMostSelectiveToken,
  tokenizeIdentifier,
} from '../../domain/model/gem-keyword'
import { type GemIndex, gemIndex, gemIndexValue } from '../../domain/model/gem-index'
import { DEFAULT_PAGE } from '../../domain/model/page-number'
import { DEFAULT_PER_PAGE } from '../../domain/model/per-page'
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
 * 絞り込み一覧（`search`）は **同じ 1 回の parse から作った同じプール** を共有する。
 * 一覧に必要な `packageName` / `stars` / `dependentCount` / `registry` のためにアセットを
 * 増やしたり 2 回目の parse を走らせたりしない。
 *
 * ## 🔴 2 段の遅延構築（`SP-19` 実測に基づく設計・親裁定 2026-08-22）
 *
 * 索引は **用途ごとに 2 段** に分け、`search` にしか要らないコストを `lookup` に払わせない。
 *
 * | 段 | 中身 | いつ作るか | 実測コスト |
 * |---|---|---|---|
 * | **プール**（`GemPool`） | `byRepo`（小文字 repo 名 → エントリ）・`meta` | cold start（`lookup` / `search` のどちらでも） | 約 82ms |
 * | **検索インデックス**（`SearchIndex`） | 照合用トークン列 + `gemIndex` 昇順に並べ替えた配列 | **初回の `search()`** | 追加で約 122ms |
 * |
 *
 * ⚠️ **なぜ分けるか**: tokenize（62,483 件 × 2 識別子・約 91ms）と並べ替え（約 31ms）は
 * **一覧専用のコスト**。これを cold start に置くと、`SP-18` で出荷済みの「検索結果ページの
 * Gem バッジ」経路（`lookup` だけを呼ぶ）が、自分では使わないコストを isolate ごとに払う
 * **既存機能の回帰** になる。したがって `lookup` しか来ないリクエストでは tokenize も
 * 並べ替えも走らせない。
 *
 * 🔵 **どちらの段も singleton**（構築中の Promise をモジュールスコープに保持する）。
 * cold start 直後に同一 isolate へ並行到達したリクエストは同じ Promise を await するだけで、
 * 12 本の取得も 62,483 件の tokenize も二重に走らない。
 * ⚠️ cold start は「デプロイ直後の 1 回」ではなく **isolate ごとに継続的に発生する**。
 *
 * 🔴 **初期化に失敗した Promise はキャッシュしない**（どちらの段も同じ扱い）。失敗を抱え込むと、
 * デプロイ直後の一時障害でその isolate の生存期間ずっとバッジも一覧も出なくなる。
 *
 * 🔴 **例外を投げない**（`GemIndexPort` の契約 / `D-28` の SPOF 方針）。壊れた入力・取得失敗は
 * `console.warn` でログだけ残し、**読めた分だけ**で索引を作る（全滅なら空の索引）。
 * 検索インデックスの構築が失敗しても **`lookup` は従来どおり動く**（段が独立しているため）。
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

/**
 * `owner/repo` の形式判定。`string かつ非空` だけでは `../settings` `owner/` `a/b/c` が通り、
 * 一覧の項目名とリンク先が食い違う（`F-09`）。
 *
 * 🔴 **正本は `static-gem-digest.ts` の `REPOSITORY_FULL_NAME_PATTERN`（同一パターン）**。
 * 共有モジュールへの切り出しは別 Issue（本 PR のファイル分担の外側にあるため今回は同値複製）。
 * ⚠️ ドメインの `tryRepositoryFullName` は使わない。`OWNER_PATTERN` が末尾ハイフンを禁止しており、
 * 実データに末尾ハイフンの owner が 25 件（`Qix-/color-convert` 等）実在してリンクが消える。
 */
const REPOSITORY_FULL_NAME_PATTERN = /^[^/\s]+\/[^/\s]+$/

/**
 * `owner/repo` として受理してよい値か。
 *
 * 🔴 上のパターン **だけでは `../settings` を弾けない**（`..` は `/` も空白も含まないので
 * `[^/\s]+` に一致してしまう）。`F-09` が問題にしたのはまさにその値なので、ドットだけの
 * セグメント（`.` / `..`）を明示的に落とす。
 * ⚠️ したがって本関数は正本（`static-gem-digest.ts` の同一パターン）より **厳しい**。
 * 共有モジュールへ切り出すときは、この 1 段も一緒に持っていく（別 Issue）。
 */
function isSafeRepositoryFullName(value: string): boolean {
  if (!REPOSITORY_FULL_NAME_PATTERN.test(value)) {
    return false
  }
  // パターン上ちょうど 2 セグメントなので、それぞれがドットだけでないことを見れば足りる。
  return value.split('/').every((segment) => segment !== '.' && segment !== '..')
}

/**
 * プール 1 件。`GemPoolEntry`（一覧が必要とする全項目）に、照合の基準となる小文字名を足したもの。
 *
 * `lowerName` は dedupe・大文字小文字を無視した照合・並べ替えのタイブレークを
 * **すべて同じ基準** で行うために持つ。
 * 🔴 内部の派生値なので外へ出す前に `toEntry()` で素の `GemPoolEntry` へ写す。
 */
type PoolEntry = GemPoolEntry & {
  readonly lowerName: string
  /**
   * 一覧の母集団に出してよいか（`F-17`）。
   *
   * 🔴 一覧用の列（`packageName` / `dependentCount` / `stars`）が **シャードに揃っていた** ときだけ
   * `true`。揃っていないシャードのレコードは所属判定（バッジ）にだけ使い、一覧には出さない。
   * 欠損を `''` / `0` で埋めた値を「★ 0 / 0 件」という **事実として** 表示してしまうため
   * （検証ではなく捏造・`ARCH-R1`）。
   */
  readonly listable: boolean
}

/** cold start で作る第 1 段。`lookup` はこれだけで応答できる。 */
type GemPool = {
  /** 小文字 `owner/repo` → エントリ。`lookup()` の O(1) 照会用。 */
  readonly byRepo: ReadonlyMap<string, PoolEntry>
  /** 出典表示（`D-29` / `GR-6`）。`index.json` の `meta`。 */
  readonly meta: DigestMeta
}

/** 検索インデックス 1 件。プールのエントリ（参照）に、照合用トークン列を添えたもの。 */
type SearchRecord = {
  readonly entry: PoolEntry
  /** `repositoryFullName` と `packageName` を単語境界で割った **和集合**（重複は畳む）。 */
  readonly tokens: readonly string[]
}

/** 初回の `search()` で作る第 2 段。`gemIndex` 昇順・同値は repo 名昇順に並べ替え済み。 */
type SearchIndex = {
  readonly records: readonly SearchRecord[]
}

const EMPTY_POOL: GemPool = {
  byRepo: new Map<string, PoolEntry>(),
  meta: FALLBACK_META,
}

const EMPTY_SEARCH_INDEX: SearchIndex = { records: [] }

/**
 * プールの構築結果。`ok=false` は **キャッシュしてはいけない失敗**（次のリクエストで再試行する）。
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
 * モジュールスコープの singleton promise（第 1 段）。isolate の生存期間だけ生き、
 * リクエストをまたいで共有される。
 * 🔴 ここを instance フィールドにすると、リクエストごとに索引を作り直して `D-38` の前提が崩れる。
 */
let cachedPool: Promise<GemPool> | undefined

/**
 * モジュールスコープの singleton promise（第 2 段）。**どのプールから作ったか** を一緒に持つ。
 * 🔴 プールが作り直された（失敗後の再試行で別インスタンスになった）ときに古い検索インデックスを
 * 使い回さないための同一性チェック用。
 */
let cachedSearchIndex: { readonly pool: GemPool; readonly index: Promise<SearchIndex> } | undefined

/**
 * 検索インデックス（第 2 段）を **実際に構築した回数**。
 *
 * 🔴 「一覧専用のコストを `lookup` に払わせない」「warm では作り直さない」という設計上の不変条件を、
 * テストが **モックなしで** 観測するための計測点（`F-18`。自作モジュールへの `vi.mock` は
 * `testing-strategy.md` §4 が禁じている）。本番コードの分岐には一切使わない。
 */
let searchIndexBuilds = 0

/** テスト用: 検索インデックスの構築回数（`resetGemIndexCacheForTest()` で 0 に戻る）。 */
export function searchIndexBuildCountForTest(): number {
  return searchIndexBuilds
}

/** テスト用: モジュールスコープの singleton promise を **両段とも** 捨てる（計測点も 0 に戻す）。 */
export function resetGemIndexCacheForTest(): void {
  cachedPool = undefined
  cachedSearchIndex = undefined
  searchIndexBuilds = 0
}

export class StaticGemIndex implements GemIndexPort {
  /**
   * `AssetReader` を注入できるようにしておく（テスト用）。省略すると実行環境に応じた
   * reader（Workers Static Assets / ファイルシステム）を `resolveAssetReader()` が選ぶ。
   */
  constructor(private readonly reader?: AssetReader) {}

  /**
   * 🔵 **第 1 段だけで応答する**（トークン計算も並べ替えもしない）。検索結果ページの
   * Gem バッジはこの経路しか使わないため、一覧専用のコストを払わせない。
   */
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
      const entry = pool.byRepo.get(name.toLowerCase())
      if (entry === undefined) {
        continue
      }
      found.set(name, entry.gemIndex)
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
   * 🔵 初回呼び出しでだけ検索インデックス（第 2 段）を作る。2 回目以降は参照するだけ。
   * 🔵 **母集団は一覧用の列が揃ったレコードだけ**（欠損を既定値で埋めたものは出さない・`F-17`）。
   * 🔵 **範囲外のページは最終ページへクランプ** し、返したページを `effectivePage` で報告する（`F-02`）。
   *
   * ⚠️ **絞り込みは 62,483 件の線形走査**（warm で実測 8〜12ms）。トークン → レコードの
   * 転置索引にすれば sub-ms にできるが、その索引の構築コストとメモリが cold start 側へ
   * 上乗せされ、`limits.cpu_ms` を押し上げる方向に働く。warm 8〜12ms は許容範囲と判断して
   * **採らない**（`SP-19` の裁定・2026-08-22）。作り直す前に同じ計測をやり直さなくてよい。
   */
  async search(input: GemPoolSearchInput): Promise<GemPoolSearchResult> {
    const pool = await this.pool()

    // 🔴 読み込み失敗（プールが空）は `GemIndexPort#search` の契約どおり
    //    「`usedTokens: []` / `relaxed: false` の空結果」にする（緩和も試みない）。
    //    ここで打ち切ることで、失敗時に無駄な検索インデックス構築も走らせない。
    if (pool.byRepo.size === 0) {
      return emptyResult(pool.meta)
    }

    const { records } = await searchIndex(pool)
    if (records.length === 0) {
      // 検索インデックスの構築に失敗した場合、または **一覧に出せるレコードが 1 件も無い**
      // 場合（全シャードで一覧用の列が欠けている・`F-17`）。`lookup` は上のとおり生きている。
      return emptyResult(pool.meta)
    }

    const tokens = normalizeTokens(input.tokens)
    let matched: readonly SearchRecord[]
    let usedTokens: readonly string[] = tokens
    let relaxed = false

    if (tokens.length === 0) {
      // 検索語なし = 絞り込みなし（プール全件を Gem Index 順に見せる）。
      matched = records
    } else {
      matched = records.filter((record) => matchesAllTokens(record.tokens, tokens))
      // 🔵 `D-37`: 全語 AND が 0 件のときだけ「最も選択的な 1 語」へ緩める。
      if (matched.length === 0) {
        const fallbackToken = selectMostSelectiveToken(countSingleTokenHits(records, tokens))
        if (fallbackToken === null) {
          // 🔴 どの語も単独で 1 件もヒットしない = **緩和は起きていない**（試みただけ）。
          //    ここで `relaxed: true` を返すと UI が「『{usedTokens[0]}』だけで絞り込んだ」と
          //    空の語で注記してしまう。`relaxed` は **実際に 1 語へ緩めたか** で立てる。
          usedTokens = []
        } else {
          const single: readonly string[] = [fallbackToken]
          matched = records.filter((record) => matchesAllTokens(record.tokens, single))
          usedTokens = single
          relaxed = true
        }
      }
    }

    // `records` は検索インデックス構築時に並べ替え済みなので、絞り込み結果は既に
    // 「`gemIndex` 昇順・同値は `repositoryFullName` 昇順」を保っている（ここで並べ替えない）。

    // 🔵 `SP-19` 追補（`案3'`・Issue #453）: 同伴指定のマージ。`relaxed` / `usedTokens` は
    //    上で確定済み（名前照合＝AND だけで判定）なので、ここから下では一切触らない。
    const merged = mergeIncludedRecords(matched, records, input.includeFullNames)

    const perPage = positiveIntOr(input.perPage, DEFAULT_PER_PAGE)
    // 🔵 範囲外のページは **最終ページへクランプ**（`F-02`）。1 ページ目へ倒すと、`?page=999` を
    //    直打ちした利用者に「最後のページ」ではなく「先頭」が返り、総件数表示と食い違う。
    //    クランプの母数は **マージ後** の件数（同伴分もページングに参加する）。
    const effectivePage = clampPage(input.page, merged.length, perPage)
    const start = (effectivePage - 1) * perPage

    return {
      items: merged.slice(start, start + perPage).map((record) => toEntry(record.entry)),
      totalCount: merged.length,
      effectivePage,
      usedTokens,
      relaxed,
      meta: pool.meta,
    }
  }

  /** 第 1 段の singleton promise を返す（未構築なら構築を開始する）。 */
  private pool(): Promise<GemPool> {
    const cached = cachedPool
    if (cached !== undefined) {
      return cached
    }

    const pending: Promise<GemPool> = this.build().then(
      (build) => {
        if (!build.ok) {
          // 失敗はキャッシュしない（次のリクエストで再試行できるようにする）。
          forgetPool(pending)
        }
        return build.pool
      },
      (error: unknown) => {
        forgetPool(pending)
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
function forgetPool(pending: Promise<GemPool>): void {
  if (cachedPool === pending) {
    cachedPool = undefined
  }
}

function forgetSearchIndex(pending: Promise<SearchIndex>): void {
  if (cachedSearchIndex?.index === pending) {
    cachedSearchIndex = undefined
  }
}

/**
 * 第 2 段（検索インデックス）の singleton promise を返す。
 *
 * 🔴 **`search()` からしか呼ばない**（`lookup` には tokenize も並べ替えも要らない）。
 * 🔴 失敗した Promise はキャッシュしない（第 1 段と同じ扱い）。失敗しても `lookup` は生きる。
 */
function searchIndex(pool: GemPool): Promise<SearchIndex> {
  const cached = cachedSearchIndex
  // プールが作り直されていたら（失敗後の再試行等）、古いインデックスは捨てて作り直す。
  if (cached !== undefined && cached.pool === pool) {
    return cached.index
  }

  const pending: Promise<SearchIndex> = buildSearchIndex(pool).catch((error: unknown) => {
    forgetSearchIndex(pending)
    warn(`検索インデックスの構築に失敗しました: ${describe(error)}`)
    return EMPTY_SEARCH_INDEX
  })
  cachedSearchIndex = { pool, index: pending }
  return pending
}

/**
 * プールから検索インデックスを作る（**初回の `search()` で 1 回だけ**）。
 *
 * ⚠️ 実測（62,483 件）: tokenize 約 91ms + 並べ替え約 31ms。ここが一覧専用のコストであり、
 * cold start に置かない理由（本ファイル冒頭の 2 段構成を参照）。
 */
async function buildSearchIndex(pool: GemPool): Promise<SearchIndex> {
  searchIndexBuilds += 1
  const records: SearchRecord[] = []
  for (const entry of pool.byRepo.values()) {
    // 🔴 一覧に出せないレコード（欠損列を埋めたもの）は母集団に入れない（`F-17`）。
    //    `lookup`（バッジ）は `pool.byRepo` を直接引くので、除外してもバッジは出続ける。
    if (!entry.listable) {
      continue
    }
    records.push({ entry, tokens: mergeTokens(entry.lowerName, entry.packageName) })
  }
  records.sort(compareRecords)
  return { records }
}

function emptyResult(meta: DigestMeta): GemPoolSearchResult {
  return {
    items: [],
    totalCount: 0,
    effectivePage: DEFAULT_PAGE,
    usedTokens: [],
    relaxed: false,
    meta,
  }
}

/**
 * `includeFullNames`（ポート入力）として実際に走査する最大件数。
 *
 * 🔴 `normalizeTokens`（`F-01`）と同じ流儀の二重防御: ユースケース層（`search-gems.ts` の
 * `MAX_INCLUDE_FULL_NAMES`）が正規の入口だが、ポートは外部入力の受け口なので、正規化
 * ユースケースを経由せずに直接呼ばれても有界にしておく。
 *
 * 🔴 **ユースケース側の上限を import せず、値を独立に定義する**（`normalizeTokens` が
 * `MAX_QUERY_TOKENS` を `domain/model/gem-keyword.ts` から import しているのとは異なる）。
 * あちらは「照合規則の正本はドメイン層」という理由でユースケース層もポート層も同じ値を
 * 参照する対称な関係だが、こちらは「ユースケース層の URL 入力向け上限」と「ポート層の
 * 入力全般に対する二重防御」という **非対称な関係**（ポートを直接呼ぶテスト・将来の別
 * ユースケースが、ユースケース側の定数変更に連動して意図せず緩む/絞ることを避ける）。
 */
const MAX_INCLUDE_FULL_NAMES = 20

/**
 * 同伴指定（`includeFullNames`）を名前照合の結果（`matched`）へマージする
 * （`SP-19` 追補・`案3'`・Issue #453）。
 *
 * 🔴 **`records`（検索インデックス）を引くだけ**（新しいアセット読み込み・2 回目の parse・
 * トークン再計算はしない）。`records` は既に `listable` なレコードだけを持つため、一覧に
 * 出せないレコード（欠損列を埋めたもの）は素通しで無視される（`records` に無い＝候補にならない）。
 *
 * 🔴 **`includeFullNames` は先頭 `MAX_INCLUDE_FULL_NAMES` 件までしか走査しない**（`F-01` 相当）。
 * 正規のユースケース層が既に上限を掛けているが、ポートは外部入力の受け口として二重に有界化する
 * （`normalizeTokens` と同じ設計）。走査の打ち切りは有効/無効を問わず件数だけで判定する
 * （不正値の除外だけを続けると、不正値を大量に並べる入力で走査量が有効件数と無関係に膨らむ）。
 *
 * 🔵 マージ後は `compareRecords`（`gemIndex` 昇順・同値は `repositoryFullName` 昇順）で
 * 並べ直す（同伴分を先頭に固定しない）。`includeFullNames` が空・未指定なら `matched` を
 * そのまま返す（余計なソート・配列複製をしない）。
 */
function mergeIncludedRecords(
  matched: readonly SearchRecord[],
  records: readonly SearchRecord[],
  includeFullNames: readonly string[] | undefined,
): readonly SearchRecord[] {
  if (includeFullNames === undefined || includeFullNames.length === 0) {
    return matched
  }

  const matchedLower = new Set(matched.map((record) => record.entry.lowerName))
  const recordByLowerName = new Map(records.map((record) => [record.entry.lowerName, record]))

  const additions: SearchRecord[] = []
  let scanned = 0
  for (const name of includeFullNames) {
    if (scanned >= MAX_INCLUDE_FULL_NAMES) {
      break
    }
    scanned += 1
    if (typeof name !== 'string' || name.length === 0) {
      continue
    }
    const lowerName = name.toLowerCase()
    if (matchedLower.has(lowerName)) {
      // 名前照合（AND）に既に一致している、または同伴指定内の重複。
      continue
    }
    const record = recordByLowerName.get(lowerName)
    if (record === undefined) {
      // プールに載っていない、または listable=false（一覧の母集団に無い）。
      continue
    }
    additions.push(record)
    matchedLower.add(lowerName)
  }

  if (additions.length === 0) {
    return matched
  }

  return [...matched, ...additions].sort(compareRecords)
}

/**
 * 実際に返すページ番号（1 始まり）を決める。範囲外は **最終ページへクランプ** する（`F-02`）。
 * 0 件・壊れた入力は 1 ページ目。
 */
function clampPage(page: number, totalCount: number, perPage: number): number {
  if (totalCount <= 0) {
    return DEFAULT_PAGE
  }
  const lastPage = Math.max(DEFAULT_PAGE, Math.ceil(totalCount / perPage))
  const requested = Math.max(DEFAULT_PAGE, Math.trunc(page) || DEFAULT_PAGE)
  return Math.min(requested, lastPage)
}

/** 内部の派生値（`lowerName` / `listable`）を落として、外へ出す形に写す。 */
function toEntry(entry: PoolEntry): GemPoolEntry {
  return {
    packageName: entry.packageName,
    repositoryFullName: entry.repositoryFullName,
    dependentCount: entry.dependentCount,
    stars: entry.stars,
    gemIndex: entry.gemIndex,
    registry: entry.registry,
  }
}

/**
 * 各トークンが **単独で** 何件に当たるかを 1 パスで数える（0 件の語は候補に入らない）。
 *
 * 🔴 **ループの向き（`F-01`・CPU 枯渇の防止）**: 「レコード × トークン」ではなく
 * **レコード側だけを回し、そのレコードが持つ語（平均 3.4 語）を `wanted` に問い合わせる**。
 * 逆向き（トークンごとに全レコードを走査）は仕事量が `62,483 × トークン数` になり、
 * 一致しない語を並べるだけで 1 リクエストが CPU を使い切れた
 * （実機で 800 語 → `error code: 1102`）。この向きなら **トークン数に依存しない O(レコード数)** で、
 * `MAX_QUERY_TOKENS` の上限と合わせて二重に有界になる。
 * 🔵 0 件の語は Map に入らないので、後段で削除する処理も要らない（1 件も当たらない語を残すと
 * 「最も選択的（＝件数最小）」がその語になり、緩めても必ず 0 件になる）。
 */
function countSingleTokenHits(
  records: readonly SearchRecord[],
  tokens: readonly string[],
): ReadonlyMap<string, number> {
  const wanted = new Set(tokens)
  const counts = new Map<string, number>()
  for (const record of records) {
    for (const token of record.tokens) {
      if (wanted.has(token)) {
        counts.set(token, (counts.get(token) ?? 0) + 1)
      }
    }
  }
  return counts
}

/**
 * 入力トークンの防御的な正規化（非空文字列のみ・重複は畳む・順序は維持）。
 *
 * 🔴 **語数上限も二重に掛ける**（`F-01`）。上限値の正本は照合規則側の
 * `MAX_QUERY_TOKENS`（`domain/model/gem-keyword.ts`）で、ここは import して使うだけ。
 * ポートは外部入力の受け口なので、`tokenizeQuery` を通さずに直接呼ばれても有界にしておく。
 */
function normalizeTokens(tokens: readonly string[] | undefined): readonly string[] {
  if (!Array.isArray(tokens)) {
    return []
  }
  const seen = new Set<string>()
  for (const token of tokens) {
    if (typeof token === 'string' && token.length > 0) {
      seen.add(token)
      if (seen.size >= MAX_QUERY_TOKENS) {
        break
      }
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

/** `index.json` → 各シャードを並列取得 → 単一のプールにマージする。 */
async function buildPool(read: AssetReader): Promise<PoolBuild> {
  const indexRaw = await read(INDEX_PATH)
  if (indexRaw === null) {
    warn(`${INDEX_PATH} を読めませんでした。Gem バッジ・Gem 一覧なしで継続します。`)
    return { pool: EMPTY_POOL, ok: false }
  }

  const index = tryParseJson(indexRaw, INDEX_PATH)
  const meta = parseMeta(isObject(index) ? index.meta : undefined)

  if (!isObject(index) || !Array.isArray(index.shards)) {
    warn(`${INDEX_PATH} の shards が配列ではありません。Gem バッジ・Gem 一覧なしで継続します。`)
    return { pool: { ...EMPTY_POOL, meta }, ok: false }
  }

  const fileNames = index.shards
    .map((shard) => (isObject(shard) && typeof shard.fileName === 'string' ? shard.fileName : null))
    .filter((fileName): fileName is string => fileName !== null && fileName.length > 0)

  // 🔵 `D-38`: cold start で全シャードを **並列**（`Promise.all`）に取得する。
  const shards = await Promise.all(fileNames.map((fileName) => loadShard(read, fileName)))
  const loaded = shards.filter((shard): shard is readonly PoolEntry[] => shard !== null)

  const byRepo = new Map<string, PoolEntry>()
  for (const shard of loaded) {
    for (const entry of shard) {
      const current = byRepo.get(entry.lowerName)
      // 同一リポジトリが複数レジストリに出る場合は **値が小さい方（より過小評価）** を採る。
      // 🔴 同値のときは `registry` 昇順で決める（`F-08`）。狭義比較だけだと同値では先に読んだ
      //    シャードが勝ち、`index.json` の `shards` の並びを入れ替えるだけで一覧に出る
      //    `registry` / `packageName` が入れ替わる（＝読み込み順に依存してしまう）。
      if (
        current === undefined ||
        entry.gemIndex < current.gemIndex ||
        (entry.gemIndex === current.gemIndex && entry.registry < current.registry)
      ) {
        byRepo.set(entry.lowerName, entry)
      }
    }
  }

  const pool: GemPool = { byRepo, meta }

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
function compareRecords(a: SearchRecord, b: SearchRecord): number {
  const diff = gemIndexValue(a.entry.gemIndex) - gemIndexValue(b.entry.gemIndex)
  if (diff !== 0) {
    return diff
  }
  return a.entry.lowerName < b.entry.lowerName ? -1 : a.entry.lowerName > b.entry.lowerName ? 1 : 0
}

/**
 * 1 シャードを読んでプールのエントリ配列にする。
 * 🔴 **読めなかった場合は `null`**（空配列と区別する）。呼び出し側が「全滅か部分成功か」を
 * 判定できなくなるため、失敗を空配列に潰さない。
 * 🔵 ここでは **tokenize しない**（`search` が来なければ不要なコストのため・第 2 段へ回す）。
 */
async function loadShard(
  read: AssetReader,
  fileName: string,
): Promise<readonly PoolEntry[] | null> {
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
  //    ここで必須にすると古い形のシャードでバッジまで落ちる。
  // 🔴 ただし **一覧の母集団からは外す**（`F-17`）。欠けた列を `''` / `0` で埋めた値を
  //    「★ 0 / 0 件」という事実として表示してしまうのは検証ではなく捏造（`ARCH-R1`）。
  const packageIndex = shard.columns.indexOf(COLUMN_PACKAGE_NAME)
  const dependentIndex = shard.columns.indexOf(COLUMN_DEPENDENT_COUNT)
  const starsIndex = shard.columns.indexOf(COLUMN_STARS)
  const listable = packageIndex >= 0 && dependentIndex >= 0 && starsIndex >= 0

  const entries: PoolEntry[] = []
  let malformedNames = 0
  for (const entry of shard.entries) {
    if (!Array.isArray(entry)) {
      continue
    }
    const fullName = entry[nameIndex]
    const value = entry[valueIndex]
    if (typeof fullName !== 'string' || fullName.length === 0) {
      continue
    }
    // 🔴 `owner/repo` の形でないものは入口で落とす（`F-09`）。`../settings` のような値が通ると
    //    詳細ページへのリンクが URL 正規化で別のページへ化け、項目名と遷移先が食い違う。
    if (!isSafeRepositoryFullName(fullName)) {
      malformedNames += 1
      continue
    }
    // 非有限数は `gemIndex()`（スマートコンストラクタ）が throw するため、ここで先に弾く。
    if (typeof value !== 'number' || !Number.isFinite(value)) {
      continue
    }

    entries.push({
      packageName: stringAt(entry, packageIndex),
      repositoryFullName: fullName,
      dependentCount: finiteAt(entry, dependentIndex),
      stars: finiteAt(entry, starsIndex),
      gemIndex: gemIndex(value),
      registry,
      lowerName: fullName.toLowerCase(),
      listable,
    })
  }

  if (!listable) {
    warn(
      `シャード ${fileName}（registry=${registry}）の columns に一覧用の列` +
        `（${COLUMN_PACKAGE_NAME} / ${COLUMN_DEPENDENT_COUNT} / ${COLUMN_STARS}）が揃っていません。` +
        `${entries.length} 件を Gem 一覧の母集団から除外し、所属判定（バッジ）にのみ使います。`,
    )
  }
  if (malformedNames > 0) {
    warn(
      `シャード ${fileName}（registry=${registry}）の repositoryFullName が` +
        ` owner/repo の形でないエントリを ${malformedNames} 件スキップしました。`,
    )
  }
  return entries
}

/**
 * `repositoryFullName` と `packageName` の単語を重複なく 1 本の配列に畳む。
 *
 * ⚠️ **`Set` を使わない**（実測・62,483 件の構築で `Set` 版 69.5ms → 配列版 48.8ms）。
 * 1 件あたりのトークンは平均 3.4 語しかなく、この規模では `Array#includes` の線形探索の方が
 * `Set` の確保・反復・配列化より速い。検索インデックス構築は CPU 予算に直接効くため、
 * 「小さい集合には素の配列」を意図して選んでいる（可読性ではなく実測に基づく選択）。
 */
function mergeTokens(repositoryFullName: string, packageName: string): readonly string[] {
  const tokens: string[] = []
  for (const token of tokenizeIdentifier(repositoryFullName)) {
    if (!tokens.includes(token)) {
      tokens.push(token)
    }
  }
  if (packageName.length > 0) {
    for (const token of tokenizeIdentifier(packageName)) {
      if (!tokens.includes(token)) {
        tokens.push(token)
      }
    }
  }
  return tokens
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
