<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: スプリントのプレビュー環境の後始末と、本番デプロイをスプリントレビュー判定に接続する仕組みを設計する（Issue #231）

- 議題ID: `sprint-env-lifecycle-20260820`
- 論点: 飼い主の指示（原文）: 『現時点でスプリントごとの実行環境を用意していますが、古い環境を削除、最新の状態でデプロイされた本番環境のデプロイをする仕組みを構築してください。基本的には以下の流れを考えています / スプリント完了後のスプリントレビューが完了したらスプリントの環境を削除する / スプリントレビューで問題がなければ、本番環境にデプロイして反映させる / 専門チームを組成して対応してください』

【オーケストレーターが実測で確定させた事実（推測ではない）】
1. プレビュー環境は同一 Worker の version + preview alias。PR ごとに `npx wrangler versions upload --preview-alias pr-<N> --tag $SHA` で作る（docs/03_design/infrastructure/cloudflare-infrastructure.md §6.1 / §8.2 / §8.3）。`[env.*]` は使わない（Worker 数を増やさないため）。
2. Cloudflare API `GET /accounts/{account_id}/workers/scripts/gem-hunter/versions` を実際に叩いた結果、version が蓄積しており、各 version の `annotations["workers/alias"]` に `pr-219` `pr-212` 等が入っている（`metadata.has_preview: true`）。後始末の仕組みは現在存在しない。
3. `npx wrangler versions --help` の実出力に delete サブコマンドは無い（view / list / upload / deploy / secret のみ）。wrangler 4.124.0。
4. 公式ドキュメント（developers.cloudflare.com/workers/versions-and-deployments/preview-urls/）の Aliased preview URLs 節に『Aliases may be created during versions upload』『Only the 1000 most recently deployed aliases are retained. When a new alias is created beyond this limit, the least recently deployed alias is deleted』とある。alias 削除コマンドの記述は見つかっていない（REST API 側の削除可否は未確定＝この議論で確定させる対象）。
5. セッションには CLOUDFLARE_API_TOKEN / CLOUDFLARE_ACCOUNT_ID が供給されており `npx wrangler whoami` は成功する（User API Token）。curl での Cloudflare API 直叩きも成功している。
6. 本番デプロイは現在 `.claude/skills/pr-review-watcher/SKILL.md` の **Step 6（マージ直後の公開反映）** に書かれている。『push まで完遂したら続けてセッションが npm run deploy を実行し本番反映まで完遂する』『deploy 前に main HEAD で npm run check を再実行』『deploy 後は本番 URL の疎通確認』。**Step 7（スプリントレビュー + レトロスペクティブ）はその後** に実行される。つまり現状は『レビュー判定の前にデプロイ済み』。
7. Step 7 はスプリントレビュー判定を Issue コメントに `**結果**: accepted | accepted_with_conditions | rejected` の書式で投稿し、`retrospective` スキルを起動し、対象 Issue をクローズする（rejected / accepted_with_conditions で持ち越しがあるときは open のまま）。発火条件は『マージした PR 本文に Sprint Goal: 行がある』。
8. GitHub Actions は制限中で使えない（D-23）。deploy-preview.yml / deploy-production.yml は撤去済み。CI もデプロイもセッションが直接実行する。`.claude/settings.json` の permissions.allow に wrangler の deploy 系が登録済み（飼い主の明示指示 2026-08-19）。
9. ADR 0004（docs/adr/0004-release-cycle-trunk-based.md・承認済み）は『trunk-based を維持。作業ブランチ → PR（プレビュー）→ main（本番）の 1 ホップ。常設 dev 環境を持たない』と決めており、受け入れた代償として『main 上の合成状態が本番で初めて動く』を挙げ、緩和策を『main マージ後のテストゲート』（Issue #39）としている。preview alias を使った固定 dev 環境案は『シークレットが Worker 1 本の版チェーン全体で線形継承されるため dev 専用シークレットを分離できない』として却下されている。
10. 既存の関連 Issue: #187『プレビュー version に secret が渡っておらず、認証とレート制限がプレビューで動作しない』が open。

【この議論で決めること（争点）】
A. プレビュー環境（version / preview alias）の後始末として **技術的に実行可能な手段は何か**。wrangler CLI・Cloudflare REST API・代替（無害化・alias 命名の変更・放置して LRU に任せる）を、公式ドキュメントと実 API の応答という一次情報で切り分ける。『できるはず』で書かない。
B. 本番デプロイの発火点を、現在の Step 6（マージ直後）から Step 7（スプリントレビューが accepted）へ移すべきか。ADR 0004 の trunk-based（main = 本番）との整合、非スプリント PR（改善 Issue・retro-try・docs）の扱い、レビュー判定までの間 main と本番がずれることのリスクを含めて判断する。
C. 判定が accepted_with_conditions / rejected のとき、本番デプロイと環境削除をそれぞれどうするか（fail-closed の設計）。Step 7 が中断したときに後始末が永久に実施されない経路を塞ぐ方法。
D. 上記を **どこに実装するか**。SSOT を増やさないこと（同じ規則の実体を 2 箇所に書かない）。候補: `.claude/skills/pr-review-watcher/SKILL.md`（Step 6 / Step 7）・`docs/03_design/infrastructure/cloudflare-infrastructure.md` §8・新規 `tools/*.py`（後始末・棚卸し）・`.claude/hooks/`・`sprint-cycle-router` の決定木。実装コストと実効性（本当に守られるか）で評価し、費用対効果が合わないものは『入れない』と明言する。
- 参加者: `cf_platform`, `release_eng`, `harness_ops`, `docs_trace`
- 投稿数: 0
- 更新: 2026-08-20T16:30:15+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

_（まだ投稿がありません）_
