<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: 入力フォームの操作性（コントロール高さ・タッチターゲット・フォーム UX）を最新の一次情報で確定し実装指針に落とす

- 議題ID: `form-ux-sizing-20260819`
- 論点: 検索フォームの入力欄・ボタンが h-8(32px) で縦幅が小さく操作性が悪い。根本原因はガイドラインに主要コントロールの最小高さ基準が無く shadcn radix-nova の既定を素通ししたこと。争点 A(最小高さの数値と根拠) B(shadcn 既定の扱い方) C(検索フォーム UX) D(ガイドラインへの落とし方と機械検証) E(導入価値のある Claude Code 資産)。詳細は tools/discussion_specs/form_ux_sizing_spec.json
- 参加者: `mobile_touch`, `form_ux`, `design_system`, `a11y_wcag`, `tooling_scout`
- 投稿数: 5
- 更新: 2026-08-19T10:03:50+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

## ラウンド 1

### `mobile_touch` — 主張
<sub>2026-08-19T10:00:56+09:00</sub>

# mobile_touch レンズ: タッチ操作性・ターゲットサイズ（Round 1）

## 1. 一次情報の正確な要件（取得日: 2026-08-19 JST）

### WCAG 2.2 SC 2.5.8 Target Size (Minimum) — Level AA
> "The size of the target for pointer inputs is at least 24 by 24 CSS pixels" except で始まる5例外付き規定。
- 数値: **24×24 CSS px**、適合レベル **AA**（達成しないと AA 非適合）
- 5例外: **Spacing**（24px 径の円が隣接ターゲットと重ならない間隔があれば未達サイズでも可）/ **Equivalent**（同ページに要件を満たす代替コントロールがある）/ **Inline**（文中・行送りに制約されるリンク等）/ **User Agent Control**（`<input type=date>` のネイティブ UI 等、著者が変更していないブラウザ既定）/ **Essential**（地図ピン等、サイズ自体が情報）
出典: https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html（2026-08-19 JST 取得）

### WCAG 2.2 SC 2.5.5 Target Size (Enhanced) — Level AAA
> "The size of the target for pointer inputs is at least 44 by 44 CSS pixels except when..."
- 数値: **44×44 CSS px**、適合レベル **AAA**（本プロジェクトの目標適合レベルではないが「望ましい上位基準」として参照可）
- 4例外: Equivalent / Inline / User Agent Control / Essential（Spacing 例外は AAA 側にはない＝間隔での代替が効かない、より厳格）
出典: https://www.w3.org/WAI/WCAG22/Understanding/target-size-enhanced.html（2026-08-19 JST 取得）

### Apple HIG
- **44×44pt** が iOS の対話要素の最小推奨値。小さい対話要素は **タップエラー率 25%以上** に悪化するという知見が根拠として挙げられている。
出典: https://www.nadcab.com/blog/apple-human-interface-guidelines-explained ほか（2026-08-19 JST 取得・複数ソース collate）

### Material Design 3
- **48×48dp** が最小タッチターゲット（物理サイズ約 9mm、推奨レンジ 7–10mm）。**視覚サイズ（アイコン 24dp 等）とタッチ領域（48dp）は別概念**であり、透明パディングで拡張してよい。標準ボタンは **最小高さ 48dp + 水平パディング 16dp**。ターゲット間は 8dp 以上の間隔を推奨。
出典: https://m3.material.io/foundations/designing/structure（2026-08-19 JST 取得）

## 2.「ターゲットサイズ」と「コントロールの視覚的高さ」は別概念 — ただし本件には使えない

WCAG の要件は**ヒットエリア（クリック/タップ可能領域）**の話であり、**見た目の高さ**ではない。理論上は「視覚 32px + 見えないパディングで 44px のヒットエリア」でも 2.5.8/2.5.5 は満たせる。

しかし本件（検索フォームの主要 2 コントロール）にはこの回避策を **推奨しない**:
1. NN/g 等の知見（form_ux レンズと要突合）で、ユーザーは視覚サイズでタップ判断するため見た目と実際の当たり判定が乖離すると「押しにくそうに見える」印象自体は解消されない（心理的 Fitts's law の起点はポインタが移動する視覚的な的の大きさ）。
2. `search-form.tsx` は `flex gap-2` で入力欄とボタンが横並び・隣接しており、見えないパディングで拡張すると**互いのヒットエリアが重なる/意図しない誤タップの原因**になりうる（Spacing 例外の考え方と逆行）。
3. 今回の争点は「縦幅が小さく操作性が悪い」というユーザー **体感**報告であり、視覚的高さを変えない対処は根本原因に対応しない。

→ **視覚的な高さそのものを引き上げる**のが正しい対処。

## 3. Fitts の法則・タッチ精度研究

Fitts's law: 到達時間 ∝ log2(距離/ターゲット幅+1)。ターゲットが小さいほど到達・確定に時間がかかり、誤操作が増える。タッチは指先の物理的な接触面積（成人の指先パッド幅は概ね 8–10mm）とパララックス（視差）誤差が加わるため、**マウスのポインタ精度よりターゲットに対する要求が厳しい**。Apple の「25%以上のタップエラー率」（HIG 系情報源に集約）はこの物理制約を反映した経験則であり、24px（≈6.4mm@160dpi 相当ではなく CSS px なので機種依存だが一般に）は「法的最低ライン」、44px/48px は「実用ライン」という位置づけが一次情報間で一貫している。

## 4. 現状 32px（h-8）が悪化させる具体点

- `Input`（`h-8` = 32px）・`Button` size=default（`h-8` = 32px）はいずれも **WCAG 2.5.8 AA の 24px は形式的にクリア**（32>24、間隔例外に頼る必要すらない）。→ **法的な非適合ではない**。
- しかし **Apple HIG 44pt・Material 3 48dp のどちらの実用基準にも届かず**、AAA（44px）にも届かない。32px は 44px 比で **面積が約 53%**（32²/44²）しかなく、Fitts's law に基づけば到達時間・誤タップ率が有意に悪化する領域。
- `search-form.tsx` は `flex gap-2`（8px）で入力欄とボタンを隣接配置しており、コントロール自体が小さいうえ間隔も広くない → 誤タップの複合要因になりやすい。
- モバイル実機では「検索」ボタンが親指到達域の下部にない構成（フォームがページ上部にある想定・`app/page.tsx` 未確認だが `max-w-3xl px-4 py-10` から通常レイアウト）でも、ボタン自体が小さいと **意図した1回のタップで確定できない＝再タップ・スクロール補正の手間**が生じ、これが「操作性が良くない」という体感報告の主因と推定できる。

## 5. ポインタ入力とタッチ入力で基準を変えるべきか（`pointer: coarse`）

- `any-pointer: coarse` は「粗い入力デバイスが**存在するか**」を見るクエリで、タッチスクリーン搭載ノート PC 等のハイブリッド機では **`any-pointer: fine` と `any-pointer: coarse` が同時に真**になりうる（一次情報: MDN / josh coast のまとめ、出典 https://developer.mozilla.org/en-US/docs/Web/CSS/@media/pointer 、2026-08-19 JST 取得）。`pointer:`（`any-` なし）は**主入力**を見るため誤判定は少ないが、それでも「デスクトップ = マウスだから小さくてよい」という前提は崩れつつある（タッチ対応ノート PC・タブレット外付けキーボードの普及）。
- **本件（検索フォームの主要 2 コントロール）への推奨: `pointer: coarse` による出し分けをしない。** 理由: (a) 検索はアプリの中心 CTA であり、マウス利用時でも大きい方が Fitts's law 的に有利（デメリットがほぼない）。(b) 出し分けはコードの複雑性を増し、JS なしの GET フォーム（RSC）という制約下でも CSS だけで実装は可能だが、**検証コストに見合わない**（jsdom では実測できず、E2E でも `pointer` メディア特性のテストは実質困難）。(c) `tooling_scout` レンズとも関わるが、「常に十分な大きさ」の方が保守性が高い。
- **出し分けを使ってよい場面**（本件のスコープ外として明示）: データテーブルの行内アイコンボタン等、密度が UX 上の価値を持つ副次的コントロール。

## 6. 争点 A への具体的数値推奨

**検索入力（Input）・送信ボタン（Button）の両方を、ブレークポイント無条件で最小高さ 44px（Tailwind `h-11`）に引き上げる。**

- 根拠: Apple HIG 44pt と WCAG 2.5.5（AAA・エンハンス基準）が一致する数値であり、Material 3 の 48dp（`h-12`）より 4px 刻みグリッドに収まりが良く既存 `lg`（`h-9`=36px）からの連続性も保ちやすい。24px（AA 必須ライン）はあくまで**法的下限**であり実用基準として採用しない。
- 44px は既存の 4px グリッド（4/8/12/16/24/32...）に一致するため制約と衝突しない（`h-11` = 44px は Tailwind 標準トークン）。
- 48px（Material 3 準拠・`h-12`）を採るなら**さらに安全**だが、`lg` バリアント（36px）との差が開きすぎるため、まずは 44px を下限として提案し、`design_system` レンズの size バリアント設計と合わせて最終判断すべき。
- ボタン・入力の**視覚的高さ**として 44px を確保すること（見えないパディングでの誤魔化しは 5 節の理由で不可）。
- `gap-2`（8px）の隣接間隔は Material 3 推奨（8dp 以上）を満たすため維持でよいが、コントロール自体が 44px 化されれば誤タップリスクはさらに下がる。

## Sources
- https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html
- https://www.w3.org/WAI/WCAG22/Understanding/target-size-enhanced.html
- https://m3.material.io/foundations/designing/structure
- https://developer.mozilla.org/en-US/docs/Web/CSS/@media/pointer
- https://www.nadcab.com/blog/apple-human-interface-guidelines-explained

### `form_ux` — 主張
<sub>2026-08-19T10:01:07+09:00</sub>

## 争点C: 検索フォームの UX 設計（JS なし GET フォーム前提）

### 1. ラベル可視化 — sr-only をやめ、可視ラベルへ

NN/g の「検索ボックスにラベルは不要」という古典的ガイダンスは、**ヘッダー常設のミニ検索**（アイコン + テキスト欄 + 「Search」ボタンの組み合わせで文脈から自明な場合）を前提にしている（[NN/g: Search: Visible and Simple](https://www.nngroup.com/articles/search-visible-and-simple/)、取得日 2026-08-19 JST）。一方 gem-hunter の検索欄は **ページの主コンテンツそのもの**（h1 直下・唯一のフォーム）であり、この前提が当てはまらない。

GOV.UK Design System は原則として可視ラベルを要求している: *"All text inputs must have labels, and in most cases the label should be visible."*（[GOV.UK: Text input](https://design-system.service.gov.uk/components/text-input/)、取得日 2026-08-19 JST）。USWDS の search コンポーネントは sr-only ラベルを既定にしているが、これは汎用ヘッダー検索を想定した実装であり（[USWDS: Search](https://designsystem.digital.gov/components/search/)、取得日 2026-08-19 JST）、本アプリの「検索が全て」という構成には設計意図が異なる。

さらに NN/g の代表的知見として、**プレースホルダをラベルの代替にすることの弊害**が確立している: 長い入力中にヒントを忘れる・視覚/認知障害者に負担・値を入れると消える（[NN/g: Placeholders in Form Fields Are Harmful](https://www.nngroup.com/articles/form-design-placeholders/)、取得日 2026-08-19 JST）。現状の実装はまさに「ラベルは sr-only、視覚的にはプレースホルダのみが手がかり」というアンチパターンに該当する。2026 時点の潮流調査でも「Never use placeholders as labels」「Labels stay visible」が繰り返し明記されている（[SpecificIT: Trends in Form Design for 2026](https://specificit.com.au/trends-in-form-design-2026/)、取得日 2026-08-19 JST）。

**提案**: `sr-only` を外し、入力欄の直上に 14px（既存タイポスケール内）の可視ラベル「検索キーワード」を配置する。プレースホルダは「例: react」程度の**補助的な例示**に格下げし、ラベルの代替にしない。

### 2. 送信ボタンの文言・アイコン

NN/g のアイコン単体化への警鐘（[NN/g: The Magnifying-Glass Icon in Search Design](https://www.nngroup.com/articles/magnifying-glass-icon/)、取得日 2026-08-19 JST）を踏まえ、**テキストボタン「検索」を維持**する。アイコンを足す場合もテキストと併記（アイコン単体化は不可）。`white-space: nowrap` 禁止（`NFR-15`）と矛盾しないよう、アイコンを追加するなら `inline-flex items-center gap-1.5` とし、折返しを許容する実装にする。

### 3. モバイルでの縦積み判断

USWDS は検索入力の最小幅を「27 文字分」としている（[USWDS: Search](https://designsystem.digital.gov/components/search/)、取得日 2026-08-19 JST）。これと 44px 級のボタン（争点A・mobile_touch 担当）を横並びで確保するには少なくとも `sm`（Tailwind 既定 640px）程度の幅が要る。既存コンテナが `max-w-3xl`（768px 相当）でモバイル時は画面幅そのものになるため、**640px 未満は縦積み、640px 以上で横並び**に切り替える。2026 年の潮流調査も「モバイルはシングルカラム・大きめの入力欄」を一貫して推奨している（[SpecificIT](https://specificit.com.au/trends-in-form-design-2026/)、取得日 2026-08-19 JST）。

### 4. 具体実装案（マークアップ・クラス）

```tsx
export function SearchForm({ keyword }: { keyword: string }) {
  return (
    <form
      action="/"
      method="get"
      role="search"
      className="flex flex-col gap-2 sm:flex-row sm:items-end"
    >
      <div className="flex-1">
        <label htmlFor="q" className="mb-1 block text-sm font-medium text-foreground">
          検索キーワード
        </label>
        <Input
          id="q"
          name="q"
          type="search"
          defaultValue={keyword}
          placeholder="例: react"
          className="h-11 text-base"
        />
      </div>
      <Button type="submit" className="h-11 w-full px-6 sm:w-auto">
        検索
      </Button>
    </form>
  )
}
```

- `h-11`（44px・4px グリッドに整合）は mobile_touch/a11y_wcag の結論と揃える前提。争点A の最終値がこれと異なる場合はここも追随させる。
- ラベルを div でラップして input と縦積みにし、button 側は `sm:items-end` で入力欄のベースラインに揃える。
- `w-full sm:w-auto` でモバイル時のボタンをフル幅化し、タップ領域を最大化する（縦積み時の操作性向上）。
- `type="search"` は維持（JS 不要でブラウザネイティブのクリア × ボタンが有効な環境がある）。
- Enter 送信はネイティブ GET フォームで既に機能するため追加実装不要。

### 5. 空状態・件数表示（現状追認）

`app/page.tsx` の「N 件中 M 件を表示」は MOJ Design System 系の一般的パターンと一致しており、`docs/03_design/ui-ux/ui-ux-guidelines.md` §4.5 に既に明記済み。**変更提案なし**。

### 6. 争点B との接続（設計提案）

`h-11`/`px-6` をフォーム側 className で上書きする方式は、既定を書き換える (i) や className 個別上書き (iii) のどちらでも実現可能。**design_system レンズの結論を優先**し、フォーム側は決定されたトークン/バリアントを呼び出すだけにする（本提案の `h-11` はプレースホルダ値であり、争点B の決定値に置き換える）。

### `tooling_scout` — 主張
<sub>2026-08-19T10:02:32+09:00</sub>

## 結論（3 分類）

**今すぐ導入（2 件）**
1. `@playwright/test` + `@axe-core/playwright`（devDependencies 追加・E2E テストとして CI 実行）
2. `docs/03_design/ui-ux/ui-ux-guidelines.md` §9 が既に前提としている **Lighthouse CI を実際に GitHub Actions へ配線**（`treosh/lighthouse-ci-action`）— ガイドラインが参照する検証手段が実在しない状態を解消する

**条件付きで後日（2 件）**
3. shadcn 公式 MCP サーバー（コンポーネント追加が頻発する局面のみ）
4. Chrome DevTools MCP（インタラクティブなパフォーマンス調査が必要になった時のみ）

**採らない（2 件）**
5. `frontend-design` 公式 plugin（本プロジェクトの制約と方向性が逆）
6. Storybook + a11y addon（アプリ規模に対して過剰）

---

## 争点D（機械検証手段）への回答: jsdom の限界を Playwright で埋める

`docs/03_design/ui-ux/ui-ux-guidelines.md` §9 は既に「レイアウトシフトの有無は目視で判定せず、Lighthouse CI の CLS 実測値で判定する」と書いているが、`.github/workflows/` に Lighthouse 系ワークフローは存在せず（確認済み・`ls .github/workflows` = `deploy-preview.yml` / `deploy-production.yml` のみ）、**ガイドラインが前提とする検証手段が実装されていない**。これは今回の争点 A（コントロール最小高さ）にも直結する: 高さの基準を文書化しても、それを壊す変更を機械的に止める手段がなければ SP-1 の事故（h-8 素通し）が再発する。

`vitest`（devDependencies に既存）は `jsdom` 環境（`jsdom: ^30.0.1` も devDependencies に既存）で動く。jsdom は CSS レイアウトエンジンを持たないため、`getBoundingClientRect()` は常に `0` を返す — **jsdom では高さ・幅の実測は原理的に不可能**（jsdom 公式 issue で明言されている既知の制約）。したがって「ボタンの実測高さが 44px 以上」のようなアサーションは vitest に書いても意味を持たない。

現実解は **実ブラウザでレイアウトを描画してから測る** ことで、Playwright の `locator.boundingBox()` が実描画後の `x/y/width/height`（ピクセル）を返す（[Playwright 公式 API](https://playwright.dev/docs/api/class-locator#locator-bounding-box) で確認）。これを Server Component の検索フォーム（`src/ui/search-form.tsx`）に対して実行し、`expect(box.height).toBeGreaterThanOrEqual(40)` のようなアサーションを書けば、争点 A で確定する数値基準を PR ごとに機械的に守らせられる。E2E レイヤーは `docs/rules/sprint-development-rules.md` SD-2 が既に「操作レビュー手順は E2E テストに写す」と定めているため、既存規律の延長として自然に収まる。

同時に `@axe-core/playwright`（Deque Labs 公式・axe-core を Playwright に注入する薄いラッパー）を同じテストファイルに組み込めば、§7.7 が「Lighthouse は axe-core 全ルールの約半分しか実行せず自動検出できる WCAG 違反は 30〜40% 程度」と書いている自動検証の穴を、Lighthouse より広いルールセットで埋められる（[出典](https://qaskills.sh/blog/playwright-accessibility-testing-axe-complete-guide)・取得日 2026-08-19 JST）。CI 統合パターンは公式ブログ含め複数の一次情報で確認済み（[Rishi Kumar Chawda 記事](https://rishikc.com/articles/accessibility-testing-ci-integration/)）。

**注意（既存資産との重複回避）**: `eslint-plugin-jsx-a11y` は `eslint-config-next` の依存として **既に有効**（`node_modules/eslint-config-next/dist/index.js` に `jsx-a11y/alt-text` 等のルールが実装済みで確認）。新規追加は不要 — これは「有用そうに見えて実は既に入っている」典型例なので、争点 E の提案から除外する。

---

## 争点E: Claude Code 資産の選別

### 今すぐ導入と判定しない理由（MCP サーバー系）

- **shadcn 公式 MCP**（[ui.shadcn.com/docs/mcp](https://ui.shadcn.com/docs/mcp)・取得日 2026-08-19 JST）: レジストリの検索・自然言語でのコンポーネント追加ができるが、本プロジェクトは既に `shadcn` CLI（`package.json` に `^4.18.0`）で `npx shadcn add` が動く。MCP は「会話でコンポーネントを足す」利便性を上げるだけで、UI 品質そのものを担保しない。新規コンポーネント追加が頻発するフェーズになってから足す判断でよい。
- **Playwright MCP**（Microsoft 公式 `@playwright/mcp`）・**Chrome DevTools MCP**（Google 公式・Chrome DevTools チーム開発・[GitHub](https://github.com/ChromeDevTools/chrome-devtools-mcp/)・43,000+ stars・取得日 2026-08-19 JST）: どちらもセッション内でブラウザを対話的に操作するツールで、実装中の「ちょっと見てみる」には有効。しかし **継続的な品質担保という議題の目的には合わない** — MCP はセッションが終われば検証をやり直さないが、争点 D で導入する Playwright テストは PR ごとに CI で強制される。両方を常時接続すると `.mcp.json` のツール面が増え、権限プロンプト・トークンコストが増える一方で、CI ゲートという実効性のある担保は増えない。Chrome DevTools MCP は将来パフォーマンス調査（INP・LCP の実測デバッグ）が頻発したら追加候補にする。

### 採らないと判定: `frontend-design` 公式 plugin

Anthropic 公式マーケットプレイス（`/plugin marketplace add anthropics/claude-code` → `/plugin install frontend-design@claude-code-plugins`・[claude.com/plugins/frontend-design](https://claude.com/plugins/frontend-design)・27万+インストール・取得日 2026-08-19 JST）。内容は「大胆な配色・個性的なタイポグラフィペアリング・演出的なモーション」を志向する設計フレームワークだが、本プロジェクトの `ui-ux-guidelines.md` はタイポスケール 5 段階固定・4px グリッド・セマンティックトークン限定という **意図的に抑制的なデザインシステム制約** を敷いている。frontend-design plugin の狙い（"generic system fonts を避け大胆な選択をする"）は、この制約と正面から矛盾する方向性であり、有効化すると SP-1 のような既定値素通し事故とは逆向きに「ガイドライン外の装飾的実装」を誘発するリスクがある。今回の議題（既定値の素通し防止）には寄与しない。

### 既存 19 スキルとの重複確認

`.claude/skills/` を確認した結果、`code-review` / `self-reviewer` / `pr-review-watcher` は差分レビューの一般プロセスを担うが、**UI の実測値検証（axe-core・boundingBox）を実行する仕組みは持たない**。新規スキルを作るより、争点 D で追加する Playwright テストファイルを `npm test` 相当の既存 CI ゲートに組み込み、`code-review` / `pr-review-watcher` が「テストが通っているか」を見る既存フローに乗せるのが最小コストで、19 スキルとの責務重複も生まない。

### `design_system` — 主張
<sub>2026-08-19T10:03:20+09:00</sub>

## 一次情報（争点 B 前提）

- **shadcn 公式（作者 @shadcn の X 投稿・2026 年）**: 「Nova – Reduced spacing for compact layouts」。5 スタイル中、Nova は明示的に「コンパクトレイアウト向けの余白削減」と位置づけられている（[出典](https://x.com/shadcn/status/1999530419125981676)・取得 2026-08-19 JST）。
- 第三者だが同時期の解説記事（Shadcnblocks.com, 2026-02-05）は Nova を「dashboards, admin panels, and data-heavy interfaces で "content on screen" を稼ぐスタイル」と説明し、より極端な密度は Mira（"spreadsheet-style layouts"）としている（[出典](https://www.shadcnblocks.com/blog/shadcn-component-styles-vega-nova-maia-lyra-mira)・取得 2026-08-19 JST）。
- **結論**: `h-8`(32px) は **「情報密度優先の管理画面 UI」を想定した既定値**であり、本アプリのような一般利用者向け検索フォーム（サイトの主役アクション）にはミスマッチ。推測ではなく作者一次情報で確認済み。

## 争点 B: 4 案の評価

| 案 | 得失 | 判定 |
|---|---|---|
| (iii) 呼び出し側 `className` 上書き | 今回 1 箇所（`search-form.tsx`）は直せるが、次に増える呼び出し箇所ごとに書き忘れるリスクがそのまま残る。**この事故自体が「既定値への無警戒な依存」で起きた**ため、同じ失敗モードを温存する | 却下 |
| (ii) `size` バリアントの使い分け（`lg` 等） | Button には既に `xs/sm/default/lg/icon` があるが、**`default` を使う限り事故は再現する**。「毎回 `size="lg"` を選ぶ」運用は (iii) と同じ記憶依存の弱点を持つ | 単独では不採用（後述のとおり default 自体の底上げに従属させる） |
| (i) コンポーネント既定を書き換える | 効果は確実だが、**生の px（`h-11` 等）を書くと「なぜこの値か」が消え、将来 `shadcn add` で入る新規コンポーネント（select・textarea 等）に基準が伝播しない** | 単独では不採用。(iv) と併用で採用 |
| (iv) `@theme` にサイズトークンを定義し両者が参照する | 起点はここにすべき。ただし **shadcn CLI はレジストリのファイルをそのまま生成する仕組みで、`components.json` にサイズをテンプレート差し替えするフィールドは存在しない**（現行 `components.json` の全キーは `style/rsc/tsx/tailwind{config,css,baseColor,cssVariables,prefix}/iconLibrary/rtl/aliases/menuColor/menuAccent/registries` のみで自由記述は使われない）。**トークンだけでは新規コンポーネントに自動で効かない** | 採用（ただし運用面の補強が必須。下記） |

**決定**: **(iv) を基盤に (i) で適用する**。`@theme` にセマンティックなコントロールサイズトークンを定義し、**既存コンポーネントの default はそのトークンで書き換える**。(iii)（呼び出し側上書き）は不採用、(ii)（size バリアント運用）は「default を上げる」判断に一本化し、個別選択の運用に頼らない。

## Tailwind CSS v4 の技術的根拠（context7 で確認）

- 公式ドキュメント（`tailwindcss.com/docs/height` 等）: **「height / size ユーティリティは `--spacing` テーマ変数で制御される」**。v4 は個々の `--spacing-8` のような変数を列挙しているのではなく、`--spacing`（基準値 `0.25rem`）を掛け算して動的生成する（[出典](https://tailwindcss.com/docs/height)・context7 `/websites/tailwindcss` 経由・取得 2026-08-19 JST）。
- そのため **数値以外の名前付きキーを `--spacing-<name>` として追加すると、任意値記法なしで `h-<name>` 等のクラスが生成される**（公式の `--spacing-4_5: 1.125rem` → `p-4_5` の例と同型・[出典](https://tailwindcss.com/docs/theme)）。これが「任意値なし」の要件を満たす唯一の正攻法。
- 注意点: `--spacing-*` は `height/width/padding/margin/gap/inset` 等すべてで**共有される名前空間**なので、`h-control-md` を定義すると理論上 `p-control-md` 等も生成される。これは Tailwind v4 の設計そのもの（既存の `h-8`/`p-8` も同じ数値スケールを共有）であり欠陥ではない。

## 具体的な差分案

**1. `app/globals.css`**（`@theme inline` ブロックに追記。4px グリッドに整合: 36/44/48px はいずれも 4 の倍数）

```css
@theme inline {
  /* ...既存トークン... */
  --spacing-control-sm: calc(var(--spacing) * 9);   /* 36px: 密なグルーピング用（将来の icon button 等） */
  --spacing-control-md: calc(var(--spacing) * 11);  /* 44px: 主要コントロールの既定（検索入力・送信ボタン） */
  --spacing-control-lg: calc(var(--spacing) * 12);  /* 48px: 予備（hero CTA 等、現状未使用） */
}
```

**2. `src/ui/components/input.tsx`**（11 行目）

```diff
- 'h-8 w-full min-w-0 rounded-lg border border-input bg-transparent px-2.5 py-1 text-base ...'
+ 'h-control-md w-full min-w-0 rounded-lg border border-input bg-transparent px-3 py-1 text-base ...'
```
（`px-2.5`→`px-3` は 4px グリッド整合のための最小限の追随。垂直方向は `h-*` が明示指定なのでレイアウト崩れなし）

**3. `src/ui/components/button.tsx`**（24-25 行目、`size.default` のみ変更。`xs/sm/lg/icon` は現状維持＝他画面が増えても密なコンテキストでは既存バリアントを選べる）

```diff
  default:
-   'h-8 gap-1.5 px-2.5 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2',
+   'h-control-md gap-1.5 px-3 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2',
```

**4. `src/ui/search-form.tsx`**: 変更不要（`className="flex-1"` のままトークン適用の恩恵を受ける）。現状 Button/Input の呼び出し箇所は本フォーム 1 箇所のみ（`grep` 実測・[SP-1] 段階のため他画面への影響なし）。

## 将来の `shadcn add` にどう基準を効かせるか（運用面・技術だけでは閉じない）

- **技術的限界を明記**: `shadcn diff`/`add --overwrite` はローカル差分と upstream 差分を見比べる補助はできるが、**新規コンポーネント（`select`・`textarea` 等）はレジストリのソースをそのままコピーするだけで、既存プロジェクトの `@theme` トークンを自動で参照させる仕組みはない**（[出典](https://github.com/shadcn-ui/ui/discussions/7170) / mintlify ミラー `shadcn diff` ドキュメント・取得 2026-08-19 JST）。トークンを作っただけでは B の再発を防げない。
- **よって運用ルールを既存ガイドラインに追記する**（`docs/03_design/ui-ux/ui-ux-guidelines.md` §1「やってはいけないこと」に 1 行追加）: 「`shadcn add` した生成物に含まれる `h-6/h-7/h-8/size-8` 等の生の高さ値は、主要な操作系コンポーネントであれば `h-control-*` トークンへ置換してからコミットする」。既存の「`use client` 境界を毎回目視で確認する」と同じ **PR レビュー時の目視チェック項目**として追加するのが最小コスト（新規ツール不要）。
- 機械検証としては `grep -rn 'h-[678]\b\|size-8\b' src/ui/components/` を pre-PR フックの警告（block ではなく flag）に足すことは可能だが、**「密な文脈でわざと `h-7` を使う」正当なケースもある**（xs/sm バリアント自体が該当）ため exit 1 の強制ゲートにはしない。Warning 止まりを推奨（採否は lead 判断）。

## Next.js 16 RSC / 既存ガイドラインとの整合

- 変更は Tailwind クラス文字列のみで、`use client` 境界・Server/Client 分岐に影響しない（`Input`/`Button` は既に汎用ラッパーで `search-form.tsx` は Server Component のまま）。
- 4px グリッド（§2.3）・固定幅禁止（§3）と衝突しない。タイポスケール（§2.3）にも触れない。

### `a11y_wcag` — 主張
<sub>2026-08-19T10:03:30+09:00</sub>

## a11y_wcag: WCAG 2.2 適合状況の確定と §7 追記項目（一次情報ベース）

### 1. 該当 SC の正確な適合レベル・除外条件（W3C Understanding 文書で確認済み）

| SC | 正式名称 | レベル | 要求値 | 出典 |
|---|---|---|---|---|
| 2.5.8 | Target Size (Minimum) | **AA** | ポインタ対象 24×24 CSS px 以上。除外: Spacing / Inline / Equivalent / User Agent Control / Essential | [Understanding 2.5.8](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html)（2026-08-19 JST 取得） |
| 2.5.5 | Target Size (Enhanced) | **AAA** | 44×44 CSS px 以上。除外は同種だが Equivalent の基準サイズも 44px | [Understanding 2.5.5](https://www.w3.org/WAI/WCAG22/Understanding/target-size-enhanced.html)（同日取得） |
| 2.4.11 | **Focus Not Obscured (Minimum)** | **AA** | フォーカス時に UI コンポーネントが著者コンテンツで**完全に**隠れない | [WCAG 2.2 仕様本体](https://www.w3.org/TR/WCAG22/)（同日取得） |
| 2.4.12 | Focus Not Obscured (Enhanced) | AAA | 一部でも隠れない（上位互換） | 同上 |
| 2.4.13 | **Focus Appearance** | **AAA**（争点 spec の「2.4.11」表記は旧ドラフト番号。確定版では 2.4.13） | フォーカスインジケータの最小面積（矩形なら **4h+4w**）かつ非フォーカス状態との**コントラスト差 3:1 以上** | [Understanding 2.4.13](https://www.w3.org/WAI/WCAG22/Understanding/focus-appearance.html)（同日取得） |
| 1.4.11 | Non-text Contrast | **AA** | UI コンポーネントの境界・状態表現は隣接色に対し **3:1 以上** | [Understanding 1.4.11 (2.1系だが2.2で継続)](https://www.w3.org/WAI/WCAG21/Understanding/non-text-contrast.html)（同日取得） |
| 1.4.10 | Reflow | **AA** | 320 CSS px 幅（400%ズーム相当）で二次元スクロール不要 | [Understanding 1.4.10](https://www.w3.org/WAI/WCAG21/Understanding/reflow.html)（同日取得） |
| 2.5.3 | Label in Name | **A** | 可視ラベル文字列が accessible name に含まれる（可視ラベルが存在する場合のみ適用） | [Understanding 2.5.3](https://w3c.github.io/wcag21/understanding/label-in-name.html)（同日取得） |
| 3.3.2 | Labels or Instructions | **A** | 入力を要求する箇所にラベル/説明が**全ユーザーに提示**される | [Understanding 3.3.2](https://www.w3.org/WAI/WCAG21/Understanding/labels-or-instructions.html)（同日取得） |

### 2. 現状コードの判定（実測・実コード）

**(1) フォーカスリングのコントラスト — 1.4.11 / 2.4.13 の両方に抵触する疑いが強い（要実装修正）**

`input.tsx` / `button.tsx` は `focus-visible:ring-3 ring-ring/50`。`globals.css` の実値 `--ring: oklch(0.708 0 0)`（ライト）を sRGB 近似変換し、`/50`（50% アルファ）で背景 `--background: oklch(1 0 0)`（白）に合成して相対輝度から算出した結果:

```
ring 実色 ≈ rgb(161,161,161) → 50%アルファで白背景と合成 ≈ rgb(208,208,208)
コントラスト比（合成色 vs 白背景）≈ 1.54 : 1
```

ダークモードでも `--ring: oklch(0.556 0 0)` vs `--background: oklch(0.145 0 0)` で合成後 **約 1.87:1**。

1.4.11 が要求する **3:1** の約半分しかない。これは「フォーカスリングが存在するか」（2.4.7 Focus Visible・AA・現状クリア）ではなく「**視認できる強さで存在するか**」（1.4.11・AA）の問題であり、**AA 適合として通らない**可能性が高い。2.4.13（AAA）は必須ではないが、同じ実装変更（`/50` を外すか `/80` 以上に上げる、または `--ring` の L 値を下げる）で両方改善できるため一括対応を推奨する。
※ oklch→sRGB 変換は自前計算（W3C の CSS Color 4 変換式に基づく）であり、実装反映後は実測ツール（axe DevTools / Colour Contrast Analyser）での再検証を推奨。

**(2) `sr-only` ラベル — 3.3.2 の Intent と衝突する（design/form_ux と要すり合わせ）**

3.3.2 の Understanding 文書は明記している:

> "It is possible for controls and inputs to have an appropriate accessible name or description (e.g. using `aria-label="..."`) and therefore pass Success Criterion 4.1.2, but to still fail this success criterion"

つまり `sr-only` の `<label>` は **4.1.2（Name, Role, Value）は満たすが、3.3.2 の意図（全ユーザーへの可視提示）は満たさない**、というのが W3C 自身の立場。現状はプレースホルダ（`placeholder:text-muted-foreground`）だけが視覚的ラベル代替になっており、プレースホルダはフォーカス時に消える・低コントラストになりがちで W3C も「ラベルの代替として不十分」と繰り返し指摘している（別 SC 1.3.1 の Understanding にも同旨あり）。**a11y 観点では可視ラベルへの変更を推奨**（文言・レイアウトは form_ux/design_system の判断に委ねるが、`sr-only` のままにする場合は「意図的な逸脱」として §7 に理由を明記すべき）。

**(3) iOS/iPadOS Safari オートズーム — md ブレークポイントに実バグの穴がある**

一次情報（[CSS-Tricks](https://css-tricks.com/16px-or-larger-text-prevents-ios-form-zoom/)、2026-08-19 JST 取得。Apple 公式のピンポイント一次資料はなく、WebKit の実装挙動として業界で広く再現確認されている二次情報が実質的な一次情報の位置づけ）: **フォーカス時の実測フォントサイズが 16px 未満だと iOS/iPadOS Safari は自動でズームする**。

`input.tsx` は `text-base md:text-sm`（Tailwind mobile-first）。モバイル実機（<768px）では `text-base`=16px が適用されるため **スマホでは問題なし**。しかし **iPad の Safari は標準の縦向きビューポート幅が 768px** で `md:` ブレークポイントに一致し、`text-sm`=14px が適用される。iPad Safari も同一の WebKit オートズームを持つため、**iPad で検索欄をタップすると意図しないページズームが発生する**可能性が高い。これは 1.4.4 Resize Text 自体の違反ではないが、望まない自動ズームは操作性を損ない、キーボード表示中にレイアウトが崩れる形で 1.4.10 Reflow の実運用にも波及しうる。**§7 に「フォームコントロールの `font-size` はブレークポイントを問わず 16px 未満にしない」という明文規則が必要**（現状規則が存在しないため、`md:text-sm` のような一般則がそのまま入力欄に適用されてしまった）。

**(4) 200% 拡大時のリフロー — 現状の `flex gap-2` 構成は 1.4.10 を満たす（違反ではない）**

`Input` は `flex-1`、`Button` は `shrink-0` だが固定幅指定はなく、320 CSS px 幅（1.4.10 の判定基準点）− `page.tsx` の `px-4`（32px）を引いても入力欄が可変幅で残るため横スクロールは発生しない。**ただし `Button` の `shrink-0` は「検索」より長いラベル（多言語化・アイコン追加時等）を入れた瞬間に破綻しうる**ため、§7 に「送信ボタンの文言は短い固定語に限定する」旨の注記を残すことを推奨（design_system/form_ux の争点 C 判断に従属）。

**(5) `prefers-reduced-motion` / `pointer: coarse` — 現状コードに動きを伴う要素はない**

`transition-colors` / `transition-all` はホバー・フォーカスの色変化のみで、WCAG 2.3.3 Animation from Interactions（AAA）が問題にする「大きな動き」に該当しない。**現時点では対応不要**（誤ってグローバルに `prefers-reduced-motion: reduce` 対応を追加提案する声があれば YAGNI として却下を推奨）。`pointer: coarse` によるタッチ時のみのサイズ拡大は mobile_touch の争点 A 判断に従う。

### 3. 争点 A（最小高さ）への a11y 観点の回答

**WCAG 適合の絶対下限（AA・必須）: 24px**（2.5.8。現状 32px はこの下限を満たしており **2.5.8 は違反ではない**）。
**a11y 観点の推奨値: 40〜44px**。根拠は 2.5.5（AAA・44px）そのものへの適合ではなく、44px 前後にすると (a) 2.4.13 のフォーカス面積要件（`4h+4w`）が縦横比の良い形で満たしやすくなる、(b) タッチ入力での誤タップ低減（mobile_touch の Fitts の法則の議論と整合）の 2 点。**AA 適合だけなら現状の 32px で技術的に足りるが、「操作性が良くない」というユーザー報告の実体はこの隙間（AA ギリギリ）にある**、というのが a11y レンズからの結論。

### 4. §7 に追記すべき項目（具体）

1. §7.5 を「ターゲットサイズ」から「**ターゲットサイズと推奨コントロール高さ**」に改題し、2.5.8（AA・24px 必須下限）と 2.5.5（AAA・44px 参考値）を明示的に書き分ける
2. **1.4.11 Non-text Contrast** の新設項目: フォーカスリング・ボーダー等の非テキスト UI 表現は隣接色に対し 3:1 以上。`--ring` の実効コントラストを計算式または実測ツールで PR ごとに確認する運用を明記
3. **2.4.13 Focus Appearance** への言及を 7.3 に追加（AAA だが実装コストがほぼ 0 のため「満たす」を目標にしてよい）
4. **フォームコントロールの `font-size` 下限 16px** をブレークポイント非依存で明文化（iOS/iPadOS オートズーム対策）
5. **3.3.2 と可視ラベル**: `sr-only` ラベルを使う場合は「なぜ可視ラベルを採用しないか」の理由を明記する運用ルールを追加（本件は不可視ラベルを既定にしない方針を推奨）
6. 7.6「該当しない基準」に 2.5.5 / 2.4.12 / 2.4.13 を「AAA・非必須だが可能なら満たす」として記録（何を意図的に見送ったかを残す）

---
**サマリー**: WCAG 2.2 の必須（AA）違反候補は **フォーカスリングのコントラスト不足（1.4.11・実測 1.5〜1.9:1 で 3:1 未達）**。ターゲットサイズ自体（2.5.8）は現状 32px で AA を満たすため違反ではなく、44px への引き上げは AAA 整合とタッチ操作性向上のための推奨。追加の実害として **iPad Safari でのオートズーム**（`md:text-sm` の穴）と **`sr-only` ラベルが 3.3.2 の意図を満たさない**という 2 点を特定した。
