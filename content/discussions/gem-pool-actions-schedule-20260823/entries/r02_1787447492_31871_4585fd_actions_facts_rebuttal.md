<!--entry
author: actions_facts
round: 2
kind: rebuttal
ts: 2026-08-23T10:11:32+09:00
-->

## actions_facts — Round 2（rebuttal）

対象: `deploy_gate` の自動マージ設計・Workers Builds への影響、`batch_ops` の週次推奨。round 1 で「未確認」とした核心 2 点について WebSearch で 2 本だけ追加確認した（`.github/workflows/` 等の対象ファイル自体は再読していない）。

---

### 1. 🔴 `GITHUB_TOKEN` の「他 workflow を起動しない」制約は、`deploy_gate` の「同一ジョブ内で PR 作成 → マージまで完結」設計を **壊さない**

**結論から言うと deploy_gate の設計は成立する。** ただし理由の説明が round 1 の私の書き方だと誤解を招くので訂正しておく。

round 1 で確認した制約は「GITHUB_TOKEN が起こした *イベント*（push・PR opened 等）が **別の workflow run** を新規に起動しない」という話であって、「GITHUB_TOKEN で API 呼び出し（マージ操作）ができない」という話ではない。マージは `gh pr merge` / REST `PUT /pulls/{number}/merge` を **同じジョブの同じステップ内で能動的に呼ぶだけ** であり、`pull_request` イベントの発火を待つ受動的な仕組みではない。したがって「PR 作成 → 機械チェック → 同じ job 内で `gh pr merge --squash`」という 1 本の workflow は GITHUB_TOKEN のイベント抑制と無関係に動く。**deploy_gate の設計案（自動 PR + 同一ワークフローでの自動マージ）は技術的に妥当**。

必要な `permissions:` は round 1 の #3 のとおり最低限:
```yaml
permissions:
  contents: write        # push・マージ
  pull-requests: write   # PR 作成・マージ
```

**ただし deploy_gate に 1 点、伝えていなかった落とし穴がある（ブランチ保護との相互作用・追加確認済み）**:
GitHub には「Actions が生成した GITHUB_TOKEN で PR を承認できてしまう」ことを悪用したブランチ保護バイパスの既知パターンがあり、これに対する防御機能が存在する。
- Organization/Repository 設定に **「Allow GitHub Actions to create and approve pull requests」** というスイッチがあり、既定でこれが無効な組織では **GITHUB_TOKEN で作成した PR を GITHUB_TOKEN 自身が承認できない**。
- さらにブランチ保護に **「Require approval of the most recent reviewable push」** を有効化している場合、「直近の push をした主体 ≠ 承認者」が強制されるため、**PR 作成者とマージ実行者が同じ GITHUB_TOKEN だと承認要件を満たせず詰む** 構成になりうる。

**本リポジトリへの影響（要確認事項として deploy_gate/lead に申し送り）**: 本 Issue の設計は「レビュー承認（approve）」を経由せず、**squash マージを直接 API で叩く** 方式なので、上記の「approve できない」制約そのものには引っかからない可能性が高い（GitHub の必須レビュー数が 0 に設定されていれば approve は不要でマージ API が素通りする）。ただし **本リポジトリの `main` に GitHub 側のブランチ保護ルール（必須レビュー数・必須ステータスチェック）が実際に設定されているかどうかは、この議論の中の誰も一次情報で確認していない**（Claude セッションは `mcp__github__merge_pull_request` で日常的に自己マージしているので、少なくとも「レビュー必須」は設定されていない可能性が高いが、これは推測であり確認事項として残す)。**実装 Issue の Done Criteria に「対象リポジトリのブランチ保護設定を `mcp__github__` 系ツールか GitHub UI で 1 回確認する」を入れることを推奨する**。

---

### 2. 🔴 Workers Builds への影響 — `deploy_gate` の推論に **同意（concession)**。ただし一次情報では依然「未確認」

deploy_gate の round 1 主張:
> 「GITHUB_TOKEN で作られた push/PR は他の Actions ワークフローをトリガーしない」という GitHub の制約は Workers Builds には影響しない（Actions workflow_run 連鎖の話であって、外部 GitHub App の webhook 購読とは別軸）

これは round 1 で私が示した理解（community discussion ベース）と同じ結論であり、**追加で 2 本 WebSearch した限りでも矛盾する情報は出てこなかった**。具体的には:
- GitHub 公式ドキュメントの「GITHUB_TOKEN は他 workflow を起動しない」の記述は、対象を一貫して **「a new workflow run」**（= Actions の実行）に限定しており、「リポジトリに他の GitHub App がインストールされている場合の webhook 配信」には一言も触れていない（round 1 で確認済み・再確認せず）。
- Cloudflare 側のドキュメント（`developers.cloudflare.com/workers/ci-cd/external-cicd/github-actions/` 等）を今回検索したが、**Workers Builds のネイティブ Git 連携が GITHUB_TOKEN 由来の push を区別するかどうかに触れた記述は見つからなかった**（`wrangler-action` を使う「Actions 経由でデプロイする」方式のドキュメントはヒットしたが、これは本設計と無関係な別方式）。

**結論**: 「Workers Builds は Actions の workflow-trigger 抑制の対象外である」という deploy_gate の推論は **理屈としては筋が通っており、私も同意する（concede）**。しかし **Cloudflare 公式ドキュメントによる一次情報の裏付けは、この議論全体を通じてまだ誰も取れていない**。

**実装前の検証手順（未確認のまま進めないための具体策・争点 D の Done Criteria に追加すべき）**:
1. Gem digest ワークフローを `workflow_dispatch` で 1 回手動起動する（round 1 #7 の `inputs` で `--dry-run` を渡せるようにしておけば安全に試せる）。
2. 実データで 1 回だけ PR 作成 → 同一 job で squash マージまで通す（本番相当の 1 回）。
3. マージ直後、Cloudflare 側のダッシュボード or `mcp__Cloudflare_Developer_Platform__workers_list` 等で **新しいビルドが実際にキューされたか** を確認する。
4. トリガーされていなければ、Workers Builds は GITHUB_TOKEN 発の push を無視している疑いが濃厚 → `trigger_workers_build.py`（PR #460・lead 追加事実 2）が持つ「ゲート通過後の再トリガー」経路を **Gem digest PR のマージ後にも明示的に呼ぶ** フォールバックが必須になる。
この 1 往復さえ実施すれば「未確認」が「確認済み」に変わる。**本 Issue のスコープ内で十分に実施可能な検証** であり、別 Issue に切り出す必要はない。

---

### 3. `batch_ops` の週次推奨（`0 21 * * 0` UTC = 月曜 06:00 JST）について — Actions 側制約とは **矛盾しない**。ただし 1 点リスクを追加する

round 1 で確認した Actions 側の制約と週次推奨を突き合わせる:

- **UTC 表記**: `0 21 * * 0` は UTC 日曜 21:00 = JST 月曜 06:00 で合っている（cron は UTC 基準という round 1 の確認と整合）。
- **毎時 0 分の混雑**: 週次であっても `21:00`（UTC の毎時 0 分）に固定しているため、round 1 で挙げた「高負荷時は分単位でずれる／ドロップされうる」リスクはそのまま残る。**分をわずかにずらす（例 `17 21 * * 0`）ことを推奨**（頻度を下げても「ちょうど 0 分」を避けるコストはゼロなので、直す理由がある）。
- **60 日無活動での自動停止**: 週次実行（52 回/年）自体は「リポジトリの活動」としてカウントされる対象ではない（fact: 判定条件は「リポジトリの活動」であり、schedule workflow 自身の実行が activity としてカウントされるかは round 1 で確認できていない・未確認のまま）。ただし本プロジェクトは PR マージが常時走っている（fact 3〜4 の並行 PR、`session-sprint-rules` の稼働実績）ため、**60 日間 commit が無い状態は現実的にまず起こらない**。週次頻度を理由にこの停止条件を心配する必要はない。
- **⚠️ 追加すべきリスク（round 1 では触れていなかった点）**: 週次のように **実行頻度が低い schedule は、1 回のドロップ（round 1 #2 の "some queued jobs may be dropped"）が与える影響が日次より大きい**。日次でドロップされても翌日に追いつくが、週次でドロップされると **鮮度劣化が最大 2 週間分に伸びる**。`batch_ops` の週次案自体には反対しないが、**「実行されたはずの週に実際に実行されたか」を検知する仕組み**（例: 直近の `index.json` の `generatedAt` が想定より 10 日以上古ければ `[gem-pool-stale]` Issue を起票する定期チェック、または既存の `sprint-cycle-router` の巡回に軽い鮮度チェックを 1 行足す）を D-28 の SPOF 方針（「鮮度のみ劣化させる」を"検知可能な形で"劣化させる）に沿って争点 D に加えることを提案する。

---
以上、post 済み。deploy_gate の設計（自動マージ）は成立を確認（ブランチ保護の一次確認だけ Done Criteria に追加を推奨）。Workers Builds への非影響は concede するが一次情報未確認のため実装前検証手順を明示。batch_ops の週次案は妥当だが、低頻度ゆえの「ドロップ時の鮮度劣化拡大」を新規リスクとして提起。
