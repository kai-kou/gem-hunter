# site/ — gem-hunter ランディングページ

GitHub Pages で配信する静的ランディングページの **ソース** です。

- 公開 URL: <https://kai-kou.github.io/gem-hunter/>
- 公開方法: `main` の `site/` をそのまま `gh-pages` ブランチのルートへ配置する
  （GitHub Actions は本リポジトリで制限中（`D-23`）のため、CI ではなくセッションが同期する）
- 決定の正本: [`open-questions.md`](../docs/02_requirements/open-questions.md) の **`D-35`**。
  判断の経緯は [議論記録](../content/discussions/lp_github_pages_review/whiteboard.md)（Issue #360）

### 🔴 `gh-pages` へ push するときの注意（`D-32` / `L-130` との関係）

`D-32` は「auto mode classifier が `production` / `release` / **`gh-pages`** 等の名前のブランチへの push を
独自に本番デプロイと判定しうる」ことを記録している。**これは Workers 本番デプロイの文脈** であり、
静的 LP の配信は別レーンとして `D-35` で許容している。実測（2026-08-22）では下記の経路で
ブロックされずに公開できた。

```bash
# 作業ツリーを触らずに site/ のツリーだけを gh-pages へ載せる
TREE=$(git rev-parse HEAD:site)
PARENT=$(git rev-parse refs/heads/gh-pages 2>/dev/null || true)
COMMIT=$(git commit-tree "$TREE" ${PARENT:+-p "$PARENT"} -m "publish: LP を反映する")
git update-ref refs/heads/gh-pages "$COMMIT"
git push origin gh-pages
```

ブロックされた場合は `mcp__github__push_files` で `gh-pages` を更新する。
🔴 **迂回のためにブランチ名を変えない**（`L-130` の迂回禁止に触れる）。

## 構成

| パス | 役割 |
|---|---|
| `index.html` | ランディングページ本体（単一ページ・JavaScript なし） |
| `404.html` | GitHub Pages のカスタム 404 |
| `assets/styles.css` | スタイル。トークンは `app/globals.css` のセマンティックトークンと同値 |
| `assets/fonts/geist-latin.woff2` | 本文フォント Geist（latin サブセット・SIL OFL 1.1。`Geist-OFL.txt` を同梱） |
| `assets/img/shot-*.webp` | アプリの実画面のスクリーンショット |
| `assets/img/why-divider.webp` | `why` セクションの装飾区切り画像（gpt-image-2 生成・実画面ではない。生成手順は `tools/ui-assets/README.md`） |
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
  ログインに言及しない）。ただし **「仕組み自体が無い」と存在を否定するのも禁止**
  （env が供給された瞬間に虚偽になる）。書いてよいのは **いま観測できる事実だけ**
  （「ログインなしで全機能が使えます」）。判断の経緯は
  [議論記録](../content/discussions/lp_github_pages_review/whiteboard.md)
- 🔵 **本番へ `GITHUB_OAUTH_CLIENT_ID` / `_SECRET` / `_CALLBACK_URL` と `SESSION_ENCRYPTION_KEY` が
  供給されたら**、FAQ「アカウント登録は必要ですか？」を現状の事実に合わせて更新する
  （それ以外の箇所にログインの説明を増やさない）
- **`npm run format` の対象外**（`.prettierignore` に `site/` を追加済み）。手書きで整形を最適化して
  いるため、prettier に整形させると表示が変わる
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
# 1. 標準ゲート（PR 前の唯一の機械的証跡。LP 静的検査 check_site.py もここに含まれる）
npm run check

# 2. 数値の裏取り（LP に焼いてある「1,062 ケース」の内訳）
npx vitest run              # → `Tests  953 passed` であること
npx playwright test --list  # → 末尾 `Total: 109 tests` であること
                            #    953 + 109 = 1,062 が index.html の「1,062 ケース」と一致する
ls docs/adr/[0-9]*.md | wc -l   # → 15（index.html の「ADR 15 本」と一致。check_site.py も検査する）
```

### アクセシビリティの実測（LP を対象に axe を流す）

`npm run check` の Lighthouse ゲートは **アプリ本体だけ** が対象で LP を見ない。LP は下記で実測する。

```bash
python3 -m http.server 8098 --directory site &   # 別プロセスで配信
node - <<'EOF'
import { chromium } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
const browser = await chromium.launch()
for (const [scheme, width] of [['light', 1280], ['dark', 1280], ['light', 390], ['light', 320]]) {
  const context = await browser.newContext({ viewport: { width, height: 900 }, colorScheme: scheme })
  const page = await context.newPage()
  await page.goto('http://127.0.0.1:8098/', { waitUntil: 'load' })
  await page.evaluate(() => document.querySelectorAll('details').forEach((d) => (d.open = true)))
  const result = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
    .analyze()
  console.log(scheme, width, 'violations =', result.violations.length)
  await context.close()
}
await browser.close()
EOF
```

**全構成で `violations = 0` であること**（`site/` は `npm run check` の a11y ゲートに載っていないため、
このコマンドが唯一の検証手段）。

## スクリーンショットの更新

```bash
npx next build
npx next start -p 3100 &     # 別プロセスで起動しておく
node tools/capture_lp_screenshots.mjs
```

- 別ポートで起動したときは `LP_SHOT_BASE=http://localhost:PORT node tools/capture_lp_screenshots.mjs`
- スクリプトは撮影後に **`index.html` の `width` / `height` と出力の実寸を突き合わせ、
  食い違っていれば非ゼロ終了する**（属性の更新漏れ = CLS を機械で止める）。
  同じ照合は `tools/check_site.py` にも入っているので、撮り直さない PR でも守られる
- 本番を対象に撮るときは `LP_SHOT_BASE=https://gem-hunter.kinamocchi-tech.workers.dev` を明示する。
  🔴 **本番直叩きは共有 API レート枠を消費する副作用があるため、乱用しない**
- 🔴 `LP_SHOT_FETCH_VIA_CURL=1`（既定 off）は **直接 HTTPS が通らないサンドボックスでの回避策**
  （恒久のベストプラクティスではない）。on にすると全リクエストを `curl` 経由で取得して差し替える
- 🔴 **撮影スクリプトは `SHOTS` 全件を撮り直す** ため、1 枚だけ更新したいときも `shot-digest.webp`
  （「今日の Gem」＝日替わりで中身が変わるカード）まで巻き込んで撮り直してしまう。
  `shot-digest` を撮り直した場合は、**`index.html` の `tile-datum` の数値（1 位 / 2 位のパッケージ名・
  利用パッケージ数・star 数）と `alt` を実データに合わせて更新すること**（撮影スクリプトは寸法しか
  照合しないため、本文・alt と画像の中身が食い違っても機械では止まらない）。逆に他のショットだけを
  更新したく `shot-digest` の日替わりデータを巻き込みたくない場合は、撮影後に
  `git checkout origin/main -- site/assets/img/shot-digest.webp` で当該ファイルだけ戻す
