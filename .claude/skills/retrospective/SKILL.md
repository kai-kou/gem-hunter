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

| 状況 | 自動実行するか |
|------|-------------|
| パイプライン完了（成功） | ✅ 毎回実行 |
| サーキットブレーカー発動 | ✅ 自動実行（STOP直後） |
| 同一エラー2回目以降 | ✅ 自動実行 |
| 品質ゲート未達（プロジェクト定義の閾値） | ✅ 自動実行（ユーザー報告の前に） |
| 1回限りの軽微なエラー（リトライで解決） | ⬜ スキップ可 |

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
Step 3: Try アイテムを GitHub Issue 化（Step 3-0 WIP ゲート → 重複チェック → 追記 or 新規作成〔上限 3 件〕）
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

| 役割 | 担当範囲 |
|------|---------|
| 成果物品質レビュアー | 成果物品質・キャラ/トーン一貫性・ドメイン固有の検証精度 |
| プロセス・自動化レビュアー | ワークフロー効率・ボトルネック・自動化の有効性 |
| 技術・ツールレビュアー | ツール・スクリプト・ドキュメントの整合性 |

- 共通プロンプト構造・役割別の詳細評価観点リスト → `reference.md` の A〜D
- 各役割は KPT を JSON 形式で出力する（出力フォーマット・`urgency`/`done_type` フィールド定義 → `reference.md` の E）
- **Step 1.5**（プロジェクト定義のレビュー役スポット監査・特定パイプラインのみ）も同時に並列起動する → `reference.md` の Step 1.5。本人視点の一言は Step 5 完了報告の末尾に添えるのみで KPT 判定には影響しない

---

## Step 2: KPT 結果のマージ

3つのサブエージェントの JSON 結果を統合する。

1. **Keep / Problem の統合**: 役割別にカテゴライズして一覧化する
2. **Try の統合・重複排除**: 複数役割から同じ改善案が出たら1つにまとめ、最も高い `priority` を採用し、`detail` に両方の視点を記載する

---

## Step 3: Try アイテムを GitHub Issue 化

> 数値（起票上限 3 件・WIP 上限 30 件・reopen 窓 90 日）の SSOT は `docs/rules/retrospective-rules.md`「WIP 制御」。本 Step は参照のみで再定義しない。

### Step 3-0: WIP ゲート判定（Issue 化ループの前に 1 回だけ）

Step 3 冒頭で次の 2 リストを **各 1 回だけ** 取得し、以降の全 Try の突合に使い回す（Try 件数に関わらず API 呼び出しは定数 2 回）:

```
open_list   = mcp__github__list_issues(owner, repo, state="OPEN",   labels=["type:retro-try"])
closed_list = mcp__github__list_issues(owner, repo, state="CLOSED", labels=["type:retro-try"], since={90 日前の ISO 8601 UTC})
              → reopen 候補（`list_issues` の応答に `state_reason` は含まれないため、ここでは絞り込まず、
                 類似ヒット時にだけ `mcp__github__issue_read(method="get")` で not_planned か確認する・reference.md F）
```

- `len(open_list)` **≥ 30（WIP 上限）→ 「追記のみモード」**: 3-A / 3-B（既存オープン Issue への追記）は通常どおり実行し、**3-C（新規 Issue 作成）と 3-B'（reopen）は実行しない**（どちらもオープン件数を増やすため）。類似 Issue が無かった Try、および TTL クローズ済み Issue に類似した Try は Issue を作らず・reopen せず、完了報告の「見送り Try（WIP 上限）」に必ず記録する（後者は「再発（TTL クローズ済み #N）」と明記。次回以降のレトロで再検出されれば、その時点の在庫次第で通常処理される。記録を残す限り「次回気をつける」禁止事項の対象外）
- **`urgency:blocker` の Try は WIP ゲートの適用外**（在庫に関わらず 3-C / 3-B' を実行する。ブロッカーを在庫理由で握りつぶさない）
- `len(open_list)` < 30 → 通常モード

### Step 3-1: Try の採用と処理

#### 0. 前回持ち越し分の合流（必須・最初に実行）

見送りログ（下記「見送りログへの記録」節）を読み、`defer_reason: "over_quota"` かつ未再評価（`reevaluated_at` フィールドが無い）の行を抽出し、**今回検出した Try より優先して** 今回の処理対象の先頭に合流させる。これが無いと「次回持ち越し」は名目だけになる。

```bash
# 前回持ち越し分の抽出（未再評価のみ）
jq -c 'select(.defer_reason == "over_quota" and (.reevaluated_at == null))' \
  content/analytics/retro/deferred_try.jsonl 2>/dev/null
```

合流させた Try がこの回で再度 Step 3-1 を通過し終えたら、**元のログ行に `"reevaluated_at": "{YYYY-MM-DD HH:MM JST}"` を追記する**（read-modify-write。同一行を無限に合流させないためのマーカーで、履歴としては残す）。再度見送りになった場合は、新しい行を追記して二重管理する（古い行を上書きしない）。上記 `jq` コマンドは必ず実行し、その出力（0 件なら「0 件」）を Step 3 完了後の記録に残す。

#### 1. 処理フロー

統合済みの Try を `high` → `medium` → `low` の順に並べ、各アイテムごとに:

```
Step 3-A: 既存 Issue との重複チェック（open_list → 一致なしなら closed_list〔not_planned・90 日〕）
  ├── open に類似あり   → Step 3-B: 既存 Issue にコメント追記（再発検知）
  ├── closed に類似あり → Step 3-B': reopen + 再発コメント（reference.md F の手順）
  └── 類似なし          → Step 3-C: 新規 Issue を作成（下記の起票上限内のみ）
                              └─ 上限到達 / WIP 上限（追記のみモード）→ 見送りログへ記録（下記）
```

**起票上限**: 3-C（新規作成）と 3-B'（reopen）を合わせて **1 回のレトロにつき最大 3 件**（どちらもオープン在庫を 1 件増やすため同じ枠で数える。`urgency:blocker` は上限にカウントしない）。上限に達した後の Try、および WIP 上限（追記のみモード）で 3-C / 3-B' を実行できなかった Try は、完了報告の「見送り Try」に記録するだけでなく、下記「見送りログへの記録」へ **必ず** 進む。3-B（既存オープン Issue への追記）はオープン件数を増やさないため上限にカウントしない。

- **3-A** 検索コマンド・類似判定の基準・reopen 手順 → `reference.md` の F
- **3-B** コメント追記コマンド・再発検知テンプレート（3回超で priority:high へエスカレーション）→ `reference.md` の G
- **3-C** `mcp__github__issue_write` の labels 構成（`sp:N` 写像必須）・本文テンプレート → `reference.md` の H

#### 2. 見送りログへの記録（`content/analytics/retro/deferred_try.jsonl`・Issue #417・必須）

🔴 **上記フローで「見送り」となった全ケースは、この追記を完了して初めてそのアイテムの Step 3 処理が完了したとみなす**（省略可能な後始末ではない）。数値の SSOT（起票上限・WIP 上限）は `docs/rules/retrospective-rules.md`「WIP 制御」であり、本節は **その見送り結果をどう記録するか** だけを扱う。

配置・フォーマットは既存の `content/analytics/sprint/*.jsonl` に倣い、**追記専用の JSONL・1 行 1 レコード** とする。フィールド・値域は `tools/check_deferred_try_jsonl.py` が機械検査する正本（`npm run check` に配線済み）だが、記録前に埋める値は以下のとおり:

| フィールド | 内容 |
|-----------|------|
| `date` | 見送り判定日（JST・`YYYY-MM-DD JST`） |
| `title` | `try.title` |
| `q1` | 再発判定（`"YES"`/`"NO"`）: 同種の Problem が過去に 2 回以上検出されているか。下記「3. Q1 の予備検索」の実行結果（見送りログ + `docs/rules/lessons/`） |
| `q2` | 重要度判定（`"YES"`/`"NO"`）: `try.priority == "high"` か（放置すると成果物の正しさ・パイプライン継続に影響する Try として統合済みの Try に既に反映されている優先度をそのまま使う） |
| `defer_reason` | `q1`/`q2` のいずれかが `"YES"`（priority:high 相当）なら `"over_quota"`（起票上限到達）または `"high_commented"`（3-B で追記して完了）。両方 `"NO"` なら `"medium"`（起票せず見送り）または `"medium_commented"`（3-B で追記して完了） |
| `related_issue` | 3-B / 3-B' で既存 Issue に追記した場合はその番号、それ以外は `null`。🔴 `defer_reason` が `high_commented` / `medium_commented` のときは **必須**（`null` 不可） |
| `reevaluated_at` | 持ち越しを合流・再評価した日時（未再評価なら省略） |

追記コマンド:

```bash
mkdir -p content/analytics/retro
DATE="$(TZ=Asia/Tokyo date +%Y-%m-%d) JST"
echo "{\"date\":\"${DATE}\",\"title\":\"{try.title}\",\"q1\":\"NO\",\"q2\":\"NO\",\"defer_reason\":\"medium\",\"related_issue\":null}" \
  >> content/analytics/retro/deferred_try.jsonl

# 🔴 追記したら必ず整形性を機械検査してからコミットする（exit 0 を確認する）
python3 tools/check_deferred_try_jsonl.py

git add content/analytics/retro/deferred_try.jsonl
git commit -m "docs: retro 見送り Try ログ追記（{pipeline} {entity_id}）"
git push
```

🔴 **`python3 tools/check_deferred_try_jsonl.py` が非 0 を返したらコミットしない。** シェルで組み立てた JSON は `{try.title}` に `"` や `\` が含まれると壊れるため、非 0 のときは追記した行を修正し、再実行して exit 0 になってから `git add` へ進む。**`git add` / `commit` / `push` のいずれかが失敗した場合**（握り潰し禁止）: その Try を見送りのまま終わらせず、その場で Step 3-C（新規 Issue 作成）にフォールバックして起票する（起票上限は超えてよい。記録が残らないリスクより、Issue として確実に残すことを優先する）。

#### 3. Q1 の予備検索（Step 3-A の重複チェックとは別・必須）

Q1 の「過去 2 回以上」は、感覚で NO と判定せず、以下の 2 系統を実際に検索して数える:

```bash
# キーワードは reference.md F 節の類似判定基準と同じ軸で抽出する
KEYWORD="{抽出したキーワード}"

# 系統1: 見送りログ（全履歴が対象）
grep -ci "$KEYWORD" content/analytics/retro/deferred_try.jsonl 2>/dev/null

# 系統2: lessons Warm 層の既存エントリ
grep -rli "$KEYWORD" docs/rules/lessons/ 2>/dev/null | wc -l
```

2 系統の合計ヒット件数が **2 件以上** なら Q1 = YES。0〜1 件なら NO。1 回目の見送りが必ずこのログに残るため、「初回は痕跡が無いので必ず NO → 記録も残らない → 2 回目も NO」という自己ロックは起きない。

### Step 3 完了後の記録

全 Try アイテムの処理結果を Step 5 の完了報告に含める:

| 結果 | 記録内容 |
|------|---------|
| 新規 Issue 作成 | Issue 番号・URL |
| 既存 Issue へコメント追記 | 既存 Issue 番号・URL・「コメント追記」の旨 |
| TTL クローズ済み Issue の reopen | Issue 番号・URL・「再発により reopen」の旨 |
| 優先度エスカレーション実施 | 対象 Issue 番号・変更前後の priority |
| 見送り Try | Try のタイトル・理由（起票上限 / WIP 上限）・見送りログへ追記済みである旨。**Issue 化しない代わりに必ず記録する** |
| 前回持ち越し分の合流 | 今回合流させた Try 一覧・再評価結果（起票 / 再度持ち越し）に加え、実行した `jq` コマンドの出力（0 件だった場合も「0 件」と明記） |

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
{Try の一覧（Issue #N リンク付き、コメント追記は「既存 Issue #N へ追記」、reopen は「#N を再発により reopen」と明記）}
#### ⏸️ 見送り Try（起票上限 / WIP 上限・Issue 化せず記録のみ）
{見送った Try のタイトルと理由。ゼロなら「なし」。WIP 上限中はオープン件数（N 件 / 上限 30 件）も併記}

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

| エラー | 対応 |
|--------|------|
| コンテキスト情報が不足 | git log と git status から可能な範囲で推測して続行 |
| サブエージェント失敗（1役割） | 残り2役割の結果で続行。失敗した役割を完了報告に明記 |
| サブエージェント全失敗 | STOP。ユーザーに手動レビューを依頼 |
| Issue 作成失敗 | 失敗した Try のタイトルを完了報告に列挙し、手動作成を依頼 |
| `type:retro-try` ラベル未存在 | ローカル: `gh label create "type:retro-try" --color "c5def5" -R kai-kou/gem-hunter` で作成してリトライ。クラウドは 403 かつ MCP にラベル作成の等価ツールがないため、ユーザーにローカル実行を案内する |
| Slack 通知失敗 | 無音でスキップ（エラーにしない） |

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

| 関連スキル | 関係 |
|-----------|------|
| 各パイプライン（プロジェクト定義） | 各工程の完了後に本スキルを呼び出す |
| `retro-try-handler` | 本スキルが起票した `type:retro-try` Issue を実装・PR 化する |
| `self-reviewer` | Try に `self-review-checklist.md` 追記候補が含まれる場合、対応する Try Issue を作成 |
| `project-manager` | Try Issue の Projects V2 への登録が必要な場合に参照 |
