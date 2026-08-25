---
name: retrospective
description: 各ワークフロー実行後に Agent Teams（3役割の並列サブエージェント）でレトロスペクティブを実施し、KPT（Keep/Problem/Try）を生成・Try アイテムを GitHub Issue 化する。各パイプライン（プロジェクト定義）の最終ステップから自動呼び出しされ、「レトロスペクティブして」「/retrospective」で手動実行も可能。KPT 生成・Try の Issue 化までが役割で、生成済み Try Issue の実装は retro-try-handler が担う。
effort: medium
---

> 🔴 **GitHub 操作の経路（必読・L-114）**: クラウド実行環境では `gh` がプリインストールされず、
> 導入しても repo スコープ REST が 403 になる。**本ファイル内の `gh ...` コマンドはローカル実行専用** で、
> クラウドでは `mcp__github__*` に読み替える（対応表: `docs/rules/github-mcp-fallback-patterns.md` §2。
> ラベル一覧/作成・マイルストーン・release 作成・variables は MCP に等価が無く **クラウドでは実行不可**・同 §2.5）。

# レトロスペクティブスキル

ワークフロー完了後に KPT レトロスペクティブを自動実施し、Try アイテムを Issue 化する汎用スキル。

- 詳細ルール: `docs/rules/retrospective-rules.md`
- 詳細プロンプト・コマンド・出力テンプレート: 本スキルの `reference.md`（各 Step 実行直前に該当セクションだけを Read する）

> 🔴 クラウド実行環境では repo スコープの `gh`（REST + GraphQL）が egress プロキシに 403 でブロックされる（L-114）。
> 本スキルの GitHub 操作は GitHub MCP（`mcp__github__*`）を一次経路とし、`gh` コマンド例は **ローカル環境向けの代替** として読む
> （SSOT: `docs/rules/github-mcp-fallback-patterns.md`）。

## トリガー条件

- 各パイプライン（プロジェクト定義）の最終ステップから自動呼び出し
- 「レトロスペクティブして」「振り返りして」「KPTして」「/retrospective」
- `/retrospective {pipeline} {ID}` のように対象を指定して手動実行
- **パイプライン失敗時にも自動トリガー（「根本原因を特定して再発防止してください」不要）**: 同一エラーパターン2回以上 / サーキットブレーカー発動（AIレビュー修正サイクル2回超）/ 品質ゲート未達 / セルフレビュー Error 未解消

### 失敗時レトロスペクティブの判断基準

| 状況                                     | 自動実行するか                    |
| ---------------------------------------- | --------------------------------- |
| パイプライン完了（成功）                 | ✅ 毎回実行                       |
| サーキットブレーカー発動                 | ✅ 自動実行（STOP直後）           |
| 同一エラー2回目以降                      | ✅ 自動実行                       |
| 品質ゲート未達（プロジェクト定義の閾値） | ✅ 自動実行（ユーザー報告の前に） |
| 1回限りの軽微なエラー（リトライで解決）  | ⬜ スキップ可                     |

**失敗時に `type:retro-try` Issue を生成することで、再発防止策が自動で蓄積される。** これにより「根本原因を特定して再発防止してください」はユーザーが言わなくてよい指示になる。

## 前提条件

- 対象ワークフローの実行が完了またはサーキットブレーカーで停止していること（未完了でも失敗レトロ目的で実行可）
- GitHub MCP（`mcp__github__issue_write`）が利用可能で、`type:retro-try` ラベルが作成済みであること

## 実行フロー概要

```
Step 0: コンテキスト収集（git log・PR情報・品質メトリクス）
  ↓
Step 1: Agent Teams 起動（3役割を並列サブエージェント・全て haiku）
  ├── 成果物品質レビュアー
  ├── プロセス・自動化レビュアー
  └── 技術・ツールレビュアー
  （Step 1.5: プロジェクト定義のレビュー役スポット監査・特定パイプラインのみ・並列）
  ↓
Step 2: KPT 結果のマージ・重複統合
  ↓
Step 3: Try アイテムの起票フィルタリング（#417）→ GitHub Issue 化（重複チェック → 追記 or 新規作成）
  ↓
Step 4: Slack 通知 → Step 5: 完了報告 → Step 6: lessons 更新チェック
```

---

## Step 0: コンテキスト収集

パイプラインから渡されたパラメータ（`pipeline` / `entity_id` / `pr_url` / `execution_summary`）を受け取り、補足情報を収集する。手動実行時はパラメータ未指定でも可（直近の git log から推測）。

```bash
git log --oneline -20   # 直近20コミット
git status              # ステージ・作業ツリーの状態
# pr_url が渡された場合は mcp__github__pull_request_read で PR 情報を取得
```

直近コミット・PR から品質メトリクスを読み取る: ドメイン固有の検証フラグ件数（該当パイプラインのみ）・セルフレビュー Error/Warning 件数・AIレビュー指摘件数・中断/リトライ発生有無。

---

## Step 1: Agent Teams 起動（3役割を並列実行）

以下の3つのサブエージェント（全て model: haiku）を `Agent` ツールで **同時に並列起動** する。各役割の担当範囲は次のとおり:

| 役割                       | 担当範囲                                                |
| -------------------------- | ------------------------------------------------------- |
| 成果物品質レビュアー       | 成果物品質・キャラ/トーン一貫性・ドメイン固有の検証精度 |
| プロセス・自動化レビュアー | ワークフロー効率・ボトルネック・自動化の有効性          |
| 技術・ツールレビュアー     | ツール・スクリプト・ドキュメントの整合性                |

- 共通プロンプト構造・役割別の詳細評価観点リスト → `reference.md` の A〜D
- 各役割は KPT を JSON 形式で出力する（出力フォーマット・`urgency`/`done_type` フィールド定義 → `reference.md` の E）
- **Step 1.5**（プロジェクト定義のレビュー役スポット監査・特定パイプラインのみ）も同時に並列起動する → `reference.md` の Step 1.5。本人視点の一言は Step 5 完了報告の末尾に添えるのみで KPT 判定には影響しない

#### フォールバック: `Agent` が利用不可の場合

実行環境（委譲先のサブエージェント等）で `Agent` ツールが使えない場合は、以下の代替手順を実施する:

| 条件                           | 代替手順                                                                                               | 品質への影響                                                                                           |
| ------------------------------ | ------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------ |
| `Agent` が利用不可と判定された | **3 役割を順次適用**（並列ではなく逐次実行）する。独立性は無いため、同じ思い込みを共有する可能性がある | **但し書きを Step 5 完了報告に記載する**: 「独立性を担保した 3 レンズではなく、逐次適用の 3 観点です」 |

---

## Step 2: KPT 結果のマージ

3つのサブエージェントの JSON 結果を統合する。

1. **Keep / Problem の統合**: 役割別にカテゴライズして一覧化する
2. **Try の統合・重複排除**: 複数役割から同じ改善案が出たら1つにまとめ、最も高い `priority` を採用し、`detail` に両方の視点を記載する

---

## Step 3: Try アイテムの起票フィルタリング → GitHub Issue 化

> 🔴 **流入抑制（Issue #417）**: `type:retro-try` の起票は流出能力（`sprint-cycle-router` Step 5.5 の消化ペース・エージング X=8h で 1 日 3 回 firing × 5 件/回 = **15 件/日**）を継続的に上回っていた（実測: 3 日平均 **31 件/日** の起票）。**全 Try アイテムは Step 3-A（重複チェック）より前に、まず下記 Step 3-0 の起票要否フィルタを通す**。
>
> **本フィルタ適用後の想定流入**: 実測 31 件/日 × `priority:high` 相当の通過率（#417 の実測で `type:retro-try` 113 件中 `priority:high` は 34 件 ＝ **30.1%**）≒ **9〜11 件/日** となり、流出上限 15 件/日を下回る。あわせて 1 回のレトロあたり **最大 5 件** の上限ゲートが単日バースト（実測: 2026-08-20 の 49 件）を抑える。
>
> ⚠️ **この 30.1% は既存ラベルの分布であって、新基準（`Q1` / `Q2`）で判定し直した通過率ではない。** 実効の収支は **適用後 1 週間の実測で確認する**（#417 の残タスク・手順は同 Issue のコメント）。想定どおり下回らなければ `Q1` / `Q2` の閾値を締め直す。

統合済みの全 Try アイテムを `high` → `medium` → `low` の順に処理する。**ただし処理の前に、下記「0. 前回持ち越し分の合流」を必ず先に実行する。**

### Step 3-0: 起票要否フィルタ（新設・#417）

#### 0. 前回持ち越し分の合流（必須・最初に実行）

見送りログ（下記 3 節）を読み、`defer_reason: "over_quota"` かつ未再評価（`reevaluated_at` フィールドが無い）の行を抽出し、**今回検出した Try より優先して** 今回の処理対象の先頭に合流させる。これが無いと「次回持ち越し」は名目だけになる（CRITICAL 1 の再発防止）。

```bash
# 前回持ち越し分の抽出（未再評価のみ）
jq -c 'select(.defer_reason == "over_quota" and (.reevaluated_at == null))' \
  content/analytics/retro/deferred_try.jsonl 2>/dev/null
```

合流させた Try がこの回で再度 Step 3-0 を通過し終えたら、**元のログ行に `"reevaluated_at": "{YYYY-MM-DD HH:MM JST}"` を追記する**（read-modify-write。同一行を無限に合流させないためのマーカーで、履歴としては残す）。再度 `over_quota` になった場合は、新しい行を追記して二重管理する（古い行を上書きしない）。

#### 1. `priority:high` 相当の判定基準

reproducible な YES/NO 問い。`try.priority` フィールドの値をそのまま使わず、以下 3 問で判定し直す。🔴 **`Q1` または `Q2` が YES のときだけ high 相当** として扱う:

| #                              | 問い（YES/NO）                                                                                                                                                                                 | 参照する既存情報                                                         |
| ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| Q1（再発）                     | 同種の Problem が **過去に 2 回以上** 検出されているか？                                                                                                                                       | 下記「4. Q1 の予備検索」の実行結果（見送りログ + `docs/rules/lessons/`） |
| Q2（正しさ毀損）               | 対応する Problem の `detail` を読み、放置すると成果物の正しさ（本番の挙動・提出物の事実性・ユーザーに見える出力）が壊れる、またはパイプラインが停止する/データを破壊する内容だと判断できるか？ | Problem の `detail` そのもの（下記「5. Q2 の判定」参照）                 |
| Q3（機械検査なし・**補助軸**） | 人手のレビュー・振り返りでしか気づけない問題か（対応する機械チェック・CI・フックが存在しないか）？                                                                                             | 該当する `tools/*.py` / `run_checks.sh` / フックの有無                   |

🔴 **`Q3` は単独で high と判定しない。** 振り返りで挙がる Try は **ほぼ全件が「まだ機械検査がない」もの** なので、`Q3` 単独 YES を high にすると全通しになり絞りが機能しない（本フィルタの目的が消える）。`Q3` は **high と判定した Try の対策方針**（機械検査を新設するか / ルールの明文化で足りるか）を決めるために記録する軸であり、優先度の判定には使わない。

#### 2. 判定フロー（全 Try アイテムがこの分岐のいずれか 1 つに必ず落ちる。どの導線にも乗らない Try は存在しない）

> 🔴 **起票上限ゲートは Step 3-A（重複チェック）の後・Step 3-C（新規作成）の直前に置く**（#417 レビュー WARNING 1）。quota が新規 Issue 作成のみを絞るものであり、重複チェック・既存 Issue へのコメント追記は quota と無関係に常時実行する（quota 消費前に弾くと、既存 Issue への追記で済むはずの Try まで「持ち越し」に誤分類される）。

```
Q1 または Q2 が YES？（Q3 は判定に使わない）
  ├─ YES（priority:high 相当）→ Step 3-A（重複チェック。quota と無関係に常時実行）
  │      ├─ 類似 Issue あり → Step 3-B（既存 Issue へコメント追記。quota を消費しない）
  │      └─ 類似 Issue なし → 起票上限ゲート（1 回のレトロ実行あたり新規 Issue 作成は最大 5 件）
  │             ├─ 上限内 → Step 3-C（新規 Issue 作成。quota を 1 消費）
  │             └─ 上限到達 → 見送りログに `defer_reason: "over_quota"` で追記（Issue化しない。今回は起票せず次回へ持ち越す）
  └─ NO（Q1 も Q2 も NO ＝ priority:high 相当ではない）
        ├─ かつ try.priority == "low" かつ影響ファイルが単一 → 「lessons 直記載」（下記）で完結 **かつ** 見送りログに `defer_reason: "low_single_file"` で追記（`related_issue` に lessons の `L-{N}` を記録）
        └─ それ以外（medium 相当、または low だが複数ファイルに影響）→ Step 3-A（重複チェック）
              ├─ 類似 Issue あり → Step 3-B（既存 Issue へコメント追記。新規起票はしない。#393 の重複検索必須化と整合）
              └─ 類似 Issue なし → 見送りログに `defer_reason: "medium"` で追記（Issue化しない）
```

**起票上限ゲートの根拠**: 流出上限 15 件/日 ÷ 1 日 3 回 firing（`sprint-cycle-router` Step 5.5・エージング X=8h）= **5 件/firing**。1 回のレトロ実行での新規 Issue 作成をこの 5 件/firing の消化能力に揃えることで、起票バースト（実測: 2026-08-20 に単日 49 件）が起きても、その回だけで 1 firing 分の処理能力を超えて在庫を積み増さない。

**lessons 直記載**（priority:low かつ単一ファイル完結の場合）: Issue化せず、Step 6 条件 A と同じ手順・フォーマット（`reference.md` の I 節）で `docs/rules/lessons/{カテゴリ}.md` に直接追記して完結させる（`try.title` → パターン名 / `try.detail` → 対策）。**Hot 層（`lessons-core.md`）へは昇格させない**（`lessons-management.md` §2 の既定どおり Warm 直行）。**lessons への追記に加えて、見送りログにも `defer_reason: "low_single_file"` で 1 行追記する**（Q1 の予備検索が 1 箇所を grep するだけで済むようにするため。二重記録ではなく用途が異なる: lessons は対策の実体、見送りログは「起票しなかった」という事実の索引）。

#### 3. 見送りログ（`content/analytics/retro/deferred_try.jsonl`・必須ステップ）

🔴 **上記フローで「見送りログに追記」となった全ケースは、この追記を完了して初めてそのアイテムの Step 3 処理が完了したとみなす**（省略可能な後始末ではない。「Issue アイテムを Issue 化せずに済ませる」ことは、この追記が完了するまで許されない）。

配置・フォーマットは既存の `content/analytics/sprint/*.jsonl`（`docs/rules/session-sprint-rules-detail.md` §5・「日次メトリクスは JSONL に追記してコミット対象にする」という既存の作法）に倣い、**追記専用の JSONL・1 行 1 レコード** とする。

🔴 **このログは追跡対象でなければ意味がない。** `.gitignore` は `content/analytics/*` を除外しているため、`!content/analytics/retro/` の再包含を入れてある（`content/analytics/sprint/` と同じ扱い・#417）。追跡されないとクラウドではコンテナ破棄でログごと消え、`Q1` の判定材料が永久に貯まらず、Step 3-0 が「初回は必ず見送り、記録が残らないので次回も見送る」自己ロックに戻る。`git check-ignore content/analytics/retro/deferred_try.jsonl` が **何も出力しない**（＝無視されない）ことが前提条件にゃ。

```jsonl
{
  "date": "2026-08-24 JST",
  "title": "{try.title}",
  "q1": "NO",
  "q2": "NO",
  "defer_reason": "medium",
  "related_issue": null
}
```

| フィールド       | 内容                                                                                                                           |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `date`           | 見送り判定日（JST・`YYYY-MM-DD JST`）                                                                                          |
| `title`          | `try.title`                                                                                                                    |
| `q1` / `q2`      | 判定結果（`"YES"` / `"NO"`）                                                                                                   |
| `defer_reason`   | `"medium"`（優先度不足・重複なし）/ `"over_quota"`（上限超過）/ `"low_single_file"`（lessons 直記載と併記）                    |
| `related_issue`  | 既存 Issue へコメント追記した場合はその番号、無ければ `null`（`low_single_file` の場合は lessons の `L-{N}` を文字列で入れる） |
| `reevaluated_at` | 持ち越しを合流・再評価した日時（未再評価なら省略。ある行は「消費済み」の印）                                                   |

追記コマンド:

```bash
mkdir -p content/analytics/retro
DATE="$(TZ=Asia/Tokyo date +%Y-%m-%d) JST"
echo "{\"date\":\"${DATE}\",\"title\":\"{try.title}\",\"q1\":\"NO\",\"q2\":\"NO\",\"defer_reason\":\"medium\",\"related_issue\":null}" \
  >> content/analytics/retro/deferred_try.jsonl
git add content/analytics/retro/deferred_try.jsonl
git commit -m "docs: retro 見送り Try ログ追記（{pipeline} {entity_id}）"
git push
```

**追記が失敗した場合のフォールバック（握り潰し禁止）**: `git add` / `commit` / `push` のいずれかが失敗した場合、その Try を見送りのまま終わらせず、**その場で Step 3-C（新規 Issue 作成）にフォールバックして起票する**（quota 上限は超えてよい。記録が残らないリスクより、Issue として確実に残すことを優先する）。

#### 4. Q1 の予備検索（Step 3-A の本検索とは別・必須）

Q1 の「過去 2 回以上」は、感覚で NO と判定せず、以下の 2 系統を実際に検索して数える:

```bash
# キーワードは reference.md F 節の類似判定基準と同じ軸で抽出する
# （同じツール名・ファイル名・品質指標・ステップ名・問題パターン）
KEYWORD="{抽出したキーワード}"

# 系統1: 見送りログ（medium/over_quota/low_single_file の全履歴が対象）
grep -ci "$KEYWORD" content/analytics/retro/deferred_try.jsonl 2>/dev/null

# 系統2: lessons Warm 層の既存エントリ
grep -rli "$KEYWORD" docs/rules/lessons/ 2>/dev/null | wc -l
```

2 系統の合計ヒット件数が **2 件以上** なら Q1 = YES。0〜1 件なら NO。この 2 系統が「過去に見送られた Try」と「昇格済みの教訓」を横断してカバーするため、CRITICAL 1 で指摘された自己ロック（初回は痕跡が無いので必ず NO → 記録も残らない → 2 回目も NO）は起きない（1 回目の見送りが必ずこのログに残るため）。

#### 5. Q2 の判定（`urgency` ラベルに依存しない）

🔴 **`urgency:*` ラベルは判定材料にしない。** 実測（2026-08-24 JST・GitHub API）: open な `type:retro-try` 171 件中 `urgency:*` が付与されているのは 20 件（11.7%）のみ、`urgency:blocker` は 0 件。ラベルの有無を判定材料にすると 88% のケースで材料が無く機能しない。

> Q2（正しさ毀損）: 対応する Problem の `detail` を読み、放置すると成果物の正しさ（本番の挙動・提出物の事実性・ユーザーに見える出力）が壊れる、またはパイプラインが停止する/データを破壊する内容だと判断できるか？

`urgency:blocker` / `urgency:quality` ラベルが付いていれば補助的な参考にしてよいが、**無いことを理由に NO と即断しない**（内容だけで判定する）。

> ⚠️ **別 Issue 候補（本スプリントでは着手しない）**: Step 3-C の Issue 本文テンプレート（`reference.md` H 節）は `urgency:{try.urgency}` ラベルを必須で組み立てているが、実測カバレッジは 11.7% しかない。ラベル付与の運用自体が形骸化している可能性があり、原因調査は別 Issue に切り出す（本 PR のスコープ外・CP-1 の解決規則どおり起票のみ行う）。

### Step 3-A 以降（priority:high 相当の Try のみ・quota ゲートの位置は上記「2. 判定フロー」参照）

```
Step 3-A: 既存オープン Issue との重複チェック（type:retro-try を検索）
  ├── 類似 Issue あり → Step 3-B: 既存 Issue にコメント追記
  └── 類似 Issue なし → 起票上限ゲート → 上限内なら Step 3-C: 新規 Issue を作成
```

- **3-A** 検索コマンド・類似判定の基準 → `reference.md` の F
- **3-B** コメント追記コマンド・再発検知テンプレート（3回超で priority:high へエスカレーション）→ `reference.md` の G
- **3-C** `mcp__github__issue_write` の labels 構成（`sp:N` 写像必須）・本文テンプレート → `reference.md` の H

### Step 3 完了後の記録

全 Try アイテムの処理結果を Step 5 の完了報告に含める:

| 結果                       | 記録内容                                                                           |
| -------------------------- | ---------------------------------------------------------------------------------- |
| 新規 Issue 作成            | Issue 番号・URL                                                                    |
| 既存 Issue へコメント追記  | 既存 Issue 番号・URL・「コメント追記」の旨                                         |
| 優先度エスカレーション実施 | 対象 Issue 番号・変更前後の priority                                               |
| lessons 直記載             | 追記先ファイル・`L-{N}` 番号（見送りログにも同時記録）                             |
| Issue化見送り（medium 等） | Try タイトル一覧・見送りログへの追記済みである旨                                   |
| 上限超過で次回持ち越し     | Try タイトル一覧・見送りログの `defer_reason: "over_quota"` として記録済みである旨 |
| 前回持ち越し分の合流       | 今回合流させた Try 一覧・再評価結果（起票 / 再度持ち越し）                         |

---

## Step 4: Slack 通知

```bash
python3 "${CLAUDE_PROJECT_DIR}/tools/slack_notify.py" pipeline \
  --pipeline "レトロスペクティブ（{pipeline}）" \
  --video-id "{entity_id}" \
  --result "完了（Keep {K}件 / Problem {P}件 / Try {T}件→Issue#{N1},#{N2},...）" \
  --duration "{所要時間}"
```

> `--video-id` は `slack_notify.py` の既存引数名（レガシー）だが、値は対象エンティティ ID（`{entity_id}`）を汎用的に渡す。動画以外のワークフローでも識別子としてそのまま使ってよい。

Slack 通知に失敗しても処理を中断しない（無音でスキップ）。

---

## Step 5: 完了報告

以下のフォーマットで出力する:

```
## レトロスペクティブ完了報告

### ワークフロー
- パイプライン: {pipeline} / 対象 ID: {entity_id} / 実施日: {YYYY-MM-DD}

### KPT サマリー
#### ✅ Keep（うまくいったこと）
{役割別 Keep の一覧（箇条書き）}
#### ⚠️ Problem（問題・改善が必要なこと）
{役割別 Problem の一覧（箇条書き）}
#### 🚀 Try（改善施策）→ Issue 化済み
{Try の一覧（Issue #N リンク付き、コメント追記は「既存 Issue #N へ追記」と明記）}

### Try Issue 一覧取得
mcp__github__list_issues(owner, repo, state="OPEN", labels=["type:retro-try"])   # クラウド一次経路
（ローカル: gh issue list -R kai-kou/gem-hunter --label "type:retro-try" --state open）
```

---

## Step 6: lessons 更新チェック（肥大化防止）

新しい Problem パターンが発見された場合に **Warm 層**（`docs/rules/lessons/{カテゴリ}.md`）を更新する。**Hot 層（`docs/rules/lessons-core.md`）には原則追記しない**（全セッション横断で必須かつ作業停止級のクリティカル規範のみ・上限 350 行 / 15 件で機械強制）。詳細は `docs/rules/lessons-management.md`（SSOT）。

- **条件 A（新規パターン）**: 適切なカテゴリ（`pipeline` / `pr-review` / `content` / `session` / `agent` / `meta` 等）の Warm 層ファイルに新規 `L-{N}` エントリを追記する。判定基準は「既存と異なる（`tools/lessons_guard.py dedup` で確認）・2回以上発生・自動化で防げた問題」。採番ルール・エントリフォーマット → `reference.md` の I
- **条件 B（既存パターン再発）**: 既存エントリの「対策」末尾に再発日を追記。3回超は `type:retro-try` Issue 化 + Lv3 フック昇格を推奨 → `reference.md` の I
- **条件 C（新規・再発なし）**: スキップし、完了報告に「lessons.md 更新なし」と明記する

---

## エラーハンドリング

| エラー                        | 対応                                                                                                                                                                                                 |
| ----------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| コンテキスト情報が不足        | git log と git status から可能な範囲で推測して続行                                                                                                                                                   |
| サブエージェント失敗（1役割） | 残り2役割の結果で続行。失敗した役割を完了報告に明記                                                                                                                                                  |
| サブエージェント全失敗        | STOP。ユーザーに手動レビューを依頼                                                                                                                                                                   |
| Issue 作成失敗                | 失敗した Try のタイトルを完了報告に列挙し、手動作成を依頼                                                                                                                                            |
| `type:retro-try` ラベル未存在 | ローカル: `gh label create "type:retro-try" --color "c5def5" -R kai-kou/gem-hunter` で作成してリトライ。クラウドは 403 かつ MCP にラベル作成の等価ツールがないため、ユーザーにローカル実行を案内する |
| Slack 通知失敗                | 無音でスキップ（エラーにしない）                                                                                                                                                                     |

---

## 手動実行・呼び出し

```
/retrospective {pipeline} {ID}   # 特定パイプラインの振り返り（対象指定）
/retrospective                   # 全ワークフロー共通（最新コミットから推測）
```

各パイプライン（プロジェクト定義）からは、完了報告（最終ステップ）の **後に** 本スキルを呼び出す（`pipeline` / `entity_id` / `pr_url` / `execution_summary` を渡す）。本スキルが作成した Try Issue の対応フロー → `reference.md` の J（実際の実装は `retro-try-handler` スキルが担う）。

## 既存スキルとの関係

> レーン境界（改善 Issue / 振り返り / 監査・衛生）の SSOT は `docs/rules/improvement-lane-map.md`。
> 本スキルは **振り返りレーン** の上流（KPT 生成・Try 起票）で、`type:retro-try` の実装は下流の
> `retro-try-handler` が担う。`type:improvement` の起票・棚卸し・実装は改善 Issue レーン
> （`self-improvement-loop`）の担当で、本スキルは扱わない。

| 関連スキル                         | 関係                                                                                |
| ---------------------------------- | ----------------------------------------------------------------------------------- |
| 各パイプライン（プロジェクト定義） | 各工程の完了後に本スキルを呼び出す                                                  |
| `retro-try-handler`                | 本スキルが起票した `type:retro-try` Issue を実装・PR 化する                         |
| `self-reviewer`                    | Try に `self-review-checklist.md` 追記候補が含まれる場合、対応する Try Issue を作成 |
| `project-manager`                  | Try Issue の Projects V2 への登録が必要な場合に参照                                 |
