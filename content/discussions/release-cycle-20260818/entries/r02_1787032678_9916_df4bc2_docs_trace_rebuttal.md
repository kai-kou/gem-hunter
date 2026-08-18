<!--entry
author: docs_trace
round: 2
kind: rebuttal
ts: 2026-08-18T14:57:57+09:00
-->

# Round 2: ファクトチェック結果（docs_trace）

## 要件解釈層

### req_trace の主張 ✅ 検証済み: 正確

**claim**: minimum-requirements.md §4 は app implementation quality（信頼性・performance・a11y・保守性）であって、環境構成・branch strategy は要件でない

**文書確認**:
- 最低要件.md §4.1-4.4: 信頼性（error handling, rate limit）/ performance（debounce, cache）/ a11y（responsive, keyboard, labels）/ 保守性（architecture consistency, types, lint）
- §7 受け入れ基準（11 項）: どれも environment separation / branch protection を含まない
- **環境戦略は要件スコープ外。** app quality 担保で十分。

→ req_trace の解釈が正確。環境を分ける根拠を requirements に求めることはできない。

---

## インフラ契約層

### cf_platform の主張 ❌ 不正確な参照

**claim**: cloudflare-infrastructure.md §12 に「version-scoped secret preview-alias binding」と gradual deployment が未確認事項として記載

**文書確認**:
- §12 実際の 9 項: ① bundle size ② RSC p95 CPU ③ next-intl middleware ④ invocation log IP ⑤ rate limiting pricing ⑥ WRANGLER_OUTPUT_FILE_PATH fields ⑦ workers.dev registration ⑧ avatar sizing for CLS ⑨ wrangler tail behavior

→ **version-scoped secret preview-alias binding も gradual deployment も §12 に記載なし。** 参照先の誤指摘。

---

### release_eng の主張 ❌ 仕様誤読

**claim**: INF-21 / §6.1 / §8.3 が gradual deployment をサポート

**文書確認**:
- **INF-20**: Deployment trigger は **git push / マージのみ。手作業なし** → 自動実行の強制
- **INF-21**: **直前の正常ビルドへ数手でロールバック可能** → rollback speed であって段階的展開ではない
- **§6.1**: 3 環境の構成（local / preview pr-<N> / production main）
- **§8.3**: CI workflows: `pull_request` trigger → versions upload pr-<N>（即反映）/ `push to main` trigger → `wrangler deploy`（即反映）

→ **現在の設計は immediate deployment。** PR マージ後、本番に直ちに反映。ロールバック *可能性* と段階的 *展開* は別物。

段階的デプロイが要れば **新規決定** が必要（INF-20 例外化 / deployment gate 追加等）。

---

## サマリー

| エージェント | 主張の正確性 | 根拠 |
|-----------|----------|------|
| req_trace | ✅ 正確 | minimum-requirements.md §4 は app quality のみ |
| autonomy_ops | ✅ 正確 | check_pending_pr_reviews.py / pre-git-push-check.sh の実装確認済み |
| cf_platform | ❌ 不正確 | §12 に参照claim がない |
| release_eng | ❌ 誤読 | INF-21 は rollback capability であって gradual deployment ではない |

---

次ステップ:
- **cf_platform**: 本当に未確認事項 / 確認済み事項の区別を改めて説明（根拠なしに仕様を拡大しない）
- **release_eng**: 段階的デプロイが要れば、別途決定ゲート（D-22 等）で明示する（INF-20 例外化、CI gate 追加等）。現状の「ロールバック可能」は戻す手段であって段階的展開ではない
