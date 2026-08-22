// pipeline.test.mjs — 変換パイプライン（純関数のみ）のテスト。
// ネットワークに触れない（`fetch` を一切使わない）。SP-17 契約 §4 の全観点を網羅する。

import { describe, expect, it } from 'vitest'
import {
  DEFAULT_MIN_DOWNLOADS_PER_DEPENDENT,
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
    expect(extractGithubFullName('git+https://github.com/lodash/lodash.git')).toBe('lodash/lodash')
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
    downloads: 245000,
    repo_metadata: { stargazers_count: 60000, fork: false },
  }

  it('正常系: NormalizedPackage を返す（downloads・isFork・isMirror を含む）', () => {
    expect(normalizeRecord(validRaw, 'npm')).toEqual({
      registry: 'npm',
      packageName: 'lodash',
      repositoryFullName: 'lodash/lodash',
      dependentCount: 123456,
      stars: 60000,
      downloads: 245000,
      isFork: false,
      isMirror: false,
    })
  })

  it('GitHub 以外の repository_url は null', () => {
    expect(
      normalizeRecord({ ...validRaw, repository_url: 'https://gitlab.com/a/b' }, 'npm'),
    ).toBeNull()
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

  it('downloads が欠落・非数のときは downloads: null', () => {
    const { downloads, ...rest } = validRaw
    expect(normalizeRecord(rest, 'npm')?.downloads).toBeNull()
    expect(normalizeRecord({ ...validRaw, downloads: 'many' }, 'npm')?.downloads).toBeNull()
  })

  it('downloads: 0 は downloads: 0 として残す（null にしない）', () => {
    expect(normalizeRecord({ ...validRaw, downloads: 0 }, 'npm')?.downloads).toBe(0)
  })

  it('repo_metadata.fork === true は isFork: true', () => {
    const raw = { ...validRaw, repo_metadata: { ...validRaw.repo_metadata, fork: true } }
    expect(normalizeRecord(raw, 'npm')?.isFork).toBe(true)
  })

  it('repo_metadata.fork が欠落・非真偽のときは isFork: false', () => {
    const { fork, ...restMeta } = validRaw.repo_metadata
    expect(normalizeRecord({ ...validRaw, repo_metadata: restMeta }, 'npm')?.isFork).toBe(false)
    expect(
      normalizeRecord({ ...validRaw, repo_metadata: { ...restMeta, fork: 'yes' } }, 'npm')?.isFork,
    ).toBe(false)
  })

  it('repo_metadata.mirror_url が非空文字列なら isMirror: true', () => {
    const raw = {
      ...validRaw,
      repo_metadata: {
        ...validRaw.repo_metadata,
        mirror_url: 'https://github.com/upstream/lodash',
      },
    }
    expect(normalizeRecord(raw, 'npm')?.isMirror).toBe(true)
  })

  it('repo_metadata.mirror_url が欠落・空文字のときは isMirror: false', () => {
    expect(normalizeRecord(validRaw, 'npm')?.isMirror).toBe(false)
    const raw = { ...validRaw, repo_metadata: { ...validRaw.repo_metadata, mirror_url: '' } }
    expect(normalizeRecord(raw, 'npm')?.isMirror).toBe(false)
  })
})

describe('isContaminated', () => {
  // 判定ロジックのテストは既定値に依存させない（既定値は実測でチューニングされる運用値であり、
  // 判定ロジックの正しさとは別の関心事。既定値の変更でここが割れないようにする）。
  // 各テストは zeroStarDependentThreshold・minDownloadsPerDependent を明示的に渡す。
  const base = { stars: 5, dependentCount: 100, downloads: 1000, isFork: false, isMirror: false }
  const disableC = { minDownloadsPerDependent: 0 } // A/B だけを見たいテストで C を明示的に無効化する

  // --- A: stars=0 と高被依存数の組み合わせ（既存・維持） ---
  it('A: stars=0 かつ dependentCount が閾値ちょうど → true（境界値は含む）', () => {
    expect(
      isContaminated(
        { ...base, stars: 0, dependentCount: 1000 },
        { zeroStarDependentThreshold: 1000, ...disableC },
      ),
    ).toBe(true)
  })

  it('A: stars=0 かつ dependentCount が閾値未満 → false', () => {
    expect(
      isContaminated(
        { ...base, stars: 0, dependentCount: 999 },
        { zeroStarDependentThreshold: 1000, ...disableC },
      ),
    ).toBe(false)
  })

  it('A: stars > 0 は dependentCount がどれだけ多くても false', () => {
    expect(
      isContaminated(
        { ...base, stars: 1, dependentCount: 999999 },
        { zeroStarDependentThreshold: 1000, ...disableC },
      ),
    ).toBe(false)
  })

  // --- B: fork / mirror（本家の代表リポジトリではない） ---
  it('B: isFork === true は単独で汚染（star・被依存数に関わらず）', () => {
    expect(isContaminated({ ...base, isFork: true }, disableC)).toBe(true)
  })

  it('B: isMirror === true は単独で汚染', () => {
    expect(isContaminated({ ...base, isMirror: true }, disableC)).toBe(true)
  })

  it('B: isFork・isMirror はそれぞれ独立に効く（片方が false でももう片方で汚染）', () => {
    expect(isContaminated({ ...base, isFork: true, isMirror: false }, disableC)).toBe(true)
    expect(isContaminated({ ...base, isFork: false, isMirror: true }, disableC)).toBe(true)
    expect(isContaminated({ ...base, isFork: false, isMirror: false }, disableC)).toBe(false)
  })

  // --- C: ダウンロード比（minDownloadsPerDependent に 0 を渡すと無効） ---
  it('C: minDownloadsPerDependent に 0 を渡すと無効になる（比が低くても汚染にしない）', () => {
    expect(
      isContaminated(
        { ...base, downloads: 130000, dependentCount: 12356 }, // http_crawler 相当・比 ≈ 11
        disableC,
      ),
    ).toBe(false)
  })

  it('C: 閾値を有効化すると、比が閾値未満のパッケージが汚染になる', () => {
    expect(
      isContaminated(
        { ...base, downloads: 130000, dependentCount: 12356 }, // 比 ≈ 10.5
        { minDownloadsPerDependent: 100 },
      ),
    ).toBe(true)
  })

  it('C: 比が閾値ちょうどは非汚染（境界は含まない・"<" 判定）', () => {
    expect(
      isContaminated(
        { ...base, downloads: 1000, dependentCount: 10 }, // 比 = 100 ちょうど
        { minDownloadsPerDependent: 100 },
      ),
    ).toBe(false)
  })

  it('C: downloads === null は汚染扱いにしない（レジストリによる欠落を誤判定しない）', () => {
    expect(
      isContaminated(
        { ...base, downloads: null, dependentCount: 12356 },
        { minDownloadsPerDependent: 100 },
      ),
    ).toBe(false)
  })

  it('C: dependentCount === 0 は 0 除算にならず非汚染', () => {
    expect(
      isContaminated(
        { ...base, downloads: 0, dependentCount: 0 },
        { minDownloadsPerDependent: 100 },
      ),
    ).toBe(false)
  })

  // --- A/B/C の併用（OR） ---
  it('A/B/C はどれか 1 つでも真なら汚染（OR 結合）', () => {
    // B のみ真（A・C は偽）でも汚染になることを確認
    expect(
      isContaminated(
        { ...base, stars: 5, downloads: 999999, dependentCount: 1, isFork: true },
        { zeroStarDependentThreshold: 1000, minDownloadsPerDependent: 1 },
      ),
    ).toBe(true)
  })

  // --- 既定値そのもの（実測較正済み・値を動かすときは実測し直す義務を可視化する） ---
  it('既定値は 12 レジストリ全件スイープの実測較正で 100/100 に決まっている', () => {
    // 実測（94,856 件・上位 20 件の汚染件数）:
    //   zeroStar≥1000 / DL比無効  → プール 99,554 件・上位20件 20/20 がスパム
    //   zeroStar≥100  / DL比無効  → プール 99,106 件・http_crawler 等 3 件が残る
    //   zeroStar≥100  / DL比<100  → プール 94,856 件・上位20件の汚染 0 件（採用・完了条件を満たす最小設定）
    //   zeroStar≥1    / DL比<1000 → 汚染 0 件だが母集団を 2 割削り pypi へ偏る
    expect(DEFAULT_ZERO_STAR_DEPENDENT_THRESHOLD).toBe(100)
    expect(DEFAULT_MIN_DOWNLOADS_PER_DEPENDENT).toBe(100)
  })
})

describe('dedupeByRepository', () => {
  it('同一 repo は dependentCount 最大の flagship を代表にする', () => {
    const items = [
      {
        registry: 'npm',
        packageName: 'ark-bench',
        repositoryFullName: 'arkworks-rs/algebra',
        dependentCount: 3,
        stars: 100,
      },
      {
        registry: 'npm',
        packageName: 'ark-ff',
        repositoryFullName: 'arkworks-rs/algebra',
        dependentCount: 1829,
        stars: 100,
      },
    ]
    const result = dedupeByRepository(items)
    expect(result).toHaveLength(1)
    expect(result[0].packageName).toBe('ark-ff')
  })

  it('dependentCount が同値のときは packageName 昇順で決定論的にタイブレークする（入力順に依存しない）', () => {
    const a = {
      registry: 'npm',
      packageName: 'b-pkg',
      repositoryFullName: 'x/y',
      dependentCount: 100,
      stars: 1,
    }
    const b = {
      registry: 'npm',
      packageName: 'a-pkg',
      repositoryFullName: 'x/y',
      dependentCount: 100,
      stars: 1,
    }
    const c = {
      registry: 'npm',
      packageName: 'c-pkg',
      repositoryFullName: 'x/y',
      dependentCount: 100,
      stars: 1,
    }

    const resultForward = dedupeByRepository([a, b, c])
    const resultReversed = dedupeByRepository([c, b, a])

    expect(resultForward).toHaveLength(1)
    expect(resultForward[0].packageName).toBe('a-pkg')
    expect(resultReversed[0].packageName).toBe('a-pkg')
  })

  it('レジストリ横断で dedupe する（同じ repo が npm と pypi の両方に出る）', () => {
    const npmPkg = {
      registry: 'npm',
      packageName: 'requests-js',
      repositoryFullName: 'psf/requests',
      dependentCount: 50,
      stars: 10,
    }
    const pypiPkg = {
      registry: 'pypi',
      packageName: 'requests',
      repositoryFullName: 'psf/requests',
      dependentCount: 90000,
      stars: 10,
    }
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
      {
        registry: 'npm',
        packageName: 'p1',
        repositoryFullName: 'o/p1',
        dependentCount: 30,
        stars: 5,
      },
      {
        registry: 'npm',
        packageName: 'p2',
        repositoryFullName: 'o/p2',
        dependentCount: 30,
        stars: 5,
      },
      {
        registry: 'npm',
        packageName: 'p3',
        repositoryFullName: 'o/p3',
        dependentCount: 20,
        stars: 5,
      },
      {
        registry: 'npm',
        packageName: 'p4',
        repositoryFullName: 'o/p4',
        dependentCount: 10,
        stars: 5,
      },
      {
        registry: 'npm',
        packageName: 'p5',
        repositoryFullName: 'o/p5',
        dependentCount: 10,
        stars: 5,
      },
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
      {
        registry: 'npm',
        packageName: 'solo',
        repositoryFullName: 'o/solo',
        dependentCount: 999,
        stars: 0,
      },
    ]
    const result = recomputeRanks(items)
    expect(result).toHaveLength(1)
    expect(result[0].gemIndex).toBe(0)
  })

  it('レジストリ別に閉じて計算する（他レジストリの分布に影響されない）', () => {
    // npm: 2件（極端な値）/ pypi: 1件（単独=0）。npm の極端な値に pypi の結果が引きずられないことを確認する。
    const items = [
      {
        registry: 'npm',
        packageName: 'big',
        repositoryFullName: 'o/big',
        dependentCount: 1000000,
        stars: 0,
      },
      {
        registry: 'npm',
        packageName: 'small',
        repositoryFullName: 'o/small',
        dependentCount: 1,
        stars: 1000000,
      },
      {
        registry: 'pypi',
        packageName: 'lonely',
        repositoryFullName: 'o/lonely',
        dependentCount: 42,
        stars: 42,
      },
    ]
    const result = recomputeRanks(items)
    const lonely = result.find((r) => r.packageName === 'lonely')
    expect(lonely.gemIndex).toBe(0)
  })

  it('gemIndex は小数第 2 位に丸める', () => {
    // n=3 → percentile 刻みは 0, 50, 100 のいずれか（3件では割り切れる範囲だが、
    // dependentRank と starRank の組み合わせで小数が出るケースを作る）
    const items = [
      {
        registry: 'npm',
        packageName: 'p1',
        repositoryFullName: 'o/1',
        dependentCount: 3,
        stars: 1,
      },
      {
        registry: 'npm',
        packageName: 'p2',
        repositoryFullName: 'o/2',
        dependentCount: 2,
        stars: 2,
      },
      {
        registry: 'npm',
        packageName: 'p3',
        repositoryFullName: 'o/3',
        dependentCount: 1,
        stars: 3,
      },
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
          // 汚染: fork（本家の代表リポジトリではない） → 除外される
          {
            name: 'forked-pkg',
            repository_url: 'https://github.com/someone/forked-lib',
            dependent_packages_count: 50,
            repo_metadata: { stargazers_count: 2, fork: true },
          },
          // 汚染: mirror（CRAN の doRNG が第三者フォークに紐付いていた実例相当） → 除外される
          {
            name: 'mirrored-pkg',
            repository_url: 'https://github.com/someone/mirror-lib',
            dependent_packages_count: 50,
            repo_metadata: { stargazers_count: 2, mirror_url: 'https://github.com/upstream/lib' },
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
    expect(result.some((r) => r.packageName === 'forked-pkg')).toBe(false)
    expect(result.some((r) => r.packageName === 'mirrored-pkg')).toBe(false)

    // dedupe: underrated 系は 1 件だけ・pypi 側（dependentCount 大）が flagship
    const underrated = result.filter((r) => r.repositoryFullName === 'acme/underrated')
    expect(underrated).toHaveLength(1)
    expect(underrated[0].packageName).toBe('underrated-lib-py')
    expect(underrated[0].registry).toBe('pypi')

    // gemIndex 昇順で返す
    const gemIndexes = result.map((r) => r.gemIndex)
    expect(gemIndexes).toEqual([...gemIndexes].sort((a, b) => a - b))
  })

  it('options.minDownloadsPerDependent を buildPool 経由で通せる', () => {
    const collected = [
      {
        registry: 'rubygems',
        packages: [
          // http_crawler 相当: 被依存 12356・downloads 130000（比 ≈ 10.5）・stars=1（A はすり抜ける）
          {
            name: 'http_crawler',
            repository_url: 'https://github.com/superjagger/http_crawler',
            dependent_packages_count: 12356,
            downloads: 130000,
            repo_metadata: { stargazers_count: 1 },
          },
        ],
      },
    ]

    // オプションで明示的に無効化（0）すると残る
    expect(
      buildPool(collected, { minDownloadsPerDependent: 0 }).some(
        (r) => r.packageName === 'http_crawler',
      ),
    ).toBe(true)

    // 閾値を有効化すると落ちる（実測較正済みの既定値 100 と同じ効き方）
    expect(
      buildPool(collected, { minDownloadsPerDependent: 100 }).some(
        (r) => r.packageName === 'http_crawler',
      ),
    ).toBe(false)
  })
})

describe('poolStats', () => {
  it('件数・レジストリ別内訳・star=0 比率・gemIndex 範囲を返す', () => {
    const candidates = [
      {
        registry: 'npm',
        packageName: 'a',
        repositoryFullName: 'o/a',
        dependentCount: 1,
        stars: 0,
        gemIndex: -10,
        downloads: 100,
      },
      {
        registry: 'npm',
        packageName: 'b',
        repositoryFullName: 'o/b',
        dependentCount: 1,
        stars: 5,
        gemIndex: 20,
        downloads: 200,
      },
      {
        registry: 'pypi',
        packageName: 'c',
        repositoryFullName: 'o/c',
        dependentCount: 1,
        stars: 0,
        gemIndex: 0,
        downloads: 300,
      },
    ]
    const stats = poolStats(candidates)
    expect(stats.total).toBe(3)
    expect(stats.byRegistry).toEqual({ npm: 2, pypi: 1 })
    expect(stats.starZeroRatio).toBeCloseTo(2 / 3)
    expect(stats.gemIndexRange).toEqual([-10, 20])
    // 3 件とも repositoryFullName の owner が 'o' で一致 → 最頻 owner は 'o'・件数 3
    expect(stats.ownerConcentration).toEqual({ owner: 'o', count: 3 })
    expect(stats.nullDownloadsRatio).toBe(0)
  })

  it('nullDownloadsRatio: downloads === null の比率を全体値で返す', () => {
    const candidates = [
      {
        registry: 'npm',
        packageName: 'a',
        repositoryFullName: 'o/a',
        dependentCount: 1,
        stars: 1,
        gemIndex: 0,
        downloads: null,
      },
      {
        registry: 'npm',
        packageName: 'b',
        repositoryFullName: 'o/b',
        dependentCount: 1,
        stars: 1,
        gemIndex: 0,
        downloads: 500,
      },
      {
        registry: 'maven',
        packageName: 'c',
        repositoryFullName: 'o/c',
        dependentCount: 1,
        stars: 1,
        gemIndex: 0,
        downloads: null,
      },
      {
        registry: 'maven',
        packageName: 'd',
        repositoryFullName: 'o/d',
        dependentCount: 1,
        stars: 1,
        gemIndex: 0,
        downloads: null,
      },
    ]
    const stats = poolStats(candidates)
    expect(stats.nullDownloadsRatio).toBeCloseTo(3 / 4)
  })

  it('ownerConcentration: 上位 100 件（gemIndex 昇順）内で最頻 GitHub owner とその件数を返す', () => {
    // rubygems スパム farm 相当: 同一オーナーの機械生成パッケージ群が上位を占拠していないかの観測値
    // （フィルタとしては使わない・値を返すだけ）。
    const spam = Array.from({ length: 12 }, (_, i) => ({
      registry: 'rubygems',
      packageName: `spam${i}`,
      repositoryFullName: `superjagger/spam${i}`,
      dependentCount: 500,
      stars: 1,
      gemIndex: -90 - i,
    }))
    const others = Array.from({ length: 5 }, (_, i) => ({
      registry: 'npm',
      packageName: `ok${i}`,
      repositoryFullName: `acme/ok${i}`,
      dependentCount: 100,
      stars: 50,
      gemIndex: -10 - i,
    }))
    const stats = poolStats([...others, ...spam])
    expect(stats.ownerConcentration).toEqual({ owner: 'superjagger', count: 12 })
  })

  it('ownerConcentration は gemIndex 上位 100 件だけを見る（101 件目以降・入力順は無視）', () => {
    // gemIndex 0〜99（上位100件）は ownerA、gemIndex 1000〜1019（下位20件）は ownerB。
    // 入力順をシャッフルしても poolStats 内で gemIndex 昇順に並べ替えてから上位 100 件を切り出す。
    const topOwnerA = Array.from({ length: 100 }, (_, i) => ({
      registry: 'npm',
      packageName: `a${i}`,
      repositoryFullName: `ownerA/a${i}`,
      dependentCount: 1,
      stars: 1,
      gemIndex: i,
    }))
    const bottomOwnerB = Array.from({ length: 20 }, (_, i) => ({
      registry: 'npm',
      packageName: `b${i}`,
      repositoryFullName: `ownerB/b${i}`,
      dependentCount: 1,
      stars: 1,
      gemIndex: 1000 + i,
    }))
    const stats = poolStats([...bottomOwnerB, ...topOwnerA])
    expect(stats.ownerConcentration).toEqual({ owner: 'ownerA', count: 100 })
  })

  it('ownerConcentration: 件数が同値のときは owner 名昇順で決定論的に選ぶ', () => {
    const items = [
      {
        registry: 'npm',
        packageName: 'x1',
        repositoryFullName: 'zeta/x1',
        dependentCount: 1,
        stars: 1,
        gemIndex: 0,
      },
      {
        registry: 'npm',
        packageName: 'x2',
        repositoryFullName: 'alpha/x2',
        dependentCount: 1,
        stars: 1,
        gemIndex: 1,
      },
    ]
    const stats = poolStats(items)
    expect(stats.ownerConcentration).toEqual({ owner: 'alpha', count: 1 })
  })

  it('空配列でも例外を投げない', () => {
    const stats = poolStats([])
    expect(stats.total).toBe(0)
    expect(stats.starZeroRatio).toBe(0)
    expect(stats.gemIndexRange).toEqual([0, 0])
    expect(stats.ownerConcentration).toBeNull()
    expect(stats.nullDownloadsRatio).toBe(0)
  })
})
