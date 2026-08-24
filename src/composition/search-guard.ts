import { searchKeyword, type SearchKeyword } from '../domain/model/search-keyword'
import { enforceSearchRateLimit } from './rate-limit'

/**
 * composition root（Issue #604）。検索経路（画面 `app/[locale]/page.tsx` / API
 * `app/api/search/route.ts`）に重複していた「値オブジェクト変換 → 自リクエスト間引き
 * （Issue #122 の `RateLimitPort`）」という順序判断を 1 本へ集約する。
 *
 * 命名は `enforceSearchRateLimit`（同ファイル内の姉妹関数）に倣い、「検索の実行前に
 * 満たしておく前提条件」という語感で `prepare` を選んだ（`validateAndConsume` 等の
 * 実装詳細を名前に出す案より、呼び出し側から見た意図を表すほうがこのリポジトリの
 * 既存命名（`enforce*` / `complete*` 等、動詞 + 対象）に馴染むと判断）。
 *
 * 🔴 **順序が仕様**（元は両呼び出し元にそれぞれ書かれていたコメントをここへ集約）:
 * 1. 未入力（空キーワード）は呼び出し側が early return / idle 扱いする（`page.tsx` の
 *    `runSearch` 冒頭・`route.ts` の空文字列も含めた `searchKeyword` 呼び出し）ため、
 *    この関数に来る時点でレート枠を無条件に消費してよいわけではない。
 * 2. まず `searchKeyword()` で値オブジェクトへ変換する。不正なキーワード（修飾子入り・
 *    256 文字超・空白のみ等）は `DomainValidationError` を投げ、**この時点でレート枠を
 *    消費しない**（400 で弾かれる入力にまで枠を使わせない）。
 * 3. 変換が通った（＝ 400 にならない）キーワードだけを対象に `enforceSearchRateLimit()`
 *    を呼ぶ。超過時は `RateLimitExceededError` をそのまま伝播させ、呼び出し側の catch に
 *    委ねる（新しい分岐は足さない）。
 * 4. 上記いずれも GitHub API を実際に叩く前に完了させる。
 *
 * @param rawKeyword URL 由来の生キーワード（画面は `searchParams`、API は `rawParams` から）。
 * @param headers 接続元 IP 抽出に使う `Headers`（画面は `await headers()`、API は `request.headers`）。
 * @returns 変換済みの `SearchKeyword`。
 */
export async function prepareSearchKeyword(
  rawKeyword: string,
  headers: Headers,
): Promise<SearchKeyword> {
  const keyword = searchKeyword(rawKeyword)
  await enforceSearchRateLimit(headers)
  return keyword
}
