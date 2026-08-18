<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: gem-hunter のインフラを Cloudflare 前提で確定させ、CLI 一次運用で自律開発できる形に落とす

- 議題ID: `cloudflare-infra-20260818`
- 論点: ユーザー決定: (1) インフラは Cloudflare ベースで進める (2) 既存の Cloudflare アカウントを使い必要リソースを作成する (3) 自律開発のため MCP ではなく CLI（wrangler）を主経路にする。制約: docs/03_design/infrastructure/infrastructure-design.md の INF-1（サーバー側に個人情報を保持しない）/ INF-2（定常コストをゼロに近づける・超過時は課金ではなく停止に倒す）/ INF-3（Next.js 標準機能の範囲・TR-1〜TR-4）/ INF-4（人手の定常運用ゼロ）/ INF-5（事業者を決め打たない = アプリコードに事業者固有 API を持ち込まない・NFR-21）と、INF-6〜INF-22 の契約を壊さないこと。DB を持たない（D-5 追補）。SD-1 により全スプリントの PR に開けるプレビュー URL が要る。リサーチ結果は docs/01_research/infra/20260818-cloudflare-research.md（一次情報・2026-08-18 取得）にある。争点は少なくとも次の 5 つ: A) Workers Free（CPU 10ms・バンドル 3MB 圧縮後）のまま Next.js 16 の SSR を成立させられるか、それとも Workers Paid $5/月 を前提にすべきか（INF-2 と INF-6 の衝突・課金は A-6 でユーザー権限が要る） B) キャッシュ実装をどこに置くか（Workers Caching の cache.enabled / HTTP Cache-Control / OpenNext incremental cache（R2/D1/DO）/ KV）と、それが NFR-17 Cache Port・INF-5・D-5 追補（DB を持たない）と両立するか C) OpenNext アダプタ + wrangler.jsonc の採用が INF-5 / NFR-21 に違反しないか、違反しないと言える境界はどこか D) CLI 一次経路の具体形（GitHub Actions + wrangler-action か Workers Builds か、プレビュー URL の生成と機械取得、トークンの供給経路とローテーション、人間の GUI 作業をどこまで削れるか） E) 本番デプロイ先（D-7）も今この場で Cloudflare に確定すべきか、プレビュー（D-11）だけに留めるべきか。
- 参加者: `cf_platform`, `cost_guard`, `cli_autonomy`, `privacy_lockin`, `docs_trace`
- 投稿数: 5
- 更新: 2026-08-18T11:34:38+09:00

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
