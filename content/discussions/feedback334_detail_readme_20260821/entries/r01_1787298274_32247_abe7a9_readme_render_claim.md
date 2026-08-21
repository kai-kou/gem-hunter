<!--entry
author: readme_render
round: 1
kind: claim
ts: 2026-08-21T16:44:33+09:00
-->

# README 表示（F-4）レンダリング方式・安全性 — 結論

## 結論サマリー

| 争点 | 結論 |
|---|---|
| 取得形式（C） | **`Accept: application/vnd.github.html+json`（GitHub 側レンダリング済み HTML）を採用**。raw + 自前 Markdown パーサはこの Worker では不採用 |
| サニタイザ | **`sanitize-html`**（htmlparser2 ベース）。`parseStyleAttributes: false` で postcss 依存を切る |
| 相対リンク・画像 | GitHub API は relativize しない（**実測で確認済み**）。README エンドポイント自身が返す `html_url`/`download_url` から算出した base URL で自前解決が必須 |
| 表示量 | サーバー側で HTML 文字列の長さで切り詰め＋「GitHub で全文を見る」リンク常設 |
| 失敗時 | README 取得は詳細ページ本体の 404 判定と分離。ネストした `<Suspense>` で個別ストリーミングし、失敗時はインラインで代替リンクのみ表示（ページ全体を落とさない） |
| NFR-3 | 影響なし。README 処理は 100% サーバー側（`use client` 不使用）で完結するため、選ぶライブラリに関わらずクライアント JS はゼロ |

---

## 1. 取得形式の比較

GitHub の Contents API `GET /repos/{owner}/{repo}/readme` は `Accept` ヘッダで 2 メディアタイプを切り替えられる（[GitHub 公式 REST リファレンス](https://docs.github.com/en/rest/repos/contents) で確認済み）:

- `application/vnd.github.raw+json`（既定）: 生 Markdown 文字列
- `application/vnd.github.html+json`: GitHub のオープンソース Markup ライブラリでレンダリング済みの HTML 文字列

**この 2 択の決め手は Cloudflare Workers の CPU 予算**。`wrangler.jsonc` は `"limits": { "cpu_ms": 50 }` を宣言しており、`cloudflare-infrastructure.md` §259 は「🔴 現状（2026-08-20 実機確認）: 本アカウントは Workers Paid（$5/月 + 従量）である」と明記している。つまり `limits.cpu_ms` は **現在まさに有効**（同ドキュメントも「Free では意味を持たないが Paid へ上げた瞬間に効く」と注記）。1 リクエストあたり 50ms の CPU 予算しかない中で、GFM（テーブル・タスクリスト・オートリンク・脚注等）まで含む Markdown を自前で AST 化してから HTML へ変換するのは、GitHub 側が既にやってくれている作業をもう一度 CPU で払い直すことになる。README は数十 KB になることも珍しくなく、自前パースの CPU コストは無視できない。**HTML 方式なら「サニタイズ（1 パスの HTML パース＋フィルタ）」だけで済み、CPU コストが小さく安定する**。

### ライブラリ比較（自前 Markdown レンダラを採る場合の参考・bundlephobia 実測）

| ライブラリ | 役割 | gzip サイズ（概算） | Workers ランタイム互換性 |
|---|---|---|---|
| `marked` | Markdown→HTML（軽量・GFM 拡張は別途） | 約 12.7 KB | 純 JS・DOM 非依存。互換 |
| `micromark`（remark の内部エンジン） | CommonMark トークナイザ | 個別に小さいが `remark-gfm` 等を積むと合算で増える | 純 JS・互換 |
| `react-markdown` + `remark-gfm` | React 要素として描画（unified/remark エコシステム） | `react-markdown` 約 34 KB + `remark-gfm` 約 9.8 KB | 純 JS・互換。Server Component として使う分にはクライアント JS は増えない |
| `markdown-it` | 高機能・プラグイン豊富 | 未計測（同系統で 20〜30 KB 帯が相場） | 純 JS・互換 |

いずれも Workers（DOM 非依存の純 JS 変換）としては動作可能。**ただし採用しない**。理由は上記の CPU 予算に加え、GFM 完全互換（タスクリスト・脚注・オートリンク・絵文字ショートコード・シンタックスハイライト）を自前で仕上げるコストが、GitHub がサーバー側で既に提供している出力を単に受け取るコストを上回るため（YAGNI・過剰実装回避）。

**根拠**: GitHub REST API 公式ドキュメント（WebFetch で取得・確認済み）、`wrangler.jsonc:11`、`docs/03_design/infrastructure/cloudflare-infrastructure.md:156,259`、bundlephobia API 実測値。

**反対されうる点**: 将来 README の構造解析（Q-2 の「README の構造品質」指標化など Gem Score 拡張）が必要になった場合、HTML 方式では Markdown の構文情報（見出し階層・リンク密度等）が失われており AST 解析に不向き。その時が来たら raw 方式 + 自前パーサへの切り替えを再検討する必要がある（現時点の F-4 スコープでは非該当）。

---

## 2. XSS 対策の具体

### GitHub 側の出力を無条件に信頼しない

GitHub は github.com 上での表示のために既に一定のサニタイズ（`<script>`/`<style>`/`<iframe>`/`on*` 属性の除去等）を行っているとみられるが、**これは github.com というホスト・CSP・出所の文脈で安全なだけ** であり、①この API 出力に対する将来のサニタイズ仕様変更を我々が保証できない、②任意の第三者（リポジトリオーナー）が完全に自由に書ける文字列を `dangerouslySetInnerHTML` で自ドメインの DOM に注入する以上、多層防御としてこちら側でも独立にサニタイズすべき。実測で取得した本リポジトリ自身の README HTML には `<script>` `<style>` `<iframe>` `onerror=` `onclick=` `javascript:` は含まれていなかったが（悪意ある内容でないため当然）、これは「安全である証拠」ではなく単に「テストケースが無害だった」だけなので判断根拠にしない。

### 採用: `sanitize-html`（htmlparser2 ベース）

- **なぜ `sanitize-html` か**: `DOMPurify`（`isomorphic-dompurify`）は Node 環境で動かすために内部で `jsdom` を要求する構成が一般的で、`jsdom` は `canvas` 等のネイティブ依存や `window`/`document` の完全実装を前提にしており、**Workers ランタイム（workerd）では動作しない**（DOM 非搭載・`nodejs_compat` でも jsdom の要求する Node API 全体はカバーされない）。除外。
- `rehype-sanitize`（`defaultSchema` が「GitHub style sanitation」を謳っており意味的には理想的）も候補にしたが、これは `rehype-parse`（内部で `parse5`＝フル HTML5 準拠パーサ）とセットで使う必要があり、bundlephobia 実測で `rehype-parse` 単体が **gzip 60.6 KB**（`sanitize-html` の 56.2 KB と同等以上）。「AST 系は軽い」という予断は誤りだった。加えて `parse5` は spec 完全準拠を優先する分、`htmlparser2`（`sanitize-html` の内部パーサ）より低速な傾向があり、cpu_ms 予算の観点では `sanitize-html` の方が有利。**Worker バンドルサイズ自体は 3 MB gzip 上限に対してどちらを選んでも誤差レベルだが、CPU 時間の観点で `sanitize-html` を推奨する。**
- `sanitize-html` は URL 書き換え（`transformTags`）とサニタイズを同一パスで行えるため、後述の相対リンク解決とサニタイズを 1 回の HTML パースで完結できる（rehype 構成だと「rewrite プラグイン」＋「sanitize プラグイン」の 2 段になるが AST 上なので追加パースは不要という点は同等）。

### 許可方針（ホワイトリスト）

- **禁止**: `script` `style` `iframe` `object` `embed` `form` `svg`（`use`/`foreignObject` 経由の XSS ベクタを避けるため意図的に不許可。README 内の手描き SVG バッジ等は表示されなくなるが安全側に倒す）、全 `on*` イベント属性、`style` 属性（`parseStyleAttributes: false` にして postcss 依存自体を切る。GitHub の構文ハイライトはクラスベースで inline style に依存しないため実害は小さい）
- **許可スキーム**: `a[href]` は `http` `https` `mailto` のみ、`img[src]` は `http` `https` のみ（`data:` は SVG 経由の XSS を避けるため両方とも不許可）。`javascript:` 系は当然除外
- **許可タグ/属性**: 見出し `h1`-`h6`（`id` 許可・後述のアンカー整合のため）、`p` `a[href]` `ul` `ol` `li` `blockquote` `pre` `code[class]`（`class` は `/^(language-|pl-)/` の正規表現許可のみ。GitHub 構文ハイライトのトークンクラス。対応 CSS を持たなければ単に無色表示になるだけで無害）、`table` `thead` `tbody` `tr` `th` `td`、`img[src|alt|width|height]`、GFM タスクリスト用に `input[type=checkbox][disabled][checked]`（`type` は `checkbox` 固定のみ許可）、折りたたみセクション用に `details` `summary`（GitHub README で多用される）、`kbd` `sub` `sup` `hr` `br` `del` `em` `strong`

### 外部リンクの `target`/`rel`

`rehype-sanitize` の `defaultSchema` は `a` タグの `target`/`rel`/`style`/`class` を仕様上明示的に不許可にしている（Context7 で確認: 「Note: these 3 are used by GFM footnotes...」のコメント付きで `target` `rel` は許可リストに **存在しない**）。攻撃者が指定した値をそのまま通す設計にはせず、**サニタイズ後の後処理として全ての外部 `<a href="http(s)://...">` に固定値 `target="_blank" rel="noopener noreferrer"` をこちらで一律付与する**（`repository-detail.tsx` のタイトルリンクと同じ既存パターンに合わせる）。

**根拠**: bundlephobia API 実測、Context7 (`/rehypejs/rehype-sanitize`, `/apostrophecms/sanitize-html`) 取得ドキュメント、`src/ui/repository-detail.tsx:71-83`（既存の `target="_blank" rel="noopener noreferrer"` パターン）。

**反対されうる点**: `svg` 全面禁止は GitHub 公式サニタイザより厳しく、CI バッジ等で古い形式（img ではなく inline svg）を使っている README は表示崩れが起きる。実害は「一部装飾が消える」程度でセキュリティ上は安全側なので許容範囲と判断するが、UX 上の劣化として認識しておくべき。

---

## 3. 相対リンク・相対画像の解決（実測で確認）

**GitHub の HTML レンダリング API は相対パスを絶対 URL に書き換えない。** 本リポジトリ自身の README（`kai-kou/gem-hunter`）に対して実際に `GET /repos/kai-kou/gem-hunter/readme` を `Accept: application/vnd.github.html+json` で叩いて確認した:

```
href="./docs" href="./LICENSE" href="./docs/adr/0001-ui-stack.md" ...
```

これらは書き換えられずそのまま返る。ドキュメント上も明記されておらず（WebFetch で GitHub 公式ページを確認したが記載なし）、**実測でしか分からない仕様** だった。github.com 本体のリポジトリ表示ページは相対パスを解決して表示しているが、それは github.com のページレンダリングパイプライン固有の処理であり、Contents API の HTML 出力には適用されていない。

さらに **アンカー ID にも罠がある**: GitHub は見出しに `id="user-content-{slug}"`（`user-content-` プレフィックス付き）を振るが、見出し横のパーマリンクアイコンや README 内目次のリンクは `href="#{slug}"`（プレフィックスなし）を指す。github.com 本体ではこの不一致を吸収する仕組みがあるとみられるが、我々の埋め込み先ページにはそれが無いため、**このまま埋め込むと README 内のアンカーリンク（目次等）が一切機能しない**。

### 解決方針

`GET /repos/{owner}/{repo}/readme` のレスポンス自体が `html_url`（例 `https://github.com/kai-kou/gem-hunter/blob/main/README.md`）と `download_url`（例 `https://raw.githubusercontent.com/kai-kou/gem-hunter/main/README.md`）を返す（実測で確認済み・`ref`＝デフォルトブランチをここから取得できるため、**`GET /repos/{owner}/{repo}` 本体に `default_branch` を追加取得する必要はない**）。これらからベース URL を組み立て、サニタイズと同じ HTML パスの中で:

- `a[href]` がスキーム付き絶対 URL・`mailto:`・`#` 始まりのフラグメント以外なら `https://github.com/{owner}/{repo}/blob/{ref}/` を base に解決
- `#{slug}` 形式のフラグメントは `#user-content-{slug}`（既に `user-content-` 始まりならそのまま）に書き換え、見出し `id` と一致させる
- `img[src]` が相対パスなら `https://raw.githubusercontent.com/{owner}/{repo}/{ref}/` を base に解決

**根拠**: 実測（`curl` で本リポジトリの README を `application/vnd.github.html+json` / 既定 JSON の両方で取得・`html_url`/`download_url`/相対 `href` の実出力を確認済み）。

**反対されうる点**: 画像を持つ README で `raw.githubusercontent.com` への解決が正しいか（GitHub 本体は `camo.githubusercontent.com` プロキシ経由にする場合がある）は本リポジトリの README に画像が無く実測できていない。実装時に画像付き README（例: 検索結果から実在の公開リポジトリ）でもう一段実機確認することを推奨する。

---

## 4. 表示量の方針

巨大 README（数百 KB 級）をそのまま埋め込むと a) cpu_ms 予算内でのサニタイズ処理時間、b) レスポンスサイズ、双方に影響する。**サニタイズ後の HTML 文字列長で上限を設け（例: 一定文字数を超えたら切り詰め）、切り詰めた場合・切り詰めていない場合の両方で「GitHub で全文を読む」導線（`html_url` へのリンク）を常設する**（`repository.htmlUrl` の外部リンクと同じ `target="_blank" rel="noopener noreferrer"` パターン）。HTML 文字列の単純な文字数カットは中途半端な位置でタグを分断するリスクがあるため、サニタイズ後の DOM/トークン単位（`sanitize-html` の `exclusiveFilter` やブロック要素境界）で打ち切るのが安全。具体的な閾値は UX 判断（`ui_nav` ロール）と合わせて決める領域なので、ここでは「文字数ではなく安全な境界で切る」という実装制約のみを申し送る。

---

## 5. 失敗時のフォールバック — AC-5 の 404 制約との両立

`app/[locale]/repos/[owner]/[repo]/page.tsx` は **`<Suspense>`/`loading.tsx` を意図的に置いていない**。理由はコメントの通り「`notFound()` は Suspense 境界より前に呼ぶ必要があり、境界のフォールバックが一度でも描画されるとレスポンスヘッダが確定して 404 を返せなくなる」ため（`node_modules/next/dist/docs/01-app/03-api-reference/03-file-conventions/loading.md` で実際に確認: *"Place `notFound()` before those boundaries and before any `await` that may suspend."*）。

**この制約はページ本体（`repository` 取得＝404 の判定材料）にのみ適用される。** README 取得は 404 の判定に関与しない（README が無くても「リポジトリは存在する」という 200 の結論は変わらない）。したがって:

- `repository === null` の `notFound()` 判定は **従来どおり同期 `await` で行い、ストリーミングを一切開始させない**（変更なし）
- 404 でないと確定した **後**（＝ `main` の JSX ツリーの中、既存の統計表示より下）に **README 専用の新しい `<Suspense>` 境界を 1 つだけ追加** し、その内側で README を取得・レンダリングする非同期 Server Component を描画する。この境界に入るのは 404 判定が既に確定した後なので、AC-5 を一切壊さない
- 境界の `fallback` は軽量なスケルトン（テキスト 1〜数行程度。クライアント JS 不要）
- README 取得自体が失敗（レート制限・upstream エラー・パース失敗等）した場合は、**例外を投げて最寄りの `error.tsx` に落とさない**。README コンポーネント内部で `try/catch` し、失敗時は「README を読み込めませんでした。GitHub で見る」の 1 行 + `repository.htmlUrl` へのリンクを表示するだけに留める（詳細ページ全体を巻き込まない）
- README 不在（404）は `findDetail` と同じ `notFoundAsNull` パターンを再利用し `null` を返す契約にする（エラーではなく「README セクションを描画しない」という正常系の分岐として扱う）
- 非 UTF-8 / バイナリ混入は実測上 GitHub API 側で正規化済み（JSON 文字列として返る時点で UTF-8 が保証される。raw モードは `encoding: "base64"` を明示的に持つため呼び出し側で誤�った decode をする余地がない。今回採用する HTML モードはそもそも base64 を経由せずテキストとして返る＝実測で日本語含む README を破損なく取得できたことで確認済み）

**根拠**: `app/[locale]/repos/[owner]/[repo]/page.tsx` 冒頭コメント、`node_modules/next/dist/docs/.../loading.md`（本バンドル版 Next.js 16 の公式仕様を直接確認）、`GithubRepositoryQuery.request()` の既存 `notFoundAsNull` パターン（`src/infrastructure/github/github-repository-query.ts:70-78`）。

**反対されうる点**: ネストした `<Suspense>` を使うと、README 取得中はページが 2 段階でストリーミングされる（統計等が先に表示され、README が後から差し込まれる）。E2E テスト（Playwright）がこの非同期性を考慮していないと、README 部分の表示待ちをせずにアサーションして flaky になるリスクがある。SD-2 の E2E 実装時は `await expect(...).toBeVisible()` 等で明示的に待つ設計にする必要がある。

---

## 6. NFR-3（クライアント JS を増やさない）との両立

README の取得・パース・サニタイズ・URL 書き換えは **すべてサーバー側**（README 専用の async Server Component、`use client` なし）で完結し、完成した安全な HTML 文字列を `dangerouslySetInnerHTML` で埋め込むだけになる。したがって **1〜2 節でどのライブラリ（`sanitize-html` / `marked` / `react-markdown` 等）を選んでも、クライアントバンドルへの影響はゼロ**（これらはすべて Worker 側のサーバーバンドルにのみ計上される）。NFR-3 は取得形式・サニタイザ選定の判断材料にはならない（争点 C の期待に反して、この観点は他の 5 点ほど決定力を持たない、という結論自体が申し送り事項）。唯一の注意点は `<Suspense>` 境界そのものは React の標準機能でありクライアント JS 追加を意味しない（RSC のストリーミングはサーバー側の仕組み）。

**根拠**: React Server Components の基本仕様（`dangerouslySetInnerHTML` を使う純粋な Server Component はクライアントへ JS を送らない）、`wrangler.jsonc`/`open-next.config.ts` にクライアント最適化に関する特別な追加設定なし。

---

## 他ロールへの申し送り

- **`arch_domain` 宛て**: `RepositoryQueryPort` に `findReadme(name): Promise<ReadmeContent | null>` のような別ポートメソッドを足す設計を推奨（`findDetail` に合成しない）。理由: README は「無くても正常」「404 でも詳細ページ全体は落とさない」という `findDetail` と異なるエラーセマンティクスを持つため、契約を分けたほうが型で表現しやすい。取得元エンドポイントが別（`/readme` vs 本体）である点も合成しない理由になる。`E-2`「データソースは `GET /search/repositories` と `GET /repos/{owner}/{repo}` に限定」という既存宣言は `GET /repos/{owner}/{repo}/readme` を追加するために更新が必要（ACL のスコープ拡張）。
- **`ui_nav` 宛て**: 詳細ページの見出し階層変更（争点 A）と README セクションの見出し（"README" ラベル等）が衝突しないか確認してほしい。README 内の `<h1>`-`<h6>` は今回の許可方針でそのまま透過するため、ページの `h1`（リポジトリ名）と README 内の `h1` が並存し、見出しレベルの整合性（a11y の見出しナビゲーション）に影響する可能性がある。README 内見出しを `+1` レベルシフトする（`h1→h2` 等）処理を検討候補として挙げる。
- **表示量の具体閾値**（4節）は UX 判断が必要なため未確定のまま。
