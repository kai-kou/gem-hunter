<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: SP-5 キャッシュ層の設計方針を確定する

- 議題ID: `sp5-cache-design-20260819`
- 論点: SP-5 のゴールは『同じキーワードで 2 回続けて検索したとき 2 回目は GitHub API を呼ばない』を、レスポンスヘッダ X-Cache-Status: HIT で検証できる状態にすること（user-story-map.md §5.3 SP-5 / E-3 / NFR-5 / NFR-17 / NFR-18）。既存資産: src/domain/ports/cache-port.ts に CachePort（get/set/invalidate + ttlSeconds）、src/infrastructure/platform/cache.ts に InMemoryCache（isolate 内メモリのみ・composition root 未配線）、src/infrastructure/platform/cache-key.ts に CacheKey ブランド型と searchResultCacheKey / repositoryCacheKey。データ取得は src/infrastructure/github/github-repository-query.ts（RepositoryQueryPort 実装）、ユースケースは src/usecases/search-repositories.ts / get-repository-detail.ts、画面は app/[locale]/page.tsx と app/[locale]/repos/[owner]/[repo]/page.tsx（いずれも Server Component から直接 await。route handler は存在しない。middleware.ts / proxy.ts は Next.js 16 + OpenNext Cloudflare 非両立のため意図的に不在で、next.config.ts の headers() / redirects() のみ利用可能）。設計文書の制約: cloudflare-infrastructure.md §4.2 は L1=React cache / L2=HTTP Cache-Control + Workers Caching（MVP の主役）/ L3=外部ストア未採用、Next.js の use cache は OpenNext 上で isolate 内メモリに退化しうるため当てにしない、と定めている。§4.5 は X-Cache-Status をアプリ側で付与し、X-GitHub-RateLimit-Remaining が変わらないことで裏を取る、と定めている。architecture-rules の ARCH-2（ユースケースはポートを引数で受け取る）/ ARCH-3（依存は内向き・app と src/ui から src/infrastructure を直 import しない、src/composition 経由）/ ARCH-4（事業者固有バインディングは src/infrastructure/platform の中だけ）は不変。D-5（DB を持たない）により永続キャッシュストアは採らない。R-7（use cache の実挙動未検証）と R-5（TTL 値のレート枠逆算）は未決。争点は次の 4 つ: A) キャッシュの主役をアプリ内 CachePort（InMemoryCache）に置くか、HTTP Cache-Control + Workers Caching に置くか、両方をどう役割分担させるか。isolate 内メモリはリクエスト間で残る保証が薄く、エッジキャッシュは HIT 時にアプリコードが動かないという相反する弱点がある。B) X-Cache-Status: HIT / MISS を実際にどう付与するか（Server Component からレスポンスヘッダを制御する手段が現状無いことをどう解決するか。route handler を新設するのか、next.config.ts の headers() で足りるのか、Cloudflare Cache API を明示的に叩くのか、OpenNext の実行モデル上どれが機能するか）。C) キャッシュ参照をどの層に差し込むか（ユースケースが CachePort を受け取る案 vs GithubRepositoryQuery をキャッシュ付きデコレータで包む案 vs composition root で合成する案）。ARCH-2 / ARCH-3 と、SP-4 で整備済みのテスト構成（vitest 併置 + e2e/ の Playwright + e2e/stub/server.mjs のスタブ GitHub API）との相性で判断する。D) TTL 暫定値をいくつにし、その根拠と再決定条件（R-5 確定後）をどこに書くか。検索結果と詳細で別値にする要件（NFR-5）を満たすこと。
- 参加者: `runtime_edge`, `clean_arch`, `verify_test`
- 投稿数: 3
- 更新: 2026-08-19T17:20:02+09:00

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
- **B（X-Cache-Status ヘッダの付与手段）**: `CachingRepositoryQuery` が HIT/MISS を判定した「結果」をどう Server Component の外（レスポンスヘッダ）まで運ぶかは、今回の設計だけでは閉じない。`search(query)` の戻り値型を広げてメタ情報（`cacheStatus: 'HIT' | 'MISS'`）を持たせるか、別の観測経路（例: `AsyncLocalStorage` 的な仕組み）を使うかは B の主担当の判断に委ねるが、**戻り値の型を広げる案を取るなら `RepositoryQueryPort` のシグネチャ変更が必要**になり `ARCH-2` 上は usecases 側も戻り値を素通しするだけで済む（usecase 内ロジックの追加は不要）ため大きな障害にはならない
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
- `src/composition/container.ts` に `InMemoryCache`（または C の結論次第でデコレータ）を配線したら、`container.test.ts` は現状存在しない。新規に「同一プロセス内で `searchRepositoriesUseCase()` を 2 回呼んでも内側の HTTP フェッチが 1 回」まで確認したい場合は **MSW でネットワーク層をカウント**するのが妥当（ここは ACL 境界を跨ぐので testing-strategy.md §4 の「MSW は ACL のテストに限る」の例外に当たらない点に注意が必要 — 厳密には ACL 単体ではなく composition root 経由の結合テストになるため、**Red 段階でこのテストを書くかどうかは要判断**。個人的な意見: 2 の層でロジックは閉じているので、composition root レベルの結合テストは「配線ミスの検知」だけが目的になり、MSW を使うより **スタブサーバー（`e2e/stub/server.mjs` は E2E 専用なので流用しない）ではなく `undici` の `MockAgent` 等を使う結合テストを 1 本足す価値はあるが必須ではない**。§6 の AC 対応表にも composition root 単体の行は無いので、**この結合テストは Nice-to-have・E2E で代替可能なら省略してよい**と考える。

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
- 争点 B が「Cloudflare Cache API を明示的に叩く」案になった場合、ローカル `next start`（Node ランタイム）では Cloudflare の `caches` グローバルが存在しない可能性があり、**ローカル webServer での E2E がそもそもその経路を通らない**リスクがある。この場合ローカル E2E は InMemoryCache 経路のみを検証し、Workers Cache API 経路は別途プレビュー環境での手動確認 or `@cloudflare/vitest-pool-workers` 導入まで検証が閉じない。この乖離は runtime_edge の結論待ちで、**Red を書く前に B の結論を確定させる必要がある**（B → 私のテスト設計の入力）。

#### 5. スタブへのリクエスト回数を数える具体案（もう1経路、E2E レベルで裏取り）
`e2e/stub/server.mjs` はグローバル変数でリクエストカウンタを持たない薄い実装。**改修案**: `/__stats` のようなデバッグ専用ルートを足し、`GET /__stats` で `{ searchRequestCount: number }` を返す（テスト専用エンドポイントなので本番コードには影響しない・スタブファイル内で閉じる）。または `X-GitHub-RateLimit-Remaining`（インフラ設計書 §4.5 の「副」経路）をそのまま使い、スタブが固定値でなく **リクエストのたびに `remaining` をデクリメントする** ようにすれば、2 回目のページ応答でその値が変わらないことをアプリ側ヘッダ経由で assert できる（新規のスタブエンドポイントを増やさずに済む）。**後者を推奨**（インフラ設計書 §4.5 の「副」の裏取り経路そのものであり、二重に確認できる）。改修対象: `e2e/stub/server.mjs`（`rateLimitBody` とは別に、`x-ratelimit-remaining` を通常応答にも付与しデクリメントするグローバルカウンタを追加）。ただし `fullyParallel: false / workers: 1` なのでテスト間の順序に依存する副作用が生まれる点に注意（他の spec ファイルが先に同じスタブへ複数回リクエストしているとカウンタがずれる）。**そのため主 assert は `X-Cache-Status` に置き、`X-GitHub-RateLimit-Remaining` は補助（裏取り）に留める**べき（インフラ設計書の位置づけと一致）。

### isolate メモリ依存への懸念（E-27相当・私のレンズ）
- ローカル `next start`（`playwright.config.ts` の `webServer`）は **単一 Node プロセスが全テストで使い回される**ため、`InMemoryCache` がプロセス内シングルトンとして配線されていれば E2E は安定して通る。**しかし実際の Cloudflare Workers 本番/プレビュー環境では isolate が頻繁にリサイクルされうる**ため、ローカル E2E が緑でも本番で HIT 率が上がらない可能性がある。これは runtime_edge の主担当領域だが、**検証可能性の観点からは「ローカル E2E だけでは SP-5 の完了を証明しきれない」**ことを明記しておく。対策案: プレビュー環境で `curl -I` を 2 回叩いて `X-Cache-Status` を目視確認する手順を PR 本文に残す（自動化はできないため、`testing-strategy.md` の「プレビュー URL への E2E 実行は現状スタブ到達不可」制約とも整合し、手動確認をセルフレビューのチェックリストに落とす形が現実的）。

### 争点 D への短い意見
TTL 暫定値は「E2E 実行時間より十分大きく（数十秒〜数分オーダー）」だけがテスト安定性からの制約。検索結果と詳細で別値にする場合も、フェイク時計を使うユニット/結合テストは TTL の実値に依存しないので、値そのものの決定はテストを Block しない。R-5 未決を理由にテストを止める必要はない。

### まとめ（結論）
1. ロジックの「2 回目は外部を呼んでいない」は **ユニット/結合層（フェイク `RepositoryQueryPort` の呼び出し回数カウント）で完全に機械的に閉じる**。ここが最も安定した Red の起点。
2. E2E は `X-Cache-Status` ヘッダを **`page.goto()` の戻り値から直接読む**方式を推奨（client action 経由だとヘッダが取れない可能性があり未検証）。
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
3. ~~Cloudflare Cache API (`caches.default`) を明示的に呼んで HIT/MISS をアプリが判定する~~ — これは「HTTP キャッシュを叩くかどうか」の実装選択（争点 A）であって、争点 B（ヘッダをどう出すか）の答えにはならない。Cache API を使っても、判定結果を **レスポンスに書き込む手段は結局 1 か 2 と同じ制約**を受ける。

**推奨**: 案 1（Route Handler 新設）。理由: cloudflare-infrastructure.md §4.5 が「主経路」と明記した検証要件（ブラウザ DevTools・E2E からの assert）を満たせるのはこれだけ。ARCH-3/ARCH-4 的にも Route Handler は `app/` 配下の通常のエントリポイントであり Cloudflare 固有バインディングを持ち込む場所ではない（既存の `src/infrastructure/platform/` 経由でユースケースを呼べば矛盾しない）。**ただし UI 変更の範囲は clean_arch / verify_test と要すり合わせ**（フォーム送信を fetch 経由にするか、page.tsx から内部的に同一 Worker 内で Route Handler を fetch するか）。後者（page.tsx が自分の Route Handler を `fetch()` する）なら UI 変更なしで実現できるが、**Worker 内から自分自身への fetch はループバック不可**（Cloudflare Workers は self-fetch に外部ネットワークを使わず `env.ASSETS`/Service Binding が必要で、同一 Worker への HTTP self-call は追加設定なしには繋がらない可能性が高い・未検証）。ここは verify_test と要検証。

### 争点 A: CachePort（isolate メモリ）vs HTTP Cache-Control + Workers Caching

**確認した事実**:
- `src/infrastructure/platform/cache.ts` の `InMemoryCache` は isolate 内 `Map`。コメントに明記の通り「isolate 内メモリのみに保持する土台実装」で composition root 未配線（YAGNI・#67）。
- cloudflare-infrastructure.md §4.2 は L2（HTTP Cache-Control + Workers Caching）を **MVP の主役**と明記し、L1（React cache）は同一レンダー内メモ化のみ、L3 は不採用。§4.3 は Cache Port の実体を「キャッシュキー生成 + `Cache-Control` 付与の薄いラッパー」と定義している。
- しかし **Cloudflare の「Workers Caching」（Cache-Control ベースでエッジが自動キャッシュする挙動）は、HIT 時に Worker を経由させない**（= アプリコードが実行されない）。この特性は brief にも明記されている既知の前提で、私も実行モデルとして確認できる（Cloudflare のキャッシュ層はオリジン=Worker の手前で応答するため、HIT ならリクエストは Worker まで届かない）。これが争点 B の根本原因でもある: **HIT のとき Worker が動かないなら、そのレスポンスにアプリが動的ヘッダを乗せることは原理的に不可能**（キャッシュに格納された時点=MISS 時に焼き込まれたヘッダしか返せない）。1 回目 MISS で `X-Cache-Status: MISS` を焼き込んで保存すると、2 回目の HIT でも **同じ `MISS` ヘッダがそのまま返る**（矛盾）。
- 一方、`InMemoryCache`（isolate 内メモリ）方式なら Worker は毎回実行されるので、`get()` の結果に応じて **その場で** `X-Cache-Status: HIT/MISS` を決定でき、ヘッダを動的に出せる。ただし isolate の生存期間は保証薄（Cloudflare は低頻度リクエストで isolate を数十秒〜数分で破棄しうる。公式に確定値の記載なし=未検証）。

**結論**: 争点 A と B は独立ではなく **強く連動する**。「HTTP Cache-Control + Workers Caching を主役にする」という §4.2 の決定と、「X-Cache-Status をアプリ側で付与する」という §4.5 の決定は、**両立しない**（HIT 時に Worker が動かない前提と、Worker がヘッダを動的に付与する前提が矛盾）。SP-5 の完了条件（X-Cache-Status で検証できること）を優先するなら、**争点 A は「アプリ内 CachePort（isolate メモリ、または Cache API を明示 fetch/put する能動利用）を主役にする」方向に倒すべき**であり、受動的な Cache-Control 依存の Workers Caching は SP-5 の検証要件と両立しない。

Cache API（`caches.default`）の明示利用（`await caches.default.match(request)` → なければ GitHub 呼び出し → `await caches.default.put(request, response.clone())`）という第三の道もある。これは HTTP Cache-Control でエッジに委ねる「受動キャッシュ」と違い、**Worker コード内で明示的に呼ぶ「能動キャッシュ」**なので Worker は常に実行され、ヘッダを動的に付与できる。isolate メモリより永続性が高い（コロケーション単位で共有）が、**ローカル `wrangler dev` / Miniflare でどこまで忠実に再現されるかは未検証**（verify_test 領域と重複するため詳細判断は譲る）。ARCH-4 的には Cache API 利用は Cloudflare 固有 API なので `src/infrastructure/platform/cache.ts` の中に閉じ込める必要があり、これは現状の配置と一致する。

**推奨（暫定）**: 争点 A は「CachePort の実装を isolate メモリ（現状の `InMemoryCache`）のまま composition root に配線し主役にする。Cache-Control ヘッダは付与してもよいが “検証の主役” にはしない」で決着させるのが最も安全（実装済み資産を活かせる・isolate 生存の弱さは SP-5 の TTL 短さで許容範囲・§4.2 の「L2 主役」という記述は本 SP-5 の検証要件と矛盾するため修正が要る=ADR/文書修正が発生する）。Cache API 明示利用への格上げは、isolate メモリの実測 HIT 率が SP-5 の操作レビューで不十分と分かった場合の次善策として残す。

### 争点 C・D への短い意見
- C: ユースケースが CachePort を引数で受け取る案（ARCH-2 に最も素直）。デコレータ案は `GithubRepositoryQuery` の呼び出し元を増やすたびに配線が要り composition root が肥大化しやすい。
- D: TTL は未検証領域（レート枠逆算は R-5 未決）。実行モデル上、TTL が短すぎると isolate 再生成で実質キャッシュが効かない検証結果になり E2E が不安定化するリスクがある点だけ指摘しておく（具体値は verify_test / clean_arch に譲る）。

### 未検証と明記する点
- isolate の実際の生存時間（低頻度アクセス時に何秒〜何分で破棄されるか）: 公式ドキュメント未確認、実測もしていない。
- Worker 内から自 Worker への self-fetch（Route Handler 案の実現可否）: 未検証。Service Binding や `env.ASSETS` の使用要否を含め要確認。
- Cloudflare Cache API (`caches.default`) が `wrangler dev` / Miniflare ローカルでどこまで実挙動を再現するか: 未検証（verify_test 領域）。
- Cloudflare エッジが実際に Worker 発行の `Cache-Control` ヘッダだけで自動キャッシュするか（Cache Rules 等の追加設定が要るのでは）: wrangler.jsonc に該当設定が見当たらず、cloudflare-infrastructure.md 他セクションも未確認のため断定を避ける。
