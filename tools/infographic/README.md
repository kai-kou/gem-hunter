# インフォグラフィック生成ツール

`docs/infographics/` に置いている **16:9 グラレコ風インフォグラフィック** の生成一式。
OpenAI の `gpt-image-2` を使い、ドキュメントから抽出した構造化テキストを画像として描画する。

## 構成

| パス | 役割 |
|---|---|
| `specs/*.json` | 各ドキュメントから抽出した **画像に描くテキストの正本**（`title` / `subtitle` / `sections` / `key_numbers`） |
| `layouts/*.txt` | 図としてどう並べるかの指示（英語。画像モデルへそのまま渡る） |
| `build_prompt.py` | spec + layout → 生成プロンプトを組み立てる |
| `prompts/*.txt` | 組み立て済みプロンプト（実際に投げた内容の記録） |
| `generate.py` | プロンプトを `gpt-image-2` に投げて PNG を保存する CLI |

## 使い方

`OPENAI_API_KEY` を環境変数に設定した状態で実行する。

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
  --size 1536x864 --quality medium

# 3. WebP に変換して docs/infographics/ へ置く
node -e "require('sharp')('/tmp/02-lean-canvas.png').webp({quality:90}).toFile('docs/infographics/02-lean-canvas.webp')"
```

`generate.py` は生成のたびに実測トークン数と概算コストを JSON で出力する。

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
