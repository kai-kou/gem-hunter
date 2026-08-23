# gem-hunter プロジェクト解説スライド（2026-08-22 作成 / 2026-08-23 改訂）

開発者・エンジニア向けに gem-hunter を 22〜25 分で解説するスライド一式（21 枚）。

> **2026-08-23 の改訂（#517）**: `SP-17`〜`SP-19`（12 レジストリの候補プール・Gem バッジ・Gem 一覧）と
> `#453` / `#467` / `#472` / `#488` / `#500` / `#504` を反映し、**19 枚 → 21 枚** にした。
> 追加したのは前半の「検索語をそのまま、Gem だけの一覧へ」（実 UI）と、
> 後半の撤去スライド直後の「母集団を広げたら、撤去の根拠が消えた」の 2 枚。

作成手順は参照リポジトリ [kai-kou/qiita-bash-lt-2026](https://github.com/kai-kou/qiita-bash-lt-2026) の
`slides` スキル（15 ステップワークフロー・取得日 2026-08-22）に沿う。環境差分の読み替えは下記「参照ワークフローとの差分」を参照。

## 成果物

| パス | 内容 |
|---|---|
| `output/gem-hunter_text.pptx` | テキスト版（レイアウト済み・そのまま使える完成品） |
| `output/gem-hunter.pptx` | 画像版（全 21 枚が 16:9 の画像 1 枚で構成される） |
| `content/slides_plan.json` | **構成の正本**。議論 `project-slides-20260822` の verdict と同一内容 |
| `content/slides_content_gem-hunter.md` | 構成マークダウン（`slides_plan.json` から生成） |
| `content/prompts/*.txt` | 新規画像に投げた `gpt-image-2` プロンプト（実際に投げた内容の記録） |
| `images/` | 画像版に貼った画像（実 UI スクリーンショット 3 枚 + 新規生成 14 枚） |
| `scripts/` | 生成スクリプト一式 |

## 画像の内訳（21 枚）

| 系統 | 枚数 | 実体 |
|---|---|---|
| 実 UI スクリーンショット | 3 | `images/shot-01-search-results.png` / `shot-03-gem-list.png` / `shot-02-daily-digest.png` |
| 既存インフォグラフィックの流用 | 4 | `docs/infographics/` の 07 / 08 / 11 / 12 |
| `gpt-image-2` で新規生成 | 14 | `images/new-01.jpg` 〜 `new-09.jpg` / `new-11.jpg` 〜 `new-15.jpg` |

新規生成は **1536×864（完全な 16:9）・quality=medium**。既存インフォグラフィックと同じ設定で、配色・筆致を揃えるため。
プロンプトのスタイル文は `tools/infographic/build_prompt.py` の `STYLE` を import して共有している（複製しない）。

🔴 **`10-gem-score.webp` の流用は 2026-08-23 にやめた**（`new-15` へ差し替え）。この図は
「健全性フィルタで足切り済み」「健全性 = OpenSSF `criticality_score`」と描いているが、実装では
`criticality_score` は使われておらず、効いている足切りは **star 下限 5 の汚染フィルタ**
（`tools/generate_gem_digest.mjs` の `DEFAULT_MIN_STARS`）である。本文に正直に書くと同じスライドの中で
画と話が矛盾するため差し替えた。図そのものの更新は Issue #521 へ回した。

**再生成の対象は「画像に焼き込むテキストが変わったものだけ」に絞る。** 文言が同じ画像を作り直すと、
同じ内容でも絵が変わって既存分との統一が崩れるうえ、コストが無駄になる（判定方法は
[`references/step10-self-review.md`](./references/step10-self-review.md) の 2026-08-23 の記録）。

## 作り直す

```bash
# 1. 構成（正本は content/slides_plan.json）から構成マークダウンを再生成する
python3 content/slides/project-explanation-20260822/scripts/build_outline.py

# 2. 実 UI スクリーンショットを撮り直す（スタブ API + 本番ビルドを自動起動する）
npx playwright test --config content/slides/project-explanation-20260822/scripts/screenshots.config.ts

# 3. 画像プロンプトを組み立てて gpt-image-2 で生成する（OPENAI_API_KEY が必要）
python3 content/slides/project-explanation-20260822/scripts/build_slide_prompts.py
python3 tools/infographic/generate.py \
  --prompt-file content/slides/project-explanation-20260822/content/prompts/new-06.txt \
  --out /tmp/claude/slide-images/new-06.png --size 1536x864 --quality medium --timeout 900

# 4. PPTX を組み立てる
python3 content/slides/project-explanation-20260822/scripts/generate_text_pptx.py
python3 content/slides/project-explanation-20260822/scripts/build_image_deck.py
```

## 参照ワークフローとの差分（環境差分の読み替え）

| 参照スキルのステップ | 本リポジトリでの扱い | 理由 |
|---|---|---|
| Step 5 / 11 / 15（Google ドライブへアップロード） | **リポジトリ内配置 + PR で受け渡し** | `gws`（Google Workspace CLI）がクラウド実行環境に無い。ユーザー確認済み |
| Step 2（構成セルフレビュー） | 議論型レビュー `project-slides-20260822`（5 レンズ × 2 ラウンド）で実施済み | MECE・ファクトチェック・最新情報リサーチをこの議論が兼ねる |
| Step 6 / 12（ユーザーレビュー） | チャットで直接依頼する | PR コメントを経由するより速く確実。明示承認まで次へ進まない原則は維持 |
| 画像フォーマット | 生成 PNG は `/tmp` に置き、リポジトリには JPEG（quality 88）を置く | PNG は 1 枚約 2MB。`docs/infographics/README.md` の方針に合わせる。`python-pptx` は WebP を埋め込めない |

## 注意

- スライド 2 のスクリーンショットに写るリポジトリは `e2e/stub/server.mjs` のスタブデータ（外部ネットワーク非依存で決定論的に撮るため）。スライド 3 の Gem 一覧とスライド 4 のダイジェストは実データ（Ecosyste.ms 由来）。
- スライド 2 は検索語 `gem-badge` で撮っている。スタブのフィクスチャは全て架空の `octostub/*` で候補プールに載らないため、`GEM_BADGE_MARKER` 分岐（`q` に `gem-badge` を含むときだけプール先頭の実在リポジトリを 1 件混ぜる）でしか「一部のカードにだけ印が付く」画にならない。**撮影のためにスタブを書き換えない**（見た目を整えるなら Issue #522）。
- **`sort=gem-index` は検索結果から撤去したままである**（`D-33`）。ただし `SP-18` / `SP-19` で **Gem バッジと Gem 一覧** という別の形で検索経路へ戻っている（`D-36`）。**検索結果の並び順を Gem Index が変えることはない** — この一点が誤読されやすいので、スライド 3・4 の両方で明示している。
