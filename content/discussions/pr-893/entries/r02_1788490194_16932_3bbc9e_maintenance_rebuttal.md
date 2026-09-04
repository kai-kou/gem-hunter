<!--entry
author: maintenance
round: 2
kind: rebuttal
ts: 2026-09-04T11:49:54+09:00
-->

## maintenance レンズ: Round 2 rebuttal/concession

### 1. counterexample の「name 重複 fail-open」（CRITICAL）に対して: 補強（concession + 具体化）

**同意し、テスト実効性の観点から根拠を追加する。**

これは単発のバグ報告ではなく、`docs/rules/sprint-development-rules.md` `SD-2` が要求する
「境界の外側の負ケース」（#750）そのものの欠落パターンである。#750 の要件は「正しい入力に対する
正解だけを固めた self-test は、判定範囲が広がる方向の欠陥を構造的に見逃す」というものだが、
今回の `validate_spec()` も **構造的に妥当（participants が dict・2 件・name/lens あり）だが
意味的には別カテゴリ（相互反論が成立しない）** という入力を一切テストしていない。既存 self-test の
失敗経路 1〜7 はすべて「構造がおかしい」ケース（型違反・欠落・regex 違反）で、「構造は正しいが
意味的に壊れている」ケースが 0 件という偏りは #750 が警告する偏りと同型。

**変異テストとして機能するかを実際に確認した**: `validate_spec()` に
`if len({p.get("name") for p in participants}) != len(participants): return False, "..."`
を足した場合、対応する self-test（`{name: "alice"} x2` を渡して `ok is False` を assert）は
実装ありなら緑、実装を削れば確実に赤になる（`len(participants) < 2` の既存チェックとは独立した
分岐のため、既存の失敗経路 1〜7 のどれとも重複しない新規の赤化ポイントになる）。つまり
counterexample が要求する修正は、既存の self-test 構造にそのまま 1 ブロック追加するだけで
`#686`（本番の主コードパスを通す）の要件も自動的に満たす（item 5 の子プロセス経由テストに
1 ケース足すだけで済む）。**修正コストは低く、CRITICAL 判定を支持する。**

### 2. scope の「validate_spec が load_spec をコピペ再実装している」（WARNING）に対して: 部分反証

**scope の指摘の事実認定（コピペ重複がある）自体は正しいが、提案する修正（`load_spec()` を
呼んで例外を握り潰す）は counterexample の CRITICAL を解決しない点を指摘する。**

`run_discussion_review.py:79-99` の `load_spec()` を実際に読んだ（file:79-99）。`load_spec()` 自身も
**participants の name 重複を一切チェックしていない**（92-98 行はループ内で個々の participant を
検証するだけで、集合としての一意性は見ていない）。つまり scope の提案どおり `validate_spec()` を
「`load_spec()` を呼んで例外を変換する」形に書き換えても、counterexample が実証した重複 name の
fail-open は **legacy 経路（`load_spec()` 自身）にも既に存在するため解消しない**。scope の提案は
「将来の乖離防止」（私が round 1 で指摘した WARNING と同種の懸念）には有効だが、今回の CRITICAL とは
独立した問題であり、優先順位を混同すべきでない。

一方で、私が round 1 で指摘した desync（`validate_spec()` が Step 0 記載より厳格）と scope の指摘は
根が同じ: **spec の「正しさ」の定義が `discussion-review/SKILL.md` Step 0 の記述・`validate_spec()`・
`load_spec()` の 3 箇所に分散し、どれも SSOT を名乗っていない**。これ自体は本 PR 単体の責任範囲を
超える構造的問題（Issue #612 の「統合はスコープ外」という既存の判断がまさにこれを追認している）
なので、本 PR をブロックする理由にはしない。ただし correctness の指摘 2（姉妹ファイルの `fullmatch` 未展開）
と合わせて、**1 つの Issue にまとめて Issue #612 の対象を拡張する** ことを推奨する（下記 3 で具体化）。

### 3. correctness の「姉妹ファイルの fullmatch 未修正」を Issue 化する場合の記録先: 補強（具体的な記録方法を提示）

**単発の PR コメントでは merge 後に失われる。本リポジトリの既存慣行に合わせた記録先を提案する。**

`tools/run_discussion_review.py:63` と `tools/discussion_whiteboard.py:59` には既に
`# dup-ok: ... 統合は Issue #612 のスコープ外` という **同一正規表現の意図的重複を追跡する定型コメント**
が存在する（本 PR より前から）。correctness が発見した「`fullmatch` 化が `validate_spec()` の
1 箇所にしか及んでいない」問題は、**この Issue #612（正規表現重複の統合検討）の射程そのもの** であり、
新規 Issue を別に立てるよりも Issue #612 の本文にコメントを追記して対象を拡張する方が、
既存の追跡単位と一致し文脈が失われない。

具体策（本 PR のスコープ外・別コミットで実施すべき）:
1. Issue #612 に「`_NAME_RE.match()` を使う箇所（`run_discussion_review.py:82` の `_check_name` /
   `discussion_whiteboard.py:75` の `_validate_id`）は末尾改行を通す抜け道があり、`validate_spec()` の
   `fullmatch` 化と非対称になっている」を追記する。
2. `tools/run_discussion_review.py:63` と `tools/discussion_whiteboard.py:59` の既存 `dup-ok` コメントに
   1 行足す（例: `# fullmatch 未対応（末尾改行を通す）。#612 で _NAME_RE 統合時に是正`）。
   このコメントは merge 後もコードに残るため、Issue 本文だけに書くより発見されやすい
   （`docs/rules/lessons/pr-review.md` の L-153 と同種の「気づいたら書き残す」原則に沿う）。
3. `docs/rules/lessons/pr-review.md` の L-153（本件の親 Issue #881 の教訓）に新規エントリを追加する
   必要は無い（L-153 は「判定器が指す前提ファイルの不在」というテーマで、今回の `fullmatch` 抜け道は
   別テーマ。無理に同じ教訓に混ぜると L-153 のスコープが曖昧になる）。

**severity 再確認**: correctness 自身が「ブロッキングではない」と明記しており同意する。ただし
「記録せず口頭指摘で終わらせる」と `agent-team-summary.md` の並行安全プリアンブルにより
このラウンドの参加者はファイル編集が禁止されているため、**verdict の `dropped` にも `blocking` にも
入れず、Issue 化タスクとして明示的に残す**ことを lead に要請する（`unresolved` ではなく
「対応方法は合意済みだが本 PR 外」の第 3 カテゴリとして verdict に含めるのが実態に合う）。
