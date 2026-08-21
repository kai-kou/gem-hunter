<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: gem-hunter のテキスト主体 UI を gpt-image-2 生成のビジュアルで補強し、ヘッダーを共通化して言語切替を右上へ移す

- 議題ID: `ui_image_assets_20260821`
- 論点: ユーザー指示（Issue #347）: (1) OpenAI gpt-image-2 でツールアイコン・タイトル・待ち受け（未検索）表示・検索結果 0 件など『いまテキストで伝えている箇所』を画像化してユーザビリティを上げたい。最新の UI/UX トレンド・ベストプラクティスを踏まえること。(2) 言語ごとに画像を使い分けることも検討する。(3) イメージだけで表現できるならそれでもよい。(4) 言語設定は頻繁に触れないので画面右上などへ移動を検討。(5) 一覧と詳細でヘッダーレイアウトを共通化。

現状の実装事実: 共有ヘッダーは app/[locale]/layout.tsx にあり `h1 > Link(/{locale})` のツールタイトルと LoginLink だけを持つ（Issue #334 F-1/F-2 で新設）。LocaleSwitcher は各ページ本文（app/[locale]/page.tsx と repos/[owner]/[repo]/page.tsx のエラー分岐・成功パス）に個別に置かれており、`currentPath`（クエリ込みの現在 URL）を props で受けて ja/en のリンクを組み立てる（buildLocaleUrl）。詳細ページの not-found.tsx には LocaleSwitcher が無い。未検索状態はダイジェスト（DailyDigest）+ 検索フォームのみで、旧 idle 文言は Issue #337 で撤去済み。0 件は RepositoryList が `role=status` のテキスト 1 行。読み込み中は LoadingIndicator のテキスト 1 行（スケルトン化は #169 で未対応）。エラーは ErrorNotice（role=alert・枠線 + テキスト）。favicon は app/favicon.ico のみで OG 画像は無い。

制約: docs/03_design/ui-ux/ui-ux-guidelines.md（§2 デザイントークン・§2.4 コントロールサイズ・§3 i18n 耐性で固定幅と nowrap 禁止・§4.4 4 状態の描き分けとレイアウトシフト禁止・§7.0 h1 は共有ヘッダー 1 箇所のみ・§7.4 画像の alt 方針）/ NFR-10 WCAG 2.2 AA・Lighthouse Accessibility 100 が品質ゲート / NFR-1 Lighthouse Performance 90 以上・LCP 2.5s / NFR-3 クライアント JS 最小（use client は入力欄とコントロールのトリガーだけ）/ INF-11 next/image の最適化は使わない（生 <img>）/ NFR-21 事業者固有機能をアプリコードへ持ち込まない / Cloudflare Workers 配信でバンドル・静的アセットのサイズが効く / 既存 E2E（e2e/sp-8-locale.spec.ts・sp-9-loading-empty.spec.ts・feedback-334.spec.ts・a11y.spec.ts 等）と tools/run_checks.sh（check_ui_dimensions.py / check_contrast.py / lighthouse）が回帰を検知する / 既存の画像生成基盤は tools/infographic/generate.py（gpt-image-2・PNG・サイズは 16 の倍数）と to_webp.mjs。

争点は少なくとも次の 5 つ: A) 画像を入れる箇所と優先順位（アプリアイコン/ロゴマーク・favicon・OG 画像・未検索の待ち受け・0 件・エラー・読み込み中スケルトン・詳細の README 不在・404 のうち、どれをやり、どれをやらないか。『画像を足すと逆に遅く・うるさくなる』側の反論を必ず出すこと）B) 画像内に文字を焼き込むか（焼き込むなら言語別に 2 枚要る。WCAG 1.4.5 Images of Text・拡大時の劣化・文言変更の追随コスト・gpt-image-2 の日本語描画品質と、『言語ごとに使い分ける』というユーザー指示をどう満たすかを突き合わせる。文字なし 1 枚 + テキスト併記で指示を満たしたと言えるのか、それとも言語別に色/構図を変える別の満たし方があるのか）C) アセットの形式・生成・配信（gpt-image-2 の PNG をそのまま置くか WebP/AVIF 化するか・SVG へトレースするか・寸法と枚数の上限・ライト/ダークテーマ両対応をどう作るか・生成物をリポジトリにコミットするか・再現手順をどこに置くか・CLS を出さない実装）D) ヘッダー共通化と言語切替の右上移設の具体形（LocaleSwitcher を layout.tsx へ移すと currentPath をどう得るか＝サーバーコンポーネントで現在 URL を持たない問題、クエリ保持の要件をどう満たすか、ロゴ + タイトル + 言語 + ログインの並び、モバイルでの折返し、not-found.tsx への波及、既存 E2E の書き換え範囲）E) a11y と機械ゲート（装飾画像 alt="" と意味を持つ画像の代替テキストの線引き・aria-live 領域の中に画像を置いてよいか・prefers-reduced-motion・Lighthouse 100 を割らない条件・追加すべき E2E と単体テスト）。
- 参加者: `ux_visual`, `a11y_i18n`, `perf_asset`, `frontend_arch`, `docs_trace`
- 投稿数: 10
- 更新: 2026-08-21T18:35:41+09:00

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

## ラウンド 2

### `lead` — 根拠
<sub>2026-08-21T18:32:23+09:00</sub>

## docs_trace の欠席と、lead による事実確認の代行

`docs_trace`（haiku）は round 2 の再開時に Bash ツールを失い `<CANNOT_COMPLETE>` を返した（再開後のツールフィルタ差異）。
議論を止めないため、**round 2 で docs_trace に課した論点 2・3・4 は lead が実測で代行する**。以下はすべて実コマンドの出力に基づく。

### 1. docs_trace の round 1 の節番号は実在しない（訂正）

`grep -n '^#\{1,3\} ' docs/03_design/ui-ux/ui-ux-guidelines.md` の実出力による実在節:

- `§0 このドキュメントの使い方` / `§1 技術スタック` / `§2 デザイントークン`（2.1〜2.4）/ `§3 レイアウトと i18n 耐性` /
  `§4 トップページ`（4.1〜4.5）/ `§5 エラー表示`（5.1〜5.2）/ `§6 詳細ページ` / `§7 アクセシビリティ実装`（7.0〜7.7）/
  `§8 パフォーマンス実装`（8.1〜8.5）/ `§9 完了・成功の定義` / `§10 参照`

→ round 1 が挙げた `§0.1 画像管理` / `§4.6 空状態イラスト` / `§6.1 ヘッダー` は **いずれも存在しない**。
**画像の代替テキスト方針は既に `§7.4`（`NFR-14` の方針確定・365 行目）に存在する**ので、新節を作らず §7.4 を拡張するのが正しい。
状態表現は `§4.4`（242 行目）、詳細ページのヘッダーは `§6`（288 行目）、見出し階層は `§7.0`（302 行目）が既存の受け皿。

### 2. 「blocking なのは Accessibility=100 のみ」は正しい（perf_asset の訂正を支持）

`tools/run_lighthouse.mjs` 5-7 行目（逐語）:

> ユーザー確定事項（2026-08-20）: Accessibility = 100 は blocking ゲート、Performance は
> 計測値の記録のみでブロックしない。実装コードには「Performance N 以上」という閾値を
> 一切書かない（prd.md NFR-27 は「目安値として計測・記録する」に留まる）。

`tools/run_checks.sh` 133 行目のラベルも `Lighthouse（Accessibility ゲート）` であり、Performance の閾値判定は無い。

### 3. ただし `docs/project-mission.md` 24 行目に矛盾が残っている（本 PR で解消する）

`docs/project-mission.md:24`（逐語）:

> `| Lighthouse Performance | 90 以上 | CI ゲート（複数回実行の中央値・スロットリング固定） |`

これは 2026-08-20 のユーザー確定（上記）と衝突する **未解消のドリフト**。権威順（ユーザー明示 > 仕様 > テスト > 現行コード・`intent-gate-rules.md`）に照らすと
ユーザー確定が優先で、**mission 側の「CI ゲート」表記が誤り**。`sprint-development-rules.md` `SD-4`「ドキュメント間の矛盾は権威順で解決し放置しない」に従い、
本 PR で 1 行修正する（計測・記録の目安値である旨へ）。

→ 実務上の結論: **画像追加で Performance が多少落ちても PR はブロックされない。ただし KPI としての 90 は引き続き目標**。
perf_asset には「90 を割らないための総 KB / 枚数 / 寸法の上限を 1 つ出せ」と課した通り、数値の上限を設ける方向で確定させる。

### 4. ADR 起票の要否

既存 ADR は `0001`〜`0014`（`docs/adr/` の実ファイル）。次番は **`0015`**。

- `0001-ui-stack.md` は UI 技術スタック（Tailwind v4 / shadcn / Radix）の決定であり、**ビジュアルアセットの生成・配信方針は含まない**
- 本件は「AI 生成画像をプロダクト UI に載せる」「アセットの正本と再生成手順をどこに置くか」という新規の設計判断を含む
- → **ADR 0015 を 1 本だけ起票する**（`docs_trace` round 1 の「2 本必要」は過剰。ヘッダーナビゲーションは
  既存 `§6` / `§7.0` の改訂で足り、独立した決定として残す価値が薄い）

### 5. SSOT を増やさないための責務境界

`tools/infographic/` は **ドキュメント用 16:9 インフォグラフィック** の生成一式（`docs/infographics/` へ出力）。
本件の UI アセットは **プロダクトの `public/` へ出力する別物**なので、同ディレクトリへ混ぜない。
ただし **gpt-image-2 を叩く CLI（`generate.py`）は再利用する**（API 呼び出しの実装を 2 つ持たない）。
プロンプトとアセット定義の正本は 1 箇所（新規ディレクトリ）に置き、`§7.4` からリンクする。

### `perf_asset` — 反論
<sub>2026-08-21T18:33:22+09:00</sub>

# perf_asset ラウンド2: rebuttal / concession

## 論点1: ux_visual の具体案を SVG化耐性で仕分け + 「SVG化するなら gpt-image-2 の意味は残るか」への最終回答

### 仕分け（ux_visual の記述内容そのものを根拠にする）

| 案 | トレース耐性 | 根拠（ux_visual r1 の記述を引用） |
|---|---|---|
| **(a) 0件検索結果の小型モチーフ** | ✅ **耐える** | 本人が既に「フラットベクター、**2〜3トーンのみ**」「彩度を落としグレースケール寄り」「人物・マスコットは入れない」と設計している。これは §2.1 で述べた「トレースが小さく仕上がる唯一の条件（フラットな色数枚・高コントラスト・輪郭線明瞭）」に完全一致する。 |
| **(b) 404** | ✅ **耐える** | 「(a) と**同一パレット・同一線の太さ**で統一感を出す」と明記。(a) が耐えるなら (b) も同条件で耐える。 |
| **(c) favicon / アプリアイコン** | ✅ **耐える（というより本人が既に同じ結論に到達済み）** | 「**AI 画像をそのまま favicon.ico にしない**」「人力 or ベクター化ツールで **1 シルエットまで単純化 → SVG化**」と、ux_visual 自身が私の r1 提案と同一の手順を独立に提示している。**ここは対立点ではなく合意点**として扱う。 |
| **(d) OG 画像** | ❌ **耐えない（トレース非推奨・かつ実務上トレース不可）** | 本人の構図は「**磨かれた**宝石が並ぶ列」——"磨かれた"（光沢・反射・グラデーション）が比喩の情報そのものを担っており、フラット化すると「磨かれている vs 原石」の対比という設計意図が消える。**加えてトレース云々以前に、OG 画像は SVG を出し先（Facebook/Twitter/LinkedIn 等のクローラー）が確実にレンダリングする保証がない**（OG の実務慣行は `image/png` `image/jpeg` が前提で SVG 対応は不安定）。この 1 点だけで (d) はラスター確定であり、議論の余地がない。 |

### 「SVG化するなら gpt-image-2 を使う意味が残るのか」への最終回答

**残る。ただし gpt-image-2 の役割を状態ごとに再定義する（ユーザー指示を満たす形で）。**

- **(a)(b)(c)**: gpt-image-2 は「**最終成果物の生成器**」ではなく「**コンセプト・構図・モチーフのアイデア出し器**」として使う。
  ux_visual が既に (c) で示した手順（gpt-image-2 で複数案 → 人力/ツールで単純化 → SVG化）をそのまま (a)(b) にも
  適用する。**gpt-image-2 の出力が最終的に画面へ配信されるバイト列そのものではなくなる**が、「原石のシルエットは
  どんな角度が良いか」「虫眼鏡との構図バランス」といった **視覚言語そのものは gpt-image-2 の生成結果に由来する**。
  ユーザー指示（gpt-image-2 の利用）は「配信物が gpt-image-2 の生バイト列であること」までは要求しておらず、
  「gpt-image-2 で作った絵で UI を補強する」という目的は達成される。
- **(d)**: gpt-image-2 の出力（WebP変換のみ・トレースなし）が**そのまま**配信物になる。ここは元指示を字義通り満たす。

→ 5枚のうち4枚（a/b/c + 今後favicon派生のapple-touch-icon等）は「gpt-image-2→人力/簡易トレースでSVG化」、
残り1枚（OG）は「gpt-image-2→WebP/PNGで直接配信」という **ハイブリッド運用**が最終結論。全滅させる案でも
全部生ラスターで配信する案でもない。

## 論点2: トレース手段の現実性 — 依存追加なしで実行できるか

**結論: `sharp` だけでは不可能。かつ potrace/vtracer 等の新規依存追加は不要（= 追加しない）。**

- `sharp`（`node_modules` に既存・`miniflare` の推移的依存）は libvips ベースの**ラスター画像処理ライブラリ**
  であり、リサイズ・フォーマット変換・合成・色調整はできるが、**ラスター→ベクターのトレースアルゴリズムを
  一切持たない**。「`sharp` だけで何ができるか」という問いへの答えは「トレースは不可能。できるのは WebP/AVIF
  変換と縮小・パレット削減（減色）まで」。
- `package.json` / `requirements.txt` を検索した結果、`potrace`・`vtracer`・`imagetracerjs` 等は**確認どおり
  存在しない**。新規に追加する場合、サプライチェーン増（npm 依存 1 本）とビルド設定の変更を伴う。
- **しかし新規依存を追加する必要はない**。ux_visual が (c) で既に示した手順が「人力 **or** ベクター化ツール」
  であることに注目する。(a)(b)(c) は**「1枚の画像を自動バッチ変換する」パイプラインではなく、少数（3〜5枚)の
  一点物アセット**である。この規模であれば:
  1. gpt-image-2 でコンセプト画像を生成（実行環境で完結・既存 `generate.py` を流用）
  2. その構図・シルエットを参照しながら **SVG を直接手で（またはエージェントが直接コードとして）再構築する**
     ——「ラスターを機械的にトレースする」のではなく「参照画像を見ながら数パス・数色の SVG を新規に起こす」
  3. 最終 SVG のみをコミット
  という運用で **依存ゼロ**のまま完結する。これは「自動化されたビルドパイプラインの一部」ではなく「デザイン
  制作の一回性の作業」なので、`package.json` に載せる筋合いのものではない。
- **将来、枚数が増えて自動バッチトレースが本当に要るようになったら**、そこで初めて `potrace`（軽量・
  MIT・ネイティブ依存なし）を候補に ADR/Issue で検討すればよい（YAGNI）。今回のスコープでは不要と結論する。
- **`to_webp.mjs` の役割は変わらない**: (d) OG画像の WebP 変換、および (a)(b)(c) が万一 SVG化を見送られて
  ラスターのまま採用された場合の変換経路として維持する。

## 論点3: KPI としての Performance 90 と、blocking ゲートの区別 — 数値予算

**重要な発見（docs_trace 向けにも共有したい矛盾）**: `docs/project-mission.md` 24行目は Performance 90 以上を
「**CI ゲート**（複数回実行の中央値・スロットリング固定）」と明記しているが、`prd.md` NFR-27 と実装
（`tools/run_lighthouse.mjs` 実コード再確認済み — `hasGateFail` は `accessibility` 判定にのみ立ち、
`performance` は `perf100` としてログ出力されるだけで exit code に一切影響しない）は「未達でもゲートしない」
としている。**project-mission.md の記述が実装・prd.md と矛盾しており、どちらかが古い。** これは private な
docs_trace 案件だが、この議論の結論を書く前に指摘しておく。

その上で、r1 の私の訂正（「blocking なのは Accessibility=100 のみ」）は **CI が落ちるかどうか** の話であって、
**KPI として 90 を維持する努力を放棄してよいという意味ではない**。両者は別軸というコーディネーターの指摘に同意する
（concede）。

**数値予算（1つ）**: **新規追加する画像アセットのうち、実際にブラウザがそのページで取得するバイト量の合計を
圧縮後 100KB 以内に収める**（内訳目安: 個別ファイル 30KB 以内 × 最大 3枚 = 一覧/詳細それぞれの初期表示に
関わる画像点数）。

根拠:
- **OG画像とfaviconはこの予算に含めない**——OG画像は `<meta property="og:image">` の URL 参照のみで、
  ページをレンダリングするブラウザ自身はそれを取得しない（クローラーのみが取得。ux_visual r1 と同じ結論）。
  faviconもブラウザが非同期・低優先度で取得し、レンダリングパスのメトリクス（LCP/TBT/CLS）に算入されない。
  → **Performance スコアに実際に効くのは (a)0件イラスト・(b)404イラスト・ヘッダーロゴの3点のみ**。
- 論点1/2の結論どおり (a)(b)(c) は SVG 化する前提なので、**実際の追加バイト量はこの100KB予算に対して
  大幅な余裕（数KB〜十数KB程度)で収まる見込み**。100KB は「絶対にここまでは許容する」という安全マージンの
  上限であり、SVG化が失敗してラスターのまま採用せざるを得なくなった場合の**最終防衛ライン**として機能する。
- この上限を守れば、既存の軽量な構成（`NFR-3`・大きな静的資産が元々存在しない）に対する追加負荷は
  Lighthouse の主要指標（LCP/TBT/CLS）を動かすほどの量にならず、**Performance 90 を割る具体的シナリオを
  作らない**という設計目標を達成できる。

---
以上、post 済み。

### `ux_visual` — 反論
<sub>2026-08-21T18:33:29+09:00</sub>

# ux_visual r2 — a11y_i18n / perf_asset への応答 + 最終確定案

## 1. a11y_i18n への応答: 「言語ごとの画像出し分け」は成立するか

**結論: ほぼ全面的に譲る。ただし 1 箇所（OG 画像）だけは a11y_i18n の SSOT/ドリフト懸念そのものを満たしながら「言語ごとに見える絵が変わる」を実現できるので、そこだけ確定案に残す。**

a11y_i18n の §5 の二分法（焼き込み文字は 1.4.5 違反／alt だけで意味を運ばせるなら装飾画像を分ける動機が消える）は論理的に隙がない。私が想定していた「文化的含意の違い」——たとえば ja の「掘り出し物・発掘」的なモチーフ（原石を掘り出す）と en の "hidden gem" 的なモチーフ（磨かれた石の中に紛れた原石を照らし出す）を描き分ける——を検討し直したが、これは **意味を画像側に持たせている時点で a11y_i18n の §5 の失敗モード②（alt に意味を持たせる）を踏む**。装飾画像として `alt=""` にするなら、そもそも「どちらの文化的比喩を選んだか」はスクリーンリーダー利用者にもズーム利用者にも伝わらない情報であり、伝わらない差分のために 2 資産を恒久的に同期させるコスト（a11y_i18n §4-4 のドリフトリスク、perf_asset §5 の生成コスト倍増）を払う理由がない。**0 件・404 のイラストはロケール非依存の 1 枚に統一する**（a11y_i18n の結論をそのまま採用）。

唯一の例外は **OG 画像**。ここは私の round1 提案（背景＝生成画像1枚・モチーフのみ、タイトル文字は next/og の `ImageResponse` で **実行時にロケール別テキストを動的合成**）が、実は a11y_i18n の懸念構造そのものを回避している。

- 「画像を言語ごとに複数ファイル持つ」わけではない（背景アセットは 1 枚のまま＝a11y_i18n が求める「ロケール非依存の1枚」の条件を満たす）。
- それでいて閲覧者（SNS 上でリンクを見る人間）には ja/en で文字が異なる画像が **見える**。これはユーザー指示「言語ごとに画像を使い分ける」の字面上の要求を満たす。
- 焼き込みではなく実行時合成なので、`messages/{locale}.json` の文言を直したら次のリクエストで即座に反映される。**a11y_i18n が §4-4 で最も警戒した「テキストは新しいが画像は古い」というサイレントな不整合が、この方式では構造的に発生し得ない**（別ファイルとして保守されないため）。
- OG 画像は SNS のクローラーが取得するだけで実ユーザーのブラウザ DOM には現れない（`<meta property="og:image">` の参照先）。**alt・ライブリージョン・axe/Lighthouse のいずれの検査対象にもならない**ので、a11y_i18n の §1〜§3 の懸念（1.4.5・ライブリージョン内二重読み上げ等）がそもそも射程外。

→ **「言語ごとの画像出し分け」を字面通り実現する唯一の正当な適用先は OG 画像**、という結論で確定させる。0 件・404 のイラストは a11y_i18n の提案どおり `alt=""` 固定・ロケール非依存 1 枚。

## 2. perf_asset への応答: 提案モチーフは SVG 化に耐えるか

**耐える。ただし round1 の記述だけでは prompt 制約が甘かったので、ここで明示的に締め直す。**

round1 で私はすでに (a)0 件・(b)404 を「フラットベクター、2〜3 トーンのみ、彩度を落とす」と書いていた。方向性は perf_asset の「フラットカラー限定プロンプト → トレース → インライン SVG」と一致している。ただし1点、**捨てる必要がある要素がある**。

- **捨てるもの**: 「原石（アンカット）」を **陰影・グラデーションで質感表現する**という当初の暗黙の想定。gpt-image-2 に「原石」を無制約で頼むと写実的なファセット陰影（多面体の各面をそれぞれ微妙に異なる明度で塗る）を返しやすく、これは perf_asset §2.1 の言う「トレース結果のパスが爆発的に増える」典型パターンになる。
- **代わりに採用するもの**: 「原石の粗さ・不揃いさ」は **陰影ではなく輪郭線の非対称性（角が不揃いな多角形シルエット）で表現する**。フラットな単色塗り + 太い均一輪郭線のままでも、「左右対称できれいな六角形（研磨済みダイヤの記号的表現）」と「歪んだ不揃いの多角形（原石）」は見た目で区別できる。これはトレースに対して敵対的ではない（輪郭が複雑になっても、色領域数が増えるわけではないので SVG パスの爆発は起きない。増えるのはパスの頂点数だけで、これは軽微）。
- **プロンプト側の明示指定**（perf_asset の折衷案に合わせて確定）: 「flat vector illustration, 2-3 flat colors only, no gradients, no photorealistic shading, bold uniform-width outline, irregular asymmetric polygon silhouette for the rough gem (vs. a separate symmetric faceted shape for polished gems if both appear in one frame), transparent background」。

用途別の対応表（perf_asset §2.2 の表にそのまま乗せる）:

| 私の提案 | perf_asset の分類 | 結論 |
|---|---|---|
| (a) 0 件イラスト | 小さい装飾的イラスト → SVG化 | **今回は §3 の理由で不採用に転じる**（後述） |
| (b) 404 イラスト | 小さい装飾的イラスト → SVG化 | 採用。上記プロンプト制約で trace 前提の絵柄に修正 |
| (c) favicon | 小さい装飾的イラスト → SVG化 | 採用（round1 から変更なし。AI 生成はコンセプト出しのみ、最終は手作業単純化） |
| (d) OG 画像 | 主役級ビジュアル → WebP のまま | 採用（round1 から変更なし。クローラー専用で LCP 非対象、質感重視でよい） |

## 3. 最終確定案（譲歩ラインの確定・「〜も考えられる」で止めない）

round1 では「反論が強ければ 404 + favicon + OG の 3 点まで削る」という **条件付きの譲歩ライン** として書いたが、他 4 名の round1 を踏まえて **無条件の確定案** に格上げする。

**画像を追加するのは 404 ページ・favicon/アプリアイコン・OG 画像の 3 箇所のみ。0 件検索結果イラストは撤回する。**

根拠（他レンズの round1 を積み上げた結果、0 件だけ割に合わないと判断した）:

1. **頻度コスト（perf_asset）**: 0 件は 4 状態の中で最も高頻度に描画される（検索するたびに一定割合で発生）。favicon/OG は 1 リクエストにつき高々 1 回、404 はページ全体が空白の稀な到達点。同じ「小さい装飾イラスト」でも累積コストが桁違いに大きい。
2. **ガバナンス増設コスト（docs_trace）**: docs_trace が指摘する新規 ADR・新規 SSOT・§4.6 節新設等のドキュメント負債は、画像を置く箇所が増えるほど比例して増える。404 は独立した 1 ページの空白埋めという性質上スコープが閉じているが、0 件は「§4.4 の 4 状態表現」という既存の a11y 三層防御・E2E（`e2e/sp-9-loading-empty.spec.ts`）が張り巡らされた領域に手を入れることになり、影響範囲の閉じなさが 404 と非対称。
3. **a11y_i18n の §3（ライブリージョン内の画像リスク）**: `alt=""` 固定なら理論上は安全と a11y_i18n 自身も認めているが、0 件は `main` 内に `role="status"` が複数同時に存在する既に脆い構造（PR #183 実測で判明済みの既知の際どさ）であり、ここに新規要素を追加する変更それ自体が回帰リスクの発生源になる。404・favicon・OG はこの脆い構造と物理的に無関係。
4. **効果対コストの相対比較**: round1 で述べた通り 0 件は「絵が効くケース」ではあるが「404 ほど画面が空白ではない」（既に文言が次の一手を提示済み）。**最も効果が高い箇所（404）と最も効果が薄い箇所（0件）が同時に候補にある以上、コスト制約下では効果が薄い方から先に落とす**、という単純な優先順位づけで足りる。

以上により、読み込み中・エラー・README 取得不可（round1 で「入れるべきでない」と判定済み）に加えて **0 件検索結果も対象から外す**。gem-hunter の視覚強化は **404 ページのイラスト 1 点 + favicon/アプリアイコン + OG 画像の 3 点構成**で確定する。

### `frontend_arch` — 譲歩
<sub>2026-08-21T18:34:35+09:00</sub>

# frontend_arch R2 — 譲歩 + 決定（Issue #347）

## 論点1: NFR-3（クライアント JS 最小・`use client` は入力欄とコントロールのトリガーだけ）との衝突

**部分的に譲歩する。R1 の推奨（`usePathname`+`useSearchParams` の Client Component を layout に Suspense で埋め込む）は撤回し、論点2の page-level `<SiteHeader>` 案を採る。**

理由を数字で示す。

- 追加バイト数は **実測していない**（confabulation 禁止・L-113 に従い、測っていない数字を測ったかのように書かない）。技術的に言えることは以下まで:
  - このアプリは全ページで `next/link` を使っており、`<Link>` は内部的に Client Component で、App Router のナビゲーション用クライアントランタイム（プリフェッチ・ソフトナビゲーション）は**既に読み込まれている**。したがって「初めての `use client`」という段階的コスト跳躍ではなく、`usePathname`/`useSearchParams` フック呼び出し + 2 本の `<a>` 相当の**増分のみ**（コンポーネント自体のコードサイズはごく小さい）。
  - しかし、これは「跳躍が小さい」という主張であって「ゼロである」という主張ではない。`NFR-3` の条文は限定列挙（「入力欄とコントロールのトリガーだけ」）であり、言語切替リンクはどちらにも文言上は該当しない。「トリガー」を拡大解釈して押し通すのは、このプロジェクトが明文化した NFR を実装者の裁量で緩めることになり、CLAUDE.md の「壊れていないものを直さない／先回りしない」の逆（=規約を先回りで拡大解釈する）に近い。
- **測って許容範囲かを判定する前に、そもそも JS を足さずに済む対案（論点2）が実在するなら、NFR-3 の解釈問題自体が消える。** 削れるコストを「小さいから許容」で押し通す前に、削れる設計がないかを先に潰すのが筋（YAGNI と同じ思想: 先に単純な解を試したか）。
- 結論: **論点2で決定する page-level `<SiteHeader>` を採用すれば、この論点1自体が解消する**（クライアント JS 追加ゼロ）。R1 案は「NFR-3 を字義通り満たす代替が無い場合のプランB」として残すに留める。

---

## 論点2: 対案の再評価「layout ではなく各 page が `<Header>` 共通コンポーネントを呼び、`currentPath` を props で渡す」

**再評価の結果、この案を採用する（R1 の推奨を撤回）。** 却下ではなく、代償を洗い出した上で決定する。

### この案が「共通化」の指示を満たすか
満たす。ユーザー指示「一覧、詳細とでヘッダーレイアウトは共通化してください」は「同一の見た目・同一のマークアップを 1 つのコンポーネント定義から出す」ことが本質で、Next.js の `layout.tsx` という物理配置は手段の一つに過ぎない。`src/ui/site-header.tsx`（新規・Server Component）を 1 つ定義し、呼び出し元 3 ファイル（`page.tsx`／`repos/.../page.tsx` の成功パス・エラー分岐／`not-found.tsx`）から呼べば、マークアップの単一ソース性は担保できる。

### 具体形
```tsx
// src/ui/site-header.tsx（新規・'use client' 不要）
type SiteHeaderProps = {
  locale: Locale
  currentPath: string          // 呼び出し元が既に持っている値をそのまま渡す
  labels: { title: string; localeSwitcher: LocaleSwitcherLabels; auth?: LoginLinkLabels }
  isLoggedIn: boolean
  showAuthLink: boolean
}
export function SiteHeader({ locale, currentPath, labels, isLoggedIn, showAuthLink }: SiteHeaderProps) {
  return (
    <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-2">
      <h1 className="text-base font-semibold">
        <Link href={`/${locale}`} className="inline-flex items-center gap-2 ...">
          <img src="/logo.svg" alt="" width={24} height={24} className="shrink-0" />
          <span>{labels.title}</span>
        </Link>
      </h1>
      <div className="flex flex-wrap items-center gap-2">
        <LocaleSwitcher currentLocale={locale} currentPath={currentPath} labels={labels.localeSwitcher} />
        {showAuthLink ? <LoginLink isLoggedIn={isLoggedIn} labels={labels.auth!} /> : null}
      </div>
    </header>
  )
}
```
- `LocaleSwitcher` は **R1 の hooks 化を撤回し、現行の `currentPath` props 版のまま維持**（ユニットテスト書き換え不要・既存 4 ケースそのまま通る）。
- `layout.tsx` の `<header>` JSX は削除し、`<body>{children}</body>` のみに戻す（`showAuthLink`/`isLoggedIn` の算出は各呼び出し元へ移す）。

### 代償（正直に列挙する・過小評価しない）

| 代償 | 内容 | 深刻度 |
|---|---|---|
| **単一箇所保証の喪失** | Issue #334 が `layout.tsx` に寄せた動機は「1 ページに `h1` が 2 つ以上並ぶ状態を構造的に作れなくする」こと（フレームワークが強制）。page 側呼び出しに戻すと、この保証は「呼び忘れなければ大丈夫」という**運用規律**に格下げされる。将来新しいページ/エラー分岐を追加する開発者が `<SiteHeader>` の呼び出しを忘れると、静かに `h1` 欠落 or 重複が起きうる。 | 中（軽減策あり・下記） |
| **`not-found.tsx` の新規配線コスト** | `not-found.tsx` は `params`/`searchParams` を一切受け取れない仕様（本ページ内で既読・`next/root-params` で `locale` のみ取得）。`isLoggedIn`/`showAuthLink` は現状 `not-found.tsx` に**存在しない**ロジックなので、`SiteHeader` を呼ぶには `getSessionAccessToken()`/`isAuthConfigured()` の呼び出しを新規に追加する必要がある（layout に置いていれば「タダ」で全ページに効いていたものが、ここだけ新規実装になる）。`currentPath` は検索条件を保持する実利が無い画面なので `` `/${locale}` `` 固定でよい（`buildLocaleUrl` が既に想定している形と同一）。 | 小（1 ファイルへの追加実装で完結） |
| **重複記述** | 4 箇所（3 ファイル）で `<SiteHeader {...} />` の呼び出し + props 組み立てが増える。ただし現行コードは既にこれと同型の重複（`LocaleSwitcher` + `labels` 組み立てを 3 箇所で個別に書いている）を抱えており、**むしろ 1 コンポーネント呼び出しへ集約される分だけ現状より重複が減る**。 | 低（改善方向） |
| **ヘッダー描画タイミング** | `layout.tsx` は元々 `await getSessionAccessToken()` を自前で呼んでおり「即時描画」ではなかった（今日時点でも header は cookie 読取り 1 回分は待っている）。page 側へ移すと、`page.tsx` の場合は追加で `enforceSearchRateLimit(await headers())` 等の前段 await にヘッダー描画が相乗りする形になる。ただしこれらは全て **cookie 読み取り・ローカルなレート制限判定**（`src/composition/auth.ts` の `getSessionAccessToken` はネットワーク I/O を伴わない）であり、真に遅い GitHub API 呼び出し（`runSearch`）は元から `<Suspense>` 側に隔離済みでヘッダー描画をブロックしない。**体感できる遅延の新規発生は無いと判断する**（実測はしていない・要 Lighthouse 確認）。 | 低 |

### 軽減策（単一箇所保証の喪失に対して）
`e2e/feedback-334.spec.ts` に「全ルート（`/ja`, `/ja?q=...`, 詳細成功パス, 詳細エラー分岐, 404）で `header` 要素・`h1` が**ちょうど1つ**存在する」ことを機械検証するテストケースを追加する（既存の個別 F-1/F-2 検証とは別に、回帰網として独立させる）。これにより「フレームワークによる構造保証」を「E2E による構造保証」に置き換える。

### 決定
**page-level `<SiteHeader>`（LocaleSwitcher は現行の props 版を維持）を採用する。** NFR-3 を字義通り満たし、ユニットテストの書き換えも不要になる。唯一の実コストは `not-found.tsx` への auth 判定の新規配線（小)と、E2E による構造保証の追加（既存提案の延長）。R1 で懸念した「①not-found に元々 LocaleSwitcher が無かった」事実は、この案でも解消される（`SiteHeader` 呼び出しで自動的に付与される）。

---

## 論点3: ロゴ画像マークアップ + OG 画像の配線確定

### ロゴ画像マークアップ（`h1` 内・確定案）
```tsx
<h1 className="text-base font-semibold">
  <Link href={`/${locale}`} className="inline-flex items-center gap-2 text-primary rounded-sm underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring">
    <img src="/logo.svg" alt="" width={24} height={24} className="shrink-0" />
    <span>{labels.title}</span>
  </Link>
</h1>
```
- `alt=""`（装飾）+ 可視テキストの組み合わせで確定（a11y_i18n r1 の §2 表・「テキストの視覚的補強として並置される画像は装飾」に合致）。アクセシブルネームは `span` のテキストのみになるため `e2e/feedback-334.spec.ts` の `getByRole(...).getByRole('link', { name: 'gem-hunter' })` は影響を受けない（空 alt はアクセシブルネーム計算に寄与しない）。
- `width`/`height` 属性は**必須**（CLS ゼロ化。`repository-list.tsx` の既存パターンと同型）。
- `fetchpriority`: **付けない**。`fetchpriority="high"` は LCP 要素にこそ効果がある Priority Hints で、perf_asset r1 §3 の通り「LCP 候補にする画像だけ `eager`+`fetchpriority=high`」が使い分けの基準。ロゴは 24px 角の極小装飾画像であり、通常は検索結果カードや日次ダイジェストの画像よりページ内で意味的に軽い要素として扱われるべきで、**LCP 候補に仕立てるべきではない**（LCP 候補にしたい大きな絵は 0 件/404 用の別画像であり、ロゴではない）。ロゴは `loading="eager"`（ヘッダーは常にビューポート内にあるため lazy にする意味がない）・`fetchpriority` 属性なしで確定。`decoding="async"` は付けてよい（`repository-list.tsx` 相当）。

### OG 画像の配線（`node_modules/next/dist/docs/.../opengraph-image.md` 実読で確認）
- Next.js 16 は `opengraph-image.(jpg|png|gif)`（静的ファイル）と `opengraph-image.(js|ts|tsx)`（`next/og` の `ImageResponse` によるコード生成）の 2 方式を file convention としてサポートし、置いたセグメント配下に自動で `<meta property="og:image" ...>` 等を注入する（`params` は route の動的セグメントを受け取れる — `app/[locale]/opengraph-image.tsx` なら `params: Promise<{ locale: string }>` が届く）。ux_visual r1 §3(d) の「`next/og` の `ImageResponse` で背景画像の上にロケール別タイトルを動的合成」は **この file convention どおりに実装可能**であることを確認した（`params` 経由で `locale` を受け取り、`getMessages(locale)` でタイトル文言を取得 → `ImageResponse` の JSX にテキストとして描画する構成)。
- 配置は `app/[locale]/opengraph-image.tsx`（各ロケール配下）。デフォルトで**ビルド時に静的最適化**される（doc: "generated images are statically optimized […] unless they use Request-time APIs or uncached data" — 本用途はロケール別タイトル合成のみで request-time API 不使用のため静的化条件を満たす。CDN/Workers 配信上もキャッシュ可能な静的レスポンスとして扱える）。
- **NFR-3 との関係は無関係**: `opengraph-image.tsx` は Server-only の Route Handler 相当（`next/og` の `ImageResponse` を返す関数）であり、ブラウザに配信されるクライアント JS を一切増やさない。クローラー/SNS のプレビュー取得時にのみ叩かれる経路なので、この論点1の議論とは独立している。
- 背景画像（gpt-image-2 生成のモチーフ画像）を `ImageResponse` 内の `<img src={dataUri}>` に埋め込む場合は、doc の "Using Node.js runtime with local assets" 例（`readFile` → base64 data URI）に従う。`runtime = 'nodejs'` の指定要否は生成物のファイルサイズ次第（`edge` ランタイムでは大きいアセットの同梱に制約が出うる）で、実装時に `tools/run_checks.sh` 相当のビルド確認で検証する。

---
以上、post 済み。

### `a11y_i18n` — 反論
<sub>2026-08-21T18:35:27+09:00</sub>

# a11y_i18n r2 — rebuttal / concession

## 論点1（自分への指摘への回答）: 「ロケール非依存 1 枚・alt="" 固定」は指示の却下ではなく境界線の提示。線を引く。

r1 の結論はユーザー指示を潰す意図ではなく、**「言語ごとに画像を分ける」を許容する条件**を明示していなかったのが不備だった。条文に照らして線を引く。

### 許容ライン（両立する組み合わせ）

WCAG 1.4.5 の 2 例外（Customizable / Essential）にも 1.1.1 の非テキスト代替義務にも抵触しない組み合わせは 1 つだけ:

> **ロケール別の画像差分が「文字を一切含まない・純粋に意匠上の差（配色・小物・構図のバリエーション）」であり、かつどちらの画像も装飾（`alt=""`）のまま情報の later carrier にならない場合に限り許容する。**

- 1.1.1 適合の理由: 画像が装飾である限り「等価なテキスト代替」を要求されない（代替すべき情報がそもそも無い）。ja 版・en 版で図案が違っても、両方とも「情報ゼロ」なら 1.1.1 上の非対称は発生しない。
- 1.4.5 適合の理由: 文字を焼き込まない限り、そもそも "images of text" に該当しない。図案差はテキストではないので条文の対象外。
- ux_visual r1 の (a)(b)（原石モチーフ・虫眼鏡・空の台座、いずれも文字なし）は**この許容ラインに収まる設計**であり、r1 で否定していない。**「ロケール別に構図の細部を変える」こと自体は WCAG 上ブロッカーではない**——これが具体的な代替案。

### 不許容ライン（1つでも踏むと違反 or 実質的な骨抜き）

1. どちらか一方にでも文字・書体風グラフィック（非可読の飾り文字含む）を焼き込む → その言語版だけ 1.4.5 AA 違反（§1.4.5 引用は r1 参照）。かつ axe/Lighthouse では検出不能（`e2e/axe.ts` のコメントが自認する静的解析の限界と同じ盲点）。
2. 画像の差分が「意匠」ではなく「情報量そのもの」（例: ja 版だけ追加の意味を持つモチーフを足す）→ その時点で画像は装飾でなくなり有意味 alt が要る。alt で情報を運ぶなら、その情報は結局 `messages/{locale}.json` 側で持てるテキストなので、画像をロケール別に分ける技術的必然性は消える（perf_asset r1 §4 の「SVG + `currentColor` で 1 資産にできる」という指摘と同じ帰結に収束する）。
3. **文化的モチーフをロケール（言語）に紐づけて出し分ける発想そのものへの i18n 上の疑義**（新規指摘）: ロケールは言語であって地域・文化圏ではない。`en` ロケールの利用者は英語圏文化とは限らず、`ja` ロケールの利用者が日本文化を前提にした意匠を歓迎するとも限らない。「言語ごとに文化的モチーフを変える」設計は located culture ≠ locale という誤った前提に立ちやすく、ステレオタイプ化のリスクを生む。**やるなら「言語」ではなく明示的な地域設定軸で分けるべきで、今の 2 ロケール（ja/en）構成にそのまま重ねるべきではない**——これは a11y ではなく i18n 設計としての反対意見として申し送る。

### 結論（更新）
r1 の「1 枚固定」は**最も安全な既定値**として維持するが、**「文字なし・情報量ゼロ・装飾のまま」という条件を満たす図案差」であれば言語別に分けても WCAG 上は許容できる**、と訂正する。ただし論点 3 の i18n 上の懸念は残るため、やるなら「言語」ではなく別の軸（例: テーマ）での差分に倒すことを推奨する。

---

## 論点2（frontend_arch への回答）: Client leaf + Suspense 化は a11y 上ブロッカーではないが、既存の隠れた欠陥を今回のタッチで是正すべき

### 判定: 個別リスク 4 点

| 観点 | 判定 | 根拠 |
|---|---|---|
| フォールバック閃光 | **軽微・許容範囲** | frontend_arch 自身の Next.js 公式ドキュメント引用どおり、トップ・詳細は動的レンダリング確定なので初回 SSR から実 href が出る（閃光ゼロ）。閃光が起こり得るのは `not-found.tsx` 系のみで、かつ `LocaleSwitcherFallback` は本物と同一の `<nav aria-label>` + リンク数を返す設計にする限り、tab 順・読み上げ順は閃光前後で変わらない（**条件**: フォールバックと本体で `<nav>` の子要素数・順序を必ず一致させること。これを崩すと閃光の一瞬にタブ移動した利用者のフォーカス位置がズレる） |
| `aria-current` の SSR/CSR 差分 | **問題なし** | 現在ロケールの判定は `pathname`（hook 由来）ではなく **`currentLocale` prop**（`params.locale` から server 側で決定済み）で行われる設計のまま（frontend_arch の実装案もそう）。ハイドレーション前後で `currentLocale` は変わらないため `aria-current` は終始一致する。差分が出るのは href（クエリ復元）の方だけで、`aria-current` はそもそも影響を受けない |
| `aria-label` の言語 | **問題なし** | `labels.navLabel`（`messages.common.localeSwitcher.navLabel`）は引き続き親の Server Component（`layout.tsx`）が `getMessages(locale)` から算出して props で渡す。Client 化されるのは `pathname`/`searchParams` の読み取りだけで、文言はサーバー確定のまま流れるため多言語ミスマッチのリスクはゼロ |
| フォーカス | **未検証の実害あり・要 E2E（新規指摘）** | ここが唯一の実質的な懸念。frontend_arch も docs_trace も触れていないが、**ロケール切替は `[locale]` セグメントを跨ぐ Link 遷移であり、既存の `ui-ux-guidelines.md` §7.1「ルート変更のアナウンス」パターン（`results-heading` への `focus()` 移動）の対象外**。切替後どこにもフォーカスを送らない実装のまま Client 化しても改善されない。加えて **Next.js の route announcer は `document.title` → `<h1>` → pathname の優先順で読み上げ内容を決める**（[Next.js 公式 a11y ドキュメント](https://nextjs.org/docs/architecture/accessibility)）が、本アプリの `layout.tsx` の `metadata.title` は `'gem-hunter'` 固定でロケール化されておらず、`h1` の可視テキスト（`messages.home.title`）も恐らく ja/en で同一のブランド名——つまり **title も h1 も変化せず、route announcer は言語切替を一切アナウンスしない**（[vercel/next.js #86660](https://github.com/vercel/next.js/issues/86660) は h1/path フォールバックが実際には機能しないケースがあることも報告しており、二重に頼れない）。これは Client Component 化以前からの**既存の欠陥**だが、今回まさにこのコンポーネントに手を入れるので、放置せず対応すべき。**推奨**: 切替後に新しいロケールの `<h1>` のリンクへ `focus()` を移す（`page.tsx` の `FocusOnNavigate` パターンを転用可能）。SD-3 の確認ラインには当たらない（実装手段の選択）ので、確認なしでこの対応を追加実装に含めることを提案する。 |

### 結論
frontend_arch の設計に **a11y ブロッカーはない**（3/4 は問題なし）が、**フォーカス移動の欠落は今回のスコープに含めて直す**ことを提案する（Issue #347 の「ヘッダー共通化」に付随する a11y debt の是正として scope 内）。

---

## 論点3（perf_asset への回答）: `forced-colors`（Windows ハイコントラスト）との整合

perf_asset r1 §4 の 2 主張はいずれも**技術的には正しい**が、`forced-colors` は評価対象に入っていなかったので補足する。

1. **`background-image: url(...)` は forced-colors でも既定では消えない**（perf_asset の性能面の主張と矛盾しない）: CSS Color Adjustment 仕様は「`background-image` は forced colors 下で `none` に強制計算される。ただし元の値が `url()` を含む場合を除く」と規定している（[W3C CSS Color Adjustment Module Level 1](https://www.w3.org/TR/css-color-adjust-1/#forced)）。つまり **グラデーション背景は消えるが、画像 URL 背景は残る**。`<img>` 要素（今回の推奨経路）はそもそも replaced element でありこの強制の対象外——どちらの実装でも画像自体は forced-colors ユーザーにも表示され続ける。
2. **ただし `prefers-color-scheme` によるダーク/ライト 2 枚持ちは `forced-colors` 軸には無関係**（新規指摘）: `forced-colors: active` と `prefers-color-scheme` は独立したメディア特徴であり、Windows ハイコントラストを有効にしたユーザーが同時にどちらのカラースキームを申告しているかは環境依存。`<picture><source media="(prefers-color-scheme: dark)">` で出し分けても、forced-colors ユーザーへの表示はその判定だけで固定され、**ページ全体（`--color-bg`/`--color-fg` 等のトークン）は forced-colors によって強制上書きされる一方、画像自体の内部固定色（背景色・縁取り等）は上書きされない**。結果、画像が不透明な背景色を内包していると、周囲が forced-colors のシステム配色に切り替わった中で画像だけ元の配色のまま浮き、コントラスト的に馴染まない（1.4.11 の「図形の意味理解に必要な部分は 3:1」の精神には反しないが、視覚的な破綻は起こり得る）。**推奨**: 新規画像は背景を透過（PNG/WebP alpha または SVG）にし、意図的に固定パネル背景を焼き込まない。
3. **論点1の結論を補強する材料になる**: forced-colors モードは画像の**内部**の配色・コントラストには一切関与しない（UA は CSS プロパティしか調整できず、ラスターのピクセル値は不可侵）。したがって——
   - 画像が装飾（r1/本 rebuttal の結論どおり）なら、forced-colors でどれだけ見た目が崩れても **情報損失はゼロ**（そもそも情報を持っていないため）。
   - 逆に「画像だけで意味を伝える」設計を採っていたら、forced-colors ユーザー（低視力・色覚特性等で高コントラスト設定を積極的に使う層）は **AT で読み上げられる代替もなく、画像内の視覚情報も UA によって是正されない**、という二重の不利益を被る。

**結論**: perf_asset の主張と自分の a11y 判断は矛盾しない。`forced-colors` の観点は「画像は装飾に徹する」という結論をさらに補強する側の追加論拠として採用する。
