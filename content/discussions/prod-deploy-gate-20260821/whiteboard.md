<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: 本番デプロイが本番へ届かない問題（Issue #288 完了条件 4）を、L-130 の是正・D-31 の再評価・D-26 ゲートの維持方式まで含めて決着させる

- 議題ID: `prod-deploy-gate-20260821`
- 論点: 飼い主の指示（原文）: 『添付画像はルーティン実行の結果です。この問題について解決済みだったか、まだIssueのままか、事実確認して教えてください』→（事実確認の報告後）『本セッションで専門チームを組成して適切に対応してください。ユーザー作業があれば、詳細に案内してください』

【オーケストレーターが実測で確定させた事実（推測ではない・すべて本セッションでツール出力を確認済み）】

1. Issue #288 は open（status:in-progress へ本セッションが変更）。完了条件 4 項目のうち 1〜3 は達成済み（L-130 記録 / §8.2.2・§8.2.3 追記 / tools/check_prod_drift.py）、**4「起点となった 64d2aa3 が本番へ反映されている」だけが未達**。

2. `npm run deploy` の実体（package.json）: `opennextjs-cloudflare build && SHA=$(git rev-parse --short=12 HEAD) && test -n "$SHA" && wrangler deploy --tag "$SHA"`。

3. 🔴 **auto mode classifier のブロックは決定論的ではない**。実測の内訳:
   - **ブロック 5 回**: 2026-08-20 07:45 JST 無人ルーティン 3 回（複合 background / 単独 background / 単独 foreground）、2026-08-21 09:17 JST 頃 有人 1 回、2026-08-21 11:40 JST 無人 1 回（#307 マージ後）。いずれも `Permission for this action was denied by the Claude Code auto mode classifier. Reason: Blocked by classifier.`
   - **成功 2 回**: 2026-08-21 10:32 JST 無人ルーティンセッションで `npm run deploy` 成功（Version ID `df728490-1f28-4911-a329-d08d2517bc7c` / tag `200743832fe6` = commit 2007438・Issue #263 のコメントに実行記録あり・本番疎通 200・`check_prod_drift.py` が `drifted:false confidence:exact`）。さらに本番の現在の最終デプロイは tag `d9ab80106e59`（= commit d9ab801 / 2026-08-21 10:45 JST・本セッションで `check_prod_drift.py` の出力から確認）であり、**2 回目のデプロイも成功している**。
   - 初回試行のエラー文言は `Stage 2 classifier error - blocking based on stage 1 assessment` で、**transient と明示されていた**。
   → つまり `docs/rules/lessons/cloud-environment.md` の `L-130`「無人・有人を問わず 4 回すべて再現」「クラウドセッションは wrangler deploy に到達できない」という断定は **実態と食い違っている**（Issue #300 が起票済み・本セッションで status:in-progress へ）。

4. 本セッション時点の乖離（`python3 tools/check_prod_drift.py` の実出力）:
```
乖離あり（exact）: 本番の最終デプロイの SHA タグが main HEAD と一致しません（exact）
  main HEAD: e4b07581bc3b53a17209eda18851055ba60e4277（2026-08-21T11:36:56+09:00）
  本番デプロイ: version=48f19b10-b713-41f4-81af-2894af4b0ce3（2026-08-21T01:45:56.020418Z） tag=d9ab80106e59
```
未反映の差分は PR #307 のみで、`.claude/hooks/` `tools/` `docs/rules/` だけを変更しており **アプリのランタイムコードを 1 行も含まない**（利用者影響なし）。

5. `D-31`（2026-08-21 飼い主決定・PR #291 マージ済み）: 本番デプロイの発火点を **Workers Builds**（Cloudflare native の Git 連携）へ移す。`D-16`（Workers Builds は採用しない）の該当部分を上書きする決定。

6. 🔴 `D-31` はまだ実行できない。Issue #290（`[user-work]` Workers Builds の接続手順）は **status:waiting-claude のまま**で、飼い主にはまだ依頼していない。理由は P-1 が未決だから:
   - **P-1**: `D-26`（`tools/check_deploy_gate.py`）は「スプリント PR は Sprint Review 判定が accepted になるまでデプロイしない・rejected の間はデプロイしない・判定コメントが無い場合も塞ぐ・exit 2（判定不能）でもデプロイしない fail-closed」と定めている。Workers Builds は **push をトリガー**にするため、このゲートが呼ばれず判定を飛ばして本番へ出る。現行フローの Sprint Review は **マージ後**（`pr-review-watcher` Step 7）に実施される。
   - 候補案 (a): Deploy command をゲート込みにする（`check_deploy_gate.py` を実行し can_deploy=false ならデプロイせず正常終了する npm script を Deploy command に指定）。**ビルド環境に Python と GitHub API アクセス（トークンをビルド変数へ）が必要で未検証**。
   - 候補案 (b): Sprint Review 判定が出るまで main にマージしない（判定をマージ前へ動かす）。`pr-review-watcher` Step 7 の運用組み替えが要る。
   - **P-2**: シークレット引き継ぎの確認（`wrangler versions secret put` で入れた値が Workers Builds の `wrangler deploy` で解決されるか）。🔴 `RATE_LIMIT_SALT` が未解決だとレート制限がフェイルオープンし、**エラーにならないので気づけない**。

7. `check_deploy_gate.py` の仕様（実ファイルを読んで確認）: open かつ `status:in-progress` の Issue を GitHub API で列挙 → タイトルに `SP-\d+` を含むか本文コメントに `## 🏃 Session Sprint Planning` があるものをスプリント対象と判定 → `## 🔍 Sprint Review 判定` の `**結果**:` 行の最新値で判定。exit 0=可 / 1=待機 / 2=判定不能（fail-closed）。API チャネルは gh → urllib + GH_TOKEN/GITHUB_TOKEN のフォールバック。

8. GitHub Actions はプラットフォーム側の制限で使えない（`D-23`）。CI という機構が存在せず、品質担保は `bash tools/run_checks.sh` をセッションが実行することで代替している。

9. `docs/03_design/infrastructure/cloudflare-infrastructure.md` §8.2.2 / §8.2.3 に、L-130 と同じ「クラウドセッションは wrangler deploy に到達できない」という断定と、Workers Builds 移行手順（設定値の表・検証 3 点・停止 runbook）が既に書かれている。§8.2.3 の設定値表は Deploy command = `npm run deploy` としているが、これは P-1 の (a) を採るなら書き換えが要る。

【この議論で決めること（争点）】

A. 🔴 **`L-130` を実態に合う記述へどう直すか**（Issue #300）。ブロック 5 回・成功 2 回の分かれ目は何か。auto mode classifier の公式ドキュメント（WebFetch で code.claude.com/docs を直接読む）に照らして、**分類器がステートレスな LLM 判定で非決定的なのか / セッション属性（有人・無人、permission mode、モデル）で決まるのか / 時期による分類器側の変更なのか** を、確認できた事実と確認できなかったことを分けて書く。「必ずブロックされる」という断定を消したうえで、**セッションが取るべき行動指針**（ブロックされたら何回まで再試行してよいか / 迂回は依然禁止か）まで落とす。

B. 🔴 **`D-31`（Workers Builds への移行）を維持するか、見直すか**。「成功例が出た＝移行不要」ではないか、という反論に正面から答える。判断材料: 非決定的なブロックに依存した運用の信頼性、無人ルーティンが止まる頻度、移行コスト（飼い主のダッシュボード操作 1 回 + P-1/P-2 の実装）、移行で失うもの（`D-26` ゲート・プレビュー運用との二重化）。**維持するなら「なぜ成功例があっても移行するのか」を 1 段落で言えること**、見直すなら代替の到達手段を具体的に示すこと。

C. 🔴 **P-1 の結論を出す**（(a) / (b) / 議論で出た第 3 案）。(a) を採るなら Workers Builds のビルド環境で `check_deploy_gate.py` が動くのかを **公式ドキュメントの一次情報で確定**させる（ビルドイメージに Python はあるか / `git` は使えるか / `WORKERS_CI_COMMIT_SHA` 等の既定環境変数 / ビルド変数とシークレットの扱い / Node バージョン指定）。GitHub トークンをビルド変数に置くことのセキュリティ評価も含める。動かないなら (b) か第 3 案へ倒し、**運用の組み替え内容を具体的に書く**。

D. 🔴 **本セッションで完遂すべき作業範囲と、飼い主に依頼する作業の確定**。(1) 現在の乖離（main e4b0758 が未反映）を本セッションでどう扱うか — `npm run deploy` を再試行してよいか、その根拠は何か（争点 A の結論に従う）。(2) このセッションでコードとして実装すべきもの（npm script・ドキュメント修正・L-130 書き換え）は何か。(3) Issue #290 を `status:waiting-user` にして飼い主へ出せる状態にできるか、まだ出せないなら何が残るか。**飼い主に渡す手順は「ダッシュボードのどの画面で何を押し、何を入力するか」まで具体化されていること**（画面遷移・入力値・確認方法・失敗時に何を Claude へ伝えればよいか）。
- 参加者: `classifier_facts`, `cf_builds`, `release_ops`, `docs_trace`
- 投稿数: 0
- 更新: 2026-08-21T12:49:08+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

_（まだ投稿がありません）_
