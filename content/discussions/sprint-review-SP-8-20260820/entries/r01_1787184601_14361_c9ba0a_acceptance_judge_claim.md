<!--entry
author: acceptance_judge
round: 1
kind: claim
ts: 2026-08-20T09:10:01+09:00
-->

## acceptance_judge claim（Sprint Review Step7 必須4点）

### (1) 設計ドキュメント追跡（1ホップ先）

`user-story-map.md` §5.3 SP-8 節（L408-421）→ §8「未解決のまま残していること」（L554: `infrastructure-design.md` §8.1）、`prd.md` AR-4/AR-5（L231-232, 237-251）を実読した。

- **AR-4（i18n）**: URL は `/ja` `/en` プレフィックス、GitHub 由来データ（description・topics・言語名）は原文のまま。→ 実装は `app/[locale]/layout.tsx` で `notFound()` によるロケール検証、`LocaleSwitcher` は endonym（「日本語」/「English」）表示。GitHub データの翻訳は行っていない（差分に該当コードなし）。整合。
- **AR-5（OAuth）**: no-scope・暗号化 httpOnly Cookie・state 必須・logout 提供・callback URL 環境変数化・未ログインでも機能差なし。→ `oauth.ts` で `scope` パラメータ未付与、`session-cookie.ts` で JWE(`A256GCM`) 暗号化 httpOnly Cookie、`login/route.ts` で `crypto.randomUUID()` の state を Cookie 保存、`callback/route.ts` で `timingSafeEqualString` による state 検証、`logout/route.ts` あり、`GITHUB_OAUTH_CALLBACK_URL` 環境変数使用。`layout.tsx` は `isAuthConfigured()` が false（env 未設定）ならログイン導線自体を出さず、既存の検索・詳細機能は無条件で動く（機能差なし）。整合。
- **infrastructure-design.md §8.1**: 「プレビューでは (a) OAuth 無効化」「SP-8 の E2E はプレビューではなくダミー OAuth 注入のローカルビルドに対して実行する」と明記。→ brief のプレビュー疎通確認（手順1・4のみ、2・3はローカル e2e で機械検証）はこの設計方針どおりで、逸脱ではなく設計文書が要求する運用そのもの。整合。
- `application-architecture.md` に `AuthPort`（`exchangeAuthorizationCode`）が追記されており、設計ドキュメントの更新漏れなし。

**結論**: 実装と設計ドキュメントの記載に不整合は検出されなかった。

### (2) 実行結果（自分で実行・断定根拠）

origin/main の squash コミット 5b7601a（PR #141 マージ後）を `git worktree add` で分離チェックアウトし、`npm ci` 後に自分で実行:

```
bash tools/run_checks.sh
→ Lint PASS / 型チェック PASS / テスト(vitest) PASS / E2E(playwright) PASS /
  依存規則 PASS / UI寸法検査 PASS / 配色コントラスト PASS / CJK Markdown PASS /
  セルフレビュー機械チェック PASS （全9項目 PASS）

npx vitest run → Test Files 40 passed(40) / Tests 261 passed(261)
python3 tools/check_architecture_boundaries.py → ✅ 依存規則 OK（99ファイル・Warning 0件）
python3 tools/check_ui_dimensions.py → ✅ UI寸法検査 OK（Warning 0件）
```

brief の「Lint/型/テスト261件/E2E/依存規則/UI寸法/配色コントラスト/CJK Markdown/セルフレビュー機械チェックすべてPASS」は実行結果と一致した（自分の実行結果のみを根拠にしている。マージ前セッションの申告を追認しただけではない）。

### (3) Issue #140 編成欄

`mcp__github__issue_read`（get_comments）で確認。Sprint Planning コメント（2026-08-19T22:10:40Z）:

> **編成**: discussion-review（設計方針の相互検証・1 ラウンド）→ fan-out（3 役割以上・ファイル非重複分割）

`session-sprint-rules.md` §2 の sp:8 既定（「着手前に議論型 discussion-review を1ラウンド → その後 fan-out 実装」）と一致。フォローアップコメント（22:24:48Z）でも discussion-review 4名2ラウンド実施済み・fan-out（auth_backend/locale_ui並列+統合）に進んだ旨が記録されている。単独実行の痕跡なし。整合。

### (4) UI/デザイン変更と ui-ux-guidelines.md §2.4

差分の UI 変更ファイル: `app/[locale]/layout.tsx`（LoginLink 統合）・`app/[locale]/page.tsx`・`app/[locale]/repos/[owner]/[repo]/page.tsx`（LocaleSwitcher 統合）・新規 `src/ui/login-link.tsx`・`src/ui/locale-switcher.tsx`。

§2.4 を実際に開いて確認した結果:

- 🔴 必須「高さ・フォントサイズは cva の `size` variant 経由でのみ指定し、生の `h-*`/`text-*` を書かない」→ `LoginLink` は `buttonVariants({ variant: 'ghost', size: 'sm' })`、`LocaleSwitcher` は `buttonVariants({ variant: isCurrent ? 'secondary' : 'ghost', size: 'default' })` を使用しており、生の `h-*`/`text-*` の直書きはコード上に見当たらない。`check_ui_dimensions.py`（機械検査）も実行して Warning 0 件で PASS（cva size variant 経由という必須要件をコードと機械検査の両面で確認）。
- 🔵 推奨「二次的なコントロールは `--size-control-md`(32px) 以上」→ `LocaleSwitcher`（size `default`=32px）は満たすが、`LoginLink`（size `sm`=28px）はこの推奨値をやや下回る（ただし 🔴 必須フロアの `--size-control-xs`(24px) は上回っており、必須違反ではない）。これは 🔵 推奨からの軽微な逸脱であり、ブロッカーではないが認識共有のため記録する。
- 固定幅・`white-space: nowrap` の使用は `layout.tsx`/`login-link.tsx`/`locale-switcher.tsx` に見当たらず、§3「レイアウトと i18n 耐性」の禁止事項にも抵触していない（`flex flex-wrap`・`justify-end` 等の可変幅実装）。

**重要な限定**: 上記はコードと機械検査（`check_ui_dimensions.py`・`check_contrast.py` PASS）のみに基づく判定であり、プレビュー画面を実際に開いての **目視確認は行っていない**（プレビューは開けない制約のため）。§2.4 が要求する「意味論的に正しい tier を選んでいるか」の視覚的な最終判断（実機での見た目・タップ感触等）は、人間の操作レビュー（`user-story-map.md` §5.3 SP-8 操作レビュー手順）に委ねるべき事項として残す。

### 総合判定

**accepted_with_conditions**

理由: (1)(2)(3) は完全に整合・PASS。(4) はコード・機械検査ベースでは適合しているが、`LoginLink` の `sm`(28px) が §2.4 🔵 推奨(32px以上)をわずかに下回る点、および視覚的最終確認が未実施（プレビュー不可のため）である点の2つを条件として残す。いずれも 🔴 必須要件の違反ではなく、ブロッカーではない。

**条件**:
- 次回以降のプレビュー環境確立（OAuth App 登録後）時に、人間の操作レビューで `LoginLink`/`LocaleSwitcher` の実見た目・タップしやすさを目視確認する
- `LoginLink` の `size: 'sm'` は意図的な二次導線判断か、`size: 'default'`(md) が妥当かをレビューで再確認する（機械検査は通過するため強制ではない）
