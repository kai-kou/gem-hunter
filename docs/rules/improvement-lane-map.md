# 改善・監査レーンマップ（責務境界 SSOT）

> **このファイルは「改善 Issue の世話・振り返り・監査/衛生」を担う各スキルの責務境界の唯一の正本（SSOT）である。**
> 各 SKILL.md は本ファイルを **参照** し、自分の中で境界表を再定義しない（相互弁明の再発防止・Issue #147）。
> Warm 層（`docs/rules/` のみ・`.claude/rules/` へ symlink しない）。境界に迷ったときだけ Read する。

## 1. 3 レーン構成

| レーン | スキル | 担当フェーズ | 主な起動 |
|--------|--------|------------|---------|
| **改善 Issue レーン** | `self-improvement-loop`（発見 / 整理 / 消化の 3 モード） | 横断レビューでの課題発見・起票 → 棚卸し（集計・重複統合・Epic 化・priority/sp 補完）→ **リファインメント**（後回しにされた低優先・滞留 Issue を 4 出口へ遷移。この工程のみ **`type:retro-try` を含む全 type 対象**・#153（実装は振り返りレーンの専管のまま・§2 ルール 2））→ 実装・マージ | 発見スロット / 消化スロット / R-1 ルーティン（リファインメントは手順 9-3 の週次ゲート）/ 「セルフ改善して」「改善バックログを棚卸しして」「リファインメントして」「改善Issue消化して」 |
| **振り返りレーン** | `retrospective` → `retro-try-handler` | ワークフロー完了・失敗時の KPT 生成と Try 起票 → Try Issue の実装・PR 化 | KPT 生成（`retrospective`）は `pr-review-watcher` 内の最終ステップ（マージ + 公開反映の直後・`Sprint Goal:` 付き PR のみ）/ Try の実装（`retro-try-handler`）は `sprint-cycle-router` の決定木 **Step 5.5**（エージング 8 時間・#377）/ 「レトロスペクティブして」 |
| **監査・衛生レーン** | `workflow-health-check`（監査ロジック本体）→ `project-sync`（衛生実行・軽量版の呼び出し側） | PR 健全性・Issue 状態の監査、Stale / Orphan / ラベル不整合の解消 | 週次ゲート（定期ルーティンに組み込む）/ 日次の衛生スロット / 「ヘルスチェックして」「project-sync して」 |

`project-manager`（Issue / Milestone の個別 CRUD）・`waiting-user-handler`（`status:waiting-user` のトリアージ）・
`skill-audit`（Agent Skills 資産の構造監査）・`audit-runner`（外部監査プロトコルによるセットアップ構成監査）は
上記 3 レーンのいずれにも属さない **単発オペレーション** で、本マップの対象外。

> **振り返りレーンの起動元は `pr-review-watcher`（`SP-n` スコープ）に加え、`self-improvement-loop`
> （消化モード・整理モード）/ `workflow-health-check`（週次レポート後の Step 4-e）/
> `retro-try-handler`（Try 実装 PR のマージ後）の各完了エンドポイントにも実装済み**（Issue #68）。
> いずれも「commit + PR + マージまで完了した場合のみ」`retrospective` を起動し、変更なしのサイクルでは
> 起動しない。
>
> ⚠️ **混同注意**: 上記は上流の `retrospective`（KPT 生成）の呼び出し元の話であって、
> 下流の `retro-try-handler`（Try の実装）の起動経路ではない。後者は #377 で
> `sprint-cycle-router` の決定木 **Step 5.5** として実装済み（両者は振り返りレーンの中の別スキル）。

### 1.1. 第 4 レーン（スプリント開発レーン）

| レーン | スキル | 担当フェーズ | 主な起動 |
|--------|--------|------------|---------|
| **スプリント開発レーン** | `sprint-cycle-router`（決定木 Step 3.5 / Step 4） | SP → Issue 同期（Step 3.5）→ Issue 選定・実装（TDD）・PR・Layer 1 セルフレビュー・マージ（Step 4） | 単一ルーティン（cron 式の正本は `docs/routines/sprint-cycle-routine.md`・可変）の決定木。ただし Step 1〜3 が埋まっていると Step 4 に到達しないため、飢餓防止のエージング（Ready な `SP-n` があるのに直近 3 日 Step 4 未実行なら差し込む）がある | <!-- lanecheck:natural-trigger-only -->

**対象**: `type:feature` の `SP-n`（プロダクト機能開発）のみ。`type:improvement` / `type:retro-try` / 衛生対象は既存 3 レーンの担当のまま（本レーンは奪わない）。

**既存 3 レーンとの責務境界（1 行ずつ）**:
- vs 改善 Issue レーン: あちらは `SP-n` 規約を持たない単発課題（`type` は問わない）、こちらは `SP-n` 規約を持つスプリント実装。在庫枯渇（`M-3` 到達）時のみ主従を改善 Issue レーンへ切り替える
- vs 振り返りレーン: あちらは `type:retro-try`（振り返り由来の Try）の実装、こちらはプロダクト機能開発。対象 type が排他
- vs 監査・衛生レーン: あちらは Issue/PR の **状態**（Stale・Orphan・ラベル不整合）の是正、こちらは新規価値を作る実装そのもの

**レーン間の受け渡し**: 未完のスプリントは `status:in-progress` + 作業ブランチのまま次の firing へ引き継ぐ（新規 state ファイルを作らない・GitHub 上の既存アーティファクトから再計算）。在庫枯渇（`[Milestone] M-3 到達` Issue 起票済み）を検知したら、以後は改善 Issue レーンの消化モードへ主従を切り替える（ルーティン自体は止めない）。

> **監査系 3 スキルの棲み分け**（混同しやすいので明記）: 対象が **Issue / PR の状態** なら
> `workflow-health-check`（監査・衛生レーン）、**Agent Skills 資産の構造** なら `skill-audit`、
> **セットアップ構成を外部プロトコルで測る** なら `audit-runner`。`audit-runner` が発見した改善は
> Issue 化して改善 Issue レーンへ受け渡す（ラベル経由・§3）。

## 2. 一意判定ルール（迷ったときはこの順で決める）

1. 対象が **実装・修正で片が付く単一の課題**（横断的な改善・不具合・ドキュメント作業など）→ **改善 Issue レーン**。
   `type:improvement` / `type:bug` が典型だが **`type` では絞らない**（`type:docs` や `SP-n` 規約を持たない
   `type:feature` を落とすと、どのレーンも拾わない孤児 Issue が生まれる。ルール 5 が `type` 非依存なのと同じ理由・CP-3）。
   除外するのは次の 2 つだけ: `type:retro-try`（ルール 2）と `SP-n` タイトル規約を持つ Issue（スプリント開発レーン）
2. 対象が `type:retro-try`（振り返り由来の Try）の **実装** → **振り返りレーン**（改善 Issue レーンの **消化モード** は扱わない・#160）。ただし **棚卸し**（重複統合・Epic 化・優先度再査定）は改善 Issue レーンの **整理モード**（Step G-1.5 / G-6）がルール 5 のとおり type 非依存で扱う（#153・消化モードのみ専管に改訂。#160 の「奪い合い防止」は実装の主体を固定する趣旨であり、棚卸しの主体まで固定するものではなかった）。なお Step G-1 の集計ツール `tools/triage_improvements.py` は取得層で `type:retro-try` を **機械的に除外済み**（#418・`type:improvement` との二重ラベルによる混入を防ぐ）。🔴 **この除外は Step G-1（`type:improvement` の集計）に限った射程の例外条項であり、本ルールの棚卸し条項を打ち消さない**: リファインメント（Step G-1.5 / G-6）は **本ツールを使わず** `mcp__github__list_issues` の別クエリで全オープン Issue を取得するため（`.claude/skills/self-improvement-loop/SKILL.md` Step G-1.5）、`type:retro-try` は従来どおりルール 5 の対象に含まれる。二重ラベル Issue を Step G-1 のレポートに載せたい場合は `--label type:retro-try` を明示指定する（明示指定時は除外されない）
3. 対象が Issue / PR / ブランチの **状態**（ラベル不整合・滞留・孤児・Stale ロック）→ **監査・衛生レーン**
4. 対象が「溜まった改善 Issue の山そのもの」（分類・重複統合・Epic 境界の判断）→ 改善 Issue レーンの **整理モード**
5. 対象が「**その Issue に取り組む価値があるか / 他と束ねられるか**」の精査（後回しにされた低優先・滞留 Issue）→ 改善 Issue レーンの **整理モード・リファインメント**（Step G-1.5 / G-6）。**`type:retro-try` を含む全 type が対象**（`type:feature` / `type:docs` / `type:retro-try` / type 欠落を取りこぼすと #335 と同型のオーファン化が起きるため。`type:retro-try` の対象化は #153 でルール 2 と揃えた）。監査・衛生レーンと対象 Issue が重なっても、あちらは「ラベル不整合・滞留という **状態**」、こちらは「取り組む価値という **内容の判断**」を見るので判定軸は排他

「実装して直すもの」は改善 Issue レーン、「ラベル・状態を整えるもの」は監査・衛生レーンと覚える。

> **ルール 2 とルール 5 の関係（将来の変更者へ・#153）**: ルール 2 の「振り返りレーンの専管」は
> #160 でレーン間の **実装の奪い合い** を防ぐために決着した条項であり、`type:retro-try` の **消化モード**
> （実装 → PR → マージ）にのみ及ぶ。棚卸し（重複統合・Epic 化・優先度再査定）はそもそも #160 が
> 想定した奪い合いの対象ではなかったため、ルール 5（整理モード・リファインメント）は `type:retro-try` を
> 除外しない。`type:retro-try` の **消化フロー自体**（`self-improvement-loop` の消化モード・§1 の
> 3 レーン表）を改善 Issue レーンへ拾わせることは今後も禁止（#160 の決定は維持）。

## 3. レーン間の受け渡し

- 受け渡しは原則 **GitHub Issue のラベル**（`type:` / `status:` / `priority:` / `sp:`）で行う。スキル間の暗黙の期待を SKILL.md の文章だけで宣言しない。
- 例外的に許可するスキル直接呼び出しは **1 本のみ**: 改善 Issue レーンの発見モードが、監査・衛生レーンの `workflow-health-check`（軽量版）を呼び出して監査結果を入力として受け取る（重複監査の回避）。
- `priority:` / `sp:` の決定は `@owner`（PO ロール）に委ねる（`docs/rules/session-sprint-rules.md` §4）。`status:` の操作はメインアシスタントが行う。

## 4. 禁止パターン

```
❌ SKILL.md 内にレーン境界表を再掲・再定義する（本ファイルを参照する）
❌ 「〇〇スキルから呼び出す」と SKILL.md に書きながら実行フローに該当ステップが無い（宣言だけの連携）
❌ レーンをまたぐ暗黙の状態共有（ローカルファイル・セッション内変数）に依存する
✅ 境界の変更は本ファイルを先に更新し、各 SKILL.md は参照 1 行に留める
```

## 5. なぜ 6 スキルを 1 つに統合しないのか

設計判断の記録（Issue #147）は開発リポジトリの提案記録として保持している。要点は
「改善 Issue の世話（起票 → 整理 → 実装）は 1 スキルに統合する。振り返り・監査/衛生は
frontmatter（`model` / `effort`）と自動起動点が異なるため統合しない」。

## 6. 参照

| ドキュメント | 関係 |
|------------|------|
| `docs/rules/session-sprint-rules.md` | SP・priority の基準、@owner（PO）の権限境界 |
| `docs/rules/user-confirmation-minimization.md` | A-1〜A-6 既約境界外（自律実行の範囲） |
| `docs/rules/core-principles.md` | CP-3（リポジトリ衛生）・CP-6（ユーザー介入最小化） |
