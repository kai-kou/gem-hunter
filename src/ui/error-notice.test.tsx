import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { ErrorKind } from '@/src/domain/errors'

import { ErrorNotice } from './error-notice'

/**
 * `ErrorKind` → イラスト画像の割り当て表（仕様・Issue #364・`ui-ux-guidelines.md` §5）。
 * `error-notice.tsx` の `ERROR_ILLUSTRATION` と 1:1 で対応する。ここに独自の期待値を持つことで
 * 実装側の対応表がずれたときにテストが検知する。
 */
const KIND_TO_IMAGE_SRC: Record<ErrorKind, string> = {
  network: '/images/error-network.webp',
  rateLimitPrimary: '/images/error-rate-limit.webp',
  rateLimitSecondary: '/images/error-rate-limit.webp',
  auth: '/images/error-upstream.webp',
  upstream: '/images/error-upstream.webp',
  validation: '/images/error-validation.webp',
  // 404 は新規生成せず既存の not-found.webp を流用する（仕様）。
  notFound: '/images/not-found.webp',
}

describe('ErrorNotice', () => {
  it('role="alert" で本文を伝える（US-24 / US-26 / NFR-12）', () => {
    render(<ErrorNotice kind="network" presentation={{ message: '接続できませんでした。' }} />)

    expect(screen.getByRole('alert')).toHaveTextContent('接続できませんでした。')
  })

  it('再試行手段を渡すとリンクとして表示する（US-24）', () => {
    render(
      <ErrorNotice
        kind="network"
        presentation={{ message: '接続できませんでした。' }}
        retryHref="/ja?q=react"
        retryLabel="再試行"
      />,
    )

    expect(screen.getByRole('link', { name: '再試行' })).toHaveAttribute('href', '/ja?q=react')
  })

  it('再試行手段を渡さなければリンクを出さない', () => {
    render(<ErrorNotice kind="network" presentation={{ message: '接続できませんでした。' }} />)

    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })

  it('loginHint があればログイン導線（文言 + リンク）を出す（US-25 / AR-5）', () => {
    render(
      <ErrorNotice
        kind="rateLimitPrimary"
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
        kind="network"
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
        kind="network"
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
        kind="rateLimitPrimary"
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
        kind="network"
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
        kind="rateLimitPrimary"
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
    render(<ErrorNotice kind="network" presentation={{ message: '接続できませんでした。' }} />)

    expect(screen.getByRole('alert').textContent).toBe('接続できませんでした。')
  })
})

describe('ErrorNotice のイラスト（Issue #364・権威順で #347「エラーには絵を入れない」判定を上書き）', () => {
  it.each(Object.entries(KIND_TO_IMAGE_SRC) as [ErrorKind, string][])(
    '%s は対応するイラスト（%s）を alt="" 単独で描画する（割り当て表・ui-ux-guidelines.md §5）',
    (kind, expectedSrc) => {
      render(<ErrorNotice kind={kind} presentation={{ message: 'エラーが発生しました。' }} />)

      const image = screen.getByAltText('')
      expect(image.tagName).toBe('IMG')
      expect(image).toHaveAttribute('src', expectedSrc)
    },
  )

  it('イラストは中央寄せにする（左寄りにならない・Issue #369・§7.4）', () => {
    render(<ErrorNotice kind="network" presentation={{ message: '接続できませんでした。' }} />)

    expect(screen.getByAltText('')).toHaveClass('mx-auto')
  })

  it('イラストは role="alert" の要素の外（兄弟）に置かれる（読み込み中とは逆の扱い・#359 / §7.4）', () => {
    render(<ErrorNotice kind="network" presentation={{ message: '接続できませんでした。' }} />)

    // #359 は読み込み中のライブリージョン内配置を構造上の例外として許容したが、
    // エラー側（role="alert"）へは波及させない（このテストが固定する）。
    const alert = screen.getByRole('alert')
    expect(alert.querySelectorAll('img')).toHaveLength(0)
    expect(screen.getByAltText('')).toBeInTheDocument()
  })
})
