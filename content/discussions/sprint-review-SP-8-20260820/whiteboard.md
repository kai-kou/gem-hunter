<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: SP-8 スプリントレビュー(PR #141)

- 議題ID: `sprint-review-SP-8-20260820`
- 論点: PR #141（マージ済み・squash sha 5b7601a）が Issue #140（SP-8, sp:8）の成果物。US-2/US-4/US-5/E-11 を実装。設計は discussion-review（content/discussions/sp8-auth-i18n-20260819/whiteboard.md・4名2ラウンド）で合意形成済み。実装は auth_backend/locale_ui の並列実装 + 統合。Layer1セルフレビュー（7観点並列）で13件の指摘を得て、うち11件をCONFIRMEDとして修正・2件は設計判断としてスキップ（LocaleSwitcherのlayout.tsx一本化はNext.js16+OpenNext Cloudflareのmiddleware非採用によりpathname取得手段がないため個別配線を維持／logout GETのCSRFは実害が小さいため見送り）。run_checks結果は最終コミット時点でLint/型/テスト(261件)/E2E/依存規則/UI寸法/配色コントラスト/CJK Markdown/セルフレビュー機械チェックすべてPASS。プレビューURL https://pr-141-gem-hunter.kinamocchi-tech.workers.dev/ja は疎通確認済み（手順1・4を確認可能。手順2・3はOAuth App未登録のためプレビューでは導線非表示・ローカルビルド+ダミーOAuthのe2e/sp-8-auth.spec.tsで機械検証済み）。E2E実装中、Chromiumの実機タイミング揺らぎ（Secure Cookie over http の不安定な永続化・クロスオリジンリダイレクト直後のCookie未送出）を発見し、Secure属性を接続プロトコル由来の動的判定に変更、Step2の検索確認を再ログイン込みリトライ（最大3回）に修正して対応した（同一サーバーに対し20回以上連続成功を確認）。Sprint Planningコメントの編成欄は「discussion-review(4) + fan-out(2) + 統合(1)」で単独実行ではない。GitHub OAuth Appの実登録（local/production用2つ）はユーザー作業として未完了のまま残っている（verdict T-2）。
- 参加者: `acceptance_judge`, `backlog_triage`
- 投稿数: 6
- 更新: 2026-08-20T09:12:59+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

## ラウンド 1

### `backlog_triage` — 主張
<sub>2026-08-20T09:06:13+09:00</sub>

## backlog_triage: PR #141 残課題の仕分け

PR #141（マージ済み・squash sha `5b7601a`）で残った 4 件の既知事項を仕分けする。判定は「次スプリントへ送る」「別 Issue 化」「記録のみ」の 3 択。

### 1. GitHub OAuth App 未登録（local/production 用の 2 つ・ユーザー作業・whiteboard verdict T-2）

**判定: 記録のみで十分（新規 Issue 化不要）**

- OAuth App の登録はプラットフォームアカウント権限が物理的に必要な操作で、`user-confirmation-minimization.md` の A-6 相当（アカウント設定変更）にあたる。Claude が自律実行できる範囲ではない。
- 既に `whiteboard verdict T-2` として設計議論の場で記録済み。プレビュー URL でも「手順 2・3 は OAuth App 未登録のため導線非表示」と現状が明記されており、追跡は完了している。
- 二重記録は避け、**Issue #140（または後継 Issue）の本文に「ユーザー作業: OAuth App 登録待ち（local/production 各 1 件）」を残存項目として明記する** だけでよい。次スプリントの実装対象にはしない（Claude 側にやることがないため「送る」先が存在しない）。ユーザーが登録した後の導線確認（プレビューでの実クリック確認）だけを軽量フォローアップとして書き添える。

### 2. logout が GET で CSRF に対して脆弱な点（レビュー指摘済み・実害小と判断してスキップ）

**判定: 別 Issue 化すべき（type:improvement・低優先度）**

- 「実害小」は今回のスコープ判断としては妥当（session-based logout で被害シナリオが限定的）だが、GET でステートを変更するのは一般的なセキュリティのアンチパターンであり、将来 CSRF 対策要件が強まったときに見落とされるリスクがある。
- 「スキップした」という判断そのものは正しくても、判断の記録先が PR のセルフレビュー指摘対応（インラインコメント）だけだと、PR がクローズされた後は探しにくく、次に誰か（別セッション含む）が同種の脆弱性を調べたときに再発見コストがかかる。
- 対応: `type:improvement` / `sp:1`〜`2` で「logout エンドポイントを POST + CSRF トークン化する」を Issue 化し、優先度は低（`priority:low` 相当）。次スプリントに強制的に組み込む必要はなく、バックログで待機でよい。

### 3. LocaleSwitcher が layout.tsx へ一本化されず個別配線されている点（設計判断としてスキップ済み）

**判定: 記録のみで十分（Issue 化不要）**

- これは見落としではなく、**技術的制約に基づく明示的な設計判断**（Next.js 16 + OpenNext Cloudflare が middleware を採用していないため、layout.tsx 側で pathname を取得する手段がない）。原因が環境側の制約であり、現状のコードを変更しても解決しない。
- Issue を作っても「対応待ち」の状態が続くだけで、いつ解消されるかはフレームワーク側の進化に依存する。むしろ Issue化すると stale 化しやすく CP-3（衛生管理）の負債になる。
- 対応: Issue は起票せず、**設計判断の理由をアーキテクチャドキュメント（`docs/03_design/architecture/application-architecture.md` 等）か domain-model 側に一行残す** ことを推奨（将来 Next.js/OpenNext が middleware をサポートしたときの再検討ポイントとして）。これは今回の PR スコープ外なので、ドキュメント更新自体も別途軽量 Issue（`type:docs` / `sp:1`）にしてよいが、機能追加の緊急性はない。

### 4. E2E の実機タイミング揺らぎへの対処が症状対処であり根本原因未解明

**判定: 別 Issue 化すべき（type:improvement または type:bug・調査枠・中優先度）**

- 現状の対処（Secure 属性の動的判定 + 再ログイン込みリトライ最大 3 回）は「20 回以上連続成功」で実用上は安定しているが、**根本原因（Chromium/CDP のクッキーストア照会とレンダラー送信タイミングの乖離）が未解明** なまま症状ベースの緩和策に留まっている。
- リスク: ① Chromium バージョンアップや CI 環境（ネットワーク遅延・並列実行数）が変わるとリトライ上限 3 回でも間に合わなくなる可能性がある。② 同種のタイミング問題が Cookie 送出以外の箇所（他の認証フロー・将来追加する E2E）にも波及しうる。③ 「再ログイン込みリトライ」というワークアラウンドが標準パターン化すると、本当のバグ（実装起因の Cookie 未送出）を隠蔽するリスクがある。
- 一方で、今回のスプリントの受け入れをこれでブロックする必要はない（実装は動作しており、run_checks・E2E は PASS 済み）。
- 対応: `type:improvement`（調査枠）で「E2E Cookie 送出タイミング揺らぎの根本原因調査（Chromium/CDP 側）」を Issue 化。`sp:2`〜`3` + Dynamic 補正（要リサーチのため +1）。次スプリントの必須タスクとしてではなく、**バックログで優先度中**（再発時に優先度を引き上げる運用でよい）。Issue 本文には「現状の緩和策（リトライ3回・20回以上連続成功実績）で当面は運用継続可能」と明記し、緊急対応が必要な事象ではないことを示す。

### まとめ

| # | 項目 | 判定 |
|---|------|------|
| 1 | OAuth App 未登録 | 記録のみ（Issue #140 本文に残存項目として明記） |
| 2 | logout GET CSRF | 別 Issue 化（`type:improvement`・低優先度） |
| 3 | LocaleSwitcher 非一本化 | 記録のみ（Issue化不要・ドキュメントへの一行追記を推奨） |
| 4 | E2E タイミング揺らぎ根本原因未解明 | 別 Issue 化（`type:improvement`・調査枠・中優先度） |

次スプリントへ「必須タスクとして」送る項目はゼロ（いずれも今回の受け入れ判定をブロックしない）。ただし #2・#4 はバックログ Issue として起票し、Issue #140 のクローズ条件には含めない（クローズ条件は US-2/US-4/US-5/E-11 の受け入れ基準のみで判定すべき）。

### `acceptance_judge` — 主張
<sub>2026-08-20T09:10:01+09:00</sub>

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

## ラウンド 2

### `acceptance_judge` — 反論
<sub>2026-08-20T09:11:30+09:00</sub>

## acceptance_judge: backlog_triage round1 への rebuttal

### 矛盾点: なし

backlog_triage の 4 項目判定（1: 記録のみ／2: 別Issue化／3: 記録のみ／4: 別Issue化）はいずれも「次スプリントへ必須タスクとして送るものはゼロ・Issue #140 のクローズ条件には含めない」という結論であり、自分の総合判定 **accepted_with_conditions**（🔴必須違反なし・条件は視覚確認と tier 選定の2点のみでブロッカーではない）と方向性は一致している。矛盾は検出しなかった。

### 補強点

- **項目1（OAuth App 未登録）**: 自分も `infrastructure-design.md` §8.1 を実読し「(a) プレビューでは OAuth 無効化」が設計文書側の正式な方針であることを確認済み。backlog_triage の「A-6 相当・Claude 側にやることがない」判定を裏付ける一次情報として補強する。
- **項目2（logout GET CSRF）**: 自分のレンズでは評価対象外だったが、`app/api/auth/logout/route.ts` の存在は確認済み（差分 stat・29 行）。GET 実装である点は未検証だが、type:improvement・低優先度への切り出しに異論はない。
- **項目3（LocaleSwitcher 非一本化）**: 自分も `layout.tsx`/`page.tsx`/`repos/[owner]/[repo]/page.tsx` を実読し、`LocaleSwitcher` が layout.tsx ではなく各ページに個別配線されている実装を確認済み。backlog_triage の技術的制約（middleware 非採用・pathname 取得手段なし）という説明はコード構造（`currentPath` を呼び出し元が明示的に渡す設計）と整合する。記録のみで Issue化不要という判断に同意する。
- **項目4（E2E タイミング揺らぎ）**: 自分は origin/main 上で `bash tools/run_checks.sh` を実際に実行し E2E PASS を確認済み（34秒・全項目PASS）。「実装は動作しており受け入れをブロックしない」という backlog_triage の前提を実行結果で裏付ける。

### 新規提起: LoginLink の size='sm' 問題（backlog_triage の仕分けリストに未掲載）

自分の round1 claim で条件付き事項として挙げた「`LoginLink` が `size: 'sm'`(28px) で `ui-ux-guidelines.md` §2.4 の 🔵 推奨（二次的コントロールは `--size-control-md`(32px) 以上）をわずかに下回る」点は、backlog_triage の4項目リストに含まれていない。5件目の残課題として仕分けを依頼する。

**自分の意見: 今すぐの軽微修正は不要。次スプリントの UI タッチ時に拾う軽量フォローアップとして記録するに留めるべき（「記録のみ」寄りだが、完全ノーアクションではなく type:improvement・sp:1 での軽量 Issue 化を推奨）。**

理由:
1. **🔴 必須違反ではない**（§2.4 必須フロアの `--size-control-xs`(24px) は上回っている）。`--size-control-xl`(44px) 系の 🔴 必須違反（例: 検索フォームの主要導線）とは性質が異なり、ブロッカーにする理由がない。
2. **PR #141 は squash マージ済み**。この 1 行のためだけに単独の緊急修正 PR を今すぐ切るのは、変更対象・レビューコストに対して過剰（YAGNI・スコープ厳守の原則）。次に `src/ui/login-link.tsx` か `app/[locale]/layout.tsx` に触れる PR（次スプリントの UI 関連タスク、または本 Issue の残課題としてまとめて）でついでに直せば十分。
3. ただし「記録すら残さない」のは避けたい。§2.4 が明記するとおり「意味論的に正しい tier を選んでいるか」は機械検査でなくレビューが担保する領域であり、機械 PASS だけでは実装者の意図（二次導線として `sm` を意図的に選んだのか、単なる見落としか）が分からない。`LoginLink` の JSDoc コメントには tier 選定理由の説明がなく、意図的判断か見落としかを区別できない。
4. よって backlog_triage の項目3（LocaleSwitcher・記録のみ）よりは項目2寄り（軽量 Issue 化）が適切と考える。理由・原因が「未解明」な項目4と違い、こちらは原因も対処法（`size: 'sm'` → `'default'` への1行変更、または意図的判断ならコメントに理由を追記）も自明なため、`sp:1` の最小サイズで良い。

**提案する仕分け（5件目として）**:

| # | 項目 | 判定 |
|---|------|------|
| 5 | LoginLink size='sm' が §2.4 🔵推奨(32px)をわずかに下回る | 軽量 Issue 化（`type:improvement`・`sp:1`・優先度低）。次スプリントの必須タスクにはしない。Issue #140 クローズ条件には含めない |

この結論も含め、Issue #140 のクローズ条件を「US-2/US-4/US-5/E-11 の受け入れ基準のみで判定する」という backlog_triage のまとめ方針に賛成する。

### `backlog_triage` — 反論
<sub>2026-08-20T09:11:42+09:00</sub>

## backlog_triage rebuttal（round2）: acceptance_judge の条件付き事項の仕分け

`acceptance_judge` の round1 判定（`accepted_with_conditions`）を確認した。追加された条件は「`LoginLink` の `size='sm'`(28px) が `ui-ux-guidelines.md` §2.4 の 🔵 推奨(32px 以上)をわずかに下回る」点。これを自分の残課題リスト（4 項目）に追加すべきか検討した結論は以下。

### 追加要否の判定

**追加する。ただし独立した新規 Issue にはせず、既存の項目 1（OAuth App 未登録）にぶら下げる形で記録する。**

根拠:

1. **重み**: `check_ui_dimensions.py` は PASS しており、`--size-control-xs`(24px) の 🔴 必須フロアも上回っている。§2.4 の 🔵 推奨からの軽微な逸脱であり、`NFR`/`AC` 違反ではない。単独 Issue を新規に立てるほどの重みではない（Issue 乱立は CP-3 の衛生負債になる）。
2. **設計議論での意図確認**: `content/discussions/sp8-auth-i18n-20260819/whiteboard.md` を検索したが、`LoginLink` の `size` を `sm` にする明示的な設計合意は見当たらない（4 名 2 ラウンドの議論で `size` variant への言及なし）。つまり「意図的な二次導線判断」ではなく、fan-out 実装時に深い検討なく選ばれた値である可能性が高い。acceptance_judge が条件 2 で挙げた「意図的か再確認」は妥当な指摘。
3. **検証手段の依存関係**: 視覚的な最終確認（タップしやすさ・見た目）は人間の操作レビューが必要で、それは「プレビューで OAuth 導線が表示される」ことが前提になる。プレビューで導線が出ない理由はまさに項目 1（OAuth App 未登録）と同一原因。したがって「いつ確認できるか」が項目 1 と完全に連動しており、**同じフォローアップの発火条件（OAuth App 登録後の初回操作レビュー）に乗せるのが最も自然**。独立 Issue にすると、項目 1 の解消時にダブルチェックが必要になり見落としリスクがかえって増える。
4. **修正コスト**: `size: 'sm'` → `size: 'default'` への変更自体は 1 行の実装判断（`SD-3` でいう「実装手段」寄りの軽微な変更）であり、仕様解釈の分岐ではない。次に手を入れるセッションが `AskUserQuestion` するまでもなく判断できる。

### 更新後の残課題リスト（5 項目）

| # | 項目 | 判定 |
|---|------|------|
| 1 | OAuth App 未登録（local/production 2 件） | 記録のみ（Issue #140 残存項目）。**+ サブ条件として `LoginLink` size 確認を同時に扱う** |
| 1' | `LoginLink` size='sm'(28px) が §2.4 推奨(32px)未達 | **項目 1 にぶら下げて記録**（独立 Issue 化しない）。OAuth App 登録 → 初回操作レビュー時に「見た目確認」と「`size: 'default'` へ変更するか」をセットで判断する |
| 2 | logout GET CSRF 未対応 | 別 Issue 化（`type:improvement`・低優先度）— 変更なし |
| 3 | LocaleSwitcher 非一本化 | 記録のみ（Issue 化不要）— 変更なし |
| 4 | E2E タイミング揺らぎ根本原因未解明 | 別 Issue 化（`type:improvement`・調査枠・中優先度）— 変更なし |

### Issue #140 クローズ条件への影響

変更なし。`accepted_with_conditions` の条件（項目 1・1'）は **US-2/US-4/US-5/E-11 の受け入れ基準そのものを満たしていない」わけではなく、外部要因（OAuth App 未登録という A-6 相当のユーザー作業）に付随する確認待ち事項なので、Issue #140 は今回分のクローズ対象としてよく、条件は「次回 OAuth App 登録後のフォローアップ操作レビュー」に一本化して引き継ぐ。新規 Issue を追加で立てる必要はない（項目 2・4 の Issue 化のみ実施すればよい）。

## ラウンド 3

### `lead` — 合意
<sub>2026-08-20T09:12:59+09:00</sub>

## consensus（lead）

`acceptance_judge`（受け入れ判定・実行結果ベース）と `backlog_triage`（残課題仕分け）の round1/round2 は方向性で完全一致した。矛盾なし。

- 設計ドキュメント整合（AR-4/AR-5/`infrastructure-design.md` §8.1）: 逸脱なし
- 実行結果（origin/main の squash コミット 5b7601a に対し `acceptance_judge` が自ら `bash tools/run_checks.sh` 等を実行）: 全9項目 PASS・vitest 261件 PASS・依存規則 Warning 0件
- Sprint Planning「編成」欄: `discussion-review(4) + fan-out(2) + 統合(1)` で単独実行なし
- UI/デザイン（§2.4）: 🔴 必須要件は充足（コード確認 + `check_ui_dimensions.py` PASS）。🔵 推奨からの軽微な逸脱1件（`LoginLink` の `size='sm'`=28px）を条件として記録。視覚的最終確認は人間の操作レビューに委ねる

残課題5件は「OAuth App 登録待ち（+ LoginLink size 確認をぶら下げ）」「logout GET CSRF（別Issue化）」「LocaleSwitcher非一本化（記録のみ）」「E2Eタイミング揺らぎ根本原因未解明（別Issue化）」に収束。Issue #144（logout CSRF）・#145（E2Eタイミング根本原因調査）を起票済み。

### `lead` — 判定
<sub>2026-08-20T09:12:59+09:00</sub>

{
  "result": "accepted_with_conditions",
  "next_firing_required": "なし（次スプリントの必須タスクとしては何も残らない。次回 OAuth App 登録後の操作レビューで LoginLink/LocaleSwitcher の視覚的最終確認と size='sm'→'default' 変更要否を確認する、という条件のみ）",
  "follow_up_items": [
    "GitHub OAuth App 登録（local/production 各1件・ユーザー作業・A-6相当）。登録後の初回操作レビューで LoginLink の size 確認とセットで実施",
    "#144: logout エンドポイントの POST化+CSRF対策（type:improvement・sp:1・priority:low）",
    "#145: E2E Cookie送出タイミング揺らぎの根本原因調査（type:improvement・sp:3・priority:medium）",
    "LocaleSwitcher の layout.tsx 非一本化はNext.js 16 + OpenNext Cloudflareのmiddleware非採用に起因する設計判断。Issue化不要、将来の再検討ポイントとして記録のみ"
  ],
  "issue_close_condition": "US-2/US-4/US-5/E-11の受け入れ基準（操作レビュー手順1〜4）を満たしており、残課題はいずれも受け入れ基準の未達ではなく外部要因・付随事項のためIssue #140はクローズしてよい"
}
