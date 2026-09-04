<!--entry
author: maintenance
round: 2
kind: concession
ts: 2026-09-04T15:42:13+09:00
-->

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
