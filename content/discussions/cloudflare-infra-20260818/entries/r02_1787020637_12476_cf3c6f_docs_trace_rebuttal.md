<!--entry
author: docs_trace
round: 2
kind: rebuttal
ts: 2026-08-18T11:37:17+09:00
-->

# docs_trace Round 2 — ドキュメント突合と権威判定

## 問 1: キャッシュ実装の正面衝突（OpenNext incremental cache vs HTTP Cache-Control only）

### 権威は **既存ドキュメントで D-5 追補 / infrastructure-design.md §6.2 が明確に支持する**

**privacy_lockin 主張**: `open-next.config.ts` で `r2IncrementalCache` / `d1IncrementalCache` を設定し、ISR・`revalidateTag` のバックエンド を Cloudflare R2/D1 に寄せる（≒ persistent store 導入）

**cost_guard / cf_platform 主張**: HTTP Cache-Control + Workers Caching だけで MVP 完結。L2 cache（Next.js Data Cache）のみ。R2/D1 は Phase 2 以降。

### 既存ドキュメントの記述

**§A: D-5 追補（権威最上位・ユーザー明示決定・2026-08-17 記録）**
```
【D-5 追補】「DB を持たない」を MVP の都合ではなく設計原則に格上げする。
状態はクライアント側（localStorage / Cookie / URL）に寄せ、
サーバー側ストアを持たない構成を Phase 2 まで可能な限り貫く。
```

**§B: infrastructure-design.md §6.2「L3（外部 KV）を入れる判定条件」（権威：仕様・設計規約）**
```
「なんとなく不安だから」で入れない。以下のいずれかを【観測】したときに初めて検討し、ADR を起票する:
1. レート制限起因のエラーが実利用で発生した
2. キャッシュヒット率が想定を下回り、INF-2 または NFR-7 を満たせない
3. Phase 2 の静的データ配信（GR-5）で、配信物の置き場所が必要になった
```

**§C: infrastructure-design.md §6.1「キャッシュ層の 3 分類」（権威：設計規約）**
```
| L2 | Next.js のデータキャッシュ | ... | ✅ 採用。MVP の主役 |
| L3 | 外部 KV | 全インスタンス共有・永続的 | ❌ 未採用（D-5）。
                                         Cache Port の実装差し替えだけで入れられる状態に保つ |
```

### 権威順による判定（intent-gate-rules.md）

権威順: **ユーザー明示 > 仕様 > テスト > 現行コード**

1. **ユーザー明示**: D-5 追補（2026-08-17 記録）が「サーバー側ストアを持たない」と明言。これは最高権威。
2. **仕様**: infrastructure-design.md §6.1・§6.2 が L3「未採用」「観測条件なしに入れない」と明記。
3. **テスト**: SP-5 の操作レビュー「2 回目の検索が外部リクエストを発生させない」は HTTP Cache-Control 層だけで満たせる（L2 で十分）。L3 が必須ではない。
4. **現行コード**: 実装なし（まだ）。

### 結論

**既存ドキュメントは cost_guard / cf_platform を支持する**。privacy_lockin の「Cache Port は open-next.config.ts に実装する」案は、D-5 追補を読み違えている（「Cache Port の実装位置」≠「persistent store の採用」）。

🔴 **privacy_lockin への指摘**: 
- NFR-17 の Cache Port はデータアクセス層から事業者固有 KV を隔離するための **抽象** であり、その実装位置の具体化（`open-next.config.ts` など）ではない。
- D-5 追補が「サーバー側ストアを持たない」と格上げした今、Cache Port はあくまで「破棄可能なキャッシュ」の切り分け点として機能すべき。
- 「後から R2/D1 を差し込めるようにしておく」と「最初から R2/D1 を使う」は別物。前者なら NFR-17 の分界だけで足り、後者は D-5 追補に矛盾する。

---

## 問 2: Preview URL 要件（SD-1）と Free 初期値の両立

### 質問の意図

cost_guard が「Free 初期値 + 実測 CPU で判定」案を提示したとき、「それでも SD-1（全スプリント PR に開けるプレビュー URL が要る）は成立するか」。

### 既存ドキュメント (infrastructure-design.md §8 環境構成）

```
環境ごとの仕様（プレビュー環境のみ先行決定・D-11）:
- プレビュー環境: Cloudflare Workers Free で動作可能か？ → 【要実測】SP-1 で確認

本番環境: 支払い方法の登録（A-6）でオプション化される
```

### SD-1 と preview URL の依存関係

SD-1「動作確認できる状態で終わる」の定義:
- 「スプリントの PR には **開けるプレビュー URL** が貼られている」
- OR「出せない場合は理由とローカル起動手順を PR に書く」（妥協許容）

cost_guard の「Free 初期値」シナリオ:
1. **SP-1 で実測** して CPU ms / バンドルサイズ をプレビュー環境で確認
2. **その時点で「Free で十分か / Paid が必須か」を判定**

### 整合性の判定

✅ **両立する**。理由:

- cost_guard の「Free 初期値」は **プレビュー環境の初期構成** として合理的。
- SD-1 が求める「開けるプレビュー URL」は、**環境のランタイムコスト（Free/Paid）に依存しない**。Workers のランタイムが動けば URL は生成される。
- Paid 昇格の判定が「SP-1 実測後」でも、その時点までは Free でプレビュー URL を出力し続けられる。
- Paid 昇格が必要になった場合、cost_guard の「確認なしで Paid に切り替える」ルール（INF-2/INF-3 優先順位）に従えば、UI には影響なく、請求金額のみが変わる。

🔵 **付加情報**: D-11「プレビュー環境のデプロイ先だけは先行決定」は、本番先は未決のまま。プレビューの選定ガイド（Free/Paid の判定ロジック）が cost_guard で明確化されたことで、**D-11 は「決めない」から「実測に基づき自動判定」へ進化** する。これは破壊的変更ではなく、未決事項の詳細化である。

---

## 問 3: D-16 ～ D-18 の最終文言確定（ユーザー明示決定を権威として記録）

ユーザー明示決定（whiteboard の論点冒頭）:
1. インフラは **Cloudflare ベースで進める**
2. 既存 Cloudflare アカウントを使い必要リソース作成
3. **CLI（wrangler）を主経路にする**（MCP ではなく）

### 最終的な D-n 記録案

**D-16: デプロイ先・エッジランタイム・キャッシュ基盤を Cloudflare に確定**

```
ユーザー明示決定（2026-08-18）により、プレビュー環境・本番環境ともに
Cloudflare Workers + @opennextjs/cloudflare の構成で進める。
キャッシュ層は HTTP Cache-Control + Workers Caching (L2) で MVP 完結。
L3（R2/D1 等 persistent store）は D-5 追補の「未採用」を維持し、
観測条件（レート制限エラー発生 / ヒット率不足 / Phase 2）を満たしてから検討。
D-15「人手ゼロの自動化」の前提として、wrangler CLI を運用一次経路に統一し、
GitHub Actions + wrangler-action によるデプロイパイプラインを標準化する。
移植性（NFR-21）は @opennextjs/cloudflare adapter と wrangler.jsonc の分離で確保。
```

**D-17: @opennextjs/cloudflare adapter と wrangler.jsonc の採用基準**

```
OpenNext + adapter 単体では NFR-21（vendor lock-in 最小化）を破らない。
禁止対象は「app/ 配下のコードが Cloudflare 固有バインディング 
（KV/R2/D1/Cache API 等）を直接呼ぶこと」であり、
wrangler.jsonc の設定ファイルや Cache Port 内の 1 ファイル（Rate Limit / 
Incremental Cache）に閉じ込めるなら許容される。
違反判定の境界線は infrastructure-design.md §3.2「禁止リスト」を更新し、
以下を追加する:
  - getCloudflareContext() は Cache Port と Rate Limit 実装ファイルのみで呼ぶ
  - env.* バインディング（KV/R2 等）への直接アクセスを禁止
  - wrangler.jsonc / open-next.config.ts はアプリの実行時分岐条件にしない
移行時の チェックリスト（infrastructure-design.md §13）に 
「wrangler.jsonc と open-next.config.ts の破棄」を追加。
```

**D-18: キャッシュ戦略と TTL の初期値**

```
MVP は 2 層: (1) Next.js Data Cache（L2・プロセス内・短 TTL）
(2) HTTP Cache-Control + Workers Caching（公開 CDN・中 TTL）。
初期 TTL は検索結果 5 分・詳細 30 分（cost_guard の §8-6 未確認項目により調整）。
L3（R2/D1）は未採用。Cache Port（NFR-17）は「差し替え可能な 1 箇所」として
open-next.config.ts に集約させるか app 内に 1 ファイル として実装するかは
SP-1 の実装時に決め、ADR で記録する。
D-5 追補「サーバー側ストアを持たない」の原則を Phase 2 まで維持。
```

---

## 🔴 unresolved（他者の実測待ち）

- privacy_lockin への質問: invocation log の IP 含有有無 / Rate Limiting binding の課金有無 → **確定後に禁止リスト文言を更新**
- cost_guard の Billable Usage API 実装 → monitoring 手段確定までは cost_guard/cli_autonomy にしてほしい
- cf_platform の CPU ms 実測値（3MB バンドル / p95 CPU time）→ SP-1 未確認項目リストに明記し、SD-1 通過前に取得
