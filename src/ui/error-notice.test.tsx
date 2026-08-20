import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ErrorNotice } from './error-notice'

describe('ErrorNotice', () => {
  it('role="alert" で本文を伝える（US-24 / US-26 / NFR-12）', () => {
    render(<ErrorNotice presentation={{ message: '接続できませんでした。' }} />)

    expect(screen.getByRole('alert')).toHaveTextContent('接続できませんでした。')
  })

  it('再試行手段を渡すとリンクとして表示する（US-24）', () => {
    render(
      <ErrorNotice
        presentation={{ message: '接続できませんでした。' }}
        retryHref="/ja?q=react"
        retryLabel="再試行"
      />,
    )

    expect(screen.getByRole('link', { name: '再試行' })).toHaveAttribute('href', '/ja?q=react')
  })

  it('再試行手段を渡さなければリンクを出さない', () => {
    render(<ErrorNotice presentation={{ message: '接続できませんでした。' }} />)

    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })

  it('loginHint があればログイン導線（文言 + リンク）を出す（US-25 / AR-5）', () => {
    render(
      <ErrorNotice
        presentation={{
          message: 'リクエストが上限に達しました。',
          loginHint: 'ログインすると上限が増えます。',
        }}
        loginHref="/api/auth/login"
        loginLabel="GitHubでログイン"
      />,
    )

    expect(screen.getByRole('alert')).toHaveTextContent('ログインすると上限が増えます。')
    expect(screen.getByRole('link', { name: 'GitHubでログイン' })).toHaveAttribute(
      'href',
      '/api/auth/login',
    )
  })

  it('loginHint が無ければログインリンクは出さない（レート制限以外のエラー）', () => {
    render(
      <ErrorNotice
        presentation={{ message: '接続できませんでした。' }}
        loginHref="/api/auth/login"
        loginLabel="GitHubでログイン"
      />,
    )

    expect(screen.queryByRole('link', { name: 'GitHubでログイン' })).not.toBeInTheDocument()
  })

  it('内部情報（スタックトレース等）を独自に足さず、渡された文言だけを表示する（NFR-9）', () => {
    render(<ErrorNotice presentation={{ message: '接続できませんでした。' }} />)

    expect(screen.getByRole('alert').textContent).toBe('接続できませんでした。')
  })
})
