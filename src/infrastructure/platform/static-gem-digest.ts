import type { DigestMeta, Gem } from '../../domain/model/gem'
import { gemIndex } from '../../domain/model/gem-index'
import type { GemDigestPort } from '../../domain/ports/gem-digest-port'

import digestJson from '../../../public/data/daily-digest.json'

/**
 * ダイジェスト候補プールの静的 JSON 実装（`SP-14` / `ADR 0014` §2.2 / `D-28` 訂正注記）。
 *
 * 🔴 **配信手段は Cloudflare Workers Static Assets**（`public/data/daily-digest.json` を
 * デプロイで丸ごと差し替える）。ここではその **同一の内容を Next.js のバンドル取り込み**
 * （`import` + `resolveJsonModule`）でも読み込める形にする。SSR / RSC 経路では
 * バンドル側から即時に返せて `fetch` の失敗経路（HTTP ステータス・タイムアウト）を持ち込まず、
 * `open-questions.md` D-28 の「Worker がそのファイルへ実行時に書き込むか」で No 側を維持する
 * （読み取り専用の静的アセット）。バッチ生成の主体は `tools/generate_gem_digest.mjs`。
 *
 * 🔴 **例外を投げない（設計判断・`GemDigestPort` の契約）**: `listCandidates()` は不正な入力でも
 * throw せず、**不正な個別エントリはスキップ**・**meta の不正フィールドは既定値へフォールバック**
 * する。バッチ（`D-28` の SPOF）が壊れた JSON を配置しても、トップページは
 * 「鮮度が落ちる / 件数が減る」だけで描画され続ける（配信自体は止めない）。
 * テスト用にソースを注入した場合も **同じスキップ方式で動かす**（本番と挙動を分けると、
 * テストが検証しているのが本番経路ではなくなるため）。
 */

/** 入力 JSON のトップレベル形（バリデーション前の生値）。 */
type RawDigestJson = {
  readonly date?: unknown
  readonly meta?: unknown
  readonly candidates?: unknown
}

/** 1 件の Gem 候補（バリデーション前の生値）。 */
type RawCandidate = {
  readonly packageName?: unknown
  readonly repositoryFullName?: unknown
  readonly dependentCount?: unknown
  readonly stars?: unknown
  readonly gemIndex?: unknown
}

/**
 * `meta` が読めなかったときの既定値（`D-29` の帰属表示は省略できないため空にはしない）。
 *
 * バッチ（`tools/generate_gem_digest.mjs`）が書き込む出典は常に Ecosyste.ms / CC BY-SA 4.0 で
 * 固定なので、静的に既知の値へ倒す。`generatedAt` だけは推測できないため空文字にし、
 * 表示側（`AttributionNotice`）が生成時刻なしとして扱う。
 */
/**
 * 候補プールが読めない / 壊れているときに使う帰属メタデータ。`D-29` の帰属表示は省略できないため、
 * フォールバック時も出典・ライセンスは保持し `generatedAt` だけを空にする。
 */
export const FALLBACK_META: DigestMeta = {
  source: 'Ecosyste.ms',
  sourceUrl: 'https://ecosyste.ms/',
  license: 'CC BY-SA 4.0',
  sourceLicenseUrl: 'https://creativecommons.org/licenses/by-sa/4.0/',
  generatedAt: '',
}

/**
 * `owner/repo` の厳格判定。`includes('/')` だけでは `owner/` `/repo` `a/b/c` `owner repo`
 * `../..` が通過し、詳細ページのリンクが 404 になる（`AC-4`）。
 */
const REPOSITORY_FULL_NAME_PATTERN = /^[^/\s]+\/[^/\s]+$/

export class StaticGemDigest implements GemDigestPort {
  /**
   * ソース JSON を差し替えたい場合（テスト用）に受け取れるようにしておく。
   * 引数を省略すると本番の `public/data/daily-digest.json` を使う。
   */
  constructor(private readonly source: unknown = digestJson) {}

  async listCandidates(): Promise<{ candidates: readonly Gem[]; meta: DigestMeta }> {
    return parseDigest(this.source)
  }
}

/** JSON 全体を検証して Gem / DigestMeta の shape に落とす（不正は握って落とす・throw しない）。 */
function parseDigest(raw: unknown): { candidates: readonly Gem[]; meta: DigestMeta } {
  if (!isObject(raw)) {
    warn('候補プール JSON がオブジェクトではありません。空の候補プールとして継続します。')
    return { candidates: [], meta: FALLBACK_META }
  }
  const source = raw as RawDigestJson

  const meta = parseMeta(source.meta, {
    notObjectWarning:
      '候補プール JSON の meta が読めません。既定の帰属表示へフォールバックします。',
    logFieldWarnings: true,
  })
  const candidatesRaw = source.candidates
  if (!Array.isArray(candidatesRaw)) {
    warn('候補プール JSON の candidates が配列ではありません。空の候補プールとして継続します。')
    return { candidates: [], meta }
  }

  const candidates = candidatesRaw
    .map((entry, index) => tryParseCandidate(entry, index))
    .filter((gem): gem is Gem => gem !== null)

  return { candidates, meta }
}

/**
 * `parseMeta` の呼び出し元ごとのオプション。呼び出し元（`static-gem-digest.ts` /
 * `static-gem-index.ts`）でログの文言・要否が異なるため、統合にあたって差し替え可能にした
 * （重複解消・PR #141 系レビュー指摘の姉妹対応。`static-gem-index.ts` 側は元々フィールド単位の
 * warn ログを出していなかったため、`logFieldWarnings` の既定値 `false` でその挙動を保つ）。
 */
interface ParseMetaOptions {
  /** `meta` 自体がオブジェクトでない場合に出す警告メッセージ（呼び出し元ごとに文言が異なる）。 */
  readonly notObjectWarning: string
  /** 警告出力に使う関数。省略時はこのモジュールの `warn`（`[StaticGemDigest]` プレフィックス）。 */
  readonly warn?: (message: string) => void
  /** フィールド単位のフォールバック発生時にも警告を出すか（既定 false）。 */
  readonly logFieldWarnings?: boolean
}

/**
 * `index.json` / `daily-digest.json` の `meta` を出典表示（`D-29`）へ落とす。フィールド単位で
 * フォールバックする（1 つ壊れても他の帰属情報は活かす）。`static-gem-index.ts` と共有する
 * （既定値は `StaticGemDigest` と同じもの・出典/ライセンスは同一バッチが書く固定値なので、
 * 2 か所に別々の既定を置かない）。
 */
export function parseMeta(raw: unknown, options: ParseMetaOptions): DigestMeta {
  const log = options.warn ?? warn
  if (!isObject(raw)) {
    log(options.notObjectWarning)
    return FALLBACK_META
  }
  const source = raw as Partial<Record<keyof DigestMeta, unknown>>
  const fieldLog = options.logFieldWarnings ? log : undefined

  return {
    source: nonEmptyStringOr(source.source, FALLBACK_META.source, 'meta.source', fieldLog),
    // 🔴 `javascript:` / `data:` スキームは `<a href>` へ流さない（React 19 は
    //    `javascript:` href でレンダリング例外を投げ、ホーム画面全体が 500 になる）。
    sourceUrl: httpUrlOr(source.sourceUrl, FALLBACK_META.sourceUrl, 'meta.sourceUrl', fieldLog),
    license: nonEmptyStringOr(source.license, FALLBACK_META.license, 'meta.license', fieldLog),
    sourceLicenseUrl: httpUrlOr(
      source.sourceLicenseUrl,
      FALLBACK_META.sourceLicenseUrl,
      'meta.sourceLicenseUrl',
      fieldLog,
    ),
    generatedAt: nonEmptyStringOr(
      source.generatedAt,
      FALLBACK_META.generatedAt,
      'meta.generatedAt',
      fieldLog,
    ),
  }
}

/** 1 件の候補を検証する。1 つでも条件を満たさなければ `null`（= その 1 件だけスキップ）。 */
function tryParseCandidate(raw: unknown, index: number): Gem | null {
  if (!isObject(raw)) {
    return skip(index, '候補エントリがオブジェクトではありません')
  }
  const entry = raw as RawCandidate

  if (typeof entry.packageName !== 'string' || entry.packageName.length === 0) {
    return skip(index, 'packageName が非空の文字列ではありません')
  }
  if (
    typeof entry.repositoryFullName !== 'string' ||
    !isRepositoryFullName(entry.repositoryFullName)
  ) {
    return skip(index, 'repositoryFullName が owner/repo 形式ではありません')
  }
  if (typeof entry.dependentCount !== 'number' || !Number.isFinite(entry.dependentCount)) {
    return skip(index, 'dependentCount が有限数ではありません')
  }
  if (typeof entry.stars !== 'number' || !Number.isFinite(entry.stars)) {
    return skip(index, 'stars が有限数ではありません')
  }
  if (typeof entry.gemIndex !== 'number' || !Number.isFinite(entry.gemIndex)) {
    // `gemIndex()`（スマートコンストラクタ）は非有限数で throw するため、ここで先に弾く。
    return skip(index, 'gemIndex が有限数ではありません')
  }

  return {
    packageName: entry.packageName,
    repositoryFullName: entry.repositoryFullName,
    dependentCount: entry.dependentCount,
    stars: entry.stars,
    gemIndex: gemIndex(entry.gemIndex),
  }
}

/** `owner/repo` 形式か（スラッシュ 1 個・空白なし・`.` / `..` セグメントなし）。 */
function isRepositoryFullName(value: string): boolean {
  if (!REPOSITORY_FULL_NAME_PATTERN.test(value)) {
    return false
  }
  return value.split('/').every((segment) => segment !== '.' && segment !== '..')
}

function nonEmptyStringOr(
  value: unknown,
  fallback: string,
  field: string,
  log: ((message: string) => void) | undefined,
): string {
  if (typeof value === 'string' && value.length > 0) {
    return value
  }
  log?.(`候補プール JSON の ${field} が読めません。既定値へフォールバックします。`)
  return fallback
}

/** `http:` / `https:` のみ許可する（スキーム経由の XSS・レンダリング例外を入口で止める）。 */
function httpUrlOr(
  value: unknown,
  fallback: string,
  field: string,
  log: ((message: string) => void) | undefined,
): string {
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
  log?.(`候補プール JSON の ${field} が http(s) URL ではありません。既定値へフォールバックします。`)
  return fallback
}

function skip(index: number, reason: string): null {
  warn(`候補プール JSON の candidates[${index}] をスキップしました: ${reason}`)
  return null
}

function warn(message: string): void {
  console.warn(`[StaticGemDigest] ${message}`)
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
