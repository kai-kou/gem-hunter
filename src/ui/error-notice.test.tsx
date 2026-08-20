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

  it('再試行導線はタップターゲット要件を満たすボタンとして描画する（ui-ux-guidelines.md §2.4 / §5.2）', () => {
    render(
      <ErrorNotice
        presentation={{ message: '接続できませんでした。' }}
        retryHref="/ja?q=react"
        retryLabel="再試行"
      />,
    )

    const retry = screen.getByRole('link', { name: '再試行' })
    // 素のテキストリンク（高さが --size-control-xs 未満）ではなく Button の size variant を経由する。
    expect(retry).toHaveAttribute('data-slot', 'button')
    expect(retry).toHaveAttribute('data-size', 'xl')
  })

  it('ログイン導線は再試行に次ぐサイズのボタンとして描画する（ui-ux-guidelines.md §2.4 推奨）', () => {
    render(
      <ErrorNotice
        presentation={{
          message: 'リクエストが上限に達しました。',
          loginHint: 'ログインすると上限が増えます。',
        }}
        retryHref="/ja?q=react"
        retryLabel="再試行"
        loginHref="/api/auth/login"
        loginLabel="GitHubでログイン"
      />,
    )

    const login = screen.getByRole('link', { name: 'GitHubでログイン' })
    expect(login).toHaveAttribute('data-slot', 'button')
    expect(login).toHaveAttribute('data-size', 'lg')
  })

  it('サイズは size variant 経由で指定し、className に生の h-* / text-* を書かない（§2.4）', () => {
    render(
      <ErrorNotice
        presentation={{ message: '接続できませんでした。' }}
        retryHref="/ja?q=react"
        retryLabel="再試行"
      />,
    )

    const alert = screen.getByRole('alert')
    // Button の cva が持つ `text-*` は size variant 経由なので対象外（§2.4 の機械検査と同じ境界）。
    const callSiteElements = [alert, ...alert.querySelectorAll('*')].filter(
      (el) => el.getAttribute('data-slot') !== 'button',
    )
    for (const el of callSiteElements) {
      for (const token of Array.from(el.classList)) {
        expect(token).not.toMatch(/^(?:h-\d|text-(?:xs|sm|base|lg|xl|\d))/)
      }
    }
  })

  it('loginHref が無ければ loginHint 自体を出さない（リンクの無い行き止まりを作らない）', () => {
    render(
      <ErrorNotice
        presentation={{
          message: 'リクエストが上限に達しました。',
          loginHint: 'ログインすると上限が増えます。',
        }}
      />,
    )

    expect(screen.getByRole('alert')).not.toHaveTextContent('ログインすると上限が増えます。')
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })

  it('内部情報（スタックトレース等）を独自に足さず、渡された文言だけを表示する（NFR-9）', () => {
    render(<ErrorNotice presentation={{ message: '接続できませんでした。' }} />)

    expect(screen.getByRole('alert').textContent).toBe('接続できませんでした。')
  })
})
