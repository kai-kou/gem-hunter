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

🔴 **`ui` 層の「型と値オブジェクトのみ」の具体的な線引き（Issue #619 系）**: `src/domain/` から `src/ui/` へ import してよいのは、**型定義・値オブジェクトの型・そのブランド型を安全に読み書きする補助関数**（コンストラクタ・アクセサ・`try*` 系の純粋なパース関数）に限る。判断の軸は「ビジネスルールを持つ関数か、形式の判定・変換だけの純粋な述語か」——

- ✅ **許可**: ブランド型の生成・分解・アクセサ（`gemIndexValue`・`ownerOf`・`repoOf` 等）、`try*` 系の純粋パース関数（不正なら `null` を返すだけで例外を投げず、副作用が無く、ポートを呼ばない）。`tryParseLenientRepositoryFullName`（`src/domain/model/repository-full-name.ts`）はこれに該当する——GitHub の命名規則という不変条件は検証せず「スラッシュで 2 分割できるか」という形式だけを見て `{ owner, name }` を返す純粋関数であり、ビジネスルール（何が Gem か・どのレジストリを信頼するか等）を一切持たない。
- ❌ **禁止**: ドメインサービス・ユースケース相当の計算（複数モデルを跨ぐ判定・母集団に依存する統計・ポートを呼ぶ処理）。`GemIndex` の算出（`computeGemIndex`）や `gem-keyword.ts` の照合規則（`tokenizeQuery` 等・単語境界一致という業務ルールそのもの）はこちらに該当し、`ui` から直接呼ばない（呼び出しはユースケース経由にする）。

**既存実装との整合**: `src/ui/gem-list.tsx` は `gemIndexValue`（`GemIndex` ブランド型のアクセサ）と `tryParseLenientRepositoryFullName`（許容版の純粋パース関数）の 2 つだけを `src/domain/` から import しており、上記の許可範囲と矛盾しない（ドメインサービス・ユースケース相当の計算は import していない）。

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
| `RepositoryQueryPort` | `search(query): Promise<SearchResult>` / `findDetail(name): Promise<RepositoryDetail \| null>` / `findReadme(name): Promise<string \| null>` | `infrastructure/github/` | `NFR-16` / `TR-4`。`findReadme` は Issue #334（F-4）で追加（新規ポートは切らずに既存ポートへ足す・`W-n` の面積判断は[議論記録](../../../content/discussions/feedback334_detail_readme_20260821/whiteboard.md)争点 B 参照） |
| `CachePort` | `get(key)` / `set(key, value, ttl)` / `invalidate(key)` | `infrastructure/platform/` | `NFR-17`（YAGNI の意図的な例外。面積を広げない） |
| `RateLimitPort` | `consume(key): Promise<Decision>` | `infrastructure/platform/` | `INF-n` / `NFR-7` |
| `ClockPort` | `now(): Date` | `infrastructure/` | テスト決定性（`SD-2`） |
| `GemIndexPort` | `lookup(repositoryFullNames): Promise<ReadonlyMap<string, GemIndex>>` / `search(input): Promise<GemPoolSearchResult>` | `infrastructure/platform/`（`static-gem-index.ts`） | `W-1`（Gem 候補プールの配信方式 — レジストリ別シャードの静的アセット + isolate 内メモリ — を UI・usecase から隠す）。`D-36`（バッジの再導入）/ `D-38`（シャード配信）/ `SP-18` / `SP-19`。面積は `lookup()`（バッジ判定）と `search()`（Gem 候補の一覧）の 2 本。**`search()` が守るのも `W-1`**（検索語での絞り込み・`gemIndex` 昇順の並べ替え・ページングを同じ配信方式の内側で完結させ、シャード構成と第 2 段の検索インデックスを UI・usecase から隠す）。同じ isolate 内メモリを共有するため `lookup()` と同一ポートに置く（別ポートへ切ると `StaticGemIndex` のシングルトンが分裂し cold start でシャードを二重取得する）。母集団の違う `GemDigestPort` と統合しない |
| `AuthPort` | `exchangeAuthorizationCode(code): Promise<{ accessToken: string }>` | `infrastructure/github/`（`oauth.ts`） | `W-3`（フェイクでユニットテストできる）。`AR-5` / `SP-8`。GitHub `/user` プロフィール取得は AC 未記載のため面積に含めない（YAGNI・`whiteboard/sp8-auth-i18n-20260819` 争点 C round2 決定） |

🔴 **ポートを増やすときの条件**: `W-1`〜`W-3` のどれを守るかを 1 行で書き、本表に行を足す。**表に無いポートを実装しない。**

🔵 **README（`findReadme`）の private ゲートは usecase 層に置く**（Issue #334・F-4）: `src/usecases/get-repository-readme.ts` が内部で `findDetail` を再度呼び、`null`（private / 404）なら `findReadme` を呼ばない。README レスポンス自体に `private` フィールドが無いため、呼び出し元の順序に依存させずゲートを usecase に埋め込む（`NFR-33` / `AC-12`）。README の HTML サニタイズは **`src/ui/` の責務** とする（ACL である `src/infrastructure/github/` は GitHub から届いた生 HTML をそのまま返すだけで、許可タグ・見出し降格・切り詰め等の変換は持ち込まない）。

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

⚠️ `CachePort`（`LayeredCache` = `InMemoryCache` + `WorkersCache`。Cache API が使えない環境では `InMemoryCache` 単独へフォールバックする・実装名と構成の正本は [Cloudflare インフラ設計](../infrastructure/cloudflare-infrastructure.md) §4.2 / [ADR 0016](../../adr/0016-cloudflare-cache-api-for-cross-isolate-cache.md)）は `container.ts` の `sharedCache` として（`SP-5`）、`RateLimitPort`（`WorkersRateLimit`）は `src/composition/rate-limit.ts` の間引き関数として（Issue #122 / Issue #442）、**いずれも composition root へ配線済み**。🔵 **どのエントリポイントへ適用しているかの正本は [Cloudflare インフラ設計](../infrastructure/cloudflare-infrastructure.md) §3.3 の適用経路表** であり、本書に経路を複製しない（`tools/check_rate_limit_wiring.py` がその表と実装を機械検査する）。実装をポートへ束ねる場所は `src/composition/` 配下に限る（関心ごとにファイルを分けてよい）。

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
| `src/domain/errors.ts` | `DomainValidationError` / `SearchQueryRejectedError` / `NotFoundError` / `RateLimitExceededError` / `NetworkError` / `AuthError` / `UpstreamError` を **クラスとして定義** する。各クラスは利用者への提示単位を表す `ErrorKind`（7 値）を `kind` として持つ（判別条件の正本は [`prd.md`](../../02_requirements/prd.md) §7） |
| `src/infrastructure/` | HTTP ステータス・例外を **上記ドメインエラーへ変換** する（変換表は下記） |
| `src/usecases/` | ドメインエラーをそのまま送出する（握り潰さない・別型に包み直さない）。fail-soft を明示した経路のみ §4.2 の例外条項に従う |
| `app/` | ドメインエラーを **UI の状態へ写す**（Not Found 表示 / レート制限の案内 / 再試行導線）。`aria-live` での通知は `NFR-12` |

🔴 **利用者向けの文言は `kind` から i18n で引く。** 各エラーの `message` は開発者向けのログ用であり、画面にも API 応答にもそのまま出さない（内部情報を漏らさない・`NFR-8`）。

### 4.1. 上流の応答 → ドメインエラーの変換表

| 上流の応答 | ドメインエラー | `kind` |
|---|---|---|
| `fetch` 自体が失敗（到達不可） | `NetworkError` | `network` |
| `403` / `429` かつ `x-ratelimit-remaining: 0` | `RateLimitExceededError` | `rateLimitPrimary` |
| `403` / `429` かつ `retry-after` あり（上記以外） | `RateLimitExceededError` | `rateLimitSecondary` |
| `401` / `403`（上記以外） | `AuthError` | `auth` |
| `422` | `SearchQueryRejectedError` | `validation` |
| `404` | `NotFoundError`（詳細取得は `null` へ倒す経路もある） | `notFound` |
| `5xx`・スキーマ不一致 | `UpstreamError` | `upstream` |

🔴 **判定順序は上表のとおり**（`prd.md` §7 の表と一致させる）。一次レート制限に `retry-after` が同時に付く応答があるため、`x-ratelimit-remaining: 0` を先に見ないとログイン導線（`AR-5` / `US-25`）が消える。

🔵 **`rateLimitSecondary` は上流由来だけではない**: `src/composition/rate-limit.ts` の自リクエスト間引き（Issue #122・Cloudflare Rate Limiting binding）も、**上流へ出る前（検索経路）／重い処理に入る前（Gem 一覧）** に同じ `RateLimitExceededError('rateLimitSecondary')` を投げる。利用者への提示要件（`retry-after` 秒後に再試行可能）が一致するため `kind` を再利用しており、**上表は「上流応答からの変換」だけを定義している** 点に注意する。

🔵 **`SearchQueryRejectedError` は「上流がクエリを受理しなかった」を表す**（`DomainValidationError` は値オブジェクトの不変条件違反のみに残す・[ドメインモデル](../data-model/domain-model.md) §4）。

- 値オブジェクトの生成は **不正なら例外**（`DomainValidationError`）。URL パラメータのように「不正でも落とさず既定値へ倒す」箇所では `tryParse`（`null` を返す変種）を使う。
- 🔴 **`catch` して `console.error` だけして握り潰さない。** 握り潰しは失敗を「0 件」に化けさせ、`AC-5`（Not Found 表示）と区別できなくなる。

### 4.2. `src/usecases/` の fail-soft 例外条項

🔵 **例外**: **表示単位が欠落しても他機能を巻き込まないと明示された経路** に限り、usecase が `catch` して失敗値へ畳んでよい（`app/` 配下に `error.tsx` が無く、漏らすとページ全体が 500 になるため・`D-28`）。現時点の該当経路は次の 2 本だけで、増やすときは本節へ追記する。

| 経路 | 失敗値 | 巻き添えを防ぐ対象 |
|---|---|---|
| `src/usecases/search-gems.ts` | `{ status: 'failed' }` | Gem 一覧ページ全体 |
| `src/usecases/get-daily-digest.ts` | `null` | トップページ全体（検索機能） |

畳む場合は次の 2 つを必ず守る。

1. **「0 件」と区別できる値にする**（`items: []` / 空結果へ畳まない）。区別できないと `AC-5`（Not Found 表示）と失敗が混ざり、上の 🔴 が禁じた状態に戻る。
2. **失敗を必ずログに出す**（`console.warn` + 例外オブジェクト。キー・値・生ペイロードは出さない）。無音で畳むと機能が恒久的に欠落しても観測できない。

🔴 **ドメインエラーは従来どおり送出する。** 本条項が許すのは「取得・生成そのものの失敗を表示単位ごと落とす」ことだけで、`ErrorKind` を持つドメインエラーを握り潰して UI から消してよいという意味ではない。

---

## 5. Next.js（App Router）との対応づけ

| Next.js の要素 | この設計での位置づけ | 規則 |
|---|---|---|
| Server Component（`page.tsx`） | Frameworks & Drivers | composition root からユースケースを取り、結果を `src/ui/` に渡すだけ。**ロジックを書かない** |
| Client Component（`"use client"`） | Presentation | `src/ui/` に置く。ユースケース・アダプタを import しない |
| Route Handler（`route.ts`） | Frameworks & Drivers | 同上（薄く保つ）。MVP は Read 中心のため原則不要 |
| Server Action | Frameworks & Drivers | 入力検証 → ユースケース呼び出しのみ |
| `use cache` / `cacheLife` / `cacheTag` | Infrastructure の実装詳細 | 🔴 **ユースケース・ドメインから直接触らない**。キャッシュは `CachePort` 越しに扱う（`D-18` により Cloudflare での実体は HTTP `Cache-Control` + Workers Caching） |
| `searchParams` | 入力の境界 | 🔴 **値オブジェクトへ変換してからユースケースへ渡す**（生の文字列を奥へ流さない・`NFR-19`）。⚠️ **唯一の例外は Gem 一覧（`/[locale]/gems`）の `q`**（下記） |

⚠️ **`searchParams` 値オブジェクト化の唯一の例外: Gem 一覧の `q`**（`SP-19` / `D-37`）

Gem 一覧（`app/[locale]/gems/page.tsx`）は `q` を **生値のままユースケース（`searchGems`）へ渡し**、ユースケース内で
`tokenizeQuery`（`src/domain/model/gem-keyword.ts`）が照合トークン列へ正規化する。境界で `searchKeyword` を挟まないのは、
GitHub 検索（`RepositoryQueryPort`）と Gem 候補プールで **照合規則そのものが違う** ためにゃ。

- `searchKeyword` は GitHub 検索 API の不変条件（修飾子・ブール演算子の拒否、`MAX_KEYWORD_LENGTH`）を守る値オブジェクトで、
  違反した入力は `''` へ丸められる。これを Gem 一覧の境界に挟むと、`q=go NOT rust` や日本語だけの検索語が「未入力」扱いになり、
  画面が `gems.queryRequired`（検索語を入れてください）へ落ちて `gems.unmatchableQuery`（この検索語では照合できない旨の案内）に
  到達しなくなる — **拒否理由が別物にすり替わる退行** が入る
- Gem 候補プール側の照合規則（repo 名・パッケージ名の単語境界一致・全語 AND・0 件時のみ 1 語へ緩和）は
  `gem-keyword.ts` が正本であり、そこが生値の切り詰め（トークン数 16 語・生値長 256 文字）と正規化を担う。
  つまり「生の文字列を奥へ流さない」の趣旨（**検証されていない値をドメインの奥で使わない**）は、境界ではなくユースケース入口の
  `tokenizeQuery` で満たしている

🔴 **この例外を「規約違反」として `searchKeyword(rawQuery)` を境界に挟み直さないこと。** 例外はこの 1 経路だけで、
他の入力（検索ページの `q`・`page`・`sort`）は従来どおり境界で値オブジェクトへ変換する。
`tools/check_architecture_boundaries.py` は import 方向しか見ないため、この規約は機械検査では守られない。

### 5.1. `LocaleSwitcher` を `layout.tsx` へ一本化しない理由（`SP-8`）

`LocaleSwitcher`（`src/ui/locale-switcher.tsx`）は共通の `app/[locale]/layout.tsx` に一本化せず、
`app/[locale]/page.tsx` と詳細ページ（`app/[locale]/repos/[owner]/[repo]/page.tsx`）へ個別に配線している。

**制約**: Next.js 16 + OpenNext Cloudflare は middleware / `proxy.ts` を採用しておらず、Server Component の
`layout.tsx` から現在のパス名（`currentPath`）を安定して取得する標準手段が無い。`layout.tsx` は `params` から
ロケールは取れるが、詳細ページの `owner`/`repo` セグメントまでは受け取らないため、切替後のリダイレクト先
（ロケールだけを差し替えた同一パス）を共通レイアウト側で組み立てられない。

**将来の再検討条件**: Next.js または OpenNext Cloudflare が middleware ベースの pathname 取得（あるいはそれに
相当する標準手段）をサポートしたら、一本化を再検討する。

参照: PR #141（`SP-8`）レビュー指摘 / `content/discussions/sp8-auth-i18n-20260819/whiteboard.md`。

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

🔵 **`check_architecture_boundaries.py` の外側を埋める検査（Issue #612）**: 上記 `ARCH-1`〜`7` はいずれも **import の向き**（どの層からどの層へ）しか見ておらず、「向きは正しいが層の中身が肥大化している」型の違反（同じオーケストレーション手順が `app/` に重複する・複数ポートの結果を `app/` が実行時に組み合わせて表示用データを作る等）は検出できなかった。2 本の検査がこの隙間の一部を埋める（いずれも `python3 tools/check_app_thinness.py` / `check_duplicate_source_patterns.py` として PR 前セルフレビューから実行）。

| # | 検査 | 見るもの |
|---|---|---|
| `check_app_thinness.py` | `app/` が「薄い」かどうかの量的な代理指標 | ファイル行数 / トップレベル関数・コンポーネント定義数 / `src/domain/` からの import 数 / 配列操作チェーン（`.filter()` `.map()` `.reduce()` `.sort()` `.slice()`）の出現数。4 指標いずれかが閾値超過で違反。導入時点の既存超過ファイルは `ALLOWLIST` に実測値を登録して PASS させる |
| `check_duplicate_source_patterns.py` | 同一の正規表現リテラルが複数ファイルへ独立にコピーされていないか | `src/**/*.ts(x)` / `app/**/*.ts(x)` / `tools/**/*.py` を横断走査し、同一パターンの重複出現を検出する。意図的な分離（脅威モデルが違う等）は出現箇所全てに `// dup-ok: {理由}`（Python は `# dup-ok:`）を書けば通す。理由が空のマーカーは無効 |

⚠️ **それでも埋まらない隙間**: 上記 2 検査は **量的な代理指標** であり、「意味的に同じ手順が 2 箇所に書かれているか」「複数ポートの結果を実行時に組み合わせているか」そのものは判定しない（閾値超過という兆候から人が疑うための入口に留まる）。`ARCH-R1` / `ARCH-R2` と同じく、最終判断はレビュー観点のまま残る。

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
