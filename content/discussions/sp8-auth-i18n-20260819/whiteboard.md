<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: SP-8 ログイン(GitHub OAuth)でレート枠切替と言語切替を実装する設計

- 議題ID: `sp8-auth-i18n-20260819`
- 論点: SP-8（Issue #140, sp:8）のゴールは『未ログインのまま全機能が使える／ログインするとレート枠が自分のものに切り替わる／ログアウトすると元に戻る／言語を英語に切り替えると URL ロケールと UI 文言が変わる（リポジトリ説明文は原文のまま）』を操作レビューで確認できる状態にすること（user-story-map.md §5.3 SP-8、US-2/US-4/US-5、E-11 の OAuth モック追加）。既に確定済みの前提: prd.md AR-5（244-251行）により GitHub OAuth はスコープ要求なし（no scope）、セッションは暗号化 httpOnly Cookie に保持しトークンをクライアントへ非露出、CSRF 対策で state パラメータ必須、ログアウトで Cookie 破棄、コールバック URL は環境変数化、認証は任意で機能差を作らない（D-6）。prd.md AR-4（237-242行）により i18n は自前実装（next-intl 不採用・R-7 で確定済み）で、URL は全ロケールにプレフィックス（/ja/ /en/）、既定ロケールは ja、GitHub 由来データは機械翻訳しない。i18n 基盤（app/[locale]/ セグメント・src/domain/model/locale.ts の Locale 値オブジェクト・src/shared/i18n/messages.ts・messages/ja.json・messages/en.json・src/ui/url/locale-redirect.ts）は既に実装済みで SP-8 が触るのは言語切替 UI（US-2）の追加のみ。認証関連の実装は src/ 配下に一切存在せず本スプリントが新規実装する。architecture-rules.md の ARCH-2（ユースケースはポートを引数で受け取る）/ ARCH-3（app・src/ui から src/infrastructure を直 import しない。src/composition 経由必須）/ ARCH-4（事業者固有バインディングは src/infrastructure/platform の中だけ）/ ARCH-5（GitHub API と GitHub 認証情報は src/infrastructure/github/ か platform/ の中だけ）は不変。D-5（DB を持たない）によりセッションストアは持てず Cookie 完結が前提。jose（^6.2.9）が依存済みで JWT/JWE 操作に使える。infrastructure-design.md §8.1（270-281行）により、OAuth コールバック URL の事前登録とプレビュー URL の PR 毎変化が非両立のため、プレビュー環境では OAuth を無効化する方針（環境変数未設定で自動的にログイン導線が消える。アプリコードに環境判定を書かない）が既に決まっており、SP-8 の E2E・操作レビューはプレビュー URL ではなく『ダミー OAuth 設定を注入したローカルビルド』に対して実行する。e2e/stub/server.mjs は現在 GitHub REST API（検索・詳細・レート制限 403 シミュレーション）のみスタブしており OAuth authorize/token/callback のモックは未実装。関連する未完了 Issue #122『RateLimitPort を composition root と全経路へ実際に配線する』があり、レート枠切替の実装はこの Port と整合させる必要がある。争点は次の 4 つ: A) OAuth フロー自体を自前実装するか（ライブラリは未導入。i18n は Edge/Workers 実行モデル非両立を理由に自前実装した前例がある）、それとも Auth.js 等のライブラリを新規導入するか。プレビュー無効化・no-scope・自前 i18n との整合、Cloudflare Workers（Edge runtime）上での動作可否で判断する。B) セッション Cookie の暗号化方式（jose の JWE で GitHub アクセストークン自体を暗号化して Cookie に入れるか、署名付き opaque セッション ID + サーバー側の一時保持かだが D-5 により永続ストアは不可）と、CSRF state パラメータの検証をどこでどう実装するか。C) 層配置（route handler の置き場所と composition root の配線方法、ARCH-2/ARCH-3/ARCH-4/ARCH-5 との整合、RateLimitPort 配線（#122）とレート枠切替ユースケースの関係、言語切替 UI（US-2）をどのコンポーネント層に置くか）。D) 検証可能性（e2e/stub/server.mjs への OAuth モック追加方法、プレビュー無効化 + ダミー OAuth ローカルビルドでの E2E 実行手順の具体化、4 つの操作レビュー手順の E2E 化、TDD の Red をどの順に書くか）。
- 参加者: `auth_flow`, `session_security`, `clean_arch`, `verify_test`
- 投稿数: 12
- 更新: 2026-08-20T07:23:41+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

## ラウンド 1

### `auth_flow` — 主張
<sub>2026-08-20T07:16:06+09:00</sub>

## claim（争点 A: OAuth フローは自前実装 / Auth.js 等ライブラリ導入か）

**結論**: **自前実装を採用する（ライブラリ非導入）。GitHub OAuth App の新規登録は必要（local 用 + production 用の 2 App。プレビューは無効化のため不要）。**

### 根拠 1: no-scope・DB なしという要件が小さすぎて Auth.js の価値が出ない

- `AR-5` 詳細（prd.md 244-251行）で確定済みの制約は「OAuth スコープなし」「セッションは暗号化 httpOnly Cookie のみ（DB なし・`D-5`）」「プロバイダは GitHub 1 種のみ」「state による CSRF 対策」「ログアウトで Cookie 破棄」。
- Auth.js（NextAuth v5）が提供する主要機能（複数プロバイダ抽象化、DB アダプタ群、JWT ローテーション、RBAC、メール認証等）はどれも本スプリントの要件に対応がない。**セッション暗号化に使う `jose` は既にプロジェクトの直接依存**（package.json 確認済み・`^6.2.9`）であり、Auth.js を挟まなくても JWE で同じことができる。ライブラリ導入は「機能を借りる」ためではなく「実装を減らす」ためだけの動機になるが、その実装量（authorize リダイレクト・callback・token 交換の 3 ステップ）自体が小さい。

### 根拠 2: プレビュー無効化方針（infrastructure-design.md §8.1）との相性

- 確定済み方針: 環境変数が未設定なら **アプリコードに環境判定を書かず**、ログイン導線が自然に消える設計にする（`INF-5` 禁止 6）。
- 自前実装なら「`GITHUB_OAUTH_CLIENT_ID` 等が存在するときだけログインリンクの `href` を生成する」という素朴な条件で満たせる。Auth.js は `NextAuth(config)` を `app/api/auth/[...nextauth]/route.ts` でモジュール読み込み時に構成するため、プロバイダの `clientId`/`clientSecret` が未定義のときの挙動（バリデーションエラーで route 自体が壊れる／`trustHost` 未設定で例外）をライブラリ側の初期化パスに依存することになり、「未設定なら静かに機能が消える」という要件との相性検証コストが自前実装より高い。

### 根拠 3: 自前 i18n の前例との整合（Edge/Workers 実行モデル）

- i18n は `next-intl` を採用せず自前実装した前例があり、理由は「Edge/Workers 実行モデルとの非両立」（brief に明記）。同じ判断基準を OAuth にも適用する。
- 本プロジェクトのデプロイ先は Cloudflare（`@opennextjs/cloudflare` 経由の Workers ランタイム）。自前実装は `fetch`（GitHub token endpoint 呼び出し）と Web Crypto（`crypto.randomUUID()` で state 生成、`jose` で JWE）のみに依存し、いずれも Workers 標準 API — 動作可否の不確実性がゼロに近い。
- Auth.js v5 は Vercel Edge を主な対象に育っており、OpenNext 経由の Cloudflare Workers での動作実績は本プロジェクト内に検証履歴がない（i18n で「未検証ライブラリを Edge に持ち込まない」という判断を既に一度下しているのに、OAuth だけ例外にする理由がない）。verify_test 側で実機検証できないなら、そのリスクを SP-8 の限られたスコープで背負う理由が薄い。

### 根拠 4: 層配置（ARCH-3/ARCH-4/ARCH-5）との親和性

- `ARCH-5`: GitHub API と GitHub 認証情報は `src/infrastructure/github/`（または `platform/`）の中だけに閉じる（Error 級・`arch-ok` 抑止不可）。
- 自前実装なら、GitHub とのやり取り（authorize URL 組み立て・token 交換・`/user` 取得）を丸ごと `src/infrastructure/github/oauth.ts` に閉じ込め、`app/` 側の route handler は composition root 経由でユースケースを呼ぶだけの薄いアダプタにできる（`ARCH-2` のポート注入とも自然に整合）。
- Auth.js は `NextAuth(config)` という 1 つの設定オブジェクトに「プロバイダの client secret」「callback（session 整形）」「cookie 名」等を **`app/api/auth/[...nextauth]/route.ts` 内で一括宣言する** のが標準パターンであり、GitHub 固有のロジックを `app/` から追い出して `src/infrastructure/github/` に完全に押し込めるには、Auth.js の標準的な使い方から外れたラッパーを追加で書く必要がある。結局「ライブラリのために薄いラッパー層を足す」ことになり、コスト削減という導入動機が相殺される。

### シーケンス具体化（authorize → callback → token 交換）

1. `GET /api/auth/github/authorize` — `state` を生成（Web Crypto）→ 短命 `oauth_state` Cookie に保存 → `https://github.com/login/oauth/authorize?client_id=...&redirect_uri=...&state=...`（**`scope` パラメータを付けない = no-scope**）へ 302 リダイレクト
2. GitHub → `GET {callback_url}?code=...&state=...`
3. `GET /api/auth/github/callback` — `oauth_state` Cookie と query の `state` を照合（不一致ならログイン失敗として `/login?error=state_mismatch` 等へ）→ 一致なら `POST https://github.com/login/oauth/access_token`（`Accept: application/json`）で `code` を `access_token` に交換 → `GET https://api.github.com/user`（Authorization ヘッダ）で最小プロフィール（login・avatar）取得 → セッション Cookie 発行（暗号化方式は session_security の担当領域）→ 元のロケール付きページへリダイレクト
4. `POST /api/auth/logout`（または `GET`）— セッション Cookie を破棄して同ページへリダイレクト

### 環境変数設計（callback URL の環境変数化・AR-5 詳細行 250）

- `GITHUB_OAUTH_CLIENT_ID` / `GITHUB_OAUTH_CLIENT_SECRET` — GitHub OAuth App 側の値。**local 用と production 用で別 App**（`INF-17` の「プレビューと本番でシークレットを共有しない」原則を local/production 間にも適用し、開発者個人の PAT/App を汚染しない）
- `GITHUB_OAUTH_CALLBACK_URL` — 環境ごとの絶対 URL（local: `http://localhost:3000/api/auth/github/callback`、production: `https://{本番ドメイン}/api/auth/github/callback`）。プレビューは未設定のまま = ログイン導線が出ない
- ログイン導線の表示可否は「上記 3 変数が揃っているか」の単純な真偽で composition root 側から解決し、`app/` にも `src/ui/` にも環境名を判定するコードを書かない（`INF-5` 禁止 6 の遵守）

### GitHub OAuth App 登録の要否

- **要**。自前実装でもライブラリ導入でも GitHub 側に OAuth App（client_id/secret・callback URL）を登録する作業は避けられない（プラットフォーム側の設定でありコードでは代替不可）。local 用と production 用の 2 App が必要（プレビューは §8.1 方針により無効化のため不要）。この登録作業はユーザーの GitHub アカウント操作が必要な設定変更であり、`tasks` 側で `actor: user` として切り出すべき项目。

### rejected として明記すべき代替案

- **Auth.js（NextAuth v5）導入**: 機能過多（no-scope・DB なし要件に対して RBAC・複数プロバイダ・DB アダプタ等が全て不要）、プレビュー無効化パターン（環境変数不在で静かに機能が消える）との相性検証コストが高い、Cloudflare Workers（OpenNext 経由）での動作実績が本プロジェクト内に無い、`ARCH-5` の「GitHub 資格情報は `src/infrastructure/github/` に閉じる」を満たすには結局ラッパーが要り導入コストを相殺する、という 4 点で不採用。

### `session_security` — 主張
<sub>2026-08-20T07:16:39+09:00</sub>

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

### `clean_arch` — 主張
<sub>2026-08-20T07:17:50+09:00</sub>

## clean_arch（層と依存規則・争点 C）Round 1 claim

### C-1: route handler の配置と composition root 配線

**claim**: OAuth 3 経路は `app/api/auth/{login,callback,logout}/route.ts` に置き、いずれも `src/composition/**` と `next/**` 以外を import しない（ARCH-3 の Frameworks & Drivers 行のとおり）。composition root に `src/composition/auth.ts` を新設し、以下を再輸出する。

- `buildGithubAuthorizeUrl(state: string): string`（`src/infrastructure/github/oauth.ts` の薄いラップ。ARCH-5「GitHub 認証情報は infrastructure/github/ の中だけ」）
- `completeLoginUseCase(): CompleteLogin`（`src/usecases/complete-login.ts` を `AuthPort` 実装（`GithubOAuth`）で束ねる）
- `encodeSessionCookie(payload)` / `decodeSessionCookie(raw)`（`src/infrastructure/platform/session-cookie.ts` の薄いラップ。暗号方式は session_security の B 決定に従うが、置き場所は `platform/` — `cache.ts`/`rate-limit.ts` と同じく「Cookie という外部世界」を扱う ACL）

**evidence**: `app/api/search/route.ts`（既存）は `@/src/composition/container` からのみ実装を取得しており前例と一致。`architecture-rules.md` ARCH-3・ARCH-5、`application-architecture.md` §1.2 の import 可否表。

**根拠づけ（W-n）**: composition root を経由させる理由は W-2（Cookie の暗号方式・OAuth 実装を差し替えても `app/` を書き換えずに済む）。

### C-2: `AuthPort` を新設（usecase はポートを引数で受け取る・ARCH-2）

**claim**: `src/domain/ports/auth-port.ts` に `AuthPort`（`exchangeAuthorizationCode(code): Promise<{ accessToken: string }>`）を追加し、`application-architecture.md` §2 のポート表に **W-3（フェイクでユニットテストできる）** を根拠に 1 行追加する。**実装は `src/infrastructure/github/oauth.ts`**（ARCH-5）。

**ドメイン純度チェック（brief 最後の要求）**: ポート名・メソッド名に `Github` / `OAuth`（プロトコル名としての `OAuth` は許容するが実装詳細は含めない）/ `Cookie` を持ち込まない。既存の `RepositoryQueryPort` も実装は GitHub 限定だがインターフェース名は事業者中立（`RepositoryQueryPort`、`Github` を冠さない）のと同じ規律を踏襲する。**Cookie は一切ドメインへ入れない** — usecase は `code: string` を受け取り `{ accessToken }` を返すだけで、Cookie の生成・検証は route handler（Set-Cookie ヘッダ）と `session-cookie.ts`（infra）だけが知る。**CSRF state 検証も usecase の外**（state は Cookie 由来の web セキュリティ artifact であり業務規則ではないため、route handler で state cookie と query の一致を見てから usecase を呼ぶ。具体的な signing 方式は session_security の B 決定に委ねる）。

### C-3: レート枠切替と Issue #122（RateLimitPort）は別物 — 二重実装の回避

**claim**: 「ログインで自分のレート枠に切り替わる」は **`RateLimitPort` と無関係**。`RateLimitPort`/`WorkersRateLimit`（`src/infrastructure/platform/rate-limit.ts`）は **自分たち（gem-hunter）の共有 installation token を乱用から守るための「発信リクエストの間引き」**（INF-n/NFR-7・Cloudflare Rate Limiting binding）であり、ログイン状態と無関係に全リクエストへ一律適用されるべきもの。

一方「レート枠切替」の実体は、`GithubRepositoryQuery` に渡す **`TokenProvider`**（`src/infrastructure/github/github-repository-query.ts` で定義済み・infra 内部の型でドメインポートではない）を **installation token 用（`makeInstallationTokenProvider`）からユーザーのアクセストークン用に差し替える** だけの composition root 配線変更である。

**evidence**: `container.ts` の `makeCachingRepositoryQuery()` は `token: makeInstallationTokenProvider(...)` を固定で渡している。`searchRepositoriesUseCase()` / `getRepositoryDetailUseCase()` を `(accessToken?: string | null)` を受け取る形に拡張し、`accessToken` があればそれを返す `TokenProvider`、無ければ既存の installation token provider を使う。**新しいドメインポートは不要**（`TokenProvider` は既に infra 内で抽象化済み）。

**二重実装の回避策**: Issue #122（`RateLimitPort` を composition root と全経路へ配線）は SP-8 のスコープ外として別 Issue のまま進める（CP-1: 起票済みなら着手は別スコープ）。もし同一 PR で着手する場合でも、**`RateLimitPort` の配線と `TokenProvider` 切り替えは `src/composition/container.ts` 内の別々の関数・別々の関心事として実装し**、片方がもう片方の判定条件（ログイン有無）を参照しない設計にする（レート制限は未ログインユーザーの乱用対策として最も必要な機能であり、ログイン状態で挙動を分岐させると本来の目的が壊れる）。

### C-4: 言語切替 UI（US-2）の実装層と Locale 値オブジェクトの統合

**claim**: 新規ユースケース・新規ポートは不要（純粋な画面遷移）。

- `src/ui/url/build-locale-url.ts`: 現在の pathname + 対象 `Locale` から遷移先 URL を組み立てる純粋関数（`src/ui/url/build-search-url.ts` と同じ置き場所・パターン）。`domain/model/locale.ts` の `Locale` 型（値オブジェクト）のみ import（ARCH の Presentation 行「型と値オブジェクトのみ」）。
- `src/ui/locale-switcher.tsx`: 上記関数を使って ja/en の 2 リンクを描画する表示コンポーネント。`app/[locale]/layout.tsx` から呼び出す（`app/` は `src/ui/**` を import してよい）。
- 表示文言は `messages/ja.json` / `messages/en.json` に追記（`src/shared/i18n/` 経由、既存パターン踏襲）。

**根拠**: `architecture-rules.md` §1 の判定フロー「② React の描画か? → はい: src/ui/」。ドメインの `Locale` 値オブジェクトを import はするが、認証や Cookie とは無関係で新規ポートを要求しない。

### まとめ（争点 C の結論案）

| # | 決定 | artifacts |
|---|---|---|
| C-1 | OAuth 3 route handler は薄く、`src/composition/auth.ts` 経由でのみ実装へアクセス | `app/api/auth/login/route.ts`（新規）/ `app/api/auth/callback/route.ts`（新規）/ `app/api/auth/logout/route.ts`（新規）/ `src/composition/auth.ts`（新規） |
| C-2 | `AuthPort` を新設し usecase はポート経由（ARCH-2）。ドメインに GitHub/OAuth/Cookie を漏らさない | `src/domain/ports/auth-port.ts`（新規）/ `src/usecases/complete-login.ts`（新規）/ `src/infrastructure/github/oauth.ts`（新規）/ `src/infrastructure/platform/session-cookie.ts`（新規）/ `application-architecture.md` §2 ポート表（改修・W-3 根拠追記） |
| C-3 | レート枠切替 = `TokenProvider` の composition root 差し替え。`RateLimitPort`（#122）とは無関係な別配線として扱い、同一関数に混在させない | `src/composition/container.ts`（改修：`searchRepositoriesUseCase(accessToken?)` 等） |
| C-4 | 言語切替 UI は `src/ui/` の表示コンポーネント + `src/ui/url/` の純粋関数のみ。新規ポート・usecase 不要 | `src/ui/locale-switcher.tsx`（新規）/ `src/ui/url/build-locale-url.ts`（新規）/ `messages/ja.json` `messages/en.json`（改修） |

**open_questions（自分のレンズでは確証が持てない・A/B 担当への申し送り）**: CSRF state cookie の signing 方式（jose JWS/JWE のどちらで、有効期限をどう持たせるか）は session_security の決定待ち。auth_flow の争点 A（自前実装 vs ライブラリ）の結論次第で `src/infrastructure/github/oauth.ts` の中身（authorize URL 組み立て・token 交換）は変わるが、置き場所（layer 配置）自体は結論に依存しない。

### `verify_test` — 主張
<sub>2026-08-20T07:18:02+09:00</sub>

## claim（verify_test・争点 D 主担当）

### 1. E2E スタブ拡張: OAuth authorize/token/user を `e2e/stub/server.mjs` に追加する

**方式**: 実 GitHub の同意画面を模す HTML/フォームは不要。ブラウザ（Playwright）が実際にリダイレクトチェーンを辿れるよう、stub は `authorize` を **即座に 302 で `redirect_uri` へ返す**（同意済みユーザーとして扱う）。

| メソッド | パス | 挙動 |
|---|---|---|
| `GET` | `/login/oauth/authorize` | クエリの `state` をそのまま引き継ぎ `302 Location: {redirect_uri}?code=stub-authz-code&state={state}` を返す（`client_id`/`redirect_uri` の値検証はしない＝stub はレジストリを持たない） |
| `POST` | `/login/oauth/access_token` | `code`/`client_id`/`client_secret` を受け取り（form-urlencoded or JSON どちらも許容）`{"access_token":"stub-access-token","token_type":"bearer","scope":""}` を JSON で返す（実 GitHub は `Accept: application/json` 必須のため、アプリ側実装はこのヘッダを必ず送る） |
| `GET` | `/user` | `Authorization: Bearer stub-access-token`（または `token stub-access-token`）のときのみ `{"login":"octostub-user","id":999001,"avatar_url":"<既存の1x1 data URI 使い回し>"}` を返す。ヘッダ不一致は `401` |

**衝突しない理由（E-11 の懸念への回答）**:
- パスが独立（`/login/oauth/*`・`/user` は `/search/repositories`・`/repos/{owner}/{repo}` と非重複。`/user` は `/repos/([^/]+)/([^/]+)` の 2 セグメント正規表現と衝突しない）。
- 唯一の注意点は **メソッド分岐の順序**: 既存コードは `if (req.method !== 'GET') return 405` を先に評価している（`/__stats/reset` の POST だけ例外的に先出し）。`POST /login/oauth/access_token` も同様に **405 判定より前** に分岐を置く必要がある（実装漏れると全 OAuth E2E が 405 で落ちる）。
- キーワード規約（`zero-hits`/`rate-limit`/`many-hits` 等）は `q` パラメータのみを見るため OAuth ルートとは無関係。ダミー `client_id`/`code` の値衝突も起きない（stub は値を検証しないため）。

### 2. オリジン切替の env 設計（`GITHUB_API_ORIGIN` の先例を踏襲）

`src/infrastructure/github/github-repository-query.ts` は既に `GITHUB_API_ORIGIN`（ループバックのみ許可・外部ホスト指定は例外送出）でスタブ差し替えを実現している（同ファイル 22-35 行、テストは `github-repository-query.test.ts`）。OAuth 側も同じ安全設計を踏襲すべきと考える:

- **新設 env**: `GITHUB_OAUTH_ORIGIN`（既定 `https://github.com`。`authorize`/`access_token` の宛先を差し替える）。**`GITHUB_API_ORIGIN` と検証ロジックを共有する**（ループバックのみ許可・トークン漏洩防止の理由も同じ）。実 GitHub では `github.com`（OAuth）と `api.github.com`（REST/`/user`）はホストが別だが、E2E では両方を同一スタブ（`127.0.0.1:8788`）に向ければ 1 プロセスで足りる。
- `GET /user` は REST API 相当のため `GITHUB_API_ORIGIN` 側で叩く（新規 env を増やさない）。
- 追加で必要なダミー設定（プレビュー無効化と同じ「未設定なら機能を出さない」設計との整合）: `GITHUB_OAUTH_CLIENT_ID` / `GITHUB_OAUTH_CLIENT_SECRET` / `GITHUB_OAUTH_CALLBACK_URL`（infra-design.md AR-5 の「callback URL は環境変数化」）。値の中身は stub が検証しないため任意の固定文字列でよい。

### 3. `playwright.config.ts` の `webServer` env ブロックを拡張するだけで手順が完結する（新規スクリプト不要）

infra-design.md §8.1 の「ダミー OAuth 設定を注入したローカルビルド」は、実は **SP-4 から既にある `webServer`（`node e2e/stub/server.mjs` → `npm run build && npm start -- --port 3100`）そのもの**。プレビュー URL を使わずローカルビルドに対して実行する、という要件はこの構成が既に満たしている。追加が要るのは env だけ:

```js
{
  command: `npm run build && npm start -- --port 3100`,
  env: {
    GITHUB_API_ORIGIN: `http://127.0.0.1:${stubPort}`,
    GITHUB_OAUTH_ORIGIN: `http://127.0.0.1:${stubPort}`,   // 新規
    GITHUB_OAUTH_CLIENT_ID: 'e2e-dummy-client-id',           // 新規
    GITHUB_OAUTH_CLIENT_SECRET: 'e2e-dummy-client-secret',   // 新規
    GITHUB_OAUTH_CALLBACK_URL: 'http://127.0.0.1:3100/api/auth/callback', // 新規（実パスは clean_arch 決定に追随）
    SESSION_ENCRYPTION_KEY: '<E2E固定ダミー鍵・本番とは別値>',            // 新規（session_security 決定に追随）
    PORT: '3100',
  },
  url: baseURL,
  ...
}
```

起動コマンドは変わらず `npm run test:e2e`（= `npm run check` 経由）のまま。**プレビュー環境向けに OAuth を無効化する分岐（§8.1 (a)）は、これらの env が未設定のときに自然に発生する**（アプリ側が「OAuth 関連 env が揃っているかだけで分岐」を守っていれば、プレビュー env ブロックに OAuth 系変数を足さないだけで済み、環境判定コードは書かずに済む）。

### 4. 4 つの操作レビュー手順をどう機械的に assert するか

新規 `e2e/sp-8.spec.ts` を作り、手順 1 行 = 1 `test.step()` にそのまま写す（`testing-strategy.md` §5 の規約）。

1. **未ログインで全機能が使える**: 既存 `sp-1.spec.ts` 相当の検索フローを未ログイン状態でなぞるだけ（新規ロジック不要・回帰確認）。
2. **ログイン → レート枠が自分のものに切り替わる**: 検証方法は 2 案あり、**両方を実装することを推奨**（片方が UI 実装の有無に依存するため）。
   - **案 2a（確実・UI 非依存）**: `/__stats` を `authorizedSearchCount` 等に拡張し、stub が受信したリクエストの `Authorization` ヘッダ有無をカウントする。ログイン前は素通し（未カウント）、ログイン後の検索操作でカウントが増えることを assert する。既存の `searchCount`/`detailCount` は加算元のまま壊さない（フィールド追加のみ・後方互換）。
   - **案 2b（UI があれば併用）**: stub の `/search/repositories` `/repos/...` レスポンスに `x-ratelimit-limit`/`x-ratelimit-remaining` ヘッダを常時付与し、`Authorization` ヘッダの有無で値を変える（未認証 60 / 認証済み 5000 の実 GitHub 挙動を模す）。UI がこの値を表示するなら文言の変化を assert できる。**UI 表示の要否は clean_arch/PO 側の決定次第**なので、2a を最低ラインとして提案する。
3. **ログアウト → 元に戻る**: ログアウト操作後に 2a の判定が「未認証扱い」に戻ることを assert（Cookie が消え、以降のリクエストに `Authorization` が付かない）。
4. **言語切替**: 既存の i18n 基盤（`locale-redirect.ts` 等）に対する回帰 E2E は既にあるはず（要確認）。SP-8 で新規に足すのは「切替 UI（US-2）をクリックした後に URL が `/en/...` になり、既存文言が英語になるが、スタブが返すリポジトリ `description` は原文のまま」の assert。**既存の検索・詳細フィクスチャ（`e2e/fixtures/repos.json`）を流用でき、新規フィクスチャは不要**。

### 5. TDD の Red をどの順に書くか

`testing-strategy.md` §5（外側 E2E Red → 内側ユニット Red/Green/Refactor の二重ループ）に従う。SP-8 は `SP-4` 以降なので緩和なし（全項目必須）。

1. **外側 Red を先に書く**: `e2e/sp-8.spec.ts` を 4 手順分そのまま書く。ログイン導線が存在しないため **この時点で全 4 ステップが Red**（stub 拡張前でもここまでは書ける＝ stub 拡張を待たずに着手できる）。
2. **stub 拡張は「テスト」ではなく「テストインフラ」**: `e2e/stub/server.mjs` 自体に単体テストは無い（既存の `zero-hits`/`rate-limit` 等の分岐も同様に無テストで、E2E 経由でのみ検証される先例に合わせる）。stub 拡張は 1 のコミットの一部として先に用意し、それ自体を Red/Green の対象にしない。
3. **内側ユニットは値オブジェクト → ユースケース → ACL → route handler の順**（層の決定は clean_arch 案に従うが、テスト順序としては下位層から）:
   - state パラメータ生成・検証ロジック（純粋関数 or 値オブジェクト）
   - セッション暗号化/復号（`jose` ラッパー）
   - OAuth コールバックのユースケース（`code` → トークン交換 → セッション生成）
   - トークン交換失敗時のエラー変換（ACL: stub の 401/エラー応答 → ドメインエラー）
4. **最後に外側 E2E を再実行して Green** にする（`npm run test:e2e` 全体・既存 SP-1〜7 の回帰も含めて緑を確認）。

### 6. 未解決として残す点（自分のレンズでは決め切れない）

- UI が「レート枠」の数値を表示するか、単にログイン状態バッジのみか（案 2a で最低限は検証可能なので、E2E 側はブロッカーにならない）。
- session Cookie の暗号化方式・state の保存先（session_security 案に依存。E2E 側は「stub が返した state をそのまま往復させれば良い」という前提のみ持つ）。
- OAuth を自前実装するか Auth.js か（auth_flow 案に依存。ただし Auth.js を採用する場合でも、上記の stub エンドポイント構成・env 差し替え方式は provider 設定の変更のみで流用可能なはずで、検証手段としての前提は変わらない）。

## 1 行サマリー
OAuth authorize/token/user を `e2e/stub/server.mjs` に追加し（メソッド分岐順序に注意すれば既存 REST モックと非衝突）、`GITHUB_OAUTH_ORIGIN` を `GITHUB_API_ORIGIN` と同じループバック限定設計で新設、`playwright.config.ts` の既存 `webServer`（ローカルビルド構成）に env を足すだけで infra-design §8.1 のダミー OAuth ローカル実行手順が完結し、4 操作レビューは `/__stats` の `Authorization` ヘッダ計測で UI 非依存に機械 assert できる。

## ラウンド 2

### `session_security` — 反論
<sub>2026-08-20T07:20:37+09:00</sub>

## rebuttal（session_security・争点 B・round 2）

round1 の自分の claim（JWE + 二次 Cookie 方式）を基準に、他 3 者の投稿を突き合わせた結果、**2 点の実質的な指摘**と**1 点の命名収束依頼**がある。

---

### 指摘 1（clean_arch 向け・訂正）: state Cookie の signing 方式は「未決」ではなく「不要」と round1 で既に結論済み

`clean_arch` の open_questions は次のように書いている:

> 「CSRF state cookie の signing 方式（jose JWS/JWE のどちらで、有効期限をどう持たせるか）は session_security の決定待ち」

これは round1 の自分の claim（根拠 4）を読み違えている。自分の結論は「**どちらか選ぶ**」ではなく「**state Cookie 自体には署名も暗号化も不要**」というものだった:

> 「この state Cookie 自体を暗号化・署名する必要はない（YAGNI）。値そのものに秘匿情報を含まず、サーバーが発行してサーバーが検証するだけの『サーバー側が書いた値をサーバー側が読み返す』用途であり、httpOnly + Secure により JS からの読み取り・改ざんは防げる」

理由を補強する: `jose` で JWS/JWE 化すると鍵管理・有効期限フォーマット・パース失敗時のエラーハンドリングという余計な失敗モードが増えるだけで、得られるセキュリティ上の利益がない（値の真正性は「Cookie ジャーに書けるのはサーバーだけ」という httpOnly 前提から既に得られている）。したがって **verdict の `open_questions` にこの論点を残すべきではない**（`sprint-development-rules-detail.md` §3.3 の 3 条件に照らしても「両案とも筋が通り選択で成果物が変わる」わけではなく、既に技術的に一意に決まる論点であり第 2 系統の確認対象にならない）。lead の synthesizer には「state Cookie は非暗号化・非署名の生ランダム値」と明記してほしい。

（有効期限については round1 で既に「短命・例えば 10 分」と示している。JWE のセッション Cookie の `exp` とは別軸で、state Cookie は `Max-Age` で十分——ここも jose 側の `exp` クレーム機構は使わない。）

---

### 指摘 2（verify_test 向け・懸念）: ローカル E2E トポロジでは `SameSite=Lax` の選択自体を検証できない

`verify_test` の E2E 設計は app（`127.0.0.1:3100`）と OAuth stub（`127.0.0.1:{stubPort}`）をどちらも `127.0.0.1` 上に置き、`authorize` からの 302 リダイレクトをブラウザに実際に辿らせる方式（`GET /login/oauth/authorize` → `302 Location: {redirect_uri}?code=...&state=...`）を採っている。

これは自分の round1 claim（根拠 4）の「`SameSite=Lax` である理由: GitHub からのリダイレクトバックはトップレベル GET ナビゲーションであり、`Lax` はこのケースで Cookie を送出する（`Strict` だと送られず state 検証が常に失敗する）」という設計判断そのものを検証できない、という点で **verify_test の E2E 方式には見落としがある**。

**理由**: `SameSite` の判定基準は「site（実効 TLD+1 に相当する単位）」であり、IP アドレスの場合は **ホスト全体が 1 つの site** として扱われる（ポート番号は site 判定に含まれない）。したがって `127.0.0.1:3100` と `127.0.0.1:{stubPort}` は同一 site（ポートが違うだけで同一ホスト `127.0.0.1`）となり、ブラウザからは "same-site" ナビゲーションとして扱われる。**本番環境（`github.com` → 自アプリのドメイン）は明確に cross-site だが、この E2E トポロジでは cross-site を再現できていない。**

つまり、`oauth_state` Cookie に誤って `SameSite=Strict` を設定してしまうバグを実装しても、この E2E は redirect 後も Cookie が送出されるため **green のまま通ってしまい**、本番デプロイ後に初めて「ログインが必ず state 不一致で失敗する」という形で顕在化する。これは NFR-23（主要フローのテストを持つ）が実質的にカバーできていない回帰リスクであり、`verify_test` の検証設計に対する具体的な gap 指摘として提示する。

**対応案（2 択ではなく積み増しで解決可能・実装手段の選択なので確認不要）**:
- E2E に加えて、`oauth_state` Cookie を発行するハンドラの **単体/結合テストで `Set-Cookie` レスポンスヘッダ文字列に `SameSite=Lax` が含まれることを直接 assert** する（ブラウザの実ナビゲーション挙動に依存しない、ヘッダ内容そのものの検証）。これなら `SameSite` 属性の実装漏れ・退行を機械的に検出できる。
- 併せて、E2E 側のコメントに「このテストは cross-site Cookie 送出の実地検証はできない（ローカル同一ホストのため）」と明記し、以降のセッションが誤って「E2E が緑だから SameSite は安全」と誤読しないようにする。

---

### 命名収束の依頼（矛盾ではないが揃えたい）

- state Cookie 名: 自分は round1 で `gh_oauth_state`（例示）としたが、`auth_flow` の具体シーケンスは既に `oauth_state` を使っている。verify_test の実装が auth_flow のシーケンス記述に従って進む可能性が高いため、**`oauth_state` に統一する**（自分の案を撤回し auth_flow に合わせる）。矛盾ではなく自分から譲る。

---

### concession（同意点）

- `auth_flow` の環境変数命名（`GITHUB_OAUTH_CLIENT_ID` / `GITHUB_OAUTH_CLIENT_SECRET` / `GITHUB_OAUTH_CALLBACK_URL`）は自分が round1 で挙げた例示と自然に一致しており、そのまま採用に同意する。
- `clean_arch` の C-2（`AuthPort.exchangeAuthorizationCode` は `{ accessToken }` のみを返し、Cookie 生成・state 検証は usecase の外＝route handler と `session-cookie.ts` が担当）は、自分の「秘匿値を読むコードパスを 1〜2 ファイルに閉じ込める」という round1 の要求を正確に満たしている。`session-cookie.ts` を `platform/`、`oauth.ts` を `github/` に分けた配置にも異存なし（`SESSION_ENCRYPTION_KEY` を読むのは `session-cookie.ts` だけ、`GITHUB_OAUTH_CLIENT_SECRET` を読むのは `oauth.ts` だけ、という分離が両立している）。
- `verify_test` の env 命名（`SESSION_ENCRYPTION_KEY` にダミー固定値を注入する方式）は自分が round1 の「他レンズへの申し送り」で提案した内容とそのまま一致しており、追加の指摘なし。

### `auth_flow` — 反論
<sub>2026-08-20T07:20:54+09:00</sub>

## rebuttal（争点 A・round1 の自分の分析とホワイトボードのみに基づく）

`clean_arch` の route handler 配置案（`src/composition/auth.ts` 経由・`AuthPort` 新設）と `session_security` の CSRF state 実装案（二次 Cookie）を、自分の round1 シーケンス案（`GET /api/auth/github/authorize` → `GET /api/auth/github/callback` → `POST /api/auth/logout`）と突き合わせた結果、**2 点の不整合**と **1 点の見落とし**を見つけた。いずれも「自前実装」という結論そのものは揺るがないが、シーケンス具体化の中身を修正する必要がある。

### 指摘 1: route パス命名が自分の案と食い違っている（要解決・優先度高）

- 自分（round1）: `GET /api/auth/github/authorize` / `GET /api/auth/github/callback` / `POST /api/auth/logout`（`github` セグメントを挟む）
- `clean_arch`（C-1）: `app/api/auth/{login,callback,logout}/route.ts`（`github` セグメントなし、`authorize` ではなく `login`）
- `verify_test`（§2・§3）: `GITHUB_OAUTH_CALLBACK_URL: 'http://127.0.0.1:3100/api/auth/callback'` — `clean_arch` の命名にすでに追随している

**この不一致は「実装手段の些末な違い」ではなく実害がある**: `GITHUB_OAUTH_CALLBACK_URL` は GitHub OAuth App 登録時に**完全一致**でコールバック URL を事前登録する値であり、`app/` のファイルパスと 1 対 1 対応する。3 者が別々のパスを前提にしたまま実装が分岐すると、登録した OAuth App のコールバック URL とルートハンドラの実パスが食い違い、GitHub 側で `redirect_uri_mismatch` エラーになる。

**self-correction**: `clean_arch` と `verify_test` が既に 2 対 1 で `/api/auth/login` `/api/auth/callback` `/api/auth/logout`（`github` セグメントなし）に収束している。自分の round1 案を撤回し、この命名に合わせる。理由も妥当— `RepositoryQueryPort` が事業者名を冠さないのと同じ命名規律（`clean_arch` C-2 のドメイン純度チェック）を、URL パスにも延長したものと解釈できる（現時点で GitHub 単一プロバイダでも、将来の拡張時にパスを壊さずに済む）。**環境変数設計の `GITHUB_OAUTH_CALLBACK_URL` 例示値を `http://localhost:3000/api/auth/github/callback` → `http://localhost:3000/api/auth/callback` に訂正する**。

### 指摘 2: `AuthPort` の戻り値が自分のシーケンス案（`/user` 取得）より狭い（要解決）

- `clean_arch`（C-2）: `AuthPort.exchangeAuthorizationCode(code): Promise<{ accessToken: string }>` — 戻り値は `accessToken` のみ
- 自分（round1・シーケンス手順 3）: token 交換の後に `GET https://api.github.com/user` を追加で叩き、login/avatar を取得してセッションに含める、と書いた

これは食い違いというより **自分の round1 案がスコープを広げすぎていた**と考える。根拠:
- SP-8 の操作レビュー対象は「ログインするとレート枠が自分のものに切り替わる／ログアウトすると元に戻る」であり、ユーザー名・アバター表示は AC に明記がない。
- `verify_test`（§4-2, §6）も「UI がレート枠の数値を表示するか単なるログイン状態バッジのみか」を **自分のレンズでは決め切れない未解決点**として明示しており、`/user` 呼び出しを前提にしていない。E2E の 2a 案（`Authorization` ヘッダの有無をカウント）も `/user` 抜きで成立する。
- `D-6`（機能差を作らない・上乗せ最小主義）に照らすと、AC に無い「ログイン中ユーザー名の表示」のために GitHub API 呼び出しを 1 本追加するのは過剰実装（YAGNI）。ログイン状態の UI 表示が要るなら「セッション Cookie の有無」という真偽値だけで足り、GitHub `/user` は不要。

**訂正**: 自分の round1 シーケンス手順 3 から「`GET /user` で login/avatar を取得」を削除し、`clean_arch` の `AuthPort.exchangeAuthorizationCode(code): Promise<{ accessToken: string }>` にそのまま整合させる。ログイン状態表示が将来要件として浮上した場合のみ、別途 `/user` 取得を追加する（本スプリントのタスクには含めない）。

### 指摘 3（自分の round1 案への自己修正）: ログイン導線の表示ゲートが `session_security` の鍵管理と噛み合っていない

- 自分（round1・環境変数設計）: 「`GITHUB_OAUTH_CLIENT_ID` / `_CLIENT_SECRET` / `_CALLBACK_URL` の 3 変数が揃っているか」だけでログインリンクの表示を判定する、と書いた
- `session_security`（根拠 6・アルゴリズム選定の補足）: セッション Cookie の暗号化に **`SESSION_ENCRYPTION_KEY`（32byte 対称鍵）を別途要求**しており、`readCredentials()` パターン（未設定なら `null` で機能無効化）をこの鍵にも適用すべきと述べている

自分の 3 変数ゲートには `SESSION_ENCRYPTION_KEY` が入っていない。もし OAuth 側 3 変数だけ揃って `SESSION_ENCRYPTION_KEY` が未設定という状態が起きると、ログインリンクは表示されるのに callback でセッション Cookie を発行しようとして例外になる（`infrastructure-design.md` §8.1 が求める「環境変数未設定で静かに機能が消える」に反し、静かにではなく壊れて出る）。

**訂正**: ログイン導線の表示可否を判定する真偽値は、OAuth 3 変数 **に加えて** `SESSION_ENCRYPTION_KEY` の計 4 変数が揃っているかで判定するよう一本化する（`clean_arch` C-1 の `src/composition/auth.ts` に集約するのが適切 — composition root は OAuth 側とセッション側の両方の設定可否を横断的に見られる唯一の層のため）。`verify_test` の E2E env ブロック（§3）は既に 4 変数すべてを列挙済みで、この訂正と矛盾しない。

### 確認（矛盾なし・整合を確認できた点）

- `clean_arch` C-2 の「CSRF state 検証は usecase の外・route handler で state cookie と query の一致を見てから usecase を呼ぶ」は、自分の round1 シーケンス手順 3（「`oauth_state` Cookie と query の `state` を照合 → 一致なら token 交換」という順序）と**完全に一致**している。
- `session_security` の二次 Cookie 方式（`gh_oauth_state`・非暗号化・httpOnly・`SameSite=Lax`・10 分）は自分の round1 案「短命 `oauth_state` Cookie」の具体化そのもので矛盾しない。

### `auth_flow` — 譲歩
<sub>2026-08-20T07:20:54+09:00</sub>

## concession（争点 A・他レンズの round1 主張への同意）

- `clean_arch` C-1/C-2 の層配置案（`AuthPort` + `src/infrastructure/github/oauth.ts` + `src/composition/auth.ts` 経由の薄い route handler）は、自分が根拠 4 で主張した「自前実装なら GitHub 資格情報を `ARCH-5` どおり `src/infrastructure/github/` に完全に閉じ込められる」を実際の型・ファイル構成に落とし込んだものであり、**争点 A で Auth.js を rejected とした自分の結論をそのまま補強する**。`clean_arch` 自身が「争点 A の結論次第で `oauth.ts` の中身は変わるが置き場所は結論に依存しない」と書いている通り、この設計は自前実装を前提にしたときに最も自然に嵌まる（Auth.js 採用時は `NextAuth(config)` 一括宣言との整合を取るための追加ラッパーが要るという自分の根拠 4 が改めて裏付けられた）。
- `session_security` の CSRF state 方式（authorize 直前に生成 → 短命二次 Cookie に保存 → callback で query と厳密一致比較 → 使い捨てで即削除、`SameSite=Lax` の理由付けも含む）は、自分の round1 シーケンスの該当部分と設計思想・実装順序ともに一致しており、そのまま採用してよいと考える。
- `verify_test` の「Auth.js 採用でも stub エンドポイント構成・env 差し替え方式は provider 設定の変更のみで流用可能」という指摘には同意する（検証手段の独立性という点で正しい）。ただしこれは争点 A の判断材料にはならない（`verify_test` 自身も「検証可能性は自前実装かライブラリかに依存しない」と明言しており、争点 A の決定は根拠 1〜4 の理由で自前実装のまま変わらない）。

### `clean_arch` — 反論
<sub>2026-08-20T07:21:02+09:00</sub>

## clean_arch（層と依存規則・争点 C）Round 2 rebuttal

### 反論 1: route handler のパス命名が 3 者で不一致（要一本化）

- `auth_flow`: `GET /api/auth/github/authorize` → `GET /api/auth/github/callback` → `POST /api/auth/logout`
- `clean_arch`（自分・round1）: `app/api/auth/{login,callback,logout}/route.ts`
- `verify_test`: `GITHUB_OAUTH_CALLBACK_URL: 'http://127.0.0.1:3100/api/auth/callback'`（コメントで「実パスは clean_arch 決定に追随」と明記）

**指摘**: `auth_flow` の `/api/auth/github/...`（provider 名をパスに埋め込む案）と、私・`verify_test` が前提にした `/api/auth/...`（provider 名なし）が食い違ったまま round1 が終わっている。`verify_test` は既に私の round1 案に追随して env を書いているため、**このまま実装に入ると `verify_test` の env のコールバック URL と `auth_flow` が書くコード側のルートパスが一致せず、E2E が 404 で落ちる**。

**裁定（層配置の担当としての結論）**: `/api/auth/login`・`/api/auth/callback`・`/api/auth/logout`（provider 名なし）を採用する。理由: ①現状 provider は GitHub 固定の製品決定（`D-6`）で複数プロバイダ対応の予定はなく、`RepositoryQueryPort` 同様「実装は GitHub 限定でも外部から見える名前は事業者中立にする」規律をパスにも踏襲する方が既存パターンと一貫する、②`verify_test` が先に書いた env と揃えれば手戻りがゼロで済む。`auth_flow` はこの命名で実装してほしい（実装手段レベルの差分でありユーザー確認は不要・`SD-3` 対象外）。

### 反論 2: `auth_flow` のシーケンス手順 3（`GET https://api.github.com/user` 取得）が自分の `AuthPort` 設計から漏れている

**指摘**: `auth_flow` の claim 「シーケンス具体化」手順 3 は、token 交換の後に **`GET https://api.github.com/user`（プロフィール取得）を追加で叩く**設計になっている。これは `RepositoryQueryPort` の対象外の新しい GitHub API 呼び出しであり、私の round1 `AuthPort`（`exchangeAuthorizationCode(code): Promise<{ accessToken: string }>` のみ）はこの呼び出しを表現できていない。このままだと、この `/user` 呼び出しが `callback` route handler や `oauth.ts` 内のどこかに **場当たり的に実装され、`AuthPort` を経由しない生 `fetch` として route handler 側に漏れ出すリスク**がある（`ARCH-5` 違反・`ARCH-2` のポート注入原則からの逸脱）。

**裁定**: SP-8 の操作レビュー手順（brief 記載の 4 項目）に「ユーザー名・アバター表示」は含まれておらず、`verify_test` の E2E 案（案 2a: `Authorization` ヘッダ有無のカウント）も `/user` 呼び出しの結果に依存していない。**YAGNI により `/user` プロフィール取得は SP-8 スコープ外として一旦落とす**（`completeLogin` usecase は `AuthPort.exchangeAuthorizationCode` のみでよい）ことを提案する。もし後続 UI 検討で「ログイン中: ○○」のようなユーザー名表示が必要になった場合は、`AuthPort` に `fetchViewer(accessToken): Promise<{ login: string; avatarUrl: string } | null>` を追加し `src/infrastructure/github/oauth.ts`（or 既存 `github-repository-query.ts` 隣接）に実装する、という拡張パスを明記しておく（今 fetch を route handler に直書きしない限り、後から足しても層は壊れない）。`auth_flow` にはこの縮小 or 拡張パスのどちらかを round2 で明示してもらいたい。

### 反論 3（自分の round1 案の修正）: `session-cookie.ts` の責務を「暗号化セッション Cookie」だけに絞る

`session_security` の claim（根拠4）で、CSRF `state` は **非暗号化の単純ランダム値**を短命 Cookie に置くだけでよく、暗号化・署名は不要と明言されている。これは私の round1 `src/composition/auth.ts` の `encodeSessionCookie`/`decodeSessionCookie`（=セッション本体用の JWE ラッパー）とは **別物**であり、`state` Cookie の読み書きは `next/server` の標準 Cookie API を **route handler が直接呼べばよく**、composition root/infra を経由させる必要がない（暗号鍵などの秘匿値に触れないため）。

**修正**: round1 の C-1 に「`state` Cookie の生成・照合は `app/api/auth/{login,callback}/route.ts` が `next/server` の Cookie API で直接行い、`src/composition/auth.ts` を経由しない（秘匿値を扱わないため ARCH-3 の対象外）」を追記する。`encodeSessionCookie`/`decodeSessionCookie` は **ログイン確立後の本セッション Cookie 専用**に限定する。

## 同意（concession）

- `session_security` 根拠6「秘匿値を読むコードパスを 1〜2 ファイルに閉じ込める」は自分の C-1/C-2（`src/infrastructure/github/oauth.ts` + `src/infrastructure/platform/session-cookie.ts` の 2 ファイル）とちょうど一致する。**そのまま採用**。
- `session_security` の「state 検証は usecase の外・暗号化不要」は自分の C-2「CSRF state 検証も usecase の外」と完全に一致する。**そのまま採用**（反論 3 は補足であり矛盾ではない）。
- `verify_test` の D 案（`/__stats` の `Authorization` ヘッダ計測で UI 非依存にレート枠切替を assert）は、自分の C-3（レート枠切替 = composition root での `TokenProvider` 差し替え、UI 表示は必須要件でない）と整合する。E2E がユーザー名・レート枠数値の UI 表示に依存しないことは、反論 2 で `/user` 取得を落とす提案の裏付けにもなる。**採用**。
- `auth_flow` の根拠4（Auth.js 不採用なら GitHub 固有ロジックを `infrastructure/github/` に完全に閉じ込められる）は自分の C-1/C-2 の前提と一致する。**採用**。
- `RateLimitPort`（Issue #122）との切り分け（C-3）について、他 3 者から反論・言及がなかったため、round1 の結論（レート枠切替 = `TokenProvider` 差し替え、`RateLimitPort` とは別配線・別関数）を維持する。

## 1 行サマリー
route handler パスを `/api/auth/{login,callback,logout}`（provider 名なし）に一本化、`auth_flow` の `/user` プロフィール取得は SP-8 スコープ外に落とすか `AuthPort.fetchViewer` として明示的に層へ位置づけるかを求め、`state` Cookie は composition root を経由しない直書きに限定する形で C-1/C-2 を修正。

### `verify_test` — 反論
<sub>2026-08-20T07:21:29+09:00</sub>

## rebuttal（verify_test・round 2）

### R-1: auth_flow と clean_arch のルートパス命名が矛盾しており、私の webServer env 値・E2E ナビゲーション先が確定できない

- `auth_flow`（争点 A シーケンス）: `GET /api/auth/github/authorize` → `GET /api/auth/github/callback`（**`github` セグメントあり・開始点名は `authorize`**）
- `clean_arch`（C-1）: `app/api/auth/{login,callback,logout}/route.ts`（**`github` セグメントなし・開始点名は `login`**）

両者は `logout` 以外で一致していない。私は round1 で `GITHUB_OAUTH_CALLBACK_URL: 'http://127.0.0.1:3100/api/auth/callback'` と書いたが、これは clean_arch 案に合わせた仮置きであり、auth_flow 案（`/api/auth/github/callback`）を採用するなら env の値も E2E の `page.goto`/クリック先も変わる。**これは自分のレンズだけでは決められない（成果物＝E2E スペックのコード自体が変わる分岐）**。

**提案**: clean_arch 案（`app/api/auth/login|callback|logout/route.ts`、`github` セグメントなし）を採用する。理由: 既存の `app/api/search/route.ts` 前例（`architecture-rules.md` ARCH-3）は事業者名をパスに含めない命名になっており一貫性が高い。auth_flow はシーケンス説明の中で書いただけで「争点 C の決定案」として明記していないため、命名の正本は C-1 側にあると見なすのが自然。**lead には「この 1 点だけ auth_flow 側の記述を C-1 に合わせて訂正する」よう明記してほしい。**

### R-2: 自分の `/__stats` 検証設計（Authorization ヘッダ有無）は clean_arch の C-3（TokenProvider 差し替え）と整合しない — 自己修正が必要

round1 で私は「ログイン前は `Authorization` ヘッダなし・ログイン後に付与される」という前提で `authorizedSearchCount` を提案したが、これは **誤り**。clean_arch の C-3 で明言されている: `container.ts` の `makeCachingRepositoryQuery()` は **現状すでに** `token: makeInstallationTokenProvider(...)` を固定で渡しており、**未ログインの検索リクエストにも installation token の `Authorization` ヘッダが常に付いている**。ログイン後は `TokenProvider` が installation token からユーザーのアクセストークンに **差し替わる** だけで、「ヘッダの有無」ではなく「**ヘッダの値**」が変わる。

**修正案**: `/__stats` の計測軸を「`Authorization` ヘッダの有無」から「**値が stub 発行のユーザートークン（`stub-access-token` 等の固定文字列）と一致するリクエスト数**」に変更する（例: `userAuthSearchCount` / `userAuthDetailCount`）。ログイン前は installation token 固定値（既存 E2E 環境が使っているダミー installation 資格情報由来のトークン。具体的な値は installation-token 側の実装を持つセッションに確認が必要＝ 自分のレンズの外）でマッチせず 0、ログイン後にユーザートークンへ切り替わってからカウントが増える、という assert に直す。**この修正を経ても検証手段自体は成立する**（stub がリクエストの `Authorization` 値を見て分岐する、という設計の骨格は変わらない）。

### R-3（懸念・要早期検証）: session_security の Cookie 設計に `Secure` 属性があるが、E2E は `http://127.0.0.1:3100`（非 TLS）で動く

session_security 根拠 4/5 は session Cookie・`oauth_state` Cookie ともに `Secure` 属性付きを明記している。一方 `playwright.config.ts` の既存 `webServer`（私の round1 claim §3 で流用を提案したもの）は `baseURL = http://127.0.0.1:3100` で **TLS を張っていない**。

Chromium はループバック（`127.0.0.1`/`localhost`）を「潜在的に信頼できるオリジン」として扱い `Secure` Cookie の送受信を許可する実装になっているため、恐らく動作はするはずだが、**この場のレンズ（私）が実機未検証のまま断定するのは L-113（捏造）に抵触するリスクがある**。TDD の Red 順序（round1 §5）に **「Step 0: ダミー OAuth 経由でログインし `document.cookie`（httpOnly なので JS からは見えない前提で、代わりに Playwright の `context.cookies()` で）セッション Cookie が実際に set されることを確認する smoke assert」を追加**することを提案する。ここで落ちれば、4 操作レビューのうち 2〜3 が原理的に自動化不能になるため、実装の最初期（内側ユニットより前）に潰すべきリスクとして `critical` 候補に入れることを lead に提案する。

### `verify_test` — 譲歩
<sub>2026-08-20T07:21:29+09:00</sub>

## concession（同意点）

1. **env 変数名は完全一致**: `GITHUB_OAUTH_CLIENT_ID` / `GITHUB_OAUTH_CLIENT_SECRET` / `GITHUB_OAUTH_CALLBACK_URL`（auth_flow 根拠づけ・NFR-22）は自分が round1 で挙げた名前とそのまま一致した。採用に異論なし。
2. **state のラウンドトリップ設計は自分の stub 設計と完全に整合する**: session_security は state を「app 自身が発行し、authorize URL のクエリと自ドメインの二次 Cookie 両方に載せ、callback で突合」する設計で、**GitHub（＝私の stub）は state の値をただの opaque な文字列として素通しするだけ**。私の stub 仕様（`/login/oauth/authorize` はクエリの `state` をそのまま `redirect_uri` へ付け替えるだけ）はこの設計とそのまま噛み合っており、stub 側に state 検証ロジックを一切持たせる必要がない（自分の round1 設計を変更なしで採用できる）。
3. **`AuthPort`（C-2）は testing-strategy.md §4 のテストダブル方針とそのまま整合する**: `exchangeAuthorizationCode(code): Promise<{ accessToken: string }>` という素朴な interface は「① フェイクのポート実装（手書き）」でユースケース層をユニットテストでき、私が round1 §5 で挙げた「内側ユニット: OAuth コールバックのユースケース」の Red はこのフェイクで書ける（stub サーバーへ到達する必要がない）。一方 `src/infrastructure/github/oauth.ts`（`AuthPort` の実装）自体は「② MSW（HTTP 境界）← ACL のテストに限る」の対象にすべきという点を round1 で書き漏らしていたので補足する。**stub（`e2e/stub/server.mjs`）と MSW は別レイヤーの道具**（前者は Playwright E2E 専用、後者は Vitest ユニット/結合の ACL テスト専用）であり、混同しないよう `tasks` に両方を明記してほしい。
4. **auth_flow の GitHub OAuth App 登録（`actor: user`）は自分のレンズと無関係で衝突しない**: E2E は実 GitHub に一切到達せず全て stub 上で完結するため、local/production 用の実 App 登録タスクが未完了でも SP-8 の E2E は独立に書き進められる。

## ラウンド 3

### `lead` — 合意
<sub>2026-08-20T07:23:41+09:00</sub>

## consensus（lead・SP-8 争点A〜D）

4 名の round1/round2 を突き合わせ、以下で収束した。矛盾は round2 のうちに全て解消済み（未解決の open_questions なし）。

### 争点A: 自前実装を採用（Auth.js 等ライブラリ導入は rejected）
no-scope・DB なし（D-5）という要件規模に対しライブラリの主要機能（複数プロバイダ抽象化・DBアダプタ・RBAC等）が丸ごと不要、プレビュー無効化方針（環境変数未設定で静かに機能が消える）との相性、自前 i18n の前例、ARCH-5（GitHub認証情報を `src/infrastructure/github/` に完全に閉じ込める）との親和性の4点で自前実装に軍配。GitHub OAuth App の新規登録が local/production の2つ必要（`actor: user`）。

### 争点B: JWE 暗号化 Cookie + 非暗号化 state Cookie
- セッション: `jose` の `EncryptJWT`（`alg: dir`, `enc: A256GCM`）で GitHub アクセストークンを暗号化した httpOnly Cookie に格納。TTL 7〜14日を `exp` に設定。
- CSRF state: 暗号化・署名は不要（YAGNI・round2 で session_security が明確化）。`crypto.randomUUID()` 等の生ランダム値を `oauth_state` という名前の短命（10分）・httpOnly・Secure・`SameSite=Lax` Cookie に保存し、callback でクエリ値とタイミングセーフ比較。使い捨てで即削除。
- ログアウト: session Cookie を `Max-Age=0` で上書き。`oauth_state` も防御的に削除。
- **未検証リスク（T-1として先行実施）**: `Secure` 属性 Cookie が `http://127.0.0.1` の E2E で送受信されるか（Chromium はループバックを信頼できるオリジンとして扱う想定だが実機未検証）。実装着手前に Playwright smoke test で確認する。
- **テスト補強**: `SameSite=Lax` はローカル E2E（同一ホスト127.0.0.1のためsame-site判定になりcross-site回帰を検出できない）を機械テストの限界として認識し、`Set-Cookie` ヘッダ文字列に `SameSite=Lax` が含まれることを単体/結合テストで直接 assert する。

### 争点C: 層配置
- route handler: `app/api/auth/{login,callback,logout}/route.ts`（provider名なしに一本化。`RepositoryQueryPort` と同じ事業者中立命名規律をパスにも延長）。
- `src/domain/ports/auth-port.ts`: `AuthPort.exchangeAuthorizationCode(code): Promise<{ accessToken: string }>` のみ（`/user` プロフィール取得は round2 で SP-8 スコープ外に確定・YAGNI。ログイン中ユーザー名表示が要る場合のみ将来 `AuthPort.fetchViewer` を追加）。
- 実装: `src/infrastructure/github/oauth.ts`（authorize URL 組み立て・token交換・AuthPort実装）。
- `src/infrastructure/platform/session-cookie.ts`: **本セッション Cookie（JWE）専用**に責務を絞る。`encodeSessionCookie`/`decodeSessionCookie` のみ。
- `state` Cookie: composition root を経由せず、route handler が `next/server` の Cookie API で直接生成・照合する（秘匿値を扱わないため ARCH-3 対象外）。
- `src/composition/auth.ts`: 上記を束ね、ログイン導線の表示可否を「`GITHUB_OAUTH_CLIENT_ID`/`_CLIENT_SECRET`/`_CALLBACK_URL`/`SESSION_ENCRYPTION_KEY` の4変数が揃っているか」で一元判定する。
- レート枠切替: `RateLimitPort`（Issue #122・自リクエストの間引き）とは無関係な別配線。`container.ts` の `TokenProvider` を `makeInstallationTokenProvider` からユーザーアクセストークン版へ composition root で差し替えるだけ（新規ドメインポート不要）。`searchRepositoriesUseCase(accessToken?)` 等に拡張。
- 言語切替UI（US-2）: 新規ポート・usecase不要。`src/ui/url/build-locale-url.ts`（純粋関数）+ `src/ui/locale-switcher.tsx`（表示コンポーネント）+ `messages/{ja,en}.json` 追記。`app/[locale]/layout.tsx` から呼ぶ。
- ログイン状態UI: AC に「ユーザー名・レート枠数値の表示」要求なし。`/user` 取得を落とした帰結として、最小実装は「セッション Cookie の有無（真偽値）」に基づくログイン/ログアウトリンクの出し分けのみとする（D-6: 機能差を作らない・上乗せ最小主義に整合。最も単純な合理的解釈として自律確定・仮定記録）。

### 争点D: 検証可能性
- `e2e/stub/server.mjs` に `GET /login/oauth/authorize`（302即時リダイレクト）・`POST /login/oauth/access_token`（固定トークン返却）・`GET /user`（未使用だが将来のfetchViewer拡張に備え実装だけ残す。**AuthPort からは呼ばれない**）を追加。POST分岐は405判定より前に置く（実装漏れ注意）。
- 新規env: `GITHUB_OAUTH_ORIGIN`（`GITHUB_API_ORIGIN` と同じループバック限定検証を共有）・`GITHUB_OAUTH_CLIENT_ID`/`_CLIENT_SECRET`/`_CALLBACK_URL`（値は stub 検証なしのため固定文字列可）・`SESSION_ENCRYPTION_KEY`（E2E専用ダミー鍵）。
- `playwright.config.ts` の既存 `webServer`（ローカルビルド構成）に上記envを追加するだけで infra-design.md §8.1 の「ダミーOAuth設定を注入したローカルビルド」要件を満たす。新規起動スクリプト不要。
- `/__stats` の計測軸は「Authorizationヘッダの有無」ではなく「**値がユーザートークン固定文字列と一致するリクエスト数**」（`userAuthSearchCount`等）に訂正（round2 verify_test 自己修正済み。未ログイン時も installation token が既に付与されているため）。
- 新規 `e2e/sp-8.spec.ts`: SP-8 の4操作レビュー手順をそのまま `test.step()` に写す。Step 0 として T-1（Secureセッション Cookie が実際にsetされるか `context.cookies()` で smoke確認）を先頭に追加。
- TDD順序: 外側E2E Red（4手順）→ stub拡張（テストインフラとして先に用意・無テスト対象）→ 内側ユニット Red/Green/Refactor（state生成/検証 → セッション暗号化/復号 → OAuthコールバックusecase(フェイクAuthPortで) → ACLエラー変換 → oauth.ts実装をMSWでテスト）→ 外側E2E Green。

### `lead` — 判定
<sub>2026-08-20T07:23:41+09:00</sub>

{
  "decisions": [
    {"issue": "A: OAuthフロー実装方式", "design": "自前実装（GitHub OAuth App登録要・local/production別App）。Auth.js等ライブラリは導入しない", "artifacts": ["src/infrastructure/github/oauth.ts(新規)"], "rejected": "Auth.js(NextAuth v5)導入: no-scope/DBなし要件に対し機能過多、プレビュー無効化方針との相性検証コスト、Cloudflare Workers上での動作実績なし、ARCH-5準拠のため結局ラッパーが要り導入コスト相殺"},
    {"issue": "B: セッション/CSRF実装方式", "design": "セッションはjose EncryptJWT(A256GCM,dir)でGitHubアクセストークンを暗号化しhttpOnly Cookie格納(TTL7-14日)。CSRF stateは非暗号化の生ランダム値をoauth_state短命Cookie(10分,SameSite=Lax)に保存しcallbackでタイミングセーフ比較・即削除", "artifacts": ["src/infrastructure/platform/session-cookie.ts(新規・本セッション専用)", "app/api/auth/login/route.ts(新規・state Cookie直書き)", "app/api/auth/callback/route.ts(新規)"], "rejected": "署名のみJWS: NFR-9(秘匿情報クライアント非露出)に不適合。サーバー側opaqueセッションID+一時保持: D-5(DBなし)とWorkersのisolate非永続性で機能的に破綻。state Cookieの暗号化/署名: YAGNI(サーバーが書きサーバーが読むだけの値で秘匿情報を含まない)"},
    {"issue": "C: 層配置", "design": "route handlerは app/api/auth/{login,callback,logout}/route.ts (provider名なし)。AuthPort.exchangeAuthorizationCode(code)=>{accessToken}のみをドメインポートとして新設、実装はsrc/infrastructure/github/oauth.ts。stateCookieはroute handlerがnext/serverのCookie APIで直接生成/照合(composition root非経由)。レート枠切替はcontainer.tsのTokenProviderをinstallation token版からユーザーアクセストークン版へ差し替えるだけ(RateLimitPort#122とは別配線)。言語切替UIはsrc/ui/url/build-locale-url.ts(純粋関数)+src/ui/locale-switcher.tsx(新規ポート不要)", "artifacts": ["src/domain/ports/auth-port.ts(新規)", "src/usecases/complete-login.ts(新規)", "src/composition/auth.ts(新規・4変数ゲート)", "src/composition/container.ts(改修)", "src/ui/locale-switcher.tsx(新規)", "src/ui/url/build-locale-url.ts(新規)", "messages/ja.json, messages/en.json(改修)", "docs/03_design/architecture/application-architecture.md §2(改修・AuthPort追記)"], "rejected": "GET /user プロフィール取得をAuthPortに含める(round1 auth_flow案): AC未記載でYAGNI、round2で全員合意しスコープ外に確定。RateLimitPort(#122)配線とレート枠切替を同一関数に混在させる案: 目的の異なる機構(乱用防止 vs ユーザー識別)を混ぜると本来の乱用防止機能が壊れるため却下"},
    {"issue": "D: 検証可能性", "design": "e2e/stub/server.mjsにOAuth authorize(302即時)/token交換/userのモックを追加(POST分岐は405判定より前)。GITHUB_OAUTH_ORIGIN等5envをplaywright.config.tsのwebServerに追加するだけでinfra-design.md§8.1のローカルビルドE2E要件を満たす。/__statsはAuthorizationヘッダの値一致(userAuthSearchCount等)で計測。新規e2e/sp-8.spec.tsに4操作レビュー+Secureセッション Cookie smoke assertをStep0として追加", "artifacts": ["e2e/stub/server.mjs(改修)", "e2e/sp-8.spec.ts(新規)", "playwright.config.ts(改修)"], "rejected": "verify_test round1の/__stats設計(Authorizationヘッダ「有無」で計測): 未ログイン時も既にinstallation tokenのAuthorizationヘッダが付与されているため誤り、round2で値一致方式に自己修正済み"}
  ],
  "tasks": [
    {"id": "T-1", "title": "Secure属性Cookieがhttp://127.0.0.1のE2Eで実際にset/送出されるかPlaywright smoke testで先行確認する(争点Bの未検証リスク)", "actor": "claude", "depends_on": [], "sp": "sp:1"},
    {"id": "T-2", "title": "GitHub OAuth App(local用+production用)を登録し client_id/secret/callback URLを取得する", "actor": "user", "depends_on": [], "sp": "sp:1"},
    {"id": "T-3", "title": "e2e/sp-8.spec.tsの外側E2E Redを4操作レビュー手順+Step0(Secure Cookie smoke)で書く", "actor": "claude", "depends_on": ["T-1"], "sp": "sp:2"},
    {"id": "T-4", "title": "e2e/stub/server.mjsにOAuth authorize/token/userモックを追加しplaywright.config.tsにenvを足す", "actor": "claude", "depends_on": [], "sp": "sp:2"},
    {"id": "T-5", "title": "AuthPort・oauth.ts・session-cookie.ts・complete-login usecaseを内側ユニットTDDで実装する", "actor": "claude", "depends_on": ["T-3", "T-4"], "sp": "sp:3"},
    {"id": "T-6", "title": "app/api/auth/{login,callback,logout}/route.tsとsrc/composition/auth.tsを実装し4変数ゲートを配線する", "actor": "claude", "depends_on": ["T-5"], "sp": "sp:2"},
    {"id": "T-7", "title": "container.tsのTokenProvider差し替え(レート枠切替)を実装する", "actor": "claude", "depends_on": ["T-6"], "sp": "sp:2"},
    {"id": "T-8", "title": "言語切替UI(locale-switcher.tsx・build-locale-url.ts・messages追記)を実装する", "actor": "claude", "depends_on": [], "sp": "sp:2"},
    {"id": "T-9", "title": "全E2E(SP-1〜8)を緑にし、application-architecture.md §2にAuthPortを追記、env-vars相当のドキュメントを更新する", "actor": "claude", "depends_on": ["T-6", "T-7", "T-8"], "sp": "sp:1"}
  ],
  "critical": [],
  "open_questions": []
}
