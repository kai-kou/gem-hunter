import type { Gem, DigestMeta } from '../model/gem'

/**
 * ダイジェスト候補プールの取得口（`SP-14` / `ADR 0014` §2.2）。
 *
 * バッチ（Cloudflare 外の cron・`D-28`）が生成した静的 JSON を丸ごと読むだけの読み取り専用
 * ポート。Worker はこのポート経由で候補を受け取り、並べ替え（日付シードの決定論的選定）は
 * usecase 側（`get-daily-digest.ts`）で行う。実装は `src/infrastructure/` 側に置き、
 * composition root で束ねる。面積はこれ以上広げない（`listCandidates()` 1 本・YAGNI）。
 */
export interface GemDigestPort {
  /**
   * npm エコシステムの Gem 候補プール全体と、その出典メタデータを返す。
   * 候補が 0 件でも例外にせず空配列を返す（配信は止めず鮮度のみ劣化させる・`D-28` SPOF 方針）。
   */
  listCandidates(): Promise<{ candidates: readonly Gem[]; meta: DigestMeta }>
}
