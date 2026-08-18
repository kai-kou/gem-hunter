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

## cron 式（現在の設定）

```
0 1,3,5,7,9,11,13,15,17,19,21,23 * * *
```

**2 時間ごと・JST の偶数時ちょうど**（00:00 / 02:00 / … / 22:00 JST）に発火する。
cron は UTC で評価されるため、JST の偶数時は UTC の奇数時になる（UTC = JST − 9 時間・`datetime-rules.md`）。

理由: `N`（発火間隔）は「スプリントが完了する保証の単位」ではなく **健全性チェックの再訪頻度**。
決定木は Step 0.1 で数クエリの早期リターン判定を行い、対象が無ければ安く no-op で抜ける
（詳細は `sprint-cycle-router` SKILL.md §0 / §2）。

### 🔴 ステップ構文（`0 */2 * * *`）を使わない — 分が 0 に固定されないため

Routine 作成 / 更新 API は **「毎時」「N 時間ごと」をステップ構文で書くと、分を作成（更新）時刻の分へ
サーバー側でアンカーする**（"hourly starting now" 挙動）。実測:

| 送った cron | 保存された cron | 結果 |
|---|---|---|
| `0 * * * *` | `53 * * * *` | ❌ 毎時 53 分にずれる |
| `0 */2 * * *` | `2 */2 * * *` | ❌ 2 時間ごと 02 分にずれる |
| `0 1,3,5,...,23 * * *` | `0 1,3,5,...,23 * * *` | ✅ **そのまま保存される（分 0 を維持）** |

**時刻をカンマ区切りのリストで書けば verbatim 保存される**（ステップ構文以外は無加工）。
分 0 ちょうどで回したい場合は、下表のリスト形式をコピーして使う。

### 発火間隔を変えたいとき（この 1 行を差し替えるだけ）

すべて **分 0 固定・JST の 0 時起点** で揃えてある。決定木側の変更は不要。

| 間隔 | JST の発火時刻 | cron 式（UTC・そのまま貼る） |
|---|---|---|
| 1 時間ごと | 毎時 00 分 | `0 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23 * * *` |
| **2 時間ごと（現在）** | 00, 02, 04, … 22 時 | `0 1,3,5,7,9,11,13,15,17,19,21,23 * * *` |
| 3 時間ごと | 00, 03, 06, … 21 時 | `0 0,3,6,9,12,15,18,21 * * *` |
| 4 時間ごと | 00, 04, 08, 12, 16, 20 時 | `0 3,7,11,15,19,23 * * *` |
| 6 時間ごと | 00, 06, 12, 18 時 | `0 3,9,15,21 * * *` |
| 12 時間ごと | 00, 12 時 | `0 3,15 * * *` |

**変更方法**: Routine 設定画面のスケジュール欄（または `mcp__Claude_Code_Remote__update_trigger` の
`cron_expression`）を上表の 1 行に差し替える。差し替え後は保存された値を必ず読み返し、分が 0 のまま
であることを確認する（アンカー挙動に当たっていないかの確認・L-113）。

⚠️ 間隔を広げるほど「自 PR の回収」「stale スプリントの再開」も遅くなる（Step 2 / Step 3）。
逆に狭めても、対象が無い firing は早期リターンで安く抜けるため無駄は小さい。

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
| `cron_expression` | `0 1,3,5,7,9,11,13,15,17,19,21,23 * * *`（上表から選ぶ。ステップ構文は分がずれる） |
| `create_new_session_on_fire` | `true`（毎 firing 新規セッション。`sprint-cycle-router` SKILL.md §0 の実行モデル「毎回新規セッション・エフェメラル VM」の前提と一致させる） |
| `environment_id` | 対象環境の ID（`mcp__Claude_Code_Remote__list_environments` で確認） |

既存 R-1 ルーティンが `persistent_session_id` 等で稼働中の場合は、新規作成ではなく
`mcp__Claude_Code_Remote__update_trigger` でそのルーティンの `prompt` を本ファイルの内容に
統合する（cron は 1 本のみという制約を守るため）。

#### 🔴 MCP 経由で作成したときに欠ける 2 つ（実測・2026-08-18）

`create_trigger` MCP ツールには **リポジトリ（source）とコネクタを指定するパラメータが無い**。
作成直後のレスポンスにも `sources` / `mcp_connections` は入らない。実測で分かったのは次のとおり:

| 項目 | 実測結果 | 対応 |
|---|---|---|
| リポジトリ（source） | **発火時に Environment から解決されて付く**（`fire_trigger` のレスポンスに `sources: kai-kou/gem-hunter` と作業ブランチが入った） | 対応不要。ただし Environment にリポジトリが紐づいていることが前提 |
| GitHub MCP（`mcp__github__*`） | **使える**（発火セッションで `mcp__github__list_issues` が成功することを実測。トリガーの `mcp_connections` が空でも影響しない） | 対応不要 |
| claude.ai の connector（Slack / Google Drive 等） | 作成時に「this trigger stores no MCP connectors」と警告が出る。呼び出し元セッションが渡せる grant を持たないため付かない | **これらの connector を使う予定がある場合のみ** Web UI 側で付与する（下記 B） |

⚠️ 仮に MCP が届かない firing があっても GitHub 操作は止まらない。`sprint-cycle-router` SKILL.md §1 が
`mcp__github__*` → `gh` → `curl + $GH_TOKEN` の 3 段フォールバックを毎 firing 判定するため。
Slack 通知は MCP ではなく `tools/slack_notify.py`（環境変数の webhook）経由なので connector 非依存。

🔵 **実測の結論: MCP 経由で作成したルーティンでも、ユーザーの追加操作なしで決定木は動く。**
`fire_trigger` で発火させたセッションが ① リポジトリのクローンあり ② `SKILL.md` 読み込み成功
③ `mcp__github__*` 成功 の 3 点すべてを満たした（記録は Issue #42 のコメント）。

### B. Web UI（Routine 設定画面）から設定する場合

1. 「新しい Routine を作成」から名前を `sprint-cycle-router` とする
2. プロンプト欄に上記「ルーティンに貼るプロンプト全文」を貼り付ける
3. スケジュールを「2 時間ごと」（`0 1,3,5,7,9,11,13,15,17,19,21,23 * * *` 相当）に設定する
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
