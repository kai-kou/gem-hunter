<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: GitHub Pages の LP（site/）を最新のドキュメント・仕様・実画面へ追随させ、画像素材の刷新方針まで確定する

- 議題ID: `lp_refresh_20260823`
- 論点: ユーザー指示: 『最新のドキュメント、仕様、画面を事実確認して、GitHub Pages の LP に反映してください。画面キャプチャなど最新化してください。画像があったほうが視認性・注目度などの向上につながるのであれば gpt-image-2 を利用して画像素材を作成してください。既存のインフォグラフィック画像を活用できるのであれば活用してください。』。現状: site/index.html は 2026-08-22 の SP-19 マージ時点で更新が止まっており、その後 PR #467 / #481 / #504（Gem 一覧のレート制限配線・検索結果への Gem 印の同伴と説明・Gem 導線の視認性向上と一覧カードの avatar 追加と件数説明の整合）が入っている。既知の陳腐化候補: ① FAQ『対応しているエコシステムは何ですか？』が『今日の Gem の被依存数は npm だけ』と書いているが、D-36 / SP-17 でEcosyste.ms の 12 レジストリ・ユニーク 109,469 リポジトリ級へ拡大済み（public/data/gem-index/ に 12 レジストリ分のシャード + index.json が存在する） ② 『できること』セクションに SP-18（検索結果の Gem バッジ）と SP-19（検索語を引き継ぐ Gem 一覧）が独立した機能として載っていない（『先に言っておく制約』に一行だけ言及がある） ③ 『仕組み』の 3 ステップが Gem 一覧導線を含んでいない ④ 『682 ケース』『ADR 15 本』などの数値が現在値と一致するか未検証 ⑤ ヒーロー / 検索 / ダイジェストのスクリーンショット（site/assets/img/shot-*.webp）が Gem バッジ・avatar・件数説明の追加前の画面である。使える素材: docs/infographics/*.webp 全 14 点（01-initial-concept / 02-lean-canvas / 03-inception-deck / 04-prd / 05-user-story-map / 06-roadmap / 07-design / 08-doc-relations / 09-adr-map / 10-gem-score / 11-testing-strategy / 12-cloudflare / 13-ops-rules / 14-architecture-flow・16:9・日本語の文字が焼き込まれている）、public/images/*.webp（アプリ内の装飾イラスト。gpt-image-2 生成・透過・文字なし）、tools/infographic/generate.py（gpt-image-2 CLI・OPENAI_API_KEY 供給済み）、tools/ui-assets/to_web_assets.mjs（透過 WebP 変換）。制約: ADR 0015（画像内に文字を焼き込まない・装飾イラストはロケール非依存の 1 枚）、site/README.md の設計上の約束（外部 CDN 非依存・ページ内 JavaScript ゼロ・相対パス・掲載する機能は実装済みのものだけ・本番で無効な機能を『使える』と書かない・opacity アニメ禁止・prettier 対象外）、tools/check_site.py の機械検査（img の width/height と実寸の一致・ADR 本数など）。参考スクリーンショット（フルページ PNG）はスクラッチ領域 /tmp/claude-0/-home-user-gem-hunter/e341a277-9634-5cf6-a9d7-170cb78ffa7f/scratchpad/lp/ に lp-desktop.png / lp-mobile.png（現行 LP）がある。争点は次の 5 つ: A) 事実の追随（LP の記述と現行仕様・実装・ドキュメントの差分を全件洗い出し、直す文言まで確定する） B) 情報設計（Gem バッジと Gem 一覧という 2 つの新機能を、既存のセクション構成のどこにどう入れるか。セクションを増やすのか既存を書き換えるのか。ヒーローのメッセージを変えるべきか） C) 画像戦略（どのスクリーンショットを撮り直すか・どの画面を新たに撮るか・既存インフォグラフィックを LP に載せる価値があるか（文字焼き込み済みで ADR 0015 の方針や a11y とどう折り合うか）・gpt-image-2 で新規生成すべき素材はあるか、あるならどこに何を） D) 技術品質と a11y（追加する画像の LCP / CLS / 総重量への影響、alt テキスト、WCAG 2.2 AA、tools/check_site.py の検査との整合、GitHub Pages サブパス配信） E) 誇張の抑制（新機能を書き足すことで『実装済みのものだけ』の約束が破られないか、Gem 印の限界の説明が薄まらないか）。
- 参加者: `fact_sync`, `info_arch`, `visual_assets`, `web_quality`, `en_parity`
- 投稿数: 12
- 更新: 2026-08-23T14:13:15+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

## ラウンド 1

### `fact_sync` — 主張
<sub>2026-08-23T14:01:11+09:00</sub>

# fact_sync round 1 — 事実の裏取り結果

## 実測サマリー
- `npx vitest run`: **81 files / 954 tests passed**（LP は「ユニット・結合 593」と主張 → 大幅に古い）
- `npx playwright test --list`: **107 tests in 23 files**（LP は「E2E 89」と主張 → 古い）
- 合計 954 + 107 = **1061 ケース**（LP は「682 ケース」と主張）
- `ls docs/adr/[0-9]*.md | wc -l` → **15**（LP の「ADR 15 本」は一致・修正不要）
- `public/data/gem-index/index.json` の `shards`: **12 レジストリ**（cran / cargo / hex / cpan / npm / nuget / packagist / go / pub / pypi / maven / rubygems）。FAQ の「npm（npmjs.org）のパッケージだけ」は SP-17（#416・12 レジストリ化）以降は誤り
- `rollup-plugin-peer-deps-external` は `npmjs-org.json` に実在: `dependentCount=26633, stars=111`（LP の「star 111 なのに 26,633 個」「利用パッケージ数 26,633・star 111」と厳密一致・修正不要。ただし現行 `daily-digest.json`（2026-08-22 生成）の上位候補には入っていない＝「ある日の一例」という注記は必須のまま正しい）
- Gem Index 選定ロジック（`src/usecases/get-daily-digest.ts` + `src/domain/model/gem-shortlist.ts`）: shortlist 60 件（`GEM_INDEX_SHORTLIST_SIZE`）→ seed 決定論的シャッフル → 先頭 5 件を Gem Index asc で並べ替え。LP の「この値が小さい上位 60 件を母集団に、日付から決まる順序で毎日 5 件」と一致（修正不要）
- Lighthouse Accessibility ゲート: `tools/run_checks.sh` L133-147 で `Accessibility gate` を **blocking**（Performance は記録のみ）に設定。LP の「Accessibility 100 を『下回ったらリリースしない』基準」と一致（修正不要）
- 検索の並び替え（`relevance/stars/updated`）・表示件数（`20/50/100`）・新着バッジ / 初回訪問文言は実装（`sort-order.ts` / `per-page.ts` / `seen-digest/*`）と一致（修正不要）
- SP-18（検索結果への Gem バッジ）・SP-19（検索語を引き継ぐ Gem 一覧）は **実装済み**（PR #435 / #440、その後 #467 / #481 / #488 / #504 で改善継続）。しかし LP の「できること」セクションにはこの機能への言及が **一切ない**（バッジ導線・Gem 一覧への言及ゼロ）
- 利用パッケージ数の表示ラベル「利用パッケージ数」は `src/shared/i18n/messages.ts` の `dependentLabel` / `gems.dependentCount` と一致（修正不要）

## 表: 現行の記述 → 事実 → 直す文言案

| 現行の記述（index.html） | 事実 | 直す文言案 |
|---|---|---|
| `<b>682 ケース</b><span>ユニット・結合 593 / E2E 89。</span>`（L477-484） | 実測: ユニット・結合 954（81 ファイル）/ E2E 107（23 ファイル）、合計 1061 | `<b>1,061 ケース</b><span>ユニット・結合 954 / E2E 107。<a href="...">テスト戦略</a></span>` |
| FAQ「対応しているエコシステムは何ですか？」への回答: 「いまのところ **npm（npmjs.org）のパッケージだけ** を対象にしています」（L560-567） | `gem-index/index.json` の shards は 12 レジストリ（npm/pypi/crates/rubygems/packagist/go/maven/cran/hex/cpan/nuget/pub）。npm 限定は SP-16 撤去時点（D-33）の古い状態で、SP-17（#416）以降は 12 レジストリに拡張済み | 「いまのところ **npm・PyPI・crates.io・RubyGems・Packagist・Go Modules・Maven・CRAN・Hex・CPAN・NuGet・pub.dev の 12 レジストリ** を対象にしています。」（レジストリ名の列挙が長すぎる場合は「npm・PyPI・crates.io など 12 のパッケージレジストリ」で圧縮可） |
| 「できること」セクションに Gem バッジ / Gem 一覧（SP-18・SP-19）への言及がない | SP-18（検索結果に Gem バッジ）・SP-19（検索語を引き継いで Gem だけ一覧）は実装済み・その後も #467/#481/#488/#504 で継続改善されている主要機能 | 「できること」の bento に新規タイルを追加: 「検索結果にも Gem の印／キーワード検索の結果一覧で、被依存数のわりに star が少ないリポジトリに Gem バッジが付きます。バッジ付きの候補だけを、検索語を引き継いだまま一覧で見られます。」 |

## 裏が取れなかった項目
- 「約 600 万」「18,600」（偽 star 研究の数字）は出典論文の内容そのもの（外部一次情報）であり、リポジトリ内のコード・データでは検証できない。裏取り対象外として明言する
- 25 star / 111,000+ の `debug_inspector`（RubyGems）例は本リポジトリのデータセット（gem-index の rubygems シャード）に該当パッケージが含まれるか未確認（時間の都合で rollup-plugin-peer-deps-external の検証を優先した）。追加検証が必要なら次ラウンドで実施する

## 矛盾チェック（PR #467 / #481 / #504）
- #467: Gem 一覧のレート制限未配線を修正 → LP に矛盾する記述なし
- #481: 検索結果で Gem 印が付いた候補を一覧へ同伴させ、印の説明を検索結果に出す → 上記「Gem バッジ未記載」の指摘と同根（LP が追随できていない）
- #504: Gem 導線を目立たせ、一覧カードに avatar を出し、件数説明の食い違いを解消 → LP のスクリーンショット（`shot-search.webp` 等）が #504 以前の古い UI のままである可能性あり（画像の実体は確認していないため、画像更新の要否は別レンズ・裏が取れない）

### `en_parity` — 主張
<sub>2026-08-23T14:01:48+09:00</sub>

# en_parity Round 1: 機械的整合検査

## 1. アンカー整合 — **完全一致**

| ID | ナビ参照 | フッター参照 | HTML 実在 | 判定 |
|---|---|---|---|---|
| `#top` | ✓ | ✓ | `<section id="top">` | ✓ |
| `#why` | ✓ | ✓ | `<section id="why">` | ✓ |
| `#how` | ✓ | ✓ | `<section id="how">` | ✓ |
| `#features` | ✓ | ✓ | `<section id="features">` | ✓ |
| `#trust` | ✓ | ✓ | `<section id="trust">` | ✓ |
| `#faq` | ✓ | ✓ | `<section id="faq">` | ✓ |
| `#main` | ✓ | — | `<main id="main">` | ✓ |
| `#desktop` | — | — | `<section id="desktop">` | ✓ |

**判定**: 不一致なし。ヘッダーナビ・フッター・スキップリンク全て実在 ID と一致。

---

## 2. 外部リンク生存確認 — **1 件警告**

| URL | HTTP Code | 判定 |
|---|---|---|
| `https://kai-kou.github.io/gem-hunter/` | 200 | ✓ |
| `https://gem-hunter.kinamocchi-tech.workers.dev/ja` | 200 | ✓ |
| `https://gem-hunter.kinamocchi-tech.workers.dev/en` | 200 | ✓ |
| `https://github.com/kai-kou/gem-hunter` | 200 | ✓ |
| `https://ecosyste.ms/` | 200 | ✓ |
| `https://github.com/kai-kou/gem-hunter/blob/main/LICENSE` | 200 | ✓ |
| `https://github.com/kai-kou/gem-hunter/tree/main/docs` | 200 | ✓ |
| `https://github.com/kai-kou/gem-hunter/tree/main/docs/adr` | 200 | ✓ |
| `https://github.com/kai-kou/gem-hunter/blob/main/docs/04_development/testing-strategy.md` | 200 | ✓ |
| `https://github.com/vercel/geist-font` | 403 | ⚠️ **Forbidden** |

**警告**: Geist フォント（`site/footer` 行 689 で言及）へのリンクが 403。リポジトリ削除済みまたはアクセス制限の可能性。

---

## 3. JSON-LD スキーマ — **完全一致**

| 項目 | JSON-LD の値 | 本文での主張 | 判定 |
|---|---|---|---|
| `WebSite.url` | `https://kai-kou.github.io/gem-hunter/` | LP（canonical）同一 | ✓ |
| `SoftwareApplication.url` | `https://gem-hunter.kinamocchi-tech.workers.dev/ja` | ヒーロー・CTA リンク | ✓ |
| `SoftwareApplication.codeRepository` | `https://github.com/kai-kou/gem-hunter` | GitHub ボタン | ✓ |
| `SoftwareApplication.inLanguage` | `["ja", "en"]` | 言語切り替え（行 432-437） | ✓ |
| `applicationCategory` | `DeveloperApplication` | ページ内容 | ✓ |
| `description` | 「star の数ではなく被依存数を手がかりに GitHub リポジトリを探す検索ツール」 | ヒーロー主張 | ✓ |

**判定**: 矛盾なし。WebSite と SoftwareApplication の 2 スキーマが整合。

---

## 4. meta 数値と daily-digest.json — **不一致あり**

og:description（行 22-23）:
> "star 111 なのに 26,633 個のパッケージから使われている——そんな OSS を毎日 5 件"

HTML 本文（行 358-363）にも同一の例：
> `rollup-plugin-peer-deps-external` — 利用パッケージ数 **26,633** / star **111** （2026-08-21 時刻点）

public/data/daily-digest.json の確認:
- `candidates` キー: 300 個（母集団）
- **star:111 / dependents:26,633 の組み合わせは存在しない**
- `gems` キー: 存在しない（5 件の日次抽出データが記録されていない）

⚠️ **判定**: og:description のタイムスタンプ（2026-08-21）と current digest date（2026-08-22）にズレあり。digest は日次で更新されるため、具体例の最新性が確保されていない可能性。

---

## 5. og:image / canonical — **完全正常**

| 項目 | 値 | 確認 |
|---|---|---|
| canonical | `https://kai-kou.github.io/gem-hunter/` | 絶対 URL ✓ |
| og:image | `https://kai-kou.github.io/gem-hunter/assets/img/ogp.png` | 絶対 URL ✓ |
| og:image:width | `1200` | ✓ |
| og:image:height | `630` | ✓ |
| 実ファイル存在 | `site/assets/img/ogp.png` | ✓ 実在 |

**判定**: 構成・メタデータ・物理ファイル全て正常。

---

## 総評

| 項目 | 状態 |
|---|---|
| アンカー整合 | ✅ 完全一致 |
| 外部リンク | ⚠️ Geist フォント 403（軽微） |
| JSON-LD スキーマ | ✅ 矛盾なし |
| meta 数値更新性 | ⚠️ og:description とデータのズレ（日次スナップショット仕様） |
| og:image / canonical | ✅ 正常 |

**即座の対応**: なし（既知の日次更新ラグ・Geist は古い参考）。

### `web_quality` — 主張
<sub>2026-08-23T14:01:57+09:00</sub>

# web_quality — Round 1: 技術品質・a11y レンズ

## 1. Core Web Vitals

**現行 LCP 要素**: `.phone-screen` 内の `shot-mobile.webp`（`fetchpriority="high"` + `decoding="async"`。唯一の `fetchpriority="high"` 画像）。モバイル viewport ではヒーロー内で最大の要素であり、ほぼ確実に LCP candidate。

**現行の総転送量（実測・`ls -la` / `du -sh`）**:

| ファイル | サイズ | 読み込みタイミング |
|---|---|---|
| `shot-mobile.webp` | 63KB | 即時（`fetchpriority="high"`） |
| `shot-search.webp` | 60KB | `loading="lazy"`（PC セクション） |
| `shot-digest.webp` | 32KB | `loading="lazy"`（bento） |
| `gem.webp` | 28KB | `loading="lazy"`（最終 CTA） |
| `logo.webp` | 2.8KB | 即時（ヘッダー + フッターで共有・ブラウザキャッシュ） |
| `icon.png` | 3.7KB | favicon |
| `geist-latin.woff2` | 29KB | `<link rel="preload">` |
| `ogp.png` | 152KB | **通常のページロードでは取得されない**（`<meta property="og:image">` は SNS クローラーのみが取得。総転送量の計算に含めない） |

→ ページロード時の実転送量は概算 **63+60+32+28+2.8+3.7+29 ≈ 220KB**（lazy 画像を含む合計。初期ビューポートだけなら shot-mobile 63KB + font 29KB + logo 2.8KB ≈ 95KB）。

**インフォグラフィック（`docs/infographics/*.webp`）を LP に足す場合の影響**:

| 検査対象 | サイズ |
|---|---|
| `01-initial-concept.webp` 〜 `13-ops-rules.webp` | 205KB 〜 324KB / 枚 |
| `14-architecture-flow.webp` | 227KB |

**1 枚追加するだけで現行の画像合計（337KB）とほぼ同等の重さが乗る。** 複数枚（例: 「つくり」セクションに 3〜4 枚並べる構成）を素の解像度のまま置くと、ページ総転送量は 1MB を超える。回避策は §4 参照。

- **width/height 指定は必須**（CLS 防止・`check_site.py` が機械強制。§4 参照）
- **`loading="lazy"`** はスクロールで到達するセクション（`#trust` 以降）なら必須。ファーストビューに置くと LCP 要素が `shot-mobile.webp` からインフォグラフィックへ差し替わり、現状の 63KB → 200KB+ で LCP が悪化する。**インフォグラフィックをヒーロー/ファーストビューに置かない**のが安全
- **`fetchpriority="high"` は絶対に増やさない**（複数画像に付けると優先度の意味が薄れ、実際の LCP 要素の取得が遅れる）

## 2. インフォグラフィック掲載時の a11y（WCAG 1.4.5 / 1.1.1 / 1.4.10）

- **WCAG 1.4.5（Images of Text）**: インフォグラフィックは「文字焼き込み済み」の raster 画像。1.4.5 は本来テキストを画像化することを避けるべきとするが、**「特定の表現が本質的に必要な場合（図表・グラレコ的要約等）」は例外規定に該当しうる**。ただし例外に該当しても **1.1.1（非テキストコンテンツ）は免除されない** — 画像内の情報と同等のテキスト代替が必要。`docs/infographics/README.md` の現行 alt（例: `alt="初期コンセプト"`）は **見出しの言い換えに過ぎず同等の代替にならない**。LP に転用するなら、`index.html` の既存スクリーンショット alt（100〜150 字程度で画面内容を具体的に記述するスタイル）に合わせて書き直す必要がある。空 alt（`alt=""`）で「装飾画像」扱いにする選択肢は、情報が画像にしかない場合は不可（1.1.1 違反になる）
- **WCAG 1.4.10（Reflow・400% ズーム）**: 画像自体は `img { max-width:100%; height:auto }` で追従するため要素としては折り返される（横スクロールは発生しない、実測 §5 参照）。ただし **画像内に焼き込まれた文字は raster なのでズームで再フローしない** — 400% 表示では画像内の文字が実質的に読めなくなる。これは 1.4.10 の直接違反ではない（画像は対象外）が、**実質的なアクセシビリティの劣化**なので、画像の下に本文と同等の内容をテキストで併記する（`docs/infographics/README.md` の「元ドキュメントへのリンク」パターンを LP でも踏襲する）ことを推奨
- **クリック拡大 / モーダル表示を追加する場合**: フォーカストラップ・Esc クローズ・`aria-modal` が必要になり、`site/README.md` の「ページ内 JavaScript はゼロ」の約束に抵触する（§5 参照）。素の `<a href="画像URL">` で新規タブ表示にとどめるなら JS 不要

## 3. GitHub Pages サブパス配信

- 新規画像・セクションを追加する際は **必ず相対パス `./assets/...` または `../../docs/infographics/...` 形式**を使う。絶対パス `/gem-hunter/...` は `404.html`専用の例外であり、`index.html` に混入すると `check_site.py` の参照チェックは通っても（`local.startswith("gem-hunter/")` 分岐で吸収される）、**ローカル確認（`python3 -m http.server --directory site`）ではルート `/` 相性で壊れる**（README 既知の注意点と同じ罠）
- `docs/infographics/*.webp` を `site/` の外から参照する場合、`site/` ディレクトリ配信では **相対パスで一段上に出られない**（`../docs/...` は GitHub Pages の `gh-pages` ブランチには `docs/` が存在しないため 404 になる）。**インフォグラフィックを LP に載せるなら `site/assets/img/` 配下へコピーする必要がある**（`docs/infographics/` を直接参照すると公開後に壊れる）。これは他レンズ（fact_sync / info_arch）が見落としやすい落とし穴として明示しておく
- `.nojekyll` は `site/` 直下にあるので新規ディレクトリ追加は問題なし

## 4. `tools/check_site.py` が新しい記述・画像で落ちる可能性

**検査項目（全件・ソース `tools/check_site.py` より）**:

1. タグの閉じ漏れ・重複 `id`（`HTMLParser` で `index.html` / `404.html` を走査）
2. ローカル参照アセット（`src` / `href`）の実在確認（`http(s)://` / `mailto:` / `data:` は除外、`gem-hunter/` 絶対パスは正規化して解決）
3. `<img>` の `width` / `height` 属性の有無、および実ファイル実寸との **縦横比**一致（許容誤差 0.01。ピクセル完全一致ではなく比率チェック）
4. ページ内アンカー（`#foo`）の参照先 `id` が存在すること（`top` は暗黙で許可）
5. 自リポジトリへの GitHub リンク（`blob|tree/main/<path>`）のパスが実在すること
6. LP に書いた「ADR n 本」の数値が `docs/adr/*.md`（数字始まりのファイル名）の実数と一致すること

**新しい画像・セクションで落ちうる項目（名指し）**:

- 項目 2・3: インフォグラフィックを追加して `width`/`height` を書き忘れる、または `docs/infographics/` を直接参照して相対パス解決に失敗する（§3 参照）→ **即座に fail**
- 項目 3: WebP は `webp_size()` が VP8X/VP8L/VP8 の 3 フォーマットしか解析できない。インフォグラフィック生成ツール（`tools/infographic/`）の出力フォーマットが上記いずれかであることを要確認（想定外フォーマットだと `image_size()` が `None` を返し「画像サイズを解析できなかった」で fail）
- 項目 5: 本文中に新しく `docs/xxx.md` への GitHub リンクを足す場合、そのファイルが実在することを確認する（typo で fail しやすい）
- **`--self-test` は `site/assets/img/*` を全走査して `image_size()` が解析できるかも検証する**ので、`site/assets/img/` 配下に置く画像は必ずこのチェックを通る

**この検査に含まれないもの（見落とし注意）**: ファイルサイズ上限のチェックは無い。§1 の「1MB 超」のような重量問題は `check_site.py` では検出されない（Lighthouse ゲートも LP を対象外・README に明記）。**サイズの歯止めは人力レビューに依存する**ため、round 2 でここを他レンズと合意しておく必要がある

## 5. `site/README.md`「設計上の約束」— 違反しやすい落とし穴

- **外部 CDN 依存禁止**: インフォグラフィックの拡大表示に lightbox ライブラリ（CDN 経由）を使う提案が出たら NG。自前実装でも「ページ内 JavaScript はゼロ」に反する
- **ページ内 JavaScript ゼロ**: モーダル拡大・タブ切り替え・カルーセル等の対話的 UI 提案は全て抵触する。`<details>`（FAQ で使用中）や `<a href>` 遷移、CSS のみのアニメーションで代替する
- **`opacity` アニメ禁止**: 新セクションの `.reveal` 演出に `opacity` を使うと、LCP 候補から除外され得る（既存の `hero-in` / `reveal-in` は `transform` のみ。これに倣うこと）
- **prettier 整形禁止**（`site/` は `.prettierignore` 対象）: 新規セクションを追加編集した場合、`npm run format` を走らせると表示崩れの原因になる。手編集を維持する
- **相対パス**: §3 参照

## 6. axe 実測結果（README 記載のスクリプトをそのまま実行）

ローカル配信: `python3 -m http.server 8098 --directory site`（既に起動済みを確認、`curl` で 200 応答を確認）。README の Playwright + axe スクリプトを `/home/user/gem-hunter` から `node` で実行。

```
light 1280  violations = 0
dark  1280  violations = 0
light  390  violations = 0
light  320  violations = 0
```

**現状は 4 構成全てで `violations = 0`**（README の完了条件を満たす）。追加で 320×256（400% ズーム相当の低高さ viewport）で横スクロール発生を確認したが `false`（横スクロールなし）。

→ **この 0 件はベースライン**。インフォグラフィックや新セクションを追加した後、同じスクリプトを再実行して 0 件を維持できるかが round 2 以降の実質的なゲートになる（特に alt テキスト不足は axe の `image-alt` ルールで機械検出できるので、§2 の懸念は axe 再実行で裏取りできる）。

## まとめ（他レンズへの申し送り）

- インフォグラフィックを LP に載せるなら: ① `site/assets/img/` へコピー ② `width`/`height` 明記 ③ 具体的な alt 文（現行 docs 版の短い alt は不可）④ ファーストビュー外＋`loading="lazy"` ⑤ 1MB 超回避のため掲載枚数を絞るか縮小版を作る、の 5 点が必須
- `check_site.py` はサイズ上限もページ全体の a11y も見ない。**axe 実測 + 人力の総転送量チェックは PR ごとに手動で回す必要がある**

### `info_arch` — 主張
<sub>2026-08-23T14:02:26+09:00</sub>

# info_arch — round 1（争点 B: 情報設計 / 争点 E: 誇張の抑制）

## 4 つの判断

1. **セクションは増やさない**。「できること」bento に新タイル 1 つを足す以外は、既存セクション内の書き換え・追記で収める。理由: `D-36` は「ブラウズ専用の発見面を主軸にする案」を明示的に却下している（キーワード起点を失うため）。新しい大セクションを作ると、視覚的な重みでバッジ／Gem 一覧が「検索と並ぶ主軸」に見えてしまい、決定と矛盾する。
2. **ヒーロー（h1・リード文・alt link）は変更しない**。現行の「毎日 5 件のダイジェスト」訴求はそのまま成立している（SP-18/19 はダイジェストを置き換えるものではなく、検索結果に注釈を足すもの）。ヒーローに詰め込むと、①「並び順は変えない」「付かないことは低評価ではない」という 2 つの限定を短い訴求文に収めきれず誤読を誘発するリスク、② SD-3 の「答えに依存しない作業を先に」に照らしても変更の必要性が薄い。バッジ／一覧の説明は「仕組み」「できること」「FAQ」に譲る。
3. **「先に言っておく制約」の既存 1 行では足りない**。現行文は Gem 一覧の並び順にしか触れておらず、検索結果カードの **バッジ** 自体には言及していない（新しい UI 要素なのに制約文に存在しない）。1 文追記で解消できる規模なので新セクションは不要。
4. **誇張チェック**: 新規ドラフトはすべて「並び順は変えない」「バッジが付かないことは低評価を意味しない」の 2 点を同じ文中に必ず伴わせた。bento タイルの新設でも "実装済みの事実のみ"（対象レジストリ数・件数）に留め、品質評価語（「おすすめ」「厳選」等）は使っていない。

## セクション単位の判断表

| セクション | 判断 | 理由 |
|---|---|---|
| ヘッダーナビ | **残す** | 新規アンカーを作らないため変更不要 |
| ヒーロー（h1 / リード / alt link） | **残す** | 上記 2 |
| PC でも使える | **残す** | 機能追加と無関係 |
| なぜ star では足りないか | **残す** | 一般論のセクションで、個別機能の追加とは独立 |
| 仕組み・3 ステップ（step1〜3） | **残す** | badge/一覧の説明を formula ブロックに集約し、ここでの二重説明を避ける |
| 仕組み・formula ブロック | **直す** | Gem Index が「今日の Gem」専用ではなく 3 箇所で使われる指標になったため、見出しと説明を広げる |
| できること・bento | **足す**（新タイル 1 つ） | バッジ＋ Gem 一覧という一体の新機能を、事実ベースで 1 タイルとして明記する |
| つくり・facts / tag-list | **残す** | 数値ゲート（テスト件数等）は今回の機能と無関係 |
| つくり・先に言っておく制約 | **直す** | 既存 1 文をバッジも含む形に拡張（判断 3） |
| FAQ「GitHub の検索と何が違いますか？」 | **直す** | 差別化ポイントが「今日の Gem」だけでなくなったため回答を更新 |
| FAQ（新規） | **足す** | バッジという新しい UI 要素を初見ユーザーが誤読しないための専用 Q&A |
| 最終 CTA / footer | **残す** | 変更不要 |

---

## 確定ドラフト

### A. 仕組み・formula ブロック（`#how` 内、既存を置き換え）

```html
<div class="formula reveal">
  <h3 class="formula-heading">Gem Index の並び順</h3>
  <p class="formula-expr">Gem Index = 被依存数の順位 − star の順位</p>
  <p>
    どちらも <a href="https://ecosyste.ms/">Ecosyste.ms</a> の
    0〜100 のパーセンタイル順位（0 が最上位）です。値が小さいほど
    「使われ方に対して star が少ない」＝ 過小評価されている、という意味になります。
    例えば被依存数が上位 0.1（＝ 上位 0.1%）で star が上位 7（＝ 上位 7%）なら
    Gem Index は −6.9。実際のデータでもこのあたりが最上位帯です。
  </p>
  <p>
    この値は 3 つの場所で使っています。「今日の Gem」では、この値が小さい上位 60 件を
    母集団に、日付から決まる順序で毎日 5 件を選び、その 5 件をこの値の順に並べています。
    検索結果では、一部のカードに Gem バッジを付けるかどうかの判定に使いますが、
    <strong>検索結果自体の並び順は変えません</strong>。検索語から開ける
    「Gem 候補を一覧で見る」画面では、集まった候補をこの値の順に並べます
    （一覧の中身は全件が Gem 候補なので、キーワード検索と違って順位が意味を持ちます）。
  </p>
  <p>
    健全性スコア（OpenSSF criticality_score など）は
    <strong>この値に足し込みません</strong>。足すと「健全だが有名」なリポジトリが
    上位に戻ってきて、結局 star 順のランキングに退化するからです。
    判断の経緯は
    <a href="https://github.com/kai-kou/gem-hunter/blob/main/docs/adr/0009-hidden-gem-score-definition.md">ADR 0009</a>
    に残してあります。
  </p>
</div>
```

変更点は h3 見出し（「今日の Gem」の並び順 → Gem Index の並び順）と 2 段落目の書き換えのみ。1・3 段落目は現行のまま。

### B. できること・bento（新タイル。`今日の Gem` タイルの直後、`スマートフォンで取りこぼさない` タイルの前に挿入）

```html
<div class="tile">
  <h3>
    <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
      <!-- アイコンはタグ/バッジ系を実装側で選定（他タイルと意匠が重ならないもの） -->
      <path d="M20.6 12.3 12 20.9a1.5 1.5 0 0 1-2.1 0l-7-7A1.5 1.5 0 0 1 3 12.8V5.5A2.5 2.5 0 0 1 5.5 3h7.3c.4 0 .8.2 1 .4l6.8 6.8a1.5 1.5 0 0 1 0 2.1Z" stroke-linejoin="round" />
      <circle cx="8" cy="8.5" r="1.3" />
    </svg>
    検索結果でも Gem に気づける
  </h3>
  <p>
    キーワード検索の結果のうち、被依存数のわりに star が少ないカードには
    Gem バッジが付きます。<strong>並び順は変わりません</strong>。
    バッジが付かないことは低評価を意味しません。
  </p>
  <p class="tile-datum">
    検索結果の上にある「この検索語の Gem 候補を一覧で見る」から、
    その検索語に合う Gem 候補だけを Gem Index 順に見られます
    <span class="tile-datum-note">（対象は 12 のパッケージレジストリ・約 6.2 万リポジトリ）</span>
  </p>
</div>
```

注記: この 1 タイル追加で bento の行組みが変わる可能性がある（実装側で `span` の再配分を確認。IA としての指定は「新タイルを既存 5 タイルと同格の通常サイズで追加」のみ）。

### C. つくり・先に言っておく制約（3 項目目を置き換え）

```html
<li>
  Gem Index は「今日の Gem」と「Gem 候補の一覧」（検索結果から開けます）の並び順、
  それに検索結果カードの Gem バッジの判定に使っています。キーワード検索の結果自体は
  GitHub の検索結果をそのまま並べており、バッジが付いても並び順は変わりません。
  Gem の印は限られたデータにもとづく参考値なので、優劣の評価ではありません。
</li>
```

### D. FAQ「GitHub の検索と何が違いますか？」（回答を置き換え）

```html
<details open>
  <summary>GitHub の検索と何が違いますか？</summary>
  <div class="answer">
    キーワード検索の並び順そのものは GitHub の検索結果です。足しているのは
    <code>stars:</code> のような条件では書けない「使われ方に対して star が少ない」
    という観点で、検索結果カードの Gem バッジ、キーワードなしで開く「今日の Gem」、
    検索語から絞り込む「Gem 候補の一覧」の 3 か所に出します。並び順を変えるのは
    「今日の Gem」と「Gem 候補の一覧」だけで、キーワード検索結果の並び順は変えません。
  </div>
</details>
```

### E. FAQ 新規追加（上記 D の直後に挿入）

```html
<details>
  <summary>検索結果に付いている Gem バッジは何ですか？</summary>
  <div class="answer">
    被依存数のわりに star が少ないリポジトリの目印です。<a href="#how">Gem Index</a>
    という指標が小さいカードに付き、<strong>検索結果の並び順は変えません</strong>。
    限られたデータにもとづく参考値なので、付いていないことが低評価という意味には
    なりません。
  </div>
</details>
```

---

## 未決事項（他ラウンドで扱ってほしい点）

- bento の新タイルのアイコンパス・grid の `span` 再配分は実装判断。IA としては「通常サイズ 1 枚を今日の Gem タイルの直後に挿入」までを指定する。
- SEO/OGP（`meta description` / `og:description`）は「毎日 5 件」を主語にしたままで良いか（badge/list を焼き込むかどうか）は本ラウンドでは扱っていない。争点 E の観点では、OGP は最初に見える 1 文なので、ここに badge/list を足すと同じ過密リスクを抱える。現時点では **触らない** ことを推奨する。

### `visual_assets` — 主張
<sub>2026-08-23T14:03:41+09:00</sub>

# 争点 C: 画像戦略（visual_assets round 1）

## 0. 前提（スクリーンショット取得の不具合）

`lp-desktop.png` / `lp-mobile.png` は両方とも実際の LP ではなく、`agent-proxy relay` のエラーテキストが描画された画面だった（撮影スクリプトが素の HTTP でナビゲートしようとしてプロキシに弾かれた可能性が高い）。`app-search.png` / `app-digest.png` / `app-gems.png` / `app-mobile-*.png` は実アプリの画面だが、いずれも GitHub / 候補プールへのデータ取得が失敗したエラー状態だった（このサンドボックスの外部到達性の制約によるもので、LP の内容評価には使えない）。

→ (1) の評価は `site/index.html` のソース（DOM 構造・画像タグの有無）を直接読んで代替した。実物の見た目の最終確認は、撮影環境が復旧してから別途行うことを推奨する。

## 1. 現行 LP の視覚評価（ソース読解ベース）

セクション構成と画像の有無:

| セクション | 画像 | 中身 |
|---|---|---|
| `hero` | shot-mobile.webp（実画面） | 見出し・リード文・CTA・電話フレーム内スクリーンショット |
| `desktop` | shot-search.webp（実画面） | ブラウザフレーム内スクリーンショット |
| `why`（課題） | **なし** | 比較カード 2 枚（テキストのみ）+ stat 数値 4 個 + 出典注 |
| `how`（仕組み） | **なし** | `<ol>` 3 ステップ（テキストのみ）+ 数式ボックス（テキストのみ） |
| `features`（できること） | shot-digest.webp（実画面）+ 6 個の line SVG アイコン | bento グリッド |
| `trust`（つくり） | **なし** | stat ブロック 4 個 + タグリスト + 制約リスト（すべてテキスト） |
| `faq` | **なし** | アコーディオン（テキストのみ） |
| `final-cta` | gem.webp（装飾イラスト） | 見出し + CTA |

**単調さの所在**: `why` → `how` → `trust` → `faq` の **4 セクション連続でテキストのみ**（`features` の SVG アイコン以外、視覚的な間（ま）が無い）。`why`/`how`/`trust` は数値・数式・内部指標（Gem Index 式、テスト件数、ADR 本数）が詰まった **高密度テキスト**で、間に絵的な休符が無いまま続くとスクロールが単調になりやすい。実画像は 3 枚のみ（hero / desktop / features）、装飾イラストは末尾の 1 枚のみ。

## 2. インフォグラフィック 14 点の使う・使わない判定

14 点すべて **使わない**。共通理由:

- **② WCAG 1.4.5 / ADR 0015 に抵触**: 全点、見出し帯・箇条書きラベル・数値が画像に焼き込まれたグラレコ風合成図（実測: `10-gem-score.webp` `14-architecture-flow.webp` `06-roadmap.webp` `11-testing-strategy.webp` `08-doc-relations.webp` `04-prd.webp` を目視確認、他 8 点も同一生成パイプライン・同一書式であることを README の仕様表で確認）。ADR 0015 §2.2 は「画像内に文字を焼き込まない」を装飾イラストの絶対条件としており、これらは正反対（文字が主役の図）。alt テキストで救う案も、1 枚あたり 15〜25 個の独立した事実（`M-1` `NFR-23` `AC-1〜12` 等）を含み、alt に全文を移すと冗長な代替テキストになり実用的な救済にならない。
- **① 対象読者に無意味**: `M-1`〜`M-6`・`NFR-23`〜`26`・`AC-1〜12`・`R-5`〜`R-8`・`SP-14〜16` 等、社内ドキュメント上の管理コードがそのまま図中ラベルになっている（04/06/10/11 で確認）。gem-hunter を初めて見る個人開発者には文脈が無く、読み解けない。
- **③ 縮小で可読性が崩れる**: 生成サイズ 1536×864 を LP 本文カラム（〜1100px）へ縮小すると、原寸で既に小さい注釈文字（4〜6 行のバッジ内テキスト等）が実効 10px 前後まで縮む。08-doc-relations や 04-prd のような箇条書き密度の高い図は特に厳しい。

| file | use | placement | alt | reason |
|---|---|---|---|---|
| 01-initial-concept.webp | no | — | — | 文字焼き込み+社内文脈（②③） |
| 02-lean-canvas.webp | no | — | — | 同上 |
| 03-inception-deck.webp | no | — | — | 同上 |
| 04-prd.webp | no | — | — | `FR-1〜7`/`AC-1〜12`等が主役。①②③すべて抵触（目視確認） |
| 05-user-story-map.webp | no | — | — | `US-n` 格子。①②③ |
| 06-roadmap.webp | no | — | — | `M-1〜M-6`/`SP-14〜16`等の運用コード。①②③抵触（目視確認） |
| 07-design.webp | no | — | — | 文字焼き込み+社内文脈（②③） |
| 08-doc-relations.webp | no | — | — | `ADR 14件`/`ルール57件`等の内部数値。①②③抵触（目視確認） |
| 09-adr-map.webp | no | — | — | 文字焼き込み+社内文脈（②③） |
| 10-gem-score.webp | no | — | — | Gem Index の計算式自体はLP「how」の説明と重複するが、`Phase1`/`Phase2`/`0014`等の実装管理コードが混入。①②③抵触（目視確認） |
| 11-testing-strategy.webp | no | — | — | `NFR-23〜26`/道具名の羅列。開発者向けドキュメント。①②③抵触（目視確認） |
| 12-cloudflare.webp | no | — | — | 文字焼き込み+インフラ内部構成（②③） |
| 13-ops-rules.webp | no | — | — | `CP-1〜6`等の運用ルールコード。①②③ |
| 14-architecture-flow.webp | no | — | — | `L1`/`L2`/`RATE_LIMITER`等の実装内部詳細。①②③抵触（目視確認） |

**補足**: `docs/infographics/README.md` からリンクする形（GitHub 上のドキュメント相互参照）であれば現状のままで問題ない。「LP に埋め込む」ことだけを不可としている。

## 3. 撮り直すスクリーンショット

| name | URL | viewport | clip | reason |
|---|---|---|---|---|
| shot-mobile（撮り直し） | `/ja?q={term}` | 390×780 / dsf2 → 出力幅640 | フルページ（既存と同じ） | 新機能（avatar・Gem バッジ）を主役ショットに反映する。現行 alt は「リポジトリ名・説明・主要言語・star数・最終更新日・トピック」までしか書いておらず avatar/バッジ非搭載時代の文言のまま。撮り直し後は alt 文言も avatar・バッジの有無に合わせて書き直す必要がある |
| shot-search（撮り直し） | `/ja?q={term}` | 1280×820 / dsf2 → 出力幅1600 | フルページ（既存と同じ、`clipFrom` なし） | 同上。PC 版一覧に avatar・Gem バッジが乗った状態を見せる。既存はバッジ導入前のスクリーンショットの可能性が高い |
| shot-gems（新規） | `/ja/gems?q={term}` | 1280×820 / dsf2 → 出力幅1600（`shot-search` と同じ縮小率で書式を揃える） | フルページ、または `gem-list.tsx` の見出し〜3件目あたりまでの `clipFrom`（`shot-digest` と同じ手法で `data-repository-full-name` を目印にトリミング可能） | 「今日の Gem」（日替わり5件）とは別の **常設の Gem 一覧**（`/gems?q=`）は LP 未掲載の新機能。features の bento に 1 タイル追加する形で使う想定 |

**`{term}` の選定について**: 既存の chips 候補（react / postgres / cli / zod / rollup plugin）のうち、実際に候補プール（Gem 候補）に載っていてバッジが立つ語を実機で確認して選ぶ。react で不発なら他の chip 語、それでも無ければ候補プール上位の語を新たに 1 つ選定する（この判定はデータ依存のため、撮影実行時に実機確認が必要——本ラウンドでは断定しない）。

**既存 shot-digest は撮り直し不要**: `daily-digest.tsx` に avatar 表示は無く（確認済み）、新機能 3 点（バッジ・Gem 一覧・avatar）のいずれの影響も受けない。

## 4. gpt-image-2 での新規生成

### 結論: 1 点だけ提案（優先度: 任意・オプション）。他は不要。

**理由**: ADR 0015 は装飾イラストに「情報を運ばない・文字を焼き込まない」を課しており、`why`/`how`/`trust` の中身（Gem Index の計算式、テスト件数、被依存数の実例）を **説明する図** としての新規生成は事実上不可能（文字を抜けば説明にならず、文字を入れれば ADR 違反）。したがって「情報密度を絵で補う」方向の新規生成は却下する。

一方で、`why` → `how` → `trust` → `faq` の4連続テキストセクションに、**既存の hero-idle / loading / empty-result / not-found / gem.webp と同じ「線画+グレーの小石+青い原石」ファミリー**を素直に1点足すことは、情報量ゼロ・文字なしのまま視覚的な休符を作れる。既存ファミリーの拡張なので新しい意匠言語を持ち込まない。

| name | purpose | prompt_direction | reason |
|---|---|---|---|
| why-divider（仮称） | `why` セクション内、比較カード2枚をつなぐ `compare-arrow`（`→`）周辺に置く小さな装飾アクセント。star（中空の星アウトライン）→ gem（塗りの青い原石）という視覚メタファーを、文字なしで補強する | 既存 `tools/ui-assets/prompts/hero-idle.txt` / `gem.webp` と同じ描線・配色（グレー〜クリームの小石、単色の濃灰アウトライン、アクセントは青の原石1個のみ）を踏襲。モチーフは「輪郭だけの星 1 個 → 矢印 → 塗りの原石 1 個」。文字・数字・記号は一切含めない。1024×1024・透過背景 | 4連続テキストセクションの唯一の視覚的立ち止まりどころを作れる。ただし launch を阻む必須項目ではなく、優先度は低〜中（`info_arch` のレイアウト・余白調整だけで十分という判断も妥当） |

**それ以外を提案しない理由**: `how` の数式・`trust` の実測値・`faq` の Q&A は、いずれも数値・固有名詞そのものが価値なので、文字なし画像に置き換える意味がない。無理に絵を足すと「意味なく飾っただけ」になり ADR 0015 の趣旨（情報を運ばない装飾は最小限）にも反する。

## ラウンド 2

### `info_arch` — 反論
<sub>2026-08-23T14:09:18+09:00</sub>

# info_arch — round 2（rebuttal / concession）

## 1. visual_assets への応答（争点 C・単調さ指摘）— 主に **譲歩 + 統合**

**譲歩する点**: round 1 の「できること・bento に新タイル 1 つ」案は、本文（見出し + 2 段落）だけを確定して **画像を指定していなかった**。これは私の設計の抜けで、`visual_assets` が提案した `shot-gems`（新規撮影・`/ja/gems?q={term}`）を素直に取り込む。

修正版のタイル B（round 1 の HTML 構造は維持し、`tile-figure` を追加）:

```html
<div class="tile">
  <h3>…（round 1 と同じ見出し・アイコン）…</h3>
  <p>…（round 1 と同じ 1 段落目）…</p>
  <p class="tile-datum">…（round 1 と同じ tile-datum）…</p>
  <figure class="tile-figure">
    <img
      src="./assets/img/shot-gems.webp"
      width="1600"
      height="{visual_assets の撮影結果に合わせる}"
      loading="lazy"
      decoding="async"
      alt="gem-hunter の Gem 候補一覧画面。検索語「{term}」を引き継いだ Gem 候補が Gem Index 順に並び、各カードにリポジトリ名・説明・オーナーの avatar・利用パッケージ数・star 数が表示されている。"
    />
  </figure>
</div>
```

alt 文は `shot-digest.webp` の既存 alt（内容を具体的に記述するスタイル）に合わせた。`{term}` は `visual_assets` が実機確認で選ぶ語に置き換える。

**反論する点（据え置き）**: 「why → how → trust → faq の 4 連続テキストセクションの単調さ」自体は事実として認めるが、**その解決を bento タイルの追加や新セクション新設に広げる必要はない**。理由は 2 つ:
- `visual_assets` 自身の round 1 提案（`why-divider`・情報量ゼロの装飾アクセント 1 点、優先度「任意・低〜中」）は、私の「why セクションは残す（本文変更なし）」という判断と**矛盾しない**。装飾アクセントは本文の書き換えを要求しないので、IA として反対する理由がない。**採用に賛成する**。
- 一方で `how` / `trust` / `faq` に同様の装飾を追加でねじ込む必要はない。この 3 セクションは数式・実測値・Q&A という「文字自体が価値」の内容で、`visual_assets` も round 1 で同じ結論（無理に絵を足すと ADR 0015 の趣旨に反する）を出している。単調さの緩和は「why の装飾アクセント 1 点」+「bento への shot-gems 追加」で十分と判断する。これ以上の図版追加は争点 E（誇張の抑制）の観点からもやりすぎ — 本来は控えめな注釈機能（バッジ）を、絵で埋めるほど重い機能に見せてしまうリスクがある。

## 2. web_quality への応答（争点 D・重さの上限）

**反論ではなく上限の明示**（要求への直接回答）: 私が bento に足す新規ファイルは `shot-gems.webp` 1 点のみ（実画面スクリーンショット・既存の `shot-search.webp`（60KB）/`shot-digest.webp`（32KB）と同じ撮影パイプラインなので、想定サイズは概ね 30〜60KB 帯）。`visual_assets` が提案する `shot-mobile` / `shot-search` の撮り直しは **既存ファイルの差し替え**であり総重量には加算されない。`why-divider` は `gem.webp`（28KB）と同系統の透過装飾なので同程度と見込む。

→ **info_arch としての上限提案**: 「新規追加ファイルは `shot-gems.webp` + `why-divider.webp`（採用する場合）の **最大 2 点まで**。ラスター化された文字入りインフォグラフィック（14 点）は 1 枚も使わない」を IA 側の合意ラインとして明記する。`visual_assets` の round 1 判定（14 点全て不使用）と一致するので、この上限に異論はないはず。web_quality の「1 枚で 337KB 相当が乗る」という警告は、インフォグラフィックを使わない前提のもとでは発生しない。

## 3. lead への応答（争点 B・ヒーローの整合性）— **部分的に譲歩**

**譲歩する点**: `visual_assets` が round 1 で指摘した通り、`shot-mobile.webp` を新機能（Gem バッジ・avatar）入りの画面で撮り直すなら、**ヒーロー内の付随テキスト（`shot-caption` と `alt`）は画像の中身と食い違わないよう更新が必須**。round 1 ではこの 2 つを見落としていた。

修正案（h1・hero-lead 本文には触れない。`shot-caption` にのみ 1 文追加）:

```html
<p class="shot-caption">
  スマートフォンで「react」を検索した実際の画面です（検索結果は GitHub API から取得しています）。
  一部のカードに付いている Gem バッジについては<a href="#how">「仕組み」</a>で説明しています。
</p>
```

`shot-mobile.webp` の `alt`（詳細記述）も、バッジ・avatar が画面に写るなら要素を追記する必要がある（文言そのものは撮影結果を見てから `visual_assets` が確定するのが適切。IA としては「画像に写っている新要素は alt に反映する」という要件だけを明示する）。

**反論する点（据え置き）**: h1・hero-lead 本文（「毎日 5 件提示する検索ツール」の訴求）は **変更しない**。理由を明確化する:
- バッジは「検索結果の一部カードに付く注釈」であり、gem-hunter という製品を要約する一文には格上げしない、というのが `D-36`（`sort=gem-index` を主軸に戻さない）の精神。画像に写っていること＝見出しで謳うべきこと、ではない。スクリーンショットは「実際の画面そのまま」を見せる場所であり、そこに写っている個々の要素（バッジ含む）を h1/lead が逐一言語化する必要はない（現に現行の hero-lead も「並び替え」「表示件数切り替え」など画面に写っている他の要素には触れていない）。
- 「画像とテキストの食い違い」は `shot-caption` 側の 1 文追加で解消できる粒度の問題であり、h1/lead という製品の中核メッセージまで書き換える理由にはならない。過剰に反応すると、hero-lead が機能列挙に近づき、争点 E が警戒する「実装済み機能を並べ立てて重要度を実態以上に見せる」方向へ寄る。

## まとめ

| 対象 | 対応 |
|---|---|
| visual_assets（単調さ・shot-gems） | 譲歩: bento タイル B に shot-gems 画像・alt を追加。同意: why-divider 採用に賛成 |
| visual_assets（インフォグラフィック不使用） | 同意（争いなし） |
| web_quality（重量上限） | 新規ファイルは最大 2 点（shot-gems + why-divider）に制限する案を提示。ラスターインフォグラフィックは使わない前提で危惧は解消 |
| lead（ヒーロー整合性） | 部分譲歩: shot-caption に 1 文追加、alt 更新を明示。h1/hero-lead 本文は変更しないという round 1 の結論は維持 |

### `en_parity` — 反論
<sub>2026-08-23T14:09:32+09:00</sub>

# en_parity Round 2: 検証結果と自己修正

## 1. Geist フォント GitHub 403 — **誤指摘・取り下げ**

**Round 1 での指摘**:
- ⚠️ `https://github.com/vercel/geist-font` が 403 Forbidden

**検証結果**:
- site/index.html 行 39: `<link rel="preload" href="./assets/fonts/geist-latin.woff2" ...>`
- LP はフォント実体を **site/assets/fonts/ 配下に自前配信**（ローカルファイル）
- footer 行 689 の GitHub リンクは**参照・ライセンス記載用のみ**（配信に含まれない）
- site/README.md 設計上の約束「外部 CDN 非依存」を遵守している

**判定**: round 1 の 403 警告は **実害なし**。GitHub リンク自体が 403 でも、LP の表示・フォント配信に影響しない。誤指摘として取り下げる。

---

## 2. og:description の日付ズレ — **既知の正常動作・concession**

**Round 1 での指摘**:
- ⚠️ og:description の具体例（star 111 / 26,633）が daily-digest.json に存在しない
- og:description のタイムスタンプ（2026-08-21）と current digest date（2026-08-22）でズレ

**fact_sync の指摘（Round 1）**:
- `rollup-plugin-peer-deps-external` は public/data/gem-index/npmjs-org.json に確実に存在（111 stars / 26,633 dependents）
- 現行 daily-digest.json の candidates（2026-08-22 生成）にこの組み合わせが入っていないのは「毎日入れ替わるため」の正常動作
- HTML での注記「ある日の一例」が明記されている（2026-08-21 時点との但し書き）

**判定**: og:description は **時間に依存しない実例を使う正しい設計**。「現在の digest と一致しないから誤り」は false alarm。fact_sync との整合は取れている → **concession（認め）**.

---

## 3. info_arch の新提案文言の整合性確認

新しく提案された文言に対して、技術的な機械検査を実施。

### A. Formula ブロック（見出し変更のみ）
- 変更: 「今日の Gem の並び順」→ 「**Gem Index の並び順**」
- 機械検査: 本文に 3 回目の「Gem Index」使用箇所（「Gem 候補の一覧」）を追加記述
- **結果**: ✓ 整合。HTML `#how` アンカー存在・新規アンカー不要

### B. できること・新タイル（bento への挿入）
```html
<div class="tile">
  <h3>検索結果でも Gem に気づける</h3>
  ...
  <span class="tile-datum-note">（対象は 12 のパッケージレジストリ・約 6.2 万リポジトリ）</span>
```
- **新規外部リンク**: なし（既存のローカルリンク・href="#how" のみ）
- **新規 id/anchor**: なし
- **画像パス**: 新アイコン SVG（既存タイルと同じ `viewBox` スタイル）
- **機械検査**: ✓ アンカー整合・リンク有効

### C. 先に言っておく制約（3 項目目置き換え）
- テキスト: 「今日の Gem」→ 「今日の Gem」「Gem 候補の一覧」「検索結果カード」と 3 箇所明記
- **HTML 参照なし**（純テキスト）
- **機械検査**: ✓ 問題なし

### D. FAQ「GitHub の検索と何が違いますか？」（回答変更）
- 既存 `<details open>` の `<div class="answer">` 内容を置き換え
- **新規リンク**: `<a href="#how">Gem Index</a>`（既存アンカー参照）
- **機械検査**: `#how` は round 1 で確認済み ✓

### E. FAQ 新規質問（追加）
```html
<details>
  <summary>検索結果に付いている Gem バッジは何ですか？</summary>
  <div class="answer">
    ...
    <a href="#how">Gem Index</a>
    ...
  </div>
</details>
```
- **新規 id**: なし（既存 FAQ 構造の `<details>` タグのみ）
- **外部リンク**: なし（内部参照 `#how` のみ）
- **機械検査**: ✓ tools/check_site.py の項目 4（内部アンカー確認）で既存 id `#how` に到達可能

---

## 4. メタデータ文字数（情報追加時の確認）

**meta description（現行）**: 105 字 → 目安 90-120 字内 ✓
**og:description（現行）**: 「star 111 なのに 26,633...毎日 5 件」
- info_arch は SEO/OGP を「本ラウンドでは触らない」と明示（未決事項欄）
- **判定**: meta / og:description は現行のまま修正不要

---

## まとめ

| 項目 | Round 1 判定 | Round 2 検証 | 変更 |
|---|---|---|---|
| Geist 403 | ⚠️ 警告 | 実害なし（自前配信） | 🚫 取り下げ |
| og:description ズレ | ⚠️ 警告 | 既知の正常動作（fact_sync 確認） | ✓ Concession |
| info_arch 提案の新リンク | （Round 2 検査対象） | 既存 anchor / アンカー 不新規 | ✓ 整合 |
| meta description 文字数 | （Round 2 検査対象） | 105 字・目安範囲内 | ✓ OK |

**総評**: Round 1 の 2 つの警告をいずれも撤回。info_arch / web_quality の提案は HTML ・アンカー・リンク整合性に問題なし。実装ゲート (tools/check_site.py) での落ち込みは予想されない。

### `fact_sync` — 反論
<sub>2026-08-23T14:09:41+09:00</sub>

# fact_sync round 2 — rebuttal / concession

## 1. info_arch の確定ドラフトを実測と突き合わせた結果

### 1-a. 濃度: **「約 6.2 万リポジトリ」は正しい。ただし議題ブリーフの「109,469」は古い見積りで使うと誤りになる**
- info_arch の B（bento 新タイル）注記「対象は 12 のパッケージレジストリ・約 6.2 万リポジトリ」は **`public/data/gem-index/index.json` の `totalCount: 62483` と完全一致**（12 シャードの `count` を合算しても同じ 62,483）。**concede — この数値のまま採用してよい**。
- 一方、この議題のブリーフ本文と `open-questions.md` `D-36` にある「ユニーク **109,469** リポジトリ」は `D-36` 時点（2026-08-22 の実現可能性検証・`gem-index-feasibility-20260822` 議論）の **見積り値**（15,000 件 ×12 レジストリの粗収集ベース）で、その後 `D-37`（レジストリ別成層化・汚染フィルタ・flagship dedupe）を経て実装（`SP-17` #416）が出した **本番の実測値は 62,483**。⚠️ **後続ラウンドで誰かが「109,469」を LP 本文やタイル注記に使おうとしたら差し戻すこと**。実データと 43% も乖離する。

### 1-b. Gem バッジの判定根拠 — **formula ブロック案 A に事実誤認あり（rebuttal）**
info_arch の案 A（formula ブロック 2 段落目）:
> 「検索結果では、一部のカードに **Gem バッジを付けるかどうかの判定に使います**」（＝ Gem Index の値でバッジ可否を決める、という書きぶり）

実装を確認すると異なる。`src/domain/ports/gem-index-port.ts`（`lookup()` のコメント）と `src/ui/gem-badge.tsx` のコメントより:
- バッジは `GemIndexPort#lookup()` = **候補プールへの所属照会**（プールに入っているか否かの二値判定）で決まる。Gem Index の **数値の大小で閾値判定している訳ではない**（候補プール自体が「Gem Index が小さい／過小評価されている」候補として `D-37` の成層化・汚染フィルタで事前に絞り込まれているため、結果的に Gem Index が小さいものにバッジが付くが、バッジ判定ロジック自体が読んでいるのは「プールに載っているか」であって「この値」ではない）。
- 一方、Gem 一覧（`/gems`）は `GemIndexPort#search()` が実際に Gem Index 順（`gemIndex` 昇順）で並べる — こちらは info_arch の記述どおり「この値」を使っている。

**直す文言案**（案 A 2 段落目を差し替え）:
> 「検索結果では、この候補プールに載っているカードに Gem バッジを付けます（並び順の判定には使いません）。検索語から開ける『Gem 候補を一覧で見る』画面では、集まった候補をこの値の順に並べます。」

新タイル（案 B）の本文「Gem バッジが付きます」自体は「値を使う／使わない」に触れていないので無修正で問題ない。**info_arch の案 B・C・D・E は今回検証した範囲で事実と矛盾しない（concede）**。

### 1-c. info_arch の対応漏れ（round1 指摘の再確認・rebuttal ではなく補足）
info_arch のセクション単位判断表は FAQ「GitHub の検索と何が違いますか？」の書き換えのみを挙げており、**FAQ「対応しているエコシステムは何ですか？」（『今日の Gem の被依存数は npm（npmjs.org）のパッケージだけ』）の書き換えが判断表に入っていない**。round1 で実測したとおり `gem-index/index.json` の shards は 12 レジストリで npm 限定はもう成立しない。B（情報設計）の担当外だとしても、A（事実の追随）としてこの FAQ は必ず直す対象に残す。直す文言案は round1 の投稿のとおり。

## 2. 「682 ケース」の分母定義について（coordinator の確認事項 2）

`ユニット・結合` と `E2E` という **2 分類の定義自体は現在も成立する**（vitest = `src/**/*.test.ts(x)` のユニット・結合、playwright = `e2e/**/*.spec.ts` の E2E で、round1 時点でファイル種別は変わっていない）。したがって **単純な数値差し替えでよく、内訳の呼び方（ラベル）を変える必要はない**。

- ユニット・結合: 593 → **954**（vitest 81 files / 954 tests passed・実行結果より）
- E2E: 89 → **107**（`npx playwright test --list` の `Total: 107 tests in 23 files`・実行結果より）
- 合計: 682 → **1,061**

確定文言案（`つくり` セクション）:
```html
<div class="fact">
  <b>1,061 ケース</b>
  <span>
    ユニット・結合 954 / E2E 107。<a
      href="https://github.com/kai-kou/gem-hunter/blob/main/docs/04_development/testing-strategy.md"
      >テスト戦略</a
    >
  </span>
</div>
```

## 3. `rollup-plugin-peer-deps-external`（26,633 / star 111）は残してよいか（coordinator の確認事項 3）

**判定: 残してよい（現状維持を推奨）。en_parity の「不一致あり」という評価は精査が必要（rebuttal）。**

en_parity は `daily-digest.json` の `candidates`（今日時点の上位 300 件の候補プール）に `star:111 / dependents:26,633` の組がないことをもって「不一致」と判定しているが、これは **検証対象を取り違えている**。round1 で実測したとおり、この数値は **`public/data/gem-index/npmjs-org.json`（全候補データそのもの）に実在する**:

```
['pmowrer/rollup-plugin-peer-deps-external', 'rollup-plugin-peer-deps-external', 26633, 111, -64.23]
```

LP 本文は最初からこの数字を「今日の 1 位」とは書いていない。`tile-datum-note` に **「（2026-08-21 時点の一例。顔ぶれは毎日入れ替わります）」** と明記した **過去 1 日のスナップショット例**として提示している。「今日の Gem」は日替わりの仕様（`GEM_INDEX_SHORTLIST_SIZE=60` から seed 決定論的に 5 件を毎日選ぶ）なので、ある特定の日に 1 位だった候補が翌日以降のトップ 300（≒ shortlist 60 の母集団）から外れるのは **仕様どおりの正常動作**であり、データの矛盾ではない。

- **本文（tile-datum・og:description の実測数値そのもの）**: 変更不要。データは実在し、正確。
- **本文側の但し書き**: 既存の `tile-datum-note`（「2026-08-21 時点の一例」）で十分。これがある限り「今日のトップ」という誤読は生まれない。
- **og:description（行 22-23）**: 同じ 26,633 / 111 の数字を使っているが、こちらには「一例・入れ替わる」という但し書きが**物理的に入れられない**（OGP は 1〜2 文が限度で、meta description は既に「毎日 5 件」という頻度の説明を含んでいる）。これは今回の SP-18/19 追随とは無関係な **既存の設計判断**（構造的制約）であり、争点 A（事実追随）の範囲では「誤り」ではなく「そもそも脚注を持てない媒体の制約」として **現状維持・据え置き**でよいと判定する。無理に変えるなら「毎日入れ替わる例の一つ」という言い回しを og:description 内に短く足す程度に留め、具体的な数値自体（26,633 / 111）は実データと一致しているため触らない。

## まとめ（確定させたい3点）

| 論点 | 結論 |
|---|---|
| info_arch 案の数値・機能記述 | B/C/D/E は事実と整合（concede）。A の Gem バッジ判定根拠は「値」ではなく「プール所属」が正しい（rebuttal・文言修正要）。FAQ 対応漏れ 1 件あり（npm 限定表記） |
| 682→? の分母定義 | 「ユニット・結合／E2E」の分類は不変。954 / 107 / 合計 1,061 に数値差し替えのみでよい |
| rollup-plugin-peer-deps-external の数値 | 実データと一致・**そのまま残す**。既存の「一例」注記で誤読リスクは解消済み。og:description は構造的制約により現状維持でよい |

### `web_quality` — 反論
<sub>2026-08-23T14:10:40+09:00</sub>

# web_quality — Round 2: rebuttal / concession

対象ファイルは再読しない。round 1 の自分の分析とホワイトボードの他レンズ投稿のみで反論する。

## 1. 撮影経路（`page.route` + `curl fulfill` で本番を撮る）を恒久化すべきか

**恒久化には反対。既定は変えず、明示 opt-in の環境変数として追加すべき。**

理由:

- **本番の共有 API レート枠を消費する**。`site/README.md`「先に言っておく制約」（現行文）は「共有の API レート枠で動いています。混み合う時間帯は検索が一時的に失敗することがあります」と明記している。撮影スクリプトの既定経路を本番直叩きに変えると、**LP 更新のたびに実ユーザーと同じ枠を消費する**副作用が生まれる。ローカル `next build && next start` は（別トークン運用であれば）この枠を侵さない。この差はスクリプトのコメントに一度も出てこないため、恒久化するなら副作用として明記が必須
- **再現性が壊れる**。既存スクリプトの設計意図は「本番ビルドをローカルで起動して撮る」＝ **決定論的な入力**（コードは固定、GitHub API のレスポンスだけが変動）。本番を直接叩く経路は、①アプリのコード ②GitHub API の実データ の両方が撮影のたびに変わりうる。「今日のコード」と「今日のデータ」が区別できなくなり、`shot-mobile` 撮り直しが実は本番デプロイの遅延を検出しているだけ、という取り違えが起きうる
- **`curl` 経由の `route.fulfill` は今回のサンドボックス固有の回避策**（Chromium の直接/プロキシ経由 HTTPS が `ERR_CONNECTION_RESET` になる、という環境制約への対処）。ローカル開発機・将来の CI 環境では発生しない可能性が高い問題を、全実行環境の既定動作に組み込むのは筋が違う

**具体案**: `LP_SHOT_BASE`（既存）はそのまま維持し、`LP_SHOT_BASE=https://gem-hunter.kinamocchi-tech.workers.dev` を明示すれば本番を対象にできる据え置き設計は変えない。その上で `curl` 経由フェッチだけを新しい opt-in フラグ（例 `LP_SHOT_FETCH_VIA_CURL=1`）でオンにし、既定は off（従来どおり `page.goto` 直行）にする。`site/README.md`「スクリーンショットの更新」に「このクラウドサンドボックスで直接 HTTPS が通らない場合の回避策」として追記し、恒久のベストプラクティスとは書かない。

## 2. 新規ショット（Gem 一覧）追加時に確定形で足すべきもの

**`tools/capture_lp_screenshots.mjs`**:
- `SHOTS` 配列に `visual_assets` が提案した `shot-gems` エントリを追加（`name: 'shot-gems'`, `path: '/ja/gems?q={term}'`, `viewport`, 出力 `width`。フルページ撮影ならプロパティ追加不要、`clipFrom` を使うなら `shot-digest` と同じパターンで関数を書く）
- それ以外の変更は不要。撮影後の width/height 突き合わせ（末尾のマッチングロジック）は `written` 配列にプッシュされた `SHOTS` の要素を自動で拾うため、**配列に追加するだけで自動的にこの新画像も検証対象になる**（コード変更なし）

**`tools/check_site.py`**: **コード変更は不要**（round 1 §4 で列挙した 6 項目はすべて `index.html` を汎用走査する実装で、画像ファイル名のホワイトリストを持たない）。必要なのは `index.html` 側の記述:
- `<img src="./assets/img/shot-gems.webp" width="{実寸幅}" height="{実寸高さ}" loading="lazy" decoding="async" alt="{具体的な代替テキスト}">` を正しい属性で書く（`width`/`height` 欠落・縦横比不一致はどちらも `check_page()` が fail させる）
- `shot-gems.webp` を `site/assets/img/` に実際に置く（参照切れチェック対象）
- `--self-test` は `site/assets/img/*` を全走査するので、新ファイルを置いた時点で自動的に画像デコード可否も検証される（追加設定不要）

## 3. インフォグラフィック 1 点だけ載せる場合の技術的な最低条件（`visual_assets` の「14 点とも不使用」を支持した上での先回り）

`visual_assets` の判定（① 社内文脈の管理コードが読者に無意味 ② ADR 0015 の文字焼き込み禁止に抵触 ③ 縮小で可読性崩壊）に同意する。round 1 のサイズ実測（205〜324KB/枚）もこの判定を補強する。それでも 1 点だけ載せる案が通るなら、最低限：

| 項目 | 条件 |
|---|---|
| コピー先 | `docs/infographics/` を直参照しない。`site/assets/img/` へコピーする（round 1 §3。相対パスが GitHub Pages のサブパス配信で `gh-pages` ブランチには `docs/` が存在せず壊れるため） |
| 配置 | ファーストビュー外（`#trust` 以降の下位セクション）。LCP 要素を `shot-mobile.webp`（63KB）から差し替えないため |
| `loading` | `lazy` 必須 |
| `width`/`height` | 実寸（16:9、例 1536×864）をそのまま記載。`check_site.py` の縦横比チェック（許容誤差 0.01）を通す |
| ファイルサイズ | 原寸 205〜324KB は現行画像合計（337KB）と同等の重さが 1 枚で乗るため不可。**再圧縮・リサイズして 1 枚あたり 100KB 未満を目標**にする（`check_site.py` にサイズ上限チェックは無いので人力で守る） |
| alt | `docs/infographics/README.md` の見出し語（例 `alt="Gem Score 算出ロジック"`）を **転用しない**。画像内の主要な事実（何を示す図か・読者が持ち帰る結論）を 1〜2 文で書く。`04-prd.webp` 等の管理コード（`FR-n`/`AC-n`）はそのまま読み上げても意味を持たないため、**コードは alt に含めず結論だけを言い換える** |
| 相対パス | `./assets/img/...`（`site/` 基準） |
| 検証 | 追加後に axe を再実行し `image-alt` ルールが引っかからないことを確認する（round 1 §6 のスクリプトで再現可能） |

## 4. `site/README.md`「設計上の約束」違反チェック — 名指し

`info_arch`（formula ブロック書き換え・bento 新タイル・制約文更新・FAQ 更新）、`visual_assets`（`shot-search`/`shot-mobile` 撮り直し・`shot-gems` 新規・`why-divider` 装飾画像 1 点提案）の round 1 ドラフトを確認した。

**違反なし**。内訳:
- 外部 CDN 依存: `info_arch` のドラフトはテキストと既存と同じインライン SVG のみ、`visual_assets` の新規画像は自前生成（gpt-image-2 → `to_web_assets.mjs`）で `site/assets/img/` へ配置する前提。CDN 参照ゼロ
- ページ内 JavaScript: 両者ともマークアップ・画像の追加のみ。`<details>` や `<a href>` 以外のインタラクション（モーダル等）は提案されていない
- `opacity` アニメ: 提案なし。`visual_assets` の新規装飾画像も静的な `<img>` で、`.reveal`/`hero-in` の `transform` 方式を流用する前提と読める（明示はされていないが、opacity への言及は一切ない）
- prettier 整形: 言及なし（懸念事項として round 1 で先出ししただけ）
- 本番で無効な機能の記載: `info_arch`・`fact_sync` の Gem バッジ／Gem 一覧はいずれも `fact_sync` が実装済みと実測確認済み（PR #435/#440 ほか）。未実装の言及なし

**補足で 1 点フラグ**: `info_arch` の bento 新タイルは新しい inline SVG アイコンを使う（`<!-- アイコンはタグ/バッジ系を実装側で選定 -->` と未確定のまま）。既存の icon 用 SVG は **`width`/`height` 属性を持たず** `.icon { width:20px; height:20px }` の CSS クラスでサイズを決めている（round 1 では気づいていなかった点として補足: `check_site.py` の width/height 検査は `<img>` タグのみが対象で `<svg>` は対象外なので、実装側がこの新アイコンにも `width`/`height` 属性を **付けない**限り機械検査には抵触しない。既存パターンを踏襲するよう実装側に申し送りたい）。

## 補足: fact_sync の「682→1061」修正への同意

round 1 では現行数値（682 ケース）をそのまま前提に画像重量の話をしたが、この数値変更はテキストのみで画像・CLS・LCP に影響しない。`fact_sync` の実測（954+107=1061）を追認する。ページ重量の実測結論（round 1 §1）は変更なし。

### `visual_assets` — 反論
<sub>2026-08-23T14:10:44+09:00</sub>

# 争点 C: 画像戦略（visual_assets round 2 — rebuttal / concession）

## 0. 撮り直された実画像を確認した（round 1 の前提を破棄）

`lp-desktop.png` / `lp-mobile.png`（正常な LP）、`app-search.png` / `app-gems.png` / `app-digest.png` / `app-mobile-search.png` / `app-mobile-gems.png` / `app-detail.png`（本番実画面）をすべて読んだ。round 1 は撮影不能だったため `site/index.html` のソース読解で代替したが、実画像で裏取りできたので以下に更新する。

## 1. 「4 セクション連続でテキストのみ」— **一部撤回・精緻化**

**撤回する点**: round 1 で「`why`→`how`→`trust`→`faq` の4セクション連続でテキストのみ」と書いたのは不正確だった。実際の DOM 順序は `why`(画像なし)→`how`(画像なし)→**`features`(shot-digest.webp あり)**→`trust`(画像なし)→`faq`(画像なし) であり、`features` が画像を持つため **連続 4 ではなく、2 セクションずつの断絶した 2 つの空白区間**（`[why, how]` と `[trust, faq]`）が正しい。実画像（`lp-desktop.png`）でもこの区切りを確認した。

**維持する点**: 画像ゼロのセクションが 4 つあるという実数そのものは正しい。ただし「どこに何を入れるのが最も効くか」は精緻化する必要がある。

**確定判断**: 2 つの空白区間のうち、**優先すべきは `[why, how]`**。理由:
- `why` は比較カード2枚+数値4個の**密な散文**、`how` は`<ol>`3ステップ+**数式ボックス**の密な散文で、両方ともグリッド的なリズム（カード区切り・アイコン等）を持たない純粋な段落の連続。実画像で見ても、この区間はスクロールしても視覚的な手がかりが変わらない。
- 一方 `trust` は `facts` グリッド（4 個の stat ブロックが横並び）+ タグリスト chip 群で、`faq` は `<details>` アコーディオン（開閉インタラクションがあり、閉じた状態では短い1行の羅列）。**どちらも「散文の連続」ではなくカード/チップ/アコーディオンという構造的リズムを既に持っている**ため、round 1 が想定したほどの単調さのリスクは低い。`info_arch` の「`trust`/`faq` は残す」判断（round 1 表）に同意する。

→ 新規視覚要素を入れるなら **`why` セクション（`compare-arrow` 周辺）1 箇所に絞るのが最も効果的**。`trust`/`faq` への追加は不要と判断を修正する。

## 2. `web_quality` のサイズ実測（205〜324KB/枚・現行合計337KB）を踏まえても「14点全て不使用」は維持する

`web_quality` の実測（インフォグラフィック1枚で現行画像合計とほぼ同等の重さが乗る）は **補強材料として受け取るが、私の結論の根拠ではない**。サイズだけが問題なら「縮小版を作る」「1枚だけ厳選する」で解決できてしまうが、**文字焼き込み（ADR 0015 §2.2・WCAG 1.4.5）と社内管理コード（`M-1`/`NFR-23`/`AC-1〜12`等）による対象読者への無意味さは、どれだけ圧縮しても解消しない**。仮に 1KB まで圧縮できたとしても、`04-prd.webp` や `06-roadmap.webp` を初見の個人開発者に見せる理由にはならない。

`web_quality` §2 が指摘した「1.4.5 の例外規定（図表として本質的に必要な場合は1.1.1相当のテキスト代替があれば許容されうる）」についても確認したが、これは **同等の代替テキストを書けることが前提**であり、14点はいずれも1枚あたり15〜25個の独立した事実を含む複合図なので、同等のalt文を書くこと自体が非現実的（`web_quality` 自身も同節で「現行の`docs/infographics/README.md`のalt（見出しの言い換えのみ）は同等の代替にならない」と認めている）。

**結論: サイズ以外の理由（文字焼き込み・ADR 0015・対象読者への無意味さ）だけで独立して十分な不使用根拠であり、`web_quality` のサイズ実測はこれに追加の実務上の裏付けを与えるが、判断の主軸ではない。round 1 の結論を維持する。**

## 3. 撮影一覧（確定形）

`react` は実際に Gem バッジが付くことを `app-search.png`（`react/react` / `vercel/next.js` / `react/react-native` / `remix-run/react-router` の4枚に `Gem` バッジ確認）で裏取りした。round 1 で保留していた `{term}` 選定は **`react` に確定**（既存 chips・既存 alt 文言との一貫性も保てる）。

| name | URL | viewport（幅×高） | クリップ | 出力幅 | 置き場所 | alt 案 |
|---|---|---|---|---|---|---|
| shot-mobile（撮り直し・確定） | `/ja?q=react` | 390×780 / dsf2 | フルページ（既存と同じ、`clip` なし） | 640 | hero（既存と同じ位置） | 「スマートフォンで表示した gem-hunter の検索結果画面。『react』で検索し、react/react カードに Gem バッジが付いている。各カードにはリポジトリのアバター画像・リポジトリ名・説明・主要言語・star 数・最終更新日・トピックが縦に積み重なっている。」 |
| shot-search（撮り直し・確定） | `/ja?q=react` | 1280×820 / dsf2 | フルページ（既存と同じ、`clip` なし） | 1600 | desktop（既存と同じ位置） | 「PC の画面幅で表示した gem-hunter の検索結果画面。『react』で検索し、各カードにアバター画像とリポジトリ名が並び、react/react・vercel/next.js・react/react-native・remix-run/react-router のカードに Gem バッジが付いている。上部に『この検索語の Gem 候補を一覧で見る』リンクがある。」 |
| shot-gems（新規・確定） | `/ja/gems?q=react` | 1280×760 / dsf2 | フルページなし（`shot-search` と同じ「ビューポートそのまま」方式。見出し『「react」の Gem』+ 総件数 + 上位 3〜4 件が収まる高さ） | 1600（`shot-search` と同一スケール率で書式を揃える） | `features` bento の新タイル内（§4 参照） | 「gem-hunter の Gem 一覧画面（検索語『react』で絞り込み）。669 件中、アバター画像・リポジトリ名・パッケージ名・レジストリ名・star 数・利用パッケージ数・Gem Index の数値順に並んでいる。」 |

**shot-digest は撮り直し不要（round 1 判定を維持）**: `app-digest.png` で実画像を確認したが avatar・バッジとも無く、新機能3点の影響を受けていないことを裏取りできた。

## 4. `info_arch` の「セクションは増やさず bento に新タイル1枚だけ」への rebuttal

**反論ではなく拡張提案**: info_arch の制約（新タイル1枚のみ・セクション非増設）自体には同意する。その上で、ドラフト B（プレーンな `tile`・アイコン+テキストのみ）を **`span-2 tile-wide` + `tile-figure`（`shot-gems.webp`）に差し替える**ことを提案する。

根拠: 同じ bento グリッド内に既に「今日の Gem」タイルが `span-2` + `tile-figure`（`shot-digest.webp`）というパターンで存在する。**新しいCSS/レイアウトパターンを持ち込まず、既存パターンを複製するだけ**で、info_arch の「新タイル1枚のみ」という制約を破らずに実画像を追加できる。`app-gems.png` を見ると、Gem Index の数値順ランキング表示は検索結果一覧とは視覚的に明確に異なり（星の代わりに Gem Index の負数、パッケージレジストリ名の併記)、文章だけの説明より一目で伝わる。

→ **画像を置く余地は info_arch 案のままで足りる**。「1タイル」という制約と「実画像を1枚含める」は両立する（tile数は変えず、tileの中身の密度だけ既存パターンに揃えて上げる）。info_arch のドラフト B 本文（コピー文言）はそのまま活かし、`<figure class="tile-figure"><img ...></figure>` を追記するだけでよい。

## 5. 新規生成（round 1「装飾アクセント1点・任意」）— **維持（配置を精緻化）**

§1 の再検討により、**`why` セクション1箇所への配置に絞って維持する**（`trust`/`faq` への追加提案は撤回）。

| name | purpose | prompt_direction | reason |
|---|---|---|---|
| why-divider（仮称） | `why` セクション内 `compare-arrow`（`→`）周辺の装飾アクセント。中空の星アウトライン→矢印→塗りの青い原石、という視覚メタファーを文字なしで補強する | 既存 `hero-idle.webp`/`gem.webp` と同じ線画（グレー〜クリームの小石、濃灰の輪郭線、単色の青原石1個のみをアクセントに）。文字・数字・記号は一切含めない。1024×1024・透過背景。`tools/ui-assets/prompts/hero-idle.txt` の共通スタイル段落をそのまま流用できる | `[why, how]` が実画像確認後も唯一の「純粋な散文が続く」区間であることが確定した。`web_quality` の実測（エラー種別イラスト4点が6.0〜8.7KBに収まっている）を踏まえると、同程度の小型装飾なら 100KB/ページ予算・30KB/枚予算のいずれにも余裕で収まる |

`trust`/`faq` は §1 の通りグリッド/アコーディオンの構造的リズムを既に持つため、追加の新規生成は不要と判断する（round 1 で言及しなかった判断を今回追加）。

## ラウンド 3

### `lead` — 合意
<sub>2026-08-23T14:12:06+09:00</sub>

# lead — 合意点と対立の決着（争点 A〜E）

## 決着した対立

| 対立 | 決着 | 根拠 |
|---|---|---|
| Gem バッジの判定根拠を「Gem Index の値」と書くか（info_arch 案 A）vs「候補プールへの所属」（fact_sync） | **fact_sync を採用**。`GemIndexPort#lookup()` は二値の所属照会で、値の閾値判定ではない | 実装（`src/domain/ports/gem-index-port.ts` / `src/ui/gem-badge.tsx`）の実測。本番の実文言も「star 数のわりに多くのパッケージから使われている候補に付きます」と値に触れていない |
| 母集団の規模を「109,469」と書くか「約 6.2 万」か | **約 6.2 万（62,483）を採用**。109,469 は `D-36` 時点の粗収集見積りで、`D-37` の成層化・汚染フィルタ・dedupe 後の実測とは 43% 乖離する | `public/data/gem-index/index.json` の `totalCount: 62483`（12 シャード合算も一致） |
| 単調さの解消を LP 全体に広げるか（visual_assets round 1）vs bento 1 枚に閉じるか（info_arch） | **visual_assets が round 1 を自ら精緻化して収束**。実画像で `features` が画像を持つことが判明し、空白区間は `[why, how]` と `[trust, faq]` の 2 つ。`trust` / `faq` はグリッド・アコーディオンの構造的リズムを持つため介入不要。介入は `why` 1 箇所 + bento の `shot-gems` に絞る | `lp-desktop.png` の実画像確認 |
| bento 新タイルをプレーン `tile` にするか `span-2` + `tile-figure` にするか | **`span-2 tile-wide` + `tile-figure`（`shot-gems.webp`）を採用**。既存「今日の Gem」タイルと同じパターンの複製で、新しい CSS を持ち込まずに実画像を入れられる。info_arch の「タイルは 1 枚だけ」制約も破らない | info_arch が round 2 で譲歩・visual_assets が拡張案を提示し両者合意 |
| ヒーロー（h1 / hero-lead）を書き換えるか | **書き換えない**。`shot-caption` に 1 文追加と `alt` の更新だけで画像とテキストの食い違いは解消する。バッジは「検索結果の一部カードに付く注釈」であり、製品の要約文へ格上げすると `D-36`（`sort=gem-index` を主軸に戻さない）の精神に反する | info_arch round 1・2 で一貫、他レンズから有効な反論なし |
| インフォグラフィック 14 点を LP に載せるか | **1 点も載せない**。① 文字焼き込み（`ADR 0015` §2.2・WCAG 1.4.5）② 社内管理コード（`M-n` / `NFR-n` / `AC-n`）が LP 読者に無意味 ③ 1 枚 15〜25 個の独立した事実を持つ複合図で同等の alt を書くこと自体が非現実的。web_quality のサイズ実測（205〜324KB/枚・現行画像合計 337KB）は補強材料 | visual_assets round 1・2 で一貫、web_quality が支持。**ユーザー指示の「既存のインフォグラフィックを活用できるのであれば活用」という条件節（"できるのであれば"）に対する答えは「活用できない」** |
| 撮影経路（`page.route` + `curl fulfill`）を恒久化するか | **恒久化しない。既定 off の opt-in 環境変数として追加する**（`LP_SHOT_FETCH_VIA_CURL=1`）。本番直叩きは共有 API レート枠を実ユーザーと食い合い、コードとデータの両方が動くため再現性も壊れる。`curl fulfill` はこのサンドボックス固有の回避策 | web_quality round 2。lead も同意（今回はこの経路でしか撮れないが、既定にはしない） |
| Geist フォントの GitHub リンク 403 | **誤指摘・取り下げ済み**（LP はフォントを自前配信しており実害なし） | en_parity round 2 の自己修正 |
| `og:description` の「star 111 / 26,633 個」 | **据え置き**。数値は `npmjs-org.json` に実在し正確。本文側には「2026-08-21 時点の一例」注記があり誤読は防げている。OGP は脚注を持てない媒体制約 | fact_sync round 2、en_parity が concession |

## 全レンズが一致した点

- LP の「682 ケース（ユニット・結合 593 / E2E 89）」は陳腐化。分類の定義は不変で **数値差し替えのみ**（954 / 107 / 合計 1,061）
- FAQ「対応しているエコシステムは何ですか？」の「npm（npmjs.org）のパッケージだけ」は誤り。12 レジストリへ更新する
- `SP-18`（Gem バッジ）/ `SP-19`（Gem 一覧）は実装済みなのに LP に未記載
- 「ADR 15 本」「Gem Index の 60 件母集団・毎日 5 件」「Accessibility 100 ゲート」「詳細画面の 4 指標」「ソート・表示件数」「新着バッジ」は現行実装と一致し **修正不要**
- LP の a11y は現状 axe violations = 0（light/dark 1280・light 390・light 320）。追加後に再測して 0 を維持する
- `tools/check_site.py` はコード変更不要（`index.html` を汎用走査する実装）
- 新規 inline SVG アイコンは既存パターンに合わせ `width`/`height` 属性を **持たせない**（CSS `.icon` でサイズを決める）
- 新規追加する画像ファイルは **`shot-gems.webp` + `why-divider.webp` の最大 2 点**（`shot-mobile` / `shot-search` は既存の差し替えなので総重量に加算されない）

## 残る注意点（実装時に守る）

- `109,469` を LP 本文へ書かない（`62,483` = 「約 6.2 万」を使う）
- Gem バッジの説明で「Gem Index の値が小さいカードに付く」と書かない（「候補プールに載っているカードに付く」が正確）
- 撮り直した画像に写る新要素（avatar・Gem バッジ・Gem 導線）は `alt` に反映する
- `site/` は `npm run format` の対象外（prettier で整形しない）

### `lead` — 判定
<sub>2026-08-23T14:13:15+09:00</sub>

{
  "fixes": [
    { "id": "F-1", "severity": "must", "issue": "A", "problem": "FAQ「対応しているエコシステムは何ですか？」が「今日の Gem の被依存数は npm（npmjs.org）のパッケージだけ」と書いているが、SP-17（#416）以降は 12 レジストリ・62,483 リポジトリが対象", "fix": "回答を「キーワード検索は GitHub 全体が対象で、言語もエコシステムも問いません。一方「今日の Gem」と Gem の印が使う被依存数は、npm・PyPI・crates.io・RubyGems・Packagist・Go Modules・Maven・CRAN・Hex・CPAN・NuGet・pub.dev の 12 のパッケージレジストリ（約 6.2 万リポジトリ）を対象にしています。」へ差し替える", "file": "site/index.html" },
    { "id": "F-2", "severity": "must", "issue": "A", "problem": "「682 ケース（ユニット・結合 593 / E2E 89）」が実測と乖離（vitest 954 / playwright 107）", "fix": "`<b>1,061 ケース</b>` / `ユニット・結合 954 / E2E 107。` に差し替える。分類の呼び方は変えない", "file": "site/index.html" },
    { "id": "F-3", "severity": "must", "issue": "B", "problem": "SP-18（検索結果の Gem バッジ）と SP-19（検索語を引き継ぐ Gem 一覧）が「できること」に載っていない", "fix": "bento に新タイル 1 枚を `span-2 tile-wide` + `tile-figure`（`shot-gems.webp`）で追加する。見出し「検索結果でも Gem に気づける」。本文は「キーワード検索の結果のうち、被依存数のわりに star が少ないカードには Gem バッジが付きます。並び順は変わりません。バッジが付かないことは低評価を意味しません。」+ tile-datum「検索結果の上にある「この検索語の Gem 候補を一覧で見る」から、その検索語に合う Gem 候補だけを Gem Index 順に見られます（対象は 12 のパッケージレジストリ・約 6.2 万リポジトリ）」。挿入位置は「今日の Gem」タイルの直後。新規 inline SVG アイコンには width/height 属性を付けない", "file": "site/index.html" },
    { "id": "F-4", "severity": "must", "issue": "A", "problem": "「仕組み」の formula ブロックが Gem Index を「今日の Gem」専用の指標として説明しており、検索結果のバッジと Gem 一覧で使われることに触れていない", "fix": "h3 を「Gem Index の並び順」へ変更し、2 段落目を「この値は 3 つの場所で使っています。「今日の Gem」では、この値が小さい上位 60 件を母集団に、日付から決まる順序で毎日 5 件を選び、その 5 件をこの値の順に並べています。検索結果では、この候補プールに載っているカードに Gem バッジを付けます（検索結果の並び順は変えません）。検索語から開ける「Gem 候補を一覧で見る」画面では、集まった候補をこの値の順に並べます（一覧の中身は全件が Gem 候補なので、キーワード検索と違って順位が意味を持ちます）。」へ差し替える。1・3 段落目は現行のまま。🔴 「Gem Index の値でバッジ可否を判定する」とは書かない（実装は候補プールへの所属照会）", "file": "site/index.html" },
    { "id": "F-5", "severity": "must", "issue": "E", "problem": "「先に言っておく制約」の 3 項目目が Gem 一覧の並び順にしか触れておらず、検索結果カードのバッジ自体に言及していない", "fix": "「Gem Index は「今日の Gem」と「Gem 候補の一覧」（検索結果から開けます）の並び順に使っています。検索結果カードの Gem の印は、この候補プールに載っているかどうかで付きます。キーワード検索の結果自体は GitHub の検索結果をそのまま並べており、印が付いても並び順は変わりません。Gem の印は限られたデータにもとづく参考値なので、優劣の評価ではありません。」へ差し替える", "file": "site/index.html" },
    { "id": "F-6", "severity": "must", "issue": "B", "problem": "FAQ「GitHub の検索と何が違いますか？」の回答が差別化を「今日の Gem」だけに限定している", "fix": "「キーワード検索の並び順そのものは GitHub の検索結果です。足しているのは `stars:` のような条件では書けない「使われ方に対して star が少ない」という観点で、検索結果カードの Gem の印、キーワードなしで開く「今日の Gem」、検索語から絞り込む「Gem 候補の一覧」の 3 か所に出します。並び順を変えるのは「今日の Gem」と「Gem 候補の一覧」だけで、キーワード検索結果の並び順は変えません。」へ差し替える", "file": "site/index.html" },
    { "id": "F-7", "severity": "must", "issue": "E", "problem": "Gem バッジという新しい UI 要素を初見ユーザーが誤読しうる（付かない = 低評価と読む）", "fix": "FAQ に「検索結果に付いている Gem の印は何ですか？」を F-6 の直後へ追加する。回答は「被依存数のわりに star が少ないリポジトリの目印です。12 のパッケージレジストリから集めた候補プールに載っているカードに付き、検索結果の並び順は変えません。限られたデータにもとづく参考値なので、付いていないことが低評価という意味にはなりません。」", "file": "site/index.html" },
    { "id": "F-8", "severity": "must", "issue": "C", "problem": "ヒーローの shot-mobile.webp と desktop の shot-search.webp が Gem バッジ・avatar・Gem 導線の追加前の画面", "fix": "`/ja?q=react` を 390×780（出力 640）と 1280×820（出力 1600）で撮り直し、`alt` に avatar・Gem バッジ・「この検索語の Gem 候補を一覧で見る」導線を反映する。`site/index.html` の width/height を実寸へ更新する", "file": "site/assets/img/shot-mobile.webp, site/assets/img/shot-search.webp, site/index.html" },
    { "id": "F-9", "severity": "must", "issue": "C", "problem": "Gem 一覧（SP-19）の画面が LP に一切写っていない", "fix": "`/ja/gems?q=react` を 1280×760（出力 1600）で撮影し `site/assets/img/shot-gems.webp` として追加、F-3 の bento 新タイルの `tile-figure` に置く。`loading=\"lazy\"` `decoding=\"async\"` と実寸の width/height を付ける", "file": "site/assets/img/shot-gems.webp, site/index.html" },
    { "id": "F-10", "severity": "should", "issue": "B", "problem": "shot-mobile を撮り直すと画面に Gem バッジが写るのに、ヒーローの shot-caption がそれに触れていない", "fix": "shot-caption に「一部のカードに付いている Gem の印については「仕組み」で説明しています。」を 1 文追加する（`#how` へのリンク付き）。h1 と hero-lead 本文は変更しない", "file": "site/index.html" },
    { "id": "F-11", "severity": "should", "issue": "C", "problem": "`why` → `how` が純粋な散文の連続で視覚的な手がかりがない（実画像で確認）", "fix": "gpt-image-2 で `why-divider`（仮称・文字なしの透過装飾。中空の星アウトライン → 矢印 → 塗りの青い原石）を 1024² 透過で生成し、`tools/ui-assets/to_web_assets.mjs` で縮小した透過 WebP を `site/assets/img/` へ置き、`why` セクションの compare-arrow 周辺に `alt=\"\"` で配置する。既存 `hero-idle` / `gem` と同じ線画トーン。1 枚 30KB 未満を目標", "file": "site/assets/img/why-divider.webp, site/index.html, site/assets/styles.css" },
    { "id": "F-12", "severity": "should", "issue": "D", "problem": "このクラウドコンテナでは Chromium から外部 HTTPS が ERR_CONNECTION_RESET になり、ローカル next start も GitHub Search API がプロキシに 403 で塞がれるため、撮影経路が存在しない", "fix": "`tools/capture_lp_screenshots.mjs` に `LP_SHOT_FETCH_VIA_CURL=1`（既定 off）を追加し、on のとき `page.route('**')` で全リクエストを横取りして `curl` 経由で取得・`route.fulfill` する。`site/README.md`「スクリーンショットの更新」に「直接 HTTPS が通らないサンドボックスでの回避策」として追記する（恒久のベストプラクティスとは書かない）。あわせて `SHOTS` 配列に `shot-gems` を追加する", "file": "tools/capture_lp_screenshots.mjs, site/README.md" },
    { "id": "F-13", "severity": "later", "issue": "A", "problem": "og:description / meta description の「star 111 なのに 26,633 個」は実データと一致するが、OGP は脚注を持てないため「ある日の一例」であることを示せない", "fix": "今回は据え置き。将来 OGP 文言を見直すときに「毎日入れ替わる例の一つ」という言い回しを検討する（別 Issue）", "file": "site/index.html" }
  ],
  "screenshots": [
    { "name": "shot-mobile", "screen": "検索結果（スマートフォン）/ja?q=react", "viewport": "390x780 (dsf2) → 出力幅 640", "reason": "Gem バッジ・avatar 追加前の画面のため。ヒーローの主役画像" },
    { "name": "shot-search", "screen": "検索結果（PC）/ja?q=react", "viewport": "1280x820 (dsf2) → 出力幅 1600", "reason": "同上。加えて「この検索語の Gem 候補を一覧で見る」導線が写るようになる" },
    { "name": "shot-gems", "screen": "Gem 一覧 /ja/gems?q=react", "viewport": "1280x760 (dsf2) → 出力幅 1600", "reason": "SP-19 の画面が LP に一切写っていないため新規追加" },
    { "name": "shot-digest", "screen": "今日の Gem（撮り直さない）", "viewport": "—", "reason": "実画像で確認したところ avatar・バッジとも無く、新機能 3 点の影響を受けていない" }
  ],
  "infographics": [
    { "file": "docs/infographics/*.webp（全 14 点）", "use": "no", "placement": "—", "alt": "—", "reason": "① 日本語の文字が焼き込まれており ADR 0015 §2.2 の「文字を焼き込まない」方針と WCAG 1.4.5 に抵触 ② M-n / NFR-n / AC-n 等の社内管理コードが LP 読者（初見の個人開発者）に無意味 ③ 1 枚あたり 15〜25 個の独立した事実を持つ複合図で、同等の代替テキストを書くこと自体が非現実的 ④ 1 枚 205〜324KB で現行の画像合計 337KB とほぼ同等の重さが乗る（補強材料）。サイズは圧縮で解決できるが ①〜③ は解決できないため不使用" }
  ],
  "generated_assets": [
    { "name": "why-divider", "purpose": "`why` セクションの compare-arrow 周辺に置く文字なしの透過装飾（alt=\"\"）。star → 被依存数という視点の転換を絵で補強する", "prompt_direction": "既存 hero-idle.webp / gem.webp と同じ線画トーン（グレー〜クリームの小石、濃灰の輪郭線、アクセントは青い原石 1 個のみ）。文字・数字・記号を一切含めない。1024×1024・透過背景。tools/ui-assets/prompts/hero-idle.txt の共通スタイル段落を流用する", "reason": "実画像で確認した唯一の「純粋な散文が続く」区間が [why, how] であり、ここだけに絞れば ADR 0015 の趣旨（装飾は文字なし・ロケール非依存）を守ったまま単調さを緩和できる。error-* イラストが 6.0〜8.7KB に収まっている実績から重量の懸念もない" }
  ],
  "critical": [],
  "open_questions": []
}
