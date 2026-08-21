<!--entry
author: rate_cache
round: 2
kind: rebuttal
ts: 2026-08-21T10:03:38+09:00
-->

## rate_cache round2: rebuttal / concession

### `domain_arch` への応答（核心の衝突点）— **一部 concession**

`domain_arch` 案（usecase の分岐が `deps.repos.search(query)` を `page=1..maxPage` でループ呼び出し）を前提にすると、**私の争点2「`search-raw` 新名前空間」提案は不要**と判断を改める（concession）。

理由: usecase から呼ぶ `deps.repos` は composition root で合成された `CachingRepositoryQuery`（`RepositoryQueryPort` の decorator）そのもの。ループの各呼び出しが `perPage=100`（GitHub 上限固定・生の raw fetch チャンクサイズ）・`page=N` の **raw 用 `SearchQuery`** を作って `deps.repos.search()` に渡すなら、既存 `searchResultCacheKey`（`keyword:page:sort:per_page`）が **そのまま raw ページ単位のキー** として機能する。新しいキー生成関数もキャッシュスキーマ変更も不要。

これにより round1 で指摘した「single-flight が全件取得に効かない」問題も**解消**する: 既存 `CachingRepositoryQuery.readThrough` の `inFlightSearch` マップは呼び出しごとのキー単位で合流するため、同一キーワード・同一 raw ページへの並行リクエストはページ単位で自動的に single-flight される。round1 の「専用 in-flight マップが要る」という主張は**撤回**する。

**ただし 1 点、実装で崩れうる前提として明示しておく**: ループ内で使う `sort` は **`'gemIndex'` という文字列そのものであってはならない**（`scope_test` 争点4-D と同じ指摘）。`GithubRepositoryQuery.search()` は `sort !== 'relevance'` なら `url.searchParams.set('sort', query.sort)` で **そのまま GitHub API に渡す**（`github-repository-query.ts:55-58`）ため、`sort='gemIndex'` を渡すと GitHub API が理解できないパラメータを送ることになる（422 のリスク）。raw 取得ループは `sort: 'relevance'`（GitHub 既定・`ux_paging` 争点5の relevance 保持方針とも整合）を使うべきで、**表側の `query.sort='gemIndex'` とは別の内部 `SearchQuery` を組み立てる**実装が必須。ここが崩れると「新しいキー空間が要る/要らない」の議論全体が変わるので、実装 Issue に明記すべき注意点として `domain_arch` 案に条件付きで同意する。

**副次効果（好ましい）**: raw 取得ページが `sort=relevance, per_page=100` の既存キー体系に乗るため、**表示 perPage=100 で通常検索（relevance）した利用者と gemIndex 検索の raw fetch がキャッシュを共有**できる（偶然のヒット率向上）。round1 の「keyword 単位の巨大 blob」案より部分再利用性が高く、こちらのほうが優れている。

**それでも変わらない点（メモリ懸念は継続）**: page 単位に分割しても、1 検索あたり最大 1,000 件分のデータ総量は変わらない（10 エントリに分散するだけ）。`InMemoryCache` に上限・LRU が無い点（round1 指摘）は `domain_arch` 案でも未解決。実装 Issue に持ち越すべき。

---

### `ux_paging` への応答

争点3 前提条件①「`totalCount` は GitHub の生値を保つ」は私のキャッシュ設計と衝突しない。`totalCount` はキー生成にもキャッシュ判定にも使わない値（`SearchResult` のペイロード内の一データ）なので、raw ページ単位キャッシュ（上記 concession 後の設計）でも usecase が 1 ページ目の `totalCount` をそのまま最終結果へ転記すれば足りる。10 ページの応答間で `total_count` が食い違う可能性（TTL 60 秒内でも GitHub 側の状態変化はありうる）は既存の「キャッシュミス最悪ケースで見積もる」方針の範囲内で無視してよいレベルとみる（`repository-publication-review.md` §7.2 も同じ割り切り）。

---

### `scope_test` への応答

**1. `enforceSearchRateLimit` の修正は `SP-16a` に入れるべき（`SP-16b` へ回すと本番でレート枠を焼く）。**

`SP-16a` の定義（「全ページ取得（打ち切り条件込み）+ 全件キャッシュ + join usecase + gemIndex ソートオプション追加」）は、**まさに multi-page fetch が有効になる境界そのもの**。`enforceSearchRateLimit`（`rate-limit.ts:20`）が `sort` を見ずに「1 リクエスト = 1 消費」で回している限り、`SP-16a` が単独でマージされた瞬間から「1 クライアントが 60 秒間に 60 回 gemIndex 検索 → upstream 最大 600 call/分」の穴が本番に露出する。`SP-16b`（カード表示リッチ化・表示専用の差分）にはこの穴を防ぐ理由が一切無いので、切り分けの基準（表示 vs 挙動）にも合致する形で **`SP-16a` 必須項目**として明記してほしい。

**2. `scope_test` 争点5 の「同時 3 人で枯渇」と私の「2.3 名で頭打ち」は別の 2 つのリスクで、両方とも `SP-16a` の対象。**

`scope_test` の 3 人瞬間バーストの見積り（30 req/分 ÷ 10 call ≒ 3 検索が限界）と、私の継続的同時実利用者モデル（30 ÷ (1.3 検索/分/人 × 10) ≒ 2.3 名）は**近い数値で相互に補強**している（正常利用・複数の異なる利用者による共有枠の枯渇）。これは「D-30 の選択が生む既知の代償」であり、`enforceSearchRateLimit` を直しても消えない（アプリ全体の共有 30 req/分という総量自体は変わらないため）。

一方、私が争点6で指摘したのは**これとは別の穴**: 単一クライアント（1 IP）が悪意・誤操作で連射した場合に、現行の per-IP 自己スロット（60 req/60秒）が **一切歯止めにならない**という構造的欠落。前者（総量の自然な枯渇）は PR 本文への注記で運用回避できる性質のものだが、後者（単一クライアントの連射）は**注記では防げない**（利用者は PR 本文を読まない）。よって `SP-16a` には最低限、`enforceSearchRateLimit` に `sort` を渡し gemIndex 用の別スロット（`wrangler.jsonc` に低い上限のエントリを追加）を持たせる変更を含めるべき、という結論は変えない。

**3. 1,000 件取得のプレビュー環境での現実性**: `scope_test` の見積り（レイテンシ 2〜5 秒・直列実行必須）は妥当と見る。私のレンズからの追加情報は「メカニズムとしては動くが、レート枠は共有総量なので**操作レビュー中に他セッションの試行と鉢合わせると 429 になりうる**」点で、これは `scope_test` 自身が争点5で既に書いている残余リスクと同じ結論。付け加えるとすれば、**`SP-16a` に `enforceSearchRateLimit` の gemIndex 別スロット修正が入っていれば**、少なくとも「PR レビュー中の 1 人の連続操作」が自分自身の枠を食い潰して再現不能になるケースは緩和できる（別スロットの上限を操作レビューの往復回数に見合う値にしておけば）。
