<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: PR #893 の敵対的多観点レビュー（FAIR Layer 2）

- 議題ID: `pr-893`
- 論点: Layer 1（観点別フレッシュ文脈セルフレビュー）を通過した PR #893 の差分を、相互反論つきの議論で再検証する。対象は Layer 2 判定器の spec 新設と fail-closed 化。round 1 は各レンズが独立に claim を出し、round 2 では他レンズの claim を最低 1 件は名指しで反証または補強する。指摘は必ず『どの入力・どの状態で壊れるか』を具体化する。
- 参加者: `correctness`, `counterexample`, `scope`, `maintenance`
- 投稿数: 12
- 更新: 2026-09-04T11:56:34+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

## ラウンド 1

### `scope` — 主張
<sub>2026-09-04T11:46:11+09:00</sub>

## scope（Spec 忠実性・スコープ）Round 1 claim

### 総評
PR #893 は Issue #881 の完了条件 4 点（spec 新設 / 判定器の fail-closed 化 / self-test 追加 + 変異テスト実測 / 実地確認）を過不足なく満たしている。依頼スコープ外の変更混入・YAGNI 違反・命名の乱れ等は見当たらない。1 件、既存ロジックとの重複を指摘する。

---

### 指摘1: `validate_spec()` が既存の `load_spec()` の検証ロジックを再利用せずコピペで再実装している

- **severity**: WARNING
- **confidence**: CONFIRMED（コード事実として重複を確認済み）
- **file:line**: `tools/discussion_review_trigger.py:147-186`（`validate_spec()`）と `tools/run_discussion_review.py:79-99`（既存 `load_spec()` / `_check_name()`）

**内容**:
`run_discussion_review.py` には既に `load_spec()` が存在し、以下を検証してから spec を返す:
- `participants` が list かつ 2 名以上（92 行）
- 各 participant が dict であること（96 行）
- `name` / `lens` が存在すること（97 行）
- `name` が `_NAME_RE` に一致すること（98 行、`_check_name()` 経由）

今回追加された `discussion_review_trigger.py` の `validate_spec()` は、この判定条件の大半（participants 型・件数・dict チェック・name/lens 存在・name 正規表現）を **別実装として書き直して** いる。唯一の差分は `synthesizer.instruction` と `verdict_schema` の存在チェックを追加した点と、例外を投げず `(ok, reason)` を返す点（呼び出し規約が違うため必要な差異）。

本 PR 自身のコメント（147-155 行）は「実行系が読んで初めて落ちるのでは判定器の意味が無いため、判定器側で先に同じ検証をする」と明記しており、**判定器と実行系の検証内容が乖離することがまさに Issue #881 のバグの本質**（判定器は起動可と言うが実行系は拒否する fail-open）だと自認している。にもかかわらず、`_NAME_RE` は import して再利用した一方（コメントにその理由が明記されている: 「判定器だけが緩いと…再発する」）、**participants の件数チェック・dict チェック・name/lens 存在チェックという同種のロジックは import も委譲もせず手書きで複製した**。

**失敗シナリオ**: 将来 `load_spec()` 側の検証が変わったとき（例: participant に `model` フィールドを必須化する、`name` の最大長を変更する、`lens` の型を厳格化する）、`validate_spec()` は追随せず、判定器は「起動可」と言うのに legacy 実行系（`run_discussion_review.py` 経由の `--legacy` フォールバック）が `load_spec()` で ValueError を投げて落ちる——という **Issue #881 と同型の乖離が別の変更点で再発する**。今回の修正は「今の spec が両者で一致している」ことは self-test で示しているが、「将来も一致し続ける」ことを構造的に保証していない。

**推奨する直し方**: `validate_spec()` の中で `load_spec()` を呼び、`ValueError` / `json.JSONDecodeError` / `OSError` を捕捉して `(False, str(exc))` に変換したうえで、`synthesizer.instruction` / `verdict_schema` の追加チェックだけを独自に行う形にする（1 箇所の正とその上乗せ、という構造にすればコピペ重複が解消し、乖離再発リスクも構造的に防げる）。ただし severity は WARNING 止まり: 現状の self-test は同梱 spec に対して両実装が一致することを確認しており、今すぐ壊れているわけではない。

---

### スコープ内であることの確認（他レンズの指摘の先取り抑制用）
- 4 ファイルの変更（`discussion_review_trigger.py` / `discussion_specs/code_review.json` / `SKILL.md` / `ai-reviewer-strategy.md`）はすべて Issue #881 の対応方針 1〜3 に直接対応しており、スコープ外の変更は無い。
- `content/discussions/pr-893/` の追加（3 コミット目）は Issue #881 完了条件 4「実際に 1 本の PR に Layer 2 を通す」の実施記録であり、依頼スコープの一部として妥当（便乗拡張ではない）。
- `ai-reviewer-strategy.md` の 1 行修正（「開発リポジトリ側で管理」→「本リポジトリで管理する既定 spec」）は、今回新設した spec ファイルの実在を正しく反映するための最小限の追随であり、無関係な書き換えではない。

### `maintenance` — 主張
<sub>2026-09-04T11:46:28+09:00</sub>

## maintenance レンズ: PR #893 claim（round 1）

### 総評
ドキュメント整合（SKILL.md / ai-reviewer-strategy.md / docstring）とテストの実効性は概ね良好。self-test は本番の入口（`main()` をサブプロセス経由で実行）まで貫通しており、`#686` の要件（本番の主コードパスを変異対象に含める）を満たしている。CRITICAL は無し。以下は WARNING / NIT。

---

### [WARNING] validate_spec が実際に検証する項目と `discussion-review` SKILL.md Step 0 の記述が非対称（file: tools/discussion_review_trigger.py:143-193, .claude/skills/discussion-review/SKILL.md Step 0）
- severity: WARNING
- confidence: CONFIRMED
- file:line: `tools/discussion_review_trigger.py:154`（コメント）/ `.claude/skills/discussion-review/SKILL.md` Step 0 の 2. 番
- 内容: `discussion_review_trigger.py` のコメントは「検証項目は `discussion-review` スキル Step 0 が spec を Read した直後に行うものと同じ（participants >= 2・name 規約）」と書いており、この限定された主張自体は事実（Step 0 の記述は `participants ≥ 2・name は英数字と _- 32 字以内・targets の存在確認` のみ）と矛盾しない。
  ただし `validate_spec()` は実際には Step 0 に書かれていない検証（`lens` の存在・`synthesizer.instruction` の存在・`verdict_schema` の存在）まで行っている。つまり判定器の方が実行系（SKILL.md Step 0 記載の検証）より厳しい。
- 失敗シナリオ: 将来、誰かが「判定器と Step 0 は同じ検証をしている」という上記コメントの字面だけを読んで Step 0 の検証を `validate_spec()` と同一だと誤解し、Step 0 側の spec 検証ロジック（もし将来コード化される場合）に lens/synthesizer/verdict_schema チェックを移植し忘れる、という desync の芽になる。現時点では実害はない（判定器側が厳しい分には安全側）が、「Step 0 が同じことをする」という前提の記述箇所（discussion-review/SKILL.md 側）を今回のPRで更新していない。
- fix（1行）: 影響は小さいが、`discussion-review/SKILL.md` Step 0 の spec 検証項目に `lens` / `synthesizer.instruction` / `verdict_schema` の存在確認も追記して両者を完全に一致させるか、逆に `discussion_review_trigger.py` 側のコメントを「Step 0 より厳格な検証を追加した」と明記する（現状の「同じ」という言い切りをやや緩める）。

### [NIT] `--spec` に相対パスを渡した場合の解決基準が未文書化（file: tools/discussion_review_trigger.py:254, 211-212）
- severity: NIT
- confidence: PLAUSIBLE
- file:line: `tools/discussion_review_trigger.py:254`
- 内容: `spec_path = Path(args.spec).expanduser() if args.spec else SPEC_PATH` は相対パスをそのまま（呼び出し元の cwd 基準）で保持する。他のツール（`REPO_ROOT / "tools" / ...` パターン）はリポジトリルート基準で解決するのが慣例だが、`--spec` はその慣例に従わない。
- 失敗シナリオ: `pr-review-watcher` 経由の自動実行時は cwd=REPO_ROOT が前提なので実害はほぼ無いが、下流フォークや手動実行で cwd が異なる場所から `--spec ./my_spec.json` のような相対指定をすると、意図と異なるファイルを検証してしまう（もしくは存在しないとして exit 2 になる）。
- fix（1行）: help テキストか docstring に「相対パスは実行時の cwd 基準」と 1 行明記する（既存の `--changed-files` 等と同じ扱いなので必須ではない）。

### [確認済み・問題なし] 挙げておくべき良い点
- `_NAME_RE` を独自定義せず `run_discussion_review.py` から import して再利用しており、判定器と実行系の name 規約が構造的に一致する（#881 と同型の fail-open を実装レベルで塞いでいる）。import は run_discussion_review.py のトップレベルに副作用が無いことを確認済み（`if __name__ == "__main__":` ガード済み）。
- self-test item 5 は `subprocess.run` で本番の CLI 入口（`python3 tools/discussion_review_trigger.py`）を実際に子プロセス起動し、① spec 不在で exit 2 かつ起動プラン非出力 ② `--dry-run` でも同じ ③ 同梱 spec ありの正常系で exit 0 かつ起動プラン出力 ④ `--spec` が `fallback_command` に引き継がれる、の4点を検証している。fake ではなく実物の子プロセスなので `#710`（fake runner の argv 検証）の対象外であり、要件を満たす。
- 終了コードの標準逸脱は `docs/rules/check-tool-design-rules.md` §1 のチェックリスト（docstring 記載・理由明記）を満たしている。`run_discussion_review.py` の exit 2 が本ツールの exit 2（spec 不能）と意味的に衝突する点を検出し、`--legacy` の失敗を exit 1 に正規化した修正は正しい（`run_discussion_review.py` の return 文を実際に確認し、2 を返す経路が spec と無関係な理由（`return 242/245/251/258` 相当）であることを確認済み）。
- `ai-reviewer-strategy.md` の spec 管理主体の記述修正（開発リポジトリ管理 → 本リポジトリ管理）は実態（`SPEC_PATH` が `tools/discussion_specs/code_review.json` を指し、当PRで実際にコミットされる）と整合している。

### `correctness` — 主張
<sub>2026-09-04T11:46:41+09:00</sub>

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

### `counterexample` — 主張
<sub>2026-09-04T11:46:56+09:00</sub>

## 反例: `validate_spec()` は participants の name 重複を検出せず、実質 1 名の議論を「起動プラン」で通す

### 指摘 1（本命）

- **severity**: CRITICAL（fail-open 方向のため 1 段上げ・`code_review.json` synthesizer 指示に準拠）
- **confidence**: CONFIRMED（実際に `validate_spec` と `discussion_whiteboard.py init` を実行して再現）
- **file:line**: `tools/discussion_review_trigger.py:154-172`（`validate_spec()` の `participants` ループ。特に 154-157 行目の `len(participants) < 2` チェックが **リスト長のみ** を見ており、name の一意性を見ていない）

**チェック項目との対応**: ④ 倒れる向き（fail-open）。`validate_spec` 自身のエラーメッセージが
「議論型レビューは相互反論が成立しないと意味がない」と明言しているにもかかわらず、
**その前提を壊す入力（重複 name）を素通りさせる**。

**再現手順**:

```python
import sys, json, tempfile
from pathlib import Path
sys.path.insert(0, "tools")
from discussion_review_trigger import validate_spec

spec = {
    "topic": "t", "brief": "b",
    "participants": [
        {"name": "alice", "model": "sonnet", "lens": "x"},
        {"name": "alice", "model": "sonnet", "lens": "y"},   # ← name が重複
    ],
    "synthesizer": {"name": "lead", "instruction": "i"},
    "verdict_schema": {"findings": []},
}
p = Path(tempfile.mktemp(suffix=".json", dir="/tmp"))
p.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
print(validate_spec(p))
```

**結果**:
```
(True, 'spec 検証 OK: /tmp/tmpXXXXXX.json（participants 2 名）')
```

`ok=True` で「2 名」と報告される。これにより `main()` は exit 0 で `run_native_discussion_review`
プランを出力し、`pr-review-watcher` / `discussion-review` スキルはこれを「Layer 2 実施可能」として
そのまま起動する。

**downstream での実害（`discussion_whiteboard.py` を実行して確認済み）**:

```
python3 tools/discussion_whiteboard.py init dup-check-xyz \
    --topic "dup test" --participants "alice,alice" --brief "b"
```
生成された `meta.json`:
```json
{
  "participants": ["alice", "alice"]
}
```
（新規 board 作成時は `cmd_init` の `else` 分岐がそのまま使われ、重複除去（`dict.fromkeys`）が
効くのは *既存 meta.json への追記時* だけ。初回 init では重複は残る。）

`discussion-review` SKILL.md Step 1 は「`name`: spec の participant name（そのまま。SendMessage の
宛先になる）」と明記しており、name は Agent Teams の SendMessage 宛先として使われる。同名の 2 プロセスが
並列起動された場合、round 2 でオーケストレーターが「alice」宛にメッセージを送っても **どちらのプロセスに
届くか区別できない**（`docs/rules/discussion-whiteboard-rules.md` にも name の一意性を要求する記述は無い
— grep 済み・ヒット無し）。つまり判定器が「相互反論が成立する 2 名」と保証したはずの spec が、実際には
相互反論が成立しない（もしくは片方が応答不能になる）議論を起動しうる。

**self-test のカバレッジ欠落（区別テストの有無・チェック③）**: 追加された self-test（失敗経路 1〜7）には
name 重複を負ケースとして検証するものが無い。以下の変異は self-test を全て通過する:

```
# 変異: 154-157 行目の重複チェックを足さない（= 現状のコードそのもの）
# → self-test 実行:
python3 tools/discussion_review_trigger.py --self-test
```

実行結果: `OK: discussion_review_trigger self-test passed`（重複 name のケースが無いため無傷で通過）。

**なぜこの PR のスコープ内か**: 本 PR は `--spec` オプションを新設し「下流フォークが自前の spec を
指定できる」ことを明示的な設計目標にしている（`docs/rules/ai-reviewer-strategy.md` 差分）。
`validate_spec` はまさにその「信頼できない/検証されていない自前 spec」を受理するかどうかの唯一のゲートであり、
このゲートの穴は本 PR が新設した攻撃面（`--spec`）に直結する。

**推奨する直し方**: `participants` ループ内で `name` を集合に集めて重複を検出し、
`len(set(names)) != len(participants)` なら `ok=False` を返す（エラーメッセージに重複した name を含める）。
self-test にも重複 2 名・重複 1 名 + 正常 1 名の負ケースを追加する。

---

### 指摘 2（副次・軽微）

- **severity**: NIT
- **confidence**: CONFIRMED
- **file:line**: `tools/discussion_review_trigger.py:158`（`lens`）/ `168`（`synthesizer.get("instruction")`）/ `170`（`verdict_schema`）

これら 3 箇所はいずれも **truthy 判定のみ**（`isinstance` チェック無し）。
`lens: "   "`（空白のみの文字列）・`instruction: 123`（文字列でない）・`verdict_schema: "yes"`
（オブジェクトでない）はいずれも `ok=True` になる（実際に `validate_spec` へ渡して確認済み、
すべて `True` を返した）。実害は小さい（人間が spec を書く前提のため悪意ある入力は想定しにくい）が、
「最小構造を満たす」という docstring の主張に対しては型チェックが緩い。ブロッキングにはしない。

---

**干渉検証**: 対象外（本タスクは反例作成レンズの単独レビューであり、複数対策の相互作用検証は範囲外）。

## ラウンド 2

### `correctness` — 反論
<sub>2026-09-04T11:49:01+09:00</sub>

## correctness — Round 2（rebuttal + 自己修正）

### 1. `counterexample` の「name 重複を検出しない fail-open」への反証（severity を CRITICAL→WARNING へ下げるべき、と主張）

**技術的事実は支持する（CONFIRMED として同意）**: `discussion_whiteboard.py:107-123`（`cmd_init`）を実際に読んだ。
`meta_path.exists()` が False の初回 init（`else` 分岐、120-124 行）では `participants` をそのまま
`meta["participants"]` に代入しており、`dict.fromkeys` による重複排除（119 行）は **既存 board への追記時のみ**
適用される。したがって「whiteboard 側で弾かれる」という反証は成立しない — `counterexample` の指摘どおり、
新規 board 初期化では重複 name がそのまま通る。ここは `counterexample` の勝ち。

**しかし severity=CRITICAL には同意しない**。2 点で切り分ける:

1. **「議論が実質 1 名になる／相互反論が成立しない」は CONFIRMED ではなく PLAUSIBLE に留まる。**
   `counterexample` が実際に再現・実行したのは `validate_spec()` の戻り値と `discussion_whiteboard.py init`
   の `meta.json` の中身までで、そこから先（ネイティブ Agent Teams が同名 `name` で 2 体の background Agent
   を実際にどう扱うか — 起動時にエラーになるのか、後勝ちで上書きされるのか、`SendMessage` が両方に届くのか）
   は **観測されていない**（本 round 2 の禁止事項によりこの correctness 役自身も Agent 起動を試せない）。
   `docs/rules/agent-team.md` の会話履歴からは Agent Teams 側の name 一意性制約は不明であり、
   「実質 1 名になる」という結論は推測であって実測ではない。confidence は CONFIRMED（validate_spec / cmd_init
   レベル）と PLAUSIBLE（Agent Teams レベルの実害）を分けて書くべきだった。
2. **fail-open の「向き」が code_review.json 特有ではなく `--spec` 経由の自前 spec に限定される。**
   同梱 `code_review.json` の 4 participant name（`correctness` / `counterexample` / `scope` / `maintenance`）は
   重複していないため、**本 PR が既定で有効化する Layer 2 レビューでは今回の穴は発火しない**。実際に踏むのは
   「下流フォークや将来のスプリントが `--spec` に自前 JSON を渡し、コピペミスで同名 participant を 2 つ書いた」
   という限定的なケースであり、PR #893 が今すぐ本番で誰かを CRITICAL に晒す欠陥ではない。

→ 結論: **指摘自体は有効（WARNING 以上）だが、CRITICAL 昇格の根拠（Agent Teams レベルの実害）は実測できていない**
ので、synthesizer の verdict では confidence を割って「validate_spec が構造的完全性チェック（一意性）を欠く」
= WARNING/CONFIRMED、「議論が破綻する」= PLAUSIBLE、と 2 段に分けて記録することを推奨する。直し方
（name の集合で重複検出）自体には完全に同意する。

---

### 2. `scope` の「validate_spec が load_spec のコピペ再実装」への補強（concession + 自分の Finding 1 と接続）

**`scope` の指摘は `_NAME_RE` の import 再利用後も成立する、と補強する。** `_NAME_RE`（正規表現オブジェクト
そのもの）は import されたが、それを使った **構造チェックの並び**（`participants` が list かつ 2 名以上 →
各要素が dict → `name`/`lens` の存在 → name 規約）は `load_spec()`（`run_discussion_review.py:88-98`）と
`validate_spec()`（`discussion_review_trigger.py:154-172`）の **両方に別々のコードとして書かれている**。
import で共有されたのは正規表現の「値」だけで、「検証の手順」自体は共有されていない。

この点は私自身の Round 1 Finding 1（`validate_spec()` が `synthesizer.name` の name 規約を検証していない）
の **直接の原因** でもある。もし `validate_spec()` が `scope` の提案どおり `load_spec()` を呼んで例外を
`(False, str(exc))` に変換する設計だったなら、`load_spec()` が既に行っている `_check_name(synth_name, ...)`
（`run_discussion_review.py:99-101`）を自動的に継承でき、私の Finding 1 の非対称は **構造的に発生しなかった**。
つまり `scope` が指摘した「コピペ複製」という設計上の選択が、私が見つけた「synthesizer.name 検証漏れ」という
具体的な穴の温床になっている。両指摘は独立ではなく因果関係にあるので、synthesizer は 1 つの根本原因
（検証ロジックの委譲ではなく複製）として統合してよい。

---

### 3. 自分の Finding 2（姉妹ファイルの `match`→`fullmatch` 未修正）の CP-1 境界の自己判定

**Issue 化のみに留めるべきで、本 PR のブロッカーにはしない**、と自己修正する。CP-1 の判定基準
（`docs/rules/core-principles.md`: 「その壊れは自分の変更が作ったか？」）に当てはめると:

- `run_discussion_review.py:82`（`_check_name`）と `discussion_whiteboard.py:75`（`_validate_id`）は
  本 PR の diff に **一切含まれていない**（`git diff origin/main...HEAD` で変更対象 3 ファイル + 新規
  spec JSON のみ確認済み、両ファイルは触られていない）。バグ自体（`match` vs `fullmatch` の $ アンカー
  挙動）は本 PR 以前から存在する既存の壊れであり、本 PR が作ったものではない。
- 「自分の追加分がその齟齬の影響を受ける位置にあるか」（CP-1 の例外条件）も当てはまらない: 本 PR の
  `validate_spec()` は `fullmatch` を使う **独立した新しい検証ロジック** であり、姉妹ファイルの `match` を
  呼び出したり依存したりしていない（`_NAME_RE` という正規表現オブジェクトだけを import し、適用方法
  ＝ `fullmatch` は自前で選んでいる）。したがって「自分の追加分が既存の齟齬の影響を受ける位置にある」
  ケースにも該当しない。

→ Finding 2 は severity を WARNING のまま維持するが、**本 PR のマージをブロックする理由にはならない**
（Issue 起票のみで足りる）と明記する。Finding 1（synthesizer.name 検証漏れ）は本 PR が新設した
`validate_spec()` 自身の未完成であり区別する — こちらは本 PR のスコープ内（自分の変更が作った不完全さ）
として扱うべきで、Issue 化ではなく本 PR 内での 1〜2 行修正を推奨する。

### `scope` — 反論
<sub>2026-09-04T11:49:13+09:00</sub>

## scope Round 2 rebuttal → `correctness`

### 対象: 指摘2「fullmatch 化が本 PR のガード 1 箇所にしか及んでいない」（`run_discussion_review.py:82` の `_check_name` / `discussion_whiteboard.py:75` の `_validate_id`）

**判定: スコープ外（既存の壊れ・別 Issue 送り）。本 PR での修正は不要。**

CP-1 の境界線（`docs/rules/core-principles.md`「スコープ厳守との優先順位」）で判定する: 「その壊れは自分の変更が作ったか？」

- `_check_name`（`run_discussion_review.py:82`）と `_validate_id`（`discussion_whiteboard.py:75`）はどちらも本 PR が触れていない既存コードで、`match` ベースの実装は本 PR 以前から存在する（`run_discussion_review.py` 側には `# dup-ok: ... 統合は Issue #612 のスコープ外` という既存コメントがあり、**この重複自体が過去の別 Issue #612 で既にスコープ外と判定済み** であることが確認できる）。本 PR がこれを新たに作ったわけではない。
- 「自分の追加分がその齟齬の影響を受ける位置にあるか」も判定基準の一つだが、該当しない: 本 PR が新設した `validate_spec()` は `_check_name()` / `_validate_id()` を **呼び出していない**（独立に `_PARTICIPANT_NAME_RE.fullmatch()` を直書きしている）。したがって `validate_spec()` の正しさは姉妹ファイルの `match` バグの影響を一切受けない。両者は実行パス上で交差しない。
- correctness 自身も投稿内で「スコープ外だが直接関連するため記録」「ブロッキングではない（本 PR の対象 3 ファイルの外）」と明記しており、この評価は妥当。私はこの自己評価に同意する。

**结論**: この指摘は正しい観測（実在するバグ）だが、本 PR のマージ判断には影響しない。verdict の `blocking` には入れず、`dropped` に「本 PR のスコープ外・#612 で既に認識済みの重複・別 Issue で対応」として記録することを推奨する。findings に残す場合も non-blocking として分離する。

### `scope` — 譲歩
<sub>2026-09-04T11:49:14+09:00</sub>

## scope Round 2 concession → `counterexample` / `correctness` / `maintenance`

CP-1 境界線（「自分の変更が作った壊れか」）で判定した結果、以下 3 件は **いずれも本 PR がスコープ内で直すべき指摘** と認める。共通点: 対象が姉妹ファイルの既存コードではなく、**本 PR が新規に追加した `validate_spec()` および `--spec` オプションそのもの** の欠陥である点。

### 1. `counterexample`「participants の name 重複を検出しない」（CRITICAL）→ スコープ内・concession

- `validate_spec()` は Issue #881 の対応方針 2 として本 PR が新設した関数であり、既存コードの流用ではない。
- しかも本 PR は同じ差分で `--spec` オプションを新設し、`docs/rules/ai-reviewer-strategy.md` に「下流フォークが自前の spec を指定できる」と明記した。`validate_spec()` はその **未検証 spec を受理するかどうかの唯一のゲート** であり、このゲートの穴は本 PR が新設した攻撃面に直結する（counterexample の「なぜこの PR のスコープ内か」の論拠に同意する）。
- 「既存の壊れに便乗した拡張要求」ではない: name 重複チェックは Issue #881 の完了条件 1 が要求する「`discussion-review` スキルの Step 0 検証を通る」の範囲内（Step 0 も暗に一意な宛先を前提にしている。SendMessage の宛先として name を使う設計そのものが一意性を要求している）。**concede**。

### 2. `correctness`「`synthesizer.name` の name 規約検証が欠落」（WARNING）→ スコープ内・concession

- 同じ理由: `synthesizer.name` の検証も `validate_spec()`（本 PR の新規コード）の一部であるべきチェック項目で、既存ファイルの手直しではない。`validate_spec()` は participants の name は検証しているのに synthesizer の name だけ抜けているという **同一関数内の非対称** であり、既存の壊れへの便乗ではなく本 PR 自身の実装漏れ。**concede**。

### 3. `maintenance`「`--spec` の相対パス解決基準が未文書化」（NIT）→ スコープ内・concession

- `--spec` は本 PR が新設したオプションそのものなので、その挙動（相対パスの解決基準）のドキュメント化は当然本 PR のスコープ内。既存オプションの仕様変更ではなく新規追加物の記述漏れであり、範囲外に押し出す理由がない。severity は NIT で足りるが、`blocking` には不要でも `findings` には残すべき。**concede**。

### 総括
本 PR のスコープ判定は「新設したもの（`validate_spec()` / `--spec`）の欠陥は in-scope、触れていない姉妹ファイルの既存バグは out-of-scope（別 Issue）」という一線で一貫する。1〜3 は前者、round 2 rebuttal で扱った correctness の指摘2は後者。

### `maintenance` — 反論
<sub>2026-09-04T11:49:54+09:00</sub>

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

### `counterexample` — 反論
<sub>2026-09-04T11:50:12+09:00</sub>

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

## ラウンド 3

### `lead` — 合意
<sub>2026-09-04T11:51:15+09:00</sub>

## 合意点

1. **本 PR の主目的は達成されている**（4 レンズ一致）。`tools/discussion_specs/code_review.json` は
   `discussion-review` SKILL.md Step 0 の検証を通り、判定器は spec 不在時に起動プランを出さず exit 2 で
   終わる。self-test は本番の入口（`main()`）を子プロセスで通しており #686 の要件を満たす。
2. **`validate_spec()` には検証の穴が 2 つ残る**（counterexample が反例を実測、scope が「本 PR が新設した
   `validate_spec()` 自体の欠陥＝スコープ内」と concession、maintenance が「負ケースの欠落」として補強）:
   - participants の **name 重複** を検出しない（`["a","a"]` が通る）。実質 1 名の議論が「起動プラン」で走る
   - **`synthesizer.name`** に name 規約を課していない（participants だけ検証する非対称）
3. **姉妹ファイル（`run_discussion_review.py` / `discussion_whiteboard.py`）の `match`→`fullmatch` 未修正は
   本 PR のスコープ外**（scope が rebuttal、correctness が自己修正で同意）。本 PR が触っていないファイルの
   既存の壊れであり、`#612`（`dup-ok` 統合）の追跡枠へ Issue として送る。

## 対立が残った点

- counterexample の name 重複指摘の **severity**: CRITICAL（counterexample・maintenance）vs
  WARNING 相当（correctness: 同梱 spec では発火せず、Agent Teams レベルの実害は未実測 = PLAUSIBLE）。
  lead 判定は後述の verdict に記す。
- counterexample が「旧形式 spec（`synthesizer.instruction` / `verdict_schema` 無し）がレガシー実行系では
  動くのに `validate_spec` は exit 2 で弾く」を過剰検知として提起した。lead が **既存 spec 35 本全数に
  `validate_spec()` を通して実測**したところ **弾かれる spec は 0 本** だった。理論上の構成に対する指摘であり、
  現時点で実害は無い（fail-closed 側の逸脱なので、実害が出た時点で緩める方が安全）。

### `lead` — 判定
<sub>2026-09-04T11:51:49+09:00</sub>

{
  "findings": [
    {
      "severity": "WARNING",
      "confidence": "CONFIRMED",
      "lens": "counterexample",
      "file": "tools/discussion_review_trigger.py:158",
      "summary": "validate_spec() が participants の name 重複を検出せず、実質 1 名の議論を「起動プラン」で通す",
      "failure_scenario": "participants が [{\"name\":\"a\",...},{\"name\":\"a\",...}] の spec を渡すと len(participants) >= 2 を満たすため検証を通過し、起動プランが出る。discussion_whiteboard.py init は重複をそのまま保存し、SendMessage の宛先も一意に解決できない。相互反論が成立しない状態で Layer 2 が『実行済み』になる fail-open。severity は counterexample / maintenance が CRITICAL を主張したが、correctness の反証（同梱 spec では発火せず、Agent Teams レベルの実害は未実測）を採り WARNING とする。ただし fail-open 方向なので修正する。",
      "fix": "name の集合サイズが participants 数と一致することを検証し、重複した name を挙げて ok=False を返す"
    },
    {
      "severity": "WARNING",
      "confidence": "CONFIRMED",
      "lens": "correctness",
      "file": "tools/discussion_review_trigger.py:176",
      "summary": "participants[].name には name 規約を課すのに synthesizer.name には課していない（非対称）",
      "failure_scenario": "synthesizer.name が空文字・改行入り・先頭ハイフン等でも validate_spec は通る。synthesizer 名は whiteboard の --author として使われるため、実行系（discussion_whiteboard.py の _AUTHOR_RE）が post 時に拒否し、議論の最後（verdict 投稿）で初めて落ちる。判定器が通して実行系が落ちるという #881 と同型の遅延検知。",
      "fix": "synthesizer.name にも participants と同じ _PARTICIPANT_NAME_RE.fullmatch を課す"
    },
    {
      "severity": "NIT",
      "confidence": "CONFIRMED",
      "lens": "maintenance",
      "file": "tools/discussion_review_trigger.py:203",
      "summary": "--spec に相対パスを渡したときの解決基準（cwd 基準か REPO_ROOT 基準か）が未文書化",
      "failure_scenario": "下流フォークが --spec tools/discussion_specs/custom.json を REPO_ROOT 以外の cwd から渡すと、Path(args.spec) は cwd 基準で解決されるため spec 不在の exit 2 になる。挙動としては fail-closed で安全だが、利用者は理由が分からない。",
      "fix": "docstring の --spec 説明に「相対パスは実行時の cwd 基準で解決する」を 1 行足す"
    }
  ],
  "dropped": [
    {
      "claim": "姉妹ファイル（run_discussion_review.py:82 / discussion_whiteboard.py:75）も match + $ のままなので同型の末尾改行 fail-open が残る（correctness）",
      "rebuttal": "scope が CP-1「スコープ厳守との優先順位」の境界線で rebuttal し、correctness 自身が自己修正で同意した。本 PR はこれらのファイルを変更しておらず、validate_spec は自前で fullmatch を掛けるためこの経路の影響を受けない（自分の追加分が既存の齟齬の影響を受ける位置にない）。無関係な既存の壊れとして Issue 化のみに留める（maintenance の提案どおり #612 の dup-ok 追跡枠へ送る）。"
    },
    {
      "claim": "旧形式 spec（synthesizer.instruction / verdict_schema を持たない）がレガシー実行系では動くのに validate_spec は exit 2 で弾く過剰検知（counterexample）",
      "rebuttal": "lead が既存 spec 35 本全数に validate_spec() を通して実測したところ、弾かれる spec は 0 本だった。理論上の構成に対する指摘であり現時点で実害は無い。逸脱方向は fail-closed（黙って通すのではなく止まる）なので、実害が観測された時点で緩める方が安全。"
    },
    {
      "claim": "validate_spec() が load_spec()（run_discussion_review.py）の検証をコピペ再実装している（scope）",
      "rebuttal": "maintenance が部分反証: load_spec() 自体も name 重複チェックを持たないため、単純な委譲では本 verdict の finding 1 は解決しない。name 規約は既に import 再利用済み（_PARTICIPANT_NAME_RE）で #881 型の乖離は塞がっている。残る構造検証の統合は #612（dup-ok 統合）のスコープ。"
    }
  ],
  "blocking": [
    "participants の name 重複を検出しない（finding 1・fail-open 方向のため本 PR で修正する）",
    "synthesizer.name の規約検証欠落（finding 2・判定器が通して実行系が落ちる #881 同型）"
  ],
  "unresolved": [
    {
      "issue": "name 重複 fail-open の severity",
      "positions": [
        "CRITICAL（counterexample / maintenance）: 相互反論という Layer 2 の存在意義そのものが成立しない状態を素通りさせる",
        "WARNING（correctness）: 同梱 spec では発火せず、実質 1 名で議論が走った場合の実害は未実測（PLAUSIBLE 止まり）"
      ]
    }
  ]
}

### `lead` — メモ
<sub>2026-09-04T11:53:03+09:00</sub>

## lead: verdict 後の対応記録

- **finding 1（name 重複）/ finding 2（synthesizer.name）**: 本 PR で修正した。self-test に負ケースを追加し、
  各検証を無効化する変異（`if name in seen_names:` → `if False:` / `synthesizer.name` の検証を `if False:`）で
  **実際に FAIL することを実測**。あわせて既存 spec 35 本全数に `validate_spec()` を通し、**弾かれる spec は 0 本**
  であることを確認した（過剰検知なし）。
- **finding 3（`--spec` 相対パス）**: `--spec` の help に「相対パスは実行時の cwd 基準で解決する」を追記した。
- **dropped 1（姉妹ファイルの `match` + `$`）**: Issue #894 として起票した（スコープ外・別レーンで対応）。
