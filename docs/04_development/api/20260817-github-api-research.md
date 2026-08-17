# GitHub API 最新リサーチ 2026

> 2026年8月17日時点。新規プロダクト開発でGitHub連携を行うことを前提に、REST / GraphQL / GitHub Apps / Webhooks / Actions / MCP・AIエージェントまで含めて整理。

## 1. 結論

2026年時点で新規プロダクトをGitHub連携させるなら、基本方針は以下。

| 項目 | 推奨 |
|---|---|
| API | REST APIを基本 |
| 複雑なデータ取得 | GraphQLを併用 |
| ユーザーのGitHub連携 | GitHub Appを第一候補 |
| 個人開発・管理用途 | Fine-grained PAT |
| GitHub Actions内 | `GITHUB_TOKEN` |
| 状態変化の検知 | Webhooks |
| ポーリング | 原則避ける |
| SDK | Octokit |
| APIバージョン | `2026-03-10`を明示 |
| 大量データ | Pagination + Queue + Cache |
| レート制限 | Primary + Secondary双方を考慮 |
| リポジトリ全体取得 | Contents APIだけに依存しない |
| 大量ファイル取得 | Git Trees / Git Blobs等を検討 |
| AIエージェント連携 | GitHub MCP Serverも重要 |
| セキュリティ | 最小権限・短命Token・Webhook署名検証 |
| SaaS | GitHub App + Webhook + REST/GraphQL |

特に重要なのは、

> **「GitHub APIを呼ぶアプリ」を作るのではなく、「GitHubをイベントソースとするアプリ」を作る**

という発想。

---

## 2. 2026年のGitHub APIを取り巻く大きな変化

特に重要なのは次の5点。

1. REST APIが日付ベースのバージョニングへ
2. GitHub AppがSaaSの標準的な認証・権限モデル
3. Webhook中心のイベント駆動設計
4. Rate Limit / Cache / Queueを前提としたスケーリング
5. AI Agent / MCPとGitHubの統合

---

## 3. REST APIのバージョニング

2026年3月10日に新しい `2026-03-10` API Versionがリリースされた。

これはGitHubのカレンダーベースAPIバージョニングにおける、最初のBreaking Changesを含むバージョン。

サポートされているREST API Versionは、

- `2026-03-10`
- `2022-11-28`

`2022-11-28`は少なくとも2028年3月10日までサポートされる。

### 新規開発での推奨

API Versionを暗黙のdefaultに依存させず、明示する。

```http
X-GitHub-Api-Version: 2026-03-10
```

例えばコード上で、

```ts
const GITHUB_API_VERSION = "2026-03-10";
```

として管理する。

---

## 4. REST API vs GraphQL

GitHubには大きく、

- REST API
- GraphQL API

の2種類がある。

どちらか一方に統一する必要はなく、用途に応じて併用する。

### RESTが向いている

- Repository
- Issue
- Pull Request
- Commit
- Release
- Actions
- Branch
- Webhook
- Contents
- Git objects
- Permissions
- Administration

などのリソース単位の操作。

### GraphQLが向いている

- 複雑な関連データ取得
- Dashboard
- Analytics
- User → Repository → PR → Reviewのような関連データ
- 必要なフィールドだけを取得したいケース

例：

```graphql
query {
  repository(owner: "octocat", name: "hello-world") {
    name
    description
    issues(first: 20) {
      nodes {
        title
        author {
          login
        }
      }
    }
    pullRequests(first: 20) {
      nodes {
        title
        author {
          login
        }
      }
    }
  }
}
```

---

## 5. GraphQLの注意点

GraphQLには、

- Query points
- Node limit
- Secondary rate limit
- Query complexity
- Timeout

など独自の制約がある。

接続部分では `first` / `last` を指定し、1〜100の範囲で取得する必要がある。

1回の呼び出しで500,000 Nodeを超えることもできない。

したがって、

```text
単純なCRUD
  ↓
REST

複雑な関連データ / Dashboard / Analytics
  ↓
GraphQL
```

という使い分けがおすすめ。

---

## 6. GitHub Appを第一候補にする

本格的なSaaSなら、ユーザーにPersonal Access Tokenを貼ってもらう方式よりGitHub Appを優先する。

GitHub Appのメリット：

- Fine-grained permissions
- Repository単位のアクセス制御
- Short-lived token
- Installation単位の権限
- Webhookとの統合

### 基本フロー

```text
User
 ↓
GitHub App Install
 ↓
Organization / Repository選択
 ↓
Installation
 ↓
Installation Access Token
 ↓
GitHub API
```

ユーザーのPATを預かる必要がなく、Repository単位の権限管理もしやすい。

---

## 7. Token管理

長期間有効なTokenをDBに保存する設計は避ける。

推奨：

```text
Secret / Key management
        ↓
短命Token
        ↓
GitHub API
```

GitHubのUser Access Tokenには有効期限を設定する仕組みがあり、Access Tokenは8時間、Refresh Tokenは6か月というモデルが提供されている。

---

## 8. Fine-grained PATの使いどころ

### 向いている

- 個人開発
- PoC
- 管理スクリプト
- 社内ツール
- GitHub API検証

### 向いていない

- 多数ユーザー向けSaaS
- Marketplace型サービス
- Repositoryごとの権限管理が必要なサービス

SaaSでは基本的に、

**GitHub App > Fine-grained PAT**

と考える。

---

## 9. Rate Limit

GitHub APIでは、

- Primary Rate Limit
- Secondary Rate Limit

の2段階で考える。

一般的な認証済みユーザーは5,000 requests/hourが基本。

GitHub Enterprise Cloud組織所有のGitHub Appなどでは、より高い制限が適用されるケースがある。

### Secondary Rate Limit

実運用では「5,000回を使い切る」よりも「短時間に叩きすぎる」方が問題になりやすい。

対象になり得るもの：

- 同時リクエスト
- Endpointへの集中
- CPU消費
- 大量コンテンツ生成
- 短時間の大量処理

REST/GraphQLを合わせた同時実行数、REST endpointのpoints/minute、GraphQLのpoints/minuteなどにも制約がある。

---

## 10. 大量APIをPromise.allで投げない

避けたい例：

```ts
await Promise.all(
  repositories.map(repo =>
    octokit.rest.repos.get({ ... })
  )
)
```

大量Repositoryを対象にするとSecondary Rate Limitに到達しやすい。

推奨：

```text
大量処理
  ↓
Queue
  ↓
Worker
  ↓
Concurrency制御
  ↓
GitHub API
```

---

## 11. Webhooksをイベント駆動の中心にする

定期PollingよりWebhookを優先する。

悪い例：

```text
1分ごと
 ↓
Pull Request API
 ↓
変化ある？
 ↓
ない
 ↓
1分後
```

良い例：

```text
GitHub
  ↓
pull_request event
  ↓
Webhook
  ↓
Queue
  ↓
Worker
```

これによりAPI消費を抑え、リアルタイム性も高められる。

---

## 12. Webhookの基本設計

Webhook endpointでは、

`X-Hub-Signature-256`

を検証する。

推奨フロー：

```text
POST /api/github/webhook
       ↓
Signature validation
       ↓
Event validation
       ↓
Idempotency check
       ↓
Queue
       ↓
200 OK
```

Webhook handlerでGitHub APIへの大量アクセスやAI処理を同期実行しない。

GitHubはWebhook endpointが10秒以上応答しない場合、delivery failureとして扱う。

---

## 13. WebhookのIdempotency

Webhookは同一イベントが重複して届くことを前提にする。

例えばDBに、

```text
github_delivery_id
```

を保存し、

```text
if delivery_id already processed:
    return 200
```

とする。

推奨データ：

```text
github_events
------------------------------
id
delivery_id
installation_id
repository_id
event_type
payload
received_at
processed_at
status
retry_count
```

---

## 14. Webhook失敗への対応

GitHubはWebhook delivery失敗を自動的に無条件で再送する仕組みではない。

そのため本番サービスでは、

```text
Webhook Delivery
       ↓
Delivery Log
       ↓
failed?
       ↓
Retry / Redelivery
```

まで設計する。

過去のdeliveryをAPIから再送する仕組みも用意する。

---

## 15. Pagination

GitHub APIではPaginationを必ず考慮する。

`per_page=100`などを利用しつつ、レスポンスの`Link` headerを利用する。

避けたい：

```ts
for (let page = 1; page <= 100; page++) {
  ...
}
```

推奨：

```text
response
 ↓
Link: rel="next"
 ↓
next URL
 ↓
response
```

OctokitのPagination機能を利用すると実装を簡略化できる。

---

## 16. SDKはOctokitを第一候補

TypeScript / Node.jsならOctokitを第一候補にする。

対応範囲：

- REST
- GraphQL
- GitHub App
- OAuth
- Webhooks
- Authentication
- Pagination
- Retry
- Throttling

例：

```ts
import { Octokit } from "octokit";

const octokit = new Octokit({
  auth: process.env.GITHUB_TOKEN,
});

const { data } =
  await octokit.rest.repos.get({
    owner: "octocat",
    repo: "hello-world",
  });
```

---

## 17. GitHub API Clientの設計

Octokitをアプリケーション全体に直接撒き散らさず、Adapter / Service層に閉じ込める。

```text
GitHub API
 ↓
Octokit
 ↓
GitHubRepositoryService
 ↓
Domain Layer
 ↓
Application
```

例：

```ts
class GitHubRepositoryService {
  async getRepository(...) {}
  async getPullRequest(...) {}
  async getFiles(...) {}
}
```

これによりREST/GraphQLの違いをアプリケーション全体に漏らさない。

---

## 18. OpenAPI

GitHub REST APIはOpenAPIで記述されている。

OpenAPI定義を利用して、

```text
GitHub OpenAPI
      ↓
Code generation
      ↓
Type definitions
      ↓
API client
      ↓
Testing
```

という自動化が可能。

長期運用するなら、

**API仕様変更検知 → 型生成 → Integration Test → API Version Upgrade**

までCI/CDに組み込むのがおすすめ。

---

## 19. Repositoryのファイル取得

Contents APIは小規模Repositoryなら便利。

ただし、

- directoryは最大1,000 files
- fileは100MB超に制約

などがある。

Repository全体を解析するようなプロダクトではContents APIだけに依存しない。

---

## 20. 大規模RepositoryではGit Trees / Blobs

Repository全体を解析するなら、

- Git Trees API
- Git Blobs API
- Git Commits API

などを組み合わせる。

Git Trees APIにはrecursive取得があるが、最大100,000 entries / 7MBという制限がある。

`truncated=true`なら階層ごとに分割取得する必要がある。

---

## 21. Repository分析プロダクトの推奨構成

```text
Repository
 ↓
Tree取得
 ↓
必要ファイルだけ抽出
 ↓
Blob取得
 ↓
AST / parser
 ↓
Index
 ↓
Embedding / Search
 ↓
AI
```

Repository全体を毎回Contents APIで取得する設計は避ける。

---

## 22. Cache / ETag

GitHub APIのレスポンスには頻繁に変わらないデータも多い。

推奨：

```text
GitHub API
 ↓
Cache
 ↓
Application
```

さらに、

```http
ETag
If-None-Match
```

を利用する。

変更がなければ`304 Not Modified`となり、適切に認証されたconditional GETではPrimary Rate Limitを消費しない。

---

## 23. 推奨アーキテクチャ

Next.js + TypeScriptでSaaSを作るなら、

```text
Next.js
   │
   ├── Web UI
   ├── API
   └── Webhook Endpoint
            │
            ↓
          Queue
            │
       ┌────┴────┐
       ↓         ↓
    Worker     Worker
       │         │
       └────┬────┘
            ↓
        GitHub API
            │
       ┌────┴────┐
       ↓         ↓
     REST    GraphQL
```

---

## 24. REST + GraphQLの混在

推奨構成：

```text
                   GitHub
                     │
             ┌───────┴───────┐
             ↓               ↓
           REST           GraphQL
             │               │
             └───────┬───────┘
                     ↓
                GitHub Adapter
                     ↓
                Domain Layer
```

アプリケーション側では、

```ts
repository.getPullRequests()
repository.getContributors()
repository.getRepositoryStats()
```

などDomain APIとして利用する。

---

## 25. Retry戦略

単純な固定回数Retryではなく、GitHubのレスポンスを見て制御する。

```text
429 / secondary limit
       ↓
Retry-After?
       ↓
yes → wait
no
       ↓
x-ratelimit-remaining = 0?
       ↓
resetまでwait
       ↓
その他
       ↓
exponential backoff
```

GitHub公式は、`retry-after`がある場合はその秒数待ち、`x-ratelimit-remaining=0`ならresetまで待ち、それ以外でも少なくとも1分待つことを推奨している。

---

## 26. Mutationは特に慎重に

`POST / PATCH / PUT / DELETE`などを大量に行う場合は、QueueとConcurrency制御を利用する。

例えば、

```text
100 PRへ一斉コメント
```

ではなく、

```text
Queue
 ↓
Rate limited worker
 ↓
順次Mutation
```

とする。

GitHub公式では、Mutationの大量処理について最低1秒程度の間隔を設けることが推奨されている。

---

## 27. AI × GitHub API

2026年に特に重要なのがAI Agent × GitHub。

GitHub MCP Serverも継続的に進化している。

2026年7月にはGitHub MCP Serverが次世代MCP仕様への対応、Stateless MCPへの対応などを発表。

### 従来

```text
AI
 ↓
Custom application
 ↓
GitHub REST API
```

### AI Agent

```text
AI Agent
 ↓
MCP
 ↓
GitHub MCP Server
 ↓
GitHub
```

ただしMCPは通常のGitHub APIの代替ではなく、AI AgentからGitHub機能をToolとして利用するためのインターフェースと考える。

---

## 28. GitHub APIとMCPの使い分け

```text
通常Web SaaS
 → REST / GraphQL

イベント処理
 → Webhooks

AI Agent
 → MCP

GitHub Actions
 → Actions API / GITHUB_TOKEN
```

AI SaaSでは、

```text
GitHub App
+ Webhooks
+ REST/GraphQL
+ MCP
```

を必要に応じて組み合わせる。

---

## 29. AI Code Reviewの典型アーキテクチャ

例えば「PRをAIがレビューする」サービスなら、

```text
PR opened
 ↓
Webhook
 ↓
Queue
 ↓
Diff取得
 ↓
Changed files
 ↓
Repository context
 ↓
AI
 ↓
Review
 ↓
GitHub PR comment
```

となる。

使用する要素：

- GitHub App
- Webhook
- REST
- GraphQL
- Git Trees
- Queue
- AI
- PR API

---

## 30. AIプロダクトで「全部取得」は避ける

避けたい：

```text
PR
 ↓
Repository全体取得
 ↓
全ファイルEmbedding
 ↓
LLM
```

より良い設計：

```text
PR diff
 ↓
Changed files
 ↓
Dependency analysis
 ↓
Relevant files
 ↓
Relevant history
 ↓
必要なcontextのみLLM
```

これにより、

- APIコスト
- Tokenコスト
- latency
- rate limit
- storage

を抑えられる。

---

## 31. GitHub Platformとして捉える

2026年のGitHubを「REST API」とだけ考えない。

```text
GitHub Platform
├── REST API
├── GraphQL API
├── GitHub Apps
├── Webhooks
├── GitHub Actions
├── Security APIs
└── MCP
```

新規プロダクトでは、どの機能をどのレイヤーに置くかを設計する。

---

## 32. 注目すべき領域

### Repository

```text
Code
Branch
Commit
Tag
Release
```

### Collaboration

```text
Issue
PR
Review
Comment
Discussion
```

### CI/CD

```text
Actions
Workflow
Run
Artifact
Deployment
```

### Security

```text
Dependabot
Code Scanning
Secret Scanning
Security Advisory
```

### Organization

```text
Members
Teams
Permissions
Audit
Projects
```

---

## 33. 推奨プロダクトアーキテクチャ

2026年に新規GitHub SaaSを作る場合の基本形：

```text
                 GitHub
                    │
        ┌───────────┴───────────┐
        │                       │
     Webhooks                API
        │                 ┌─────┴─────┐
        │                 │           │
        │               REST       GraphQL
        │                 │           │
        └──────────┬──────┴───────────┘
                   ↓
              GitHub Adapter
                   ↓
               Queue / Job
                   ↓
                Workers
             ┌─────┼─────┐
             ↓     ↓     ↓
           DB    Cache    AI
             │
             ↓
           API
             │
             ↓
          Frontend
```

認証はGitHub App、SDKはOctokit。

---

## 34. 推奨技術スタック例

```text
Frontend
Next.js
React
TypeScript

Backend
Next.js Route Handlers
or Node.js

GitHub
Octokit
GitHub App

Database
PostgreSQL

Cache
Redis

Queue
BullMQ / SQS / Cloud Tasks等

AI
LLM API

Observability
OpenTelemetry
```

---

## 35. Domain Data Model

GitHub APIレスポンスをそのままDBに保存するのではなくDomain Modelへ変換する。

例：

```text
github_installation
github_repository
github_user
github_pull_request
github_issue
github_commit
github_event
```

GitHub Repositoryをアプリケーション内の`Repository`として扱う。

---

## 36. Webhook Event Log

本番サービスではWebhookイベントを保存する。

推奨：

```text
github_events
------------------------------
id
delivery_id
installation_id
repository_id
event_type
payload
received_at
processed_at
status
retry_count
```

これにより、

- 何が起きたか
- なぜ処理されなかったか
- 再処理できるか

を追跡できる。

---

## 37. Observability

最低限ログに残す：

```text
API latency
HTTP status
Rate limit remaining
Rate limit reset
Secondary rate limit
Endpoint
Installation
Repository
Webhook delivery ID
```

特に、

```text
X-RateLimit-Remaining
X-RateLimit-Reset
```

は重要。

---

## 38. API選択マトリクス

| やりたいこと | 推奨 |
|---|---|
| Repository取得 | REST |
| Issue CRUD | REST |
| PR CRUD | REST |
| Commit取得 | REST |
| File取得 | REST / Git API |
| Repository tree | Git Trees |
| 複雑なRepository dashboard | GraphQL |
| User → Repo → PR → Review | GraphQL |
| リアルタイム変更検知 | Webhook |
| GitHub App | REST + Webhook |
| Actions | REST |
| SaaS OAuth/Install | GitHub App |
| 個人スクリプト | Fine-grained PAT |
| Actions workflow | GITHUB_TOKEN |
| AI Agent | MCP |
| AI SaaS | GitHub App + Webhook + REST/GraphQL |

---

## 39. 2026年のトレンド

| トレンド | 重要度 | 新規開発への影響 |
|---|---:|---|
| GitHub Apps | ★★★★★ | 認証・権限設計の基本 |
| Webhooks | ★★★★★ | Event-driven化 |
| API Versioning | ★★★★★ | 長期運用に必須 |
| Rate Limit対策 | ★★★★★ | スケール時の最大課題 |
| Octokit | ★★★★★ | TypeScript開発の基本選択肢 |
| GraphQL併用 | ★★★★☆ | Dashboard/Analyticsで有効 |
| Git Trees | ★★★★☆ | Code Intelligenceで重要 |
| ETag/Cache | ★★★★☆ | APIコスト削減 |
| GitHub Actions API | ★★★★☆ | CI/CD SaaSで重要 |
| GitHub MCP | ★★★★☆ | AI Agent時代に重要 |
| AI Code Agent | ★★★★★ | 今後の大きな市場 |
| Security API | ★★★★☆ | Enterprise SaaSで重要 |

---

## 40. チームの設計原則として使える10項目

1. **GitHub Appを基本認証方式にする**
2. **REST API Versionを`2026-03-10`で固定する**
3. **Octokitを使う**
4. **Webhookをイベント駆動の中心にする**
5. **Pollingを極力避ける**
6. **Rate LimitをQueue / Backoffで吸収する**
7. **RESTとGraphQLを用途に応じて併用する**
8. **Repository全体取得にはGit Trees等を利用する**
9. **ETag / Cache / DBを使ってGitHub API依存度を下げる**
10. **AI Agent系ではMCPもアーキテクチャ選択肢に入れる**

---

## 41. 新規プロダクトで最初に決めること

### Authentication

```text
GitHub App
```

### API

```text
REST first
GraphQL when useful
```

### SDK

```text
Octokit
```

### Events

```text
Webhooks
```

### Async

```text
Queue
```

### Persistence

```text
PostgreSQL
```

### Cache

```text
Redis / equivalent
```

### API Version

```text
2026-03-10
```

### Security

```text
Least privilege
Short-lived tokens
Webhook signature verification
Secret management
```

### Reliability

```text
Idempotency
Retry
Backoff
Dead Letter Queue
```

---

## 42. 公式ドキュメント

- [GitHub REST API Documentation](https://docs.github.com/en/rest)
- [REST API Versions](https://docs.github.com/en/rest/about-the-rest-api/api-versions?apiVersion=2026-03-10)
- [REST API Best Practices](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api?apiVersion=2026-03-10)
- [REST API / GraphQL比較](https://docs.github.com/en/rest/about-the-rest-api/comparing-githubs-rest-api-and-graphql-api?apiVersion=2026-03-10)
- [GitHub GraphQL API](https://docs.github.com/en/graphql/overview)
- [GraphQL Rate Limits](https://docs.github.com/en/graphql/overview/rate-limits-and-query-limits-for-the-graphql-api)
- [GitHub Apps Authentication](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app)
- [Webhook Signature Validation](https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries)
- [REST API Pagination](https://docs.github.com/en/rest/using-the-rest-api/using-pagination-in-the-rest-api)
- [GitHub REST OpenAPI Description](https://docs.github.com/en/rest/about-the-rest-api/about-the-openapi-description-for-the-rest-api)
- [Octokit.js](https://github.com/octokit/octokit.js)
- [Git Trees API](https://docs.github.com/en/rest/git/trees)

---

## 43. まとめ

2026年のGitHub API連携では、単にREST APIを呼び出すだけではなく、

**GitHub Platform = REST + GraphQL + GitHub Apps + Webhooks + Actions + MCP**

として捉えることが重要。

新規SaaSの基本形としては、

**GitHub App → Webhook → Queue → Octokit → REST/GraphQL → Domain DB**

を推奨する。

AIを組み込む場合は、

**GitHub App + Webhooks + REST/GraphQL + Context Engine + AI**

を基本とし、AI AgentとのTool連携にはMCPを追加する。

この構成を最初から採用することで、将来的な以下への拡張性が高くなる。

- AI Code Review
- Repository Intelligence
- 開発組織分析
- PR自動化
- CI/CD SaaS
- Security SaaS
- AI Coding Agent
- Developer Productivity Platform
