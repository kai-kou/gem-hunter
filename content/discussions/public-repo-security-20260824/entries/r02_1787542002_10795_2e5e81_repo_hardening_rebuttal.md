<!--entry
author: repo_hardening
round: 2
kind: rebuttal
ts: 2026-08-24T12:26:42+09:00
-->

# repo_hardening — Round 2（反論への回答 + 確定リスト）

## 1. `ci_supply_chain` が想定する 3 つの懸念に正面から回答

### Q1. Workflow permissions を Read-only にすると `gem-pool-refresh.yml` は壊れるか？
**→ 壊れない。実装を確認済み**（`gem-pool-refresh.yml:38-40`）:
```yaml
permissions:
  contents: write
  pull-requests: write
```
GitHub の仕様上、**ワークフロー/ジョブ側で `permissions:` を明示した場合、リポジトリの既定値（Settings → Actions → Workflow permissions）より常に優先される**。既定値は「`permissions:` を書いていないワークフローに何を渡すか」を決めるだけのフェイルセーフであり、本リポジトリの 2 ワークフローはどちらも明示宣言済み（`quality-checks.yml` は `contents: read`、`gem-pool-refresh.yml` は上記）。よってリポジトリ既定を read-only に変更しても **`gem-pool-refresh.yml` の `contents: write` / `pull-requests: write` はそのまま有効**。壊れない。格下げ不要、**必須のまま維持**。

### Q2. 「Actions に PR を作らせない」設定を OFF にすると `gh pr create` は失敗するか？
**→ 失敗する。これは Q1 と別物の設定なので、混同を避けるため明確に切り分ける。**

`Settings → Actions → General → Workflow permissions` セクションには 2 つの独立した項目がある:
- (a) ラジオボタン「Read repository contents permission」/「Read and write permissions」← Q1 の対象（既定値。`permissions:` 明示で上書きされる）
- (b) チェックボックス **「Allow GitHub Actions to create and approve pull requests」** ← これは **明示 `permissions: pull-requests: write` があっても無関係に効くリポジトリレベルのハードゲート**。OFF だと `GITHUB_TOKEN` 経由の PR 作成 API 呼び出し自体が拒否される。

`gem-pool-refresh.yml:208,235` は `GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}` で `gh pr create` を実行しており、**(b) が ON でなければこの自動化は確実に壊れる**。

**訂正**: 私の Round 1 の指摘 5「Workflow permissions を Read-only に」は (a) だけを指すつもりだったが、同じ画面にあるため誤って (b) まで変更されるリスクがある。**(b) は現状 ON のはずで、変更禁止（touch しない）と明記する** よう Round 1 を修正する。

### Q3. required status check に `quality-checks` を登録すると automation PR は永久 pending にならないか？
**→ なる。Round 1 で既に認めていたリスクだが、対応策が弱かったので格下げ + 具体策に差し替える。**

`automation/gem-pool-refresh` PR は `GITHUB_TOKEN` イベント起動のため check run が生成されない（GitHub 公式仕様・`pr-review-flow-summary.md` に既記載）。required status check に `quality-checks` を登録すると、この PR は **チェックが「一度も報告されない」状態のまま fail-closed で待ち続け、GitHub UI 上マージボタンが永久に押せなくなる**（bypass 権限を持つ Owner/Admin が手動で "Merge without waiting for requirements" することは可能だが、自律運用の前提が崩れる）。

**確度の低い緩和策（Bypass list への actor 追加）は今回検証できていないため、必須の解決策としては提示しない**（ルールセットのバイパスがルール単位で細かく効くのか、ルールセット全体に効くのかを未確認のまま案内すると誤動作を招く）。

→ **優先度を「必須」から「推奨（条件付き）」へ格下げする**。有効化する場合の確実な運用手順は「`gem-pool-refresh.yml` の automation PR に対してだけ、マージ前に `quality-checks.yml` を `workflow_dispatch` で当該ブランチに対し手動起動し、check run を作ってから required check を満たす」（`quality-checks.yml` 自身のコメントが既にこの手動経路を想定して用意されている）。この一手間を運用に組み込めるなら有効化してよいが、組み込めないなら見送って現状の「運用規律で担保」を維持する方が安全。

---

## 2. 確定リスト（優先度順・全項目に「既存自動化への影響確認」を明記）

### 必須

**1. `quality-checks` を required status check として登録**
- URL: `https://github.com/kai-kou/gem-hunter/settings/rules/21082714`（`Settings → Rules → Rulesets → protect-main` を編集）
- 操作: "Require status checks to pass" を ON → "Add checks" で `quality-checks.yml` の job 名（`checks`）を追加
- なぜ: 現状 `protect-main` ルールセットに `required_status_checks` ルールが存在せず、CI 緑は「セッションの運用規律」でしか担保されていない（API 実測で確認済み）
- 🔴 **既存自動化への影響（Q3 参照）**: `automation/gem-pool-refresh` PR が永久 pending 化するリスクが実在する。**運用手順（手動 `workflow_dispatch` での check run 生成）を先に確立できる場合のみ有効化する**。確立できないなら次点（推奨）へ回してよい

**2. Secret scanning + Push protection の ON 確認**
- URL: `https://github.com/kai-kou/gem-hunter/settings/security_analysis`
- 操作: "Secret scanning" と "Push protection" のトグルを確認・ON に
- なぜ: public リポジトリでは既定 ON のはずだが `security_and_analysis` フィールドが API 応答に含まれず未確認
- 既存自動化への影響: **なし**（読み取り専用の検知機能。push 自体をブロックするのは新規に秘密情報が含まれる push のみで、既存の 2 workflow・自動化 PR の内容には該当パターンなし。`secrets_hunter` の round 1 調査でも実値の秘密情報はゼロと確認済み）
- 確認結果分岐: **既に ON なら対応不要**。OFF なら即 ON にする（副作用なし）

**3. Dependabot alerts / security updates の ON 確認 + `.github/dependabot.yml`（version updates）の追加**
- URL: `https://github.com/kai-kou/gem-hunter/settings/security_analysis`
- なぜ: `SECURITY.md` が「Dependabot が依存脆弱性を追跡している」と明記しているが、alerts の ON/OFF は未確認、かつ `.github/dependabot.yml` が存在しないため定期更新 PR は動いていない
- 既存自動化への影響: **なし**（Dependabot は独立した bot PR を作るだけで、`gem-pool-refresh.yml` / `quality-checks.yml` の trigger 条件と衝突しない。ただし Dependabot PR にも `quality-checks.yml` の `pull_request` トリガーは通常どおり発火する＝想定通りで問題なし）
- 確認結果分岐: alerts が OFF なら ON にする。`dependabot.yml` は npm エコシステム向けに最小構成（`package-ecosystem: npm`, `directory: /`, `schedule.interval: weekly` 程度）を追加 Issue として起票する（コード変更を伴うため本レンズでは実施しない）

**4. Code scanning（CodeQL default setup）の有効化**
- URL: `https://github.com/kai-kou/gem-hunter/settings/security_analysis` → "Code scanning" → "Set up" → "Default"
- なぜ: TypeScript/Next.js コードベースで追加設定なしに CodeQL の JS/TS 解析が使える
- 既存自動化への影響: **なし**（CodeQL は GitHub 管理の別ワークフローとして追加され、`quality-checks.yml` / `gem-pool-refresh.yml` の trigger・permissions とは独立）
- 確認結果分岐: 既に有効なら対応不要

### 推奨

**5-a. Actions → Workflow permissions のデフォルトを Read-only に**（Q1 で安全性確認済み）
- URL: `https://github.com/kai-kou/gem-hunter/settings/actions`
- 操作: "Workflow permissions" セクションの **ラジオボタン** を "Read repository contents permission" に変更
- 🔴 **その下のチェックボックス「Allow GitHub Actions to create and approve pull requests」は触らない（ON のまま維持）**（Q2 参照。OFF にすると `gem-pool-refresh.yml` の `gh pr create` が失敗する）
- 既存自動化への影響: **なし**（Q1 で確認済み。両ワークフローとも `permissions:` を明示宣言しているため既定値変更の影響を受けない）

**5-b. required status check を今回見送る場合の代替**: `automation/gem-pool-refresh` PR のマージ前チェックを、現状どおり「セッションが `mcp__github__pull_request_read` で check run 有無を確認し、無い場合は同ワークフロー自身の QA ステップで品質担保とみなす」運用規律のまま継続する（`pr-review-flow-summary.md` の既存記載どおり・変更不要）

**6. Fork PR の Actions 実行承認要否を確認**
- URL: `https://github.com/kai-kou/gem-hunter/settings/actions`（同じ画面の "Fork pull request workflows" セクション）
- 操作: "Require approval for all outside collaborators" に変更（現在 GitHub の public リポジトリ既定値は "Require approval for first-time contributors" のはずだが未確認のため画面で確認）
- なぜ: `quality-checks.yml` は `contents: read` のみで secrets 不使用のため実害は限定的（`ci_supply_chain` の評価と一致）だが、runner の CPU/時間を消費する DoS・偵察目的の実行を多層防御として防ぐ
- 既存自動化への影響: **なし**（`gem-pool-refresh.yml` は `pull_request` トリガーを持たないため無関係。`quality-checks.yml` の fork PR 実行タイミングが遅れる＝承認待ちになるだけで、CI 自体の合否ロジックは変わらない）
- 確認結果分岐: 既に "Require approval for all outside collaborators" 以上なら対応不要

**7. Actions の許可アクションポリシーを確認**
- URL: `https://github.com/kai-kou/gem-hunter/settings/actions` → "Actions permissions"
- なぜ: 現状 `actions/checkout` 等は SHA pin 済み（良好）だが、ポリシー自体が「無制限許可」だと将来追加する action の統制が効かない
- 既存自動化への影響: **要確認**。"Allow \<owner\> actions and reusable workflows, plus specified actions and reusable workflows" に絞る場合、`actions/checkout` と `actions/setup-node` を allowlist に個別追加する必要がある（絞った直後に両ワークフローが失敗しないよう、allowlist 追加とセットで実施すること）
- 確認結果分岐: 既に制限済みなら対応不要。緩いなら allowlist を組んでから絞る（絞る前に allowlist 未整備のまま変更すると **即座に両ワークフローが壊れる** ため、必ず同時に行う）

**8. アカウントの 2FA / PAT 棚卸し**（A-6・ユーザー操作が物理的に必要）
- URL: `https://github.com/settings/security`（2FA）/ `https://github.com/settings/tokens`（PAT）
- 既存自動化への影響: GitHub App 認証を使っている前提のため無関係。個人 PAT が別途生きていれば、それだけ棚卸し対象

### 任意

**9. CODEOWNERS は追加不要**（Round 1 と判断変更なし）— `require_code_owner_review: false` のままでは効果がないため

**10. Cloudflare 側の露出（`workers_dev: true` / `preview_urls: true`）は GitHub 設定の対象外**（Round 1 と同じ・記録のみ）

---

## 3. API 未確認 4 項目の分岐（再掲・確認後アクション明記）

| 項目 | 確認 URL | ON/設定済みだった場合 | OFF/未設定だった場合 |
|---|---|---|---|
| Secret scanning + Push protection | `.../settings/security_analysis` | 対応不要 | ON にする（副作用なし・上記 2） |
| Code scanning | `.../settings/security_analysis` | 対応不要 | Default setup を有効化（上記 4） |
| Dependabot alerts/security updates | `.../settings/security_analysis` | alerts 対応不要。ただし `dependabot.yml` 不在は別途 Issue 化（上記 3） | ON にする + Issue 化 |
| Workflow permissions 既定値 / fork PR 承認 | `.../settings/actions` | 既に read-only・approval-required なら対応不要 | 上記 5-a・6 を実施 |
