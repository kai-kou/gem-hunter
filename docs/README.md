# ドキュメント構成

本プロジェクト（gem-hunter）のドキュメントは、要件定義・リサーチから実装・リリースまでのフェーズに沿って以下のディレクトリで管理する。

> **要件の正本は [`02_requirements/prd.md`](./02_requirements/prd.md)**。各決定の理由・経緯は [`02_requirements/open-questions.md`](./02_requirements/open-questions.md) の決定ログが正本であり、同じ事実を 2 箇所に書かず ID（`D-n` / `Q-n` / `FR-n` / `AR-n` / `NFR-n` / `GR-n`）で参照して結ぶ。

| ディレクトリ | 用途 |
|---|---|
| [`00_concept/`](./00_concept) | 初期コンセプト・プロダクトビジョン |
| [`01_research/`](./01_research) | 市場・競合・ユーザーリサーチ（`market/`, `user/`） |
| [`02_requirements/`](./02_requirements) | 要件定義（PRD、ユーザーストーリー等） |
| [`03_design/`](./03_design) | 設計ドキュメント（`architecture/`, `ui-ux/`, `data-model/`） |
| [`04_development/`](./04_development) | 開発者向けドキュメント（環境構築、API仕様等） |
| [`05_release/`](./05_release) | リリースノート・デプロイ手順 |
| [`adr/`](./adr) | Architecture Decision Records（技術的意思決定の記録） |
| [`meeting-notes/`](./meeting-notes) | 議事録・ミーティングメモ |

## 運用ルール（暫定）

- 各フェーズの成果物は対応するディレクトリに追加し、完了したドキュメントは削除せず残す（意思決定の経緯を追跡可能にするため）。
- 大きな技術的決定は `adr/` にADR（Architecture Decision Record）として記録する。
- ファイル名は `YYYYMMDD-タイトル.md` 等、日付が意味を持つものは日付プレフィックスを付与する（例: 議事録）。
