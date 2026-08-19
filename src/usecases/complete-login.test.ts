import { describe, expect, it, vi } from 'vitest'

import type { AuthPort } from '../domain/ports/auth-port'
import { makeCompleteLogin } from './complete-login'

function fakeAuthPort(overrides: Partial<AuthPort> = {}): AuthPort {
  return {
    exchangeAuthorizationCode: vi.fn().mockResolvedValue({ accessToken: 'gho_fake' }),
    ...overrides,
  }
}

describe('makeCompleteLogin', () => {
  it('AuthPort.exchangeAuthorizationCode へ code をそのまま渡す', async () => {
    const auth = fakeAuthPort()
    const completeLogin = makeCompleteLogin({ auth })

    const result = await completeLogin('auth-code-1')

    expect(auth.exchangeAuthorizationCode).toHaveBeenCalledWith('auth-code-1')
    expect(result).toEqual({ accessToken: 'gho_fake' })
  })

  it('AuthPort が例外を投げたらそのまま伝播する', async () => {
    const auth = fakeAuthPort({
      exchangeAuthorizationCode: vi.fn().mockRejectedValue(new Error('upstream failed')),
    })
    const completeLogin = makeCompleteLogin({ auth })

    await expect(completeLogin('bad-code')).rejects.toThrow('upstream failed')
  })
})
