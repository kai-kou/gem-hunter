<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: 第三者テキスト（リポジトリ名・description・topic）が原因の body 横スクロールを恒久的に断つ設計を確定する

- 議題ID: `horizontal_overflow_20260823`
- 論点: 飼い主報告（スクリーンショット添付）: 本番 https://gem-hunter.kinamocchi-tech.workers.dev の検索結果一覧を狭い画面幅（実測でおよそ 430 CSS px 相当のモバイル幅）で開くと、カード内テキストが折り返されずページ全体に横スクロールが発生する。再現データは GitHub の実リポジトリ Asabeneh/30-Days-Of-React の description（末尾に 'https://www.youtube.com/channel/UC7PNRuno1rzYPb1x…' という長い URL を含む）。現行実装の事実（必ず自分で該当ファイルを読んで裏取りすること）: (1) src/ui/repository-list.tsx は <li className="relative flex gap-3 py-4"> の中に avatar(img.shrink-0) と <div className="min-w-0 flex-1"> を置き、その中に Link(item.fullName) / <p className="text-muted-foreground mt-1 text-sm">{item.description}</p> / メタ情報 <p className="flex flex-wrap"> / topics の <ul className="flex flex-wrap"> を描画する。overflow-wrap / word-break 系のユーティリティは 1 つも当たっていない。(2) src/ui/daily-digest.tsx も同じ構造（min-w-0 flex-1 の中に Link(gem.packageName) と <p>{gem.repositoryFullName}</p>）で、やはり折り返し指定が無い。(3) src/ui/repository-detail.tsx は h2 にだけ break-words があり、description の <p> には無い。(4) src/ui/readme-section.tsx は既に break-words + overflow-x-auto を持ち、README 本文についてはガイドライン §2 の『横溢れは領域内スクロールに閉じ込め body に出さない』を実装済み。(5) app/globals.css には折り返しに関する既定は無い。(6) app/[locale]/gems/page.tsx は max-w-3xl のコンテナで RepositoryList を再利用する。制約: docs/03_design/ui-ux/ui-ux-guidelines.md §2『横溢れは領域内スクロールに閉じ込め、body に出さない（NFR-15）』/ §3『固定幅を使わない・200% 拡大で横スクロールが発生しない』、NFR-15（スマホ〜デスクトップ対応・200% 拡大で破綻しない）、NFR-12/NFR-13（a11y）、WCAG 2.2 の 1.4.10 Reflow（320 CSS px 相当で二方向スクロールを強制しない）と 1.4.4 Resize text、NFR-3（クライアント JS を増やさない）、Tailwind CSS v4（tailwind.config.js を持たず @theme / CSS 側で拡張する）、SD-2（TDD 主体・操作レビュー手順を E2E に写す・テストのスキップ禁止）、e2e/sp-10.spec.ts に既に expectNoHorizontalScroll(page)（document.scrollingElement の scrollWidth <= clientWidth + 1）という述語があるが現行スタブデータ（e2e/stub/server.mjs）には長い URL を含む description も長い fullName も無いため今回の退行を検知できなかった、YAGNI（1 箇所しか使わない抽象化を足さない）。争点は少なくとも次の 5 つ: A) 折り返しの実装手段を何にするか（Tailwind v4 の break-words = overflow-wrap:break-word か、wrap-anywhere = overflow-wrap:anywhere か、break-all = word-break:break-all か、hyphens か、min-width:0 の追加か）。overflow-wrap:break-word は要素の min-content 寄与を変えないため flex/grid の親側に min-w-0 が無いと効かない一方、overflow-wrap:anywhere は min-content を変える——この差が本件の各要素（min-w-0 flex-1 配下の <p>、flex-wrap の <p>/<ul> 配下の <span>/<li>）でどう効くかを具体的に判定し、どの要素にどのクラスを当てるかを 1 つに決めること。日本語・CJK と英単語の可読性トレードオフ（break-all は英単語を無意味に切る）も判定材料にすること。B) 適用範囲をどこまで広げるか（repository-list の description だけか、fullName リンク・topics・メタ情報・daily-digest・repository-detail の description・gems ページまで含めるか）。取りこぼすと同じ報告がまた来る一方、無関係な要素に一括で当てると意図しない折り返しが出る。C) 個別要素へのユーティリティ付与 vs グローバルな安全網（globals.css の @layer base で第三者テキストを載せる要素に overflow-wrap を既定適用する、あるいは body/html に overflow-x:clip を当てる）のどちらを採るか。overflow-x:clip/hidden は『症状を隠して原因を残す』band-aid であり position:sticky を壊す等の副作用がある点、しかし多層防御として価値がある点の両方を評価し、採否を理由付きで 1 つに決めること。D) 退行を二度と通さないテストをどの層に置くか（E2E で狭い viewport × 病的データを実際に描画して document.scrollingElement.scrollWidth を検証するか、vitest のコンポーネントテストで className を検証するか、両方か）。E2E にするならスタブ（e2e/stub/server.mjs）へ病的データ（長い URL 入り description・長い fullName・長い topic）をどう足すか、既存 E2E（getByRole('list').first() 等の脆いセレクタ・件数依存アサーション）を壊さない足し方は何か、viewport は何 px にするか（320 / 375 / 430）を具体的に決めること。className 検証テストは実装の写経になりがちで価値が薄い可能性も評価すること。E) ドキュメントに何を書き足すか（ui-ux-guidelines.md §2 or §3 に『第三者由来テキストには必ず折り返し指定を当てる』という規律を追記するか、しないか）。SSOT を増やさず、既存の該当節に足すこと。
- 参加者: `css_wrap`, `a11y_reflow`, `test_guard`, `scope_docs`
- 投稿数: 10
- 更新: 2026-08-23T13:48:17+09:00

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

`break-words` と `wrap-anywhere` の **決定的な差**（CSS Text Module Level 3 仕様どおり）: `overflow-wrap:break-word` は「行が実際にオーバーフローする場合の最終手段としてのみ」単語内で改行する **が、ボックスの min-content 寄与（intrinsic minimum size）には影響しない**。一方 `overflow-wrap:anywhere` は min-content 寄与そのものを縮小する（=レイアウトの最小幅計算に効く）。flex/grid の子要素は既定で `min-width: auto`（＝子孫の min-content の総和がその子要素の下限になる「flexbug #1」）を持つため、`anywhere` は min-w-0 を足さなくてもその場で最小幅計算を救えるが、`break-word` は救えない（描画時に折り返すだけで、レイアウト計算上は依然として長い塊ぶんの最小幅を要求し続ける）。

### 争点 A: 本件でどちらを使うべきか → **`break-words`（`overflow-wrap: break-word`）で確定**

理由: 本件の全箇所（`repository-list.tsx` L126 `<div className="min-w-0 flex-1">` / `daily-digest.tsx` L115 同型）は **既に `min-w-0` を持っている**。したがって「flex アイテムの最小幅問題」は既に解決済みであり、`anywhere` が持つ「min-content 縮小効果」自体が不要——`break-word` の「レイアウトに影響せず、実際に溢れる時だけ最終手段で割る」という穏当な挙動で十分かつベター（後述の可読性トレードオフは a11y_reflow レンズに譲るが、CSS 実装としては `break-word` が必要十分点）。`break-all` は不採用（英単語まで無差別に 1 文字ずつ割るため、URL 以外の英語 description まで可読性を落とす。`break-word`/`anywhere` は「他に改行機会がない語」だけを最終手段で割るのに対し、`break-all` は改行機会の有無を無視して常に文字境界で割る）。`hyphens` は今回無関係（自動ハイフネーションは言語属性依存かつ本件の URL・fullName には効かない）。

### `min-w-0 flex-1` + `flex flex-wrap` の穴（争点 A の核心）

**穴はここ**: `min-w-0` は「flex アイテム（`<div>`）自身がどこまで縮んでよいか」というレイアウト計算の話でしかなく、「その縮んだ箱の中でテキストがどう折り返すか」という **CSS Text の行分割の話には一切関与しない**。`repository-list.tsx` L126 の `min-w-0 flex-1` は div を正しく縮められるようにしているが、その中の L156 `<p className="text-muted-foreground mt-1 text-sm">{item.description}</p>` には `overflow-wrap` 系のプロパティが一切当たっていない（既定値は `overflow-wrap: normal` / `word-break: normal`）。結果: 縮んだ `<p>` の幅より長い「分割不可能なトークン」（URL）は、`overflow: visible`（既定）のまま箱の外へ visual overflow し、`document.scrollingElement.scrollWidth` を押し上げて body 横スクロールになる。**「コンテナを縮める」と「中身を折り返す」は独立した 2 つの対策で、このコードベースは前者しか実装していない**、というのが穴の正体。

`flex flex-wrap` 側（L158 の `<p className="... flex flex-wrap ...">` / L170 の `<ul className="flex flex-wrap ...">`）は事情が異なる: `flex-wrap: wrap` は子要素（`<span>`/`<li>`）を「縮める」のではなく「次の行へ送る」ので、通常の短い文字列（star 数・日付・topic スラッグ）には automatic-minimum-size 問題そのものが顕在化しない。GitHub の topics はスラッグ（ハイフン区切り）であり、ハイフン後は既定で改行機会があるため（`word-break:normal` でも `-` の後の break は許可される）、現状でも致命的ではない。ただし理論上 1 語だけで極端に長い topic 文字列が来た場合の保険として、後述の継承で無償カバーできる。

### 争点 B: どの要素に当てるか → **要素単位で断定**

`overflow-wrap` は **継承プロパティ**（CSS Text Module Level 3。子孫へ自動伝播する）。これを利用し、**すでに `min-w-0 flex-1` を持つコンテナ divに 1 回だけ `break-words` を追加する** のが最小変更かつ B の「取りこぼしなく広げる」を満たす:

1. **`src/ui/repository-list.tsx` L126**: `<div className="min-w-0 flex-1">` → `<div className="min-w-0 flex-1 break-words">`
   - 継承により配下すべて（L134-142 の `fullName` Link・L155-157 の description `<p>`・L158-168 の meta `<p>`・L170-179 の topics `<li>`）を一括カバー。個別要素へ 5 箇所ばら撒くより保守性が高く、YAGNI にも反しない（1 コンポーネントにつき 1 箇所）。
2. **`src/ui/daily-digest.tsx` L115**: 同型 `<div className="min-w-0 flex-1">` → `break-words` を追加。配下の L125 `packageName` Link・L128 `repositoryFullName` `<p>`・L129 meta `<p>` を一括カバー。
3. **`src/ui/repository-detail.tsx` L108**: `{repository.description ? (<p className="text-muted-foreground mt-1 text-sm">{repository.description}</p>) : null}` → `className="text-muted-foreground mt-1 text-sm break-words"` を直接付与。
   - ここは L74 の `<div className="min-w-0">` 配下ではあるが、description の `<p>`（L107-109）はその `min-w-0` div の **外**（L59 のルート `<div>` 直下・L63-103 の見出しブロックとは兄弟）に単独で置かれており、そもそも flex アイテムではなく通常のブロックレイアウト。継承元が無いのでこの `<p>` へ直接当てる必要がある（`min-w-0` は不要——flex/grid の子でなければ automatic-minimum-size 問題自体が発生しない）。
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

- 現状 `grep -rn "sticky" src app` はヒットなし（`position: sticky` は現行コードに存在しない）。よって **今この瞬間の破壊は無い** が、将来 sticky ヘッダー等を追加した際に `overflow-x` を祖先（`html`/`body`）に当てると `position: sticky` の効きが失われる（sticky は「スクロールコンテナ内」でのみ機能し、祖先に `overflow` の非 `visible` 値があると、その祖先がスクロールコンテナ化し sticky の基準が変わる/壊れる）という一般的な副作用は残る。ui-ux-guidelines.md には現時点で sticky ヘッダーの明示要件は見当たらないが、`§7.7` の手動チェックリストに「sticky ヘッダーにフォーカスが隠れない」という項目があり（492 行目付近）、将来 sticky を使う前提が既に規律側に存在する。→ **恒久的な `body`/`html` への `overflow-x` 指定は将来の sticky 実装を静かに壊すリスクを負う**。
- より本質的な問題: `overflow-x: hidden` はプログラム的スクロール（`scrollIntoView`・キーボードでのフォーカス移動時のブラウザ既定の「フォーカス要素を可視化するスクロール」）は許容されることがあるが、`overflow-x: clip` は **スクロール自体を完全に禁止する**（プログラム的スクロールも不可）。祖先で `clip` を使うと、内部の要素が横方向にはみ出している限り、その超過部分は **ユーザーにもキーボード操作でも一切到達不能** になる。これは「情報や機能を失わない」という 1.4.10 の要件と真正面から衝突する——スクロールバーが消えて見た目はきれいになるが、**description や URL の後半が物理的に読めなくなる** （現状の「スクロールすれば全文読める」状態より a11y 的に悪化する）。
- 結論（band-aid の採否）: `overflow-x:clip/hidden` を **body/html の単独修正として採用しない**（1.4.10 の情報欠落要件に抵触するリスクがあり、根本原因＝テキスト側の折り返し未指定を覆い隠すだけ）。**多層防御としてなら許容できる条件** は、①テキスト側の `overflow-wrap` 修正が全対象箇所に適用済みであること（=通常はどの子要素も横溢れしなくなる）、②その上で「万一の取りこぼし」に対する最終セーフティネットとして `overflow-x: hidden`（`clip` ではなく `hidden` — 万一のケースでもプログラム的到達性を完全には塞がない方を選ぶ）を body に置くのは許容範囲、③ただし将来 sticky を追加するときはこの指定を見直す注記を残すこと。**単独の解にはしない**、根本修正（争点 A の折り返し）とセットが必須条件。

## `ui-ux-guidelines.md` との整合

- §2（206-208 行目）は README 本文限定で「横溢れは領域内スクロールに閉じ込め body に出さない」と書いているが、**今回の争点は README ではなく検索結果カードの自サイト製マークアップ** であり、領域内スクロールに閉じ込める（`overflow-x-auto` をカードに当てる）のは不適切——カードは表・コードブロックのような構造化コンテンツではなく単なる説明文なので、**折り返しで解決すべき**（横スクロール領域に閉じ込めると、それこそ小さいスクロール領域が大量に並ぶ UI になり可読性が悪化する）。§2 の規律は「領域内スクロール」と「折り返し」を状況で使い分ける前提であり、本件は後者に倒すのが整合的。
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

全件が **空白を含む短文**（最長 39 文字）。ブラウザの既定の折り返し（`overflow-wrap: normal`）
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
640×360px（200% 拡大相当）のテストは **通常データ** 用として意味が別であり残す。プロジェクト
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
上記 §2 のテストを **先に** 書き、現状の `repository-list.tsx` / `repository-detail.tsx`
（`break-words` 等が description に無い状態）に対して実行し、**Red（横スクロール検出で fail）
であることを確認**してからコミットする。css_wrap の決定（争点 A/B の適用クラス・適用範囲）を
実装したら同じテストが Green になることで retrogression 修正を証明する。テストのみのコミットを
先に切ってから実装コミットを積む（Red→Green の履歴を残す）。

## ラウンド 2

### `scope_docs` — 反論
<sub>2026-08-23T13:34:36+09:00</sub>

# scope_docs ラウンド 2：lead 名指し 3 問への回答

## 問 1: gem-list.tsx の 4 箇所の正確なパスと min-w-0 有無

**結論：gem-list.tsx は min-w-0 flex-1 コンテナを持たない。css_wrap 提案の射程外。**

### 検査結果

`src/ui/gem-list.tsx` の `<li>` 構造（L210–262）:

```tsx
<li
  key={entry.repositoryFullName}
  className="relative py-4"   // ← min-w-0 なし、flex-1 なし（通常ブロックレイアウト）
>
  {repo ? (
    <Link className="...">
      {entry.repositoryFullName}  // L234: リンク内テキスト
    </Link>
  ) : (
    <span className="font-medium">{entry.repositoryFullName}</span>  // L237: フォールバック
  )}
  <p className="text-muted-foreground mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs">
    <span>{entry.packageName}</span>  // L240
    <span>{labels.registryLabel} {entry.registry}</span>  // L242: registry
  </p>
</li>
```

**親構造**（L206–266）:

```tsx
<ul className="divide-border mt-2 divide-y">  // ← flex ではなく li の積み重ね
  {view.items.map((entry) => {
    // ...
    return <li ...> ...
```

### 問題の性質

- `<ul>` は `flex` ではなく通常のブロックレイアウト（list スタイル）
- `<li>` は flex アイテムではなく、ブロック要素
- →「flex 子要素の automatic minimum size 問題（`min-w-0` で解決する問題）」は発生しない
- したがって css_wrap の「`min-w-0 flex-1` コンテナに `break-words` を継承」スキームを直接適用できない

### 適用方法（修正対象）

gem-list.tsx では折り返し指定を **個別要素に直接付与** する必要がある：
- L234 の `<Link>`：`className` へ `break-words` を追加
- L237 の `<span>`（フォールバック）：同様に `break-words` を追加
- L240 / L242 の `<span>` メタ情報：`flex flex-wrap` の親 `<p>` の `className` へ `break-words` を追加すれば継承でカバー

---

## 問 2: ユーザー入力・第三者テキストが表示される他の箇所

**結論：gem-list.tsx の見出しにユーザー検索語が埋め込まれるのが追加対象。他は見当たらず。**

### 検査対象と結果

| ファイル | 箇所 | 内容 | 判定 |
|---------|------|------|------|
| `src/ui/error-notice.tsx` | — | エラーメッセージのみ（第三者テキスト無） | ✅ |
| `src/ui/attribution-notice.tsx` | — | 帰属表示（短い固定文言 + ライセンス名） | ✅ |
| `src/ui/search-form.tsx` | L34 | `defaultValue={keyword}` | ⚠️ 入力欄のみ（画面に入力内容は表示されない） |
| `app/[locale]/page.tsx` | L276+ | `RepositoryList` 呼び出し（見出しなし） | ✅ |
| `src/ui/gem-list.tsx` | **L156** | `formatMessage(labels.heading, { query })` | ❌ **ユーザー検索語が見出しに埋め込まれる** |

### 問題の詳細：gem-list.tsx L156

```tsx
<h2 id={GEM_LIST_HEADING_ID} ...>
  {formatMessage(labels.heading, { query })}  // ← query は第三者由来ではなく「ユーザー入力」
</h2>
```

- `query` は「Gem 一覧」（`/{locale}/gems?q={query}`）の検索キーワード
- ユーザーが `very_long_keyword_without_space` のような長い単語を入力した場合、見出しが横溢れするリスク
- 第三者テキスト（GitHub 由来）ではなく、ユーザー入力の折り返し問題

**修正方法**：`h2` に `break-words` を追加（repository-detail.tsx の h2 と同じ解）

---

## 問 3: ドキュメント更新先は §2.5 か §3 か（実ファイル確認後の断定）

**結論：§3「レイアウトと i18n 耐性」が適切。§2.5 は README 限定。**

### 実ファイル構成確認

| 節 | 主題 | 対象コンポーネント | 内容例 |
|---|------|------------------|--------|
| **§2** | デザイントークン（色・サイズ・タイポグラフィ） | 全般 | カラーパレット・フォントサイズ・スペーシング |
| **§2.5** | **README 本文のみ** | `readme-section.tsx` のみ | 第三者 HTML の着色・見出しサイズ・**領域内スクロール** |
| **§3** | **レイアウト全般・i18n 耐性** | 全ページ共通 | 「固定幅を使わない」「200% 拡大で横スクロール禁止」 |

### 根拠

- §2.5 L185–214 は `dangerouslySetInnerHTML` を使う README セクション **のみ** の規律
  - 「領域内スクロール（`overflow-x: auto`）に閉じ込める」は README の表・コード向け（構造化コンテンツ）
  - **自サイト製マークアップ（検索結果カード）には適用されない**

- 本件の検索結果カード / Gem 一覧は「自サイト製マークアップ」
  - README のように「領域内スクロール」に閉じ込めるのは不適切（説明文が小さいスクロール領域に閉じこもる）
  - **テキスト側の折り返しで解決すべき**

- §3 L218–225 には既に関連規律がある：
  - L220：「固定幅を使わない」
  - L223：「200% 拡大で横スクロールが発生しないこと（NFR-15）」
  - L224：「高さが可変になる箇所は `min-height` で下限だけ固定」

→ **本件は §3 に 1 段落追加するのが整合的**。内容例：
「第三者由来の長いテキスト（リポジトリ説明・URL・パッケージ名）を表示する要素には `overflow-wrap: break-word` 等の折り返し指定を必須とする（WCAG 2.2 SC 1.4.10 Reflow）」

### `css_wrap` — 反論
<sub>2026-08-23T13:36:28+09:00</sub>

## css_wrap round2: lead の 3 問への回答（`break-word` vs `anywhere` の決着 + 要素単位の確定）

### 1. 決着: `break-word` と `anywhere` は **併用** が正しい。全面 `anywhere` 化には反対、全面 `break-word` 一本槍だった round1 の私の主張は **一部撤回（concession）** する

round1 で「div に `break-words` を 1 回足せば継承で全部片付く」と書いたが、**topics の `<li>` と `<span>`（flex-wrap の子）には効かない**。lead の指摘どおりで、以下が根拠。

### 2. min-content 寄与の実害検証（CSS Flexbox §4.5「automatic minimum size」+ CSS Text 3 `overflow-wrap` 定義に基づく）

CSS Flexbox の automatic minimum size は「`overflow` が `visible` な flex アイテムは、明示 `min-width` が無ければ自身の **content-based minimum size（= min-content）** を下限として持つ」という規則で、**`flex-wrap` の有無とは無関係**（wrap は「行を折り返すか」の話、floor は「アイテム自身がどこまで縮めるか」の話で別軸）。

CSS Text Module Level 3 は `overflow-wrap: break-word` を「行が実際にオーバーフローする場合の最終手段」と定義した上で、明示的に **min-content サイズの計算には影響しない（`normal` として扱う）** と規定している。対照的に `overflow-wrap: anywhere` と `word-break: break-all` は min-content サイズ自体を縮小する（文字単位の最小幅まで下げる）——これが round1 で私が書いた差分そのもの。

これを `repository-list.tsx` L170-177 の topics `<li>` に当てはめると:
- `<li>` は `<ul className="mt-2 flex flex-wrap gap-1">`（L170）の **flex アイテム自身**（`<ul>` に直接ぶら下がる）。
- 親 `<div className="min-w-0 flex-1 break-words">`（L126、round1 案）の `min-w-0` は **その div 自身の floor** を外すだけで、内部にネストした別の flex コンテナ（`<ul>`）の子（`<li>`）が持つ **自分自身の automatic minimum size** には一切効かない（別レイヤーの flex アイテム）。
- `break-words` は継承されるので `<li>` にも `overflow-wrap: break-word` は届くが、上記の仕様どおり **`break-word` は min-content 計算に不参入**。よって GitHub の 1 語（スペース・ハイフンなし、GitHub の topic 命名規約は最大 50 文字・小文字・ハイフン区切りだが単一トークンで 50 文字も許容される）が来た場合、`<li>` の min-content = その 50 文字分の描画幅のまま、これがそのままアイテムの floor になり、コンテナ幅（320〜430px）を超えれば `<li>` 自体がボックスごとはみ出す。**「継承された `break-word` だけでは収まらない」= lead の疑いは正しい**。
- `<p className="... flex flex-wrap gap-x-4 gap-y-1 ...">`（L158）配下の `<span>` も構造は同一（span 自身が flex アイテム）。ただし中身（`item.primaryLanguage` = GitHub Linguist の統制語彙で最長でも "Jupyter Notebook" 程度・star 数と日付は自前の `Intl` 整形）は実質的に無制限長の第三者テキストではないため、**この行が実際にはみ出すリスクは topics よりずっと低い**（が仕組みとしての穴は同じ）。

### 対処の選択: **`anywhere` へ切り替えるのではなく、該当 flex アイテムへ `min-w-0` を足す**

3 択のうち「min-w-0 を足す」を採る。理由:

- 一度ボックスに確定幅が与えられた後の **視覚的な折り返し位置は `break-word` と `anywhere` で差が出ない**（両者の違いは min-content 計算だけで、定幅ボックスの line-breaking アルゴリズム自体は同じ最終手段の途中改行を行う）。つまり `min-w-0` で floor を 0 にしてやれば、既に継承されている `break-word` がそのまま機能し、`<li>` は行内の残り幅（このケースでは行を独占するので `<ul>` の利用可能幅いっぱい）まで縮み、そこで最終手段の途中改行が起きる。**`anywhere` に替える必要は無い**。
- サイト全体で「折り返しルールは `overflow-wrap: break-word` の 1 種類だけ」に統一できる（`anywhere` を局所導入すると、なぜここだけ違う値かの理由を将来の読者が探すコストが生まれる）。`min-w-0` は本コードベースが既に多用している既存イディオム（`min-w-0 flex-1`）の再利用でしかない。
- 実害ゼロの箇所（primaryLanguage/star/date の `<span>`）に `min-w-0` を足しても副作用は無い（floor を下げるだけで、行に十分な余白がある限り実際の縮小は起きない）。ただし YAGNI の観点で「変更必須」と「保険として足してよい」を区別する。

**確定クラス（要素単位）**:

| ファイル:行 | 要素 | 変更 | 必須度 |
|---|---|---|---|
| `repository-list.tsx` L172-174 | topics `<li>` | `className="bg-muted text-muted-foreground rounded-full px-2 py-0.5 text-xs min-w-0"` | **必須**（GitHub topic は空白なし単一トークンで最大 50 文字、実害あり） |
| `repository-list.tsx` L159 | primaryLanguage `<span>` | `min-w-0` 追加 | 任意（統制語彙で実害ほぼ無いが無コストの保険） |
| `daily-digest.tsx` L129-137 | 各 `<span>`（dependentCount / star） | 変更なし | 不要（自前フォーマットの数値、第三者テキストでない） |

### 3. `fullName` の `<Link>`（`repository-list.tsx` L134-142）は継承だけで確実に折り返る — 追加対応不要

根拠は 2 点重なる:

1. **この `<a>` はそもそも flex アイテムではない**。親 `<div className="min-w-0 flex-1 break-words">`（L126）は `display: flex` を持たない（このコンポーネントで `flex` は `<li>` 自身と、内部の meta `<p>`/topics `<ul>` にしか付いていない）。したがって `<a>` は通常のブロック内インライン要素として、div の確定済み content width（＝ L126 の `min-w-0` により既に floor が外れて縮んでいる）の中でレイアウトされるだけで、automatic-minimum-size の対象にすらならない。
2. CSS 2.1 §10.3.1 は **`min-width` / `max-width` は非置換インライン要素には適用されない** と規定している。`<a>` はテキストのみを含む非置換インライン要素なので、そもそも「floor を持つ／持たない」という争点自体が発生しない。

以上 2 点により、`<div>` の `break-words` を継承した時点で `<a>` 内のテキストは div の確定幅に合わせて最終手段改行される。**`min-w-0` も `anywhere` も `<a>` には不要**——round1 の結論を維持する。

### 追加確認: `scope_docs` が挙げた `gem-list.tsx`（round1 で私は未読、今回読んだ）

`gem-list.tsx` L210 `<li className="relative py-4">` は `<ul>`（L206 `className="divide-border mt-2 divide-y"`。flex なし）の **子ではあるが、その `<ul>` 自体が flex コンテナではない** ため、`<li>` は plain block（automatic-minimum-size の対象外）。よって:

- L210 `<li className="relative py-4">` → `break-words` を **この `<li>` に 1 回** 追加すれば、配下の L229-235 `<Link>`／L237 フォールバック `<span>`／L239 の `<p className="flex flex-wrap ...">` 内の全 `<span>` まで継承で一括カバーできる（`repository-list.tsx` と同型パターン。ここは flex アイテムではないので `min-w-0` は不要——上の `<a>` の議論と同じ理由）。
- ただし L239 `<p className="... flex flex-wrap gap-x-4 gap-y-1 ...">` 配下の **L240 `packageName` の `<span>`** は、その `<p>` の flex アイテムであり、`packageName`（npm/pip 等のパッケージ名）は topics 同様 **第三者・可変長・ハイフンなしもあり得る文字列** なので、topics と同じ実害がある。→ **L240 `<span>` にも `min-w-0` が必須**。L242 `registry` の `<span>`（"npm"/"pypi" 等の統制小語彙）は任意（低優先）。

post します。

### `a11y_reflow` — 反論
<sub>2026-08-23T13:36:31+09:00</sub>

# a11y_reflow round2: 名指し 3 問への回答

## Q1（`css_wrap` との対立）: 決着 — **要素ごとに判定が割れる。`break-words` だけでは不足する箇所が 1 つある**

一次情報で裏取り済み（MDN `overflow-wrap`、逐語）:

> `anywhere`: "Soft wrap opportunities introduced by the word break **are** considered when calculating min-content intrinsic sizes."
> `break-word`: "soft wrap opportunities introduced by the word break are **NOT** considered when calculating min-content intrinsic sizes."

この 1 文が争点 A の核心で、`css_wrap` の主張の射程を分ける。

### `css_wrap` が正しい箇所（同意する）
`repository-list.tsx` L156 の description `<p>` と L141 の fullName `Link` は、**それ自身が flex アイテムではない**（親 `<div className="min-w-0 flex-1">` L126 が flex アイテムで、`<p>`/`Link` はその中の通常のブロック/インライン子）。この `<div>` は既に `min-w-0` で自動最小サイズ問題を解いており、`<p>` の幅は「自身の min-content」ではなく「親の確定済み幅」で決まる。したがって `break-word` の「min-content には効かない」という弱点はここでは無関係——確定幅の行内に収まらない語を最終手段で割れれば十分。**`css_wrap` の L126/L138 の結論（`break-words` を div に 1 個）に同意する。**

### `css_wrap` が見落としている箇所（反証）
`repository-list.tsx` L170-179 の topics `<ul className="mt-2 flex flex-wrap gap-1">` の子 `<li>`（L172-177）は事情が違う。この `<li>` **自身が** `ul.flex.flex-wrap` の flex アイテムであり、`min-w-0` は付いていない。GitHub の topic 文字列はハイフンを含まない単一トークンになり得る第三者由来の文字列で、改行機会（空白・ハイフン）がゼロの語が来ると、`<li>` の自動最小サイズ＝その語の min-content 幅になる。ここで:
- 継承された `overflow-wrap: break-word`（`div` からの継承）は **min-content を縮めない**（上記引用のとおり）。したがって `<li>` の自動最小サイズは変わらず、その語が行の残り幅より広ければ `<li>` はその行に収まらず、次の行へ送っても（`flex-wrap: wrap` の性質上）単独行でもなお `<ul>`/カード幅を超えて視覚オーバーフローする——**`break-words` の継承だけではこの `<li>` の溢れを閉じられない**。
- `overflow-wrap: anywhere` を **この `<li>` に直接** 当てれば、min-content 自体が改行機会込みで縮むため、flex-wrap のアルゴリズムが正しく縮小・折返しできる。

### 裁定
「どちらか一方が正しい」ではなく **両方採用**（css_wrap の判定を上書きしない・追加する）:
- `src/ui/repository-list.tsx` L126: `<div className="min-w-0 flex-1">` → `break-words` 追加（`css_wrap` 案のまま）
- `src/ui/repository-list.tsx` L172-175: `<li className="bg-muted text-muted-foreground rounded-full px-2 py-0.5 text-xs">` → **`wrap-anywhere` を直接追加**（継承に頼らない。ここだけ min-content 計算に効く値が要る）
- `daily-digest.tsx` / `gem-list.tsx` は `scope_docs` の洗い出し（topics 相当の flex-wrap リストが無い）を信じる限りこの追加パターンの対象外——ただし `scope_docs` に「flex-wrap の子要素で min-w-0 が無い箇所」を横断確認するよう申し送る。

**「意図しない箇所でレイアウトが痩せる」副作用について**: `wrap-anywhere` を当てるのは topics の `<li>` 1 箇所（独立した `ul.flex.flex-wrap` の中）に限定するため、L113 の avatar/本文 flex 行の幅配分（`w-6 shrink-0` 等）には一切波及しない——影響範囲は topic pill 自身の中だけ。CSS 実装は個別要素粒度で決まる（`css_wrap` の「継承で一括」という設計方針自体は正しいが、継承だけで全箇所が閉じるという結論は誤り）。

## Q2（`overflow-x:hidden/clip` の採否）: **不採用（二択で断定）**

round1 の「多層防御として条件付き許容」を撤回する。理由は a11y の情報欠落リスクだけでなく、**`test_guard` が設計した回帰テストそのものを無効化する** という決定的な技術的事実に気づいたため（round1 では見落としていた）。

`body { overflow-x: hidden }`（または `clip`）を指定すると、`<body>` 自身がその軸のスクロールコンテナになり、子孫のインク オーバーフローは `<body>` の外（`<html>`/viewport）へ伝播しなくなる（CSS Overflow の「body の overflow が viewport へ伝播する」規則は、body 自身が `overflow` を明示指定した時点で適用対象外になる——これは "body 全体に横スクロールバーを出さない" ための定番ハックとして広く知られる挙動）。結果として `document.scrollingElement`（＝ `documentElement`）の `scrollWidth` は `clientWidth` に収まり、**`test_guard` が設計した `expectNoHorizontalScroll`（`document.scrollingElement.scrollWidth <= clientWidth + 1`）は、実際にはコンテンツが `<body>` 内でクリップ／見えなくなっていても green になる**。

つまり「根本修正 + 最終防御としての hidden」を同じ PR に入れると、その PR が同時に追加する退行検知テスト（争点 D）の検出力をゼロにする——将来誰かが第三者テキストの折り返し指定を書き忘れても、E2E は永久に検知できなくなる。これは「症状を隠す」どころか「回帰テストの目を潰す」ため、band-aid の中でも最悪の選択肢。

→ **本 PR では `overflow-x:hidden`/`clip` を `body`/`html` に一切追加しない（断定）**。将来 sticky ヘッダー等の副作用（round1 で述べた）を持ち出すまでもなく、この 1 点だけで不採用が確定する。

## Q3（viewport 選定）: **320px 単独で a11y 要件上も必要十分（`test_guard` に同意・補強）**

- 320 CSS px は WCAG 2.2 SC 1.4.10 の達成基準文言に **名指しで明記された数値**（「1280px 幅 ×400% ズームと等価」）であり、375/430 は業界的に一般的なデバイス幅ではあるが基準文言上の閾値ではない。a11y 適合判定の基準点は 320px 以外にない。
- `test_guard` の単調性の主張（固定長の改行不能文字列に対し、必要幅は viewport 幅に依存せず一定 → 狭いほど厳しい判定になる）は、本プロジェクトの `ui-ux-guidelines.md` §3「固定幅を使わない。`min-width` + padding + Flex/Grid で可変にする」という制約があって初めて成立する。もし仮にどこかで固定 px 幅のブレークポイントが使われていて、広い viewport でカードの利用可能幅がかえって狭くなるような実装があれば単調性は崩れるが、`repository-list.tsx` にはそのような固定幅指定は無い（`min-w-0 flex-1` のみ）ため前提は成立している。
- したがって a11y レンズからも **320px 単独で十分**、375/430 を病的データ用に追加する意味はない（費用対効果が悪いだけでなく、320 を通過すれば論理的に導ける結果を重ねて検証するだけ）。既存の 375px・640×360px（200% 拡大相当）の通常データ用テストはそのまま残してよい（別の関心事）。

以上、post します。

### `test_guard` — 反論
<sub>2026-08-23T13:39:07+09:00</sub>

# test_guard round2: lead 名指し 4 点への回答

## 1（css_wrap vs a11y_reflow: break-word で `<li>`/`<span>` 自体が溢れないか）
**concede**: round1 の私のテストは検出できない。理由を実コードで裏取りした。

`repository-list.tsx:158` の `<p className="... flex flex-wrap ...">` と `:170` の
`<ul className="mt-2 flex flex-wrap gap-1">` は、L126 の外側 `<div className="min-w-0 flex-1">`
とは **別の flex コンテナ**。その子（primaryLanguage の `<span>`・topics の `<li>`, L173-176）は
**この内側コンテナ自身の flex アイテム** であり、`min-w-0` を個別に持たない。

css_wrap が指摘した「`overflow-wrap: break-word` は min-content 寄与を変えない」という事実は、
外側 div では `min-w-0` によって別解決済みだが、**この内側の `<li>`/`<span>` には min-w-0 も
overflow!=visible も無い**ため、automatic minimum size（flexbug #1）がそのまま残る。継承された
`break-words` は「箱の中でテキストをどう折り返すか」しか変えず、「箱自体（`<li>`）がどこまで
縮んでよいか」には無関係——つまり**空白もハイフンも持たない 1 個の topic 文字列が来ると、
`<li>` 自体がその文字列の全幅を要求し、flex-wrap で行送りされても行内で親幅を超えて溢れる**。
これは description の `<p>`（通常のブロック子で、独自の flex コンテナではない）とは構造が違う
ため、round1 の「長い URL 入り description」データでは踏めない経路。

**round1 の gap を埋めるスタブ変更**（`overflow-guard` マーカーの既存 1 件に追記。新マーカーは
不要）:

```js
topics: ['x'.repeat(48)], // 空白・ハイフン無しの単一トークン（GitHub 側の文字数上限は
                           // アプリが信頼してよい保証ではない——brief 自身が『長さも内容も
                           // 制御できない』と定義しているため、上限値の当否は問わず作る）
```

`toSearchItem`（`server.mjs:534-564`）は `topics` を素通しするので追加フィールドだけで足りる。
`repository-list.tsx:169` は `item.topics.length > 0` のときだけ `<ul>` を描画するため、この
1 行追加で `<li>` 経路が確実に踏まれる。

この 1 行を足すと、私の `expectNoHorizontalScroll` は **css_wrap 案（外側 div へ break-words
1 箇所）だけでは Red のまま**になる（`<li>` は inherited break-words では救えないため）。
Green にするには **`<li>`（L173-176）と `<span>`（primaryLanguage, L159 内）にも min-w-0
相当の対策**（`min-w-0` 追加、または `overflow-wrap: anywhere` — anywhere は min-content
そのものを縮めるため min-w-0 が無くても効く、と css_wrap が round1 で述べた通り）が要る。
**この 1 テストが争点 A（break-word か anywhere か）の実地裁定者になる**: 外側 div は
break-word で足りるが、`<li>`/`<span>` のような「自身が flex アイテムで min-w-0 を持たない
子」には anywhere（または個別 min-w-0 追加）が要る、という **要素ごとに手段が変わる可能性** を
テストが機械的に炙り出す。

## 2（daily-digest / gems ページは誰が守るか）
**断定: E2E では守らない。理由を明示する。**

- `daily-digest.tsx` のデータ源は `public/data/daily-digest.json`（`static-gem-digest.ts:5`
  で `import` されるバンドル取り込み）。`gem-list.tsx` のデータ源は `public/data/gem-index/`
  （シャード分割・`static-gem-index.ts`。`e2e/stub/server.mjs:329` 付近のコメントと一致）。
  どちらも **HTTP スタブ（`server.mjs`）を経由しない**、Next サーバープロセスが直接ファイル
  システムから読む実データ。E2E の `webServer` は `npm run build && npm start`（
  `playwright.config.ts:50`）で本物のファイルをそのままバンドルするため、`server.mjs` のような
  マーカー分岐を差し込む注入点が無い。
- 唯一の差し替え口は `StaticGemDigest` のコンストラクタ引数（`static-gem-digest.ts:69`
  「テスト用にソースを注入」）だが、これは **vitest（unit）専用** の DI で、E2E（実ブラウザ→
  ビルド済みアプリ）には届かない。
- 実データファイルを直接書き換えて注入する案は却下する: `daily-digest.json`（294 件・
  `sp-14.spec.ts:31` コメント）と `gem-index` シャード（`kafka` 33 件等、`sp-19.spec.ts` 冒頭
  JSDoc）は `sp-14` / `sp-15` / `sp-18` / `sp-19` が **実データの統計的性質**（重複排除・
  シャッフルの分散・実件数）に依拠しており、しかも `tools/generate_gem_digest.mjs` の定期再生成
  で上書きされる（恒久的な仕込みにならない・`server.mjs:319` の既存コメント「プール側の
  リポジトリ名をハードコードしない」と同じ理由）。
- したがって **E2E での退行検知は repository-list（一覧・検索結果）と repository-detail に
  限定する**（実バグの再現経路そのもの）。

**それでも「守らない」で終わらせない代替策（次善のセーフティネット）**:
- css_wrap には **争点 B の適用範囲に `daily-digest.tsx` と `gem-list.tsx` を明示的に含める**
  ことを要求する（scope_docs の 4 ファイル 10 箇所指摘どおり。css_wrap round1 は
  `daily-digest.tsx` は直したが **`gem-list.tsx` に触れていない** — これは取りこぼし）。
- E2E が届かないこの 2 ファイルに限り、`daily-digest.test.tsx` / `gem-list.tsx` 用の新規 vitest
  に「E2E で実証済みのクラス（`min-w-0 flex-1 break-words` 等、必要なら `<li>`/`<span>` 側の
  対策も含む）が同じ箇所に当たっているか」を確認する **横展開漏れ検知** を追加する。§5 で述べた
  「className 検証は横スクロールの発生自体を証明しない」という限界は変わらないが、ここでの
  役割は「同じ構造バグを 4 箇所目・5 箇所目で再導入していないか」の確認に限定するため、
  「実装の写経で価値が薄い」という批判は repository-list には当たるがここでは当たらない
  （repository-list は E2E で実証済み・ここは E2E が構造的に届かない代替経路）。
- 恒久対応: `E2E_STUB_PORT` と同じ発想で `daily-digest.json` / `gem-index` の読み込みパスを
  環境変数で差し替え可能にする改修は価値があるが、本争点のスコープ外（CP-1: 起票はするが
  本スプリントのコード変更には含めない・YAGNI）。実装 Issue として起票することを提案する。

## 3（viewport 320px 単独の再判定）
再判定した上で **320px 単独を維持する**。

根拠（単調性の精査）: 本件の破綻条件は「分割不可能なトークンの必要幅 > コンテナ幅」。
トークンの必要幅は viewport 幅に依存せず一定なので、コンテナ幅が広いほど破綻しにくい
（狭いほど厳しい）。`repository-list.tsx` / `repository-detail.tsx` に `sm:`/`md:`/`lg:` 系の
レスポンシブ prefix が無いか実際に grep して確認した結果、唯一の例外は
`repository-detail.tsx:111` の `<dl className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">`
（stats グリッドが 640px で 2 列→4 列に変わる）。ここは **description・topics とは無関係な
別要素**なので、単調性の前提（同一構造のまま幅だけ変わる）を崩さない。したがって
「320px で fail しない」ことを確認すれば、375px・430px・640px でも同じデータに対して
fail しないことが論理的に導ける——320px 単独で十分（追加 viewport は冗長）。

なお 1.4.4（200% 拡大・sp-10 の 640×360 テスト）は **別の懸念**（通常データでのレイアウト
崩れ）を見ており、本退行クラスとは無関係。既存のまま維持すればよく、`overflow-guard` 用に
640 を増設する必要はない。

## 4（既存 E2E への影響のより厳密な検証）

**マーカー衝突なしの再確認**（`server.mjs` の分岐一覧を実際に洗った）:
`SP9_NETWORK_DOWN_MARKER='sp9-network-down'`(l.106) / `SP9_SECONDARY_RATE_LIMIT_MARKER`(l.107)
/ `SP9_SLOW_MARKER`(l.108) / `SP9_FORBIDDEN_MARKER`(l.113) / `'zero-hits'`(l.661) /
`'upstream-error'`(l.664) / `'rate-limit'`(l.667) / `PRIVATE_MIXED_MARKER='private-mixed'`(l.122)
/ `GEM_BADGE_MARKER='gem-badge'`(l.326) / `MANY_HITS_MARKER='many-hits'`(l.71) /
`'not-found'`(l.749 detail 側)。`overflow-guard` はこのいずれの部分文字列でもなく、
いずれも `overflow-guard` の部分文字列でもない（10 個全部を文字列比較で確認済み）。

**件数・totalCount への非干渉**: 新マーカーの分岐は `PRIVATE_MIXED_MARKER`（l.672-678）や
`GEM_BADGE_MARKER`（l.682-688）と同じ形で `{ total_count: 自分の配列.length, ... }` を
**独自に返す**（グローバル `TOTAL_COUNT` 定数 l.64 や `searchResponse()` ヘルパー l.566 を
使わない）。既定フィクスチャ（`react` 等）の分岐（l.707 のフォールバック）は if-chain を
一切通過しないため無傷。

**stats（`/__stats`）への影響**: `stats.searchCount += 1`（l.625）・`stats.detailCount += 1`
（l.743）はマーカー判定より **前** で無条件に走るため、`overflow-guard` の検索・詳細アクセスも
カウントされる。ただし `sp-5.spec.ts` は測定直前に必ず `resetStubStats()`（l.72-76、呼び出しは
`beforeEach` 相当 l.85 と l.141）で `stats` をゼロに戻してから比較しており、
`playwright.config.ts:19-21`（`fullyParallel: false` / `workers: 1`）で全 spec が直列実行される
ため、他ファイルの実行順に関わらず sp-5 は自分のリセット後の増分だけを見る。**干渉なし**。

**axe（`a11y.spec.ts`）への影響**: 全 6 テスト（l.17-90 実測）は `'react'` 検索
（`octo-widgets` 固定フィクスチャ）・`octo-readme-rich`・`/ja` 未検索・404 の **固定ページのみ**
を対象にしており、任意クエリをクロールする処理は無い。新マーカーへ axe が触れる経路が
そもそも存在しないため、**新規違反が出ようがない**（`a11y.spec.ts` 側のテストは無傷）。
逆に言うと **`overflow-guard.spec.ts` 自体には axe 検査が無い**——望むなら
`createAxeBuilder(page).analyze()`（`e2e/axe.ts`）を追加できるが、これは Q4 の「壊さないか」
への回答としては不要（既存スイートは無関係で無傷、が新規スイートへの axe 追加自体は
別途のプラス提案として css_wrap/a11y_reflow に投げる）。

以上、post します。

## ラウンド 3

### `lead` — 合意
<sub>2026-08-23T13:41:06+09:00</sub>

# lead 合意整理（round 3）

## 合意された事実（4 レンズが round 2 で一致した点）

1. **根本原因**: 第三者由来テキスト（GitHub の `description` に含まれる空白なしの長い URL 等）に折り返し指定が無く、`overflow-wrap` の既定 `normal` では改行機会が無い語を割れないため、カードからはみ出して `body` に横スクロールが伝播する。`ui-ux-guidelines.md` §2 の「横溢れは領域内スクロールに閉じ込め body に出さない（`NFR-15`）」と WCAG 2.2 SC 1.4.10 Reflow（320 CSS px 相当で二方向スクロールを強制しない）に違反している。

2. **`overflow-wrap: break-word` と `anywhere` の差は min-content 寄与だけ**（MDN / CSS Text 3 の逐語で裏取り済み）。`break-word` は min-content を縮めず、`anywhere` は縮める。**定幅が確定したボックスの中での折り返し位置は両者で差が出ない。**

3. **したがって要素の性質で必要な値が変わる**（css_wrap の round1「継承 1 回で全部片付く」は本人が一部撤回、a11y_reflow の round1「全面 `anywhere`」も撤回）:
   - **flex アイテムでない要素**（`min-w-0` 済みコンテナ配下の `<p>` / 非置換インライン `<a>`・`<span>`）→ 親の確定幅に従うので、継承された `break-word` で足りる。`<a>` は CSS 2.1 §10.3.1 により `min-width` が適用対象外なので floor 問題自体が起きない。
   - **それ自身が flex アイテムの要素**（`ul.flex.flex-wrap` 直下の topics `<li>`、`p.flex.flex-wrap` 直下の `<span>`）→ automatic minimum size（自身の min-content）が floor として残るため、継承された `break-word` **だけでは閉じない**。GitHub の topic は空白・ハイフンなしの単一トークンで最大 50 文字あり得るので実害がある。

4. **`overflow-x: hidden` / `clip` を `body`/`html` に足すのは不採用**（a11y_reflow が round1 の条件付き許容を撤回し断定・全員が受諾）。情報欠落（1.4.10）だけでなく、**`body` が `overflow` を明示した時点で viewport への伝播が止まり、本 PR が同時に追加する退行検知テスト（`document.scrollingElement.scrollWidth <= clientWidth`）の検出力を永久にゼロにする** ため。band-aid の中でも最悪の選択肢。

5. **E2E の viewport は 320px 単独で必要十分**（test_guard の単調性論 + a11y_reflow の「320 は SC 1.4.10 の基準文言に名指しされた唯一の閾値」で一致）。375 / 430 を病的データ用に足す価値はない。

6. **既存 E2E が今回を検知できなかった理由**: `e2e/stub/server.mjs` の既定データは最長 39 字・空白入りで、改行機会ゼロの連続長文字列が 1 つも無い。`e2e/sp-10.spec.ts` の `expectNoHorizontalScroll` という述語は正しかったが、**食わせるデータが健全すぎた**。

7. **適用漏れ**: css_wrap の round1 案は 3 ファイルだったが、scope_docs の機械洗い出しで `src/ui/gem-list.tsx`（4 箇所 + 検索語を埋め込む見出し 1 箇所）が抜けていた。`gem-list.tsx` の `<ul>` は flex ではないため `<li>` は plain block で、`min-w-0` 不要・`break-words` 1 回で配下を継承カバーできる。ただし `p.flex.flex-wrap` 直下の `packageName` の `<span>` は flex アイテムなので上記 3 と同じ扱いが要る。

8. **ドキュメントの追記先は §3「レイアウトと i18n 耐性」**（§2.5 は README typography 限定・scope_docs が自らの round1 を訂正）。

## 残った唯一の対立と lead 裁定

**topics `<li>` 等「flex アイテムかつ第三者テキスト」への対処** を、css_wrap は `min-w-0` 追加、a11y_reflow は `wrap-anywhere` 直付けとした。両者とも技術的には成立する（floor を外すか、min-content を縮めるかの違いで、結果の折り返しは同じ）。

**lead 裁定: `wrap-anywhere` を採る（a11y_reflow 案）。**

理由は「サイト全体で折り返しルールを 1 種類に統一したい」（css_wrap）よりも **結合の弱さ** を優先したため:

- `min-w-0` 案が成立する前提は「祖先の `break-words` が継承されてくること」。将来この `break-words` を誰かが外す・要素を別の親へ移すと、`min-w-0` だけが残って **静かに折り返さなくなる**（`min-w-0` 単独では折り返し指定が無いので、floor が外れた分かえって溢れる）。
- `wrap-anywhere` は **その要素だけで自己完結** する（min-content の縮小と折り返し機会の導入を 1 つの宣言が両方担う）。祖先の状態に依存しない。
- 副作用は topic pill / package 名の内側に閉じ、`w-6 shrink-0` 等の兄弟との幅配分には波及しない（a11y_reflow の指摘どおり）。

「値が 2 種類になる理由が将来の読者に分からない」という css_wrap の懸念は、**コード側のコメントと `ui-ux-guidelines.md` §3 の追記で判定規則（flex アイテムか否か）を明文化する** ことで解消する。

### `lead` — 判定
<sub>2026-08-23T13:42:04+09:00</sub>

{
  "decisions": [
    {
      "issue": "A: 折り返しの実装手段",
      "design": "要素の性質で 2 値を使い分ける。(1) flex アイテムでない要素（min-w-0 済みコンテナ配下のブロック・非置換インライン）は祖先コンテナへ `break-words`（overflow-wrap: break-word）を 1 回当てて継承でカバーする。(2) それ自身が flex アイテムで、かつ長さを制御できない第三者テキストを載せる要素には `wrap-anywhere`（overflow-wrap: anywhere）を直付けする（automatic minimum size の floor を min-content ごと縮めるため、祖先の状態に依存せず自己完結する）。判定規則は『その要素自身が flex コンテナの直接の子か？』の一点。",
      "artifacts": [
        "src/ui/repository-list.tsx（改修）: L126 `<div className=\"min-w-0 flex-1\">` に `break-words` を追加 / topics の `<li>`（L172 付近）に `wrap-anywhere` を追加",
        "src/ui/daily-digest.tsx（改修）: L115 `<div className=\"min-w-0 flex-1\">` に `break-words` を追加",
        "src/ui/repository-detail.tsx（改修）: description の `<p>`（L108 付近）に `break-words` を追加",
        "src/ui/gem-list.tsx（改修）: `<li className=\"relative py-4\">` に `break-words` を追加 / `p.flex.flex-wrap` 直下の packageName `<span>` に `wrap-anywhere` を追加 / 検索語を埋め込む見出しに `break-words` を追加"
      ],
      "rejected": "全面 `break-word` 一本槍（css_wrap round1・本人が撤回）= flex アイテムの floor が残り topics `<li>` が閉じない。全面 `anywhere`（a11y_reflow round1・本人が撤回）= 不要な箇所まで min-content を縮める。`word-break: break-all`= 英単語を無意味に切り可読性を損なう。`hyphens`= URL に効かない。flex アイテムへの `min-w-0`（css_wrap round2）= 祖先の `break-words` 継承に依存する結合の強さゆえ却下（祖先の変更で静かに壊れる）。"
    },
    {
      "issue": "B: 適用範囲",
      "design": "第三者由来テキスト（GitHub / Ecosyste.ms 由来で長さも内容も制御できない文字列）とユーザー入力の再表示を描画する全箇所を対象にする。scope_docs の機械洗い出しに基づき 4 ファイル（repository-list / daily-digest / repository-detail / gem-list）。統制語彙（primaryLanguage の Linguist 語彙・registry 名）と自前 Intl 整形の数値・日付は対象外（YAGNI）。",
      "artifacts": [
        "上記 4 ファイル（改修）"
      ],
      "rejected": "repository-list.tsx の description だけを直す最小修正 = 同じ報告が topics・gem 一覧から再発する。primaryLanguage / registry / star 数 / 日付にも保険で当てる案 = 実害ゼロの箇所を触る YAGNI 違反。"
    },
    {
      "issue": "C: 個別要素 vs グローバル安全網",
      "design": "個別要素（+ コンテナからの継承）のみ。globals.css への @layer base 一括適用も、body/html への overflow-x:hidden/clip も採らない。",
      "artifacts": [],
      "rejected": "body/html への `overflow-x: hidden`/`clip` = ① WCAG 1.4.10 の『情報や機能を失わない』に反しうる ② position:sticky を壊す ③ 決定的な理由として、body が overflow を明示した時点で viewport への伝播が止まり、本 PR が同時に追加する退行検知テスト（document.scrollingElement.scrollWidth <= clientWidth）を永久に green にしてしまい検出力をゼロにする。globals.css の @layer base による一括適用 = 対象を『第三者テキストを載せる要素』に絞れず、意図しない折り返しを広範囲に生む。"
    },
    {
      "issue": "D: 退行検知テスト",
      "design": "E2E を主とする。専用スペック `e2e/overflow-guard.spec.ts` を新設し、viewport 320px 単独で、スタブに新設する病的データセット（マーカー `overflow-guard`）を検索して一覧ページと詳細ページの双方で document.scrollingElement.scrollWidth <= clientWidth + 1 を検証する。病的データは 3 種すべてを含める: (a) 空白を一切含まない長い URL 入り description（本件の再現データ）(b) 空白・ハイフンなしの長い単一 topic（flex アイテム floor の再現）(c) 長い full_name。E2E で注入口を持たない daily-digest / gem-list は、vitest のコンポーネントテストで折り返しクラスの存在を検証する（弱いが、この 2 つに対する唯一の回帰網）。TDD 順序: 先にスタブ拡張 + E2E を書いて Red を確認してから実装する。",
      "artifacts": [
        "e2e/stub/server.mjs（改修）: マーカー `overflow-guard` の病的データセットを追加",
        "e2e/overflow-guard.spec.ts（新規）: 320px viewport・一覧 + 詳細の横スクロール検証",
        "src/ui/daily-digest.test.tsx / src/ui/gem-list.test.tsx（改修 or 新規）: 折り返しクラスの存在検証"
      ],
      "rejected": "375 / 430px の追加 viewport = 320 を通れば論理的に導ける（改行不能文字列の必要幅は viewport 幅に依存せず一定・固定幅ブレークポイントが無いため単調）。playwright.config.ts へ狭い viewport のプロジェクトを追加 = 全スペックが二重実行されコストに見合わない。全コンポーネントへの className 写経テスト = jsdom はレイアウト計算を持たず実際の溢れを検証できないため、E2E で守れる箇所には価値がない。"
    },
    {
      "issue": "E: ドキュメント",
      "design": "ui-ux-guidelines.md §3「レイアウトと i18n 耐性」に規律を 1 項追記する。内容は『長さも内容も制御できない第三者由来テキスト（description・topic・fullName・packageName・ユーザー入力の再表示）を描画する要素には必ず折り返し指定を当てる。その要素自身が flex コンテナの直接の子なら `wrap-anywhere`、そうでなければ祖先コンテナの `break-words` の継承でよい』という判定規則。SSOT を増やさず既存節に足す。",
      "artifacts": [
        "docs/03_design/ui-ux/ui-ux-guidelines.md（改修・§3 に 1 項追記）"
      ],
      "rejected": "§2.5 への追記（scope_docs round1・本人が訂正）= §2 は README typography 限定の節。prd.md / user-story-map.md の改訂 = NFR-15 / AC-9 の要件文言自体は変わっておらず、違反していたのは実装なので要件側を触る必要はない。新規ルールファイルの作成 = SSOT を増やす。"
    }
  ],
  "tasks": [
    { "id": "T-1", "title": "e2e/stub/server.mjs に病的データセット（マーカー overflow-guard）を追加する", "actor": "claude", "depends_on": [], "sp": "sp:1" },
    { "id": "T-2", "title": "e2e/overflow-guard.spec.ts を新設し 320px で Red を確認する", "actor": "claude", "depends_on": ["T-1"], "sp": "sp:1" },
    { "id": "T-3", "title": "4 ファイルへ折り返しクラスを適用し Green にする", "actor": "claude", "depends_on": ["T-2"], "sp": "sp:2" },
    { "id": "T-4", "title": "daily-digest / gem-list の折り返しクラス検証を vitest に追加する", "actor": "claude", "depends_on": ["T-3"], "sp": "sp:1" },
    { "id": "T-5", "title": "ui-ux-guidelines.md §3 へ判定規則を追記する", "actor": "claude", "depends_on": ["T-3"], "sp": "sp:1" },
    { "id": "T-6", "title": "npm run check を通し、プレビュー URL 付きで PR を作成する", "actor": "claude", "depends_on": ["T-3", "T-4", "T-5"], "sp": "sp:1" }
  ],
  "critical": [
    "body/html への overflow-x:hidden/clip は、同 PR で追加する退行検知テストの検出力を恒久的にゼロにするため絶対に入れない（誤って入れるとテストは green のまま溢れが復活する）",
    "flex アイテムへの対処を祖先の break-words 継承に依存させると、将来祖先を触ったときに静かに壊れる（wrap-anywhere で自己完結させること）"
  ],
  "open_questions": []
}
