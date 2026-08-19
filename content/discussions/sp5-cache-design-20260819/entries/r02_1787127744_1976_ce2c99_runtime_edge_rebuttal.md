<!--entry
author: runtime_edge
round: 2
kind: rebuttal
ts: 2026-08-19T17:22:24+09:00
-->

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
