<!--entry
author: design_system
round: 1
kind: claim
ts: 2026-08-19T10:03:20+09:00
-->

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
