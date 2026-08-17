# UI/UX 技術スタック・実装ノウハウ リサーチ（2026-08-17 JST）

- **目的**: MVP 時点で正式リリースと遜色ない UI/UX を成立させるための、本リポジトリ構成に適合した技術選定材料とベストプラクティスを集める
- **位置づけ**: 調査記録。**実装で参照する指針は [`ui-ux-guidelines.md`](./ui-ux-guidelines.md) が正本**（本ファイルはその根拠）
- **関連 Issue**: #16

---

## 0. このドキュメントの読み方

🔴 **「確認済み」と「未確認」を厳密に分けている。** 一次情報（公式ドキュメント・W3C・NN/g 等）で確認できたものだけを断定し、二次情報どまり・推論のものは **⚠️ 未確認** と明記した。実装着手時に未確認項目を先に潰すこと。

調査は 4 観点を並列で実施した（① UI 技術スタック ② アクセシビリティ実装 ③ Core Web Vitals ④ 検索系 UI の UX）。既存の [Next.js 16 アーキテクチャ調査](../architecture/20260817-nextjs16-architecture-research.md) と重複する範囲は扱わず、**UI 層の差分に絞っている**。

---

## 1. UI 技術スタック

### 1.1. 🔴 最重要の発見: shadcn/ui の既定プリミティブが Radix UI → Base UI に切り替わった

**2026-07 の公式アナウンス** で、shadcn/ui の新規プロジェクト既定が Radix UI から **Base UI** になった（出典: [shadcn/ui changelog 2026-07](https://ui.shadcn.com/docs/changelog/2026-07-base-ui-default)）。Radix は非推奨化されておらず、`npx shadcn init -b radix` で従来の Radix 版を選べる。両者は同じ開発チーム（Radix 作者）による設計。

| 項目 | Radix UI | Base UI |
|---|---|---|
| アクセシビリティ保証の **一次情報** | ✅ **ある** — WAI-ARIA Authoring Practices 準拠、NVDA / JAWS / VoiceOver でテスト済みと公式が明記（出典: [Radix Accessibility](https://www.radix-ui.com/primitives/docs/overview/accessibility)） | ⚠️ **未確認** — shadcn 公式アナウンス本文には「Radix での学びを反映した」との記述のみで、アクセシビリティを直接保証する文言は確認できなかった |
| shadcn/ui での位置づけ | 選択可（`-b radix`） | 既定 |
| RTL / CSP 対応 | — | ⚠️ 未確認（第三者記事のみ） |

🔵 **本プロジェクトの判断**: **Radix を明示指定する**。理由は [ADR 0001](../../adr/0001-ui-stack.md) に記録。要旨は「`Lighthouse Accessibility = 100` を CI ゲートにする（`NFR-27`）以上、アクセシビリティ保証が **一次情報で明文化されている** 側を選ぶ」。既定に逆らう選択なので ADR で理由を残す。

### 1.2. Tailwind CSS v4（確認済み）

- 現行メジャーは **v4**。Next.js への導入は `tailwindcss` + `@tailwindcss/postcss` + `postcss` を入れ、`postcss.config.mjs` にプラグインを 1 行書き、CSS 側で `@import "tailwindcss";` するだけ（出典: [Tailwind: Next.js guide](https://tailwindcss.com/docs/installation/framework-guides/nextjs)）
- 🔵 **`tailwind.config.js` は不要**（v4 は CSS-first 設定）。カスタムトークンは CSS 内の `@theme { --color-...: ...; }` で定義する（出典: [Tailwind: Theme](https://tailwindcss.com/docs/theme)）
- v4 では JS 設定ファイルが自動検出されなくなり、必要な場合のみ `@config` で明示読み込み。`corePlugins` / `safelist` / `separator` は非対応（`safelist` は `@source inline()` に置換）（出典: [Tailwind: Upgrade guide](https://tailwindcss.com/docs/upgrade-guide)）
- **ランタイム JS はゼロ**（ビルド時に静的生成）。`NFR-28`（バンドルサイズ）に対して有利

⚠️ **未確認**: 正確な最新パッチバージョン番号（二次情報で v4.3.0 との記載を見たが公式リリースノートで裏取りできていない）。

### 1.3. shadcn/ui の RSC 適合性（確認済み）

- `components.json` の `"rsc": true|false` で、CLI が生成物に `"use client"` を自動付与するかを制御できる（出典: [shadcn: components.json](https://ui.shadcn.com/docs/components-json)）
- 🔵 **コード生成方式**（`node_modules` に隠れず自分のリポジトリにファイルとして残る）のため、**`use client` 境界を PR レビューで目視確認・調整できる**。`NFR-3`（`use client` をインタラクション箇所に限定）を機械的に守れる
- 未使用コンポーネントを持ち込まないため、ライブラリ全体の import コストが発生しない

⚠️ **未確認**: ① shadcn 公式ドキュメントは主対象を **Next.js 15 + React 19** として書かれており、**Next.js 16 固有の互換性表明は公式本文から確認できなかった**（二次情報では「16/15 両対応」との記載）② コンポーネントごとの `use client` 要否の網羅的一覧（実際に `shadcn add` して確認が必要）③ ライブラリ有無によるバンドルサイズの定量差分（KB 実測値）

### 1.4. テーマ切替（確認済み）

- `next-themes` は App Router 対応。`<html suppressHydrationWarning>` + `<ThemeProvider>` の 2 点構成が定石（出典: [next-themes](https://github.com/pacocoursey/next-themes)）
- `ThemeProvider` は `localStorage` / `matchMedia` に依存するため Client Component 必須だが、**RSC ツリー最上位に 1 箇所置くだけで配下の Server Components に影響しない** → `NFR-3` と両立
- 開発モードでは一瞬フラッシュしうるが **本番ビルドでは解消される** と公式が明記
- テーマ状態は `localStorage` に載るため、本プロジェクトの状態方針（`prd.md` §2.4）とそのまま整合

### 1.5. フォント（確認済み）

- `next/font` は Google Fonts をビルド時に **自己ホスト化** し、ブラウザから Google への外部リクエストを発生させない（出典: [Next.js: Fonts](https://nextjs.org/docs/app/getting-started/fonts)）
- フォールバックフォントに `size-adjust` を自動適用して CLS を抑える。可変フォント推奨（1 ファイルで全ウェイト）
- 🔴 **`display` の選択が CLS に直結する**: `swap`（既定）は即座にフォールバック表示 → 差し替えでシフトが起きやすい。**`optional` はネットワークが遅い場合にカスタムフォントを完全にスキップ** してフォールバック確定にするため、シフトのリスクが最小（出典: [Vercel: next/font](https://vercel.com/blog/nextjs-next-font)）

---

## 2. アクセシビリティ実装（WCAG 2.2 AA + Lighthouse 100）

### 2.1. 🔴 Lighthouse Accessibility 100 は AA 達成を意味しない（確認済み）

- Lighthouse の a11y カテゴリは **axe-core の全ルール（約 96）のうち約 50 ルールのみ** を実行するサブセット（出典: [unlighthouse: accessibility](https://unlighthouse.dev/learn-lighthouse/accessibility) / [GoogleChrome/lighthouse#15215](https://github.com/GoogleChrome/lighthouse/issues/15215)）
- 自動ツールが検出できる WCAG 違反は **全体の 30〜40% 程度** という指摘が複数の実務情報で一致（出典: [AFixt](https://afixt.com/why-your-lighthouse-score-of-100-means-almost-nothing/) / [BOIA](https://www.boia.org/blog/why-google-lighthouse-scores-arent-useful-for-evaluating-accessibility)）

🔵 **含意**: `prd.md` の `NFR-10` が「**完全準拠とは名乗らない**」「自動検証可能な範囲を CI で担保し、残りは手動チェックリスト」としているのは、この事実と整合している。**手動チェックリストが本質** であり、Lighthouse 100 は下限にすぎない。

### 2.2. WCAG 2.2 の新規基準のうち本アプリに効くもの（確認済み）

| 基準 | 本アプリでの意味 |
|---|---|
| **2.4.11 Focus Not Obscured (AA)** | sticky ヘッダーを置くなら、フォーカス移動先に `scroll-margin-top` をヘッダー高さ分設定して隠れないようにする（出典: [W3C Understanding 2.4.11](https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum.html)） |
| **2.5.8 Target Size (Minimum・AA)** | ページネーションのページ番号、カード内のアイコンのみのコントロールは **24×24 CSS px 以上**、または隣接ターゲットと間隔を確保。テキスト内リンクは対象外（inline exception）（出典: [WCAG 2.2](https://www.w3.org/TR/WCAG22/)） |
| **3.3.7 Redundant Entry (A)** | 詳細 → 一覧復帰で検索条件を再入力させない。**`AC-6` / `NFR-2`（URL 状態）が既にこれを満たす設計になっている** |
| **3.2.6 Consistent Help (A)** | 🔵 **該当なし**（ヘルプ・問い合わせ導線は要件に存在しない）。将来追加する場合は共有 `layout.tsx` に置いて相対位置を固定する |
| **2.5.7 Dragging Movements (AA)** | 🔵 **該当なし**（ドラッグ操作を持たない） |
| **3.3.8 Accessible Authentication (AA)** | 🔵 **構造的に満たしやすい** — `AR-5` のログインは **GitHub OAuth への委任** であり、自前のパスワード入力・認知機能テストが存在しない |

### 2.3. 🔴 Next.js 固有の落とし穴: ルート変更が支援技術にアナウンスされない（確認済み）

Next.js の `next-route-announcer` は **document title が変化しないと何もアナウンスしない** 既知の問題がある（出典: [vercel/next.js#86660](https://github.com/vercel/next.js/issues/86660)）。

🔵 **本アプリは直撃する**: ページ送り・ソート切替・件数切替はいずれも `searchParams` だけが変わり、title は変わらない設計になる（`NFR-2`）。**遷移後に結果見出しへ明示的にフォーカスを移す実装が必須**（`tabIndex={-1}` を付けた見出しへ `focus()`）。これがないと `AC-8`（状態変化を支援技術に伝える）を満たせない。

### 2.4. `aria-live` の実装（確認済み）

- 結果件数の通知は **`role="status"`**（暗黙で `aria-live="polite"` + `aria-atomic="true"`）を使う
- 🔴 **`role="alert"` と明示 `aria-live="assertive"` を同時に付けない** — iOS VoiceOver で二重読み上げになる（出典: [MDN: ARIA live regions](https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Guides/Live_regions) / [W3C ARIA22](https://www.w3.org/WAI/WCAG21/Techniques/aria/ARIA22)）
- ライブリージョンは **初期 DOM に空で常設** し、後から中身を書き換える（要素ごと動的挿入しない）

### 2.5. カード全体をクリック可能にする（確認済み）

- 🔴 **カード全文を `<a>` で包まない** — スクリーンリーダーが長い文字列を全部読み上げてから「リンク」と告げることになる
- 正しいパターン: **リポジトリ名（見出し）だけを `<a>` にし、`::after` 疑似要素に `position:absolute; inset:0` を張ってクリック領域をカード全体へ拡張する**（出典: [Adrian Roselli: Block Links, Cards, Clickable Regions](https://adrianroselli.com/2020/02/block-links-cards-clickable-regions-etc.html) / [Nomensa](https://www.nomensa.com/blog/how-build-accessible-cards-block-links/)）
- カード内に二次リンクを置く場合は `position:relative` + `z-index` で疑似要素の上に出す
- ⚠️ トレードオフ: **カード内テキストのドラッグ選択がしづらくなる**

### 2.6. その他（確認済み）

- **フォーカス可視性**: `:focus` ではなく `:focus-visible` を使う。`outline-none` は必ず `focus-visible:ring-*` と対で書く。2.4.13 Focus Appearance は AAA なので必須ではないが、品質目標としてリングのコントラスト 3:1 以上・太さ 2px 相当を満たす
- **アバターの alt**: オーナー名がテキストとして隣接表示される文脈では **`alt=""`（スペースなしの空文字）を明示指定** する。属性の省略はしない（ファイル名を読み上げる SR がある）（出典: [W3C WAI: Decorative Images](https://w3c.github.io/wai-tutorial-images/tutorials/images/decorative/)）
- **ページネーション**: `<nav aria-label="...">` でラップし、現在ページに `aria-current="page"` を付与

⚠️ **未確認**: axe-core の `wcag22aa` タグが旧バージョンの AA ルールを再包含するのか新規ルールのみを指すのかは推論どまり。`@axe-core/playwright` で `.withTags([...])` を書く前に [axe-core API.md](https://github.com/dequelabs/axe-core/blob/develop/doc/API.md) で確認が必要（調査時は 403 で直接取得できなかった）。

---

## 3. Core Web Vitals

### 3.1. LCP（確認済み）

- Next.js 16 では `params` / `searchParams` が **Promise** 化されている。トップレベルで `await` すると配下全体が dynamic 化して prerender 不可になるため、**実際にデータを使うコンポーネントまで `await` を遅延させる**（出典: [Next.js: Streaming](https://nextjs.org/docs/app/guides/streaming)）
- `loading.tsx` は route segment に置くだけで自動的に Suspense boundary としてラップされる（出典: [Next.js: loading.js](https://nextjs.org/docs/app/api-reference/file-conventions/loading)）
- 🔴 **LCP 対象要素（見出し・最初の結果カード）を、遅いデータに依存する Suspense 配下に置かない**

### 3.2. INP（確認済み）

- Client Component は JS 出力と hydration コストを増やし、hydration はメインスレッドを占有して INP を悪化させる（出典: [This Dot Labs](https://www.thisdot.co/blog/improving-inp-in-react-and-next-js)）
- 🔵 **ソート切替・件数切替・ページ送りは URL 変更 + Server Component 再フェッチで実装する**（クライアント状態を持たない）。`use client` が必要なのは検索入力欄と各コントロールのトリガーに限られる

⚠️ **未確認**: `useTransition` が INP に与える具体的効果を明記した一次情報（web.dev / Next.js 公式）は見つからず、二次情報どまり。

### 3.3. CLS（確認済み）

- 画像は `width` / `height`（intrinsic size）を必須指定してアスペクト比をブラウザに伝える。`fill` を使う場合は親に `position: relative` 等が必須で、**`sizes` を必ず指定する**（未指定だと `100vw` 前提で過大な画像を落とす）（出典: [Next.js: Image](https://nextjs.org/docs/app/api-reference/components/image)）
- スケルトンは **実データと同一寸法** にする。Suspense boundary の周囲に `min-height` でスペースを先に確保する
- フォントは `next/font` の `display: 'optional'` を優先検討（§1.5）

⚠️ **未確認**: 可変長テキスト（リポジトリ説明文）の CLS 対策として `line-clamp` で行数を固定する手法は、Next.js / web.dev が明示的に推奨しているかは確認できなかった（設計として妥当と判断してガイドラインに採用する）。

### 3.4. GitHub アバターの最適化（確認済み）

- `next.config` の `images.remotePatterns` に `avatars.githubusercontent.com` を **`protocol: 'https'` を明示して** 追加する
- 🔴 **`protocol` / `hostname` 以外を省略してワイルドカード任せにしない** — 公式が非推奨と明記（意図しない URL まで最適化対象になりうる）（出典: [Next.js: Image](https://nextjs.org/docs/app/api-reference/components/image)）
- Vercel 環境では画像最適化に費用が発生するため、`remotePatterns` の限定はコスト面でも有効（出典: [Vercel: Managing Image Optimization Costs](https://vercel.com/docs/image-optimization/managing-image-optimization-costs)）

### 3.5. 一覧 ↔ 詳細の体感（確認済み）

- `<Link>` は viewport 進入で自動プリフェッチ（static は全体、dynamic は `loading.js` があればそこまで）。**スクロール位置は標準で維持される**（出典: [Next.js: Prefetching](https://nextjs.org/docs/app/guides/prefetching)）
- 🔵 **標準挙動に任せるのが正解**。独自のプリフェッチ制御を書かない
- ⚠️ **View Transitions は実験的扱い**（`experimental.viewTransition` フラグ / React `unstable_ViewTransition`）。**本番運用の推奨は一次情報上まだない** → MVP では使わない

### 3.6. Lighthouse CI の安定化（確認済み）

- 公式サンプルは **`numberOfRuns: 5`** + simulated throttling（既定）。中央値または optimistic 集計で閾値判定（出典: [Lighthouse CI Configuration](https://googlechrome.github.io/lighthouse-ci/docs/configuration.html)）
- スコアの分散は CI ランナーの性能変動が主因。専有ランナー（最低 2 core / 4GB）で分散が減る（出典: [Lighthouse variability](https://developers.google.com/web/tools/lighthouse/variability)）
- これは `prd.md` `NFR-27` の注記（本番相当ビルド・複数回実行の中央値・スロットリング固定）と整合する

⚠️ **未確認**: `@next/bundle-analyzer` は Next.js 16.1 以降で公式パッケージとして提供されると確認したが、**CI でバンドルサイズ予算を強制する具体手順**（`size-limit` 統合等）は公式ドキュメントで確認できず、コミュニティ情報どまり。

---

## 4. 検索系 UI の UX

### 4.1. 実在プロダクトの比較

| プロダクト | 採る | 採らない |
|---|---|---|
| **GitHub 検索結果**（実機確認済み・[検索結果ページ](https://github.com/search?q=react&type=repositories)） | **カード内の情報順序**（名前 → 説明 → topics → 言語/star/更新日）/ 上部のソートドロップダウン / 結果総数の明示 | 多種別タブ（Code / Issues / Users）— 本アプリはリポジトリのみ |
| **GOV.UK / MOJ Design System**（実機確認済み） | **ページネーションの件数明示**（"Showing 26 to 50 of 157 total results"・出典: [MOJ: Pagination](https://design-patterns.service.justice.gov.uk/components/pagination/)）/ **エラー文言の規則**（出典: [GOV.UK: Error message](https://design-system.service.gov.uk/components/error-message/)） | 複雑なフォームバリデーション — 本アプリの検索フォームは単純 |
| **Shopify Polaris**（実機確認済み） | **検索 0 件を専用状態（`emptySearchState`）として初期状態と区別する** 設計（出典: [Polaris: Resource List](https://polaris-react.shopify.com/components/lists/resource-list)） | リソースリストの一括操作 UI |
| **OSS Insight** | 軽量なチップ/ドロップダウンでのフィルタ配置 | 高度なデータ可視化（Phase 1 のスコープ外） |
| **npm / Libraries.io** | — | ⚠️ **実機確認できず**（403 / ログイン壁）。参照材料として使わない |

### 4.2. カードの情報設計（`R-10` のクローズ根拠）

GitHub 検索結果の実機構造をベースラインに採る。NN/g は、ユーザーが検索結果を **非線形（"pinball" パターン）にスキャン** するため、強いタイポグラフィコントラストが視認性を左右すると指摘している（出典: [NN/g: Ecommerce Search UX](https://www.nngroup.com/reports/ecommerce-ux-search-including-faceted-search/)）。

| 優先度 | 要素 | 扱い |
|---|---|---|
| 主役 | リポジトリ名（+ オーナーアイコン） | 最大フォント・太字。**省略しない** |
| 準主役 | 説明文 | `line-clamp: 2` で 2 行固定 + `min-height` で欄自体の高さを確保（有無・長さでカード高さが暴れないようにする） |
| タグ | topics | 説明文の下。折返し許容、多すぎる場合は `+N` |
| メタ | 言語 / star 数 / 最終更新日 | 小フォント・低コントラスト（ただし 4.5:1 は死守）。**アイコンだけにせず明示ラベルを添える**（言語間で意味が伝わらないため） |

🔵 **日時は絶対表記を基本にする**（相対表記 "3 days ago" は i18n とタイムゾーン誤解のリスクがある）。

### 4.3. 状態表現（確認済み）

- 🔴 **「未検索の初期状態」と「0 件」は別物として設計する**（出典: [NN/g: Empty States](https://www.nngroup.com/articles/empty-state-interface-design/)）
  - 初期状態 = **教育的**（何ができるか + 始め方）
  - 0 件 = **システム状態の確認**（何に対して 0 件か + 次の手）
- **ローディングの使い分け**（出典: [NN/g: Skeleton Screens vs. Progress Bars vs. Spinners](https://www.nngroup.com/videos/skeleton-screens-vs-progress-bars-vs-spinners/)）
  - 0〜300ms: 何も出さない（ちらつき防止）
  - 300ms〜1s: 軽いスピナー可
  - 1s 以上でレイアウトが既知: **スケルトン**
  - 🔵 本アプリのカード一覧はレイアウトが既知なので **カード形状のスケルトン** が適合
- **エラー文言**（出典: [GOV.UK: Error message](https://design-system.service.gov.uk/components/error-message/)）
  - 「**何が起きたか + どう直すか**」を書く
  - 「sorry」「oops」「invalid」等の曖昧・謝罪表現を使わない
  - `prd.md` §7 の 3 種（通信失敗 / レート制限 / クエリ不正）は文言を分ける。レート制限は `x-ratelimit-reset` から復帰時刻を出す

### 4.4. i18n レイアウト耐性（確認済み）

- 固定幅を避け `min-width` + padding、Flex/Grid で可変対応。**ボタン内テキストに `white-space: nowrap` を使わない**
- 🔵 **ソート切替・件数切替は固定幅のセグメントコントロールにしない**（「関連度」vs "Best match" のように日英で長さが大きく変わる）。ドロップダウンか可変幅にする
- 文字列膨張のテストにはドイツ語・フィンランド語が使われる（英語比 30〜50% 長くなる）（出典: [Phrase: i18n real-world challenges](https://phrase.com/blog/posts/internationalization-beyond-code-a-developers-guide-to-real-world-language-challenges/)）

### 4.5. 「作り込んで見える」低コストな差分

- **タイポグラフィスケール**（例: 12/14/16/20/24px）と **スペーシングリズム**（4px または 8px グリッド）を先に決めて使い回すだけで統一感が出る
- **カラートークンを最小セット**（テキスト / 背景 / ボーダー / アクセント / エラー）に絞り、最初からライト・ダーク両対応にする

⚠️ **未確認**: 上記 2 点は実務解説記事レベルの情報が中心で、厳密な一次情報での裏取りはしていない（設計判断として採用する）。

⚠️ **未確認**: ページネーションで取得上限（1,000 件）に達したときの UI 文言について、NN/g 等の一次ガイドラインは見つからなかった。

---

## 5. 未確認項目の一覧（実装着手時に潰す）

| # | 未確認事項 | いつ潰すか | 影響 |
|---|---|---|---|
| 1 | shadcn/ui の **Next.js 16 固有の互換性表明**（公式本文は Next.js 15 が主対象） | `SP-1` の依存導入時に実機で確認 | 大（採用可否） |
| 2 | Base UI のアクセシビリティ保証の一次情報 | — （**Radix を選ぶ判断で回避済み**・[ADR 0001](../../adr/0001-ui-stack.md)） | 回避済み |
| 3 | shadcn/ui コンポーネントごとの `use client` 要否 | `SP-1`（`shadcn add` して実物を確認） | 中（`NFR-3`） |
| 4 | axe-core の `wcag22aa` タグの意味（旧 AA を含むか） | `SP-10`（`E-13`）で `axe-core` の API ドキュメントを確認 | 中（a11y 検証の網羅性） |
| 5 | CI でのバンドルサイズ予算の強制手順 | `SP-12` 以降（`E-20`・ゲート化は必須ではない） | 小 |
| 6 | `useTransition` と INP の関係の一次情報 | 必要になった時点 | 小 |
| 7 | Tailwind v4 の正確な最新パッチ版 | `SP-1` の導入時に `npm view` で確認 | 小 |
| 8 | 取得上限到達時の UI 文言の一次ガイドライン | — （見つからないため設計判断で決める・ガイドライン §5） | 小 |

---

## 6. 参照

| ドキュメント | 関係 |
|---|---|
| [`ui-ux-guidelines.md`](./ui-ux-guidelines.md) | **本調査を実装指針に落としたもの（実装時はこちらを読む）** |
| [ADR 0001: UI スタック](../../adr/0001-ui-stack.md) | `TR-5` の決定と、shadcn/ui 既定に逆らって Radix を選んだ理由 |
| [`prd.md`](../../02_requirements/prd.md) | 要件の正本（`TR-5` / `NFR-1`〜`NFR-15` / `NFR-26`〜`NFR-28`） |
| [Next.js 16 アーキテクチャ調査](../architecture/20260817-nextjs16-architecture-research.md) | データ層・キャッシュ・レンダリング戦略（本調査は UI 層の差分に限定） |
| [`user-story-map.md`](../../02_requirements/user-story-map.md) | `E-9`（配色）/ `E-13`（a11y）/ `E-15`（キーボード）等の実装単位 |
