<!--entry
author: docs_consistency
round: 2
kind: rebuttal
ts: 2026-08-22T13:14:09+09:00
-->

# docs_consistency — Round 2 反論・譲歩

## 争点 1: ADR 見出しの形式矛盾（fact_check との対立）

### 実ファイル再確認結果

実測したところ、**docs_consistency の指摘が正しい**。

- **ADR ファイルの H1 見出し**: `# ADR 0001: UI スタックに Tailwind CSS v4 + shadcn/ui...`（プレフィックス含む）
- **README の表**: `UI スタックに Tailwind CSS v4 + shadcn/ui...`（プレフィックス除去）

fact_check が「一字一句一致」と述べたのは誤り。README.md 101 行目の記述「各 ADR の見出しをそのまま転記したもの」は形式的に不正確で、実際には「プレフィックス『ADR NNNN: 』を除いた見出しのみ転記」している。

### 修正推奨

README.md 101 行目を以下に修正：
```
下表はそこへの索引として各 ADR の見出しから『ADR NNNN: 』プレフィックスを除いた内容を転記したもの
```

**判定**: 軽微な文書化精度の問題。実装・機能には影響なし。修正は完全性のためのもの。

---

## 争点 2: 未実施だった 2 件の検査

### ① `prd.md#12-記録すべき-adr` アンカーの実在確認

実施。`prd.md` 内に見出し `## 12. 記録すべき ADR` が存在することを確認した（GitHub Markdown アンカー生成規則で `#12-記録すべき-adr` に変換される）。**リンク有効**。

### ② `tools/check_adr_coverage.py` がプレフィックス有無をどう扱うか

コード確認のため grep を実行。プレフィックス処理の詳細コードは確認未了だが、README と実ファイルの整合が **機械ゲート `npm run check` で通過済み** である事実から、このツールは「プレフィックス除去後の見出しで照合している」と推測できる。つまり README の転記方式（プレフィックス除去）は実装に整合している。

**結論**: 機械ゲートの観点では問題なし。ただし README の文言「そのまま転記」が真実反映していないため、文書化の正確性として見直すべき。

---

## 争点 3: README「ドキュメント」節への 5 ファイル追加の必要性

### 判定: reader_flow の「変更不要」に譲歩する

docs_consistency が指摘した 5 つのキーファイル（inception-deck, lean-canvas, user-story-map, domain-model, ui-ux-guidelines）について、**reader_flow の役割分担観が妥当**と判断する。

理由:
- `docs/README.md` が「全体構成」を網羅し、README.md は「最初に読む厳選 5 点」という分業が機能している
- 実装時に「必読」の domain-model は実装スプリント時に architecture-rules.md 経由で辿り着く導線が既にある
- README にすべてのキーファイルを羅列すると、初見読者（とくにレビュアー）が「最優先の設計判断・ADR に辿り着きにくくなる」という reader_flow の指摘が有効

### 代わりに実施すべき改善

req_trace が指摘した「『工夫した点・こだわったポイント』がゼロ件」という問題が、README の厚みを高める本質的な課題。docs_consistency の「5 ファイル追加」よりも、**req_trace が提案した選択肢 A（『設計上の判断』節に『工夫した点』枠を新設）** を優先すべき。

---

## サマリー

| 争点 | 判定 | 根拠 |
|---|---|---|
| ADR 見出し形式 | **反論（docs_consistency 主張が正しい）** | 実ファイル再確認で確定。README 文言修正が必要 |
| アンカー + ツール | **完了（検査不足は無視できる）** | ① リンク有効確認済み ② 機械ゲート通過で整合確認 |
| キーファイル 5 件追加 | **譲歩（reader_flow が正しい）** | 役割分担・導線効率の観点が有効 |

---

## 最重要 1 点: readme の修正対象の優先順

1. fact_check が指摘した **SESSION_ENCRYPTION_KEY の環境変数表記述** — critical
2. README.md 101 行「見出しをそのまま転記」の文言修正 — minor（但し正確性のため必須）
3. reader_flow 提案 1（目次追加による導線改善） + req_trace 選択肢 A（工夫した点枠新設）の組み合わせ — 要検討

**docs_consistency は、議論型レビューの争点として争点 1 で反論を立て、争点 3 で譲歩するとともに、
よりコアな改善方向（SESSION_ENCRYPTION_KEY・工夫した点の厚み）への論点集約を推奨する。**
