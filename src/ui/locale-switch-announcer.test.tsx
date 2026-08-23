import { render } from '@testing-library/react'
import { StrictMode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { LocaleSwitchAnnouncer as LocaleSwitchAnnouncerType } from './locale-switch-announcer'

// `hasMountedInThisDocument` はモジュールスコープで保持される（フルドキュメントロードに
// 紐づく実装のため・#347 追加タスク）。1 テストファイル内では import キャッシュが共有され
// テスト間で値が持ち越されてしまうので、各テストの前に `vi.resetModules()` して
// モジュールを新規評価し直し、動的 import で「フルロード直後」の状態から始める。
describe('LocaleSwitchAnnouncer', () => {
  let LocaleSwitchAnnouncer: typeof LocaleSwitchAnnouncerType

  beforeEach(async () => {
    vi.resetModules()
    ;({ LocaleSwitchAnnouncer } = await import('./locale-switch-announcer'))
  })

  it('初回描画では何もアナウンスしない（ページを開いた瞬間に読み上げない）', () => {
    const { container } = render(
      <LocaleSwitchAnnouncer currentLocale="ja" announcedLabel="言語を日本語に切り替えました" />,
    )

    const live = container.querySelector('[role="status"]')
    expect(live).not.toBeNull()
    expect(live).toBeEmptyDOMElement()
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

    rerender(
      <LocaleSwitchAnnouncer currentLocale="ja" announcedLabel="言語を日本語に切り替えました" />,
    )

    const live = container.querySelector('[role="status"]')
    expect(live).toBeEmptyDOMElement()
  })

  it('sr-only かつ aria-live="polite" である', () => {
    const { container } = render(
      <LocaleSwitchAnnouncer currentLocale="ja" announcedLabel="言語を日本語に切り替えました" />,
    )

    const live = container.querySelector('[role="status"]')
    expect(live).toHaveAttribute('aria-live', 'polite')
    expect(live).toHaveClass('sr-only')
  })

  it('同一ドキュメント内で remount されても（[locale] セグメント遷移相当）2 回目のマウント直後にアナウンスする', () => {
    // 1 回目のマウント（フルロード相当）→ unmount（ソフトナビゲーションによる remount を模擬）。
    const first = render(
      <LocaleSwitchAnnouncer currentLocale="ja" announcedLabel="言語を日本語に切り替えました" />,
    )
    first.unmount()

    // 2 回目のマウント（[locale] セグメント遷移で SiteHeader 配下が remount された想定）。
    // useRef 版ではここでも「初回」と誤判定されアナウンスが握り潰される（#347 で実測確認済みの
    // バグ）。モジュールスコープ版では hasMountedInThisDocument が生きているため、
    // この 2 回目のマウント自体が「切替の結果」としてアナウンスされる。
    const second = render(
      <LocaleSwitchAnnouncer currentLocale="en" announcedLabel="Switched to English." />,
    )

    const live = second.container.querySelector('[role="status"]')
    expect(live).toHaveTextContent('Switched to English.')
  })

  it('同一ロケールのまま unmount → 再 mount してもアナウンスしない（一覧→詳細等のロケールを跨がない遷移での誤発火防止）', () => {
    // 一覧ページ → 詳細ページのような、ロケールを跨がない通常のクライアント遷移で
    // <LocaleSwitchAnnouncer> 自体が remount されるケースを再現する。
    const first = render(
      <LocaleSwitchAnnouncer currentLocale="ja" announcedLabel="言語を日本語に切り替えました" />,
    )
    first.unmount()

    // 2 回目のマウントだが currentLocale は "ja" のまま変わっていない。
    const second = render(
      <LocaleSwitchAnnouncer currentLocale="ja" announcedLabel="言語を日本語に切り替えました" />,
    )

    const live = second.container.querySelector('[role="status"]')
    expect(live).toBeEmptyDOMElement()
  })

  it('StrictMode 下での初回 render（useEffect が2回走る）でもアナウンスしない', () => {
    const { container } = render(
      <StrictMode>
        <LocaleSwitchAnnouncer currentLocale="ja" announcedLabel="言語を日本語に切り替えました" />
      </StrictMode>,
    )

    const live = container.querySelector('[role="status"]')
    expect(live).toBeEmptyDOMElement()
  })
})
