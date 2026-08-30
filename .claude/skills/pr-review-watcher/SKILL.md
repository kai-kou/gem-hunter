---
name: pr-review-watcher
description: PR 作成後のレビュー監視・指摘対応・自動マージを自律実行するスキル。「PR を監視して」「レビュー対応して」「PR をマージまで見届けて」「レビュー待ち PR を回収して」と依頼された時、PR 作成フローの直後、またはセッション復帰時に check_pending_pr_reviews.py がレビュー待ち PR を検出した時に必ず使用する。Layer 1 セルフレビュー（自前 code-review スキル。組み込み /code-review を同名 project スキルで置換済み・自律起動可）を必ず実行し、指摘対応 → 自動マージまでを自律実行する。外部 AI レビュアー（Copilot/Gemini）への依頼はしない。CI・人手コメントは subscribe_pr_activity で任意監視する。対応はサイレント（ユーザー報告せず PR スレッド・Issue 記録のみ・L-102）。
effort: medium
---

# PRレビュー監視・自動対応スキル

PR 作成後に **Claude 自身が Layer 1 セルフレビュー（自前 `code-review` スキルを `Skill(code-review)` で
起動）を必ず実行** し、指摘対応 → 自動マージまでをユーザー指示なしで自律実行する。組み込み
`/code-review` は disable-model-invocation で自律起動不可のため、同名 project スキル
`.claude/skills/code-review/` が bundled を置換している（自律起動可・#275 → #280）。
**外部 AI レビュアー（Copilot / Gemini）への
レビュー依頼は行わない**（Copilot 依頼廃止・Gemini は 2026-07-17 廃止済み）。CI 結果・人手コメントは
`subscribe_pr_activity` で任意に監視する。**詳細手順（Step 1-7・GraphQL・トラブルシューティング・
フィードバックループ）は `reference.md`**、フロー全体の正本は **`docs/rules/pr-review-flow.md`**、
レビュアー構成の SSOT は **`docs/rules/ai-reviewer-strategy.md`** を参照。

## 品質チェックの二層構成（必読・`D-42`・Issue #543）

🔴 **CI はある**。`.github/workflows/quality-checks.yml` が `push`（`main`）と `pull_request` を契機に
**自動実行** される（Prettier `format:check` / ESLint / `tsc --noEmit` / Vitest の 4 種のみ・`contents: read` の
読み取り権限だけで、自動マージもデプロイもしない）。**マージ前に check run を確認し、赤いままマージしない**
（確認方法・例外の正本は `docs/rules/pr-review-flow-summary.md`「レビュー監視と自動マージ」）。

⚠️ **CI 緑は層 2 の省略理由にならない**。CI が見るのは `tools/run_checks.sh` に定義された 40 件超
（実測 42 件）のチェックのうち **4 件だけ** で、E2E・Lighthouse・依存規則（`check_architecture_boundaries.py`）・
CJK Markdown・LP 静的検査・各 self-test は **CI に載っていない**。**PR 作成前に `npm run check`
（= `bash tools/run_checks.sh`）を実行し、結果表を PR 本文へ貼る層 2 は引き続き必須**
（手順は同ファイル「PR 作成時の必須事項」項目 0 が正本・`pre-pr-create-check.sh` がブロックで強制する）。

⚠️ **check run が付かない例外**: `gem-pool-refresh.yml` が `secrets.GITHUB_TOKEN` で作る
`automation/gem-pool-refresh` PR には、GitHub 公式仕様（`GITHUB_TOKEN` 由来のイベントは新しい
workflow run を作らない）により check run が生成されない。この PR は **check run 不在をもって赤とみなさない**
（品質は同ワークフロー自身の QA ステップが担保する。必要なら `workflow_dispatch` で明示起動して検証する）。

🔴 **本番デプロイに Actions は使わない**（`D-31` / `D-32` の Workers Builds が正本・不変）。

## トリガー条件

- PR 作成後に AI レビューの到着を待つ時（PR 作成フローの一部として自動開始）
- **セッション復帰時**: `tools/check_pending_pr_reviews.py` がレビュー待ち PR を検出した時

## Layer 2 レビュー自動起動（Issue #97・ネイティブ化 #193）

PR 作成・AI レビュー依頼の直後に `discussion_review_trigger.py`（要否判定器）を呼び出す。
差分 ≥300行 または `type:security`/`type:breaking-change` ラベル付きの PR には
自動的に Layer 2 議論型レビューを追加実行する。

クラウド環境（gh CLI 不可）では `mcp__github__pull_request_read` で取得した値を渡す:

```bash
# クラウド環境: mcp__github__pull_request_read(method="get") の結果を使う
python3 tools/discussion_review_trigger.py \
  --pr {PR番号} \
  --diff-lines {additions + deletions} \
  --labels "{label1},{label2}" \
  --changed-files "{file1.py},{file2.md}"

# ローカル環境（gh CLI 有効時）: PR 番号のみ
python3 tools/discussion_review_trigger.py --pr {PR番号}
```

- Layer 2 不要と判定された場合: `ℹ️ Layer 2 レビュー不要` を出力して skip
- **トリガー該当時**: 実行プラン JSON（id / spec / targets / rounds）が出力される。そのプランに従い
  **`discussion-review` スキル（ネイティブ Agent Teams・既定）** で議論型レビューを実行する
- ネイティブ実行が成立しない場合のみ、プランの `fallback_command`（`--legacy` = 旧 claude -p 経路）へ退避する（理由をログ）
- Layer 2 失敗時: stderr に警告を出力し Layer 0+1 で継続（サイレントフォールバック禁止）
- 詳細: `docs/rules/ai-reviewer-strategy.md` を参照

## 使い方（ユーザー指示不要・自動実行）

PR 作成後、指示を待たずにセルフレビュー → マージまで進める:

```
1. PR 作成（本文に Session-Id: $CLAUDE_CODE_SESSION_ID を必ず記載・#47 所有判定の前提）
2. Layer 1 セルフレビューを必ず実行: 自前 code-review スキルを Skill(code-review) で起動する
   （.claude/skills/code-review/ が組み込みを置換・観点別ファインダー並列 → 敵対的検証 → 報告）
   ❌ Copilot 依頼（request_copilot_review / --add-reviewer @copilot）・Gemini 依頼（/gemini review）はしない
3. 指摘対応（修正コミット or スキップ + 返信 + Resolve）→ `check_pending_pr_reviews.py --verify-layer1 <PR番号>` で Layer 1 投稿済みを機械検証（#462）→ Layer 0+1 通過で自動マージ
4. （任意）subscribe_pr_activity で CI / 人手コメントを監視
5. セッションが切れたら → 次セッションで check_pending_pr_reviews.py --mine が自 PR を識別 → 復帰
```

> **自セッション作成 PR の回収（#47）**: 復帰時はまず `check_pending_pr_reviews.py --mine --actionable-only --json` で
> **自セッションが作成した PR のみ** を最優先で責任継続する（Session-Id トレーラーによる積極的所有判定）。
> 自 PR は時間ベースの `active_session` 除外を受けないため、10 分超アイドル・再起動・圧縮後でも確実に回収できる。
> その後に `--mine` なしの共有スコープで孤児 PR を救済する。詳細は `docs/rules/session-concurrency-rules.md` レイヤー 6。

> 監視中はタスク依存ルールを `docs/rules/` から Read する: `docs/rules/self-review-checklist.md`（セルフレビュー観点）/
> `docs/rules/lessons/pr-review.md`（PR レビュー・マージの過去ミスパターン）。

## 監視方式: subscribe_pr_activity + ハートビート（推奨）

`subscribe_pr_activity` でイベント購読し、同時に `pr_review_heartbeat.sh` をバックグラウンド起動して
`Monitor` でストリームする（クラウドの 10 分タイムアウトを防止）。

```
# ① イベント購読を開始（イベント駆動）
mcp__github__subscribe_pr_activity(owner="kai-kou", repo="gem-hunter", pull_number={pr_number})
# ② ハートビートをバックグラウンド起動（セッション維持・5分間隔）
Bash(run_in_background=true): bash tools/pr_review_heartbeat.sh {pr_number} 30  # → PID を控える
# ③ Monitor でハートビート出力をストリーム（各行が通知としてセッションを維持）
Monitor(pid={HEARTBEAT_PID}, description="PR #{pr_number} ハートビート")
```

- ハートビートは 5 分ごとに `check_pending_pr_reviews.py` で状態確認し stdout 出力（アイドルタイムをリセット）
- `ready_to_merge` 検出で 🚀、マージ済みで ✅ を出力して自動終了、`max_minutes`（既定 30）経過で ⏰ 終了
- `<github-webhook-activity>` タグのレビューイベントとハートビート通知を並行処理する
- sleep ポーリングは禁止（イベント駆動 + 定期出力で両立）

> subscribe が使えない環境のフォールバック: `bash tools/poll_pr_reviews.sh kai-kou/gem-hunter {pr_number} /tmp/pr_review_{pr_number}.json`

## 監視タイムライン（PR 作成時刻基準）

```
0分   : PR 作成 → Layer 1 観点別フレッシュ文脈セルフレビューを必ず実行
        指摘対応（修正コミット or スキップ + 返信 + Resolve）
マージ前        : quality-checks.yml の check run を確認（赤ならマージしない・上記の例外を除く）
Layer 0+1 通過後 : 即自動マージ（外部レビュアー応答待ちなし）
任意   : subscribe_pr_activity で CI / 人手コメントを監視。あれば対応してからマージ
        └─ A-1〜A-6 該当（サーキットブレーカー発動等）時のみユーザー報告
```

## ステップ概要（詳細は reference.md）

| Step | 内容                                                                                                                                                                                                                                                                                                                                                                                                                     |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1    | Layer 1 セルフレビュー実行（自前 `code-review` スキル・`Skill(code-review)`）+ 既存レビュー状態の取得。**指摘は全件 PR の行単位インラインコメントで記録し、指摘ゼロでも `event="COMMENT"` のレビューを 1 件投稿する**（#461・手順は code-review スキル Step 3-A）                                                                                                                                                        |
| 2    | 指摘の分類（修正対象 / スキップ）。CI 失敗・人手コメントの有無を確認                                                                                                                                                                                                                                                                                                                                                     |
| 3    | 指摘への自動対応（修正コミット or スキップ → スレッド返信 → **Resolve 必須**）                                                                                                                                                                                                                                                                                                                                           |
| 4    | Layer 0（機械ゲート）+ Layer 1 通過の確認。**`check_pending_pr_reviews.py --verify-layer1 <PR番号>` で Layer 1 投稿済みかを機械検証**（#462・挙動は reference.md Step 4）。**あわせて `quality-checks.yml` の check run が緑であることを `mcp__github__pull_request_read`（`method="get_check_runs"` / `method="get_status"`）で確認する**（赤ならマージしない。check run が付かない例外は本ファイル冒頭の二層構成の節） |
| 5    | 自動マージ（squash・外部レビュアー応答待ちなし）                                                                                                                                                                                                                                                                                                                                                                         |
| 6    | **公開リポジトリへの反映（`publish-sync`）は常に実行**。**本番デプロイはゲート判定を経由し、一次経路は Workers Builds の再トリガー**（`tools/trigger_workers_build.py`。`npm run deploy` の直叩きはフォールバック）: スプリント PR（`Sprint Goal:` 行あり）はここでデプロイせず Step 7 の判定へ委譲。非スプリント PR は同スクリプトが内部でゲートを確認し、開いているときだけトリガーする（fail-closed）。詳細は下記     |
| 7    | **スプリントレビュー + レトロスペクティブ**（`Sprint Goal:` 行のある PR のみ・完了報告の前に必須実施）。判定が `accepted`（または `accepted_with_conditions` かつ `deploy: yes`）ならデプロイ → 疎通確認 → プレビュー環境の退役（`tools/retire_preview_aliases.py`）まで実行。詳細は下記                                                                                                                                 |
| 8    | レビュー完了サマリーを **PR スレッドのみ** に記録（サイレント・L-102）                                                                                                                                                                                                                                                                                                                                                   |
| 9    | マージ後フィードバックループ → `docs/rules/lessons/pr-review.md` に教訓追記（必須・`lessons-management.md` に従う）                                                                                                                                                                                                                                                                                                      |

### Step 6: マージ直後の公開反映とデプロイゲート（#449・`sprint-env-lifecycle-20260820` 決定）

🔵 **一次経路を `wrangler deploy` の直叩きから Workers Builds の再トリガーへ変更**（Issue #451）:
`D-31` の理念（マージ＝本番反映・セッションが `wrangler deploy` を打たない）に戻す変更であり、
`npm run deploy` の手動実行は L-130（auto mode classifier ブロック）対策のフォールバックに降格する。

マージした瞬間が、公開リポジトリとのドリフトが生まれる瞬間である。**反映をセッション終了時や次回の
定期ルーティンに先送りしない**（先送りが実際に 13〜17 時間の滞留を生んだ・#449）。

- `post-merge-publish-check.sh`（PostToolUse・matcher `mcp__github__merge_pull_request`）が
  マージ成功を検知してドリフトを判定し、反映が要るときだけ指示を注入する。指示が来たら
  `publish-sync` スキルに従って **push まで完遂する**（ユーザー確認は不要・PR 種別によらず常に実行）。
- 🔴 **本番デプロイの発火点は PR 種別で分岐する**（`sprint-env-lifecycle-20260820`
  議論・lead 判定「B: 本番デプロイの発火点」・飼い主の明示指示 2026-08-19・`D-23`。`permissions.allow` に登録済み）:
  - **スプリント PR（`Sprint Goal:` 行あり）**: このステップではデプロイしない。判定は Step 7 の
    スプリントレビュー結果に委ねる（下記）。push（公開反映）だけ完遂して Step 7 へ進む。
  - **非スプリント PR**（改善 Issue・retro-try・docs 等）: 🔴 **一次経路は `python3
tools/trigger_workers_build.py`**（Workers Builds の再トリガー。内部で `tools/check_deploy_gate.py`
    を確認し、ゲートが開いているときだけトリガーする）。終了コード 0 = トリガー成功 / 1 = ゲート待機中
    （異常ではない・保留のまま次回に持ち越す）/ 2 = 判定不能（fail-closed）。スクリプトが存在しない、
    または 2 を返した場合に限り、フォールバックとして `python3 tools/check_deploy_gate.py` を直接実行し
    デプロイ可のときだけ `npm run deploy` する（L-130: `npm run deploy` は auto mode classifier に
    ブロックされることがあるため一次経路にしない）。デプロイしない場合はコマンド出力をそのまま PR/Issue
    コメントに記録する（次に該当 PR が再チェックされるまでデプロイは保留のまま）。🔴 **終了コード
    （0/1/2）の意味は `cloudflare-infrastructure.md` §8.2 の記載が SSOT**（本項では再掲しない）。
  - このゲートの目的: レビュー待ちのスプリント成果物が `main` 経由で本番へ漏れる穴を塞ぐ（release_eng が
    round 2 で採用した「デプロイの直列化」。穴を受け入れる案は撤回済み）。
- デプロイを実行する場合は 🔴 **deploy 前に `main` HEAD で `npm run check` を再実行** し（合成状態の検証）、
  deploy 後は本番 URL の疎通を確認する。**手順の実体（コマンド列）は `cloudflare-infrastructure.md` §8.2
  が SSOT**（本項では参照と判断基準のみを持ち、再掲しない）。⚠️ **これは「デプロイ実行」の委任であって、
  Layer 1 セルフレビュー・指摘対応・マージ条件を省略してよいという意味ではない**（レビュー規律は従来どおり）。
- **反映できないセッションでも黙って終わらせない**。`add_repo` が提供されない自動タスク実行モード
  （scheduled trigger・GitHub Issue/PR 起動・L-117）では push が 403 になるため、その場で
  `publish-sync` スキルの §5 に従って `[publish-sync]` Issue に失敗段階を記録する。
- ローカル実行で `gh pr merge` を使った場合はフックの matcher（MCP ツール）に掛からない。
  セッション終了時の `stop-publish-check.sh` が backstop として拾う。

### Step 7: スプリントレビュー + レトロスペクティブ（マージ + 公開反映の直後・完了報告の前・必須）

`sp1-review-retro-20260819` 議論（争点 C・lead 判定）の決定に基づく。判定後のデプロイ・退役は
`sprint-env-lifecycle-20260820` 議論（lead 判定 B/C/D）の決定に基づく。**発火条件**: マージした PR 本文に
`Sprint Goal:` 行がある（= `SP-n` スプリントの PR）。無い場合は本ステップをスキップして Step 8 へ進む。

**スコープは `SP-n` スプリントの成果物レビューに限定する**（改善 Issue・`type:retro-try` の PR は対象外）。
全パイプライン共通の `retrospective` 死蔵解消（各パイプライン終端への呼び出し追加）は本ステップの
射程外であり、別 Issue で扱う。

1. **スプリントレビューを実行する**。既定は **fan-out 2 役割**（受け入れ判定役 / 残課題の仕分け役）。
   `sp:8` のときだけ `discussion-review` スキルに切り替え、議論全文は
   `content/discussions/sprint-review-SP-{n}-{YYYYMMDD}/` に残し、Issue コメントには結論サマリーだけ書く。
2. 🔴 **受け入れ判定役の役割定義に必ず含める 5 点**（省略すると判定が浅くなり実効性が消える）:
   - `accepted_with_conditions` を選ぶ場合、**デプロイ可否（`deploy: yes|no`）を明示する**（既定は
     `yes`。「条件」がプロセス・スコープ上の残課題でありコード自体の欠陥でないなら `yes` のまま出す。
     本番影響ありと判断したときだけ `no` にする・`sprint-env-lifecycle-20260820` 争点 C）
   - 該当 `SP-n` 節が参照する **設計ドキュメントのポインタを 1 ホップ先まで辿る**（例:
     `user-story-map.md` → `cloudflare-infrastructure.md` 等の Cloudflare 固有ゲート）
   - テスト・依存規則チェック等は **実際に実行して結果で断定する**（「たぶん満たしている」は書かない・L-113）
   - Sprint Planning コメントの **`編成` 欄が単独実行になっていないか** を確認し、なっていれば
     Problem として記録する（`session-sprint-rules.md` §2 で単独実行は禁止）
   - **UI/デザイン変更を含む場合**（PR 差分が `app/**` `src/ui/**` を含む）の **デザイン観点の受け入れ判定**:
     `docs/03_design/ui-ux/ui-ux-guidelines.md` §2.4 を実際に開いて 🔴 必須行を満たすか判定する
     （「たぶん満たしている」と書かない = 上記 2 点目と同型の実行原則・L-113）。🔵 推奨行の逸脱は
     Problem として記録し次スプリントへ送る（マージ済みなのでブロックはしない）。
     🔴 **サブエージェントはプレビュー画面を開けない**。「目視で確認した」とは書かせず、
     「PR 本文のプレビュー URL を示したうえで、主要導線コントロールが §2.4 の推奨 tier を
     使っているかを **コードで** 確認した結果」と、**視覚的な最終判断は人間の操作レビューに委ねる**
     旨を書かせる。機械検査（`check_ui_dimensions.py`）の対象外である 4 領域（動的 className に
     よるサイズ上書き / 推奨値の妥当性 / 未登録コンポーネント / 実ブラウザでの体感操作性）は、
     境界の事実として書く（基準の実体は書かない）
3. 判定結果を **対象 Issue のコメント** として投稿する。**`デプロイ` 行を必ず含める**（`accepted` は
   常に `yes`、`rejected` は常に `no`、`accepted_with_conditions` は受け入れ判定役が明示した値）。
   `進捗:` 行は `sprint-cycle-router` Step 3 の stale 再開判定が読むマーカーなので必ず末尾に置き、
   **結果とデプロイ要否が分かる形** で書く（次 firing がこのコメント 1 件だけで再開判断できるように）:

   ```markdown
   ## 🔍 Sprint Review 判定

   **結果**: accepted | accepted_with_conditions | rejected
   **デプロイ**: yes | no
   **次 firing 必須**: {条件付き受け入れのときだけ・無ければ「なし」}
   **後続スプリントへ送る項目**: {箇条書き}
   **Issue クローズ条件**: {1 行}
   進捗: Sprint Review 判定済み（結果: {accepted|accepted_with_conditions|rejected}・デプロイ: {yes|no}）。次は{デプロイ実行 → 退役 → retrospective スキル起動 | retrospective スキル起動}
   ```

3.5. **デプロイ・疎通確認・退役**（`デプロイ: yes` のときのみ実行。`rejected` または `deploy: no` は
本項を丸ごとスキップして 4 へ進む・fail-closed）:

- 🔴 **一次経路は `python3 tools/trigger_workers_build.py`**（Workers Builds の再トリガー・#451。
  終了コード 0 = トリガー成功 / 1 = デプロイゲート待機中・異常ではない / 2 = 判定不能・fail-closed）。
  スクリプトが存在しない、または 2 を返した場合に限り Step 6 のフォールバック手順（`main` HEAD で
  `npm run check` 再実行 → `npm run deploy` → 本番 URL 疎通確認。**手順の実体は
  `cloudflare-infrastructure.md` §8.2 が SSOT**）をここで実行する。1（ゲート待機中）の場合は
  デプロイを実行せず、`進捗:` を「デプロイ未完了」のまま更新しない（下記の失敗時と同じ扱い。
  次回 firing は `sprint-cycle-router` Step 0.2 が拾う）。
- デプロイ成功後、**そのスプリント PR の preview alias を退役する**:
  `python3 tools/retire_preview_aliases.py --alias pr-<N>`（`<N>` は対象 PR 番号。本番と同一ビルドへ
  張り替える＝「削除」ではなく「上書き」。削除 API が存在しないことは
  `sprint-env-lifecycle-20260820` 争点 A/E で確定済み）。
- 完了したら **追加コメント** で `進捗:` を更新する（判定コメントを書き換えない・追記のみ):
  `進捗: デプロイ完了（tag: <merge commit SHA>）・退役完了（alias: pr-<N>）。次は retrospective スキル起動`
- デプロイ・退役のいずれかが失敗した場合は、失敗段階とエラー全文を同じ追加コメントに記録し、
  `進捗:` は「デプロイ未完了」または「退役未完了」のまま更新しない（次 firing の Step 3 再開が
  正しく再試行できるようにするため・下記 §「Step 3 の再開」参照）。

4. 続けて **`retrospective` スキルを起動** する（KPT 生成と Try の Issue 化。既存仕様のまま）。
5. **対象 Issue をクローズする**（本ステップの最終アクション）。判定が `rejected` / `accepted_with_conditions` で
   次 firing に持ち越すものがある場合は **open のまま残す**（`status:in-progress` も維持）。
6. 🔴 上記 1〜5（`デプロイ: yes` のときは 3.5 を含む）が未実施のまま完了報告しない（下記「注意事項」に完了条件として追加）。

🔴 **`SP-n` の PR 本文に `Closes #{Issue番号}` を書かない**（`pr-review-flow.md` の標準テンプレートの例外）。
書くとマージ時点で Issue が閉じ、Step 7 が中断したときに **`sprint-cycle-router` Step 3（`status:in-progress`
かつ open の stale Issue を再開）が拾えなくなる**（= レビューとレトロが黙って永久に実施されない）。
クローズは本ステップ 5 が行うため、Issue は Step 7 完了まで open + `status:in-progress` のまま残す。

新ラベル（`status:conditionally-accepted` 等）・新 state ファイル・新ディレクトリ規約は作らない。
記録先は既存の仕組み（Issue コメント / `content/discussions/` / `retrospective` スキルの出力）に限定する。

## サイレント原則（L-102・最重要）

AIレビュー指摘対応は **ユーザーに報告しない**。記録は PR スレッド返信・Resolve・Issue コメントのみ。
チャット逐次報告・Slack `@mention`・完了報告アウトカムへのレビュー対応混入は禁止。
例外は A-1〜A-6（サーキットブレーカー発動・ファクト致命的 NG 等）のみ。
マージ後の完了報告は `docs/rules/completion-report-rules.md`（SSOT）に従う。

## 注意事項

- 修正コミット後の再レビューに備え、`resolved` 後も監視を継続する
- 全体タイムアウトは 30 分。経過時は現状を PR コメントに記録（サイレント）
- 他セッション対応中の PR（`active_session: true`・`--actionable-only` 出力に現れない）には介入しない（CP-4・L-109）
- 🔴 `Sprint Goal:` 行のある PR をマージしたら、Step 7（スプリントレビュー + レトロスペクティブ）を実施済みでない限り完了報告しない
- 🔴 Step 7 の判定が `デプロイ: yes` の場合、デプロイ・疎通確認・退役（3.5）を実施済みでない限り完了報告しない（`sprint-env-lifecycle-20260820` D）
