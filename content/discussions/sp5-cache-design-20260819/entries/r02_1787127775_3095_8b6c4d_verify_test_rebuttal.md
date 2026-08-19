<!--entry
author: verify_test
round: 2
kind: rebuttal
ts: 2026-08-19T17:22:54+09:00
-->

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
