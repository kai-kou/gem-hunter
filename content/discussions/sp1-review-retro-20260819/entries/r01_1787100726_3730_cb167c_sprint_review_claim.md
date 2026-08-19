<!--entry
author: sprint_review
round: 1
kind: claim
ts: 2026-08-19T09:52:05+09:00
-->

## sprint_review（争点A主担当）

### 判定: **accepted_with_conditions**

### 根拠（要件ID × 実ファイル行、実際に読んで確認した事実のみ）

| 要件ID | 実ファイル:該当箇所 | 判定 | 備考 |
|---|---|---|---|
| `AC-1` | `package.json`: `"next": "16.3.1"`／`app/page.tsx` `app/layout.tsx`（`app/` 配下＝App Router、`pages/` なし） | 満 | v16 以降 + App Router 確認 |
| `AC-2`（SP-1 は「一部」が必達） | `app/page.tsx:37-44`（`searchParams` の `q`/`page` を読む）／`src/ui/search-form.tsx:9-25`（`<form action="/" method="get">` で GET 送信） | 満（必達超過） | キーワードの URL 反映（本来 SP-2 相当）までこの時点で実装済み |
| `AC-3`（必達＝アイコン+リポジトリ名） | `src/ui/repository-list.tsx:26-40`（`<img>` avatar + `item.fullName` リンク） | 満 | |
| `AR-1`（SP-1 では未達達成でよい） | `src/ui/repository-list.tsx:42-58`（説明文・言語・star・最終更新日・topics） | 満（前倒し達成） | 本来 SP-6 のスコープまで先取り実装 |
| `SD-2`（TDD・実行結果での断定） | `npx vitest run` を実行して確認 → `Test Files 7 passed (7)` `Tests 22 passed (22)` | 満 | brief の主張どおり実結果で green を確認（L-113 準拠） |
| `SD-1`（プレビュー URL・操作レビュー完走） | `wrangler.jsonc`／`.github/workflows/deploy-preview.yml`／実 URL `https://sp1-gem-hunter.kinamocchi-tech.workers.dev` | 条件付き満 | Actions 経由の自動プレビュー自体は 2 回とも起動不能（0 バイトログ）で未達。ただし `user-story-map.md` L332 の bootstrap 例外（`INF-20`：CI 整備前はセッションから直接 `wrangler versions upload` を叩いてよい）で URL は確保済み。SD-1 の「出せない場合は理由とローカル起動手順を書く」要件は実質的に手動アップロードで代替されている |
| アーキ依存規則 | `python3 tools/check_architecture_boundaries.py` 実行 → `✅ 依存規則 OK（26 ファイル・Warning 0 件）`（0.042s） | 満 | brief の 58ms 主張と整合（バックトラック修正確認） |
| **SP-1 固有ゲート**（`docs/03_design/infrastructure/cloudflare-infrastructure.md` §5.3：「判定タイミング: **SP-1 でプレビュー環境へ初回デプロイした直後**」の p95 CPU 実測） | 未実施。`wrangler.jsonc:9` の `limits.cpu_ms: 50` は事前設定のみで、`wrangler tail` による実測（brief の残作業④）が行われた形跡なし | **未達** | ドキュメントが SP-1 のタイミングを名指ししている実測ゲート。Free/Paid 判定（`A-6` 相当の不可逆コスト判断）に直結する |

### 未達項目の切り分け

1. **p95 CPU 実測ゲート（cloudflare-infrastructure.md §5.3）→ 次の firing で必ず潰す。** 初回デプロイ（プレビュー URL 確保）は既に完了しており、実測自体（`wrangler tail --format json` を叩くだけ）はブロッカーが無い。先送りすると Free/Paid の不可逆判断（`A-6`）が遅れ続ける。
2. **GitHub Actions 起動不能（`E-22` の CI 経路）→ 既に `A-6` 相当としてユーザー確認依頼中（brief記載どおり）。** SD-1 の必達要件そのものは bootstrap 例外で代替されているため、これ単体で SP-1 の受け入れを差し戻す理由にはしない。ただし SP-4 以降は Actions 経由に一本化する規定（L332）があるため、次 firing 以降も追跡は必要（争点 D/E 側の管轄）。
3. **⑤ Cache Port の器 / ⑥ シークレット投入・Rate Limiting / `installation-token.ts` の ClockPort 化 → 後続スプリントへ送ってよい。** ⑤は `cloudflare-infrastructure.md` §4.3 が実装「場所」を指定するのみで時期を指定しておらず、キャッシュ層自体は `SP-5`（§5.3「同じ検索で API を二度叩かない」）のスコープ。⑥（Rate Limiting）も SP-1 の `AC`/操作レビュー手順に含まれない。ClockPort 化はテスト容易性改善で `AC`/`SD` に直接紐づかない。

### Issue #26 が open のままであることについて（`user-story-map.md` §7 item 10 との整合）

同項は「Issue のクローズ条件は操作レビュー手順の全項目を PR のプレビュー URL 上でなぞれた状態でマージされたときのみ」と定める。brief 記載どおり SP-1 の操作レビュー 3 項目はプレビュー URL 上で完走済みとされる一方、Issue #26 は open のまま。これは矛盾に見えるが、**p95 CPU 実測ゲートが未達である以上、SP-1 の Done 条件（cloudflare-infrastructure.md §5.3 のゲートを含む）自体がまだ満たされていない** と読めば、open のままにしている現状の運用は正しい。ただし item 10 の文言は「操作レビュー手順」の完走のみを条件として明記しており、Cloudflare 固有ゲートを明示的に含んでいない。**この文言の解釈（Done 条件に §5.3 のような設計ドキュメント側のゲートを含めるか）は正本の記述レベルで曖昧であり、process_design / docs_trace 側で争点 B/C として突き合わせるべき。**

### 結論

`AC-1` / `AC-2`（一部・超過達成） / `AC-3`（必達・AR-1 も前倒し達成）/ `SD-2` は満たしている。`SD-1` は bootstrap 例外の範囲で満たしている。**SP-1 固有の p95 CPU 実測ゲートが未達のため accepted_with_conditions とし、次の firing で実測を完了させてから Issue #26 を close する** のが一貫した扱い。それ以外の残作業（⑤⑥ + ClockPort）は後続スプリントへ送ってよい。
