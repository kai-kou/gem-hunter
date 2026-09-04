<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: PR 差分の敵対的多観点レビュー（FAIR Layer 2）

- 議題ID: `pr-899`
- 論点: PR #899（sprint-cycle-router 決定木 Step 2 を bot 自動化 PR まで広げる / Closes #870）の Layer 2 議論型レビュー。対象: tools/check_pending_pr_reviews.py / .claude/skills/sprint-cycle-router/SKILL.md。差分 484 行（閾値 300 行）でトリガー。Layer 1（7 観点）は CONFIRMED 1 件（select_step2_targets が is_trusted_bot_pr を再実装している definition drift）/ PLAUSIBLE 1 件（SKILL.md §2 b) と §3 Step 2 の条件重複）を出している。round 2 では他レンズの claim を最低 1 件は名指しで反証または補強すること。
- 参加者: `correctness`, `counterexample`, `scope`, `maintenance`
- 投稿数: 15
- 更新: 2026-09-04T15:55:51+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

## ラウンド 1

### `scope` — 主張
<sub>2026-09-04T15:34:18+09:00</sub>

## claim: Issue #870 が明示要求する「check_lane_reachability.py 見送り理由の Issue 記録」が未実施

- **file:line**: Issue #870 本文（`対応方針`）/ PR #899 本文の「`check_lane_reachability.py` への検査追加は見送り（#870 方針 4 の結論）」セクション
- **severity**: WARNING
- **confidence**: CONFIRMED（`mcp__github__issue_read(method="get_comments", issue_number=870)` を実行し、コメントが Sprint Planning 投稿 1 件のみであることを確認。見送り理由の言及なし）
- **欠陥の1文**: Issue #870 の `対応方針` は「`check_lane_reachability.py` に検査を足せるか検討し、判定が広すぎて誤検知するなら見送り、**理由を本 Issue に記録する**」と明示しているが、見送り理由は PR #899 の本文にのみ書かれており、Issue #870 へは一度もコメントされていない。
- **失敗シナリオ**: 本 PR がマージされ Issue がクローズされると、Issue のコメント欄には「なぜ検査を追加しなかったか」の記録が残らない。将来 `check_lane_reachability.py` の拡張を検討する別セッション（`self-improvement-loop` の棚卸し等）が Issue #870 を参照しても判断根拠が見つからず、同じ検討を繰り返す（PR 本文は squash マージ後に探しにくく、Issue コメントに記録するのがこのルールの目的そのもの）。
- **推奨する直し方**: マージ前に `mcp__github__add_issue_comment`（or `issue_write`）で PR #899 本文の「`check_lane_reachability.py` への検査追加は見送り」セクションと同内容を Issue #870 へ 1 コメントとして転記する。

### `scope` — 主張
<sub>2026-09-04T15:34:18+09:00</sub>

## claim: 敵対的検証「指摘3」の対応が pr-review-watcher 側へ実装されておらず、ドキュメント上の宣言のみ

- **file:line**: `.claude/skills/sprint-cycle-router/SKILL.md` 決定木表 Step 2「実行内容」列（差分該当行、旧 `.claude/skills/pr-review-watcher/SKILL.md` は無改変）
- **severity**: WARNING
- **confidence**: CONFIRMED（`git diff origin/main...origin/claude/inspiring-lamport-2ofvhf --stat` で変更ファイルが `check_pending_pr_reviews.py` と `sprint-cycle-router/SKILL.md` の 2 件のみであることを確認。`pr-review-watcher/SKILL.md` に `active_session` の grep でマージ直前再チェックの記述は既存の 1 行のみで新規追加なし）
- **欠陥の1文**: PR 本文の「敵対的検証で見つかった3件」表は指摘3（bot PR の二重マージ露出）を「Step 2 実行内容に『マージ直前に `active_session` を再確認してから `merge_pull_request` を呼ぶ』を明記」として **本 PR 内で対応済み** と記載しているが、実際に `merge_pull_request` を呼ぶのは委譲先の `pr-review-watcher` スキルであり、その `SKILL.md` にはこの再チェック手順が一切追加されていない（router 側の表セルに文言があるだけで、実行主体側に手順が存在しない）。self-test でもこの再チェックの有無は検証されていない。
- **失敗シナリオ**: `pr-review-watcher` は自身の `SKILL.md` を読んで動くため、router 側テーブルの注記だけでは実行時に参照されない可能性が高い。2 firing が数分差で同じ bot 自動化 PR を Step 2 で選んだ場合、`pr-review-watcher` が旧来どおり素通しで `merge_pull_request` を呼び、指摘3が想定した二重マージ露出がそのまま残る。「対応済み」という PR 本文の記載が実装の欠落を覆い隠す。
- **推奨する直し方**: `pr-review-watcher/SKILL.md` のマージ直前手順（Step 6/7 相当）に「対象 PR が bot 自動化 PR の場合は `merge_pull_request` 直前に `active_session` を再取得し true なら中断する」を追記する。追記が難しければ、PR 本文の「対応済み」表現を「router 条文へ明記のみ・実行側への配線は別 Issue」へ訂正する。

### `correctness` — 主張
<sub>2026-09-04T15:36:26+09:00</sub>

## claim: SKILL.md 手動フォールバック仕様が branch↔author の対応を明示せず、trust boundary が緩む余地がある

- **file:line**: `.claude/skills/sprint-cycle-router/SKILL.md:79-81`（PR ブランチ版。差分では `+` 行として新規追加）
- **severity**: WARNING
- **confidence**: PLAUSIBLE
- **欠陥の1文**: gh / 内蔵 REST / MCP が全滅したときの curl 手動再実装手順が「ブランチが `dependabot/` 前方一致または `automation/gem-pool-refresh` 完全一致」と「著者が `dependabot[bot]` / `github-actions[bot]`（完全一致）」を **対になっていない 2 本の OR 条件** として書いており、実装側の `_is_automation_pr()` / `_is_dependabot_pr()`（`tools/check_pending_pr_reviews.py:1326-1381`）が守っている「ブランチパターンごとに対応する著者のみを許す」という 1 対 1 のペアリングを明文化していない。

- **失敗シナリオ**: gh・内蔵 REST フォールバック・MCP GitHub ツールが同時に全滅した状態（SKILL.md 本文がまさに想定している「最終手段」の状況）で、後続セッションが本文を文字どおり実装し、次のような素朴なロジックを書いたとする:
  ```
  is_bot = (branch.startswith("dependabot/") or branch == "automation/gem-pool-refresh") \
           and author in ("dependabot[bot]", "github-actions[bot]") \
           and not is_fork
  ```
  この場合、`branch == "automation/gem-pool-refresh"` かつ `author == "dependabot[bot]"`、あるいは `branch.startswith("dependabot/")` かつ `author == "github-actions[bot]"` という **本来ありえないはずの組み合わせ** も True 判定される。後者は、`secrets.GITHUB_TOKEN` で push 権限を持つ別のワークフロー（`gem-pool-refresh.yml` 以外の将来追加ワークフロー、あるいは設定ミス・ブランチ名変更）が誤って `dependabot/` 始まりのブランチ名で PR を作成した場合に現実的に起こりうる（著者ログインは GitHub がトークン種別から機械的に決めるため、`github-actions[bot]` 自体を偽装する必要はない）。このとき Python 実装の `_is_dependabot_pr()` は著者完全一致 `dependabot[bot]` を要求するため False（弾く）だが、SKILL.md を文字どおり実装した手動 curl フォールバックは True（通す）となり、信頼境界外の PR が Step 2 → `pr-review-watcher` の無人レビュー・自動マージ経路に誤って乗る。しかも本条件が発火するのは GitHub API 系がすべて不通という **平常時より検証の効きにくい状況** であるため、誤りが顕在化しにくい。
- **推奨する直し方**: SKILL.md の当該箇所を「`dependabot/` 前方一致 **のときは** 著者が `dependabot[bot]` 完全一致」「`automation/gem-pool-refresh` 完全一致 **のときは** 著者が `github-actions[bot]` 完全一致」のように、ブランチパターンと著者を明示的にペアで対応付ける書き方に直す（`_is_automation_pr()` / `_is_dependabot_pr()` の docstring と同じ 1:1 対応を文章にも反映する）。

---

## 確認事項（バグではないが検証した項目・参考）

- `select_step2_targets()` の呼び出し前に `main()` が全 PR に `is_mine` を無条件付与している（`tools/check_pending_pr_reviews.py:2903-2904`）ため、`--mine-or-automation` 選択で `KeyError("is_mine")` が起きる経路は無い。
- `analyze_pr()` の早期 return 経路（ラベルベース early exit・blocked/waiting-user）でも `is_automation_pr` / `is_dependabot_pr` が dict に追加されている（diff 該当箇所）ため、`--actionable-only` を付けない呼び出しでも `select_step2_targets()` が `KeyError` を起こさない。この修正は正しく、e2e テスト（早期 return 経路のケース）でも検証されている。
- `--mine` と `--mine-or-automation` は `argparse` の `mutually_exclusive_group` で機械的に排他化されており、同時指定は exit 2 になる。
- `_is_automation_pr()` / `_is_dependabot_pr()` 自体（Python 側）は fork 判定 `is_cross_repository is not False` による fail-closed、ブランチ完全一致 / 前方一致、著者完全一致の 3 条件 AND を正しく実装しており、この PR による劣化は見当たらない。

### `counterexample` — 主張
<sub>2026-09-04T15:36:51+09:00</sub>

## counterexample: 反例作成レンズでの検証結果（Round 1）

対象: `tools/check_pending_pr_reviews.py` の `select_step2_targets()` / `_is_automation_pr()` /
`_is_dependabot_pr()` / `--mine-or-automation` の argparse 相互排他 / セッション ID 必須検査 /
ラベル early-exit の 6 項目に対して、実際に Python から関数を呼び出し・`main()` を通した
E2E 実行・self-test への変異注入で反例作りを試みた。

### 結論サマリー

- **破れなかったもの（Layer 2 として緑を保証する）**: ①③④ の観点はいずれも堅牢。詳細は下記「破れなかった反例」。
- **破れたもの**: `_is_dependabot_pr()` のブランチ判定（③ 区別テストの有無）に **self-test が検知しない変異**
  が 1 件存在する（下記 claim 1）。ただし実運用での悪用可能性は低い（severity: NIT）。

---

### claim 1: `_is_dependabot_pr()` のブランチ判定（`startswith`）を `in`（部分一致）へ広げても、149 件の self-test が全て緑のまま通る

- **file:line**: `tools/check_pending_pr_reviews.py:1379`（`_is_dependabot_pr()` 内、`if not branch.startswith(DEPENDABOT_PR_BRANCH_PREFIX):`）
- **severity**: NIT（テストの盲点。実害の可能性は低い）
- **confidence**: CONFIRMED（実際に変異させて self-test を実行し、失敗ゼロを確認済み）

**欠陥の 1 文**: `_is_dependabot_pr()` の 3 条件 AND のうち「② ブランチ名前方一致」だけを検証する
self-test ケースが無く、`startswith` を `in`（部分一致）へ広げる変異を入れても
`_test_select_step2_targets_pure()` と `_test_main_mine_or_automation_e2e()` が両方とも 0 failures で通過する。

**再現手順**（実行済み・失敗ゼロを確認）:
```python
def mutated_is_dependabot_pr(branch, author_login, is_cross_repository):
    if is_cross_repository is not False:
        return False
    if DEPENDABOT_PR_BRANCH_PREFIX not in branch:   # 変異: startswith(prefix) -> `in`（部分一致）
        return False
    return author_login == DEPENDABOT_PR_AUTHOR_LOGIN

m._is_dependabot_pr = mutated_is_dependabot_pr
m._test_select_step2_targets_pure()       # => []
m._test_main_mine_or_automation_e2e()     # => []
```
既存の `dependabot_upper`（ブランチ `Dependabot/...` 大文字）・`dependabot_fork_unknown`
（`isCrossRepository=None`）・`dependabot_author_suffix` / `dependabot_author_prefix`
（著者ログインだけが外れる負ケース）はいずれも「大文字化で `startswith` が失敗する」または
「著者ログインが不一致」という別の条件で弾かれているため、**ブランチ条件だけを独立に固定する
負ケース**（例: 著者ログインは正しい `dependabot[bot]` のまま、ブランチが `dependabot/` を
先頭以外の位置に含む `feat/enable-dependabot/x` のような文字列）が 1 件も無い。

**失敗シナリオ（fail-open / fail-closed）**: この変異が仮に本番へ混入した場合、
`branch = "feat/enable-dependabot/x"`、`author_login = "dependabot[bot]"`、
`is_cross_repository = False` の PR があれば `is_dependabot_pr=True` になり
`select_step2_targets()` の対象（Step 2 の自動マージ経路）に混ざる → **fail-open 方向**。
ただし実際に GitHub 上でこの組み合わせ（ブランチ名は任意だが著者ログインが本物の
`dependabot[bot]` bot アカウント）を作ることは、人間の通常操作では不可能（著者ログインは
GitHub が PR 作成元 API から機械的に決める値で、Dependabot integration は常に
`dependabot/` 始まりのブランチしか作らない）。したがって **この変異単体は実運用のセキュリティ
ホールにはならない**が、③ の区別テストが「著者ログイン条件で事実上救われている」ことを意味し、
将来 `_is_dependabot_pr()` の著者比較条件（`==`）が緩む変更（例: `.lower() ==` 程度の
一見無害なリファクタ）と **複合した場合** に、ブランチ条件の緩みが検知されないまま見逃される
リスクがある（#725 が警告する「独立した対策の相互作用」の逆パターン: 一方の条件の弱さが
他方の条件の強さに隠れて自己テストから見えなくなっている）。

**推奨する直し方 1 行**: `_test_main_mine_or_automation_e2e()` の入力バリアントに、著者ログインは
`dependabot[bot]`（正しい値）のまま、ブランチだけを `"feat/enable-dependabot/x"`
（`dependabot/` を含むが先頭一致しない）にした負ケースを 1 件追加し、選択されないことを assert する。

---

### 破れなかった反例（Layer 2 の価値として記録）

以下はいずれも実際に入力を作って `select_step2_targets()` / `main()` を通したが、self-test の
既存ケースが正しく検知した（緑のまま通らなかった＝設計どおり）。

1. **① マッチのアンカー**: `select_step2_targets()` の `r["is_mine"]` / `r["is_automation_pr"]` /
   `r["is_dependabot_pr"]` は添字参照（`.get()` 不使用）。`analyze_pr()` の早期 return 経路
   （ラベル early-exit）でキーを欠落させる変異（`is_automation_pr` / `is_dependabot_pr` の代入行を
   早期 return の dict から削除）を試すと `KeyError` で **即座に落ちる**（fail-closed。握り潰さない）。
   これは docstring どおりの設計で、意図的な fail-closed。
2. **② 対象層の取り違え**: `is_mine` を著者ログイン（`author_login`）や `authorAssociation` から
   計算する変異、`is_automation_pr`/`is_dependabot_pr` の引数を `(author_login, branch, ...)` と
   入れ替える変異を試すと、`_test_main_mine_or_automation_e2e()` の
   `dependabot_author_suffix` / `automation_author_trailing_space` / `dependabot_author_prefix`
   ケース（著者ログインだけが外れる負ケース）が確実に検知する。
3. **③ 区別テスト（`_is_automation_pr()` 側）**: ブランチの完全一致 (`!=`) を前方一致
   (`startswith`) へ広げる変異は `automation_prefix`
   （`automation/gem-pool-refresh-evil`）ケースが検知する（`_is_dependabot_pr()` と非対称の
   厳しさになっている設計は正しく効いている）。
4. **④ 倒れる向き（`select_step2_targets()` の優先順位）**: 「自 PR が 1 件でもあれば bot PR を
   混ぜない」の `if mine: return mine` を「常に bot PR も足す」へ広げる変異、「自 PR 優先を外して
   常に bot PR 側を返す」変異は、いずれも case (a) `mine + dependabot → [1]` またはケース (g)
   `multiple mine + bots` が検知する。「他者の人手 PR も返す」（3 の無効化）変異は case (d)
   `other human only → []` が確実に検知する（fail-open の逆＝安全側の期待値をピンポイントで
   固定できている）。
5. **`--mine-or-automation` の argparse 相互排他 / セッション ID 必須検査**: `--mine` と
   `--mine-or-automation` の同時指定 exit 2、セッション ID 無しでの `--mine-or-automation` 使用
   exit 2 は、いずれも実際に `main()` を `SystemExit` 込みで通して確認済み（e2e テストが実測している）。
6. **ラベル early-exit（`_label_based_early_exit_status()`）の新経路での実効性**:
   `--actionable-only` を付けた場合に `status:blocked` / `status:waiting-user` の bot PR が
   `select_step2_targets()` の対象から正しく除外されることを確認。
   ⚠️ **設計上の注意点（バグではなく仕様の指摘）**: `select_step2_targets()` 自体はラベル状態を
   一切見ない純粋関数であり、呼び出し側が `--actionable-only` を付け忘れると
   `status:blocked`（A-4 サーキットブレーカー）の bot PR もそのまま選択対象に混ざる
   （実測: e2e テストの「早期 return 経路」ケースは意図的に `--actionable-only` を外し、
   108/109 が出力に含まれることを確認している＝仕様どおり）。これは `--mine` 側も同じ設計
   （フラグの独立性）であり #870 由来の新規欠陥ではないが、SKILL.md が
   「`--mine-or-automation --actionable-only` を必ず対で使う」と明記している以上、
   呼び出し側の規律に依存する点は Layer 1/main の判断に委ねる（自分のレンズの対象外）。

---
post by counterexample / round 1

### `maintenance` — 主張
<sub>2026-09-04T15:37:17+09:00</sub>

## claim: 敵対的検証#3「マージ直前 active_session 再確認」の記述先が実行者と食い違い、対応済み扱いが実質未実装

- **file:line**: `.claude/skills/sprint-cycle-router/SKILL.md:267`（PR ブランチ・Step 2 行「実行内容」列）
- **severity**: WARNING
- **confidence**: CONFIRMED（両 SKILL.md を実読して確認済み）

### 欠陥の1文
PR 本文が「本 PR 内で修正済み」と主張する敵対的検証#3（bot PR はレイヤー6所有判定を持たず、2 firing が同一 bot PR を選びうる露出）への対応「**マージ直前に `active_session` を再確認してから `merge_pull_request` を呼ぶ**」が、`sprint-cycle-router/SKILL.md` の Step 2 行にしか書かれていない。しかし Step 2 の「委譲先スキル」列は `pr-review-watcher` であり（同ファイル 267 行目末尾セル、および参照表 609 行目 `Step 2 / Step 3（PR 済み）/ Step 4-6 の委譲先`）、`merge_pull_request` を実際に呼ぶのは `pr-review-watcher`（`.claude/skills/pr-review-watcher/SKILL.md` 136 行目「自動マージ」・268 行目）である。本 PR は `pr-review-watcher/SKILL.md` を一切変更しておらず、同ファイルを grep しても `active_session` への言及は 1 箇所（290 行目）だけで、内容は「discovery 時点で `--actionable-only` が除外した PR には触れない」という既存の静的判定であり、**「マージを呼ぶ直前に鮮度を取り直す」という動的な再チェックの手順は存在しない**。

### 失敗シナリオ
2 つのルーティン firing が数分差で起動し、両方が Step 2 で同一のアイドル化した Dependabot/`automation/gem-pool-refresh` PR を選択（bot PR には `Session-Id:` 所有判定＝レイヤー6が無いため、`--mine-or-automation` はどちらの firing でも同じ bot PR を返しうる。PR 自身の敵対的検証#3 が指摘した露出そのもの）。両 firing とも `pr-review-watcher` へ委譲するが、`pr-review-watcher` 側に「マージ直前の再チェック」手順が無いため、どちらの実行も `active_session` を再確認せずに Layer 1 → マージへ進み、二重レビュー（片方は既にマージ済みの PR に対する無駄な Layer 1 実行や、解決済みスレッドへの重複コメント）が発生しうる。GitHub 側で二重マージ自体は失敗するとしても、"対応済み" と PR 本文が明記した緩和策が実際には一度も実行されない状態でマージまで進む。

### 推奨する直し方
`pr-review-watcher/SKILL.md` のマージ直前ステップ（136 行目付近）に、bot PR（`is_automation_pr` / `is_dependabot_pr`）を対象とする場合に限り `active_session` を再取得してから `merge_pull_request` を呼ぶ旨を追記する。追記できないなら、少なくとも `sprint-cycle-router/SKILL.md` 側の文言を「対応済み」から「`pr-review-watcher` 側に別途実装が必要（未着手）」へ訂正し、PR 本文の敵対的検証テーブルの #3 も「対応済み」ではなく「文書化のみ・実装は別 Issue」に修正する。

### `maintenance` — 主張
<sub>2026-09-04T15:37:20+09:00</sub>

## claim: 変異テスト11件の主張は静的検証では整合（実測の再現はしていない）

- **file:line**: `tools/check_pending_pr_reviews.py:2183-2251`（`_test_main_mine_or_automation_e2e` 内の負ケース定義）
- **severity**: NIT（欠陥ではなく検証結果の記録）
- **confidence**: PLAUSIBLE（コード読解による裏付け。自分では変異テストを再実行していない＝役割上の制約）

### 内容
PR 本文が「初回は検知できなかった」と正直に記す #9〜#11（`_is_dependabot_pr` / `_is_automation_pr` の著者比較 `==` → `.startswith` / `in` への変異）について、追加された 3 件の負ケースを個別に照合した:

- `dependabot_author_suffix`（`"dependabot[bot]-evil"`）: `==` は False のまま、`.startswith("dependabot[bot]")` は True → **#9/#10 系の `.startswith` 変異を検知**
- `automation_author_trailing_space`（`"github-actions[bot] "`）: 同様に `.startswith` 変異で True に反転 → **#10 を重複して検知**
- `dependabot_author_prefix`（`"evil-dependabot[bot]"`）: `.startswith` では False のままだが `in`（部分一致）では True → **#11（`in` 変異）だけを選択的に検知**（`.startswith` 変異は検知しない設計）

3 件がそれぞれ異なる緩み方向（前方一致 / 部分一致）を狙い分けており、「著者ログインだけが外れる」（ブランチ名・fork 条件は正しいまま）という #750 の境界外負ケースの形にもなっている。`_test_select_step2_targets_pure`（純粋関数）と `_test_main_mine_or_automation_e2e`（`main()` 経由・fake `run_gh` の argv 検証込み）の二段構成も `sprint-development-rules.md` SD-2 の「本番の主コードパスを変異対象に含める」（#686）と `check-tool-design-rules.md` §3 の fake runner argv 検証（#710）の要件をコード上で満たしている。

### 追記: `--self-test` を実際に実行して確認した（変異テストではなく現状の PASS/FAIL のみ・役割上許可された範囲）
PR ブランチの `tools/check_pending_pr_reviews.py` を取得し `python3 pr_file.py --self-test` を実行したところ、`gh` 未到達の WARNING（テスト環境に `gh`/`GH_TOKEN` が無いため。self-test 内で意図的にスタブ化されている箇所）を挟みつつ最終行で **`PASS: check_pending_pr_reviews self-test (149 cases)`** を確認した。PR 本文の「149 cases PASS」という記述と実測が一致する。

### 留保
本レンズの役割制約（変異テスト＝実装をわざと壊す検証は実施禁止）により、「#9〜#11 が実際に FAIL した」という **変異時点の主張そのもの**（PASS→FAIL への反転）は再現していない。上記で確認できたのは「現状（変異なしの正規実装）で 149 cases 全 PASS」という静的・実測の一致であり、変異を入れて本当に赤くなるかまでは検証していない（役割制約の範囲内）。変異時点の再現は別レンズ（`correctness` 等）に委ねる。

### 推奨する直し方
対応不要（欠陥ではない）。上記の実測により PR 本文の self-test 件数の主張は裏取りできた。

## ラウンド 2

### `scope` — 反論
<sub>2026-09-04T15:39:35+09:00</sub>

## rebuttal（スコープ判定）: correctness / counterexample の claim は両方とも本 PR のスコープ内

### 1. `correctness` の claim「SKILL.md §1 curl 手動実装が branch↔author の対応を明示しない」→ **スコープ内（同じ PR で直すべき）**

round 1 で取得済みの diff（`@@ -74,7 +74,14 @@`）を再確認した。correctness が指摘する段落は該当行が丸ごと本 PR の `+` 行（新規追加）であり、旧行は 1 行（`--mine` 相当の記述）のみ削除・置換されている。すなわち「ブランチ前方一致または完全一致」「著者完全一致」を **1 対 1 でペアにせず 2 本の OR として書いた文章そのものを、本 PR が今回新規に書いた**。

CP-1（`core-principles.md`）の判定基準は「自分の変更が作った壊れか」の一点であり、「既存の齟齬でも、自分の追加分がその齟齬の影響を受ける位置にあるなら同じ PR で直す」。本件はそれ以前の話で、**既存の齟齬に追加分が触れたのではなく、追加分そのものが齟齬を新規に作っている**（Python 実装は 1:1 ペアリングを守っているのに、同じ PR が書いた自然言語版はペアリングを表現できていない）。よって「無関係な既存の壊れだから Issue 化のみ」には当たらず、**同じ PR での修正が妥当**。severity は correctness の言うとおり WARNING（発火条件が GitHub API 全滅時の最終手段であり、実害の顕在化はしにくいが、まさにその状況下で誤りが検証されにくいため深刻）。

### 2. `counterexample` の claim「`_is_dependabot_pr()` を `in` に緩めても 149 cases 全緑」→ **スコープ内（既存関数への便乗要求ではない）**

`_is_dependabot_pr()` 本体（`tools/check_pending_pr_reviews.py:1352-1381`）自体は PR 本文が明記するとおり本 PR で無改変・既存コード。ここだけ見れば「既存の壊れへの便乗」に見える。

しかし counterexample が実際に指摘しているのは **関数本体ではなく、本 PR が新規に書いた自己テストスイート**（`_test_select_step2_targets_pure` / `_test_main_mine_or_automation_e2e`）のカバレッジの穴である。この自己テストは PR 本文の「敵対的検証で見つかった 3 件」表・指摘1で「信頼境界の本体（3条件ANDの③＝著者ログイン）が self-test されていない」ことへの対応として **本 PR が自ら「3 条件 AND を変異で崩して検知できること」を担保目標に掲げ、実際に著者比較の変異（#9〜#11）を self-test の完了条件に含めている**（PR 本文の変異テスト表）。つまり「3 条件 AND の各条件が独立に固定されているか」は本 PR が自分で設定したスコープであり、counterexample が見つけたのはその **自己申告した担保目標のうち、ブランチ条件（②）だけが漏れている** という事実。

これは「既存関数のバグを直せ」という拡張要求ではなく、「あなたが今回新しく書いたテストが、あなたが今回宣言した担保目標を実際には満たしていない」という指摘であり、CP-1 上は完全にスコープ内（自分が追加した成果物＝self-test 自体の欠陥）。ただし severity は counterexample の判定どおり NIT（実運用での悪用可能性は `dependabot[bot]` という bot アカウントの著者ログイン自体が偽装困難なため低い）。同じ PR 内で 1 件負ケースを足すコストは低く、マージのブロッカーにする必要はないが「別 Issue へ切り出す」対象でもない。

### 3. 補強: 自分（`scope`）と `maintenance` の active_session 再確認 claim も同じ理由でスコープ内

PR 本文自身が指摘3を「（本変更が持ち込んだ）露出」と明記している。CP-1 の「自分の変更が作った壊れは即修正」に完全一致し、「無関係な既存の壊れ」ではない。PR 本文は「対応済み」と述べているが、実装が伴わない以上、これは **未着手のまま完了と誤記した** ケースであり、別 Issue への切り出しで済ませてよい話ではない（切り出すなら PR 本文の「対応済み」表記自体を訂正する必要がある）。maintenance の claim（`pr-review-watcher/SKILL.md` 未改修）と完全に一致する結論であり、two lenses が独立に同じ欠落へ到達したことでこの claim の confidence は上がる。

### `correctness` — 反論
<sub>2026-09-04T15:39:37+09:00</sub>

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

### `counterexample` — 反論
<sub>2026-09-04T15:41:30+09:00</sub>

## counterexample → correctness 宛て: 「branch↔author 誤ペア一致」は構築できるが、非対称（片方向のみ）

`correctness` の claim（SKILL.md §1 の curl 手動実装が branch↔author を 1:1 ペアで明示していない）を
実際に反例入力で検証した。**結論: 誤ペアは実在するが、2 方向のうち 1 方向だけが現実的に到達可能**。
severity/confidence の見直しを提案する。

### 検証したナイーブ実装と 2 方向の誤ペア

```python
is_bot = (branch.startswith("dependabot/") or branch == "automation/gem-pool-refresh") \
         and author in ("dependabot[bot]", "github-actions[bot]") \
         and not is_fork
```

- **方向 A**: `branch startswith "dependabot/"` かつ `author == "github-actions[bot]"`
- **方向 B**: `branch == "automation/gem-pool-refresh"` かつ `author == "dependabot[bot]"`

両方とも `is_bot=True`（誤って信頼境界を通す）になることは Python で実際に確認した:
```python
>>> is_bot = lambda b, a: (b.startswith("dependabot/") or b == "automation/gem-pool-refresh") and a in ("dependabot[bot]", "github-actions[bot]")
>>> is_bot("dependabot/evil-branch", "github-actions[bot]")   # 方向A
True
>>> is_bot("automation/gem-pool-refresh", "dependabot[bot]")  # 方向B
True
```
一方、実装済みの `_is_automation_pr()` / `_is_dependabot_pr()`（1:1 ペア）はどちらも正しく `False` を返す
（round 1 で確認済み）。

### 到達可能性は非対称（ここが claim に無い重要な補強）

- **方向 B（`automation/gem-pool-refresh` + `dependabot[bot]`）は誰にも構築不能**。Dependabot
  integration は GitHub 側が完全管理し、常に `dependabot/<ecosystem>/<pkg>-<ver>` 形式のブランチしか
  作らない。`dependabot[bot]` という著者ログインを持つ PR のブランチ名を `automation/gem-pool-refresh`
  にする経路は、外部攻撃者はもちろん **リポジトリ管理者にも存在しない**（Dependabot 自体の挙動は
  `.github/dependabot.yml` の設定項目では変更できない）。
- **方向 A（`dependabot/` 前方一致 + `github-actions[bot]`）は insider のみ到達可能**。
  `github-actions[bot]` という著者ログインは「このリポジトリの **任意の** workflow が
  デフォルトの `GITHUB_TOKEN` で PR を作成した場合」に共通して現れる値であり、
  `gem-pool-refresh.yml` 専用ではない。したがって、**将来 `.github/workflows/` に追加される
  別の workflow**（例: 別の自動生成ジョブ）が、誤って（あるいは意図的に）`dependabot/` で
  始まるブランチ名を選べば、方向 A の誤ペアが成立する。ただし `.github/workflows/` への書き込みは
  リポジトリの書き込み権限（`OWNER`/`MEMBER`/`COLLABORATOR` 相当）を要する行為であり、
  **外部の低信頼コントリビューター（fork PR）が単独で到達できる経路ではない**。

### fail-open / fail-closed 判定

**fail-open**（信頼境界を誤って広げる方向）だが、悪用に必要な前提が「外部からの入力操作」ではなく
「リポジトリへの書き込み権限を持つ内部者の設定ミス」である点は、severity 判定において重要な違いを生む。
書き込み権限を持つ主体は、この誤ペアを使わずとも `.github/workflows/` に直接悪意ある処理を書ける
（例えば自動マージを一切経由せず直接 `git push origin main` するワークフローを書くことも可能）ため、
**この誤ペア単体が新たに開ける攻撃対象領域（attack surface）は限定的**。

### 結論・提案

`correctness` の confidence（PLAUSIBLE）は妥当だが、severity は「WARNING（誰でも到達しうる trust
boundary の緩み）」ではなく「NIT〜WARNING（insider 限定・方向は 1 つだけ）」に近いと考える。
とはいえ **修正コスト自体が低い**（SKILL.md の文言を 1:1 ペアで書き直すだけ）ため、severity の
格下げを理由に見送るべきではない。推奨する直し方は correctness の提案（1:1 ペア明示）に同意する。

post by counterexample / round 2 / rebuttal（correctness 宛て・一部補強・一部確度の精緻化）

### `counterexample` — 譲歩
<sub>2026-09-04T15:41:30+09:00</sub>

## counterexample → maintenance/scope 宛て: 二重選択のタイムラインは構築できた（ただし「二重マージ」ではなく「二重選択」が実害の中心）

`maintenance` の claim（敵対的検証#3「マージ直前 active_session 再確認」が `pr-review-watcher/SKILL.md`
に実装されていない）と、それと同型の `scope` の claim を検証するため、2 firing が同一 bot PR を選ぶ
具体的なタイムラインを実際に `compute_last_activity_min()` / `get_pr_human_comment_times()`
（round 1 で読み込み済みの自分のコピーから再確認。新規の対象ファイル読み込みはしていない）のロジックに
沿って構築した。**タイムラインは作れる**。ただし想定していた「無制限の露出窓」という悪い方向の仮説は
外れ、露出は「選定〜Claude の最初のコメント投稿まで」に限定されることが分かった。

### 構築できたタイムライン

```
T+0min   : Firing A が `check_pending_pr_reviews.py --mine-or-automation --actionable-only` を実行。
           数日前に作られた Dependabot PR #200（active_session=False。最終アクティビティ =
           Dependabot 自身の push 時刻・compute_last_activity_min() は bot コメントを
           非活動としてカウントしない）を選択し、Layer 1 レビュー（内部分析）を開始する。
T+1〜3min: Firing A はまだ PR にコメント・コミットを一切していない（分析中）。
T+2min   : Firing B が起動し、同じコマンドを実行。PR #200 の最終アクティビティは T+0min 時点と
           変わらず古いまま（Firing A の分析はまだ GitHub 上に何も残していない）→
           active_session=False のまま → **Firing B も同じ PR #200 を選択する**。
```

この窓は「`ACTIVE_WINDOW_MIN=10` 分」に縛られていない。`compute_last_activity_min()` は
（1）PR 作成時刻、（2）head ブランチの最新コミット時刻、（3）非ボットの issue/inline コメント時刻、
の 3 種類だけを見る。**Firing A が選定してから GitHub 上に最初の痕跡（コメント or コミット）を
残すまでの時間**が丸ごと無防備な窓になり、Layer 1 分析に数分かかればその分だけ窓は伸びる。

### ただし「二重マージ」より「二重選択（重複作業）」が実害の中心という訂正

`get_pr_human_comment_times()` の docstring は「非ボット（**人間 / Claude セッション**）issue
コメント時刻一覧」と明記しており、`_filter_human_comment_times()` は GitHub の `user.type` が
`"Bot"` かどうかで弾いている。Claude セッションが投稿する Layer 1 レビューコメントは
（GitHub App の bot アカウントではなく）Claude Code 自身の認証アイデンティティで投稿される設計を
前提としている記述であり、**Firing A が最初のコメントを 1 件でも投稿すれば、その時点で
`last_activity_min` はリセットされ `active_session=True` になる**。

したがって:
- `maintenance` が指摘する「マージ直前の `active_session` 再チェックが `pr-review-watcher` に無い」
  問題を **仮に実装したとしても**、Firing A が Layer 1 レビューを完了しコメントを投稿した後であれば
  Firing B の再チェックはそこで `active_session=True` を検知し中断できる（＝再チェック自体は有効な
  対策になりうる）。
- しかし **T+0〜T+(最初のコメント投稿) の窓では Firing B の選択そのものは防げない**。この窓は
  「マージ直前の再チェック」では塞がらない（選択はマージよりずっと前に起きる）。実害は
  「GitHub 上の実際の二重マージ」（GitHub 自体の状態遷移・レイヤー4が最終防衛線になる）ではなく、
  **2 セッションが同じ PR に対して重複した Layer 1 レビュー分析・重複コメントを行う無駄** である。

### 推奨する直し方（maintenance の提案への追加）

`pr-review-watcher/SKILL.md` のマージ直前再チェック（maintenance 提案）に加えて、**Step 2 で bot PR を
選択した直後・分析着手前に軽量な「着手宣言」コメントを 1 件即時投稿する**（または類似の早期マーカー）
ことを推奨する。これにより `last_activity_min` が選定直後にリセットされ、後続 firing の露出窓が
「選定〜分析完了」ではなく「選定〜着手宣言コメント投稿」に短縮される（`session-concurrency-rules.md`
の論理ロック思想と同型・ただしラベル付与ではなくコメントで済ませる案）。

post by counterexample / round 2 / concession + extension（maintenance・scope 宛て）

### `maintenance` — 反論
<sub>2026-09-04T15:42:09+09:00</sub>

## rebuttal: `counterexample` claim 1（`_is_dependabot_pr` の `startswith`→`in` 変異）は本 PR の責任範囲外・かつ実行経路（`--self-test`）では既に検知される

対象: `counterexample` round1 claim 1（`tools/check_pending_pr_reviews.py:1379` の `_is_dependabot_pr()` ブランチ判定、`startswith`→`in` 変異が 149 件全緑で通る、という指摘）

### 反証の要旨
`counterexample` の再現手順は `m._test_select_step2_targets_pure()` と `m._test_main_mine_or_automation_e2e()`（**#899 で新規追加した 2 関数のみ**）を直接呼んでおり、`--self-test` の実行経路（`main()` → `_run_self_test()`）を通していない。しかし `_run_self_test()` 本体には **PR #594（Issue #458 と同時期・#870 とは無関係）由来の既存ケース** が既にある:

```python
# tools/check_pending_pr_reviews.py:2497-2510（dependabot_cases、#899 で無改変）
dependabot_cases = [
    ...
    ("dependabot", "dependabot[bot]", False, False),          # 前方一致しない（単体）
    ("feat/dependabot/npm", "dependabot[bot]", False, False), # ← ここ
]
for branch, author_login, is_cross_repository, expected in dependabot_cases:
    got = _is_dependabot_pr(branch, author_login, is_cross_repository)
    if got != expected: failures.append(...)
```

`("feat/dependabot/npm", "dependabot[bot]", False, False)` は **著者ログインを正しい値に固定したまま、ブランチだけを「`dependabot/` を含むが先頭ではない」形にした負ケース** であり、`counterexample` が提案した反例（`branch="feat/enable-dependabot/x"`, `author="dependabot[bot]"`）と同型である。ブール代数で確認する:

- baseline（`startswith`）: `"feat/dependabot/npm".startswith("dependabot/")` = `False` → 早期 `return False` → `expected=False` と一致（緑）
- `counterexample` の変異（`in` へ緩める）: `"dependabot/" in "feat/dependabot/npm"` = **`True`**（`"feat/"` の直後に `"dependabot/"` が部分文字列として現れる）→ 早期 return を通過 → 著者一致（`dependabot[bot]` == `dependabot[bot]`）→ **`_is_dependabot_pr` が `True` を返す** → `expected=False` と不一致 → **`failures` に 1 件追加され、`--self-test` は非ゼロ終了する**

つまり `counterexample` が「149 件全緑」と結論したのは、**変異を当てた状態で `--self-test`（＝この検査の本番の実行経路・エントリポイント）を実際には通していない** ため。彼らが直接呼んだ 2 関数だけを見れば 0 failures なのは事実だが、それは「その 2 関数が単体でこの区別をテストしていない」というだけであり、**ツール全体（`--self-test`）としての実効性は既に別ケースで担保されている**。

### 責任範囲の判定
このブランチ条件の区別テストは PR #594（`_is_dependabot_pr()` 新設時）に由来し、**#899（本 PR）が追加も削除もしていない**。#899 の敵対的検証#1 が特定した穴（③著者ログイン条件が無検証）は #899 が実際に埋めた対象であり、ブランチ条件側は #870/#899 のスコープ外（元から別 PR が担保済み）。したがって「非対称」は #899 の見落としではなく、**#899 が着手する前から解決済みだった論点に #899 は触れていない、というだけ** である。severity は NIT で妥当だが、confidence は「実測で確認済み」から「テスト対象の選び方（2 関数直呼び）に起因する再現手順の不備」へ格下げすべきで、**PR #899 のマージ判断への影響はゼロ** と判定する。

### 推奨する直し方
`counterexample` の反例自体は将来のリファクタ耐性チェックとして無価値ではないため、`_test_main_mine_or_automation_e2e()` へブランチ限定負ケースを 1 件足すこと自体は妥当な提案として残してよい（ただし「本 PR が導入した穴」ではなく「既存カバレッジの二重化」という位置づけで PR コメントに書く）。次回同種の反例作成では `_run_self_test()` / `--self-test` を通しで実行し、対象外の既存ケースが横から検知していないかを先に確認することを推奨する。

### `maintenance` — 譲歩
<sub>2026-09-04T15:42:13+09:00</sub>

## concession: `correctness` の SKILL.md §1 指摘は正しい（自分の round1 の「一致」評価は粗すぎた）。ブール代数で CONFIRMED に格上げする

対象: `correctness` round1 claim（`.claude/skills/sprint-cycle-router/SKILL.md:79-81`、curl 手動フォールバックの branch↔author ペアリング欠落、confidence: PLAUSIBLE）

### 自分の round1 の所見の撤回
round1 で自分は SKILL.md §1 の curl フォールバック文言を Python 側 `_is_automation_pr()` / `_is_dependabot_pr()` の条件と読み合わせ、「著者は完全一致（前方一致・部分一致にしない）」等の個々の要素が正しく明記されている点だけを確認して「一致」と判断した。しかし **要素の網羅性だけを見ており、要素同士の結合構造（AND/OR の掛かり方）までは検証していなかった**。`correctness` の指摘はまさにこの結合構造の欠陥であり、自分の round1 評価はここを見落としていた。

### なぜ CONFIRMED か（ブール代数で検証）
SKILL.md §1 の文言（PR ブランチ 79-81 行目）を素直に構造化すると:

```
(branch == "automation/gem-pool-refresh" OR branch.startswith("dependabot/"))
AND (author == "github-actions[bot]" OR author == "dependabot[bot]")
AND NOT is_fork
```

一方 Python 実装（`is_trusted_bot_pr = is_automation_pr or is_dependabot_pr`）は:

```
(branch == AUTOMATION_PR_BRANCH AND author == AUTOMATION_PR_AUTHOR_LOGIN AND NOT is_fork)
OR
(branch.startswith(DEPENDABOT_PR_BRANCH_PREFIX) AND author == DEPENDABOT_PR_AUTHOR_LOGIN AND NOT is_fork)
```

前者は「(P∨Q)∧(R∨S)」、後者は「(P∧R)∨(Q∧S)」。この 2 つは論理的に同値ではなく、前者は後者の **真の上位集合**（後者が真ならば前者も必ず真だが、逆は成り立たない）。具体的な非等価点: `branch="automation/gem-pool-refresh"` かつ `author="dependabot[bot]"`（あるいはその逆の組み合わせ）は、Python 実装では `is_automation_pr=False`（著者不一致）かつ `is_dependabot_pr=False`（ブランチ前方一致しない）で **両方 False**（=対象外）だが、SKILL.md の文言を字面どおり実装すると `(branch 条件: automation 完全一致で True) AND (author 条件: dependabot[bot] で True)` となり **True と誤判定される**。`correctness` が挙げた失敗シナリオ（別ワークフローが `dependabot/` 始まりのブランチ名で PR を誤って作る等）は、この非等価性の具体的な発現例として妥当。

### §2 / §3 との整合について（3 箇所は「同一の粒度」ではない・矛盾ではない）
round1 で自分が確認した §2（早期リターン b）・§3（Step 2 表）は、いずれも「bot 自動化 PR（Dependabot / `automation/gem-pool-refresh`・`D-43`）」という **カテゴリ名だけ** を参照する要約であり、branch/author のペアリング条件そのものは書いていない（詳細条件を持つのは §1 のみ）。したがって `correctness` の指摘は §1・§2・§3 の **3 箇所間の食い違い** ではなく、**§1 単体の記述精度の問題** であり、自分の round1 の「3 箇所一致」という評価はそもそも比較対象が違う（§2/§3 に同レベルの詳細が無いので「一致」も「不一致」も本来評価できない）。この点は訂正する: 3 箇所は「矛盾していない」が「§1 だけが詳細を持ち、その詳細に `correctness` の指摘する欠陥がある」が正確な状態。

### 推奨する直し方（correctness の提案を支持）
SKILL.md §1 を「`automation/gem-pool-refresh` 完全一致 **のときに限り** 著者 `github-actions[bot]` 完全一致」「`dependabot/` 前方一致 **のときに限り** 著者 `dependabot[bot]` 完全一致」のペア表現に書き換える。severity は WARNING、confidence は **CONFIRMED**（実装コードとの論理的非等価性を式で確認済み）に格上げを支持する。

### `maintenance` — 主張
<sub>2026-09-04T15:42:16+09:00</sub>

## claim（round1 CONFIRMED 指摘の具体化）: `is_trusted_bot_pr` 定義一元化の修正に必要な self-test ケース

対象: Layer 1 CONFIRMED 指摘（`select_step2_targets()` が `analyze_pr()` 内の `is_trusted_bot_pr = is_automation_pr or is_dependabot_pr` と同じ OR を再実装している definition drift）の具体的な直し方と、その修正が満たすべき self-test 要件。

### 修正の形（提案）
`analyze_pr()` の両 return 経路（早期 exit / 通常）の dict に `is_trusted_bot_pr` キーを追加し、`select_step2_targets()` 側は `r["is_automation_pr"] or r["is_dependabot_pr"]` の再実装をやめて `r["is_trusted_bot_pr"]` を直接参照する（`is_automation_pr` / `is_dependabot_pr` 自体は個別の判定結果として dict に残してよい。JSON 出力の後方互換のため）。

### 必要な self-test ケース（`sprint-development-rules.md` SD-2 / `check-tool-design-rules.md` §4 準拠）

1. **両 return 経路のキー存在検証（#870 で `is_automation_pr`/`is_dependabot_pr` に対して既にやった手当てと同型）**: 既存の「早期 return 経路」e2e ケース（`blocked_dependabot` / `blocked_automation`、diff 該当行）に `parsed_blocked[0]["is_trusted_bot_pr"] is True` の assert を追加する。早期 exit の dict にキーを足し忘れると、`select_step2_targets()` を `r["is_trusted_bot_pr"]` の素の添字参照（`.get()` 不使用・fail-closed 方針）へ書き換えた瞬間に `KeyError` で落ちるため、**この 1 件を足さないと「早期 return 経路でだけキーが無い」退行が self-test を素通りする**（通常経路のケースだけでは検知できない＝#870 の教訓そのもの）。
2. **`is_trusted_bot_pr == (is_automation_pr or is_dependabot_pr)` の不変条件テスト**: `_test_select_step2_targets_pure()` の各 `rec()` フィクスチャに `is_trusted_bot_pr` を明示的に **別の値** として持たせたケースを 1 件加える（例: `is_automation_pr=True, is_dependabot_pr=False, is_trusted_bot_pr=False` という **わざと矛盾させた入力**）。もし実装が「まだ `is_automation_pr or is_dependabot_pr` を再計算している」箇所が残っていれば矛盾に気づかず通ってしまうので、`select_step2_targets()` が **`is_trusted_bot_pr` だけを見て `is_automation_pr`/`is_dependabot_pr` を見ていないこと** を積極的に確認する（`testing-strategy.md` の言う「実装の欠落を検知するテスト」に該当。ただしこれは #750 の「境界外負ケース」とは別種の「フィールド優先順位の固定」テストである点に注意）。
3. **変異対象（`sprint-development-rules.md` SD-2）**: 修正後、`analyze_pr()` 内の `is_trusted_bot_pr = is_automation_pr or is_dependabot_pr` の計算式自体（`or` → `and` にする等）を変異させ、上記 2 のテストが FAIL することを実測する。これが「本番の主コードパスを変異対象に含める」（#686）の実践になる。
4. **回帰**: 既存の `_test_select_step2_targets_pure()` の (a)〜(g) と `_test_main_mine_or_automation_e2e()` の全ケースが、キー参照先を変えても同じ期待値で通ること（純粋なリファクタであることの担保）。

### 位置づけ
本項目は修正そのものの提案ではなく（Layer 1 が既に CONFIRMED 指摘済み・別 Issue 化が妥当）、**修正する場合に self-test 側で満たすべき最低条件の仕様** として記録する。#899 のマージ判断を左右するものではない（severity: 情報提供・NIT 相当）。

## ラウンド 3

### `lead` — 合意
<sub>2026-09-04T15:44:03+09:00</sub>

## 合意点

- **`select_step2_targets()` の分岐意味論そのものは堅牢**。4 レンズが独立に反例（他者の人手 PR の混入・優先順位の逆転・KeyError・argparse 相互排他の抜け）を試み、いずれも破れなかった。`counterexample` は 66 種の decoy を混ぜた fuzz でも fail-open を再現できていない。
- **3 条件 AND（fork 不可 + ブランチ条件 + 著者ログイン完全一致）は緩んでいない**。著者ログインは攻撃者が偽装できない値であり、これが信頼境界の実質的な要になっている（`correctness` / `counterexample` が round 2 で一致）。
- **`--mine-or-automation` のセッション ID 必須化は妥当**。未指定だと `is_mine` が全件 False になり優先順位が黙って逆転するため、exit 2 で止めるのが正しい。

## 対立点と決着

### 1. `_is_dependabot_pr()` の `startswith` → `in` 変異が self-test を素通りするか

`counterexample`（round 1）は「149 件全緑のまま通った」と主張。`maintenance`（round 2）は「既存 `_run_self_test()` に `("feat/dependabot/npm", "dependabot[bot]", False, False)` の負ケースがあり必ず検知する。`counterexample` は新規 2 関数を直呼びしただけで本番エントリポイントを通していない」と反証。

**lead が実測で決着**: PR ブランチ版を一時ディレクトリへ複製し、`if not branch.startswith(DEPENDABOT_PR_BRANCH_PREFIX)` を `if DEPENDABOT_PR_BRANCH_PREFIX not in branch` へ変異させて `--self-test` を実行したところ、

```
FAIL: check_pending_pr_reviews self-test
  _is_dependabot_pr('feat/dependabot/npm', 'dependabot[bot]', False) = True (expected False)
```

exit 1 で落ちた。**`maintenance` の反証が正しく、`counterexample` の claim は棄却する**（dropped）。

### 2. bot PR の「二重マージ」露出

`scope` / `maintenance` が「PR 本文が対応済みと主張する `active_session` 再確認が、実際にマージを呼ぶ `pr-review-watcher/SKILL.md` に配線されていない」と指摘。`correctness` が「GitHub のマージ API はマージ済み PR への再マージを 405 で拒否するため二重マージ自体は構造的に起こり得ない」と部分反証。`counterexample` が `compute_last_activity_min()` を読んで「Firing A の選定〜最初のコメント投稿までの窓なら 2 firing が同一 bot PR を選ぶタイムラインは構築できる」と補強しつつ、実害は二重マージではなく **二重選択による重複レビュー作業** であると訂正。

**決着**: 症状名を「二重マージ」から「**二重選択による重複レビュー作業**」へ訂正したうえで、desync 自体は残る指摘として採用する（severity は CRITICAL 相当から WARNING へ下げる）。

### 3. 各指摘のスコープ

`scope` が CP-1「スコープ厳守との優先順位」で 3 件すべてを判定し、いずれも **本 PR の追加行が原因、または PR 自身が「本変更が持ち込んだ露出」と認めている** ため同一 PR で直す対象とした。既存の壊れへの便乗要求は無い。

### `lead` — 判定
<sub>2026-09-04T15:44:51+09:00</sub>

{
  "findings": [
    {
      "severity": "WARNING",
      "confidence": "CONFIRMED",
      "lens": "correctness（maintenance が concession で支持・scope がスコープ内と判定）",
      "file": ".claude/skills/sprint-cycle-router/SKILL.md:78-81",
      "summary": "curl モードの手動実装仕様が「ブランチ条件のいずれか」かつ「著者条件のいずれか」という (P∨Q)∧(R∨S) の形で書かれており、実装側の (P∧R)∨(Q∧S)（各 bot が自分のブランチと自分の著者名を対で AND 判定）より緩い信頼境界を許す。",
      "failure_scenario": "gh も内蔵 REST も全滅して curl モードへ落ちた firing で、本段落を文字どおり実装すると、head ブランチが `dependabot/` 前方一致で著者が `github-actions[bot]` という誤ペアの PR（GitHub Actions ワークフローが dependabot/ 系のブランチ名で PR を作った場合に実在しうる）が Step 2 の対象として選ばれる。`_is_dependabot_pr()` / `_is_automation_pr()` はこれを False にするため、実装と条文が食い違う。倒れる向きは fail-open（信頼境界が広がる方向）。",
      "fix": "条件をペアで書き直す。「(`dependabot/` 前方一致 かつ 著者 `dependabot[bot]`) または (`automation/gem-pool-refresh` 完全一致 かつ 著者 `github-actions[bot]`)、いずれも fork でないこと」と、AND の結合を各 bot 内に閉じる形へ変える。"
    },
    {
      "severity": "WARNING",
      "confidence": "CONFIRMED",
      "lens": "Layer 1（簡素化・再利用）→ maintenance が round 2 で必要な self-test を具体化",
      "file": "tools/check_pending_pr_reviews.py:937",
      "summary": "「信頼済み bot か」の定義が 2 箇所に分かれている。`analyze_pr()` は `is_trusted_bot_pr = is_automation_pr or is_dependabot_pr` を信頼境界判定に使うがこの派生値を戻り値 dict に載せず、`select_step2_targets()` が同じ OR を独立に再実装している。",
      "failure_scenario": "将来 3 系統目の信頼済み bot を足すとき、実装者は `analyze_pr()` の `is_trusted_bot_pr` 行と dict へ載せる新フラグだけを更新する。937 行は `is_trusted_bot_pr` という概念を経由せず個別フラグを直接 OR しているため更新漏れに気づきにくく、`analyze_pr()` は新 bot を信頼境界内と認めるのに Step 2 の対象選択だけがその PR を拾わない definition drift が起きる。倒れる向きは fail-closed（bot PR が黙って放置され `open-pull-requests-limit` に達する = D-43 の懸念そのもの）。",
      "fix": "`analyze_pr()` の両 return 経路の dict に `is_trusted_bot_pr` を追加し、937 行を `return [r for r in results if r[\"is_trusted_bot_pr\"]]` に変える。self-test には (a) 両 return 経路に新キーが載ること (b) 個別フラグと新キーが矛盾する入力を与えたとき新キー側が優先されること を追加する。"
    },
    {
      "severity": "WARNING",
      "confidence": "CONFIRMED",
      "lens": "scope / maintenance（correctness が症状名を反証・counterexample が訂正のうえ補強）",
      "file": ".claude/skills/pr-review-watcher/SKILL.md（本 PR 未変更）",
      "summary": "PR 本文が敵対的検証指摘 3 への対応として掲げた「マージ直前に `active_session` を再確認する」が `sprint-cycle-router/SKILL.md` の Step 2 行にしか書かれておらず、実際に `merge_pull_request` を呼ぶ `pr-review-watcher/SKILL.md` には該当ステップが無い。緩和策が実行経路に存在しない desync。",
      "failure_scenario": "bot PR は `Session-Id:` による決定論的所有判定（レイヤー 6）を持たないため排他が `active_session` の 10 分窓だけになる。`compute_last_activity_min()` の実装上、firing A が bot PR を選んでから最初のコメントを投稿するまでの窓に firing B が起動すると、同一 bot PR を 2 firing が選ぶ。実害は「二重マージ」ではない（GitHub のマージ API が 2 回目を 405 で拒否する）が、Layer 1 セルフレビューが二重に走る重複作業と重複インラインコメントが発生する。",
      "fix": "`pr-review-watcher/SKILL.md` の Step 5（自動マージ）に「bot 自動化 PR は `Session-Id:` 所有判定を持たないため、マージ直前に `check_pending_pr_reviews.py --actionable-only` で `active_session` を再確認する」の 1 行を足し、router 側の条文と実行経路を一致させる。"
    },
    {
      "severity": "WARNING",
      "confidence": "CONFIRMED",
      "lens": "scope",
      "file": "Issue #870（コメント）",
      "summary": "Issue #870 が対応方針として明示要求した「`check_lane_reachability.py` への検査追加を見送る場合は理由を本 Issue に記録する」が未実施で、見送り理由は PR #899 の本文にしか存在しない。",
      "failure_scenario": "PR がマージされ参照が薄れたあと、Issue #870 単体を読む後続セッションが「検査追加が検討されたのか、忘れられたのか」を判別できず、同じ検討を再度行う（または未検討とみなして誤って検査を追加する）。",
      "fix": "マージ前に Issue #870 へ見送り理由（判定軸が構文的到達可能性であり入力種別の到達可能性とは軸が異なる／広く作れば誤検知・狭く作れば fail-open）を 1 コメントで転記する。"
    }
  ],
  "dropped": [
    {
      "claim": "counterexample（round 1）: `_is_dependabot_pr()` のブランチ判定を `startswith` から部分一致 `in` へ緩めても 149 件の self-test が全緑で通る（テストの実効性の欠落）",
      "rebuttal": "maintenance が round 2 で「既存 `_run_self_test()`（PR #594 由来・本 PR 無改変）に `(\"feat/dependabot/npm\", \"dependabot[bot]\", False, False)` の同型負ケースが既にあり、ブール代数上その変異を確実に検知する。counterexample は本番エントリポイント（`--self-test`）を通さず新規 2 関数だけを直呼びした」と反証。lead が PR ブランチ版を一時ディレクトリへ複製して実際に同じ変異を注入し `--self-test` を実行したところ `FAIL: _is_dependabot_pr('feat/dependabot/npm', 'dependabot[bot]', False) = True (expected False)` で exit 1 になることを実測。claim は成立しない。"
    },
    {
      "claim": "scope / maintenance（round 1）: bot PR の二重マージが起こりうる（CRITICAL 相当）",
      "rebuttal": "correctness が「GitHub のマージ API はマージ済み PR への再マージを 405 で拒否するため二重マージ自体は構造的に起こり得ない」と反証。counterexample が `compute_last_activity_min()` を読んで二重「選択」までは成立すると補強したため、症状名を「二重選択による重複レビュー作業」へ訂正し severity を WARNING へ下げたうえで findings に残した（claim 全体の棄却ではなく症状の訂正）。"
    }
  ],
  "blocking": [
    "curl モードの手動実装仕様のブランチ↔著者ペアリング欠落（SKILL.md:78-81）— 本 PR が新規に書いた段落であり、実装より緩い信頼境界を条文が許している",
    "`select_step2_targets()` の `is_trusted_bot_pr` 再実装（check_pending_pr_reviews.py:937）— 信頼済み bot の定義を 1 箇所へ集約する",
    "`pr-review-watcher/SKILL.md` への `active_session` 再確認の配線 — PR 本文が「対応済み」と主張する緩和策を実行経路へ届かせる",
    "Issue #870 への見送り理由の記録 — Issue が明示要求した完了条件"
  ],
  "unresolved": []
}
