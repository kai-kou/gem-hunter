/**
 * `SP-17`（Issue #387）変換パイプラインのユニットテスト。
 *
 * `D-37` が必須と定めた 3 点（(1) レジストリ別成層化 / (2) 汚染フィルタ / (3) repo 単位 dedupe）
 * それぞれに対応するテストを置き、`D-37` が **却下した挙動**（`sum` 集約・`min`/`max` 代表選定・
 * レジストリ内順位の素の混在）が入り込んでいないことも回帰テストで担保する。
 */

import { describe, expect, it } from 'vitest'

import { computeGemIndexValue } from '../../src/domain/model/gem-index.rules.mjs'

import {
  applyPollutionFilter,
  buildPool,
  dedupeByRepository,
  projectPackage,
  restratifyByRegistry,
} from './pipeline.mjs'

/** テスト用に `RankedRecord` を組み立てる補助（純粋関数なので直接与えてよい）。 */
function ranked(overrides) {
  return {
    registry: 'npm',
    packageName: 'pkg',
    repositoryFullName: 'owner/repo',
    dependentCount: 100,
    stars: 10,
    dependentRank: 50,
    starRank: 50,
    gemIndex: 0,
    ...overrides,
  }
}

describe('projectPackage（投影）', () => {
  it('GitHub の HTTPS URL から owner/repo を抜く', () => {
    const record = projectPackage(
      {
        name: 'left-pad',
        repository_url: 'https://github.com/stevemao/left-pad',
        dependent_packages_count: 42,
        repo_metadata: { stargazers_count: 1234 },
      },
      'npm',
    )
    expect(record).toEqual({
      registry: 'npm',
      packageName: 'left-pad',
      repositoryFullName: 'stevemao/left-pad',
      dependentCount: 42,
      stars: 1234,
    })
  })

  it('git+https / .git サフィックス / git@ 形式 / 末尾スラッシュを正規化する', () => {
    const variants = [
      'git+https://github.com/owner/repo.git',
      'git://github.com/owner/repo.git',
      'git@github.com:owner/repo.git',
      'ssh://git@github.com/owner/repo.git',
      'https://www.github.com/owner/repo/',
      'http://github.com/owner/repo',
      'HTTPS://GitHub.com/owner/repo',
    ]
    for (const repositoryUrl of variants) {
      const record = projectPackage(
        {
          name: 'p',
          repository_url: repositoryUrl,
          dependent_packages_count: 1,
          repo_metadata: { stargazers_count: 5 },
        },
        'npm',
      )
      expect(record?.repositoryFullName, repositoryUrl).toBe('owner/repo')
    }
  })

  it('GitHub 以外・解決不能・owner/repo が不正なものは null を返す', () => {
    const invalid = [
      'https://gitlab.com/owner/repo',
      'https://bitbucket.org/owner/repo',
      'https://github.com/owner',
      'https://github.com/owner/repo/tree/main',
      'https://github.com/owner/re po',
      'https://github.com//repo',
      'not a url',
      '',
      null,
      undefined,
    ]
    for (const repositoryUrl of invalid) {
      const record = projectPackage(
        {
          name: 'p',
          repository_url: repositoryUrl,
          dependent_packages_count: 1,
          repo_metadata: { stargazers_count: 5 },
        },
        'npm',
      )
      expect(record, String(repositoryUrl)).toBeNull()
    }
  })

  it('dependent_packages_count が有限数でなければ null を返す', () => {
    for (const dependentCount of [null, undefined, 'many', NaN, Infinity, -1]) {
      const record = projectPackage(
        {
          name: 'p',
          repository_url: 'https://github.com/owner/repo',
          dependent_packages_count: dependentCount,
          repo_metadata: { stargazers_count: 5 },
        },
        'npm',
      )
      expect(record, String(dependentCount)).toBeNull()
    }
  })

  it('star の 3 状態を区別する（repo_metadata 無し / キー無し / 明示 0）', () => {
    // ① repo_metadata 自体が無い → 欠損
    const noMetadata = projectPackage(
      {
        name: '@types/json5',
        repository_url: 'https://github.com/DefinitelyTyped/DefinitelyTyped',
        dependent_packages_count: 10,
      },
      'npm',
    )
    expect(noMetadata?.stars).toBeNull()

    // ② repo_metadata はあるが stargazers_count キーが無い（Maven 実測で 100 件中 22 件）→ 欠損
    const noStarKey = projectPackage(
      {
        name: 'org.example:lib',
        repository_url: 'https://github.com/owner/repo',
        dependent_packages_count: 10,
        repo_metadata: { full_name: 'owner/repo' },
      },
      'maven',
    )
    expect(noStarKey?.stars).toBeNull()

    // ②' 非有限数も欠損として扱う
    const invalidStar = projectPackage(
      {
        name: 'p',
        repository_url: 'https://github.com/owner/repo',
        dependent_packages_count: 10,
        repo_metadata: { stargazers_count: 'zero' },
      },
      'npm',
    )
    expect(invalidStar?.stars).toBeNull()

    // ③ stargazers_count: 0 が明示 → 真の 0
    const trueZero = projectPackage(
      {
        name: 'is-color-stop',
        repository_url: 'https://github.com/pigcan/is-color-stop',
        dependent_packages_count: 10,
        repo_metadata: { stargazers_count: 0 },
      },
      'npm',
    )
    expect(trueZero?.stars).toBe(0)
  })

  it('API の rankings は投影に持ち込まない（母集団が違うため使わない）', () => {
    const record = projectPackage(
      {
        name: 'p',
        repository_url: 'https://github.com/owner/repo',
        dependent_packages_count: 10,
        repo_metadata: { stargazers_count: 5 },
        rankings: { dependent_packages_count: 0.1, stargazers_count: 99.9 },
      },
      'npm',
    )
    expect(record).toEqual({
      registry: 'npm',
      packageName: 'p',
      repositoryFullName: 'owner/repo',
      dependentCount: 10,
      stars: 5,
    })
    expect(record).not.toHaveProperty('rankings')
    expect(record).not.toHaveProperty('dependentRank')
  })

  it('packageName は長さ上限（214 文字）と制御文字 / 双方向制御文字を検証する', () => {
    const project = (name) =>
      projectPackage(
        {
          name,
          repository_url: 'https://github.com/owner/repo',
          dependent_packages_count: 10,
          repo_metadata: { stargazers_count: 5 },
        },
        'npm',
      )

    // 正常系: スコープ付き・記号入り・ちょうど 214 文字は通る
    expect(project('@scope/pkg-name.v2')?.packageName).toBe('@scope/pkg-name.v2')
    expect(project('org.example:artifact-id')?.packageName).toBe('org.example:artifact-id')
    expect(project('a'.repeat(214))?.packageName).toBe('a'.repeat(214))

    // 異常系: 215 文字・C0/C1 制御文字・双方向制御文字は投影しない
    // ソースへ生の制御文字を書かないよう、エスケープシーケンスで表現する
    expect(project('a'.repeat(215))).toBeNull()
    expect(project('pkg\u0000name')).toBeNull() // NUL（C0）
    expect(project('pkg\nname')).toBeNull() // LF（C0）
    expect(project('pkg\u009Fname')).toBeNull() // APC（C1）
    expect(project('pkg\u202Ename')).toBeNull() // RLO（表示詐称）
    expect(project('pkg\u200Fname')).toBeNull() // RLM
    expect(project('pkg\u2066name')).toBeNull() // LRI
  })

  it('レジストリ名が __proto__ / constructor / prototype のものは投影しない', () => {
    for (const registryName of ['__proto__', 'constructor', 'prototype']) {
      const raw = {
        name: 'p',
        repository_url: 'https://github.com/owner/repo',
        dependent_packages_count: 10,
        repo_metadata: { stargazers_count: 5 },
        registry: { name: registryName },
      }
      // API レスポンス由来（引数省略）でも、明示指定でも弾く
      expect(projectPackage(raw), registryName).toBeNull()
      expect(projectPackage(raw, registryName), registryName).toBeNull()
    }
  })
})

describe('restratifyByRegistry（レジストリ別成層化）', () => {
  it('レジストリごとに独立して順位を振る（小さいレジストリの 1 位も 0 になる）', () => {
    const input = [
      {
        registry: 'npm',
        packageName: 'n1',
        repositoryFullName: 'o/n1',
        dependentCount: 9000,
        stars: 900,
      },
      {
        registry: 'npm',
        packageName: 'n2',
        repositoryFullName: 'o/n2',
        dependentCount: 5000,
        stars: 500,
      },
      {
        registry: 'npm',
        packageName: 'n3',
        repositoryFullName: 'o/n3',
        dependentCount: 1000,
        stars: 100,
      },
      {
        registry: 'hex',
        packageName: 'h1',
        repositoryFullName: 'o/h1',
        dependentCount: 30,
        stars: 3,
      },
      {
        registry: 'hex',
        packageName: 'h2',
        repositoryFullName: 'o/h2',
        dependentCount: 10,
        stars: 1,
      },
    ]
    const result = restratifyByRegistry(input)
    const byName = Object.fromEntries(result.map((r) => [r.packageName, r]))

    expect(byName.n1.dependentRank).toBe(0)
    expect(byName.n2.dependentRank).toBe(50)
    expect(byName.n3.dependentRank).toBe(100)
    // 小さいレジストリの 1 位も同じ 0（レジストリ別に独立計算されている証拠）
    expect(byName.h1.dependentRank).toBe(0)
    expect(byName.h2.dependentRank).toBe(100)
  })

  it('同値は同じランクになる（値が最初に現れるインデックスを使う）', () => {
    const input = [
      {
        registry: 'npm',
        packageName: 'a',
        repositoryFullName: 'o/a',
        dependentCount: 10,
        stars: 5,
      },
      {
        registry: 'npm',
        packageName: 'b',
        repositoryFullName: 'o/b',
        dependentCount: 10,
        stars: 5,
      },
      { registry: 'npm', packageName: 'c', repositoryFullName: 'o/c', dependentCount: 5, stars: 1 },
    ]
    const byName = Object.fromEntries(restratifyByRegistry(input).map((r) => [r.packageName, r]))
    expect(byName.a.dependentRank).toBe(0)
    expect(byName.b.dependentRank).toBe(0)
    expect(byName.c.dependentRank).toBe(100)
    expect(byName.a.starRank).toBe(0)
    expect(byName.b.starRank).toBe(0)
    expect(byName.c.starRank).toBe(100)
  })

  it('1 件しかないレジストリのランクは 0（ゼロ除算しない）', () => {
    const [record] = restratifyByRegistry([
      {
        registry: 'cran',
        packageName: 'solo',
        repositoryFullName: 'o/solo',
        dependentCount: 7,
        stars: 3,
      },
    ])
    expect(record.dependentRank).toBe(0)
    expect(record.starRank).toBe(0)
    expect(record.gemIndex).toBe(0)
  })

  it('gemIndex = dependentRank − starRank（小数第 2 位に丸める）', () => {
    const input = [
      {
        registry: 'npm',
        packageName: 'a',
        repositoryFullName: 'o/a',
        dependentCount: 100,
        stars: 1,
      },
      {
        registry: 'npm',
        packageName: 'b',
        repositoryFullName: 'o/b',
        dependentCount: 50,
        stars: 50,
      },
      {
        registry: 'npm',
        packageName: 'c',
        repositoryFullName: 'o/c',
        dependentCount: 10,
        stars: 100,
      },
    ]
    const byName = Object.fromEntries(restratifyByRegistry(input).map((r) => [r.packageName, r]))
    // a: 被依存 1 位（0）・star 最下位（100）→ 最も過小評価
    expect(byName.a.gemIndex).toBe(-100)
    expect(byName.b.gemIndex).toBe(0)
    expect(byName.c.gemIndex).toBe(100)
  })

  it('🔴 本番の gemIndex は domain と共有の正本（gem-index.rules.mjs）で算出される', () => {
    // Issue #276 の回帰テスト。かつては本ファイルの算出（`dependentRank - starRank`）と
    // domain の `computeGemIndex` が別実装で、片方を変えても他方は静かに旧規則のまま動いた。
    // `computeGemIndexValue` を独立に適用した値と一致することで、本番経路が共有正本を
    // 通っていることを確認する（別実装へ戻すと、式を変えた瞬間にここが落ちる）。
    const input = Array.from({ length: 5 }, (_, i) => ({
      registry: 'npm',
      packageName: `p${i}`,
      repositoryFullName: `o/p${i}`,
      dependentCount: 100 - i * 7,
      stars: 3 + i * 11,
    }))
    const records = restratifyByRegistry(input)
    expect(records).toHaveLength(5)
    for (const record of records) {
      const expected =
        Math.round(computeGemIndexValue(record.dependentRank, record.starRank) * 100) / 100
      expect(record.gemIndex).toBe(expected)
    }
    // 向きの正本（値が小さいほど過小評価度が高い）も同時に押さえる。
    expect(records.some((r) => r.gemIndex < 0)).toBe(true)
  })

  it('小数第 2 位に丸められる（7 件で 1/6 刻みになるケース）', () => {
    const input = Array.from({ length: 7 }, (_, i) => ({
      registry: 'npm',
      packageName: `p${i}`,
      repositoryFullName: `o/p${i}`,
      dependentCount: 100 - i,
      stars: 100 - i,
    }))
    for (const record of restratifyByRegistry(input)) {
      expect(Number.isInteger(record.gemIndex * 100)).toBe(true)
    }
  })

  it('stars が欠損（null）のレコードはランク計算の母集団に入れず出力から落とす', () => {
    const input = [
      {
        registry: 'npm',
        packageName: 'a',
        repositoryFullName: 'o/a',
        dependentCount: 100,
        stars: 10,
      },
      {
        registry: 'npm',
        packageName: 'missing',
        repositoryFullName: 'o/m',
        dependentCount: 90,
        stars: null,
      },
      {
        registry: 'npm',
        packageName: 'b',
        repositoryFullName: 'o/b',
        dependentCount: 50,
        stars: 5,
      },
      {
        registry: 'npm',
        packageName: 'c',
        repositoryFullName: 'o/c',
        dependentCount: 10,
        stars: 1,
      },
    ]
    const result = restratifyByRegistry(input)
    expect(result.map((r) => r.packageName)).not.toContain('missing')
    // 欠損を母集団から外した 3 件で順位が振られる（4 件だったら 33.33 刻みになる）
    const byName = Object.fromEntries(result.map((r) => [r.packageName, r]))
    expect(byName.a.dependentRank).toBe(0)
    expect(byName.b.dependentRank).toBe(50)
    expect(byName.c.dependentRank).toBe(100)
  })

  it('出力の dependentRank / starRank は必ず 0〜100 に収まる', () => {
    // domain の `computeGemIndex`（`src/domain/model/gem-index.ts` の `assertRank`）と同じ不変条件。
    // 実装側は値域を外れたら例外にする（多層防御）ので、ここでは不変条件が保たれることを固定する。
    const input = Array.from({ length: 13 }, (_, i) => ({
      registry: i % 2 === 0 ? 'npm' : 'cargo',
      packageName: `p${i}`,
      repositoryFullName: `o/p${i}`,
      dependentCount: (i * 37) % 11,
      stars: (i * 53) % 7,
    }))
    const result = restratifyByRegistry(input)
    expect(result).toHaveLength(13)
    for (const record of result) {
      expect(record.dependentRank).toBeGreaterThanOrEqual(0)
      expect(record.dependentRank).toBeLessThanOrEqual(100)
      expect(record.starRank).toBeGreaterThanOrEqual(0)
      expect(record.starRank).toBeLessThanOrEqual(100)
      expect(Math.abs(record.gemIndex)).toBeLessThanOrEqual(100)
    }
  })

  it('出力は決定論的（同値のタイブレークは packageName 昇順）', () => {
    const input = [
      {
        registry: 'npm',
        packageName: 'zzz',
        repositoryFullName: 'o/z',
        dependentCount: 10,
        stars: 5,
      },
      {
        registry: 'npm',
        packageName: 'aaa',
        repositoryFullName: 'o/a',
        dependentCount: 10,
        stars: 5,
      },
    ]
    const first = restratifyByRegistry(input).map((r) => r.packageName)
    const second = restratifyByRegistry([...input].reverse()).map((r) => r.packageName)
    expect(first).toEqual(second)
    expect(first).toEqual(['aaa', 'zzz'])
  })
})

describe('applyPollutionFilter（汚染フィルタ）', () => {
  it('高被依存帯 × stars=0 は repo 誤紐付けの疑いとして落とす', () => {
    const suspicious = ranked({ packageName: 'webjars-mirror', stars: 0, dependentRank: 2 })
    const { kept, dropped } = applyPollutionFilter([suspicious])
    expect(kept).toHaveLength(0)
    expect(dropped).toEqual([{ reason: 'suspicious-zero-star', record: suspicious }])
  })

  it('低被依存帯 × stars=0 は既定の閾値では残る', () => {
    const lowRank = ranked({ packageName: 'tiny', stars: 0, dependentRank: 80 })
    const { kept, dropped } = applyPollutionFilter([lowRank])
    expect(kept).toEqual([lowRank])
    expect(dropped).toHaveLength(0)
  })

  it('highDependentRankPercentile=100 で全帯が対象になる', () => {
    const lowRank = ranked({ packageName: 'tiny', stars: 0, dependentRank: 80 })
    const { kept, dropped } = applyPollutionFilter([lowRank], { highDependentRankPercentile: 100 })
    expect(kept).toHaveLength(0)
    expect(dropped[0].reason).toBe('suspicious-zero-star')
  })

  it('minStars=Infinity × highDependentRankPercentile=100 で star を持つものも全部落ちる', () => {
    const records = [
      ranked({ packageName: 'a', stars: 1 }),
      ranked({ packageName: 'b', stars: 99999 }),
    ]
    const { kept } = applyPollutionFilter(records, {
      minStars: Infinity,
      highDependentRankPercentile: 100,
    })
    expect(kept).toHaveLength(0)
  })

  it('minStars を上げると閾値未満の star が高被依存帯で落ちる', () => {
    const records = [
      ranked({ packageName: 'few-stars', stars: 3, dependentRank: 1 }),
      ranked({ packageName: 'many-stars', stars: 300, dependentRank: 1 }),
    ]
    const { kept, dropped } = applyPollutionFilter(records, { minStars: 10 })
    expect(kept.map((r) => r.packageName)).toEqual(['many-stars'])
    expect(dropped.map((d) => d.record.packageName)).toEqual(['few-stars'])
  })

  it('dependentCount=0 は no-dependents として落とす', () => {
    const zeroDependents = ranked({ packageName: 'unused', dependentCount: 0, stars: 500 })
    const { kept, dropped } = applyPollutionFilter([zeroDependents])
    expect(kept).toHaveLength(0)
    expect(dropped).toEqual([{ reason: 'no-dependents', record: zeroDependents }])
  })

  it('dropped に理由が残り、理由別に集計できる', () => {
    const records = [
      ranked({ packageName: 'ok', stars: 100, dependentRank: 1 }),
      ranked({ packageName: 'zero-dep', dependentCount: 0, stars: 100 }),
      ranked({ packageName: 'sus', stars: 0, dependentRank: 0 }),
    ]
    const { kept, dropped } = applyPollutionFilter(records)
    expect(kept.map((r) => r.packageName)).toEqual(['ok'])
    const reasons = dropped.map((d) => d.reason).sort()
    expect(reasons).toEqual(['no-dependents', 'suspicious-zero-star'])
  })

  it('入力配列を破壊しない', () => {
    const records = [ranked({ packageName: 'a' })]
    const snapshot = structuredClone(records)
    applyPollutionFilter(records)
    expect(records).toEqual(snapshot)
  })
})

describe('dedupeByRepository（repo 単位 dedupe）', () => {
  it('同一 repo では被依存数最大の flagship パッケージが代表になる', () => {
    const records = [
      ranked({
        packageName: 'ark-bench',
        repositoryFullName: 'arkworks-rs/algebra',
        dependentCount: 3,
      }),
      ranked({
        packageName: 'ark-ff',
        repositoryFullName: 'arkworks-rs/algebra',
        dependentCount: 1829,
      }),
      ranked({
        packageName: 'ark-poly',
        repositoryFullName: 'arkworks-rs/algebra',
        dependentCount: 400,
      }),
    ]
    const result = dedupeByRepository(records)
    expect(result).toHaveLength(1)
    expect(result[0].packageName).toBe('ark-ff')
  })

  it('回帰防止: D-37 が却下した sum 集約をしない（代表の被依存数は素のまま）', () => {
    const records = [
      ranked({ packageName: 'pkg-a', repositoryFullName: 'o/mono', dependentCount: 1829 }),
      ranked({ packageName: 'pkg-b', repositoryFullName: 'o/mono', dependentCount: 3 }),
    ]
    const [representative] = dedupeByRepository(records)
    expect(representative.dependentCount).toBe(1829)
    expect(representative.dependentCount).not.toBe(1832)
  })

  it('回帰防止: D-37 が却下した min/max（gemIndex）による代表選定をしない', () => {
    // gemIndex が最小（＝過小評価度が最も高い）のはベンチマーク用クレートだが、
    // 代表は被依存数最大の ark-ff でなければならない。
    const records = [
      ranked({
        packageName: 'ark-bench',
        repositoryFullName: 'arkworks-rs/algebra',
        dependentCount: 3,
        gemIndex: -99,
      }),
      ranked({
        packageName: 'ark-ff',
        repositoryFullName: 'arkworks-rs/algebra',
        dependentCount: 1829,
        gemIndex: -10,
      }),
    ]
    const [representative] = dedupeByRepository(records)
    expect(representative.packageName).toBe('ark-ff')
    expect(representative.gemIndex).toBe(-10)
  })

  it('被依存数が同値なら packageName 昇順で決定論的に選ぶ', () => {
    const records = [
      ranked({ packageName: 'zeta', repositoryFullName: 'o/repo', dependentCount: 10 }),
      ranked({ packageName: 'alpha', repositoryFullName: 'o/repo', dependentCount: 10 }),
    ]
    expect(dedupeByRepository(records)[0].packageName).toBe('alpha')
    expect(dedupeByRepository([...records].reverse())[0].packageName).toBe('alpha')
  })

  it('repositoryFullName の大文字小文字違いを同一 repo として畳む（GitHub は case を区別しない）', () => {
    const records = [
      ranked({ packageName: 'perl-small', repositoryFullName: 'perl/perl5', dependentCount: 3 }),
      ranked({
        packageName: 'perl-flagship',
        repositoryFullName: 'Perl/perl5',
        dependentCount: 900,
      }),
    ]
    const result = dedupeByRepository(records)
    expect(result).toHaveLength(1)
    expect(result[0].packageName).toBe('perl-flagship')
    // 表示値は代表レコードの元の綴りを保つ（小文字化するのは突き合わせキーだけ）
    expect(result[0].repositoryFullName).toBe('Perl/perl5')
    // 入力順を変えても代表は変わらない（決定論）
    expect(dedupeByRepository([...records].reverse())[0].repositoryFullName).toBe('Perl/perl5')
  })

  it('異なる repo は残す（レジストリが違っても repo が同じなら 1 件に畳む）', () => {
    const records = [
      ranked({ registry: 'npm', packageName: 'a', repositoryFullName: 'o/a', dependentCount: 10 }),
      ranked({ registry: 'pypi', packageName: 'b', repositoryFullName: 'o/b', dependentCount: 20 }),
      ranked({
        registry: 'pypi',
        packageName: 'a-py',
        repositoryFullName: 'o/a',
        dependentCount: 5,
      }),
    ]
    const result = dedupeByRepository(records)
    expect(result.map((r) => r.repositoryFullName)).toEqual(['o/a', 'o/b'])
    expect(result.find((r) => r.repositoryFullName === 'o/a').packageName).toBe('a')
  })
})

describe('buildPool（全段の統合）', () => {
  /** レジストリ別の投影済み入力（Map 形式）。 */
  function fixture() {
    return new Map([
      [
        'npm',
        [
          {
            registry: 'npm',
            packageName: 'a-top',
            repositoryFullName: 'o/a',
            dependentCount: 1000,
            stars: 10,
          },
          {
            registry: 'npm',
            packageName: 'b-mid',
            repositoryFullName: 'o/b',
            dependentCount: 500,
            stars: 5000,
          },
          {
            registry: 'npm',
            packageName: 'c-missing',
            repositoryFullName: 'o/c',
            dependentCount: 300,
            stars: null,
          },
          {
            registry: 'npm',
            packageName: 'd-zero',
            repositoryFullName: 'o/d',
            dependentCount: 0,
            stars: 100,
          },
        ],
      ],
      [
        'cargo',
        [
          {
            registry: 'cargo',
            packageName: 'ark-ff',
            repositoryFullName: 'ark/algebra',
            dependentCount: 1829,
            stars: 700,
          },
          {
            registry: 'cargo',
            packageName: 'ark-bench',
            repositoryFullName: 'ark/algebra',
            dependentCount: 3,
            stars: 700,
          },
          {
            registry: 'cargo',
            packageName: 'g-sus',
            repositoryFullName: 'x/g',
            dependentCount: 2000,
            stars: 0,
          },
        ],
      ],
    ])
  }

  it('欠損除去 → 被依存 0 除去 → dedupe → 汚染フィルタ → 最終順位の再計算 の順で流れ、gemIndex 昇順で返る', () => {
    const { records } = buildPool(fixture())
    expect(records.map((r) => r.repositoryFullName)).toEqual(['o/a', 'ark/algebra', 'o/b'])
    // 最終順位は「生き残りだけ」で再計算される。cargo は ark-ff の 1 件だけが残るのでランクは 0/0
    //（除外前の 3 件で振った順位のままなら 50 になる ＝ 除外率の差が gemIndex に漏れている状態）。
    expect(records.map((r) => r.gemIndex)).toEqual([-100, 0, 100])
    // dedupe の代表は被依存数最大の flagship
    expect(records[1].packageName).toBe('ark-ff')
  })

  it('stats の件数が合う（レジストリ別 collected / missingStars / filtered / kept）', () => {
    const { stats } = buildPool(fixture())
    // 全項目一致で見る（`deduped` を落とす変異がすり抜けないように・`index.json` の運用判断に使う値）
    expect(stats.byRegistry.npm).toEqual({
      collected: 4,
      missingStars: 1,
      filtered: 1,
      deduped: 0,
      kept: 2,
    })
    expect(stats.byRegistry.cargo).toEqual({
      collected: 3,
      missingStars: 0,
      filtered: 1,
      deduped: 1,
      kept: 1,
    })
    expect(stats.totalUnique).toBe(3)
    expect(stats.droppedByReason).toEqual({
      'missing-stars': 1,
      'no-dependents': 1,
      'suspicious-zero-star': 1,
      'duplicate-repository': 1,
    })
  })

  it('registryShare は最終プールのレジストリ別構成比（%）', () => {
    const { stats } = buildPool(fixture())
    expect(stats.registryShare).toEqual({ npm: 66.67, cargo: 33.33 })
  })

  it('{registry, records}[] 形式の入力も受け付ける', () => {
    const asArray = [...fixture()].map(([registry, records]) => ({ registry, records }))
    expect(buildPool(asArray).records).toEqual(buildPool(fixture()).records)
  })

  it('options が汚染フィルタのつまみとして効く', () => {
    const { records, stats } = buildPool(fixture(), {
      minStars: Infinity,
      highDependentRankPercentile: 100,
    })
    expect(records).toHaveLength(0)
    expect(stats.totalUnique).toBe(0)
    expect(stats.registryShare).toEqual({})
  })

  it('空入力でも壊れない', () => {
    const { records, stats } = buildPool(new Map())
    expect(records).toEqual([])
    expect(stats.totalUnique).toBe(0)
    expect(stats.byRegistry).toEqual({})
  })

  it('回帰防止: レジストリ内順位を素で混ぜない（小レジストリの極小パッケージが上位を独占しない）', () => {
    // hex 側は 2 件しかないため素の混在ではランク 0 の h1 が npm の巨大パッケージと同列に並ぶ。
    // 成層化後も「レジストリ別に再計算した順位の差」で比較されることを確認する。
    const byRegistry = new Map([
      [
        'npm',
        [
          {
            registry: 'npm',
            packageName: 'n1',
            repositoryFullName: 'o/n1',
            dependentCount: 90000,
            stars: 100,
          },
          {
            registry: 'npm',
            packageName: 'n2',
            repositoryFullName: 'o/n2',
            dependentCount: 100,
            stars: 90000,
          },
        ],
      ],
      [
        'hex',
        [
          {
            registry: 'hex',
            packageName: 'h1',
            repositoryFullName: 'o/h1',
            dependentCount: 5,
            stars: 1,
          },
          {
            registry: 'hex',
            packageName: 'h2',
            repositoryFullName: 'o/h2',
            dependentCount: 1,
            stars: 900,
          },
        ],
      ],
    ])
    const { records } = buildPool(byRegistry)
    // 各レジストリで「被依存 1 位 × star 最下位」が -100 になる（レジストリ規模に依存しない）
    const byName = Object.fromEntries(records.map((r) => [r.packageName, r]))
    expect(byName.n1.gemIndex).toBe(-100)
    expect(byName.h1.gemIndex).toBe(-100)
    expect(byName.n2.gemIndex).toBe(100)
    expect(byName.h2.gemIndex).toBe(100)
  })

  it('回帰防止: 最終順位は生き残りだけで再計算する（除外率のレジストリ差を順位に漏らさない）', () => {
    // レジストリ a は 10 件中 9 件が汚染で落ち、レジストリ b は 1 件も落ちない。
    // 除外前に振った順位のまま配信すると、a の生き残りは dependentRank=100 のまま残り
    // gemIndex=100（最下位）になる。生き残り集合で再計算すれば単独の 1 件なので 0 になる。
    const byRegistry = new Map([
      [
        'a',
        Array.from({ length: 10 }, (_, i) => ({
          registry: 'a',
          packageName: `a${i}`,
          repositoryFullName: `o/a${i}`,
          dependentCount: 1000 - i * 100,
          stars: i < 9 ? 0 : 5, // 被依存上位 9 件は star 0（＝汚染扱い）
        })),
      ],
      [
        'b',
        Array.from({ length: 10 }, (_, i) => ({
          registry: 'b',
          packageName: `b${i}`,
          repositoryFullName: `o/b${i}`,
          dependentCount: 1000 - i * 100,
          stars: 10 + i,
        })),
      ],
    ])
    const { records, stats } = buildPool(byRegistry, {
      minStars: 1,
      highDependentRankPercentile: 90,
    })

    expect(stats.byRegistry.a).toEqual({
      collected: 10,
      missingStars: 0,
      filtered: 9,
      deduped: 0,
      kept: 1,
    })
    expect(stats.byRegistry.b).toEqual({
      collected: 10,
      missingStars: 0,
      filtered: 0,
      deduped: 0,
      kept: 10,
    })

    const survivor = records.find((r) => r.registry === 'a')
    expect(survivor.packageName).toBe('a9')
    // 生き残り集合（a は 1 件だけ）で再計算されるので 0/0/0。100 なら除外前の順位が漏れている。
    expect(survivor.dependentRank).toBe(0)
    expect(survivor.starRank).toBe(0)
    expect(survivor.gemIndex).toBe(0)

    // b 側は 10 件そのままなので 0〜100 に広がる（再計算が b の順位を壊していないこと）
    const bRanks = records.filter((r) => r.registry === 'b').map((r) => r.dependentRank)
    expect(Math.min(...bRanks)).toBe(0)
    expect(Math.max(...bRanks)).toBe(100)
  })

  it('回帰防止: 汚染判定は dedupe 後の代表（flagship）に対して行う', () => {
    // 逆順（汚染フィルタ → dedupe）だと flagship だけが落ち、被依存 3 件の兄弟が代表に繰り上がる。
    const byRegistry = new Map([
      [
        'npm',
        [
          {
            registry: 'npm',
            packageName: 'spam-flagship',
            repositoryFullName: 'spam/repo',
            dependentCount: 9000,
            stars: 0,
          },
          {
            registry: 'npm',
            packageName: 'spam-sibling',
            repositoryFullName: 'spam/repo',
            dependentCount: 3,
            stars: 0,
          },
          {
            registry: 'npm',
            packageName: 'legit',
            repositoryFullName: 'o/legit',
            dependentCount: 100,
            stars: 50,
          },
        ],
      ],
    ])
    const { records, stats } = buildPool(byRegistry)
    expect(records.map((r) => r.repositoryFullName)).toEqual(['o/legit'])
    expect(records.map((r) => r.packageName)).not.toContain('spam-sibling')
    expect(stats.droppedByReason['duplicate-repository']).toBe(1)
    expect(stats.droppedByReason['suspicious-zero-star']).toBe(1)
  })

  it('レジストリ名が __proto__ でも Object.prototype を汚染しない', () => {
    const byRegistry = new Map([
      [
        '__proto__',
        [
          {
            registry: '__proto__',
            packageName: 'p',
            repositoryFullName: 'o/p',
            dependentCount: 10,
            stars: 5,
          },
        ],
      ],
    ])
    const { stats } = buildPool(byRegistry)

    expect(Object.keys(stats.byRegistry)).toEqual(['__proto__'])
    expect(Object.values(stats.byRegistry)[0]).toEqual({
      collected: 1,
      missingStars: 0,
      filtered: 0,
      deduped: 0,
      kept: 1,
    })
    expect(stats.totalCollected).toBe(1)
    // `Object.prototype` に集計値が生えていないこと（`??=` が prototype を見て代入を握り潰さないこと）
    expect({}.collected).toBeUndefined()
    expect(Object.prototype.collected).toBeUndefined()
    expect(Object.prototype.kept).toBeUndefined()
  })

  it('入力の Map / 配列を破壊しない', () => {
    const input = fixture()
    const snapshot = structuredClone([...input])
    buildPool(input)
    expect(structuredClone([...input])).toEqual(snapshot)
  })
})
