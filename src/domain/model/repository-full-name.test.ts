import { describe, expect, it } from 'vitest'

import { DomainValidationError } from '../errors'
import {
  MAX_OWNER_LENGTH,
  MAX_REPO_LENGTH,
  isLenientRepositoryFullName,
  ownerOf,
  repoOf,
  repositoryFullName,
  tryParseLenientRepositoryFullName,
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

describe('isLenientRepositoryFullName / tryParseLenientRepositoryFullName（許容版）', () => {
  // 🔴 実データ（GitHub リポジトリ 62,783 件・#141 系の全件突合）に実在する
  //    「owner が末尾ハイフンで終わる」リポジトリ。厳格版（`tryRepositoryFullName`）は
  //    これらを拒否するため、許容版が別に必要な理由そのものをここで固定する。
  const TRAILING_HYPHEN_OWNER_SAMPLES: ReadonlyArray<readonly [string, string]> = [
    ['Qix-/color-convert', 'Qix-'],
    ['qix-/node-is-arrayish', 'qix-'],
    ['main--/rust-timerfd', 'main--'],
  ]

  it.each(TRAILING_HYPHEN_OWNER_SAMPLES)(
    '末尾ハイフン owner の実データ %s は許容版で受理し、厳格版で拒否する',
    (fullName, owner) => {
      const repo = fullName.slice(owner.length + 1)

      expect(isLenientRepositoryFullName(fullName)).toBe(true)
      expect(tryParseLenientRepositoryFullName(fullName)).toEqual({ owner, name: repo })

      expect(() => repositoryFullName(owner, repo)).toThrow(DomainValidationError)
      expect(tryRepositoryFullName(owner, repo)).toBeNull()
    },
  )

  it.each(['./x', 'x/..', 'a/.', '../..'])(
    'ドットセグメントを含む %s は許容版でも拒否する',
    (value) => {
      expect(isLenientRepositoryFullName(value)).toBe(false)
      expect(tryParseLenientRepositoryFullName(value)).toBeNull()
    },
  )

  it('通常の値は許容版・厳格版のどちらでも受理する', () => {
    expect(isLenientRepositoryFullName('facebook/react')).toBe(true)
    expect(tryParseLenientRepositoryFullName('facebook/react')).toEqual({
      owner: 'facebook',
      name: 'react',
    })
    expect(tryRepositoryFullName('facebook', 'react')).toBe('facebook/react')
  })

  it('スラッシュが無い・空白を含む・2 分割できない値は許容版でも拒否する', () => {
    expect(isLenientRepositoryFullName('owner')).toBe(false)
    expect(isLenientRepositoryFullName('owner/')).toBe(false)
    expect(isLenientRepositoryFullName('/repo')).toBe(false)
    expect(isLenientRepositoryFullName('owner repo')).toBe(false)
    expect(tryParseLenientRepositoryFullName('a/b/c')).toBeNull()
  })
})
