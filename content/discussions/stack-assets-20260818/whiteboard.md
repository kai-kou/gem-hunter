<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: 技術スタック向け Claude Code 資産（スキル・エージェント・MCP）の採否を決める

- 議題ID: `stack-assets-20260818`
- 論点: リサーチ結果の一次情報は docs/01_research/tooling/20260818-claude-code-assets-research.md（2026-08-18 取得）にある。必ず全文を読んでから発言すること。前提事実: (1) 自リポジトリの .claude/skills 19 件・agents 1 件・commands 2 件は全てプロセス系/メタ系で、技術スタック系は 0 件（grep ヒット 0）。(2) アプリコードは 1 行も存在しない（src/ app/ package.json 未作成・SP-13/SP-1 未着手）。(3) Hot 層（.claude/rules/ 常駐 14 ファイル）は 91,600 B で基準比 +16% 超過のため、常駐ルールとしての知識追加は不可。スキル/サブエージェント形態なら description 分のみで予算影響はほぼゼロ。(4) 設計ドキュメントは What/Why/Constraints を高密度に確定済み（application-architecture.md 209 行・testing-strategy.md 148 行・ui-ux-guidelines.md 307 行・cloudflare-infrastructure.md 585 行）。空白は How（手順化）と書いた後の検証。(5) フロントエンド品質ゲート（ESLint / TS strict / axe / Lighthouse 相当）は tools/ に 1 つも無い。(6) @opennextjs/cloudflare 向けの公式資産は Cloudflare にも Vercel にも存在しない（本プロジェクトの肝が空白）。(7) Next.js 16.3 の next dev は AGENTS.md と CLAUDE.md を自動生成/upsert する副作用がある。争点は少なくとも次の 6 つ: A) 公式 MCP（next-devtools-mcp / shadcn MCP / Playwright MCP / Cloudflare Documentation MCP）をどれだけ .mcp.json に足すか。足すと context7 と役割が重複しないか。クラウドコンテナで npx 起動型が実際に動くか。B) 外部スキル/プラグイン（vercel plugin 33 skills / cloudflare skills / secondsky 個別 skill / superpowers / wshobson 個別 plugin）を採るか、それとも自リポジトリの確定済みドキュメントを SSOT として自作スキルに落とすか。外部資産は ADR 0001（shadcn -b radix）・testing-strategy.md の意図的抑制（vitest-pool-workers を入れない・vi.mock は最終手段）・cloudflare-infrastructure.md §7.4（MCP 書き込み禁止）と正面衝突しないか。C) tdd-guard（PreToolUse hook で実装をブロック）を入れて SD-2 を機械強制するか。既存 19 hooks・self_review_check.py の TDD コミット順序検査と二重にならないか。追加モデル呼び出しコストとサードパーティ hook 常駐のリスクをどう見るか。D) Playwright Agents（npx playwright init-agents が .claude/agents/ に 3 ファイル + .mcp.json を生成）を採るか。既存 .claude/agents/ と check_agent_definitions.py に干渉しないか。E) アクセシビリティ（AC-10 / NFR-26 / Lighthouse Accessibility 100 が品質ゲート）を外部資産（Community-Access 11 agents / masuP9 4 skills）で埋めるか、自作の機械ゲート（@axe-core/playwright を CI で回す）で埋めるか。F) 導入タイミング: SP-13/SP-1 着手前の今入れるか、アプリコードが出てから入れるか（今入れると空振りの死蔵スキルになり skill-audit が検出する）。評価軸の優先順位は CP-5（ミッション貢献）> D-9（基盤優先）> 保守コスト。star 数はメンテ品質の指標にならないことが実測で確認されている（VoltAgent ★24k が Next.js 14 前提のまま）。
- 参加者: `stack_fit`, `conflict_guard`, `risk_ops`, `sprint_value`, `budget_meta`
- 投稿数: 0
- 更新: 2026-08-19T08:27:07+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

_（まだ投稿がありません）_
