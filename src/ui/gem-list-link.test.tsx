import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { GemListLink } from './gem-list-link'

describe('GemListLink', () => {
  it('渡された href と文言でリンクを描画する（href の組み立ては呼び出し側の責務）', () => {
    render(<GemListLink href="/ja/gems?q=react" label="この検索語で Gem 一覧を見る" />)

    expect(screen.getByRole('link', { name: 'この検索語で Gem 一覧を見る' })).toHaveAttribute(
      'href',
      '/ja/gems?q=react',
    )
  })

  it('フォーカスリングは ring-3 パターンに揃える（ui-ux-guidelines §7.3・ghost ボタン由来）', () => {
    render(<GemListLink href="/ja/gems" label="Gem 一覧" />)

    const link = screen.getByRole('link', { name: 'Gem 一覧' })
    // outline-none は必ず focus-visible:ring-* と対で書く（§7.3）
    expect(link.className).toContain('focus-visible:ring-3')
    expect(link.className).toContain('focus-visible:ring-ring')
  })

  it('ghost ボタンのクラスが当たっている（class 名の部分一致で判定）', () => {
    render(<GemListLink href="/ja/gems" label="Gem 一覧" />)

    const link = screen.getByRole('link', { name: 'Gem 一覧' })
    expect(link.className).toContain('hover:bg-muted')
    expect(link.className).toContain('h-(--size-control-md)')
  })

  it('アイコンは装飾として描画され、アクセシブルネームは label のみになる', () => {
    render(<GemListLink href="/ja/gems" label="Gem 一覧" />)

    const link = screen.getByRole('link', { name: 'Gem 一覧' })
    const icon = link.querySelector('svg')
    expect(icon).not.toBeNull()
    expect(icon).toHaveAttribute('aria-hidden', 'true')
  })
})
