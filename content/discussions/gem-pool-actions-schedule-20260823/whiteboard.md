<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: Gem 候補プール再生成を GitHub Actions で定期実行する設計（Issue #458）

- 議題ID: `gem-pool-actions-schedule-20260823`
- 論点: 飼い主の指示（原文）: 『リポジトリをパブリック化したことで、GitHub Actionsの利用制限が解除されました。本セッションでIssue作成して定期的に実行されるように専門チームを組成して対応してください』

【オーケストレーターが本セッションで実測・確認した事実（推測ではない）】

1. Issue #458 を起票済み（type:improvement / status:in-progress / sp:5）。

2. バッチの実体は `node tools/generate_gem_digest.mjs`（Node 22+ / ESM）。CLI 冒頭の docstring に処理段が書かれている: 収集 collectAll（12 レジストリ × 被依存数降順 15,000 件）→ 整形 projectPackage → 順位 buildPool（汚染フィルタ + repo 単位 dedupe + レジストリ別再ランク）→ 出力 output.*。既定実行で **約 10 分・180 リクエスト**。オプション: `--dry-run` / `--registries` / `--quota` / `--allow-partial-write`。⚠️ 部分実行 + `--allow-partial-write` は **孤児シャードを削除する**。

3. 🔴 同 CLI の冒頭に『⚠️ CI での自動実行はしない（更新は `D-28` どおり Cloudflare の外で回して git commit → デプロイ）』と明記されている。これは Actions が使えなかった時期の制約に由来する記述であり、本 Issue で実態に合わせて直す対象。

4. 生成物は `public/data/gem-index/*.json`（12 シャード）+ `public/data/gem-index/index.json` + `public/data/daily-digest.json`。**合計 3.6MB**。git 追跡済み（`.gitignore` されていない）。過去にこのディレクトリを変更したコミットは 2 つだけ（6488e01 / 74ea0b4）。現行 `index.json` の `generatedAt` は **2026-08-22 15:04 JST**、`totalCount` 62,483。

5. 反映経路の制約: 🔴 `main` への直接 push は本プロジェクトの既約境界外 **A-1**（`docs/rules/user-confirmation-minimization.md` §1）。PR 経由・自動マージのみ。

6. 本番デプロイは **Workers Builds**（Cloudflare native の Git 連携・`D-31` / `D-32`）が main への push をトリガーに動き、Deploy command が `tools/workers_build_deploy.sh` を呼ぶ。同スクリプトは `tools/check_deploy_gate.py` を実行し、**ゲートが閉じているときは非ゼロで終了する（fail-closed）**。`check_deploy_gate.py --json` の終了コードは 0=デプロイ可 / 1=待機 / 2=判定不能。判定は『open かつ status:in-progress の Issue のうち、タイトルに SP-\d+ を含むか本文コメントに `## 🏃 Session Sprint Planning` があるもの』をスプリント対象とし、`## 🔍 Sprint Review 判定` の `**結果**:` 行の最新値で決まる。

7. `D-28`（`docs/02_requirements/open-questions.md`）: バッチ集計は **Cloudflare の外** で回し、生成した静的 JSON を git commit → デプロイで Static Assets として丸ごと差し替える。SPOF（バッチ停止時に更新が止まる）は無害化 + 検知して自己修復で対処し、**配信自体は止めず鮮度のみ劣化させる**。

8. `docs/rules/pr-review-flow-summary.md` に『🔴 GitHub Actions は制限中で使えない（ジョブが数秒・ログ 0 バイトで失敗）。ワークフロー 2 本は撤去済み』とあり、`docs/rules/harness-escalation.md` / `docs/rules/lessons-management.md` にも Actions を運用に使わない旨の記述がある。`.github/workflows/` は現在 **存在しない**。

9. Gem Index は母集団依存の相対指標であり、再生成のたびに **全銘柄の値が変わりうる**（`src/domain/model/gem-index.ts` の JSDoc が明示）。日次ダイジェストの日替わりは date シードによる選定であって、値の再計算ではない。

【この議論で決めること（争点）】

A. 🔴 **実行間隔（cron 式まで確定させる）**。判断材料: Ecosyste.ms 側のデータ更新頻度と本バッチの負荷（180 リクエスト・10 分）、Gem Index が相対指標であること（頻繁に回すと同じリポジトリのバッジが付いたり消えたりする）、3.6MB の生成物を毎回コミットすることによる git 履歴の増加、Actions の無料枠（パブリックリポジトリでの扱いを一次情報で確認すること）。**『毎日』『毎週』を感覚で選ばず、上記のどれが効いて何時（JST）に回すのかまで書くこと**。schedule cron は UTC で書く点に注意。

B. 🔴 **生成物の反映経路**。`main` 直 push は A-1 で不可。PR を自動作成する場合: どのアクション/コマンドで作るか（サードパーティアクションの是非も含む）、GITHUB_TOKEN の permissions は何が要るか、**workflow が GITHUB_TOKEN で作った PR は他の workflow をトリガーしない** という GitHub の仕様が本プロジェクトに影響するか、自動マージしてよいか（するなら誰が品質を担保するのか / しないなら誰がいつマージするのか・放置される PR が増えないか）。差分が実質ゼロだった回に空 PR を作らない仕組みも決める。

C. 🔴 **マージ後の Workers Builds デプロイゲートとの整合**。データ PR がマージされたとき `check_deploy_gate.py` は何を返すか（そのとき in-progress のスプリント Issue があれば **待機（exit 1）で fail-closed** になり、データだけ main に入ってデプロイされない状態が生まれないか）。生まれるなら許容するのか、対処するのか。**ゲートを迂回する案は採らない**（`workers_build_deploy.sh` 冒頭が禁じている）。

D. 🔴 **失敗時の扱い**（`D-28` の SPOF 方針に沿うこと）。途中でネットワーク失敗したとき部分的な生成物をコミットしてしまわないか（`--allow-partial-write` の孤児シャード削除に注意）、リトライするか、失敗を誰にどう通知するか（Issue 起票 / Slack / Actions の失敗通知のどれか。既存の `tools/slack_notify.py` を使えるか、シークレットが要るなら誰が設定するのか）、**60 日間コミットが無いとスケジュール実行が自動停止する** GitHub の仕様への対処。

E. 🔴 **更新すべき既存記述の洗い出し**（実ファイルを読んで、パスと節・行の粒度で）。最低限: `tools/generate_gem_digest.mjs` 冒頭コメント、`docs/rules/pr-review-flow-summary.md`、`docs/rules/harness-escalation.md`、`docs/rules/lessons-management.md`、`docs/02_requirements/open-questions.md`（`D-23` / `D-28` / `D-31` / `D-32`）、`docs/03_design/infrastructure/cloudflare-infrastructure.md`、`CLAUDE.md`。**Actions が使えるようになったからといって、飼い主が別途決めた『Actions を品質ゲートには使わない』方針まで勝手に覆さないこと**（本 Issue のスコープはバッチの定期実行に限る。方針変更が要ると判断したら follow_up_issues に落とす）。
- 参加者: `actions_facts`, `batch_ops`, `deploy_gate`, `docs_trace`
- 投稿数: 6
- 更新: 2026-08-23T10:09:12+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

## ラウンド 1

### `lead` — 根拠
<sub>2026-08-23T10:06:54+09:00</sub>

## lead からの追加事実（round 2 の材料・すべて本セッションのツール実出力）

1. **Actions は実際に動いている**（`mcp__github__actions_list`）。`total_count: 219` 件の run があり、直近も success。ただし走っているのは GitHub 管理の **dynamic ワークフロー**（`dynamic/github-code-scanning/codeql`・`dynamic/dependabot/update-graph`・`dynamic/pages/pages-build-deployment`）で、**リポジトリ定義のワークフローではない**。
   - `pages-build-deployment`（2026-08-22 18:53 JST 作成）は `site/` の LP を `gh-pages` で配信している経路。
2. **`repo-checks`（`.github/workflows/repo-checks.yml`）が workflow 一覧に残っている**（id 336593661・state active・作成 2026-08-18 09:47 JST）が、**作業ツリーに `.github/` は存在しない**（撤去済み・`pr-review-flow-summary.md` の記述と一致）。→ 新規ワークフローを足すとき、この残骸の扱い（無視してよいか / 名前衝突しないか）を確認すること。
3. 🔴 **他セッションが並行稼働中**（CP-4）: open PR #456 / #459 / #460 が存在する。とくに **PR #460「Workers Builds をゲート通過後に再トリガーする CLI を追加する（#451）」** は争点 C と直接関係する（ゲートで赤終了した push を、ゲート通過後に main の最新コミットで再トリガーする経路）。
   - `deploy_gate` は round 2 で **この PR の存在を前提に**争点 C を再検討すること（「データ PR がマージされてもゲートが閉じていてデプロイされない」問題に、既に別レーンの解が動いている可能性がある）。
   - 🔴 これらの PR には介入しない（レビュー・マージ・コメントをしない）。

### `batch_ops` — 主張
<sub>2026-08-23T10:07:34+09:00</sub>

## バッチ実行特性レンズ（争点 A・D）— batch_ops

読んだファイル: `tools/generate_gem_digest.mjs` / `tools/gem-pool/collect.mjs` / `tools/gem-pool/pipeline.mjs`（import 一覧のみ確認・npm 依存なしを確認）/ `tools/gem-pool/output.mjs`。追加で `docs/01_research/data/20260822-dependency-data-sources.md`（レート制限の一次実測）を参照。

### 1. 失敗モードと生成物の安全性（争点 D）

コードで確認した実装は **保守的**。壊れた生成物が残るケースは限定的:

- **ネットワーク断・1 レジストリだけ失敗**: `collectAll`（`collect.mjs:349-388`）は 1 レジストリの失敗を `failures[]` に積んで **続行**する（12 レジストリのうち 11 が成功すれば止まらない）。ただし失敗した状態で書き込むと `partial=true` になり、既定では **書き込み自体を拒否**する（`decideOutputWrite`・`generate_gem_digest.mjs:230-264`）。`--allow-partial-write` を付けない限り安全側（exit 1・生成物は更新されない）。
- **全レジストリ失敗**: `main()` が `throw`（`generate_gem_digest.mjs:401-405`）→ 生成物は一切書き込まれず終了コード 1。
- **途中でプロセスが kill される（Actions のタイムアウト・runner 障害等）**: これはコードで守れない領域。`writeJsonFile` は1ファイルずつ `writeFile`（`output.mjs:166-171`）するため、**13 ファイル書き込みの途中でプロセスが落ちると一部シャードだけ新しく一部古いままという不整合が起きうる**（アトミックな全置換ではない）。これはワークフロー側で緩和すべき点で、対処案は「job に十分なタイムアウト（20 分以上）を設定」「失敗時は `git status` で差分ファイルを確認し、部分的な差分だけが出ていたら PR を作らず失敗として通知する」。
- **`--allow-partial-write` の孤児シャード削除**: `removeOrphanShards`（`generate_gem_digest.mjs:485-497`）は「今回書いたファイル」に含まれないシャードを **物理削除**する。定期実行では **`--allow-partial-write` を絶対に付けない**（部分実行時は書き込み拒否・exit 1 のまま失敗させ、次回実行に委ねる）。これは D-28 の「配信は止めず鮮度のみ劣化させる」と整合する（前回の生成物が残り続ける）。
- **総括**: 定期実行のワークフローが守るべき鉄則は1つだけ — **`generate_gem_digest.mjs` の終了コードをそのまま尊重し、非ゼロ終了なら `git add` すら行わない**（コードが安全側に倒す設計を、ワークフロー側で上書きしない）。

### 2. 冪等性（争点 A 材料）

**実質差分ゼロでもコミットが生える要素が3箇所ある**（すべて `meta.generatedAt`、`output.mjs:55-57` の `buildMeta`）:

- 12 レジストリシャード each の `doc.meta.generatedAt`
- `index.json` の `meta.generatedAt`
- `daily-digest.json` の `meta.generatedAt`

加えて `daily-digest.json` の最上位 `date`（`output.mjs:103-117`）も実行日ごとに変わる（これは「生成日」であって候補内容ではない）。

**差分判定の具体案**: PR 作成前に、新しく書き出したファイルと `git show HEAD:<path>` の内容を **`meta.generatedAt` と `daily-digest.json` の `date` キーを正規化してから比較**する。

```bash
normalize() { jq '(.meta.generatedAt // empty) |= "X" | (.date // empty) |= "X"' "$1"; }
changed=0
for f in public/data/gem-index/*.json public/data/daily-digest.json; do
  if ! diff <(git show "HEAD:$f" 2>/dev/null | normalize /dev/stdin) <(normalize "$f") >/dev/null 2>&1; then
    changed=1; break
  fi
done
if [ "$changed" = "0" ]; then
  git checkout -- public/data/gem-index public/data/daily-digest.json  # generatedAt/date だけの差分を破棄
  echo "no-op: 実質差分なし。PR を作らない"
fi
```

`entries`（シャード）・`candidates`（digest）・`shards`/`stats`/`totalCount`（index）はいずれも `sortRecords`/ソートキー固定（`output.mjs:81, 174-181`）で **入力が同じなら出力も決定論的**（生成順・Map 順に依存しない）。したがって「実質ゼロ差分」判定は上記の 2 キー除外だけで十分——他に非決定要素はコード上見当たらない。

### 3. Ecosyste.ms への負荷

`collect.mjs` の実装（実測コメント付き・2026-08-22 時点の一次情報）:

- User-Agent に連絡先 URL を明記した **polite pool** で送信（`collect.mjs:22`）→ 上限 **15,000 req/時**。UA を送らない匿名は 5,000 req/時（`docs/01_research/data/20260822-dependency-data-sources.md:32`、実測ヘッダ `x-ratelimit-limit` 基準）。
- リトライは 429 で `retry-after` ヘッダ尊重、無ければ指数バックオフ（`1000 * 2^attempt`ms）、既定 3 回まで（`collect.mjs:132-178`）。認証キーは不要（公開一覧 API・匿名でも動く）。
- 実行 1 回あたり **180 リクエスト**（12 レジストリ × 15 ページ、`per_page=1000`）・約 10 分（`docs/01_research/data/20260822-dependency-data-sources.md:61`）。

**妥当性評価**: 180 req/回は polite pool 上限 15,000 req/時 の **1.2%**、匿名上限 5,000 req/時 でも **3.6%**。よほど頻繁（1 時間に 1 回など）に回さない限り Ecosyste.ms 側のレート制限に抵触する余地はほぼない。負荷の観点では **日次実行でも全く問題にならない規模**。ただし「レート制限に収まる」ことと「回す価値があるか」は別問題（§4 参照）。なお Ecosyste.ms の公式ドキュメント（`docs.ecosyste.ms`・Swagger UI）から更新頻度の明文記載は WebFetch で取得できなかった（JS レンダリング前提のページで空振り）。バルクダンプが 2023-10 → 2026-02 と不定期にしか更新されない一方 API 一覧は都度最新値を返す、という `docs/01_research/data/20260822-dependency-data-sources.md:34` の実測は、**Ecosyste.ms 側の被依存数・star 数自体が API 経由なら準リアルタイムだが、日次で劇的に動く性質の値ではない**（被依存数・star 数は数十件〜数百件規模の緩やかな増減が通常）ことを裏付ける。

### 4. 実行間隔の推奨（理由付き・争点 A の結論案）

**推奨: 週次（毎週月曜 06:00 JST = `0 21 * * 0`・UTC 日曜21:00）**。日次には反対。

根拠（3点、すべてコードから確認した事実に基づく）:

1. **Gem Index は相対指標**（whiteboard fact 9・`src/domain/model/gem-index.ts`）。母集団 62,483 件のランキングが再計算されるたびに、個々のリポジトリの gemIndex・順位は**元データがほぼ動いていなくても再計算のたびに微小に揺れうる**（浮動小数の再ランクは母集団全体の分布に依存する）。日次で回すと「昨日出ていたバッジが今日消えて明日また出る」ようなチラつきが起きやすく、ユーザー体験としては望ましくない。週次なら変化の「意味のある単位」に近づく。
2. **3.6MB を毎回コミットする git 履歴コスト**。過去 2 コミットの実績（fact 4）からも分かる通り、この生成物は「差分の大半が実質同じデータの並び替えバイト列」になりやすい大型 blob。日次 365 回/年 vs 週次 52 回/年で、リポジトリ肥大化速度が 7 倍違う。§2 の実質ゼロ差分スキップを入れても、被依存数はほぼ毎回どこかしら動くため実際にはほぼ毎回コミットが生える（実質ゼロ差分は稀）。
3. **データの実際の変化速度**: 被依存数・star 数は個々のリポジトリでは週〜月単位でしか目に見えて動かない指標（§3 で述べた「緩やかな増減」）。180 リクエストで 10 分かけて日次で追いかけても、得られる鮮度の向上は「今日の Gem」の表示に対してはほぼ知覚できない一方、コストは上記 1・2 で確実に発生する。

補足: **62,483 件から数百件を選ぶ「今日の Gem」候補プール**という用途に照らすと、週次更新でも十分に「新しい発見」を提供できる（母集団が週次でしか動かないなら、日次で回しても同じ顔ぶれが続くだけ）。将来 Ecosyste.ms 側のデータ更新頻度がより高頻度だと分かれば、間隔短縮の余地はあるが、現時点でその根拠は確認できなかった（§3 末尾）。

### 5. Actions ランナー上での実行前提

- **Node バージョン**: `package.json` の `"engines": { "node": ">=22" }` と一致させ、`actions/setup-node@v4` で `node-version: 22`（`cloudflare-infrastructure.md:820` が wrangler 4.x 向けに同じ要件を既に明記——値を揃えられる）。
- **依存インストールの要否**: `tools/gem-pool/*.mjs` の import は `node:fs/promises` / `node:path` / `node:url` などの **Node 組み込みモジュールのみ**（`grep "^import"` で確認・外部 npm パッケージへの依存ゼロ）。したがって **`npm ci` は不要**——`actions/checkout` の直後に `node tools/generate_gem_digest.mjs` を直接叩ける。これは起動オーバーヘッドを大きく削る（依存インストールが要る一般的な Node ワークフローより速い）。
- **実行時間の見積もり**: 実測 **約 10 分**（`docs/01_research/data/20260822-dependency-data-sources.md:61`）。GitHub-hosted runner の既定ジョブタイムアウトは 360 分なので余裕は十分だが、**明示的に `timeout-minutes: 20`** 程度を設定し、ハング時に無駄に枠を消費しないようにすべき（§1 の「途中終了で不整合が起きうる」ケースの検知も兼ねる）。
- **並行実行の排除**: cron トリガーの workflow は `concurrency: { group: gem-pool-regen, cancel-in-progress: false }` を付け、前回実行が長引いた場合に重複起動しないようにする（180 req/回とはいえ、二重実行は Ecosyste.ms への負荷を無意味に倍加させる）。

---
以上、争点 A（週次推奨・理由 3 点）・D（安全側フェイルクローズの確認・部分書き込み拒否を尊重・不整合検知）を中心に投稿。

### `lead` — 根拠
<sub>2026-08-23T10:07:38+09:00</sub>

## lead 追加事実 2: PR #460 の中身（争点 C の前提が変わる・実 diff を確認済み）

`mcp__github__pull_request_read(get_files, pullNumber=460)` の実出力より。**未マージの open PR** だが、争点 C はこの内容を前提に判断すること。

追加・変更されるもの:

1. **`tools/trigger_workers_build.py`（新規 579 行）**: Cloudflare Builds API（`workers/scripts` → `builds/workers/{tag}/triggers` → `POST builds/triggers/{uuid}/builds`）で `main` 最新コミットのビルドを再トリガーする CLI。**内部で `check_deploy_gate.py` を先に実行し、閉じていれば何もせず exit 1**。終了コード 0=トリガー成功 / 1=ゲート待機（異常ではない）/ 2=判定不能（fail-closed）。
2. **`sprint-cycle-router` SKILL.md に §1.5 Step 0.2（本番ドリフト検査）を追加**: 毎 firing・全ブランチより先に `tools/check_prod_drift.py` を実行し、乖離があれば `trigger_workers_build.py` を試行。ゲート待機中なら `[prod-drift]` Issue で可視化する。
3. `open-questions.md` に「`D-31` / `D-32` の決定から従属的に確定する事項」節を追加。実測: **Workers Builds の直近 24 件が全件 `build_outcome: "fail"`**（ゲートで塞がれた）。本番を追いつかせていたのは手動 `npm run deploy` だった。

🔴 **争点 C への含意**: 「データ PR をマージしてもゲートが閉じていて本番へ出ない」問題は、**このレーンが既に解いている**（滞留は Step 0.2 が検知し、ゲートが開いた時点で再トリガーされる）。したがって本 Issue のワークフロー側で **デプロイの発火や再トリガーを自前で実装しない**（SSOT を二重化しない）。`deploy_gate` は round 2 でこの前提に立って結論を出すこと。

🔴 **ファイル衝突の注意（並行作業）**: PR #460 は `.claude/hooks/post-sprint-review-deploy-check.sh` / `.claude/skills/pr-review-watcher/SKILL.md` / `.claude/skills/sprint-cycle-router/SKILL.md` / `docs/02_requirements/open-questions.md` / `docs/03_design/infrastructure/cloudflare-infrastructure.md` / `docs/rules/lessons/cloud-environment.md` / `tools/run_checks.sh` を変更している。`docs_trace` は round 2 で、**本 Issue の変更対象からこれらを外せないか**（外せないなら衝突しない箇所に限定できないか）を検討すること。

### `docs_trace` — 主張
<sub>2026-08-23T10:07:38+09:00</sub>

# ドキュメント整合性分析：GitHub Actions 制約の記述状況

## 変更が必要な記述（Actions 制限中という前提に基づく）

| ファイル | 行番号 | 現在の記述 | 必要な変更の要旨 | 状態 |
|----------|--------|----------|---------------|------|
| `tools/generate_gem_digest.mjs` | 27 | `⚠️ CI での自動実行はしない（更新は D-28 どおり Cloudflare の外で回して git commit → デプロイ）` | 本行は「Actions が使えない」を前提にした制約。Issue #458 の決定（Actions で定期実行）を反映して修正。新規に「Actions の schedule workflow で毎日午前 2 時 JST（UTC 17 時）に実行し、生成物を PR で main へ反映する」等の具体手順へ置き換える | 要変更 |
| `docs/rules/pr-review-flow-summary.md` | 23-25 | 「🔴 GitHub Actions は制限中で使えない（ジョブが数秒・ログ 0 バイトで失敗）。ワークフロー 2 本は撤去済み」「CI という機構自体が現在存在しない前提でこのファイルを読む」 | Gem digest バッチ用 workflow の存在を明記。品質チェック（`npm run check`）と本番デプロイ（`wrangler` → Workers Builds）は「現在 Actions を使わない」と書き続ける（飼い主決定・#298）。バッチの定期実行は「Actions schedule workflow で」と明確に分岐させる | 要変更 |
| `docs/rules/harness-escalation.md` | 11 | 「本ベースは現時点不採用（飼い主決定・2026-07-24・#298）」 | **変更対象外**。飼い主が「品質ゲート」には Actions を使わないと明示的に決めている。本 Issue はバッチの定期実行であり、この方針を覆さない。ただし注記に「ただし Gem digest 定期バッチ（Issue #458）等、スケジュール実行に限定した用途では Actions を採用する」と併記してもよい（オプション） | 変更対象外 |
| `docs/rules/lessons-management.md` | 90 | 「本ベースは GitHub Actions を運用に使わない」「Lv4 CI は既定で設けず」 | **変更対象外**。上記と同方針。ただし §4 の説明に「ただし定期バッチ実行用の schedule workflow は別扱い」と注記を追加してもよい（オプション） | 変更対象外 |
| `docs/02_requirements/open-questions.md` | 333 | D-23: GitHub Actions が制限中のため CI とデプロイをセッション実行へ切り替える（2026-08-19 確定） | **変更対象外**。既に決定済みのドキュメント記録。ただし D-23 に「本決定は品質チェックと本番デプロイに限定される。Gem digest 定期バッチ（Issue #458）等の定期実行はスケジュール workflow で別途実装する」という注釈を追加してもよい（オプション） | 変更対象外だが注釈可 |
| `docs/02_requirements/open-questions.md` | 338 | D-28: バッチ集計は Cloudflare の外で回し、生成した静的 JSON を git commit → デプロイで差し替える（2026-08-20 確定） | **変更対象外**。既に決定済みのドキュメント記録。本決定は「どこで実行するか」（Cloudflare 外）を示しており、「Actions schedule で実行」とも「Routine で実行」とも矛盾しない。実装時に「実行経路は Issue #458 の決定に従う」と Issue コメントで記録すれば足りる | 変更対象外 |
| `docs/02_requirements/open-questions.md` | 342 | D-31: 本番デプロイの発火点を Workers Builds へ移す（2026-08-21 確定） | **変更対象外**。既に決定済み。Gem digest の定期実行と無関係（デプロイ先の基盤選択）。ただし「Gem digest の PR がマージされた場合、ゲート判定（D-32）がどう動くか」は Issue #458 の実装時に明記する必要あり | 変更対象外だが実装時注記 |
| `docs/02_requirements/open-questions.md` | 343 | D-32: Workers Builds へ移行してもデプロイゲートを維持する（2026-08-21 確定） | **変更対象外かつ要注意**。Gem digest PR がマージされるたびに `check_deploy_gate.py` が呼ばれ、「in-progress のスプリント Issue があるか」を判定する。Gem digest は通常業務の外（スプリント独立）なので、`check_deploy_gate.py` のロジックを「スプリント対象か否か」で分岐させるか、Gem digest PR を除外する仕組みが必要になる可能性がある | 変更対象外だが実装時に要検討 |
| `docs/03_design/infrastructure/cloudflare-infrastructure.md` | 52 | 「⚠️ CI/CD は暫定でセッション（Claude）実行」「原則は GitHub Actions + wrangler-action だが、Actions が制限中のため一時的に手動実行へ切り替えている」 | **変更対象外**。品質チェック・デプロイの話。ただし「ただし Gem digest 定期バッチは Actions schedule workflow で実装される（Issue #458）」と注記を追加してもよい | 変更対象外だが注記可 |
| `docs/03_design/infrastructure/cloudflare-infrastructure.md` | 814 | 「復帰条件と手順（GitHub Actions の制限が解除されたら）」| 本セクション全体が「Actions が復帰したときの手順」。Gem digest 定期バッチは既に Actions を採用するので、「バッチの復帰」ではなく「品質チェック・デプロイの復帰手順」と明記してもよい（オプション） | 変更対象外だが明確化推奨 |
| `docs/rules/env-vars.md` | 52 | 「❌ Actions variables/secrets: ... → 403『Access to this GitHub Actions path is not permitted through this proxy.』（MCP にも等価ツールなし・§2.4）」 | **変更対象外**。クラウドセッション内での secrets 管理の話。Gem digest の workflow（GitHub のクラウド実行環境）では secrets の問題にならない。ただし「workflow 内で secrets を使う場合は GitHub のネイティブ secrets 管理を使う」と注記を追加してもよい | 変更対象外 |
| `docs/rules/github-mcp-fallback-patterns.md` | 52 | 「❌ Actions variables/secrets: ... → MCP にも等価ツールなし」「§2.4」 | **変更対象外**。クラウドセッション内での話。workflow 内での secrets 参照（`${{ secrets.CLOUDFLARE_API_TOKEN }}`）はこの制約の外側 | 変更対象外 |

## 変更対象外として除外した理由

飼い主が「GitHub Actions での品質ゲート・本番デプロイ」を不採用と明示的に決めている（Issue #298 / `harness-escalation.md` Lv4）。本 Issue はバッチの定期実行に限定されており、その方針を変更対象としない。

記述を分類すると:
- **変更対象外**: 品質チェック・本番デプロイ CI（`D-23` / `harness-escalation.md` / `cloudflare-infrastructure.md` §7.5-§8）
- **オプション注記**: 既存の決定ドキュメント（`D-23` / `D-28` / `D-31` / `D-32`）に「ただし Gem digest は別扱い」と併記する余地あり
- **実装時に要検討**: `check_deploy_gate.py` との整合（D-32 関連）

## 実装時の追加記述が必要な場所（Issue #458 完了時）

1. `tools/generate_gem_digest.mjs` 冒頭コメント → workflow schedule の手順・実行頻度・PR 作成の自動化方針
2. `.github/workflows/` → 新規 schedule workflow ファイル（またはドキュメント）
3. `docs/02_requirements/open-questions.md` → 実装時の決定ログ（実行経路・失敗時の扱い等・争点 A〜E）
4. `cloudflare-infrastructure.md` → Gem digest 定期実行の位置づけ（CI/CD セクション内）

### `actions_facts` — 主張
<sub>2026-08-23T10:07:48+09:00</sub>

## actions_facts — GitHub Actions 一次情報（Round 1・争点 A / B / D 担当）

すべて WebFetch/WebSearch で docs.github.com を実際に確認した内容にゃ。確認できなかった項目は「未確認」と明記する。推測では埋めない。

### 1. パブリックリポジトリの Actions 無料枠
> "GitHub Actions usage is free for public repositories that use standard GitHub-hosted runners."
（billing/managing-billing-for-github-actions/about-billing-for-github-actions）

- **パブリックリポジトリ + 標準ランナー（`ubuntu-latest` 等）は完全無料・分数上限なし**。プライベートは月 2,000〜3,000 分等の無料枠 + 超過課金だが、本リポジトリは既にパブリック化済みなので無関係。
- ⇒ **争点 A への含意**: 「無料枠の温存」を理由に実行頻度を絞る必要はない。頻度は Ecosyste.ms 側の更新頻度・Gem Index の相対指標特性・3.6MB 生成物のコミット増加の 3 点だけで決めればよい（コスト制約は消える）。

### 2. `schedule`（cron）の仕様
（reference/workflows-and-actions/events-that-trigger-workflows）

- 最短間隔: **"The shortest interval you can run scheduled workflows is once every 5 minutes."**
- タイムゾーン: **"By default, scheduled workflows run in UTC."**（cron 式は UTC 基準で書く。IANA タイムゾーン文字列で明示指定も可）
- 混雑時の遅延・スキップ: **"The `schedule` event can be delayed during periods of high loads of GitHub Actions workflow runs. High load times include the start of every hour. If the load is sufficiently high enough, some queued jobs may be dropped."**
  - ⇒ 争点 A への含意: **毎時 0 分ぴったりの実行は避ける**（`0 * * * *` のような分は混雑と重なりやすい）。本バッチは 10 分かかる重い処理なので、日次 1 回なら JST 深夜〜早朝の毎時 0 分以外（例: 分をずらして `17 * * * *` 相当）を選ぶのが無難。
- **60 日間コミットが無いとスケジュール実行が自動停止する条件**: **"In a public repository, scheduled workflows are automatically disabled when no repository activity has occurred in 60 days."**
  - 「リポジトリの活動（activity）」が条件であり、「ワークフロー自体の実行」ではない点に注意（本文言はコミット等のリポジトリ活動を指す。本プロジェクトは PR マージが頻繁なため通常は問題にならないはずだが、**争点 D で「60 日無活動」を実際に起こしうるか要検討**）。
  - 再有効化・回避策は本ページに記載なし（**未確認**。Actions タブから手動再有効化 or 適当な commit を打つ、が一般的だが一次情報未確認）。
- 補足: **"Scheduled workflows will only run on the default branch."** / **"This event will only trigger a workflow run if the workflow file exists on the default branch."**（`main` にマージ済みのワークフローファイルでないと動かない）

### 3. GITHUB_TOKEN の既定権限・`permissions:`
（actions/security-for-github-actions/security-guides/automatic-token-authentication ほか）

- 一次情報で確定: **"People with admin permissions to an organization or repository can set the default permissions to be either permissive or restricted."** かつ **"Use the `permissions` key in your workflow file to modify permissions for the `GITHUB_TOKEN`"**。
- **2023 年以降、新規作成された個人アカウントのリポジトリでは GITHUB_TOKEN の既定が read-only（contents / packages が read）に変更されている**という情報を複数の二次情報（Arinco ブログ・GitHub Changelog 系）で確認したが、**docs.github.com の該当ページ本文を直接引用した一字一句の確認はできていない**（ページが長大で WebFetch がその節を切り出せなかった）。organization リポジトリの場合は org 設定を継承する。**この点は「未確認（高確度の二次情報のみ）」として扱ってほしい**。
- 実務上の対応は確定: ブランチへの push・PR 作成には最低でも次の `permissions:` が必要（GitHub のサンプルで一般的に使われる組み合わせ。本リポジトリの既定が read-only なら明示指定が必須、permissive でも最小権限の原則で明示すべき）:
  ```yaml
  permissions:
    contents: write        # ブランチへの commit / push
    pull-requests: write   # PR の作成・更新
  ```
  ※ `contents: write` は既定ブランチへの直接 push にも使えてしまう権限だが、本プロジェクトは A-1（main 直 push 禁止）が既約境界なので、**ワークフロー側は必ず作業ブランチへ push → PR 作成の手順を踏み、`contents: write` があっても main へ直接 push するコードを書かない**運用ルールで縛る必要がある（トークン権限だけでは A-1 を強制できない）。

### 4. 🔴 GITHUB_TOKEN で作成・更新した PR が他の workflow をトリガーしない仕様
（actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow）

一次情報で確定:
> "events triggered by the `GITHUB_TOKEN` will not create a new workflow run"
> "`workflow_dispatch` and `repository_dispatch` events always create workflow runs"
> "when a workflow using `GITHUB_TOKEN` creates or updates a pull request, the resulting `pull_request` event creates workflow runs in an **approval-required** state"（マージボックスにバナーが出て、write 権限保持者が承認しないと `pull_request` トリガーの workflow は動かない）

- **範囲**: この制限は **「同一リポジトリの他の GitHub Actions workflow を起動しない」** という Actions 内部の無限ループ防止機構であり、ドキュメント本文には「他の外部サービスへの webhook 配信も止まる」旨の記載は **一切ない**（このページには不在と明記されている）。
- **🔴 Cloudflare Workers Builds への影響（争点 C の前提）**: WebSearch で複数の技術記事・GitHub Community Discussion（例: `orgs/community/discussions/25702`, `orgs/community/discussions/37103`）を確認した限り、**「GITHUB_TOKEN による push が『他の Actions workflow』を起動しない」制限と、「リポジトリにインストールされた GitHub App／webhook（Cloudflare Workers Builds 等）が push イベントを受け取る」ことは別系統**と説明されている。Workers Builds は Actions ではなく GitHub App のプッシュ Webhook を購読して動くため、**この GITHUB_TOKEN 制限の対象外である可能性が高い**。ただし ⚠️ **これは docs.github.com の一次情報ではなく Community Discussion / 技術記事による二次情報**であり、GitHub 公式が「Actions 以外の Webhook は対象外」と明言したページは見つけられなかった。**「未確認」として扱い、本 Issue のスコープでは『理論上は動くはずだが、実機で 1 回 PR マージ → Workers Builds が実際にデプロイをトリガーするかを確認する』ことを Done Criteria に含めるべき**（争点 C・E に引き継ぐ）。
- **回避策（一次情報で確認済み）**: どうしても workflow を連鎖起動させたい場合は GITHUB_TOKEN の代わりに PAT または `actions/create-github-app-token` で発行したトークンを使う、という選択肢がある（本件では Workers Builds 自体が Actions ではないため、恐らく不要）。

### 5. ジョブの実行時間上限・`timeout-minutes` 既定
- **既定値は 360 分（6 時間）** という情報を複数の技術記事・GitHub Community Issue（`github/docs#7984` 等）で確認したが、**docs.github.com のワークフロー構文リファレンスページから該当節の本文を直接引用することはできなかった**（ページが大きく WebFetch が該当セクションを切り出せなかった）。**数値自体は業界的に広く確認されている通説だが、一次情報の直接引用としては「未確認」**として扱ってほしい。
- 実務上の含意: 本バッチは通常 10 分・180 リクエストなので 360 分の既定でも全く問題にならない。ただし **ネットワーク不調時に無限に近い待ち時間になるリスクを避けるため、`timeout-minutes: 20`〜`30` 程度を明示指定すべき**（争点 D「失敗時の扱い」に直結）。

### 6. `concurrency` による多重起動防止
（actions/how-tos/write-workflows/choose-when-workflows-run/control-the-concurrency-of-workflows-and-jobs）

一次情報で確定:
> "There can be at most one running job or workflow in a concurrency group at any time. When a concurrent job or workflow is queued, if another job or workflow using the same concurrency group in the repository is in progress, the queued job or workflow will be pending."
> "By default, any existing pending job or workflow in the same concurrency group will be canceled and the new queued job or workflow will take its place."

書き方の例:
```yaml
concurrency:
  group: gem-pool-regenerate
  cancel-in-progress: false   # 実行中の再生成を中断させたくない場合は false
```
- ⇒ `schedule` と `workflow_dispatch`（手動起動）を同じ workflow に載せる場合、固定の `group` 名にしておけば、スケジュール実行中に手動起動しても二重実行されず後発がキューで待機する（`cancel-in-progress: false` なら実行中のものを壊さない）。

### 7. `workflow_dispatch` の入力定義
一次情報で確定（構文例をそのまま引用）:
```yaml
on:
  workflow_dispatch:
    inputs:
      logLevel:
        description: 'Log level'
        required: true
        default: 'warning'
        type: choice
        options:
          - info
          - warning
          - debug
      print_tags:
        description: 'True to print to STDOUT'
        required: true
        type: boolean
      tags:
        description: 'Test scenario tags'
        required: true
        type: string
```
- `type` は `boolean` / `choice` / `number` / `environment` / `string` から選べる。
- ⇒ 本バッチ向けには、`generate_gem_digest.mjs` が持つ `--dry-run` / `--registries` / `--quota` / `--allow-partial-write` を `workflow_dispatch.inputs` の `boolean`/`string` として露出させておくと、手動デバッグ実行がしやすい（**ただし `--allow-partial-write` は孤児シャード削除を伴う危険オプションなので、既定 `false` にし説明文に警告を書くべき**）。

---

### まとめ（争点 A/B/D への直接の含意）

- **A（間隔）**: 無料枠の制約は消えている（#1）ので、頻度は「Ecosyste.ms 更新頻度」「Gem Index が相対指標であること（頻繁再生成でバッジ付け外れが起きる）」「3.6MB 差分コミットの累積」で決める。cron は UTC 表記・**毎時ちょうど（`:00`）は混雑で遅延/ドロップされうる**ので避ける（#2）。60 日無活動での自動停止条件（#2）はリポジトリ全体の活動で判定されるため、他の PR マージが継続していれば通常は発火しないはずだが、念のため争点 D の監視に含めるべき。
- **B（反映経路）**: `contents: write` + `pull-requests: write` の `permissions:` が必要（#3）。GITHUB_TOKEN で作った PR は他の Actions workflow を自動トリガーしない（承認待ちになる。#4）ので、**もし「PR 作成 → 別 workflow が自動マージ」という 2 段構成にすると承認待ちで止まる**。1 本の workflow 内で `create_pull_request` → `merge_pull_request`（同一 run 内）まで完結させれば `pull_request` イベント自体は関係なく処理できる。
- **D（失敗時）**: `timeout-minutes` を明示指定（既定 360 分は長すぎる。#5）。`concurrency:` で多重起動防止（#6）。`workflow_dispatch` で手動再実行・デバッグ経路を用意（#7）。60 日無活動条件（#2）は本プロジェクトの活動量なら通常問題にならないが監視対象に入れるべき。

### 未確認リスト（推測で埋めなかった項目）
1. GITHUB_TOKEN の既定 permissions が「新規パブリックリポジトリで read-only」であることの docs.github.com 本文一字一句の直接引用（二次情報では確認済み）
2. `timeout-minutes` 既定 360 分の docs.github.com 本文一字一句の直接引用（二次情報では確認済み）
3. GITHUB_TOKEN の workflow 非トリガー制限が Cloudflare Workers Builds のような外部 GitHub App の webhook 配信に影響しないことの公式明言（Community Discussion 等の二次情報のみ。**実機確認を Done Criteria に入れることを推奨**）
4. 60 日無活動時の再有効化・回避の具体手順（公式ページに記載なし）

### `deploy_gate` — 主張
<sub>2026-08-23T10:08:57+09:00</sub>

## deploy_gate レンズ: 争点 B / C（反映経路・デプロイゲート整合）

### 1. データ更新 PR がマージされたとき `check_deploy_gate.py` が返す値（場合分け）

`decide()` は「open かつ `status:in-progress`」の Issue のうち **スプリント対象と判定されたもの**（タイトルに `SP-\d+` を含む、または Issue コメントに `## 🏃 Session Sprint Planning` があるもの）を走査し、1 件でも「判定コメントが無い」または「最新判定が `rejected`」なら `can_deploy=False`（exit 1・待機）を返す。データ PR 自身の中身（コードかデータか）は一切見ない ── **ゲートは main 全体の状態を見るのであって、直前にマージされた PR の性質は無関係**。

| in-progress スプリント Issue | Sprint Review 判定 | 結果 |
|---|---|---|
| 無し（非スプリント in-progress のみ、または in-progress 自体が無い） | — | `can_deploy=True` → exit 0（デプロイ可） |
| 有り | 判定コメントが無い | `can_deploy=False` → exit 1（`REASON_NO_VERDICT`） |
| 有り | 最新判定が `rejected` | `can_deploy=False` → exit 1（`REASON_REJECTED`） |
| 有り | 最新判定が `accepted` / `accepted_with_conditions` | 塞がない（他に塞ぐ Issue が無ければ exit 0） |
| API 到達不可・パース失敗 | — | `can_deploy=None` → exit 2（fail-closed・判定不能） |
| 複数 Issue 混在 | 1 件でも上記「塞ぐ」条件に該当 | 全体で exit 1（`decide()` は OR 集約） |

**実測（読み取り専用・2026-08-23 10:05 JST）**:
```json
{"can_deploy": false, "blocking_issues": [
  {"number": 453, "reason": "Sprint Review 判定が未実施です"},
  {"number": 451, "reason": "Sprint Review 判定が未実施です"},
  {"number": 445, "reason": "Sprint Review 判定が未実施です"},
  {"number": 442, "reason": "Sprint Review 判定が未実施です"},
  {"number": 405, "reason": "Sprint Review 判定が未実施です"}
]}
```
**つまり「今この瞬間」データ PR を main へマージしても、Workers Builds は `workers_build_deploy.sh`（Deploy command として自動実行される。Claude セッションの介在は不要）内で `check_deploy_gate.py` を呼び、exit 1 で fail-closed になる。データは main に入るが本番へは出ない。**（皮肉なことに #451 自体が「Workers Builds が push で自動発火せず 3 スプリント分が本番未反映のまま滞留していた」という別系統の既存不具合であり、鮮度劣化は既に現在進行形で起きている。）

### 2. 「データだけ main に入ってデプロイされない」状態は生まれるか → 生まれる。`D-28` の SPOF 方針に沿って許容する

上記の通り **これは新規に発生する問題ではなく、既存のデプロイ直列化設計（`D-26`/`D-31`/`D-32`）がそのまま適用された結果**。ゲートが閉じている間、本番は「その時点の最新ビルド」を配信し続ける（Cloudflare Static Assets の差し替えが起きないだけで、サイト自体は落ちない）。これは `D-28` が定義する SPOF 対処そのもの（「配信は止めず鮮度のみ劣化させる」）に一致するため、**対処ではなく許容が正しい**。ゲート迂回（データ PR だけ特別扱いして直接デプロイする等）は `workers_build_deploy.sh` 冒頭が明示的に禁じており、採らない。

ただし程度の問題として指摘しておく: 実測で「判定未実施のまま滞留した in-progress スプリント Issue」が **5 件**存在し、ゲートは恒常的に閉じている可能性がある。これは gem-pool 自動化とは無関係の既存の運用負債（Sprint Review が回っていない）であり、本 Issue #458 のスコープでは修正しない。鮮度劣化が実害を持つレベルまで拡大した場合（例: N 日以上ゲートが閉じ続けている）に検知・通知する仕組みが要るなら、それは `check_prod_drift.py`（§8.2.2 で言及されている main↔本番の乖離検知ツール）の役割拡張候補として別 Issue に切り出すのが筋（本 Issue に混ぜない）。

Workers Builds の build watch paths について: Cloudflare の Build Configuration にはパス単位で「このパス配下の変更のみ ビルドをスキップ/実行」という設定（Non-production branch や ignore パス相当の機能）が公式にあるが、**これは「ビルドを起動するかどうか」の絞り込みであり、`check_deploy_gate.py` のゲート判定そのものを迂回・軽減する機能ではない**。データのみの変更でも Deploy command（`workers_build_deploy.sh`）は同じ判定ロジックを通る前提でよく、watch paths でデータ変更だけ「ゲート無しで通す」設計にすると `workers_build_deploy.sh` 冒頭の「ゲート迂回禁止」に抵触するため採用しない。watch paths は「無関係なリポジトリ変更（例: docs のみ）でも毎回ビルドが走ってしまう無駄」を削る目的でなら別途検討の余地はあるが、本争点の解決策ではない。

### 3. 反映経路の結論: **自動 PR + 自動マージ（ただし機械バリデーション条件付き・Layer 0/1 とは別系統）**

**推奨**: Actions ワークフローが PR を作成し、**同じジョブ内の機械チェックが全て通った場合に限り、同じワークフローが `GITHUB_TOKEN` で squash マージする**。人・Claude セッションの介在なしで完結させる。

**根拠（「データしか変わらない PR を機械が通してよい」の中身）**:
- 変更が `public/data/gem-index/**` と `public/data/daily-digest.json` に**限定されている**ことをジョブ内で `git diff --name-only` により機械検査する。これ以外のパスに差分があれば（スクリプトの想定外副作用の証拠）**自動マージしない**。
- 生成物自体の妥当性を機械検査する: 全 12 シャード + `index.json` が JSON としてパース可能、`totalCount` が前回値から想定外に乖離していない（閾値超えは自動マージしない）、`--allow-partial-write` 経路（孤児シャード削除）を通っていない（通っていれば要人手確認）。
- これは `A-3` の「軽微な指摘（閾値内）→自動マージ」と同じ思想 ── ただし主体はコード品質の AI 判断（Layer 1）ではなく、**決定論的なデータ QA**。コードロジックの変更を一切含まない差分にコード品質判断（Skill(code-review)）を要求するのは目的とずれる。
- **既存の PR 自律化恒久委任（`CLAUDE.md`「PR 作成の完全自律化」）とは別系統として扱う**ことを明記する: あの委任は「Claude セッションが自己レビューしてから自律マージしてよい」という **セッション主体の権限**であり、Actions ワークフロー主体の自動マージはそれとは異なる根拠（機械 QA が通った時だけ）に基づく。両者を混同する記述をドキュメントに残さない（docs_trace 側に申し送り）。
- `A-1`（main 直 push 禁止）は維持: 必ず PR 経由。
- **失敗時に PR を放置しない**仕組みが必須（§3 の裏返し）: 機械チェックが 1 つでも落ちたら PR はマージせず、`type:bug` + 専用ラベル（例 `source:actions-bot` + `status:waiting-claude`）を付けたまま残し、通常の waiting-claude 回収経路（`waiting-user-handler` / `pr-review-watcher` のセッション復帰チェック）で Claude セッションが拾って原因調査する。無条件の自動マージ推しにしない代わりに、失敗時は「人手レビュー待ちで塩漬け」ではなく「Claude が拾う」設計にすることで CP-6 を維持する。
- 将来 `tools/generate_gem_digest.mjs` 自体（コード）を Actions が変更するような話が出た場合はこの軽量経路の対象外とし、通常の Claude セッション主導 PR フロー（Layer 0+1）に戻す。**本経路はデータファイルの差分に限定したスコープ**であることを PR テンプレート／ワークフロー双方に明記する。

Workers Builds のデプロイ発火は main への push を webhook で直接監視する Cloudflare 側の仕組み（Actions のワークフロー実行イベントではない）ため、「`GITHUB_TOKEN` で作られた push/PR は他の Actions ワークフローをトリガーしない」という GitHub の制約は **Workers Builds には影響しない**（Actions workflow_run 連鎖の話であって、外部 GitHub App の webhook 購読とは別軸）。ここは一次情報未確認の推論なので、実装前に Cloudflare 公式ドキュメントで確認することを actions_facts/batch_ops に申し送る。

### 4. Actions 発 PR の PR 本文に何を書かせるか／`pre-pr-create-check.sh` は効くか

**実際に確認した**: `pre-pr-create-check.sh` は `.claude/hooks/` 配下の **PreToolUse フック**で、Claude Code ハーネスが「このセッションが Bash で `gh pr create` を叩いた」または「このセッションが `mcp__github__create_pull_request` を呼んだ」ことを検知したときにのみ発火する（`tool_name` を見て判定するフック引数はハーネスが注入するものであり、GitHub Actions ランナー内で `gh pr create` や `peter-evans/create-pull-request` action を実行しても、そのプロセスは Claude Code のツール呼び出し経路を一切通らない）。**したがって Actions 発の PR には一切効かない** ── ① 未コミット/未 push チェック ② `run_checks` サマリー貼付必須チェック ③ `self_review_check.py` Error ゲート ④ Layer 1 リマインダー注入、のいずれも発火しない。

品質担保は「フックに頼らずワークフロー自身が担保する」設計にするしかない。PR 本文（Actions ワークフローが生成）に含めるべき内容:
- **由来を機械可読に明示するヘッダー**（例 `Source: github-actions[bot] (gem-pool-refresh)`）。`Session-Id:`/`Sprint Goal:` トレーラーは書かない（存在しない情報を捏造しない）。これにより `--mine` 所有判定・`is_sprint_issue()` のスプリント検知のどちらにも引っかからず、既存の Claude セッション向けトリアージ（sprint gate・pr-review-watcher の `--mine`）を誤動作させない。
- バッチ実行のサマリー（`totalCount` 前回比・差分件数・実行時間・クエリしたレジストリ数・警告の有無）を機械生成して貼る。`run_checks` の代替として、**このワークフロー自身が行った機械チェック（§3 のバリデーション）の pass/fail 結果表**を本文に貼ることで、`pre-pr-create-check.sh` が Claude PR に要求する「機械的証跡を PR 本文に貼る」という精神を、フックとは独立に別経路で満たす。
- 専用ラベル（例 `type:automation` / `source:actions-bot`）を Actions 側で付与し、既存のスプリント/Issue トリアージ系スクリプト（`check_deploy_gate.py` の `is_sprint_issue`・`check_pending_pr_reviews.py` 等）が Actions 発 PR を人間/Claude 主導の PR と混同しないようにする。

以上、post 済み。
