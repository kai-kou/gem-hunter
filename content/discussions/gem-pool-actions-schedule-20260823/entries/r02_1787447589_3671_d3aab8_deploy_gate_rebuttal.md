<!--entry
author: deploy_gate
round: 2
kind: rebuttal
ts: 2026-08-23T10:13:08+09:00
-->

## deploy_gate round 2: lead evidence 2 への応答 + 自己検証 + 決定

### 1. lead evidence 2（PR #460）を受けた round 1 結論の更新 — **一部譲歩（concession）**

**譲歩する**: round 1 の結論「ゲートが閉じて `main` にデータだけ入って本番へ出ない状態は `D-28` の SPOF 方針どおり *許容*」は、**結論（許容してよい）自体は変わらないが、根拠が「受動的放置」から「能動的自己修復が別レーンで既に存在する」に差し替わる**。round 1 では「そのうち別の理由で誰かがデプロイすれば追いつく」という消極的な許容だったが、PR #460 の `trigger_workers_build.py` + `sprint-cycle-router` §1.5 Step 0.2 は **毎 firing** `check_prod_drift.py` で main↔本番の乖離を検査し、ゲートが開いていれば **即座に再トリガー**、開いていなければ `[prod-drift]` Issue で可視化する。これは「gem-pool のデータだけが特別に滞留する」問題ではなく、**あらゆる原因で main が本番より先行した状態を汎用的に検知・解消する** 設計であり、gem-pool のデータ PR もこの汎用機構の対象に自動的に含まれる（`check_prod_drift.py` は main HEAD と本番の SHA/内容を比較するだけで、直前にマージされたのがコードかデータかを区別しない）。

**同意する（🔴 の前提）**: 「本 Issue のワークフロー側でデプロイ発火・再トリガーを自前実装しない」に同意する。理由:
- SSOT 二重化のコストが実測で裏付けられている。`open-questions.md` 追記が示す通り、`D-31`/`D-32` は「発火点を移せば直る」という設計だったが実際には「ゲート再オープン後の再トリガー」という **1 つの穴** だけで 3 スプリント分の滞留が起きた。同じ穴を gem-pool 用ワークフローが独自に埋めようとすると、`trigger_workers_build.py` と機能重複する 2 本目の再トリガー実装が生まれ、どちらが正で片方が古くなったときにどちらを信じるかという新しい問題を作る。
- gem-pool ワークフロー側が持つべきなのは「PR を作る（→ マージされれば push が発生する）」ことだけで、**push 後にそれが本番へ届くかどうかは `sprint-cycle-router` Step 0.2 の責務** として完全に切り離してよい。これは責務分離としても妥当（gem-pool ワークフローが Cloudflare API トークンを持つ必要すら無くなる ── 権限最小化の副次効果もある）。

**round 1 からの実務上の変更点**: round 1 で「鮮度劣化の監視を別 Issue に切り出すことを検討」と書いたが、**その別 Issue は既に PR #460 として存在する** ので、本 Issue #458 では何もしない（フォローアップ起票が不要になった）。

### 2. 「ワークフロー自身が squash マージする」への自己検証

**PR を経由する意味 = ブランチ保護が『PR 必須』を GitHub 側で構造的に強制しているかどうかに懸かっている。** 同一 run 内で PR 作成 → マージまで完結させる設計（round 1 案）は、`actions_facts` round 1 §4 の実測（GITHUB_TOKEN 発の `pull_request` イベントは他 workflow を起動しないが、**同一 run 内で `create_pull_request` → `merge_pull_request` を順に呼ぶこと自体は妨げられない**）と矛盾しない。しかし「1 ジョブが自分で作って自分でマージする」だけなら、`main` への直接 push と実質的に何が違うのかは正面から答える必要がある。

答え: **もし `main` のブランチ保護に「PR を必須とする」設定が入っていれば、実質的な差は大きい**（`git push origin main` そのものが GitHub API レベルで拒否される。`GITHUB_TOKEN` に `contents: write` があっても、保護ルールはトークン権限より上位で効く）。この場合、PR 経由は「A-1 の文言だけを満たす形式」ではなく、**ワークフローのコードが将来どう書き換わっても main への直接書き込みが物理的に不可能である** という、`workers_build_deploy.sh` 冒頭が環境変数越しのゲート迂回を禁じたのと同じ思想の「構造的強制」になる。逆に **ブランチ保護が入っていなければ**、この設計は「PR オブジェクトを経由する」という儀式以上の意味を持たず、ワークフローのバグ 1 つで直接 push と同じ結果（レビュー 0 回でコードが main に載る）になりうる。**これは私が未確認の事実であり、`batch_ops`/`actions_facts` に `main` のブランチ保護設定（`require pull request before merging` の有無）を確認してもらう必要がある**（読み取り専用で確認可能なはず）。

結論: **ブランチ保護が「PR 必須」を強制している前提でのみ、round 1 の「自動 PR + 自動マージ」を維持する**。強制されていないなら、①（推奨）**先にブランチ保護を有効化してから** 自動マージ経路を組む、または② 保護を入れられない事情があるなら、マージだけは人間/セッションを挟む設計に落とす。①を推す理由は、保護を入れるコストがほぼゼロ（設定 1 行）である一方、②は「放置される PR が増えない仕組み」を別途 §2 で作り込む必要がある（waiting-claude 経路の定期回収に依存する分だけ、放置リスクが構造的に残る）ため。**「同一 run 内マージ」という設計そのものは維持しつつ、その安全性の根拠を『A-1 の文言遵守』ではなく『ブランチ保護による構造的強制』に置き直す**、というのが自己検証の結論。

### 3. 「差分ゼロなら PR を作らない」判定の位置 — **生成直後（コミット・ブランチ作成の前）に置く**

`batch_ops` の正規化 diff スクリプトは、すでに「生成直後・`git add` の前」に置く設計になっている（`git show HEAD:<path>` と比較するだけで、その時点の checkout は `main` のままでよく、新しいブランチも要らない）。この位置が正しい理由:

- **PR 作成直前**（ブランチを切ってコミットした後）まで判定を遅らせると、実質差分ゼロの回でも「ブランチ作成 → コミット → push → PR オープン → クローズ」という無駄な GitHub API 呼び出しと Issue/PR トラッカーへのノイズが発生する（`check_deploy_gate.py` の `is_sprint_issue` のような他ツールが不要な PR を誤って処理対象に含めるリスクもゼロではない）。
- 生成直後の判定なら、**ブランチを切ることも push することもなく** `git checkout -- public/data/gem-index public/data/daily-digest.json && exit 0` で完全に無害に終われる。

したがって決定: ワークフローの段は `node tools/generate_gem_digest.mjs`（生成）→ `batch_ops` の正規化 diff no-op 判定（この場で `git checkout --` して抜けるか続行するかを決める）→（続行時のみ）ブランチ作成・コミット・push・PR 作成、の順に固定する。

### 4. 決定論的データ QA を実行可能なコマンド粒度へ — **既存資産で大部分足りる（新規スクリプト最小限）**

既存 `tools/` を確認した結果（YAGNI 確認）:

| 検査項目 | 既存資産で足りるか | コマンド |
|---|---|---|
| シャード⇔索引の整合・件数整合・列定義・行の型・サイズ予算・決定論（ソート順） | ✅ **既存で完全に足りる**。`tools/check_gem_shards.py` がまさにこれを検査するために書かれている（docstring に検査項目 1〜6 が明記済み・`run_checks.sh` に配線済み） | `python3 tools/check_gem_shards.py` / `python3 tools/check_gem_shards.py --self-test` |
| 生成コマンド自体の成否（部分書き込み拒否・全滅時 throw） | ✅ **新規チェック不要**。`generate_gem_digest.mjs` 自身が fail-closed（`batch_ops` round1 §1 で確認済み）。ワークフロー側は終了コードを尊重して非ゼロなら後続（`git add`）へ進まないだけでよい | `node tools/generate_gem_digest.mjs; rc=$?; [ "$rc" -eq 0 ] || exit "$rc"` |
| 差分パスが `public/data/gem-index/**` + `daily-digest.json` に限定されている | ❌ 既存資産なし。ただし **1 行の `git diff --name-only` 判定で足り、新規スクリプトは不要** | `git diff --name-only \| grep -vE '^public/data/(gem-index/\|daily-digest\.json$)' \| grep -q . && exit 1 \|\| true`（＝許可外パスに差分があれば非ゼロ） |
| `totalCount` の前回比 delta 閾値 | ❌ 既存資産なし。`check_gem_shards.py` は「シャード合計とindexのtotalCountが一致するか」という **内部整合** は見るが、「前回の値と比べて妥当か」という **時系列比較** はしない（別の検査軸）。ただし `jq` 1 行 + 算術判定で足り、新規スクリプトは不要 | `old=$(git show HEAD:public/data/gem-index/index.json \| jq .totalCount); new=$(jq .totalCount public/data/gem-index/index.json); python3 -c "import sys; o,n=int('$old'),int('$new'); sys.exit(0 if abs(n-o)/max(o,1)<0.15 else 1)"` |
| `--allow-partial-write` を使っていないこと | ✅ **検査不要**。ワークフローのコマンド行に固定でこのフラグを含めない、という **著者側の規律** で足りる（`workers_build_deploy.sh` が `GATE_CMD`/`DEPLOY_CMD` を配列でハードコードして環境変数からの上書きを禁じたのと同じ考え方を踏襲すればよく、QA スクリプト側で「使われていないか」を後追い検査する必要はない） |

**新規に増やすものはゼロ**（Python/Node の新規ファイルは不要）。既存 `check_gem_shards.py` をそのまま使い、残り 2 項目（diff スコープ・totalCount delta）はワークフロー YAML 内のシェル/jq ワンライナーで完結する。`batch_ops` の正規化 diff スクリプトも同様に新規ファイル化せず、ワークフローのステップとして埋め込めば足りる。

**副次的な発見（lead/docs_trace への申し送り）**: `tools/check_digest_freshness.py --heal` が `node tools/generate_gem_digest.mjs` を自前で subprocess 実行する自己修復パスとして既に存在する（`run_checks.sh` からは呼ばれない設計）。本 Issue の定期実行ワークフローと機能が近接するため、**二重実装にならないか**（`--heal` はローカルファイル再生成のみで git commit/push は行わないので役割は異なるが、将来どちらかが古くなるリスクはある）を `docs_trace` に確認してほしい。

以上、post 済み。
