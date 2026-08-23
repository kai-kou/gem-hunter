<!--entry
author: web_research
round: 1
kind: claim
ts: 2026-08-23T16:25:30+09:00
-->

## 問い1: 開発者向けLPで技術仕様・数値をどの粒度で出すのが有効か

**一次情報**

- NN/g「Concise, SCANNABLE, and Objective: How to Write for the Web」
  https://www.nngroup.com/articles/concise-scannable-and-objective-how-to-write-for-the-web/
  - 客観的スタイル（誇張・主観語を削ぎ落とす）が信頼性懸念を下げ、ユーザビリティが対照群比 +27% 改善した、という実証結果あり。
  - ただし「専門用語や数値をどこまで見せるか」への明示的な指針は本記事にはない（見つからなかった）。scannability の技術（見出し・太字・箇条書き・短い段落）が主眼で、粒度そのものへの言及はなし。
- 実在の開発者向けプロダクト LP を 4 件、実際に WebFetch して構造を観察（3 件以上の指示を満たす）:
  - **Vercel** https://vercel.com/ — 技術仕様（ms・メモリ制限・バージョン番号）はほぼゼロ。出てくる数値は事業規模のみ（"millions of agent conversations daily" "100 million monthly visits" 等）。機能はカテゴリ名の列挙にとどめ、詳細スペックはドキュメントに委譲。
  - **Linear** https://linear.app — 技術数値はほぼ皆無（進捗インジケータ的な "02/145" 程度）。ベネフィット文（"Reduces noise and restores momentum..."）が主役で、機能名（Agents / Coding Sessions / Diffs）は列挙のみ、仕様説明は省略。
  - **PostHog** https://posthog.com/ — 技術仕様（レイテンシ・精度・スケーラビリティ）は本文に出てこない。唯一の数値はユーザー数（"500,000+ teams"）。機能名を 20 以上列挙するが詳細は書かない。
  - **Plausible** https://plausible.io/ — 🔴 上記 3 件と対照的に、**技術仕様・数値を積極的に出す** LP。「Our script is 54 times smaller than Google Analytics」「135KB less JavaScript」「4 kg CO2/year」「20k subscribers」「260B tracked pageviews」「99.99% Uptime (Last 90 days)」。一方で UX・プライバシーのベネフィット（"No cookies, just insights" "Simple analytics at a glance"）は数値なしの定性文のまま。

**本件への含意**

4 件の観察から、開発者向け LP の粒度戦略は一枚岩ではなく、**「その数値が読者にとって検証可能な差別化要因（性能・規模・信頼の証拠）か、それとも単なる UX の状態説明か」で出し分けている**ことが分かる。Vercel/Linear/PostHog（ビジネス色の強い SaaS）は数値を事業規模のみに絞り機能は抽象化するが、Plausible（gem-hunter と同じ「透明性が信頼の代替」を掲げる個人色の強いプロダクト）は **trust/proof の文脈でのみ**具体的な技術数値（サイズ比較・稼働率・処理件数）を出し、**UX 体験の文脈では数値を出さない**という使い分けをしている。

これは `site/index.html` の trust セクション（:520-554 の `1,061 ケース` `Accessibility 100` `ADR 15 本` `JavaScript 0 行` `Next.js 16 / React Server Components` 等）は Plausible 型の正当な粒度（残してよい・むしろ強み）である一方、**features セクションの tile 本文（例: `スマートフォンで取りこぼさない` :401 の「44px」「16px」、`キーボードだけで完走できる` :481 前後の tag-list「WCAG 2.2 AA」「コントラスト実測」「フォーカス可視」）は「UX の状態説明」に技術数値を混ぜている点で、Vercel/Linear が避けているパターンに近い**、という具体的な切り分けの根拠になる。数値そのものが悪いのではなく、**置き場所（trust セクションか features tile か）が粒度の適否を決めている**、というのが web_research としての一次的な結論。

---

## 問い2: 「機能ではなくベネフィットを書け」の一次出典と開発者読者での成立条件

**見つかった情報（厳密な一次出典は特定できず）**

- 「features tell, benefits sell」という定型句自体の起源・一次出典元は検索で特定できなかった（**見つからなかった**）。copywriting 分野で広く定着した経験則としてしか裏取りできない。
- ただし、**開発者・技術者読者に対する適用限界**については複数の実務資料で明確な例外が述べられている:
  https://mrymarketing.com/blog/features-vs-benefits-technical-product-copywriting （Technical Product Copywriting Framework）
  > "A software developer buying a database cares about read/write speeds, query language support, and uptime SLAs. These are features, but to this audience, they are the benefit because they directly indicate product quality."
  - 同様の趣旨: 技術的な差別化要因（他社が言えない具体的な数値・仕様）は、汎用的なベネフィット文言より説得力が高い、という指摘（例: 「早い配送」より「専属配達員による2時間以内配送」）。

**本件への含意**

「機能ではなくベネフィットを書け」は開発者読者にそのまま適用してはいけない指針であり、**技術仕様そのものが読者の判断材料（＝ベネフィット）になる場合は、抽象化するとむしろ情報価値が下がる**。これは brief にある dev_reader レンズの立場（削りすぎ批判）を一次情報で裏付ける。

ただし逆に言えば、この例外が効くのは「その仕様が読者にとって**差別化・意思決定の判断材料**になる場合」に限られる。`site/index.html` の trust セクションの `1,061 ケース` `ADR 15 本` のような**プロダクトの信頼性・品質を裏付ける数値**は例外に該当し残すべきだが、features tile の `44px` `16px` は「gem-hunter を使うかどうかの判断材料」というより「モバイルでちゃんと使える」という**当たり前品質（table stakes）の技術的証跡**に近く、開発者読者であっても「どの実装値か」より「本当にちゃんと動くか」の一言（ベネフィット文）の方が情報価値が高い可能性が高い。つまり同じ LP 内でも tile によって適用すべき指針が違う、というのが A（弁別基準）への示唆。

---

## 問い3: 44px タップ領域・iOS 16px 自動ズームの一般向け言い回し

**規格の原文**

- Apple HIG: タップ領域の推奨最小サイズは **44×44pt**（"minimum tap target size of 44x44pt"）。指の腹の平均サイズに基づく。
  https://www.brilworks.com/blog/apple-human-interface-guidelines/ ほか複数の二次資料が同旨で引用（Apple 公式 HIG ページそのものへの直接 WebFetch はしていないため、二次資料経由）
- WCAG 2.5.5 Target Size（AAA・任意）原文:
  > "The size of the target for pointer inputs is at least 44 by 44 CSS pixels except when: ..."
  https://appt.org/en/guidelines/wcag/success-criterion-2-5-5 / https://dequeuniversity.com/resources/wcag2.1/2.5.5-target-size
- web.dev（Google Chrome チーム）は **48px** を推奨（"around 48 device independent pixels... corresponds to around 9mm, about the size of a person's finger pad"）。8px の余白も推奨。
  https://web.dev/articles/accessible-tap-targets
  ⚠️ **事実精度への示唆（fact_check 向け共有）**: HIG/WCAG は 44px、web.dev は 48px を挙げており、業界内でも基準数値に揺れがある。LP が「44px」と単一の数値を断定的に書く場合、どの規格に準拠したかを暗黙に選んでいる点は fact_check が確認すべき。
- iOS 自動ズームの原因: 「Safari for iPhone automatically zooms in on text input fields when the computed font size of the input is less than 16 pixels」
  https://css-tricks.com/16px-or-larger-text-prevents-ios-form-zoom/

**一般向け（非規格語）の言い換え実例**

- 「roughly the size of the average adult finger pad」（指の腹サイズが基準、という説明）
  https://www.brilworks.com/blog/apple-human-interface-guidelines/
- 「Interactive text ... should be large enough for easy tapping」「easy to tap」という平易な達成状態の言い方
  複数のブログ・ガイド記事（Design Shack, UXPin 等）が共通して「タップしやすい／押し間違えない」という**結果ベースの言い方**に翻訳しており、px 数値をそのまま出さずに済ませている実例が多数派。
  https://designshack.net/articles/ux-design/tappable-targets/
- iOS ズームは「押したら勝手に拡大してしまう不便」という**現象の名前**（"unexpectedly zooming the page"）で語られることが多く、「16px」という数値は開発者向け技術記事（CSS-Tricks 等）にのみ現れ、一般ユーザー向け文脈では現れない。

**本件への含意**

外部の実例を見る限り、**「44px」「16px」という数値そのものを一般読者向けコピーにそのまま出す慣行は見当たらない**。多くは「指で押しやすい」「誤タップしにくい」「入力時に勝手に拡大しない」のような**結果・体験ベースの言い方**に翻訳されている。これは copy_editor の書き換え案（tile 本文・tag-list）が「44px」「16px」を残すのではなく、体験ベースの言葉に置き換える方向性を取ることの外部的な裏付けになる。ただし fact_check が指摘するとおり「44px は主要導線のみ・全コントロールではない」という射程の正確さは、言い換えた文でも失ってはならない（例:「指で押しやすい大きさにしています」だけだと将来の実装後退を検知しにくくなるので、対象範囲＝主要導線限定であることは言葉のどこかに残す方が安全）。

---

## 問い4: 数値を出すことが信頼を上げる／下げる条件

- 「数値データは客観的・事実ベースと知覚されやすく、信頼を高める」という一般的知見はある。
  https://www.rogerdooley.com/how-numbers-persuade-you/
- ただし重要な留保: **「数値が主題に関連していることが必須で、無関係・場違いなデータはむしろ説得力を損なう」**
  （同上ソースの要約より）
- 数字は算用数字（"10"）の方が文字表記（"ten"）より説得力が高い、という知見もあり（本件は既に算用数字表記なので直接の示唆はなし）。
  https://spsp.org/news/character-and-context-blog/romero-craig-mormann-kumar-number-ten-more-convincing-than-word-ten-consumer-marketing

**本件への含意**

「数値は関連性がある場合にのみ信頼を上げ、関連性がないと逆効果」という条件は、A（弁別基準）に直接効く。trust セクションの数値（テストケース数・ADR 本数）は「このプロダクトはどれだけ検証されているか」という**主題（信頼性）に直結**するため関連性が高く、残す根拠になる。一方 features tile の「44px」「16px」は「スマホで使いやすいか」という**主題（使い勝手）に対しては数値そのものが関連性の中心ではなく、結果（押しやすい・拡大しない）こそが関連情報**であり、数値は補助情報に留まる。ここでも「同じ"数値を出す/出さない"でもセクションの主題によって関連性が変わる」という A の弁別軸を補強する。
