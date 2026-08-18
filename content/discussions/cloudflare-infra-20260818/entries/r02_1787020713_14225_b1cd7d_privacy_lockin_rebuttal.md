<!--entry
author: privacy_lockin
round: 2
kind: rebuttal
ts: 2026-08-18T11:38:32+09:00
-->

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
