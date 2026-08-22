<!--entry
author: workflow_compliance
round: 1
kind: claim
ts: 2026-08-22T09:18:38+09:00
-->

# 参照ワークフロー準拠検証（workflow_compliance Round 1）

## 1. 15 ステップ × 必達原則準拠表

| ステップ | 必達原則 1～8 準拠可否 | 読み替え / 注釈 |
|---------|-----------------|----------------|
| **Step 1: 構成作成** | ✅ 準拠 | 標準実装。gem-hunter 規約に従う |
| **Step 2: 構成セルフレビュー** | ⚠️ 読み替え要 | **軸2（MECE）必須**。`doc-review` スキル（参照リポ固有 19 行）は gem-hunter に無し。**代替: `discussion-review` スキル** で Lead 1 名 + Reviewer 3 名（MECE / ファクト / 最新情報 軸）で実施 |
| **Step 3: テキスト版作成** | ✅ 準拠 | Write 80 行以内 + Edit 3～4 要素ずつ分割（lessons.md 適用） |
| **Step 4: テキスト版セルフレビュー** | ⚠️ 読み替え要 | **self-reviewer スキル使用** （gem-hunter 標準）。MECE 観点は必須維持 |
| **Step 5: Google Drive アップロード** | ❌ 環境適合不可 | **`gws` コマンド未装備**。**読み替え**: ① ローカル PPTX 生成 → ② PR に添付 → ③ ユーザー確認後 Push。 Google ドライブ共有は別途ユーザー作業 |
| **Step 6: テキスト版ユーザーレビュー** | ✅ 準拠（読み替え） | **PR コメント欄で収集**。明示承認（「OK」）まで Step 7 進行禁止は維持 |
| **Step 7: フィードバック反映** | ✅ 準拠 | PR 修正コミット。Step 6 へ戻るループ維持 |
| **Step 8: テキスト版最終セルフレビュー** | ⚠️ 読み替え要 | **self-reviewer** で再実施。ファクト最新性再確認は必須（必達5） |
| **Step 9: 画像版作成** | ✅ 準拠（必達8 注力） | 「一字一句正確に」指示を必ずプロンプトに含める。lessons.md 実例 3 の分割原則厳守（繰り返し構造は 3～4 要素ずつ） |
| **Step 10: 画像版セルフレビュー** | ⚠️ 読み替え要 | **self-reviewer**。テキスト一字一句照合は手動確認（実例 3 のタイムアウト対策）。MECE・統一性も必須 |
| **Step 11: 画像版アップロード** | ❌ 環境適合不可 | **読み替え**: ローカル PPTX → PR 添付 → ユーザー確認後 Push |
| **Step 12: 画像版ユーザーレビュー** | ✅ 準拠（読み替え） | **PR コメント欄で収集**。明示承認まで Step 13 進行禁止 |
| **Step 13: フィードバック反映** | ✅ 準拠 | PR 修正コミット。手順原則厳守 |
| **Step 14: 画像版最終セルフレビュー** | ⚠️ 読み替え要 | **self-reviewer**。最終性確認 |
| **Step 15: 最終版アップロード** | ❌ 環境適合不可 | **読み替え**: PR マージ後 `content/discussions/project-slides-{YYYYMMDD}/output/` に配置。成果物サマリーをユーザーに報告 |

---

## 2. セルフレビュー実装方法（Step 2 / 4 / 8 / 10 / 14）

本セッションで使用可能な代替戦略：

**Plan A: `discussion-review` スキル（推奨・高確度）**
- Lead 1 名（main セッション）+ Reviewer 3 名（専門軸: MECE / ファクト・最新情報 / テキスト品質）
- Round 1 で指摘収集 → 修正 → Round 2（指摘ゼロ時点で終了）
- **利点**: 必達原則 2（MECE） を複数視点で保証。gem-hunter 既存スキル
- **注意**: タイムアウト対策（長大ドキュメント読み込み禁止・lessons.md 実例 3）

**Plan B: `self-reviewer` スキル（軽量・単独実施）**
- テキスト版時点（Step 4 / 8）での使用
- MECE 観点は手動チェック項目として追加
- **利点**: 速度・既存スキル
- **制限**: 単一視点のため複合指摘の見落としリスク

**推奨運用**:
- Step 2: discussion-review（構成段階での MECE 確保が後続全体に効く）
- Step 4: self-reviewer（必達原則 7 テキスト量チェック中心）
- Step 8: discussion-review（ユーザーフィードバック確実反映確認）
- Step 10: self-reviewer（テキスト一字一句照合はツール不要・目視）
- Step 14: self-reviewer（最終性確認のみ）

---

## 3. ユーザーレビュー実装方法（Step 6 / 12）

`gws` （Google ドライブ）不在のため、代替フロー：

**実装**:
1. ローカル PPTX 生成 → PR に Artifact（HTML preview）または添付で掲載
2. PR コメント欄でフィードバック収集 → 修正 → PR コメントで再共有
3. 明示承認（「OK」/ 「承認」）確認後のみ次ステップへ移行
4. 最終版マージ後、`content/discussions/{project_slug}/output/` に PPTX/画像ファイル配置

**記録媒体**: GitHub PR コメント（公式・監査可能・thread resolve で管理）

---

## 4. `doc-review` スキル代替案

参照リポジトリ `doc-review` は 19 行で 7 軸並列レビュー（Task tool + Explore サブエージェント）を実行。

**gem-hunter での選択肢**:
1. **参照リポの SKILL.md を本リポに複製**（許容・スキル数加算）→ API 統合・新 Task tool 追加コスト
2. **`discussion-review` で代替**（推奨・実績あり）→ Round 制御・手動ブレーキあり・軸数調整可
3. **`code-review` + 手動チェックリスト**（最軽量・テキスト量多時は避ける）

**結論**: **Plan A は `discussion-review` で実施。必達2（MECE）をチェック項目に明示化**。

---

## 5. タイムアウト対策・本セッション実装ガイド

参照リポ `lessons.md` から抽出（実例 1～3）:

| 作業 | 対策 | 本セッション適用 |
|-----|------|-----------------|
| **スクリプト生成** | 骨子 Write 80 行 + Edit 3～4 要素ずつ | Step 3 / 9 で全スクリプトに適用 |
| **大型ドキュメント全読み** | Grep で節特定 → offset/limit ≤150 行 | Step 9 プロンプト読み込み時に適用 |
| **テンプレート挿入** | 丸コピーしない・関数 import or ピンポイント抽出 | Python-pptx module 利用（コピペ防止） |
| **参照リポ資料引用** | 原典ポインタ（URL・取得日）を記録 | 本セッション rules に追加 |

**実装チェックリスト**:
- [ ] スクリプト作成時は 80 行以内単位で Write / Edit を分割
- [ ] プロンプト含む画像生成ループは 3～4 要素ずつ繰り返し
- [ ] lessons.md 実例 3 の再発防止を意識（300 行スクリプト一発 Write の禁止）

---

## 6. 成果物配置案

参照リポ: `events/{日付}/{content, references, scripts, output}/` 構造

**gem-hunter 既存規約** (`find content docs tools`):
- `content/discussions/{discussion_name}/` （議論記録のみ）
- `content/research/` （リサーチ出力）
- `docs/` （仕様・設計・規約）
- `tools/` （スクリプト）

**スライドプロジェクト配置案**（両規約統合）:

```
content/discussions/project-slides-20260822/
  ├ whiteboard.md (discussion 記録)
  ├ output/
  │  ├ slides_content_20260822.md (構成マークダウン)
  │  ├ slides_20260822_text.pptx (テキスト版)
  │  ├ slides_20260822.pptx (画像版)
  │  └ images/ (生成画像・PNG)
  └ references/
     ├ PPTX_TEMPLATE.md (デザイン定義引用・内部参照リンク)
     └ *.md (要件定義・スコープ・ユーザーフィードバック)

tools/project_slides_20260822/ （スクリプト専用）
  ├ generate_text_pptx.py
  ├ generate_image_version.py
  └ run_all_steps.sh
```

**バイナリ（PPTX / PNG）扱い判定**:
- `.gitignore` に明示的な ignore ルールなし → **コミット可能**
- **ただし** `content/analytics/*` / telemetry 系は ignore（本構成に無関係）
- **推奨**: PPTX・PNG は `output/` 配下にコミット（PR で確認可・共有容易）
- **代替**: バイナリサイズ >10MB なら `.gitattributes` で LFS 化（別途要検討）

---

## 7. 実行責務分担（メインセッション vs サブエージェント）

| ロール | 操作 | 実施者 |
|--------|------|-------|
| **オーケストレーター** | ステップ間の進行制御・最終判断・ユーザー報告 | main セッション（本エージェント） |
| **セルフレビュー実行** | discussion-review / self-reviewer 起動・結果統合 | 委譲可（サブエージェント） |
| **コンテンツ作成** | 構成・テキスト・プロンプト・スクリプト実装 | 委譲可（役割分担型 fan-out） |
| **ファクトチェック・最新情報リサーチ** | WebSearch / WebFetch 実行 | main（必達原則 4・5 重視） |
| **ユーザーレビュー管理** | PR コメント監視・明示承認確認・次ステップ判定 | main セッション（A-1 相当） |

---

## 結論

✅ **15 ステップワークフローは gem-hunter で実装可能。必達原則 1～8 はすべて維持される**。

⚠️ **読み替え**: `gws` 環境変数不在 (Step 5/11/15) は PR 配置 + ユーザー作業で吸収。セルフレビューは `discussion-review` / `self-reviewer` で実装。

🔧 **タイムアウト対策**: lessons.md 実例 3（分割 Write/Edit）を全スクリプトに適用。

📁 **配置**: `content/discussions/project-slides-{YYYYMMDD}/output/` に成果物集約。バイナリコミット許容（`.gitignore` 既定）。
