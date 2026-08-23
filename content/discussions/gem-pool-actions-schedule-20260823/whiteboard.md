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
- 投稿数: 12
- 更新: 2026-08-23T10:17:03+09:00

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

## ラウンド 2

### `docs_trace` — 反論
<sub>2026-08-23T10:11:24+09:00</sub>

# Round 2 反論：衝突回避と新規決定ログの方針

## 1. ファイル衝突の回避（PR #460 と本 Issue の分岐）

| 重複ファイル | round 1 での位置づけ | 本 Issue での対応方針 |
|-----------|------------------|------------|
| `docs/02_requirements/open-questions.md` | 既存決定の「注釈追加（オプション）」「実装時注記（オプション）」| **本 Issue では触らない**。PR #460 での変更を優先させ、Gem digest の決定ログ（D-39 相当）は Issue #458 着手時に **別途追記** |
| `docs/03_design/infrastructure/cloudflare-infrastructure.md` | 既存記述への「注記追加（オプション）」「明確化推奨」| **本 Issue では触らない**。PR #460 での変更を優先させ、Gem digest の位置づけは同 PR の「ただし Gem digest 定期実行は除く」等の書き換えで足りる |

**結論**: round 1 で挙げた変更対象のうち、上記 2 ファイルは「実装時に Issue #458 側で別途対応」として外す。必須変更は `tools/generate_gem_digest.mjs` と `docs/rules/pr-review-flow-summary.md` の 2 ファイルのみに絞る。

## 2. 新規決定ログの追記方法（D-39 の位置づけ）

PR #460 が「`D-31` / `D-32` の決定から従属的に確定する事項」という **新規節** を追加する予定なら、Gem digest の決定（争点 A〜E）も同じ構造（新規節）で実装時に追加するのが自然。

**追記案**:
```
### D-31 / D-32 の決定から従属的に確定する事項

[既存の従属事項...]

🔴 **Gem digest 定期実行（Issue #458・`D-39` 相当）の実装時決定**
  - 実行間隔: [争点 A で決定]
  - 生成物の反映経路: [争点 B で決定]
  - Workers Builds ゲート（`check_deploy_gate.py`）との整合: [争点 C で決定]
  - 失敗時の扱い: [争点 D で決定]
  - 更新すべきドキュメント: [争点 E で決定]
```

**衝突回避**: PR #460 の新規節の直後に上記を足すだけで、PR #460 と本 Issue の変更境界が明確になり、衝突のリスクが下がる。

## 3. `docs/rules/pr-review-flow-summary.md` 23 行目の書き換え文案（逐語）

現行:
```
🔴 **GitHub Actions は制限中で使えない**（ジョブが数秒・ログ 0 バイトで失敗）。ワークフロー 2 本は撤去済み。
```

提案:
```
🔴 **GitHub Actions は制限中から復帰した**（Issue #458 で Gem digest 定期実行用の schedule workflow が実装済み）。
ただし **品質チェック（`npm run check`）と本番デプロイ（Workers Builds）には引き続き使わない**（飼い主決定・Issue #298・`harness-escalation.md` Lv4）。
```

**理由**: Actions の状態変化（「制限中」→「復帰」）を事実で反映しながら、飼い主の「品質ゲートに使わない」方針は維持。Gem digest の schedule workflow は「別用途」と明確に分岐される。

### `actions_facts` — 反論
<sub>2026-08-23T10:11:32+09:00</sub>

## actions_facts — Round 2（rebuttal）

対象: `deploy_gate` の自動マージ設計・Workers Builds への影響、`batch_ops` の週次推奨。round 1 で「未確認」とした核心 2 点について WebSearch で 2 本だけ追加確認した（`.github/workflows/` 等の対象ファイル自体は再読していない）。

---

### 1. 🔴 `GITHUB_TOKEN` の「他 workflow を起動しない」制約は、`deploy_gate` の「同一ジョブ内で PR 作成 → マージまで完結」設計を **壊さない**

**結論から言うと deploy_gate の設計は成立する。** ただし理由の説明が round 1 の私の書き方だと誤解を招くので訂正しておく。

round 1 で確認した制約は「GITHUB_TOKEN が起こした *イベント*（push・PR opened 等）が **別の workflow run** を新規に起動しない」という話であって、「GITHUB_TOKEN で API 呼び出し（マージ操作）ができない」という話ではない。マージは `gh pr merge` / REST `PUT /pulls/{number}/merge` を **同じジョブの同じステップ内で能動的に呼ぶだけ**であり、`pull_request` イベントの発火を待つ受動的な仕組みではない。したがって「PR 作成 → 機械チェック → 同じ job 内で `gh pr merge --squash`」という 1 本の workflow は GITHUB_TOKEN のイベント抑制と無関係に動く。**deploy_gate の設計案（自動 PR + 同一ワークフローでの自動マージ）は技術的に妥当**。

必要な `permissions:` は round 1 の #3 のとおり最低限:
```yaml
permissions:
  contents: write        # push・マージ
  pull-requests: write   # PR 作成・マージ
```

**ただし deploy_gate に 1 点、伝えていなかった落とし穴がある（ブランチ保護との相互作用・追加確認済み）**:
GitHub には「Actions が生成した GITHUB_TOKEN で PR を承認できてしまう」ことを悪用したブランチ保護バイパスの既知パターンがあり、これに対する防御機能が存在する。
- Organization/Repository 設定に **「Allow GitHub Actions to create and approve pull requests」** というスイッチがあり、既定でこれが無効な組織では **GITHUB_TOKEN で作成した PR を GITHUB_TOKEN 自身が承認できない**。
- さらにブランチ保護に **「Require approval of the most recent reviewable push」** を有効化している場合、「直近の push をした主体 ≠ 承認者」が強制されるため、**PR 作成者とマージ実行者が同じ GITHUB_TOKEN だと承認要件を満たせず詰む**構成になりうる。

**本リポジトリへの影響（要確認事項として deploy_gate/lead に申し送り）**: 本 Issue の設計は「レビュー承認（approve）」を経由せず、**squash マージを直接 API で叩く**方式なので、上記の「approve できない」制約そのものには引っかからない可能性が高い（GitHub の必須レビュー数が 0 に設定されていれば approve は不要でマージ API が素通りする）。ただし **本リポジトリの `main` に GitHub 側のブランチ保護ルール（必須レビュー数・必須ステータスチェック）が実際に設定されているかどうかは、この議論の中の誰も一次情報で確認していない**（Claude セッションは `mcp__github__merge_pull_request` で日常的に自己マージしているので、少なくとも「レビュー必須」は設定されていない可能性が高いが、これは推測であり確認事項として残す)。**実装 Issue の Done Criteria に「対象リポジトリのブランチ保護設定を `mcp__github__` 系ツールか GitHub UI で 1 回確認する」を入れることを推奨する**。

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
3. マージ直後、Cloudflare 側のダッシュボード or `mcp__Cloudflare_Developer_Platform__workers_list` 等で **新しいビルドが実際にキューされたか**を確認する。
4. トリガーされていなければ、Workers Builds は GITHUB_TOKEN 発の push を無視している疑いが濃厚 → `trigger_workers_build.py`（PR #460・lead 追加事実 2）が持つ「ゲート通過後の再トリガー」経路を **Gem digest PR のマージ後にも明示的に呼ぶ**フォールバックが必須になる。
この 1 往復さえ実施すれば「未確認」が「確認済み」に変わる。**本 Issue のスコープ内で十分に実施可能な検証**であり、別 Issue に切り出す必要はない。

---

### 3. `batch_ops` の週次推奨（`0 21 * * 0` UTC = 月曜 06:00 JST）について — Actions 側制約とは **矛盾しない**。ただし 1 点リスクを追加する

round 1 で確認した Actions 側の制約と週次推奨を突き合わせる:

- **UTC 表記**: `0 21 * * 0` は UTC 日曜 21:00 = JST 月曜 06:00 で合っている（cron は UTC 基準という round 1 の確認と整合）。
- **毎時 0 分の混雑**: 週次であっても `21:00`（UTC の毎時 0 分）に固定しているため、round 1 で挙げた「高負荷時は分単位でずれる／ドロップされうる」リスクはそのまま残る。**分をわずかにずらす（例 `17 21 * * 0`）ことを推奨**（頻度を下げても「ちょうど 0 分」を避けるコストはゼロなので、直す理由がある）。
- **60 日無活動での自動停止**: 週次実行（52 回/年）自体は「リポジトリの活動」としてカウントされる対象ではない（fact: 判定条件は「リポジトリの活動」であり、schedule workflow 自身の実行が activity としてカウントされるかは round 1 で確認できていない・未確認のまま）。ただし本プロジェクトは PR マージが常時走っている（fact 3〜4 の並行 PR、`session-sprint-rules` の稼働実績）ため、**60 日間 commit が無い状態は現実的にまず起こらない**。週次頻度を理由にこの停止条件を心配する必要はない。
- **⚠️ 追加すべきリスク（round 1 では触れていなかった点）**: 週次のように **実行頻度が低い schedule は、1 回のドロップ（round 1 #2 の "some queued jobs may be dropped"）が与える影響が日次より大きい**。日次でドロップされても翌日に追いつくが、週次でドロップされると **鮮度劣化が最大 2 週間分に伸びる**。`batch_ops` の週次案自体には反対しないが、**「実行されたはずの週に実際に実行されたか」を検知する仕組み**（例: 直近の `index.json` の `generatedAt` が想定より 10 日以上古ければ `[gem-pool-stale]` Issue を起票する定期チェック、または既存の `sprint-cycle-router` の巡回に軽い鮮度チェックを 1 行足す）を D-28 の SPOF 方針（「鮮度のみ劣化させる」を"検知可能な形で"劣化させる）に沿って争点 D に加えることを提案する。

---
以上、post 済み。deploy_gate の設計（自動マージ）は成立を確認（ブランチ保護の一次確認だけ Done Criteria に追加を推奨）。Workers Builds への非影響は concede するが一次情報未確認のため実装前検証手順を明示。batch_ops の週次案は妥当だが、低頻度ゆえの「ドロップ時の鮮度劣化拡大」を新規リスクとして提起。

### `batch_ops` — 反論
<sub>2026-08-23T10:12:52+09:00</sub>

## batch_ops round 2 — rebuttal / concession（round 1 の自分の分析＋ホワイトボードのみで回答。対象ファイルは再読していない）

### 1. 週次推奨を `actions_facts` の制約で再検証 → 確定 cron

`actions_facts` の3点（UTC 基準・毎時 `:00` 混雑・60日無活動で自動停止）と自分の週次推奨は **矛盾しない**。むしろ強化材料がある:

- **60日無活動の自動停止との関係**: 停止条件は「ワークフローの実行有無」ではなく「**リポジトリの活動**」（`actions_facts` #2）。逆に言えば、週次実行が §2（round 1）で述べた「実質ゼロ差分は稀（被依存数はほぼ毎回どこか動く）」の通りほぼ毎回 PR → マージを生むなら、**このバッチ自身が週次の repo activity を生成し、60日しきい値に一度も近づかない**（52 回/年 ≫ 60日に最低1回で足りる水準）。日次にする動機（60日対策）は不要——週次で十分すぎる余裕がある。逆に「実質ゼロ差分の回は PR を作らない」設計（round 1 §2）を厳格に運用しすぎて **何週も連続でゼロ差分が続く**と自己矛盾的にリスクが生まれるが、被依存数の自然変動を考えるとその可能性は低いと見る。念のため「N 週連続で no-op が続いたら Issue 化」を D の監視項目に追加する。
- **毎時 `:00` 混雑の回避**: 分をずらす。
- **確定**: **毎週月曜 06:17 JST**（`:00` から 17 分ずらし、深夜バッチ帯を避けて朝一の枠）。
  ```yaml
  on:
    schedule:
      - cron: '17 21 * * 0'   # UTC 日曜 21:17 = JST 月曜 06:17
  ```
  cron の曜日フィールドは GitHub 仕様上 `0=日曜`。UTC 日曜 21:17 + 9h = 月曜 06:17 JST で計算済み。

### 2. `deploy_gate` の機械マージ案への危険指摘（round1未回答分・核心）

`index.json` について **確実に分かっているキー**（`output.mjs` を全文読んだ範囲）は `shards[].{registry, ecosystem, fileName, count}` と `totalCount` と `stats`（中身は未読・`pipeline.mjs` 本体は round1 で import 一覧しか見ていない）。**`stats` 配下の除外理由別キー名は断定しない**（L-113: 読んでいないものを埋めない）。したがって閾値提案は **確実なキーだけ**で組む:

- **危険 1: 収集失敗（レジストリ 1 つ丸ごと）は既にコード側でブロック済み**——`collectAll` が失敗を記録すると `decideOutputWrite` が `partial=true` → 既定で `write=false`・exit 1（round1 §1）。**ワークフローが exit code を尊重してさえいれば、この経路は最初から PR すら作られない**（`git diff` する対象がない）。したがって `deploy_gate` が懸念する「収集失敗で構成比が崩れた回」は、機械 QA を足すまでもなく **CLI 自身の fail-closed 設計で既に塞がれている**——ここは deploy_gate の懸念が半分は杞憂（危険ではなく安全）だと指摘したい。
- **危険 2（本物の隙間）: 収集は "成功" 扱いだが、フィルタ・dedupe が効きすぎて特定レジストリ or 全体が激減する回**。これは `failures` に乗らないため上記のブロックを素通りし、`write=true` のまま PR が作られる。ここに機械 QA が要る。**具体的閾値（`shards[].count` / `totalCount` のみを使う）**:
  1. **レジストリ単位のゼロ化検知**: 直前コミットの `index.json.shards[]` に存在した `registry` が、今回の `shards[]` から**消えている**、または `count === 0` になっている → 自動マージ **禁止**。（`shards` に載らない＝配列から要素ごと消える点に注意。round1 で確認済みの `buildRegistryShards` の実装〔`byRegistry` を持つレジストリだけ配列化〕からそう読める。）
  2. **レジストリ単位の急減**: 各レジストリについて `count_今回 / count_前回 < 0.7`（30% 超の減少）→ 自動マージ禁止。
  3. **全体の急減**: `totalCount_今回 / totalCount_前回` が **0.85〜1.15 の範囲外**（±15%）→ 自動マージ禁止。根拠: `generate_gem_digest.mjs` の docstring に載っていた実測テーブル（round1 で読んだ範囲）では `minStars` を 1→5 に変えると 88,981→62,565（**約 30% 減**）——これは「意図的な閾値変更」の regime であり、週次の同一設定運転でここまで動くのは異常と判定してよい。±15% は初期値の仮置きで、実運転数回のログで較正し直す前提（ラボ実測ではなく初期ヒューリスティックであることを明記）。
  4. **CLI 自身のフラグを最優先で信じる**: `--report` の JSON（`generate_gem_digest.mjs` の `buildSummary` を round1 で全文読んだ範囲、確実なキー）`partial` / `wroteOutputs` / `blocked` / `removedFiles` を先にチェックし、**`partial !== false` または `removedFiles.length > 0` なら問答無用で自動マージ禁止**（孤児シャード削除が起きた回を機械 QA で二重に弾く）。これは stats の中身を推測するより堅牢——CLI がすでに構造化して吐いている値を再利用するだけで済む。
- **危険 3（deploy_gate 提案への追加指摘）**: 「差分パスを `public/data/**` に機械限定」だけでは①②のような **パスは正しいが中身がおかしい PR** を通してしまう。`git diff --name-only` のパス限定チェックと、上記①〜④の内容チェックは **別の防御層**として両方必須。

### 3. 冪等性チェックの実装形（jq 依存を外す）

`actions_facts` は Actions ランナーの jq プリインストールを一次情報で確認していない（未確認リストに無いが、明言もされていない）。**Node は Actions ワークフローが `setup-node` で確実に用意する**（バッチ本体が Node 22 必須のため）ので、jq には依存せず Node スクリプトで統一する:

```js
// tools/gem-pool/scripts/normalize_for_diff.mjs（新規・提案）
import { readFileSync } from 'node:fs'
const doc = JSON.parse(readFileSync(process.argv[2], 'utf8'))
if (doc?.meta?.generatedAt !== undefined) doc.meta.generatedAt = 'NORMALIZED'
if (doc?.date !== undefined) doc.date = 'NORMALIZED'
process.stdout.write(JSON.stringify(doc, null, 2) + '\n')
```

```bash
changed=0
for f in public/data/gem-index/*.json public/data/daily-digest.json; do
  if ! git show "HEAD:$f" > /tmp/old.json 2>/dev/null; then changed=1; break; fi  # 新規ファイル＝実差分
  node tools/gem-pool/scripts/normalize_for_diff.mjs /tmp/old.json > /tmp/old.norm.json
  node tools/gem-pool/scripts/normalize_for_diff.mjs "$f"       > /tmp/new.norm.json
  diff -q /tmp/old.norm.json /tmp/new.norm.json > /dev/null || { changed=1; break; }
done
if [ "$changed" = "0" ]; then
  git checkout -- public/data/gem-index public/data/daily-digest.json
  echo "no-op: 実質差分なし。PR を作らない"
fi
```
`git diff` 単体では済まない（`generatedAt`/`date` は毎回変わるため生の `git diff` は常に非空になる）。正規化前処理が必須で、それを jq でなく Node で書くのがこのリポジトリの前提（Node 22 セットアップ）に最も素直。

### 4. `--allow-partial-write` はワークフローで使うか

**round1 の結論を維持: 定期実行（`schedule` トリガー）では絶対に使わない。** 孤児シャード削除（`removeOrphanShards`）は取り返しのつかない破壊的操作であり、無人実行と組み合わせるべきではない。

使ってよい場面は **1 つだけ**: `workflow_dispatch`（手動起動）かつ人が明示的に「特定レジストリだけ緊急再生成したい」と判断したとき（CLI コメント自身が「緊急除外・部分再生成用」と明記——round1 では未言及だったが `generate_gem_digest.mjs` の `parseRegistryList` 直上のコメントで確認済み）。`actions_facts` #7 の `workflow_dispatch.inputs` 案に乗せる場合は:
- 既定 `false`、`description` に「⚠️ 索引に載らない孤児シャードを削除します」を明記（`actions_facts` も同じ注意を出している・一致）。
- **このフラグが `true` で実行された回は、§2 で提案した自動マージ QA を無条件でスキップし人手レビュー待ちにする**（自己判断で緊急操作した結果をさらに機械マージするのは二重に危険）。

---
以上、1（cron 確定・60日条件は週次で無問題）、2（deploy_gate の危険指摘の核心に回答・確実なキーのみで閾値提案・危険1は実は安全という訂正込み）、3（Node ベースの実装形）、4（`--allow-partial-write` は schedule では不使用・workflow_dispatch限定＋自動マージ対象外）。

### `deploy_gate` — 反論
<sub>2026-08-23T10:13:08+09:00</sub>

## deploy_gate round 2: lead evidence 2 への応答 + 自己検証 + 決定

### 1. lead evidence 2（PR #460）を受けた round 1 結論の更新 — **一部譲歩（concession）**

**譲歩する**: round 1 の結論「ゲートが閉じて `main` にデータだけ入って本番へ出ない状態は `D-28` の SPOF 方針どおり *許容*」は、**結論（許容してよい）自体は変わらないが、根拠が「受動的放置」から「能動的自己修復が別レーンで既に存在する」に差し替わる**。round 1 では「そのうち別の理由で誰かがデプロイすれば追いつく」という消極的な許容だったが、PR #460 の `trigger_workers_build.py` + `sprint-cycle-router` §1.5 Step 0.2 は **毎 firing** `check_prod_drift.py` で main↔本番の乖離を検査し、ゲートが開いていれば **即座に再トリガー**、開いていなければ `[prod-drift]` Issue で可視化する。これは「gem-pool のデータだけが特別に滞留する」問題ではなく、**あらゆる原因で main が本番より先行した状態を汎用的に検知・解消する**設計であり、gem-pool のデータ PR もこの汎用機構の対象に自動的に含まれる（`check_prod_drift.py` は main HEAD と本番の SHA/内容を比較するだけで、直前にマージされたのがコードかデータかを区別しない）。

**同意する（🔴 の前提）**: 「本 Issue のワークフロー側でデプロイ発火・再トリガーを自前実装しない」に同意する。理由:
- SSOT 二重化のコストが実測で裏付けられている。`open-questions.md` 追記が示す通り、`D-31`/`D-32` は「発火点を移せば直る」という設計だったが実際には「ゲート再オープン後の再トリガー」という **1 つの穴**だけで 3 スプリント分の滞留が起きた。同じ穴を gem-pool 用ワークフローが独自に埋めようとすると、`trigger_workers_build.py` と機能重複する 2 本目の再トリガー実装が生まれ、どちらが正で片方が古くなったときにどちらを信じるかという新しい問題を作る。
- gem-pool ワークフロー側が持つべきなのは「PR を作る（→ マージされれば push が発生する）」ことだけで、**push 後にそれが本番へ届くかどうかは `sprint-cycle-router` Step 0.2 の責務**として完全に切り離してよい。これは責務分離としても妥当（gem-pool ワークフローが Cloudflare API トークンを持つ必要すら無くなる ── 権限最小化の副次効果もある）。

**round 1 からの実務上の変更点**: round 1 で「鮮度劣化の監視を別 Issue に切り出すことを検討」と書いたが、**その別 Issue は既に PR #460 として存在する**ので、本 Issue #458 では何もしない（フォローアップ起票が不要になった）。

### 2. 「ワークフロー自身が squash マージする」への自己検証

**PR を経由する意味 = ブランチ保護が『PR 必須』を GitHub 側で構造的に強制しているかどうかに懸かっている。** 同一 run 内で PR 作成 → マージまで完結させる設計（round 1 案）は、`actions_facts` round 1 §4 の実測（GITHUB_TOKEN 発の `pull_request` イベントは他 workflow を起動しないが、**同一 run 内で `create_pull_request` → `merge_pull_request` を順に呼ぶこと自体は妨げられない**）と矛盾しない。しかし「1 ジョブが自分で作って自分でマージする」だけなら、`main` への直接 push と実質的に何が違うのかは正面から答える必要がある。

答え: **もし `main` のブランチ保護に「PR を必須とする」設定が入っていれば、実質的な差は大きい**（`git push origin main` そのものが GitHub API レベルで拒否される。`GITHUB_TOKEN` に `contents: write` があっても、保護ルールはトークン権限より上位で効く）。この場合、PR 経由は「A-1 の文言だけを満たす形式」ではなく、**ワークフローのコードが将来どう書き換わっても main への直接書き込みが物理的に不可能である**という、`workers_build_deploy.sh` 冒頭が環境変数越しのゲート迂回を禁じたのと同じ思想の「構造的強制」になる。逆に **ブランチ保護が入っていなければ**、この設計は「PR オブジェクトを経由する」という儀式以上の意味を持たず、ワークフローのバグ 1 つで直接 push と同じ結果（レビュー 0 回でコードが main に載る）になりうる。**これは私が未確認の事実であり、`batch_ops`/`actions_facts` に `main` のブランチ保護設定（`require pull request before merging` の有無）を確認してもらう必要がある**（読み取り専用で確認可能なはず）。

結論: **ブランチ保護が「PR 必須」を強制している前提でのみ、round 1 の「自動 PR + 自動マージ」を維持する**。強制されていないなら、①（推奨）**先にブランチ保護を有効化してから**自動マージ経路を組む、または② 保護を入れられない事情があるなら、マージだけは人間/セッションを挟む設計に落とす。①を推す理由は、保護を入れるコストがほぼゼロ（設定 1 行）である一方、②は「放置される PR が増えない仕組み」を別途 §2 で作り込む必要がある（waiting-claude 経路の定期回収に依存する分だけ、放置リスクが構造的に残る）ため。**「同一 run 内マージ」という設計そのものは維持しつつ、その安全性の根拠を『A-1 の文言遵守』ではなく『ブランチ保護による構造的強制』に置き直す**、というのが自己検証の結論。

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
| `totalCount` の前回比 delta 閾値 | ❌ 既存資産なし。`check_gem_shards.py` は「シャード合計とindexのtotalCountが一致するか」という**内部整合**は見るが、「前回の値と比べて妥当か」という**時系列比較**はしない（別の検査軸）。ただし `jq` 1 行 + 算術判定で足り、新規スクリプトは不要 | `old=$(git show HEAD:public/data/gem-index/index.json \| jq .totalCount); new=$(jq .totalCount public/data/gem-index/index.json); python3 -c "import sys; o,n=int('$old'),int('$new'); sys.exit(0 if abs(n-o)/max(o,1)<0.15 else 1)"` |
| `--allow-partial-write` を使っていないこと | ✅ **検査不要**。ワークフローのコマンド行に固定でこのフラグを含めない、という**著者側の規律**で足りる（`workers_build_deploy.sh` が `GATE_CMD`/`DEPLOY_CMD` を配列でハードコードして環境変数からの上書きを禁じたのと同じ考え方を踏襲すればよく、QA スクリプト側で「使われていないか」を後追い検査する必要はない） |

**新規に増やすものはゼロ**（Python/Node の新規ファイルは不要）。既存 `check_gem_shards.py` をそのまま使い、残り 2 項目（diff スコープ・totalCount delta）はワークフロー YAML 内のシェル/jq ワンライナーで完結する。`batch_ops` の正規化 diff スクリプトも同様に新規ファイル化せず、ワークフローのステップとして埋め込めば足りる。

**副次的な発見（lead/docs_trace への申し送り）**: `tools/check_digest_freshness.py --heal` が `node tools/generate_gem_digest.mjs` を自前で subprocess 実行する自己修復パスとして既に存在する（`run_checks.sh` からは呼ばれない設計）。本 Issue の定期実行ワークフローと機能が近接するため、**二重実装にならないか**（`--heal` はローカルファイル再生成のみで git commit/push は行わないので役割は異なるが、将来どちらかが古くなるリスクはある）を `docs_trace` に確認してほしい。

以上、post 済み。

## ラウンド 3

### `lead` — 合意
<sub>2026-08-23T10:16:02+09:00</sub>

## lead 合意整理（4 レンズの claim / rebuttal を突き合わせた結果）

### 合意できた点

1. **コスト制約は消えた**（`actions_facts` 一次情報）。パブリック + 標準ランナーは無料・分数上限なし。頻度はデータ特性だけで決めてよい。
2. **週次で回す**（`batch_ops`）。Gem Index は母集団依存の相対指標でバッジが付いたり消えたりするため高頻度は害。3.6MB の生成物を毎回コミットする履歴コストも効く。60 日無活動の自動停止は、週次実行自体が repo activity を生むため非リスク（`batch_ops` が `actions_facts` の制約に照らして再検証済み）。
3. **cron は毎時 `:00` を避ける**（`actions_facts` 一次情報: 毎時の開始は高負荷でキュー投入がドロップされうる）。
4. **デプロイには一切関与しない**（`deploy_gate` の譲歩 + lead evidence 2）。PR #460 の `trigger_workers_build.py` + `sprint-cycle-router` §1.5 Step 0.2 が「main↔本番の乖離」を原因不問で検知・再トリガーする汎用レーンとして既にあるため、本ワークフローが 2 本目の再トリガー実装を持たない（SSOT 二重化の禁止）。副次効果として **ワークフローに Cloudflare API トークンを持たせる必要が無くなる**（権限最小化）。
5. **差分ゼロ判定は生成直後・ブランチ作成前**（`batch_ops` / `deploy_gate` 一致）。`meta.generatedAt` と `daily-digest.json` の `date` は毎回変わるため生の `git diff` は常に非空になる。正規化してから比較し、実質差分ゼロなら `git checkout --` して何もせず終わる。
6. **jq に依存せず Node で書く**（`batch_ops`）。ランナーの jq プリインストールは一次情報で未確認。バッチ本体が Node 22 必須なので Node は確実にある。
7. **`--allow-partial-write` は定期実行で使わない**（孤児シャード削除が不可逆）。
8. **`pre-pr-create-check.sh` は Actions 発の PR に効かない**（`deploy_gate` が実装を確認）。品質担保はワークフロー自身が持ち、機械チェックの結果を PR 本文へ貼る。
9. **既存資産で足りる**（`deploy_gate` の YAGNI 確認）。`tools/check_gem_shards.py` が索引整合・件数・列定義・サイズ予算・決定論を既に検査している。
10. **本 Issue で `open-questions.md` / `cloudflare-infrastructure.md` を大きく触らない**（`docs_trace`）。PR #460 と衝突するため、必須変更は `generate_gem_digest.mjs` と `pr-review-flow-summary.md` に絞る。

### 対立点と lead の裁定

**対立 1: ワークフロー自身が squash マージしてよいか**

- `deploy_gate` round 1: 機械 QA が全通過したときだけワークフローが自動マージする（人・セッションの介在なし）。
- `deploy_gate` round 2（自己検証後）: その安全性の根拠は「A-1 の文言遵守」ではなく **`main` のブランチ保護が『PR 必須』を構造的に強制していること** に懸かる。強制されていなければ「PR を経由する儀式」にすぎず、ワークフローのバグ 1 つで直接 push と同じ結果になる。→ 保護を先に有効化するか、マージだけ人/セッションを挟むか。
- `actions_facts` round 2: 同一 run 内のマージ API 呼び出し自体は GITHUB_TOKEN の非トリガー制約と無関係で技術的には成立する。ただし **ブランチ保護の「Allow GitHub Actions to approve pull requests」「Require approval of most recent push」** が入っていると自己承認・自己マージが弾かれうる。

🔴 **lead 裁定: ワークフローは PR を作るところまで。マージしない。**

理由:
1. 自動マージ案の安全性は **本セッションで確認できていない設定（ブランチ保護）** に依存する。`mcp__github__list_branches` は `protected` フラグを返すが、`main` に到達するまでのページングが重く、かつ「PR 必須」かどうかまでは分からない。**未確認の前提に安全性を預ける設計は採らない**（`deploy_gate` 自身が round 2 で置いた条件を満たせない）。
2. 保護を有効化してから組む案（`deploy_gate` の①）は、**リポジトリ設定の変更がユーザー操作**になる。設定 1 つのために本 Issue の完了をユーザー待ちにするのは筋が悪い。
3. 「放置される PR が増えないか」という②の弱点は、**本プロジェクトでは既に埋まっている**。`check_pending_pr_reviews.py --actionable-only`（孤児 PR 救済）・`project-sync` の Orphan PR 検出（24 時間超）・`sprint-cycle-router` Step 2（自 PR 回収）という 3 つの回収経路が既に稼働している。加えて **週次・固定ブランチ** なので同時に開くデータ PR は常に 1 本以内で、積み上がらない。
4. 週次のデータ更新に数時間のマージ遅延が乗っても実害がない（鮮度の劣化のみ・`D-28`）。

**選ばなかった側（自動マージ）の最強の論拠への反駁**: 「セッションを挟むと CP-6（ユーザー介入最小化）に反する」——反する相手は *ユーザー* であって *Claude セッション* ではない。マージするのは Claude であり、ユーザーの手は 1 度も要らない。したがって CP-6 は満たされている。むしろ自動マージ案の方が、成立条件としてユーザーのリポジトリ設定変更を要求する分だけ CP-6 から遠い。

**対立 2: 機械 QA が落ちたときどうするか**

- `deploy_gate` round 1: PR は作り、ラベルを付けて Claude セッションに拾わせる。
- `batch_ops` round 2: 収集失敗は CLI 自身が fail-closed で書き込まないので PR すら作られない。本当の隙間は「収集は成功したがフィルタ・dedupe で激減した回」。閾値は確実なキー（`shards[].count` / `totalCount`）だけで組む。

🔴 **lead 裁定: QA が落ちたら PR を作らずジョブを失敗させる（fail-closed）。**
壊れている可能性のあるデータで PR を開くと、回収経路が「マージしてよい PR」と混ざる。週次なので次回に自動リトライされ、失敗は Actions の失敗通知として残る。`batch_ops` の閾値（レジストリのゼロ化・レジストリ単位 30% 減・全体 ±15%）をそのまま採る。

**対立 3（lead が発見した新しい論点）: `check_digest_freshness.py` の 48 時間閾値と週次が矛盾する**

`project-sync` スキルは `check_digest_freshness.py --json` を既定閾値（**48 時間**）で呼び、stale なら `--heal`（= `generate_gem_digest.mjs` をその場で実行）する。週次運用にすると **1 週間のうち 5 日以上が常に stale** と判定され、セッションが毎回 10 分のバッチを回してしまう（週次スケジュールの意味が消える）。

🔴 **lead 裁定: `project-sync` の呼び出しを `--max-age-hours 192`（8 日）にする。** 週次スケジュール（168 時間）+ 実行遅延の余裕を見た値。これにより **一次経路は Actions のスケジュール、`--heal` はワークフローが 1 週間以上失敗し続けたときだけ動く真のフォールバック**になる。`E-25`（鮮度チェックと自己修復）の要件は満たしたまま、二重実行だけを消す。

### `lead` — 判定
<sub>2026-08-23T10:17:03+09:00</sub>

{
  "decisions": [
    {
      "issue": "A: 実行間隔",
      "decision": "週次。cron '17 21 * * 0'（UTC 日曜 21:17 = JST 月曜 06:17）+ workflow_dispatch の手動起動を併設する。",
      "rationale": "パブリック + 標準ランナーは無料・分数上限なしでコスト制約は消えた（actions_facts 一次情報）。頻度を決めるのは Gem Index が母集団依存の相対指標であること（高頻度だとバッジが付いたり消えたりする）と 3.6MB を毎回コミットする履歴コスト（batch_ops）。毎時 :00 は高負荷でドロップされうるため分をずらす（actions_facts 一次情報）。60 日無活動の自動停止は、週次実行自体が repo activity を生むため非リスク。",
      "files": [".github/workflows/gem-pool-refresh.yml（新規）"]
    },
    {
      "issue": "B: 生成物の反映経路",
      "decision": "ワークフローは固定ブランチ automation/gem-pool-refresh へ push して PR を作るところまで。自動マージしない。ラベルは type:improvement + status:waiting-claude を付け、既存の PR 回収経路（check_pending_pr_reviews.py / project-sync / sprint-cycle-router）に拾わせる。permissions は contents: write + pull-requests: write。差分ゼロなら PR を作らない。",
      "rationale": "自動マージ案の安全性は main のブランチ保護（PR 必須 / Allow Actions to approve）という本セッションで未確認の設定に依存し、成立させるにはユーザーのリポジトリ設定変更が要る。放置リスクは既存の 3 つの回収経路 + 週次・固定ブランチ（同時に開くデータ PR は常に 1 本以内）で埋まっている。マージするのは Claude なのでユーザーの手は要らず CP-6 も満たす。",
      "files": [".github/workflows/gem-pool-refresh.yml（新規）"]
    },
    {
      "issue": "C: Workers Builds デプロイゲートとの整合",
      "decision": "本ワークフローはデプロイに一切関与しない。デプロイゲートが閉じている間データが main に入っても本番へ出ない状態は D-28 の SPOF 方針どおり許容する（配信は止めず鮮度のみ劣化）。滞留の解消は PR #460 の trigger_workers_build.py + sprint-cycle-router §1.5 Step 0.2 に委ねる。",
      "rationale": "あのレーンは main↔本番の乖離を原因不問で検知・再トリガーする汎用機構で、データ PR も自動的に対象に含まれる。2 本目の再トリガー実装を持つと SSOT が割れる。副次効果としてワークフローに Cloudflare API トークンを持たせずに済む（権限最小化）。ゲート迂回は workers_build_deploy.sh 冒頭が禁じており採らない。",
      "files": []
    },
    {
      "issue": "D: 失敗時の扱い",
      "decision": "timeout-minutes: 25 / concurrency group（cancel-in-progress: false）/ 機械 QA が落ちたら PR を作らずジョブを失敗させる（fail-closed）/ --allow-partial-write は使わない。失敗は Actions の失敗通知として残り、週次スケジュールが次回自動リトライする。",
      "rationale": "収集失敗は CLI 自身が fail-closed で書き込まないため PR すら作られない（batch_ops の訂正）。本当の隙間は「収集は成功したがフィルタ・dedupe で激減した回」で、ここに閾値チェックが要る。壊れた可能性のあるデータで PR を開くと回収経路が「マージしてよい PR」と混ざるため、PR を作らない側に倒す。",
      "files": [".github/workflows/gem-pool-refresh.yml（新規）", "tools/gem_pool_qa.mjs（新規・QA と no-op 判定）"]
    },
    {
      "issue": "D-2: 機械 QA の中身",
      "decision": "① tools/check_gem_shards.py（既存・索引整合/件数/列定義/サイズ予算/決定論）② 差分パスが public/data/gem-index/** と public/data/daily-digest.json に限定されているか ③ index.json の shards[].count でレジストリのゼロ化・消失を検出 ④ レジストリ単位 30% 超の減少を検出 ⑤ totalCount の前回比 ±15% 超を検出。②〜⑤ を tools/gem_pool_qa.mjs にまとめ、--self-test を run_checks.sh に配線する。",
      "rationale": "①は既存資産で完全に足りる（deploy_gate の YAGNI 確認）。②〜⑤は既存に無く、閾値は index.json の確実なキーだけで組む（batch_ops が stats 配下のキー名は未読として断定を避けた）。jq はランナー同梱が一次情報で未確認のため Node で書く。",
      "files": ["tools/gem_pool_qa.mjs（新規）", "tools/run_checks.sh（self-test 配線・PR #460 と別アンカー）"]
    },
    {
      "issue": "E: 既存記述の更新",
      "decision": "必須は 3 ファイル: ① tools/generate_gem_digest.mjs 冒頭の「⚠️ CI での自動実行はしない」→ 週次ワークフローがある旨へ ② docs/rules/pr-review-flow-summary.md の「GitHub Actions は制限中で使えない」→ 復帰した事実 + 品質ゲート・本番デプロイには引き続き使わない方針 ③ .claude/skills/project-sync/SKILL.md の check_digest_freshness.py 呼び出しに --max-age-hours 192 を付ける。あわせて open-questions.md の決定ログへ D-39 を 1 行追加する。",
      "rationale": "①②は事実が変わった記述。③は週次（168 時間）と既定 48 時間が矛盾し、セッションが毎回 10 分のバッチを回してしまうため（lead が発見した対立 3）。open-questions.md / cloudflare-infrastructure.md の大きな改稿は PR #460 と衝突するため避け、決定ログの表に 1 行足すだけに留める（docs_trace の衝突回避案）。",
      "files": ["tools/generate_gem_digest.mjs", "docs/rules/pr-review-flow-summary.md", ".claude/skills/project-sync/SKILL.md", "docs/02_requirements/open-questions.md"]
    }
  ],
  "workflow_spec": {
    "cron": "17 21 * * 0",
    "jst": "毎週月曜 06:17 JST",
    "steps": [
      "actions/checkout（main・fetch-depth 2 以上）",
      "actions/setup-node（Node 22・npm ci は不要＝バッチは外部依存ゼロ）",
      "node tools/generate_gem_digest.mjs（終了コードが非ゼロならここで失敗）",
      "node tools/gem_pool_qa.mjs --check（差分パス限定 + レジストリゼロ化/30% 減 + totalCount ±15%。落ちたらジョブ失敗・PR を作らない）",
      "node tools/gem_pool_qa.mjs --no-op（generatedAt / date を正規化して比較。実質差分ゼロなら git checkout -- して正常終了）",
      "python3 tools/check_gem_shards.py（既存の静的検査）",
      "固定ブランチ automation/gem-pool-refresh へ commit & force push",
      "PR を作成（既存があれば更新）。本文に QA 結果表・totalCount 前回比・レジストリ別件数・実行時刻（JST）を貼る",
      "ラベル type:improvement / status:waiting-claude を付与"
    ],
    "permissions": ["contents: write", "pull-requests: write"]
  },
  "user_actions": [],
  "rejected": [
    "ワークフロー自身が squash マージする（安全性が未確認のブランチ保護設定に依存し、成立させるにはユーザーのリポジトリ設定変更が要る）",
    "main への直接 push（A-1・不可逆）",
    "デプロイゲートの迂回・データ PR だけ特別扱いして直接デプロイ（workers_build_deploy.sh 冒頭が禁止）",
    "本ワークフロー側で Workers Builds を再トリガーする（PR #460 と SSOT が割れる）",
    "日次実行（Gem Index の相対指標としてのチラつき + 3.6MB×365 の履歴コスト）",
    "--allow-partial-write を定期実行で使う（孤児シャード削除が不可逆）",
    "jq 前提のワンライナー（ランナー同梱が一次情報で未確認）",
    "Actions を品質ゲート・本番デプロイに使う（飼い主決定 #298・本 Issue のスコープ外）"
  ],
  "unknowns": [
    "GITHUB_TOKEN 起因の push で Cloudflare Workers Builds が発火するか（GitHub App の webhook は Actions の非トリガー制約の対象外という理解は二次情報のみ）。ただし本設計ではマージするのが Claude セッション（= 通常の push）なので、この不確実性は実害を持たない",
    "main のブランチ保護に『PR 必須』が入っているか（未確認。本設計は保護の有無に依存しない）",
    "GITHUB_TOKEN の既定 permissions が read-only か（二次情報のみ。permissions を明示するので実害なし）",
    "totalCount ±15% / レジストリ 30% 減という閾値は初期ヒューリスティック。実運転数回のログで較正し直す"
  ],
  "follow_up_issues": [
    {
      "title": "improvement: Gem 候補プール QA の閾値（totalCount ±15% / レジストリ 30% 減）を実運転ログで較正する",
      "labels": ["type:improvement", "sp:2"],
      "done_criteria": "週次ワークフローを 4 回以上回した実績値をもとに閾値を見直し、根拠を tools/gem_pool_qa.mjs の docstring に記録する"
    }
  ]
}
