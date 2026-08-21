<!--entry
author: scope_test
round: 2
kind: rebuttal
ts: 2026-08-21T10:04:39+09:00
-->

# scope_test（レンズ: スコープとテスト戦略）round2 rebuttal

## 0. 結論から: round1 の判定は維持する。ただし SP-16a/SP-16b の境界線は修正する

**3 レンズ案を合算しても `sp:8`（グレーゾーン・超過リスク高）の判定は変わらない。** ただし内訳が round1 時点の想定から変わった。要点:

- `domain_arch` の「既存 `RepositoryQueryPort.search()` をユースケース内で 10 回ループする」設計は、**キャッシュ・single-flight を無改修で流用できる** ため、`rate_cache` が提案した新キャッシュ名前空間（`search-raw:`）+ 専用 in-flight マップの新設分がまるごと不要になる。これは大きな削減。
- 一方で `rate_cache` の `enforceSearchRateLimit` 欠落指摘は **別 Issue に逃がせない**（後述 §2）。小さいが確実な追加。
- `ux_paging` の反論（バッジに `dependentCount` も要る）は **認める**。round1 で「カード表示は最小限（gemIndex 数値のみ）を `SP-16a` に残し、リッチ化は `SP-16b`」としていたが、これは操作レビュー手順 3 の文言（「被依存数と star の乖離がわかる」）を満たさない。ただし `daily-digest.tsx` の既存パターン流用のため、想定していたほど高くつかない。

差し引きすると **合計実装量は round1 の見積もりからほぼ横ばい**（キャッシュ新設の削減 ≒ バッジ前倒し + レート制限修正の追加）。判定は維持: 「収まるが超過リスクの高いグレーゾーン。縦切り分割案は用意しておく」。

---

## 1. `domain_arch` vs `rate_cache`: キャッシュ層の衝突は `domain_arch` 案の方が実装量が小さい（第三者判定）

`container.ts:78-79` を確認した:

```ts
export function searchRepositoriesUseCase(accessToken?: string | null): SearchRepositories {
  return makeSearchRepositories({ repos: makeCachingRepositoryQuery({ accessToken }) })
}
```

**`makeSearchRepositories` に渡る `deps.repos` は既に `CachingRepositoryQuery`（キャッシュ + single-flight 込み）である。** つまり `domain_arch` が言う「ユースケース内で `deps.repos.search()` を `page=1..10` 分ループする」を素直に実装すると、**10 回の呼び出しそれぞれが既存の `search:v2:kw:page=N:sort=X:per_page=100` キーで自動的にキャッシュされ、既存の `inFlightSearch`（per-page 単位）で single-flight もタダで効く**。新しいキャッシュキー関数も、新しい in-flight マップも、`cached-repository-query.ts` の改修も **一切不要**。

これは `rate_cache` が指摘した「争点2: `search-raw` 名前空間 + 専用 in-flight マップが要る」を丸ごと代替する。しかも副作用として `rate_cache` が争点6の補足で挙げた懸念（「`search-raw` 名前空間には既存 single-flight マップが効かない、ページ番号違いで合流しない」）も **最初から発生しない**: 内部ループが常に固定の内部ページ集合（`per_page=100 固定・page=1..10`）を叩く設計にすれば、利用者が選んだ表示 `page`/`perPage`（20/50/100 の任意組み合わせ）に関わらず、同じキーワードの gemIndex 検索は常に同じ 10 個の内部キャッシュキーへ収束する。表示ページが違っても single-flight は合流する。

**第三者としての判定: `domain_arch` 案（既存ポートをループで再利用）を採用すべき。** 理由は 3 つ:
1. 新規コード量が明確に少ない（`cache-key.ts` / `cached-repository-query.ts` 無改修）
2. `rate_cache` 案より **single-flight の合流粒度が広い**（`rate_cache` 案はキーワード単位の新規 in-flight マップを別途正しく実装する必要があるが、既存流用なら実装ミスの余地自体が無い）
3. `cache-key.ts` の docstring が「生成関数以外でキーを組み立てない」と明記しており、名前空間を増やすたびにこの docstring の対象を広げる設計変更は最小に留めたい（`domain-model.md` §4 の精神）

**ただし懸念点を 1 つ指摘する**: `domain_arch` の実装例コード（round1 コードスニペット）は内部ループで `deps.repos.search(query)` を呼ぶ際に **`query.sort` をそのまま渡す設計に読める**。`query.sort === 'gemIndex'` のまま `GithubRepositoryQuery.search()` に渡ると、`github-repository-query.ts` の `if (query.sort !== 'relevance') { url.searchParams.set('sort', query.sort) ... }` 分岐に引っかかり、**`sort=gemIndex` という無効な値が実際に GitHub API へ送られ 422 相当のエラーになる**（`domain_arch` 自身が「`GithubRepositoryQuery` は無改修」と明言しているにもかかわらず、これは無改修のままでは壊れる）。内部ループ用の `SearchQuery` は `sort` を `'relevance'`（または固定の安全な値）に上書きして構築する必要がある——実装手段レベルの修正で規模には影響しないが、**単体テストで「内部フェッチが `sort=gemIndex` を GitHub 側へ漏らさないこと」を Red→Green で明示的に確認する項目として `§2 の内側 2.3` に追加する**。

**TTL の一貫性について（`rate_cache` 争点2への補足）**: `rate_cache` は「10 call を 1 エントリに集約しないと、TTL 境界で個々のページが別タイミングで失効し combined 結果が不整合になる」と暗に懸念しうるが、`domain_arch` 案採用でもこの懸念は残る（10 回の `cache.get`/`cache.set` は逐次実行なので、フェッチ中に前のページの TTL（60 秒）が切れることは通常の応答時間（数秒）では起きない）。実害はほぼ無いと判断し、これを理由に `rate_cache` 案へ戻す必要はない。

---

## 2. `rate_cache` の争点6（`enforceSearchRateLimit` 欠落）: **`SP-16a` のスコープ内** と判定する（別 Issue にしない）

`CLAUDE.md` `core-principles.md` CP-1 の判定基準:

> 自分がこのタスクで変更したコードパス上の壊れ（自分の変更で落ちたテスト・自分が編集したファイルの参照先が不在・自分が追加した処理が動かない等）は 報告ではなく即修正する

`enforceSearchRateLimit` の「1 検索 = 1 upstream call」という暗黙の前提は、**`SP-16` がまさに壊す前提そのもの**（`sort=gemIndex` を追加した瞬間に 1 検索 = 最大 10 call になる）。これは「無関係な既存の壊れ」ではなく、**このスプリントの変更が直接作り出す壊れ**（sort の選択肢を増やす変更と、レート制限が sort を見ない実装が、同じ PR の中で矛盾を起こす）。放置すると本番で「1 クライアントが upstream 30 req/分の共有枠を 1 人で 20 倍消費できる」実害のある穴を新規に開けたまま出荷することになり、`project-mission.md` の運用継続性（無料枠に収まる・レート制限で破綻しない）という品質ゲートにも反する。**別 Issue へ切り出す判断は採らない。**

**ただしフルスコープの `rate_cache` 提案（新スロット名 + `wrangler.jsonc` エントリ追加 + LRU 上限設計）を全部 `SP-16a` に含める必要はない**、と切り分ける:

- **`SP-16a` に含める（必須・小規模）**: `enforceSearchRateLimit` に `sort`（または内部コスト）を渡せるようにし、`sort === 'gemIndex'` のときは **別スロット・低い上限** で消費する。`app/api/search/route.ts` / `app/[locale]/page.tsx` で `sort` を早期パースする変更、`wrangler.jsonc` へ 1 エントリ追加。いずれも変更箇所は数ファイル・数行単位で、`rate-limit.ts` の既存構造（`WorkersRateLimit.consume(key)`）を壊さない加算的変更。
- **別 Issue へ切り出す（本スプリント外）**: `InMemoryCache` の LRU 上限・メモリ使用量の全体設計。これは `SP-16` 固有の壊れではなく、`SP-5`（キャッシュ導入時）から存在する **既存の設計前提**（軽量な 1 ページ分のみを想定）に対する一般的な指摘であり、`gemIndex` 実装が引き金にはなるが「このタスクで変更したコードパス」そのものではない（境界は 上記 CP-1 の「自分の変更が作ったか」で判定）。1,000 件 × 想定同時キーワード数程度なら実測ベースでは即座に破綻する規模ではなく（`rate_cache` 自身も「要確認」止まりで実測数値を出していない）、`SP-16` の完了条件には含めない。

---

## 3. `ux_paging` の反論（バッジに `dependentCount` が要る）を認め、分割案を修正する

`ux_paging` の指摘は正しい: 操作レビュー手順 3 は「**被依存数と star の乖離** がわかる」と明記しており、`gemIndex` の数値 1 個だけの表示では「乖離」（2 項目の比較）を説明できない。round1 の `SP-16a`（最小カード＝ Index 数値のみ）はこの手順を満たさない。**この点は撤回する。**

**分割案の修正**（`C-1`〜`C-5` を単独スプリントで満たす必要があるため、境界を引き直す）:

**`SP-16a`（1 本目・修正版）**: 全ページ取得（内部ループ・`domain_arch` 案採用・§1）+ join usecase + `gemIndex` ソートオプション + `enforceSearchRateLimit` の sort 別スロット化（§2）+ **`RepositorySummary` への `gemIndex?` / `dependentCount?` optional フィールド追加 + `daily-digest.tsx` のバッジパターンを流用したカード表示**（`ux_paging` 提案どおり。**新規デザインではなく既存パターンの再配線** なので当初懸念していたほど重くない）+ 対応する単体テスト + E2E（操作レビュー手順 1〜6 を **フルカバー**、手順 3 も含む）。

**`SP-16b`（2 本目・縮小）**: `SortPicker` で `gemIndex` を選んだときだけ出る注記文言（「Gem Index は一部のみ算出されています」・`ux_paging` 提案）の追加と i18n 仕上げ、および `dependentRank`/`starRank` の視覚的な比較表現（棒グラフ的な強調など、テキストバッジを超える表現）が要ると判断された場合の拡張。

**この修正により、`SP-16a` 単独で操作レビュー手順 1〜6 が全て通しで確認できる**（`ux_paging` の反論は解消され、分割案は成立する）。`SP-16a` の見積もりは round1 時点より上がる（バッジ + `dependentCount` 配線 + レート制限修正の分）が、§1 のキャッシュ簡素化で相殺されるため、**単独スプリント（分割しない場合の `SP-16` 全体）の合計規模としては round1 判定から大きく動かない**。

---

## 4. 再見積もり（3 レンズ案 + 上記の取捨選択を反映）

| 要素 | round1 見積もり | round2 修正後 |
|---|---|---|
| 全ページ取得ループ | 中 | 中（変わらず。ただし sort 漏れ防止のテスト項目を追加） |
| 全件キャッシュ | 中（新設） | **削除**（既存ポートの流用で不要・§1） |
| join usecase | 中 | 中（変わらず。`domain_arch` 案で「既存ユースケース内分岐」に確定・新規ファイルなし） |
| sort-order 拡張 + 波及 | 小〜中 | 小〜中（変わらず） |
| カード表示（バッジ） | 中（`SP-16b` 送り想定だった） | 小〜中（`SP-16a` へ前倒し。ただし既存パターン流用のため単価は下がる） |
| `enforceSearchRateLimit` の sort 別スロット化 | （round1 では未検討） | **新規・小**（§2） |
| 単体テスト | 中 | 中（対象が増えた分やや増） |
| E2E | 中〜大 | 中〜大（変わらず・§3.2 の候補プール差し替え機構は依然必要） |

**合計判定: round1 と同じく「収まるが超過リスクの高いグレーゾーン」を維持する。** キャッシュ簡素化による削減と、レート制限修正・バッジ前倒しによる追加がほぼ相殺し、正味の変動は小さい。着手セッションは §3 の修正済み `SP-16a`/`SP-16b` 分割を初手から用意しておくことを推奨する（「1 firing で `SD-1` に届かなければ次 firing で分割」の待機ではなく、最初から境界を決めておいた方が手戻りが小さい）。
