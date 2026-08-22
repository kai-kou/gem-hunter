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
   * トップページの日次ダイジェスト用に切り出した Gem 候補プールと、その出典メタデータを返す。
   *
   * 🔴 **「候補プール全体」ではない**。`SP-17`（`D-36` / `D-37`）以降、母集団は 12 レジストリの
   * 数万リポジトリ規模になり、ここが返すのはそこから **Gem Index 上位 N 件（既定 300）を
   * 切り出したスライス**（バンドル取り込みのサイズを保つため・`ADR 0014` §2.6）。
   * 配信用の全量は `public/data/gem-index/` のレジストリ別シャードが持つ（`D-38`）。
   * したがって **このポートの戻り値にキーワード照合をかけて「該当なし」と判定してはならない**
   * （全量を見ていないため）。検索語との突き合わせはシャード側の経路で行う。
   *
   * 候補が 0 件でも例外にせず空配列を返す（配信は止めず鮮度のみ劣化させる・`D-28` SPOF 方針）。
   */
  listCandidates(): Promise<{ candidates: readonly Gem[]; meta: DigestMeta }>
}
