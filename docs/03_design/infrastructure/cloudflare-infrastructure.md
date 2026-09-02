# gem-hunter Cloudflare インフラ設計

- **版**: 1.0
- **作成日**: 2026-08-18 JST
- **状態**: 確定（`D-16` / `D-17` / `D-18` / `D-24`）
- **位置づけ**: **事業者を Cloudflare に確定したときの実装先の正本**。契約（`INF-n`）の正本は [`infrastructure-design.md`](./infrastructure-design.md) であり、本書はその契約を **Cloudflare のどの機能で満たすか** を定める
- **根拠**: ユーザー明示決定（2026-08-18・「インフラについて Cloudflare ベースで進めたい」「アカウントは既存のものを使う」「MCP よりも CLI を利用する方針で」）/ [Cloudflare インフラ リサーチ](../../01_research/infra/20260818-cloudflare-research.md)（一次情報）/ [専門チーム議論](../../../content/discussions/cloudflare-infra-20260818/whiteboard.md)

---

## 0. このドキュメントについて

### 0.1. 正本としての責務範囲

**同じ事実を 2 箇所に書かない。** 本書が正本を持つのは次の 4 つだけである。

| 本書が正本を持つもの |
|---|
| `INF-n` 契約 → Cloudflare 機能の対応表（§2.2） |
| Cloudflare 固有の構成（ランタイム・キャッシュ・環境分離・CI/CD・プライバシー設定） |
| CLI 一次運用の規約（非対話実行・MCP アローリスト・`INF-20` の例外） |
| Free / Paid の判定式と、人間に残る作業（§5.3・§11） |

以下は他が正本を持ち、本書は ID で参照する。

| 情報 | 正本 |
|---|---|
| インフラに求める契約（`INF-1`〜`INF-22`）・移行手順 | [`infrastructure-design.md`](./infrastructure-design.md) |
| 要件 ID・受け入れ条件 | [`prd.md`](../../02_requirements/prd.md) |
| 環境変数の一覧 | [`prd.md`](../../02_requirements/prd.md) §10 |
| 各決定の理由・経緯 | [`open-questions.md`](../../02_requirements/open-questions.md) の `D-n` |
| Cloudflare の数値（無料枠・上限・料金） | [リサーチ](../../01_research/infra/20260818-cloudflare-research.md)（**変動するので実装時に再確認する**） |
| 選定判断の記録 | [ADR 0002](../../adr/0002-cloudflare-workers-infrastructure.md) |

### 0.2. 🔴 数値をここに書き写さない

Cloudflare の無料枠・上限・料金は変動する。本書は **判断に必要な最小限だけを引用し、根拠はリサーチの節番号で参照する**。数値を疑ったらリサーチではなく [Cloudflare 公式](https://developers.cloudflare.com/workers/platform/pricing/) を見る。

---

## 1. 決定サマリー

| ID | 決定 |
|---|---|
| **`D-16`** | デプロイ先を **プレビュー・本番とも Cloudflare Workers** に確定する（`D-7` / `D-11` をクローズ） |
| **`D-17`** | ランタイムは **`@opennextjs/cloudflare` アダプタ**。`next` は **16.2.11 以上** にピンする |
| **`D-18`** | MVP のキャッシュは永続ストア（R2 / D1 / DO / KV）を採用しない。🔴 **L2 の実装方式は `D-24`（2026-08-19）で改訂済み**（§4.2 参照）: 当初案の「HTTP `Cache-Control` + Workers Caching のみ」は撤回し、**アプリ内 `CachePort` の実装（`InMemoryCache`）が主役** |

あわせて運用方針を 2 つ確定する。

- **CLI（wrangler）が一次経路**。Cloudflare MCP は読み取り 4 ツールのみ（§7.4）
- 🔵 **CI/CD は 2 レーンに分かれる**（2026-08-24 現在）。**品質チェック**（Prettier / ESLint / `tsc --noEmit` / Vitest）は GitHub Actions の `.github/workflows/quality-checks.yml` が `push`（`main`）/ `pull_request` 契機で自動実行する（`D-42`）。**デプロイ** の発火点は **Workers Builds**（`D-31` / `D-32`・§8.2.3）であり、**GitHub Actions は使わない**。セッション（Claude）による `wrangler` 直接実行は、Workers Builds 移行後も **手動フォールバック**（プレビュー URL の取得・デプロイゲート通過後の再デプロイ）として残す（詳細は §8）

---

## 2. 構成

### 2.1. 物理構成

```mermaid
flowchart TB
    B["ブラウザ<br/>URL / Cookie / localStorage に状態を持つ"]

    subgraph CF["Cloudflare"]
        SA["Workers Static Assets<br/>JS / CSS / フォント（無料・無制限）"]
        WC["Workers Caching<br/>Cache-Control に従うエッジキャッシュ<br/>リクエスト合体あり"]
        W["Worker（@opennextjs/cloudflare）<br/>Server Components / Route Handlers"]
        RL["Rate Limiting binding<br/>key = HMAC(IP)"]
    end

    G["GitHub API<br/>search / repos"]
    O["GitHub OAuth<br/>（任意ログイン・AR-5）"]

    B --> SA
    B --> WC
    WC -->|MISS| W
    W --> RL
    W --> G
    W --> O

    classDef none fill:#fff,stroke-dasharray: 4 3
```

🔴 **この図にも「データベース」が存在しない**（`D-5` 追補を維持）。Worker はリクエストを処理して捨てるだけで、次のリクエストへ持ち越す状態を持たない。エッジキャッシュは TTL 付きの揮発層であって永続ストアではない。

### 2.2. `INF-n` 契約 → Cloudflare 機能の対応

| 契約 | Cloudflare での満たし方 | 判定 |
|---|---|---|
| `INF-6` Node.js 互換ランタイム・Web Crypto | `compatibility_date` を 2026-08-04 以降にすると `nodejs_compat` が既定で有効。Web Crypto は互換フラグなしで利用可 | ✅ |
| `INF-7` リクエスト単位のサーバー実行 | Worker が Server Components / Route Handlers を実行する | ✅ |
| `INF-8` レスポンスストリーミング | 対応。ストリーミング中の Worker はアクティブ扱いで wall time 制限がない | ✅ |
| `INF-9` 環境変数のランタイム注入 | シークレット・変数が `process.env` に自動注入される（再ビルド不要） | ✅ |
| `INF-10` CDN 配信・`immutable` ヘッダ | Workers Static Assets。**リクエストは無料・無制限** | ✅ |
| `INF-11` 画像配信 | 🔵 **`next/image` の最適化を使わない**（§3.2）。GitHub のアバターは `avatars.githubusercontent.com?s=N` をそのまま使う | ⚠️ 方針は確定・**`NFR-6`（CLS）を満たすかは実測待ち**（§12 の 8） |
| `INF-12` 1 リクエスト 10 秒以内 | wall clock は無制限・課金対象外。GitHub API の待ち時間は CPU を消費しない | ✅ 余裕 |
| `INF-13` 永続ディスクを前提にしない | サーバーレスなので構造的に満たす | ✅ |
| `INF-14` 単一リージョンで成立 | エッジ実行だが、アプリはどこで動いても同じ（リージョン固有の前提を持たない） | ✅ |
| `INF-15`〜`INF-19` シークレット | `wrangler versions secret put`（GA・§7.2.1）を環境ごとに使う。Secrets Store は open beta のため採用しない | ✅ |
| `INF-20` トリガーは git push / マージのみ | 発火点は **Workers Builds**（`D-31` / `D-32`・§8.2.3）。⚠️ **移行が完全に回りきるまでの間、および完了後も手動フォールバックとして** セッションの `wrangler` 直接実行を許容する（§7.5 / §8.2）。🔵 `D-42`（品質チェックの Actions 化）は **本行の緩和条件に影響しない** | ⚠️ 暫定緩和中（フォールバック経路を保持） |
| `INF-21` ロールバック | `wrangler rollback` / `wrangler versions deploy` | ✅ |
| `INF-22` 失敗の通知 | GitHub Actions の失敗通知 | ✅ |
| `INF-1` 個人情報を保持しない | §9 の設定で満たす。⚠️ アカウント運用ログ（Audit 18 か月等）はアプリの制御外 | ⚠️ 一部のみ |
| `INF-2` 定常コストをゼロに | Free plan を維持する限り超過は課金ではなく停止（§5） | ⚠️ 実測待ち |
| `INF-3` 与件の技術スタック | Next.js 16 App Router が動く。⚠️ Free の CPU / バンドル上限に収まるかは実測待ち（§5.3） | ⚠️ 実測待ち |
| `INF-4` 人手の定常運用ゼロ | ブートストラップ以外の定常作業はゼロ（**トークンに TTL を設定しない** ことが条件・§11.3） | ✅ 条件付き |
| `INF-5` 事業者を決め打たない | §10 の境界（`src/infrastructure/platform/` 限定 + grep 2 本）で機械的に守る | ✅ |

---

## 3. ランタイム（`D-17`）

### 3.1. 採用するもの

| 項目 | 値 | 理由 |
|---|---|---|
| アダプタ | `@opennextjs/cloudflare` | Cloudflare 公式の唯一の推奨経路。`@cloudflare/next-on-pages` は npm 上で deprecated |
| `next` | **16.2.11 以上にピン** | アダプタ 1.20.2 の peer 依存が `>=16.2.11`。16.2.3 未満は CVE 未修正 |
| `wrangler` | `^4.86.0` 以上（実装時の最新） | アダプタの peer 依存 |
| Node（開発・CI） | **22 以上** | wrangler 4.x の `engines` 要件 |
| `compatibility_date` | 2026-08-04 以降 | この日付以降は `nodejs_compat` が既定で有効になる |

### 3.2. 🔴 使わないもの（地雷を踏まない設計）

| 使わない | 理由 | 代わりに |
|---|---|---|
| **Node.js Middleware** | アダプタが未対応で、検出するとビルドを早期エラーにする | 使わない |
| **`proxy.ts`**（Next 16 で `middleware.ts` から改名） | ✅ **不採用を確定（2026-08-19）**: Next.js 16 で Proxy は Node.js ランタイム固定になり、`runtime` config を Proxy 側で指定するとビルドエラーになる（`node_modules/next/dist/docs/01-app/03-api-reference/03-file-conventions/proxy.md` "Runtime" 節）。かつ `@opennextjs/cloudflare`（Edge 実行）は Node.js middleware を検出すると `process.exit(1)` で早期エラーにし `.open-next/worker.js` を生成しない（`node_modules/@opennextjs/cloudflare/dist/cli/build/build.js` 65-68 行目）。公式ドキュメントも単純なリダイレクトは `next.config.ts` の `redirects` を優先する旨を明記（`node_modules/next/dist/docs/01-app/01-getting-started/16-proxy.md` 27 行目） | `next.config.ts` の `redirects()` で `/` → `/ja`、ロケール接頭辞なしパス → `/ja/:path` へ既定ロケール固定リダイレクトする（`accept-language` の検出は行わない）。実装は `next.config.ts` |
| `next/image` の最適化 | Cloudflare Images は月 5,000 変換の無料枠があるが、検索結果の大量アバターで unique 変換が膨らむ | GitHub のアバター URL のサイズパラメータ（`?s=N`）をそのまま使う（`INF-11`） |
| Secrets Store | open beta で Super Administrator ロールを要求する | `wrangler versions secret put`（GA・§7.2.1） |
| Bot Fight Mode | 有効化すると WAF の Skip が効かず正当な API リクエストがチャレンジされうる | 有効化しない（Rate Limiting binding で足りる） |

> 🔵 **i18n（`E-4` / `SP-2`）への含意**: ✅ **決定済み（2026-08-19）**: `/` → `/ja` のリダイレクトは **middleware（`proxy.ts`）で実装せず** `next.config.ts` の `redirects()` で行う（上表の根拠）。`next-intl` は **不採用に決定** し、依存を増やさない自前実装（`src/domain/model/locale.ts` のロケール定義 + `src/shared/i18n/messages.ts` のメッセージカタログ）でメッセージ管理を行う。詳細は [PRD §13](../../02_requirements/prd.md#13-未決事項実装着手時に決定する)。

### 3.3. `wrangler.jsonc`（出発点）

```jsonc
{
  "$schema": "./node_modules/wrangler/config-schema.json",
  "name": "gem-hunter",
  "main": ".open-next/worker.js",
  "compatibility_date": "2026-08-04",
  "assets": { "directory": ".open-next/assets", "binding": "ASSETS" },
  "workers_dev": true,
  "preview_urls": true,
  "cache": { "enabled": true },
  "observability": { "enabled": true, "logs": { "invocation_logs": false } },
  "limits": { "cpu_ms": 400 },
  "ratelimits": [
    { "name": "RATE_LIMITER", "namespace_id": "1001", "simple": { "limit": 60, "period": 60 } }
  ]
}
```

- `preview_urls` は 2025-09-17 以降 opt-in。`workers_dev` を切るなら明示が必要
- `limits.cpu_ms` は Free では意味を持たないが、**Paid へ上げた瞬間に denial-of-wallet 対策として効く** ため最初から書いておく
- 🔴 **値は `SP-18`（#388）で 50 → 200 へ引き上げた**（`D-38` の `SP-18` 実測追記が正本）。理由は `D-38` のシャード配信で cold start の CPU が **約 81ms**（`JSON.parse` 39.9ms + `Map` 構築 40.7ms・ローカル実測）に達し、暫定 50ms では超過しうるため。超過時は **Error 1102**（`Worker exceeded resource limits` / invocation outcome `exceededCpu`）になる（1027 は Free の使用量到達による停止で Paid では出ない）。⚠️ Workers 上の p95 は未測定で、軽量アセット化（Issue #434）で締め直せる見込みがある
- 🔴 **さらに `SP-19`（#389）で 200 → 400 へ引き上げた**（`D-38` の `SP-19` 実測追記が正本）。Gem 一覧は所属判定用の `Map` だけでなく **全レコード + 照合用トークン列** を同じ 1 回の parse から作るため、**一覧の初回リクエストが 237〜277ms**（ローカル実測・別プロセス 5 回）に達し 200ms では **Error 1102** になる。🔵 一覧専用のコスト（トークン計算 約 91ms + 並べ替え 約 31ms）は初回の一覧リクエストまで遅延させてあり、`SP-18` で出荷済みのバッジ経路（`lookup` のみ）は **96〜110ms**（`SP-18` 実装の同条件 84〜90ms に対し +約 14ms）に留まる。🔴 **400 にした理由**: 観測した最大は 277ms で、300 では余裕が約 8% しか残らない。Workers 実機の p95 が未測定（`wrangler tail` がプロキシを通らない）である以上そこが枯れる保証がないため、**実測最大に対して約 44% の余裕** を取って Error 1102 を潰す側に倒した。🔵 `limits.cpu_ms` は **上限のキャップであって予約ではない**（課金は実使用 CPU に対して起きる）ので、上げても平常時のコストは増えない
- `ratelimits` は **`wrangler.jsonc` の宣言だけで有効になる**（事前のリソース作成コマンドは不要）。`namespace_id` はアカウント内で一意な任意の識別子、`period` は **10 秒か 60 秒のみ**。⚠️ wrangler 4.36.0 以上が必要
- ⚠️ `wrangler deploy` は設定ファイルを source of truth として扱う。**Dashboard で変えた設定は次回デプロイで巻き戻る**

🔴 **binding は宣言だけでは呼ばれない。実際に `limit()` を呼ぶ配線がある**（Issue #122・実装済み）。

| 役割 | ファイル |
|---|---|
| composition root（唯一の呼び出し口） | `src/composition/rate-limit.ts` の `enforceSearchRateLimit(headers)` / `enforceGemListRateLimit(headers)`（内部で共通の間引き処理にキー接頭辞を渡す） |
| binding 取得 | `src/infrastructure/platform/cloudflare-bindings.ts` の `rateLimiterBinding()`（`getCloudflareContext()` を動的 import。Workers 実行環境の外（`npm test` / `next dev`）では `undefined`） |
| binding ラッパー（`RateLimitPort` 実装） | `src/infrastructure/platform/rate-limit.ts` の `WorkersRateLimit` |
| key 生成 | `src/infrastructure/platform/rate-limit-key.ts` の `clientIpOf()`（`cf-connecting-ip` → `x-forwarded-for` 先頭の順で解決）と `hashRateLimitKey()`（§9.1 の HMAC 化） |

#### 適用経路（正本）

🔴 **本表が正本**。新しいエントリポイントを追加したらこの表にも行を足すこと（`tools/check_rate_limit_wiring.py` が機械検査する）。

<!-- rate-limit-wiring:begin -->

| 経路 | ファイル | レート制限 | キー接頭辞 |
|---|---|---|---|
| 検索画面（`prepareSearchKeyword` 経由） | `app/[locale]/page.tsx` | ✅ 適用 | `search:` |
| 検索 API（`prepareSearchKeyword` 経由） | `app/api/search/route.ts` | ✅ 適用 | `search:` |
| Gem 一覧 | `app/[locale]/gems/page.tsx` | ✅ 適用 | `gems:` |
| リポジトリ詳細（`fetchRepositoryDetail` 経由） | `app/[locale]/repos/[owner]/[repo]/page.tsx` | ✅ 適用 | `detail:` |
| OG 画像 | `app/[locale]/opengraph-image.tsx` | ❌ 対象外 | — |
| ログイン | `app/api/auth/login/route.ts` | ❌ 対象外 | — |
| 認証コールバック | `app/api/auth/callback/route.ts` | ❌ 対象外 | — |
| ログアウト | `app/api/auth/logout/route.ts` | ❌ 対象外 | — |

<!-- rate-limit-wiring:end -->

**❌ 対象外にした理由**（判断を再現できるように残す）:

- **ログイン / 認証コールバック / ログアウト**: OAuth のリダイレクトと Cookie 操作だけで、上流 API の重い呼び出しも重い CPU 処理も持たない。むしろ間引くと正規のログイン導線を壊す側のリスクが大きい
- **OG 画像**: 背景画像は `tools/ui-assets/build_data_uri_module.mjs` がビルド時に base64 データ URI の TS モジュールへ変換してバンドルへ埋め込んでおり、**実行時の I/O が無い**（実行時 `readFile` は Workers 上で 500 になるため不採用・Issue #347）。さらに `params` しか使わず `headers()` / `cookies()` 等のリクエスト時 API を使わないため、**ビルド時に静的最適化される**（= リクエストごとに Worker を起動しない）。🔴 **この判断は現在の実装に依存している**: リクエスト時 API の導入など静的最適化が崩れる変更を入れたら、間引きの要否をここで見直すこと

#### リポジトリ詳細を独立枠にした理由（`detail:`・Issue #190）

**リポジトリ詳細** は当初（#122）❌ 対象外だった。**平常時のトラフィックでは** GitHub Core 枠が 5,000 req/h あり、ここがボトルネックにならないという判断（`SP-19` の追加でもこの判断は変えていなかった）だが、🔴 **枠の枯渇攻撃には無防備な残存リスクとして受容している状態のままだった**: 未ログインの `/{locale}/repos/{owner}/{repo}` は **全ユーザー共有の installation token** を使うため、存在しない `owner/repo` をランダム生成して叩き続けられるとキャッシュが毎回ミスし、詳細取得（+ README）で 1〜2 コールが上流へ飛ぶ。毎秒 1 リクエスト程度でも 1 時間以内に Core 枠を使い切り、以後は **正規の利用者全員が `rateLimitPrimary`**（検索・詳細とも利用不能）になる。Issue #190 でこの残存リスクへ対応し、`✅ 適用` へ切り替えた。

**検索と枠を共有せず独立させる**（キー接頭辞 `detail:`）のは、`enforceGemListRateLimit` が `gems:` を独立させたのと同じ判断（経路ごとに独立した枠を割り当てる）を踏襲したため。詳細取得も検索と同じく上流 GitHub API の枠を消費する点では性質が同じだが、失敗シナリオ（owner/repo を変えながら詳細ページを連打）は検索とは独立に起こりうる。枠を共有すると、検索を一切していない利用者の詳細連打だけで枠が枯れたときに検索側まで巻き込まれ、逆に検索側の消費で「検索して詳細を開く」という正常な導線が早く枯れる可能性がある。

#### Gem 一覧を独立枠にした理由（`gems:`・Issue #442）

`SP-19` で追加した Gem 一覧（`/{locale}/gems`）は、**本数を絞る仕組みが 1 つも無い唯一の重量経路** だった。

- `limits.cpu_ms: 400` は **1 リクエストあたりの CPU 時間の天井であって、リクエスト本数を制限しない**（本数が増えれば CPU の総量はそのまま増える）
- Gem 一覧は GitHub API を叩かないため、**上流の 403/429 という壁にも間接的に守られない**（検索経路はそこに守られている）
- 実測 CPU は **cold 237〜277ms / warm 8〜12ms**（[`open-questions.md`](../../02_requirements/open-questions.md) の `D-38` の `SP-19` 実測追記が正本）。Workers Paid の課金体系（含まれるリクエスト数・CPU 時間と超過単価）は [パブリック化レビュー](../../05_release/repository-publication-review.md) §7.3 が正本（🔴 §0.2 のとおり単価を本書へ書き写さない。数値を疑ったら正本と [Cloudflare 公式](https://developers.cloudflare.com/workers/platform/pricing/) を見る）

**検索と枠を分ける**（キー接頭辞 `search:` / `gems:`）のは、守りたいコストの種類が違うため。検索が守るのは **上流 GitHub API の枠**、Gem 一覧が守るのは **自 Worker の CPU** である。枠を共有すると「検索 → Gem 一覧」という主要導線で正常な利用者どうしが枠を食い合う。

🔴 **この打ち手の限界（過信しない）**:

1. Cloudflare の Rate Limiting binding は **Worker のコード内で判定する** ため、**リクエスト課金そのものは減らない**。減るのは「重い処理に入る前に弾いて浮く CPU 分」だけである。Worker の手前で止めたいなら **WAF のレート制限という別レイヤー** が要る
2. binding は公式が **per-colo・"permissive, eventually consistent"・正確な会計向けではない** と明記している。厳密な回数保証を前提にした設計にしない
3. 同じ理由で **送信元 IP のローテーションには効かない**。レート制限キーは IP 全体（IPv6 なら 128 ビット）の HMAC なので、`/64` を配る VPS 等でアドレスを都度変えられると毎回別キーの 1 件目になり、閾値に到達しない。Worker の手前で止めるには WAF レイヤーが要る。🔵 これは「だから無意味」ではなく **この打ち手が守れる範囲はここまで** という意味である（IPv6 の `/64` 正規化そのものは別 Issue で扱う）

#### 超過時の挙動とフェイルオープン（全経路共通）

🔴 **本節は §3.3 の適用経路表で `✅ 適用` になっている全経路に共通する仕様である**（特定の経路の枠分けをやめても本節は残す）。

超過時は `RateLimitExceededError('rateLimitSecondary')` を投げ、画面はローカライズ済みメッセージを表示、API は **`429` + `Retry-After: 60`** を返す（`period=60` と一致させた保守的な上限値。Cloudflare の `limit()` は `{ success }` しか返さず復帰時刻を教えないため、窓の長さをそのまま使う）。

**フェイルオープン**（間引かず黙って通す）にする条件は 3 つ。いずれも「間引くべきでない」ではなく「判定に必要な材料が揃わない」ケースであり、意図的な設計判断（`src/composition/rate-limit.ts` のコメント参照）:

1. 接続元 IP を識別できない
2. `RATE_LIMIT_SALT` が未設定（§7.2.1 / `env-vars.md`）
3. binding が未提供（ローカル `npm test` / `next dev` 等の Workers 実行環境の外）

---

## 4. キャッシュ（`D-18` / `D-24`）

### 4.1. 🔴 3 軸に分解する（`infrastructure-design.md` §10.2 の Cloudflare 版）

`infrastructure-design.md` §10.2 は「キャッシュヒット率向上はコスト削減とレート制限対策の **同じ打ち手**」と書いているが、**Cloudflare では成立しない**。3 軸に分けて考える。

| 軸 | キャッシュヒットは効くか | 根拠 |
|---|---|---|
| **GitHub API のレート枠**（`NFR-7`） | 🟢 **効く**（GitHub を呼ばない） | 事業者非依存 |
| **CPU 時間**（Free の 10ms / Paid の従量） | 🟢 **効く**（CPU 課金はキャッシュミス時のみ） | リサーチ §3.2 |
| **リクエスト数**（Free の 100,000/日 / Paid の従量） | 🔴 **効かない** | 公式明記: キャッシュから返したリクエストも同じ per-request レートで課金される |

→ **リクエスト数枠を減らす唯一の手段は「Worker を経由させないこと」**（静的アセット化）。キャッシュは防波堤にならない。

### 4.2. 採用する構成

> 🔴 **2026-08-19 改訂（決定ログ `D-24`）**: 当初案（下記の旧構成）は「L2 = HTTP `Cache-Control` + Workers Caching が MVP の主役」としていたが、§4.5 の「`X-Cache-Status` をアプリ側で動的に付与する」検証手段と両立しなかった（エッジキャッシュが HIT した場合 Worker 自体が実行されず、動的ヘッダを付与できない）。`SP-5` の受け入れ条件は「2 回目は GitHub API を呼んでいないことを外から検証できる」こと（`user-story-map.md` §5.3）であり、**検証可能性を優先して L2 の主役をアプリ内 `CachePort` の実装に置き換える**。経緯・却下案は議論記録 [`content/discussions/sp5-cache-design-20260819/whiteboard.md`](../../../content/discussions/sp5-cache-design-20260819/whiteboard.md)（round 3・lead 判定・争点 A）を参照。

| 層 | 実装 | 役割 |
|---|---|---|
| **L1** | リクエスト内メモ化（React `cache`） | 同一レンダー内の重複呼び出しを消す |
| **L2** | **アプリ内 `CachePort` の実装（`InMemoryCache`）** | 🔵 **MVP の主役**。composition root の **モジュールスコープで生成する単一インスタンス** として全リクエストから共有参照する（`NFR-17`） |
| **L3** | 外部ストア（R2 / D1 / KV） | ❌ **未採用**。§6.2 の観測条件を満たしたときだけ ADR とともに導入 |

- `Cache-Control` ヘッダは付与してよいが、**「エッジが自動的に Worker をバイパスする」効果には依存しない**（依存すると HIT 時に `X-Cache-Status` を付与できなくなり §4.5 と矛盾するため）。ヘッダを付けても Workers Caching の tiered 化・リクエスト合体自体は副次的な効果として残るが、`SP-5` の検証手段としては当てにしない
- `NFR-7`（request coalescing）は当初案（`infrastructure-design.md` §4）どおり **補助** に据え置く。エッジのリクエスト合体を主要な防波堤とする格上げは、L2 をエッジキャッシュに依存させないという本改訂と両立しないため撤回する。代わりに `CachingRepositoryQuery`（`src/infrastructure/platform/cached-repository-query.ts`）が **アプリ層の single-flight**（同一キー並行リクエストの in-flight `Promise` 合流）で `NFR-7` を担保する（詳細は [ADR 0005](../../adr/0005-cache-port-yagni-exception-and-ttl.md) §5）
- **isolate をまたぐ永続性は本スプリントでは追わない**（`InMemoryCache` は isolate が破棄されると失われる）。将来の格上げ候補として、Cloudflare の Cache API（`caches.default`）を composition root から能動的に呼び出し isolate 間で共有する案が残っている（§6.2 の観測条件を満たしたときに ADR で検討する）

⚠️ **Next.js の `fetch` Data Cache / `use cache` は当てにしない**。OpenNext で incremental cache を設定しない構成では isolate 内メモリに退化し、isolate の生存に依存する。**`SP-5`（同じ検索で API を二度叩かない）の担保は L2（アプリ内 `CachePort`）で説明する**。

### 4.3. `NFR-17` Cache Port の実装位置

Cache Port は **維持する**（撤廃しない）。ただし実装は `open-next.config.ts` ではなく **`src/infrastructure/platform/cache.ts`** に置く。

- 面積は `get` / `set` / `invalidate` + TTL のみ（`NFR-17` のとおり。汎用キャッシュライブラリを自作しない）
- 実体は「キャッシュキーの生成（`NFR-18`）+ レスポンスへの `Cache-Control` 付与」の薄いラッパー
- `Cache-Control` は RFC 9111 準拠で **事業者非依存**。他社へ移してもヘッダ制御はそのまま動く（§10 の退避コストが小さい理由）
- `invalidate` は TTL 短縮またはキャッシュキーの **バージョンセグメント**（名前空間の直後の `CACHE_SCHEMA_VERSION`）の引き上げで表現する（永続タグストアに踏み込まない）。値の意味が変わる変更をしたら bump して一括で論理無効化する（Issue #142・[ドメインモデル](../data-model/domain-model.md) §4）

### 4.4. L3 を入れる判定条件

`infrastructure-design.md` §6.2 の条件を **そのまま維持する**（新しいルールを作らない）。加えて Cloudflare 固有の注意を 1 つ足す。

> 🔴 **R2 の有効化は支払い方法の登録を伴う**（`A-6`）。L3 導入の ADR を起票するときは、Workers Paid への加入とは **別のユーザー作業** が発生することを明記する。

---

### 4.5. 🔴 `SP-5` の検証手段（「2 回目は GitHub API を叩いていない」をどう見せるか）

[`user-story-map.md`](../../02_requirements/user-story-map.md) §5.3 の `SP-5` は「2 回目は GitHub API を呼んでいない（`x-ratelimit-remaining` が減らない／ログに外部リクエストが出ない）」を操作レビュー手順にしている。**本設計はログを既定で無効化する（§9.1）ため、確認手段を設計として先に確定しておく。**

> 🔴 **2026-08-19 改訂**: 当初案は「画面（Server Component の SSR 応答）に `X-Cache-Status` を **アプリ側で** 動的付与し、ブラウザの DevTools で誰でも確認できる」を主経路としていたが、`wrangler dev --local` + スタブ GitHub API による実機検証で **不成立** と判明した。回避策として「wrangler の `main` を自前エントリに差し替え、`node:async_hooks` の `AsyncLocalStorage` で HIT/MISS を Worker の外側（エントリ層）へ運ぶ」方式を試したが、OpenNext 生成物が挟む非同期継続を `AsyncLocalStorage` の store が越えられず、composition root のコールバックが呼ばれる時点で `getStore()` が **常に `undefined`** だった（デバッグログで実測確認済み。原因は workerd の `nodejs_compat` 実装が Next.js 内部の継続を計装できていない可能性が高いが **未確定**）。一方 **キャッシュ本体（L2 `CachePort`）は実機で正しく動作しており**、同一 URL を短間隔で連続 GET すると 2 回目以降 HIT することをログで確認済み — 壊れていたのは観測手段だけで、二重フェッチしない性質そのものは健全だった。経緯・却下案の全文は議論記録 [`content/discussions/sp5-cache-design-20260819/whiteboard.md`](../../../content/discussions/sp5-cache-design-20260819/whiteboard.md) を参照。

→ 主経路を **`GET /api/search`（Route Handler）の応答ヘッダ** に切り替える。Route Handler は Web 標準の `Response` を直接返せるため動的ヘッダ付与に制約がなく、確認できるのは **画面（SSR 応答）ではなく `/api/search?q=...` を直接叩いたとき** に限る。🔴 **画面（`app/[locale]/page.tsx`）は SSR 内でユースケースを直接呼ぶだけで `/api/search` へリクエストしないため、検索フォームを操作しても DevTools の Network タブに `/api/search` は現れない**。確認するにはブラウザのアドレスバーで `/api/search?q=...` を別途開く（画面の検索操作とは別の追加操作）。

| 経路 | 手段 | 位置づけ |
|---|---|---|
| **主** | `GET /api/search` の応答ヘッダ `X-Cache-Status: HIT` / `MISS`（Route Handler が付与） | 🟢 **事業者非依存**。`/api/search?q=...` を直接開く（画面の検索操作とは別操作）ことで誰でも確認でき、E2E テストからも assert できる（`SD-2`）。**画面の SSR 応答には乗らない**（上記改訂理由による制約。画面の検索フォーム操作だけでは DevTools の Network タブにも `/api/search` は現れない） |
| 副 | レスポンスヘッダ `X-GitHub-RateLimit-Remaining`（GitHub の応答から転記） | 2 回目に値が変わらないことで裏を取る。`INF-1` に抵触しない（利用者ではなく **アプリの GitHub App installation token** の残量・`D-20`） |
| 補助 | `wrangler tail --format json` のライブストリーム | ⚠️ `invocation_logs: false` でも tail が拾えるかは **未確認**（§12 の 9）。主経路にしない |

### 4.6. `GET /api/search` のエラー応答の契約（`SP-9`）

エラー時の本文は **`kind`（+ 再試行情報）だけ** を返す。利用者向けの文言は画面側が `kind` から i18n で組み立てるため、応答に開発者向けメッセージを含めない（内部情報を漏らさない・`NFR-8`）。

| HTTP | 本文 | 補足 |
|---|---|---|
| 400 | `{ "kind": "validation" }` | 検索条件が不正 |
| 404 | `{ "kind": "notFound" }` | 対象なし |
| 429 | `{ "kind": "rateLimitPrimary" \| "rateLimitSecondary", "retryAfter"?: ISO 8601, "retryAfterSeconds"?: number }` | `Retry-After` ヘッダも同時に付く |
| 502 | `{ "kind": "network" \| "auth" \| "upstream" }` | 利用者が入力で直せない上流側の問題 |

⚠️ **`/api/search?q=...` を直接開いて確認するときは、エラーでも文言が出ないのが正しい挙動**（不具合ではない）。判別条件の正本は [`prd.md`](../../02_requirements/prd.md) §7。

🔵 **`X-Cache-Status` は「キャッシュが効いたことを外から観測できる」ための最小の仕掛け** であり、事業者を差し替えても残る（`src/infrastructure/platform/` の実装が付け替わるだけ）。付与位置が Route Handler になっても、キャッシュ判定ロジック自体（L2 `CachePort`）への依存関係は変わらない。

---

## 5. コスト（`INF-2`）

> 🔴 **現状（2026-08-20 実機確認）: 本アカウントは Workers Paid（$5/月 + 従量）である。**
> したがって **§5.1「月額 0 円の条件」は満たしていない**（条件 1 を外れている）。現状に該当するのは
> §5.4「Paid へ移行した場合に失うもの」の側である。§5.1 / §5.3 は **Free を選べた時点の判断記録** として残す。
>
> 実額の試算（含まれる 1,000 万リクエスト/月・撤退ライン $10 に触れる条件の逆算）は
> [パブリック化レビュー](../../05_release/repository-publication-review.md) §7.3 が正本。
> ⚠️ `D-19` が約束した Billable Usage API の日次ポーリングは **未実装**。

### 5.1. 月額 0 円の条件（⚠️ 現在は満たしていない・上記注記を参照）

| # | 条件 |
|---|---|
| 1 | **Workers Free のまま**（$5/月 のサブスクに加入しない・支払い方法を登録しない） |
| 2 | 静的アセットは Workers Static Assets で配信する（無料・無制限）。`run_worker_first` を使わない |
| 3 | 動的処理を 100,000 リクエスト/日・CPU 10ms/invocation 以内に収める |
| 4 | **R2 を有効化しない**（支払い方法の登録が必要）。D1 / KV / DO も使わない |
| 5 | CI は GitHub Actions（Cloudflare 側のビルド枠を使わない） |
| 6 | 独自ドメインを使わない（`*.workers.dev` で運用する。§6.3） |

🔵 **Free の最大の価値は無料であること自体ではなく、超過時に「課金されず停止する」こと**（HTTP Error 1027）。これが `INF-2` §10.3 の「課金ではなく停止側に倒す」を **構造的に** 満たす唯一の手段である。

### 5.2. Free の上限（判断に必要な分だけ）

| 項目 | Free の上限 | 超えるとどうなるか |
|---|---|---|
| リクエスト | 100,000 / 日 | HTTP Error 1027 で停止（課金されない） |
| **CPU 時間** | **10 ms / invocation** | 同上 |
| **Worker バンドル** | **3 MB（圧縮後）** | デプロイが失敗する |
| サブリクエスト | 50 / リクエスト | エラー |

数値の出典と全体像は [リサーチ §1.4 / §3.1](../../01_research/infra/20260818-cloudflare-research.md)。

### 5.3. 🔴 Free / Paid の判定式（`SP-1` の実測ゲート）

**前倒しで Paid にしない。実測してから決める。**

```
判定タイミング: SP-1 でプレビュー環境へ初回デプロイした直後

計測 1: p95 CPU 時間
  npx wrangler tail --format json   # SP-1 時点の 2 経路（トップ / 検索結果 100 件）を叩いて cpuTime を見る
  # ⚠️ 詳細ページは SP-3 の成果物。SP-3 完了後に同じ計測を 1 回追加する

計測 2: Worker バンドルサイズ（圧縮後）
  npx opennextjs-cloudflare build && gzip -c .open-next/worker.js | wc -c

判定: p95 CPU > 7〜8 ms  または  gzip サイズ > 3 MB
  → Free では INF-3（Next.js 16 が動くこと）を満たせないことが実測で確定
```

**閾値を超えたときの手順**（`INF-3` > `INF-2` の優先順位に従う）:

1. まず CPU / サイズを削る打ち手を試す（アイコンの barrel import 回避・不要な Node ポリフィルの除去・キャッシュヒット率の向上）
2. それでも超えるなら、Claude が `limits.cpu_ms` の設定と監視の準備を **確認なしで** 済ませる
3. **支払い方法の登録とプラン切替だけ** を `A-6` としてユーザーへ通知する（Free → Paid に CLI/API 経路は存在しない）

🟢 **切替の可否はユーザーから事前承認済み（`D-19`・2026-08-18）**。閾値超過が実測で確定したら、判断を仰ぎ直さずに「支払い方法を登録してください」という 1 手だけを依頼する。

⚠️ **`SP-1` はこの手順の 3 に到達しない限り止まらない**（Free のままプレビュー URL は出せる）。

### 5.4. Paid へ移行した場合に失うもの

| 手段 | 防げること | 防げないこと |
|---|---|---|
| `limits.cpu_ms` | 1 リクエストあたりの CPU 課金の暴走 | **リクエスト数課金** |
| Billable Usage API（日次） | 製品別コストの事後取得 | バースト検知のラグ |
| Budget alerts | 閾値到達の通知 | 🔴 **停止しない**（公式に "informational only" と明記） |

🔴 **残余リスク**: Paid 移行後は、大量アクセスによるリクエスト数課金の急増を止める native な手段が存在しない。Billable Usage API のポーリングによる後追い封じ込めしか残らない。

🟢 **撤退ラインは月額 $10**（`D-19`・ユーザー決定）。Billable Usage API（`GET /accounts/{id}/billable-usage`）の日次ポーリングでこの閾値を監視し、超えたら Issue を起票して通知する。⚠️ Budget alerts は通知のみで停止しないため、これに依存しない。

---

## 6. 環境構成

### 6.1. 3 環境

| 環境 | 実体 | URL | シークレット |
|---|---|---|---|
| **local** | `wrangler dev` / `opennextjs-cloudflare preview` | `localhost` | `.dev.vars`（コミットしない） |
| **preview** | 同一 Worker の **version**（`wrangler versions upload --preview-alias pr-<N>`） | `pr-<N>-gem-hunter.<subdomain>.workers.dev` | プレビュー専用の PAT（OAuth は無効） |
| **production** | Worker 本体（`wrangler deploy`） | `gem-hunter.<subdomain>.workers.dev` | 本番の PAT / OAuth |

🔴 **プレビューに `[env.*]`（Wrangler Environments）を使わない**。`[env.*]` は `<name>-<env>` という **別 Worker** を作るため、PR ごとに使うと Free の Worker 数上限（100/アカウント）と棚卸しコストに直結する。**versions + preview alias なら Worker は増えない**。

🔴 **preview alias は削除できない**（wrangler CLI・Cloudflare REST API のいずれにも delete 系エンドポイントが存在しないことを実測で確認済み。**2026-08-24 に再検証済み**（Issue #613/#615）: `wrangler versions` サブコマンドは `upload`/`deploy`/`list`/`view`/`secret` のみ、`DELETE .../versions/<id>` は実 API で HTTP 405 `10405 Method not allowed for this authentication scheme` を返す）。能動的に効く唯一のレバーは Worker 全体の `previews_enabled` トグル（全 PR のプレビューを一括で無効化する。PR 単位の選択削除は不可能）だが、並行中の他 PR のプレビューも巻き添えにするため `SD-1`（プレビュー URL 必須）と両立せず、通常のスプリント後始末には使わない（インシデント対応で全プレビューを緊急停止したいときだけの手動 killswitch として想定する）。唯一の自動的な後始末は **1000-alias LRU 自動失効**（受動的。最近デプロイされた 1000 件の alias だけが保持され、それを超えた分は最古の alias から自動的に消える）。

→ 「削除」ではなく **退役（retire）** で対応する: 完了したスプリントの alias に対して、そのときの本番ビルドと同じ成果物を `wrangler versions upload --preview-alias <name>` で再アップロードし、実効ルーティング先を張り替える。alias URL 自体は生き続けるが、古いスプリントのコードを配信し続ける状態は解消される（version オブジェクト自体は削除されず残る）。手順は §8.2.1。決定の経緯は [議論記録](../../../content/discussions/sprint-env-lifecycle-20260820/whiteboard.md)、決定ログは [`open-questions.md`](../../02_requirements/open-questions.md) `D-26`。

🔴 **`workers/scripts/<name>` 配下への `DELETE` は、末尾に未知のサブリソース名を付けても 404 にならない**（実測・Issue #615）。Cloudflare API はパス末尾の未知セグメントを黙って切り捨て、`DELETE /accounts/{account_id}/workers/scripts/{name}` （**Worker 本体の削除**）として処理する。個別 version・alias を削除する経路を探索するために `DELETE .../workers/scripts/<name>/<存在しないサブリソース>` を実 API へ投げると、本番 Worker ごと消える。**Cloudflare API を裏取りする調査で破壊的メソッドを試す場合、対象パスに `workers/scripts/<本番 Worker 名>` を含めてはならない**（存在しないダミーの script 名や、影響のない読み取り専用エンドポイントに限定する）。再発防止のガードは `.claude/hooks/pre-cloudflare-destructive-check.sh`（`DELETE` × `workers/scripts` パス、および `wrangler delete` を PreToolUse でブロック）。

### 6.2. OAuth とプレビューの相性（`infrastructure-design.md` §8.1 の Cloudflare 版）

方針 (a)「プレビューでは OAuth を無効化する」を採る。preview alias は PR ごとに変わるため、コールバック URL を事前登録できない。**環境変数が揃っていないときはログイン導線を出さない** というアプリ側の分岐だけで成立する（`AR-5`: 未ログインでも全機能が使える）。

### 6.3. ドメイン

**MVP は `*.workers.dev` で運用する**（独自ドメイン不要）。理由:

- Workers の Custom Domain には **active な Cloudflare zone とその所有が必要**（公式の要件・[リサーチ §6.1.1](../../01_research/infra/20260818-cloudflare-research.md)）→ レジストラでのネームサーバー変更（人間作業・§11.2 の `H-4`。**未実施**）が発生する
- ポートフォリオ用途（`D-3`）では `*.workers.dev` で足りる

⚠️ **`H-n` の採番は本書（§11）とリサーチ文書（[`20260818-cloudflare-research.md`](../../01_research/infra/20260818-cloudflare-research.md) §6.1）で独立している。** リサーチ側の `H-3`（ネームサーバー変更）は本書の `H-4` に対応する（本書の `H-3` は GitHub App の設定で別件・🟢 対応済み）。リサーチ文書は 2026-08-18 時点のスナップショットなので採番は揃えず、参照するときに読み替える。

⚠️ Cloudflare 公式は workers.dev を「Free website 扱いで、business-critical でない個人・ホビー用途を想定したもの」と明記し、本番は Workers route か Custom Domain で動かすことを推奨している（[リサーチ §6.1.1](../../01_research/infra/20260818-cloudflare-research.md) に原文）。**独自ドメインの要否は `M-4`（公開判断ゲート）で決める**。

---

## 7. CLI 一次運用（ユーザー指示の実装）

### 7.1. 非対話実行の前提

```bash
export CLOUDFLARE_API_TOKEN="<token>"      # これがあると wrangler は profile / OAuth を見ない
export CLOUDFLARE_ACCOUNT_ID="<account_id>"
export WRANGLER_SEND_METRICS=false         # 未設定だと初回に対話プロンプトが出て非 TTY で失敗する
export WRANGLER_SEND_ERROR_REPORTS=false
npx wrangler whoami                        # 疎通確認
```

🔴 **トークンの実値をシェルへ直接打ち込まない**（履歴・`ps` 出力・スクロールバックに残る）。値は必ず **供給済みの環境変数から参照する**（CI は `${{ secrets.CLOUDFLARE_API_TOKEN }}`、Claude Code のセッションは供給済みの env）。上の `export` は「wrangler がこの変数名を読む」ことを示すための表記であり、値を手打ちする手順ではない。

```bash
```

- 🔵 **本リポジトリのクラウドセッションから `api.cloudflare.com` に到達できることは実測済み**（リサーチ §7）。トークンが env に供給されれば Claude が直接 wrangler を叩ける
- ⚠️ `wrangler login` はブラウザ必須なので使わない。`--temporary` トークンは 60 分以内に人間が claim URL を踏む必要があり自律運用に不適
- ⚠️ Cloudflare API のレート制限は 1,200 リクエスト / 5 分（Dashboard 操作も合算）。ポーリング型の監視を書かない

### 7.2. ブートストラップ手順

```bash
# 1. 疎通確認
npx wrangler whoami

# 2. 初回デプロイ（workers.dev サブドメインが未設定ならここで確定させる）
npx opennextjs-cloudflare build
npx wrangler versions upload --preview-alias bootstrap

# 3. シークレット投入（非対話・GitHub App 方式 / `D-20`）
# 🔴 本プロジェクトは version + preview alias 運用のため `wrangler secret put` は使えない（下記 §7.2.1）
printf '%s' "$GITHUB_APP_CLIENT_ID"       | npx wrangler versions secret put GITHUB_APP_CLIENT_ID
printf '%s' "$GITHUB_APP_INSTALLATION_ID" | npx wrangler versions secret put GITHUB_APP_INSTALLATION_ID
printf '%s' "$RATE_LIMIT_SALT"            | npx wrangler versions secret put RATE_LIMIT_SALT

# 秘密鍵は PKCS#8 へ変換して投入する（理由は §7.6）。中間ファイルを作らずパイプで渡す
# ⚠️ 供給元によっては改行がリテラルの \n にエスケープされているため、先に正規化する
set -o pipefail   # openssl の失敗をパイプに埋もれさせない（空シークレット登録の防止）
printf '%s\n' "${GITHUB_APP_PRIVATE_KEY//\\n/$'\n'}" \
  | openssl pkcs8 -topk8 -inform PEM -outform PEM -nocrypt \
  | npx wrangler versions secret put GITHUB_APP_PRIVATE_KEY_PKCS8

# 4. 本番デプロイ
npx wrangler deploy
```

### 7.2.1. 🔴 シークレットは `wrangler versions secret put` で投入する（実測 2026-08-19・#67）

本プロジェクトは **version + preview alias 運用**（`wrangler versions upload`。`wrangler deploy` を常用しない）のため、`wrangler secret put` は次のエラーで失敗する:

```
✘ [ERROR] Secret edit failed. You attempted to modify a secret, but the latest version of your Worker isn't currently deployed.
```

これは「バージョン運用とシークレットを併用したときの事故（意図しないデプロイ）を防ぐための Cloudflare 側の制限」であり、環境不良ではない。**デプロイせずにシークレットだけ更新する `wrangler versions secret put` を使う**（本プロジェクトの標準経路）。

```bash
printf '%s' "$V" | npx wrangler versions secret put KEY --message "投入理由"
npx wrangler versions view <VERSION_ID>   # 投入結果は Secrets 欄で確認する
```

- 投入すると **その時点の最新バージョンのコード + 新しいシークレット** で新バージョンが作られる（デプロイはされない）
- その後 `wrangler versions upload` で作る新しいバージョンは **既存のシークレットを引き継ぐ**（`versions view` の `Secrets:` 欄で確認できる）
- ⚠️ `wrangler secret list` は **デプロイ済みバージョン** を見るため、versions 運用中は空の `[]` を返すことがある。投入確認は `wrangler versions view <VERSION_ID>` で行う

### 7.3. 使うコマンド（一覧）

| 目的 | コマンド |
|---|---|
| 本番デプロイ | `wrangler deploy` |
| プレビュー版のアップロード | `wrangler versions upload --preview-alias pr-<N> --tag "$SHA"` |
| 段階的な本番反映 | `wrangler versions deploy <VID>@100 -y` |
| ロールバック | `wrangler rollback` / `wrangler versions list` |
| シークレット | `printf '%s' "$V" \| wrangler versions secret put KEY`（version 運用のため `secret put` は不可・§7.2.1） |
| 型生成 | `wrangler types --env-interface CloudflareEnv` |
| ログ | `wrangler tail --format json --status error` |
| 状態確認 | `wrangler deployments list --json` |

⚠️ 非対話で詰まる箇所は `--yes` / `-y`（`versions deploy`）・`--skip-confirmation`（削除系）で回避する。

### 7.4. 🔴 Cloudflare MCP の扱い（アローリスト）

ユーザー指示「MCP よりも CLI」は **主経路の指定** であり、読み取りまでの禁止ではない（本プロジェクトが GitHub 操作で「MCP が一次経路・gh は当てにしない」と表現しているのと同型）。

| 区分 | ツール | 可否 |
|---|---|---|
| 読み取り（許可） | `search_cloudflare_documentation` / `workers_list` / `workers_get_worker` / `workers_get_worker_code` | 🟢 使ってよい（`CP-2` の一次情報確認・障害調査） |
| 書き込み（禁止） | `*_create` / `*_delete` / `*_edit` / `*_query`（D1 / KV / R2 / Hyperdrive の全書き込み系） | 🔴 **使わない**。リソース作成は `wrangler` に一本化する |

🔴 **理由**: リソース ID は `wrangler.jsonc` にコミットする必要があり、MCP で作っても反映作業は消えない。CLI なら「作成コマンドの出力 → 設定ファイル」が 1 本で完結し、**正本が 1 つ** になる。MCP で作ると「実体は MCP 操作ログ、設定は git」という二重の真実になる。

> 補足: MCP で読んだ値（namespace ID 等）は **必ず `wrangler.jsonc` かコミットに落とす**。Claude が知っているだけの状態にしない。

🔴 **本表は `.claude/settings.json` の `permissions` に反映済み**（Issue #49 の専門チーム議論で確定）。**本表をドキュメントに書くだけでは実効力がない** — クラウドではサンドボックスが動作せず（[`sandbox-rules.md`](../../rules/sandbox-rules.md)「クラウド実行環境ではサンドボックスは動作しない」・#383）、実効防御はコンテナ隔離・`permissions` ACL・PreToolUse フックの 3 層に限られるため。

| 反映内容 | ツール |
|---|---|
| `allow` | 上表の読み取り 4 ツール |
| `deny` | 書き込み系 10 種（D1 / KV / R2 / Hyperdrive の `*_create` / `*_delete` / `*_edit` / `*_query`）**＋ 上表に無い読み取り系 10 種**（各サービスの `*_get` / `*_list` と `migrate_pages_to_workers_guide`） |

⚠️ **`deny` は既知ツール名の列挙** であり、`allow` を潰さずにワイルドカードで塞ぐ手段がないため、**MCP サーバー側に新しいツールが増えると未列挙のまま素通りする**。今後 MCP を追加する PR は、許可範囲の `permissions` 反映を **同一 PR に含める**。

🔴 **恒久対策（アローリスト化・#56・実装済み）**: `PreToolUse`（`.claude/hooks/pre-tool-use-router.sh` → `pre-cloudflare-mcp-allowlist-check.sh`）が `mcp__Cloudflare_Developer_Platform__*` 呼び出しを本表（読み取り 4 ツール）に対して機械的に照合し、**許可集合に無いツールは exit code 2 で一律ブロックする**（新規ツールが `permissions` の更新漏れで素通りする穴を塞ぐ）。許可集合は本表の **「読み取り（許可）」行（行頭 `|` で始まる表の行にアンカーし、散文中の同一文言には反応しない）から、ヘッダの「ツール」列を動的解決した上で** バッククォート区切りのツール名を機械的に読み取る（正本はこの表のみ・二重管理にしない。列位置の決め打ちはしない）。表を解析できない・行が曖昧（複数該当）・列を解決できない場合は **fail-closed**（全 Cloudflare MCP ツールをブロック）にする。回帰検証: `bash .claude/hooks/pre-cloudflare-mcp-allowlist-check.sh --self-test`（`tools/run_checks.sh` に配線済み）。

**`permissions.allow` / `deny` の扱い（判断記録）**: 上表の `allow`/`deny` はそのまま **残す**（削除しない）。理由は二重防御（defense-in-depth）— `permissions` ACL は Claude Code 本体が PreToolUse フックより先に評価しうるレイヤーであり、フック側にバグ・設定ミス（ドキュメント解析失敗を除く）があっても `deny` 列挙済みの書き込み系ツールは別レイヤーで止まる。一方でこの `deny` 列挙は「新しいツールを塞げない」という本質的な限界を持ち続けるため、**アローリストの正本はあくまでフック側（本表 §7.4 を参照する実装）** であり、`permissions.deny` は「知られている危険なツール名を二重に塞ぐ補助」という位置づけに格下げする。

**`workers_get_worker_code` の `scriptName` 値域制限について（Issue #56「あわせて検討」への回答）**: 本フックはツール名の呼び出し可否のみを判定し、**引数値（`scriptName` が本プロジェクトの Worker 名以外を指せてしまう点）はスコープ外** とする。理由: 引数値の妥当性検証は「読み取り専用ツールが他プロジェクトの Worker 情報まで読めてしまう」という情報漏洩リスクへの対策であり、ツール呼び出し自体の可否を塞ぐ本フックの設計目的（新規ツールの無許可素通り防止）とは別の対策軸になる。根本対策は **最小権限トークン**（対象アカウント・Worker を絞った Cloudflare API トークンの発行・A-6）に委ねる。

**他 MCP サーバー（`context7` / `github` 等）への一般化について**: 本 Issue の対応方針検討時に調査済み（Issue #56 コメント参照）。`shadcn` は許可済みツールと実装ツールが一致し穴なし。`github` MCP は本表のような「これが全て」という正本の表が存在せず、GitHub 操作が多数のスキル・ドキュメントで広範に使われているため、ここで新規にアローリスト SSOT を作ると誤ブロックのリスクが高い。YAGNI に従い今回は一般化せず Cloudflare のみに適用する。github MCP のアローリスト化が必要になった場合は、正本表の新設を伴う別 Issue とする。

### 7.5. ⚠️ `INF-20` の例外（セッションからの手動デプロイ・`D-23` → 復帰先は `D-31` / `D-32` で改訂）

`INF-20` は「デプロイのトリガーは git push / マージのみ」と定めるが、**GitHub Actions がプラットフォーム側の制限により起動できない間に限り、Claude がセッションから直接 `wrangler versions upload` / `wrangler deploy` を叩いてよい**。

**経緯**: 当初はブートストラップ期間限定の例外だったが、`deploy-preview` ワークフローが 4 回とも数秒でジョブごと失敗（ログ 0 バイト・ステップ未開始）し、無関係な `repo-checks` も同様の失敗を示したため調査した結果、**GitHub Actions が制限中であることが確定した**（Issue #65・飼い主回答）。ワークフロー定義・参照アクションのタグはいずれも正しく、Actions 側の問題である。これを受けて `.github/workflows/deploy-preview.yml` と `deploy-production.yml` は **撤去済み**（`D-23`）。起動できない赤いチェックを毎 PR に残すと、本当の失敗が埋もれるため。

~~🔴 **例外の終了条件は「GitHub Actions の制限が解除され、ワークフローを復帰させた時点」**（旧: 「デプロイ用ワークフローが `main` にマージされた時点」から `D-23` で改定）。これ以降は GitHub Actions 経由のみに一本化し、手動デプロイの経路を残さない。復帰手順は §8.4。~~

🔵 **一部失効（2026-08-24・`D-42`）**: GitHub Actions の制限解除は **品質チェックの Actions 化にのみ効く**（`.github/workflows/quality-checks.yml`）。🔴 **デプロイの復帰先は Actions ではなく Workers Builds**（`D-31` / `D-32`・§8.2.3）であり、上記の終了条件のうち「ワークフローを復帰させる」「GitHub Actions 経由のみに一本化する」部分は失効している。**§8.4 のワークフロー復元手順は実行しない。**

🔵 **現在の終了条件**: Workers Builds への移行が完了し、デプロイゲート（`D-26`）通過後の再ビルド経路（`tools/trigger_workers_build.py`・§8.2.3「移行後の実測」）で `main` の本番反映が回る状態を維持できていること。🔴 **それ以降も、セッションによる `wrangler` の直接実行は手動フォールバックとして残す**（プレビュー URL の取得は `docs/rules/pr-review-flow-summary.md` の PR 作成手順が要求しており、これを止めると `SD-1`（開けるプレビュー URL）を満たせなくなるため）。

⚠️ **`SP-4`（テスト CI の整備）と混同しない。** 本例外は **デプロイの経路** に限定した話である。品質チェックの側は二層構成になっており、Prettier / ESLint / 型 / Vitest は `.github/workflows/quality-checks.yml` が自動実行し（`D-42`）、E2E と Lighthouse は引き続きセッション側の `tools/run_checks.sh`（= `npm run check`）が担当する（§8.2・`docs/04_development/testing-strategy.md`）。


### 7.6. 🔴 GitHub App の秘密鍵は PKCS#8 で持つ（`D-20` の実装上の必須事項）

GitHub が発行する App の秘密鍵は **PKCS#1**（`-----BEGIN RSA PRIVATE KEY-----`）だが、**Workers の Web Crypto `crypto.subtle.importKey()` は `pkcs8` しか受け付けない**（`pkcs1` という形式指定が存在しない）。変換せずに渡すと実行時に import が失敗する。

```bash
# PKCS#1 -> PKCS#8（Worker に入れる前に一度だけ行う）
openssl pkcs8 -topk8 -inform PEM -outform PEM -nocrypt
```

- 🔴 **変換結果をファイルに書かない**。上記のようにパイプで `wrangler versions secret put` へ直接渡す（`INF-5` / 秘密のディスク残留を避ける・投入コマンドの理由は §7.2.1）
- 🔴 **改行がリテラルの `\n` にエスケープされた形で供給される経路がある**（複数行の鍵をシークレット UI へ貼る場合）。そのまま `openssl` に渡すと `Could not read key from <stdin>` で失敗し、**空のシークレットが登録されて実行時まで気づけない**。§7.2 のとおり正規化と `set -o pipefail` をセットで使う（2026-08-18 に実測確認済み）
- Worker 側は `importKey("pkcs8", …, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["sign"])` で読み、`iat` / `exp` / `iss`（App の Client ID）を含む JWT を RS256 で署名する
- **`exp` は最大 10 分**（GitHub 側の上限）。時計ずれ対策として `iat` を 60 秒戻す
- installation token（`POST /app/installations/{id}/access_tokens`）は **TTL 1 時間**。毎リクエストで取り直さず、**失効前まで再利用する**（安全マージンを引いて再取得）

> 🔵 上記はいずれも 2026-08-18 に Cloudflare Workers 上で実測確認済み（[ADR 0003](../../adr/0003-github-app-authentication.md)）。

---

## 8. CI/CD

### 8.1. 🔴 現状: **デプロイに** GitHub Actions は使用しない（`D-23` → 発火点は `D-31` / `D-32` で Workers Builds へ・品質チェックのみ `D-42` で Actions 化）

> **この切り替えの根拠は飼い主の明示指示（2026-08-19・逐語）**: 「GitHub Actions について、制限中なので自前でチェックする仕組みに切り替えてください。」本番デプロイをセッションから実行することについても同日「本番デプロイについて自動で行えるように許可リストに追加してください。」の指示を受けて `.claude/settings.json` の `permissions.allow` に wrangler の deploy 系を追加済み。**この 2 件を超える範囲（レビュー・セルフレビューの省略等）は認めない。**

~~**原則（GitHub Actions が復帰したら戻す構成）は「GitHub Actions + `cloudflare/wrangler-action` に一本化・Workers Builds は不採用」だが、GitHub Actions がプラットフォーム側の制限で起動できないため、現在は CI とデプロイの両方を Claude がセッションから直接実行する。**~~

🔵 **上書き済み（`D-31` / `D-32`・2026-08-21）**: 上の「原則」は **もう有効ではない**。デプロイの発火点は **Workers Builds** であり、🔴 **Actions の制限が解除されても GitHub Actions へは戻さない**（`D-31` の明示決定・移行手順は §8.2.3）。🔵 **品質チェックだけは `D-42`（2026-08-24）で Actions 化済み**（`.github/workflows/quality-checks.yml`）だが、これは **デプロイの経路とは無関係** であり、`D-31` / `D-32` を緩めるものではない。

`.github/workflows/deploy-preview.yml` と `deploy-production.yml` は撤去済みで、🔴 **復元しない**（発火点は Workers Builds へ移した・`D-31`）。品質チェックは二層構成: Prettier / ESLint / `tsc --noEmit` / Vitest は `.github/workflows/quality-checks.yml`（`D-42`）、E2E と Lighthouse を含む残りは `tools/run_checks.sh`（詳細は同スクリプトを参照。本書は参照のみ）で行う。

### 8.2. セッション実行の手順

**プレビュー（PR 作成前）**:

```bash
npm run check                 # = bash tools/run_checks.sh（permissions で許可済みの呼び出し形はこちら）
npx opennextjs-cloudflare build
npx wrangler versions upload --preview-alias "pr-<N>" --tag "$SHA"
```

出力された URL を **PR 本文に貼る**（`SD-1`）。🔴 **fail-closed を維持する**（旧 CI 版の思想を踏襲）: URL が取得できなければ、その場で PR を出さずに理由を特定するか、**PR 本文に「URL が取得できなかった理由」と「ローカル起動手順」を書く**（沈黙禁止・`SD-1`）。

**本番デプロイの発火点**（`D-26`・[ADR 0004](../../adr/0004-release-cycle-trunk-based.md) 追記）:

🔴 **本番デプロイの前に必ずゲート判定を通す。** マージ・push（公開反映）自体は妨げない — 止めるのは `npm run deploy` の呼び出しだけ。

| PR の種類 | デプロイの発火点 |
|---|---|
| **スプリント PR**（`Sprint Goal:` 行あり） | マージ直後にはデプロイしない。**スプリントレビュー判定が `accepted`（または `accepted_with_conditions` かつ `deploy: yes`）になった時点** でデプロイする。`rejected` の間はデプロイしない（fail-closed。プレビューは差し戻し検証にまだ使うため退役もしない） |
| **非スプリント PR**（改善 Issue・retro-try・docs 等） | 従来どおりマージ直後にデプロイを試みる。ただしその前に下記のゲート判定を通し、「待機」判定なら push のみで終える（デプロイの直列化。`main` は 1 本の Worker であり部分的デプロイができないため、判定未確定のスプリント成果物を巻き込んで出さない） |

🔴 **`deploy: no` の限界**: `tools/check_deploy_gate.py` は Sprint Review コメントの `**結果**:` 行しか見ない（`accepted_with_conditions` の `deploy: no` 条件は判定に入らない）。したがって `deploy: no` は **そのスプリント自身の Step 7 デプロイ発火だけ** を止め、それ以降に別の PR（非スプリント PR も含む）がマージされて `npm run deploy` が実行されると、`deploy: no` のコミットも main HEAD の一部として本番へ出てしまう。他 PR 経由でそのコミットが本番に出ることを防ぐ仕組みではない（既知の限界として運用する。設計判断は議論 round 2 のとおり）。

```bash
python3 tools/check_deploy_gate.py
# exit 0 = デプロイ可
# exit 1 = 待機（main 上に判定未確定 or rejected のスプリント Issue が残っている）
#          → push のみで終える。「デプロイ保留: 理由は #N の Sprint Review 未確定/rejected」を
#            Issue / PR コメントに記録する
# exit 2 = 判定不能 → デプロイしない（fail-closed）
```

**本番デプロイ**（ゲート判定が「デプロイ可」のときのみ実行）:

🔴 **一次経路は Workers Builds の再トリガー（`tools/trigger_workers_build.py`）、`npm run deploy` の手動実行はフォールバック**（`D-31` / `D-32` 移行後の実測を踏まえた改訂・詳細と実測根拠は §8.2.3「移行後の実測」）。理由: `main` への push は Workers Builds 側で常にビルドが走るが、push 時点でデプロイゲートが閉じていた分は **ゲートが開いたあとも自動では再試行されない**（Cloudflare 側の仕様）。そのままだと「マージは完了しているのに本番が古いまま滞留する」状態が静かに発生するため、ゲート通過を契機に **明示的に再ビルドを起こす** 必要がある。手動 `npm run deploy` は auto mode classifier にブロックされることがある（§8.2.2）ため二次手段に留める。

```bash
# 一次経路: Workers Builds の再トリガー（分類器の管轄外・Cloudflare のビルド環境で wrangler deploy が走る）
git fetch origin +main:refs/remotes/origin/main && git checkout origin/main
npm ci && npm run check       # 🔴 合成状態の検証（複数 PR がマージされた main HEAD で再実行する）
python3 tools/trigger_workers_build.py --wait
# → 内部でデプロイゲートを確認し、開いていれば Cloudflare Builds API 経由で main 最新コミットの
#   ビルドを再トリガーする（エンドポイント 3 段は §8.2.3「移行後の実測」参照）。閉じていれば
#   何もせず exit 1 で終わる（fail-closed のまま）。
# → 🔴 `--wait` はトリガー後にビルドの終端まで待ち、`build_outcome: success` 以外はすべて exit 2 で
#   終わる（既定の待機上限 900 秒・`--wait-timeout` / `--poll-interval` で調整可）。**`--wait` を
#   付けずに「トリガーした = 本番へ反映された」と断定しない**（Issue #497 はこの取り違えで、
#   ビルドが 55 秒で失敗しているのに気づけなかった）。
```

```bash
# 二次経路（フォールバック・一次が使えない/失敗したときのみ）: セッションから直接デプロイ
git fetch origin +main:refs/remotes/origin/main && git checkout origin/main
npm ci && npm run check       # 🔴 合成状態の検証（複数 PR がマージされた main HEAD で再実行する）
npm run deploy                # = opennextjs-cloudflare build && wrangler deploy（ビルドを含む形に統一）
curl -s -o /dev/null -w '%{http_code}\n' https://gem-hunter.<subdomain>.workers.dev/   # 5xx なら rollback を検討
```

実行結果（どちらの経路を使ったか・ゲート判定・デプロイ成功可否・URL・疎通確認の HTTP ステータス）は Issue / PR コメントに記録する（実行したことを黙らない）。

- 🔴 **フォールバック経路では `npm run deploy` を使う**（`wrangler deploy` 単独はビルド成果物 `.open-next/worker.js` を更新しないため、**古いビルドを本番へ反映してしまう**）。上記のとおり一次経路は `trigger_workers_build.py` であり、`npm run deploy` は **フォールバック経路でのみ使う**
- 🔴 **`npm run deploy` は本番 version に `--tag "$(git rev-parse --short=12 HEAD)"` を付ける**（Issue #288）。このタグが `tools/check_prod_drift.py` の厳密判定（SHA 一致）の入力になるため、**`wrangler deploy` を手で叩いてタグを省略しない**（省略すると乖離検知が日時ベースの緩い判定へ後退する）。`git rev-parse` が失敗したときは空タグでデプロイせずコマンド全体が失敗する
- 🔴 **deploy 前に `main` HEAD で `npm run check` を再実行する**。PR ブランチ単体のチェックでは、複数 PR がマージされた **合成状態** を検証できない（[ADR 0004](../../adr/0004-release-cycle-trunk-based.md) §3.3 がこのリスクの緩和策として挙げた「`main` マージ後のテストゲート」= #39 の代替。🔵 `D-42` で Vitest / Lint / 型は `main` への push でも Actions が回るようになったが、**E2E と Lighthouse は CI 対象外** のため本手順は維持する。上記のスプリントレビューゲートはこのテストゲートを **置き換えず拡張** する）
- **失敗したら本番へ進まない**（fail-closed）。疎通確認が 5xx なら `npx wrangler rollback` を検討し、判断と結果を記録する

### 8.2.1. 🔴 プレビュー環境の退役（Sprint Review accepted 後）

本番デプロイに成功したら、**そのスプリント PR の preview alias を退役する**（削除ではなく上書き。削除 API が存在しない理由は §6.1）。

```bash
python3 tools/retire_preview_aliases.py --list             # 対象確認（dry-run 兼用・書き込みなし）
python3 tools/retire_preview_aliases.py --alias "pr-<N>"    # 1 件だけ退役する
python3 tools/retire_preview_aliases.py --closed-prs        # クローズ済み PR 由来を一括退役する
python3 tools/retire_preview_aliases.py --closed-prs --alias sp1 --alias sp7   # 併用: 和集合で退役する
```

- 実体は `wrangler versions upload --preview-alias <name>` で **本番と同じビルド成果物を再アップロード** し、alias の実効ルーティング先を張り替えること。alias URL 自体は残り続けるが、古いスプリントのコードは配信されなくなる（version オブジェクト自体は削除されず残る・§6.1）
- 🔴 **`--closed-prs` は Sprint Review 判定を見ない**（`tools/retire_preview_aliases.py` の `select_closed_pr_aliases()` を確認）。判定基準は **PR の open/closed/merged だけ**（`pr-<N>` 形式の alias に紐づく PR がクローズ済みか）であり、`rejected` かどうかは判定に入らない。**`rejected` 判定の保護は Step 7（スプリントレビュー）からの自動退役の経路が担う** もので、`--closed-prs` の一括退役自体には効かない。squash マージ（Step 5）は Sprint Review（Step 7）より前に起きるため、差し戻し検証中（`rejected` で再検証待ち）のスプリントでも PR 自体は既にクローズ済みとなり、`--closed-prs` の対象に入ってしまう。**差し戻し検証中のスプリントがあるときは `--closed-prs` を使わず、対象を `--alias` で個別指定する**
- `--closed-prs` と `--alias` は併用でき、対象は和集合になる（`sorted(set(targets) | set(args.alias))`）。`pr-<N>` 形式でない alias（`sp1` / `sp7` / `form-uiux` 等）は `--closed-prs` の自動選別対象にならないため、これらを退役するには併用時の `--alias` 指定が実際の使い道になる
- 🔵 **`pr-<N>` の `N` が PR ではなく Issue 番号のケースにも対応済み**（Issue #613）。`/pulls/<N>` が 404 のときは `/issues/<N>` へフォールバックし、Issue が closed なら退役対象に含める（`issue:closed`）。open のままなら PR の open と同じく対象外にする（`issue:open`）。それでも Issue としても見つからない番号は従来どおり fail-closed で対象外
- 退役の実行結果（対象 alias・成否）は Issue / PR コメントに記録する

### 8.2.2. 🔴 本番デプロイは auto mode classifier にブロックされることがある（非決定的・2026-08-20 初出 / 2026-08-21 訂正・Issue #288 / #300）

**クラウド実行環境の Claude セッションは、上記 8.2 の「本番デプロイ」コマンド
（`npm run deploy` = `opennextjs-cloudflare build && wrangler deploy --tag "$(git rev-parse --short=12 HEAD)"`）が
`Permission for this action was denied by the Claude Code auto mode classifier. Reason: Blocked by classifier.`
で拒否されることがある。** 🔴 **毎回ではない**（2026-08-21 訂正・#300）: 実測は **ブロック 5 回・成功 2 回** で、
同一コマンド・同一 `permissions.allow` 設定でも結果が割れており、分かれ目は未確定。一方、
`npx opennextjs-cloudflare build`（ビルド）と `npx wrangler versions upload --preview-alias ...`（プレビュー反映）は
一貫して成功する。**ブロック対象は本番反映（`wrangler deploy`）そのものに限られる**（実測の内訳・一次情報の出典・
リトライの上限を含む行動指針は [`docs/rules/lessons/cloud-environment.md` L-130](../../rules/lessons/cloud-environment.md) 参照）。

一次情報（公式ドキュメント）によれば、auto mode classifier は `permissions` システムの後段で動く
第二のゲートであり、本番デプロイは分類器の組み込み保護対象（`soft_deny`）として明示的に扱われる。
分類器の設定（`autoMode`）はプロジェクトの `.claude/settings.json` からは読まれず、ユーザー設定
`~/.claude/settings.json` または managed settings のみが対象になる。セッション内からの解除は公式に
非対応（`anthropics/claude-code` Issue #60004・Closed as not planned）。

**結果として、「マージ = 本番反映」ではなく、マージ（公開反映）と本番デプロイの実行は分離している。**
マージ・push は自律的に完了できるが、本番デプロイの実行そのものはこの制約に阻まれる場面がある
（上記 8.2 のゲート判定を通過していても実行できない）。🔴 **「必ずブロックされる」と決めつけて試さないのも誤り**
（実際に通る経路を最初から諦めることになる）。ブロックされたときのリトライは同一セッション内で 1 回まで（`L-130`）。

**乖離検知**: `main` の内容と本番稼働中のコードが乖離していないかは `tools/check_prod_drift.py`
で検知する（実装は別レーンが担当。オプション・終了コードの詳細は同スクリプト自身を参照する）。

**🟢 決定済みなのは「発火点の移行先」だけ（2026-08-21・飼い主決定 = `D-31`）: 下記 5（Workers Builds）を採用する。**
🟢 **デプロイのタイミングを決める運用（`D-26` のデプロイゲート）も決定済み**（2026-08-21・P-1 = 案 (a)）:
Deploy command をゲート込みの `npm run deploy:ci` にすることで、Workers Builds へ移行しても `D-26` は維持される。
移行手順・設定値は §8.2.3。
以下は検討した選択肢の全体（いずれも飼い主の判断・実行が必要で、Claude が自律的に設定変更を行って
解除する経路ではない）:

1. `~/.claude/settings.json`（ユーザー設定）の `autoMode.allow` に本番デプロイを許可する例外ルールを
   追加する
2. Organization の managed settings 側で `autoMode` を調整する（組織管理者権限が必要）
3. 分類器がブロックした都度、Claude Code の `/permissions` 画面「Recently denied」からユーザー自身が
   手動で承認・リトライする（🔴 **無人ルーティンでは `/permissions` 画面が存在せず機能しない**。
   有人セッション限定の手段）
4. 本番デプロイの実行自体を、飼い主自身（または GitHub Actions の制限が解除された場合は CI/CD）が担う
   運用に切り替える（🔴 **採らない**。制限が解除された現在も **デプロイに GitHub Actions は使わない**・`D-31` / `D-42`）
5. ✅ **採用（`D-31`）: [Workers Builds](https://developers.cloudflare.com/workers/ci-cd/builds/)（Cloudflare native の Git 連携）へ発火点を移す**
   — Cloudflare ダッシュボードで Worker に GitHub リポジトリを接続すると、**`main` への push ごとに
   Cloudflare 側がビルドしてデプロイする**。Claude は `wrangler deploy` を打つ必要がなくなり、分類器と
   構造的に衝突しなくなる（マージ = 本番反映に戻る）

> 🔵 **5 が構造的な解決である理由**: 1〜3 は分類器の保護を弱める方向で、しかも 1 は飼い主の全プロジェクト・
> 全セッションに影響する。4 は自律運用（`CP-6`）を後退させる。5 だけが **Claude の権限を広げずに**
> マージから本番反映までを自動化する。
>
> ⚠️ **5 の前提**: Cloudflare の GitHub App の接続は **ダッシュボードでの 1 回きりの対話的認可が必須** で
> API からは実行できない（[API リファレンス](https://developers.cloudflare.com/workers/ci-cd/builds/api-reference/)
> が明記）。接続後のビルド設定・手動トリガーは API で操作できる。また **ダッシュボード上の Worker 名と
> Wrangler 設定の `name` が一致していないとビルドが失敗する**。
>
> ⚠️ **5 を採るときに検証が要る点**: 本プロジェクトは OpenNext（`opennextjs-cloudflare build`）を挟むため、
> Workers Builds のビルドコマンドをその形に設定できるか・シークレット（`wrangler secret`）が
> ビルド環境から参照できるかを、切り替え前に確認する。

### 8.2.3. Workers Builds への移行手順（`D-31`・Issue #288 完了条件 4）

🔴 **`D-16` は「CI は GitHub Actions + `cloudflare/wrangler-action` とし Workers Builds は採用しない」と
決めていた。`D-31` はこの部分だけを上書きする**（Cloudflare を使う選択・wrangler を一次経路とする点は不変）。
上書きの理由は ① GitHub Actions がプラットフォーム側の制限で起動できない（`D-23`）② セッションからの
`wrangler deploy` が auto mode classifier に阻まれる（§8.2.2）— つまり `D-16` 当時に想定した 2 経路が
**どちらも塞がった** ため。

#### 🔴 接続の前に決める・確認すること（前提条件・省略不可）

⚠️ **ダッシュボードでの接続は「決めてから」行う。** 接続した瞬間から `main` への push が本番へ流れ始めるため、
下記が未解決のまま接続すると **`D-26` のデプロイゲートが無効化される**（`rejected` 判定のスプリントも本番で
稼働し続ける）。🟢 **P-1 / P-2 はいずれも 2026-08-21 に決着済み**（下記）。接続を依頼できる状態にゃ。

**P-1. `D-26` のデプロイゲートをどう維持するか（🟢 決定済み・2026-08-21・議論記録 `content/discussions/prod-deploy-gate-20260821/whiteboard.md`）**

`D-26` は「`Sprint Goal:` 行のあるスプリント PR は、マージ直後ではなく **Sprint Review 判定が `accepted`
になった時点** でデプロイする（`rejected` の間はデプロイしない・fail-closed）」と定めている。一方 Workers Builds は
**push をトリガーにする** ため、素のままでは `tools/check_deploy_gate.py` が呼ばれず判定を飛ばして本番へ出る。

🟢 **採用: 案 (a) — Deploy command をゲート込みにする。** Workers Builds の本番ブランチは `main`（リポジトリの
default branch）のままとし、Deploy command に `npm run deploy:ci`（= `bash tools/workers_build_deploy.sh`）を指定する。
このスクリプトはビルド環境で `python3 tools/check_deploy_gate.py` を実行し、**exit 0 のときだけ `npm run deploy` へ進む**。

🔴 **ゲートが閉じているときは exit 0 で握り潰さず、その終了コードのままビルドを失敗させる。**
Workers Builds が「Deploy command が exit 0 でデプロイしなかった場合にビルドを成功扱いにするか」を公式ドキュメントに
明記していない（2026-08-21 時点で未確認）ため、その未文書の挙動に依存しない設計にしている。
**ビルドが赤くなるのは「デプロイ保留中」の可視化であって故障ではない**（本番は更新されていない = fail-closed が成立している）。

| 案 | 内容 | 判定 |
|---|---|---|
| **(a)** ✅ | Deploy command をゲート込みにする（`npm run deploy:ci`） | **採用**。ビルドイメージには Python 3.13.3 と git がプリインストール済み（公式 build-image で確認）。Claude が実行するアクションは「`main` へのマージ」だけになり、`wrangler deploy` は分類器の管轄外（Cloudflare のビルド環境）へ移る |
| (b) | Sprint Review 判定が出るまで `main` にマージしない | **非採用**。Sprint Review の滞留が `main` への統合全体を止め、非スプリント PR まで巻き込む（#288 / #308 が実際に滞留した） |
| (c) | `deploy-live` 専用ブランチを本番ブランチに指定し、ゲート判定はセッション側で実行する | **検討のうえ撤回**。分類器は **non-default branch のうち名前がデプロイ先を示すもの**（`production` / `release` / `gh-pages` 等）への push を独自に本番デプロイと判定する。しかも分類器は CLAUDE.md とドキュメントを読むため、**正しく文書化するほど検知されやすくなる**。名前を隠して回避するのは `L-130` の迂回禁止に触れる |

**P-2. シークレットの引き継ぎ（🟢 決定済み・専用の検証ビルドは挟まない）**

Wrangler の公式ドキュメントが **「Wrangler will not delete your secrets (encrypted environment variables) unless you
run `wrangler secret delete <key>`」「Secrets are never deleted by a deployment」** と明記しており、これは
**実行元の環境に依存しない一般仕様**（secrets は Cloudflare アカウント側の Worker に紐づく）。したがって
「Deploy command を一時的に `echo skip` にして無害化ビルドを 1 回走らせる」という当初案は **過剰なので採らない**
（手順を 1 段増やすだけで得るものがない）。

代わりに **初回の実デプロイの前後で確認する**:

1. 初回デプロイ前に `npx wrangler secret list` を実行し、既存 secrets の **名前一覧**（`RATE_LIMIT_SALT` を含む）を記録する
2. デプロイ後に同じコマンドを再実行し、名前一覧が一致することを突合する
3. レート制限が効く経路（§3.3「適用経路（正本）」の ✅ 適用 行）へ短時間に連続アクセスし、制限応答が返ることを確認する。**検索（`/{locale}` または `GET /api/search`）と Gem 一覧（`/{locale}/gems`）をそれぞれ 1 回ずつ** 確認する（キー接頭辞が `search:` / `gems:` で分かれた独立枠のため、片方だけでは他方の配線漏れに気づけない）
   （🔴 `RATE_LIMIT_SALT` が未解決だと **フェイルオープンでエラーにならない** ため、動作で確かめないと気づけない）

#### 飼い主の操作（API では実行できない・1 回だけ）

Cloudflare の GitHub App の接続は **ダッシュボードでの対話的認可が必須** で、API 経路が存在しない
（[API リファレンス](https://developers.cloudflare.com/workers/ci-cd/builds/api-reference/) が明記）。
手順は `[user-work]` Issue に切り出す。

#### 設定値（接続後にダッシュボードで入れる）

| 項目 | 値 | 根拠 |
|---|---|---|
| Worker 名 | `gem-hunter` | 🔴 **ダッシュボード上の Worker 名と `wrangler.jsonc` の `name` が一致していないとビルドが失敗する**（[公式](https://developers.cloudflare.com/workers/ci-cd/builds/troubleshoot/)）。本プロジェクトは一致済み |
| 本番ブランチ | `main` | trunk-based（`D-21`） |
| Build command | **空にする** | `npm run deploy` が `opennextjs-cloudflare build` を内包しているため、build と deploy を二重に走らせない |
| Deploy command | `npm run deploy:ci` | = `bash tools/workers_build_deploy.sh`。`D-26` のゲート判定を通してから `npm run deploy` を実行する（P-1 の決定）。既定の `npx wrangler deploy` のままだと ① OpenNext のビルド成果物が更新されない ② ゲートが素通りする、の 2 つの罠を踏む。SHA タグ付与も `npm run deploy` 側に入っている |
| Non-production branch builds | 🔴 **有効化しない**（本番ブランチのトリガーだけを接続する） | 既定の `npx wrangler versions upload` は **alias を付けない**。PR ごとのプレビューは既存の `--preview-alias pr-<N>` 運用（§6.1）が担っており、両方走ると ① レビュアーがどちらの URL が最新か誤認する ② alias なし version は `retire_preview_aliases.py`（`pr-<N>` 形式のみ判定）の **退役対象外** になり orphan として蓄積する ③ push のたびに Cloudflare API のレート制限（#117 で 248 秒待機を実測）を追加消費する。**一本化するなら退役スクリプトを alias なし version に対応させてから**（別 Issue） |
| Build variables and secrets | 🔴 **`GH_TOKEN` を Secret 種別で登録する**（+ Next.js のビルドに必要な変数があればここへ） | `npm run deploy:ci` が呼ぶ `check_deploy_gate.py` は GitHub API で Issue を読む。ビルド環境に `gh` は無いので `GH_TOKEN` / `GITHUB_TOKEN` のフォールバック経路を使う。🔴 **専用の fine-grained PAT を新規発行し、対象リポジトリを `gem-hunter` のみ・権限を `Issues: Read-only` + `Metadata: Read-only` に限定する**（他用途のトークンを流用しない。classic PAT の `repo` スコープは過剰権限）。有効期限を設定しておくと、切れたときにビルドが赤くなって気づける。⚠️ ビルド変数は `npm run deploy` を含む同一ビルド環境の全プロセス（npm 依存パッケージのライフサイクルスクリプトを含む）から参照できるため、**権限を絞ることが唯一の緩和策**。[公式の Next.js ガイド](https://developers.cloudflare.com/workers/framework-guides/web-apps/nextjs/)のとおり **ビルド変数はランタイムには渡らない**（ランタイム値は Settings → Variables & Secrets 側） |

#### 🔴 接続作業で実際に踏んだ罠（2026-08-21 実測・#290）

飼い主の接続作業に立ち会って観測した事実を残す。**次に同じ作業をする人が同じ穴に落ちないための節** にゃ。

**罠 1: 既定値のまま接続すると 3 つ同時に踏む**

接続ダイアログの初期値は次のようになっており、そのまま「接続」を押すと 3 つの罠を同時に踏む。

| 項目 | 既定値 | あるべき値と理由 |
|---|---|---|
| ビルド コマンド | `pnpm run build` | 上の「設定値」表の `Build command` 行を参照（**空にする**）。本プロジェクトは npm 運用なので、この既定値はそもそもコマンドとして成立しない |
| デプロイ コマンド | `npx wrangler deploy` | 上の「設定値」表の `Deploy command` 行を参照（`npm run deploy:ci`） |
| プレビュービルドを有効化 | ✅ **チェック済み** | 上の「設定値」表の `Non-production branch builds` 行を参照（**有効化しない**） |

🔵 **各項目の理由は上の「設定値」表が正本**（ここに再掲しない）。本表が伝えるのは
**「既定値のまま押すと 3 つ同時に踏む」という事実そのもの** にゃ。

→ **接続ダイアログの時点で 3 つとも直してから「接続」を押す**（後から直すこともできるが、接続直後に `main` へ push が入ると誤った設定でデプロイが走る）。

**罠 2: `GH_TOKEN` を入れる「変数とシークレット」が 2 か所ある**

Worker の設定ページには **同名のセクションが 2 つ** ある。

| 場所 | 何のためのものか | `GH_TOKEN` を入れる場所か |
|---|---|---|
| 設定 → **変数とシークレット**（`GITHUB_APP_CLIENT_ID` / `RATE_LIMIT_SALT` が並ぶ側） | **アプリのランタイム** 変数 | ❌ **違う**。ここに入れてもビルド環境からは読めず、しかも **アプリの実行環境にトークンが露出する** |
| 設定 → **ビルド** セクション内の **変数とシークレット**（`API トークン` / `デプロイ フック` / `ビルド キャッシュ` と並ぶ側） | **ビルド環境** の変数 | ✅ **こちら** |

→ 見分け方は **同じカード内に「API トークン」「デプロイ フック」「ビルド キャッシュ」があるか**。あればビルド側にゃ。

**罠 3: 接続直後に「Git アカウントから切断されています」警告が出ることがある**

接続レコード自体は作られている（API の `repo_connection` に `deleted_on: null` で存在する）のに、ダッシュボードに
「このプロジェクトは Git アカウントから切断されています。これによりデプロイが失敗する可能性があります」という警告が出た。
**GitHub 側（`https://github.com/settings/installations`）で Cloudflare のアプリにリポジトリを追加すると警告は消えた**。

⚠️ API の `repo_connection.grant_id` は警告が消えたあとも `null` のままだった。**`grant_id` を接続の健全性判定に使わない**
（この API では常に `null` の可能性がある。判定はダッシュボードの警告表示か実ビルドの成否で行う）。

**罠 4: 初回は手動ビルドボタンが無い**

ビルド履歴が 1 件も無いうちは「再試行」系のボタンが出ず、ダッシュボードには
「Git リポジトリにコミットをプッシュして最初のビルドを開始できるようになりました」と表示される。
→ **初回ビルドは `main` への push で起こす**（`A-1` により直接 push は禁止なので、PR をマージして起こす）。

**🟢 接続後の設定変更は API で完結する（実測）**

`GET /accounts/{account_id}/builds/workers/{worker_tag}/triggers` で trigger 一覧（`trigger_uuid` を含む）が取れ、
`PATCH /accounts/{account_id}/builds/triggers/{trigger_uuid}` で `build_command` / `deploy_command` を更新できることを実機で確認した
（`worker_tag` は `GET /accounts/{account_id}/workers/scripts` の `tag` フィールド）。
⚠️ `branch_includes` に空配列を渡すと `12002 Invalid request body` で拒否される（trigger の無効化には使えない）。
プレビュー trigger を無くしたいときは **ダッシュボードで「プレビュービルドを有効化」のチェックを外す**（＝ 非本番 trigger を作らない）。

#### 🔴 移行前に検証する 3 点

1. **シークレットの引き継ぎ**: 本プロジェクトは version + preview alias 運用のため `wrangler versions secret put`
   でシークレットを入れている（§7.2.1）。Workers Builds が実行する `wrangler deploy` で、これらが
   引き続き解決されるかを実機で確認する（未確認のまま切り替えると本番が認証なしで動く）
2. **SHA タグの付与**: Workers Builds のビルド環境で `git rev-parse` が使えるか。使えない場合は
   `npm run deploy` を、Workers Builds が注入する `WORKERS_CI_COMMIT_SHA`
   （[2025-06-10 changelog](https://developers.cloudflare.com/changelog/post/2025-06-10-default-env-vars/)）を
   優先して読む形に変える。**タグが落ちると `tools/check_prod_drift.py` が heuristic 判定へ後退する**
3. **Node バージョン**: `package.json` の `engines.node` は `>=22`。ビルド環境の既定が下回る場合は
   ビルド変数で指定する

#### 🔴 壊れたデプロイが流れ続けるときの停止手順（runbook）

GitHub App の **切断** は接続と同様にダッシュボード操作が必須で、Claude は自律的に止められない。
一次対応として次を試す。⚠️ **「未検証」の射程に注意**: 下記 1 の `deploy_command` の PATCH 自体は
§8.2.3 上部の「接続後の設定変更は API で完結する（実測）」で **動作確認済み** にゃ。未検証なのは
**停止目的での実運用**（使用中のトークンに Workers Builds Configuration の Edit 権限があるか・
書き換えが実際に進行中のデプロイを止めるか）の部分だけ:

1. Builds API の `PATCH /accounts/{account_id}/builds/triggers/{trigger_uuid}` で **Deploy command を
   無害なコマンド（`echo halted`）へ書き換える** → 以降の push はビルドされてもデプロイされない
   - 🔴 使用中の `CLOUDFLARE_API_TOKEN` に **Workers Builds Configuration の Edit 権限があるかを事前確認する**
     （無ければこの経路は使えないので、その場合は 2 のみが手段になる）
2. 飼い主へ切断を依頼する（`A-6`）
3. 直前の正常な version へ戻す（`INF-21` のロールバック手順・§8 の既存記述）

⚠️ **`previews_enabled` の全体トグルは使わない**（`D-26` のとおり、並行中の他 PR のプレビューまで
一括無効化して `SD-1` と両立しない）。

#### 移行後に変わること

- ✅ **「マージ = 本番反映」が回復する**（`INF-20` の原則へ復帰。`D-23` で暫定緩和した部分が不要になる）
- ✅ Claude は `wrangler deploy` を打たなくなるため、分類器と構造的に衝突しない（`L-130` の制約が
  デプロイ経路に影響しなくなる。**ただし制約自体は残るので `L-130` は削除しない**）
- ✅ `tools/check_deploy_gate.py` によるゲート判定（`D-26`: スプリント PR は Sprint Review 判定まで
  デプロイしない）は **Deploy command の中で維持される**（P-1 の決定・`npm run deploy:ci`）。ゲートが閉じている
  間はビルドが失敗扱いになり、本番は更新されない（fail-closed）
- ⚠️ ゲート待機のたびにダッシュボードへ赤いビルドが残る。これは異常ではなく「デプロイ保留中」の可視化にゃ

#### 🔴 移行後の実測（2026-08-23 JST・Issue #451・追記）

上の「移行後に変わること」は接続直後の設計意図であり、**Git 連携・ゲート込み Deploy command のどちらも実際に正しく機能していた**（この 2 点は撤回しない）。一方で **「マージ = 本番反映が回復する」という結論部分だけが不正確だった**。実測で確定した事実は以下のとおり。

- **Git 連携は壊れていない**: Cloudflare Builds API（`GET /accounts/{account_id}/builds/workers/{worker_tag}/builds`）で直近 24 件のビルドを確認したところ、`repo_connection: kai-kou/gem-hunter` / `branch_includes: ["main"]` / `deploy_command: "npm run deploy:ci"` が正しく設定され、`main` への push ごとにビルドは **発火していた**（`SP-17`〜`SP-19` のコミットを含む）。
- **その 24 件すべてが `build_outcome: "fail"`** だった。最新ビルドのログ実文（`a621fea` 分・2026-08-22 10:05 JST）:
  ```
  Executing user deploy command: npm run deploy:ci
  > bash tools/workers_build_deploy.sh
  デプロイ待機: 以下の Issue がゲートを塞いでいます
    #389 feat: SP-19 検索語を引き継ぐ Gem 一覧ページを追加する — Sprint Review 判定が未実施です
  [workers-build-deploy] デプロイを実行しません（ゲート終了コード: 1）。
  [workers-build-deploy] ビルドが赤くなるのは想定どおりの挙動です（本番は更新されていません）。
  Failed: error occurred while running deploy command
  ```
  → `D-32` が意図した fail-closed（ゲートが閉じていれば本番を更新しない）は実測でも正しく成立している。全 24 件で本番は更新されていない。
- **不足していたのは「ゲート通過後に再ビルドを起こす経路」**。デプロイゲート（`D-26`）は Sprint Review 判定が出るまで **あとで開く** 性質を持つが、塞がれた時点の push は Cloudflare 側で失敗ビルドとして記録されるだけで、**ゲートが後から開いても Cloudflare は自動的に再試行しない**。結果、セッションが手動で `npm run deploy` を打たない限り本番が古いまま滞留する（`D-31` が回避しようとしていた `L-130`＝分類器ブロックへの依存が、この救済経路として実運用に残り続けていた）。
- **滞留は静かに起きる**: `tools/check_prod_drift.py`（本番と `main` HEAD の乖離を検出する専用スクリプト）は `tools/run_checks.sh` から `--self-test`（自己診断）としてしか呼ばれておらず、**本判定モードがどの定期ルーティンからも呼ばれていなかった**。乖離が発生してもアラートが上がらない状態だった。
- 実測時点の本番は手動デプロイで `main` HEAD（`a621fea`）に追いついていた（`wrangler deployments list` の最新 tag `a621fead113b` が HEAD と一致・`source: "wrangler"` = Workers Builds 経由ではなく手動デプロイ由来）。

**対策**（実装は別レーンが担当・本節は事実の記録）:

1. `tools/trigger_workers_build.py`（新規）を一次のデプロイ経路として追加した。Cloudflare Builds API を次の 3 段で呼び、`main` の最新コミットのビルドを明示的に再トリガーする（内部でデプロイゲートを先に確認し、閉じていれば何もしない）:
   - `GET /accounts/{account_id}/workers/scripts` → `worker_tag` を取得
   - `GET /accounts/{account_id}/builds/workers/{worker_tag}/triggers` → `trigger_uuid` を取得
   - `POST /accounts/{account_id}/builds/triggers/{trigger_uuid}/builds` → 再ビルドを起こす
2. Sprint Review 判定コメント投稿を検知する経路（Step 7 のデプロイ発火）の一次手段を、手動 `npm run deploy` からこの再トリガーへ切り替えた（上の §8.2「本番デプロイ」参照。`npm run deploy` の手動実行はフォールバックとして残す）。
3. スプリント自走ルーティンのプリフライトに `tools/check_prod_drift.py` の **本判定モード** を配線し、乖離を検出したら再トリガーを試み、ゲート待機中ならその滞留を可視化する。

### 8.2.4. 🔴 ビルド環境の依存インストール契約（npm の install スクリプト既定ブロック・Issue #497）

Workers Builds のビルド環境の npm は **依存の install スクリプト（`preinstall` / `install` / `postinstall`）を既定でブロックする**（npm 11.15 で導入・npm 12 で既定 off）。ローカルの `node_modules` は古い npm で作られているため気づけず、**本番ビルドだけが落ちる** 形で現れる。実測（npm 12.0.2 で `npm ci` を再現）で分かった失敗は 2 つある。

| # | 何が起きるか | 症状 | 対策（正本は `package.json`） |
|---|---|---|---|
| 1 | `esbuild` / `workerd` / `msw` / `unrs-resolver` の postinstall が走らず、ネイティブバイナリが配置されない | `npm warn install-scripts ... blocked because they are not covered by allowScripts` | `package.json` の **`allowScripts`** に許可を宣言する（`npm install-scripts approve <pkg> --no-allow-scripts-pin`）。バージョン固定しない形（`"esbuild": true`）で書き、依存更新のたびにビルドが落ちないようにする |
| 2 | トップレベルの `node_modules/esbuild` が入らない | `Error [ERR_MODULE_NOT_FOUND]: Cannot find package 'esbuild' imported from .../@opennextjs/cloudflare/dist/cli/build/bundle-server.js` | `esbuild` を **直接の devDependency として宣言する**。`@opennextjs/cloudflare` は `esbuild` を bare import するのに自身の依存として持たないため、宣言が無いと `vite` の **optional peer dependency** 経由の巻き上げに依存する。npm 12 の `npm ci` はこの optional peer を入れないので解決できなくなる |

🔴 **この 2 点は `python3 tools/check_install_scripts_policy.py`（`npm run check` に配線済み）が静的に検査する。** lockfile の `hasInstallScript` を `allowScripts` と突き合わせ、必須の直接依存の宣言も見る。install スクリプトを持つ依存を新たに増やしたときは、この検査が落ちるので `npm install-scripts approve` で明示的に許可する（黙って通さない）。

### 8.3. 🔴 プレビュー URL は fail-closed で扱う（手動実行版）

`SD-1`（PR に開けるプレビュー URL がある）が **サイレントに欠落する経路を塞ぐ**。CI 版と同じ検証をセッション側のコマンドとして実行する。

```bash
npx wrangler versions upload --preview-alias "pr-<N>" --tag "$SHA" 2>&1 | tee wrangler-out.log
URL=$(grep -oE 'https://[a-zA-Z0-9.-]+\.workers\.dev' wrangler-out.log | head -1)

if [ -z "$URL" ]; then
  echo "wrangler がプレビュー URL を出力しなかった（stdout 形式が変わった可能性）"
  # → PR 本文に理由とローカル起動手順を書く（沈黙禁止）
fi

for i in 1 2 3; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "$URL") && [ "$code" -lt 500 ] && break
  sleep 5
done
```

- **主経路は stdout の正規表現抽出**。`WRANGLER_OUTPUT_FILE_PATH` の ND-JSON は **フィールド名が未確認** のため検証専用に留める（§12 の 6）
- URL を PR へ投稿したあと、**投稿が反映されたことまで確認** して初めて成功とする

### 8.4. ~~🔴 復帰条件と手順（GitHub Actions の制限が解除されたら）~~（廃止・`D-31` により Workers Builds へ移行済み）

🔴 **この節の手順は実行しない。** デプロイの発火点は `D-31` / `D-32` で **Workers Builds** に決まっており、GitHub Actions へは戻さない（現行の手順は §8.2.3）。🔵 `D-42`（2026-08-24）で Actions の制限解除が明文化されたが、**それが解禁したのは品質チェックだけ** であり、本節の発火条件（「制限が解除されたら」）を満たすものではない。以下は経緯として取り消し線で残す。

1. ~~**ワークフローの復元**: 削除した `deploy-preview.yml` / `deploy-production.yml` の YAML 全文は git 履歴に残っている。`git log -- .github/workflows/` で削除前のコミットを特定し、`git show <commit>:.github/workflows/deploy-preview.yml` 等で内容を復元する（本書には全文を残さない）~~ — 🔴 **復元しない**（`D-31`）
2. ~~**fail-closed 検証の復帰**: §8.3 の URL 抽出・5xx リトライロジックを、CI のステップ（`::error::` + `exit 1` での失敗化）としてワークフローに戻す~~ — fail-closed は Workers Builds の Deploy command 側（`npm run deploy:ci`）が担う（`D-32`・§8.2.3）
3. ~~**`INF-20` の原則復帰**: §7.5 の暫定緩和を終了し、「デプロイのトリガーは git push / マージのみ」に一本化する。`infrastructure-design.md` の `INF-20` 注記・`open-questions.md` の `D-23` を「復帰済み」に更新する~~ — 原則復帰の経路は Workers Builds への移行に置き換わった（§8.2.3）
4. ~~**セッション実行の手動デプロイ経路を残さない**（`INF-20` の原則に戻す。§8.2 の手動コマンドは以後使わない）~~ — 🔴 **手動フォールバックは残す**（プレビュー URL 取得とゲート通過後の再デプロイに必要・§7.5）
5. ~~`actions/setup-node` は **`node-version: 22` 以上**（wrangler 4.x の要件）を復元時も維持する~~ — デプロイ用ワークフローを持たないため対象外（`quality-checks.yml` は Node 22 を使用）

---

## 9. プライバシー設定（`INF-1` / `D-14`）

### 9.1. 設定する項目

| # | 設定 | 場所 |
|---|---|---|
| 1 | **invocation ログを無効化する** | `wrangler.jsonc` の `observability.logs.invocation_logs: false` |
| 2 | **Rate Limiting の key を HMAC 化する**（生 IP を渡さない） | key 生成は `src/infrastructure/platform/rate-limit-key.ts` の `hashRateLimitKey()`（HMAC-SHA256(salt, ip) の hex）。呼び出し口は `src/composition/rate-limit.ts`（§3.3 に配線の全体像）。salt は `wrangler versions secret put RATE_LIMIT_SALT`（§7.2.1）。**salt 未設定時はハッシュ化ではなくフェイルオープン**（判定自体をスキップする。生 IP へのフォールバックはしない） |
| 3 | **Bot Fight Mode を有効化しない** | Dashboard（既定オフのまま触らない） |
| 4 | **WAF Rate limiting rules を使わない** | Free は 1 ルール・IP 固定で `AR-5`（ログイン有無での枠分け）に使えない |

⚠️ **1 の理由**: invocation ログにクライアント IP が含まれるかは公式が列挙しておらず **未確認**。含まれる前提で切る（`INF-1` を守る側に倒す）。

### 9.2. アプリの制御外にあるもの（`infrastructure-design.md` §5.3 の Cloudflare 版）

同 §5.3 は「事業者標準のアクセスログはアプリの制御外」と留保していた。Cloudflare での回答は **「一部のみ制御できる」**。

| ログ | 保持期間 | アプリから無効化できるか |
|---|---|---|
| Workers Logs（invocation + custom） | Free 3 日 | 🟢 **できる**（§9.1 の 1） |
| Security Analytics | Free 7 日 | ❌ できない |
| Security Events | 24 時間 | ❌ できない |
| Audit Logs（アカウント操作） | 18 か月 | ❌ できない |

→ `infrastructure-design.md` §11 の評価軸 6（ログの保持期間・無効化可否）に対する Cloudflare の答えは **「アプリの invocation ログのみ無効化可、アカウント運用ログは不可」**。

---

## 10. `INF-5` の境界（機械的に判定できる形）

### 10.1. 規約

> 🔴 **Cloudflare bindings（`getCloudflareContext()` の戻り値・`env.KV` / `env.R2` / `env.D1` / `env.RATE_LIMITER` / `env.CACHE` / `env.IMAGES` 等）へのアクセスは `src/infrastructure/platform/` 配下のファイルからのみ行ってよい。** `app/`（Server Component / Route Handler）と `src/infrastructure/github/`（`NFR-16` のデータアクセス層）からの直接アクセスを禁止する。

> 🔴 **`wrangler.jsonc` / `open-next.config.ts` はリポジトリルートに置き、アプリの実行時分岐条件として読まない。**

### 10.2. 機械ゲート（`tools/self_review_check.py` に追加する）

```bash
# 違反 1: bindings への直接アクセスが src/infrastructure/platform/ の外にある
grep -rnE 'getCloudflareContext\(|env\.(KV|R2|D1|RATE_LIMITER|CACHE|IMAGES)\b' \
  --include='*.ts' --include='*.tsx' app/ src/ | grep -v '^src/infrastructure/platform/'
# 出力ゼロなら合格

# 違反 2: Cloudflare 環境変数を実行時の分岐条件にしている
grep -rnE 'process\.env\.(CF_|CLOUDFLARE_)|context\.env\.' \
  --include='*.ts' --include='*.tsx' app/
# 出力ゼロなら合格
```

### 10.3. 退避コスト（`infrastructure-design.md` §13 への追加分）

Cloudflare を離れるときに **追加で** 破棄・置換するもの。

- [ ] `wrangler.jsonc` を破棄する（bindings 定義・`observability` 設定を含む）
- [ ] `open-next.config.ts` と `@opennextjs/cloudflare` 依存を破棄する
- [ ] `.github/workflows/deploy-*.yml` を新事業者向けに置き換える
- [ ] `src/infrastructure/platform/` の実装を差し替える（**インターフェースと呼び出し側は変更しない**）
- [ ] `Cache-Control` ヘッダ制御は **破棄不要**（RFC 9111 準拠で事業者非依存）

🔵 **`app/` と `src/infrastructure/github/` に手を入れないことが合格条件**（`NFR-21`）。

---

## 11. 人間に残る作業

### 11.1. ブートストラップ（一度きり）

| # | 作業 | 所要 | なぜ CLI で代替できないか |
|---|---|---|---|
| **H-1** | Cloudflare Dashboard → My Profile > API Tokens → 「Edit Cloudflare Workers」テンプレートでトークンを 1 本発行する | 3 分 | `POST /user/tokens` には既存トークンが必要（ニワトリ卵）。公式が「初回は Dashboard で」と明記 |
| **H-2** | そのトークンと Account ID を **2 箇所** に貼る: ① GitHub リポジトリ Settings > Secrets and variables > Actions ② Claude.ai の環境変数設定 | 3 分 | クラウドセッションから `actions/*` API が 403 でブロックされる（`env-vars.md`）。セッション env への書き込みも人間操作 |
| **H-3** | **GitHub App を作成し、App ID / Client ID・秘密鍵・Installation ID を同じ 2 箇所に登録する**（権限は `contents:read` / `issues:read` / `metadata:read`）| 5 分 | アプリがサーバー側で使う認証情報（[`prd.md`](../../02_requirements/prd.md) §10・`D-20`）。App の作成・鍵の発行・インストールはいずれも GitHub アカウントの権限が要るため Claude が代行できない。**未設定でも未認証で動くが、レート枠が落ちる**。🟢 **本リポジトリでは対応済み**（Issue #31・実測検証は [ADR 0003](../../adr/0003-github-app-authentication.md)） |

🔵 **H-1 〜 H-3 が済めば、以降のリソース作成・デプロイ・プレビュー URL 生成・シークレット投入・トークンのローテーション発行はすべて Claude が非対話で実行できる。**

### 11.2. 条件付きで発生するもの

| # | 作業 | 発火条件 |
|---|---|---|
| **H-4** | レジストラでネームサーバーを Cloudflare へ変更する | 独自ドメインを使う場合のみ（`M-4` で判断） |
| **H-5** | Workers Paid（$5/月）への加入・支払い方法の登録 | §5.3 の実測ゲートが閾値超過を確定した場合のみ。🟢 **切替の可否は `D-19` で事前承認済み** |

### 11.3. 定常運用（`INF-4`）

**ゼロ**。デプロイは git トリガー、ロールバックは CLI、監視は CI の失敗通知で足りる。

🔴 **そのために、`H-1` の Cloudflare API トークンには TTL を設定しない**（`INF-4` を優先する。[`infrastructure-design.md`](./infrastructure-design.md) §9.4 の「PAT の有効期限更新」を発生させないための選択）。

🟢 **GitHub 側は `D-20`（GitHub App 方式）により、この問題が構造的に消えている**: 有効期限を持つのは 1 時間で自動失効する installation token であり、**アプリが毎回取り直すため人手の更新作業が発生しない**。人が保持するのは期限のない署名鍵だけになる（Fine-grained PAT を採っていた場合に残るはずだった定常作業が `INF-4` から落ちる）。

⚠️ **TTL を付ける運用に変えるなら、期限前に Issue を自動起票する仕組みの実装を同時に行う**（手当てなしに人手の定常作業を増やさない・`D-15`）。2 本目以降のトークンを `POST /accounts/{id}/tokens` で発行する場合も同じ判断を適用する。

---

## 12. 未確認事項（実装時に潰す）

| # | 未確認事項 | 潰し方 | 影響 |
|---|---|---|---|
| 1 | Next.js 16 + shadcn/ui の Worker バンドルが 3 MB（gzip）に収まるか | `SP-1` で計測（§5.3） | 大（Paid 要否） |
| 2 | RSC レンダリングの p95 CPU が 10 ms に収まるか | `SP-1` で計測（§5.3） | 大（Paid 要否） |
| 3 | `next-intl` のミドルウェアレス構成が現行版でサポートされるか | `SP-2` 着手前に context7 で一次確認。ダメならルーティングは自作に閉じる | 中 |
| 4 | Workers invocation log にクライアント IP が含まれるか | 含まれる前提で無効化（設計で回避済み） | 小 |
| 5 | Rate Limiting binding の課金有無 | 実装直前に料金ページを再確認 | 小 |
| 6 | `WRANGLER_OUTPUT_FILE_PATH` の `version-upload` エントリのフィールド名 | 初回 CI 実行で確認（主経路にしないので blocking ではない） | 小 |
| 7 | workers.dev サブドメインの初期登録を非対話で完結できるか | 初回デプロイで確認。失敗したら `H-1` と同時に Dashboard で 1 回設定 | 小 |
| 8 | GitHub アバターを `?s=N` で出す方式で `NFR-6`（CLS 0.1 以下）を満たせるか | `SP-1`〜`SP-2` で Lighthouse / DevTools により実測 | 中 |
| 9 | `observability.logs.invocation_logs: false` でも `wrangler tail` がライブログを拾えるか | `SP-5` の補助経路。主経路（`X-Cache-Status`）があるため blocking ではない | 小 |

---

## 13. 参照

| ドキュメント | 関係 |
|---|---|
| [`infrastructure-design.md`](./infrastructure-design.md) | `INF-n` 契約の正本。本書はその実装先を定める |
| [Cloudflare インフラ リサーチ](../../01_research/infra/20260818-cloudflare-research.md) | 数値・一次情報の出典 |
| [ADR 0002](../../adr/0002-cloudflare-workers-infrastructure.md) | 選定判断の記録 |
| [`prd.md`](../../02_requirements/prd.md) | 要件 ID・環境変数の正本 |
| [`open-questions.md`](../../02_requirements/open-questions.md) | `D-16` / `D-17` / `D-18` / `D-23`（CI/CD の暫定運用。品質チェック部分は `D-42` で失効）/ `D-24`（`D-18` の L2 実装改訂）/ `D-26`（プレビュー環境の退役・デプロイゲート）/ `D-31` / `D-32`（デプロイ発火点の Workers Builds 移行）/ `D-42`（品質チェックの Actions 化）の決定ログ |
| [議論記録](../../../content/discussions/cloudflare-infra-20260818/whiteboard.md) | 本設計に至った専門チームの議論 |
| [議論記録（2026-08-20）](../../../content/discussions/sprint-env-lifecycle-20260820/whiteboard.md) | プレビュー環境の退役・デプロイゲートに関する専門チームの議論 |
