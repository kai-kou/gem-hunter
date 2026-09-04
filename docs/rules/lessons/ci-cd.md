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

**なぜ Warm 層に置くか**: 症状（CI が走らない）と原因（コンフリクト）が結び付かず、
ワークフロー定義の調査に時間を溶かしやすい。ただし観測したときにだけ必要な知識で、常駐は不要。
