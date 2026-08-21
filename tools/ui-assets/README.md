# UI 画像アセット

gem-hunter の装飾イラスト 5 点（logo / hero-idle / empty-result / not-found / og-background）を
`gpt-image-2` で生成し、配信用ファイルへ変換するツール群。経緯・判断根拠は
`content/discussions/ui_image_assets_20260821/whiteboard.md` の `entries/r03_*_ux_visual_claim.md`
（プロンプト全文）と `entries/r04_*_lead_consensus.md`（争点 C の最終確定）を参照。

## 構成

| ファイル | 役割 |
|---|---|
| `prompts/logo.txt` | ヘッダー 24px ロゴ / favicon 原型の完成プロンプト |
| `prompts/hero-idle.txt` | 未検索（待ち受け）状態の完成プロンプト |
| `prompts/empty-result.txt` | 検索結果 0 件の完成プロンプト |
| `prompts/not-found.txt` | 404 ページの完成プロンプト |
| `prompts/og-background.txt` | OG 画像背景（1536×864）の完成プロンプト |
| `to_web_assets.mjs` | 原寸 PNG → 配信用 WebP/PNG への変換スクリプト（`sharp` 使用） |

各 `prompts/*.txt` は共通スタイル段落（線幅・パレット・「文字なし」等の指定）+ アセット固有の
モチーフ段落を連結した完成形で、**そのまま** `--prompt-file` に渡せる。

## 再生成手順

`OPENAI_API_KEY` が環境変数に設定されている前提。原寸 PNG は一時ディレクトリへ出力し、
`public/` にはコミットしない。

```bash
# 1. 原寸 PNG を生成（透過が必要な 4 点は --background transparent を付ける）
python3 tools/infographic/generate.py --prompt-file tools/ui-assets/prompts/logo.txt \
  --out /tmp/assets/logo.png --size 1024x1024 --quality medium \
  --background transparent --timeout 900

python3 tools/infographic/generate.py --prompt-file tools/ui-assets/prompts/hero-idle.txt \
  --out /tmp/assets/hero-idle.png --size 1024x1024 --quality medium \
  --background transparent --timeout 900

python3 tools/infographic/generate.py --prompt-file tools/ui-assets/prompts/empty-result.txt \
  --out /tmp/assets/empty-result.png --size 1024x1024 --quality medium \
  --background transparent --timeout 900

python3 tools/infographic/generate.py --prompt-file tools/ui-assets/prompts/not-found.txt \
  --out /tmp/assets/not-found.png --size 1024x1024 --quality medium \
  --background transparent --timeout 900

# og-background は不透過（背景色そのものが絵の一部）なので --background は付けない
python3 tools/infographic/generate.py --prompt-file tools/ui-assets/prompts/og-background.txt \
  --out /tmp/assets/og-background.png --size 1536x864 --quality medium --timeout 900

# 2. 生成物を必ず Read（目視）して検証する
#    - 文字・記号・ロゴが写り込んでいないか（プロンプトは文字なしを要求している）
#    - 透過であるべき 4 点が実際に透過か（sharp の metadata().hasAlpha で機械確認も可）
#    - empty-result に青い原石が写っていないか（グレーのみが正しい）
#    - og-background の左 55〜60% が無地の余白のままか（ここにタイトル文字を合成する）
#    NG があればプロンプトを微調整して 1 回だけ再生成する（無限に回さない）

# 3. 配信用ファイルへ変換
node tools/ui-assets/to_web_assets.mjs --in /tmp/assets/logo.png \
  --out public/images/logo.webp --width 96 --format webp
node tools/ui-assets/to_web_assets.mjs --in /tmp/assets/logo.png \
  --out app/icon.png --width 256 --format png --colors 64
node tools/ui-assets/to_web_assets.mjs --in /tmp/assets/hero-idle.png \
  --out public/images/hero-idle.webp --width 640 --format webp --quality 75
node tools/ui-assets/to_web_assets.mjs --in /tmp/assets/empty-result.png \
  --out public/images/empty-result.webp --width 256 --format webp
node tools/ui-assets/to_web_assets.mjs --in /tmp/assets/not-found.png \
  --out public/images/not-found.webp --width 320 --format webp
node tools/ui-assets/to_web_assets.mjs --in /tmp/assets/og-background.png \
  --out public/images/og-background.png --width 1200 --height 630 --format png \
  --fit cover --colors 32 --dither 0
```

`--format png` で `--colors` を付けるとパレット（インデックスカラー）PNG になる。`gpt-image-2` は
プロンプトの「no texture, no grain」指定にもかかわらず微細なノイズを焼き込むことがあり、素の
可逆圧縮ではフラットな塗りでも色数が減らず容量が膨らむ（`og-background` は無指定だと 500KB 超・
`app/icon.png` も無指定だと 36KB 超で個別予算 30KB を超える）。`--colors 32 --dither 0` 程度で
`og-background.png` は約 140KB、`--colors 64`（既定の `dither` のまま）で `app/icon.png` は
約 3.7KB まで縮む。

## アセット表

| アセット | 生成サイズ・透過 | quality | 配信ファイル | 変換後の幅 |
|---|---|---|---|---|
| logo | 1024×1024・透過 | medium | `public/images/logo.webp` | 96px |
| logo（同じ原寸から） | — | — | `app/icon.png`（PNG・透過） | 256px |
| hero-idle | 1024×1024・透過 | medium | `public/images/hero-idle.webp` | 640px |
| empty-result | 1024×1024・透過 | medium | `public/images/empty-result.webp` | 256px |
| not-found | 1024×1024・透過 | medium | `public/images/not-found.webp` | 320px |
| og-background | 1536×864・不透過 | medium | `public/images/og-background.png` | 1200×630（cover） |

## 位置づけ（重要）

- **中間生成物（原寸 1024² などの PNG）はコミットしない。** 正本は配信ファイル（`public/images/*`・
  `app/icon.png`、いずれも git 管理下）である。
- **画像生成は非決定的**。同じプロンプトを再実行しても同じ画素は返らない。したがって
  「再生成」は「同じ結果の復元」ではなく、**デザインを変えたいときの起点** として扱う。壊れた
  配信ファイルを直すために再生成しても、以前と寸分違わぬ絵には戻らないことを前提に運用する。
- 争点 C（`entries/r04_*_lead_consensus.md`）で「手書き SVG 再作図」は明示的に却下されている。
  配信するのは **`gpt-image-2` の生成物そのもの**（`sharp` によるリサイズ・形式変換のみ）であり、
  エージェントが絵を描き直すことはしない。
