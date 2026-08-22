<!--entry
author: workflow_compliance
round: 2
kind: rebuttal
ts: 2026-08-22T09:23:32+09:00
-->

# workflow_compliance Round 2 Rebuttal

## 論点 1: 成果物配置案の修正

**Round 1 の誤り認める。** `content/discussions/` は議論記録（whiteboard.md / entries/meta.json）専用。成果物は独立ディレクトリへ。

**修正案**:
```
content/slides/project-slides-20260822/
  ├ content/
  │  ├ slides_outline.md (構成マークダウン)
  │  └ 参考資料
  ├ output/
  │  ├ slides_20260822_text.pptx
  │  ├ slides_20260822.pptx
  │  └ images/ (PNG)
  └ scripts/
     └ generate_*.py

content/discussions/project-slides-20260822/ ← whiteboard のみ
  └ whiteboard.md / entries/
```

**スクリプト配置**: `tools/` に `project_slides_20260822/` サブディレクトリを新設（既例: `tools/infographic/`）。

---

## 論点 2: バイナリコミット可否（実物再確認）

### 確認結果

| ファイル | 状態 | サイズ | LFS 対象か | コミット許可 |
|---------|------|--------|----------|-----------|
| `.webp`（既存・13 枚） | tracked | 207〜260KB | **設定なし**（通常 git） | ✅ コミット済み・許可 |
| `.pptx`（新規予定） | — | 数 MB 推定 | **明示ルールなし** | ⚠️ 確認必要 |
| `.png`（新規予定） | — | 500KB〜数 MB 推定 | **明示ルールなし** | ⚠️ 確認必要 |

### 判定

- **WebP 215KB × 13 が tracked** = **画像バイナリのコミットは許容基準**。ただし `git-lfs-safety-rules.md` 存在 = **LFS 運用ポリシーはある**。
- `.gitignore` に PNG/PPTX 明示ルールなし = **未指定は "許容"** と解釈するのは根拠不十分。
- **PPTX は Microsoft Office フォーマット（ZIP アーカイブ）で差分が取りにくく、複数エージェント同時編集に不向き**（テキストベースではないため git マージが機械的にできない）。

**推奨**:
- **PPTX**: リポジトリに登録しない。生成後 issue 添付 or Artifact で PDF プレビュー提供。ユーザー承認後ローカル保存。
- **PNG**: 1 枚あたり想定サイズ（GPT-image-2 生成 1536×864） = 200〜400KB。13 枚なら 2.6〜5.2MB。WebP 215KB × 13 ≈ 2.8MB と同等 → **PNG コミット許容（ただし画像が増えすぎたら WebP に変換検討）**。

---

## 論点 3: ユーザーレビュー実施方法の修正

**Round 1 の「PR コメント欄」案は不適切。** 本セッションはチャット直接対話中（AskUserQuestion 既実施）。

**修正案**:

### Step 6 / 12 実装

1. **テキスト版 PPTX 生成後** → **PNG スクリーンショット化（libreoffice / soffice）or Artifact で HTML Preview**
2. **チャットでスクリーンショット or Artifact URL を直接ユーザーに提示**
3. **「OK」の明示承認をチャットで回収**
4. フィードバック → PR で修正 → 再度チャットで共有 → 承認

**PPTX 閲覧方法の選択肢**（環境確認後に判定）:
- `libreoffice` / `soffice` がインストール済み → PPTX to PNG 変換実行
- 未装備 → Artifact で PDF プレビュー or テキスト版として `.md` を直接見せる

**記録**: ユーザーレビューは「チャット履歴 + PR コメント双方に記録」（チャット = リアルタイム対話、PR = 公式記録）。

---

## 論点 4: セルフレビュー実施主体と「この議論が Step 2 を兼ねるか」

### 4.1 議論型 discussion-review が Step 2 を兼ねるか

**部分的に兼ねる**: この Round 1 議論が（narrative_design 主導で）アウトライン 7 項目の**論理・MECE・異議反論**を行い、構成を磨いている。

**ただし Step 2 は「ファクトチェック + 最新情報リサーチ」も必須** → **議論型では不完全**。

**結論**: Round 1〜2 で「構成の論理性・MECE」は担保するが、**Step 2 セルフレビューとして「ファクトチェック・最新情報リサーチ」を別途実行する**（Slack notification の都合上 Round 2 完了後に起動）。

### 4.2 画像版一字一句照合（Step 10）の機械化案

画像から Tesseract-OCR で抽出したテキストを構成マークダウンと突き合わせる手段：

```bash
# 1. 生成画像を OCR
for img in images/*.png; do
  tesseract "$img" stdout >> extracted_text.txt
done

# 2. 構成マークダウンから「Image text elements」を抽出
grep -A 50 "### Image text elements" slides_outline.md > expected_text.txt

# 3. 照合（差分を表示）
diff <(sort expected_text.txt) <(sort extracted_text.txt) || echo "Text mismatch detected"
```

**利点**: 手動一文字照合の人力を削減。**制限**: OCR エラー（特殊文字・日本語フォント・背景色）で誤判定の可能性 → **最終確認は目視**が引き続き必須。手順は Step 10 で「OCR 照合 → 視覚的確認」の 2 段階に落とす。

---

## 総括

| 論点 | Round 1 | 修正 | 影響範囲 |
|-----|--------|------|--------|
| 配置 | ❌ 議論専用ディレクトリに混在 | ✅ 独立 `content/slides/` を切る | ディレクトリ構成・スクリプト配置 |
| バイナリ | ⚠️ 根拠不十分 | ✅ PPTX は非コミット・PNG コミット許可 | 成果物受け渡し方法 |
| ユーザーレビュー | ⚠️ PR コメント案は非効率 | ✅ チャット直接・PNG プレビュー | Step 6/12 実装形 |
| セルフレビュー | ⚠️ 議論型のみで不完全 | ✅ 議論型(MECE) + 別途 Step 2(ファクト) | セルフレビュー段階の実行順 |

15 ステップワークフローの適用可能性は変わらず（読み替え条件が明確化された）。
