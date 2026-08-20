# ADR 0006: Next.js 16 + App Router を採用する

- **状態**: **承認**
- **日付**: 2026-08-20 JST
- **対応要件**: `TR-1` / `TR-2` / `AC-1` / `NFR-3`
- **関連**: [`minimum-requirements.md`](../02_requirements/minimum-requirements.md) §2 / [Next.js 16 リサーチ](../03_design/architecture/20260817-nextjs16-architecture-research.md) / [アプリケーションアーキテクチャ](../03_design/architecture/application-architecture.md) §5

---

## 1. 文脈

`TR-1`（Next.js v16 以降を使用する）・`TR-2`（App Router を使用する。Pages Router は使用しない）は、いずれも [`minimum-requirements.md`](../02_requirements/minimum-requirements.md) §2「技術要件」が定める **必須の与件**（`D-2`）である。フレームワークとルーティング方式そのものは選択の余地がない。

一方で、与件が定めていないのは **その上でどう作るか**（Server Component をどこまで基本に据えるか・`use client` 境界をどう引くか・データ取得をどの層に置くか）である。これは実装が自律的に決める領域（`D-12`）であり、本 ADR が記録するのはこの部分の判断と、それによって却下された代替アーキテクチャである。

## 2. 決定

- **Next.js 16.2.11 以上**（`D-17`）+ **App Router**（`app/` ディレクトリ）を採用する。`pages/` によるルーティングは使用しない
- **Server Components First**（`NFR-3`）: 既定は Server Component とし、`"use client"` はインタラクションが必要な箇所（フォーム入力・テーマ切替・shadcn/ui のインタラクティブ系コンポーネント等）に限定する
- Server Component（`page.tsx`）は **composition root からユースケースを取り、結果を `src/ui/` の Presentation コンポーネントへ渡すだけ**（ロジックを書かない・[アプリケーションアーキテクチャ](../03_design/architecture/application-architecture.md) §5）
- 本プロジェクトは Read 中心（検索・詳細表示のみで Mutation を持たない）のため、データ取得は **Server Component からの直接呼び出しが基本**。Route Handler は `SP-5` でキャッシュ HIT/MISS を外部から観測するための例外的経路（`GET /api/search`）としてのみ存在する（[ADR 0005](0005-cache-port-yagni-exception-and-ttl.md) §2.3）
- 検索キーワード・ページ・ソート・表示件数は **URL（`searchParams`）に状態を持たせる**（`NFR-2`。詳細は [ADR 0007](0007-no-database-client-side-state.md)）

## 3. 理由

### 3.1. 与件由来の制約と、その上での選択を区別する

| 決定事項 | 性質 |
|---|---|
| Next.js v16 以降を使う | 与件必須（`TR-1`）。選択の余地なし |
| App Router を使う（Pages Router を使わない） | 与件必須（`TR-2`）。選択の余地なし |
| Server Components First・`use client` を最小化する | **自律判断**。与件は言及していないが `NFR-3` として自ら課した |
| composition root を挟み Server Component にロジックを書かない | **自律判断**。クリーンアーキテクチャの依存規則（`ARCH-2`〜`ARCH-4`）を App Router に適用した結果 |

`TR-1` / `TR-2` は「Next.js を使うか」「どのルーティングか」を固定するだけで、「App Router の中でどう層を分けるか」までは決めていない。後者の設計判断が本 ADR の実質的な中身である。

### 3.2. なぜ App Router / RSC を選んだ結果を積極的に活かすか

与件が App Router を必須にしている以上、React Server Components・Streaming・Suspense は標準機能として最初から使える。[Next.js 16 リサーチ](../03_design/architecture/20260817-nextjs16-architecture-research.md)「本プロジェクトへの適用メモ」は「App Router / Server Components First / Streaming・Suspense」を **そのまま採用**、「URL State（`searchParams`）」を **採用必須** と整理しており、本プロジェクトの MVP スコープ（認証なし・DB なし・GitHub API 直参照・与件 §2）と相性がよい。

- **Server Components First**（`NFR-3`）を課すことで、GitHub API 呼び出し・アダプタ実装をクライアントバンドルから排除でき、`NFR-28`（初期 JS バンドルサイズ）に直接効く
- `searchParams` による URL 状態は、与件 §4.3「リロード・共有で同じ結果」（`FR-5` / `FR-6` / `NFR-2`）をフレームワーク標準機能だけで満たせる
- Mutation を持たない Read 中心アプリのため、Server Action の必要性が薄く、データ取得は Server Component からの直接 fetch で完結する（複雑な状態管理層を持ち込まずに済む）

## 4. 却下した選択肢

| 選択肢 | 却下理由 |
|---|---|
| **Pages Router** | `TR-2` が明示的に禁止（与件必須要件） |
| **Next.js を使わず SPA（React + Vite 等）+ 別 API サーバー** | `TR-1` / `TR-2` に違反する。加えて DB レス原則（[ADR 0007](0007-no-database-client-side-state.md)）と組み合わせるなら、Next.js の Server Component 経由でサーバー側シークレット（GitHub トークン）を扱う方が `NFR-9` を満たしやすく、別 API サーバーを立てる運用コスト（`INF-4` の定常運用ゼロに反する）もかからない |
| **すべて Client Component にしてクライアント側でデータ取得する** | `NFR-3` に反し、GitHub トークン（`NFR-9`）をクライアントへ露出させずに検索を実行できなくなる。バンドルサイズ（`NFR-28`）も悪化する |
| **Server Action を Mutation 用に先行導入する** | 本プロジェクトは検索・詳細表示のみで Mutation を持たない（与件 §1.2 の対象外リスト）。1 箇所も使わない抽象化を先回りしない（YAGNI） |
| **App Router 内でロジック（ユースケース呼び出し・整形）を `page.tsx` に直接書く** | クリーンアーキテクチャの依存規則（`ARCH-2`〜`ARCH-4`）に反し、`app/` が「薄く保つ」という制約（[アプリケーションアーキテクチャ](../03_design/architecture/application-architecture.md) §2）を破る |

## 5. 結果（この決定がもたらすもの）

### 良い方向

- Server Components First により、GitHub API 呼び出し・トークンの扱いがすべてサーバー側に閉じる（`NFR-9`）
- `app/` が薄く保たれ、`src/domain` / `src/usecases` / `src/infrastructure` へのロジック集約が機械検査可能になる（`tools/check_architecture_boundaries.py`）
- URL 状態設計と組み合わさり、DB を持たずに与件 §4.3 の要求（リロード・共有）を満たせる

### 受け入れる代償

| 代償 | 緩和策 |
|---|---|
| Next.js 16 + OpenNext Cloudflare アダプタは `middleware` / `proxy.ts` を採用していない（`D-17`） | ロケールリダイレクトはルート Server Component の `redirect()` で実装する（`next-intl` 不採用の理由と同根・`prd.md` §13） |
| shadcn/ui は公式に Next.js 15 を主対象としており、16 固有の互換性表明が薄かった | `SP-1` で実機導入し互換性を確認済み（[ADR 0001](0001-ui-stack.md) §7.1）。不成立時は ADR 0001 を supersede する運用にしていた |

## 6. 参照

| ドキュメント | 関係 |
|---|---|
| [`minimum-requirements.md`](../02_requirements/minimum-requirements.md) §2 | `TR-1` / `TR-2` の与件原文 |
| [`prd.md`](../02_requirements/prd.md) `AC-1` | Next.js v16 以降 + App Router で構築されていることの受け入れ条件 |
| [Next.js 16 リサーチ](../03_design/architecture/20260817-nextjs16-architecture-research.md) | 「本プロジェクトへの適用メモ」が採用範囲を仕分けている一次情報 |
| [アプリケーションアーキテクチャ](../03_design/architecture/application-architecture.md) §5 | Server Component / Client Component と層の対応づけの正本 |
| [ADR 0001](0001-ui-stack.md) | shadcn/ui × Next.js 16 の互換性確認結果 |
| [ADR 0007](0007-no-database-client-side-state.md) | URL 状態設計・DB レス原則の記録 |
