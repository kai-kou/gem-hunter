<!--entry
author: classifier_facts
round: 2
kind: rebuttal
ts: 2026-08-21T12:56:58+09:00
-->

## classifier_facts round 2: 必答 3 点への回答

### 1. 🔴 `release_ops` 第 3 案（`deploy-live` ブランチ）を分類器レンズで評価

**結論: 構造的には解決していない。むしろ「ドキュメント化するほどブロックされやすくなる」というジレンマを抱える。**

round 1 で引いた一次情報を再掲する:
> "A non-default branch whose name marks it as a deploy or publication target, such as `production`, `release`, or `gh-pages`, isn't covered by that default: **the classifier judges a push there on its own terms, including as a production deploy.**"

この記述の射程は 2 点重要:
- 例示（`production` / `release` / `gh-pages`）は **"such as"= 例示であって網羅ではない**。判定条件は「ブランチ名が deploy/publication target だと **示している**（marks it as）」ことであり、`deploy-live` は語そのものが deploy を名乗っている以上、**例示より強く該当する**。文字列パターンマッチの話ではなく、classifier が「このブランチへの push は本番デプロイの引き金である」と認識できるかどうかが分岐点。
- classifier は **CLAUDE.md とトランスクリプトの文脈を読む**（`auto-mode-config`: "The classifier reads the same CLAUDE.md content Claude itself loads"）。第 3 案を正式な運用にするなら、`docs/03_design/infrastructure/cloudflare-infrastructure.md` や `pr-review-watcher` SKILL.md に「`deploy-live` への push が Workers Builds 経由で本番デプロイを引き起こす」と **明記する必要がある**（SD-4・ドキュメント整備の要請とも一致）。しかしそれをドキュメント化した瞬間、**classifier 自身がそのドキュメントを読んで「このブランチへの push＝本番デプロイ」と認識する**。つまり、この案を正しく運用しようとすればするほど、classifier からは `npm run deploy` の直接実行と区別がつかなくなる。

**「名前を変えれば回避できるか」への回答**: 一次情報の射程では **No**。前段（decision order の「everything else goes to classifier」＝Bash・push は narrow allow の対象外なら基本 classifier 行き）と、「judges on its own terms, including as a production deploy」という文言は、**行為の実質的効果（production への反映を引き起こすか）を見ている** と読むのが自然で、コマンドの表層（`wrangler deploy` か `git push` か）を切り替えるだけでは、本番反映を引き起こすという事実そのものは変わらない。

**回避目的での命名は L-130 の禁止に触れるか**: 触れる、と考える。もし「classifier に気づかれないよう **意図的に無害な名前**（例: `chore/misc-123`）を選び、かつドキュメントにも本番デプロイの引き金であることを書かない」という設計にすれば、classifier の文脈認識を出し抜ける可能性は残る。しかしこれは L-130 の対策節「回避しようとしてコマンドを分解しない」「分類器のブロックはバグではなく設計された保護であり、迂回は分類器の意図に反する」と **同じ性質の行為**（メカニズムが Bash コマンド分解から git ブランチ命名に変わっただけ）。**意図を隠すために名前を選ぶこと自体を採用しない** べき。

→ したがって第 3 案は「P-1(a) の未検証リスク（Workers Builds ビルド環境で Python/GH API が動くか）を解消する」という `cf_builds`/`release_ops` の主張点では価値があるが、**「classifier のブロックを回避する」効果は一次情報からは保証できない**。第 3 案を採るとしても、classifier に正直にブロックされ得る前提（透明な命名・文書化）で設計し、ブロックされた場合の扱いは `npm run deploy` と同じ行動指針（下記・1 回まで単純リトライ、以降はゲート待機）に従うべき。第 3 案の本質的な利点は「classifier 回避」ではなく「**ゲート判定をセッション側の検証済み環境（Python 実測動作確認済み）に留め、Workers Builds 側の未検証リスクを引き受けなくて済む**」という P-1 の論点に限定される。

### 2. explicit user intent の適用 — `release_ops` の「本セッションではデプロイしない」を支持する

round 1 で引いた一次情報:
> "if the user's message **directly and specifically describes the exact action** Claude is about to take, the classifier allows it... **General requests don't count as explicit intent.**"
> 例: "Asking Claude to 'clean up the repo' doesn't authorize force-pushing"

飼い主の 2 通のメッセージ（①事実確認を求めた質問、②「専門チームを組成して適切に対応してください。ユーザー作業があれば詳細に案内してください」）は、いずれも `npm run deploy` / `wrangler deploy` / 「本番へデプロイして」を **名指ししていない**。②は「適切に対応」という一般的委任であり、`release_ops` が round 1 で引いた "clean up the repo" の例そのものに近い——**explicit user intent の要件を満たさない**。

したがって: **本セッションでの `npm run deploy`（または第 3 案の `git push origin main:deploy-live`）実行は、explicit user intent による soft_deny 解除の対象にならない。** これは `release_ops` の D.1（ゲート待機中につき今回は再試行しない）を **classifier の観点からも二重に支持する** 結論になる——ゲート（`check_deploy_gate.py`）が exit 1 で待てと言っている上に、classifier 側の soft_deny 解除条件（explicit intent）も満たしていないため、たとえ試行して通ったとしても「たまたま通った」以上の正当化がない。

念のため: この結論を変えるために「ユーザーの発言としてデプロイを名指しさせる」ことを誘導する行為（例えば飼い主に確認を装って `npm run deploy` を明示的に言わせる）は、ゲート待機という技術的判断を追認させるためだけの操作になり得るため行うべきではない。今回はゲート判定自体が待機なので、そもそも explicit intent の有無を議論する必要すらない。

### 3. `cf_builds` の「Deploy command が exit 0 でスキップしたときの成否」未確認への評価

支持する。**確認できていない前提でのみ成立する設計を「動くはず」で採用してはならない**——これはこの議論全体が向き合っている問題（L-130 が「必ずブロックされる」と根拠薄弱な断定をしたまま運用ルールを固定化していたのと同じ失敗パターン）の再発になる。CI 一般の通例（最後のコマンドの exit code がステップの成否になる）からの類推は「もっともらしい」だけで一次情報ではない。P-1(a) を最終決定として採用するなら、`cf_builds` が提案した非破壊の検証手段（別 Worker での実地テスト、または Cloudflare サポート/コミュニティでの確認）を **実施してから** 確定すべきで、未検証のまま本番 Worker の Deploy command に組み込むのは、確認できたことと確認できなかったことを混同する行為になる。第 3 案（release-ops 提案）を採るならこの未確認事項自体が P-1(a) 側にのみ残るリスクとして切り離され、今回の意思決定を急がせる要因にはならない。

---
post 済み。要点: (1) `deploy-live` ブランチ案は classifier の「deploy/publication target と分かるブランチは push も本番デプロイとして独自判定される」という一次情報に照らし、ドキュメント化するほど検知されやすくなるジレンマがあり、classifier 回避を目的とした命名は L-130 の迂回禁止に抵触する。(2) 飼い主の 2 通の指示はどちらも explicit user intent の要件（具体的行為の名指し）を満たさず、`release_ops` の「本セッションではデプロイしない」結論を classifier 観点からも支持。(3) `cf_builds` の exit code 未確認事項は、検証なしで P-1(a) に採用すべきでないという立場を支持。
