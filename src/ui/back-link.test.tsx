import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { locale } from '../domain/model/locale'
import { BackLink } from './back-link'

describe('BackLink', () => {
  it('href 省略時は /{locale} を指す（既存呼び出し元との後方互換・not-found.tsx 等）', () => {
    render(<BackLink locale={locale('ja')} labels={{ backLink: '一覧へ戻る' }} />)

    expect(screen.getByRole('link', { name: '一覧へ戻る' })).toHaveAttribute('href', '/ja')
  })

  it('href を渡すとそちらを優先する（SP-7・検索条件を保持した戻り先）', () => {
    render(
      <BackLink
        locale={locale('ja')}
        labels={{ backLink: '一覧へ戻る' }}
        href="/ja?q=react&sort=stars"
      />,
    )

    expect(screen.getByRole('link', { name: '一覧へ戻る' })).toHaveAttribute(
      'href',
      '/ja?q=react&sort=stars',
    )
  })
})
