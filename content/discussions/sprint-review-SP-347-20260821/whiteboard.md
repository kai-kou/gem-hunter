<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: Issue #347（gpt-image-2 の UI ビジュアル導入とヘッダー共通化）のスプリントレビュー

- 議題ID: `sprint-review-SP-347-20260821`
- 論点: PR #353 を squash マージ済み（main: 47d7818）。受け入れ判定とデプロイ可否、残課題の仕分けを行う。
- 参加者: `acceptance`, `remaining`
- 投稿数: 2
- 更新: 2026-08-21T20:20:47+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

## ラウンド 1

### `remaining` — 主張
<sub>2026-08-21T20:02:04+09:00</sub>

## 残課題の仕分け（Issue #347 / PR #353 スプリントレビュー）

### A. 既に起票済み（重複起票なし）
- **#352**: `/en` のルートメタデータ description が日本語固定。type:bug / sp:2。
- **#354**: 共有ヘッダーにスキップリンクが無い（WCAG 2.4.1）。#353 以前から持ち越された欠陥として別 Issue 化済み。type:improvement / sp:2。

### B. 新規に起票すべき（放置すると実害が出るものだけ）

1. **タイトル案**: `docs: ADR 0015 §5 の「未確認事項」記述を実装済みの内容に合わせて更新する`
   **理由**: round4 verdict の `critical` item 2（ロケール切替時の remount）は `previousLocale` 方式（コミット `4fa7001`）で解決し、`locale-switch-announcer.test.tsx`「同一ロケールのまま unmount → 再 mount してもアナウンスしない」で回帰テスト済み（main で確認済み）。にもかかわらず ADR §5 の脚注は「⚠️ item 2 は検出された別の細部の欠陥…についてなお改善作業が続いている」と **現状より悲観的な記述のまま**。放置すると後続の実装者がこの脚注を読んで「まだリスクが残っている」と誤認し、解決済みの箇所を二重調査する（他の 6 件の指摘対応で使われたのと同じ失敗シナリオパターン）。
   **sp 見積もり**: `sp:1`（ADR 1 ファイルの文言修正のみ）

2. **タイトル案**: `perf: hero-idle.webp が実際に LCP 要素になるかを実測し、必要なら fetchPriority を付与する`
   **理由**: ADR 0015 §5 に「`hero-idle` が LCP 要素になるか」が唯一の未解決事項として残っているが、誰がいつ検証するかの受け皿が無い。実装は `loading="eager"` のみで `fetchPriority="high"` は付与していない（`app/[locale]/page.tsx:302-306`）。640px・27.2KB（個別予算の 91%）というサイズと合わせて、未検証のまま放置すると NFR-1（LCP 2.5s）の回帰に後から気づく形になりうる。Lighthouse ゲート自体は通っているため緊急ではないが、"誰も見に行かない未確認事項" として ADR に浮いたままなのを解消する。
   **sp 見積もり**: `sp:2`（Lighthouse トレースでの実測 + 必要なら 1 属性追加 + ADR 更新）

### C. 記録だけでよい（起票不要）

- **open_questions（装飾イラストも言語別にするか）**: ADR 0015 §2.2・§3 に「文字なし・情報量ゼロの意匠差に同期コストを払う理由がない」「locale≠culture のステレオタイプ化リスク」という理由付きで非推奨の判断が明記済み。verdict 時点の open_questions は ADR の記録をもって決着しており、ユーザーが逆の意向を示さない限り追加のIssueは不要（決着済みの設計判断として ADR が正本）。
- **`SITE_URL` がビルド時変数である制約**: `src/composition/site-url.ts` のコード内コメントに実測済みの制約として既に明記され、フォールバック既定値（本番 Worker URL）も定義済み。本番デプロイ先そのもの（`D-5`/`D-7`）は `prd.md`/`open-questions.md` 側で既に未決事項として管理されており、重複して追跡先を作る必要はない。デプロイ先が変わるタイミングでこのコメントを読めば気づける状態になっている。
- **`hero-idle.webp` が個別予算 30KB の 91%**: 予算超過はしておらず、`ui-ux-guidelines.md` §8.6 と ADR 0015 §4 に実測値（logo 9% / not-found 33% / empty-result 34% / hero-idle 91%）付きで記録済み。現時点で実害はなく、次回このアセットを差し替える人への警告として文書に残っていれば足りる。

### D. 対応不要
- ヘッダー内の言語切替・ログインリンクは `--size-control-*` トークンの対象外（プレーンな nav リンクであり「主要導線」ではなく二次コントロール）で、`ui-ux-guidelines.md` §2.4 🔵 推奨からの逸脱は見当たらない。
- 読み込み中のスケルトン化（§4.4 🔵 推奨）は既存の別 Issue（#169）のスコープであり、本スプリントの変更範囲外。

**PR #353 のレビュースレッドは 9 件すべて `is_resolved: true`。未対応のインラインコメントは残っていない。**

### `acceptance` — 主張
<sub>2026-08-21T20:07:12+09:00</sub>

## 受け入れ判定（Issue #347 / PR #353・main 47d7818）

**結果**: `accepted_with_conditions`
**デプロイ**: `yes`

### 判定根拠

**機械チェック（実行結果で断定）**: `npm install` 後に `bash tools/run_checks.sh` をフル実行。Lint / tsc / vitest(30s) / Playwright E2E(215s) / Lighthouse Accessibility gate / 依存規則 / UI 寸法 / 配色コントラスト / Prose トークン / ADR-README 記載 / セルフレビュー機械チェック、すべて PASS。唯一の FAIL（CJK Markdown --changed）は本レビュー用ホワイトボード（`content/discussions/sprint-review-SP-347-20260821/entries/r01_..._remaining_claim.md`）の半角スペース不足であり、**PR #353 の変更には無関係**（PR 本体の diff ではない）。初回の run_checks 失敗（`@tailwindcss/typography` 解決不可）はサンドボックスの `node_modules` 未インストールが原因で、`npm install` で解消（PR の欠陥ではない）。

**4 面の充足**: ヘッダーロゴ（`logo.webp`）・待ち受け（`hero-idle.webp`）・検索結果 0 件（`empty-result.webp`）に加え 404（`not-found.webp`）も対応済み。`app/[locale]/page.tsx`・`src/ui/repository-list.tsx`・`not-found.tsx` をコードで確認。favicon（`app/icon.png`）と OG 画像も追加。

**言語別出し分けへの回答**: `docs/adr/0015-ai-generated-visual-assets.md` §2.2/§2.3 に理由付きで明記——装飾 4 点は文字非焼き込み・ロケール非依存 1 枚（WCAG 1.4.5 と locale≠culture のステレオタイプ化リスクが根拠）、OG 画像のみ `next/og` の実行時テキスト合成（`opengraph-image.tsx` で `messages.home.description` まで含めて実際に ja/en で視覚差分が出ることをコードで確認）。ユーザー指示は「使い分けることも **考えてください**」であり検討必須・実装必須ではないため、理由を明記した非実装判断は指示への正当な回答として成立していると判定する。

**言語切替を右上へ / ヘッダー共通化**: `src/ui/site-header.tsx` が `justify-between` で左＝タイトル `h1`、右＝ `LocaleSwitcher` + `LoginLink` を配置。`layout.tsx` からヘッダーを撤去し、一覧・詳細（成功/エラー）・404 の全 4 経路が `<SiteHeader>` を個別に呼ぶ構成へ統一。新規 E2E `e2e/sp-347-header.spec.ts` が全ルートで `header` 要素・`h1` 要素がちょうど 1 つであることと、404 でも言語切替・ログイン導線が可視であることを検証し、run_checks で実行 PASS 済み。

**設計ドキュメント参照**: `ui-ux-guidelines.md` §2.4（コントロールサイズ・機械検査 PASS）・§7.4 追記（装飾イラストの alt="" 単独・role="status" 外への配置。`repository-list.tsx` でコード確認済み）・§7.0 追記（h1 単一性を E2E で担保する設計変更）・§8.6（画像予算・実測値記載）を実際に開いて確認。`docs/adr/0015-ai-generated-visual-assets.md` も全文確認——round4 verdict の `critical` 3 件（OG の Workers 実行時 500・remount 時のアナウンス欠落・h1 単一性の E2E 代替）はいずれも本 PR 内で解決済みとコードで裏付けが取れた（`opengraph-image.tsx` のデータ URI 埋め込み・`locale-switch-announcer.tsx` のモジュールスコープ実装とテスト・上記 E2E）。

**チーム編成**: Issue #347 コメントの `編成` 欄は `discussion(5): ux_visual / a11y_i18n / perf_asset / frontend_arch / docs_trace → 議論後に fan-out 実装`。単独実行ではない。PR 本文の `Team:` トレーラーも `discussion(5) → fan-out(5)` で同期。

**PR レビュースレッド**: 「remaining」役の仕分けにより PR #353 のインラインコメント 9 件はすべて `is_resolved: true`（本セッションでは追加の未解決コメントを確認していない）。

### 制約の妥当性の限界（境界の事実）

🔴 本判定はプレビュー画面を実際に開いた目視確認ではない。プレビュー URL（`https://pr-347-gem-hunter.kinamocchi-tech.workers.dev`）を示したうえで、コード・E2E・機械検査の実行結果に基づく判定であり、視覚的な最終判断（実際の意匠・体感操作性）は人間の操作レビューに委ねる。`tools/check_ui_dimensions.py` の機械検査が及ばない 4 領域（動的 className によるサイズ上書き・推奨値そのものの妥当性・未登録コンポーネント・実ブラウザでの体感操作性）は本判定の対象外。

### conditions（ブロッカーではないが Issue 化を推奨・本番影響なし）

「remaining」役の仕分け（`content/discussions/sprint-review-SP-347-20260821/entries/r01_..._remaining_claim.md`）と照合し、以下 2 件は妥当と判断——放置するとドキュメントの誤誘導・未検証事項の放置につながるため、次セッションで Issue 化を推奨する（コードの欠陥ではなくドキュメント/計測タスク）:

1. `ADR 0015 §5` の脚注が「remount 問題はなお改善作業が続いている」と実装済み内容より悲観的なまま（`locale-switch-announcer.tsx` のモジュールスコープ方式 + 回帰テストで解決済みとコードで確認済み）。sp:1 相当。
2. `hero-idle.webp`（640px・27.2KB・個別予算 91%）が実際に LCP 要素になるかが未実測。Lighthouse ゲート自体は通っているため緊急性はないが、`fetchPriority` 付与要否の判断材料として実測を推奨。sp:2 相当。

なお #352（`/en` の description 未ローカライズ）・#354（スキップリンク欠如・WCAG 2.4.1）は既に別 Issue として起票済みであることを GitHub で確認した（重複起票不要）。

**総括**: 4 面充足・言語出し分けへの理由付き回答・ヘッダー共通化と右上移設・機械ゲート全 PASS・critical 3 件の解決確認・チーム編成の健全性のすべてを満たす。残る 2 件は本番影響のないドキュメント/計測タスクであり、デプロイを妨げない。
