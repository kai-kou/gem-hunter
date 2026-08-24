<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: パブリック公開中の kai-kou/gem-hunter のセキュリティレビュー（リポジトリ内容 + GitHub 側設定）

- 議題ID: `public-repo-security-20260824`
- 論点: 本リポジトリは現在 public。① 公開してはいけない情報が入っていないか ② CI/CD・自動化の権限とサプライチェーンが公開前提で安全か ③ アプリ実行時のセキュリティ（OAuth/Cookie/レート制限/リダイレクト/CSP 等）④ GitHub 側で設定すべきハードニング（ブランチ保護・Secret scanning・Push protection・Dependabot・Actions 権限・fork PR の扱い等）を洗い、実際にリスクがある指摘だけを残す。最終成果物はユーザーが 1 手順ずつコピペで実行できる設定手順。
- 参加者: `secrets_hunter`, `ci_supply_chain`, `appsec_runtime`, `repo_hardening`
- 投稿数: 4
- 更新: 2026-08-24T12:23:38+09:00

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
