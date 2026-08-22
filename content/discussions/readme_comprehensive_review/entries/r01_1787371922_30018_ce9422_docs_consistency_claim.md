<!--entry
author: docs_consistency
round: 1
kind: claim
ts: 2026-08-22T13:12:01+09:00
-->

# README.md ドキュメント整合検証 — docs_consistency レンズ

## 検査結果サマリー

- **リンク実在**: ✓ 全 31 個の相対リンクが実在確認
- **ADR 索引**: ⚠️ 形式上の矛盾 15 件（プレフィックス「ADR NNNN: 」の有無）
- **ドキュメント間整合**: ⚠️ キーファイル参照の不完全性 5 件
- **権利表示**: ✓ NOTICE / LICENSE と一致

---

## 1. リンク検証

### ✓ 実在確認（全クリア）

31 個の相対リンク全てが実ファイルとして存在:
- `./site`, `./LICENSE`, `./NOTICE`
- `./docs/` 配下の全 ADR（0001〜0015）
- 要件・設計・開発ドキュメント全て

### ⚠️ アンカー（見出し）の検証

`./docs/02_requirements/prd.md#12-記録すべき-adr` の見出し実在は確認ナシ（時間制約・スコープ外判定）。

---

## 2. ADR 索引の矛盾

### ⚠️ 形式上の不一致 15 件

**状況**: README の ADR テーブル（行 103-120）では見出しを転載と述べているが、実ファイルの見出しとプレフィックス有無が異なる。

| 形式 | README の記載 | 実ファイル（docs/adr/*.md） |
|---|---|---|
| **見出し** | `UI スタックに Tailwind CSS...` | `# ADR 0001: UI スタックに Tailwind CSS...` |
| **プレフィックス** | なし | あり（`ADR NNNN: `） |

**影響度**: 低 — 見出しの内容（`ADR NNNN: 」除去後）は完全一致。形式的な文言（「そのまま転記」）の厳密性の問題。

**修正案**: README 101 行目の記述を「各 ADR の見出しから『ADR NNNN: 』プレフィックスを除いた内容を転記」に修正。

---

## 3. ドキュメント構成の整合性

### ⚠️ README が参照していないキーファイル 5 件

`docs/README.md` で「実装時に読む 3 つの正本」等として指摘されているが、README.md では言及されていないもの:

| ファイル | 所属セクション | README での言及 |
|---|---|---|
| `00_concept/inception-deck.md` | コンセプト | ✗ 未参照 |
| `00_concept/lean-canvas.md` | コンセプト | ✗ 未参照 |
| `02_requirements/user-story-map.md` | 要件 | ✗ 未参照 |
| `03_design/data-model/domain-model.md` | **実装時の 3 正本の 1 つ** | ✗ 未参照 |
| `03_design/ui-ux/ui-ux-guidelines.md` | UI 設計 | ✗ 未参照 |

**影響度**: 中 — `domain-model.md` は architecture-rules.md で「実装必読」と明記されているのに README では案内されていない。

**修正案**: 
- README 「ドキュメント」セクション（54-63 行）に上記 5 ファイルへの補足リンクを追加
- または、セクション構成を拡張して、ユーザー別の「読み順ガイド」を追加

---

## 4. 決定ログとの矛盾チェック

### ✓ 完全一致

README で参照している `D-21` / `Q-12` の記述が open-questions.md の決定内容と一致:

| ID | README の言及内容 | open-questions.md の記述 | 一致度 |
|---|---|---|---|
| `Q-12` | 旧称 IndieGems を `gem-hunter` に統一 | 正式名称を `gem-hunter` に統一する | ✓ 一致 |
| `D-21` | dev 環境を置かない（trunk-based） | trunk-based（PR ごとのプレビュー + `main` = 本番）を維持 | ✓ 一致 |

---

## 5. 権利表示の整合

### ✓ MIT License との対応

README の「ライセンスと権利表示」セクション（121-132 行）が NOTICE と完全一致:

- **MIT License 対象**: コード + ドキュメント
- **対象外**:
  - `docs/02_requirements/minimum-requirements.md` — 与件（第三者著作権）
  - `./.claude/skills/skill-creator/` — Apache License 2.0

---

## 最重要 3 件の指摘

1. **ADR 見出しの形式矛盾** — README.md 101 行「そのまま転記」の文言を修正（低リスク・文書化の正確性）
2. **domain-model.md の言及漏れ** — 実装時の必読ドキュメントが README では紹介されていない（中リスク・ユーザーが見落とす）
3. **キーファイル参照の不完全性** — docs/README.md と README.md の構成表現が異なる（低リスク・補完性の問題）

---

## 検査範囲と限界

✓ 実施:
- 相対リンク実在確認（全 31 件）
- ADR ファイル・見出しの突合（15 件）
- 他ドキュメント参照の補完性検査
- Q-12/D-21 の記述一致確認

✗ 未実施（時間制約・スコープ外）:
- 各 ADR の内容が prd.md `§12` 要件と一致するか（機械検査 `tools/check_adr_coverage.py` 推奨）
- アンカー（`#12-記録すべき-adr` 等）が見出しとして存在するか
- site/ 配下の相対パス検証
