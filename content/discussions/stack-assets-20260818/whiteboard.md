<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: 技術スタック向け Claude Code 資産（スキル・エージェント・MCP）の採否を決める

- 議題ID: `stack-assets-20260818`
- 論点: リサーチ結果の一次情報は docs/01_research/tooling/20260818-claude-code-assets-research.md（2026-08-18 取得）にある。必ず全文を読んでから発言すること。前提事実: (1) 自リポジトリの .claude/skills 19 件・agents 1 件・commands 2 件は全てプロセス系/メタ系で、技術スタック系は 0 件（grep ヒット 0）。(2) アプリコードは 1 行も存在しない（src/ app/ package.json 未作成・SP-13/SP-1 未着手）。(3) Hot 層（.claude/rules/ 常駐 14 ファイル）は 91,600 B で基準比 +16% 超過のため、常駐ルールとしての知識追加は不可。スキル/サブエージェント形態なら description 分のみで予算影響はほぼゼロ。(4) 設計ドキュメントは What/Why/Constraints を高密度に確定済み（application-architecture.md 209 行・testing-strategy.md 148 行・ui-ux-guidelines.md 307 行・cloudflare-infrastructure.md 585 行）。空白は How（手順化）と書いた後の検証。(5) フロントエンド品質ゲート（ESLint / TS strict / axe / Lighthouse 相当）は tools/ に 1 つも無い。(6) @opennextjs/cloudflare 向けの公式資産は Cloudflare にも Vercel にも存在しない（本プロジェクトの肝が空白）。(7) Next.js 16.3 の next dev は AGENTS.md と CLAUDE.md を自動生成/upsert する副作用がある。争点は少なくとも次の 6 つ: A) 公式 MCP（next-devtools-mcp / shadcn MCP / Playwright MCP / Cloudflare Documentation MCP）をどれだけ .mcp.json に足すか。足すと context7 と役割が重複しないか。クラウドコンテナで npx 起動型が実際に動くか。B) 外部スキル/プラグイン（vercel plugin 33 skills / cloudflare skills / secondsky 個別 skill / superpowers / wshobson 個別 plugin）を採るか、それとも自リポジトリの確定済みドキュメントを SSOT として自作スキルに落とすか。外部資産は ADR 0001（shadcn -b radix）・testing-strategy.md の意図的抑制（vitest-pool-workers を入れない・vi.mock は最終手段）・cloudflare-infrastructure.md §7.4（MCP 書き込み禁止）と正面衝突しないか。C) tdd-guard（PreToolUse hook で実装をブロック）を入れて SD-2 を機械強制するか。既存 19 hooks・self_review_check.py の TDD コミット順序検査と二重にならないか。追加モデル呼び出しコストとサードパーティ hook 常駐のリスクをどう見るか。D) Playwright Agents（npx playwright init-agents が .claude/agents/ に 3 ファイル + .mcp.json を生成）を採るか。既存 .claude/agents/ と check_agent_definitions.py に干渉しないか。E) アクセシビリティ（AC-10 / NFR-26 / Lighthouse Accessibility 100 が品質ゲート）を外部資産（Community-Access 11 agents / masuP9 4 skills）で埋めるか、自作の機械ゲート（@axe-core/playwright を CI で回す）で埋めるか。F) 導入タイミング: SP-13/SP-1 着手前の今入れるか、アプリコードが出てから入れるか（今入れると空振りの死蔵スキルになり skill-audit が検出する）。評価軸の優先順位は CP-5（ミッション貢献）> D-9（基盤優先）> 保守コスト。star 数はメンテ品質の指標にならないことが実測で確認されている（VoltAgent ★24k が Next.js 14 前提のまま）。
- 参加者: `stack_fit`, `conflict_guard`, `risk_ops`, `sprint_value`, `budget_meta`
- 投稿数: 12
- 更新: 2026-08-19T08:37:03+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

## ラウンド 1

### `stack_fit` — 主張
<sub>2026-08-19T08:29:28+09:00</sub>

### 前提: 「技術スタック適合性」の判定軸

このレンズでは「star 数」「導入の手軽さ」ではなく、**追随の実態（バージョン表記・最終更新・実行時の依存関係）が本プロジェクトの確定スタックと一致しているか**だけで採否を判定する。リサーチ §1.1 の事実（アプリコード 0 行・`package.json` 未作成）が全争点の前提を変える点に注意。

---

### 争点A: 公式MCPをどれだけ足すか → **段階導入（今は不採用、SP到達時に個別追加）**

- **`next-devtools-mcp`**: `/_next/mcp` は `next dev` の実行時エンドポイント（リサーチ §2.2）。**`next dev` を1度も回していない現時点では接続先が存在せず、機能しない**。加えて `get_errors` / `get_compilation_issues` は Next.js のコンパイル層のエラーであり、**Workers ランタイム（`@opennextjs/cloudflare` 経由の実行）固有の失敗を検出しない**。`cloudflare-infrastructure.md` 7.4 が定める「CLI（wrangler）が一次経路」の実行時検証は `wrangler dev` / `wrangler versions upload` で行うものであり、`next-devtools-mcp` はそれを代替しない。**リサーチ §2.3 が明記する「`@opennextjs/cloudflare` 向け公式資産は存在しない」という欠落を `next-devtools-mcp` は埋めない**（あくまで Next.js dev サーバー層の道具）。→ `SP-1`（Next.js 導入）以降に追加は妥当だが、「これで Workers 実行時の型・コンパイルエラーが拾える」という誤認は禁止すべき。
- **shadcn MCP**: context7 とは役割が重複しない（context7 は汎用ドキュメント取得、shadcn MCP はレジストリの search/install という**操作**）。ただし `ui-ux-guidelines.md` 35 行目が「`-b radix` を付けずに `shadcn init` を実行する」ことを ADR 0001 が名指しする最大の運用リスクとして明記している。MCP 経由の `add` はプロジェクトが既に `-b radix` で初期化済みの `components.json` を読むだけなので `init` 自体を MCP に任せない限り安全 — **`init` は CLI で必ず先に実行し、MCP は `init` 後の `add` のみに限定使用**という運用条件を付けるべき。
- **Playwright MCP**: 争点D（Playwright Agents）採用時に `npx playwright init-agents` が `.mcp.json` を自動生成する（リサーチ §2.4）ため、**単体で先に足すと Agents 導入時に二重定義・競合の恐れ**。D の可否とセットで判断すべきで、A 単体では先送りが妥当。
- **Cloudflare Documentation MCP**: 認証不要かつ既にセッション側で稼働中（リサーチ §1.5・§2.3）。`.mcp.json` への追加コストはほぼゼロで、`cloudflare-infrastructure.md` 7.4 の読み取り許可リストとも整合する。**これだけは今すぐ `.mcp.json` に固定してよい**（他の3つは「今は使えない/条件付き」）。

**結論**: A は一律 yes/no ではない。Cloudflare Documentation MCP のみ即採用可、残り3つは対応する SP 到達（Next.js 導入・shadcn init 完了・Playwright 導入）まで保留。

---

### 争点B: 外部スキル/プラグイン vs 自作スキル → **自作を主、公式個別資産のみ例外的に併用**

リサーチ §3.3 の事実は決定的: **Next.js 16 に明示追随しているコミュニティ資産は2件のみ（★60 と ★22）で、wshobson（★38,899）・VoltAgent 等の大手コレクションは軒並み Next.js 14+/React 18+ のまま**。React 18 前提の記述は React 19 の変更点（例: Server Actions の扱い・`use` フック等）と食い違う可能性があり、**採用すれば「間違った書き方を教えるスキル」を自分で常駐させることになる**。さらに `@opennextjs/cloudflare` を扱うコミュニティ skill はゼロ、MSW2/zod 主題の skill もゼロ（§3.3）。つまり**本プロジェクトの技術的な肝（Next.js on Workers・MSW2 での ACL テスト）に届く外部資産は存在しない**。

一方 `application-architecture.md`(209行)/`testing-strategy.md`(148行)/`ui-ux-guidelines.md`(307行)/`cloudflare-infrastructure.md`(585行) は §1.2 の通り **What/Why/Constraints を高密度に確定済み**。空白は Why ではなく How の手順化。ここに星の多い汎用コレクションを入れても、確定済みの決定と矛盾する記述が紛れ込むリスクの方が「早く書ける」利益より大きい。

**推奨**: 確定ドキュメントから自作スキルへ落とす（自リポジトリ SSOT を単一の真実源に保つ）。例外として個別に採る価値があるのは **ベンダー公式かつバージョン追随の仕組みを持つもの限定**（例: Vercel 公式の Next.js Skills は `vercel/next.js` canary ブランチ同梱で追随されやすい・shadcn は公式 MCP を持つため外部 skill 不要 = リサーチ §3.5 の「shadcn 系サードパーティ skill全般」不採用判断は本レンズでも支持できる）。`nathankim0/clean-architecture-skills` を「自リポジトリの `architecture-rules.md` + `check_architecture_boundaries.py` があるため外部依存を増やさず内容だけ取り込む」とした §3.5 の判断も同じ理由でこのレンズから支持する。

---

### 争点C: `tdd-guard` → **保留（Vitest 4 実追随が未確認）**

リサーチは「Vitest レポーター実装済み」（★2,304・2026-08-16 更新）と書くが、**「Vitest 4 で動作確認済み」とは書いていない**（`vitest@latest` 指定で「実質追随」という推測表現に留まる・§3.3）。`testing-strategy.md` は Vitest 4 の Browser Mode stable 化を前提に採用を決めている（新しい API 面）。PreToolUse hook で Write/Edit を実際にブロックする常駐コードである以上、レポーター実装が Vitest 4 の新しいテスト実行フローと非互換なら **`SD-2`(TDD強制) を助けるはずが実装そのものを止める障害になる**。stack_fit の観点では「メンテ頻度は高いが対象バージョンの一致が文書上確認できない」ため、**採用は Vitest 4 導入後（`SP-4`）に実機で動作検証してから**が筋。今の時点での断定的な採用/不採用は時期尚早。

---

### 争点D: Playwright Agents → **最も適合度が高い。SP-4での採用を推奨**

`npx playwright init-agents` は **Playwright 本体 v1.56+ に同梱**され、プロジェクトが実際にインストールする Playwright のバージョンに直接紐づく（リサーチ §2.4）。これは今回のリサーチで洗い出された資産の中で**唯一「別リポジトリの更新頻度に依存せず、自動的にプロジェクトの実バージョンに追随する」構造を持つ**（wshobson・secondsky 等は全て「そのリポジトリが更新されるか」に運命を握られている）。stack_fit レンズでは他のどの選択肢よりリスクが低い。`testing-strategy.md` が Playwright を `SP-4` で導入すると明記しているため、**導入は SP-4 と同時**が妥当（争点F にも直結）。

---

### 争点E: アクセシビリティ → **実行ゲートは自作（決定済み）、外部資産は技法の参考のみ**

`testing-strategy.md` は既に **`@axe-core/playwright` を `NFR-26` の実行機構として確定**している（§2 道具表）。つまり「E2E の各主要画面で axe を回す」という**強制の仕組み自体は決定済みで、外部プラグインを入れる余地がそもそもない**（Community-Access の37 agents・axe MCP 等は Deque 有料サブスク必須で A-6 相当・§2.4）。stack_fit として外部 a11y 資産に残る役割は「axe-core が拾わない技法（フォーカスインジケーター・320px リフロー・テキスト間隔・ターゲットサイズ）をどう検証するか」という **How の補完**のみ（§3.2・masuP9）。ここは争点Bと同じ結論: **skill/plugin として依存を増やすのではなく、確認された技法だけを自作 E2E テストに移植する**。masuP9 は日本の WAIC 準拠を謳うが、本プロジェクトの `NFR-26` は WCAG 2.2 AA（英語圏基準）を指しているため、**準拠先の基準が一致するかは移植時に個別確認が必要**（無条件の技法採用は避ける）。

---

### 争点F: 導入タイミング → **「今」入れられるものはほぼ無い。SP到達ゲート方式を推奨**

リサーチ §1.1 の事実（`package.json` / `src/` / `app/` / `.github/workflows/` が全て未作成）は F の結論を強く規定する。**争点A・C・D で挙げた資産はすべて `npx <パッケージ>` が対象パッケージ（Next.js・Playwright・shadcn CLI）を前提にした実行**であり、**依存パッケージが存在しない今は物理的に動作しない**。唯一の例外は Cloudflare Documentation MCP（依存パッケージ不要・リモートURL型）。

推奨マッピング:

| 資産 | 導入可能タイミング | 理由 |
|---|---|---|
| Cloudflare Documentation MCP | 今すぐ | 依存パッケージ不要 |
| `next-devtools-mcp` / shadcn MCP | `SP-1`（Next.js/shadcn 導入完了後） | 対象サーバー/CLIが存在しないと接続不能 |
| 自作スキル（B の落とし込み） | 今すぐ着手可（ドキュメントは既に確定済み） | パッケージ非依存 |
| `tdd-guard` | `SP-4`（Vitest導入後）に実機検証してから | Vitest 4 との実追随が未確認 |
| Playwright Agents | `SP-4`（Playwright導入時） | Playwright本体に同梱、他タイミングでは意味がない |
| a11y 技法の移植 | `SP-4` 前後（E2E基盤確立時） | axe実行基盤が無いと検証できない |

🔴 加えて **`next dev` 初回実行時の `AGENTS.md`/`CLAUDE.md` 自動生成リスク（リサーチ §4）は、`next-devtools-mcp` を含む Next.js 依存資産すべての導入前に検証必須**。本リポジトリの `CLAUDE.md` が `@AGENTS.md` 1行に上書きされないことを確認してから `SP-1` の一部として組み込むべきで、「資産追加」と「`next dev` 初回実行の安全確認」は同一PRで扱うべき不可分のタスクである。

### `conflict_guard` — 主張
<sub>2026-08-19T08:29:44+09:00</sub>

# conflict_guard 第1ラウンド主張

## 総論
本リサーチが提示する外部資産の多くは「決定はドキュメントに確定済み、外部資産は How の手順化」という前提（research §1.2 結論）に反し、**確定済み SSOT と矛盾する初期値・慣行を持ち込む**ものが複数ある。SSOT を増やさない観点で最大リスクは B（shadcn/tailwind/clean-arch 系スキル）と F（`next dev` の AGENTS.md 自動生成）。

## A: 公式 MCP 追加 — context7 との重複はないが、`.mcp.json` 運用規律との衝突あり
- context7（`resolve-library-id`/`query-docs`）は静的ドキュメント参照、`next-devtools-mcp`（dev サーバー実行時イントロスペクション）・shadcn MCP（コンポーネント install）・Playwright MCP（ブラウザ操作）は役割が異なり **重複ではない**。
- ただし `cloudflare-infrastructure.md` §7.4 が Cloudflare MCP を「読み取り 4 ツールのみ許可・書き込み禁止」と定めているのに `.claude/settings.json` の `permissions` に未反映という **既存ドリフト**が research §1.5 で既に指摘されている（`/home/user/gem-hunter/.claude/settings.json`）。ここに新規 MCP（shadcn/next-devtools/playwright）を追加すると、同じパターン（ドキュメントで定めた可否がpermissionsに反映されない）を再生産する。**新規 MCP を足すなら、同一 PR で `.claude/settings.json` の許可範囲を明示すること**を条件にすべき。
- **A と D の衝突**: research §2.4 は `microsoft/playwright-mcp` と Playwright Agents（`npx playwright init-agents` が独自に `.mcp.json` を生成）を **別項目として両方リストしている**が、両方導入すると Playwright 用 MCP サーバーが二重登録される。どちらか一方に決めるべきで、両方を「導入候補」のまま残すのは危険。

## B: 外部スキル vs 自作スキル（SSOT 保全の核心）
🔴 **最大の具体的衝突**: `/home/user/gem-hunter/docs/adr/0001-ui-stack.md` §3 は shadcn/ui の新規既定が Radix UI ではなく Base UI に変わったことを把握した上で、a11y 保証の一次情報がある Radix を **明示的に選び直した**（`npx shadcn init -b radix`）。`/home/user/gem-hunter/docs/03_design/ui-ux/ui-ux-guidelines.md` §1「やってはいけないこと」の先頭は「`-b radix` を付けずに `shadcn init` を実行する」ことを名指しで禁止している。
  - secondsky/claude-skills の `tailwind-v4-shadcn` や wshobson の `tailwind-design-system` を **そのまま導入**すると、その skill 本文は一般的な `shadcn init`（= 現在の既定 Base UI）を案内している可能性が高い。中身を読まずに導入すれば、ADR 0001 が最も警戒した運用リスクをスキルが自動的に踏み抜く。**導入するなら中身を全文レビューし、`-b radix` 指定に書き換えてから採用する（外部の記述をそのまま信じない）**。
  - `nathankim0/clean-architecture-skills` は research §3.5 で「導入しない」と既に結論済み。理由も的確（総コミット2・自リポジトリの `architecture-rules.md` + `check_architecture_boundaries.py` で足りる）。この結論は維持すべき。一般に外部の Clean Architecture 系スキルは「集約ルート・リポジトリパターン」を推奨しがちだが、`/home/user/gem-hunter/docs/rules/architecture-rules.md` §3 は「🔴 採らないもの: 集約ルート・リポジトリパターン（永続化）・ドメインイベント・CQRS」と明示している。wshobson の `architecture-patterns` を導入する場合も同じ地雷がある。
- **判定**: B は「自作に落とす」を既定にすべき。外部スキルを採る場合は **導入前の全文レビューで ADR 0001 / `architecture-rules.md` の禁止事項と矛盾しないことを確認**するゲートを必須にする。

## C: tdd-guard — 二重にはならないが、責務境界が曖昧になる
- 既存の TDD 検査は `/home/user/gem-hunter/docs/04_development/testing-strategy.md` §4（フェイク優先・MSW はACLのみ・`vi.mock`最終手段）+ `architecture-rules.md` §4「test: コミット → feat: コミットの順」を **`self_review_check.py`（PR 前・事後・Warning）** が検査する仕組み。
- `tdd-guard` は **PreToolUse hook で Write/Edit を実際にブロックする**（事前・予防）。検査タイミングが違うため機械的な二重実行にはならないが、**「TDD を誰が強制するか」の権威が 2 箇所に分裂**する（self_review_check.py と tdd-guard）。矛盾した判定が出た場合にどちらを正とするか未定義になる。
- `.claude/settings.json`（`/home/user/gem-hunter/.claude/settings.json` 118〜154 行）の `PreToolUse` は既に `matcher: "Bash|mcp__github__create_pull_request"` で `pre-tool-use-router.sh` を配線済み。tdd-guard を追加するには新規 matcher（`Write|Edit`）のエントリを追加する形になり、配列としては技術的に共存可能だが、**19 hooks を「グループ別に整理した表」（CLAUDE.md ハーネス節）に新規グループが増える**ため CLAUDE.md の更新が必須。
- 追加コスト: tdd-guard は編集のたびに追加のモデル呼び出しが発生する（research §3.1 の注記）。Hot 層は既に +16% 超過（research §1.3）というコンテキスト予算問題とは別軸だが、**セッションコストの二重投資**（self_review_check.py は無料の静的チェック、tdd-guard は都度LLM検証）になる点は要検討。
- **判定**: 導入するなら self_review_check.py の「事後・コミット順序」チェックとの役割分担（tdd-guard=予防、self_review_check.py=最終防衛線）を明文化しないと、SSOT が 2 つに割れる。

## D: Playwright Agents — `.claude/agents/` と `check_agent_definitions.py` への実害あり
- 現状 `/home/user/gem-hunter/.claude/agents/` には `owner.md`（PO ロール）が 1 件のみ。`npx playwright init-agents --loop=claude` は **planner / generator / healer の3ファイルを無条件生成**し、かつ `.mcp.json` も生成する。
- `/home/user/gem-hunter/tools/check_agent_definitions.py` は `.claude/agents/*.md` の `tools` フィールドを公式フィルタ仕様と突合し、zero tools（ERROR）や MCP-only（WARN）を検出する。**Playwright Agents が生成する frontmatter がこのチェックを通る保証はない**（外部ツールが Claude Code の tools フィルタ仕様を意識して生成しているとは限らない）。導入したら **必ず `python3 tools/check_agent_definitions.py` を実行してから commit する**運用ゲートが要る。
- `.mcp.json` の生成が既存の `context7`/`github` 登録済み `.mcp.json`（research §1.5）を **上書きするか追記するか未検証**。上書きなら A の「MCP 二重登録」問題と合わせて実質的なデータ損失リスク。導入前に `git diff` で必ず確認すべき。
- **判定**: 「採る」なら generator/healer だけを個別評価し、無条件の一括 init コマンドは使わない（生成物を精査してから commit）。

## E: アクセシビリティ — 自作ゲートを主、外部資産は参考限定
- ADR 0001 §3 の判断基準は「品質保証が一次情報で明文化されているか」。これは **外部 skill/agent パッケージそのものにも同じ基準で適用すべき**。`Community-Access/accessibility-agents`（37 agents 全部同梱）は research §3.2 が自ら「過剰」と注記済み。37 エージェントを丸ごと入れると `skill-audit`（`/home/user/gem-hunter/.claude/skills/skill-audit/SKILL.md`）が検出対象にしている「トリガー衝突」「責務重複」を確実に誘発する（既存 `code-review` スキルの「観点別フレッシュ文脈レビュー」と役割が被る a11y 系エージェントが複数入る）。
- `/home/user/gem-hunter/docs/01_research/tooling/20260818-claude-code-assets-research.md` §1.4 は「フロントエンド品質ゲート（ESLint / TypeScript strict / axe / Lighthouse 相当）が1つも存在しない」ことを明確な空白と認めている。ここは **真の空白**であり、既存資産との衝突はない。
- 判定: 空白を埋める主手段は **`check_architecture_boundaries.py` と同型の自作機械ゲート**（`tools/check_a11y.py` 等、axe MCP か Playwright MCP を叩く）にすべき。masuP9（4 skill・小粒）はスクリプトの参考実装としてのみ読む。37 agent パッケージ（Community-Access）は導入対象から外す。

## F: 導入タイミング — 最優先で押さえるべきは AGENTS.md 自動生成の副作用
- research §4 が指摘する **Next.js 16.3 `next dev` の `AGENTS.md`/`CLAUDE.md` 自動生成/upsert** は、外部資産の中で唯一「明示的に導入していないのに、既存 SSOT（`CLAUDE.md` 本体）を書き換えうる」項目。CLAUDE.md はこのリポジトリの最上位 SSOT（本メッセージの前提コンテキストそのもの）であり、**衝突ではなく「上書き」レベルの実害**になる。
- 対策は `next.config.ts` に `agentRules: false` を **`SP-1` の依存導入と同一コミットで先に設定**すること。これは「決定してから入れる」のではなく「入れる前に無効化する」順序が必要な唯一の項目。
- ADR 0001 §7 の未確認事項#1（shadcn/ui × Next.js 16 互換性、`SP-1` で確認予定）が確定するまでは、B で懸念した shadcn/tailwind 系の外部スキル本文を書き込む・調整する作業は **確定後に着手**すべき（ADR が supersede された場合、外部スキルの記述と自リポジトリの決定が二重にずれる）。
- 結論: 導入順序は ①`agentRules:false` の先行設定 → ②MCP（A, 低リスクなものから）→ ③ ADR 0001 #1 確定後に B（スタック特化スキル、全文レビュー必須）→ ④ D（Playwright Agents、生成物精査必須）→ ⑤ E（自作ゲート）。C（tdd-guard）は責務分担が明文化できた場合のみ。

### `risk_ops` — 主張
<sub>2026-08-19T08:29:46+09:00</sub>

## risk_ops（リスク・運用可能性レンズ）Round 1 主張

### 実地検証（このクラウドコンテナで確認した事実）
- `node v22.22.2` / `npm 10.9.7` / `npx 10.9.7` が使用可能。`npm view next-devtools-mcp` で `registry.npmjs.org` に到達成功（`allowedDomains` に登録済み）。
- `bwrap` は存在しない → `sandbox-rules.md` の記述どおり、**このクラウドコンテナでは sandbox network allowlist は無効**。つまり npx 起動型 MCP が動くかどうかは allowlist の可否ではなく「npm レジストリに到達できるか」だけで決まり、それは確認できた。
- `/opt/pw-browsers/` に **Chromium バイナリが既にプリインストール済み**（`chromium-1194` / `chromium_headless_shell-1194` / `ffmpeg-1011`）。**`npx playwright install --with-deps chromium` を追加実行しなくても Playwright MCP / Playwright Agents はこのクラウドコンテナでブラウザ起動可能**。§4 の「Playwright はハードルが高い」という一般論は、少なくとも本コンテナには当てはまらない（他の環境・将来のイメージ更新では要再検証）。
- `IS_SANDBOX=yes` / `CLAUDE_CODE_REMOTE_ENVIRONMENT_TYPE=cloud_default` を確認。`security-posture-controls.md` の「クラウドの実効防御は ①コンテナ隔離 ②permissions ACL ③PreToolUse フックの3層」という記述と整合。

### A: 公式 MCP をどれだけ足すか
- npx 起動型（`next-devtools-mcp` / shadcn MCP / Playwright MCP）は **技術的にはクラウドで動く**（上記検証）。ただし `.mcp.json` はリポジトリ管理でありローカル実行者とも共有される。`npx -y <pkg>@latest` は **バージョン無指定=毎回最新を取得**する構成で、サプライチェーン上は「破壊的変更・悪意あるパッケージ更新を無条件に取り込む」経路になる。**主張**: 追加する場合は `@latest` を使わず、動作確認済みのバージョンをピン留めして `.mcp.json` に記載する（`agent-team.md` のモデルエイリアス方針とは逆で、MCP パッケージはピン留めが原則）。
- 認証要否の切り分け（A-6 該当）:
  - **不要**: Cloudflare Documentation MCP（既に稼働中）、`next-devtools-mcp`（dev サーバーのローカル `/_next/mcp` に接続するだけ）、shadcn MCP（レジストリ browse は無認証）
  - **A-6 該当（ユーザー操作が物理的に必要）**: Cloudflare Workers Bindings/Builds/Observability MCP（OAuth）、Vercel plugin 内 MCP（Vercel トークン）、axe MCP（後述 E）
  - Cloudflare 16 MCP のうち `cloudflare-infrastructure.md` §7.4 が定めた「読み取り4ツールのみ許可」が `.claude/settings.json` の `permissions` に未反映というドリフトは、**新規 MCP を足す前に埋めるべき既存負債**として扱う（新規追加のたびに同じドリフトを重ねない）。

### B: 外部スキル/プラグインか自作か
- 公式マーケット（`anthropics/claude-plugins-official` 経由の `/plugin install`）は一次配布であり、`skill-audit` の監査対象にもなる正規経路。**リスクは低いと判断**。
- 非公式（`secondsky/claude-skills` 142件・`wshobson/agents` 181 skills 等）は SKILL.md 内に **任意の Bash コマンド列**を含みうる。本リポジトリは `bypassPermissions: true`（確認プロンプトなし）で運用しているため、大量の外部スキルを導入するとは「未読の外部コードに実行許可を事前付与する」のと同義になる。`security-posture-controls.md` の deny リスト・PreToolUse フックは秘密情報アクセスと main push は塞ぐが、**スキル本文が指示する任意の通常コマンド実行そのものは止めない**設計（意図的な補償統制であって漏れではない）。**主張**: 個別スキル単位で導入するなら SKILL.md 全文を読んでから import し、142件一括導入のような形は取らない。
- 保守コストの試算: `wshobson/agents`（202 agents）は `nextjs-app-router-patterns` が "Next.js 14+" 表記のまま（リサーチ文書 §3.1 で確認済み）。**外部資産は本プロジェクトの Next.js 16 追随速度より遅い**ため、導入すれば「本体より古い情報源を保守し続ける」コストが恒久的に発生する。`architecture-rules.md` + `check_architecture_boundaries.py` という自前の機械ゲートが既にあるアーキテクチャ領域は、**自作の勝ち**（リサーチ文書 §3.5 の `nathankim0` 判断と同結論）。

### C: `tdd-guard` を入れるか
- PreToolUse(Write|Edit) で編集経路に外部コードが常駐する。現行 `pre-tool-use-router.sh` は `matcher: "Bash|mcp__github__create_pull_request"` のみなので **マッチャーは衝突しない**（別エントリとして追加可能）が、「フックが最終防衛線」という `security-posture-controls.md` §1.3 の設計思想に **サードパーティが加わる**ことは明記すべき変更。
- 追加のモデル呼び出しコストは、本リポジトリが `env.DISABLE_NON_ESSENTIAL_MODEL_CALLS: 1` を明示設定している方針と**目的が相反**する（tdd-guard の検証呼び出しは非必須モデル呼び出しの典型）。**主張**: 導入するなら `DISABLE_NON_ESSENTIAL_MODEL_CALLS` の例外として明示的に許可する判断が要る。バージョンピン必須（★2,304・MIT・2026-08-16 更新で活性は高いが、PreToolUse ブロック権限を持つコードなので diff レビューなしの自動追従は禁止）。
- 保守コスト: Vitest レポーター実装済みなので技術スタックとの整合は良いが、「誰が `tdd-guard` の破壊的変更に追随するか」の担当（`claude-code-spec-sync` 相当のレーン）が未定。担当を決めずに入れると陳腐化リスクを他資産と同じく抱える。

### D: Playwright Agents
- 上記実地検証の通り、**ブラウザバイナリ既存でクラウド実行の技術的障壁は当初想定より低い**。`npx playwright init-agents --loop=claude` は `.claude/agents/` に 3 ファイル + `.mcp.json` を **生成**する（＝リポジトリの構成ファイルを書き換える）ため、生成後は差分を人間可読な状態でレビューしてからコミットする（生成物をそのまま無検証コミットしない）。
- 認証・課金は不要（A-6 非該当）。**主張**: D は技術的には採用可能だが、生成ファイルのレビュー工程を SD-2（TDD 主体）のワークフローに組み込むまでが導入の完了条件。

### E: アクセシビリティ — axe MCP（有料）は不要、自作機械ゲートで足りる
- axe MCP（Deque 公式）は **axe DevTools 有料サブスク必須 = A-6 相当**。一方 `testing-strategy.md` が既に選定している `@axe-core/playwright` は **無料の OSS ライブラリ**（axe-core 本体）であり、axe MCP とは別物。**主張**: E は「有料 MCP を採る/A-6 確認する」ではなく、**既に決定済みの `@axe-core/playwright` を Playwright E2E テストの中で機械ゲート化する**（自作）だけで要件を満たす。A-6 の課金確認自体が不要になる設計を推奨。

### F: 導入タイミング
- Hot 層予算が既に基準比 +16% 超過（リサーチ文書 §1.3）。**主張**: MCP/skill/subagent 形態（常駐は `description` のみ）に限定するなら Hot 層は圧迫しないが、`.mcp.json` へのサーバー追加は **セッション起動時に毎回 npx を叩く**ため、追加数に比例してセッション起動レイテンシと失敗点が増える。段階導入（`SP-1`〜`SP-4` で確定した範囲だけ先に入れ、以降は各 SP 着手時に必要な分だけ足す）を推奨。
- 🔴 **`CLAUDE.md` 破壊リスクの回避策（具体・必須）**:
  1. `SP-1`（Next.js scaffold 作成コミット）で **`next.config.ts` に `agentRules: false` を最初のコミットから含める**。「後で無効化する」ではなく「有効化させたことがない」状態を最初から作る。
  2. 機械ゲートを追加する: `grep -q '^@AGENTS.md$' CLAUDE.md && exit 1` 相当のチェックを `tools/check_rules_sync.sh` 等の既存衛生スクリプトに 1 行追加し、`next dev` を一度でも実行した後に `CLAUDE.md` が意図せず書き換わっていないか機械検知する。
  3. `next dev` を **初回実行する前に** `git status` で `CLAUDE.md` の追跡状態を確認し、実行直後にも再度 `git diff CLAUDE.md` を取る運用を `SP-1` の Done Criteria に明記する（本リサーチ文書 §4 が「導入前に検証すべき最大のリスク」と既に特定済みのため、これを Issue の完了条件に落とし込む）。

### `budget_meta` — 主張
<sub>2026-08-19T08:30:05+09:00</sub>

# 予算メタ分析: 争点 A〜F の定量評価

## 実測値（基準日 2026-08-18）

| 項目 | 実測 | 備考 |
|-----|------|------|
| `.claude/rules/` (Hot 層) | **91,600 B** | 13 ファイル。予算基準 79,072 B に対して **+15.9%** 既に超過 |
| skill `description` 総量 | **14,506 B** | 19 skill のみ。secondsky が示す「15,000 文字（~15KB）可視化上限」にほぼ到達 |
| `.claude/skills/` スキル数 | 19 件 | 現状 P13・M6・T0（技術スタック系ゼロ） |

**制約構造**: Hot 層の 91.6KB は「追加が事実上不可能」を意味する。必須ルール 14 ファイルと「削減対象外②（実観測ベースの行動規範）」が既に限界。

---

## MCP 追加のコスト構造

### 現状 MCP（デリファード・リスト上部より）

- `context7`: 1 MCP・ツール 2 本（`query-docs` / `resolve-library-id`）
- `github`: 1 MCP・ツール **46 本**（`actions_*` / `create_*` / `search_*` 等）
- クラウド供給: `Cloudflare Developer Platform` (ツール **30+ 本**)・`Slack` / `Google Drive` / `Claude Code Remote`

**1 MCP あたり平均 20〜40 ツール定義が system prompt に展開される。**

### MCP 候補のコスト見積もり

| MCP | ツール数（推定） | 用途 | 予算影響 |
|-----|-------|------|---------|
| `next-devtools-mcp` | 4 | 開発サーバー状態取得 | **最小（既存ツール統合可）** |
| `playwright-mcp` | 6〜8 | E2E 実行・a11y スナップショット | 低・MCP 重複リスク低 |
| `shadcn` MCP | 3 | shadcn/ui registry 検索・install | 最小 |
| `chrome-devtools-mcp` | 5 | Performance trace | 低（選択肢）|
| Cloudflare MCP（docs 除外で既許可） | 12 | Workers / Bindings / Builds | 既計上・追加なし |
| axe MCP | 4 | アクセシビリティ検証 | 低・有料課金（A-6） |

**結論**: MCP 4〜5 本（next-devtools / playwright / shadcn / chrome-devtools 相当）なら合計ツール定義 ~25 本。**System prompt への肥大化は許容範囲**（既にコンテキストの 1〜2%）。「何本足すか」より「何を足さないか」が問題。

---

## Skill `description` 予算 vs Plugin 導入

### シナリオA: 外部 plugin 一括導入（現状との比較）

| Plugin | 含有スキル数 | description 推定B | 累積B |
|--------|---------|---------|------|
| 現状（19 skill） | 19 | 14,506 | 14,506 |
| + vercel plugin | 33 | ~8,500 | **~23,000** ⚠️ |
| + secondsky-claude-skills | 142 | ~45,000 | **~59,000** 🔴 |
| + wshobson/agents（92 agents 内の skill 部分） | 100+ | ~50,000+ | **~64,000+** 🔴 |

**secondsky 導入は既に可視化予算上限（15,000 文字）の 3 倍**。`SLASH_COMMAND_TOOL_CHAR_BUDGET=30000` 環境変数の回避策は「コンテキスト圧縮」ではなく「見えにくくなる」だけで、バックグラウンド検索やコンテキスト計数は変わらない。

### シナリオB: スタック特化スキルの自作（段階導入）

| 段階 | 自作スキル | 作成コスト | description B | 累積 |
|------|--------|-------|---------|------|
| 現状 | 19 | — | 14,506 | 14,506 |
| SP-1〜4（基盤整備） | +4（tdd / testing / a11y / architecture-check） | 低（テンプレート化） | +1,800 | **16,306** ✓ |
| SP-5〜11（機能実装） | +6（UI / state / API / form / cache / error-handling） | 中 | +2,400 | **18,706** ✓ |

**自作ならスキル 29 本・description ~18.7KB で可視化上限以内に収まる。**

---

## TDD Guard 導入の実コスト

### 導入形態による違い

| 形態 | コスト | 制約 |
|-----|------|------|
| **plugin (`tdd-guard` リポジトリから）** | description ~300B | PreToolUse hook が常駐。外部コード更新に依存（バージョンピン必須） |
| **自作ルール + `self_review_check.py` 拡張** | ルール追加 ~500B | インハウス管理。`sprint-development-rules.md` に統合可 |
| **superpower skill（Anthropic 公式）** | description ~600B | **既に公式マーケットにあり、追加導入で新規コストなし** |

**判定**: `tdd-guard` は「実装を行う前にテストを**強制**する」外部 hook。**削減対象外②（実観測ベースの行動規範）** と衝突する（本リポジトリは既に SD-2 で TDD を規律化・実施してから修正検出する設計）。実装拒否フック化するなら追加のモデル呼び出しコスト（推定 +1〜2% 出力トークン）が発生する点も勘案し、スキル形式での検証ルール提供に留めるのが現実的。

---

## Playwright Agents 導入のリスク

### コンテキスト側の影響

ドキュメント §2.4 に記載のとおり、`npx playwright init-agents --loop=claude` は:
- `.claude/agents/` に planner / generator / healer の 3 つの `.md` ファイルを自動生成
- `.mcp.json` を自動更新（Playwright MCP を登録）
- 各エージェントの frontmatter（model / tools / background / isolation）を自動設定

**問題**: §4 に明記の「`AGENTS.md` 自動生成の副作用」と同一リスク。**Next.js 16.3 の `next dev` + Playwright v1.56 が同時に実行環境を装飾すると、`.claude/` ファイルの競合・二重定義が起こる可能性**。

### 導入時の必須検証

1. `next dev` 実行 → 実際に `.claude/` が何を生成するか確認
2. Playwright Agents 初期化 → 上書き / 競合の有無
3. agent 実行テスト → 両者のマージ状態で LLM がどう動作するか

**判定**: 導入は可能だが「最初の 1 回」のセットアップに相当なリスク。SP-1 の「基盤確立」フェーズ内に検証タスク（SP-1.1）として組み込む必要がある。

---

## アクセシビリティ（a11y）資産の最小構成

### 重複回避のための選別

| 候補 | 行・スキル数 | 本スタック適合度 | 採否判定 |
|-----|-----------|--------------|--------|
| masuP9/a11y-specialist-skills | 4 skill | **最高**（Playwright + 独自検証） | **採用・自作スキルに統合** |
| Community-Access/accessibility-agents | 11 agents | 全体・過剰 | reference only |
| wshobson/agents（wcag-audit ほか） | 大量 | 標準的・重複多 | 不採用（secondsky で代替） |

**実装戦略**:
1. masuP9 の 4 skill を参考に、本プロジェクト向けスキル 1 本に統合（`a11y-check.md`）
2. Playwright MCP + axe-core ライブラリ呼び出し（外部 axe MCP は有料なので不採用）
3. WCAG 2.2 AA チェックリスト（`ui-ux-guidelines.md` §6 に既に列挙済み）

**予算**: 自作スキル 1 本（description ~300B）のみ。

---

## 導入タイミング（SP1-2 or 待機？）

### Hot 層予算の現実

| フェーズ | 制約 | 判定 |
|--------|------|------|
| **現在（事前準備）** | Hot 層 91.6KB（限界超過）| MCP / Hot ルール追加は不可 |
| **SP-1〜2（スキル開発基盤）** | 自作スキルのみ | description 追加 ~2KB なら許容 |
| **SP-3〜4（品質ゲート）** | 公式 MCP 活用（no cost） | `next-devtools-mcp` / `playwright-mcp` の最小 2 本は着手可 |
| **SP-5 以降（実装中）** | 都度判定 | ユーザーが「MCP 追加」と明示指定のみ |

**最適な導入順序**:
1. 非 MCP の自作スキル（tdd / testing / a11y）は SP-1 から並列開発可
2. MCP は SP-3（品質ゲート実装）時に `next-devtools-mcp` / `playwright-mcp` の 2 本に限定・確定
3. その他（shadcn / chrome-devtools / axe）は「発生する需要で」「追加予算確認で」後付け

---

## 争点ごとの予算判定

| 争点 | 採否 | 理由（予算軸） |
|-----|------|---------|
| **A: MCP を何本追加するか** | **2 本（next-devtools / playwright）** | その他は axe（有料 A-6）・shadcn（MCP 不要・skill で代替）・chrome-devtools（選択肢） |
| **B: 外部スキル vs 自作** | **自作 6 本 + 参考導入 2 本** | description 予算 ~18.7KB で可視化上限内。外部 plugin は description 肥大化（secondsky で +45KB）で不可 |
| **C: TDD Guard** | **スキル化（不採用 plugin）** | 実装拒否フックは観測規範と衝突。SD-2 検証スキル + 既存 `self_review_check.py` で充分 |
| **D: Playwright Agents** | **SP-1 検証タスク組込** | 無条件導入は不可。`next dev` + Playwright の副作用を最初に検証してから採否決定 |
| **E: a11y 資産** | **masuP9 参考・自作 1 skill** | 全体導入不可（weight 過剰）。本スタック向けスキル 1 本に統合（予算 ~300B） |
| **F: タイミング** | **SP-1 は自作のみ / SP-3 で MCP 確定** | Hot 層超過中のため外部追加は停止。ドキュメント検証（architecture / testing / ui-ux）が優先 |

---

## 不採用の理由付け（ドキュメント §3.5 に記録すべき案件）

1. **vercel plugin**: 33 skills ⇒ description ~8.5KB（当初許容と見えるが、自作スキルとの合算で超過に）
2. **secondsky / wshobson**: 超大型・description 競合のため既定不採用。「本当に必要な 2〜3 スキルだけ参考に手書き」方式へ
3. **community-access agents**: 11 agents 同梱は過剰。masuP9 の方が粒度適切

---

## 追記: 「削減の是非」と「導入の新規タイミング」は独立

本分析は「現状 91.6KB からそれ以上は足さない」を前提にしている。**削減機会（Hot 層を 68KB に戻す）と新規導入（MCP / plugin 追加）は別軸**。削減がない場合、このまま「高い基準で厳選」して進めるのが現実的。削減する選択肢は以下の通り:

- `lessons-core.md` の L-111 / L-113 / L-124 を Warm に降格（削減 ~5.5KB）→ output style との冗長性 引き受け
- `sprint-development-rules.md` の詳細を `-detail.md` に完全移設（削減 ~3KB）→ SD-1〜4 の実行チェックリストが読みづらくなる
- 組み合わせて削減 ~8KB なら「MCP 1 本（~20 ツール定義）追加」の足がかりになる

**本分析では「削減しない現状維持」を前提に判定している。**

### `sprint_value` — 主張
<sub>2026-08-19T08:30:30+09:00</sub>

# sprint_value: スプリント実利レンズからの主張（争点 A〜F）

## 総論
現状 `src/` `app/` `package.json` が **1 つも存在しない**（研究 §1.1）。アプリコードがない段階で導入した資産は、着手対象がないため **効果を発揮しようがなく死蔵する**。したがって本レンズの結論は一貫して「**今日入れるものは最小限、大半は該当スプリント着手時に導入**」（`D-9` 基盤優先 + YAGNI）。

---

## A: 公式 MCP — 資産 × スプリント対応表

| 資産 | 効くスプリント | 導入タイミング | 効かない/死蔵の理由 |
|---|---|---|---|
| **Cloudflare Documentation MCP** | `SP-13`/`SP-1`（Cloudflare 初期設定）・`SP-5`（キャッシュヘッダ確認） | **今すぐ維持**（既に稼働中・認証不要・読み取り専用で常時ゼロコスト） | 死蔵しない。使わない期間があっても保持コストが実質ゼロ |
| **next-devtools-mcp** | `SP-13` 以降の全フロントエンドスプリント（`get_errors`/`get_compilation_issues` で `next build` 省略） | `SP-13` 着手時（`next dev` が起動できて初めて `/_next/mcp` に接続できる） | **今入れると即死蔵**: 接続先の dev サーバーが存在しない |
| **shadcn MCP** | `SP-1` 残作業（`E-2`/`E-5`〜`E-8`）〜`SP-10`（UI コンポーネントを触る全スプリント） | `SP-1` 着手時（`SP-13` でスケルトンが立った直後） | `SP-13` 以前は UI 実装対象がなく死蔵 |
| **Playwright MCP** | `SP-4`（E2E 導入）〜`SP-10`（a11y/キーボード検証） | `SP-4` 着手時 | それ以前は E2E 対象の画面遷移が存在せず死蔵。`testing-strategy.md` も Playwright 導入を `SP-4` と明記済み |
| **axe MCP（Deque 公式）** | 理論上 `SP-10` | **導入しない** | 有料サブスク必須（`A-6`）。`@axe-core/playwright` が既に `testing-strategy.md` で確定済みの無償手段であり、重複導入は SP 予算の無駄 |

---

## B: 外部スキル/プラグイン vs 自作 — 資産 × スプリント対応表

| 資産 | 効くスプリント | 導入タイミング | 死蔵/リスクの名指し |
|---|---|---|---|
| `vercel` plugin（33 skills 一括） | 理論上 `SP-13`〜`SP-11` 全域 | **一括導入は却下**。個別 skill（`next-dev-loop` のみ）を `SP-13` 着手時にチェリーピックするなら検討可 | 一括導入は `skill-audit` が既に警告するトリガー衝突リスク（自作 20+ スキルと衝突）。32/33 skill は使われず死蔵 |
| `cloudflare/skills`（`wrangler`/`workers-best-practices` 等） | `SP-1`/`SP-13` の Cloudflare 作業・`SP-5` | **導入しない**（既存ドキュメントで代替） | `cloudflare-infrastructure.md`（585 行）が手順を既に高密度カバー。スキルを足しても限界的価値が薄く、Hot 層外でも `description` 常駐分だけ純損失 |
| secondsky `vitest-testing` / `playwright-testing` | `SP-4`（テスト基盤確立） | `SP-4` 着手時、個別 skill 単位でのみ | `SP-1`〜`SP-3` は明示的にテスト基盤未整備期間（`testing-strategy.md` §5 緩和規定）。それ以前に入れても呼ばれず死蔵 |
| secondsky `tailwind-v4-shadcn` | `SP-2`（配色トークン確定）〜`SP-6`（UI 実装） | `SP-1`/`SP-2` 着手時 | `ui-ux-guidelines.md`（307 行）が既に 9 種トークン・4 状態表現を確定済みのため、限界価値は「実装手順の省力化」のみ。導入するなら `SP-2` |
| wshobson/agents（202 agents 一括）・VoltAgent 等の大量同梱型 | — | **導入しない** | 研究 §3.5 で「2 世代遅れ」「衝突確実」と既に判定済み。本レンズでも同じ結論: どのスプリントにも専用対応しないまま常駐コストだけ発生する典型的な死蔵資産 |
| **自作スキル: `@opennextjs/cloudflare` デプロイ手順化** | `SP-13`（プレビュー環境確立）・`SP-1` の Cloudflare 固有作業 | `SP-13` 着手時に自作 | 研究 §2.3 が明記する通り **公式・コミュニティともにこの領域の資産がゼロ**。外部に代替がなく、`SD-1`（プレビュー URL）の完了条件に直結するため、ここだけは自作が唯一の選択肢 |

---

## C: `tdd-guard`（`SD-2` の機械強制）

| 導入時期 | 判定 |
|---|---|
| **今（`SP-13`/`SP-1` 着手前）** | ❌ 導入しない。強制対象のテストがまだ存在せず、`Write`/`Edit` を無差別ブロックするだけの死重量 |
| `SP-1`〜`SP-3` | ❌ 導入しない。`testing-strategy.md` §5 が **明示的にテスト基盤未整備期間の緩和**（「書ける対象から書く」）を認めており、`tdd-guard` が hard block すると **この飼い主承認済みの緩和規定と正面衝突** する |
| **`SP-4`（回帰を検知できるスプリント）** | ✅ ここで初めて導入する。Vitest レポーター実装済みで本スタック（Vitest 4）と直結。`SD-2`「テストを先に書く」を機械強制でき、以降 `SP-5`〜`SP-11` 全スプリントに効く |

**結論**: `tdd-guard` は「今すぐ入れるべき」の代表候補に見えるが、**導入タイミングを誤ると既存ルールと矛盾する**ため `SP-4` 固定とする。

---

## D: Playwright Agents（planner/generator/healer）

| 効くスプリント | 導入タイミング |
|---|---|
| `SP-4`（E2E 生成: 操作レビュー手順 → Playwright テスト） 〜 `SP-11`（回帰時の自動修復） | `SP-4` 着手時（`npx playwright init-agents --loop=claude` で `.claude/agents/` 3 ファイル + `.mcp.json` を生成） |

`SP-13`/`SP-1`〜`SP-3` には E2E 対象の往復導線（`SP-3` で往復が繋がる）自体が育っていないため、`SP-4` 以前の導入は死蔵。`healer` は `SP-5` 以降の回帰スプリントで真価を発揮する（テストが壊れたときに直す役割のため、テストが存在しない期間は無意味）。

---

## E: アクセシビリティ（`AC-10`/`NFR-26`/Lighthouse Accessibility 100）

| 資産 | 効くスプリント | 導入タイミング |
|---|---|---|
| `@axe-core/playwright`（既定・無償） | `SP-4`（導入）〜`SP-10`（ゲート達成） | `SP-4` で Playwright と同時導入。追加検討不要 |
| masuP9/a11y-specialist-skills（4 skill・WAIC/WCAG 2.2 AA・小粒） | `SP-10`（誰でも操作できる） | `SP-10` 着手時にチェリーピック |
| Community-Access/accessibility-agents（37 agents 同梱） | 理論上 `SP-10` | **導入しない**（研究 §3.2 も「過剰」と明記）。37 agent 中 `SP-10` で実際に使うのは数個で残りは死蔵 |

`SP-2` のコントラスト比 4.5:1 確認は `ui-ux-guidelines.md` のトークンが既に固定値を持つため、専用スキル不要（操作レビューの目視確認で足りる）。**`SP-10` 以前に a11y 専用資産を入れる理由はない**（`SP-10` を最後に回さない、の警告は「実装順」の話であり「資産導入時期」とは別軸）。

---

## F: 導入タイミング（総括・主担当）

### 今すぐ入れてよいもの（`SP-13` 着手前）
| 資産 | 理由 |
|---|---|
| Cloudflare Documentation MCP | 既に稼働中・認証不要・保持コストゼロ。使われない期間があっても死蔵にならない（read-only ルックアップは「使う時だけ呼ぶ」性質のため） |

**それ以外は基本的に何も入れない。** これが本レンズの核心的主張。

### 各スプリント着手時に導入するもの
| スプリント | このタイミングで入れる資産 |
|---|---|
| `SP-13`（プレビュー環境 + 骨格） | 自作「`@opennextjs/cloudflare` デプロイ」スキル / `next dev` 初回実行時に `CLAUDE.md` が `AGENTS.md` で上書きされないことを検証（研究 §4 最大リスク・**この検証を怠ると Hot 層の規律全体が壊れる**） |
| `SP-1`（残作業） | shadcn MCP / next-devtools-mcp / secondsky `tailwind-v4-shadcn`（採用する場合） |
| `SP-4`（回帰を検知できる） | Playwright MCP / Playwright Agents / `tdd-guard` / secondsky `vitest-testing`・`playwright-testing`（採用する場合） |
| `SP-10`（誰でも操作できる） | masuP9 a11y skills（チェリーピック） |

### 導入しない（死蔵確定と判定するもの）
`vercel` plugin 一括導入・`cloudflare/skills` 一括導入・wshobson/VoltAgent 系大量同梱・Community-Access（37 agents）・axe MCP（有料）。理由は共通: **本リポジトリの完了条件（`SP-n` の操作レビュー手順・`AC-n`）に直接対応しない部分を大量に抱え込み、常駐コスト（`description` 可視化バジェット・トリガー衝突リスク）だけを払う。**

### 衝突解決の適用
`D-9`（基盤優先）: `SP-4` にテスト系資産（`tdd-guard`/Playwright Agents/secondsky testing skills）を集中させたのは、「回帰を検知できる」という基盤スプリントへ実利を集約する判断。YAGNI: 1 スプリントでしか使わない資産（例: masuP9 a11y skill）を先回りで `SP-13` に入れない。

## ラウンド 2

### `conflict_guard` — 反論
<sub>2026-08-19T08:32:42+09:00</sub>

# conflict_guard 第2ラウンド: rebuttal / concession

## 1. @budget_meta「description 総量 14,506B が可視化上限 15,000 にほぼ到達」に反対する（rebuttal・実測で反証）

`.claude/skills/*/SKILL.md` の `description` を実測した（`python3` で frontmatter を正規表現抽出）。

| 指標 | 実測値 |
|---|---|
| バイト数（UTF-8） | 14,240 B（budget_meta の 14,506B とほぼ一致） |
| **文字数（コードポイント）** | **6,394 文字** |
| バイト/文字比 | 2.23（CJK 中心のため 1 文字が平均約2.2バイト） |

**budget_meta の「14,506B ≒ 15,000 文字上限にほぼ到達」は単位の取り違え**。research §3.4 が明示する上限は `15,000 文字`（`SLASH_COMMAND_TOOL_CHAR_BUDGET` の既定値・secondsky README 由来）であり **文字数上限であってバイト数上限ではない**。日本語 description は 1 文字が UTF-8 で平均 2.2〜3 バイトを占めるため、現在の消費は上限の **6,394/15,000 ≒ 43%** に過ぎず、「ほぼ到達」は誤り。**残り約 8,600 文字の余地がある。**

この誤りは budget_meta のシナリオ表自体にも既に矛盾として出ている: シナリオB「SP-1〜4 で +4 skill・+1,800B」の累積を budget_meta は「16,306 ✓」と判定しているが、16,306 はバイト換算なら 15,000 の基準を **超過している**のに `✓`（許容）としている。バイトと文字を混同したまま両方の値を使っており、判定の整合性が取れていない。

**断定**: 実測（文字数基準）に基づけば、**自作スキルは 6 本どころか、現行 19 skill の description 平均文字数（約 337 文字/本）で計算すると `8,600 ÷ 337 ≒ 25 本` 追加できる**。ただし「予算に入るから足してよい」わけではない（私のレンズ＝トリガー衝突・責務重複は別制約として残る）。budget_meta が示した **B の「自作6本+参考2本」という数自体は妥当な範囲**（予算的には十分に収まる）だが、根拠として引用した「上限にほぼ到達」という前提は撤回されるべき。**衝突しない真の空白の主張（R1 §E: フロントエンド品質ゲートの空白）と予算制約は両立する**（予算はむしろ想定より緩い）。

## 2. @stack_fit「Playwright Agents は唯一バージョンドリフトしない構造で最もリスクが低い」に部分譲歩し、条件を強化する（concession + rebuttal）

stack_fit の指摘（Playwright 本体 v1.56+ 同梱 = 別リポジトリの更新頻度に運命を握られない）は**技術的に正しく、B で懸念した secondsky/wshobson のような陳腐化リスクは Playwright Agents には当てはまらない**点は譲歩する。

ただし risk_ops と budget_meta が独立に同じ懸念（生成物の検証必須・`next dev` の AGENTS.md 生成との競合検証）を挙げている点は無視できない。**「生成物をレビューしてから commit する」という運用だけでは不十分**と断定する。理由:

- `check_agent_definitions.py`（`/home/user/gem-hunter/tools/check_agent_definitions.py`）は tools フィルタの **機械検証**であり、目視レビューでは第1フィルタ・background フィルタでの黙った消失（silent removal）を見逃す設計上の理由でこのツールが存在する（ツール自身の docstring が「目視では気づけないため機械検出する」と明記）。目視レビューで足りるなら、そもそもこのツールは要らない。
- したがって導入条件は「読んでから commit」ではなく **「`python3 tools/check_agent_definitions.py` が PASS することを commit 前に確認する」を機械ゲートとして義務化**する。加えて `.mcp.json` は `git diff` で上書きでなく差分追記になっていることを確認する（risk_ops も同旨）。

**判定**: 採用可（stack_fit に同意）。ただし D の「導入完了条件」に上記2つの機械検証を明記しない限り、私のレンズでは「採らない方が安全」側に倒す。

## 3. @risk_ops「非公式スキル大量導入は未読外部コードへの実行権限の事前付与と同義」に同意し、条件を1文で定義する（concession）

risk_ops の指摘（`bypassPermissions: true` 運用下ではスキル本文の任意コマンドをフックが止めない設計）は SSOT 衝突の話とは別軸だが、私の B の主張（「導入するなら全文レビューしてから」）を **セキュリティ側から補強する独立の論拠**であり、全面的に同意する。

外部資産を採ってよい条件を統合して 1 文で定義する:

> **外部資産（skill / plugin / MCP）は、① SKILL.md 全文を人間が読み、② 本リポジトリの確定ドキュメント（ADR / `architecture-rules.md` / `testing-strategy.md` / `cloudflare-infrastructure.md` §7.4 等）と矛盾する記述がないことを個別に確認し、③ パッケージ一括ではなく単体ファイル単位で取り込み、④ 取得先バージョンをピン留めする、の 4 条件をすべて満たした場合に限り採用する。**

①③は SSOT/衝突観点（私）、②も SSOT 観点、④は risk_ops のサプライチェーン懸念の反映。4条件すべてが揃わない限り「採らない」を既定にする。

## 4. @sprint_value「死蔵を作らない」と私の「skill-audit のトリガー衝突検出」は同じ結論に**部分的にしか**向かわない（rebuttal）

sprint_value の SP 到達ゲート方式（各スキルを使うスプリントの着手時にのみ導入）は「保持コストの無駄」（死蔵）を防ぐという点で私の主張と方向性は一致する。しかし **完全には一致しない**。

理由: `skill-audit`（`/home/user/gem-hunter/.claude/skills/skill-audit/SKILL.md`）が検出するトリガー衝突・責務重複は「**その時点で同時に存在する description 同士の文言重複**」を問題にする。sprint_value の段階導入は「同時に存在するスキルの絶対数」を減らすので衝突確率は下がるが、**SP-10 到達時点では SP-1〜SP-10 で導入した資産が全て累積して同時に存在する**ため、最終形（SP-11 完了時点）でのトリガー衝突リスクは段階導入でもビッグバン導入でも **量的には変わらない**。段階導入が防ぐのは「今すぐ使われないスキルの保持コスト（死蔵）」であって、「将来のトリガー衝突」ではない。

**結論**: 両者は独立した制約であり、段階導入（sprint_value）は死蔵を防ぐが衝突を防がない。衝突を防ぐには、私が§2で強化した条件（B の全文レビュー・非対象の明記）を **各 SP 到達時の導入ゲートに追加**する必要がある。「段階導入すれば衝突リスクも自動的に下がる」という読み方をするなら、それは誤りとして訂正する。

### `stack_fit` — 反論
<sub>2026-08-19T08:32:47+09:00</sub>

### 1. @budget_meta「MCP は next-devtools / playwright の2本」への反論 — 時間軸を分けると「2本」は過小算定

budget_meta は §争点ごとの予算判定で **A: 2本（next-devtools/playwright）** と数量で結論しているが、これは自分のコスト表と矛盾している。budget_meta 自身の「MCP 候補のコスト見積もり」表は shadcn MCP を「予算影響: 最小（3ツール）」と評価しているのに、最終判定の2本には **理由の説明なく shadcn MCP が脱落している**。さらに Cloudflare Documentation MCP（既に稼働中・認証不要・ゼロコスト）も除外されており、budget_meta の「何を足さないかが問題」という総論と、実際の2本カウントが噛み合っていない。

時間軸で分けて決着させる:
- **「今」（`SP-13`/`SP-1` 着手前）**: 新規に足せる npx 型 MCP は **0本**。理由は round1 で述べた通り、`next-devtools-mcp`（`/_next/mcp` は `next dev` 実行時エンドポイント）・shadcn MCP（`init` 済み `components.json` が前提）・Playwright MCP（対象パッケージ未導入）はいずれも接続先/前提が存在しない。これは budget_meta の §F 表「現在（事前準備）: MCP/Hot ルール追加は不可」という記述とも整合しており、budget_meta 自身が「今の2本」を主張しているわけではない（時間軸を明示していない箇所だけが誤解を招く）。
- **「到達点」（各SPで対象パッケージが揃った後）**: 正しい数は2本ではなく **少なくとも4本**（Cloudflare Documentation MCP＝維持のみ／shadcn MCP＝`SP-1`／next-devtools-mcp＝`SP-1`〜`SP-13`／Playwright由来のMCP＝`SP-4`。詳細は下記3.）。sprint_value の資産×スプリント対応表の方が budget_meta の単一数字より本レンズの結論と整合する。

**結論**: budget_meta の「2本」は最終到達点の数として過小（shadcn を無条件に落とす理由がない）。「今は0本」の部分は同意する。

---

### 2. @risk_ops「`/opt/pw-browsers` にプリインストール済みで低リスク」への一部concession + 残るrebuttal

**concession**: risk_ops の実地検証（Chromium/`chromium_headless_shell` 既存プリインストール）は、リサーチ §4 が挙げた「Playwright はブラウザ実体前提でハードルが最も高い」という一般論を、少なくともこのクラウドコンテナに関しては弱める具体的な反証であり、正当な指摘として受け入れる。round1 で私はこの点を検証せず「実行環境依存」とだけ書いたが、risk_ops の検証によって**ブラウザバイナリ起動の運用障壁は解消済み**と修正する。

**しかし rebuttal**: これは私が round1 の争点Dで挙げた適合度評価の根拠（「Playwright 本体のバージョンに直接紐づく」）とは**別の障壁**を消しただけで、D の導入タイミングの結論は変わらない。`npx playwright init-agents --loop=claude` は Playwright 本体（`playwright` パッケージ）が対象プロジェクトの依存関係として存在することを前提にした操作であり、リサーチ §1.1 の事実（`package.json` が1つも存在しない）が解消されない限り、**「ブラウザが起動できる」ことと「Playwright Agents が意味のある成果物を生成できる」ことは別問題**である。ブラウザバイナリはコンテナ側の準備、Playwright 依存関係はプロジェクト側の準備であり、後者は `SP-4` まで存在しない。→ **D の導入タイミングは `SP-4` のまま変更なし**（sprint_value の表と同結論）。

---

### 3. @conflict_guard「Playwright MCP と Playwright Agents の `.mcp.json` 二重登録」への断定回答

技術的な答えを出す: **Playwright Agents が生成する `.mcp.json` エントリのみを採用し、`microsoft/playwright-mcp` を単体で `.mcp.json` に追加してはならない。**

理由は round1 の私の主張と直結する。争点Dで「Playwright Agents は Playwright 本体に同梱され、プロジェクトが実際にインストールする Playwright バージョンに直接紐づく」ことを最大の強みとして挙げた。`npx playwright init-agents` が生成する `.mcp.json` エントリは、その**同一バージョンの Playwright に紐づいた MCP 定義**である。一方、単体の `microsoft/playwright-mcp`（`@playwright/mcp` パッケージ）は **別リポジトリ・別リリースサイクル**を持ち、`playwright` 本体との版ズレが起こりうる — これはまさに round1 の争点Bで批判した「コミュニティ資産は本体の更新速度から独立してドリフトする」構造と同型のリスクを、公式資産内に持ち込むことになる。

したがって争点A（MCP追加）における Playwright 関連の答えは「単体 MCP を候補に残す」ではなく「**D を採用した時点で自動的に手に入るものだけを使う**」に一本化すべき。budget_meta の「2本（next-devtools/playwright）」という数え方も、この観点では「playwright MCP を独立候補として数えるべきではない」ため訂正が必要（1.の指摘と合わせて、budget_metaの数え方には二重の修正が要る）。

---

### 4. @sprint_value の資産×スプリント対応表への2点の指摘

**(a) `tailwind-v4-shadcn` を `SP-2` 着手時に無条件で導入可としている点は @conflict_guard の指摘を反映していない**: conflict_guard は round1 で「secondsky の `tailwind-v4-shadcn` は本文が一般的な `shadcn init`（= 現在の既定 Base UI）を案内している可能性が高く、`-b radix` 指定に書き換えてから採用する全文レビューが必須」と具体的に指摘した。sprint_value の表（B節）はこれを「`SP-1`/`SP-2` 着手時」と時期だけを示し、**全文レビューという前提条件を表に明記していない**。stack_fit のレンズでは「バージョン表記が新しい（Tailwind v4 追随）」ことと「本プロジェクトの確定済み決定（ADR 0001 の `-b radix`）と一致する」ことは別軸であり、混同すると危険。sprint_value の表に conflict_guard のレビュー条件を統合すべきと主張する。

**(b) `tdd-guard` を「Vitest 4 と直結」と言い切っている点は根拠過剰**: sprint_value は争点Cで「Vitest レポーター実装済みで本スタック（Vitest 4）と**直結**」と書くが、リサーチ本文（§3.3）が明記しているのは「`vitest@latest` 指定で**実質追随**」という推測表現までであり、Vitest 4 の新API（Browser Mode 等）との実動作確認は取れていない。round1 で私が指摘した通り、この差は無視できない: PreToolUse hook として Write/Edit を実際にブロックするコードが対象バージョンと非互換なら実装作業そのものが止まる。sprint_value の「`SP-4` で導入」という**タイミングの結論には同意する**が、「直結」という言葉は言い過ぎであり、**`SP-4` 導入時に実機動作検証を行うことを条件として明記すべき**（無条件の直結扱いは撤回を求める）。

### `risk_ops` — 反論
<sub>2026-08-19T08:33:16+09:00</sub>

## risk_ops Round 2 — rebuttal / concession

### 論点1: tdd-guard（C）— budget_meta の「不採用（plugin 却下・スキル化）」に反対する

@budget_meta は C の判定を「スキル化（plugin 不採用）」と断定した。**この結論に反対する**。

理由: budget_meta 自身の表が認める通り、`tdd-guard` の固有価値は「実装を行う前にテストを**強制**する」PreToolUse ブロック（予防層）にある。これを「スキル化」に置き換えると、実体は @conflict_guard が既に指摘した `self_review_check.py`（PR 前・**事後**の静的チェック）と同じ検知タイミングの層をもう一枚重ねるだけになり、tdd-guard を導入する理由そのもの（事前ブロック）が消える。budget_meta の「削減対象外②（実観測ベースの行動規範）と衝突する」という理由も再検討が必要: 衝突しているのは「モデル呼び出しコストの発生」であって「予防的ブロックという仕組み自体」ではない。私が Round 1 で指摘したのは前者（`DISABLE_NON_ESSENTIAL_MODEL_CALLS=1` との整合）であり、これは**不採用の理由ではなく「採用するなら明示的な例外を切る」という運用条件**に過ぎない。

**3 者の理由は収束しない。断定する**:
- budget_meta = 不採用（plugin 形態そのものを却下）
- conflict_guard = 条件付き採用（自分と self_review_check.py の権威分離を明文化すれば可）
- risk_ops（私） = 条件付き採用（`DISABLE_NON_ESSENTIAL_MODEL_CALLS` の明示例外 + バージョンピンを付ければ可）
- sprint_value / stack_fit = `SP-4` での採用を推奨（stack_fit は Vitest 4 実追随の実機検証を前置条件化）

**私の結論**: conflict_guard・sprint_value・stack_fit と同じ「`SP-4` での条件付き採用」を支持し、budget_meta の「不採用」には反対する。条件は 3 点の AND: ①権威分離の明文化（conflict_guard）②`DISABLE_NON_ESSENTIAL_MODEL_CALLS` の明示例外化 + バージョンピン（risk_ops）③ Vitest 4 での実機動作検証（stack_fit）。

### 論点2: `bwrap` 不在（sandbox 無効）という事実が他 4 名の評価をどれだけ厳しくするか

これは Round 1 で私だけが実地検証した事実であり、他 4 名の分析はいずれも「sandbox の network allowlist が防波堤として機能する」ことを暗黙の前提にしている（誰も明示的に否定していない）。**影響は 2 点で断定できる**:

1. **@conflict_guard の A 論点の指摘（Cloudflare MCP の読み取り限定ポリシーが `permissions` に未反映というドリフト）は「直したほうがいい」ではなく「新規 MCP を 1 本でも足す前の必須前提」に格上げすべき**。`security-posture-controls.md` の設計が正しく機能するのはローカル環境だけで、本リポジトリの主戦場であるクラウドでは network allowlist が完全に無効（`command -v bwrap` で不在確認済み）。つまりクラウドでの実効防御は `permissions.allow/deny` の ACL と PreToolUse フックの 2 層のみであり、Cloudflare MCP の書き込み系ツールが `permissions` で塞がれていない限り、**「ドキュメントで読み取り専用と決めた」ことに実効力がない**。新規 MCP（A の next-devtools/shadcn/playwright を含む）を追加する PR は、このドリフト修正を同一 PR に含めることを **必須条件**とすべきで、conflict_guard の「望ましい」から一段強い要求に修正する。
2. **@conflict_guard の B 論点（外部スキル全文レビュー）も同様に格上げが必要**。「中身を読まずに導入すれば ADR 0001 の運用リスクを踏み抜く」という conflict_guard の指摘は shadcn/tailwind の設定ミスの話だったが、sandbox が無効という事実を足すと射程が広がる: 外部スキル本文の Bash コマンドは `bypassPermissions: true` 下で確認プロンプトなしに実行され、かつ sandbox のドメイン制限も効かない。**唯一の防波堤は deny リスト（cwd 内の秘密ファイルパターンのみ）と PreToolUse フック（main push・PR 作成前検査止まり）**であり、「任意の通常コマンド実行」自体は誰も止めない設計だと `security-posture-controls.md` 自身が明記している。したがって 142 件一括導入のような形（secondsky・wshobson）は「description 予算超過だから不採用」（budget_meta の理由）だけでなく、**「未読の外部コードに無制限の実行権限を事前付与する」という独立したリスク理由でも不採用**であるべきで、budget_meta のコンテキスト予算論だけを根拠にすると「予算さえ空けば少数なら一括導入してよい」という誤読を招く。

### 論点3: @stack_fit の「Cloudflare Documentation MCP のみ即採用可」— MCP は何本まで即採用してよいか断定する

**断定: 今すぐ `.mcp.json` に追加してよい MCP は 1 本のみ（Cloudflare Documentation MCP）。**

理由を stack_fit の主張に一段補強する: 判定軸は「認証要否」ではなく「認証不要 **かつ** 接続先が今すでに存在する（リモート URL 型 or 依存パッケージ不要）」の AND 条件である。`next-devtools-mcp` と shadcn MCP はどちらも認証不要だが、前者は `next dev` の実行時エンドポイント（存在しない）、後者は `shadcn init` 実行後の `components.json` に依存し、どちらも `package.json` が 0 行の現状では**接続先が物理的に存在しない**（stack_fit の A 論点・sprint_value の対応表と同結論）。budget_meta の見積表も「SP-3」時点の着手可否として書いており「今すぐ」とは主張していない（表現が紛らわしいが矛盾ではない）。**5 名の主張は実質的に一致する**: 即採用 = 1 本、残りは全て SP ゲート待ち。認証要否だけで切ると next-devtools-mcp/shadcn MCP も「今すぐ足せる」と誤読されるため、stack_fit の結論を「認証不要」ではなく「認証不要 AND 接続先実在」の二条件で確定させる。

### 論点4: `agentRules: false` 先行設定案は十分か（@conflict_guard も同懸念）— 一部 concession

**concession**: 私の Round 1 の対策 1（`SP-1` の最初のコミットから `next.config.ts` に `agentRules: false` を含める）は、**`next.config.ts` がスキャフォールド時点（`next dev` を一度も実行する前）に生成されることを前提**にしている。標準の `create-next-app` フローはこの前提を満たす（スキャフォールドは dev サーバーを起動しない）が、`cloudflare-infrastructure.md` が指定する Cloudflare 向けスキャフォールド経路（`@opennextjs/cloudflare` 初期化・C3 CLI 等）が同じ順序（config 生成 → 未実行）を保証するかは、**本ラウンドの手元情報だけでは確認できていない**（対象ファイル再読禁止の制約内で断定できない）。したがって「対策 1 だけで十分」という Round 1 の言い方は言い過ぎで、撤回・格下げする。

その上で反論: だからこそ対策 2（機械ゲート: `CLAUDE.md` に `@AGENTS.md` 相当の upsert 痕跡が無いかを検知する grep チェック）と対策 3（`next dev` 初回実行前後で `git diff CLAUDE.md` を取る運用）を**対策 1 の代替ではなく必須の後備え（backstop）として明記すべき**であり、sprint_value の F 節が言う「`next dev` 初回実行時に検証する」という**事後検知だけに頼る設計は不十分**（`git` 管理下なので revert は可能だが、検知が漏れれば「壊れた `CLAUDE.md` のまま次のコミットが積まれる」ウィンドウが生まれる）。**結論**: `agentRules: false` 先行設定（可能な経路では実施）+ 機械ゲート（恒常的な検知）+ 初回実行前後の diff 確認、の **3 点セット全部が必須**であり、どれか 1 つで足りるという主張（私自身の Round 1 を含む）は修正する。`SP-1` の Done Criteria に「Cloudflare 向けスキャフォールド経路で `next.config.ts` が dev 実行前に生成されるか」の実地確認を追加項目として求める。

### `budget_meta` — 反論
<sub>2026-08-19T08:33:24+09:00</sub>

# budget_meta Round 2 反論・修正申告

## 実測再計算: 自作スキル 6 本での description 超過

### 現状と許容限界

| 項目 | 実測値 |
|-----|------|
| 現状 description 総量 | 14,506 B |
| スキル数 | 19 件 |
| **1 本あたりの平均** | **763 B** |
| 可視化上限（secondsky 明記） | 15,000 B |
| 残り予算 | 494 B |

### 自作スキル 6 本追加時の試算

```
追加 description 量 = 763 B/本 × 6 本 = 4,578 B
累積 description = 14,506 + 4,578 = 19,084 B
上限超過量 = 19,084 - 15,000 = +4,084 B（+27%）
```

**修正**: R1 で「自作ならスキル 29 本・description ~18.7KB で可視化上限以内」と述べたが、実際は **4,084 B = 27% 超過**する。本修正は `budget_meta` からの誤断定。

### 許容できる追加本数

```
許容限界 = (15,000 - 14,506) / 763 = 494 / 763 ≈ 0.65 本
実質: 0 本（既に上限到達状態）
```

**判定**: R1「自作 6 本 + 参考導入 2 本」は予算観点から **不可能**。

---

## stack_fit / sprint_value の「段階導入」主張への同意・補正

`stack_fit` の「Cloudflare MCP のみ今すぐ、他は SP 到達まで保留」・`sprint_value` の「SP-n ごとにタイミングを分ける」判断は **予算観点からも必須**。

理由:

- **今は Cloudflare Documentation MCP のみ** → description 追加ゼロ（read-only）
- `next-devtools-mcp` / `shadcn` MCP / `Playwright` MCP：**実行可能時点に入れる**
  - `next-devtools` は `next dev` 稼働時から効く（今は無意味）
  - `shadcn` MCP は `shadcn init` 完了後から効く（SP-1 後）
  - `Playwright` MCP は E2E 対象の画面が繋がる時点（SP-4）から効く

**重要**: 死蔵スキルを避ける実利観点（sprint_value）が、ほぼ同じ時点で「予算超過を招く」予算観点と一致している。2 つのレンズが異なる根拠で同じ結論に達した。

---

## conflict_guard が指摘した「description 肥大化リスク」への定量的査証

### 外部スキル導入での description 爆発

`conflict_guard` が「secondsky / wshobson は大量導入で risk」と述べた点を、skill `description` 単位で検証:

| 外部資産 | スキル数 | 平均 desc（推定） | 追加 description | 評価 |
|---------|---------|--------|---------|------|
| secondsky（142 件） | 142 | ~300-400 B | 約 50KB | 🔴 完全不可 |
| wshobson（92 agents 内 skill） | 92 | ~350 B | 約 32KB | 🔴 完全不可 |
| vercel plugin（33 skills） | 33 | ~250 B | 約 8.5KB | ⚠️ 限界超過 |

**どれを採っても現状 14.5KB を圧倒的に超過する。** conflict_guard の警告は定量的に正当化される。

---

## risk_ops の「バージョンピン必須」への予算的中立性

### ピン有無での `.mcp.json` サイズ差

```
ピンなし: "cmd": "npx -y next-devtools-mcp@latest"  (47 bytes)
ピン有：  "cmd": "npx next-devtools-mcp@1.2.3"      (45 bytes)
差分: -2 bytes（ピン化で若干削減）
```

**予算観点**: バージョンピンしても description 総量・ツール定義数は変わらない。**予算的には中立**。

ただし `risk_ops` が指摘した「サプライチェーン・破壊的変更リスク」は予算軸ではなく運用軸のため、本レンズでは確認できない。セッション起動レイテンシ（MCP サーバー起動数に比例）への影響も予算軸ではなく performance 軸。

---

## sprint_value / conflict_guard vs budget_meta: 本数上限の厳しさ比較

### 3 つのレンズの制約

| レンズ | 制約 | 結論 |
|--------|------|------|
| **budget_meta（予算軸）** | description 15,000 B 可視化上限 | **追加 0 本**（既に 14.5KB でほぼ満杯） |
| **sprint_value（実利軸）** | 死蔵スキルを避ける（YAGNI） | 効くスプリント到達まで 0 本（段階導入） |
| **conflict_guard（SSOT軸）** | ADR/ドキュメント矛盾を避ける | 全文レビュー必須のため実質 0-1 本 |

**3 つのレンズが異なる理由で同じ結論に収束**: 「今は何も足さない」。

- `sprint_value` の「段階導入」（SP 到達時に入れる）は、予算観点でも「その時点で description 再計算する」という逃げ道を開ける
- 例: SP-1 時点で確定スキル 2 本（description +1.5KB）を入れるなら、description 累積は 16KB に上がるが、**まだ可視化上限と無視できない距離**

---

## 重要な修正: R1 の「自作 6 本」推奨は取り下げ

**R1 結論（誤）**:
```
自作スキル 29 本・description ~18.7KB で可視化上限以内に収まる ✗
```

**R2 修正（正）**:
```
現状 14.5KB でほぼ可視化上限（15KB）に到達済み
追加は「段階的 1〜2 本」程度（SP ごとに判断）のみ可能 ✓
```

---

## 最終的な予算判定（修正版）

| 争点 | R1 判定 | R2 修正判定 | 理由 |
|-----|--------|-----------|------|
| **A: MCP 何本** | **2 本**（next-devtools / playwright） | **段階導入・今は 0 本** | Cloudflare 以外は SP 到達まで待つ。予算も死蔵も回避 |
| **B: 外部 vs 自作** | **自作 6 本** | **自作は 0-1 本/SP** | description 上限が既に到達状態。外部導入は不可 |
| **C: TDD Guard** | **スキル化** | **スキル化（後送り）** | 予算影響最小。タイミングは risk_ops に同意 |
| **D: Playwright Agents** | **SP-1 検証** | **SP-4 確定導入** | stack_fit / sprint_value / risk_ops が SP-4 指定 |
| **E: a11y 資産** | **masuP9 参考・自作 1 skill** | **自作ゲートのみ** | description 超過状態では新規 skill 不可 |
| **F: タイミング** | **SP-1 自作のみ** | **今は Cloudflare MCP のみ / 他は SP 到達時** | 3 レンズ合意 |

---

## 最小構成（予算・死蔵・SSOT の 3 軸で許容できる着手案）

**フェーズ A（今・SP-13 着手前）**
- ✅ Cloudflare Documentation MCP（既稼働・追加コストゼロ）
- ❌ 外部スキル一切不導入

**フェーズ B（SP-1 着手時）**
- ✅ 自作スキル 1 本（`@opennextjs/cloudflare` デプロイ手順）→ +763 B → 累積 15,269 B（実質 15.3KB・限界付近）
- ✅ `next-devtools-mcp` / shadcn MCP（ただし `.mcp.json` は作成し entry のみ作成、実際の接続は後続タスク）

**フェーズ C（SP-4 着手時）**
- ✅ Playwright MCP + Playwright Agents（生成物レビュー済みで commit）
- 🤔 追加スキルがあれば description 容量を再計測してから個別判定

**フェーズ D（SP-10 着手時）**
- ✅ masuP9 a11y skills （チェリーピック 1-2 skill）

---

## 予算メタの立場からの最終主張

1. **現状は可視化上限到達状態**。「自作 6 本」「外部 plugin」いずれも実現不可
2. **段階導入が予算・死蔵・SSOT 3 軸で最適**。sprint_value / conflict_guard の実利判定と予算判定が一致している点に注目
3. **description 計測を SP ごとに再実施する運用**が必須（今後も追加候補が出てくるため）

---

## 他エージェントへの同意・補正

| エージェント | 主張 | 予算観点の補正 |
|-------------|------|-------------|
| **stack_fit** | Cloudflare 以外は SP 到達まで保留 | ✅ 同意（予算超過防止） |
| **sprint_value** | 各 SP ごとに必要なものだけ導入 | ✅ 同意（実利と予算が一致） |
| **conflict_guard** | SSOT 矛盾リスク回避 | ✅ 同意（SSOT 破壊も description 超過も招く外部資産が多い） |
| **risk_ops** | バージョンピン・生成物レビュー必須 | ✅ 同意（予算軸とは別軸で重要） |

---

## 訂正の根拠（実測）

- 現状 description 総量: **14,506 B（実測値）**
- スキル当たり平均: **763 B（14,506 ÷ 19 の実測値）**
- 追加 6 本: **4,578 B（763 × 6）**
- 上限 15,000 B に対して: **+4,084 B 超過（確定）**

### `sprint_value` — 反論
<sub>2026-08-19T08:33:39+09:00</sub>

# sprint_value: round 2 反論 + 統合実行順序表

## 1. stack_fit への確認（対立というより用語のズレを解消）

stack_fit は争点A/Fで next-devtools-mcp / shadcn MCP の導入を一律「`SP-1`」としているが、私の round 1 対応表は **`SP-13`（分割された場合の骨格スプリント）** を先に置いている。これは矛盾ではなく **条件分岐**として決着させる: `user-story-map.md` §5.3 は「`SP-13` に切り出すかは着手セッションの実測判断」であり、切り出さなければ `SP-1` 自体が `E-1`（骨格）を含む。したがって **正しい命題は「`next dev` が初めて起動するスプリント（`SP-13` が起票されていればそちら、なければ `SP-1`）」** であり、固定で「`SP-1`」と書くのは分割ケースを見落とす。stack_fit の結論の骨格は支持するが、**用語を「骨格確立スプリント」に統一すべき**と主張する。

shadcn MCP の運用条件（「`init` は CLI 先行、MCP は `add` のみ」）は私の表になかった具体化であり、**concession として採用**する。

## 2. budget_meta への反論（2 点、両方とも事実誤り）

### 2-1. 「`SP-3` で MCP 確定」は SSOT と矛盾する

budget_meta は §「導入タイミング」表で **「`SP-3`（品質ゲート実装）」に `next-devtools-mcp`/`playwright-mcp` を確定**と書いているが、これは誤り。`user-story-map.md` §5.3 の一次情報を名指しする:

- `SP-3` のゴールは「一覧 → 詳細 → 一覧の往復が通る」（`US-16`/`US-17`/`US-20`）。テストや品質ゲートは含まれない。
- 「回帰を検知できる」＝品質ゲート実装は **`SP-4`** であり、`testing-strategy.md` §2 が Playwright 導入を「`SP-4` で導入する」と明記している。

**訂正**: playwright-mcp の確定タイミングは `SP-3` ではなく **`SP-4`**。budget_meta の予算試算（MCP 2 本を SP-3 に前倒し）は、存在しないテスト対象に対して Playwright MCP を接続することになり、私の round 1 の「死蔵」判定基準（＝接続先が存在しないと機能しない）にそのまま抵触する。`SP-4` に統一すべきと断定する。

### 2-2. 「自作スキル 6 本」は budget_meta 自身の表とも矛盾し、YAGNI 超過

budget_meta の「シナリオB」表は `SP-1〜4` で +4・`SP-5〜11` で +6 の **合計 10 本**を示すが、争点別判定表では「自作 6 本」と書いており、**自己矛盾**している（どちらが正か本人に確認が要る）。

いずれにせよ、**「スプリントで 2 回以上使われるものだけに絞る」という YAGNI 基準で数え直すと、正当化できる自作資産は 2 本のみ**と断定する:

| 自作資産 | 使用スプリント | 2 回以上か |
|---|---|---|
| `@opennextjs/cloudflare` デプロイ手順スキル | `SP-13`（初期構築）+ `SP-1` 残りの Cloudflare 作業 ④⑤ + `SP-4` の GitHub Actions 移行（`INF-20` 例外終了時） | ✅ 3 回 |
| TDD/テスト運用スキル（Vitest/Playwright の本スタック規約をまとめる） | `SP-4`〜`SP-11` の全実装スプリントで毎回参照 | ✅ 8 回 |
| 「architecture-check」skill（budget_meta 案） | — | ❌ **既存の `architecture-rules.md` + `check_architecture_boundaries.py` と完全重複**（stack_fit §B・研究 §3.5 の `nathankim0` 判断と同型）。新規に作る意味がない |
| 「UI / state / API / form / cache / error-handling」の 6 分割 skill（budget_meta 案） | 各領域は `SD-4` の着手時読み順（`user-story-map.md` §5.3 →`ui-ux-guidelines.md` 等）で **既に SSOT として読まれる設計**になっている | ❌ 同じ知識を skill として二重化するだけで、conflict_guard が B で警告した「SSOT を割る」問題を**自作資産自身が引き起こす**。ドキュメントを読めば済むものをパッケージ化しない |
| a11y チェック | `SP-10`（主）+ `SP-2`/`SP-9` の軽量接触 | 🔶 2 回以上使うが、**conflict_guard の提案どおり `tools/check_a11y.py`（機械ゲート）として作るべきでスキル形態は不要**。masuP9 は参考実装に留める（budget_meta も同じ結論だが形態は skill 化と書いており、ここは訂正） |

**結論**: 自作は **2 本（デプロイスキル・テスト運用スキル）+ 1 本の機械ゲートスクリプト（`tools/check_a11y.py`、skill 本数にカウントしない）**。budget_meta の 6〜10 本は死蔵確定資産（architecture-check の重複・6 分割 skill の SSOT 二重化）を含んでおり、YAGNI 基準で棄却する。

## 3. conflict_guard への同意 + 着手順序の修正（concession）

conflict_guard の指摘（ADR 0001 #1 = shadcn/ui × Next.js 16 互換性確認前に外部スキル調整に着手すると二重にずれる）を **全面的に認める**。私の round 1 表は「`SP-1` 着手時」とだけ書き、ADR 確認前後を区別していなかった。

**修正**: `SP-1` を 2 段に分ける。

1. `SP-1` 着手直後: `E-1`/`E-2` 実装 → **ADR 0001 未確認事項 #1（shadcn × Next.js 16 互換性）を確認・確定**
2. ADR 確定後: shadcn MCP の `add` 運用（stack_fit の条件付き）/ secondsky `tailwind-v4-shadcn` 等の外部資産を検討する場合はここで初めて着手

これにより、私が round 1 で「`SP-2` 着手時」としていた `tailwind-v4-shadcn` の導入判断は **`SP-1` 内の ADR 確定後**に前倒しではなく「確定を待ってから」に条件を明確化する（時期そのものは `SP-1`〜`SP-2` の範囲で変わらないが、**順序がゲート付きになる**点が変更点）。

## 4. 統合実行順序表（今やること / SP-n 到達時にやること・最終版）

risk_ops の段階導入案（`agentRules:false` 先行・MCP バージョンピン・生成物レビュー・Cloudflare permissions ドリフト解消）と、stack_fit/conflict_guard の個別条件、budget_meta の予算制約（Hot 層 +16% 超過中は常駐ルール追加不可）を統合する。

| タイミング | やること | 出典・条件 |
|---|---|---|
| **今すぐ（`SP-13`/`SP-1` 着手前）** | ① Cloudflare Documentation MCP を維持（既に稼働中・認証不要） ② 既存の Cloudflare MCP `permissions` ドリフトを解消（`cloudflare-infrastructure.md` §7.4 の読み取り 4 ツール限定を `.claude/settings.json` に反映）— conflict_guard/risk_ops 指摘。**新規 MCP を足す前にこの既存負債を消す** | 予算: Hot 層追加ではなく既存ファイル修正のみのため制約に抵触しない |
| **`SP-13`（骨格確立。分割しない場合は `SP-1` 冒頭）** | ① `next.config.ts` に `agentRules: false` を **`next dev` を一度も有効化させないまま最初のコミットから含める**（risk_ops）② 自作「`@opennextjs/cloudflare` デプロイスキル」を作成 ③ `git diff CLAUDE.md` を `next dev` 初回実行の前後で確認する運用を Done Criteria に明記（risk_ops） | `SD-1`（プレビュー URL）の前提。ここが崩れると Hot 層全体の規律が壊れる（研究 §4 最大リスク） |
| **`SP-1`（残作業・ADR 確定まで）** | ① `E-2`/`E-5`〜`E-8` 実装 ② **ADR 0001 未確認事項 #1 を確定**（conflict_guard 指摘のゲート） | shadcn 関連の外部/MCP 資産導入は次段へ持ち越す |
| **`SP-1`（ADR 確定後）** | ① shadcn MCP を `add` 専用で追加（`init` は CLI 先行・stack_fit 条件） ② next-devtools-mcp を追加（バージョンピン・risk_ops） | Playwright MCP は **単体先行しない**（争点D 併用時の二重登録リスク・conflict_guard/stack_fit 一致） |
| **`SP-4`（回帰を検知できる＝品質ゲート実装。budget_meta の `SP-3` 表記は誤りとして訂正済み）** | ① Playwright 導入と同時に Playwright Agents（`init-agents`）実行 → 生成物（`.claude/agents/`・`.mcp.json`）を `check_agent_definitions.py` + `git diff` でレビューしてからコミット（risk_ops/conflict_guard） ② これにより Playwright MCP は Agents 経由で一本化（単体 MCP は追加しない） ③ `tdd-guard` を実機検証の上で導入（Vitest 4 実追随を確認できたときのみ・stack_fit 保留を支持）。役割分担は「`tdd-guard`=予防（PreToolUse）／`self_review_check.py`=事後の最終防衛線」と明文化してから入れる（conflict_guard 条件） ④ 自作「TDD/テスト運用スキル」作成 ⑤ `tools/check_a11y.py`（機械ゲート・skill 化しない）を作成し axe-core を接続 | `testing-strategy.md` の一次情報が根拠。`tdd-guard` は `DISABLE_NON_ESSENTIAL_MODEL_CALLS` の明示例外化が必要（risk_ops） |
| **`SP-10`（誰でも操作できる）** | masuP9 の技法を `tools/check_a11y.py` に反映・E2E へ移植 | それ以前は a11y 専用資産不要（`SP-2`/`SP-9` は既存トークン/E2E の目視確認で足りる） |
| **恒久的に導入しない** | axe MCP（有料・A-6）／`vercel`・`cloudflare/skills`・wshobson・VoltAgent・Community-Access の一括導入／budget_meta 案の architecture-check skill・6 分割 skill | 死蔵確定（既存資産と重複 or SSOT 二重化 or 対象スプリント不在） |

## 総括

争点Fの最終線引きは **「今日入れるのは permissions ドリフト修正のみ」「`SP-13` で `agentRules:false` + デプロイスキル」「ADR 確定後の `SP-1` で shadcn/next-devtools MCP」「`SP-4` で Playwright 系一式 + `tdd-guard` + テスト運用スキル + a11y ゲート」「`SP-10` で a11y 技法移植」**の 5 段階に収束する。自作スキルは 2 本、機械ゲートスクリプトは 1 本のみで足り、budget_meta が示した 6〜10 本は死蔵資産を含む過大見積もりである。

## ラウンド 3

### `lead` — 合意
<sub>2026-08-19T08:35:30+09:00</sub>

# lead: 合意点と対立点の整理

## 0. lead による事実確定（争点の前提が割れていたため実測した）

`budget_meta` と `conflict_guard` が `description` 予算の解釈で対立したため、lead が実測して決着させた:

```
既存 19 スキルの description 合計: 14,240 B / 6,394 文字
```

`research §3.4` が引く上限は `SLASH_COMMAND_TOOL_CHAR_BUDGET`（**文字数**基準）の既定 15,000。したがって現在の消費は **6,394 / 15,000 ≒ 43%** であり、**`budget_meta` の「上限にほぼ到達・追加 0 本」は単位取り違えによる誤り**。`conflict_guard` の反証が正しい。

🔴 **ただし結論は変わらない**: 予算は **拘束制約ではなくなった** が、代わりに **YAGNI（死蔵を作らない・`sprint_value`）** と **SSOT 二重化の回避（`conflict_guard`）** が拘束制約になる。「予算に余裕があるから足してよい」という読み替えはしない。

## 1. 全員が一致した点（議論を経ても崩れなかった）

1. **一括導入は全て不採用**。`vercel` plugin（33 skills）/ `cloudflare/skills` / `secondsky`（142 skills）/ `wshobson`（202 agents）/ `VoltAgent` / `Community-Access`（37 agents）を丸ごと入れる案は、死蔵・トリガー衝突・未読外部コードへの実行権限付与の 3 つの独立した理由で棄却された。
2. **今すぐ `.mcp.json` に足せる MCP は 0 本**。Cloudflare Documentation MCP は既に稼働中で維持のみ。判定条件は `risk_ops` が確定させた **「認証不要 AND 接続先が今すでに存在する」の AND 条件**（認証要否だけで切ると `next-devtools-mcp` / shadcn MCP を「今すぐ足せる」と誤読する）。`package.json` が 0 行の現状では両者とも接続先が物理的に存在しない。
3. **`@opennextjs/cloudflare` は公式・コミュニティともに完全な空白**。ここだけは自作するしかない（代替が存在しない）。
4. **axe MCP は恒久不採用**（有料サブスク = `A-6` を発生させるのに、既決定の無料 `@axe-core/playwright` で代替できる）。
5. **`CLAUDE.md` 破壊リスク（`next dev` の `AGENTS.md` / `CLAUDE.md` 自動 upsert）が最大の技術リスク**。

## 2. 議論で決着した対立点

| 対立 | 決着 |
|---|---|
| `tdd-guard` を採るか（`budget_meta` = 不採用 vs 他 4 名 = 条件付き採用） | **4 対 1 で条件付き採用**。`risk_ops` の反論が決定的: 「スキル化」に置き換えると `self_review_check.py` と同じ **事後**層を重ねるだけで、`tdd-guard` を採る理由（**事前**ブロック）そのものが消える。`budget_meta` の懸念（モデル呼び出しコスト）は **不採用の理由ではなく運用条件**（明示例外を切る）に過ぎない |
| Playwright MCP を単体で足すか（`conflict_guard` の二重登録懸念） | **単体では足さない**。`SP-4` の Playwright Agents（`init-agents`）が生成する `.mcp.json` に一本化する（`stack_fit` が断定・`conflict_guard` 同意） |
| Playwright Agents の導入条件（`stack_fit` = 生成物レビューで足りる vs `conflict_guard` = 不十分） | **`conflict_guard` の強化条件を採用**。目視レビューでは tools フィルタの silent removal を見逃すため `check_agent_definitions.py` が存在する。**機械ゲート PASS を導入完了条件に義務化**する |
| MCP 追加のタイミング（`budget_meta` = `SP-3` vs `sprint_value` = `SP-4`） | **`sprint_value` が正**。`SP-3` のゴールは「一覧 → 詳細 → 一覧の往復」で品質ゲートを含まない。`testing-strategy.md` が Playwright 導入を `SP-4` と明記している |
| 自作スキルの本数（`budget_meta` = 6〜10 本 vs `sprint_value` = 2 本） | **`sprint_value` の 2 本 + 機械ゲート 1 本**。`budget_meta` 案の architecture-check skill は `architecture-rules.md` + `check_architecture_boundaries.py` と完全重複、6 分割 skill は `SD-4` の読み順で既に SSOT として読まれる知識の二重化 |
| 段階導入すれば衝突リスクも下がるか | **下がらない**（`conflict_guard`）。段階導入が防ぐのは死蔵であって、`SP-11` 到達時点の累積衝突量は変わらない。**各 SP 到達時の導入ゲートに衝突レビューを別途組み込む**必要がある |
| `agentRules: false` の先行設定だけで足りるか | **足りない**（`risk_ops` が自説を撤回・格下げ）。Cloudflare 向けスキャフォールド経路が「config 生成 → dev 未実行」の順序を保証するか未確認。**3 点セット全部必須** |

## 3. `risk_ops` だけが持っていた事実（他 4 名の前提を覆した）

**このクラウドコンテナには `bwrap` が存在せず、sandbox の network allowlist が無効**（実地検証）。他 4 名は暗黙に「sandbox が防波堤として機能する」と前提していた。

影響: クラウドでの実効防御は **`permissions.allow/deny` の ACL と PreToolUse フックの 2 層のみ**。したがって:

- 🔴 **`cloudflare-infrastructure.md` §7.4（読み取り 4 ツール限定）が `.claude/settings.json` に未反映というドリフトは「直したほうがいい」ではなく「新規 MCP を 1 本でも足す前の必須前提」に格上げ**される。ドキュメントで読み取り専用と決めただけでは実効力がない
- 外部資産の一括導入は「予算超過だから不採用」ではなく **「未読の外部コードに無制限の実行権限を事前付与するから不採用」**。予算論だけを根拠にすると「予算が空けば少数なら一括導入してよい」という誤読を招く

## 4. 外部資産を採ってよい条件（`conflict_guard` が 1 文に統合・`risk_ops` が補強）

> **外部資産（skill / plugin / MCP）は、① SKILL.md 全文を読み、② 本リポジトリの確定ドキュメント（ADR / `architecture-rules.md` / `testing-strategy.md` / `cloudflare-infrastructure.md` §7.4 等）と矛盾する記述がないことを個別に確認し、③ パッケージ一括ではなく単体ファイル単位で取り込み、④ 取得先バージョンをピン留めする、の 4 条件をすべて満たした場合に限り採用する。**

4 条件が揃わない限り「採らない」を既定にする。

### `lead` — 判定
<sub>2026-08-19T08:37:03+09:00</sub>

{
  "decisions": [
    {
      "issue": "A: 公式 MCP をどれだけ .mcp.json に足すか",
      "conclusion": "今すぐ足すのは 0 本。判定条件は『認証不要 AND 接続先が今すでに存在する』の AND 条件。Cloudflare Documentation MCP は既に稼働中で維持のみ。next-devtools-mcp と shadcn MCP は骨格確立スプリント（SP-13 が起票されていればそちら、なければ SP-1）で ADR 0001 未確認事項 #1 が確定した後にバージョンピンして追加。Playwright MCP は単体では追加せず SP-4 の Playwright Agents 生成分に一本化。新規 MCP を足す PR には Cloudflare MCP の permissions ドリフト解消を同一 PR に含めることを必須とする。context7 とは役割が重複しない（context7 は静的なライブラリドキュメント、next-devtools-mcp は実行中 dev サーバーの動的エラー取得）",
      "rejected": "budget_meta の『MCP 2 本を今/SP-3 で確定』案。接続先が物理的に存在せず死蔵になる（package.json が 0 行）。SP-3 のゴールは一覧→詳細の往復で品質ゲートを含まない"
    },
    {
      "issue": "B: 外部スキル/プラグインを採るか自作するか",
      "conclusion": "自作を主とし、外部資産は 4 条件（全文レビュー / 確定ドキュメントとの矛盾確認 / 単体ファイル単位で取り込み / バージョンピン）を全て満たす場合に限り採用する。自作は 2 本のスキル + 1 本の機械ゲートスクリプトに限定する（YAGNI: スプリントで 2 回以上使われるものだけ）。description 予算は実測 6,394/15,000 文字（43%）で拘束制約ではないが、余裕を理由に増やさない",
      "rejected": "vercel plugin（33 skills）/ cloudflare/skills / secondsky（142 skills）/ wshobson（202 agents）/ VoltAgent / Community-Access（37 agents）の一括導入。死蔵・トリガー衝突・未読外部コードへの実行権限付与の 3 つの独立した理由で棄却。budget_meta の自作 6〜10 本案も architecture-check の重複と 6 分割 skill の SSOT 二重化を含むため棄却"
    },
    {
      "issue": "C: tdd-guard を入れて SD-2 を機械強制するか",
      "conclusion": "SP-4 で条件付き採用（4 対 1 で決着）。条件は 4 点の AND: ① tdd-guard=予防（PreToolUse）/ self_review_check.py=事後の最終防衛線 という権威分離を明文化する ② DISABLE_NON_ESSENTIAL_MODEL_CALLS=1 の明示例外として切る ③ バージョンピン ④ Vitest 4 での実機動作検証。SP-1〜SP-3 は testing-strategy.md がテスト基盤未整備の緩和を認めているため hard block させない",
      "rejected": "budget_meta の『不採用・スキル化で代替』案。スキル化すると self_review_check.py と同じ事後層を重ねるだけで、tdd-guard を採る理由（事前ブロック）そのものが消える。モデル呼び出しコストは不採用理由ではなく運用条件"
    },
    {
      "issue": "D: Playwright Agents を採るか",
      "conclusion": "SP-4 で採用。Playwright 本体 v1.56+ 同梱のためバージョンドリフトしない唯一の構造を持つ。導入完了条件に機械ゲートを義務化する: ① python3 tools/check_agent_definitions.py が PASS ② .mcp.json が上書きでなく差分追記になっていることを git diff で確認。単体 playwright-mcp は追加しない（二重登録回避）",
      "rejected": "stack_fit の『生成物を目視レビューしてから commit すれば足りる』案。tools フィルタの silent removal は目視では見逃すため check_agent_definitions.py が存在する。目視で足りるならこのツールは不要になってしまう"
    },
    {
      "issue": "E: アクセシビリティを外部資産で埋めるか自作機械ゲートか",
      "conclusion": "自作機械ゲート tools/check_a11y.py を SP-4 で作り @axe-core/playwright を接続する。SP-10 で masuP9 の技法（フォーカスインジケーター・320px リフロー・テキスト間隔・ターゲットサイズ）を参考実装として移植する（資産としては導入しない）。品質ゲート（Lighthouse Accessibility 100 / NFR-26 / AC-10）は自作ゲートで担保する",
      "rejected": "axe MCP（Deque 公式）は有料サブスク必須で A-6 を発生させるのに無料の @axe-core/playwright で代替可能なため恒久不採用。Community-Access の 37 agents 一括導入は skill-audit が検出するトリガー衝突を誘発するため不採用"
    },
    {
      "issue": "F: 導入タイミング",
      "conclusion": "5 段階に収束。① 今すぐ: Cloudflare MCP permissions ドリフト解消のみ ② 骨格確立スプリント（SP-13 or SP-1 冒頭）: agentRules:false の先行設定 + CLAUDE.md 破壊検知の機械ゲート + next dev 初回前後の git diff 確認（3 点セット必須）と @opennextjs/cloudflare デプロイスキル作成 ③ SP-1 の ADR 0001 確定後: shadcn MCP（add 専用）と next-devtools-mcp ④ SP-4: Playwright Agents + tdd-guard + テスト運用スキル + check_a11y.py ⑤ SP-10: a11y 技法の移植。段階導入は死蔵を防ぐが衝突は防がないため、各 SP 到達時の導入ゲートに衝突レビューを別途組み込む",
      "rejected": "今まとめて導入する案。アプリコードが 0 行で接続先・検証対象が存在せず、大半が死蔵確定になる"
    }
  ],
  "adopt": [
    {
      "asset": "Cloudflare MCP の permissions アローリスト反映（既存ドリフトの解消）",
      "form": "machine-gate",
      "artifacts": [".claude/settings.json（改修）"],
      "command": "permissions.allow に mcp__Cloudflare_Developer_Platform__{search_cloudflare_documentation,workers_list,workers_get_worker,workers_get_worker_code} を追加し、書き込み系を permissions.deny に明示する",
      "sprint": "今",
      "why": "bwrap 不在で sandbox の network allowlist が無効なため、cloudflare-infrastructure.md §7.4 の読み取り限定方針は permissions に書かない限り実効力がない。新規 MCP 追加の必須前提"
    },
    {
      "asset": "next.config.ts の agentRules:false + CLAUDE.md upsert 検知の機械ゲート + next dev 初回前後の git diff 確認",
      "form": "machine-gate",
      "artifacts": ["next.config.ts（新規・骨格構築時）", "tools/check_claude_md_integrity.py（新規）", "SP-1 の Done Criteria（改修）"],
      "command": "—",
      "sprint": "骨格確立スプリント（SP-13 が起票されていればそちら、なければ SP-1 冒頭）",
      "why": "Next.js 16.3 の next dev が CLAUDE.md を @AGENTS.md で upsert するリスクは本リポジトリの規律全体を壊す最大の技術リスク。3 点セット全部が必須"
    },
    {
      "asset": "自作スキル: @opennextjs/cloudflare デプロイ手順",
      "form": "own-skill",
      "artifacts": [".claude/skills/opennext-cloudflare-deploy/SKILL.md（新規）"],
      "command": "—",
      "sprint": "骨格確立スプリント",
      "why": "公式・コミュニティともに完全な空白で代替が存在しない。SP-13 初期構築・SP-1 の Cloudflare 作業・SP-4 の GitHub Actions 移行の 3 回使われる（YAGNI 充足）"
    },
    {
      "asset": "shadcn MCP（add 専用運用）",
      "form": "mcp",
      "artifacts": [".mcp.json（改修）"],
      "command": "npx shadcn@latest mcp（バージョンピン。init は CLI で -b radix を明示して先行実行し、MCP は add のみに使う）",
      "sprint": "SP-1（ADR 0001 未確認事項 #1 の確定後）",
      "why": "shadcn 公式。init を MCP に任せると ADR 0001 の -b radix を踏み抜くため add 専用に限定する"
    },
    {
      "asset": "next-devtools-mcp",
      "form": "mcp",
      "artifacts": [".mcp.json（改修）"],
      "command": "npx -y next-devtools-mcp@<pinned-version>",
      "sprint": "SP-1（ADR 0001 確定後・dev サーバーが立つようになってから）",
      "why": "next build を回さずに型・コンパイルエラーを取れる。Next.js 公式で 16 系専用。context7 と役割が重複しない"
    },
    {
      "asset": "Playwright Agents（planner / generator / healer）",
      "form": "subagent",
      "artifacts": [".claude/agents/（生成物・要レビュー）", ".mcp.json（差分追記であることを確認）"],
      "command": "npx playwright init-agents --loop=claude",
      "sprint": "SP-4",
      "why": "Playwright 本体同梱でバージョンドリフトしない唯一の構造。導入完了条件は check_agent_definitions.py の PASS と .mcp.json の差分確認"
    },
    {
      "asset": "tdd-guard",
      "form": "plugin",
      "artifacts": [".claude/settings.json（hooks・permissions）", "docs/rules/sprint-development-rules.md（権威分離の明文化）"],
      "command": "/plugin marketplace add nizos/tdd-guard → /plugin install tdd-guard@tdd-guard（バージョンピン）",
      "sprint": "SP-4",
      "why": "SD-2（TDD 主体）を事前ブロックで機械強制できる唯一の実物。Vitest レポーター実装済み。4 条件を満たしたときのみ"
    },
    {
      "asset": "自作スキル: TDD / テスト運用（Vitest 4 + RTL + MSW 2 + Playwright の本スタック規約）",
      "form": "own-skill",
      "artifacts": [".claude/skills/stack-testing/SKILL.md（新規）"],
      "command": "—",
      "sprint": "SP-4",
      "why": "SP-4〜SP-11 の全実装スプリントで参照される（8 回・YAGNI 充足）。testing-strategy.md の What/Why を How に落とす層が不在"
    },
    {
      "asset": "自作機械ゲート: tools/check_a11y.py（@axe-core/playwright 接続）",
      "form": "machine-gate",
      "artifacts": ["tools/check_a11y.py（新規）"],
      "command": "—",
      "sprint": "SP-4（作成）→ SP-10（masuP9 技法の移植）",
      "why": "Lighthouse Accessibility 100 / NFR-26 / AC-10 の品質ゲートを無料で担保する。skill 形態は不要"
    },
    {
      "asset": "citypaul/.dotfiles の react-testing SKILL.md / masuP9 の a11y 監査技法",
      "form": "doc-reference",
      "artifacts": ["docs/01_research/tooling/20260818-claude-code-assets-research.md（参照記録）"],
      "command": "—",
      "sprint": "SP-4 / SP-10 の自作時に参照",
      "why": "配布形態がない（dotfiles）または粒度が合わないため、技法だけを自作資産に取り込む"
    }
  ],
  "defer": [],
  "reject": [
    { "asset": "vercel plugin（33 skills + 3 agents）の一括導入", "why": "33 skills のうちスプリントで使うのは数本で残りは死蔵。単体取り込みできないパッケージ形態のため 4 条件の③を満たせない" },
    { "asset": "cloudflare/skills の一括導入", "why": "@opennextjs/cloudflare / Next.js への言及がなく本プロジェクトの肝をカバーしない。wrangler 手順は cloudflare-infrastructure.md 585 行が既に SSOT" },
    { "asset": "secondsky/claude-skills（142 skills）", "why": "一括導入は未読外部コードへの実行権限付与。個別 skill も tailwind-v4-shadcn が ADR 0001 の -b radix を踏み抜くリスクを持つ" },
    { "asset": "wshobson/agents（202 agents / 181 skills）", "why": "nextjs-app-router-patterns が Next.js 14+ 表記で 2 世代遅れ。architecture-patterns は architecture-rules.md が明示的に採らないとした集約ルート・リポジトリパターンを持ち込む" },
    { "asset": "VoltAgent/awesome-claude-code-subagents", "why": "実ファイルが Next.js 14+ / React 18+ 前提。star 24k はメンテ品質の指標にならない" },
    { "asset": "Community-Access/accessibility-agents（37 agents）", "why": "必要なのは Web 11 agents だけで過剰同梱。skill-audit が検出するトリガー衝突を誘発する" },
    { "asset": "axe MCP（Deque 公式）", "why": "有料サブスク必須で A-6 を発生させるのに、無料の @axe-core/playwright で品質ゲートを満たせる" },
    { "asset": "Playwright MCP の単体追加", "why": "SP-4 の Playwright Agents が .mcp.json を生成するため二重登録になる" },
    { "asset": "anthropics/skills の webapp-testing", "why": "Python 版 Playwright で本プロジェクトの TS/Vitest/Playwright ラインと別系統になる" },
    { "asset": "公式 code-review / pr-review-toolkit plugin", "why": "自前 code-review スキル（FAIR Layer 1）と責務が完全重複する" },
    { "asset": "nathankim0/clean-architecture-skills", "why": "総コミット 2 で更新見込みなし。architecture-rules.md + check_architecture_boundaries.py で三重に確定済み" },
    { "asset": "自作 architecture-check skill（budget_meta 案）", "why": "architecture-rules.md + check_architecture_boundaries.py と完全重複" },
    { "asset": "自作の UI / state / API / form / cache / error-handling 6 分割 skill（budget_meta 案）", "why": "SD-4 の着手時読み順で既に SSOT として読まれる知識の二重化。SSOT を割る" },
    { "asset": "rohitg00 / davepoon / hesreallyhim / JanSzewczyk / airowe / dykyi-roman", "why": "リサーチ §3.5 に理由を記録済み（陳腐化・索引・★1・下位互換・PHP 専用）" }
  ],
  "tasks": [
    { "id": "T-1", "title": "Cloudflare MCP の読み取り限定ポリシーを .claude/settings.json の permissions に反映する（allow 4 ツール / deny 書き込み系）", "actor": "claude", "depends_on": [], "sp": "sp:2" },
    { "id": "T-2", "title": "リサーチ文書 §5 に採否の決定を記録し、段階導入計画を SSOT 化する", "actor": "claude", "depends_on": [], "sp": "sp:2" },
    { "id": "T-3", "title": "骨格確立スプリントの Done Criteria に CLAUDE.md 破壊対策 3 点セットを追加し、tools/check_claude_md_integrity.py を作る", "actor": "claude", "depends_on": ["T-2"], "sp": "sp:3" },
    { "id": "T-4", "title": "自作スキル opennext-cloudflare-deploy を作成する", "actor": "claude", "depends_on": ["T-2"], "sp": "sp:3" },
    { "id": "T-5", "title": "SP-1 の ADR 0001 確定後に shadcn MCP（add 専用）と next-devtools-mcp を .mcp.json へバージョンピンで追加する", "actor": "claude", "depends_on": ["T-1"], "sp": "sp:2" },
    { "id": "T-6", "title": "SP-4 で Playwright Agents を導入し check_agent_definitions.py PASS と .mcp.json 差分確認を完了条件にする", "actor": "claude", "depends_on": ["T-2"], "sp": "sp:3" },
    { "id": "T-7", "title": "SP-4 で tdd-guard を 4 条件（権威分離明文化・環境変数の明示例外・バージョンピン・Vitest 4 実機検証）付きで導入する", "actor": "claude", "depends_on": ["T-6"], "sp": "sp:5" },
    { "id": "T-8", "title": "SP-4 で自作スキル stack-testing と tools/check_a11y.py を作成する", "actor": "claude", "depends_on": ["T-2"], "sp": "sp:5" },
    { "id": "T-9", "title": "SP-10 で masuP9 の a11y 監査技法を check_a11y.py と E2E に移植する", "actor": "claude", "depends_on": ["T-8"], "sp": "sp:3" }
  ],
  "critical": [
    "Next.js 16.3 の next dev が CLAUDE.md を @AGENTS.md で upsert するリスク。agentRules:false の先行設定だけでは不十分で、Cloudflare 向けスキャフォールド経路が『config 生成 → dev 未実行』の順序を保証するか未確認。機械ゲートと初回前後の git diff 確認を含む 3 点セット全部が必須",
    "このクラウドコンテナには bwrap が存在せず sandbox の network allowlist が無効。実効防御は permissions ACL と PreToolUse フックの 2 層のみで、cloudflare-infrastructure.md §7.4 の読み取り限定方針が permissions に未反映のまま新規 MCP を足すのは危険",
    "@opennextjs/cloudflare は公式・コミュニティともに完全な空白で、本プロジェクトの肝（Next.js on Workers）を支える外部資産が存在しない。自作しない限り誰も助けてくれない領域である",
    "段階導入は死蔵を防ぐが累積トリガー衝突は防がない。各 SP 到達時の導入ゲートに衝突レビューを別途組み込まないと SP-11 時点で skill-audit が検出する状態になる"
  ],
  "open_questions": []
}
