import type { NextRequest } from 'next/server'
import { decodeSessionCookie, SESSION_COOKIE_NAME } from '@/src/composition/auth'
import {
  GEM_INDEX_SEARCH_RATE_LIMIT_COST,
  searchRepositoriesWithCacheStatus,
} from '@/src/composition/container'
import { enforceSearchRateLimit } from '@/src/composition/rate-limit'
import { DomainError, type ErrorKind, RateLimitExceededError } from '@/src/domain/errors'
import { GEM_INDEX_SORT_ORDER } from '@/src/domain/model/sort-order'
import { searchKeyword } from '@/src/domain/model/search-keyword'
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
  const { page, sort } = parseSearchParams(rawParams)

  try {
    // 値オブジェクトへの変換は境界（ここ）で行う（domain-model.md §4 / ARCH-R2）。
    // 画面（page.tsx）は空キーワードを「idle 状態」として黙って許すが、JSON API に
    // idle 相当の応答は無いため、ここでは throw する `searchKeyword` を使って
    // DomainValidationError に倒し、下の catch で `kind: 'validation'` として返す。
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

    // Issue #122: 自リクエストの間引き（RateLimitPort）。不正な入力（400 で弾く分）で
    // 枠を消費しないよう `searchKeyword` の検証（値オブジェクト変換）の後に置き、
    // GitHub API を実際に叩く（`search()`）前に間引く。超過時は `RateLimitExceededError`
    // を投げ、下の catch → `errorResponse()` が 429 + `Retry-After` を返す（新しい分岐は足さない）。
    //
    // 🔴 PR #293 セルフレビュー指摘・修正②（レート増幅対策）: `sort=gem-index` は 1 リクエストで
    // 最大 `GEM_INDEX_SEARCH_RATE_LIMIT_COST` 回の上流呼び出しに増幅しうるため、その回数ぶんを
    // 消費コストとして渡す（`page.tsx` と同じ判定・単一の定義元）。
    await enforceSearchRateLimit(request.headers, {
      cost: sort === GEM_INDEX_SORT_ORDER ? GEM_INDEX_SEARCH_RATE_LIMIT_COST : undefined,
    })

    // SP-8: セッション Cookie があればユーザー自身のレート枠で検索する（AR-5）。
    // このエンドポイントは元々 X-Cache-Status 観測・検証専用（用途はファイル冒頭コメント参照）
    // であり、レート枠切替（T-7・composition/container.ts の TokenProvider 差し替え）を
    // 外部から観測できる唯一の経路として流用する（実装手段の選択・SD-3 対象外）。
    const sessionCookie = request.cookies.get(SESSION_COOKIE_NAME)?.value
    const session = sessionCookie ? await decodeSessionCookie(sessionCookie) : null

    const { search, getCacheStatus } = searchRepositoriesWithCacheStatus(session?.accessToken)
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
