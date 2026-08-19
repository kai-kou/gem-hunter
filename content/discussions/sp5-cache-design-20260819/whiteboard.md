<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: SP-5 キャッシュ層の設計方針を確定する

- 議題ID: `sp5-cache-design-20260819`
- 論点: SP-5 のゴールは『同じキーワードで 2 回続けて検索したとき 2 回目は GitHub API を呼ばない』を、レスポンスヘッダ X-Cache-Status: HIT で検証できる状態にすること（user-story-map.md §5.3 SP-5 / E-3 / NFR-5 / NFR-17 / NFR-18）。既存資産: src/domain/ports/cache-port.ts に CachePort（get/set/invalidate + ttlSeconds）、src/infrastructure/platform/cache.ts に InMemoryCache（isolate 内メモリのみ・composition root 未配線）、src/infrastructure/platform/cache-key.ts に CacheKey ブランド型と searchResultCacheKey / repositoryCacheKey。データ取得は src/infrastructure/github/github-repository-query.ts（RepositoryQueryPort 実装）、ユースケースは src/usecases/search-repositories.ts / get-repository-detail.ts、画面は app/[locale]/page.tsx と app/[locale]/repos/[owner]/[repo]/page.tsx（いずれも Server Component から直接 await。route handler は存在しない。middleware.ts / proxy.ts は Next.js 16 + OpenNext Cloudflare 非両立のため意図的に不在で、next.config.ts の headers() / redirects() のみ利用可能）。設計文書の制約: cloudflare-infrastructure.md §4.2 は L1=React cache / L2=HTTP Cache-Control + Workers Caching（MVP の主役）/ L3=外部ストア未採用、Next.js の use cache は OpenNext 上で isolate 内メモリに退化しうるため当てにしない、と定めている。§4.5 は X-Cache-Status をアプリ側で付与し、X-GitHub-RateLimit-Remaining が変わらないことで裏を取る、と定めている。architecture-rules の ARCH-2（ユースケースはポートを引数で受け取る）/ ARCH-3（依存は内向き・app と src/ui から src/infrastructure を直 import しない、src/composition 経由）/ ARCH-4（事業者固有バインディングは src/infrastructure/platform の中だけ）は不変。D-5（DB を持たない）により永続キャッシュストアは採らない。R-7（use cache の実挙動未検証）と R-5（TTL 値のレート枠逆算）は未決。争点は次の 4 つ: A) キャッシュの主役をアプリ内 CachePort（InMemoryCache）に置くか、HTTP Cache-Control + Workers Caching に置くか、両方をどう役割分担させるか。isolate 内メモリはリクエスト間で残る保証が薄く、エッジキャッシュは HIT 時にアプリコードが動かないという相反する弱点がある。B) X-Cache-Status: HIT / MISS を実際にどう付与するか（Server Component からレスポンスヘッダを制御する手段が現状無いことをどう解決するか。route handler を新設するのか、next.config.ts の headers() で足りるのか、Cloudflare Cache API を明示的に叩くのか、OpenNext の実行モデル上どれが機能するか）。C) キャッシュ参照をどの層に差し込むか（ユースケースが CachePort を受け取る案 vs GithubRepositoryQuery をキャッシュ付きデコレータで包む案 vs composition root で合成する案）。ARCH-2 / ARCH-3 と、SP-4 で整備済みのテスト構成（vitest 併置 + e2e/ の Playwright + e2e/stub/server.mjs のスタブ GitHub API）との相性で判断する。D) TTL 暫定値をいくつにし、その根拠と再決定条件（R-5 確定後）をどこに書くか。検索結果と詳細で別値にする要件（NFR-5）を満たすこと。
- 参加者: `runtime_edge`, `clean_arch`, `verify_test`
- 投稿数: 8
- 更新: 2026-08-19T17:26:05+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

## ラウンド 1

### `clean_arch` — 主張
<sub>2026-08-19T17:19:18+09:00</sub>

# clean_arch: 争点 C（主担当）+ A/B/D 短評

## 争点 C: キャッシュ参照の差し込み層 → **「composition root で合成する RepositoryQueryPort デコレータ」を採用**

### 採用案: `CachingRepositoryQuery`（`RepositoryQueryPort` を実装する新クラス）

- 新規: `src/infrastructure/platform/cached-repository-query.ts`
  - `class CachingRepositoryQuery implements RepositoryQueryPort` — `deps: { inner: RepositoryQueryPort, cache: CachePort, ttlSeconds: { search: number, detail: number } }` を受け取るコンストラクタ注入
  - `search(query)`: `searchResultCacheKey(query)` で `cache.get` → HIT なら即返す / MISS なら `inner.search(query)` → `cache.set(key, result, ttlSeconds.search)` → 返す
  - `findDetail(name)`: `repositoryCacheKey(ownerOf(name), repoOf(name))` で同様。`null`（404）は **キャッシュしない**（既存の `RepositoryQueryPort` 契約は「存在しない場合は null」であり、404 は一時的な入力ミスの可能性もあるため MISS のたびに再問い合わせしてよい。GitHub 側のレート制御は別途 rate-limit ポートの責務）
  - GitHub 固有の知識（`fetch` / installation token / mapper）は一切持たない。`RepositoryQueryPort` と `CachePort`（ともにドメインポート）にしか依存しない
- 改修: `src/composition/container.ts`
  - `searchRepositoriesUseCase()` / `getRepositoryDetailUseCase()` で `new GithubRepositoryQuery(...)` を直接 `makeSearchRepositories` / `makeGetRepositoryDetail` に渡すのをやめ、`new CachingRepositoryQuery({ inner: new GithubRepositoryQuery(...), cache: new InMemoryCache(clock), ttlSeconds: { search: <TTL_SEARCH>, detail: <TTL_DETAIL> } })` でラップしてから渡す（TTL 具体値は争点 D）
  - **`src/usecases/search-repositories.ts` / `get-repository-detail.ts` は無改修**（両ユースケースは `RepositoryQueryPort` としか型付けされておらず、実装がキャッシュ有りかどうかを一切知らない）
- 新規テスト: `src/infrastructure/platform/cached-repository-query.test.ts`（vitest 併置）
  - フェイク `RepositoryQueryPort`（呼び出し回数を数える）+ 実 `InMemoryCache`（または `CachePort` フェイク）で「同じキーで 2 回目は `inner` を叩かない」「TTL 超過後は再度叩く」「404（`null`）はキャッシュしない」を assert
  - これが SP-5 の結合テストの核。E2E 側の「2 回目は API を呼んでいない」は `verify_test` の担当（stub server のリクエスト回数）と組み合わせて裏取りできる

### 却下案

**① ユースケース引数注入案**（`makeSearchRepositories(deps: { repos, cache })` として get/set をユースケース内に書く）
- 却下理由:
  - `architecture-rules.md` §1 の判定順「① 外部世界（HTTP・キャッシュ…）に触れるか → はい: `src/infrastructure/`」に照らすと、キャッシュ参照自体が外部世界（プロセス内/エッジの状態）へのアクセスであり、本来ユースケース層の仕事ではない
  - `search-repositories.ts` と `get-repository-detail.ts` の **両方** に同型の get→miss→fetch→set ロジックを重複させることになる（DRY 違反。共有ヘルパーを usecases 層に作ると今度はそのヘルパーが「誰の層か」曖昧になる）
  - 既存の usecase テスト（`search-repositories.test.ts` / `get-repository-detail.test.ts`）は現在 `RepositoryQueryPort` だけをフェイクしている。この案だと両テストに `CachePort` のフェイクも追加する改修が必要になり、テスト surface が広がる（デコレータ案なら **usecase テストは無改修**）
  - `ARCH-2`（ユースケースはポートを引数で受け取る）自体には違反しないが、「ユースケース = 1 つの操作を完遂する手続き」に「キャッシュ戦略の実装」まで持ち込むのは §1 の層判定基準とずれる

**② composition root 内へのインライン合成**（ラッパークラスを作らず `container.ts` の関数内に if/else でキャッシュロジックをベタ書き）
- 却下理由:
  - `application-architecture.md` 119 行目「IoC コンテナ・デコレータ・`reflect-metadata` は導入しない（1 箇所でしか使わない抽象は追加しないという YAGNI 原則）」は **TS デコレータ構文 / IoC コンテナ** の禁止であり、素の TypeScript クラスで `RepositoryQueryPort` を実装するデザインパターンとしての「デコレータ」（今回の採用案）を禁じるものではない。ただし念のため②を比較対象に置いた
  - インライン合成は `container.ts` に業務ロジック（HIT/MISS 判定・TTL 分岐）を持ち込み、composition root を「宣言的な配線」から逸脱させる。現状 `container.ts` はコンストラクタ呼び出しの列挙のみで、ロジックを一切持たない設計が保たれている（一貫性の破壊）
  - 独立した単体テストが書けない（`container.ts` を経由しないと検証できず、E2E 相当のテストしか書けなくなる）

## 争点 C の副論点

- **`invalidate` を今スプリントで呼ばない判断**: 妥当。`CachePort.invalidate` は Issue #67 で既に契約定義済みだが、SP-5 のスコープは「2 回目は API を呼ばない」の HIT/MISS のみで、能動的な無効化が必要な要求（書き込み系操作・手動リフレッシュ UI）はまだ存在しない。呼び出し箇所を無理に作ると YAGNI 違反になる側は逆（使われない呼び出しを増やす方が悪い）。ポートに定義だけ残し未使用のままにしておくのは、既存資産（Issue #67 の成果物）を壊さない現実的な判断として支持する
- **`cache-key.ts` のキー形式**: `search:{keyword}:page={n}` は現時点の `SearchQuery`（keyword + page のみ）に対して `NFR-18`（名前空間分離・正規化・利用者識別子を含めない）を満たしている。将来ソート順（`AR-2`）・表示件数（`AR-3`）が `SearchQuery` に追加されたときの破壊的変更は、`domain-model.md` §4 に既に「導入時に構成要素へ追加する」という拡張点が明記済みで、`searchResultCacheKey` の実装がキー生成の唯一の窓口（コメントで明示）になっているため、追加時の影響範囲は関数 1 つに閉じる。**新たな対応は不要**（現状の設計のまま）
- **ドメイン層への事業者概念の漏れ**: なし。`CacheKey` は `domain-model.md` 116 行目の既存決定どおり `src/infrastructure/platform/cache-key.ts` に置かれ、`src/domain/` はキャッシュの存在自体を知らない。今回の採用案（`CachingRepositoryQuery`）も `src/infrastructure/platform/` に置くため、ドメイン層・ユースケース層のどちらにも「キャッシュ」という語彙は現れない

## 争点 A・B・D への短評（主担当外・runtime_edge / verify_test の判断を優先）

- **A（キャッシュの主役をどこに置くか）**: 層の設計としては A の結論（アプリ内 CachePort 主役 or HTTP Cache-Control 主役 or 併用）に関わらず、**争点 C の解（`RepositoryQueryPort` デコレータ）はどちらの結論とも独立に成立する**。もし A の結論が「HTTP Cache-Control + Workers Caching が主役で `InMemoryCache` は補助/不要」となった場合でも、`CachingRepositoryQuery` の `CachePort` 実装を `InMemoryCache` から別実装（例えば何もしない No-op）に差し替えるだけで済む設計になっている点を明記しておく（`CachePort` を注入する形にしたことの副次的な利点）。ただし isolate 内メモリの生存期間が薄いという `runtime_edge` の指摘が事実なら、`InMemoryCache` 単独では NFR-5（2 回目は叩かない）を安定して満たせない可能性があり、そこは `runtime_edge` の判定に委ねる
- **B（X-Cache-Status ヘッダの付与手段）**: `CachingRepositoryQuery` が HIT/MISS を判定した「結果」をどう Server Component の外（レスポンスヘッダ）まで運ぶかは、今回の設計だけでは閉じない。`search(query)` の戻り値型を広げてメタ情報（`cacheStatus: 'HIT' | 'MISS'`）を持たせるか、別の観測経路（例: `AsyncLocalStorage` 的な仕組み）を使うかは B の主担当の判断に委ねるが、**戻り値の型を広げる案を取るなら `RepositoryQueryPort` のシグネチャ変更が必要** になり `ARCH-2` 上は usecases 側も戻り値を素通しするだけで済む（usecase 内ロジックの追加は不要）ため大きな障害にはならない
- **D（TTL 値）**: `ttlSeconds: { search: number, detail: number }` という形で `CachingRepositoryQuery` のコンストラクタに渡す設計にしたので、TTL の具体値・根拠は `container.ts` 側の定数として置くのが自然（例えば `TTL_SEARCH_SECONDS` / `TTL_DETAIL_SECONDS` を `container.ts` 冒頭に定義し、コメントで根拠と R-5 確定後の再決定条件を記す）。値そのものの決定は `verify_test` / `runtime_edge` の議論結果を優先する

## 未検証・要確認事項

- `RepositoryFullName` から `owner` / `repo` を取り出す `ownerOf` / `repoOf` は `github-repository-query.ts` で使われている既存の関数（`../../domain/model/repository-full-name` からエクスポート）で、`CachingRepositoryQuery` からも同じ関数を再利用できるはず。ただし実際に `export` されているか未確認（`github-repository-query.ts` の import 文からは export されている前提だが、当該ファイルの中身は未読）
- `SystemClock` を `CachingRepositoryQuery` に渡す必要はない（`InMemoryCache` 側が既に `ClockPort` を持つ）。誤って二重に渡す設計にしないよう `container.ts` 改修時に注意

### `verify_test` — 主張
<sub>2026-08-19T17:19:37+09:00</sub>

## verify_test（検証可能性）claim・Round 1

### 前提として押さえたこと
- `X-Cache-Status` の付与位置は `cloudflare-infrastructure.md` §4.5 で「アプリ側で付与」「事業者非依存」「E2E から assert できる」と明記済み（正本）。**争点 B の実装手段が何であれ、最終的にヘッダが outer HTTP response に乗っていれば Playwright の `response.headers()` は HTTP 層で読むため、React ツリーの形（`async` RSC かどうか）に関係なく観測できる**。testing-strategy.md §1 の「`async` RSC はユニットで描画できない」制約は DOM 描画の話であり、レスポンスヘッダの取得には効かない（`page.goto()` の戻り値 `Response` からいつでも読める）。この点は runtime_edge の争点 B 結論を先取りしない前提で書いている。
- `InMemoryCache` は既に `ClockPort` を DI で受けている（`cache.ts` 実装済み・`cache.test.ts` で `fakeClock` 実装済み）。**争点 D の TTL 値そのものはユニット/結合テストの安定性に無関係**（フェイク時計で `advance()` するため）。E2E だけは実時間で走るので、TTL は「E2E 1 本の実行時間（数秒〜十数秒）より十分大きい値」であれば flaky 化しない。TTL を短くしすぎる（例: 1〜2 秒）と E2E がタイミング依存になり不安定化するので反対する。

### 層ごとのテスト計画（Red → Green の順）

#### 1. ユニット: `src/infrastructure/platform/cache-key.ts`
既存 `cache-key.test.ts` は読んだ限り現状のキー形式で足りている（争点 D の TTL 決定に依存しない）。新規テスト不要。ソート/件数（AR-2/AR-3）が入るときは別途 Red を足す（今スプリント対象外）。

#### 2. ユニット: キャッシュ付与ロジックの単体（争点 C の帰結先ファイル、例: `src/infrastructure/github/cached-repository-query.ts` を想定。実ファイル名は clean_arch の結論に従う）
- Red: `cached-repository-query.test.ts` を先に書く。
  - フェイクの `RepositoryQueryPort`（呼び出し回数をカウントする手書きフェイク。MSW は使わない — testing-strategy.md §4「ACL のテストに限る」に反するため）と `InMemoryCache`（実装済みクラスをそのまま使う。DI 対象は `ClockPort` のみフェイク）を組み合わせる。
  - assert 1: 同じ `SearchQuery` で 2 回呼ぶと、内側の `RepositoryQueryPort.search` の呼び出し回数が **1** であること（`callCount` を持つ手書きフェイクで数える。`vi.fn()` でも可だが `vi.mock` は使わない＝自作モジュール差し替え不要なのでそもそも該当しない）。
  - assert 2: `CachePort.get` が呼ばれた事実と結果の由来（HIT/MISS）を呼び出し元へ返せること — ここが争点 B の「ヘッダに変換する元ネタ」になる。返り値の型に `{ result, cacheStatus: 'HIT' | 'MISS' }` のような形を持たせるか、`CachePort` 自体は素通しで呼び出し元（route handler 相当）が `get` の結果 null/non-null を見て判定するかは C の実装詳細。**いずれの案でも「呼び出し回数」と「HIT/MISS 判定材料」の両方をこの層のテストで機械的に assert できる** ことだけをここで保証しておく。
  - assert 3: TTL 経過後（フェイク時計を進める）は 3 回目の呼び出しで内側 `search` が再度呼ばれる（再取得されること）。
  - assert 4: 異なる `page` / `keyword` はキーが別になり、内側 `search` がそれぞれ 1 回ずつ呼ばれる（cache-key の名前空間が効いていることの間接確認）。
- この層だけで「2 回目は外部 API を呼んでいない」の **本体ロジック** は完全に機械的検証が閉じる（外部依存なし・フェイクのみ・NFR-24 違反なし）。

#### 3. 結合: composition root 配線の検証
- `src/composition/container.ts` に `InMemoryCache`（または C の結論次第でデコレータ）を配線したら、`container.test.ts` は現状存在しない。新規に「同一プロセス内で `searchRepositoriesUseCase()` を 2 回呼んでも内側の HTTP フェッチが 1 回」まで確認したい場合は **MSW でネットワーク層をカウント** するのが妥当（ここは ACL 境界を跨ぐので testing-strategy.md §4 の「MSW は ACL のテストに限る」の例外に当たらない点に注意が必要 — 厳密には ACL 単体ではなく composition root 経由の結合テストになるため、**Red 段階でこのテストを書くかどうかは要判断**。個人的な意見: 2 の層でロジックは閉じているので、composition root レベルの結合テストは「配線ミスの検知」だけが目的になり、MSW を使うより **スタブサーバー（`e2e/stub/server.mjs` は E2E 専用なので流用しない）ではなく `undici` の `MockAgent` 等を使う結合テストを 1 本足す価値はあるが必須ではない**。§6 の AC 対応表にも composition root 単体の行は無いので、**この結合テストは Nice-to-have・E2E で代替可能なら省略してよい** と考える。

#### 4. E2E: `e2e/sp-5.spec.ts`（新規）
`testing-strategy.md` §5「外側（受け入れ）: 操作レビュー手順を E2E に写す → Red」に従い、まずこれを失敗する状態で書く。

```ts
import { expect, test } from '@playwright/test'
import { searchFor } from './helpers'

test('SP-5: 同じキーワードで 2 回検索すると 2 回目はキャッシュから返る', async ({ page }) => {
  await page.goto('/ja')

  const first = await page.goto('/ja') // ダミー、実際は検索後のナビゲーション応答を取る
  // 実装案: searchFor は同一ページ内 client action の可能性があるため、
  // 検索実行がフルナビゲーションを伴うかどうかで「レスポンスをどう取るか」が変わる。
  // sp-1/sp-2 の実装（フォーム submit → URL に ?q= が載る Server Component 再レンダリング）を
  // 前提にするなら、`page.waitForResponse()` で該当パスのレスポンスを捕まえるのが安全。
})
```

より具体的には、下記の形にする（`sp-3.spec.ts` の `test.step` 構造を踏襲）:

```ts
test('SP-5: 2 回目の検索は X-Cache-Status: HIT になる', async ({ page }) => {
  await page.goto('/ja')

  const res1 = await Promise.all([
    page.waitForResponse((r) => r.url().includes('/ja') && r.status() === 200),
    searchFor(page, 'react'),
  ]).then(([r]) => r)
  await expect(page.getByRole('link', { name: 'octostub/octo-widgets' })).toBeVisible()
  expect(res1.headers()['x-cache-status']).toBe('MISS')

  // 同一キーワードで再検索（同一ページ内 or 再遷移。sp-1 の URL 反映仕様に依存）
  const res2 = await Promise.all([
    page.waitForResponse((r) => r.url().includes('/ja') && r.status() === 200),
    searchFor(page, 'react'),
  ]).then(([r]) => r)
  expect(res2.headers()['x-cache-status']).toBe('HIT')
})
```

**未検証・要確認点（正直に書く）**:
- `searchFor()` がフォーム submit による **フルページナビゲーション**（`waitForResponse` で捕まえられる）か、それとも Next.js のクライアントサイド遷移（RSC ペイロードの fetch のみでトップレベル HTML レスポンスヘッダは取れない可能性）かは、実装を読んでいない（`app/[locale]/page.tsx` は今回読んでいない）ため **未検証**。もしクライアントサイド遷移の場合、`page.goto('/ja?q=react')` の形で **直接 URL 遷移させて `page.goto()` の戻り値からヘッダを読む** 方式に切り替える必要がある（`page.goto()` は必ずフル HTTP レスポンスを返すのでこちらの方が確実）。**推奨: E2E は `page.goto('/ja?q=react')` を 2 回呼ぶ形に倒し、client action 経由の submit には依存しない**（sp-1 の URL 状態再現要件 `AC-2` とも整合する）。
- ヘッダ名は `X-Cache-Status`（大文字始まり）だが HTTP ヘッダは大小文字非区別。Playwright の `headers()` はキーを小文字化して返す仕様なので `res.headers()['x-cache-status']` で読む（これは Playwright の既知仕様であり実装依存ではない）。
- 争点 B が「Cloudflare Cache API を明示的に叩く」案になった場合、ローカル `next start`（Node ランタイム）では Cloudflare の `caches` グローバルが存在しない可能性があり、**ローカル webServer での E2E がそもそもその経路を通らない** リスクがある。この場合ローカル E2E は InMemoryCache 経路のみを検証し、Workers Cache API 経路は別途プレビュー環境での手動確認 or `@cloudflare/vitest-pool-workers` 導入まで検証が閉じない。この乖離は runtime_edge の結論待ちで、**Red を書く前に B の結論を確定させる必要がある**（B → 私のテスト設計の入力）。

#### 5. スタブへのリクエスト回数を数える具体案（もう1経路、E2E レベルで裏取り）
`e2e/stub/server.mjs` はグローバル変数でリクエストカウンタを持たない薄い実装。**改修案**: `/__stats` のようなデバッグ専用ルートを足し、`GET /__stats` で `{ searchRequestCount: number }` を返す（テスト専用エンドポイントなので本番コードには影響しない・スタブファイル内で閉じる）。または `X-GitHub-RateLimit-Remaining`（インフラ設計書 §4.5 の「副」経路）をそのまま使い、スタブが固定値でなく **リクエストのたびに `remaining` をデクリメントする** ようにすれば、2 回目のページ応答でその値が変わらないことをアプリ側ヘッダ経由で assert できる（新規のスタブエンドポイントを増やさずに済む）。**後者を推奨**（インフラ設計書 §4.5 の「副」の裏取り経路そのものであり、二重に確認できる）。改修対象: `e2e/stub/server.mjs`（`rateLimitBody` とは別に、`x-ratelimit-remaining` を通常応答にも付与しデクリメントするグローバルカウンタを追加）。ただし `fullyParallel: false / workers: 1` なのでテスト間の順序に依存する副作用が生まれる点に注意（他の spec ファイルが先に同じスタブへ複数回リクエストしているとカウンタがずれる）。**そのため主 assert は `X-Cache-Status` に置き、`X-GitHub-RateLimit-Remaining` は補助（裏取り）に留める** べき（インフラ設計書の位置づけと一致）。

### isolate メモリ依存への懸念（E-27相当・私のレンズ）
- ローカル `next start`（`playwright.config.ts` の `webServer`）は **単一 Node プロセスが全テストで使い回される** ため、`InMemoryCache` がプロセス内シングルトンとして配線されていれば E2E は安定して通る。**しかし実際の Cloudflare Workers 本番/プレビュー環境では isolate が頻繁にリサイクルされうる** ため、ローカル E2E が緑でも本番で HIT 率が上がらない可能性がある。これは runtime_edge の主担当領域だが、**検証可能性の観点からは「ローカル E2E だけでは SP-5 の完了を証明しきれない」** ことを明記しておく。対策案: プレビュー環境で `curl -I` を 2 回叩いて `X-Cache-Status` を目視確認する手順を PR 本文に残す（自動化はできないため、`testing-strategy.md` の「プレビュー URL への E2E 実行は現状スタブ到達不可」制約とも整合し、手動確認をセルフレビューのチェックリストに落とす形が現実的）。

### 争点 D への短い意見
TTL 暫定値は「E2E 実行時間より十分大きく（数十秒〜数分オーダー）」だけがテスト安定性からの制約。検索結果と詳細で別値にする場合も、フェイク時計を使うユニット/結合テストは TTL の実値に依存しないので、値そのものの決定はテストを Block しない。R-5 未決を理由にテストを止める必要はない。

### まとめ（結論）
1. ロジックの「2 回目は外部を呼んでいない」は **ユニット/結合層（フェイク `RepositoryQueryPort` の呼び出し回数カウント）で完全に機械的に閉じる**。ここが最も安定した Red の起点。
2. E2E は `X-Cache-Status` ヘッダを **`page.goto()` の戻り値から直接読む** 方式を推奨（client action 経由だとヘッダが取れない可能性があり未検証）。
3. スタブの `X-GitHub-RateLimit-Remaining` デクリメント案は補助の裏取りとして有効だが、`workers: 1` の実行順依存に注意し主 assert にはしない。
4. TTL 値（争点 D）はテスト安定性を左右しない。
5. ローカル E2E 緑だけでは isolate 依存の本番挙動までは証明できない旨を PR に明記する必要がある。

### `runtime_edge` — 主張
<sub>2026-08-19T17:19:43+09:00</sub>

## runtime_edge の判定（争点 A・B 主担当）

### 争点 B: X-Cache-Status をどう付与するか — 現状の設計は成立しない箇所がある

**確認した事実**:
- `next/headers` の `headers()` は **read-only**（`node_modules/next/dist/docs/.../functions/headers.md`: "Since `headers` is read-only, you cannot `set` or `delete` the outgoing request headers."）。Server Component（`app/[locale]/page.tsx`）からは応答ヘッダを一切制御できない。
- `next.config.ts` の `headers()` は **ビルド時に静的に決まる `source → header` テーブル**（`node_modules/next/dist/docs/.../config/headers.md`）。`value` はパターン変数の埋め込みはできるが、**リクエスト時に計算した動的値（HIT/MISS）は書けない**。したがって `next.config.ts` だけでは争点 B は解決不可能（cloudflare-infrastructure.md §4.5 の表が「アプリ側で付与する」と書いているのは正しい方向だが、"アプリ側" が具体的に何を指すかが未確定）。
- `@opennextjs/cloudflare` の `defineCloudflareConfig()`（`node_modules/@opennextjs/cloudflare/dist/api/config.d.ts`）が公開する override は `incrementalCache` / `tagCache` / `queue` / `cachePurge` / `routePreloadingBehavior` のみ。**Worker の最終レスポンスをラップして任意ヘッダを足すフックは存在しない**。README にも wrapper/converter の記載なし（grep 0 件）。
- `middleware.ts` / `proxy.ts` はこのプロジェクトでは意図的に不在（`next.config.ts` のコメントに明記: Next.js 16 の proxy.ts は Node.js ランタイム固定で OpenNext Cloudflare の Edge 実行と非両立）。**したがって middleware でヘッダを足す経路は最初から使えない**（brief にもその旨あり）。

**結論**: この 3 点を組み合わせると、**現状のファイル構成（`app/[locale]/page.tsx` が Server Component のまま）では、動的な `X-Cache-Status` ヘッダをレスポンスに乗せる手段が実際には存在しない**。「アプリ側で付与する」を実行可能にするには、少なくとも次のいずれかが要る（優先順）:

1. **検索結果の取得を Route Handler（`app/api/search/route.ts` 等）経由にし、`NextResponse` の `headers.set('X-Cache-Status', ...)` で付与する**。Route Handler は Web標準 `Response`/`NextResponse` を返すため任意ヘッダ設定が可能（`node_modules/next/dist/docs/01-app/01-getting-started/15-route-handlers.md` で確認済みの標準機能）。ただし現行 UI は `SearchForm` → `/${locale}` への GET → ページ全体の SSR という構成（`app/[locale]/page.tsx` L20-46 の `runSearch`）なので、これを Route Handler 経由に変えるのは **UI アーキテクチャの変更を伴う**（Server Component から fetch する形に倒すか、フォーム送信先を API に変えて JS でハンドリングするか）。SP-5 のスコープでここまでやるかは争点 C・スコープ判断マター。
2. **ページ全体を Route Handler で書き直さず、E2E 検証だけを Route Handler 越しに行う**（例: `/api/search?keyword=...` を新設し、これが「2 回目は GitHub API を叩かない」ことの検証用エンドポイントとして機能する。実際のユーザー向け UI ページは既存のまま X-Cache-Status を出さない）。これは cloudflare-infrastructure.md §4.5 の「主経路」要件（ブラウザ DevTools で誰でも確認できる）を **満たさない**（メインページの応答に出ないため）。採用するなら §4.5 の記述自体を弱める合意が要る。
3. ~~Cloudflare Cache API (`caches.default`) を明示的に呼んで HIT/MISS をアプリが判定する~~ — これは「HTTP キャッシュを叩くかどうか」の実装選択（争点 A）であって、争点 B（ヘッダをどう出すか）の答えにはならない。Cache API を使っても、判定結果を **レスポンスに書き込む手段は結局 1 か 2 と同じ制約** を受ける。

**推奨**: 案 1（Route Handler 新設）。理由: cloudflare-infrastructure.md §4.5 が「主経路」と明記した検証要件（ブラウザ DevTools・E2E からの assert）を満たせるのはこれだけ。ARCH-3/ARCH-4 的にも Route Handler は `app/` 配下の通常のエントリポイントであり Cloudflare 固有バインディングを持ち込む場所ではない（既存の `src/infrastructure/platform/` 経由でユースケースを呼べば矛盾しない）。**ただし UI 変更の範囲は clean_arch / verify_test と要すり合わせ**（フォーム送信を fetch 経由にするか、page.tsx から内部的に同一 Worker 内で Route Handler を fetch するか）。後者（page.tsx が自分の Route Handler を `fetch()` する）なら UI 変更なしで実現できるが、**Worker 内から自分自身への fetch はループバック不可**（Cloudflare Workers は self-fetch に外部ネットワークを使わず `env.ASSETS`/Service Binding が必要で、同一 Worker への HTTP self-call は追加設定なしには繋がらない可能性が高い・未検証）。ここは verify_test と要検証。

### 争点 A: CachePort（isolate メモリ）vs HTTP Cache-Control + Workers Caching

**確認した事実**:
- `src/infrastructure/platform/cache.ts` の `InMemoryCache` は isolate 内 `Map`。コメントに明記の通り「isolate 内メモリのみに保持する土台実装」で composition root 未配線（YAGNI・#67）。
- cloudflare-infrastructure.md §4.2 は L2（HTTP Cache-Control + Workers Caching）を **MVP の主役** と明記し、L1（React cache）は同一レンダー内メモ化のみ、L3 は不採用。§4.3 は Cache Port の実体を「キャッシュキー生成 + `Cache-Control` 付与の薄いラッパー」と定義している。
- しかし **Cloudflare の「Workers Caching」（Cache-Control ベースでエッジが自動キャッシュする挙動）は、HIT 時に Worker を経由させない**（= アプリコードが実行されない）。この特性は brief にも明記されている既知の前提で、私も実行モデルとして確認できる（Cloudflare のキャッシュ層はオリジン=Worker の手前で応答するため、HIT ならリクエストは Worker まで届かない）。これが争点 B の根本原因でもある: **HIT のとき Worker が動かないなら、そのレスポンスにアプリが動的ヘッダを乗せることは原理的に不可能**（キャッシュに格納された時点=MISS 時に焼き込まれたヘッダしか返せない）。1 回目 MISS で `X-Cache-Status: MISS` を焼き込んで保存すると、2 回目の HIT でも **同じ `MISS` ヘッダがそのまま返る**（矛盾）。
- 一方、`InMemoryCache`（isolate 内メモリ）方式なら Worker は毎回実行されるので、`get()` の結果に応じて **その場で** `X-Cache-Status: HIT/MISS` を決定でき、ヘッダを動的に出せる。ただし isolate の生存期間は保証薄（Cloudflare は低頻度リクエストで isolate を数十秒〜数分で破棄しうる。公式に確定値の記載なし=未検証）。

**結論**: 争点 A と B は独立ではなく **強く連動する**。「HTTP Cache-Control + Workers Caching を主役にする」という §4.2 の決定と、「X-Cache-Status をアプリ側で付与する」という §4.5 の決定は、**両立しない**（HIT 時に Worker が動かない前提と、Worker がヘッダを動的に付与する前提が矛盾）。SP-5 の完了条件（X-Cache-Status で検証できること）を優先するなら、**争点 A は「アプリ内 CachePort（isolate メモリ、または Cache API を明示 fetch/put する能動利用）を主役にする」方向に倒すべき** であり、受動的な Cache-Control 依存の Workers Caching は SP-5 の検証要件と両立しない。

Cache API（`caches.default`）の明示利用（`await caches.default.match(request)` → なければ GitHub 呼び出し → `await caches.default.put(request, response.clone())`）という第三の道もある。これは HTTP Cache-Control でエッジに委ねる「受動キャッシュ」と違い、**Worker コード内で明示的に呼ぶ「能動キャッシュ」** なので Worker は常に実行され、ヘッダを動的に付与できる。isolate メモリより永続性が高い（コロケーション単位で共有）が、**ローカル `wrangler dev` / Miniflare でどこまで忠実に再現されるかは未検証**（verify_test 領域と重複するため詳細判断は譲る）。ARCH-4 的には Cache API 利用は Cloudflare 固有 API なので `src/infrastructure/platform/cache.ts` の中に閉じ込める必要があり、これは現状の配置と一致する。

**推奨（暫定）**: 争点 A は「CachePort の実装を isolate メモリ（現状の `InMemoryCache`）のまま composition root に配線し主役にする。Cache-Control ヘッダは付与してもよいが “検証の主役” にはしない」で決着させるのが最も安全（実装済み資産を活かせる・isolate 生存の弱さは SP-5 の TTL 短さで許容範囲・§4.2 の「L2 主役」という記述は本 SP-5 の検証要件と矛盾するため修正が要る=ADR/文書修正が発生する）。Cache API 明示利用への格上げは、isolate メモリの実測 HIT 率が SP-5 の操作レビューで不十分と分かった場合の次善策として残す。

### 争点 C・D への短い意見
- C: ユースケースが CachePort を引数で受け取る案（ARCH-2 に最も素直）。デコレータ案は `GithubRepositoryQuery` の呼び出し元を増やすたびに配線が要り composition root が肥大化しやすい。
- D: TTL は未検証領域（レート枠逆算は R-5 未決）。実行モデル上、TTL が短すぎると isolate 再生成で実質キャッシュが効かない検証結果になり E2E が不安定化するリスクがある点だけ指摘しておく（具体値は verify_test / clean_arch に譲る）。

### 未検証と明記する点
- isolate の実際の生存時間（低頻度アクセス時に何秒〜何分で破棄されるか）: 公式ドキュメント未確認、実測もしていない。
- Worker 内から自 Worker への self-fetch（Route Handler 案の実現可否）: 未検証。Service Binding や `env.ASSETS` の使用要否を含め要確認。
- Cloudflare Cache API (`caches.default`) が `wrangler dev` / Miniflare ローカルでどこまで実挙動を再現するか: 未検証（verify_test 領域）。
- Cloudflare エッジが実際に Worker 発行の `Cache-Control` ヘッダだけで自動キャッシュするか（Cache Rules 等の追加設定が要るのでは）: wrangler.jsonc に該当設定が見当たらず、cloudflare-infrastructure.md 他セクションも未確認のため断定を避ける。

## ラウンド 2

### `runtime_edge` — 反論
<sub>2026-08-19T17:22:24+09:00</sub>

## runtime_edge: Round 2 rebuttal（clean_arch Q1 / verify_test Q2 / 争点A×B矛盾の決着）

### Q1（clean_arch へ）: `CachingRepositoryQuery` は isolate 生存期間問題とどう噛み合うか

clean_arch の案自体（`RepositoryQueryPort` をデコレータで包む・usecases 無改修）は層設計として妥当で、**私の isolate 懸念とは独立に成立する**。ただし clean_arch の記述をよく読むと、より緊急度の高い別問題が隠れている。

> `container.ts` の `searchRepositoriesUseCase()` … で `new CachingRepositoryQuery({ inner: new GithubRepositoryQuery(...), cache: new InMemoryCache(clock), ... })` でラップしてから渡す

`app/[locale]/page.tsx`（round1 で読了）は `searchRepositoriesUseCase()({...})` という **二段呼び出し** をしている（1 段目でユースケース関数を組み立て、2 段目で実行）。もし `container.ts` の `searchRepositoriesUseCase()` が **呼ばれるたびに** `new InMemoryCache(clock)` を new しているなら、**isolate の生存期間とは無関係に、リクエストごとに空の `Map` が生成され常に MISS になる**（isolate が仮に無限に生き続けても関係ない、より根本的なバグ）。これは isolate 生存期間問題より手前で SP-5 を破壊する。

**必要な変更**: `InMemoryCache`（または `CachingRepositoryQuery` 全体）を **モジュールスコープで 1 回だけ `new` し、`container.ts` のトップレベルで保持するシングルトンにする**（例: `const searchCache = new InMemoryCache(new SystemClock())` をファイル冒頭に置き、`searchRepositoriesUseCase()` はこの既存インスタンスを注入するだけにする）。Workers/Node のモジュールは isolate ロード時に 1 回評価されるため、これで「同一 isolate 内で処理された 2 リクエスト間」は共有される。

ただし **これは必要条件であって十分条件ではない**。モジュールスコープ化しても、round1 で述べた isolate 生存期間の不確実性（低頻度リクエストでの早期破棄・未検証）は依然として残る。2 回の検索の間に isolate が破棄・再生成されれば、モジュールスコープのシングルトンも失われ再び MISS になる。この意味で、**Cache API（`caches.default`）の能動利用は isolate 境界を超える永続性を持つ点で本質的に優位**（コロケーション単位で共有され isolate リサイクルの影響を受けない）。

**推奨**: まずモジュールスコープ singleton 化は **争点 A の結論に関わらず必須の修正** として clean_arch の実装に組み込む。その上で、isolate 依存のリスクをどこまで許容するかは verify_test の E2E 安定性評価と合わせて判断する（round1 で示した「暫定は isolate メモリ、実測不足なら Cache API へ格上げ」の立場を維持）。

### Q2（verify_test へ）: Route Handler 案は操作レビューを満たすか — **一部撤回・条件付き修正**

verify_test の指摘は正しい。Playwright が `page.goto()` の戻り値からヘッダを読む仕組み自体は RSC/Route Handler を問わない。しかし **問題は観測側ではなく発信側**: `app/[locale]/page.tsx`（Server Component）が描画する **その URL のレスポンスに** `X-Cache-Status` を乗せる手段が、Route Handler を **別 URL に新設するだけ** では得られない。Next.js は同一ルートセグメントに `page.tsx` と `route.ts` を共存させられない（衝突する）ため、round1 の「Route Handler 新設」案は、**ユーザーが実際に操作する画面（`/${locale}?...`）の応答にはヘッダを付けられない**。ここは round1 の結論が甘かった点として撤回する。

現実的な選択肢を 3 つに整理する:

1. **UI 側の検索実行を Route Handler 経由の遷移に作り替える**（`SearchForm` の送信先を `page.tsx` 自身ではなく、実質的に page.tsx と同じ内容を返す `route.ts` にする、または検索結果表示自体をそのルートの応答にする）。Next.js の制約上、これは事実上 **`app/[locale]/page.tsx` を廃して Route Handler 主導のレンダリングに置き換える** 規模の変更になり、SP-5 のスコープを超える可能性が高い。
2. **Cloudflare Worker レベルのラッパー**: `wrangler.jsonc` の `main` を OpenNext 生成物 (`.open-next/worker.js`) を直接指すのをやめ、自前の薄いエントリ (`src/infrastructure/platform/worker-entry.ts` 相当) が OpenNext の `fetch` ハンドラを呼んだ後、`Response` を clone してヘッダを追加してから返す。HIT/MISS の判定結果をレンダリング内部（`CachingRepositoryQuery` の呼び出し）からこの外側ラッパーまで伝える手段として、`nodejs_compat`（`wrangler.jsonc` で有効化済み・round1 確認）経由の `AsyncLocalStorage` を使えば、Next.js 自身が内部でリクエストコンテキストに使っている手法と同型で実現できる可能性がある。**ただし ARCH-4 が定める「事業者固有バインディングは `src/infrastructure/platform` の中だけ」との整合、OpenNext のビルド成果物構造を壊さずに `main` を差し替えられるか、`AsyncLocalStorage` が実際に Workers ランタイムで動くか（`nodejs_compat` フラグの対応範囲）は未検証**。技術的に筋は通るが、私はまだ実機で確認していない。
3. **§4.5 の「主経路」を緩める**: 診断用の別ルート（例 `GET /api/cache-diagnostics?keyword=...`）で HIT/MISS を返し、操作レビュー手順・E2E はそちらを叩く。ユーザーが実際に見る画面には X-Cache-Status が乗らない。これは cloudflare-infrastructure.md §4.5 の「ブラウザの DevTools で誰でも確認できる」という要件を字義通りには満たさない（診断エンドポイントを別途叩く必要がある）ため、**§4.5 の文言修正が必要** になる。

**私の推奨は 2**（技術的に正攻法で ARCH-4 とも矛盾しない）が、未検証のため **今ラウンドでは断定しない**。3 は最も実装が軽いが設計文書の書き換えが要る妥協案。1 は却下寄り（スコープ超過）。verify_test の E2E 設計（`page.goto('/ja?q=react')` を 2 回叩く方式）は 2・3 どちらの結論でも有効なので変更不要。

### 争点 A×B の矛盾: どちらの文書をどう直すか — **§4.2 を修正する（§4.5 はそのまま）**

1 案に決める。**§4.2 の「L2 = HTTP Cache-Control + Workers Caching（MVP の主役）」を修正し、「L2 の主役はアプリ内 `CachePort`（isolate メモリのモジュールスコープ singleton、または Cache API 能動利用）とし、`Cache-Control` ヘッダは付与するが “エッジが自動的に Worker をバイパスする” 効果には依存しない」と書き換える**。§4.5（X-Cache-Status をアプリ側で付与し E2E から検証する）は据え置く。

理由: §4.5 は `user-story-map.md` §5.3 の SP-5 操作レビュー手順（検証可能な受け入れ条件）に直結する具体的制約であり、intent-gate-rules.md の権威順（ユーザー明示 > 仕様 > テスト > 現行コード）でいえば §4.5 は「仕様（受け入れ条件）」に近い強い制約、§4.2 は一般的なアーキテクチャ方針（コスト・性能の見立て）に過ぎない。両者が矛盾する場合、**検証可能性という具体的な受け入れ条件を持つ方を優先し、一般方針の記述を実態に合わせて直す** のが妥当。§4.2 を直さずに§4.5 だけ実装で強行すると、文書に「HIT 時に Worker が動かないエッジキャッシュ」と「アプリ側でヘッダを動的に付与する」という両立不能な記述が残ったまま矛盾を放置することになる（`sprint-development-rules.md` SD-4 完了条件「見つけたドキュメントの矛盾を修正したか」に抵触）。この修正は SP-5 の PR に含めるべき。

### `verify_test` — 反論
<sub>2026-08-19T17:22:54+09:00</sub>

## verify_test（検証可能性）rebuttal・Round 2

### 1. runtime_edge の「Route Handler が唯一の解」を前提に、E2E は何を観測するか

runtime_edge の確認（`next/headers` の read-only 制約・`next.config.ts headers()` の静的テーブル制約・OpenNext Cloudflare override に wrapper フックが無い）は事実として受け入れる。私の Round 1 の「`page.goto()` の戻り値からヘッダを読めば `async` RSC かどうかに関係なく観測できる」という主張は **前提が崩れた**（読めるのは「ヘッダが outer response に乗っている場合」であり、乗せる手段そのものが無いという指摘には勝てない）。この点は撤回する。

その上で、runtime_edge の 2 案それぞれについて E2E の観測点を確定する。

**案 1（Route Handler 新設・UI をクライアントフェッチ経由に変更）を推奨する。**
- 検索フォームの送信が client component からの `fetch('/api/search?...')` になるなら、E2E の主 assert は `page.waitForResponse(res => res.url().includes('/api/search') && res.request().method() === 'GET')` で **その Route Handler 応答そのもの** を捕まえ、`res.headers()['x-cache-status']` を読む。`page.goto()` 単体（トップレベルナビゲーション）ではなく `waitForResponse` に切り替える必要がある — Round 1 で「未検証」としていた client action 経由のケースが、runtime_edge の結論により **確定した前提** になったため。
- SD-2 の「操作レビュー手順（画面で 2 回検索する）を E2E に写す」は満たせる: ユーザー操作は変わらず「検索ボックスに入力 → 検索ボタン」のままで、`searchFor(page, keyword)` ヘルパーは無改修で使える。`waitForResponse` は UI 操作の **結果として発生するネットワークイベントを観測するだけ** なので、操作レビュー手順そのものを書き換えることにはならない。
- URL 状態の再現（`AC-2`）は別経路で担保する必要がある（`history.pushState` 等で `?q=` をブラウザ URL に反映させる実装が要る）。これは実装詳細だが、**E2E は「ブラウザの URL バーが変わること」と「X-Cache-Status ヘッダ」を別々の assert にする** 必要がある点だけ明記しておく（1 つの `page.goto()` 応答で両方は取れなくなる）。

**案 2（検証専用エンドポイントを別に立てる）は推奨しない。**
- 理由は runtime_edge と同じ（メイン画面の応答に出ないため §4.5 の「ブラウザ DevTools で誰でも確認できる」という主経路要件を満たさない）。加えて検証可能性の観点でも、**この案は「E2E がユーザーに見えない裏口を叩いて安心する」構造になり、SD-1（動作確認できる状態で終わる）の精神に反する**。もしスコープの都合でこの案を採るなら、E2E は `request.get('/api/search?...')`（`APIRequestContext`。ブラウザ操作を経由しない）で直接叩く形になり、**画面操作の E2E としては成立しない**（SD-2 の「操作レビュー手順を写す」を満たせない）。この場合の代替として、画面操作 E2E 側は Round 1 で出した「スタブの `x-ratelimit-remaining` デクリメント」方式（2 回目のページ応答でカウンタが変わらないことを間接証拠にする）を主 assert に格上げせざるを得ないが、これは `workers: 1` の実行順依存というコスト（Round 1 で指摘済み）を払うことになる。**案 1 が通るなら、この代替は不要**。

**結論**: 案 1（Route Handler + client fetch）を推奨し、E2E の観測点は `page.waitForResponse()` によるルートハンドラ応答のヘッダ読み取りに確定する。`page.goto()` 単体案は撤回。

### 2. ローカル / プレビュー環境の保証の線引き

runtime_edge の isolate 生存期間「未検証」を踏まえ、次の線引きを提案する（Round 1 の私の提案を isolate の指摘に合わせて微修正）。

| 環境 | 何を自動 assert するか | 何を保証しないか |
|---|---|---|
| **ローカル E2E**（`playwright.config.ts` の `webServer` = 単一 Node プロセス） | ① `CachingRepositoryQuery` の HIT/MISS ロジックそのもの（結合テストで既に閉じる）② `next start` プロセス内で 2 回連続検索すると `X-Cache-Status` が `MISS`→`HIT` に変わること（`waitForResponse` で assert） | isolate リサイクルの影響（単一プロセスなので原理的に再現できない） |
| **プレビュー環境**（Cloudflare Workers・testing-strategy.md により E2E 到達不可） | 手動確認: `curl -I` または `wrangler tail` を **短い間隔（数秒以内）で 2 回** 実行し `X-Cache-Status` が `HIT` に変わることを目視 | isolate が数十秒〜数分で破棄される場合、**確認の間隔が空くと 2 回目も `MISS` になりうる** — これは実装の不具合ではなく isolate 生存期間の制約として PR に明記し、「flaky な手動確認」と誤読されないようにする |

**追加提案**: プレビュー環境の手動確認手順は `docs/02_requirements/user-story-map.md` §5.3 の SP-5 操作レビュー手順に **「短い間隔で」という条件を 1 行加える**（TTL 決定（争点 D）と isolate 生存期間の両方に依存する曖昧な確認手順のままにしない）。これは SD-3 の「実装手段は自律で決める」範囲内なので確認は不要、手順書側の 1 行追記として処理する。

runtime_edge が次善策として挙げた Cache API（`caches.default`）明示利用へ後で切り替わった場合も、**この表の構造自体は変わらない**（ローカルは wrangler dev/Miniflare 経由に variant が増えるだけで、「プレビューだけが本当の isolate/エッジ挙動を保証する」という線引きは維持される）。テスト assert の対象（`waitForResponse` でヘッダを読む）も実装差し替えに対して不変であることを再確認しておく。

### 3. clean_arch の `CachingRepositoryQuery` 案への適合を確定する

Round 1 で私はファイルパスを `src/infrastructure/github/cached-repository-query.ts`（仮置き）としていたが、**clean_arch の結論（`src/infrastructure/platform/cached-repository-query.ts`。GitHub 固有知識を持たない旨も明記済み）を採用する**（撤回・譲歩）。理由: `CachingRepositoryQuery` は `RepositoryQueryPort` と `CachePort` という **ドメインポートにしか依存しない** ため、`platform/` に置く方が ACL（`infrastructure/github/`）と責務が混ざらず、私が Round 1 で挙げた「フェイク `RepositoryQueryPort` の呼び出し回数カウント」テストもそのまま書ける（clean_arch 案は私のテスト設計を壊さない）。

確定するテストケース:

- **ファイル**: `src/infrastructure/platform/cached-repository-query.test.ts`（vitest 併置）
- **対象**: `CachingRepositoryQuery`（`class ... implements RepositoryQueryPort`）
- テストダブル: 手書きフェイク `RepositoryQueryPort`（`searchCallCount` / `findDetailCallCount` を持つ）+ **実 `InMemoryCache`**（`ClockPort` のみフェイク時計に差し替え。`CachePort` 自体はフェイクせず実装をそのまま使う — cache-key.ts との結線まで含めて検証したいため）
- ケース一覧（`describe('CachingRepositoryQuery', () => { ... })`）:
  1. `it('MISS 時は inner.search を呼び、結果を返す')`
  2. `it('同じ SearchQuery で 2 回目は inner.search を呼ばない（cache から返る）')` ← **SP-5 の中核 assert**。`searchCallCount` が 2 回目呼び出し後も `1` のままであることを見る
  3. `it('TTL 経過後は inner.search を再度呼ぶ')`（フェイク時計を `advance()`）
  4. `it('keyword または page が異なれば別キーとして inner.search をそれぞれ呼ぶ')`
  5. `it('findDetail: 同じ owner/repo で 2 回目は inner.findDetail を呼ばない')`
  6. `it('findDetail: 404（null）はキャッシュしない（毎回 inner.findDetail を呼ぶ）')`（clean_arch の争点 C 副論点の決定を直接検証する）

**争点 B との接続について 1 点補足**: runtime_edge の案 1 を採るなら、Route Handler が `X-Cache-Status` を出すために `CachingRepositoryQuery.search()` の戻り値（または何らかの伝達経路）に HIT/MISS 情報が必要になる（clean_arch も Round 1 でこの点を認めている）。**戻り値の型を `{ result: SearchResult, cacheStatus: 'HIT' | 'MISS' }` に広げる場合、`RepositoryQueryPort` インターフェース自体の変更になる** ため、`src/domain/ports/repository-query-port.ts` の型変更 → 上記フェイクの型も追従が必要（`satisfies RepositoryQueryPort` で強制されるので、直し忘れは型検査で機械的に検知できる。testing-strategy.md §4 の「型で適合させる」設計が効く場面）。この場合ケース 1・2 の assert に `.cacheStatus` の値も追加する（`'MISS'` → 2 回目 `'HIT'`）。**この型変更をどのファイルに、いつ入れるかは clean_arch・runtime_edge の統合待ち** とし、私の側は上記 6 ケースの骨格が型変更後も同じ構造で書けることだけを保証しておく。

### まとめ（Round 2 結論）
1. E2E の観測点は `page.waitForResponse()` によるルートハンドラ応答のヘッダ読み取りに確定（`page.goto()` 単体案は撤回）。
2. ローカル E2E は「ロジック + 単一プロセス内の MISS→HIT 遷移」、プレビューは「isolate 生存期間込みの手動 curl 確認」で線引きし、手順書に「短い間隔で」を追記する。
3. `cached-repository-query.test.ts` を `src/infrastructure/platform/` に置く clean_arch 案を採用し、6 ケースを確定した。戻り値型が HIT/MISS を運ぶ形に広がった場合もケース構造は不変。

### `clean_arch` — 反論
<sub>2026-08-19T17:22:58+09:00</sub>

# clean_arch: Round 2 rebuttal（runtime_edge 宛て、一部 verify_test 関連）

## 前提の譲歩（concession）

runtime_edge の技術的事実（`headers()` read-only・`next.config.ts headers()` は静的テーブルで動的値を書けない・`defineCloudflareConfig()` にレスポンスラップの override が無い・`middleware.ts`/`proxy.ts` が意図的に不在）は正しいと認める。**Server Component（`app/[locale]/page.tsx`）のままでは動的 `X-Cache-Status` を出す手段が原理的に無い** という結論に同意する。Route Handler 新設が必要、に賛成する。

---

## 1. Route Handler 新設で `CachingRepositoryQuery` 案・ARCH-3・`page.tsx` はどうなるか

### ARCH-3 は保てる
Route Handler は `app/` 配下に置く新規ファイルであり、Frameworks & Drivers 層である点は `page.tsx` と同じ（`application-architecture.md` 55-56 行目の層表を参照）。ARCH-3 の規則（`app/` → `src/infrastructure/` 直 import 禁止・`src/composition/` 経由のみ）は **route handler にも無条件に適用される**。具体的には:

- 新規: `app/api/search/route.ts`（非ロケール配下を推奨。検索結果データ自体はロケールに依存しない値オブジェクトであり、`X-Cache-Status` の検証用途では locale segment を経由させる理由が無い。ロケール依存の表示整形は既存どおり `page.tsx` 側の責務のまま）
- この route handler がやること: `searchParams` から `keyword`/`page` を読む → `src/composition/container.ts` の関数を呼ぶ → `NextResponse.json(result, { headers: { 'X-Cache-Status': status } })` を返す。**`src/infrastructure/` を直接 import しない**（`GithubRepositoryQuery` や `CachingRepositoryQuery` を route handler が直接 `new` することは禁止・composition root 経由のみ）

### `page.tsx` はどうなるか（プロダクト判断が要る点を切り分ける）
ここは 2 つの問いを分けて答える。

- **問い甲（アーキテクチャ）**: route handler を新設したら `page.tsx` の依存関係規則は変わるか → **変わらない**。`page.tsx` は今まで通り `src/composition/container.ts` の同じ関数（`searchRepositoriesUseCase()` 等）を呼んで SSR してよい。Route Handler は「別の入口」を追加するだけで、既存の Server Component 経路を破壊・置換する必要はない。
- **問い乙（プロダクト・UX）**: 実ユーザーの検索操作（フォーム submit）そのものを route handler 経由の client fetch に倒すか、それとも SSR ページはそのまま残し route handler は「検証・DevTools 確認専用の並行経路」に留めるか → **これは私（clean_arch）のレンズの外**（JS 必須化・progressive enhancement の後退という UX トレードオフを伴う、`SD-3` 第 2 系統に相当しうる分岐）。runtime_edge の「案 2 は §4.5 の“主経路”要件を満たさない」という指摘は理解するが、それを理由に **実装が SSR フォームを client fetch へ置き換えるべきだと自動的には決まらない**。この対立は synthesizer の `open_questions` に上げることを提案する（「§4.5 の“主経路”を厳密に取るなら route handler 経由の client fetch へ UI を変更する必要があるが、これは進行中の SP-1/SP-2 の progressive enhancement 方針と衝突しうる」という 1 文で）。

### `CachingRepositoryQuery` 案は生き残るか → **生き残る、かつ route handler 新設はこの案の価値を上げる**
`page.tsx` と `app/api/search/route.ts` の **両方** が同じ `src/composition/container.ts` の関数（`searchRepositoriesUseCase()`）を呼ぶだけで、どちらの呼び出し元もキャッシュの存在を意識しない。もし争点 C で「ユースケース引数注入案」を採っていたら、2 つの呼び出し元（page.tsx 用と route handler 用）それぞれで `CachePort` を組み立てて渡す配線が必要になり重複が増えていた。**デコレータ案は呼び出し元が増えるほど有利**（composition root の 1 関数を直すだけで両方の入口に効く）。

---

## 2. `InMemoryCache` の生存期間 — composition root をどう書くか

### 決定: モジュールスコープのシングルトンにする（毎回 `new` しない）

```ts
// src/composition/container.ts
const sharedCache: CachePort = new InMemoryCache(new SystemClock())

export function searchRepositoriesUseCase(): SearchRepositories {
  const clock = new SystemClock()
  const query = new CachingRepositoryQuery({
    inner: new GithubRepositoryQuery({ token: makeInstallationTokenProvider({ clock }) }),
    cache: sharedCache, // ← モジュールスコープの単一インスタンスを共有
    ttlSeconds: { search: TTL_SEARCH_SECONDS, detail: TTL_DETAIL_SECONDS },
  })
  return makeSearchRepositories({ repos: query })
}
```

理由: 現行設計は `searchRepositoriesUseCase()` / `getRepositoryDetailUseCase()` を **呼び出し側（`page.tsx` や新設の route handler）がリクエストのたびに呼ぶ** 構成（`GithubRepositoryQuery` も毎回 `new` している）。もし `InMemoryCache` もこの関数内で毎回 `new` すれば、生成された瞬間に空の `Map` になり、**同一 isolate 内であっても常に MISS**（キャッシュが単一リクエストのライフタイムしか持たず存在意義が消える）。モジュール読み込み時（isolate 起動時）に 1 回だけ生成し、以降の全リクエストで使い回す必要がある。

### 副作用への対処
- **isolate 間の非共有**: モジュールスコープの singleton は「1 isolate = 1 モジュールインスタンス = 1 キャッシュ」を意味する。isolate をまたいで共有されないのは singleton にしてもしなくても変わらない性質（`InMemoryCache` 自体の設計限界であり、争点 A の isolate 生存期間問題そのもの）。ここは runtime_edge / verify_test の争点 A の結論に従う。composition root 側でできるのは「**1 isolate の中では確実に使い回す**」ことだけであり、それ以上の永続化（isolate をまたぐ共有）は `InMemoryCache` を Cache API 実装へ差し替える（争点 A の次善策）でしか解決しない。
- **同一 isolate 内の同時リクエストの競合**: `Map` は同期的な読み書きなので、同じキーへの同時 `set` はデータ破損はしないが「後勝ち」になりうる（2 つの同時リクエストが同じキーで MISS → 両方 fetch → 両方 set）。SP-5 のスコープでは正確性を壊さない（無駄な二重フェッチが起きるだけ）ため、ロックは導入しない（YAGNI）。
- **テスト間の状態リーク**: `container.ts` の `sharedCache` はモジュールスコープなので、同一 vitest ワーカープロセス内で `container.ts` を import する複数テストがあると状態が漏れる。**対策**: `search-repositories.test.ts` / `get-repository-detail.test.ts` は現状どおり `container.ts` を import せず `makeSearchRepositories` に直接フェイクポートを渡す設計を維持する（無改修方針・冒頭で確認済み）ので、既存テストへの影響は無い。もし verify_test が `container.ts` 経由の結合テストを追加するなら、`container.ts` に `sharedCache` を直接 export させず（現状案でも export しない想定）、**テスト専用に `cache: CachePort` を注入できるファクトリ**（例: `createSearchRepositoriesUseCase(deps?: { cache?: CachePort })`）を用意し、テストは自前の `InMemoryCache` インスタンスを渡す形にすることを推奨する（本番コードパスはデフォルト引数で `sharedCache` を使う）。この形にすれば `vi.resetModules()` のような回避策も不要になる。

---

## 3. HIT/MISS を上位へ伝える手段（`CachePort` の面積を広げない）

### 決定: `CachingRepositoryQuery` に `onCacheStatus` コールバックを持たせる（`CachePort`・`RepositoryQueryPort` はどちらも無改修）

```ts
// src/infrastructure/platform/cached-repository-query.ts
export class CachingRepositoryQuery implements RepositoryQueryPort {
  constructor(
    private readonly deps: {
      inner: RepositoryQueryPort
      cache: CachePort
      ttlSeconds: { search: number; detail: number }
      onCacheStatus?: (status: 'HIT' | 'MISS') => void // ← 追加はここだけ
    },
  ) {}

  async search(query: SearchQuery): Promise<SearchResult> {
    const key = searchResultCacheKey(query)
    const cached = await this.deps.cache.get<SearchResult>(key)
    if (cached !== null) {
      this.deps.onCacheStatus?.('HIT')
      return cached
    }
    const result = await this.deps.inner.search(query)
    await this.deps.cache.set(key, result, this.deps.ttlSeconds.search)
    this.deps.onCacheStatus?.('MISS')
    return result
  }
  // findDetail も同様
}
```

`CachePort`（`get`/`set`/`invalidate`）にも `RepositoryQueryPort`（`search`/`findDetail` の戻り値型）にも一切手を入れない。HIT/MISS の判定ロジックはこのデコレータのローカル変数のスコープに閉じ、port の契約には現れない。

composition root 側は route handler 専用の **request スコープのファクトリ** を用意する:

```ts
// src/composition/container.ts
export function searchRepositoriesWithCacheStatus(): {
  search: SearchRepositories
  getCacheStatus: () => 'HIT' | 'MISS' | undefined
} {
  let status: 'HIT' | 'MISS' | undefined
  const clock = new SystemClock()
  const query = new CachingRepositoryQuery({
    inner: new GithubRepositoryQuery({ token: makeInstallationTokenProvider({ clock }) }),
    cache: sharedCache,
    ttlSeconds: { search: TTL_SEARCH_SECONDS, detail: TTL_DETAIL_SECONDS },
    onCacheStatus: (s) => { status = s },
  })
  return { search: makeSearchRepositories({ repos: query }), getCacheStatus: () => status }
}
```

Route Handler は関数呼び出しのたびにこのファクトリを呼ぶ（Next.js の route handler はリクエストごとに実行されるので、`status` はクロージャで request スコープに閉じ、`sharedCache`（争点 2 の singleton）だけが isolate スコープで共有される — 2 つのスコープが混ざらない）。`page.tsx` 側は HIT/MISS を必要としないので、既存の `searchRepositoriesUseCase()`（コールバック無し）をそのまま使い続けてよい。

### 却下した代替案

1. **`CachePort.get()` の戻り値を `{ value, status }` に広げる**: 却下。`NFR-17`（get/set/invalidate + TTL のみ）を明示的に破る。`InMemoryCache` の既存実装・既存の `cache.test.ts` の契約（`get<T>(key): Promise<T | null>`）も変更が要り、影響範囲が「HIT/MISS を1箇所に伝えたいだけ」という目的に対して不釣り合いに大きい。
2. **`RepositoryQueryPort` の戻り値にキャッシュメタデータを持たせる（`SearchResult` を `{ data, cacheStatus }` に拡張）**: 却下。`SearchResult` は `src/domain/model/repository.ts` のドメイン型であり、`domain-model.md` はキャッシュを「事業者固有バインディングと不可分」として `src/infrastructure/platform/` に隔離する決定を既にしている（§4・116 行目）。ドメイン型にキャッシュ概念を混ぜるとその隔離が崩れる。加えて `GithubRepositoryQuery`（キャッシュを知らない実装）も戻り値の形を合わせる必要が生じ、`ARCH-5`（GitHub 実装は `src/infrastructure/github/` に閉じる）の実装がキャッシュ層の都合に引きずられる。
3. **`AsyncLocalStorage` 等のグローバル側儀チャネル**: 却下（暫定）。Cloudflare Workers 上での `AsyncLocalStorage` の可用性・挙動は未検証（runtime_edge 領域）。明示的なコールバック注入の方が `cached-repository-query.test.ts` で `onCacheStatus` の呼び出し順序・引数を直接 assert でき、verify_test の Round 1 で示された「HIT/MISS 判定材料をこの層のテストで機械的に assert する」という要求にも最も素直に応える。暗黙のグローバル状態より明示的な DI を優先するのは既存コードベースの一貫した流儀（`ClockPort` 等）とも整合する。

---

## verify_test への補足（Round 1 の assert 2 に対する回答）

verify_test が「`CachePort.get` が呼ばれた事実と結果の由来（HIT/MISS）を呼び出し元へ返せることを assert したい」と書いていた点は、上記 `onCacheStatus` コールバックで解決する。`cached-repository-query.test.ts` では `onCacheStatus` に手書きフェイクを渡し、呼ばれた回数・引数（`'HIT'`/`'MISS'`）の順序をそのまま assert できる。

## ラウンド 3

### `lead` — 合意
<sub>2026-08-19T17:25:23+09:00</sub>

# lead: 合意（争点 A〜D の決着）

## 合意できたこと

1. **層設計（争点 C）は全員一致で決着**: `CachingRepositoryQuery`（`RepositoryQueryPort` のデコレータ）を `src/infrastructure/platform/cached-repository-query.ts` に置き、composition root で合成する。`src/usecases/*` は無改修。`CachePort` / `RepositoryQueryPort` の面積は広げず、HIT/MISS の伝達は `onCacheStatus?: (status) => void` コールバックで行う（`NFR-17` 維持）。verify_test も置き場所とテスト設計を clean_arch 案に合わせて撤回・追従した。
2. **`InMemoryCache` はモジュールスコープの singleton にする**: 現行 composition root は呼び出しのたびに依存を `new` するため、`InMemoryCache` を関数内で `new` すると **isolate 生存期間以前にリクエストごとに空 Map となり常に MISS** になる。これは争点 A の結論に関わらず必須の修正（runtime_edge が指摘、clean_arch が具体形を確定）。
3. **`page.goto()` 単体でヘッダを読む E2E は不成立**: Server Component の HTML 応答に動的ヘッダを載せる手段が現構成に存在しない（`next/headers` は read-only・`next.config.ts headers()` は静的テーブル・`defineCloudflareConfig` にレスポンスラップのフック無し・`middleware.ts` / `proxy.ts` は意図的に不在）。verify_test が round 1 案を撤回。
4. **同一ルートに `page.tsx` と `route.ts` は共存できない**: よって「Route Handler を新設すれば画面応答にヘッダが乗る」も誤り。runtime_edge が round 1 の結論を撤回。
5. **`docs/03_design/infrastructure/cloudflare-infrastructure.md` §4.2 と §4.5 は現状矛盾している**: 「HIT 時に Worker が実行されないエッジキャッシュを主役にする」（§4.2）と「アプリ側で動的にヘッダを付与する」（§4.5）は両立しない。検証可能性という受け入れ条件に直結する §4.5 を残し、§4.2 を実態に合わせて直す（`SD-4` 完了条件「見つけた矛盾を修正したか」）。

## 対立が残り、lead が裁定したこと

**争点 B（`X-Cache-Status` をどこに載せるか）**。3 案が出た。

- **案 1（UI を client fetch に作り替える）→ 却下**。SP-5 のゴールは「同じ検索で API を二度叩かない」であって「検索の実行方式を変える」ではない。SSR フォーム経路の置き換えは `AC-2`（URL 状態の再現）の作り直しを伴い、`inception-deck.md` Q4 のスコープ侵食にあたる。clean_arch が「プロダクト判断」として open_questions 送りを提案したが、**スコープ規律で機械的に却下できるため確認事項にしない**。
- **案 2（Worker ラッパー + `AsyncLocalStorage` で SSR 応答に付与）→ 第 1 候補**。ユーザーが実際に操作する画面の応答にヘッダが乗るため §4.5 を字義どおり満たす。ただし ① `wrangler.jsonc` の `main` を自前エントリへ差し替えて OpenNext 生成物を包めるか ② Workers ランタイムで `AsyncLocalStorage` が動くか、が **いずれも未検証**。
- **案 3（`app/api/search/route.ts` を観測経路にする）→ フォールバック**。実装は軽いが、画面応答にヘッダが乗らないため §4.5 の「ブラウザ DevTools で誰でも確認できる」を字義どおりには満たさず、§4.5 の文言修正が要る。

**裁定**: **案 2 を実機スパイクで検証し、成立すれば案 2、不成立なら案 3 へフォールバックする**。どちらに着地しても、キャッシュのロジック自体（「2 回目は inner を呼ばない」）は `cached-repository-query.test.ts` の結合テストで完全に閉じており、SP-5 の本質的な完了条件はヘッダ経路の成否に左右されない。スパイクは 1 回で判定し、失敗を引きずらない（`A-4` サーキットブレーカーの精神）。

## 検証の線引き（verify_test 案を採用）

| 環境 | 自動 assert | 保証しないこと |
|---|---|---|
| 結合（vitest） | HIT / MISS ロジック・TTL 経過・キー分離・404 非キャッシュ | ランタイム差異 |
| ローカル E2E（`next start` 単一プロセス） | 2 回連続検索で `MISS` → `HIT` に変わること | isolate リサイクルの影響（原理的に再現不能） |
| プレビュー（Workers） | 手動 `curl` を短い間隔で 2 回 | 間隔が空くと isolate 破棄で `MISS` になりうる（実装不具合ではない旨を PR に明記） |

`user-story-map.md` §5.3 の SP-5 操作レビュー手順に「短い間隔で 2 回」の 1 行を追記する。

### `lead` — 判定
<sub>2026-08-19T17:26:05+09:00</sub>

{
  "decisions": [
    {
      "issue": "A: キャッシュの主役をどこに置くか",
      "design": "アプリ内 CachePort（InMemoryCache）を主役にし、composition root のモジュールスコープで 1 インスタンスだけ生成して全リクエストで共有する。Cache-Control ヘッダは付与してよいが『エッジが Worker をバイパスする』効果には依存しない。isolate をまたぐ永続性は本スプリントでは追わない（Cache API 能動利用は将来の格上げ候補として記録するに留める）。",
      "artifacts": [
        "src/composition/container.ts（改修・sharedCache をモジュールスコープに）",
        "docs/03_design/infrastructure/cloudflare-infrastructure.md §4.2（改修・L2 の主役の記述を実態に合わせる）"
      ],
      "rejected": "HTTP Cache-Control + Workers Caching を主役にする案。HIT 時に Worker が実行されず X-Cache-Status を動的付与できないため §4.5 と両立しない。use cache / cacheLife も OpenNext 上で isolate 内メモリへ退化しうる（R-7 未検証）ため主役にしない。"
    },
    {
      "issue": "B: X-Cache-Status をどう付与するか",
      "design": "第 1 候補: wrangler の main を自前エントリ（src/infrastructure/platform/worker-entry.ts）に差し替え、OpenNext 生成物の fetch を呼んだ結果を包んでヘッダを付与する。HIT/MISS の受け渡しは node:async_hooks の AsyncLocalStorage（nodejs_compat 有効済み）。実機スパイクで成立を確認し、不成立ならフォールバックとして app/api/search/route.ts を観測経路として新設し、§4.5 の主経路の記述をそちらへ修正する。スパイクは 1 回で判定する。",
      "artifacts": [
        "src/infrastructure/platform/worker-entry.ts（新規・第 1 候補が成立した場合）",
        "wrangler.jsonc（改修・main の差し替え）",
        "app/api/search/route.ts（新規・フォールバック時）",
        "docs/03_design/infrastructure/cloudflare-infrastructure.md §4.5（フォールバック時のみ改修）"
      ],
      "rejected": "UI の検索実行を client fetch へ作り替える案。SP-5 のゴール外でありスコープ侵食（AC-2 の URL 状態再現の作り直しを伴う）。同一ルートに page.tsx と route.ts を共存させる案は Next.js の制約で不成立。next.config.ts headers() は静的テーブルのため動的値を書けず不成立。"
    },
    {
      "issue": "C: キャッシュ参照をどの層に差し込むか",
      "design": "CachingRepositoryQuery（RepositoryQueryPort を実装するデコレータ）を新設し composition root で合成する。CachePort と RepositoryQueryPort は無改修。HIT/MISS の伝達は onCacheStatus コールバック（デコレータのコンストラクタ引数）で行い、リクエストスコープのクロージャで受ける。404（null）はキャッシュしない。invalidate は本スプリントで呼び出し箇所を作らない。",
      "artifacts": [
        "src/infrastructure/platform/cached-repository-query.ts（新規）",
        "src/infrastructure/platform/cached-repository-query.test.ts（新規・6 ケース）",
        "src/composition/container.ts（改修）"
      ],
      "rejected": "ユースケース引数注入案（呼び出し元が増えるたびに配線が重複する）。CachePort.get の戻り値を { value, status } に広げる案（NFR-17 のポート面積を破る）。SearchResult にキャッシュメタデータを持たせる案（ドメイン型にインフラ概念が漏れる）。"
    },
    {
      "issue": "D: TTL 暫定値と再決定条件",
      "design": "検索結果 60 秒 / 詳細 300 秒を暫定値として composition root の名前付き定数（TTL_SEARCH_SECONDS / TTL_DETAIL_SECONDS）に置く。根拠（検索は鮮度要求が高く、詳細は変化が緩い）と再決定条件（R-5 のレート枠逆算が確定したら見直す）をコード内コメントと ADR に明記する。TTL はテスト安定性に影響しない（結合テストはフェイク時計、E2E は連続実行のため）。",
      "artifacts": [
        "src/composition/container.ts（新規定数）",
        "docs/03_design/architecture/adr/（新規 ADR・Cache Port が YAGNI の意図的例外である理由と TTL 暫定値の根拠）"
      ],
      "rejected": "TTL を環境変数化する案（R-5 未確定の段階で運用面を増やす YAGNI）。検索と詳細で同一 TTL にする案（NFR-5 が別値を要求）。"
    }
  ],
  "tasks": [
    { "id": "T-1", "title": "CachingRepositoryQuery と結合テスト 6 ケースを TDD で実装する", "actor": "claude", "depends_on": [], "sp": "sp:3" },
    { "id": "T-2", "title": "composition root を sharedCache シングルトン + TTL 定数 + onCacheStatus ファクトリへ改修する", "actor": "claude", "depends_on": ["T-1"], "sp": "sp:2" },
    { "id": "T-3", "title": "X-Cache-Status の付与経路を実機スパイクで判定し、成立側を実装する", "actor": "claude", "depends_on": ["T-2"], "sp": "sp:3" },
    { "id": "T-4", "title": "E2E（2 回検索で MISS→HIT）と操作レビュー手順の 1 行追記を反映する", "actor": "claude", "depends_on": ["T-3"], "sp": "sp:2" },
    { "id": "T-5", "title": "cloudflare-infrastructure.md §4.2 の矛盾を解消し、ADR を起こす", "actor": "claude", "depends_on": ["T-3"], "sp": "sp:1" }
  ],
  "critical": [
    "InMemoryCache を composition root の関数内で new すると isolate 生存期間以前に常に MISS となる。モジュールスコープ singleton 化は必須（この 1 点を落とすと SP-5 は成立しない）。",
    "X-Cache-Status を SSR 応答へ載せる手段は現時点で未検証であり、スパイクが失敗した場合は観測経路を分ける設計変更（§4.5 の文言修正）が必要になる。"
  ],
  "open_questions": []
}
