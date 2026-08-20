import { describe, expect, it } from 'vitest'

import { computeDigestDiff } from './digest-diff'

describe('computeDigestDiff', () => {
  it('seen が null（初回訪問 / ストレージ喪失）のとき isFirstVisit: true・newNames は空集合を返す', () => {
    const result = computeDigestDiff(['chalk', 'debug'], null)

    expect(result.isFirstVisit).toBe(true)
    expect(result.newNames.size).toBe(0)
  })

  it('seen があり、前回に無かった packageName だけを newNames に含める', () => {
    const seen = { date: '20260819', packageNames: ['chalk'] }

    const result = computeDigestDiff(['chalk', 'debug', 'lodash'], seen)

    expect(result.isFirstVisit).toBe(false)
    expect(result.newNames.has('chalk')).toBe(false)
    expect(result.newNames.has('debug')).toBe(true)
    expect(result.newNames.has('lodash')).toBe(true)
  })

  it('前回と全く同じ packageName 一覧なら newNames は空集合', () => {
    const seen = { date: '20260819', packageNames: ['chalk', 'debug'] }

    const result = computeDigestDiff(['chalk', 'debug'], seen)

    expect(result.isFirstVisit).toBe(false)
    expect(result.newNames.size).toBe(0)
  })

  it('今回のダイジェストが 0 件でも例外を投げず空集合を返す', () => {
    const seen = { date: '20260819', packageNames: ['chalk'] }

    const result = computeDigestDiff([], seen)

    expect(result.isFirstVisit).toBe(false)
    expect(result.newNames.size).toBe(0)
  })

  it('seen.packageNames が空配列（前回 0 件）のとき、今回の全件が新着になる', () => {
    const seen = { date: '20260819', packageNames: [] }

    const result = computeDigestDiff(['chalk'], seen)

    expect(result.isFirstVisit).toBe(false)
    expect(result.newNames.has('chalk')).toBe(true)
  })
})
