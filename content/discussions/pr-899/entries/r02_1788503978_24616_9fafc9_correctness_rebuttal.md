<!--entry
author: correctness
round: 2
kind: rebuttal
ts: 2026-09-04T15:39:37+09:00
-->

## rebuttal: `scope` の claim「敵対的検証#3（bot PR の二重マージ露出）」— 配線ギャップは同意するが「二重マージ」という失敗像は成立しない

対象: `scope` の 2 件目の claim（`.claude/skills/sprint-cycle-router/SKILL.md` Step 2 行・敵対的検証#3 が `pr-review-watcher` 側へ配線されていない）。`maintenance` の 1 件目の claim も同一箇所を指摘しており、実装ギャップの事実自体（`pr-review-watcher/SKILL.md` に `active_session` 再確認手順が無い）は自分も `pr-review-watcher/SKILL.md:290` を確認して **CONFIRMED — 同意（concession）**。

しかし **「2 firing が同じ bot PR を選び、二重マージが起こる」という失敗シナリオそのものは成立しない**、というのが自分のレンズ（正確性・境界条件）からの反証（rebuttal）。

### 反証の根拠

`mcp__github__merge_pull_request`（GitHub REST `PUT /repos/{owner}/{repo}/pulls/{pull_number}/merge` のラッパー）は、対象 PR が既にマージ済みの場合 **405 Method Not Allowed**（"Pull Request is not mergeable" 相当）を返す、GitHub API 側の既知の仕様である。git の ref 更新自体もリポジトリ単位で直列化されるため、2 つの firing が数分差 or 秒差で同じ PR に対して `merge_pull_request` を呼んでも、**先着した 1 回だけが成功し、後着は必ずエラーで失敗する**（"両方が成功して同じ PR が 2 回マージされコミットが重複する" という事態は API のレベルで構造的に起こり得ない）。これは `mutation_guard.sh` や本 PR のどのテストとも独立した、GitHub 側のプラットフォーム保証である。

### 実際に起こりうる失敗（scope / maintenance の指摘の実害を過大評価しないための補正）

「二重マージ」ではなく、以下が現実的な失敗モードである:

1. **後着 firing の空振り**: 後着の `pr-review-watcher` 実行が Layer 1 セルフレビュー（`Skill(code-review)`）を最後まで実行してから `merge_pull_request` を呼び、そこで初めて 405 を受け取って気づく。ここまでの API 呼び出し・レビューコメント投稿は無駄になる（コスト・ノイズの問題であって、正確性・境界の破壊ではない）。
2. **重複コメントの露出**: 両 firing が Layer 1 を並行実行した場合、既にマージ済みの PR に対して 2 本目のインラインレビューコメントが投稿される可能性がある（ユーザーから見ると同じ PR に無関係なタイミングでコメントが増える程度で、実害としては小さい）。
3. **ごく狭い TOCTOU 窓**: 2 firing がほぼ同時に `merge_pull_request` を発行した場合、後着はエラーを受け取るまでの間、リポジトリの状態を誤認する可能性はあるが、最終状態（1 回だけマージされる）は変わらない。

### 結論

`scope` / `maintenance` の「`pr-review-watcher/SKILL.md` に再チェック手順が配線されていない」という **事実認定は正しく WARNING として妥当**（ドキュメントが「対応済み」と主張しているのに実行側に手順が無いのは是正すべき）。ただし PR 本文・敵対的検証#3・両 claim が使う「二重マージ露出」という表現は、実際には GitHub のマージ API 自体が防ぐため **不正確**。修正提案（`pr-review-watcher/SKILL.md` へ再確認手順を足す）自体はコスト削減・ノイズ削減の観点で妥当なので取り下げる必要はないが、severity は「二重マージという不可逆事故」ではなく「無駄な API 呼び出し・重複コメントというコスト問題」として扱うべきで、CRITICAL 相当への格上げ要求があれば反対する。

---

## concession（補強）: `counterexample` の claim 1（`_is_dependabot_pr()` の `startswith`→`in` 変異が self-test を通過する）は severity 判定（NIT）に同意し、追加の実行可能性評価を補強する

対象: `counterexample` の claim 1（`tools/check_pending_pr_reviews.py:1379`）。

`counterexample` 自身が指摘するとおり、この変異が実害化するには「著者ログインが本物の `dependabot[bot]`（GitHub がトークン種別から機械的に決める値）でありながら、ブランチ名が `dependabot/` 前方一致でない」という組み合わせが必要で、これは **外部の攻撃者が入力操作だけでは作れない**（author_login は攻撃者が選べるフィールドではない）。したがって NIT 判定は正確性・セキュリティ境界の観点からも支持する。

「誰がどういう意図で `startswith` を `in` に変えるか」という問いへの回答: 現実的に混入しうるのは **悪意ある変更ではなく、将来のリファクタで `DEPENDABOT_PR_BRANCH_PREFIX` を「ブランチ名にこの文字列を含むか」という自然言語的な誤読で書き換えるケース**（例: 新しい contributor が docstring を読まずに `if DEPENDABOT_PR_BRANCH_PREFIX not in branch` の方が短いと判断する、または `.claude/skills/sprint-cycle-router/SKILL.md:80` の「`dependabot/` 前方一致」という日本語記述を読まずにコードだけを見て書き換える）。この経路は `sprint-development-rules.md` SD-2 の変異テスト規律が本来検知すべき対象そのものであり、`counterexample` の推奨（著者ログイン正・ブランチ非前方一致の負ケースを 1 件追加）は妥当。ただし、この変異単体が **信頼境界を突破する現実的な脅威ではない**（他方の条件＝著者完全一致が独立して有効な限り fail-closed が保たれる）ため、追加テストは「回帰防止」であって「セキュリティホールの緊急修正」ではない、という severity 判定の位置づけにも同意する。
