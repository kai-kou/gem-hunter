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
- **相対パス**で参照する（GitHub Pages のサブパス配信で壊れないため）。
  OGP と canonical だけは仕様上 **絶対 URL**
- **CTA の優先順位は ① 本番ツール ② GitHub リポジトリ**。この順序を崩さない
- 掲載する機能は **実装済みのものだけ**。未実装の構想を載せない
- 配色・角丸・コントロール寸法は `app/globals.css` / `docs/03_design/ui-ux/ui-ux-guidelines.md` に合わせる

## ローカル確認

```bash
python3 -m http.server 8098 --directory site
# http://localhost:8098/ を開く
```

## スクリーンショットの更新

`tools/capture_lp_screenshots.mjs` を実行する（アプリをローカルで本番ビルド・起動してから撮る）。
手順はスクリプト冒頭のコメントを参照。
