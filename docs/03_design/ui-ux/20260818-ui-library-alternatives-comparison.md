# Next.js の UI ライブラリ比較 — shadcn/ui 以外の選択肢（2026-08-18 JST）

- **目的**: Next.js（App Router / React Server Components 前提）で使える UI コンポーネントライブラリを shadcn/ui 以外まで広げて洗い出し、**特徴・メリット・デメリット・デザイン性・実装のしやすさ・運用のしやすさ** の観点で横並び比較する
- **位置づけ**: 調査記録。本プロジェクトの実装指針の正本は [`ui-ux-guidelines.md`](./ui-ux-guidelines.md)、採用決定は [ADR 0001](../../adr/0001-ui-stack.md)。本ファイルは **「他の選択肢はどうか」を後から検証できるようにするための材料**
- **先行調査**: [UI/UX 技術スタック・実装ノウハウ リサーチ（2026-08-17）](./20260817-ui-ux-research.md)（shadcn/ui 側の詳細はこちら）

---

## 0. このドキュメントの読み方

🔴 **「一次情報で確認済み」と「未確認」を厳密に分けている。**

- 版数・公開日・週次ダウンロード数・依存関係・ライセンス表記は、**2026-08-18 JST に npm レジストリ（`registry.npmjs.org` / `api.npmjs.org`）を直接叩いた実測値**。以下では 🟢 と記す
- 設計方針・RSC 対応の可否は、**各ライブラリの公式ドキュメント本文** で確認したものだけを断定する
- 二次情報（比較ブログ等）どまりのものは ⚠️ を付ける。**比較ブログには誤りが混在していた**（§8 に実例）

数値は「その時点のスナップショット」であり、**採用判断の直前に必ず再取得すること**（`npm view <pkg> version` / `npm view <pkg> time.modified`）。

---

## 1. Next.js で効く評価軸は「一般的な UI ライブラリ比較」と違う

React 単体の比較記事は「コンポーネント数」「見た目」「学習コスト」で並べるが、**App Router + RSC では次の 4 軸が先に効く**。本ドキュメントはこの 4 軸を先頭に置く。

| 軸 | なぜ Next.js で効くか | 良い状態 |
|---|---|---|
| **RSC 適合性** | ルートに Provider を置くライブラリは、そこから下が全部クライアントコンポーネントになる。`use client` 境界が押し上がると初期 JS が増える | Provider 不要 / コンポーネント単位で `use client` が閉じる |
| **スタイルの実行時コスト** | ランタイム CSS-in-JS（Emotion 等）はサーバーで完結せず、ハイドレーション時に CSS を生成・挿入する | ビルド時に CSS が確定する（Tailwind / CSS Modules / ゼロランタイム CSS-in-JS） |
| **配布モデル** | npm 依存だと生成物が `node_modules` の中にあり、`use client` の付き方をレビューできない | コード生成方式なら自リポジトリに残り、PR で目視できる |
| **アクセシビリティ保証の一次情報** | Lighthouse Accessibility を CI ゲートにすると、プリミティブの a11y 品質が実装のブロッカーになる | 準拠規格・テスト環境を公式が明記している |

> 🔵 **補足**: 「ランタイム CSS-in-JS = 即アウト」ではない。Emotion 系でも Next.js 公式の統合パッケージでストリーミング対応は取れている（後述の MUI）。効くのは **Provider によって押し上がる `use client` 境界** のほうが大きい。

---

## 2. 選択肢の地図 — 4 カテゴリに分かれる

「shadcn/ui の代わり」を探すとき、**同じ土俵にないものが混ざる** のが混乱の元になる。まずカテゴリで分ける。

```
A. コード配布（copy & own）    … shadcn/ui, HeroUI v3(CLI), Catalyst, Park UI
   └ 生成物が自分のリポジトリに入る。ライブラリ更新の概念がない

B. ヘッドレス基盤（primitives） … Base UI, Radix UI, React Aria Components, Ark UI, Headless UI, Ariakit
   └ 挙動と a11y だけ。見た目は自分で作る。A の土台でもある

C. フル装備・スタイル付き      … MUI, Ant Design, Mantine, Chakra UI, HeroUI, PrimeReact, Fluent UI, Flowbite React
   └ npm 依存。デザインと大量のコンポーネントが最初から揃う

D. CSS のみ（JS なし）         … daisyUI, Tailwind Plus
   └ クラス名/マークアップだけ。挙動は自前 or B と組む
```

**shadcn/ui の代替になりうるのは A と C。** B は「shadcn/ui の中身」なので代替ではなく **より低いレイヤー**、D は「見た目だけ」なので a11y 込みの挙動は別途必要になる。

---

## 3. 一覧比較表（実測値ベース）

### 3.1. 版数・規模・ライセンス 🟢

| ライブラリ | 最新版 | 公開日 | 週次 DL | ライセンス | カテゴリ |
|---|---|---|---|---|---|
| **Radix UI**（Primitives） | `@radix-ui/react-dialog` 1.1.23 | 2026-07-24 | **60.9M** | MIT | B |
| **Material UI（MUI）** | `@mui/material` 9.3.1 | 2026-08-06 | **8.70M** | MIT（MUI X の一部は商用） | C |
| **Base UI** | `@base-ui/react` 1.7.0 | 2026-08-04 | **8.58M** | MIT | B |
| **Ant Design** | `antd` 6.6.1 | 2026-08-17 | 3.05M | MIT | C |
| **React Aria Components** | `react-aria-components` 1.20.0 | 2026-07-31 | 2.58M | Apache-2.0 | B |
| **Mantine** | `@mantine/core` 9.5.1 | 2026-08-02 | 2.08M | MIT | C |
| **Chakra UI** | `@chakra-ui/react` 3.36.1 | 2026-07-19 | 1.17M | MIT | C |
| **daisyUI** | `daisyui` 5.7.18 | 2026-08-18 | 785K | MIT | D |
| **Ark UI** | `@ark-ui/react` 5.38.2 | 2026-08-17 | 671K | MIT | B |
| **HeroUI**（旧 NextUI） | `@heroui/react` 3.2.4 | 2026-08-07 | 448K | MIT | A/C |
| **Fluent UI React** | `@fluentui/react-components` 9.74.6 | 2026-08-11 | 350K | MIT | C |
| **PrimeReact** | `primereact` 11.1.0 | 2026-08-05 | 284K | 🔴 **v11 から独自ライセンス** | C |
| **Flowbite React** | `flowbite-react` 0.12.17 | 2026-02-09 | 102K | MIT | C |
| （参考）shadcn CLI | `shadcn` 4.18.0 | 2026-08-13 | — | MIT | A |

> **Radix の 60.9M は「Radix 単体の人気」ではない。** shadcn/ui 経由で全世界のプロジェクトに `@radix-ui/react-*` が入るため、**依存の依存として数えられた値**。同じ理由で Base UI の 8.58M も、2026-07 に shadcn/ui の既定プリミティブが Base UI へ移った影響を強く含む。**DL 数をそのまま「良さ」と読まないこと。**

### 3.2. Next.js / RSC 適合性（一次情報で確認）

| ライブラリ | スタイル方式 | ルート Provider | `use client` 境界 | 判定 |
|---|---|---|---|---|
| **shadcn/ui** | Tailwind v4（ビルド時） | 不要 | 生成コード側で制御（`components.json` の `rsc`） | ◎ |
| **HeroUI v3** | Tailwind v4 + CSS 変数 | **不要**（公式明記） | コンポーネント単位 | ◎ |
| **Base UI / Radix / React Aria / Ark UI** | 非スタイル（自由） | 不要 | 使う側が決める | ◎ |
| **daisyUI / Tailwind Plus** | Tailwind クラスのみ | 不要 | JS を持たないので発生しない | ◎ |
| **Mantine** | CSS ファイル + PostCSS | **必要**（`MantineProvider`） | 🔴 公式が「**Mantine components cannot be used as server components**」と明記。各エントリに `'use client'` が自動付与される | △ |
| **Material UI** | **Emotion**（ランタイム。Pigment CSS は任意 peer） | 必要（`AppRouterCacheProvider`） | テーマ定義ファイルに `'use client'` が必要。`page.tsx` はサーバーのまま保てる設計 | △ |
| **Chakra UI v3** | Emotion（`@emotion/react` が peer） + Ark UI | 必要（`ChakraProvider`） | ルートで client 化 | △ |
| **Ant Design v6** | CSS-in-JS（v6 は CSS 変数モード） | 必要 | ルートで client 化 | △ |

🔴 **Mantine / MUI / Chakra / Ant Design を「RSC 非対応」と読まないこと。** いずれも App Router で動く。効くのは「**インタラクティブでない画面まで含めてクライアントバンドルに乗る**」という初期 JS の話であり、要件次第で十分許容できる。

---

## 4. 個別評価

観点は毎回同じ 6 つ（**特徴 / メリット / デメリット / デザイン性 / 実装のしやすさ / 運用のしやすさ**）で揃えている。

### 4.1. Material UI（MUI）— 「全部入り」の最大手

- **特徴**: Material Design 準拠のフルスタック UI。別売りの **MUI X**（DataGrid / DatePicker / Charts / TreeView）まで含めると、業務システムで必要なものはほぼ揃う。v9 が 2026-04-07 に出た（🟢 **v8 は存在せず 7 → 9 に飛んでいる**）
- **メリット**: 週次 8.70M でエコシステムが圧倒的。求人・記事・AI の学習データすべてが厚く、**詰まったときに答えが見つかる確率が最も高い**。企業向けサポート契約もある
- **デメリット**: ① **スタイルエンジンは今も Emotion**（`@emotion/react` / `@emotion/styled` が optional peer、Next.js 統合で `@emotion/cache` を要求）。ゼロランタイム化を狙った **Pigment CSS は 2026-08 時点でも alpha 扱い・作業停止中**（公式リポジトリの説明文）で、`@mui/material-pigment-css` は任意の peer にとどまる ② コンポーネント数が多い＝ API 表面積が大きく、`sx` / `styled` / `theme` の使い分けを揃えないとコードベースが荒れる ③ Material Design の匂いが強く、**脱・Material には相応の工数**
- **デザイン性**: ⭐⭐⭐（**「整っている」が「今どき」ではない**）。Material Design そのものが好き嫌いを分ける。テーマで色や角丸は変えられるが、シルエットは Material のまま残りやすい
- **実装のしやすさ**: ⭐⭐⭐⭐⭐（ドキュメント量・サンプル量が最強。**AI 補完との相性も最良**）
- **運用のしやすさ**: ⭐⭐⭐⭐（メジャー更新は重いが、移行ガイドと codemod が毎回用意される。長期保守の安心感は随一）
- **こう使う**: 管理画面・業務系で **DataGrid が要る** なら第一候補。v9 では新規プリミティブ `NumberField` が Base UI ベースで作られており、**MUI 自身が土台を Base UI に寄せ始めている** 点は将来の安心材料

### 4.2. Mantine — RSC 時代の総合力トップ

- **特徴**: 100 以上のコンポーネント + 大量のフック。**スタイルは CSS ファイル + PostCSS プリセット**（ランタイム CSS-in-JS ではない）。v9（🟢 9.5.1）で `@mantine/schedule`（カレンダー/スケジューラ）、FloatingWindow、Marquee 等が追加され、**React 19.2+ 必須** になった
- **メリット**: ① 「フォーム・通知・モーダル・リッチテキスト・チャート・日付」まで **公式パッケージで揃う**（サードパーティ探しが要らない） ② `useDisclosure` などフック群が実務で効く ③ ランタイム CSS-in-JS でないぶんスタイル計算が軽い ④ 週次 2.08M と伸びており、**Chakra からの移住先として定着**
- **デメリット**: 🔴 **公式が「Mantine のコンポーネントはサーバーコンポーネントとして使えない」と明記している**（すべてのコンポーネントが default props と Styles API のために context を要求する）。各エントリに `'use client'` が自動で付くため書き忘れは起きないが、**RSC の恩恵は構造的に受けにくい**。加えて PostCSS プリセットの設定ファイル（`postcss.config.cjs`）が必須
- **デザイン性**: ⭐⭐⭐⭐（**素の状態が最もクセがない**。Material でも Ant でもない中庸なモダンさで、そのまま出しても違和感がない）
- **実装のしやすさ**: ⭐⭐⭐⭐⭐（**スタイル props + フックで書き味が良い**。ドキュメントの実例密度が高い）
- **運用のしやすさ**: ⭐⭐⭐⭐（更新が速く breaking もそれなり。v9 では `Collapse` の `in` → `expanded`、`Grid` の `gutter` → `gap` 等の改名が入った）
- **こう使う**: **「shadcn/ui は自由すぎる、MUI は重い」の中間**。社内ツール・SaaS ダッシュボードを速く作るなら最有力

### 4.3. Ant Design — エンタープライズ／データ密度特化

- **特徴**: 中国発の業務システム標準。v6 が 2026 年に登場し（🟢 `antd` 6.6.1）、**React 18 以降のみサポート・CSS 変数モード（`cssVar`）** に舵を切った。v5 からは互換パッケージや codemod なしで上げられる
- **メリット**: ① **テーブル・フォーム・ツリーの作り込みが世界最高水準**（フィルタ・ソート・仮想化・編集が標準装備） ② デザイントークンが体系化されており、Default / Dark / Glass 等のプリセットがある ③ Ant Design Pro という管理画面テンプレート群が別に存在する
- **デメリット**: ① **バンドルが重い**（フル装備の代償） ② デザインが「Ant らしさ」に強く寄り、**コンシューマ向けサービスだと業務っぽく見える** ③ ドキュメント・Issue に中国語が混じる ④ CSS-in-JS 起点なのでルート client 化は避けにくい
- **デザイン性**: ⭐⭐⭐（**情報密度重視**。整然としているが「かっこいい」方向ではない）
- **実装のしやすさ**: ⭐⭐⭐⭐（やりたい業務 UI がだいたい標準機能で足りる。API は大きい）
- **運用のしやすさ**: ⭐⭐⭐⭐（v5 → v6 が非破壊的に上げられたのは高評価。更新頻度も高い）
- **こう使う**: **管理画面・社内システムで「テーブルが主役」なら最短距離**

### 4.4. Chakra UI v3 — 書き味は最高、ランタイムは残る

- **特徴**: v3 で全面的に作り直され、**コンポーネントロジックは Ark UI（Zag.js の状態機械）へ、スタイルは Panda CSS 由来の recipes API へ** 移行した（🟢 `@chakra-ui/react` の依存に `@ark-ui/react` と `@pandacss/is-valid-prop` が実在する）
- **メリット**: ① スタイル props の書き味は依然として React 界で最上位 ② Ark UI 化で複雑コンポーネント（Dialog / Popover / Slider）の挙動品質が上がった ③ framer-motion 依存を外してバンドルが軽くなった
- **デメリット**: 🔴 **「v3 で Emotion を脱してゼロランタイムになった」は誤り。** 🟢 npm 上の `@chakra-ui/react` 3.36.1 の peerDependencies は **今も `@emotion/react` >= 11 を要求** しており、公式 Next.js ガイドも `npm i @chakra-ui/react @emotion/react` を指示している（§8 参照）。加えて ① コンポーネント数が MUI / Mantine より少なく、データテーブル・リッチテキスト・高度な日付入力は別パッケージ ② 公式ガイドに **Turbopack の既知問題で `--webpack` を付ける回避策** が記載されている
- **デザイン性**: ⭐⭐⭐⭐（清潔で素直。ただし v3 のプリセットは v2 より地味という評価もある）
- **実装のしやすさ**: ⭐⭐⭐⭐⭐（**style props に慣れていれば最速**）
- **運用のしやすさ**: ⭐⭐⭐（v2 → v3 の移行が非常に重かった実績があり、そこで離脱した層が Mantine に流れた）
- **こう使う**: **既に Chakra 資産がある** か、style props の書き味を最優先する場合

### 4.5. HeroUI v3（旧 NextUI）— 「デザイン性 × Tailwind × React Aria」

- **特徴**: NextUI から改名し、**v3 で完全に書き直された**。🟢 `@heroui/react` 3.2.4 の peerDependencies は `react >= 19` / `tailwindcss >= 4` / `react-aria-components ^1.20` で、**React Aria + Tailwind v4 の上に建っている** ことがパッケージ定義から確認できる。75+ の Web コンポーネントに加え React Native 版も持つ。**CLI でコンポーネントを追加する導線（コード配布に近い使い方）も用意されている**
- **メリット**: ① **素のデザインが最も「今どき」**（角丸・影・モーションの完成度が高く、そのまま製品として出せる） ② **Provider ラッパー不要** を公式が明記しており、RSC 前提の Next.js と噛み合う ③ CSS-in-JS ランタイムがない ④ 挙動と a11y は React Aria（Adobe）が担保 ⑤ Card.Header のような **compound component API** で入れ子 props 地獄を避けている
- **デメリット**: ① 🔴 **React 19 と Tailwind v4 が必須**（peer が `>=19` / `>=4.0.0`。古いスタックには載らない） ② **v2 → v3 が全面書き換え** で、v2 資産の移行は実質作り直し。旧 `@nextui-org/react` は 🟢 2.6.11 / 2025-01-05 で止まっており **旧名パッケージは事実上終了** ③ 週次 448K と MUI / Mantine より 1 桁小さく、**情報量とサードパーティ資産は薄い** ④ デザインの個性が強いぶん、独自ブランドに寄せると HeroUI らしさと衝突しやすい
- **デザイン性**: ⭐⭐⭐⭐⭐（**本比較の中で最も美しい既定値**）
- **実装のしやすさ**: ⭐⭐⭐⭐（Tailwind を書ける前提なら速い。Provider 不要も効く）
- **運用のしやすさ**: ⭐⭐⭐（月次マイナーリリースを掲げており活発。ただしメジャー間の断絶実績があり、**長期運用の実績はまだ短い**）
- **こう使う**: **見た目の完成度を最優先するコンシューマ向けプロダクト**。「shadcn/ui は自分でデザインを決めないといけないのが辛い」の直接の答えになる

### 4.6. Base UI — shadcn/ui の新しい既定（ヘッドレス）

- **特徴**: **Radix / Material UI / Floating UI の開発者が合流して作った非スタイルのプリミティブ集**。🟢 v1.0.0 が 2025-12-11 に出て、2026-08-04 時点で 1.7.0。公式は 40+ コンポーネントと明記。2026-07 に **shadcn/ui の新規プロジェクト既定が Radix → Base UI に変更** された
- **メリット**: ① フルタイムの開発体制（MUI 社）で、**Radix より更新が活発** ② スタイル非依存（Tailwind / CSS Modules / CSS-in-JS どれでも） ③ WAI-ARIA 準拠と、スクリーンリーダー含む多環境テストを公式が明記 ④ MUI 本体も v9 の新規コンポーネントを Base UI で作り始めており、**将来の主流になる公算が高い**
- **デメリット**: ① 🔴 **npm パッケージ名が移動している**（旧 `@base-ui-components/react` は 1.0.0-rc.0 で停止、現行は `@base-ui/react`）。**古い記事のコピペが通らない** ② 見た目はゼロなので、デザインを自前で用意するコストは shadcn/ui などと組む前提 ③ Radix より歴史が浅く、エッジケースの蓄積はこれから
- **デザイン性**: —（提供しない）
- **実装のしやすさ**: ⭐⭐⭐（プリミティブ単体で使うなら、スタイルを全部書く覚悟が要る。shadcn/ui 経由なら ⭐⭐⭐⭐⭐）
- **運用のしやすさ**: ⭐⭐⭐⭐（更新が活発で、shadcn/ui 既定という強い後ろ盾がある）

### 4.7. Radix UI（Primitives / Themes）— 実績の厚いヘッドレス

- **特徴**: ヘッドレスの事実上の標準だったライブラリ。🟢 Primitives は 2026-07-24 に更新があり **メンテは継続**。一方で **`@radix-ui/themes`（スタイル付きの上物）は 3.3.0 / 2026-01-31 と更新間隔が空いている**
- **メリット**: ① 🔴 **アクセシビリティ保証が一次情報で明文化されている**（WAI-ARIA Authoring Practices 準拠、NVDA / JAWS / VoiceOver でテスト済み）。本プロジェクトが ADR 0001 で Base UI ではなく Radix を選んだ理由がこれ ② 数年ぶんの実運用で踏まれたバグが潰れている ③ shadcn/ui でも `-b radix` で引き続き選べる（非推奨化されていない）
- **デメリット**: ① 中心開発者が Base UI 側に移っており、**新機能の主戦場は Base UI に移りつつある** ② Themes は「そこそこ整った見た目」を高速に得られるが更新が緩やか
- **デザイン性**: —（Primitives）/ ⭐⭐⭐（Themes）
- **実装のしやすさ**: ⭐⭐⭐（単体）/ ⭐⭐⭐⭐⭐（shadcn/ui 経由）
- **運用のしやすさ**: ⭐⭐⭐⭐（安定しているが、**長期的には Base UI への移行判断が発生する**）

### 4.8. React Aria Components（Adobe）— a11y 最強のヘッドレス

- **特徴**: Adobe 製。🟢 1.20.0 / 週次 2.58M。**50+ コンポーネント**、30 以上の言語・13 の暦体系に対応した国際化、アクセシブルなドラッグ&ドロップ、キーボード複数選択、テーブル列リサイズまで含む
- **メリット**: ① **アクセシビリティと国際化の作り込みが業界最深**（日付・数値のロケール処理まで面倒を見る） ② `[data-pressed]` `[data-selected]` などのデータ属性 + Tailwind プラグインでスタイリングでき、Tailwind と相性が良い ③ 高レベルコンポーネント / コンテキスト / 低レベルフックの **3 段階の抽象度** を選べる ④ HeroUI や shadcn/ui（React Aria ベース版）の土台としても使われている
- **デメリット**: ① API がやや冗長で **学習曲線は Radix / Base UI より急** ② 見た目ゼロ ③ ライセンスが Apache-2.0（MIT ではない。実務上ほぼ問題ないが法務確認の対象になりうる）
- **デザイン性**: —
- **実装のしやすさ**: ⭐⭐⭐（機能が多いぶん覚えることも多い）
- **運用のしやすさ**: ⭐⭐⭐⭐⭐（**Adobe が自社製品で使い続けている** ので枯れ方が違う）
- **こう使う**: **アクセシビリティが契約要件・法令要件**（公共・大企業・海外展開）のとき

### 4.9. Ark UI — マルチフレームワーク対応のヘッドレス

- **特徴**: Chakra チーム製。🟢 5.38.2 / 週次 671K。**Zag.js の状態機械** をコアに、**React / Vue / Solid / Svelte で同一 API** を提供する。Chakra UI v3 の中身でもある
- **メリット**: ① 複数フレームワークを跨ぐ組織で **デザインシステムを一本化できる** ② 状態機械ベースなので複雑コンポーネントの挙動が堅い ③ 更新が非常に活発
- **デメリット**: ① React 単体で見ると Radix / Base UI に対する決定打が弱い ② 情報量は英語圏でも中程度
- **運用のしやすさ**: ⭐⭐⭐⭐

### 4.10. PrimeReact — 🔴 ライセンス変更に注意

- **特徴**: 90 以上の巨大コンポーネント群（DataTable / OrgChart / TreeTable / WYSIWYG まで）
- **🔴 最重要の注意**: 🟢 **npm メタデータ上で v11 からライセンス表記が変わっている。** `primereact` 10.9.7（2025-08-15）は `license: MIT` かつ GitHub リポジトリが紐づいていたが、**11.0.0（2026-07-15）以降は `SEE LICENSE IN LICENSE.md` になり、`repository` フィールドが消えている**。⚠️ 二次情報では「v11 から商用 PrimeUI ライセンスへ移行し、公開リポジトリはアーカイブ、一定規模以下は無償の Community ティア」と報じられている。**採用前に `LICENSE.md` と公式ライセンスページを必ず自分で読むこと**（本ドキュメントは条件の詳細を一次情報で確認できていない）
- **メリット**: コンポーネント網羅性は最大級。既存 v10（MIT）はそのまま使い続けられる
- **デメリット**: **新規採用でライセンスリスクを負う**。デザインはやや古典的
- **こう使う**: 🔴 **法務確認が済むまで新規採用しない** のが安全

### 4.11. Fluent UI React v9（Microsoft）

- **特徴**: Microsoft の Fluent Design 実装。🟢 9.74.6 / 週次 350K。60+ コンポーネント
- **メリット**: ① Microsoft 製品（Teams / Office アドイン）と **見た目が完全に揃う** ② Microsoft が実際の支援技術ユーザーでテストしており a11y が強い ③ Griffel によるアトミック CSS でスタイル性能が良い
- **デメリット**: ① **Microsoft 文脈の外だと「Office っぽさ」が浮く** ② 日本語情報が薄い ③ 汎用 Web サービス向けの装飾性は低い
- **こう使う**: **Teams アプリ・Office アドイン・Microsoft 365 連携が要件** のときは実質一択

### 4.12. daisyUI — JS ゼロ、最軽量

- **特徴**: Tailwind プラグイン。🟢 5.7.18（2026-08-18 に更新されており非常に活発）。`btn` `card` `modal` のような **セマンティックなクラス名を提供するだけ** で JavaScript を一切含まない
- **メリット**: ① **RSC 適合は自動的に完璧**（JS がないので `use client` の議論自体が発生しない） ② クラス名が短く、Tailwind のユーティリティ地獄を避けられる ③ テーマが 35 種類プリセットされ、切り替えが CSS だけで済む ④ React / Vue / Svelte / 素の HTML すべてで同じマークアップが使える
- **デメリット**: 🔴 **挙動と a11y は一切面倒を見ない。** Dialog のフォーカストラップ、Combobox のロービングタブインデックス、Escape 処理などは自前実装か、B カテゴリとの併用が必要 ② デザインの独自性は出しにくい（daisyUI らしさが出る）
- **デザイン性**: ⭐⭐⭐
- **実装のしやすさ**: ⭐⭐⭐⭐⭐（**静的なマークアップ主体なら圧倒的に速い**）
- **運用のしやすさ**: ⭐⭐⭐⭐⭐（依存が CSS だけなので壊れる余地が小さい）
- **こう使う**: **LP・マーケティングサイト・静的ページ中心**。アプリ的な複雑 UI が来たら B カテゴリを足す

### 4.13. Tailwind Plus / Catalyst（有償）

- **特徴**: Tailwind 本家が販売する **500+ のコンポーネント・テンプレート集** と、React 向け UI キット **Catalyst**。⚠️ 買い切り（個人ライセンス 299 ドル / チーム 979 ドル、二次情報）
- **メリット**: ① **デザイン品質が本家保証** で、そのまま製品水準 ② コードを自分のリポジトリに貼るので所有権は自分にある ③ Next.js 前提のテンプレートが多い
- **デメリット**: ① **有償**（社内の購買プロセスが要る） ② ライセンス上、成果物の再配布に制約がある ③ 挙動は Headless UI 依存で、コンポーネント網羅性は C カテゴリに劣る
- **こう使う**: **デザイナー不在で、見た目の質を金で買いたいとき**

### 4.14. shadcn/ui エコシステム（＝ shadcn/ui を捨てずに不満を解消する道）

「shadcn/ui 以外」を探す動機の多くは **「見た目が全部同じになる」「複雑コンポーネントが足りない」** の 2 つだが、これは **レジストリの追加で解消できる**（別ライブラリへの乗り換えが唯一の解ではない）。

| 不満 | 解 | 中身 |
|---|---|---|
| 見た目が没個性 | **tweakcn** | shadcn/ui 用のビジュアルテーマエディタ。色・角丸・影を GUI で作ってトークンを書き出す |
| アニメーションが弱い | **Magic UI / Aceternity UI** | Motion ベースの装飾コンポーネント群（150+ / 200+） |
| 複雑コンポーネントがない | **Kibo UI** | Gantt・Kanban・コードエディタ・カラーピッカー・ファイルドロップゾーンなどを shadcn CLI 経由で追加 |
| 部品のバリエーション不足 | **Origin UI** | 数百のコピペ可能な派生コンポーネント |

🟢 shadcn CLI は 4.18.0（2026-08-13）まで進んでおり、レジストリのサーバーサイド検索、GitHub レジストリ、MCP サーバー対応など **「配布プラットフォーム」方向に進化している**。⚠️ これらサードパーティレジストリの品質・保守性は個別に見極めが必要（一次情報での検証は本調査の範囲外）。

---

## 5. 観点別の総合評価

⭐ は本調査での相対評価（絶対的な優劣ではなく、**Next.js App Router 前提での相対値**）。

| ライブラリ | デザイン性 | 実装のしやすさ | 運用のしやすさ | RSC 適合 | a11y | 総合の性格 |
|---|---|---|---|---|---|---|
| **shadcn/ui**（基準） | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ◎ | ◎ | 自由と制御 |
| **HeroUI v3** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ◎ | ◎ | 美しさ最優先 |
| **Mantine** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | △ | ○ | 総合力 |
| **Material UI** | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | △ | ○ | 安心と物量 |
| **Ant Design** | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | △ | ○ | 業務データ |
| **Chakra UI v3** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | △ | ○ | 書き味 |
| **daisyUI** | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ◎ | △ | 最軽量 |
| **Base UI** | — | ⭐⭐⭐ | ⭐⭐⭐⭐ | ◎ | ○ | 次世代の土台 |
| **Radix UI** | — | ⭐⭐⭐ | ⭐⭐⭐⭐ | ◎ | ◎ | 枯れた土台 |
| **React Aria** | — | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ◎ | ◎◎ | a11y 最強 |
| **Fluent UI** | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | △ | ◎ | MS 連携 |
| **PrimeReact** | ⭐⭐ | ⭐⭐⭐⭐ | ⚠️ | △ | ○ | 網羅性（要ライセンス確認） |

---

## 6. 用途別の推奨（決定フロー）

```
アクセシビリティが法令・契約の要件か？
  └ YES → React Aria Components（+ 自前スタイル or shadcn/ui の React Aria 版）

管理画面で「データテーブルが主役」か？
  ├ YES かつ Material 系の見た目でよい → Material UI（+ MUI X DataGrid）
  └ YES かつ情報密度を最優先        → Ant Design v6

見た目の完成度を最優先し、React 19 + Tailwind v4 に乗れるか？
  └ YES → HeroUI v3

社内ツール・SaaS を「速く・破綻なく」作りたいか？
  └ YES → Mantine

静的ページ・LP 中心で JS を極力積みたくないか？
  └ YES → daisyUI（複雑 UI が出てきたら Base UI / Radix を足す）

デザインを自分で決めたい・use client 境界を PR で管理したいか？
  └ YES → shadcn/ui（不満は §4.14 のレジストリで埋める）

デザイナー不在で品質を金で買えるか？
  └ YES → Tailwind Plus / Catalyst
```

---

## 7. 本プロジェクト（gem-hunter）への含意

現行の決定は [ADR 0001](../../adr/0001-ui-stack.md)（Tailwind CSS v4 + shadcn/ui、プリミティブは **Radix を明示指定**）。本調査の結論として、**この決定を変更する理由は見つからなかった**。根拠は次の 3 点。

1. **`NFR-27`（Lighthouse Accessibility = 100 を CI ゲート化）に対して、a11y 保証が一次情報で明文化されているのは Radix と React Aria の 2 つだけ。** 本 ADR の選択理由はそのまま有効
2. **`NFR-3`（`use client` を最小化）に対し、C カテゴリはすべて構造的に不利。** 特に Mantine は公式が「サーバーコンポーネントとして使えない」と明記しており、要件と正面から衝突する
3. **`NFR-28`（初期 JS バンドル）に対し、コード生成方式は「使った分だけ」が保証される**

一方で、次の 2 点は **将来の再検討トリガー** として記録しておく。

| トリガー | 再検討の中身 |
|---|---|
| shadcn/ui の Radix 版サポートが縮小した / Base UI の a11y 保証が一次情報で明記された | ADR 0001 の「Radix 明示指定」を Base UI に切り替える。MUI 本体も v9 の新規コンポーネントを Base UI で作り始めている |
| 「見た目を自分で決めるコスト」がスプリント速度のボトルネックになった | **HeroUI v3** への切り替え、または **tweakcn によるテーマ生成**（§4.14）。前者は全面書き換え、後者は差分が小さいので **まず tweakcn を試す** |

---

## 8. ⚠️ 二次情報に見つかった誤り（同じ罠を踏まないための記録）

本調査で参照した比較ブログには、**一次情報と矛盾する記述が複数あった**。

| 二次情報の主張 | 一次情報での実際 |
|---|---|
| 「Chakra UI v3 は Emotion を脱し Panda CSS のゼロランタイムになった」 | 🟢 `@chakra-ui/react` 3.36.1 の peerDependencies は **今も `@emotion/react` >= 11 を要求**。公式 Next.js ガイドも `@emotion/react` のインストールを指示する。正しくは「**recipes API が Panda CSS 由来**」であってランタイムの置換ではない |
| 「MUI は Pigment CSS でゼロランタイム化済み」 | 🟢 Pigment CSS は **alpha・作業停止中**（公式リポジトリの説明文）。`@mui/material-pigment-css` は **任意の peer** にとどまり、既定は今も Emotion |
| 「Base UI は `@base-ui-components/react`」 | 🟢 そのパッケージは **1.0.0-rc.0 で停止**。現行は **`@base-ui/react` 1.7.0** |
| 「NextUI を使えばよい」 | 🟢 `@nextui-org/react` は **2.6.11 / 2025-01-05 で停止**。後継は `@heroui/react` |

> 🔴 **教訓**: UI ライブラリの比較は陳腐化が速い。**版数・依存関係・ライセンスは npm レジストリを直接叩いて確認する**（本ドキュメントの 🟢 はすべてその手順で取得した）。

---

## 9. 未確認事項（採用判断の前に潰す）

| # | 未確認事項 | 確認方法 | 影響 |
|---|---|---|---|
| 1 | PrimeReact v11 のライセンス条件（Community ティアの適用範囲・料金） | `LICENSE.md` と公式ライセンスページを直接読む | 大（採用可否） |
| 2 | 各ライブラリの **実測バンドルサイズ差**（KB） | 同一画面を各ライブラリで実装して `@next/bundle-analyzer` で比較 | 中（`NFR-28`） |
| 3 | Base UI の a11y 保証に関する一次情報の有無（テスト環境・準拠規格の明記） | Base UI 公式の Accessibility ページを精読 | 中（ADR 0001 の再検討トリガー） |
| 4 | HeroUI v3 の Next.js 16 での動作実績 | 実機で最小プロジェクトを作って確認 | 中（乗り換え候補としての評価） |
| 5 | サードパーティ shadcn レジストリ（Kibo UI 等）の保守性・ライセンス | 各リポジトリの更新頻度と LICENSE を確認 | 小〜中 |
| 6 | Tailwind Plus の正確な価格・ライセンス条項 | 公式の購入ページを直接確認（本文の価格は二次情報） | 小 |

---

## 10. 出典

**一次情報（公式ドキュメント）**

- [Base UI — About](https://base-ui.com/react/overview/about)
- [Mantine — Next.js guide](https://mantine.dev/guides/next/) / [Mantine 9.0.0 changelog](https://mantine.dev/changelog/9-0-0/)
- [Chakra UI — Next.js App Router setup](https://chakra-ui.com/docs/get-started/frameworks/next-app) / [Announcing v3](https://chakra-ui.com/blog/announcing-v3)
- [Material UI — Next.js integration](https://mui.com/material-ui/integrations/nextjs/) / [Introducing Material UI v9](https://mui.com/blog/introducing-material-ui-v9/) / [Pigment CSS リポジトリ](https://github.com/mui/pigment-css)
- [shadcn/ui — Docs](https://ui.shadcn.com/docs) / [Changelog](https://ui.shadcn.com/docs/changelog)
- [React Aria](https://react-aria.adobe.com/)
- [Radix Themes — Releases](https://www.radix-ui.com/themes/docs/overview/releases)
- [HeroUI](https://heroui.com/) / [Ant Design v6 移行ガイド](https://ant.design/docs/react/migration-v6/) / [Ark UI](https://ark-ui.com/) / [daisyUI](https://daisyui.com/) / [Tailwind Plus](https://tailwindcss.com/plus)

**一次情報（レジストリ実測・2026-08-18 JST 取得）**

- `https://registry.npmjs.org/<package>`（版数・公開日・peerDependencies・ライセンス表記）
- `https://api.npmjs.org/downloads/point/last-week/<package>`（週次ダウンロード数）

🟢 **ライセンス表記は全 12 パッケージを npm メタデータで個別に確認済み**（React Aria Components のみ Apache-2.0、他は MIT。PrimeReact v11 は §4.10 のとおり独自表記）。

**二次情報（⚠️ 記載箇所を明示している。誤りは §8 に記録）**

- [InfoQ — HeroUI v3 Lands as a Ground-Up Rewrite](https://www.infoq.com/news/2026/07/heroui-v3-rewrite/)
- [LogRocket — Headless UI alternatives](https://blog.logrocket.com/headless-ui-alternatives/)
- [AdminLTE — Mantine vs Chakra UI vs MUI (2026)](https://adminlte.io/blog/mantine-vs-chakra-ui-vs-mui/) / [18 Best React UI Frameworks 2026](https://adminlte.io/blog/react-ui-frameworks/)
- [designrevision — Best React Component Libraries (2026)](https://designrevision.com/blog/best-react-component-libraries)
- [Tailkits — Tailwind Plus](https://tailkits.com/components/tailwind-plus/)
