# site/ — gem-hunter ランディングページ

GitHub Pages で配信する静的ランディングページの **ソース** です。

- 公開 URL: <https://kai-kou.github.io/gem-hunter/>
- 公開方法: `main` の `site/` をそのまま `gh-pages` ブランチのルートへ配置する
  （GitHub Actions は本リポジトリで制限中のため、CI ではなくセッションが同期する）

## 構成

| パス | 役割 |
|---|---|
| `index.html` | ランディングページ本体（単一ページ・JavaScript なし） |
| `404.html` | GitHub Pages のカスタム 404 |
| `assets/styles.css` | スタイル。トークンは `app/globals.css` のセマンティックトークンと同値 |
| `assets/fonts/geist-latin.woff2` | 本文フォント Geist（latin サブセット・SIL OFL 1.1。`Geist-OFL.txt` を同梱） |
| `assets/img/shot-*.webp` | アプリの実画面のスクリーンショット |
| `assets/img/ogp.png` | OGP 画像（1200×630） |
| `.nojekyll` | Jekyll ビルドを止める（`_` 始まりのパスが消えるのを防ぐ） |

## 設計上の約束

- **外部 CDN に依存しない**（フォントも自前配信）。ページ内 JavaScript はゼロ
- **相対パス** で参照する（GitHub Pages のサブパス配信で壊れないため）。
  例外は 2 つだけ: ① OGP と canonical は仕様上 **絶対 URL** ②
  **`404.html` はサブパス付きの絶対パス**（`/gem-hunter/...`）。カスタム 404 は任意の階層の
  リクエストに対して返るため、相対パスだと深い階層で確実に壊れる
- **CTA の優先順位は ① 本番ツール ② GitHub リポジトリ**。この順序を崩さない
- 掲載する機能は **実装済みのものだけ**。未実装の構想を載せない。
  🔴 **本番で無効化されている機能も「使える」と書かない**（例: OAuth 環境変数が未供給の間は
  ログインに言及しない。判断の経緯は Issue #360 の議論記録）
- **アニメーションで `opacity` を動かさない**。初回描画で `opacity: 0` の要素は LCP 候補から
  永久に除外され、回線が細いほど白画面の時間が伸びる（`transform` だけで出現させる）
- 配色・角丸・コントロール寸法は `app/globals.css` / `docs/03_design/ui-ux/ui-ux-guidelines.md` に合わせる

## ローカル確認

```bash
python3 -m http.server 8098 --directory site
# http://localhost:8098/ を開く
```

⚠️ `404.html` は上記の理由でサブパス前提の絶対パスを持つため、**ローカル配信ではスタイルが当たらない**
（`/gem-hunter/assets/...` がローカルのルート配信と噛み合わない）。見た目の確認は公開後の
`https://kai-kou.github.io/gem-hunter/存在しないパス` で行う。

## 公開前チェック

```bash
# 1. 数値の裏取り（LP に焼いてある「682 ケース」の内訳）
npx vitest run              # ユニット・結合
npx playwright test --list  # E2E

# 2. アクセシビリティ（axe を light / dark × 1280 / 390 / 320px で流す）
#    → 0 violations であること

# 3. Markdown の書式
python3 tools/check_cjk_markdown.py --changed
```

## スクリーンショットの更新

`tools/capture_lp_screenshots.mjs` を実行する（アプリをローカルで本番ビルド・起動してから撮る）。
手順はスクリプト冒頭のコメントを参照。
