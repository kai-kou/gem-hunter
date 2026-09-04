<!--entry
author: maintenance
round: 2
kind: rebuttal
ts: 2026-09-04T15:42:09+09:00
-->

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
