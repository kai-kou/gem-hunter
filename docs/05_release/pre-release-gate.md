# 提出前ゲート（Pre-Release Gate・SSOT）

> **このファイルは「提出（リリース）前に片付ける Issue と、その着手順」の唯一の正本（SSOT）である。**（Issue #452）
>
> ルーティン（`sprint-cycle-router` の 2 時間ごとの firing）が **Step 5（バックログ消化）で本ファイルを読み、ここに書かれた順序で着手する**。順序を変えたいときは本ファイルだけを書き換える（Issue のラベルや SKILL.md をその都度いじらない）。

---

## 0. なぜこのファイルが要るか

`sprint-cycle-router` SKILL.md Step 5 は `status:waiting-claude` の Issue を `type` で絞らずに拾い、`self-improvement-loop` 消化モードへ渡す。消化モードの選択順は **priority ラベル順（high → medium → なし → low）** で、`priority:high` の該当 Issue は 15 件以上あるため、**提出前に必要な 8 件が先に選ばれる保証がない**。

消化モードは次の上書きを認めている（`self-improvement-loop` SKILL.md「消化モード実行フロー」冒頭）。

> トリガー起動時の上書き: スケジュールトリガー（ルーティン）から起動された場合、起動プロンプト側（下流プロジェクトの運用メモが定義する実行手順等）が指定する **対象スコープ・件数上限・同 priority 内のタイブレーク順** は本フローの既定値に優先する。

**本ファイルがその「下流プロジェクトの運用メモ」である。**

---

## 1. ラベルの定義（本ゲート専用・2 種のみ）

| ラベル | 意味 | ルーティンでの扱い |
|---|---|---|
| `release:required` | 提出前に片付ける | 消化スロットで **最優先**。順序は §2 の表のとおり（priority ラベルより本ファイルの順序が優先する） |
| `release:deferred` | 提出後に回す | 🔴 **消化スロットの対象外**（スプリント対象外）。Step 5 も Step 3.5 / Step 4 も拾わない |

- 2 種とも **本ゲートの期間限定**。§4 の解除条件を満たしたら剥がす
- `status:blocked` とは意味が違う（`blocked` は「前提が未成立」・`release:deferred` は「前提は成立しているが提出後で足りる」）。混ぜない

---

## 2. ゲート対象（`release:required`）と着手順

**上から 1 件ずつ着手する。** 同時に複数へ手を広げない（CP-4 のロックと相性が悪い）。

### 順 0: `main` の E2E が赤い（#454 / #455 / #457）— 他の 8 件より先

与件 §5 は「テストがコマンド 1 つで実行でき、成功する」ことを求めており、**E2E が赤いまま他を直しても提出できない**。よって本ゲートの先頭に置く。

**実測（2026-08-23 09:5x JST・Issue #452 のセッション）**: 同一コンテナで `npx playwright test` を **連続 2 回** 実行し、2 回とも `e2e/sp-18.spec.ts` 2 件・`e2e/sp-19.spec.ts` 6 件が失敗した（1 回目のみ `e2e/a11y.spec.ts` も失敗し、2 回目は通過）。失敗時の画面には「Gem 候補プールを読み込めませんでした。」が出ている。**2 回目も赤いため「新しいコンテナの初回だけ落ちる」（#455 の仮説）では説明できない。**

3 件は同一症状を別角度から起票したもの（#454 = `/data/gem-index/index.json` が 404 / #455 = `.open-next/assets` 未生成 / #457 = 再現失敗の内訳）。**着手したセッションが重複を統合してよい**（統合したら本節の行を 1 つに畳む）。

| 順 | Issue | 何が起きているか（実物・本番で確認済み） | 提出前に必要な理由 |
|---|---|---|---|
| 1 | **#365** | `src/ui/i18n/error-message.ts:70` が `rateLimitPrimaryLoginHint` を無条件で付ける。本番 `/ja` にログイン導線は **0 件**（OAuth 未設定） | レート上限を踏むと **存在しない導線を案内するエラー画面** が出る。未認証枠は評価者が踏みやすい |
| 2 | **#338** | `dto.ts` は `pushed_at` / `updated_at` を `z.string()` としか検証せず、`app/**/error.tsx` も不在 | 上流の不正日付で **一覧・詳細が HTTP 500**。与件 §4.1「握り潰さず継続利用可能に保つ」に直撃する |
| 3 | **#272** | `src/domain/model/page-number.ts:22` が固定 `MAX_PAGE`（= 50）と比較。`maxPageFor(perPage)` は `src/ui/pagination.tsx` でしか使われていない | `?per_page=100&page=40` が検証を素通りして GitHub API へ到達。`AC-7` と `prd.md` §2.4.1 の「丸めて表示を続ける」宣言に反する |
| 4 | **#354** | `skip-link` は `site/index.html`（LP）のみ。アプリ側の `app/` `src/` に **0 件** | WCAG 2.4.1（レベル A）。与件 §4.3 のアクセシビリティ項目 |
| 5 | **#352** | `app/[locale]/layout.tsx:25` の `description` が日本語リテラル固定 | `/en` でも日本語 description が出る。多言語対応を謳っている分だけ目立つ |
| 6 | **#402** | `tools/run_checks.sh` に prettier / `format:check` の記述が **1 行も無い**。`npm run format:check` は 110 ファイルで red | 与件 §4.4「フォーマッタを機械的に検証できる状態」の唯一の穴。充足チェックリストの ⚠️ 2 番がそのまま残っている |
| 7 | **#366** | `NOTICE` に `Ecosyste.ms` / `Geist` の文字列が **0 件** | 第三者データ・フォントの帰属表示。公開リポジトリとして提出する以上、権利表示の欠落は避ける |
| 8 | **#401** | リポジトリに `.env*` が **1 つも存在しない** | 与件 §6 のセットアップ手順。README に環境変数表があるため致命ではなく、8 件の最後に置く |

> 📌 順序の原則: **順 0 = テストが緑であること（他の全項目の前提）** → **①〜⑤ = 評価者が触って気づく不具合** → **⑥ = 機械的証跡の穴** → **⑦⑧ = 体裁・権利**。同じ層の中では「壊れて見える度合い」の大きい順。

### 飼い主にしかできない残作業（ラベル対象外）

**#241 の `U-3`**（マージ済みブランチの削除）。実測で `main` 以外に **50 本** 残っている。`git push --delete` も REST も プロキシが 403 で拒否し、GitHub MCP にブランチ削除ツールが無いため Claude 側から実行できない（`A-6` 相当）。公開リポジトリの第一印象に効くため、提出前に飼い主が実行する。`U-4`（公開）・`U-5`（`main` の保護）は **完了済み**（リポジトリは Public、`main` は `protected: true`）。

---

## 3. スプリント対象外（`release:deferred`）

**消化スロット・スプリント着手の対象から外す。** 提出後に通常のバックログへ戻す。

| Issue | 事実確認の結果 | 判断 |
|---|---|---|
| **#97** | 本番で **再現しない**。`/ja/repos/vercel/next.js` も、ロケール接頭辞なしの `/repos/socketio/socket.io` も正常表示（ドット入りリポジトリ名の詳細ページが 500 にならない） | 起票時の `SP-2` プレビューでの事象は、`SP-3` 以降の実装で解消した可能性が高い。**クローズはしない**（原因が一次情報で特定できていないため）。提出後に再検証する |
| **#144** | 本番は OAuth 未設定でログイン導線自体が存在しない（`isAuthConfigured()` が false） | `logout` の CSRF 保護は、ログイン機能が本番で有効になってから意味を持つ |
| **#446** | `../..` 形式は上流（Ecosyste.ms）データ依存の潜在バグ。Gem 一覧経路は `SP-19` で塞ぎ済みで、残るのはダイジェスト経路のみ | 実データでの発生が観測されていない潜在リスク |

---

## 4. ゲートの解除条件

以下をすべて満たしたら、本ゲートの運用を終了する。

- [ ] 順 0（#454 / #455 / #457・統合後は残った 1 件）が closed で、`npm run check` の E2E が緑
- [ ] §2 の 8 件がすべて closed
- [ ] `release:required` / `release:deferred` の 2 ラベルを全 Issue から剥がす（ラベル自体は削除してよい）
- [ ] `sprint-cycle-router` SKILL.md Step 5 の本ファイルへの参照 2 行を撤去する
- [ ] 本ファイルは **履歴として残す**（何を提出前の関門としたかの記録。冒頭に「終了済み」と追記する）

解除後は Step 5 の既定（priority ラベル順）に戻る。

---

## 5. ルーティンへの指定（消化スロットの上書き）

`sprint-cycle-router` の firing が Step 5 に到達したとき、`self-improvement-loop` 消化モードへ **次の上書きを渡す**。

| 上書き項目 | 指定値 |
|---|---|
| **対象スコープ** | `status:waiting-claude` かつ **`release:deferred` が付いていない** Issue（既定の除外 — `type:retro-try` / `SP-n` 規約 — はそのまま維持する） |
| **選択順** | `release:required` を **priority ラベルより先に** 見る。その中の順序は §2 の表の「順」列（1 → 8）に **一意に従う**（priority・作成日時・タイブレークは適用しない） |
| **件数上限** | `release:required` が残っている間は **1 firing あたり 1 件**（8 件は互いに独立で、まとめて着手すると PR が絡む） |
| **`release:required` が空のとき** | 既定のフロー（priority ラベル順 + 既定タイブレーク）へそのまま戻る |

> 🔴 `A-5`（新規マイルストーンの追加）を避けるため、順序はマイルストーンではなく **本ファイルの表** で表現している。順序を変えるときは表の行を入れ替える。

---

## 6. 参照

| ドキュメント | 関係 |
|---|---|
| [`.claude/skills/sprint-cycle-router/SKILL.md`](../../.claude/skills/sprint-cycle-router/SKILL.md) | 決定木の SSOT（Step 5 が本ファイルを参照する） |
| [`.claude/skills/self-improvement-loop/SKILL.md`](../../.claude/skills/self-improvement-loop/SKILL.md) | 消化モードの実行フロー（本ファイルはその上書きを与える運用メモ） |
| [`docs/02_requirements/minimum-requirements-checklist.md`](../02_requirements/minimum-requirements-checklist.md) | 与件の充足状況（❌ ゼロ・⚠️ 4 件）。§2 の ⑥ は同ファイル ⚠️ 2 番の解消にあたる |
| [`docs/05_release/repository-publication-review.md`](./repository-publication-review.md) | 公開可否レビュー（#241 の判定と根拠） |
| [`docs/rules/user-confirmation-minimization.md`](../rules/user-confirmation-minimization.md) | `A-5` / `A-6` の境界（マイルストーン新設を避けた理由・#241 `U-3` が飼い主作業である理由） |
