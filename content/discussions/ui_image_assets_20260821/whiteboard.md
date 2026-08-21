<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: gem-hunter のテキスト主体 UI を gpt-image-2 生成のビジュアルで補強し、ヘッダーを共通化して言語切替を右上へ移す

- 議題ID: `ui_image_assets_20260821`
- 論点: ユーザー指示（Issue #347）: (1) OpenAI gpt-image-2 でツールアイコン・タイトル・待ち受け（未検索）表示・検索結果 0 件など『いまテキストで伝えている箇所』を画像化してユーザビリティを上げたい。最新の UI/UX トレンド・ベストプラクティスを踏まえること。(2) 言語ごとに画像を使い分けることも検討する。(3) イメージだけで表現できるならそれでもよい。(4) 言語設定は頻繁に触れないので画面右上などへ移動を検討。(5) 一覧と詳細でヘッダーレイアウトを共通化。

現状の実装事実: 共有ヘッダーは app/[locale]/layout.tsx にあり `h1 > Link(/{locale})` のツールタイトルと LoginLink だけを持つ（Issue #334 F-1/F-2 で新設）。LocaleSwitcher は各ページ本文（app/[locale]/page.tsx と repos/[owner]/[repo]/page.tsx のエラー分岐・成功パス）に個別に置かれており、`currentPath`（クエリ込みの現在 URL）を props で受けて ja/en のリンクを組み立てる（buildLocaleUrl）。詳細ページの not-found.tsx には LocaleSwitcher が無い。未検索状態はダイジェスト（DailyDigest）+ 検索フォームのみで、旧 idle 文言は Issue #337 で撤去済み。0 件は RepositoryList が `role=status` のテキスト 1 行。読み込み中は LoadingIndicator のテキスト 1 行（スケルトン化は #169 で未対応）。エラーは ErrorNotice（role=alert・枠線 + テキスト）。favicon は app/favicon.ico のみで OG 画像は無い。

制約: docs/03_design/ui-ux/ui-ux-guidelines.md（§2 デザイントークン・§2.4 コントロールサイズ・§3 i18n 耐性で固定幅と nowrap 禁止・§4.4 4 状態の描き分けとレイアウトシフト禁止・§7.0 h1 は共有ヘッダー 1 箇所のみ・§7.4 画像の alt 方針）/ NFR-10 WCAG 2.2 AA・Lighthouse Accessibility 100 が品質ゲート / NFR-1 Lighthouse Performance 90 以上・LCP 2.5s / NFR-3 クライアント JS 最小（use client は入力欄とコントロールのトリガーだけ）/ INF-11 next/image の最適化は使わない（生 <img>）/ NFR-21 事業者固有機能をアプリコードへ持ち込まない / Cloudflare Workers 配信でバンドル・静的アセットのサイズが効く / 既存 E2E（e2e/sp-8-locale.spec.ts・sp-9-loading-empty.spec.ts・feedback-334.spec.ts・a11y.spec.ts 等）と tools/run_checks.sh（check_ui_dimensions.py / check_contrast.py / lighthouse）が回帰を検知する / 既存の画像生成基盤は tools/infographic/generate.py（gpt-image-2・PNG・サイズは 16 の倍数）と to_webp.mjs。

争点は少なくとも次の 5 つ: A) 画像を入れる箇所と優先順位（アプリアイコン/ロゴマーク・favicon・OG 画像・未検索の待ち受け・0 件・エラー・読み込み中スケルトン・詳細の README 不在・404 のうち、どれをやり、どれをやらないか。『画像を足すと逆に遅く・うるさくなる』側の反論を必ず出すこと）B) 画像内に文字を焼き込むか（焼き込むなら言語別に 2 枚要る。WCAG 1.4.5 Images of Text・拡大時の劣化・文言変更の追随コスト・gpt-image-2 の日本語描画品質と、『言語ごとに使い分ける』というユーザー指示をどう満たすかを突き合わせる。文字なし 1 枚 + テキスト併記で指示を満たしたと言えるのか、それとも言語別に色/構図を変える別の満たし方があるのか）C) アセットの形式・生成・配信（gpt-image-2 の PNG をそのまま置くか WebP/AVIF 化するか・SVG へトレースするか・寸法と枚数の上限・ライト/ダークテーマ両対応をどう作るか・生成物をリポジトリにコミットするか・再現手順をどこに置くか・CLS を出さない実装）D) ヘッダー共通化と言語切替の右上移設の具体形（LocaleSwitcher を layout.tsx へ移すと currentPath をどう得るか＝サーバーコンポーネントで現在 URL を持たない問題、クエリ保持の要件をどう満たすか、ロゴ + タイトル + 言語 + ログインの並び、モバイルでの折返し、not-found.tsx への波及、既存 E2E の書き換え範囲）E) a11y と機械ゲート（装飾画像 alt="" と意味を持つ画像の代替テキストの線引き・aria-live 領域の中に画像を置いてよいか・prefers-reduced-motion・Lighthouse 100 を割らない条件・追加すべき E2E と単体テスト）。
- 参加者: `ux_visual`, `a11y_i18n`, `perf_asset`, `frontend_arch`, `docs_trace`
- 投稿数: 5
- 更新: 2026-08-21T18:29:49+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

## ラウンド 1

### `ux_visual` — 主張
<sub>2026-08-21T18:26:33+09:00</sub>

# ux_visual r1 — ビジュアル資産の要否判定（Issue #347）

## 前提として観測したこと

- 現行の「未検索」状態は **既にテキストの穴埋めではない**（`app/[locale]/page.tsx` 297-335 行 / `docs/03_design/ui-ux/ui-ux-guidelines.md` §4.4 の改訂注記）。かつての教育的コピー（「キーワードを入力して検索してください」）は撤去済みで、代わりに `DailyDigest`（今日の Gem・実データのカードリスト）が表示される。つまりこの画面は **NN/g が扱う「空状態（何も表示するものがない画面）」の定義に既に当てはまらない**。ここに絵を足す提案は「空状態の穴埋め」ではなく「ブランド演出」の話にすり替わる点に注意。
- 0 件・読み込み中・エラーはいずれもテキスト 1 行のみ（`repository-list.tsx` 33-40 行 / `loading-indicator.tsx` / `error-notice.tsx` 56-77 行）。すべて `min-height` 等でレイアウトシフト対策込みの設計。
- 404 は `repos/[owner]/[repo]/not-found.tsx` — `<h2>` + 戻るリンクのみで、ページ全体が実質空白。
- README 取得不可は `readme-section.tsx` 120-122 行 — 統計・タイトル等の実データが並ぶ詳細ページの **一部セクション** の中の 1 行フォールバック。

## 1. 状態ごとの判定

| 状態 | 絵の要否 | 根拠 |
|---|---|---|
| **未検索（待ち受け）** | **限定的に可（穴埋めとしては不要）** | 既に `DailyDigest` の実データが主役として表示されている。NN/g の空状態記事は「本当に何もない画面」を対象にしており（記事内の例示は "search results lists when nothing is found" 等、常にデータ 0 件の文脈）、実データが既にある画面へ空状態イラストを持ち込むのは対象誤りになる。ここでの画像はブランド表現（後述の OG/favicon の派生）程度に留め、日次ダイジェストのカード群より視覚的に軽くする。全面イラストは NG。 |
| **検索結果 0 件** | **可（小さく）** | NN/g の 3 ガイドライン記事が空状態の定型例として明示的に列挙する唯一の検索系ケース（"Search results lists when nothing is found, as well as other cases where a command creates empty output."）。GitHub Primer も初回体験（onboarding blankslate）とは区別しつつ、コンテンツが存在しない理由を説明する構図の中に軽い図版を許容する。現行文言（「キーワードを変えて試してください」）は既に NN/g 推奨の「次の一手」を満たしているため、画像は **文言の補助・ミッション訴求の器** として小さく添えるのが適切。全面ヒーロー画像にはしない。 |
| **読み込み中** | **絵を入れるべきでない（1）** | 表示時間が短く（0〜300ms は非表示・`ui-ux-guidelines.md` §4.4）、遅延ロードされる装飾画像を挟むと「絵の読み込み待ちで文言表示がさらに遅れる」か「絵がちらつくだけで終わる」の二択になる。あらゆる主要デザインシステム（Primer / GOV.UK / M3）が読み込み中はスケルトン or 最小限のスピナーのみを推奨し、装飾イラストの居場所として扱っていない。本プロジェクトも §4.4 でスケルトン化（実データと同一寸法のカード形状）を将来対応として明記しており、方向性は「形状の予告」であって「絵で楽しませる」ではない。 |
| **エラー** | **絵を入れるべきでない（2）** | `role="alert"` は緊急性を伴う通知であり、GitHub Primer のエラー状態指針が明言する通り「グラフィックは楽しさを追求せず、問題発生を強調するのみ」（デフォルトはアラートアイコン程度）。レート制限エラーは復帰時刻という時間的に重要な情報を含み（`US-25`）、装飾イラストは注意をその情報から逸らす方向にしか働かない。プロジェクトの GOV.UK 由来ルール（§5.1「申し訳ありません」等の曖昧表現禁止）とも整合しない温度感になる。**採用するなら `--color-danger` トークンに合わせた単色のアラート記号程度**（gpt-image-2 の出番ではない）。 |
| **404** | **可** | 唯一「ページ全体が実質空白」になる独立到達点で、NN/g・Primer・Atlaskit（`atlaskit.atlassian.com/examples/design-system/empty-state/with-image`）のいずれも空状態イラストの典型適用先として扱う。他の情報と競合するレイアウトがないため、絵の視覚的重みを気にせず配置できる唯一の状態。 |
| **詳細ページ README 取得不可** | **絵を入れるべきでない（3・任意）** | 統計行・リポジトリ名など実データが並ぶ詳細ページの中の一部セクションのフォールバックに過ぎない。ここだけ絵を足すと、周囲の情報密度の高いセクション群との視覚的リズムが崩れ（§2.3 のタイポスケール規律とも不釣り合い）、かつ「たまに起きる例外」ではなく private リポジトリ等で恒常的に発生しうるため、絵を見飽きるコストの方が大きい。 |

**絵を入れるべきでない事例は上記の 3 つ（読み込み中・エラー・README 取得不可）。全部に絵を足す提案は明確に却下する。**

## 2. ブランド面（優先順位）

1. **favicon（最優先）**: ブラウザタブ・ブックマークでの識別に必須。ただし **gpt-image-2 の写実的・グラデーション豊かな出力はそのまま favicon に使わない**。16×16 まで縮小されると潰れる。gpt-image-2 では「原石（アンカット・非対称な多面体）」のモチーフ案を大きめに生成し、そこから単色・2 トーンまで単純化した SVG を別途起こす（AI 画像→そのまま favicon化、をしない）。
2. **OG 画像（次点）**: 個人開発者への SNS 経由の発見がミッション上重要（`docs/project-mission.md` の「個人開発者が見つけられるようにする」）ため、シェア時の第一印象を作る OG 画像の効果は大きい。**ただし静的にテキストを焼き込まない**（後述）。
3. **アプリアイコン（apple-touch-icon 等）**: favicon の高解像度版を流用すれば追加コストはほぼゼロ。PWA 化の予定が無い現状では独立した優先度を持たせない。

## 3. 具体案（gpt-image-2 へ渡す粒度）

### (a) 0 件検索結果・小型モチーフ
- **構図**: 虫眼鏡が、磨かれた宝石の山を素通りして、隅で埃をかぶった小さな原石（カットされていない不揃いな結晶）を照らし出そうとしているが、その原石も見当たらない/枠の外にある——という「探しているが今回は見つからない」を示す静止した 1 カット。
- **モチーフ**: 原石（ミッションの「star は少ないが実利用されている」の視覚的比喩）+ 虫眼鏡。人物・マスコットは入れない（GOV.UK 的な即物性を壊さない）。
- **トーン**: 静か・素っ気ない・少しユーモラスな程度に抑える（謝罪的にしない。§5.1「申し訳ありません」禁止と同じ温度感を絵にも適用）。
- **配色**: フラットベクター、2〜3 トーンのみ。彩度を落とし `--color-fg-muted` / `--color-border` 相当のグレースケール寄りにする（`--color-accent` は使わない。0 件はネガティブな結果でアクセントカラーを当てると誤誘導になる）。ライト/ダーク両テーマ用に背景透過の 2 バリアントを用意。
- **サイズ感**: 96〜120px 程度の小型。文言（見出し級ではない）の隣に添える程度に留め、ヒーロー画像化しない。

### (b) 404
- **構図**: 展示台（または額縁・棚）だけがあり、そこに置かれているはずの原石が無い——空いた台座に薄く輪郭線だけが残っている、という「ここにあるはずのものが無い」を直接示す構図。
- **モチーフ**: 空の台座 + 微かな輪郭（不在の暗示）。宇宙飛行士・迷子の犬などの汎用 404 クリシェは避け、ミッション固有のモチーフ（原石探し）に寄せる。
- **トーン**: 0 件よりわずかにドライでよい（ページ全体が空白なので絵の存在感は許容度が高い）。
- **配色**: (a) と同一パレット・同一線の太さで統一感を出す（別モチーフの絵が混在すると一貫性が崩れる）。
- **サイズ感**: 160〜200px 程度。`<h2>` の上または横に配置。

### (c) favicon / アプリアイコン
- **構図**: 単一の原石を正面から見た多面体シルエット 1 つのみ。背景無し。
- **配色**: 2 色まで（例: `--color-accent` 相当 1 色 + 背景）。グラデーション・影・細かいハイライトは禁止（縮小で潰れる）。
- **手順**: gpt-image-2 で大きめの原石コンセプトを複数案出し → 人力 or ベクター化ツールで 1 シルエットまで単純化 → SVG化 → 各解像度書き出し。**AI 画像をそのまま favicon.ico にしない**。

### (d) OG 画像
- **構図**: 磨かれた宝石が並ぶ列の中に 1 つだけ原石が紛れている、という「注目度に埋もれた実力者」のメタファーをワイド構図（1200×630）で。
- **テキストは画像に焼き込まない**（後述の反対尋問への回答）。next/og の `ImageResponse` で背景画像（gpt-image-2 生成・モチーフのみ）の上にロケール別タイトルを動的合成する構成にする。
- **配色**: (a)(b) と同一パレット系統でよいが、OG はクロール専用でユーザー端末のテーマに依存しないため、ライト背景 1 種のみで足りる。

## 4. 反対尋問への備え（どこまで譲るか）

- **「重くなる」への回答**: OG 画像はクローラーのみが取得し実ユーザーの読み込みコストはゼロ。0 件・404 の画像は 10〜20KB 程度の最適化 WebP を想定し、かつ LCP 対象（`ui-ux-guidelines.md` §8.1 の「最初の結果カード」）ではないため CWV 目標に影響しない。**譲歩ライン**: パフォーマンス懸念が強ければ、最初に落とすのは (a) 0 件検索結果の画像（4 状態中もっとも高頻度に描画されるため累積コストが一番大きい）。404 と favicon/OG（ブランド系）は影響範囲が狭いので最後まで残したい。
- **「うるさくなる」への回答**: 単色・小型・token パレット準拠という制約を課しているため、既存の情報密度の高い一覧 UI とは衝突しない設計にしてある。**譲歩ライン**: それでも「GOV.UK 的な即物性から外れる」という指摘が通るなら、0 件検索結果の画像も落とし、**404 + favicon + OG の 3 点（一覧 UI と物理的に分離された場所）のみ** に絞る。一覧・検索という中核体験には一切絵を持ち込まない案を代替案として明示しておく。
- **「文言変更に追随できない」への回答**: すべての画像は **モチーフのみでテキストを含めない**。可視文言は従来どおり `messages/{locale}.json` 側の通常 DOM テキストとして画像の外に置く。OG 画像だけは慣習的にタイトル文字を画像内に持つことが多いが、静的合成画像を作らず next/og の動的合成（背景＝生成画像、テキスト＝実行時レンダリング）にすることで、コピー変更のたびに画像を再生成する必要をなくす。

---
以上、post 済み。

### `docs_trace` — 主張
<sub>2026-08-21T18:26:44+09:00</sub>

# 議論型レビュー: UI ビジュアル導入（Issue #347）の既存ドキュメント整合分析

## 1. 更新が必要になる節（パス + 節番号 + 概要）

### ui-ux-guidelines.md
- **新規 §0.1: 画像アセット管理の SSOT 参照**
  - 公式ロゴ・空状態イラスト・ビジュアルの配信元・命名規約
  - `tools/infographic/` との責務分離（ドキュメント図 vs UI 内アセット）

- **新規 §6.1: ヘッダーコンポーネント（共通化）** 
  - ツールタイトル / ロゴ配置 / 言語切替ボタンの配置
  - モバイルレスポンシブ時の動作

- **新規 §4.6: トップページの空状態イラスト（§4.4 に並列）**
  - 未検索初期状態・0 件・エラー時のビジュアル表示
  - 既存の `4.4 状態表現` は「テキスト」中心だが、Issue #347 でイラストを伴う

### prd.md
- **§2.3「アーキテクチャ上の設計原則」に追記**
  - 「ビジュアルアセット配信は既存 infographic 基盤に乗らない」という境界明記が必要

## 2. 影響する AC-n / NFR-n / US-n / E-n

### 既存要件への直接影響
- **NFR-14**（画像の alt）
  - ロゴ：文脈次第（リンク時は装飾扱い / スタンドアロンなら説明要）
  - イラスト：状態の非テキスト表現として alt または aria-describedby 必須

- **AR-4**（i18n）の詳細実装
  - ADR 0011 は「ロケール基盤（ルーティング）」に限定
  - 言語切替ボタンの配置・ラベル文言は新規の設計事項

- **NFR-21**（PaaS 非依存）
  - 「画像配信は HTTP キャッシュ + Workers Caching」なのか「Cloudflare Images」なのか未決
  - アプリコード（`src/`）から `src/infrastructure/platform/` への分離対象になるか

### 新規要件の定義の必要性
- **UI 内ビジュアルアセットの取得・配信方式**（現在は AC-n / NFR-n に未定義）
  - 検索窓の初期表示イラスト / エラーイラスト の正本・更新 SLA は？
  - `tools/infographic/` 既存スキルで生成するのか？別フローか？

## 3. ADR 起票の要否

### 状態
- **ADR 0001**（UI スタック: Tailwind + shadcn/ui）: 既存・承認
- **ADR 0011**（i18n ルーティング）: 既存・承認

### 新規 ADR が必要か？
🔴 **はい。以下 2 本の新規 ADR 考案候補**：

1. **「ビジュアルアセット（ロゴ・イラスト）の配信・キャッシング戦略」**
   - 対応要件: `NFR-21`（PaaS 非依存）/ `D-11`（プレビュー環境）
   - 決定対象: アセット配信先（Workers / Cloudflare Images / CDN）・キャッシュルール・バージョニング戦略
   - 理由: `tools/infographic/` との責務分離、UI アセット vs ドキュメント図の境界明記が必須

2. **「ヘッダー共通化とナビゲーション配置」**
   - 対応要件: `AR-4`（i18n）/ Issue #347（ヘッダー共通化）
   - 決定対象: h1 の位置（既存は `app/[locale]/layout.tsx`・Issue #334 F-2 反映済み）の再確認、言語切替ボタン位置
   - 理由: 既存ガイドラインに記載がなく、この決定で複数ページのレイアウト・アクセシビリティが変わる

## 4. 矛盾する既存記述

### 境界曖昧性
**prd.md §2.3 vs ui-ux-guidelines.md の責務分離**:

```
prd.md §2.3 引用:
  | 「インフラを決め打たない」 | … 特定 PaaS 固有機能への依存は最小化し、
                             事業者固有バインディングへのアクセスは
                             `src/infrastructure/platform/` 配下に限定する（`NFR-21`）

ui-ux-guidelines.md:
  （画像・ロゴに関する節がない）
```

→ **ビジュアルアセット（ロゴ・図・イラスト）が `NFR-21` の対象か否かが未明記**。
  - アプリが画像を `src/` から供給するなら → `src/infrastructure/platform/` 隔離対象
  - 静的ファイル（`public/`）でホストするなら → Workers が直接サーブ可能
  - Cloudflare Image API を使うなら → `src/infrastructure/platform/cloudflare-images.ts` を新設すべき

### ドキュメント図との責務分離が不明確

**tools/infographic/README.md 既存**:
```
このツールは「ドキュメントから抽出した構造化テキストを gpt-image-2 で 16:9 グラレコ風に」描画
（プレゼンスライド用）
```

**Issue #347 のビジュアル**:
- ロゴ（ブランディング用）
- 空状態イラスト（UI フロー用）
- （日次ダイジェスト等のプレビューイラスト？）

→ **両者の生成パイプライン・配信形式は完全に別** だが、既存ドキュメントに明記がない

## 5. SSOT 増設の監視観点

以下の 3 項目が新たに「正本」を必要とする可能性：

### a. 画像アセット配信の基盤（新規 SSOT 候補）
**現在の SSOT**: なし（`tools/infographic/` だけが「ドキュメント図の正本」を持つ）

**Issue #347 導入後に必要な SSOT**:
- UI 内ロゴ / イラストの正本・バージョニング・更新手順
  - 例: `docs/03_design/ui-assets/README.md` に「ロゴはデザイナーが gpt-image-2 で生成 → WebP に変換 → `public/images/` へ配置」等の SOP
  - または単に prd.md §2.3 に追記

### b. i18n 言語切替 UI の配置（新規 SSOT 候補）
**現在の SSOT**: ADR 0011（ルーティングのみ）

**Issue #347 で必要な SSOT**:
- ヘッダーの言語切替ボタンのプロダクト設計
  - 何をクリック → どこへジャンプ？（URL はどう変わる？）
  - モバイルメニュー内か / ヘッダー右上固定か？
  - 既存の `messages.*.json` のキー（例 `header.langSwitch`）の正本

### c. 画像サイズ・フォーマット規約（新規 SSOT 候補）
**現在の SSOT**: ui-ux-guidelines.md §2.4「コントロールサイズトークン」（寸法は CSS px）

**Issue #347 で追加必要**:
- ロゴ横幅 / 高さ（CSS px / rem）
- イラスト領域のアスペクト比（既存 `§4.4 状態表現` とのレイアウト整合）
- WebP / PNG / SVG の使い分け基準

---

## 結論

**既存ドキュメントは Issue #347 で必要な**
- **ヘッダー共通化** の UI 設計
- **ビジュアルアセット配信・キャッシング戦略**
- **i18n UI（言語切替ボタン）のプロダクト仕様**

**について、ほぼ記述がない状態。**

これらを追加する際に、以下を同時に進める必要がある：
1. ui-ux-guidelines.md に §6.1（ヘッダー）・§4.6（空状態ビジュアル）を新設
2. prd.md に「ビジュアルアセット配信」の方式（新規 AR-* or E-* ?)  を追加
3. 新規 ADR 0015～0016 程度で「ビジュアルアセット基盤」「ヘッダーナビゲーション」を記録
4. `tools/infographic/` との責務分離を `tools/infographic/README.md` にも明記

### `a11y_i18n` — 主張
<sub>2026-08-21T18:26:51+09:00</sub>

# a11y_i18n r1: 画像化 UI と言語別出し分けへの反対尋問

## 結論を先に

**ユーザー指示「言語ごとに画像を使い分ける」「イメージだけで表現できるならそれでよい」は、a11y を割らずには両立しない。**
「画像だけで意味を伝える」（= 有意味な alt もテキスト焼き込みも必要な情報を画像側に持たせる）と、「言語ごとに画像を分ける」を同時にやると、必ず次のどちらかを踏む。

- 画像に **文字を焼き込む** → 1.4.5 Images of Text（AA）違反。かつ **axe/Lighthouse では検出できない**（本プロジェクトの三層防御の盲点が増える）。
- 画像に文字を焼き込まず、**alt だけで情報を運ばせる** → 1.1.1 は満たせるが、それはもう「イメージだけで表現」ではなく「テキスト（alt）+ 装飾画像」であり、言語別に画像を分ける動機（文言の翻訳）自体が消える（alt を `messages/{locale}.json` で出し分ければ済み、画像はロケール非依存の 1 枚でよい）。

したがって成立する組み合わせは 1 つだけ: **画像は常に装飾（`alt=""`）とし、意味は既存どおり HTML テキストで運ぶ。画像は言語非依存の 1 枚に固定し、ロケール別に差し替えない。** 詳細は §5。

---

## 1. WCAG 2.2 条文と本プロジェクトへの影響

### 1.1.1 Non-text Content（Level A）
> "All non-text content that is presented to the user has a text alternative that serves the equivalent purpose[...]" （[W3C WCAG 2.2 Quickref](https://www.w3.org/WAI/WCAG22/quickref/)）

画像が「唯一の情報源」になる設計（0 件表示・読み込み中・エラーを画像だけで表す案）は、その画像に**等価なテキスト代替**が要る。`ui-ux-guidelines.md` §7.4 は既にこの区分（テキスト隣接＝装飾 `alt=""` / 唯一の情報源＝有意味 `alt`）を確立済みで、新規の画像もこの表に従うだけでよい。**「イメージだけで表現できるなら alt も省略してよい」という読み方は誤り**——1.1.1 は「画像だけで表現する」ことを禁じてはいないが、その画像に**必ずテキスト代替を伴わせる**ことを要求する。alt が実質的にテキスト表現そのものになった時点で、それはもう「テキストレス」ではない。

### 1.4.5 Images of Text（Level AA・本プロジェクトの axe tag `wcag2aa`/`wcag21aa`/`wcag22aa` の適合範囲内）
> "If the technologies being used can achieve the visual presentation, text is used to convey information rather than images of text" — 例外は (1) Customizable: 「画像の文字がユーザーの要求に合わせて視覚的にカスタマイズできる」、(2) Essential: 「特定の視覚表現がその情報を伝える上で本質的（ロゴ等）」（[Digital Policy Office 訳/W3C 原文](https://www.digitalpolicy.gov.hk/en/our_work/digital_government/digital_inclusion/accessibility/promulgating_resources/handbook/wcag2aa/9_7_images_of_text.html)）

`gpt-image-2` で文言（見出し・ボタン文言・エラー文言等）を画像内に焼き込む案は、この 2 つの例外のどちらにも該当しない（ユーザーがフォント・色・サイズを変更できない／ロゴのような本質的表現でもない）。**AA 違反が確定する。**

**さらに重大な問題**: `e2e/axe.ts` のコメントが既に自認している通り、axe-core は DOM 静的解析であり「画像の中に文字が焼き込まれている」ことを OCR 的に検出する仕組みを持たない。`tools/run_lighthouse.mjs` の Accessibility=100 も同様に検出不能。つまり **1.4.5 違反は Lighthouse 100 + axe wcag22aa 通過後も残存する** ——`ui-ux-guidelines.md` §7 が三層防御で明示している「Lighthouse が緑でも a11y 全体は健全とは限らない」構図に、**新しい盲点（画像内テキスト）が追加される**。既存の三層表（フォーカスリングの非テキストコントラスト用）は今回のケースをカバーしていないため、機械ゲートを信用して「通ったから安全」と判断しないよう、PR レビュー観点（人手チェックリスト）へ明記する必要がある。

### 1.4.11 Non-text Contrast（Level AA）
> "The visual presentation of [...] Graphical Objects: Parts of graphics required to understand the content [...] have a contrast ratio of at least 3:1 against adjacent color(s), except when a particular presentation of graphics is essential" （[W3C Quickref](https://www.w3.org/WAI/WCAG22/quickref/)）

AI 生成イラストは背景・アイコン部分のコントラストが偶然低くなりやすい（写実的な陰影・グラデーションを多用するため）。`tools/check_contrast.py` は **CSS 変数の宣言値だけ**しか見ないため、ラスター画像内のコントラストは対象外——ここも機械ゲートの範囲外である。「意味を理解するのに必要な図形要素」（例: 空状態イラストの虫眼鏡そのものが状態を表す場合）が該当すれば人手確認が要る。

### 1.4.4 Resize Text（Level AA）
テキストを画像化すると、ブラウザのページズーム（200%）では画像ごと拡大されるため直ちに違反にはならないが、**低解像度で生成された画像はズーム時にピクセル化し実質的に判読不能**になりやすい（`gpt-image-2` の出力解像度次第）。これは 1.4.4 の例外条項（キャプション・本質的表現の画像は対象外）に逃げ込める場合もあるが、逃げ込めた時点で「読める」ことは保証されない——1.4.5 で焼き込みを禁止していれば、この問題自体が発生しない。

### 2.3.3 Animation from Interactions（Level AAA・本プロジェクトの axe tag には含まれず必須ゲート外）
`loading-indicator.tsx` は既に `motion-reduce:animate-none` で `prefers-reduced-motion` に対応済み。生成画像にホバーアニメーション・パララックス等を足す場合も同じ配慮を踏襲すること（AAA のため必須ゲートではないが、既存の作法を崩さない）。

---

## 2. alt の線引き（新規画像への適用）

`ui-ux-guidelines.md` §7.4 の表をそのまま新規画像に適用できる。追加すべき論点は 1 点だけ:

| 画像の役割 | 判定 |
|---|---|
| 既存の HTML テキスト（見出し・本文・ラベル）の**視覚的補強**として並置される（例: 検索フォーム脇の装飾イラスト、0 件状態の脇に添えるイラスト） | `alt=""`（装飾）。情報は既にテキスト側にあるため画像は冗長 |
| 画像**単体**でテキストが一切ない箇所に置かれ、意味を持つ（例: アイコンのみのボタン） | 意味のある `alt` が必要。ただし alt の内容は**焼き込み文字の転記ではなく**、画像の意味の説明であること |
| 上記どちらにも当てはまらない「画像だけで完結させたい」箇所 | **成立しない**（§0 の結論どおり）。1.1.1 を満たすには結局テキスト等価物が要るため、最初から HTML テキスト + 装飾画像に設計し直す |

**「絵だけで意味を伝える」案が成立する唯一の条件**: その絵が **既存のテキストと同じ情報を重複して示すだけ**（=装飾）である場合に限る。絵が「言語によって伝えるべき情報そのもの」を担う設計（ユーザーの想定に近い）は、必然的に有意味 alt かテキスト焼き込みのどちらかを要求し、後者は 1.4.5 で不可、前者は「言語別に画像を分ける」動機を消す。

---

## 3. ライブリージョン内に画像を置いたときの支援技術挙動

対象 3 状態（0 件 `<p role="status">` in `repository-list.tsx`／読み込み中 `<section id="search-status" role="status" aria-live="polite">` in `page.tsx`／エラー `<div role="alert">` in `error-notice.tsx`）はいずれも `aria-live` の**暗黙 atomic**（`role="status"`/`role="alert"` は既定で `aria-atomic="true"`）。

- **画像が decorative（`alt=""`）の場合**: アクセシブルネーム計算に寄与しないため、ライブリージョンの再アナウンスには一切乗らない。**安全**。
- **画像が有意味 alt を持つ場合**: `aria-atomic` によりリージョン全体（画像の alt を含む）が再構成されるたびに**丸ごと再読み上げ**される。`page.tsx` のコメントが自認する通りこの region は「読み込み中 → 件数」の**中身の書き換え**を繰り返す設計であり、その都度 alt 付き画像があれば alt テキストごと再読み上げされる——**二重読み上げ**（同じ絵の説明を検索のたびに聞かされる）を生む。特に 0 件時は `main` 内に `role="status"` が **2 つ**（`#search-status` の件数文言と `RepositoryList` の 0 件文言）同時に存在すると `e2e/sp-9-loading-empty.spec.ts` のコメントが明記しており、両方に画像を足すと二重どころか多重の読み上げが起きる。
- **無通知リスク**: 逆に、画像の `src` だけを差し替えて `alt` を変えない実装（例: 読み込み中→完了で同じ alt のイラストのまま）は、リージョン内のテキストノードに変化がないと解釈され AT によっては**通知が飛ばない**ことがある（ブラウザ・AT 実装依存の未定義動作領域で、`loading-indicator.tsx` のコメントが述べる「二重読み上げ／無視のいずれも起こりうる」と同種のリスク）。
- **結論**: ライブリージョンの内側に置く画像は **例外なく `alt=""` に固定する**。有意味な絵をどうしても状態表現に使いたいなら、ライブリージョンの**外**（兄弟要素）に固定表示として置き、テキストの状態変化とは独立させる。

---

## 4. 言語別出し分けの実装リスク

1. **`<picture>` の誤用**: `<picture>`/`<source media="...">` はビューポート・解像度・`prefers-color-scheme` 等のメディア特徴用であり、**ロケールは媒体特徴ではない**。ロケール分岐に `<picture>` を使うのは仕組みの誤用で、将来ダークモード対応が入ったときに「メディアクエリの軸」が衝突する（ロケール軸とカラースキーム軸を同じ `<source>` 一覧で表現できない）。本プロジェクトは Server Component で `locale: Locale` を既に props として持ち回している（`repository-list.tsx` 等）ので、**サーバー側で `src` を条件分岐した通常の `<img>`** を返せばよく、クライアント JS も `<picture>` も不要（`NFR-3` の「クライアント JS を持たない」方針にも合致）。
2. **`<html lang>` との整合**: 画像自体は言語情報を持たないため `lang` 属性とは無関係だが、**alt を画像と同じ言語で出す**運用を徹底しないと、`lang="en"` ページなのに日本語 alt が残る（スクリーンリーダーの言語切り替えが誤作動し発音が崩れる）取り違えが起きやすい。alt は必ず `messages/{locale}.json` 経由にし、ハードコードしない（`ui-ux-guidelines.md` §7.4a の既存方針と同一の縛りを課す）。
3. **SSR・キャッシュ**: 各 `/ja` `/en` は既に別ルートとして完全に分離されているため（`generateStaticParams` で `LOCALES` ごとに生成）、画像を言語別に静的アセットとして持つこと自体はキャッシュ機構上の新規リスクを生まない（既存の日付・数値フォーマットのロケール分岐と同列）。**リスクは技術的な出し分けではなく運用上のドリフトの方**（次項）。
4. **ドリフト（劣化）リスク・最重要**: `messages/ja.json` / `messages/en.json` は文言追加・修正のたびに両言語を同時に更新する運用が前提だが、**画像アセットにはそれを強制する仕組みが存在しない**。文言（テキスト）を修正しても、対応する言語別画像を更新し忘れれば「ja のテキストは新しいが ja の画像は古い」という **サイレントな不整合** が生まれ、これは axe にも Lighthouse にも `check_contrast.py` にも引っかからない（テキストと画像の意味的一致は静的検査では判定不能）。**画像に情報を持たせるほど、この不整合の検出コストが上がる**——だからこそ画像は「情報の担い手」ではなく「装飾」に限定し、情報は必ずテキスト側（i18n 化・grep 可能・レビュー可能）に置くべきである。装飾画像であれば言語別に分ける必然性そのものがなく（意味を持たないので言語に依存しない）、**1 枚の画像を ja/en 共通で使い回すのが最も安全**。

---

## 5. 結論（再掲・具体策）

ユーザー要望「言語ごとに画像を使い分ける」「イメージだけで表現できるならそれで良い」を、a11y を割らずに満たす方法は **無い**。以下を代替として提案する。

1. **画像は全面的に装飾（`alt=""`）とし、テキストへ焼き込まない**。情報は既存どおり `messages/{locale}.json` の HTML テキストが担う（見出し・0 件文言・エラー文言・読み込み中文言、いずれも現状維持）。
2. **画像はロケール非依存の 1 枚に統一する**。装飾である以上、言語によって出し分ける意味的必然性がないため、ドリフトの発生源を最初から作らない。
3. **ライブリージョン（`role="status"`/`role="alert"` の内側）に置く画像は必ず `alt=""` を明示指定する**（§3）。有意味な画像を使いたい箇所があるなら、そのリージョンの外側の静的な位置（例: 検索フォームの脇・詳細ページの上部装飾）に限定する。
4. **画像に文字を一切焼き込まない**（1.4.5・axe/Lighthouse では検出不能なので PR レビューのチェック項目として明記する必要がある——`ui-ux-guidelines.md` §7 の三層防御表に「画像内テキストは目視レビューのみが検出できる」旨を追記することを推奨）。
5. どうしても「文言そのものを画像で見せたい」動機があるなら、それは a11y 上不可能ではなく **不要**——生成画像はあくまで視覚的な補強・雰囲気づくりに徹し、意味の伝達は引き続き 100% テキストが担う設計に倒すのが唯一の両立案。

### `perf_asset` — 主張
<sub>2026-08-21T18:27:32+09:00</sub>

# perf_asset ラウンド1: パフォーマンス・アセット配信レンズ

## 0. 前提の訂正（議題文の numbers は不正確・要修正）

議題は「Lighthouse Performance 90 以上・LCP 2.5s 以下・CLS 0.1 以下が **必達**」としているが、実装済みのゲート
（`tools/run_lighthouse.mjs` + `docs/02_requirements/prd.md` NFR-27）はそうなっていない。

- **blocking なのは Accessibility = 100 だけ**（`evaluateAccessibilityGate`）。
- Performance は「90 以上を **目安値として計測・記録する（未達でもゲートしない）**」（NFR-27・偽陽性対策あり:
  本番相当ビルド・複数回中央値・スロットリング固定）。
- NFR-1（LCP 2.5s / INP 200ms / CLS 0.1）は `P1-MVP` の要件ではあるが、CI で数値ゲート化されているわけではない。

→ **「未達なら CI が落ちる」という前提で設計判断をしない。** ただし NFR-1/NFR-27 は依然として P1-MVP 要件なので、
「ゲートされないから何でもよい」でもない。実務的な結論: 画像追加は Performance スコアの **目に見える劣化を作らない**
ことを目標にし、劣化したら記録には残る（レビューで拾われる）という前提で予算を組む。

## 1. 品質ゲートへの定量的影響

- 実測データ: `docs/infographics/*.webp`（gpt-image-2 medium 品質・1536×864・sharp webp quality=90 で変換済み）は
  **1 枚 205〜324KB**（13 枚平均 約 253KB）。これは「文字を一字一句正確に描く」高密度インフォグラフィックの実測値で、
  UI装飾用の単純なイラスト（背景シンプル・文字なし）とは性質が違うが、**「gpt-image-2 → WebP そのまま」の素朴な
  パイプラインは 1 枚 200KB 前後になりうる** という基準値として扱うべき。
- LCP 要素にした場合: 250KB の画像 1 枚だけで、3G Fast 相当のスロットリング（Lighthouse 既定）では転送に
  優に 1 秒超かかりうる。現状ページは他に大きな静的アセットを持たない軽量構成（`NFR-3`）なので、LCP 候補は
  相対的に見つけやすく、うっかり大きい画像を above-the-fold に置くと LCP 予算 2.5s の大半をその 1 枚が食う。
- CLS: `width`/`height`（または `aspect-ratio`）を明示すれば新規画像由来の CLS はほぼゼロにできる。
  `repository-list.tsx` の既存パターン（`width={40} height={40}`）がそのまま流用できる。CLS はむしろ守りやすい軸。
- **結論**: Performance 90 は CI では強制されないが、実測 200KB 級の画像を LCP パスに置くと「目安値」を割り込み、
  レビューで指摘対象になる公算が高い。**予算: 1 枚あたり圧縮後 50KB 以下（理想 20〜30KB）** を目標値として置く
  （後述 §2 の SVG 化ならこの予算は容易に達成できる。ラスターのまま置くなら寸法・quality を絞る必要がある）。

## 2. 形式の選定 — 「SVG 化すべき」対案の本気の検討

### 2.1 gpt-image-2 の出力特性とベクター化の相性

gpt-image-2 は写実的な陰影・グラデーション・テクスチャを含む「絵画的」なラスター画像を生成するのが強み。
これを `potrace` 等でトレースすると:

- **グラデーション・多色・柔らかい陰影**があるほどトレース結果のパスが爆発的に増え、SVG が数百KB〜数MBになる
  （「ラスターより重い SVG」という本末転倒が起きる）。実質的にトレースが小さく仕上がるのは、**フラットな色数枚・
  高コントラスト・輪郭線がはっきりした「ロゴ／アイコン調」の絵柄に限る**。
- つまり **「gpt-image-2 の絵作りの強み」と「トレースして軽くする」は基本的に二律背反**。豊かな質感を求めるほど
  トレースは非現実的になる。

### 2.2 折衷案（ユーザーの gpt-image-2 指示を無効化しない結論）

ユーザー指示（gpt-image-2 を使う）を尊重しつつ性能を守る現実的な線引きは **用途で使い分ける** こと。

| 用途 | 推奨形式 | 理由 |
|---|---|---|
| **小さい装飾的イラスト**（例: 空状態・0件状態のワンポイント図・アイコン的カット） | gpt-image-2 で生成 → プロンプトを **「フラットカラー 3〜4 色・グラデーションなし・太い輪郭線・ベクターイラスト風」に明示指定** → `potrace`/`imagetracerjs` でトレース → **インライン SVG** として配置 | 数KB に収まる。ネットワークリクエスト 0 本（インライン化すれば HTML に同梱）。CSS `currentColor` 等でダーク/ライトの色調整も可能（§4）。LCP リスクが実質消える |
| **主役級のビジュアル**（豊かな質感・雰囲気を出したいヒーロー画像等） | gpt-image-2 で生成 → **WebP** で配信 | トレース非現実的。ラスターのまま配信するしかない。その代わり §1 の予算（圧縮後 50KB 目標）を厳守し、**LCP 要素にしない**（後述 §3）か、LCP にするならサイズを極小に絞る |

**本プロジェクトの現状（`ui-ux-guidelines.md` §4.4）に照らすと**: 未検索状態は「教育的テキスト」、0件は「システム状態確認」
という **テキスト主体の設計方針**で、いずれも大きなヒーロー画像を要求していない。したがって現実的な着地点は
**前者（小さい装飾イラスト・SVG化）** であり、「主役級ビジュアル」の必要性自体を ux_visual/main に問いたい。
必要性が薄いなら、豊かな質感を捨てずに済む上に性能リスクもゼロという二重の利点がある。

### 2.3 PNG のまま置くのは論外・AVIF は費用対効果が低い

- gpt-image-2 の生 PNG はロスレスで巨大（実測ワークフローでも WebP 変換前提）。**PNG 直置きは禁止**。
- AVIF は WebP よりさらに 20〜30% 小さくなりうるが、`next/image` の最適化を使わない本プロジェクト（`INF-11`）では
  **ビルド時に静的変換して `<picture>` で出し分ける**しかない。追加の変換ステップ・追加のビルド成果物（1画像に
  つき WebP + AVIF の2ファイル）というコストに対し、対象画像が数枚・数十KB規模であれば削減量は数KB〜十数KB。
  **投資対効果が低いので今回は見送り、WebP 単体で十分**（`to_webp.mjs` の `sharp` 依存はそのまま流用でき、
  `avif()` メソッドも同じ `sharp` にあるため後日追加するのは低コスト）。

## 3. 実装制約（`INF-11`・生 `<img>`）

- `repository-list.tsx` の既存実装（`width`/`height` 明示・`loading="lazy"`）は **非LCPの一覧アイコン**向けの
  正しいパターン。新規 UI 画像もこれをベースにするが、**LCP候補になるかどうかで属性を変える**:
  - **LCP候補にしない画像**（=下記の推奨経路、SVG化 or 折りたたみ以下 or 非ヒーロー）:
    `loading="lazy"` `decoding="async"` のまま踏襲。
  - **LCP候補にする画像**（ヒーロー等、避けられない場合）: `loading="eager"`（**lazy にしない** — LCP要素を
    lazy-load すると発見が遅れて LCP を悪化させるのが公式ガイダンス）・`fetchpriority="high"`・`decoding="async"`
    を付け、`width`/`height` を実サイズ比率で必ず指定。
  - **`ui-ux-guidelines.md` §8.1 の既存規律を画像にも適用**: 「LCP 対象要素を、遅いデータに依存する Suspense
    配下に置かない」。`page.tsx` は検索結果を Suspense で遅延させているため、**新規画像を検索結果と同じ
    Suspense 境界の中に置かない**（未検索の初期状態・0件状態のイラストであれば元々 Suspense 外の可能性が高いが、
    実装時に確認が要る）。
- `fetchpriority`/`decoding` は現状コードベースで未使用（`repository-list.tsx` は `loading` のみ）。新規追加は
  既存パターンからの逸脱ではなく **拡張**として扱ってよい。
- `<link rel="preload" as="image" fetchpriority="high">` の追加は **今は不要**（YAGNI）。`fetchpriority="high"`
  属性だけで Priority Hints は効く。実測して Performance 記録値がなお悪ければ preload を検討する、の順で進める。

## 4. ダーク/ライト両対応

- **CSS `background-image: url()` は LCP 候補から除外されない**（web.dev / W3C LCP 仕様: gradientは除外だが
  `url()` 画像は対象。要修正: 「background-image ならLCP判定を回避できる」という発想は誤り・確認済み）。
  したがって「`<img>` を避けて CSS 側に逃がせば性能上の考慮が要らなくなる」という判断はできない。
- 2枚持つ（`<picture><source media="(prefers-color-scheme: dark)">`）場合、**ランタイムのネットワークコストは
  1枚分のまま**（ブラウザは一致する `<source>` だけ取得する）。増えるのは ① 生成コスト（API 呼び出し2倍）
  ② リポジトリ容量（2倍） ③ 運用の手間（片方だけ再生成すると絵柄がズレるリスク）であって、配信性能への
  直接的な悪化ではない。
- とはいえ **SVG 化経路（§2.2）を採るなら、そもそも2枚persistする必要がない**: `fill="currentColor"` や
  CSS 変数で塗りだけをテーマに応じて変える設計にすれば、1つの SVG 資産で両テーマに対応できる
  （生成・保守コストが半分になる）。これは a11y_i18n/ux_visual にも共有したい強い性能側の推し。
- ラスターのまま2枚持つ選択をするなら、性能上のブロッカーではないので反対しない（ux_visual の判断領域）。

## 5. リポジトリと配信

- **生成 PNG を git にコミットしない**: 既存の `tools/infographic/` ワークフローと同じく、PNG は `/tmp` 等の
  一時出力にとどめ、**最終成果物（WebP または トレース後 SVG）だけを `public/` にコミット**する。
- **配置**: `public/` 直下 or `public/illustrations/` 等のサブディレクトリ。Cloudflare Workers の Static Assets
  は `wrangler.jsonc` の `assets.directory`（`.open-next/assets`）経由でビルド時に `public/` の内容が取り込まれる
  想定（OpenNext の標準挙動）。1ファイルあたり数十〜数百KB規模であれば Cloudflare Workers Static Assets の
  単一アセット上限（数十MB級）に対して無視できるサイズで、配信面のブロッカーにはならない。
- **生成コストと再現手順**: `tools/infographic/generate.py` は本用途にそのまま転用可能（プロンプト→PNG生成の
  責務は同一）。ただし出力ディレクトリ・命名規約が「ドキュメント用インフォグラフィック」前提になっているため、
  UI アセット用には **専用のプロンプト/spec 置き場**（例 `tools/ui-assets/` を新設し `generate.py` を import/流用、
  または `tools/infographic/` に「UI 用」の spec を混在させず責務を分ける）を用意し、`prompts/*.txt` 記録の
  慣行（再生成の再現性）を踏襲することを推奨する。
- **コスト試算**: 本リポジトリの実測（1536×864・medium: 1,078 output tokens ≈ $0.032/枚、high: $0.129/枚）と
  gpt-image-2 の公開料金表クロスチェック（1024×1024・medium ≈ $0.053/枚 — 出典下記）は同オーダー。
  想定枚数が数枚〜十数枚（テーマ違い2枚持つ場合は倍）であれば **総額は $1 未満〜数ドル**で、コスト面は
  ブロッカーにならない。むしろ再生成を何度も試行錯誤する運用（プロンプト調整の反復）の方が枚数の桁を上げる
  ので、`build_prompt.py` 的な「spec→プロンプト組み立て」を経由してから生成回数を絞る運用を推奨する。

## 6. まとめ（他レンズへの申し送り）

- **性能的には「小さい装飾イラストは gpt-image-2 生成 → フラットカラー限定プロンプト → トレース SVG 化」が
  最善**。ユーザー指示（gpt-image-2 使用）を満たしつつ配信コストをほぼゼロにできる。
- **「主役級のリッチなビジュアル」を本気で入れたいなら SVG化は非現実的**なので、WebP・圧縮後 50KB 目標・
  LCP要素にしない（または `eager`+`fetchpriority=high` で明示的に手当てする）という運用で妥協する。
- ux_visual には「どちらの絵作り（フラット装飾 vs リッチなヒーロー）を望むか」を先に決めてもらう必要がある
  （分岐で実装方針が全く変わるため）。
- a11y_i18n には「ダーク/ライトを2枚持つ vs SVG+CSS変数で1枚にする」の選択が a11y（コントラスト再確認の要否）
  にも影響する旨を共有したい。

---
出典（WebSearch・2026-08-21 時点）:
- gpt-image-2 サイズ/料金: https://yingtu.ai/en/blog/gpt-image-2-cost-per-image ・ https://help.apiyi.com/en/gpt-image-2-vip-size-resolution-complete-guide-en.html
- LCP と background-image の扱い: https://web.dev/articles/lcp ・ https://www.w3.org/TR/2026/WD-largest-contentful-paint-20260408

### `frontend_arch` — 主張
<sub>2026-08-21T18:29:34+09:00</sub>

# frontend_arch R1 — Issue #347 ヘッダー共通化・LocaleSwitcher 移設・ロゴ

## 1. 現在 URL 問題（最大の争点）— 結論: 選択肢②（Client leaf + Suspense）を推奨

### 事実確認（`node_modules/next/dist/docs/` 実読）

- `01-app/03-api-reference/03-file-conventions/layout.md` "Caveats" は本件と完全に同型の制約を明記している。
  - **Query params**: 「Layouts do not rerender on navigation, so they cannot access search params… To access updated query parameters, use the Page `searchParams` prop, **or read them inside a Client Component using the `useSearchParams` hook**」
  - **Pathname**: 「Layouts do not re-render on navigation, so they do not access pathname… read it inside a Client Component using the `usePathname` hook」
  - 両方とも「小さな Client Component を切り出して Layout から呼ぶ」を **公式が提示する唯一の解決パターン** として例示している（`app/ui/breadcrumbs.tsx` 例）。
- `04-functions/use-search-params.md` "Server Components > Layouts" に明文: 「Unlike Pages, Layouts (Server Components) **do not** receive the `searchParams` prop. […] Instead, use the Page `searchParams` prop or the `useSearchParams` hook in a Client Component」。
- 同ファイル "Behavior > Prerendering": 静的にプリレンダーされるルートでは `useSearchParams` を使う Client Component は **最寄りの `<Suspense>` までクライアントレンダリングに倒れる**。本番ビルドで Suspense 無しだと **ビルド失敗**（`missing-suspense-with-csr-bailout`）。
- 同ファイル "Behavior > Dynamic Rendering": ルートが動的レンダリングなら **`useSearchParams` はサーバー初回レンダリング時点で使える**（= フォールバック閃光なしで正しい href が SSR される）。
- `04-functions/headers.md`: `headers()` が返すのは **実際の HTTP リクエストヘッダーのみ**（`user-agent`/`authorization` 等の例のみ記載）。パス名・クエリ文字列を運ぶ標準ヘッダーの記載は無い。App Router に「現在パスを運ぶ規約ヘッダー」は存在しない（Pages Router 時代の `x-invoke-path` 相当は文書化されていない内部実装であり、依拠すべきでない）。
- `04-functions/next-root-params.md`（v16.3.0 新機能。`not-found.tsx` が既に `locale` 取得に使用済み）: ルートパラメータ（root layout より手前のセグメント）だけが対象。`owner`/`repo` は root layout より深いので対象外 — つまり **`next/root-params` では現在パス全体を復元できない**（`locale` しか取れない）。

### 選択肢の列挙と評価

| # | 案 | 判定 | 理由 |
|---|----|------|------|
| ① | `headers()` から現在 URL を復元 | ❌ 却下 | パス/クエリを運ぶ標準ヘッダーが存在しない（上記 `headers.md`）。実装するなら独自 middleware でカスタムヘッダーを注入する必要があり、未文書化の内部ヘッダーに依拠するより明らかに大掛かりでスコープ外 |
| ② | **layout の一部だけ小さな `'use client'` 境界に切り出し、`usePathname`+`useSearchParams` で自前導出** | ✅ **推奨** | `layout.md`/`use-search-params.md` が公式に提示する唯一の解決パターン。コストは後述の通り小さく、既存の動的ルート（トップ・詳細）では SSR 初回描画で本物の href が出る（閃光なし） |
| ③ | 各 page から Parallel Routes（`@localeSwitcher` slot）で layout へ値を渡す | ❌ 却下（YAGNI） | slot は独自のルーティングツリーを持つため、`owner`/`repo` 動的セグメントまで含めて layout 側にミラーする必要がある（`app/[locale]/@localeSwitcher/repos/[owner]/[repo]/page.tsx` 等）。1 個の nav 部品のためにルーティング構造を二重化するのは CLAUDE.md の「1 箇所しか使わない抽象化を先回りしない」に反する |
| ④ | クエリ保持を諦め、ロケール接頭辞だけ swap（`/{other}`固定） | ❌ 却下（無条件の zero-cost ではない上に退行） | **これも layout 単体では実現できない**: `next/root-params` は `locale` しか返さず、`owner`/`repo`/検索クエリのどれも layout から取れないため、実装できる「ゼロコスト版」は事実上「常に `/{locale}` へ固定リンク」しかない。これは SP-7/SP-8 で確立した「操作を跨いでも検索条件を保持する」方針の後退であり、詳細ページで言語切替を押すと一覧トップに戻される退行になる（未依頼のスコープ拡大） |
| ⑤ | LocaleSwitcher は今まで通り各 page から描画し、CSS で見た目だけヘッダー行に重ねる | ❌ 却下 | DOM 順序（layout.tsx 側のロゴ/タイトル/ログイン）と視覚順序（ページ側の LocaleSwitcher）が乖離し、タブ順・スクリーンリーダー順が視覚と一致しなくなる。2 ファイルにまたがる flex/grid の座席合わせが必要になり、「共通化」の目的（1 箇所に一元化）にも反する |

### 推奨案の実装設計

```tsx
// src/ui/locale-switcher.tsx（変更後）
'use client'
import { usePathname, useSearchParams } from 'next/navigation'
// currentPath は props から削除。自前で導出する。
export function LocaleSwitcher({ currentLocale, labels }: LocaleSwitcherProps) {
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const qs = searchParams.toString()
  const currentPath = qs === '' ? pathname : `${pathname}?${qs}`
  // 以降は現行の buildLocaleUrl 呼び出しロジックをそのまま流用
  ...
}
```

```tsx
// app/[locale]/layout.tsx（header 内）
<Suspense fallback={<LocaleSwitcherFallback currentLocale={locale} labels={...} />}>
  <LocaleSwitcher currentLocale={locale} labels={{...}} />
</Suspense>
```

- **`LocaleSwitcherFallback`**（新規・サーバーコンポーネントで可）: `buildLocaleUrl('/' + locale, target)` で `/{target}` 固定リンクを出すだけの最小版。layout はこの時点で `locale` root param しか持たないため、フォールバックが出せる情報はここまで（④で却下した「ゼロコスト版」と同じ形）。ただし **これは初回ペイントの一瞬だけ** で、実際にフォールバックが見える可能性があるのは静的化されうる `not-found.tsx` 系統のみ（下記参照）。トップ・詳細ページは既に `headers()`/`searchParams` で動的レンダリングが確定しているため、"Dynamic Rendering" 節の通り **フォールバックは描画されず最初から正しい href が SSR される**。
- Suspense を **必須** で挟む（layout.md/use-search-params.md 両方が明記）。挟まないと本番ビルドが `missing-suspense-with-csr-bailout` で失敗する。

### コスト評価（NFR-3 クライアント JS 最小との関係）

- 本アプリは既に全ページで `next/link` を使用しており、`<Link>` 自体が Client Component（プリフェッチ用のクライアントランタイムを既に読み込んでいる）。したがって「初めての Client Component」による段階的なコスト跳躍ではなく、**`usePathname`+`useSearchParams`+2 本の `<a>` 相当の増分のみ**（数百バイト〜1KB 程度）。
- 挙動面のコスト: 動的ルート（トップ・詳細）は SSR 初回描画で完全な href が出るため利用者体験の劣化なし。`not-found.tsx`（各ロケール分 `generateStaticParams` で静的化されうる）だけ、初回ペイントで `/{locale}` 固定 → ハイドレーション後に（該当なら）正しいクエリ付き URL に更新、という一瞬の差分が起こり得る。404 画面はそもそも検索条件を引き継ぐ実利が薄いため許容範囲と判断する。
- テスト資産への影響: `src/ui/locale-switcher.test.tsx` は `currentPath` を直接 props で渡す現行 API に依存しており、hooks 化に伴い **`vi.mock('next/navigation', …)` で `usePathname`/`useSearchParams` をケースごとにモックする書き換えが必須**（4 ケース全て）。これは本プロジェクト初の Client Component ユニットテストになる（先例なし・SD-2 のコストとして明記すべき）。

---

## 2. ヘッダー構成（ロゴ + タイトル + 言語切替 + ログイン）

```tsx
<header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-2">
  <h1 className="text-base font-semibold">
    <Link href={`/${locale}`} className="inline-flex items-center gap-2 text-primary rounded-sm underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring">
      <img src="/logo.svg" alt="" width={24} height={24} className="shrink-0" />
      <span>{messages.home.title}</span>
    </Link>
  </h1>
  <div className="flex flex-wrap items-center gap-2">
    <Suspense fallback={<LocaleSwitcherFallback currentLocale={locale} labels={...} />}>
      <LocaleSwitcher currentLocale={locale} labels={...} />
    </Suspense>
    {showAuthLink ? <LoginLink ... /> : null}
  </div>
</header>
```

- **`nowrap` 禁止（§3）**: 外側 `header` に `flex-wrap` を付け、右側グループ（言語切替+ログイン）がモバイル幅でタイトル行の下へ折り返せるようにする。右側グループ自体にも `flex-wrap` を付け、ja/en ボタン + ログインボタンが 1 行に収まらない極小幅でも折返し可能にする。
- **固定幅を使わない（§3）**: `header` は `min-width` 前提の Flex のみ。ロゴ画像だけは意図的に固定 `width`/`height` 属性を持たせる（CLS 対策・後述）。これは「テキスト要素の固定幅禁止」の対象外（画像の intrinsic size 指定は §3 の趣旨と矛盾しない）。
- **ロゴを `h1` 内に入れる形**: 画像は `alt=""`（装飾）にし、視覚テキスト `{messages.home.title}` をそのままアクセシブルネームにする。`e2e/feedback-334.spec.ts` の `getByRole('banner').getByRole('link', { name: 'gem-hunter' })` はアクセシブルネーム完全一致で判定しており、`alt=""` の画像はアクセシブルネーム計算に寄与しない（空 alt は無視される）ため、**この改修だけでは同テストは壊れない**（実行して確認は必須・断定はしない）。ロゴにテキストを埋め込んで `<span>` 側を `sr-only` にする代替案は、名前をラスター/ベクター画像に固定してしまい将来の多言語ブランディング変更時に画像差し替えが要る点で `messages.home.title` を素のテキストで持つ現行案より劣る（i18n 耐性は a11y_i18n レンズの判断に委ねるが、実装コストの観点でも alt="" + テキスト表示が単純）。
- ヘッダー高さの固定と CLS: `<img>` に `width`/`height` 属性を明示し、ブラウザが intrinsic aspect ratio 分のスペースを事前確保できるようにする（`next/image` は本リポジトリで未使用のため、素の `<img>` に寸法属性を付ける方式が既存パターンとの一貫性が高い。要確認: `next/image` 未使用の理由がある場合はそれに合わせる）。`header` 自体は `py-2` の固定パディング + ロゴの固定サイズにより実質的に高さが安定するが、規約上は `min-height` トークンを明示するほうが安全（§3「高さが可変になる箇所は `min-height` で下限だけ固定」）。

---

## 3. 波及範囲

### 呼び出し元からの `LocaleSwitcher` 除去

| ファイル | 現状 | 変更後 |
|---|---|---|
| `app/[locale]/page.tsx` | `<main>` 先頭で `<LocaleSwitcher currentLocale currentPath={currentPath} labels={...} />` | 削除。ただし `currentPath`（`buildSearchUrl` の結果）は `SearchBody` の `retryHref` にも使われているため **変数自体は残す** |
| `app/[locale]/repos/[owner]/[repo]/page.tsx`（エラー分岐） | `<LocaleSwitcher ... currentPath={currentPath} .../>` | 削除。`currentPath` は同ファイル内で `retryHref`/自身の URL 用に残る |
| `app/[locale]/repos/[owner]/[repo]/page.tsx`（成功パス） | 同上、2 箇所目 | 削除 |
| `app/[locale]/repos/[owner]/[repo]/not-found.tsx` | **現状 `LocaleSwitcher` を呼んでいない**（コード確認済み） | 変更不要。ただし共有ヘッダーへの統合により **404 画面が初めて言語切替導線を持つ**（既存の抜け漏れの解消であり副次的な改善）。オーケストレーター/PO へ「新規獲得する挙動」として共有すべき |

- `messages.common.localeSwitcher.*` の i18n キー自体は引き続き必要（消費元が page から layout に変わるだけ）。
- 上記 3 箇所での `labels={{ navLabel: ..., localeNames: ... }}` の組み立てコードを削除できる（layout.tsx 側で 1 回だけ組み立てる）。

### 既存 E2E への影響

- **`e2e/sp-8-locale.spec.ts`**: `getByRole('navigation', { name: '言語切替' })` でロールベース取得しており、DOM 上の位置（page 内 or header 内）に依存していない。**大きな書き換えは不要な見込み**（実行して確認は必須）。ただし、テストファイル冒頭のコメントに「`LocaleSwitcher` を `layout.tsx` へ配線するのは統合担当」と明記されており、今回の変更はまさにその配線先を `layout.tsx` に確定させる作業なので、コメントの更新は必要。
- **`e2e/feedback-334.spec.ts`**: LocaleSwitcher 自体は検証対象外（h1 クリック導線のみ）。ロゴ追加によるアクセシブルネームへの影響は上記 §2 の通り実害なしと推定するが、`header` 内の DOM 構造が変わるため **回帰確認として実行必須**。
- **新規/追加が望ましい観点**（テスト設計自体は他レンズの担当だが、フロントエンド実装側から見て必要な検証ポイントとして共有）:
  - `page.locator('header').getByRole('navigation', { name: ... })` で「言語切替がヘッダー内にある」ことを明示検証する（現状の `getByRole` だけでは DOM 位置を保証しない）。
  - 詳細ページ（成功パス・エラー分岐）・`not-found.tsx` それぞれで言語切替クリック時にクエリ/パスが保持される（またはは 404 では保持不要）ことの確認。
  - 動的ルート側で「フォールバックへ落ちずに SSR 初回描画で正しい href が出る」ことは Playwright の初回レスポンス HTML（JS 無効化 or `page.goto` 直後の DOM）で検証可能（クライアント JS のちらつきが本当に起きないかの回帰網）。

### ユニットテストへの影響

- `src/ui/locale-switcher.test.tsx`: `currentPath` prop 直接指定 → `usePathname`/`useSearchParams` のモックへ全面書き換え（§1 参照）。

### `tools/check_ui_dimensions.py` への影響

- `CALL_SITE_REQUIREMENTS` に `src/ui/locale-switcher.tsx` や `app/[locale]/layout.tsx` は現状登録されていない（登録済みは `search-form.tsx` 等のみ）。LocaleSwitcher は既存どおり `buttonVariants()` の size variant 経由でのみ寸法指定しており、生の `h-*`/`text-*` を持ち込まないので **本ツールの Error 系チェックには抵触しない**。
- ただし今回ヘッダーが「常時表示される主要ナビゲーション」に格上げされるため、`ui-ux-guidelines.md` の size tier 要求を `layout.tsx` を呼び出しサイトとして新規登録すべきかは **UI/UX ガイドライン側の判断**（このレンズの決定事項ではないため他エージェント/lead へ提起するに留める）。

---

## 4. 画像の載せ方（要点のみ・詳細は上記§2に統合済み）

- `alt=""` の装飾画像 + 可視テキストの組み合わせを推奨（h1 のアクセシブルネームをテキストに一本化）。
- `width`/`height` 属性必須（CLS 対策・intrinsic size 確保）。
- SVG 推奨（解像度非依存・軽量。ラスターにする場合は `@2x` 相当の高 dpi 対応要否を perf/visual レンズと要調整）。
