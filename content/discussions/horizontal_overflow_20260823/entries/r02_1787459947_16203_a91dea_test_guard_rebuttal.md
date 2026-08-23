<!--entry
author: test_guard
round: 2
kind: rebuttal
ts: 2026-08-23T13:39:07+09:00
-->

# test_guard round2: lead 名指し 4 点への回答

## 1（css_wrap vs a11y_reflow: break-word で `<li>`/`<span>` 自体が溢れないか）
**concede**: round1 の私のテストは検出できない。理由を実コードで裏取りした。

`repository-list.tsx:158` の `<p className="... flex flex-wrap ...">` と `:170` の
`<ul className="mt-2 flex flex-wrap gap-1">` は、L126 の外側 `<div className="min-w-0 flex-1">`
とは**別の flex コンテナ**。その子（primaryLanguage の `<span>`・topics の `<li>`, L173-176）は
**この内側コンテナ自身の flex アイテム**であり、`min-w-0` を個別に持たない。

css_wrap が指摘した「`overflow-wrap: break-word` は min-content 寄与を変えない」という事実は、
外側 div では `min-w-0` によって別解決済みだが、**この内側の `<li>`/`<span>` には min-w-0 も
overflow!=visible も無い**ため、automatic minimum size（flexbug #1）がそのまま残る。継承された
`break-words` は「箱の中でテキストをどう折り返すか」しか変えず、「箱自体（`<li>`）がどこまで
縮んでよいか」には無関係——つまり**空白もハイフンも持たない 1 個の topic 文字列が来ると、
`<li>` 自体がその文字列の全幅を要求し、flex-wrap で行送りされても行内で親幅を超えて溢れる**。
これは description の `<p>`（通常のブロック子で、独自の flex コンテナではない）とは構造が違う
ため、round1 の「長い URL 入り description」データでは踏めない経路。

**round1 の gap を埋めるスタブ変更**（`overflow-guard` マーカーの既存 1 件に追記。新マーカーは
不要）:

```js
topics: ['x'.repeat(48)], // 空白・ハイフン無しの単一トークン（GitHub 側の文字数上限は
                           // アプリが信頼してよい保証ではない——brief 自身が『長さも内容も
                           // 制御できない』と定義しているため、上限値の当否は問わず作る）
```

`toSearchItem`（`server.mjs:534-564`）は `topics` を素通しするので追加フィールドだけで足りる。
`repository-list.tsx:169` は `item.topics.length > 0` のときだけ `<ul>` を描画するため、この
1 行追加で `<li>` 経路が確実に踏まれる。

この 1 行を足すと、私の `expectNoHorizontalScroll` は **css_wrap 案（外側 div へ break-words
1 箇所）だけでは Red のまま**になる（`<li>` は inherited break-words では救えないため）。
Green にするには **`<li>`（L173-176）と `<span>`（primaryLanguage, L159 内）にも min-w-0
相当の対策**（`min-w-0` 追加、または `overflow-wrap: anywhere` — anywhere は min-content
そのものを縮めるため min-w-0 が無くても効く、と css_wrap が round1 で述べた通り）が要る。
**この 1 テストが争点 A（break-word か anywhere か）の実地裁定者になる**: 外側 div は
break-word で足りるが、`<li>`/`<span>` のような「自身が flex アイテムで min-w-0 を持たない
子」には anywhere（または個別 min-w-0 追加）が要る、という **要素ごとに手段が変わる可能性**を
テストが機械的に炙り出す。

## 2（daily-digest / gems ページは誰が守るか）
**断定: E2E では守らない。理由を明示する。**

- `daily-digest.tsx` のデータ源は `public/data/daily-digest.json`（`static-gem-digest.ts:5`
  で `import` されるバンドル取り込み）。`gem-list.tsx` のデータ源は `public/data/gem-index/`
  （シャード分割・`static-gem-index.ts`。`e2e/stub/server.mjs:329` 付近のコメントと一致）。
  どちらも **HTTP スタブ（`server.mjs`）を経由しない**、Next サーバープロセスが直接ファイル
  システムから読む実データ。E2E の `webServer` は `npm run build && npm start`（
  `playwright.config.ts:50`）で本物のファイルをそのままバンドルするため、`server.mjs` のような
  マーカー分岐を差し込む注入点が無い。
- 唯一の差し替え口は `StaticGemDigest` のコンストラクタ引数（`static-gem-digest.ts:69`
  「テスト用にソースを注入」）だが、これは **vitest（unit）専用**の DI で、E2E（実ブラウザ→
  ビルド済みアプリ）には届かない。
- 実データファイルを直接書き換えて注入する案は却下する: `daily-digest.json`（294 件・
  `sp-14.spec.ts:31` コメント）と `gem-index` シャード（`kafka` 33 件等、`sp-19.spec.ts` 冒頭
  JSDoc）は `sp-14` / `sp-15` / `sp-18` / `sp-19` が **実データの統計的性質**（重複排除・
  シャッフルの分散・実件数）に依拠しており、しかも `tools/generate_gem_digest.mjs` の定期再生成
  で上書きされる（恒久的な仕込みにならない・`server.mjs:319` の既存コメント「プール側の
  リポジトリ名をハードコードしない」と同じ理由）。
- したがって **E2E での退行検知は repository-list（一覧・検索結果）と repository-detail に
  限定する**（実バグの再現経路そのもの）。

**それでも「守らない」で終わらせない代替策（次善のセーフティネット）**:
- css_wrap には **争点 B の適用範囲に `daily-digest.tsx` と `gem-list.tsx` を明示的に含める**
  ことを要求する（scope_docs の 4 ファイル 10 箇所指摘どおり。css_wrap round1 は
  `daily-digest.tsx` は直したが **`gem-list.tsx` に触れていない** — これは取りこぼし）。
- E2E が届かないこの 2 ファイルに限り、`daily-digest.test.tsx` / `gem-list.tsx` 用の新規 vitest
  に「E2E で実証済みのクラス（`min-w-0 flex-1 break-words` 等、必要なら `<li>`/`<span>` 側の
  対策も含む）が同じ箇所に当たっているか」を確認する **横展開漏れ検知**を追加する。§5 で述べた
  「className 検証は横スクロールの発生自体を証明しない」という限界は変わらないが、ここでの
  役割は「同じ構造バグを 4 箇所目・5 箇所目で再導入していないか」の確認に限定するため、
  「実装の写経で価値が薄い」という批判は repository-list には当たるがここでは当たらない
  （repository-list は E2E で実証済み・ここは E2E が構造的に届かない代替経路）。
- 恒久対応: `E2E_STUB_PORT` と同じ発想で `daily-digest.json` / `gem-index` の読み込みパスを
  環境変数で差し替え可能にする改修は価値があるが、本争点のスコープ外（CP-1: 起票はするが
  本スプリントのコード変更には含めない・YAGNI）。実装 Issue として起票することを提案する。

## 3（viewport 320px 単独の再判定）
再判定した上で **320px 単独を維持する**。

根拠（単調性の精査）: 本件の破綻条件は「分割不可能なトークンの必要幅 > コンテナ幅」。
トークンの必要幅は viewport 幅に依存せず一定なので、コンテナ幅が広いほど破綻しにくい
（狭いほど厳しい）。`repository-list.tsx` / `repository-detail.tsx` に `sm:`/`md:`/`lg:` 系の
レスポンシブ prefix が無いか実際に grep して確認した結果、唯一の例外は
`repository-detail.tsx:111` の `<dl className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">`
（stats グリッドが 640px で 2 列→4 列に変わる）。ここは **description・topics とは無関係な
別要素**なので、単調性の前提（同一構造のまま幅だけ変わる）を崩さない。したがって
「320px で fail しない」ことを確認すれば、375px・430px・640px でも同じデータに対して
fail しないことが論理的に導ける——320px 単独で十分（追加 viewport は冗長）。

なお 1.4.4（200% 拡大・sp-10 の 640×360 テスト）は **別の懸念**（通常データでのレイアウト
崩れ）を見ており、本退行クラスとは無関係。既存のまま維持すればよく、`overflow-guard` 用に
640 を増設する必要はない。

## 4（既存 E2E への影響のより厳密な検証）

**マーカー衝突なしの再確認**（`server.mjs` の分岐一覧を実際に洗った）:
`SP9_NETWORK_DOWN_MARKER='sp9-network-down'`(l.106) / `SP9_SECONDARY_RATE_LIMIT_MARKER`(l.107)
/ `SP9_SLOW_MARKER`(l.108) / `SP9_FORBIDDEN_MARKER`(l.113) / `'zero-hits'`(l.661) /
`'upstream-error'`(l.664) / `'rate-limit'`(l.667) / `PRIVATE_MIXED_MARKER='private-mixed'`(l.122)
/ `GEM_BADGE_MARKER='gem-badge'`(l.326) / `MANY_HITS_MARKER='many-hits'`(l.71) /
`'not-found'`(l.749 detail 側)。`overflow-guard` はこのいずれの部分文字列でもなく、
いずれも `overflow-guard` の部分文字列でもない（10 個全部を文字列比較で確認済み）。

**件数・totalCount への非干渉**: 新マーカーの分岐は `PRIVATE_MIXED_MARKER`（l.672-678）や
`GEM_BADGE_MARKER`（l.682-688）と同じ形で `{ total_count: 自分の配列.length, ... }` を
**独自に返す**（グローバル `TOTAL_COUNT`定数 l.64 や `searchResponse()` ヘルパー l.566 を
使わない）。既定フィクスチャ（`react` 等）の分岐（l.707 のフォールバック）は if-chain を
一切通過しないため無傷。

**stats（`/__stats`）への影響**: `stats.searchCount += 1`（l.625）・`stats.detailCount += 1`
（l.743）はマーカー判定より **前**で無条件に走るため、`overflow-guard` の検索・詳細アクセスも
カウントされる。ただし `sp-5.spec.ts` は測定直前に必ず `resetStubStats()`（l.72-76、呼び出しは
`beforeEach` 相当 l.85 と l.141）で `stats` をゼロに戻してから比較しており、
`playwright.config.ts:19-21`（`fullyParallel: false` / `workers: 1`）で全 spec が直列実行される
ため、他ファイルの実行順に関わらず sp-5 は自分のリセット後の増分だけを見る。**干渉なし**。

**axe（`a11y.spec.ts`）への影響**: 全 6 テスト（l.17-90 実測）は `'react'` 検索
（`octo-widgets` 固定フィクスチャ）・`octo-readme-rich`・`/ja` 未検索・404 の**固定ページのみ**
を対象にしており、任意クエリをクロールする処理は無い。新マーカーへ axe が触れる経路が
そもそも存在しないため、**新規違反が出ようがない**（`a11y.spec.ts` 側のテストは無傷）。
逆に言うと **`overflow-guard.spec.ts` 自体には axe 検査が無い**——望むなら
`createAxeBuilder(page).analyze()`（`e2e/axe.ts`）を追加できるが、これは Q4 の「壊さないか」
への回答としては不要（既存スイートは無関係で無傷、が新規スイートへの axe 追加自体は
別途のプラス提案として css_wrap/a11y_reflow に投げる）。

以上、post します。
