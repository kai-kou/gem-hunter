import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ReadmeSection, type ReadmeSectionLabels } from './readme-section'

const labels: ReadmeSectionLabels = {
  heading: 'README',
  unavailable: 'README を表示できませんでした。',
  viewOnGithub: 'GitHub で README を読む',
  opensInNewTab: '（新しいタブで開きます）',
}

const HTML_URL = 'https://github.com/facebook/react'

describe('ReadmeSection', () => {
  it('見出しを h2 として表示する', async () => {
    const element = await ReadmeSection({
      readmePromise: Promise.resolve(null),
      htmlUrl: HTML_URL,
      labels,
    })
    render(element)

    expect(screen.getByRole('heading', { name: 'README', level: 2 })).toBeInTheDocument()
  })

  it('README が取得できたら本文をサニタイズして描画する', async () => {
    const element = await ReadmeSection({
      readmePromise: Promise.resolve('<h1>Title</h1><p>hello</p>'),
      htmlUrl: HTML_URL,
      labels,
    })
    render(element)

    expect(screen.getByText('hello')).toBeInTheDocument()
    // 見出しは +2 シフトされる（h1 → h3）
    expect(screen.getByRole('heading', { name: 'Title', level: 3 })).toBeInTheDocument()
  })

  it('README 本文の XSS ベクタはサニタイズされて描画に混ざらない', async () => {
    const element = await ReadmeSection({
      readmePromise: Promise.resolve('<p>hello</p><script>window.__hacked = true</script>'),
      htmlUrl: HTML_URL,
      labels,
    })
    const { container } = render(element)

    expect(container.innerHTML).not.toContain('<script')
  })

  it('README が null（不在・private・404）なら本文なし + 案内文言のみ描画する', async () => {
    const element = await ReadmeSection({
      readmePromise: Promise.resolve(null),
      htmlUrl: HTML_URL,
      labels,
    })
    render(element)

    expect(screen.getByText(labels.unavailable)).toBeInTheDocument()
  })

  it('readmePromise が例外を投げても詳細ページ全体を落とさず案内文言のみ描画する（NFR-9）', async () => {
    const element = await ReadmeSection({
      readmePromise: Promise.reject(new Error('upstream boom')),
      htmlUrl: HTML_URL,
      labels,
    })
    render(element)

    expect(screen.getByText(labels.unavailable)).toBeInTheDocument()
    // 🔴 内部エラー文言（Error のメッセージ）が画面に出ない
    expect(screen.queryByText(/upstream boom/)).not.toBeInTheDocument()
  })

  it('GitHub で読むリンクは常に描画される（本文あり・なし問わず）', async () => {
    const withReadme = await ReadmeSection({
      readmePromise: Promise.resolve('<p>hello</p>'),
      htmlUrl: HTML_URL,
      labels,
    })
    const { unmount } = render(withReadme)
    expect(screen.getByRole('link', { name: new RegExp(labels.viewOnGithub) })).toHaveAttribute(
      'href',
      HTML_URL,
    )
    unmount()

    const withoutReadme = await ReadmeSection({
      readmePromise: Promise.resolve(null),
      htmlUrl: HTML_URL,
      labels,
    })
    render(withoutReadme)
    expect(screen.getByRole('link', { name: new RegExp(labels.viewOnGithub) })).toHaveAttribute(
      'href',
      HTML_URL,
    )
  })

  it('GitHub で読むリンクは新しいタブで開く（target=_blank・rel=noopener noreferrer・sr-only 文言つき）', async () => {
    const element = await ReadmeSection({
      readmePromise: Promise.resolve(null),
      htmlUrl: HTML_URL,
      labels,
    })
    render(element)

    const link = screen.getByRole('link', { name: new RegExp(labels.viewOnGithub) })
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
    expect(link).toHaveTextContent(labels.opensInNewTab)
  })

  it('README 内の相対リンクは htmlUrl を基準に絶対 URL へ解決される', async () => {
    const element = await ReadmeSection({
      readmePromise: Promise.resolve('<a href="docs/a.md">doc</a>'),
      htmlUrl: HTML_URL,
      labels,
    })
    render(element)

    const docLink = screen.getByRole('link', { name: 'doc' })
    expect(docLink.getAttribute('href')).toBe(
      'https://github.com/facebook/react/blob/HEAD/docs/a.md',
    )
  })
})
