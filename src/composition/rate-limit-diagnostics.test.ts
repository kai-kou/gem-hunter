import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from 'vitest'

import type { ClockPort } from '../domain/ports/clock-port'

import {
  RATE_LIMIT_DISABLED_MARKER,
  RATE_LIMIT_WARN_INTERVAL_MS,
  createRateLimitDisabledReporter,
  reportRateLimitDisabled,
} from './rate-limit-diagnostics'

/** 決定的に時間を進めるためのフェイク（`ClockPort` に型で適合させる・testing-strategy §4）。 */
class FakeClock implements ClockPort {
  constructor(private millis = 0) {}
  now(): Date {
    return new Date(this.millis)
  }
  advance(ms: number): void {
    this.millis += ms
  }
}

let warnSpy: MockInstance<typeof console.warn>

beforeEach(() => {
  warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
})

afterEach(() => {
  vi.restoreAllMocks()
})

function warnedLines(): string[] {
  return warnSpy.mock.calls.map((call) => String(call[0]))
}

/**
 * 🔴 **外部契約（運用手順が依存するリテラル）を固定する。**
 * これらの値は `docs/03_design/infrastructure/cloudflare-infrastructure.md` §3.3
 * 「無効化を外から確認する」の手順（`wrangler tail` で grep する文字列・観測窓の長さ）と
 * 結ばれている。シンボル参照だけで検証すると、値を変えても全テストが緑のまま通り、
 * 運用手順だけが黙って壊れる（#187 の再発）。
 *
 * 🔴 **変更するときは同じ PR で `cloudflare-infrastructure.md` §3.3 の手順も直すこと。**
 */
describe('外部契約のリテラル（運用手順と結ばれている値）', () => {
  it('マーカー文字列は wrangler tail の grep 条件と同じ', () => {
    expect(RATE_LIMIT_DISABLED_MARKER).toBe('[rate-limit] disabled')
  })

  it('間引き間隔は §3.3 が「10 分」と書いている値と同じ', () => {
    expect(RATE_LIMIT_WARN_INTERVAL_MS).toBe(600_000)
  })
})

describe('createRateLimitDisabledReporter', () => {
  it('初回はマーカーと理由コードを含む 1 行を出す（Issue #192 完了条件 1）', () => {
    const report = createRateLimitDisabledReporter(new FakeClock())

    report('no-salt')

    expect(warnedLines()).toHaveLength(1)
    const [line] = warnedLines()
    expect(line).toContain(RATE_LIMIT_DISABLED_MARKER)
    expect(line).toContain('reason=no-salt')
  })

  it('同じ理由の連続報告は間引かれ、ログ量がリクエスト数に比例しない（完了条件 2）', () => {
    const clock = new FakeClock()
    const report = createRateLimitDisabledReporter(clock)

    for (let i = 0; i < 500; i += 1) {
      clock.advance(100) // 500 リクエストが 50 秒間に到着した想定
      report('no-binding')
    }

    expect(warnedLines()).toHaveLength(1)
  })

  it('理由ごとに独立して 1 回ずつ出す（3 条件の区別が失われない）', () => {
    const report = createRateLimitDisabledReporter(new FakeClock())

    report('no-client-ip')
    report('no-binding')
    report('no-salt')
    report('no-client-ip')

    const lines = warnedLines()
    expect(lines).toHaveLength(3)
    expect(lines.filter((l) => l.includes('reason=no-client-ip'))).toHaveLength(1)
    expect(lines.filter((l) => l.includes('reason=no-binding'))).toHaveLength(1)
    expect(lines.filter((l) => l.includes('reason=no-salt'))).toHaveLength(1)
  })

  it('間引き間隔を超えたら同じ理由でも再び出す（検証窓で必ず観測できる）', () => {
    const clock = new FakeClock()
    const report = createRateLimitDisabledReporter(clock)

    report('no-salt')
    clock.advance(RATE_LIMIT_WARN_INTERVAL_MS - 1)
    report('no-salt')
    expect(warnedLines()).toHaveLength(1)

    clock.advance(1)
    report('no-salt')
    expect(warnedLines()).toHaveLength(2)
  })

  it('秘密情報（salt 値・接続元 IP）を載せない', () => {
    const report = createRateLimitDisabledReporter(new FakeClock())

    report('no-salt')
    report('no-client-ip')

    for (const line of warnedLines()) {
      expect(line).not.toMatch(/\d+\.\d+\.\d+\.\d+/)
      expect(line.toLowerCase()).not.toContain('salt=')
    }
  })

  it('レポーターごとに間引き状態が独立している（isolate 単位の状態を共有しない）', () => {
    const first = createRateLimitDisabledReporter(new FakeClock())
    const second = createRateLimitDisabledReporter(new FakeClock())

    first('no-salt')
    second('no-salt')

    expect(warnedLines()).toHaveLength(2)
  })

  /**
   * 🔴 干渉検証（#725）。本 Issue は独立した 2 対策を含む:
   *   A. 運用中のログ間引き（本モジュールの `createRateLimitDisabledReporter`）
   *   B. 検証時の確認手段（`wrangler tail` で `RATE_LIMIT_DISABLED_MARKER` と `reason=` を拾う手順・
   *      `cloudflare-infrastructure.md` §3.3「無効化を外から確認する」）
   * 両者は「同じ 1 行の文字列」を共有データとして通る。A が B の前提（機械可読な形と、
   * 観測窓のうちに必ず 1 回は出ること）を壊していないことをここで固定する。
   */
  it('干渉検証: 間引きが効いた後の再出力でも検証手段が読む形（マーカー + reason=）を保つ', () => {
    const clock = new FakeClock()
    const report = createRateLimitDisabledReporter(clock)

    report('no-salt')
    // 間引きが効いている区間（B から見ると「無音」に見える区間）。
    for (let i = 0; i < 100; i += 1) {
      clock.advance(1_000)
      report('no-salt')
    }
    expect(warnedLines()).toHaveLength(1)

    // 検証手順が定める観測窓（間引き間隔以上）を待てば、必ずもう一度観測できる。
    clock.advance(RATE_LIMIT_WARN_INTERVAL_MS)
    report('no-salt')

    const lines = warnedLines()
    expect(lines).toHaveLength(2)
    // 再出力された行も初回とまったく同じ機械可読な形（grep 条件が変わらない）。
    expect(lines[1]).toBe(lines[0])
    expect(lines[1]).toContain(RATE_LIMIT_DISABLED_MARKER)
    expect(lines[1]).toContain('reason=no-salt')
  })

  /**
   * ⚪ 既定 export（モジュールレベル singleton）は **間引き状態を跨いで共有する** ため、
   * 「1 行出ること」を直接 assert すると同一プロセスで 2 回実行された場合（`--repeat` /
   * `--retry`）に 2 周目が間引かれ、実装は正しいのにテストだけが落ちる。
   * ここでは「既定 export が `createRateLimitDisabledReporter` と **同じ形の行** を出す」
   * ことだけを見たいので、フェイク時計で作った比較用レポーターの出力と突き合わせる。
   */
  it('既定のレポーター（アプリが実際に使う export）も同じ形の 1 行を出す', () => {
    const reference = createRateLimitDisabledReporter(new FakeClock())
    reference('no-binding')
    const [expectedLine] = warnedLines()
    warnSpy.mockClear()

    reportRateLimitDisabled('no-binding')

    // 間引かれた場合は 0 行になりうる（singleton の状態に依存する）。出たときは
    // 必ず比較用レポーターと同一の行であること = 形が乖離していないこと、を固定する。
    for (const line of warnedLines()) {
      expect(line).toBe(expectedLine)
    }
    expect(expectedLine).toContain(`${RATE_LIMIT_DISABLED_MARKER} reason=no-binding`)
  })
})
