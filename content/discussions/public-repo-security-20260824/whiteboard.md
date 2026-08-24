<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: パブリック公開中の kai-kou/gem-hunter のセキュリティレビュー（リポジトリ内容 + GitHub 側設定）

- 議題ID: `public-repo-security-20260824`
- 論点: 本リポジトリは現在 public。① 公開してはいけない情報が入っていないか ② CI/CD・自動化の権限とサプライチェーンが公開前提で安全か ③ アプリ実行時のセキュリティ（OAuth/Cookie/レート制限/リダイレクト/CSP 等）④ GitHub 側で設定すべきハードニング（ブランチ保護・Secret scanning・Push protection・Dependabot・Actions 権限・fork PR の扱い等）を洗い、実際にリスクがある指摘だけを残す。最終成果物はユーザーが 1 手順ずつコピペで実行できる設定手順。
- 参加者: `secrets_hunter`, `ci_supply_chain`, `appsec_runtime`, `repo_hardening`
- 投稿数: 8
- 更新: 2026-08-24T12:26:52+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

## ラウンド 1

### `secrets_hunter` — 主張
<sub>2026-08-24T12:22:00+09:00</sub>

# secrets_hunter — Round 1 所見

## 結論（severity: なし。実値の秘密情報漏洩は検出ゼロ）

事前に `docs/05_release/repository-publication-review.md`（2026-08-20 実施の公開前レビュー）が存在し、Issue/PR/全ブランチ含む網羅スキャンで「秘密情報の検出ゼロ」と結論済み。本ラウンドはその**再現性確認**（独立した正規表現走査）と**2026-08-20〜08-24 の差分 50 コミット分の再走査**を実施した。結果、新規混入なし。

## 実施した調査と結果

1. **`git log --all -p` 全履歴**を `ghp_/gho_/ghu_/ghs_/ghr_/xox[baprs]-/sk-ant-/sk-/AKIA/AIza/ya29\./BEGIN * PRIVATE KEY` で走査
   → ヒットはすべてダミー値・docstring 例示・鍵形式名への言及のみ（例: `tools/mask_secrets.py:54` の docstring、`docs/rules/slack-notification-rules.md:199-202` のプレースホルダ `xoxb-xxxxx-xxxxx-xxxxx` / `C0XXXXXXXXX`）。実値なし。

2. **`.env` 系ファイル**: `git ls-files` に実 `.env`/`.env.local` 等は 0 件。`.gitignore` が `.env` `.env.*` `*.pem` `*.key` を網羅し、`!.env.example`（値なしテンプレート）のみ例外化。

3. **`public/data/`（4.2MB・生成データ）**: gem-index 系 JSON を全件 grep したが token/key パターン検出ゼロ（パッケージレジストリの公開メタデータのみ）。

4. **`.claude/settings.json`**: `permissions.allow` / `sandbox.network.allowedDomains` / hooks 設定を確認。実 API キー・実アカウント ID の記載なし。`excludedCommands` で secrets broker 系スクリプトをサンドボックス除外しているが、これは値を出力しない設計（`tools/setup_secrets_broker.sh` 等はブローカー経由取得のラッパーで、値自体はコミットされていない）。

5. **メールアドレス走査**: 検出は `git@github.com`（コミットメッセージ例示・リモート URL 例）と `i@izs.me`（npm 依存 `package-lock.json` のライセンス表記由来、`isaacs` 氏の公開情報）のみ。ユーザー個人メール（`koka.orz@...`）は履歴・追跡ファイルとも 0 件。

6. **GitHub App / Cloudflare 識別子**: `GITHUB_APP_CLIENT_ID` / `GITHUB_APP_INSTALLATION_ID` の実値が入った箇所なし（`.env.example` は空欄、テストは `vi.stubEnv` でダミー文字列 `'client-id'` 等）。Cloudflare account_id/zone_id（32 桁 hex）走査もヒットゼロ。`installation-token.test.ts` は `jose` で都度生成した使い捨て鍵ペアを使用（実鍵ではない）。

7. **`kinamocchi-tech.workers.dev`**（本番 URL）は README・SECURITY.md・`content/discussions/` に多数露出しているが、これは**意図的に公開しているプロダクト URL そのもの**（README 冒頭で「使ってみる」として案内済み）であり秘密情報ではない。既存レビューの `M-1'` で「新たな露出ではない」と結論済みの内容と整合。

8. **Slack チャンネル ID っぽい文字列（`C0[A-Z0-9]{8,10}`）**: ヒットは `og-background-data.ts` の SVG/画像生成用ランダム文字列、`e2e/fixtures/repos.json` のダミー avatar URL 断片、`package-lock.json` の npm パッケージ integrity 由来の base64 断片で、いずれも実 Slack チャンネル ID ではない誤検知。ドキュメント中の `C0XXXXXXXXX` はプレースホルダ。

9. **2026-08-20〜08-24 の差分**（コミット 50 件・`content/discussions/` の新規議論ログ多数含む）を同一パターンで再走査 → 新規混入なし。

## 明示的に「問題なし」と判定した領域
- git 全履歴（46 ブランチ相当は現行 origin では 1 本のみ確認できたため今回は `--all` の到達範囲で確認。ブランチ削除状況は他レンズの担当範囲外のため言及のみ）
- `public/data/`
- `.claude/settings.json` の allow/deny リスト・sandbox 設定
- `.env.example` とその周辺ツール（`mask_secrets.py` 等）の設計
- 直近 4 日間の差分

## 参考: 既存の一次資料
`docs/05_release/repository-publication-review.md`（2026-08-20 公開前レビュー、飼い主決定済み）が本レンズの大半を先行して網羅している。本ラウンドはその結論を独立に再現確認した位置づけ。

### `ci_supply_chain` — 主張
<sub>2026-08-24T12:22:28+09:00</sub>

# ci_supply_chain — Round 1 分析

## 結論サマリー
`.github/workflows/*` 2 本・`.mcp.json`・`.claude/hooks/*.sh`・`.claude/settings.json` permissions・依存関係（`package-lock.json`/`requirements.txt`）を精査。**critical / high 相当の実悪用可能な穴は見つからなかった**。既に fork PR・スクリプトインジェクション・postinstall RCE を意識した対策コメント付きで実装済み（`quality-checks.yml` の `--ignore-scripts` + `persist-credentials: false`、`gem-pool-refresh.yml` のヒアドキュメント delimiter ランダム化 + env 経由の PR body 渡し）。medium/low を数点、GitHub 設定側の推奨を 1 点報告する。

## 問題なし（確認済み・重複指摘しないための明記）
1. **`quality-checks.yml`（fork PR 到達時）**: `pull_request`（`pull_request_target` ではない）→ fork PR は書き込み権限なしトークンで実行され secrets 露出なし。`permissions: contents: read` のみ。`persist-credentials: false`（checkout時）。`npm ci --ignore-scripts` により fork 側 lockfile の postinstall RCE 経路を明示的に遮断（コメントで実測検証済みと明記）。`run:` 内に `${{ github.event.pull_request.* }}` 等の untrusted 値を直接展開している箇所はゼロ（4 チェックは固定コマンドのみ）。
2. **`gem-pool-refresh.yml`**: トリガーは `schedule` + `workflow_dispatch` のみで `pull_request` 系ではない → fork からの到達経路が存在しない。`workflow_dispatch.inputs.force_publish` は boolean で `run:` に直接展開されず `env.FORCE_PUBLISH` 経由（インジェクション不可）。PR body 生成でヒアドキュメント delimiter を `openssl rand -hex 8` で毎回ランダム化し、`GITHUB_OUTPUT` への early-termination injection を対策済み。PR body 自体も `env: PR_BODY` 経由で shell に渡し `${{ }}` を `run:` へ直接埋め込んでいない（GitHub 公式ガイダンス準拠）。`git push --force` の対象は自動化専用ブランチ `automation/gem-pool-refresh`（ユーザー入力に依存しない固定文字列）で、他ブランチ・main には触れない。
3. **Action pin**: 両ワークフローとも `actions/checkout` `actions/setup-node` を full-length commit SHA で pin（`# vX.Y.Z` コメント併記）。tag pin ではなくSHA pin なので改ざん耐性あり。
4. **`permissions:` 最小権限性**: `quality-checks.yml` は `contents: read` のみで妥当。`gem-pool-refresh.yml` の `contents: write` + `pull-requests: write` は「生成物をコミットして自動化ブランチへ push → PR 作成」という目的に対して必要最小限（Issue 作成権限・Actions 権限等の不要スコープは付与していない）。
5. **`.mcp.json`**: `CONTEXT7_API_KEY` / `GH_TOKEN` はプレースホルダ変数展開（`${VAR:-}`）のみで、実トークンはリポジトリに存在しない。public リポジトリに置いても安全な形。
6. **`.claude/hooks/*.sh`**: 全 19 スクリプトを `PR_TITLE`/`PR_BODY`/`ISSUE_TITLE`/`github.event` の直接シェル展開・`eval`/`bash -c` パターンで grep したが、危険な使用箇所はゼロ（`pre-git-push-check.sh` にヒットしたのは `eval` 自体を **検出してブロックする側**のガード実装）。
7. **Fork PR 経由の `.claude/` 改ざん → メンテナセッションでの任意コード実行**: hooks・skills・tools を grep した限り、PR レビュー処理は `mcp__github__*`（API 経由）で完結しており、**fork PR のブランチを `git checkout` してディスク上に展開する経路が見当たらない**（`pr-review-watcher` はレビュー・マージを GitHub API 越しに行う設計）。したがって fork 側で `.claude/settings.json` や hooks を書き換えても、それが同一セッションで自動的に読み込まれ実行される直接経路は確認できなかった。**ただし** これは grep ベースの確認であり、`pr-review-watcher` / `code-review` スキルが将来 diff 適用のために `git checkout <pr-branch>` する変更が入ると経路が生まれる点は要警戒（設計原則として明文化する価値はあるが、現状のコードには該当箇所なし）。
8. **依存関係**: `package.json` に `postinstall`/`preinstall`/`prepare` スクリプトなし。`package-lock.json`（lockfileVersion 3）は 1330 件の `resolved` が全て `registry.npmjs.org`（git/http 経由の野良依存ゼロ）。`requirements.txt` は `PyYAML>=6.0` のみで妥当。
9. **秘密情報の直書き**: リポジトリ全体を軽量 grep（AWS key / OpenAI風 sk- / GitHub PAT / Slack xox 系）した結果、ヒットは全てドキュメントのプレースホルダ・テストフィクスチャ・マスク関数の docstring 例（`tools/mask_secrets.py` 等）のみで実トークンなし。

## 指摘（medium/low）

### [low] `scripts/apply-to-repo.sh:11` — curl | bash の参照先が `main` ブランチ（可変 ref）
- ファイル: `scripts/apply-to-repo.sh:11`（コメント内のドキュメント例）
- 内容: `curl -fsSL https://raw.githubusercontent.com/kai-kou/claude-code-repository-base/main/scripts/apply-to-repo.sh | bash` という自己参照インストーラ例が置かれている。`main` は可変参照なので、`kai-kou/claude-code-repository-base` 側が将来侵害されれば任意コードが無検証で実行される（curl|bash パターン共通の弱点）。
- 攻撃シナリオ: 第三者ユーザーがこのコマンド例をコピペ実行した場合、実行時点の `main` HEAD の内容がそのまま無検証で走る。ただし同一組織（kai-kou）が管理する別リポジトリへの参照であり、本リポジトリ自体の攻撃面ではない（this repo → 別 repo への信頼委譲）。
- 対応: severity low。タグ/コミット SHA 固定への変更は任意（自己参照インストーラの一般的トレードオフであり必須ではない）。指摘のみ。

### [info] GitHub 設定で対処（`repo_hardening` 向けの要求事項として）
- **workflow の既定 `GITHUB_TOKEN` permissions**: リポジトリ Settings → Actions → Workflow permissions が "Read and write" のままだと、`permissions:` を明示していない将来の新規ワークフローが誤って書き込み権限を持ってしまう。現状の 2 workflow は明示 `permissions:` を持つため実害はないが、**既定を "Read repository contents permission" (read-only) に設定** しておくことを推奨（fail-safe化）。
- **fork PR の Actions 実行承認要否**: Settings → Actions → "Fork pull request workflows" が "Require approval for first-time contributors" 以上になっているか確認要（未設定だと fork PR の `pull_request` ワークフローが承認なしで即実行される。今回の `quality-checks.yml` 自体は read-only なので実害は限定的だが、runner 上での CPU/時間消費 DoS・情報探索目的の実行を防ぐ多層防御として推奨）。
- **ブランチ保護**: `main` へのブランチ保護ルール（required status check・force-push 禁止）が有効か未確認（GitHub API 越しの確認が必要でこのセッションのレンズ外）。`repo_hardening` 側で確認・設定手順化を推奨。

## 担当外への申し送り
- `.claude/settings.json` の `permissions.allow` の広さ（`Bash(gh:*)` 等）や sandbox `network.allowedDomains` の内容自体の是非は、prompt injection 耐性のレンズ（他参加者の担当）で評価されるべきなので本分析では踏み込まない。

### `appsec_runtime` — 主張
<sub>2026-08-24T12:22:41+09:00</sub>

## appsec_runtime — アプリケーション実行時セキュリティ（Round 1）

### 総評
OAuth・セッション Cookie・レート制限・SSRF 対策・README サニタイズは、すべてコード内コメントで
脅威モデルと対策根拠を明示した上で実装されており、実際にコードを読んだ限り重大な実装バグは
見当たらなかった。指摘は「実装ミス」ではなく「設計判断として妥当だが、公開リポジトリという
文脈で明示的にリスクとして残すべき点」が中心。

---

### [medium] セキュリティレスポンスヘッダ・CSP が一切設定されていない
- **該当**: `next.config.ts`（`headers()` 関数が存在しない）、`wrangler.jsonc`、`public/_headers` も不在
- **確認事実**: `next.config.ts` は `redirects()` のみで `headers()` を定義していない。リポジトリ全体を
  `_headers` で grep しても該当ファイルが存在しない。Cloudflare Workers 側にも独自ヘッダ注入は無い。
- **攻撃シナリオ**: README 表示（`app/[locale]/repos/[owner]/[repo]/page.tsx`）は `dangerouslySetInnerHTML`
  に `sanitize-html` 済みの第三者（GitHub リポジトリ作者）由来 HTML を差し込む。サニタイザ自体は
  allowlist 方式で堅牢だが、CSP が無いため「サニタイザにバグがあった場合の多層防御」が存在しない
  （`Content-Security-Policy` があればインラインスクリプト実行やインラインイベントハンドラが
  二重に防げる）。加えて `X-Frame-Options` / `frame-ancestors` が無いため、`/api/auth/login` を
  含む本サイトは第三者サイトに iframe 埋め込みしてクリックジャッキングを試みることが技術的に可能
  （実際に成立するかは UI 側の確認が必要・未確認）。`Referrer-Policy` も未設定。
- **分類**: コード修正が必要 → 別 Issue 起票が妥当（`next.config.ts` に `headers()` を追加するだけで
  実装できる小粒な変更）。

### [low] `RATE_LIMIT_SALT` 未設定時のフェイルオープンは、設計判断として文書化済みだが検知手段が弱い
- **該当**: `src/composition/rate-limit.ts:59-64`
- **確認事実**: `.env.example` に「未設定時は間引きをしない（フェイルオープン。429 にもならず黙って通る）」
  と明記され、コード側も `binding があるのに salt が無い＝Workers 上の設定不備` の場合だけ
  `console.warn('[rate-limit] RATE_LIMIT_SALT 未設定のため間引きを無効化しています')` を出す設計になっている。
- **リスク**: 本番（Workers 上）で salt だけが外れる事故（`wrangler secret` の付け替えミス等）が起きると、
  検索・Gem 一覧の両経路のレート制限が **黙って無効化**される。警告は `console.warn` のみで、
  Cloudflare Logs を能動的に見ていない限り気づかない。上流 GitHub API 枠の枯渇・自 Worker CPU 課金の
  青天井化につながりうる（`wrangler.jsonc` の `limits.cpu_ms: 400` が個別リクエストの天井にはなるが、
  本数自体は絞られない）。
- **判定**: 設計として意図的（フェイルオープンで可用性を優先）であり「バグ」ではない。ただし
  アラート未整備は運用上の穴なので、コード修正というより監視強化（Cloudflare Logs アラート等）が
  妥当な対応。GitHub 設定手順の範疇に近いため本セッションの主成果物（GitHub 設定）にも馴染む。

### 未確認・参考情報（他レンズとの重複を避けるため深掘りしていない）
- `wrangler.jsonc` の `workers_dev: true` / `preview_urls: true` はデプロイ設定であり、
  workers.dev サブドメイン経由でアプリ本体へ直接到達できる経路が常時開いている（カスタムドメイン
  だけに制限されていない）。アプリ実行時コードの問題ではなくインフラ設定なので、他レンズ
  （supply-chain / secrets）の担当範囲であれば重複起票しないでほしい。

### 確認して問題なしと判断したもの（対策が妥当に機能している）
- OAuth state: `crypto.randomUUID()` + `httpOnly/secure/sameSite=lax` Cookie + タイミングセーフ比較（`callback/route.ts`）
- オープンリダイレクト対策: `resolveLandingHost()` が `GITHUB_OAUTH_CALLBACK_URL` 由来の許可ホストとしか一致させない（`src/composition/auth.ts:55-62`）
- セッション Cookie: `jose` の `EncryptJWT`（A256GCM）でアクセストークンを暗号化し `httpOnly/secure/sameSite=lax` で保存（`session-cookie.ts`）。復号失敗は全経路 `null`（安全側）
- OAuth スコープ: `buildAuthorizeUrl` に `scope` パラメータを付けず no-scope（最小権限）
- SSRF: `resolveLoopbackOverridableOrigin()` が上書き先をループバックのみに制限し、認証情報送信先ホストを外部から差し替えられない（`loopback-origin.ts`）
- 検索クエリインジェクション: `searchKeyword()` が修飾子構文（`名前:値`）と大文字ブール演算子を拒否 + `is:public` を先頭固定（多層防御・`search-keyword.ts` / `github-repository-query.ts:44-50`）
- README XSS: `sanitize-html` allowlist（`script`/`style`/`iframe`等除外・`javascript:`等の危険スキーム除外・`parseStyleAttributes:false`）（`readme-html.ts`）
- 秘密情報のクライアント漏洩: `NEXT_PUBLIC_` プレフィックスの使用箇所がリポジトリ全体でゼロ（grep 確認済み）
- エラー応答: `search/route.ts` の `errorResponse()` は `error.message` を含めず `ErrorKind` のみ返す（内部情報を出さない）
- CSRF（logout）: POST 限定 + `sameSite=lax` セッション Cookie でクロスサイト POST は Cookie 非送信（`logout/route.ts`）

### `repo_hardening` — 主張
<sub>2026-08-24T12:23:24+09:00</sub>

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

## ラウンド 2

### `secrets_hunter` — 反論
<sub>2026-08-24T12:25:22+09:00</sub>

# secrets_hunter — Round 2 反論・譲歩

## 1. 過剰指摘（名指し）: `repo_hardening` の「必須」項目の緊急度フレーミング

`repo_hardening` の推奨アクション 2（Secret scanning + Push protection）・3（Dependabot）・7（2FA/PAT 棚卸し）を「必須」に分類している点について、**私のレンズ（実際に漏れている情報はあるか）からは異論がある**。

- **項目 2・3**: これらは「今この瞬間、公開してはいけない何かが露出している」ことへの対処ではない。私の Round 1 の網羅走査（全履歴・全追跡ファイル・直近 4 日差分）で **実値の秘密は検出ゼロ**。したがって Secret scanning / Push protection は「事故の後始末」ではなく「将来の事故を防ぐ予防線」であり、**緊急度は "必須（今すぐ止血が必要）" ではなく "推奨（再発防止の多層防御）"** に近い。有効化すべきという結論自体には同意するが、"必須" という語が「現に何か漏れている」という誤った切迫感を読み手に与えるなら過剰。
- **項目 7（2FA / PAT 棚卸し）**: 「本リポジトリを公開したことで生じたリスクへの対応」としては根拠が薄い。私のレンズでは **本リポジトリ内に PAT・個人トークンの実値は存在しない**（GitHub App 認証のみで運用されており、`.env.example` にも実値なし）。したがって "gem-hunter を公開したから PAT を確認すべき" という因果は成立せず、これは公開の有無に関係ない一般的なアカウント衛生（A-6）。優先度を「本件起因の必須」から「無関係の一般推奨」へ格下げすべき。

## 2. 他者の「問題なし」判定への補強（見落としではなく独立確認）

`ci_supply_chain` の項目 5（`.mcp.json` の `CONTEXT7_API_KEY` / `GH_TOKEN` はプレースホルダ展開のみで実値なし）は、私が Round 1 で実施した **リポジトリ全体の token パターン走査**（`ghp_/gho_/xox[baprs]-/sk-/AKIA` 等）の対象にも `.mcp.json` は含まれており、独立に同じ結論（実値なし）に達している。矛盾なし、むしろ二重確認で確度が上がった点を明記しておく。

## 3. `repo_hardening` の GitHub 設定項目 — 実際の脅威に紐づけた優先度の再判定

私のレンズ（漏洩の有無）から見た実際の脅威モデルは「**過去に漏れたものを今すぐ止める必要があるか**」であり、その基準で見ると:

- **過小評価されているものは無い**（Secret scanning 等はどれも "有効化して損はない" 側で、下げる理由がない）
- **過大評価**: 上記 1 で述べたとおり、項目 2/3/7 の緊急度ラベルが「本リポジトリの実態（=秘密は 0 件）」に対して重すぎる。実態は「攻めるべき穴が今ある」ではなく「守りの層を増やす」なので、`ci_supply_chain` が使っている critical/high/medium/low の重大度スケールに合わせるなら **medium 相当**（低すぎず、火急でもない）が私の判定。

## 4. 譲歩（Concession）

- **Issue/PR コメント本文の直近 4 日分は未走査**: Round 1 で「2026-08-20〜08-24 の差分を再走査」と書いたが、これは **git 追跡ファイルの diff のみ**であり、GitHub Issue/PR コメント本文（GitHub API 経由でしか取れない領域）は今回のセッションでは再確認していない。既存レビュー（`repository-publication-review.md`）は 2026-08-20 時点で Issue 233 件・コメント 196 件・PR レビュー 197 件・行コメント 415 件を走査済みだが、**それ以降の 4 日間に投稿された新規コメントは私の Round 1 の走査範囲外**。ゼロ件と断定した範囲を「追跡ファイル + 全 git 履歴」に限定するよう訂正する（severity は変えないが、対象範囲を明確化）。
- **workers.dev URL の一括評価を訂正**: Round 1 の主張 7 で `kinamocchi-tech.workers.dev` 系 URL 全般を「意図的公開・問題なし」と一括評価したが、これは **本番 URL**（README で案内済み）についてのみ正確。`appsec_runtime` / `repo_hardening` が指摘する **PR プレビュー用サブドメイン**（`pr-N-gem-hunter.workers.dev` 等）は、Issue #187（secret 未注入）により認証・レート制限が効かない状態で公開されている点で本番 URL とは性質が異なる。これは「秘密の漏洩」ではなく「未認証アクセスの可用性リスク」であり両者の担当レンズだが、**「URL の存在自体は新規露出ではない」という私の結論は本番 URL に限定し、プレビュー URL の可用性リスクの評価には及ばない**ことを明示しておく。

### `ci_supply_chain` — 反論
<sub>2026-08-24T12:26:18+09:00</sub>

# ci_supply_chain — Round 2（rebuttal）

## 1. `repo_hardening` の GitHub 設定項目を CI 知識で査定

### 1-A. 「`quality-checks` を required status check に登録」— **技術的に精度は正しいが、severity を格上げすべき**

- **check 名の指摘は正確**: `quality-checks.yml` の job 定義は `jobs: checks:`（`name:` オーバーライドなし）なので、GitHub 側に登録される check run 名は **`checks`**（workflow 名 `quality-checks` ではない）。`repo_hardening` の投稿はカッコ書きで既にこの区別をしており訂正不要。
- **fork PR での挙動**: `quality-checks.yml` は `pull_request`（非 `pull_request_target`）で fork PR にも到達するため、初回コントリビューターの実行承認さえ通れば check run `checks` は正常に生成される。required status check への登録自体は fork PR 経路と矛盾しない。
- 🔴 **格上げすべき点**: `repo_hardening` は「登録すると `automation/gem-pool-refresh` PR が永久 pending でマージ不能になる」ことを **注意書き**（"検討すること"）で済ませているが、これは仮定の話ではなく **確定した regression**。根拠: `gem-pool-refresh.yml` 自体のコメントに明記の通り、`GITHUB_TOKEN` 由来のイベントは新しい workflow run を作らない（GitHub 公式仕様）ため、この自動化 PR に対して `quality-checks.yml` の `pull_request` は **一度も発火しない** → check run `checks` は永久に「未報告」のまま。GitHub のルールセット `required_status_checks` は「未報告」を「pending」として扱い続け、タイムアウトで自動的に免除されることはない（GitHub Checks API の仕様）。つまり **この 1 行を有効化した瞬間、既存の自動反映フロー（週次・Issue #458/#482 で正式決定済み）が機能停止する**。
- **具体的な緩和策（`repo_hardening` の "検討すること" を実行可能な形に落とす）**:
  - (a) ルールセットの **bypass list** に、マージを実行する ID（Claude セッションが使う GitHub App/PAT、または "Repository admin" ロール）を追加する。ruleset の `bypass_actors` はブランチ名条件なしで全体に効くため、"このブランチだけ除外" はできない点に注意（ruleset のターゲットは push 先の `main` であり、PR の head ブランチ名では絞れない）。
  - (b) もしくは required status check 登録を **見送る**（現状維持）。
  - (a)/(b) いずれかを明示的に選んでから実行に移すべきで、「登録してから様子を見る」は不可（有効化した瞬間に壊れるため後戻りが必要になる）。
- **判定**: `repo_hardening` の技術的記述（check 名・fork PR 挙動）は正しい。ただし risk 表現は「検討事項」ではなく **「先に bypass 方針を確定しないと実装できない前提条件」** として最終手順書に明記すべき（ユーザーがコピペで実行した場合に自動化が壊れる実害が確定しているため）。

### 1-B. 「Workflow permissions を Read-only に」— **実害なし。CI 知識で裏付け確認**

- GitHub Actions の権限解決順序: リポジトリ既定の "Workflow permissions"（Read-only / Read-write）は、ワークフロー YAML が `permissions:` を **明示していない場合のフォールバック値** にすぎない。YAML 側で `permissions:` を宣言していれば、そちらが優先されリポジトリ既定を上書きする（GitHub 公式仕様。既定を絞っても明示宣言の上限を切り下げることはない）。
- 実際に確認済み: `quality-checks.yml` は `permissions: contents: read`（top-level）、`gem-pool-refresh.yml` は `permissions: contents: write / pull-requests: write`（top-level）を **両方とも明示宣言済み**。よって Workflow permissions を Read-only に変更しても **`gem-pool-refresh.yml` は壊れない**（`repo_hardening` の「実害は限定的」という表現は正確には「実害ゼロ」と言い切ってよい）。
- **格上げ提案**: この変更は 100% 安全なので、`repo_hardening` の優先度分類「推奨」から実装容易性の観点で「必須リストの直後にすぐ実行してよい低リスク項目」として案内してよい。

### 1-C. 「Allow GitHub Actions to create and approve pull requests」を OFF にした場合 — **`gem-pool-refresh.yml` が壊れる（ここは誰も OFF を推奨していないが、明示的な NG 事項として最終成果物に書くべき）**

- この設定は Settings → Actions → General の "Workflow permissions" セクション内にある **別のチェックボックス**（Read/Write のラジオボタンとは独立）。既定 OFF のリポジトリも多く、一般的な「GitHub Actions ハードニングチェックリスト」ではしばしば OFF 推奨として登場する。
- `gem-pool-refresh.yml` の最終ステップ（`Create or update pull request`）は `GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}` を使って `gh pr create` を実行している。この設定が OFF だと、`pull-requests: write` の permissions scope を宣言していても **`GITHUB_TOKEN` による PR 作成自体が 403 で拒否される**（scope の上限とは独立したリポジトリレベルのゲート）。
- 現状 `repo_hardening` の推奨リストにこの項目を OFF にする提案は **含まれていない**（確認済み・良い）。ただし一般的な「セキュリティ強化」の連想から、ユーザーやレビュアーが独自判断で OFF にしてしまうリスクがある。**最終成果物に「この設定は ON のまま維持すること（OFF にすると Gem 候補プールの週次自動反映 PR が作成できなくなる）」という明示的な NG 事項を 1 行追加することを提案する**。

## 2. `appsec_runtime` の CSP / セキュリティヘッダ指摘 — Cloudflare Workers + OpenNext 構成での実装可否

- **結論: 実装可能。ただし推奨実装面は `next.config.ts` の `headers()`（または `middleware.ts`）であり、`public/_headers` ファイルではない。**
- 根拠: `public/_headers` は **Cloudflare Pages 専用の規約**（静的アセット配信時にのみ Pages のルーティング層が解釈する）。本プロジェクトは `wrangler.jsonc` + `wrangler deploy` / `@opennextjs/cloudflare` で **Workers としてデプロイ**しており（`package.json` の `deploy` スクリプトが `wrangler deploy` を呼ぶ構成を確認済み）、Pages ではない。したがって `public/_headers` が存在しないことは「CSP 未設定の証拠」の一つとしては成立するが、**仮に追加してもこのデプロイ経路では効かない**（Workers のリクエストは Pages のアセットルーターを経由しない）。
- 正しい実装面: `next.config.ts` の `async headers()` はビルド時に Next.js のルーティングメタデータへ組み込まれ、OpenNext Cloudflare アダプタは Next.js のレスポンス生成パイプラインをそのまま Worker 上で実行するため、`headers()` で定義したレスポンスヘッダ（CSP・`X-Frame-Options`・`Referrer-Policy` 等）は Workers 環境でも問題なく付与される（OpenNext のドキュメント・アーキテクチャ上、`next.config.js` の `headers()`/`redirects()`/`rewrites()` は Cloudflare アダプタのサポート範囲内）。あるいはミドルウェア（`NextResponse.next()` の `.headers.set(...)`）でも同様に付与可能。
- **`appsec_runtime` の finding 自体（CSP 欠如は medium）は妥当・撤回不要**。実装ガイダンスとして「`next.config.ts` に `headers()` を追加する（`public/_headers` ではない）」という 1 行を最終成果物に添えることを提案する。

## 3. 自分の round 1 主張の concession

- **撤回**: round 1 の「[info] fork PR の Actions 実行承認要否」（`quality-checks.yml` に対する一般的な提案）は、`repo_hardening` の項目 5「"Require approval for all outside collaborators" を有効化」という同一対象への、より精密で実測に基づいた指摘と重複する。自分の記述（「Require approval for first-time contributors 以上」）は GitHub の実際の選択肢ラベルと微妙に異なり不正確なので **撤回し、`repo_hardening` の item 5 に一本化することを支持する**。
- **撤回しないもの**: 「ブランチ保護の要確認」という round 1 の申し送りは `repo_hardening` の実測（ルールセット `protect-main`・`required_status_checks` 不在）で解消済み・裏付けされたので、そのまま `repo_hardening` の item 1 に委ねる。「curl\|bash の `main` 参照（low）」は他レンズと重複がなく撤回不要。

## サマリー
- `repo_hardening` item 1（required status check 登録）: 技術的に正確だが、**bypass 方針を先に決めないと `gem-pool-refresh` 自動化 PR が永久マージ不能になる確定 regression** なので、最終手順の「必須」欄には前提条件（bypass_actors 設定 or 見送り）を明記すべき。
- `repo_hardening` item 5 前半（Workflow permissions read-only 化）: 両ワークフローとも `permissions:` を明示済みのため **実害ゼロ**、安全に実行可。
- 未言及の危険 NG 事項を追加提案: **「Allow GitHub Actions to create and approve pull requests」は ON のまま維持**（OFF にすると `gem-pool-refresh.yml` の PR 作成が壊れる）。
- `appsec_runtime` の CSP 指摘は妥当。実装面は `next.config.ts` `headers()`（`public/_headers` は Pages 専用で本構成には効かない点を最終成果物に反映）。
- 自分の round 1 の fork PR 承認要否コメントは `repo_hardening` item 5 に一本化し撤回。

### `appsec_runtime` — 反論
<sub>2026-08-24T12:26:27+09:00</sub>

## appsec_runtime — Round 2（rebuttal / concession）

### Q1: CSP/セキュリティヘッダ指摘（medium）の再評価 → **自主的に low へ格下げ**

「ソース公開で悪化するリスク」ではなく、大部分は**公開有無と無関係な一般的改善**だと判断する。
本アプリはソースの公開/非公開に関係なく常時インターネットへ露出する Web サービス（README でも
本番 URL を案内済み・`secrets_hunter` round1 記載の `kinamocchi-tech.workers.dev` の扱いと同じ論理）
であり、CSP/`X-Frame-Options` 欠如という状態そのものは公開前から存在していた。

公開によって **純増する分**は 1 点のみ: 攻撃者が `sanitize-html` の allowlist（許可タグ・属性・
スキーム）を黒箱推測ではなく `readme-html.ts` から正確に読めるため、バイパス探索の効率が上がる
（security-through-obscurity の喪失）。ただし allowlist 方式のサニタイザはソースが読めること自体を
前提に安全であるべき設計であり（Kerckhoffs の原則）、この増分は小さいと評価する。
→ **medium → low に自己格下げ**。指摘自体（Issue 起票が妥当という結論）は維持する。

### Q2: `RATE_LIMIT_SALT` フェイルオープン → **「公開が実害を増やす」という当初のフレーミングを撤回**

429 が出るかどうかは、稼働中のアプリへ実際にバーストリクエストを送れば誰でも黒箱的に検出できる
事実であり、ソースを読まなくても攻撃者は判明させられる。ソース公開が追加で明かすのは「なぜ
429 が出ないか」という**理由**（salt 未設定時のフェイルオープン設計）であって、「429 が出ない」
という**観測可能な事実**そのものではない。

→ 「公開したことで悪化するリスク」というカテゴリからは撤回する。round1 の指摘は
「運用監視の穴（アラート未整備）」という一般的な運用課題として残し、本議題（公開リスク）内での
優先度は round1 で既に low としていた通りで変更なし（格下げではなく、分類の訂正）。

### Q3: `repo_hardening` の設定項目への優先度付け（アプリ実行時レンズから）

**上げるべき**:
- **#4 CodeQL default setup**: 賛成・優先度を上げるべき。`dangerouslySetInnerHTML` + 自前
  `sanitize-html` 設定という高リスクパターンを持つコードベースであり、CodeQL の JS/TS XSS クエリは
  将来の allowlist 緩和・`parseStyleAttributes` 解除等のリグレッションを機械的に捕捉できる唯一の
  継続的防御線になる（人力レビューは今回 1 回限り）。
- **#1 required status check 化**: 賛成するが理由を具体化する。ブランチ保護一般ではなく、
  「`readme-html.ts` の allowlist/スキーム制限を検証するユニットテストが将来リグレッションしても、
  現状は CI 緑を人間の運用規律でしか確認しておらず機械的にマージを止める仕組みが無い」点が
  アプリ実行時セキュリティに直結する具体的理由。

**下げてよい**:
- **#9（Cloudflare `workers_dev`/`preview_urls` 露出、round1 で自分も言及した項目）**:
  自己レビューの結果、優先度は低のままでよいと判断する。`resolveLandingHost()` は受信 Host が
  `GITHUB_OAUTH_CALLBACK_URL` 由来の許可ホストと一致しない場合は一律その許可ホストへ
  フォールバックする設計（`src/composition/auth.ts:55-62`）であり、レート制限 binding も
  Worker 単位でドメインに依存しない。つまり workers.dev 経由でも本番と同じ保護がそのまま効き、
  **独立した新規の攻撃面にはなっていない**。露出面としては「入口が 1 つ増える」程度。
- **#7（個人アカウント 2FA/PAT 棚卸し）**: アプリ実行時への直接効果は間接的（アカウント乗っ取り
  後の問題は既に別カテゴリ）。GitHub 設定項目群の中では最低優先度でよい。

### Q4: `secrets_hunter` / `ci_supply_chain` の「問題なし」領域の見落とし

具体的に 1 点だけ挙げる。両者とも `wrangler.jsonc` の `ratelimits`（`60 req / 60s`、キー接頭辞
`search:` / `gems:`）と `limits.cpu_ms: 400` を秘密情報・サプライチェーンの対象外として扱っている
（妥当な判断）。公開によって攻撃者はこれらの**閾値を黒箱調査なしで正確に**知れるようにはなるが、
実害は限定的と判断し **新規指摘は起票しない**:
- 閾値を知ることは「閾値未満に留める」という合法的な使い方を助けるだけで、閾値超過を回避する
  バイパス手段を与えるものではない（レート制限は元々「知られてよい」性質の設定）。
- `gems:` 経路（Gem 一覧・CPU 重量エンドポイント）は独立したキー接頭辞でレート制限されており、
  際限ない連打はできない。

**未確認のまま申し送る点**（対象ファイル再読はしない、というラウンド制約のため round1 で
読んでいない）: `src/infrastructure/platform/cache-key.ts` / `cached-repository-query.ts` の
キャッシュキーがセッション状態（accessToken の有無）を含めているかは round1 で未確認。ただし
`GithubRepositoryQuery.search()` は常に `is:public` を強制するため、認証状態に関わらず返る内容は
常に公開リポジトリのみ（`github-repository-query.ts:29`）であり、たとえキャッシュキーが
セッション状態を無視していても **プライベート情報の漏洩には当たらない**と推測する（未検証）。
新規指摘としては起票しない。

### `repo_hardening` — 反論
<sub>2026-08-24T12:26:42+09:00</sub>

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

**訂正**: 私の Round 1 の指摘 5「Workflow permissions を Read-only に」は (a) だけを指すつもりだったが、同じ画面にあるため誤って (b) まで変更されるリスクがある。**(b) は現状 ON のはずで、変更禁止（touch しない）と明記する**よう Round 1 を修正する。

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
- 操作: "Workflow permissions" セクションの **ラジオボタン**を "Read repository contents permission" に変更
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
