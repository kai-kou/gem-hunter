# ADR 0016: Cloudflare Cache API を isolate 間共有の L2b として追加する

- **状態**: **承認**
- **日付**: 2026-09-03 JST
- **対応要件**: `NFR-7` / `NFR-17` / `NFR-18` / `D-5` / `D-18` / `D-24`
- **関連**: Issue #121（isolate をまたいでキャッシュを共有し、Workers 上でのヒット率を上げる） / [ADR 0005](0005-cache-port-yagni-exception-and-ttl.md)（`CachePort` を YAGNI の例外として維持する決定・本 ADR はその実装を拡張する） / [Cloudflare インフラ設計](../03_design/infrastructure/cloudflare-infrastructure.md) §4.2 / §4.4 / [インフラ設計](../03_design/infrastructure/infrastructure-design.md) §6.1 / §6.2

---

## 1. 文脈

Issue #121 は「isolate をまたいでキャッシュを共有し、Workers 上でのヒット率を上げる」ことを求めている。現行の L2（`InMemoryCache`・[ADR 0005](0005-cache-port-yagni-exception-and-ttl.md)）は composition root のモジュールスコープで生成する単一インスタンスだが、**isolate が破棄されると失われる**。[`cloudflare-infrastructure.md`](../03_design/infrastructure/cloudflare-infrastructure.md) §4.2 は「isolate をまたぐ永続性は本スプリントでは追わない」と明記した上で、「将来の格上げ候補として Cloudflare の Cache API（`caches.default`）を composition root から能動的に呼び出す案が残っている（§6.2 の観測条件を満たしたときに ADR で検討する）」と書き残していた。本 ADR がその検討の実体である。

プレビュー環境で同一 URL への連続 GET 12 回中 HIT 2 回（約 17%）、別 URL でも 6 回中 2 回という実測が Issue #121 のコメントに記録されており、これが[`infrastructure-design.md`](../03_design/infrastructure/infrastructure-design.md) §6.2 の条件 2（「キャッシュヒット率が想定を下回り、`INF-2` または `NFR-7` を満たせない」）に該当するかどうかを判定する必要があった。この「想定」の数値がこれまで未定義だったため判定できず、Issue #121 は一度保留されていた。本 ADR で確定させる。

### 1.1. 一次情報で確認した Cache API の仕様

- `cache.put()` は `GET` 以外のメソッドの `Request` に対して例外を投げる。`status 206`・`Vary: *`・`Set-Cookie` を持つ `Response` も保存できず例外になる。`Cache-Control` は解釈される。出典: [Cloudflare Docs — Cache](https://developers.cloudflare.com/workers/runtime-apis/cache/)
- 🔴 **共有範囲は同一データセンター（colo）内に限られる**。他の colo には複製されず、`cache.delete()` も呼び出された colo でのみパージされる（出典同上）。この意味論は[`infrastructure-design.md`](../03_design/infrastructure/infrastructure-design.md) §6.1 が L3 に与えている「全インスタンス共有・永続的」という定義とは異なる（§2.2 で判定する）。
- Free プランでも `caches.default` は利用できる。支払い方法の登録は不要（`A-6` 非該当）。出典: [Cloudflare Docs — Pricing](https://developers.cloudflare.com/workers/platform/pricing/) / [Cloudflare Blog — How Cloudflare Workers Cache API speeds up your website](https://blog.cloudflare.com/workers-cache/)
- 本リポジトリは `@cloudflare/vitest-pool-workers` を導入していないため、Vitest（`jsdom` / `node` environment）では `caches` グローバルが未定義になる。実装側でこれを検知しフォールバックする必要がある。

---

## 2. 決定

### 2.1. `CachePort` の実装を 2 段構成にする

`CachePort` の実装を、前段 L2a = 既存 `InMemoryCache`（isolate 内メモリ）、後段 L2b = 新規 `WorkersCache`（Cloudflare Cache API `caches.default` を使う）の **2 段構成** にする。読み出しは L2a → L2b の順に試行し、L2a に無く L2b に HIT した場合は L2a へ書き戻す（isolate 内の以降のリクエストは L2a で完結する）。書き込みは両層へ行う。`caches` グローバルが存在しない実行環境（Vitest 等）では L2b をフォールバック（no-op）にし、L2a のみで動作する。

実装位置は `src/infrastructure/platform/workers-cache.ts`（新規）。composition root（`src/composition/container.ts`）でのポート合成方法は実装側の裁量とする。

### 2.2. これは L3（外部ストア）の導入ではない

[`infrastructure-design.md`](../03_design/infrastructure/infrastructure-design.md) §6.1 は L3 を「全インスタンス共有・永続的」な外部 KV 等と定義し、`D-5`（データアーキテクチャ）は MVP では DB を持たない方針を定めている。本決定が L3 に該当しないことの根拠は次の 3 点。

1. **新しいバインディングを追加しない**。`wrangler.jsonc` は変更せず、`caches.default` は Workers ランタイムが標準で提供するグローバルである。
2. **支払い方法の登録を伴わない**（`A-6` 非該当）。§1.1 のとおり Free プランでも利用できる。
3. **共有範囲が「同一 colo 内・エッジキャッシュの生存期間」に限られる**。他 colo への複製も永続保証もなく、`infrastructure-design.md` §6.1 が L3 に求める「全インスタンス共有・永続的」を満たさない。

よって本決定は `D-5`（DB を持たない）に抵触しない。**L2 の内部を 2 段に分けただけであり、L3 の採否判定（§6.2）はこれまでどおり未実施のまま維持する。**

### 2.3. 🔴 「想定」ヒット率の数値定義（`infrastructure-design.md` §6.2 条件 2 の確定）

`infrastructure-design.md` §6.2 の条件 2 が「キャッシュヒット率が想定を下回り」とだけ書いており、「想定」の数値がこれまで未定義だった。本 ADR で以下のとおり確定する。

> **定義**: 「同一 colo・TTL 内に同一キーへ届いた 2 回目以降のリクエストのうち、上流 GitHub API を呼ばずに応答できた割合」が **80% 未満** のとき、条件 2 を満たした（想定を下回った）とみなす。

仮定: 「想定」の数値基準が未定義 → 80% を採用（無人実行のため推奨案を採用。ユーザー判断で訂正可）。

**判定**: 実測 17%（Issue #121 コメント記録）はこの定義に照らして条件 2 を満たしている（= L3 導入を検討してよい状態）。ただし本 ADR は L2 の 2 段化を決定するのみで、L3 の導入判断そのものは行わない（§2.2）。2 段化後の実測ヒット率が §6 の完了条件の測り方でなお条件 2 を満たす場合は、改めて L3 導入の ADR 起票を検討する。

---

## 3. 却下した代替案

| 選択肢 | 却下理由 |
|---|---|
| **(a) 現状維持（`InMemoryCache` のみ）** | Issue #121 の「isolate をまたいだヒット率向上」という要求を満たさない。実測 17% が §2.3 の定義で条件 2 を満たしており、対応しない選択は取れない |
| **(b) Cache API 単段（メモリ前段を廃止）** | 同一 isolate 内の 2 回目以降のアクセスでも非同期 I/O（Cache API 呼び出し）が毎回発生し、`InMemoryCache` が担っていた「同一 isolate 内は同期的な `Map` 参照で完結する」という現在の性質を退行させる。また [ADR 0005](0005-cache-port-yagni-exception-and-ttl.md) §5 が `CachingRepositoryQuery` の single-flight（`NFR-7` の担保）に前提としている同期的な参照経路とも組み合わせが悪化する |
| **(c) L3（KV / R2 / D1）の導入** | R2 は有効化に支払い方法の登録が必要（`A-6`）。[`infrastructure-design.md`](../03_design/infrastructure/infrastructure-design.md) §6.2 の観測条件は §2.3 の定義に照らせば満たしているが、L3 は「全インスタンス共有・永続的」という性質上コスト・運用面の影響が大きく、まず新しいバインディングを追加しない Cache API（L2b）で isolate 間共有を試すのが段階的である。L3 導入は本 ADR の範囲外とし、必要になれば別途 ADR を起票する |

---

## 4. 限界と残るリスク

- **同一 colo 限定**: 複数の colo に分散するアクセスパターン（利用者の地理分布が広い等）では L2b は HIT しない。「isolate をまたぐ」は満たすが「全世界のリクエストが 1 つのキャッシュを共有する」わけではない。
- **エッジキャッシュは Cloudflare 側の都合で退去されうる**: TTL 内であっても Cloudflare のキャッシュ容量管理により早期に破棄される可能性があり、保証された生存期間ではない。
- **`X-Cache-Status` の検証手段は層を区別しない**: [`cloudflare-infrastructure.md`](../03_design/infrastructure/cloudflare-infrastructure.md) §4.5 の観測手段は「L2a で HIT したか L2b で HIT したか」を区別しない（`CachePort` の外側からは 1 つの L2 として見える）。どちらの層で HIT したかを切り分けたい場合は、別途ログ・メトリクスを追加する必要がある（本 ADR の範囲外）。
- **テスト環境の差異**: `caches` グローバルが存在しない環境（Vitest）では L2b が常にフォールバックするため、単体テストは L2a のみの経路しか検証できない。isolate 間共有そのものの検証はプレビュー環境の実機確認に依存する。

---

## 5. 結果（この決定がもたらすもの）

### 良い方向

- Issue #121 の要求（isolate をまたいだヒット率向上）に対応する
- `wrangler.jsonc` の変更・支払い方法の登録を伴わず導入できる（`A-6` を発生させない）
- `D-5`（DB を持たない）に抵触しない範囲で isolate 間共有を実現する

### 受け入れる代償

| 代償 | 緩和策 |
|---|---|
| 同一 colo 限定で、全世界共有ではない | §4 に限界として明記。将来複数 colo にまたがる共有が必要になれば L3 の ADR を別途起票する |
| L2b 経路は Vitest では検証できない | プレビュー環境の実機確認で isolate 間共有の効果を確認する（§6） |

---

## 6. 完了条件の測り方

- 測定対象は **「同一クライアントから同一 URL への連続リクエスト」における HIT 率** であり、全リージョン・全 isolate をまたいだ共有率ではない（§4 の限界のとおり、複数 colo にまたがるアクセスは測定対象に含まれない）。
- プレビュー環境で §2.3 の定義（同一 colo・TTL 内の 2 回目以降のリクエストに対する HIT 割合）に沿って実測し、`InMemoryCache` 単段時点の実測（17%）と比較する。
- 2 段化後もなお §2.3 の 80% 基準を下回る場合は、`infrastructure-design.md` §6.2 条件 2 を満たした状態が継続していることになるため、L3 導入の ADR 起票を検討する（本 ADR は起票しない）。

---

## 7. 参照

| ドキュメント | 関係 |
|---|---|
| Issue #121 | 本 ADR の発端。isolate 間キャッシュ共有によるヒット率向上の要求と実測コメント |
| [ADR 0005](0005-cache-port-yagni-exception-and-ttl.md) | `CachePort` を維持する決定・`CachingRepositoryQuery` の single-flight（`NFR-7`）。本 ADR はその L2 実装を 2 段構成へ拡張する |
| [`cloudflare-infrastructure.md`](../03_design/infrastructure/cloudflare-infrastructure.md) §4.2 / §4.4 | キャッシュ層構成の正本。L2 行と「isolate をまたぐ永続性」の記述を本 ADR の決定に合わせて改訂 |
| [`infrastructure-design.md`](../03_design/infrastructure/infrastructure-design.md) §6.1 / §6.2 | 3 層構成の正本・L3 導入の観測条件。§6.2 条件 2 の「想定」数値の定義は本 ADR（§2.3）が正本 |
| [Cloudflare Docs — Cache](https://developers.cloudflare.com/workers/runtime-apis/cache/) | Cache API の仕様一次情報 |
| [Cloudflare Docs — Pricing](https://developers.cloudflare.com/workers/platform/pricing/) | Free プランでの `caches.default` 利用可否 |
