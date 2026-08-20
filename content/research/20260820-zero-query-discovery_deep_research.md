# ディープリサーチ結果: キーワード入力に依存しない OSS 発見体験（zero-query discovery）

- **ID**: `20260820-zero-query-discovery`
- **実行日**: 2026-08-20 JST
- **エンジン**: ネイティブ `/deep-research`（Workflow・3 票制の敵対的検証）
- **統計**: サブエージェント 111 体 / ツール呼び出し 880 回
- **依頼元**: Issue #218

> 🔴 **読み方**: 本レポートの「検証済み所見」は 3 票制の敵対的検証を通過した主張のみ。
> 反証・不支持となった主張は §4 に列挙してあり、**事実として引用してはならない**。

---

## 1. 要約

3 票制の敵対的検証を通過した 13 主張を統合すると、gem-hunter の zero-query 発見体験について確度の高い結論は 4 つに収斂する。(1) 「キーワードを入力しない発見」の器として無限フィードは NN/g が「目的なき同質アイテム閲覧」に限定して推奨する一方、探索・比較・上位数件の検分には非推奨で、かつキーボード操作を複雑化するため、Lighthouse A11y 100・キーボード完走が必須ゲートの gem-hunter では「有限・ページ分割・明示的な Load more」側に倒すのが安全である。(2) 時間トリガー×定期ダイジェスト（Hugging Face Daily Papers の日次購読）と、ランキング固定化への対処としての時間分割ランダム化（Product Hunt が 2026-03-27 の単日イベントで実施した 25 分ランダム／5 分通常の 30 分周期）という 2 つの実装例が一次情報で確認でき、いずれも gem-hunter の「静的事前生成 JSON + クライアント時刻」で近似可能である。(3) セレンディピティは研究上いまだ定義が一意でなく（Kaminskas & Bridge の surprise+relevance 2 成分／Kotkov らの relevance+novelty+unexpectedness 3 成分／UMAP'25 の fortuitous+refreshing+enriching 3 成分が併存）、実装前にどの変種を採るかの明示が必要で、単一スコアへの潰し込み（単純加算）は少なくとも UMAP'25 の枠組みでは不適切とされる。(4) データ源としては Ecosyste.ms が被依存数（dependent_packages_count / dependent_repos_count）を公式 API フィールドとして提供しており制約は成立するが、精度と beyond-accuracy 目的（novelty 等）にはトレードオフがあり、かつオフライン評価自体が人気アイテムに偏るため、「過小評価度」の効果はオフライン指標では過小評価される点を前提に設計する必要がある。なお本検証では調査項目 3（AI エージェント時代・MCP・偽 star）・5（localStorage 個人化の実例）・6（スコア提示 UI）・7（エッジ実行下のフィード生成）を支える主張がほぼ全て脱落しており、これらは未解明領域として残る。

## 2. 検証済み所見

### F-1（確度: high / 票: 3-0（2 主張を統合））

[A] 無限スクロールが適するのは「特定のタスクや目標を持たずに同質なアイテムを閲覧する」状況に限られ、逆に (a) 特定のものを探す (b) 長いリスト内のアイテムを比較する (c) 上位数件だけを検分する、という用途では NN/g は無限スクロールを推奨しない。→ gem-hunter の「リマインド的に良質な OSS が提示される」体験は (前者) に該当しうるが、提示された OSS を比較検討して 1 つ選ぶという本来の目的行為は (b)(c) に該当するため、発見面と比較面を UI 上で分離しないと無限フィードは逆効果になる。【制約充足性: 条件付き可 — 無限スクロール自体は静的 JSON + クライアント計算で実装可能だが、比較・選定フェーズには使わない設計分離が前提】

**根拠**: 一次情報（NN/g, Tim Neusesser, 2022-09-04）を直接 WebFetch し逐語確認。肯定側: "Infinite scrolling typically works best for situations where users will want to scroll through homogeneous items with no particular task or goal in mind — for example, entertainment, news, or social media." 否定側: "we do not recommend it when users will want to use the listing page's content to: Find something specific... Compare items in a long list... Inspect only a few items at the top of the list." 検証者 2 名がそれぞれ独立に逐語一致を確認し、反証情報源はゼロ。Baymard の EC ユーザビリティ知見・NN/g 自身の 2023 年動画も同方向。【留意】出典は 2022 年であり 2025〜2026 の新知見ではない。標準的ガイダンスとして扱う。また「目的なきブラウジング = zero-query 発見体験」という等式は本レポート側の解釈であり、NN/g は zero-query という語を用いていない。

**出典**: https://www.nngroup.com/articles/infinite-scrolling-tips/

### F-2（確度: high / 票: 3-0）

[A] 無限スクロールはキーボードのみのユーザーにとって、1 ページに大量のコンテンツが載るためリンクを 1 つずつ tab 移動せざるを得ず、ウェブ操作を複雑にする。ただし W3C ARIA の role=feed により「無限フィードを飛び越して次のフォーカス可能要素へ移動する」緩和策が存在する。→ gem-hunter の必須ゲート（キーボードのみで完走可能・Lighthouse A11y 100）に対し、真の無限スクロールは明示的な緩和（role=feed / キーボードで到達できる Load more ボタン / スキップリンク）なしには採用不可。【制約充足性: 条件付き可】

**根拠**: NN/g 記事の逐語: "For keyboard-only users, infinite scrolling complicates navigating the web, due to the vast amount of content that can be placed on one page because such users have to 'tab' through content link by link"。同記事は「スクリーンリーダー利用者は最初の chunk しか認識しない」とも述べる。Deque・BOIA・DigitalA11Y が独立に同じ障害（下部に読み込まれたコンテンツへ到達できない・フィードから抜けられない）を記述。反証検索では「キーボード利用者にとって問題ない」とする情報源はゼロ件。出典は 2022 年だが、機序（無制限 DOM の逐次 tab 走査・読み込みトリガーがキーボード操作に紐づかない）は陳腐化していない。

**出典**: https://www.nngroup.com/articles/infinite-scrolling-tips/ / https://www.deque.com/blog/infinite-scrolling-rolefeed-accessibility-issues/ / https://www.boia.org/blog/is-infinite-scrolling-accessible

### F-3（確度: high / 票: 3-0）

[A/B] 「時間トリガー × 定期ダイジェスト」の実装例として Hugging Face Daily Papers はメール購読を提供しており、ユーザーがキーワードを入力せずに新着が届く。ただし現行ページの Subscribe は /login?next=%2Fpapers へ遷移する＝アカウント必須であり、gem-hunter の「ログイン必須にしない・サーバーに個人データを持たない」制約とは正面から衝突する。→ 同じ体験を gem-hunter で採るなら、メール配信ではなく RSS / 静的 JSON + クライアント側の「前回訪問差分」に置き換える必要がある。【制約充足性: メール購読は不可（アドレス保持が必要）／RSS・静的ダイジェストへの読み替えは可】

**根拠**: 公式ブログ（2024-09-23）の「✅ Subscription」節に逐語 "You'll receive daily updates (excluding weekends) with the latest papers straight to your inbox. 📩"。加えて検証時点（2026-08-20）に https://huggingface.co/papers を実取得し、"Get trending papers in your email inbox once a day!" と Subscribe CTA が現存すること、その CTA が /login?next=%2Fpapers を指すことを確認（＝機能は現役、かつログイン前提）。【留意】「週末を除く」という cadence 表記は 2024 年ブログのみに由来し、現行ページは "once a day"（Daily/Weekly/Monthly の選択肢が存在する模様）。週末除外は 2024 年時点の記述として扱い、現在の事実として断定しない。

**出典**: https://huggingface.co/blog/daily-papers / https://huggingface.co/papers

### F-4（確度: high / 票: 3-0）

[A] ランキング上位の固定化に対する実運用上の対処として、Product Hunt は「Randomized Leaderboard Day」（イベント日 2026-03-27）で、30 分周期のうち 25 分をランダム順・残り 5 分を通常のランク順とする時間分割方式を採った。ランダム性を常時ではなく時間で区切って与える設計である。なお、これは恒久機能ではなく単日イベントの仕様である。→ gem-hunter が「同じ OSS が上位に居座る」問題に対処する際、シャッフルを常時適用せず「時間帯で切り替える」設計は前例がある。クライアント時刻 + 静的 JSON + 決定論的シード（例: UTC 時刻から導出）で DB なしに再現可能。【制約充足性: 可】

**根拠**: 公式フォーラム投稿を 2 回独立に取得し、いずれも同一逐語を返した: "The Loop: This cycle repeats every 30 minutes, all day long. / 25 Minutes: The leaderboard will be completely randomized. / 5 Minutes: The leaderboard will return to its standard ranked order." 独立の WebSearch サマリも同じ 25 分／5 分を再現し、周期や配分を否定する情報源はゼロ。投稿日 2026-03-26、イベント日 2026-03-27（相対表記 "5mo ago" が現在 2026-08 と整合）。【留意】(1) 恒久機能ではなく単日イベント。(2) 同投稿にはランダム期間中「ポイント非表示」「投票が 2 倍カウント」という併記仕様があるが、これらは 3-0 の検証を通過していないため本レポートでは主張しない。(3) 告知どおり当日稼働したことを検証した独立の一次計測は未確認。

**出典**: https://www.producthunt.com/p/producthunt/introducing-randomized-leaderboard-day-on-product-hunt

### F-5（確度: high / 票: 3-0）

[A] GitHub のリポジトリ総数は 2025 年 Octoverse 時点で 6.3 億件、当該計測期間に 1.21 億件（毎分 230 件）が新規作成された。→ キーワード検索だけでは母集団を把握できない規模であり、zero-query 型の発見支援が必要になる背景データとして使える。【制約充足性: 背景データのため制約に無関係】

**根拠**: 一次情報を WebFetch し 3 数値すべて逐語確認（"630M" total repositories / "Developers created more than 230 new repositories every minute" / "+121M new repositories in 2025"）。230/分 × 60 × 24 × 365 = 1.209 億 と 121M が相互検証になっている。InfoWorld・Forbes（2025-11-01）等の二次情報も同数値を反証なく再掲。GitHub 自身のプラットフォーム計測であり、この数値を出せる主体は他に存在しない（[A] 妥当）。【重要な限定】(1) 計測窓は GitHub 自身の定義で 2024-09-01〜2025-08-31 のローリング 12 か月であり暦年 2025 ではない。(2) 6.3 億にはフォーク・アーカイブ・非活動リポジトリを含むため「6.3 億の活動中プロジェクト」と読み替えてはならない（ただしこの点はむしろ「母集団は人手で見渡せない」という主張の趣旨を補強する）。(3) 「だから zero-query が必要」は本レポート側の推論であり Octoverse の知見ではない。

**出典**: https://octoverse.github.com/ / https://github.blog/news-insights/octoverse/octoverse-a-new-developer-joins-github-every-second-as-ai-leads-typescript-to-1/

### F-6（確度: high / 票: 3-0）

[A] Ecosyste.ms Packages は「パッケージ・バージョン・依存関係メタデータを提供するオープン API サービス」であり、被依存数は dependent_packages_count / dependent_repos_count / docker_dependents_count という公式 API フィールドとして提供され、公開 UI 上でも ?sort=dependent_repos_count 等のソートキーとして露出している。→ gem-hunter の「被依存数を Ecosyste.ms から取得する」制約は、スクレイピングや派生推定ではなく公式提供経路で成立する。【制約充足性: 可】

**根拠**: 自己定義の逐語をトップページと GitHub リポジトリ description の 2 箇所で確認: "An open API service providing package, version and dependency metadata of many open source software ecosystems and registries." さらに検証時（2026-08-20）に実 API を叩き 200 応答を取得: dependent_packages_count: 93237 / dependent_repos_count: 1853938 / docker_dependents_count: 46587、および dependent_packages_url・dependent_repositories_url が第一級フィールドとして返ることを確認。「dependency metadata（順方向依存）」という語だけでは逆方向（被依存）を保証しないという弱点を狙って検証したが、機械可読な API 出力で直接反証に失敗した。【運用上の限定】README 記載のレート制限は IP あたり 5000 req/hour（polite pool あり）。gem-hunter はリクエスト時ではなく静的事前生成で使うため本制約の影響は小さい。

**出典**: https://packages.ecosyste.ms/ / https://github.com/ecosyste-ms/packages / https://packages.ecosyste.ms/api/v1/registries/npmjs.org/packages/express

### F-7（確度: medium / 票: 2-1）

[B] Ecosyste.ms Packages は 51 エコシステム・109 レジストリにまたがる 14,697,982 パッケージ／176,887,122 バージョンをインデックスしている（2026-08-20 時点）。言語横断の zero-query 候補プールを静的に事前生成するには十分な母集団規模がある。ただしレート制限 5000 req/hour で全件走査すると約 122 日を要するため、bulk/dump 経路または上位 N への事前絞り込みが前提となる。【制約充足性: 条件付き可 — 母集団は十分だが取得戦略が未解決】

**根拠**: 検証時に https://packages.ecosyste.ms/ を実取得し 4 数値すべて（51 Ecosystems / 109 Registries / 14,697,982 Packages / 176,887,122 Versions）が逐語で存在することを確認。反証検索では数値やカバレッジを否定する情報源は見つからず、唯一の学術的言及（arXiv 2605.06164, PyPI 保守活動モデリング）も Ecosyste.ms を利用可能なデータ源として扱い、批判はコンタクト情報 91.8%・寄付リンク 58.8% という別フィールドの網羅性に限定される。【票が 2-1 に割れた理由と限定】(1) これらは単調増加のライブカウンタであり、検索エンジンのキャッシュ版は同一 URL で 5,750,985 packages / 75,312,648 versions（約 2.5 分の 1）を示す。取得日を明記せず数値を引くと確実に陳腐化する。(2) 「十分な母集団規模がある」は本レポート側の判断であり、ページはそう述べていない。(3) 3MB gzip バンドルに 1470 万件を載せられるという意味ではなく、あくまで上流の母集団規模の話である。

**出典**: https://packages.ecosyste.ms/ / https://github.com/ecosyste-ms/packages

### F-8（確度: high / 票: 3-0）

[A] 体験されたセレンディピティは「ユーザーが意図せず出会ったコンテンツが fortuitous（偶然性）・refreshing（新鮮さ）・enriching（豊かさ）と感じられるユーザー体験」と定義でき、単一指標ではなくこの 3 成分に分解して設計・評価の指針にできる。同論文は成分の単純加算による操作化を明示的に批判し（1 成分の高得点が他成分の低得点を隠す）、成分ごとの最低閾値を代替案として挙げる。→ gem-hunter の「Gem Score（過小評価度）」を単一スコアに潰し込む設計は、少なくともこの枠組みでは不適切。【制約充足性: 可（設計指針であり実装制約に依存しない）】

**根拠**: PDF 全文を取得し、Abstract・Conclusion の 2 箇所で定義の逐語一致を確認: "we conceptualize experienced serendipity as a user experience in which a user unintentionally encounters content that feels fortuitous, refreshing, and enriching." 単純加算批判も §5 に逐語で存在: "current research frequently operationalizes serendipity by either summing its main components ... these approaches are problematic ... A formula that calculates experienced serendipity by summing the components fails to ensure this ... One possible way to avoid this problem is by setting a minimum threshold score for each main component." 出典は arXiv プレプリントではなく査読済み: Binst, Michiels & Smets, ACM UMAP '25, DOI 10.1145/3699682.3728325（2025-06）。【限定】(1) N=17、参加者は全員ベルギー人・20〜60 歳、論文自身が "This narrow scope may limit the generalizability" と明記。(2) 参加者は主に大規模国際プラットフォームの体験を語っており、論文自身が「小規模・ローカルなプラットフォームへの適用は future work」と述べる — gem-hunter はまさに後者。(3) 検証済みの測定尺度はまだ存在せず論文は "lays the groundwork" と述べるため、「評価に使える」は設計指針・単純加算の排除までであり、既製の 3 成分メトリクスが使えるという意味ではない。(4) 「3 成分は各々必要条件で 3 つ揃って十分条件」というより強い派生主張は 1-2 で棄却されたため本レポートでは主張しない。

**出典**: https://arxiv.org/abs/2505.15440 / https://doi.org/10.1145/3699682.3728325

### F-9（確度: high / 票: 3-0）

[A] セレンディピティは推薦システム研究において、ユーザー満足度の向上とロングテールアイテムの消費増加という便益に関連づけられてきた（因果の断定ではなく文献上の関連づけ）。→ gem-hunter が狙う「過小評価 OSS＝人気の裾野にあるアイテム」の提示に、推薦研究側の理論的な追い風がある。【制約充足性: 可（理論的根拠）】

**根拠**: UMAP '25 論文（査読済み）Abstract 冒頭の逐語: "Serendipity has been associated with numerous benefits in the context of recommender systems, e.g., increased user satisfaction and consumption of long-tail items." 独立の裏付けとして Chen et al., WWW 2019 "How Serendipity Improves User Satisfaction with Recommendations? A Large-Scale User Evaluation"（産業系モバイル EC、3,000 名超、serendipity と満足度・購買意図の有意な関係）。【限定】(1) この一文は当該論文自身の実験結果ではなく先行研究を要約した導入文（＝査読済み論文における文献レビュー記述）。(2) 同論文自身が直後に「serendipity は概念的に曖昧で operationalization が研究間で不一致、findings の比較・統合が困難」と述べる。(3) "The Dark Matter of Serendipity in Recommender Systems"（DOI 10.1145/3627508.3638342）は、セレンディピティ指標を直接最適化してもユーザーの期待と一致せず UX を損なう可能性を指摘する — 指標の直接最適化には反対材料がある。(4) 推薦研究の long-tail（カタログ内低人気アイテム）を OSS の「過小評価度」に読み替えるのはアナロジーであり、出典が支持する内容ではない。

**出典**: https://arxiv.org/abs/2505.15440 / https://doi.org/10.1145/3699682.3728325 / https://doi.org/10.1145/3308558.3313469

### F-10（確度: high / 票: 3-0（2 主張を統合））

[A] セレンディピティの定義には研究上のコンセンサスが存在せず、少なくとも 2 系統が併存する。Kaminskas & Bridge（ACM TiiS 2016）は「surprise + relevance の 2 成分というのが共通了解」とし、Herlocker らの定義に基づき「novel であっても serendipitous とは限らないが、serendipitous なアイテムは novel かつ surprising でなければならない（＝セレンディピティ集合は新規性集合の部分集合）」と整理する。一方 Kotkov, Wang & Veijalainen（Knowledge-Based Systems 2016）は「定義に合意はないが、大多数の文献は relevance・novelty・unexpectedness の 3 成分で一致している」とする。また Adamopoulos & Tuzhilin の unexpectedness 系指標は novel であることを要求しない。→ gem-hunter が「セレンディピティ推薦」を実装する前に、どの定義変種を採るかを明示しなければ、指標も UI コピーも一貫しない。【制約充足性: 可（設計上の意思決定事項）】

**根拠**: 2 主張の統合。(1) Kaminskas & Bridge 側: 完全一致フレーズ検索 2 本が同一 PDF に収束し逐語確認 — "it is commonly agreed that serendipity consists of two components—surprise and relevance [Herlocker et al. 2004]" / "a serendipitous item must be both novel and surprising; hence, the set of items that are serendipitous to a user is a subset of the set of items that are novel to that user" / "Adamopoulos and Tuzhilin [2014] ... did not require an unexpected item to be novel"。DOI 10.1145/2926720（ACM TiiS, 2016-12-19, 被引用 358〜448）を Crossref・OpenAlex・Semantic Scholar の 3 API で同定。(2) Kotkov 側: ScienceDirect は実測で HTTP 403（有料）だったため、第一著者の OA 博士論文 PDF 全文（University of Jyväskylä 2018, ISBN 978-951-39-7438-1、163p）を取得して検証。当該サーベイが Paper PI として収録・全文再録されており、"There is no consensus on definition of serendipity in recommender systems" / "Most authors agree that serendipity includes three components: relevance, novelty and unexpectedness" を逐語確認。KBS 原典本文でも同旨（abstract "there is no wide consensus on which definition and evaluation metric to use"、§2.2.2 "The majority of papers include each of these three components"）を確認したため、代替出典依存ではない。【限定】(1) 「共通了解」を分野全体の合意として無限定に書かない — 帰属を Kaminskas & Bridge に明示すべき。(2) 概念論争は 2025 年時点でも継続中（前掲 UMAP '25 の 3 成分定義が第 3 系統として存在）。(3) Kotkov らの「novelty 2 変種 × unexpectedness 4 変種 = 8 通りの定義」というより細かい派生主張は 0-2 で棄却されたため本レポートでは主張しない。(4) 出典はいずれも 2016 年で 2025〜2026 の新知見ではないが、基礎定義の系譜整理であり陳腐化しない性質のもの。

**出典**: https://www.semanticscholar.org/paper/Diversity,-Serendipity,-Novelty,-and-Coverage-Kaminskas-Bridge/0a2a1bfeea7a572a78cd12a79f3b00911aa9bba4 / https://doi.org/10.1145/2926720 / https://jyx.jyu.fi/handle/123456789/58207 / https://www.sciencedirect.com/science/article/abs/pii/S0950705116302763

### F-11（確度: medium / 票: 3-0）

[A] 精度と beyond-accuracy 目的（多様性・新規性・セレンディピティ）にはトレードオフがあり、Kaminskas & Bridge の実験では Recall はベースラインのランキングで最高値をとり、いずれの再ランキング手法でも低下した。とりわけ novelty 目的の再ランキングが精度を最も損なうが、その一因はオフライン評価自体が人気アイテムに偏っていること（テストセットの評価が人気アイテムに集中すること）にある。→ gem-hunter の「過小評価度による再ランキング」はオフライン指標上は必ず精度が下がって見えるが、その低下の一部は評価手法側のバイアスであり、実効果の判定にはオフライン指標を使えない。【制約充足性: 可（評価設計上の含意）】

**根拠**: 引用文と主張の対応は要素ごとに逐語一致（"Recall has its highest value when using the Baseline ranking for each algorithm and is lowered using any of the reranking approaches" / "Reranking the recommendations for novelty ... hurts accuracy the most" / "any offline evaluation methodology is (to a certain extent) biased toward popular items: user ratings in the test set are more likely to belong to popular items"）。出典の同定は Crossref（DOI 10.1145/2926720, ACM TiiS, 2016-12-19）・OpenAlex・Semantic Scholar の 3 API で一致確認。【medium 判定の理由】(1) 全文が有料（OpenAlex oa_status "closed"、dl.acm.org は 403）で、引用文の逐語一致を PDF 本体に対して直接確認できておらず、掲載誌・論文種別・TLDR との整合による間接確認に留まる。(2) 検証セッションの WebSearch 予算が枯渇し、独立の反証検索を実施できていない。【限定】出典は 2016 年。ただし主張は「ある特定の実験がこう報告した」という過去形・帰属付きの命題であり、後続研究（Cañamares & Castells 2018 等のオフライン人気バイアス研究）は反証ではなく補強にあたる。

**出典**: https://www.semanticscholar.org/paper/Diversity,-Serendipity,-Novelty,-and-Coverage-Kaminskas-Bridge/0a2a1bfeea7a572a78cd12a79f3b00911aa9bba4 / https://doi.org/10.1145/2926720

### F-12（確度: low / 票: —（設計提案））

【設計提案・本調査からの推論であり事実主張ではない】方向性候補 A「日次の有限ダイジェスト（Daily Gems）」— ①体験: 1 日 1 回、静的に事前生成された N 件（例 5 件）の過小評価 OSS が全員に同じ順で提示され、その日はそれ以上出てこない（Wordle 型の有限性）。②必要なデータ源: Ecosyste.ms の被依存数 + OpenSSF criticality_score を日次バッチで事前計算した静的 JSON。③制約充足性: 可（DB 不要・ログイン不要・個人データ不要・クライアントは日付キーで JSON を引くだけで CPU 予算に収まる）。④差別化: 無限フィードへの反動としての「有限性」を正面から採り、キーボードのみで完走可能な a11y ゲートとも整合。⑤失敗モード: 新規性の枯渇（過小評価 OSS の母集団が数か月で尽きる）、全員同一のため再訪動機が弱い、日次バッチが止まると体験ごと死ぬ。

**根拠**: 本項目は検証済み主張の組み合わせから導いた設計提案であり、いずれの出典もこの提案自体を支持していない。根拠となる検証済み事実は 3 点: (1) NN/g が探索・比較・上位数件検分の用途で無限スクロールを非推奨としていること、(2) Hugging Face Daily Papers が日次の時間トリガー型ダイジェストとして現に稼働していること（ただしログイン必須のためメール経路は gem-hunter では採れない）、(3) Ecosyste.ms が被依存数を公式 API フィールドとして提供していること。⑤の失敗モード（新規性の枯渇）は調査項目 2 が求めていた「同じものが上位に居座る問題への対処」の実例調査が今回の検証で 1 件も生き残らなかったため、対処法の裏付けが無い状態である。

**出典**: https://www.nngroup.com/articles/infinite-scrolling-tips/ / https://huggingface.co/blog/daily-papers / https://packages.ecosyste.ms/

### F-13（確度: low / 票: —（設計提案））

【設計提案・本調査からの推論であり事実主張ではない】方向性候補 B「時間分割シャッフル（Serendipity Window）」— ①体験: 同じ静的データセットに対し、時間帯によって並びをランク順とランダム順で切り替え、「今この時間だけ違うものが見える」という再訪動機を作る。②必要なデータ源: 候補 A と同一の静的 JSON + クライアント時刻から導出する決定論的シード（サーバー状態不要）。③制約充足性: 可（Product Hunt が 30 分周期・25 分ランダム／5 分通常で実施した前例あり。クライアント計算のみで Workers の CPU 予算を消費しない）。④差別化: ランキング固定化への対処としてシャッフルを常時ではなく時間で区切って与える設計は、OSS 発見領域では前例が見当たらない。⑤失敗モード: ランダム順が「関連性ゼロの提示」に堕してセレンディピティ 3 成分のうち enriching / relevance を満たさない、URL 共有時に相手に別の並びが見えて再現性が失われる（URL に seed を含める必要がある）、単日イベントとして成立した仕掛けが常設だと飽きられる。

**根拠**: 設計提案。検証済みの根拠は (1) Product Hunt の 25 分ランダム／5 分通常・30 分周期という時間分割ランダム化が公式告知で確認できること（ただし恒久機能ではなく 2026-03-27 の単日イベント）、(2) セレンディピティは surprise/unexpectedness だけでは成立せず relevance ないし enriching を要すること（Kaminskas & Bridge の 2 成分定義、UMAP '25 の 3 成分定義）— したがって純ランダムはセレンディピティ設計として不十分であり、⑤の失敗モードは理論的に裏付けられている。

**出典**: https://www.producthunt.com/p/producthunt/introducing-randomized-leaderboard-day-on-product-hunt / https://arxiv.org/abs/2505.15440 / https://www.semanticscholar.org/paper/Diversity,-Serendipity,-Novelty,-and-Coverage-Kaminskas-Bridge/0a2a1bfeea7a572a78cd12a79f3b00911aa9bba4

### F-14（確度: low / 票: —（設計提案））

【設計提案・本調査からの推論であり事実主張ではない】方向性候補 C「多軸バッジ提示（単一 Gem Score を作らない）」— ①体験: 「過小評価度」を 1 つの数値に潰さず、被依存数・star 数・criticality_score・最終更新などを独立した軸／バッジとして並置し、「なぜこれが提示されたか」を軸単位で説明する。②必要なデータ源: Ecosyste.ms（dependent_packages_count / dependent_repos_count）+ OpenSSF criticality_score / Scorecard、出典表示付き。③制約充足性: 可（すべて事前計算した静的値の表示であり CPU 予算・DB 制約に抵触しない）。④差別化: star 一元主義への批判をそのまま UI の構造に落とし込める。⑤失敗モード: 軸が多すぎてユーザーが判断できない（単一スコアが求められる本来の理由）、軸の組み合わせが gaming されうる、出典表示義務の履行形式が未確定。

**根拠**: 設計提案。検証済みの根拠は (1) UMAP '25 論文が成分の単純加算による操作化を明示的に批判し（"A formula that calculates experienced serendipity by summing the components fails to ensure this: one component can score exceptionally high, masking a low score in another"）、成分ごとの最低閾値を代替案として挙げていること、(2) Ecosyste.ms が複数の被依存指標を独立フィールドとして返すこと（dependent_packages_count / dependent_repos_count / docker_dependents_count を実 API 応答で確認）。【重大な留保】調査項目 6 が求めていた「単一スコアへの潰し込みへの批判と代替提示の UI 実例」「スコアの gaming 対策」「説明可能性 UI」は今回の検証で 1 件も生き残っておらず、④⑤は裏付けの無い推測である。また Ecosyste.ms のライセンスが CC BY-SA 4.0 であるという主張は 0-3 で棄却された（＝本調査では確認できなかった）ため、②の「出典表示付き」の具体的義務内容は別途一次確認が必要。

**出典**: https://arxiv.org/abs/2505.15440 / https://packages.ecosyste.ms/api/v1/registries/npmjs.org/packages/express / https://doi.org/10.1145/3699682.3728325

## 3. 留意事項（この調査の限界）

【1. 調査項目の広範な未カバー】検証を通過した 13 主張は、依頼された 7 調査項目のうち実質 1（UI パターンの一部）・2（母集団規模のみ）・4（セレンディピティ研究）・7（無限スクロール a11y）にしか届いていない。**調査項目 3（AI エージェント時代の発見体験・MCP サーバーという提示面・AI 生成スロップ／偽 star 問題）、5（localStorage / Cookie / URL による DB レス個人化の実例、package.json 貼り付け型の文脈入力 UX、プライバシー訴求の UI 表現）、6（独自スコアの提示 UI・説明可能性・gaming 対策）は、支持する主張が 1 件も生き残らなかった**。これらについて本レポートは何も主張できず、未調査領域として扱う必要がある。同様に、解空間 5 軸のうち軸(4) パーソナライズの深さ、軸(5) 目的関数のうち「過小評価度」の実装事例、軸(3) の器のうち CLI・IDE 拡張・MCP・埋め込みウィジェットは実質的に空白のままである。

【2. 棄却された主張（レポートに書いてはならない事項）】以下は敵対的検証で反証・不支持となったため、事実として記載できない。(a) Hugging Face Daily Papers の「AK とコミュニティによる人手キュレーション／年間 3,700 本超／購読者 12,000 人超」（0-3）。(b) Product Hunt の Randomized Leaderboard Day を「上位固定化問題への対処として公式導入した」という目的の帰属、および「イベント中はポイントを完全に隠して中身で投票させる」という仕様（いずれも 0-3）。時間分割の仕様（25/5 分）のみが生き残っている。(c) 「zero-query information retrieval が学術的に定義済みで Google Now / Cortana がその実装形態」という枠組み、および「zero-query 環境ではユーザーモデリングが中核」という命題（いずれも 0-3）— **すなわち本調査は「zero-query」という語の学術的定義を確立できていない**。(d) 「コーディングエージェントが 2025 年 5〜9 月に 100 万件超の PR を作成」（0-3）。(e) 「開発者の 85% が AI ツールを日常利用」「AI 委任タスクの第 2 位が情報検索」（JetBrains, 1-2 / 0-3）。(f) **Ecosyste.ms のライセンスが CC BY-SA 4.0 でありコードが AGPL-3 という主張（0-3）** — gem-hunter が制約として掲げる「出典表示義務」の具体的内容は本調査では確認できておらず、実装前に一次確認が必須。(g) 「novelty はアイテム人気度の逆数として推定するのが一般的で、ユーザー情報ゼロで事前計算できる」（0-3）— **gem-hunter の「過小評価度＝ログイン不要で事前計算可能」という設計前提を支える最も重要な主張が落ちている**。(h) セレンディピティ 3 成分の必要十分性（1-2）、Kotkov らの 8 通り定義の導出（0-2）。

【3. 出典年次の偏り】依頼は「2025〜2026 年の最新事例」を求めたが、生き残った主張の主要出典のうち、NN/g（2022）、Kaminskas & Bridge（2016）、Kotkov ら（2016 / 博論 2018）、Hugging Face 公式ブログ（2024）は 2024 年以前である。2025〜2026 の一次情報として確認できたのは UMAP '25 論文（2025-06）、Product Hunt イベント（2026-03）、Octoverse 2025（2025-11）、Ecosyste.ms のライブ取得値（2026-08-20）に限られる。**「フィード疲れ／無限スクロール離れへの反動として 2025〜2026 に何が起きているか」という設問の中核部分は、2024 年以前のガイダンスで代替されており、現在の状況として断定してはならない。**

【4. 時間依存性】Ecosyste.ms の 4 数値は単調増加のライブカウンタで、同一 URL のキャッシュ版が約 2.5 分の 1 を示すほど揮発性が高い。必ず取得日（2026-08-20）を併記すること。Hugging Face の cadence（週末除外）も 2024 年時点の記述であり現行と異なる可能性がある。Product Hunt の 25/5 分は単日イベント仕様であり恒久機能ではない。

【5. 出典強度の不均一】Kaminskas & Bridge（2016）の実験結果に関する主張は全文が有料で PDF 本体に対する逐語照合ができておらず、掲載誌・論文種別・TLDR との整合による間接確認に留まる（medium）。また当該検証セッションは WebSearch 予算を使い切っており、独立の反証検索が未実施の主張が 2 件ある。

【6. 出典件数】依頼は 8 件以上の出典を求めており、本レポートは 14 の独立 URL を引いているため形式要件は満たすが、実質的な独立ドメイン数は 8（nngroup / huggingface / producthunt / octoverse-github / ecosyste.ms / arxiv-acm / semanticscholar-crossref / jyx.jyu.fi）である。

【7. 方向性候補の性質】末尾 3 件の「方向性候補」は検証済み事実ではなく、検証済み主張から構成した設計提案である。依頼が求めた 3〜5 個に対し 3 個に留めたのは、調査項目 3・5・6 が空白のため、MCP / エージェント向け提示面や localStorage 個人化を軸にした候補を根拠付きで構成できなかったためである。

## 4. 反証・不支持となった主張（引用禁止）

- ❌ Hugging Face Daily Papers はアルゴリズム推薦ではなく人手キュレーション（AK とコミュニティの研究者）で日次の掲載論文を選定しており、1 年間で 3,700 本超を掲載・購読者は 12,000 人超に達した（zero-query 発見面としての「人間キュレーション + 有限な日次単位」の実装例）
- ❌ Product Hunt は 2026 年 3 月に「Randomized Leaderboard Day」を公式導入し、ランキング上位の固定化（同じプロダクトが上位に居座る問題）に対して、リーダーボードそのものをランダム化する運用イベントで対処した。
- ❌ 同イベント中はスコア（ポイント）が公開ビューから完全に隠され、ユーザーが現在の順位ではなく中身の良し悪しで投票するよう誘導している（単一スコアの可視化が評価を歪めることへの実運用上の対処）。
- ❌ 「ゼロクエリ検索（zero-query information retrieval）」は学術的に定義済みの概念で、Google Now / Microsoft Cortana のようなプロアクティブ検索システム（時間・位置・環境・ユーザー興味という文脈に基づいて情報カードをプッシュする方式）がその実装形態として位置づけられている。gem-hunter が目指す「キーワードを入力しない発見体験」は、この zero-query ランキング問題として先行研究の枠組みに乗せられる。
- ❌ ゼロクエリ環境ではクエリという明示的な情報要求シグナルが存在しないため、ユーザーモデリング（ユーザー興味の推定）がシステム性能を左右する中核要素になる、と本論文は明示している。これは「ログイン不要・DB なし＝ユーザーモデルをほぼ持てない」制約下の zero-query 設計が、先行研究の前提（豊富な履歴によるユーザーモデル）と正面から矛盾することを示す。
- ❌ コーディングエージェントによって 2025 年 5〜9 月に 100 万件以上のプルリクエストが作成された。ライブラリ選定を含む開発行為の一部が AI エージェントに移りつつあることを示す一次データで、「人間向け発見 UI」と「エージェント向け提示面（MCP 等）」を分けて設計する根拠になる [A]
- ❌ Ecosyste.ms のデータセットのライセンスは CC BY-SA 4.0（コードは AGPL-3）であり、gem-hunter が「出典表示義務」を制約として扱っているのは公式表記と一致する。派生表示物（スコア・ダイジェスト）にも継承条件が及ぶ点を UI 設計上考慮する必要がある。
- ❌ 開発者が AI に委任するタスクの第 2 位が「開発関連情報のインターネット検索」であり、情報発見行為そのものが AI へ移りつつある（人間向け発見 UI の前提が変わる）。
- ❌ 2025 年時点で開発者の 85% がコーディング・開発に AI ツールを日常的に利用している。
- ❌ 3 成分（fortuitous / refreshing / enriching）はいずれも必要条件であり、3 つ揃って初めて十分条件となる。つまりランダム提示（偶然性のみ）や新着順提示（新鮮さのみ）だけではセレンディピティ体験は成立しない。
- ❌ 新規性（novelty）は、ユーザー個人に依存しない形で「アイテム人気度の逆数」（例: 受け取ったレーティング数）として推定するのが一般的になっている。すなわち novelty はユーザー情報ゼロ（ログイン不要・履歴なし）でもアイテム側の統計だけで事前計算でき、gem-hunter の「過小評価度」的スコアはこの系譜に属する。
- ❌ Kotkov らは文献レビューに基づき serendipity を操作可能な形に分解し、novelty を 2 変種（strict = 聞いたこともない / motivational = 聞いたことはあるが未消費）、unexpectedness を 4 変種（relevant / find = 自力では見つけられなかった / implicit = 普段消費するものと大きく非類似 / recommend = 推薦されるとは思わなかった）に分け、合計 8 通りのセレンディピティ定義を導出した。単一の「セレンディピティ指標」を実装する前にどの変種を採るかの明示が必要となる。

## 5. 未解決の問い

- 「新規性の枯渇」問題（過小評価 OSS の母集団が有限で、日次・週次ダイジェストを続けると数か月で提示可能な候補が尽きる／同じものが再登場する）に対して、既存の OSS ディスカバリー製品（GitHub Explore / Trending、OpenSauced、libraries.io、Openbase、awesome リスト、JavaScript Weekly 等）が実際にどう対処し、何が失敗したのか。今回の検証ではこの領域の主張が 1 件も生き残らず、方向性候補 A の最大の失敗モードが無防備なまま残っている。

- 「過小評価度」を、ユーザー情報ゼロ・ログイン不要・DB なしの条件下でどう定義・事前計算するのか。推薦研究における novelty を「アイテム人気度の逆数」としてユーザー非依存に推定できるという主張は検証で棄却されており、gem-hunter のスコア設計を支える理論的橋渡しが未確立である。被依存数／star 比という素朴な比率が、Kaminskas & Bridge や Kotkov らの novelty / unexpectedness のどの定義変種に対応するのかを明示する必要がある。

- Ecosyste.ms のデータライセンスと出典表示義務の正確な内容は何か。CC BY-SA 4.0 という前提は本調査で確認できなかった。とくに ShareAlike が gem-hunter の派生表示物（スコア・ダイジェスト JSON）に継承されるのか、UI 上でどの粒度の帰属表示が必要かは、実装前に一次情報（ecosyste.ms/api・各リポジトリの LICENSE）で確定させる必要がある。また 1470 万パッケージをレート制限 5000 req/hour 下でどう harvest するか（bulk dump 経路の有無）も未解決。

- AI コーディングエージェントがライブラリ選定を代行し始めた状況で、人間向けの発見 UI とエージェント向けの提示面（MCP サーバー等）をどう分けて設計すべきか。また偽 star・AI 生成スロップが混入する母集団に対し、被依存数ベースの指標がどこまで耐性を持つのか。この領域は調査項目 3 として依頼されたが、支持された主張がゼロであり完全に未調査である。

## 6. 出典一覧

1. [?] https://humanebydesign.com/principles/finite — https://humanebydesign.com/principles/finite
2. [?] https://www.nngroup.com/articles/infinite-scrolling-tips/ — https://www.nngroup.com/articles/infinite-scrolling-tips/
3. [?] https://huggingface.co/blog/daily-papers — https://huggingface.co/blog/daily-papers
4. [?] https://www.producthunt.com/p/producthunt/introducing-randomized-leaderboard-day-on-product-hunt — https://www.producthunt.com/p/producthunt/introducing-randomized-leaderboard-day-on-product-hunt
5. [?] https://www.microsoft.com/en-us/research/publication/modelling-user-interest-for-zero-query-ranking/ — https://www.microsoft.com/en-us/research/publication/modelling-user-interest-for-zero-query-ranking/
6. [?] https://www.deque.com/blog/infinite-scrolling-rolefeed-accessibility-issues/ — https://www.deque.com/blog/infinite-scrolling-rolefeed-accessibility-issues/
7. [?] https://github.com/orgs/community/discussions/179946 — https://github.com/orgs/community/discussions/179946
8. [?] https://www.producthunt.com/products/openbase — https://www.producthunt.com/products/openbase
9. [?] https://octoverse.github.com/ — https://octoverse.github.com/
10. [?] https://packages.ecosyste.ms/ — https://packages.ecosyste.ms/
11. [?] https://daily.dev/blog/github-trending-alternatives-spot-rising-repos-early/ — https://daily.dev/blog/github-trending-alternatives-spot-rising-repos-early/
12. [?] https://blog.jetbrains.com/research/2025/10/state-of-developer-ecosystem-2025/ — https://blog.jetbrains.com/research/2025/10/state-of-developer-ecosystem-2025/
13. [?] https://arxiv.org/abs/2505.15440 — https://arxiv.org/abs/2505.15440
14. [?] https://www.semanticscholar.org/paper/Diversity,-Serendipity,-Novelty,-and-Coverage-Kaminskas-Bridge/0a2a1bfeea7a572a78cd12a79f3b00911aa9bba4 — https://www.semanticscholar.org/paper/Diversity,-Serendipity,-Novelty,-and-Coverage-Kaminskas-Bridge/0a2a1bfeea7a572a78cd12a79f3b00911aa9bba4
15. [?] https://www.sciencedirect.com/science/article/abs/pii/S0950705116302763 — https://www.sciencedirect.com/science/article/abs/pii/S0950705116302763
16. [?] https://dl.acm.org/doi/full/10.1145/3554819 — https://dl.acm.org/doi/full/10.1145/3554819
17. [?] https://www.mdpi.com/2078-2489/16/2/151 — https://www.mdpi.com/2078-2489/16/2/151
18. [?] https://developers.cloudflare.com/workers/platform/limits/ — https://developers.cloudflare.com/workers/platform/limits/
19. [?] https://github.com/47ng/nuqs — https://github.com/47ng/nuqs
20. [?] https://rxdb.info/articles/localstorage.html — https://rxdb.info/articles/localstorage.html
21. [?] https://toolshref.com/npm-dependency-visualizer/ — https://toolshref.com/npm-dependency-visualizer/
22. [?] https://cmustrudel.github.io/papers/icse2026fakestars.pdf — https://cmustrudel.github.io/papers/icse2026fakestars.pdf
23. [?] https://arxiv.org/html/2503.17181 — https://arxiv.org/html/2503.17181
24. [?] https://socket.dev/blog/slopsquatting-targets-across-frontier-llms — https://socket.dev/blog/slopsquatting-targets-across-frontier-llms
25. [?] https://github.com/ossf/criticality_score — https://github.com/ossf/criticality_score
26. [?] https://www.w3.org/WAI/ARIA/apg/patterns/feed/examples/feed/ — https://www.w3.org/WAI/ARIA/apg/patterns/feed/examples/feed/
27. [?] https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Reference/Roles/feed_role — https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Reference/Roles/feed_role
28. [?] https://www.wcag.com/developers/2-5-7-dragging-movements/ — https://www.wcag.com/developers/2-5-7-dragging-movements/
