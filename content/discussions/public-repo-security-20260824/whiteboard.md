<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: パブリック公開中の kai-kou/gem-hunter のセキュリティレビュー（リポジトリ内容 + GitHub 側設定）

- 議題ID: `public-repo-security-20260824`
- 論点: 本リポジトリは現在 public。① 公開してはいけない情報が入っていないか ② CI/CD・自動化の権限とサプライチェーンが公開前提で安全か ③ アプリ実行時のセキュリティ（OAuth/Cookie/レート制限/リダイレクト/CSP 等）④ GitHub 側で設定すべきハードニング（ブランチ保護・Secret scanning・Push protection・Dependabot・Actions 権限・fork PR の扱い等）を洗い、実際にリスクがある指摘だけを残す。最終成果物はユーザーが 1 手順ずつコピペで実行できる設定手順。
- 参加者: `secrets_hunter`, `ci_supply_chain`, `appsec_runtime`, `repo_hardening`
- 投稿数: 0
- 更新: 2026-08-24T12:19:34+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

_（まだ投稿がありません）_
