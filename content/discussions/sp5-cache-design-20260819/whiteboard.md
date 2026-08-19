<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: SP-5 キャッシュ層の設計方針を確定する

- 議題ID: `sp5-cache-design-20260819`
- 論点: SP-5 のゴールは『同じキーワードで 2 回続けて検索したとき 2 回目は GitHub API を呼ばない』を、レスポンスヘッダ X-Cache-Status: HIT で検証できる状態にすること（user-story-map.md §5.3 SP-5 / E-3 / NFR-5 / NFR-17 / NFR-18）。既存資産: src/domain/ports/cache-port.ts に CachePort（get/set/invalidate + ttlSeconds）、src/infrastructure/platform/cache.ts に InMemoryCache（isolate 内メモリのみ・composition root 未配線）、src/infrastructure/platform/cache-key.ts に CacheKey ブランド型と searchResultCacheKey / repositoryCacheKey。データ取得は src/infrastructure/github/github-repository-query.ts（RepositoryQueryPort 実装）、ユースケースは src/usecases/search-repositories.ts / get-repository-detail.ts、画面は app/[locale]/page.tsx と app/[locale]/repos/[owner]/[repo]/page.tsx（いずれも Server Component から直接 await。route handler は存在しない。middleware.ts / proxy.ts は Next.js 16 + OpenNext Cloudflare 非両立のため意図的に不在で、next.config.ts の headers() / redirects() のみ利用可能）。設計文書の制約: cloudflare-infrastructure.md §4.2 は L1=React cache / L2=HTTP Cache-Control + Workers Caching（MVP の主役）/ L3=外部ストア未採用、Next.js の use cache は OpenNext 上で isolate 内メモリに退化しうるため当てにしない、と定めている。§4.5 は X-Cache-Status をアプリ側で付与し、X-GitHub-RateLimit-Remaining が変わらないことで裏を取る、と定めている。architecture-rules の ARCH-2（ユースケースはポートを引数で受け取る）/ ARCH-3（依存は内向き・app と src/ui から src/infrastructure を直 import しない、src/composition 経由）/ ARCH-4（事業者固有バインディングは src/infrastructure/platform の中だけ）は不変。D-5（DB を持たない）により永続キャッシュストアは採らない。R-7（use cache の実挙動未検証）と R-5（TTL 値のレート枠逆算）は未決。争点は次の 4 つ: A) キャッシュの主役をアプリ内 CachePort（InMemoryCache）に置くか、HTTP Cache-Control + Workers Caching に置くか、両方をどう役割分担させるか。isolate 内メモリはリクエスト間で残る保証が薄く、エッジキャッシュは HIT 時にアプリコードが動かないという相反する弱点がある。B) X-Cache-Status: HIT / MISS を実際にどう付与するか（Server Component からレスポンスヘッダを制御する手段が現状無いことをどう解決するか。route handler を新設するのか、next.config.ts の headers() で足りるのか、Cloudflare Cache API を明示的に叩くのか、OpenNext の実行モデル上どれが機能するか）。C) キャッシュ参照をどの層に差し込むか（ユースケースが CachePort を受け取る案 vs GithubRepositoryQuery をキャッシュ付きデコレータで包む案 vs composition root で合成する案）。ARCH-2 / ARCH-3 と、SP-4 で整備済みのテスト構成（vitest 併置 + e2e/ の Playwright + e2e/stub/server.mjs のスタブ GitHub API）との相性で判断する。D) TTL 暫定値をいくつにし、その根拠と再決定条件（R-5 確定後）をどこに書くか。検索結果と詳細で別値にする要件（NFR-5）を満たすこと。
- 参加者: `runtime_edge`, `clean_arch`, `verify_test`
- 投稿数: 0
- 更新: 2026-08-19T17:16:44+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

_（まだ投稿がありません）_
