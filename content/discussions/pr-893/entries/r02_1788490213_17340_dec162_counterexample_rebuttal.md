<!--entry
author: counterexample
round: 2
kind: rebuttal
ts: 2026-09-04T11:50:12+09:00
-->

## counterexample Round 2: rebuttal + 検証

### 1. `correctness` の指摘1（synthesizer.name 非対称）を補強・実測で裏付け

`correctness` の claim は「Step 3 まで進んでから壊れる（fail-late）」「`--legacy` は exit 1 として報告される」
という 2 点を推測で書いていたが、実際に再現して確認した:

```
$ python3 tools/run_discussion_review.py --id repro-synth --spec /tmp/xxx.json --rounds 2 --dry-run
ERROR: spec 読み込み/検証に失敗: synthesizer name が不正です: 'lead x'（...）
EXIT=2

$ python3 tools/discussion_review_trigger.py --pr 999 --diff-lines 400 --spec /tmp/xxx.json --legacy
🔍 Layer 2 レビュー起動: 差分 400 行（閾値 300 行）
ERROR: spec 読み込み/検証に失敗: synthesizer name が不正です: 'lead x'（...）
⚠️ Layer 2 レビュー失敗（run_discussion_review.py exit 2）。Layer 1 / Layer 3 レビューで継続します。
EXIT=1
```
（spec: `synthesizer.name = "lead x"`、participants は正常な 2 名）

**追加で確認できた実害（correctness の claim に無かった点）**: `--legacy` 経路の失敗は
`run_discussion_review.py` 内部では `load_spec()` が投げた `ValueError`（= 本質的に spec 不正）
だが、`discussion_review_trigger.py` はこの rc=2 を「実行系と無関係」として一律 exit 1
（本ツールの docstring 定義では「PR 情報を取得できない / --legacy 実行が失敗した」＝**実行系の失敗**）
に丸めている。つまり呼び出し元は「exit 1 = 実行系のトラブル」と解釈し、「spec を修復せよ」という
正しい対処（本ツールの exit 2 の場合の案内文）を受け取れない。**判定器自身が『2 を 0 に丸めない』
（#881 本文）と明言している同じ精神からすると、『2 を 1 に丸めて原因を隠す』のも同種の情報欠落**であり、
correctness の指摘は severity WARNING のままで妥当だが、**「なぜ実害があるか」の具体的な機序
（exit code の意味論の混線）を追加で裏付けられた**。

### 2. `maintenance` の「validate_spec が Step 0 より厳格」への反証: 実際に正当な spec を弾ける

maintenance は「実害はない（判定器側が厳しい分には安全側）」と結論していたが、これは **誤り**。
`run_discussion_review.py` の `load_spec()`（レガシー実行系・本 PR 以前から存在）は
`synthesizer.instruction` も `verdict_schema` も一切要求しない。実際に検証した:

```python
spec = {
    "topic": "t", "brief": "b",
    "participants": [{"name":"alice","lens":"x"}, {"name":"bob","lens":"y"}],
    "synthesizer": {"name": "lead"},   # instruction 無し
    # verdict_schema も無し
}
```

- `validate_spec(spec)` → `(False, 'synthesizer（instruction 付き）がありません: ...')` → **判定不能 exit 2**
- `python3 tools/run_discussion_review.py --spec <同spec> --dry-run` → **exit 0**、lead プロンプトを正常生成
  （`--legacy` で実際に議論を回せる、正真正銘「動く」spec）

つまり **「レガシー実行系にとって正当（動く）な spec」を `validate_spec()` が exit 2 で弾く** ケースが
実在する。本 PR は `--spec` を新設し「下流フォークが自前の spec JSON を指定できる」ことを目的にしている
（`ai-reviewer-strategy.md` 差分）ため、レガシー由来の（`synthesizer.instruction`/`verdict_schema` を
持たない旧形式の）spec を下流フォークが `--spec` 経由で使おうとすると、**今まで `--legacy` で動いていたもの
が新設の判定器によって『判定不能』に格下げされる**という後方非互換が起きる。maintenance の severity は
WARNING のままで良いが、「実害はない」の部分は撤回すべきで、**「新規追加フィールドを要求する分だけ
fail-closed 側に振れており、旧形式 spec への後方互換は無い」と明記すべき**（fix 案: docstring か
`--spec` の help に「本ツールの `--spec` は `synthesizer.instruction` / `verdict_schema` を持つ新形式
spec のみ対応。旧形式のみを持つレガシー spec は `run_discussion_review.py --spec` を直接使うこと」と
1 行注記する）。

### 3. 自分自身（name 重複チェック）の過剰検知チェック: 既存 spec 33 本を全数走査、誤検知ゼロ

自分が round 1 で提案した修正（`len(set(names)) != len(participants)` で重複を弾く）が正当な spec を
誤って弾かないか、`tools/discussion_specs/*.json` 全 33 本の participants name を実際に列挙して確認した:

```
$ find tools/discussion_specs -name "*.json" | xargs -I{} python3 -c \
    'import json;d=json.load(open("{}"));print([p.get("name") for p in d.get("participants",[])])'
```
結果: 全 33 spec で participants name の重複は 0 件（`code_review.json` を含む）。
提案した修正を適用しても、リポジトリに現存するどの spec も弾かれない。

**ただし 1 点、自分の提案の弱さを認める（concession）**: 重複チェックを `name` の完全一致だけで見ると、
大文字小文字違い（`"Alice"` と `"alice"`）のような **実質的に区別困難だが文字列としては異なる** name は
素通りする。今回の 33 spec には該当例が無いため緊急性は無いが、修正時に「大文字小文字を区別しない重複」
まで見るかどうかは fix の設計判断として残る（自分は「区別しない」までは過剰検知のリスク
（意図的に `Alice`/`alice` を別人格として使う下流spec があれば弾いてしまう）があるため、
**完全一致の重複のみを exit 2 にする現状の提案どおりでよい** と考える）。
