<!--entry
author: design_acceptance
round: 1
kind: claim
ts: 2026-08-20T13:18:48+09:00
-->

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
