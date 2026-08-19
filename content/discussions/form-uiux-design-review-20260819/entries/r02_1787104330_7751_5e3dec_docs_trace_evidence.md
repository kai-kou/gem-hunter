<!--entry
author: docs_trace
round: 2
kind: evidence
ts: 2026-08-19T10:52:09+09:00
-->

# Round 2: 他者提案との既存記述衝突検査

## 1. ux_standards「§2.4 コントロールサイズトークンを新設」案 → 衝突判定

### 衝突 A: 既存 §2.3 との内容重複
- `docs/03_design/ui-ux/ui-ux-guidelines.md:67-71` → §2.3 現在行
  - 「スペーシング: 4px グリッド」と「タイポスケール: 12/14/16/20/24px の 5 段階」を定義
  - 新規 §2.4「コントロールサイズトークン」は同じ寸法体系（4px グリッド・px 単位の 5 段階）で、**同じ層の設計決定をセクション分割**することになり、内容の整合が問題になる（どちらが正本か判定不能になる）

### 衝突 B: 既存 §4.5・§7.5 との二重定義
- `docs/03_design/ui-ux/ui-ux-guidelines.md:142-147`（§4.5 ページネーション）
  - 既に「ページ番号ボタンは 24×24 CSS px 以上」を具体数値で規定
- `docs/03_design/ui-ux/ui-ux-guidelines.md:220-224`（§7.5 ターゲットサイズ）
  - 同じく「24×24 CSS px 以上」を規定
- 新規 §2.4 の「コントロール高さのトークン」が「44px 推奨」を入ると、§7.5 の「24px 必須」と **二層構造**になるのは良いが、§4.5（ページネーション）はどちらに従うのかが曖昧になる

### 衝突 C: 節番号の変更が後続参照を破壊
- grep で `§4` 参照を確認: `docs/02_requirements/user-story-map.md:294` に「[ガイドライン §4](../03_design/ui-ux/ui-ux-guidelines.md)」と参照
- 現状 §4（カード設計）が §5 に変わると、このリンク参照が対応ズレ
- grep で `§2.3` 明示参照: `testing-strategy.md` 等に現状なし（ただし「スペーシング」「タイポスケール」への内容参照は多い）
- **結論**: 新規 §2.4 を挿入すると後続全セクション番号が変わり、`user-story-map.md:294` の参照が対応ズレする。加えて「デザイントークン」§2 内の細分化は「色トークン・タイポ・スペーシング・新規コントロールサイズ」で粒度不揃いになる

### 推奨されるアプローチ
§2.3 を **「タイポグラフィ・スペーシング・コントロール基本寸法」として統合拡張** し、セクション番号変更を避ける。または、設計上の理由で分離必須なら、§2.3 直後に §2.4 を挿入したうえで、**user-story-map.md 等の参照を全検査して修正する必要がある**（手作業・error-prone）。

---

## 2. review_process「code-review Step 1 + pr-review-watcher Step 7」拡張案 → 実装対象の正確な行

### 対象 1: `.claude/skills/code-review/SKILL.md` の Step 1 観点表
- **現在の位置**: `L41-51` の観点別ファインダー table
- 現在の行抜粋:
  ```
  | 項目 | 対象 | 指示（焦点） |
  | ファイルの層・責務 | app/, src/ 含む | architecture-rules.md に従い層を判定（…） |
  | ドメインモデル整合 | app/, src/ 含む | domain-model.md の値オブジェクト定義と型が一致（…） |
  ```
- **書き換え対象行**: table 末尾（L51 の `)」が終わる行）の次に「UI・アクセシビリティ」行を追加
  - 新規行のフォーマット: `| UI・アクセシビリティ | app/ / src/ui/ 含む | ui-ux-guidelines.md §2/§4/§7 の寸法・タイポ・ターゲットサイズ・コントラスト規定を満たすか判定 |`
  - 条件式（「app/ または src/ui/ のときだけ」）の実装は指示テンプレート L56 で並列条件として追加

### 対象 2: `.claude/skills/code-review/SKILL.md` の指示テンプレート
- **現在の位置**: `L53-64` の各観点ごとの指示文テンプレート
- 新規観点「UI・アクセシビリティ」への指示テンプレートを末尾に追加（例）:
  ```
  🔴 **UI・アクセシビリティ**
  次を判定して明記してください:
  - コントロール高さ・幅の変更なし、または新規コントロール追加: `ui-ux-guidelines.md` §2.4（新規トークン）を満たす
  - タイポ・スペーシング変更: §2.3 の 5 段階スケール・4px グリッドを守る
  - ターゲットサイズ（アイコンボタン等）: §7.5 の 24px 以上を満たす
  - コントラスト（色変更を含む場合）: §2.1 の 4.5:1 以上（§2.1 の表を参照）
  ```

### 対象 3: `.claude/skills/pr-review-watcher/SKILL.md` の Step 7 受け入れ判定役
- **現在の位置**: `L144-161` のエージェント定義と必須 3 項目
- 現在の行抜粋（L156-161）:
  ```
  🔴 **受け入れ判定役**（fan-out の第一メンバー）
  必須チェック 3 項 → 本PR:
  1. **設計文書を 1 ホップ先まで辿ったか**（…）
  2. **実行結果で断定したか**（…）
  3. **単独実行チェック**（編成欄が `Team: solo` でなく…）
  ```
- **書き換え対象**: 必須 3 項の直後（L161 の末尾）に以下を追加:
  ```
  4. **UI/デザイン変更時のガイドライン確認**（PR 差分が `app/**` `src/ui/**` を含む場合のみ）: 
     コントロール寸法・タイポスケール・ターゲットサイズ・コントラスト比が 
     `docs/03_design/ui-ux/ui-ux-guidelines.md` の該当節（§2/§4/§7）を満たすか確認。
     確認結果と参照セクション ID を Step 7 の返り値コメントに記載する。
  ```
- 役割数は 2 のまま変更なし（既存「受け入れ判定役」の責務を4項に拡張するだけで、3つ目の役割は増やさない）

### 参照ファイルの確認
- grep で `code-review/SKILL.md` 参照: `pr-review-flow-summary.md:17`（「Layer 1 の標準実行手段は `Skill(code-review)`」と記載 → 該当で参照が生きている）
- grep で `pr-review-watcher/SKILL.md` 参照: `pr-review-flow-summary.md:11` 等で明示（参照は生存）

---

## 3. guardrail_eng「`tools/check_ui_dimensions.py` 新設 + `run_checks.sh` 統合」案 → 実装箇所と書式

### 対象ファイル: `tools/run_checks.sh`
- **現在の構成**: L1-8（前文）、L10-60（6 個のチェック関数 check_lint/format/test/a11y など）
- **新規追加位置**: L60 の最終チェック（現在は a11y `axe`）直後に「7. UI 寸法検査」を追加
- **挿入予定行**: L62 相当（確認: `tail -20 tools/run_checks.sh` で最終行確認後に決定）

### 書式（既存チェックに倣った追加）
```bash
# 7. UI 寸法検査（コントロール高さ・幅がガイドライン準拠）
echo "🔍 UI 寸法検査..."
python3 tools/check_ui_dimensions.py --self-test > /dev/null 2>&1 && \
    python3 tools/check_ui_dimensions.py src/ui/components/button.tsx src/ui/components/input.tsx || {
    echo "❌ UI 寸法違反（詳細は上記参照）"
    return 1
}
```
- 既存チェック（check_lint など）と同じ「成功時は沈黙、失敗時は Error として停止」の流儀を継承
- **対象ファイル固定**: `src/ui/components/button.tsx` / `src/ui/components/input.tsx`（過検知を避けるため）
- `--self-test` フラグ（既存 `check_architecture_boundaries.py` に倣う）で統一テストを実行可能

### 既存チェックの確認（責務重複なし）
- grep で `tools/` 配下の existing checkers:
  - `check_architecture_boundaries.py`: import 境界（責務なし重複）
  - `check_cjk_markdown.py`: Markdown CJK スペーシング（責務なし重複）
  - `check_datetime_tz.py`: datetime TZ（責務なし重複）
  - `self_review_check.py`: TDD 順序・アーキテクチャ静的チェック（責務なし重複）
  - 新規 `check_ui_dimensions.py`: CSS クラス静的抽出 → px 数値マッピング（独立領域）

**衝突なし。** 各チェッカーは独立した正規表現パターン対象で、同じファイルを複数回スキャンしても結果の矛盾は起きない。

---

## まとめ

| 提案者 | 提案 | 衝突 | 根拠ファイル |
|--------|------|------|--------------|
| ux_standards | §2.4 新設 | **あり**（§2.3/§4.5/§7.5 との内容重複・後続参照ズレ） | user-story-map.md:294 の参照が変わる |
| review_process | code-review/pr-review-watcher 拡張 | **なし**（既存テーブル末尾への追加） | SKILL.md:41-51/L156-161 |
| guardrail_eng | check_ui_dimensions.py + run_checks.sh | **なし**（独立した新規検査エンジン） | run_checks.sh:60 の次行に追加 |
