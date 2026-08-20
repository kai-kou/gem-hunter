import { DomainValidationError } from '../../domain/errors'
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

export class StaticGemDigest implements GemDigestPort {
  /**
   * ソース JSON を差し替えたい場合（テスト用）に受け取れるようにしておく。
   * 引数を省略すると本番の `public/data/daily-digest.json` を使う。
   */
  constructor(private readonly source: unknown = digestJson) {}

  async listCandidates(): Promise<{ candidates: readonly Gem[]; meta: DigestMeta }> {
    const parsed = parseDigest(this.source)
    return {
      candidates: parsed.candidates,
      meta: parsed.meta,
    }
  }
}

/** JSON 全体を検証して Gem / DigestMeta の shape に落とす。 */
function parseDigest(raw: unknown): { candidates: readonly Gem[]; meta: DigestMeta } {
  if (!isObject(raw)) {
    throw new DomainValidationError(
      'DailyDigestJson',
      raw,
      '候補プール JSON はオブジェクトである必要があります',
    )
  }
  const source = raw as RawDigestJson

  const meta = parseMeta(source.meta)
  const candidatesRaw = source.candidates
  if (!Array.isArray(candidatesRaw)) {
    throw new DomainValidationError(
      'DailyDigestJson.candidates',
      candidatesRaw,
      'candidates は配列である必要があります',
    )
  }

  const candidates: Gem[] = candidatesRaw.map((entry, index) => parseCandidate(entry, index))
  return { candidates, meta }
}

function parseMeta(raw: unknown): DigestMeta {
  if (!isObject(raw)) {
    throw new DomainValidationError('DigestMeta', raw, 'meta はオブジェクトである必要があります')
  }
  const source = raw as Partial<Record<keyof DigestMeta, unknown>>
  const source_ = source.source
  const license = source.license
  const sourceLicenseUrl = source.sourceLicenseUrl
  const generatedAt = source.generatedAt

  if (
    typeof source_ !== 'string' ||
    typeof license !== 'string' ||
    typeof sourceLicenseUrl !== 'string' ||
    typeof generatedAt !== 'string'
  ) {
    throw new DomainValidationError(
      'DigestMeta',
      raw,
      'meta の source / license / sourceLicenseUrl / generatedAt は全て文字列で必須です（D-29 帰属表示）',
    )
  }
  return {
    source: source_,
    license,
    sourceLicenseUrl,
    generatedAt,
  }
}

function parseCandidate(raw: unknown, index: number): Gem {
  if (!isObject(raw)) {
    throw new DomainValidationError(
      `DailyDigestJson.candidates[${index}]`,
      raw,
      '候補エントリはオブジェクトである必要があります',
    )
  }
  const entry = raw as RawCandidate

  if (typeof entry.packageName !== 'string' || entry.packageName.length === 0) {
    throw new DomainValidationError(
      `DailyDigestJson.candidates[${index}].packageName`,
      entry.packageName,
      'packageName は非空の文字列である必要があります',
    )
  }
  if (typeof entry.repositoryFullName !== 'string' || !entry.repositoryFullName.includes('/')) {
    throw new DomainValidationError(
      `DailyDigestJson.candidates[${index}].repositoryFullName`,
      entry.repositoryFullName,
      'repositoryFullName は owner/repo 形式の文字列である必要があります',
    )
  }
  if (typeof entry.dependentCount !== 'number' || !Number.isFinite(entry.dependentCount)) {
    throw new DomainValidationError(
      `DailyDigestJson.candidates[${index}].dependentCount`,
      entry.dependentCount,
      'dependentCount は有限数である必要があります',
    )
  }
  if (typeof entry.stars !== 'number' || !Number.isFinite(entry.stars)) {
    throw new DomainValidationError(
      `DailyDigestJson.candidates[${index}].stars`,
      entry.stars,
      'stars は有限数である必要があります',
    )
  }
  if (typeof entry.gemIndex !== 'number') {
    throw new DomainValidationError(
      `DailyDigestJson.candidates[${index}].gemIndex`,
      entry.gemIndex,
      'gemIndex は数値である必要があります',
    )
  }

  return {
    packageName: entry.packageName,
    repositoryFullName: entry.repositoryFullName,
    dependentCount: entry.dependentCount,
    stars: entry.stars,
    gemIndex: gemIndex(entry.gemIndex),
  }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
