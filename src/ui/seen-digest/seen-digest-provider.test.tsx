import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { SeenDigestProvider, useSeenDigest } from './seen-digest-provider'

const STORAGE_KEY = 'gem-hunter:seen-digest'

function Probe() {
  const state = useSeenDigest()
  if (state.status === 'pending') {
    return <span data-testid="probe">pending</span>
  }
  return (
    <span data-testid="probe">
      ready:{state.isFirstVisit ? 'first' : 'revisit'}:{Array.from(state.newNames).join(',')}
    </span>
  )
}

beforeEach(() => {
  window.localStorage.clear()
})

afterEach(() => {
  window.localStorage.clear()
})

describe('SeenDigestProvider', () => {
  it('localStorage が空のとき isFirstVisit: true になる（effect 後）', async () => {
    render(
      <SeenDigestProvider currentPackageNames={['chalk', 'debug']} date="20260820">
        <Probe />
      </SeenDigestProvider>,
    )

    expect(await screen.findByText('ready:first:')).toBeInTheDocument()
  })

  it('既存の seen があれば前回に無かった packageName が newNames に反映される（effect 後）', async () => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ date: '20260819', packageNames: ['chalk'] }),
    )

    render(
      <SeenDigestProvider currentPackageNames={['chalk', 'debug']} date="20260820">
        <Probe />
      </SeenDigestProvider>,
    )

    expect(await screen.findByText('ready:revisit:debug')).toBeInTheDocument()
  })

  it('effect 後に今回のダイジェストを localStorage へ書き込む（次回訪問向け）', async () => {
    render(
      <SeenDigestProvider currentPackageNames={['chalk', 'debug']} date="20260820">
        <Probe />
      </SeenDigestProvider>,
    )

    await screen.findByText('ready:first:')

    expect(window.localStorage.getItem(STORAGE_KEY)).toBe(
      JSON.stringify({ date: '20260820', packageNames: ['chalk', 'debug'] }),
    )
  })

  it('Provider の外で useSeenDigest を使うと既定で pending を返す', () => {
    render(<Probe />)
    expect(screen.getByTestId('probe')).toHaveTextContent('pending')
  })
})
