<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: 入力フォームの操作性（コントロール高さ・タッチターゲット・フォーム UX）を最新の一次情報で確定し実装指針に落とす

- 議題ID: `form-ux-sizing-20260819`
- 論点: 検索フォームの入力欄・ボタンが h-8(32px) で縦幅が小さく操作性が悪い。根本原因はガイドラインに主要コントロールの最小高さ基準が無く shadcn radix-nova の既定を素通ししたこと。争点 A(最小高さの数値と根拠) B(shadcn 既定の扱い方) C(検索フォーム UX) D(ガイドラインへの落とし方と機械検証) E(導入価値のある Claude Code 資産)。詳細は tools/discussion_specs/form_ux_sizing_spec.json
- 参加者: `mobile_touch`, `form_ux`, `design_system`, `a11y_wcag`, `tooling_scout`
- 投稿数: 12
- 更新: 2026-08-19T10:11:20+09:00

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
- **48×48dp** が最小タッチターゲット（物理サイズ約 9mm、推奨レンジ 7–10mm）。**視覚サイズ（アイコン 24dp 等）とタッチ領域（48dp）は別概念** であり、透明パディングで拡張してよい。標準ボタンは **最小高さ 48dp + 水平パディング 16dp**。ターゲット間は 8dp 以上の間隔を推奨。
出典: https://m3.material.io/foundations/designing/structure（2026-08-19 JST 取得）

## 2.「ターゲットサイズ」と「コントロールの視覚的高さ」は別概念 — ただし本件には使えない

WCAG の要件は **ヒットエリア（クリック/タップ可能領域）** の話であり、**見た目の高さ** ではない。理論上は「視覚 32px + 見えないパディングで 44px のヒットエリア」でも 2.5.8/2.5.5 は満たせる。

しかし本件（検索フォームの主要 2 コントロール）にはこの回避策を **推奨しない**:
1. NN/g 等の知見（form_ux レンズと要突合）で、ユーザーは視覚サイズでタップ判断するため見た目と実際の当たり判定が乖離すると「押しにくそうに見える」印象自体は解消されない（心理的 Fitts's law の起点はポインタが移動する視覚的な的の大きさ）。
2. `search-form.tsx` は `flex gap-2` で入力欄とボタンが横並び・隣接しており、見えないパディングで拡張すると **互いのヒットエリアが重なる/意図しない誤タップの原因** になりうる（Spacing 例外の考え方と逆行）。
3. 今回の争点は「縦幅が小さく操作性が悪い」というユーザー **体感** 報告であり、視覚的高さを変えない対処は根本原因に対応しない。

→ **視覚的な高さそのものを引き上げる** のが正しい対処。

## 3. Fitts の法則・タッチ精度研究

Fitts's law: 到達時間 ∝ log2(距離/ターゲット幅+1)。ターゲットが小さいほど到達・確定に時間がかかり、誤操作が増える。タッチは指先の物理的な接触面積（成人の指先パッド幅は概ね 8–10mm）とパララックス（視差）誤差が加わるため、**マウスのポインタ精度よりターゲットに対する要求が厳しい**。Apple の「25%以上のタップエラー率」（HIG 系情報源に集約）はこの物理制約を反映した経験則であり、24px（≈6.4mm@160dpi 相当ではなく CSS px なので機種依存だが一般に）は「法的最低ライン」、44px/48px は「実用ライン」という位置づけが一次情報間で一貫している。

## 4. 現状 32px（h-8）が悪化させる具体点

- `Input`（`h-8` = 32px）・`Button` size=default（`h-8` = 32px）はいずれも **WCAG 2.5.8 AA の 24px は形式的にクリア**（32>24、間隔例外に頼る必要すらない）。→ **法的な非適合ではない**。
- しかし **Apple HIG 44pt・Material 3 48dp のどちらの実用基準にも届かず**、AAA（44px）にも届かない。32px は 44px 比で **面積が約 53%**（32²/44²）しかなく、Fitts's law に基づけば到達時間・誤タップ率が有意に悪化する領域。
- `search-form.tsx` は `flex gap-2`（8px）で入力欄とボタンを隣接配置しており、コントロール自体が小さいうえ間隔も広くない → 誤タップの複合要因になりやすい。
- モバイル実機では「検索」ボタンが親指到達域の下部にない構成（フォームがページ上部にある想定・`app/page.tsx` 未確認だが `max-w-3xl px-4 py-10` から通常レイアウト）でも、ボタン自体が小さいと **意図した1回のタップで確定できない＝再タップ・スクロール補正の手間** が生じ、これが「操作性が良くない」という体感報告の主因と推定できる。

## 5. ポインタ入力とタッチ入力で基準を変えるべきか（`pointer: coarse`）

- `any-pointer: coarse` は「粗い入力デバイスが **存在するか**」を見るクエリで、タッチスクリーン搭載ノート PC 等のハイブリッド機では **`any-pointer: fine` と `any-pointer: coarse` が同時に真** になりうる（一次情報: MDN / josh coast のまとめ、出典 https://developer.mozilla.org/en-US/docs/Web/CSS/@media/pointer 、2026-08-19 JST 取得）。`pointer:`（`any-` なし）は **主入力** を見るため誤判定は少ないが、それでも「デスクトップ = マウスだから小さくてよい」という前提は崩れつつある（タッチ対応ノート PC・タブレット外付けキーボードの普及）。
- **本件（検索フォームの主要 2 コントロール）への推奨: `pointer: coarse` による出し分けをしない。** 理由: (a) 検索はアプリの中心 CTA であり、マウス利用時でも大きい方が Fitts's law 的に有利（デメリットがほぼない）。(b) 出し分けはコードの複雑性を増し、JS なしの GET フォーム（RSC）という制約下でも CSS だけで実装は可能だが、**検証コストに見合わない**（jsdom では実測できず、E2E でも `pointer` メディア特性のテストは実質困難）。(c) `tooling_scout` レンズとも関わるが、「常に十分な大きさ」の方が保守性が高い。
- **出し分けを使ってよい場面**（本件のスコープ外として明示）: データテーブルの行内アイコンボタン等、密度が UX 上の価値を持つ副次的コントロール。

## 6. 争点 A への具体的数値推奨

**検索入力（Input）・送信ボタン（Button）の両方を、ブレークポイント無条件で最小高さ 44px（Tailwind `h-11`）に引き上げる。**

- 根拠: Apple HIG 44pt と WCAG 2.5.5（AAA・エンハンス基準）が一致する数値であり、Material 3 の 48dp（`h-12`）より 4px 刻みグリッドに収まりが良く既存 `lg`（`h-9`=36px）からの連続性も保ちやすい。24px（AA 必須ライン）はあくまで **法的下限** であり実用基準として採用しない。
- 44px は既存の 4px グリッド（4/8/12/16/24/32...）に一致するため制約と衝突しない（`h-11` = 44px は Tailwind 標準トークン）。
- 48px（Material 3 準拠・`h-12`）を採るなら **さらに安全** だが、`lg` バリアント（36px）との差が開きすぎるため、まずは 44px を下限として提案し、`design_system` レンズの size バリアント設計と合わせて最終判断すべき。
- ボタン・入力の **視覚的高さ** として 44px を確保すること（見えないパディングでの誤魔化しは 5 節の理由で不可）。
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

さらに NN/g の代表的知見として、**プレースホルダをラベルの代替にすることの弊害** が確立している: 長い入力中にヒントを忘れる・視覚/認知障害者に負担・値を入れると消える（[NN/g: Placeholders in Form Fields Are Harmful](https://www.nngroup.com/articles/form-design-placeholders/)、取得日 2026-08-19 JST）。現状の実装はまさに「ラベルは sr-only、視覚的にはプレースホルダのみが手がかり」というアンチパターンに該当する。2026 時点の潮流調査でも「Never use placeholders as labels」「Labels stay visible」が繰り返し明記されている（[SpecificIT: Trends in Form Design for 2026](https://specificit.com.au/trends-in-form-design-2026/)、取得日 2026-08-19 JST）。

**提案**: `sr-only` を外し、入力欄の直上に 14px（既存タイポスケール内）の可視ラベル「検索キーワード」を配置する。プレースホルダは「例: react」程度の **補助的な例示** に格下げし、ラベルの代替にしない。

### 2. 送信ボタンの文言・アイコン

NN/g のアイコン単体化への警鐘（[NN/g: The Magnifying-Glass Icon in Search Design](https://www.nngroup.com/articles/magnifying-glass-icon/)、取得日 2026-08-19 JST）を踏まえ、**テキストボタン「検索」を維持** する。アイコンを足す場合もテキストと併記（アイコン単体化は不可）。`white-space: nowrap` 禁止（`NFR-15`）と矛盾しないよう、アイコンを追加するなら `inline-flex items-center gap-1.5` とし、折返しを許容する実装にする。

### 3. モバイルでの縦積み判断

USWDS は検索入力の最小幅を「27 文字分」としている（[USWDS: Search](https://designsystem.digital.gov/components/search/)、取得日 2026-08-19 JST）。これと 44px 級のボタン（争点A・mobile_touch 担当）を横並びで確保するには少なくとも `sm`（Tailwind 既定 640px）程度の幅が要る。既存コンテナが `max-w-3xl`（768px 相当）でモバイル時は画面幅そのものになるため、**640px 未満は縦積み、640px 以上で横並び** に切り替える。2026 年の潮流調査も「モバイルはシングルカラム・大きめの入力欄」を一貫して推奨している（[SpecificIT](https://specificit.com.au/trends-in-form-design-2026/)、取得日 2026-08-19 JST）。

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

`h-11`/`px-6` をフォーム側 className で上書きする方式は、既定を書き換える (i) や className 個別上書き (iii) のどちらでも実現可能。**design_system レンズの結論を優先** し、フォーム側は決定されたトークン/バリアントを呼び出すだけにする（本提案の `h-11` はプレースホルダ値であり、争点B の決定値に置き換える）。

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
- **結論**: `h-8`(32px) は **「情報密度優先の管理画面 UI」を想定した既定値** であり、本アプリのような一般利用者向け検索フォーム（サイトの主役アクション）にはミスマッチ。推測ではなく作者一次情報で確認済み。

## 争点 B: 4 案の評価

| 案 | 得失 | 判定 |
|---|---|---|
| (iii) 呼び出し側 `className` 上書き | 今回 1 箇所（`search-form.tsx`）は直せるが、次に増える呼び出し箇所ごとに書き忘れるリスクがそのまま残る。**この事故自体が「既定値への無警戒な依存」で起きた** ため、同じ失敗モードを温存する | 却下 |
| (ii) `size` バリアントの使い分け（`lg` 等） | Button には既に `xs/sm/default/lg/icon` があるが、**`default` を使う限り事故は再現する**。「毎回 `size="lg"` を選ぶ」運用は (iii) と同じ記憶依存の弱点を持つ | 単独では不採用（後述のとおり default 自体の底上げに従属させる） |
| (i) コンポーネント既定を書き換える | 効果は確実だが、**生の px（`h-11` 等）を書くと「なぜこの値か」が消え、将来 `shadcn add` で入る新規コンポーネント（select・textarea 等）に基準が伝播しない** | 単独では不採用。(iv) と併用で採用 |
| (iv) `@theme` にサイズトークンを定義し両者が参照する | 起点はここにすべき。ただし **shadcn CLI はレジストリのファイルをそのまま生成する仕組みで、`components.json` にサイズをテンプレート差し替えするフィールドは存在しない**（現行 `components.json` の全キーは `style/rsc/tsx/tailwind{config,css,baseColor,cssVariables,prefix}/iconLibrary/rtl/aliases/menuColor/menuAccent/registries` のみで自由記述は使われない）。**トークンだけでは新規コンポーネントに自動で効かない** | 採用（ただし運用面の補強が必須。下記） |

**決定**: **(iv) を基盤に (i) で適用する**。`@theme` にセマンティックなコントロールサイズトークンを定義し、**既存コンポーネントの default はそのトークンで書き換える**。(iii)（呼び出し側上書き）は不採用、(ii)（size バリアント運用）は「default を上げる」判断に一本化し、個別選択の運用に頼らない。

## Tailwind CSS v4 の技術的根拠（context7 で確認）

- 公式ドキュメント（`tailwindcss.com/docs/height` 等）: **「height / size ユーティリティは `--spacing` テーマ変数で制御される」**。v4 は個々の `--spacing-8` のような変数を列挙しているのではなく、`--spacing`（基準値 `0.25rem`）を掛け算して動的生成する（[出典](https://tailwindcss.com/docs/height)・context7 `/websites/tailwindcss` 経由・取得 2026-08-19 JST）。
- そのため **数値以外の名前付きキーを `--spacing-<name>` として追加すると、任意値記法なしで `h-<name>` 等のクラスが生成される**（公式の `--spacing-4_5: 1.125rem` → `p-4_5` の例と同型・[出典](https://tailwindcss.com/docs/theme)）。これが「任意値なし」の要件を満たす唯一の正攻法。
- 注意点: `--spacing-*` は `height/width/padding/margin/gap/inset` 等すべてで **共有される名前空間** なので、`h-control-md` を定義すると理論上 `p-control-md` 等も生成される。これは Tailwind v4 の設計そのもの（既存の `h-8`/`p-8` も同じ数値スケールを共有）であり欠陥ではない。

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
- **よって運用ルールを既存ガイドラインに追記する**（`docs/03_design/ui-ux/ui-ux-guidelines.md` §1「やってはいけないこと」に 1 行追加）: 「`shadcn add` した生成物に含まれる `h-6/h-7/h-8/size-8` 等の生の高さ値は、主要な操作系コンポーネントであれば `h-control-*` トークンへ置換してからコミットする」。既存の「`use client` 境界を毎回目視で確認する」と同じ **PR レビュー時の目視チェック項目** として追加するのが最小コスト（新規ツール不要）。
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
| 2.4.11 | **Focus Not Obscured (Minimum)** | **AA** | フォーカス時に UI コンポーネントが著者コンテンツで **完全に** 隠れない | [WCAG 2.2 仕様本体](https://www.w3.org/TR/WCAG22/)（同日取得） |
| 2.4.12 | Focus Not Obscured (Enhanced) | AAA | 一部でも隠れない（上位互換） | 同上 |
| 2.4.13 | **Focus Appearance** | **AAA**（争点 spec の「2.4.11」表記は旧ドラフト番号。確定版では 2.4.13） | フォーカスインジケータの最小面積（矩形なら **4h+4w**）かつ非フォーカス状態との **コントラスト差 3:1 以上** | [Understanding 2.4.13](https://www.w3.org/WAI/WCAG22/Understanding/focus-appearance.html)（同日取得） |
| 1.4.11 | Non-text Contrast | **AA** | UI コンポーネントの境界・状態表現は隣接色に対し **3:1 以上** | [Understanding 1.4.11 (2.1系だが2.2で継続)](https://www.w3.org/WAI/WCAG21/Understanding/non-text-contrast.html)（同日取得） |
| 1.4.10 | Reflow | **AA** | 320 CSS px 幅（400%ズーム相当）で二次元スクロール不要 | [Understanding 1.4.10](https://www.w3.org/WAI/WCAG21/Understanding/reflow.html)（同日取得） |
| 2.5.3 | Label in Name | **A** | 可視ラベル文字列が accessible name に含まれる（可視ラベルが存在する場合のみ適用） | [Understanding 2.5.3](https://w3c.github.io/wcag21/understanding/label-in-name.html)（同日取得） |
| 3.3.2 | Labels or Instructions | **A** | 入力を要求する箇所にラベル/説明が **全ユーザーに提示** される | [Understanding 3.3.2](https://www.w3.org/WAI/WCAG21/Understanding/labels-or-instructions.html)（同日取得） |

### 2. 現状コードの判定（実測・実コード）

**(1) フォーカスリングのコントラスト — 1.4.11 / 2.4.13 の両方に抵触する疑いが強い（要実装修正）**

`input.tsx` / `button.tsx` は `focus-visible:ring-3 ring-ring/50`。`globals.css` の実値 `--ring: oklch(0.708 0 0)`（ライト）を sRGB 近似変換し、`/50`（50% アルファ）で背景 `--background: oklch(1 0 0)`（白）に合成して相対輝度から算出した結果:

```
ring 実色 ≈ rgb(161,161,161) → 50%アルファで白背景と合成 ≈ rgb(208,208,208)
コントラスト比（合成色 vs 白背景）≈ 1.54 : 1
```

ダークモードでも `--ring: oklch(0.556 0 0)` vs `--background: oklch(0.145 0 0)` で合成後 **約 1.87:1**。

1.4.11 が要求する **3:1** の約半分しかない。これは「フォーカスリングが存在するか」（2.4.7 Focus Visible・AA・現状クリア）ではなく「**視認できる強さで存在するか**」（1.4.11・AA）の問題であり、**AA 適合として通らない** 可能性が高い。2.4.13（AAA）は必須ではないが、同じ実装変更（`/50` を外すか `/80` 以上に上げる、または `--ring` の L 値を下げる）で両方改善できるため一括対応を推奨する。
※ oklch→sRGB 変換は自前計算（W3C の CSS Color 4 変換式に基づく）であり、実装反映後は実測ツール（axe DevTools / Colour Contrast Analyser）での再検証を推奨。

**(2) `sr-only` ラベル — 3.3.2 の Intent と衝突する（design/form_ux と要すり合わせ）**

3.3.2 の Understanding 文書は明記している:

> "It is possible for controls and inputs to have an appropriate accessible name or description (e.g. using `aria-label="..."`) and therefore pass Success Criterion 4.1.2, but to still fail this success criterion"

つまり `sr-only` の `<label>` は **4.1.2（Name, Role, Value）は満たすが、3.3.2 の意図（全ユーザーへの可視提示）は満たさない**、というのが W3C 自身の立場。現状はプレースホルダ（`placeholder:text-muted-foreground`）だけが視覚的ラベル代替になっており、プレースホルダはフォーカス時に消える・低コントラストになりがちで W3C も「ラベルの代替として不十分」と繰り返し指摘している（別 SC 1.3.1 の Understanding にも同旨あり）。**a11y 観点では可視ラベルへの変更を推奨**（文言・レイアウトは form_ux/design_system の判断に委ねるが、`sr-only` のままにする場合は「意図的な逸脱」として §7 に理由を明記すべき）。

**(3) iOS/iPadOS Safari オートズーム — md ブレークポイントに実バグの穴がある**

一次情報（[CSS-Tricks](https://css-tricks.com/16px-or-larger-text-prevents-ios-form-zoom/)、2026-08-19 JST 取得。Apple 公式のピンポイント一次資料はなく、WebKit の実装挙動として業界で広く再現確認されている二次情報が実質的な一次情報の位置づけ）: **フォーカス時の実測フォントサイズが 16px 未満だと iOS/iPadOS Safari は自動でズームする**。

`input.tsx` は `text-base md:text-sm`（Tailwind mobile-first）。モバイル実機（<768px）では `text-base`=16px が適用されるため **スマホでは問題なし**。しかし **iPad の Safari は標準の縦向きビューポート幅が 768px** で `md:` ブレークポイントに一致し、`text-sm`=14px が適用される。iPad Safari も同一の WebKit オートズームを持つため、**iPad で検索欄をタップすると意図しないページズームが発生する** 可能性が高い。これは 1.4.4 Resize Text 自体の違反ではないが、望まない自動ズームは操作性を損ない、キーボード表示中にレイアウトが崩れる形で 1.4.10 Reflow の実運用にも波及しうる。**§7 に「フォームコントロールの `font-size` はブレークポイントを問わず 16px 未満にしない」という明文規則が必要**（現状規則が存在しないため、`md:text-sm` のような一般則がそのまま入力欄に適用されてしまった）。

**(4) 200% 拡大時のリフロー — 現状の `flex gap-2` 構成は 1.4.10 を満たす（違反ではない）**

`Input` は `flex-1`、`Button` は `shrink-0` だが固定幅指定はなく、320 CSS px 幅（1.4.10 の判定基準点）− `page.tsx` の `px-4`（32px）を引いても入力欄が可変幅で残るため横スクロールは発生しない。**ただし `Button` の `shrink-0` は「検索」より長いラベル（多言語化・アイコン追加時等）を入れた瞬間に破綻しうる** ため、§7 に「送信ボタンの文言は短い固定語に限定する」旨の注記を残すことを推奨（design_system/form_ux の争点 C 判断に従属）。

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
**サマリー**: WCAG 2.2 の必須（AA）違反候補は **フォーカスリングのコントラスト不足（1.4.11・実測 1.5〜1.9:1 で 3:1 未達）**。ターゲットサイズ自体（2.5.8）は現状 32px で AA を満たすため違反ではなく、44px への引き上げは AAA 整合とタッチ操作性向上のための推奨。追加の実害として **iPad Safari でのオートズーム**（`md:text-sm` の穴）と **`sr-only` ラベルが 3.3.2 の意図を満たさない** という 2 点を特定した。

## ラウンド 2

### `mobile_touch` — 反論
<sub>2026-08-19T10:05:50+09:00</sub>

# mobile_touch レンズ: Round 2 反論・応答

## 対 `a11y_wcag`: 「32px は AA 適合済み、44px は AAA 整合の推奨にすぎない」への応答

**部分的に同意し、部分的に反論する。**

同意する点: `a11y_wcag` の整理（2.5.8 AA の絶対下限は 24px であり、32px は形式的に AA 適合済み）は自分の Round 1 の記述と完全に一致しており、争いはない。「44px = AAA そのものへの適合義務」という主張はしていない。

反論する点: 「44px は AAA 整合の“推奨”にすぎない」という **フレーミング** 自体が誤解を招く。`a11y_wcag` 自身が §3 で「a11y 観点の推奨値: 40〜44px」と結論しており、根拠に自分（mobile_touch）の Fitts の法則の議論を明示的に引用している。つまり `a11y_wcag` は「AAA 整合だから」ではなく「タッチ誤操作低減のため」に 40〜44px を推奨しており、**これは AAA 準拠目的の話ではなく私の Round 1 主張と同じ実用工学上の理由**。争点は「AAA という抽象的上位基準への整合」ではなく「**この 2 コントロールに限定した、タッチ操作エラー率を下げるための実用的引き上げ**」であり、これは過剰要求（scope creep）ではない。理由は 3 点:

1. **適用範囲が極小**: アプリ全体の全コントロールを 44px にせよという主張ではない。検索フォームの主要 2 要素（入力・送信）に限定しており、`design_system` の一次情報（Nova = 情報密度優先の管理画面向けスタイル）が示す通り、そもそも `h-8` 既定自体がこのユースケースの想定外だった。是正は既定値の誤用の是正であり、新たな過剰基準の追加ではない。
2. **ユーザー体感報告との対応**: 「縦幅が小さく操作性が悪い」という報告は AA/AAA の適合ラベルとは無関係に存在する実害であり、`a11y_wcag` 自身も「操作性が良くないというユーザー報告の実体はこの隙間（AA ギリギリ）にある」と結論している。44px 論拠を「AAA 整合」に矮小化すると、この実害が見えなくなる。
3. **40〜44px という幅ではなく 44px に一本化すべき**: `a11y_wcag` は「40〜44px」とレンジで示したが、40px（`h-10`）は 4px グリッドには乗るものの Apple HIG・WCAG AAA いずれの実数とも一致しない中途半端な値になる。`design_system` が既に `--spacing-control-md: 44px` としてトークン設計済みであり、複数レンズが同じ 44px に収束している以上、レンジを残す理由はない。**44px で確定** を維持する。

## 対 `design_system`: `@theme` トークン（36/44/48px）で `pointer:coarse` 出し分けコストが下がるなら採用すべきでは

**不採用の結論は維持するが、一部譲歩する。**

`design_system` の `--spacing-control-{sm,md,lg}` トークンは、**「どの値を使うか」の宣言コストを下げる** ものであり、**「いつどちらを使うか（=出し分けロジック）」のコストは下げない**。`pointer: coarse` による出し分けを実装するには、`h-control-md`（44px 固定）とは別に「`pointer: coarse` のときだけ `h-control-lg`（48px）、`pointer: fine` のときは `h-control-sm`（36px）」のような **Tailwind バリアント併記**（例: `h-control-sm coarse:h-control-lg`、または `@theme` の値自体をメディアクエリで再定義する CSS カスタムプロパティの上書き）が別途必要で、これはトークン層ではなくコンポーネント/CSS 層の追加ロジック。トークンが増えても、この分岐自体は依然として実装・レビュー・（jsdom では検証不能という Round 1 の指摘の通り）**テストのコストとして残る**。

加えて Round 1 で述べたハイブリッド機（`any-pointer: coarse` と `any-pointer: fine` が同時に真になりうる）の問題は **値の置き場所（トークンかどうか）とは独立** した判定ロジック自体の不確実性であり、トークン導入では解消しない。

一方で譲歩する点: `design_system` が `--spacing-control-sm/md/lg` を「将来の密なコンテキスト（icon button 等）向け」として汎用的に設計したことには同意する。**このトークン基盤自体は、将来ほかの副次的コントロールで `pointer: coarse` 出し分けを採用する余地を残しておく（Round 1 §5 で述べた「密度が価値を持つ副次コントロール」向け）という点で有用** であり、トークン設計そのものへの反対はしない。反対しているのは「**今回の検索フォーム主要 2 コントロールに出し分けを適用すること**」であり、`h-control-md`（44px）で無条件固定、というのが引き続きの結論。

## 対 `form_ux`: 640px 縦積み/横並び切替と、縦積み時の `w-full` ボタンの是非

**`w-full` 自体はタッチ操作性の観点で明確に有利、ただし積み重ね時の縦間隔に懸念があり補強を提案する。**

有利な理由: `w-full` は視覚境界とヒットエリアが一致した状態でターゲット面積を大幅に拡大する（Round 1 §2 で述べた「見えないパディングでの誤魔化しは不可」の対極＝視覚・当たり判定とも真に大きい、最も望ましい形）。横方向の到達精度要求が実質ゼロになるため Fitts's law 上も明確に有利で、640px 切替判断そのものにも異論はない。

懸念点: `form_ux` の実装案（`flex flex-col gap-2` で入力欄→ボタンを縦積み、両者とも `h-11` 相当・`gap-2`=8px）では、**幅いっぱいの 2 つの大きな縦積みターゲットが 8px 間隔で隣接する**。Material 3 の「ターゲット間 8dp 以上」は形式的には満たすが、これは境界値（ちょうど最小値）であり、余裕がない。特にこのフォームは「入力 → 打ち直し（再フォーカス）→ 送信」という往復操作が起きやすく、ソフトウェアキーボード表示中は画面下部の視認性が落ちるため、**入力欄を再タップしようとしてボタンを誤タップする／その逆** のリスクが横並び時より高い（横並びなら誤タップ方向は左右のみで、縦積みでは進行方向＝スクロール/スワイプ方向と一致するため親指の慣性で行き過ぎやすい）。

**提案**: 縦積み時（`<sm`）のみ `gap-2`（8px）ではなく `gap-3`（12px）に広げる（4px グリッドには適合、`sm:` 以上では横並びに戻るため `gap-2` のままでよい）。`className="flex flex-col gap-3 sm:flex-row sm:items-end sm:gap-2"` のような出し分けを推奨する。これは `form_ux` の縦積み判断そのものへの反対ではなく、縦積み時の間隔値への追加提案。

## 結論（争点Aへの最終スタンス・変更なし）

44px（`h-11` = `design_system` の `--spacing-control-md`）を検索入力・送信ボタンの最小高さとして無条件採用。`pointer:coarse` 出し分けは不採用。縦積み時の `w-full` は採用、ただし間隔を `gap-3`（12px）に補強することを追加提案する。

### `form_ux` — 反論
<sub>2026-08-19T10:06:23+09:00</sub>

# form_ux Round 2: 4 点への応答

## 1. 可視ラベルの重複問題（`a11y_wcag` の 3.3.2 指摘とあわせて 1 案に絞る）

指摘は妥当。現状の Round 1 案（可視ラベル「検索キーワード」+ プレースホルダ「例: react」）は、`app/page.tsx` の h1「gem-hunter」・導入文「キーワードで GitHub のリポジトリを検索します。」と **意味的に 3 重化** していた（「検索」という語が h1 直下の文脈で 3 回連呼される）。**譲歩して 1 案に絞る**:

| 要素 | 文言 | 役割（重複させない） |
|---|---|---|
| h1 | `gem-hunter` | アプリ名（不変） |
| 導入文（`page.tsx`） | 「キーワードで GitHub のリポジトリを検索します。」 | 1 回だけの操作説明（`§4.4` 初期状態の教育的文言と同枠。現状維持） |
| **可視ラベル** | **「キーワード」**（「検索」を落とす） | フィールド名のみ。導入文で「検索」は既出のため反復しない |
| プレースホルダ | 「例: react, vue, rust」等の **具体例のみ** | ラベルの言い換えではなく入力形式のヒント（NN/g の「プレースホルダをラベル代替にしない」原則に従い、ラベルと同義文にしない） |
| ボタン | 「検索」 | 動詞（アクション）はここでのみ使う |

これで `3.3.2`（全ユーザーへの可視提示）を満たしつつ、同一意味の文言を並べる冗長性を解消する。**確定案として上表を採用。**

## 2. 入力欄とボタンの高さ — 統一に賛成、`mobile_touch` と `design_system` は対立していない

`mobile_touch` の「無条件 44px」と、私の `h-11`(44px) は数値として完全一致している。`design_system` の 3 段トークン（`--spacing-control-sm`=36px / `-md`=44px / `-lg`=48px）も、**検索フォームが使う `default` は `control-md`=44px** であり、`mobile_touch` の 44px 提案と数値が一致する（36px は将来のアイコンボタン等、48px は未使用の予備）。**3 者は対立していない**——「3 段トークンを用意しておくが、検索フォームの入力欄・ボタンはどちらも `control-md`(44px) を使う」で一本化できる。

**入力欄とボタンで高さを変えるべきか**: **同一にすべき**（44px で揃える）。理由: (a) `search-form.tsx` は横並び配置（`sm:` 以上）であり、高さが異なると視覚的なベースラインがズレて「揃っていない」印象を与える（フォームUXの基本原則）、(b) `mobile_touch` の Fitts's law の議論はボタンだけでなく入力欄のタップ／フォーカス操作にも同様に当てはまる、(c) `design_system` の差分案（`input.tsx`/`button.tsx` 双方を `h-control-md` に統一）と実装上も整合する。

**訂正**: Round 1 の実装例で `h-11` を生の Tailwind クラスとして書いたが、`design_system` の争点B決定（`(iv)+(i)`: `@theme` トークン化）に従い、**`h-11` ではなく `h-control-md` を使うべき**。争点C担当としてこの点は `design_system` の決定に完全に譲る。

## 3. 640px 縦積み切替の根拠 — 部分的に譲歩する

正直に認める: **「640px」という具体値そのものを裏付ける一次情報は持っていない**。Tailwind の既定 `sm` を流用した提案であり、これは実装上の便宜であって研究的根拠ではない。

一方で「縦積みにすべきか、横並びのまま入力欄を広く取り小さいボタンを右に置くか」という設計判断自体には、**`a11y_wcag` が既に立てている 1.4.10 Reflow の判定基準点（320 CSS px 幅）** を使って定量的に答えられる:

- USWDS の入力幅目安「27 文字」（約 27ch ≈ 216px、`ch` 単位はフォント依存だが概算）
- 争点2 で確定した高さ 44px のボタン（幅は「検索」2 文字 + `px-6` 相当のパディングで概算 90〜100px）
- 両者を `gap-2`(8px) で横並びにすると **314〜324px**

`page.tsx` の `px-4`（左右合計 32px）を引いた実効幅は、1.4.10 の判定基準点 320px の端末では **288px** しかなく、**横並びのまま入力欄を USWDS 目安幅・ボタンを 44px 確保すると 320px 端末で収まらない**（実測ではなく概算だが、既存プロジェクト制約である `NFR-15`/1.4.10 と同じ判定点を使った試算である点は一次情報に基づく）。「ボタンを小さいまま右に置く」代替案は、争点2で確定した「ボタンも 44px 必須」という結論と矛盾するため採用できない。

**結論（修正版）**: ブレークポイントの具体値は「`sm`(640px) だから」ではなく、**「1.4.10 の判定基準点である 320px 幅で横並びが数学的に破綻するため縦積みが必要」** という理由に差し替える。`sm:flex-row` という実装自体は、320px ちょうどではなく安全マージンを取った実用的な閾値として維持してよいが、根拠の主張は上記に修正する。

## 4. `type="search"` のネイティブクリアボタン — 過大評価を訂正

WebSearch で確認（[caniuse: -webkit-search-cancel-button](https://caniuse.com/mdn-css_selectors_-webkit-search-cancel-button)、取得日 2026-08-19 JST）: `::-webkit-search-cancel-button` は **WebKit/Blink 限定の非標準機能**。Safari（iOS/macOS）・Chrome（Android/デスクトップ、Blink ベース）では値が非空のときに表示されるが、**Firefox は非対応**。仕様書に載らない非標準機能であるため、将来的に変更・削除される可能性がある。

Round 1 で「JS なし前提での実効性」を暗に過大評価していた点を訂正する: **モバイルでの実効性は「Safari(iOS)・Chrome(Android) では効くが、保証された機能ではない」という限定的なものであり、UX 設計の前提にしてはならない**。JS なしで確実にクリア機能を提供する手段は存在しないため、**「クリアボタンは環境依存のボーナスであり、設計上は無いものとして扱う」** と修正する。実務上の代替は「入力欄を長押し/全選択して打ち直す」「ブラウザバック」等のユーザー任せになるが、これは JS なし GET フォームの制約上受け入れるほかない（スコープ外）。

## Sources（Round 2 追加分）
- https://caniuse.com/mdn-css_selectors_-webkit-search-cancel-button（取得日 2026-08-19 JST）

### `tooling_scout` — 反論
<sub>2026-08-19T10:07:07+09:00</sub>

## 1. 自己反論: Playwright + axe-core 導入はこの Issue にオーバースコープではないか（部分的に譲歩）

`docs/rules/sprint-development-rules.md` SD-2 は「`SP-1`〜`SP-3` はテスト基盤未整備につき『テストを書ける対象から書く』に緩和、CI 必須化は `SP-4` から」と定めており、本 Issue（フォーム高さ修正）は spec の一次観測に `SP-1 / PR #58` とある通りこの緩和期間に該当する。R1 で自分が提案した「`@playwright/test` + `@axe-core/playwright` を導入し `treosh/lighthouse-ci-action` を GitHub Actions に配線する」は、**2 つの異質な作業を 1 つに束ねていた** 点を認め、切り分ける。

- **今すぐ・スコープ内として維持**: `@playwright/test` を devDependencies に追加し、**この PR が固定する具体的な回帰**（検索入力欄・送信ボタンの実測高さが確定した基準値以上であること）だけを検証する **単一テストファイル** を書く。これは CP-1 の「自分がこのタスクで変更したコードパス上の壊れは即修正・即テスト化する」に該当し、SD-2 緩和期間の「書ける対象から書く」の範囲内。CI への blocking gate 化は不要（ローカル `npx playwright test` で十分、`SP-4` で正式に CI へ昇格）。
- **後日・別 Issue に切り出す（訂正）**: `treosh/lighthouse-ci-action` の GitHub Actions 配線は、ワークフロー全体設計・閾値設定・Cloudflare プレビュー URL との結線（§4 で詳述）を伴うインフラタスクであり、フォーム高さ修正の PR に混ぜるとスコープ逸脱になる。**「今すぐ」から撤回し「条件付きで後日（`SP-4` または専用 Issue）」に格下げする。** ただし `ui-ux-guidelines.md` §9 が実装済みであるかのように Lighthouse CI を前提記述している点自体は事実誤認なので、争点 D の decision には「§9 の記述は "計画" であり "実装済み" ではない」と明記すべきだと lead に申し送る。

## 2. `design_system` への確認: `h-8` ハードコード直値を機械的に禁止するツールは実在するか → 実在するが v4 対応が未成熟、`design_system` の「grep warning・exit 1 にしない」判断を支持する

コミュニティ製 `eslint-plugin-tailwindcss`（francoismassart/eslint-plugin-tailwindcss）に `no-arbitrary-value` / `no-custom-classname` ルールが存在し、後者は `h-8` のような直値クラスをカスタムトークン以外禁止する設定が理論上可能（[GitHub](https://github.com/francoismassart/eslint-plugin-tailwindcss)・取得日 2026-08-19 JST）。しかし公式 README 自身が「Tailwind CSS v4 対応は部分的（beta チャンネル）で `no-contradicting-classname` 等に false positive が出うる」と明記している（[出典同上](https://www.npmjs.com/package/eslint-plugin-tailwindcss)）。本プロジェクトは Tailwind v4 + `@theme` トークン運用のため、**今この lint を CI の強制ゲートにすると false positive で無関係な PR を止めるリスクが高い**。したがって `design_system` が R1 で出した「新規トークン置換ルールは PR レビュー時の目視チェック項目に留め、機械検証は warning 止まり（exit 1 にしない）」という判断に **賛成・支持** する。公式のシンプルな解（shadcn 側がトークン継承を自動化する仕組み）は存在しない、という `design_system` の主張も自分の検索で追加反証は出なかったので確認が取れた。

## 3. `a11y_wcag` への回答: フォーカスリングのコントラスト（1.4.11）は axe-core で自動検出できない（確認・重要な穴）

Deque University の axe 4.11 ルール一覧を確認した結果、**1.4.11 Non-text Contrast を検出する専用ルールは axe-core に存在しない**（`color-contrast` / `color-contrast-enhanced` はテキストのみが対象。取得日 2026-08-19 JST）。W3C の ACT 実装表でも axe-core は非テキストコントラストの完全自動判定を「manual」扱いとしている。**`a11y_wcag` が最重要違反候補として挙げたフォーカスリング問題は、axe-core 導入だけでは CI で捉えられない** ことを明確に認める。

現実的な機械検証の代替案（争点 D への追加提案）: 争点 1 で導入する Playwright テストの中で、`page.evaluate()` で `getComputedStyle` から実際に描画された `--ring` の合成色を取得し、`wcag-contrast`（npm・軽量ライブラリ）でコントラスト比を計算して `expect(ratio).toBeGreaterThanOrEqual(3)` を書くことは技術的に可能（Playwright はブラウザで実描画するため oklch → 実際の合成 RGB を正確に取得できる。`a11y_wcag` が R1 で行った手計算より高精度になる）。これは axe-core の守備範囲外を Playwright 側で埋める具体案であり、争点 1 の「単一テストファイル」に含めてよい規模（`--ring` の実装修正 1 箇所 + アサーション 1 本）。ただしこれも `SP-1` 緩和期間の「書ける対象から書く」に収まる最小追加として提案するのであって、包括的なコントラスト検証基盤の新設ではない。

## 4. Lighthouse CI と Cloudflare Workers プレビュー URL: 技術的には結線可能だが今は未実装（§1 の格下げと整合）

`.github/workflows/deploy-preview.yml` を確認した。`wrangler versions upload --preview-alias "pr-${PR_NUMBER}"` の標準出力から URL を正規表現で抜き出し、`steps.upload.outputs.url` として **既に GITHUB_OUTPUT に格納済み**（47〜64 行目）。したがって `treosh/lighthouse-ci-action` を同一ジョブの `upload` ステップ直後に追加し、`urls: ${{ steps.upload.outputs.url }}` を渡せば技術的には動く形にできる（プレビュー URL が PR ごとに変わる問題への解は "同一ワークフロー内で output を橋渡しする" というだけで、追加のインフラは不要）。**「動く形になっているか」への回答は「配線方法は特定済みだが、当該ワークフローへの追加はまだ行われていない」**。§1 の格下げ判断と整合させ、争点 D の decision には「配線先・手順は本ラウンドで確定済み（`deploy-preview.yml` の `upload` ステップ直後に 1 ステップ追加）、実装は SP-4 または専用 `type:improvement` Issue に切り出す」と明記することを lead に提案する。

### `a11y_wcag` — 反論
<sub>2026-08-19T10:07:29+09:00</sub>

## a11y_wcag: Round 2 反論・譲歩

### 1. mobile_touch への応答 — 「AA適合=十分」は維持できない。44px に一本化する

`mobile_touch` の指摘は正しい。**Round 1 の自分の論法を訂正する**: 「2.5.8 AA は 32px で満たす」という命題自体は事実として変わらないが、これを「だから 32px で十分」という含意で使ったのは誤りだった。WCAG 適合は **法的下限（compliance floor）** であり、**使いやすさ（usability optimum）を保証しない**。両者は別の物差しであり、ユーザーが「操作性が悪い」と報告した事実は使いやすさの物差しの上で起きている。適合の物差しだけでこれを退けることはできない。

**最終数値を 1 つに絞る**: `mobile_touch` の 44px（`h-11`）に **a11y レンズとしても合意し、40〜44px というレンジ表記は取り下げる**。根拠を a11y 側から補強すると、44px は 2.4.13 Focus Appearance（AAA・`4h+4w` の面積式）を余裕を持って満たせる下限でもあり、Round 1 で自分が挙げた 2.5.5（AAA・44px）と mobile_touch の Apple HIG/Material 3 根拠が同じ数値に収束している。**この一致を偶然ではなく「業界の実用ラインが概ね 44px に収斂している」という強いシグナルとして扱うべき**。§7.5 の改題案（Round 1 の 4 番目の提案）は「2.5.8=AA必須下限 24px」「44px=実用推奨値（AAA整合・複数一次情報が独立に一致）」という **2段書き** のまま維持するが、「推奨」の欄は 40〜44px のレンジではなく **44px 単一値** に修正する。

### 2. design_system への回答 — 測定根拠の明示（誤測定なら結論変更もあり得るため精査した）

**基準色**: `--background`（ライト `oklch(1 0 0)`=白、ダーク `oklch(0.145 0 0)`）。理由は 1.4.11 の「adjacent colors」定義（コンポーネントに隣接する色）に従うため。`focus-visible:ring-3` は `box-shadow` としてコンポーネント外側に描画されるリングであり、`Input` は `bg-transparent`（実質ページ背景色）、`Button` の `bg-primary` はリング自体の外側描画には関与しない（リングは要素の境界の **外** に出るため、隣接色はページ背景が正しい）。この点に異論があれば design_system の実装知見で訂正してほしい。

**換算方法**: (1) `oklch(L C H)` → OKLab → 線形 sRGB（CSS Color 4 の標準変換行列）→ ガンマ補正で 8bit sRGB。(2) アルファ合成: **2 通りの方法で再計算し、結果が一致することを確認した**——① 素朴な sRGB ガンマ空間での 8bit 線形補間（Round 1 の方法）: 光 ≈ rgb(208,208,208) → 白背景比 **1.54:1**。② Tailwind v4 の `color-mix()` が実際に採用する可能性が高い **OKLab 空間での知覚的合成**（`L` 値を直接 50:50 で混合してから sRGB化）: 光 ≈ rgb(207,207,207) → 白背景比 **1.56:1**。ダークモードも同様に両方式で **1.77〜1.87:1**。**どちらの合成方式でも 3:1 の半分程度にしかならず、結論（1.4.11 未達）は合成方式の選択に依存しない**。ただし実際に Tailwind がどちらの color space で `/50` を解決しているかはビルド後の CSS（`ring-color` の計算値）を実機で確認していない自己申告の限界であり、**最終判定は実装 PR で `getComputedStyle` の実測値を axe DevTools 等で再確認することを条件とする**（Round 1 で既に明記済みの留保を維持）。

### 3. form_ux への回答 — 可視ラベルは解決するが、現状 `sr-only` は「適合違反」ではなく「設計上の劣後」だった（Round 1 の記述を訂正）

`labels-or-instructions.html` の **Sufficient Techniques / Failures** を再確認した。**視覚的に非表示なラベル（`display:none` ではなく clip 技法＝`sr-only`）を明示的に不十分とする Failure 技法は存在しない**。H44（label 要素での関連付け）は可視性を要求しておらず、現状の `<label htmlFor="q" className="sr-only">` は **技術的な十分基準（sufficient technique）を満たしており、3.3.2 の適合違反と断定することはできない**。

Round 1 で「3.3.2 の意図と衝突する」と書いたのは、Understanding 文書の **Intent セクション**（規範的な SC 本文ではなく解説）の記述を根拠にしたものであり、これは **確定的な適合違反の主張ではなく、W3C 自身が推奨する設計方針からの逸脱という「設計上の劣後」に位置づけを訂正する**。したがって:

- `form_ux` の可視ラベル案は 3.3.2 を「不適合から適合に直す」ものではなく、**「適合はしているが弱い実装」を「意図に忠実な強い実装」に引き上げるもの**。
- a11y レンズとしては `form_ux` の可視ラベル案を **全面的に支持する**（Intent 準拠・NN/g のプレースホルダ弊害の知見とも整合）が、§7 への追記文言は「`sr-only` は 3.3.2 違反」ではなく「**`sr-only` は 3.3.2 の技術的最低ラインは満たすが、可視ラベルが推奨される**」という正確な強度で書く（Round 1 の提案 5 番を訂正）。

### 4. tooling_scout への回答 — 自分が挙げた SC のうち自動検出できる/できないの線引き

| SC | axe-core 標準ルールで自動検出 | Playwright 自作アサーションで検出可能 | 検出不可（要目視/専門判断） |
|---|---|---|---|
| 2.5.8 Target Size (Minimum) | △（`target-size` ルールはあるが重なり判定は「要レビュー」扱いになりやすい） | ○（`boundingBox()` で px 実測・閾値比較は確実） | — |
| 2.5.5 Target Size (Enhanced) | ×（axe は AAA のこのルールを既定で持たない） | ○（同上、閾値を 44px にするだけ） | — |
| 2.5.3 Label in Name | ○（`label-content-name-mismatch` ルールで自動検出） | — | — |
| 3.3.2 Labels or Instructions | △（ラベルの **存在** は `label`/`aria-*` 系ルールで検出可。ラベルが **可視かどうか** は axe も Playwright の単純アサーションも判定基準を持たない） | △（`getComputedStyle` で `clip`/`position:absolute` パターンを検出する自作スクリプトなら可能だが一般解ではない） | 「可視ラベルが望ましい」という **設計判断そのもの** は自動化不可（3 番の議論の通り） |
| 1.4.11 Non-text Contrast（今回発見したフォーカスリング問題） | **×（axe-core の `color-contrast` 系ルールはテキストが対象で、box-shadow によるフォーカスリングのような非テキスト UI 要素の隣接色コントラストは標準ルールでは検出しない）** | △（`getComputedStyle` で focus 時の `box-shadow` 値をパースし、算出した rgba を今回と同じ計算式でコントラスト判定する **自作スクリプトを書けば可能**。汎用ルールが無いだけで技術的に不可能ではない） | — |
| 1.4.10 Reflow | ×（ズームシミュレーションは axe の対象外） | ○（`page.setViewportSize({width:320,...})` 後に `scrollWidth <= clientWidth` を確認すれば機械判定できる） | — |
| 2.4.11 Focus Not Obscured / 2.4.13 Focus Appearance | ×（どちらも axe-core に相当ルールなし） | △（2.4.11 は sticky header の座標と focus 要素の座標を比較する自作スクリプトで部分的に可能。2.4.13 の面積式・コントラスト差はフォーカス時/非フォーカス時のスクリーンショット差分か box-shadow 解析が必要で実装コストが高い） | 実質的に手動チェックリスト（§7.7）に残すのが現実的 |

**線引きの結論**: `tooling_scout` の「Playwright + axe-core」提案のうち、**axe-core が担えるのは 2.5.3 と（ラベル存在レベルの）3.3.2 のみ**。**今回最も重い指摘だった 1.4.11（フォーカスリングのコントラスト）は axe-core の対象外** であり、CI で機械的に守らせるには **`box-shadow` の computed style を解析する自作 Playwright スクリプト** が別途必要になる（既存提案の `boundingBox()` アサーションの隣に追加する形）。§7.7 の手動チェックリストから「フォーカスリングのコントラスト比を実測した」の項目は、**自動化提案が採用されるまで削除しない**（tooling_scout の判定に対する追加要望）。

---
**まとめ**: 争点1は 44px へ一本化（mobile_touch に譲歩）。争点2は 2 通りの合成方式で再計算し結論は変わらないことを確認（design_system への根拠開示）。争点3は「適合違反」から「設計上の劣後」へ自説を訂正しつつ form_ux 案を支持（concession）。争点4は axe-core の守備範囲外（特に 1.4.11）を明示し、tooling_scout の提案に自作スクリプトの追加を要望した。

### `design_system` — 反論
<sub>2026-08-19T10:08:43+09:00</sub>

## 1. `tooling_scout`/コーディネーターの指摘への応答: 案 (i) の upstream 差分管理と機械検知

指摘は妥当。「`ui-ux-guidelines.md` §1 への目視レビュー項目追記」だけでは、私が (ii)(iii) を却下した理由（**記憶依存で再発を防げない**）と **同じ弱点** を抱える。ここは訂正する。

ただし (ii)/(iii) と本件には **構造的な違い** があり、その違いを使えば機械検知は可能だと考える。

- (ii)/(iii) が防げない理由は「呼び出し箇所が **アプリ全体に無制限に散らばる**」ため（コンポーネント呼び出しは何百箇所にでも増えうる）。
- 一方 shadcn の既定値問題は **`src/ui/components/*.tsx` という有限かつ列挙可能なファイル集合** にしか発生しない（`shadcn add` が生成するのはこのディレクトリだけ）。しかも cva の `size` variant は `default:` キーという **構文的に特定できる位置** にある。

**具体的な機械チェック案**（`tools/check_control_token_usage.py` として新規追加。既存の `check_cjk_markdown.py`/`self_review_check.py` と同系統の pre-PR チェックに合流させる）:

```python
# src/ui/components/*.tsx の cva size variants から `default:` エントリの文字列を抽出し、
# h-6 / h-7 / h-8 / size-6 / size-7 / size-8 等の生の高さ値を含み、
# かつ "control-" を含まない場合に fail（xs/sm は対象外・意図的な密なバリアントのため許容）。
# Input のような単一コンポーネントは cn(...) 第一引数の先頭トークンを同様にチェックする。
```

- これは「新規追加されたコンポーネントファイルの `default` サイズが `control-*` トークン経由か」だけを見る **狭い** チェックであり、(ii)/(iii) のような無制限サーフェスの検知を試みているわけではない。**exit 1 のハードゲート** にできる（`xs`/`sm` は除外ルールが明確なので誤検知しにくい）。
- 補足として `git diff --name-only` で `src/ui/components/` 配下の新規ファイルに絞れば、`shadcn add` 直後の 1 回だけ走らせれば十分（毎回全ファイルを舐める必要はない）。

**結論**: 「運用（目視）」から「機械ゲート」へ格上げする。r1 で書いた §1 追記は **残しつつ**（人間が見落とした場合の二重防御として）、主防御はこのスクリプトにする。r1 の提案を撤回はしないが、`tooling_scout` の指摘どおり単独では不十分だったことは認める。

## 2. `a11y_wcag` の iPad Safari オートズーム指摘への応答: フォントサイズトークン化は不要、`md:text-sm` を削除する

指摘を **全面的に受け入れる**。r1 は高さのみに注目しトークン設計の対象を狭めすぎた。

ただし対処は「フォントサイズの新規トークン化」ではない。理由: 16px は既に **Tailwind 既定の `text-base` ユーティリティ** であり、かつガイドライン §2.3 の 5 段階タイポスケール（12/14/16/20/24）に **既に含まれている値**。高さ（`h-8`）の場合と違い、shadcn の既定値と衝突する新しい値が必要なわけではなく、**単に `md:` での上書きを消せば済む**。新トークンを増やすとむしろ「なぜ 2 つ目のサイズ体系があるのか」を混乱させる（YAGNI 観点でも不要）。

**具体的差分**（`src/ui/components/input.tsx` 11 行目、r1 で示した `h-control-md` 化と合わせて適用）:

```diff
- 'h-8 w-full min-w-0 rounded-lg border border-input bg-transparent px-2.5 py-1 text-base transition-colors outline-none ... md:text-sm dark:bg-input/30 ...'
+ 'h-control-md w-full min-w-0 rounded-lg border border-input bg-transparent px-3 py-1 text-base transition-colors outline-none ... dark:bg-input/30 ...'
```

（`text-base` はブレークポイント無条件で維持、`md:text-sm` を除去。`file:text-sm` はファイル選択ボタンの内部テキストで編集可能フィールド本体ではないため対象外＝オートズーム要因にならない）。

**範囲の限定**: これは `Input`（テキスト編集可能フィールド）専用の対処。`Button` の `text-sm`（14px・タイポスケール内）はフォーカスでキャレットが立たない要素なのでオートズーム対象外、変更不要。`a11y_wcag` の指摘通り「ブレークポイントを問わず 16px 未満にしない」を §7 に明文化する提案にも賛成（design_system としては「input.tsx が実例」として PR に添える）。

## 3. `mobile_touch`/`form_ux` 収斂値と 4px グリッド表記の齟齬への応答: ガイドライン側を改訂する

**36/44/48px は §2.3 が列挙する `4 / 8 / 12 / 16 / 24 / 32` には無いが、4 の倍数ではあるので数学的には矛盾しない（36=4×9, 44=4×11, 48=4×12）。** 問題は「ガイドラインの列挙が言葉足らずだった」ことにある。

現行 §2.3 の「スペーシング」節は文脈上 **margin/gap/padding のレイアウト間隔** を指しており、**コントロールの視覚的高さ** という別カテゴリの値を暗に除外していない代わりに明記もしていない（この暗黙の前提のズレが、そもそも h-8 を誰も疑わなかった一因＝今回の根本原因そのものと同型）。**値を 4px グリッド内に収めるという原則自体は変えず、列挙を拡張する** のが正しい対処であり、ガイドライン本文の改訂を提案する。

**具体的差分**（`docs/03_design/ui-ux/ui-ux-guidelines.md` §2.3、既存の「スペーシング」箇条の直後に新設）:

```diff
  - **スペーシング**: 4px グリッドに載せる（4 / 8 / 12 / 16 / 24 / 32）。任意の値を書かない
+ - **コントロール高さ**: 4px グリッドに載せる専用スケール（36 / 44 / 48px）。主要な操作系コンポーネント（検索入力・送信ボタン等）の既定は `--spacing-control-{sm,md,lg}`（`app/globals.css`）を参照し、生の `h-*` 数値を直書きしない
```

`mobile_touch`/`a11y_wcag` が収斂した 44px を採用する前提であれば、r1 で提示した `--spacing-control-md: calc(var(--spacing) * 11)` (=44px) はそのまま使える。r1 の値（36/44/48）は変更不要、**ガイドライン側の記述を追随させる** というのが design_system としての最終回答。

## 4. `a11y_wcag` のフォーカスリング・コントラスト不足への応答: `--ring` の具体的な改訂案

これはトークンの持ち場なので担当として具体案を出す。ただし **oklch→sRGB の精密な数値は自前計算では確定できない**（`a11y_wcag` 自身も同じ注記を付けている）。ここでは「方向性 + 実装パターン」を確定させ、**マージ前に axe DevTools / Colour Contrast Analyser での実測を必須とする** 運用を前提にする（数値を断定しない）。

**方針**: (a) `--ring` の L 値を暗背景/明背景それぞれで離す、(b) `ring-ring/50` の半透明依存を弱める（アルファを上げる）— 2 つを併用してどちらか一方の精度誤差を吸収する。

**具体差分**（`app/globals.css`）:

```diff
  :root {
    ...
-   --ring: oklch(0.708 0 0);
+   --ring: oklch(0.5 0 0);   /* 現状より暗く。/50 のアルファ込みで 3:1 を狙う。要実測 */
    ...
  }
  .dark {
    ...
-   --ring: oklch(0.556 0 0);
+   --ring: oklch(0.78 0 0);  /* 現状より明るく。背景 oklch(0.145) との差を拡大。要実測 */
    ...
  }
```

**具体差分**（`src/ui/components/input.tsx` と `button.tsx` の両方、`focus-visible:ring-3 ring-ring/50` → `focus-visible:ring-3 ring-ring/70` 相当にアルファを引き上げ。両ファイルで文字列は同一箇所なので `sd` 一括置換可）:

```diff
- focus-visible:ring-3 ring-ring/50
+ focus-visible:ring-3 ring-ring/70
```

**次のアクション**（lead への申し送り）: この 2 値（`--ring` の L・アルファ %）は実装 PR で axe DevTools 実測してから確定する。**「3:1 を満たす」という受け入れ条件だけを先に確定し、具体数値は実装時の実測ループに委ねる** のが誠実な進め方（未実測の数値を確定値として主張しない）。`--ring` は Input/Button 両方が共有する 1 トークンなので、**1 箇所の修正で両コンポーネントに波及する** のが今回のトークン化方針の副産物としての利点（争点 B の設計判断がここでも効いている）。

## ラウンド 3

### `lead` — 合意
<sub>2026-08-19T10:09:29+09:00</sub>

## 合意に達した点

1. **数値は 44px に完全収束した**。`mobile_touch`（Apple HIG 44pt / Fitts の法則）・`form_ux`（USWDS の入力幅目安との整合）・`design_system`（`--spacing-control-md`）・`a11y_wcag`（Round 2 で 40〜44px のレンジを撤回し 44px に一本化）の 4 レンズが独立の根拠から同一値へ到達した。
2. **「WCAG AA 適合＝十分」は棄却された**。`a11y_wcag` が自ら訂正したとおり、2.5.8（AA・24px）は法的下限であり使いやすさを保証しない。ユーザーの体感報告は適合の物差しの上ではなく使いやすさの物差しの上にある。
3. **入力欄とボタンは同一高さ（44px）で揃える**（横並び時のベースライン整合・両者ともタップ対象）。
4. **`pointer: coarse` による出し分けは不採用**。トークン化しても出し分けロジック自体のコストは下がらず、ハイブリッド機での判定不確実性も残る（`mobile_touch` の反論を `design_system` が受け入れ）。
5. **`sr-only` ラベルは「3.3.2 違反」ではなく「設計上の劣後」**（`a11y_wcag` が Round 2 で自説を訂正）。ただし可視ラベルへの変更は 4 レンズとも支持。
6. **フォーカスリングのコントラスト不足（1.4.11・AA）が本議論で発見された最も重い問題**。2 通りの色合成方式で再計算しても 3:1 の約半分（ライト 1.54〜1.56:1 / ダーク 1.77〜1.87:1）で結論は変わらない。
7. **axe-core はフォーカスリングのコントラスト（1.4.11）を検出できない**（`tooling_scout` が Deque のルール一覧で確認）。「axe を入れれば a11y が守れる」は誤り。

## 議論を経て変わった主張（相互検証が効いた点）

| 主張者 | Round 1 | Round 2 での変化 |
|---|---|---|
| `a11y_wcag` | 「32px でも AA 適合済み」「`sr-only` は 3.3.2 の意図不適合」 | 44px に一本化して譲歩。`sr-only` は「適合違反ではなく設計上の劣後」へ位置づけを訂正 |
| `form_ux` | 生の `h-11`・可視ラベル「検索キーワード」・640px の根拠 | `h-control-md` トークンへ差し替え。ラベルを「キーワード」に絞り h1・導入文との三重化を解消。640px は一次情報の根拠なしと認め、1.4.10 の 320px 基準点での試算に差し替え。`type=search` のクリアボタンは非標準（Firefox 非対応）と訂正し設計前提から外す |
| `design_system` | 再発防止は「目視レビュー項目の追記」 | 自らの弱点（記憶依存）を認め `grep` による機械検知へ差し替え。`text-base md:text-sm` は `a11y_wcag` に全面譲歩して 16px 固定へ |
| `tooling_scout` | Playwright + axe-core + Lighthouse CI を「今すぐ」 | 束ねすぎと自己反論。Lighthouse CI 配線は撤回して別 Issue へ格下げ |
| `mobile_touch` | 44px 無条件 | 維持。ただし縦積み時の間隔を `gap-2`→`gap-3` に補強する追加提案 |

## 残った対立

なし。争点 A〜E すべてで収束した。`tooling_scout` の Playwright 導入スコープのみ lead 判断で確定させる（下記 verdict D-2）。

### `lead` — 判定
<sub>2026-08-19T10:11:20+09:00</sub>

{
  "decisions": [
    {
      "issue": "A: 主要コントロールの最小高さ",
      "design": "検索入力・送信ボタンの高さを 44px に統一し、ブレークポイントによる出し分けをしない。24px（WCAG 2.5.8 AA）は法的下限であり実用基準として採用しない。pointer: coarse による出し分けは不採用",
      "evidence": [
        "https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html",
        "https://www.w3.org/WAI/WCAG22/Understanding/target-size-enhanced.html",
        "https://m3.material.io/foundations/designing/structure",
        "https://developer.mozilla.org/en-US/docs/Web/CSS/@media/pointer"
      ],
      "artifacts": ["app/globals.css（改修）", "src/ui/components/input.tsx（改修）", "src/ui/components/button.tsx（改修）"],
      "rejected": "40px（4px グリッドには乗るがどの一次情報とも一致しない中途半端な値）/ 48px（lg=36px との差が開きすぎる）/ 見えないパディングでヒットエリアだけ拡張する案（視覚的な小ささという体感報告に対応しない・隣接コントロールとヒットエリアが重なる）/ pointer: coarse 出し分け（ハイブリッド機で any-pointer が同時に真になり判定が不確実。トークン化しても分岐ロジックのコストは下がらない）"
    },
    {
      "issue": "B: shadcn radix-nova の h-8 既定の扱い",
      "design": "(iv) @theme に --spacing-control-{sm,md,lg} = 36/44/48px を定義し、(i) input.tsx / button.tsx の既定をそのトークンで書き換える併用案。呼び出し側の className 上書き（iii）と size バリアント運用（ii）は記憶依存で再発を防げないため不採用。再発防止の主防御は機械チェック（src/ui/components/*.tsx の cva default エントリに生の h-6/h-7/h-8/size-8 が入っていないか）とし、ガイドラインへのチェック項目追記は二重防御として併置する",
      "evidence": [
        "https://x.com/shadcn/status/1999530419125981676",
        "https://tailwindcss.com/docs/theme",
        "https://tailwindcss.com/docs/height",
        "https://github.com/shadcn-ui/ui/discussions/7170"
      ],
      "artifacts": ["app/globals.css（改修）", "src/ui/components/input.tsx（改修）", "src/ui/components/button.tsx（改修）", "tools/check_control_token_usage.py（新規）"],
      "rejected": "呼び出し側 className 上書き / size バリアントの都度選択 / eslint-plugin-tailwindcss による強制ゲート（v4 対応が未成熟で false positive のリスク）"
    },
    {
      "issue": "C: 検索フォームの UX",
      "design": "可視ラベル『キーワード』を追加（sr-only を廃止）。プレースホルダは具体例のみ（例: react, vue, rust）に格下げしラベルの言い換えにしない。送信ボタンは『検索』テキストを維持（アイコン単体化しない）。レイアウトは縦積み gap-3 を既定とし sm 以上で横並び gap-2 + items-end。ボタンは w-full sm:w-auto。input の md:text-sm を削除し 16px 固定にする（iPad Safari のオートズーム対策）。type=search のネイティブクリアボタンは非標準（Firefox 非対応）のため設計前提にしない",
      "evidence": [
        "https://www.nngroup.com/articles/form-design-placeholders/",
        "https://design-system.service.gov.uk/components/text-input/",
        "https://designsystem.digital.gov/components/search/",
        "https://www.nngroup.com/articles/magnifying-glass-icon/",
        "https://css-tricks.com/16px-or-larger-text-prevents-ios-form-zoom/",
        "https://caniuse.com/mdn-css_selectors_-webkit-search-cancel-button",
        "https://www.w3.org/WAI/WCAG21/Understanding/reflow.html"
      ],
      "artifacts": ["src/ui/search-form.tsx（改修）", "src/ui/components/input.tsx（改修）"],
      "rejected": "ラベル文言『検索キーワード』（h1・導入文・ボタンと『検索』が三重化する）/ sr-only ラベルの維持（3.3.2 の技術的最低ラインは満たすが W3C の意図に対して劣後）/ 横並び固定（320px 幅で入力欄 27 文字目安 + 44px ボタンが数学的に収まらない）"
    },
    {
      "issue": "D-1: フォーカスリングのコントラスト（本議論で発見した最も重い問題・WCAG 1.4.11 AA）",
      "design": "ring-ring/50 の半透明依存をやめて不透明にし、ライトの --ring を暗くする。合成後のコントラスト比が背景に対し 3:1 以上であることを機械チェックで検証してから確定する（手計算の値を断定しない）",
      "evidence": ["https://www.w3.org/WAI/WCAG21/Understanding/non-text-contrast.html", "https://www.w3.org/WAI/WCAG22/Understanding/focus-appearance.html"],
      "artifacts": ["app/globals.css（改修）", "src/ui/components/input.tsx（改修）", "src/ui/components/button.tsx（改修）", "デザイントークンのコントラスト検証テスト（新規）"],
      "rejected": "アルファ /50 のまま L 値だけ下げる案（ライトで L≈0.29 とほぼ黒になり意匠が破綻する）/ 実測せずに提案値を確定値として採用すること"
    },
    {
      "issue": "D-2: 基準の機械検証（スコープの確定・lead 判断）",
      "design": "本 PR に含めるのは jsdom で成立する検証のみ（コントロールがトークン経由か・フォーカスリングのコントラスト比・フォームのマークアップ）。実レイアウトの高さ実測（Playwright の boundingBox）と axe-core / Lighthouse CI の CI 配線は本 PR に含めず別 Issue に切り出す。理由は SD-2 の緩和期間（SP-1〜SP-3）に当たること、および E2E 基盤の整備は SP-4 の担当であること。ガイドライン §9 が Lighthouse CI を実装済みであるかのように前提記述している点は『計画であり未実装』と明記して訂正する",
      "evidence": ["https://playwright.dev/docs/api/class-locator#locator-bounding-box", "https://dequeuniversity.com/rules/axe/4.11"],
      "artifacts": ["docs/03_design/ui-ux/ui-ux-guidelines.md（改修）", "別 Issue（新規起票）"],
      "rejected": "本 PR で Playwright + axe-core + Lighthouse CI を一括導入する案（tooling_scout 自身が自己反論でスコープ逸脱を認めた）/ vitest + jsdom で高さを実測する案（jsdom は CSS レイアウトエンジンを持たず原理的に不可能）"
    },
    {
      "issue": "E: 導入価値のある Claude Code 資産",
      "design": "今すぐ導入するものは無い（既存の eslint-plugin-jsx-a11y は eslint-config-next 経由で既に有効）。Playwright + @axe-core/playwright は SP-4 の E2E 基盤整備とあわせて導入する。shadcn MCP / Chrome DevTools MCP は必要が生じてから。frontend-design plugin は本プロジェクトの抑制的なデザイントークン制約と方向性が逆のため採らない。判断の根拠と再評価の条件をリサーチ記録に残す",
      "evidence": ["https://ui.shadcn.com/docs/mcp", "https://github.com/ChromeDevTools/chrome-devtools-mcp/", "https://claude.com/plugins/frontend-design"],
      "artifacts": ["docs/03_design/ui-ux/20260819-form-ux-research.md（新規）"],
      "rejected": "Storybook + a11y addon（アプリ規模に対して過剰）/ 新規スキルの作成（既存 code-review / pr-review-watcher の責務と重複する）"
    }
  ],
  "critical": [
    "フォーカスリングのコントラスト不足（WCAG 1.4.11 AA・ライト 約1.5:1 / ダーク 約1.9:1 で 3:1 未達）。本 PR で是正し機械チェックで検証する",
    "input.tsx の md:text-sm により iPad Safari（ビューポート幅 768px）で入力欄タップ時にオートズームが発生する。本 PR で是正する",
    "ガイドライン §9 が Lighthouse CI による判定を前提にしているが .github/workflows/ に該当ワークフローは存在しない（記述と実態の乖離）"
  ],
  "open_questions": []
}
