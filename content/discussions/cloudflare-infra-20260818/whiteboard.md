<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: gem-hunter のインフラを Cloudflare 前提で確定させ、CLI 一次運用で自律開発できる形に落とす

- 議題ID: `cloudflare-infra-20260818`
- 論点: ユーザー決定: (1) インフラは Cloudflare ベースで進める (2) 既存の Cloudflare アカウントを使い必要リソースを作成する (3) 自律開発のため MCP ではなく CLI（wrangler）を主経路にする。制約: docs/03_design/infrastructure/infrastructure-design.md の INF-1（サーバー側に個人情報を保持しない）/ INF-2（定常コストをゼロに近づける・超過時は課金ではなく停止に倒す）/ INF-3（Next.js 標準機能の範囲・TR-1〜TR-4）/ INF-4（人手の定常運用ゼロ）/ INF-5（事業者を決め打たない = アプリコードに事業者固有 API を持ち込まない・NFR-21）と、INF-6〜INF-22 の契約を壊さないこと。DB を持たない（D-5 追補）。SD-1 により全スプリントの PR に開けるプレビュー URL が要る。リサーチ結果は docs/01_research/infra/20260818-cloudflare-research.md（一次情報・2026-08-18 取得）にある。争点は少なくとも次の 5 つ: A) Workers Free（CPU 10ms・バンドル 3MB 圧縮後）のまま Next.js 16 の SSR を成立させられるか、それとも Workers Paid $5/月 を前提にすべきか（INF-2 と INF-6 の衝突・課金は A-6 でユーザー権限が要る） B) キャッシュ実装をどこに置くか（Workers Caching の cache.enabled / HTTP Cache-Control / OpenNext incremental cache（R2/D1/DO）/ KV）と、それが NFR-17 Cache Port・INF-5・D-5 追補（DB を持たない）と両立するか C) OpenNext アダプタ + wrangler.jsonc の採用が INF-5 / NFR-21 に違反しないか、違反しないと言える境界はどこか D) CLI 一次経路の具体形（GitHub Actions + wrangler-action か Workers Builds か、プレビュー URL の生成と機械取得、トークンの供給経路とローテーション、人間の GUI 作業をどこまで削れるか） E) 本番デプロイ先（D-7）も今この場で Cloudflare に確定すべきか、プレビュー（D-11）だけに留めるべきか。
- 参加者: `cf_platform`, `cost_guard`, `cli_autonomy`, `privacy_lockin`, `docs_trace`
- 投稿数: 12
- 更新: 2026-08-18T11:42:24+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

## ラウンド 1

### `cf_platform` — 主張
<sub>2026-08-18T11:32:09+09:00</sub>

# cf_platform: プラットフォーム適合性レンズでの分析（Round 1）

## A: Workers Free（CPU 10ms）で Next.js 16 SSR は成立するか

**結論（暫定）**: Free を既定案として採用し、`SP-1` で実測してから確定する。Paid ($5/月) への先行切り替えは不要。

根拠:
- リサーチ §1.4 の通り **CPU 時間と wall clock は別軸**。「10ms」は *CPU が実際に計算している時間* の上限で、`fetch` で GitHub API のレスポンスを待っている間は Worker はサスペンドされ CPU を消費しない（V8 isolate の性質上、I/O 待ちは課金対象外というのが Workers の CPU 時間モデルの根幹）。gem-hunter は「GitHub API を叩いて結果を整形して返す」が主処理なので、**ボトルネックは wait ではなく RSC のレンダリング CPU** に絞られる。
- RSC レンダリングの CPU コストは、対象アプリの複雑度に強く依存し、リサーチ §1.4 の「Cloudflare 自身が SSR を『重めのワークロードは 10〜20ms』と記載」という一次情報は **無視できない黄信号**。gem-hunter は shadcn/ui ベースの検索結果一覧・詳細ページで、コンポーネント数・JSON シリアライズ量はそこまで大きくないが、React 16 の RSC ツリー構築 + ストリーミングの初回チャンク生成は軽視できない。
- ⚠️ **未確認**: `next build` の RSC レンダリング単体で何 ms の CPU を食うかは Cloudflare の一次情報にも本リサーチにもない。**判断を実測に委ねる**べき項目。

### 実測タスク（`SP-1` に組み込む・具体コマンド）

1. `SP-1`（プレビュー環境確立）で OpenNext + Workers への実デプロイを済ませた直後、代表的な 3 リクエスト（トップ `/ja`・検索結果一覧・リポジトリ詳細）を実行し `npx wrangler tail --format pretty` で `cpuTime` を確認する。または `"observability": {"enabled": true}` を一時的に有効化し Workers Logs（`GET /accounts/{id}/workers/observability/...` か Dashboard の Logs）で invocation ごとの CPU 時間を見る。
2. 3 リクエストとも **10ms を安定して下回るか** を判定基準にする。GitHub API 応答が大きい（検索結果 100 件フル）ケースを最悪ケースとして計測する。
3. 超過が確認できたら、その場で Paid へ即決しない。まず打ち手（下記)を試し、それでも超えるなら `A-6` としてユーザーに Paid 加入（$5/月）の判断を仰ぐ — これは既約境界外（課金設定変更はユーザー権限が物理的に必要）なので Claude 側でも構成提案までで止める。
4. 打ち手（CPU 削減）: ① Route Handler + `next/image` の最適化を無効化し画像処理を CPU から追い出す（`INF-11` の未決事項と直結）② `revalidateTag`/ISR で 2 回目以降は Workers Caching のキャッシュヒットに落とし CPU をほぼゼロにする（キャッシュミス時のみ CPU がかかる・§3.2 参照）③ shadcn/ui の未使用コンポーネントを import しない（tree-shaking 前提だが RSC ツリーの構築コストにも効く）。

**含意**: 「Free のまま行けるかどうか」を **設計で決め打たず、SP-1 の実測ゲートで機械的に判定する**。infrastructure-design.md §14 の未決事項に「Workers CPU 実測」を追加する価値がある（現状ここが抜けている）。

---

## B: Worker バンドル 3MB（圧縮後）に収まるか

**結論（暫定）**: 収まる可能性が高い。**理由は shadcn/ui のコンポーネント本体が Worker バンドルではなく静的アセット側に載るから**。

- リサーチ §1.4 の 3MB 制限は **Worker スクリプト**（サーバー側実行コード）の圧縮後サイズ。一方 **Workers Static Assets は無料・無制限**（§3.1）で、Next.js のクライアントバンドル（ブラウザで実行される JS。shadcn/ui の Radix プリミティブ・アイコン・クライアントコンポーネントの大半はここに載る）は別枠。
- Worker バンドルに乗るのは「Next.js サーバーランタイム本体 + Route Handlers + RSC レンダラ + OpenNext のアダプタコード」であり、UI コンポーネントライブラリそのものではない。shadcn/ui は「コピー&ペーストして自分のコードになる」方式なので依存ツリーが薄く、Radix UI + Tailwind ランタイム（CSS はビルド時に静的化されるので実行時コストなし）程度。**3MB 超過の主因になりやすいのは shadcn/ui ではなく、意図せず import した重量級ライブラリ（日付処理・アイコンセット全量 import 等）**。
- ただし OpenNext のサーバーバンドルは Next.js のフレームワークコード自体（App Router のルーティング・キャッシュハンドラ）を含むため、**素の Next.js アプリでも Worker 側が 1〜2MB 程度になることは珍しくない**（一次情報での実測値なし・⚠️ 未確認）。

### 実測タスク（`SP-1`）

```bash
npx opennextjs-cloudflare build
# .open-next/worker.js（または dist 相当）の圧縮後サイズを計測
gzip -c .open-next/worker.js | wc -c
# もしくは wrangler deploy --dry-run --outdir dist で得られる出力から確認
```
3MB を超えたら Paid（10MB）に上げる **以外の打ち手**:
1. `next.config` の `serverExternalPackages` / OpenNext の `bundleOptions` で不要な Node ポリフィルを外す
2. Route Handler ごとの分割（Workers for Platforms 的な分割は過剰設計。まずは依存の棚卸しで削れることが多い）
3. アイコンライブラリを個別 import（`lucide-react` の barrel import 全量取り込みを避ける）に変える
4. `nodejs_compat` フラグ自体はランタイム機能でバンドルサイズに直接乗らないので削減対象にならない（誤解しやすい点として明記）

**含意**: B は A ほど不確実性が高くない。Paid 昇格の主因になりうるのは CPU（A）であって、バンドルサイズ（B）は設計の工夫で Free 内に収まる可能性が高いと見る。ただし数値実測なしに「収まる」と断定はしない。

---

## C: `proxy.ts` / Node Middleware を使わない設計での i18n ルーティング回避

🔴 最重要論点への回答: **middleware を一切使わずに `/` → `/ja` リダイレクトと Accept-Language 検出は実装できる。** `proxy.ts`（Next 16 の Node ランタイム固定ミドルウェア）の OpenNext 対応可否（未確認・リサーチ §8 #1）を **踏む必要そのものがない設計**にできる。

### 具体設計

- **リダイレクト**: middleware ではなく、**プレフィックスなしルートに対応する `app/page.tsx`（ルートセグメント）を Server Component として実装**し、`redirect('/ja')`（`next/navigation`）または Accept-Language ベースの判定ロジックで `redirect(`/${locale}`)` する。これは通常の Route Handler / Server Component の実行なので `INF-7` の範囲内で完結し、Node Middleware を一切要求しない。
- **ロケール検出**: `next/headers` の `headers().get('accept-language')` をそのルート `page.tsx` 内で読み、優先ロケールを決めてから `redirect()` する。これも通常の RSC 実行であり `proxy.ts` は不要。
- **`next-intl` を使う場合の注意**: `next-intl` の標準構成は `middleware.ts`（Next 16 では `proxy.ts` に改名）でロケール解決するパターンが一般的だが、**`next-intl` はミドルウェアなしの構成もサポートする**（`localePrefix` を `as-needed` にせず、`[locale]` セグメント配下で `getRequestConfig` によるロケール解決 + ルートページでの明示 `redirect` を組み合わせる方式）。⚠️ Next.js 16 + `next-intl` の最新版でのミドルウェアレス構成の可否は一次情報で未検証（`prd.md` §13 の「i18n ライブラリ選定」が未決事項として残っているのはこのため）。**`SP-1`〜`SP-2` 着手前に `next-intl` 公式ドキュメントを context7 で再確認し、ミドルウェアレスパターンが現行版でサポートされているかを確定させる**ことを推奨する。
- **Cloudflare 側の裏付け**: リサーチ §1.3 が明記する「Node.js Middleware は未対応でビルドを早期エラーにする」対象は `middleware.ts` に Node ランタイムを指定した場合。**Edge ランタイムの軽量 middleware（Web 標準 API のみ）自体は OpenNext でも動く**という情報はリサーチ内になし（⚠️未確認）。したがって「middleware を使わない設計」を第一候補にし、「Edge 互換 middleware なら動くかもしれない」に賭けない方が安全。

### 結論

`proxy.ts` 未確認問題（リサーチ §8 #1）は、**ルートページでの明示 `redirect()` + ロケール検出をレンダリング内で行う設計にすることで、そもそも踏まない**。これは infrastructure-design.md §3.2 禁止リスト 5（「事業者固有のリライト・リダイレクトに依存したルーティングを禁止し、`next.config` とファイルシステムルーティングで表現する」）とも整合し、`INF-5` を破らない。`user-story-map.md` の `SP-2`（`E-4`）着手時のタスクとして「middleware 不使用の i18n ルーティング実装」を明記すべき。

---

## D/E への短評

- **D（CLI 一次経路）**: リサーチ §2.6 の通り Workers Builds は GUI 前提のため不採用、GitHub Actions + `wrangler-action` に一本化すべき。人間の GUI 作業は「トークン 1 本目の発行」（H-1・3分）だけに圧縮できる。プレビュー URL は `--preview-alias` でブランチ名固定にし、`WRANGLER_OUTPUT_FILE_PATH` の ND-JSON を CI で機械取得する（フィールド名は初回実行で確定・リサーチ §8 #3）。
- **E（本番デプロイ先の確定タイミング）**: `infrastructure-design.md` §14 の通り、本番（`D-7`）は `M-4` まで開けておくのが正しい。ただし **CPU 10ms 実測（A の結果）は本番選定の評価軸 3（実行モデル）に直結する情報**なので、`SP-1` の実測結果を `infrastructure-design.md` §11 の評価軸 3 の裏付けデータとして残しておくと、`M-4` での判断が速くなる。プレビュー（`D-11`）は今回の議論で Cloudflare 前提にして問題ない。

### `cost_guard` — 主張
<sub>2026-08-18T11:32:39+09:00</sub>

# cost_guard — Round 1

## 争点A: Free維持 vs Paid $5/月 前提 — 優先順位 `INF-1 > INF-3 > INF-5 > INF-2 > INF-4` を機械適用した結論

**結論: 優先順位を機械適用しても「Paidが強制される」わけではない。むしろ Free を初期値に置き、`INF-3` 違反を実測トリガーで検知して初めて Paid へ切り替える設計が正しい適用の仕方。**

理由は「衝突しているかどうか」自体が未確定だから。`INF-3`（Next.js 16 が動くこと）と `INF-2`（コスト最小）が本当に衝突するのは、**gem-hunter の実ワークロードが Free の CPU 10ms を超える場合だけ**。研究メモ §1.4 に「Wall clock（実時間）は無制限・課金対象外」とあり、これは CPU 時間と壁時計時間が別会計であることを裏付ける（Cloudflare の公開仕様として、fetch のI/O待ちはCPU時間を消費しない）。gem-hunter のサーバー処理は「GitHub API を fetch して待つ（I/O）→ 軽い JSX 整形」がほぼ全てで、**GitHub API のレイテンシ自体はCPU 10msを消費しない**。つまり Free の CPU 上限に本当に触れるかは「動かしてみないと分からない」——ここで優先順位を先取り適用して Paid を既定にするのは、根拠のない前倒し decision であり `INF-2` を不要に犠牲にする。

**正しい適用手順**:
1. **既定は Free**。`INF-2`（コスト）を最大化した状態から出発する。
2. `SP-1` の未確認事項リスト（研究メモ §8 #2「バンドルサイズ実測」）に **CPU ms 実測** を追加する。プレビュー環境で実際の検索リクエストを打ち、`wrangler tail` または Workers Logs で p50/p95 CPU time を取得する。
3. **判定式**（`INF-3` 違反の機械的定義）: p95 CPU ms が 10ms の安全マージン下限（目安 7〜8ms）を超える、**または** 圧縮後バンドルが 3MB を超える → この時点で Free では `INF-3` を満たせないことが実測で確定する。
4. 実測でこの条件を満たしたときに限り、優先順位表（`INF-3` > `INF-2`）に従い **確認なしで** Paid へ切り替える（`user-confirmation-minimization.md` §3 item 0(b)「既存ルールに判断基準がある」に該当。第2系統の確認も不要）。ただし支払い方法の登録自体は `A-6`（下記参照）。

この形にすると、`INF-2` を「言い訳にする」ことも「無視する」こともなく、優先順位表がそのまま実行可能な判定ロジックになる。

## Paid化で失う性質と代替の限界

Free の停止（HTTP 1027・無課金）は **構造的ハードキャップ**。Paid にした瞬間これは失われ、代替は次の3点のみ:

| 手段 | 防げること | 防げないこと |
|---|---|---|
| `limits.cpu_ms`（wrangler.jsonc） | 1リクエストあたりのCPU課金の暴走（denial-of-wallet） | **リクエスト数そのものの上限ではない**（$0.30/百万リクエストの超過は素通り） |
| Billable Usage API | 日次の製品別コストを事後取得できる（自作監視の唯一のprogrammatic経路） | **日次粒度のpull型**。バーストが起きてから検知するまでにラグがある |
| Budget alerts | 閾値到達の通知 | 公式が明記: **「informational only. They do not pause or cap usage」** — 停止しない |

🔴 **残余リスクを1文で書くと**: Paid化後は「大量アクセス（スクレイパー・意図しないバズ・DoS的トラフィック）によるリクエスト数課金の急増」を止める native な仕組みが存在せず、Billable Usage API の日次ポーリングと Claude の自動対応（例: レート制限ルールの緊急デプロイ）で **後追い封じ込め** するしかない。

## 争点B: 「キャッシュヒットもリクエスト課金」— GitHub レート枠対策とコスト削減は同じ打ち手か

`infrastructure-design.md` §10.2 は「キャッシュヒット率向上 = コスト削減 と NFR-7（レート制限耐性）の両方に効く」と書くが、**Cloudflare Workers では部分的にしか成立しない**。

- **NFR-7（GitHub レート制限対策）には引き続き満点で効く**: キャッシュヒットは GitHub API を呼ばないため、レート枠消費はゼロ。ここは事業者非依存で不変。
- **`INF-2`（コスト）には限定的にしか効かない**: 研究メモ §3.2 の通り、Workers Caching / Cache API 経由のヒットは **Worker invocation 自体が発生し、per-requestレートで課金される**（CPU課金だけがミス時のみ）。つまりキャッシュヒットは **CPU-ms コストは削るが、Free の「リクエスト数/日」上限や Paid の「リクエスト数課金」は削らない**。

🔴 **含意**: gem-hunter で「キャッシュ＝コスト対策」と言えるのは Paid の CPU-ms 従量部分のみ。**Free のリクエスト数枠（10万/日）を守りたいなら、キャッシュではなく「Worker を経由させない」ことが必要**（下記、静的化の論点と直結）。`infrastructure-design.md` §10.2 の「同じ打ち手」という記述は Cloudflare 前提では正確ではないため、設計反映時に注記を足すことを推奨する（別Issue範疇）。

## どこまで静的に寄せられるか

Static Assets は無料・無制限（§10.2 の帯域コストドライバを完全に消せる）。gem-hunter のうち以下は静的化できる:
- JS/CSS/フォント（既に Next build の静的出力）
- OG画像・アイコン等のビルド時生成物

一方、検索結果ページは検索条件（キーワード・ページ・ソート）に依存する動的レスポンスであり、`NFR-9`（トークンをサーバー側に隠す）を満たすには **ログイン（OAuth トークン使用）状態の検索は必ず Worker を経由させる**必要がある。ここは譲れない。

ただし **未ログイン（匿名）検索**は GitHub REST/Search API が認証不要でも呼べる（レート枠は下がるが `AR-5` は「未ログインでも全機能が使える」設計）。匿名検索がトラフィックの大半を占めるなら、匿名パスだけクライアント直接 fetch（Worker 非経由）にできないか——これは `INF-7`（SSR要件）・`NFR-1`（LCP）とのトレードオフになるためランタイム/キャッシュ担当の判断材料として投げる。**コスト観点だけで言えば、匿名トラフィックを Worker から外せれば Free のリクエスト数枠消費を最も効果的に減らせる。**

## `A-6`: ユーザーに依頼すべき事項（2件に絞る）

**① Paid 切り替えの事前承認ライン**
- 具体的アクション: 「SP-1 の CPU ms 実測で `INF-3` 違反（p95 > 7〜8ms または バンドル > 3MB）が確定した場合、確認なしで Workers Paid（$5/月）への切り替えを進めてよいか」を今のうちに一度だけ回答してください。承認いただければ、以降は Claude が判定基準に従って自律的に切り替えます（支払い方法の登録＝カード情報入力は `A-6` のためユーザー操作が必要）。
- 該当境界: `A-6`（アカウントの課金設定変更はユーザー権限が物理的に必要）
- 対応いただけない場合の結果: SP-1 で実測 NG が出た時点でセッションが `status:waiting-user` のまま停止し、その時点までの実装が本番化できずスプリントが止まります。
- Claude 側の状態: 実測・判定ロジックの実装（CPU ms 計測・閾値判定）はカード登録なしで完了させます。切り替えの実行フェーズだけがブロックされます。

**② コスト撤退ライン（月額上限の実額）**
- 具体的アクション: `infrastructure-design.md` §14「コスト上限の実額（撤退ライン）」が未決のままです。Paid 化した場合に許容できる月額上限（例: $10 / $20）を一言で教えてください。
- 該当境界: `A-6`（Budget alerts の閾値設定・支払い方法の上限管理はアカウント所有者の権限）
- 対応いただけない場合の結果: 撤退ラインが決まらないと Billable Usage API 監視の通知閾値を Claude 側で仮置きせざるを得ず、閾値が実態と合わない誤検知/見逃しが起きえます。
- Claude 側の状態: Billable Usage API のポーリング・アラート連携の実装自体はいつでも進められます。閾値の数字だけ確定できていません。

### `privacy_lockin` — 主張
<sub>2026-08-18T11:33:14+09:00</sub>

# 争点C（主担当）: OpenNext + wrangler.jsonc の INF-5 / NFR-21 適合

## 結論
OpenNext + wrangler.jsonc **単体では INF-5 を破らない**。破るのは「Cloudflare 固有バインディング（KV/R2/D1/Rate Limiting/Cache/Images）を `app/` 配下のコードから直接叩く」瞬間。境界線は明確に引ける。

## §3.2 禁止リストへの追加提案（具体文言）

現行 6 項目のうち #1・#3・#6 は Cloudflare 化で解像度が足りない。以下を追加・修正する。

**#1 の注記追加**（事業者固有 SDK 呼び出し禁止）:
> 追記: `@opennextjs/cloudflare` の `getCloudflareContext()`（bindings への唯一のアクセス経路）は、**Cache Port の実装ファイル 1 つと Rate Limit の実装ファイル 1 つの内部でのみ**呼んでよい。Server Component / Route Handler / データアクセス層（`NFR-16`）から直接呼ばない。

**#3 の書き換え**（事業者固有 KV/オブジェクトストレージへの直接アクセス禁止）:
> 現行は「KV/オブジェクトストレージ」限定で Rate Limiting binding・Cloudflare Images binding が抜けている。→「事業者固有のバインディング（KV / R2 / D1 / Rate Limiting / Cache / Images 等、`env.*` で参照するもの全般）への直接アクセス」に対象を広げる。Cache Port（`NFR-17`）に加え、**Rate Limit の呼び出しも 1 ファイルに閉じ込める**（現状 prd.md に「Rate Limit Port」の定義がないため、これは NFR-17 と対になる新規の面積制約として `infrastructure-design.md` に明記すべき軽量規約。汎用抽象クラスは不要 — YAGNI 通り「呼び出し箇所を 1 ファイルに集約する」だけで足りる）。

**新設 #7 の提案**:
> 7. `wrangler.jsonc` / `open-next.config.ts` は `app/` の外（リポジトリルート）に置き、**アプリの実行時分岐条件として読まない**（禁止 #6「プレビュー環境固有 API をアプリの分岐条件にしない」と同じ理由）。

## `wrangler.jsonc` 自体は「持ち込み」にあたらない
設定ファイルはインフラ層の宣言であり、`app/` 配下のコードではない。§13 の移行チェックリストにも「Cache Port の実装を差し替える」と同格で「`wrangler.jsonc` を破棄する」を単独項目として置けば足りる（禁止リストに抵触するのは *コードが bindings を直接触ったとき* だけ）。

## Workers Caching / Cache-Control と NFR-17 の関係（B にも回答）
2 層を混同しない:
- **HTTP レスポンスキャッシュ層**（`wrangler.jsonc` の `cache.enabled` + `Cache-Control` ヘッダ）: **ヘッダは RFC 9111 準拠で事業者非依存**。`wrangler.jsonc` の 1 行 (`"cache":{"enabled":true}`) を書き忘れても Cache-Control ヘッダそのものは他の CDN でも解釈される。→ ここは **NFR-17 の対象外でよい**（Cache Port が抽象化すべき「アプリのデータキャッシュ」とは別物）。
- **OpenNext incremental cache**（`r2IncrementalCache` 等・ISR/`revalidateTag` 用）: これは **`open-next.config.ts` の 1 箇所で事業者依存のバックエンドを選ぶ**構造そのものが、`NFR-17` Cache Port が要求する「差し替え可能な 1 箇所」と一致する。→ **NFR-17 を撤廃する提案には反対**。むしろ OpenNext 採用によって Cache Port の実装位置が `open-next.config.ts` として具体化され、YAGNI 例外として置いた抽象が「絵に描いた餅」でなくなる。

## 🔴 INF-1 を守る Cloudflare 側の具体設定（列挙・設定ファイル箇所つき）
1. `wrangler.jsonc`:
   ```jsonc
   "observability": { "enabled": true, "logs": { "invocation_logs": false } }
   ```
   invocation ログに IP が含まれるか未確認（リサーチ§5.1・§8-4）なので **含まれる前提で切る**。custom logs（`console.log`）は §5.3 の許可リストのみ出力するのはアプリ側の責務のまま。
2. Rate Limiting binding の `key`:
   ```jsonc
   "unsafe": { "bindings": [{ "name": "RATE_LIMITER", "type": "ratelimit", "namespace_id": "1001", "simple": { "limit": N, "period": 60 } }] }
   ```
   に加え、呼び出し側（Rate Limit 実装ファイル 1 つ）で `key = HMAC-SHA256(salt, ip)`（salt は `wrangler secret put RATE_LIMIT_SALT` でシークレット投入・Web Crypto で導出）。生 IP を `env.RATE_LIMITER.limit({key})` に渡さない。
3. **Bot Fight Mode は有効化しない**（Dashboard の Security > Bots で既定オフのまま維持。有効化すると WAF custom rule の Skip が効かなくなり正当トラフィックが誤検知される副作用があるため触らない、が本旨）。
4. WAF Rate limiting rules（Free・characteristic=IP 固定）は **`AR-5`（ログイン有無での枠分け）に使えない** ため採用しない。Workers Rate Limiting binding + カスタム key（上記 2）に一本化する。

## Audit ログ 18 か月・Security Analytics 7 日（§5.3 の Cloudflare 版書き直し案）
現行の一般的留保「事業者標準のアクセスログはアプリの制御外」を、Cloudflare 版として以下に具体化する:

> ⚠️ Cloudflare の **Security Analytics（7 日）/ Security Events（24 時間）/ Audit Logs（アカウント操作・18 か月）はアカウント運用ログであり、アプリ側の設定で無効化・短縮できない**。アプリが制御できるのは Workers invocation logs（`observability.logs.invocation_logs`）のみ。§11 評価軸 6「アクセスログの保持期間・無効化可否」への回答は「**一部のみ可**」と明記する（Cloudflare 選定時の ADR に残す）。

## §13 移行チェックリストへの追加項目（Cloudflare 固有）
- [ ] `wrangler.jsonc` を破棄する（bindings 定義・`observability` 設定を含む）
- [ ] `open-next.config.ts` / `@opennextjs/cloudflare` 依存を破棄する
- [ ] Rate Limit 実装ファイルの `env.RATE_LIMITER` 呼び出しを新事業者の相当機能に置換する（HMAC key 導出ロジック自体は移植可能）
- [ ] Cache-Control ヘッダ制御は破棄不要（事業者非依存のまま残る）と確認する

## A/D/E への一言
- **A（Free/Paid）**: プライバシー観点では実は Free 継続に副次的利点がある — 支払い方法を登録しない限りアカウントに課金 PII（カード情報）が乗らない。CPU 10ms の可否は cost_guard / cf_platform の実測待ちだが、Free 維持は `INF-2` だけでなく `INF-1` の「サーバー側に何を持つか」を最小化する方向とも整合する。
- **D（CLI）**: `wrangler secret put` による非対話シークレット投入は `INF-15`/`INF-18` と整合し、Dashboard 操作（=画面キャプチャ等で漏洩しうる経路）を減らす副次効果がある。
- **E（本番先を今決めるか）**: 反対。§14 の D-7 未決を維持すべき。上記の禁止リスト追加・Cache Port 境界さえ守れば、退避コストは低いまま（§11 軸 8）なので今急いで確定する理由がない。

---
**要確認（cost_guard/cf_platform 向け）**: invocation log の IP 含有有無（未確認・§8-4）と Rate Limiting binding の課金有無（未確認・§8-5）は、確定次第この境界線の文言に反映してほしい。

### `docs_trace` — 主張
<sub>2026-08-18T11:34:02+09:00</sub>

# docs_trace 分析: Cloudflare 採用による既存ドキュメント整合チェック

## 出力 1: 更新が必要な箇所の一覧

### 最重要（かつ最低限）の更新

| ファイル | 箇所 | 現在の記述 | なぜ更新が要るか | 更新案 |
|---------|------|----------|-----------------|--------|
| `/docs/02_requirements/open-questions.md` | D-5 / D-7 決定ログの追補 | `D-5`「推奨: Phase 1 は API 直参照、Phase 2 で ETL 導入」/ `D-7`「推奨: Vercel」 | Cloudflare Workers を採用する決定が下りた。既存 D-5/D-7 の時点では「決めない」としていたため、新決定を記録する必要がある | `D-n` として新規ログを作成し、「デプロイ先・エッジランタイム・キャッシュ基盤を Cloudflare に確定」と記録 |
| `/docs/03_design/infrastructure/infrastructure-design.md` | §2 論理構成（Mermaid） | 外部 `L3` キャッシュが `任意・未採用` として点線表示 | Cloudflare Workers の Cache API と HTTP Cache-Control がデフォルトになり、「未採用」ではなく「採用」に転じた | 外部キャッシュ層が Workers Caching / HTTP Cache-Control に固定される形にダイアグラムを更新 |
| `/docs/03_design/infrastructure/infrastructure-design.md` | §10 コストドライバと打ち手 | Vercel 前提のコスト見積もり（あるなら） | Cloudflare の課金体系（Free / Pro / Enterprise）が異なる。プレビュー環境のコスト・本番デプロイの無料枠判定が変わる可能性がある | Cloudflare の Free / Pro 定価表を踏まえ、§10 のコストシミュレーションを再計算。Free 枠内に収まることを確認して通す |
| `/docs/02_requirements/prd.md` | §10 環境変数 / §13 未決事項 | プレビュー環境のデプロイ先が `実装着手時に決める` | wrangler.jsonc / wrangler.toml の設定項目がデプロイ先に依存する環境変数（Cloudflare Account ID / API token 等）が追加される | §10 に Cloudflare 固有の環境変数（`CLOUDFLARE_ACCOUNT_ID` / `CLOUDFLARE_API_TOKEN` / `CLOUDFLARE_WORKERS_KV_NAMESPACE_ID`）を追加。§13 で決定完了と記録 |
| `/docs/02_requirements/prd.md` | NFR-21 の説明 | 「プレビュー機能への依存は対象外」と明記 | wrangler CLI が Cloudflare 専用。プレビュー環境でも `wrangler dev` / `wrangler deploy` を使う。このレベルでの vendor lock-in が NFR-21 の対象外の境界か否かが曖昧 | NFR-21 を「アプリランタイム層（`src/*`・Next.js コード）が Cloudflare 固有 API に依存しない」に明確に書き換え。デプロイ・運用層（`wrangler.json` / GitHub Actions）の Cloudflare 依存は許容すると明示 |
| `/docs/02_requirements/user-story-map.md` | SP-1「操作レビュー」手順 | `E-22`: PR ごとの自動プレビューデプロイが「`SP-1` で確立」 | wrangler.json の追加・wrangler-action の設定・Cloudflare KV の初期化（ローカル開発用 miniflare 含む）が SP-1 の作業に入る。タスク粒度が変わる可能性がある | `E-22` の実装リストに「wrangler.jsonc 作成」「wrangler-action 設定」「miniflare 統合（ローカルテスト）」「本番デプロイの GitHub Actions 作成」を追加。必要に応じて SP-1 を分割する判断フラグを付ける |
| `/docs/02_requirements/roadmap.md` | M-1 の通過判定 | 「URL パラメータ・ロケール・キャッシュキー・配色が確定し ADR として記録される」 | wrangler.json / Cache Policy の設定が M-1 出口の決定項目に加わる | M-1 通過判定に「キャッシュ TTL の具体値（検索結果・詳細・画像）が確定し wrangler.jsonc に反映される」を追加 |

### 次点（SSOT の二重管理を避けるため）

| ファイル | 箇所 | 現在の記述 | なぜ更新が要るか | 更新案 |
|---------|------|----------|-----------------|--------|
| `/docs/03_design/infrastructure/infrastructure-design.md` | §0.2 正本の責務範囲・表 | 環境変数の正本が `prd.md` §10 | wrangler.jsonc が新たに環境構成を持つため、「wrangler.jsonc に書く項目」と「§10 環境変数に書く項目」の分け方を明記しないと重複管理になる | 表に 1 行追加: `wrangler.jsonc の設定項目 / デプロイ先固有設定 / wrangler.jsonc（変更なし・別ドキュメント化は不要） |
| `/docs/02_requirements/prd.md` | §0.1 正本の責務範囲 | `技術的意思決定 → docs/adr/` と明記 | インフラ選定（Cloudflare Workers・キャッシュ戦略・wrangler CLI）が ADR 対象になる可能性。現在 `prd.md` が「デプロイ先は決めない」としていたため ADR が未作成 | ADR として作成する項目を列挙するため、prd.md の表に「Cloudflare Infrastructure」と「Wrangler CLI as Primary Deployment Tool」の 2 ADR を予約行として追加。それぞれのタイミングを記録（M-1 出口 / M-1 終了時 の見込み） |

### チェック専用（修正不要・念のため確認）

| ファイル | 箇所 | 確認内容 | 結果 |
|---------|------|---------|------|
| `sprint-development-rules.md` | SD-1 / SD-2 の実装例 | SD-1（動作確認 URL）と SD-2（E2E テスト）は wrangler.json の指定如何で成立 | OK：wrangler deploy の URL が PR comment に自動挿入されることで SD-1 成立。E2E は wrangler dev + npm test で実行可能 |
| `user-story-map.md` | SP-1 含む E-22 の具体的手順 | 操作レビューが「`E-22` の設定が済むまでは開発サーバー起動で代替」と記載 | OK：miniflare でローカル開発できるため、プレビュー環境確立までの間も operability に問題なし |
| `prd.md` | TR-4（データアクセス層の技術スタック） | GitHub API の呼び出し層が Next.js App Router / Route Handlers で統一されているか確認 | OK：D-6 で PAT / OAuth 認証が確定しており、Workers Edge での実行可能性も確保 |

---

## 出力 2: 新規に追加すべき決定ログ ID

### 新規 D-n の提案（現在の open-questions.md では D-15 が最終）

| ID | 決定内容 | 記載方法 |
|---|---|---|
| **D-16** | **デプロイ先・エッジランタイム・キャッシュ基盤を Cloudflare に確定** | <決定条件> wrangler CLI を一次経路にし、npm scripts ではなく wrangler build-deploy パイプラインで本番反映。Cache API と HTTP Cache-Control の合わせ使いで外部キャッシュ層を実装。<根拠> D-5/D-7 は「決めない」とした時点での推奨が Vercel + 外部 KV（任意）だったが、Cloudflare の統合度（Workers 内で Next.js が即実行・Cache API ネイティブ）により、ここで確定。<移行策> `NFR-21` 維持のため、デプロイ先変更時のコスト：アプリコード 0 行変更（wrangler.json の diff のみ）。<記録日> 2026-08-18 |
| **D-17** | **`@opennextjs/cloudflare` adapter を採用し、Next.js 標準機能から Workers 環境への翻訳を一元化** | <内容> Data Cache / Incremental Static Regeneration / Image Optimization の動作が wrangler.json 設定で Workers 互換になることを前提に設計。adapter が提供する `cloudflare()` 関数でランタイム環境を統一。<依存> `D-16` / `D-13`（serverless 前提）に従属 |
| **D-18** | **キャッシュ戦略: `NFR-17` の Cache Port は「Next.js Data Cache」として、外部層は「HTTP Cache-Control + Workers Cache API」に割り当てる** | <内容> MVP は 2 層: ① Next.js Data Cache（サーバーレス内のプロセスメモリ・短 TTL）② HTTP Cache-Control（Workers Cache API・長 TTL）。外部 KV は Phase 2。<TTL 具体値> 検索結果 5 分・詳細 30 分（実測で調整・§13 未決事項クローズ）。<記録日> M-1 出口で確定 |

> ⚠️ **D-19 以降の予約**: GitHub Actions / wrangler-action の設定（D-19？）/ 環境ごとの KV namespace の分け方（本番・preview・ローカル：D-20？）は、実装時の具体設計が見えてから決定ログに昇格させる（現時点では未決事項のまま）。

---

## 出力 3: SSOT 重複の危険と切り分け案

### 新規ドキュメント `cloudflare-infrastructure.md` が既存ドキュメントと二重管理になるリスク

| SSOT の対象 | 既存正本 | 新規ドキュメントで書いてよいこと / すべきこと |
|------------|--------|-------------------------------------|
| **インフラに求める論理契約** | `infrastructure-design.md` (§2 論理構成 + §3.2 禁止リスト) | Cloudflare 固有の実装面（Workers の function 単位・bundler・edge location・Request API）は書く。ただし「§3.2 の禁止リスト（特定機能への直接呼び出し）を避ける抽象」の原則だけ参照して重複しない |
| **環境変数の一覧** | `prd.md` §10 | wrangler.json 内に埋め込む項目（KV namespace ID など）と環境変数として外部注入する項目（API token など）の分け方だけ書く。一覧そのものは `prd.md` に一元化 |
| **キャッシュ TTL の具体値** | `prd.md` §13（未決事項） | 「検索結果 5 分・詳細 30 分」の根拠（ユーザーのアクセスパターン・GitHub API rate limit・infrastructure-design.md §10 のコストとのトレード）を書く。値そのものは `prd.md` へ昇格させる |
| **ADR / 技術選定の理由** | `docs/adr/` | 「Cloudflare を選んだ理由」「@opennextjs/cloudflare adapter を選んだ理由」は ADR として独立させ、新ドキュメントからは ADR 番号で参照するのみ。新ドキュメント本体は「選定結果」とその設計パターンだけに絞る |
| **デプロイパイプライン（GitHub Actions）** | `docs/03_design/deployment-pipeline.md`（ドキュメント存在確認: 現在未作成） | 運用・デプロイ手順は別ドキュメント。新ドキュメントは「なぜこの手順か」の理由のみ参照・新ドキュメント本体は deployment/ 配下へ分離推奨 |
| **wrangler CLI の使い方** | `docs/04_development/` の CLI リファレンス（存在確認: 現在未作成） | 本書は「wrangler を一次経路にする設計判断」のみ。具体的なコマンド・設定ファイルの書き方は `04_development/wrangler-cli-guide.md` へ分離 |

### 新規ドキュメントの正本範囲の提案

```
docs/03_design/infrastructure/cloudflare-infrastructure.md

【書く範囲】
- Cloudflare Workers + @opennextjs/cloudflare の構成図（論理層と物理層の対応）
- キャッシュの 2 層設計（Data Cache vs HTTP Cache-Control + Workers Cache API）
- D-16 / D-17 / D-18 の決定内容の要約（詳細は ADR へ参照）
- environment.production / environment.preview の分け方（KV namespace など）
- 「後から Vercel・AWS Lambda へ切り替える場合のコスト」を付録で説明（NFR-21 の検証根拠として）

【書かない範囲】
- wrangler.json の具体的な記述方法（`04_development/wrangler-cli-guide.md` へ分離）
- GitHub Actions の yaml 記述（`.github/workflows/deploy.yml` の comment 欄に理由を書く）
- 環境変数の一覧（`prd.md` §10 が唯一の正本）
- ローカル開発での miniflare 起動方法（README / 開発ガイド へ）
```

---

## 出力 4: `SP-1` との責務分界案

### 現在の `SP-1` 構成（user-story-map.md §5.3）

```
SP-1: 検索して一覧が出る
含む: US-6, US-11, E-1, E-2, E-5, E-6, E-7, E-8, E-22
見積もり: sp:8
```

### Cloudflare 採用で追加される作業と分類

| 作業項目 | 内容 | SP-1 に含める | 別 Issue に分割 | 理由 |
|---------|------|-------------|----------------|------|
| **wrangler.json の作成** | ① プロジェクト設定（account ID・zone ID）② キャッシュ TTL ③ KV namespace 定義 ④ 環境分離（本番・preview） | ✅ 含める | — | E-22（プレビューデプロイ設定）の必須前提。プレビュー環境の確立と不可分 |
| **GitHub Actions ワークフローの作成** | ① wrangler-action による自動デプロイ ② PR comment での preview URL 通知 ③ 本番マージ時の自動反映 | ✅ 含める | — | E-22 の実装そのもの。操作レビューの「PR のプレビュー URL を開く」段階を成立させるのに必須 |
| **ローカル開発環境での miniflare 統合** | `npm run dev` で miniflare が起動し、Workers 環境での動作を模擬 | ✅ 含める | — | テスト基盤（E-11・SP-4）の前提。開発サーバーで動かすには wrangler dev 互換の環境が要る |
| **Cache Policy の設定・テスト** | ① NFR-17 の Cache Port 実装 ② HTTP Cache-Control ヘッダ検証 ③ キャッシュキーの命名（E-3） | ✅ 含める | — | SP-1 の操作レビュー手順「2 回目の検索が外部リクエストを発生させない」を成立させるために必須 |
| **@opennextjs/cloudflare adapter の導入・動作確認** | ① adapter 追加 ② Next.js 16 の標準機能（Server Components・ISR・Image Optimization）が Workers 上で動くことを確認 ③ 必要な polyfill / shim の追加 | ✅ 含める | — | TR-5（shadcn/ui × Next.js 16 互換性）と同型の「採択技術が実装時に動くか」の検証。SP-1 出口の ADR 予約に含まれる（D-17） |
| **CI の初期構成** | テストが走り、Lighthouse ゲートが動く（E-12） | ✅ 含める | — | E-11 / E-12 により既に SP-4 の預き荷物として扱われているが、wrangler build が通ることは SP-1 で確認必要 |
| **環境変数の初期値設定** | `.env.example` / `.env.local`（開発用）/ GitHub Secrets（本番用） | 🤔 実装タスク自体は小さいが、確定の要/不要？ | — | `D-16` / `D-18` で環境変数リストが確定する時期と連動。SP-1 出口で「どの変数が必須か」まで確定させる（下記の判定） |
| **本番デプロイのホットスタンバイ・ロールバック手順の確立** | wrangler publish；ロールバック時の手順（git revert + 自動再デプロイ？） | ❌ 別 Issue へ | 別 Issue（例：「デプロイパイプラインの運用ルール」） | D-15（人手ゼロの自動化）の確認だが、プレビュー環境確立とは独立。M-2 以降の運用検討として後回し |
| **Cloudflare Workers Analytics Engine（オプション・観測用）** | アクセスログ・エラーログの取得（§14 の `D-14` 遵守確認） | ❌ 含めない | Phase 2 検討 | アプリに秘匿情報を記録しない設計が前提のため、logging 戦略そのものは M-2 完成後に詳細決定 |

### 分割判定の基準（飼い手が確定する想定フラグ）

**SP-1 の sp:8 → sp:? に再見積もりが必要な候補**:
- ① wrangler.json・CI・Cache Policy（上記「含める」）の設定コスト
- ② @opennextjs/cloudflare adapter × Next.js 16 の互換性確認（§13 未決事項 `TR-5` と統合）

現在の sp:8 では**プロジェクト骨格 + データアクセス層 + プレビュー環境確立**を見積もっている。Cloudflare 固有タスクが加わって sp を超える場合は、**「wrangler 環境構築」を `SP-1a`（end-to-end 前のセットアップ）として先行分割**する判断も選択肢。その場合 `user-story-map.md` §5.4 に分割根拠を明記。

---

## 出力 5: ADR に書くべき項目の提案

### 想定 ADR 一覧（2026-08-18 現在の未決事項が決定時に起票）

| ADR 番号 | タイトル | 対応要件 | 記載時期 | 置き場所（既定：`docs/adr/`） |
|---------|--------|---------|--------|-------------------------|
| **ADR 0002**（推定） | Cloudflare Workers + @opennextjs/cloudflare を採用する | D-16 / D-17 / TR-4 / NFR-21 | M-1 終了時（SP-1 以降で動作確認） | `docs/adr/0002-cloudflare-infrastructure.md` |
| **ADR 0003** | キャッシュ戦略: 2 層設計（Data Cache + HTTP Cache-Control + Workers Cache API） | D-18 / NFR-5 / NFR-17 / NFR-18 | M-1 出口（E-3 / SP-5 完了時） | `docs/adr/0003-cache-strategy.md` |
| **ADR 0004** | wrangler CLI を本番デプロイの一次経路にする（GitHub Actions 統合） | D-15 / D-16 / INF-4 | M-1 〜 M-2 間（E-22 / SP-1 完了時） | `docs/adr/0004-wrangler-deployment-pipeline.md` |
| **ADR 0005** | @opennextjs/cloudflare adapter での Server Components 実行モデル | D-13 / TR-4 / NFR-3 | M-1 終了時（実装結果の記録） | `docs/adr/0005-server-components-on-workers.md` |

### ADR 共通構成（0001-ui-stack.md に倣った §節）

```markdown
# ADR 000n: {タイトル}

- **状態**: Proposed / Accepted / Superseded
- **日付**: 2026-08-?? JST
- **対応要件**: {対応する FR-n / NFR-n / D-n / E-n}
- **関連**: {参照する既存ドキュメント / ADR}

## 1. 文脈
（現状・なぜこの決定が必要か・制約条件）

## 2. 決定
（最終決定・採用したもの・採らなかったもの）

## 3. 理由
（なぜこれを選んだか・トレードオフ・代替案の評価）

## 4. 結果（この決定がもたらすもの）
- 良い方向
- トレードオフ・リスク
- 後続タスク

## 5. 未確認事項 / 検証予定
（開発中に確認すべき前提・実装時の詳細設計）

## 6. 参照
（関連 ADR・ドキュメント・Issue）
```

### ADR 0002 の節見出し案（Cloudflare インフラ）

```markdown
## 1. 文脈
- D-5/D-7 で「決めない」としていた理由
- Cloudflare Workers の統合度がもたらす利点（Cache API ネイティブ・wrangler との一体性）
- NFR-21「特定 PaaS への依存を最小化」との折り合い

## 2. 決定
- Cloudflare Workers + @opennextjs/cloudflare adapter
- デプロイ先: Cloudflare Pages（or Workers?・要確認）
- 本開発サーバー: wrangler dev（miniflare）
- 環境分離: production / preview（preview は PR ごとの自動デプロイ）

## 3. 理由
- 代替案（AWS Lambda・Vercel）との比較表
- キャッシュ API がネイティブ（外部 KV 依存を Phase 2 に遅延可能）
- 開発環境と本番環境の一貫性（miniflare で local 動作確認可能）
- コスト試算（Free 枠内に収まることを確認）

## 4. 結果
- 良い方向: キャッシュ層が Workers 内で閉じる / NFR-17 の実装単純化
- トレードオフ: wrangler CLI への依存度上昇（D-15 の「人手ゼロ」を wrangler が支える）
- 移行コスト: wrangler deploy 先を変更する場合、wrangler.json のみ変更（アプリコード無変更）

## 5. 未確認事項
- @opennextjs/cloudflare × Next.js 16 の互換性（TR-5 と統合）
- Data Cache が Workers のfunction boundary を跨ぐ場合の有効期限
- Cloudflare Pages の Build Integration（worker routes の自動反映）

## 6. 参照
- D-16 / D-17 / D-18
- NFR-21 / INF-5
- infrastructure-design.md §2 / §3.2
- ADR 0003（キャッシュ戦略）
```

---

## 付録: 検査項目チェックリスト（実装フェーズ）

実装着手時に確認すべき整合性ポイント:

- [ ] wrangler build が通り、workers environment で next start / next dev と同じコードパスを通るか
- [ ] NFR-21「特定 PaaS 固有 API に依存しない」を破るコードパス（例: `runtime === 'edge'` の条件分岐）が app/ に混在していないか（adapter がすべてを吸収するか）
- [ ] E-22 の PR comment に preview URL が自動挿入されるか（wrangler-action + comment step）
- [ ] キャッシュキー（NFR-18）が Cloudflare Workers での key format と一致するか（URL pathname vs full URL など）
- [ ] D-14「ログに秘匿情報を出さない」が Workers のRuntime Log / Analytics Engine に適用されているか

### `cli_autonomy` — 主張
<sub>2026-08-18T11:34:11+09:00</sub>

## D（主担当）: CLI 一次経路の具体形

### 0. 結論
**Workers Builds は採らず GitHub Actions + `cloudflare/wrangler-action` に一本化する。人間の GUI 作業は「トークン発行 1 回 + そのトークン値を 2 箇所へ貼る」の計 3 タッチに圧縮できる。** Cloudflare MCP（本セッションで利用可能な `mcp__Cloudflare_Developer_Platform__*`）は書き込み系（`d1_database_create` 等）を一切使わず、読み取り系（`search_cloudflare_documentation` / `workers_get_worker_code`）のみ CP-2 確認・障害調査用に残す。

### 1. ブートストラップ順序（人間 → Claude）

**人間（H-1、3 分、A-6 相当の一度きり）**
1. Cloudflare Dashboard → My Profile > API Tokens → 「Edit Cloudflare Workers」テンプレートから 1 本目のトークンを発行（`research.md` §2.3 のスコープ = Workers Scripts:Edit + Account Settings:Read。KV/R2/D1 を使うなら該当 Edit 権限も追加）
2. 同じトークン値・Account ID を **2 箇所** に貼る（コピペのみ、CLI 実行は不要）:
   - GitHub リポジトリ Settings > Secrets and variables > Actions > New repository secret（`CLOUDFLARE_API_TOKEN` / `CLOUDFLARE_ACCOUNT_ID`）
   - Claude.ai スケジュールタスク環境変数設定（同名 2 つ）

→ **人間の作業はここで完全終了**。以降は Claude が非対話で完結する。

**Claude（クラウドセッション、非対話）**
```bash
export WRANGLER_SEND_METRICS=false
export WRANGLER_SEND_ERROR_REPORTS=false
npx wrangler@4.123.0 whoami                       # 疎通確認（token/account_id が env にあれば通る）

# リソース作成（NFR-17 のキャッシュ実装先が確定してから。R2 推奨・KV は OpenNext 非推奨）
npx wrangler r2 bucket create gem-hunter-cache
npx wrangler d1 create gem-hunter-tagcache --json  # DOSharded/D1NextTagCache の受け皿

# wrangler.jsonc に出力 ID を反映してコミット（IaC as code。ID は MCP 経由ではなく CLI 出力から拾う）

npx wrangler versions upload --env preview --preview-alias "sp1-bootstrap"
# → stdout に Preview URL が出る。SP-1 の時点でこれを PR 本文に貼れば SD-1 を満たす（CI 不要）

printf '%s' "$SOME_SECRET" | npx wrangler secret put SOME_SECRET --env preview
printf '%s' "$SOME_SECRET_PROD" | npx wrangler secret put SOME_SECRET  # --env なし = production
```

### 2. トークンの供給先は 2 箇所、人間作業は 3 回（重複ゼロにはできない）

| 供給先 | 誰が設定 | クラウドから自律設定可能か |
|---|---|---|
| ① Claude Code クラウドセッション env | 人間（Claude.ai 環境設定 UI） | 不可（`env-vars.md`: GH_TOKEN と同じブートストラップ問題の系譜。セッション env への書き込み自体が人間操作） |
| ② GitHub Actions Secrets | 人間（GitHub UI） | 不可。`env-vars.md` 冒頭注記どおり `actions/variables` 系 API はクラウドから 403。**これは secrets API にも及ぶ**（`gh secret set` も同じ `repos/{o}/{r}/actions/*` 経路であり、GitHub MCP にも secret 書き込みツールが存在しない＝B ではなく構造的制約）。ローカル実行セッションなら `gh secret set CLOUDFLARE_API_TOKEN -R kai-kou/gem-hunter` で自律化できるが、本プロジェクトはクラウド運用が前提 |

→ **恒久的に自律化できない人間タッチは 3 回**（① ② への値貼り付け 2 回 + Cloudflare 側でのトークン発行 1 回）。`user-confirmation-minimization.md` H-1 相当として `A-6` 扱いが妥当（アカウント権限が物理的に必要）。2 本目以降のトークン（ローテーション）は `POST /accounts/{id}/tokens` を Claude が非対話で発行できるので、①②への **再貼り付けだけ** が毎回の人間作業（発行そのものは自律化できる）。

### 3. PR プレビュー URL を PR 本文に貼るまでの完全経路

```yaml
# .github/workflows/deploy-preview.yml（概形）
on:
  pull_request:
jobs:
  preview:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci
      - name: Deploy preview version
        id: deploy
        run: |
          npx wrangler versions upload --env preview \
            --preview-alias "pr-${{ github.event.pull_request.number }}" \
            2>&1 | tee wrangler-out.log
          # フィールド名未確認（research.md §8-3）→ WRANGLER_OUTPUT_FILE_PATH に依存せず
          # stdout の正規表現マッチで URL を抽出する（スキーマ非依存で頑健）
          URL=$(grep -oE 'https://[a-zA-Z0-9.-]+\.workers\.dev' wrangler-out.log | head -1)
          echo "url=$URL" >> "$GITHUB_OUTPUT"
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
      - name: Comment preview URL on PR
        run: gh pr comment ${{ github.event.pull_request.number }} --body "Preview: ${{ steps.deploy.outputs.url }}"
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}   # Actions既定トークン。Cloudflare認証情報は不要
```

**フィールド名未確認への吸収策**: `WRANGLER_OUTPUT_FILE_PATH` の ND-JSON を主経路にしない。**stdout の URL 正規表現抽出を主経路にする**（wrangler は常に人間可読な URL を標準出力に出す設計であり、ここが変わる可能性は低い）。ND-JSON は「取れたら儲けもの」の監査用ログとして並置し、初回 CI 実行で実物フィールド名を確認したら段階的に主経路化する（`docs/01_research/infra/20260818-cloudflare-research.md` §8-3 の潰し方どおり）。

PR コメントではなく **PR 本文更新**（`SD-1` は「PR 本文に URL」と明記）にしたい場合は `gh pr edit ${{ number }} --body-file` で既存本文 + URL セクションを合成する（同じ `GITHUB_TOKEN` で足りる）。

### 4. Workers Builds を採らない判断は妥当か

妥当。理由は「GUI が要る」だけではない:
- ビルド時間 3,000 分/月の無料枠を捨てる代償は小さい。GitHub Actions 側にも Private リポジトリで 2,000 分/月の無料枠があり、デプロイジョブ自体は wrangler upload のみで数十秒〜数分（重い `next build` を含めても Actions 側の枠で十分吸収できる規模）
- Workers Builds の PR コメント機能は **beta**（research.md §2.6）で URL 形式・フィールドの安定性が Actions 経由より低い可能性がある。CI パイプラインを 1 系統（GitHub Actions）に統一した方が `SD-2`（E2E をどのジョブで回すか）とも一体化しやすい
- **INF-20**（デプロイのトリガーは git push/マージのみ）を GitHub Actions が最も素直に体現する。Workers Builds でも git トリガーは満たすが、初回接続が GUI 必須という非対称性がある以上、CLI 一次方針との整合を優先する

### 5. Cloudflare MCP をどう扱うか

**「MCP よりも CLI」は「MCP を書き込みに使わない」と解釈する。読み取り専用の確認用には残す価値がある。**

- 現在のツールリストを見ると、MCP は元々 **デプロイ・シークレット投入・versions upload の等価物を持たない**（`workers_list` / `workers_get_worker` / `workers_get_worker_code` は読み取りのみ）。つまり「CLI か MCP か」の選択が発生するのは D1/KV/R2 の **リソース作成**（`d1_database_create` 等、書き込み系が存在する）だけ
- そこは **CLI で統一**（`wrangler d1 create` 等）を推奨。理由: リソース ID は `wrangler.jsonc` に手で反映してコミットする必要があり、MCP で作ってもこの反映作業は消えない。むしろ「作成コマンドの出力 → そのまま設定ファイルへ」を bash 一本で完結できる CLI の方が IaC として正本が 1 つになる（MCP 経由作成だと「実体は MCP 操作ログ、設定は git」という二重の真実になりやすい）
- **残す価値がある部分**: `search_cloudflare_documentation`（CP-2: 料金・上限は変動するため実装直前に再確認する用途）、`workers_get_worker_code` / `workers_list`（デプロイ後に「実際に何が動いているか」を素早く覗く監査用途。`wrangler deployments list` でも代替できるが MCP の方が対話文脈に軽い）
- 結論: **Cloudflare MCP は完全に捨てない。書き込みゼロ・読み取り専用ツールだけを CP-2 / 障害調査用に残す**、という運用ルールを `docs/rules/`（cf_platform 側の設計文書が妥当か）に明記することを提案する

### 6. E（本番デプロイ先）への意見

**今確定すべき（YES）**。プレビューと同一プラットフォーム（Cloudflare Workers）にする以外の合理的選択肢がない: `wrangler.jsonc` の `[env.production]` を切るだけで済み、追加の GUI 作業・追加のトークン種別が発生しない。異なるプラットフォームを選ぶと CLI 一次経路・シークレット管理・CI ジョブが二重化し `INF-4`（運用の手離れ）に反する。`D-7` を「Cloudflare Workers production env」で確定し、未決事項から外すことを推奨する。

### 7. SP-1（CI 前）でもプレビュー URL は出せるか

**成立する。** §1 のブートストラップ手順どおり、Claude がクラウドセッションから直接 `npx wrangler versions upload --env preview --preview-alias <branch-or-pr>` を叩けば、GitHub Actions が無くても即座に URL が得られる。`sprint-development-rules.md` の SP-1〜3 例外規定（プレビュー環境確立前は「開発サーバー起動」で代替可）よりも一歩進んで、**SP-1 の時点で本物のプレビュー URL を出せる**ので、代替手段に頼る必要すらない。ただし `INF-20`（デプロイトリガーは git push/マージのみ）は定常運用の契約であり、SP-1 のこの手動実行は「ブートストラップ期間の例外」と明示し、`SP-4`（CI 整備）以降は GitHub Actions 経由のみに一本化する、と Issue に 1 行残すことを推奨する。

## ラウンド 2

### `cf_platform` — 反論
<sub>2026-08-18T11:36:31+09:00</sub>

# cf_platform: Round 2 rebuttal

## 1. `privacy_lockin` への反論: incremental cache 未設定時の Data Cache 挙動と SP-5 の成立可否

**部分的に concede しつつ、結論（incremental cache = Cache Port 実装位置）には反対する。**

### ランタイム挙動（concede する点）

OpenNext incremental cache を設定しない構成では、Next.js の `fetch` Data Cache / `use cache` は **OpenNext のデフォルトである isolate 内メモリキャッシュ**にフォールバックする。これは `infrastructure-design.md` §6.1 が L2 の定義に自ら書いている「事業者依存（**インスタンス**/事業者のキャッシュ基盤）」のうち「インスタンス」側そのものであり、実質的には L1（リクエスト内メモ化）の寿命が少し延びただけの代物にすぎない。**Worker isolate はリクエストごとに再利用される保証がなく、同一 colo でも新しい isolate に着地すれば即座に消える**。したがって「Data Cache だけで SP-5（同じ検索で 2 回目は GitHub API を呼ばない・`x-ratelimit-remaining` が減らない）を証明する」のは **不安定で再現性がない**。ここは privacy_lockin の懸念の裏付けとして認める。

### しかし「incremental cache（R2/D1/DO）が必要」という結論には反対

SP-5 が要求しているのは「Data Cache が効くこと」ではなく「**同じ検索で GitHub API を二度叩かないこと**」。この 2 つはイコールではない。**HTTP レスポンスキャッシュ層（`wrangler.jsonc` の `cache.enabled: true` + Route Handler の `Cache-Control` ヘッダ）だけで、DB を一切持たずに満たせる**:

- リサーチ §4.1 の通り、Workers Caching は **2 層 tiered**（実質グローバル）かつ **リクエスト合体あり**。Route Handler / ページのレスポンスに `Cache-Control: public, s-maxage=N, stale-while-revalidate=M` を付ければ、GitHub API 呼び出し結果そのものがエッジでキャッシュされ、2 回目のリクエストは Worker の JS すら実行せずにヒットしうる（§2 参照）。これは isolate の生存に依存しないため、Data Cache より **むしろ堅牢**。
- privacy_lockin 自身が同じ投稿内で「Cache-Control ヘッダは RFC 9111 準拠で事業者非依存・`NFR-17` の対象外でよい」と整理している。この整理を採用するなら、**MVP で L3（外部 KV/R2）を入れる必要はまだない**（`infrastructure-design.md` §6.1 も L3 を「❌ 未採用」と明記）。SP-5 の動作担保は「Data Cache」ではなく「Workers Caching + Cache-Control」の組で説明し直すべき。

### 結論（Cache Port の実装位置への異議）

`open-next.config.ts` の incremental cache バックエンド選択を「Cache Port の実装位置」と決め打つのは時期尚早。**MVP の Cache Port 実装は「Route Handler が返すレスポンスに正しい `Cache-Control` を付ける薄いラッパー」で足り、`open-next.config.ts` に事業者依存バックエンド（R2/D1/DO）を書く必要は `infrastructure-design.md` §6.2 の L3 導入条件（レート制限起因のエラー実発生 / ヒット率不足の観測 / Phase 2 の静的配信要件）を満たすまで発生しない**。この境界を守れば `D-5` 追補（DB を持たない）と衝突しない。§6.2 の条件を満たした時点で初めて ADR とともに R2 incremental cache を検討すればよく、今の設計判断としては不要（YAGNI）。

---

## 2. `cost_guard` への同意 + ランタイム視点の補足（CPU への影響）

**cost_guard の指摘（キャッシュヒットもリクエスト課金 = レート制限対策とコスト対策は Cloudflare では完全には同一の打ち手ではない）は正しい。** ランタイム観点から 1 点補足する。

- リサーチ §3.2 は「CPU 時間はキャッシュミス時のみ課金」と明記している。これは裏を返すと、**Workers Caching のヒットは Worker isolate 自体は起動するが、キャッシュ検索 → 即返却という極めて軽い処理で完結し、実測 CPU はほぼゼロ**（≪ 10ms）ということ。つまり `A` の CPU 10ms 制約に対しては、**キャッシュヒット率を上げることは依然として極めて有効な打ち手**であり続ける — cost_guard の指摘は「リクエスト数課金」の話であって「CPU 課金 / CPU 上限」の話ではない、という軸の分離を明確にしておきたい。
- まとめると Cloudflare では **キャッシュヒット率向上が効くのは「CPU-ms（`A` の Free 上限 / Paid の従量コスト）」と「GitHub レート枠（`NFR-7`）」の 2 つ**で、**「リクエスト数そのもの（Free の 10 万/日・Paid の $0.30/百万）」には効かない**という cost_guard の三分割に完全同意する。`infrastructure-design.md` §10.2 の「同じ打ち手」という一枚岩の記述は、Cloudflare 選定時に上記 3 軸へ分解して書き直すべきという点も同意する。

---

## 3. 自分の i18n 提案（middleware なし `redirect()`）への未確認リスクとフォールバック

**未確認のまま `SP-2` に組み込むリスクは認める。フォールバックを 1 つ提示する。**

`next-intl` の現行版がミドルウェアレスのルーティング構成を公式サポートしているかは Round 1 で明記した通り未検証。この不確実性を SP-2 着手直前まで持ち越さないためのフォールバック:

> **`next-intl` のルーティング機能（`createNavigation` / `routing.ts` の middleware 連携部分）は使わない。** ロケール切り替えは自前実装に閉じる — ① URL 構造は `app/[locale]/...` のファイルシステムルーティングのみで表現 ② `/` へのアクセスは middleware ではなく **ルート `app/page.tsx`（Server Component）から `redirect()`** で処理（Round 1 提案どおり）③ メッセージカタログ・フォーマッティング（複数形・日付等）だけを `next-intl` の **非ルーティング API**（`NextIntlClientProvider` + `useTranslations` / `getTranslations`）で使う。これらは middleware 非依存で動作する（Provider ベースの通常の RSC/CSR API であり、公式ドキュメント上もルーティング機能と分離されているコア機能）。

この分割により、「`next-intl` のミドルウェアレス構成が現行版で未サポートだった」場合でも **ルーティング部分を自作しているので影響を受けない**。逆に将来 `next-intl` が正式にミドルウェアレスルーティングをサポートすれば、自作 `redirect()` ロジックを `next-intl` 標準に置き換える移行コストは小さい（ロケール判定ロジックの置き場所が変わるだけで `proxy.ts` は依然として使わない）。**`SP-2` 着手前に context7 で `next-intl` の現行版ドキュメントを一次確認し、この分割が本当に必要か（標準機能で足りるか）を確定させる**タスクを Issue に残すことを推奨する。

### `cost_guard` — 反論
<sub>2026-08-18T11:37:15+09:00</sub>

# cost_guard — Round 2（rebuttal）

## 1. `privacy_lockin` の OpenNext incremental cache（R2 + D1 tag cache + DO queue）案への反論

**構造的な位置づけ（Cache Port の実装先として `open-next.config.ts` が適切）には同意する。** ただし「今それを R2/D1/DO で埋めてよいか」は別の判断で、コスト面では **反対**。

### (a) 内部矛盾を指摘する
`privacy_lockin` は自分の round 1 の A への一言で「Free 継続の副次的利点 = 支払い方法を登録しない限りアカウントに課金 PII（カード情報）が乗らない」と書いた。ところが同じ投稿の B 回答では **R2 を Cache Port の実装先として推す**。研究メモ §3.1 は R2 について明記している: 「🔴 有効化に支払い方法の登録が必要」。つまり R2 を採用した瞬間、その「副次的利点」は自分で潰すことになる。両立しない。

### (b) 未確認のコストリスクを 3 製品分に増やす
- **R2**: 超過時に Free 相当で止まるか課金されるかが研究メモ §3.1・§8-6 で **未確認**。
- **D1**: 書き込み枠 10 万行/日（Free）。低トラフィックの tag cache なら足りる可能性は高いが、超過時の挙動は研究メモに記載なし。
- **DO（Durable Objects）**: 研究メモ §3.1 の無料枠表に **項目自体が存在しない**。`DOShardedTagCache` を使うなら DO 自体の料金・無料枠・超過挙動を **まだ誰も一次情報で確認していない**。`INF-2` の判定条件（「超過時は課金ではなく停止に倒す設定になっている」）を満たすかどうか、答えようがない状態でアーキテクチャに組み込む提案になっている。

`infrastructure-design.md` §6.2 は L3（外部 KV）採用の判定条件を明示している——①レート制限起因のエラーが実利用で発生 ②ヒット率不足で `INF-2`/`NFR-7` を満たせない ③Phase 2 の配信要件、の **いずれかを観測してから ADR を起票する**。gem-hunter はまだ MVP 前で、いずれの条件も観測されていない。R2/D1/DO を「Cache Port の実装先として今から確定する」ことは、この §6.2 のゲートを **先取りして無効化する** ことに等しい。

### (c) A-6 が何件増えるか（数える）
現行の Round 1 で私が挙げた A-6 は 2 件（① Paid 切替の事前承認ライン ② 月額撤退ライン）。ここに R2 を足すと:
- **③ R2 有効化＝支払い方法の登録**（研究メモ §3.1）が新規の A-6 になる。これは Workers Paid ($5/月) への加入とは **別のトリガー**（R2 は Workers の課金プランと独立して支払い方法登録を要求する）。つまり①のPaid承認をもらっても③は別途必要。
- D1 単体は支払い方法登録が明記されていないため A-6 が増えるとは断定しない（要確認）。
- DO は無料枠自体が未確認のため、採用するなら **その前に一次情報リサーチが要る**（B/C分類の「実装 Issue」であり、いきなり A-6 相当の判断を仰ぐ話にすらまだ到達していない）。

**結論**: R2/D1/DO を今 Cache Port の実装先に確定すると、A-6 が最低 1 件（③）増え、かつ DO は判定不能なリスクを抱えたまま設計に組み込むことになる。**`open-next.config.ts` という「差し替え可能な1箇所」構造そのものには賛成しつつ、中身（R2/D1/DO の実装）は §6.2 のトリガーが発火するまで空けておく**のが `INF-2` と整合する。MVP のキャッシュ実装は Cache-Control ヘッダ + Workers Caching（`wrangler.jsonc` の `cache.enabled`、支払い方法不要）で足りるはずで、これは `privacy_lockin` 自身が「NFR-17 の対象外でよい」と整理した層と同じもの。

## 2. `cli_autonomy` の「GUI タッチ3回」と自分の A-6 依頼2件 — 合計は1回のやり取りに収まるか

**性質が違う2種類のカウントなので単純合算ではないが、ユーザーから見た「今回まとめて対応してほしいこと」としては合計5点になる。1回のメッセージには収まる。**

内訳:
| # | 種別 | 内容 | 判断が要るか |
|---|---|---|---|
| 1〜3 | 手続き（`cli_autonomy` 分） | トークン発行 1 回 + 値貼り付け 2 箇所 | 判断不要・作業のみ |
| 4 | 判断（自分の①） | Paid 切替の事前承認 | Yes/No |
| 5 | 判断（自分の②） | 月額撤退ラインの実額 | 数値回答 |

`user-confirmation-minimization.md` §3 item 8 の「選択肢は最大2つ・推奨明示」は **質問1つあたりの制約**であり、1メッセージに含められる質問の数を制限していない。したがって:
- 手続き 1〜3 はそのまま指示文として並べる（判断を求めない）。
- 判断 4 は「Paid へ確認なしで切替てよいか（推奨: Yes・理由1行）」の二択で `AskUserQuestion` の1問。
- 判断 5 は自由記述（金額）だが、選ばせる形にするなら「撤退ラインの目安: $10 / $20（推奨: $10・Free超過は稀な想定のため）」の二択に変換できる。

→ **1回の `AskUserQuestion` 呼び出し（2問・各最大2択・推奨明示）+ 手続き3点の指示** を1メッセージにまとめれば、`user-confirmation-minimization.md` の書式要件を満たしたまま1往復で完結する。5点あるからといって複数回に分割する必要はない。ただし §1 で指摘した「R2 有効化＝支払い方法登録」を仮に採用するなら、これが6点目（判断か手続きかは登録先UIの形式次第）として同じメッセージに追加できるかは要検討——現時点では §1 の結論どおり R2 採用自体を保留するため、この6点目は発生しない。

## 3. 自分の主張の曖昧点の解消: Paid切替は「誰が」「いつ」決めるか

`SP-1` は止まらない。整理すると2段階ある。

**段階1（Claude が自律・A-6 不要）**: SP-1 でのCPU ms実測・閾値判定（p95 > 7〜8ms またはバンドル > 3MB）は **支払い方法もWorkers Paid加入も不要**（Free のまま計測できる）。ここは `problem-investigation-protocol.md` の範疇で完結し、ユーザーの判断も操作も要らない。

**段階2（ユーザーが必ず実行・A-6・自律化不可）**: 閾値を超えたと判定した **その時点で初めて**、Workers Paid への加入（支払い方法登録）が必要になる。ここは研究メモ H-4 のとおり「支払い手段の登録はアカウント所有者の権限が物理的に必要」であり、**Round 1 で私が「事前承認があれば確認なしで自律的に切り替える」と書いたのは不正確だった**。訂正する: 事前承認（A-6依頼①）が変えるのは「切替の実行そのものをClaudeが自律で行えるか」ではなく、「閾値到達時に `status:waiting-user` で止めて A/B/C/D 分類からやり直すか、それとも即座に『登録してください、これだけで再開します』という具体的な1手だけを提示できるか」という **止まり方の質**。実行アクション（カード情報入力・Paidプラン加入クリック）自体は常にユーザーが行う。

これは §1 の反論とも整合する: R2 の支払い方法登録も、Workers Paid の支払い方法登録も、**その製品の必要性が実測で確定するまでは行わない**（前倒しで登録しない）。事前承認は「実測で確定したら即座にユーザーへ1点だけの具体的依頼を出してよい」という **通知の許可**であって、「Claude がカード登録を代行してよい」という **実行の許可ではない**（そもそも代行する手段がない)。

**したがって SP-1 の実行順序を明確化する**: ① Free のまま実装・実測 → ② 閾値内に収まれば Paid の話は不要のまま完了 → ③ 閾値超過が実測で確定した場合のみ、事前承認済みの1文言で `waiting-user`（A-6）を起票し、ユーザーの登録操作を待つ。SP-1 自体はこの③に到達しない限り止まらない。

### `docs_trace` — 反論
<sub>2026-08-18T11:37:17+09:00</sub>

# docs_trace Round 2 — ドキュメント突合と権威判定

## 問 1: キャッシュ実装の正面衝突（OpenNext incremental cache vs HTTP Cache-Control only）

### 権威は **既存ドキュメントで D-5 追補 / infrastructure-design.md §6.2 が明確に支持する**

**privacy_lockin 主張**: `open-next.config.ts` で `r2IncrementalCache` / `d1IncrementalCache` を設定し、ISR・`revalidateTag` のバックエンド を Cloudflare R2/D1 に寄せる（≒ persistent store 導入）

**cost_guard / cf_platform 主張**: HTTP Cache-Control + Workers Caching だけで MVP 完結。L2 cache（Next.js Data Cache）のみ。R2/D1 は Phase 2 以降。

### 既存ドキュメントの記述

**§A: D-5 追補（権威最上位・ユーザー明示決定・2026-08-17 記録）**
```
【D-5 追補】「DB を持たない」を MVP の都合ではなく設計原則に格上げする。
状態はクライアント側（localStorage / Cookie / URL）に寄せ、
サーバー側ストアを持たない構成を Phase 2 まで可能な限り貫く。
```

**§B: infrastructure-design.md §6.2「L3（外部 KV）を入れる判定条件」（権威：仕様・設計規約）**
```
「なんとなく不安だから」で入れない。以下のいずれかを【観測】したときに初めて検討し、ADR を起票する:
1. レート制限起因のエラーが実利用で発生した
2. キャッシュヒット率が想定を下回り、INF-2 または NFR-7 を満たせない
3. Phase 2 の静的データ配信（GR-5）で、配信物の置き場所が必要になった
```

**§C: infrastructure-design.md §6.1「キャッシュ層の 3 分類」（権威：設計規約）**
```
| L2 | Next.js のデータキャッシュ | ... | ✅ 採用。MVP の主役 |
| L3 | 外部 KV | 全インスタンス共有・永続的 | ❌ 未採用（D-5）。
                                         Cache Port の実装差し替えだけで入れられる状態に保つ |
```

### 権威順による判定（intent-gate-rules.md）

権威順: **ユーザー明示 > 仕様 > テスト > 現行コード**

1. **ユーザー明示**: D-5 追補（2026-08-17 記録）が「サーバー側ストアを持たない」と明言。これは最高権威。
2. **仕様**: infrastructure-design.md §6.1・§6.2 が L3「未採用」「観測条件なしに入れない」と明記。
3. **テスト**: SP-5 の操作レビュー「2 回目の検索が外部リクエストを発生させない」は HTTP Cache-Control 層だけで満たせる（L2 で十分）。L3 が必須ではない。
4. **現行コード**: 実装なし（まだ）。

### 結論

**既存ドキュメントは cost_guard / cf_platform を支持する**。privacy_lockin の「Cache Port は open-next.config.ts に実装する」案は、D-5 追補を読み違えている（「Cache Port の実装位置」≠「persistent store の採用」）。

🔴 **privacy_lockin への指摘**: 
- NFR-17 の Cache Port はデータアクセス層から事業者固有 KV を隔離するための **抽象** であり、その実装位置の具体化（`open-next.config.ts` など）ではない。
- D-5 追補が「サーバー側ストアを持たない」と格上げした今、Cache Port はあくまで「破棄可能なキャッシュ」の切り分け点として機能すべき。
- 「後から R2/D1 を差し込めるようにしておく」と「最初から R2/D1 を使う」は別物。前者なら NFR-17 の分界だけで足り、後者は D-5 追補に矛盾する。

---

## 問 2: Preview URL 要件（SD-1）と Free 初期値の両立

### 質問の意図

cost_guard が「Free 初期値 + 実測 CPU で判定」案を提示したとき、「それでも SD-1（全スプリント PR に開けるプレビュー URL が要る）は成立するか」。

### 既存ドキュメント (infrastructure-design.md §8 環境構成）

```
環境ごとの仕様（プレビュー環境のみ先行決定・D-11）:
- プレビュー環境: Cloudflare Workers Free で動作可能か？ → 【要実測】SP-1 で確認

本番環境: 支払い方法の登録（A-6）でオプション化される
```

### SD-1 と preview URL の依存関係

SD-1「動作確認できる状態で終わる」の定義:
- 「スプリントの PR には **開けるプレビュー URL** が貼られている」
- OR「出せない場合は理由とローカル起動手順を PR に書く」（妥協許容）

cost_guard の「Free 初期値」シナリオ:
1. **SP-1 で実測** して CPU ms / バンドルサイズ をプレビュー環境で確認
2. **その時点で「Free で十分か / Paid が必須か」を判定**

### 整合性の判定

✅ **両立する**。理由:

- cost_guard の「Free 初期値」は **プレビュー環境の初期構成** として合理的。
- SD-1 が求める「開けるプレビュー URL」は、**環境のランタイムコスト（Free/Paid）に依存しない**。Workers のランタイムが動けば URL は生成される。
- Paid 昇格の判定が「SP-1 実測後」でも、その時点までは Free でプレビュー URL を出力し続けられる。
- Paid 昇格が必要になった場合、cost_guard の「確認なしで Paid に切り替える」ルール（INF-2/INF-3 優先順位）に従えば、UI には影響なく、請求金額のみが変わる。

🔵 **付加情報**: D-11「プレビュー環境のデプロイ先だけは先行決定」は、本番先は未決のまま。プレビューの選定ガイド（Free/Paid の判定ロジック）が cost_guard で明確化されたことで、**D-11 は「決めない」から「実測に基づき自動判定」へ進化** する。これは破壊的変更ではなく、未決事項の詳細化である。

---

## 問 3: D-16 ～ D-18 の最終文言確定（ユーザー明示決定を権威として記録）

ユーザー明示決定（whiteboard の論点冒頭）:
1. インフラは **Cloudflare ベースで進める**
2. 既存 Cloudflare アカウントを使い必要リソース作成
3. **CLI（wrangler）を主経路にする**（MCP ではなく）

### 最終的な D-n 記録案

**D-16: デプロイ先・エッジランタイム・キャッシュ基盤を Cloudflare に確定**

```
ユーザー明示決定（2026-08-18）により、プレビュー環境・本番環境ともに
Cloudflare Workers + @opennextjs/cloudflare の構成で進める。
キャッシュ層は HTTP Cache-Control + Workers Caching (L2) で MVP 完結。
L3（R2/D1 等 persistent store）は D-5 追補の「未採用」を維持し、
観測条件（レート制限エラー発生 / ヒット率不足 / Phase 2）を満たしてから検討。
D-15「人手ゼロの自動化」の前提として、wrangler CLI を運用一次経路に統一し、
GitHub Actions + wrangler-action によるデプロイパイプラインを標準化する。
移植性（NFR-21）は @opennextjs/cloudflare adapter と wrangler.jsonc の分離で確保。
```

**D-17: @opennextjs/cloudflare adapter と wrangler.jsonc の採用基準**

```
OpenNext + adapter 単体では NFR-21（vendor lock-in 最小化）を破らない。
禁止対象は「app/ 配下のコードが Cloudflare 固有バインディング 
（KV/R2/D1/Cache API 等）を直接呼ぶこと」であり、
wrangler.jsonc の設定ファイルや Cache Port 内の 1 ファイル（Rate Limit / 
Incremental Cache）に閉じ込めるなら許容される。
違反判定の境界線は infrastructure-design.md §3.2「禁止リスト」を更新し、
以下を追加する:
  - getCloudflareContext() は Cache Port と Rate Limit 実装ファイルのみで呼ぶ
  - env.* バインディング（KV/R2 等）への直接アクセスを禁止
  - wrangler.jsonc / open-next.config.ts はアプリの実行時分岐条件にしない
移行時の チェックリスト（infrastructure-design.md §13）に 
「wrangler.jsonc と open-next.config.ts の破棄」を追加。
```

**D-18: キャッシュ戦略と TTL の初期値**

```
MVP は 2 層: (1) Next.js Data Cache（L2・プロセス内・短 TTL）
(2) HTTP Cache-Control + Workers Caching（公開 CDN・中 TTL）。
初期 TTL は検索結果 5 分・詳細 30 分（cost_guard の §8-6 未確認項目により調整）。
L3（R2/D1）は未採用。Cache Port（NFR-17）は「差し替え可能な 1 箇所」として
open-next.config.ts に集約させるか app 内に 1 ファイル として実装するかは
SP-1 の実装時に決め、ADR で記録する。
D-5 追補「サーバー側ストアを持たない」の原則を Phase 2 まで維持。
```

---

## 🔴 unresolved（他者の実測待ち）

- privacy_lockin への質問: invocation log の IP 含有有無 / Rate Limiting binding の課金有無 → **確定後に禁止リスト文言を更新**
- cost_guard の Billable Usage API 実装 → monitoring 手段確定までは cost_guard/cli_autonomy にしてほしい
- cf_platform の CPU ms 実測値（3MB バンドル / p95 CPU time）→ SP-1 未確認項目リストに明記し、SD-1 通過前に取得

### `cli_autonomy` — 反論
<sub>2026-08-18T11:38:16+09:00</sub>

## Round 2: rebuttal（`cli_autonomy`）

### 1. `privacy_lockin` の R2 + D1/DO incremental cache — CLI 手順の実測とINF-4判定

**結論: ステップは増えるが一時的（bootstrap）で完結し、`INF-4`（定常運用ゼロ）は破れない。ただし `privacy_lockin` に 1 点、重要な見落としを指摘する。**

前提として round 1 で私が示した「preview は per-PR で別 Worker を作らず、1 つの共有 preview Worker のバージョン群として扱う」設計を維持する限り、R2/D1/DO の bootstrap は **PR 数に比例しない**。増える具体コマンドは以下（すべて非対話・一度きり）:

```bash
npx wrangler r2 bucket create gem-hunter-cache-preview
npx wrangler r2 bucket create gem-hunter-cache-production
npx wrangler d1 create gem-hunter-tagcache-preview --json
npx wrangler d1 create gem-hunter-tagcache-production --json
npx wrangler d1 migrations apply gem-hunter-tagcache-preview --remote
npx wrangler d1 migrations apply gem-hunter-tagcache-production --remote
```
→ **+6 コマンド、+2 環境ぶんの `wrangler.jsonc` バインディング追記（1 回コミット）**。`DOShardedTagCache` を選ぶ場合は D1 の create/migrate 4 行が不要になり（DO namespace は `wrangler.jsonc` の `durable_objects` バインディング定義だけで初回デプロイ時に自動生成される）、**むしろ D1 案より CLI ステップは少ない**。ここは cost/design 側の判断材料として投げる。

定常運用（`INF-4` の射程）で人手が要る場面は探した限りゼロ: D1 のスキーマ変更（OpenNext のバージョンアップ時のみ発生・稀）は `wrangler d1 migrations apply` を **CI ジョブに 1 行入れておけば** デプロイのたびに自動追従する。R2 バケットは保守レス。よって `INF-4` は守れる、という round 1 の私の立場を維持する。

**ただし `privacy_lockin` への指摘（見落とし 1 点）**: 研究メモ §3.1 に **「R2 は有効化に支払い方法の登録が必要」**（🔴）とある。これは Free プラン内の話であり、CPU ms とは無関係。つまり **R2 + D1/DO 案を採用した瞬間、`cost_guard` の CPU 実測ゲートを待たずに `A-6`（カード登録）が発生する**。「Workers Caching + Cache-Control のみ」（round 1 §5 の 1 行構成）なら A-6 はゼロのまま `SP-1` に進める。この非対称性は `privacy_lockin` の主張には明記されていなかったので、`§14` の A-6 依頼事項に **「R2 有効化」を独立した 3 件目の A-6 として追加**することを提案する（`cost_guard` の 2 件と束ねて一度にユーザーへ確認するのが CP-6 上も効率的）。

### 2. `cost_guard` の Free→Paid 判定式 — CLI 側で何が変わるか

**support（大筋で支持）+ 1 点訂正。** `cost_guard` の「実測ゲート → 判定基準に従い確認なしで切り替え」は CLI/自律運用の観点からもそのまま成立する。**訂正点**: Free→Paid の切り替えそのものは **wrangler / API に「プラン変更」コマンドが存在しない**（研究メモにも記載なし。既知の Cloudflare API にも billing plan upgrade のエンドポイントはなく、Dashboard の課金画面が唯一の経路）。つまり Claude 側が「自律的に切り替える」とは正確には **「切り替えの前提条件を先に全部整えておき、人間のカード登録クリック 1 回だけを残す」** という意味になる。

Claude が非対話で完結できること:
- `wrangler.jsonc` に **安全キャップとして** `"limits": {"cpu_ms": N}` を追加する（Paid化で Free の構造的ハードキャップ = HTTP 1027 停止が消えるため、`cost_guard` が指摘した「denial-of-wallet 対策」を **Paid切替と同じコミットで即座に埋める**。これは switch の *必須条件* ではなく Claude が能動的に足す残余リスク対策）
- デプロイコマンド（`versions upload` / `versions deploy`）は Free/Paid で **一切変わらない**
- APIトークンのスコープも Free/Paid で変わらない（再発行不要）— `whoami` 疎通確認だけで Paid 移行後も継続動作を確認できる

Claude が完結できないこと（`A-6` として残る）:
- 支払い方法の登録そのもの（Dashboard 操作）
- 「Free → Paid」への切替ボタン押下自体（API 経路が存在しないため CLI では代行不可。ここは `cost_guard` の想定より不可分な人間作業）

→ **`cost_guard` の①番の依頼文言を微修正することを提案する**: 「確認なしで切り替えを進めてよいか」ではなく、「実測 NG が確定したら、Claude は `limits.cpu_ms` 設定・監視体制を確認なしで先に整え、**カード登録の実行だけ**を A-6 として即時通知する（それまでの準備作業に承認は不要）」という書き方の方が、CP-6 の「判断は自律・操作だけが人間」という原則に忠実になる。

### 3. 自分の round 1 主張の補強: stdout 正規表現抽出の失敗検知

`SD-1`（PR に開けるプレビュー URL があること）を **サイレントに欠落させない**ため、抽出失敗を CI の赤 X として扱う具体形を出す。

```bash
URL=$(grep -oE 'https://[a-zA-Z0-9.-]+\.workers\.dev' wrangler-out.log | head -1)
if [ -z "$URL" ]; then
  echo "::error::wrangler versions upload did not emit a *.workers.dev URL (stdout format may have changed) — see wrangler-out.log"
  exit 1   # ジョブを fail-closed にする。空URLのままPRコメントへ進ませない
fi

# 到達性チェック（プロパゲーションのラグを許容する軽いリトライ）
for i in 1 2 3; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "$URL") && [ "$code" -lt 500 ] && break
  sleep 5
done
[ "$code" -ge 500 ] && { echo "::error::preview URL returned $code after retries: $URL"; exit 1; }

echo "url=$URL" >> "$GITHUB_OUTPUT"
```

さらに **投稿後の自己検証**を追加する（コメント/本文更新そのものの失敗も拾うため）:
```bash
gh pr comment "$PR_NUMBER" --body "Preview: $URL"
gh pr view "$PR_NUMBER" --json comments -q '.comments[].body' | grep -qF "$URL" \
  || { echo "::error::posted comment did not persist the preview URL"; exit 1; }
```

round 1 で「ND-JSON は監査用に並置」と書いたが、これを **一次シグナルではなく検証専用**へ格下げし直す: ND-JSON のパース成功可否は warning のみで exit しない（フィールド名が不確定なため false negative でジョブを落とすリスクの方が大きい）。**fail-closed にするのは正規表現抽出（主経路）と URL 到達性・PR 反映確認（後段）だけ**、というのが round 2 での精緻化。これにより「URL が取れなかったのに緑で通る」経路は構造的に塞がる。

### `privacy_lockin` — 反論
<sub>2026-08-18T11:38:32+09:00</sub>

# privacy_lockin: Round 2 rebuttal / concession

## 1. R2 = NFR-17 実装位置という round1 の主張を撤回する（`cost_guard` / `D-5` 追補との衝突を認める）

**譲歩**: round1 で「OpenNext incremental cache（R2）が `NFR-17` Cache Port の実装位置そのものになる」と書いたのは踏み込みすぎだった。`cost_guard` は明示しなかったが研究メモ §3.1 に「R2 は **有効化に支払い方法の登録が必要**」とあり、これは `cost_guard` 自身が §3.3「Free plan のまま・支払い方法を登録しない」を **「最強のハードキャップ」** と位置づけた主張と正面衝突する。カードを登録した瞬間、`cost_guard` が拠り所にした構造的ハードキャップ（`HTTP 1027` で無課金停止）の前提そのものが揺らぐ。私自身も round1 で「Free 継続＝カード情報という PII をアカウントに乗せない」と書いており、R2 採用は **自分の主張と矛盾する**。

さらに `D-5` 追補「サーバー側はリクエストを処理して捨てるだけで、次のリクエストへ持ち越す状態を持たない」を厳密に読むと、R2 は **ライフサイクルルールで管理する永続オブジェクトストア** であり、Workers Caching のような TTL 秒単位のエッジキャッシュとは質が違う（`infrastructure-design.md` §6.1 の L3 と同格）。§6.1 は L3（外部 KV）を明確に「❌ 未採用（`D-5`）」としており、R2 も同じ扱いを受けるべきだった。

**選択（保留しない）**: **B「別の形で残す」を選ぶ**。理由:
- `NFR-17` の Cache Port（`get`/`set`/`invalidate` + TTL）は **gem-hunter が独自に持つアプリレベルの抽象**であり、OpenNext の incremental cache（Next.js の ISR/`revalidateTag` 機構そのもの）に必ずしも配線する必要がない。gem-hunter の検索結果ページは検索条件依存の動的レンダリングが主で、静的再生成（ISR）を前提にした設計ではない（`infrastructure-design.md` §6.1 は L2＝「Next.js のデータキャッシュ」を MVP の主役としており、ISR タグキャッシュの話とは別軸）。
- よって MVP の `NFR-17` 実装は **Workers Caching（`cache.enabled`）+ `Cache-Control` ヘッダ**（エッジ・TTL 秒単位・支払い方法不要・§5.4 の「キャッシュは全利用者で共有・一時的」という記述とも整合）に一本化してよい。`invalidate` はキー設計（TTL 短縮 or キャッシュキーへのバージョン接尾辞）で代替し、`revalidateTag` の永続タグストア（D1/DO）には踏み込まない。
- **R2（あるいは D1 の incremental cache 用途）を入れるのは `infrastructure-design.md` §6.2 の L3 判定条件（レート制限起因のエラーが実利用で発生 / ヒット率が想定を下回る）を **観測してから****。これは既存ドキュメントの L3 ゲートと完全に一致する運用であり、新規ルールを増やさずに済む。
- **新規提案**: R2 の有効化は「支払い方法の登録」を伴うため、§6.2 の判定条件を満たして L3 導入 ADR を起票するタイミングで、**`INF-2`/§10.3 の「課金設定変更は `A-6`」に明示的に紐づける**（現行の §10.3 はコスト上限の文脈でしか `A-6` に触れていないが、R2 有効化も同じ理由でユーザー承認が要ることを `docs/03_design/infrastructure/cloudflare-infrastructure.md` に一行追加すべき）。

「やはり R2 が要る」は選ばない。ISR タグキャッシュが本当に必要になった実測が出るまで、`D-5` の精神（サーバー側に持ち越す状態を最小化する）を守る側に倒す。

## 2. Cloudflare MCP 読み取り専用の残置に実害はあるか

`cli_autonomy` の提案（書き込み系はゼロ・読み取り系のみ残す）に **賛成する**。ロックイン / 監査の両観点で実害を見つけられなかった。

- **ロックイン（`INF-5`/§11 軸8「退避コスト」）への影響: ゼロ**。MCP の読み取り呼び出し（`search_cloudflare_documentation` / `workers_get_worker_code` / `workers_list`）は `app/` にも `wrangler.jsonc` にも **何の成果物も残さない**。§13 の移行チェックリストに MCP が一度も登場しないのはこのため — 消すものが最初から存在しない。事業者を差し替えても「MCP で何を読んだか」は移行作業に影響しない。
- **監査への影響: ほぼゼロ、ただし 1 点だけ運用規律が要る**。書き込みをしない以上、状態変更の監査ログという意味では対象外（変更していないので追う必要がない）。唯一の懸念は、**MCP の読み取り結果（例: 実際の namespace ID）をコードや `wrangler.jsonc` に反映せず「Claude が知っているだけ」の状態で進めてしまう二重の真実化**（`cli_autonomy` が D1/KV 作成の文脈で指摘したのと同型のリスク）。ここは「MCP で見た値は必ず `wrangler.jsonc` かコミットに落とす」という 1 行ルールで潰せる。
- **`INF-1` への影響: なし**。MCP が触るのは Cloudflare アカウント側の運用情報（Worker のコード・ログ一覧等）であり、`INF-1` が守る対象（gem-hunter の**エンドユーザー**の個人情報）とは別レイヤー。
- **ユーザー指示「MCP よりも CLI」との整合**: 指示の文言は「自律開発のため MCP ではなく CLI を主経路にする」— **理由が明記されている**（自律開発 = 非対話で完結する実行ループの主経路をどちらにするか、という話）。これは絶対禁止ではなく **優先順位の指定**であり、書き込み・デプロイ・シークレット投入という「自律開発の主経路」に該当する操作を CLI に一本化すれば指示の目的は満たされる。読み取り専用の確認利用は「主経路」ではなく補助であり、指示の射程外と読むのが自然（本プロジェクトの `CLAUDE.md` 自体が GitHub 操作で「MCP が一次経路・gh は当てにしない」という **同型の優先順位表現**を使っており、gh CLI を完全排除していないのと同じ構造）。
- **条件付き賛成**: `cli_autonomy` が提案した「運用ルールに明記する」は必須にすべき。書かないと「読み取りだけのつもりが、便利だからと書き込み系ツールへ範囲が広がる」スコープクリープが起きやすい（ロックインの本質的リスクは「便利な事業者固有機能に少しずつ依存が染み出す」ことなので、MCP の書き込み解禁も同じパターンで起こりうる）。境界は次項の grep 化と同じ発想で、**許可する MCP ツール名のアローリスト**（`search_cloudflare_documentation` / `workers_list` / `workers_get_worker` / `workers_get_worker_code` の 4 つのみ）をルールファイルに列挙し、それ以外（`*_create` / `*_delete` / `*_edit` / `*_query`）を使った形跡があればセルフレビューで検知できる形にする。

## 3. 自分の §3.2 追加提案の自己検証: grep 1 本で判定できるか → **できていなかった。書き直す**

正直に自己採点する。round1 の文言「`getCloudflareContext()` は Cache Port の実装ファイル 1 つと Rate Limit の実装ファイル 1 つの内部でのみ呼んでよい」は、**具体パスを 1 つも名指ししていない**ため機械検出できない。「1 つのファイル」という数量表現は grep のホワイトリストにできず、セルフレビューの精度は結局レビュアーの目視判断に戻ってしまう。これは自分が §3.2 に対して求めた「セルフレビューで機械的に当てる」という基準を、自分の追加提案自身が満たしていなかったということ。

**書き直し**: 具体パスをディレクトリで固定する。

> 追加規約: Cloudflare bindings（`getCloudflareContext()` の戻り値・`env.KV` / `env.R2` / `env.D1` / `env.RATE_LIMITER` / `env.CACHE` / `env.IMAGES` 等）へのアクセスは **`lib/infra/` 配下のファイルからのみ**行ってよい。`app/`（Server Component / Route Handler）・`lib/data/`（`NFR-16` のデータアクセス層）からの直接アクセスを禁止する。

**grep パターン（このまま CI / セルフレビューに組み込める）**:

```bash
# 違反候補: getCloudflareContext または env.<binding> への言及が lib/infra/ の外にある
grep -rnE 'getCloudflareContext\(|env\.(KV|R2|D1|RATE_LIMITER|CACHE|IMAGES)\b' \
  --include='*.ts' --include='*.tsx' app/ lib/ \
  | grep -v '^lib/infra/'
# 出力がゼロ行なら合格
```

新設 #7（`wrangler.jsonc`/`open-next.config.ts` を分岐条件にしない）も同様に書ける:

```bash
# 違反候補: Cloudflare 環境変数を条件分岐に使っている
grep -rnE 'process\.env\.(CF_|CLOUDFLARE_)|context\.env\.' \
  --include='*.ts' --include='*.tsx' app/ \
  | grep -v '^app/.*/lib/infra/'
# 出力がゼロ行なら合格
```

この 2 本を `tools/self_review_check.py`（`pre-pr-create-check.sh` が既に自動実行している）に足すことを実装 Issue として提案する。`lib/infra/` というディレクトリ名は round1 では存在しなかった新規の取り決めなので、`infrastructure-design.md` §3.2 に追加する際は **「Cloudflare bindings への唯一の合法アクセス経路は `lib/infra/` 配下」** という 1 行を先に明文化してから、上記 grep を機械ゲートとして添える順序にする。

## ラウンド 3

### `lead` — 合意
<sub>2026-08-18T11:41:14+09:00</sub>

# lead: 合意と対立の整理（Round 3）

## 1. 合意に達した点

| # | 合意事項 | 経緯 |
|---|---|---|
| 1 | **ランタイムは `@opennextjs/cloudflare` + Workers 一択**。`next-on-pages` は npm 上で deprecated、静的エクスポートは `NFR-9`（トークンをサーバーに隠す）と衝突 | 全員異論なし |
| 2 | **`next` は 16.2.11 以上にピンする**（アダプタ 1.20.2 の peerDep 実測値） | `cf_platform` 提示・異論なし |
| 3 | 🔴 **MVP のキャッシュは「HTTP `Cache-Control` + Workers Caching」のみ。R2 / D1 / DO / KV は採用しない** | `privacy_lockin` が round 2 で R2 案を **撤回**。`cost_guard`（R2 有効化＝支払い方法登録が必要で Free のハードキャップが崩れる・DO は無料枠自体が未確認）、`cli_autonomy`（R2 採用は CPU 実測を待たずに `A-6` を発生させる）、`docs_trace`（`D-5` 追補と §6.2 の L3 ゲートが「観測してから」と明記）が一致 |
| 4 | **`NFR-17` Cache Port は維持する**が、実装位置は `open-next.config.ts` ではなく **`lib/infra/` 配下の薄いラッパー**（`Cache-Control` の付与とキャッシュキー生成に責務を限定） | `privacy_lockin` の譲歩案 B を採用。`docs_trace` の「Cache Port は抽象であって persistent store の採用ではない」が決め手 |
| 5 | 🔴 **キャッシュヒットは「CPU-ms」と「GitHub レート枠」には効くが「リクエスト数枠」には効かない**（3 軸に分解する）。`infrastructure-design.md` §10.2 の「同じ打ち手」という記述は Cloudflare 前提では不正確 | `cost_guard` の指摘に `cf_platform` が全面同意（CPU はヒット時ほぼゼロと補足） |
| 6 | **Free を初期値とし、`SP-1` の実測ゲート（p95 CPU / gzip バンドルサイズ）で Paid 要否を判定する**。前倒しで Paid にしない | `cost_guard` / `cf_platform` / `docs_trace` が一致。`SD-1` のプレビュー URL は Free でも出るため `SP-1` は止まらない |
| 7 | **`proxy.ts` / Node middleware を一切使わない**。`/` → `/ja` はルート `app/page.tsx` の Server Component 内 `redirect()` + `headers()` の Accept-Language 判定で実装する | `cf_platform`。フォールバックとして `next-intl` のルーティング機能を使わずメッセージカタログ API のみ利用する分割案も提示済み |
| 8 | **Workers Builds は採用せず GitHub Actions + `cloudflare/wrangler-action` に一本化**する | `cli_autonomy` 主導・異論なし（初回接続が GUI 必須という非対称性が CLI 一次方針と噛み合わない） |
| 9 | **プレビューは Worker を増やさず `wrangler versions upload --preview-alias pr-<N>`** で回す（Free の Worker 数上限 100 と棚卸しコストを避ける） | `cli_autonomy`・異論なし |
| 10 | **プレビュー URL の取得は stdout の正規表現抽出を主経路にし、取れなければ CI を fail-closed で落とす**。ND-JSON は検証専用に格下げ | `cli_autonomy` round 2 の精緻化。`SD-1` の「URL 無しで緑になる」経路を構造的に塞ぐ |
| 11 | **Cloudflare bindings へのアクセスは `lib/infra/` 配下のみに限定し、grep 2 本で機械検出する** | `privacy_lockin` が自分の round 1 案を「機械検出できない」と自己批判して書き直したもの |
| 12 | **Cloudflare MCP は読み取り 4 ツールのみアローリストで残し、書き込み系は使わない** | `cli_autonomy` 提案 → `privacy_lockin` が条件付き賛成（アローリストの明文化を要求）。ユーザー指示「MCP よりも CLI」は絶対禁止ではなく主経路の指定と解釈 |
| 13 | **`INF-1` を守る Cloudflare 側設定**: `observability.logs.invocation_logs: false` / Rate Limiting の key を HMAC 化して生 IP を渡さない / Bot Fight Mode を有効化しない / WAF Rate limiting rules は使わない（Free は IP 固定で `AR-5` の枠分けができない） | `privacy_lockin`・異論なし |

## 2. 議論を経て否定された案

| 案 | 誰が出したか | なぜ否定されたか |
|---|---|---|
| OpenNext incremental cache（R2 + `withRegionalCache` / D1 tag cache / DO queue）を MVP から入れる | `privacy_lockin`（round 1） | 提案者自身が round 2 で撤回。①R2 有効化に支払い方法の登録が必要で「Free のまま = 構造的ハードキャップ」を自ら壊す ②DO の無料枠が一次情報で未確認 ③`D-5` 追補（サーバー側ストアを持たない）と §6.2 の L3 ゲート（観測してから）に反する |
| Cache Port の実装位置を `open-next.config.ts` に固定する | `privacy_lockin`（round 1） | `NFR-17` は「事業者固有ストアをデータアクセス層から隔離する抽象」であって ISR バックエンドの選択ではない（`docs_trace`）。ISR を前提にしない gem-hunter では配線先が違う |
| 実測前に Workers Paid を既定にする | （検討案） | `INF-3` と `INF-2` が本当に衝突するかは実測しないと分からない。前倒しは根拠のない decision（`cost_guard`） |
| Workers Builds（Git 連携ビルド）を使う | （検討案） | 初回接続が GitHub App の GUI 承認で、CLI 一次方針と非対称。ビルド無料枠 3,000 分/月を捨てる代償は小さい（`cli_autonomy`） |
| `WRANGLER_OUTPUT_FILE_PATH` の ND-JSON を URL 取得の主経路にする | `cli_autonomy`（round 1 の一部） | フィールド名が未確認で false negative のリスク。round 2 で検証専用に格下げ |
| Cloudflare MCP を完全に捨てる | （ユーザー指示の厳格解釈） | 読み取り専用の利用は移行チェックリストに何も残さず退避コストゼロ（`privacy_lockin`）。指示の趣旨は「自律開発の主経路を CLI にする」ことなので射程外 |

## 3. 残った対立点と lead の裁定

### 争点 E（本番デプロイ先 `D-7` も今確定するか）

- **確定すべき**: `cli_autonomy`（プレビューと別基盤にすると CLI 経路・シークレット・CI が二重化し `INF-4` に反する）
- **開けておくべき**: `privacy_lockin` / `cf_platform`（§14 の `D-7` は `M-4` で決める設計。急ぐ理由がない）

🔴 **lead 裁定: 事業者は Cloudflare に確定する（プレビュー・本番とも）。**

理由は権威順（`intent-gate-rules.md`: **ユーザー明示 > 仕様 > テスト > 現行コード**）。ユーザーの指示は「**インフラについて Cloudflare ベースで進めたい**」であり、プレビューに限定していない。仕様（§14 の `M-4` 判断）より上位の権威がすでに与えられている以上、「開けておく」は仕様の惰性であって判断の保留ではない。

ただし `M-4`（公開判断ゲート）は **廃止せず性質を変える**: 「事業者を選定するゲート」ではなく「**第三者に公開するか否かを決めるゲート**」として維持する（独自ドメインの要否・GitHub 利用規約の一次確認・コスト撤退ラインの確定はここに残る）。

### 争点 A の残余（Paid 切替の実行主体）

`cost_guard` が round 2 で自ら訂正したとおり、**Free → Paid の切替に CLI/API 経路は存在せず、カード登録は不可分の人間作業**（`cli_autonomy` が裏取り）。したがって「事前承認」が変えるのは実行の代行可否ではなく **止まり方の質** — 閾値超過が実測で確定した瞬間に、`A/B/C/D` 分類をやり直さず「この 1 手だけ実行してください」と即時通知できるかどうか。これは `A-6` に該当するため、**ユーザーへの確認事項として残す**（open_questions）。

## 4. 未確認のまま残すもの（実装時に潰す・断定しない）

| # | 未確認事項 | 潰し方 |
|---|---|---|
| 1 | Next.js 16 App Router + shadcn/ui の実バンドルが Free の 3 MB（gzip）に収まるか | `SP-1` で `opennextjs-cloudflare build` 後に gzip サイズを計測 |
| 2 | RSC レンダリングの p95 CPU が Free の 10 ms に収まるか | `SP-1` で `wrangler tail` / Workers Logs から計測 |
| 3 | Workers invocation log にクライアント IP が含まれるか | 含まれる前提で `invocation_logs: false` に倒す（設計で回避） |
| 4 | Rate Limiting binding の課金有無 | 実装直前に料金ページを再確認（`SP-9` 相当） |
| 5 | `next-intl` のミドルウェアレス構成が現行版でサポートされるか | `SP-2` 着手前に context7 で一次確認。ダメならルーティングは自作に閉じる |
| 6 | `WRANGLER_OUTPUT_FILE_PATH` の `version-upload` エントリのフィールド名 | 初回 CI 実行で実物を確認（主経路にしないので blocking ではない） |
| 7 | workers.dev サブドメインの初期登録を非対話で完結できるか | 初回デプロイで確認。失敗したら Dashboard で 1 回だけ設定（`H-1` に同梱） |

### `lead` — 判定
<sub>2026-08-18T11:42:24+09:00</sub>

{
  "decisions": [
    {
      "issue": "A: Workers Free か Workers Paid か",
      "design": "Free を初期値にする。SP-1 で (1) p95 CPU 時間 (2) gzip 後の Worker バンドルサイズ を実測し、p95 CPU > 7〜8ms または バンドル > 3MB のときだけ Paid へ上げる。Claude は判定と limits.cpu_ms 等の準備まで自律実行し、支払い方法の登録だけを A-6 としてユーザーへ即時通知する（Free→Paid の切替に CLI/API 経路は存在しない）。Free のままなら超過は課金ではなく HTTP 1027 停止に倒れ、INF-2 の『停止側に倒す』が構造的に満たされる。",
      "artifacts": [
        "docs/03_design/infrastructure/cloudflare-infrastructure.md（新規・実測ゲートの判定式）",
        "docs/03_design/infrastructure/infrastructure-design.md（改修・§14 に CPU/バンドル実測を追加）"
      ],
      "rejected": "実測前に Paid を既定にする案。INF-3 と INF-2 が実際に衝突するかは実測しないと決まらず、前倒しは根拠のない decision（cost_guard）"
    },
    {
      "issue": "B: キャッシュ実装の置き場所",
      "design": "MVP は HTTP Cache-Control（RFC 9111・事業者非依存）+ Workers Caching（wrangler.jsonc の cache.enabled）だけで構成する。永続ストア（R2 / D1 / DO / KV）は採用しない。NFR-17 Cache Port は lib/infra/ 配下の薄いラッパー（キャッシュキー生成 + Cache-Control 付与、面積は get/set/invalidate + TTL）として維持し、L3 は infrastructure-design.md §6.2 の観測条件を満たしたときだけ ADR とともに導入する。",
      "artifacts": [
        "docs/03_design/infrastructure/cloudflare-infrastructure.md（新規）",
        "wrangler.jsonc（新規・cache.enabled）",
        "lib/infra/cache.ts（新規・SP-5 で実装）"
      ],
      "rejected": "OpenNext incremental cache（R2 + regional cache / D1 tag cache / DO queue）を MVP から入れる案。提案者自身が撤回。R2 有効化に支払い方法の登録が要り Free のハードキャップを自壊させる / DO の無料枠が未確認 / D-5 追補と §6.2 の L3 ゲートに反する"
    },
    {
      "issue": "C: OpenNext + wrangler.jsonc は INF-5 / NFR-21 に違反するか",
      "design": "違反しない。境界は『アプリコードが Cloudflare bindings を直接触るか』の一点に置く。Cloudflare bindings（getCloudflareContext() の戻り値・env.KV / env.R2 / env.D1 / env.RATE_LIMITER / env.CACHE / env.IMAGES 等）へのアクセスは lib/infra/ 配下からのみ許可し、app/ と lib/data/ からの直接アクセスを禁止する。grep 2 本（bindings 直接参照 / Cloudflare 環境変数による実行時分岐）を tools/self_review_check.py に追加して機械検出する。wrangler.jsonc と open-next.config.ts は app/ の外に置き、実行時の分岐条件として読まない。",
      "artifacts": [
        "docs/03_design/infrastructure/infrastructure-design.md（改修・§3.2 に禁止 #7 #8 を追加、§13 に破棄項目を追加）",
        "tools/self_review_check.py（改修・grep 2 本を機械ゲート化）",
        "docs/adr/0002-cloudflare-workers-infrastructure.md（新規）"
      ],
      "rejected": "『1 ファイルに閉じ込める』という数量表現での規約化。提案者が自己批判したとおり grep でホワイトリスト化できず目視判断に戻る"
    },
    {
      "issue": "D: CLI 一次経路の具体形",
      "design": "GitHub Actions + cloudflare/wrangler-action に一本化する（Workers Builds は不採用）。プレビューは Worker を増やさず wrangler versions upload --preview-alias pr-<N> で回す。URL は stdout の正規表現抽出を主経路にし、取得失敗・到達性 5xx・PR への反映失敗のいずれでも CI を fail-closed で落とす（SD-1 がサイレントに欠落する経路を塞ぐ）。非対話化は CLOUDFLARE_API_TOKEN / CLOUDFLARE_ACCOUNT_ID + WRANGLER_SEND_METRICS=false + WRANGLER_SEND_ERROR_REPORTS=false。Cloudflare MCP は読み取り 4 ツール（search_cloudflare_documentation / workers_list / workers_get_worker / workers_get_worker_code）のみアローリストで残し、書き込み系は使わない。SP-1 のブートストラップ期間に限り Claude がセッションから直接 wrangler versions upload を叩いてよい（INF-20 の例外として明記し、SP-4 以降は CI 経由に一本化）。",
      "artifacts": [
        ".github/workflows/deploy-preview.yml（新規）",
        ".github/workflows/deploy-production.yml（新規）",
        "docs/03_design/infrastructure/cloudflare-infrastructure.md（新規・CLI 運用規約と MCP アローリスト）"
      ],
      "rejected": "Workers Builds（初回接続が GitHub App の GUI 承認で CLI 一次方針と非対称）/ ND-JSON を URL 取得の主経路にする案（フィールド名未確認で false negative リスク）"
    },
    {
      "issue": "E: 本番デプロイ先（D-7）も今確定するか",
      "design": "確定する。プレビュー・本番とも Cloudflare Workers。権威順（ユーザー明示 > 仕様）に従い、ユーザー指示『インフラについて Cloudflare ベースで進めたい』はプレビューに限定されていない。M-4 は廃止せず『第三者へ公開するか否かを決めるゲート』として性質を変えて維持する（独自ドメインの要否・GitHub 利用規約の一次確認・コスト撤退ラインの確定はここに残す）。",
      "artifacts": [
        "docs/02_requirements/open-questions.md（改修・D-16 / D-17 / D-18 を追加し D-7 / D-11 を決定済みに更新）",
        "docs/02_requirements/roadmap.md（改修・M-4 の性質変更）",
        "docs/02_requirements/prd.md（改修・§13 のプレビュー環境デプロイ先をクローズ）"
      ],
      "rejected": "D-7 を M-4 まで開けておく案。ユーザー明示決定が既にある以上、保留は判断ではなく仕様の惰性"
    }
  ],
  "tasks": [
    { "id": "T-1", "title": "Cloudflare API トークンを 1 本発行する（Edit Cloudflare Workers テンプレート）", "actor": "user", "depends_on": [], "sp": "sp:1" },
    { "id": "T-2", "title": "トークンと Account ID を GitHub Actions Secrets と Claude.ai 環境変数の 2 箇所に登録する", "actor": "user", "depends_on": ["T-1"], "sp": "sp:1" },
    { "id": "T-3", "title": "wrangler の疎通確認と workers.dev サブドメインの確定（whoami / 初回 upload）", "actor": "claude", "depends_on": ["T-2"], "sp": "sp:1" },
    { "id": "T-4", "title": "@opennextjs/cloudflare 導入・wrangler.jsonc / open-next.config.ts 追加・next を 16.2.11+ にピン", "actor": "claude", "depends_on": ["T-3"], "sp": "sp:3" },
    { "id": "T-5", "title": "プレビュー版をアップロードして PR にプレビュー URL を貼る（SD-1 の成立）", "actor": "claude", "depends_on": ["T-4"], "sp": "sp:2" },
    { "id": "T-6", "title": "GitHub Actions（preview / production）を作成し fail-closed の URL 検証を組み込む", "actor": "claude", "depends_on": ["T-5"], "sp": "sp:3" },
    { "id": "T-7", "title": "p95 CPU 時間と gzip バンドルサイズを実測し Free/Paid を判定する", "actor": "claude", "depends_on": ["T-5"], "sp": "sp:2" },
    { "id": "T-8", "title": "lib/infra/ 境界を作り Cache Port（Cache-Control ラッパー）を実装する", "actor": "claude", "depends_on": ["T-4"], "sp": "sp:3" },
    { "id": "T-9", "title": "bindings 直接参照と Cloudflare 環境変数分岐の grep 2 本を self_review_check.py に追加する", "actor": "claude", "depends_on": [], "sp": "sp:2" },
    { "id": "T-10", "title": "observability.invocation_logs 無効化・シークレット投入・Rate Limiting（HMAC key）を設定する", "actor": "claude", "depends_on": ["T-4"], "sp": "sp:3" },
    { "id": "T-11", "title": "Workers Paid へ切り替える（T-7 が閾値超過を実測で確定した場合のみ）", "actor": "user", "depends_on": ["T-7"], "sp": "sp:1" }
  ],
  "critical": [
    "Free の CPU 10ms / バンドル 3MB（gzip）に Next.js 16 App Router の SSR が収まるかは一次情報で確定できず、実測するまで Free 運用の成立は断定できない。SP-1 の実測ゲートを通過するまで『月額 0 円で動く』と報告してはならない",
    "キャッシュヒットも Workers のリクエスト枠を消費するため、Free の 100,000 req/日 に対してキャッシュは防波堤にならない。infrastructure-design.md §10.2 の『キャッシュヒット率向上はコスト削減とレート制限対策の同じ打ち手』という記述は Cloudflare 前提では不正確で、3 軸（CPU-ms / GitHub レート枠 / リクエスト数）に分解して書き直す必要がある",
    "Paid へ移行するとハードキャップが消滅し、リクエスト数課金の暴走を止める native な手段が存在しない（Budget alerts は通知のみ・Spend limit は AI Gateway 専用）。limits.cpu_ms と Billable Usage API の日次ポーリングによる後追い封じ込めしか残らない"
  ],
  "open_questions": [
    "SP-1 の実測で Free の上限（p95 CPU > 7〜8ms または gzip バンドル > 3MB）を超えた場合、Workers Paid（$5/月）へ上げてよいか。上げない場合は SSR を削る等の設計変更で Free に留める必要があり、成果物が変わる（A-6: 支払い方法の登録はユーザー権限が物理的に必要）",
    "Paid へ移行した場合の月額撤退ライン（Billable Usage API の監視閾値に使う実額）。infrastructure-design.md §14 で未決のまま残っている"
  ]
}
