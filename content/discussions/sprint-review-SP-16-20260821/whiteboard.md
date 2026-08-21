<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: SP-16 スプリントレビュー（受け入れ判定 / 残課題の仕分け / デザイン観点）

- 議題ID: `sprint-review-SP-16-20260821`
- 論点: PR #293（squash マージ済み・main 2007438）で SP-16「キーワード検索の結果も過小評価度の順に並べられる」を実装した。Issue #263 の完了条件と user-story-map.md §5.3 SP-16 の操作レビュー手順に対して受け入れ可否を判定し、残課題を仕分ける。
- 参加者: `acceptance`, `backlog`, `design`
- 投稿数: 2
- 更新: 2026-08-21T10:28:43+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

## ラウンド 1

### `backlog` — 主張
<sub>2026-08-21T10:27:47+09:00</sub>

# backlog レンズ: SP-16 残課題の仕分け（round1）

## 1. 既に起票済みで漏れがないか

PR #293 のレビュースレッド 8 件（`get_review_comments`）を全件確認した。スキップした指摘はすべて対応済み Issue へ紐づいている（重複なし）。

| 指摘 | 紐づけ先 |
|---|---|
| `searchByGemIndex` が生値を受ける（NIT） | 実害なし・#294 起票時に合わせて整理予定と記載済み（未追跡だが実害軽微・新規起票は不要） |
| `sort=gem-index` の 1 リクエストで候補プールを 2 回読む | #294（既起票） |
| 区切り `<li>` の a11y セマンティクス不足 | #296（既起票） |
| `src/ui/` から domain 関数 `gemFacetKey` を import（NIT） | #294 解消時に同時整理と明記（新規起票は不要） |
| E2E が本番 `daily-digest.json` に依存 | #295（既起票） |
| `seriousOrCritical()` の 5 重複（NIT） | #295 に含めると明記（新規起票は不要） |
| 読み込み中インジケータの axe コントラスト（PR 内で偶発検出・レビュー指摘ではない） | #292（既起票） |

**🔴 未起票で漏れている項目が 1 件ある**: `content/discussions/sp16-gem-index-sort-20260821/whiteboard.md` の `lead` 判定 `follow_up_issues`（round1 時点）——

> 「ADR 0005 の TTL を『1 検索あたりの API 呼び出し数が可変』な前提で再逆算する（gem-index 経路は最大 10 倍）」

PR #293 本文・review comment（`repository-publication-review.md` §7.2 への追記）は「前提が変わった事実の 1 行」を正本に追記しただけで、**再逆算そのものはスコープ外として明示的に見送っている**。`mcp__github__search_issues`（「ADR 0005 TTL 再逆算 gem-index」「TTL 逆算 レート予算 gem-index キャッシュ」「rate-limit budget re-derive TTL」の 3 クエリ）でヒットしたのは無関係の #276（Gem Index 算出ロジック集約）のみで、**この follow-up は起票されていない**。親セッションでの起票が必要（`type:improvement` / `NFR-5` 参照 / ADR 0005 §TTL 根拠の再計算 が要旨）。

## 2. 次スプリントへ送る項目

- 上記「ADR 0005 の TTL 再逆算」Issue（未起票・起票後にバックログへ）
- #292 / #294 / #295 / #296 はいずれも `SP-16` のスコープ外として明示的に切り出し済みのバックログ項目（次スプリントで着手するかは `priority:*` 次第・owner の棚卸しに委ねる）

## 3. Issue #263 をクローズしてよいか

**🟢 クローズしてよい。** 完了条件を突き合わせた結果:

- [x] 検索結果を Gem Index 順で並べ替えられ、URL に反映される（`sort=gem-index`・プレビュー URL で確認済み）
- [x] Gem Index を持たないリポジトリの扱いが UI 上で理解できる（区切り見出し実装済み）
- [x] 分岐②で (a) を選んだ場合の UI 明示要件 → **該当なし**（実際は (b) 全件取得を採用したため、この条件は発火しない。操作レビュー手順 4「2 ページ目でも大小関係が破綻しない」がそのまま検証項目になっている）
- [x] `AC-6` / `AC-7`（ページング・ソート・復帰）の既存の振る舞いを壊していない（PR 本文に無変更の明記・E2E PASS）
- [x] `bash tools/run_checks.sh` が緑で、結果を PR 本文に貼っている（15 チェック全 PASS を確認済み）

`user-story-map.md` §7 運用ルール 10 の「クローズ条件 = 操作レビュー手順の全項目をプレビュー URL 上でなぞれた状態でマージされたとき」も PR #293 本文に「操作レビュー手順（1〜6）をプレビュー URL でなぞれる」と明記されており満たしている。

## 4. `SP-16` の次に着手すべき `SP-n`

**在庫はまだ尽きていない（`M-3` 未到達）が、次の一手は通常の SP 着手ではなく「S-2 の統合設計」である。**

- `user-story-map.md` §5.3 は `SP-1`〜`SP-11`・`SP-14`〜`SP-16` まで個別の `### SP-n:` セクション（ゴール・操作レビュー・見積もり）を持つが、**`SP-12 以降（S-2）` はまとまった 1 セクションのままで、個別の `SP-12:` 見出しが存在しない**（492 行目）。対象ストーリーは `US-10` / `US-27` / `US-28` / `US-29` / `E-20` / `E-21` で「1 スプリント 1〜2 項目で順次追加」とだけ書かれている。
- `D-27`（`open-questions.md`）により、この統合設計は **`S-3`（`SP-14`〜`SP-16`）完了後に着手する** と決められており、`SP-16` の完了（本 Issue のクローズ）でその前提条件が満たされた。
- §7 運用ルール 10 は「未起票の次の 1 件だけ起票する」「着手順序は未 Closed の最小 `SP-N`」と定めるが、**`SP-12` はまだ Issue 化できる粒度（ゴール・操作レビュー・見積もり）に分解されていない** ため、機械的な次スプリント起票（`tools/sprint_backlog_sync.py`）はこのままでは空振りする可能性が高い。
- したがって次に着手すべきは「`SP-12` 以降を `US-10` / `US-27` / `US-28` / `US-29` / `E-20` / `E-21` の単位で `SP-12`, `SP-13`, … に統合設計・分割し、`user-story-map.md` §5.3 に個別セクションとして追記する」タスクである（Gem 発見（`S-3`）の実装を踏まえた設計、という `D-27` の趣旨どおり）。
- `M-3`（在庫が尽きたときのマイルストーン通知）には該当しない。`S-2` のストーリー自体は残っており、単に「まだ SP に切り分けられていない」だけ。

### `acceptance` — 主張
<sub>2026-08-21T10:28:28+09:00</sub>

## 受け入れ判定（acceptance・SP-16 / Issue #263 / PR #293）

### 判定: **accepted**

`main` へ squash マージ済み（`2007438`。PR #293 の head `f3af837`）。プレビュー URL: https://pr-293-gem-hunter.kinamocchi-tech.workers.dev/ja（?q=react&sort=gem-index で Gem Index 順を確認可能）。**私（acceptance）はプレビュー画面を開けないため「目視で確認した」とは書かない**。以下はすべてコードと実行結果に基づく判定であり、視覚的な最終確認（レイアウト崩れ・実機での体感操作性）は人間の操作レビューに委ねる。

### 1. 設計ドキュメントの 1 ホップ先ポインタ確認

`user-story-map.md` §5.3 `SP-16` から辿った先:
- `prd.md` `AR-2`（ソート UI・データアクセス層は MVP で用意済みと明記）/ `GR-4`（差別化の実体）/ `NFR-5`（キャッシュ TTL）/ `NFR-7`（レート制限耐性・直列化）/ `NFR-8`（API 失敗を握り潰さない）/ `AC-6`（戻ってもソート保持）/ `AC-7`（ページング・1,000 件上限超のページを要求しない）
- Cloudflare 固有ゲートの見落とし: なし。`AC-7` の 1,000 件上限は `page-number.ts` の `API_RESULT_LIMIT`（既存 SSOT）を `search-repositories.ts` の `GEM_INDEX_FETCH_MAX_PAGES` が参照する設計になっており、二重定義していない（PR 本文の修正③）。Cloudflare Workers 固有の追加ゲート（`cloudflare-infrastructure.md` 側）は本スプリントの変更範囲（アプリコード）に影響しない
- `docs/03_design/ui-ux/ui-ux-guidelines.md` §2.4（コントロールサイズトークン）まで実際に開いて確認（下記 5.）

### 2. 仕様分岐（Issue #263 の 2 件）の実装確認

| 分岐 | 決定（#285） | 実装確認 |
|---|---|---|
| ① Index 非保有の扱い | 絞り込まず末尾に残す | `gem-index.ts` `sortByGemIndex` が ranked/unranked に分けて安定ソート後に結合。`totalCount` は不変（`search-repositories.ts`）。E2E（`e2e/sp-16.spec.ts`）が「件数不変」「非保有は末尾」「区切り見出し 1 本」を検証 |
| ② 並べ替え範囲 | 最大 1,000 件取得してから | `GEM_INDEX_FETCH_PER_PAGE=100` × `GEM_INDEX_FETCH_MAX_PAGES=10`（`API_RESULT_LIMIT` 由来）で逐次取得。早期打ち切り（`per_page` 未満応答 or `ceil(totalCount/100)`）・id 重複排除・fail-closed（途中ページ失敗は例外伝播、部分データで返さない）を実装で確認 |

`AC-6`/`AC-7` との相性（Issue が名指しした懸念）: ページ境界での大小関係破綻は、**全件取得後にまとめて並べ替えてから表示ページへスライス** する設計（②を (b) 案で解決）のため構造的に発生しない。E2E がこれを操作レビュー手順 4 として実測（1 ページ目末尾 ≤ 2 ページ目先頭を単調性で検証）。

### 3. 実行結果（実際に走らせた出力を引用）

```
$ npx vitest run
 Test Files  63 passed (63)
      Tests  547 passed (547)

$ python3 tools/check_architecture_boundaries.py
✅ 依存規則 OK（146 ファイル・Warning 0 件）

$ python3 tools/check_ui_dimensions.py
✅ UI 寸法検査 OK（Warning 0 件）

$ python3 tools/check_contrast.py
[check_contrast] PASS: 11 ペア × ライト/ダーク 計 22 判定、全てしきい値を満たしています
```
PR 本文の `run_checks.sh` サマリー（lint/tsc/vitest/E2E/Lighthouse/依存規則/UI寸法/コントラスト/ADR/副作用GET/CJK/セルフレビュー機械チェック/退役スクリプト/デプロイゲート/ダイジェスト鮮度 = 全 PASS）とも整合。E2E・Lighthouse は重いため本判定では再実行せず PR 本文の記載を採用した（vitest・依存規則・UI寸法・コントラストは独立に再実行して裏取り済み）。

`e2e/sp-9-a11y.spec.ts` の 1 回限りの flaky（`animate-pulse` の `color-contrast`）は本 PR のスコープ外コンポーネントで、#292 として別途起票済み（本判定に影響しない）。

### 4. Sprint Planning `編成` 欄

Issue #263 のコメント（`Session-Id: f64595c1-...`）: `編成: discussion-review（1 ラウンド）→ fan-out(3): ドメイン・ユースケース / インフラ / UI・E2E`。**単独実行ではない**。PR 本文の `Team:` トレーラーとも一致（同期コピー確認済み）。Problem なし。

### 5. デザイン観点（`ui-ux-guidelines.md` §2.4 実測）

差分は `app/[locale]/page.tsx` / `src/ui/repository-list.tsx` / `src/ui/sort-picker.tsx`（既存拡張、SortPicker 自体は無変更）を含む。

**🔴 必須行の充足（コードで確認）**:
- 新規コントロールの追加なし。`SortPicker` は既存の `buttonVariants({ size: 'default', ... })`（cva 経由）をそのまま使い回しており、`repository-list.tsx` の追加要素（Gem Index 値・被依存数のテキスト、区切り見出し `<li>`）はいずれも **非インタラクティブなテキスト表示**（`<span>` / `<li>`）でありコントロールに該当しない → `--size-control-*` 系の適用対象外
- `h-*` / `text-*` の生数値直書きなし（`repository-list.tsx` の追加分は `text-xs` 等の **カード内メタ情報のフォントサイズ** で、§2.4 の「入力系コントロールの最小フォントサイズ」規制の対象外。同ファイル冒頭の既存カードと同一クラスパターンを踏襲）
- 機械検査 `check_ui_dimensions.py` が Warning 0 件で PASS（上記 3. で再実行済み）

**🔵 推奨行からの逸脱（Problem として記録・マージ済みのためブロックしない）**: 検出なし。区切り見出し・Gem Index 値表示は二次的情報でコントロールではないため §2.4 の tier 選定の対象外という整理そのものが妥当かは、**視覚的な密度・読みやすさの領域**（機械検査の射程外の「推奨値の妥当性」）であり、人間の操作レビューで見てもらいたい

**機械検査の射程外 4 領域（境界の事実）**:
1. 動的 className によるサイズ上書き — 本 PR には該当なし（`SortPicker` は cva のみ、動的合成なし）
2. 推奨値の妥当性（tier 選定が意味論的に正しいか）— 「Gem Index 値・区切り見出しをコントロール外のテキストとして扱う」判断はコード上一貫しているが、**実際の見た目の情報密度** は目視でしか判断できない
3. 未登録の新規コンポーネント — 新規 UI ファイルは `sort-picker.tsx`（既存拡張・config 登録済み）のみで、`repository-list.tsx` 内の追加要素はコンポーネント化されていない（既存ファイル内の分岐追加）ため config 登録の要否自体が生じない
4. 実ブラウザでの体感操作性 — プレビュー URL で人間の操作レビューが必要（私は開けない）

### 6. 総合結論

`accepted`。理由: ① 仕様分岐 2 件（#285 決定）が実装・E2E とも一致 ② `AC-6`/`AC-7` を壊す設計になっていない（全件取得後スライスで構造的に保証） ③ 依存規則・単体テスト・UI 寸法・コントラストを実行し全 PASS ④ 編成が単独実行になっていない ⑤ デザイン観点は必須行を満たし、推奨行の逸脱はコード上確認できず、視覚確認は人間の操作レビューに委ねる。

`deploy: yes`（本番影響ありと判断する要素なし。#292 の flaky はスコープ外コンポーネントで既に別 Issue 化済み）。
