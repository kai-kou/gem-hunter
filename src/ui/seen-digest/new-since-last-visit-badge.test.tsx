import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { SeenDigestProvider } from './seen-digest-provider'
import { NewSinceLastVisitBadge } from './new-since-last-visit-badge'

const STORAGE_KEY = 'gem-hunter:seen-digest'

beforeEach(() => {
  window.localStorage.clear()
})

afterEach(() => {
  window.localStorage.clear()
})

describe('NewSinceLastVisitBadge', () => {
  it('新着 packageName にはバッジを表示する（effect 後）', async () => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ date: '20260819', packageNames: ['chalk'] }),
    )

    render(
      <SeenDigestProvider currentPackageNames={['chalk', 'debug']} date="20260820">
        <NewSinceLastVisitBadge packageName="debug" label="新着" />
      </SeenDigestProvider>,
    )

    expect(await screen.findByText('新着')).toBeInTheDocument()
  })

  it('既知の packageName にはバッジを表示しない', async () => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ date: '20260819', packageNames: ['chalk'] }),
    )

    render(
      <SeenDigestProvider currentPackageNames={['chalk']} date="20260820">
        <NewSinceLastVisitBadge packageName="chalk" label="新着" />
      </SeenDigestProvider>,
    )

    // ready 状態になるまで待ってから不在を確認する（他の packageName で ready 到達を待機）。
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(screen.queryByText('新着')).not.toBeInTheDocument()
  })

  it('初回訪問（isFirstVisit）では個別バッジを表示しない', async () => {
    render(
      <SeenDigestProvider currentPackageNames={['chalk']} date="20260820">
        <NewSinceLastVisitBadge packageName="chalk" label="新着" />
      </SeenDigestProvider>,
    )

    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(screen.queryByText('新着')).not.toBeInTheDocument()
  })

  it('Provider の外（pending 相当）では何も描画しない', () => {
    render(<NewSinceLastVisitBadge packageName="chalk" label="新着" />)
    expect(screen.queryByText('新着')).not.toBeInTheDocument()
  })
})
