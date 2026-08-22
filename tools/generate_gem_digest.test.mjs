/**
 * generate_gem_digest.mjs（CLI）のユニットテスト（`SP-17` / Issue #387）。
 *
 * ここで固定するのは **出荷値と契約** にゃ:
 * - CLI の既定値（`D-37` の決定ログが採用値として記録した `minStars=5` / `high-dependent-rank=100`）
 * - `buildPool()` へ渡すオプションの **キー名**（取り違えるとモジュール既定へ静かに落ちて汚染が復活する）
 * - 引数エラーが例外になること
 * - 部分実行時に配信データを書き換えない判定
 *
 * ⚠️ import した時点で `main()` が走らないこと（実 API を叩かないこと）も、本ファイルが
 * import できている事実そのもので担保している。
 */
import { describe, expect, it } from 'vitest'

import {
  DEFAULT_DIGEST_LIMIT,
  DEFAULT_DIGEST_OUT,
  DEFAULT_HIGH_DEPENDENT_RANK,
  DEFAULT_MIN_STARS,
  DEFAULT_OUT_DIR,
  DEFAULT_PER_PAGE,
  DEFAULT_QUOTA,
  decideOutputWrite,
  parseArgs,
  selectOrphanShards,
  toBuildPoolOptions,
} from './generate_gem_digest.mjs'

describe('既定値（出荷値の固定）', () => {
  it('引数なしのときの既定値が決定ログの採用値と一致する', () => {
    const args = parseArgs([])
    expect(args).toMatchObject({
      quota: 15000,
      perPage: 1000,
      registries: null,
      minStars: 5,
      highDependentRank: 100,
      digestLimit: 300,
      dryRun: false,
      allowPartialWrite: false,
      report: null,
    })
  })

  it('定数と parseArgs の既定値が同じものを指している', () => {
    const args = parseArgs([])
    expect(DEFAULT_QUOTA).toBe(15000)
    expect(DEFAULT_PER_PAGE).toBe(1000)
    expect(DEFAULT_MIN_STARS).toBe(5)
    expect(DEFAULT_HIGH_DEPENDENT_RANK).toBe(100)
    expect(DEFAULT_DIGEST_LIMIT).toBe(300)
    expect(args.outDir).toBe(DEFAULT_OUT_DIR)
    expect(args.digestOut).toBe(DEFAULT_DIGEST_OUT)
  })

  it('明示指定した値で既定を上書きする', () => {
    const args = parseArgs([
      '--quota',
      '2000',
      '--min-stars',
      '0',
      '--high-dependent-rank',
      '10',
      '--digest-limit',
      '50',
      '--out-dir',
      'tmp/out',
      '--digest-out',
      'tmp/digest.json',
      '--report',
      'tmp/report.json',
      '--dry-run',
      '--allow-partial-write',
    ])
    expect(args).toMatchObject({
      quota: 2000,
      minStars: 0,
      highDependentRank: 10,
      digestLimit: 50,
      outDir: 'tmp/out',
      digestOut: 'tmp/digest.json',
      report: 'tmp/report.json',
      dryRun: true,
      allowPartialWrite: true,
    })
  })

  it('--registries は既知のレジストリ定義へ解決し、重複を畳む', () => {
    const args = parseArgs(['--registries', 'npmjs.org, crates.io ,npmjs.org'])
    expect(args.registries.map((r) => r.name)).toEqual(['npmjs.org', 'crates.io'])
  })
})

describe('toBuildPoolOptions', () => {
  it('buildPool の契約どおり `highDependentRankPercentile` というキー名で渡す', () => {
    const options = toBuildPoolOptions(parseArgs([]))
    // 🔴 キー名を変えると pipeline 側のモジュール既定へ静かにフォールバックする
    expect(Object.keys(options).sort()).toEqual(['highDependentRankPercentile', 'minStars'])
    expect(options.highDependentRankPercentile).toBe(100)
    expect(options.minStars).toBe(5)
  })

  it('CLI で上書きした値をそのまま渡す', () => {
    const options = toBuildPoolOptions(
      parseArgs(['--min-stars', '3', '--high-dependent-rank', '12.5']),
    )
    expect(options).toEqual({ minStars: 3, highDependentRankPercentile: 12.5 })
  })
})

describe('引数エラー', () => {
  it('未知のレジストリ名を拒否する', () => {
    expect(() => parseArgs(['--registries', 'npmjs.org,nope.example'])).toThrow(/未知のレジストリ/)
  })

  it('--quota 0 を拒否する', () => {
    expect(() => parseArgs(['--quota', '0'])).toThrow(/正の整数/)
  })

  it('未知のフラグを拒否する', () => {
    expect(() => parseArgs(['--nope'])).toThrow(/未知の引数/)
  })

  it('値のないパス系フラグを拒否する', () => {
    expect(() => parseArgs(['--out-dir'])).toThrow(/パスを指定/)
    expect(() => parseArgs(['--report', '--dry-run'])).toThrow(/パスを指定/)
  })

  it('--high-dependent-rank の範囲外を拒否する', () => {
    expect(() => parseArgs(['--high-dependent-rank', '101'])).toThrow(/0〜100/)
  })
})

describe('decideOutputWrite（部分実行で配信物を壊さない）', () => {
  const full = { selectedRegistryCount: 12, totalRegistryCount: 12, failureCount: 0 }

  it('全レジストリ成功なら書き込む', () => {
    expect(decideOutputWrite(full)).toEqual({
      partial: false,
      write: true,
      blocked: false,
      reason: null,
    })
  })

  it('--registries で部分指定したら既定で書き込みを拒否する', () => {
    const d = decideOutputWrite({ ...full, selectedRegistryCount: 2 })
    expect(d).toMatchObject({ partial: true, write: false, blocked: true })
    expect(d.reason).toMatch(/--allow-partial-write/)
  })

  it('収集失敗があれば既定で書き込みを拒否する', () => {
    const d = decideOutputWrite({ ...full, failureCount: 1 })
    expect(d).toMatchObject({ partial: true, write: false, blocked: true })
    expect(d.reason).toMatch(/収集失敗 1 件/)
  })

  it('--allow-partial-write を付ければ部分結果でも書き込む', () => {
    const d = decideOutputWrite({
      ...full,
      selectedRegistryCount: 2,
      failureCount: 1,
      allowPartialWrite: true,
    })
    expect(d).toMatchObject({ partial: true, write: true, blocked: false })
  })

  it('--dry-run はどんな場合でも書き込まず、拒否（非ゼロ終了）にもしない', () => {
    expect(decideOutputWrite({ ...full, dryRun: true })).toMatchObject({
      write: false,
      blocked: false,
    })
    expect(decideOutputWrite({ ...full, selectedRegistryCount: 1, dryRun: true })).toMatchObject({
      partial: true,
      write: false,
      blocked: false,
    })
  })
})

describe('selectOrphanShards', () => {
  it('今回の索引に載らない *.json だけを削除対象にする', () => {
    const orphans = selectOrphanShards(
      ['npmjs-org.json', 'crates-io.json', 'rubygems-org.json', 'index.json', 'README.md'],
      ['npmjs-org.json', 'crates-io.json', 'index.json'],
    )
    expect(orphans).toEqual(['rubygems-org.json'])
  })

  it('JSON 以外のファイルは削除しない', () => {
    expect(selectOrphanShards(['notes.txt', '.gitkeep'], ['index.json'])).toEqual([])
  })

  it('削除対象がなければ空配列を返す', () => {
    expect(selectOrphanShards(['index.json'], ['index.json'])).toEqual([])
    expect(selectOrphanShards(undefined, ['index.json'])).toEqual([])
  })
})
