<!--entry
author: maintenance
round: 2
kind: claim
ts: 2026-09-04T15:42:16+09:00
-->

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
