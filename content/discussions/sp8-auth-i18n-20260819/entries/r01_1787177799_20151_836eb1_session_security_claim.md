<!--entry
author: session_security
round: 1
kind: claim
ts: 2026-08-20T07:16:39+09:00
-->

## claim（session_security・争点 B）

### 結論（先出し）

1. **暗号化方式は JWE（`jose` の `EncryptJWT` / `A256GCM` + `dir` 鍵管理）を採用し、署名のみの JWS は不採用**
2. **GitHub アクセストークンは（no-scope 前提で）JWE 暗号化した httpOnly Cookie に直接持たせてよい**。ただし平文コミットせず、暗号化必須を絶対条件とする
3. **CSRF `state` はサーバー側ストアを持てない（D-5）ため、`authorize` 時に発行する短命な二次 Cookie（`oauth_state`、単純ランダム値・非暗号化）に保存し、`callback` でクエリ値と Cookie 値を厳密一致比較する。比較後は即座に破棄する**
4. **ログアウトは session Cookie を `Max-Age=0` で上書きし、`oauth_state` 系 Cookie が残っていれば同時に破棄する**

---

### 根拠 1: JWE 必須・JWS 単独では NFR-9 を満たせない

- `prd.md` AR-5 詳細（244-251 行）: 「セッションは暗号化した httpOnly Cookie で保持する（DB を持たないため）。ユーザーの OAuth トークンをクライアントへ露出させない」— **「暗号化した」と明記**されており、署名のみ（JWS）は仕様の字面上も不適合。
- NFR-9（288 行）:「秘匿情報をクライアントへ露出させない…ユーザーのアクセストークンはすべてサーバー側でのみ扱う」。JWS はペイロードが base64url でしかなく **誰でも復号（デコード）してトークン原文を読める**。httpOnly は JS からの読み取りを防ぐだけで、Cookie は物理的にブラウザ側に存在し、DevTools の Application パネルやネットワークログ経由でペイロードが可読になる。JWS のみだと「サーバー側でのみ扱う」の実質を満たせず NFR-9 違反リスクが高い。
- 一方 JWE は対称鍵（`SESSION_ENCRYPTION_KEY` などの環境変数、サーバーのみ保持）がなければ復号不能なため、Cookie が物理的にクライアント側にあっても内容は「実質的にサーバー側でのみ扱われている」と言える。**D-5（DB なし）の制約下で NFR-9 を満たす唯一の現実的手段が自己完結型の暗号化 Cookie（JWE）**。

### 根拠 2: 「署名付き opaque セッション ID + サーバー側一時保持」案は D-5 だけでなく Workers の実行モデルでも破綻する（rejected）

- `installation-token.ts` はモジュールレベルの `cached` 変数（グローバル可変状態）でトークンキャッシュを持っているが、コメントに明記されている通りこれは **「失っても再取得すれば済む」性質のキャッシュ**であり、正しさに影響しない。
- opaque セッション ID をキーにしたサーバー側一時保持（インメモリ Map 等)を同じパターンで実装しようとすると、性質が違う: Cloudflare Workers は **リクエストごとに異なる isolate で実行されうる**ため、グローバル変数に保持したセッション状態は次のリクエストで消えている可能性があり、**ログイン直後に自分のセッションが見えなくなる**という機能的破綻を起こす。D-5 の「永続ストア不可」を KV/D1 等の外部ストアで回避する提案も出うるが、それは新規インフラ導入であり本スプリントのスコープ外・D-5 の意図（DB を持たない）に反するため不採用。
- 結論: **自己完結（self-contained）な暗号化 Cookie 以外に選択肢がない**。

### 根拠 3: no-scope トークンをそのまま Cookie に持たせることの是非

- `auth_flow` 側の争点 A 決定（no-scope OAuth）を前提にすると、漏洩時の実害は「公開データの取得 API に対するレート枠増加」に限られ、プライベートリポジトリ・書き込み権限などの重大リスクはない（`AR-5`:「公開リポジトリの検索・閲覧しか行わないため追加権限は不要」）。
- とはいえ NFR-9 は no-scope かどうかに関わらず「クライアント非露出」を要求しているため、**リスクの小ささを理由に平文格納・JWS のみへ格下げしない**。JWE 前提であれば直接持たせて問題ない（トークンを別途参照するための opaque ID を発行してどこかに紐付ける、という余分な間接層は D-5 下では作れる場所がなく YAGNI）。
- セッション Cookie の有効期限は GitHub トークンの無期限性に依存させず、**アプリ側で妥当な TTL（例: 7〜14 日）を JWE の `exp` に設定し、期限切れで再ログインを要求する**設計にする（無期限セッションを避けることは一般的なセキュリティ衛生であり、no-scope でも省略しない）。

### 根拠 4: CSRF state はサーバー側ストア不可（D-5）→ 二次 Cookie 方式（double-submit 型）

- 標準的な「サーバーでランダム値を生成 → セッションストアに保存 → callback で突合」というパターンは D-5 で使えない。
- 代替として **`authorize` へのリダイレクト直前に、暗号論的乱数の `state` を生成し、GitHub への authorize URL のクエリに載せると同時に、短命（例: 10 分）・httpOnly・`Secure`・`SameSite=Lax` の Cookie（例: `gh_oauth_state`）にも同じ値を保存する**。`SameSite=Lax` である理由: GitHub からのリダイレクトバックはトップレベル GET ナビゲーションであり、`Lax` はこのケースで Cookie を送出する（`Strict` だと送られず state 検証が常に失敗する）。
- `callback` ハンドラでは、クエリの `state` と Cookie の `gh_oauth_state` を **タイミングセーフな文字列比較**で厳密一致確認し、不一致・欠如なら 400 として処理を中断、トークン交換に進まない。一致確認後は state Cookie を即時削除する（使い捨て・リプレイ防止）。
- **この state Cookie 自体を暗号化・署名する必要はない**（YAGNI）。値そのものに秘匿情報を含まず、サーバーが発行してサーバーが検証するだけの「サーバー側が書いた値をサーバー側が読み返す」用途であり、httpOnly + Secure により JS からの読み取り・改ざんは防げる。攻撃者が Cookie を上書きできるのは XSS が成立した場合のみで、その場合は state 云々よりも根本の XSS 対策が先決（対称鍵で毎回暗号化するコストに見合わない）。

### 根拠 5: ログアウト

- session Cookie を `Set-Cookie: <name>=; Max-Age=0; Path=/; HttpOnly; Secure; SameSite=Lax` で上書きし、クライアント側の Cookie ストアから確実に削除する（値を空にするだけで Max-Age を更新しないと古いブラウザで残存しうるため必須）。
- `gh_oauth_state` は callback 成功時点で既に削除済みのはずだが、フロー中断（state 不一致・ユーザーが認可を拒否等）で残る可能性があるため、ログアウト処理でも防御的に同名 Cookie を削除する。
- GitHub 側のトークン失効（`DELETE /applications/{client_id}/grant`）は、no-scope かつ D-6（機能差を作らない・上乗せ最小主義）の方針を踏まえると **MVP 必須要件ではない**と判断する（Cookie 削除だけで本アプリからは即座に使えなくなり、AC 上の「ログアウトすると元に戻る」は満たせる）。ただし将来課題として `critical`/`open_questions` ではなく単なる補足に留める（成果物が変わる仕様分岐ではないため確認不要・SD-3 の射程外）。

### 根拠 6: NFR-22（環境変数集約）との整合

- `prd.md` §10 の環境変数一覧に「OAuth クライアント ID」「OAuth クライアントシークレット」「OAuth コールバック URL」「セッション暗号化キー」が既に列挙済み。**いずれも `NEXT_PUBLIC_` を付けない**（518 行）。
- `installation-token.ts` の `readCredentials()` パターン（環境変数が揃っていなければ `null` を返し機能を無効化）を、セッション暗号化キー・OAuth クライアント ID/シークレットの読み取りにも踏襲する。これは `infrastructure-design.md` §8.1 の「環境変数未設定でログイン導線が自動的に消える」方針（アプリコードに環境判定を書かない）とも整合する。
- セッション Cookie の暗号鍵と OAuth 資格情報を読んでよいファイルは、`installation-token.ts` 冒頭コメント「🔴 秘匿情報を読んでよいのはこのファイルだけ」に倣い、**新設する session/OAuth 用インフラファイル 1〜2 本に限定**すべき（ARCH-5: GitHub API・GitHub 認証情報は `src/infrastructure/github/` か `platform/` の中だけ）。具体的な配置は争点 C（`clean_arch` レンズ）と整合させる必要があるが、セキュリティ観点からの制約としては「秘匿値を読むコードパスを 1 箇所に閉じ込める」ことを要求する。

### アルゴリズム選定の補足（Edge/Workers 適合性）

- installation token 用の `SignJWT`/`importPKCS8`（RS256・非対称）は GitHub App 認証の要件上必須だが、**セッション Cookie はアプリ自身が発行・検証する**ため非対称鍵にする理由がない。`EncryptJWT`（`jose`）で `alg: "dir"`（鍵導出なしの直接鍵使用）+ `enc: "A256GCM"` を使う対称暗号を推奨する。Web Crypto ベースで Cloudflare Workers 上でも動作する（`jose` は Workers 対応を謳っている）。
- 対称鍵は 32 バイト（256bit）を base64url 等でエンコードして環境変数に格納する運用とし、`readCredentials` 相当のガードで未設定時は `null`（ログイン機能無効化）とする。

---

### 他レンズへの申し送り

- `auth_flow`（争点 A）: no-scope 前提と自前実装方針が確定するなら、本 claim の JWE 設計・state Cookie 設計はそのまま適用可能。ライブラリ導入（Auth.js 等）を選ぶ場合でも、D-5 制約下のセッション戦略（DB アダプタ不使用・JWT セッション戦略）は本 claim と同じ結論に収束するはずなので、ライブラリ選定如何に関わらずこの設計方針自体は独立して成立する。
- `clean_arch`（争点 C）: 秘匿値を読むコードを 1〜2 ファイルに閉じ込める制約（ARCH-5 由来）を、composition root 配線の設計に反映してほしい。
- `verify_test`（争点 D）: E2E での state 検証・Cookie 暗号化のモック化について、`SESSION_ENCRYPTION_KEY` はダミー固定値を e2e 用環境変数として注入すればよく、GitHub 側の authorize/token/callback だけを `e2e/stub/server.mjs` でモックすれば十分（暗号化ロジック自体はアプリ内で完結するためスタブ不要）。
