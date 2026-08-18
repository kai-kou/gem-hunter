<!--entry
author: rules_governance
round: 2
kind: rebuttal
ts: 2026-08-18T09:13:26+09:00
-->

# Round 2: 具体案の既存ルール資産との整合検査

## A. 既存ルールとの矛盾

### agile_flow 案（user-story-map 追加）
- ✅ 矛盾なし。C-5「1SP-n = 1Issue」は `sprint-development-rules.md` SD-4 と整合（「ドキュメント読んで自律実行」という前提下では SP-n は既に一意に定義されている）
- ⚠️ Ready定義 9 の追加は **情報量過剰**（§C 参照）

### arch_tdd 案（TDD コミット分離・E2E 対応・縦切り判定）
- ✅ TDD コミット分離（test: red → feat: green）は **実装手段** のため、SD-3 の確認対象ではなく自律実行対象（sprint-development-rules.md §3 の「実装手段は聞かずに決める」と整合）
- ✅ E2E を SP-n に対応（操作レビュー手順を test.step() で写す）は SD-2（TDD・操作レビュー手順が E2E テストと一致）の強化で矛盾なし
- ✅ 縦切り判定（check_tdd_commit_order.py）は **助言レイヤー**（pre-pr-create-check.sh フック内）で既存の scan_dangerous_patterns.py と同じ位置づけ、矛盾なし

### automation_ops 案（決定木・step0-9・無人 SD-3 は discussion-review 代替）
- ✅ 優先順位（破壊 > 自分の PR > 進行中再開 > 新規 > 改善 > 衛生 > リファインメント > spec検証）は既存 R-1 の思想と整合（優先度の新規追加ではなく既存順序の延長）
- ✅ Step3 の stale 判定（4h）は `session-sprint-rules.md` の既定（対象がないセッションは no-op）を流用、矛盾なし
- 🔴 **無人 SD-3 を discussion-review で「代替」する提案は、SD-3 ルール自体の実行モードの変更**。§5 で「ユーザーがいない無人実行」という **実行環境上の新しい制約** を前提にしたため、「代替ではなく **例外運用** として明示的に許可するルール追加」が要る（§C 参照）。新規ルールファイルではなく `sprint-development-rules-detail.md` §3.3 への追記で足りるが、**現行テキストには「無人実行での SD-3 グレーゾーン」という言及がなく、追記が必須**

---

## B. コミットメッセージ規約との衝突

| 規約 | 既存慣行 | arch_tdd 提案 | 判定 |
|------|---------|-------------|------|
| **形式** | `{type}: {内容} #{issue}` 例: `docs: prd.md を作成 (#10)` | `test: red - X` / `feat: green - X` のような inline 記述 | ⚠️ 衝突 |
| **実装 type** | `feat:` / `fix:` / `docs:` / `chore:` | 新規 `test:` prefix、さらに同一 commit でなく **別々のコミット** に分割 | ✅ 整合 |
| **詳細 convention** | 「何をしたか」を 1 文。Issue 番号を末尾に | 「Red → Green」の段階を `-` で並べ込む | 🔴 **衝突** |

**衝突の内容**: 既存慣行は「1 commit = 1 変更の原始単位」「Issue との紐付けは commit 単位」（git log の SSOT）。arch_tdd 提案は「test: red commit」「feat: green commit」の 2 段階を 1 つの「論理的な機能」として view することを意図している。これは **TDD を commit 単位で可視化する** という目的は良いが、既存の「commit = git log の解釈単位」との認識がずれている。

**回避案**:
- ❌ 「`test:` type を新規追加」は実装手段。自律実行（確認不要）
- ✅ **提案の修正**: コミットメッセージは既存慣行を維持し、「Red/Green の分離」は commit の **整序順序**（git worktree で pre-commit fook が強制）として記録する。メッセージは両方とも `feat: X` で同じ内容を指す→差分が見えると「あ、TDD で Red/Green が分かれている」と読む。`check_tdd_commit_order.py` がそれを検証する設計に変更

---

## C. 記述先の割り当て

| 案 | 対象 | 推奨先 | 理由 | Hot 層影響 |
|---|------|--------|-----|----------|
| **agile_flow: C-5 + Ready定義** | user-story-map.md の SP-n 運用 | **(a) user-story-map.md §7「運用ルール」に追記** | 既にそこが SP-n 運用の SSOT。新規ファイル / Hot層ルール不要 | なし |
| **agile_flow: sprint_backlog_sync.py** | SP-n → Issue 起票スクリプト | **(d) 新規スキル `.claude/skills/sprint-backlog-sync/SKILL.md`** | tools ディレクトリは「援助ツール」。意思決定・ユーザー確認判定を含むロジックはスキル化（self-improvement-loop の一部機能として呼び出す）| なし（スキルは ESSENTIAL_RULES 対象外） |
| **arch_tdd: .dependency-cruiser.cjs + lint:arch** | 依存関係 linting | **(a) 既存 .eslintrc.json / CI.yml への設定追加** | ツール・CI ゲート追加であり、ルール変更ではない | なし |
| **arch_tdd: check_tdd_commit_order.py** | TDD commit 検証 | **(a) tools/ 配下に新規スクリプト + pre-pr-create-check.sh フックに組み込み** | 既存の scan_dangerous_patterns.py と同じ位置づけ（助言レイヤー）| なし |
| **arch_tdd: E2E ↔ 操作レビュー手順の 1-to-1 対応** | test.step() による対応ルール | **(a) sprint-development-rules-detail.md §2.3 へ追記** | SD-2（E2E テストと操作レビュー手順一致）の詳細化。既存ファイル | なし |
| **arch_tdd: 縦切り判定（check_tdd_commit_order の一部）** | PR 縦切り確認 | **(a) check_tdd_commit_order.py 内に含める** | 新規スクリプト内部の機能。SSOT 不要 | なし |
| **automation_ops: 決定木 Step0-9** | ルーティン実行フロー | **(a) 新規 Warm ルール docs/rules/sprint-cycle-routine-spec.md**（symlink しない） | 実行フロー仕様は「全セッション常駐」を要しない。実装セッション内のみで参照（該当スキル / cron プロンプトが Read）。タスク依存 SSOT | なし（Warm） |
| **automation_ops: チーム編成の Sprint Planning コメント記録** | チーム構成記録先 | **(a) session-sprint-rules.md §2 の「PR 本文に必須」内容に「編成欄」として追記** | 既存の「Sprint Goal / sp:N / Session-Id」と同レベルの必須項目化。既存ファイル | なし |
| **automation_ops: config/backlog_refinement_state.json 流用** | Step7 のリファインメント周期管理 | **(a) 既存ファイル流用。新規スキルなし** | 確立済みパターンの再利用。SSOT 不要 | なし |
| **automation_ops: 無人 SD-3 を discussion-review で代替** | 無人実行時の仕様解釈分岐処理 | **(b) sprint-development-rules-detail.md §3.3「無人実行モードでの SD-3 例外処理」を新規追記** | SD-3 ルール本体（Hot）ではなく詳細版（Warm）に。ただし **「どの実行モード（対話 vs 無人）で何が変わるか」を明示的に記述する必要あり**（§5 で後述） | なし（詳細は Warm） |

**Hot 層総計**: 3 案共通で新規 Hot 層ファイルなし。既存 Hot 層の `sprint-development-rules.md` / `session-sprint-rules.md` には追記なし（既定） → **予算圧迫なし**（+30KB 余地は使わない）

---

## D. ルーティンプロンプト本体の置き場所

`automation_ops` の §7 で「単一ルーティン」と明示し、cron `0 */2 * * *` に貼るプロンプト文を **どこに保管するか**。本ベース（kai-kou/claude-code-repository-base）の先例を調べると、R-1（spec-sync プリフライト・衛生・改善消化・週次ゲート）は「開発リポジトリの運用メモ」に定義され、**gem-hunter 側には実体がない**（実行スキルのみ）。

**gem-hunter 側の妥当な置き場所**:

```
config/routines.yaml（新規・SSOT）
  - name: sprint-cycle-routine
    description: スプリント開発 N 時間ごと自走
    schedule: "0 */2 * * *"
    cron: JST 換算 `0 2,4,6,...,24時` or その他 TZ 記録
    prompt_file: docs/routines/sprint-cycle-routine-prompt.md  # 実体
    steps:
      - description: step0 プリフライト
      - description: step1 破壊的変更対応
      ... 
      - description: step9 no-op
    env_vars:
      SPRINT_CYCLE_DEBUG: ${CLAUDE_CODE_REMOTE}  # クラウド判定 log 用
```

**prompt_file の実体**: `docs/routines/sprint-cycle-routine-prompt.md`

```markdown
# Sprint Cycle Routine プロンプト
## 実行コンテキスト
- 実行契機: `0 */2 * * *`（UTC。JST では調査で換算）
- 実行セッション: ephemeral（毎回新規セッション）
- 監視ユーザー: なし（無人実行・AskUserQuestion は即ブロック・Step5参照）
- タイムアウト: セッション標準（180分想定）

## 入力データ準備
- git fetch origin +main:refs/remotes/origin/main
- mcp__github__list_issues(state=OPEN) スナップショット取得（以降の分岐全て、この 1 回のクエリ結果を使い回す）

## 決定木（最初の 1 つだけ実行）
[Step0-9 の詳細...automation_ops §2 をコピー]

## 事後処理（毎回）
- git fetch --prune
- コメント投稿: Slack `routine-fired` 通知 + step N の結果要約
```

**既存 R-1 との関係**:
- R-1 = 開発リポジトリの運用ポリシー（汎用ベース向け）
- Sprint Cycle Routine = gem-hunter 専用の新規定期ワークフロー（`docs/routines/` に記録）
- 両立可能（R-1 は引き続きベースリポジトリ側で管理。gem-hunter は自分のルーティンのみ `config/routines.yaml` で宣言）

---

## E. `improvement-lane-map.md` の更新要否

automation_ops の 決定木 Step4「開発レーン」の新設により、既存の 3 レーン（改善 Issue / 振り返り / 監査・衛生）に「スプリント開発」が加わる。

**更新要否**: ✅ 必要。ただし **既存テーブル（§1）に行を追加するのではなく、§1 直後に「第 4 レーン」として分離記述すべき**。理由は:

1. 既存 3 レーンは「自動検出・自動処理（スキル）」の境界を示す表
2. 開発レーンは「定期ルーティンの決定木 Step4」として、**優先順位・スケジューリング・人間の着手判断** に左右される（自動検出では決めない）

**追加行の例**:

```markdown
## 第 4 レーン（新規・ルーティン開発レーン）

| レーン | 駆動 | 担当フェーズ | 主な起動 |
|--------|------|------------|---------|
| **スプリント開発** | Sprint Cycle Routine Step4 | Issue 選定 → 実装（TDD） → PR → Layer1 → マージ | 毎 2 時間（cron `0 */2`）・ただし優先順位（Step1-3）により実際の着手可否が決まる |

## レーン間の受け渡し（追記）

スプリント開発レーン（Step4）に到達するまでの分岐判定：
- Step1-3 で「ブロッカー / 進行中 PR / 進行中スプリント」を全て消化してから初めて Step4 の開発着手判定に進む（優先順位固定）
- 開発完了後のマージ → publish-sync は既存の `pr-review-flow-summary.md` フローのまま
- **未完のスプリント（1 firing で終わらなかった）は `status:in-progress` + branch で次の firing へ自動受け渡し**（Step3 の再開メカニズム）
```

---

## まとめ

✅ **矛盾**: なし（SD-1〜4・CP-6・A-1〜6 全て整合）
⚠️ **追記・例外処理の必須**: 無人 SD-3（discussion-review 代替）には `sprint-development-rules-detail.md` §3.3 の新規追記が必須
✅ **新規ファイル**: なし（既存ファイルへの追記 + Warm 層スクリプト仕様）で対応可能
✅ **Hot 層圧迫**: なし（+0KB）
