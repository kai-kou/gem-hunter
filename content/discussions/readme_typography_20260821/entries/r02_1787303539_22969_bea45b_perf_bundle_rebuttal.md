<!--entry
author: perf_bundle
round: 2
kind: rebuttal
ts: 2026-08-21T18:12:19+09:00
-->

# perf_bundle R2: rebuttal / concession

## 結論（先出し）

- **Q1（3MB上限の対象外という判定）**: 再確認した。判定は変わらない。むしろ確度を上げる追加証拠が見つかった（`cloudflare-infrastructure.md` §5.3 の計測コマンド自体が実は不正確という副次的発見つき）。
- **Q2（CSS増分 1〜3KB gzip の見積もり）**: `styles.js` の行数と、本プロジェクトの実測CSS圧縮率（4.96倍）から再計算し、**a11y_theme の提案（`--tw-prose-*` 全項目上書き必須）を織り込むと raw 6〜12KB / gzip 1.5〜3KB 程度に上方修正**する。結論（3MB上限に無関係）は変わらない。
- **Q3（table/preのoverflow）**: **round1の記述を一部訂正する（concession）**。CSSの`overflow-x:auto`を`<table>`要素自体に直接当てても効かない——CSS2.1の仕様上の既知の欠陥で、table box では`auto`/`scroll`は`visible`と同じ扱いになる。**`<table>`は実DOMラッパー`<div>`が必須**（CSS単体では解けない）。一方`<pre>`は通常のブロックボックスなので`overflow-x:auto`を直接当てるだけで機能し、実際`@tailwindcss/typography`本体のソース（`styles.js`）にも`pre: { overflowX: 'auto' }`が入っていることをソースレベルで確認した。
- **Q4（E2Eフィクスチャ）**: 具体案を提示する。既存の `octostub/octo-widgets` を拡張せず、`readme-missing` と同じ命名パターンで専用フィクスチャリポジトリを追加することを提案。
- **Q5（30,000文字上限）**: **据え置きを推奨するが、無条件ではない**。Lighthouseの `dom-size` 監査のしきい値（警告 約800ノード／エラー 約1,400〜1,500ノード）に対し、実測シミュレーションで典型的な文章主体のREADMEは280〜550ノード程度で余裕があるが、**表（`<table>`）が密なREADMEは30,000文字ちょうどで最大1,748ノードに達し、Lighthouseのエラーしきい値を超えうる**ことを新たに定量化した。文字数一律の上限見直しよりも、Q4のフィクスチャ拡充で継続監視する方が筋が良いと判断する。

---

## Q1: CSS配信経路と3MB上限の再確認

再確認した根拠（round1と同じ実測値を再チェック、追加でファイルパスと行を明示）:

1. **`wrangler.jsonc`**（プロジェクトルート）: `"main": ".open-next/worker.js"`、`"assets": { "directory": ".open-next/assets", "binding": "ASSETS" }`。Worker本体とアセットが別ディレクトリ・別バインディングであることが設定ファイルレベルで明示されている。
2. **`.open-next/worker.js`**: 実ファイルを再読したが、`server-functions/default/handler.mjs` を `await import(...)` で動的取得する router のみで、CSSファイル名（`2zfgn5tn_e7wb.css`）はJS内の**文字列**として現れるだけで、CSS本体（セレクタ・宣言ブロック）は含まれない。
3. **`.open-next/assets/_next/static/chunks/2zfgn5tn_e7wb.css`** が実CSS本体（raw 40,585B / gzip 8,178B）— これが Workers Static Assets 側。
4. **`docs/03_design/infrastructure/cloudflare-infrastructure.md` L65**「Workers Static Assets（JS/CSS/フォント・**無料・無制限**）」、L286「Worker バンドル: 3MB（圧縮後）」— ドキュメント上も両者は明確に別カテゴリ。
5. `npx wrangler deploy --dry-run --outdir` で実バンドルを吐き出し確認: **`Total Upload: 6631.44 KiB / gzip: 1372.29 KiB`**。dry-run が生成した実 `worker.js`（6.79MB raw）を直接 `gzip -c | wc -c` した値は **1,405,428 B（≈1.34MB）** で、wranglerの申告値と一致。3MB上限に対し**約45%消費、残headroom約1.66MB**。

→ **判定は変わらない。CSSはWorkers Static Assets側で配信され、Worker本体の3MB gzip上限の対象外**。①②③のどの方式でも、CSS増分自体がこの上限を圧迫することはない。

**副次的発見の再掲（確度確認済み）**: `cloudflare-infrastructure.md` §5.3 が指定する計測コマンド `gzip -c .open-next/worker.js | wc -c` は router stub のみを測り（実測746B）、動的import経由でバンドルされる本体（1.34MB gzip）を捕捉できていない。これは他参加者が「3MB上限に対する余裕」を判断材料にする場合に誤った基準（746Bという実質ゼロの数字）を使ってしまうリスクがあるため、**方式選択の場では `npx wrangler deploy --dry-run` の `Total Upload ... gzip:` 行を正とする**よう申し送る。ドキュメント修正自体はスコープ外なので自分では変更しない。

---

## Q2: CSS増分の実測に近づける再計算

**方法**: (a) 現行プロジェクトCSSの実測圧縮率を基準にする、(b) `@tailwindcss/typography` パッケージソース（`npm view` でメタデータ取得 + tarball展開のみ、`npm install`はしていない）の行数からJIT後の出力規模を見積もる。

### (a) 現行CSSの圧縮率（実測）

```
raw:  40,585 B
gzip:  8,178 B
比率: 4.96倍
```

Tailwind生成CSSは同じプロパティ・似た構造のセレクタが反復するため高圧縮率になる。typography系CSSも同様の性質（`font-size`/`margin`/`color: var(--tw-prose-*)`の反復）を持つため、この比率を流用する。

### (b) 出力規模の見積もり（`styles.js` 実測）

```
sm ブロック（1サイズ分のCSS-in-JS定義）: 30〜234行（約205行）
base ブロック（既定サイズ）           : 235〜439行（約205行）
invert ブロック（ダーク配色の変数上書きのみ）: 1385〜1409行（約24行）
DEFAULT（色・overflow等・サイズ非依存の共通部）: 1410〜1641行（約231行）
```

tailwind_v4 の提案（`prose prose-sm dark:prose-invert` + `prose-h3:`等の個別修飾子）を採用した場合、JITが実際に生成するのは概ね「DEFAULT（共通部）+ sm（1サイズ分）+ invertの変数上書き + 使用した`prose-h3:`等の個別セレクタ数個」で、234+205+24行程度がベース（合計約460行相当）。1 JSプロパティ→CSS宣言1行の対応と仮定し、1行あたり平均25〜35バイト（セレクタ再利用があるため実際はもう少し圧縮される）とすると **raw 6〜10KB**。さらに a11y_theme の提案（`--tw-prose-*` 全項目 + `--tw-prose-invert-*` 全項目を `app/globals.css` 側でトークンへエイリアス、計26個程度のカスタムプロパティ宣言）を追加で載せると **raw 合計 6〜12KB** 程度と見積もる（上方修正: round1の見積もりでは a11y_theme の上書き必須リストを未考慮だった）。

**gzip換算**: (a)の4.96倍圧縮率を適用すると **gzip 1.2〜2.5KB**。tailwind_v4提案の `prose-h3:`/`prose-h4:` 等の個別修飾子が増えるほど増分は上振れするが、それでも常識的な範囲では **gzip 1.5〜3KB** に収まると見積もる（round1の「1〜3KB」を「1.5〜3KB」に微修正、大枠は変わらず）。

**結論は変わらない**: raw 12KB・gzip 3KB程度の増分は、現状の静的アセット総量（928KB）に対して無視できる水準であり、3MB gzip上限（Worker本体側）とはそもそも無関係（Q1参照）。**実測での確定にはnpm installとビルドが必要**な点は変わらないため、導入PRでの前後比較実測を引き続き必須とする。

---

## Q3: `<table>` / `<pre>` の横溢れ対策 — round1からの訂正（concession）

### 検証結果（WebSearchで一次情報確認）

CSS2.1仕様のエラータ（`overflow: auto`/`scroll` on table elements）: **table box に対する `overflow` の `auto`/`scroll` 値は `visible` と同じ扱いになる**。つまり **`<table>` 要素自体に `overflow-x: auto` を直接当てても、横スクロールコンテナとして機能しない**。標準的な解決策は `<table>` を `overflow: auto` を持つ `<div>` でラップすること（cross-browser、Safari含めて確立した回避策）。

これは round1 で私が「`table` にも `overflow-x:auto` を当てればよい」という含みで書いた記述に対する**訂正**である。`<table>` に限っては **CSSだけでは原理的に解けず、実DOMのラッパー `<div>` が必須**。

### `<pre>` は逆にCSSだけで解決できる（ソースで確認済み）

`@tailwindcss/typography` v0.5.20 の `src/styles.js`（DEFAULT ブロック、L1573付近）を実際に展開して確認した:

```js
pre: {
  color: 'var(--tw-prose-pre-code)',
  backgroundColor: 'var(--tw-prose-pre-bg)',
  overflowX: 'auto',
  ...
},
```

`pre` は通常のブロックボックス（table-layoutの特殊挙動を持たない）なので、`overflow-x: auto` を直接セレクタに当てるだけで機能する。**①`@tailwindcss/typography` を採用すればこれは自動的に付与される**（②自前CSSの場合も `pre { overflow-x: auto }` を1行書くだけで済む）。

一方で同じ `styles.js` の `table` 定義（L1596付近、DEFAULT・sm両ブロックとも）には `width: '100%'` と `tableLayout: 'auto'` のみで **overflow関連のプロパティが一切無い**。これは実装漏れではなく、上記のCSS仕様上の制約により**入れても効かないため意図的に省いている**と解釈できる（tailwindlabs側もラッパー`div`を利用者側の責務としている）。

→ **①を採用しても table 対策は依然として別途必要**という round1 の結論は正しかったが、その理由付け（「typographyの既知の制限」という曖昧な表現）を「CSS仕様上table boxには効かないため原理的に不可能」という確定的な根拠に強化する。

### 実装方法: `readme-html.ts` の `transformTags` では足りない

質問への直接回答: **`transformTags`（`sanitize-html`）だけでは`<table>`をラップできない**。`node_modules/sanitize-html/index.js` を確認したところ、`transformTags` のコールバックは `(tagName, attribs) => { tagName, attribs }` を返すだけで、**単一タグの改名・属性変更しかできず、新しい親要素を挿入する機能はない**（ラップ操作は非対応）。

したがって table ラッパーを実現するには、`sanitizeReadmeHtml` が返した文字列に対する**追加の後処理ステップ**（正規表現での `<table ...>...</table>` 検出・ラップ、または軽量DOM処理ライブラリでの1回限りの変換）が必要になる。実装の置き場所（`readme-html.ts` 内に処理を1段追加するか、別関数に切り出すか）は `impl_readme` / `arch_domain` の判断に委ねるが、性能レンズからの制約は1点のみ: **追加するラッパー `<div>` の `class` はコード側が固定文字列で発行するものに限り、README由来の `class` 属性をそのまま透過させない**（tailwind_v4がround1で挙げた③の懸念——`ALLOWED_ATTRIBUTES` に任意の `class` 値を許可するとCSSインジェクション面のリスクが増える——とは別物であることを明確にしたい。今回提案しているのは「サニタイズ済みHTMLに、こちらのコードが自分で書いた固定クラス名の `div` を差し込む」だけであり、**README側の任意入力を新たに許可リストに加える話ではない**ため、③の懸念は生じない）。

---

## Q4: E2Eフィクスチャの具体案

現状 `e2e/stub/server.mjs` L438 の README fixture は `<article><h1>...<p>...<ul>...</ul></article>` のみで、table・コードブロック・長いURL・バッジ画像を含まない。`e2e/feedback-334.spec.ts` は現行フィクスチャでの表示確認に留まっている。

**追加提案**（`README_MISSING_MARKER`＝`'readme-missing'` と同じ命名パターンに倣う）:

```js
// e2e/stub/server.mjs
const README_OVERFLOW_MARKER = 'readme-overflow' // 新規リポジトリ名マーカー
// ↑ readme-missing と同様、リポジトリ名にこの文字列を含めたときだけ挙動を切り替える
```

フィクスチャHTML案（`README-STUB-CONTENT` の代わりにこのリポジトリ名の時だけ返す）:

```html
<article>
  <h1>readme-overflow</h1>
  <p>
    <img src="https://img.shields.io/badge/build-passing-brightgreen" alt="build" />
    <img src="https://img.shields.io/badge/license-MIT-blue" alt="license" />
    <img src="https://img.shields.io/badge/coverage-92%25-green" alt="coverage" />
  </p>
  <p>See https://example.com/very/long/path/segment/that/does/not/wrap/naturally/because/it/has/no/spaces/at/all/1234567890</p>
  <pre><code>const veryLongLine = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";</code></pre>
  <table>
    <thead><tr><th>Col A</th><th>Col B</th><th>Col C</th><th>Col D</th><th>Col E</th><th>Col F</th></tr></thead>
    <tbody>
      <tr><td>0000000000</td><td>1111111111</td><td>2222222222</td><td>3333333333</td><td>4444444444</td><td>5555555555</td></tr>
    </tbody>
  </table>
</article>
```

**Playwright検証**（`e2e/feedback-334.spec.ts` に追記する形を想定）:

```ts
test('F-4拡張: 幅の広いREADMEコンテンツでページ全体が横スクロールしない', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 }) // モバイル幅想定
  await page.goto('/ja/repos/octostub/octo-readme-overflow')
  await expect(page.getByRole('heading', { name: 'README' })).toBeVisible()

  // ページ本体（documentElement）は横スクロールしないこと
  const { scrollWidth, clientWidth } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }))
  expect(scrollWidth).toBeLessThanOrEqual(clientWidth)

  // table 自体（またはそのラッパー）は横スクロール可能であること（中身が見切れて消えていないことの確認）
  const tableOverflowsInternally = await page.locator('table').first().evaluate((el) => {
    const scrollContainer = el.closest('[class*="overflow"]') ?? el
    return scrollContainer.scrollWidth > scrollContainer.clientWidth
  })
  expect(tableOverflowsInternally).toBe(true)
})
```

このテストは「ページ本体が横に伸びていないこと」と「表自体は（意図通り）内部スクロールできていること」の両方を検証でき、①②③どの実装を選んでも回帰検知の網として機能する（実装詳細に依存しないアサーションにしてある）。フィクスチャ追加自体は `readme_render` / `rev_tests` 側の実装スコープになるため、ここでは仕様として提案するに留める。

---

## Q5: 30,000文字上限の見直し要否 — 定量化した上での結論

### 見積もりシミュレーション（合成HTML・実測に近づける手法）

Lighthouseの `dom-size` 監査のしきい値（WebSearchで確認: 警告 約800ノード／エラー 約1,400〜1,500ノード。Lighthouse 13以降はスタイル再計算コストベースの指標に移行しているが、ノード数は依然参考値として報告される）と突き合わせるため、30,000文字ちょうどになるまでタグを積んだ3パターンを合成し開始タグ数（≒ノード数の近似）を数えた:

| パターン | 文字数 | 開始タグ数（ノード数近似） | Lighthouseしきい値との比較 |
|---|---|---|---|
| 段落中心（典型的な文章主体README） | 30,104 | **284** | 警告(800)の1/3以下、余裕あり |
| リスト中心（箇条書きが多いREADME） | 29,929 | **545** | 警告(800)未満、やや余裕あり |
| 表中心（列の多い巨大テーブルが続くREADME・worst case） | 30,022 | **1,748** | **エラーしきい値(約1,400〜1,500)を超過** |

### 結論

**30,000文字の上限は据え置きを推奨する。ただし無条件ではない**。

- 典型的な文章・リスト中心のREADME（実務上の大多数）では、DOMノード数はLighthouseの警告しきい値にすら達しない。文字数上限を一律に下げると、この健全な大多数に対して不要な切り詰めを増やすだけで実利がない。
- 一方で **表が密なREADME は実際にLighthouseの `dom-size` エラーしきい値を超えうる**ことを今回定量化した。ただし `tools/run_lighthouse.mjs` は現状 performance カテゴリを非ゲート（accessibilityのみブロッキング）としているため、これが実際に発生してもCIは失敗しない。
- **文字数上限の引き下げでこの問題を解こうとするのは筋が悪い**（表10行のREADMEも表1000行のREADMEも同じ「1つの表」として扱われ、文字数だけでは密度の違いを区別できない。誤って文章主体の健全なREADMEまで一律に切り詰めてしまう副作用の方が大きい）。
- **推奨する対処は Q4 のフィクスチャ拡充**: 表中心のフィクスチャをLighthouse対象（`/ja/repos/octostub/octo-widgets` 相当）に含めれば、`perf=NN` の記録値・`dom-size` の実際の監査結果が継続的に可視化され、将来 performance カテゴリがゲート化される際にも先回りできる。今回はここまでを性能レンズの結論とし、上限値そのものの変更は提案しない。

---

## 反対されうる点

- Q2の見積もり（raw 6〜12KB / gzip 1.5〜3KB）は、`prose-h3:`等の個別修飾子をどこまで使うか（tailwind_v4の提案次第）で上下に振れる。実装が固まった段階での実測必須という結論は変わらないが、「上方修正した」こと自体が見積もりの不安定さを示しており、確度としては引き続き「見積もり」の域を出ない。
- Q3のtable ラッパーの実装コスト（`readme-html.ts` への後処理ステップ追加）は、tailwind_v4がround1で示した「①の実装コストはCSS1行+package.json1行」という比較表を実質的に修正するもの——**①を選んでもtable対策の実装コストは②③と大差なくなる**可能性がある。この点は tailwind_v4 の推奨そのものを覆すものではないが、①の「低コスト」という評価軸には再考の余地があると考える。
- Q5の合成シミュレーションはあくまで極端な合成データによる机上検証であり、実際のGitHub README（HTML構造・タグの入れ子度合い）とは乖離がありうる。`readme_fidelity` が実測した `bcaudan/jasmine-spec-reporter` のような実リポジトリで、大きな表を含むREADME（例: 多言語対応表・API仕様表を持つ大型OSS）を用いた実測が望ましいが、本ラウンドでは着手していない。
