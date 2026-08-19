import { describe, expect, it } from 'vitest'

import { DomainValidationError } from '../errors'
import {
  MAX_OWNER_LENGTH,
  MAX_REPO_LENGTH,
  ownerOf,
  repoOf,
  repositoryFullName,
  tryRepositoryFullName,
} from './repository-full-name'

describe('repositoryFullName', () => {
  it('正しい owner/repo から "owner/repo" を組み立てる', () => {
    expect(repositoryFullName('facebook', 'react')).toBe('facebook/react')
  })

  it('リポジトリ名にドットを含むケースを許容する（#97）', () => {
    expect(repositoryFullName('someone', 'someone.github.io')).toBe('someone/someone.github.io')
  })

  it('リポジトリ名の . _ - を許容する', () => {
    expect(repositoryFullName('owner', 'my-repo_name.js')).toBe('owner/my-repo_name.js')
  })

  it('owner の空文字を拒否する', () => {
    expect(() => repositoryFullName('', 'react')).toThrow(DomainValidationError)
  })

  it('repo の空文字を拒否する', () => {
    expect(() => repositoryFullName('facebook', '')).toThrow(DomainValidationError)
  })

  it('owner の先頭・末尾のハイフンを拒否する', () => {
    expect(() => repositoryFullName('-facebook', 'react')).toThrow(DomainValidationError)
    expect(() => repositoryFullName('facebook-', 'react')).toThrow(DomainValidationError)
  })

  it('owner の許可されない文字（スラッシュ含む）を拒否する', () => {
    expect(() => repositoryFullName('face/book', 'react')).toThrow(DomainValidationError)
    expect(() => repositoryFullName('face book', 'react')).toThrow(DomainValidationError)
  })

  it('repo の許可されない文字を拒否する', () => {
    expect(() => repositoryFullName('facebook', 're/act')).toThrow(DomainValidationError)
    expect(() => repositoryFullName('facebook', 're act')).toThrow(DomainValidationError)
  })

  it('repo が "." または ".." のみは拒否する', () => {
    expect(() => repositoryFullName('facebook', '.')).toThrow(DomainValidationError)
    expect(() => repositoryFullName('facebook', '..')).toThrow(DomainValidationError)
  })

  it('owner の長さ上限を超える値を拒否する', () => {
    expect(() => repositoryFullName('a'.repeat(MAX_OWNER_LENGTH + 1), 'react')).toThrow(
      DomainValidationError,
    )
  })

  it('repo の長さ上限を超える値を拒否する', () => {
    expect(() => repositoryFullName('facebook', 'a'.repeat(MAX_REPO_LENGTH + 1))).toThrow(
      DomainValidationError,
    )
  })
})

describe('tryRepositoryFullName', () => {
  it('不正値は null に倒す（URL 由来の値を 500 にしない）', () => {
    expect(tryRepositoryFullName('', 'react')).toBeNull()
    expect(tryRepositoryFullName(undefined, 'react')).toBeNull()
    expect(tryRepositoryFullName('facebook', null)).toBeNull()
    expect(tryRepositoryFullName('facebook', 'react')).toBe('facebook/react')
  })
})

describe('ownerOf / repoOf', () => {
  it('組み立てた RepositoryFullName から owner と repo を取り出せる', () => {
    const name = repositoryFullName('someone', 'someone.github.io')
    expect(ownerOf(name)).toBe('someone')
    expect(repoOf(name)).toBe('someone.github.io')
  })
})
