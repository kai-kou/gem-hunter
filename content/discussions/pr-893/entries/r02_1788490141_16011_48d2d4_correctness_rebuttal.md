<!--entry
author: correctness
round: 2
kind: rebuttal
ts: 2026-09-04T11:49:01+09:00
-->

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
