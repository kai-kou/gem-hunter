<!--entry
author: correctness
round: 1
kind: claim
ts: 2026-09-04T11:46:41+09:00
-->

## correctness — Round 1 claim

### 指摘 1（WARNING / CONFIRMED）: `validate_spec()` は `synthesizer.name` の name 規約を検証していない

- file: `tools/discussion_review_trigger.py:186-192`
- 失敗シナリオ: `synthesizer.name` に空白・記号・33 字超・末尾改行など name 規約違反の値を持つ spec を用意する
  （例: `{"name": "lead x", "instruction": "..."}`）。`validate_spec()` は `isinstance(synthesizer, dict) and synthesizer.get("instruction")`
  しか見ておらず `name` フィールドは一切参照しないため `ok=True`（判定不能ではない）になり、
  トリガーは「起動プランを出力」または `--legacy` 実行に進んでしまう。
  - ネイティブ経路: `discussion-review` スキル Step 0 は participants の name しか検証しない
    （SKILL.md L37: 「participants ≥ 2・name は英数字と `_-` 32 字以内」）ので、この場では検知されない。
    実際に破綻するのは Step 3 で lead が `discussion_whiteboard.py post <id> --author <synthesizer.name> ...`
    を叩く段（`tools/discussion_whiteboard.py:150` の `_validate_id`）まで進んでからで、議論を最後まで
    やらせた後に初めて失敗する（fail-late）。
  - `--legacy` 経路: `run_discussion_review.py:99-101` の `load_spec()` が `_check_name(synth_name, ...)` で
    `ValueError` を送出し、`discussion_review_trigger.py` はこれを exit 1（実行系の失敗）として報告する。
- 本 PR の docstring は「検証項目は `discussion-review` スキル Step 0 が spec を Read した直後に行うものと
  同じ」と書いており、Step 0 の記述とは一致しているが、**同じ関数が参照している `run_discussion_review.py`
  の `load_spec()` が実際に検証している範囲（participants name + synthesizer name）とは一致していない**。
  「spec が壊れているかどうかは事前に判定器で潰す」という #881 の目的からすると、この非対称は
  実行時まで検知が遅れる抜け穴になっている。
- 影響は低い（現行の同梱 spec `code_review.json` の `synthesizer.name` は `"lead"` で正しいため、
  今回のデフォルト運用では発火しない）。修正案: `validate_spec()` 内で `synthesizer.get("name")` が
  存在するときも `_PARTICIPANT_NAME_RE.fullmatch()` で検証する（1〜2 行の追加で足りる）。

### 指摘 2（WARNING / CONFIRMED・スコープ外だが直接関連するため記録）: `fullmatch` 化が本 PR のガード 1 箇所にしか及んでいない

- file: `tools/run_discussion_review.py:82`（`_check_name`）/ `tools/discussion_whiteboard.py:75`（`_validate_id`）
- 本 PR は `validate_spec()` のコメントで「Python の `$` は非 MULTILINE でも末尾改行の直前にマッチするため
  `match` だと `"a\n"` が通ってしまう」と明示し、`fullmatch` で塞いでいる。実際に実測して再現できた:
  ```
  >>> re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$').match('alice\n')
  <re.Match object; span=(0, 5), match='alice'>   # bypass
  >>> re.compile(...).fullmatch('alice\n')
  None                                              # 正しく拒否
  ```
  しかし **同一パターンを `.match()` で使っている `run_discussion_review.py:82` の `_check_name` と
  `discussion_whiteboard.py:75` の `_validate_id` はどちらも未修正のまま**（コード中の `dup-ok` コメントが
  示す通り意図的な重複実装であり、`discussion_review_trigger.py` の `validate_spec()` を通らない他の
  呼び出し経路（`native_fallback.py` 経由で `audit-runner` / `claude-code-spec-sync` 等が独自 spec を
  `run_discussion_review.py --spec ...` に渡すケース）では、末尾改行付きの name（例 `"alice\n"`）が
  今も素通りする。
  - 実害の程度: 全ての呼び出しが `subprocess.run`/`subprocess.call` を list 引数で使っており
    `shell=True` は使われていないため、シェルインジェクションには至らない（確認済み・grep で
    `shell=True` は 0 件）。実害は「改行入り author 名が git 管理下の whiteboard Markdown に
    埋め込まれる」程度の低リスクだが、この PR が明示的に指摘したのと同じバグクラスが姉妹ファイルに
    残っている点は本 PR のスコープ内で気づいた既存の齟齬（同じ regex を『新設』でなく『流用』した
    箇所）に該当しうるので記録する。**ブロッキングではない**（本 PR の対象 3 ファイルの外）。

### 指摘なし（確認した点）
- `validate_spec()` の TOCTOU（`is_file()` 後に `read_text()` が失敗するケース）は `except OSError` で
  `FileNotFoundError` を捕捉できており fail-closed（クラッシュしない）。
- `participants` の要素が非 dict（str/None/int/list）でも `isinstance` チェックが先にあるため例外は
  漏れない（self-test 済み・実装読解でも確認）。
- self-test の子プロセス実行は `--diff-lines` / `--labels` を明示指定しており、`gh` や外部ネットワークへの
  依存はない（フレーキー化の懸念なし）。
- `rc` を素通しせず exit 1 に丸める設計（`run_discussion_review.py` が spec と無関係の理由でも 2 を返す
  ことを `main()` の return 値から実際に確認: L242/245/251/258 がいずれも 2 を返す）は正しい。
- JST 表示・記録日時（`datetime-rules.md`）に関わるコードは本差分に含まれていない（対象外）。
