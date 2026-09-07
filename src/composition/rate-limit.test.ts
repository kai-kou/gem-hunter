import { afterEach, describe, expect, it, vi } from 'vitest'

import { RateLimitExceededError } from '../domain/errors'
import {
  RATE_LIMIT_DISABLED_MARKER,
  createRateLimitDisabledReporter,
  type RateLimitDisabledReason,
} from './rate-limit-diagnostics'

const clientIpOf = vi.fn()
const hashRateLimitKey = vi.fn()
vi.mock('../infrastructure/platform/rate-limit-key', () => ({
  clientIpOf: (...args: unknown[]) => clientIpOf(...args),
  hashRateLimitKey: (...args: unknown[]) => hashRateLimitKey(...args),
}))

const rateLimiterBinding = vi.fn()
vi.mock('../infrastructure/platform/cloudflare-bindings', () => ({
  rateLimiterBinding: (...args: unknown[]) => rateLimiterBinding(...args),
}))

const consume = vi.fn()
const WorkersRateLimit = vi.fn().mockImplementation(function (this: { consume: typeof consume }) {
  this.consume = consume
})
vi.mock('../infrastructure/platform/rate-limit', () => ({
  RATE_LIMIT_PERIOD_SECONDS: 60,
  WorkersRateLimit,
}))

// mock 定義後に import する（vi.mock はホイストされるため import 順は問題ないが明示のため最後に置く）。
const { enforceSearchRateLimit, enforceGemListRateLimit, enforceDetailRateLimit } =
  await import('./rate-limit')

const HEADERS = new Headers()
const IP = '203.0.113.1'
const SALT = 'test-salt'
const BINDING = { limit: vi.fn() }

/**
 * 🔴 診断レポーターは **`vi.mock` で差し替えない**（`testing-strategy.md` §4:
 * 「`vi.mock` で自作モジュールを差し替えたくなったら依存性注入ができていないサイン」）。
 * `enforceRateLimit` の第 2 引数 `deps.report` へ手書きフェイクを注入する。
 *
 * 引数を **rest で丸ごと記録** するのが要点。理由コード 1 個だけを記録すると、将来
 * `report('no-salt', ip)` のように引数を広げて秘密情報を渡す変更が入っても記録に残らず、
 * 「秘密情報を渡していない」という assert が恒真化する（PR #1044 セルフレビュー指摘）。
 */
function createReportFake(): {
  calls: unknown[][]
  report: (reason: RateLimitDisabledReason) => void
} {
  const calls: unknown[][] = []
  // `satisfies` で本番のレポーター型に適合させる（契約が変わればここが型エラーになる）。
  const report = ((...args: unknown[]): void => {
    calls.push(args)
  }) satisfies (reason: RateLimitDisabledReason) => void
  return { calls, report }
}

// 🔴 フェイルオープンした事実が **必ず記録される**（Issue #192）ことと、有効な環境では
// 1 件も記録されないことの両方が検証対象なので、素通し系・正常系ともに毎回検証する。
// 間引き（同一理由の抑制）の責務は `rate-limit-diagnostics.ts` 側にあり、本ファイルは
// 「どの分岐がどの理由コードを報告するか」という配線だけを固定する。
const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})

afterEach(() => {
  vi.clearAllMocks()
  vi.unstubAllEnvs()
})

/**
 * `enforceSearchRateLimit` / `enforceGemListRateLimit` は同じ `enforceRateLimit` の
 * 1 行ラッパーであり、フェイルオープン条件と consume の呼び方は完全に共通。
 * 逐語コピーで 2 本持つと、条件を 1 つ変えるたびに二重修正が必要になり、
 * 片側だけ更新した瞬間に「両経路を独立に検証している」という見かけと実態が乖離するため、
 * 共通仕様は表駆動でまとめて回す（接頭辞だけをパラメータ化する）。
 */
type EnforceCase = [
  name: string,
  enforce: (
    headers: Headers,
    deps?: { report?: (reason: RateLimitDisabledReason) => void },
  ) => Promise<void>,
  expectedPrefix: string,
]

const ENFORCE_CASES: EnforceCase[] = [
  ['enforceSearchRateLimit', enforceSearchRateLimit, 'search:'],
  ['enforceGemListRateLimit', enforceGemListRateLimit, 'gems:'],
  ['enforceDetailRateLimit', enforceDetailRateLimit, 'detail:'],
]

describe.each(ENFORCE_CASES)('%s', (_name, enforce, expectedPrefix) => {
  it('IP が取れないなら素通りし、理由 no-client-ip を記録する（binding も取りに行かない）', async () => {
    const { calls, report } = createReportFake()
    clientIpOf.mockReturnValue(null)
    vi.stubEnv('RATE_LIMIT_SALT', SALT)

    await expect(enforce(HEADERS, { report })).resolves.toBeUndefined()

    expect(rateLimiterBinding).not.toHaveBeenCalled()
    expect(consume).not.toHaveBeenCalled()
    expect(calls).toEqual([['no-client-ip']])
  })

  it('binding 未提供なら素通りし、理由 no-binding を記録する（Issue #192）', async () => {
    const { calls, report } = createReportFake()
    clientIpOf.mockReturnValue(IP)
    vi.stubEnv('RATE_LIMIT_SALT', SALT)
    rateLimiterBinding.mockResolvedValue(undefined)

    await expect(enforce(HEADERS, { report })).resolves.toBeUndefined()

    expect(consume).not.toHaveBeenCalled()
    expect(calls).toEqual([['no-binding']])
  })

  // 旧テスト「RATE_LIMIT_SALT 未設定なら素通り（binding も取りに行かない）」の後継。
  // 旧テストは「salt が無いなら binding 取得のコストも払わない」という順序（salt → binding）を
  // 固定していたが、その順序では **Workers 上で salt だけ落ちた設定不備** が
  // 「binding 未提供のローカル実行」と区別できず、両経路が無音で全面無効化される。
  // 判定順を binding → salt に入れ替えたため、本ケースが固定する意図も
  // 「取得コストを払わないこと」から「binding 無しの環境は no-binding として切り分けられること」
  // へ変わった（Issue #192: salt の設定不備と実行環境の違いを取り違えない）。
  it('binding 未提供のときは salt 未設定でも理由は no-binding 1 件だけ（実行環境と設定不備を混同しない）', async () => {
    const { calls, report } = createReportFake()
    clientIpOf.mockReturnValue(IP)
    vi.stubEnv('RATE_LIMIT_SALT', '')
    rateLimiterBinding.mockResolvedValue(undefined)

    await expect(enforce(HEADERS, { report })).resolves.toBeUndefined()

    expect(consume).not.toHaveBeenCalled()
    expect(calls).toEqual([['no-binding']])
  })

  it('binding があるのに RATE_LIMIT_SALT 未設定なら素通りし、理由 no-salt を記録する', async () => {
    const { calls, report } = createReportFake()
    clientIpOf.mockReturnValue(IP)
    vi.stubEnv('RATE_LIMIT_SALT', '')
    rateLimiterBinding.mockResolvedValue(BINDING)

    await expect(enforce(HEADERS, { report })).resolves.toBeUndefined()

    expect(consume).not.toHaveBeenCalled()
    // 🔴 診断へ渡すのは理由コード **1 個だけ**。`toEqual` で引数列そのものを固定するので、
    //    `report('no-salt', ip)` のように引数を広げた瞬間にここが落ちる（恒真化しない）。
    expect(calls).toEqual([['no-salt']])
  })

  /**
   * 🔴 秘密情報の非漏洩は **実レポーターが `console.warn` した行** に対して検査する（PR #1044 指摘）。
   * 手書きフェイクの引数だけを見ると、`enforceRateLimit` 内で `console.warn` を直に呼んで
   * salt / IP を埋め込む変更を検知できない。ここでは salt（env）と IP（変数）が
   * 実際にスコープへ存在する 2 経路（`no-binding` / `no-salt`）を通したうえで出力行を見る。
   * レポーターはテストごとに新規生成する（間引き状態が空 = 必ず 1 行出る）。
   */
  it('診断の出力行に秘密情報（salt 値・接続元 IP）が現れない', async () => {
    const report = createRateLimitDisabledReporter()
    clientIpOf.mockReturnValue(IP)

    // 経路 1: IP 取得済み・env に salt あり・binding 無し（salt / IP ともスコープに存在）。
    vi.stubEnv('RATE_LIMIT_SALT', SALT)
    rateLimiterBinding.mockResolvedValue(undefined)
    await enforce(HEADERS, { report })

    // 経路 2: IP 取得済み・binding あり・salt 未設定（IP がスコープに存在）。
    vi.stubEnv('RATE_LIMIT_SALT', '')
    rateLimiterBinding.mockResolvedValue(BINDING)
    await enforce(HEADERS, { report })

    const lines = warnSpy.mock.calls.map((call) => String(call[0]))
    expect(lines).toHaveLength(2)
    for (const line of lines) {
      expect(line).toContain(RATE_LIMIT_DISABLED_MARKER)
      expect(line).not.toContain(SALT)
      expect(line).not.toMatch(/\d+\.\d+\.\d+\.\d+/)
    }
  })

  it('allowed: true なら素通りし、診断も警告も一切出さない（完了条件 3）', async () => {
    const { calls, report } = createReportFake()
    clientIpOf.mockReturnValue(IP)
    vi.stubEnv('RATE_LIMIT_SALT', SALT)
    rateLimiterBinding.mockResolvedValue(BINDING)
    hashRateLimitKey.mockResolvedValue('hashed-key')
    consume.mockResolvedValue({ allowed: true })

    await expect(enforce(HEADERS, { report })).resolves.toBeUndefined()

    expect(calls).toEqual([])
    expect(warnSpy).not.toHaveBeenCalled()
  })

  it('allowed: false なら RateLimitExceededError(rateLimitSecondary) を投げる', async () => {
    clientIpOf.mockReturnValue(IP)
    vi.stubEnv('RATE_LIMIT_SALT', SALT)
    rateLimiterBinding.mockResolvedValue(BINDING)
    hashRateLimitKey.mockResolvedValue('hashed-key')
    consume.mockResolvedValue({ allowed: false, retryAfterSeconds: 60 })

    const error = await enforce(HEADERS).catch((e) => e)

    expect(error).toBeInstanceOf(RateLimitExceededError)
    expect((error as RateLimitExceededError).kind).toBe('rateLimitSecondary')
    expect((error as RateLimitExceededError).retryAfterSeconds).toBe(60)
  })

  it('1 リクエストにつき consume を 1 回だけ、生 IP を含まない接頭辞付きキーで呼ぶ', async () => {
    clientIpOf.mockReturnValue(IP)
    vi.stubEnv('RATE_LIMIT_SALT', SALT)
    rateLimiterBinding.mockResolvedValue(BINDING)
    hashRateLimitKey.mockResolvedValue('hashed-key')
    consume.mockResolvedValue({ allowed: true })

    await enforce(HEADERS)

    expect(consume).toHaveBeenCalledTimes(1)
    const [calledKey] = consume.mock.calls[0] as [string]
    expect(calledKey).not.toContain(IP)
    expect(calledKey).toBe(`${expectedPrefix}hashed-key`)
    expect(hashRateLimitKey).toHaveBeenCalledWith(IP, SALT)
  })
})

// 🔴 この 1 本だけは表駆動化しない。共通実装を 3 経路から叩くのではなく
// 「3 経路を同時に使ったときにキーが衝突しない」ことを見るテストであり、
// 共通化後も意味を保つ唯一の検証（枠を分けるというユーザー裁定の実効性を固定する）。
describe('検索・Gem 一覧・詳細取得の枠は独立している（Issue #442 / #190 のユーザー裁定）', () => {
  it('同じ IP・同じ salt でも consume に渡るキーの接頭辞が異なる', async () => {
    clientIpOf.mockReturnValue(IP)
    vi.stubEnv('RATE_LIMIT_SALT', SALT)
    rateLimiterBinding.mockResolvedValue(BINDING)
    hashRateLimitKey.mockResolvedValue('hashed-key')
    consume.mockResolvedValue({ allowed: true })

    await enforceSearchRateLimit(HEADERS)
    await enforceGemListRateLimit(HEADERS)
    await enforceDetailRateLimit(HEADERS)

    expect(consume).toHaveBeenCalledTimes(3)
    const [searchKey] = consume.mock.calls[0] as [string]
    const [gemListKey] = consume.mock.calls[1] as [string]
    const [detailKey] = consume.mock.calls[2] as [string]

    expect(searchKey).toBe('search:hashed-key')
    expect(gemListKey).toBe('gems:hashed-key')
    expect(detailKey).toBe('detail:hashed-key')
    // 同一ハッシュでも接頭辞が違えば Cloudflare 側のカウンタは別枠になる。
    // ここが同じキーに退行すると「検索 → 詳細を開く」等の導線で枠を食い合う。
    expect(new Set([searchKey, gemListKey, detailKey]).size).toBe(3)
  })
})

/**
 * 既定の `deps`（引数を 1 つだけ渡す本番と同じ呼び方）で診断が実際に出ることを固定する。
 * 上のケース群は注入済みフェイクを見ているため、既定値が未配線（`deps.report` 未指定なら
 * 何もしない）へ退行しても全て緑のまま通ってしまう。ここだけが本番経路を守る。
 *
 * 🔵 `vi.resetModules()` + 動的 import で **既定レポーターの singleton を作り直す**
 * （間引き状態を空にする）。`--repeat` / `--retry` で 2 周目に間引かれて落ちるのを避ける。
 */
describe('既定の診断レポーターの配線（deps 省略時）', () => {
  it('deps を渡さない呼び出しでも [rate-limit] disabled が 1 行出る', async () => {
    vi.resetModules()
    const { enforceSearchRateLimit: freshEnforce } = await import('./rate-limit')
    clientIpOf.mockReturnValue(null)

    await expect(freshEnforce(HEADERS)).resolves.toBeUndefined()

    const lines = warnSpy.mock.calls.map((call) => String(call[0]))
    expect(lines).toHaveLength(1)
    expect(lines[0]).toContain(`${RATE_LIMIT_DISABLED_MARKER} reason=no-client-ip`)
  })
})
