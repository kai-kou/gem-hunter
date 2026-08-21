import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { LocaleSwitchAnnouncer } from './locale-switch-announcer'

describe('LocaleSwitchAnnouncer', () => {
  it('初回描画では何もアナウンスしない（ページを開いた瞬間に読み上げない）', () => {
    const { container } = render(
      <LocaleSwitchAnnouncer currentLocale="ja" announcedLabel="言語を日本語に切り替えました" />,
    )

    const live = container.querySelector('[role="status"]')
    expect(live).not.toBeNull()
    expect(live).toHaveTextContent('')
  })

  it('currentLocale が変わったら role="status" の内容を announcedLabel に更新する', () => {
    const { container, rerender } = render(
      <LocaleSwitchAnnouncer currentLocale="ja" announcedLabel="言語を日本語に切り替えました" />,
    )

    rerender(<LocaleSwitchAnnouncer currentLocale="en" announcedLabel="Switched to English." />)

    const live = container.querySelector('[role="status"]')
    expect(live).toHaveTextContent('Switched to English.')
  })

  it('currentLocale が変わらない再描画では内容を更新しない', () => {
    const { container, rerender } = render(
      <LocaleSwitchAnnouncer currentLocale="ja" announcedLabel="言語を日本語に切り替えました" />,
    )

    rerender(<LocaleSwitchAnnouncer currentLocale="ja" announcedLabel="言語を日本語に切り替えました" />)

    const live = container.querySelector('[role="status"]')
    expect(live).toHaveTextContent('')
  })

  it('sr-only かつ aria-live="polite" である', () => {
    const { container } = render(
      <LocaleSwitchAnnouncer currentLocale="ja" announcedLabel="言語を日本語に切り替えました" />,
    )

    const live = container.querySelector('[role="status"]')
    expect(live).toHaveAttribute('aria-live', 'polite')
    expect(live).toHaveClass('sr-only')
  })
})
