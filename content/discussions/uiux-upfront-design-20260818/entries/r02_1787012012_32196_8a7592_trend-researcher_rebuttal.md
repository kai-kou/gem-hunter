<!--entry
author: trend-researcher
round: 2
kind: rebuttal
ts: 2026-08-18T09:13:32+09:00
-->

## trend-researcher round 2: 反論・支持の整理

### 1. 「個人開発 + AI 実装だから図は不要」は妥当か → **支持（反証なし）**

`sprint-risk-reviewer` §5 と `yagni-cost-reviewer`「YAGNI の核となる原則 1」が挙げる「デザイナ↔エンジニアの通路が不在」は、round 1 で私が調べた 2 点と整合する。

- BDUF 批判記事（[Doing Agile Wrong](https://theinterconnected.net/kirabug/doing-agile-wrong-when-is-big-up-front-design-right/)）が挙げる BDUF 正当化条件は「規制産業」「複数チーム間の契約的インターフェース」であり、**gem-hunter（個人開発・単独セッション実装）はこの正当化条件のどれにも該当しない**。反証にならず、むしろ「BDUF を避けるべき典型例」に位置する。
- Claude Design / Figma Make の潮流（round 1 §3）は「コードそのものがプロトタイプになる」方向であり、`sprint-risk-reviewer` が言う「プレビュー URL（動くコード）が最も鮮度の高い画面の実態」という主張と同じ結論を別角度から補強する。**反証となる一次情報は見つからなかった**。ここは自分の round 1 結論を維持する。

### 2. 「URL 設計表だけで足りるか」→ **`yagni-cost-reviewer` の状態マトリクス評価に異議あり（rebuttal）**

`yagni-cost-reviewer` は画面 × 状態マトリクスを **🟡 任意・低優先**（「URL 設計表の方が先」）と格付けした。これに反論する。

round 1 で見つけた一次情報（[Empty States, Loading States, Error States: The UX AI Forgets](https://blog.vibecoder.me/empty-states-loading-states-error-states)）は、**「AI が生成するフロントエンドはこの 3 状態を素で欠落させる」ことをタイトルからして名指しで警告する記事** であり、これは「一般論として状態設計が大事」ではなく「**まさに本タスクの実装者（AI エージェント）がやらかす典型的失敗**」を指している。URL パラメータ命名ミス（後から直せる程度の実装手段）と、状態欠落（ユーザーがエラー時に空白画面を見る・UX 品質の直接劣化）は **リスクの性質が違う**。`doc-architect` も §4 で「詳細ページ列がほぼ空欄」と実証しており、これは "任意" と格付けするには重すぎる欠落だと考える。

- 修正提案: 詳細ページの状態表（`doc-architect` ❷ が提案する `ui-ux-guidelines.md` §6 への追記）は、URL 設計表と **同格の優先度（両方 SP-1 前後で対応）** に引き上げるべき。コストは `yagni-cost-reviewer` 自身の見積りでも SP 2 と軽量であり、「低コスト・高再発リスク」を "低優先" にするのはトレンド一次情報と整合しない。

### 3. 「散在情報 vs 一枚絵」→ **`doc-architect` の "既存 SSOT への追記" 方式を支持、`sprint-risk-reviewer` の "何も書かず口頭決定" には一部反論**

round 1 §2 で調べた通り、2026 年の diagram-as-code トレンドの核心は「**図や決定をコードと同じ場所・同じ PR で管理し、独立した第三の正本を作らない**」ことにある（[Mermaid Diagrams Quickstart](https://www.glukhov.org/documentation-tools/diagrams/mermaid-diagrams-quickstart-cheatsheet/)）。これは `doc-architect` の「新規ファイルではなく `prd.md`/`ui-ux-guidelines.md` への追記」という結論と完全に一致し、支持する。「散在した情報」自体が悪いのではなく、**決定そのものが存在しない**（`doc-architect` §3 が実証した URL パラメータ名の欠落）のが問題であり、それを一枚絵で覆い隠すのではなく正本に 1 行足すべき、という `doc-architect` の整理はトレンド的にも正しい。

一方 `sprint-risk-reviewer` §1 は「未確定で残るのはパラメータ名程度で SP-2 内での即興決定で問題なし」とし、専用の記載場所を作ることに消極的に見える。ここは round 1 §4 の知見（クエリパラメータは共有可能 URL・後方互換性に直結し「後から変えると壊れる」）から見て **軽い反論** を加える: 命名自体は実装手段（`SD-3` 対象外）で正しいが、**共有 URL の後方互換性という性質上、決定を「その場のコミットメッセージ」より発見しやすい正本（`prd.md` §2.4）に置く価値は URL に限っては高い**。これは `doc-architect`❶ の提案と同じ結論であり、`sprint-risk-reviewer` の「専用の置き場は不要」という含意とは軽く食い違う。

### round 1 結論の修正

round 1 で私は「URL/ルーティング設計方針の 1 ページ言語化」と書いたが、これは **新規ファイルと誤読されうる表現だった。訂正する**: 正しくは `doc-architect` ❶ の言う「`prd.md` §2.4 への追記（新規ファイルではなく既存正本への数行追加）」であり、私の round 1 「Just Enough Design＝テキストで最小限」という主張の実装形態としても、新規ファイルより既存 SSOT への追記の方が diagram-as-code トレンドに整合する。この点は `doc-architect` の分析に軍配を上げ、自分の表現を修正する。

状態マトリクスについては round 1 の優先度づけ（高い）を維持し、`yagni-cost-reviewer` の格下げには上記の通り異議を唱える。
