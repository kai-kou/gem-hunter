import { describe, expect, it } from 'vitest'

import { clientIpOf, hashRateLimitKey } from './rate-limit-key'

describe('clientIpOf', () => {
  it('cf-connecting-ip があれば最優先で使う', () => {
    const headers = new Headers({
      'cf-connecting-ip': '203.0.113.1',
      'x-forwarded-for': '198.51.100.1',
    })
    expect(clientIpOf(headers)).toBe('203.0.113.1')
  })

  it('cf-connecting-ip が無ければ x-forwarded-for の先頭要素を使う（前後の空白は除去）', () => {
    const headers = new Headers({ 'x-forwarded-for': ' 198.51.100.1 , 203.0.113.2' })
    expect(clientIpOf(headers)).toBe('198.51.100.1')
  })

  it('どちらも無ければ null', () => {
    expect(clientIpOf(new Headers())).toBeNull()
  })

  it('どちらも空文字なら null', () => {
    const headers = new Headers({ 'cf-connecting-ip': '', 'x-forwarded-for': '' })
    expect(clientIpOf(headers)).toBeNull()
  })
})

describe('hashRateLimitKey', () => {
  it('同じ (source, salt) は同じ hex を返す', async () => {
    const a = await hashRateLimitKey('203.0.113.1', 'salt-a')
    const b = await hashRateLimitKey('203.0.113.1', 'salt-a')
    expect(a).toBe(b)
  })

  it('salt が違えば別の値になる', async () => {
    const a = await hashRateLimitKey('203.0.113.1', 'salt-a')
    const b = await hashRateLimitKey('203.0.113.1', 'salt-b')
    expect(a).not.toBe(b)
  })

  it('出力は 64 文字の小文字 hex（HMAC-SHA256）', async () => {
    const hash = await hashRateLimitKey('203.0.113.1', 'salt-a')
    expect(hash).toMatch(/^[0-9a-f]{64}$/)
  })

  it('生 IP が出力に含まれない（ドット区切りのまま残らない）', async () => {
    const hash = await hashRateLimitKey('203.0.113.1', 'salt-a')
    expect(hash).not.toContain('203.0.113.1')
    expect(hash).not.toContain('.')
  })
})
