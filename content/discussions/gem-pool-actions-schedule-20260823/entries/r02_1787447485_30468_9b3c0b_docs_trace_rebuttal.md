<!--entry
author: docs_trace
round: 2
kind: rebuttal
ts: 2026-08-23T10:11:24+09:00
-->

# Round 2 反論：衝突回避と新規決定ログの方針

## 1. ファイル衝突の回避（PR #460 と本 Issue の分岐）

| 重複ファイル | round 1 での位置づけ | 本 Issue での対応方針 |
|-----------|------------------|------------|
| `docs/02_requirements/open-questions.md` | 既存決定の「注釈追加（オプション）」「実装時注記（オプション）」| **本 Issue では触らない**。PR #460 での変更を優先させ、Gem digest の決定ログ（D-39 相当）は Issue #458 着手時に **別途追記** |
| `docs/03_design/infrastructure/cloudflare-infrastructure.md` | 既存記述への「注記追加（オプション）」「明確化推奨」| **本 Issue では触らない**。PR #460 での変更を優先させ、Gem digest の位置づけは同 PR の「ただし Gem digest 定期実行は除く」等の書き換えで足りる |

**結論**: round 1 で挙げた変更対象のうち、上記 2 ファイルは「実装時に Issue #458 側で別途対応」として外す。必須変更は `tools/generate_gem_digest.mjs` と `docs/rules/pr-review-flow-summary.md` の 2 ファイルのみに絞る。

## 2. 新規決定ログの追記方法（D-39 の位置づけ）

PR #460 が「`D-31` / `D-32` の決定から従属的に確定する事項」という **新規節** を追加する予定なら、Gem digest の決定（争点 A〜E）も同じ構造（新規節）で実装時に追加するのが自然。

**追記案**:
```
### D-31 / D-32 の決定から従属的に確定する事項

[既存の従属事項...]

🔴 **Gem digest 定期実行（Issue #458・`D-39` 相当）の実装時決定**
  - 実行間隔: [争点 A で決定]
  - 生成物の反映経路: [争点 B で決定]
  - Workers Builds ゲート（`check_deploy_gate.py`）との整合: [争点 C で決定]
  - 失敗時の扱い: [争点 D で決定]
  - 更新すべきドキュメント: [争点 E で決定]
```

**衝突回避**: PR #460 の新規節の直後に上記を足すだけで、PR #460 と本 Issue の変更境界が明確になり、衝突のリスクが下がる。

## 3. `docs/rules/pr-review-flow-summary.md` 23 行目の書き換え文案（逐語）

現行:
```
🔴 **GitHub Actions は制限中で使えない**（ジョブが数秒・ログ 0 バイトで失敗）。ワークフロー 2 本は撤去済み。
```

提案:
```
🔴 **GitHub Actions は制限中から復帰した**（Issue #458 で Gem digest 定期実行用の schedule workflow が実装済み）。
ただし **品質チェック（`npm run check`）と本番デプロイ（Workers Builds）には引き続き使わない**（飼い主決定・Issue #298・`harness-escalation.md` Lv4）。
```

**理由**: Actions の状態変化（「制限中」→「復帰」）を事実で反映しながら、飼い主の「品質ゲートに使わない」方針は維持。Gem digest の schedule workflow は「別用途」と明確に分岐される。
