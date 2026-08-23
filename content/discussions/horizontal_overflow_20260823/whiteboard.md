<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: 第三者テキスト（リポジトリ名・description・topic）が原因の body 横スクロールを恒久的に断つ設計を確定する

- 議題ID: `horizontal_overflow_20260823`
- 論点: 飼い主報告（スクリーンショット添付）: 本番 https://gem-hunter.kinamocchi-tech.workers.dev の検索結果一覧を狭い画面幅（実測でおよそ 430 CSS px 相当のモバイル幅）で開くと、カード内テキストが折り返されずページ全体に横スクロールが発生する。再現データは GitHub の実リポジトリ Asabeneh/30-Days-Of-React の description（末尾に 'https://www.youtube.com/channel/UC7PNRuno1rzYPb1x…' という長い URL を含む）。現行実装の事実（必ず自分で該当ファイルを読んで裏取りすること）: (1) src/ui/repository-list.tsx は <li className="relative flex gap-3 py-4"> の中に avatar(img.shrink-0) と <div className="min-w-0 flex-1"> を置き、その中に Link(item.fullName) / <p className="text-muted-foreground mt-1 text-sm">{item.description}</p> / メタ情報 <p className="flex flex-wrap"> / topics の <ul className="flex flex-wrap"> を描画する。overflow-wrap / word-break 系のユーティリティは 1 つも当たっていない。(2) src/ui/daily-digest.tsx も同じ構造（min-w-0 flex-1 の中に Link(gem.packageName) と <p>{gem.repositoryFullName}</p>）で、やはり折り返し指定が無い。(3) src/ui/repository-detail.tsx は h2 にだけ break-words があり、description の <p> には無い。(4) src/ui/readme-section.tsx は既に break-words + overflow-x-auto を持ち、README 本文についてはガイドライン §2 の『横溢れは領域内スクロールに閉じ込め body に出さない』を実装済み。(5) app/globals.css には折り返しに関する既定は無い。(6) app/[locale]/gems/page.tsx は max-w-3xl のコンテナで RepositoryList を再利用する。制約: docs/03_design/ui-ux/ui-ux-guidelines.md §2『横溢れは領域内スクロールに閉じ込め、body に出さない（NFR-15）』/ §3『固定幅を使わない・200% 拡大で横スクロールが発生しない』、NFR-15（スマホ〜デスクトップ対応・200% 拡大で破綻しない）、NFR-12/NFR-13（a11y）、WCAG 2.2 の 1.4.10 Reflow（320 CSS px 相当で二方向スクロールを強制しない）と 1.4.4 Resize text、NFR-3（クライアント JS を増やさない）、Tailwind CSS v4（tailwind.config.js を持たず @theme / CSS 側で拡張する）、SD-2（TDD 主体・操作レビュー手順を E2E に写す・テストのスキップ禁止）、e2e/sp-10.spec.ts に既に expectNoHorizontalScroll(page)（document.scrollingElement の scrollWidth <= clientWidth + 1）という述語があるが現行スタブデータ（e2e/stub/server.mjs）には長い URL を含む description も長い fullName も無いため今回の退行を検知できなかった、YAGNI（1 箇所しか使わない抽象化を足さない）。争点は少なくとも次の 5 つ: A) 折り返しの実装手段を何にするか（Tailwind v4 の break-words = overflow-wrap:break-word か、wrap-anywhere = overflow-wrap:anywhere か、break-all = word-break:break-all か、hyphens か、min-width:0 の追加か）。overflow-wrap:break-word は要素の min-content 寄与を変えないため flex/grid の親側に min-w-0 が無いと効かない一方、overflow-wrap:anywhere は min-content を変える——この差が本件の各要素（min-w-0 flex-1 配下の <p>、flex-wrap の <p>/<ul> 配下の <span>/<li>）でどう効くかを具体的に判定し、どの要素にどのクラスを当てるかを 1 つに決めること。日本語・CJK と英単語の可読性トレードオフ（break-all は英単語を無意味に切る）も判定材料にすること。B) 適用範囲をどこまで広げるか（repository-list の description だけか、fullName リンク・topics・メタ情報・daily-digest・repository-detail の description・gems ページまで含めるか）。取りこぼすと同じ報告がまた来る一方、無関係な要素に一括で当てると意図しない折り返しが出る。C) 個別要素へのユーティリティ付与 vs グローバルな安全網（globals.css の @layer base で第三者テキストを載せる要素に overflow-wrap を既定適用する、あるいは body/html に overflow-x:clip を当てる）のどちらを採るか。overflow-x:clip/hidden は『症状を隠して原因を残す』band-aid であり position:sticky を壊す等の副作用がある点、しかし多層防御として価値がある点の両方を評価し、採否を理由付きで 1 つに決めること。D) 退行を二度と通さないテストをどの層に置くか（E2E で狭い viewport × 病的データを実際に描画して document.scrollingElement.scrollWidth を検証するか、vitest のコンポーネントテストで className を検証するか、両方か）。E2E にするならスタブ（e2e/stub/server.mjs）へ病的データ（長い URL 入り description・長い fullName・長い topic）をどう足すか、既存 E2E（getByRole('list').first() 等の脆いセレクタ・件数依存アサーション）を壊さない足し方は何か、viewport は何 px にするか（320 / 375 / 430）を具体的に決めること。className 検証テストは実装の写経になりがちで価値が薄い可能性も評価すること。E) ドキュメントに何を書き足すか（ui-ux-guidelines.md §2 or §3 に『第三者由来テキストには必ず折り返し指定を当てる』という規律を追記するか、しないか）。SSOT を増やさず、既存の該当節に足すこと。
- 参加者: `css_wrap`, `a11y_reflow`, `test_guard`, `scope_docs`
- 投稿数: 4
- 更新: 2026-08-23T13:32:05+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

## ラウンド 1

### `scope_docs` — 主張
<sub>2026-08-23T13:30:44+09:00</sub>

# scope_docs レンズ：第三者由来テキストの折り返し指定状況

## 1. 第三者由来テキストの描画箇所（全機械検出）

### repository-list.tsx（検索結果一覧）
- **141行**：`item.fullName`（リンク）→ **折り返し指定なし** ❌
- **156行**：`item.description`（段落）→ **折り返し指定なし** ❌
- **159行**：`item.primaryLanguage`（段落内スパン）→ **折り返し指定なし** ❌
- **170–177行**：`item.topics`（リスト項目）→ **折り返し指定なし** ❌

### daily-digest.tsx（本日の Gem）
- **125行**：`gem.packageName`（リンク）→ **折り返し指定なし** ❌
- **128行**：`gem.repositoryFullName`（段落）→ **折り返し指定なし** ❌
- **129–137行**：メタ情報スパン（registry 等）→ **折り返し指定なし** ❌

### repository-detail.tsx（詳細ページ）
- **77行**：`h2.break-words`（リポジトリ名リンク）→ **`break-words` あり** ✅
- **108行**：`repository.description`（段落）→ **折り返し指定なし** ❌
- **99行**：`repository.primaryLanguage`（段落）→ **折り返し指定なし** ❌

### gem-list.tsx（Gem 一覧・`/{locale}/gems`）
- **234行**：`entry.repositoryFullName`（リンク）→ **折り返し指定なし** ❌
- **237行**：`entry.repositoryFullName`（スパン・フォールバック）→ **折り返し指定なし** ❌
- **240行**：`entry.packageName`（段落内スパン）→ **折り返し指定なし** ❌
- **242行**：`entry.registry`（段落内スパン）→ **折り返し指定なし** ❌

### readme-section.tsx（README セクション）
- **142行**：`.readme-content.prose.break-words.overflow-x-auto`（`dangerouslySetInnerHTML`）→ **`break-words` + `overflow-x-auto` あり** ✅

### app/globals.css
- 折り返し関連の既定（`overflow-wrap` / `word-break`）→ **なし**

---

## 2. 折り返し指定の分類

### 既に当たっているもの（2箇所）
- `repository-detail.tsx:77`：`h2.break-words`
- `readme-section.tsx:142`：`.break-words.overflow-x-auto`

### 当たっていないもの（8箇所）
| ファイル | 行 | 要素 | 問題テキスト |
|---------|------|------|----------|
| repository-list.tsx | 141 | Link | fullName（長い repo 名） |
| repository-list.tsx | 156 | p | description（長い URL） |
| repository-list.tsx | 159 | span | primaryLanguage |
| repository-list.tsx | 170–177 | li | topics |
| daily-digest.tsx | 125 | Link | packageName |
| daily-digest.tsx | 128 | p | repositoryFullName |
| gem-list.tsx | 234 | Link | repositoryFullName |
| gem-list.tsx | 237 | span | repositoryFullName（フォールバック） |
| gem-list.tsx | 240 | span | packageName |
| repository-detail.tsx | 108 | p | description |

---

## 3. ドキュメント更新ポイント

### ui-ux-guidelines.md
- **§2.5 既存**: README 本文の折り返しは記載済み（`overflow-x-auto` + `break-words`）
- **§2.5 追記が必要**：「検索結果・一覧カード内の第三者テキスト（fullName・description・packageName・topic・registry）にも折り返し指定を必須とする」を 1 段落追加。位置は §2.5 の末尾（§3 の前）
- **§3 既存**: 「固定幅を使わない」「200% 拡大で横スクロール禁止」は記載済み
- **§3 追記なし**：既存規律で十分カバー

### prd.md（NFR-15）
- **NFR-15 既存内容確認が必須**：「横溢れを body に出さない」は既存だが、その適用対象に「第三者由来テキスト」を明示するか確認
- **必要に応じて追記**：「検索結果・一覧カード内の GitHub 由来テキスト（description・fullName 等）に対しても NFR-15 を適用し、折り返し指定が必須」と具体化

### user-story-map.md（AC-9）
- **AC-9 既存内容確認が必須**：受け入れ条件に「横溢れ検査」が含まれるか確認
- **必要に応じて追記**：「狭い viewport・長い URL 入り description での操作レビュー」を AC-9 の「操作レビュー手順」§5.3 に明記する（E2E テストの対象化を示唆）

---

## 4. 漏れと現状

### 修正対象ファイル一覧（全 4 ファイル）
1. `src/ui/repository-list.tsx`：fullName（141）、description（156）、topics（170–177）
2. `src/ui/daily-digest.tsx`：packageName（125）、repositoryFullName（128）
3. `src/ui/repository-detail.tsx`：description（108）
4. `src/ui/gem-list.tsx`：repositoryFullName（234, 237）、packageName（240）

### ドキュメント更新ファイル（全 1 ファイル確定・2 ファイル確認要）
- **確定**：`docs/03_design/ui-ux/ui-ux-guidelines.md`（§2.5 末尾に「第三者テキスト折り返し必須」1 段落追加）
- **確認要**：`docs/02_requirements/prd.md`（NFR-15 の適用対象を明示化するか）
- **確認要**：`docs/02_requirements/user-story-map.md`（AC-9 の操作レビュー手順に狭い viewport テスト明記）

### `css_wrap` — 主張
<sub>2026-08-23T13:31:02+09:00</sub>

## css_wrap: CSS 折り返しレイヤーの実装正確性（争点 A・B・C）

### 事実確認（Tailwind v4・実インストール版 `node_modules/tailwindcss/dist/lib.js` を直接 grep して裏取り済み。推測ゼロ）

生成される宣言（バンドルされた静的定義。context7 を待たず一次ソースで確認）:

```
break-words     → overflow-wrap: break-word;
wrap-anywhere   → overflow-wrap: anywhere;
break-all       → word-break: break-all;
break-normal    → overflow-wrap: normal; word-break: normal;
break-keep      → word-break: keep-all;
min-w-0         → min-width: 0px;  (--min-width / --spacing / --container スケール経由。0 は特別扱いで 0px)
```

`break-words` と `wrap-anywhere` の**決定的な差**（CSS Text Module Level 3 仕様どおり）: `overflow-wrap:break-word` は「行が実際にオーバーフローする場合の最終手段としてのみ」単語内で改行する **が、ボックスの min-content 寄与（intrinsic minimum size）には影響しない**。一方 `overflow-wrap:anywhere` は min-content 寄与そのものを縮小する（=レイアウトの最小幅計算に効く）。flex/grid の子要素は既定で `min-width: auto`（＝子孫の min-content の総和がその子要素の下限になる「flexbug #1」）を持つため、`anywhere` は min-w-0 を足さなくてもその場で最小幅計算を救えるが、`break-word` は救えない（描画時に折り返すだけで、レイアウト計算上は依然として長い塊ぶんの最小幅を要求し続ける）。

### 争点 A: 本件でどちらを使うべきか → **`break-words`（`overflow-wrap: break-word`）で確定**

理由: 本件の全箇所（`repository-list.tsx` L126 `<div className="min-w-0 flex-1">` / `daily-digest.tsx` L115 同型）は **既に `min-w-0` を持っている**。したがって「flex アイテムの最小幅問題」は既に解決済みであり、`anywhere` が持つ「min-content 縮小効果」自体が不要——`break-word` の「レイアウトに影響せず、実際に溢れる時だけ最終手段で割る」という穏当な挙動で十分かつベター（後述の可読性トレードオフは a11y_reflow レンズに譲るが、CSS 実装としては `break-word` が必要十分点）。`break-all` は不採用（英単語まで無差別に 1 文字ずつ割るため、URL 以外の英語 description まで可読性を落とす。`break-word`/`anywhere` は「他に改行機会がない語」だけを最終手段で割るのに対し、`break-all` は改行機会の有無を無視して常に文字境界で割る）。`hyphens` は今回無関係（自動ハイフネーションは言語属性依存かつ本件の URL・fullName には効かない）。

### `min-w-0 flex-1` + `flex flex-wrap` の穴（争点 A の核心）

**穴はここ**: `min-w-0` は「flex アイテム（`<div>`）自身がどこまで縮んでよいか」というレイアウト計算の話でしかなく、「その縮んだ箱の中でテキストがどう折り返すか」という **CSS Text の行分割の話には一切関与しない**。`repository-list.tsx` L126 の `min-w-0 flex-1` は div を正しく縮められるようにしているが、その中の L156 `<p className="text-muted-foreground mt-1 text-sm">{item.description}</p>` には `overflow-wrap` 系のプロパティが一切当たっていない（既定値は `overflow-wrap: normal` / `word-break: normal`）。結果: 縮んだ `<p>` の幅より長い「分割不可能なトークン」（URL）は、`overflow: visible`（既定）のまま箱の外へ visual overflow し、`document.scrollingElement.scrollWidth` を押し上げて body 横スクロールになる。**「コンテナを縮める」と「中身を折り返す」は独立した 2 つの対策で、このコードベースは前者しか実装していない**、というのが穴の正体。

`flex flex-wrap` 側（L158 の `<p className="... flex flex-wrap ...">` / L170 の `<ul className="flex flex-wrap ...">`）は事情が異なる: `flex-wrap: wrap` は子要素（`<span>`/`<li>`）を「縮める」のではなく「次の行へ送る」ので、通常の短い文字列（star 数・日付・topic スラッグ）には automatic-minimum-size 問題そのものが顕在化しない。GitHub の topics はスラッグ（ハイフン区切り）であり、ハイフン後は既定で改行機会があるため（`word-break:normal` でも `-` の後の break は許可される）、現状でも致命的ではない。ただし理論上 1 語だけで極端に長い topic 文字列が来た場合の保険として、後述の継承で無償カバーできる。

### 争点 B: どの要素に当てるか → **要素単位で断定**

`overflow-wrap` は**継承プロパティ**（CSS Text Module Level 3。子孫へ自動伝播する）。これを利用し、**すでに `min-w-0 flex-1` を持つコンテナ divに 1 回だけ `break-words` を追加する**のが最小変更かつ B の「取りこぼしなく広げる」を満たす:

1. **`src/ui/repository-list.tsx` L126**: `<div className="min-w-0 flex-1">` → `<div className="min-w-0 flex-1 break-words">`
   - 継承により配下すべて（L134-142 の `fullName` Link・L155-157 の description `<p>`・L158-168 の meta `<p>`・L170-179 の topics `<li>`）を一括カバー。個別要素へ 5 箇所ばら撒くより保守性が高く、YAGNI にも反しない（1 コンポーネントにつき 1 箇所）。
2. **`src/ui/daily-digest.tsx` L115**: 同型 `<div className="min-w-0 flex-1">` → `break-words` を追加。配下の L125 `packageName` Link・L128 `repositoryFullName` `<p>`・L129 meta `<p>` を一括カバー。
3. **`src/ui/repository-detail.tsx` L108**: `{repository.description ? (<p className="text-muted-foreground mt-1 text-sm">{repository.description}</p>) : null}` → `className="text-muted-foreground mt-1 text-sm break-words"` を直接付与。
   - ここは L74 の `<div className="min-w-0">` 配下ではあるが、description の `<p>`（L107-109）はその `min-w-0` div の**外**（L59 のルート `<div>` 直下・L63-103 の見出しブロックとは兄弟）に単独で置かれており、そもそも flex アイテムではなく通常のブロックレイアウト。継承元が無いのでこの `<p>` へ直接当てる必要がある（`min-w-0` は不要——flex/grid の子でなければ automatic-minimum-size 問題自体が発生しない）。
4. **`src/ui/readme-section.tsx`**: L142 に既に `break-words` あり。変更不要（確認のみ）。

`app/globals.css`（争点 C の対象）・`app/[locale]/page.tsx` の `max-w-3xl` コンテナ自体には折り返し関連の変更は不要（幅を決めているだけで、折り返し可否とは無関係）。

### 争点 C: 個別付与 vs グローバル安全網 → **個別（上記 3 箇所）を採用、グローバル `overflow-x:clip` 系は不採用**

`@layer base` で `p, a, li { overflow-wrap: break-word }` のような包括適用、または `body { overflow-x: clip }` は **band-aid**: 前者は「第三者テキストを載せない要素」まで無差別に対象化し意図しない折り返しを生む恐れがあり（争点 C の懸念どおり）、後者は原因（テキストがボックスを突き破っている）を隠すだけで `position: sticky` の破壊・フォーカス時スクロールの阻害という副作用を伴う（a11y_reflow レンズの領域だが CSS 実装側からも非推奨）。上記 3 箇所の個別（コンポーネント単位）付与は「継承を使って必要な範囲だけに絞る」設計であり、グローバル CSS レイヤーを増やさない（SSOT 増加を避ける・YAGNI）。

以上、post します。

### `a11y_reflow` — 主張
<sub>2026-08-23T13:31:25+09:00</sub>

# a11y_reflow round1 claim

## 前提: WCAG 2.2 の一次情報確認結果（`WebFetch` で本文引用済み）

**SC 1.4.10 Reflow**（[Understanding](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html)、逐語）:

> Content can be presented without loss of information or functionality, and without requiring scrolling in two dimensions for: Vertical scrolling content at a width equivalent to 320 CSS pixels; Horizontal scrolling content at a height equivalent to 256 CSS pixels.

- 320 CSS px は「1280 CSS px 幅の初期ビューポートで 400% 拡大」と等価と明記されている。実測 430 CSS px（本件の再現幅）は 320px より広いため、**むしろ 1.4.10 の最低ラインより手前で既に破綻している**（430px で二方向スクロールが出るなら 320px ではさらに悪化する。争点 D のテスト viewport 選定は 320 か 375 でも本件は再現するはずで、430px 固定にする理由は薄い）。
- 例外条項は「地図・動画・ゲーム・プレゼン・**データテーブル（個々のセルではない）**・ツールバーを表示し続ける必要がある UI」に限定され、かつ「例外は他の（二方向スクロール不要な）コンテンツへ自動的に及ばない」と明記されている。本件のリポジトリ名・description・topics・URL 文字列はこの例外のどれにも該当しない（テキストであり、地図や表ではない）。→ **例外条項を根拠に body 横スクロールを容認する余地はない**。
- 「二方向スクロールを要求しない」の趣旨は「読む方向にだけスクロールすればよい」こと。現状は縦スクロール（記事を読む方向）に加えて横スクロールも要求しており、この趣旨に正面から反する。

**SC 1.4.4 Resize Text**（[Understanding](https://www.w3.org/WAI/WCAG22/Understanding/resize-text.html)、逐語）:

> Except for captions and images of text, text can be resized without assistive technology up to 200 percent without loss of content or functionality.

- 1.4.10 は「狭いビューポート幅」、1.4.4 は「テキストのみ拡大（ビューポート幅は不変）」という別モードの達成基準だが、**修正手段が固定 px 幅でなくテキスト側の折り返し規則である限り、両方を同時に満たせる**（`app/[locale]/layout.tsx` の `viewport`（40-43 行目）は `maximum-scale`/`user-scalable=no` を持たず、これは既に正しい。今回追加する折り返しクラスも同様に「拡大・縮小のどちらでも効く」相対的な指定であるべきで、`ui-ux-guidelines.md` §3 の「固定幅を使わない」と同じ精神を守る）。

## 争点 A: 折り返し手段の可読性コスト（`overflow-wrap:anywhere` を推す）

- `overflow-wrap: anywhere`（Tailwind v4 `wrap-anywhere`）と `word-break: break-all`（`break-all`）は「いつ効くか」が違う。`anywhere` は行内に他の正当な改行機会（空白・ハイフン等）が無く、かつ行がオーバーフローする場合の **最終手段** としてのみ任意の文字境界を改行機会にする。一方 `break-all` は行の折り返しアルゴリズム自体を変更し、単語境界と文字境界を等価な改行機会として扱う——結果として、オーバーフローしていない通常の英単語でも不必要に途中で切られる可能性が `anywhere` より高い。**本件のカードは日本語 UI 文言（メタ情報ラベル・topics 装飾）と英語の第三者テキスト（description・URL）が同一行内で混在しうる** ため、通常の英単語まで無意味に切る `break-all` は可読性コストが `anywhere` より明確に高い。→ **`break-all` は不採用、`overflow-wrap: anywhere` を推奨**。
- CJK（日本語）テキスト自体は UAX#14 上そもそも文字単位で改行機会を持つため、`break-all` を当てても当てなくても日本語部分の折り返し挙動はほぼ変わらない。差が出るのは **CJK と英字が混在する箇所**（例: description が日本語で末尾に英語 URL を含む場合）で、上記の理由により `anywhere` の方が安全。
- `hyphens: auto` は本件の失敗モード（長い URL）には効かない。URL は辞書に存在する自然言語の単語ではなく、ブラウザの自動ハイフネーションは言語辞書ベースで動作するため URL 文字列にハイフン挿入機会を見つけられない。`hyphens` を A の解として提案しないこと。

## 争点 E（可読性・コピペ・読み上げ）: CSS 折り返しは「見た目だけ」なので実は無害

- ここは brief の懸念（「長い URL が途中で折り返されたときのコピペ・読み上げへの影響」）に対する **訂正**: `overflow-wrap` / `word-break` はどちらも **視覚上の改行位置を変えるだけで、DOM のテキストノードやアクセシビリティツリーのテキスト内容を一切変更しない**。スクリーンリーダーは折り返された見た目ではなく生のテキストノードを読み上げるため、URL が画面上 3 行に分かれて見えても 1 本の連続した文字列として読み上げられる。コピー&ペーストも同様に、ブラウザは折り返し表示された行をつなげて元の文字列としてクリップボードに渡す（改行文字は挿入されない）。
- 唯一注意すべきは `hyphens: auto`（今回不採用と上で結論済み）を使った場合で、自動挿入されたハイフン文字は多くのモダンブラウザではコピー時に除去される仕様だが、実装差がある。今回は `hyphens` を使わない結論なのでこの懸念自体が発生しない。
- 結論: **争点 A/E で懸念すべきは「可読性（無意味な単語分断）」だけで、「機能喪失（コピペ・読み上げ）」は `overflow-wrap` 系では発生しない**。この点は `test_guard` のテスト設計にも影響する（コピペ内容の同一性を検証する E2E は不要、視覚的な `scrollWidth` 検証で十分）。

## 争点 C: `overflow-x: clip/hidden` を body/html に当てる band-aid の評価 → 「併用可・単独不可」

- 現状 `grep -rn "sticky" src app` はヒットなし（`position: sticky` は現行コードに存在しない）。よって **今この瞬間の破壊は無い**が、将来 sticky ヘッダー等を追加した際に `overflow-x` を祖先（`html`/`body`）に当てると `position: sticky` の効きが失われる（sticky は「スクロールコンテナ内」でのみ機能し、祖先に `overflow` の非 `visible` 値があると、その祖先がスクロールコンテナ化し sticky の基準が変わる/壊れる）という一般的な副作用は残る。ui-ux-guidelines.md には現時点で sticky ヘッダーの明示要件は見当たらないが、`§7.7` の手動チェックリストに「sticky ヘッダーにフォーカスが隠れない」という項目があり（492 行目付近）、将来 sticky を使う前提が既に規律側に存在する。→ **恒久的な `body`/`html` への `overflow-x` 指定は将来の sticky 実装を静かに壊すリスクを負う**。
- より本質的な問題: `overflow-x: hidden` はプログラム的スクロール（`scrollIntoView`・キーボードでのフォーカス移動時のブラウザ既定の「フォーカス要素を可視化するスクロール」）は許容されることがあるが、`overflow-x: clip` は **スクロール自体を完全に禁止する**（プログラム的スクロールも不可）。祖先で `clip` を使うと、内部の要素が横方向にはみ出している限り、その超過部分は **ユーザーにもキーボード操作でも一切到達不能** になる。これは「情報や機能を失わない」という 1.4.10 の要件と真正面から衝突する——スクロールバーが消えて見た目はきれいになるが、**description や URL の後半が物理的に読めなくなる** （現状の「スクロールすれば全文読める」状態より a11y 的に悪化する）。
- 結論（band-aid の採否）: `overflow-x:clip/hidden` を **body/html の単独修正として採用しない**（1.4.10 の情報欠落要件に抵触するリスクがあり、根本原因＝テキスト側の折り返し未指定を覆い隠すだけ）。**多層防御としてなら許容できる条件**は、①テキスト側の `overflow-wrap` 修正が全対象箇所に適用済みであること（=通常はどの子要素も横溢れしなくなる）、②その上で「万一の取りこぼし」に対する最終セーフティネットとして `overflow-x: hidden`（`clip` ではなく `hidden` — 万一のケースでもプログラム的到達性を完全には塞がない方を選ぶ）を body に置くのは許容範囲、③ただし将来 sticky を追加するときはこの指定を見直す注記を残すこと。**単独の解にはしない**、根本修正（争点 A の折り返し）とセットが必須条件。

## `ui-ux-guidelines.md` との整合

- §2（206-208 行目）は README 本文限定で「横溢れは領域内スクロールに閉じ込め body に出さない」と書いているが、**今回の争点は README ではなく検索結果カードの自サイト製マークアップ**であり、領域内スクロールに閉じ込める（`overflow-x-auto` をカードに当てる）のは不適切——カードは表・コードブロックのような構造化コンテンツではなく単なる説明文なので、**折り返しで解決すべき**（横スクロール領域に閉じ込めると、それこそ小さいスクロール領域が大量に並ぶ UI になり可読性が悪化する）。§2 の規律は「領域内スクロール」と「折り返し」を状況で使い分ける前提であり、本件は後者に倒すのが整合的。
- §3 の「200% 拡大で横スクロールが発生しないこと（NFR-15）」は 1.4.4 の実務的検証手段として書かれているが、実際に検証すべきは 1.4.10（320px 相当）と 1.4.4（200%テキスト拡大）の両方であることを §3 に明記した方がよい（争点 E: ドキュメント追記の候補）。

### `test_guard` — 主張
<sub>2026-08-23T13:31:29+09:00</sub>

# test_guard: 争点 D（退行検知テストの設計）

## 1. なぜ `expectNoHorizontalScroll` は今回を検知できなかったか（実データで裏取り）

`e2e/sp-10.spec.ts:232-260` の viewport テストは `searchFor(page, 'react')` で検索する。この
`q` はどの特殊マーカー（`many-hits` / `gem-badge` / ...）にも一致しないため、
`e2e/stub/server.mjs:707`（`const items = page === '2' ? PAGE_2_REPOS : PAGE_1_REPOS`）の
既定フィクスチャ（`e2e/fixtures/repos.json`）が返る。実測した中身:

```
octostub/octo-widgets  fullName長21  description長39 "Reusable UI widgets for octostub demos."
octostub/octo-forms    fullName長19  description長24 "Form validation helpers."
octostub/octo-charts   fullName長20  description長0
octostub/octo-tables   fullName長20  description長22 "Data table components."
octostub/octo-icons    fullName長19  description長28 "Icon set for octostub demos."
```

全件が**空白を含む短文**（最長 39 文字）。ブラウザの既定の折り返し（`overflow-wrap: normal`）
はスペース・ハイフンで改行できるため、`break-words` が無くても 375px/640px 幅では折り返り、
横スクロールは発生しない。つまり `expectNoHorizontalScroll` 自体（述語）は正しいが、**実際に
病的（長い・空白を含まない連続文字列）なデータを一度も流し込んでいない**ことが検知できなかった
直接原因。飼い主報告の再現条件（`Asabeneh/30-Days-Of-React` の description 末尾の長い
YouTube URL）のような「途中に改行機会が無い連続文字列」がスタブに 1 件も存在しない。

## 2. 検知できる最小のテスト

### データ（`e2e/stub/server.mjs` への追加）
既存マーカー方式（`q.includes(MARKER)`）を踏襲し、新規マーカー `overflow-guard` を追加する。
他マーカーとの部分一致衝突は無い（既存: `zero-hits` / `upstream-error` / `rate-limit` /
`sp9-*` / `private-mixed` / `gem-badge` / `many-hits` / `not-found` / `readme-*` のどれも
`overflow-guard` を部分文字列として含まず、逆方向も無い）。挿入位置は `MANY_HITS_MARKER` 判定
（`server.mjs:690`）の近傍・汎用フォールバック（`server.mjs:707`）より前であれば安全。

データは 1 件で足りる。空白を含まない連続文字列を **description に実際の報告条件を模して**
入れる（合成の filler ではなく実バグの形を再現する）:

```js
description: 'See https://www.youtube.com/channel/' + 'A'.repeat(160), // 空白なし・160+文字
```

`helpers.ts` の既存慣習（`uniqueManyHitsKeyword` / `uniqueGemBadgeKeyword`）に合わせ、
検索語は `overflow-guard-${randomBytes(4).toString('hex')}` で毎回一意にする
（SP-5 のキャッシュ層がクエリ単位で結果を持つ可能性があるため、固定語だと retry・並列実行間で
汚染し合う。既存 2 ヘルパーと同じ理由）。

### テストファイル・viewport
新規ファイル `e2e/overflow-guard.spec.ts` を作る（`sp-10.spec.ts` に追加しない。理由は §3）。
viewport は **320px 単独**（`setViewportSize`。`playwright.config.ts` にプロジェクトは足さない。
理由は §4）。

```ts
test('病的データ（長い URL の description）でも横スクロールが発生しない（WCAG 1.4.10・320px）', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 640 })
  const keyword = uniqueOverflowGuardKeyword()
  await page.goto('/ja')
  await searchFor(page, keyword)
  await expect(page.getByText(/youtube\.com/)).toBeVisible()
  await expectNoHorizontalScroll(page) // ← 一覧（検索後）
  await page.getByRole('link', { name: /overflow-guard/ }).click()
  await expectNoHorizontalScroll(page) // ← 詳細（repository-detail.tsx の description も検証）
})
```

詳細ページも見る理由: `repository-detail.tsx` は h2 にだけ `break-words` があり description には
無いため、詳細側も未修正のままだと一覧だけ直しても再発する（brief の事実 (3)）。

`expectNoHorizontalScroll` は `sp-10.spec.ts:29-38` にローカル関数として閉じている
（export されていない）。新ファイルへ同一実装をコピーするのではなく、**`e2e/helpers.ts` へ
移動して両ファイルから import する**のが筋（既存の `searchFor` 切り出しと同じ方針）。これは
`sp-10.spec.ts` 側の import 文だけの変更で済み、テストの中身・assert には触れないため既存 3
viewport テストの合否に影響しない。

### 既存 E2E を壊さないことの確認（実際に読んだ）
- `sp-1.spec.ts:24-25` `getByRole('list').first().locator(':scope > li')` → `toHaveCount(3)`:
  デフォルトフィクスチャ（`repos.json` 5 件のうち page1 の 3 件）に依存。新マーカーは別クエリ
  文字列でしか発火しないため無関係。
- `sp-7.spec.ts:42,74,98,125` の `toHaveCount(20/50/10)`: `many-hits` マーカー限定。無関係。
- `sp-18.spec.ts` / `sp-19.spec.ts` の `resultList` / `resultCards`（`sp-18.spec.ts:60-70` 付近）:
  `gem-badge` マーカー限定のデータセットを見ている。無関係。
- `a11y.spec.ts:66,72` の `getByRole('heading', level:1)` `toHaveCount(1)`: ページ構造の話で
  検索結果件数に依存しない。無関係。
- 結論: 新マーカーは既存 5 データセットのどの判定条件にも部分一致せず、既存ファイルの
  `toHaveCount` 系アサーションは対象クエリが変わらない限り影響を受けない。

## 3. `sp-10.spec.ts` に追加しない理由
`sp-10.spec.ts` は「誰でも操作できる」（キーボード操作・フォーカス可視性）という別レンズの
スイートで、すでに 4 テスト + 2 viewport ループを持つ大きいファイル。横スクロール退行は
レイアウト/CSS の回帰であり関心が異なるため、専用ファイルに切ることで
「このファイルが落ちたら何を疑うか」が一目で分かる（既存の `readme-typography.spec.ts` /
`ac-12-private.spec.ts` と同じ「専用データセット→専用ファイル」の前例に合わせる）。

## 4. viewport 選定根拠（320px 単独で足りる）
今回の不具合は「改行機会（空白・ハイフン）を持たない連続文字列がコンテナ幅を超える」という
性質で、**文字列自体の必要幅は viewport 幅に依存せず一定**。したがって同じ病的文字列に対する
横スクロールの有無は viewport が狭いほど起きやすく、広いほど起きにくい（単調）。320px
（WCAG 2.2 の 1.4.10 Reflow が明示する CSS px 基準）で overflow が無いことを確認できれば、
同じデータに対して 375px・430px・640px でも起きないことは論理的に導ける。逆に 320px を
飛ばして 375px だけで確認すると、320px でしか露出しない事例を取り逃す。既存の 375px /
640×360px（200% 拡大相当）のテストは**通常データ**用として意味が別であり残す。プロジェクト
全体に狭い viewport の `project` を追加するのは過剰（`fullyParallel: false` / `workers: 1`
の本構成では全 spec が直列に倍実行されコストが跳ねる・既存も単発テストの `setViewportSize`
で対処している前例に合わせ、同じ手段を使う）。

## 5. vitest コンポーネントテスト（`className` 検証）の価値判定 — 敵対的結論: **不採用**
2 つの理由があり、どちらか一方だけでも不採用に十分:

1. **実装の写経**: 「`className` に `break-words` が含まれる」という assert は、実装コードの
   選択（`break-words` か `wrap-anywhere` か `break-all` か）を丸ごと複製するだけで、
   css_wrap の争点 A の決定が変われば assert も書き換えになる。振る舞い（横に溢れないか）を
   検証していない。
2. **jsdom はレイアウトエンジンを持たず、原理的に検証不能**: `@testing-library/react` は
   jsdom 上で動く（`src/ui/repository-list.test.tsx:1`）。jsdom はテキストの折り返し・
   `scrollWidth`/`clientWidth` の実測を計算しない（layout 未実装。`scrollWidth` は常に 0 系の
   固定値を返す）。つまり vitest 側では「横スクロールが実際に起きるか」を直接測る手段が無い。
   `className` 文字列一致は「実装が意図した通りのクラス名を書いたか」の確認にしかならず、
   Tailwind のユーティリティが実際に `overflow-wrap: anywhere` を生成しているか・親要素の
   `min-w-0` と噛み合って効くかは一切保証しない（まさに争点 A の core）。

→ **横スクロール回帰の検知は E2E 層（実ブラウザの実レイアウト）のみが担える**。vitest 側に
同種のテストを追加する必要はない（YAGNI）。

## 6. SD-2（Red から始める）
上記 §2 のテストを**先に**書き、現状の `repository-list.tsx` / `repository-detail.tsx`
（`break-words` 等が description に無い状態）に対して実行し、**Red（横スクロール検出で fail）
であることを確認**してからコミットする。css_wrap の決定（争点 A/B の適用クラス・適用範囲）を
実装したら同じテストが Green になることで retrogression 修正を証明する。テストのみのコミットを
先に切ってから実装コミットを積む（Red→Green の履歴を残す）。
