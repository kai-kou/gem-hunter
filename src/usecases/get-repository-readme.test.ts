import { describe, expect, it } from 'vitest'

import type { RepositoryDetail } from '../domain/model/repository'
import type { RepositoryFullName } from '../domain/model/repository-full-name'
import type { RepositoryQueryPort } from '../domain/ports/repository-query-port'
import { makeGetRepositoryReadme } from './get-repository-readme'

const detail: RepositoryDetail = {
  id: 10270250,
  fullName: 'facebook/react',
  name: 'react',
  owner: { login: 'facebook', avatarUrl: 'https://avatars.githubusercontent.com/u/69631?v=4' },
  description: 'The library for web and native user interfaces.',
  primaryLanguage: 'JavaScript',
  stars: 233000,
  watcherCount: 6600,
  forkCount: 48000,
  openIssueCount: 1200,
  lastPushedAt: new Date('2026-08-15T03:00:00Z'),
  topics: ['javascript', 'react'],
  htmlUrl: 'https://github.com/facebook/react',
}

function fakePort(opts: {
  detailResult: RepositoryDetail | null
  readmeResult: string | null
  findDetailCalls: RepositoryFullName[]
  findReadmeCalls: RepositoryFullName[]
}): RepositoryQueryPort {
  return {
    async search() {
      throw new Error('unused in this test')
    },
    async findDetail(name) {
      opts.findDetailCalls.push(name)
      return opts.detailResult
    },
    async findReadme(name) {
      opts.findReadmeCalls.push(name)
      return opts.readmeResult
    },
  }
}

describe('getRepositoryReadme', () => {
  it('detail が見つかれば README を取得して返す', async () => {
    const findDetailCalls: RepositoryFullName[] = []
    const findReadmeCalls: RepositoryFullName[] = []
    const getRepositoryReadme = makeGetRepositoryReadme({
      repos: fakePort({
        detailResult: detail,
        readmeResult: '<h1>README</h1>',
        findDetailCalls,
        findReadmeCalls,
      }),
    })

    const result = await getRepositoryReadme({ owner: 'facebook', repo: 'react' })

    expect(result).toBe('<h1>README</h1>')
    expect(findDetailCalls).toHaveLength(1)
    expect(findReadmeCalls).toHaveLength(1)
  })

  it('detail が null（存在しない・非公開）なら findReadme を呼ばずに null を返す（NFR-33 / AC-12）', async () => {
    const findDetailCalls: RepositoryFullName[] = []
    const findReadmeCalls: RepositoryFullName[] = []
    const getRepositoryReadme = makeGetRepositoryReadme({
      repos: fakePort({
        detailResult: null,
        readmeResult: '<h1>絶対に出てはいけない README</h1>',
        findDetailCalls,
        findReadmeCalls,
      }),
    })

    const result = await getRepositoryReadme({ owner: 'acme', repo: 'secret' })

    expect(result).toBeNull()
    expect(findDetailCalls).toHaveLength(1)
    expect(findReadmeCalls).toHaveLength(0)
  })

  it('detail はあるが README が無い（404）リポジトリは null を返す', async () => {
    const findDetailCalls: RepositoryFullName[] = []
    const findReadmeCalls: RepositoryFullName[] = []
    const getRepositoryReadme = makeGetRepositoryReadme({
      repos: fakePort({
        detailResult: detail,
        readmeResult: null,
        findDetailCalls,
        findReadmeCalls,
      }),
    })

    const result = await getRepositoryReadme({ owner: 'facebook', repo: 'react' })

    expect(result).toBeNull()
    expect(findReadmeCalls).toHaveLength(1)
  })

  it('不正な owner/repo（URL 由来）ではポートを一切呼ばずに null を返す', async () => {
    const findDetailCalls: RepositoryFullName[] = []
    const findReadmeCalls: RepositoryFullName[] = []
    const getRepositoryReadme = makeGetRepositoryReadme({
      repos: fakePort({
        detailResult: detail,
        readmeResult: '<h1>README</h1>',
        findDetailCalls,
        findReadmeCalls,
      }),
    })

    const result = await getRepositoryReadme({ owner: '', repo: 'react' })

    expect(result).toBeNull()
    expect(findDetailCalls).toHaveLength(0)
    expect(findReadmeCalls).toHaveLength(0)
  })
})
