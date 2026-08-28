import '@testing-library/jest-dom/vitest'
import { describe, expect, it } from 'vitest'

// 🔴 #175 Layer1 指摘: vitest.config.mts の app project の TZ 固定（test.env.TZ）が
// 実際にプロセスへ反映されていることを固定する。tools/env-tz.test.mjs と対（tools project 用）。
describe('テスト実行環境の TZ 固定（vitest.config.mts・app project）', () => {
  it('プロセス TZ が UTC に固定されている', () => {
    expect(process.env.TZ).toBe('UTC')
  })
})
