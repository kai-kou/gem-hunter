<!--entry
author: secrets_hunter
round: 1
kind: claim
ts: 2026-08-24T12:22:00+09:00
-->

# secrets_hunter — Round 1 所見

## 結論（severity: なし。実値の秘密情報漏洩は検出ゼロ）

事前に `docs/05_release/repository-publication-review.md`（2026-08-20 実施の公開前レビュー）が存在し、Issue/PR/全ブランチ含む網羅スキャンで「秘密情報の検出ゼロ」と結論済み。本ラウンドはその**再現性確認**（独立した正規表現走査）と**2026-08-20〜08-24 の差分 50 コミット分の再走査**を実施した。結果、新規混入なし。

## 実施した調査と結果

1. **`git log --all -p` 全履歴**を `ghp_/gho_/ghu_/ghs_/ghr_/xox[baprs]-/sk-ant-/sk-/AKIA/AIza/ya29\./BEGIN * PRIVATE KEY` で走査
   → ヒットはすべてダミー値・docstring 例示・鍵形式名への言及のみ（例: `tools/mask_secrets.py:54` の docstring、`docs/rules/slack-notification-rules.md:199-202` のプレースホルダ `xoxb-xxxxx-xxxxx-xxxxx` / `C0XXXXXXXXX`）。実値なし。

2. **`.env` 系ファイル**: `git ls-files` に実 `.env`/`.env.local` 等は 0 件。`.gitignore` が `.env` `.env.*` `*.pem` `*.key` を網羅し、`!.env.example`（値なしテンプレート）のみ例外化。

3. **`public/data/`（4.2MB・生成データ）**: gem-index 系 JSON を全件 grep したが token/key パターン検出ゼロ（パッケージレジストリの公開メタデータのみ）。

4. **`.claude/settings.json`**: `permissions.allow` / `sandbox.network.allowedDomains` / hooks 設定を確認。実 API キー・実アカウント ID の記載なし。`excludedCommands` で secrets broker 系スクリプトをサンドボックス除外しているが、これは値を出力しない設計（`tools/setup_secrets_broker.sh` 等はブローカー経由取得のラッパーで、値自体はコミットされていない）。

5. **メールアドレス走査**: 検出は `git@github.com`（コミットメッセージ例示・リモート URL 例）と `i@izs.me`（npm 依存 `package-lock.json` のライセンス表記由来、`isaacs` 氏の公開情報）のみ。ユーザー個人メール（`koka.orz@...`）は履歴・追跡ファイルとも 0 件。

6. **GitHub App / Cloudflare 識別子**: `GITHUB_APP_CLIENT_ID` / `GITHUB_APP_INSTALLATION_ID` の実値が入った箇所なし（`.env.example` は空欄、テストは `vi.stubEnv` でダミー文字列 `'client-id'` 等）。Cloudflare account_id/zone_id（32 桁 hex）走査もヒットゼロ。`installation-token.test.ts` は `jose` で都度生成した使い捨て鍵ペアを使用（実鍵ではない）。

7. **`kinamocchi-tech.workers.dev`**（本番 URL）は README・SECURITY.md・`content/discussions/` に多数露出しているが、これは**意図的に公開しているプロダクト URL そのもの**（README 冒頭で「使ってみる」として案内済み）であり秘密情報ではない。既存レビューの `M-1'` で「新たな露出ではない」と結論済みの内容と整合。

8. **Slack チャンネル ID っぽい文字列（`C0[A-Z0-9]{8,10}`）**: ヒットは `og-background-data.ts` の SVG/画像生成用ランダム文字列、`e2e/fixtures/repos.json` のダミー avatar URL 断片、`package-lock.json` の npm パッケージ integrity 由来の base64 断片で、いずれも実 Slack チャンネル ID ではない誤検知。ドキュメント中の `C0XXXXXXXXX` はプレースホルダ。

9. **2026-08-20〜08-24 の差分**（コミット 50 件・`content/discussions/` の新規議論ログ多数含む）を同一パターンで再走査 → 新規混入なし。

## 明示的に「問題なし」と判定した領域
- git 全履歴（46 ブランチ相当は現行 origin では 1 本のみ確認できたため今回は `--all` の到達範囲で確認。ブランチ削除状況は他レンズの担当範囲外のため言及のみ）
- `public/data/`
- `.claude/settings.json` の allow/deny リスト・sandbox 設定
- `.env.example` とその周辺ツール（`mask_secrets.py` 等）の設計
- 直近 4 日間の差分

## 参考: 既存の一次資料
`docs/05_release/repository-publication-review.md`（2026-08-20 公開前レビュー、飼い主決定済み）が本レンズの大半を先行して網羅している。本ラウンドはその結論を独立に再現確認した位置づけ。
