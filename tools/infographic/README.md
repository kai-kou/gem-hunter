# インフォグラフィック生成ツール

`docs/infographics/` に置いている **16:9 グラレコ風インフォグラフィック** の生成一式。
OpenAI の `gpt-image-2` を使い、ドキュメントから抽出した構造化テキストを画像として描画する。

## 構成

| パス | 役割 |
|---|---|
| `specs/*.json` | 各ドキュメントから抽出した **画像に描くテキストの正本**（`title` / `subtitle` / `sections` / `key_numbers`） |
| `layouts/*.txt` | 図としてどう並べるかの指示（英語。画像モデルへそのまま渡る） |
| `build_prompt.py` | spec + layout → 生成プロンプトを組み立てる（「見出し + 箇条書き」型の 13 枚） |
| `build_grid_prompt.py` | `specs/usm_grid.json` → 格子型プロンプトを組み立てる（ユーザーストーリーマップ専用） |
| `prompts/*.txt` | 組み立て済みプロンプト（実際に投げた内容の記録） |
| `generate.py` | プロンプトを `gpt-image-2` に投げて PNG を保存する CLI |
| `to_webp.mjs` | 生成した PNG をまとめて WebP へ変換し `docs/infographics/` へ置く |

## 使い方

`OPENAI_API_KEY` を環境変数に設定した状態で実行する。

> クラウド実行環境では GitHub Variables の自動ロードが 403 でブロックされているため、`OPENAI_API_KEY` は
> **Claude.ai の環境変数設定** で供給する（SSOT: [`docs/rules/env-vars.md`](../../docs/rules/env-vars.md) 冒頭）。
> もう 1 つの経路である secrets-broker は opt-in で、**本リポジトリには未導入**（`infra/` が存在しない）。
> 未設定のまま実行すると `generate.py` は理由を stderr に出して終了コード 1 を返す。

```bash
# 1. プロンプトを組み立てる
python3 tools/infographic/build_prompt.py \
  tools/infographic/specs/concept.json lean-canvas \
  tools/infographic/layouts/lean-canvas.txt \
  tools/infographic/prompts/02-lean-canvas.txt

# 2. 画像を生成する（1536x864 = 完全な 16:9）
python3 tools/infographic/generate.py \
  --prompt-file tools/infographic/prompts/02-lean-canvas.txt \
  --out /tmp/02-lean-canvas.png \
  --size 1536x864 --quality medium --timeout 900

# 3. WebP に変換して docs/infographics/ へ置く（ディレクトリ内の .png をまとめて処理する）
node tools/infographic/to_webp.mjs /tmp/infographics
```

`generate.py` は生成のたびに実測トークン数と概算コストを JSON で出力する。
出力ファイル名がそのまま WebP のファイル名になるので、`--out` は `docs/infographics/` の命名（`01-initial-concept.png` 等）に合わせておく。

ユーザーストーリーマップだけは格子構造のため専用ビルダーを使う。

```bash
python3 tools/infographic/build_grid_prompt.py --out tools/infographic/prompts/05-user-story-map.txt
```

> `to_webp.mjs` が使う `sharp` は **`package.json` の直接依存ではなく `miniflare` の推移的依存** として
> `node_modules/` に入っている。依存更新で解決できなくなったら、`sharp` を `devDependencies` に明示追加する。

## 14 枚の対応表

`build_prompt.py` の引数（spec ファイル / キー / レイアウト）は画像ごとに違うので、ここを正本にする。

| 出力プロンプト | spec ファイル | キー | レイアウト |
|---|---|---|---|
| `01-initial-concept.txt` | `specs/concept.json` | `initial-concept` | `layouts/initial-concept.txt` |
| `02-lean-canvas.txt` | `specs/concept.json` | `lean-canvas` | `layouts/lean-canvas.txt` |
| `03-inception-deck.txt` | `specs/concept.json` | `inception-deck` | `layouts/inception-deck.txt` |
| `04-prd.txt` | `specs/requirements.json` | `prd` | `layouts/prd.txt` |
| `05-user-story-map.txt` | `specs/usm_grid.json` | （格子・`build_grid_prompt.py` を使う） | `layouts/user-story-map.txt` |
| `06-roadmap.txt` | `specs/requirements.json` | `roadmap` | `layouts/roadmap.txt` |
| `07-design.txt` | `specs/design.json` | `design` | `layouts/design.txt` |
| `08-doc-relations.txt` | `specs/design.json` | `doc-relations` | `layouts/doc-relations.txt` |
| `09-adr-map.txt` | `specs/extra1.json` | `adr-map` | `layouts/adr-map.txt` |
| `10-gem-score.txt` | `specs/extra1.json` | `gem-score` | `layouts/gem-score.txt` |
| `11-testing-strategy.txt` | `specs/extra2.json` | `testing` | `layouts/testing.txt` |
| `12-cloudflare.txt` | `specs/extra2.json` | `cloudflare` | `layouts/cloudflare.txt` |
| `13-ops-rules.txt` | `specs/extra3.json` | `ops-rules` | `layouts/ops-rules.txt` |
| `14-architecture-overview.txt` | `specs/extra4.json` | `architecture-overview` | `layouts/architecture-overview.txt` |

全 14 枚のプロンプトをまとめて組み立て直すには `build_all_prompts.sh` を使う。

```bash
bash tools/infographic/build_all_prompts.sh
```

## サイズと品質の制約

- **サイズは幅・高さとも 16 の倍数** でなければ API がエラーを返す（`1920x1080` は 1080 が 16 で割り切れず不可）。
  16:9 で使えるのは `1024x576` / `1536x864` / `1792x1008` / `2048x1152` など。
- 品質別の画像出力トークン（1536×864 実測）: `low` 120 / `medium` 1,078 / `high` 4,312。
  画像出力の単価は **$30 / 1M tokens** なので、1 枚あたり概算 **$0.004 / $0.032 / $0.129**。
- 日本語テキストは `medium` で一字一句正確に描画できることを実測で確認済みのため、既定を `medium` にしている。

## テキストを正確に描かせるための決めごと

`build_prompt.py` の `STYLE` に、以下を毎回のプロンプトへ埋め込んでいる。これを外すと描画が崩れる。

- 列挙した文字を **一字一句そのまま** 描く（翻訳・言い換え・装飾文字の追加を禁じる）
- **見出しの集合は spec の見出しと完全一致** させる（モデルが勝手に「まとめ」ボックスを足すのを防ぐ）
- 同じ見出し・同じ項目を **2 箇所に描かない**（フロー図で同じブロックが重複描画されるのを防ぐ）

## 更新のしかた

元ドキュメントを更新したら、対応する `specs/*.json` を直してから再生成する。
spec を直さずにプロンプトだけ手で書き換えると、次回の再生成で戻ってしまう。

`prompts/*.txt` は **現在のビルダーが出力する内容と一致した状態を保つ**（記録と再現手順がずれないようにするため）。
ただし画像生成そのものは非決定的なので、同じプロンプトでもピクセル単位で同一の画像にはならない。
