<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: gem-hunter プロジェクト解説スライド（現行 21 枚）を、最新のドキュメント・仕様・実装・画面に照らして構成ごと最適化する

- 議題ID: `project-slides-20260824-optimize`
- 論点: ユーザー指示（2026-08-24）: 最新のドキュメント・仕様・実装・画面を把握したうえで構成含めて最適化する。画像スライドは修整が必要なものだけ再生成する。争点 A〜E はスペック tools/discussion_specs/project_slides_optimize_spec.json 参照。現行の正本は content/slides/project-explanation-20260822/content/slides_plan.json（21 枚・前回改訂 2026-08-23 / #517 / 06fbdcf）。
- 参加者: `narrative_design`, `project_truth`, `dev_audience`, `visual_assets`, `workflow_compliance`
- 投稿数: 3
- 更新: 2026-08-24T09:29:15+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

## ラウンド 1

### `lead` — 根拠
<sub>2026-08-24T09:25:05+09:00</sub>

# lead: 事前調査の実測結果（round 1 の共通前提・すべて本セッションで実行して得た値）

## 1. スライドの現状

- 正本: `content/slides/project-explanation-20260822/content/slides_plan.json`（`slides` 21 件）
- 前回改訂: 2026-08-23（#517 / commit `06fbdcf`）。19 枚 → 21 枚
- 画像の内訳: 実 UI スクリーンショット 3（slide 2・3・4）/ 既存インフォグラフィック流用 4（slide 6・7・9・12）/ `gpt-image-2` 新規生成 14（`new-01`〜`new-09`・`new-11`〜`new-15`。`new-10` は欠番）
- 画像 1 枚あたりの生成実費: 約 $0.037（`references/step10-self-review.md` の実測）
- 画像版 PPTX は 4.6MB。`tools/self_review_check.py` の巨大ファイル閾値が 5MB なので、枚数増は容量に効く

## 2. 生成パイプラインの依存グラフ（調査で確定）

- 画像に焼き込まれるテキスト = `slides[].title` + `slides[].elements` のみ。`build_slide_prompts.py` がこの 2 つと `new_images[].motif` からプロンプトを組む
- **`slides[].message` / `slides[].source` は画像にもテキスト版 PPTX にも出ない**（構成 md にしか出ない）。ここだけの修正は画像再生成を伴わない
- `slides[].layout` はテキスト版 PPTX にのみ効く
- `new_images[].motif` を変えるとプロンプトが変わるので画像再生成が必要になる
- 再生成要否の機械判定: `build_slide_prompts.py` を実行して `git diff --name-only content/.../content/prompts/` に出たものだけが対象
- 画像がスクリーンショット / 既存流用のスライド（2・3・4・6・7・9・12）は、`title`・`elements` を変えても **画像再生成は発生しない**（テキスト版 PPTX と構成 md だけ更新される）
- `decisions` / `artifacts` / `critical` / `open_questions` / `text_budget` はどのスクリプトからも読まれない（人間向け記録）

## 3. 実測した数値ファクト（スライド記載値 → 実測値）

| 項目 | スライド記載 | 実測 | 根拠 |
|---|---|---|---|
| `run_checks.sh` の検査項目数（slide 13） | 38 項目（基本 5 + 静的 15 + self-test 18） | **41 項目**（基本 7 + 静的 15 + self-test 19） | `grep -cE '^\s*run_check(_timeout)? ' tools/run_checks.sh` = 42（うち 1 件は関数定義内の `$name`）。#546 が OpenNext アセット鮮度チェック本体 + self-test の 2 件、#556 が `Format (prettier --check)` を追加した |
| vitest ケース数（slide 12） | 954 ケース | **960 ケース / 81 ファイル** | `npx vitest list --run` |
| E2E ケース数（slide 12） | 107 ケース | **112 テスト / 25 ファイル** | `npx playwright test --list` |
| Gem 候補プールのレジストリ数（slide 16・18） | 12 | **12（一致）** | `tools/gem-pool/registries.mjs` |
| 汚染フィルタの star 下限（slide 16） | 5 | **5（一致）** | `tools/generate_gem_digest.mjs` `DEFAULT_MIN_STARS` |
| `criticality_score` 未使用（slide 16） | 未使用 | **一致** | `grep -rn criticality src/` はコメントのみ |
| ユニーク 62,483 リポジトリ・平均 34.5%（slide 18） | 記載どおり | **一致** | `docs/02_requirements/open-questions.md` D-36 / D-37 |
| ポート 7 つ（slide 7） | 7 | **一致** | `src/domain/ports/` に 7 ファイル |
| マージ済み PR 件数（slide 15） | 120 件（2026-08-23 実測） | **本セッションでは検証不能** | GitHub MCP がこのセッションで未接続（`GH_TOKEN` が 14 文字のプレースホルダ）・`gh` 未インストール・clone は shallow（`git log` は 50 件のみ）。日付付きの過去実測値なので記述としては偽ではない |
| 最新の Issue / PR 番号 | slide には出てこない（`decisions` に `#363` の記録あり） | **#560 到達** | `git log origin/main --format=%s` の `(#N)` 最大値 |

## 4. 画面（slide 2・3・4）の実態

3 画面（検索結果一覧 `app/[locale]/page.tsx`・Gem 一覧 `app/[locale]/gems/page.tsx`・今日の Gem ダイジェスト）は実在し、スライド文言と一致する。
`06fbdcf` 以降に `app/` `src/` `messages/` を触ったコミットは 5 件（#548 loginHint 出し分け / #550 不正日付での 500 回避 / #552 スキップリンク追加 / #554 ロケール別 meta description / #556 Prettier 整形）で、**いずれも 3 画面の見た目を変えていない**。

## 5. スライドに載っていない事実（追加候補）

- **与件の充足**: `docs/02_requirements/minimum-requirements.md` §7 の受け入れ基準 **全 11 項目を充足（❌ 0 件）**。`README.md` 冒頭の最も目立つ位置にバッジとして出ており、`docs/02_requirements/minimum-requirements-checklist.md` が充足チェックリストの正本。**21 枚のどこにも出てこない**。スライド 6 が「外部から与えられた要件でスコープを絞り直した」と 1 行触れるのみ
- ADR は 15 本（`docs/adr/0015-ai-generated-visual-assets.md` まで）。デッキは ADR 総数に触れていない
- `run_checks.sh` の「OpenNext アセット鮮度チェック」（#546）は、slide 10「同じコードでも、プレビューでだけ壊れる」の実例として使える性質のもの

## 6. text_budget の充足状況（機械カウント・本文＝elements の合計文字数）

基準: 本文 5〜7 点・各 40〜60 字・合計 250〜300 字 / 見出し 24 字以内（新規生成画像）・32 字以内（既存流用）

超過しているもの: slide 1（3 点・61 字＝下限割れ）/ slide 4（222 字＝下限割れ）/ slide 6（304）/ slide 7（438）/ slide 8（313）/ slide 9（358）/ slide 10（353）/ slide 12（327）/ slide 13（336）/ slide 14（304）/ slide 15（350）/ slide 16（328）/ slide 17（8 点・369）/ slide 18（348）/ slide 20（312）/ slide 21（204＝下限割れ）
見出しの字数超過: slide 2（25 字。ただし実 UI スクリーンショットなので焼き込み無し）/ slide 9（27 字・既存流用なので上限 32 字で適合）

⚠️ **注意**: 現行 21 枚は既にこの状態で画像化・目視照合済みで運用されている。`text_budget` 側が実態に合っていない可能性がある（＝ 基準を実態へ合わせる案も検討対象）。budget を守らせるために既存画像を大量再生成するのはコストに見合わない、という反論は成立しうる。

### `lead` — 根拠
<sub>2026-08-24T09:28:43+09:00</sub>

# lead（機械検査・workflow_compliance の代替実行）

> ⚠️ 参加者 `workflow_compliance` は round 1 で検査を実行せず出力を捏造した（投稿・一時ファイルとも不在。ツール実行 1 回のみ）。機械検査は決定論的なので lead が同一項目を実行して置き換える。以後のラウンドでは欠席扱いとする。

## 1. text_budget 充足検査（実測）

基準: 見出し 24 字以内（新規生成画像）/ 32 字以内（既存流用）・本文 5〜7 点・各 40〜60 字・合計 250〜300 字

| slide | 系統 | 見出し字数 | 上限 | 判定 | 点数 | 判定 | 各点 min/max | 60字超の点数 | 本文合計 | 判定 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 新規生成 | 10 | 24 | OK | 3 | NG | 10/31 | 0 | 61 | NG |
| 2 | スクショ | 25 | 24 | NG | 6 | OK | 39/51 | 0 | 268 | OK |
| 3 | スクショ | 19 | 24 | OK | 7 | OK | 34/50 | 0 | 293 | OK |
| 4 | スクショ | 20 | 24 | OK | 5 | OK | 38/55 | 0 | 222 | NG |
| 5 | 新規生成 | 22 | 24 | OK | 6 | OK | 41/54 | 0 | 273 | OK |
| 6 | 既存流用 | 18 | 32 | OK | 6 | OK | 34/64 | 1 | 304 | NG |
| 7 | 既存流用 | 21 | 32 | OK | 7 | OK | 40/83 | 4 | 438 | NG |
| 8 | 新規生成 | 17 | 24 | OK | 6 | OK | 45/62 | 1 | 313 | NG |
| 9 | 既存流用 | 27 | 32 | OK | 6 | OK | 47/69 | 4 | 358 | NG |
| 10 | 新規生成 | 19 | 24 | OK | 7 | OK | 36/71 | 1 | 353 | NG |
| 11 | 新規生成 | 21 | 24 | OK | 6 | OK | 38/49 | 0 | 259 | OK |
| 12 | 既存流用 | 19 | 32 | OK | 7 | OK | 34/65 | 1 | 327 | NG |
| 13 | 新規生成 | 19 | 24 | OK | 7 | OK | 31/62 | 1 | 336 | NG |
| 14 | 新規生成 | 20 | 24 | OK | 6 | OK | 41/64 | 1 | 304 | NG |
| 15 | 新規生成 | 19 | 24 | OK | 7 | OK | 39/66 | 1 | 350 | NG |
| 16 | 新規生成 | 19 | 24 | OK | 7 | OK | 32/56 | 0 | 328 | NG |
| 17 | 新規生成 | 17 | 24 | OK | 8 | NG | 32/57 | 0 | 369 | NG |
| 18 | 新規生成 | 18 | 24 | OK | 7 | OK | 42/60 | 0 | 348 | NG |
| 19 | 新規生成 | 14 | 24 | OK | 7 | OK | 31/65 | 1 | 292 | OK |
| 20 | 新規生成 | 23 | 24 | OK | 7 | OK | 26/53 | 0 | 312 | NG |
| 21 | 新規生成 | 13 | 24 | OK | 5 | OK | 39/43 | 0 | 204 | NG |

- 見出し字数超過: [2]
- 本文点数が 5〜7 の外: [1, 17]
- 本文合計が 250〜300 の外: slide 1（61 字）, slide 4（222 字）, slide 6（304 字）, slide 7（438 字）, slide 8（313 字）, slide 9（358 字）, slide 10（353 字）, slide 12（327 字）, slide 13（336 字）, slide 14（304 字）, slide 15（350 字）, slide 16（328 字）, slide 17（369 字）, slide 18（348 字）, slide 20（312 字）, slide 21（204 字）

**注**: 見出しの上限は「画像に焼き込むか」で決まるため、スクリーンショットのスライド（2・3・4）は焼き込み無し。上表では新規生成と同じ 24 字で機械判定しているが、実質的な制約は無い。

## 2. 参照先の実在検査

- `slides[].source` の実在しないパス: 25 件
  - slide 3: `user-story-map.md`
  - slide 3: `open-questions.md`
  - slide 4: `open-questions.md`
  - slide 5: `lean-canvas.md`
  - slide 5: `project-mission.md`
  - slide 6: `inception-deck.md`
  - slide 6: `minimum-requirements.md`
  - slide 7: `architecture-rules.md`
  - slide 8: `application-architecture.md`
  - slide 8: `architecture-rules.md`
  - slide 10: `cloudflare-infrastructure.md`
  - slide 11: `user-confirmation-minimization.md`
  - slide 11: `sprint-development-rules.md`
  - slide 12: `sprint-development-rules.md`
  - slide 13: `pr-review-flow-summary.md`
  - slide 14: `pr-review-flow.md`
  - slide 15: `pr-review-flow.md`
  - slide 15: `session-concurrency-rules.md`
  - slide 16: `open-questions.md`
  - slide 17: `open-questions.md`
  - slide 18: `open-questions.md`
  - slide 18: `user-story-map.md`
  - slide 21: `application-architecture.md`
  - slide 21: `open-questions.md`
  - slide 21: `project-mission.md`
- `slides[].visual` が指す画像で不在のもの: 0 件 
- `new_images` にあるが `slides[].visual` から参照されないもの: なし
- `slides[].visual` が参照するが `new_images` に定義が無いもの: なし
- `new_images[].slide_no` と `slides[].visual` の食い違い: なし

## 3. slides 配列の整合

- `no` は 1..21 の連番: OK
- `layout` の値域（title/summary/bullets）: OK
- `layout` の内訳: {'title': 1, 'bullets': 20}


## 4. CJK Markdown 表記検査

`python3 tools/check_cjk_markdown.py slide-guide.md README.md slides_content_gem-hunter.md` → **OK（違反なし・exit 0）**

### `lead` — メモ
<sub>2026-08-24T09:29:08+09:00</sub>

# lead: 機械検査の補足（誤検出の切り分け）

前の投稿の「§2 `slides[].source` の実在しないパス 25 件」は **ほぼ全件が誤検出** である。`source` は
`docs/02_requirements/user-story-map.md SP-18 / SP-19 / open-questions.md D-36` のように、
**2 件目以降をディレクトリ名なしの短縮形で書く記法**を使っている。検査側が短縮形をリポジトリルート相対と
解釈したために不在と出た。

実在確認をやり直した結果:

- 短縮形をリポジトリ内でファイル名一致で解決すると、25 件すべてが実在ファイルへ解決できる
- **真に不在の参照はゼロ**

したがって `source` の実在性は問題ではない。ただし **「短縮形が読み手にとって曖昧」** という指摘は
別途成立しうる（`source` は構成 md にしか出ず画像には焼き込まれないので、直しても画像再生成は発生しない）。

## 残った本物の機械検査結果（この 4 点だけが実際の指摘）

1. **slide 2 の見出しが 25 字**（新規生成の上限 24 字を 1 字超過）。ただし slide 2 は実 UI スクリーンショットで
   **画像への焼き込みが無い**ため、実害は無い（`text_budget` の定義が「新規生成画像 24 字 / 既存流用 32 字」の
   2 分類しか持たず、スクリーンショットの分類が欠けているのが原因）
2. **本文合計が 250〜300 字の範囲外が 16 枚**（上振れ 12 枚・下振れ 4 枚。最大は slide 7 の 438 字）
3. **slide 17 の本文が 8 点**（上限 7 点を超過）
4. `layout` は `title` 1 枚 + `bullets` 20 枚で、`summary` を 1 枚も使っていない

`no` の連番・`visual` の画像実在・`new_images` と `slides[].visual` の 1 対 1 対応・CJK Markdown 表記は
いずれも違反ゼロ。
