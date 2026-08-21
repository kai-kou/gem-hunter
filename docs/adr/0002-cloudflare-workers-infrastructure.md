# ADR 0002: インフラを Cloudflare Workers（`@opennextjs/cloudflare`）に確定し、wrangler CLI を運用の一次経路にする

- **状態**: **承認** — ただし §7 の未確認事項 #1（Free の CPU / バンドル上限に収まるか）が `SP-1` の実測で確定するまで、**「月額 0 円で動く」とは報告しない**
- **日付**: 2026-08-18 JST
- **対応要件**: `D-5` / `D-7` / `D-11` / `D-13`〜`D-15` / `INF-1`〜`INF-22` / `NFR-17` / `NFR-21` / `TR-1`〜`TR-3` / `SD-1`
- **関連**: [Cloudflare インフラ設計](../03_design/infrastructure/cloudflare-infrastructure.md) / [事業者非依存インフラ設計](../03_design/infrastructure/infrastructure-design.md) / [リサーチ](../01_research/infra/20260818-cloudflare-research.md) / [議論記録](../../content/discussions/cloudflare-infra-20260818/whiteboard.md) / Issue #30

---

## 1. 文脈

[`infrastructure-design.md`](../03_design/infrastructure/infrastructure-design.md) は **事業者を決めないまま** インフラの契約（`INF-1`〜`INF-22`）を確定させ、選定を `M-1`（プレビュー・`D-11`）と `M-4`（本番・`D-7`）へ先送りしていた。§11 に評価軸 10 項目を用意し、「埋まらない軸があるなら選定してはいけない」としていた。

2026-08-18、ユーザーから明示の決定が示された。

> インフラについて Cloudflare ベースで進めたい。アカウントについては既存のものがあるのでそれを利用して必要なリソースを作成する。自律的な開発をするのに MCP よりも CLI を利用するほうが適しているので、その方針で。

権威順（[`intent-gate-rules.md`](../rules/intent-gate-rules.md): **ユーザー明示 > 仕様 > テスト > 現行コード**）により、この指示は §11 の評価軸を通した選定プロセスより上位にある。したがって本 ADR が扱うのは「Cloudflare を選ぶかどうか」ではなく、**Cloudflare を選んだうえで既存の契約（`INF-n`）を壊さない構成は何か** である。

一次情報リサーチと専門チームによる議論（5 レンズ・2 ラウンドの敵対的相互検証）を経て、以下を決定する。

---

## 2. 決定

| # | 決定 |
|---|---|
| 1 | **デプロイ先はプレビュー・本番とも Cloudflare Workers**（`D-16`）。`D-7` / `D-11` をクローズする |
| 2 | **ランタイムは `@opennextjs/cloudflare`**。`next` は **16.2.11 以上** にピンする（`D-17`） |
| 3 | **MVP のキャッシュは HTTP `Cache-Control` + Workers Caching のみ**。R2 / D1 / Durable Objects / KV は採用しない（`D-18`） |
| 4 | **`NFR-17` Cache Port は維持** し、実装位置を **`src/infrastructure/platform/`** と定める |
| 5 | **運用の一次経路は wrangler CLI**。Cloudflare MCP は読み取り 4 ツールのみアローリストで許可する |
| 6 | **CI は GitHub Actions + `cloudflare/wrangler-action`**。Workers Builds は採用しない |
| 7 | **Workers Free を初期値** とし、`SP-1` の実測ゲート（p95 CPU / gzip バンドル）で Paid 要否を判定する |
| 8 | **`Node.js Middleware` と `proxy.ts` を一切使わない**。`/` → `/ja` はルート Server Component の `redirect()` で実装する |

構成の詳細・コマンド・設定ファイルは [Cloudflare インフラ設計](../03_design/infrastructure/cloudflare-infrastructure.md) が正本。

> ⚠️ **追記（2026-08-19・`D-23`）**: 決定 #6（CI は GitHub Actions + `cloudflare/wrangler-action`）は、GitHub Actions がプラットフォーム側の制限で起動できない状態（Issue #65）を受けて **暫定的にセッション（Claude）実行へ切り替えている**。`.github/workflows/deploy-preview.yml` / `deploy-production.yml` は撤去済み。本 ADR の決定 #6 自体は取り消さず、制限解除後に GitHub Actions へ復帰する（現状の運用・復帰手順は [Cloudflare インフラ設計](../03_design/infrastructure/cloudflare-infrastructure.md) §8 が正本）。

> 🔴 **追記（2026-08-21・`D-31`）: 決定 #6 を取り消す。** 上の `D-23` 追記が想定していた「制限解除後に GitHub Actions へ復帰する」は **もう起こらない**。復帰ではなく **Workers Builds（Cloudflare native の Git 連携）への置き換え** を選択した。理由は `D-16` 当時に想定した 2 経路が **どちらも塞がった** こと: ① GitHub Actions がプラットフォーム側の制限で起動できない（`D-23`）② クラウドセッションからの `wrangler deploy` が Claude Code の auto mode classifier の組み込み保護対象で実行できない（Issue #288・[`L-130`](../rules/lessons/cloud-environment.md)）。**決定 #5（運用の一次経路は wrangler CLI）は変更しない**（Workers Builds が実行するのも wrangler である）。移行手順・設定値は [Cloudflare インフラ設計](../03_design/infrastructure/cloudflare-infrastructure.md) §8.2.3 が正本。

---

## 3. 理由

### 3.1. なぜ `@opennextjs/cloudflare` か（他に選択肢がない）

| 選択肢 | 判定 |
|---|---|
| `@opennextjs/cloudflare` + Workers | 🟢 Cloudflare 公式ドキュメントが唯一記載する現役経路 |
| `@cloudflare/next-on-pages` + Pages | 🔴 **npm 上で deprecated**（「Please use the OpenNext adapter instead」）。最終リリースは 2025-09-04 |
| 静的エクスポート + Static Assets | 🔴 サーバー実行がゼロになりコストは最小だが、**GitHub トークンをサーバー側に隠せない**（`NFR-9` 違反） |

### 3.2. 🔴 なぜ永続ストア（R2 / D1 / DO / KV）を採らないか

議論の最大の争点であり、**提案者自身が撤回して決着した**。

1. **`D-5` 追補との衝突**: 「サーバー側ストアを持たない構成を Phase 2 まで貫く」は MVP の都合ではなく **設計原則に格上げ済み**。R2 はライフサイクルで管理する永続オブジェクトストアであり、TTL 秒単位のエッジキャッシュとは質が違う
2. **`INF-2` の自壊**: R2 は **有効化に支払い方法の登録が必要**。Free plan の「超過したら課金ではなく停止（HTTP 1027）」という **構造的ハードキャップ** を、キャッシュのために自ら手放すことになる
3. **§6.2 のゲートを先取りしてしまう**: `infrastructure-design.md` §6.2 は L3 導入の条件を「レート制限起因のエラーの実発生 / ヒット率不足の観測 / Phase 2 の配信要件」の **観測** に限定している。MVP 前の現時点でどれも観測されていない
4. **未確認リスクを 3 製品に広げる**: Durable Objects は無料枠そのものが一次情報で確認できていない。`INF-2` の判定（超過時に停止するか）に答えられない製品を設計へ組み込まない

**代わりに使う HTTP `Cache-Control` + Workers Caching は、支払い方法の登録が不要で、かつ RFC 9111 準拠のため事業者非依存である。**

### 3.3. 🔴 なぜ Free を初期値にするか（優先順位の機械適用）

`infrastructure-design.md` §1 の優先順位は `INF-1` > `INF-3` > `INF-5` > `INF-2` > `INF-4`。`INF-3`（与件の技術スタックが動くこと）は `INF-2`（コスト）より上位なので、**衝突するなら Paid が正しい**。

しかし **衝突しているかどうか自体が未確定** である。Cloudflare の CPU 時間は wall clock と別会計で、GitHub API の待ち時間は CPU を消費しない。gem-hunter の主処理は「API を待って軽く整形する」であり、Free の 10 ms に本当に触れるかは実測しないと分からない。

→ **実測前に Paid を選ぶのは根拠のない前倒しの決定** であり、`INF-2` を不要に犠牲にする。判定式を設計に埋め込み（§5.3）、実測が閾値超過を示したときに初めて `INF-3` > `INF-2` を発動する。

### 3.4. なぜ Workers Builds ではなく GitHub Actions か

Workers Builds は初回接続に **GitHub App のインストール承認（GUI）** を要求する。CLI 一次方針と非対称であり、CI 系統が Cloudflare 側と GitHub Actions 側に分裂する。ビルド無料枠 3,000 分/月 を捨てる代償は、この規模のアプリでは小さい。

### 3.5. なぜ MCP を完全には捨てないか

ユーザー指示は「自律的な開発をするのに MCP よりも CLI を利用するほうが適している」であり、**理由が明記された優先順位の指定** である。読み取り専用の利用は移行チェックリストに何も残さず（退避コストゼロ）、`INF-5` にも `INF-1` にも影響しない。

ただし **書き込み系は使わない**。リソース ID を `wrangler.jsonc` にコミットする必要がある以上、MCP で作ると「実体は MCP 操作ログ、設定は git」という二重の真実になる。CLI なら正本が 1 つで済む。

---

## 4. 結果（この決定がもたらすもの）

### 良い方向

- **`INF-2` が構造的に満たされる**: Free を維持する限り、超過は課金ではなく停止に倒れる。「青天井の課金リスクを負わない」（§10.3）が設定ではなく **プラン選択そのもの** で担保される
- **`NFR-7`（request coalescing）が補助から主役級へ格上げされる**: Workers Caching のリクエスト合体は **エッジで効く**。`infrastructure-design.md` §4 が「インスタンス内でしか効かない」として補助扱いにしていた前提が変わる
- **静的アセットのコストがゼロになる**: Workers Static Assets へのリクエストは無料・無制限（`INF-10` / §10.1 のコストドライバ 2 が消える）
- **`INF-5` が目視判断から機械判定になる**: `src/infrastructure/platform/` 限定 + grep 2 本により、セルフレビューで自動検出できる
- **`INF-1` の留保が 1 段階解消される**: §5.3 が「事業者標準のアクセスログはアプリの制御外」としていた唯一の領域について、Workers の invocation ログは設定で無効化できる

### 受け入れる代償

- **`INF-3` の充足が実測待ちになる**: Free の CPU 10 ms / バンドル 3 MB に収まる保証がない。`SP-1` を通るまで「0 円で動く」と言えない
- **キャッシュがリクエスト数枠の防波堤にならない**: キャッシュヒットも Worker のリクエストとして課金される。`infrastructure-design.md` §10.2 の「同じ打ち手」という記述は 3 軸に分解して書き直す必要がある（本 PR で実施）
- **Paid へ移行するとハードキャップが消える**: リクエスト数課金の暴走を止める native な手段が存在しない（Budget alerts は通知のみ）。`limits.cpu_ms` と Billable Usage API による後追い封じ込めしか残らない
- **`INF-20` にブートストラップ例外が入る**: `SP-1` の CI 整備前だけ、Claude が手元から `wrangler versions upload` を叩く
- **人間の作業が 2 つ残る**: API トークンの初回発行と、その値を 2 箇所へ貼る作業（自動化不可能・§11）

---

## 5. 却下した選択肢

| 選択肢 | 却下理由 |
|---|---|
| **Cloudflare Pages + `next-on-pages`** | npm 上で deprecated。公式が Workers への移行ガイドを提供している |
| **静的エクスポート（サーバー実行ゼロ）** | GitHub トークンをサーバー側に隠せず `NFR-9` に違反する |
| **OpenNext incremental cache（R2 + D1 tag cache + DO queue）を MVP から導入** | §3.2 のとおり。提案者自身が議論の中で撤回した |
| **Cache Port の実装位置を `open-next.config.ts` にする** | `NFR-17` は「事業者固有ストアをデータアクセス層から隔離する抽象」であって ISR バックエンドの選択ではない。ISR を前提にしない本アプリでは配線先が違う |
| **実測前に Workers Paid を既定にする** | §3.3 のとおり、根拠のない前倒しの決定 |
| **Workers Builds（Git 連携ビルド）** | 初回接続が GUI 必須で CLI 一次方針と非対称。CI が 2 系統に分裂する |
| **`[env.*]`（Wrangler Environments）で PR ごとのプレビューを作る** | Worker が PR ごとに増え、Free の Worker 数上限 100 と棚卸しコストに直結する。versions + preview alias なら Worker は増えない |
| **`WRANGLER_OUTPUT_FILE_PATH`（ND-JSON）をプレビュー URL 取得の主経路にする** | `version-upload` エントリのフィールド名が未確認で、false negative で CI を落とすリスクがある |
| **Cloudflare MCP を完全に捨てる** | 読み取り専用の利用は退避コストがゼロで、指示の趣旨（自律開発の主経路を CLI にする）の射程外 |
| **本番デプロイ先（`D-7`）を `M-4` まで開けておく** | ユーザー明示決定が既にある以上、保留は判断ではなく仕様の惰性。ただし `M-4` は「公開するか否かのゲート」として維持する |

---

## 6. `NFR-21`（特定 PaaS 固有機能への依存を最小化）との整合

**本 ADR は `NFR-21` を破らない。** 破る境界を次のように明文化して機械判定にした。

| 層 | Cloudflare 依存 | 判定 |
|---|---|---|
| `app/` / `src/infrastructure/github/`（アプリランタイム層） | 🔴 **禁止**（bindings の直接参照・Cloudflare 環境変数による分岐） | grep 2 本で検出 |
| `src/infrastructure/platform/` | 🟢 許容（bindings への唯一の合法アクセス経路） | 差し替え時はここだけ書き換える |
| `wrangler.jsonc` / `open-next.config.ts` / `.github/workflows/` | 🟢 許容（デプロイ・運用層。`app/` の外） | 差し替え時は破棄する |

🔵 `NFR-21` は `D-11` の時点で既に「アプリのランタイムに対する制約であり、開発フローの道具への依存は対象外」と限定されている。本 ADR はその限定を **ディレクトリ境界と grep** に翻訳したものである。

---

## 7. 🔴 この決定に付随する未確認事項（実装時に潰す）

| # | 未確認事項 | いつ | 影響 |
|---|---|---|---|
| 1 | Next.js 16 App Router + shadcn/ui の Worker バンドルが **3 MB（gzip）** に収まるか / RSC の p95 CPU が **10 ms** に収まるか | `SP-1` の初回デプロイ直後に実測 | **大** — 満たせない場合は Workers Paid（`A-6`）が必要になる |
| 2 | `next-intl` のミドルウェアレス構成が現行版でサポートされるか | `SP-2` 着手前に context7 で一次確認 | 中 — ダメならロケール判定を自作に閉じる |
| 3 | Workers invocation log にクライアント IP が含まれるか | 含まれる前提で無効化済み（設計で回避） | 小 |
| 4 | Rate Limiting binding の課金有無 | 実装直前に料金ページを再確認 | 小 |
| 5 | workers.dev サブドメインの初期登録を非対話で完結できるか | 初回デプロイで確認 | 小 |

⚠️ **#1 が満たせないと判明した場合も本 ADR は supersede しない**（構成は変わらず、プランだけが変わる）。プラン変更の判断は `A-6` としてユーザーへ通知し、結果を本 ADR の §7 に追記する。

---

## 8. 参照

- [Cloudflare インフラ設計](../03_design/infrastructure/cloudflare-infrastructure.md)（構成の正本）
- [事業者非依存インフラ設計](../03_design/infrastructure/infrastructure-design.md)（`INF-n` 契約の正本）
- [Cloudflare インフラ リサーチ](../01_research/infra/20260818-cloudflare-research.md)（一次情報）
- [決定ログ `D-16` / `D-17` / `D-18`](../02_requirements/open-questions.md)
- [議論記録](../../content/discussions/cloudflare-infra-20260818/whiteboard.md)
