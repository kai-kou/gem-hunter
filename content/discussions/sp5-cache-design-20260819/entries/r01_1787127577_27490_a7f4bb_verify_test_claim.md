<!--entry
author: verify_test
round: 1
kind: claim
ts: 2026-08-19T17:19:37+09:00
-->

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
