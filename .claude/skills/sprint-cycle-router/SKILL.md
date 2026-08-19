---
name: sprint-cycle-router
description: 単一ルーティン（N 時間ごとの cron 起動）でスプリント開発を自走させる決定木ルーター。破壊的変更対応・自 PR 回収・進行中スプリント再開・SP→Issue 同期・新規スプリント着手（TDD・縦切り・専門チーム編成）・改善Issue消化・衛生・週次リファインメント・spec-sync 検証の 9 ブランチから、1 firing につき該当する最初の 1 つだけを実行する。「スプリント自走ルーティン」「N 時間ごとの開発を進めて」「スプリントサイクルを回して」「/sprint-cycle-router」と依頼された時、またはルーティン設定（`docs/routines/sprint-cycle-routine.md`）から自動起動する時に使用する。各ブランチの実処理は既存パイプラインスキル（`claude-code-spec-sync` / `pr-review-watcher` / `self-improvement-loop` / `workflow-health-check` / `project-sync`）に委譲し、本スキル自身は「今どのブランチを実行すべきか」の判定と Step4（新規スプリント着手）の内部手順だけを持つ。改善Issueの発見・棚卸し自体は `self-improvement-loop`、リポジトリ衛生の監査自体は `workflow-health-check` の担当（本スキルはそれらの呼び出し元）。
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
4. 全滅 → GitHub API 完全不通。Issue/PR 依存の Step 1〜8 は実行不能と判定し、
   git 単独で判定できる範囲（ローカルに push 漏れのコミットが無いか等）だけ確認して **安全側 no-op**。
   ログを残さず何もしない（永続化先が無い。次回 firing が独立に再判定するのが ephemeral 前提と一致する。
   中途半端なローカル state ファイルを新設しない）。
```

---

## §2 Step 0.1: 早期リターン判定

数クエリで「今回やることが無い」を判定して安く抜ける。**a〜d のいずれかが該当した時点で該当ステップに
進み、全て非該当なら Step 9（no-op）へ**。

```
a) [CC-Sync 破壊的変更] `lane:claude-code-spec` かつ `[CC-Sync][破壊的変更]` の open Issue の存在チェック（1 クエリ）
b) 自分の in-progress Issue / open PR の存在チェック（`check_pending_pr_reviews.py --mine --actionable-only`
   相当・1 クエリ。§1 のチャネルに応じて MCP/gh/curl 手動実装のいずれかで実行）
c) `status:waiting-claude` の **非 `SP-n`** Issue の在庫チェック（1 クエリ・`type` は問わない）
d) 当日の衛生スロット実施済みか（`project-sync` のログ相当・当日の Issue コメント日付や
   `workflow-health-check` 実行痕跡から判定・1 クエリ。新規 state ファイルは作らない）
```

早期リターンのコストが数クエリに収まるからこそ、cron を短い間隔で回せる（§0）。

---

## §3 決定木 Step 1〜9

**1 firing = 上から該当する最初の 1 ブランチだけ実行する。** 優先順位の設計原則: 「今動いている作業を
完走させる（Step 1〜3）」>「新しい価値を作る（Step 4）」>「バックログの健全性を保つ（Step 5〜8）」。

| Step | 判定条件（機械的に書く） | 実行内容 | 委譲先スキル |
|---|---|---|---|
| **1** | `lane:claude-code-spec` かつ `[CC-Sync][破壊的変更]` の open Issue が存在する | 即対応（他ブランチより最優先・既存仕様どおり） | `claude-code-spec-sync` Step1 |
| **2** | `check_pending_pr_reviews.py --mine --actionable-only`（相当）が非空 | レビュー対応・自動マージ・公開反映まで継続。新規スプリント着手より優先（CP-4: 中途 PR を放置して新規に手を広げない） | `pr-review-watcher` |
| **3** | `status:in-progress` かつ Sprint Planning コメントがある Issue のうち `updated_at` が **4 時間超 stale**（4 時間未満は他セッション対応中とみなし触らない） | 前回 firing が力尽きた形跡。git log とIssue コメント（Sprint Planning・仮定記録・「進捗: {SD ステップ名 **または Sprint Review**}まで完了。次は {次にやること}」1 行）から続きを判定し再開（手順は §7 の中断条件と対）。対応する open PR があれば Step 2 と同じ扱いに合流 | `pr-review-watcher`（PR 済みなら）/ 自前（PR 未作成なら §4 の 4-4 以降から再開） |
| **3.5** | Ready 判定（下記「Ready の定義」5 条件）を満たす次の `SP-n` の Issue が **無い** | `tools/sprint_backlog_sync.py` を実行し、**その 1 件だけ** 起票する（先読み複数起票はしない＝CP-4 のロックと相性が悪く他セッションの着手余地を奪う）。起票は Issue 作成に限定した副作用。呼び出し方のみ本スキルが持ち、スクリプト内部のパース・判定ロジックは持たない | `tools/sprint_backlog_sync.py` |
| **4** | Ready な `SP-n` の Issue が存在する（Step 3.5 の結果、必ず 0 件か 1 件） | 新規スプリント着手。内部手順は §4 | 自前（`pr-review-watcher` へ Step 4-6 で継続） |
| **5** | `status:waiting-claude` の Issue のうち、タイトルが `SP-n` 規約（`^SP-(\d+):`）に一致しないものが存在する（**`type` で絞らない**） | バックログ消化（既定 5 件/回。本ルーティンでは firing の残り予算次第で件数を絞ってよい） | `self-improvement-loop` 消化モード |
| **6** | 当日の衛生スロット未実施（`project-sync` ログなし） | 監査・衛生 | `workflow-health-check` 軽量版 → `project-sync` |
| **7** | `config/backlog_refinement_state.json` の `last_refinement_at` から 7 日超 | リファインメント週次ゲート | `self-improvement-loop` 整理モード Step G-1.5〜G-6 <!-- refcheck:ignore --> |
| **8** | `[CC-Sync][検証]` の open Issue が残っている | 検証 Issue 対応（1 件のみ） | `claude-code-spec-sync` Step2 |
| **9** | 全部空 | no-op。`routine-idle` 通知は既存の 1 日 1 回自己抑制のまま | — |

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
- `type:retro-try` は振り返りレーン（`retro-try-handler`）の担当なので従来どおり除外する
  （`improvement-lane-map.md`）

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

```
4-0. SP-4 ハードゲート: 着手先が SP-4 以降 かつ SP-4（テスト基盤・CI）が未 Closed なら、
     着手対象を SP-4 に強制上書きする（SP-4 が終わらないと以降のスプリントの TDD 検証・
     プレビュー確認が成立しないため）。

4-1. 対象選定: 未 Closed の SP-n のうち **数値昇順で最小の番号**を選ぶ（4-0 のハードゲート適用後）。
     `user-story-map.md` §5.3 の Markdown を毎 firing パースしない（Ready 判定は Issue ラベル・
     本文の ID 参照・先行 SP-n の Closed 状態から機械判定する）。

4-2. `status:in-progress` 付与（処理の最初のアクション・CP-4 論理ロック）。

4-3. Sprint Planning コメントを投稿する。**編成の既定（単独実行禁止・sp 別の役割数）の正本は
     `docs/rules/session-sprint-rules.md` §2**。本スキルは参照のみで、性質別・sp 別の分岐を
     SKILL.md に複製しない（しきい値を片方だけ直すと、無人ルーティンが古い基準で並列/単独を
     判定し続ける）。チーム編成の記録先は既存の `編成` 欄であり、新しい記録先は作らない。

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
```

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
```

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

| 失敗モード | 検知 | 次回 firing の回復経路 |
|---|---|---|
| プレビュー URL 不出 | PR 本文に「プレビュー URL なし」明記（`sprint-development-rules-detail.md` §1.3 既定動作） | Step 2 で `pr-review-watcher` が継続。A-6 相当なら waiting-user Issue 化済みのはずなので Step 5 の対象にもなる |
| CI 赤 | `pr-review-watcher` Step 2 が検知 | Step 2 で継続対応。放置なら次々回 firing でも同じ Step 2 が拾う（PR が閉じない限り自然回復） |
| A-4 サーキットブレーカー発動（修正サイクル 2 回超） | 該当箇所での修正試行回数 | 該当 Issue/PR に `status:blocked` を付与。**Step 3 / Step 4 の対象クエリから除外**（`status:blocked` を除外条件に必ず含める・`self-improvement-loop` の除外リストと同じ書式）。waiting-user 通知は `user-notification-triage.md` の A 区分基準どおり必要時のみ |
| セッション圧縮（コンテキスト 95%） | `post-compact.sh` フックが自動コミット | 元々 ephemeral なので特別対応不要。圧縮後もその firing 内で継続。firing 自体が尽きたら Step 3 の再開経路に合流 |
| スプリントが 1 firing に収まらない | Step 3 の stale 判定（4 時間） | §7 の健全な中断状態から §3 の Step 3 の再開手順で続きを判定（git log と Sprint Planning コメントから SD ステップを特定して再開）。🔴 **同一 `SP-n` が 3 回の firing を跨いでも `SD-1`（プレビュー URL を貼った PR）に到達しない場合は、次の着手時に分割する**（回数は Issue のコメント履歴＝ Sprint Planning コメントと進捗コメントの件数で数える。新規 state ファイルは作らない）。切る場所と番号は `user-story-map.md` §5.3 の該当 `SP-n` に事前明記してある場合それに従い、無ければ「操作レビュー手順の前半で切れる位置」で切って末尾番号を振る（§7-7） |

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
- [ ] Step 4 着手時、`SD-1`〜`SD-4` を省略していない（プレビュー URL・TDD・縦切り・ドキュメント参照）
- [ ] 無人 firing で `AskUserQuestion` を使っていない（§6 の 3 条件判定で代替している）
- [ ] `status:blocked` の Issue/PR が Step 3 / Step 4 / Step 5 の対象から除外されている
- [ ] Step 5 で `SP-n` 以外の `status:waiting-claude` Issue を `type` で取りこぼしていない
- [ ] 健全な中断の 4 条件（§7）を満たさずに firing を終えていない
- [ ] `[Milestone] M-3 到達` Issue が重複起票されていない（既存 open Issue の有無で判定済み）

---

## §11 参照

| ドキュメント | 関係 |
|---|---|
| `docs/routines/sprint-cycle-routine.md` | 本スキルを起動するルーティン設定（cron・貼り付けプロンプト） |
| `docs/rules/sprint-development-rules.md` | `SD-1`〜`SD-4`（Step 4 が実行する 4 規律の本体） |
| `docs/rules/sprint-development-rules-detail.md` | 中断時チェックリスト・無人実行モードの詳細補足 |
| `docs/rules/session-sprint-rules.md` | スプリントの単位・`sp:N`・Sprint Planning コメント書式（編成欄含む） |
| `docs/02_requirements/user-story-map.md` | `SP-n` の仕様本体（§5.3）・`C-5`・Ready/Done の定義（§7） |
| `docs/02_requirements/roadmap.md` | `M-3`（積み上げ）・`M-4`（公開判断ゲート）の定義 |
| `docs/rules/improvement-lane-map.md` | 既存 4 レーンとの責務境界（本スキルの Step 4 が第 4 レーン） |
| `docs/rules/user-confirmation-minimization.md` | `AskUserQuestion` の書式規約（§6 の Issue テンプレートが準拠） |
| `docs/rules/github-mcp-fallback-patterns.md` | Step 0.0 の API チャネル判定の根拠 SSOT |
| `.claude/skills/claude-code-spec-sync/SKILL.md` | Step 1 / Step 8 の委譲先 |
| `.claude/skills/pr-review-watcher/SKILL.md` | Step 2 / Step 3（PR 済み）/ Step 4-6 の委譲先 |
| `.claude/skills/self-improvement-loop/SKILL.md` | Step 5（消化モード）/ Step 7（整理モード）の委譲先 |
| `.claude/skills/workflow-health-check/SKILL.md` / `.claude/skills/project-sync/SKILL.md` | Step 6（衛生）の委譲先 |
| `tools/sprint_backlog_sync.py` | Step 3.5 の SP→Issue 同期スクリプト（本スキルは呼び出し方のみ持ち、パース・判定ロジックは持たない） |
| `tools/self_review_check.py` | 縦切り・`C-5`・TDD 順序の機械判定（PR 前チェック） |
| `content/discussions/sprint-cycle-design-20260818/whiteboard.md` | 本設計の議論全文・却下案・合意経緯 |
