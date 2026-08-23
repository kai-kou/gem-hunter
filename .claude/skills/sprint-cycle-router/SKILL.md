---
name: sprint-cycle-router
description: 単一ルーティン（N 時間ごとの cron 起動）でスプリント開発を自走させる決定木ルーター。破壊的変更対応・自 PR 回収・進行中スプリント再開・SP→Issue 同期・新規スプリント着手（TDD・縦切り・専門チーム編成）・改善Issue消化・振り返り Issue 消化・衛生・週次リファインメント・spec-sync 検証の 10 ブランチから、1 firing につき該当する最初の 1 つだけを実行する。「スプリント自走ルーティン」「N 時間ごとの開発を進めて」「スプリントサイクルを回して」「/sprint-cycle-router」と依頼された時、またはルーティン設定（`docs/routines/sprint-cycle-routine.md`）から自動起動する時に使用する。各ブランチの実処理は既存パイプラインスキル（`claude-code-spec-sync` / `pr-review-watcher` / `self-improvement-loop` / `retro-try-handler` / `workflow-health-check` / `project-sync`）に委譲し、本スキル自身は「今どのブランチを実行すべきか」の判定と Step4（新規スプリント着手）の内部手順だけを持つ。改善Issueの発見・棚卸し自体は `self-improvement-loop`、リポジトリ衛生の監査自体は `workflow-health-check` の担当（本スキルはそれらの呼び出し元）。
effort: medium
---

> 🔴 **GitHub 操作の経路（必読・L-114）**: クラウド実行環境では `gh` がプリインストールされず、
> 導入しても repo スコープ REST が 403 になりうる。**本ファイル内の `gh ...` コマンドはローカル実行専用**
> で、クラウドでは `mcp__github__*` に読み替える（対応表: `docs/rules/github-mcp-fallback-patterns.md`）。
> 本スキルは無人 cron 起動が既定のため、**Step 0.0 で毎 firing チャネルを再判定する**（§0 参照。
> 「前回動いたから今回も」という恒久判断はしない）。

# sprint-cycle-router スキル

## 目的

飼い主が単一のルーティン設定内で「N 時間ごとに開発が進む」状態を作れるよう、**1 本の決定木** で
「今 firing で何を実行すべきか」を判定し、実処理は既存パイプラインスキルに委譲するルーター。
新規スプリント着手（Step 4）だけは本スキルが内部手順を持つ（`sprint-development-rules.md` の
`SD-1`〜`SD-4` を実行する主体がここに要るため）。

設計の経緯・却下案・被害の非対称性の議論全文は
`content/discussions/sprint-cycle-design-20260818/whiteboard.md`（本スキルは判定ロジックの実体。
議論ログは変更しない）。

## 他レーンとの境界

- 破壊的変更対応の実処理 → `claude-code-spec-sync`
- PR レビュー・マージ・公開反映の実処理 → `pr-review-watcher`
- 改善 Issue の発見・棚卸し・消化の実処理 → `self-improvement-loop`
- リポジトリ衛生（Stale/Orphan/ラベル不整合）の実処理 → `workflow-health-check` → `project-sync`
- 本スキルはこれらの **呼び出し順序と、どれも該当しないときの新規スプリント着手（Step 4）** だけを担う。
  Step 4 の実装フローが既存 4 レーンと並ぶ「第 4 レーン（スプリント開発レーン）」であることの境界定義は
  `docs/rules/improvement-lane-map.md` を参照する（本スキルでは再定義しない）。

---

## §0 実行モデル

- **1 firing = 上から該当する最初の 1 ブランチだけを実行する。** スプリントは複数 firing にまたがってよい
  （SD-1 の完了条件は「マージされた PR にプレビュー URL があり操作レビューを完走できる」ことであって
  「1 firing で完結する」ことではない）。
- **毎回新規セッション・エフェメラル VM**。前回 firing のメモリ・ローカル state は引き継がれない。
  次回 firing が状態を知る手段は **GitHub 上のアーティファクト（Issue ラベル・コメント・PR・ブランチ・
  コミット）だけ**。日次・毎 firing の判定に新規 state ファイルを作らない（§9 の週次ゲートのみ既存パターンを流用可）。
- 早期リターン（§2）を安く済ませることで、cron を短い間隔で回しても空振りコストを抑える
  （実際の間隔は `docs/routines/sprint-cycle-routine.md` が正本・可変）。
- **§1.5（Step 0.2・本番ドリフト検査）は早期リターンではない**。§2 以降のどのブランチが選ばれるかに
  かかわらず毎 firing 必ず 1 回通る前置チェックとして、§2 より前に評価する（#451）。
  **N（cron 間隔）は完了保証の単位ではなく健全性チェックの再訪頻度**。

---

## §1 Step 0.0: API チャネル判定（毎 firing 必須・1 回だけ判定して使い回す）

無人 cron 起動では `mcp__github__*` が届かない firing がありうる（実測事例あり）。以下の
4 段で **毎 firing** 判定し、以降の全ステップで同じチャネルを使い回す。

```
1. mcp__github__list_issues(perPage=1) を試す → 成功なら MCP モード（既定・以降はこれを使う）
2. 失敗 → `gh api user` を試す → 成功なら gh モード
   （tools/check_pending_pr_reviews.py 等の既存 gh 依存ツールをそのまま使ってよい）
3. 失敗 → `curl -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $GH_TOKEN" \
   https://api.github.com/repos/{owner}/{repo}` を試す
   ⚠️ `docs/rules/github-mcp-fallback-patterns.md` は「直叩きは通常 403 でフォールバックにならない」
      と明記済み。この段が 200 を返しても **恒久前提にしない**（CP-2）。この firing 限定で
      curl モードに落ちてよいが、次回 firing は必ず 1 → 3 を再度順に試す。
      curl が 200 を返す事実自体が SSOT の記述と矛盾する場合は、矛盾を検証フラグ付きで
      `type:bug`（`lane:github-api-proxy` 等の既存ラベル体系があれば流用）Issue に記録し、
      本firingの判定はそのまま続行する（記録と実行を両立させる。記録のために止まらない）。
   curl モードで Step 2（自分の PR 回収）を判定する場合、`check_pending_pr_reviews.py` に
   curl 経由の第 3 層は無いため、`GET /repos/{owner}/{repo}/pulls?state=open` を直叩きし、
   PR 本文の `Session-Id:` トレーラーをクライアント側で grep して `--mine` 相当を素朴に再実装する。
4. 全滅 → GitHub API 完全不通。Issue/PR に依存する全 Step（整数・小数点を問わず。Step 1〜8 と 3.5 / 5.5）は実行不能と判定し、
   git 単独で判定できる範囲（ローカルに push 漏れのコミットが無いか等）だけ確認して **安全側 no-op**。
   ログを残さず何もしない（永続化先が無い。次回 firing が独立に再判定するのが ephemeral 前提と一致する。
   中途半端なローカル state ファイルを新設しない）。
```

---

## §1.5 Step 0.2: 本番ドリフト検査（毎 firing 必須・全ブランチより先に評価）

Cloudflare Workers Builds は `main` への push ごとに発火するが、Deploy command 側のデプロイゲート
（`tools/check_deploy_gate.py`）が閉じているとビルド自体が exit 1 で終わり、**ゲートが後から開いても
その push を再ビルドする経路が存在しない**（Issue #451・実測: SP-17〜SP-19 の 3 スプリント分が本番
未反映のまま気づかれずに滞留）。本ステップはその滞留を毎 firing 検知し、可能なら自己解決し、
できなければ可視化する。

🔴 **評価順の注意（このリポジトリは過去に到達不能な分岐を作った事故がある）**: 本ステップは
**§1（Step 0.0 チャネル判定）の直後・§2（Step 0.1 早期リターン）より前** に評価する。早期リターンや
Step 1〜9 のどのブランチが選ばれても、その手前で必ず 1 回通る位置に置くことで「条件は書いたが
評価順で到達しない」再発を防ぐ。1 firing 1 ブランチの原則（§0）の対象外の **前置チェック** であり、
早期リターンではない（本ステップの実行後、通常どおり §2 以降の判定を続ける）。

```
1. §1 のチャネル判定が MCP/gh/curl のいずれかで成立している場合のみ実行する
   （§1 手順 4「全滅」の場合は本ステップも実行せず安全側 no-op のまま Step 0.1 以降へ進まない）。
2. python3 tools/check_prod_drift.py を実行する（引数なし・本判定）。
   終了コード: 0 = ドリフト無し / 1 = ドリフトあり / 2 = 判定不能（fail-closed）。
3. 0（ドリフト無し）→ 何もせず §2 へ進む。
4. 1（ドリフトあり）→ python3 tools/trigger_workers_build.py を実行する（既定でデプロイゲートを
   内部で再確認するため、ここでの `check_deploy_gate.py` の二重実行はしない）。
   - 0（トリガー成功）→ 自己解決。`[prod-drift]` の open Issue があれば
     `進捗: Workers Builds 再トリガー成功（build_uuid: <値>）` を追記コメントしてクローズする
     （無ければ起票不要・「気づかれず滞留」した形跡が無いため）。
   - 1（デプロイゲート待機中・異常ではない）→ **滞留を可視化する**:
     `[prod-drift]` の open Issue が既に無いか確認する（重複起票防止・§9 の `[Milestone] M-3 到達`
     と同じ作法）。無ければ 1 件だけ起票し、本文に「本番と main HEAD が乖離しています。
     デプロイゲートが閉じているため Workers Builds の再トリガーは待機中です」と、乖離を検知した
     コミット SHA・検知日時（JST）を記録する。既にあれば「まだ乖離継続中（前回検知から N 回目の
     firing）」を追記コメントする（新規 Issue を毎回作らない）。**このステップでは @mention しない**
     （A-1〜A-6 に該当しない・`user-notification-triage.md`）。
   - 2（判定不能）→ fail-closed。`type:bug` Issue（`lane:cloudflare-deploy` 等の既存ラベル体系が
     あれば流用）に判定不能の事実とエラー内容を記録し、握り潰さずに §2 へ進む。
5. 2（`check_prod_drift.py` 自体が判定不能）→ 4 の「2（判定不能）」と同じ扱いで fail-closed 記録し、
   §2 へ進む。
6. `trigger_workers_build.py` が存在しない場合（未デプロイ環境等）はスキップし、記録も起票もせず
   §2 へ進む（本ステップは #451 対策の一部であり、存在しない前提で決定木全体を止めない）。
```

新規ラベル・新規 state ファイルは作らない（`[prod-drift]` Issue の open/closed 状態だけで滞留を判定する。
`[publish-sync]` Issue と同じ作法・`pr-review-flow-summary.md` 参照）。

---

## §2 Step 0.1: 早期リターン判定

数クエリで「今回やることが無い」を判定して安く抜ける。**a〜d のいずれかが該当した時点で該当ステップに
進み、全て非該当なら Step 9（no-op）へ**。

```
a) [CC-Sync 破壊的変更] `lane:claude-code-spec` かつ `[CC-Sync][破壊的変更]` の open Issue の存在チェック（1 クエリ）
b) 自分の in-progress Issue / open PR の存在チェック（`check_pending_pr_reviews.py --mine --actionable-only`
   相当・1 クエリ。§1 のチャネルに応じて MCP/gh/curl 手動実装のいずれかで実行）
c) `status:waiting-claude` の **非 `SP-n`** Issue の在庫チェック（1 クエリ・`type` は問わない。`release:deferred` は在庫に数えない＝Step 5 の対象外のため・`docs/05_release/pre-release-gate.md` §3）
d) 当日の衛生スロット実施済みか（`project-sync` のログ相当・当日の Issue コメント日付や
   `workflow-health-check` 実行痕跡から判定・1 クエリ。新規 state ファイルは作らない）
```

早期リターンのコストが数クエリに収まるからこそ、cron を短い間隔で回せる（§0）。

---

## §3 決定木 Step 1〜9

**1 firing = 上から該当する最初の 1 ブランチだけ実行する。** 優先順位の設計原則: 「今動いている作業を
完走させる（Step 1〜3）」>「新しい価値を作る（Step 4）」>「バックログの健全性を保つ（Step 5〜8）」。

| Step    | 判定条件（機械的に書く）                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                | 実行内容                                                                                                                                                                                                                                                                                                                                                                                                                                                                            | 委譲先スキル                                                                     |
| ------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| **1**   | `lane:claude-code-spec` かつ `[CC-Sync][破壊的変更]` の open Issue が存在する                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           | 即対応（他ブランチより最優先・既存仕様どおり）                                                                                                                                                                                                                                                                                                                                                                                                                                      | `claude-code-spec-sync` Step1                                                    |
| **2**   | `check_pending_pr_reviews.py --mine --actionable-only`（相当）が非空                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    | レビュー対応・自動マージ・公開反映まで継続。新規スプリント着手より優先（CP-4: 中途 PR を放置して新規に手を広げない）                                                                                                                                                                                                                                                                                                                                                                | `pr-review-watcher`                                                              |
| **3**   | `status:in-progress` かつ Sprint Planning コメントがある Issue のうち `updated_at` が **4 時間超 stale**（4 時間未満は他セッション対応中とみなし触らない）                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              | 前回 firing が力尽きた形跡。git log とIssue コメント（Sprint Planning・仮定記録・「進捗: {SD ステップ名 **または Sprint Review 判定済み（結果 / デプロイ要否）・デプロイ完了・退役完了**}まで完了。次は {次にやること}」1 行）から続きを判定し再開（手順は §7 の中断条件と対。**Sprint Review 判定済みでデプロイ・退役が未完了のケースは下記「Step 3 の再開: デプロイ・退役未完了の検出」を先に見る**）。対応する open PR があれば Step 2 と同じ扱いに合流                          | `pr-review-watcher`（PR 済みなら）/ 自前（PR 未作成なら §4 の 4-4 以降から再開） |
| **3.5** | Ready 判定（下記「Ready の定義」5 条件）を満たす次の `SP-n` の Issue が **無い**                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | `tools/sprint_backlog_sync.py` を実行し、**その 1 件だけ** 起票する（先読み複数起票はしない＝CP-4 のロックと相性が悪く他セッションの着手余地を奪う）。起票は Issue 作成に限定した副作用。呼び出し方のみ本スキルが持ち、スクリプト内部のパース・判定ロジックは持たない                                                                                                                                                                                                               | `tools/sprint_backlog_sync.py`                                                   |
| **4**   | Ready な `SP-n` の Issue が存在する（Step 3.5 の結果、必ず 0 件か 1 件）                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                | 新規スプリント着手。内部手順は §4                                                                                                                                                                                                                                                                                                                                                                                                                                                   | 自前（`pr-review-watcher` へ Step 4-6 で継続）                                   |
| **5**   | ① `status:in-progress` かつ `SP-n` 規約にも `type:retro-try` にも該当しない Issue が **4 時間超 stale**（前回 firing が着手だけして力尽きた形跡。Step 3 は Sprint Planning コメントを持つ `SP-n` しか拾わず、Step 5.5 ① は `type:retro-try` 限定のため、**この 2 つの隙間に落ちる非 `SP-n` Issue をここで再開する**・#452）、または ② `status:waiting-claude` の Issue のうち、タイトルが `SP-n` 規約（`^SP-(\d+):`）に一致しないものが存在する（**`type` で絞らない**）。① は ② より優先する。**`release:deferred` はどちらの対象にもしない**（提出後に回すと決めたもの・`docs/05_release/pre-release-gate.md` §3）                                                                    | バックログ消化（既定 5 件/回。本ルーティンでは firing の残り予算次第で件数を絞ってよい）。🔴 **提出前ゲートが稼働中は `docs/05_release/pre-release-gate.md` §5 の上書き（対象スコープ・同 priority 内のタイブレーク順・件数上限の 3 項目のみ）を読み、`release:required` を §2 の表の順に 1 件だけ処理する**（上書きが許される根拠と射程は `self-improvement-loop` SKILL.md 消化モード冒頭。**priority ラベルの大小順は上書きしない**。ゲート終了後は本行の参照ごと撤去する・#466） | `self-improvement-loop` 消化モード                                               |
| **5.5** | ① `status:in-progress` かつ `type:retro-try` の Issue が **4 時間超 stale**（着手して中断したものの再開。Step 3 は Sprint Planning コメントを持つ `SP-n` しか拾わないためここで拾う）、または ② `status:waiting-claude` かつ `type:retro-try` の Issue が存在し **直近の retro-try 対応から 8 時間以上経過** している（エージング条件・§5）。① は ② より優先する。🔴 **提出前ゲート稼働中（`release:required` の open Issue が 1 件以上）は ① の Step 5 に対する優先を停止し、retro-try の再開は 1 日 1 回までに制限する**（2 時間 cron のスロットが retro-try に吸われてゲートが進まなくなるため・`docs/05_release/pre-release-gate.md` §5・#452。ゲート終了後は本文を撤去する・#466） | 振り返り由来の Try Issue の消化（既定 2〜5 件/回・件数は委譲先の動的上限に従う）                                                                                                                                                                                                                                                                                                                                                                                                    | `retro-try-handler`                                                              |
| **6**   | 当日の衛生スロット未実施（`project-sync` ログなし）                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     | 監査・衛生                                                                                                                                                                                                                                                                                                                                                                                                                                                                          | `workflow-health-check` 軽量版 → `project-sync`                                  |
| **7**   | `config/backlog_refinement_state.json` の `last_refinement_at` から 7 日超                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              | リファインメント週次ゲート                                                                                                                                                                                                                                                                                                                                                                                                                                                          | `self-improvement-loop` 整理モード Step G-1.5〜G-6 <!-- refcheck:ignore -->      |
| **8**   | `[CC-Sync][検証]` の open Issue が残っている                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            | 検証 Issue 対応（1 件のみ）                                                                                                                                                                                                                                                                                                                                                                                                                                                         | `claude-code-spec-sync` Step2                                                    |
| **9**   | 全部空                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  | no-op。`routine-idle` 通知は既存の 1 日 1 回自己抑制のまま                                                                                                                                                                                                                                                                                                                                                                                                                          | —                                                                                |

### Step 3 の再開: デプロイ・退役未完了の検出（`sprint-env-lifecycle-20260820` D）

対象 Issue の **最新コメント**（または最新に近いコメント）が `## 🔍 Sprint Review 判定` で、
かつそれ以降に「デプロイ完了」を示す追加コメント（`pr-review-watcher` Step 7-3.5 が投稿する
`進捗: デプロイ完了（tag: ...）・退役完了（alias: ...）。次は retrospective スキル起動`）が **無い** 場合、
判定は出ているがデプロイ・退役が未実行のまま前回 firing が力尽きたと判定する。

```
1. 最新の Sprint Review 判定コメントを読む（**結果** / **デプロイ** 行を取得）
2. **デプロイ: no**（rejected、または accepted_with_conditions かつ deploy:no）→
   デプロイ・退役は不要。そのまま retrospective 起動へ進む（`pr-review-watcher` Step 7-4 から再開）
3. **デプロイ: yes** かつ後続に「デプロイ完了」コメントが無い →
   retrospective 起動より **先に** `pr-review-watcher` Step 7-3.5（デプロイ → 疎通確認 → 退役）を
   実行してから 4（retrospective）へ進む（`trigger_workers_build.py` / `npm run deploy`（フォールバック）/
   `retire_preview_aliases.py` はいずれも idempotent なので再実行しても安全）
4. **デプロイ: yes** かつ後続に「デプロイ完了」コメントが既にある →
   デプロイ・退役は完了済み。retrospective 未実行なら Step 7-4 から再開
```

新規ラベル・新規 state ファイルは作らない（既存の Issue コメント読み取りだけで判定する）。

### Step 5 が `type` で絞らない理由（孤児 Issue の回収）

`type:improvement` / `type:bug` だけを対象にすると、`SP-n` 規約を持たない `type:feature` や
`type:docs` の `status:waiting-claude` Issue が **どのブランチにも該当せず永久に放置される**
（CP-3「Issue / PR ゼロ放置」に反する構造。実測で 2 件検出）。よって Step 5 の対象は
**`SP-n` 以外のすべての `status:waiting-claude` Issue** とし、`type` では絞らない。

- **二重取得はしない**: `SP-n` タイトル規約（`^SP-(\d+):`）に一致する Issue は Step 3.5 / Step 4 の
  担当であり、Step 5 の対象から除外する。委譲先の `self-improvement-loop` 消化モードも同じ除外を
  実装しているため（`type:retro-try` と `SP-n` だけを落とし `type` では絞らない）、Step 5 が渡した
  孤児 Issue はそのまま処理される。責務境界の正本は `improvement-lane-map.md` §2 ルール 1
- **着手できないものは `status:blocked`**: 前提が未成立の Issue（例: `SP-4` 完了が前提の CI 作業）は
  `status:waiting-claude` ではなく `status:blocked` を付け、解除条件を本文に書く。`status:blocked` は
  Step 5 の対象外である（§10 の完了定義）
- `type:retro-try` は振り返りレーン（`retro-try-handler`）の担当なので Step 5 の対象からは外す
  （`improvement-lane-map.md`）。**外した先は Step 5.5 が拾う**（#377）。かつては外すだけで
  受け皿が無く、`type:retro-try` が決定木のどのブランチからも起動されずに滞留していた
  （open の 6 割が到達不能だった）。Step 5.5 を消すなら同時に本行の除外も撤回すること

### Step 3 が拾わない `status:in-progress`（#419）

Step 3 の対象は「**Sprint Planning コメントがある** Issue」で、これは `SP-n` スプリントの着手時に
投稿されるもの。`type:retro-try` の Issue には付かないため、Step 5.5 で着手して中断した
retro-try Issue は Step 3 では再開されない。**その再開は Step 5.5 の条件 ① が担う**
（`status:in-progress` かつ 4 時間超 stale）。Step 3 の条件は変更しない（他ファイルから
Step 番号と条件を名指しで参照されているため）。

🔴 **同じ隙間が「非 `SP-n` かつ非 `type:retro-try`」の Issue にも空いていた**（#452 で実測: `status:in-progress`
のまま滞留する非 `SP-n` Issue が 7 件）。Step 3（`SP-n` 限定）も Step 5.5 ①（`type:retro-try` 限定）も拾わず、
Step 5 は `status:waiting-claude` しか見ていなかったため、**着手だけして力尽きた Issue が二度と再開されなかった**。
その再開は **Step 5 の条件 ①** が担う。1 firing 1 件で逐次処理する運用（提出前ゲート）はこの穴を直撃するため、
ゲートの有無にかかわらず恒久の条件として置く。

### エージング（Step 4 の飢餓防止・§5 で詳述）

Step 2 が毎回埋まり続けると Step 4 に永久に到達しない構造的リスクがある。Ready な `SP-n` があるのに
直近 **3 日** Step 4 が一度も実行されていなければ、**その firing だけ Step 2 を 1 回後回しにして Step 4 を
差し込む**（判定手段は §5）。

### Ready の定義（着手可能条件・Step 3.5 / Step 4 共通）

**正本は `docs/02_requirements/user-story-map.md` §7 運用ルール 9**（5 条件）。本スキルには複製しない
（要件書と実装の着手条件がずれると、要件書を読んだ人間が「Ready なはず」と考えた Issue が起票されない、
あるいは逆に本来ブロックすべき Issue が着手される）。`tools/sprint_backlog_sync.py` も同じ定義を実装する。

---

## §4 Step 4（開発レーン）の内部手順

````
4-0. SP-4 ハードゲート: 着手先が SP-4 以降 かつ SP-4（テスト基盤・CI）が未 Closed なら、
     着手対象を SP-4 に強制上書きする（SP-4 が終わらないと以降のスプリントの TDD 検証・
     プレビュー確認が成立しないため）。

4-1. 対象選定: 未 Closed の SP-n のうち **数値昇順で最小の番号**を選ぶ（4-0 のハードゲート適用後）。
     `user-story-map.md` §5.3 の Markdown を毎 firing パースしない（Ready 判定は Issue ラベル・
     本文の ID 参照・先行 SP-n の Closed 状態から機械判定する）。

4-1.5. **並行安全性判定（#197）**: 4-1 で選んだ候補が、他セッションのオープン PR とファイル競合
     しないかを `tools/check_parallel_safety.py` で機械判定する（目視突き合わせでの誤判定 — Issue
     タイトル・本文だけから変更ファイルを推測し、実装調査より前に「並行可能」と結論して着手後に
     衝突が判明した実例 — の再発防止）。

     1. オープン PR の変更ファイルを取得する: `mcp__github__pull_request_read(method="get_files",
        pullNumber=N)` の生 JSON を一時ファイル（例 `/tmp/pr_<N>_files.json`）に保存する
        （オープン PR が 0 件なら `--in-flight` 系の指定なしで実行してよい）。🔴 **`get_files` は
        `perPage` / `page` のページング API**（既定では 1 ページ分しか返らない）。変更ファイル数が
        既定ページサイズを超えうる PR では `perPage=100` を指定し、`page` を進めて全ページ取得する。
        ページごとに別ファイルへ保存してよい（`--in-flight-json` は繰り返し指定でき、複数ページを
        1 回の実行にそのまま渡せる）。全ページを渡さないと、衝突しているのに `parallel_safe` と
        誤判定しうる（ファイル数が多く衝突リスクが最も高い PR ほど見落としの被害が大きい）。
     2. 候補 SP-n の想定変更ファイルは、Issue 本文（`user-story-map.md` §5.3 該当セクションの
        対象パス記載）に書いてあればそれを使い、書いていなければ **未確定** として
        `--candidate "SP-n:"`（コロンの後を空）で渡す。
     3. 実行する:
        ```bash
        python3 tools/check_parallel_safety.py \
            --in-flight-json /tmp/pr_<N>_files.json \
            --candidate "SP-n:glob1,glob2" \
            --json
        ```
     4. 終了コード別の行動:
        - `1`（conflict）→ この候補は選ばない。4-1 に戻り次の Ready な SP-n を選び直す
          （無ければ Step 9 no-op へフォールスルー）
        - `3`（undetermined）→ 🔴 **「並行可能」と報告しない**。先に実装調査（コード探索）で
          想定変更ファイルを確定させ、確定した一覧で再実行してから 4-2 へ進む。**未宣言
          （`--candidate "SP-n:"`）だけでなく、宣言した glob が 1 件も展開できなかった場合
          （対象ディレクトリが未作成等）も同じ `3` になる**。後者は実ファイルパスがまだ存在しない
          ケースなので、対象ディレクトリが未作成なら実装調査で確定する予定の実ファイルパスで
          宣言し直すか、実装調査そのものを先に進めてから再実行する
        - `0`（parallel_safe）→ 4-2 へ進む。ただし着手後に想定外のファイルが必要と判明したら
          **その時点で再実行する**（判定は着手前の一度きりではない）
     5. 実行コマンドと判定結果を 4-3 の Sprint Planning コメントに含める。

4-2. `status:in-progress` 付与（処理の最初のアクション・CP-4 論理ロック）。

4-3. Sprint Planning コメントを投稿する。**編成の既定（単独実行禁止・sp 別の役割数）の正本は
     `docs/rules/session-sprint-rules.md` §2**。本スキルは参照のみで、性質別・sp 別の分岐を
     SKILL.md に複製しない（しきい値を片方だけ直すと、無人ルーティンが古い基準で並列/単独を
     判定し続ける）。チーム編成の記録先は既存の `編成` 欄であり、新しい記録先は作らない。
     **4-1.5 の並行安全性判定（実行コマンド + 判定結果）も同コメントに含める**
     （目視で決めていないことを事後検証可能にする）。

4-4. `sprint-development-rules.md` の `SD-1`〜`SD-4` をそのまま実行する:
     - `SD-4`（ドキュメントを読んで自律的に動く）: 着手時に `user-story-map.md` §5.3 の該当
       `SP-n` → `prd.md` の参照要件 ID と該当 `AC-n` → `prd.md` §13 未決事項 → `inception-deck.md`
       Q4 → `project-mission.md` の順で読む。**アプリコードを書く firing では続けて
       `docs/rules/architecture-rules.md` を読む**（層の判定・依存規則 7 項目・DDD の語彙規律・
       TDD の最低ライン。定義の正本である `application-architecture.md` / `domain-model.md` /
       `testing-strategy.md` への入口になっている）
     - `SD-2`（TDD 主体）: Red → Green → Refactor。操作レビュー手順を E2E に写す。
       **道具・層分担・フレームワーク由来の制約の正本は `docs/04_development/testing-strategy.md`**
       （本スキルには複製しない）
     - **新しいドメイン語を導入したら `docs/03_design/data-model/domain-model.md` を同じ PR で更新する**
       （ユビキタス言語はコードと同時に更新されて初めて機能する）
     - **縦切りの判定境界（3 層・強制力の 4 段）**: 正本は
       `docs/02_requirements/user-story-map.md` §5.2（層ごとの対象パスと、`C-5` 違反 = blocking /
       `SP-1` の 3 層必須 = blocking / 機能スプリントの 2 層以上 = warning / イネイブラー単独 = exempt）。
       本スキルには複製しない。判定は `tools/self_review_check.py` が PR 前チェックで機械実行するため、
       本スキルは **判定結果に従うだけ**でよい。
     - **無人 firing での SD-3 第 2 系統（仕様解釈の分岐）**: §6 の手順に従う。
     - `SP-8`（ログイン）の E2E は `infrastructure-design.md` §8.1 の記載どおり、プレビュー URL
       では実行不能なため、ダミー OAuth 設定の **ローカルビルド**に対して実行する（この 1 件だけ
       実行対象を切り替える）。

4-5. PR 本文の必須項目: `Sprint Goal:` 1 行 / `sp:N` / `Team:` トレーラー（`編成` 欄の同期コピー） /
     `Session-Id: $CLAUDE_CODE_SESSION_ID` /
     **`tools/run_checks.sh` の結果（PASS / FAIL）** / プレビュー URL（`wrangler versions upload
     --preview-alias pr-<N>` で取得。出せない場合は理由とローカル起動手順） / 参照要件 ID（既存必須項目そのまま。
     手順の正本は `docs/rules/pr-review-flow-summary.md`「PR 作成時の必須事項」・本スキルには複製しない。
     `session-sprint-rules.md` の「スプリントプランニング」節 / `sprint-development-rules.md` `SD-1` 準拠）。
     🔴 **`Closes #{Issue番号}` は書かない**（クローズは `pr-review-watcher` Step 7 の最終アクション。
     マージ時に閉じると Step 7 中断時に Step 3 が再開できなくなる）。

4-6. `pr-review-watcher` へ継続（Layer1 セルフレビュー → 指摘対応 → マージ → 公開反映）。
     マージ後のスプリントレビュー + レトロスペクティブは `pr-review-watcher` 側で必ず実行される
     （本スキルは呼び出し元を持たない）。
     ここで firing のセッション予算が尽きたら、コミット済みの内容と `status:in-progress` ラベルだけが
     生き残る。次の該当 firing は Step 2（自分の PR）または Step 3（stale 再開）で拾う。
````

---

## §5 飢餓防止（エージング）

**判定手段は GitHub 上の情報だけ**（新規 state ファイル禁止）:

```
1. Step 3.5 / Step 4 の対象クエリで Ready な SP-n の Issue の有無を確認する
2. Step 4 の最終実行時刻を、直近の `SP-{n}:` タイトルを持つ Issue の
   `status:in-progress` 付与コメント（Sprint Planning コメント）の投稿日時、または
   直近のマージ済み SP-n PR のマージ日時のうち新しい方から推定する
   （専用ログを持たず、既存アーティファクトの日付を読むだけで再計算できる）
3. Ready な SP-n が存在し、かつ 2 の推定時刻から 3 日以上経過していれば、
   この firing に限り Step 2 の判定を 1 回後回しにして Step 4 を実行する
   （Step 2 の対象 PR は次回 firing 以降に持ち越しても CP-4 上問題ない
   ＝ pr-review-watcher の active_session 判定・stale 判定がそのまま安全弁になる）

4. Step 5.5（retro-try）の飢餓防止（#377 / #419）:
   次のどちらかを満たしたら、この firing に限り Step 5 の判定を後回しにして Step 5.5 を実行する。
   **① を ② より優先して選定する**。
   - **①（再開・優先）**: `status:in-progress` かつ `type:retro-try` の Issue が **4 時間超 stale**。
     着手して中断したものの回収で、放置すると CP-4 の論理ロックが永久に解放されない。
     **経過時間の条件を課さない**（Step 5 の在庫は常に 2 桁あるため、①にオーバーライドを与えないと
     Step 5 に永久に先を越されて条件が書いてあるだけになる）。
   - **②（新規消化）**: `status:waiting-claude` かつ `type:retro-try` の Issue が存在し、**直近の
     retro-try 対応から 8 時間以上経過**している。
   直近の対応時刻は直近 closed の `type:retro-try` Issue の `closed_at` から逆算する
   （`mcp__github__list_issues(state="CLOSED", labels=["type:retro-try"],
   orderBy="UPDATED_AT", direction="DESC", perPage=1)`）。専用ログもラベルも新設しない。
   🔴 **closed の `type:retro-try` が 0 件のとき**（プロジェクト初期など）は「無限に経過済み」と
   みなして Step 5.5 を実行する。逆に解釈する（経過 0 として非該当にする）と、一度も消化されて
   いないから永久に消化されない、という #377 そのものが再発する。
```

### なぜ Step 5.5 にエージングが要るか（#377・実測）

Step 5 の対象プール（`SP-n` 規約に一致しない `status:waiting-claude` Issue）は実測で常時 2 桁の
在庫を抱えており、**ほぼ常に真** になる。「1 firing = 上から該当する最初の 1 ブランチだけ」という
設計上、エージングが無ければ Step 5 より下は永久に評価されない。Step 5.5 を単に足すだけでは
`type:retro-try` の滞留は解消しない。

閾値を 8 時間にした理由: 2 時間おきの cron に対し 1 日 3 回（`floor(24/8)`）Step 5.5 を通せる。
これより短くする（例: 4 時間 = 1 日 6 回）と Step 5 自身が実質停止し、retro-try の飢餓を
Step 5 側の飢餓にすり替えるだけになる（CP-3 違反の移動）。

---

## §6 無人 firing での `SD-3`（仕様解釈分岐）

`sprint-development-rules.md` `SD-3` は「仕様解釈が 2 通り以上あり成果物が変わる場合は
`AskUserQuestion` で確認する」と定めるが、**無人 cron 起動では応答するユーザーがいない**。

🔴 **判定基準（続行してよい 3 条件）と、その根拠の正本は
`docs/rules/sprint-development-rules-detail.md` §3.3。** 本スキルには複製しない
（片方だけ調整すると、無人実行の実際の判定と人間が読む説明が食い違う）。
グレーゾーンに遭遇したら **まず同 §3.3 を Read して 3 条件を判定する**。

判定後に本スキルが行うこと:

```
3 条件すべてを満たす（＝続行）
  → 推奨案を採用して実装を続行し、PR 本文と Issue コメントに §3.3 の書式で仮定を 1 行記録する

1 つでも満たさない（＝待つ）
  → 実装せず `status:waiting-user` Issue を下記テンプレートで起票し、
    そのスプリントは飛ばして次の Ready な SP-n へフォールスルーする（ルーティン全体は止めない）
```

`status:waiting-user` Issue のテンプレート（選択肢は最大 2 つ・各 1 行の判断材料・推奨明示。
`user-confirmation-minimization.md` §3 item 8 準拠）:

```markdown
## 仕様解釈の分岐（無人 firing のため実装を保留）

**対象**: SP-{n}（#{Issue番号}）
**曖昧点**: {1 文}
**選択肢**:

- A: {解釈A}（{判断材料 1 行}）
- B: {解釈B}（{判断材料 1 行}）

**推奨**: {A または B}（理由 1 行）
**保留理由**: 3 条件のうち {不成立の条件} を満たさないため無人実行では続行しない
```

🔴 **Claude 内部の議論（`discussion-review`）の結論を「ユーザーの答え」の代わりにしない**（`D-12` 違反）。
`discussion-review` を使ってよいのは「3 条件のどれに該当するかの判定が曖昧なとき」に限り、
判定結果が「待つ」なら `discussion-review` の結論でユーザー確認を省略しない。

---

## §7 健全な中断（満たさずに firing を終えない）

firing のセッション予算が尽きそうになったら、**`docs/rules/sprint-development-rules-detail.md` §5.1
「中断時チェックリスト」の 4 条件**（正本）を満たす状態に整えてから終える。条件の実体は同ファイルにあり、
本スキルには複製しない（片方だけ直すと、無人ルーティンと人間のレビューで中断可否の基準がずれる）。

次に該当 firing が来たとき Step 3（stale 再開）がここから続きを拾う。

---

## §8 失敗モード別の自己回復

| 失敗モード                                          | 検知                                                                                       | 次回 firing の回復経路                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| --------------------------------------------------- | ------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| プレビュー URL 不出                                 | PR 本文に「プレビュー URL なし」明記（`sprint-development-rules-detail.md` §1.3 既定動作） | Step 2 で `pr-review-watcher` が継続。A-6 相当なら waiting-user Issue 化済みのはずなので Step 5 の対象にもなる                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| CI 赤                                               | `pr-review-watcher` Step 2 が検知                                                          | Step 2 で継続対応。放置なら次々回 firing でも同じ Step 2 が拾う（PR が閉じない限り自然回復）                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| A-4 サーキットブレーカー発動（修正サイクル 2 回超） | 該当箇所での修正試行回数                                                                   | 該当 Issue/PR に `status:blocked` を付与。**Step 3 / Step 4 の対象クエリから除外**（`status:blocked` を除外条件に必ず含める・`self-improvement-loop` の除外リストと同じ書式）。waiting-user 通知は `user-notification-triage.md` の A 区分基準どおり必要時のみ                                                                                                                                                                                                                                                                                             |
| セッション圧縮（コンテキスト 95%）                  | `post-compact.sh` フックが自動コミット                                                     | 元々 ephemeral なので特別対応不要。圧縮後もその firing 内で継続。firing 自体が尽きたら Step 3 の再開経路に合流                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| スプリントが 1 firing に収まらない                  | Step 3 の stale 判定（4 時間）                                                             | §7 の健全な中断状態から §3 の Step 3 の再開手順で続きを判定（git log と Sprint Planning コメントから SD ステップを特定して再開）。🔴 **同一 `SP-n` が 3 回の firing を跨いでも `SD-1`（プレビュー URL を貼った PR）に到達しない場合は、次の着手時に分割する**（回数は Issue のコメント履歴＝ Sprint Planning コメントと進捗コメントの件数で数える。新規 state ファイルは作らない）。切る場所と番号は `user-story-map.md` §5.3 の該当 `SP-n` に事前明記してある場合それに従い、無ければ「操作レビュー手順の前半で切れる位置」で切って末尾番号を振る（§7-7） |

---

## §9 在庫枯渇（`M-3` 到達）

`roadmap.md` の `M-3`（積み上げマイルストーン・`SP-12` 以降）に対応する全 `SP-n` が Closed になり、
Step 3.5 が Ready 判定を満たす次の `SP-n` を発見できなくなった時点で **在庫枯渇** と判定する。

```
在庫枯渇を検知したら:
  1. `[Milestone] M-3 到達` Issue が既にオープンでないか確認する（重複起票防止）
  2. 無ければ 1 回だけ起票する（A-5 相当・@mention）。本文に roadmap.md M-4（公開判断ゲート）が
     要求する Claude が自己生成できない入力（R-5 逆算の TTL 反映・R-6 運用コスト試算・
     R-8 GitHub 利用規約確認）を列挙し、飼い主に公開判断を促す
  3. 以後は「この Issue が open か」だけで在庫枯渇状態を判定する（state ファイル不要）。
     open のままなら Step 4 は恒常的に空振りし、決定木は Step 5（改善 Issue 消化）へ
     フォールスルーし続ける（ルーティンは止まらない）
```

---

## §10 完了・成功の定義

- [ ] 1 firing で決定木の該当ブランチが正しく特定でき、上位ステップを飛ばして実行していない
- [ ] Step 0.0 のチャネル判定を毎 firing 実施している（前回の判定結果を恒久前提にしていない）
- [ ] Step 0.2（本番ドリフト検査）を Step 0.1 以降のどのブランチよりも先に評価している（#451。
      到達不能な分岐を作っていないか評価順を確認する）
- [ ] Step 4 着手時、`SD-1`〜`SD-4` を省略していない（プレビュー URL・TDD・縦切り・ドキュメント参照）
- [ ] 無人 firing で `AskUserQuestion` を使っていない（§6 の 3 条件判定で代替している）
- [ ] `status:blocked` の Issue/PR が Step 3 / Step 4 / Step 5 の対象から除外されている
- [ ] Step 5 で `SP-n` 以外の `status:waiting-claude` Issue を `type` で取りこぼしていない
- [ ] `type:retro-try` の Issue が Step 5.5 から到達可能で、エージング（§5-4）により飢餓していない
      （`python3 tools/check_lane_reachability.py` が PASS する・#377）
- [ ] 健全な中断の 4 条件（§7）を満たさずに firing を終えていない
- [ ] `[Milestone] M-3 到達` Issue が重複起票されていない（既存 open Issue の有無で判定済み）

---

## §11 参照

| ドキュメント                                                                             | 関係                                                                                                                                    |
| ---------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| `docs/routines/sprint-cycle-routine.md`                                                  | 本スキルを起動するルーティン設定（cron・貼り付けプロンプト）                                                                            |
| `docs/rules/sprint-development-rules.md`                                                 | `SD-1`〜`SD-4`（Step 4 が実行する 4 規律の本体）                                                                                        |
| `docs/rules/sprint-development-rules-detail.md`                                          | 中断時チェックリスト・無人実行モードの詳細補足                                                                                          |
| `docs/rules/session-sprint-rules.md`                                                     | スプリントの単位・`sp:N`・Sprint Planning コメント書式（編成欄含む）                                                                    |
| `docs/02_requirements/user-story-map.md`                                                 | `SP-n` の仕様本体（§5.3）・`C-5`・Ready/Done の定義（§7）                                                                               |
| `docs/02_requirements/roadmap.md`                                                        | `M-3`（積み上げ）・`M-4`（公開判断ゲート）の定義                                                                                        |
| `docs/rules/improvement-lane-map.md`                                                     | 既存 4 レーンとの責務境界（本スキルの Step 4 が第 4 レーン）                                                                            |
| `docs/rules/user-confirmation-minimization.md`                                           | `AskUserQuestion` の書式規約（§6 の Issue テンプレートが準拠）                                                                          |
| `docs/rules/github-mcp-fallback-patterns.md`                                             | Step 0.0 の API チャネル判定の根拠 SSOT                                                                                                 |
| `.claude/skills/claude-code-spec-sync/SKILL.md`                                          | Step 1 / Step 8 の委譲先                                                                                                                |
| `.claude/skills/pr-review-watcher/SKILL.md`                                              | Step 2 / Step 3（PR 済み）/ Step 4-6 の委譲先                                                                                           |
| `.claude/skills/self-improvement-loop/SKILL.md`                                          | Step 5（消化モード）/ Step 7（整理モード）の委譲先                                                                                      |
| `.claude/skills/retro-try-handler/SKILL.md`                                              | Step 5.5（`type:retro-try` の消化）の委譲先（#377）                                                                                     |
| `tools/check_lane_reachability.py`                                                       | レーン定義のスキルが決定木・他スキル・hooks から到達可能かの機械検査（#377 の再発検知）                                                 |
| `tools/check_prod_drift.py`                                                              | Step 0.2 が呼ぶ本番乖離判定（本判定は本番疎通に依存するため `run_checks.sh` には `--self-test` のみ配線）                               |
| `tools/trigger_workers_build.py`                                                         | Step 0.2 が呼ぶ Workers Builds 再トリガー（内部でデプロイゲートを再確認・#451）                                                         |
| `.claude/skills/workflow-health-check/SKILL.md` / `.claude/skills/project-sync/SKILL.md` | Step 6（衛生）の委譲先                                                                                                                  |
| `tools/sprint_backlog_sync.py`                                                           | Step 3.5 の SP→Issue 同期スクリプト（本スキルは呼び出し方のみ持ち、パース・判定ロジックは持たない）                                     |
| `tools/check_parallel_safety.py`                                                         | Step 4-1.5 の並行安全性判定スクリプト（CLI 契約・判定思想の詳細は `docs/rules/session-concurrency-rules-detail.md`「レイヤー 1 補強」） |
| `tools/self_review_check.py`                                                             | 縦切り・`C-5`・TDD 順序の機械判定（PR 前チェック）                                                                                      |
| `content/discussions/sprint-cycle-design-20260818/whiteboard.md`                         | 本設計の議論全文・却下案・合意経緯                                                                                                      |
| `content/discussions/sprint-env-lifecycle-20260820/whiteboard.md`                        | Step 3 の「デプロイ・退役未完了の検出」の議論全文（削除不可・張り替え方式・デプロイゲートの決定経緯）                                   |
