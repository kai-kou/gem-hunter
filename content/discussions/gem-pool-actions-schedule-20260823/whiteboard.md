<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: Gem 候補プール再生成を GitHub Actions で定期実行する設計（Issue #458）

- 議題ID: `gem-pool-actions-schedule-20260823`
- 論点: 飼い主の指示（原文）: 『リポジトリをパブリック化したことで、GitHub Actionsの利用制限が解除されました。本セッションでIssue作成して定期的に実行されるように専門チームを組成して対応してください』

【オーケストレーターが本セッションで実測・確認した事実（推測ではない）】

1. Issue #458 を起票済み（type:improvement / status:in-progress / sp:5）。

2. バッチの実体は `node tools/generate_gem_digest.mjs`（Node 22+ / ESM）。CLI 冒頭の docstring に処理段が書かれている: 収集 collectAll（12 レジストリ × 被依存数降順 15,000 件）→ 整形 projectPackage → 順位 buildPool（汚染フィルタ + repo 単位 dedupe + レジストリ別再ランク）→ 出力 output.*。既定実行で **約 10 分・180 リクエスト**。オプション: `--dry-run` / `--registries` / `--quota` / `--allow-partial-write`。⚠️ 部分実行 + `--allow-partial-write` は **孤児シャードを削除する**。

3. 🔴 同 CLI の冒頭に『⚠️ CI での自動実行はしない（更新は `D-28` どおり Cloudflare の外で回して git commit → デプロイ）』と明記されている。これは Actions が使えなかった時期の制約に由来する記述であり、本 Issue で実態に合わせて直す対象。

4. 生成物は `public/data/gem-index/*.json`（12 シャード）+ `public/data/gem-index/index.json` + `public/data/daily-digest.json`。**合計 3.6MB**。git 追跡済み（`.gitignore` されていない）。過去にこのディレクトリを変更したコミットは 2 つだけ（6488e01 / 74ea0b4）。現行 `index.json` の `generatedAt` は **2026-08-22 15:04 JST**、`totalCount` 62,483。

5. 反映経路の制約: 🔴 `main` への直接 push は本プロジェクトの既約境界外 **A-1**（`docs/rules/user-confirmation-minimization.md` §1）。PR 経由・自動マージのみ。

6. 本番デプロイは **Workers Builds**（Cloudflare native の Git 連携・`D-31` / `D-32`）が main への push をトリガーに動き、Deploy command が `tools/workers_build_deploy.sh` を呼ぶ。同スクリプトは `tools/check_deploy_gate.py` を実行し、**ゲートが閉じているときは非ゼロで終了する（fail-closed）**。`check_deploy_gate.py --json` の終了コードは 0=デプロイ可 / 1=待機 / 2=判定不能。判定は『open かつ status:in-progress の Issue のうち、タイトルに SP-\d+ を含むか本文コメントに `## 🏃 Session Sprint Planning` があるもの』をスプリント対象とし、`## 🔍 Sprint Review 判定` の `**結果**:` 行の最新値で決まる。

7. `D-28`（`docs/02_requirements/open-questions.md`）: バッチ集計は **Cloudflare の外** で回し、生成した静的 JSON を git commit → デプロイで Static Assets として丸ごと差し替える。SPOF（バッチ停止時に更新が止まる）は無害化 + 検知して自己修復で対処し、**配信自体は止めず鮮度のみ劣化させる**。

8. `docs/rules/pr-review-flow-summary.md` に『🔴 GitHub Actions は制限中で使えない（ジョブが数秒・ログ 0 バイトで失敗）。ワークフロー 2 本は撤去済み』とあり、`docs/rules/harness-escalation.md` / `docs/rules/lessons-management.md` にも Actions を運用に使わない旨の記述がある。`.github/workflows/` は現在 **存在しない**。

9. Gem Index は母集団依存の相対指標であり、再生成のたびに **全銘柄の値が変わりうる**（`src/domain/model/gem-index.ts` の JSDoc が明示）。日次ダイジェストの日替わりは date シードによる選定であって、値の再計算ではない。

【この議論で決めること（争点）】

A. 🔴 **実行間隔（cron 式まで確定させる）**。判断材料: Ecosyste.ms 側のデータ更新頻度と本バッチの負荷（180 リクエスト・10 分）、Gem Index が相対指標であること（頻繁に回すと同じリポジトリのバッジが付いたり消えたりする）、3.6MB の生成物を毎回コミットすることによる git 履歴の増加、Actions の無料枠（パブリックリポジトリでの扱いを一次情報で確認すること）。**『毎日』『毎週』を感覚で選ばず、上記のどれが効いて何時（JST）に回すのかまで書くこと**。schedule cron は UTC で書く点に注意。

B. 🔴 **生成物の反映経路**。`main` 直 push は A-1 で不可。PR を自動作成する場合: どのアクション/コマンドで作るか（サードパーティアクションの是非も含む）、GITHUB_TOKEN の permissions は何が要るか、**workflow が GITHUB_TOKEN で作った PR は他の workflow をトリガーしない** という GitHub の仕様が本プロジェクトに影響するか、自動マージしてよいか（するなら誰が品質を担保するのか / しないなら誰がいつマージするのか・放置される PR が増えないか）。差分が実質ゼロだった回に空 PR を作らない仕組みも決める。

C. 🔴 **マージ後の Workers Builds デプロイゲートとの整合**。データ PR がマージされたとき `check_deploy_gate.py` は何を返すか（そのとき in-progress のスプリント Issue があれば **待機（exit 1）で fail-closed** になり、データだけ main に入ってデプロイされない状態が生まれないか）。生まれるなら許容するのか、対処するのか。**ゲートを迂回する案は採らない**（`workers_build_deploy.sh` 冒頭が禁じている）。

D. 🔴 **失敗時の扱い**（`D-28` の SPOF 方針に沿うこと）。途中でネットワーク失敗したとき部分的な生成物をコミットしてしまわないか（`--allow-partial-write` の孤児シャード削除に注意）、リトライするか、失敗を誰にどう通知するか（Issue 起票 / Slack / Actions の失敗通知のどれか。既存の `tools/slack_notify.py` を使えるか、シークレットが要るなら誰が設定するのか）、**60 日間コミットが無いとスケジュール実行が自動停止する** GitHub の仕様への対処。

E. 🔴 **更新すべき既存記述の洗い出し**（実ファイルを読んで、パスと節・行の粒度で）。最低限: `tools/generate_gem_digest.mjs` 冒頭コメント、`docs/rules/pr-review-flow-summary.md`、`docs/rules/harness-escalation.md`、`docs/rules/lessons-management.md`、`docs/02_requirements/open-questions.md`（`D-23` / `D-28` / `D-31` / `D-32`）、`docs/03_design/infrastructure/cloudflare-infrastructure.md`、`CLAUDE.md`。**Actions が使えるようになったからといって、飼い主が別途決めた『Actions を品質ゲートには使わない』方針まで勝手に覆さないこと**（本 Issue のスコープはバッチの定期実行に限る。方針変更が要ると判断したら follow_up_issues に落とす）。
- 参加者: `actions_facts`, `batch_ops`, `deploy_gate`, `docs_trace`
- 投稿数: 0
- 更新: 2026-08-23T10:04:33+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

_（まだ投稿がありません）_
