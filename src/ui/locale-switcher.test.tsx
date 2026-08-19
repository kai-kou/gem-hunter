import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { locale } from '../domain/model/locale'
import { LocaleSwitcher } from './locale-switcher'

const labels = {
  navLabel: '言語切替',
  localeNames: { ja: '日本語', en: 'English' },
}

describe('LocaleSwitcher', () => {
  it('ja / en の 2 リンクを描画する', () => {
    render(
      <LocaleSwitcher currentLocale={locale('ja')} currentPath="/ja" labels={labels} />,
    )

    expect(screen.getByRole('navigation', { name: '言語切替' })).toBeVisible()
    expect(screen.getByRole('link', { name: '日本語' })).toHaveAttribute('href', '/ja')
    expect(screen.getByRole('link', { name: 'English' })).toHaveAttribute('href', '/en')
  })

  it('現在のロケールのリンクに aria-current="true" を付ける', () => {
    render(
      <LocaleSwitcher currentLocale={locale('ja')} currentPath="/ja" labels={labels} />,
    )

    expect(screen.getByRole('link', { name: '日本語' })).toHaveAttribute('aria-current', 'true')
    expect(screen.getByRole('link', { name: 'English' })).not.toHaveAttribute('aria-current')
  })

  it('現在のパス（検索条件付き・詳細ページ等）を保ったまま切り替え先 URL を組み立てる（SP-7 の検索条件保持方針を踏襲）', () => {
    render(
      <LocaleSwitcher
        currentLocale={locale('ja')}
        currentPath="/ja/repos/octostub/octo-widgets?from=list"
        labels={labels}
      />,
    )

    expect(screen.getByRole('link', { name: 'English' })).toHaveAttribute(
      'href',
      '/en/repos/octostub/octo-widgets?from=list',
    )
  })

  it('英語 UI でも表示名は言語の自称（endonym）のまま変わらない（言語切替の一般的な UX 慣行）', () => {
    render(
      <LocaleSwitcher
        currentLocale={locale('en')}
        currentPath="/en"
        labels={{ navLabel: 'Language', localeNames: { ja: '日本語', en: 'English' } }}
      />,
    )

    expect(screen.getByRole('link', { name: '日本語' })).toBeVisible()
    expect(screen.getByRole('link', { name: 'English' })).toHaveAttribute('aria-current', 'true')
  })
})
