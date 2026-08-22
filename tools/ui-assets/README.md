# UI 画像アセット

gem-hunter の装飾イラスト 6 点（logo / hero-idle / loading / empty-result / not-found / og-background）と、
エラー種別ごとのイラスト 4 点（error-network / error-rate-limit / error-upstream / error-validation・
Issue #364）を `gpt-image-2` で生成し、配信用ファイルへ変換するツール群。経緯・判断根拠は
`content/discussions/ui_image_assets_20260821/whiteboard.md` の `entries/r03_*_ux_visual_claim.md`
（プロンプト全文）と `entries/r04_*_lead_consensus.md`（争点 C の最終確定）を参照。

## 構成

| ファイル | 役割 |
|---|---|
| `prompts/logo.txt` | ヘッダー 24px ロゴ / favicon 原型の完成プロンプト |
| `prompts/hero-idle.txt` | 未検索（待ち受け）状態の完成プロンプト |
| `prompts/loading.txt` | 読み込み中状態の完成プロンプト |
| `prompts/empty-result.txt` | 検索結果 0 件の完成プロンプト |
| `prompts/not-found.txt` | 404 ページの完成プロンプト |
| `prompts/og-background.txt` | OG 画像背景（1536×864）の完成プロンプト |
| `prompts/error-network.txt` | エラー種別: ネットワーク不通の完成プロンプト |
| `prompts/error-rate-limit.txt` | エラー種別: レート制限（待てば回復）の完成プロンプト |
| `prompts/error-upstream.txt` | エラー種別: 上流（GitHub 等）障害の完成プロンプト |
| `prompts/error-validation.txt` | エラー種別: 入力バリデーション不通過の完成プロンプト |
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
  --out /tmp/assets/hero-idle.png --size 1536x864 --quality medium \
  --background transparent --timeout 900

python3 tools/infographic/generate.py --prompt-file tools/ui-assets/prompts/loading.txt \
  --out /tmp/assets/loading.png --size 1024x1024 --quality medium \
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
#    - loading が虫眼鏡モチーフになっていないか、hero-idle / empty-result と見分けがつくか
#    - og-background の左 55〜60% が無地の余白のままか（ここにタイトル文字を合成する）
#    NG があればプロンプトを微調整して 1 回だけ再生成する（無限に回さない）

# 3. 配信用ファイルへ変換
node tools/ui-assets/to_web_assets.mjs --in /tmp/assets/logo.png \
  --out public/images/logo.webp --width 96 --format webp
node tools/ui-assets/to_web_assets.mjs --in /tmp/assets/logo.png \
  --out app/icon.png --width 256 --format png --colors 64
# hero-idle は 16:9 の広い画面で gpt-image-2 の微細ノイズが乗りやすく、素の webp 変換だと
# 768px 幅で 60KB 超になり個別予算 30KB を超える。og-background と同じ「先に減色 PNG へ、
# それを webp へ」の二段変換で 30KB 以内に収める。
node tools/ui-assets/to_web_assets.mjs --in /tmp/assets/hero-idle.png \
  --out /tmp/assets/hero-idle-q16.png --width 768 --format png --colors 16 --dither 0
node tools/ui-assets/to_web_assets.mjs --in /tmp/assets/hero-idle-q16.png \
  --out public/images/hero-idle.webp --width 768 --format webp --quality 80
node tools/ui-assets/to_web_assets.mjs --in /tmp/assets/loading.png \
  --out public/images/loading.webp --width 256 --format webp
node tools/ui-assets/to_web_assets.mjs --in /tmp/assets/empty-result.png \
  --out public/images/empty-result.webp --width 256 --format webp
node tools/ui-assets/to_web_assets.mjs --in /tmp/assets/not-found.png \
  --out public/images/not-found.webp --width 320 --format webp
node tools/ui-assets/to_web_assets.mjs --in /tmp/assets/og-background.png \
  --out public/images/og-background.png --width 1200 --height 630 --format png \
  --fit cover --colors 32 --dither 0

# エラー種別イラスト 4 点（透過・1024×1024・素の webp 変換で個別予算 30KB 以内）
for name in error-network error-rate-limit error-upstream error-validation; do
  python3 tools/infographic/generate.py --prompt-file tools/ui-assets/prompts/$name.txt \
    --out /tmp/assets/$name.png --size 1024x1024 --quality medium \
    --background transparent --timeout 900
  node tools/ui-assets/to_web_assets.mjs --in /tmp/assets/$name.png \
    --out public/images/$name.webp --width 256 --format webp
done
```

`--format png` で `--colors` を付けるとパレット（インデックスカラー）PNG になる。`gpt-image-2` は
プロンプトの「no texture, no grain」指定にもかかわらず微細なノイズを焼き込むことがあり、素の
可逆圧縮ではフラットな塗りでも色数が減らず容量が膨らむ（`og-background` は無指定だと 500KB 超・
`app/icon.png` も無指定だと 36KB 超で個別予算 30KB を超える）。`--colors 32 --dither 0` 程度で
`og-background.png` は約 140KB、`--colors 64`（既定の `dither` のまま）で `app/icon.png` は
約 3.7KB まで縮む。同じ理由で `hero-idle`（16:9・768px 幅）も素の webp 変換だと 60KB 超になるため、
`--colors 16 --dither 0` の減色 PNG を経由してから webp 化する（実測 27.6KB）。`--colors 8` まで
落とすと青い原石のアクセントカラーごと潰れてしまう（16 が下限）。

## アセット表

| アセット | 生成サイズ・透過 | quality | 配信ファイル | 変換後の幅 |
|---|---|---|---|---|
| logo | 1024×1024・透過 | medium | `public/images/logo.webp` | 96px |
| logo（同じ原寸から） | — | — | `app/icon.png`（PNG・透過） | 256px |
| hero-idle | 1536×864（16:9）・透過 | medium | `public/images/hero-idle.webp` | 768px |
| loading | 1024×1024・透過 | medium | `public/images/loading.webp` | 256px |
| empty-result | 1024×1024・透過 | medium | `public/images/empty-result.webp` | 256px |
| not-found | 1024×1024・透過 | medium | `public/images/not-found.webp` | 320px |
| og-background | 1536×864・不透過 | medium | `public/images/og-background.png` | 1200×630（cover） |
| error-network | 1024×1024・透過 | medium | `public/images/error-network.webp` | 256px |
| error-rate-limit | 1024×1024・透過 | medium | `public/images/error-rate-limit.webp` | 256px |
| error-upstream | 1024×1024・透過 | medium | `public/images/error-upstream.webp` | 256px |
| error-validation | 1024×1024・透過 | medium | `public/images/error-validation.webp` | 256px |

## OG 画像背景の埋め込み（`app/[locale]/opengraph-image.tsx` 用・追加タスク・Issue #347）

`opengraph-image.tsx` は `next/og` の `ImageResponse` で背景に `og-background.png` を敷くが、
**実行時の `readFile()` で `public/` を読む方式は Cloudflare Workers 上で 500 になる**（Workers に
ファイルシステムは無く、`public/` の中身はディスク上に存在せず `ASSETS` バインディング経由でしか
配信されないため。`npx opennextjs-cloudflare build` の成功はこれを検出できない——実デプロイへの
`curl` で判明した）。そのため背景は **ビルド時に TS モジュール（base64 データ URI）へ変換して
バンドルへ埋め込む**。`getCloudflareContext()` 等の Cloudflare 固有 API は使わない（`NFR-21`）。

```bash
# 1. 配信用 og-background.png（1200×630・約140KB）をさらに縮小・減色する
#    （バンドルに埋め込むため、配信用よりずっと小さい版でよい。flat なベクター調の絵なので
#    OG の 1200×630 へ拡大表示しても実用上問題ない）
node tools/ui-assets/to_web_assets.mjs --in public/images/og-background.png \
  --out /tmp/og-background-embed.png --width 600 --height 315 --format png \
  --fit cover --colors 8 --dither 0
# → 実測 4.5KB（600×315・8 色パレット）。目視で文字・記号の欠落やバンディングが無いことを確認する。

# 2. base64 データ URI を export する TS モジュールへ変換する
node tools/ui-assets/build_data_uri_module.mjs --in /tmp/og-background-embed.png \
  --out "app/[locale]/og-background-data.ts" --export-name OG_BACKGROUND_DATA_URI --mime image/png
# → app/[locale]/og-background-data.ts（自動生成・手で編集しない）を上書きする。
#    opengraph-image.tsx は `import { OG_BACKGROUND_DATA_URI } from './og-background-data'` で使う。
```

`app/[locale]/og-background-data.ts` は自動生成ファイルだが、Cloudflare Workers に手動デプロイの
たびに再生成する必要が無いよう **git 管理下に置く**（`public/images/og-background.png` を
再生成したときだけ上記 2 手順を再実行する）。

## 位置づけ（重要）

- **中間生成物（原寸 1024² などの PNG）はコミットしない。** 正本は配信ファイル（`public/images/*`・
  `app/icon.png`、いずれも git 管理下）である。
- **画像生成は非決定的**。同じプロンプトを再実行しても同じ画素は返らない。したがって
  「再生成」は「同じ結果の復元」ではなく、**デザインを変えたいときの起点** として扱う。壊れた
  配信ファイルを直すために再生成しても、以前と寸分違わぬ絵には戻らないことを前提に運用する。
- 争点 C（`entries/r04_*_lead_consensus.md`）で「手書き SVG 再作図」は明示的に却下されている。
  配信するのは **`gpt-image-2` の生成物そのもの**（`sharp` によるリサイズ・形式変換のみ）であり、
  エージェントが絵を描き直すことはしない。
