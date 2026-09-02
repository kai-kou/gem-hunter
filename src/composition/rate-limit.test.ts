import { afterEach, describe, expect, it, vi } from 'vitest'

import { RateLimitExceededError } from '../domain/errors'

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

// 警告の有無そのものが検証対象（Issue #442 のセルフレビュー指摘）なので、
// 素通し系のテストが「実は無音でなかった」ことを見逃さないよう常に spy を挟む。
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
  enforce: (headers: Headers) => Promise<void>,
  expectedPrefix: string,
]

const ENFORCE_CASES: EnforceCase[] = [
  ['enforceSearchRateLimit', enforceSearchRateLimit, 'search:'],
  ['enforceGemListRateLimit', enforceGemListRateLimit, 'gems:'],
  ['enforceDetailRateLimit', enforceDetailRateLimit, 'detail:'],
]

describe.each(ENFORCE_CASES)('%s', (_name, enforce, expectedPrefix) => {
  it('IP が取れないなら素通り（binding も取りに行かない・無音）', async () => {
    clientIpOf.mockReturnValue(null)
    vi.stubEnv('RATE_LIMIT_SALT', SALT)

    await expect(enforce(HEADERS)).resolves.toBeUndefined()

    expect(rateLimiterBinding).not.toHaveBeenCalled()
    expect(consume).not.toHaveBeenCalled()
    expect(warnSpy).not.toHaveBeenCalled()
  })

  it('binding 未提供なら素通り（無音）', async () => {
    clientIpOf.mockReturnValue(IP)
    vi.stubEnv('RATE_LIMIT_SALT', SALT)
    rateLimiterBinding.mockResolvedValue(undefined)

    await expect(enforce(HEADERS)).resolves.toBeUndefined()

    expect(consume).not.toHaveBeenCalled()
    expect(warnSpy).not.toHaveBeenCalled()
  })

  // 旧テスト「RATE_LIMIT_SALT 未設定なら素通り（binding も取りに行かない）」の後継。
  // 旧テストは「salt が無いなら binding 取得のコストも払わない」という順序（salt → binding）を
  // 固定していたが、その順序では **Workers 上で salt だけ落ちた設定不備** が
  // 「binding 未提供のローカル実行」と区別できず、両経路が無音で全面無効化される。
  // 判定順を binding → salt に入れ替えたため、本ケースが固定する意図も
  // 「取得コストを払わないこと」から「binding 無しの環境は依然として完全に無音であること」へ変わった。
  it('binding 未提供なら RATE_LIMIT_SALT 未設定でも完全に無音（ローカル実行を汚さない）', async () => {
    clientIpOf.mockReturnValue(IP)
    vi.stubEnv('RATE_LIMIT_SALT', '')
    rateLimiterBinding.mockResolvedValue(undefined)

    await expect(enforce(HEADERS)).resolves.toBeUndefined()

    expect(consume).not.toHaveBeenCalled()
    expect(warnSpy).not.toHaveBeenCalled()
  })

  it('binding があるのに RATE_LIMIT_SALT 未設定なら素通りしつつ警告を出す', async () => {
    clientIpOf.mockReturnValue(IP)
    vi.stubEnv('RATE_LIMIT_SALT', '')
    rateLimiterBinding.mockResolvedValue(BINDING)

    await expect(enforce(HEADERS)).resolves.toBeUndefined()

    expect(consume).not.toHaveBeenCalled()
    expect(warnSpy).toHaveBeenCalledTimes(1)
    const [warned] = warnSpy.mock.calls[0] as [string]
    expect(warned).toContain('RATE_LIMIT_SALT')
    // 秘密情報（salt 本体・接続元 IP）を警告に載せない。
    expect(warned).not.toContain(SALT)
    expect(warned).not.toContain(IP)
  })

  it('allowed: true なら素通り', async () => {
    clientIpOf.mockReturnValue(IP)
    vi.stubEnv('RATE_LIMIT_SALT', SALT)
    rateLimiterBinding.mockResolvedValue(BINDING)
    hashRateLimitKey.mockResolvedValue('hashed-key')
    consume.mockResolvedValue({ allowed: true })

    await expect(enforce(HEADERS)).resolves.toBeUndefined()

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
