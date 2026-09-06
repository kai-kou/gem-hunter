# Warm 層 教訓 — CI / CD・フック

CI / CD・フック運用に関するカテゴリ別教訓（タスク依存で Read）。

---

## L-023: CI 失敗は自律修正する・フックを `--no-verify` で bypass しない（2026-06-13）

**パターン**: ① GitHub Actions / CI が失敗したとき、ログを読まずユーザーに「直してよいか」と確認に回す。
② コミットが Lv3 フック（pre-commit / pre-push）でブロックされた際、`git commit --no-verify` /
`git push --no-verify` でフックを **bypass** して回避する。

**根本原因**: CI 失敗・フックブロックを「ユーザー判断が必要な障害」と誤分類している（実際は
Claude が自律修正すべき作業）。フック bypass は品質ゲートの無効化であり、ハードコンストレイント
（Lv3）の意味を失わせる。

**対策**:
- CI 失敗時はログを読んで根本原因を特定し **自律修正** する（ユーザー確認不要・CP-1 / `core-principles-detail.md` 自律実行表）
- フックブロックは正規の手順で解消する。`--no-verify` での bypass は **禁止**

**禁止 → 推奨**:
```
❌ git commit --no-verify / git push --no-verify でフックを回避
❌ CI 失敗を理由にユーザー確認へ丸投げ
✅ フックの指摘を解消してから再コミット
✅ CI ログ → 根本原因特定 → 修正 → 再実行（自律）
```

---

## L-024: MCP 経由 PR 作成が PreToolUse ゲートを素通りする（2026-06-26）

**症状**: クラウドセッションで作成した PR で、Layer 0 機械ゲート（`self_review_check.py`）と
Layer 1 セルフレビュー（FAIR・全PR必須）が **発火せずスキップ** される。未コミット検出も働かない。

**根本原因**: `pre-pr-create-check.sh`（PR 作成前ゲート）は `PreToolUse` フックだが、
`.claude/settings.json` の matcher が `Bash` のみで、`mcp__github__create_pull_request` を
捕捉していなかった。クラウド環境では `gh pr create` が proxy の GraphQL 403 で失敗するため
PR 作成は **MCP ツールが主経路** になるが、その経路が matcher 外だったため Layer 0 ゲート・
未コミットチェック・Layer 1 リマインダーを **完全素通り** していた。`gh pr create` 前提のガードが
クラウドの実経路（MCP）とズレていた（L-094 型 desync）。

**対策（実装済み）**:
- `settings.json` の `PreToolUse` matcher に `mcp__github__create_pull_request` を追加
- `pre-tool-use-router.sh` が MCP PR 作成を `pre-pr-create-check.sh` へ委譲
- `pre-pr-create-check.sh` が Bash `gh pr create` と MCP PR 作成の両方でゲート（git-clean +
  `self_review_check.py` + Layer 1 リマインダー）を実行

**禁止 → 推奨**:
```
❌ PR 作成前ガードを Bash の gh pr create だけ前提にする（クラウドは MCP が主経路）
✅ PR 作成の全経路（Bash gh pr create / mcp__github__create_pull_request）を matcher・router で捕捉する
```

**判定基準**: 「クラウドで動く実経路（MCP）と、ローカル前提のガード（Bash）がズレていないか」を
新しいガードを足すたびに確認する。

---

## L-137: 品質ゲートの数値判定に生の浮動小数点値を使わない（2026-08-20）

**症状**: Lighthouse Accessibility スコア判定が `score < 1.0` で検査し、表示は `Math.round(score * 100)` している場合、丸め誤差で `0.9999999999999998` が返されると、ログには「Accessibility 100/100」と出力されながら判定で FAIL する原因不明の矛盾が発生する（SP-10・PR #183）。

**根本原因**: ゲートの比較判定と、ログ出力・UI 表示の丸め処理が別々になっているため、判定値と表示値が一致しない。浮動小数点演算の丸め誤差（`0.9999999999999998` vs `1.0`）が、判定の直前段階で顕在化する。

**対策**:

1. **ゲートの数値判定は、表示と同じ丸め処理を通した値で行う**（判定値と表示値が常に一致する）
2. **丸め処理は判定の前段に必ず挟む**（生の浮動小数点値で比較しない）
3. 新規ゲート追加時のテンプレート:

```javascript
// ❌ 誤り（生値で判定、表示で丸め）
const rawScore = 0.9999999999999998;
if (rawScore < 1.0) { /* FAIL */ }
console.log(Math.round(rawScore * 100)); // "100" が出力（矛盾！）

// ✅ 正しい（丸め後の値で判定）
const rawScore = 0.9999999999999998;
const displayScore = Math.round(rawScore * 100); // 100
const gateScore = displayScore / 100; // 1.0
if (gateScore < 1.0) { /* PASS */ }
console.log(displayScore); // "100" が出力（一貫性あり）
```

**禁止 → 推奨**:
```
❌ if (score < 1.0) { /* gate */ }; console.log(Math.round(score * 100));
✅ const rounded = Math.round(score * 100); 
   if (rounded < 100) { /* gate */ }; console.log(rounded);
```

**判定基準**: 「ゲートの合否判定」と「ログ表示」に数値変換（四捨五入・スケーリング）が挟まる場合、両者で同じ丸め処理を使っているか確認する。

---

## L-156: マージ不能（`mergeable_state: dirty`）な PR では `pull_request` 起動の CI が生成されない（2026-09-04・PR #883）

> **マージ判定へ戻る導線**: 本症状で check run が不在のままマージ可否を決めるときは、`docs/rules/pr-review-flow.md`「CI check run が不在のときの判定」の 3 手順に従う（#961）。

**症状**: PR を作成したのに、`quality-checks.yml`（`on: pull_request`）の check run が **いつまでも現れない**。
`mcp__github__pull_request_read(method="get_check_runs")` には CodeQL や GitGuardian など他系統だけが並び、
`mcp__github__actions_list(method="list_workflow_runs", resource_id="quality-checks.yml", workflow_runs_filter={"branch": "<作業ブランチ>"})`
も `total_count: 0` を返す。`get_status` も `state: pending / total_count: 0`。

**原因**: GitHub の `pull_request` イベントは **マージコミット（`refs/pull/<N>/merge`）** に対して走る。
ベースブランチと衝突していて `mergeable_state` が `dirty` の PR ではそのマージコミットを作れないため、
**run 自体が生成されない**（失敗するのではなく最初から存在しない）。実測: PR #883 は作成直後に
`origin/main` が別 PR で進んでおり `dirty` → 25 分間 CI 不在 → `origin/main` をマージして解消した直後に
`checks` が走り success。

**判定基準**: 「CI が走らない」と感じたら、失敗を疑う前に
`mcp__github__pull_request_read(method="get", ...)` の **`mergeable_state`** を先に見る。
`mergeable_state` は 2 値ではないので、観測した値ごとに分岐する（`dirty` / `clean` だけを見ると、
`unknown` や `unstable` を引いたときに次の一手が決まらず、本エントリが防ごうとした調査の空転を再現する）。

| `mergeable_state` | 意味 | 次の一手 |
|---|---|---|
| `dirty` | ベースブランチとコンフリクトしている | CI の問題ではない。`origin/main` をマージして解消する |
| `unknown` | mergeability を非同期計算中（PR 作成直後に出やすい） | 数十秒待って `pull_request_read(method="get")` を取り直す |
| `clean` / `unstable` / `blocked` / `behind` | マージコミットは作れている（`unstable` は他チェックが赤、`blocked` は保護ルール待ち、`behind` はベースより古い） | ここで初めてワークフロー側を疑う（`on:` 条件・`paths-ignore`・Actions の有効状態） |

**再発（2026-09-05・PR #960 / Issue #961）**: 同じ症状の 2 回目。`content/analytics/retro/deferred_try.jsonl` が
main と衝突して作成時から `dirty` → `quality-checks.yml` の run が約 30 分不在（`c55dbf1` / `c0cafbf` とも run なし）
→ `origin/main` をマージしたコミット `8f0966a` の直後に run 591 が `event: pull_request` で発火し success。
本エントリが既にあったのに到達しなかったのは、**マージ判定の条文（`pr-review-flow-summary.md`「マージ前」）が
「赤ならマージしない」しか規定しておらず、不在時に本エントリを引く導線が無かった**ため（教訓の不在ではなく
導線の不在）。#961 で条文に 3 状態（緑 / 赤 / 不在）の判定を明記し、不在の切り分けの第 1 段を `mergeable_state` の
確認にした（判定表は `pr-review-flow.md`「CI check run が不在のときの判定」）。

**なぜ Warm 層に置くか**: 症状（CI が走らない）と原因（コンフリクト）が結び付かず、
ワークフロー定義の調査に時間を溶かしやすい。ただし観測したときにだけ必要な知識で、常駐は不要。

---

## L-162: git の出力を解釈する検査ツールが「色付き diff」「shallow clone」で黙って合格する（2026-09-06）

**パターン**: `git diff` の出力を行頭アンカー（`+` / `-` / `@@` / `diff --git `）で解釈する検査ツールが、
実行環境の git 設定やクローン形態によって **1 行も抽出できないまま exit 0（合格）** を返す。テストは
fake runner で無着色の文字列を返すため、この破壊は **self-test では原理的に検出できない**。

**症状 1（色付き diff）**: `color.ui=always` が設定された環境では全行が ANSI エスケープ（`^[[1mdiff --git ...`）で
始まり、`startswith("@@")` も `startswith("-")` も成立しない。同型の破壊は `diff.external` 設定でも起きる。

- 🔴 **`git --no-color` はトップレベルオプションではない**（`unknown option` になる）。`-c color.ui=false` を
  トップレベル `-c` で渡し、あわせてサブコマンド側に `--no-color --no-ext-diff` を付ける
- 🔴 **`-c diff.external=` で外部 diff を無効化しようとすると git 自身が `error: cannot run :` / rc=128 で死ぬ**
  （実測）。空文字を渡すのではなく `--no-ext-diff` を使う

**症状 2（shallow clone）**: `git rev-parse --verify origin/main^{commit}` が rc=0 を返しても、
`git diff --name-only origin/main...HEAD` は **merge base 不在で rc=128**（`actions/checkout` 既定の
`fetch-depth: 1`）。ref の存在確認だけを preflight にしていると、変更集合が空のまま「対象 0 件 → 合格」に倒れる。
`.git/index.lock` 競合・タイムアウトでも同じ経路に落ちる。

**対策**:

- ref の存在確認では足りない。**実際に使う収集コマンドを 1 回叩いて rc を見る** preflight を置く
- 複数ソース（base range / worktree / cached）を見る設計で「**全滅したときだけ** 判定不能へ倒す」のは不十分。
  1 ソースでも非ゼロなら判定不能（exit 2）へ倒す（`git` の非ゼロは「差分が無い」を意味しないため）
- ANSI エスケープが混入していないかを出力側でも検査し、混入したら fail-closed にする
- 実 git（一時リポジトリ）で `color.ui=always` と shallow clone を再現する回帰テストを持つ

**参照実装**: `tools/check_module_contract_drift.py`（`_run_git()` の固定オプション・
`ensure_changed_collectable()`・`ensure_no_ansi()`）。横断検査は #1009。

**なぜ Warm 層に置くか**: git の出力を解釈するツールを新設・改修するときにだけ必要な知識で、常駐は不要。
ただし fail-open（PASS しながら何も守らない）に倒れるため、該当ツールを触るときは必ず参照する。
