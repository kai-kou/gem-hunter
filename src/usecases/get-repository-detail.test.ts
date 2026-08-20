import { describe, expect, it } from 'vitest'

import type { RepositoryDetail } from '../domain/model/repository'
import type { RepositoryFullName } from '../domain/model/repository-full-name'
import type { RepositoryQueryPort } from '../domain/ports/repository-query-port'
import { makeGetRepositoryDetail } from './get-repository-detail'

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
  topics: ['javascript', 'react'],
  htmlUrl: 'https://github.com/facebook/react',
}

function fakePort(received: RepositoryFullName[], result: RepositoryDetail | null): RepositoryQueryPort {
  return {
    async search() {
      throw new Error('unused in this test')
    },
    async findDetail(name) {
      received.push(name)
      return result
    },
  }
}

describe('getRepositoryDetail', () => {
  it('owner/repo を値オブジェクトへ変換してポートへ渡す', async () => {
    const received: RepositoryFullName[] = []
    const getRepositoryDetail = makeGetRepositoryDetail({ repos: fakePort(received, detail) })

    const result = await getRepositoryDetail({ owner: 'facebook', repo: 'react' })

    expect(received).toHaveLength(1)
    expect(received[0]).toBe('facebook/react')
    expect(result?.fullName).toBe('facebook/react')
  })

  it('ポートが null を返したら null を返す（存在しないリポジトリ）', async () => {
    const received: RepositoryFullName[] = []
    const getRepositoryDetail = makeGetRepositoryDetail({ repos: fakePort(received, null) })

    const result = await getRepositoryDetail({ owner: 'facebook', repo: 'does-not-exist' })

    expect(result).toBeNull()
  })

  it('不正な owner/repo（URL 由来）ではポートを呼ばずに null を返す', async () => {
    const received: RepositoryFullName[] = []
    const getRepositoryDetail = makeGetRepositoryDetail({ repos: fakePort(received, detail) })

    const result = await getRepositoryDetail({ owner: '', repo: 'react' })

    expect(result).toBeNull()
    expect(received).toHaveLength(0)
  })

  it('不正な repo（URL 由来）ではポートを呼ばずに null を返す', async () => {
    const received: RepositoryFullName[] = []
    const getRepositoryDetail = makeGetRepositoryDetail({ repos: fakePort(received, detail) })

    const result = await getRepositoryDetail({ owner: 'facebook', repo: '' })

    expect(result).toBeNull()
    expect(received).toHaveLength(0)
  })
})
