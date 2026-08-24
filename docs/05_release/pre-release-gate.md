# 提出前ゲート（Pre-Release Gate・終了済み履歴）

> 🔴 **終了済み（2026-08-24 JST・Issue #466）**: 本ゲートの運用は終了した。何を提出前の関門としたかの記録として本ファイルを残すが、**現在の運用は本ファイルではなく各スキルの既定に従う**（`sprint-cycle-router` Step 5 は priority ラベル順で `status:waiting-claude` を消化する）。
> `release:required` / `release:deferred` の 2 ラベルは、本ゲート終了に伴い **全 Issue（31 件）から剥がし、ラベル自体も削除済み**（2026-08-24 JST・GitHub API で実施。`release:` で始まるラベルはリポジトリに 1 つも存在しない）。

> **このファイルは「提出（リリース）前に片付ける Issue と、その着手順」の正本だった**（Issue #452・2026-08-23〜08-24）。
>
> 当時は ルーティン（`sprint-cycle-router` の 2 時間ごとの firing）が **Step 5（バックログ消化）で本ファイルを読み、§2 の表の順に 1 件ずつ着手** していた。順序を変えたいときは本ファイルの表の行を入れ替える運用だった。🔴 **現在この経路は存在しない**（#466 で撤去済み）。以下 §0〜§5 は当時の記述をそのまま残した履歴であり、現在の挙動を規定しない。

---

## 0. なぜこのファイルが要るか

`sprint-cycle-router` SKILL.md Step 5 は `status:waiting-claude` の Issue を `type` で絞らずに拾い、`self-improvement-loop` 消化モードへ渡す。消化モードの選択順は **priority ラベル順（high → medium → なし → low）** で、`priority:high` の該当 Issue は 15 件以上あるため、**提出前に必要な件が先に選ばれる保証がない**。

消化モードは次の上書きを認めている（`self-improvement-loop` SKILL.md「消化モード実行フロー」冒頭・逐語）。

> トリガー起動時の上書き: スケジュールトリガー（ルーティン）から起動された場合、起動プロンプト側（下流プロジェクトの運用メモが定義する実行手順等）が指定する **対象スコープ・件数上限・同 priority 内のタイブレーク順** は本フローの既定値（status:waiting-claude フィルタ・5 件/回・下記タイブレーク）に **優先** する。それ以外（priority ラベルの大小順・サーキットブレーカー等）は本フローに従う。

**本ファイルがその「下流プロジェクトの運用メモ」である。**

🔴 **上書きは許可された 3 項目（対象スコープ・件数上限・同 priority 内のタイブレーク順）だけで表現する。** priority ラベルの大小順は上書き対象外なので、**順序は「対象スコープを `release:required` だけに絞ったうえでの、その中の順序指定」として与える**（§5）。これにより priority の大小順を侵さずにゲート順が一意に決まる。

---

## 1. ラベルの定義（本ゲート専用・2 種のみ）

| ラベル | 意味 | ルーティン・入口での扱い |
|---|---|---|
| `release:required` | 提出前に片付ける | ゲート稼働中は **消化スロットの対象スコープそのもの**。順序は §2 の表のとおり（§5） |
| `release:deferred` | 提出後に回す | 🔴 **消化スロット（Step 5）・早期リターン判定 c）・Step 7 のリファインメント対象集合・`/next` のいずれからも除外**（＝スプリント対象外） |

- 2 種とも **本ゲートの期間限定**。§4 の解除条件を満たしたら剥がす（撤去作業は #466）
- `status:blocked` とは意味が違う（`blocked` は「前提が未成立」・`release:deferred` は「前提は成立しているが提出後で足りる」）。混ぜない
- 🔴 **`release:deferred` を Step 7 の除外に入れる理由**: `self-improvement-loop` Step G-1.5 は `priority:low` かつ滞留の Issue を拾い、Step G-6 が「取り組む / **やめる（クローズ）** / 束ねる / 保留」のいずれかへ **必ず** 遷移させる。除外しないと、§3 で「クローズはしない」と決めた Issue がリファインメントで静かにクローズされる

---

## 2. ゲート対象（`release:required`）と着手順

**上から 1 件ずつ着手する。** 同時に複数へ手を広げない（CP-4 のロックと相性が悪い）。

| 順 | Issue | 何が起きているか（実物で確認済み） | 提出前に必要な理由 |
|---|---|---|---|
| **0-a** | **#454** | `main` の E2E が赤い（`/data/gem-index/index.json` が 404） | 与件 §5 はテストコードの存在とコマンド 1 つでの実行・CI 自動実行可能な状態を求めており、**E2E が赤いまま他を直しても提出できない**。実測は下記 |
| **0-b** | **#455** | 同上（`.open-next/assets` 未生成という別角度の見立て） | 同上。#454 / #457 と同一症状の可能性が高い |
| **0-c** | **#457** | 同上（失敗の内訳: SP-18 の Gem バッジ・SP-19 の見出し） | 同上 |
| **1** | **#365** | 対応済み（PR #548）。`toErrorPresentation()`（`src/ui/i18n/error-message.ts`）に `isAuthConfigured` パラメータを追加し、`isAuthConfigured()`（`src/composition/auth.ts`）を根本で見るよう修正した | レート上限を踏むと **本番に存在しない導線を案内するエラー画面** が出る問題を解消（未認証枠は評価者が踏みやすい） |
| **2** | **#338** | `src/infrastructure/github/dto.ts` は `updated_at: z.string()` / `pushed_at: z.string().nullable()` で **日付として妥当かを検証していない**。`app/**/error.tsx`・`global-error.tsx` はいずれも不在 | 上流の不正日付が `Intl.DateTimeFormat` に渡ると `RangeError` になり、**一覧・詳細が HTTP 500**。与件 §4.1「握り潰さず継続利用可能に保つ」に直撃する |
| **3** | **#354** | 対応済み（PR #552）。`site-header.tsx` の `<header>` 直前に `#main-content` へのスキップリンクを追加し、各ページの `<main>` に `id="main-content"` / `tabIndex={-1}` を付与した | 与件 §4.3 は「キーボードのみで操作できる」を求めている。スキップリンクは与件の明文要求ではなく **WCAG 2.4.1（レベル A）に基づく本プロジェクト独自の基準** だが、キーボード操作性の実効を左右する |
| **4** | **#352** | `app/[locale]/layout.tsx:25` の `description` が日本語リテラル固定 | `/en` でも日本語 description が出る。多言語対応を謳っている分だけ目立つ |
| **5** | **#402** | 対応済み（PR #556）。`prettier --write .` で全ファイルを整形し `npm run format:check` が PASS、`tools/run_checks.sh` に `prettier --check` を配線した | 与件 §4.4「フォーマッタを機械的に検証できる状態」の唯一の穴を解消。充足チェックリストの注記から Prettier 項目を削除済み |
| **5.5** | **#543** | 対応済み（PR #578）。`.github/workflows/quality-checks.yml` を追加し、`D-42` として `D-23` / `D-40` の品質チェック部分を失効させた（実行は Prettier / ESLint / `tsc --noEmit` / Vitest の 4 種・権限は `contents: read` のみ） | push / PR 契機の品質チェックが機械的に再検証できる状態になった。E2E と Lighthouse は従来どおりセッション実行 + PR 本文の結果表で担保する二層構成（本番デプロイに Actions を使わない境界は不変） |
| **5.8** | **#544** | 対応済み（本 PR）。README の「使ってみる」直後に、与件充足チェックリストへの導線と手元確認コマンドを追加した | 評価者が与件充足を確認するまでの導線が長い。コストが小さく効果が大きい |
| **6** | **#366** | `NOTICE` に `Ecosyste.ms` / `Geist` の文字列が 0 件（`Geist` は `layout.tsx` で使用中） | 第三者データ・フォントの帰属表示。公開リポジトリとして提出する以上、権利表示の欠落は避ける |
| **7** | **#401** | リポジトリに `.env*` が 1 つも存在しない | 与件 §6 のセットアップ手順。README に環境変数表があるため致命ではなく、実装系の最後に置く |
| **8** | **#466** | 対応済み（**参照撤去は PR #584 / ラベル剥がし・履歴化は PR #585**）。PR #584 が `.claude/` / `CLAUDE.md` / `docs/rules/` からゲート参照を撤去し（`Closes #466`）、PR #585 が `release:required` / `release:deferred` を全 Issue（31 件）から剥がしてラベル定義を削除したうえで本ファイルを履歴として整えた | 🔴 **解除の発火主体**。これを表の最終行に置くことで、`release:required` が空になる直前に必ず 1 件残り、ルーティンが自力で解除に到達した（置かないと終了済みゲートを毎 firing 読み続けることになっていた） |

> 📌 順序の原則: **順 0 = テストが緑であること（他の全項目の前提）** → **1〜4 = 評価者が触って気づく不具合** → **5 = 機械的証跡の穴** → **6〜7 = 体裁・権利** → **8 = ゲートの撤去**。同じ層の中では「壊れて見える度合い」の大きい順。

### 順 0 の実測（2026-08-23 10:0x JST・Issue #452 のセッション）

同一コンテナで `npx playwright test` を **連続 2 回** 実行し、2 回とも `e2e/sp-18.spec.ts` 2 件・`e2e/sp-19.spec.ts` 6 件が失敗した（1 回目のみ `e2e/a11y.spec.ts` も失敗し、2 回目は通過）。失敗時の画面には「Gem 候補プールを読み込めませんでした。」が出ている。**2 回目も赤いため「新しいコンテナの初回だけ落ちる」（#455 の見立て）では説明できない。**

3 件は同一症状を別角度から起票したものなので、**着手したセッションが重複を統合してよい**（統合したら表の 0-a〜0-c を 1 行に畳む）。

### 飼い主にしかできない残作業（ラベル対象外）

**#241 の `U-3`**（マージ済みブランチの削除）。実測で `git ls-remote --heads origin` が **54 本**（`main` を除き 53 本・2026-08-23 10:21 JST 時点）。`git push --delete` も REST も プロキシが 403 で拒否し、GitHub MCP にブランチ削除ツールが無いため Claude 側から実行できない（`A-6` 相当）。公開リポジトリの第一印象に効くため、提出前に飼い主が実行する。`U-4`（公開）・`U-5`（`main` の保護）は **完了済み**（リポジトリは Public、`main` は `protected: true`）。

---

## 3. スプリント対象外（`release:deferred`）

**消化スロット・リファインメント・`/next` の対象から外す。** 提出後に通常のバックログへ戻す。

| Issue | 事実確認の結果 | 判断 |
|---|---|---|
| **#272** | 🔴 **起票時の前提が仕様と食い違っていた**。`prd.md` §2.4.1 の正本表は `page` の許容値を「**1〜50 の整数（固定値。`per_page` の実値では再計算しない）**」と定め、同節は `per_page=100&page=40` が丸められず GitHub API の 1,000 件上限超過になりうることを **`AC-7` の二層設計に基づく「既知の制約」** として明記している。つまり `page-number.ts:22` の固定 `MAX_PAGE` 比較は **仕様どおりの実装** | 直すなら **`prd.md` §2.4.1 の表と二層記述を先に改訂する** 必要がある（権威順は 仕様 > 現行コード・`intent-gate-rules.md`）。提出直前に仕様を変える必然性がないため提出後へ回す |
| **#97** | 本番で **再現しない**。`/ja/repos/vercel/next.js` も、ロケール接頭辞なしの `/repos/socketio/socket.io` も正常表示（ドット入りリポジトリ名の詳細ページが 500 にならない） | 起票時の `SP-2` プレビューでの事象は、`SP-3` 以降の実装で解消した可能性が高い。**クローズはしない**（原因が一次情報で特定できていないため）。提出後に再検証する |
| **#144** | 本番は OAuth 未設定でログイン導線自体が存在しない（`isAuthConfigured()` が false） | `logout` の CSRF 保護は、ログイン機能が本番で有効になってから意味を持つ |
| **#446** | `../..` 形式は上流（Ecosyste.ms）データ依存の潜在バグ。Gem 一覧経路は `SP-19` で塞ぎ済みで、残るのはダイジェスト経路のみ | 実データでの発生が観測されていない潜在リスク |

---

## 4. ゲートの解除条件

**解除作業の実体は #466**（§2 の表の最終行）。以下をすべて満たしたため、本ゲートの運用を終了した。

- [x] §2 の表の全行（#466 を除く）が closed で、`npm run check` の E2E が緑
      （2026-08-24 JST・最後の 1 件 #543 完了。証跡は **PR #585 のブランチでの `bash tools/run_checks.sh` 実測 1 回**。
      🔴 CI（`.github/workflows/quality-checks.yml`）は E2E / Lighthouse を **意図的に含めない** ため、
      この [x] は「`main` の E2E が恒常的に緑」の根拠にはならない。`main` での E2E の赤を報告する
      #564 / #520 / #468 / #462 は 2026-08-24 JST 時点でいずれも open であり、その扱いは各 Issue が正本）
- [x] `release:required` / `release:deferred` の 2 ラベルを全 Issue から剥がし、ラベル自体を削除する → **実施済み**（2026-08-24 JST・対象 31 件。`release:` で始まるラベルはリポジトリに 0 件）
- [x] ゲート由来の追記を撤去する（#466 の PR で実施）: `sprint-cycle-router` SKILL.md（Step 5 の 2 箇所・§2 早期リターン c）/ `self-improvement-loop` SKILL.md（上書き契約の 1 行・Step G-1.5 の除外 1 行）/ `CLAUDE.md`（ラベル 2 行）/ `.claude/commands/next.md`（除外 1 行）/ `docs/rules/improvement-lane-map.md`（参照 1 行）
- [x] 本ファイルは **履歴として残す**（何を提出前の関門としたかの記録。冒頭に「終了済み」と追記済み）

解除後は Step 5 の既定（priority ラベル順）に戻る。

---

## 5. ルーティンへの指定（消化スロットの上書き）

`sprint-cycle-router` の firing が Step 5 に到達したとき、`self-improvement-loop` 消化モードへ **次の上書きを渡す**。いずれも §0 の引用が許可した 3 項目の範囲に収めてある。

| 上書き項目（許可された 3 項目） | 指定値 |
|---|---|
| **対象スコープ** | `release:required` が 1 件でも open な間は、**`status:waiting-claude` かつ `release:required` の Issue のみ**（既定の除外 — `type:retro-try` / `SP-n` 規約 — はそのまま維持）。`release:deferred` は常に対象外 |
| **同 priority 内のタイブレーク順** | §2 の表の「順」列（0-a → 8）に **一意に従う**。作成日時・監査マイルストーン等の既定タイブレークは適用しない |
| **件数上限** | 1 firing あたり **1 件**（各件は互いに独立で、まとめて着手すると PR が絡む） |
| **`release:required` が空のとき** | 既定のフロー（対象スコープ = `status:waiting-claude` 全件・priority ラベル順 + 既定タイブレーク）へそのまま戻る |

> 🔴 **priority ラベルの大小順は上書きしない**（§0 の引用が上書き対象外と明示している）。対象スコープを `release:required` に絞ることで、priority の大小順を侵さずにゲート順が一意に決まる。実際 `release:required` は `priority:high` 6 件・`medium` 3 件の混在だが、対象スコープを絞ったうえで表の順を「その中の順序」として与えるため、medium の #366 / #401 / #466 も表の位置どおりに着手される。

### 決定木の他ブランチとの優先関係（ゲート稼働中のみ）

- **Step 5.5 ①（`type:retro-try` の stale 再開）を Step 5 より優先しない。** 既定では `status:in-progress` かつ 4 時間超 stale の retro-try が Step 5 より先に処理されるが、ゲート稼働中にこれが続くと 2 時間 cron のスロットが retro-try に吸われ、ゲートが一切進まない（実測: #405 が `type:retro-try` かつ `status:in-progress` で滞留中）。**ゲート稼働中の retro-try 再開は 1 日 1 回までに制限する**
- **Step 7（週次リファインメント）の対象集合から `release:deferred` を除外する**（§1 の理由）

---

## 6. 参照

| ドキュメント | 関係 |
|---|---|
| [`.claude/skills/sprint-cycle-router/SKILL.md`](../../.claude/skills/sprint-cycle-router/SKILL.md) | 決定木の SSOT（Step 5 が本ファイルを参照する） |
| [`.claude/skills/self-improvement-loop/SKILL.md`](../../.claude/skills/self-improvement-loop/SKILL.md) | 消化モードの実行フロー（本ファイルはその上書きを与える運用メモ） |
| [`docs/rules/improvement-lane-map.md`](../rules/improvement-lane-map.md) | レーン責務境界の SSOT（ゲート期間中のみ本ファイルが消化スロットの対象スコープ・順序を上書きする） |
| [`docs/02_requirements/minimum-requirements-checklist.md`](../02_requirements/minimum-requirements-checklist.md) | 与件の充足状況（❌ ゼロ・⚠️ 3 件）。§2 の 順 5（#402・PR #556 で対応済み）は同ファイルの Prettier 注記の解消にあたる |
| [`docs/02_requirements/prd.md`](../02_requirements/prd.md) | §2.4.1 が URL クエリの正本（#272 を `release:deferred` にした根拠） |
| [`docs/05_release/repository-publication-review.md`](./repository-publication-review.md) | 公開可否レビュー（#241 の判定と根拠） |
| [`docs/rules/user-confirmation-minimization.md`](../rules/user-confirmation-minimization.md) | `A-5` / `A-6` の境界（マイルストーン新設を避けた理由・#241 `U-3` が飼い主作業である理由） |
