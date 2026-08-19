import type { NextRequest } from 'next/server'
import { searchRepositoriesWithCacheStatus } from '@/src/composition/container'
import { DomainError, DomainValidationError, NotFoundError, RateLimitExceededError, UpstreamError } from '@/src/domain/errors'
import { tryPageNumber } from '@/src/domain/model/page-number'
import { searchKeyword } from '@/src/domain/model/search-keyword'
import { formatMessage } from '@/src/shared/i18n/format-message'
import { getMessages } from '@/src/shared/i18n/messages'
import { SEARCH_PARAM_KEYS } from '@/src/ui/url/search-params'

/**
 * SP-5: `X-Cache-Status`（`HIT` | `MISS`）を観測できる検索エンドポイント。
 *
 * 画面（`app/[locale]/page.tsx`）の SSR 応答にはこのヘッダを載せられない
 * （`AsyncLocalStorage` 案が実機検証で不成立・whiteboard round 3 lead 裁定）ため、
 * この Route Handler がキャッシュ状態を外部から観測する唯一の経路になる
 * （`docs/03_design/infrastructure/cloudflare-infrastructure.md` §4.5）。
 *
 * クエリパラメータ名は画面と同じ契約（`src/ui/url/search-params.ts` の `SEARCH_PARAM_KEYS`）を使う。
 */
export async function GET(request: NextRequest) {
  // API 応答のメッセージ言語: このエンドポイントは locale セグメントを持たない（`/api/search` は
  // `/[locale]/...` の外）。プロジェクトは日本語運用（CLAUDE.md「応答スタイル」）のため 'ja' 固定とする
  // （実装手段の選択であり仕様分岐ではない・`SD-3`）。
  const messages = getMessages('ja')
  const { searchParams } = request.nextUrl
  const rawKeyword = searchParams.get(SEARCH_PARAM_KEYS.keyword) ?? ''
  const rawPage = searchParams.get(SEARCH_PARAM_KEYS.page)

  try {
    // 値オブジェクトへの変換は境界（ここ）で行う（domain-model.md §4 / ARCH-R2）。
    // 画面（page.tsx）は空キーワードを「idle 状態」として黙って許すが、JSON API に
    // idle 相当の応答は無いため、ここでは throw する `searchKeyword` を使って
    // DomainValidationError に倒し、下の catch で画面と同じ整形（formatMessage +
    // messages.home.searchError）に載せる。
    const keyword = searchKeyword(rawKeyword)
    const page = tryPageNumber(rawPage)

    const { search, getCacheStatus } = searchRepositoriesWithCacheStatus()
    const result = await search({ keyword, page })

    // getCacheStatus() が undefined になるのは `CachingRepositoryQuery` が
    // `onCacheStatus` を一度も呼ばずに正常終了した場合のみで、現行実装では起き得ない
    // （HIT/MISS のいずれかを必ず呼ぶ）。型上は undefined を許すため、観測できなかった
    // ケースを安全側（「キャッシュ未確認」）に倒し `MISS` として報告する。
    const cacheStatus = getCacheStatus() ?? 'MISS'

    return Response.json(result, {
      headers: { 'X-Cache-Status': cacheStatus },
    })
  } catch (error) {
    if (error instanceof DomainError) {
      return Response.json(
        { error: formatMessage(messages.home.searchError, { message: error.message }) },
        { status: domainErrorStatus(error) },
      )
    }
    // ドメインエラーでない想定外の例外は、生のメッセージを外へ出さず Next.js の
    // 既定エラーハンドリングに委ねる（page.tsx の catch と同じ方針・rethrow）。
    throw error
  }
}

function domainErrorStatus(error: DomainError): number {
  if (error instanceof DomainValidationError) {
    return 400
  }
  if (error instanceof RateLimitExceededError) {
    return 429
  }
  if (error instanceof NotFoundError) {
    return 404
  }
  if (error instanceof UpstreamError) {
    return 502
  }
  return 500
}
