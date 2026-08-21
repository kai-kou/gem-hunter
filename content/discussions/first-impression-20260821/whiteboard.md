<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: 初見ユーザーのフィードバック 10 件（用語・説明・データ整合・体感速度）への対応方針を確定する（Issue #308）

- 議題ID: `first-impression-20260821`
- 論点: 飼い主が本番相当のトップページ（スマートフォン）を初めて触った際の生のフィードバック 10 件。原文: ①「今日の Gem」とあるが『Gem って何？』となった ②「キーワードで GitHub のリポジトリを検索します。」が初期のままで、どういったツールなのか説明しきれていない ③「被依存数」が分からなかった。説明を増やすより直感的に分かる名称にしたい ④「Gem Index」も同様 ⑤「Data via Ecosyste.ms」って何？となった ⑥「検索結果 / キーワードを入力して検索してください。」はない方が自然に思えた ⑦ 一覧と詳細とでスター数などが不一致しているのが気になった ⑧（要望）詳細で README が読めるといい ⑨ 検索→Gem Index 順とした際に検索にかかる時間が長く不安になった。早くすることも大切だが、なぜ時間がかかっているのかも分かると良い ⑩ 検索リストに Gem Index の数値がなく不安になった。

既知の技術的事実（調査済み・前提として扱ってよい）: (a) ダイジェストの stars / dependentCount は Ecosyste.ms バッチが生成した静的 JSON `public/data/daily-digest.json`（generatedAt = 2026-08-20T16:56Z のスナップショット・候補 294 件 / ユニークリポジトリ 227）由来。一方、詳細画面 `RepositoryDetail` は GitHub API のライブ値。出所が違うので star 数が一致しない。 (b) `sort=gem-index` は GitHub 検索 API に無い自前指標のため、`src/usecases/search-repositories.ts` が per_page=100 × 最大 10 ページを **逐次** 取得してから並べ替える（D-30 ②の代償として open-questions.md に記録済み）。 (c) 検索一覧への Gem Index 表示は SP-16 / PR #293 で実装済み（`src/ui/repository-list.tsx` の `gemFacets`）。本番 URL に出ていない理由の候補は「本番デプロイ経路の移行（D-31）が未完で main と本番が乖離している」か「候補プール 227 リポジトリの被覆率が低く、多くの検索結果が Gem Index 情報なし側に落ちる」。 (d) Gem Index = 被依存数パーセンタイル順位 − star パーセンタイル順位。値が小さい（強い負値）ほど過小評価＝上位（ADR 0009 / gem-index.ts）。0 が最上位のランキングを入力にするため、UI に出る値は -6.7〜0.0 程度の負数になる。 (e) 文言は `messages/ja.json` / `messages/en.json` の 2 言語。UI は props 経由で受け取る（E-4）。 (f) 候補プールに `react` → `react/react` のような誤ったリポジトリ名解決が混ざっている（正しくは facebook/react）。

争点: A) 「Gem」というプロダクト中核語をどう扱うか（残して説明を足すか / 表示語を変えるか）と、トップの説明文をどう書き直すか。B) 「被依存数」「Gem Index」の表示名をどうするか（直感的な代案を複数出し、誤解を生まないかを相互検証する。負数が並ぶ Gem Index を数値のまま出すのが妥当かも含む）。C) 出典表示（Data via Ecosyste.ms）と idle 文言・「検索結果」見出しの扱い。D) 一覧（静的プール）と詳細（ライブ API）の数値不一致をどう解消するか（片方に寄せる / 鮮度を明示する / 表示項目を削る）。E) gem-index 順検索の体感時間（最大 10 リクエスト逐次）を、速度と透明性の両面でどう改善するか。F) 詳細画面での README 表示（要望⑧）を今スプリントに入れるか別 Issue にするか。

制約: NFR-21（アプリコードに PaaS 固有 API を持ち込まない）/ NFR-3（トップはクライアント JS を持たない Server Component 方針）/ D-29（Ecosyste.ms の生テキストは再配信しない・帰属表示は省略できない）/ NFR-5 のレート予算 / ドメイン語彙の SSOT は docs/03_design/data-model/domain-model.md / 受け入れ条件の SSOT は docs/02_requirements/prd.md §6。YAGNI（1 箇所しか使わない抽象を先回りしない）。スコープ外の発見は別 Issue に切り出す。
- 参加者: `newcomer_ux`, `domain_naming`, `data_integrity`, `perf_transparency`, `docs_trace`
- 投稿数: 5
- 更新: 2026-08-21T12:51:35+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

## ラウンド 1

### `domain_naming` — 主張
<sub>2026-08-21T12:47:44+09:00</sub>

## domain_naming: round 1 分析

### 前提の切り分け — フィードバック 1/3/4/5 は「表示文言」の問題であって「ドメイン語彙」の問題ではない

`domain-model.md` §2.1 が定義する語は **コード上の識別子** の正本である。UI 文言（`messages/ja.json` / `messages/en.json`）は表示層の関心事であり、両者は理屈の上では独立に変更できる。ただし DDD の原則に立てば「ユビキタス言語は UI にも浸透しているべき」なので、**コード識別子と表示文言を意図的に分岐させる場合はそのギャップ自体を明示的な決定として残す必要がある**（暗黙の分岐は「開発者は Gem と呼ぶが、ユーザーには別の名前を見せる」という二重語彙を生み、将来の Issue・PR・コードコメントとユーザー向け文言の対応が取れなくなる）。

### 表示名だけ変える案（コード識別子は据え置き）

**変更対象は `messages/ja.json` / `messages/en.json` の文言のみ**。以下は一切変更しない。

- `src/domain/model/gem.ts` の `Gem` / `GemFacet` 型
- `src/domain/model/gem-index.ts` の `GemIndex` / `computeGemIndex` / `gemIndex` / `gemIndexValue` / `gemFacetKey` / `toGemFacetMap` / `sortByGemIndex`
- `Gem.dependentCount` フィールド名
- `sort=gem-index`（`src/domain/model/sort-order.ts` の `ALLOWED_SORT_ORDERS` / `GEM_INDEX_SORT_ORDER`）— これは **URL クエリパラメータのワイヤー値**（`domain-model.md` `SearchQuery` は「URL と 1 対 1 対応」= `NFR-2`）かつ `searchResultCacheKey` の構成要素（`domain-model.md` §4 実例 `search:v2:...:sort=gem-index...`）。表示名だけ変える案ではここを一切触らないため、共有済み URL・ブックマーク・キャッシュキーへの影響がゼロ。
- `docs/03_design/data-model/domain-model.md` / `docs/adr/0009-hidden-gem-score-definition.md` / `docs/project-mission.md` — 更新不要（コード識別子・ドメイン定義そのものは変わらないため）

**コスト**: 低。`messages/*.json` の該当キー（`gemIndexValueLabel` / `gemIndexDependentLabel` / `gemIndexUnavailableHeading` / digest セクションの `heading` / `dependentLabel` / `gemIndexLabel` 等）と、search-panel まわりの説明文（フィードバック 2・6 該当キー）を書き換えるだけで済む。`sp:1`〜`sp:2` 相当。

**リスク**: 「コードでは `Gem` と呼ぶが画面には出さない」という分岐が生まれる。今後 Issue・PR・コミットメッセージで「Gem」と書いても画面のどこにも対応する語が無くなり、新規参加者（開発側）の理解コストが上がる。ただし **この分岐は他のドメイン用語（`RepositoryFullName` → 画面には出ない、`CacheKey` → 画面に出ない等）でも既に許容されている構造** なので、DDD 原則上は許容範囲内。「ユーザー向け説明語彙」と「開発者向けドメイン語彙」を意図的に分離するなら、その旨を `domain-model.md` に 1 行注記するのが望ましい（例: 「§2.1 の用語はコード識別子の正本であり、UI 表示文言は `messages/*.json` が別途持つ」）。

### 語彙ごと変える案（ドメイン識別子から変更）

**変更が波及するファイル**（絶対パス・grep 実測）:

- `src/domain/model/gem.ts`（`Gem` 型・`GemFacet` 型・JSDoc）
- `src/domain/model/gem-index.ts`（`GemIndex` 型・関数群一式）
- `src/domain/model/gem-index.test.ts`
- `src/domain/model/sort-order.ts`（`ALLOWED_SORT_ORDERS` の `'gem-index'` 文字列・`GEM_INDEX_SORT_ORDER`）— **URL ワイヤー値の変更を意味する**。`SearchQuery` は URL と 1 対 1 対応（`NFR-2`）なので `sort=gem-index` を変えると既存の共有 URL・ブックマークが壊れる。後方互換のため旧値のエイリアス受理が必要になり、`CacheKey`（`searchResultCacheKey`）の構成要素も変わるため `CACHE_SCHEMA_VERSION` の bump 要否も検討事項に入る（`domain-model.md` §4 の bump 条件は「値の意味が変わったとき」なので機械的には不要な可能性が高いが、キー文字列自体が変わる影響は要確認）
- `src/domain/model/page-number.ts`（コメントで `gem-index` 順ソートに言及）
- `src/domain/ports/gem-digest-port.ts`
- `src/usecases/get-daily-digest.ts` / `.test.ts`
- `src/usecases/list-gem-facets.ts` / `.test.ts`
- `src/usecases/search-repositories.ts` / `.test.ts`
- `src/infrastructure/feed/digest-rss.ts` / `.test.ts`
- `src/infrastructure/platform/static-gem-digest.ts` / `.test.ts`
- `src/infrastructure/github/github-repository-query.ts`（コメント + `'gem-index'` リテラル比較）
- `src/ui/daily-digest.tsx` / `.test.tsx`
- `src/ui/repository-list.tsx` / `.test.tsx`
- `src/ui/sort-picker.test.tsx`
- `src/composition/container.ts` / `src/composition/rate-limit.ts`（コメント言及・DI 配線）
- `docs/03_design/data-model/domain-model.md` §2.1（用語集）/ §4（`GemIndex` 値オブジェクト定義）/ §6（境界づけられたコンテキスト「Gem Index コンテキスト」）— **全面改訂が必須**（このファイルは SSOT であり「ここに載っていない語をコードの識別子に使わない」規律の対象そのもの）
- `docs/adr/0009-hidden-gem-score-definition.md` — **状態「承認」で確定済みの ADR**。命名変更は ADR の中身を書き換えるのではなく、ADR の慣例上は「新 ADR で amend/supersede」が筋（このリポジトリでは ADR の後日書き換え実績を確認できていないため、単純な文言置換で済ませるか新 ADR を切るかは別途判断が要る）
- `docs/project-mission.md`（ミッション文中で「Gem」を定義済み・KPI 文言に影響）
- `docs/02_requirements/prd.md` §1.4（Hidden Gem 定義）/ `GR-n` 要件群/ `AR-2` 等 — 要件 ID 自体は変えないが本文中の語を全置換
- `README.md`（ADR 一覧の要約文）
- プロダクト名 `gem-hunter`（`package.json` の `name`）— **語彙変更の射程外に置くべき**。プロダクト名まで変える提案は本 Issue のスコープ外

**コスト**: 高。`sp:5` 以上（複数レイヤー・型・テスト・ドキュメント同時改修 + URL 後方互換設計）。

**リスク**:
1. **プロダクト名との断絶**: `gem-hunter` というプロダクト名の中核語が「Gem」である以上、UI 表示語彙だけ「Gem」を廃止すると「プロダクト名は Gem を名乗るのに、アプリ内のどこにも Gem という語が出てこない」という一貫性の欠落が生まれる。これは表示名だけ変える案でも語彙ごと変える案でも共通して発生しうるリスクだが、語彙ごと変える案は **コードベース全体で Gem を追放する** ため、開発者向けドキュメント（`docs/project-mission.md` のミッション文・ADR 0009 のタイトル）とプロダクト名の乖離まで生む。
2. **URL 後方互換の実装コストが必須で発生する**（`sort=gem-index` のワイヤー値変更）。表示名だけ変える案にはこのコストが一切発生しない。
3. **ADR 0009 は Hidden Gem の「定義」を確定させた文書**（状態: 承認）。命名を変えるならこの ADR 自体の扱い（改訂 or 新規制定）を決める必要があり、単なる実装タスクの範囲を超える。

### 被依存数＝実利用の量 / Gem Index＝過小評価度、という定義の擁護（他参加者への予告）

`ADR 0009` §2.1 は 2 軸を明確に役割分担させている（過小評価度＝並び順、健全性＝足切り）。命名変更案を検討する際、**「被依存数」を「人気」「利用者数」のような曖昧語に置き換えると `starCount`（注目度）との対概念性が壊れる**（`domain-model.md` §2.2 が「人気」という語自体を star に対して使うことを明示的に禁じている: 『`stargazers_count` | `starCount` | 「人気」と呼ばない』）。同様に「Gem Index」を「おすすめ度」「注目度」のような語に寄せると、`starCount` が担う「注目度」の意味と衝突し、2 軸分離の設計意図（`ADR 0009` §3.2: 合算しない）が UI 表示の語彙レベルで崩れる。round 2 で newcomer_ux の代案が出たら、この 2 点（① 実利用と注目度の対比が保てるか、② 過小評価度という「差分・ギャップ」の性質が単一の絶対量を示す語に矮小化されていないか）を軸に検証する。

### 結論（round 1 時点の推奨）

**境界線**: フィードバック 1・3・4・5（「Gem って何」「被依存数が分からない」「Gem Index も同様」「Data via Ecosyste.ms って何」）は **表示文言の分かりやすさの問題であり、コード識別子・ドメイン語彙を変える理由にならない**。表示名だけ変える案（`messages/*.json` の書き換え + 初出時の平易な説明・ツールチップ等の追加）で解決すべきで、`domain-model.md` / ADR 0009 / URL ワイヤー値 / 型定義には触れない。語彙ごと変える案を取る根拠（プロダクト名との整合性を優先してでもコード語彙を変える必要がある、等の強い理由）は今回のフィードバックからは見出せない。

### `newcomer_ux` — 主張
<sub>2026-08-21T12:48:08+09:00</sub>

# 初見ユーザー視点レビュー（担当フィードバック ①②③④⑤⑥⑩）

## 総論
このアプリの核心的価値（「被依存数に対して star が不釣り合いに小さいリポジトリを見つける」= ADR 0009）は、
初見画面のどこにも **言葉で** 説明されていない。`home.description`（`messages/ja.json:31`）はテンプレートの
プレースホルダ文言（「キーワードで GitHub のリポジトリを検索します。」）のままで、これは「GitHub 検索の劣化コピー」
にしか見えない。①②③④⑤⑩ は個別の語彙問題に見えるが、根はすべて同じ — **「Gem」という核となる概念が
画面上のどこにも定義されていない** ことに起因する。まずここを直せば、個々の語のリネームだけでは埋まらない
理解可能性のギャップが縮む。

---

## ① 「今日の Gem」の「Gem」が説明なしに登場する
- 該当: `messages/ja.json:59` `home.digest.heading` = "今日の Gem"、`app/[locale]/page.tsx:339-340` の
  `<h1>{title}</h1><p>{description}</p>` はブランド名 "gem-hunter" と汎用検索文言のみで、"Gem" が
  何を指すかを一度も定義しない。
- 10 秒テスト: 初見ユーザーは「Gem」を「宝石アイコン付きの何か」程度にしか認識できず、「なぜこの
  リポジトリが選ばれているのか」の説明変数がゼロ。
- **提案**: 見出し自体は変えずに（"gem-hunter" ブランドと一致させたいので）、`home.description` を
  プレースホルダから **プロダクトの一言価値提案** に差し替える（②と統合対応）。加えて「今日の Gem」の
  直下（`daily-digest.tsx:73` の `<h2>` の直後）に 1 行の説明文を追加する案を出す。
  - 案A: 「注目度のわりに使われている、隠れた良リポジトリ」/ "Underrated repos people actually use"
    - 誤読リスク: 「注目度」が「star」を指すと分からない読者には抽象的なまま。ただし専門用語ゼロ。
  - 案B: 「star の数より使われている実績が多いリポジトリ」/ "Repos used more than their star count suggests"
    - 誤読リスク: 「実績」が具体的に何を指すか（ダウンロード数？ Issue 数？）曖昧になりうる。
  - 推奨は案B（「star」という既知の語をアンカーにして「使われている実績」との対比を明示するほうが、
    「注目度」という抽象語より初見での自己解決率が高い）。

## ② `home.description` がプレースホルダのまま
- 該当: `messages/ja.json:31` / `en.json:31`。両言語とも「キーワードで GitHub のリポジトリを検索します。」
  /"Search GitHub repositories by keyword." — これは Next.js のテンプレ的説明文で、GitHub 公式検索との
  差別化点（ADR 0009 §3.1: 被依存数を分母にした過小評価度ランキング）に一切触れていない。
- **提案**（`<h1>gem-hunter</h1>` 直下の1文を差し替え。実装コストは i18n 文言差し替えのみで軽微）:
  - 案A: 「star 数だけでは見つからない、実際によく使われているリポジトリを探せます。」/
    "Find repos that are actually used more than their star count shows."
    - 誤読リスク: 「実際によく使われている」の根拠（被依存数）が言語化されないため、詳細ページまで
      行かないと納得感が薄い可能性。
  - 案B: 「GitHub 検索 + 「どれだけ使われているか」を加味した並び替えで、隠れた良リポジトリを探せます。」/
    "GitHub search, ranked by how much a repo is actually used — not just its star count."
    - 誤読リスク: 文が長く、検索フォーム直上のワンライナーとしてはやや説明過多（UI 上の視覚ノイズになる）。
  - 推奨は案A。理由: 短く、"star" という既知語をアンカーに使い、「何が独自か」を暗示する。詳細は③④の
    改善と合わせて理解が完結する設計にする（説明文だけで背負わせない）。

## ③④ 「被依存数」「Gem Index」が直感的に分からない
- 該当: `messages/ja.json:49,63` (`gemIndexDependentLabel`/`digest.gemIndexLabel`)、
  `repository-list.tsx:156-163`、`daily-digest.tsx:117-129`。表示は生の数値のみ（例:
  「被依存数 1,234」「Gem Index -3.2」）で、単位や意味の補助テキストが一切ない。
- 「説明文を増やす」より先に **語そのもの** を変える方針で検討する。

### 「被依存数」の代案（日本語 / 英語 対）
| 案 | 日本語 | 英語 | 誤読リスク |
|---|---|---|---|
| A | 依存プロジェクト数 | Depended on by | 主語が曖昧。「このリポジトリ**が**依存しているパッケージ数」（方向が逆）と読める危険が最も高い。英語も "Depended on by N" は文法的に据わりが悪い。 |
| B（推奨） | 利用プロジェクト数 | Used by | 「利用」がダウンロード数・フォーク数と混同されうるが、方向の誤読（③の最大の懸念）は避けられる。英語は既に `en.json:49` の `gemIndexDependentLabel` が "Used by" になっており、日本語側（現状「被依存数」）だけを揃えれば足りる＝実装差分が最小。 |
| C | 採用プロジェクト数 | Adopted by | 「採用」は硬く、就職活動関連の語感を連想させる懸念がある。 |

→ **推奨: 日本語ラベルを「利用プロジェクト数」に統一**（`daily-digest.tsx` の `dependentLabel` と
`repository-list.tsx` の `gemIndexDependentLabel` の両方。現状すでに英語は "Used by" で統一されているのに
日本語だけ「被依存数」という専門語が残っている非対称に気づいた — これは①③④共通の根本原因のひとつ）。

### 「Gem Index」自体の代案 + 表示形式の見直し
語のリネームだけでは解決しない構造的な問題がある: **値が -6.7〜0.0 の負数で、しかも「小さいほど上位」という
直感に反する符号** になっている（ADR 0009 §2.1 `Q-3`）。一般ユーザーは「数値は大きいほど良い」と読む
傾向が強く、「Gem Index -3.2」は「マイナス評価」に見えるリスクが高い。名前だけ変えても符号の問題は残る。

**表示形式の代案（優先度順）**:
1. **生値を見せず、順位・パーセンタイル表現に変える（最推奨）**: 「掘り出し度ランキング 3位」「上位 8%」
   のように、母集団内の相対位置を正の整数・百分率で見せる。ADR 0009 の定義（パーセンタイル順位の差）と
   実装上の親和性も高い（`gem-index.ts` が既にパーセンタイル順位差を算出しているはず）。
   - 誤読リスク: 「母集団」が何か（同じキーワード検索結果内？ エコシステム全体？）を明示しないと
     「何位中の3位か」が不明になる。フッタ注記または `aria-describedby` で 1 行の母集団説明が必要。
2. **バッジ / 段階表現（次善）**: 生値を 3〜5 段階のラベルに変換して表示（例: 「掘り出し度: 高 / 中 / 低」、
   または星アイコン ★★★☆☆）。実装コストは高め（しきい値設計が ADR 0009 §2.3 で Phase 2 未確定のパラメータ
   に依存するため、Phase 1 では時期尚早の可能性がある）。
   - 誤読リスク: 段階数が粗すぎると「高」ばかりに見えて差別化が効かない可能性（しきい値のチューニングが要る）。
3. **生値を出す場合の最低限の緩和策**: 符号を反転させて「小さいほど上位」を「大きいほど上位」に正規化した
   別の表示値を作る（内部の Gem Index 自体は変えず、UI 表示用に `-value` または `100 - percentile` 等へ変換）。
   - 誤読リスク: 内部ロジックとの乖離が発生し、開発者が混乱する / QA コストが増える。あくまで暫定策。

**ラベル名自体の代案**（表示形式を変えても、ラベルは残るため）:
| 案 | 日本語 | 英語 | 誤読リスク |
|---|---|---|---|
| A | 掘り出し度 | Hidden Gem Score | 「度」は一般に高いほど強いという直感があるため、①の符号問題と組み合わさると「マイナスの掘り出し度」が違和感を生む。表示形式改善（順位化）とセットなら解消される。 |
| B（推奨） | 掘り出しランキング / 掘り出し順位 | Underrated Rank | 「ランキング・順位」という語は「小さい数字（1位）が良い」という直感と自然に一致するため、符号の誤読リスクを語のレベルで先に解消できる。表示形式の代案1（順位化）とセットで最も一貫性が高い。 |
| C | Gem Index（現状維持） | Gem Index | プロダクト固有語として押し通す案。ただし初見での意味の自己解決は最も弱く、常に注記が要る。 |

→ **推奨: 表示形式は代案1（順位・パーセンタイル化）+ ラベルは案B（「掘り出し順位」/"Underrated Rank"）**。
語と符号の直感を一致させることが、「説明文を足す」よりも根本的な解決になる。

## ⑤ 「Data via Ecosyste.ms」が何のことか分からない
- 該当: `messages/ja.json:64` `digest.attribution` = "Data via {source}({license})· 生成: {generatedAt} ..."
  実際の描画は `attribution-notice.tsx`（未読だが呼び出し元 `page.tsx:373-377` から `AttributionNotice` に
  `meta` を渡すのみ）で、"Ecosyste.ms" が何のサービスかという説明は UI 上のどこにもない。
- ライセンス表示自体は `D-29` により省略不可（CC BY-SA 4.0 の継承ライセンス要件）だが、**表現は変えられる**
  という前提を踏まえた提案:
  - 案A: 「データ提供: Ecosyste.ms（オープンソースパッケージの利用状況を集計する外部サービス）」/
    "Data via Ecosyste.ms — an open-source package usage tracker (CC BY-SA 4.0)"
    - 誤読リスク: 括弧内の説明が長く、脚注としての視覚的ノイズが増える。
  - 案B: 出典表示自体は現状の短さを維持しつつ、"Ecosyste.ms" をリンクにして公式サイトへ誘導する
    （すでにリンクになっているかは `attribution-notice.tsx` 未確認・要確認）。加えて「被依存数」の
    ラベル説明（③④の改善）の中で「Ecosyste.ms 提供のデータをもとに算出」と 1 度だけ触れる。
  - 推奨は案B寄り: 出典行そのものに説明を詰め込むより、**数値ラベル側（Gem Index / 利用プロジェクト数の
    近く）で情報源を軽く示す**ほうが、ユーザーが疑問を持つ場所（数値を見た瞬間）と説明の位置が一致する。
    出典行は義務表示として簡潔なまま、リンク先（Ecosyste.ms 公式）で詳細を補う。

## ⑥ idle 文言「検索結果 / キーワードを入力して検索してください。」は無い方が自然
- 該当: `messages/ja.json:35-36` `home.idle` = "キーワードを入力して検索してください。"、
  `resultsHeading` = "検索結果"。`page.tsx:416-422` で `<h2 id="results-heading">{resultsHeading}</h2>` は
  常時表示、`page.tsx:442-444` の `SearchStatusText` が idle 時に `idle` 文言をライブリージョンへ出す。
- SP-14（今日の Gem 発見面）導入後、**キーワード未入力時は「今日の Gem」がすでに画面上に存在** する
  （`page.tsx:357-379`、`hasKeyword` が false のときのみ表示）。この状態で「検索結果」見出し＋
  「キーワードを入力して検索してください。」がその下に並ぶと、ユーザーから見て「もう Gem が表示されている
  のに、なぜ『検索してください』と言われるのか」という二重メッセージになり、飼い主のフィードバックが
  指す違和感はここに起因すると考えられる。
- **提案**（a11y の役割は壊さずに文言・表示条件だけ調整する）:
  - 案A: `idle` 文言を削除せず、**未検索時は「検索結果」見出しと idle 文言のセクションごと非表示にする**
    （`hasKeyword` が false のときは `results-heading` の `<h2>` と `#search-status` セクションを
    レンダリングしない）。検索を実行した瞬間に初めて「検索結果」見出しが現れる設計にする。
    - 誤読リスク: 実装上、`aria-live` リージョンを条件付きレンダリングにすると `ui-ux-guidelines.md` §7.2
      が定める「ライブリージョンは初期 DOM に空で常設」という既存規約と衝突する可能性がある
      （`page.tsx:424-435` のコメント参照）。この規約自体の趣旨（スクリーンリーダーへの通知）を壊さない
      よう、視覚的にのみ隠す（`hidden` ではなく空文字列にする等）配慮が必要 — a11y 担当のレンズで別途
      検証してもらうのがよい。
  - 案B: idle 文言を「キーワードを入力して検索してください。」から、より能動的な誘導文へ変更する。
    例:「気になるキーワードで探すこともできます（例: react, cli）」/ "Or search for something specific
    (e.g. react, cli)"。「今日の Gem」が主役で検索は補助手段、という位置づけを文言で明示する。
    - 誤読リスク: 「今日の Gem」と検索が独立機能であることが伝わりにくくなり、「検索は Gem に関連した
      絞り込みなのか？」と誤解される可能性がある（実際は独立: `page.tsx:311-315` のコメント参照）。
  - 推奨は **案A**（表示条件の見直し）。文言をどういじっても「Gem がもう出ているのに検索を促される」
    という構造的な二重感は消えないため、根本原因（表示条件）を直すほうが筋が良い。ただし a11y 規約との
    整合は実装時に個別検証が必要（このレビューでは指摘に留め、断定しない）。

## ⑩ 検索結果一覧に Gem Index の数値がなく不安になる
- 該当: `repository-list.tsx:154-164` — `facet`（Gem Index データ）は `sort=gem-index` のときだけ
  `gemFacets` として渡され、それ以外のソート順（関連度・star数・更新日時）では **Gem Index の値も
  被依存数も一切表示されない**（`gemFacets` が `undefined` のため）。
- 初見ユーザーは「Gem Index 順」以外のソートで検索した場合に Gem Index が見えないことを、
  「取得に失敗している」「バグ」と解釈しやすい（実際は意図的な非表示・`D-L`）。
- **提案**:
  - 案A: 全ソート順で Gem Index データを常時取得・表示する。
    - 誤読リスク: 発生しない代わりに、`page.tsx:301-303` のコメントが明示する「無駄な取得をしない」
      という既存の設計判断（`D-L`）と正面から衝突する。API 呼び出しコスト増（レート制限 §④ `SP-16` の
      `GEM_INDEX_SEARCH_RATE_LIMIT_COST` 増幅の懸念）を再評価する必要があり、実装コストは高い。
  - 案B（推奨）: データを追加取得せず、**「Gem Index 順」以外のソート時は、Gem Index 欄そのものを
    「見えない」のではなく「ここでは並び替えに使っていません」と明示する**軽量な代替。
    例えば `sortLabel` の直下や結果見出し付近に 1 行、「Gem Index で並び替えると、各リポジトリの
    利用実績スコアも表示されます」という誘導文を出す（`sort-options` に Gem Index 順があることの
    発見可能性も同時に上げる副次効果がある）。
    - 誤読リスク: 誘導文が「Gem Index 順にすれば必ず良い結果が出る」という過剰な期待を生む可能性がある
      ため、文言は「表示される情報が変わる」という事実ベースに留める。
  - 補足: この不安は⑨（検索の所要時間の不透明さ）と隣接する問題で、どちらも「今何が起きているか
    説明されない」という同根の症状。②の全体方針（プロダクトの動作原理を一言で見せる）が改善されれば、
    ⑩ の不安も間接的に緩和される可能性が高い。

---

## 横断的な優先度メモ（自分のレンズからの推奨順）
1. **③④ Gem Index の表示形式（生値→順位化）+ ラベル日英統一** — 符号の直感的誤読という実害が最も大きく、
   語のリネームだけでなく表示形式そのものの見直しが必要な唯一の項目。
2. **①② description・「今日の Gem」の説明不足** — 実装コストが最小（文言差し替えのみ）で、他の項目
   （③④⑤⑩）の理解可能性を底上げする波及効果がある。
3. **⑩ 一覧ページの Gem Index 不在**は③④の解決（順位化）とセットで再検討すると、コスト対効果の良い
   軽量案（案B）が取りやすくなる。
4. **⑥ idle 文言**は表示条件の変更（案A）が本筋だが a11y 規約との整合確認が必要なため、他チーム
   （a11y 担当レンズ）の見解を待ちたい。
5. **⑤ Data via Ecosyste.ms** は出典行単体の改修よりも、③④の改修（ラベル近くでの出典の軽い言及）と
   合わせた方が効果的。

### `docs_trace` — 根拠
<sub>2026-08-21T12:48:21+09:00</sub>

# 初見ユーザーフィードバック 10 件の対応箇所洗い出し

## ① Gem という語が分からない

**messages/ja.json**
- line 31: "description": "キーワードで GitHub のリポジトリを検索します。" → Gem の定義が不足
- line 59-60: "digest" -> "heading": "今日の Gem" → 「Gem」が何か説明なし

**prd.md**
- line 78-79: 1.4「Hidden Gem の定義」（正本）
  - 「Gem とは、『実際に使われている度合い（被依存数）』に対して『注目度（star 数）』が不釣り合いに小さいリポジトリである」

**user-story-map.md**
- line 100-110: A-8「きっかけなく出会う」/ US-30〜US-33（S-3 Gem 発見）

**ADR 0009**
- line 25-27: 2.1「Hidden Gem の定義」

---

## ② トップの説明文が初期のまま

**messages/ja.json**
- line 31: home.description = "キーワードで GitHub のリポジトリを検索します。"

**messages/en.json**
- line 31: home.description = "Search GitHub repositories by keyword."

**根拠**:
- prd.md 1.2〜1.4 で Gem Index / 被依存数による過小評価度の概念を説明しているが、UI の description は MVP（検索機能）の初期の説明のまま

---

## ③ 「被依存数」が分からない

**messages/ja.json**
- line 49: "gemIndexDependentLabel": "被依存数" → ラベルのみで説明なし
- line 61: "digest" -> "dependentLabel": "被依存数"

**messages/en.json**
- line 49: "gemIndexDependentLabel": "Used by"
- line 61: "digest" -> "dependentLabel": "Used by"

**prd.md**
- line 128: 2.2「被依存数は GitHub API では取得できない」
- line 80: 1.4「被依存数のパーセンタイル順位」

**ADR 0009**
- line 27: 「実際に使われている度合い（被依存数）」
- line 39: 「被依存数の取得は Ecosyste.ms に委ねる」

---

## ④ 「Gem Index」が分からない

**messages/ja.json**
- line 46: "gem-index": "Gem Index 順" → 「Gem Index」の説明なし
- line 48: "gemIndexValueLabel": "Gem Index"

**messages/en.json**
- line 46: "gem-index": "Gem Index"
- line 48: "gemIndexValueLabel": "Gem Index"

**prd.md**
- line 84-86: 1.4 表 「①過小評価度 | Gem Index = エコシステム内での『被依存数のパーセンタイル順位』−『star のパーセンタイル順位』」

**ADR 0009**
- line 27-34: 2.1「Gem Index」の計算式・役割定義

---

## ⑤ 「Data via Ecosyste.ms」が分からない

**messages/ja.json**
- line 64: "digest" -> "attribution": "Data via {source}({license})· 生成: {generatedAt} · 並び順は日付シードで再算出しています"
  → 「Ecosyste.ms」が何か、なぜこのデータを使うのか説明なし

**messages/en.json**
- line 64: "digest" -> "attribution": "Data via {source} ({license}) · Generated: {generatedAt} · Order is recomputed from the day's seed."

**prd.md**
- line 128: 2.2「被依存数は GitHub API では取得できない」
- line 249: open-questions.md 引用「Ecosyste.ms が提供ありと確認済み」

**ADR 0009**
- line 39: 「被依存数の取得は Ecosyste.ms に委ねる」
- line 109: 「Ecosyste.ms のデータは CC BY-SA 4.0（継承ライセンス）」

**ADR 0014**
- line 152: 5. 号「Ecosyste.ms REST API の rankings フィールドを Gem Index の入力に採用」

---

## ⑥ idle 文言「キーワードを入力して検索してください。」と「検索結果」見出しは不要

**messages/ja.json**
- line 35: home.idle = "キーワードを入力して検索してください。"
- line 36: home.resultsHeading = "検索結果"

**messages/en.json**
- line 35: home.idle = "Enter a keyword to search."
- line 36: home.resultsHeading = "Search results"

**user-story-map.md**
- line 96: US-3「未検索の初期状態で、検索を促す表示を見る」→ AC-8 参照

**prd.md**
- AC-8（受け入れ条件）で idle 表示要件を定義

---

## ⑦ 一覧と詳細で star 数が不一致

**user-story-map.md**
- line 130-131: US-11「検索結果を一覧で見る（各項目にオーナーアイコンとリポジトリ名）」
- line 131-132: US-12「カード上で説明文・主要言語・star 数・最終更新日・topics を見て」
- line 142: US-18「詳細ページでリポジトリ名・オーナーアイコン・言語・Star 数・Watcher 数・Fork 数・Issue 数を見る」
  → 一覧（star）と詳細（star + watcher など）の項目が異なる

**messages/ja.json**
- line 39: home.starCount = "star 数"
- line 73: detail.starCount = "star 数"

**messages/en.json**
- line 39: home.starCount = "stars"
- line 73: detail.starCount = "stars"

**テスト**:
- `/home/user/gem-hunter/src/shared/i18n/format-message.test.ts` など、メッセージが統一されているか確認が必要

---

## ⑧ 詳細で README を読みたい

**user-story-map.md**
- line 136-145: A-4「候補を見極める」/ US-16〜US-18
  → README への言及がない

**prd.md**
- FR-4, AC-5 で表示項目を定義
  → README は未記載

**ADR 一覧**
- README 取得は検討されていない

**open-questions.md**
- README 機能は未決事項として記録されているか確認が必要

---

## ⑨ Gem Index 順の検索が遅い

**prd.md**
- section 4（要件テーブル）で NFR-n（非機能要件）を探す
  → 応答時間・キャッシュ戦略が定義されているか確認

**user-story-map.md**
- line 110: US-34「検索結果を Gem Index（過小評価度）順に並べ替える」→ AR-2 / GR-4 / S-3
- line 160 以降: SP-16 の詳細（操作レビュー手順で「速さ」に関する基準があるか）

**ADR 0014**
- line 50-58: 2.2.2「サーバー側計算に課す CPU 予算」
  - 「`limits.cpu_ms = 50`」
  - 「候補プール件数に比例する」CPU 消費

---

## ⑩ 検索リストに Gem Index の数値がない

**user-story-map.md**
- line 128-134: US-12「カード上で説明文・主要言語・star 数・最終更新日・topics を見て」
  → Gem Index 数値は記載されていない

**user-story-map.md**
- line 107: US-31「なぜその候補が Gem なのか（被依存数と star の乖離）が画面でわかる」
  → S-3（日次ダイジェスト）では表示されるが、検索結果一覧では言及なし

**messages/ja.json**
- line 48: "gemIndexValueLabel": "Gem Index" → ラベルは定義されている
- 但し、一覧画面（検索結果）での表示フィールドが messages に定義されているか確認が必要

**messages/en.json**
- line 48: "gemIndexValueLabel": "Gem Index"

---

## 対応ファイル 総括

### messages (UI 文言)
- `/home/user/gem-hunter/messages/ja.json`: line 31, 35-36, 39, 46, 48-49, 59-64, 73
- `/home/user/gem-hunter/messages/en.json`: line 31, 35-36, 39, 46, 48-49, 59-64, 73

### 要件定義
- `/home/user/gem-hunter/docs/02_requirements/prd.md`:
  - line 78-96: 1.4「Hidden Gem の定義」
  - line 128: 2.2「被依存数・Ecosyste.ms」
  - AC-8, AC-5, FR-4 等受け入れ条件
  - NFR-n（非機能要件・応答時間）

### ユーザーストーリー
- `/home/user/gem-hunter/docs/02_requirements/user-story-map.md`:
  - line 96: US-3（初期状態表示）
  - line 110-111: US-12（一覧表示項目）
  - line 107-110: US-31（日次ダイジェストでの Gem 説明）
  - line 136-145: US-16〜US-18（詳細ページ項目）
  - line 174-186: S-3（Gem 発見機能）

### 建築・設計決定
- `/home/user/gem-hunter/docs/adr/0009-hidden-gem-score-definition.md`:
  - line 25-40: Hidden Gem 定義・Gem Index 計算
  - line 39: Ecosyste.ms 採用

- `/home/user/gem-hunter/docs/adr/0014-zero-query-daily-digest.md`:
  - line 24-36: 日次ダイジェスト実装設計
  - line 50-58: CPU 予算（パフォーマンス）

### 未決事項
- `/home/user/gem-hunter/docs/02_requirements/open-questions.md`:
  - D-28: Ecosyste.ms データ出典表示の運用ルール
  - README 機能が未決事項として記録されているか確認が必要

### テスト
- `/home/user/gem-hunter/src/shared/i18n/format-message.test.ts`：メッセージ統一性確認
- E2E テスト（`/home/user/gem-hunter/e2e/`）: 表示内容の一致性確認が必要

### `perf_transparency` — 主張
<sub>2026-08-21T12:49:31+09:00</sub>

## perf_transparency: ⑨⑩ 分析（コード実読・根拠付き）

### 前提（読んだコードの要点）
- `search-repositories.ts`: `sort=gem-index` のときだけ `GEM_INDEX_FETCH_PER_PAGE=100` × 最大 `GEM_INDEX_FETCH_MAX_PAGES=10`（`API_RESULT_LIMIT=1000` 由来）を **逐次**取得。既に ①1 ページ目の `totalCount` から `maxPages` を実件数まで縮める適応、②`items.length < 100` での自然打ち切り、の 2 つの早期終了が実装済み（PR #293）。
- 各ページ取得は `CachingRepositoryQuery`（`cached-repository-query.ts`）経由。キーは `search:v2:{keyword}:page=N:sort=gem-index:per_page=100`（`cache-key.ts`）。**表示ページ・表示件数（`displayPage`/`displayPerPage`）はこのキーに含まれない** ので、同一キーワード内でページ送り・表示件数変更をしても内部 10 ページ分は再ヒットする。つまり遅いのは「同一キーワード＋gem-index 順の初回（キャッシュ冷えている）検索」に限られる。
- `TTL_SEARCH_SECONDS = 60`（`container.ts`）。60 秒を過ぎると再び冷える。
- `NFR-7`③「GitHub API 呼び出しの直列化（公式が並行実行を非推奨としているため）」がコード内コメントにも明記（`search-repositories.ts:76`）。**並列化は要件で明示的に禁止**されており、提案しない（提案するなら NFR-7 の再合意が要る別提案として切り出す）。

### 1. 実際に短縮できる余地
- **早期打ち切り／適応ページ数**: 既に実装済み。追加でできることは薄い（総件数が 1,000 未満の検索は自動的に速い。遅いのは総件数が多い＝人気キーワードのときだけ、という性質を先に共有しておく）。
- **キャッシュ活用（すぐできる・低リスク）**: 内部の 10 ページ生データは「GitHub の gem-index 用生順序」であり、候補プール突合（並べ替え）は毎回その場で再計算するだけで安価。ボトルネックは往復回数そのもの。ここに手を入れるなら、`gem-index` 内部フェッチ専用に **TTL を検索一般（60 秒）より長く**取る（例: 5 分程度）のが最も費用対効果が高い。gem-index 用の生ページは候補プールとの突合結果ではなく GitHub 側の生順序であり、これは短時間で大きく変わらないため許容できるはず。ただし TTL 変更は `NFR-5` の「具体値は§13未決事項」領域に触れるため、今回は提案に留め実装は別確認とする。
- **並列化**: `NFR-7`③により **不可**（現行要件と矛盾）。検討するなら NFR-7 自体の再合意が要る別トラックの話。
- **取得ページ数の適応（追加案）**: 現行の 10 ページ上限自体を引き下げる（例 5 ページ=500 件）は「速くなるが gem-index 順の網羅性が落ちる」トレードオフ。`GEM_INDEX_FETCH_MAX_PAGES` は飼い主決定②の値なので、変更は仕様解釈の分岐（SD-3 第 2 系統）として要確認。今回のセッションでは変更しない前提で進めるのが安全。
- **まとめ**: 今回すぐ入れられる「実際の高速化」は事実上 **内部ページ専用の TTL 延長**のみ。それ以外（並列化・上限引き下げ）は要件・飼い主決定と衝突するため対象外か別 Issue。

### 2. 待たせる間に何を見せるか（現行構造のままで実現可能）
- 現行 `LoadingIndicator`（`loading-indicator.tsx`）は `sort` に関わらず同じ文言（`messages.common.loading`＝「読み込み中」1 行）。**すぐできる・コスト実質ゼロ**な案:
  - `page.tsx` は `Suspense` を組む前に `sort` を既に知っている（`searchState.sort`）。`sort === 'gem-index'` のときだけ fallback の `label` を差し替え、「Gem Index 順に並べ替え中です（最大1,000件を順番に集計するため、通常の並び順より時間がかかります）」のような**理由入りの文言**を出す。クライアント JS 増加ゼロ（`NFR-3` 適合）。既存の `role="status" aria-live="polite"` 構造もそのまま使える。
  - コスト: 文言追加のみ（i18n メッセージカタログに 1 エントリ追加）。実装難度は最小。
- **段階表示（発展案・コスト明記）**: React Server Component の Suspense は「fallback → 解決後の最終表示」の 1 回遷移が基本で、内部 10 ページの進捗（例: 「3/10 ページ集計中」）をリアルタイム更新するには、`searchByGemIndex` を複数段の `Suspense` 境界に分解する（各境界が前段の Promise 解決を待って次段へ進む「waterfall」構成）必要がある。**クライアント JS は増やさずに実現可能**（React の Streaming SSR の標準機能のみで足りる）だが、`search-repositories.ts` の内部実装を「一括 async 関数」から「段階ごとに Promise を返す」形へ再設計する必要があり、コストは中程度（既存の単体テスト・型も分解が要る）。今回のスプリント内での実装は見送り、次点の改善 Issue として切り出すことを推奨。
- 折衷案として、1 ページ目取得直後（最も速く手に入る情報）に判明する `totalCount` を使い、「◯件を Gem Index 順に集計中…」のように**総数だけ**を出す 1 段構成なら、既存構造への影響を抑えつつ「進行中である」「どれだけの規模の処理か」を伝えられる。ただしこれも `searchByGemIndex` を 2 段の Promise に分ける必要があり、上記「発展案」と同程度のコスト。

### 3. 順序（速さ vs 理由の説明、どちらを先に入れるべきか）
**理由の説明（透明性）を先に入れることを推奨。** 根拠:
- 実際に測って短縮できる余地は「内部 TTL 延長」程度で効果は限定的（初回検索は依然遅い。TTL はキャッシュ済みの 2 回目以降にしか効かない）。
- 一方、理由入りローディング文言は **実装コストがほぼゼロ**（文言 1 本の差し替えのみ、クライアント JS 増加なし、NFR-3 に抵触しない）にもかかわらず、⑨の核心である「不安」を直接解消する。飼い主の 1 次反応（フィードバック文面）も「遅い」より先に「理由が分かるとよい」という不安の言語化になっている。
- 段階表示や TTL 調整のような「本当の高速化」は設計判断（飼い主決定②との整合・NFR-5 未決事項）を伴うため、今回は理由表示だけ即実装し、高速化系は Issue 化して次段に回すのが妥当な切り方。

### 4. ⑩「検索リストに Gem Index の数値がなく不安」の原因切り分け（実コード・実データで確認）
**主因は「本番未反映」ではなく「既定のソート順が gem-index ではないため facet 取得自体が発火していない」こと。**

- `page.tsx:302-303`: `gemFacetsPromise` は **`sort === GEM_INDEX_SORT_ORDER` のときだけ**生成される（`hasKeyword && sort === GEM_INDEX_SORT_ORDER`）。渡されなければ `RepositoryList` は Gem Index 値を一切描画しない（`repository-list.tsx:83-85` の `facets` が `undefined` のまま）。
- `sort-order.ts:9`: `DEFAULT_SORT_ORDER = 'relevance'`。つまり **ユーザーがソートを明示的に「Gem Index 順」へ切り替えない限り**、検索結果一覧には Gem Index 値も被依存数も一切出ない（実装が入っていないのではなく、既定状態では発火しない設計）。飼い主が普段どおり検索窓にキーワードを打って Enter しただけなら、まず見えない。
- 加えて **候補プールの被覆率が低い**: `daily-digest.json` の `candidates` は **294 件**（`toGemFacetMap` の元データ）。GitHub 検索は 1 キーワードで最大 1,000 件相当を返しうるので、たとえ `sort=gem-index` に切り替えても、294 件の候補プールに含まれないリポジトリは「Gem Index 情報なし」の区切り以降（`gemIndexUnavailableHeading`）に回り、値が表示されない。人気キーワードほど候補プール外の結果が多く、体感としては「ほとんど数値が出ない」になりうる。
- 結論: **本番デプロイ未反映を主因と断定する根拠はコード上ない**（実装自体は `sort=gem-index` 選択時に正しく動作する設計になっている）。むしろ①既定ソートが relevance で facet 取得が走らない、②候補プール 294 件の被覆率不足、の **2 つの設計上の理由**で「検索リストに出ない」という体験が生まれている可能性が高い。実際の本番挙動の最終確認（デプロイ反映有無）は URL を直接開いて検証する必要があるが、コード・データからは上記 2 点が優先度の高い仮説。

### `data_integrity` — 主張
<sub>2026-08-21T12:51:08+09:00</sub>

# data_integrity: フィードバック⑦（一覧と詳細でスター数不一致）の分析

## 1. 不一致の原因（コード確認済み）

- **一覧（ダイジェスト）**: `tools/generate_gem_digest.mjs` が手動 / 非定期実行のバッチで
  Ecosyste.ms から取得し `public/data/daily-digest.json` に焼き込む静的スナップショット
  （`static-gem-digest.ts` が `import` で読む）。`generatedAt` は現物で `2026-08-20T16:56:03Z`
  （今日 2026-08-21 時点で 1 日前）。CI 自動実行なし（スクリプト冒頭コメントに明記）ため、
  実運用では **数日〜数週間単位で古くなりうる**。
- **詳細**: `get-repository-detail.ts` → `RepositoryQueryPort.findDetail` = GitHub API を
  `CachingRepositoryQuery` 経由でライブ取得（ADR 0005・TTL 300 秒）。
- したがって一覧と詳細は **設計上そもそも別ソース・別鮮度**（バッチ静的 vs ライブ 300 秒
  キャッシュ）であり、不一致は「バグ」ではなく **アーキテクチャ上の必然**。

## 2.「repository 名の誤解決」は事実誤認（実測で否定）。ただし別の真の欠陥を発見

依頼された前提（`react` → `react/react` は誤りで正しくは `facebook/react`）を実測で検証した結果、
**これは誤りではない**。

- Ecosyste.ms API 実測: `react` パッケージの `repository_url` も `repo_metadata.full_name` も
  両方とも `react/react`（`repo_metadata.stargazers_count: 247323`, `archived: false`）
- GitHub 実測（WebFetch）: `github.com/react/react` は 200 で実在し 247k star（一致）。
  `facebook/react` ではなく `react/react` が現在の正規ロケーション（2026-08 時点で react org へ
  移管済みと見られる）。
- `owner === repo` 形式の候補を機械検出したところ 294 件中 85 件ヒットしたが、サンプル確認した
  `eslint/eslint` `prettier/prettier` `webpack/webpack` `axios/axios` `lodash/lodash` 等は
  すべて実在の正しい自己名リポジトリ、`DefinitelyTyped/DefinitelyTyped` `babel/babel` は
  意図通りのモノレポ集約（複数パッケージが同一リポジトリを指すのは仕様どおり）。
  → **404 を生む欠陥ではない。今スプリントで対応すべき別 Issue も不要。**

### 発見した真の欠陥（未報告・出所の非同期）

`generate_gem_digest.mjs` の `toGem()` は 1 件の Gem を作る際に **2 つの異なる鮮度のフィールドを
無自覚に混在** させている:

```js
const repo = extractGithubFullName(pkg?.repository_url)       // npm registry 由来（比較的新鮮）
const stars = pkg?.repo_metadata?.stargazers_count             // Ecosyste.ms 独自クロール由来
```

`repo_metadata.last_synced_at`（Ecosyste.ms が GitHub をクロールした最終時刻）はパッケージごとに
バラつきが大きく、実測サンプル（候補プールからランダム 20 件）で:

| packageName | full_name | last_synced_at からの経過日数 |
|---|---|---|
| husky | typicode/husky | 0 日 |
| ts-jest | kulshekhar/ts-jest | 1 日 |
| gulp-sass | dlmanning/gulp-sass | 23 日 |
| grunt-contrib-clean | gruntjs/grunt-contrib-clean | **714 日** |
| gulp | gulpjs/gulp | **858 日** |
| node-sass | sass/node-sass | **858 日** |
| postcss | postcss/postcss | **859 日** |
| @babel/cli 等（babel/babel） | babel/babel | **974 日**（≈2.7 年） |

20 件中 6 件（30%）が **700 日超**（1.9〜2.7 年）Ecosyste.ms 側で未更新。つまり「一覧の star が
古い」の主因は **①自分たちのバッチが日次で回っていないこと** だけでなく、**②データ元
（Ecosyste.ms）自体のクロール鮮度が銘柄ごとに最大 2.7 年単位でバラつく** ことにもある。
`generatedAt`（バッチ実行時刻）を「as of」として案内しても、実際の値の鮮度はそれより古い
場合がある、という点は fix 案の精度に関わる注記として残す（今スプリントでの追加対応は不要、
将来 `repo_metadata.last_synced_at` を候補に持たせて個別表示する改善は別 Issue 候補）。

## 3. 4 案の評価

| 案 | NFR-3（トップは client JS 無し） | NFR-5（レート予算） | D-29（Ecosyste.ms 帰属・再配信規律） | ADR 0005（キャッシュ設計） | 総合 |
|---|---|---|---|---|---|
| **(1) 一覧の star をライブ取得に寄せる** | 直接違反はしない（SSR 内で fetch すれば JS 追加は不要）が、ADR 0014 §2.2 の「候補プールは静的 JSON のみ・ゼロクエリでサーバー状態を持たない」設計を破る。detail 用の `RepositoryQueryPort` を digest usecase にも配線する新規結合が要る（`GemDigestPort` と `RepositoryQueryPort` の分離を壊す） | 日次ダイジェストは同一 URL で edge cache されうる設計（ADR 0014 §2.2）だが、`?date=` バリエーションや初回キャッシュミス時に candidates 中 表示件数分（既定 5）の GitHub API 呼び出しが毎回発生しうる。`R-5` の逆算は「1 検索 = 1 API 呼び出し」前提（ADR 0005 追補・`SP-16`）で、ダイジェスト用の呼び出しは検討対象外のため予算の再逆算が要る | 影響なし（star はもともと数値のみで再配信禁止の対象は生テキスト） | `CachingRepositoryQuery` の TTL 300 秒に乗せれば軽減できるが、それでも「候補プールは静的・実行時 API 呼び出しゼロ」という ADR 0014 の根本設計を変える | **却下寄り**: スコープが 1 スプリントに収まらない設計変更（ADR 改訂が要る） |
| **(2) 一覧の表示から star を落とす** | 影響なし | 影響なし（呼び出しが減るだけ） | 影響なし | 影響なし | 実装コストは最小だが、比較検討という製品価値（`Gem Index` と並ぶ判断材料）を一覧から奪う。newcomer_ux 側の要望（#10: 一覧に数値が欲しい）とも逆行 |
| **(3) 鮮度を明示して仕様として説明する（推奨）** | 影響なし（テキスト追加のみ、JS 不要） | 影響なし | **相性が良い**: D-29 が既に要求する帰属表示（`AttributionNotice`）と同じ場所に「{生成日時} 時点のスナップショット」を併記でき、実装済みの `meta.generatedAt`（実測値あり・空でない）をそのまま使える | 影響なし。既存のバッチ/静的配信設計をそのまま維持 | **推奨**: 追加実装は UI 文言 + i18n ラベルのみ。ADR・NFR のいずれにも抵触しない。ただし §2 の注記どおり「生成日時」は必要十分条件ではなく Ecosyste.ms 側鮮度のバラつきまでは説明しきれない（それでも「一覧はスナップショット・詳細はライブ」という設計の説明としては十分） |
| **(4) 詳細側にも同じ出所の値を併記する** | 影響なし | 影響なし（GitHub 呼び出し追加なし） | 影響なし | 影響なし | 詳細ページはダイジェスト経由以外（検索結果経由）でも表示されるため、294 件の候補プールを毎回 detail 側でも読み込んで該当有無を調べる新規結合が必要（YAGNI寄り・detail の責務が `GemDigestPort` に染み出す）。得られる価値はダイジェスト経由の少数ケースのみ。費用対効果が低く**非推奨** |

## 4. 結論

- **推奨は (3)**: `daily-digest.tsx` の star 表示付近（または帰属表示と同じ箇所）に
  `meta.generatedAt` を使い「この一覧の数値は {日付} 時点のものです。最新の値は詳細ページでご確認
  いただけます」を追加する。実装コストは UI 文言 + i18n のみで、A-1〜A-6 相当のリスクも
  ADR/NFR 抵触もない。
- **「repository 名の誤解決」は今スプリント対応不要**（実測で欠陥ではないと確認済み）。ただし
  Ecosyste.ms 自体のクロール鮮度が銘柄ごとに最大 2.7 年ばらつく事実は (3) の文言設計時に
  「バッチ実行日 = 全銘柄の実際のデータ鮮度」ではない点として認識しておくべき（過剰な精度を
  文言で約束しない）。将来的に `repo_metadata.last_synced_at` を候補データに持たせて銘柄ごとの
  鮮度を出す改善は、価値はあるが本スプリントのスコープ外・別 Issue 候補。
