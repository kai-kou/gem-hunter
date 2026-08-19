<!--entry
author: retro_facilitator
round: 2
kind: concession
ts: 2026-08-19T09:55:02+09:00
-->

## retro_facilitator round2: 3 点への応答

### 1. guardrail_eng の根本原因特定を受けて Try-2 を具体化（concession）

`pre-pr-create-check.sh` が `check_exit -eq 1` しか見ておらず、`self_review_check.py` 自身の異常終了
（内部例外 exit=2 / 外側 `timeout` による kill exit=124）が可視化されずに握りつぶされている、という
guardrail_eng の実コード特定（L800-811 の `run_subcheck` は対策済み、L1028-1032 の `__main__` 外側
try/except と `pre-pr-create-check.sh` の 1 点判定の間に穴がある）を採用する。

**私の Try-2 の誤り**: 「非ゼロ終了で Error 扱いにする（ブロック）」と書いたが、これは guardrail_eng の
fail-open 方針（無人ルーティンを止めない・Warning のみ）と矛盾する。**撤回して guardrail_eng の設計に合わせる**。

**Try-2 完了条件を差し替え**:
- Issue タイトル: `fix: self_review_check.py 自体の異常終了（exit≠0,1）を pre-pr-create-check.sh が握りつぶさず可視化する`
- ラベル: `type:retro-try`, `sp:1`（guardrail_eng 見積もりを採用。実装コスト極小のため sp:3 は過大）
- 完了条件: `pre-pr-create-check.sh` に `check_exit -ne 0 && check_exit -ne 1` の分岐を追加し、
  self_review_check.py 自身の異常終了（内部例外 exit=2 / timeout kill exit=124）を additionalContext に
  **Warning として**（Error 化・ブロックはしない）必ず注入する。exit=2 と exit=124 を合成的に再現するテスト
  （意図的に遅い/例外を投げるダミーチェッカーを差し替えるか、モックで代替）で Warning が実際に出力されることを
  確認する。ブロックしない（fail-open）ことを明記したテストケースも合わせて確認する

### 2. docs_trace の「retrospective スキル死蔵」は Try に入れない（rebuttal）

死蔵の実態（`sprint-cycle-router` Step 4-6 が `pr-review-watcher` へ継続するだけで retrospective を
呼ばない）は docs_trace の実測どおりで異論はない。ただし **process_design が争点 C で既に具体設計を
出している**（`pr-review-watcher` の「マージ＋公開反映の直後、完了報告の前」に retrospective 呼び出しを
1 箇所だけ差し込む案。決定木は変更しない・発火条件は `Sprint Goal:` 行の有無・記録先も SSOT を増やさない
形で確定済み）。

ここで私が別 Try Issue（例: `improvement: retrospective の呼び出し元を追加する`）を起票すると、
process_design の設計と **同じ課題に対して 2 つの Issue が並立** し、どちらが正の実装手順かが割れる
（本ブリーフ自体が警告している「同じ規則が 2 箇所に実体で書かれる状態」と同型のリスク）。

**結論: 起票しない。** process_design の設計（③ pr-review-watcher SKILL.md 追記案）をそのまま
Issue 化する動線に乗せるべきで、KPT レーン側からの重複起票は避ける。もし process_design 側が
「設計は出したが Issue 化は retro レーンに任せる」という前提なら、その 1 点だけラウンド 3 で
明示的に確認したい（Issue 起票の担当が宙に浮くと #147 型の孤児化が起きるため）。

### 3. sprint_review の「p95 CPU 実測」は Try ではなく SP-1 自身の残作業（concession + 境界明示）

同意する。sprint_review は p95 CPU 実測ゲート（`cloudflare-infrastructure.md` §5.3）を
「**次の firing で必ず潰す**」＝ Issue #26 自身の Done 条件（accepted_with_conditions の条件そのもの）
と位置づけており、⑤⑥+ClockPort のように「後続スプリントへ送ってよい」対象とは明確に区別している。

これは **振り返り由来の改善（retro-try）ではなく、SP-1 というスプリント自身が完了していない作業**
なので、私の Try 一覧には含めない。

**Try-4 の境界を修正**: 元の Try-4 は「p95 CPU 実測 / Cache Port の器 / シークレット投入・Rate Limiting /
ClockPort 化」の 4 件を一律に sub-issue 化する案だったが、**p95 CPU 実測はここから除外する**（#26 に
残したまま、次 firing で直接実測して #26 の Done 条件を満たす作業として扱う。新規 Issue を起こさない）。

**Try-4 スコープ確定版**:
- Issue タイトル: `feature: SP-1 の後続スプリント送り残作業（Cache Port の器 / シークレット投入・Rate Limiting / installation-token.ts の ClockPort 化）を独立 Issue に分解する`
- ラベル: `type:retro-try`, `sp:2`
- 完了条件: sprint_review が「後続スプリントへ送ってよい」と判定した 3 件（p95 CPU 実測は含まない）を、
  それぞれ検証可能な完了条件・`sp:N` 付きの sub-issue として起票し（`mcp__github__sub_issue_write` で
  #26 に紐付け）、sprint-cycle-router の Step 4 が拾えるバックログ状態にする。p95 CPU 実測は #26 本文に
  残し、次 firing で直接対応することを明記する
- 対応する Problem: P4（境界を p95 CPU 実測ゲートを除く 3 件に修正）

### Try-1・Try-3 は変更なし
Try-1（GitHub Actions 起動不能の切り分け）・Try-3（SD-4 読む順序への domain-model.md 明記）は
他 4 名の投稿と抵触しないため据え置き。
