# Cloudflare インフラ リサーチ（2026-08-18 JST）

- **目的**: [`infrastructure-design.md`](../../03_design/infrastructure/infrastructure-design.md) の `INF-n` 契約を **Cloudflare で満たせるか** を一次情報で検証する
- **調査方法**: 5 観点（ランタイム / CLI 運用 / コスト / キャッシュ・セキュリティ / アカウント運用）を並列調査し、Cloudflare 公式ドキュメント・npm registry・OpenNext 公式で裏取りした
- **位置づけ**: 🔴 **本書は「調査時点のスナップショット」であり設計の正本ではない**。設計の正本は [`cloudflare-infrastructure.md`](../../03_design/infrastructure/cloudflare-infrastructure.md)
- **数値の鮮度**: すべて 2026-08-18 取得。Cloudflare の料金・上限は変動するため、**実装時に再確認する**

---

## 0. 本書の読み方

各節の末尾に 🔵 **含意**（gem-hunter にとって何を意味するか）を置く。⚠️ は未確認事項（一次情報で確定できなかったもの）で、**断定に使わない**。

---

## 1. ランタイム: Next.js 16 を Cloudflare で動かす

### 1.1. 選択肢（結論: 1 つしかない）

| 選択肢 | 状態 |
|---|---|
| **`@opennextjs/cloudflare` + Workers** | 🟢 **公式推奨・唯一の現役経路**（[Cloudflare framework guide](https://developers.cloudflare.com/workers/framework-guides/web-apps/nextjs/)） |
| `@cloudflare/next-on-pages` + Pages | 🔴 **npm 上で deprecated**（「Please use the OpenNext adapter instead」）。最終リリース 1.13.16 / 2025-09-04 |
| 静的エクスポート + Workers Static Assets | 🟢 有効。サーバー実行がゼロになるが、**トークンをサーバーに隠せない**（`NFR-9` と衝突） |

⚠️ **「Cloudflare Pages が新規非推奨」という公式宣言は確認できなかった**。ただし [Pages → Workers 移行ガイド](https://developers.cloudflare.com/workers/static-assets/migration-guides/migrate-from-pages/)（最終更新 2026-08-14）が「Workers の方が機能が広い」と明記し、強い誘導がある。

### 1.2. `@opennextjs/cloudflare` の実測メタデータ

`npm view @opennextjs/cloudflare`（2026-08-18 実行）:

| 項目 | 値 |
|---|---|
| 最新版 | **1.20.2**（2026-07-21 公開） |
| peer `next` | **`>=15.5.21 <16 \|\| >=16.2.11`** |
| peer `wrangler` | `^4.86.0` |

🔴 **ドキュメントは「Next.js 16 の全 minor/patch に対応」と書くが、実 peerDep は `>=16.2.11`**。16.0〜16.2.10 は peer 警告になる。CHANGELOG によれば `16.2.3` 未満には CVE 修正が入っていないため、下限の切り上げは意図的。npm 最新の `next` は **16.3.1**（同日実測）なので、要件 `TR-1`（v16 以降）と矛盾しない。

### 1.3. 対応 / 非対応

| 機能 | 状態 |
|---|---|
| Server Components / Route Handlers / SSR / **streaming SSR** | 🟢 対応（`INF-7` / `INF-8` を満たす） |
| ISR / `revalidateTag` / `revalidatePath` | 🟢 対応（別途 tag cache 構成が要る・§4.3） |
| `use cache`（composable cache） | 🟢 Next 16 で対応 |
| Turbopack ビルド / OG image 生成 | 🟢 対応 |
| **Node.js Middleware**（Next 15.2+） | 🔴 **未対応**。検出するとビルドを早期エラーにする |
| **`proxy.ts`**（Next 16 で `middleware.ts` から改名・Node ランタイム固定） | ⚠️ **未確認**。関連 Issue は closed だが CHANGELOG に対応明記がない。**使わない設計で回避する** |
| グローバル DB クライアント（リクエスト跨ぎの接続保持） | 🔴 不可（`INF-13` と同じ制約） |

### 1.4. Workers ランタイムの上限

| 項目 | Free | Paid（$5/月〜） |
|---|---|---|
| **CPU 時間 / リクエスト** | 🔴 **10 ms** | 既定 30 秒・`limits.cpu_ms` で最大 5 分 |
| **Wall clock（実時間）** | **無制限**（クライアント接続中は上限なし・課金対象外） | 同左 |
| Worker サイズ（圧縮後） | 🔴 **3 MB** | 10 MB |
| メモリ | 128 MB | 128 MB |
| サブリクエスト / リクエスト | **50** | 10,000 |
| 静的アセット | 20,000 ファイル / 1 ファイル 25 MiB | 100,000 ファイル / 25 MiB |

出典: [Workers Limits](https://developers.cloudflare.com/workers/platform/limits/) / [Workers Pricing](https://developers.cloudflare.com/workers/platform/pricing/)

- **Web Crypto API は `nodejs_compat` なしで利用可能**（`INF-6` のセッション暗号化要件を満たす）
- `compatibility_date` が **2026-08-04 以降なら `nodejs_compat` / `nodejs_compat_v2` が既定で有効**
- `nodejs_compat` + compat date 2025-04-01 以降で、環境変数・シークレットが **`process.env` に自動注入** される（`INF-9` を満たす）
- ストリーミング中の Worker はアクティブなまま扱われ、wall time 制限がない（`INF-8` / `INF-12` を満たす）

🔵 **含意**: `INF-6`〜`INF-14` のうち **`INF-12`（10 秒以内に完結）は wall clock が無制限なので余裕で満たす**。一方 **`INF-6` の「Node.js 互換ランタイム」は CPU 10 ms（Free）という別軸の制約に化ける**。Cloudflare 自身が「SSR を扱う重めのワークロードは 10〜20 ms」と記載しており、**Free のまま SSR 主体で運用できる保証はない**。

---

## 2. CLI 運用（wrangler 一次経路）

### 2.1. wrangler の現行仕様

| 項目 | 値 |
|---|---|
| 最新版 | **4.123.0**（2026-08-18 実測） |
| Node 要件 | **`>=22.0.0`**（CI は `node-version: 22` 以上が必須） |
| 設定ファイル | **`wrangler.jsonc` が新規プロジェクトの推奨**（公式明記。一部の新機能は JSON 設定でのみ利用可） |

### 2.2. 非対話認証（エージェント運用の土台）

```bash
export CLOUDFLARE_API_TOKEN="<token>"
export CLOUDFLARE_ACCOUNT_ID="<32桁hex>"
npx wrangler whoami          # 疎通確認。ここが通れば以降すべて非対話
```

- `CLOUDFLARE_API_TOKEN` が設定されていると wrangler は **profile / OAuth を一切見ない**（公式明記）。`wrangler login` はブラウザ必須なので CI・エージェントでは使わない
- 併用する環境変数: `WRANGLER_SEND_METRICS=false` / `WRANGLER_SEND_ERROR_REPORTS=false`（**未設定だと初回に対話プロンプトが出て非 TTY で失敗する**）
- API レート制限: **1,200 リクエスト / 5 分**（ユーザー単位・ダッシュボード操作も合算）

### 2.3. 最小権限スコープ

Cloudflare が Workers Builds 用に自動生成するトークンの権限が事実上の公式リファレンス（[Builds Configuration](https://developers.cloudflare.com/workers/ci-cd/builds/configuration/)）。

| 区分 | 権限 | 何に要るか |
|---|---|---|
| Account | **Workers Scripts: Edit** | `deploy` / `versions upload` / `versions deploy` / `rollback` / `secret *` |
| Account | **Account Settings: Read** | account_id 解決・`whoami` |
| Account | Workers KV Storage: Edit | KV を使う場合 |
| Account | Workers R2 Storage: Edit | R2 を使う場合 |
| Account | D1: Edit | D1 を使う場合 |
| Zone | Workers Routes: Edit | 独自ドメイン / ルートを使う場合 |
| User | User Details: Read / Memberships: Read | `whoami`・所属解決 |

GUI テンプレート「**Edit Cloudflare Workers**」でも足りる。

### 2.4. トークン発行のニワトリ卵

- **1 本目だけは Dashboard での発行が必須**（公式: 「Before you can use the API, you need to generate an initial token via the Cloudflare dashboard」）
- 1 本目に `API Tokens Write`（user 所有）または `Account API Tokens: Edit` を付けておけば、**2 本目以降は `POST /user/tokens` / `POST /accounts/{id}/tokens` で発行・失効・ローテーションできる**
- `wrangler tokens create` は [未実装の feature request](https://github.com/cloudflare/workers-sdk/issues/13042)

### 2.5. プレビュー URL（`SD-1` の要）

2 種類ある。URL 形式は `<PREFIX|ALIAS>-<WORKER>.<SUBDOMAIN>.workers.dev`。

1. **Versioned Preview URL** — `wrangler versions upload` のたびに自動生成
2. **Aliased Preview URL** — `wrangler versions upload --preview-alias <alias>`（**wrangler 4.21.0+**）。ブランチ名を alias にすればコミットを重ねても URL が変わらない

🔴 **2025-09-17 以降 Preview URL は opt-in**。`preview_urls` の既定は `workers_dev` と同値なので、`workers_dev: false` にするなら `"preview_urls": true` の明示が要る。

CI での URL 機械取得は **`WRANGLER_OUTPUT_FILE_PATH`**（ND-JSON 出力・2025-11-03 追加）を使う。`version-upload` エントリに version ID とプレビュー URL が含まれると公式が明記している。
⚠️ **フィールド名（`preview_url` か `targets[]` か）は未確認**。初回実行時に実物を確認する。

### 2.6. Workers Builds（Git 連携ビルド）との比較

| | Workers Builds | GitHub Actions + wrangler |
|---|---|---|
| セットアップ | 🔴 **GitHub App のインストール = GUI 必須** | 環境変数 2 つを置くだけ |
| PR プレビュー | ブランチ alias を自動生成し PR にコメント（beta） | 自前で alias 指定 + コメント |
| エージェント適性 | ✕（初回接続が GUI） | 🟢 **完全 CLI** |
| 無料枠 | 3,000 分/月・同時 1 ビルド | GitHub Actions 側の枠 |

### 2.7. 非対話で詰まる箇所と回避フラグ

| 事象 | 回避 |
|---|---|
| 確認プロンプト | `--yes` / `-y`（`versions deploy` / `d1 execute`）・`--skip-confirmation`（`kv namespace delete`）・`--force`（`r2 object delete`） |
| テレメトリの初回プロンプト | `WRANGLER_SEND_METRICS=false` / `WRANGLER_SEND_ERROR_REPORTS=false` |
| Node 22 未満 | wrangler 4.123 が起動しない |
| `--temporary` トークン | 60 分以内に人間が claim URL を踏む必要があり **エージェント自律には不適** |

🔵 **含意**: `INF-20`（デプロイのトリガーは git push / マージのみ）と CLI 一次経路は両立する。**Workers Builds は採らず GitHub Actions + wrangler に一本化する** ことで、Cloudflare 側の GUI 作業を「トークン 1 本目」だけに圧縮できる。

---

## 3. コスト（`INF-2` の検証）

### 3.1. 無料枠と超過時の挙動

| 製品 | Free 枠 | 超過時 |
|---|---|---|
| **Workers** | 100,000 リクエスト/日・CPU 10 ms/invocation | 🟢 **HTTP Error 1027 で停止**（課金されない）。ルート設定で fail open / fail closed を選択可 |
| **Workers Static Assets** | 🟢 **無料・無制限**（ストレージ課金もなし） | — |
| **Workers KV** | 読 100,000/日・**書き 1,000/日**・1 GB | 該当操作がエラーで失敗 |
| **D1** | 読 500 万行/日・書き 10 万行/日・5 GB | API がエラーを返す |
| **R2** | 10 GB-月・Class A 100 万・Class B 1,000 万・**エグレス無料** | 🔴 **有効化に支払い方法の登録が必要**。超過時に Free 相当で停止するかは ⚠️ 未確認 |
| **Cloudflare Images** | 5,000 unique transformations/月 | 🟢 エラー（`9422`）を返し **課金されない** |
| **Workers Builds** | 3,000 分/月・同時 1 | — |
| **Workers Logs** | 200,000 events/日・**保持 3 日** | — |
| **Analytics Engine** | 100,000 データポイント/日・10,000 read query/日 | 公式に「currently, you will not be billed」 |

出典: [Workers Pricing](https://developers.cloudflare.com/workers/platform/pricing/) / [Static Assets Billing](https://developers.cloudflare.com/workers/static-assets/billing-and-limitations/) / [KV Pricing](https://developers.cloudflare.com/kv/platform/pricing/) / [D1 Pricing](https://developers.cloudflare.com/d1/platform/pricing/) / [R2 Pricing](https://developers.cloudflare.com/r2/pricing/) / [Images Pricing](https://developers.cloudflare.com/images/pricing/) / [Builds Limits](https://developers.cloudflare.com/workers/ci-cd/builds/limits-and-pricing/) / [Analytics Engine Pricing](https://developers.cloudflare.com/analytics/analytics-engine/pricing/)

### 3.2. 🔴 「キャッシュヒットでもリクエスト枠を消費する」

公式明記: **「Workers Caching を有効にした場合、Worker のキャッシュから返されたリクエストも、Worker を起動したリクエストと同じ per-request レートで課金される」**（CPU 時間はキャッシュミス時のみ）。

→ **「キャッシュすれば Workers の枠が減らない」は誤り**。枠を減らしたいなら静的アセット化する（静的アセットへのリクエストは無料・無制限）。

### 3.3. コスト暴走の防止

| 手段 | 実効性 |
|---|---|
| **Free plan のまま・支払い方法を登録しない** | 🟢 **最強のハードキャップ**。超過は課金ではなく停止 |
| Budget alerts（2026-04 提供開始・Pay-as-you-go で既定 ON・$10） | 🔴 **「informational only. They do not pause or cap usage」＝ 通知のみ**。⚠️ API からの設定可否は未確認 |
| `limits.cpu_ms`（wrangler.jsonc） | 🟢 公式が「runaway bills / denial-of-wallet 攻撃を防ぐため」と明記。**ただし防げるのは CPU 課金のみでリクエスト数は制限できない** |
| Billable Usage API（2026-08-03 公開） | `GET /accounts/{id}/billable-usage` で日次コストを製品別に取得。自前の閾値監視を組む唯一の programmatic 経路 |

**Spend limit（ハードキャップ）は AI Gateway 専用機能で、Workers 本体には存在しない。**

🔵 **含意**: `INF-2` §10.3 の「超過時は課金ではなく停止側に倒す」は、**Cloudflare では「Free plan のままにする」ことで構造的に満たせる**。Paid に上げた瞬間にこの性質は失われ、`limits.cpu_ms` と Billable Usage API による自作監視しか残らない。

---

## 4. キャッシュ（`NFR-17` Cache Port の実装先）

### 4.1. 🔴 Workers Caching が新しい推奨

2026 年に **Workers Caching**（`/workers/cache/`・Cache API とは別物の read-through キャッシュ）が登場し、公式が「**For new Workers, prefer Workers Caching**」と明記。Cache API は「lower-level primitive」に降格した（[Workers Caching limitations](https://developers.cloudflare.com/workers/cache/limitations/)）。

| 観点 | Workers Caching（新） | Cache API `caches.default` | Workers KV 直叩き |
|---|---|---|---|
| 範囲 | **2 層 tiered**（最初の 1 リクエストが upper tier を埋める＝実質グローバル） | 🔴 **per-colo のみ**（他データセンターに複製されない） | グローバル（結果整合・最大 60 秒） |
| TTL 制御 | `Cache-Control`（RFC 9111・`stale-while-revalidate` 可） | `Cache-Control` | `expirationTtl`（**最小 60 秒**） |
| **リクエスト合体** | 🟢 **あり**（同一キーの同時リクエストで Worker は 1 回だけ実行） | ✕ なし | ✕ なし |
| 課金 | HIT もリクエスト課金（CPU 課金なし） | Free は 50 calls/req（subrequest 枠と共有） | 書き **1,000/日**（Free） |
| 有効化 | `wrangler.jsonc` に `"cache": { "enabled": true }` | コードで `caches.default` | コードで実装 |

🔵 **含意**: `NFR-7`（request coalescing）は「サーバーレスではインスタンス内でしか効かない」と [`infrastructure-design.md`](../../03_design/infrastructure/infrastructure-design.md) §4 で **補助扱いに格下げされていた** が、**Workers Caching のリクエスト合体はエッジで効くため、この前提が変わる**。GitHub のレート枠（30 req/分）を守る打ち手として最も効く 1 行になる。

### 4.2. OpenNext の incremental cache

| バックエンド | 評価 |
|---|---|
| **R2**（`r2IncrementalCache`）+ `withRegionalCache` | 🟢 OpenNext 公式推奨 |
| **Workers KV** | 🔴 OpenNext 公式が明確に非推奨（「We do not recommend using KV because it is eventually consistent」） |
| Workers Static Assets | 読み取り専用（revalidation 不可） |

tag cache（`revalidateTag` 用）は `D1NextTagCache`（低トラフィック向け）または `DOShardedTagCache`（高トラフィック向け）。ISR の時間ベース revalidation では **cache purge が呼ばれない**（`revalidateTag` / `revalidatePath` を呼んだときだけ）。

### 4.3. Workers KV の数値（正本）

| 項目 | 値 |
|---|---|
| 書き込み反映 | 同一 colo は即時・**他地域は最大 60 秒** |
| `expirationTtl` 最小 | **60 秒** |
| `cacheTtl` | 最小 30 秒（2026-01-30 に 60→30 へ短縮）・既定 60 |
| 値サイズ / キーサイズ | 25 MiB / 512 bytes |
| 同一キーへの書き込み | **1 回/秒**・last write wins（楽観ロックなし） |

---

## 5. セキュリティ・プライバシー（`INF-1` / `D-14` の検証）

### 5.1. Cloudflare が自動記録するログ

| ログ種別 | 既定 | 保持期間 |
|---|---|---|
| **Workers Logs**（invocation + custom） | 🔴 **新規 Worker は既定で有効** | Free 3 日 / Paid 最大 7 日 |
| Security Analytics | 自動 | Free 7 日 |
| Security Events | 自動 | Free 24 時間 |
| Audit Logs（アカウント操作） | 自動 | **18 か月** |

- **無効化できる**: `"observability": { "enabled": false }`、または invocation ログだけ落とす `{ "logs": { "invocation_logs": false } }`
- ⚠️ **invocation log にクライアント IP が含まれるかは公式が列挙しておらず未確認**（「enriched with information available to Cloudflare in the context of the invocation」とのみ記載）

🔵 **含意**: [`infrastructure-design.md`](../../03_design/infrastructure/infrastructure-design.md) §5.3 が「事業者標準のアクセスログはアプリの制御外にある」と留保した唯一の領域について、**Cloudflare は invocation ログを設定で切れる**。§11 評価軸 6（ログの保持期間・無効化可否）に対する回答になる。

### 5.2. レート制限と「IP を保存しない」の両立

- **Workers Rate Limiting binding**（GA・2025-09-19・wrangler 4.36.0+）は `wrangler.jsonc` の宣言 3 行で使える。`period` は **10 秒か 60 秒のみ**、**per-colo**（公式が「permissive, eventually consistent」「正確な会計には使わない設計」と明記）
- `key` は任意文字列で **カウンタしか保持しない**。生 IP ではなく **サーバー保持の salt 付き HMAC-SHA256 で導出したハッシュ** を key にすれば、`INF-1`（個人情報を保持しない）と両立する
- WAF Rate limiting rules は **Free では 1 ルール・characteristic は IP 固定** で、ログイン有無による枠分け（`AR-5`）ができない
- ⚠️ Rate Limiting binding の課金の有無は公式ドキュメントに明記なし（未確認）

### 5.3. シークレット

| | `wrangler secret put`（Worker secrets） | Secrets Store（アカウント単位） |
|---|---|---|
| 状態 | 🟢 GA | ⚠️ **open beta**（2026-08 時点） |
| 参照 | `env.MY_SECRET`（同期） | `await env.MY_SECRET.get()`（非同期） |
| 権限 | Worker のデプロイ権限 | Super Administrator / Secrets Store Deployer ロールが必要 |

非対話投入は `printf '%s' "$VALUE" | npx wrangler secret put KEY` またはまとめて `wrangler secret bulk`。環境ごとの分離は `--env` で行う。

### 5.4. Bot Fight Mode

Free 向けのオプトイン機能で **既定オフ**。有効化すると **WAF custom rules の Skip でバイパスできず**、正当な API トラフィックがチャレンジされうると公式が明記している。

---

## 6. アカウント運用: 人間の作業を最小化する

### 6.1. 🔴 人間が Dashboard で必ず触る作業

| # | 作業 | 所要 | なぜ CLI で代替できないか |
|---|---|---|---|
| **H-1** | My Profile > API Tokens で **1 本目のトークンを作成** | 3 分 | `POST /user/tokens` には既存トークンが要る（ニワトリ卵）。公式が「初回は Dashboard で」と明記 |
| **H-2** | （Workers Builds を採る場合のみ）GitHub App のインストール承認 | 3 分 | GitHub 側の OAuth 同意フローで API 代行不可 |
| **H-3** | （独自ドメインを使う場合のみ）レジストラでネームサーバーを Cloudflare へ変更 | 10 分 + 伝播待ち | Cloudflare 外のレジストラ操作 |
| **H-4** | （Paid が必要になった場合のみ）Workers Paid への加入 | 3 分 | 支払い手段の登録はアカウント所有者の権限が物理的に必要（`A-6`） |

**H-1 さえ済めば、Worker 作成・デプロイ・プレビュー URL・KV/R2/D1 作成・シークレット投入・削除・2 本目以降のトークン発行はすべて非対話で自動化できる。**
⚠️ workers.dev サブドメインの **初期登録** は、初回 `wrangler deploy` の対話プロンプトで登録される経路しか確認できておらず、非 TTY で完結するかは未確認（Dashboard の Workers & Pages > Your subdomain でも設定可）。

### 6.2. 環境分離の公式パターン

| 方式 | 内容 | 向き |
|---|---|---|
| **`[env.*]`（Wrangler Environments）** | `<name>-<env>` という **別 Worker** が作られる。バインディング・vars は **継承されない**（env ごとに全記述） | 常設 staging |
| **versions & preview URLs** | Worker を増やさずに版を積む。`--preview-alias` で URL を安定させられる | 🟢 **PR ごとのプレビュー** |

Free の Worker 数上限は 100/アカウント。**PR プレビューを `[env.*]` で作ると Worker が増え続けるため、versions/preview-alias で回すのが正解**。

### 6.3. GitHub Actions からのデプロイ

`cloudflare/wrangler-action@v4` に `apiToken` / `accountId` を渡す。outputs に `deployment-url` がある。
🔴 **OIDC は 2026-08 時点で未対応**（[wrangler-action #402](https://github.com/cloudflare/wrangler-action/issues/402) は解決コメントなく closed）。**長期トークン + GitHub Secrets が唯一の公式経路** なので、TTL 付きトークンを API でローテーションするのが緩和策。

---

## 7. 実測（本セッションで自ら確認した事実・2026-08-18）

| 確認内容 | 結果 |
|---|---|
| `npm view wrangler version` | `4.123.0` |
| `npm view @opennextjs/cloudflare version` | `1.20.2` |
| `npm view next version` | `16.3.1` |
| `@opennextjs/cloudflare` の peerDependencies | `next: >=15.5.21 <16 \|\| >=16.2.11` / `wrangler: ^4.86.0` |
| クラウドセッションから `api.cloudflare.com` へ到達できるか | 🟢 到達可（未認証で HTTP 400 `Missing "Authorization" header`。プロキシ遮断ではない） |
| `npx wrangler@4.123.0 --version` の起動 | 🟢 起動し、プロキシ環境変数を自動認識する |

🔵 **含意**: **トークンさえセッション env に供給されれば、Claude Code のクラウドセッションから wrangler を非対話で実行できる**（`B` カテゴリの「ツール改修で自律化」ではなく、そのまま動く）。

---

## 8. 未確認事項の一覧（実装時に潰す）

| # | 未確認事項 | 潰し方 |
|---|---|---|
| 1 | `proxy.ts`（Next 16）が `@opennextjs/cloudflare` 1.20.2 で動くか | **使わない設計で回避**。必要になったら実機検証 |
| 2 | Next.js 16 App Router の実バンドルが Free の 3 MB（圧縮後）に収まるか | 実ビルドして計測（`SP-1`） |
| 3 | `WRANGLER_OUTPUT_FILE_PATH` の `version-upload` エントリの正確なフィールド名 | 初回 CI 実行で実物を確認 |
| 4 | Workers invocation log にクライアント IP が含まれるか | 含まれる前提で `invocation_logs: false` に倒す |
| 5 | Rate Limiting binding の課金有無 | 実装前に料金ページを再確認 |
| 6 | R2 無料枠超過時に停止するか課金されるか | R2 を使わない構成なら不要 |
| 7 | Budget alerts の API 経由設定可否 | Free 運用なら不要 |
| 8 | workers.dev サブドメインの初期登録を非対話で完結できるか | 初回デプロイ時に確認（失敗したら Dashboard で 1 回だけ設定） |

---

## 9. 参照

| ドキュメント | 関係 |
|---|---|
| [`cloudflare-infrastructure.md`](../../03_design/infrastructure/cloudflare-infrastructure.md) | 本調査を踏まえた **Cloudflare 前提の設計（正本）** |
| [`infrastructure-design.md`](../../03_design/infrastructure/infrastructure-design.md) | `INF-n` 契約の正本（事業者非依存） |
| [`prd.md`](../../02_requirements/prd.md) | 要件 ID の正本 |
