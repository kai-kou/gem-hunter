/**
 * test-http-stubs.mjs — `collect.test.mjs` / `github-stars.test.mjs` で重複していた
 * Response 互換スタブ・fetch スタブの共有モジュール（テスト専用・Issue #950）。
 *
 * 🔴 テスト専用: アプリ側コード（`http-retry.mjs` 等）からは import しない。
 * `vi`（vitest）に依存するため、vitest 実行環境の外では使えない。
 */
import { vi } from 'vitest'

/**
 * 成功レスポンス（Response 互換の最小スタブ）。
 * @param {*} body `json()` が解決する値
 * @param {Record<string,string>} [headers]
 */
export function okResponse(body, headers = {}) {
  return { ok: true, status: 200, headers: new Headers(headers), json: async () => body }
}

/**
 * エラーレスポンス（Response 互換の最小スタブ）。
 * @param {number} status
 * @param {Record<string,string>} [headers]
 */
export function errorResponse(status, headers = {}) {
  return {
    ok: false,
    status,
    headers: new Headers(headers),
    json: async () => ({ error: `HTTP ${status}` }),
  }
}

/**
 * レスポンス列（1 リクエスト目から順の配列）を返す fetch スタブを作る。
 * 要素が `Error` インスタンスなら reject、Response 互換オブジェクトならそのまま解決する。
 * 用意した件数を超えて呼ばれたら例外を投げる（想定外の追加リクエストをテストで検知するため）。
 *
 * @param {ReadonlyArray<object|Error>} responses
 * @returns {{ fetchImpl: import('vitest').Mock, calls: {url:string, init:object}[] }}
 */
export function makeFetchImpl(responses) {
  const calls = []
  const fetchImpl = vi.fn(async (url, init) => {
    calls.push({ url: String(url), init })
    const next = responses[calls.length - 1]
    if (next === undefined) throw new Error(`想定外の追加リクエスト: ${url}`)
    if (next instanceof Error) throw next
    return next
  })
  return { fetchImpl, calls }
}

/**
 * `sleepImpl` のスタブ（実際には待機せず、待機ミリ秒だけ記録する）。
 * @returns {{ sleepImpl: import('vitest').Mock, waited: number[] }}
 */
export function makeSleepImpl() {
  const waited = []
  const sleepImpl = vi.fn(async (ms) => {
    waited.push(ms)
  })
  return { sleepImpl, waited }
}
