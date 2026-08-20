# 入力フォームの操作性リサーチ（コントロール高さ・タッチターゲット・フォーム UX）

> 🔴 **数値は後続の議論で改定されている（2026-08-20 追記）**: 本書と `form-ux-sizing-20260819` の議論は
> `--spacing-control-{sm,md,lg}` = **36 / 44 / 48px** を結論としたが、その後の `form-uiux-design-review-20260819`
> で体系ごと見直され、現行は `--size-control-{xs,sm,md,lg,xl}` = **24 / 28 / 32 / 40 / 44px**（`app/globals.css`）である。
> **本書の数値をそのまま実装に引かないこと。** 現行の正本は [`ui-ux-guidelines.md`](./ui-ux-guidelines.md) §2.4。
> 本書は「44px という数値をどの一次情報から導いたか」という **当時の調査過程** を残すための資料として収録している
> （元の PR #75 はクローズ未マージ。ブランチ削除で失われるのを避けるため 2026-08-20 に回収した）。

> **取得日**: 2026-08-19 JST / **議論記録**: `content/discussions/form-ux-sizing-20260819/whiteboard.md`
> **きっかけ**: `SP-1`（PR #58）の検索フォームについて「縦幅が小さく操作性が良くない」というユーザー報告（Issue #62）
> **位置づけ**: 一次情報の調査記録。**実装時に引く規範は `ui-ux-guidelines.md`（SSOT）** に転記済みで、
> 本書は「なぜその数値なのか」を残すための資料。数値が食い違ったらガイドラインが正。

---

## 0. 何が起きていたか（根本原因）

| 層 | 事実 |
|---|---|
| 現象 | 検索入力欄・送信ボタンの高さが 32px（`h-8`）で、タップしづらい |
| 直接原因 | shadcn の `radix-nova` スタイルの既定値をそのまま採用した |
| 中間原因 | `radix-nova` は作者が「**compact layouts 向けの余白削減**」と明言しているスタイルで、想定文脈は管理画面・データ密度優先の UI。一般利用者向けの検索フォームは想定外 |
| 根本原因 | **ガイドラインに「主要コントロールの最小高さ」の基準が存在しなかった**。WCAG 2.2 の下限（24px）しか書かれておらず、ライブラリ既定値を疑う根拠が無かった |

→ 対策は「今回の値を直す」ことではなく、**基準を明文化し、機械的に守らせる** こと。

---

## 1. 結論（実装時に引く数値）

| 項目 | 値 | 適用対象 |
|---|---|---|
| 主要コントロールの高さ | **44px**（`--spacing-control-md`） | 検索入力欄・送信ボタン等、利用者が必ず触る操作系 |
| 既定より大きい導線の高さ | 48px（`--spacing-control-lg`） | `Button` の `size="lg"` |
| フォームコントロールの文字サイズ | **16px 以上（ブレークポイント非依存）** | `input` / `textarea` / `select` |
| フォーカスリングのコントラスト | **背景に対し 3:1 以上** | 全コントロール |
| コントロール間の間隔 | 縦積み 12px / 横並び 8px | 検索フォーム |

**24px（WCAG 2.5.8 AA）は法的下限であって実用基準ではない。** 32px はこの下限を満たすが、
44px 比で面積が約 53%（32²/44²）しかなく、Fitts の法則に照らして到達時間・誤タップ率が悪化する領域にある。

---

## 2. タッチターゲットとコントロール高さ

### 2.1. 一次情報の正確な要件

| 出典 | 数値 | 適合レベル・性質 | 除外条件 |
|---|---|---|---|
| [WCAG 2.2 SC 2.5.8 Target Size (Minimum)](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html) | 24×24 CSS px | **AA（必須）** | Spacing / Equivalent / Inline / User Agent Control / Essential の 5 例外 |
| [WCAG 2.2 SC 2.5.5 Target Size (Enhanced)](https://www.w3.org/WAI/WCAG22/Understanding/target-size-enhanced.html) | 44×44 CSS px | AAA（非必須） | 4 例外（**Spacing 例外が無い** ＝ 間隔での代替が効かない） |
| Apple Human Interface Guidelines | 44×44pt | 推奨（実用基準） | — |
| [Material Design 3](https://m3.material.io/foundations/designing/structure) | 48×48dp（物理約 9mm・推奨 7〜10mm）、標準ボタンは最小高 48dp、ターゲット間 8dp 以上 | 推奨（実用基準） | 視覚サイズとタッチ領域は別概念として扱う |

**44px は、独立した 3 系統（Apple HIG / WCAG AAA / タッチ精度の実測研究）が同じ値に収束している点で強い。**
40px は 4px グリッドには乗るが、どの一次情報とも一致しない中途半端な値のため採らない。

### 2.2. 「ターゲットサイズ」と「見た目の高さ」は別概念 — ただし今回は使えない

WCAG が規定するのはヒットエリアであり、理論上は「視覚 32px + 透明パディングで 44px」でも適合する。
本件でこの回避策を採らない理由は 3 つ:

1. 利用者は **視覚サイズでタップ判断する**。当たり判定だけ広げても「押しにくそう」という体感は解消しない
2. 入力欄とボタンが隣接しているため、透明パディングで拡張すると **互いのヒットエリアが重なる**
3. 今回の報告は「縦幅が小さい」という **見た目に対する指摘** であり、見た目を変えない対処は根本原因に対応しない

### 2.3. ポインタ種別による出し分け（`pointer: coarse`）を採らない理由

- `any-pointer: coarse` と `any-pointer: fine` は **ハイブリッド機（タッチ対応ノート PC 等）で同時に真になりうる**（[MDN](https://developer.mozilla.org/en-US/docs/Web/CSS/@media/pointer)）
- 検索はアプリの中心導線であり、マウス利用時でも大きい方が Fitts の法則上有利。小さくする利得が無い
- 分岐を入れるとテストできない箇所が増える（jsdom はメディア特性を評価しない）

→ **無条件で 44px**。密度が価値を持つ副次コントロールが必要になったら、そのときに小さい段を足す。

---

## 3. フォームと検索 UI のベストプラクティス

### 3.1. ラベルは可視にする

- [NN/g: Placeholders in Form Fields Are Harmful](https://www.nngroup.com/articles/form-design-placeholders/) — プレースホルダをラベル代わりにすると、入力中にヒントが消え、認知負荷が上がる
- [GOV.UK Design System: Text input](https://design-system.service.gov.uk/components/text-input/) — *"All text inputs must have labels, and in most cases the label should be visible."*
- [USWDS: Search](https://designsystem.digital.gov/components/search/) は `sr-only` ラベルを既定にしているが、これは **ヘッダー常設のミニ検索** を想定した実装。本アプリのように検索がページの主コンテンツである場合は前提が異なる

**文言の重複を避ける割り当て**（同じ語を 3 回並べない）:

| 要素 | 文言 | 役割 |
|---|---|---|
| `h1` | `gem-hunter` | アプリ名 |
| 導入文 | キーワードで GitHub のリポジトリを検索します。 | 操作説明（1 回だけ） |
| 可視ラベル | **キーワード** | フィールド名（「検索」を落とす） |
| プレースホルダ | 例: react | 入力例（ラベルの言い換えにしない） |
| 送信ボタン | 検索 | 動作 |

### 3.2. 送信ボタンはテキストを保つ

[NN/g: The Magnifying-Glass Icon in Search Design](https://www.nngroup.com/articles/magnifying-glass-icon/) — 虫眼鏡アイコン単体は認知コストが上がる。
アイコンを足す場合もテキストと併記する。

### 3.3. 縦積みへの切り替えは「収まらないから」

640px（Tailwind の `sm`）という数値そのものに一次情報の根拠は無い。根拠になるのは **WCAG 1.4.10 Reflow の判定基準点である 320px 幅で横並びが成立しない** という事実:

```
入力欄（USWDS の目安 27 文字 ≒ 216px）+ gap 8px + ボタン（「検索」+ padding ≒ 90〜100px）= 314〜324px
ページの左右 padding（px-4 = 32px）を引いた実効幅 = 288px  → 収まらない
```

「ボタンだけ小さくして横並びを保つ」案は、ボタンも 44px 必須という結論と矛盾するため採れない。
よって **狭い画面は縦積み**、`sm` 以上で横並び。縦積み時はボタンを `w-full` にしてタップ領域を最大化する。

### 3.4. `type="search"` のネイティブクリアボタンは設計前提にしない

[`::-webkit-search-cancel-button`](https://caniuse.com/mdn-css_selectors_-webkit-search-cancel-button) は **WebKit / Blink 限定の非標準機能で Firefox は非対応**。
JS を持たない GET フォームでは確実なクリア手段を提供できないため、「環境依存のボーナス」として扱う。

---

## 4. アクセシビリティ（WCAG 2.2）

### 4.1. 該当 SC と現状の判定

| SC | レベル | 要求 | SP-1 時点の判定 |
|---|---|---|---|
| 2.5.8 Target Size (Minimum) | AA | 24×24 CSS px | ✅ 適合（32px）。**ただし適合は使いやすさを保証しない** |
| 2.5.5 Target Size (Enhanced) | AAA | 44×44 CSS px | 未達 → 本対応で達成 |
| [1.4.11 Non-text Contrast](https://www.w3.org/WAI/WCAG21/Understanding/non-text-contrast.html) | **AA** | UI コンポーネントの境界・状態表現が隣接色に対し 3:1 以上 | ❌ **未達**（下記 4.2） |
| [1.4.10 Reflow](https://www.w3.org/WAI/WCAG21/Understanding/reflow.html) | AA | 320px 幅で二次元スクロール不要 | ✅ 適合（可変幅のため） |
| [3.3.2 Labels or Instructions](https://www.w3.org/WAI/WCAG21/Understanding/labels-or-instructions.html) | A | 入力にラベル・説明がある | ✅ 適合（`sr-only` も H44 の十分技法を満たす）。ただし **W3C の意図に対して劣後** しており可視ラベルが推奨 |
| [2.4.13 Focus Appearance](https://www.w3.org/WAI/WCAG22/Understanding/focus-appearance.html) | AAA | 面積 `4h+4w` かつコントラスト差 3:1 | リング幅 3px は面積要件を満たす。コントラストは 1.4.11 と同じ修正で解決 |

> ⚠️ 争点提示時に「2.4.11 Focus Appearance」と書いたのは **旧ドラフトの番号**。確定版では 2.4.13 が Focus Appearance、
> 2.4.11 は Focus Not Obscured (Minimum)（AA）。

### 4.2. 発見した AA 違反: フォーカスリングのコントラスト不足

`focus-visible:ring-3 ring-ring/50` の実効コントラストを、`--ring` の実値から算出した結果:

| モード | `--ring`（修正前） | 背景 | 合成後のコントラスト比 | 判定 |
|---|---|---|---|---|
| ライト | `oklch(0.708 0 0)` | `oklch(1 0 0)` | **約 1.54:1** | ❌ 3:1 未達 |
| ダーク | `oklch(0.556 0 0)` | `oklch(0.145 0 0)` | **約 1.87:1** | ❌ 3:1 未達 |

2 通りの合成方式（sRGB ガンマ空間の線形補間 / OKLab 空間の知覚的合成）で再計算しても結論は変わらなかった。
**原因は半透明（`/50`）依存** であり、不透明にすると同じ `--ring` でもダークは 4.18:1 に改善する。ライトは `--ring` 自体が明るすぎるため値を下げる必要がある。

### 4.3. iOS / iPadOS Safari のオートズーム

フォーカス時の実測フォントサイズが **16px 未満だと WebKit はページを自動ズームする**（[CSS-Tricks](https://css-tricks.com/16px-or-larger-text-prevents-ios-form-zoom/)）。

`input.tsx` は `text-base md:text-sm` だった。スマートフォン（<768px）では 16px なので無害だが、
**iPad Safari の標準ビューポート幅は 768px で `md:` に一致する** ため、iPad で入力欄をタップするとズームが発生する。
「一般的な UI では小さい画面ほど文字を大きく」というレスポンシブの定型が、入力欄には当てはまらない例。

---

## 5. デザインシステムとしての実装（shadcn + Tailwind v4）

### 5.1. 4 案の比較と採用理由

| 案 | 評価 |
|---|---|
| 呼び出し側の `className` で上書き | ❌ 呼び出し箇所が増えるたびに書き忘れる。**今回の事故と同じ失敗モードを温存する** |
| `size` バリアント（`lg` 等）を都度選ぶ | ❌ `default` を使う限り再発する。記憶依存 |
| コンポーネントの既定を書き換える | △ 効果は確実だが、生の px を書くと意図が消え、新規コンポーネントに伝播しない |
| **`@theme` にサイズトークンを定義し、既定がそれを参照する** | ✅ **採用**（既定書き換えと併用） |

### 5.2. Tailwind CSS v4 でのトークン定義

v4 の `height` / `width` などは `--spacing` テーマ変数から **動的に生成** される（[公式](https://tailwindcss.com/docs/height)）。
`--spacing-<name>` として名前付きキーを足すと、**任意値記法なしで `h-<name>` クラスが生成される**（[公式](https://tailwindcss.com/docs/theme)）。

```css
@theme inline {
  --spacing-control-md: calc(var(--spacing) * 11);  /* 44px */
  --spacing-control-lg: calc(var(--spacing) * 12);  /* 48px */
}
```

> 議論の段階では 36px（`control-sm`）を含む 3 段を置く案だったが、セルフレビューで
> **実際に使う箇所が無い段を先回りで定義するのは YAGNI** と指摘され 2 段に絞った。
> 密な文脈が必要になった時点で足す。

実ビルドで `.h-control-md{height:calc(var(--spacing) * 11)}` が生成されることを確認済み。

> `--spacing-*` は `height` / `padding` / `gap` などで共有される名前空間のため、`p-control-md` 等も同時に生成される。
> これは v4 の設計（既存の `h-8` / `p-8` も同じスケールを共有）であり、副作用ではない。

### 5.3. 将来の `shadcn add` に基準を効かせる

**技術的な限界**: shadcn CLI はレジストリのソースをそのまま生成するだけで、プロジェクトの `@theme` トークンを
新規コンポーネントへ自動で参照させる仕組みは無い（[discussion #7170](https://github.com/shadcn-ui/ui/discussions/7170)）。

→ **機械ゲートで補う**。`src/ui/components/*.tsx` は `shadcn add` が生成する有限のファイル集合であり、
既定サイズは cva の `default:` エントリという構文的に特定できる位置にある。この範囲だけを検査すればよい:

- `src/ui/design-tokens.test.ts` が全コンポーネントを走査し、既定サイズに生の `h-<数値>` があれば失敗させる
- `xs` / `sm` / `icon-*` バリアントは密な文脈用として対象外

`eslint-plugin-tailwindcss` の `no-custom-classname` でも同種の検査は可能だが、**Tailwind v4 対応が未成熟で
false positive のリスクがある**ため採らない（テスト側で完結させる）。

---

## 6. 品質を継続担保する道具立て

### 6.1. 自動検証の守備範囲（誤解しやすい）

| 検証したいこと | jsdom + vitest | axe-core | Playwright |
|---|---|---|---|
| 実描画の高さが 44px 以上 | ❌ **原理的に不可**（CSS レイアウトエンジンを持たない） | ❌ | ✅ `boundingBox()` |
| 既定サイズがトークン経由か | ✅ ソース検査 | ❌ | ❌ |
| フォーカスリングのコントラスト | ✅ トークン値からの算出 | ❌ **標準ルールが無い** | △ 自作スクリプトなら可 |
| ラベルと accessible name の一致（2.5.3） | ❌ | ✅ | ✅ |
| 320px 幅でのリフロー | ❌ | ❌ | ✅ ビューポート変更 |

> 🔴 **「axe-core を入れれば a11y が守れる」は誤り**。今回最も重かった 1.4.11（フォーカスリングのコントラスト）は
> axe-core の標準ルールに存在しない（テキストのコントラストのみが対象）。

### 6.2. Claude Code 資産・ツールの採否

| 対象 | 判断 | 理由 |
|---|---|---|
| `eslint-plugin-jsx-a11y` | **導入済み**（追加不要） | `eslint-config-next` の依存として既に有効。「有用そうで実は入っている」典型 |
| `@playwright/test` + `@axe-core/playwright` | **`SP-4` で導入**（別 Issue） | 実描画の高さ実測とリフロー検証には必須。ただし E2E 基盤の整備は `SP-4` の担当で、本対応に混ぜるとスコープが逸れる |
| Lighthouse CI（`treosh/lighthouse-ci-action`） | **別 Issue** | 配線先は特定済み（`deploy-preview.yml` の `upload` ステップが `steps.upload.outputs.url` を既に出力している）。ガイドライン §9 が実装済みのように書いている点は訂正が必要 |
| shadcn 公式 MCP | 必要が生じたら | コンポーネント追加の利便性は上がるが、UI 品質そのものは担保しない |
| Chrome DevTools MCP / Playwright MCP | 必要が生じたら | セッション内の対話的調査には有効だが、CI ゲートのような継続的な担保にはならない |
| `frontend-design` plugin（Anthropic 公式） | **採らない** | 「大胆な配色・個性的なタイポグラフィ」を志向する設計方針で、本プロジェクトの抑制的なトークン制約（タイポスケール 5 段階固定・4px グリッド）と逆向き |
| Storybook + a11y addon | 採らない | アプリ規模に対して過剰 |
| 新規 Agent Skill の作成 | 作らない | 既存の `code-review` / `pr-review-watcher` が「テストが通っているか」を見る流れに乗せれば足りる |

---

## 7. 本対応で適用した変更

| ファイル | 変更 |
|---|---|
| `app/globals.css` | `--spacing-control-{md,lg}`（44/48px）を追加。ライトの `--ring` を `oklch(0.708 0 0)` → `oklch(0.55 0 0)` |
| `src/ui/components/input.tsx` | `h-8` → `h-control-md`、`px-2.5` → `px-3`、`md:text-sm` を削除（16px 固定）、`ring-ring/50` → `ring-ring` |
| `src/ui/components/button.tsx` | `size=default` の `h-8` → `h-control-md`、`size=lg` の `h-9` → `h-control-lg`（既定より小さいのを是正）、`px-2.5` → `px-3`、フォーカス・エラー状態のリングを不透明化 |
| `src/ui/search-form.tsx` | 可視ラベル「キーワード」を追加、プレースホルダを入力例に格下げ、縦積み → `sm:` 横並び、ボタン `w-full sm:w-auto` |
| `src/ui/design-tokens.test.ts` | トークン値・コントラスト比・既定サイズの回帰テスト（新規） |
| `src/ui/search-form.test.tsx` | フォームのマークアップ・レイアウトの回帰テスト（新規） |
| `docs/03_design/ui-ux/ui-ux-guidelines.md` | 上記の基準を規範として転記 |

## 8. 残課題（別 Issue）

- 実描画での高さ実測・リフロー検証・axe-core 統合（`SP-4` の E2E 基盤整備とあわせて）
- Lighthouse CI の GitHub Actions 配線（ガイドライン §9 の記述と実態の乖離解消）
- 彩度のある色（`--destructive` 等）のコントラスト比を機械検証する（現在のテストはグレースケールの `oklch(L 0 0)` のみ算出できる）

## 9. 出典一覧

| 分類 | URL |
|---|---|
| WCAG | [2.5.8](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html) / [2.5.5](https://www.w3.org/WAI/WCAG22/Understanding/target-size-enhanced.html) / [1.4.11](https://www.w3.org/WAI/WCAG21/Understanding/non-text-contrast.html) / [1.4.10](https://www.w3.org/WAI/WCAG21/Understanding/reflow.html) / [3.3.2](https://www.w3.org/WAI/WCAG21/Understanding/labels-or-instructions.html) / [2.4.13](https://www.w3.org/WAI/WCAG22/Understanding/focus-appearance.html) |
| プラットフォーム | [Material Design 3](https://m3.material.io/foundations/designing/structure) / [MDN: pointer](https://developer.mozilla.org/en-US/docs/Web/CSS/@media/pointer) |
| フォーム UX | [NN/g: Placeholders](https://www.nngroup.com/articles/form-design-placeholders/) / [NN/g: Magnifying-Glass Icon](https://www.nngroup.com/articles/magnifying-glass-icon/) / [GOV.UK: Text input](https://design-system.service.gov.uk/components/text-input/) / [USWDS: Search](https://designsystem.digital.gov/components/search/) |
| 実装 | [Tailwind: theme](https://tailwindcss.com/docs/theme) / [Tailwind: height](https://tailwindcss.com/docs/height) / [shadcn discussion #7170](https://github.com/shadcn-ui/ui/discussions/7170) / [caniuse: search-cancel-button](https://caniuse.com/mdn-css_selectors_-webkit-search-cancel-button) / [CSS-Tricks: iOS form zoom](https://css-tricks.com/16px-or-larger-text-prevents-ios-form-zoom/) |
| 検証 | [Playwright: boundingBox](https://playwright.dev/docs/api/class-locator#locator-bounding-box) / [Deque axe rules](https://dequeuniversity.com/rules/axe/4.11) |
