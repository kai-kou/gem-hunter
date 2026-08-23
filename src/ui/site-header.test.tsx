import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { locale } from '../domain/model/locale'
import { SiteHeader } from './site-header'

const localeSwitcherLabels = {
  navLabel: '言語切替',
  localeNames: { ja: '日本語', en: 'English' },
  switchedAnnouncement: '言語を日本語に切り替えました',
}

const authLabels = { login: 'ログイン', logout: 'ログアウト' }

describe('SiteHeader', () => {
  it('header 要素の中に h1 > リンク（ロゴ画像 + タイトル）を描画する', () => {
    render(
      <SiteHeader
        locale={locale('ja')}
        currentPath="/ja"
        title="gem-hunter"
        localeSwitcherLabels={localeSwitcherLabels}
        isLoggedIn={false}
        showAuthLink={false}
        skipLinkLabel="本文へスキップ"
      />,
    )

    const header = screen.getByRole('banner')
    const heading = screen.getByRole('heading', { level: 1 })
    expect(header).toContainElement(heading)

    const link = screen.getByRole('link', { name: 'gem-hunter' })
    expect(link).toHaveAttribute('href', '/ja')

    const img = link.querySelector('img')
    expect(img).not.toBeNull()
    expect(img).toHaveAttribute('alt', '')
  })

  it('言語切替（nav）を header 内に描画する', () => {
    render(
      <SiteHeader
        locale={locale('ja')}
        currentPath="/ja"
        title="gem-hunter"
        localeSwitcherLabels={localeSwitcherLabels}
        isLoggedIn={false}
        showAuthLink={false}
        skipLinkLabel="本文へスキップ"
      />,
    )

    const header = screen.getByRole('banner')
    const nav = screen.getByRole('navigation', { name: '言語切替' })
    expect(header).toContainElement(nav)
  })

  it('showAuthLink=true かつ authLabels 指定時はログイン導線を描画する', () => {
    render(
      <SiteHeader
        locale={locale('ja')}
        currentPath="/ja"
        title="gem-hunter"
        localeSwitcherLabels={localeSwitcherLabels}
        isLoggedIn={false}
        showAuthLink={true}
        authLabels={authLabels}
        skipLinkLabel="本文へスキップ"
      />,
    )

    expect(screen.getByRole('link', { name: 'ログイン' })).toHaveAttribute(
      'href',
      '/api/auth/login',
    )
  })

  it('showAuthLink=false のときログイン導線を描画しない', () => {
    render(
      <SiteHeader
        locale={locale('ja')}
        currentPath="/ja"
        title="gem-hunter"
        localeSwitcherLabels={localeSwitcherLabels}
        isLoggedIn={false}
        showAuthLink={false}
        skipLinkLabel="本文へスキップ"
      />,
    )

    expect(screen.queryByRole('link', { name: 'ログイン' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'ログアウト' })).not.toBeInTheDocument()
  })

  it('isLoggedIn=true のときログアウト導線を描画する', () => {
    render(
      <SiteHeader
        locale={locale('ja')}
        currentPath="/ja"
        title="gem-hunter"
        localeSwitcherLabels={localeSwitcherLabels}
        isLoggedIn={true}
        showAuthLink={true}
        authLabels={authLabels}
        skipLinkLabel="本文へスキップ"
      />,
    )

    expect(screen.getByRole('button', { name: 'ログアウト' })).toBeInTheDocument()
  })

  it('header の直前にスキップリンクを描画し、#main-content を指す（Issue #354）', () => {
    render(
      <SiteHeader
        locale={locale('ja')}
        currentPath="/ja"
        title="gem-hunter"
        localeSwitcherLabels={localeSwitcherLabels}
        isLoggedIn={false}
        showAuthLink={false}
        skipLinkLabel="本文へスキップ"
      />,
    )

    const skipLink = screen.getByRole('link', { name: '本文へスキップ' })
    expect(skipLink).toHaveAttribute('href', '#main-content')
    expect(skipLink).toHaveClass('sr-only')

    const header = screen.getByRole('banner')
    expect(skipLink.compareDocumentPosition(header) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })
})
