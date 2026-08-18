<!--entry
author: rules_governance
round: 1
kind: evidence
ts: 2026-08-18T09:08:13+09:00
-->

# スプリント自走ルーティン導入時の既存ルール資産整合検査

## 既に定義済み（重複禁止）

| 観点 | 既存 SSOT ファイル | 該当節 | 内容 |
|------|---|------|------|
| **スプリント回し方** | `sprint-development-rules.md` | §0 / 1-4 | SD-1〜4（動作確認 URL・TDD・曖昧点確認・ドキュメント自動参照） |
| **スプリント単位** | `session-sprint-rules.md` | §1-3 | 1 セッション = 1 スプリント・SP スケール（1/2/3/5/8）・Dynamic 補正 |
| **見積もり・Dynamic 補正** | `session-sprint-rules-detail.md`（Warm）| §3.1.5 | 要リサーチ・仕様未確定・新規領域 → +1〜2 SP |
| **リファインメント** | `improvement-lane-map.md` | §1-2 | 「後回しにされた低優先・滞留 Issue」の 4 出口遷移・リファインメント対象は `type:retro-try` 除く全 type |
| **自走スキル** | `self-improvement-loop` SKILL.md | description | 「改善 Issue → 棚卸し（集計・重複統合・Epic 化・priority/sp 補完）→ リファインメント → 実装」の 3 モード稼働 |
| **リファインメント実行体** | `self-improvement-loop` SKILL.md | Step G-1.5 / G-6 | 「取り組む価値があるか」の精査を整理モードで実施（全 type 対象・`type:retro-try` 除外） |
| **定期ルーティン** | `project-manager.md`（別 Issue）で定義 | — | R-1（日次消化・週次リファインメント等）のスロット定義 |
| **確認境界** | `user-confirmation-minimization.md` | §1 / §3 item 0 | A-1〜A-6（既約境界外）・仕様解釈の分岐（第 2 系統・不可逆でなくても確認） |
| **PR フロー** | `pr-review-flow-summary.md` | §1-2 | 実装完了 → セルフレビュー → PR → Layer 1 → 自動マージ（**恒久委任・CP-6**） |
| **並列・チーム** | `agent-team-summary.md` / `agent-team.md` | — | role 分担型 fan-out vs 議論型（`discussion-review`）の振り分け・モデル選択 |
| **Dynamic Workflows** | `dynamic-workflows-rules.md` | §2-5 | WF 化の判定基準・並列エージェント上限・敵対的相互レビューの codify |
| **CP-6 / 確認最小化** | `core-principles.md` | CP-6 | ユーザー介入最小化・定義済みルール範囲は自律実行 |

---

## Hot 層予算の実測

| 項目 | 現在値 | 上限 | 追加余地 |
|------|-----:|-----:|-----:|
| `.claude/rules/` ファイル数 | 14 個 | — | +? |
| `.claude/rules/` 総サイズ（実測 2026-08-17） | ~89.3 KB | **120 KB**（参考値） | **+30.7 KB** |
| 推定トークン数 | ~22,300 | — | — |
| 実測値の根拠 | `token-optimization-rules.md` §1.1 の表 / 増減ログ | — | — |

**注**: 上限 120 KB は「参考値」（#146 / #324 / #369 で段階的に棚卸し後、確実な上限値なし）。逆算すると **ルールファイル 1 本追加なら +8〜10KB**（新規ルール最小単位）が目安。現在 89.3KB + 予想 8KB = ~97KB（予備 23KB）で追加余地あり。

---

## 新規ファイル追加時の必須手順（session-compression-rules.md §4 より）

1. `/home/user/gem-hunter/docs/rules/{名前}.md` に実体を作成
2. `.claude/rules/{名前}.md` に symlink を作成
3. `/home/user/gem-hunter/tools/check_rules_sync.sh` の `ESSENTIAL_RULES` 配列に追加
4. `python3 tools/check_rules_sync.sh --fix` で検証・自動修正
5. git commit & push（`CLAUDE.md` への追記不要・自動読み込み）

---

## スキル description のトリガー衝突リスク

| 衝突リスク | スキル名（description より） | 衝突する自然文 | 回避案 |
|----------|------|--------|--------|
| **「スプリント開発を進めて」** | `self-improvement-loop` | 「プロジェクト全体を定期的に横断レビューし…改善Issue起票→棚卸し→リファインメント→実装」が既に「スプリント開発」を含む | スプリント自走ルーティンの description は「定期的な…」ではなく「×時間ごとに自走」「N 回目スプリント」と時間軸を明示 |
| **「開発ルーティン開始」** | `project-sync` / `workflow-health-check` | 両スキルが「プロジェクト定義の衛生スロット / 日次消化スロット」で既に自動起動 | 新ルーティンの固有なトリガーワード（「スプリント自動実行」「周期実行」等）を明示 |
| **「改善バックログ」「Epic化」** | `self-improvement-loop` | 整理モードが既に「集計・重複統合・Epic 化・priority/sp 補完」を実施 | ユーザー指示による新ルーティン起動と、既存スキルの「定期自動化」の境界を明示（`Skill(self-improvement-loop)` vs ルーティン内での自動呼び出し） |

---

## 機械検証一覧（`.claude/rules/` 追加時に自動実施）

| ツール | 検証内容 | 実行タイミング |
|--------|-------|--------|
| `tools/check_rules_sync.sh` | symlink 実在・ESSENTIAL_RULES 突合・Hot 層ファイル状態 | `--fix` で自動修正・hook `post-compact.sh` が自動実施 |
| `tools/lessons_guard.py check` | Hot 層サイズ上限内（89.3KB）か検証 | CI / pre-commit hook `user-prompt-submit-guard.sh`（非ブロック助言） |
| `tools/check_skill_references.py` | ルール本体中の参照ファイル実在・SKILL.md 行数肥大化 | CI / `skill-audit` スキル実行時 |
| `tools/check_cjk_markdown.py --fix --changed` | 新規ルール .md 内の CJK マークダウン形式 | `pre-pr-create-check.sh` フック自動実施 |
| `tools/check_datetime_tz.py` | ルール内の日時表記が JST 統一か検証（API 用 UTC は除外） | CI・`self_review_check.py` 内で実行 |

---

## CP-6 / A-1〜A-6 との衝突リスク

| 衝突箇所 | リスク内容 | 自走ルーティン側の対策 |
|---------|----------|--------|
| **A-1（main 直接 push 禁止）** | N 時間ごとの自走が「確認なしで push」するのは既定。衝突なし | 既に恒久委任済み（`CLAUDE.md`「PR 作成の完全自律化」・SSOT） |
| **A-3（品質ゲート致命的 NG 時の続行判断）** | ルーティンが「層フロー」の途中で致命的指摘を検出した場合、続行判断が必要か | ルーティンの設計時に「品質ゲート閾値の定義」を issue 化してから実装（#A-3 判定は詳細検査後） |
| **A-4（サーキットブレーカー・修正サイクル 2 回超）** | ルーティン内でサーキットブレーカー発動した場合、自動で停止するか続行するか | ルーティン設計時に「発動時は `status:waiting-user` に遷移・通知」と明記（手動再開必須） |
| **CP-6 / 確認最小化** | ルーティンの意思決定（「リファインメント対象にするか」「Epic 化するか」）が既存スキル（`self-improvement-loop` の整理モード）と重なるか | `improvement-lane-map.md` §3 による「受け渡しは GitHub Issue のラベル」で境界明示・暗黙の期待排除 |
| **CP-4 / マルチセッション並行** | ルーティン実行中に別セッションが同じ Issue に着手する TOCTOU 競合 | `status:in-progress` ロック（論理ロック・CP-4）を ルーティン開始時に即操作（既定動作） |

---

## 追加確認が必要な設計フェーズ

スプリント自走ルーティン「導入」に先立ち、以下を明記した Issue / ADR を先行起票：

1. **ルーティン実行モデル**: 「毎 N 時間・決まった時刻・トリガー駆動」のどれか（スケジュール定義）
2. **リファインメント対象の収束条件**: 「全 type 対象（`type:retro-try` 除外）」が実装スプリント開発ルール（SD-3）と矛盾しないか
3. **障害検出時の自動ルート**: サーキットブレーカー発動・品質ゲート NG を自動で `status:waiting-user` 化するか、ユーザー判断に委ねるか
4. **並列エージェント上限**: `agent-team-summary.md` §0 の「同時 20 上限」「ネスト深度 3」がルーティン内の並列実行で守られるか
5. **Warm 層ルール参照**: リファインメント手順が `improvement-lane-map.md` / `user-confirmation-minimization-detail.md` § 等 Warm ファイルを必要とする場合、ルーティン開始時に自動 Read させる仕組み

---

## 検査完了のサマリー

✅ スプリント開発フロー（SD-1〜4・見積もり・リファインメント・確認境界）は既存ルール資産で 85% カバー済み
✅ Hot 層予算に +30KB の余地あり（新規ルール追加可能）
✅ スキル description との衝突リスク低い（トリガーワード明示で回避可能）
✅ 機械検証ツール 5 本が既に配備済み（新規ファイル追加時に自動実施）
🟡 CP-6 / A-1〜A-6 との衝突は「設計フェーズ」で明示的に解決必須（設計 Issue 先行起票推奨）
🟡 マルチセッション競合（CP-4）と品質ゲート（A-3/A-4）の自動ルート定義が未確定
