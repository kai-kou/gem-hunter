<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: SP-16: 検索結果の Gem Index 順ソート（①末尾温存 ②最大1000件取得）の設計方針

- 議題ID: `sp16-gem-index-sort-20260821`
- 論点: 飼い主決定（Issue #285）: ① Gem Index を持たない結果は末尾に残す（絞り込まない） ② 最大1,000件を取得してから並べ替える。この決定を前提に、クリーンアーキテクチャの層配置・レート予算の吸収方法・AC-6/AC-7 との整合をどう設計するかを議論する。
- 参加者: `arch`, `rate`, `ux`
- 投稿数: 6
- 更新: 2026-08-21T09:31:13+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

## ラウンド 1

### `arch` — 主張
<sub>2026-08-21T09:14:34+09:00</sub>

## arch レンズ: SP-16 Gem Index 順ソート — アーキテクチャ観点

### 論点1: マージ・並べ替えロジックの置き場所

**推奨**: 2 分割する。
- **純粋な並べ替え規則**（gemIndex を持つ項目は昇順、持たない項目は元の相対順を保ったまま末尾に残す）は **domain**（`src/domain/model/gem-index.ts` に関数を追加。例 `sortSummariesByGemIndexRank(items, gemIndexByFullName)`）。GitHub が無くても意味が通る規則（architecture-rules.md §1 の判定基準そのもの）であり、ネットワーク無しでユニットテストできる（`W-3`）。`src/domain/services/` は新設しない（domain-model.md §5 の既定方針どおり、既存の `gem-index.ts` に併置）。
- **手続き**（`GemDigestPort` から候補プールを読む・1000 件まで検索結果をループ取得する・並べ替え関数へ渡す・表示ページ分だけ切り出す）は **usecase**（`search-repositories.ts`）。`GemDigestPort` を新規依存として注入する案は妥当 — 複数ポートを組み合わせて 1 操作を完遂するのはユースケースの定義そのもの（`get-daily-digest.ts` も同型で `GemDigestPort` を消費している前例あり）。

却下した代案: マージ・並べ替えロジックを infrastructure（例: `GithubRepositoryQuery` や新規 adapter）に置く案。GitHub 依存の取得と無関係な業務規則（並び替え）を混在させ、ACL の責務（外部語彙の変換のみ）を超える。ユニットテストにネットワーク/フェイク HTTP が要ることになり `W-3` に反する。

### 論点2: `SortOrder` への `gem-index` 追加と API 送出の分離

**推奨**: `SortOrder`（`src/domain/model/sort-order.ts`）の `ALLOWED_SORT_ORDERS` に `'gem-index'` を追加し、型は分割しない。「API へ送ってよい値」と「アプリ内ソート」の分離は **`src/infrastructure/github/github-repository-query.ts` の中だけ** で行う（既存の `if (query.sort !== 'relevance') { …sort/order を付与… }` を `!== 'relevance' && !== 'gem-index'` に広げるだけ）。GitHub 検索 API へ渡す `sort` を選ぶ判断は元々 ACL（infra/github）の仕事であり、新しい変換規則が 1 行増えるだけで済む。`gem-index` 指定時は `relevance` 相当（sort/order 無指定）で取得し、その後 usecase が並べ替える。

却下した代案: `SortOrder` を「API 用」「表示用」の 2 型に分割する。`SearchQuery`/`CacheKey`（`cache-key.ts` の `searchResultCacheKey` は `sort` を直接キーへ含める）・URL との 1:1 対応（`NFR-2`）を担う型が単一である前提を崩し、分岐が 1 パターンしかないのに恒久的な変換層を新設することになり YAGNI 違反（`application-architecture.md` §0 の W-1〜W-3 いずれにも該当しない）。

### 論点3: 「最大 1,000 件取得」とポート契約

**推奨**: `RepositoryQueryPort.search()` の契約は変更しない（1 ページ分を返す既存の意味論を維持）。**usecase 側でループする**: `search-repositories.ts` が `query.sort === 'gem-index'` のときだけ `deps.repos.search()` を `page=1..10 / perPage=100` で最大 10 回呼び、`items` を連結してから domain の並べ替え関数へ渡し、最後に要求された `page`/`perPage`（表示用）でスライスして返す。`totalCount` は 1 回目の応答をそのまま使い、`incompleteResults` は取得した全ページの OR を取る。`CachingRepositoryQuery` は既存のキー設計（`page`/`perPage`/`sort` を含む）のまま透過的に効くため変更不要 — 10 回のうち再訪問分はキャッシュヒットする。

却下した代案①: ポートに `searchAllPages(query, maxPages)` 等の新メソッドを追加する。`gem-index` という 1 ソート方式のためだけに面積を広げることになり、`application-architecture.md` §2「表に無いポートを実装しない／面積を広げるときは W-1〜W-3 のどれかを 1 行で言えること」を満たせない。
却下した代案②: `search()` の引数に `maxPages` を追加する。全実装（`GithubRepositoryQuery` / `CachingRepositoryQuery` / 将来のフェイク実装・テスト）がこの引数を意識する必要が生じ、`gem-index` 以外の全呼び出しにとって無意味なパラメータを増やす。

### 論点4: 新規ドメイン語の要否

- `SortOrder` の許容値表（`domain-model.md` §4）に `gem-index` を追記する必要がある（新語ではなく既存語彙表の値追加）。
- 新しい型・エンティティの追加は不要と判断する。`RepositorySummary` に `gemIndex` フィールドを足すかどうかは **UI 表示要件（バッジ表示等）が確定してから** の話であり、今回のソート機能だけなら並べ替え用の一時マップ（`repositoryFullName → GemIndex`）で完結し、`RepositorySummary` 自体は変更しない。表示要件が出た時点で別途 `domain-model.md` 更新が必要になる点は Issue に書き残す。
- 「最大 1,000 件（10 ページ）」という数値は業務規則というより実装定数であり、ドメイン語彙表への追加は不要。ただし `prd.md` の `AR-n`（表示件数と同様の性質）に準ずる仕様値として、usecase 内定数化しコメントで根拠（GitHub 検索 API の 1000 件上限）を明記すること。

同一 PR で `docs/03_design/data-model/domain-model.md` §4（`SortOrder` 行）の更新が必須。

### `rate` — 主張
<sub>2026-08-21T09:15:03+09:00</sub>

# rate（レンズ: レート制限予算・キャッシュ・性能・障害時の劣化）— Round 1

## 論点1: 全ページ取得のキャッシュキー粒度

**推奨**: 既存 `searchResultCacheKey`（`page`/`sort`/`per_page` を含む）とは別に、Gem Index 順ソート専用の **集約キー** を新設する。`page` を含めず、`keyword` + GitHub 側 `sort`（gem-index はアプリ内ソートなので GitHub API へは渡さない下層 sort、例えば relevance）+ `per_page=100` 固定 で構成する。取得した最大 1,000 件（10 ページ分）を **1 つの配列として 1 キーにまとめて cache.set** する。表示件数（`AR-3`: 20/50/100）や表示ページはこの集約結果をアプリ内でスライスするだけにし、スライス結果自体はキャッシュしない（CPU コストが軽いため）。

根拠: 既存キーは「1 API 呼び出し = 1 キー」の対応が前提（`cache-key.ts` コメント「ソート順・表示件数はキャッシュ断片化を招くため構成要素に含める」）。Gem Index 順は「10 回の API 呼び出しの結果を 1 つの論理的な検索結果」として扱う必要があり、既存の 1:1 対応をそのまま使うと（ご指摘の通り）ページ送りのたびに 10 回再取得が走る。

**却下案**: 既存 `searchResultCacheKey`（`page` を含む）をそのまま使い、ページ 1〜10 をそれぞれ個別キーで `cache.set` する。→ 却下理由: 10 個のキーが独立した TTL で個別に失効するため、同じ「1,000 件セット」のうち一部だけが古い/欠けた状態で再構成される可能性があり、GitHub 検索インデックスの変動と相まって非アトミックな不整合を生む（例: ページ 3 だけ TTL 切れで再取得すると、ページ 1・2・4〜10 と検索時点がずれる）。1 論理結果 = 1 キーで書き込みをアトミックにすべき。

## 論点2: TTL は既存 60 秒でよいか

**推奨**: 既存 `TTL_SEARCH_SECONDS`（60 秒・`src/composition/container.ts`）とは別の定数（例 `TTL_SEARCH_ALL_PAGES_SECONDS`）を新設し、`TTL_DETAIL_SECONDS`（300 秒）と同じ暫定値を採用する。理由: `ADR 0005` §3.4「追補（2026-08-19 実施）」で確定した 60 秒は **1 検索 = 1 API 呼び出し** を前提にレート枠を逆算した値（`repository-publication-review.md` §7 が正本、本ファイルでは中身未確認だが ADR 本文に「1 検索あたりの API 呼び出し数 × 想定利用者数」と明記）。Gem Index ソートは 1 検索あたり最大 10 回の API 呼び出しになりうるため、同じ TTL のままだと **この経路だけレート消費が最大 10 倍** になり、ADR が確定させた計算の前提が崩れる。

**ADR 改訂の要否**: 別 Issue ではなく **`ADR 0005` への追補（同一ドキュメントの改訂）を推奨**。理由: ADR 0005 §3.4 は「再決定条件」を「同時利用者 20 名規模」「L3 導入」の 2 つに限定しており、「1 検索あたりの API 呼び出し数が変わる」ケースを想定していない。TTL 決定の権威は既に ADR 0005 にあるため、新たな ADR を並列に作ると TTL の正本が 2 箇所に分裂する。ただし **数値の妥当性検証（R-5 相当の逆算のやり直し）自体は SP-16 のスコープ外**（CLAUDE.md「スコープ外の改善は別 Issue」）なので、SP-16 では暫定値（300 秒）を採用しつつ ADR 追補で明記し、正式な逆算は別 Issue で追う、という 2 段構えにする。

**却下案**: 60 秒のまま変更しない。→ 却下理由: R-5 の前提（1 検索 1 呼び出し）と矛盾したまま運用することになり、ADR が「確定値」と明言した根拠が SP-16 の実装によって静かに壊れる（ドキュメントとコードの矛盾を放置しない・`SD-4` 完了条件）。

## 論点3: 途中ページでのエラー時の挙動

**推奨**: **fail-closed**（取得できた分で打ち切って並べ替えるのではなく、全体を失敗させてエラーを呼び出し元へ伝播する）。理由:
- `NFR-8`「API 呼び出しの失敗を握りつぶさない。利用者に伝えたうえでアプリケーションを継続利用可能に保つ」。10 ページ中の一部だけを使って静かに並べ替えた結果を返すと、利用者は「これが Gem Index 順の完全な結果」と誤認する（失敗が握り潰される）。これは NFR-8 違反。
- 途中ページのエラーは `prd.md §7` の判別表にそのまま写像できる。403/429 + `x-ratelimit-remaining: 0` → `rateLimitPrimary`、403/429 + `retry-after` → `rateLimitSecondary`、5xx → `UpstreamError`、fetch 失敗 → `NetworkError`。既存 `github-repository-query.ts` の `toDomainError` がページ単位のリクエストでも同じ判定をそのまま使えるため、10 回のループのどこで失敗しても「そのエラー種別」をそのまま最上位へ投げればよく、新しい判別ロジックを増やす必要がない。
- 飼い主確定仕様①（Gem Index を持たない結果は絞り込まず末尾）は「取得した 1,000 件の中に Gem Index 未設定のものが混じる」ケースの話であり、「取得自体が一部失敗した」場合の話ではない。両者を混同して「部分取得も同じ寛容さで扱ってよい」と拡大解釈しない。

**却下案**: 取得できたページまでの結果で打ち切り、部分データで並べ替えて返す（fail-open）。→ 却下理由: NFR-8 の「握り潰さない」に反する（エラーが起きたことも、結果が不完全であることも UI に伝わらない）。また「何ページ目まで成功したか」を UI に伝える新しい状態表現が必要になり、`SP-16` のスコープ（並べ替え機能）を超えて UI 要件を増やす。レート制限で 3 ページ目が落ちたケースでは、そもそも「あと 7 回叩いても大抵また同じレート制限に当たる」ため、部分データを使う実利も薄い。

## 論点4: 逐次取得 vs 並列取得

**推奨**: **逐次取得**（1 ページずつ、前の応答を待ってから次を投げる）。`prd.md NFR-7` が明示: 「③ GitHub API 呼び出しの直列化（公式が並行実行を非推奨としているため）」。10 リクエストを並列で投げるのは既存の明文化されたポリシーに正面から反する。副次的にも、二次レート制限（`retry-after` 系）は短時間の集中リクエストで発火しやすく、10 並列は単一の逐次より発火リスクが高い。

**却下案**: 10 リクエストを `Promise.all` で並列投入する。→ 却下理由: `NFR-7` の直列化方針に反する。実測レイテンシが問題になる場合でも、対応は「並列化」ではなく「早期打ち切り（論点5）」で呼び出し回数自体を削るべき。

## 論点5: 総ヒット件数が少ないときの早期打ち切り

**推奨**: 1 ページ目のレスポンスに含まれる `total_count`（`SearchResult.totalCount` として既にマッピング済み・`src/infrastructure/github/mapper.ts:23`）を使い、`totalPagesNeeded = Math.min(10, Math.ceil(totalCount / 100))` を1ページ目取得後に計算してループの上限をこの値に差し替える。さらに防御的に、ある回の応答の件数が `per_page`（100）未満だった場合もその回で打ち切る（最終ページ到達の副次シグナル）。30 件ヒットの例では 1 ページ目で `totalCount=30` が判明し、`Math.ceil(30/100)=1` となるため 2 回目以降のリクエストは発生しない。

**却下案**: 常に固定 10 回取得してから打ち切る。→ 却下理由: `NFR-7`（レート制限に耐える）の趣旨に反し、無駄な API 呼び出しでレート枠を消費する。`totalCount` は既に取得済みの情報（追加のリクエストなしで判定可能）なので、使わない理由がない。

### `ux` — 主張
<sub>2026-08-21T09:15:25+09:00</sub>

# ux レンズ: SP-16 Gem Index 順ソート

## 1. `sort` の値文字列: `gem-index`（推奨）／却下案 `gem_index`

- **推奨**: `gem-index`（ケバブケース）
  - 根拠: §2.4.1 の `sort` 許容値は `relevance` / `stars` / `updated` の単語のみで、複合語の先例が本コードベースにはまだない。ただし `per_page` の **キー名** は snake_case、URL の **値** 側は GitHub API 由来の単語をそのまま渡す設計（`AR-2` 備考で「同じ UI に追加」と明記）。Gem Index は GitHub API に転送しない自前ソート（`GR-4`）なので、GitHub の語彙と衝突しない値にできる自由度があり、URL リテラルとしては kebab-case が Web の慣例（`ui-ux-guidelines.md` に反する記述はなし）。
  - `ALLOWED_SORT_ORDERS` へ追加するだけで既存の丸め処理（不正値→既定値）・`SortPicker` の `Record<..., string>` 型がそのまま効く。
- **却下**: `gem_index`（スネークケース）
  - 理由: `per_page` の snake_case は **キー名** の慣習であって値の慣習ではなく、`sort` の既存値に snake_case の先例がない。GitHub API の `sort` パラメータ自体は underscore を使う語（例: `updated`）もあるが複合語の実例がないため根拠が弱く、kebab の方が「URL の値」として一貫性が高い。

## 2. カードへの追加表示: Gem Index ランクの視覚ラベル（推奨）／却下案「生値の表示のみ」

- **推奨**: `RepositoryList` の既存メタ行（`primaryLanguage` / star / updatedAt を並べている `<p className="... flex flex-wrap gap-x-4 gap-y-1 text-xs">`）に、Gem Index でソートされているときだけ **1 項目追記** する。
  - 表示形式は `daily-digest.tsx` の踏襲: `<span aria-hidden="true">{labels.gemIndexLabel} </span>` + 数値。ただし操作レビュー手順 3 が求めるのは「なぜ上位なのか（被依存数と star の乖離）」であり、Gem Index の生値（-6.7 等）だけでは "乖離" が伝わらない。**被依存数ランクと star ランクの両方を持つのは `Gem` 型**（`gem.ts`）であり、`RepositorySummary`（検索結果の型）は `stars` は持つが被依存数ランクを持たない。検索結果はライブ検索（GitHub API 直叩き）で、静的配信の Gem Index（`GR-5`）とはデータ経路が別なため、被依存数ランクをこのカードに載せるのは本スプリントのスコープ外の可能性が高い（`RepositorySummary` にフィールドが無いなら "曖昧点" ではなく実装可否の技術的制約＝ SD-3 の確認対象ではないが、**親セッションへの申し送り事項** として明示する）。
  - 現実的な最小追加は「Gem Index の数値」を `labels.gemIndexLabel`（例: 日本語「Gem Index」= `daily-digest` と統一語）付きで出す。**生値（負数含む）をそのまま出してよい**: `daily-digest.tsx` が既に `gemIndexValue` の生数値（-63.9 等）を出典表示なしで直接見せている先例があり、符号は「相対順位（プラスなら過小評価、マイナスなら知名度先行）」の意味を持つため隠さない方がむしろ ux 的に正しい（符号の意味を `sortOptions.gemIndex` 選択時のみ 1 行の補助文言で説明する案は後述 §3）。
  - この結果が Gem Index を持たない（`Gem Index を持たない結果は末尾に残す`＝仕様①）場合、その項目には Gem Index 数値を出さず、代わりに §3 のバッジ/見出しで区別する。
- **却下**: 「被依存数ランクと star ランクを両方カードに表示し乖離を数値で見せる」
  - 理由: `RepositorySummary`（検索結果ドメインモデル）に被依存数フィールドが存在するか未確認・現状のコード grep では見当たらず、追加するなら API 呼び出し経路の変更を伴う可能性が高い（スコープが SP-16 の「並べ替え」を超え、SD-4 の「読めば分かること」の範囲を超える）。曖昧なまま実装すると「2 通り以上の解釈で成果物が変わる」（SD-3 発火条件）に該当しうるため、**この 1 点だけ親セッションでの確認候補として残す**（Gem Index 数値のみ表示 vs 被依存数・star 内訳まで表示、の 2 択）。

## 3. Gem Index を持たない結果が末尾に来ることの UI 表現: 区切り見出し（推奨）／却下案「バッジのみ」

- **推奨**: 一覧内に **1 本だけの区切り見出し**（例: 日本語「Gem Index 情報なし」/ 英語 "No Gem Index data"）を、Gem Index 順ソート時 **かつ** 両グループが両方存在するときだけ挿入する。
  - `ui-ux-guidelines.md` §4.4「状態表現」は 4 状態（idle/loading/empty/error）を排他的に切り替える指針であり、本件は「1 つの結果リスト内の部分的な性質の違い」なので同列には扱えないが、**同じ「支援技術に状態変化を伝える」設計思想**（§7.2 `aria-live` / `role="status"`）を踏襲し、見出し自体は `role="status"` にはせず、視覚的には `<li>` 内の `<h3>` 相当（または `<p>` に `aria-hidden` を使わない通常テキスト）として **`<ul>` の中に埋め込む**（別リストへ分割すると `AC-3`/`AC-7` が前提にする「1 つの結果一覧」構造・件数表示 `resultCount` の計算が壊れる恐れがあるため、DOM 構造は 1 つの `<ul>` のまま維持し、見出し行だけ `<li>` として挿入するのが最小変更）。
  - スクリーンリーダーでの読み上げ: 見出しの `<li>` 自体はリスト項目としてそのまま読み上げられるため、通常の見出しテキストで十分に伝わる（追加の `aria-live` は不要 — ページ全体の並び替えは `AC-8` が要求する `aria-live` ではなく、`page.tsx` の「結果一覧の見出しへ focus 移動」パターン（§7.1）でカバーされる操作結果であり、新規に `aria-live` を足すと `SortPicker` 変更のたびに二重通知になる）。
  - 件数表示（`resultCount` = `{total} 件中 {shown} 件を表示`）は変更不要（仕様①により件数は変わらない）。
- **却下**: 「各カードに “Gem Index なし” バッジを個別表示」
  - 理由: Gem Index を持つ結果が大多数を占める通常ケースでは「ある」側にバッジを付けないと非対称になり、逆に「ない」側だけ毎カードにバッジを付けると末尾グループ全体で同じ文言が繰り返され冗長（スクリーンリーダーでも同一文言の連呼になる）。区切り見出し 1 本の方が「どこからが対象外か」を一度で伝えられ、`ui-ux-guidelines.md` 全体の「情報過多を避ける」トーンにも合う。

## 4. 追加する i18n メッセージキー（`messages/{ja,en}.json` の `home` 配下、既存命名規約に合わせる）

既存規約: `sortOptions.{value}` は `sort` の許容値名そのまま（`relevance`/`stars`/`updated`）。ラベル系は `xxxLabel`。区切り見出し系の先例は無いが `resultsHeading` に倣い名詞 + `Heading` を採用。

```jsonc
// home 配下に追加
"sortOptions": {
  // 既存 relevance/stars/updated に追加
  "gemIndex": "Gem Index 順" /* ja */ // en: "Gem Index"
},
"gemIndexValueLabel": "Gem Index" /* ja/en 共通（daily-digest.gemIndexLabel と同一文言に揃える） */,
"gemIndexUnavailableHeading": "Gem Index 情報なし" /* ja */ // en: "No Gem Index data"
```

- キー名は `gemIndex` プレフィックスで統一（`daily-digest.gemIndexLabel` と表記を揃え、ユーザーが同じ概念だと認識できるようにする）。
- `sortOptions.gemIndex` の文言は他の並び順ラベルと語調を揃える: ja は既存が体言止め（「関連度」「star 数」「更新日時」）なので `"Gem Index 順"` を推奨（「順」を付けて並び順であることを明示。他の3つは意味的に自明だが Gem Index は初見語のため補う）。en は既存が名詞のみ（"Relevance" 等）なので `"Gem Index"` のまま。

## 5. E2E で検証すべき項目（既存 spec の書き方に合わせたテスト名の箇条書き）

`e2e/sp-16.spec.ts`（新規ファイル。`sp-7.spec.ts` の構成を踏襲: `test.step` で手順を分割、`uniqueManyHitsKeyword` 相当の一意キーワード関数を再利用または新設）

- `test('SP-16: Gem Index 順に並べ替えても件数が変わらず、情報なしの結果は末尾に残る', ...)`
  - `test.step('前提: Gem Index を持つ結果と持たない結果が混在する検索を実行しておく')`
  - `test.step('1. 並び順を Gem Index 順に切り替える → URL に sort=gem-index が乗る')`（`SEARCH_PARAM_KEYS.sort` 経由でアサート、`sp-7.spec.ts` の正規表現パターンを踏襲）
  - `test.step('2. Gem Index を持つ結果が Gem Index の降順で並んでいる')`（先頭カードの `data-testid` かリンク名で順序を確認）
  - `test.step('3. Gem Index を持たない結果は一覧の末尾に残り、区切り見出しが表示される')`
  - `test.step('4. 総件数表示（resultCount）が並び替え前後で変化しない')`（仕様①の直接検証）
- `test('SP-16: Gem Index 順のページ送り・詳細往復で並び順が保たれる（AC-6 / AC-7）', ...)`
  - `test.step('1. Gem Index 順で 2 ページ目へ移動する → URL に page=2 と sort=gem-index が両方乗る')`
  - `test.step('2. カードから詳細ページへ遷移し、戻る導線で一覧へ戻る → sort=gem-index / page=2 が保持されている')`（`AC-6` 「直前の検索条件が保持されている」の直接検証。`back-link.tsx` 経由）
  - `test.step('3. per_page=100 など 1,000 件境界に近いケースでも 1,000 件超のページを要求しない')`（`AC-7` の「取得可能な範囲を超えるページを要求しない」を Gem Index 順でも壊さないことの回帰確認。既存スタブのデータ件数次第では省略可 — スタブ側の対応要否は実装側の判断）
- （a11y）既存 `sp-7.spec.ts` の `createAxeBuilder` パターンを流用し、区切り見出し挿入後も deque axe の serious/critical 違反が増えないことを確認する 1 ケースを追加する

## ラウンド 2

### `lead` — 合意
<sub>2026-08-21T09:16:53+09:00</sub>

## 合意（lead 集約・round 2）

3 レンズの主張を突き合わせ、対立は 1 点だけだった。

### 一致した点

| 論点 | 決定 |
|---|---|
| 並べ替え規則の置き場所 | **domain**（`src/domain/model/gem-index.ts` に純関数を追加）。GitHub が無くても意味が通る規則であり、ネットワーク無しで単体テストできる |
| 取得・合成の手続き | **usecase**（`src/usecases/search-repositories.ts` に `GemDigestPort` を注入） |
| `SortOrder` | `ALLOWED_SORT_ORDERS` に `'gem-index'` を追加し、型は分割しない。「API へ送る sort」と「アプリ内 sort」の分離は ACL（`github-repository-query.ts`）の中の 1 行拡張で済ませる |
| ポート契約 | **変更しない**。`RepositoryQueryPort.search()` は 1 ページ分を返す既存の意味論のまま。全件取得は usecase 側のループで行う |
| 取得の並列度 | **逐次**（`NFR-7` ③「GitHub API 呼び出しの直列化」に従う。10 並列は二次レート制限の発火リスクも高い） |
| 早期打ち切り | 1 ページ目の `totalCount` から `min(10, ceil(totalCount / 100))` を算出してループ上限を差し替える。加えて応答件数が `per_page` 未満なら最終ページとして打ち切る |
| 途中ページの失敗 | **fail-closed**（部分データで静かに並べ替えない・`NFR-8`「失敗を握りつぶさない」）。エラー種別は既存 `toDomainError` の判定をそのまま最上位へ伝播する |
| 並べ替えの向き | **昇順**（`gem-index.ts` の正本コメント: 値が小さいほど過小評価度が高い）。`get-daily-digest.ts` の 2 段目と同じ向きに揃える |
| URL の値 | `sort=gem-index`（kebab-case） |
| Index 非保有分の UI | 区切り見出しを **1 本だけ** 挿入する（個別バッジは冗長・スクリーンリーダーで同一文言の連呼になる） |

### 対立した点と裁定: キャッシュのキー粒度

- `rate`: **集約キー新設**（`page` 非依存で 1,000 件を 1 キーに格納）。ページごとの独立 TTL で失効すると「一部だけ新しい」非アトミックな合成が起きる
- `arch`: **既存キーのまま**（`searchResultCacheKey` は `page` / `sort` / `per_page` を含むので、10 回の呼び出しがそれぞれ透過的にキャッシュされる）。ポートにもキャッシュにも手を入れない

🔵 **裁定: `arch` 案（既存キーのまま）を採る。ただし `rate` が指摘した非アトミック性は「マージ時の `id` による重複排除」で潰す。**

- 集約キーを新設すると、usecase が `CachePort` を直接持つことになり、キャッシュの責務が infra デコレータと usecase の 2 箇所に分裂する（`ADR 0005` が `CachePort` を YAGNI 例外として 1 箇所に閉じた前提が崩れる）
- 既存キーは `sort=gem-index` を含むため通常閲覧のエントリとは別物になり、断片化の相互汚染は起きない
- `rate` の懸念（ページ間の鮮度ずれで同一リポジトリが重複・欠落する）は実在するが、**マージ時に `RepositorySummary.id` で重複排除する** ことで観測可能な破綻は消える。欠落は「その時点の検索インデックスでは実際に落ちた」ケースと区別できず、`totalCount` 表示にも影響しない
- 🔵 `rate` の TTL 追補提案は **採用する**（キー設計とは独立に成立する）。`gem-index` 経路だけ 1 検索あたり最大 10 リクエストになり、`ADR 0005` が「1 検索 = 1 呼び出し」で逆算した 60 秒の前提が崩れるため、**同一 PR で ADR 0005 に追補を書く**。TTL 値そのものの再逆算は本スプリントのスコープ外なので別 Issue へ回す

### `ux` が申し送った 1 点への裁定（カードの表示内容）

`ux` は「被依存数と star の乖離を見せるには `RepositorySummary` に被依存数が無い」ことを親への確認候補として挙げた。🔵 **確認は不要**（`SD-3` 発火せず）: 候補プール（`Gem` 型）は `dependentCount` と `stars` を保持しており、Gem Index を持つ結果はプール由来なので **被依存数はマージ時に手元にある**。操作レビュー手順 3 が要求する「なぜ上位なのか」は、Gem Index 値と被依存数を並べて出せば満たせる。ドキュメントを読めば決まることを聞かない（`SD-4`）。

### `lead` — 判定
<sub>2026-08-21T09:17:16+09:00</sub>

{
  "decision": "proceed",
  "sprint": "SP-16",
  "decisions": [
    {"id": "D-A", "topic": "並べ替え規則の層", "value": "src/domain/model/gem-index.ts に純関数を追加（昇順・非保有は末尾に安定保持）"},
    {"id": "D-B", "topic": "取得手続きの層", "value": "src/usecases/search-repositories.ts に GemDigestPort を注入し、逐次ループで最大 10 ページ取得"},
    {"id": "D-C", "topic": "SortOrder", "value": "ALLOWED_SORT_ORDERS に 'gem-index' を追加。型は分割しない"},
    {"id": "D-D", "topic": "API への sort 送出", "value": "github-repository-query.ts で 'gem-index' も 'relevance' と同様に sort/order を送らない"},
    {"id": "D-E", "topic": "ポート契約", "value": "RepositoryQueryPort は変更しない"},
    {"id": "D-F", "topic": "キャッシュ", "value": "既存 searchResultCacheKey をそのまま使う。マージ時に RepositorySummary.id で重複排除する"},
    {"id": "D-G", "topic": "TTL", "value": "値は変更しない。ADR 0005 に『gem-index 経路は 1 検索最大 10 リクエスト』の追補を同一 PR で書き、再逆算は別 Issue"},
    {"id": "D-H", "topic": "取得の並列度", "value": "逐次（NFR-7 ③）"},
    {"id": "D-I", "topic": "早期打ち切り", "value": "min(10, ceil(totalCount/100)) と『応答件数 < per_page』の二重条件"},
    {"id": "D-J", "topic": "途中失敗", "value": "fail-closed。既存 toDomainError の種別をそのまま伝播（NFR-8）"},
    {"id": "D-K", "topic": "URL 値", "value": "sort=gem-index（kebab-case）"},
    {"id": "D-L", "topic": "カード表示", "value": "gem-index 順のときだけ Gem Index 値と被依存数を追記（プール由来なので手元にある）"},
    {"id": "D-M", "topic": "非保有分の UI", "value": "区切り見出しを 1 本だけ挿入（両グループが存在するときのみ）"},
    {"id": "D-N", "topic": "i18n キー", "value": "sortOptions.gemIndex / gemIndexValueLabel / gemIndexDependentLabel / gemIndexUnavailableHeading"}
  ],
  "critical": [],
  "follow_up_issues": [
    "ADR 0005 の TTL を『1 検索あたりの API 呼び出し数が可変』な前提で再逆算する（gem-index 経路は最大 10 倍）"
  ],
  "docs_to_update_in_same_pr": [
    "docs/03_design/data-model/domain-model.md §4（SortOrder の許容値に gem-index を追記）",
    "docs/adr/0005-cache-port-yagni-exception-and-ttl.md（レート消費の前提変更の追補）"
  ],
  "out_of_scope": [
    "docs/02_requirements/user-story-map.md §5.3 SP-16（オープン中の PR #289 が既に確定反映済み・二重更新しない）"
  ]
}

### `ux` — 主張
<sub>2026-08-21T09:30:48+09:00</sub>

# ux レンズ: round1 の訂正 + `listGemFacetsUseCase()` を踏まえた更新

## 訂正 A（重要・round1 の誤り）: Gem Index の並び順と符号の意味

`src/domain/model/gem-index.ts` の実装・コメント（正本）を読み直したところ、round1 の記述に **2 箇所誤り**があった。

1. **並び順は昇順（値が小さいほど上位）**。round1 §5 の e2e テスト名で「Gem Index の**降順**で並んでいる」と書いたのは誤り。正しくは「Gem Index の**昇順**（小さい値が先頭）で並んでいる」。`sortByGemIndex` の実装・コメントが明記（`D-28` 訂正注記と同じ向き）。
2. **符号の意味も round1 と逆**。round1 §2 で「プラスなら過小評価、マイナスなら知名度先行」と書いたのは誤り。正しくは **マイナス（負値）が過小評価度が高い（= "Gem"）**、プラスは知名度（star）が実利用（被依存数）より先行していることを意味する（`computeGemIndex` のコメント: 「被依存数が上位（小さい）かつ star が下位（大きい）ほど差が強い負値になり、過小評価度が高いことを意味する」）。

**影響**: e2e スペック案・カード表示の符号説明文言は、この訂正後の向きで書くこと（round1 の該当箇所をそのまま実装に持ち込まない）。

## 更新 B: `impl_usecase` の共有を受けて §2 の推奨を確定

`listGemFacetsUseCase()`（`src/composition/container.ts`）が `ReadonlyMap<gemFacetKey, GemFacet>`（`GemFacet = { gemIndex, dependentCount }`）を返す。`SearchResult` / `route.ts` の契約は無変更。これにより round1 §2 で「親セッションへの確認候補」として保留していた論点が解消した。

- **確定推奨**: カードのメタ行に **Gem Index の生値**（`gemIndexValueLabel`）に加えて、**被依存数**（`daily-digest.tsx` の `dependentLabel`「被依存数」と同一語彙を再利用）も表示する。両方を並べることで操作レビュー手順 3「なぜ上位なのか（被依存数と star の乖離）がわかる」を数値で直接裏付けられる（star 数は既存の `starCount` 表示が既にカードにあるため、被依存数だけ追加すれば「被依存数 vs star」の対比が完成する）。
- 表示条件: `sort=gem-index` のときのみ（他のソートでは `GemFacet` を取得する意味が薄く、`listGemFacetsUseCase()` の追加呼び出しコストも避けられる）。Gem Index を持たない結果（`facets` に無い項目）はこの追加表示自体を出さない（区切り見出し側で「情報なし」を伝えるため、カード側で欠落を繰り返し示さない）。
- 表示順は「被依存数 → Gem Index」（`daily-digest.tsx` の並び: `dependentLabel` → `starsLabel` → `gemIndexLabel` を踏襲し、star は round1 通り既存の `starCount` 表示のまま据え置く）。

## 更新 C: i18n キーへの追記（round1 §4 に追加）

```jsonc
"dependentLabel": "被依存数" /* ja、en: "Used by" — daily-digest.dependentLabel と同一文言を home 側にも複製せず、共有できるなら共通化を検討（実装側の判断）*/
```
既存 `daily-digest.dependentLabel` と全く同じ意味・同じ文言なので、新規キーを増やすより **既存キーの再利用（`messages.home.digest.dependentLabel` を home 直下からも参照 or `home.gemIndexDependentLabel` として複製）** を実装側で選んでよい（SD-3 対象外の実装判断）。

## 更新 D: e2e（round1 §5 の訂正版）

- `test.step('2. Gem Index を持つ結果が Gem Index の**昇順**（小さい値が先頭）で並んでいる')`（round1 の「降順」を訂正）
- 追加: `test.step('カードに被依存数と Gem Index の数値が表示され、Gem Index を持たない結果には表示されない')`

`impl_usecase` へ確認事項なし・追加依頼なし（返答のみ）。
