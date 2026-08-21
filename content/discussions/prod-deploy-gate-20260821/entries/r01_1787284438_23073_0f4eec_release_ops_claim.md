<!--entry
author: release_ops
round: 1
kind: claim
ts: 2026-08-21T12:53:58+09:00
-->

## release_ops（リリース運用レンズ・争点 B/C/D）round 1

### 実測（本ラウンドで確認した事実）

- `python3 tools/check_deploy_gate.py --json` を実行 → **`exit 1`（待機）**。
  ```
  {"can_deploy": false, "blocking_issues": [
    {"number": 308, "title": "improvement: 初見ユーザーのフィードバック10件...", "reason": "Sprint Review 判定が未実施です"},
    {"number": 288, "title": "fix: 本番デプロイ（npm run deploy）が auto mode classifier にブロックされ...", "reason": "Sprint Review 判定が未実施です"}
  ], "repo": "kai-kou/gem-hunter"}
  ```
  （初回実行時は #288 が漏れ、2 回目実行で #288 も検出。GitHub API 反映のタイミング差と見られる — 実行のたびに再確認が必要という教訓）。
- GitHub REST を直接叩いて裏取り: **#288 は既に Issue コメントに `## 🏃 Session Sprint Planning` マーカーを持つ**（4 コメント中）。**#300 はコメント 0 件・マーカーなし**（`is_sprint_issue` が False を返すのは正しい）。#308 も `Session Sprint Planning` マーカーあり。
- `python3 tools/check_prod_drift.py` → 乖離あり（exact）: main HEAD `e4b0758`（PR #307・`.claude/hooks/` `tools/` `docs/rules/` のみ、ランタイム影響なし）に対し本番は `d9ab801` のまま。

### 争点 D（③ ゲート判定への影響）への回答

**#288 が現在ブロック要因に含まれているのは誤検知ではなく、ゲートの正しい挙動である。** `check_deploy_gate.py` は「open かつ `status:in-progress` で、SP タイトル or Sprint Planning マーカーを持つ Issue」全件をスプリント対象とみなし、そのうち Sprint Review 判定コメントがまだ無いものを「待機」理由にする（`REASON_NO_VERDICT`）。#288 は本セッション系列の作業対象として Sprint Planning 済み・Sprint Review 未実施のまま open で残っている（この議論セッション自体がその途中）。したがって **いま `npm run deploy` を再試行することは、D-26 が守ろうとしている「レビュー未確定のスプリント成果物を本番に漏らさない」という設計思想に反する**。classifier が今回たまたま許可したとしても、ゲート側が「待機」と言っている以上デプロイしてはならない。#308 も同型（別スプリントが Sprint Review 待ちで残留）。

→ **D.1 の結論**: 🔴 本セッションで `npm run deploy` を再試行しない。乖離の中身（PR #307 = hooks/tools/rules のみ、ランタイム 0 行）はユーザー影響が無く、ゲートが開くまで待っても実害がない。ゲートが `can_deploy:true` を返すまで待機し、待機中である旨を Issue #288 のコメントに記録するに留める。

### 争点 B: D-31（Workers Builds 移行）は維持か見直しか

**維持を推奨。** 判断材料:
- 実測はブロック 5 / 成功 2（過去 7 試行中 71% がブロック）。この分布は「非決定的だが確率的にほぼ安定して失敗が多い」ことを示す。無人ルーティンは classifier に拒否されても人間の代わりにリトライ・承認できない（`/permissions` の Recently denied はユーザー操作が要る）ため、**現行方式のままだと将来の無人デプロイの過半数が失敗し続ける**。2 回の成功は「絶対に無理ではない」ことの証明にはなるが、「無人運用で信頼できる」ことの証明にはならない——このギャップこそが D-31 の必要性そのもの。
- 成功例のうち直近 1 回（10:32 JST）はセッションが能動的に実行して通っただけで、**再現条件が特定できていない**（本ラウンドは classifier_facts の担当領域だが、release-ops 視点では「原因不明の非決定性に本番リリースの生命線を預ける」こと自体がリスク）。
- 移行コストは一度きり（ダッシュボード接続 1 回 + P-1/P-2 の実装検証）。据え置きコストは「今後も無人ルーティンの deploy 失敗率 ~70% が続き、都度ドリフト検知・手動介入が要る」という継続コスト。一度きり vs 継続、で比較すると移行が優位。
- 失うもの（`D-26` ゲート・プレビュー運用の二重化）は P-1 で吸収可能（下記 C）。単純な「push=deploy」に戻すだけで壊れるものではない。

→ **成功例が出たことは「移行の緊急度を下げる」材料にはなるが「移行を止める」材料にはならない**（サーキットブレーカー的にたまたま通った試行を運用の前提にしない、という一般原則と同じ）。**D-31 は維持**。

### 争点 C: P-1（(a) / (b) / 第 3 案）

まず `pr-review-watcher` SKILL.md Step 7 を確認: **Sprint Review は「マージ直後の同一セッション内」で実施する設計**（Step 6 → Step 7 は連続ステップ）。にもかかわらず #288・#308 のように **Sprint Review 未実施のまま open で残っている実例が現に 2 件ある**（セッション中断・長時間化等で「即レビュー」の前提が破れる）。この事実は (b)（判定が出るまで main にマージしない）の評価に直結する:

- **(b) の重大な副作用**: (b) は「マージ」自体を判定確定までブロックする。今回のように Sprint Review が滞留するケースが実在する以上、(b) を採ると **その滞留がデプロイだけでなく trunk（main）全体への統合を止める**——他の非スプリント PR（改善・docs・retro-try）まで巻き込んで `main` が長時間フリーズしうる。現行方式は「デプロイだけを止め、マージ・push は止めない」ため被害範囲が限定的。(b) はこの利点を失う。**(b) は非推奨**。
- **(a) の評価**: 本命だが「ビルド環境に Python + GitHub API アクセスが要る・未検証」がリスク。Workers Builds のビルド環境仕様（Python 有無・アウトバウンド API 到達可否）は cf_builds レンズの検証待ち。
- **🔴 第 3 案（release-ops 視点で提案）: 「デプロイ専用ブランチ (`deploy-live`) を Workers Builds の本番ブランチに指定し、ゲート判定はセッション側（今の Python 環境）で実行してから `deploy-live` を fast-forward する」**。
  - 具体的には: Workers Builds の「本番ブランチ」を `main` ではなく `deploy-live` に設定する。`main` は今までどおり trunk（マージ先）のまま。Step 6/7 の中で `check_deploy_gate.py` が `can_deploy:true` を返した時点で、セッションが `git push origin main:deploy-live`（fast-forward）を実行する。Workers Builds は `deploy-live` への push だけを見て `npm run deploy` 相当（Build command 空 / Deploy command `npm run deploy`）を実行する。
  - **利点**: ① `check_deploy_gate.py` は今回の実測（本ラウンドで exit 1 を実際に取得済み）のとおり **現行のセッション環境で確実に動く**（Python・GH API 到達は実証済み）ため、Workers Builds 側のビルド環境に Python/GitHub API アクセスを持ち込む必要がなくなり、P-1(a) の「未検証」リスクをまるごと消せる。② fail-closed 性質を保てる: ゲート判定不能（exit 2）や待機（exit 1）のときは `deploy-live` を進めない＝Workers Builds は起動しない（何もしないことが安全側）。③ `main` は従来どおり「マージ = 公開反映」のまま保て、`D-26` の「デプロイだけを止める」設計思想とも整合する。④ P-2（シークレット引き継ぎ）の検証は (a) でも (c) でも同じだけ必要（Workers Builds が `wrangler deploy` を実行する点は変わらないため、こちらは免除されない）。
  - **コスト**: 新しい概念（`deploy-live` ブランチ）をドキュメント・運用に追加する。Step 7 の「デプロイ実行」を「`check_deploy_gate.py` 実行 → true なら `git push origin main:deploy-live`」に書き換える（既存の `npm run deploy` 直接呼び出しをやめる）。ブランチ保護設定は不要（session が直接 fast-forward するだけ）。
  - **推奨順位**: **(c) を第一候補として推す**（P-1(a) の最大の不確実性を検証不要にできるため）。(a) はビルド環境検証で (c) と同等以上のリスクが判明した場合の代替、(b) は非推奨（上記の理由）。

### 争点 D（②③ 続き）: 本セッションの完遂範囲

- **今回コードとして書ける／書くべきもの**: (1) `docs/03_design/infrastructure/cloudflare-infrastructure.md` §8.2.3 の P-1 決定欄に上記 (c) 案を追記し、設定値表の「本番ブランチ」を `deploy-live` に更新（決定が出た場合）。(2) Step 7 のデプロイ手順を「ゲート判定 → `deploy-live` へ fast-forward」に書き換える差分（`pr-review-watcher` SKILL.md）。(3) L-130 の実態訂正（classifier_facts 側の担当・本ラウンドでは触れない）。
- **今回は実行しない**: `npm run deploy` の再試行（上記 D.1 の結論どおり、ゲートが待機中のため）。
- **Issue #290 を waiting-user に出せるか**: (c) 案が採用されるなら **出せる**。ダッシュボード手順が「本番ブランチ = `deploy-live`」という 1 点だけ変わる以外は §8.2.3 の既存の設定値表（Worker 名 `gem-hunter`・Build command 空・Deploy command `npm run deploy`・Non-production branch builds 無効・Build variables/secrets 設定）がそのまま使える。cf_builds のビルド環境検証（Python 有無の確認は (c) 採用なら不要になるが、シークレット引き継ぎ・Node バージョンの検証は残る）を待ってから最終文言を確定する。

---
返却済みサマリー: post 済み。`check_deploy_gate.py --json` 実測 exit=1（#308・#288 が Sprint Review 未実施でブロック）。D-31 維持を推奨、P-1 は (a)(b) に加え第3案「deploy-live ブランチ + セッション側ゲート」を提案（(a)の未検証リスクを解消）、本セッションでの `npm run deploy` 再試行は非推奨（ゲート待機中のため）。
