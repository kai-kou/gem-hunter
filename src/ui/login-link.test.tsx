import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { LoginLink } from './login-link'

const labels = { login: 'ログイン', logout: 'ログアウト' }

describe('LoginLink', () => {
  it('未ログイン時はログインリンク（/api/auth/login）を表示する', () => {
    render(<LoginLink isLoggedIn={false} labels={labels} />)

    const link = screen.getByRole('link', { name: 'ログイン' })
    expect(link).toHaveAttribute('href', '/api/auth/login')
    expect(screen.queryByRole('button', { name: 'ログアウト' })).not.toBeInTheDocument()
  })

  it('ログイン時はログアウトボタン（POST フォーム経由）を表示する', () => {
    render(<LoginLink isLoggedIn={true} labels={labels} />)

    const button = screen.getByRole('button', { name: 'ログアウト' })
    expect(screen.queryByRole('link', { name: 'ログイン' })).not.toBeInTheDocument()

    const form = button.closest('form')
    expect(form).not.toBeNull()
    expect(form).toHaveAttribute('method', 'post')
    expect(form).toHaveAttribute('action', '/api/auth/logout')
  })

  it('ユーザー名・レート枠数値は表示しない（AC 未記載・YAGNI）', () => {
    render(<LoginLink isLoggedIn={true} labels={labels} />)

    expect(screen.queryByText(/octostub|rate|残り/i)).not.toBeInTheDocument()
  })
})
