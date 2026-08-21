<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: 詳細画面の README を書式どおりに表示する方式を確定する（Tailwind v4 / Workers 制約下）

- 議題ID: `readme_typography_20260821`
- 論点: 飼い主フィードバック（2026-08-21・Issue #339）: 「README について参照できるようになったが**書式が反映されていない**」。実機スクリーンショットでは、README の見出し・リスト・インラインコード・コードブロックがすべて同じ大きさの素のテキストとして縦に並んでおり、階層も余白も付いていない（唯一 `code` 相当が等幅で出ている）。現状: PR #337 で `GET /repos/{o}/{r}/readme` を `Accept: application/vnd.github.html+json` で取得し、`src/ui/readme-html.ts` が sanitize-html で 1 パス変換（許可リスト・相対 URL 解決・target=_blank 付与・見出し +2 降格（h1→h3・h6 cap・id 保持）・30,000 文字での切り詰め）してから `src/ui/readme-section.tsx` が `dangerouslySetInnerHTML` で描画している。描画側のクラスは `className="mt-2 max-w-none space-y-3 text-sm leading-relaxed break-words"` だけで、実装時のコメントは「`@tailwindcss/typography` は未導入（新規依存の追加禁止・タスクスコープ外）のため `prose` は使わない。見出し・段落・リストは既定のブラウザスタイルに委ねる」と書いている。ところが本プロジェクトは **Tailwind CSS v4**（`app/globals.css` の 1 行目が `@import "tailwindcss";`、他に `tw-animate-css` と `shadcn/tailwind.css` を import）であり、Tailwind の Preflight がブラウザ既定スタイル（見出しのサイズ・リストのマーカーとインデント・引用・表の枠）を打ち消すため『既定のブラウザスタイルに委ねる』が成立していない。これが書式が出ない直接原因である（この仮説自体も検証対象とする）。制約: ① Cloudflare Workers（OpenNext）で動く。バンドル上限 3 MB（gzip・現在 1372 KiB）・`limits.cpu_ms: 50`。CSS はビルド時に静的化されるので実行時 CPU には効かないが、バンドル/アセットサイズと Lighthouse への影響は見る ② `NFR-3` クライアント JS を増やさない（`use client` を足さない） ③ ダークモード（`app/globals.css` のセマンティックトークン）と `docs/03_design/ui-ux/ui-ux-guidelines.md`（§2 デザイントークン・§7 a11y・§8 表示状態）に整合させる ④ サニタイズの許可リスト（`ALLOWED_TAGS`）を超えるタグは描画されないので、スタイルを当てる対象は許可済みタグに限る ⑤ README は第三者が書いた HTML であり、スタイルのために許可タグ・許可属性（特に `class` / `style`）を広げるとサニタイズの前提が変わる ⑥ 見出しは +2 降格済みなので、README 内の最上位見出しは h3 として出てくる（プレーンな `h1` セレクタ前提のスタイルは当たらない）。争点は少なくとも次の 6 つ: A) 方式の選択 — `@tailwindcss/typography`（v4 では CSS 側の `@plugin "@tailwindcss/typography";` で読み込む形になっているはず。**最新の公式ドキュメントで v4 における導入方法・`prose` の使い方・`not-prose`・`prose-invert` / ダークモード対応の現行仕様を必ず一次情報で確認すること**）を入れるか、`app/globals.css` に自前のスコープ付き CSS（例 `.readme-content h3 { ... }`）を書くか、`readme-html.ts` の `transformTags` で各タグに Tailwind ユーティリティクラスを注入するか B) 降格済み見出し（h3 起点）と typography プラグインの既定スケール（h1/h2 前提）の噛み合わせをどう解決するか（`prose-headings:` 系の修飾で足りるか、降格の段数自体を見直すべきか） C) ダークモードの扱い（`prose-invert` を使うか、セマンティックトークンで自前定義するか。本プロジェクトのテーマ実装と整合するか） D) サニタイズとの整合 — `class` 属性を許可しないまま方式 A を成立させられるか（typography は親要素の `prose` クラスと子孫セレクタで効くはずなので許可リスト変更は不要という仮説の検証）。GitHub 由来の HTML が持つ独自クラス（`anchor` / `octicon` / `highlight` / `notranslate` 等）や `<img>` のバッジ、`<details>`/`<summary>`、絵文字画像（`g-emoji`）、シンタックスハイライト用の `<span class="pl-*">` が現状どう落ちているか、書式再現にどこまで必要か E) バンドル・パフォーマンスへの影響（typography プラグイン導入時の CSS 増分の実測方法、Lighthouse への影響、`max-w-none` の扱い、モバイルでの表・コードブロックの横スクロール） F) 回帰をどう機械検査するか（現状 `tools/check_ui_dimensions.py` / `check_contrast.py` / axe / Lighthouse があるが、書式が当たっていないことは検知できなかった。E2E で「見出しの計算後フォントサイズが本文より大きい」等を検証できるか、その検査は過剰か）。
- 参加者: `tailwind_v4`, `readme_fidelity`, `perf_bundle`, `a11y_theme`
- 投稿数: 4
- 更新: 2026-08-21T18:05:15+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

## ラウンド 1

### `tailwind_v4` — 主張
<sub>2026-08-21T18:01:03+09:00</sub>

## 結論

`@tailwindcss/typography` 導入案が最も低コストかつ安全。**Tailwind v4 では `tailwind.config.js` を新設せず、`app/globals.css` に `@plugin "@tailwindcss/typography";` を 1 行追加するだけ**で有効化できる。`prose max-w-none dark:prose-invert` を `readme-section.tsx` の `<div>` に付与し、降格済み見出し（README 内は `h3`〜`h6` に強制シフト済み・`readme-html.ts:27-34`）は `prose-h3:text-lg prose-h3:font-semibold` 等の要素修飾子でスケール調整する。Preflight を切る選択肢は他 UI（shadcn コンポーネント全体）を壊すため不採用が正しい。

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
- `/home/user/gem-hunter/app/globals.css` の **4 行目**（現状 1〜3 行目は `@import` 3 本、5 行目が `@custom-variant dark`）に `@plugin "@tailwindcss/typography";` を **1 行挿入**するだけ。`@import` ブロックの直後・`@custom-variant` の前が自然な位置。
- `postcss.config.mjs` は **変更不要**（`@tailwindcss/postcss` が既に CSS 内の `@plugin` ディレクティブを解決する。v3 のように `plugins: [require('@tailwindcss/typography')]` を JS 側に書く必要はない）。

→ 合計で **CSS 1 行 + package.json 1 行**。`tailwind.config.js` 新設は不要（v4 では非推奨/存在しない前提）。

### 2. `prose` の適用単位・サイズスケール

- `prose` はクラスを当てた要素の**子孫**（見出し・段落・リスト・コード等）に CSS セレクタベースでスタイルを適用する（コンポーネント登録ではなく通常のユーティリティクラス）。
- 既定で `max-width: 65ch` 相当が付く。**コンテナ幅に合わせるには `max-w-none` を明示的に追加**する必要がある（`readme-section.tsx:128` は既に `max-w-none` を単独クラスとして使っているので、`prose max-w-none` の並びに違和感なく統合できる）。
- サイズスケール: `prose-sm` / `prose-base`（既定） / `prose-lg` / `prose-xl` / `prose-2xl`。本プロジェクトの現行クラスが `text-sm` のため、`prose-sm` を選ぶのが最も既存デザインとの差分が小さい。

### 3. ダークモード

- `@tailwindcss/typography` は `dark:prose-invert` で切り替える仕様（CSS 変数ベースの配色反転）。
- 本プロジェクトは `app/globals.css:5` に `@custom-variant dark (&:is(.dark *));` を定義しており、**`.dark` 祖先クラスの有無で切り替える方式**（`app/[locale]/layout.tsx` は未 Read だが、`globals.css` の `@custom-variant` 定義から Tailwind 標準の `dark:` バリアントを `.dark` クラスベースで再定義していることが確認できる。これは shadcn の標準パターン）。
- `dark:prose-invert` は Tailwind の `dark:` バリアント機構に乗るユーティリティなので、**この `@custom-variant` 再定義と完全に噛み合う**（`dark:` の実体が何であれ、`dark:prose-invert` はその条件下で `prose-invert` を適用するだけ）。矛盾なし。
- ⚠️ `app/[locale]/layout.tsx` 側で実際に `<html class="dark">` のように**クラスをどこで付け外ししているか**は未確認（読む指示のファイルには含まれていたが本ラウンドでは `globals.css` の定義確認を優先した）。**未確認**: layout.tsx 内の具体的なテーマ切り替えトリガー（`next-themes` 等の使用有無）。他の参加者のレンズで確認済みなら整合性チェックだけで済む。

### 4. 降格済み見出し（README 最上位が `h3`）のスケール調整

`prose-headings:` は h1〜h6 と `th` に一括適用、`prose-h3:` のように**個別タグ修飾子**も存在する（Context7 確認済み: `class-reference.md`）。例:

```html
<article class="prose prose-sm max-w-none prose-h3:text-base prose-h3:font-semibold prose-h4:text-sm">
```

`readme-html.ts:27-34` の `HEADING_SHIFT`（`h1→h3` … `h5/h6→h6`）と組み合わせても、**`prose-h3:` 等のタグセレクタは DOM 上の実タグ名に対して効く**ため、シフト後のタグ構成のままで見た目のスケールだけ `prose-h3:` 系ユーティリティで復元・調整できる。デフォルトの `prose` は「文書内の最上位見出しが `h1`」を想定した相対スケールを持つため、**無調整だと `h3` 始まりの見た目がやや小さめになる可能性がある**——これは実装フェーズで実ブラウザ確認が必要な項目であり、本ラウンドでは「調整手段が存在する」ことまでを確認する。

### 5. `not-prose` の用途

`prose` 適用範囲内で「ここだけは prose のスタイルを外したい」ブロックに使う一括除外ユーティリティ（Context7 確認済み: `plugin.md` の Generated Variants 記載）。本件では、README 本文全体を `prose` 化する方針であれば、通常は不要。ただし将来的に README 内に**埋め込みウィジェットやカスタムブロックを許可リストに追加する**場合、その要素にだけ `not-prose` を当てて prose のリセットから逃がす、という用途はありうる（現状の `ALLOWED_TAGS`・`readme-html.ts:46-92` を見る限り、そのような要素は今のところ存在しないため**現時点で使う場面はない**）。

### 6. Preflight と typography の関係（Preflight を切る選択肢について）

Context7 の公式説明（`README.md` / `_autodocs/README.md`）:

> "By default, Tailwind removes browser styling, which is useful for application UIs but can be surprising for content from rich-text editors or markdown files. The `@tailwindcss/typography` plugin aims to provide excellent typography **without the downsides of disabling base styles**."

つまり **typography プラグインは「Preflight を維持したまま、`.prose` 配下だけスコープを絞って装飾を復元する」ことこそが存在意義**であり、Preflight と typography はセットで使うのが公式に想定された設計。

**Preflight を切る案が不可な根拠**: `app/globals.css:150-165` の `@layer base` は `* { @apply border-border outline-ring; }` `body { @apply bg-background text-foreground; }` `html { @apply font-sans; }` を Preflight 前提の CSS カスケードで組んでおり、Preflight（ブラウザ既定値のリセット）を切ると shadcn コンポーネント一式（`button.tsx` / `input.tsx` 等、コメントに明記あり）のフォーカスリング・ボーダー・フォント指定が二重定義・崩れの原因になる。**Preflight はグローバル適用**（v4 でも無効化オプションは「プラグイン全体を読み込まない」単位でしか存在せず、`.readme-content` だけスコープを絞って切ることはできない）。→ **不可（他 UI 全体を道連れにする）**。

### 7. 代替案比較

| 案 | 実装コスト | 保守性 | 安全性 | 備考 |
|---|---|---|---|---|
| **① `@tailwindcss/typography`** | 低（CSS 1 行 + `package.json` 1 行 + `readme-section.tsx` のクラス変更のみ） | 高（Tailwind 公式・アップデート追従・テーマトークンとの連動は別途要検証） | 高（サニタイズ後の HTML に対する**装飾のみ**。属性・タグの許可を増やさない） | 見出しスケール調整は `prose-h3:` 等で対応可（§4） |
| ② 自前スコープ付き CSS（`.readme-content h3{...}` 等） | 中〜高（見出し・リスト・コード・テーブル・blockquote 等を手動で網羅、ダークモード分岐も自前実装） | 低（Tailwind のテーマトークン変更に追従させる保守が継続的に発生。属人化しやすい） | 高（同上、サニタイズ済み HTML への装飾のみ） | 既存コメント（`readme-section.tsx:125` 「新規依存の追加禁止」）は本タスクで見直し対象と推定 |
| ③ `transformTags` でタグごとに Tailwind ユーティリティを直接注入 | 中（`readme-html.ts` の変換ロジックに全許可タグ分のクラス付与処理を追加） | 中（`sanitize-html` の `class` 属性をサニタイズの許可リストに追加する必要があり、`readme-html.ts` の責務が「サニタイズ」から「サニタイズ+スタイリング」に肥大化） | **要注意**: `class` 属性をサニタイズ対象に加えると、任意の CSS クラス名文字列がサニタイズ後 HTML に残る経路が新たに生まれる（XSS 直結ではないが、CSS インジェクション的な想定外スタイル適用のリスク面で①③より監査コストが増える。既存の `ALLOWED_ATTRIBUTES`（`readme-html.ts:94-104`）は意図的に最小構成を保っている設計思想と衝突する） | 非推奨 |

## 推奨

**① `@tailwindcss/typography` プラグイン導入**を推奨する。理由:
- 変更範囲が最小（CSS 1 行 + 依存追加 + コンポーネントのクラス変更）で `sanitize-html` の許可リストに一切手を入れない（③のセキュリティ懸念を回避）
- Preflight との併用が公式設計そのもの（§6 の一次情報）
- ダークモード・見出し降格・レスポンシブサイズの全要件が `dark:prose-invert` / `prose-h3:` / `prose-sm` の標準修飾子だけで満たせる（§2〜4）
- `readme-section.tsx:125` のコメント「新規依存の追加禁止（タスクスコープ外）」は**当時のタスクスコープの制約であり、今回の書式修正タスクではこの制約自体を見直す**必要がある（実装担当・スコープ判定は他の参加者の議論に委ねる）

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
| `<table>` の `class="table" `等の GitHub 独自属性 | 落ちる（`table`/`th`/`td` の属性は `colspan`/`rowspan` のみ許可） | 罫線自体は自前 CSS 次第（後述） |

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
- `--tw-prose-*` は CSS カスタムプロパティなので上書き自体は可能（Tailwind Typography 公式が想定する拡張点）。**採用するなら全項目を `app/globals.css` 内でセマンティックトークンへエイリアスする**ことを必須にする（例: `--tw-prose-body: var(--color-fg); --tw-prose-headings: var(--color-fg); --tw-prose-links: var(--color-accent); --tw-prose-bold: var(--color-fg); --tw-prose-counters: var(--color-fg-muted); --tw-prose-bullets: var(--color-border); --tw-prose-hr: var(--color-border); --tw-prose-quotes: var(--color-fg); --tw-prose-quote-borders: var(--color-border); --tw-prose-captions: var(--color-fg-muted); --tw-prose-code: var(--color-fg); --tw-prose-th-borders: var(--color-border); --tw-prose-td-borders: var(--color-border);` と、ダーク側の `--tw-prose-invert-*` 一式も同様に）。1 項目でも上書き漏れがあれば §3 のゲート抜けが起きる（下記）。
- ②（自前スコープ CSS）はそもそも `var(--color-*)` を直接参照するだけなので、この「上書き必須リスト」を持つ必要がない。**新規トークンをゼロに保てる**という点でテーマ整合が最も単純。

**具体策（②を選ぶ場合の指針）**: `app/globals.css` の `@layer base` の外（README 専用スコープ）に `.readme-content` を追加し、`h3`〜`h6` / `p` / `a` / `code` / `pre` / `blockquote` / `table th,td` 等の要素セレクタで **既存 10 トークンのみ**を `color:` / `background-color:` / `border-color:` に指定する。新しい `--readme-*` 変数を作る誘惑があるが、作った時点で `check_contrast.py` の検査対象外になる（§3 参照）ので避ける。

---

## 2. ダークモード

`app/[locale]/layout.tsx` を実読した結果、**`next-themes` の `ThemeProvider` はまだ実装されていない**（`ThemeProvider` / `attribute=` の grep が 0 件）。`app/globals.css` 側には `@custom-variant dark (&:is(.dark *))`（L5）と `.dark { ... }` ブロック（L113-148）は既に存在するが、**`<html>` に `.dark` クラスを付与する主体（トグル UI・`ThemeProvider`）がまだ配線されていない**。つまり現時点でダークテーマは「配線待ちの静的な CSS 変数セット」であり、稼働はしていない。

このことから README スタイリングへの指針:

- **`prose-invert`（`dark:prose-invert` として `.dark` 祖先で発火させる想定のクラス）は採用しない**。理由は 2 つ: (a) `prose-invert` も独自の invert カラースケールを持ち §1 と同じ二重管理問題を抱える、(b) それ以前に **`.dark` トグル自体が未実装**なので、`prose-invert` を今書いても検証しようがない（動作確認できない状態で終わる= `SD-1` 違反リスク）。
- ②（自前 CSS）で `var(--color-fg)` 等のトークン参照だけを書けば、**`dark:` バリアントも `prose-invert` も一切不要**——トークン自体が `.dark` セレクタ配下で値を持っているため（例: `--foreground` は `:root` で `oklch(0.145 0 0)`、`.dark` で `oklch(0.985 0 0)`）、`.dark` が将来配線された瞬間に README 本文も自動で追従する。**ダークモード対応の実装コストをゼロにできる**のがトークン直参照の最大の利点であり、これは①でも `--tw-prose-*` を上書きしてさえいれば同様に効く（`--tw-prose-invert-*` も上書き必須な点は §1 の通り）。
- コードブロック背景・引用罫線・表罫線・リンク色の具体的な割当（両テーマで破綻しないことを確認済みの既存トークンのみを使う）:
  - コードブロック（`pre`, `code`）背景: `--color-bg-subtle`（カード面トークン。ライト `oklch(0.97 0 0)` / ダーク `oklch(0.269 0 0)`。地の `--color-bg` と視覚的に区別がつく値としてすでに確定済み）
  - 引用（`blockquote`）左罫線・表（`table`）罫線: `--color-border`（**既に 3:1 ゲート済み**。§2.2 の実測表でライト 3.95:1 / ダーク 4.08:1 が PASS 確認済み——罫線は非テキストなので 3:1 要件で足りる）
  - リンク色: `--color-accent`（§2.1 の用途表に明記の「リンク・主ボタン」用トークン。4.5:1 ゲート済み）。⚠️ 現状 `readme-section.tsx` L138 の「GitHub で見る」リンクは `text-primary` を使っており `--color-accent` ではない（`--primary` は `check_contrast.py` の検査対象外トークン）。README **本文中**のリンク（第三者 HTML 由来で数が多い）はこの既存の慣習に倣わず、**ゲート対象の `--color-accent` を明示的に使う**ことを推奨する（本文リンクは 1 本の「GitHub で見る」リンクと違って数量・出現箇所を制御できないため、機械ゲートの網に必ず載せておきたい）。

---

## 3. コントラスト（`tools/check_contrast.py` の検査範囲を実読して確認）

`tools/check_contrast.py` は **`app/globals.css` の `:root` / `.dark` ブロックに書かれた固定 9 個の raw 変数**（`--background` / `--muted` / `--foreground` / `--muted-foreground` / `--border` / `--accent` / `--accent-foreground` / `--destructive` / `--destructive-foreground`）だけを正規表現でパースし、**あらかじめハードコードされた 11 ペア**（fg vs bg, fg-muted vs bg, border vs bg, accent vs bg, accent-fg vs accent, danger vs bg, danger-fg vs danger, ring vs bg, ring vs bg-subtle 等・L13-24 のコメント）のコントラストだけを計算する（L38-39 で `CSS_PATH` を `app/globals.css` に固定、パースも同ファイル限定）。

**含意**:

- README 用に **新しい raw 色**（例: `--tw-prose-code: #1f2937` のような Tailwind Typography の既定値、または自前 CSS で新規に書いた `--readme-code-bg: oklch(...)`）を導入すると、**このゲートは一切関知しない**。検査対象の変数名リストにもペアリストにも載らないため、閾値割れのまま気づかず merge されうる。
- したがって **③（サニタイズ時のユーティリティクラス注入）は特に危険**: 注入するクラス（例 `prose-slate` や独自の `text-gray-700` 相当）が実質的に新しい色を持ち込むが、注入場所が `readme-html.ts`（サニタイズ変換）なので `app/globals.css` を見ている `check_contrast.py` からは完全に不可視。
- **推奨**: README のスタイル（①でも②でも）は §1/§2 で述べた **既存 10 トークンの再利用のみ**に限定する。新規色をゼロに保てば、README のコントラストは `check_contrast.py` の既存 22 判定にただ乗りする形で保証される——**README 専用の新しいコントラスト検査を追加開発する必要がなくなる**（YAGNI・CLAUDE.md「1 箇所しか使わない抽象化レイヤーを先回りで追加しない」の精神にも合致）。
- 逆に、もし①を採用して `--tw-prose-*` の上書きを 1 項目でも忘れた場合、または②で `--readme-*` のような新変数を作ってしまった場合は、`check_contrast.py` 側の「検査対象変数リスト」（現状 9 個固定）を拡張する追加実装が必要になる。**この追加実装が要る設計は避けるべき**——ゲートを README 側の都合で毎回拡張し続けるのは持続可能でない。

---

## 4. 見出し階層(視覚 vs セマンティック)

前提の再確認（`readme-html.ts` L27-34、`ui-ux-guidelines.md` §7.0）:

- ページ全体で `h1` を持つのは共有ヘッダーのツールタイトルだけ。
- 詳細ページの「README」セクション見出しは `h2`（`readme-section.tsx` L116: `text-lg font-semibold` = 18px）。
- README 本文の見出しは `+2` シフト済みで `h3`〜`h6`（`h1→h3, h2→h4, h3→h5, h4以降→h6` で cap）。

`ui-ux-guidelines.md` §2.3 のタイポスケールは **`12/14/16/20/24px` の 5 段階のみ、中間値を足さない**が正本。ここで 1 点、既存コードとの整合に注意が必要: セクション見出し「README」自体が `text-lg`（18px）を使っており、**厳密には 5 段階のどれにも一致しない**（既存の実装で、本タスクのスコープ外の既存差分だが、README 見出しのサイズ設計はこの 18px を「超えてはいけない上限」として扱う必要がある）。

**指針（視覚とセマンティックのねじれ防止）**:

1. README 本文の `h3`〜`h6`（4 段階）に、5 段階スケールのうち **18px（セクション h2）未満の範囲**——`16px` と `14px` の 2 段階しか実質使えない（`12px` は本文メタ情報用途で埋まっており、見出しに転用すると §2.3 のカード内規約と衝突するため避ける。よって見出し専用に残るのは 16px と 14px の 2 段階のみ）。4 段階を 2 サイズに収めるには **フォントウェイトを併用**して差をつける（§2.3 の「カード内 3 段階」がすでに size + weight の組み合わせで階層を作っている前例に倣う）。
2. 具体案:

   | タグ（変換後） | 元の見出しレベル | 視覚サイズ | ウェイト |
   |---|---|---|---|
   | `h3` | 元 `h1` | `16px`（`text-base`） | `700`（bold） |
   | `h4` | 元 `h2` | `16px`（`text-base`） | `600`（semibold） |
   | `h5` | 元 `h3` | `14px`（`text-sm`） | `600`（semibold） |
   | `h6` | 元 `h4`〜`h6`（cap） | `14px`（`text-sm`） | `500`（medium） |

   いずれも `18px`（セクション h2「README」）を **上回らない**ため、「README 内の見出しがページ側の h2 より大きく見える事故」を構造的に防げる。
3. これは②（スコープ付き CSS で `.readme-content h3 {...}` 等をタグごとに個別指定）なら自然に書ける。①（`prose`）は既定で `h3`/`h4` に `1.25em`/`1.125em` 相当の相対サイズを割り当てており、かつ **「+2 シフト後のタグである」ことをプラグインは知らない**ため、上記の size/weight テーブルを含め見出し関連の `--tw-prose-*`・および Typography プラグインの `h3`,`h4`,`h5`,`h6` 個別スタイル（CSS では `font-size` は変数化されておらずクラスごとの静的値のため、上書きには `[&_h3]:text-base [&_h3]:font-bold` のような追加の Tailwind 個別指定が結局必要になる）を **全て上書き**することになり、プラグイン採用の省力化メリットがほぼ消える。この点でも②が実装コストで有利。
4. 見出しに `id="user-content-*"` が保持される（`readme-html.ts` L15, L97-100）ため、フォーカス時のアウトライン（§7.3 の `focus-visible:ring-*`）は見出し自体ではなくページ内アンカー`<a href="#...">`側の話であり本節と独立——ただし README 内リンクがアンカー遷移する際、フォーカス移動先の見出しに `scroll-margin-top` が必要かは sticky ヘッダーの有無次第（§7.3 末尾）。本アプリの共有ヘッダーが sticky でなければ不要、sticky であれば README 内アンカー着地点にも同じ配慮が要る（要確認事項として残す）。

---

## 5. 第三者コンテンツの制御（視覚破綻防止）

`readme-section.tsx` の現状ラッパー（L127-130）は `max-w-none space-y-3 text-sm leading-relaxed break-words` のみで、**画像・表・コードブロックのサイズ制御が一切ない**。これは①②③どの方式を選んでも共通で対処が必要な、**既存の実際の不具合**（未着手状態の欠陥であり本 Issue のスコープ内）。

- **画像の溢れ**: `readme-html.ts` は GitHub 由来の `width` / `height` 属性をそのまま透過する（L191-196）。README 冒頭に並ぶバッジ画像は通常小さいので問題にならないが、**スクリーンショット画像（`width="1200"` 等）はコンテナ幅を突破する**。`img { max-width: 100%; height: auto }` を README スコープに必須で追加する（`ui-ux-guidelines.md` §8.3 「画像は `width`/`height` を必須指定」という**サイト自前コンポーネント**向けの規約とは別に、**README のような可変・信頼できない寸法の画像には `max-width:100%` の上書きが必要**——この違いを明示的にドキュメント化すべき、§6 参照）。
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

- 「`@tailwindcss/typography` は業界標準で保守コストが低い」という反論は理解できるが、**このプロジェクトはすでに配色をトークン化・実測ゲート化済み**という特殊事情があり、プラグインの既定カラースケールをそのまま使うことは選択肢にない（全上書きが前提になる時点で「導入の手軽さ」という利点が縮む）。
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
- `.open-next/worker.js`（router）は `await import("./server-functions/default/handler.mjs")` で本体を**動的import**。CSSファイル名（`2zfgn5tn_e7wb.css`）は `handler.mjs` 内に **パス文字列としてのみ** 52箇所出現し、CSS本文（セレクタ・宣言）は埋め込まれていない（`grep -c "font-family|@media"` = 10件で、いずれもJSのマニフェスト文字列・断片であり実CSSブロックではない）。
- `.open-next/assets/_next/static/chunks/2zfgn5tn_e7wb.css` が実CSS本体（raw 40,585B / gzip 8,178B）。`du -sh .open-next/assets` = 928K。
- `docs/03_design/infrastructure/cloudflare-infrastructure.md` L65: 「Workers Static Assets（JS/CSS/フォント・無料・無制限）」と明記済み。**静的アセットに3MB制限は適用されない**（同ファイルL286の「Worker バンドル: 3MB（圧縮後）」はWorkerスクリプト側のみ）。

→ **判定**: CSSはWorkers Static Assets側。3MB gzip 上限の対象外。

### 2. Worker本体の実サイズ（`npx wrangler deploy --dry-run` で実測・npm installなし）

```
✨ Read 35 files from the assets directory /home/user/gem-hunter/.open-next/assets
Total Upload: 6631.44 KiB / gzip: 1372.29 KiB
```

`dry-run --outdir` で吐き出された実バンドル `worker.js`（6.79MB raw）を直接 `gzip -c | wc -c` した結果 **1,405,428 B ≈ 1.34MB**。3MB上限に対し**現状で約45%消費、残headroom約1.66MB**。

⚠️ **副次的な発見（本タスクのスコープ外だが記録）**: `cloudflare-infrastructure.md` §5.3 が指定する計測コマンド `gzip -c .open-next/worker.js | wc -c` は、動的import前の router stub のみを測る（実測746B）。実際にデプロイされる本体（`handler.mjs` 込み・1.34MB gzip）を捕捉できておらず、**この計測手順は現状の3MB判定に対して使い物にならない過小評価になっている**。`npx wrangler deploy --dry-run` の `Total Upload ... / gzip:` 行、または `dry-run --outdir` してから対象ファイルを直接gzipする方法への修正が必要。README書式化とは独立の既存ドキュメント不備のため、自分では変更せず別Issue化を推奨（担当外のためここでは提起のみ）。

### 3. `@tailwindcss/typography` 導入時のCSS増分見積もり（npm installはしていない。`npm view` によるメタデータ照会と、npmレジストリからのtarball直接ダウンロード＋展開のみ）

- `npm view @tailwindcss/typography` → v0.5.20、`peerDependencies.tailwindcss: ">=3.0.0 || >=4.0.0 || insiders"`。プロジェクトは `tailwindcss: "^4"` + `@tailwindcss/postcss` のCSS-first構成（`app/globals.css` に `@import "tailwindcss"` 方式）。typography v0.5.20のREADMEはv4向けに `@plugin "@tailwindcss/typography";` を`globals.css`へ追記する方式を明記しており、現行の設定スタイル（`@import "tw-animate-css"` 等）と整合する。
- パッケージ本体を展開すると `src/styles.js`（prose全バリエーションのCSS-in-JS定義）が45,863B。ただしTailwind v4はJITで**実際にHTML中で使用されたクラスだけ**を最終CSSに生成する。README描画では想定使用クラスは `prose`・サイズ修飾（例 `prose-sm`）・`dark:prose-invert` 程度に限られる見込みで、45.9KB全体が出力に載ることはない。
- **見積もり**（実測ではない）: 使用クラスを絞った場合、追加CSSは raw で数KB〜十数KB、gzipで1〜3KB程度。現状の全体CSS（gzip 8.2KB）に対して相対的に小さく、静的アセット総量（928KB）から見ても無視できる増分。
- **実測が必要な理由**: JITの生成結果はマークアップに依存するため、上記は一次情報（npmメタデータ・パッケージソース）からの合理的な見積もりであり、`npm install` して実ビルドしないと確定しない。導入を決めた回のPRで `gzip -c .open-next/assets/_next/static/chunks/*.css | wc -c` の前後比較を記録することを推奨。

### 4. `limits.cpu_ms: 50` への影響

- `wrangler.jsonc` コメント: 「Free では意味を持たないが、Paid へ上げた瞬間に denial-of-wallet 対策として効く」。CSSはNext.jsビルド時に静的ファイルとして書き出され、リクエスト時にWorkerが実行するのはHTML生成（Reactレンダリング）とサニタイズ（`readme-html.ts`）のみ。CSS配信自体はWorkers Static AssetsがWorker実行を経由せず直接返す設計（`INF-10`: 「リクエストは無料・無制限」）。
- したがって**仮説は支持される**: ①②③のどの方式でもCSS自体はcpu_ms消費に寄与しない。唯一CPU時間に乗るのは③（サニタイズ時にユーティリティクラス注入）で `readme-html.ts` の変換パスにクラス文字列の付与処理が追加される点だが、既存のタグ/属性フィルタ処理（cheerio等ベースの1パス変換）に対する追加コストは軽微（文字列結合レベル）と見積もる。cpu_ms観点では①②③に有意差はない。

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

- **どの要素に `overflow-x: auto` を当てるべきか**: `table` 単体と `pre` 単体の**それぞれに** `overflow-x: auto; max-width: 100%; display: block`（またはtableを `<div class="overflow-x-auto">` でラップ）が必要。バッジ画像（`<img>` の連続）はインライン要素として自然に折り返すため追加対策は基本不要。裸URLの長いリンクテキストは `break-words` で概ねカバーされる。
- **①`@tailwindcss/typography` を選んだ場合**: proseの既定CSSは `pre` に `overflow-x: auto` を持つ（Tailwind Typographyの標準仕様）が、**`table` には横スクロールラッパーを付けない既知の制限がある**（v0.5.x系で継続している挙動）。①を採用しても table 対策は**別途**必要になる＝①だけで横溢れ問題が解決するわけではない。
- **②自前スコープCSSを選んだ場合**: `pre`・`table` それぞれに直接ルールを書けるため、むしろシンプルに両方カバーできる。
- **③サニタイズ時にクラス注入を選んだ場合**: `readme-html.ts` の変換パスで `<table>` を `<div class="overflow-x-auto">…</div>` でラップする処理を足せば、CSSセレクタに頼らず構造的に解決できる（他方式より確実だが実装コストは増える）。

→ **性能レンズからの推奨**: 採用方式に関わらず、`table` と `pre` は明示的に `overflow-x: auto` の対象にすることを他レンズ（readme_render / readme_fidelity）に申し送りたい。CSSサイズへの影響はどの案でも数十バイト単位で無視できる。

### 7. `tools/run_lighthouse.mjs` の扱い（詳細ページ: `/ja/repos/octostub/octo-widgets`）

- L14-17のコメント: 「Accessibility = 100 は blocking ゲート、Performance は計測値の記録のみでブロックしない」。実装（L261-273）でも `categories.accessibility.score` のみで `hasGateFail` を判定し、`perfScore` はサマリー出力（`perf=NN`）に載るだけ。
- **個別audit（CLS: `cumulative-layout-shift` 等）はスクリプトが一切参照していない**。README は Suspense で非同期描画される設計（`readme-section.tsx` docコメント: 「README到着時にフォーカスは移動しない（ユーザー操作起因でない後追い描画のため）」）ため、書式適用後にコンテンツの実効高さが変わり、後追い描画によるレイアウトシフトが発生しうる。performance score には畳み込まれるがCIはブロックしない。
- **E2Eスタブ（`e2e/stub/server.mjs` L438）のREADME fixtureが単純すぎる**: `<article><h1>...<p>...<ul>...</ul></article>` のみで、**table・コードブロック・長いURL・バッジ画像を一切含まない**。このため、Lighthouse・E2Eのどちらも今回の横溢れ対策（§6）の回帰を検知できない。

**書式適用後に見るべき指標（推奨・自分では実装しない）**:
1. `result.report.audits['cumulative-layout-shift'].numericValue`（詳細ページ）を手動確認し、README非同期到着によるCLS悪化がないか
2. `tools/run_lighthouse.mjs` は perf非ゲートのままでよいが、**E2Eスタブ側のREADME fixtureに table・長いコードブロック・長いURL・バッジ画像行を追加**し、Playwright側で横スクロール発生（`scrollWidth > clientWidth`）の有無を検証するテストケースを追加することを推奨（担当は readme_render / rev_tests 想定）
3. 静的アセット総量の前後比較（`.open-next/assets` の du -sh）をPR記録に残す

---

## 反対されうる点

- **「見積もり」の精度**: §3のCSS増分見積もりは `npm install` していない一次情報（パッケージメタデータ・ソース展開）からの推定であり、実際にJITでビルドしないと確定しない。導入PRでの実測比較を必須にすべき、という反論はもっとも。
- **cloudflare-infrastructure.md §5.3の計測手順の不備（§2の副次的発見）は、本タスクのスコープ（README書式）と無関係**という指摘はありうる。ただし「3MB上限に対する現在の消費率」を正しく報告するために実測方法を修正した経緯であり、他の参加者が③案などでバンドルサイズを判断材料にする場合に誤った基準を使わないよう申し送りが必要と判断し記載した。
- **table横溢れの「①でも別途対策が必要」という主張**は、Tailwind Typographyの具体的バージョン挙動に依存する。v0.5.20時点のsrc/styles.js中身までは検証したが、実際にレンダリングして確認したわけではない（npm installしていないため）。readme_render/readme_fidelityレンズでの実装時に、最終的に採用したバージョンで実挙動を確認してほしい。
- **cpu_ms影響ゼロという結論**は「CSSファイル配信」に限った話であり、③案（サニタイズ時のクラス注入）が複雑な変換ロジック（正規表現多用等）になった場合はサニタイズ全体のCPU時間が増える可能性がある。今回は「軽微」という定性評価に留まり、実測（`npx wrangler tail --format json`でのcpuTime計測）はしていない。
