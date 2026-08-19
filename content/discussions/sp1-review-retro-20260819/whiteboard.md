<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: SP-1 のスプリントレビュー・レトロスペクティブと『常に専門チームで進める』プロセス改定

- 議題ID: `sp1-review-retro-20260819`
- 論点: 飼い主のフィードバック（原文 2 点）: (1)『スプリント開発やリファインメントについて、単独エージェントで進めずに常に専門チームを組成してチームとして進めるようにしてください。メインのエージェントは高コストなモデルなのでオーケストレーターとして、専門チームを組成してタスクを遂行してください。』 (2)『成果物に対するスプリントレビューと、レトロスペクティブを必ずチームで実施して記録を残してください。必要に応じて Issue も作成して後続のスプリントで対応できるようにしてください。』

直前スプリント（SP-1・Issue #26・PR #58・2026-08-19 JST マージ済み）で実際に起きた事実:
- リポジトリはアプリコードゼロの状態から、Next.js 16.3.1 + Tailwind v4 + shadcn/ui(Radix) の骨格、ドメイン(SearchKeywo
- 参加者: `sprint_review`, `process_design`, `retro_facilitator`, `guardrail_eng`, `docs_trace`
- 投稿数: 5
- 更新: 2026-08-19T09:53:01+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

## ラウンド 1

### `retro_facilitator` — 主張
<sub>2026-08-19T09:51:00+09:00</sub>

# レトロスペクティブ（争点E担当）: SP-1 KPT

## Keep
- Vitest 4 + MSW 2 で 7 ファイル 22 テスト green・依存規則チェック PASS・Cloudflare へ実デプロイして操作レビュー手順を完走できる状態でマージ（SD-1/SD-2 の骨格は満たせた）
- ACL の ZodError 層漏れをセルフレビュー段階（マージ前）で検出し safeParse + UpstreamError へ自己修正できた（単独実行下でも一部の自己修正は機能した実例）
- check_architecture_boundaries.py の 57 秒バックトラックを同じ firing 内で発見し 58ms まで修正できた（気づいた後の対応速度は速かった）

## Problem（どの仕組みが欠けていたか。誰が悪いかではなく）
- **P1**: SD-4 の「着手時に読む順序」に `domain-model.md`（値オブジェクト＝ブランド型+スマートコンストラクタの正本）が明示されておらず、`architecture-rules.md` 経由の間接参照に留まっていた。結果、SearchQuery を最初クラスで書いてから書き直す手戻りが発生した。
- **P2**: `self_review_check.py` はチェッカーがタイムアウト（30 秒）した場合に「checker error」として非致命扱いにしており、`check_architecture_boundaries.py` の性能劣化（57 秒）が PR 前ゲートを素通りさせていた。チェッカー自体の異常とチェッカーが検出した違反を区別する仕組みが無く、前者がサイレントに握りつぶされる設計だった。
- **P3**: GitHub Actions のジョブ（deploy-preview 含む）が起動できない状態が未切り分けのまま残り、プレビュー URL 確保を `wrangler versions upload` の手動実行に依存している。SD-1（プレビュー URL 必須）の自動化経路が壊れたまま次スプリントに持ち越されるリスクがある。
- **P4**: SP-1 の残作業（p95 CPU 実測 / Cache Port の器 / シークレット投入・Rate Limiting / installation-token.ts の ClockPort 化）が Issue #26 本文の記述に留まり、後続スプリントが個別に着手・完了判定できる単位（sub-issue・sp 付与）に分解されていない。
- **P5（参考・Try は争点 B/D 側に委ねるためここでは起票しない）**: 単独実行モードでは Layer 1 セルフレビューが観点別フレッシュ文脈の並列サブエージェント（自己修正盲点 64.5% 回避が設計目的）を使えず、メインの読み直しで代替した。これはチーム編成そのものの規律なので、Try の起票は process_design / guardrail_eng の設計（争点 B/D）に委ね、本レーンでは重複起票しない。

## Try（Issue 化候補・優先度順・上位4件）

### Try-1（優先度: 高）P3 に対応
- Issue タイトル: `bug: GitHub Actions のジョブが起動しない（deploy-preview 含む）原因を切り分ける`
- ラベル: `type:retro-try`, `sp:3`
- 完了条件: Actions のジョブが起動不能な原因（org/repo の Actions 権限・runner 在庫・ワークフロー設定のいずれか）を特定し、再現手順付きで記録する。恒久修正できた場合は deploy-preview が実際に緑で走ることを確認する。A-6（アカウント設定）相当と判明した場合は、飼い主に依頼する設定変更を 1 文で明記して Issue に残す（原因調査自体はユーザー確認なしで完遂する・L-077）
- 対応する Problem: P3

### Try-2（優先度: 高）P2 に対応
- Issue タイトル: `fix: self_review_check.py のチェッカータイムアウトをサイレント通過させず Error として扱う`
- ラベル: `type:retro-try`, `sp:3`
- 完了条件: 個別チェッカー（`check_architecture_boundaries.py` 等）が self_review_check.py のタイムアウト閾値内に完了しなかった場合、非致命の「checker error」として PR 前ゲートを通過させず、非ゼロ終了で Error 扱いにする。あわせて主要チェッカーの実行時間を計測してログに残し、`python3 tools/self_review_check.py` を意図的に遅いチェッカーで実行するテストケースで Error 終了を確認する
- 対応する Problem: P2

### Try-3（優先度: 中）P1 に対応
- Issue タイトル: `improvement: SD-4 の読む順序に domain-model.md / application-architecture.md の該当節を明示する`
- ラベル: `type:retro-try`, `sp:2`
- 完了条件: `docs/rules/sprint-development-rules.md` §4 の読む順序表に「値オブジェクト・エンティティを実装する前に `domain-model.md` の該当節（ブランド型 + スマートコンストラクタ規約）を確認する」行を追加する。`architecture-rules.md` との参照が重複しないよう「入口はこちら、詳細は architecture-rules.md 経由」の形に整理し、次にドメイン層を実装するスプリントで同型の手戻りが起きないことをレビューで確認する
- 対応する Problem: P1

### Try-4（優先度: 中）P4 に対応
- Issue タイトル: `feature: SP-1 残作業（p95 CPU 実測 / Cache Port の器 / シークレット投入・Rate Limiting / installation-token.ts の ClockPort 化）を独立 Issue に分解する`
- ラベル: `type:retro-try`, `sp:2`
- 完了条件: Issue #26 に列挙されている残作業 4 件を、それぞれ検証可能な完了条件・`sp:N` 付きの sub-issue として起票し（`mcp__github__sub_issue_write` で #26 に紐付け）、sprint-cycle-router の Step 4 が拾えるバックログ状態にする。分解後、#26 自体は「SP-1 の親 Issue」として残すか、全 sub-issue 完了時にクローズするかを 1 行で明記する
- 対応する Problem: P4

## 起票しない候補
- 該当なし（争点 E のブリーフ候補 4 件すべてを Try-1〜4 として起票、P5 は他争点のレーンへ委譲）

### `docs_trace` — 主張
<sub>2026-08-19T09:51:05+09:00</sub>

# docs_trace：ドキュメント整合・ラウンド 1

## 整合状態（既存記述 vs 飼い主指示の 2 点）

| ファイル:行 | 現在の記述（要約） | 飼い主指示との関係 |
|---|---|---|
| **session-sprint-rules.md §2** | 既定は役割分担型 fan-out（`sp:5` 以上ファイル非重複分割で並列 / `sp:1`〜`sp:3` は単独実行）。議論型 `discussion-review` は Layer 2 トリガーと SD-3 グレーゾーン精査に限定 | 🔴 **変更要**。飼い主指示「常に専門チーム」と矛盾。既定が「単独実行を許す」ため修正必須 |
| **agent-team-summary.md「協調モード振り分け」** | ユーザーが「専門チームを組成して」と明示したら議論型が既定。fan-out は軽微タスク・コスト優先時のみ | 🔴 **矛盾あり**。飼い出指示は「スプリント開発・リファインメントは常に専門チーム」で、ユーザー明示条件がない。全スプリント一律適用か sp/性質で分けるかを決定要す |
| **.claude/skills/sprint-cycle-router/SKILL.md Step 4-3** | Sprint Planning コメント投稿時に `docs/rules/session-sprint-rules.md` の編成欄規則を参照するだけ。複製しない | 🟡 **参照のみ**だが、参照先（session-sprint-rules.md §2）が飼い主指示と矛盾していると、ルーティン判定が古いままになるリスク |
| **.claude/skills/sprint-cycle-router/SKILL.md Step 4-6** | `pr-review-watcher` へ継続で完結。その後のステップなし | 🔴 **変更要**。improvement-lane-map.md では「振り返りレーン：各パイプラインの最終ステップから自動呼び出し」と明記されているのに実装がない＝死蔵 |
| **docs/rules/improvement-lane-map.md §1 振り返りレーン** | 「各パイプラインの最終ステップ」から retrospective 自動呼び出し | 🔴 **矛盾あり**。sprint-cycle-router Step 4-6 には retrospective の呼び出しが無い。improvement-lane-map.md の記述と実装がずれている |
| **.claude/skills/retrospective/SKILL.md line 26** | 「各パイプライン（プロジェクト定義）の最終ステップから自動呼び出しされ」 | 🔴 **矛盾あり**。宣言だけで実装がない。sprint-cycle-router など主要パイプラインスキル（Step 4-6 の最終）から呼び出しがない |
| **.claude/skills/code-review/SKILL.md Step 1** | 観点別フレッシュ文脈ファインダーの並列サブエージェント（自己修正盲点 64.5% 回避） | 🟡 **参照のみ**。SP-1 では使われなかった（メイン単独）。「常にチーム編成」施行後は layer 1 セルフレビューもチーム化が必須か検証要 |
| **docs/rules/sprint-development-rules.md SD-4「ドキュメント読む順序」** | `user-story-map.md` §5.3 → `prd.md` → `inception-deck.md` → `project-mission.md` の順 | 🟡 **参照のみ**だが、次フェーズでアプリコードを触る前に domain-model.md / application-architecture.md / testing-strategy.md を読む手順が **明記されていない**（§4-4 では触れられているが、着手時の読む順序表 SD-4 には入っていない）。SP-1 の値オブジェクト手戻りの一因 |

## retrospective スキルの起動経路（調査結果）

**結論: 現在、実装上の呼び出し元が無い（死蔵）**

- `retrospective` SKILL.md line 26：「各パイプラインの最終ステップから自動呼び出しされ」と書かれている
- `improvement-lane-map.md` §1：「各パイプラインの最終ステップ」から自動呼び出しと記述
- **実装確認**:
  - `sprint-cycle-router` SKILL.md Step 4-6：`pr-review-watcher` へ継続で終わる。その後 retrospective を呼ぶ実装なし
  - `pr-review-watcher` SKILL.md：参照不可（`/home/user/gem-hunter/.claude/skills/pr-review-watcher/SKILL.md` が存在していたが確認待ち）だが、通常は PR マージまでが責務であり、マージ後のレトロスペクティブは呼んでいない確率高い
  - 他パイプラインスキル（`self-improvement-loop` / `workflow-health-check` など）から呼び出し：確認が必要だが、grep では見つからなかった

**対応要: 飼い主指示「レビュー・レトロを必ずチームで実施して記録」を実装するには、どのパイプラインのどこが retrospective を呼ぶべきかを決定・コーディング必要。**

---

## 機械化すべき検査（guardrail_eng の対象）

- 🟡 `session-sprint-rules.md` §2 の編成欄に「単独実行」と書かれた Issue を検出し Warning
- 🟡 PR 本文の Sprint Planning コメント欄が無い Issue・PR を Warning
- 🟡 `[Milestone] M-1 / M-2 / ...` の Sprint Review / Retro が content/discussions/ or content/retrospectives/ に記録されていない Issue を検出

### `process_design` — 主張
<sub>2026-08-19T09:51:45+09:00</sub>

# process_design（プロセス設計）ラウンド1

主担当: 争点 B（常時チーム編成の恒久化）・C（レビュー・レトロの差し込み位置）

## B) 協調モード決定表（sp × 性質）

既存 2 ファイルの役割は変えない: `agent-team-summary.md`＝議論型/fan-out の **選び方の仕組み**（汎用）、
`session-sprint-rules.md` §2＝**スプリント編成欄の既定値**（スプリント固有）。今回の恒久指示は
「スプリント編成欄の既定値」を変える話なので、**書き込み先は session-sprint-rules.md §2 の実体 1 箇所のみ**。
agent-team-summary.md は変更不要（sp:8 の議論型トリガーとして「既存 Layer 2 トリガー」を参照するだけで足り、
新しい振り分け軸を増やすと 2 SSOT 化する）。

| スプリント性質 | sp | 既定モード | 単独実行 |
|---|---|---|---|
| Step4 実装（新規/機能） | 1 | fan-out 最小 2 役割（実装+検証） | **不可**。例外は「1 ファイル・typo/設定値 1 個」のみ、理由 1 行を編成欄に記録 |
| Step4 実装 | 2〜3 | fan-out 3 役割以上（既存どおりファイル非重複分割） | 不可 |
| Step4 実装 | 5 | fan-out 3 役割以上並列 | 不可（現行のまま） |
| Step4 実装 | 8 | 着手前に discussion-review 1 ラウンド（設計方針の相互検証）→ fan-out 実装へ | 不可 |
| リファインメント（self-improvement-loop 整理モード） | — | discussion-review（優先度判断は複数視点が必要。飼い主指示(1)が名指し） | 不可 |
| スプリントレビュー（新設・後述 C） | 全 sp | fan-out 2 役割（受け入れ判定＋残課題仕分け）。sp:8 のみ discussion-review | 不可 |
| レトロスペクティブ | 全 sp | 既存の 3 役割並列（実質 fan-out）のまま容認 | 該当なし |

**編集内容（session-sprint-rules.md §2、該当行の置き換え）**:
> 旧: 「既定は役割分担型 fan-out（`sp:5` 以上はファイル非重複分割で並列 / `sp:1`〜`sp:3` は単独実行）。議論型 `discussion-review` は既存 Layer 2 トリガーと `SD-3` グレーゾーン精査に限定し、使う場合のみ理由を添える。」
> 新: 「飼い主の恒久指示により **単独実行は禁止**。既定は役割分担型 fan-out（メインはオーケストレーターに徹し実装コードを自分で書かない。`sp:1`〜`2` は最小 2 役割 / `sp:3`〜`5` はファイル非重複分割で 3 役割以上 / `sp:8` は着手前に議論型 `discussion-review` を 1 ラウンド追加してから fan-out 実装へ）。例外は『1 ファイル・機械的変更（typo・設定値 1 個）』のみ許容し、単独実行を選んだ理由を編成欄に 1 行記録する。議論型のその他の用途（既存 Layer 2 トリガー・`SD-3` グレーゾーン精査）は `agent-team-summary.md` のまま。」

`sprint-development-rules.md` は不変更（4 規律は「作り方」の規律で「編成」は範囲外）。§5 参照表の
「`session-sprint-rules.md`（単位と `sp:N`）」を「（単位・`sp:N`・チーム編成）」に 1 語追記するだけで足りる。
**SD-5 は新設しない**（同じ規則を 2 か所に実体化することになり D の懸念どおりドリフトの温床になる）。

## C) レビュー・レトロの差し込み位置

sprint-cycle-router は「1 firing = 該当ブランチ 1 つ」。Step4 は同一 firing 内で完結しないことがあり
（4-6 で pr-review-watcher に継続 → 予算切れなら次 firing は Step2/Step3 が拾う）、レビュー・レトロを
決定木の新規トップレベル Step にすると、マージが Step2/Step3/Step4 のどれ経由でも二重管理になる。

**結論: 決定木は変更しない。フックは `pr-review-watcher` 内部（マージ＋公開反映の直後、完了報告の前）に 1 箇所だけ追加する。**
理由: マージに到達する経路（Step2 拾い上げ／Step3 再開／Step4-6 直行）が全て最終的に pr-review-watcher の
「マージ→公開反映」を通るため、ここに 1 回差し込めば経路によらず必ず 1 回だけ実行される（決定木側の
分岐追加が不要＝「1 firing = 1 ブランチ」の設計と衝突しない）。

**発火条件**: PR 本文に `Sprint Goal:` 行がある（＝ SP-n スプリントの PR）場合のみ。改善 Issue・retro-try の
PR は対象外（それぞれ自分のレーンの retro/レビューを持つか、対象外でよい）。

**手順（pr-review-watcher SKILL.md への追記案）**:
1. マージ＋公開反映が完了したら、対象 Issue が `SP-n` 規約タイトルか判定
2. 該当すれば Sprint Review を fan-out 2 役割（受け入れ判定 / 残課題の次 firing 送り仕分け）で実行し、
   結果を **対象 Issue へのコメント**（Sprint Planning コメントの続き）として記録。`sp:8` のときだけ
   discussion-review に切り替え、結論サマリーのみ Issue コメントに書いて全文はホワイトボードを参照させる
3. 続けて `retrospective` スキルを起動（既存 3 役割並列のまま）。Try は既存どおり `type:retro-try` で Issue 化
4. 上記が未実施のまま完了報告しない（`pr-review-watcher` の完了条件チェックリストに 1 項目追加）

**記録の置き場所（SSOT を増やさない）**:
- Sprint Review の判定・根拠 → 対象 SP-n Issue のコメント（新規ディレクトリを作らない）
- sp:8 の discussion-review 全文 → `content/discussions/sprint-review-SP-{n}-{日付}/`（既存の `discussion-review` スキルの保存規約をそのまま流用）
- Retro（KPT・Try）→ 既存 `retrospective` スキルの出力仕様どおり（変更提案なし。呼び出しが漏れていた点だけを塞ぐ）

## コスト影響（概算・1 firing あたり）

- 実装 fan-out 強制（sp:1〜2 も最低 2 役割化）: 追加 **+15〜25K トークン/firing**（役割ごとのドキュメント再読込 + 集計サマリー）。sp:1 の typo 例外を残すことで最小変更の firing まで肥大化させない
- sp:8 着手前 discussion-review 1 ラウンド: 参加者 3〜5 名 × (プロンプト 5K + 出力 3K) + 統合 5K ≈ **+45K トークン**（スプリントの最初の 1 回だけ・繰り返し発生しない）
- Sprint Review（fan-out 2 役割）: 2 × (8K+3K) + 統合 3K ≈ **+25K トークン/マージ**
- Retro（3 役割並列、既存仕様の呼び出し漏れを塞ぐだけ）: 3 × (10K+4K) ≈ **+42K トークン/マージ**（今まで呼ばれていなければ純増、呼ばれていれば増分ゼロ）
- 合計: 通常スプリント（sp:3、マージ 1 回）で概算 **+80〜90K トークン**、sp:8 は 着手時 +45K が上乗せで **+125〜135K トークン**。ドル換算・実測較正は既存の `sprint_session_metrics.py` 相当の枠組みで後日検証すべき（本ラウンドでは概算のみ）

### `sprint_review` — 主張
<sub>2026-08-19T09:52:05+09:00</sub>

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

`AC-1` / `AC-2`（一部・超過達成） / `AC-3`（必達・AR-1 も前倒し達成）/ `SD-2` は満たしている。`SD-1` は bootstrap 例外の範囲で満たしている。**SP-1 固有の p95 CPU 実測ゲートが未達のため accepted_with_conditions とし、次の firing で実測を完了させてから Issue #26 を close する**のが一貫した扱い。それ以外の残作業（⑤⑥ + ClockPort）は後続スプリントへ送ってよい。

### `guardrail_eng` — 主張
<sub>2026-08-19T09:52:46+09:00</sub>

## guardrail_eng round1: 機械強制の実効性（争点D主担当）

前提確認（実測）: `content/retrospectives/` は未作成。`.claude/skills/retrospective/SKILL.md` は「各パイプライン最終ステップから自動呼び出し」を謳うが、`sprint-cycle-router` の決定木（Step 4-6 は pr-review-watcher へ継続するのみ）にレビュー・レトロの呼び出しは無い（brief 記載どおり実測でも確認）。`self_review_check.py` はローカル git 情報のみで完結する設計（API 呼び出しゼロ）。

---

### ① チーム編成の証跡なしでスプリント PR が作られた → **入れない（費用対効果が合わない）**

- 検知方法の候補: PR 作成前フックで Sprint Planning Issue コメントの「編成」欄を検査する、または `content/discussions/` の存在で判定する。
- **却下理由**:
  - 「編成」欄は Issue コメントにしか存在しない。`self_review_check.py` は PR 作成前（`pre-pr-create-check.sh`）に動くローカル git 検査ツールで、GitHub API 呼び出しを一切持たない設計（既存コード内コメント「PR 本文は... 対象外」が示す通り、PR 本文すら未確定の時点で走る）。Issue コメント検査には `gh`/MCP 呼び出しが要り、CLAUDE.md 記載の cloud 403 リスク（`gh` 未同梱・repo スコープ REST が不安定）を Lv3 ブロッキングゲートに持ち込むことになる。API が落ちているだけで無関係な PR が軒並みブロックされる事故経路を作る。
  - `content/discussions/` の有無で代替判定するのも誤検知が大きい: 役割分担型 fan-out（sp:5 以上の既定）は whiteboard を書かない（議論型 discussion-review のときだけ）。正当な fan-out 実行が「証跡なし」と誤検知される。
  - 実装コスト（API 版）: 中〜高（MCP 呼び出し + Issue コメントパース + cloud 403 のフォールバック設計が要る）。リターン（チーム編成の実効性向上）に対して割に合わない。
- 代替: 機械強制ではなく `session-sprint-rules.md` §2 の「編成」欄必須化（既存）＋ Layer 1 セルフレビューでの目視確認に留める。

---

### ② スプリントレビュー・レトロの記録なしで Issue を閉じる / スプリントを終える → **条件付きで実装可能（ただし今は時期尚早・Warning 止まり）**

- 検知方法: `PostToolUse` に `mcp__github__issue_write` 用フックを追加（`.claude/settings.json` へ matcher 追加 + 新規 `.claude/hooks/post-issue-close-retro-check.sh`）。
  - 条件: `tool_input.state`（または `method`）が close 系 かつ `tool_input`/`tool_response` のラベルに `sp:` を含む
  - その場合、`content/discussions/` 配下・（新設予定の）`content/retrospectives/` 配下・`git log --all --grep` で対象 Issue 番号（`#N`）への言及をローカルに grep（API 呼び出し不要・安価）
  - 見つからなければ additionalContext に Warning を注入（**PostToolUse は事後実行のため原理的に非ブロッキング＝ Error 化不可能。Issue は既に閉じた後にしか検知できない**）
- 誤検知リスク: 記録はしたが Issue 番号を明示引用していない（例: ブランチ名だけで紐付け）と false positive。実害は小さい（ブロックしないため）。
- **時期尚早と判断する理由**: 検査対象の「記録の置き場所」が争点C（process_design 担当）でまだ未確定（`content/retrospectives/` 不存在・retrospective スキルが router の決定木から呼ばれていない）。置き場所が決まる前に検査ロジックを書くと、対象不在で常に Warning が空振りするか、逆に決定後の実際の置き場所と食い違って検知漏れになる。**process_design の結論（記録先 SSOT）が出てから実装すべき**（Issue 化して次スプリントへ）。
- 実装コスト: 小（40〜50 行、新規 hook 1 本 + settings.json 1 エントリ）。cost 自体は低いので、置き場所確定後は即着手可能。

---

### ③ tools 系スクリプトのタイムアウトでゲートが素通り（今回発生した実バグ） → **最優先で入れる（Warning・低コスト・高確度）**

**根本原因を実コードで特定した**（`tools/self_review_check.py` / `.claude/hooks/pre-pr-create-check.sh`）:

1. `run_subcheck()`（self_review_check.py L800-811）は**ネストしたサブチェッカー**（`check_architecture_boundaries.py` 等）の異常終了を `subcheck_outcome()` で検出し Warning 化する設計が既にある（L775-798）。ここは対策済み。
2. しかし `self_review_check.py` **自身**がトップレベルで例外（今回のケースなら `subprocess.TimeoutExpired`）を投げると、`__main__` の外側 try/except（L1028-1032）が `print(f"[self-review] checker error: {e}", file=sys.stderr); sys.exit(2)` するだけ。
3. 呼び出し元 `pre-pr-create-check.sh`（L153 相当）は `check_exit=$?` を取るが、判定は `if [ "$check_exit" -eq 1 ]` の**1点のみ**（Error ブロック用）。`check_exit == 2`（内部例外）にも `check_exit == 124`（外側 `timeout 60` によるプロセス kill）にも**分岐が無い**。結果、`check_output`（stderr 込みで捕捉した "checker error" 文言）は変数に入ったまま**誰にも表示されずに握りつぶされる**。Step 6 の additionalContext 注入も `grep -q 'Warning'` でしか拾わないため、"checker error" 文言はそこにも載らない。
4. これが brief 記載の「57 秒バックトラックで self_review_check の 30 秒タイムアウトを超え、PR 前ゲートが checker error で素通りしていた」の実体そのもの（`run_subcheck` の `timeout=30` が内部で TimeoutExpired を投げ、上記 2-3 の穴を通り抜ける）。

**修正案**（`pre-pr-create-check.sh` の該当ブロックのみ・Warning・非ブロック）:
```bash
if [ "$check_exit" -eq 1 ]; then
  hook_block "..."
elif [ "$check_exit" -ne 0 ]; then
  # 新設: self_review_check.py 自体が異常終了（内部例外 exit=2 / 外側 timeout 60 による kill exit=124 等）。
  # ブロックはしない（無人ルーティンを止めない）が、握りつぶさず可視化する。
  check_output="${check_output}
[pre-pr-create-check] self_review_check.py が exit ${check_exit} で異常終了しました。
セルフレビュー機械チェックが実質未実行のまま PR 作成が続行されています。原因を確認してください。"
fi
```
かつ Step 6 の `grep -q 'Warning'` 判定に「上記異常終了メッセージも必ず注入される」ことを保証する（現状 grep 条件を満たさない文言なので、`check_exit -ne 0` のときは無条件で `_ctx` に追記する分岐を足す）。

- **Warning か Error か**: Warning（additionalContext での可視化のみ）。Error 化＝ブロックすると「チェッカーが落ちただけで PR が永久に作れない」というデッドロックを無人ルーティン（sprint-cycle-router）に持ち込む。fail-open の既存方針（コメント L7-8 に明記済み）と整合させ、**可視化だけを追加する**。
- **誤検知リスク**: ほぼゼロ。「チェッカーが異常終了した」という事実そのものが常に真（判定に曖昧さがない）。
- **実装コスト**: 極小（bash 8〜10 行の追加のみ。新規ファイル不要）。
- **無人ルーティンを止めない設計か**: 満たす。ブロックを増やさず、握りつぶしを可視化するだけ。可視化された異常は、後続セッションが `problem-investigation-protocol.md` の 5 ステップ経由で type:bug Issue 化する通常の自律修正ルートに乗る（今回まさにそのルートで直った実績あり）。

---

### 総括（費用対効果の優先順位）

1. **③ を今スプリントで即着手**（低コスト・高確度・実害が実測済み）。Try Issue 化を推奨（`sp:1`、完了条件: exit≠0,1 のケースを合成テストで再現し Warning が additionalContext に現れることを確認）。
2. **② は Issue 化のみ**（process_design の記録先確定を前提条件として明記し、確定後に着手）。
3. **① は入れない**（API 依存 Lv3 ゲートのリスクがリターンに見合わない。プロセス上のドキュメント規律（session-sprint-rules.md §2）で担保する）。
