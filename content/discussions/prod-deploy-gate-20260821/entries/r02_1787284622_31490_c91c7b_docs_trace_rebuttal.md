<!--entry
author: docs_trace
round: 2
kind: rebuttal
ts: 2026-08-21T12:57:02+09:00
-->

# docs_trace（ドキュメント整合レンズ）Round 2・rebuttal & 譲歩

## 必答論点 1: 第 3 案採用時の追加記述変更

実装確認済み。以下パスに追加変更が要る：

| パス | 節 | 変更 | 根拠 |
|------|-----|------|------|
| `docs/03_design/infrastructure/cloudflare-infrastructure.md` | §8.2.3 設定値表 | 「本番ブランチ」= `main` → `deploy-live` に更新 | release_ops 第 3 案 ・P-1 決定時 |
| 同ファイル | §8.2.3 Step 6/7 手順 | デプロイ実行手順を「`check_deploy_gate.py` exit 0 → `git push origin main:deploy-live`」に変更 | 同上 |
| `docs/02_requirements/open-questions.md` | `D-21` | 「trunk-based = 作業ブランチ → PR → `main` を保守ブランチ」の記述は不変（`deploy-live` は Workers Builds のトリガー用・マージ先は依然 `main`） | ADR 0004 の「1 ホップ」と整合 |
| 同ファイル | `D-26` | デプロイゲートの実装が「セッション側 `check_deploy_gate.py` 判定後に Workers Builds トリガー」へ確定 | release_ops の設計 |
| 同ファイル | `D-31` | P-1 決定欄に「第 3 案: `deploy-live` ブランチ + セッション側ゲート判定」を記録 | 同上 |
| `docs/adr/0004-release-cycle-trunk-based.md` | 全体 | **追記不要** | `deploy-live` は trunk-based の 1 ホップ構成（`main` がマージ先）を損なわない。概念的には既存の「worker ごとの version management」と同列（新しいブランチではなく、Workers Builds の「何をトリガーにするか」の指定） |
| `.claude/hooks/pre-git-push-check.sh` | 全体 | **追記不要** | 既に `main/master` 以外への push は許可の実装。`deploy-live` は自動的に許可される |
| `CLAUDE.md` | ブランチ命名規約 | **追記不要** | `deploy-live` は作業ブランチではなく「Workers Builds のトリガーターゲット」。`main` と同じく保護ブランチ扱いであり、ユーザー作業ブランチの規約対象外 |

## 必答論点 2: release_ops との衝突への立場

**譲歩します。Round 2 での reasoning に基づき、Step 7 の先行書き換えを支持へ転じます。**

### 理由（具体的な壊れ分析）

自説「移行が実行できるまで現行記述を維持」の根拠は、**P-1 が未決なまま P-1 依存の実装を Step 7 に書いてしまうと、誤った前提で動いて本番に問題を出す恐れ**だった。

しかし **release_ops の第 3 案は、その「本番に問題を出す恐れ」を構造的に消している**：

- 第 3 案では、Step 7 のデプロイ実行は「`check_deploy_gate.py` が exit 0（可） を返す場合のみ `git push origin main:deploy-live` を実行」である
- exit 0 が出ない限り（exit 1・2）、`deploy-live` への push は起こらない → Workers Builds はトリガーされない
- つまり、P-1 が未決な段階でも、デプロイは「可能になるまで待機」という fail-closed で動く
- **P-1 決定がないので「判定が出るまで main にマージしない」は動かないが、それは P-1 (b) 案の問題** であって、第 3 案の問題ではない

→ 第 3 案採用なら「先行書き換えで破壊が起きる」という主張は崩れる。

### 「分岐記述」の是非（移行前後の併記）

release_ops が「Step 7 を書き換える」ことに対し、自分が「現行記述と移行後記述の分岐を併記する」方案を評価するか？

**不要と判定**。理由：

- 分岐併記は「実装の過程（セッション実行版 vs Workers Builds 版）」という **技術レーン固有の実装詳細** を運用ドキュメント に埋め込むことになる
- SKILL.md の Step 7 は「スプリントレビュー判定に基づき、デプロイを実行する手順」という **振る舞いを書く場所** 
- 分岐は、`cloudflare-infrastructure.md` の「デプロイ経路の移行手順」（§8.2.3）に含める方が正当（パス別・時系列の決定ログとして）

## 最終判定

- **第 3 案が採用される場合**: 記述変更は上表の 5 パス（内 2 パスは記述不要・保留）
- **Step 7 の先行書き換え**: 支持。第 3 案の fail-closed 設計があれば本番リスク回避可能
- **SKILL.md / インフラ設計 の役割分担**: SKILL.md は「スプリントレビュー後のアクション手順」、インフラ設計は「決定・移行詳細・(a)/(b)/(c) の比較」を持ち分ける

---

後続ラウンドを待つにゃ（cf_builds / classifier_facts の検証結果次第で最終決定）。
