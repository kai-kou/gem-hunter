<!--entry
author: repo_hardening
round: 1
kind: claim
ts: 2026-08-24T12:23:24+09:00
-->

# GitHub 側ハードニング（リポジトリ/アカウント設定）— 担当: repo_hardening

## 0. 実際に API で確認できたこと（推測ではなく実測）

- **`main` の保護は「ルールセット」方式**（旧 classic branch protection ではない）。`GET /branches/main/protection` は 403（旧 API 経路は使われていない）、`GET /rulesets` で `protect-main`（id=21082714, enforcement=active）を確認。
- **`protect-main` ルールセットの実際の中身**（`GET /rulesets/21082714`）:
  - `deletion` ルールあり（main 削除禁止）
  - `non_fast_forward` ルールあり（force push 禁止）
  - `pull_request` ルールあり（`required_approving_review_count: 0` / `allowed_merge_methods: ["squash"]` / `require_code_owner_review: false`）
  - 🔴 **`required_status_checks` ルールが存在しない** → `quality-checks.yml` は CI として動いているが、**main へのマージ条件として強制されていない**（`pr-review-flow-summary.md` 自身が「強制力は未配線」と認めている記述と一致。実測で裏付けが取れた）
- **Private vulnerability reporting は有効**（`GET /private-vulnerability-reporting` → `{"enabled": true}`）。`SECURITY.md` の「Security タブから報告」導線と整合。
- リポジトリは `visibility: public`・`allow_squash_merge: true` のみ許可・`delete_branch_on_merge: true`。
- `SECURITY.md` は存在（脆弱性報告窓口として機能）。`CODEOWNERS` は **存在しない**（`find` で確認、0 件）。`.github/dependabot.yml` も **存在しない**（バージョンアップ PR の自動化は未設定。アラート自体は別機能）。`.github/ISSUE_TEMPLATE/` も存在しない（優先度低）。
- Actions ワークフローは 2 本のみ。`quality-checks.yml` は `permissions: contents: read` のみ（最小権限・良好）。`gem-pool-refresh.yml` は `schedule` + `workflow_dispatch` のみが trigger（`pull_request` 系ではない → fork PR からのシークレット窃取経路にはならない）。`permissions: contents: write, pull-requests: write` をジョブ内で明示（デフォルト権限に頼らず宣言している点は良好）。`actions/checkout@11d5960...` のように **SHA 固定** で third-party action を pin 済み（サプライチェーン対策として良好・既に実施済みなので追加指摘なし）。

## 1. API 経由では確認できなかった項目（画面で確認が必要・断定しない）

以下は本セッションのプロキシ制約（`Access to this GitHub API path is not permitted through this proxy` / `Resource not accessible by integration`）により **取得不可**。ユーザーが画面で確認する必要あり:

- Secret scanning / Push protection の ON/OFF（`security_and_analysis` フィールドが応答に含まれず）
- Code scanning（CodeQL）設定状況
- Dependabot alerts / security updates の ON/OFF
- Actions の Workflow permissions（デフォルト read/write）・fork PR 承認要否設定
- Collaborators 一覧・Deploy keys 一覧・Environments/Secrets 一覧
- 2FA 設定状況

## 2. 推奨アクション（優先度付き・実際の URL）

### 必須

1. **`quality-checks` を required status check として `protect-main` ルールセットに追加**
   - URL: `https://github.com/kai-kou/gem-hunter/settings/rules/21082714`（または `Settings → Rules → Rulesets → protect-main`）
   - 手順: "Require status checks to pass" をトグル ON → "Add checks" で `checks`（`quality-checks.yml` の job 名）を検索して追加。`pull_request` トリガーで走る run を選ぶ
   - なぜ: 現状 CI 緑確認は「セッションの運用規律」のみで担保しており、機械的強制がない（`pr-review-flow-summary.md` 自身が明記）。ルールセットに登録すれば取りこぼしを機械的に防げる
   - 注意: 登録すると `automation/gem-pool-refresh` PR（`GITHUB_TOKEN` 起動のため check run が生成されない・`pr-review-flow-summary.md` に既知の記載あり）が **永久 pending でマージ不能** になる。このブランチ/PR だけ除外条件を設けるか、bypass 設定を検討すること

2. **Secret scanning + Push protection の ON 確認**
   - URL: `https://github.com/kai-kou/gem-hunter/settings/security_analysis`
   - public リポジトリでは既定 ON のはずだが、API 経由で未確認のため画面で実際の状態を目視すること

3. **Dependabot alerts + security updates の ON 確認、および version updates（`.github/dependabot.yml`）の追加**
   - URL: `https://github.com/kai-kou/gem-hunter/settings/security_analysis`
   - なぜ: `SECURITY.md` が「依存パッケージの脆弱性は Dependabot が追跡している」と明記しているが、`.github/dependabot.yml` が存在しないため **version updates（定期 PR での更新）は動いていない**。alerts（脆弱性検知）は別機能で репо設定で有効化するだけで動くが、内容は画面確認必須
   - package.json は dependencies 14 件・devDependencies 25 件（npm エコシステム）

4. **Code scanning（CodeQL default setup）の有効化**
   - URL: `https://github.com/kai-kou/gem-hunter/settings/security_analysis` → "Set up" → Default
   - なぜ: TypeScript/Next.js コードベース。CodeQL の JS/TS 解析は追加設定なしで default setup が使える

### 推奨

5. **Actions → Workflow permissions を Read-only に**
   - URL: `https://github.com/kai-kou/gem-hunter/settings/actions`
   - "Workflow permissions" セクションで "Read repository contents permission" を選択（デフォルトが Read/Write のままだと、`permissions:` 未宣言の将来のワークフローが誤って書き込み権限を持つ）。現状の 2 本は自前で `permissions:` を宣言済みなので実害は限定的だが、デフォルトを絞ることで将来の workflow 追加時の事故を防げる
   - 同じ画面で **"Require approval for all outside collaborators"**（fork からの PR で Actions が自動実行されないようにする）を有効化。本リポジトリは public で fork PR を受け付けうるため優先度は中〜高

6. **Actions の許可アクションポリシー**
   - URL: `https://github.com/kai-kou/gem-hunter/settings/actions` → "Actions permissions"
   - "Allow \<owner\> actions and reusable workflows, plus specified actions and reusable workflows" 等に絞ることを検討（現状 `actions/checkout` 等 SHA pin 済みなので急務ではないが、無制限許可のままだと新規追加時の統制が効かない）

7. **アカウントの 2FA / Personal Access Token 棚卸し**（A-6・ユーザー操作が物理的に必要）
   - URL: `https://github.com/settings/security`（2FA）/ `https://github.com/settings/tokens`（PAT 棚卸し）
   - GitHub App 認証を使っている前提だが、個人アカウント側の PAT が別途生きていないか確認

### 任意

8. **CODEOWNERS の追加は不要と判断**（優先度: 低・情報提供のみ）
   - `protect-main` の `required_approving_review_count: 0` は自律 PR 運用（恒久委任）の意図的な設計。CODEOWNERS を追加しても `require_code_owner_review: false` のままなら効果がない。将来レビュー必須化する場合にのみ検討

9. **Cloudflare 側の露出**（GitHub 設定ではないため対象外だが記録）: `wrangler.jsonc` に `workers_dev: true` / `preview_urls: true` があり `*.workers.dev` サブドメインと PR プレビュー URL が誰でも到達可能。GitHub の設定範囲外なので Cloudflare ダッシュボード側の確認をユーザーに促す（他レンズの担当外なら別途指摘要）
