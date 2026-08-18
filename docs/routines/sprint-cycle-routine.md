# スプリント自走ルーティン（設定手順・保管用）

> 飼い主が Claude Code の Routine 設定画面（または `mcp__Claude_Code_Remote__create_trigger`）に
> **そのまま貼れる** 設定値の保管先。決定木の実体（判定ロジック・Step 番号・委譲先）は
> `.claude/skills/sprint-cycle-router/SKILL.md` が持つ **唯一の正本（SSOT）** であり、
> 本ファイルには複製しない。

## このルーティンは単一である

開発（Step 4）・改善 Issue 消化（Step 5）・衛生（Step 6）・リファインメント（Step 7）・
`claude-code-spec-sync`（Step 1 / 8）を **すべて 1 本の決定木**（`sprint-cycle-router` スキル）に
束ねている。別 cron・別ルーティンを追加で作らない（飼い主要求「単一のルーティン設定内で」との
整合を保つため）。既存 R-1 ルーティンが別スロットで稼働している場合は、本ルーティンへ統合し
cron は 1 本だけ持つ。

## cron 式

```
0 * * * *
```

**1 時間ごと（UTC 評価）**。理由: `N` は「スプリントが完了する保証の単位」ではなく **健全性チェックの
再訪頻度**。決定木は Step 0.1 で数クエリの早期リターン判定を行い、対象が無ければ安く no-op で
抜けるため、短い間隔で回しても空振りコストは低い（詳細は `sprint-cycle-router` SKILL.md §0 / §2）。

**変更方法**: この cron 式を書き換えるだけでよい（決定木側の変更は不要）。頻度を落としたい場合は
例えば `0 */2 * * *`（2 時間ごと）に変更する。

⚠️ **cron は UTC で評価される**。JST 表記で運用を語るときは `datetime-rules.md` に従い
UTC = JST − 9 時間で換算する（例: JST 09:00 に触れたい場合は UTC 00:00 = `0 0 * * *`。ただし
本ルーティンは「特定時刻に触れる」設計ではなく「毎時 1 回、健全性を再チェックする」設計のため、
通常は `0 * * * *` のままでよい）。

## ルーティンに貼るプロンプト全文

以下をそのままコピーして Routine のプロンプト欄に貼る。**決定木の本文はここに複製しない**
（SSOT は `.claude/skills/sprint-cycle-router/SKILL.md`）。

```
Skill(sprint-cycle-router) を実行する。

前提:
- これは無人の定期実行である。ユーザーは今この場にいない。
- AskUserQuestion は使わない（無人 firing での仕様解釈分岐は SKILL.md §6 の手順に従う）。
- 完了報告はチャットに逐次出力せず、対応した Issue / PR へのコメント記録のみで完結させる
  （サイレント原則。L-102 / completion-report-rules.md）。ユーザーへの @mention が必要なのは
  A-1〜A-6 該当時（user-confirmation-minimization.md §1）と、M-3 到達 Issue の初回起票時のみ。
```

## 設定手順

### A. `mcp__Claude_Code_Remote__create_trigger` を使う場合

| パラメータ | 値 |
|---|---|
| `name` | `sprint-cycle-router`（またはプロジェクトの命名規約に合わせる） |
| `prompt` | 上記「ルーティンに貼るプロンプト全文」 |
| `cron_expression` | `0 * * * *` |
| `create_new_session_on_fire` | `true`（毎 firing 新規セッション。`sprint-cycle-router` SKILL.md §0 の実行モデル「毎回新規セッション・エフェメラル VM」の前提と一致させる） |
| `environment_id` | 対象環境の ID（`mcp__Claude_Code_Remote__list_environments` で確認） |

既存 R-1 ルーティンが `persistent_session_id` 等で稼働中の場合は、新規作成ではなく
`mcp__Claude_Code_Remote__update_trigger` でそのルーティンの `prompt` を本ファイルの内容に
統合する（cron は 1 本のみという制約を守るため）。

### B. Web UI（Routine 設定画面）から設定する場合

1. 「新しい Routine を作成」から名前を `sprint-cycle-router` とする
2. プロンプト欄に上記「ルーティンに貼るプロンプト全文」を貼り付ける
3. スケジュールを「毎時」（`0 * * * *` 相当）に設定する
4. 実行モードは「毎回新規セッション」を選ぶ（既存の対話セッションに固定しない）
5. 保存後、初回発火前に本ファイルと `sprint-cycle-router` SKILL.md の内容が一致していることを確認する

## 停止・一時停止の方法

- **一時停止**: `mcp__Claude_Code_Remote__update_trigger` で `enabled: false` を渡す（Routine 定義は
  残るため、再開時は `enabled: true` に戻すだけでよい）
- **完全停止**: `mcp__Claude_Code_Remote__delete_trigger` で該当 `trigger_id` を削除する
- Web UI からは Routine 一覧の該当行でトグル操作、または削除操作を行う

## 参照

| ドキュメント | 関係 |
|---|---|
| `.claude/skills/sprint-cycle-router/SKILL.md` | 決定木の実体（判定ロジック・Step 番号・委譲先の SSOT） |
| `docs/rules/session-sprint-rules.md` | スプリントの単位・`sp:N` |
| `docs/rules/sprint-development-rules.md` | Step 4 が実行する `SD-1`〜`SD-4` |
| `content/discussions/sprint-cycle-design-20260818/whiteboard.md` | 本ルーティン設計の議論全文 |
