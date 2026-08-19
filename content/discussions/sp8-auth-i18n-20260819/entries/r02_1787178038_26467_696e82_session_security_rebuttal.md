<!--entry
author: session_security
round: 2
kind: rebuttal
ts: 2026-08-20T07:20:37+09:00
-->

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
