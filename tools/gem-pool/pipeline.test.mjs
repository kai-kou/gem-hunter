// pipeline.test.mjs — 変換パイプライン（純関数のみ）のテスト。
// ネットワークに触れない（`fetch` を一切使わない）。SP-17 契約 §4 の全観点を網羅する。

import { describe, expect, it } from 'vitest'
import {
  DEFAULT_ZERO_STAR_DEPENDENT_THRESHOLD,
  buildPool,
  classifyStars,
  dedupeByRepository,
  extractGithubFullName,
  isContaminated,
  normalizeRecord,
  poolStats,
  recomputeRanks,
} from './pipeline.mjs'

describe('classifyStars', () => {
  it('① repo_metadata 自体が無い → missing', () => {
    expect(classifyStars({ name: '@types/json5' })).toBe('missing')
  })

  it('② repo_metadata はあるが stargazers_count キーが無い（Maven 実測相当） → missing', () => {
    expect(classifyStars({ repo_metadata: { forks_count: 3 } })).toBe('missing')
  })

  it('② stargazers_count が数値でない（文字列等） → missing', () => {
    expect(classifyStars({ repo_metadata: { stargazers_count: 'N/A' } })).toBe('missing')
  })

  it('③ stargazers_count: 0 が明示されている → zero（真の 0）', () => {
    expect(classifyStars({ repo_metadata: { stargazers_count: 0 } })).toBe('zero')
  })

  it('④ それ以外の有限数 → positive', () => {
    expect(classifyStars({ repo_metadata: { stargazers_count: 60000 } })).toBe('positive')
  })
})

describe('extractGithubFullName', () => {
  it('https URL から owner/repo を抜き出す', () => {
    expect(extractGithubFullName('https://github.com/lodash/lodash')).toBe('lodash/lodash')
  })

  it('git+https / .git 付きも解決する', () => {
    expect(extractGithubFullName('git+https://github.com/lodash/lodash.git')).toBe(
      'lodash/lodash',
    )
  })

  it('git@github.com: 形式も解決する', () => {
    expect(extractGithubFullName('git@github.com:lodash/lodash.git')).toBe('lodash/lodash')
  })

  it('GitHub 以外の URL は null', () => {
    expect(extractGithubFullName('https://gitlab.com/foo/bar')).toBeNull()
  })

  it('null/undefined は null', () => {
    expect(extractGithubFullName(undefined)).toBeNull()
    expect(extractGithubFullName(null)).toBeNull()
  })
})

describe('normalizeRecord', () => {
  const validRaw = {
    name: 'lodash',
    repository_url: 'https://github.com/lodash/lodash',
    dependent_packages_count: 123456,
    repo_metadata: { stargazers_count: 60000 },
  }

  it('正常系: NormalizedPackage を返す', () => {
    expect(normalizeRecord(validRaw, 'npm')).toEqual({
      registry: 'npm',
      packageName: 'lodash',
      repositoryFullName: 'lodash/lodash',
      dependentCount: 123456,
      stars: 60000,
    })
  })

  it('GitHub 以外の repository_url は null', () => {
    expect(normalizeRecord({ ...validRaw, repository_url: 'https://gitlab.com/a/b' }, 'npm')).toBeNull()
  })

  it('name が不正（欠落・空文字）は null', () => {
    expect(normalizeRecord({ ...validRaw, name: '' }, 'npm')).toBeNull()
    const { name, ...rest } = validRaw
    expect(normalizeRecord(rest, 'npm')).toBeNull()
  })

  it('dependent_packages_count が非数は null', () => {
    expect(normalizeRecord({ ...validRaw, dependent_packages_count: 'many' }, 'npm')).toBeNull()
  })

  it('classifyStars が missing のときは null', () => {
    expect(normalizeRecord({ ...validRaw, repo_metadata: undefined }, 'npm')).toBeNull()
  })

  it('真の 0 star は stars: 0 で採用する（null にしない）', () => {
    const raw = { ...validRaw, repo_metadata: { stargazers_count: 0 } }
    expect(normalizeRecord(raw, 'npm')?.stars).toBe(0)
  })
})

describe('isContaminated', () => {
  const opts = { zeroStarDependentThreshold: DEFAULT_ZERO_STAR_DEPENDENT_THRESHOLD }

  it('stars=0 かつ dependentCount が閾値ちょうど → true（境界値は含む）', () => {
    expect(
      isContaminated({ stars: 0, dependentCount: DEFAULT_ZERO_STAR_DEPENDENT_THRESHOLD }, opts),
    ).toBe(true)
  })

  it('stars=0 かつ dependentCount が閾値未満 → false', () => {
    expect(
      isContaminated(
        { stars: 0, dependentCount: DEFAULT_ZERO_STAR_DEPENDENT_THRESHOLD - 1 },
        opts,
      ),
    ).toBe(false)
  })

  it('stars > 0 は dependentCount がどれだけ多くても false', () => {
    expect(isContaminated({ stars: 1, dependentCount: 999999 }, opts)).toBe(false)
  })
})

describe('dedupeByRepository', () => {
  it('同一 repo は dependentCount 最大の flagship を代表にする', () => {
    const items = [
      { registry: 'npm', packageName: 'ark-bench', repositoryFullName: 'arkworks-rs/algebra', dependentCount: 3, stars: 100 },
      { registry: 'npm', packageName: 'ark-ff', repositoryFullName: 'arkworks-rs/algebra', dependentCount: 1829, stars: 100 },
    ]
    const result = dedupeByRepository(items)
    expect(result).toHaveLength(1)
    expect(result[0].packageName).toBe('ark-ff')
  })

  it('dependentCount が同値のときは packageName 昇順で決定論的にタイブレークする（入力順に依存しない）', () => {
    const a = { registry: 'npm', packageName: 'b-pkg', repositoryFullName: 'x/y', dependentCount: 100, stars: 1 }
    const b = { registry: 'npm', packageName: 'a-pkg', repositoryFullName: 'x/y', dependentCount: 100, stars: 1 }
    const c = { registry: 'npm', packageName: 'c-pkg', repositoryFullName: 'x/y', dependentCount: 100, stars: 1 }

    const resultForward = dedupeByRepository([a, b, c])
    const resultReversed = dedupeByRepository([c, b, a])

    expect(resultForward).toHaveLength(1)
    expect(resultForward[0].packageName).toBe('a-pkg')
    expect(resultReversed[0].packageName).toBe('a-pkg')
  })

  it('レジストリ横断で dedupe する（同じ repo が npm と pypi の両方に出る）', () => {
    const npmPkg = { registry: 'npm', packageName: 'requests-js', repositoryFullName: 'psf/requests', dependentCount: 50, stars: 10 }
    const pypiPkg = { registry: 'pypi', packageName: 'requests', repositoryFullName: 'psf/requests', dependentCount: 90000, stars: 10 }
    const result = dedupeByRepository([npmPkg, pypiPkg])
    expect(result).toHaveLength(1)
    expect(result[0].registry).toBe('pypi')
    expect(result[0].packageName).toBe('requests')
  })

  it('別 repo は残す', () => {
    const items = [
      { registry: 'npm', packageName: 'a', repositoryFullName: 'a/a', dependentCount: 1, stars: 1 },
      { registry: 'npm', packageName: 'b', repositoryFullName: 'b/b', dependentCount: 1, stars: 1 },
    ]
    expect(dedupeByRepository(items)).toHaveLength(2)
  })
})

describe('recomputeRanks', () => {
  it('同値は同順位（最小順位方式）になる', () => {
    // dependentCount 降順: [30,30,20,10,10] → rank(0-indexed, 最小順位) = [0,0,2,3,3]
    // n=5 → percentile = rank/(n-1)*100 = [0,0,50,75,75]
    // stars は全員同値（=タイブレークなし・starRank は全員 0）なので gemIndex = dependentRank
    const items = [
      { registry: 'npm', packageName: 'p1', repositoryFullName: 'o/p1', dependentCount: 30, stars: 5 },
      { registry: 'npm', packageName: 'p2', repositoryFullName: 'o/p2', dependentCount: 30, stars: 5 },
      { registry: 'npm', packageName: 'p3', repositoryFullName: 'o/p3', dependentCount: 20, stars: 5 },
      { registry: 'npm', packageName: 'p4', repositoryFullName: 'o/p4', dependentCount: 10, stars: 5 },
      { registry: 'npm', packageName: 'p5', repositoryFullName: 'o/p5', dependentCount: 10, stars: 5 },
    ]
    const result = recomputeRanks(items)
    const byName = Object.fromEntries(result.map((r) => [r.packageName, r.gemIndex]))
    expect(byName.p1).toBe(0)
    expect(byName.p2).toBe(0)
    expect(byName.p3).toBe(50)
    expect(byName.p4).toBe(75)
    expect(byName.p5).toBe(75)
  })

  it('n===1 のときは dependentRank・starRank ともに 0 → gemIndex は 0', () => {
    const items = [
      { registry: 'npm', packageName: 'solo', repositoryFullName: 'o/solo', dependentCount: 999, stars: 0 },
    ]
    const result = recomputeRanks(items)
    expect(result).toHaveLength(1)
    expect(result[0].gemIndex).toBe(0)
  })

  it('レジストリ別に閉じて計算する（他レジストリの分布に影響されない）', () => {
    // npm: 2件（極端な値）/ pypi: 1件（単独=0）。npm の極端な値に pypi の結果が引きずられないことを確認する。
    const items = [
      { registry: 'npm', packageName: 'big', repositoryFullName: 'o/big', dependentCount: 1000000, stars: 0 },
      { registry: 'npm', packageName: 'small', repositoryFullName: 'o/small', dependentCount: 1, stars: 1000000 },
      { registry: 'pypi', packageName: 'lonely', repositoryFullName: 'o/lonely', dependentCount: 42, stars: 42 },
    ]
    const result = recomputeRanks(items)
    const lonely = result.find((r) => r.packageName === 'lonely')
    expect(lonely.gemIndex).toBe(0)
  })

  it('gemIndex は小数第 2 位に丸める', () => {
    // n=3 → percentile 刻みは 0, 50, 100 のいずれか（3件では割り切れる範囲だが、
    // dependentRank と starRank の組み合わせで小数が出るケースを作る）
    const items = [
      { registry: 'npm', packageName: 'p1', repositoryFullName: 'o/1', dependentCount: 3, stars: 1 },
      { registry: 'npm', packageName: 'p2', repositoryFullName: 'o/2', dependentCount: 2, stars: 2 },
      { registry: 'npm', packageName: 'p3', repositoryFullName: 'o/3', dependentCount: 1, stars: 3 },
    ]
    const result = recomputeRanks(items)
    for (const r of result) {
      expect(Number.isInteger(r.gemIndex * 100)).toBe(true)
    }
  })
})

describe('buildPool', () => {
  it('normalize → 汚染フィルタ → dedupe（横断）→ recomputeRanks（レジストリ別）→ gemIndex 昇順の統合フロー', () => {
    const collected = [
      {
        registry: 'npm',
        packages: [
          // 正常: 高被依存・低star（過小評価候補）
          {
            name: 'underrated-lib',
            repository_url: 'https://github.com/acme/underrated',
            dependent_packages_count: 5000,
            repo_metadata: { stargazers_count: 3 },
          },
          // 正常: 低被依存・高star
          {
            name: 'famous-lib',
            repository_url: 'https://github.com/acme/famous',
            dependent_packages_count: 10,
            repo_metadata: { stargazers_count: 50000 },
          },
          // 汚染: stars=0 かつ高被依存 → 除外される
          {
            name: 'mirror-pkg',
            repository_url: 'https://github.com/acme/mirror',
            dependent_packages_count: 999999,
            repo_metadata: { stargazers_count: 0 },
          },
          // 欠損: repo_metadata なし → 除外される
          {
            name: 'no-meta-pkg',
            repository_url: 'https://github.com/acme/nometa',
            dependent_packages_count: 100,
          },
          // GitHub 以外 → 除外される
          {
            name: 'gitlab-pkg',
            repository_url: 'https://gitlab.com/acme/gl',
            dependent_packages_count: 100,
            repo_metadata: { stargazers_count: 10 },
          },
        ],
      },
      {
        registry: 'pypi',
        packages: [
          // npm の underrated-lib と同一 repo（dedupe 対象・こちらが flagship）
          {
            name: 'underrated-lib-py',
            repository_url: 'https://github.com/acme/underrated',
            dependent_packages_count: 8000,
            repo_metadata: { stargazers_count: 3 },
          },
        ],
      },
    ]

    const result = buildPool(collected)

    // 汚染・欠損・非 GitHub は落ちている
    expect(result.some((r) => r.packageName === 'mirror-pkg')).toBe(false)
    expect(result.some((r) => r.packageName === 'no-meta-pkg')).toBe(false)
    expect(result.some((r) => r.packageName === 'gitlab-pkg')).toBe(false)

    // dedupe: underrated 系は 1 件だけ・pypi 側（dependentCount 大）が flagship
    const underrated = result.filter((r) => r.repositoryFullName === 'acme/underrated')
    expect(underrated).toHaveLength(1)
    expect(underrated[0].packageName).toBe('underrated-lib-py')
    expect(underrated[0].registry).toBe('pypi')

    // gemIndex 昇順で返す
    const gemIndexes = result.map((r) => r.gemIndex)
    expect(gemIndexes).toEqual([...gemIndexes].sort((a, b) => a - b))
  })
})

describe('poolStats', () => {
  it('件数・レジストリ別内訳・star=0 比率・gemIndex 範囲を返す', () => {
    const candidates = [
      { registry: 'npm', packageName: 'a', repositoryFullName: 'o/a', dependentCount: 1, stars: 0, gemIndex: -10 },
      { registry: 'npm', packageName: 'b', repositoryFullName: 'o/b', dependentCount: 1, stars: 5, gemIndex: 20 },
      { registry: 'pypi', packageName: 'c', repositoryFullName: 'o/c', dependentCount: 1, stars: 0, gemIndex: 0 },
    ]
    const stats = poolStats(candidates)
    expect(stats.total).toBe(3)
    expect(stats.byRegistry).toEqual({ npm: 2, pypi: 1 })
    expect(stats.starZeroRatio).toBeCloseTo(2 / 3)
    expect(stats.gemIndexRange).toEqual([-10, 20])
  })

  it('空配列でも例外を投げない', () => {
    const stats = poolStats([])
    expect(stats.total).toBe(0)
    expect(stats.starZeroRatio).toBe(0)
    expect(stats.gemIndexRange).toEqual([0, 0])
  })
})
