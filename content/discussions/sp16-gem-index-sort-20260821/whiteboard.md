<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: SP-16: キーワード検索結果を Gem Index 順に並べ替える実装の設計を確定する

- 議題ID: `sp16-gem-index-sort-20260821`
- 論点: 確定仕様（D-30）: ① Index を持たない結果は上位に集めて末尾に残す（絞り込まない） ② 最大 1,000 件取得してから並べ替える。争点 7 件: (1) 全件取得の発火条件 (2) キャッシュキー粒度 (3) ページの意味と AC-6/AC-7 整合 (4) join の層 (5) Index なし同士の順序 (6) NFR-5 のレート予算 (7) sp:8 に収まるか
- 参加者: `domain_arch`, `rate_cache`, `ux_paging`, `scope_test`
- 投稿数: 0
- 更新: 2026-08-21T09:54:45+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

_（まだ投稿がありません）_
