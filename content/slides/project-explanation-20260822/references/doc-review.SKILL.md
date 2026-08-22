---
name: doc-review
description: ドキュメントを7つの専門軸で並列レビューし、統合修正計画書を作成する。「ドキュメントレビュー」「文書レビュー」と言われた場合にも使用。
user-invocable: true
---
指定されたドキュメントを7つの専門軸で並列レビューし、統合して修正計画書を作成してください。

対象ドキュメント: $ARGUMENTS

7つのレビュー軸：
1. 戦略・目的（Why）
2. 論理・MECE（What）
3. 実行設計（How）
4. ポジション視点（For Whom）
5. 可読性（Readability）
6. 人間らしさ（Humanize）
7. リスク（Risk）

Task tool（subagent_type: Explore）を活用して、Batch 1（4つ並列）→ Batch 2（3つ並列）→ 統合レビュー → 修正計画書作成の順で実行してください。
