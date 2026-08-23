<!--entry
author: ux_entry
round: 2
kind: rebuttal
ts: 2026-08-23T12:09:42+09:00
-->

# ux_entry Round 2: 実装検証 + F-1 PR 文言 + F-2 avatar レイアウト判定

## 1. 自案の実装検証（再読・実行済み・結論: 訂正不要）

- **import パス**: `src/ui/gem-list-link.tsx` は `src/ui/` 直下にあり、`src/ui/components/button.tsx` が実在（`login-link.tsx` L1 が同じ階層から同じ `./components/button` で import している前例と一致）。**`./components/button` は正しい**。飼い主コメントが疑った `src/ui/button.tsx`（直下）は存在しない——実体は `src/ui/components/button.tsx` の 1 箇所のみ（`find /home/user/gem-hunter/src/ui -iname "*button*"` で確認済み）。
- **`buttonVariants` の `className` 受け口**: `node_modules/class-variance-authority/package.json` の実バージョンは `0.7.1`。`dist/types.d.ts` L20-25 に `ClassPropKey = "class" | "className"` があり、cva の戻り関数は `class` / `className` のどちらか一方を追加マージ入力として正式に受ける型定義になっている。**`buttonVariants({ variant, size, className })` は型・実装ともに正しい**（`pagination.tsx` L43-46 が `disabledClassName = buttonVariants({ variant: 'ghost', size: 'default', className: 'pointer-events-none text-muted-foreground/50' })` と全く同じ形で既に使っている前例あり）。
- **`lucide-react` の `Gem` エクスポート**: `node_modules/lucide-react/dist/esm/lucide-react.mjs` L882 に `export { default as Gem, default as GemIcon, default as LucideGem } from './icons/gem.mjs';` を実測。**named export `Gem` は実在する**（`Gemini`/`Gemma` 系アイコンとの誤爆ではない、`gem.mjs` 単体ファイルも実在)。
- **`gem-list-link.test.tsx` の既存アサーション**: 全文を再読。
  - `getByRole('link', { name: '…' })` + `href` 検証 → アイコンに `aria-hidden="true"` を付ける前提のため、アクセシブルネームは可視ラベルのみで変わらず **無修正で通る**。
  - `link.className` に対する `toContain('focus-visible:ring-3')` / `toContain('focus-visible:ring-ring')` → `button.tsx` L11 のベースクラス文字列に両方の部分文字列がリテラルで含まれる（`focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring`）。cva はこれをそのまま結合した文字列を返すため **部分一致は成立し、無修正で通る**。

**結論**: round 1 の実装案（`buttonVariants({ variant: 'ghost', size: 'default', className: 'gap-1.5' })` + `<Gem aria-hidden="true" className="size-4 shrink-0" />`）は import パス・API・テストのいずれについても訂正不要。断定して良いことを実機で確認した。

## 2. 飼い主が名指しした「ロゴ流用」への回答（PR 本文にそのまま書ける 1〜2 文）

> 飼い主案の「アプリタイトルのロゴを文言頭に添える」は見送り、代わりに lucide の `Gem` アイコンを採用します。`logo.webp` はサイトブランド（ホームへの `<h1>` タイトルリンク）専用の固定色ラスター画像で、検索結果の別導線に転用すると「これもホームへのリンクでは」という誤読を招くため、行き先（Gem 一覧）を直接示すピクトグラムを新規に用意する方が導線としての意味が伝わります。`Gem` は既存の `lucide-react` 依存内にあり追加コスト・追加アセットレビューなしで導入できます。

**ロゴ流用が妥当になる条件（1 行）**: 「この導線がトップページ（`/${locale}`）そのものへ戻る操作を兼ねる」設計に変わるなら、ロゴ＝ホームという意味が導線の意味と一致するため流用は妥当（現行仕様は Gem 一覧という別画面へ行く導線であり、この条件を満たさない）。

## 3. F-2: avatar 追加時の Gem 一覧カードのレイアウトと `::after` クリック領域整合（`data_scope` 案への判定）

**判定: 妥当。ただし `repository-list.tsx` と厳密に同じ 2 カラム構造に揃える必要がある（現状の `gem-list.tsx` は単カラムなので実装変更が要る）。**

根拠（実測・行番号付き）:

- 現行 `repository-list.tsx` L113-142 は `<li className="relative flex gap-3 py-4">` の中に、**avatar `<img>` を `Link` の外（兄弟）** に置き（L116-125）、続けて `<div className="min-w-0 flex-1">`（L126）の中に `::after` 付き `Link`（L134-142）を置く 2 カラム（画像 + テキスト列）構造。`::after` の `position: absolute; inset: 0` は最も近い `position` 祖先である `<li className="relative …">` を基準に広がるため、avatar が `Link` の外に居ても **クリック領域は `<li>` 全体（avatar の上も含む）** に及ぶ（`ui-ux-guidelines.md` §4.3 が要求する「見出しだけを `<a>` にし `::after` で領域拡張」という構造と矛盾しない——avatar を `<a>` の中に入れていないので二次リンクの `z-index` 競合問題（§4.3 の注記）も発生しない）。
- 一方、現行 `gem-list.tsx` L210-238 は `<li className="relative py-4">`（`flex` 無し・単カラム）で avatar が無い。`data_scope` の avatar 追加案をそのまま L210 の `<li>` 直下に `<img>` を足すだけだと、`flex` が無いため画像がブロック要素として **テキストの上に積み上がる**（横並びにならない）。**`repository-list.tsx` と同じ `className="relative flex gap-3 py-4"` へ変更し、`<img>` を `Link` の外側・`<div className="min-w-0 flex-1">` の外に置く構造に揃える実装が必要**（`data_scope` の主張は「足せる」という可否判定としては正しいが、レイアウト構造の変更点までは明示していない——ここを補う）。
- **画像仕様も `repository-list.tsx` に揃える**: `width={40} height={40}` 明示 + `className="size-10 shrink-0 rounded-full"` + `loading="lazy"` + `alt=""`（`repositoryFullName` がテキストとして隣接表示されるため装飾扱い・`ui-ux-guidelines.md` §7.4 表の 1 行目と同じ理由）。1 ページ最大 20 件（`data_scope` の投稿にある GitHub API 20 件枠と同じ母数）全件に `loading="lazy"` を付ければ、初期ビューポート外の画像はブラウザが自動的に読み込みを遅延する。`repository-list.tsx` も全件 `loading="lazy"` で特別扱い（最初の数件だけ eager にする等）はしていないため、Gem 一覧も同じ扱いで一貫性が保てる。
- **レイアウトシフト対策**: `width`/`height` 属性が明示されていれば、ブラウザは画像読み込み前にアスペクト比から確保領域を計算する（CLS 対策・`ui-ux-guidelines.md` L524「画像は `width`/`height` を必須指定」）。`size-10`（40px 固定）と合わせて数値が矛盾なく一致しているため、20 件分の画像が順次読み込まれても行の高さが動かない。これは検索結果一覧で既に本番相当のトラフィックで検証済みのパターン（`repository-list.tsx`）の再利用であり、新規のリスクではない。
- `next/image` の remote patterns 設定（`next.config.js` の `avatars.githubusercontent.com` 許可）は **今回のケースには不要**: `data_scope` が提案する `https://github.com/{owner}.png` も、既存の `repository-list.tsx` と同じ **素の `<img src>`**（`next/image` 不使用・`INF-11`）で描画するため、ドメイン許可リストの対象外。ここは `data_scope` 案の実装上の懸念点にはならない（念のため明示しておく）。

**結論**: `data_scope` の「avatar だけなら足せる」という可否判定に同意した上で、実装は `repository-list.tsx` の 2 カラム構造・画像属性一式をそのまま複製する形に限定すべきで、単カラムの `gem-list.tsx` へ `<img>` を無条件に追記する実装は避ける（レイアウトが崩れる）。§4.3 のクリック領域要件・§7.4 の `alt` 方針・CLS 対策のいずれも repository-list.tsx の実装をコピーすれば自動的に満たされる。
