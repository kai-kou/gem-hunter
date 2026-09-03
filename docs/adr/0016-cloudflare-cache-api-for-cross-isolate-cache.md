# ADR 0016: Cloudflare Cache API を 2 段目に重ね、isolate を跨いでキャッシュを共有する

- **状態**: **承認**
- **日付**: 2026-09-03 JST
- **対応要件**: `NFR-5`（API レスポンスのキャッシュ） / `NFR-7`（レート制限耐性） / `NFR-17`（Cache Port の面積） / `NFR-18`（キャッシュキー命名規約） / `NFR-21`（PaaS 固有機能への依存最小化） / `INF-2`（コスト） / `INF-5`（事業者固有 API をアプリコードへ持ち込まない） / `ARCH-4`（事業者固有バインディングの隔離）
- **関連**: [ADR 0005](./0005-cache-port-yagni-exception-and-ttl.md)（Cache Port・TTL・single-flight の正本） / [Cloudflare インフラ設計](../03_design/infrastructure/cloudflare-infrastructure.md) §4 / [インフラ設計](../03_design/infrastructure/infrastructure-design.md) §6 / [`open-questions.md`](../02_requirements/open-questions.md) `D-5` / `D-18` / `D-24` / Issue #121

---

## 1. 文脈

### 1.1. 実測: isolate 内キャッシュのヒット率が 17% しかない

[ADR 0005](./0005-cache-port-yagni-exception-and-ttl.md) が決めた L2 の実装 `InMemoryCache` は、composition root（`src/composition/container.ts`）のモジュールスコープ singleton として全リクエストから共有される。しかし共有されるのは **その isolate の中だけ** である。

Issue #121 でプレビュー環境を実測したところ、次の結果になった（いずれも **1 本のキーへの連打** であり、2 行目は 1 行目とは別のキーを使った独立した計測である。6 本の別々の URL へ 1 回ずつ投げたものではない）。

| 計測 | リクエスト | `X-Cache-Status: HIT` | HIT 率 |
|---|---|---|---|
| 同一 URL（キー A）へ 12 回連続 | 12 | 2 | ≒17% |
| 別の同一 URL（キー B）へ 6 回連続 | 6 | 2 | ≒33% |

TTL（検索 60 秒）内の連続アクセスであり、キャッシュ実装そのものは正しく動いている。それでも HIT しないのは、**Cloudflare Workers がリクエストを複数の isolate へ分散し、isolate ごとに別の `Map` が立つ** ためである。1 isolate = 1 キャッシュである以上、リクエストが散るほどヒット率は下がる。

これは実装の欠陥ではなく、`InMemoryCache` という選択の構造的な帰結である。ADR 0005 §5 も「`InMemoryCache` は isolate をまたいで永続しない」を **受け入れる代償** として明記し、緩和策を「将来の格上げ候補として Cache API（`caches.default`）の能動利用を記録するに留める」としていた。本 ADR はその格上げの記録である。

### 1.2. `caches.default` は何を変えるか

Cloudflare の Cache API（`caches.default`）は **originating data center（コロケーション）単位** で共有され、isolate のリサイクルに影響されない。同じコロケーションに届いたリクエストは、どの isolate に載っても同じキャッシュエントリを見る。

---

## 2. 決定

### 2.1. `InMemoryCache` を **置き換えず**、2 段構成にする

`CachePort` の実装として `LayeredCache`（`src/infrastructure/platform/layered-cache.ts`）を導入する。

| 段 | 実装 | 生存範囲 |
|---|---|---|
| **primary** | `InMemoryCache`（`src/infrastructure/platform/cache.ts`） | isolate 内 |
| **secondary** | `WorkersCache`（`src/infrastructure/platform/workers-cache.ts`・`caches.default`） | コロケーション内 |

- `get`: primary が HIT ならそこで返し、secondary は引かない。secondary が HIT したら値を返しつつ primary へ充填する（同じ isolate の次のリクエストが secondary へ往復しないようにする）
- `set`: 両段へ書く。TTL 値域外の `RangeError` は握り潰さず呼び出し側へ伝播させる（fail-open を作らない）
- `invalidate`: 片方が throw してももう片方を実行し、自身は throw しない（冪等）

### 2.2. 🔴 なぜ「置き換え」ではなく「2 段」なのか（本決定の中核）

`caches.default` が本プロジェクトの構成で実際に効くかどうかは、**公式ドキュメントを読んでも確定できない**（§5.2）。ここで `InMemoryCache` を Cache API で **置き換える** と、Cache API が実質 no-op だった場合にヒット率は現状の 17% から **0% へ悪化しうる**。

2 段にすれば、変化は **片方向にしか起きない**。

- Cache API が効く → secondary が HIT を拾い、ヒット率は上がる
- Cache API が効かない（no-op・常に MISS） → primary だけが効き、**現状（17%）を維持する**

未確定要因を抱えたまま前へ進める唯一の形がこれであり、「効くかどうかを実測で決着させるまで、悪化する経路を作らない」という設計判断である。

### 2.3. `caches.default` は L3 ではなく **L2 の実装差し替え** である

🔴 [`infrastructure-design.md`](../03_design/infrastructure/infrastructure-design.md) §6.2 が「入れる判定条件」を課しているのは **L3（外部ストア: R2 / D1 / KV）** であって、本決定はその L3 の導入では **ない**。理由は 3 点。

1. **新規バインディングを伴わない**: `caches.default` は Workers ランタイムのグローバルであり、`wrangler.jsonc` へバインディングを追加しない
2. **支払い方法の登録（`A-6`）を伴わない**: R2 の有効化が要求するユーザー作業（`cloudflare-infrastructure.md` §4.4 / `infrastructure-design.md` §6.2 の注記）が発生しない
3. **永続ストアではない**: Cache API のエントリはコロケーション内の揮発的なキャッシュであり、いつでも退避されうる。`D-5`（DB を持たない）にも、`D-18`（永続ストア R2 / D1 / Durable Objects / KV を採用しない）の列挙にも抵触しない

したがって本決定は **L3 未採用のまま**、L2 の実装（ADR 0005 §2.1 が `InMemoryCache` と定めた部分）を差し替えるものである。

🔵 **[ADR 0005](./0005-cache-port-yagni-exception-and-ttl.md) §3.4 の TTL 再決定条件は「発火する。ただし再逆算は不要」と判定する。** 同 §3.4 が挙げる 2 条件のうち「`InMemoryCache`（isolate 内メモリ）より広い共有キャッシュを導入したとき」は、本決定が **コロケーション単位の共有キャッシュを 2 段目に足す** ため **文言どおり満たす**（同 §3.4 はこれを括弧で `L3` と呼んでいるが、本 ADR §2.3 のとおり本決定は L3 の導入ではない。条件の趣旨は「共有範囲が広がると TTL の前提が変わるか」であり、その趣旨に照らして判定する）。**その判定結果は「TTL の再逆算は不要」**: `R-5` の逆算は「1 検索あたりの上流 API 呼び出し数 × 想定利用者数」からレート枠を求めるものであり、本決定は同一キーへの上流 API 呼び出しを **増やす方向には一切変えない**（共有範囲が広がることで呼び出しは減るだけ）。したがって検索 60 秒 / 詳細 300 秒という確定値の前提は不変で、TTL は変更しない。もう一方の条件（同時実利用者 20 名規模の実測）は本決定とは無関係に未充足のまま。

### 2.4. `D-24` の撤回ではない（`X-Cache-Status` は付与できる）

`D-24` は「L2 の主役を HTTP `Cache-Control` + Workers Caching（エッジキャッシュ）から **アプリ内 `CachePort` の実装** へ移す」決定だった。理由は、エッジキャッシュが HIT すると **Worker 自体が実行されず** `X-Cache-Status` を動的付与できないことにあった（`cloudflare-infrastructure.md` §4.5）。

Cache API は性質が違う。`caches.default.match()` は **Worker のコードが明示的に呼ぶ** ものであり、HIT しても Worker は必ず実行される。したがって `CachingRepositoryQuery` の `onCacheStatus` コールバックも Route Handler の `X-Cache-Status` 付与も、これまでどおり動く。

**本 ADR は `D-24` が置いた「L2 の主役はアプリ内 `CachePort`」という構造を維持したまま、その `CachePort` の実装だけを差し替える。**

### 2.5. ポート面積・依存の隔離は変えない

- `CachePort` の面積は `get` / `set` / `invalidate` + TTL のまま。広げない（`NFR-17`）
- `caches` の型・参照は `src/infrastructure/platform/` に閉じる（`ARCH-4` / `NFR-21` / `INF-5`）。`WorkersCache` は `@cloudflare/workers-types` に依存せず、実際に使う 3 メソッド（`put` / `match` / `delete`）だけを自前の `WorkersCacheStorage` 型で受ける
- キャッシュキーの命名規約（`NFR-18`）は変えない。`CacheKey` は `https://cache.gem-hunter.internal/<encodeURIComponent(key)>` という合成 URL の GET `Request` へ写す（Cache API のキーは `Request` であり `CacheKey` はそのままでは URL ではないため）。`encodeURIComponent` を必ず通し、`:` `/` `=` `?` `#` を含むキーが別キーと同じ URL へ潰れないようにする

### 2.6. `caches` が無い環境では `InMemoryCache` 単独へフォールバックする

composition root は **実行時に** `caches.default` の存在（3 メソッドが揃っているか）を判定する。使えなければ `LayeredCache` を組まず `InMemoryCache` 単独で動かし、`console.warn` で「Cache API が使えないため isolate 内メモリキャッシュへフォールバックした」ことを表明する。

判定を実行時に置くのは、`caches` が Workers 実行環境のグローバルであり、Vitest / Node / ビルド時には存在しないためである。**本番 Workers でこの警告が出ていたら、Cache API の判定か配線が壊れている**（isolate 跨ぎの共有が失われている）というシグナルとして使う。

---

## 3. 🔴 `infrastructure-design.md` §6.2 観測条件 2 の「想定」を数値で定義する

§6.2 の条件 2 は「キャッシュヒット率が **想定** を下回り、`INF-2` または `NFR-7` を満たせない」と書かれているが、**その「想定」がどこにも数値で定義されていなかった**。そのため条件充足を機械的に判定できず、Issue #121 の起票時に判断が止まった。本 ADR で数値を確定させる（**この節が「想定」の定義の正本であり、他所へ数値を複製しない**）。

### 3.1. 定義

| 項目 | 定義 |
|---|---|
| **計測条件** | プレビューまたは本番の `GET /api/search` に対し、**同一クエリ（＝同一キャッシュキー）** で、検索 TTL（60 秒）以内に **12 回連続** リクエストする |
| **計測値** | 応答ヘッダ `X-Cache-Status: HIT` の回数 ÷ 12 |
| **想定値** | **12 連打ヒット率 75%**（12 回中 9 回以上が HIT） |
| **条件 2 の充足** | 計測値が **75% を下回った** とき、§6.2 の観測条件 2 を満たしたものとして扱う |

🔴 **判定に使えるのは本節の計測条件（新規キーへ 12 連打）で採った値だけである。** ウォーム済みのキーへ短い連打を足した測定（§6.1 の 2 行目のような 6 連打）は、初回 MISS の重みが小さくなるぶん高く出るため、**本節の 75% と比較してはならない**（参考値として扱う）。「定常」「ウォーム」等の別語で呼び分けた測定値を本節の判定へ流用しないこと。

### 3.2. 75% の根拠

同一キーへ TTL 内で 12 回連続アクセスしたときの理想値は **11/12 ≒ 92%**（初回だけが MISS で、以降は TTL 切れまで HIT する）。ここから、isolate の入れ替わり・コロケーションの差・デプロイ直後の cold start による取りこぼしとして **追加の MISS を 2 回ぶん（12 回中 3 回 = 25%）まで許容** し、下限を 75% に置く。言い換えると「同一キーに対する上流 API 呼び出しが、理想の毎分 1 回に対して **毎分 3 回を超えたら異常** とみなす」ラインである。

`NFR-7` の律速は検索 API の 30 req/分（`R-5` の逆算・[パブリック化レビュー](../05_release/repository-publication-review.md) §7.2）であり、同一キーが毎分 3 回を超えて上流を叩く状態は、**キャッシュがレート枠を節約しているとは言えない** 水準である。逆に 75% 以上であれば、キーの分散（利用者が別々の語で検索する）を考えても枠の逆算が壊れない。

### 3.3. 本 ADR 起票時点の判定

§1.1 の実測 **17%** は 75% を大きく下回っており、**観測条件 2 は充足済み** である。ただし条件 2 が要求するのは「検討して ADR を起票すること」であって「L3 を入れること」ではない。検討の結果、本 ADR は **L3（外部ストア）ではなく L2 の実装差し替え（§2.3）** を選んだ。

---

## 4. 却下した選択肢

| 選択肢 | 却下理由 |
|---|---|
| **Cache API で `InMemoryCache` を置き換える**（2 段にしない） | `caches.default` が本構成で効くかは公式ドキュメントで確定できない（§5.2）。no-op だった場合にヒット率が 17% → 0% へ **悪化しうる**。2 段なら最悪でも現状維持で、変化は片方向に限定される（§2.2） |
| **L3（R2 / D1 / KV）を導入する** | R2 の有効化は **支払い方法の登録**（`A-6`）というユーザー作業を伴い、`D-5`（DB を持たない）・`D-18`（永続ストアを採用しない）の再検討も必要になる。isolate 跨ぎの共有という目的は、バインディングも課金設定も伴わない Cache API で達成できる。L3 は本 ADR の後もなお **未採用** のまま維持する |
| **HTTP `Cache-Control` によるエッジキャッシュに依存する**（`D-18` 原案への回帰） | `D-24` で却下済み。エッジキャッシュが HIT すると Worker 自体が実行されず、`SP-5` の受け入れ条件に必要な `X-Cache-Status` を動的付与できない（`cloudflare-infrastructure.md` §4.5）。Cache API は Worker のコードが明示的に呼ぶため同じ問題が起きない（§2.4） |
| **`LayeredCache` の充填 TTL を secondary の残 TTL に揃える** | `CachePort` の `get` は値だけを返し **残り TTL を返さない**。揃えるにはポート面積を広げる必要があり `NFR-17` の歯止めを破る。固定値（既定 60 秒）で妥協し、制約を §5 に明記する |

---

## 5. 結果（この決定がもたらすもの）

### 5.1. 良い方向

- isolate 跨ぎでキャッシュが共有され、同一キーへの上流 API 呼び出しが減る（`NFR-7` のレート枠・`INF-2` の CPU 時間の 2 軸に効く）
- 最悪ケースでも **現状維持**。Cache API が効かなくても primary（`InMemoryCache`）がこれまでどおり働く（§2.2）
- `X-Cache-Status` による外部検証（ADR 0005 §2.3 / `cloudflare-infrastructure.md` §4.5）がそのまま使える。`SP-5` の操作レビュー手順を変えずに済む
- `CachePort` の面積も `src/usecases/*` も無改修。差し替えは composition root と `src/infrastructure/platform/` の中で閉じる（`ARCH-4` を維持）

### 5.2. 受け入れる代償: Cloudflare Cache API の制約

出典: [Cloudflare Docs — Cache](https://developers.cloudflare.com/workers/runtime-apis/cache/)（本 ADR 起票時に実取得して確認）。

| 制約 | 本プロジェクトへの影響 |
|---|---|
| `cache.put()` は **GET リクエストのみ**（他メソッドは throw） | `cacheKeyToRequest()` が生成する `Request` は既定で GET。影響なし |
| **`Set-Cookie` を含むレスポンスは決してキャッシュされない**（回避策: ヘッダ削除、または `Cache-Control: private=Set-Cookie`） | `WorkersCache` が `put` するのは自前で組み立てた JSON 封筒の `Response` であり `Set-Cookie` を持たない。影響なし |
| `206 Partial Content` / `Vary: *` / 過大サイズ（413）はキャッシュ不可 | 同上（自前生成の 200 応答のみ）。ただし将来キャッシュ対象を増やすときに再確認が要る |
| **ダッシュボードのエディタと Playground のプレビューでは Cache API 操作が無効（no impact）** | 🔴 これらの経路で動作確認しても意味がない。**検証は必ずデプロイ済みのプレビュー / 本番へ実 HTTP リクエストを投げて行う**（§6） |
| Cloudflare Access で保護された Worker では Cache API は利用不可 | 現構成では Access を使っていない。将来プレビューを Access で保護する判断をするなら、この段が無効化されることを織り込む |
| `cache.put` は **tiered caching と非互換** | tiered caching は有効化していない。有効化を検討する際に本行を再確認する |
| キャッシュ内容は **originating data center の外へ複製されない** | 共有はコロケーション単位であり、グローバルに 1 つのキャッシュにはならない。利用者が地理的に散るほど、コロケーションごとに独立した MISS が発生する |

### 5.3. 受け入れる代償: 実装上の制約

| 制約 | 内容 |
|---|---|
| **充填した primary のコピーが secondary より長生きしうる** | `CachePort` が残り TTL を返さないため、secondary HIT 時の充填 TTL は固定値（既定 60 秒 = 本プロジェクト最短の TTL）。最悪ケースは「secondary の残 TTL が 1 秒の状態で充填」で、その isolate は最大 59 秒だけ secondary から見て失効済みの値を返す。これは `InMemoryCache` 単独運用でも許容していた古さの範囲であり、**上流 API 呼び出しを増やす方向の劣化ではない** |
| **Vitest では fake が要る** | `caches` は Workers 実行環境のグローバルで Node には存在しない。ユニット/結合テストは `WorkersCacheStorage` の fake を注入して書く（`caches` の存在に依存したテストを書かない） |
| **`D-18` の 3 軸のうち「リクエスト数」には効かない** | `cloudflare-infrastructure.md` §4.1 のとおり、キャッシュから返したリクエストも Worker のリクエスト枠を消費する。本決定が効くのは **GitHub API のレート枠** と **CPU 時間** の 2 軸だけで、リクエスト数枠の削減にはならない |
| **TTL の表現が `max-age` の整数秒に丸まる** | Cache API は `Cache-Control: max-age` を秒単位で解釈する。1 秒未満の TTL は 1 秒へ切り上げる（`set` したのに必ず MISS になる挙動を作らないため） |

### 5.4. 🔴 未確定のまま残すこと（実測で決着させる）

以下の 2 点は **公式ドキュメントに記載が無く**、断定できない。実測で決着させる（§6）。

1. **合成 URL をキーにできるか**: 実装は Worker 自身のゾーン / ホスト名に属さない `https://cache.gem-hunter.internal/<key>` をキーにしている。cross-zone のキーが許容されるのか、拒否されるのか、拒否される場合にどのエラーが throw されるのかは、いずれも公式ドキュメントに記載が無い
2. **`*.workers.dev` での動作可否**: 明示されていない（クエリ文字列がキーの既定に含まれる旨の記述から動作が示唆されるのみ）

`WorkersCache` はどちらの失敗も `get` → `null` / `set` → 無視に倒すため、**未確定のまま本番へ出しても壊れない**（効かないだけで、その場合は primary の現状維持に落ちる）。

---

## 6. 検証方法

**デプロイ済みのプレビュー環境へ実 HTTP リクエストを投げて計測する**（ダッシュボードのエディタ / Playground では Cache API が無効なため、そこでの確認は証拠にならない・§5.2）。

1. §3.1 の計測条件（同一クエリで `GET /api/search` へ 12 回連続）でヒット率を測る
2. §1.1 の実測（≒17%）と比較する

| 結果 | 次のアクション |
|---|---|
| **75% 以上** | 決着。§3 の想定値を満たす |
| **17% から改善したが 75% 未満** | Cache API は効いている。コロケーション分散・TTL の見直しなど別要因として切り分ける |
| **17% から改善しない** | 🔴 §5.4 の未確定要因（合成オリジンが拒否されている / `*.workers.dev` で無効）を疑い、**キーの合成オリジンを自ゾーンの URL（`https://<デプロイ先ホスト>/__cache/<key>` 等）へ変える** 変更を試し、再計測する |

> 計測手順のスクリプト化は **Issue #124** で追う（本 ADR の範囲外）。

### 6.1. 実測結果（2026-09-03 JST・PR #874 のプレビュー）

`https://pr-874-gem-hunter.kinamocchi-tech.workers.dev/api/search?q=<キー>` へ連続リクエストし、`X-Cache-Status` を数えた。

| 計測 | 並び | HIT 率 |
|---|---|---|
| 新規キー A を 12 連打 | `MISS×5 → HIT×7` | 7/12（58%） |
| 同じキー A を続けて 6 連打（**参考値**・§3.1 の計測条件外） | `HIT HIT MISS HIT HIT HIT` | 5/6（83%） |
| 新規キー B を 12 連打 | `MISS HIT MISS HIT MISS HIT HIT MISS MISS HIT HIT HIT` | 7/12（58%） |
| 新規キー C を 12 連打 | `MISS MISS MISS HIT MISS MISS HIT MISS HIT HIT HIT HIT` | 6/12（50%） |

**判定: §6 の 3 分岐のうち「17% から改善したが 75% 未満」**（§3.1 の計測条件で採った新規キー 3 本が 50〜58%）。

⚠️ 表 2 行目（ウォーム済みキーへの 6 連打・83%）は **§3.1 の計測条件外の参考値であり判定には使えない**（初回 MISS の重みが小さく高く出る）。判定は 12 連打の 3 本だけで行っている。

🔴 **これにより §5.4 の未確定 2 点が決着した**（実測が唯一の決着手段だったもの）。

| 未確定だったこと | 実測による結論 |
|---|---|
| Worker 自身のゾーン外の合成 URL（`https://cache.gem-hunter.internal/<key>`）をキーにできるか | **できる**。合成オリジンのまま HIT が発生している（拒否されていれば HIT 率は 17% 前後のまま変わらないはず） |
| `*.workers.dev` で Cache API が動くか | **動く**。本計測は `*.workers.dev` のプレビューに対して実施した |

🔴 **測定の限界**: 本 PR の構成では `X-Cache-Status` が **primary（isolate 内メモリ）HIT と secondary（Cache API）HIT を区別しない**。したがって上表の結論は「primary 単独では説明できない改善幅（17% → 50〜58%）」からの **推論であって、secondary が働いたことの直接証拠ではない**。層別カウンタ（secondary HIT 数）を取得して直接証拠にする作業は **#875 で追う**。

したがって §6 の 3 分岐目（合成オリジンを自ゾーン URL へ変える）は **実施しない**。

**残差（75% に届かない分）の扱い**: 新規キーの初回に MISS が連続する挙動が残っており、コロケーション分散か Cache API への書き込みが後続の読み取りに間に合わないラグが疑われる。本 ADR の決定（2 段構成の採用）は実測で裏付けられたため変更せず、**残差の切り分けは別 Issue（#875）として追う**（本 PR のスコープを広げない・`CP-1`）。

🔴 **`infrastructure-design.md` §6.2 の観測条件 2 は、本 PR の後も依然として充足状態である。** §3.1 の判定式（新規キーへ 12 連打・想定値 75%）に照らすと、上表の 3 本（58% / 58% / 50%）はいずれも 75% を下回っている。本 ADR が条件 2 に対して要求どおり「検討して ADR を起票する」を果たしたことと、条件 2 の **充足状態が解消したこと** は別である（解消していない）。**その解消は #875 で追う**。

---

## 7. 参照

| ドキュメント | 関係 |
|---|---|
| [ADR 0005](./0005-cache-port-yagni-exception-and-ttl.md) | Cache Port の面積・TTL 値・single-flight の正本。本 ADR はその §2.1 が定めた L2 実装だけを差し替える |
| [Cloudflare インフラ設計](../03_design/infrastructure/cloudflare-infrastructure.md) §4.1 / §4.2 / §4.4 / §4.5 | キャッシュ 3 軸・採用構成・L3 判定条件・`X-Cache-Status` の付与位置 |
| [インフラ設計](../03_design/infrastructure/infrastructure-design.md) §6.1 / §6.2 | 3 層構成と L3 導入の観測条件（条件 2 の「想定」の数値定義は本 ADR §3 が正本） |
| [`open-questions.md`](../02_requirements/open-questions.md) `D-5` / `D-18` / `D-24` | DB レス原則・永続ストア不採用・L2 主役の改訂。本 ADR はいずれも撤回しない（§2.3 / §2.4） |
| [`prd.md`](../02_requirements/prd.md) `NFR-5` / `NFR-7` / `NFR-17` / `NFR-18` / `NFR-21` | 要件の正本 |
| [Cloudflare Docs — Cache](https://developers.cloudflare.com/workers/runtime-apis/cache/) | §5.2 の制約一覧の出典 |
