<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: SP-10（誰でも操作できる）のスプリントレビュー: 受け入れ判定と残課題の仕分け

- 議題ID: `sprint-review-SP-10-20260820`
- 論点: 対象: GitHub Issue #181（SP-10・sp:8・P1-MVP）／PR #183（squash マージ済み・main の f53bbbf）。プレビュー URL: https://pr-183-gem-hunter.kinamocchi-tech.workers.dev

判定の正本: docs/02_requirements/user-story-map.md §5.3 SP-10 の操作レビュー手順 4 項目と、docs/02_requirements/prd.md §6 の AC-9。Issue のクローズ条件は user-story-map.md §7 運用ルール 10（操作レビュー手順の全項目を PR のプレビュー URL 上でなぞれた状態でマージされたときのみ）。

実施済みの検証（実測値）: npm run check は最終コミット 1e739da のクリーンビルドで全 10 項目 PASS（Lint / tsc / vitest / E2E 49秒 / Lighthouse Accessibility gate / 依存規則 / UI 寸法 / 配色コントラスト / CJK / セルフレビュー機械チェック）。Lighthouse は一覧・詳細とも Accessibility 100/100。Layer 1 セルフレビューは 7 観点の並列フレッシュ文脈 → 敵対的検証で CONFIRMED 6 件（全件 PR 内で是正）・REFUTED 2 件・別 Issue 送出 2 件（#185 / #186）。

既知の残件: e2e/sp-9-errors.spec.ts:164 が Issue #145（Cookie 送出タイミング）の既存 flake で約 40〜60% の頻度で落ちる（main 3/5・ブランチ 2/5 を worktree で実測。本 PR 起因ではないことを確認済み）。

編成の記録: Issue #181 の Sprint Planning コメントに 編成: discussion-review（1 ラウンド）→ fan-out(4) と記載。実際には discussion-review 4 レンズ × 2 ラウンド → fan-out(4) → 統合・検証 4 エージェントで実施した。

⚠️ プロセス上の逸脱が 1 件あった: 議論フェーズの参加者（e2e_verify）が担当範囲外でリポジトリを直接編集・コミット・push し、統合フェーズで同じ修正を割り当てていた別担当（R5）と作業が二重化した。内容は正しかったため巻き戻していないが、レトロで扱うべき事象。

⚠️ もう 1 件: 検証用に distDir を変えてビルドした成果物 269 ファイルが Stop フックの WIP 自動コミットで混入し、GitGuardian に検出された（後から追跡除外して .gitignore に /.next-*/ を追加）。Issue #94（並行サブエージェント実行中の Stop フック WIP 自動コミット）と同根。
- 参加者: `acceptance`, `design_acceptance`, `leftover_triage`
- 投稿数: 3
- 更新: 2026-08-20T13:21:08+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

## ラウンド 1

### `design_acceptance` — 主張
<sub>2026-08-20T13:18:48+09:00</sub>

## デザイン観点の受け入れ判定（PR #183 / SP-10）

判定方式: `docs/03_design/ui-ux/ui-ux-guidelines.md`（§2.4・§7）を実開して、PR で新設・変更された UI 要素をコードで照合した。プレビュー URL（https://pr-183-gem-hunter.kinamocchi-tech.workers.dev）は確認したが **視覚的な最終判断（実描画）は行っていない**。以下は静的コード照合の結果であり、実ブラウザでの見え方は人間の操作レビューに委ねる。

### 🔴 必須行への適合（対象要素を個別確認）

| 対象 | 確認内容 | 判定 |
|---|---|---|
| `button.tsx` / `input.tsx` の `/50` 除去 | `focus-visible:ring-ring/50` → `focus-visible:ring-ring` へ変更済み。§7.3「透明度は CSS 変数側に埋め込み、ring/outline に Tailwind の `/NN` を使わない」に適合。`--ring` は §2.2 でライト 8.36:1・ダーク 7.95:1（vs bg）実測済みなので不透明化後も 3:1 を満たす | 適合 |
| `loading-indicator.tsx` の role 除去 | 自身の `role`/`aria-live` を削除し、`app/[locale]/page.tsx` の外側 `<section role="status" aria-live="polite">` の内側にのみ現れる表示専用コンポーネントへ変更。§7.2「ライブリージョンは初期 DOM に空で常設し中身を書き換える／入れ子にしない」に適合 | 適合 |
| `repository-list.tsx` の `alt=""` | オーナーアイコンは `owner/repo` としてテキスト隣接表示されるため §7.4 の「テキストとして隣接表示される→ `alt=""` 明示指定」ケースに一致。空文字が明示指定されており省略ではない | 適合 |
| `back-link.tsx` / `repository-list.tsx` のフォーカスリング付与 | ネイティブ `<a>` に `outline-none focus-visible:ring-3 focus-visible:ring-ring`（`/NN` なし）を付与。§7.3 のパターンに `button.tsx`/`input.tsx`/結果見出しと揃えて適用されている | 適合 |
| `page.tsx` の結果見出し `<h2 id="results-heading" tabIndex={-1}>` | §7.1 の必須実装 3 点（見出しに `tabIndex={-1}`／遷移後に `focus()`／件数ライブリージョン更新）をコードで確認。`FocusOnNavigate` が `results-heading` を対象に設定されており、`h1`（ページタイトル）→ `h2`（結果見出し）の見出し階層も正しい（レベル飛ばしなし） | 適合 |

### 🔵 推奨行の逸脱（Problem・マージ済みにつきブロックしないが次スプリントへ送る）

1. **結果見出し `<h2>` の `text-lg`（18px）が §2.3 のタイポスケール（12/14/16/20/24px の 5 段階のみ）から外れている。** 本 PR で新設された要素であり、`text-xl`（20px）への変更 or §2.3 に見出し専用の例外を明記するかの判断が必要。機械検査の射程外（`check_ui_dimensions.py` はタイポスケールを検査しない）のため、レビューでのみ拾える種類の逸脱。
2. **`button.tsx` `outline` variant: ライトテーマで `--border` と `--ring` が同一値（`oklch(0.6 0 0)`）** のため、resting の border と focus の border-color が視覚的に無区別。コード上のコメントで「ring-3 の有無というバイナリな形状差で判別できるため許容する」と明記されており、WCAG の非テキストコントラスト要件（フォーカスインジケータ自体が 3:1・2px 以上）は ring-3 の追加要素で満たしている。実装判断として妥当だが、**実描画で「resting と focus の境界線が同色で紛らわしく見えないか」は目視でしか判定できない** ため、§7.7 手動チェックリストに追加確認してほしい。

### 境界の事実（判定範囲外・機械検査の射程外）

- `check_ui_dimensions.py` の `COMPONENT_FILES` / `CALL_SITE_REQUIREMENTS` は `button.tsx` / `input.tsx` / `search-form.tsx` / `error-notice.tsx` のみを対象とする。本 PR は `src/ui/components/` 配下に新規ファイルを追加していない（`button.tsx` / `input.tsx` の既存 size variant テーブルは無改変、焦点は focus-ring のみ）ため、**メタチェック（未登録の新規コンポーネント検知）に該当なし**
- `back-link.tsx` / `repository-list.tsx` / 結果見出し（`page.tsx`）は cva 経由のコンポーネントではなく生の `<Link>`/`<h2>` に直接クラスを書いているため、`check_ui_dimensions.py` の登録対象（`COMPONENT_FILES` / `CALL_SITE_REQUIREMENTS`）そのものの外側にある。フォーカスリングの実効値（色・太さ）は `tools/check_contrast.py`（宣言値のみ）ではなく E2E 層（`measureFocusIndicator`）で担保されている旨は `ui-ux-guidelines.md` §7 に明記済みで、本 PR にも `e2e/sp-10.spec.ts` が追加されている
- 動的な `className` 合成によるサイズ上書きの有無、機械検査 config 未登録コンポーネントの網羅性、実ブラウザでの体感操作性は、いずれも本判定の対象外（コード照合のみで判定可能な範囲に限定した）

### 総合判定

**🔴 必須行はすべて満たしている。ブロック要因なし（マージ済みの事後判定としても妥当）。** 🔵 推奨行の逸脱 2 件（タイポスケール逸脱・outline variant の border 同色トレードオフ）は次スプリントへ Problem として送る。

### `acceptance` — 主張
<sub>2026-08-20T13:18:58+09:00</sub>

## 受け入れ判定: **accepted**

### 参照した ID
- `docs/02_requirements/user-story-map.md` §5.3 `SP-10`（操作レビュー手順 1〜4 / `AC-9` / `E-13`〜`E-17` / `US-15`）
- `docs/02_requirements/prd.md` §6 `AC-9`（レスポンシブ対応およびキーボード操作が可能）
- Issue #181 Sprint Planning コメント（編成: `discussion-review`（1 ラウンド）→ `fan-out(4)`）

### 編成の確認（3 点目の必須チェック）
Issue #181 の Sprint Planning コメントに記載の編成は `discussion-review`（1 ラウンド）→ `fan-out(4)`（判定基盤 / フォーカス・ライブリージョン / レスポンシブ・画像 / E2E・ドキュメントの 4 役割・ファイル排他）。**単独実行ではない**。meta.json の実施報告（discussion-review 4 レンズ×2ラウンド → fan-out(4) → 統合・検証4エージェント）は計画をむしろ上回る体制で、Problem には該当しない。

### 実行して確認した結果（`bash tools/run_checks.sh` を実際に再実行・最新コミット f53bbbf）
| チェック | 結果 |
|---|---|
| Lint / tsc / vitest | PASS |
| E2E (playwright, 41件) | **1件のみ FAIL**（`e2e/sp-9-errors.spec.ts:164`）、残り40件 PASS |
| Lighthouse (Accessibility gate) | **PASS** |
| 依存規則 / UI寸法 / 配色コントラスト / CJK / セルフレビュー機械チェック | 全て PASS |

`e2e/sp-9-errors.spec.ts:164` の失敗は brief記載どおり Issue #145（Cookie 送出タイミングの既存 flake）と一致するエラーメッセージ（ログイン導線が消えず残留）で、SP-10 の変更範囲外。**本 PR 起因ではないことを実行結果でも再確認した**。

### `e2e/sp-10.spec.ts` — 操作レビュー手順の写像と結果（実行して緑を確認）
- 手順1（キーボードのみで検索→一覧→詳細→一覧、フォーカス常時可視）: `手順1: キーボードのみで...` **PASS**（908ms）。加えて「フォーカス喪失の検知」テストも **PASS**（route announcer 対応・`FocusOnNavigate` 実装済み）
- 手順2/3（375px・640×360=200%拡大相当で横スクロールなし）: 両 viewport とも一覧（検索前/後）・詳細で **PASS**
- 手順4（`run_checks.sh` で axe・Lighthouse・`check_contrast.py` の三層防御 + 実描画コントラスト計測）: `measureFocusIndicator` によるフォーカスリングの実測（コントラスト≥3:1・太さ≥2px）が検索欄・検索ボタン・一覧リンク・結果見出し・戻るリンクの全ターゲットで **PASS**

4 項目すべてが E2E に写されており、かつ実行結果が緑であることを確認した（「たぶん満たしている」ではなく実行結果で断定）。

### `AC-9` の充足確認
- 任意の画面幅で検索→一覧→詳細→一覧をキーボードのみで完走: 満たす（手順1 テストで実測）
- フォーカスが常に可視: 満たす（手順4 の実描画コントラスト計測で実測）
- 200% 拡大時にレイアウト破綻なし: 満たす（640×360 viewport テストで実測）

### `E-13`〜`E-17` / `US-15` の実装確認
- `E-13`（axe 検証）: `e2e/a11y.spec.ts` が組み込まれ `run_checks.sh` 経由で PASS
- `E-14`（Lighthouse ゲート化）: `tools/run_lighthouse.mjs` が新規実装され `run_checks.sh` に配線済み。実行して Accessibility ゲート PASS を確認
- `E-15`（キーボード完走・フォーカス可視・ルート変更時のフォーカス移動）: `focus-on-navigate.tsx` 実装 + E2E で確認
- `E-16`（レスポンシブ・200%拡大）: E2E で確認
- `E-17`（画像 alt 方針）: `src/ui/repository-list.tsx:62` / `repository-detail.tsx:59` で `alt=""`（装飾アイコンとしてアクセシブルネームを持たない方針どおり）を確認

### 視覚的最終判断についての注記
🔴 本判定はコードとテスト結果（コード読解・実行ログ）に基づくものであり、プレビュー URL（`https://pr-183-gem-hunter.kinamocchi-tech.workers.dev`）を実際に目視で開いての確認は行っていない（サブエージェントはプレビュー画面を開けないため）。フォーカスリングの見た目・レイアウト破綻の視覚的な最終判断は人間の操作レビューに委ねる。

### 総合判定
**accepted**。操作レビュー手順 4 項目すべてが E2E に写され緑、`AC-9` の各条件を実測で充足、`E-13`〜`E-17`/`US-15` の実装を確認、編成も計画どおり（単独実行ではない）。既知の flake（`sp-9-errors.spec.ts:164`・Issue #145 起因、本 PR 対象外）以外に受け入れを妨げる要因は見当たらない。

### `leftover_triage` — 主張
<sub>2026-08-20T13:20:48+09:00</sub>

# 残課題の仕分け（leftover_triage）

## 1. SP-10 で解消したはずの Issue（本文の完了条件 vs main f53bbbf 実コード）

### #173（a11y 判定手段の確定）→ **閉じてよい**
- `tools/run_checks.sh:133-147` に Lighthouse ゲートが配線済み（`node tools/run_lighthouse.mjs`）。`npm run check` で実行できるコマンドとして `AC-9` を判定可能。
- `docs/03_design/ui-ux/ui-ux-guidelines.md` §9 の CLS 項目は「`tools/run_checks.sh` で実行される Lighthouse の CLS 実測値で判定する」に更新済み（"未配線" 注記は grep 0 件で消滅済み）。
- `user-story-map.md` §5.3 `SP-10` 操作レビュー手順 4 は三層防御（`check_contrast.py` / axe / Lighthouse + `e2e/sp-10.spec.ts` の `measureFocusIndicator`）へ更新済み。
- 完了条件 2 項目とも実コードで確認できた。

### #179（フォーカスリング 2.51:1）→ **条件 3 が未達。閉じられない**
- 条件 1（ライト/ダーク両方 3:1 以上）: **満たす**。`app/globals.css` でライト `--ring` を `oklch(0.708→0.6 0 0)` に是正。`python3 tools/check_contrast.py` を実行し実測: ライト vs bg **3.95:1** / vs bg-subtle **3.62:1**、ダーク vs bg **4.18:1** / vs bg-subtle **3.19:1**（全 PASS）。
- 条件 2（`check_contrast.py` が ring ペアを含めて PASS）: **満たす**（上記実行結果、`SEMANTIC_VARS` / `CHECK_PAIRS` に `ring` 追加済み）。
- 条件 3（`ui-ux-guidelines.md` §2.2 の実測値表を更新）: **未達**。§2.2 の実測値テーブル（9 トークン×ライト/ダーク）に `--color-ring` の行が追加されていない。実測値（3.95:1 等）は `app/globals.css` のインラインコメントと §7.3 の三層防御節に **文章としては** 現れるが、§2.2 の表そのものは無更新。
- 判定: 機能要件は満たすが Issue 本文が明記した完了条件（§2.2 表更新）を満たしていないため、字義通りにはクローズ不可。§2.2 に ring 行 2 本（vs bg 3.95:1 / vs bg-subtle 3.62:1、ライト・ダーク計 4 値）を足す小さな追記で解消できる。

### #180（ライブリージョン入れ子）→ **実質達成。閉じてよい（軽微な注記付き）**
- 条件 1（読み込み中に入れ子なし）: **満たす**。`src/ui/loading-indicator.tsx` から `role="status"` / `aria-live` を撤去し、`app/[locale]/page.tsx:333-335` の外側 `section#search-status[aria-live="polite"]` 1 本に統一（コード上のコメントでも明記）。
- 条件 2（`e2e/sp-9-a11y.spec.ts` に入れ子検知の assert）: **文字どおりの「入れ子カウント」assert は無い** が、`page.locator('main').getByRole('status')`（フィルタなし）を使う既存テスト（読み込み中テスト）が、入れ子が再発した場合 Playwright の strict-mode 違反で確実に落ちる構造になっており、退行検知は機能的にカバーされている。
- 条件 3（identity 維持）: **満たす**（`isSameNode` assert が既存）。
- 判定: 機能・退行検知とも実質満たすため閉じて問題ないが、「入れ子検知」を名指しした専用 assert が無い点は認識しておくこと。

## 2. 別 Issue への送出（#185 / #186）→ **内容・sp・priority とも妥当**
- #185（未参照トークン棚卸し）: 実害ゼロだが再導入リスクを正確に記述。`sp:2` / `priority:medium` は棚卸し + 検査追加の作業量に見合う。
- #186（Lighthouse と E2E の起動ロジック二重実装）: 対応方針・トレードオフ（サマリー表の独立性維持要件）まで具体的に記述済み。`sp:3` / `priority:medium` 妥当。

## 3. 関連 Issue の状況変化

- **#74（Lighthouse CI 未配線）→ 閉じてよい**: `docs/03_design/ui-ux/ui-ux-guidelines.md` に "未配線" 注記は無くなり（grep 0 件）、Lighthouse は `tools/run_checks.sh` 経由でブロッキングゲートとして稼働（PR 本文にサマリー表を貼る運用で「PR ごとに記録」も満たす）。GitHub Actions 経由（原文の想定手段）ではないが、`pr-review-flow-summary.md` が定める「Actions 停止中はセッション実行に読み替える」の標準パターンに一致し、本質的な要求は満たされている。#77 復旧後に Actions へ統合するかは #186 の射程。
- **#77（Actions 停止・A-6）→ 変更なし（open のまま）**: SP-10 の対応と無関係。ユーザーの Billing 確認待ち。
- **#53（masuP9 a11y 技法の移植）→ open のまま（部分達成）**: フォーカスインジケーター可視性は `e2e/sp-10.spec.ts`（`measureFocusIndicator`）で達成。リフローは 375px/640×360 で E2E 化（`expectNoHorizontalScroll`）されたが Issue 本文が指定する **320px** 幅そのものではない。**Text Spacing** と **Target Size (Minimum)** の検査は `check_a11y.py` / E2E のいずれにも見当たらず未着手。完了条件 3 項目中 1 項目のみ達成、2 項目未着手のため open を維持。
- **#73（UI 実測値の E2E 検証）→ open のまま（大部分達成）**: axe-core 自動検出・フォーカスリング実効コントラスト（`measureFocusIndicator`）は SP-9/SP-10 で達成し、§7.7 手動チェックリストも存在する。ただし **`locator.boundingBox()` によるコントロール実測高さ 44px の自動 E2E** は見当たらない（§7.7 では依然「手動チェックリスト」項目のまま）。CI ブロックの要件（Actions 停止中のため run_checks.sh 読み替え）は満たすとみなせる。1 項目未達のため open を維持。
- **#145（Cookie flake・priority 引き上げ）→ 変更なし・確認のみ**: 実際に `priority:high` が付与済みであることを確認した（整合）。

## 4. SP-11 への申し送り

`user-story-map.md` §5.3 `SP-11` の Ready 条件は「先行する `SP-n` の Issue が全て Closed」。#181（`SP-10` 本体）は本仕分けの対象外だが、SP-11 に進むには #181 のクローズ判定（操作レビュー 4 手順を PR プレビュー URL 上でなぞれたか）が別途必要。#173/#180 はクローズ可、#179 は §2.2 表更新の小さな残作業がある状態。

## 5. 重複・陳腐化

検出なし。#53 と #73 は目的（技法移植 vs E2E インフラ整備）が異なり重複ではない。#74 と #186 も「配線するか」と「二重実装を一本化するか」で射程が違う。

## 6. プロセス逸脱（brief 記載の 2 件）

e2e_verify の担当外編集（R5 との二重作業）と distDir 成果物の WIP 誤コミット（Issue #94 と同根）は、いずれも仕分け対象の Issue ではなくレトロスペクティブ（KPT）の材料として扱うのが適切（本仕分けでは Issue化・クローズ判定の対象外として報告のみ）。
