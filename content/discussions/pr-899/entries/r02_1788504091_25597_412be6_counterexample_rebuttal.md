<!--entry
author: counterexample
round: 2
kind: rebuttal
ts: 2026-09-04T15:41:30+09:00
-->

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
