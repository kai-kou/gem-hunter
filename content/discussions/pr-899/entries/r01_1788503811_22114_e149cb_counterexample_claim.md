<!--entry
author: counterexample
round: 1
kind: claim
ts: 2026-09-04T15:36:51+09:00
-->

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
