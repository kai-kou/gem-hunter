<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: GitHub Pages 用ランディングページ（site/）を公開前に多角レビューする

- 議題ID: `lp_github_pages_review`
- 論点: ユーザー指示: 『GitHub Pages を利用して本ツールのランディングページを実装・公開する。LP の最新トレンド / UI・UX / ベストプラクティス / マーケティング戦術を詳細にリサーチして設計する。CTA の優先順位は ① 本番ツール ② GitHub リポジトリ。ファーストビューに本ツールのスナップショットを含める。ツールに合わせたデザインにする。実装後に視覚的なものを含めた多角レビューを行いブラッシュアップしてからユーザー確認を求める。』。実装済みの成果物: site/index.html（単一ページ・ページ内 JavaScript ゼロ）、site/assets/styles.css、site/404.html、site/assets/img/*（アプリ実画面のスクリーンショット + OGP 1200x630）、site/assets/fonts/geist-latin.woff2（自前配信・SIL OFL）。公開方式は gh-pages ブランチ（GitHub Actions は本リポジトリで制限中のため CI デプロイは採らない）。公開 URL 予定は https://kai-kou.github.io/gem-hunter/ 。本番ツールは https://gem-hunter.kinamocchi-tech.workers.dev/ja 。ローカル配信中: http://127.0.0.1:8098/ 。レンダリング済みスクリーンショットは /tmp/claude-0/-home-user-gem-hunter/d2e5f9c2-513b-5347-bdb5-4acca9ed545d/scratchpad/lp/ に desktop-light-full.png / desktop-dark-full.png / mobile-light-full.png / fold.png / sec-why.png / sec-how.png / sec-features.png / sec-trust.png / sec-faq.png がある。争点は少なくとも次の 5 つ: A) ファーストビューの説得力（見出し・サブコピー・CTA・スクリーンショットの見せ方が 2026 年の LP トレンドと CVR の定石に照らして妥当か。過剰・不足はどこか） B) アクセシビリティ（WCAG 2.2 AA。ランドマーク・見出し階層・フォーカス可視・ターゲットサイズ 2.5.8・sticky ヘッダーと 2.4.11・コントラスト（ライト/ダーク両方）・装飾画像の alt・details/summary の扱い） C) コピーとマーケティング（開発者向けの誇張しないトーン・信頼の代替（star 0・ユーザーの声なし）・限界の明示・シェアされる 1 行・FAQ の異議処理が足りているか） D) 技術品質（Core Web Vitals・画像戦略・フォント・OGP/canonical の絶対 URL・構造化データの妥当性・GitHub Pages サブパス配信での相対パス事故・404.html・.nojekyll） E) 事実の正確性（実装していない機能を書いていないか。数値・引用・出典の裏が取れているか。ダークモード切替やフィルタ機能など存在しない機能に言及していないか）。
- 参加者: `visual_design`, `a11y_wcag`, `copy_cvr`, `web_quality`, `fact_check`
- 投稿数: 5
- 更新: 2026-08-22T09:33:35+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

## ラウンド 1

### `copy_cvr` — 主張
<sub>2026-08-22T09:24:46+09:00</sub>

## copy_cvr / Round 1 — コピー & コンバージョン観点

前提の再確認: star 0・利用者の声ゼロ。よって **信頼の原資は「第三者の研究データ」「実装の透明性」「制約の先出し」の 3 つだけ**。現状の LP はこの 3 本柱を既に押さえており、土台は good。以下は「その柱を弱めている箇所」と「離脱理由が潰せていない箇所」に絞る。

---

### must（誇張・不整合・数字が意味を成していない）

**M-1. ヒーローの約束と、最初のクリック先の体験がズレている（最大の離脱リスク）**

h1 + リードは「**被依存数を手がかりに GitHub を探す**」と約束するが、サンプルチップ（`react` / `postgres` / `cli` …）を押して着地するのはキーワード検索であり、そこに被依存数は出ない（検索結果のカラムは star / 更新日 / トピック）。FAQ と制約セクションでは正直に「キーワード検索そのものは GitHub の検索結果です」と認めているぶん、**ヒーローだけが過大**になっている。開発者は最初のクリックで「これ普通の GitHub 検索では？」と判断して離脱する。

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
→ 5 件全部を写した俯瞰画像をやめ、**上位 1〜2 件だけを拡大トリミングした画像**に差し替える。もしくは画像をやめて「利用パッケージ数 26,633 / star 111」を HTML テキストのミニ表で組む（テキストなら縮小に強く、ダーク対応も VD-1 ごと解決する）。

---

### should

**VD-4 ヒーローのスクショだけ左端が約 40px 内側にずれ、縦のグリッドが崩れている**
`fold.png` で h1・リード・CTA・チップスはすべて x≈180 に揃っているのに、`.browser` の左端だけ x≈222 から始まる。`transform: rotateX(3deg)` + `perspective: 1600px` の透視縮小で上部が内側に寄るため。3deg は「意図した傾き」としては弱すぎて、ただ左右の整列が狂って見えるだけになっている。
→ `rotateX` を 0 にして正面に置き、代わりに `--shadow` を一段強めて浮かせる。傾けるなら 6〜8deg + `transform-origin: top center` で明確に演出として立てる。中間の 3deg が一番損。

**VD-5 対比セクションの 2 枚のカードで、数字のベースラインが揃っていない**
`sec-why.png` の左カードは本文 2 行で `stat-row` が y≈506、右カードは 3 行で y≈532。**比較させるための並置**なのに、比べたい数字（約 600 万 / 25 star）が 26px ずれて置かれている。
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
3. **アプリ本体と同じ oklch トークンを使っている**ので、ヒーローの accent 青とスクショの中の UI の青が完全に一致しており、LP → ツールの遷移に色の断絶がない（`fold.png` で確認できる）。

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
`src/ui/login-link.tsx` も表示切替のみで機能差ゼロ）。**壊れているのは LP ではなく本番の env 供給**だが、
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
未設定なら同ファイル `:86-92` のとおり `null` を返して**未認証（10 req/分）で動く**ため、LP の数値は 3 倍の誇張になる。

あわせて **数値の主語が 2 つある点も紛らわしい**。実際に「混み合うと待たされる」直接の原因は
`wrangler.jsonc:12`（`ratelimits: { limit: 60, period: 60 }`）＝**同一 IP あたり 60 リクエスト / 分**の
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
  つまり**仕様上 2 日古くても正常**であり「日次生成」ではない。
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
2. shortlist を `SHA-256(日付:packageName)` で**決定論的シャッフル**し先頭 5 件を選ぶ
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
- **later-3**: 「今日の Gem」の**初回訪問時は 5 件すべてに「新着」が付き**「初回として全件を表示しています」の注記が出る
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

> **相対パス**で参照する（GitHub Pages のサブパス配信で壊れないため）。OGP と canonical だけは仕様上 **絶対 URL**

と書いているが、`404.html` は 8 / 9 / 16 / 25 行が `/gem-hunter/...` の絶対パス。README がこの例外を書いていない。

実測（README の手順どおり `python3 -m http.server 8098 --directory site` で `/404.html` を開く）:

```
404 http://127.0.0.1:8098/gem-hunter/assets/styles.css
404 http://127.0.0.1:8098/gem-hunter/assets/img/gem.webp
→ .btn-primary の border-radius = 0px（完全に無スタイル）
```

**絶対パスにした判断そのものは妥当**（後述 OK-6）。問題は ① README にその例外が書かれていない ② ローカルでは 404 ページの見た目を検証できないのに、その注記が無いこと。README の「設計上の約束」に 404.html を例外として明記し、「ローカル確認」節に「404.html はサブパス前提のため localhost では無スタイルになる」と 1 行足したい。

より堅くするなら、404.html は使用するスタイルが 20 行程度しかないので **CSS を `<style>` で内包し、`gem.webp` を落とす**とパス依存がゼロになる。リポジトリ名変更・独自ドメイン移行でも壊れなくなる（そのときは `.nojekyll` と 404.html だけを触れば済む）。

**S-3. `404.html` に `<h1>` が無い**
実測: `h1` 要素 0 個 / `h2` 1 個（`404.html:22` の「このページは見つかりませんでした。」）。`.final-cta h2` のスタイルを流用したかったのだと思うが、単独ページの主見出しは `h1` にすべき。`.final-cta h1, .final-cta h2 { … }` に広げるか、404 用に 1 セレクタ足す。

**S-4. 死にセレクタ `.sr-only`**
`assets/styles.css:185-194`。CSSOM 全 147 ルールを DOM 照合した結果、`index.html` / `404.html` の **どちらからも参照されていない唯一のセレクタ**（他は全件一致。CSS は全体としてかなり無駄がない）。削除するか、`.assurance li::before` の `✓` に読み上げ用テキストを付ける等で実際に使う。

---

### later

**L-1. `will-change: transform` が 12 要素に常時付いている**（`assets/styles.css:1031`）。実測で `will-change: transform` の要素は 12 個（`.reveal` 全件）。scroll-driven animation は実行中に自前で合成レイヤーを確保するので `will-change` は不要で、常時指定はモバイルの GPU メモリを無駄に占有する。削除推奨。

**L-2. `srcset` 不在**。`shot-search.webp` は 1600px 固定配信で、1280px ビューポートでの実描画は 1021px、390px ビューポートでも 1600px のまま届く（DPR1 なら 2.6 倍のピクセル）。モバイル総転送は実測 141KB と十分軽いので急ぎではないが、`srcset`（800w を追加）+ `sizes` で 40KB 前後は削れる。

**L-3. `twitter:image` / `og:image:type` / `theme-color` が無い**。`twitter:image` は `og:image` にフォールバックするので実害は小さい。`theme-color` はライト/ダーク 2 本（`media="(prefers-color-scheme: dark)"`）を入れると、モバイルのアドレスバー色が本文と揃う。

**L-4. JSON-LD に `WebPage` ノードと `offers` が無い**。`SoftwareApplication` が `@graph` 内の `WebSite` と `@id` で接続されておらず、LP 自身を表す `WebPage` ノードも無い。また「無料」を本文で謳っているので `offers: { "@type": "Offer", "price": "0", "priceCurrency": "USD" }` は**事実に即した追記**として入れられる（`aggregateRating` は入れない — OK-4 参照）。

**L-5. `site/README.md` が公開ツリーに含まれる**。`gh-pages` ルートへ `site/` の中身をそのまま置く方式なので、`https://kai-kou.github.io/gem-hunter/README.md` として素の Markdown が公開される（`.nojekyll` があるので raw のまま配信）。実害はないが、公開物に含めない選択肢もある。

**L-6. インラインスタイル 3 箇所**（`index.html:260` h3 の font-size、`544` brand の margin-bottom、`548` footer p の color/max-width）。CSS に寄せたい。

---

### 問題なしと確認できた項目

- **OK-1 CLS = 0.0000**。全画像に `width`/`height` があり（`shot-search` 1600×1025 / `shot-digest` 1400×766 / `shot-mobile` 640×1280 / `gem` 640×640 / `logo` 24×24、すべて実ファイルの実寸と一致）、layout-shift エントリは 1 件も発生しない。`.crop-top` の `max-height: 420px` + `object-fit: cover` も内在アスペクト比が先に確定するのでシフトを起こしていない。
- **OK-2 横スクロール発生なし**。320 / 360 / 768 / 1280 / 1440px のすべてで `scrollWidth === innerWidth`、ビューポート右端をはみ出す要素ゼロ。`body { overflow-x: hidden }` があっても html 側が `visible` なのでビューポートへ伝播し、新しいスクロールコンテナを作らない — sticky ヘッダーはスクロール後も実測で `top: 0` に貼り付いている。
- **OK-3 ネットワークが健全**。リクエスト 7 件・非圧縮合計 243KB。GitHub Pages の gzip 後は HTML 7.4KB / CSS 5.3KB（実測 `gzip -9`）で、ミニファイの必要性は低い。**外部ドメインへのリクエストはゼロ**（フォントも自前配信）、コンソールエラー・pageerror もゼロ。155KB の `ogp.png` はページから一切読まれていない。
- **OK-4 JSON-LD が正直**。妥当な JSON としてパースでき、`aggregateRating` も `reviewCount` も **書いていない**（実在しない評価を捏造していない — LP でいちばん壊れやすい箇所が正しく回避されている）。`applicationCategory: "DeveloperApplication"`、`license` の SPDX URL、`SoftwareApplication.url` が LP ではなく本番アプリを指す点もすべて正しい。
- **OK-5 絶対 URL とフォント**。canonical / `og:url` / `og:image` はすべて `https://kai-kou.github.io/gem-hunter/…` の絶対 URL で、`og:image` の実ファイルは宣言どおり 1200×630。フォントは `preload`（`crossorigin` 付き・stylesheet より前）+ `font-display: swap` + `unicode-range` で latin に限定。**可変フォントであることも実測確認**（HVAR/MVAR/STAT を保持、`font-weight: 400` と `700` の描画幅が 730.9px / 772.9px と実際に異なる）ので、`font-weight: 400 700` の宣言は正しく、太字が合成（fake bold）になっていない。
- **OK-6 GitHub Pages サブパス配信で壊れるパスが無い**。`index.html` は全参照が `./assets/…` の相対パスで `/gem-hunter/` 配下に正しく解決する。`404.html` を絶対パス（`/gem-hunter/…`）にした判断は**正しい** — Pages のカスタム 404 は任意の階層のリクエストに対して返るため、相対パスでは深い階層で確実に壊れる。`.nojekyll` も 0 バイトで存在（`_` 始まりのパスは現状無いが、置いておくのが正しい）。ページ内アンカー（`#why` `#how` `#features` `#trust` `#faq` `#top` `#main`）は全件解決、重複 id なし、HTML のタグ対応も破綻なし（`</a\n>` のような改行入り終了タグは仕様上妥当）。
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
これは固有名詞でも技術用語でもない**英文の句**なので 3.1.2 の除外に当たらず、日本語音声エンジンが英語を読み上げます。

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

1.4.10 は「情報**または機能**の損失なく提示できること」を求めており、
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
**厳密な AA 不適合ではありません**が、拡大表示を「ズーム」ではなく「既定フォントサイズ」で行う
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
  境界の唯一の手がかりが 1.39:1 の枠と 1.09:1 の面で、**それが操作可能であることを示す唯一の視覚情報**です。
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
   `fg-muted` 5.65（light）/ 7.28（dark）で **適合**でした。唯一の NG は上記 S-3 の hairline のみです。
4. **`prefers-reduced-motion: reduce` — 適合**。`animation-timeline: none !important` と
   `scroll-behavior: auto !important` まで無効化しており、実測で `scrollBehavior=auto` を確認。
   `.reveal` を **opacity ではなく transform だけで動かす**判断（CSS のコメントに明記）は正しく、
   最下部までスクロール後に全 12 個の `.reveal` が `transform` 恒等行列（ずれ残留ゼロ）でした。
   「範囲外に留まった要素が不可視のまま残る」事故を構造的に排除できています。
5. **`details` / `summary` — 適合**。`display: flex` を当てていますが Chromium のアクセシビリティツリー上の
   role は `DisclosureTriangle` のまま、**Enter / Space の両方でトグル**することを実測で確認。
   開閉状態を示すシェブロンも `--fg-muted` で 6.00:1（light）/ 7.63:1（dark）＝ 3:1 超。
6. **スキップリンク — 適合**。最初の Tab 停止点で `top=8, left=8, 153×52` に可視化され、
   `z-index: 100 > ヘッダーの 50` で隠れません。Enter で `<main id="main" tabindex="-1">` に
   フォーカスが移り、**次の Tab がヘッダーナビを飛ばしてヒーロー CTA に入る**ことまで確認しました。
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
- **コントラストはトークン値からの算出**であり、レンダリング後のピクセル実測ではありません。
  グラデーショングロー・`backdrop-filter` が絡む箇所は最悪ケースを合成計算しましたが（結果は適合）、
  実ピクセルサンプリングではない点は留保します。
- **404.html はローカル配信ではスタイル未適用**（`/gem-hunter/assets/styles.css` の絶対パスがローカルの
  ルート配信と噛み合わないため）。S-4 は DOM 構造と共有スタイルシートの読解に基づく指摘で、
  GitHub Pages 上（`/gem-hunter/` 配下）では正しく解決するはずです。
