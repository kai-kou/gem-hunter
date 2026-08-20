import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { SeenDigestProvider } from './seen-digest-provider'
import { FirstVisitNote } from './first-visit-note'

const STORAGE_KEY = 'gem-hunter:seen-digest'

beforeEach(() => {
  window.localStorage.clear()
})

afterEach(() => {
  window.localStorage.clear()
})

describe('FirstVisitNote', () => {
  it('localStorage が空（初回訪問）のとき role="status" で注記を表示する', async () => {
    render(
      <SeenDigestProvider currentPackageNames={['chalk']} date="20260820">
        <FirstVisitNote label="初回として全件を表示しています" />
      </SeenDigestProvider>,
    )

    expect(await screen.findByRole('status')).toHaveTextContent('初回として全件を表示しています')
  })

  it('前回訪問の記録がある（再訪）ときは注記を表示しない', async () => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ date: '20260819', packageNames: ['chalk'] }),
    )

    render(
      <SeenDigestProvider currentPackageNames={['chalk']} date="20260820">
        <FirstVisitNote label="初回として全件を表示しています" />
      </SeenDigestProvider>,
    )

    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('Provider の外（pending 相当）では何も描画しない', () => {
    render(<FirstVisitNote label="初回として全件を表示しています" />)
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})
