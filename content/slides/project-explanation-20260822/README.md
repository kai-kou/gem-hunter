# gem-hunter プロジェクト解説スライド（2026-08-22）

開発者・エンジニア向けに gem-hunter を 15〜20 分で解説するスライド一式（17 枚）。

作成手順は参照リポジトリ [kai-kou/qiita-bash-lt-2026](https://github.com/kai-kou/qiita-bash-lt-2026) の
`slides` スキル（15 ステップワークフロー・取得日 2026-08-22）に沿う。環境差分の読み替えは下記「参照ワークフローとの差分」を参照。

## 成果物

| パス | 内容 |
|---|---|
| `output/gem-hunter_text.pptx` | テキスト版（レイアウト済み・そのまま使える完成品） |
| `output/gem-hunter.pptx` | 画像版（全 17 枚が 16:9 の画像 1 枚で構成される） |
| `content/slides_plan.json` | **構成の正本**。議論 `project-slides-20260822` の verdict と同一内容 |
| `content/slides_content_gem-hunter.md` | 構成マークダウン（`slides_plan.json` から生成） |
| `content/prompts/*.txt` | 新規画像 10 枚に投げた `gpt-image-2` プロンプト（実際に投げた内容の記録） |
| `images/` | 画像版に貼った画像（実 UI スクリーンショット 2 枚 + 新規生成 10 枚） |
| `scripts/` | 生成スクリプト一式 |

## 画像の内訳（17 枚）

| 系統 | 枚数 | 実体 |
|---|---|---|
| 実 UI スクリーンショット | 2 | `images/shot-01-search-results.png` / `images/shot-02-daily-digest.png` |
| 既存インフォグラフィックの流用 | 5 | `docs/infographics/` の 07 / 08 / 10 / 11 / 12 |
| `gpt-image-2` で新規生成 | 10 | `images/new-01.jpg` 〜 `new-10.jpg` |

新規生成は **1536×864（完全な 16:9）・quality=medium**。既存 13 枚と同じ設定で、配色・筆致を揃えるため。
プロンプトのスタイル文は `tools/infographic/build_prompt.py` の `STYLE` を import して共有している（複製しない）。

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

- スライド 2 のスクリーンショットに写るリポジトリは `e2e/stub/server.mjs` のスタブデータ（外部ネットワーク非依存で決定論的に撮るため）。スライド 3 のダイジェストは実データ（Ecosyste.ms 由来）。
- **検索結果に Gem Index は効かない**（`D-33` で撤去済み）。Gem Index を使うのはトップページの「今日の Gem」だけ。スライド 2 と 3 を分けているのはこの誤読を防ぐため。
