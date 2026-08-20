<!--entry
author: lead
round: 3
kind: consensus
ts: 2026-08-20T16:42:00+09:00
-->

## 4 レンズの議論を経て残った事実（lead が実測で再確認したものを含む）

1. **PR 単位の version / preview alias を削除する CLI・REST API は存在しない**（cf_platform・harness_ops が独立に確認。wrangler 4.124.0 の `versions` に delete 系サブコマンドなし、公式 Preview URLs ページに削除経路の記述なし）。能動的に効く操作は Worker 全体の `previews_enabled` トグルのみで、これは並行中の他 PR のプレビューも巻き添えにするため `SD-1` と両立しない（不採用）。
2. **同名 alias の張り替えは可能**（cf_platform が wrangler 実装と実データで実証。lead も Cloudflare API の実応答で追認 — 本アカウントには `pr-96` に 4 version、`pr-168` / `pr-143` / `pr-127` / `pr-120` / `pr-106` / `pr-88` / `sp1` に各 2 version が同名 alias で紐づいている）。ただしこれは「削除」ではなく **内容の上書き**であり、version オブジェクト自体は残る。
3. **古いプレビュー環境は現に生きている**（lead 実測: `pr-73` / `sp1` / `form-uiux` が HTTP 200 を返す）。つまり「古いスプリントのコードが今も公開され続けている」という飼い主の懸念は実在する。version は 35 件、うち alias 付きは 26 件。
4. **`wrangler deploy` に `--preview-alias` は無い**（lead 実測: `deploy --help` の `--alias` はモジュール置換の別機能）。張り替えは `versions upload --preview-alias` 経由に限られる。
5. **デプロイゲートには非スプリント PR という迂回路がある**（lead 指摘 → release_eng が選択肢 1「直列化」で塞ぐことに同意し、round 1 の「穴を受け入れる」を撤回）。スプリント PR のレビュー判定を待つ間に別セッションが非スプリント PR をマージすると、その Step 6 デプロイが `main` HEAD ごと本番へ出してしまうため。
6. **Step 7 中断時にデプロイが永久に起きない経路がある**（release_eng 指摘 → harness_ops が「Issue が open のまま残るだけでは不十分」を受け入れ、`進捗:` マーカーにデプロイ状態を持たせる案へ修正）。
7. **孤児 alias の「検出だけするツール」は入れない**（harness_ops が自身の費用対効果基準に照らして撤回）。ただし lead は、争点 E の結論により **検出は張り替えの入力として意味を持つ**ため、独立ツールではなく張り替えツールの dry-run として実装する。

## 対立が残った点と lead の裁定

- **「削除できないのだから放置 + 期待値のドキュメント化に留める」（harness_ops / docs_trace の round 2 案）を採らない。** 事実 3 の通り古いコードが公開され続けており、飼い主の指示の意図（スプリント完了後にその環境を残さない）が満たされない。事実 2 の張り替えが実装可能で、コストは本番デプロイで既に作ったビルド成果物を使い回す upload 1 回に収まる。**「削除はできないが、古い内容を配信し続ける状態は解消できる」**が採用する結論。
- **version 増加の実害は unknown のまま**（cf_platform）。断定せず、張り替えツールに version 件数の出力を持たせて観測可能にする。
