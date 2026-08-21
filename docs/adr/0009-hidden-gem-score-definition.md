# ADR 0009: Hidden Gem を「被依存数に対する star の残差」と定義し、既存スコアを再実装しない

- **状態**: **承認**（定義は Phase 1 で実装しない構想。Phase 2 着手時に `Q-3` のパラメータを確定するまで一部が意図的に未確定）
- **日付**: 2026-08-20 JST
- **対応要件**: `Q-1` / `Q-2` / `Q-3` / `R-2` / `R-3` / `R-4` / `D-10` / `GR-1`〜`GR-4`
- **関連**: [PRD](../02_requirements/prd.md) §1.4 / §11 / [`open-questions.md`](../02_requirements/open-questions.md) §3 `Q-1`〜`Q-3` / §4.1 `R-2`〜`R-4` / [`lean-canvas.md`](../00_concept/lean-canvas.md) / [`initial-concept.md`](../00_concept/initial-concept.md)（編集しない一次資料）

---

## 1. 文脈

初期コンセプト [`initial-concept.md`](../00_concept/initial-concept.md) §3 は独自の `Gem Score` を「Maintenance Score（コミット密度 + Issue クローズ率）+ Doc Quality Score（README 構造解析）+ Dependency Signal（著名プロダクトからの依存数）」の合成として構想していたが、重み・正規化方法・スコアレンジ・再計算頻度・欠損値の扱いが未定で、**このままではテスト可能な受け入れ条件が書けない**（`Q-3`）。

さらに 2 点、コンセプトの前提そのものを揺るがす調査結果が [`open-questions.md`](../02_requirements/open-questions.md) §4.1 で得られている。

1. **`R-2`（GitHub 純正検索での代替可能性）**: 「star レンジで絞り込む」だけの検索は `stars:10..500 pushed:>...` の 1 クエリで再現できることが実測で確認された（n=1・要追試だが、根拠は後述のとおり本サンプル数に依存しない）。star 単純ランキング・star レンジ絞り込みは差別化にならない。
2. **`R-3`（既存スコアとの差分）**: OpenSSF `criticality_score` は既に 10 シグナルの加重和として一次資料の重複表（コミット頻度・Issue クローズ率など）と大きく重なっており、Maintenance Score / Doc Quality Score をそのまま実装すると `criticality_score` の再実装になる。

`Q-1`（コア機能を自プロジェクトの競合調査が否定している）と `Q-2`（Hidden Gem の操作的定義が存在しない）は、この 2 点を先に決着させない限りプロダクトの存在理由が書けない、と `open-questions.md` §5 の推奨進行順で明示されている。専門チームによる検証を経ずとも `R-2`〜`R-4` の一次調査結果だけで定義が一意に定まったため、`open-questions.md` §4.1 で推奨解として記録済みの内容を、本 ADR で ADR として確定させる。

---

## 2. 決定

### 2.1. Hidden Gem の定義

> **Gem とは、「実際に使われている度合い（被依存数）」に対して「注目度（star 数）」が不釣り合いに小さいリポジトリである。**

判定は **2 軸を役割分担させ、1 つのスコアに合算しない**（[PRD](../02_requirements/prd.md) §1.4）。

| 軸 | 指標 | 役割 |
|---|---|---|
| ① 過小評価度 | `Gem Index` = エコシステム内での「被依存数のパーセンタイル順位」−「star のパーセンタイル順位」（`Q-3`） | **並び順**（ランキング） |
| ② 健全性 | OpenSSF `criticality_score` / Scorecard（自作しない） | **足切り**（フィルタ） |

### 2.2. 既存スコアを再実装しない

- **健全性の評価は OpenSSF `criticality_score` / Scorecard に委ねる。** `initial-concept.md` の Maintenance Score（コミット密度 + Issue クローズ率）・Doc Quality Score（README 構造解析）は自作しない。
- **被依存数の取得は Ecosyste.ms に委ねる**（`R-4` の調査結果。被依存数を独自集計する ETL パイプラインを持たない）。
- `Gem Index` は `criticality_score` の代替品ではなく、`criticality_score` を **健全性フィルタの入力としてそのまま利用する**、別の軸（過小評価度）を測る指標として新設する。

### 2.3. 意図的に未確定のまま残すもの（Phase 1 の対象外・`Q-3` / `D-10` の残タスク）

🔴 **本 ADR は Hidden Gem の「定義」を確定させるものであり、Phase 2 の実装パラメータを確定させるものではない。** 以下は [PRD](../02_requirements/prd.md) §13「未決事項」に既に開いてあるとおり、Phase 2 の実データを見てから決める。

| 未確定パラメータ | 決定に必要なもの |
|---|---|
| パーセンタイルの母集団定義（`Q-3` 従属事項） | 対象エコシステム（`D-10`）ごとの実データ分布 |
| `Gem Index` のしきい値・足切り基準の具体値 | 実データのサイズと分布（[PRD](../02_requirements/prd.md) §13） |
| 配信件数（Gem 一覧の表示数） | 同上 |
| 対象エコシステムの最終確定（`D-10` は npm + PyPI を推奨に留める） | Ecosyste.ms のカバレッジ実測 |
| 名前解決（リポジトリ URL ↔ パッケージ名。モノレポ・リポジトリ URL 未設定への対応） | [`open-questions.md`](../02_requirements/open-questions.md) §11「Phase 2 の中核課題」 |

> 🔴 **`D-33`（2026-08-21）追記**: 本 ADR が定義する `Gem Index` の算出方法・符号の向きは撤回しない（日次ダイジェスト「今日の Gem」が使い続ける）。ただし **検索結果への適用（`sort=gem-index`・`SP-16` / `US-34`）は `D-33` により撤去された**。候補プールがユニーク 227 リポジトリに留まり、検索上位 100 件との一致が一般語ではほぼ 0 件という被覆率の問題（機能として成立していない）が理由であり、`Gem Index` の定義そのものの妥当性が否定されたわけではない。詳細・再導入条件は [`open-questions.md`](../02_requirements/open-questions.md) `D-33` を参照。

---

## 3. 理由

### 3.1. なぜ「星の多さ」ではなく「被依存数に対する star の残差」か

`R-2` の実測により、star レンジで絞り込むだけの検索は GitHub 純正検索の 1 クエリで再現できることが確定した。**star を分子（ランキングの直接指標）として使う限り、GitHub 純正検索に対する差別化が原理的に作れない。**

`Gem Index` は star を **分母** として使う。被依存数（実利用の量）に対して star（注目度）が不釣り合いに小さいほど順位が上がる。この設計は次の性質を持つ。

1. **GitHub 純正検索で原理的に再現できない**: 被依存数は GitHub API に存在しないため、`stars:` `topic:` 等の検索構文では表現不可能（`Q-1` / `Q-2` / `R-2`）。
2. **偽 star に構造的に頑健**: `competitive-analysis.md`（[`lean-canvas.md`](../00_concept/lean-canvas.md) `P-1` が引用）は約 600 万個の偽 star（He et al., ICSE 2026）を報告しており、star 単純ランキングは既に崩壊しているとされる。`Gem Index` は star を水増しすると値が **下がる**（ランキングから外れる）ため、この攻撃面を持たない。

### 3.2. なぜ 2 軸を合算しないか

過小評価度（`Gem Index`）と健全性（`criticality_score`）を 1 つのスコアに合算すると、「健全だが有名」なリポジトリが加重平均で上位に戻り、[PRD](../02_requirements/prd.md) §1.4 が否定した star 追随ランキングへ退化する。**役割を分離**（過小評価度＝並び順・健全性＝足切り）することで、「有名だが健全」なリポジトリは Gem Index が低いためランキング上位に出ず、「無名だが不健全」なリポジトリは健全性フィルタで除外される、という 2 軸それぞれの意図を独立に保つ。

### 3.3. なぜ健全性スコアを自作しないか

`R-3` の調査により、`initial-concept.md` の Maintenance Score（コミット密度・Issue クローズ率）が OpenSSF `criticality_score` の既存シグナル（`commit_frequency` / `closed_issues_count` / `updated_issues_count`）と重複することが判明した。[PRD](../02_requirements/prd.md) §2.3 の設計原則「既存のものを再実装しない」（`Q-1` / `Q-2` / `R-3`）に従い、健全性評価は自作せず OpenSSF に依存する。これにより Doc Quality Score（README 構造解析・自作の解析ロジックが必要）も採用しない。

### 3.4. なぜ `criticality_score` の再実装ではなく別物と言えるか

`criticality_score` が測るのは「重要度の絶対値」であり、多くのシグナルを重み付き加算した単一スコアである。`Gem Index` が測るのは「重要度（被依存数）に対する注目度（star）の不足＝残差」であり、**入力（被依存数・star）は一部重なるが、測っている概念自体が異なる**（絶対値 vs 相対的な乖離）。`R-3` の比較表で明示されたとおり、`dependents_count` 相当のシグナルは `criticality_score` にも含まれるが、Gem Index はそれを star との相対比較に転用する点で別物である。

---

## 4. 却下した選択肢

| 選択肢 | 却下理由 |
|---|---|
| **`initial-concept.md` の Gem Score（Maintenance + Doc Quality + Dependency Signal の合成）をそのまま実装する** | 重み・正規化・スコアレンジが未定でテスト可能な受け入れ条件が書けない（`Q-3`）。Maintenance / Doc Quality は OpenSSF `criticality_score` の再実装になる（`R-3`） |
| **star レンジ絞り込み（`stars:10..500`）を差別化機能として維持する** | GitHub 純正検索の 1 クエリで再現できることが実測で確定した（`R-2`）。差別化にならない |
| **過小評価度と健全性を 1 つのスコアに合算する** | 「健全だが有名」なリポジトリが上位に戻り、star 追随ランキングに退化する（§3.2） |
| **健全性スコアを自作する（README 構造解析・独自の Maintenance Score）** | OpenSSF が既に同等のシグナルを提供しており、車輪の再発明になる（`R-3`。[PRD](../02_requirements/prd.md) §2.3「既存のものを再実装しない」に抵触） |
| **被依存数を自前 ETL（GH Archive / BigQuery）で集計する** | `D-5` の「DB を持たない」設計原則と衝突し、Ecosyste.ms が既に被依存数を無料（IP 単位 5,000 req/h・認証不要）で提供している（`R-4`） |
| **母集団・しきい値・配信件数を本 ADR で確定させる** | 実データを見ていない段階で確定させると根拠のない前倒しの決定になる。[PRD](../02_requirements/prd.md) §13 が意図的に開いている（§2.3） |
| **deps.dev を被依存数の主データ源にする** | v3 API のエンドポイント一覧に被依存数取得の相当機能が確認できなかった（v3alpha は未確認・`R-4`）。Ecosyste.ms は提供ありと確認済み |

---

## 5. 結果（この決定がもたらすもの）

### 良い方向

- Phase 2 の実装着手時に、`Gem Index` の算出方法（パーセンタイル順位の差）と役割分担（並び順 / 足切り）を再検討する必要がない
- 健全性の評価ロジックを自作しないため、Phase 2 の実装量が「被依存数の取得（Ecosyste.ms 連携）」と「パーセンタイル計算」に限定される
- 偽 star への頑健性が設計そのものに組み込まれるため、`competitive-analysis.md` が指摘した star 崩壊問題への回答を Phase 2 の README にそのまま書ける

### 受け入れる代償

| 代償 | 緩和策 |
|---|---|
| 被依存数はパッケージレジストリ単位でしか取得できないため、Phase 2 の対象は「パッケージとして公開されているリポジトリ」に限定される（アプリ・設定集・学習用リポジトリは対象外） | [`open-questions.md`](../02_requirements/open-questions.md) §4.1 が指摘するとおり、これは同時に `initial-concept.md` が排除したがっていたノイズ（チュートリアル・課題提出用リポジトリ）を自動的に除外する利点でもある |
| `R-2` の実測が n=1（1 ドメインのみ）で、母数も 31 件と小さい | 主要根拠（被依存数が GitHub API に存在しないという API 仕様側の事実）はサンプル数と独立に成立するため、追試（言語・分野を変えた 3〜5 ドメイン）が未了でも定義の妥当性は揺らがない |
| Ecosyste.ms のデータは CC BY-SA 4.0（継承ライセンス） | 商用化する場合は商用ライセンスの取得可否を別途確認する必要がある（`R-8`。本 ADR の射程外） |

---

## 6. 参照

| ドキュメント | 関係 |
|---|---|
| [`prd.md`](../02_requirements/prd.md) §1.4 / §11 | Hidden Gem 定義・Phase 2 構想の正本 |
| [`open-questions.md`](../02_requirements/open-questions.md) `Q-1`〜`Q-3` / `R-2`〜`R-4` / `D-10` | 決定に至る調査・決定ログの正本 |
| [`lean-canvas.md`](../00_concept/lean-canvas.md) | UVP・検証状況（`P-1` / `P-2`・未検証事項） |
| [`initial-concept.md`](../00_concept/initial-concept.md)（編集しない一次資料） | 当初の Gem Score 構想（本 ADR が採らなかった案） |
