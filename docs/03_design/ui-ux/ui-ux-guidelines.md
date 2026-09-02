# gem-hunter UI/UX ガイドライン（実装指針）

- **版**: 1.0
- **作成日**: 2026-08-17 JST
- **位置づけ**: **UI 実装の判断基準の正本**。スプリント着手時に読む（`sprint-development-rules.md` `SD-4`）
- **根拠**: [UI/UX リサーチ](./20260817-ui-ux-research.md)（出典・未確認項目はそちら）

---

## 0. このドキュメントの使い方

🔴 **本書は「推奨」ではなく「判定できる指示」として書いてある。** 実装が本書に反しているかどうかを、レビューで機械的に判定できる粒度にしてある。曖昧に感じる箇所があればそれは本書の欠陥なので、修正して PR を出す。

| 情報 | 正本 |
|---|---|
| 要件・受け入れ条件 | [`prd.md`](../../02_requirements/prd.md) |
| 技術選定の理由・却下案 | [`docs/adr/`](../../adr) |
| 調査の出典・未確認事項 | [リサーチ](./20260817-ui-ux-research.md) |
| スプリントの回し方 | `docs/rules/sprint-development-rules.md` |

---

## 1. 技術スタック（`TR-5` の決定）

| 層 | 採用 | 補足 |
|---|---|---|
| CSS | **Tailwind CSS v4** | `tailwind.config.js` を作らない。トークンは CSS の `@theme` で定義（v4 は CSS-first） |
| コンポーネント | **shadcn/ui** | 🔴 **`npx shadcn init -b radix` で Radix UI を明示指定する**（既定の Base UI を使わない・[ADR 0001](../../adr/0001-ui-stack.md)） |
| テーマ切替 | **next-themes** | `<html suppressHydrationWarning>` + `<ThemeProvider>`。RSC ツリー最上位に 1 箇所だけ |
| フォント | **next/font**（可変フォント） | 🔴 **`display: 'optional'`**（`swap` はシフトが起きやすい） |
| アイコン | shadcn/ui の既定に従う | 個別 import し、アイコンセット全体を bundle に載せない |

### 🔴 やってはいけないこと

- 🔴 **`-b radix` を付けずに `shadcn init` を実行する**（既定の Base UI が入る。ADR 0001 が名指しした最大の運用リスク。`components.json` の設定を確認して検知する）
- `components.json` の `"rsc"` を `false` にする（`use client` の自動付与制御が効かなくなる）
- `shadcn add` した生成物を読まずにマージする（**`use client` 境界を毎回目視で確認する**・`NFR-3`）
- CSS-in-JS ランタイムを持つライブラリを追加する（`NFR-28`）
- View Transitions API を使う（実験的扱いのため MVP では採らない）

---

## 2. デザイントークン（`NFR-13` の構成確定）

### 2.1. カラートークン（6 系統・**計 10 トークン** × ライト/ダーク）

CSS の `@theme` に以下の **セマンティックな名前** で定義する。生の色名（`slate-700` 等）をコンポーネントに直接書かない（配色変更が全画面に波及するのを防ぐ）。

| トークン | 用途 | コントラスト要件 |
|---|---|---|
| `--color-bg` / `--color-bg-subtle` | ページ背景 / カード背景 | — |
| `--color-fg` | 本文・見出し | **背景に対し 4.5:1 以上** |
| `--color-fg-muted` | メタ情報（言語・star 数・更新日） | 🔴 **背景に対し 4.5:1 以上**（「薄いから免除」はない） |
| `--color-border` | カード枠・区切り線 | UI コンポーネントとして **3:1 以上** |
| `--color-accent` / `--color-accent-fg` | リンク・主ボタン | 背景に対し 4.5:1 以上 |
| `--color-danger` / `--color-danger-fg` | エラー表示 | 4.5:1 以上 |
| `--color-ring` | フォーカスリング | UI コンポーネントとして **3:1 以上**（WCAG 2.2 SC 1.4.11 非テキストコントラスト） |

### 2.2. ✅ 実値の確定結果（`SP-2` の `E-9` で確定・2026-08-19。フォーカスリング行は `#179`〔`SP-10`〕で追加・2026-08-20）

`tools/check_contrast.py`（`run_checks.sh` に組み込み済み）で実測した結果、以下の 10 トークン × ライト/ダーク計 22 値で全ペアがしきい値を満たす。実体は `app/globals.css` の既存 shadcn raw 変数（`--background` / `--muted` / `--foreground` / `--muted-foreground` / `--border` / `--accent` / `--accent-foreground` / `--destructive` / `--destructive-foreground` / `--ring`）に意味づけとして重ね、`@theme inline` で `--color-*` としてエイリアスする（採用方針は下記コラム参照）。

**ライトテーマ**

| トークン | 値（oklch） | 比較先 | 実測コントラスト比 | しきい値 | 判定 |
|---|---|---|---|---|---|
| `--color-bg` | `oklch(1 0 0)` | — | — | — | — |
| `--color-bg-subtle` | `oklch(0.97 0 0)` | — | — | — | — |
| `--color-fg` | `oklch(0.145 0 0)` | vs `--color-bg` | 19.79:1 | 4.5:1 | PASS |
| `--color-fg` | 同上 | vs `--color-bg-subtle` | 18.15:1 | 4.5:1 | PASS |
| `--color-fg-muted` | `oklch(0.5 0 0)`（旧 `0.556` から調整） | vs `--color-bg` | 6.00:1 | 4.5:1 | PASS |
| `--color-fg-muted` | 同上 | vs `--color-bg-subtle` | 5.50:1 | 4.5:1 | PASS |
| `--color-border` | `oklch(0.6 0 0)`（旧 `0.922` から調整） | vs `--color-bg` | 3.95:1 | 3.0:1 | PASS |
| `--color-ring` | `oklch(0.6 0 0)`（旧 `oklch(0.708 0 0)` から調整・`#179`。`--color-border`（ライト）と同値へ揃えた） | vs `--color-bg` | 3.95:1 | 3.0:1 | PASS |
| `--color-ring` | 同上 | vs `--color-bg-subtle` | 3.62:1 | 3.0:1 | PASS |
| `--color-accent` | `oklch(0.42 0.14 250)`（旧 `oklch(0.97 0 0)` から調整。グレーではなく彩度を持たせた） | vs `--color-bg` | 8.36:1 | 4.5:1 | PASS |
| `--color-accent-fg` | `oklch(1 0 0)` | vs `--color-accent` | 8.36:1 | 4.5:1 | PASS |
| `--color-danger` | `oklch(0.577 0.245 27.325)`（既存値のまま） | vs `--color-bg` | 4.76:1 | 4.5:1 | PASS |
| `--color-danger-fg` | `oklch(1 0 0)`（新規追加） | vs `--color-danger` | 4.76:1 | 4.5:1 | PASS |

**ダークテーマ**

| トークン | 値（oklch） | 比較先 | 実測コントラスト比 | しきい値 | 判定 |
|---|---|---|---|---|---|
| `--color-bg` | `oklch(0.145 0 0)` | — | — | — | — |
| `--color-bg-subtle` | `oklch(0.269 0 0)` | — | — | — | — |
| `--color-fg` | `oklch(0.985 0 0)` | vs `--color-bg` | 18.96:1 | 4.5:1 | PASS |
| `--color-fg` | 同上 | vs `--color-bg-subtle` | 14.48:1 | 4.5:1 | PASS |
| `--color-fg-muted` | `oklch(0.708 0 0)`（既存値のまま） | vs `--color-bg` | 7.63:1 | 4.5:1 | PASS |
| `--color-fg-muted` | 同上 | vs `--color-bg-subtle` | 5.83:1 | 4.5:1 | PASS |
| `--color-border` | `oklch(0.55 0 0)`（旧 `oklch(1 0 0 / 10%)` から不透明値へ調整） | vs `--color-bg` | 4.08:1 | 3.0:1 | PASS |
| `--color-ring` | `oklch(0.556 0 0)`（既存値のまま。ダークは元々 3:1 に足りていた） | vs `--color-bg` | 4.18:1 | 3.0:1 | PASS |
| `--color-ring` | 同上 | vs `--color-bg-subtle` | 3.19:1 | 3.0:1 | PASS |
| `--color-accent` | `oklch(0.72 0.16 250)`（旧 `oklch(0.269 0 0)` から調整） | vs `--color-bg` | 7.95:1 | 4.5:1 | PASS |
| `--color-accent-fg` | `oklch(0.1 0 0)` | vs `--color-accent` | 8.26:1 | 4.5:1 | PASS |
| `--color-danger` | `oklch(0.704 0.191 22.216)`（既存値のまま） | vs `--color-bg` | 6.84:1 | 4.5:1 | PASS |
| `--color-danger-fg` | `oklch(0.1 0 0)`（新規追加） | vs `--color-danger` | 7.12:1 | 4.5:1 | PASS |

#### 既存 shadcn 変数との重ね方（採用方針）

**「意味づけとして重ねる」を基本とし、コントラストが未達だった 4 系統（`--muted-foreground` ライト / `--border` ライト・ダーク / `--accent` 系ライト・ダーク）だけ raw 値自体を調整した。** 新規の `--semantic-*` 変数は追加していない。理由:

- `--color-border` は `border-border`（`@apply border-border` で全要素に適用済み）と同一の Tailwind ユーティリティを生成するため、新しい raw 変数へ差し替えるとエイリアスが二重定義になり cascading で意図せず片方が無視される。実際に「カード枠・区切り線」として使われる値そのものを 3:1 以上へ調整するのが本来の要求（E-9）に最も忠実
- `--color-accent` も同様に既存の `bg-accent` 系ユーティリティと同一。現時点で `src/` 配下にアクセント色の具体的な参照箇所がまだ無い（スキャフォールド段階）ため、彩度を持たせた値へ調整しても既存コンポーネントの回帰リスクがない
- `--color-fg-muted` は概念的に `--muted-foreground` と完全に一致するため新規変数を作らず raw 値のみ調整
- `--color-bg` / `--color-bg-subtle` / `--color-fg` / `--color-danger` は既存値がそのまま要件を満たしたため無調整
- `--destructive-foreground` は shadcn の標準命名パターン（`*-foreground`）に合わせて新規追加し、`--color-danger-fg` としてもエイリアスした

#### 実測手順（再検証・再確定時）

```bash
python3 tools/check_contrast.py --self-test   # 変換・計算ロジックの自己テスト
python3 tools/check_contrast.py               # app/globals.css の実値を検査（run_checks.sh に組み込み済み）
```

配色を変更する際は、必ず上記を実行してから本節の表を更新すること。

### 2.3. タイポグラフィとスペーシング

- **タイポスケール**: `12 / 14 / 16 / 20 / 24 px` の 5 段階のみ。中間値を足さない
- **カード内の 3 段階**: リポジトリ名 `16–18px / 700` → 説明文 `14px / 400 / --color-fg` → メタ `12–13px / 500 / --color-fg-muted`
- **スペーシング**: **4px グリッド** に載せる（4 / 8 / 12 / 16 / 24 / 32）。任意の値を書かない

### 2.4. コントロールサイズトークン

`app/globals.css` の `@theme inline` に定義する。**数値の正本はここ 1 箇所**（他節は参照するだけで数値を書かない）。

| トークン | 用途 | 値 | 根拠 |
|---|---|---|---|
| `--size-control-xs` | 最小許容サイズ（アイコンのみボタン等） | `24px` | WCAG 2.2 2.5.8（AA）フロア。[Understanding SC 2.5.8](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html) |
| `--size-control-sm` | 小型コントロール | `28px` | Primer `--control-small-size`。[Primer Primitives: Size](https://primer.style/foundations/primitives/size) |
| `--size-control-md` | 既定 | `32px` | Primer `--control-medium-size`。[Primer Primitives: Size](https://primer.style/foundations/primitives/size) |
| `--size-control-lg` | 大型コントロール | `40px` | GOV.UK の text input 高さ（`alphagov/govuk-frontend` `_mixin.scss` の `height: govuk-px-to-rem(40px)`）/ Primer `--control-large-size` |
| `--size-control-xl` | 主要導線 | `44px` | WCAG 2.2 2.5.5（AAA）相当。[Understanding SC 2.5.5](https://www.w3.org/WAI/WCAG21/Understanding/target-size.html) / Apple HIG が **44×44 pt** を最小ヒット領域として明記（[Buttons](https://developer.apple.com/design/human-interface-guidelines/buttons)・逐語: "a button needs a hit region of at least 44x44 pt"） |
| `--text-control-min` | 入力系コントロールの最小フォントサイズ | `1rem`（16px） | iOS Safari は 16px 未満の入力欄にフォーカスすると自動ズームする |

#### 🔴 必須

- すべてのコントロールは `--size-control-xs`（24px）を下回らない
- 入力系コントロールのフォントサイズは `--text-control-min`（16px）を下回らない。**全ブレークポイントで**（`md:text-sm` のような縮小をしない）
- `maximum-scale=1` や `user-scalable=no` でズームを抑止しない（抑止すると WCAG 1.4.4 Resize Text 違反になる）
- **高さとフォントサイズは cva の `size` variant 経由でのみ指定し、呼び出し側の `className` に生の `h-*` / `text-*` を書かない**（数値の入力経路を 1 本に絞り、機械検査の射程に収める）

#### 🔵 推奨

- 主要導線（検索入力欄・検索ボタン）は `--size-control-xl`（44px）を使う
- 二次的なコントロールは `--size-control-md`（32px）以上を使う

#### なぜ 24px では足りないのか

WCAG 2.2 の 2.5.8（AA）が定める 24×24 CSS px は **適合の下限であって、快適な操作性の目標値ではない**。2.5.8 には間隔例外（隣接ターゲットと直径 24px の円が交差しなければ、視覚サイズが 24px 未満でも適合しうる）があり、法規適合の最低ラインに過ぎない。実際のタップ操作しやすさ（誤タップ防止・手指の震え・粗大運動障害への配慮）を狙うなら、2.5.5（AAA）相当の 44×44 CSS px が実務上のベストプラクティスとされる。

主要なプラットフォームのガイドラインも下限を 24px より大きく置いている（いずれも一次情報で確認済み）:

- **Apple Human Interface Guidelines**: "a button needs a hit region of at least 44x44 pt — in visionOS, 60x60 pt"（[Buttons](https://developer.apple.com/design/human-interface-guidelines/buttons)）
- **Material Design 3**: "Extra small and small icon buttons must have a target size of 48x48dp or larger to be accessible."（[Buttons specs](https://m3.material.io/components/buttons/specs)）。テキストフィールドは container height / target size とも **56dp**（[Text fields specs](https://m3.material.io/components/text-fields/specs)）

本プロジェクトが `--size-control-xl` を 48dp / 56dp ではなく **44px** に置いたのは、WCAG 2.5.5 の CSS px 基準と Apple HIG の pt 基準が一致する値であり、dp（Android の密度非依存単位）は CSS px と 1:1 対応しないため。

本プロジェクトの適合目標は `NFR-10` により **AA** であるため、`--size-control-xl`（44px）の採用は「AAA 準拠を謳うもの」ではない。あくまで主要導線に社内ベストプラクティスとして上乗せしているだけであり、AA 適合の判定自体は `--size-control-xs`（24px）で満たされる。

#### Tailwind v4 での参照記法

`h-(--size-control-xl)` の短縮記法を使う（`h-[var(--size-control-xl)]` と等価。tailwindcss 4.3.3 で実ビルド検証済み）。

```
❌ h-11 / h-[44px]（生の数値・Tailwind 既定スケール）
✅ h-(--size-control-xl)（トークン参照）
```

#### 機械検査とレビューの境界

| 範囲 | 担当 | 具体例 |
|---|---|---|
| cva `size` テーブルへの生の `h-\d+` / `size-\d+` 直書きの禁止 | 機械（`tools/check_ui_dimensions.py`・`run_checks.sh` の Error 検査） | `button.tsx` / `input.tsx` の variant 文字列 |
| 入力欄の無プレフィックス `text-*` が 16px 未満でないこと | 機械 | `input.tsx` のベースクラス |
| `--size-control-xs` / `--text-control-min` の宣言値がフロアを下回っていないこと | 機械 | `app/globals.css` |
| 登録済み呼び出しサイトの `className` への `h-*` / `text-*` 直書き禁止 | 機械 | `search-form.tsx` 等、config に登録された箇所 |
| variant → 必要 tier（例: 主要導線は `xl` 以上）の充足 | 機械 | config テーブルに登録された variant のみ |
| 未登録の新規コンポーネントの検知漏れがないか | レビュー（機械は Warning のみ） | `src/ui/components/` に新設されたが config 未登録のファイル |
| トークン化されていない意味論（「これは主要導線か」の判断そのもの） | レビュー（`code-review` スキルの UI・アクセシビリティ観点 / `pr-review-watcher` Step 7 の受け入れ判定役） | 新規コントロールの tier 選定の妥当性 |

🔴 **機械が守る範囲（上表の機械列）をレビューで二重指摘しない。** レビューは「機械検査を通過しているか」ではなく「意味論的に正しい tier を選んでいるか」「新規コンポーネントが config に登録されているか」を見る。

### 2.5. README 本文のタイポグラフィと書式（Issue #339・第三者コンテンツの表示規定）

詳細ページの README セクション本文（`src/ui/readme-section.tsx` の `dangerouslySetInnerHTML`）は
GitHub が書いた第三者 HTML であり、自サイトの UI コンポーネントとは別の規律で扱う。

- 🔴 **自サイトのセマンティックトークンだけで着色する**。新しい raw 色を追加しない。すべての色指定は
  §2.1 の 10 セマンティックトークンへの `var(--color-*)` 参照のみで構成する
  （`@tailwindcss/typography` の `--tw-prose-*` 18 項目を含む・`app/globals.css`）。
  `tools/check_contrast.py` は `app/globals.css` の `:root`/`.dark` ブロックの固定変数・固定ペアしか
  検査しないため、README 用に追加した色指定はこのゲートの対象外になりうる——だからこそ
  「新規 literal 色（`oklch(`/`#`/`rgb(`）を増やさない」という規律を守る（`transparent` のような
  無彩の値は可）。
- 🔴 **`prose-invert` / `--tw-prose-invert-*` は使わない**。本プロジェクトのセマンティックトークンは
  `:root` と `.dark` の両方で異なる値を持つ（自己反転する）ため、`var(--color-*)` を参照するだけで
  ダークテーマに自動追従する。invert 側の変数セットを別途定義すると項目数が倍になり、書き漏らしが
  プラグイン既定のグレースケールへ静かにフォールバックする失敗モードが生まれる。
- 🔴 **セクション見出しより大きい見出しを作らない**。README 本文の見出し（`readme-html.ts` が
  `h1→h3` 等へ +2 シフトした後のタグ）は、そのページのセクション見出し（`<h2>`「README」・
  `text-lg` = 18px）を視覚的に上回らない。§2.3 の 5 段階タイプスケールに中間値を足さず、
  16px / 14px の 2 段階とフォントウェイトの組み合わせで階層を表現する（見出しの `+2` シフト自体は
  アクセシビリティツリー上のセマンティクスであり、視覚サイズを絶対値で大きくする必要はない）。
- 🔴 **横溢れは領域内スクロールに閉じ込め、`body` に出さない**（`NFR-15`）。`table` は CSS だけでは
  table box 自身にスクロールを付けられないため、README 本文コンテナ側（`.readme-content`）に
  `overflow-x: auto` を当てて、はみ出す表・コードブロックをコンテナごと横スクロールさせる。
  `img` の溢れ防止は Tailwind Preflight が `max-width: 100%; height: auto` を既定で提供するため、
  重複して書かない。
- サニタイズの許可リスト（`src/ui/readme-html.ts` の `ALLOWED_TAGS` / `ALLOWED_ATTRIBUTES`）は
  書式付与のために広げない。`prose` は親要素のクラスと子孫セレクタで効くため、README 本文側の
  `class` 属性を許可する必要はない（第三者 HTML への `class` 開放は UI redress・コントラストゲート
  すり抜けのリスクを生む）。

---

## 3. レイアウトと i18n 耐性

- 🔴 **固定幅を使わない。** `min-width` + padding + Flex/Grid で可変にする
- 🔴 **ボタン・ラベルに `white-space: nowrap` を使わない。** 日英で文字列長が 1.5〜2 倍変わる
- 🔴 **ソート切替・表示件数切替を固定幅のセグメントコントロールにしない**（「関連度」vs "Best match"）。ドロップダウンか可変幅ボタンにする
- **200% 拡大で横スクロールが発生しないこと**（`NFR-15`）。確認は実ブラウザのズームで行う
- 🔴 **長さも内容も制御できない第三者由来テキストを描画する要素には、必ず折り返し指定を当てる。**
  対象は GitHub / Ecosyste.ms 由来の `description` ・ `topic` ・ `fullName` ・ `packageName` と、
  **画面へ再表示するユーザー入力**（検索語を埋め込む見出し等）。既定の `overflow-wrap: normal` は
  空白・ハイフンを 1 つも含まない長い文字列（`description` 末尾の URL 等）を割れないため、
  指定が無いと要素からはみ出し `body` に横スクロールが伝播する（WCAG 2.2 SC 1.4.10 Reflow 違反）。
  統制語彙（Linguist の言語名・レジストリ名）と自前 `Intl` 整形の数値・日付は対象外。

  **どちらを当てるかは「その要素自身が flex コンテナの直接の子か」で決める**:

  | 要素 | 当てるもの | 理由 |
  |---|---|---|
  | flex アイテム **でない**（ブロック・非置換インライン） | 祖先コンテナに `break-words` を 1 回（継承で届く） | 幅は親が確定させるので、行が溢れたときに割れれば足りる |
  | それ自身が flex アイテム（`ul.flex.flex-wrap` 直下の `<li>` 等） | その要素に `wrap-anywhere` を直付け | `overflow-wrap: break-word` は min-content の計算に参入しない（CSS Text 3）ため、automatic minimum size が floor として残り、継承だけでは要素ごとはみ出す |

  🔴 **`body` / `html` に `overflow-x: hidden` / `clip` を足して塞がない。** 情報が失われうるだけでなく、
  `body` が `overflow` を明示した時点で viewport への伝播が止まり、退行検知テスト
  （`e2e/overflow-guard.spec.ts` の `document.scrollingElement.scrollWidth <= clientWidth`）が
  **恒久的に green** になる（溢れが復活しても検知できなくなる）。

  退行検知は `e2e/overflow-guard.spec.ts`（320px 幅 × 改行機会ゼロの文字列）。E2E スタブから
  データを注入できない Gem 一覧・日次ダイジェストは、コンポーネントテストでクラスの存在を守る。
  経緯は `content/discussions/horizontal_overflow_20260823/whiteboard.md`。
- 高さが可変になる箇所は **`min-height` で下限だけ固定** する（上限を固定して文字を溢れさせない）

---

## 4. トップページ（検索・一覧）

### 4.1. コントロールの配置

検索欄の **直下に横並びのコントロール行**（ソート切替 + 表示件数切替）を置く。サイドバーは作らない（フィルタが 2 つしかないため過剰）。モバイルでは縦積みに落とす。

- すべての状態は **URL の `searchParams` に反映** する（`NFR-2`）
- ソート・件数・ページの変更は **URL 変更 → Server Component 再フェッチ** で実装する。クライアント側に結果の状態を持たない（`NFR-3` / INP）
- `use client` を付けるのは **検索入力欄と各コントロールのトリガーだけ**

### 4.2. 結果カードの情報設計（`R-10` の決定）

GitHub 検索結果の情報順序をベースラインに採る。

```
┌─────────────────────────────────────────────┐
│ [icon] owner/repo-name          ← 主役 16-18px/700
│ 説明文を 2 行で固定（line-clamp: 2）      ← 14px/400
│ 　（min-height で欄の高さを確保）
│ #topic #topic #topic +3                    ← タグ
│ ● TypeScript   ★ 1,234   更新: 2026-08-01  ← メタ 12-13px/500/muted
└─────────────────────────────────────────────┘
```

| 要素 | 指示 |
|---|---|
| リポジトリ名 | **省略しない**。最大フォント・太字 |
| 説明文 | `line-clamp: 2` で 2 行固定 + **説明欄に `min-height`**（有無・長さでカード高さが暴れないようにする = CLS 対策） |
| topics | 折返し許容。多い場合は `+N` に省略 |
| メタ情報 | 🔴 **アイコンだけにせず明示ラベルを添える**（「更新: 2026-08-01」）。言語間でアイコンの意味が伝わらない |
| 日時 | 🔵 **絶対表記**（`YYYY-MM-DD`）。相対表記（"3 日前"）は i18n とタイムゾーン誤解のリスクがあるため使わない |

### 4.3. 🔴 カード全体をクリック可能にする実装（a11y 必須パターン）

```
❌ カード全体を <a> で包む
   → スクリーンリーダーが説明文もメタ情報も全部読み上げてから「リンク」と告げる

✅ リポジトリ名（見出し）だけを <a> にし、その ::after に
   position: absolute; inset: 0 を張ってクリック領域をカード全体へ拡張する
```

- カード内に二次リンク（オーナーへのリンク等）を置く場合は `position: relative` + `z-index` で疑似要素の上に出す
- ⚠️ **受け入れる代償**: カード内テキストのドラッグ選択がしづらくなる

### 4.4. 状態表現（4 状態を同じ領域に排他的に出す）

| 状態 | 出すもの | 根拠 |
|---|---|---|
| **未検索（初期）** | **教育的**: 何ができるか + 始め方（例: 「キーワードを入力して Enter または検索ボタンで GitHub リポジトリを探せます」） | `AC-8` / NN/g |
| **読み込み中** | イラスト（`loading.webp`・256×256・「ふるいを振って小石がこぼれる」モチーフ）+ テキスト。`role="status"` / `aria-live` は外側の `<section id="search-status">` のみが持ち、`LoadingIndicator` 自身は持たない（#180 の回帰防止） | `AC-8` / `NFR-1` |
| **0 件** | **システム状態の確認**: 何に対して 0 件か + 次の手（例: 「"react" に一致するリポジトリが見つかりませんでした。キーワードを変えて再検索してください」） | `AC-8` / NN/g |
| **エラー** | §5 の種別別文言 + 再試行手段 | `AC-8` / `prd.md` §7 |

🔴 **初期状態と 0 件を同じ文言・同じ見た目にしない。** 別物として設計する。
🔴 **4 状態でレイアウトシフトを起こさない**（同じ領域に同じ最小高さで出す）。

> 🔵 **追記（Issue #347・2026-08-21）**: 未検索（初期）と 0 件の両方に装飾イラストが入った（`hero-idle.webp` / `empty-result.webp`）。**意匠をわざと変えている**: `hero-idle` は「灰色の小石の群れ + その中に 1 個だけ青い原石」（これから探せば見つかる = 原石が **ある**）、`empty-result` は「小石だけで原石なし・レンズ内は点線の空シルエット」（この条件では見つからなかった = 原石が **ない**）。文言だけでなく絵でも初期状態と 0 件を混同させない設計（専門チーム議論・`content/discussions/ui_image_assets_20260821` lead 裁定・争点 A）。両画像とも `alt=""` 単独・ロケール非依存の 1 枚（方針の詳細は §7.4）。
>
> 🔴 **改訂（Issue #359・2026-08-21・権威順: ユーザー明示 > 仕様）**: 読み込み中の表現を、上表がそれまで 🔵 推奨としていた「カード形状のスケルトン」ではなく、**専用イラスト（`loading.webp`）+ テキスト** に決定した。Issue #347 で導入した `hero-idle` / `empty-result` とのビジュアル一貫性を優先するというユーザーの明示指示によるもので、本表の 🔵 推奨（スケルトン）より優先する。**#169（スケルトン化）とスコープが競合する**: 本 Issue により「読み込み中をスケルトンにする」という #169 の前提が変わったため、#169 は「イラスト表示を維持したままレイアウトシフト対策（寸法の事前確保）をどう両立させるか」へ論点を絞り直す必要がある（クローズはせず、スコープ見直しの上で継続する）。

### 4.5. ページネーション

- `<nav aria-label="検索結果のページ">` でラップし、現在ページに **`aria-current="page"`** を付与（現在ページはリンクにしない）
- **件数を明示する**: 「157 件中 26〜50 件を表示」（MOJ Design System のパターン）
- 取得上限（1,000 件）に達したら、**上限の存在を明示する**（例: 「表示できる最終ページです。キーワードを絞り込むと他の結果が見られます」）。上限を超えるページ番号は提示しない（`AC-7`）
- ページ番号ボタンは `--size-control-xs`（§2.4）以上
- モバイルでは前後ボタン中心に簡略化してよい

---

## 5. エラー表示（`prd.md` §7 の UI 実装）

### 5.1. 文言の規則

- 🔴 **「何が起きたか + どう直すか」を書く**
- 🔴 **「申し訳ありません」「エラーが発生しました」「不正な」等の曖昧・謝罪表現を使わない**（GOV.UK Design System の規則）
- 内部情報（スタックトレース・トークン・内部エンドポイント）を出さない（`NFR-9`）

### 5.2. 種別別の文言（`prd.md` §7 の対応表に対応）

| 種別 | 文言の骨格 | 添えるもの |
|---|---|---|
| ネットワーク到達不可 | 「接続できませんでした」 | **再試行ボタン** |
| 一次レート制限 | 「リクエストが上限に達しました。{復帰時刻} 以降に再試行できます」 | 🔵 **ログイン導線**（`AR-5` / `US-25`）+ 復帰時刻（`x-ratelimit-reset` から算出） |
| 二次レート制限 | 「{N} 秒後に再試行できます」 | `retry-after` の秒数 |
| 認証・権限（401/403 のその他） | 汎用エラー | 内部情報を出さない（利用者は対処できない） |
| クエリ不正（422） | 「検索キーワードを確認してください」 | 具体的な制約（文字数上限等） |
| 対象なし（404・詳細） | Not Found 表示 | 一覧へ戻る導線 |
| GitHub 側障害（5xx） | 「GitHub 側で問題が発生しています」 | 再試行ボタン |

🔵 **レート制限エラーが `AR-5`（任意ログイン）の唯一の価値訴求点**（`US-25`）。ここの文言を手抜きしない。

### 5.3. 🔵 種別ごとの装飾イラスト（Issue #364・追記）

`ErrorNotice`（`role="alert"`）は `ErrorKind` ごとに装飾イラストを添える。対応表は以下のとおり（`src/ui/error-notice.tsx` の `ERROR_ILLUSTRATION` が実装の正本）。

| 画像 | `ErrorKind` |
|---|---|
| `/images/error-network.webp` | `network` |
| `/images/error-rate-limit.webp` | `rateLimitPrimary` / `rateLimitSecondary` |
| `/images/error-upstream.webp` | `auth` / `upstream` |
| `/images/error-validation.webp` | `validation` |
| `/images/not-found.webp`（既存流用・新規生成しない） | `notFound` |

🔴 **§5.1 の即物性の原則は変わらない**。イラストは文言の **補助** であり、置き換えではない——「申し訳ありません」等の曖昧・謝罪表現を使わない規律、「何が起きたか + どう直すか」を文言で書く規律は、イラストの有無に関わらずそのまま適用する。

> 権威順（ユーザー明示 > 仕様）により、Issue #347 の議論で一度確定した「エラーには絵を入れない」という判定を、Issue #364 のユーザー明示指示で上書きした。

---

## 6. 詳細ページ

- 最上部に オーナーアイコン + リポジトリ名（`h2` 相当。**ページ全体の `h1` は共有ヘッダーのツールタイトルが担うため、詳細ページ側では h2 に降格する**。改訂理由は下記コラム・§7.0 を参照）、直下に統計行
- 統計は **アイコン + ラベル + 数値** のセットで横並び（数値だけにしない）
- 🔴 **Watcher 数は `subscribers_count`**（`watchers_count` は star のミラー）。**Star と Watcher が同じ数字で並んでいたら実装ミス**（`AC-5`）
- 「一覧へ戻る」を左上に固定。ブラウザバックだけに依存しない。戻り先で検索条件が復元されること（`AC-6` / WCAG 2.2 の 3.3.7 Redundant Entry）
- リポジトリ名（`h2`）は GitHub 本体の該当リポジトリページへの外部リンク（新しいタブ）にする（Issue #148）。実装規約は §7.4a。**このリンクはページの `h1` ではない**（h1 は共有ヘッダーのツールタイトル・§7.0）

> 🔴 **改訂（Issue #334 F-1 / F-2・2026-08-21）**: 旧版は本節の見出しを `h1` と規定していたが、これはトップページの `h1`（旧: `messages.home.title` のプレーンテキスト）とは別に、詳細ページだけがもう 1 つ `h1` を持つ構造だった。F-1（トップのツールタイトルをクリックしたら未検索状態の画面へ遷移してほしい）と F-2（詳細画面も同じツールタイトルを含めて同じ挙動にしてほしい）への対応として、ツールタイトルを共有ヘッダーへ 1 箇所だけ実装し直したため、**1 ページに `h1` を 1 つだけ保つには詳細ページのリポジトリ名を `h2` へ降格する必要がある**。専門チームの議論（[議論記録](../../../content/discussions/feedback334_detail_readme_20260821/whiteboard.md)・争点 A・lead 裁定）で、リポジトリ名を `h1` のまま残す対案（ヘッダー側を非見出しリンクにする、またはルートごとにヘッダーを出し分ける）は複雑さに見合わないとして採らなかった。
>
> 🔵 **追記（Issue #347・2026-08-21）**: 上記の「共有ヘッダー」の実装場所が変わった。ロゴ画像・言語切替の右上移設・ログイン導線を 1 箇所に集約する必要が生じたため、`app/[locale]/layout.tsx` に直接書いていたヘッダーを新規 `src/ui/site-header.tsx`（Server Component・`<SiteHeader>`）へ切り出し、**一覧・詳細（成功/エラー）・404 の各 `page.tsx` / `not-found.tsx` が個別に呼び出す** 構成へ変えた（`layout.tsx` からはヘッダーを撤去済み）。`h1`（ツールタイトル + ロゴ画像）を持つのは `<SiteHeader>` 1 箇所のみで、規律そのもの（1 ページに `h1` は 1 つ）は変わらない。詳細は §7.0 の追記を参照。

---

## 7. アクセシビリティ実装（`NFR-10`〜`NFR-14` / `NFR-26`）

### 7.0. 🔴 ページ共通の見出し階層（`h1` / `h2`・Issue #334 F-1 / F-2）

全ページを通じて `h1` を持つのは **共有ヘッダー 1 箇所だけ** とする。中身はツールタイトル（`messages.home.title`）を `/{locale}`（クエリなしの固定 href）への内部リンクにしたもので、トップ・詳細のどちらからクリックしても未検索状態のトップページへ戻る（F-1 / F-2）。

各ページ固有のセクション見出し——トップの検索結果見出し・日次ダイジェスト見出し・詳細ページのリポジトリ名（§6）・README セクション見出し等——は **すべて `h2`** にする。個々の `page.tsx`（またはエラー分岐・`not-found.tsx`）が自前で `h1` を持つ実装は禁止し、1 ページに `h1` が 2 つ以上並ぶ状態を作らない。README 本文由来の見出し（`h1`〜`h6`）はこの `h2` セクション見出しの子として `+2` シフトして描画する（`h1→h3` … `h6` で cap。詳細は実装ドキュメント側の README レンダリング仕様を参照）。

> 🔵 **追記（Issue #347・2026-08-21）**: 共有ヘッダーの実装場所は `app/[locale]/layout.tsx` から新規 `src/ui/site-header.tsx`（`<SiteHeader>`・Server Component）へ移した。`layout.tsx` は `<html>`/`<body>` とフォント設定のみを持ち、ヘッダーは撤去済み。一覧（`app/[locale]/page.tsx`）・詳細の成功/エラー分岐・404（`not-found.tsx`）が **それぞれ `<SiteHeader>` を呼び出す** ことで、結果として全ルートに `h1` がちょうど 1 つ存在する状態を作る。
>
> これにより、旧版が持っていた「`layout.tsx` 1 箇所に書けばフレームワークが自動的に全ページへ適用する」という **構造的な強制力は失われた**（各 page が呼び忘れれば `h1` 0 個のページが作れてしまう）。この強制力は運用規律（本節の「自前で `h1` を持つ実装は禁止」）と、**新規 E2E `e2e/sp-347-header.spec.ts`**（全ルートで `header` 要素・`h1` 要素がちょうど 1 つであることを検証）による機械保証に置き換えた。`<SiteHeader>` 自体には左にロゴ画像（`alt=""`）+ ツールタイトル、右に言語切替（`LocaleSwitcher`）+ ログイン導線（`LoginLink`）を `justify-between` で配置する（「言語設定は頻繁に触れないので画面右上へ」というユーザー指示への対応・専門チーム議論の争点 D）。

### 🔴 機械ゲートの三層防御（役割分担・SSOT はここ 1 箇所のみ）

`SP-10` 実装スプリントの議論で確定（`content/discussions/sp10_a11y_20260820/`）。Lighthouse の Accessibility = 100 は「a11y が担保された」ことを意味しない（axe-core は `:focus-visible` を発火させないため、フォーカスリングの非テキストコントラスト等 SC 1.4.11 系の欠陥は検出できない）。1 層だけで守ろうとせず、以下 3 層で分担する。

| 層 | 担当 | 検出できるもの |
|---|---|---|
| Lighthouse / axe（DOM 静的解析） | `tools/run_lighthouse.mjs`・`e2e/axe.ts` | alt 欠落・ラベル欠落・ARIA 誤用など広範な一般違反 |
| `tools/check_contrast.py`（静的トークン検査） | デザイントークンの **宣言値** | `app/globals.css` に書かれた `--ring` 等の値そのものの 3:1 判定 |
| E2E（構造・到達・**実描画**） | `e2e/sp-10.spec.ts`・`e2e/overflow-guard.spec.ts`・`e2e/a11y-target-size.spec.ts`・`e2e/a11y-text-spacing.spec.ts` | フォーカスリングの **消失**、フォーカスの **喪失・到達不能**、`measureFocusIndicator`（`e2e/helpers.ts`）による **実効色・実効太さ** の 3:1 / 2px 判定、`boundingBox()` による **実描画ターゲットサイズ**（§7.5）、テキスト間隔の上書き耐性（§7.5a） |

「Lighthouse が緑だから a11y は健全」と早合点しない。

🔴 **`check_contrast.py`（層 2）の限界（PR #183 実測で判明）**: この層は `app/globals.css` の
**CSS 変数の宣言値**（文字列としての `oklch(...)`）しか読まない。以下は宣言値に一切現れないため、
この層では原理的に検出できない:

- Tailwind ユーティリティ側の不透明度修飾子（`focus-visible:ring-ring/50` 等）— `--ring` 自体は
  不透明のまま宣言されているため、宣言値だけ見ると PASS してしまう
- `transition-all`（`button.tsx` 等）による **遷移途中** の中間値（低 alpha・極細幅の一瞬）
- ブラウザのカスケード・実際のレンダリングパイプラインを経た後の **実効値**

これらは「宣言値は正しいのに実描画が誤っている」クラスの欠陥であり、**層 3（E2E・
`measureFocusIndicator`）だけが検出できる**。`measureFocusIndicator` は `getComputedStyle`
（カスケード・トランジション適用後）を読み、`<canvas>` の 2 点サンプリングで任意の CSS 色関数を
実ブラウザの変換で RGB へ解決してからコントラストを計算する（自前の oklch 変換式を二重実装しない）。
静的トークン検査が緑でも、この層が赤くなることがある——それは検査の誤りではなく、
検査対象が異なることの表れである。

### 7.1. 🔴 Next.js 固有の必須対応: ルート変更のアナウンス

Next.js の route announcer は **document title が変化しないと何もアナウンスしない**（既知の issue）。本アプリはページ送り・ソート切替で `searchParams` だけが変わるため **直撃する**。

```
必須実装:
1. 結果一覧の見出し（<h2>）に tabIndex={-1} を付ける
2. 検索実行・ページ送り・ソート変更の完了後、その見出しへ focus() を移す
3. あわせて件数のライブリージョンを更新する
```

これがないと `AC-8`（状態変化を支援技術に伝える）を満たせない。

🔴 **本節の対象は `next/link` によるクライアント遷移**（ページ送り・ソート・件数切替・一覧⇄詳細）であり、`search-form.tsx` のネイティブ GET フォーム送信（ページ全体のフルリロード）は対象外。

### 7.2. `aria-live`

- 件数通知は **`role="status"`**（暗黙で `polite` + `atomic`）
- 🔴 **`role="alert"` と `aria-live="assertive"` を同時に付けない**（iOS VoiceOver で二重読み上げ）
- 🔴 ライブリージョンは **初期 DOM に空で常設** し、中身を書き換える（要素ごと動的挿入しない）

### 7.3. フォーカス

- 🔴 **`:focus` ではなく `:focus-visible`** を使う
- 🔴 **`outline-none` を単独で書かない。** 必ず `focus-visible:ring-*` と対にする
- リングのコントラストは **3:1 以上**、太さ 2px 相当以上
- 🔴 **透明度は CSS 変数側に埋め込み、Tailwind ユーティリティ側の `/NN` サフィックスを `ring`/`outline` に使わない**（例: `focus-visible:ring-ring/50` は禁止。半透明にしたいなら `--ring: oklch(L C H / A%)` のように変数の宣言値へ alpha を埋め込む）。`tools/check_contrast.py` は CSS 変数の宣言値しか読まないため、ユーティリティ側 opacity を使うと機械検査が値を読めなくなる
- sticky ヘッダーを置くなら、フォーカス移動先に **`scroll-margin-top`** をヘッダー高さ分設定する（WCAG 2.2 の 2.4.11）

#### フォーカスリング実装パターン別ガイド（Issue #208）

CSS プロパティ選択による実効値の違いを以下に示す。要件「2px 相当以上 + コントラスト 3:1 以上」の充足判定に使う。

| 実装方法 | CSS プロパティ | 実効値（ピクセル） | 実装例 | 推奨度 |
|---------|---------------|------------------|--------|--------|
| **Tailwind ring** | `focus-visible:ring-3`（Tailwind `ring` は両側の合計値） | **3px**（効果的） | `<button className="focus-visible:ring-3 focus-visible:ring-ring">` | ✅ **推奨** |
| **outline（ブラウザ既定）** | `outline: auto`（ブラウザ依存） | 1px（Safari / Chrome） | `<select />` のネイティブ要素 | ⚠️ 要実測（要件未達の可能性） |
| **outline（明示指定）** | `outline: 2px solid`（手書き）| 2px | `focus-visible:outline-2 focus-visible:outline-ring` | ✅ 可 |
| **box-shadow** | `box-shadow: 0 0 0 2px` | 2px | Tailwind には未実装・カスタム CSS 必須 | ✅ 可 |
| **border** | `border: 2px`（toggle） | 2px | ボタンサイズが変わるため、`box-sizing: border-box` 必須 | ⚠️ 実装コストあり |

🔴 **ネイティブ `<select />` 等でブラウザ既定の `outline: auto` に依存する場合は、実測で要件充足を確認する**（1px で要件未達になるケースあり・Issue #208）。

### 7.3a. スキップリンク（WCAG 2.4.1 Bypass Blocks・Issue #354）

- 共通ヘッダー（`site-header.tsx`）の `<header>` **直前** に `#main-content` へ飛ぶスキップリンクを置く。`sr-only`（既定は非表示）+ `focus-visible:not-sr-only`（キーボードフォーカス時のみ可視化）とし、可視化時は他要素と同じ `focus-visible:ring-*` の枠を使う（§7.3）
- 各ページの `<main>` に `id="main-content"` と `tabIndex={-1}` を付け、リンク先へ実際にフォーカスが移るようにする（`href="#main-content"` だけではフォーカス移動を保証しない）

### 7.4. 画像の代替テキスト（`NFR-14` の方針確定）

| 文脈 | 指示 |
|---|---|
| カード・詳細でオーナー名が **テキストとして隣接表示される** | 🔵 **`alt=""`（スペースなしの空文字）を明示指定**（装飾扱い）。属性の省略はしない（ファイル名を読み上げる SR がある） |
| アイコンが **唯一の情報源** になる場合 | 意味のある `alt` を書く |

#### 🔵 追記: 装飾イラストの方針（Issue #347・logo / hero-idle / empty-result / not-found・2026-08-21）

ヘッダーロゴ・未検索（待ち受け）・検索結果 0 件・404 の 4 点は **装飾イラスト**（情報を運ばない）として扱い、以下を満たす。

- **画像内に文字を焼き込まない**。WCAG 1.4.5（Images of Text）を踏まないためで、意匠変更のたびに翻訳・再生成を同期する運用コストも避ける
- **ロケール非依存の 1 枚** を ja/en で共用する。「言語ごとに画像を出し分ける」は文字なし・情報量ゼロの意匠差にとどまるため WCAG 上は許容されうるが、**locale は言語であって文化圏ではない**——言語に文化的モチーフを紐づけるとステレオタイプ化するリスクがあり、資産を 2 倍持って同期し続けるコストにも見合わない（専門チーム議論・`content/discussions/ui_image_assets_20260821` a11y_i18n 反論・lead 裁定・争点 B）。ロケール別に出し分けるのは OG 画像のみで、そちらは `next/og` の実行時テキスト合成であり画像への文字の焼き込みではない
- **`alt=""` は単独で指定する**。`aria-hidden="true"` を重ねて二重に隠さない（既存 `repository-list.tsx` の装飾画像と実装パターンを揃える）
- **ライブリージョン（`role="status"`）の外（兄弟要素）に置く**: 検索結果 0 件のイラストは、件数・文言を読み上げる `role="status"` 要素の **内側に置かない**。ライブリージョンの中身は音声で読み上げられる情報だけに保つという §7.2 の不変条件を、画像追加後も構造で守るため
  - 🔴 **唯一の例外は読み込み中のイラスト（`loading.webp`・Issue #359）**。`LoadingIndicator` は `<Suspense>` の fallback として **必ず `<section id="search-status" role="status" aria-live="polite">` の内側に現れる**（外に出すと「読み込み中 → N 件中 M 件を表示」の遷移がライブリージョンの中身の入れ替わりとして通知されなくなる・§7.2）。したがって構造的に兄弟へ出せない。**この例外が成立する条件は `alt=""` 単独であること 1 点のみ**——空 alt の `<img>` はアクセシビリティツリーから除外されるため、ライブリージョンの再構成対象に実質含まれない。🔴 **この画像に有意味な `alt` を与える変更は禁止**（与えた瞬間、再検索のたびに画像の代替テキストまで読み上げ直され、§7.2 の不変条件が破れる）
  - 🔵 **追記（Issue #364・2026-08-22）**: `ErrorNotice`（`role="alert"`）に添えるエラー種別イラスト（§5.3）も本文の外（兄弟要素）に置く。`role="alert"` は `role="status"` と同じくライブリージョンであり、上記の不変条件がそのまま適用される。**読み込み中（`loading.webp`）が唯一の例外という位置づけは変わらない**——`ErrorNotice` は一度確定した最終状態を 1 回描画するだけで、`<Suspense>` fallback のように遷移の通知を担う構造上の理由が無いため、既定どおり外に出せる（実装は `src/ui/error-notice.tsx` を参照。単体テスト `src/ui/error-notice.test.tsx` が `role="alert"` 内に `img` が 0 個であることを固定する）
- **中央寄せにする（Issue #369・2026-08-22）**: 装飾イラストは横幅いっぱいのコンテナ内で左寄りにならないよう中央寄せにする。待ち受け（`mx-auto`）・読み込み中（`mx-auto`）・0 件（親要素の `flex flex-col items-center`）・404（`mx-auto`）・エラー（`mx-auto`）の 5 状態全てで揃える
- **アセットの正本は `tools/ui-assets/`**（プロンプト全文・生成手順・配信ファイルへの変換スクリプト）。詳細は [`tools/ui-assets/README.md`](../../../tools/ui-assets/README.md) を参照。中間生成物（1024² の原寸 PNG）はリポジトリにコミットしない——正本は配信ファイル（`public/images/*.webp` 等・git 管理）そのもので、原寸 PNG の再生成は「同じ結果の復元」ではなく「デザインを変えたいときの起点」（画像生成は非決定的なため）

### 7.4a. 新しいタブで開く外部リンクの実装規約

🔴 **適用対象**: `target="_blank"` を持つ **すべて** の外部リンク（例外なし）。現時点の適用箇所は `repository-detail.tsx` の GitHub リンク・`attribution-notice.tsx` のライセンスリンク等だが、この列挙は **現時点の適用箇所一覧であってスコープの限定ではない**。新しく `target="_blank"` を持つリンクを追加した箇所にも同じ 3 点を適用する。

新しいタブで開くリンク（`target="_blank"`）を実装するときは、以下の 3 点を必ず満たす。

- 🔴 **`target="_blank"` を単独指定にしない**: 必ず `rel="noopener noreferrer"` を併記する。`noopener` は新規タブ側の `window.opener` を断ち、リバーステーブナッビング攻撃（新規タブが `window.opener.location` を書き換えて元タブをフィッシングサイトに差し替える攻撃）を防ぐ。`noreferrer` はリファラーヘッダの送出を止める
- 🔴 **新しいタブで開く旨を支援技術に伝える**: リンクの可視テキストだけでは画面遷移がないことを期待するスクリーンリーダー利用者を驚かせるため、`sr-only` 文言（`（新しいタブで開きます）` / `(opens in a new tab)`）を添える。文言は `messages/{locale}.json` に持ち、コンポーネントへ props で渡す（ハードコードしない・§3 の i18n 方針）
- 🔴 **sr-only 文言は `<a>` の内側に置く**: 外（兄弟要素）に出すと **リンク自体のアクセシブルネームに入らない** ため、スクリーンリーダーのリンク一覧で読み上げたときに新しいタブで開くことが伝わらない。見出しの中にリンクを置く場合も同じ（`repository-detail.tsx` の `<h2>` はこの形。ページの `h1` は共有ヘッダーのツールタイトル・§7.0）
- 🔴 **区切りは半角スペースに頼らず文言側の括弧で作る**: アクセシブルネームの計算はインライン要素の境界で空白を挿入しないため、`<a>fullName<span class="sr-only"> 新しいタブで開きます</span></a>` は `fullName新しいタブで開きます` と連結される（JSX が要素先頭の空白を落とすことも重なる）。文言を括弧で始めておけば連結されても区切りとして読める

```
❌ target="_blank" のみ（rel 省略・sr-only 文言なし）
✅ target="_blank" rel="noopener noreferrer" + sr-only で新規タブである旨を明示
```

### 7.5. ターゲットサイズ（WCAG 2.2 の 2.5.8 / 2.5.5）

🔴 **値の正本は §2.4**。本節は数値を繰り返さず、2 つの達成基準の関係と例外条項の解説に専念する。

#### 2.5.8 Target Size (Minimum) — Level AA（本プロジェクトの適合目標）

ポインタ入力のターゲットは、`--size-control-xs`（§2.4）以上。判定は「ターゲット内に軸整列した正方形（同サイズ）を完全に収められるか」であり、ターゲットの外形そのものが正方形である必要はない。**5 つの例外** を持つ:

| 例外 | 内容 |
|---|---|
| Spacing（間隔） | フロア未満のターゲットでも、各ターゲットの外接矩形中心にフロア直径の円を置いたとき、隣接ターゲットの円と交差しなければ適合 |
| Equivalent（等価コントロール） | 同一ページ上の別のコントロールが 2.5.8 自体を満たしていれば（＝フロア以上であれば）よい自己参照的な規定 |
| Inline（インライン） | 文または文のブロック内にあるターゲット（テキスト内リンク等）は対象外 |
| User Agent Control（ユーザーエージェント制御） | サイズがブラウザ既定値のままで著者が変更していない場合は適用除外 |
| Essential（本質的） | サイズがそのターゲットの機能にとって本質的な場合 |

本プロジェクトは間隔例外に頼らず、`--size-control-xs` を実サイズで満たす方針を §2.4 で確定させている。担保するのは **`e2e/a11y-target-size.spec.ts`**（`boundingBox()` の実描画サイズで判定。宣言値・クラス名では判定しない）。同ファイルは検査対象に含めた要素と、例外に該当するため除外した要素の双方を根拠つきで列挙する。

### 7.5a. テキスト間隔（WCAG 2.2 の 1.4.12）

利用者がテキスト間隔（`line-height` 1.5 / 段落後 2em / `letter-spacing` 0.12em / `word-spacing` 0.16em）を上書きしても、**コンテンツや機能が失われない** こと。本プロジェクトはこの 4 値を独自に上書きしないため、達成基準の文言値をそのまま判定基準とする（**ここで新しい数値を定義しない**）。

担保するのは **`e2e/a11y-text-spacing.spec.ts`**。上記 4 値を `page.addStyleTag` で強制注入したうえで、320px 幅（§3 が SC 1.4.10 の根拠として定めた最小幅と同じ）で ① 横スクロールが発生しない ② カード同士が縦方向に重ならない ③ 主要なテキスト要素が引き続き可視、の 3 点を実測する。

#### 2.5.5 Target Size (Enhanced) — Level AAA（社内ベストプラクティスとして一部採用）

ポインタ入力のターゲットは `--size-control-xl`（§2.4）以上。2.5.8 と異なり **Spacing 例外を持たない**（4 つの例外: Equivalent／Inline／User Agent Control／Essential）。Equivalent 例外も 2.5.8 より厳格で、代替コントロールが明示的にフロア（44px）以上であることが要求される（2.5.8 の自己参照的な緩さがない）。

🔴 **本プロジェクトの適合目標は `NFR-10` により AA。** 2.5.5（AAA）は「準拠を謳うもの」ではなく、主要導線（§2.4 の 🔵 推奨）にのみ社内ベストプラクティスとして上乗せする。すべてのコントロールに 44px を要求しない。

### 7.6. 該当しない基準（記録として残す）

| 基準 | 理由 |
|---|---|
| 3.2.6 Consistent Help | ヘルプ・問い合わせ導線を持たない。**将来追加するなら共有 `layout.tsx` に置く** |
| 2.5.7 Dragging Movements | ドラッグ操作を持たない |
| 3.3.8 Accessible Authentication | `AR-5` は GitHub OAuth への委任であり、自前のパスワード入力・認知機能テストが存在しない |

### 7.7. 🔴 自動検証で拾えない項目（手動チェックリスト）

Lighthouse の a11y カテゴリは axe-core の全ルールの約半分しか実行せず、自動ツールが検出できる WCAG 違反は全体の 30〜40% 程度。**Lighthouse 100 は下限であって達成ではない。**

```
[ ] キーボードのみで 検索 → 一覧 → 詳細 → 一覧復帰 を完走できる（Tab 順序が論理的・フォーカストラップなし）
[ ] スクリーンリーダーで件数アナウンスが二重読み上げにならない
[ ] 読み込み中 → 件数確定 のアナウンス順序が破綻しない
[ ] 200% 拡大で横スクロールが強制されない
[ ] アイコンボタンの実測サイズが `--size-control-xs`（§2.4）以上
[ ] 入力欄にモバイル実機でフォーカスして自動ズームが起きない
[ ] アバターの alt="" が「隣接テキストと冗長」な文脈でのみ使われている
[ ] sticky ヘッダーにフォーカスが隠れない（実際にキーボードで確認）
[ ] フォーカスリングのコントラスト比を実測した
[ ] リンクテキストが文脈から切り離されても意味が通る（「詳細を見る」等の曖昧文言がない）
```

---

## 8. パフォーマンス実装（`NFR-1` / `NFR-6`）

### 8.1. LCP

- 🔴 **LCP 対象要素（見出し・最初の結果カード）を、遅いデータに依存する Suspense 配下に置かない**
- `searchParams` は Promise。**トップレベルで `await` せず、実際に使うコンポーネントまで遅延させる**（トップで await すると配下全体が dynamic 化する）
- `loading.tsx` は route segment に置くだけで Suspense fallback として機能する

### 8.2. INP

- 🔴 **ソート切替・件数切替・ページ送りはクライアント状態を持たない。** URL 変更 → Server Component 再フェッチ
- `use client` は検索入力欄と各コントロールのトリガーに限定する（`NFR-3`）

### 8.3. CLS

- 画像は `width` / `height` を必須指定。`fill` を使う場合は **`sizes` を必ず指定**（未指定は `100vw` 前提で過大な画像を落とす）
- スケルトンは **実データと同一寸法**
- 説明文は `line-clamp` で行数を固定し、欄に `min-height` を与える
- フォントは `display: 'optional'`

### 8.4. GitHub アバターの最適化

```
next.config: images.remotePatterns に
  { protocol: 'https', hostname: 'avatars.githubusercontent.com' }
```

🔴 **`protocol` / `hostname` を省略してワイルドカード任せにしない**（公式が非推奨）。

### 8.5. 一覧 ↔ 詳細の遷移

🔵 **`<Link>` の標準挙動に任せる。** viewport 進入で自動プリフェッチされ、スクロール位置も標準で維持される。独自のプリフェッチ制御を書かない。

### 8.6. 🔵 画像アセットの予算（Issue #347・装飾イラスト・追記）

- **1 ページ合計 100KB・個別 30KB** を目安予算とする（🔴 **本表の KB 表記と消費率はいずれも 1KB = 1024 バイト換算**。個別予算 30KB = 30,720 バイトを 100% とする。行ごとに 1000 / 1024 を混ぜない）。実測値（`ls -l public/images/`・2026-08-22・Issue #364 でエラー種別イラスト 4 点を追加した後の値）は以下のとおりで、**アセットごとに予算消費率が大きく異なる**。

  | アセット | 表示寸法 | 実測サイズ | 個別予算（30KB）比 |
  |---|---|---|---|
  | `logo.webp`（96px 生成） | 24×24 | 2,838 バイト（約 2.8KB） | 9% |
  | `error-validation.webp`（256px 生成） | 80×80 | 6,130 バイト（約 6.0KB） | 20% |
  | `error-upstream.webp`（256px 生成） | 80×80 | 8,256 バイト（約 8.1KB） | 27% |
  | `error-rate-limit.webp`（256px 生成） | 80×80 | 8,476 バイト（約 8.3KB） | 28% |
  | `error-network.webp`（256px 生成） | 80×80 | 8,884 バイト（約 8.7KB） | 29% |
  | `not-found.webp`（320px 生成） | 160px | 9,966 バイト（約 9.7KB） | 32% |
  | `empty-result.webp`（256px 生成） | 96〜120px | 10,400 バイト（約 10.2KB） | 34% |
  | `loading.webp`（256px 生成） | 64×64 | 19,358 バイト（約 18.9KB） | 63% |
  | `hero-idle.webp`（768×432・16:9 へ変換） | 最大幅 320px（16:9） | 27,594 バイト（約 27.0KB） | **90%** |
  | `og-background.png`（OG 専用・1200×630） | OG 1200×630 | 140,957 バイト（約 137.7KB） | 対象外（ブラウザの DOM に現れず、SNS クローラーのみが取得するため §7.4 のとおりこのページ内予算に含めない） |

  🔴 **「約 10.2KB」は 256px の静止画アセット（`empty-result` 相当）の実測値であり、全アセットに当てはまるわけではない**（同じ 256px 生成でも `loading.webp` は約 18.9KB、エラー種別イラスト 4 点は 6.0〜8.7KB とばらつく）。特に `hero-idle.webp`（16:9 化後も）は 27.0KB で **個別予算 30KB の約 90% を消費** しており、余裕があるとは言えない。1 ページで同時に読み込むのはロゴ + 状態イラスト 1 枚（例: logo + hero-idle ≒ 30.4KB）、またはエラー画面ではロゴ + エラー種別イラスト 1 枚（例: logo + error-network ≒ 11.5KB）で、いずれも合計予算 100KB は下回る
- 予算内に収まるアセットを、予算超過を理由に別形式（例: 手書き SVG への再作図）へ作り直す必要はない。ただし **アセットを追加・差し替える際は `ls -l` 等で実測してから予算比を記載する**（推測で「余裕がある」と書かない）。予算はあくまで **上限のガードレール** であり、それ自体を実装方針の決定根拠にしない（判断根拠は `docs/adr/0015-ai-generated-visual-assets.md`）

---

## 9. 完了・成功の定義（レビューで判定する）

- [ ] §1 のスタック以外のランタイム依存を追加していない
- [ ] §2 のセマンティックトークン経由で色を参照している（生の色名の直書きがない）
- [ ] §4.3 のカードリンクパターンを使っている（カード全体を `<a>` で包んでいない）
- [ ] §4.4 の 4 状態が実装されている。**レイアウトシフトの有無は目視で判定せず、`tools/run_checks.sh` で実行される Lighthouse の CLS 実測値で判定する**（`NFR-1` の 0.1 以下）
- [ ] §5.2 のエラー種別ごとに文言が分かれている
- [ ] §2.4 のコントロールサイズトークンを cva の `size` variant 経由でのみ参照し、`tools/check_ui_dimensions.py` が PASS する
- [ ] §7.1 のフォーカス移動が実装されている（⚠️ **実装は `SP-10`（`E-15`）の射程**。`SP-9` は状態の可視化とアナウンスまでを担い、`AC-8` の完全達成は `SP-10` 時点）
- [ ] §7.7 の手動チェックリストを実際に通し、🔴 **チェック結果（各項目の可否）を PR 本文に貼付した**（自己申告だけで ✅ を付けない）
- [ ] §8.4 の `remotePatterns` が明示指定されている
- [ ] §2.5 の README 書式が新規 raw 色を追加せず（機械検査済み）、既存セマンティックトークンの参照のみで実装されている

---

## 10. 参照

| ドキュメント | 関係 |
|---|---|
| [UI/UX リサーチ](./20260817-ui-ux-research.md) | 本書の根拠・出典・**未確認項目の一覧** |
| [ADR 0001: UI スタック](../../adr/0001-ui-stack.md) | `TR-5` の決定と Radix を選んだ理由 |
| [ADR 0015: AI 生成ビジュアルアセット](../../adr/0015-ai-generated-visual-assets.md) | §7.4 の装飾イラスト方針（文字非焼き込み・ロケール非依存 1 枚・透過 WebP 配信）を決めた理由 |
| [`prd.md`](../../02_requirements/prd.md) | 要件・受け入れ条件の正本 |
| [`user-story-map.md`](../../02_requirements/user-story-map.md) | `E-9`（配色）/ `E-13`（a11y）/ `E-15`（キーボード）/ `E-17`（alt）の実装単位 |
| `docs/rules/sprint-development-rules.md` | `SD-4` の読解対象。本書はスプリント着手時に読む |
