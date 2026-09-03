# PRレビューフロー（サマリー版）

> 完全版は `docs/rules/pr-review-flow.md`（マージコンフリクト解決・force push 後の再レビュー・監視方式・パイプライン別チェックリスト）。
> 実行手順そのものは `pr-review-watcher` スキルが持つ。本ファイルは **判断基準と不変の境界** だけを常駐させる。

## フロー概要

```
実装 → セルフレビュー（self-reviewer）→ PR 作成 → Slack 通知
  → Layer 0 機械ゲート + Layer 1 観点別フレッシュ文脈セルフレビュー（主軸・全 PR 必須・自己実行）
  → 指摘対応（修正コミット or スキップ + 返信 + Resolve）→ Layer 0+1 通過で自動マージ（squash）
  → 🔴 **本番デプロイはゲート判定を経由**（一次経路 `trigger_workers_build.py`・フォールバック `npm run deploy` とも無条件では呼ばない。発火条件・終了コードの意味は `cloudflare-infrastructure.md` §8.2 が SSOT）
  → Slack 完了通知
```

- **🟢 恒久承認**: 実装完了したら確認なしで PR まで進める（SSOT: `CLAUDE.md`「PR 作成の完全自律化」）。「PR 作成してよいですか？」は禁止。
- **🔴 外部 AI レビュアーは廃止**: Copilot / Gemini へのレビュー依頼・催促は行わない。レビューは **Layer 1 セルフレビューで完結** させ、外部応答を待たない（SSOT: `ai-reviewer-strategy.md`）。
- **Layer 1 の標準実行手段は `Skill(code-review)`**（`.claude/skills/code-review/` が組み込みを置換・自律起動可）。

## PR 作成時の必須事項（コマンド仕様は各ツールの description に従う）

> 🔴 **品質チェックは二層構成**（`D-42`・Issue #543）。**GitHub Actions は本番デプロイには使わない**（`D-31` / `D-32` の Workers Builds が正本・不変）。
> - **層 1（CI・自動）**: `push`（`main`）と `pull_request` を契機に `.github/workflows/quality-checks.yml` が
>   Prettier `format:check` → ESLint `lint` → `tsc --noEmit` → Vitest `test` を自動実行する（読み取り権限のみ・自動マージもデプロイもしない）。
>   🔴 **層 1 の被覆はごく一部**: CI が見るのは `tools/run_checks.sh` に定義された **70 件規模**（実測 74 件・2026-08-31 JST 時点。件数は増え続けるので、正確な数は `grep -cE '^\s*run_check(_timeout)? ' tools/run_checks.sh` でその場で数える）のチェックのうち **4 件だけ**。
>   残り（E2E・Lighthouse・依存規則 `check_architecture_boundaries.py`・CJK Markdown・LP 静的検査・各 self-test など）は層 2 が唯一の担保であり、
>   **CI 緑は層 2 の省略理由にならない**。※ `.prettierignore` が `docs/` `content/` `site/` `public/data/` を除外しているため、
>   **ドキュメントのみの PR では CI が実質空振りの緑を返す**（層 2 の CJK Markdown 検査などが本当の担保になる）。
> - **層 2（セッション・手動）**: **E2E と Lighthouse a11y ゲートは CI に含めない**（1 PR あたりの待ち時間に見合わないため）。
>   従来どおり **セッション（Claude）が `bash tools/run_checks.sh` を実行し、結果のサマリー表を PR 本文へ貼る**（下記 0 は引き続き必須）。
> - **本番・プレビューのデプロイ** は引き続きセッションが `wrangler` を直接叩く / Workers Builds に委ねる（Actions からはデプロイしない）。
>
> 定期バッチ用途としては **Gem 候補プールの日次実行 + 週次反映にも** Actions を使う（`D-40`・Issue #458 / #482・PR を作るところまでで自動マージしない）。
> 生成・機械 QA は毎日走らせるが、`main` への反映（PR 作成）は生成物が 7 日以上前のときだけ行う（マージ頻度が git 履歴コストを決めるため）。

0. **PR 作成前チェック（層 2 の証跡・CI と重複しても省略しない）**: `npm run check`（= `bash tools/run_checks.sh`）を実行し、**結果の Markdown サマリー表を PR 本文に貼る**（貼っていないと `pre-pr-create-check.sh` が PR 作成をブロックする）（`tools/run_checks.sh` 自体の中身は別レーンの持ち物・本ファイルは呼び出し方のみ規定する）。**見出しは `##` 固定で `run_checks` または `npm run check` を含める（`pre-pr-create-check.sh` の検出仕様が SSOT・Issue #405 / PR #456）**: `## run_checks 結果` / `## npm run check 結果` のいずれか（`run_checks` / `npm run check` の部分はバッククォートで囲んでも囲まなくても良い）。同じ見出しが複数回出てきても構わない（いずれか 1 か所が満たしていれば可）。その見出しから次の `##` 見出しまでの間（無関係な別セクションの表・コードフェンス内の例示は不可）に表（`|` 区切り行）があること
0.5. **プレビュー URL の取得**: プレビューデプロイに GitHub Actions は使わず、**セッションが `npx opennextjs-cloudflare build` → `npx wrangler versions upload --preview-alias pr-<N>` を実行** して取得したプレビュー URL を PR 本文へ貼る（`sprint-development-rules.md` `SD-1` の「開けるプレビュー URL」要件をこの経路で満たす）
0.7. **自動保全コミットの書き換え（必須・base#483）**: ブランチに `[wip]` 件名の自動保全コミットが残っていたら、PR 作成前に意味のある粒度・メッセージへ書き換える。`pre-pr-create-check.sh` が機械ブロックし、書き換え手順（amend / `reset --soft` 起点の再コミット）をエラーメッセージ内に案内する
1. `mcp__github__create_pull_request`（`head`={作業ブランチ} / `base`=main）。本文に **`Session-Id: $CLAUDE_CODE_SESSION_ID`**・`Sprint Goal:` 1 行・`sp:N`・**`Team:` トレーラー**（例 `Team: fan-out(3)`・Issue の `編成` 欄の同期コピー）を必ず含める（`--mine` 所有判定と done_sp 計測の前提）。🔴 **`SP-n` のスプリント PR には `Closes #N` を書かない**（Issue のクローズは `pr-review-watcher` Step 7 の最終アクション）
2. **PR 存在確認（必須・L-050）**: `mcp__github__list_pull_requests` で `head` を指定して実在を確認する（作成の成否をレスポンスだけで判断しない）
3. Slack 通知: `python3 tools/slack_notify.py pr --pr-url ... --pr-title "[PR作成] ..." --branch ...`
4. **Layer 1 セルフレビュー**: `Skill(code-review)` を必ず実行 → **指摘は全件 PR の行単位インラインコメントで記録**（指摘ゼロでも `event="COMMENT"` のレビューを 1 件投稿する・#461）
5. （任意）`mcp__github__subscribe_pr_activity` + `tools/pr_review_heartbeat.sh` で CI / 人手コメントを監視

> ローカル実行時は `gh pr create --head {branch} --base main -R {owner}/{repo}` でもよい。クラウドでは MCP が一次経路。

## レビュー監視と自動マージ

| タイミング | アクション |
|---------|-----------|
| PR 作成直後 | Layer 1 セルフレビュー → **指摘を行単位インラインコメントで投稿** → 指摘対応（修正コミット or スキップ + **同一スレッドへの返信** + Resolve） |
| **マージ前** | 🔴 **`quality-checks.yml` の check run が緑であることを確認する**（`mcp__github__pull_request_read` の `method="get_check_runs"` または `method="get_status"`。`mcp__github__get_check_run` は check run ID を引数に取るため PR からは引けない）。**赤いままマージしない**（強制力は未配線＝`main` の required status check には未登録なので、運用規律として守る）。⚠️ **例外**: `gem-pool-refresh.yml` が `secrets.GITHUB_TOKEN` で作る `automation/gem-pool-refresh` PR には、GitHub 公式仕様（`GITHUB_TOKEN` 由来のイベントは新しい workflow run を作らない）により **check run が生成されない**。この PR は check run 不在をもって赤とみなさず、同ワークフロー自身の QA ステップが品質を担保する（必要なら `workflow_dispatch` で明示起動して検証できる） |
| Layer 0+1 通過後 | **上記の CI が緑であることを確認したうえで** `mcp__github__merge_pull_request`（`merge_method="squash"`）で即マージ |
| **マージ直後** | 🔵 **`site/`（LP）を変更していたら `gh-pages` ブランチへ同期する**（手順の正本は [`site/README.md`](../../site/README.md)・決定は `D-35`）。続けて 🔴 **本番デプロイの発火条件をゲート判定**（`Sprint Goal:` 行ありなら Step 7 のスプリントレビュー判定へ委譲・無ければ `tools/check_deploy_gate.py` の結果に従う。判断基準・終了コードは `cloudflare-infrastructure.md` §8.2 が SSOT・実行手順は `pr-review-watcher` スキル Step 6/7）→ Slack 完了通知 |
| 任意 | 人手コメントがあれば対応してからマージ |

サーキットブレーカー: 修正サイクル 2 回超で STOP → ユーザー報告（A-4）。

**マージ後のチャット完了報告は `completion-report-rules.md`（SSOT）に従う**: 「ご依頼（初回指示の再掲）→ アウトカム」を冒頭に置き、マージ方法・レビュー往復・指摘件数を主役にしない。「PR #N をマージしました」だけで終わらせない。

## 指摘対応ルール

- **記録先は PR の行単位インラインコメント（必須・#461）**: 指摘は確度（CONFIRMED / PLAUSIBLE）を問わず全件インライン化し、対応結論は **同一スレッドへの返信** で残す（新規コメントに分離しない）。指摘ゼロでもレビューを 1 件投稿する。手順・テンプレート・フォールバックの SSOT は `.claude/skills/code-review/SKILL.md` Step 3-A
- **サイレント原則（L-102）**: AI レビュー指摘対応は **ユーザーに報告しない**。記録は PR スレッド返信・Resolve・Issue コメントのみ（Slack `--outcome` にセルフレビュー実施・指摘件数を書くのも違反）。チャット逐次報告・Slack `@mention`・完了報告アウトカムへの混入は禁止。例外は A-1〜A-6 のみ
- **`<github-webhook-activity>` は抑制対象ではない（#61・詳細は `pr-review-flow.md`「入力とチャット出力の区別」）**: ハーネスが配信する入力であり L-102 の対象外
- 対応した場合: 「対応しました。{修正概要}（{commit_sha}）」を返信してから Resolve
- スキップした場合: 「スキップします。理由: {理由}」を返信してから Resolve（製品名・API 仕様は公式ドキュメントで確認してから記録する）

## セッション復帰（PR 放置検出）

```bash
python3 tools/check_pending_pr_reviews.py --mine --actionable-only --json   # ① 自 PR を最優先で回収
python3 tools/check_pending_pr_reviews.py --actionable-only --json          # ② 他保護込みの全体ビュー（孤児 PR 救済）
```

`needs_prompt` → Layer 1 セルフレビュー実行 → 指摘解消 → 即マージ / `needs_response` → 指摘対応（CI 失敗・人手コメント）/ `awaiting_review` → 作成セッションが実行中（待機）。**自スコープ優先（#47）・他セッション対応中 PR への不介入（CP-4・L-109）** の判定ロジック全文は `pr-review-flow.md`「セッション復帰フロー」を参照。

**公開反映（`publish-sync` レーン）は本リポジトリでは採用しない（#407）**: 本リポジトリ自体が公開リポジトリであり、別の公開リポジトリへ反映するレーンを持たない。したがって `tools/check_publish_drift.py` / `publish-sync` スキルは **実装予定ではなく不要** であり、セッション復帰時に `[publish-sync]` Issue を回収する責務も無い（ベース由来の `post-merge-publish-check.sh` は `tools/check_publish_drift.py` 不在時に publish-sync の指示を出さないだけで、`Sprint Goal:` を含む PR のマージでは Sprint Review + Retrospective の実施リマインド（Issue #69）を注入する。配線を削除しないこと）。

- **bot 自動化 PR も回収対象（`D-43`）**: `automation/gem-pool-refresh`（`github-actions[bot]`）と Dependabot（`dependabot/...` プレフィックス・`dependabot[bot]`）の 2 系統は、`authorAssociation` が信頼集合に入らないが `check_pending_pr_reviews.py` の専用述語（`_is_automation_pr()` / `_is_dependabot_pr()`）が **fork 不可 + ブランチ条件 + 著者ログイン固定の 3 条件 AND** で通すため、`needs_prompt` として出力される。これらも自 PR と同じく Layer 1 セルフレビュー → マージまで進める（放置すると `open-pull-requests-limit` に達して自動化が黙って止まる）
