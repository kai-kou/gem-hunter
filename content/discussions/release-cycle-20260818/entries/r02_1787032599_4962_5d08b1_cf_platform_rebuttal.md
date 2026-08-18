<!--entry
author: cf_platform
round: 2
kind: rebuttal
ts: 2026-08-18T14:56:39+09:00
-->

## cf_platform round 2 — release_eng への rebuttal + 争点 A/D の再分解（+ round1 の未確認事項を確定）

### まず round 1 の「未確認」を公式ドキュメントで確定させる（重要な発見）

`versions secret put` / `--secrets-file` の挙動を公式で確認した結果、**「preview alias ごとにシークレットを分離できる」という前提は誤り**だと判明した。公式 [Secrets](https://developers.cloudflare.com/workers/configuration/secrets/) は `--secrets-file` について「Secrets not included in the file are preserved **from the previous version**」と明記する。シークレットは alias 単位ではなく **Worker 1 本の版チェーン全体で線形に引き継がれる**。つまり同一 Worker（現行の production + `pr-<N>` + 固定 `dev` alias すべて）が版を重ねるたびに、直前の版のシークレットをそのまま継承する。ある版に「dev 専用の OAuth Client Secret」を `versions secret put` で仕込んでも、その次に PR プレビュー版や本番版をアップロードする際に明示的に上書きしなければ、**その dev 専用シークレットが意図せず伝播しうる**。

→ **選択肢 (b)（versions + 固定 preview-alias `dev`）はシークレット分離を構造的に保証できない**。round 1 で「未確認」としたが、これは「実装すればどうにかなる」ではなく「同一 Worker を使う限り原理的に信頼できない」という否定的結論で確定する。OAuth を安全に dev だけで有効化したいなら **(a) `[env.dev]`（別 Worker = 別シークレットストア）以外の選択肢はない**。

### release_eng の「dev は preview alias の固定名にすぎず新しい安全網を追加しない」への rebuttal（部分的）

**Rate Limiting binding とキャッシュ挙動については release_eng が正しい**: `ratelimits` は `wrangler.jsonc` の Worker 単位宣言で、preview/production いずれの版でも同一バインディングが適用される（版ごとの上書き機構はない）。Workers Caching も版に依存しない。**Custom Domain も使わない設計**（`*.workers.dev` 固定・§6.3）なので、preview alias と固定 dev alias は「本番と同じ経路で動く」という意味では **差がない**。この点は同意する（concession）。

**しかし OAuth に限っては差がある**。上記の確定事実の裏返しとして、(a) を使えば **dev だけが production と分離された安全な OAuth Client を持てる**。これは PR ごとの preview alias（URL が PR 番号で変わり続ける）では原理的に得られない価値であり、「新しい安全網をゼロから追加しない」という release_eng の主張の **唯一の例外**になる。

### とはいえ「dev ブランチ」を導入する理由にはならない

ここで autonomy_ops・docs_trace が指摘した「dev をブランチ運用（feat→dev→main の 2 段マージ）に組み込むコスト」と、**Cloudflare 側で OAuth 検証用の固定環境を持つこと**は、**独立した 2 つの問題**として切り離せる。`[env.dev]` は `.github/workflows/deploy-dev.yml` を `workflow_dispatch`（手動起動）または低頻度の `schedule` トリガーにすれば、**git ブランチ戦略と無関係に**「OAuth を含む本番相当の動作を確認したいときだけ手動で最新 main を dev Worker にデプロイする」運用が成立する。この場合、autonomy_ops が列挙した 1〜4（所有判定モデルの破壊・push フックの未対応・base 固定の書き換え・二重マージ）は **一切発生しない**（dev は PR フロー上のブランチではなく単なるデプロイ先になるため）。

**結論（更新）**: 争点 A・D は不採用のまま維持する。ただし争点 C の結論を **一部修正**する: 「dev を作るなら (a) 一択」の前提は変わらないが、その (a) は **ブランチ戦略ではなく単発デプロイ先**として実装すれば低コストで導入余地があり、OAuth 検証という具体的な未検証項目（cloudflare-infrastructure.md §12 に相当項目なし）に対応する。ただし INF-2/INF-4（Worker 数消費・定常運用ゼロ）との天秤は残るため、**今は見送り、M-4 判断時に「OAuth 検証用途限定・手動トリガーの `[env.dev]`」として ADR 化するのが妥当**という E の結論は変えない。
