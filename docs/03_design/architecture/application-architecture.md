# アプリケーションアーキテクチャ（Clean Architecture・SSOT）

> **このファイルは「アプリケーションコードの層・依存規則・ディレクトリ構造」の唯一の正本（SSOT）である。**
>
> - ドメインの語彙とモデルの正本は [ドメインモデル](../data-model/domain-model.md)
> - テストの正本は [テスト戦略](../../04_development/testing-strategy.md)
> - 運用基盤（デプロイ・バインディング・キャッシュ実体）の正本は [インフラ設計](../infrastructure/infrastructure-design.md) / [Cloudflare インフラ設計](../infrastructure/cloudflare-infrastructure.md)
> - 実装中に読む要約（判断のためのチェックリスト）は [`docs/rules/architecture-rules.md`](../../rules/architecture-rules.md)
>
> 対応要件: `NFR-16`（データアクセス層の隔離）/ `NFR-17`（Cache Port）/ `NFR-19`（型安全）/ `NFR-21`（PaaS 非依存）/ `NFR-23`〜`NFR-25`（テスト）/ `TR-1`〜`TR-3`

---

## 0. なぜ層を分けるのか（この 3 つだけのため）

過剰設計を避けるため、**本プロジェクトで層を分ける理由を 3 つに限定する**。これ以外の理由で層や抽象を増やさない（YAGNI・`CLAUDE.md`「やってはいけないこと」）。

| # | 理由 | 具体的に何を守るか | 根拠 |
|---|---|---|---|
| **W-1** | **データ源を差し替えられる** | Phase 2 で被依存数（Ecosyste.ms）・健全性（OpenSSF）が加わっても、UI を書き換えずに済む | `NFR-16` / `GR-2` |
| **W-2** | **事業者を差し替えられる** | Cloudflare 固有 API がアプリ全体に染み出さない | `NFR-21` / `INF-5` |
| **W-3** | **速く確実にテストできる** | 中核ロジックがネットワークもフレームワークも要らずに実行できる | `NFR-23`〜`NFR-25` / `SD-2` |

🔴 **「クリーンアーキテクチャだから」は理由にならない。** 新しい層・インターフェース・DTO を足したくなったら、`W-1`〜`W-3` のどれを守るためかを 1 行で言えることを条件にする。言えないなら足さない。

---

## 1. 層と依存規則

### 1.1. 依存の向き（内向きのみ）

```text
   app/  （Next.js: Route / Page / Server Action）
     │  ← 合成（composition root 経由でのみ実装を注入する）
     ▼
  src/usecases/        アプリケーション固有のふるまい
     │
     ▼
  src/domain/          ドメインモデル + ポート（interface）  ← 依存ゼロの中心
     ▲                      ▲
     │                      │ implements
  src/ui/（表示）        src/infrastructure/（外部世界のアダプタ）
```

🔴 **唯一絶対の規則（Dependency Rule）**: **内側は外側を知らない。** `src/domain/` は他のどの層も import しない。外側の実装は、内側が定義した **ポート（interface）** に適合する形で外から差し込む（依存性逆転）。

### 1.2. 層ごとの責務と import 可否（機械チェックの正本）

| 層 | ディレクトリ | 責務 | import してよい | 🔴 import 禁止 |
|---|---|---|---|---|
| **Domain** | `src/domain/` | エンティティ・値オブジェクト・ドメインサービス・ドメインエラー・**ポート定義（interface）** | `src/domain/**` / `src/shared/**` のみ | **その他すべて**（`react` / `next` / `zod` / 他層） |
| **Application** | `src/usecases/` | ユースケース（1 ファイル 1 ユースケース）。ポートを組み合わせて 1 つの操作を完遂する | `src/domain/**` / `src/shared/**` | `src/infrastructure/**` / `src/ui/**` / `app/**` / `next/**` / `react` |
| **Interface Adapters** | `src/infrastructure/` | 外部世界（GitHub API・キャッシュ・事業者バインディング）とドメインの相互変換。ポートの **実装** | `src/domain/**` / `src/shared/**` / 外部ライブラリ | `src/ui/**` / `src/usecases/**` / `app/**` |
| **Presentation** | `src/ui/` | 表示。React コンポーネント（Client Components を含む） | `src/domain/`（**型と値オブジェクトのみ**）/ `src/shared/**` / `react` | `src/usecases/**` / `src/infrastructure/**` / `app/**` |
| **Composition** | `src/composition/` | **唯一、実装をポートへ束ねてよい場所**（composition root） | すべて | — |
| **Frameworks & Drivers** | `app/` | ルーティング・Server Component・Route Handler・Server Action。**薄く保つ** | `src/composition/**` / `src/ui/**` / `src/domain/`（型）/ `next/**` | `src/infrastructure/**`（直接） |
| **Shared** | `src/shared/` | どの層にも属さない純粋ユーティリティ（型ヘルパー・日付整形等）。**ビジネス知識を置かない** | `src/shared/**` のみ | すべての層（機械チェックは Warning・§6） |

> ⚠️ **`src/infrastructure/` はクリーンアーキテクチャのアダプタ層であり、`user-story-map.md` §5.2 の「インフラ層（`INF-n`・CI / デプロイ設定）」とは別物。** 3 層判定では `src/infrastructure/` は **バックエンド** に数える（混同禁止）。

### 1.3. ディレクトリ構造（確定）

```text
app/                                # Next.js App Router（薄い）
  [locale]/page.tsx                 #   検索・一覧
  [locale]/repos/[owner]/[repo]/page.tsx
src/
  domain/
    model/                          # Repository / Owner / SearchQuery / SearchResult / Locale …
    ports/                          # RepositoryQueryPort / CachePort / RateLimitPort（interface のみ）
    services/                       # 複数モデルに跨る純粋ロジック（Phase 2: GemIndex 算出）
    errors.ts                       # ドメインエラー（NotFound / RateLimitExceeded / Upstream …）
  usecases/
    search-repositories.ts
    get-repository-detail.ts
  infrastructure/
    system-clock.ts                 #   ClockPort の実装（composition root でのみ束ねる）
    github/                         # 🔴 GitHub API に触れてよい唯一の場所（ACL）
      github-repository-query.ts    #   RepositoryQueryPort の実装
      installation-token.ts         #   GitHub App installation token 供給（ClockPort 経由で時刻を受け取る）
      dto.ts                        #   API レスポンスのスキーマ（zod）
      mapper.ts                     #   DTO → ドメインモデル変換
    platform/                       # 🔴 事業者固有バインディング・キャッシュ実装に触れてよい唯一の場所（NFR-21）
      cache.ts                      #   CachePort の実装（キー規約は NFR-18）
      cache-key.ts                  #   CacheKey の生成関数（唯一の組み立て場所）
      rate-limit.ts                 #   RateLimitPort の実装
  ui/                               # 表示コンポーネント
    url/                            #   URL クエリ契約（SEARCH_PARAM_KEYS・parse・ロケールリダイレクトのパス判定）。domain の値オブジェクトのみ import 可
    i18n/                           #   Locale → Intl ロケールタグ変換等、domain の値オブジェクトに依存する表示用ユーティリティ
  composition/                      # 実装の組み立て（composition root）
  shared/
    i18n/                           # メッセージ辞書の読み込み（実体は messages/ 直下）・プレースホルダー置換等、
                                     #   domain に依存しない純粋ユーティリティ（ARCH-7・ロケール定義自体は domain/model/locale.ts）
messages/
  ja.json                           # メッセージ辞書（日本語）
  en.json                           # メッセージ辞書（英語）
e2e/                                # Playwright（操作レビュー手順の写し）
```

🔴 **旧表記からの移行（`D-22`）**: 以前のドキュメントにあった `lib/infra/` は **`src/infrastructure/platform/`**、`lib/data/` は **`src/infrastructure/github/`** に読み替える。表記は本ファイルに統一済みで、旧表記は使わない。

---

## 2. ポート（境界の契約）

ポートは **`src/domain/ports/` に interface としてのみ置く**。実装は必ず `src/infrastructure/` 側に置く。

| ポート | 面積（これ以上広げない） | 実装 | 根拠 |
|---|---|---|---|
| `RepositoryQueryPort` | `search(query): Promise<SearchResult>` / `findDetail(name): Promise<RepositoryDetail \| null>` | `infrastructure/github/` | `NFR-16` / `TR-4` |
| `CachePort` | `get(key)` / `set(key, value, ttl)` / `invalidate(key)` | `infrastructure/platform/` | `NFR-17`（YAGNI の意図的な例外。面積を広げない） |
| `RateLimitPort` | `consume(key): Promise<Decision>` | `infrastructure/platform/` | `INF-n` / `NFR-7` |
| `ClockPort` | `now(): Date` | `infrastructure/` | テスト決定性（`SD-2`） |

🔴 **ポートを増やすときの条件**: `W-1`〜`W-3` のどれを守るかを 1 行で書き、本表に行を足す。**表に無いポートを実装しない。**

### 2.1. 依存性注入（DI コンテナは使わない）

**IoC コンテナ・デコレータ・`reflect-metadata` は導入しない**（1 箇所でしか使わない抽象は追加しないという YAGNI 原則。サーバーレス起動コストの観点でも不利）。

```ts
// src/composition/container.ts（composition root）
export function searchRepositoriesUseCase(): SearchRepositories {
  const clock = new SystemClock()
  return makeSearchRepositories({
    repos: new GithubRepositoryQuery({ token: makeInstallationTokenProvider({ clock }) }),
  })
}
```

⚠️ `CachePort`（`InMemoryCache`）/ `RateLimitPort`（`WorkersRateLimit`）はまだ composition root に配線しない（実装済みだが未接続。実適用は `E-3` / `SP-5` のスコープ・`NFR-17` の YAGNI 注記どおり）。

- ユースケースは **ポートを引数で受け取る高階関数（またはコンストラクタ注入）** として書く。`import` で実装を掴まない。
- テストは composition root を経由せず、**フェイク実装を直接渡す**（[テスト戦略](../../04_development/testing-strategy.md) §4）。

---

## 3. データの流れと変換（腐敗防止層）

```text
GitHub API JSON → [zod で検証] → DTO → [mapper] → ドメインモデル → ユースケース → ViewModel → UI
```

| 段 | 置き場所 | 規則 |
|---|---|---|
| 検証 | `infrastructure/github/dto.ts` | 🔴 **外部レスポンスを検証せずにドメインへ入れない**（`NFR-19`）。想定外の形は `UpstreamContractError` にする |
| 変換 | `infrastructure/github/mapper.ts` | 🔴 **GitHub の語彙をドメインへ持ち込まない**（腐敗防止層）。例: `subscribers_count` → `watcherCount`（[ドメインモデル](../data-model/domain-model.md) §2 の対応表が正本） |
| 表示整形 | `src/ui/` または `app/` | ロケール依存の整形（数値・日付）は表示側で行う。ドメインに文言・書式を持ち込まない |

🔴 **`app/` や `src/ui/` に GitHub API の生 JSON の形が現れたら設計違反**（`NFR-16` 違反）。

---

## 4. エラーモデル

| 層 | 扱い |
|---|---|
| `src/domain/errors.ts` | `DomainValidationError` / `RepositoryNotFoundError` / `RateLimitExceededError` / `UpstreamUnavailableError` / `UpstreamContractError` を **クラスとして定義** する |
| `src/infrastructure/` | HTTP ステータス・例外を **上記ドメインエラーへ変換** する（`404` → `RepositoryNotFoundError`、`403 / 429 + レート枠ヘッダ` → `RateLimitExceededError`） |
| `src/usecases/` | ドメインエラーをそのまま送出する（握り潰さない・別型に包み直さない） |
| `app/` | ドメインエラーを **UI の状態へ写す**（Not Found 表示 / レート制限の案内 / 再試行導線）。`aria-live` での通知は `NFR-12` |

- 値オブジェクトの生成は **不正なら例外**（`DomainValidationError`）。URL パラメータのように「不正でも落とさず既定値へ倒す」箇所では `tryParse`（`null` を返す変種）を使う。
- 🔴 **`catch` して `console.error` だけして握り潰さない。** 握り潰しは失敗を「0 件」に化けさせ、`AC-5`（Not Found 表示）と区別できなくなる。

---

## 5. Next.js（App Router）との対応づけ

| Next.js の要素 | この設計での位置づけ | 規則 |
|---|---|---|
| Server Component（`page.tsx`） | Frameworks & Drivers | composition root からユースケースを取り、結果を `src/ui/` に渡すだけ。**ロジックを書かない** |
| Client Component（`"use client"`） | Presentation | `src/ui/` に置く。ユースケース・アダプタを import しない |
| Route Handler（`route.ts`） | Frameworks & Drivers | 同上（薄く保つ）。MVP は Read 中心のため原則不要 |
| Server Action | Frameworks & Drivers | 入力検証 → ユースケース呼び出しのみ |
| `use cache` / `cacheLife` / `cacheTag` | Infrastructure の実装詳細 | 🔴 **ユースケース・ドメインから直接触らない**。キャッシュは `CachePort` 越しに扱う（`D-18` により Cloudflare での実体は HTTP `Cache-Control` + Workers Caching） |
| `searchParams` | 入力の境界 | 🔴 **値オブジェクトへ変換してからユースケースへ渡す**（生の文字列を奥へ流さない・`NFR-19`） |

---

## 6. 機械チェック（この設計は grep で守る）

`python3 tools/check_architecture_boundaries.py`（PR 前セルフレビューから自動実行）が §1.2 の import 可否と §1.3 の配置を検査する。検査項目:

| # | 検査 | 重大度 |
|---|---|---|
| `ARCH-1` | `src/domain/` が他層・フレームワーク（`next` / `react` / `zod` 等）を import していない | Error |
| `ARCH-2` | `src/usecases/` が `src/infrastructure/` / `src/ui/` / `app/` / `next` / `react` を import していない | Error |
| `ARCH-3` | `app/` / `src/ui/` が `src/infrastructure/` を直接 import していない（`src/composition/` 経由のみ）。`src/infrastructure/` が `src/usecases/` / `src/ui/` / `app/` を import していない（逆流）。`src/ui/` が `app/` を import していない | Error |
| `ARCH-4` | 事業者固有バインディング（`getCloudflareContext` / `env.KV` 等）の参照が `src/infrastructure/platform/` の外に無い（`NFR-21` / `INF-5`） | Error |
| `ARCH-5` | GitHub API・GitHub 認証情報（`api.github.com` / `@octokit/` / `GITHUB_TOKEN` / `GITHUB_APP_*`）の参照が `src/infrastructure/github/`（認証は `platform/` も可）の外に無い（`NFR-16` / `D-20`） | Error |
| `ARCH-6` | `src/ui/` が `src/usecases/` を import していない | Error |
| `ARCH-7` | `src/shared/` が他層に依存していない | Warning |
| 配置 | `app/` / `src/` 配下のファイルが §1.3 のいずれかの層に属している | Warning |

🔴 **`ARCH-R1`（外部レスポンスの検証）と `ARCH-R2`（値オブジェクトでの受け渡し）は機械チェックできない**（レビュー観点・`docs/rules/architecture-rules.md` §2）。
`// arch-ok` による抑止は `ARCH-1` / `2` / `3` / `6` / `7` にのみ効き、**`ARCH-4` / `ARCH-5`（秘密情報とベンダー境界）には効かない**。抑止件数はサマリーに出力される。

アプリコードが 1 行も無い期間は **全検査をスキップ** する（誤検知させない）。

---

## 7. 完了・成功の定義

- [ ] 新規ファイルが §1.3 のディレクトリのいずれかに属している
- [ ] `python3 tools/check_architecture_boundaries.py` が PASS する
- [ ] 追加したポートが §2 の表に載っている（表に無いポートを実装していない）
- [ ] 外部レスポンスが `infrastructure/github/dto.ts` で検証されてからドメインに入っている
- [ ] `app/` にビジネスロジックが無い（ユースケース呼び出しと表示の受け渡しのみ）

---

## 8. 参照

| ドキュメント | 関係 |
|---|---|
| [ドメインモデル](../data-model/domain-model.md) | 中心（`src/domain/`）に何を置くかの正本 |
| [テスト戦略](../../04_development/testing-strategy.md) | 各層をどうテストするかの正本（`R-11`） |
| [インフラ設計](../infrastructure/infrastructure-design.md) / [Cloudflare](../infrastructure/cloudflare-infrastructure.md) | `src/infrastructure/platform/` の外側（運用基盤）の正本 |
| [`docs/rules/architecture-rules.md`](../../rules/architecture-rules.md) | 実装中に読む要約（判断チェックリスト） |
| [Next.js 16 リサーチ](./20260817-nextjs16-architecture-research.md) | 採用したフレームワーク機能の背景 |
