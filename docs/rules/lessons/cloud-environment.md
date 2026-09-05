# クラウド実行環境の障害カタログ（Warm 層）

> **読むタイミング**: 下記の症状を **実際に観測したとき** だけ Read する（Hot 層には索引 1 行のみ・#324）。
> いずれも「発生時にどう回避するか」の手順であり、平時に常駐させても判断に影響しない。
> ハーネス（`gh_shim.py` の stderr ガイダンス・`post-tool-use-failure.sh`・`session-start.sh` の truncate）が
> 一次検知を担うため、常駐は不要と判定した（Hot 層再棚卸し・#324）。

| 症状 | エントリ |
|------|---------|
| `git push` だけが 403 / 413 / 502 で失敗する | L-079 |
| バックグラウンドエージェントの push 結果が不明 | L-080 |
| `tool call could not be parsed (retry also failed)` | L-101 |
| `E2BIG: argument list too long` で全 Bash が停止 | L-106 |
| `gh` が 403 を返す（`[gh-shim]` ガイダンスが出る） | L-114 |
| スコープ外リポジトリへの `git clone` / `ls-remote` が 403、`add_repo` が無い | L-117 |
| OpenNext Cloudflare のプレビューでのみリダイレクト / パス解決が期待どおりにならない | L-129 |
| 本番デプロイ系コマンド（`wrangler deploy` 等）が `permissions.allow` 済みでも auto mode classifier にブロックされることがある（毎回ではない） | L-130 |
| Cloudflare API に `DELETE` で未知のサブリソース名を投げて 404 を確認しようとしたら、本番リソースが消えた | L-134 |
| 同趣旨の Stop 差し戻しが `~/.claude/...` と `.claude/hooks/...` の両方から二重に届く | L-155 |

---

## L-079: クラウド環境で git push が HTTP 403/413/502 で繰り返し失敗する

**症状**: `git push` だけが 403（権限）または 413/502（プロキシのサイズ制限）で失敗する
（pull/fetch/gh は動く）。クラウドのプロキシが書き込みをブロックするため。

**フォールバック順**: ① `mcp__github__push_files`（GitHub MCP）→
② `tools/github_push_helper.py`（GitHub Contents API で base64 PUT）。
ファイル単位 push なのでマージコミットは作れない点に注意。

**クロスリポ書き込み（別リポへの push）の注意（2026-06-30 実機検証）**: クラウドのプロキシは
**PAT 直叩き（埋め込みトークン git push / gh REST / urllib REST）を全拒否** し、**セッションの GitHub App 認証のみ許可** する。
別リポに書くには ① `add_repo` でそのリポをセッションスコープに追加 → ② **埋め込みトークンを使わないプレーン git push**
（プロキシが App 認証を注入）または **MCP `mcp__github__push_files`**。urllib+PAT 直叩きの自作同期スクリプトは
クラウドでは効かない。「403 = トークン権限不足」と即断せず、まず add_repo 漏れを疑う。

---

## L-080: バックグラウンドエージェントがサイレントに失敗し取りこぼす

**症状**: `run_in_background: true` で push 系タスクを委譲すると、エージェント失敗が
次セッションまで検知されない。
**対策**: push 委譲後は必ず `mcp__github__get_file_contents` / `list_commits` で結果を検証する。
push が重要ならフォアグラウンド実行する。

> 行動規範としての要点は `docs/rules/agent-team-summary.md`「バックグラウンドエージェント」節に
> 1 行で常駐済み（Hot 層の重複を解消・#324）。

---

## L-101: 「tool call could not be parsed (retry also failed)」でセッションが停止する

**パターン**: `The model's tool call could not be parsed (retry also failed).` で停止する。
大コンテキスト + 強い thinking で発生する Claude Code 側の既知事象。壊れた tool_use が履歴に残ると
自己回帰生成が模倣する（few-shot poisoning）ため、同一セッション内 retry は確定的に再失敗する。

**対策**:
```
✅ 発生時は retry せず /clear・新規セッションで回復（破損セッションは捨てる）
✅ 1ターンのツール呼び出しは8個以下に抑える
✅ 高負荷でない工程は軽量モデルに切り替える
❌ パースエラー後に同一セッションで retry を繰り返す（逆効果）
```

> 予防側（1 ターン 8 ツール以下）は `docs/rules/session-safety-rules.md` ルール 1 に常駐済み。
> 本エントリは **発生後の回復手順** を担当する。

---

## L-106: CLAUDE_ENV_FILE が resume 毎に肥大化し全 bash が E2BIG で停止する

**症状**: 長時間タスクで resume を繰り返した後、`echo hi` すら
`E2BIG: argument list too long, posix_spawn '/bin/bash'` で失敗し全 Bash ツールが停止する。
**根本原因**: SessionStart フックが env を毎回 truncate せず追記し、resume で数千行に肥大化する。

**対策**: `session-start.sh` 冒頭で `CLAUDE_ENV_FILE` を毎回 truncate する（**本ベース実装済み＝再発しない**）。
bash 停止中も MCP（GitHub 操作）・Write/Edit・コミットは `mcp__github__create_or_update_file` で代替可能。

---

## L-114: クラウドの gh 403 は「認証」ではなく「リポジトリの API attach」— gh を導入しても直らない

**症状**: クラウド実行環境（`CLAUDE_CODE_REMOTE=true`）で GitHub API 経路が 403 になる。
**可否は変動する**（06-30 #121 → 07-02 拡大 #133 → 07-13 文言変化 #227 → 07-14 repo REST が許可に転換 #254
→ **07-26 repo REST が再び 403 へ回帰 #338**）。2026-07-26 実測:

- ❌ **`gh` はそもそもプリインストールされていない**（公式仕様）。`apt install -y gh` で導入は可能だが、
  **導入しても repo スコープ REST が 403 なら何も解決しない**（＝ gh の導入を解決策として試さない）
- ✅ `gh api user`・`gh api rate_limit` は **200**（プロキシの認証注入は効いている）
- ❌ `gh api repos/{o}/{r}/...` は **403**「GitHub access is not enabled for this session.
  An org admin must connect the Claude GitHub App for this organization.」
- ❌ GraphQL は 403「only the pinned set of PR-review operations is served」
- ❌ `curl`/`urllib` 直叩きは `Authorization` 有無・`Bearer proxy-injected`・実 `GH_TOKEN` とも同一 403
  - 🔴 **2026-08-31 再検証で repo スコープ REST の直叩きは 200 へ回帰した**（`/repos/{o}/{r}`・`/pulls`・`/issues`・`/actions/runs`・`/commits/{sha}/check-runs`・`/check-runs/{id}/annotations`）。ただし `code-scanning/*` は 403 のまま（プロキシではなくトークン権限不足）。**可否は 1 か月に 5 回変わっており、直叩きを一次経路にしない**（一次経路は MCP のまま）。使うのは「MCP にツールが無い読み取り」に限り、使う前にその場で HTTP コードを計測する。実測表は `github-mcp-fallback-patterns.md` §1.1（#684 / PR #729）
- ✅ **MCP（`mcp__github__*`）と git 操作は生存**（どちらも API プロキシを通らない別系統）

**根本原因**: プロキシは GitHub API リクエストを **セッションに attach されたリポジトリに限定** する
（環境のネットワークアクセスレベルとは独立）。`access:"read"` の attach は git clone/fetch のみで
API アクセスは付かない。`add_repo(access:"push")` が公式の解決手段だが、auto mode classifier に
ブロックされることがある（07-26 実測）。

**対策（優先順）**: ① **MCP（`mcp__github__*`）を一次経路にする** ② git 操作は別系統で常時生存
（`git clone https://...`・`fetch/pull/push`）③ gh は当てにしない（シムは 403 → MCP ガイダンスの
発生器およびローカル互換として残す）。`gh auth status` は exit 0 でも失敗表示が出るため認証判定に使わない。
代替表・検証マトリクスの SSOT は `docs/rules/github-mcp-fallback-patterns.md`。
**判定基準**: 403 を見たら **`gh api user` を叩く** — 200 なら認証は正常で、原因は repo の attach 側。
「403 = トークン権限不足」「403 = gh 未導入」はいずれも誤診。`GH_TOKEN` を触っても直らない。

---

## L-117: タスク実行モードによっては `add_repo` 自体が提供されず、クロスリポ参照が git/MCP 双方で 403 になる

**症状**: GitHub Issue/PR 対応のリモートタスク実行モードに加え、**4 時間ごとの scheduled trigger
（本リポジトリの R-1）セッションでも同様** に `mcp__Claude_Code_Remote__add_repo` がツールリストに
存在しない（ToolSearch でもヒットしない・実機再検証 2026-08-07・Issue #443）。`add_repo` 不在は
「GitHub Issue/PR 起動」固有の制約ではなく、**インタラクティブな claude.ai/code Web セッション以外の
自動タスク実行モード全般** に及ぶと判断する。

スコープ外リポジトリへの到達可否は **読み取りと書き込みで挙動が異なりうる**:
- **読み取り専用 `git clone`**: 2026-08-07 実機再検証では、対象が **public** リポジトリ
  （`kai-kou/claude-code-repository-base`）への `git clone` が exit 0 で成功した。一方
  2026-06-30・07-01 の実機検証ではスコープ外リポジトリへの `git ls-remote` が一貫して 403 だった
  （対象リポジトリの public/private は当時の記録に明記されておらず、今回の成功例と同一条件の
  再現とは断定できない）。**「read は public なら通る」と一般化せず、都度 `git ls-remote`/
  `git clone --depth 1` で実際に確認してから可否を判定する**（`apply-base` 等のクロスリポ参照を
  前提とするスキルが「git clone は常に通る」と決め打ちすると、この揺れを踏む）。
- **書き込み `git push`**: 2026-08-07 実機再検証では public リポジトリへの push も 403 だった
  （プロキシが明示メッセージを返す:
  `access denied by the git proxy: <owner>/<repo> is not in this session's authorized repository set,
  so the proxy will not inject a credential for it. To fix, add the repository to the session's sources.`）。
  `mcp__github__*` 等の GitHub API 系ツールも、システムプロンプトの「Repository Scope」に列挙された
  リポジトリ以外には到達できない（API 呼び出し自体が拒否される）。

**`create_session` による子セッションでも回避できない（2026-08-08 実機検証・#449）**: 親セッションから
`mcp__Claude_Code_Remote__create_session` で子セッションを起こし、そこで `add_repo` → clone → push を
試させても、`add_repo` は分類器にブロックされ `git push --dry-run` は 403 を返した。**「無人セッションが
push できないなら、push できるセッションを自分で起こせばよい」という回避策は成立しない**。
ルーティンの `session_context.sources` は配列だが、`create_trigger` / `update_trigger` のどちらも
sources を設定できないため、MCP からルーティンに 2 つ目のリポジトリを足すこともできない。

**根本原因**: Anthropic は 2026-08-07 時点で、1 セッション/タスクに複数リポジトリを恒久的に紐付ける
公式機能を提供していない（`anthropics/claude-code` issue #23627 がオープンの feature request。
類似要望の #27934 は #23627 の重複としてクローズ済み）。
`add_repo` によるスコープ動的拡張は **インタラクティブな claude.ai/code Web セッション限定の機能** であり、
GitHub Issue/PR からの自動トリガー型タスクにも scheduled trigger タスクにも搭載されない。

**対策**:
- クロスリポ参照（`apply-base` での他リポジトリ取得・`publish-sync` での公開リポジトリ push 等）が
  必要な作業は、`add_repo` が使えるインタラクティブな claude.ai/code セッション（ユーザーが直接チャットで
  指示する通常のセッション）で実行する。
- 自動タスク実行モード（GitHub Issue/PR 対応・scheduled trigger のいずれも）で `git ls-remote`/`git clone`/
  `git push` がスコープ外リポジトリに対し 403 を返したら、GH_TOKEN・ネットワーク設定の問題と誤診断して
  リトライを繰り返さない。直ちに「このタスク実行モードでは未対応。通常の claude.ai/code セッションで
  再実行が必要」と判定し、その旨を Issue に記録する（A-6 ではなく、Anthropic 側の機能制約として報告する。
  scheduled trigger の場合はユーザーが直接見ていないため、チャット案内ではなく Issue 記録が必須）。
- **public リポジトリの読み取りだけなら通ることがある** ため、「add_repo 不在 = 完全に到達不能」と即断せず、
  push を試みるコマンド（`git push --dry-run` 等）で実際に確認してから「未対応」と判定する
  （読み取り可否だけで書き込み可否を推定しない）。
- 恒久的な複数リポジトリアクセスの公式機能がリリースされたら、本エントリとクロスリポ参照系スキルの
  前提を更新する（CP-2）。

---

## L-126: クラウドコンテナの Chromium は TLS 1.3 で必ず失敗する（Playwright で SPA を開けない）

**症状**: プリインストールされた Chromium を Playwright で起動して外部サイトへアクセスすると、**対象ドメインを問わず・プロキシ経由でも直接接続でも 100% 決定論的に** `net::ERR_CONNECTION_RESET`（稀に `ERR_CERT_DATE_INVALID`）で失敗する。`page.goto` が一度も成功しない。

**原因**: TLS 1.3 のハンドシェイク自体が通らない（CPU に `avx512_vnni` があり BoringSSL の AVX512 暗号パスに起因すると推測）。**証明書の信頼設定の問題ではない**（CA バンドルを NSS DB へ登録しても解決しない）。

**対策**: 起動時に TLS 1.2 へ固定する。**TLS 検証の無効化ではない** ため `/root/.ccr/README.md` の禁止事項に抵触しない。

```js
const browser = await chromium.launch({
  executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
  args: ['--ssl-version-max=tls1.2'],           // 🔴 この 1 行が無いと必ず失敗する
  proxy: process.env.HTTPS_PROXY ? { server: process.env.HTTPS_PROXY } : undefined,
})
```

**あわせて必要な環境知識**:

- Playwright は **グローバルに導入済み**（`playwright@1.56.1`）。`NODE_PATH=/opt/node22/lib/node_modules node script.js` とすれば `require('playwright')` が通る（`playwright install` は実行しない・`playwright-core` の追加インストールも不要）
- `networkidle` 待機は常時バックグラウンド通信があるサイト（`developer.apple.com` 等）でタイムアウトする。**`domcontentloaded` + 明示待機** に切り替えると安定する

**使いどころ**: `WebFetch` は JS レンダリング SPA（`m3.material.io` / `developer.apple.com` 等）の本文を取得できずタイトルだけ返す。一次情報の逐語確認が要るときは本手順で実ブラウザを使う（CP-2）。ヘルパー化は #86。

症状（`ERR_CONNECTION_RESET` の全滅）から原因（TLS 1.3）へ辿り着くのが難しく、証明書・プロキシ設定の調査に時間を溶かす。発生時にだけ必要な環境依存の障害カタログのため Warm 層に置く。

---

## L-127: OpenNext Cloudflare 上では `AsyncLocalStorage` の store が SSR レンダリング内部へ伝播しない（2026-08-19・`gem-hunter` `SP-5`）

**症状**: wrangler の `main` を自前エントリに差し替え、`node:async_hooks` の `AsyncLocalStorage` で Worker 側の状態（例: キャッシュ HIT/MISS）を Next.js の SSR レンダリング内部（composition root のコールバック等）へ運ぼうとすると、`getStore()` が **常に `undefined`** を返す。`wrangler dev --local` + スタブ API による実機検証で確認済み。

**原因**: `AsyncLocalStorage` の store は Worker エントリでは確立できるが、OpenNext 生成物が挟む非同期継続を越えて Next.js 内部の SSR レンダリングまで伝播しない。workerd の `nodejs_compat` の `AsyncLocalStorage` 実装が Next.js 内部の継続を計装できていない可能性が高いが **未確定**（原因の断定はしない）。

**対策**: Server Component の応答(SSR 応答)に動的な値を載せる目的でこの手法を採らない。動的ヘッダ・観測用の値が必要な場合は、Web 標準 `Response` を直接返せる **Route Handler** の応答で返す（Server Component は `Response` を経由せずレンダリングされるため、そもそも動的ヘッダを付与する手段がない）。

**保持理由**: OpenNext Cloudflare（Next.js 16 相当）特有の実行モデルの制約で、同種の「Worker 側の状態をレンダリング内部へ運びたい」設計を再び試みると同じ壁にぶつかる。詳細な検証過程は `gem-hunter` の [`content/discussions/sp5-cache-design-20260819/whiteboard.md`](../../../content/discussions/sp5-cache-design-20260819/whiteboard.md) と [ADR 0005 §2.3](../../adr/0005-cache-port-yagni-exception-and-ttl.md#23-観測経路の決定x-cache-status-をどこに付与するか) を参照。

---

## L-129: OpenNext Cloudflare のパス処理で踏んだ罠（redirects の path-to-regexp 検証 / 拡張子付きパスの 404・2026-08-19・`SP-2`〜`SP-3`）

> 同じ「OpenNext / Workers のパス処理」カテゴリの罠を 1 エントリにまとめる（引くときのキーワードが
> どちらも「パスが期待どおりに解決しない」で同じため・Issue #102 コメント）。

**症状 ①（`redirects()` の `destination` が 500 になる）**: `next.config` の `redirects()` に素の `:path` パラメータを
含む `destination` を書くと、**Cloudflare プレビューでのみ** 500 になる（ローカル `next start` は正常）。

**原因**: OpenNext のルーティング層が `redirects()` の `destination` を `path-to-regexp` の `compile()` に
**検証有効（`validate: true`）** で通すため、`:path` のようなパラメータがスラッシュを含む値を拒否する。
Next.js 本体は `compile()` を `{ validate: false }` で呼ぶため、ローカルでは再現しない。

**切り分け方**: `path-to-regexp` の `match()` → `compile()` を直接評価する小さいスクリプトを書き、実際に渡す
`destination` の値がラウンドトリップできるか（スラッシュ入りの値でも `compile()` が例外を投げないか）を確認する。

**対策**: `destination` 側にも `(.*)` 等のパターンを明示し、`:path` の受け取り側でスラッシュを許容する形にする
（PR #96 で適用済み・回帰テストあり）。

**症状 ②（拡張子付きパスの 404）**: ロケール接頭辞なしの共有 URL で、末尾セグメントが「アセットらしい拡張子」で
終わるパスの解決が拡張子によって割れる（`SP-3`・PR #106 のプレビュー実測・詳細は #97）。

| パス | 実測 |
|---|---|
| `/repos/foo/user.github.io` | 307（正しくリダイレクトされる） |
| `/repos/angular/angular.js` | **404** |
| `/ja/repos/angular/angular.js` | 200（ロケール付きなら正常） |

**原因（未確定）**: `.io` は通り `.js` は 404 になることから、**Worker より先に静的アセットハンドラがリクエストを
処理している** ことが原因と考えられる（一次情報での確認は #97 の残作業。断定はしない）。

**切り分け方**: ロケール接頭辞の有無・拡張子の有無を変えた組み合わせで実測し、どの条件で静的アセットハンドラに
奪われるかのパターンを特定する。

**保持理由**: OpenNext Cloudflare のルーティング層はローカル実行では再現しない罠を複数抱えており、
「プレビューでだけ壊れる」を見たら一次候補として本カテゴリを疑えるようにする。詳細は Issue #97 / #102、
症状 ① の修正は PR #96。

---

## L-130: 本番デプロイ（`wrangler deploy`）は auto mode classifier にブロックされることがある（非決定的・原因未確定・2026-08-20 初出 / 2026-08-21 訂正・Issue #288 / #300）

**症状**: `npm run deploy`（= `opennextjs-cloudflare build && wrangler deploy --tag "$(git rev-parse --short=12 HEAD)"`）が
`Permission for this action was denied by the Claude Code auto mode classifier. Reason: Blocked by classifier.`
で拒否されることがある。`.claude/settings.json` の `permissions.allow` に `Bash(npm run deploy:*)` /
`Bash(npx wrangler deploy:*)` を追加済みでもブロックは解けない。

🔴 **毎回ブロックされるわけではない**（初出時の「無人・有人を問わず 4 回すべて再現」という断定は 2026-08-21 に訂正した）。実測の内訳:

| 区分 | 回数 | 内訳 |
|---|---|---|
| ブロック | 5 回 | 2026-08-20 07:45 JST 無人ルーティン 3 回（複合 background / 単独 background / 単独 foreground）/ 2026-08-21 09:17 JST 頃 有人 1 回 / 2026-08-21 11:40 JST 無人 1 回 |
| **成功** | **2 回** | 2026-08-21 10:32 JST 無人ルーティン（Version `df728490-...` / tag `200743832fe6`）/ 2026-08-21 10:45 JST（tag `d9ab80106e59`） |
| **リトライで通過** | **1 回** | 2026-09-02 07:12 JST 無人ルーティン（`trigger_workers_build.py` の 1 回目がブロック → L-130 の指針どおり 1 回だけ再実行して通過。返り値は exit 2 ＝ build trigger 0 件・#809 レトロ） |

🔴 **ブロックは「終状態」ではなく「未判定」**（2026-09-02 追記）: 上表の 1 件は、ブロックのまま諦めていたら「classifier のせいでデプロイできない」と記録され、真因（build trigger 0 件・A-6）に到達しなかった。**ブロックされた時点で結論を書かない**（1 回だけリトライしてから判定する）。分岐の 3 状態化は Issue #785 で扱う。

同一コマンド・同一 `permissions.allow` 設定でも結果が割れており、**何が分かれ目かは未確定**。初回試行のエラー文言は
`Stage 2 classifier error - blocking based on stage 1 assessment` で **transient と明示** されていた。

**切り分け結果**:
- `npx opennextjs-cloudflare build` は単体実行では成功する（`.open-next/worker.js` の生成まで完了）。
  ブロック対象は **ビルドではなく `wrangler deploy`（本番反映そのもの）**
- `npx wrangler versions upload --preview-alias ...`（プレビュー反映）と `npx wrangler whoami` は成功する。
  wrangler バイナリ・Cloudflare API への到達・認証はブロック対象ではない
- `python3 tools/check_deploy_gate.py --json` はプロジェクト側のゲートであり、分類器のブロックとは独立に判定される
- **成功した実行も存在する**（上表の 2 回。Issue #263 のコメントと `tools/check_prod_drift.py` の出力で確認）

**一次情報（公式ドキュメント・2026-08-21 に `docs/en/auto-mode-config` / `docs/en/permission-modes` / `docs/en/errors` を全文確認）**:
- auto mode classifier は「`permissions` システムの後段で動く第二のゲート」
- 本番デプロイは分類器の組み込み `soft_deny` に含まれる。ただし `soft_deny` は `hard_deny` と違い
  "destructive actions that user intent can clear"（`allow` 例外や explicit user intent で解除され得る）
- **explicit user intent**: "if the user's message directly and specifically describes the exact action Claude is
  about to take, the classifier allows it… General requests don't count as explicit intent."
  → 「適切に対応して」のような一般的委任は要件を満たさない（**ユーザーのメッセージ** が対象で、Claude 自身の発話は対象外）
- **繰り返しブロックの閾値**: 3 回連続または通算 20 回で auto mode が一時停止する。🔴 **headless（無人）では
  プロンプトへフォールバックできないため、閾値に達したあとはアクションが実行されないまま静かに素通りする**（エラーにならない）
- 分類器は `autoMode` をプロジェクトの `.claude/settings.json` / `.claude/settings.local.json` からは **読まない**。
  読むのはユーザー設定 `~/.claude/settings.json`・managed settings・`--settings` のみ → 緩和は **A-6 相当**
- 分類器は **CLAUDE.md とドキュメントの文脈を読む**（"The classifier reads the same CLAUDE.md content Claude itself loads"）
- 分類器は **non-default branch のうち名前がデプロイ先を示すもの**（`production` / `release` / `gh-pages` 等）への
  push を、それ自体で本番デプロイとして独自に判定する
- 🔴 **未確認（一次情報で説明できない）**: 公式の decision order は「narrow な `Bash(...)` allow ルールは分類器より前段で
  即座に解決される」と述べ、本番デプロイをその例外とする記述は **どこにもない**。にもかかわらず narrow allow が
  ある状態でブロックされたという実測がある。バージョン差か未文書の例外かは断定できない
- 🔴 **未確認**: `Stage 2 classifier error` / `stage 1` という語は公式ドキュメントに存在しない。性質が最も近いのは
  「unparseable response」カテゴリで、**公式がリトライを推奨している**（"Retry the action; this usually succeeds on the next attempt."）

**対策（行動指針）**:
- 🔴 **回避しようとしてコマンドを分解しない**（`npm run deploy` を `opennextjs-cloudflare build && wrangler deploy` に
  割って個別実行する、別名スクリプト経由で `wrangler deploy` を呼ぶ等）。**分類器に気づかれないためにブランチ名を
  選ぶ**（デプロイを引き起こす push を無害そうな名前のブランチへ向ける）のも同性質の迂回であり採らない。
  分類器のブロックはバグではなく設計された保護
- **リトライは同一セッション内で 1 回まで**。transient（unparseable response）なら 1 回で通ることが多い。2 回目も
  ブロックされたら打ち切る。3 回目以降は根拠がないうえ、連続ブロックの閾値に達すると **headless では黙って
  何も実行されない状態** になるだけ
- **explicit user intent を人為的に作らない**。ユーザーが自分の言葉で `npm run deploy` を名指しした場合はそれが
  intent として働くが、それを言わせるために確認を装うのは筋が悪い
- 「マージ（`main` への反映）」と「本番デプロイ（`wrangler deploy` の実行）」を分離して扱う。マージ・push 自体は
  妨げられない。手順・乖離検知・恒久対策は
  `docs/03_design/infrastructure/cloudflare-infrastructure.md` §8.2.2 / §8.2.3 を参照
- **恒久対策は `D-31`（Workers Builds へ発火点を移す）+ `D-32`（移行後も `D-26` のデプロイゲートを Deploy command 内で維持する）**。分類器の非決定性に本番リリースの生命線を預けない
  （実測 7 試行中 5 ブロック）。移行後も本エントリは削除しない（制約自体は残るため）

**追記（2026-08-23 JST・Issue #451）: `D-31` 移行後も本エントリが解消しきらなかった理由**

`D-31` は「分類器がブロックしても Workers Builds が Git push を契機に自動デプロイするので影響しない」ことを狙ったが、実際には **デプロイゲート（`D-26`）で塞がれた push は Cloudflare 側でビルド失敗として記録されるだけで、ゲートが後から開いても自動では再試行されない**。直近 24 件のビルドは全件 `build_outcome: "fail"` で、本番を `main` HEAD に追いつかせていたのは Workers Builds ではなく、その都度セッションが打っていた手動 `npm run deploy`（＝分類器の管轄内）だった。つまり **救済経路として本エントリの制約（分類器ブロック）への依存が実運用で残り続けていた**。

**対策（実装後）**: `tools/trigger_workers_build.py` を追加し、デプロイゲート通過を検知したらこのスクリプトで Cloudflare Builds API を叩いて **再ビルドを明示的にトリガーする** 経路を一次にした（Cloudflare のビルド環境で `wrangler deploy` が走るため分類器の管轄外）。手動 `npm run deploy` はフォールバックとして残すが、一次経路ではなくなる。手順・API エンドポイントの正本は `docs/03_design/infrastructure/cloudflare-infrastructure.md` §8.2.3「移行後の実測」。

**保持理由**: 本番デプロイは `SD-1`（動作確認できる状態で終わる）と直結する重要な工程で、無人ルーティンで再現する。
ビルドまでは成功してログが緑に見えるため、「デプロイが成功したように見えて実は本番へ出ていない」誤認を招きやすい。
さらに **「必ずブロックされる」と思い込むと、実際には通る経路を最初から諦める**（試さずに保留する）判断を誘発する
ため、非決定性そのものを記録に残す。詳細は Issue #288 / #300 / #451、議論記録は
`content/discussions/prod-deploy-gate-20260821/whiteboard.md`。

**一般則（2026-09-02 追記・Issue #785）: `exit code` 軸と `実行可否` 軸は別軸である**

デプロイ系コマンド（`trigger_workers_build.py` / `npm run deploy` 等）を呼ぶスキルは、しばしば
「終了コード 0/1/2 で分岐する」ことだけを実装し、**ツール呼び出しそのものが auto mode classifier の
permission フェーズで止まり、コマンドが一切実行されず終了コードが返らない** という第 3 の状態を
分岐に持たない（本ファイルの上表「リトライで通過」の実測どおり、classifier ブロックはスクリプトの
`sys.exit()` を経由しないため exit code の 0/1/2 のどれにも該当しない）。

- **exit code 軸**（スクリプトが実際に走った場合の結果）: 0 = 成功 / 1 = 待機中・異常ではない /
  2 = 判定不能（fail-closed）— スクリプト内部の分岐であり `check_prod_drift.py` /
  `trigger_workers_build.py` の docstring が個別に定義する
- **実行可否軸**（そのツール呼び出しが実行されたかどうか）: 実行された（→ 上記 exit code 軸で分岐）/
  **実行がブロックされた**（`Permission for this action was denied by the Claude Code auto mode
  classifier.` のエラー文言で止まり、exit code が存在しない）

**デプロイ系コマンドを呼ぶ分岐を書く・レビューするときは、必ず両軸を独立に扱う**（exit code の分岐だけを
書いて「ブロックされたら exit code のどれかに丸め込まれるはず」と仮定しない。丸め込み先が無いため、
分岐から漏れた実行ブロックは無人 firing では静かに素通りする）。実行ブロックを検知したときの行動指針は
上記「対策（行動指針）」のリトライ規律（同一セッション内で 1 回まで）と同じであり、1 回リトライしても
なお実行不能なら「判定不能」ではなく「実行ブロック」として記録し区別する（原因が異なるため対策も異なる:
判定不能はスクリプト側のバグ・API 障害の疑いがあるが、実行ブロックは分類器設定の問題であり緩和は
ユーザーのアカウント権限が必要な A-6 相当）。実装例は `sprint-cycle-router` SKILL.md §1.5 手順 4 の
「実行ブロック」分岐。

## L-134: Cloudflare API に「未知のサブリソース名 + DELETE」を投げると親リソースが削除される（本番 Worker 誤削除・実測）

**症状**: 「preview alias / version を個別削除する API があるか」を実 API で裏取りする過程で、
存在しない末尾サブリソースを付けた `DELETE` を送った。

```
DELETE /accounts/{account_id}/workers/scripts/gem-hunter/totally-bogus-subresource
```

「存在しないルートなら 404 が返るはず」という前提で投げたところ、Cloudflare API は
**パス末尾の未知セグメントを黙って切り捨て**、`DELETE /accounts/{account_id}/workers/scripts/gem-hunter`
（Worker 本体の削除）として処理し `HTTP 200 / success: true` を返した。結果、本番 Worker・
version 165 件・preview alias 46 件・シークレット 4 件が全て消失した（Issue #613 / #615）。

**根本原因**: 「破壊的メソッドを本番リソースのパスに対して探索目的で送った」こと自体が誤り。
読み取り専用の調査（公式ドキュメント確認・`OPTIONS` での許可メソッド確認）で
「削除 API は存在しない」という結論は既に得られていたにもかかわらず、実 API での追加裏取りに
**取り消しのきかない `DELETE` を本番パスへ選んだ**。

**対策（行動指針・全プロジェクト共通）**:
- 未知のエンドポイント・サブリソースの存在を確かめたいときは、まず **`GET` / `OPTIONS`** など
  非破壊メソッドで確認する。`DELETE` / `PUT` / `PATCH` を探索に使わない
- どうしても破壊的メソッドで挙動を確認する必要があるなら、**実在しないダミーの識別子**
  （存在しない account_id・存在しないリソース名全体）に対して投げ、**本物の本番リソース名を
  パスに含めない**
- 「末尾に未知のセグメントを付ければ 404 になる」という前提を無検証で信じない。REST API の
  ルーティング実装によっては、末尾の未知セグメントが黙って無視され親リソースのハンドラへ
  フォールスルーすることがある（Cloudflare の Workers Scripts API で実測）
- 本プロジェクトでは `.claude/hooks/pre-cloudflare-destructive-check.sh` を PreToolUse に配線し、
  `DELETE` × `workers/scripts` パス・`wrangler delete` を機械的にブロックする（他プロジェクトへ
  展開する場合は対象 API・リソース名を読み替えて同様のガードを検討する）

**保持理由**: 本番停止に直結する不可逆操作で、複数プロジェクトの Cloudflare API 運用に
共通して当てはまる教訓（探索目的の破壊的メソッドを本番パスに使わない）。

## L-135: `PUT /pulls/{N}/merge`（REST）も GraphQL の `mergePullRequest` も、このセッション種別では 403 でブロックされる

**症状**: GitHub MCP（`mcp__github__*`）が一切ロードされないセッションで、代替として GitHub REST API
を直叩きして PR をマージしようとすると `403 Merging into a protected base branch is not permitted
for this session type.` が返る。GraphQL 経由（`mergePullRequest` mutation）も試すと `403 This GraphQL
query is not enabled for this session — only the pinned set of PR-review operations is served.` で
同様にブロックされる。`gh` CLI・シムも存在しない環境だった。

**根本原因（推測・一次情報未確認）**: protected branch へのマージは MCP の
`mcp__github__merge_pull_request`（Claude Code Remote が持つ追加チェック付きの経路）を通す設計で、
生トークンでの REST/GraphQL 直叩きは意図的にブロックされている。本セッションは GitHub MCP サーバー
自体が接続されていなかった（`ToolSearch` で `mcp__github__*` が一件もヒットしない）ため、マージだけ
がどの経路からも実行不能になった。Issue/PR 作成・コメント・レビュー投稿・CI 確認は同じ REST 直叩きで
問題なく成功した（マージだけが個別にブロックされている）。

**対策**: MCP の GitHub サーバーが未接続のまま作業を進めてしまった場合、実装・セルフレビュー・PR 作成
までは自律完了できるが、**最終マージだけはブロックされる可能性がある** と想定しておく。ブロックされたら
`gh` CLI 導入を試さない（L-114 と同じ理由でこの種の 403 は認証不足ではない）。PR を green・レビュー
済みの状態のまま残し、状況を正直に報告する（L-113: マージしていないのに「マージ済み」と書かない）。
MCP が接続されたセッション、または人間が GitHub UI から直接マージすることで解消する。

**保持理由**: L-113（捏造禁止）と直結する新規の環境制約。「PR は完成しているのにマージだけできない」
という状態を正しく報告できないと、虚偽の完了報告につながる。

## L-140: Workers Builds の build trigger が 0 件になると、デプロイ系スクリプト 2 本が別々の理由で「判定不能」になる（2026-08-30・Issue #626 / #693 / #694）

**症状**: 本番デプロイ関連の 2 スクリプトが、それぞれ別の顔をした失敗を返す。

```
$ python3 tools/check_prod_drift.py
ERROR: 判定不能: 本番デプロイ情報の取得に失敗しました
       （本番への実デプロイ実績（triggered_by=deployment）が見つかりません）   # exit 2

$ python3 tools/trigger_workers_build.py
ERROR: branch_includes に 'main' を含む trigger が見つかりません              # exit 2
```

前者は「デプロイ **履歴** が無い」、後者は「**branch 設定** のミス」に読める。**どちらも同じ一次事実（Cloudflare の build trigger が 0 件）の言い換えでしかない。**

**原因**: Workers Builds の GitHub 接続（Cloudflare GitHub App の認可）が外れると build trigger が消える。trigger が無いので `main` への push で自動ビルドが発火せず、deployment 由来のビルド実績も生まれない。**認証・アカウント ID・Worker 自体はすべて正常なまま** なので、トークン権限を疑う方向へ切り分けが逸れる。

**診断手順（原因まで 1 発で到達する）**: エラー文言から推測せず、**trigger の件数を直接数える**。

```python
# CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN はセッション env から取れる
scripts = fetch_worker_scripts(account_id, token)          # ここが通れば認証は正常
tag = worker_tag_from_scripts(scripts, "gem-hunter")       # ここが通れば Worker も正常
triggers = fetch_build_triggers(account_id, token, tag)    # ← 0 件ならこれが根本原因
```

段階的に切り分けると、どこまでが正常でどこから壊れているかが 1 回で確定する（実測: scripts 13 件 ✅ / worker tag ✅ / **trigger 0 件** 🔴 / build token 1 件 ✅）。

**復旧の可否**: 公式 API に `POST /accounts/{id}/builds/triggers`（trigger 作成）と `PUT /accounts/{id}/builds/repos/connections`（repo connection 作成）はある。ただし *"Before using the API, you must first install the Cloudflare GitHub App through the dashboard"* と明記されており、**GitHub App のインストール自体が外れていればダッシュボード操作（A-6）が必要**。build token は API で作成できない（ダッシュボードのみ）ので、**残っているうちは温存する**。

**暫定の回避経路**: trigger が復旧するまで、本番反映は `npm run deploy`（`wrangler deploy` 直実行）で継続できる（`pr-review-flow-summary.md` のフォールバック）。ただし L-130 のとおり auto mode classifier にブロックされることがある。

**保持理由**: この症状は #626 / #640 / #672 / #679 と **4 回起票されながら 3 週間以上原因未特定のまま** で、その間ずっと本番デプロイが止まっていた。エラー文言が根本原因の層を指していないため、毎回別方向の仮説から切り分けをやり直していたのが原因。恒久対策（メッセージ統一 = #693 / 判定不能の escalate = #694）が入るまでは、本エントリの診断手順が最短経路になる。

---

## L-155: CCR プラットフォーム側の Stop フックがプロジェクト側と同文の差し戻しを二重に届ける

> ベース（`claude-code-repository-base`）では base#543 の L-126 として収録されたが、本リポジトリの
> L-126 / L-127 は別の教訓に採番済みのため L-155 とした（番号だけがベースと異なる）。

**症状**: セッション終了時に「There are untracked files in the repository. Please commit and push …」が
`[~/.claude/stop-hook-git-check.sh]` と `[$CLAUDE_PROJECT_DIR/.claude/hooks/stop-router.sh]` の **2 系統** で届く。
クラウド実行環境（CCR）は `~/.claude/launcher-settings.json` の `hooks.Stop` に **独自の git チェック**
（未コミット / 未追跡 / 未 push / 未署名コミット）を登録しており、プロジェクト側 `stop-git-check.sh` と
役割が重複する。リポジトリからは変更できない（`~/.claude/` はコンテナ側）。

**含意**:

- 差し戻しの回数・文量はプロジェクト側だけでは制御しきれない。続行ターンで完了報告を再掲しない規律
  （`completion-report-rules.md` §1.2）が二重防御として必要な理由の 1 つ。
- プロジェクト側 `stop-git-check.sh` を削除して一本化しない: 残留ファイル判別（origin/main と同一内容の検知・
  重複コミット防止）はプラットフォーム側に無い。
- `~/.claude/` には Slack 発セッション限定の `stop-hook-reply-gate.py`（`CCR_REPLY_STOP_HOOK_REASON` 設定時のみ
  登録・Opus 系で terminal ツール未呼び出しなら最大 3 回 block）もある。Web セッションでは未登録
  （`env | grep CCR_REPLY` が空）。Slack 発セッションで「返信していない」差し戻しが繰り返されたらこれを疑う。

**判定基準**: 同趣旨の差し戻しが `~/.claude/...` と `.claude/hooks/...` の両方から届いても異常ではない。
どちらか 1 回分だけ対応し、報告は 1〜3 行に留める（`completion-report-rules.md` §1.2）。

**再発（2026-09-05・PR #949）— 抑止マーカーは片側にしか効かない**: 並行委譲中の WIP 自動コミットを止めるため
`bash tools/mutation_guard.sh begin` でマーカーを置いたが、抑止できたのは **プロジェクト側の `stop-router.sh` だけ** で、
`~/.claude/stop-hook-git-check.sh` は同じターンで差し戻しを続けた。マーカーの検査は `.claude/hooks/lib/wip_guard.sh`
（project 配下）にあり、グローバル側フックはそれを読まないため構造的に効かない。
**回避策**: 完了した役の担当ファイルだけを `git add <path>` で **パス指定コミット** し、作業中の役のファイルは残す
（作業ツリー全体の `git add -A` は他役の中間状態を巻き込む）。解決方針の検討は Issue #322 のコメントに記録済み。
