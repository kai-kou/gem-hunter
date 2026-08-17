# Next.js 新規プロダクト開発リサーチ

- **基準日:** 2026-08-17
- **対象:** Next.js 16系を中心とした最新仕様、トレンド、ベストプラクティス
- **目的:** 今後の新規プロダクト開発で、そのままArchitecture/技術選定/開発ルールに利用できる形に整理する
- **関連:** [最低要件定義（MVP）](../../02_requirements/minimum-requirements.md) / [GitHub API 最新リサーチ](../../04_development/api/20260817-github-api-research.md)

> 重要: 基準日時点で16.x系がActive LTS（16は2025-10-21リリース）、15.x系がMaintenance LTS。16.x系の最新リリースは16.3（2026-08-03）で、メモリ使用量の削減、Instant Navigations、AI Coding Agent向け機能などが入っている。ProductionではLTSを基本とし、canary/preview機能は本番のコア要件に依存させない。
>
> 本プロジェクトは [最低要件定義](../../02_requirements/minimum-requirements.md) で「Next.js v16以降 + App Router」を必須としているため、本ドキュメントの前提と整合する。ただし本ドキュメントは汎用的な新規プロダクト開発を対象としており、MVPスコープ（認証なし・DBなし・GitHub API直参照）では過剰な項目も含む。適用時は「MVPで必要な範囲」と「将来拡張時に効いてくる範囲」を切り分けること（下記「本プロジェクトへの適用メモ」参照）。

### 本プロジェクトへの適用メモ

| 本ドキュメントの項目 | MVPでの扱い |
|---|---|
| App Router / Server Components First / Streaming・Suspense | そのまま採用（要件の非機能要件4.2と整合） |
| Cache Components（`use cache` / `cacheLife` / `cacheTag`） | GitHub APIレスポンスのキャッシュに採用検討。レート制限緩和に直結する |
| URL State（searchParams） | 採用必須。検索キーワード・ページのURL反映が要件（4.3） |
| Route Handler vs Server Action | MVPはRead中心のためServer Componentからの直接fetchが基本。Mutationは現時点でなし |
| Secret管理（`NEXT_PUBLIC_*`禁止・Server Only） | 採用必須。GitHubトークンの扱いが要件（4.1）にある |
| Validation（Zod等） | 外部APIレスポンスの型検証として採用検討 |
| DAL / Service Layer / PostgreSQL / ORM | MVPスコープ外（DBを持たない）。将来Gem Score等で永続化が必要になった段階で再検討 |
| Authentication / Authorization | MVPスコープ外（要件1.2で対象外） |
| Observability（OpenTelemetry） | MVPでは最小限。将来の運用フェーズで導入 |
| AI Agent対応（`AGENTS.md`等） | 初期から整備してよい（低コスト・高リターン） |

## 1. エグゼクティブサマリー

2026年の新規Next.js開発では、単なる「React + SSR」ではなく、**フルスタックWebアプリケーション基盤**として設計する。

基本方針:

1. Next.js 16.x + App Routerを採用
2. TypeScriptを必須級とする
3. React Server Componentsをデフォルトにする
4. `use client`はインタラクションが必要な箇所に限定
5. Cache Componentsをデータ/UI単位のキャッシュ設計に利用
6. Server Functions/ActionsはMutationに活用
7. Server Actionでも認証・認可・入力検証を必ず実施
8. DBアクセスはData Access Layerに隔離
9. Proxyは前段処理に使い、認可の最終防衛線にしない
10. Turbopackを標準利用し、Webpack依存を減らす
11. Observabilityを初期から設計
12. AI Coding Agentが理解しやすいRepository構造・`AGENTS.md`・ドキュメントを整備

## 2. Next.js 16の主要変更

Next.js 16の大きなテーマは以下。

- Cache Components
- `use cache`
- Turbopack stable / default
- React Compiler support
- Enhanced routing / prefetching
- `updateTag()` / `refresh()` / 改良された`revalidateTag()`
- React 19.2
- Proxyへの名称変更
- Build Adapters API
- AI Coding Agent対応の強化

### バージョン戦略

新規本番プロダクト:
- **Next.js 16.x Active LTS**
- Node.js 20.9+
- TypeScript
- App Router

Preview/canary:
- 新機能検証専用
- 本番の必須アーキテクチャにはしない

## 3. App Router

新規プロダクトは原則App Routerを採用する。

```text
app/
├── layout.tsx
├── page.tsx
├── loading.tsx
├── error.tsx
├── not-found.tsx
├── dashboard/
├── users/
└── api/
```

App RouterはServer Components、Suspense、Streaming、Server FunctionsなどReactの新しいモデルを前提とする。

## 4. Server Components First

基本原則:

```text
Server Component
  ├─ DB
  ├─ External API
  ├─ Authentication
  └─ Business Logic
          ↓
Client Component
  ├─ State
  ├─ Event Handler
  └─ Browser API
```

`use client`は以下が必要な場合だけ付与する。

- `useState`
- `useEffect`
- Browser API
- イベントハンドラ
- Client-side interactive UI

ページ全体をClient Componentにする設計は原則避ける。

## 5. Cache Components

Next.js 16で特に重要な機能。

従来の「ページ単位のStatic/ISR/Dynamic」から、同一ページ内にStatic/Cached/Dynamicを混在させる設計へ移行できる。

例:

```text
Product Page
├── Header          Cached
├── Product Info    Cached
├── Inventory       Dynamic
├── User Cart       Dynamic
└── Recommendations Cached
```

`use cache`、`cacheLife`、`cacheTag`を利用して、データの意味に応じてキャッシュする。

### キャッシュ設計原則

| データ | 基本方針 |
|---|---|
| 商品マスタ | 強くCache |
| カテゴリ | Cache |
| ブログ | Cache |
| Recommendations | Cache |
| ユーザー情報 | 要件次第 |
| カート | Dynamic |
| 在庫 | Dynamic |
| 決済状態 | Dynamic |

## 6. `revalidateTag()` と `updateTag()`

### `revalidateTag()`

Stale-While-Revalidate型の用途。

向いているもの:
- 商品
- ブログ
- ドキュメント
- ランキング

### `updateTag()`

Read-your-own-writes向け。

向いているもの:
- ユーザー設定変更
- プロフィール編集
- 記事編集
- 注文情報変更

原則:

```text
「多少古くてもよい」
→ revalidateTag

「変更直後に自分の変更を必ず見たい」
→ updateTag
```

## 7. Server Functions / Server Actions

MutationをServer側に寄せる。

推奨フロー:

```text
Form
 ↓
Server Action
 ↓
Authentication
 ↓
Authorization
 ↓
Input Validation
 ↓
Business Logic
 ↓
DAL
 ↓
Database
 ↓
Cache Update
```

重要: Server Actionは内部関数に見えても、セキュリティ上はpublic-facing endpointと同じように扱う。

## 8. Proxy

Next.js 16では`middleware.ts`から`proxy.ts`へ名称変更。

向いている用途:
- Redirect
- Rewrite
- Headers
- Cookie
- 軽量な認証前処理
- A/B test

ただしProxyだけでAuthorizationを完結させない。

Server Function / Route Handler / DALなど、データに近い境界でも認証・認可を再検証する。

## 9. Route Handler vs Server Action

### Server Action

自社UIからのMutation。

### Route Handler

- Public API
- Webhook
- External client
- Mobile app
- 外部サービスとのAPI連携

使い分け:

```text
Internal UI mutation → Server Action
External/Public API  → Route Handler
```

## 10. Data Access Layer

大規模化する新規プロダクトではDALを設ける。

```text
UI
 ↓
Server Component / Server Action
 ↓
Service
 ↓
DAL
 ↓
DB
```

推奨構造:

```text
src/
├── app/
├── components/
├── features/
├── lib/
│   ├── auth/
│   ├── dal/
│   ├── db/
│   ├── validation/
│   ├── cache/
│   └── observability/
├── services/
└── types/
```

DBや秘密情報をUI層に露出させない。

## 11. Authentication / Authorization

認証は成熟したAuth Library/Managed Providerを優先し、独自実装を最小化する。

重要なのはAuthenticationとAuthorizationを分離すること。

```text
Authentication
→ 誰か？

Authorization
→ 何をしてよいか？
```

Server Action、Route Handler、DALなど、重要なデータ境界で認可を確認する。

## 12. Validation

Client validationだけではセキュリティにならない。

推奨:

```text
unknown
 ↓
Schema Validation
 ↓
Typed Object
 ↓
Business Logic
```

Zod等のSchema Validationを採用候補にする。

## 13. State Management

すべてをRedux/Zustandに入れない。

```text
Server State
→ Server Components / Cache

URL State
→ searchParams

Form State
→ Server Functions / useActionState

Local UI State
→ useState

Global Client State
→ 必要な場合だけ Zustand等
```

検索・フィルタ・ソート・PaginationはURL Stateとの相性がよい。

## 14. Streaming / Suspense

「すべてのデータ取得が完了してから表示」する設計を避ける。

```text
Header        → 即表示
Product Info  → 即表示
Reviews       → 後から
Recommendations → 後から
```

`loading.tsx`、Suspense、Streamingを活用する。

## 15. Turbopack

Next.js 16ではTurbopackが標準。

方針:
- `next dev` / `next build`の標準構成を利用
- Webpack依存の独自カスタマイズを避ける
- Turbopack FileSystem Cacheなどの進化を継続的に追う

TurbopackはRust製のincremental bundlerとして進化している。

## 16. React Compiler

React Compiler integrationがstable。

従来の手動最適化:

```text
useMemo
useCallback
memo
```

を必要以上に乱用せず、Compilerによる自動最適化を基本にする。

## 17. Performance

主要ポイント:

- Server Componentsを優先
- Client Bundleを小さくする
- Streaming
- Suspense
- Cache
- Image optimization
- Font optimization
- Script optimization
- 適切なPrefetch
- Production buildで測定

「最初から過剰最適化」ではなく、Observability → Measurement → Optimizationの順序を推奨。

## 18. SEO

Metadata APIを利用。

必要に応じて:
- `metadata`
- `generateMetadata`
- sitemap
- robots
- Open Graph
- Twitter Card
- canonical
- structured data

を設計する。

## 19. Security

最低ライン:

```text
Authentication
Authorization
Input Validation
CSRF
XSS
CSP
Secret Management
Rate Limiting
Audit Log
Dependency Security
```

`NEXT_PUBLIC_*`はBrowserへ公開される前提。

SecretはServer Only。

## 20. Observability

初期からObservabilityを設計する。

```text
Next.js
├── Logs
├── Metrics
└── Traces
       ↓
OpenTelemetry
       ↓
Observability Platform
```

最低限追跡したい情報:

- Request ID
- Trace ID
- User ID
- Route
- Duration
- Status
- Error
- External API latency
- DB latency

## 21. Deployment

Next.jsはVercel以外にもNode.js Server、Docker、Static Export、各種Platform Adapterを利用可能。

### Vercel

向いている:
- Next.js中心
- 開発速度優先
- Preview Deployment重視
- 運用負荷削減

### AWS/GCP/Azure等

向いている:
- Enterprise IAM
- Private Network
- 既存インフラ統合
- DB/Serviceとの密結合
- コスト最適化
- 独自インフラ要件

Vercel Lock-inを避けたい場合でも、Next.js自体のPlatform対応が進んでいるため選択肢は広い。

## 22. AI Coding Agent対応

2026年の重要トレンド。

Next.js 16.3では:
- `AGENTS.md`
- Version-matched docs
- First-party Skills
- Agent Browser
- React introspection
- MCP
- Actionable errors

など、AI Coding Agentをfirst-class userとして扱う方向が進んでいる。

新規Repositoryでは:

```text
README.md
AGENTS.md
CONTRIBUTING.md
docs/
architecture/
```

を整備する。

`AGENTS.md`には例えば:

```text
Architecture:
- App Router
- Server Components first

Rules:
- Avoid unnecessary "use client"
- All mutations require authorization
- DB access only through DAL
- Validate external input
- Respect cache strategy
```

などを明記する。

## 23. 推奨Repository構造

```text
src/
├── app/
│   ├── (marketing)/
│   ├── (auth)/
│   ├── dashboard/
│   ├── api/
│   ├── layout.tsx
│   └── page.tsx
│
├── components/
│   ├── ui/
│   ├── forms/
│   └── shared/
│
├── features/
│   ├── users/
│   ├── products/
│   ├── billing/
│   └── organizations/
│
├── lib/
│   ├── auth/
│   ├── dal/
│   ├── db/
│   ├── validation/
│   ├── cache/
│   └── observability/
│
├── services/
├── types/
└── instrumentation.ts

AGENTS.md
next.config.ts
package.json
tsconfig.json
```

## 24. 推奨Technology Stack

| 領域 | 推奨 |
|---|---|
| Framework | Next.js 16 |
| UI | React 19系 |
| Language | TypeScript |
| Router | App Router |
| Bundler | Turbopack |
| Rendering | React Server Components |
| Cache | Cache Components |
| Validation | Zod等 |
| DB | PostgreSQL |
| ORM | Prisma / Drizzle |
| Auth | Auth Library / Managed Auth |
| Styling | Tailwind CSS等 |
| Unit/Integration | Vitest等 |
| E2E | Playwright等 |
| Observability | OpenTelemetry |
| CI/CD | GitHub Actions等 |
| Hosting | Vercel / AWS / GCP等 |
| AI Coding | Codex / Claude Code等 |
| Documentation | Markdown + AGENTS.md |

## 25. アーキテクチャ例

```text
                    Browser
                       │
                       ▼
                 ┌──────────┐
                 │ Next.js  │
                 │ App      │
                 │ Router   │
                 └────┬─────┘
                      │
          ┌───────────┼───────────┐
          ▼           ▼           ▼
       Server      Server       Route
     Components   Functions    Handlers
          │           │           │
          └───────┬───┴───────────┘
                  ▼
            Service Layer
                  │
                  ▼
           Data Access Layer
             │           │
             ▼           ▼
        PostgreSQL    External APIs
```

Cacheを追加:

```text
Server / Data
     │
     ├── Static
     ├── Cached
     └── Dynamic
```

## 26. アンチパターン

避けるべき設計:

- 全ページを`use client`
- Server Actionを認証なしで実行
- ProxyだけでAuthorization
- Client ComponentからDBへ直接アクセス
- すべてをRedux/Zustandへ投入
- すべてをSSR
- すべてをCache
- キャッシュ戦略を後付け
- APIを無意味にRoute Handler化
- 巨大なClient Bundle
- Webpack前提の独自カスタマイズ
- Secretを`NEXT_PUBLIC_*`にする
- Observabilityをリリース直前に導入

## 27. 開発フェーズ

### Phase 1: Architecture

最初に決める:

- Authentication
- Authorization
- DB
- DAL
- Server/Client boundary
- Cache strategy
- Deployment
- Observability

### Phase 2: Foundation

- Next.js
- TypeScript
- Lint/Format
- Testing
- CI
- Environment
- Auth
- DB

### Phase 3: Core Features

```text
Server Component
 ↓
DAL
 ↓
DB
```

Mutation:

```text
Form
 ↓
Server Action
 ↓
Validation
 ↓
Authorization
 ↓
Service
 ↓
DB
 ↓
Cache update
```

### Phase 4: Performance

- Cache
- Streaming
- Suspense
- Prefetch
- Bundle
- Image
- Font

### Phase 5: Production

- Monitoring
- Tracing
- Logging
- Security
- CSP
- Rate Limit
- Backup
- Error Handling
- Load Test

## 28. 今後ウォッチすべきトレンド

### 最重要

1. Cache Components
2. AI Coding Agent integration
3. Instant Navigations
4. Turbopack
5. React Compiler
6. Platform Adapters
7. Server/Client architecture
8. Server-side data security
9. Observability
10. ReactのServer-firstモデル

## 29. チーム開発ルールとして推奨する10原則

```text
1. Server First
2. Client Only When Necessary
3. Data Access Server Only
4. Authorization at the Data Boundary
5. Cache by Data Semantics
6. Validate Every External Input
7. Prefer Platform APIs Before Libraries
8. Keep Client Bundles Small
9. Observe Before Optimizing
10. Make the Repository AI-Agent Friendly
```

## 30. 最終評価

2026年に新規プロダクトをNext.jsで開発する場合、Next.jsを単なる「ReactのSSRフレームワーク」と捉えないことが重要。

推奨モデル:

```text
Next.js 16
├─ App Router
├─ React Server Components
├─ Server Functions
├─ Cache Components
├─ Turbopack
├─ React Compiler
│
├─ Data Access Layer
├─ PostgreSQL
├─ Auth
├─ Validation
├─ OpenTelemetry
├─ E2E Testing
├─ CI/CD
└─ AI-Agent-ready Repository
```

最重要Architecture Decisionは:

1. Server/Client境界
2. Cache設計
3. Data Access Layer
4. Authentication / Authorization
5. Observability
6. AI Agent対応

の6点。

この6点を最初に設計しておくことで、Next.jsの進化を取り込みながら、後からの大規模な作り直しを抑えやすい。

## 31. 公式情報・参考資料

- Next.js Docs: https://nextjs.org/docs
- Next.js Blog: https://nextjs.org/blog
- Next.js Support Policy: https://nextjs.org/support-policy
- Next.js 16: https://nextjs.org/blog/next-16
- Next.js 16.3: https://nextjs.org/blog/next-16-3
- Caching: https://nextjs.org/docs/app/getting-started/caching
- Production Checklist: https://nextjs.org/docs/app/guides/production-checklist
- Authentication: https://nextjs.org/docs/app/guides/authentication
- Data Security: https://nextjs.org/docs/app/guides/data-security
- Deploying: https://nextjs.org/docs/app/getting-started/deploying
- Turbopack: https://nextjs.org/docs/app/api-reference/turbopack

### リサーチ上の注意

Next.jsは短期間で仕様が変化するため、実装時には必ず公式Docsの対象バージョンを確認する。特にCache Components、AI Agent tooling、Instant Navigations、TurbopackのPreview機能は、Stable化の状況を確認してから本番採用する。

保存時（2026-08-17）に公式サイトで確認した内容:

- Support Policy: 16.x = Active LTS、15.x = Maintenance LTS（15.x以前はUnsupported）
- リリース履歴: 16（2025-10-21） / 16.1（2025-12-18） / 16.2（2026-03-18） / 16.3（2026-08-03）

パッチバージョン単位の最新値は変動するため、実装着手時に `npm view next version` 等で再確認すること。
