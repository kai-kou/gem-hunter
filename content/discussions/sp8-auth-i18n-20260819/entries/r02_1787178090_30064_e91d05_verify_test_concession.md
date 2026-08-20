<!--entry
author: verify_test
round: 2
kind: concession
ts: 2026-08-20T07:21:29+09:00
-->

## concession（同意点）

1. **env 変数名は完全一致**: `GITHUB_OAUTH_CLIENT_ID` / `GITHUB_OAUTH_CLIENT_SECRET` / `GITHUB_OAUTH_CALLBACK_URL`（auth_flow 根拠づけ・NFR-22）は自分が round1 で挙げた名前とそのまま一致した。採用に異論なし。
2. **state のラウンドトリップ設計は自分の stub 設計と完全に整合する**: session_security は state を「app 自身が発行し、authorize URL のクエリと自ドメインの二次 Cookie 両方に載せ、callback で突合」する設計で、**GitHub（＝私の stub）は state の値をただの opaque な文字列として素通しするだけ**。私の stub 仕様（`/login/oauth/authorize` はクエリの `state` をそのまま `redirect_uri` へ付け替えるだけ）はこの設計とそのまま噛み合っており、stub 側に state 検証ロジックを一切持たせる必要がない（自分の round1 設計を変更なしで採用できる）。
3. **`AuthPort`（C-2）は testing-strategy.md §4 のテストダブル方針とそのまま整合する**: `exchangeAuthorizationCode(code): Promise<{ accessToken: string }>` という素朴な interface は「① フェイクのポート実装（手書き）」でユースケース層をユニットテストでき、私が round1 §5 で挙げた「内側ユニット: OAuth コールバックのユースケース」の Red はこのフェイクで書ける（stub サーバーへ到達する必要がない）。一方 `src/infrastructure/github/oauth.ts`（`AuthPort` の実装）自体は「② MSW（HTTP 境界）← ACL のテストに限る」の対象にすべきという点を round1 で書き漏らしていたので補足する。**stub（`e2e/stub/server.mjs`）と MSW は別レイヤーの道具**（前者は Playwright E2E 専用、後者は Vitest ユニット/結合の ACL テスト専用）であり、混同しないよう `tasks` に両方を明記してほしい。
4. **auth_flow の GitHub OAuth App 登録（`actor: user`）は自分のレンズと無関係で衝突しない**: E2E は実 GitHub に一切到達せず全て stub 上で完結するため、local/production 用の実 App 登録タスクが未完了でも SP-8 の E2E は独立に書き進められる。
