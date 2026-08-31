# 技術スタック向け Claude Code 資産リサーチ（スキル・サブエージェント・MCP）

- **調査日**: 2026-08-18
- **対象 Issue**: #49
- **目的**: スプリント開発（`SP-13` → `SP-1`〜`SP-11`）で、本リポジトリの技術スタックに効く Claude Code 資産（Agent Skills / Subagents / Plugin / MCP）を公式・非公式を問わず洗い出し、導入可否の判断材料を揃える
- **注意**: 本ドキュメントは **リサーチ結果（事実）** であり、採否の決定ではない。採否は専門チーム議論（`content/discussions/`）の verdict と §5 に記録する

## 0. 対象技術スタック（設計ドキュメントで確定済み）

| 領域 | 確定内容 | 正本 |
|---|---|---|
| フレームワーク | Next.js 16 App Router + React 19 + TypeScript | `minimum-requirements.md` |
| UI | Tailwind CSS v4（CSS-first）+ shadcn/ui（`-b radix` 明示） | `ui-ux-guidelines.md` / ADR 0001 |
| テスト | Vitest 4 + RTL + MSW 2 / Playwright + `@axe-core/playwright` | `testing-strategy.md` |
| インフラ | Cloudflare Workers + `@opennextjs/cloudflare` + wrangler | `cloudflare-infrastructure.md`（`D-16` / `D-17`） |
| 設計 | クリーンアーキテクチャ + DDD + zod | `application-architecture.md` |
| 外部 API | GitHub API（GitHub App 認証） | ADR 0003 |

---

## 1. 既存資産の棚卸し（自リポジトリ）

### 1.1 決定的な事実: 技術スタック系の資産はゼロ

`.claude/skills/`（19 件）・`.claude/agents/`（1 件）・`.claude/commands/`（2 件）を全件分類した結果:

| 分類 | 件数 | 内訳 |
|---|---|---|
| **P**（プロセス系: PR / Issue / レビュー / 振り返り / 衛生） | 13 | `code-review` / `pr-review-watcher` / `project-manager` / `retrospective` / `sprint-cycle-router` ほか |
| **M**（メタ系: スキル・ルール自体の保守） | 6 | `apply-base` / `skill-audit` / `skill-creator` / `claude-code-spec-sync` ほか |
| **T**（技術スタック系: コードの書き方） | **0** | — |

機械検証: `grep -rilE 'next\.js|nextjs|vitest|playwright|tailwind|shadcn|cloudflare|wrangler|a11y|axe' .claude/skills .claude/agents .claude/commands` → **ヒット 0 件**。

> ⚠️ スコープを `.claude/` 全体に広げると `settings.json`（sandbox の `allowedDomains` に `api.cloudflare.com`）と `hooks/session-start.sh` の 2 件がヒットするが、いずれも **資産定義ではなく環境設定** なので本判定の対象外。

さらに **アプリコードが 1 行も存在しない**（`src/` / `app/` / `package.json` / `.github/workflows/` すべて未作成。`SP-1` 未着手）。`check_architecture_boundaries.py` も現状は全スキップで空振りしている。

### 1.2 ドキュメントが既にカバーしている範囲（＝外部資産が重複しやすい領域）

| ドキュメント | 行数 | カバー済み |
|---|---|---|
| `application-architecture.md` | 209 | 層と依存規則・層別 import 可否表・確定ディレクトリ構造・ポート契約・DI・腐敗防止層・エラーモデル |
| `testing-strategy.md` | 148 | 道具の採否・層別テスト対応表・テストダブル優先順位（フェイク > MSW > `vi.mock`）・二重ループ TDD・禁止事項 |
| `ui-ux-guidelines.md` | 307 | Tailwind v4 CSS-first / shadcn `-b radix` / デザイントークン 9 種 / 4 状態表現 / WCAG 2.2 実装 |
| `cloudflare-infrastructure.md` | 585 | 物理構成・ランタイム採否・`wrangler` CLI 一次運用の全コマンド・3 軸キャッシュ設計・MCP アローリスト |
| `architecture-rules.md` | 85 | 配置判定フロー・`ARCH-1`〜`ARCH-7`・DDD 3 点・TDD 最低ライン |

**結論**: 「何を採用するか（What）」「なぜそうするか（Why）」「守るべき境界（Constraints）」は **高密度に確定済み**。空白は **「決定に沿ってどう手を動かすか（How）」の手順化** と **「書いた後の検証」** の側にある。

### 1.3 コンテキスト予算の制約（導入形態を決める決定要因）

> 🔴 **Hot 層予算の実測値は本節に転記しない。正本は [`docs/rules/token-optimization-rules.md`](../../rules/token-optimization-rules.md) の増減ログであり、現在値は `python3 tools/check_hot_budget.py` で都度取り直す。**
> 本節はかつて実測スナップショット（2026-08-18 時点で 91,600 B・ベース基準 79,072 B に対し約 +16%）を表で持っていたが、増減ログの最新エントリと乖離したまま固定化していた。#55 の調査で **その二重管理そのものが乖離の原因** と判明したため固定値を撤去した（乖離の実体は、その後の通常運用で増減ログ側へ既に反映済みだった）。

- **技術知識を常駐ルール（`.claude/rules/`）として足すのは予算上不可**
- **スキル / サブエージェント形態なら常駐するのは `description` のみ**（数百 B）で予算影響はほぼゼロ
- ただしスキル `description` の総量にも可視化バジェット（後述 §3.3）があり、無制限ではない

### 1.4 既存の機械ゲート（`tools/`）

`check_architecture_boundaries.py`（`ARCH-1`〜`ARCH-7`）/ `self_review_check.py`（TDD コミット順序・縦切り 3 層・`C-5`）/ `scan_dangerous_patterns.py` / `check_cjk_markdown.py` / `check_datetime_tz.py` / `check_rules_sync.sh` / `check_agent_definitions.py` / `lessons_guard.py` ほか。

⚠️ **フロントエンド品質ゲート（ESLint / TypeScript strict / axe / Lighthouse 相当）は 1 つも存在しない**。`SP-1`〜`SP-4` で必ず必要になる。

### 1.5 MCP の現状

- `.mcp.json`（リポジトリ管理）: `context7` / `github` の 2 サーバー
- セッション側で追加供給: `Cloudflare Developer Platform` / `Slack` / `Google Drive` / `Claude Code Remote`
- ⚠️ **ドリフト検出**: `cloudflare-infrastructure.md` §7.4 が Cloudflare MCP の「読み取り 4 ツールのみ許可・書き込み系は明示禁止」と定めているが、`.claude/settings.json` の `permissions` に反映されていない（別 Issue 相当）

---

## 2. 公式・ベンダー公式の資産

### 2.1 Anthropic 公式

| 名称 | 種別 | 概要 | 導入 |
|---|---|---|---|
| [anthropics/claude-plugins-official](https://github.com/anthropics/claude-plugins-official) | marketplace | **286 プラグイン**。初回起動時に自動登録される | — |
| `frontend-design` | skill / plugin | 「AI っぽくない」プロダクション品質の UI 生成 | `/plugin install frontend-design@claude-plugins-official` |
| [`webapp-testing`](https://github.com/anthropics/skills/tree/main/skills/webapp-testing) | skill | **Python 版 Playwright** で webapp を操作・スクショ・ログ取得 | `/plugin marketplace add anthropics/skills`（Apache-2.0） |
| `code-review` / `pr-review-toolkit` | plugin | 観点別レビュー agent 群（type design 観点を含む） | 公式マーケット |
| `security-guidance` | plugin（hooks） | 編集時パターン警告 + Stop 時 LLM diff レビュー。XSS/SSRF/injection など 25+ クラス | 公式マーケット（v2.0.7） |
| `typescript-lsp` | plugin（LSP） | `typescript-language-server` を接続し型情報・定義ジャンプを提供 | 公式マーケット（v1.0.0） |

### 2.2 Vercel / Next.js 公式（本スタックへの当たりが最も強い）

| 名称 | 種別 | 概要 | 導入 |
|---|---|---|---|
| [Next.js バンドル docs + `AGENTS.md` 自動生成](https://nextjs.org/docs/app/guides/ai-agents) | 仕組み | `node_modules/next/dist/docs/` にバージョン一致の docs を同梱。**16.3 以降は `next dev` が `AGENTS.md` と `CLAUDE.md` を自動生成 / upsert** | `next dev` を 1 回実行。`next.config.ts` の `agentRules: false` で無効化 |
| [`next-devtools-mcp`](https://nextjs.org/docs/app/guides/mcp) | MCP | dev サーバーの `/_next/mcp` に接続。`get_errors` / `get_logs` / `get_routes` / `get_compilation_issues` など。**`next build` を回さずに型・コンパイルエラーを取れる** | `.mcp.json` に `npx -y next-devtools-mcp@<固定バージョン>` |
| [Next.js 公式 Skills](https://github.com/vercel/next.js/tree/canary/skills) | skill | `next-dev-loop`（編集 → 実行時検証ループ）/ `next-cache-components-*` / `next-partial-prefetching-adoption` | `npx skills add vercel/next.js --skill next-dev-loop` |
| [`vercel` plugin](https://github.com/vercel/vercel-plugin) | plugin | **33 skills + 3 agents + MCP**。`nextjs` / `react-best-practices` / **`shadcn`** / `turbopack` / `next-upgrade` / `cdn-caching` ほか | `/plugin install vercel@claude-plugins-official` |
| [`agent-browser`](https://github.com/vercel-labs/agent-browser) | CLI | DOM / console / network / Web Vitals / React ツリーを構造化テキスト出力。`next-dev-loop` が内部利用 | `next-dev-loop` 経由 |

### 2.3 Cloudflare 公式

| 名称 | 種別 | 概要 | 導入 |
|---|---|---|---|
| [cloudflare/skills](https://github.com/cloudflare/skills) | plugin（skill 束） | `cloudflare` / **`wrangler`** / `durable-objects` / `agents-sdk` / **`workers-best-practices`** / `web-perf` ほか。★2,669・Apache-2.0 | `/plugin marketplace add cloudflare/skills` |
| [Cloudflare Remote MCP 群（16 種）](https://github.com/cloudflare/mcp-server-cloudflare) | MCP | Documentation / Workers Bindings / Workers Builds / Observability / Browser Run ほか。**Documentation MCP のみ認証不要** | リモート URL 登録（本セッションでは既に稼働） |

🔴 **重要な欠落**: **`@opennextjs/cloudflare` 向けの公式資産は存在しない**。Cloudflare 公式 skills にも Next.js / OpenNext への言及がなく、OpenNext 公式 docs にも llms.txt / AGENTS.md / MCP / skill の記載がない。**本プロジェクトの肝（Next.js on Workers）はどの公式資産もカバーしていない**。

### 2.4 テスト・アクセシビリティ

| 名称 | 種別 | 概要 | 導入 |
|---|---|---|---|
| [microsoft/playwright-mcp](https://github.com/microsoft/playwright-mcp) | MCP | **アクセシビリティスナップショット主体**（スクショではなく構造化データ）。ネットワーク傍受・モック・trace・アサーション。headless / Docker / CI 対応 | `claude mcp add playwright npx @playwright/mcp@latest` |
| **Playwright Agents**（planner / generator / healer） | subagent + MCP | Playwright v1.56+ 同梱。仕様 → テスト計画 → TS テスト生成 → 失敗テストの自動診断・修復。**`.claude/agents/` に 3 ファイル + `.mcp.json` を生成** | `npx playwright init-agents --loop=claude` |
| [shadcn MCP](https://ui.shadcn.com/docs/mcp) | MCP | レジストリの component を browse / search / 自然言語 install。"Built by shadcn at Vercel" | `.mcp.json` に `npx shadcn@<固定バージョン> mcp` |
| [chrome-devtools-mcp](https://github.com/ChromeDevTools/chrome-devtools-mcp) | MCP | 実 Chrome の performance trace / network / source map 付き console | 公式マーケット |
| [axe MCP（Deque 公式）](https://github.com/dequelabs/axe-mcp-server-public) | MCP | `analyze` / `remediate`。⚠️ **axe DevTools 有料サブスク必須**（A-6 相当） | Docker + API キー |

### 2.5 公式に存在しなかったもの

- **Vitest 公式の成熟した MCP は事実上不在**（`vitest-community/mcp` は commit 3 件・★8 の WIP）
- **Testing Library / MSW / zod の公式 skill・MCP は不在**
- **`@opennextjs/cloudflare` / `@cloudflare/vitest-pool-workers` 向け公式資産は不在**
- 公式マーケット 286 件走査でも **shadcn 単体 plugin・Tailwind 公式 plugin・Vitest plugin・axe plugin は不在**（shadcn は `vercel` plugin 内の skill としてのみ存在）

---

## 3. 非公式・コミュニティの資産

### 3.1 方法論・ハーネス系（バージョン陳腐化しない）

| 名称 | 規模 | 概要 |
|---|---|---|
| [obra/superpowers](https://github.com/obra/superpowers) | ★273,667 / MIT / 2026-08-13 | `test-driven-development`（RED → GREEN → REFACTOR 強制）/ `systematic-debugging` / `verification-before-completion` / `subagent-driven-development` ほか。**Anthropic 公式マーケット収載済み**・フレームワーク非依存 |
| [nizos/tdd-guard](https://github.com/nizos/tdd-guard) | ★2,304 / MIT / 2026-08-16 | **PreToolUse hook で Write/Edit を実際にブロック**。テストなしの実装・過剰実装を拒否。**Vitest レポーター実装済み**。⚠️ 検証に追加のモデル呼び出しコストが発生 |

### 3.2 スタック特化系

| 名称 | 規模 | 本スタック関連の中身 |
|---|---|---|
| [secondsky/claude-skills](https://github.com/secondsky/claude-skills) | ★207 / MIT / 2026-08-06 | **142 skills**。Cloudflare 21 / Frontend 26（**`tailwind-v4-shadcn`**）/ Testing 4（**`vitest-testing`** / **`playwright-testing`**）/ `architecture-patterns`。**skill 単位で個別導入可** |
| [wshobson/agents](https://github.com/wshobson/agents) | ★38,899 / MIT / 2026-08-18 | **92 plugins / 202 agents / 181 skills**。`tdd-orchestrator` / `accessibility-expert` / `architecture-patterns`（Clean / Hexagonal / DDD）/ `wcag-audit-patterns`（WCAG 2.2）/ `tailwind-design-system`。⚠️ `nextjs-app-router-patterns` は **"Next.js 14+"** 表記 |
| [Community-Access/accessibility-agents](https://github.com/Community-Access/accessibility-agents) | ★396 / MIT / 2026-08-18 | Web チーム 11 agents（`aria-specialist` / `contrast-master` / `keyboard-navigator` ほか）+ **Playwright MCP による実行時 a11y 検証** + axe-core + WCAG 2.2 AA。⚠️ 全 37 agent 同梱で過剰 |
| [masuP9/a11y-specialist-skills](https://github.com/masuP9/a11y-specialist-skills) | ★56 / MIT / 2026-08-18 | 4 skill と小粒。axe-core + 独自 Playwright スクリプト（フォーカスインジケーター・320px リフロー・テキスト間隔・ターゲットサイズ）。**日本の a11y 専門家（WAIC 準拠）** |
| [gocallum/nextjs16-agent-skills](https://github.com/gocallum/nextjs16-agent-skills) | ★22 / MIT / 2026-07-16 | **Next.js 16 / shadcn を明示ターゲットする希少例**。テスト・a11y・アーキテクチャは対象外 |
| [laguagu/claude-code-nextjs-skills](https://github.com/laguagu/claude-code-nextjs-skills) | ★60 / 2026-08-18 | **Next.js 16** + AI SDK 7 + pgvector + bun。AI / pgvector 前提が強くズレる |
| [citypaul/.dotfiles](https://github.com/citypaul/.dotfiles/blob/main/claude/.claude/skills/react-testing/SKILL.md) | 配布形態なし | **Vitest Browser Mode + `vitest-browser-react` を第一選択**・MSW は `setupWorker`・`getByRole` 優先。**SKILL.md の書き方の参考** |

### 3.3 バージョン追随の総括（厳しめ評価）

- **Next.js 16 に明示追随しているのは 2 件のみ**（laguagu ★60 / gocallum ★22）。**大手コレクションはすべて Next.js 14〜15 世代のまま**
- **Tailwind v4 追随は複数あり**（secondsky / wshobson / JanSzewczyk）
- **Vitest 4 を明示するものは発見できず**（tdd-guard は `vitest@latest` 指定で実質追随）
- **`@opennextjs/cloudflare` を扱うコミュニティ skill はゼロ**
- **MSW 2 / zod を主題にした skill も発見できず**
- 🔴 **star 数はメンテ品質の指標にならない**: VoltAgent は ★24,442 ながら本文が Next.js 14+ / React 18+ のまま

### 3.4 リスク

| 種別 | 内容 |
|---|---|
| **トリガー衝突** | wshobson（202 agents）・VoltAgent（158）・rohitg00（135）は一括導入すると `description` 衝突が確実。本リポジトリは既に 20 以上の自作スキルを持ち `skill-audit` が衝突を検出対象にしている |
| **可視化バジェット** | secondsky の README 自身が「**15,000 文字の skill 可視化バジェット制限**」に当たると明記し `SLASH_COMMAND_TOOL_CHAR_BUDGET=30000` を回避策として案内。大量導入はコンテキストを実際に食う |
| **サードパーティ hook** | tdd-guard は **PreToolUse でツール実行に介入** する外部コードが常駐する。導入するならバージョンピン + 差分レビュー必須 |
| **取得経路** | `npx skills add <github-url>` 系は実行時に外部リポジトリを取得する。`curl \| bash` ワンライナー install は `security-posture-controls.md` / `sandbox-rules.md` と要突き合わせ |
| **ライセンス** | 大半は MIT / Apache-2.0。⚠️ `hesreallyhim/awesome-claude-code` は **NOASSERTION**（索引参照に留める） |

### 3.5 「入れる価値がない」と判断できたもの（再検討で消耗しないための記録）

| 資産 | 理由 |
|---|---|
| VoltAgent/awesome-claude-code-subagents | 実ファイルが Next.js 14+ / React 18+ 前提で 2 世代遅れ |
| rohitg00/awesome-claude-code-toolkit | 大量同梱型 + open issue 288。見合うスタック特化資産がない |
| davepoon/buildwithclaude | 独自資産が薄い。検索はサイトを見れば足りる |
| hesreallyhim/awesome-claude-code | 索引であり導入対象ではない + ライセンス NOASSERTION |
| dykyi-roman/awesome-claude-code | PHP 専用（DDD 目当てで引っかかるが非該当） |
| JanSzewczyk/claude-plugins | スタック一致度は高いが ★1 の実質個人設定。中身のみ参考 |
| airowe/claude-a11y-skill | masuP9 / Community-Access の下位互換（★14・停滞） |
| shadcn 系のサードパーティ skill 全般 | shadcn/ui が公式 Skills と公式 MCP を提供しているため採る理由がない |
| nathankim0/clean-architecture-skills（導入として） | 総コミット 2 で更新見込みなし。自リポジトリの `architecture-rules.md` + `check_architecture_boundaries.py` があるため外部依存を増やさず内容だけ取り込む方が合理的 |

---

## 4. 導入判断に効く制約（横断）

| 制約 | 内容 |
|---|---|
| **クラウドコンテナ動作** | `next-devtools-mcp` / shadcn MCP / Playwright MCP は **npx でローカルプロセス起動**（Playwright は `npx playwright install --with-deps chromium` が別途必要）。Cloudflare の 16 MCP は **リモート URL 型** で制約を受けにくい。`agent-browser` / `chrome-devtools-mcp` は実ブラウザ前提でハードルが最も高い |
| **認証・課金（A-6）** | axe MCP は有料サブスク + API キー。Vercel plugin の MCP 部分は Vercel トークン、Cloudflare Bindings / Builds / Observability MCP は OAuth または API トークン。**Cloudflare Documentation MCP のみ認証不要** |
| 🔴 **`AGENTS.md` 自動生成の副作用** | Next.js 16.3 の `next dev` は `AGENTS.md` と `CLAUDE.md` を **勝手に生成 / upsert する**。本リポジトリの `CLAUDE.md` は精緻に設計済みのため、**最初の `next dev` 実行で `CLAUDE.md` が `@AGENTS.md` 1 行で上書きされないことを必ず確認する**（不安なら `agentRules: false`）。**導入前に検証すべき最大のリスク** |
| **Hot 層予算** | 既に基準比 +16%。**常駐ルールとしての追加は不可**。スキル / サブエージェント形態のみ現実的（§1.3） |
| 🔴 **`@latest` のままコミットしない** | 上表の導入コマンドは、公式ドキュメントが `@latest` で示しているものを **固定バージョン表記に書き換えてある**。`npx` 起動型 MCP は起動のたびにレジストリから取得するため、`@latest` のまま `.mcp.json` にコミットすると、パッケージ乗っ取り・タイポスクワッティング時に **セッション起動のたび任意コードが走る**。導入時にその時点の安定版番号へ確定してからコミットする |
| ⚠️ **`workers_get_worker_code` の残存リスク** | `scriptName` を自由に受け取るため、同一 Cloudflare アカウント内の **無関係な Worker のソースまで取得できる**（読み取り専用＝安全とは言い切れない）。Cloudflare 側で API トークンを本プロジェクトの Worker に絞る最小権限設定（`A-6`）で緩和する |

---

## 5. 採否の決定（専門チーム議論の verdict）

> 決定の根拠・対立と決着の全文は [`content/discussions/stack-assets-20260818/whiteboard.md`](../../../content/discussions/stack-assets-20260818/whiteboard.md)（5 レンズ × 2 ラウンドの敵対的相互レビュー）。本節はその結論だけを記録する。

### 5.0 判断の土台（議論で確定した 3 つの原則）

| 原則 | 内容 |
|---|---|
| **予算は拘束制約ではない** | 既存 19 スキルの `description` は実測 **14,240 B / 6,394 文字**。上限 15,000 は `SLASH_COMMAND_TOOL_CHAR_BUDGET`（**文字数** 基準）なので消費は約 43%。当初の「上限に到達しているから足せない」という見立ては単位取り違えで撤回した。**代わりに YAGNI（死蔵を作らない）と SSOT 二重化の回避が拘束制約になる** |
| **今すぐ足せる MCP の判定条件** | 「認証不要」だけでは足りず、**「認証不要 **かつ** 接続先が今すでに存在する」の AND 条件**。`package.json` が 0 行の現状では `next-devtools-mcp`（`next dev` のエンドポイント）も shadcn MCP（`components.json`）も接続先が物理的に存在しない |
| **外部資産を採ってよい 4 条件** | ① SKILL.md 全文を読む ② 本リポジトリの確定ドキュメント（ADR / `architecture-rules.md` / `testing-strategy.md` / `cloudflare-infrastructure.md` §7.4）と矛盾しないことを個別に確認 ③ パッケージ一括ではなく **単体ファイル単位** で取り込む ④ 取得先バージョンをピン留めする。**4 条件が揃わない限り「採らない」を既定にする** |

🔴 **サンドボックスがクラウドで効かないことが判断を変えた**: 詳細は [`sandbox-rules.md`](../../rules/sandbox-rules.md)「クラウド実行環境ではサンドボックスは動作しない」（SSOT・#383）。クラウドでの実効防御は **① コンテナ隔離 ② `permissions.allow/deny` の ACL ③ PreToolUse フック** の 3 層で、`allowedDomains` は含まれない。したがって MCP の利用範囲は「ドキュメントで読み取り専用と決めた」だけでは実効力がなく、**`permissions` に書いて初めて効く**。

### 5.1 採用するもの（段階導入）

| # | 資産 | 形態 | 導入タイミング | 主な条件 |
|---|---|---|---|---|
| 1 | **Cloudflare MCP の読み取り限定を `permissions` に反映** | 機械ゲート | **今すぐ**（本 PR で実施済み） | `cloudflare-infrastructure.md` §7.4 の読み取り 4 ツールを `allow`、D1 / KV / R2 / Hyperdrive の書き込み系を `deny` に明示 |
| 2 | **`CLAUDE.md` 破壊対策 3 点セット** | 機械ゲート | 骨格確立スプリント | `next.config.ts` の `agentRules: false` 先行設定 + `CLAUDE.md` の upsert 痕跡を検知する機械ゲート + `next dev` 初回実行前後の `git diff CLAUDE.md`。**3 点すべて必須**（1 点で足りるという当初案は撤回） |
| 3 | **自作スキル: `@opennextjs/cloudflare` デプロイ手順** | 自作スキル | 骨格確立スプリント | 公式・コミュニティともに完全な空白で代替が存在しない。3 スプリントで使われる |
| 4 | **shadcn MCP（`add` 専用）** | MCP | `SP-1`（ADR 0001 未確認事項 #1 の確定後） | `init` は CLI で `-b radix` を明示して先行実行する。MCP に `init` を任せると ADR 0001 を踏み抜く |
| 5 | **`next-devtools-mcp`** | MCP | `SP-1`（同上） | バージョンピン。`next build` を回さずに型・コンパイルエラーを取れる。context7（静的ドキュメント）と役割が重複しない |
| 6 | **Playwright Agents**（planner / generator / healer） | サブエージェント | `SP-4` | 完了条件に **機械ゲートを義務化**: `check_agent_definitions.py` の PASS と `.mcp.json` が差分追記であることの `git diff` 確認。目視レビューでは tools フィルタの silent removal を見逃す |
| 7 | **`tdd-guard`** | plugin | `SP-4` | 4 条件の AND: ① 権威分離の明文化（`tdd-guard` = 予防 / `self_review_check.py` = 事後の最終防衛線）② `DISABLE_NON_ESSENTIAL_MODEL_CALLS=1` の明示例外化 ③ バージョンピン ④ Vitest 4 での実機検証 |
| 8 | **自作スキル: TDD / テスト運用** | 自作スキル | `SP-4` | `SP-4`〜`SP-11` の全実装スプリントで参照される。`testing-strategy.md` の What / Why を How に落とす層が不在 |
| 9 | **自作機械ゲート `tools/check_a11y.py`** | 機械ゲート | `SP-4`（作成）→ `SP-10`（技法移植） | `@axe-core/playwright` を接続。Lighthouse Accessibility 100 / `NFR-26` / `AC-10` を無料で担保する |
| 10 | citypaul の `react-testing` SKILL.md / masuP9 の a11y 監査技法 | ドキュメント参照 | `SP-4` / `SP-10` の自作時 | 配布形態がない、または粒度が合わないため **技法だけを自作資産に取り込む** |

**自作するのはスキル 2 本 + 機械ゲート 2 本のみ**（YAGNI: スプリントで 2 回以上使われるものだけに絞った結果）。

### 5.2 採用しないもの（理由 1 行・再検討で消耗しないための記録）

| 資産 | 採らない理由 |
|---|---|
| `vercel` plugin（33 skills + 3 agents）の一括導入 | 使うのは数本で残りは死蔵。単体取り込みできず 4 条件の ③ を満たせない |
| `cloudflare/skills` の一括導入 | `@opennextjs/cloudflare` / Next.js への言及がなく本プロジェクトの肝をカバーしない。`wrangler` 手順は `cloudflare-infrastructure.md` 585 行が既に SSOT |
| `secondsky/claude-skills`（142 skills） | 一括導入は未読外部コードへの実行権限付与。`tailwind-v4-shadcn` も ADR 0001 の `-b radix` を踏み抜くリスクを持つ |
| `wshobson/agents`（202 agents / 181 skills） | `nextjs-app-router-patterns` が Next.js 14+ 表記で 2 世代遅れ。`architecture-patterns` は `architecture-rules.md` が明示的に採らないとした集約ルート・リポジトリパターンを持ち込む |
| `VoltAgent/awesome-claude-code-subagents` | 実ファイルが Next.js 14+ / React 18+ 前提。★24k はメンテ品質の指標にならない |
| `Community-Access/accessibility-agents`（37 agents） | 必要なのは Web 11 agents だけで過剰同梱。`skill-audit` が検出するトリガー衝突を誘発する |
| axe MCP（Deque 公式） | 有料サブスク必須で `A-6` を発生させるのに、無料の `@axe-core/playwright` で品質ゲートを満たせる |
| Playwright MCP の **単体追加** | `SP-4` の Playwright Agents が `.mcp.json` を生成するため二重登録になる |
| `anthropics/skills` の `webapp-testing` | Python 版 Playwright で本プロジェクトの TS / Vitest / Playwright ラインと別系統になる |
| 公式 `code-review` / `pr-review-toolkit` plugin | 自前 `code-review` スキル（FAIR Layer 1）と責務が完全重複する |
| `nathankim0/clean-architecture-skills` | 総コミット 2 で更新見込みなし。`architecture-rules.md` + `check_architecture_boundaries.py` で三重に確定済み |
| 自作 architecture-check スキル案 | `architecture-rules.md` + `check_architecture_boundaries.py` と完全重複 |
| 自作の UI / state / API / form / cache / error-handling の 6 分割スキル案 | `SD-4` の着手時読み順で既に SSOT として読まれる知識の二重化。**SSOT を割る** |
| `rohitg00` / `davepoon` / `hesreallyhim` / `JanSzewczyk` / `airowe` / `dykyi-roman` | §3.5 に理由を記録済み（陳腐化・索引・★1・下位互換・PHP 専用） |

### 5.3 議論を経ても残った真の問題（critical）

1. 🔴 **`next dev` による `CLAUDE.md` 上書きリスク**: `agentRules: false` の先行設定だけでは不十分。Cloudflare 向けスキャフォールド経路が「config 生成 → dev 未実行」の順序を保証するかが **未確認**。骨格確立スプリントの Done Criteria に実地確認を含める
2. 🔴 **sandbox が無効な環境での実効防御は 2 層のみ**: `permissions` ACL と PreToolUse フック。新規 MCP を足す PR は必ず許可範囲を同一 PR で明示する
3. 🔴 **`@opennextjs/cloudflare` は外部資産が完全にゼロ**: 本プロジェクトの肝を支えるものが存在しない。自作しない限り誰も助けてくれない領域である
4. 🔴 **段階導入は死蔵を防ぐが累積トリガー衝突は防がない**: `SP-11` 到達時点の同時存在数はビッグバン導入と変わらない。**各 SP 到達時の導入ゲートに衝突レビューを別途組み込む**

### 5.4 実行タスク

`T-1`（本 PR で完了）以降は Issue に分解して段階導入する。

| ID | タスク | タイミング |
|---|---|---|
| `T-1` | Cloudflare MCP の読み取り限定を `permissions` に反映 | ✅ 本 PR |
| `T-2` | 本節（採否の決定）の記録 | ✅ 本 PR |
| `T-3` | `CLAUDE.md` 破壊対策 3 点セットと検知ゲート | 骨格確立スプリント（#50） |
| `T-4` | 自作スキル `opennext-cloudflare-deploy` | 骨格確立スプリント（#50） |
| `T-5` | shadcn MCP + `next-devtools-mcp` の追加 | `SP-1`（ADR 確定後・#51） |
| `T-6` | Playwright Agents 導入 + 機械ゲート義務化 | `SP-4`（#52） |
| `T-7` | `tdd-guard` の 4 条件付き導入 | `SP-4`（#52） |
| `T-8` | 自作スキル `stack-testing` + `tools/check_a11y.py` | `SP-4`（#52） |
| `T-9` | masuP9 の a11y 技法を移植 | `SP-10`（#53） |
