<!--entry
author: lane_boundary
round: 1
kind: claim
ts: 2026-08-22T14:25:20+09:00
-->

# レーン責務境界（争点 A の案 2 / 争点 C）— lane_boundary 分析

## 1. #160 の決定は今も妥当か

`docs/rules/improvement-lane-map.md:52` のルール 2（`type:retro-try` → 振り返りレーン専管・改善 Issue レーンは扱わない）は **今も機能的に妥当** と判断する。「58% が二重ラベル」という実測は事実だが、その原因を実際に追うと **レーン分割の失敗ではなく、ラベルの直交軸が同じ `type:` prefix を共有しているだけ**、かつ **別レイヤーの実装漏れ（後述 §2）** であることが分かった。

### 二重ラベルの発生源を特定した

`open_issues.json`（113 件の `type:retro-try`）を `type:` 系ラベルの組み合わせで集計:

```
66 (type:improvement, type:retro-try)
31 (type:retro-try,)                 ← 単独
 9 (type:bug, type:retro-try)
 7 (type:docs, type:retro-try)
```

`type:improvement` だけでなく `type:bug`（9 件）`type:docs`（7 件）とも同型に共起している。「type:improvement を持つ Issue は改善レーンにも属する」という主張が成立するなら、「type:bug を持つ Issue はバグレーンにも属する」も成立しなければならないが、そんなレーンは存在しない。つまり `type:*` は **2 つの直交する軸**（① 内容分類＝improvement/bug/docs、② 由来＝retro-try）を 1 つの prefix に同居させているだけで、**dual-label は「両方のレーンが処理すべき」を意味しない**。

これは起票元（`retrospective/reference.md:242-249`）を読むと裏が取れる。新規 Try Issue のラベル配列はハードコードで:

```python
labels = [
  "type:retro-try",                       # ← フィルタ用の主キー（必須）
  "type:improvement",
  ...
]
```
（`retrospective/reference.md:245-247`）

コメント自身が `type:retro-try` を「フィルタ用の主キー」と明記しており、`type:improvement` はルーティングキーではなく **内容カテゴリの固定付与**（Try の性質上ほぼ全件が「改善」に分類されるため常時付く）。実際、title prefix と dual-label の相関を見ると `[Retro][...]` テンプレート由来の 10 件は 100% dual、`improvement:` に後から書き換えられた 56 件も dual、一方で `type:...:` / `fix:` / `docs:` prefix の 30 件は 0 件が dual（別の起票経路・おそらく棚卸し #385 前後の手作業/正規化）。多数派が dual なのは「テンプレートが機械的に両方貼るから」であって「内容が両属性を要求するから」ではない。

**ルール 2 自体は迷いなく機能する**: 一意判定ルールは「対象が `type:retro-try` →振り返りレーン」であり、他の `type:*` の有無を見ない。曖昧さはゼロ。

## 2. 案 1 と案 2 の比較

### 案 2（レーン統合）を採った場合に実際に壊れるもの

`type:retro-try` の除外は `improvement-lane-map.md` 1 箇所ではなく、**`self-improvement-loop/SKILL.md` 内に最低 3 箇所** 独立に埋め込まれている（実測）:

- `SKILL.md:37`「`type:retro-try` は振り返りレーンの担当。本スキルの消化モードは扱わない（奪い合い防止・#160）」
- `SKILL.md:142`（Step G-1.5 リファインメント対象抽出の除外条件）「`type:retro-try`（振り返りレーンの専管・#160 の奪い合い防止）」
- `SKILL.md:314`（消化モード実行フロー）「`type:retro-try`（振り返りレーンの担当）… を除外し、残り全件を…」
- frontmatter の `description` 冒頭にも「type:retro-try（振り返り由来の Try）は retro-try-handler … が担当する」と明記

案 2 は `improvement-lane-map.md` の書き換えだけでは終わらず、上記 4 箇所すべての除外条件を撤廃し、**さらに retro-try-handler が持つ専用ロジックを self-improvement-loop 側へ移植するか、失うかの二択**を迫られる。両者は処理の詳細度が全く別物と確認した:

| | retro-try-handler | self-improvement-loop 消化モード |
|---|---|---|
| 優先順位 | urgency ラダー（blocker→dep:blocking→quality/high→…）+ doc-only は **月曜のみ処理** という特殊規則 | priority:high→medium→なし→low の単純順 |
| 分類 | 8 カテゴリ（doc/script/validate/skill/user/tool-update/domain/dev-tool）× `reference.md` C-1〜C-7 の専用手順 | 「小〜中なら実装」という粗い工数判定のみ |
| 処理上限 | バックログ残件数に応じ動的 2〜5 件 | 固定 5 件/回 |
| model | `haiku`（安価・frontmatter 明記） | 指定なし（既定 `sonnet`。発見/整理モードは並列サブエージェント・discussion-review も抱える高コスト経路） |

統合すると (a) urgency ラダー・doc-only 月曜スキップという細かい制御を失うか、(b) それを self-improvement-loop に移植して二重実装になるかのどちらかで、**どちらも純増のリスクであって #377（到達不能の解消）には寄与しない**。さらに model 差（haiku vs sonnet 既定）はコスト面でも統合の根拠を弱める。これは `improvement-lane-map.md:78-82`「振り返り・監査/衛生は frontmatter（model/effort）と自動起動点が異なるため統合しない」という既存決定と正面から一致しており、今回の実測はこの決定を覆す根拠にならない、むしろ補強する。

### 案 1（責務維持）を採った場合に残る歪み

「二重ラベルの Issue はどちらのレーンが拾うのか」自体は歪みではない（ルール 2 で明確に retro-try が勝つ）。しかし **実装のバグとして #160 の除外が 1 箇所だけ漏れている** ことを発見した:

`tools/triage_improvements.py`（Step G-1「棚卸し」本体＝重複統合・Epic 化・priority/sp 補完のデータソース）は `--label type:improvement`（既定値、`triage_improvements.py:524`）で無条件フェッチし、`type:retro-try` を除外するコードが **どこにもない**（`fetch_issues`/`label_names` 全文 grep で `retro` 0 件ヒット）。

一方 `self-improvement-loop/SKILL.md` は Step G-1.5（リファインメント・142 行目）と消化モード（314 行目）では明示的に `type:retro-try` を除外しているのに、**Step G-1（棚卸し本体）だけ除外条件が実装されていない**（`SKILL.md:121`「Step G-1 のレポートは type:improvement に限定されるため本 Step では使わない」は G-1.5 の話で、G-1 自体の除外漏れには触れていない）。結果として **66 件の retro-try Issue が改善 Issue レーンの重複統合・Epic 化対象に混入している**。これは「レーン分割の設計ミス」ではなく「#160 のルール実装が 1 ツールだけ追従できていない」という **実装バグ**であり、案 1 のもとで直せば消える歪みである。

## 3. 結論

**案 1（責務維持）を推す。** #160 の決定・`improvement-lane-map.md` の一意判定ルール（L46-61）は書き換え不要。理由: (1) dual-label は直交軸の共有によるラベル表記の問題であって、ルーティングは既に一意（曖昧さ実測ゼロ）。(2) 案 2 は self-improvement-loop 内 4 箇所の除外条件撤廃＋retro-try-handler 専用ロジックの喪失/二重実装という実コストを生み、#377（到達不能の解消）には寄与しない。(3) 案 1 で唯一実在した歪みは lane 設計ではなくツールのバグで、狭い修正で閉じる。

### 移行手順（案 1 採用・バグ修正のみ）

1. `docs/rules/improvement-lane-map.md`: **変更不要**（L46-61 のルール 2 はそのまま維持）。
2. `tools/triage_improvements.py`: `fetch_issues()`（154-169 行目付近）の返り値、または呼び出し側で `type:retro-try` を含む Issue を除外する 1 行フィルタを追加する（Step G-1.5 が既に実装している除外条件と同じロジックを Step G-1 のデータソースにも揃える）。
3. `.claude/skills/self-improvement-loop/SKILL.md`: Step G-1 の説明（99-121 行目）に「`triage_improvements.py` は `type:retro-try` を除外済み（ツール側対応）」の 1 行注記を足し、G-1 と G-1.5 の除外条件が揃っていることを明記する。
4. 争点 A（決定木への挿入）は router_designer の設計に従い、`sprint-cycle-router` 側に retro-try-handler への到達経路を追加する（レーン境界の変更は不要、起動経路の欠落を埋めるだけ）。

以上、post 済み。
