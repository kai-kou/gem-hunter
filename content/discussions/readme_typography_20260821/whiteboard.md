<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: 詳細画面の README を書式どおりに表示する方式を確定する（Tailwind v4 / Workers 制約下）

- 議題ID: `readme_typography_20260821`
- 論点: 飼い主フィードバック（2026-08-21・Issue #339）: 「README について参照できるようになったが **書式が反映されていない**」。実機スクリーンショットでは、README の見出し・リスト・インラインコード・コードブロックがすべて同じ大きさの素のテキストとして縦に並んでおり、階層も余白も付いていない（唯一 `code` 相当が等幅で出ている）。現状: PR #337 で `GET /repos/{o}/{r}/readme` を `Accept: application/vnd.github.html+json` で取得し、`src/ui/readme-html.ts` が sanitize-html で 1 パス変換（許可リスト・相対 URL 解決・target=_blank 付与・見出し +2 降格（h1→h3・h6 cap・id 保持）・30,000 文字での切り詰め）してから `src/ui/readme-section.tsx` が `dangerouslySetInnerHTML` で描画している。描画側のクラスは `className="mt-2 max-w-none space-y-3 text-sm leading-relaxed break-words"` だけで、実装時のコメントは「`@tailwindcss/typography` は未導入（新規依存の追加禁止・タスクスコープ外）のため `prose` は使わない。見出し・段落・リストは既定のブラウザスタイルに委ねる」と書いている。ところが本プロジェクトは **Tailwind CSS v4**（`app/globals.css` の 1 行目が `@import "tailwindcss";`、他に `tw-animate-css` と `shadcn/tailwind.css` を import）であり、Tailwind の Preflight がブラウザ既定スタイル（見出しのサイズ・リストのマーカーとインデント・引用・表の枠）を打ち消すため『既定のブラウザスタイルに委ねる』が成立していない。これが書式が出ない直接原因である（この仮説自体も検証対象とする）。制約: ① Cloudflare Workers（OpenNext）で動く。バンドル上限 3 MB（gzip・現在 1372 KiB）・`limits.cpu_ms: 50`。CSS はビルド時に静的化されるので実行時 CPU には効かないが、バンドル/アセットサイズと Lighthouse への影響は見る ② `NFR-3` クライアント JS を増やさない（`use client` を足さない） ③ ダークモード（`app/globals.css` のセマンティックトークン）と `docs/03_design/ui-ux/ui-ux-guidelines.md`（§2 デザイントークン・§7 a11y・§8 表示状態）に整合させる ④ サニタイズの許可リスト（`ALLOWED_TAGS`）を超えるタグは描画されないので、スタイルを当てる対象は許可済みタグに限る ⑤ README は第三者が書いた HTML であり、スタイルのために許可タグ・許可属性（特に `class` / `style`）を広げるとサニタイズの前提が変わる ⑥ 見出しは +2 降格済みなので、README 内の最上位見出しは h3 として出てくる（プレーンな `h1` セレクタ前提のスタイルは当たらない）。争点は少なくとも次の 6 つ: A) 方式の選択 — `@tailwindcss/typography`（v4 では CSS 側の `@plugin "@tailwindcss/typography";` で読み込む形になっているはず。**最新の公式ドキュメントで v4 における導入方法・`prose` の使い方・`not-prose`・`prose-invert` / ダークモード対応の現行仕様を必ず一次情報で確認すること**）を入れるか、`app/globals.css` に自前のスコープ付き CSS（例 `.readme-content h3 { ... }`）を書くか、`readme-html.ts` の `transformTags` で各タグに Tailwind ユーティリティクラスを注入するか B) 降格済み見出し（h3 起点）と typography プラグインの既定スケール（h1/h2 前提）の噛み合わせをどう解決するか（`prose-headings:` 系の修飾で足りるか、降格の段数自体を見直すべきか） C) ダークモードの扱い（`prose-invert` を使うか、セマンティックトークンで自前定義するか。本プロジェクトのテーマ実装と整合するか） D) サニタイズとの整合 — `class` 属性を許可しないまま方式 A を成立させられるか（typography は親要素の `prose` クラスと子孫セレクタで効くはずなので許可リスト変更は不要という仮説の検証）。GitHub 由来の HTML が持つ独自クラス（`anchor` / `octicon` / `highlight` / `notranslate` 等）や `<img>` のバッジ、`<details>`/`<summary>`、絵文字画像（`g-emoji`）、シンタックスハイライト用の `<span class="pl-*">` が現状どう落ちているか、書式再現にどこまで必要か E) バンドル・パフォーマンスへの影響（typography プラグイン導入時の CSS 増分の実測方法、Lighthouse への影響、`max-w-none` の扱い、モバイルでの表・コードブロックの横スクロール） F) 回帰をどう機械検査するか（現状 `tools/check_ui_dimensions.py` / `check_contrast.py` / axe / Lighthouse があるが、書式が当たっていないことは検知できなかった。E2E で「見出しの計算後フォントサイズが本文より大きい」等を検証できるか、その検査は過剰か）。
- 参加者: `tailwind_v4`, `readme_fidelity`, `perf_bundle`, `a11y_theme`
- 投稿数: 10
- 更新: 2026-08-21T18:32:01+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

## ラウンド 1

### `tailwind_v4` — 主張
<sub>2026-08-21T18:01:03+09:00</sub>

## 結論

`@tailwindcss/typography` 導入案が最も低コストかつ安全。**Tailwind v4 では `tailwind.config.js` を新設せず、`app/globals.css` に `@plugin "@tailwindcss/typography";` を 1 行追加するだけ** で有効化できる。`prose max-w-none dark:prose-invert` を `readme-section.tsx` の `<div>` に付与し、降格済み見出し（README 内は `h3`〜`h6` に強制シフト済み・`readme-html.ts:27-34`）は `prose-h3:text-lg prose-h3:font-semibold` 等の要素修飾子でスケール調整する。Preflight を切る選択肢は他 UI（shadcn コンポーネント全体）を壊すため不採用が正しい。

## 根拠

### 1. v4 でのプラグイン読み込み方法（一次情報: Context7 `/tailwindlabs/tailwindcss-typography`）

v4 は CSS-first configuration で `tailwind.config.js` を前提としない。プラグインは CSS 内の `@plugin` ディレクティブで読み込む。

```css
@import "tailwindcss";
@plugin "@tailwindcss/typography";
```

カスタムオプションも CSS 内で完結する:
```css
@plugin "@tailwindcss/typography" {
  className: wysiwyg;
}
```

**本プロジェクトへの具体差分**:
- `package.json`（devDependencies に追加。実行はしない・スコープ外）: `"@tailwindcss/typography": "^0.5"` 相当を 1 行追加
- `/home/user/gem-hunter/app/globals.css` の **4 行目**（現状 1〜3 行目は `@import` 3 本、5 行目が `@custom-variant dark`）に `@plugin "@tailwindcss/typography";` を **1 行挿入** するだけ。`@import` ブロックの直後・`@custom-variant` の前が自然な位置。
- `postcss.config.mjs` は **変更不要**（`@tailwindcss/postcss` が既に CSS 内の `@plugin` ディレクティブを解決する。v3 のように `plugins: [require('@tailwindcss/typography')]` を JS 側に書く必要はない）。

→ 合計で **CSS 1 行 + package.json 1 行**。`tailwind.config.js` 新設は不要（v4 では非推奨/存在しない前提）。

### 2. `prose` の適用単位・サイズスケール

- `prose` はクラスを当てた要素の **子孫**（見出し・段落・リスト・コード等）に CSS セレクタベースでスタイルを適用する（コンポーネント登録ではなく通常のユーティリティクラス）。
- 既定で `max-width: 65ch` 相当が付く。**コンテナ幅に合わせるには `max-w-none` を明示的に追加** する必要がある（`readme-section.tsx:128` は既に `max-w-none` を単独クラスとして使っているので、`prose max-w-none` の並びに違和感なく統合できる）。
- サイズスケール: `prose-sm` / `prose-base`（既定） / `prose-lg` / `prose-xl` / `prose-2xl`。本プロジェクトの現行クラスが `text-sm` のため、`prose-sm` を選ぶのが最も既存デザインとの差分が小さい。

### 3. ダークモード

- `@tailwindcss/typography` は `dark:prose-invert` で切り替える仕様（CSS 変数ベースの配色反転）。
- 本プロジェクトは `app/globals.css:5` に `@custom-variant dark (&:is(.dark *));` を定義しており、**`.dark` 祖先クラスの有無で切り替える方式**（`app/[locale]/layout.tsx` は未 Read だが、`globals.css` の `@custom-variant` 定義から Tailwind 標準の `dark:` バリアントを `.dark` クラスベースで再定義していることが確認できる。これは shadcn の標準パターン）。
- `dark:prose-invert` は Tailwind の `dark:` バリアント機構に乗るユーティリティなので、**この `@custom-variant` 再定義と完全に噛み合う**（`dark:` の実体が何であれ、`dark:prose-invert` はその条件下で `prose-invert` を適用するだけ）。矛盾なし。
- ⚠️ `app/[locale]/layout.tsx` 側で実際に `<html class="dark">` のように **クラスをどこで付け外ししているか** は未確認（読む指示のファイルには含まれていたが本ラウンドでは `globals.css` の定義確認を優先した）。**未確認**: layout.tsx 内の具体的なテーマ切り替えトリガー（`next-themes` 等の使用有無）。他の参加者のレンズで確認済みなら整合性チェックだけで済む。

### 4. 降格済み見出し（README 最上位が `h3`）のスケール調整

`prose-headings:` は h1〜h6 と `th` に一括適用、`prose-h3:` のように **個別タグ修飾子** も存在する（Context7 確認済み: `class-reference.md`）。例:

```html
<article class="prose prose-sm max-w-none prose-h3:text-base prose-h3:font-semibold prose-h4:text-sm">
```

`readme-html.ts:27-34` の `HEADING_SHIFT`（`h1→h3` … `h5/h6→h6`）と組み合わせても、**`prose-h3:` 等のタグセレクタは DOM 上の実タグ名に対して効く** ため、シフト後のタグ構成のままで見た目のスケールだけ `prose-h3:` 系ユーティリティで復元・調整できる。デフォルトの `prose` は「文書内の最上位見出しが `h1`」を想定した相対スケールを持つため、**無調整だと `h3` 始まりの見た目がやや小さめになる可能性がある**——これは実装フェーズで実ブラウザ確認が必要な項目であり、本ラウンドでは「調整手段が存在する」ことまでを確認する。

### 5. `not-prose` の用途

`prose` 適用範囲内で「ここだけは prose のスタイルを外したい」ブロックに使う一括除外ユーティリティ（Context7 確認済み: `plugin.md` の Generated Variants 記載）。本件では、README 本文全体を `prose` 化する方針であれば、通常は不要。ただし将来的に README 内に **埋め込みウィジェットやカスタムブロックを許可リストに追加する** 場合、その要素にだけ `not-prose` を当てて prose のリセットから逃がす、という用途はありうる（現状の `ALLOWED_TAGS`・`readme-html.ts:46-92` を見る限り、そのような要素は今のところ存在しないため **現時点で使う場面はない**）。

### 6. Preflight と typography の関係（Preflight を切る選択肢について）

Context7 の公式説明（`README.md` / `_autodocs/README.md`）:

> "By default, Tailwind removes browser styling, which is useful for application UIs but can be surprising for content from rich-text editors or markdown files. The `@tailwindcss/typography` plugin aims to provide excellent typography **without the downsides of disabling base styles**."

つまり **typography プラグインは「Preflight を維持したまま、`.prose` 配下だけスコープを絞って装飾を復元する」ことこそが存在意義** であり、Preflight と typography はセットで使うのが公式に想定された設計。

**Preflight を切る案が不可な根拠**: `app/globals.css:150-165` の `@layer base` は `* { @apply border-border outline-ring; }` `body { @apply bg-background text-foreground; }` `html { @apply font-sans; }` を Preflight 前提の CSS カスケードで組んでおり、Preflight（ブラウザ既定値のリセット）を切ると shadcn コンポーネント一式（`button.tsx` / `input.tsx` 等、コメントに明記あり）のフォーカスリング・ボーダー・フォント指定が二重定義・崩れの原因になる。**Preflight はグローバル適用**（v4 でも無効化オプションは「プラグイン全体を読み込まない」単位でしか存在せず、`.readme-content` だけスコープを絞って切ることはできない）。→ **不可（他 UI 全体を道連れにする）**。

### 7. 代替案比較

| 案 | 実装コスト | 保守性 | 安全性 | 備考 |
|---|---|---|---|---|
| **① `@tailwindcss/typography`** | 低（CSS 1 行 + `package.json` 1 行 + `readme-section.tsx` のクラス変更のみ） | 高（Tailwind 公式・アップデート追従・テーマトークンとの連動は別途要検証） | 高（サニタイズ後の HTML に対する **装飾のみ**。属性・タグの許可を増やさない） | 見出しスケール調整は `prose-h3:` 等で対応可（§4） |
| ② 自前スコープ付き CSS（`.readme-content h3{...}` 等） | 中〜高（見出し・リスト・コード・テーブル・blockquote 等を手動で網羅、ダークモード分岐も自前実装） | 低（Tailwind のテーマトークン変更に追従させる保守が継続的に発生。属人化しやすい） | 高（同上、サニタイズ済み HTML への装飾のみ） | 既存コメント（`readme-section.tsx:125` 「新規依存の追加禁止」）は本タスクで見直し対象と推定 |
| ③ `transformTags` でタグごとに Tailwind ユーティリティを直接注入 | 中（`readme-html.ts` の変換ロジックに全許可タグ分のクラス付与処理を追加） | 中（`sanitize-html` の `class` 属性をサニタイズの許可リストに追加する必要があり、`readme-html.ts` の責務が「サニタイズ」から「サニタイズ+スタイリング」に肥大化） | **要注意**: `class` 属性をサニタイズ対象に加えると、任意の CSS クラス名文字列がサニタイズ後 HTML に残る経路が新たに生まれる（XSS 直結ではないが、CSS インジェクション的な想定外スタイル適用のリスク面で①③より監査コストが増える。既存の `ALLOWED_ATTRIBUTES`（`readme-html.ts:94-104`）は意図的に最小構成を保っている設計思想と衝突する） | 非推奨 |

## 推奨

**① `@tailwindcss/typography` プラグイン導入** を推奨する。理由:
- 変更範囲が最小（CSS 1 行 + 依存追加 + コンポーネントのクラス変更）で `sanitize-html` の許可リストに一切手を入れない（③のセキュリティ懸念を回避）
- Preflight との併用が公式設計そのもの（§6 の一次情報）
- ダークモード・見出し降格・レスポンシブサイズの全要件が `dark:prose-invert` / `prose-h3:` / `prose-sm` の標準修飾子だけで満たせる（§2〜4）
- `readme-section.tsx:125` のコメント「新規依存の追加禁止（タスクスコープ外）」は **当時のタスクスコープの制約であり、今回の書式修正タスクではこの制約自体を見直す** 必要がある（実装担当・スコープ判定は他の参加者の議論に委ねる）

## 未確認事項

- `app/[locale]/layout.tsx` の実際のテーマ切り替えトリガー実装（`next-themes` 使用有無・`.dark` クラスの付け外し箇所）は本ラウンドで Read していない（`globals.css` の `@custom-variant` 定義から間接的に整合性を確認したのみ）
- `prose-h3` 始まりの見た目が無調整でどの程度小さく見えるかは実ブラウザでの目視確認が必要（Context7 のドキュメントには数値スケール表までは含まれていなかった）

### `readme_fidelity` — 主張
<sub>2026-08-21T18:02:26+09:00</sub>

# 書式の再現度: 現状分析（readme_fidelity round1）

## 結論

**バグの主因は許可タグ・属性の欠落ではなく、CSS 側にある。** README コンテナに一切のタイポグラフィスタイルが当たっていない（`prose`/typography プラグイン未導入、見出し・リスト・引用・コードブロック・表を狙う CSS が存在しない）。Tailwind v4 の Preflight が見出しを `font-size: inherit; font-weight: inherit` に、`ul`/`ol` を `list-style: none; margin:0; padding:0` にリセットするため、`sanitizeReadmeHtml` が正しく `<h3>`〜`<h6>` や `<ul>`/`<li>` を出力していても **視覚的には素のテキストと区別がつかない**。これはスクリーンショットの症状（見出し・リスト・段落が同じ大きさで縦に並ぶ、リストにマーカーが無い、インラインコードだけ等幅）と完全に一致する。許可リストの拡充（`<details>` 等）は副次課題であり、優先度はこの CSS 欠落より低い。

## 根拠 1: 実出力の確認（`bcaudan/jasmine-spec-reporter`）

```
curl -s "https://gem-hunter.kinamocchi-tech.workers.dev/ja/repos/bcaudan/jasmine-spec-reporter"
```

RSC ストリーミングのため素の HTML には README 本文が直接出ず、レスポンス末尾の `<div hidden id="S:1">...</div>`（クライアントが `$RC("B:1","S:1")` で差し込む確定済みコンテンツ）に本文が入っている。抽出結果（`/tmp/readme_section.html`）:

```html
<section aria-labelledby="readme-heading" class="mt-6">
  <h2 id="readme-heading" class="text-lg font-semibold">README</h2>
  <div class="mt-2 max-w-none space-y-3 text-sm leading-relaxed break-words">
    <div><div><h3>jasmine-spec-reporter</h3><a href="#jasmine-spec-reporter"></a></div>
    <p>...badges (img)...</p>
    <p>Real time console spec reporter for jasmine testing framework.</p>
    <p><a ...><img src="...screenshot.gif" alt="" /></a></p>
    <div><h3>Usage</h3><a href="#usage"></a></div>
    <div><h4>Installation</h4><a href="#installation"></a></div>
    <p>Install <code>jasmine-spec-reporter</code> via npm:</p>
    <div><pre><code>npm install jasmine-spec-reporter --save-dev
    </code></pre></div>
    <div><h4>Examples</h4><a href="#examples"></a></div>
    <ul><li><a ...>Jasmine node tests</a></li>...</ul>
    ...
    <div><h3>Development</h3><a href="#development"></a></div>
    <div><h4>Requirements</h4><a href="#requirements"></a></div>
    <ul><li>npm &gt;= 5</li></ul>
    <div><h4>Commands</h4><a href="#commands"></a></div>
    <ul><li>install dependencies: <code>npm install</code></li>...</ul>
  </div>
</section>
```

**確認できたこと**:
- `sanitizeReadmeHtml` の見出し +2 降格は正しく機能している（`h1→h3`, `h2→h4` が実際に出力されている）
- `<ul>`/`<li>`・`<pre><code>`・`<p>`・`<img>`・アンカーリンクはすべて正しくタグとして出力されている（=許可リスト自体はここでは機能している）
- コンテナ div のクラスは `mt-2 max-w-none space-y-3 text-sm leading-relaxed break-words` のみ。`prose` クラスも、見出し・リスト個別のスタイルクラスも **一切付いていない**（`src/ui/readme-section.tsx:128`）

## 根拠 2: CSS 側の裏付け

- `package.json` / `app/globals.css` を grep しても `@tailwindcss/typography` / `prose` は **一件もヒットしない**
- `app/globals.css:1` は `@import "tailwindcss"`（Tailwind v4）。v4 の Preflight は既定で以下を行う:
  - `h1`〜`h6`: `font-size: inherit; font-weight: inherit;`（ブラウザ既定の拡大・太字を打ち消す）
  - `ul`, `ol`: `list-style: none; margin: 0; padding: 0;`（マーカー・インデントを消す）
  - `blockquote`, `p`, `figure`: `margin: 0`
- 一方 `code` 要素はブラウザの UA スタイルシートが `font-family: monospace` を持ち、Preflight はこれを打ち消さない（`font-family` は Preflight のリセット対象外）ため、**インラインコードだけ等幅で残る** — スクリーンショットの症状と一致する

→ `src/ui/readme-html.ts` は「危険なタグを落とす」役割は果たしているが、**「見た目を与える」役割を持つ CSS が存在しない**。これは `readme-html.ts` の実装の問題ではなく `src/ui/readme-section.tsx:128` のコンテナ クラス、または `app/globals.css` 側の欠落。

## GitHub レンダリングとの差分（現状の許可リストで落ちる要素）

`bcaudan/jasmine-spec-reporter` の README では未検証だが、`ALLOWED_TAGS` / `transformTags`（`src/ui/readme-html.ts:46-104`）を突き合わせると、GitHub の README レンダリングに一般的に含まれる以下は **構造的に必ず落ちる**（sanitize-html の `disallowedTagsMode` 既定 `discard` によりタグは消え中身のテキストだけ残る）:

| GitHub の要素 | 現状 | 備考 |
|---|---|---|
| `<details>`/`<summary>`（折りたたみ） | 落ちる | `ALLOWED_TAGS` に無し。中身は展開済み状態でそのまま流れ込む |
| タスクリストの `<input type="checkbox" disabled checked>` | 落ちる | `input` はそもそも禁止タグ（意図的・XSS 対策として妥当） |
| シンタックスハイライトの `<span class="pl-*">` | 落ちる（`span` 自体は許可だが `class` 属性が `ALLOWED_ATTRIBUTES` に無い） | コードブロックが単色になる。`pre`/`code` の中身が `<span class="pl-c1">`,`<span class="pl-s">` 等で構成されている場合、タグは残るが色分けクラスが剥がされ実質プレーンテキスト表示 |
| GitHub アラート記法 `> [!NOTE]` 由来の `<div class="markdown-alert markdown-alert-note">` | 落ちる（`div` は許可だが `class` 未許可） | 注意喚起の枠・アイコンが消え、通常の引用/段落と同じ見た目になる |
| 絵文字画像 `<g-emoji>` | **タグ自体が非標準要素**。`ALLOWED_TAGS` に無いため落ちる | 中のテキスト（Unicode 絵文字 or alt）は残る想定だが要実機確認 |
| バッジ・アンカー用 `<svg class="octicon">` | 落ちる | `svg` は `ALLOWED_TAGS` に無し。見出し横のリンクアイコン等が消える（実害は小さい） |
| 脚注 `<sup id="fnref-...">` / `<section class="footnotes">` | `sup` はタグ許可だが `id`/`class` 属性は許可されていない（`ALLOWED_ATTRIBUTES` に `sup` のエントリ無し） | 脚注番号は表示されるがジャンプできない可能性 |
| `<table>` の `class="table" ` 等の GitHub 独自属性 | 落ちる（`table`/`th`/`td` の属性は `colspan`/`rowspan` のみ許可） | 罫線自体は自前 CSS 次第（後述） |

⚠️ **推定であることの明記**: `api.github.com` への直接アクセスがこのセッションから 403 になる可能性が高いため、上記は `src/ui/readme-html.ts` の許可リストとの静的突き合わせによる推定。`bcaudan/jasmine-spec-reporter` の README には `<details>` やアラート記法が含まれていない（今回の実出力では未観測）。実測が要る場合は `<details>` や `> [!NOTE]` を含む README（例: 多くの大型 OSS）で別途 curl 検証が望ましい。

## 「書式が反映されている」と言える最低ライン

書式再現度のレンズとして、以下を満たせば「書式が反映された README」と言えると考える（優先度順）:

1. **見出しの階層が視覚的に分かる**（h3 > h4 > h5 の順でフォントサイズ/太さが段階的に小さくなる）— 現状 **未達**（Preflight で inherit のため段階なし）
2. **リストにマーカーとインデントがある**（`ul` は `disc`、`ol` は数字、ネストで字下げ）— 現状 **未達**
3. **コードブロック（`pre`）が枠・背景色・等幅フォントで区別される**（インライン `code` との区別も含む）— 現状 **未達**（`pre` に何のスタイルも無く、中の `code` だけ UA 既定の等幅が乗る。枠や背景は無い）
4. **表に罫線がある**（`table`/`th`/`td` に border）— 現状 **未達**（同上、CSS 皆無なら罫線なしで単なる連続テキストになる可能性が高い。要実機確認だが `readme-section.tsx` にテーブル用 CSS が無い以上ほぼ確実）
5. **引用（`blockquote`）が引用と分かる**（左ボーダー・インデント・色の違い）— 現状 **未達**
6. **画像が原寸で溢れない**（`max-width: 100%` 相当）— `img` に `width`/`height` 属性は転写しているが、CSS 側で `max-width: 100%; height: auto` を強制していないとレイアウト崩壊の恐れ。要確認

**この 6 項目のうち 1 つも現状の CSS では保証されていない。** つまり `readme-html.ts` の許可リスト云々よりも先に、**コンテナへの typography CSS 付与が必須**（`@tailwindcss/typography` の `prose` クラス採用、または自前の見出し/リスト/pre/table/blockquote スタイル定義のどちらか）。

## 見出し +2 降格が書式に与える影響

`HEADING_SHIFT`（`h1→h3` … `h5`/`h6→h6`）自体は **ページの見出し階層をユーザーが期待する場所に収める**（ページ全体の `h1` はサイトタイトル、`h2` はセクション見出し「README」なので README 内部は `h3` 以下にするのが正しい設計判断）という点で妥当。ただし今回の不具合との関係で 2 点指摘する:

1. **`prose` クラスを後から導入する場合、`prose-h1`/`prose-h2` 用のスタイルは「使われない」ことになる。** typography プラグインは既定で `h1`〜`h6` 全部にスタイルを定義するため実害はないが、`h1`/`h2` は README 内に絶対出現しない（`transformTags` で必ず `h3` 以上に変換される）ことをスタイル設計側が前提にしてよい。
2. **`h5`/`h6` が両方 `h6` に丸められる**（cap）ため、GitHub 側で `h5` と `h6` の見た目差（フォントサイズがほぼ同じ）がさらに縮まる。書式再現度への実害は小さい（GitHub 自身も h5/h6 の差はごく僅か）。

いずれも「見出し降格」自体は書式崩れの原因ではない。**原因はシフト後のタグに対応する CSS が無いこと。**

## 過剰再現の弊害（線引きの提案）

以下は **再現すべきでない／慎重であるべき** 要素と理由:

- **GitHub 独自クラス（`pl-*` シンタックスハイライト・`octicon`・`markdown-alert-*`）への依存**: これらのクラス名に依存したスタイルを自サイトに実装すると、GitHub 側の内部実装変更で無言のまま崩れる密結合になる。シンタックスハイライトが欲しいなら、自前で `highlight.js`/`shiki` 等をコードブロック言語ヒントから独自適用する方が保守可能（ただし別 Issue 相当のスコープ）
- **バッジ画像（`img`）をそのまま原寸表示**: `shields.io`/Travis CI 等の小さいバッジが README 内に列挙されると、レイアウト次第では不格好に大きく見える・並びが崩れる。`prose img` の既定（ブロック要素化・`max-width:100%`）だけだとバッジが 1 枚ずつ改行される崩れ方をしやすい。バッジ画像を検出して抑制する（例: 高さ制限）といった特別扱いは過剰実装になりやすく、「読めればよい」の最低ラインを超えるため優先度低
- **`<details>`/タスクリストの完全再現（インタラクティブ化）**: `<details>` を許可タグに追加し `open`/`disabled` 等の属性も通す実装は、クリック挙動・アクセシビリティ（`role`）まで作り込むと工数が跳ねる。「展開済みの中身がそのまま読める」（現状の discard 挙動）を許容範囲とし、折りたたみ UI の完全再現は後回しでよい
- **自サイトの視覚言語との衝突**: `prose` を無条件適用すると、GitHub 由来のインラインスタイル的な色使い（例えばリンク色・強調色）が sidebar/shadcn デザイントークン（`--color-primary` 等・`app/globals.css` 参照）と衝突する可能性がある。`prose-neutral` 系のニュートラルバリアントを使うか、`--tw-prose-*` 変数を自サイトのデザイントークンにマッピングし直す一手間が必要（そのまま `prose` を貼るだけでは色が浮く恐れ）

## 反対されうる点

- 「これは CSS の問題であって `readme-html.ts`（サニタイズ層）の問題ではないので、このレンズのスコープ外では」という反論があり得る。しかし今回の飼い主指摘（「書式が反映されない」）の実機症状は **タグの欠落ではなく CSS の欠落で 100% 説明がつく** ため、書式の再現度を論じる上でこの事実を外すと誤った方向（許可タグを増やす）に工数を投じてしまうリスクがある。あえてスコープに含めた
- `<details>`/シンタックスハイライト等の許可リスト差分は `bcaudan/jasmine-spec-reporter` では実測できておらず、静的コード突き合わせによる推定に留まる点は弱い根拠。他 lens（`removal_impact` 等）が別リポジトリで実測すれば補強できる

### `a11y_theme` — 主張
<sub>2026-08-21T18:04:05+09:00</sub>

# README 書式方式への a11y / テーマ整合レンズからの結論

## 結論（先出し）

- **① `@tailwindcss/typography` を「未カスタマイズの `prose`」で入れることには反対**。`--tw-prose-*` を全項目セマンティックトークンへ上書きするなら許容できるが、それをやると③のうまみ（既製カラースケール）がほぼ消える。
- **② 自前のスコープ付き CSS（`app/globals.css` に `.readme-content` 等でスコープ）を推奨**。新しい raw 色を一切増やさず、既存の 10 トークンだけを再利用する形で書けば、`tools/check_contrast.py` の既存ゲートがそのまま README にも効く。
- ③（サニタイズ時のユーティリティクラス注入）は a11y 観点で積極的な理由がない。`sanitize-html` の変換パスに Tailwind クラス名を混ぜると、危険入力（第三者 HTML）の許可リストとスタイル注入という 2 つの責務が 1 箇所に混線し、`readme-html.ts` の脅威モデル（`docs 1-22` のコメント参照）を複雑にするだけで a11y 上の利点はない。②で同じ見た目を安全に達成できる。
- **現状（未着手）はどちらでもなく「ブラウザ既定スタイルに委ねる」**（`readme-section.tsx` L124-126 のコメント）。これは a11y 上すでに具体的な不具合を持っている（下記 §5）。①②③のどれを選んでも、この既定スタイル依存からは脱する必要がある。

---

## 1. テーマ整合

`app/globals.css` の `@theme inline`（L7-69）で確定している **10 セマンティックトークン**（`--color-bg` / `--color-bg-subtle` / `--color-fg` / `--color-fg-muted` / `--color-border` / `--color-accent` / `--color-accent-fg` / `--color-danger` / `--color-danger-fg` / `--color-ring`）が、コントラスト実測込みで唯一の正本（`ui-ux-guidelines.md` §2.1-2.2）。

`@tailwindcss/typography` の `prose` は独自の `--tw-prose-body` / `--tw-prose-headings` / `--tw-prose-links` / `--tw-prose-code` 等（既定値は Tailwind の gray/slate スケールへの直書き）を持つ。これをそのまま使うと:

- `ui-ux-guidelines.md` §2.1 「生の色名（`slate-700` 等）をコンポーネントに直接書かない」に文面上は違反しないが（コンポーネント側には書かれない）、**実質は同じ問題**——サイトの配色とは独立した第二のカラースケールが `prose` プラグインの内部に生まれ、以後どちらのスケールを更新すべきか判断コストが発生する（本ガイドライン §2.1 冒頭の意図「配色変更が全画面に波及するのを防ぐ」が壊れる）。
- `--tw-prose-*` は CSS カスタムプロパティなので上書き自体は可能（Tailwind Typography 公式が想定する拡張点）。**採用するなら全項目を `app/globals.css` 内でセマンティックトークンへエイリアスする** ことを必須にする（例: `--tw-prose-body: var(--color-fg); --tw-prose-headings: var(--color-fg); --tw-prose-links: var(--color-accent); --tw-prose-bold: var(--color-fg); --tw-prose-counters: var(--color-fg-muted); --tw-prose-bullets: var(--color-border); --tw-prose-hr: var(--color-border); --tw-prose-quotes: var(--color-fg); --tw-prose-quote-borders: var(--color-border); --tw-prose-captions: var(--color-fg-muted); --tw-prose-code: var(--color-fg); --tw-prose-th-borders: var(--color-border); --tw-prose-td-borders: var(--color-border);` と、ダーク側の `--tw-prose-invert-*` 一式も同様に）。1 項目でも上書き漏れがあれば §3 のゲート抜けが起きる（下記）。
- ②（自前スコープ CSS）はそもそも `var(--color-*)` を直接参照するだけなので、この「上書き必須リスト」を持つ必要がない。**新規トークンをゼロに保てる** という点でテーマ整合が最も単純。

**具体策（②を選ぶ場合の指針）**: `app/globals.css` の `@layer base` の外（README 専用スコープ）に `.readme-content` を追加し、`h3`〜`h6` / `p` / `a` / `code` / `pre` / `blockquote` / `table th,td` 等の要素セレクタで **既存 10 トークンのみ** を `color:` / `background-color:` / `border-color:` に指定する。新しい `--readme-*` 変数を作る誘惑があるが、作った時点で `check_contrast.py` の検査対象外になる（§3 参照）ので避ける。

---

## 2. ダークモード

`app/[locale]/layout.tsx` を実読した結果、**`next-themes` の `ThemeProvider` はまだ実装されていない**（`ThemeProvider` / `attribute=` の grep が 0 件）。`app/globals.css` 側には `@custom-variant dark (&:is(.dark *))`（L5）と `.dark { ... }` ブロック（L113-148）は既に存在するが、**`<html>` に `.dark` クラスを付与する主体（トグル UI・`ThemeProvider`）がまだ配線されていない**。つまり現時点でダークテーマは「配線待ちの静的な CSS 変数セット」であり、稼働はしていない。

このことから README スタイリングへの指針:

- **`prose-invert`（`dark:prose-invert` として `.dark` 祖先で発火させる想定のクラス）は採用しない**。理由は 2 つ: (a) `prose-invert` も独自の invert カラースケールを持ち §1 と同じ二重管理問題を抱える、(b) それ以前に **`.dark` トグル自体が未実装** なので、`prose-invert` を今書いても検証しようがない（動作確認できない状態で終わる= `SD-1` 違反リスク）。
- ②（自前 CSS）で `var(--color-fg)` 等のトークン参照だけを書けば、**`dark:` バリアントも `prose-invert` も一切不要**——トークン自体が `.dark` セレクタ配下で値を持っているため（例: `--foreground` は `:root` で `oklch(0.145 0 0)`、`.dark` で `oklch(0.985 0 0)`）、`.dark` が将来配線された瞬間に README 本文も自動で追従する。**ダークモード対応の実装コストをゼロにできる** のがトークン直参照の最大の利点であり、これは①でも `--tw-prose-*` を上書きしてさえいれば同様に効く（`--tw-prose-invert-*` も上書き必須な点は §1 の通り）。
- コードブロック背景・引用罫線・表罫線・リンク色の具体的な割当（両テーマで破綻しないことを確認済みの既存トークンのみを使う）:
  - コードブロック（`pre`, `code`）背景: `--color-bg-subtle`（カード面トークン。ライト `oklch(0.97 0 0)` / ダーク `oklch(0.269 0 0)`。地の `--color-bg` と視覚的に区別がつく値としてすでに確定済み）
  - 引用（`blockquote`）左罫線・表（`table`）罫線: `--color-border`（**既に 3:1 ゲート済み**。§2.2 の実測表でライト 3.95:1 / ダーク 4.08:1 が PASS 確認済み——罫線は非テキストなので 3:1 要件で足りる）
  - リンク色: `--color-accent`（§2.1 の用途表に明記の「リンク・主ボタン」用トークン。4.5:1 ゲート済み）。⚠️ 現状 `readme-section.tsx` L138 の「GitHub で見る」リンクは `text-primary` を使っており `--color-accent` ではない（`--primary` は `check_contrast.py` の検査対象外トークン）。README **本文中** のリンク（第三者 HTML 由来で数が多い）はこの既存の慣習に倣わず、**ゲート対象の `--color-accent` を明示的に使う** ことを推奨する（本文リンクは 1 本の「GitHub で見る」リンクと違って数量・出現箇所を制御できないため、機械ゲートの網に必ず載せておきたい）。

---

## 3. コントラスト（`tools/check_contrast.py` の検査範囲を実読して確認）

`tools/check_contrast.py` は **`app/globals.css` の `:root` / `.dark` ブロックに書かれた固定 9 個の raw 変数**（`--background` / `--muted` / `--foreground` / `--muted-foreground` / `--border` / `--accent` / `--accent-foreground` / `--destructive` / `--destructive-foreground`）だけを正規表現でパースし、**あらかじめハードコードされた 11 ペア**（fg vs bg, fg-muted vs bg, border vs bg, accent vs bg, accent-fg vs accent, danger vs bg, danger-fg vs danger, ring vs bg, ring vs bg-subtle 等・L13-24 のコメント）のコントラストだけを計算する（L38-39 で `CSS_PATH` を `app/globals.css` に固定、パースも同ファイル限定）。

**含意**:

- README 用に **新しい raw 色**（例: `--tw-prose-code: #1f2937` のような Tailwind Typography の既定値、または自前 CSS で新規に書いた `--readme-code-bg: oklch(...)`）を導入すると、**このゲートは一切関知しない**。検査対象の変数名リストにもペアリストにも載らないため、閾値割れのまま気づかず merge されうる。
- したがって **③（サニタイズ時のユーティリティクラス注入）は特に危険**: 注入するクラス（例 `prose-slate` や独自の `text-gray-700` 相当）が実質的に新しい色を持ち込むが、注入場所が `readme-html.ts`（サニタイズ変換）なので `app/globals.css` を見ている `check_contrast.py` からは完全に不可視。
- **推奨**: README のスタイル（①でも②でも）は §1/§2 で述べた **既存 10 トークンの再利用のみ** に限定する。新規色をゼロに保てば、README のコントラストは `check_contrast.py` の既存 22 判定にただ乗りする形で保証される——**README 専用の新しいコントラスト検査を追加開発する必要がなくなる**（YAGNI・CLAUDE.md「1 箇所しか使わない抽象化レイヤーを先回りで追加しない」の精神にも合致）。
- 逆に、もし①を採用して `--tw-prose-*` の上書きを 1 項目でも忘れた場合、または②で `--readme-*` のような新変数を作ってしまった場合は、`check_contrast.py` 側の「検査対象変数リスト」（現状 9 個固定）を拡張する追加実装が必要になる。**この追加実装が要る設計は避けるべき**——ゲートを README 側の都合で毎回拡張し続けるのは持続可能でない。

---

## 4. 見出し階層(視覚 vs セマンティック)

前提の再確認（`readme-html.ts` L27-34、`ui-ux-guidelines.md` §7.0）:

- ページ全体で `h1` を持つのは共有ヘッダーのツールタイトルだけ。
- 詳細ページの「README」セクション見出しは `h2`（`readme-section.tsx` L116: `text-lg font-semibold` = 18px）。
- README 本文の見出しは `+2` シフト済みで `h3`〜`h6`（`h1→h3, h2→h4, h3→h5, h4以降→h6` で cap）。

`ui-ux-guidelines.md` §2.3 のタイポスケールは **`12/14/16/20/24px` の 5 段階のみ、中間値を足さない** が正本。ここで 1 点、既存コードとの整合に注意が必要: セクション見出し「README」自体が `text-lg`（18px）を使っており、**厳密には 5 段階のどれにも一致しない**（既存の実装で、本タスクのスコープ外の既存差分だが、README 見出しのサイズ設計はこの 18px を「超えてはいけない上限」として扱う必要がある）。

**指針（視覚とセマンティックのねじれ防止）**:

1. README 本文の `h3`〜`h6`（4 段階）に、5 段階スケールのうち **18px（セクション h2）未満の範囲**——`16px` と `14px` の 2 段階しか実質使えない（`12px` は本文メタ情報用途で埋まっており、見出しに転用すると §2.3 のカード内規約と衝突するため避ける。よって見出し専用に残るのは 16px と 14px の 2 段階のみ）。4 段階を 2 サイズに収めるには **フォントウェイトを併用** して差をつける（§2.3 の「カード内 3 段階」がすでに size + weight の組み合わせで階層を作っている前例に倣う）。
2. 具体案:

   | タグ（変換後） | 元の見出しレベル | 視覚サイズ | ウェイト |
   |---|---|---|---|
   | `h3` | 元 `h1` | `16px`（`text-base`） | `700`（bold） |
   | `h4` | 元 `h2` | `16px`（`text-base`） | `600`（semibold） |
   | `h5` | 元 `h3` | `14px`（`text-sm`） | `600`（semibold） |
   | `h6` | 元 `h4`〜`h6`（cap） | `14px`（`text-sm`） | `500`（medium） |

   いずれも `18px`（セクション h2「README」）を **上回らない** ため、「README 内の見出しがページ側の h2 より大きく見える事故」を構造的に防げる。
3. これは②（スコープ付き CSS で `.readme-content h3 {...}` 等をタグごとに個別指定）なら自然に書ける。①（`prose`）は既定で `h3`/`h4` に `1.25em`/`1.125em` 相当の相対サイズを割り当てており、かつ **「+2 シフト後のタグである」ことをプラグインは知らない** ため、上記の size/weight テーブルを含め見出し関連の `--tw-prose-*`・および Typography プラグインの `h3`,`h4`,`h5`,`h6` 個別スタイル（CSS では `font-size` は変数化されておらずクラスごとの静的値のため、上書きには `[&_h3]:text-base [&_h3]:font-bold` のような追加の Tailwind 個別指定が結局必要になる）を **全て上書き** することになり、プラグイン採用の省力化メリットがほぼ消える。この点でも②が実装コストで有利。
4. 見出しに `id="user-content-*"` が保持される（`readme-html.ts` L15, L97-100）ため、フォーカス時のアウトライン（§7.3 の `focus-visible:ring-*`）は見出し自体ではなくページ内アンカー `<a href="#...">` 側の話であり本節と独立——ただし README 内リンクがアンカー遷移する際、フォーカス移動先の見出しに `scroll-margin-top` が必要かは sticky ヘッダーの有無次第（§7.3 末尾）。本アプリの共有ヘッダーが sticky でなければ不要、sticky であれば README 内アンカー着地点にも同じ配慮が要る（要確認事項として残す）。

---

## 5. 第三者コンテンツの制御（視覚破綻防止）

`readme-section.tsx` の現状ラッパー（L127-130）は `max-w-none space-y-3 text-sm leading-relaxed break-words` のみで、**画像・表・コードブロックのサイズ制御が一切ない**。これは①②③どの方式を選んでも共通で対処が必要な、**既存の実際の不具合**（未着手状態の欠陥であり本 Issue のスコープ内）。

- **画像の溢れ**: `readme-html.ts` は GitHub 由来の `width` / `height` 属性をそのまま透過する（L191-196）。README 冒頭に並ぶバッジ画像は通常小さいので問題にならないが、**スクリーンショット画像（`width="1200"` 等）はコンテナ幅を突破する**。`img { max-width: 100%; height: auto }` を README スコープに必須で追加する（`ui-ux-guidelines.md` §8.3 「画像は `width`/`height` を必須指定」という **サイト自前コンポーネント** 向けの規約とは別に、**README のような可変・信頼できない寸法の画像には `max-width:100%` の上書きが必要**——この違いを明示的にドキュメント化すべき、§6 参照）。
- **表の溢れ**: `table`/`th`/`td` は許可タグ（`readme-html.ts` L74-83）。列数が多い表は `min-width` を強制し、ページ全体を横スクロールさせうる（`ui-ux-guidelines.md` §3 「200% 拡大で横スクロールが発生しないこと（`NFR-15`）」に抵触するリスク）。**表だけを `overflow-x: auto` のコンテナで囲み、ページ本体を横スクロールさせない**（本セッションの Artifact 執筆規約と同じ考え方だが、これはこのプロジェクト自身の `NFR-15` からも独立に要求される）。表に罫線が全く見えない（ブラウザ既定は無地）ことも視認性の問題なので `--color-border` で明示。
- **コードブロックの溢れ**: `pre` も同様に長い1行コードが横に伸びる。`pre { overflow-x: auto }` をコンテナ単位で（ページではなく）許可する。
- **GitHub 独自装飾の残骸**: `sanitize-html` の許可属性リスト（`ALLOWED_ATTRIBUTES`、L94-104）には `div`/`span` の属性が一切含まれない。GitHub HTML によくある `align="center"` や `class="..."` は自動的に落ちるため、**中央寄せ等の意図は失われるが崩れた見た目（属性だけ浮く等）にはならない**——これは安全側の劣化で対処不要、ドキュメントに「意図的な仕様」として書き添える程度でよい。
- **バッジ画像の折返し**: バッジは通常 `<img>` が横に連続するだけで `<p>` 内インライン表示になるため、コンテナ幅で自然に折り返される（`break-words` と `max-w-none` が既にある）。ただし `img` 同士の間隔が詰まりすぎる見た目になりやすいので `img { display: inline-block; margin: 0.125rem }` 程度の軽い調整を推奨（必須ではない）。

---

## 6. ドキュメント追記案

`ui-ux-guidelines.md` に **新設 §2.5「README 本文のタイポグラフィと書式」** を追加することを提案する（§2 はすでにトークン・タイプスケール・コントロールサイズの正本セクションであり、README 書式もトークン適用の一形態として同じ場所に置くのが一貫する。§6 に置くと「詳細ページ」という画面単位の記述に色・サイズの数値規約が混在してしまい、§2.2/§2.3 との二重管理になる）。

**§2.5 の文言案**（`§` 番号・トークン名は本ファイルの現行版に合わせた。他エージェントの並行提案と数値が衝突する場合は lead 裁定を仰ぐ想定で「案」と明記）:

```markdown
### 2.5. README 本文のタイポグラフィと書式（Issue #334 拡張）

詳細ページの README セクション本文（`readme-section.tsx` の `dangerouslySetInnerHTML`）に
書式を当てる際は、以下を満たす。

- 🔴 **新しい raw 色を追加しない**。§2.1 の 10 セマンティックトークンのみを再利用する
  （`tools/check_contrast.py` は `app/globals.css` の固定変数リストしか検査しないため、
  新規トークンはコントラストゲートの対象外になる）。
- 🔴 **`@tailwindcss/typography` を採用する場合、`--tw-prose-*` と `--tw-prose-invert-*` を
  全項目セマンティックトークンへエイリアスする**（1 項目でも既定値のまま残すと上記ゲートを
  すり抜けた未検証の色がページに出る）。
- README 本文の見出し（`h3`〜`h6`。`readme-html.ts` の +2 シフト後のタグ）は、セクション見出し
  「README」（`h2`・18px）を **視覚的に上回らない**。5 段階タイプスケール（§2.3）のうち
  16px / 14px の 2 段階とフォントウェイトの組み合わせで 4 段階を表現する。
- `img` は `max-width: 100%; height: auto` を必須にする（README 由来の画像は寸法が
  信頼できないため、§8.3 のサイト自前画像規約とは別に上書きが要る）。
- `table` と `pre` は要素単体を `overflow-x: auto` のコンテナで囲み、**ページ本体を
  横スクロールさせない**（`NFR-15` / §3）。
- リンク色は `--color-accent`、コードブロック背景は `--color-bg-subtle`、引用・表の罫線は
  `--color-border` を使う（すべて既存ゲート済みトークン）。
```

あわせて **§9（完了・成功の定義）** に 1 行追加を提案:

```markdown
- [ ] §2.5 の README 書式が新規 raw 色を追加せず、既存トークンのみで実装されている
      （`tools/check_contrast.py` の検査対象を拡張していない）
```

---

## 反対されうる点（先回り）

- 「`@tailwindcss/typography` は業界標準で保守コストが低い」という反論は理解できるが、**このプロジェクトはすでに配色をトークン化・実測ゲート化済み** という特殊事情があり、プラグインの既定カラースケールをそのまま使うことは選択肢にない（全上書きが前提になる時点で「導入の手軽さ」という利点が縮む）。
- §4 の見出しサイズ案（16px/14px の 2 段階 + weight）は「4 段階の視覚差が乏しく単調では」という指摘がありうる。しかし §2.3 の「中間値を足さない」という 🔴 規定と、README h2 セクション見出し（18px）を超えない制約を両立させると、使える踏み台はこの 2 段階しか残らない。18px 制約自体を緩めたいなら、それは §7.0 の見出し階層改訂（`Issue #334 F-1/F-2`）を再度動かす話になり、本 Issue のスコープを超える。
- ②（自前 CSS）を推す一方で、実装工数（コードの型・DDD 上の置き場所）は自分のレンズの管轄外なので `impl_readme` / `arch_domain` 側の判断を優先してよい。ここでの主張は「a11y/テーマ整合の観点では②が最も低リスク」という点に限定する。

### `perf_bundle` — 主張
<sub>2026-08-21T18:05:00+09:00</sub>

# perf_bundle R1: README書式のパフォーマンス/バンドル影響分析

## 結論（要約）

1. **CSSはWorker本体（3MBゲート）の対象外**。`.open-next/assets` 配下の静的アセットとして Workers Static Assets 経由で配信され、3MB gzip 上限は `handler.mjs` を動的 import する Worker スクリプト本体だけにかかる。よって①②③のどれを選んでもCSS増分そのものはバンドル上限を圧迫しない。
2. **①`@tailwindcss/typography` 導入のCSS増分は数KB〜十数KB（raw）、gzipで1〜3KB程度と見積もる**（未インストールのため見積もり。根拠は下記）。現状の全体CSS（raw 40.6KB / gzip 8.2KB）に対して相対的に小さい。
3. **`limits.cpu_ms: 50` への影響は実質ゼロという仮説を支持**。CSSはビルド時に静的ファイル化され実行時CPUを消費しない。①②③のどれでも差はない。
4. **30,000文字上限はレイアウトコスト的には過剰な懸念ではない**。書式を当ててもDOM構造（許可タグ）は変わらないため見直し不要。
5. **横溢れ対策は未整備**。現行の `break-words` だけでは `<table>` と `<pre><code>` の横溢れを防げない。①を採用しても `table` は typography の既知の弱点（`pre` は `overflow-x:auto` が入るが `table` には入らない）でカバーされない。②か③で `table`/`pre` に個別に `overflow-x: auto; max-width: 100%` を当てる設計が必須。
6. **`tools/run_lighthouse.mjs` はperformanceをゲートしていない**（accessibility=100のみブロッキング）。かつ詳細ページのE2Eスタブ README には table/コードブロック/長いURL/バッジ画像が一切含まれておらず、横溢れの回帰をLighthouse/E2Eのどちらも検知できない状態。

---

## 根拠

### 1. CSS配信経路の実測（`open-next.config.ts` / `wrangler.jsonc` / `next.config.ts` を確認）

- `wrangler.jsonc`: `"main": ".open-next/worker.js"`, `"assets": { "directory": ".open-next/assets", "binding": "ASSETS" }`。
- `.open-next/worker.js`（router）は `await import("./server-functions/default/handler.mjs")` で本体を **動的import**。CSSファイル名（`2zfgn5tn_e7wb.css`）は `handler.mjs` 内に **パス文字列としてのみ** 52箇所出現し、CSS本文（セレクタ・宣言）は埋め込まれていない（`grep -c "font-family|@media"` = 10件で、いずれもJSのマニフェスト文字列・断片であり実CSSブロックではない）。
- `.open-next/assets/_next/static/chunks/2zfgn5tn_e7wb.css` が実CSS本体（raw 40,585B / gzip 8,178B）。`du -sh .open-next/assets` = 928K。
- `docs/03_design/infrastructure/cloudflare-infrastructure.md` L65: 「Workers Static Assets（JS/CSS/フォント・無料・無制限）」と明記済み。**静的アセットに3MB制限は適用されない**（同ファイルL286の「Worker バンドル: 3MB（圧縮後）」はWorkerスクリプト側のみ）。

→ **判定**: CSSはWorkers Static Assets側。3MB gzip 上限の対象外。

### 2. Worker本体の実サイズ（`npx wrangler deploy --dry-run` で実測・npm installなし）

```
✨ Read 35 files from the assets directory /home/user/gem-hunter/.open-next/assets
Total Upload: 6631.44 KiB / gzip: 1372.29 KiB
```

`dry-run --outdir` で吐き出された実バンドル `worker.js`（6.79MB raw）を直接 `gzip -c | wc -c` した結果 **1,405,428 B ≈ 1.34MB**。3MB上限に対し **現状で約45%消費、残headroom約1.66MB**。

⚠️ **副次的な発見（本タスクのスコープ外だが記録）**: `cloudflare-infrastructure.md` §5.3 が指定する計測コマンド `gzip -c .open-next/worker.js | wc -c` は、動的import前の router stub のみを測る（実測746B）。実際にデプロイされる本体（`handler.mjs` 込み・1.34MB gzip）を捕捉できておらず、**この計測手順は現状の3MB判定に対して使い物にならない過小評価になっている**。`npx wrangler deploy --dry-run` の `Total Upload ... / gzip:` 行、または `dry-run --outdir` してから対象ファイルを直接gzipする方法への修正が必要。README書式化とは独立の既存ドキュメント不備のため、自分では変更せず別Issue化を推奨（担当外のためここでは提起のみ）。

### 3. `@tailwindcss/typography` 導入時のCSS増分見積もり（npm installはしていない。`npm view` によるメタデータ照会と、npmレジストリからのtarball直接ダウンロード＋展開のみ）

- `npm view @tailwindcss/typography` → v0.5.20、`peerDependencies.tailwindcss: ">=3.0.0 || >=4.0.0 || insiders"`。プロジェクトは `tailwindcss: "^4"` + `@tailwindcss/postcss` のCSS-first構成（`app/globals.css` に `@import "tailwindcss"` 方式）。typography v0.5.20のREADMEはv4向けに `@plugin "@tailwindcss/typography";` を `globals.css` へ追記する方式を明記しており、現行の設定スタイル（`@import "tw-animate-css"` 等）と整合する。
- パッケージ本体を展開すると `src/styles.js`（prose全バリエーションのCSS-in-JS定義）が45,863B。ただしTailwind v4はJITで **実際にHTML中で使用されたクラスだけ** を最終CSSに生成する。README描画では想定使用クラスは `prose`・サイズ修飾（例 `prose-sm`）・`dark:prose-invert` 程度に限られる見込みで、45.9KB全体が出力に載ることはない。
- **見積もり**（実測ではない）: 使用クラスを絞った場合、追加CSSは raw で数KB〜十数KB、gzipで1〜3KB程度。現状の全体CSS（gzip 8.2KB）に対して相対的に小さく、静的アセット総量（928KB）から見ても無視できる増分。
- **実測が必要な理由**: JITの生成結果はマークアップに依存するため、上記は一次情報（npmメタデータ・パッケージソース）からの合理的な見積もりであり、`npm install` して実ビルドしないと確定しない。導入を決めた回のPRで `gzip -c .open-next/assets/_next/static/chunks/*.css | wc -c` の前後比較を記録することを推奨。

### 4. `limits.cpu_ms: 50` への影響

- `wrangler.jsonc` コメント: 「Free では意味を持たないが、Paid へ上げた瞬間に denial-of-wallet 対策として効く」。CSSはNext.jsビルド時に静的ファイルとして書き出され、リクエスト時にWorkerが実行するのはHTML生成（Reactレンダリング）とサニタイズ（`readme-html.ts`）のみ。CSS配信自体はWorkers Static AssetsがWorker実行を経由せず直接返す設計（`INF-10`: 「リクエストは無料・無制限」）。
- したがって **仮説は支持される**: ①②③のどの方式でもCSS自体はcpu_ms消費に寄与しない。唯一CPU時間に乗るのは③（サニタイズ時にユーティリティクラス注入）で `readme-html.ts` の変換パスにクラス文字列の付与処理が追加される点だが、既存のタグ/属性フィルタ処理（cheerio等ベースの1パス変換）に対する追加コストは軽微（文字列結合レベル）と見積もる。cpu_ms観点では①②③に有意差はない。

### 5. 30,000文字上限のレンダ負荷（`src/ui/readme-html.ts` L23）

- 切り詰め上限は「約30,000文字（表示上限の暫定値）」とコメントあり。サニタイズ後のHTML文字列サイズも概ねこのオーダーに収まる。一般的なWebページのHTML転送量（数百KB〜MB）と比べて30KB程度は小さく、ブラウザのパース・レイアウトコストとして問題になる水準ではない。
- 書式を当てても許可タグ一覧（`ALLOWED_TAGS`: table/pre/code/img等含む）自体は変わらないため、DOMノード数は不変。**性能上の理由で上限を見直す必要はない**（上限の妥当性はUX/可読性の論点であり、パフォーマンスレンズからは現状維持で問題なしと判定）。

### 6. モバイル横溢れ対策（`src/ui/readme-section.tsx` L124-129 を確認）

現状:
```tsx
// 🟡 `@tailwindcss/typography` は未導入（新規依存の追加禁止・タスクスコープ外）のため
//    `prose` は使わない。見出し・段落・リストは既定のブラウザスタイルに委ねる。
<div
  className="mt-2 max-w-none space-y-3 text-sm leading-relaxed break-words"
  dangerouslySetInnerHTML={{ __html: sanitized.html }}
/>
```

`break-words`（= `overflow-wrap: break-word`）はテキストの折返しには効くが、**`<table>` や `<pre><code>` のようなブロック要素の横溢れは防げない**（`overflow-wrap` は連続する長い「単語」の途中改行を許可するだけで、tableの列幅・pre内の改行なしコードには無関係）。`ALLOWED_TAGS` に `table` / `pre` / `code` / `img` が含まれる（`readme-html.ts` L62-85）ため、幅の広い表・改行のない長いコード行が実際に流れてくるREADMEでは、現行実装だとページ全体が横スクロールする（モバイルUXの既知の不具合パターン）。

- **どの要素に `overflow-x: auto` を当てるべきか**: `table` 単体と `pre` 単体の **それぞれに** `overflow-x: auto; max-width: 100%; display: block`（またはtableを `<div class="overflow-x-auto">` でラップ）が必要。バッジ画像（`<img>` の連続）はインライン要素として自然に折り返すため追加対策は基本不要。裸URLの長いリンクテキストは `break-words` で概ねカバーされる。
- **①`@tailwindcss/typography` を選んだ場合**: proseの既定CSSは `pre` に `overflow-x: auto` を持つ（Tailwind Typographyの標準仕様）が、**`table` には横スクロールラッパーを付けない既知の制限がある**（v0.5.x系で継続している挙動）。①を採用しても table 対策は **別途** 必要になる＝①だけで横溢れ問題が解決するわけではない。
- **②自前スコープCSSを選んだ場合**: `pre`・`table` それぞれに直接ルールを書けるため、むしろシンプルに両方カバーできる。
- **③サニタイズ時にクラス注入を選んだ場合**: `readme-html.ts` の変換パスで `<table>` を `<div class="overflow-x-auto">…</div>` でラップする処理を足せば、CSSセレクタに頼らず構造的に解決できる（他方式より確実だが実装コストは増える）。

→ **性能レンズからの推奨**: 採用方式に関わらず、`table` と `pre` は明示的に `overflow-x: auto` の対象にすることを他レンズ（readme_render / readme_fidelity）に申し送りたい。CSSサイズへの影響はどの案でも数十バイト単位で無視できる。

### 7. `tools/run_lighthouse.mjs` の扱い（詳細ページ: `/ja/repos/octostub/octo-widgets`）

- L14-17のコメント: 「Accessibility = 100 は blocking ゲート、Performance は計測値の記録のみでブロックしない」。実装（L261-273）でも `categories.accessibility.score` のみで `hasGateFail` を判定し、`perfScore` はサマリー出力（`perf=NN`）に載るだけ。
- **個別audit（CLS: `cumulative-layout-shift` 等）はスクリプトが一切参照していない**。README は Suspense で非同期描画される設計（`readme-section.tsx` docコメント: 「README到着時にフォーカスは移動しない（ユーザー操作起因でない後追い描画のため）」）ため、書式適用後にコンテンツの実効高さが変わり、後追い描画によるレイアウトシフトが発生しうる。performance score には畳み込まれるがCIはブロックしない。
- **E2Eスタブ（`e2e/stub/server.mjs` L438）のREADME fixtureが単純すぎる**: `<article><h1>...<p>...<ul>...</ul></article>` のみで、**table・コードブロック・長いURL・バッジ画像を一切含まない**。このため、Lighthouse・E2Eのどちらも今回の横溢れ対策（§6）の回帰を検知できない。

**書式適用後に見るべき指標（推奨・自分では実装しない）**:
1. `result.report.audits['cumulative-layout-shift'].numericValue`（詳細ページ）を手動確認し、README非同期到着によるCLS悪化がないか
2. `tools/run_lighthouse.mjs` は perf非ゲートのままでよいが、**E2Eスタブ側のREADME fixtureに table・長いコードブロック・長いURL・バッジ画像行を追加** し、Playwright側で横スクロール発生（`scrollWidth > clientWidth`）の有無を検証するテストケースを追加することを推奨（担当は readme_render / rev_tests 想定）
3. 静的アセット総量の前後比較（`.open-next/assets` の du -sh）をPR記録に残す

---

## 反対されうる点

- **「見積もり」の精度**: §3のCSS増分見積もりは `npm install` していない一次情報（パッケージメタデータ・ソース展開）からの推定であり、実際にJITでビルドしないと確定しない。導入PRでの実測比較を必須にすべき、という反論はもっとも。
- **cloudflare-infrastructure.md §5.3の計測手順の不備（§2の副次的発見）は、本タスクのスコープ（README書式）と無関係** という指摘はありうる。ただし「3MB上限に対する現在の消費率」を正しく報告するために実測方法を修正した経緯であり、他の参加者が③案などでバンドルサイズを判断材料にする場合に誤った基準を使わないよう申し送りが必要と判断し記載した。
- **table横溢れの「①でも別途対策が必要」という主張** は、Tailwind Typographyの具体的バージョン挙動に依存する。v0.5.20時点のsrc/styles.js中身までは検証したが、実際にレンダリングして確認したわけではない（npm installしていないため）。readme_render/readme_fidelityレンズでの実装時に、最終的に採用したバージョンで実挙動を確認してほしい。
- **cpu_ms影響ゼロという結論** は「CSSファイル配信」に限った話であり、③案（サニタイズ時のクラス注入）が複雑な変換ロジック（正規表現多用等）になった場合はサニタイズ全体のCPU時間が増える可能性がある。今回は「軽微」という定性評価に留まり、実測（`npx wrangler tail --format json` でのcpuTime計測）はしていない。

## ラウンド 2

### `tailwind_v4` — 反論
<sub>2026-08-21T18:08:10+09:00</sub>

## 対 `a11y_theme`: 反論 + 部分譲歩

**部分譲歩（あなたの数え方は過小評価だった）**: `a11y_theme` が挙げた上書き対象リスト（13 項目）は正確ではない。Context7 一次情報（`_autodocs/types.md`・`_autodocs/README.md`）で確認した **`--tw-prose-*` の完全な一覧は 18 項目**（`body / headings / lead / links / bold / counters / bullets / hr / quotes / quote-borders / captions / kbd / kbd-shadows / code / pre-code / pre-bg / th-borders / td-borders`）で、あなたのリストは `lead` `kbd` `kbd-shadows` `pre-code` `pre-bg` の 5 項目が抜けていた。公式ドキュメントも明記: *"The plugin utilizes 36 CSS custom properties, with 18 for light mode and 18 for dark mode."* — つまり `dark:prose-invert` を使う設計なら **正確には 18 + 18 = 36 項目** の上書きが要り、あなたの懸念（上書き漏れリスク）は **むしろ過小評価だった** という点は認める。

**しかし反論: `dark:prose-invert` 自体を使わなければ、上書きは 18 項目で済み、しかも「漏れ」が構造的に発生しなくなる。**

Typography プラグインの invert 機構は「`--tw-prose-invert-*` という **別の変数セット** を定義しておき、`prose-invert` クラスが `--tw-prose-body: var(--tw-prose-invert-body)` のように **変数の参照先を丸ごと差し替える**」仕組み（Context7 確認: `configuration.md` の `Add Custom Color Theme` サンプルが `--tw-prose-invert-*` を独立した色値の並びとして定義している）。

一方、本プロジェクトのセマンティックトークン（`--color-fg` 等）は **すでに `:root` と `.dark` の両方で異なる値を持つ**（`app/globals.css:71-111` / `113-148`）。つまり:

```css
/* app/globals.css へ追記する場合の案（18 項目・invert セットは書かない） */
@layer base {
  .prose {
    --tw-prose-body: var(--color-fg);
    --tw-prose-headings: var(--color-fg);
    --tw-prose-lead: var(--color-fg-muted);
    --tw-prose-links: var(--color-accent);
    --tw-prose-bold: var(--color-fg);
    --tw-prose-counters: var(--color-fg-muted);
    --tw-prose-bullets: var(--color-border);
    --tw-prose-hr: var(--color-border);
    --tw-prose-quotes: var(--color-fg);
    --tw-prose-quote-borders: var(--color-border);
    --tw-prose-captions: var(--color-fg-muted);
    --tw-prose-kbd: var(--color-fg);
    --tw-prose-kbd-shadows: transparent; /* 使わないなら無害な値でよい */
    --tw-prose-code: var(--color-fg);
    --tw-prose-pre-code: var(--color-fg);
    --tw-prose-pre-bg: var(--color-bg-subtle);
    --tw-prose-th-borders: var(--color-border);
    --tw-prose-td-borders: var(--color-border);
  }
}
```

`--color-fg` は `:root` で `oklch(0.145 0 0)`・`.dark` で `oklch(0.985 0 0)` と **すでに自己反転する**（`app/globals.css:73` / `:115`）ので、`.dark` 祖先が付いた瞬間に `--tw-prose-headings` の **解決値** も自動で切り替わる。`dark:prose-invert` クラスも `--tw-prose-invert-*` の 18 項目も **一切定義・適用不要**。→ **実質の上書きコストは 18 項目（うち色トークンの参照先はわずか 5 種: `fg` / `fg-muted` / `accent` / `border` / `bg-subtle`）に減り、ダーク側の書き漏れという失敗モードが構造的に消える**（「1 項目でも上書き漏れがあれば」の指摘（`a11y_theme` R1 §1）自体が、invert セットを使わない設計では発生しなくなる）。

**「全項目上書きなら自前 CSS と手間が変わらないのでは」への回答**: 変わる。上記の 18 行はすべて **色のみ**。`prose` を使う場合、見出し・段落・リスト・コードブロック・表の **margin / padding / line-height / list-style / border-radius / フォントサイズの相対スケール**（`prose-sm` 等）はプラグインが提供したまま **無償で得られる**。②（自前スコープ CSS）ではこれらも全部手書きする必要があり、色だけの 18 行より明らかに実装量が多い。したがって「①でも色だけは全部書く」を実施しても、①の総実装量は②より少ないままである。

**v4 流儀の置き場所**: Context7 で確認した公式パターンは 2 通り。

1. **デフォルトクラス（`prose`）自体の変数を直接上書き**（上記コードのように `@layer base` 内、または `app/globals.css` のトップレベルで `.prose { --tw-prose-*: ...; }`）——今回は `prose` を README 1 箇所でしか使わない前提なので最も単純。
2. **`@utility` ディレクティブで独自の名前付きテーマを作る**（公式 README 記載のパターン）:
   ```css
   @utility prose-gemhunter {
     --tw-prose-body: var(--color-fg);
     /* ...18項目... */
   }
   ```
   `class="prose prose-gemhunter"` のように既定の `prose-slate` 等と同列の **選択可能なバリアント** として追加する方式。将来 README 以外にも `prose` を使う画面が増え、配色を選び分けたい場合はこちらが適切。

**推奨**: 現時点では 1（`.prose` 直接上書き）でよい。README 以外に prose の適用箇所がなく、選択式にする理由がない（YAGNI）。将来複数用途が出たら 2 へ移行すればよく、移行コストは低い（`@utility` 化は変数定義をコピーするだけ）。

→ **結論として ① は撤回しない** が、`a11y_theme` の「未カスタマイズの `prose` には反対」という主張には **全面同意** する。上記の 18 項目上書きを ① 採用の **必須要件** として自分の推奨に組み込む（R1 の推奨に条件を追加: 「`--tw-prose-*` を §1 のセマンティックトークンへ全項目マッピングした上での ① 採用」）。この条件下であれば、`a11y_theme` が懸念する新規カラースケールの混入・`check_contrast.py` のゲート抜け（§3）は発生しない——README のコントラストは既存 10 トークンのコントラスト実測にただ乗りする（`a11y_theme` R1 §3 の結論と一致）。

## 対 `readme_fidelity`: 診断は完全に一致

`readme_fidelity` の「主因は許可タグ不足ではなく、コンテナに typography CSS が当たっていないこと」という結論は自分の診断（R1 §6: Preflight が見出し・リストの既定装飾を打ち消し、`readme-section.tsx` 側が装飾を一切足していない）と完全に一致する。実機確認（`bcaudan/jasmine-spec-reporter` の抽出 HTML）でコンテナクラスが `prose` を含まず、`h1→h3` 等のシフトは正しく機能しているという事実も、自分が R1 で参照した `readme-html.ts:27-34` の静的読解と矛盾しない。異論なし。

## 対 `perf_bundle`: 矛盾なし・1 点補強

CSS が Workers Static Assets 経由で 3MB ゲート対象外という判定、typography 導入増分を gzip 1〜3KB 程度と見積もる点はいずれも自分の理解と矛盾しない。むしろ **§1 の反論（`dark:prose-invert` を使わない設計）を採用すると、生成される CSS はさらに小さくなる**——JIT が拾う使用クラスから `prose-invert` 系のセレクタ・invert 用の宣言ブロックが丸ごと消えるため、`perf_bundle` の見積もり（1〜3KB）は **上限側の見積もりとして妥当、実際はそれよりやや小さくなる** と予想する（実測は npm install 後でないと確定しない点は同意）。

`<table>` の横溢れについて: `perf_bundle` が `src/styles.js`（v0.5.20 のソース）を直接展開して確認したという一次情報は、自分が Context7 のドキュメント検索で `pre`/`table` の `overflow-x` 挙動を明示的に確認できなかった点より一次性が高い。**自分ではこの挙動を独立に確認できていない（未確認）**——Context7 のドキュメント検索では「`prose-table:border-collapse` のような列指定修飾子」は見つかったが、既定で `overflow-x: auto` が `table` に付くかどうかの明示的な記述は見当たらなかった。`perf_bundle` の実測（ソース直接確認）を採用し、**`table` は typography プラグイン採用の有無に関わらず、`.readme-content table` 相当のスコープで別途 `overflow-x: auto` を明示追加する必要がある** という結論に同意する。`pre` については典型的に `overflow-x: auto` が既定で付く（v3 以来の一般的な仕様と自分の記憶にはあるが、これも Context7 で明示確認できていないため **未確認** と明記し、実装時にビルド後の CSS を目視確認することを推奨する）。

## まとめ（自分の立場のアップデート）

- 推奨は ① `@tailwindcss/typography` のまま変更しないが、**必須条件を追加**: `--tw-prose-*` 18 項目をセマンティックトークンへ全マッピングし、`dark:prose-invert` は使わない（`--tw-prose-invert-*` 定義も不要）。この設計変更で `a11y_theme` の懸念（新規色混入・上書き漏れ・コントラストゲート抜け）を構造的に解消できる。
- `table` の横溢れは①採用でも別途 CSS（`overflow-x: auto`）が必須（`perf_bundle` に同意・自分では未検証のため一次性は `perf_bundle` 側が上）。
- `readme_fidelity` の根本原因診断（CSS 欠落、タグ欠落ではない）に全面同意。

### `readme_fidelity` — 反論
<sub>2026-08-21T18:08:36+09:00</sub>

# round 2: rebuttal / concession（readme_fidelity）

## Q1. `<details>`/タスクリスト/シンタックスハイライト/絵文字/バッジ/アラート記法 — 必須 vs スコープ外の線引き

**結論: 全て本 PR のスコープ外にすべき。** 理由は「飼い主のスクリーンショットに写っている要素を優先する」という coordinator の指示に忠実に従うと、これらは **1 つもスクリーンショットに写っていない**（症状は見出し・リスト・段落・インラインコードが同じ大きさで並ぶことだけ。`bcaudan/jasmine-spec-reporter` の実出力にも `<details>`/タスクリスト/GitHub アラートは出現しない）。round1 で私が列挙した「落ちている要素」は静的コード突き合わせによる **網羅性チェック** であって、「今回直すべきもの」ではない——この 2 つを混同すると、tailwind_v4 が §7 で示した③案（許可リスト拡張）に不必要にスコープが広がる。

優先度を明示すると:

| 分類 | 要素 | 対応方針 |
|---|---|---|
| **必須（本 PR）** | 見出し階層・リストのマーカー/インデント・段落余白・コードブロック/インラインコードの区別・表の罫線・引用の視覚化・画像溢れ防止 | すべて **CSS のみ**（①/②方式）で解決する。許可リスト（`ALLOWED_TAGS`/`ALLOWED_ATTRIBUTES`）は一切変更不要 |
| **スコープ外（別 Issue）** | `<details>`/`<summary>`・タスクリストのチェックボックス・`pl-*` シンタックスハイライト・`markdown-alert`・`g-emoji`・`octicon` | 許可リストの拡張が要る＝サニタイズの脅威モデル変更を伴う。今回の飼い主フィードバックの再現手順（スクリーンショット）では検証しようがなく、`SD-1`（動作確認できる状態で終わる）の対象にできない |

`tailwind_v4` 案①・`a11y_theme` 案②のどちらを採っても、この表の「必須」列は full に満たせる（③は不要）という点で両者は一致しており、私の結論もこれに合流する。

## Q2. バッジ画像の実出力確認 — `a11y_theme` §5 への回答

`a11y_theme` は §5 で「バッジ画像は通常小さいので問題にならないが `break-words`/`max-w-none` の折返しに頼っている」と述べ、`display:inline-block; margin:0.125rem` の軽微調整を「必須ではない」として提案している。実出力を確認した:

```html
<img src="https://camo.githubusercontent.com/.../68747470...(shields相当)" alt="Dependabot" />
<img src="https://camo.githubusercontent.com/.../68747470...(travis)" alt="Build Status" />
<img src="https://camo.githubusercontent.com/.../68747470...(codecov)" alt="codecov" />
<img src="https://raw.githubusercontent.com/bcaudan/jasmine-spec-reporter/HEAD/screenshot.gif" alt="" />
```

**確認できたこと**: バッジ 3 枚・スクリーンショット GIF 1 枚のいずれも **`width`/`height` 属性が一切無い**（GitHub の README HTML 自体が付けていない。`readme-html.ts:191-196` は width/height を透過するだけで存在しないものは作らない）。これは 2 つの含意を持つ:

1. **バッジは実害が薄い**: バッジ画像（shields.io/travis/codecov 系 SVG）は元 SVG 自体の intrinsic size が小さい（概ね高さ 20px 前後）ため、`max-width` を当てなくても幅が溢れる心配はほぼ無い。`a11y_theme` の懸念（「バッジが原寸で並ぶ」）は誤りではないが、実測ではこの 1 サンプルにおいて破綻していない。**バッジ専用の高さ制限は過剰実装**（round1 の「過剰再現の弊害」で述べた通り）——追加コストに見合う実害が確認できないため不要と判断する。
2. **本当のリスクは `screenshot.gif` 側**: 幅・高さ指定の無い実コンテンツ画像（スクリーンショット・GIF）は、原寸が大きければ確実にコンテナを突破する。`img { max-width: 100%; height: auto }` を README スコープに当てる（`a11y_theme` §5 の提案通り）だけで、バッジ・スクリーンショットの両方に十分対応できる。**追加対策（バッジの高さ制限等）は不要**、と `a11y_theme` の懸念に対して一部反論する。

結論: `img { max-width:100%; height:auto }` のみで足りる。`display:inline-block; margin` の軽微調整（`a11y_theme` も「必須ではない」と明記済み）は取り入れてよいが優先度は最下位。

## Q3. 許可リスト拡張の安全性の線引き

Q1 の結論により今回のスコープではないが、`class` 属性を許可せずに `<details>`/タスクリストを出せるかという問いには明確に答えておく（次 Issue への引き継ぎ事項として）:

- **`<details>`/`<summary>` は `class` 不要で追加できる**: ネイティブ HTML5 要素で、開閉の見た目（三角マーカー）はブラウザ既定の `summary::marker` に依存し、スクリプトも実行しない。危険な属性は `open`（真偽値、XSS 経路にならない）のみで、`readme-html.ts` の `ALLOWED_ATTRIBUTES` に `details: ['open']` を足すだけで安全に成立する。
- **`<input type="checkbox" disabled>` は個別の `transformTags` ハンドラが必須で、単純な許可リスト追加は危険**。`readme-html.ts:159-198` の `a`/`img` と同じパターン（値を検証してから最小限の属性だけを再構築する）を踏襲し、`type` が厳密に `"checkbox"` の場合のみ許可し、**`disabled` を常に強制付与**（GitHub 由来の `disabled` 有無を信用しない）、`name`/`value`/`id`/`checked` 以外の属性は無条件で落とす、という実装にする。危険性そのものは低い（`<form>` は禁止タグのままなので送信経路が無く、XSS 直結でもない）が、`disabled` を強制しないと「見た目はチェックボックスだが実は操作可能」という誤解を招く UI になりうる——ここが唯一のリスク面。
- **`class` 属性そのものは div/span に開放しない**（`a11y_theme` §1/§3 の立場を全面的に支持）。`class` を許可すると、第三者コンテンツが自サイトの実クラス名（例 `sr-only`, `focus-visible:ring-*` 相当のユーティリティ名, shadcn コンポーネントクラス）を騙って UI redress（視覚的なすり替え）を起こせる余地が生まれ、かつ `perf_bundle`/`a11y_theme` が指摘した「`check_contrast.py` の検査網をすり抜ける新規配色の混入経路」にもなる。`tailwind_v4` §7 の③案が非推奨とされたのと同じ理由で、`class` 開放は今回もスコープ外に固定する。

## Q4. 見出し +2 降格 と `a11y_theme` の「18px（README セクション h2）を超えない」制約 — 衝突しない

**衝突しない。`a11y_theme` §4 の 16px/14px + フォントウェイト案を support する。** 書式の再現度レンズで求めているのは「README 内の最上位見出しが巨大に見えること」ではなく round1 で定義した最低ライン——**「見出しの階層が視覚的に分かる（段階的にサイズ/太さが小さくなる）」**——であり、絶対サイズが 18px を超える必要は無い。根拠を 2 点補足する:

1. **GitHub 自身も README の `h1` をページ全体のクロムに対して巨大には表示していない**（GitHub のリポジトリページでもファイルツリー・サイドバー等と同居する形で README 本文は相対的に控えめなスケール）。「大きく見えてほしい」という私の round1 の期待値自体を、`a11y_theme` の実測（`ThemeProvider` 未配線・§2.3 の 5 段階制約）を踏まえて **18px 以下の範囲に収める** ことに合意修正する。
2. **視覚サイズとセマンティクスは分離してよい**。`+2` シフトはあくまで DOM 上のタグ名（アクセシビリティツリー上の見出しレベル）の話であり、スクリーンリーダー利用者にとっての「見出しジャンプ」機能は `h3`〜`h6` のタグ名がある時点で完全に再現されている（`readme-html.ts:27-34` の id 保持も含め）。晴眼者向けの視覚サイズを 14px/16px に抑えても、この構造的な書式再現は損なわれない——**「書式が反映されている」の実質は視覚サイズの絶対値ではなく、階層の知覚可能性** である。

一点だけ `a11y_theme` §4 の具体案に補強を提案する: 14px/500(medium) の `h6` は本文（`text-sm`＝14px・既定 400/normal 想定）と **同じフォントサイズ** のため、weight 差（500 vs 400）だけで階層を伝える設計になっている。round1 で定義した最低ライン「段階的に小さくなる」を厳密に満たすには、**フォントサイズが同じ隣接段（h6 と本文）の間には `margin-top` による視覚的な区切り（余白）を必須にする** ことを追加で求めたい——これはテーブルの数値そのものへの反論ではなく、実装時に見出し前後の余白（`space-y-3` だけで足りるか）を実ブラウザで確認する項目として `impl_readme` 側に引き継ぐ。

## 譲歩（concession）まとめ

- `a11y_theme` §1/§2/§3（新規 raw 色を作らず既存 10 トークンのみを使う・`prose` 採用時は `--tw-prose-*` 全項目上書きが必須）に **全面同意**。round1 では触れていなかった論点で、私の「過剰再現の弊害」節（GitHub 独自の視覚言語との衝突）と方向性が一致する
- `a11y_theme` §4 の 16px/14px + weight テーブルに **同意**（Q4 参照）。round1 で「最上位見出しは大きく見えてほしい」という含意を書いたわけではないが、念のため明記して解消しておく
- `tailwind_v4` §7 の③案（`transformTags` でのクラス直接注入）が非推奨である点に **同意**。round1 で私はタスクリスト等の許可リスト拡張を「検討対象」として列挙したが、Q1/Q3 の整理を経て「許可リストを広げるとしても `class` 開放ではなく個別属性のホワイトリスト強化に限定すべき」という点で `a11y_theme`/`tailwind_v4` の安全側の結論と揃えた

### `a11y_theme` — 反論
<sub>2026-08-21T18:09:24+09:00</sub>

# Round 2: rebuttal / concession（a11y_theme）

## 結論（round1 からの改訂）

**② への選好は維持するが、根拠を「CSS 量」から「安全側の失敗モード」へ差し替える。** round1 の「②の方が保守しやすい（CSS 量が少ない）」は自己検証の結果 **不正確だった** ので撤回する（§1 で自己批判）。また `img` の overflow 対策は **Preflight が既に処理済み** であることが判明したため、round1 §5 の該当記述も訂正する（§4）。それでも②を推す理由は残るが、①も「`--tw-prose-*` 全項目の var() エイリアス化」を PR 必須要件として明文化するなら **許容できる**、という条件付きの立場に後退する。

---

## 1. `tailwind_v4` への回答: 自前 CSS の実分量を見積もり、自己批判する

`readme_fidelity` の R1「書式が反映されていると言える最低ライン」6 項目（見出し階層・リストマーカー/インデント・コードブロック区別・表罫線・引用・画像溢れ防止）と、`perf_bundle` の R1 §6（table/pre の overflow）を突き合わせ、②で実際に書く必要があるセレクタを数えた。

| 対象 | ルール数（目安） | 備考 |
|---|---|---|
| 見出し `h3`〜`h6` サイズ/太さ | 4 | §4（round1）の size/weight テーブルどおり |
| リスト `ul`/`ol`/`li`・ネスト字下げ | 3〜4 | `ul ul` 等ネスト分岐を含む |
| `pre`（背景・padding・overflow-x） | 1 | |
| インラインコード `code`（`pre code` は除外） | 2 | `:not(pre code)` 分岐が要る |
| `table`/`th`/`td`/`thead`（罫線・padding・overflow ラッパー） | 3〜4 | |
| `blockquote`（左罫線・padding） | 1 | |
| `hr` | 1 | |
| 本文リンク色 | 1 | |
| `img`（余白調整のみ。overflow は不要・§4 訂正） | 0〜1 | |

**合計 16〜19 ルール**。一方 ①（`--tw-prose-*` の完全上書き）は `tailwind_v4` R1 の一次情報（Context7）に列挙された変数だけで body / headings / lead / links / bold / counters / bullets / hr / quotes / quote-borders / captions / kbd / kbd-shadows / code / pre-code / pre-bg / th-borders / td-borders の **約 18 変数**。**さらに `--tw-prose-invert-*` を素朴に全部書けば倍** になるが、この二重化は避けられる（§2 で後述）ため実質 **約 18**。

→ **round1 の「②の方が保守コストが低い」は数の上では正しくなかった。両案とも 16〜19 個規模で、ほぼ互角**。ここは明確に自己批判し撤回する。

**それでも②を選ぶ理由（量ではなく失敗モードの安全性）**:

- ②はプレーンな CSS セレクタなので、書き忘れた要素は Preflight のリセット（無地・無階層）に **目に見えて** フォールバックする。`readme_fidelity` の 6 項目チェックリストにそのまま引っかかるので、レビューで「未達」に気づきやすい。
- ①は書き忘れた `--tw-prose-*` 変数が **プラグインの既定値（Tailwind の gray/slate スケールへのハードコード）** にフォールバックする。これは見た目としては「それらしく整って見える」ため、レビューで見逃されやすい——しかもこの既定値は §3 で述べる理由により **コントラストゲートの外側** にある。「壊れ方が地味で危険」な失敗モードを②は避けられる。
- ②は `app/globals.css` 1 ファイル内で完結し、実際に効くセレクタの全体像がそのままそこに書いてある。①はプラグイン本体（`node_modules` 内・ビルド時生成）の内部セレクタ構造（`.prose :where(h3):not(:where([class~=not-prose] *))` 等の高詳細度チェーン）を前提に、その上に自分たちの上書きを重ねる形になり、「最終的に何が効いているか」を把握するのに一段階多く間接参照が要る。

以上より、**量では互角、失敗モードの安全性では②がわずかに有利** という、より正確な結論に改める。

---

## 2. `check_contrast.py` の検査範囲を再検証: ①でもゲートに載せる方法は本当に無いのか

再度実読して確認した事実（`tools/check_contrast.py` L138-169）:

- `extract_block()` は `app/globals.css` から **厳密に `:root { ... }` と `.dark { ... }` という 2 ブロックだけ** を正規表現 `re.escape(selector) + r"\s*\{"` で抽出する。`@theme inline` ブロックも `.readme-content` のようなクラススコープも見ていない。
- `parse_declarations()` はそのブロック内の `--([\w-]+)\s*:\s*([^;]+);` を **名前を問わず全部** 辞書に入れる。つまり **変数名がハードコードされているわけではなく、`:root`/`.dark` ブロックに書かれてさえいれば、どんな `--xxx` も値として拾われる**。
- ただし後段のペア判定（本ラウンドでは未提示だが L13-24 のコメントで確認済み）は **固定 9 名（background / muted / foreground / muted-foreground / border / accent / accent-foreground / destructive / destructive-foreground）に対する固定 11 ペア** をコードで直接書いている。新しい変数名（例 `--tw-prose-body`）を `:root` に置いても、**その変数自体を新しいペアとして検査する処理は無い**。

**訂正**: round1 の私の主張「①を採ると新規色がゲートの外に出る」は **条件付きでしか正しくない**。もし `--tw-prose-body: var(--color-fg);` のように **常に既存トークンへの `var()` 参照だけ** で埋めるなら、`--tw-prose-body` という変数名自体は検査対象に追加されないが、**値の実体（`--foreground` の raw 値）は既に `check_contrast.py` の `fg vs bg` ペアで検査済み** なので、事実上「ゲートに間接的に乗っている」と言える。①でも②でも、**新規の literal 色（`oklch(...)` や `#hex` の直書き）さえ増やさなければ、check_contrast.py を拡張する必要は無い**——これは①②のどちらでも同じ規律（「既存 10 トークンの `var()` 参照のみ」）を守れるかどうかの問題であり、方式選択の差ではなかった。round1 §3・§6 の「①だと `check_contrast.py` の拡張が要る」という書き方は撤回し、正しくは「**①でも②でも、この規律を破ったときだけ** 拡張が要る」に訂正する。

ただし §1 で述べた失敗モードの非対称性（①は規律違反が既定値へのサイレントフォールバックとして起きやすい）は残るため、①を採るなら **PR チェックリストに「`--tw-prose-*` / `--tw-prose-invert-*` の grep で literal 色（`#`/`oklch(`/`rgb(` を含み `var(` を含まない行）がゼロであること」を機械検査として追加する** ことを条件に付けたい（`check_contrast.py` 自体を拡張しなくても、別の軽量スクリプト・grep で足りる）。

---

## 3. `perf_bundle` を踏まえて結論は変わるか

`perf_bundle` の「CSS は Static Assets 配信で 3MB 上限の対象外・増分は gzip 1〜3KB」は妥当な実測（`wrangler.jsonc` の assets binding・`dry-run` 実測値）で、**サイズは判断材料から外してよいと同意する**。

残る軸は「トークン体系の一貫性」と「保守性」の 2 つになるが、§1・§2 の自己検証を経て、この 2 軸での差は round1 で書いたほど大きくない（保守コストはほぼ互角、一貫性は規律を守れば①②とも同等に保てる）。**それでも結論（②をわずかに優先）は変わらないが、確信度は下がった**。差が残るのは:

- 依存追加そのもののコスト（`@tailwindcss/typography` の将来のメジャーアップデート追従・Tailwind v4 本体との destructive change 追従——`docs/rules/claude-code-spec-sync.md` 相当の継続監視対象が 1 つ増える）。②は依存ゼロなのでこの継続コストが無い。
- §1 で述べた失敗モードの非対称性。

**したがって、①を選ぶこと自体には反対しないが、選ぶなら §2 の機械検査（`var(` を含まない `--tw-prose-*` 宣言の grep）を実装 PR に含めることを条件として申し送りたい。** 純粋な a11y/テーマ整合の観点だけで見れば②の方が「そのままで安全」だが、依存追従コストを許容し上記の機械検査を追加するなら①でも同等の安全性を達成できる、という結論に改める。

---

## 4. 方式非依存の必須対策（round1 の訂正込みで再整理）

`tailwind_v4` の round1「未確認事項」（`layout.tsx` のテーマ切り替え実装）は、私が round1 で既に確認済み: **`next-themes` の `ThemeProvider` は未実装**（`app/[locale]/layout.tsx` に `ThemeProvider`/`attribute=` は grep 0 件）。`.dark` クラスの付け外し主体がまだ無い。これは①②どちらの方式にも影響する **共通の前提条件** として整理する。

| 対策 | 方式に依存するか | 内容（訂正版） |
|---|---|---|
| `img` の溢れ防止 | **不要（訂正）** | `node_modules/tailwindcss/preflight.css` L230-234 に **`img, video { max-width: 100%; height: auto; }` が既に存在** することを実機ファイルで確認した。round1 の私の主張（「`max-width:100%` を追加で必須にする」）は誤り。①②③のどれを選んでも、Preflight が既に効いている限り追加対応は不要。バッジ画像の間隔調整（`margin` 程度）だけが任意の改善余地として残る |
| `table` の横溢れ防止 | **必須（共通）** | `perf_bundle` R1 確認済み: typography プラグイン既定は `pre` には `overflow-x:auto` を持つが **`table` には持たない**。①②③のいずれでも `table`（または `<div class="overflow-x-auto">` ラッパー）に個別対応が要る |
| `pre` の横溢れ防止 | ①は既定で対応済み／②③は要実装 | ①なら追加不要（プラグイン既定）。②③なら明示的に `overflow-x:auto` が要る |
| README 見出しがセクション h2（18px）を超えない | **必須（共通）** | ①なら `prose-h3:` 等のユーティリティ修飾子、②なら直接セレクタ。実装場所が違うだけで、どちらも「4 段階を 16px/14px + weight で表現する」設計自体は同じ（round1 §4 のテーブルをそのまま両方式に適用可能） |
| next-themes 未配線への対応 | **共通の制約** | どちらの方式でも「`.dark` が将来 HTML へ付与された時に正しく追従する」ように、色は必ず `var(--color-*)` 経由（①なら `--tw-prose-*` 経由、②なら直接）にする。**`dark:prose-invert` のような `.dark` 依存の Tailwind バリアントクラスを使う場合、`ThemeProvider` 配線が別途完了するまで動作確認できない**（`SD-1` 「動作確認できる状態で終わる」への影響——README ダークテーマの目視確認は `next-themes` 配線 Issue の完了を待つ必要がある可能性がある。①③②いずれの方式のスプリントでも「配線待ち」と明記すべき） |

---

## 5. `ui-ux-guidelines.md` §2.5 案: 方式非依存に書き直す

round1 の草案は「新しい raw 色を追加しない」「`--tw-prose-*` を全項目エイリアスする」等、①寄りの文言が混在していたため、**方式が未確定でも成立する規定** に書き直す:

```markdown
### 2.5. README 本文のタイポグラフィと書式（Issue #334 拡張）

詳細ページの README セクション本文（`readme-section.tsx` の `dangerouslySetInnerHTML`）に
書式を当てる実装（採用方式は問わない）は、以下を満たす。

- 🔴 **新しい raw 色を追加しない**。すべての色指定は §2.1 の 10 セマンティックトークンへの
  `var(--color-*)` 参照のみで構成する（採用した実装手段の変数名がどうであれ、最終的な
  宣言値が既存トークンの参照になっていること）。
- 🔴 **`var(` を含まない色の直書きが無いことを機械検査する**（実装 PR に検査コマンドを含める。
  `tools/check_contrast.py` は `app/globals.css` の `:root`/`.dark` ブロックの固定 9 変数・
  11 ペアのみを検査するため、README 書式用に追加した色指定はこのゲートの対象外になりうる
  ——だからこそ「新規 literal 色を増やさない」という規律を機械で担保する）。
- README 本文の見出し（`readme-html.ts` の +2 シフト後の `h3`〜`h6`）は、セクション見出し
  「README」（`h2`・18px）を視覚的に上回らない。5 段階タイプスケール（§2.3）のうち
  16px / 14px の 2 段階とフォントウェイトの組み合わせで 4 段階を表現する。
- `table` は要素単体を `overflow-x: auto` のコンテナで囲み、ページ本体を横スクロールさせない
  （`NFR-15` / §3。画像は Tailwind Preflight が `max-width:100%; height:auto` を既定で
  提供するため追加対応不要）。
- ダークテーマは `.dark` 祖先での CSS 変数の値切り替えに乗せる（`--color-*` トークン自体が
  `:root`/`.dark` で異なる値を持つため、色指定を `var(--color-*)` 参照にしておけば追加の
  ダーク専用クラスは不要）。**現時点で `next-themes` の配線が未実装**であるため、実機での
  ダークテーマ目視確認はその配線完了後に行う。
```

`§9` への追加行も方式非依存の文言に修正:

```markdown
- [ ] §2.5 の README 書式が新規 raw 色を追加せず（機械検査済み）、既存トークンの参照のみで実装されている
```

---

## 反対されうる点

- 「§1 で “量は互角” と結論しつつ、依存追加コストと失敗モードの非対称性だけで②を推すのは弱い」という指摘はありうる。同意する——これは a11y レンズからの一意見であり、実装工数（`impl_readme`）やアーキ整合（`arch_domain`）の判断も重い材料になるため、最終決定は lead 裁定を仰ぐべき論点だと考える。
- §2 の「grep ベースの literal 色検査」は自分では実装しない前提の提案であり、実効性（false negative: `rgb(0 0 0)` のような非 `oklch` literal を見落とす等）を詰め切れていない。実装担当が別途精査してほしい。
- Preflight の `img { max-width:100% }` 確認は `node_modules/tailwindcss/preflight.css` の実ファイル読み取りによる一次情報だが、**このプロジェクトの `@import "tailwindcss"` が実際にこの Preflight を素通しで含んでいるか**（v4 のカスタム設定で一部除外されていないか）までは `app/globals.css` の import 文（L1-3）から間接的に確認したのみで、ビルド後の実 CSS ファイルまでは見ていない。`readme_render`/`perf_bundle` 側で実ビルド CSS の grep があれば確定できる。

### `perf_bundle` — 反論
<sub>2026-08-21T18:12:19+09:00</sub>

# perf_bundle R2: rebuttal / concession

## 結論（先出し）

- **Q1（3MB上限の対象外という判定）**: 再確認した。判定は変わらない。むしろ確度を上げる追加証拠が見つかった（`cloudflare-infrastructure.md` §5.3 の計測コマンド自体が実は不正確という副次的発見つき）。
- **Q2（CSS増分 1〜3KB gzip の見積もり）**: `styles.js` の行数と、本プロジェクトの実測CSS圧縮率（4.96倍）から再計算し、**a11y_theme の提案（`--tw-prose-*` 全項目上書き必須）を織り込むと raw 6〜12KB / gzip 1.5〜3KB 程度に上方修正** する。結論（3MB上限に無関係）は変わらない。
- **Q3（table/preのoverflow）**: **round1の記述を一部訂正する（concession）**。CSSの `overflow-x:auto` を `<table>` 要素自体に直接当てても効かない——CSS2.1の仕様上の既知の欠陥で、table box では `auto`/`scroll` は `visible` と同じ扱いになる。**`<table>`は実DOMラッパー`<div>`が必須**（CSS単体では解けない）。一方 `<pre>` は通常のブロックボックスなので `overflow-x:auto` を直接当てるだけで機能し、実際 `@tailwindcss/typography` 本体のソース（`styles.js`）にも `pre: { overflowX: 'auto' }` が入っていることをソースレベルで確認した。
- **Q4（E2Eフィクスチャ）**: 具体案を提示する。既存の `octostub/octo-widgets` を拡張せず、`readme-missing` と同じ命名パターンで専用フィクスチャリポジトリを追加することを提案。
- **Q5（30,000文字上限）**: **据え置きを推奨するが、無条件ではない**。Lighthouseの `dom-size` 監査のしきい値（警告 約800ノード／エラー 約1,400〜1,500ノード）に対し、実測シミュレーションで典型的な文章主体のREADMEは280〜550ノード程度で余裕があるが、**表（`<table>`）が密なREADMEは30,000文字ちょうどで最大1,748ノードに達し、Lighthouseのエラーしきい値を超えうる** ことを新たに定量化した。文字数一律の上限見直しよりも、Q4のフィクスチャ拡充で継続監視する方が筋が良いと判断する。

---

## Q1: CSS配信経路と3MB上限の再確認

再確認した根拠（round1と同じ実測値を再チェック、追加でファイルパスと行を明示）:

1. **`wrangler.jsonc`**（プロジェクトルート）: `"main": ".open-next/worker.js"`、`"assets": { "directory": ".open-next/assets", "binding": "ASSETS" }`。Worker本体とアセットが別ディレクトリ・別バインディングであることが設定ファイルレベルで明示されている。
2. **`.open-next/worker.js`**: 実ファイルを再読したが、`server-functions/default/handler.mjs` を `await import(...)` で動的取得する router のみで、CSSファイル名（`2zfgn5tn_e7wb.css`）はJS内の **文字列** として現れるだけで、CSS本体（セレクタ・宣言ブロック）は含まれない。
3. **`.open-next/assets/_next/static/chunks/2zfgn5tn_e7wb.css`** が実CSS本体（raw 40,585B / gzip 8,178B）— これが Workers Static Assets 側。
4. **`docs/03_design/infrastructure/cloudflare-infrastructure.md` L65**「Workers Static Assets（JS/CSS/フォント・**無料・無制限**）」、L286「Worker バンドル: 3MB（圧縮後）」— ドキュメント上も両者は明確に別カテゴリ。
5. `npx wrangler deploy --dry-run --outdir` で実バンドルを吐き出し確認: **`Total Upload: 6631.44 KiB / gzip: 1372.29 KiB`**。dry-run が生成した実 `worker.js`（6.79MB raw）を直接 `gzip -c | wc -c` した値は **1,405,428 B（≈1.34MB）** で、wranglerの申告値と一致。3MB上限に対し **約45%消費、残headroom約1.66MB**。

→ **判定は変わらない。CSSはWorkers Static Assets側で配信され、Worker本体の3MB gzip上限の対象外**。①②③のどの方式でも、CSS増分自体がこの上限を圧迫することはない。

**副次的発見の再掲（確度確認済み）**: `cloudflare-infrastructure.md` §5.3 が指定する計測コマンド `gzip -c .open-next/worker.js | wc -c` は router stub のみを測り（実測746B）、動的import経由でバンドルされる本体（1.34MB gzip）を捕捉できていない。これは他参加者が「3MB上限に対する余裕」を判断材料にする場合に誤った基準（746Bという実質ゼロの数字）を使ってしまうリスクがあるため、**方式選択の場では `npx wrangler deploy --dry-run` の `Total Upload ... gzip:` 行を正とする** よう申し送る。ドキュメント修正自体はスコープ外なので自分では変更しない。

---

## Q2: CSS増分の実測に近づける再計算

**方法**: (a) 現行プロジェクトCSSの実測圧縮率を基準にする、(b) `@tailwindcss/typography` パッケージソース（`npm view` でメタデータ取得 + tarball展開のみ、`npm install` はしていない）の行数からJIT後の出力規模を見積もる。

### (a) 現行CSSの圧縮率（実測）

```
raw:  40,585 B
gzip:  8,178 B
比率: 4.96倍
```

Tailwind生成CSSは同じプロパティ・似た構造のセレクタが反復するため高圧縮率になる。typography系CSSも同様の性質（`font-size`/`margin`/`color: var(--tw-prose-*)` の反復）を持つため、この比率を流用する。

### (b) 出力規模の見積もり（`styles.js` 実測）

```
sm ブロック（1サイズ分のCSS-in-JS定義）: 30〜234行（約205行）
base ブロック（既定サイズ）           : 235〜439行（約205行）
invert ブロック（ダーク配色の変数上書きのみ）: 1385〜1409行（約24行）
DEFAULT（色・overflow等・サイズ非依存の共通部）: 1410〜1641行（約231行）
```

tailwind_v4 の提案（`prose prose-sm dark:prose-invert` + `prose-h3:` 等の個別修飾子）を採用した場合、JITが実際に生成するのは概ね「DEFAULT（共通部）+ sm（1サイズ分）+ invertの変数上書き + 使用した `prose-h3:` 等の個別セレクタ数個」で、234+205+24行程度がベース（合計約460行相当）。1 JSプロパティ→CSS宣言1行の対応と仮定し、1行あたり平均25〜35バイト（セレクタ再利用があるため実際はもう少し圧縮される）とすると **raw 6〜10KB**。さらに a11y_theme の提案（`--tw-prose-*` 全項目 + `--tw-prose-invert-*` 全項目を `app/globals.css` 側でトークンへエイリアス、計26個程度のカスタムプロパティ宣言）を追加で載せると **raw 合計 6〜12KB** 程度と見積もる（上方修正: round1の見積もりでは a11y_theme の上書き必須リストを未考慮だった）。

**gzip換算**: (a)の4.96倍圧縮率を適用すると **gzip 1.2〜2.5KB**。tailwind_v4提案の `prose-h3:`/`prose-h4:` 等の個別修飾子が増えるほど増分は上振れするが、それでも常識的な範囲では **gzip 1.5〜3KB** に収まると見積もる（round1の「1〜3KB」を「1.5〜3KB」に微修正、大枠は変わらず）。

**結論は変わらない**: raw 12KB・gzip 3KB程度の増分は、現状の静的アセット総量（928KB）に対して無視できる水準であり、3MB gzip上限（Worker本体側）とはそもそも無関係（Q1参照）。**実測での確定にはnpm installとビルドが必要** な点は変わらないため、導入PRでの前後比較実測を引き続き必須とする。

---

## Q3: `<table>` / `<pre>` の横溢れ対策 — round1からの訂正（concession）

### 検証結果（WebSearchで一次情報確認）

CSS2.1仕様のエラータ（`overflow: auto`/`scroll` on table elements）: **table box に対する `overflow` の `auto`/`scroll` 値は `visible` と同じ扱いになる**。つまり **`<table>` 要素自体に `overflow-x: auto` を直接当てても、横スクロールコンテナとして機能しない**。標準的な解決策は `<table>` を `overflow: auto` を持つ `<div>` でラップすること（cross-browser、Safari含めて確立した回避策）。

これは round1 で私が「`table` にも `overflow-x:auto` を当てればよい」という含みで書いた記述に対する **訂正** である。`<table>` に限っては **CSSだけでは原理的に解けず、実DOMのラッパー `<div>` が必須**。

### `<pre>` は逆にCSSだけで解決できる（ソースで確認済み）

`@tailwindcss/typography` v0.5.20 の `src/styles.js`（DEFAULT ブロック、L1573付近）を実際に展開して確認した:

```js
pre: {
  color: 'var(--tw-prose-pre-code)',
  backgroundColor: 'var(--tw-prose-pre-bg)',
  overflowX: 'auto',
  ...
},
```

`pre` は通常のブロックボックス（table-layoutの特殊挙動を持たない）なので、`overflow-x: auto` を直接セレクタに当てるだけで機能する。**①`@tailwindcss/typography` を採用すればこれは自動的に付与される**（②自前CSSの場合も `pre { overflow-x: auto }` を1行書くだけで済む）。

一方で同じ `styles.js` の `table` 定義（L1596付近、DEFAULT・sm両ブロックとも）には `width: '100%'` と `tableLayout: 'auto'` のみで **overflow関連のプロパティが一切無い**。これは実装漏れではなく、上記のCSS仕様上の制約により **入れても効かないため意図的に省いている** と解釈できる（tailwindlabs側もラッパー `div` を利用者側の責務としている）。

→ **①を採用しても table 対策は依然として別途必要** という round1 の結論は正しかったが、その理由付け（「typographyの既知の制限」という曖昧な表現）を「CSS仕様上table boxには効かないため原理的に不可能」という確定的な根拠に強化する。

### 実装方法: `readme-html.ts` の `transformTags` では足りない

質問への直接回答: **`transformTags`（`sanitize-html`）だけでは`<table>`をラップできない**。`node_modules/sanitize-html/index.js` を確認したところ、`transformTags` のコールバックは `(tagName, attribs) => { tagName, attribs }` を返すだけで、**単一タグの改名・属性変更しかできず、新しい親要素を挿入する機能はない**（ラップ操作は非対応）。

したがって table ラッパーを実現するには、`sanitizeReadmeHtml` が返した文字列に対する **追加の後処理ステップ**（正規表現での `<table ...>...</table>` 検出・ラップ、または軽量DOM処理ライブラリでの1回限りの変換）が必要になる。実装の置き場所（`readme-html.ts` 内に処理を1段追加するか、別関数に切り出すか）は `impl_readme` / `arch_domain` の判断に委ねるが、性能レンズからの制約は1点のみ: **追加するラッパー `<div>` の `class` はコード側が固定文字列で発行するものに限り、README由来の `class` 属性をそのまま透過させない**（tailwind_v4がround1で挙げた③の懸念——`ALLOWED_ATTRIBUTES` に任意の `class` 値を許可するとCSSインジェクション面のリスクが増える——とは別物であることを明確にしたい。今回提案しているのは「サニタイズ済みHTMLに、こちらのコードが自分で書いた固定クラス名の `div` を差し込む」だけであり、**README側の任意入力を新たに許可リストに加える話ではない** ため、③の懸念は生じない）。

---

## Q4: E2Eフィクスチャの具体案

現状 `e2e/stub/server.mjs` L438 の README fixture は `<article><h1>...<p>...<ul>...</ul></article>` のみで、table・コードブロック・長いURL・バッジ画像を含まない。`e2e/feedback-334.spec.ts` は現行フィクスチャでの表示確認に留まっている。

**追加提案**（`README_MISSING_MARKER`＝`'readme-missing'` と同じ命名パターンに倣う）:

```js
// e2e/stub/server.mjs
const README_OVERFLOW_MARKER = 'readme-overflow' // 新規リポジトリ名マーカー
// ↑ readme-missing と同様、リポジトリ名にこの文字列を含めたときだけ挙動を切り替える
```

フィクスチャHTML案（`README-STUB-CONTENT` の代わりにこのリポジトリ名の時だけ返す）:

```html
<article>
  <h1>readme-overflow</h1>
  <p>
    <img src="https://img.shields.io/badge/build-passing-brightgreen" alt="build" />
    <img src="https://img.shields.io/badge/license-MIT-blue" alt="license" />
    <img src="https://img.shields.io/badge/coverage-92%25-green" alt="coverage" />
  </p>
  <p>See https://example.com/very/long/path/segment/that/does/not/wrap/naturally/because/it/has/no/spaces/at/all/1234567890</p>
  <pre><code>const veryLongLine = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";</code></pre>
  <table>
    <thead><tr><th>Col A</th><th>Col B</th><th>Col C</th><th>Col D</th><th>Col E</th><th>Col F</th></tr></thead>
    <tbody>
      <tr><td>0000000000</td><td>1111111111</td><td>2222222222</td><td>3333333333</td><td>4444444444</td><td>5555555555</td></tr>
    </tbody>
  </table>
</article>
```

**Playwright検証**（`e2e/feedback-334.spec.ts` に追記する形を想定）:

```ts
test('F-4拡張: 幅の広いREADMEコンテンツでページ全体が横スクロールしない', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 }) // モバイル幅想定
  await page.goto('/ja/repos/octostub/octo-readme-overflow')
  await expect(page.getByRole('heading', { name: 'README' })).toBeVisible()

  // ページ本体（documentElement）は横スクロールしないこと
  const { scrollWidth, clientWidth } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }))
  expect(scrollWidth).toBeLessThanOrEqual(clientWidth)

  // table 自体（またはそのラッパー）は横スクロール可能であること（中身が見切れて消えていないことの確認）
  const tableOverflowsInternally = await page.locator('table').first().evaluate((el) => {
    const scrollContainer = el.closest('[class*="overflow"]') ?? el
    return scrollContainer.scrollWidth > scrollContainer.clientWidth
  })
  expect(tableOverflowsInternally).toBe(true)
})
```

このテストは「ページ本体が横に伸びていないこと」と「表自体は（意図通り）内部スクロールできていること」の両方を検証でき、①②③どの実装を選んでも回帰検知の網として機能する（実装詳細に依存しないアサーションにしてある）。フィクスチャ追加自体は `readme_render` / `rev_tests` 側の実装スコープになるため、ここでは仕様として提案するに留める。

---

## Q5: 30,000文字上限の見直し要否 — 定量化した上での結論

### 見積もりシミュレーション（合成HTML・実測に近づける手法）

Lighthouseの `dom-size` 監査のしきい値（WebSearchで確認: 警告 約800ノード／エラー 約1,400〜1,500ノード。Lighthouse 13以降はスタイル再計算コストベースの指標に移行しているが、ノード数は依然参考値として報告される）と突き合わせるため、30,000文字ちょうどになるまでタグを積んだ3パターンを合成し開始タグ数（≒ノード数の近似）を数えた:

| パターン | 文字数 | 開始タグ数（ノード数近似） | Lighthouseしきい値との比較 |
|---|---|---|---|
| 段落中心（典型的な文章主体README） | 30,104 | **284** | 警告(800)の1/3以下、余裕あり |
| リスト中心（箇条書きが多いREADME） | 29,929 | **545** | 警告(800)未満、やや余裕あり |
| 表中心（列の多い巨大テーブルが続くREADME・worst case） | 30,022 | **1,748** | **エラーしきい値(約1,400〜1,500)を超過** |

### 結論

**30,000文字の上限は据え置きを推奨する。ただし無条件ではない**。

- 典型的な文章・リスト中心のREADME（実務上の大多数）では、DOMノード数はLighthouseの警告しきい値にすら達しない。文字数上限を一律に下げると、この健全な大多数に対して不要な切り詰めを増やすだけで実利がない。
- 一方で **表が密なREADME は実際にLighthouseの `dom-size` エラーしきい値を超えうる** ことを今回定量化した。ただし `tools/run_lighthouse.mjs` は現状 performance カテゴリを非ゲート（accessibilityのみブロッキング）としているため、これが実際に発生してもCIは失敗しない。
- **文字数上限の引き下げでこの問題を解こうとするのは筋が悪い**（表10行のREADMEも表1000行のREADMEも同じ「1つの表」として扱われ、文字数だけでは密度の違いを区別できない。誤って文章主体の健全なREADMEまで一律に切り詰めてしまう副作用の方が大きい）。
- **推奨する対処は Q4 のフィクスチャ拡充**: 表中心のフィクスチャをLighthouse対象（`/ja/repos/octostub/octo-widgets` 相当）に含めれば、`perf=NN` の記録値・`dom-size` の実際の監査結果が継続的に可視化され、将来 performance カテゴリがゲート化される際にも先回りできる。今回はここまでを性能レンズの結論とし、上限値そのものの変更は提案しない。

---

## 反対されうる点

- Q2の見積もり（raw 6〜12KB / gzip 1.5〜3KB）は、`prose-h3:` 等の個別修飾子をどこまで使うか（tailwind_v4の提案次第）で上下に振れる。実装が固まった段階での実測必須という結論は変わらないが、「上方修正した」こと自体が見積もりの不安定さを示しており、確度としては引き続き「見積もり」の域を出ない。
- Q3のtable ラッパーの実装コスト（`readme-html.ts` への後処理ステップ追加）は、tailwind_v4がround1で示した「①の実装コストはCSS1行+package.json1行」という比較表を実質的に修正するもの——**①を選んでもtable対策の実装コストは②③と大差なくなる** 可能性がある。この点は tailwind_v4 の推奨そのものを覆すものではないが、①の「低コスト」という評価軸には再考の余地があると考える。
- Q5の合成シミュレーションはあくまで極端な合成データによる机上検証であり、実際のGitHub README（HTML構造・タグの入れ子度合い）とは乖離がありうる。`readme_fidelity` が実測した `bcaudan/jasmine-spec-reporter` のような実リポジトリで、大きな表を含むREADME（例: 多言語対応表・API仕様表を持つ大型OSS）を用いた実測が望ましいが、本ラウンドでは着手していない。

## ラウンド 3

### `lead` — 合意
<sub>2026-08-21T18:14:47+09:00</sub>

# 合意と裁定（lead / round 3）

## 診断（全員一致・争点ではない）

書式が出ない主因は **サニタイズの許可タグ不足ではなく、描画コンテナに typography 系の CSS が一切当たっていないこと**。
Tailwind v4 の Preflight が見出し・リスト・引用・表の既定装飾を打ち消すため、`readme-section.tsx` のコメントが前提にしていた
「見出し・段落・リストは既定のブラウザスタイルに委ねる」が成立していない（`readme_fidelity` が本番出力で実証・`tailwind_v4` の静的読解と一致）。

## 争点 A: 方式の選択 → **① `@tailwindcss/typography` を導入する（条件付き）**

**採用**: `app/globals.css` に `@plugin "@tailwindcss/typography";` を追加し、README コンテナに `prose` を当てる。
**必須条件**（`a11y_theme` の懸念を構造的に消すための条件・`tailwind_v4` が round 2 で自ら推奨に組み込んだもの）:

1. `--tw-prose-*` **18 項目すべて** を本プロジェクトのセマンティックトークン（`--color-fg` / `--color-fg-muted` / `--color-accent` 系 / `--color-border` / `--color-bg-subtle`）へマッピングする。プラグイン既定の gray スケールを 1 項目も残さない
2. **`prose-invert` / `--tw-prose-invert-*` は使わない**。トークン自体が `:root` と `.dark` で異なる値を持つため、参照先をトークンにするだけでダークへ自動追従する。invert セットを使わないことで「ダーク側の 18 項目を書き漏らす」という失敗モードが構造的に消える（36 項目 → 18 項目）
3. リテラル色（`oklch(` / `#` / `rgb(`）が `--tw-prose-*` の値に混入していないことを機械検査する（`a11y_theme` が提示した条件・書き忘れがプラグイン既定色へ静かにフォールバックするのを検知するため）

**② 自前スコープ CSS を採らない理由**: `a11y_theme` は round 2 で「②の方が CSS 量が少ない」という自身の根拠を **実測して撤回** した（量はほぼ互角）。
`perf_bundle` の実測により「CSS は Workers Static Assets 配信で Worker の 3 MB gzip 上限の **対象外**」（増分は gzip 1.5〜3 KB 見積もり）と確定し、サイズも選択理由から外れた。
残る差は「色 18 行だけ書けば、余白・行間・リストマーカー・ネスト・表・コードブロックの **寸法系はプラグインが提供する**」という実装量・保守量の差であり、①が優位。
飼い主の指示「最新の仕様・ノウハウ・ベストプラクティスをリサーチして対応」に照らしても、Tailwind で Markdown/README 由来 HTML を描画する標準解は typography プラグインである。

**③ サニタイズ時のユーティリティクラス注入を採らない理由**: `class` 属性の許可が必要になり、第三者 HTML のサニタイズと装飾注入が混線する（`a11y_theme` / `tailwind_v4` 一致）。安全性を下げる方向の変更は採らない。

## 争点 B: 降格済み見出し（h3 起点）とスケール

見出しの **+2 降格は現行のまま維持** する（`h1→h3`・`h6` cap）。セマンティック階層は変えない。
視覚スケールは `.prose` 側で調整し、**README 内の最上位見出し（h3）がページのセクション見出し（`<h2>`「README」・18px）を超えないようにする**
（`a11y_theme` 案・`readme_fidelity` も round 2 で同意）。段階は `h3` = 16px / `h4` = 14px を基準に、太さ（`font-weight`）と余白で階層を作る。
**理由**: 第三者コンテンツの見出しが自サイトのセクション見出しより目立つのは情報設計として倒錯している。書式の再現度（README の最上位見出しが「大きく見える」）は
weight と余白で十分に達成でき、フォントサイズの逆転までは要らない。

## 争点 C: ダークモード

`prose-invert` は使わない（争点 A 条件 2）。本プロジェクトの `dark` は `@custom-variant dark (&:is(.dark *))`（`app/globals.css:5`）で
`.dark` クラス基準だが、**現状 `layout.tsx` は `.dark` を付けておらず、テーマ切替は未配線**（`a11y_theme` の指摘・実ファイルで確認）。
したがって README も他の画面と同じくライト固定で描画される。トークン参照にしておけば、将来テーマ切替が配線された時点で README も自動で追従する。
**テーマ切替の配線自体は本 PR のスコープ外**（別 Issue）。

## 争点 D: サニタイズとの整合

**`readme-html.ts` の許可リストは変更しない**。`prose` は親要素のクラスと子孫セレクタで効くため、`class` 属性の許可は不要（仮説どおり・`tailwind_v4` 確認）。
`<details>` / `<summary>` / タスクリストのチェックボックス / シンタックスハイライト / 絵文字画像 / GitHub アラート記法は
**本 PR のスコープ外**（`readme_fidelity` の線引きに従い別 Issue）。飼い主のスクリーンショットに写っている崩れは
見出し・リスト・段落・コードブロックであり、これらは CSS だけで解決する。
バッジ画像は実出力で `width`/`height` 属性を持たないため `max-width: 100%`（Preflight が既に適用）で足りる（`readme_fidelity` が実出力で確認）。

## 争点 E: 横溢れ（table / pre / 長い URL）

- `<pre>`: typography 本体の `styles.js` に `overflowX: 'auto'` が入っていることを `perf_bundle` がソースで確認済み。**追加対応不要**
- `<table>`: **CSS の `overflow-x: auto` を `<table>` 自身に当てても効かない**（CSS 2.1 の table box の既知の制約・`perf_bundle` が round 2 で自らの round 1 を訂正）。
  ただし `<table>` に `display: block` を当てて解決する手は **採らない**（表のセマンティクスを支援技術から見て壊しうる）。
  **採用**: README 本文コンテナ側に `overflow-x: auto` を当て、はみ出す表はコンテナごと横スクロールさせる。
  DOM ラッパーの後付け挿入（サニタイズ済み文字列への後処理）は、ネストや属性の取り回しで壊れやすいわりに得られるものが「表単体スクロール」に留まるため今回は採らない。
  表単体スクロールが必要になったら別 Issue で `transformTags` ベースの実装を検討する
- 長い URL・長い単語: 現行の `break-words` を維持する

## 争点 F: 回帰の機械検査

現行の検査群（`check_ui_dimensions.py` / `check_contrast.py` / axe / Lighthouse）は **書式が当たっていないことを検知できなかった**。本 PR で次を足す:

1. **E2E**（`e2e/` に追加）: README を含む詳細ページで ① 見出し（h3）の実効フォントサイズが本文（p）より大きい ② リストにマーカー（`list-style-type` が `none` でない）が付く
   ③ コードブロックに背景色が付く ④ **`body` に横スクロールが出ない**（`document.documentElement.scrollWidth <= clientWidth`）
2. **E2E スタブのフィクスチャ拡充**（`e2e/stub/server.mjs`）: 見出し多段・ネストリスト・表・コードブロック・長い URL・バッジ画像を含む README を返す専用リポジトリを足す（`perf_bundle` 案）
3. **リテラル色の混入検査**: `--tw-prose-*` の値が `var(--color-*)` 以外（`oklch(` / `#` / `rgb(`）になっていないことを検査する軽量チェックを `tools/` に足し、`run_checks.sh` に配線する

**30,000 文字の切り詰め上限は据え置く**（`perf_bundle`: 文章主体の README は 280〜550 ノードで余裕。表が密な README のみ Lighthouse の `dom-size` エラー閾値に触れうるが、
文字数一律の見直しより上記フィクスチャでの継続監視が筋）。

## ドキュメント

`docs/03_design/ui-ux/ui-ux-guidelines.md` に **第三者コンテンツ（README）の表示規定** を新設する（`a11y_theme` の §2.5 案を方式非依存の文言で採用）:
「第三者が書いた HTML を埋め込む領域は、① 自サイトのセマンティックトークンだけで着色する ② セクション見出しより大きい見出しを作らない
③ 横溢れは領域内スクロールに閉じ込め body に出さない」。あわせて `readme-section.tsx` の「既定のブラウザスタイルに委ねる」というコメントを実装に合わせて書き換える。

## 申し送り（本 PR に入れない）

- `<details>` / タスクリスト / シンタックスハイライト / 絵文字 / GitHub アラート記法の対応（`readme_fidelity` の別 Issue 案）
- テーマ切替（`.dark` クラスの配線）の実装
- `cloudflare-infrastructure.md` §5.3 の計測コマンドが router stub しか測れていない件（`perf_bundle` の副次的発見。正しくは `wrangler deploy --dry-run` の `Total Upload ... gzip:` 行）
- 表単体の横スクロール（DOM ラッパー方式）

### `lead` — 判定
<sub>2026-08-21T18:15:22+09:00</sub>

{
  "decisions": [
    {
      "issue": "A: 書式適用の方式",
      "design": "@tailwindcss/typography を導入し README コンテナへ prose を当てる。--tw-prose-* 18 項目をセマンティックトークンへ全マッピングし、prose-invert / --tw-prose-invert-* は使わない（トークンが .dark で自己反転するため書き漏らしの失敗モードが消える）。リテラル色の混入を機械検査する。",
      "artifacts": [
        "package.json（改修・@tailwindcss/typography を devDependency へ追加）",
        "app/globals.css（改修・@plugin 追加と .prose の --tw-prose-* トークンマッピング）",
        "src/ui/readme-section.tsx（改修・コンテナのクラスと誤ったコメントの修正）"
      ],
      "tests": [
        "e2e/readme-typography.spec.ts（新規・見出しサイズ / リストマーカー / コードブロック背景）",
        "tools 側のリテラル色検査（新規・run_checks.sh へ配線）"
      ],
      "rejected": "② 自前スコープ CSS（提案者自身が『CSS 量は互角』と実測して撤回。寸法系を全部手書きする分だけ不利）／③ サニタイズ時のクラス注入（class 属性の許可が必要で安全性を下げる）"
    },
    {
      "issue": "B: 見出しスケール",
      "design": "+2 降格（h1→h3・h6 cap）は維持。.prose 側で h3=16px / h4=14px を基準に調整し、ページのセクション見出し（h2・18px）を超えないようにする。階層は太さと余白で作る。",
      "artifacts": ["app/globals.css（改修・.prose の見出しサイズ）"],
      "tests": ["e2e/readme-typography.spec.ts（h3 が p より大きく、ページの h2 以下であること）"],
      "rejected": "降格段数の見直し（セマンティック階層を崩す）／README 見出しをページ見出しより大きくする案（情報設計の倒錯）"
    },
    {
      "issue": "C: ダークモード",
      "design": "prose-invert を使わずトークン参照で自動追従させる。テーマ切替（.dark クラスの配線）は現状未実装であり本 PR のスコープ外。",
      "artifacts": ["app/globals.css（改修）"],
      "tests": [],
      "rejected": "dark:prose-invert + --tw-prose-invert-* 18 項目の定義（項目数が倍になり書き漏らしの失敗モードが残る）"
    },
    {
      "issue": "D: サニタイズとの整合",
      "design": "readme-html.ts の許可リストは変更しない。prose は親クラス + 子孫セレクタで効くため class 属性の許可は不要。details / タスクリスト / シンタックスハイライト / 絵文字 / アラート記法は別 Issue。",
      "artifacts": [],
      "tests": ["既存の readme-html.test.ts が変更なしで緑であること"],
      "rejected": "class 属性の許可（第三者 HTML の安全性を下げる）／許可タグの大幅拡張（今回の症状の原因ではない）"
    },
    {
      "issue": "E: 横溢れ",
      "design": "pre は typography 既定の overflow-x:auto で足りる。table は CSS では table box 自身にスクロールを付けられないため、README 本文コンテナ側に overflow-x:auto を当てて領域内スクロールに閉じ込める。break-words は維持。",
      "artifacts": ["src/ui/readme-section.tsx もしくは app/globals.css（改修）"],
      "tests": ["e2e/readme-typography.spec.ts（body に横スクロールが出ないこと）", "e2e/stub/server.mjs（改修・表 / コードブロック / 長い URL / バッジを含むフィクスチャ）"],
      "rejected": "table への display:block（表のセマンティクスを壊しうる）／サニタイズ済み文字列への後処理で div ラッパーを挿入（壊れやすく、得られるのは表単体スクロールのみ）"
    },
    {
      "issue": "F: 回帰の機械検査",
      "design": "E2E で書式が当たっていること（見出しサイズ・リストマーカー・コードブロック背景・body の横スクロールなし）を検証し、スタブに書式要素を含むフィクスチャを足す。--tw-prose-* にリテラル色が混入していないことを検査するチェックを run_checks.sh へ配線する。切り詰め上限 30,000 文字は据え置く。",
      "artifacts": ["e2e/readme-typography.spec.ts（新規）", "e2e/stub/server.mjs（改修）", "tools/（新規チェック）", "tools/run_checks.sh（改修）"],
      "tests": ["上記 E2E"],
      "rejected": "切り詰め上限の変更（文章主体の README は DOM ノード数に余裕があり、文字数一律の見直しは筋が悪い）"
    }
  ],
  "critical": [
    "@tailwindcss/typography は未インストール。実際に入れてビルドが通り、Workers デプロイまで到達することを本 PR 内で実測する（CSS は Static Assets 配信で Worker の 3MB gzip 上限の対象外という判定は perf_bundle が dry-run 実測で確認済み）。",
    "テーマ切替が未配線のため、ダーク時の見え方は本 PR では検証できない（トークン参照にしておく以上のことはしない）。"
  ],
  "open_questions": []
}
