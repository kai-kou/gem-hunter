<!--entry
author: readme_fidelity
round: 1
kind: claim
ts: 2026-08-21T18:02:26+09:00
-->

# 書式の再現度: 現状分析（readme_fidelity round1）

## 結論

**バグの主因は許可タグ・属性の欠落ではなく、CSS 側にある。** README コンテナに一切のタイポグラフィスタイルが当たっていない（`prose`/typography プラグイン未導入、見出し・リスト・引用・コードブロック・表を狙う CSS が存在しない）。Tailwind v4 の Preflight が見出しを `font-size: inherit; font-weight: inherit` に、`ul`/`ol` を `list-style: none; margin:0; padding:0` にリセットするため、`sanitizeReadmeHtml` が正しく `<h3>`〜`<h6>` や `<ul>`/`<li>` を出力していても **視覚的には素のテキストと区別がつかない**。これはスクリーンショットの症状（見出し・リスト・段落が同じ大きさで縦に並ぶ、リストにマーカーが無い、インラインコードだけ等幅）と完全に一致する。許可リストの拡充（`<details>` 等）は副次課題であり、優先度はこの CSS 欠落より低い。

## 根拠 1: 実出力の確認（`bcaudan/jasmine-spec-reporter`）

```
curl -s "https://gem-hunter.kinamocchi-tech.workers.dev/ja/repos/bcaudan/jasmine-spec-reporter"
```

RSC ストリーミングのため素の HTML には README 本文が直接出ず、レスポンス末尾の `<div hidden id="S:1">...</div>`（クライアントが `$RC("B:1","S:1")` で差し込む確定済みコンテンツ）に本文が入っている。抽出結果（`/tmp/readme_section.html`）:

```html
<section aria-labelledby="readme-heading" class="mt-6">
  <h2 id="readme-heading" class="text-lg font-semibold">README</h2>
  <div class="mt-2 max-w-none space-y-3 text-sm leading-relaxed break-words">
    <div><div><h3>jasmine-spec-reporter</h3><a href="#jasmine-spec-reporter"></a></div>
    <p>...badges (img)...</p>
    <p>Real time console spec reporter for jasmine testing framework.</p>
    <p><a ...><img src="...screenshot.gif" alt="" /></a></p>
    <div><h3>Usage</h3><a href="#usage"></a></div>
    <div><h4>Installation</h4><a href="#installation"></a></div>
    <p>Install <code>jasmine-spec-reporter</code> via npm:</p>
    <div><pre><code>npm install jasmine-spec-reporter --save-dev
    </code></pre></div>
    <div><h4>Examples</h4><a href="#examples"></a></div>
    <ul><li><a ...>Jasmine node tests</a></li>...</ul>
    ...
    <div><h3>Development</h3><a href="#development"></a></div>
    <div><h4>Requirements</h4><a href="#requirements"></a></div>
    <ul><li>npm &gt;= 5</li></ul>
    <div><h4>Commands</h4><a href="#commands"></a></div>
    <ul><li>install dependencies: <code>npm install</code></li>...</ul>
  </div>
</section>
```

**確認できたこと**:
- `sanitizeReadmeHtml` の見出し +2 降格は正しく機能している（`h1→h3`, `h2→h4` が実際に出力されている）
- `<ul>`/`<li>`・`<pre><code>`・`<p>`・`<img>`・アンカーリンクはすべて正しくタグとして出力されている（=許可リスト自体はここでは機能している）
- コンテナ div のクラスは `mt-2 max-w-none space-y-3 text-sm leading-relaxed break-words` のみ。`prose` クラスも、見出し・リスト個別のスタイルクラスも **一切付いていない**（`src/ui/readme-section.tsx:128`）

## 根拠 2: CSS 側の裏付け

- `package.json` / `app/globals.css` を grep しても `@tailwindcss/typography` / `prose` は **一件もヒットしない**
- `app/globals.css:1` は `@import "tailwindcss"`（Tailwind v4）。v4 の Preflight は既定で以下を行う:
  - `h1`〜`h6`: `font-size: inherit; font-weight: inherit;`（ブラウザ既定の拡大・太字を打ち消す）
  - `ul`, `ol`: `list-style: none; margin: 0; padding: 0;`（マーカー・インデントを消す）
  - `blockquote`, `p`, `figure`: `margin: 0`
- 一方 `code` 要素はブラウザの UA スタイルシートが `font-family: monospace` を持ち、Preflight はこれを打ち消さない（`font-family` は Preflight のリセット対象外）ため、**インラインコードだけ等幅で残る** — スクリーンショットの症状と一致する

→ `src/ui/readme-html.ts` は「危険なタグを落とす」役割は果たしているが、**「見た目を与える」役割を持つ CSS が存在しない**。これは `readme-html.ts` の実装の問題ではなく `src/ui/readme-section.tsx:128` のコンテナ クラス、または `app/globals.css` 側の欠落。

## GitHub レンダリングとの差分（現状の許可リストで落ちる要素）

`bcaudan/jasmine-spec-reporter` の README では未検証だが、`ALLOWED_TAGS` / `transformTags`（`src/ui/readme-html.ts:46-104`）を突き合わせると、GitHub の README レンダリングに一般的に含まれる以下は **構造的に必ず落ちる**（sanitize-html の `disallowedTagsMode` 既定 `discard` によりタグは消え中身のテキストだけ残る）:

| GitHub の要素 | 現状 | 備考 |
|---|---|---|
| `<details>`/`<summary>`（折りたたみ） | 落ちる | `ALLOWED_TAGS` に無し。中身は展開済み状態でそのまま流れ込む |
| タスクリストの `<input type="checkbox" disabled checked>` | 落ちる | `input` はそもそも禁止タグ（意図的・XSS 対策として妥当） |
| シンタックスハイライトの `<span class="pl-*">` | 落ちる（`span` 自体は許可だが `class` 属性が `ALLOWED_ATTRIBUTES` に無い） | コードブロックが単色になる。`pre`/`code` の中身が `<span class="pl-c1">`,`<span class="pl-s">` 等で構成されている場合、タグは残るが色分けクラスが剥がされ実質プレーンテキスト表示 |
| GitHub アラート記法 `> [!NOTE]` 由来の `<div class="markdown-alert markdown-alert-note">` | 落ちる（`div` は許可だが `class` 未許可） | 注意喚起の枠・アイコンが消え、通常の引用/段落と同じ見た目になる |
| 絵文字画像 `<g-emoji>` | **タグ自体が非標準要素**。`ALLOWED_TAGS` に無いため落ちる | 中のテキスト（Unicode 絵文字 or alt）は残る想定だが要実機確認 |
| バッジ・アンカー用 `<svg class="octicon">` | 落ちる | `svg` は `ALLOWED_TAGS` に無し。見出し横のリンクアイコン等が消える（実害は小さい） |
| 脚注 `<sup id="fnref-...">` / `<section class="footnotes">` | `sup` はタグ許可だが `id`/`class` 属性は許可されていない（`ALLOWED_ATTRIBUTES` に `sup` のエントリ無し） | 脚注番号は表示されるがジャンプできない可能性 |
| `<table>` の `class="table" `等の GitHub 独自属性 | 落ちる（`table`/`th`/`td` の属性は `colspan`/`rowspan` のみ許可） | 罫線自体は自前 CSS 次第（後述） |

⚠️ **推定であることの明記**: `api.github.com` への直接アクセスがこのセッションから 403 になる可能性が高いため、上記は `src/ui/readme-html.ts` の許可リストとの静的突き合わせによる推定。`bcaudan/jasmine-spec-reporter` の README には `<details>` やアラート記法が含まれていない（今回の実出力では未観測）。実測が要る場合は `<details>` や `> [!NOTE]` を含む README（例: 多くの大型 OSS）で別途 curl 検証が望ましい。

## 「書式が反映されている」と言える最低ライン

書式再現度のレンズとして、以下を満たせば「書式が反映された README」と言えると考える（優先度順）:

1. **見出しの階層が視覚的に分かる**（h3 > h4 > h5 の順でフォントサイズ/太さが段階的に小さくなる）— 現状 **未達**（Preflight で inherit のため段階なし）
2. **リストにマーカーとインデントがある**（`ul` は `disc`、`ol` は数字、ネストで字下げ）— 現状 **未達**
3. **コードブロック（`pre`）が枠・背景色・等幅フォントで区別される**（インライン `code` との区別も含む）— 現状 **未達**（`pre` に何のスタイルも無く、中の `code` だけ UA 既定の等幅が乗る。枠や背景は無い）
4. **表に罫線がある**（`table`/`th`/`td` に border）— 現状 **未達**（同上、CSS 皆無なら罫線なしで単なる連続テキストになる可能性が高い。要実機確認だが `readme-section.tsx` にテーブル用 CSS が無い以上ほぼ確実）
5. **引用（`blockquote`）が引用と分かる**（左ボーダー・インデント・色の違い）— 現状 **未達**
6. **画像が原寸で溢れない**（`max-width: 100%` 相当）— `img` に `width`/`height` 属性は転写しているが、CSS 側で `max-width: 100%; height: auto` を強制していないとレイアウト崩壊の恐れ。要確認

**この 6 項目のうち 1 つも現状の CSS では保証されていない。** つまり `readme-html.ts` の許可リスト云々よりも先に、**コンテナへの typography CSS 付与が必須**（`@tailwindcss/typography` の `prose` クラス採用、または自前の見出し/リスト/pre/table/blockquote スタイル定義のどちらか）。

## 見出し +2 降格が書式に与える影響

`HEADING_SHIFT`（`h1→h3` … `h5`/`h6→h6`）自体は **ページの見出し階層をユーザーが期待する場所に収める**（ページ全体の `h1` はサイトタイトル、`h2` はセクション見出し「README」なので README 内部は `h3` 以下にするのが正しい設計判断）という点で妥当。ただし今回の不具合との関係で 2 点指摘する:

1. **`prose` クラスを後から導入する場合、`prose-h1`/`prose-h2` 用のスタイルは「使われない」ことになる。** typography プラグインは既定で `h1`〜`h6` 全部にスタイルを定義するため実害はないが、`h1`/`h2` は README 内に絶対出現しない（`transformTags` で必ず `h3` 以上に変換される）ことをスタイル設計側が前提にしてよい。
2. **`h5`/`h6` が両方 `h6` に丸められる**（cap）ため、GitHub 側で `h5` と `h6` の見た目差（フォントサイズがほぼ同じ）がさらに縮まる。書式再現度への実害は小さい（GitHub 自身も h5/h6 の差はごく僅か）。

いずれも「見出し降格」自体は書式崩れの原因ではない。**原因はシフト後のタグに対応する CSS が無いこと。**

## 過剰再現の弊害（線引きの提案）

以下は **再現すべきでない／慎重であるべき** 要素と理由:

- **GitHub 独自クラス（`pl-*` シンタックスハイライト・`octicon`・`markdown-alert-*`）への依存**: これらのクラス名に依存したスタイルを自サイトに実装すると、GitHub 側の内部実装変更で無言のまま崩れる密結合になる。シンタックスハイライトが欲しいなら、自前で `highlight.js`/`shiki` 等をコードブロック言語ヒントから独自適用する方が保守可能（ただし別 Issue 相当のスコープ）
- **バッジ画像（`img`）をそのまま原寸表示**: `shields.io`/Travis CI 等の小さいバッジが README 内に列挙されると、レイアウト次第では不格好に大きく見える・並びが崩れる。`prose img` の既定（ブロック要素化・`max-width:100%`）だけだとバッジが 1 枚ずつ改行される崩れ方をしやすい。バッジ画像を検出して抑制する（例: 高さ制限）といった特別扱いは過剰実装になりやすく、「読めればよい」の最低ラインを超えるため優先度低
- **`<details>`/タスクリストの完全再現（インタラクティブ化）**: `<details>` を許可タグに追加し `open`/`disabled` 等の属性も通す実装は、クリック挙動・アクセシビリティ（`role`）まで作り込むと工数が跳ねる。「展開済みの中身がそのまま読める」（現状の discard 挙動）を許容範囲とし、折りたたみ UI の完全再現は後回しでよい
- **自サイトの視覚言語との衝突**: `prose` を無条件適用すると、GitHub 由来のインラインスタイル的な色使い（例えばリンク色・強調色）が sidebar/shadcn デザイントークン（`--color-primary` 等・`app/globals.css` 参照）と衝突する可能性がある。`prose-neutral` 系のニュートラルバリアントを使うか、`--tw-prose-*` 変数を自サイトのデザイントークンにマッピングし直す一手間が必要（そのまま `prose` を貼るだけでは色が浮く恐れ）

## 反対されうる点

- 「これは CSS の問題であって `readme-html.ts`（サニタイズ層）の問題ではないので、このレンズのスコープ外では」という反論があり得る。しかし今回の飼い主指摘（「書式が反映されない」）の実機症状は **タグの欠落ではなく CSS の欠落で 100% 説明がつく** ため、書式の再現度を論じる上でこの事実を外すと誤った方向（許可タグを増やす）に工数を投じてしまうリスクがある。あえてスコープに含めた
- `<details>`/シンタックスハイライト等の許可リスト差分は `bcaudan/jasmine-spec-reporter` では実測できておらず、静的コード突き合わせによる推定に留まる点は弱い根拠。他 lens（`removal_impact` 等）が別リポジトリで実測すれば補強できる
