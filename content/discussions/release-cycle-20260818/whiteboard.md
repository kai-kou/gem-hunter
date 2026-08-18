<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: リリースサイクル: dev ブランチ = プレビュー環境 / main = 本番環境 という環境・ブランチ分離を採用すべきか

- 議題ID: `release-cycle-20260818`
- 論点: ユーザーの相談（原文）: 『最低限の要件の中にプロダクションを意識するという事項があったかと思いますが、それを踏まえて、リリースサイクルとして dev リポジトリはプレビュー環境へのデプロイ、main は本番環境へのデプロイと環境を分けるべきか悩んでいます』。

現状（確定済み）: (1) minimum-requirements.md §4 が『プロダクション運用を想定した実装とする』と定める（非機能要件の前置き。ブランチ戦略やデプロイ環境の分離は明示していない）。 (2) D-16 でデプロイ先はプレビュー・本番とも Cloudflare Workers に確定。 (3) cloudflare-infrastructure.md §6.1 で 3 環境（local / preview / production）を既に定義済み。preview は『同一 Worker の version + preview alias（pr-<N>）』で、Wrangler Environments（[env.*]）は Worker 数上限と棚卸しコストを理由に不採用。 (4) §8.3 で CI は deploy-preview.yml（trigger: pull_request）と deploy-production.yml（trigger: push to main）の 2 本。 (5) CLAUDE.md のブランチ運用は main 保護 + 作業ブランチ（feat/ fix/ docs/ claude/）→ PR → セルフレビュー → 自動マージ（squash）。dev ブランチは存在しない。 (6) SD-1 により全スプリントの PR に開けるプレビュー URL が要る。 (7) D-3 によりプロジェクトの主目的はポートフォリオ（与件充足 + 設計判断の説明可能性）で、M-4 が『第三者へ公開するか否か』の判断ゲート。現時点で公開判断は未通過。 (8) MVP のドメインは *.workers.dev。独自ドメインは M-4 で判断。 (9) OAuth は preview では無効化する方針（§6.2）。 (10) INF-2（定常コストをゼロに）・INF-4（人手の定常運用ゼロ）・INF-20（デプロイのトリガーは git push / マージのみ）。 (11) 開発は Claude の自律ルーティン（sprint-cycle-router）が 1 時間ごとに自走し、PR は自動マージされる。人間のレビュー待ちは発生しない設計。

争点は少なくとも次の 5 つ:
A) 常設の dev ブランチ（= 常設プレビュー環境）を追加すべきか。現行の『PR ごとの preview alias + main マージで本番』で『プロダクションを意識する』要件は満たせているか、それとも不足があるか。
B) 与件『プロダクション運用を想定した実装とする』は何を要求しているか。ブランチ戦略・環境分離まで含む解釈は妥当か、それとも実装品質（エラー処理・秘匿情報・型・テスト・CI）を指すのか。過剰解釈による YAGNI 違反のリスク。
C) Cloudflare Workers 上で dev 常設環境を作る場合の実装コストと制約（別 Worker（[env.*]）を作るのか、versions + 固定 preview alias（例 dev）にするのか。Worker 数上限・シークレット分離・OAuth コールバック URL・独自ドメイン・Free 枠への影響・wrangler.jsonc の複雑化）。
D) 単一開発者 + AI 自律ルーティンという運用実態でのプロセス負荷（dev→main の 2 段マージが自動マージフロー・CP-6・SD-1・sprint-cycle-router とどう衝突するか。リリース遅延・コンフリクト・cherry-pick・ホットフィックス経路。trunk-based development との比較）。
E) 採用するとしたら『今』か『M-4 公開判断の後』か。段階導入の設計（今は何もせず、公開時に何を足せば dev/main 分離相当の安全性が得られるか。gradual deployment / wrangler versions / rollback で代替できないか）。
- 参加者: `release_eng`, `cf_platform`, `autonomy_ops`, `req_trace`, `docs_trace`
- 投稿数: 0
- 更新: 2026-08-18T14:50:40+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

_（まだ投稿がありません）_
