<!--entry
author: data_integrity
round: 2
kind: rebuttal
ts: 2026-08-20T20:24:18+09:00
-->

# round 2: data_pipeline round1 への rebuttal / concession（data_integrity）

## 1. concession: rankings の母集団スコープ（npm 単独 vs 混合）は解決したと認める

data_pipeline の実測 d（ecosyste-ms/packages のソース `package.rb` の `load_rankings`）が示す
`rankings[:stargazers_count] = registry.top_percentage_for(self, :stargazers_count)` は、
私が round1 §1「手段 A（最優先・決定的）」として提案した検証そのものである。`registry` オブジェクト経由でパーセンタイルを計算している以上、少なくとも計算の呼び出し単位が **エコシステム（registry = npmjs.org）単位で閉じている**ことは一次情報として確認できたと判断する。

→ **round1 で懸念していた「rankings が全エコシステム混合の母集団かもしれない」という疑いは、この時点で解消されたと認める。この懸念を理由に自前パーセンタイル計算を主張する部分は撤回する。**

## 2. concession: 極性（0=最上位）の矛盾指摘も、data_pipeline の実測 h で説明可能と判明

round1 で私は「chalk の `rankings.dependent_packages_count=0.0005476` が chalk の実際の人気度と矛盾する」と指摘したが、これは data_pipeline の実測 h（typescript: `dependent_packages_count=488,056`（実利用トップクラス）に対し `rankings.dependent_packages_count=0.0` → 0.0 が最上位という向き）によって **矛盾ではなく、単に「0 に近いほど上位」という向きの convention だった**ことが判明した。chalk の 0.0005476 はむしろ「被依存数で上位 0.05%」という筋の通った値であり、round1 の指摘（矛盾の指摘）はここで撤回する。

## 3. rebuttal（軽微・予防的）: 向きの反転は式の符号設計に事故のリスクを残す

ただし、この「0=最上位」convention と、ADR 0009 の文言「被依存数のパーセンタイル順位 − star のパーセンタイル順位」が素直に想定する **「高い値=多い方」という自然な convention** は逆向きである。この点を数式で確認する。

- ADR 0009 が意図する式（自然な convention。percentile が高い = その指標が多い）:
  `Gem Index = percentile_dep(自然) − percentile_star(自然)`
- Ecosyste.ms の `rankings`（0=最上位 convention）から自然な convention へ変換すると:
  `percentile_dep(自然) = 1 − rankings.dependent_packages_count`
  `percentile_star(自然) = 1 − rankings.stargazers_count`
- 代入すると:
  `Gem Index = (1 − rankings.dependent_packages_count) − (1 − rankings.stargazers_count) = rankings.stargazers_count − rankings.dependent_packages_count`

→ data_pipeline が §4 で提案した式（`rankings.stargazers_count − rankings.dependent_packages_count`）は、**両軸が同じ極性で反転しているために減算で自動的にキャンセルされ、ADR 0009 が意図する式と数学的に一致する**。式そのものは正しいと確認できた。

**しかしこれは「たまたま両辺が同じ向きに反転しているために結果的に正しい」だけであり、直感的には正しく見えない（`rankings.stargazers_count` を単独で「star が多いほど大きい値」と誤読するとバグを埋め込む）。** 実装時に以下 2 点を必須にすることを提案する（これは対立ではなく、data_pipeline の設計への追加要求）。

1. 実装コード（`tools/generate_gem_index.py` の compute フェーズ）に、上記の変換式（`1 − rankings.*` → キャンセル）をコメントとして明記する。「なぜ `star − dep` の順で引き算するのか」を将来の実装者が rankings の生値だけを見て誤読しないようにする。
2. **golden test を必須にする**: typescript（`rankings.dependent_packages_count=0.0`, `rankings.stargazers_count=0.0505` → Gem Index ≈ +0.05・被依存/star とも上位のため中立に近い正の値）と chalk（`rankings.dependent_packages_count=0.0005476`, `rankings.stargazers_count=0.6435` → Gem Index ≈ +0.64・被依存は上位だが star は相対的に低い＝典型的な「隠れた名品」寄りの高い正の値）の実測ペアを単体テストの固定値として組み込み、符号を取り違えるリグレッションを機械的に検出できるようにする。

## 4. 新たな未解決論点（data_pipeline の実測ではまだ解消されていない・round1「残す論点」の延長）

`registry.top_percentage_for(self, :stargazers_count)` はスコープが registry 単位であることは示すが、**その `top_percentage_for` の分母（population）が `registry.packages` の全 5,760,152 件なのか、それとも GitHub 解決済み（`stargazers_count` が非 null）のサブセットに限定されているのかは、引用されたソース断片だけでは判定できない**。

これは chalk の実測値（`rankings.stargazers_count=0.6435`）と整合性を検討すると具体的な疑問になる。npm 5,760,152 件の大多数は GitHub リポジトリが未解決（stars を持たない、または 0 扱い）と考えられる。もし分母が全量（5.76M 件）であれば、母集団の大部分が star=0 側に積み上がるため、chalk のように実際に GitHub star を一定数持つパッケージは「上位に近い」値（0 に近い）になるはずである。ところが実測値は 0.6435（下から見れば上位約 36%）であり、**「大多数が 0 扱いで下位に積み上がる」という前提と整合しにくい**。これは以下のいずれかを示唆する。

- (a) `top_percentage_for` の分母は GitHub 解決済みパッケージのサブセットに限定されている（＝ star 軸の母集団が npm 全量より暗黙に小さい）。
- (b) 分母は全量だが、GitHub 未解決パッケージの扱い（null 除外 / 0 換算 / 別枠）が私の想定と異なる。
- (c) 単純に、npm には chalk より GitHub star が多いパッケージが実際に相当数（数十万件規模）存在する（大規模フレームワーク・企業製 SDK・自動生成パッケージ群等）。

(a) が正しい場合、round1 の「残す論点」（stargazers 側の母集団が dependents 側より非対称に小さい）がそのまま再燃し、ADR 0014 §2.6 の「母集団は npm 全量」という不変条件との整合を追加検証する必要がある。(c) であれば単なる私の直感の誤りであり問題ない。

**data_pipeline への確認依頼**（round3 に向けて）: `top_percentage_for` メソッド本体（呼び出し元ではなく定義側。おそらく `registry.rb` か関連 concern）を確認し、分母の集合条件（`where` 句の有無・null 除外の有無）を実測してほしい。この 1 点が確認できれば、私の round1 からの懸念（母集団の完全性）は完全に解消できる。

## 5. まとめ

| round1 の懸念 | round2 判定 |
|---|---|
| rankings の母集団が npm 単独か混合か不明 | **解消（concession）**。ソース実測 d により registry 単位で閉じていると確認 |
| chalk の値が矛盾しているように見える | **解消（concession）**。0=最上位の向きで説明可能（実測 h） |
| 自前パーセンタイル計算を主，張とする理由 | **撤回**。上記 2 点が解消された以上、rankings をそのまま使う data_pipeline 案（§3.1 item 1）を支持する |
| 符号設計のリスク | **新規（軽微な rebuttal）**。式自体は正しいが実装コメント + golden test を必須要件として追加提案 |
| star 軸の母集団の完全性 | **未解決（rebuttal 継続）**。`top_percentage_for` の分母定義の実測が必要。round1 の「未解決として残す論点」と同根 |
