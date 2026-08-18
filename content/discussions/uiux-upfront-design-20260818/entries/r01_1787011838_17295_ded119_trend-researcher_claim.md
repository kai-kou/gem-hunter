<!--entry
author: trend-researcher
round: 1
kind: claim
ts: 2026-08-18T09:10:37+09:00
-->

## trend-researcher: 2026 年時点のトレンド調査結果

### 1. アジャイル/スプリントにおける「どこまで先に設計するか」の定説

- **BDUF（Big Design Up Front）は依然アンチパターン扱いが定説**。Wikipedia/DevIQ とも「変更コストが高い」「プロトタイピングなしに問題領域を予見できない」を根拠に批判を維持している。[Big design up front - Wikipedia](https://en.wikipedia.org/wiki/Big_Design_Up_Front) / [Big Design Up Front (BDUF): A Software Development Antipattern – DevIQ](https://deviq.com/antipatterns/big-design-up-front/)
- 一方で「Doing Agile Wrong: When is Big Up-Front Design Right?」のように **BDUF が正当化される条件**（規制産業・複数チーム間の契約的インターフェース・後戻りコストが極端に高い基盤部分）を論じる記事も 2026 年時点で存在し、「BDUF=常に悪」ではなく **文脈依存** という立場が主流。[Doing Agile Wrong – The Interconnected](https://theinterconnected.net/kirabug/doing-agile-wrong-when-is-big-up-front-design-right/)
- **Dual-track agile が 2026 年の主流モデル**: リサーチ/デザインと実装を並行 2 トラックで回し、デザイナーは実装の 1〜2 スプリント先を設計する（全部を先に固めない）。[UX Design and Agile: Dual-Track Done Right in 2026 | CorsoUX](https://courseux.com/ux-design-and-agile/)
- **Lean UX の位置づけ**: 成果物（ドキュメント）を作ることより「学習速度」を優先し、軽量 MVP で仮説検証する思想。Agile UX（ワイヤーフレーム等の構造化成果物を作る）と対比される。[What is Lean UX? — updated 2026 | IxDF](https://ixdf.org/literature/topics/lean-ux) / [9 UX Design Frameworks Every Product Team Should Know (2026)](https://www.uxpin.com/studio/blog/design-frameworks/)
- **結論**: 「Big Design Up Front はしない」が定説の骨格は変わっていないが、「Just Enough Design（次の 1〜2 スプリント分だけ先行）」が推奨形。個人開発・単独スプリント運用（本リポジトリ）では複数トラックの並行体制自体が過剰。

### 2. 画面遷移図/ユーザーフロー図/IA 図の現在の位置づけ

- **静的画像の遷移図は陳腐化しやすいと明言される一方、"diagram as code" として形を変えて残っている**。Mermaid のようにテキストで書きリポジトリにコミットし、PR でレビューし、コードと同じパイプラインで更新する運用が 2026 年の標準的推奨。[Mermaid Diagrams Quickstart and Cheatsheet for Developers](https://www.glukhov.org/documentation-tools/diagrams/mermaid-diagrams-quickstart-cheatsheet/) / [10 Copy-Paste Mermaid Diagram Examples for 2026 — GitDoc](https://gitdoc.ai/resources/mermaid-diagram-examples)
- ドリフト対策の要点は「**図をコードと同じ PR で更新する**」「**スキーマ/エンドポイント定義の隣に置く**」の 2 点に集約されている（本リポジトリの `artifact-diagramming` スキルが Mermaid をネイティブ対応しているのは追い風）。
- **含意**: 「先に一枚絵の画面遷移図を作って終わり」は推奨されない。作るなら Next.js の `app/` ディレクトリ構造＝ルーティング定義そのものを正本にし、Mermaid は補助的な可視化として **必要になった時点で・コードと同じ場所で** 生成する方が長持ちする。

### 3. AI コーディング時代の変化（最重要論点）

- **Spec-Driven Development（SDD）が 2026 年の主要潮流**: 「コードではなく実行可能な仕様（spec）を正本にする」考え方。vibe coding の失敗モード（もっともらしいが意図からドリフトするコード・API 幻覚）への直接的な反動として 2025 年に台頭し、2026 年半ばには Claude Code・Cursor・GitHub Spec Kit・AWS Kiro 等主要ツールが軒並み対応。[Spec-Driven Development with AI Coding Agents (2026)](https://zeroshot.ghost.io/spec-driven-development-with-ai-coding-agents/) / [Spec-Driven Development (SDD): The Definitive 2026 Guide](https://www.thebcms.com/blog/spec-driven-development/)
- **重要な非対称性**: SDD が求める「spec」は**振る舞い・受け入れ条件を記述したテキスト仕様**であり、**ビジュアルなワイヤーフレーム画像ではない**。AI エージェントへの入力として有効なのは「テキスト仕様」（本リポジトリの `prd.md` / `user-story-map.md` の AC）であって、静的ワイヤーフレーム画像はむしろ補助情報止まり。
- **Claude Design / Figma Make / v0 の位置づけ**: 「コードが最初のデザイン成果物になる」動きが加速。Claude Design はコードベースを読んでデザインシステムを抽出し、そのまま HTML として動く出力を返す＝**プロトタイプ＝実装コードの一種**になりつつある。[Claude Design (Anthropic): The Complete 2026 Guide](https://agence-scroll.com/en/blog/claude-design-anthropic-2026-guide) / [Claude Design vs Figma Make: Which AI Prototyping Tool Is Better?](https://alloy.app/library/figma-make-vs-claude-design)
- **AI エージェント実装前提での含意**: 人間チーム前提のセオリー（「エンジニアに渡す前に非エンジニアが読めるワイヤーフレームを用意する」）は、実装者が AI エージェント（このセッション自身）になる場合は動機が薄れる。AI エージェントは Figma のような画像よりテキスト仕様（AC・状態一覧・URL 設計）を直接消費できるため、**「絵を描く」コストを「テキストで仕様化する」コストに置き換えるほうが投資対効果が高い**。
- ただし「Vibe Coder Blog」の指摘（後述 §5）のとおり、**AI が生成した UI は状態設計を素で漏らす傾向がある** ため、"仕様が要らない" わけではなく "絵ではなくテキスト・チェックリストで仕様化すべき" という方向にシフトしている。

### 4. URL/ルーティング設計を先に固定することの扱い

- Next.js App Router では **ディレクトリ構造＝URL 構造** が直接対応するため、ルート設計は「別図に描く」のではなく **`app/` の設計そのものが正本**になる。route group の命名規約（`(marketing)` のような無意味な名前を避け `(dashboard)` 等の意味のある名前にする）が実務上の要点。[App Router Directory Design: Next.js Project Structure Patterns](https://dev.to/pipipi-dev/app-router-directory-design-nextjs-project-structure-patterns-31eo)
- **共有可能な URL（クエリパラメータでの状態保持）は事前に方針だけ決めておく価値がある**: リロード耐性・共有可能性のため、フィルタ/検索状態を URL クエリに载せるかどうかは早期に決めるべき設計判断（後から変えると壊れるため）。[mastering state in next js app router with url query parameters](https://medium.com/@roman_j/mastering-state-in-next-js-app-router-with-url-query-parameters-a-practical-guide-03939921d09c)
- **結論**: 「URL を図に描く」必要はないが、「検索クエリ・フィルタ条件を URL に持たせるか」という **1〜2 個の設計方針の言語化** は、画面遷移図よりずっと軽いコストで同じ目的（後戻りコスト回避）を達成できる。

### 5. 状態設計（loading/empty/error/初期）の一覧化

- 2026 年の実務記事群は一貫して **「Empty / Loading / Error / Success の 4 状態は全画面で洗い出すべき」** と明言。特に **AI 生成フロントエンドはこの 4 状態のうち初期状態以外を素で欠落させがち**、という直接的な指摘がある: 「Empty States, Loading States, Error States: The UX AI Forgets」。[Empty States Loading States Error States The UX AI Forgets](https://blog.vibecoder.me/empty-states-loading-states-error-states)
- ローディングは 2026 年時点でスピナーではなく **skeleton screen** が推奨（体感待ち時間を約 30% 短縮・レイアウトシフト防止）。[Nobody Designs the Empty State](https://medium.com/design-bootcamp/nobody-designs-the-empty-state-thats-exactly-why-your-app-feels-unfinished-da3396570de0)
- **含意**: これは gem-hunter（GitHub 検索アプリ）に直接刺さる。検索結果 0 件・API レート制限エラー・初回訪問時の空状態は、画面遷移図より **「各画面の状態一覧表（テキストのチェックリスト）」** の形で先に洗い出すほうが実装バグを防ぎやすく、AI エージェント（実装者）が読み落としにくい。

---

### trend-researcher の暫定結論

**先に作る価値がある（ただし絵ではなくテキスト/コードとして）**:
1. **状態一覧チェックリスト**（各画面 × loading/empty/error/success を表で洗い出す）— AI 実装エージェントが素で漏らす領域への直接対策。コストは低く効果が高い。
2. **URL/ルーティング設計方針の 1 ページ言語化**（`app/` 構造そのものを正本にし、フィルタ・検索語をクエリに持たせるかだけ明文化）。Next.js App Router では図よりディレクトリ構造が正本になるため、別途遷移図を描く投資対効果は低い。
3. 複雑なフロー（認証・多段階ウィザード等）が発生するスプリントに限り、**その場で Mermaid をコードと同じ PR に書く**（先に一括で全画面分を用意しない）。

**先に作る価値が低い/無駄になりやすいもの**:
- 全画面を網羅した静的ワイヤーフレーム集・画面遷移図（BDUF 的投資、AI エージェント実装では消費されない、スプリントで頻繁に変わる個人開発では陳腐化が確実）
- 実装前の高忠実度モックアップ（Claude Design 的にコード＝プロトタイプになる時代性を踏まえると、「動くコード」を先に出したほうが安い）

**根拠の要約**: 2026 年の潮流は「Big Design Up Front からの脱却」自体は変わらず継続しているが、AI コーディングエージェント時代に入り **「先に描くべきもの」がビジュアル成果物からテキスト仕様（spec-driven development・状態一覧・受け入れ条件）へシフトした** という点が新しい論点。gem-hunter は個人開発・単独セッションの実装なので、複数人チーム前提のドキュメント（画面遷移図・IA 図）よりも、実装エージェント自身が消費しやすい形式（AC・状態表・ルーティング方針）に投資する方が期待値が高い。
