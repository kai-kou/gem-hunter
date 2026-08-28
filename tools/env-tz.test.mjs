import { describe, expect, it } from 'vitest'

// 🔴 #175 Layer1 指摘: vitest.config.mts の TIMEZONE_LOCKED_ENV（test.env.TZ）が実際に
// プロセスへ反映されていることを固定する。設定のマージ順序が将来のアップグレードで崩れても、
// このテストが赤くならない限り「本番だけ 9 時間ずれる」退行の再発防止が効いていない状態を検知できない。
describe('テスト実行環境の TZ 固定（vitest.config.mts）', () => {
  it('プロセス TZ が UTC に固定されている', () => {
    expect(process.env.TZ).toBe('UTC')
  })
})
