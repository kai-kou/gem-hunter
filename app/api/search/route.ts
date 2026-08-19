import type { NextRequest } from 'next/server'
import { searchRepositoriesWithCacheStatus } from '@/src/composition/container'
import { DomainError, DomainValidationError, NotFoundError, RateLimitExceededError, UpstreamError } from '@/src/domain/errors'
import { searchKeyword } from '@/src/domain/model/search-keyword'
import { formatMessage } from '@/src/shared/i18n/format-message'
import { getMessages } from '@/src/shared/i18n/messages'
import { parseSearchParams, SEARCH_PARAM_KEYS } from '@/src/ui/url/search-params'

/**
 * SP-5: `X-Cache-Status`（`HIT` | `MISS`）を観測できる検索エンドポイント。
 *
 * 画面（`app/[locale]/page.tsx`）の SSR 応答にはこのヘッダを載せられない
 * （`AsyncLocalStorage` 案が実機検証で不成立・whiteboard round 3 lead 裁定）ため、
 * この Route Handler がキャッシュ状態を外部から観測する唯一の経路になる
 * （`docs/03_design/infrastructure/cloudflare-infrastructure.md` §4.5）。
 *
 * クエリパラメータ名は画面と同じ契約（`src/ui/url/search-params.ts` の `SEARCH_PARAM_KEYS`）を使う。
 *
 * 🟡 **このエンドポイントの用途（PR #120 セルフレビュー指摘・修正4）**: ドメイン型
 * （`SearchResult`）をそのまま JSON で返しており、外部公開 API としての後方互換を約束する
 * ものではない。用途は上記の `X-Cache-Status` 観測・検証（キャッシュ挙動の結合テスト・手動確認）
 * に限定する。レスポンス形状を安定契約にしたくなったら、DTO 変換層を別途追加する
 * （現時点では 1 呼び出し元しかなく先回りの抽象化は避ける・YAGNI）。
 */
export async function GET(request: NextRequest) {
  // API 応答のメッセージ言語: このエンドポイントは locale セグメントを持たない（`/api/search` は
  // `/[locale]/...` の外）。プロジェクトは日本語運用（CLAUDE.md「応答スタイル」）のため 'ja' 固定とする
  // （実装手段の選択であり仕様分岐ではない・`SD-3`）。
  const messages = getMessages('ja')
  // クエリ解釈を画面（page.tsx）と同じ `parseSearchParams` に一本化する（PR #120 セルフレビュー
  // 指摘・修正3・二重管理の解消）。`URLSearchParams` はブラケット記法での添字アクセス
  // （`params['q']`）を `.get('q')` のようには解決しない（未定義を返す）ため、
  // `parseSearchParams` が期待する `RawSearchParams`（プレーンオブジェクト）へ変換してから渡す。
  // `Object.fromEntries(searchParams.entries())` は重複キー（`?q=a&q=b`）で最後の値が勝つが
  // `URLSearchParams.get()`（従来の抽出方法）は最初の値を返すため、ここでは最初の出現だけを
  // 採用するループで変換し、重複キー時の挙動を変えない。
  const rawParams: Record<string, string> = {}
  for (const [key, value] of request.nextUrl.searchParams) {
    if (!(key in rawParams)) {
      rawParams[key] = value
    }
  }
  const { page } = parseSearchParams(rawParams)

  try {
    // 値オブジェクトへの変換は境界（ここ）で行う（domain-model.md §4 / ARCH-R2）。
    // 画面（page.tsx）は空キーワードを「idle 状態」として黙って許すが、JSON API に
    // idle 相当の応答は無いため、ここでは throw する `searchKeyword` を使って
    // DomainValidationError に倒し、下の catch で画面と同じ整形（formatMessage +
    // messages.home.searchError）に載せる。
    //
    // 🔴 keyword は `parseSearchParams` が返す既に正規化済みの文字列（`trySearchKeyword` が
    // 不正値を `''` へ倒した後の値）ではなく、`rawParams` の生の値をそのまま `searchKeyword`
    // に渡す。`parseSearchParams` の出力を経由すると、たとえば 256 文字超のキーワードが
    // 「空文字列」に潰され、`DomainValidationError` のメッセージが「検索キーワードを
    // 入力してください」（空欄用）にすり替わってしまう（本来は「256 文字以内で」の方）。
    // これは `parseSearchParams` が「不正値は例外を投げず既定値へ倒す」設計（画面の idle
    // 表示用）のためで、API のエラーメッセージ精度とは要件が異なる。よってキー名の契約
    // （`SEARCH_PARAM_KEYS` 経由で `parseSearchParams` に一本化）は共有しつつ、キーワードの
    // 生値だけは `rawParams` から直接取り出す（page.tsx にはこの精度要件がないため
    // `parseSearchParams` の page 解決はそのまま利用する）。
    const rawKeyword = rawParams[SEARCH_PARAM_KEYS.keyword] ?? ''
    const keyword = searchKeyword(rawKeyword)

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
      const headers = new Headers()
      if (error instanceof RateLimitExceededError && error.retryAfter) {
        // `Retry-After` は秒数（delta-seconds）と HTTP-date のどちらでも仕様上有効
        // （RFC 9110 §10.2.3）。`RateLimitExceededError.retryAfter` は既に絶対時刻
        // （GitHub のレート制限リセット時刻）を持つ `Date` なので、"今" を計算に持ち込む
        // 秒数変換（クロックの注入が余分に要る）より HTTP-date 形式（`toUTCString()`）の
        // ほうが素直で情報も落ちない。
        headers.set('Retry-After', error.retryAfter.toUTCString())
      }
      return Response.json(
        { error: formatMessage(messages.home.searchError, { message: error.message }) },
        { status: domainErrorStatus(error), headers },
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
