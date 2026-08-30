/**
 * Issue #276 の回帰テスト。**本番の候補プール生成が Gem Index の共有正本を実際に経由しているか**
 * だけを検証する（式そのものの正しさは `pipeline.test.mjs` の固定値テストが担保する）。
 *
 * 🔴 **なぜ値の一致で検証しないのか**: 期待値を `computeGemIndexValue` で計算すると、実装が
 * 共有正本を捨てて `dependentRank - starRank` をインライン再実装しても両辺が一致し、
 * **Issue #276 が防ごうとした先祖返りそのものを検知できない**（PR #689 のセルフレビューで実測。
 * 当該変異を入れても 42/42 件が通過した）。よってここでは共有正本をスパイに差し替え、
 * `restratifyByRegistry` が **その関数を呼んだ事実** をアサートする。
 *
 * 🔵 モジュール全体をモックするため、他のテストへ影響しないよう **専用ファイル** に分離している。
 */

import { describe, expect, it, vi } from 'vitest'

const { computeGemIndexValueSpy } = vi.hoisted(() => ({
  computeGemIndexValueSpy: vi.fn((dependentRank, starRank) => dependentRank - starRank),
}))

vi.mock('../../src/domain/model/gem-index.rules.mjs', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, computeGemIndexValue: computeGemIndexValueSpy }
})

const { restratifyByRegistry } = await import('./pipeline.mjs')

/** 3 件・レジストリ 1 つ。ランクが 0 / 50 / 100 に割れる最小の母集団。 */
const INPUT = [
  { registry: 'npm', packageName: 'a', repositoryFullName: 'o/a', dependentCount: 100, stars: 1 },
  { registry: 'npm', packageName: 'b', repositoryFullName: 'o/b', dependentCount: 50, stars: 50 },
  { registry: 'npm', packageName: 'c', repositoryFullName: 'o/c', dependentCount: 10, stars: 100 },
]

describe('restratifyByRegistry と Gem Index 共有正本の結線', () => {
  it('🔴 レコードごとに共有正本の computeGemIndexValue を呼ぶ（インライン再実装への先祖返りを検知する）', () => {
    computeGemIndexValueSpy.mockClear()

    const records = restratifyByRegistry(INPUT)

    expect(records).toHaveLength(3)
    expect(computeGemIndexValueSpy).toHaveBeenCalledTimes(3)
  })

  it('🔴 渡す引数は (dependentRank, starRank) の順で、出力のランクと一致する', () => {
    computeGemIndexValueSpy.mockClear()

    const records = restratifyByRegistry(INPUT)

    // 引数の順序が入れ替わると Gem Index の符号が反転する（過小評価と過大評価が逆になる）。
    for (const record of records) {
      expect(computeGemIndexValueSpy).toHaveBeenCalledWith(record.dependentRank, record.starRank)
    }
  })

  it('🔴 共有正本の戻り値が gemIndex に反映される（丸めだけを被せて使う）', () => {
    computeGemIndexValueSpy.mockClear()
    // 共有正本を差し替えれば出力も変わる = 本当にこの関数の結果を使っている。
    computeGemIndexValueSpy.mockReturnValue(-42.128)

    const records = restratifyByRegistry(INPUT)

    // round2（小数第 2 位）だけが被さる。
    expect(records.map((r) => r.gemIndex)).toEqual([-42.13, -42.13, -42.13])

    computeGemIndexValueSpy.mockImplementation(
      (dependentRank, starRank) => dependentRank - starRank,
    )
  })
})
