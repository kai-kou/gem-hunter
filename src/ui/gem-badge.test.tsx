import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { GemBadge } from './gem-badge'

describe('GemBadge', () => {
  it('可視のテキストラベルを表示する（色だけで意味を伝えない・WCAG 1.4.1）', () => {
    render(<GemBadge label="Gem" srHint="star の数のわりに、多くのパッケージから使われている候補です" />)

    expect(screen.getByText('Gem')).toBeInTheDocument()
  })

  it('バッジの意味を説明する srHint が支援技術に届く（sr-only でも DOM 上に存在する）', () => {
    render(<GemBadge label="Gem" srHint="star の数のわりに、多くのパッケージから使われている候補です" />)

    const hint = screen.getByText('star の数のわりに、多くのパッケージから使われている候補です')
    expect(hint).toBeInTheDocument()
    // 視覚的には隠すが、アクセシビリティツリーからは外さない（aria-hidden を付けない）。
    expect(hint).toHaveClass('sr-only')
    expect(hint).not.toHaveAttribute('aria-hidden')
  })

  it('ハードコードした色を持たず、セマンティックトークン由来のクラスで着色する（§2.1 / §2.2）', () => {
    const { container } = render(<GemBadge label="Gem" srHint="説明" />)
    const badge = container.firstElementChild

    expect(badge).not.toBeNull()
    const className = badge?.getAttribute('class') ?? ''
    // topics チップ（bg-muted / text-muted-foreground）と区別が付く配色にする。
    expect(className).toContain('bg-accent')
    expect(className).toContain('text-accent-foreground')
    expect(className).not.toContain('bg-muted')
    // 生の色（#rrggbb / oklch / rgb）を className にもインラインスタイルにも書かない。
    expect(className).not.toMatch(/#[0-9a-fA-F]{3,8}|oklch\(|rgb\(/)
    expect(badge?.getAttribute('style')).toBeNull()
  })

  it('フォーカス可能要素にしない（カード全体の ::after クリック領域と競合させない・§4.3）', () => {
    const { container } = render(<GemBadge label="Gem" srHint="説明" />)
    const badge = container.firstElementChild

    expect(badge?.tagName).toBe('SPAN')
    expect(badge).not.toHaveAttribute('tabindex')
  })
})
