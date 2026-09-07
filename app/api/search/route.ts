import type { NextRequest } from 'next/server'
import { decodeSessionCookie, SESSION_COOKIE_NAME } from '@/src/composition/auth'
import {
  buildCacheObservationHeaders,
  searchRepositoriesWithCacheStatus,
} from '@/src/composition/container'
import { prepareSearchKeyword } from '@/src/composition/search-guard'
import { DomainError, type ErrorKind, RateLimitExceededError } from '@/src/domain/errors'
import { parseSearchParams, rawKeywordOf } from '@/src/ui/url/search-params'

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
    // 値オブジェクトへの変換は境界（ここ）で行う（domain-model.md §4 / ARCH-R2）。画面
    // （page.tsx）と異なり throw する `searchKeyword` を使い DomainValidationError に倒す
    // （下の catch で `kind: 'validation'`）。`parseSearchParams` 経由の正規化済み文字列
    // （不正値が `''` へ倒れ済み）ではなく `rawKeywordOf()` の生値を渡す（256 文字超などの
    // エラーメッセージ精度のため。既定値フォールバックの意味論は同関数の JSDoc を参照）。
    const rawKeyword = rawKeywordOf(rawParams)
    // 「変換 → Issue #122 の自リクエスト間引き（RateLimitPort）」の順序自体が仕様（不正な
    // 入力・400 で弾く分では枠を消費せず、GitHub API を実際に叩く前に間引く）で、この画面
    // （page.tsx）と重複していたため `prepareSearchKeyword`（composition root）へ集約した。
    // 超過時は `RateLimitExceededError` を投げ、下の catch → `errorResponse()` が 429 +
    // `Retry-After` を返す（新しい分岐は足さない）。理由の全文は同関数の JSDoc
    // （`src/composition/search-guard.ts`）を参照。
    const keyword = await prepareSearchKeyword(rawKeyword, request.headers)

    // SP-8: セッション Cookie があればユーザー自身のレート枠で検索する（AR-5）。
    // このエンドポイントは元々 X-Cache-Status 観測・検証専用（用途はファイル冒頭コメント参照）
    // であり、レート枠切替（T-7・composition/container.ts の TokenProvider 差し替え）を
    // 外部から観測できる唯一の経路として流用する（実装手段の選択・SD-3 対象外）。
    const sessionCookie = request.cookies.get(SESSION_COOKIE_NAME)?.value
    const session = sessionCookie ? await decodeSessionCookie(sessionCookie) : null

    const { search, getCacheStatus, getCacheLayer } = searchRepositoriesWithCacheStatus(
      session?.accessToken,
    )
    const result = await search({ keyword, page })

    // Issue #875: `X-Cache-Status`（後方互換で HIT/MISS のまま）・`X-Cache-Layer`（段の内訳）・
    // `X-Cache-Colo`（コロケーション）の組み立ては composition root へ委ねる
    // （`app/` に判断を持たせない・`application-architecture.md` §1.2）。
    const headers = await buildCacheObservationHeaders({
      cacheStatus: getCacheStatus(),
      cacheLayer: getCacheLayer(),
    })

    return Response.json(result, { headers })
  } catch (error) {
    if (error instanceof DomainError) {
      return errorResponse(error)
    }
    // ドメインエラーでない想定外の例外は、生のメッセージを外へ出さず Next.js の
    // 既定エラーハンドリングに委ねる（page.tsx の catch と同じ方針・rethrow）。
    throw error
  }
}

/**
 * 🔴 応答に載せるのは `ErrorKind`（prd.md §7）と再試行情報だけで、`error.message` は載せない
 * （message は開発者向けのログ用。内部情報を外へ出さない）。利用者向けの文言は受け取り側が
 * kind から i18n で引く。
 */
function errorResponse(error: DomainError): Response {
  const headers = new Headers()
  const body: { kind: ErrorKind; retryAfter?: string; retryAfterSeconds?: number } = {
    kind: error.kind,
  }

  if (error instanceof RateLimitExceededError) {
    // 🔴 上流の `x-ratelimit-reset` が壊れていると Invalid Date が渡りうる（ACL 側でも null へ
    //    倒しているが、ここでも防ぐ）。`toISOString()` は Invalid Date で RangeError を投げ、
    //    429 ではなく未処理例外の 500 になってしまうため、有効な Date のときだけ載せる。
    if (error.retryAfter && !Number.isNaN(error.retryAfter.getTime())) {
      // `Retry-After` は秒数（delta-seconds）と HTTP-date のどちらでも仕様上有効
      // （RFC 9110 §10.2.3）。一次レート制限の `retryAfter` は既に絶対時刻
      // （GitHub のレート制限リセット時刻）を持つ `Date` なので、"今" を計算に持ち込む
      // 秒数変換（クロックの注入が余分に要る）より HTTP-date 形式（`toUTCString()`）の
      // ほうが素直で情報も落ちない。
      headers.set('Retry-After', error.retryAfter.toUTCString())
      body.retryAfter = error.retryAfter.toISOString()
    } else if (error.retryAfterSeconds !== undefined) {
      // 二次レート制限は相対秒数しか分からない（`retry-after` 由来）ので、そのまま秒数で返す。
      headers.set('Retry-After', String(error.retryAfterSeconds))
      body.retryAfterSeconds = error.retryAfterSeconds
    }
  }

  return Response.json(body, { status: statusOf(error.kind), headers })
}

/** エラー種別 → HTTP ステータス（prd.md §7）。 */
function statusOf(kind: ErrorKind): number {
  switch (kind) {
    case 'validation':
      return 400
    case 'notFound':
      return 404
    case 'rateLimitPrimary':
    case 'rateLimitSecondary':
      return 429
    // 到達不可・認証/権限・上流異常は、いずれも利用者が入力で直せない上流側の問題
    // （認証エラーは内部情報を出さず汎用エラーとして扱う・prd.md §7）。
    case 'network':
    case 'auth':
    case 'upstream':
      return 502
  }
}
