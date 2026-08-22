<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: GitHub Pages 用ランディングページ（site/）を公開前に多角レビューする

- 議題ID: `lp_github_pages_review`
- 論点: ユーザー指示: 『GitHub Pages を利用して本ツールのランディングページを実装・公開する。LP の最新トレンド / UI・UX / ベストプラクティス / マーケティング戦術を詳細にリサーチして設計する。CTA の優先順位は ① 本番ツール ② GitHub リポジトリ。ファーストビューに本ツールのスナップショットを含める。ツールに合わせたデザインにする。実装後に視覚的なものを含めた多角レビューを行いブラッシュアップしてからユーザー確認を求める。』。実装済みの成果物: site/index.html（単一ページ・ページ内 JavaScript ゼロ）、site/assets/styles.css、site/404.html、site/assets/img/*（アプリ実画面のスクリーンショット + OGP 1200x630）、site/assets/fonts/geist-latin.woff2（自前配信・SIL OFL）。公開方式は gh-pages ブランチ（GitHub Actions は本リポジトリで制限中のため CI デプロイは採らない）。公開 URL 予定は https://kai-kou.github.io/gem-hunter/ 。本番ツールは https://gem-hunter.kinamocchi-tech.workers.dev/ja 。ローカル配信中: http://127.0.0.1:8098/ 。レンダリング済みスクリーンショットは スクラッチ領域の lp/ 配下に desktop-light-full.png / desktop-dark-full.png / mobile-light-full.png / fold.png / sec-why.png / sec-how.png / sec-features.png / sec-trust.png / sec-faq.png がある。争点は少なくとも次の 5 つ: A) ファーストビューの説得力（見出し・サブコピー・CTA・スクリーンショットの見せ方が 2026 年の LP トレンドと CVR の定石に照らして妥当か。過剰・不足はどこか） B) アクセシビリティ（WCAG 2.2 AA。ランドマーク・見出し階層・フォーカス可視・ターゲットサイズ 2.5.8・sticky ヘッダーと 2.4.11・コントラスト（ライト/ダーク両方）・装飾画像の alt・details/summary の扱い） C) コピーとマーケティング（開発者向けの誇張しないトーン・信頼の代替（star 0・ユーザーの声なし）・限界の明示・シェアされる 1 行・FAQ の異議処理が足りているか） D) 技術品質（Core Web Vitals・画像戦略・フォント・OGP/canonical の絶対 URL・構造化データの妥当性・GitHub Pages サブパス配信での相対パス事故・404.html・.nojekyll） E) 事実の正確性（実装していない機能を書いていないか。数値・引用・出典の裏が取れているか。ダークモード切替やフィルタ機能など存在しない機能に言及していないか）。
- 参加者: `visual_design`, `a11y_wcag`, `copy_cvr`, `web_quality`, `fact_check`
- 投稿数: 12
- 更新: 2026-08-22T09:45:53+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

## ラウンド 1

### `copy_cvr` — 主張
<sub>2026-08-22T09:24:46+09:00</sub>

## copy_cvr / Round 1 — コピー & コンバージョン観点

前提の再確認: star 0・利用者の声ゼロ。よって **信頼の原資は「第三者の研究データ」「実装の透明性」「制約の先出し」の 3 つだけ**。現状の LP はこの 3 本柱を既に押さえており、土台は good。以下は「その柱を弱めている箇所」と「離脱理由が潰せていない箇所」に絞る。

---

### must（誇張・不整合・数字が意味を成していない）

**M-1. ヒーローの約束と、最初のクリック先の体験がズレている（最大の離脱リスク）**

h1 + リードは「**被依存数を手がかりに GitHub を探す**」と約束するが、サンプルチップ（`react` / `postgres` / `cli` …）を押して着地するのはキーワード検索であり、そこに被依存数は出ない（検索結果のカラムは star / 更新日 / トピック）。FAQ と制約セクションでは正直に「キーワード検索そのものは GitHub の検索結果です」と認めているぶん、**ヒーローだけが過大** になっている。開発者は最初のクリックで「これ普通の GitHub 検索では？」と判断して離脱する。

対応は 2 つ。**両方やるのを推奨**。

(a) リード文を実像に合わせる（`hero-lead` 置き換え案）:

> gem-hunter は、キーワード検索に加えて **被依存数**（そのリポジトリを実際に依存関係へ入れているパッケージの数）が star に見合っていない OSS を毎日 5 件提示する検索ツールです。ブラウザで開くだけ、登録は要りません。

(b) チップ群の先頭に「キーワードなし」の導線を 1 本足す（差別化機能に最初に触れさせる）:

```html
<p class="samples-label" id="samples-label">キーワードなしで開くと「今日の Gem」／例のキーワードはクリックでそのまま検索</p>
<li><a class="chip chip-lead" href="https://gem-hunter.kinamocchi-tech.workers.dev/ja">今日の Gem を見る</a></li>
```

**M-2. `約 560 + 88` が数字として読めない（信頼のための数字が逆効果）**

`facts` の `<b>` に式が入っており、スクリーンショットでも「何の 560 なのか」が視線 1 往復では取れない。`<b>` は 1 つの数、`<span>` に内訳、が鉄則。

- `<b>` → `648 ケース`
- `<span>` → `ユニット・結合 約 560 / E2E 88（`npm run check` で一括実行）`

**M-3. 「約 600 万 / 研究で検出された偽 star の数」は出典より強く言い切っている**

引用元の論文タイトル自体が *Six Million (**Suspected**) Fake Stars* であり、「検出された偽 star」と断定すると、誇張を最も嫌う読者に対して他の数字の信頼まで巻き込んで落とす。

- ラベル → `研究が「偽の疑いあり」と判定した star 数`

同様に右カードの `111,000+` は `そのリポジトリに依存する OSS の数` のままでよいが、**実例のリポジトリ名を出典注ではなくカード内に出す**（検証可能性が跳ね上がる）:

- `<b>25 star</b>` の `<span>` → `debug_inspector の star 数`
- `<b>111,000+</b>` の `<span>` → `debug_inspector に依存する OSS の数`

---

### should（CVR・離脱理由の潰し込み）

**S-1. 同じ遷移先の CTA ラベルが 3 通りある**

ヘッダー `ツールを開く` / ヒーロー・最終 `gem-hunter を開く` / フッター `ツールを開く（日本語）`。同一導線はラベルを固定したほうがスクロール中に「またこれか」ではなく「これが本線だ」と認識される。**`gem-hunter を開く` に統一**（フッターのみ言語併記のため `gem-hunter を開く（日本語）`）。

**S-2. FAQ が「いつ消えるか分からない個人プロジェクト」への不安を潰していない**

star 0 の無料ツールで最大の離脱理由はこれ。かつ **MIT + ソース公開という手持ちのカードで完全に潰せる**（最強のリスクリバーサル）。FAQ に 1 問追加:

> **なぜ無料なのですか？いつまで使えますか？**
> 個人プロジェクトとして無償で運用しています。収益化の予定はなく、広告を入れることもありません。仮に運用を止める場合でも、ソースは MIT ライセンスで GitHub に残るので、自分の環境で動かし続けられます。

**S-3. FAQ に「自分のエコシステムは対象か」が無い**

被依存データが Ecosyste.ms 由来である以上、読者は真っ先に「npm だけ？ Go / Rust / Python は？」を考える。ここが不明だと、自分のスタックが対象外かもしれない不安のまま離脱する。対応言語の実態は product-facts の確認結果に合わせて書く前提で、質問だけ先に確保:

> **対応しているエコシステムは何ですか？**
> （※ 事実確認後に確定。npm / PyPI / crates.io …の実カバレッジを列挙する）

**S-4. FAQ の 1 問目が既出の答えになっている**

`アカウント登録は必要ですか？` はヒーローの保証行（登録不要）で既に答え済み。**1 問目は最大の反論である `GitHub の検索と何が違いますか？` に差し替える**（登録の質問は 3 番目以降へ）。

**S-5. OAuth の権限範囲が LP のどこにも無い**

「ログインは任意」と繰り返しているが、押した先で何が要求されるかが書かれていない。開発者は権限スコープを見て引き返す。`ログインは任意` タイル（`span-3` で余白が余っている）に追記:

> 共有枠は 30 リクエスト / 分。混み合うときだけログインすれば自分の枠で動きます。要求する権限は公開情報の読み取りのみで、リポジトリへの書き込み権限は要求しません。

（※ 実スコープは product-facts の確認に従って表現を確定）

**S-6. 制約リストの 4 番目が「制約」ではない**

`被依存データは Ecosyste.ms（CC BY-SA 4.0）…` はデータ出典であり、フッターとも重複している。**制約セクションから外して 3 項目に絞る**。誠実さは項目数ではなく中身で伝わるので、「不安要素が 4 つもある」という量的な印象だけを減らせる。

**S-7. 「混み合うと待たされます」は起きることを言い切れていない**

実際に起きるのは待機なのか失敗なのかで、ユーザーの心構えが変わる（失敗なのに「待てば通る」と読むと不信につながる）。事実確認後、以下のどちらかに寄せる:

> 混み合うと検索が一時的に失敗することがあります。少し時間をおくか、GitHub でログインすると自分の枠で動きます。

**S-8. Gem Index の説明に具体例が無い**

式 + パーセンタイル + 「0 が最上位」+ 「小さいほど過小評価」を一度に読ませており、ここだけ認知負荷が跳ねる。数式の直後に 1 行足すだけで一気に腑に落ちる:

> 例: 被依存数は上位 1%（0.01）なのに star は上位 40%（0.40）なら、Gem Index は −0.39。この値が小さいものから並べています。

**S-9. ステップ 2 の見出しが受け身**

`「今日の Gem」を眺める` は差別化機能の見出しとしては弱い。→ **`キーワードなしで開いて「今日の Gem」を見る`**（M-1(b) の導線とも一致し、「入力しなくても使える」ことが手順として伝わる）。

**S-10. OGP / シェア文言が機能説明どまり**

`og:description` は現状「何であるか」しか言っておらず、タイムラインで止まらない。研究データと実例の数字を前に出す:

> `star ではなく被依存数から GitHub を探す検索ツール。25 star なのに 11 万パッケージから依存されている OSS を、毎日 5 件。登録不要・無料・MIT。`

**S-11. `facts` の 4 枚が全部ただのテキスト**

`ADR 15 本` `Accessibility 100` は検証可能なのにリンクが無く、「自己申告の数字」の見え方をしている。`ADR 15 本` → `docs/adr/`、`約 560 + 88` → テスト戦略ドキュメントへリンクすると、透明性という柱がそのまま効く。

---

### later

- **L-1. 保証行の項目数がヒーロー（4 個）と最終 CTA（3 個・MIT 欠落）で不一致**。最終 CTA 側にも `MIT ライセンス` を足して揃える。
- **L-2. 「今このリンクを開けば触れるものだけ」の「このリンク」が指示対象不明**（近くにリンクが無い）。→ `いま開いて触れるものだけを載せています。`
- **L-3. ヒーローリードの `——`（全角ダッシュ）2 連は日本語では読点との区別が付きにくい**。M-1(a) の書き換えどおり括弧に置換すると解決する。
- **L-4. Show HN / 英語圏向けの 1 行が LP 上に存在しない**（ツールには `/en` があるが LP は日本語のみ）。英語 LP を作らない判断なら、README 冒頭の 1 行を Show HN 用に整えるのが最小コスト。

---

### 変えないほうがよい（過剰な書き換えの抑制）

1. **最終 CTA の見出し「探しているのは、たぶん star の下にあります。」** — このページで一番いい 1 行。「たぶん」という弱め語が誇張を嫌う読者に効いており、ここに強い動詞を足すと途端に広告臭くなる。触らない。
2. **GitHub ボタンのラベル「GitHub でソースを見る」** — star 0 の状況で `Star してね` 系を書かず、閲覧行動だけを求めているのが正しい。社会的証明の欠如を露出させない賢い処理なので維持。
3. **「健全性スコアは足し込みません」+ ADR 0009 リンク** — 「やらなかったこと」と「その理由」を出すのは、社会的証明の代替として本 LP で最も強い部分。短くしたくなるが、この段落は長いままの価値がある。
4. **「先に言っておく制約」という見出し** — 「制約」「既知の問題」ではなく能動的に先出しする語感が、そのまま誠実さの表明になっている（S-6 は中身の 1 項目を移す提案であって、見出しは変えない）。
5. **「いま動いている機能。／これから作るものではなく〜」** — ロードマップを機能に見せない宣言。個人開発ツールへの最大の不信を先に潰しており、削らない。

---

### ダークパターン / 誇張チェック（結果）

- superlative（最高・唯一・革命的）なし ✓
- 偽の社会的証明（利用者数・ロゴ・レビュー）なし ✓
- 偽の緊急性・カウントダウン・強制モーダルなし ✓
- 「全機能が使えます」は実装と一致（ログインはレート枠のみ）✓
- 誇張リスクとして残るのは **M-1（ヒーローの約束）と M-3（"suspected" の脱落）の 2 点のみ**。この 2 つを直せば、このページは「誇張ゼロ」と言い切れる状態になる。
- 日本語トーン: 不自然な直訳・過剰敬語なし。文体（です・ます）も統一されている ✓

### `visual_design` — 主張
<sub>2026-08-22T09:26:26+09:00</sub>

## visual_design / Round 1

スクリーンショット（fold / desktop light+dark full / mobile / セクション別）を実際に見た上での視覚デザイン指摘。

---

### must

**VD-1 ダークモードで、アプリのスクリーンショット 3 枚がライト版のまま白く浮いている**
`desktop-dark-full.png` を見ると、ヒーローの `.browser` の中身（`shot-search.webp`）が真っ白な塊になり、ページ全体で最も面積の大きい要素が背景（`oklch(0.145)`）と真逆の明度で光っている。bento の `shot-digest.webp` / `shot-mobile.webp` も同様に白パネル。ダークで来た訪問者の視覚的第一印象が「白い矩形が 3 つ貼られたダークページ」になる。
→ ダークテーマで撮り直した 3 枚を用意し、`<picture>` + `<source media="(prefers-color-scheme: dark)">` で出し分ける。撮り直しが今スプリントで無理なら、暫定でも `.browser-body` / `.tile-figure` にダーク時だけ `filter: brightness(.92)` ではなく **明示的なライト背景のマット（余白パディング + 白いカード面）** を敷き、「意図してライトの画面を額装している」と読める形にする（浮きの原因は明度差そのものではなく、額装なしで背景に直付けされていること）。

**VD-2 bento 1 行目「今日の Gem」タイルに、本文と図の間へ約 100px の空洞ができている**
`sec-features.png` の 1 行目は `[今日の Gem (span-2)][スマートフォンでも同じ]`。右のスマホタイルは `img.crop-top { max-height: 420px }` の縦長図で行高を決めており、左の span-2 タイルは `.tile figure { margin-top: auto }` で図が下端に張り付く。結果、左タイルは本文 2 行のあと y≈400〜500 が完全な空白になり、セクションで一番大きいカードだけが「中身が足りていない」ように見える。
→ (a) `crop-top` の `max-height` を 420px → 300px 前後に下げて行高を揃える、(b) span-2 側の図に `flex: 1; object-fit: cover; object-position: top` を与えて余った縦を図で埋める、のいずれか。(b) のほうが「今日の Gem」を主役にする意図と合う。

**VD-3 タイル内スクリーンショットの文字が実効 6〜7px で、読ませる図なのに読めない**
`shot-digest.webp`（1400px 原寸）が span-2 タイル内で幅 660px に縮み、「利用パッケージ数 26,633 / ★111」という **この LP の主張を裏付ける唯一の実データ** が判読不能になっている。モバイル（`mobile-light-full.png`）では幅 350px でさらに潰れ、灰色のノイズにしか見えない。
→ 5 件全部を写した俯瞰画像をやめ、**上位 1〜2 件だけを拡大トリミングした画像** に差し替える。もしくは画像をやめて「利用パッケージ数 26,633 / star 111」を HTML テキストのミニ表で組む（テキストなら縮小に強く、ダーク対応も VD-1 ごと解決する）。

---

### should

**VD-4 ヒーローのスクショだけ左端が約 40px 内側にずれ、縦のグリッドが崩れている**
`fold.png` で h1・リード・CTA・チップスはすべて x≈180 に揃っているのに、`.browser` の左端だけ x≈222 から始まる。`transform: rotateX(3deg)` + `perspective: 1600px` の透視縮小で上部が内側に寄るため。3deg は「意図した傾き」としては弱すぎて、ただ左右の整列が狂って見えるだけになっている。
→ `rotateX` を 0 にして正面に置き、代わりに `--shadow` を一段強めて浮かせる。傾けるなら 6〜8deg + `transform-origin: top center` で明確に演出として立てる。中間の 3deg が一番損。

**VD-5 対比セクションの 2 枚のカードで、数字のベースラインが揃っていない**
`sec-why.png` の左カードは本文 2 行で `stat-row` が y≈506、右カードは 3 行で y≈532。**比較させるための並置** なのに、比べたい数字（約 600 万 / 25 star）が 26px ずれて置かれている。
→ `.compare-card { display: flex; flex-direction: column }` + `.stat-row { margin-top: auto }` で下端揃えにする。

**VD-6 「111,000+」が黒のままで、良い指標と悪い指標の視覚的な差がない**
`約 600 万`（偽 star）と `111,000+`（実依存数）が同じ `--fg` / 同じ 1.5rem。`.is-good` のボーダー色だけが差分で、数字そのものは中立。読者は左右を読み比べないと意味が取れない。
→ `.compare-card.is-good .stat b { color: var(--accent) }`。ボーダーの淡い accent と呼応してカード単位で「こちらが答え」と一瞥で分かる。

**VD-7 `span-3` の「ログインは任意」タイルが、3 列全幅に本文 2 行だけで右 40% が空白**
`sec-features.png` の最終行。他のタイルが密度を持っているぶん、最後だけ「余り物を横に伸ばした」ように見えてセクションの締まりが悪い。
→ span-3 をやめて 1 列に戻し（3 行目が 1 枚だけになるなら 2 行目を 2 列 + 3 行目 1 列などに再構成）、または右側に「未ログイン / ログイン時」の差分を並べた小さな 2 カラムを足して幅を使い切る。

**VD-8 モバイルで CTA ボタン 2 つの幅が不揃いに縦積みされる**
`mobile-light-fold.png` で「gem-hunter を開く」が約 222px、「GitHub でソースを見る」が約 250px。左揃えで幅の違う矩形が 2 つ重なり、ファーストビューの一番目立つ箇所が不揃いに見える。
→ `@media (max-width: 520px) { .hero-actions .btn { width: 100% } }`。タップ面積も広がる。

**VD-9 モバイルで対比セクションの矢印が横向き（→）のまま**
820px 未満では `.compare` が 1 列縦積みになるが、`.compare-arrow` の `→` はそのまま。縦の流れに横向きの矢印が挟まり、方向の記号として機能していない。
→ `@media (max-width: 819px) { .compare-arrow { transform: rotate(90deg) } }`。

**VD-10 `.limits` の破線ボーダーだけが意匠から浮いている（古く見える要素）**
`sec-trust.png`。他のカードは全て `1px solid var(--hairline)` の実線なのに、ここだけ `1px dashed var(--border)`（`oklch(0.6)` で他より濃い）。破線枠 = 注意書き・工事中という 2010 年代のボキャブラリで、「先に言っておく制約」という誠実さの表明を「警告」に見せてしまう。
→ 実線 hairline + `background: color-mix(in oklab, var(--bg-subtle) 60%, var(--bg))` 程度の面の差でトーンを落とす。破線をやめても「別枠」であることは十分伝わる。

**VD-11 `.limits` の箇条書きだけ行長が無制限で、1 行が全角 60 文字近くある**
`sec-trust.png` の 1 項目目が幅 1080px を使い切って折り返している。`.section-head` は 62ch、フッター説明は 44ch、`.source-note` は 78ch と制御されているのに、ここだけノーガード。可読行長の上限を超えて視線の戻りが辛い。
→ `.limits ul { max-width: 76ch }`。

**VD-12 出典注記の長いリンクが「青い帯」になって本文を分断している**
`sec-why.png` 最下部、`『Six Million (Suspected) Fake Stars on GitHub』（ICSE 2026）ほかの調査まとめ` 全体がリンクで、13.5px / line-height 1.75 の中で下線付きの青が行の大半を占め、注記なのに一番強い視覚要素になっている。
→ リンク範囲を書名だけに縮める（`ほかの調査まとめ` は地の文に出す）。加えて `.source-note a { text-decoration-thickness: 1px }` で細める。

**VD-13 `.fact` の 4 枚が「数値カード」の見た目なのに、1 枚目だけプロダクト名で、2 枚目は数式が読めない**
`sec-trust.png`：`Next.js 16 + Workers` / `約 560 + 88` / `Accessibility 100` / `ADR 15 本`。同じ 1.375rem・`tabular-nums` で組まれているので統計の並びに見えるが、意味の粒度が揃っていない。特に `約 560 + 88` は説明を読むまで何の和か分からず、数字を大きく出す意味がない。
→ 4 枚とも単一の数値に揃える（例: `テスト 648 件` + 説明で内訳、`ADR 15 本`、`Accessibility 100`）。技術スタックは数値カードから外し、`.tag-list` 相当の小さなバッジ行に落とす。

**VD-14 ライトモードでヒーローの glow がほぼ視認できず、装飾コストが回収できていない**
`fold.png` の上部に `--glow-a` / `--glow-b` の痕跡がほとんど見えない（`oklch(0.62 0.19 250 / 0.28)` を白地に blur 20px で乗せているため）。モバイル（`mobile-light-fold.png`）では幅が狭く密度が上がるぶん、かろうじて青みが見える。デスクトップでだけ「何もない上部 620px」を確保している状態。
→ ライト時のみ透明度を 0.28 → 0.4 前後に上げ、`blur` を 20px → 60px にして面として効かせる。効かせられないなら削って、その 620px ぶんヒーローを詰める（VD-15 と同時に効く）。

**VD-15 モバイルのファーストビューにプロダクト画面が 1px も入らない**
`mobile-light-fold.png`（390×844 相当）で見えるのはブラウザフレームの上端バーだけ。CTA とスクショの間に `assurance`（2 行に折り返し「MIT ライセンス」が孤立）と `samples`（ラベル + 5 チップで 2 行）が挟まり、合計 180px 以上を消費している。
→ モバイルでは `assurance` を 3 項目に絞って 1 行化し、`samples` をスクショの **下** へ移す。「何のツールか」を絵で見せるのが最短のはずが、テキストの列で押し下げられている。

**VD-16 モバイルでリード文の `——` 挿入句が行頭・行末に落ちて折り返しが破綻している**
`mobile-light-fold.png`：`被依存数` / `—— そのリポジトリを実際に` / `依存関係へ入れているパッケージの数 —— を` と、ダッシュが 3 行に散る。`word-break: auto-phrase` は文節では折れるが、この二重ダッシュの挿入句までは救えない。
→ 挿入句をやめて 2 文に割る（「gem-hunter は star の数ではなく **被依存数** を手がかりに GitHub を探す検索ツールです。被依存数とは、そのリポジトリを実際に依存関係へ入れているパッケージの数です。」）。視覚的な折り返しの問題だが、直し先はコピー側。

**VD-17 `.formula-expr` がモバイルで横スクロールする**
`white-space: nowrap` + `overflow-x: auto`。`Gem Index = 被依存数の順位 − star の順位` は全角混じりで 390px には収まらず、「仕組み」セクションの中核の式が **切れて右にはみ出す**（スクロールバーの存在に気づかないと式の後半が読めない）。
→ モバイルでは `white-space: normal` にして 2 行で折り返す（`=` の前で改行させるなら `<span>` を分けて `display: block`）。式は横スクロールさせるより折り返したほうが読める。

---

### later

**VD-18 セクションの視覚的リズムが 5 回とも同一で単調**
`desktop-light-full.png` を通しで見ると、`kicker → h2 → 説明文 → カードの格子` が 5 セクション連続し、背景も `--bg` / `--bg-subtle` の交互だけ。スクロールの記憶に残る「山」がヒーローと最終 CTA の 2 つしかない。
→ 1 セクションだけ組みを変える（例: 「仕組み」を 3 カラムのカードではなく、番号 + 図の左右交互の縦フローにする）。カードを減らす方向のほうが 2026 年の LP としては新しく見える。

**VD-19 bento のアイコン 2 つが意味を伝えていない**
「キーボードだけで完走できる」の `M12 3v18M4 7h16M6 21h12` は縦棒 + 横棒で、キーボードにもアクセシビリティにも読めない図形になっている。「スマートフォンでも同じ」は角丸長方形だけでホームインジケータ等の手がかりがなく、他の抽象アイコンと区別がつかない。
→ キーボードは 3×2 のキー矩形、スマホは下部にバーを 1 本足す。アイコン全体を Lucide 等の既製セットに寄せてストローク幅・端点処理を統一するのが早い。

**VD-20 FAQ 6 件が完全に同じ高さの行として並び、視覚的な手がかりがない**
閉じた状態では 6 本の同一の帯。どれが自分の疑問かをテキストだけで探すことになる。
→ 最初の 1 件を `open` にして「開くとこうなる」を見せる（回答の存在自体が信頼の材料になる）。

---

### 良い点（3 つだけ）

1. **日本語見出しの折り返しが実際に効いている**。`word-break: auto-phrase` + `text-wrap: balance` で `star は「注目度」であって、/「使われている証拠」ではない。` のように文節で正しく折れており（`sec-why.png`）、日本語 LP で最も崩れやすい箇所が崩れていない。
2. **スクロール連動アニメーションで `opacity` を動かさない判断**（CSS のコメントに理由も残っている）。「見えないまま残る」事故を構造的に潰しつつ、`transform` だけで十分な出現感が出ている。
3. **アプリ本体と同じ oklch トークンを使っている** ので、ヒーローの accent 青とスクショの中の UI の青が完全に一致しており、LP → ツールの遷移に色の断絶がない（`fold.png` で確認できる）。

### `fact_check` — 主張
<sub>2026-08-22T09:28:26+09:00</sub>

## fact_check R1 — LP 主張の裏取り（`site/index.html`）

実装・ドキュメント・**本番稼働中のサイト実機**（`https://gem-hunter.kinamocchi-tech.workers.dev/ja`）で照合した。
判定は ✅ 裏が取れた / ⚠️ 表現が実装とずれている / ❌ 事実と異なる / ❓ 裏が取れない。

---

### 🔴 must-1: ❌ ログイン機能は本番で使えない（LP は 3 箇所で「使える」と書いている）

**該当文言**
- `index.html:379`「ログインは任意 … 未ログインでも全機能が使えます。GitHub でログインしても変わるのは API のレート枠だけで、機能差は作っていません。」
- `index.html:428`「GitHub でログインすると自分の枠を使えます。」
- `index.html:448`（FAQ）「GitHub でログインする導線もありますが、変わるのは API のレート枠だけで…」

**実測（本番）**
```
curl -sS https://gem-hunter.kinamocchi-tech.workers.dev/ja      → 200（「今日の Gem」「言語切替」は描画される）
  → "ログイン" / "login" の文字列は HTML に 0 件（ログイン導線が描画されていない）
curl -sS -o /dev/null -w '%{http_code}' .../api/auth/login       → 404
```

**原因（コード上の裏）**: `src/composition/auth.ts:33` `isAuthConfigured()` が
`oauthCredentialsConfigured() && sessionEncryptionConfigured()` を要求し、
`src/infrastructure/github/oauth.ts:24-26`（`GITHUB_OAUTH_CLIENT_ID` / `_SECRET` / `_CALLBACK_URL`）と
`src/infrastructure/platform/session-cookie.ts:41`（`SESSION_ENCRYPTION_KEY`）が本番未設定。
`src/ui/site-header.tsx:61` は `showAuthLink` が false ならリンク自体を出さない設計なので、
**静かに消える**（`infrastructure-design.md` §8.1 の意図どおりの挙動）。

コード自体は正しく実装されている（`src/composition/container.ts:70-76` `makeTokenProvider` が
`accessToken` があればユーザートークン、無ければ installation token を使う。
`src/ui/login-link.tsx` も表示切替のみで機能差ゼロ）。**壊れているのは LP ではなく本番の env 供給** だが、
**LP を今の本番に対して読むと 3 箇所とも事実と異なる**。

**修正案（どちらかを選ぶ）**
- (A) 本番に OAuth 4 変数を供給してから LP をそのまま出す（推奨。文言修正不要）
- (B) 供給しないなら文言を落とす:
  - タイル見出し「ログインは任意」→ **タイルごと削除**、または「登録もログインも不要」に置換し本文を
    「アカウントを作る導線自体がありません。全機能が最初から使えます。」へ
  - 制約リスト → 「共有の API レート枠で動いています。混み合うと待たされます。」（後半 1 文を削除）
  - FAQ → 「不要です。ログインの仕組み自体を置いていないので、開いた瞬間から全機能が使えます。」

---

### 🔴 must-2: ⚠️「タップ領域は 44px 以上」は主要導線だけの基準（全コントロールではない）

`index.html:344`「タップ領域は 44px 以上、入力欄は 16px 以上で iOS の自動ズームも起きません。」

- 入力欄 16px は ✅（`src/ui/components/input.tsx:9` が `text-base`＝16px。
  `ui-ux-guidelines.md:140` が「全ブレークポイントで縮小しない」を明記）
- 44px は ⚠️。`ui-ux-guidelines.md:146`「**主要導線（検索入力欄・検索ボタン）は** `--size-control-xl`（44px）を使う」、
  同 `:459`「**すべてのコントロールに 44px を要求しない**」「適合目標は AA、2.5.5 は AAA で準拠を謳うものではない」、
  同 `:161` AA 判定は `--size-control-xs`（24px）で満たす、と明示。
  実際 `src/ui/login-link.tsx` / `locale-switcher.tsx` は `size: 'sm'` で 44px 未満。

**修正案**: 「主要導線のタップ領域は 44px、入力欄は 16px 以上で iOS の自動ズームも起きません。」

---

### 🟠 must-3: ❓「共有の API レート枠（30 リクエスト / 分）」— 数値の出所は正しいが本番前提が未確認

`index.html:427`。30 req/分の出所は ✅ `docs/02_requirements/prd.md:122`
「GitHub 検索 API のレート制限 | 認証済み **30 req/分** / 未認証 10 req/分」。

ただし **30 req/分は「GitHub App の installation token で認証できている場合」の値**。
must-1 で OAuth 系 env が本番未設定と判明した以上、**`GITHUB_APP_*` 3 変数
（`src/infrastructure/github/installation-token.ts:35-37`）が供給されているかは外部から判定できない**。
未設定なら同ファイル `:86-92` のとおり `null` を返して **未認証（10 req/分）で動く** ため、LP の数値は 3 倍の誇張になる。

あわせて **数値の主語が 2 つある点も紛らわしい**。実際に「混み合うと待たされる」直接の原因は
`wrangler.jsonc:12`（`ratelimits: { limit: 60, period: 60 }`）＝**同一 IP あたり 60 リクエスト / 分** の
自リクエスト間引き（`src/composition/rate-limit.ts`）であり、30 req/分は上流 GitHub 側の枠。

**アクション**: 本番の `GITHUB_APP_CLIENT_ID` / `_INSTALLATION_ID` / `_PRIVATE_KEY_PKCS8` 供給有無を確認し、
未供給なら「10 リクエスト / 分」に直すか、数値を落として「共有の API レート枠で動いています」に留める。

---

### 🟡 should-1: ⚠️「日次スナップショット」は日次生成が保証されていない

`index.html:415`「「今日の Gem」は日次スナップショットです」/ `:459`（FAQ）「日次で生成したスナップショット」。

- **本番実機の生成時刻表示は `2026/08/21 01:56`**（＝ `public/data/daily-digest.json` の
  `meta.generatedAt: 2026-08-20T16:56:03.289Z`）。本レビュー時点（2026-08-22）で **約 1.5 日前**。
- 生成は cron ではなく **衛生スロットからの自己修復**（`.claude/skills/project-sync/SKILL.md:165-172` が
  `tools/check_digest_freshness.py` を実行し stale なら `--heal`）。しきい値は
  同ツール既定 `--max-age-hours 48`（`tools/check_digest_freshness.py` docstring）。
  つまり **仕様上 2 日古くても正常** であり「日次生成」ではない。
- 一方「**毎日 5 件が入れ替わる**」（`:322` / `:363`）は ✅。日付シード由来の決定論的シャッフル
  （`src/usecases/get-daily-digest.ts`）なので、元データが更新されなくても顔ぶれは毎日変わる。

**修正案**: 「「今日の Gem」は定期的に取り直しているスナップショットです（画面に生成時刻を出しています）。
GitHub の最新値や詳細画面の表示とは差が出ることがあります。」
FAQ 側も「日次で生成した」→「定期的に生成している」。

---

### 🟡 should-2: ⚠️「今日の Gem」の選ばれ方の説明が 1 段抜けている

`index.html:370-374` は見出し「「今日の Gem」の並び順」の下に `Gem Index = 被依存数の順位 − star の順位` だけを置く。

実装（`src/usecases/get-daily-digest.ts` / `ADR 0014:34`）は **3 段階**:
1. 候補プール 294 件を Gem Index 昇順に並べ、**上位 60 件（`GEM_INDEX_SHORTLIST_SIZE`）の shortlist** を作る
2. shortlist を `SHA-256(日付:packageName)` で **決定論的シャッフル** し先頭 5 件を選ぶ
3. 選ばれた 5 件を Gem Index 昇順で並べる

つまり **「並び順」は式どおり ✅ だが、「どの 5 件が出るか」は上位 60 件からの日替わり抽選** であり、
「Gem Index の上位 5 件」ではない。式だけを読んだ読者は後者と誤解する（`:322`「毎日 5 件だけ入れ替えて」も同様）。

**修正案**（見出し下に 1 文追加）: 「この値の上位 60 件を母集団に、日付から決まる並びで毎日 5 件を選び、
選ばれた 5 件をこの値の順に並べています。」

---

### ✅ 裏が取れたもの（そのままで良い）

| LP の主張 | 根拠 |
|---|---|
| 並び替えは 関連度 / star 数 / 更新日時 の 3 種 | `src/domain/model/sort-order.ts:4` `['relevance','stars','updated']` / `messages/ja.json` `sortOptions` |
| 表示件数は 20 / 50 / 100 | `src/domain/model/per-page.ts:4` `ALLOWED_PER_PAGE = [20,50,100]`（既定 20） |
| 「今日の Gem」は 5 件 | `src/composition/container.ts:47` `DAILY_DIGEST_LIMIT = 5`。本番実機でも 5 件 |
| 前回訪問になかったものに「新着」 | `src/ui/seen-digest/`（`computeDigestDiff` + localStorage）。`messages/ja.json` `newBadge: "新着"` |
| 詳細は star / watcher / fork / open issue + README | `messages/ja.json` `detail.{starCount,watcherCount,forkCount,openIssueCount,readme}` |
| ログインで機能差を作っていない（**コード上は**） | `src/ui/login-link.tsx`（表示切替のみ）/ `container.ts:70` `makeTokenProvider`（トークン差し替えのみ）※本番での可否は must-1 |
| 検索条件が URL に載る / 戻ると保持される | `src/ui/url/build-search-url.ts` / `src/ui/back-link.tsx:22`（keyword/page/sort/perPage を保持） |
| 言語切替はリンク遷移で JS 不要・画面右上 | `src/ui/locale-switcher.tsx:44` `next/link` / `src/ui/site-header.tsx:21,59-60`（`justify-between` の右側） |
| Lighthouse Accessibility 100 を「下回ったらリリースしない」 | `tools/run_lighthouse.mjs:52-58` `rounded < 100 → GATE_FAIL`（blocking）。`tools/run_checks.sh:133-147` が実行し、PR 作成前チェックに組み込み済み。`docs/project-mission.md:23` |
| テスト 約 560 + 88 | `it(`/`test(` 実測 **562**（`src/`・`app/`）/ E2E **88**（`e2e/*.spec.ts`）。丸め表記として正確 |
| ADR 15 本 | `docs/adr/0001〜0015` = 15 ファイル |
| Next.js 16 + Workers | `package.json` `next: 16.3.1` / `wrangler.jsonc`（OpenNext + Workers） |
| 偽 star 約 600 万・18,600 リポジトリ | `docs/01_research/market/20260817-github-repo-search-competitive-analysis.md:17`（He et al., ICSE 2026・StarScout・GHArchive 20TB） |
| `debug_inspector` 25 star / 111,000+ 依存 | 同 `:78` 逐語一致 |
| MIT / Ecosyste.ms CC BY-SA 4.0 / Geist SIL OFL | `LICENSE`（MIT）/ `src/ui/attribution-notice.tsx` + `messages/ja.json`（CC BY-SA 4.0 を画面表示）/ `site/assets/fonts/Geist-OFL.txt` |
| LP に JS ゼロ・外部 CDN 依存なし | `site/index.html` の `<script>` は JSON-LD 1 本のみ（実行コードなし）。`site/assets/styles.css` に外部 URL・`@import` ゼロ。フォントは `./assets/fonts/geist-latin.woff2` を自己ホスト。`.reveal` は CSS の `animation-timeline: view()`（`styles.css:1026`）で JS 不要 |
| トラッキングなし | `src/`・`app/`・`public/` に analytics/gtag/plausible/sentry 等の参照ゼロ |
| 検索キーワードをサーバーに保存しない | `wrangler.jsonc` に KV/D1/R2 バインディング **なし**（永続ストアが存在しない）。`observability.logs.invocation_logs: false`（URL を含む自動リクエストログを無効化）。`console.*` はキーワードを出さない 1 箇所のみ（`static-gem-digest.ts:201`）。キャッシュは isolate 内 `Map` + TTL 60 秒（`container.ts:28`）で永続化なし |
| 環境変数はすべて任意・1 つも設定せず検索と詳細が動く | `README.md:25`。`installation-token.ts:86-92` が未設定時 `null` を返し未認証で継続 |
| 本番が実際に開けて検索できる | 実機 `/ja` 200・`/ja?q=react` 200（`7,171,602 件中 20 件を表示`） |
| 存在しない機能に言及していない（テーマ切替 / 言語フィルタ / 期間フィルタ / Gem Index による検索結果の並べ替え） | いずれも LP に記載なし。むしろ `:429` が「Gem Index は「今日の Gem」の並び順にだけ使っています」と正しく限定 ✅ |

---

### 🔵 later（LP の誤りではないが、整合させておきたい）

- **later-1**: `NOTICE` に Ecosyste.ms（CC BY-SA 4.0）と Geist（SIL OFL 1.1）の項目が無い。
  LP フッターと画面内 `AttributionNotice` は両方を明示しているので、リポジトリ側 `NOTICE` を追随させる（別 Issue 可）。
- **later-2**: 旗艦事例の `debug_inspector` は **RubyGems** のパッケージだが、「今日の Gem」の候補プールは
  **npm 単独スコープ**（`ADR 0014:164`「母集団は `registry.rb#top_percentage_for` により npm 単独スコープと確認済み」）。
  LP は「gem-hunter で見つかる」とは書いていないので誤りではないが、読者が探して見つからない可能性がある。
- **later-3**: 「今日の Gem」の **初回訪問時は 5 件すべてに「新着」が付き**「初回として全件を表示しています」の注記が出る
  （`messages/ja.json` `firstVisitNote` / 本番実機でも「新着」5 件）。LP `:363`「前回の訪問になかったものには「新着」が付きます」
  は嘘ではないが、初回の見え方に触れておくと期待とのズレが減る。

### `web_quality` — 主張
<sub>2026-08-22T09:30:44+09:00</sub>

## web_quality / Round 1 — 静的 LP の技術品質（実測ベース）

計測環境: Playwright(Chromium) で `http://127.0.0.1:8098/` を 1280×900 / 390×844 / 320 / 360 / 768 / 1440px、light / dark、`prefers-reduced-motion` の両設定で計測。PerformanceObserver（LCP・layout-shift）、CSSOM 走査による未使用セレクタ検出、`document.fonts` による可変フォント検証、404 ページの実リクエスト追跡を実施。

---

### must

**M-1. `.site-header` の `background` に `color-mix()` フォールバックが無く、非対応ブラウザで sticky ヘッダーが完全透明になる**
`assets/styles.css:205`

```css
background: color-mix(in oklab, var(--bg) 82%, transparent);
```

宣言はこれ 1 本だけで、直前に素の色指定が無い。`color-mix()` 非対応ブラウザはこの宣言を丸ごと捨てるため、背景指定が **一切残らない**。

実測（当該宣言を CSSOM から削除して非対応を再現）:
- 対応時 … `oklab(1 0 0 / 0.82)`
- 非対応時 … **`rgba(0, 0, 0, 0)`（完全透明）**

sticky ヘッダーが透明になると、スクロール中の本文がヘッダー帯の上を素通りして重なり、ブランド名・ナビ・CTA が読めなくなる。対象は Safari 16.1 以下 / Chrome 110 以下 / Firefox 112 以下と、それらを内包する Android WebView。修正は 1 行:

```css
background: var(--bg);                                   /* ← 追加 */
background: color-mix(in oklab, var(--bg) 82%, transparent);
```

**M-2. `hero-in` が `opacity: 0` から始まるため、ヒーローの h1 と主役スクリーンショットが LCP 候補から永久に除外される**
`assets/styles.css:1045-1080`（`.hero > .wrap > *` に `animation: hero-in ... both`、keyframes の `from { opacity: 0 }` は 1072 行）

実測した LCP 候補は **これ 1 件だけ**:

| | 要素 | 面積 | 記録時刻 |
|---|---|---|---|
| 実際に記録された LCP | `.header-nav` 内の `<a>`（「なぜ star では足りないか」等） | **2,916 px²** | 232ms |
| 記録されなかった h1 | `star では埋もれる、…` | 182,213 px²（62 倍） | — |
| 記録されなかったヒーロー画像 | `shot-search.webp` | **660,137 px²（226 倍）** | — |

5 秒待っても候補は増えない。Chromium は「初回描画時に `opacity: 0` だった要素」を LCP から除外し、その後不透明になっても再評価しない仕様のため。結果として:

- **報告される LCP がヘッダーの小さなリンクになり、CWV の実測値が実態を表さない**（Lighthouse でも CrUX でも、ヒーローの描画は測られない）。
- `prefers-reduced-motion: reduce` にすると LCP が **H1（216ms）** に切り替わる。ユーザー設定で計測対象が入れ替わるのは指標として不安定。
- 実ユーザー側の実害も残る。`.shot-stage` は `animation-delay: 0.26s` + `duration 0.5s` なので、**ヒーロー全体が最大 0.76 秒間ゼロ不透明**。回線が細いほど「CSS は来たのに何も見えない」時間が伸びる。

加えてこれは **自リポジトリのルール違反** でもある。`assets/styles.css:1022` に

> 🔴 opacity は動かさない（対応ブラウザで範囲外に留まった要素が「不可視のまま」になる事故を構造的に起こさないため。移動だけに留める）

と明記して `.reveal` ではそれを守っているのに、`hero-in`（1070 行の keyframes）だけが `opacity: 0 → 1` を動かしている。`hero-in` からも `opacity` を落として `translateY` だけにすれば、規律が揃い LCP 除外も同時に解消する。

---

### should

**S-1. `-webkit-backdrop-filter` が無く、M-1 と重なって旧 Safari でヘッダーが「透明かつブラー無し」になる**
`assets/styles.css:206`。CSS 全文を grep して `-webkit-backdrop-filter` の記述はゼロ（実測）。unprefixed `backdrop-filter` は Safari 18 以降のみ。Safari 17 以下は M-1 の透明背景と合わせて **ヘッダーが視覚的に消える**。`-webkit-backdrop-filter: blur(12px);` を 1 行足すだけで、少なくともブラーは効く。

**S-2. README の「相対パス」記述が 404.html と食い違い、ローカル確認手順が壊れている**
`README.md:24-25` は

> **相対パス** で参照する（GitHub Pages のサブパス配信で壊れないため）。OGP と canonical だけは仕様上 **絶対 URL**

と書いているが、`404.html` は 8 / 9 / 16 / 25 行が `/gem-hunter/...` の絶対パス。README がこの例外を書いていない。

実測（README の手順どおり `python3 -m http.server 8098 --directory site` で `/404.html` を開く）:

```
404 http://127.0.0.1:8098/gem-hunter/assets/styles.css
404 http://127.0.0.1:8098/gem-hunter/assets/img/gem.webp
→ .btn-primary の border-radius = 0px（完全に無スタイル）
```

**絶対パスにした判断そのものは妥当**（後述 OK-6）。問題は ① README にその例外が書かれていない ② ローカルでは 404 ページの見た目を検証できないのに、その注記が無いこと。README の「設計上の約束」に 404.html を例外として明記し、「ローカル確認」節に「404.html はサブパス前提のため localhost では無スタイルになる」と 1 行足したい。

より堅くするなら、404.html は使用するスタイルが 20 行程度しかないので **CSS を `<style>` で内包し、`gem.webp` を落とす** とパス依存がゼロになる。リポジトリ名変更・独自ドメイン移行でも壊れなくなる（そのときは `.nojekyll` と 404.html だけを触れば済む）。

**S-3. `404.html` に `<h1>` が無い**
実測: `h1` 要素 0 個 / `h2` 1 個（`404.html:22` の「このページは見つかりませんでした。」）。`.final-cta h2` のスタイルを流用したかったのだと思うが、単独ページの主見出しは `h1` にすべき。`.final-cta h1, .final-cta h2 { … }` に広げるか、404 用に 1 セレクタ足す。

**S-4. 死にセレクタ `.sr-only`**
`assets/styles.css:185-194`。CSSOM 全 147 ルールを DOM 照合した結果、`index.html` / `404.html` の **どちらからも参照されていない唯一のセレクタ**（他は全件一致。CSS は全体としてかなり無駄がない）。削除するか、`.assurance li::before` の `✓` に読み上げ用テキストを付ける等で実際に使う。

---

### later

**L-1. `will-change: transform` が 12 要素に常時付いている**（`assets/styles.css:1031`）。実測で `will-change: transform` の要素は 12 個（`.reveal` 全件）。scroll-driven animation は実行中に自前で合成レイヤーを確保するので `will-change` は不要で、常時指定はモバイルの GPU メモリを無駄に占有する。削除推奨。

**L-2. `srcset` 不在**。`shot-search.webp` は 1600px 固定配信で、1280px ビューポートでの実描画は 1021px、390px ビューポートでも 1600px のまま届く（DPR1 なら 2.6 倍のピクセル）。モバイル総転送は実測 141KB と十分軽いので急ぎではないが、`srcset`（800w を追加）+ `sizes` で 40KB 前後は削れる。

**L-3. `twitter:image` / `og:image:type` / `theme-color` が無い**。`twitter:image` は `og:image` にフォールバックするので実害は小さい。`theme-color` はライト/ダーク 2 本（`media="(prefers-color-scheme: dark)"`）を入れると、モバイルのアドレスバー色が本文と揃う。

**L-4. JSON-LD に `WebPage` ノードと `offers` が無い**。`SoftwareApplication` が `@graph` 内の `WebSite` と `@id` で接続されておらず、LP 自身を表す `WebPage` ノードも無い。また「無料」を本文で謳っているので `offers: { "@type": "Offer", "price": "0", "priceCurrency": "USD" }` は **事実に即した追記** として入れられる（`aggregateRating` は入れない — OK-4 参照）。

**L-5. `site/README.md` が公開ツリーに含まれる**。`gh-pages` ルートへ `site/` の中身をそのまま置く方式なので、`https://kai-kou.github.io/gem-hunter/README.md` として素の Markdown が公開される（`.nojekyll` があるので raw のまま配信）。実害はないが、公開物に含めない選択肢もある。

**L-6. インラインスタイル 3 箇所**（`index.html:260` h3 の font-size、`544` brand の margin-bottom、`548` footer p の color/max-width）。CSS に寄せたい。

---

### 問題なしと確認できた項目

- **OK-1 CLS = 0.0000**。全画像に `width`/`height` があり（`shot-search` 1600×1025 / `shot-digest` 1400×766 / `shot-mobile` 640×1280 / `gem` 640×640 / `logo` 24×24、すべて実ファイルの実寸と一致）、layout-shift エントリは 1 件も発生しない。`.crop-top` の `max-height: 420px` + `object-fit: cover` も内在アスペクト比が先に確定するのでシフトを起こしていない。
- **OK-2 横スクロール発生なし**。320 / 360 / 768 / 1280 / 1440px のすべてで `scrollWidth === innerWidth`、ビューポート右端をはみ出す要素ゼロ。`body { overflow-x: hidden }` があっても html 側が `visible` なのでビューポートへ伝播し、新しいスクロールコンテナを作らない — sticky ヘッダーはスクロール後も実測で `top: 0` に貼り付いている。
- **OK-3 ネットワークが健全**。リクエスト 7 件・非圧縮合計 243KB。GitHub Pages の gzip 後は HTML 7.4KB / CSS 5.3KB（実測 `gzip -9`）で、ミニファイの必要性は低い。**外部ドメインへのリクエストはゼロ**（フォントも自前配信）、コンソールエラー・pageerror もゼロ。155KB の `ogp.png` はページから一切読まれていない。
- **OK-4 JSON-LD が正直**。妥当な JSON としてパースでき、`aggregateRating` も `reviewCount` も **書いていない**（実在しない評価を捏造していない — LP でいちばん壊れやすい箇所が正しく回避されている）。`applicationCategory: "DeveloperApplication"`、`license` の SPDX URL、`SoftwareApplication.url` が LP ではなく本番アプリを指す点もすべて正しい。
- **OK-5 絶対 URL とフォント**。canonical / `og:url` / `og:image` はすべて `https://kai-kou.github.io/gem-hunter/…` の絶対 URL で、`og:image` の実ファイルは宣言どおり 1200×630。フォントは `preload`（`crossorigin` 付き・stylesheet より前）+ `font-display: swap` + `unicode-range` で latin に限定。**可変フォントであることも実測確認**（HVAR/MVAR/STAT を保持、`font-weight: 400` と `700` の描画幅が 730.9px / 772.9px と実際に異なる）ので、`font-weight: 400 700` の宣言は正しく、太字が合成（fake bold）になっていない。
- **OK-6 GitHub Pages サブパス配信で壊れるパスが無い**。`index.html` は全参照が `./assets/…` の相対パスで `/gem-hunter/` 配下に正しく解決する。`404.html` を絶対パス（`/gem-hunter/…`）にした判断は **正しい** — Pages のカスタム 404 は任意の階層のリクエストに対して返るため、相対パスでは深い階層で確実に壊れる。`.nojekyll` も 0 バイトで存在（`_` 始まりのパスは現状無いが、置いておくのが正しい）。ページ内アンカー（`#why` `#how` `#features` `#trust` `#faq` `#top` `#main`）は全件解決、重複 id なし、HTML のタグ対応も破綻なし（`</a\n>` のような改行入り終了タグは仕様上妥当）。
- **OK-7 モーション周りの設計**。`@supports (animation-timeline: view())` でガードされ、`.reveal` は `opacity` を動かさず `translateY` のみ — 非対応ブラウザ（Safari / Firefox）で要素が不可視のまま残る事故は構造的に起きない。`prefers-reduced-motion: reduce` では `animation-timeline: none !important` と `scroll-behavior: auto !important` まで打ち消しており、`html { scroll-behavior: smooth }` も無効化される。`.browser` の `rotateX(3deg)` も reduce で解除。**M-2 は、この正しい設計が `hero-in` にだけ適用されていない、という一点の問題**。
- **OK-8 外部リンク**。外部リンク 23 本すべて `target="_blank"` を持たないため `rel="noopener"` は不要（付けても無害だが必須ではない）。タブジャックの経路は無い。

### `a11y_wcag` — 主張
<sub>2026-08-22T09:33:13+09:00</sub>

## a11y_wcag / Round 1 — WCAG 2.2 AA 実測レビュー

**実測環境**: Chromium（Playwright）+ `@axe-core/playwright`。`http://127.0.0.1:8098/` を
ライト/ダーク × 1280 / 390 / 320px（= 1280@400% ズーム相当）の 6 通りで検査。
`details` は全開状態にしてから走査。コントラストは oklch トークンから
`tools/check_contrast.py` の変換ロジックで算出（18 ペア × 2 テーマ）。

**axe 結果**: desktop（light / dark）＝ **violations 0**。390px / 320px で `scrollable-region-focusable` が 1 件のみ。
以下はその 1 件＋精読・手動実測で追加検出したものです。

---

### must（AA 不適合として修正が必要）

**M-1. `.formula-expr` が「キーボードで操作できないスクロール領域」になる — SC 2.1.1 Keyboard（A）**

`styles.css` の `.formula-expr` は `white-space: nowrap` + `overflow-x: auto`。
実測（`scrollWidth` / `clientWidth`）:

| viewport | scrollWidth | clientWidth | はみ出し |
|---|---|---|---|
| 320px | 371 | 238 | 133px |
| 390px | 371 | 308 | 63px |
| 1280px | — | — | なし |

**1280px では再現せず、狭幅・400% ズーム時にだけ発生する**（＝ SC 1.4.10 が要求する検証条件そのもの）。
`tabindex` が無いため Chromium ではキーボードで横スクロールできず「Gem Index = 被依存数の順位 − star の順位」の
右側が読めません。axe も `serious` で 4 構成すべてで検出。

推奨修正（上が本命）:
- 狭幅で `white-space: normal`（折り返し）にしてスクロールコンテナ自体を作らない。
  数式が短いので `Gem Index =` の後で折り返しても意味は壊れません。SC 1.4.10 的にも最善。
- 折り返しを避けたいなら `tabindex="0"` + `role="group"` + `aria-label="Gem Index の計算式"` を付与する
  （axe のこのルールが求める形。ただし「横スクロールが必要」状態自体は残る）。

**M-2. 英語の句に `lang="en"` が無い — SC 3.1.2 Language of Parts（AA）**

`<html lang="ja">` 配下で、フッター `<nav aria-label="プロダクト">` の
`<a href=".../en">Open the tool (English)</a>` が `lang=ja` のまま（実測で確認）。
これは固有名詞でも技術用語でもない **英文の句** なので 3.1.2 の除外に当たらず、日本語音声エンジンが英語を読み上げます。

```html
<a href="https://gem-hunter.kinamocchi-tech.workers.dev/en" lang="en">Open the tool (English)</a>
```

同じ扱いを検討すべき箇所（こちらは論文タイトル＝固有名詞寄りで **should** 相当）:
`#why` の `『Six Million (Suspected) Fake Stars on GitHub』` を `<span lang="en">…</span>` で囲う。

> 逆に `Ecosyste.ms` / `WCAG 2.2 AA` / `Next.js 16 + Workers` / chip の `rollup plugin` は
> 固有名詞・技術用語なので **付けなくてよい**（付けると冗長）。

---

### should（AA 解釈上グレー、または AA 未満だが実害が明確）

**S-1. 900px 未満でページ内ナビが完全消滅し、代替が無い — SC 1.4.10 Reflow（AA）**

`.header-nav { display: none }` → `@media (min-width: 900px) { display: flex }`。
実測で **390px / 320px とも可視ナビリンク 0 件**、ハンバーガー等の代替導線もなし。
フッターに `#features` / `#faq` はありますが、**`#why` / `#how` / `#trust` の 3 つは狭幅で到達手段が消えます**。

1.4.10 は「情報 **または機能** の損失なく提示できること」を求めており、
ワイド幅にだけ存在する機能が 320px で消えるのは典型的な指摘対象です
（Understanding 1.4.10 は「メニューボタンの背後に隠す」ことを許容していますが、本 LP は隠す先がありません）。
一方で各セクション自体はスクロールで到達できるため「情報の損失」ではない、という反論も成り立ちます。
そのため **must ではなく should** と判定しました。

最小コストの案: 狭幅では `.header-nav` を消さず、横スクロールする chip 列にする
（既に `.chips` のスタイル資産があり、min-height 36px でターゲットサイズも満たす）。
それも避けたいなら、フッター `<nav aria-label="プロダクト">` に `#why` / `#how` / `#trust` を足すだけでも
「到達手段ゼロ」は解消します。

**S-2. `body { font-size: 16px }` — ユーザーのブラウザ既定フォントサイズを無視する**

実測: `document.documentElement.style.fontSize = '32px'`（＝ ユーザーが既定を 200% に設定した状態）にしても
`getComputedStyle(document.body).fontSize` は **16px のまま**、`.site-header` も 60px 固定のまま変化なし。
ヘッダー・ボタン・chip・`--header-h` など主要寸法が px 固定なので、**ブラウザのフォントサイズ設定が一切効きません**。

SC 1.4.4 Resize Text はブラウザズーム（実測でクリップ無しを確認済み）で満たせるため
**厳密な AA 不適合ではありません** が、拡大表示を「ズーム」ではなく「既定フォントサイズ」で行う
ロービジョンユーザーには何も届きません。`body { font-size: 1rem }` と、
少なくとも `--header-h` / `.btn` / `.chip` の `min-height` を `rem` 化することを推奨します。

**S-3. chip / カードの枠線が 1.28〜1.45:1 — SC 1.4.11 Non-text Contrast（AA・解釈グレー）**

実測コントラスト:

| ペア | light | dark | しきい値 |
|---|---|---|---|
| `--hairline` / `--bg` | **1.39** | **1.45** | 3.0 |
| `--hairline` / `--bg-subtle` | **1.28** | **1.31** | 3.0 |
| chip 面 `--bg-subtle` / ページ `--bg` | 1.09 | 1.10 | — |

**対象を切り分けます**（過剰指摘を避けるため）:
- 🔸 **`.chip`（= リンク）は should**。スクリーンショットで目視確認したところピル形状は「見えなくはない」ものの、
  境界の唯一の手がかりが 1.39:1 の枠と 1.09:1 の面で、**それが操作可能であることを示す唯一の視覚情報** です。
  ただし直前の `<p id="samples-label">キーワードの例（クリックでそのまま検索）</p>` が
  `aria-labelledby` でリストに結び付いており、テキストで操作性を説明できているため must には下げませんでした。
  `--border`（light 3.95:1 / dark 4.08:1）に差し替えれば 3:1 を満たします。
- ⚪️ **`.tile` / `.compare-card` / `.steps li` / `.fact` / `.faq details` の枠は指摘しません**。
  非インタラクティブなカードの装飾枠であり、見出し・余白でグルーピングは伝わるため
  1.4.11 の「理解に必要な視覚情報」に当たらないと判断しました（誤検知防止のため明記します）。

**S-4. 404.html に `<h1>` が無い — SC 1.3.1（A）/ 2.4.6（AA）の境界**

`site/404.html` の最上位見出しが `<h2>このページは見つかりませんでした。</h2>`。
axe も `page-has-heading-one`（moderate）で検出。ページの主見出しがレベル 2 から始まるのは
見出し構造の意味的な誤りです。`.final-cta h2` のスタイルはそのままに `<h1>` へ変更するのが最小修正
（`.final-cta h1 { font-size: clamp(1.6rem, 3.6vw, 2.5rem); margin-top: 12px }` を足すか、セレクタを `h1, h2` に拡張）。
`index.html` 側の見出し階層は h1 が 1 つ・レベル飛ばし無しで問題ありません。

---

### later（実害小・改善提案）

- **L-1. `.url-pill` が読み上げノイズ**: `aria-hidden` 無しで
  `gem-hunter.kinamocchi-tech.workers.dev/ja?q=react` を読み上げます。
  ブラウザモックの装飾（`.dots` は既に `aria-hidden="true"`）なので、`.url-pill` にも同様に付けるのが一貫します。
  320px では `clientWidth` 116px に対し中身 399px で ellipsis 省略されており、視覚的にも情報を担っていません。
- **L-2. `.assurance li::before { content: '✓' }`**: Chromium は擬似要素のテキストをアクセシビリティツリーに出すため、
  「チェックマーク 登録不要」のように読まれます。`background-image` か SVG に置き換えると静かになります。
  （`.steps li::before` の数字も `<ol>` の項番と二重ですが、視覚的な番号として妥当なので許容範囲です。）
- **L-3. `html { scroll-behavior: smooth }` と Tab 移動**: 実測で 400ms 待ちではフォーカス要素が画面外に見え、
  1200ms 待って初めて可視になりました（＝ スムーススクロールが 1 秒級）。連続 Tab で「いまどこにフォーカスがあるか」を
  見失いやすくなります。SC 2.2.2 の対象（5 秒超）ではないので不適合ではありませんが、
  `:focus-visible` を伴う移動だけ `scroll-behavior: auto` にする手はあります。
- **L-4. `.tile-figure img.crop-top`**: `max-height: 420px` + `object-fit: cover` で下部が切れる一方、
  alt は切れた部分（「リポジトリカードが縦に積み重なっている」）まで説明しています。
  alt を見えている範囲に合わせるか、切り抜きをやめるか。
- **L-5. `.chip` の `aria-label`**: 現状でも `<ul aria-labelledby="samples-label">` があるため
  **SC 2.4.4 は満たしていると判断しました**（リストの名前が文脈として programmatically determinable）。
  ただしリンクリスト読み上げモードでは「react」単体で読まれるので、
  `aria-label="react で検索"` にするとより堅牢です。

---

### 問題なしと確認した項目（過剰指摘の抑制のため明記）

1. **SC 2.4.11 Focus Not Obscured（AA）— 適合**。`scroll-margin-top: calc(var(--header-h) + 16px)` を
   `a` / `button` / `summary` / `section[id]` に当てている設計が実際に効いています。
   Tab で全 30 個のフォーカス可能要素を巡回し、スクロール収束後に
   **sticky ヘッダー（h=60, z=50）と重なった要素 0 件・画面外 0 件**（reduced-motion 両方で確認）。
2. **SC 2.5.8 Target Size (Minimum)（AA）— 適合**。非インライン要素の実測値は
   `.btn` 44px / `.faq summary` 64px / `.header-nav a` 45px / `.chip` 36px / `.btn-sm` 40px / `.footer-grid a` 32px で
   すべて 24×24 以上。24px 未満だったのは本文中の `Ecosyste.ms`（90×19）等のみで、これは 2.5.8 の
   **インライン例外**（文中に埋め込まれ行の高さに制約される）に該当し違反ではありません。
3. **コントラスト — 18 ペア中 17 ペアが AA 適合（light / dark 両方）**。
   `fg-muted/bg` 6.00 / 7.63、`fg-muted/bg-subtle` 5.50 / 6.91、`accent/bg` 8.36 / 7.95、
   `accent-fg/accent`（主ボタン）8.36 / 8.26、`.eyebrow` 7.23 / 6.04、`border/bg` 3.95 / 4.08。
   フォーカスリングは `ring/bg` 8.36 / 7.95 で SC 1.4.11 の 3:1 を大きく超過。
   半透明ヘッダー（`color-mix` 82% + `backdrop-filter`）にヒーローのグローが透ける最悪ケースも計算し、
   `fg-muted` 5.65（light）/ 7.28（dark）で **適合** でした。唯一の NG は上記 S-3 の hairline のみです。
4. **`prefers-reduced-motion: reduce` — 適合**。`animation-timeline: none !important` と
   `scroll-behavior: auto !important` まで無効化しており、実測で `scrollBehavior=auto` を確認。
   `.reveal` を **opacity ではなく transform だけで動かす** 判断（CSS のコメントに明記）は正しく、
   最下部までスクロール後に全 12 個の `.reveal` が `transform` 恒等行列（ずれ残留ゼロ）でした。
   「範囲外に留まった要素が不可視のまま残る」事故を構造的に排除できています。
5. **`details` / `summary` — 適合**。`display: flex` を当てていますが Chromium のアクセシビリティツリー上の
   role は `DisclosureTriangle` のまま、**Enter / Space の両方でトグル** することを実測で確認。
   開閉状態を示すシェブロンも `--fg-muted` で 6.00:1（light）/ 7.63:1（dark）＝ 3:1 超。
6. **スキップリンク — 適合**。最初の Tab 停止点で `top=8, left=8, 153×52` に可視化され、
   `z-index: 100 > ヘッダーの 50` で隠れません。Enter で `<main id="main" tabindex="-1">` に
   フォーカスが移り、**次の Tab がヘッダーナビを飛ばしてヒーロー CTA に入る** ことまで確認しました。
7. **代替テキスト — 適合**。装飾画像（`logo.webp` / `gem.webp`）は `alt=""`、全 `svg` は `aria-hidden="true"`、
   スクリーンショット 3 点は内容を具体的に説明する alt。`.compare-arrow`（→）も `aria-hidden`。
8. **ランドマーク／見出し** — `header` / `main` / `footer` + `nav` 3 つすべてに `aria-label`。
   `index.html` の見出しは h1 が 1 つ、h1→h2→h3 でレベル飛ばしなし（22 見出しを列挙して確認）。

---

### 自動検出の限界（この結果で保証できないこと）

- **axe が拾えるのは WCAG 要件の一部**（一般に 3〜4 割）。上記 must/should の M-2・S-1・S-2・S-4 は
  axe では検出されず、精読と手動実測で見つけたものです。
- **Chromium のみで検証**。Safari / Firefox は未検証で、特に ① `summary { display: flex }` の
  ディスクロージャ挙動、② Firefox がスクロール可能領域に自動でキーボードフォーカスを与える挙動（M-1 の再現性）は
  ブラウザ差があります。M-1 は「Firefox なら操作できる可能性がある」が、Chromium で操作できない時点で修正対象です。
- **スクリーンリーダーの実読み上げ（NVDA / VoiceOver）は未検証**。L-1 / L-2 は
  アクセシビリティツリー上の露出から推定したもので、SR 側の抑制設定で聞こえ方は変わります。
- **コントラストはトークン値からの算出** であり、レンダリング後のピクセル実測ではありません。
  グラデーショングロー・`backdrop-filter` が絡む箇所は最悪ケースを合成計算しましたが（結果は適合）、
  実ピクセルサンプリングではない点は留保します。
- **404.html はローカル配信ではスタイル未適用**（`/gem-hunter/assets/styles.css` の絶対パスがローカルの
  ルート配信と噛み合わないため）。S-4 は DOM 構造と共有スタイルシートの読解に基づく指摘で、
  GitHub Pages 上（`/gem-hunter/` 配下）では正しく解決するはずです。

## ラウンド 2

### `copy_cvr` — 反論
<sub>2026-08-22T09:38:32+09:00</sub>

## copy_cvr / Round 2 — rebuttal & concession

総括を先に。**fact_check の must-1 は全面的に受け入れる。そのうえで「(B) 文言を落とす」は誠実さのための妥協ではなく、CVR 的にも現状コピーより上だと主張する。** 理由は単純で、いまの LP は **持っていない摩擦（ログイン）をわざわざ読者に紹介してから否定している** から。コピーの原則として、存在しない障害物は登場させないほうが速い。「ログインは任意」というタイル見出しは、読み手の頭に一瞬「ログインがあるのか」を置いてから消しにいく、いちばん損な形になっている。

---

## 確定案 1: ログイン記述（fact_check must-1 への回答）

### 判断: **(B) を採る。ただし「削除」ではなく「置換」**。`site/` の公開を env 供給タスクの完了待ちにしない

(A)（本番に OAuth 4 変数を供給してから出す）を選ぶと、LP の公開が **別レーンの作業に依存** する。いま最悪なのは「ボタンが存在しない画面に対して LP が 3 箇所でログインを語っている」状態なので、**まず現状に合わせて正しくし、env が供給された時点で 1 ブロックだけ足す** 運用にする。

さらに重要な指摘: **いま LP はログインに 3 箇所で言及しており、これは「将来 3 箇所を直し忘れる」設計** でもある。今後は **言及先を FAQ の 1 問だけに集約** し、機能タイルと制約リストからは概念ごと消す（フラグが立ったときの編集が 1 箇所で済む）。

### 文言（そのまま差し替え可）

**(1) `features` の `span-3` タイル — 見出しごと置換**

これは visual_design VD-7（span-3 の右 40% が空白）への回答も兼ねる。ログインという「無い話」を削った空きに、**fact_check が実測で裏を取った 3 つの「渡さなくていい」** を入れると、幅を使い切りつつ開発者向けの信頼材料になる。

> **見出し**: 渡すものが何もない
>
> **本文**: アカウント登録もログインもありません。広告も、アクセス解析のトラッキングも入れていません。検索したキーワードをサーバーに保存する仕組みも持っていません（データベースを 1 つも接続していないので、保存しようがない、が正確です）。
>
> **`tag-list`**: `登録なし` / `トラッキングなし` / `保存なし`

括弧内は fact_check の「KV/D1/R2 バインディングなし・`invocation_logs: false`」という実測に基づく。**「しません」ではなく「できない構造です」と言えるのが強く**、社会的証明ゼロの LP で使える数少ない硬い材料。

**(2) `limits`（制約リスト）の 2 項目目** → 確定案 2 に統合（後述）。ログインへの言及は削除。

**(3) FAQ 1 問目**（S-4 で順序を入れ替えたあとの位置）

> **アカウント登録は必要ですか？**
> 不要です。ログインの仕組み自体を置いていないので、開いた瞬間から全機能が使えます。

⚠️ **注記**: この文はフラグが立った瞬間に偽になる。将来 OAuth を有効化するときは **この 1 問だけを**「任意でログインできます。変わるのは API のレート枠だけで、機能差はありません」に戻せばよい（他 2 箇所には二度と書かない）。

---

## 確定案 2: レート枠の数値（fact_check must-3 への回答）

### 判断: **LP から「30 リクエスト / 分」という数字を落とす**

コピー観点の理由は 2 つ。

1. **その数字は誰の意思決定も変えない**。「30 req/分 なら使う、10 req/分 なら使わない」と判断する読者は存在しない。読者が必要なのは「混むと失敗することがある」という **心構え** だけ。得るものがゼロで、外れたときの信頼喪失だけがある数字は、コピーとして純損失。
2. **主語が 2 つある**（上流 GitHub の枠 30 と、自前の同一 IP 60/分の間引き）。fact_check の指摘どおり、体感の直接原因は後者。**読者に上流の内部事情を説明する必要はない**。

### 文言（制約リストの 2 項目目・確定）

> 混み合う時間帯は、検索が一時的に失敗することがあります。API の枠を利用者全員で共有しているためです。少し時間をおいて試してください。

（数字を出したい場合の代案 — 採らなくてよい）: どうしても具体値を置くなら、**env に依存せずリポジトリで確定している自前の値**（`wrangler.jsonc` の同一 IP 60 リクエスト / 分）だけを書く。上流 GitHub 側の枠は env 次第で 3 倍ぶれるので **絶対に書かない**。私の推奨は数字なし。

---

## 確定案 3: タイル内スクリーンショット（visual_design VD-3 との折り合い）

### 判断: **VD-3 の後者（HTML テキスト化）を採る。「見せてから語る」は撤回しない — 適用範囲を切り分ける**

原則を 1 行に落とす。

> **主張が「見た目」なら画像で、主張が「数字」ならテキストで証明する。**

- `shot-digest.webp`（今日の Gem）の主張は **数字**（利用パッケージ数 26,633 に対し star 111）。→ **テキストに置換**。読めない数字は証明ではなくノイズで、いま最も証明力の高いデータが最も読めない形で置かれている。テキストなら ① 幅に強い ② ダークで浮かない（VD-1 が同時に解消）③ **リポジトリ名をリンクにできる＝読者がその場で検証できる** ④ ページ本文に数字が入るので引用・シェア・検索に乗る。画像には ③④ が原理的にできない。
- `shot-mobile.webp`（スマートフォンでも同じ）の主張は **見た目**（同じ画面が縦に積み替わる）。→ **画像のまま残す**。ここをテキストにしたら主張そのものが消える。
- `shot-search.webp`（ヒーロー）は **「これは実在する動くプロダクトだ」** という主張。→ **画像のまま、位置も変えない**。ユーザー指示の「ファーストビューにスナップショットを含める」もここで満たされている。

つまり **「見せてから語る」はファーストビューで完結** しており、機能タイルで実在性を再証明する必要はない。タイルの仕事は主張の裏取りなので、証明力の高い媒体（テキスト）に替えるのは方針転換ではなく方針の徹底。

### 置換案（`今日の Gem` タイルの `figure` を置き換え）

> 実際に「今日の Gem」に出たリポジトリ:
>
> | リポジトリ | 利用パッケージ数 | star |
> |---|---:|---:|
> | `rollup-plugin-peer-deps-external` | 26,633 | 111 |
>
> ※ リポジトリ名は GitHub へのリンクにする。2 行に増やしてもよいが、3 行以上にすると「一覧」に見えてタイルの主役が数字からリストに移るので 1〜2 行に留める。

visual_design が VD-2 で指摘した「span-2 タイル下部の約 100px の空洞」も、図の代わりに高さの読める表が入ることで自然に埋まる（`margin-top: auto` の張り付きも不要になる）。

---

## 自分の Round 1 からの撤回・修正（concession）

- ❌ **S-5「OAuth の権限範囲をタイルに書く」を全面撤回**。fact_check must-1 のとおり本番に導線が無く、**存在しない画面のスコープを説明するのは端的に虚偽**。確定案 1 の置換文がこの枠を引き継ぐ。
- 🔧 **S-7 を確定案 2 に差し替え**。R1 では「失敗するのか待たされるのか」の精度だけを問題にしたが、fact_check の実測を受けて **数値ごと落とす** に強化する。
- 🔧 **M-1(b)（ヒーローのチップ先頭に「今日の Gem を見る」を足す）を visual_design VD-15 と統合**。VD-15 の「モバイルのファーストビューにプロダクト画面が 1px も入らない」は正しく、私の提案は素直に足すとさらに押し下げる。**修正案: リード用チップ「今日の Gem を見る」1 個だけをスクリーンショットの上に残し、キーワード 5 個はスクリーンショットの下へ移す**。差別化機能への入口は保ちつつ、モバイルで約 90px を返せる。保証行もモバイルは 3 項目に絞る（VD-15 に同意）。
- 🔧 **fact_check should-1（日次でない）を受けたコピー修正**。ただし fact_check の「定期的に取り直しているスナップショットです」に **そのままは同意しない** — この言い方だと「毎日変わる」という **再訪動機（LP で唯一の習慣化フック）** まで一緒に消える。fact_check 自身が「毎日 5 件が入れ替わるのは ✅（日付シードの決定論的シャッフル）」と裏を取っているので、**2 つの主張を分離** して書く:
  > 出てくる 5 件は毎日入れ替わります。元になる被依存データは定期的に取り直しているスナップショットなので、GitHub の最新値や詳細画面の表示とは差が出ることがあります（画面に生成時刻を出しています）。
- 🔧 **fact_check should-2（上位 60 件からの日替わり選出）に同意**。ただし「抽選」「ランダム」という語は使わない（無料ツールで抽選語彙を出すとガチャ的な演出に見え、このページのトーンから浮く）。確定文:
  > この値が小さい上位 60 件を母集団に、日付から決まる順序で毎日 5 件を選び、その 5 件をこの値の順に並べています。同じ日なら、誰が見ても同じ 5 件です。

  最後の 1 文は事実（決定論的シャッフル）であると同時に、**「自分だけに出された演出ではない」＝ パーソナライズ的な操作をしていない** ことの表明になり、確定案 1 の「渡すものが何もない」と響き合う。
- 🔧 **fact_check must-2（44px は主要導線のみ）に全面同意**。→ 「主要導線のタップ領域は 44px、入力欄は 16px 以上で iOS の自動ズームも起きません。」

---

## 名指しの反論（コピー・CVR 観点で採るべきでないもの）

**R-1. a11y_wcag S-1 の最小コスト案「狭幅では `.header-nav` を横スクロールする chip 列にする」に反対。**
到達手段ゼロを解消すべき、という **問題提起には同意** する。しかし解決手段としての chip 列は、visual_design VD-15（モバイルのファーストビューにプロダクト画面が 1px も入らない）と真正面から衝突する。ヘッダー直下に横スクロールのナビ列を足せば、**ただでさえテキストで押し下げられている CTA とスクリーンショットがさらに下がる** — LP のモバイル CVR にとって最も高くつく変更になる。しかも LP のセクションナビは、縦スクロールで全部通過する 1 ページ構成では **元々ほとんど使われない**（複数画面のアプリのナビとは役割が違う）。
→ **a11y_wcag 自身が併記している後者の案（フッター `nav` に `#why` / `#how` / `#trust` を足す）を採るべき**。到達手段ゼロは解消され、ファーストビューは 1px も動かない。

**R-2. visual_design VD-18「カードを減らす方向のほうが 2026 年の LP としては新しく見える」に部分反対。**
「5 セクション連続で同じ組みは単調」という観察には同意する。ただし **機能セクションのカードは装飾ではなく、離脱理由を 1 枚ずつ潰す実務パーツ**（モバイル対応・キーボード操作・i18n・渡すものがない）。新しく見せるためにカードを減らすのは、**測れる CVR を測れない印象と交換** する取引になる。
→ 単調さは **コピー側で解く**。いま 5 セクションの見出しが「課題 → 仕組み → できること → つくり → FAQ」と全部同じ抽象度の名詞で並んでいるのが単調さの正体で、1 つを断定文の見出しに変えるだけでリズムは付く（例: `つくり` → `隠していないこと`）。**カードの枚数は減らさない**。

**R-3. web_quality L-4 の「JSON-LD に `offers: price 0` を足す」は later で構わないが、優先度は最下位。**
「無料」は本文・保証行・FAQ の 3 箇所で既に言い切っており、構造化データに価格を足しても **読者の意思決定には 1 ミリも触れない**。加えて、このページは「収益化しない個人プロジェクト」という立て付けなので、価格・通貨という商取引の語彙を（不可視とはいえ）持ち込むのは方向としては逆。やるなら害はないが、**確定案 1〜3 が終わるまで着手しない**。

**R-4. a11y_wcag L-2「`.assurance li::before` の `✓` を画像に置き換える」に条件付きで反対。**
読み上げノイズは理解するが、`✓ 登録不要 ✓ 無料 ✓ 広告・トラッキングなし ✓ MIT ライセンス` の **チェック記号は保証行の視覚的な型そのもの**（読者はこの並びを見た瞬間に「前提条件の列だ」と認識する）。画像化して読み上げが静かになる代わりに、`background-image` はダークテーマで色を合わせる手当てが要る（VD-1 と同じ轍）。
→ 記号は CSS の `content` のまま残し、`.assurance li::before { content: '✓'; }` に **`content: '✓' / ''`**（代替テキスト空指定）を使えば、見た目を変えずに読み上げだけ落とせる。置換より先にこちらを試すべき。

---

## 他レンズへの支持（コピー観点から見て CVR 直撃と判断するもの）

- **web_quality M-2（`hero-in` の `opacity: 0` で LCP が除外される）は、指標の問題である以上に CVR の問題**。ヒーロー全体が最大 0.76 秒ゼロ不透明ということは、**このページで最も練られた 1 行（h1）と唯一の実画面が、回線の細い読者には「白紙」として届く時間がある** ということ。ファーストビューのコピーは表示されて初めてコピーなので、`translateY` のみに落とす修正を **確定案 1〜3 と同格の優先度** で扱ってほしい。
- **visual_design VD-17 / a11y_wcag M-1（`.formula-expr` がモバイルで切れる・キーボードで読めない）に同意**。`Gem Index = 被依存数の順位 − star の順位` は **このプロダクトの主張そのもの** で、ここが右に切れて読めないのは a11y 不適合であると同時に、差別化の説明が最後まで届かないという CVR の損失。折り返し（`white-space: normal`）を採るべきで、`tabindex` を付けて横スクロールを残す案は「読める」にならないので支持しない。
- **visual_design VD-20（FAQ の 1 件目を `open` にする）に同意。ただし開く対象は入れ替え後の 1 問目**。私の R1 S-4 のとおり 1 問目を `GitHub の検索と何が違いますか？` に差し替えたうえで、**それを開いた状態にする**。最大の反論への回答が最初から見えているのが最も効く。`アカウント登録は必要ですか？` を開いて見せても、保証行で既出の情報が二度出るだけになる。
- **visual_design VD-6（`111,000+` を accent 色に）に同意**。左右のカードで数字の色が同じだと、**どちらが良い指標なのかを読者が文章から再構成しないと分からない**。色 1 つで「こちらが答え」を渡せるのは安い。

### `visual_design` — 反論
<sub>2026-08-22T09:38:52+09:00</sub>

## visual_design / Round 2 — 反論と譲歩

他 4 名の R1 を読了。結論から書くと、**視覚レンズ側から降ろす指摘のほうが、足す指摘より多い**（VD-13 / VD-16 / VD-17 を他者案に統合して取り下げ、VD-14 を later へ降格、VD-7 を条件付きに変更）。以下、争点ごとに。

---

## 1. web_quality M-2（`hero-in` の `opacity: 0` が LCP を殺す）— **全面的に譲歩する。視覚的損失はゼロどころか、いま損をしている**

**両立するか？ → 対立しない。`opacity` は落とすべきで、視覚レンズからも落とすべきと言える。**

理由を 3 点。

**(a) 静止画の完成度には一切影響しない。** 私が R1 で評価した `fold.png` は全要素が着地済みの状態であり、そこに `opacity` フェードの寄与は 1px も無い。失われるのは「読み込み後 0.5 秒の演出」だけで、ページの見た目そのものは変わらない。

**(b) むしろ現状のほうが視覚的に悪い。** web_quality の実測どおり `.shot-stage` は `animation-delay: 0.26s` + `duration 0.5s` で **最大 0.76 秒間ゼロ不透明**。CSS が届いているのにヒーローの主役（660,137px² の画像）が真っ白、という状態を回線が細いほど長く見せている。これは「演出」ではなく「白画面の延長」で、ファーストビューの説得力（争点 A）を直接毀損している。**フェードは、体感を良くするどころか悪くしている側**。

**(c) 動きの読みやすさは `translateY` だけで足りる。** stagger（0.02 → 0.26s の 6 段）が残る限り、順に立ち上がる印象は保たれる。14px の移動は「フェード無しだと硬い」と感じる距離ではない（硬く見えるのは 30px 超あたりから）。

具体案（`styles.css:1070-1079` の keyframes 置換）:

```css
@keyframes hero-in {
  from { transform: translateY(14px); }
  to   { transform: none; }
}
```

`from` から `opacity` を消すだけ。`.reveal` 側（`styles.css:1022` のコメントで「opacity は動かさない」と自ら宣言している規律）と揃い、web_quality の指摘どおり **自リポジトリのルール違反も同時に解消** する。

**「h1 と画像だけ除外して他はフェード残す」案は採らない。** 上下に隣接する要素の一部だけがフェードし、一部がスライドのみ、という混在は 0.5 秒間はっきり見える不整合になる。規律としても「一部だけ例外」は次の改修で必ず崩れる。**全部から `opacity` を外す** のが視覚・規律・計測の 3 方向で正解。

**追加の視覚的要求を 1 つ。** `opacity` を外すと `.shot-stage` は初回描画時から不透明で見えるので、**VD-4（`rotateX(3deg)` で左端が 40px 内側にずれる）の見え方が今より目立つようになる**。VD-4 は「あとで直す装飾」ではなく、LCP 要素の初期描画位置がグリッドから外れている問題に格上げされる。`rotateX` の除去は同じコミットに入れてほしい。

---

## 2. VD-1（ダークで白いスクショが浮く）— **fact_check の事実を受けて、対処案を差し替える。severity は must で維持**

**譲歩**: 「ダークテーマで撮り直した 3 枚を `<picture>` で出し分ける」という R1 の第一案は **撤回する**。アプリ本体にテーマ切替が無く（`app/globals.css` に `.dark` トークンはあるが、それを適用する導線が本番に存在しない）、ダーク版スクショは **Playwright で `.dark` を強制注入すれば「撮れて」しまうが、それは実ユーザーが到達できない画面の捏造** になる。fact_check が must-1 で「本番で使えないログインを LP が 3 箇所で使えると書いている」を問題にしている以上、**LP 側が存在しない UI 状態を絵として出すのは同じ罪** であり、視覚レンズから見ても採ってはいけない。R1 のこの一文は私の落ち度。

**維持**: それでも severity は **must のまま**。`desktop-dark-full.png` で、ページ最大面積の要素 3 つが背景と真逆の明度で光っている状態は、ダークで訪れた開発者が受ける第一印象を決めてしまう。事実として直せないのではなく、**額装で解決できる** のに未処理、という状態。

**差し替え後の対処案（推奨 = 案 A）**:

**案 A: ブラウザモック全体をライト固定にして「ライト UI の画面写真を意図して額装している」形にする。**
いま最も悪いのは、`.browser-bar`（`--bg-subtle` = ダークでは `oklch(0.205)`）という **暗いブラウザ枠が、白い本文を包んでいる** 点。枠とコンテンツの明度が逆転しているため「白い穴」に見える。枠ごとライトにすれば、暗いページの上に置かれた 1 枚のライトなカードとして読める。

```css
@media (prefers-color-scheme: dark) {
  .browser, .browser-bar { background: oklch(0.97 0 0); border-color: oklch(0.87 0 0); }
  .url-pill { background: oklch(1 0 0); color: oklch(0.5 0 0); border-color: oklch(0.87 0 0); }
  .dots span { background: oklch(0.87 0 0); }
  .browser { box-shadow: 0 0 0 1px oklch(1 0 0 / 0.12), 0 24px 60px oklch(0 0 0 / 0.6); }
  .tile-figure { background: oklch(0.97 0 0); border-color: oklch(0.8 0 0); padding: 8px; }
}
```

ポイントは `box-shadow` の 1 本目（1px の明るいリング）。ダーク背景と白い面の間に境界を 1 本入れるだけで「浮いている」が「置かれている」に変わる。**この 5 宣言でダークの最大の視覚欠陥は解消する**（撮り直し不要・事実の捏造なし・コスト最小）。

**案 B: LP 自体をライト固定にする（`color-scheme: light` + ダークブロック削除）。**
アプリがライトのみである以上、LP がダークで、クリックした先が突然ライト、という遷移は体験としても割れている。案 B なら VD-1 は根本から消え、a11y_wcag が実測した 18 ペア × 2 テーマの半分が検証不要になり、レンダリング経路も 1 本になる。

**推奨は A。** 開発者向け LP でダーク非対応は 2026 年には「手を抜いた」と読まれる側のリスクが大きく、ダークで見ている読者にライトを強制する明滅のほうが体感の損失が大きい。ただし「今スプリントで判断を 1 つに絞って risk を最大量減らす」方針なら B も筋は通る。**A / B のどちらでも、案 A の CSS を書いた時点で B へは 5 行削除で移れる** ので、A を先に入れて損はしない。

---

## 3. VD-3（タイル内スクショが 6〜7px で読めない）vs copy_cvr「見せてから語る」— **対立していない。両取りが正解で、私の第 2 案が悪かった**

**譲歩**: R1 で並記した「画像をやめて HTML のミニ表に置き換える」案は **主案から降ろす**。copy_cvr の M-1 は「差別化機能（今日の Gem）に最初に触れさせろ」であり、その説得力の源泉は **実物の画面** である。ユーザー指示にも「本ツールのスナップショットを含める」がある。画面を消してテキスト表にするのは、読みやすさのために証拠を捨てる交換で、割に合わない。

**維持 + 統合案（これを推す）**: **画像は「上位 1〜2 件だけを拡大トリミングした版」に差し替え、数字だけをタイル本文の HTML テキストにも二重化する。**

- 画像（証拠）: 5 件俯瞰 → 1〜2 件の拡大。同じ 660px 幅でも文字が実効 14px 相当になり、`利用パッケージ数 26,633 / ★111` が実際に読める。順位番号（`1.`）は残るので、リスト由来であることも伝わる。
- テキスト（可読性）: タイル本文に `rollup-plugin-peer-deps-external — 利用パッケージ数 26,633 / star 111` の 1 行を置く。テキストなら **どの幅でも読め、選択・検索でき、ダークでも壊れない**（VD-1 の影響を受けない）。copy_cvr M-2 / M-3 の「数字は 1 つの数として読ませる」原則とも揃う。

つまり **優先すべきは「見せる」で、「読ませる」は画像の外に逃がす**。どちらかを選ぶ問題ではなかった。

なお fact_check should-2（実際は上位 60 件からの日替わり抽選であって「Gem Index 上位 5 件」ではない）を踏まえると、拡大トリミングで 1〜2 位を大きく見せることが「これが常に 1 位」という誤読を強めない書き方が要る。タイル本文のテキストは `ある日の 1 位` のように日付性を残す表現にしておくのが安全。

---

## 4. 他者指摘のうち、過剰・不要と考えるもの（名指し）

**4-1. a11y_wcag S-1 の主案「狭幅では `.header-nav` を横スクロールする chip 列にする」— 反対。副案（フッター nav に `#why` / `#how` / `#trust` を足す）を採るべき。**
理由は視覚側に 3 つ。① 60px の sticky ヘッダーに chip 列を入れると、ブランド + 横スクロール列 + `ツールを開く` ボタンが 390px を奪い合い、**最優先 CTA が縮むか消える**（争点 A の直接の後退）。② 私は VD-17 / a11y M-1 で「狭幅の横スクロール領域を 1 つ消そう」と言っているのに、**より目立つ位置に新しい横スクロール領域を作る** のは自己矛盾。③ モバイルのファーストビューは VD-15 で「既に詰まりすぎ」と指摘した箇所で、そこに常時可視のスクロール手掛かりを足すと fold がさらに埋まる。**フッター nav に 3 リンク足すだけで「到達手段ゼロ」は消える**（a11y 自身が最小コスト案として書いている）。指摘の妥当性ではなく、提示された 2 案のうち高コスト側を否定している。

**4-2. a11y_wcag S-2 の後半「`--header-h` / `.btn` / `.chip` の `min-height` を rem 化」— 今スプリントでは反対。前半（`font-size` の rem 化）は賛成。**
`font-size` の px → rem は機械的で副作用が無く、やるべき（`body` だけでなく 13/13.5/14/15/17px も一緒に、でないと本文だけ伸びて部品が伸びない不整合が出る）。一方 `min-height` と `--header-h` の rem 化は話が別で、**既定フォント 200% 環境では sticky ヘッダーが 120px になり、844px の縦の 14% を常時占有する**。しかもそれは a11y_wcag 自身が「適合」と実測証明した SC 2.4.11（`scroll-margin-top: calc(var(--header-h) + 16px)` が効いている・全 30 要素で重なりゼロ）と、web_quality が実測した CLS 0.0000 / 320px 横スクロールなしの前提を、**両方まとめて再検証が必要な状態に戻す**。S-2 は a11y 自身が「厳密な AA 不適合ではない」と書いている項目であり、確定している適合を崩してまで今やる順番ではない。`font-size` だけ入れて、寸法の rem 化は別 Issue に切る。

**4-3. a11y_wcag L-2「`.assurance li::before` の `✓` を `background-image` / SVG に置き換える」— 置き換えは不要。1 宣言で解決する。**
SVG 化すると accent 色がライト `oklch(0.42 0.14 250)` / ダーク `oklch(0.72 0.16 250)` で変わるため、data-URI を 2 本持つか `mask-image` + `background-color` に組み替えることになり、**読み上げノイズ 1 語のために配色の連動を 1 箇所壊す**。代替テキスト構文を使えば見た目を一切変えずに黙らせられる:

```css
.assurance li::before { content: '✓' / ''; }
```

非対応ブラウザでは現状（`✓` を読み上げる）に戻るだけで後退が無い、純粋な上乗せ。L-2 は「対処不要」ではなく「提案されている対処法が重い」。

**4-4. web_quality S-4「死にセレクタ `.sr-only` を削除」— 削除に反対（残す or 使う）。**
`.sr-only` は 10 宣言・gzip で数十バイトの標準ユーティリティで、削除の実利がほぼ無い。一方、この議論で出ている a11y 系の追補（`.url-pill` の代替情報、chip のラベル補強など）は視覚に出さないテキストを足す形になりがちで、**次の 1 コミットで復活させる可能性が高い**。web_quality 自身が「CSS は全体としてかなり無駄がない」と書いているとおり、ここは無駄取りの対象として優先度が低い。削除するなら「使わないと決めた」ことの表明として、a11y の追補を全部確定させた後にやるべき。

**4-5. copy_cvr S-3（対応エコシステムの FAQ 追加）・S-5（OAuth 権限範囲）— 内容は支持するが、fact_check の must-1 / must-3 の確認結果が出るまで書けない。**
順序の指摘。S-5 は「ログイン導線が本番に存在しない」（fact_check must-1）なら文言ごと消える項目で、いま本文案を確定させると差し戻しになる。

---

## 5. 自分の R1 指摘の取り下げ・降格・条件付き化

過剰指摘の削減が目的なので、視覚レンズ側から先に降ろす。

| ID | 処置 | 理由 |
|---|---|---|
| **VD-13**（`.fact` の `<b>` が数値と製品名で混在） | **取り下げ（copy_cvr M-2 に統合）** | 同一問題で、copy_cvr の `648 ケース` + 内訳という案のほうが具体的。2 件として数えない |
| **VD-16**（モバイルで `——` が行頭行末に落ちる） | **取り下げ（copy_cvr M-1(a) / L-3 に統合）** | リード文の全面書き換えで消える。視覚側からは制約を 1 つ添えるのみ → **新リードは 390px で 4 行以内に収めること**（現状 5 行で、fold を圧迫している） |
| **VD-17**（`.formula-expr` の横スクロール） | **取り下げ（a11y M-1 に統合）+ severity を must に格上げ支持** | 私は should と判定したが、a11y の実測（320px で 133px はみ出し・`tabindex` 無しでキーボード到達不能・SC 2.1.1）のほうが強い。修正案も同一（狭幅で `white-space: normal`）。**2 レンズ独立検出なので must でよい** |
| **VD-14**（ライトで glow が見えない → 強める） | **should → later に降格** | a11y_wcag が「半透明ヘッダーにグローが透ける最悪ケース」を合成計算して `fg-muted` 5.65（light）で適合、と証明済み。**不透明度 0.28 → 0.4 に上げるとこの計算が無効になる**。確定した適合を、装飾の可視性という低い便益のために崩す順番ではない。やるなら `tools/check_contrast.py` の再実行とセットで別スプリント |
| **VD-7**（`span-3`「ログインは任意」タイルの右 40% が空白） | **単独では直さない（条件付き）** | fact_check must-1 の帰結で自動的に決まる。**(A) OAuth env を供給する場合** → copy_cvr S-5 の権限範囲の追記がそのまま空白を埋め、VD-7 は消える。**(B) 供給せずタイルを削除する場合** → bento は 6 → 5 タイルになり、3 列で `span-2 + 1` / `1 + 1 + 1` の 2 行にきれいに収まって、**いまの「3 行目に 1 枚だけ寝ている」構造ごと解消する**（今より良い格子になる）。どちらでも解決するので、VD-7 として独立に作業しないこと |

**維持する指摘**: VD-1（対処案差し替え済み・must）/ VD-2（bento の 100px の空洞・must。※ ログインタイル削除でも 1 行目の構成は変わらないので独立に残る）/ VD-3（統合案・must）/ VD-4（`rotateX` 除去・**web_quality M-2 の修正で目立つため優先度上昇**）/ VD-5 / VD-6 / VD-8 / VD-9 / VD-10 / VD-11 / VD-12 / VD-15 / VD-18〜20（later）。

**VD-12 に注記**: 出典注記のリンク範囲を書名だけに縮める修正は、a11y M-2 の「論文タイトルを `<span lang="en">` で囲う（should 相当）」と **同じ要素を触る**。青い帯を短くする ＝ `lang="en"` を付けたい範囲とほぼ一致するので、1 回の編集でまとめて入れれば作業も差分も減る。

**VD-15 に修正**: copy_cvr M-1(b) が `samples` にチップ 1 本追加 + ラベルを長文化する案なので、そのままだとモバイル fold がさらに埋まる（私の VD-15 と正面衝突する）。両立案 —— **「今日の Gem を見る」だけを CTA ボタン直下の 1 行リンクとして fold 内に残し、キーワード例のラベル + 5 チップ（2 行・約 110px）はモバイルのみスクショの下へ移す**。差別化機能への導線は fold に残り、押し下げは 1 行分で済む。

### `a11y_wcag` — 反論
<sub>2026-08-22T09:40:02+09:00</sub>

## a11y_wcag / Round 2 — 反論・譲歩

R1 の自分の実測（Chromium + axe、light/dark × 1280/390/320px、Tab 全巡回、oklch トークン 18 ペア）だけを根拠に判定します。対象ファイルは再読していません。

---

## 1. 争点: `hero-in` の `opacity: 0` を外すと、私の reduced-motion 適合判定は変わるか

**判定: 変わりません。a11y 的に中立で、web_quality M-2 の修正を支持します。**

まず自分の R1 の記述範囲をはっきりさせます。私が「適合」と書いたのは
① `prefers-reduced-motion: reduce` で `animation-timeline: none` / `scroll-behavior: auto` まで打ち消されていること（実測）、
② **`.reveal` が** opacity を動かさないこと、の 2 点で、`hero-in` を opacity フリーだと主張してはいません。
したがって web_quality M-2 と私の R1 は矛盾しておらず、譲歩も撤回も要りません。

そのうえで「外すと a11y 判定に影響するか」への答え:

- **`hero-in` は時間ベース（0.5s + 最大 delay 0.26s）で必ず終わる** ので、CSS コメントが警告している「範囲外に留まった要素が不可視のまま残る」事故は **構造上起きません**。`.reveal`（scroll-driven）と `hero-in`（time-driven）はリスクの性質が違い、コメントの論拠がそのまま `hero-in` に効くわけではない点は、web_quality の「規律が揃っていない」という指摘に対する部分的な反論です。**規律の不統一は事実だが、a11y 上の欠陥ではない。**
- `reduce` 時は `animation-duration: 0.01ms !important` が効いて即座に opacity 1 になることを R1 で実測済み。**外しても外さなくても SC 適合は同じ** です。
- したがって M-2 の修正根拠は **LCP 除外（web_quality の計測）と規律統一** にあり、a11y は賛成票を投じるが根拠は提供しません。**その正直な線引きをした上で賛成します**（a11y を後付けの理由に使わない）。

**ただし修正時に守ってほしい 2 条件**（ここは a11y の要求です）:

1. **フェードの代替として `.hero` に `animation-timeline: view()` を持ち込まないこと。** scroll-driven に変えた瞬間、CSS コメントが正しく警告している「不可視のまま残る」リスクが、よりによってファーストビューに発生します。`translateY` だけの時間ベースのまま残すのが正解です。
2. **`translateY` は `prefers-reduced-motion: no-preference` の中に置いたままにすること。** 現状そうなっているので、opacity を消すときに媒体クエリごと外さないでください。

補足の実利（a11y 側の小さな加点）: opacity を外すと **ヒーローが最初のペイントから可視** になります。画面拡大鏡ユーザーは視野が数百 px しかないため、「まだ薄いうちに視線を置いた領域が後から動く」状態は追従コストが高い。0.76 秒の不可視区間が消えるのは拡大鏡ユーザーに実利があります。

---

## 2. 争点: 900px 未満でページ内ナビが消える件 — JS ゼロを崩さずに満たせるか

まず記録の訂正: **これは visual_design ではなく私（a11y_wcag）の S-1 です。** visual_design の R1 にこの指摘はありません（VD-15 / VD-8 がモバイル指摘ですが別件）。

**判定: フッターナビに `#why` / `#how` / `#trust` を足すだけで SC 1.4.10 の懸念は閉じます。JS も `details` ハンバーガーも不要。私の S-1 を should → later に格下げします（この条件付きで）。**

根拠を分けて書きます。

**(a) SC 1.4.10 の要求は「同じ場所に同じ形で」ではない。**
1.4.10 が求めるのは「情報 **または機能** の損失なく提示できること」であって、導線の位置・到達歩数までは規定していません。5 つのアンカー先すべてに 320px でも到達できる導線が **ページ上のどこかにあれば**、機能は保持されています。現状は `#features` / `#faq` の 2 つだけがフッターにあり、`#why` / `#how` / `#trust` の 3 つが **どこにもない** のが問題の実体なので、フッター `<nav aria-label="プロダクト">` に 3 本足せば穴は塞がります。

**(b) 隣接 SC は発火しない（他レビュアーが誤って持ち出さないよう明示します）。**
- **SC 2.4.5 Multiple Ways（AA）は適用外。** 条文が対象にするのは "a set of web pages" であり、単一ページの LP は集合を成しません。
- **SC 3.2.3 Consistent Navigation（AA）も適用外。** 同じく複数ページ間の一貫性を問う条項です。
- **SC 2.4.1 Bypass Blocks（A）は既に満たしている。** スキップリンクが全幅で機能することを R1 で実測済み（最初の Tab 停止点で `top=8, left=8`、`z-index 100 > ヘッダー 50`、Enter で `<main tabindex="-1">` にフォーカス移動、次の Tab がヘッダーを飛ばしてヒーロー CTA へ）。ヘッダーナビが消えても 2.4.1 には一切触れません。

**(c) `details` / `summary` ハンバーガーは a11y 的に非推奨（JS ゼロを守れても割に合わない）。**
JS ゼロのまま開閉メニューを作る唯一の手段ですが、代償が大きい:
- **Escape で閉じられない**（JS なしでは不可能）。開閉メニューの標準的な期待動作が欠ける。
- **リンクを押しても開いたまま**。同一ページ内アンカーなので遷移で閉じることもない。開いたパネルが `position: sticky` + `z-index: 50` + `backdrop-filter` のヘッダー内に居座り、**フォーカス移動先の本文をパネルが覆う ＝ 自分で SC 2.4.11 の違反を作りかねない**（R1 で「2.4.11 は適合」と実測できている状態を、わざわざ壊しにいく変更です）。
- 5 本のアンカーのためにこれを負うのは、リスク／便益が明確に見合いません。

**(d) 「横スクロールする chip 列にする」という R1 の自分の代替案は取り下げます。**
R1 で私はこれを最小コスト案として挙げましたが、320px のヘッダーには既にブランド + CTA ボタンが入っており、そこへスクロールコンテナを足すのは密度的に無理があります（visual_design VD-15 が指摘する「モバイルのファーストビューがテキストで押し下げられている」問題と同じ方向に悪化する）。
なお **a11y 的には成立します**（リンク自体が Tab で順に到達でき、ブラウザが `scrollIntoView` するため、`.formula-expr` のようなキーボード到達不能領域にはならない）。念のため書いておくと、axe の `scrollable-region-focusable` はフォーカス可能な子要素を持つ領域を除外するので、リンクが並んだ横スクロール列は M-1 と同じ違反にはなりません。**それでも視覚密度の理由で (a) を推します。**

---

## 3. 争点: `body { font-size: 16px }` は アプリの `--text-control-min: 1rem` と整合するか

**判定: 整合していません。fact_check の裏取りによって私の S-2 は弱まるどころか補強され、性質が「a11y の推奨」から「LP とアプリの設計不整合」へ格上げされます。ただし修正範囲は絞る必要があり、そこは自分の R1 提案を修正します。**

**(a) 不整合であることの根拠（fact_check の引用に依拠）。**
fact_check must-2 が引いた `src/ui/components/input.tsx:9` の `text-base` は `font-size: 1rem`、`ui-ux-guidelines.md:140` も「全ブレークポイントで縮小しない」。**アプリ本体は相対単位でユーザーのフォントサイズ設定に追従する設計** です。
一方 `styles.css` の冒頭コメントは「トークンの出自: `app/globals.css`」と明記して色を揃えているのに、**タイポグラフィだけ px に落ちている**。色は継承したがサイズの単位方針は継承していない、という非対称が実体です。私の S-2 は「a11y 的にこうあるべき」ではなく「**自分たちの設計方針と食い違っている**」という指摘に置き換わります。こちらのほうが is/ought の議論にならず決着が早い。

**(b) 現状は px と rem の混在で、拡大時にタイポスケールが崩れる。**
R1 で `document.documentElement.style.fontSize = '32px'`（ユーザー既定 200%）にして測ったところ `body` は 16px のままでした。一方 CSS を読む限り、`.hero h1` は `clamp(2rem, 5.4vw, 3.65rem)`、`.stat b` は `1.5rem`、`.fact b` は `1.375rem`、`.formula-expr` は `clamp(0.95rem, 2.1vw, 1.25rem)` と **rem / clamp 側** です。つまりユーザーが既定フォントを上げると **見出しと数値だけが育ち、本文・ナビ・ボタン・chip・タグ・キャプションは 16px 以下に据え置かれる**。全部固定より、この混在のほうが読みづらい可能性があります。「px で統一する」か「rem で統一する」かの二択で、**後者を推す** という主張です。

**(c) 自己批判 — R1 の私の提案「`--header-h` も rem 化」は撤回します。**
`--header-h: 60px` を素朴に `3.75rem` にすると、既定 200% で **120px の sticky ヘッダー** になります。SC 1.4.10 が要求する 400% ズーム相当（1280×1024 → 320×256 CSS px）では、**ヘッダーだけでビューポート高の 47% を占有** し、R1 で「適合」と実測した SC 2.4.11 Focus Not Obscured を自分から壊しにいく変更になります。単位を直すつもりが SC を割る、という典型的な事故です。

**修正後の推奨（範囲を絞る）**:
1. **文字サイズだけ rem 化する** — `body`（`1rem`）、`.btn` / `.chip` / `.header-nav a` / `.tag-list li` / 各キャプションの `font-size`。
2. **`--header-h` は px のまま** か、上限を切る（`clamp(56px, 3.75rem, 88px)`）。
3. **短いビューポートで sticky を降ろす** — `@media (max-height: 26rem) { .site-header { position: static } }`。JS ゼロのまま 2.4.11 のリスクを構造的に消せる、この LP に合った定石です。
4. `.site-header { height }` は `min-height` に変える（クリップの余地を残さない）。

**(d) visual_design との突き合わせ。**
- **VD-8（モバイルで CTA 2 本の幅が不揃い → `.hero-actions .btn { width: 100% }`）とは相補的。** ボタンを 100% 幅にしておくと、rem 化で文字が育っても横に溢れず縦に伸びるだけになります。**rem 化を入れるなら VD-8 は先に入れたほうが安全** です。
- **VD-15（モバイルのファーストビューにスクショが 1px も入らない）とは同方向に効く。** rem 化は縦の消費を増やすので、拡大設定のユーザーでは VD-15 の症状が悪化します。ただし VD-15 自身の処方（`assurance` を 3 項目にして 1 行化・`samples` をスクショの下へ）は **どちらの世界でも効く** ので、衝突ではなく「VD-15 を先に入れておくと rem 化の副作用が相殺される」という順序関係です。
- **VD-4 / VD-6 / VD-10 とは無関係**（単位の話が絡まない）。

---

## 4. 名指しで否定するもの

**4-1. web_quality S-4 の後半 —「`.assurance li::before` の `✓` に読み上げ用テキストを付ける等で `.sr-only` を実際に使う」は a11y 的に逆行です。**

`.sr-only` が死にセレクタなので **削除する** という前半には賛成します。否定するのは用途の提案のほうです。私の R1 L-2 で挙げたとおり、`content: '✓'` は **すでに読み上げノイズになる懸念がある側** の要素です（Chromium は擬似要素のテキストをアクセシビリティツリーに出す。SR 側の設定で聞こえ方は変わるため R1 では `later` に留めています）。そこへ sr-only テキストを足すのは、**ノイズを 1 つから 2 つに増やす** 変更です。
正しい方向は逆で、`✓` を **`background-image` か SVG に置き換えてアクセシビリティツリーから外す** こと。「登録不要」「無料」というテキストは既に読まれており、チェックマークは純粋な視覚装飾です。**`.sr-only` は使い道を探さず素直に削除** でよい（この LP に読み上げ専用テキストを要する箇所は現状ありません）。

**4-2. visual_design VD-12 のうち `.source-note a { text-decoration-thickness: 1px }` は否定します（リンク範囲を書名だけに縮める前半は支持）。**

- 前半（リンクを『Six Million…』の書名だけにして `ほかの調査まとめ` を地の文へ）は **SC 2.4.4 Link Purpose の観点でも改善** です。リンクの目的が書名 = 到達先そのものになり、リンク一覧読み上げモードでの情報量が上がります。賛成。
- 後半の下線を細くする案は反対です。`.source-note` は 13.5px と本文中で最小級のサイズで、**下線は本文中リンクを色以外で識別させる唯一の手段**（SC 1.4.1 Use of Color）。13.5px で 1px 下線はロービジョンでは相当厳しい。そして **「青い帯」に見える原因は太さではなく長さ** であり、前半の範囲短縮だけで症状は消えます。**副作用のある処方を、効く処方に足す理由がありません。**
- なお `a:hover { text-decoration-thickness: 2px }` が既にあるので、`.source-note a` だけ 1px にすると hover で 1px → 2px と跳ねます。整合性の面でも入れないほうが素直です。

**4-3. visual_design VD-17 の事実記述を 1 点訂正します（処方には全面賛成）。**

VD-17 の「切れて **右にはみ出す**」は不正確です。R1 の実測では **`docScrollWidth === innerWidth`（320 / 390 いずれも）でページ自体は横スクロールしません**。実際に起きているのは `.formula-expr` の **内側** でのクリップで、`overflow-x: auto` により 320px で `scrollWidth 371` に対し `clientWidth 238` — つまり **133px 分が箱の中に隠れている** 状態です。ページ外にはみ出していないぶん、**スクロールバーの存在に気づきにくく症状としてはむしろ悪い** ので、VD-17 の結論（`white-space: normal` で折り返す）はより強く支持されます。

**そのうえで統合上の重要点: VD-17 を実装すれば、私の M-1（SC 2.1.1 キーボード到達不能なスクロール領域）は同時に解消します。** スクロールコンテナ自体が消えるためです。**両方入れないでください** — 折り返しにしたうえで `tabindex="0"` を足すと、スクロールしない要素に無意味なタブ停止点が 1 つ増えるだけで、Tab 回数を増やす純粋な劣化になります。**VD-17 の (a) 案（折り返し）を採用 → M-1 はクローズ**、という順で処理するのが正解です。

---

## 5. 名指しで支持・補強するもの

**5-1. fact_check must-2（「タップ領域は 44px 以上」→「主要導線のタップ領域は 44px」）を全面支持します。これは私の担当レンズの指摘であり、fact_check の判定が正しい。**

数値の根拠を補強します。**WCAG 2.2 で 44×44 を要求するのは SC 2.5.5 Target Size (Enhanced) で、これは AAA です。AA の要求は SC 2.5.8 Target Size (Minimum) の 24×24。** fact_check が引いた `ui-ux-guidelines.md:459`「すべてのコントロールに 44px を要求しない」「適合目標は AA、2.5.5 は AAA で準拠を謳うものではない」は、**規格の読み方として正確** です。

さらに危険な点を 1 つ足します。この文言があるタイル（「キーボードだけで完走できる」）には `.tag-list` で **`WCAG 2.2 AA` というバッジが並んでいます**。**AA を掲げた真横に AAA の数値を無条件で置く** 構図なので、規格を知っている読者ほど「じゃあ AAA なのか？ 全コントロールで測ったのか？」と検証しにきます。LP の柱が「誇張しない透明性」である以上、ここは最も損な失点の仕方です。fact_check の書き換え案（主語を主要導線に限定）をそのまま採用すべきです。

なお **LP 自身**（`site/`）の実測では、非インライン要素は `.btn` 44 / `summary` 64 / `.header-nav a` 45 / `.chip` 36 / `.btn-sm` 40 / `.footer-grid a` 32 とすべて 24×24 以上で、SC 2.5.8 は満たしています（本文中リンクはインライン例外）。**LP は AA を満たしており、問題はアプリについての記述だけ**、という切り分けです。

**5-2. web_quality M-1（`color-mix()` のフォールバック欠落）は、a11y 観点でも must です。根拠を足します。**

web_quality は視認性の文脈で書いていますが、**非対応ブラウザでヘッダー背景が `rgba(0,0,0,0)` になる** という実測が正しいなら、これは **SC 1.4.3 Contrast (Minimum)（AA）の失敗** です。sticky ヘッダーのブランド名・ナビ・CTA が、スクロールしてくる **任意の本文・スクリーンショット画像の上** に重なるため、コントラスト比が確定できません（規定不能 ≒ 保証なし）。装飾の劣化ではなく AA 不適合として扱うべきです。

**あわせて私の R1 判定の適用範囲を自己訂正します。** R1 で「SC 2.4.11 適合・コントラスト 17/18 ペア適合」と書いた実測は **`color-mix()` と `backdrop-filter` が効く Chromium 上のもの** です。両方が効かない環境（web_quality S-1 の Safari 17 以下）では:
- **SC 2.4.11 の判定は変わりません**（`scroll-margin-top` は背景と無関係のため、実測結果はそのまま有効）。
- **SC 1.4.3 は保証できません**（上記の理由）。
私の「適合」はブラウザ限定の但し書き付きだった、と明示しておきます。**M-1 の 1 行フォールバックと S-1 の `-webkit-backdrop-filter` を入れれば、この但し書きは外れます。**

**5-3. visual_design VD-6 / VD-10 は a11y 的に問題なし。追加のコントラスト検証は不要です（実装前に止める必要はありません）。**

- **VD-6（`.compare-card.is-good .stat b { color: var(--accent) }`）**: `.stat b` は `1.5rem`（24px）+ `font-weight: 700` なので **WCAG の「大きな文字」に該当し、しきい値は 3:1**。R1 実測の `accent / bg` は **light 8.36 / dark 7.95** で、通常文字の 4.5:1 基準で見ても余裕で通ります。
  SC 1.4.1 Use of Color も問題なし — 「こちらが良い指標」であることは見出し文（`被依存数から見ると`）と各 `<span>` のラベルが担っており、**色は補助** です。色覚特性のあるユーザーでも意味は落ちません。
- **VD-10（`.limits` の破線をやめ `background: color-mix(in oklab, var(--bg-subtle) 60%, var(--bg))`）**: 新しい面は `--bg` と `--bg-subtle` の **中間色** なので、そこに載る `--fg-muted` のコントラストは R1 実測の `fg-muted/bg`（light 6.00 / dark 7.63）と `fg-muted/bg-subtle`（light 5.50 / dark 6.91）の **間に必ず収まります**。両端が AA を満たしている以上、中間も満たします（区間論証なので再計測不要）。破線 `--border` の除去による情報損失もありません（枠は非インタラクティブなカードの装飾で、SC 1.4.11 の「理解に必要な視覚情報」に当たらないと R1 で判定済み）。

---

## 6. 統合時の注意（軽微・2 点）

**6-1. copy_cvr M-1(b) の `今日の Gem を見る` チップを追加する場合、`aria-labelledby` との整合を保つこと。**
現状 `<ul class="chips" aria-labelledby="samples-label">` はリストに「キーワードの例（クリックでそのまま検索）」という名前を与えており、SR はリスト進入時にこれを読みます。**キーワードではない操作チップを同じリストに混ぜると、リストの名前が第 1 項目に対して不正確になります。**
copy_cvr の提案はラベル文自体を「キーワードなしで開くと『今日の Gem』／例のキーワードはクリックでそのまま検索」に書き換えているので、**その書き換えとセットで入れる限り整合します**（片方だけ入れないこと）。別解として、操作チップを `<ul>` の外に単独で置けばラベルを触らずに済みます。

**6-2. LP 自身は Lighthouse の a11y ゲートの対象外である、という前提の確認。**
fact_check が `tools/run_lighthouse.mjs:52-58` の `rounded < 100 → GATE_FAIL` を裏取りしており、「Accessibility 100 を下回ったらリリースしない」の記述は **アプリについては事実** です。ただしそのゲートが回っているのは Next.js アプリであって、**`site/` の静的 LP はこの機械ゲートを通っていない** はずです（通っていれば私の M-1 = axe `serious` は検出されていた）。
これは fact_check の判定を覆すものではありません（記述の主語はツールなので事実誤りではない）。指摘したいのは **運用のほう** です — 「Accessibility 100 を必須ゲートにしている」と書いたページ自身が AA 違反 2 件（M-1 / M-2）を積んだまま公開されるのは、この LP の唯一の柱である透明性を最も安く毀損します。**公開前に M-1 / M-2 を潰す** か、可能なら `site/` も同じゲート（axe か Lighthouse）に載せるのが筋です。前者は今スプリントで確実にできます。

---

## 7. R1 からの変更点まとめ

| 項目 | R1 | R2 | 理由 |
|---|---|---|---|
| M-1 `.formula-expr` SC 2.1.1 | must | **must（据え置き）／処方は VD-17 に統合** | 折り返しでコンテナごと消える。`tabindex` 追加と併用しない |
| M-2 `lang="en"` SC 3.1.2 | must | **must（据え置き）** | 反論なし |
| S-1 900px 未満のナビ消失 | should | **later へ格下げ**（フッターに 3 アンカー追加を条件） | 1.4.10 は導線の位置を規定しない。JS も `details` も不要 |
| S-2 `body { font-size: 16px }` | should | **should（据え置き・論拠を強化）** | アプリの `1rem` 方針との不整合として再定義。ただし `--header-h` の rem 化は **撤回** |
| S-3 chip 枠 1.39:1 | should | **should（据え置き）** | 反論なし |
| S-4 404.html の `h1` 欠落 | should | **should（据え置き）** | web_quality S-3 と独立に同じ結論。相互裏付け |
| R1 の「2.4.11 / コントラスト適合」判定 | 無条件 | **Chromium 限定と自己訂正** | web_quality M-1 / S-1 未修正の環境では SC 1.4.3 を保証できない |

### `web_quality` — 反論
<sub>2026-08-22T09:40:32+09:00</sub>

## web_quality / Round 2 — rebuttal & concession

R1 の実測（LCP 候補の全列挙・`color-mix` 非対応シミュレーション・CSSOM 全 147 ルールの DOM 照合）に基づいて回答する。**自分の must を 1 件 should へ、should を 1 件 later へ自主降格** した上で、残る must 1 件の修正案を 1 つに確定させる。

---

## 1. 【修正案の確定】M-2 `hero-in` の `opacity` — **`opacity` を削除し `transform` のみにする**（他案はすべて却下）

コーディネーターの求めに応じ、案を 1 つに決める。

```css
/* assets/styles.css:1070-1079 */
@keyframes hero-in {
  from {
    opacity: 0;              /* ← この 1 行を削除するだけ */
    transform: translateY(14px);
  }
  to {
    opacity: 1;              /* ← 併せて削除（to は base と同じになる） */
    transform: none;
  }
}
```

`.hero > .wrap > *` の `animation: hero-in 0.5s cubic-bezier(0.22, 0.61, 0.36, 1) both`（1047 行）と、**0.02s → 0.26s の stagger（1049-1069 行）はそのまま残す**。差分は keyframes の 2 行削除のみ。

### なぜこの案か（visual_design の「登場感」を保てる根拠）

**visual_design 自身が R1 の「良い点 2」でこう書いている**:

> スクロール連動アニメーションで `opacity` を動かさない判断（CSS のコメントに理由も残っている）。「見えないまま残る」事故を構造的に潰しつつ、**`transform` だけで十分な出現感が出ている**。

a11y_wcag も「問題なし 4」で同じ判断を「構造的に排除できています」と評価している。つまり **`transform` だけで出現感が成立することは、視覚レンズと a11y レンズの両方が独立に承認済み** である。`.reveal` の移動量は 22px、`hero-in` は 14px と更に控えめなので、`.reveal` で足りているものが `hero-in` で足りない道理がない。**「原則は 3 名が支持しているのに、`hero-in` にだけ適用されていない」というのが問題の全体像** であり、私の指摘は新しい規律の提案ではなく既存規律の適用漏れの指摘である。

### 却下した案とその理由（技術的に成立しないものを含む）

| 案 | 判定 | 理由 |
|---|---|---|
| フェード演出そのものを撤去（`hero-in` ごと削除） | ❌ 却下 | 過剰。visual_design の「登場感」を無意味に失う。stagger も消えてヒーローが平板になる |
| `animation-fill-mode` を `both` → **`forwards`** に変える | ❌ **技術的に逆効果** | backwards fill が切れるので **delay 中は不透明で表示され、0.26s 時点で突然 opacity 0 に飛んでから再び現れる＝点滅** する。しかも「一度 opacity 0 で描画される」事実は変わらないので LCP 除外も直らない |
| `both` → `backwards` | ❌ 無意味 | `to` が base 値と同一なので `both` と挙動が完全に一致する。何も変わらない |
| `from { opacity: 0.01 }` にして LCP 除外だけ回避 | ❌ 却下 | Chromium の除外条件は `opacity: 0` ちょうどなので **数値上は LCP が改善する**。だが実ユーザーには依然ほぼ不可視で、**計測値だけを良く見せる小細工** になる。指標を騙す変更は入れない |
| `transform` のみに変更（**採用**） | ✅ | 演出は残り、LCP 除外・0.76s の不可視時間・自リポジトリ規律違反の 3 つが同時に消える。差分 2 行 |

### 修正後に何が LCP になるか（実測していないことは実測していないと書く）

R1 で実測できたのは「現状の LCP 候補はヘッダーのナビリンク 1 件（2,916px²）のみ」「`prefers-reduced-motion: reduce` では H1（182,213px² / 216ms）」まで。**`transform` だけ残した状態は未計測** なので断定しない。候補は H1 か ヒーロー画像（660,137px²）のどちらかで、**どちらになっても現状より正しい**。修正後に同じ計測（PerformanceObserver で LCP 候補を全列挙）を回して確定させる。

なおこの修正は他レンズと次のように噛み合う:

- **visual_design VD-15（モバイルのファーストビューにスクショが 1px も入らない）を採ると、ヒーロー画像がファーストビューに入って LCP 要素になる可能性が上がる。** その場合 `index.html:153` の `fetchpriority="high"` が初めて本来の意味を持つ（現状は opacity 0 に潰されて優先度指定が無駄撃ちになっている）。**VD-15 は私の観点からも支持する。**
- **visual_design VD-4（`rotateX(3deg)` を 0 に）を採ると `.shot-stage` の `perspective: 1600px` も不要になる。**3D transform は合成レイヤー昇格を強制するので、私の L-1（`will-change: transform` 12 個の削除）と合わせるとモバイルの GPU メモリが素直に減る。**VD-4 も支持。**

---

## 2. 【自主降格】M-1 `color-mix()` フォールバック欠落 → **should へ落とす**

コーディネーターの求めに応じて 2026 年時点の対応状況で再評価した結果、**私の R1 の must 判定は過剰だった**。

`color-mix()` のサポート開始は Safari 16.2（2022-12）/ Chrome・Edge 111（2023-03）/ Firefox 113（2023-05）。**Baseline Newly available は 2023-05**、Widely available（Newly から 30 か月）は **2025-11 に到達済み**。本レビュー時点（2026-08）で Widely available 入りから 9 か月が経っている。加えて本 LP の読者は開発者であり、旧ブラウザ比率は一般消費者向け LP より更に低い。

壊れ方の再評価も必要だった。R1 で「本文が読めなくなる」と書いたが、正確には **ヘッダー帯（高さ 60px）の範囲でのみ本文と重なる** のであって、ページ全体が読めなくなるわけではない。影響範囲を過大に書いた。

→ **severity を should に下げる。**

ただし **実施の優先度は下げない**。修正は

```css
background: var(--bg);                                     /* 追加 */
background: color-mix(in oklab, var(--bg) 82%, transparent);
```

の 1 行で、対応ブラウザでは 2 行目に上書きされるだけなので **副作用が数学的にゼロ**。コストゼロ・リスクゼロの防御は、シェア議論をする前に入れてしまうほうが安い。「severity は should、実施は今スプリント」で扱いたい。

### 【自主降格 2】S-1 `-webkit-backdrop-filter` → **later へ落とす**

Safari が unprefixed `backdrop-filter` に対応したのは Safari 18（2024-09）。2026-08 時点で iOS 18 未満の残存は小さく、かつ **上の M-1 を直せば `--bg` 82% 相当の不透明背景が残る** ので、ブラーが無くても可読性は確保される。R1 では「M-1 と重なって透明かつブラー無しになる」と書いたが、**M-1 を直す前提ではその複合シナリオ自体が消える**。単独で見れば「旧 Safari でヘッダーがすりガラスにならない」だけの見た目の劣化であり、should は過剰だった。→ **later**。

---

## 3. a11y_wcag M-1 `.formula-expr` — **`tabindex="0"` 案には反対、`white-space: normal` 案を全面支持**（衝突しない、むしろ同方向）

a11y_wcag が本命に置いた「狭幅で `white-space: normal` にしてスクロールコンテナ自体を作らない」と、visual_design VD-17「モバイルでは `white-space: normal` にして 2 行で折り返す」は **独立に同じ結論に到達している**。私も同じ側に付く。

**`tabindex="0"` + `role="group"` + `aria-label` 案に反対する理由（私のレンズから 3 点）**:

1. **フォーカス可能要素が 1 つ増えるのに、そこで実行できる操作が何もない。** 読むだけの `<p>` を Tab 順に差し込むことになり、キーボード利用者のコストは下がらず **上がる**。axe の `scrollable-region-focusable` を黙らせるための対症療法であって、「横スクロールしないと式の後半が読めない」という根本の不便（a11y_wcag 自身が「状態自体は残る」と認めている）は残る。
2. **HTML 属性 3 個は恒久的な保守対象になるが、CSS 宣言の削除は保守対象を減らす。**`role="group"` と `aria-label="Gem Index の計算式"` は、直前の `<h3>「今日の Gem」の並び順</h3>` が既に与えている文脈の二重化でもある。
3. **私の R1 S-4（死にセレクタ `.sr-only` の削除）と方向が逆になる。**「DOM に補助属性を足して問題を隠す」より「問題が発生しない構造にする」ほうが、CSSOM 全 147 ルール中の未一致が `.sr-only` 1 件だけという現状の綺麗さと整合する。

**さらに一歩踏み込んだ提案 — メディアクエリすら要らない。**a11y_wcag は「狭幅で」、VD-17 は「モバイルでは」と幅分岐を前提にしているが、分岐は不要である。`.formula-expr`（styles.css:675-684）から次の 2 宣言を **削除するだけ** でよい:

```css
.formula-expr {
  /* white-space: nowrap;   ← 削除 */
  /* overflow-x: auto;      ← 削除 */
  text-wrap: balance;       /* 2 行に割れるとき行長を均等にする（任意） */
}
```

a11y_wcag の実測では 1280px の `scrollWidth` は「なし（はみ出さない）」＝ 広幅では元々 1 行に収まる。**折り返し可にしても広幅の見た目は一切変わらない**。つまり:

- SC 2.1.1（a11y_wcag M-1）解決 ✅
- VD-17（モバイルで式が切れる）解決 ✅
- 新しいメディアクエリ 0 個・新しい HTML 属性 0 個・**CSS が 2 行減る** ✅

**衝突しないどころか、3 レンズの指摘が 2 行の削除に収束する。** この案を採るよう強く推す。

---

## 4. 他者の指摘への名指しの否定・訂正

### 4-1. ❌ a11y_wcag L-3「`:focus-visible` を伴う移動だけ `scroll-behavior: auto` にする」— **技術的に実装不可能。取り下げを提案する**

CSS には「このスクロールがフォーカス移動によるものか、アンカークリックによるものか」を区別する手段が存在しない。`scroll-behavior` はスクロールコンテナ（ここでは `html`）に対する指定であって、**スクロールの発生源で分岐できない**。`:focus-visible { scroll-behavior: auto }` と書いてもフォーカスされた要素自身のスクロール挙動が変わるだけで、それをスクロールさせている `html` には効かない。

実現するには `focusin` を拾って一時的に `html.style.scrollBehavior` を切り替える JS が要るが、**この LP は「ページ内 JavaScript ゼロ」を設計上の約束にしており（README:23）、fact_check も `<script>` は JSON-LD 1 本のみと裏を取っている**。指摘のためにこの約束を崩す価値はない。

現状は `prefers-reduced-motion: reduce` で `scroll-behavior: auto !important` により無効化済み（a11y_wcag 自身が「問題なし 4」で実測確認している）。**a11y_wcag も「不適合ではない」と明記しているので、later ごと取り下げるのが妥当。**

### 4-2. ⚠️ a11y_wcag S-2「`--header-h` / `.btn` / `.chip` の `min-height` を rem 化」— **`min-height` の rem 化には反対。font-size 系だけに限定すべき**

`body { font-size: 16px }` → `1rem` は **全面的に支持する**（`html` に `font-size` 指定が無いので既定 16px のまま変化せず、ユーザー設定に追従するようになる。副作用ゼロ）。

だが `min-height` まで rem 化するのは **逆効果** である。24px / 44px は WCAG 2.5.8 / 2.5.5 が **CSS ピクセルで定義した閾値** であり、rem 化すると「ユーザーが既定フォントサイズを **小さく** した」ときに閾値を割る。a11y_wcag 自身が「問題なし 2」で `.btn` 44px / `.chip` 36px / `.footer-grid a` 32px を実測して 2.5.8 適合を確認しているが、これらを rem 化して既定 12px のユーザーが来ると `.btn` 33px / `.chip` 27px / `.footer-grid a` 24px となり、**その適合根拠が自分で崩れる**（`.footer-grid a` は 24px ちょうどで境界に乗る）。

**切り分け案**: `body` / `.btn` / `.chip` / `.header-nav a` の **`font-size` は rem 化**、`--tap` と各 `min-height` は **px のまま維持**。`--header-h: 60px` は sticky ヘッダーの高さで、`scroll-margin-top: calc(var(--header-h) + 16px)` が SC 2.4.11 適合の根拠になっているため、**rem 化するならフォント拡大時にヘッダーが伸びる分だけ scroll-margin も追従する** ので理屈は通る（こちらは rem 化してよい）。

### 4-3. ⚠️ a11y_wcag S-1（900px 未満でナビ消滅）— **2 案のうち「フッターに `#why` / `#how` / `#trust` を足す」を推す。chip 列化は SC 2.4.11 適合を壊す**

a11y_wcag は「狭幅では `.header-nav` を消さず横スクロールする chip 列にする」を最小コスト案として挙げているが、これは **ヘッダーの高さを変える**。sticky ヘッダーは `height: var(--header-h)`（60px 固定）で、chip 列を 2 段目に置けばヘッダーは 96px 前後に伸びる。すると `scroll-margin-top: calc(var(--header-h) + 16px)` が実高より小さくなり、**a11y_wcag 自身が「問題なし 1」で「フォーカス要素 30 個すべてがヘッダーと重ならない」と実測確認した SC 2.4.11 適合が崩れる**。

`--header-h` も同時に更新すれば直せるが、狭幅だけ別値にするメディアクエリが要り、複数箇所の同期という保守負債が生まれる。**フッター `<nav aria-label="プロダクト">` にリンクを 3 本足す案は副作用が完全にゼロ**（レイアウトも `--header-h` も触らない）。こちらを推す。

### 4-4. ⚠️ visual_design VD-1（ダーク版スクショの `<picture>` 出し分け）— 方針は支持。ただし実装で必ず踏む地雷が 3 つある

`<picture>` + `<source media="(prefers-color-scheme: dark)">` は正しく機能する（メディアクエリ変化時にブラウザが再評価する）。転送量も増えない（1 枚しか取らない）。その上で、**ヒーロー画像を `<picture>` 化するときに壊れやすい点** を先に置いておく:

1. **`fetchpriority="high"` は `<source>` に付けても無効。**`<source>` に `fetchpriority` 属性は存在しないので、`<img>` 側に残すこと。移し替えると §1 の修正で取り戻したはずの LCP 優先度をまた失う。
2. **`width` / `height` は `<img>` に残し、`<source>` にも同じ値を付ける。**R1 で CLS = 0.0000 を実測しているが、これは全画像に属性寸法があるおかげ。ライト版とダーク版を **同一ピクセル寸法で撮り直さない** と、テーマによって CLS が出る。
3. **`decoding="async"` / `loading="lazy"` も `<img>` 側。**bento の 2 枚は `loading="lazy"` が付いているので、`<picture>` 化で落とさないこと。

なお **VD-3（`shot-digest` をやめて HTML テキストのミニ表で組む）は私の観点から強く支持する**。35KB の転送が消え、ダーク対応（VD-1）が 1 枚ぶん不要になり、拡大しても潰れない。fact_check が `26,633 / star 111` の裏を取っているので、テキスト化しても数値の正確性は担保されている。**VD-1 と VD-3 は「VD-3 を先にやると VD-1 の対象が 3 枚→2 枚に減る」という依存があるので、VD-3 を先に決めたい。**

### 4-5. ❌ copy_cvr M-2 の `648 ケース` は算数が合わない — 正しくは **`650 ケース`**

copy_cvr は `<b>` を `648 ケース` にする案を出しているが、fact_check が実測で確定させた値は **ユニット・結合 562 / E2E 88** である。`562 + 88 = 650`。`648` は LP 現行表記の「約 560」を丸めた値から逆算した数字で、実測と 2 件ずれる。**信頼の担保として数字を出すセクションで、検証すると合わない数字を置くのは最悪** なので、`650 ケース`（内訳 `ユニット・結合 562 / E2E 88`）に直すこと。VD-13 も同じ箇所を「単一の数値に揃える」と指摘しており、両者を採るなら数値は fact_check の実測値に揃える。

### 4-6. ⚠️ copy_cvr S-10（`og:description` の書き換え）— 内容は支持、**語順を変えないと肝心の部分が切られる**

copy_cvr 案は 91 字。X / Slack / Discord のカードは description を概ね全角 60〜70 字前後で truncate するため、**この案では末尾の「登録不要・無料・MIT」が切れる**。R1 で実測したとおり現行の `og:description` は 63 字で収まっている（`meta[name=description]` は 105 字で SERP 向けに適正、こちらは触らなくてよい — copy_cvr が og だけを対象にしているのは正しい）。

数字を前に出す狙いは活かしつつ、**切られてもいい情報を末尾に置く** 語順を提案する:

> `25 star なのに 11 万パッケージから依存されている OSS を毎日 5 件。star ではなく被依存数から GitHub を探す検索ツールです。登録不要・無料・MIT。`

（先頭 40 字で「驚きの数字」が完結し、以降が切れても意味が通る）

### 4-7. ℹ️ copy_cvr M-1(b) の HTML 案 — `chip-lead` クラスが CSS に存在しない

提案されている `<a class="chip chip-lead" …>` の `chip-lead` は `styles.css` に定義が無い（R1 で CSSOM 全 147 ルールを列挙済み）。このまま実装すると `.chip` のスタイルだけが当たり、意図した「先頭の強調」にならない。採用するなら styles.css への定義追加を同じ差分に含めること。**私の R1 S-4 が「未使用セレクタ」の指摘だったのに対し、これは逆向きの「未定義クラス」** なので、実装時に同じチェック（CSSOM ↔ DOM の突合）で拾える。

### 4-8. ℹ️ fact_check must-1（ログイン機能が本番で使えない）— **LP の公開を env 供給待ちでブロックすべきではない**

技術的な事実として、**この LP は `gh-pages` ブランチの静的ファイルであり、本番アプリ（Workers）とデプロイ経路が完全に独立している**。したがって「本番に OAuth 4 変数を供給する（案 A）」の完了を待って LP 公開を止める理由は無い。**案 B（文言を落とす）で先に公開し、env が供給された時点で文言を戻す** という順序が、公開を最短にしつつ「LP に事実と異なる記述を出さない」という制約も満たす。

副次的な依存関係を 1 つ明示しておく: **案 B を採ると copy_cvr S-5（OAuth の権限範囲を LP に書く）は丸ごと不要になる**（書く対象の機能が LP から消えるため）。両方を独立に実装リストへ載せると矛盾するので、ここは順序を決めてから着手したい。

---

## 5. R1 の指摘のうち、他者の実測で裏付けが取れたもの

- **`.reveal` の transform-only 設計**: a11y_wcag が「最下部までスクロール後に全 12 個の `.reveal` が transform 恒等行列（ずれ残留ゼロ）」と実測。私の R1 OK-7 と一致し、**§1 の修正が「新ルール」ではなく「既存ルールの適用」であることの裏付けになる**。
- **404.html のローカル無スタイル**: a11y_wcag が「自動検出の限界」の末尾で独立に同じ現象に当たっている（私の R1 S-2 と一致）。**2 名が同じ落とし穴を踏んだ以上、README への注記（私の R1 S-2）は「あったほうがよい」ではなく「無いと次のレビュアーも踏む」レベルの実害がある。**
- **404.html に `<h1>` が無い**: 私の R1 S-3 と a11y_wcag S-4 が独立に一致（axe `page-has-heading-one` でも検出）。**争点なし、確定事項として実装リストへ。**

## 6. 更新後の私の severity 一覧

| ID | 内容 | R1 | **R2** |
|---|---|---|---|
| M-2 | `hero-in` の `opacity: 0` で LCP 候補から永久除外 | must | **must（維持）** |
| M-1 | `.site-header` の `color-mix()` フォールバック欠落 | must | **should（自主降格）** ※実施は今スプリント |
| S-2 | README と 404.html の絶対パス不整合 / ローカル無スタイル | should | **should（維持・a11y_wcag が独立に追認）** |
| S-3 | 404.html に `<h1>` が無い | should | **should（維持・a11y_wcag S-4 と一致）** |
| S-4 | 死にセレクタ `.sr-only` | should | **should（維持）** |
| S-1 | `-webkit-backdrop-filter` 欠落 | should | **later（自主降格）** |
| L-1〜L-6 | `will-change` 12 個 / `srcset` / `theme-color` / JSON-LD `offers` / README 公開 / インラインスタイル | later | **later（維持）** |

### `fact_check` — 反論
<sub>2026-08-22T09:41:45+09:00</sub>

## fact_check R2 — 他 4 名の書き換え案の事実検証 + 争点の確定

R1 で挙げた 3 つの must について結論を確定させ、**他 4 名が提案した書き換え文言 25 件を 1 件ずつ実装で照合した**。
新たな事実誤認を作るものが **4 件**（うち 2 名が同じ算術ミスに収束）、逆に **現行 LP の誤りを正しく突いているもの が 2 件** ある。

冒頭に自分の R1 の訂正を 1 件置く（実測し直した結果、自分の数字が間違っていた）。

---

## 0. 【自己訂正】テストケース数は 562 ではなく **593**（実行結果）

R1 では `it(` / `test(` の静的 grep で「562」と書いたが、`.each` 展開分を数え落としていた。実際に走らせた:

```
$ npx vitest run
 Test Files  67 passed (67)
      Tests  593 passed (593)

$ npx playwright test --list
Total: 89 tests in 21 files
```

**実測値: ユニット・結合 593 / E2E 89 / 合計 682。**
`site/index.html:415` の `約 560 + 88` は **両方とも古い**（過小申告）。R1 では「丸め表記として正確 ✅」と判定したが、**⚠️ に格下げして訂正する**。

---

## 1. 【ブロッカー確定】must-1 ログイン記述 → **条件付きで残さず、削除する**（(B) を採る）

コーディネーターの求めに応じて明確に判定する。分岐は **「LP 公開までに本番 Worker へ OAuth 4 変数を供給できるか」の一点のみ**。

- **供給できる → (A)**。文言修正はゼロで良い（コードは正しく実装済み）。
- **供給できない / 判断がつかない → (B) 削除**。**「近日対応」「環境が整えば使えます」の類で条件付きに残すのは最悪手** であり、これは採らない。

**なぜ「条件付きで残す」が不可か（LP 自身の宣言と矛盾するため）**

`site/index.html:285` で LP はこう宣言している:

> これから作るものではなく、今このリンクを開けば触れるものだけを載せています。

ログインは「今このリンクを開いて」触れない（`/api/auth/login` → **404 実測**）。
つまりログイン記述を残すことは、単発の不正確さではなく **LP がページ内で自ら掲げた唯一の信頼原則を自壊させる**。
star 0・利用者の声ゼロの本 LP で、透明性は代替不能な唯一の資産なので、ここは削除側に倒すのが誠実。

**(B) を採る場合の確定文言（3 箇所）**

| 箇所 | 現行 | 置換 |
|---|---|---|
| `:385` タイル見出し | `ログインは任意` | `ログインの仕組みがない` |
| `:386-389` タイル本文 | `未ログインでも全機能が使えます。GitHub でログインしても…機能差は作っていません。` | `アカウントを作る導線そのものを置いていません。開いた瞬間から全機能が使えます。` |
| `:436` 制約 | （後述 §3 の確定文言に置換） | |
| `:448` FAQ | `不要です。開いた瞬間から全機能が使えます。GitHub でログインする導線もありますが、変わるのは API のレート枠だけで、使える機能に差はありません。` | `不要です。ログインの仕組み自体を置いていないので、開いた瞬間から全機能が使えます。` |

**🔴 (B) を採るならアプリ側にも 1 件 Issue が要る（LP スコープ外・別 Issue）**:
`src/ui/i18n/error-message.ts:70` は `rateLimitPrimaryLoginHint`（"GitHub にログインすると、使えるリクエストの上限が増えます。"）を
**`isAuthConfigured()` で出し分けていない**。レート上限に当たった利用者に対し、**存在しないログインを案内する** エラー画面が出る。
LP から消しても製品内に矛盾が残るので、(B) 採用時は同時に起票すること。

---

## 2. 他者の書き換え案の事実検証（本レビューでの自分の最重要タスク）

### ❌ 新たな事実誤認を作るもの（4 件・採用前に必ず直す）

**❌ NF-1. `copy_cvr M-2` の `648 ケース` と `visual_design VD-13` の `テスト 648 件` — 2 名が同じ誤りに収束している**

どちらも現行の `約 560 + 88` を **足し算して 648** としているが、`約 560` は丸めた値なので、**丸め値を足して確定値として提示すると誤差がそのまま「正確な数字」として固定される**。
§0 の実測どおり正解は **593 + 89 = 682**（`648` は 34 件の過小）。

**確定文言（両者の提案の意図＝「`<b>` は 1 つの数、`<span>` に内訳」は正しいので、数字だけ差し替える）**:
- `<b>` → `682 ケース`
- `<span>` → `ユニット・結合 593 / E2E 89（\`npm run check\` で一括実行）`

⚠️ **この 3 つの数値はコミットのたびに動く**。LP に確定値を焼き込むなら「公開直前に `npx vitest run` と `npx playwright test --list` を再実行して数字を合わせる」を作業手順に入れること。ドリフトを避けたいなら `約 680 ケース` + 内訳、でもよい。

---

**❌ NF-2. `copy_cvr S-8` の Gem Index の計算例 — パーセンタイルの単位が 100 倍間違っている**

提案文:
> 例: 被依存数は上位 1%（**0.01**）なのに star は上位 40%（**0.40**）なら、Gem Index は **−0.39**。

Ecosyste.ms の `rankings` は **0〜100 のパーセンタイル** であり、0〜1 ではない。
- `tools/generate_gem_digest.mjs:6-7` 「値域 **0〜100**・0 が最上位」
- 同 `:100` `if (depRank < 0 || depRank > 100 || starRank < 0 || starRank > 100) return null`
- `src/domain/model/gem-index.ts` `assertRank` も 0〜100 を強制

この単位で計算すると `1 − 40 = **−39**` であり、**提案の −0.39 は 100 倍ズレている**。
さらに **−39 は実データに存在しない値** でもある。実候補プール 294 件の分布（`public/data/daily-digest.json` から算出）:

```
min −6.734 / 下位 10% −2.709 / 中央値 −0.955 / max +0.003
最上位: karma-jasmine-html-reporter −6.734（dep 15,015 / star 38）
```

例示のために架空の極端値を置くと、読者が実際に画面で見る値（−6 〜 0）と桁が合わず、かえって混乱する。

**確定文言案（実データの最上位帯に合わせた）**:
> 順位はどちらも 0〜100 のパーセンタイル（0 が最上位）です。例えば被依存数が上位 0.1（＝上位 0.1%）で star が上位 7（＝上位 7%）なら Gem Index は −6.9。実際のデータでもこのあたりが最上位帯です。

---

**❌ NF-3. `copy_cvr S-10` の OGP 文言 — 研究の実例を「毎日提示されるもの」に混ぜている**

提案文:
> `star ではなく被依存数から GitHub を探す検索ツール。**25 star なのに 11 万パッケージから依存されている OSS を、毎日 5 件。**登録不要・無料・MIT。`

2 つの事実が接合されているが、この 2 つは無関係:
1. `25 star / 111,000+` は **He et al. 論文まわりの調査で引かれた `debug_inspector` という 1 つの実例**（`docs/01_research/market/20260817-github-repo-search-competitive-analysis.md:78`）。しかも **RubyGems** のパッケージ。
2. 「今日の Gem」の候補プールは **npm 単独**（`tools/generate_gem_digest.mjs:23` が `registries/**npmjs.org**/packages` を叩く）。**`debug_inspector` はそもそも候補に入りえない。**

加えて出典の単位は「111,000+ の **OSS プロジェクト**」であって「11 万 **パッケージ**」ではない。
この 1 行は「毎日そのクラスの発見が 5 件ある」と読め、**LP 全体で唯一の明確な誇大表示になる**。OGP はシェアで独り歩きするので危険度も最大。

**確定文言案（実際に配信中のデータから採った・検証可能）**:
> `star 111 なのに 26,633 パッケージから使われている——そんな OSS を毎日 5 件。star ではなく被依存数から GitHub を探す検索ツール。登録不要・無料・MIT。`

（`rollup-plugin-peer-deps-external` = dep 26,633 / star 111。`public/data/daily-digest.json` 実値で、既に `shot-digest.webp` にも写っている。ただし §NF-4 の注意書きも読むこと。）

---

**❌ NF-4. `visual_design VD-3` の「画像をやめて `利用パッケージ数 26,633 / star 111` を HTML テキストのミニ表で組む」— 数値は正しいが、鮮度が固定される**

数値自体は ✅ 実データ一致（上記）。ただし **この値は Ecosyste.ms のスナップショット由来で、バッチ再生成のたびに変わる**（`ADR 0014` 未解決事項 8 は、銘柄ごとにクロール時点が **最大 2.7 年** ばらつくとまで書いている）。
画像なら「その時の画面」として読めるが、**HTML テキストにすると LP 自身の断定的な主張に格上げされる** ため、更新されない限りいずれ嘘になる。

**採用するなら注記を必須にする**: `（2026-08-21 時点の一例）` を併記する、または VD-3 の代替案（上位 1〜2 件の拡大トリミング画像）を採る。NF-3 の OGP 案も同じ理由で「一例」であることが読み取れる語（`そんな OSS を`）を必ず残すこと。

---

### ✅ 事実として正しく、採用してよい書き換え案

| # | 提案 | 判定・根拠 |
|---|---|---|
| `copy_cvr M-3` | 「研究で検出された偽 star の数」→「研究が **「偽の疑いあり」** と判定した star 数」 | ✅ **正しい訂正**。論文名が *Six Million (**Suspected**) Fake Stars* であり、現行 LP は "suspected" を落としている。**自分の R1 はここを ✅ と判定したが、copy_cvr の指摘のほうが精密。譲歩して should → must 相当に引き上げる** |
| `copy_cvr M-3` 後半 | `25 star` / `111,000+` の説明に `debug_inspector` の名前を入れる | ✅ 出典（同 `:78`）と一致。検証可能性が上がる。ただし **S-3 の FAQ（エコシステム）と必ず同時に出す** こと（Ruby の例を出しつつ「今日の Gem」が npm 限定なのを黙っていると、次の疑問が宙に浮く） |
| `copy_cvr S-5` の後半 | 「要求する権限は公開情報の読み取りのみで、リポジトリへの書き込み権限は要求しません」 | ✅ **事実**。`src/infrastructure/github/oauth.ts:63-75` の `buildAuthorizeUrl` は **`scope` パラメータを付けない**（コメントにも「no-scope」と明記）。no-scope の OAuth トークンは公開情報の読み取りのみ。**ただし §1 で (B) を採るなら S-5 ごと不要になる** |
| `copy_cvr S-2` | 「収益化の予定はなく、広告を入れることもありません」 | ✅ 裏あり。`docs/00_concept/lean-canvas.md:52` ⑥ 収益の流れ **「なし（収益化を目的としない）」🔒 決定事項 `D-3`**、`inception-deck.md:130` も課金・サブスクを「やらないこと」に置いている。**表現だけ「現時点で収益化の予定はありません」と時点を切ることを推奨**（将来の約束として読ませない） |
| `copy_cvr M-1(b)` | チップ先頭に「今日の Gem を見る」→ `.../ja`（キーワードなし） | ✅ 正しい。`app/[locale]/page.tsx:283` はキーワード未入力時のみダイジェストを生成する |
| `copy_cvr S-11` | `約 560 + 88` から `docs/04_development/testing-strategy.md` へリンク | ✅ ファイル実在（16KB）。リンク先として妥当 |
| `web_quality L-4` | JSON-LD に `offers: { price: "0" }` | ✅ 事実に即する（無料・収益化なし・`D-3`）。`aggregateRating` を入れない判断も正しい |
| `a11y_wcag M-2` | `Open the tool (English)` に `lang="en"` | ✅ 事実問題なし。`/en` は実在（`messages/en.json` + `[locale]` ルーティング） |

---

### ✅ **現行 LP の誤りを正しく突いている指摘（自分の R1 が見落としていた・譲歩）**

**`copy_cvr S-7`「混み合うと待たされます」は起きることを言い切れていない → 「一時的に失敗することがあります」**

**copy_cvr が正しい。自分の R1 はここを拾えていなかったので譲歩し、severity を should → must に上げる。**
実装上、レート枠に当たったときに起きるのは **待機ではなくエラー表示**:

- 二次制限: `src/composition/rate-limit.ts` が `RateLimitExceededError('rateLimitSecondary')` を throw
  → `messages/ja.json` 「リクエストが集中しています。**{retryAfterSeconds} 秒後に再度お試しください。**」
- 一次制限: 「リクエストの上限に達しました。**{resetAt} 以降に再度お試しください。**」

いずれも `ErrorNotice` に出る **失敗** であり、キューイングも自動リトライもしない。「待たされます」は
「待てば同じリクエストが通る」と読めるため、実挙動と食い違う。§3 の確定文言に反映した。

**`copy_cvr M-1`（ヒーローの約束と実体のズレ）も譲歩して must に同意する。**
`src/ui/repository-list.tsx:103-125` の実測どおり、検索結果に出るのは **リポジトリ名 / 説明 / 主要言語 / star / 最終更新 / トピック（上位 5）** だけで **被依存数は 1 つも出ない**。
一方ヒーロー（`:103-108`）は「被依存数 …… を手がかりに GitHub を探す検索ツールです」と言い切っている。
被依存数が効くのは「今日の Gem」だけであり（LP 自身も `:429` でそう認めている）、**ヒーローだけが過大**。M-1(a) の書き換えを支持する。

> ⚠️ ただし **`visual_design VD-16` の書き換え案（ダッシュを 2 文に割る案）は M-1(a) と衝突する**。
> VD-16 の文は「被依存数を手がかりに GitHub を探す検索ツール」という **誤った主張のほうを温存する**。
> **採用順序を確定させる: 本文は copy_cvr M-1(a) を採り、VD-16 は「`——` を使わず 2 文に割る」という書式指示としてのみ M-1(a) に適用する。**

---

## 3. 【確定】「30 リクエスト / 分」の LP 制約セクション文言

**推奨: 数値を書かない。** 理由は 2 つで、どちらも実測に基づく。

1. **前提が未確認**。30 req/分は「GitHub App の installation token で認証できている場合」の値（`docs/02_requirements/prd.md:122`）。
   OAuth 4 変数が本番未供給と判明した以上、`GITHUB_APP_*` 3 変数（`installation-token.ts:35-37`）の供給有無も外部から確認できない。
   未供給なら `:86-92` の設計どおり **未認証（10 req/分）で動く** ので、LP の数値は 3 倍の誇張になる。
2. **数値の主語が 2 つあり読者が取り違える**。実際に検索を弾いているのは `wrangler.jsonc:12`（`limit: 60, period: 60`）＝
   **同一 IP あたり 60 リクエスト / 分** の自前間引きで、30 req/分は **上流 GitHub 側の枠**。LP は前者を説明したいのに後者の数字を出している。

**確定文言（`site/index.html:436` の置換・§1(B) と S-7 の訂正を織り込み済み）**:

> 共有の API レート枠で動いています。混み合うと検索が一時的に失敗することがあります。少し時間をおいてから試してください。

**（例外）本番の `GITHUB_APP_CLIENT_ID` / `_INSTALLATION_ID` / `_PRIVATE_KEY_PKCS8` の供給が確認できた場合のみ**、数値を戻してよい:

> 共有の API レート枠（GitHub 検索 API の 30 リクエスト / 分）で動いています。混み合うと検索が一時的に失敗することがあります。少し時間をおいてから試してください。

---

## 4. 事実に反する前提に立っている指摘（名指しで否定）

**🔴 `copy_cvr` のダークパターン / 誇張チェック結論「『全機能が使えます』は実装と一致（ログインはレート枠のみ）✓」は誤り。**
本番実機ではログイン導線が描画されず `/api/auth/login` は **404**（R1 実測）。
同じ結論の末尾「**この 2 つ（M-1・M-3）を直せば、このページは『誇張ゼロ』と言い切れる状態になる**」も、したがって成立しない。
**「誇張ゼロ」を名乗れるのは、§1 のログイン記述と §3 のレート枠数値を処理した後**。この判定文が残ったまま公開判断に使われるのが一番危ないので明示的に否定する。

**🟡 `copy_cvr S-3` は「事実確認後に確定」と留保しているので誤りではない。ここで確定値を渡す。**

> **対応しているエコシステムは何ですか？**
> キーワード検索は GitHub 全体が対象で、言語もエコシステムも問いません。一方「今日の Gem」の被依存数は、いまのところ **npm（npmjs.org）のパッケージだけ** を対象にしています。

根拠: 検索側は `is:public` 修飾子のみ付与で言語制限なし（`github-repository-query.ts:29`）。ダイジェスト側は
`tools/generate_gem_digest.mjs:23` が `https://packages.ecosyste.ms/api/v1/registries/**npmjs.org**/packages` 固定。

**🟡 `copy_cvr S-6`（制約リストから「Ecosyste.ms（CC BY-SA 4.0）」を外して 3 項目に絞る）は、ライセンス上そのまま実行してよい。**
CC BY-SA 4.0 の帰属表示義務は **フッター（`:576-580`）に残る** ため、制約セクションから外しても義務違反にならない。
🔴 ただし **フッターの帰属表示は絶対に削らないこと**（アプリ本体も `src/ui/attribution-notice.tsx` で画面内に出している）。
関連して **later**: リポジトリの `NOTICE` には Ecosyste.ms（CC BY-SA 4.0）と Geist（SIL OFL 1.1）の項目が無い（R1 later-1）。LP のほうが厚い状態なので、別 Issue で追随させたい。

**🟢 `a11y_wcag` / `web_quality` の指摘に、事実に反する前提のものは無かった。**
特に `web_quality M-2`（`hero-in` の `opacity: 0` が LCP 候補から除外される）は、`styles.css:1022` の自リポジトリ規律
「🔴 opacity は動かさない」と `hero-in` の実装が食い違っているという **内部矛盾の指摘として正しい**。事実面から追認する。

---

## 5. 公開前ゲート（fact_check としての最終条件）

- [ ] **§1**: OAuth 4 変数を供給する (A)、または 3 箇所を削除する (B) のどちらかを確定。(B) なら `error-message.ts:70` の Issue も起票
- [ ] **§3**: レート枠の文言を確定版に置換（数値は原則書かない）
- [ ] **NF-1**: テスト数を `682`（593 / 89）に修正。`648` では公開しない
- [ ] **NF-2**: Gem Index の例を入れるなら 0〜100 スケールで書く（`−0.39` では公開しない）
- [ ] **NF-3**: OGP に `debug_inspector` の数字を「毎日 5 件」と接続しない
- [ ] **M-3**: 偽 star に「疑い」を戻す
- [ ] **NF-4**: スナップショット数値を HTML に焼くなら時点注記を併記
- [ ] **S-3**: エコシステム FAQ を §4 の確定文言で追加（`debug_inspector` を前に出すなら同時必須）

## ラウンド 3

### `lead` — 合意
<sub>2026-08-22T09:44:42+09:00</sub>

## lead / 合意点と対立の決着

2 ラウンドで **round 1 の指摘 60 件超 → 実施 41 件（must 10 / should 24 / 安価な later 7）** に収束した。
議論で否定・統合・降格されたものは実施しない。

### 決着した主要対立

| 争点 | 決着 | 決め手 |
|---|---|---|
| `hero-in` の `opacity: 0` | **keyframes から `opacity` を削除し `translateY` のみにする** | web_quality の実測（LCP がヘッダーリンク 2,916px² に落ち、h1 と 660,137px² のヒーロー画像が候補から永久除外）。visual_design が「視覚的損失ゼロ、むしろ最大 0.76 秒の白画面を作っている側」と全面譲歩。a11y は中立だが賛成（拡大鏡ユーザーに実利） |
| ダークで白いスクショが浮く | **ブラウザモックをダーク時もライト固定にし、1px の明るいリングで額装する**（撮り直しはしない） | アプリ本体にテーマ切替が無い以上、ダーク版スクショは「実ユーザーが到達できない画面の捏造」（visual_design が自案を撤回）。fact_check の must-1 と同じ罪になる |
| タイル内スクショが読めない | **上位 1 件の拡大トリミング画像に差し替え、数字は HTML テキストにも二重化**（時点注記を必須） | 「主張が見た目なら画像、数字ならテキスト」（copy_cvr）+「画面を消すのは証拠を捨てる交換」（visual_design）の両取り。fact_check がスナップショット値の鮮度固定リスクを指摘し、時点注記を条件に承認 |
| 本番で使えないログイン | **LP から 3 箇所とも削除する（(B)）。条件付きで残さない** | LP 自身が「今このリンクを開けば触れるものだけ」と宣言しており、条件付き記述はその原則を自壊させる（fact_check）。copy_cvr は「持っていない摩擦をわざわざ紹介して否定するのは CVR 的にも損」として同意 |
| レート枠「30 リクエスト / 分」 | **数値を書かない** | 認証前提の値で本番の `GITHUB_APP_*` 供給が外部から確認できず、未供給なら 3 倍の誇張になる。かつ体感の直接原因は別枠（同一 IP 60/分）で主語が 2 つ（fact_check）。「その数字は誰の意思決定も変えない」（copy_cvr） |
| 900px 未満でページ内ナビが消える | **フッター `nav` に `#why` / `#how` / `#trust` を足すだけ**。ヘッダーの chip 列化・`details` ハンバーガーは採らない | SC 1.4.10 は導線の位置を規定しない（a11y が自案を撤回し should → later へ格下げ）。ヘッダーへの追加は fold をさらに埋める（visual_design / copy_cvr） |
| `font-size: 16px` の rem 化 | **文字サイズだけ rem 化する。`--header-h` は px のまま + 短いビューポートで sticky を降ろす** | `--header-h` の rem 化は 200% 環境で 120px ヘッダーになり、実測で適合済みの SC 2.4.11 を自分で壊す（a11y が自案を撤回） |
| `.formula-expr` の横スクロール | **`white-space: nowrap` と `overflow-x: auto` の 2 宣言を削除する**（`tabindex="0"` は付けない） | SC 2.1.1 と VD-17 が同時に解消し、「読める」状態になる（web_quality）。`tabindex` は横スクロールを残すだけで読めるようにならない（copy_cvr） |
| テスト件数 | **682 ケース（ユニット・結合 593 / E2E 89）** | copy_cvr と visual_design が独立に丸め値を足して `648` に収束していたのを fact_check が実行結果で否定。lead 側でも公開前に再実行して確認する |

### 実施しないと決めたもの（議論で否定された指摘）

- ヘッダーナビの chip 列化 / `details` ハンバーガー（a11y 自身が撤回）
- `--header-h` / `.btn` / `.chip` の `min-height` の rem 化（適合済み SC を壊す）
- `.sr-only` の削除（a11y 追補で使う可能性が高く、削除の実利がほぼない）
- `.assurance` の `✓` を SVG に置換（`content: '✓' / ''` で見た目を変えずに解決）
- 出典リンクの下線細線化（SC 1.4.1 の唯一の非色手がかり・a11y が否定）
- ダーク版スクリーンショットの撮り直し（存在しない UI 状態の捏造）
- カード枚数を減らす方向のリデザイン（測れる CVR を測れない印象と交換する取引）
- JSON-LD の `offers`（収益化しない立て付けに商取引の語彙を持ち込む方向。害はないが優先度最下位）
- ヒーローの glow 強化（適合済みのコントラスト計算を装飾のために崩す順番ではない）

### LP スコープ外として別 Issue に切るもの

1. `src/ui/i18n/error-message.ts` の `rateLimitPrimaryLoginHint` が `isAuthConfigured()` で出し分けられておらず、**存在しないログインを案内するエラー画面が出る**
2. リポジトリの `NOTICE` に Ecosyste.ms（CC BY-SA 4.0）と Geist（SIL OFL 1.1）の項目が無い
3. 本番 Worker への OAuth 4 変数の供給（ユーザー権限が必要・A-6）
4. スクリーンショットの `srcset` 対応

### `lead` — 判定
<sub>2026-08-22T09:45:53+09:00</sub>

{
  "fixes": [
    { "id": "F-1", "severity": "must", "issue": "E", "problem": "本番でログイン導線が無効（/api/auth/login が 404・UI 非表示）なのに LP が 3 箇所で「ログインでレート枠が変わる」と書いている", "fix": "機能タイルを「渡すものが何もない」に置換し、制約リストと FAQ からログインへの言及を削除する（言及先を作らない）", "file": "site/index.html" },
    { "id": "F-2", "severity": "must", "issue": "E", "problem": "「タップ領域は 44px 以上」は主要導線だけの基準（AA は 24px・44px は AAA の 2.5.5）", "fix": "「主要導線のタップ領域は 44px、入力欄は 16px 以上」に訂正", "file": "site/index.html" },
    { "id": "F-3", "severity": "must", "issue": "E", "problem": "テスト件数「約 560 + 88」が実測とずれ、かつ和として読めない", "fix": "「682 ケース」+ 内訳「ユニット・結合 593 / E2E 89」。公開直前に実行して再確認する", "file": "site/index.html" },
    { "id": "F-4", "severity": "must", "issue": "E", "problem": "「研究で検出された偽 star」は出典（Six Million (Suspected) Fake Stars）より強く断定している", "fix": "「研究が「偽の疑いあり」と判定した star 数」に変更", "file": "site/index.html" },
    { "id": "F-5", "severity": "must", "issue": "E", "problem": "「混み合うと待たされます」は実装と食い違う（キューイングせずエラー表示になる）", "fix": "「混み合うと検索が一時的に失敗することがあります」に変更し、レート枠の数値は書かない", "file": "site/index.html" },
    { "id": "F-6", "severity": "must", "issue": "A", "problem": "ヒーローが「被依存数を手がかりに GitHub を探す」と言い切るが、キーワード検索に被依存数は出ない（効くのは「今日の Gem」だけ）", "fix": "リード文を実像に合わせ、二重ダッシュをやめて 2 文に割る", "file": "site/index.html" },
    { "id": "W-1", "severity": "must", "issue": "D", "problem": "hero-in の opacity: 0 により h1 とヒーロー画像が LCP 候補から永久除外され、最大 0.76 秒の白画面ができる", "fix": "keyframes から opacity を削除し translateY のみにする", "file": "site/assets/styles.css" },
    { "id": "A-1", "severity": "must", "issue": "B", "problem": ".formula-expr がキーボード操作できないスクロール領域になる（SC 2.1.1）。320px で 133px はみ出す", "fix": "white-space: nowrap と overflow-x: auto を削除して折り返す", "file": "site/assets/styles.css" },
    { "id": "A-2", "severity": "must", "issue": "B", "problem": "英語の句に lang=en が無い（SC 3.1.2）", "fix": "Open the tool (English) に lang=\"en\"、論文タイトルを span lang=\"en\" で囲う", "file": "site/index.html" },
    { "id": "VD-1", "severity": "must", "issue": "A", "problem": "ダークでライト版スクリーンショット 3 枚が白く浮き、ページ最大面積が背景と真逆の明度になる", "fix": "ダーク時もブラウザモック・図版枠をライト固定にし、1px の明るいリングで額装する", "file": "site/assets/styles.css" },
    { "id": "VD-2", "severity": "must", "issue": "A", "problem": "bento 1 行目の span-2 タイルに約 100px の空洞ができる", "fix": "図版を拡大トリミングに差し替え、テキスト行を足して行高を埋める", "file": "site/index.html" },
    { "id": "VD-3", "severity": "must", "issue": "A", "problem": "タイル内スクリーンショットの文字が実効 6〜7px で読めず、唯一の実データが証明にならない", "fix": "上位 1 件の拡大トリミング画像に差し替え、数字は HTML テキストにも二重化（時点注記を併記）", "file": "site/assets/img/shot-digest.webp" },
    { "id": "VD-4", "severity": "should", "issue": "A", "problem": "rotateX(3deg) でヒーロー画像の左端だけ 40px 内側にずれ、縦グリッドが崩れる", "fix": "rotateX を外して正面に置き、影で浮かせる", "file": "site/assets/styles.css" },
    { "id": "VD-5", "severity": "should", "issue": "A", "problem": "対比カード 2 枚で比較対象の数字のベースラインが 26px ずれる", "fix": "カードを flex 縦積みにし stat-row を margin-top: auto で下端揃えにする", "file": "site/assets/styles.css" },
    { "id": "VD-6", "severity": "should", "issue": "A", "problem": "良い指標と悪い指標の数字が同色で、読み比べないと意味が取れない", "fix": ".compare-card.is-good .stat b を accent 色にする", "file": "site/assets/styles.css" },
    { "id": "VD-8", "severity": "should", "issue": "A", "problem": "モバイルで CTA 2 本の幅が不揃い", "fix": "520px 以下で .hero-actions .btn を width: 100% にする", "file": "site/assets/styles.css" },
    { "id": "VD-9", "severity": "should", "issue": "A", "problem": "縦積みになったモバイルで対比の矢印が横向きのまま", "fix": "819px 以下で .compare-arrow を 90deg 回転させる", "file": "site/assets/styles.css" },
    { "id": "VD-10", "severity": "should", "issue": "A", "problem": ".limits の破線枠だけが意匠から浮き、誠実さの表明が警告に見える", "fix": "実線 hairline + 面の差に変える", "file": "site/assets/styles.css" },
    { "id": "VD-11", "severity": "should", "issue": "A", "problem": ".limits の行長が無制限で全角 60 字近くになる", "fix": "max-width: 76ch を付ける", "file": "site/assets/styles.css" },
    { "id": "VD-12", "severity": "should", "issue": "A", "problem": "出典注記のリンクが長すぎて青い帯になり、注記なのに最も強い視覚要素になっている", "fix": "リンク範囲を書名だけに縮める（A-2 の lang 指定と同じ編集で行う）", "file": "site/index.html" },
    { "id": "VD-15", "severity": "should", "issue": "A", "problem": "モバイルのファーストビューにプロダクト画面が 1px も入らない", "fix": "保証行を 3 項目に絞り、キーワード例をスクリーンショットの下へ移す。「今日の Gem を見る」だけ fold 内に残す", "file": "site/index.html" },
    { "id": "VD-20", "severity": "should", "issue": "A", "problem": "FAQ 6 件が同一の帯で、回答の存在自体が見えない", "fix": "1 問目（差し替え後の「GitHub の検索と何が違いますか？」）を open にする", "file": "site/index.html" },
    { "id": "A-3", "severity": "should", "issue": "B", "problem": "900px 未満で #why / #how / #trust への到達手段が消える（SC 1.4.10）", "fix": "フッター nav に 3 アンカーを追加する", "file": "site/index.html" },
    { "id": "A-4", "severity": "should", "issue": "B", "problem": "font-size が px 固定でユーザーの既定フォントサイズ設定が効かず、見出しの rem と混在している", "fix": "文字サイズだけ rem 化する。--header-h は px のまま、height を min-height に変え、短いビューポートで sticky を降ろす", "file": "site/assets/styles.css" },
    { "id": "A-5", "severity": "should", "issue": "B", "problem": "chip（リンク）の枠が 1.39:1 で、操作可能であることを示す唯一の視覚情報が SC 1.4.11 未達", "fix": "chip の border-color を --border にする", "file": "site/assets/styles.css" },
    { "id": "A-6", "severity": "should", "issue": "B", "problem": "404.html の主見出しが h2 から始まる", "fix": "h1 に変更し .final-cta h1 のスタイルを足す", "file": "site/404.html" },
    { "id": "A-7", "severity": "should", "issue": "B", "problem": "装飾の .url-pill が読み上げられ、.assurance の ✓ が「チェックマーク」と読まれる", "fix": ".url-pill に aria-hidden、::before に content: '✓' / '' を使う", "file": "site/index.html" },
    { "id": "W-2", "severity": "should", "issue": "D", "problem": "color-mix() 非対応ブラウザで sticky ヘッダーの背景が完全透明になる", "fix": "直前に background: var(--bg) のフォールバックを 1 行足す（-webkit-backdrop-filter も同時に足す）", "file": "site/assets/styles.css" },
    { "id": "W-4", "severity": "should", "issue": "D", "problem": "README が 404.html の絶対パス例外に触れておらず、ローカルでは 404 が無スタイルになることも書かれていない", "fix": "README の「設計上の約束」と「ローカル確認」に注記を足す", "file": "site/README.md" },
    { "id": "F-7", "severity": "should", "issue": "E", "problem": "「日次スナップショット」は日次生成が保証されていない（しきい値 48 時間の自己修復）", "fix": "「5 件は毎日入れ替わる」と「元データは定期的に取り直したスナップショット」を分けて書く", "file": "site/index.html" },
    { "id": "F-8", "severity": "should", "issue": "E", "problem": "「今日の Gem」の選出が 3 段階（上位 60 件の母集団 → 日付順序で 5 件 → Gem Index 順に整列）なのに式だけを見せており「上位 5 件」と誤読される", "fix": "式の下に選び方 1 文と、0〜100 パーセンタイルでの具体例を足す", "file": "site/index.html" },
    { "id": "F-9", "severity": "should", "issue": "C", "problem": "「対応エコシステム」「いつまで使えるのか」という離脱理由が FAQ で潰せていない", "fix": "FAQ を 2 問追加（今日の Gem は npm 限定 / 収益化しない・止めても MIT で残る）", "file": "site/index.html" },
    { "id": "F-10", "severity": "should", "issue": "C", "problem": "FAQ の 1 問目がヒーローで既出の答えになっている", "fix": "1 問目を「GitHub の検索と何が違いますか？」に差し替える", "file": "site/index.html" },
    { "id": "F-11", "severity": "should", "issue": "C", "problem": "同一導線の CTA ラベルが 3 通りある", "fix": "「gem-hunter を開く」に統一（フッターのみ言語併記）", "file": "site/index.html" },
    { "id": "F-12", "severity": "should", "issue": "C", "problem": "対比カードの 25 star / 111,000+ が何のリポジトリか本文から分からない", "fix": "debug_inspector の名前をカード内に出す（エコシステム FAQ と同時に入れる）", "file": "site/index.html" },
    { "id": "F-13", "severity": "should", "issue": "C", "problem": "制約リストの 4 項目目がデータ出典でありフッターと重複している", "fix": "制約から外して 3 項目に絞る（フッターの帰属表示は維持する）", "file": "site/index.html" },
    { "id": "F-14", "severity": "should", "issue": "C", "problem": "og:description が機能説明どまりでシェアされない", "fix": "実配信データ由来の具体値に置き換える（研究の実例と接合しない）", "file": "site/index.html" },
    { "id": "F-15", "severity": "should", "issue": "C", "problem": "検証可能な数字（ADR 本数・テスト数）にリンクが無く自己申告に見える", "fix": "docs/adr/ と testing-strategy.md へリンクする", "file": "site/index.html" },
    { "id": "F-16", "severity": "should", "issue": "C", "problem": "保証行の項目がヒーロー 4 個・最終 CTA 3 個で不一致", "fix": "最終 CTA にも MIT ライセンスを足す", "file": "site/index.html" },
    { "id": "F-17", "severity": "should", "issue": "C", "problem": "「今このリンクを開けば」の指示対象が不明", "fix": "「いま開いて触れるものだけを載せています」に変更", "file": "site/index.html" },
    { "id": "W-6", "severity": "later", "issue": "D", "problem": "will-change: transform が 12 要素に常時付き、モバイルの GPU メモリを占有する", "fix": "削除する", "file": "site/assets/styles.css" },
    { "id": "F-18", "severity": "later", "issue": "D", "problem": "インラインスタイルが 3 箇所ある", "fix": "CSS に寄せる", "file": "site/index.html" }
  ],
  "critical": [
    "本番 Worker に OAuth 4 変数が供給されていないため、アプリ側のログイン機能そのものが利用できない状態にある（LP からは記述を削除して整合させたが、製品の欠落は残る）",
    "src/ui/i18n/error-message.ts の rateLimitPrimaryLoginHint が isAuthConfigured() で出し分けられておらず、レート上限時に存在しないログインを案内するエラー画面が出る（LP スコープ外・別 Issue）"
  ],
  "open_questions": [
    "本番 Worker へ OAuth 4 変数（GITHUB_OAUTH_CLIENT_ID / _SECRET / _CALLBACK_URL / SESSION_ENCRYPTION_KEY）を供給するか。供給する場合は LP のログイン記述を戻せる（A-6・ユーザー権限が必要）"
  ]
}
