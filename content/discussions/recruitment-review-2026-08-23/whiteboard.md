<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: gem-hunter を採用課題の提出物としてシニア 3 名で精査し、スコア付け・合否判定する

- 議題ID: `recruitment-review-2026-08-23`
- 論点: ユーザー指示: 「本リポジトリの最低要件を企業からの採用課題として扱い、実装や PR などを詳細に精査して企業の優秀なシニアエンジニア 3 名による合否判定をチームを組成して行なってください。議論のうえでスコア付けして判定して、本判定結果をユーザーに分かりやすくフィードバックしてください」。

【前提】docs/02_requirements/minimum-requirements.md が『企業から出された課題（与件）』の原文である（第三者著作物。引用せず要件 ID と要約のみ使うこと・NOTICE 参照）。与件の骨子: Next.js v16 以降 + App Router / GitHub API GET /search/repositories / FR-1 キーワード検索・FR-2 一覧（オーナーアイコン + リポジトリ名）・FR-3 詳細遷移・FR-4 詳細に 名前/アイコン/言語/Star/Watcher/Fork/Issue 数・FR-5 詳細はモーダルでなく独立 URL のページ・FR-6 一覧へ戻る導線・FR-7 ページネーション or 無限スクロール / 状態表示（初期・読み込み中・0 件・エラー（通信/API/レート制限を区別 + 再試行手段）・詳細の Not Found） / 非機能（エラー握りつぶし禁止・レート制限考慮・秘匿情報をクライアントへ出さない・打鍵ごとに API を呼ばない・RSC とキャッシュ活用・画像最適化・レスポンシブ・キーボード操作・ラベル/代替テキスト・検索条件を URL に反映・責務分割・API レスポンスの型定義・Lint/フォーマッタ導入） / テスト要件（主要フローのテスト・外部 API モック化・コマンド 1 つで実行・CI で自動実行できる状態） / ドキュメント要件（README にセットアップ手順・設計上の判断/工夫・AI 利用の方法と範囲、重要な意思決定を docs/adr/ に ADR 記録）。

【オーケストレーターが実測した事実（2026-08-23 セッション）】next 16.3.1 / react 19.2.8 / TypeScript strict / pages ディレクトリ不在。src は domain(model,ports) / usecases / infrastructure(github,platform) / ui / composition / shared の層構成、アプリコードは約 8,832 行（テスト除く）。ユニット/結合テストファイル 75 本、E2E spec 21 本（e2e/）。npm scripts: dev/build/start/lint/format/format:check/test/test:watch/test:e2e/check/preview:build/preview:upload/deploy/deploy:ci/cf-typegen。`.github/workflows` は存在しない（GitHub Actions がプラットフォーム制限で使えず撤去・D-23）。`npx prettier --check .` は 125 ファイルで FAIL（tsconfig.json / wrangler.jsonc を含む）で、tools/run_checks.sh にも未接続。ADR は docs/adr/0001〜0015 の 15 本。README は 151 行で、セットアップ・環境変数 8 件の表・技術スタッ
- 参加者: `senior_req`, `senior_arch`, `senior_prod`
- 投稿数: 3
- 更新: 2026-08-23T09:38:44+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

## ラウンド 1

### `senior_req` — 主張
<sub>2026-08-23T09:35:30+09:00</sub>

## 受け入れ基準の再検証

自己申告チェックリスト（`minimum-requirements-checklist.md`）は根拠にせず、実コード・実テストを直接読んで 11 項目を再検証した。

1. **Next.js v16 + App Router**: ✅ `package.json` `next: 16.3.1`。`pages/` ディレクトリ不在（`find app -type f` で確認）。`app/[locale]/page.tsx` 冒頭は Server Component。
2. **キーワード検索で GitHub API 結果が一覧表示**: ✅ `app/[locale]/page.tsx:64-90`（`runSearch` → `searchRepositoriesUseCase`）。GET フォーム経由（`src/ui/search-form.tsx:25`）で打鍵ごとの API 呼び出しなし（フォーム submit のみ・NFR-7 も自然に満たす）。
3. **一覧にオーナーアイコン + リポジトリ名**: ✅ `src/ui/repository-list.tsx:116-142`（`item.owner.avatarUrl` の `<img>` + `item.fullName` へのリンク）。
4. **一覧項目選択で独立 URL の詳細ページへ遷移（モーダルでない）**: ✅ `repository-list.tsx:134-142` は `next/link` の `<Link href="/{locale}/repos/{owner}/{repo}...">`。詳細は `app/[locale]/repos/[owner]/[repo]/page.tsx` という別ルート実体（モーダルではなく実ページ）。
5. **詳細に 名前/アイコン/言語/Star/Watcher/Fork/Issue**: ✅ `src/ui/repository-detail.tsx:51-56, 96-101`（4 統計 + 言語 + 名前 + アイコン）。
   - 🔴 **自己申告との食い違いなし、ただし要精査だった論点**: Watcher 数は `subscribers_count` を採用（`src/infrastructure/github/mapper.ts:85` コメント「watchers_count（star のミラー）ではなく subscribers_count を使う」）。GitHub API の既知の癖（`watchers_count` は `stargazers_count` の同期ミラーで別概念にならない）を踏まえた妥当な設計判断であり、`repository-detail.tsx:23-24` のコメントで「Star 数と同じ値にならないことをテストで検証」と明記、実際 `src/ui/repository-detail.test.tsx` で確認可能。**これは減点対象ではなく、要件を字面通りでなく仕様として正しく解釈した加点材料**。
6. **詳細からトップページへ戻れる**: ✅ `repository-detail.tsx:61`（`BackLink`）、`app/.../page.tsx:95-99`（`backHref` 組み立て・検索条件保持）。
7. **ページネーション/無限スクロールで 2 ページ目以降**: ✅ `src/ui/pagination.tsx` 全体。`<nav>` + `next/link` によるサーバー駆動ページング（GET リンク、JS 不要）。GitHub 検索 API の 1,000 件上限も `maxPageFor` で考慮済み（`pagination.tsx:57-64`）。
8. **読み込み中・0 件・エラーの判別可能表示**: ✅ 読み込み中= `<Suspense fallback={<LoadingIndicator/>}>`（`page.tsx:471-476`）、0 件 = `repository-list.tsx:63-80`（`role="status"`）、エラー = `src/ui/error-notice.tsx`（`role="alert"` + `ErrorKind` ごとの文言・イラスト出し分け、`ERROR_ILLUSTRATION` は `Record<ErrorKind, string>` で網羅性を型で担保）。
9. **レスポンシブ + キーボード操作**: ✅ Tailwind のブレークポイントクラスを随所で確認（例 `repository-detail.tsx:111` `grid-cols-2 sm:grid-cols-4`）。フォームは素の `<form method="get">`・`<Link>` なので Enter/Tab のみで検索から詳細まで到達可能（JS 依存箇所なし）。
10. **主要フローのテストが存在し実行して成功する**: ✅ 自分で `npx vitest run` を実行し実測: **Test Files 79 passed / Tests 908 passed**（自己申告の数字と一致、かつ自分の手で再現できた）。
11. **README にセットアップ手順 + 設計上の判断**: ✅ `README.md:14-30`（セットアップ）、`README.md:70-105`（設計上の判断 3 本）。

**詳細 404 が HTTP ステータスも 404 か**（争点 1 の個別論点）: ✅ `e2e/sp-6-notfound.spec.ts:19-22` で `page.goto()` の実レスポンスを取得し `expect(response?.status()).toBe(404)` を実測している。実装側も `app/.../page.tsx:188-190` で `repository === null` のとき `notFound()`（Next.js のネイティブ 404 機構）を呼んでおり、Suspense 境界の外（`notFound()` 判定より前）に置くというコメント（`page.tsx:41-47`）どおりの配置になっている。**主張どおり動く。**

## 争点 1 への見解

**結論**: 与件の受け入れ基準 11 項目は全件、実コードと実テストで確認でき、自己申告と実物の食い違いは見つからなかった。個別に疑わしいとされた 4 点（Watcher=subscribers_count・ページネーション・エラー種別出し分け・404 の HTTP ステータス）はいずれも実装・テストの両方で裏付けが取れた。

- Watcher の実装判断は GitHub API の仕様理解に基づく正しい選択（`watchers_count` を額面通り使うほうがむしろ誤り）
- ページネーションは無限スクロールでなくページ番号方式だが、与件は「ページネーション**または**無限スクロール」なので要件を満たす（`ADR 0008` に選定理由あり）
- エラー種別は `ErrorKind` の型で網羅されており、`network`/`rateLimitPrimary`/`rateLimitSecondary`/`auth`/`upstream`/`validation`/`notFound` の 7 種を区別（与件が求める「通信失敗・API エラー・レート制限超過の区別」を上回る粒度）

## 争点 2 への見解

**結論**: スコープ拡張は採用課題としては**プラスとマイナスが併存**し、単純にどちらかに倒せない。

- プラス材料: 与件の 11 項目を土台としてきちんと満たしたうえでの拡張であり、`README.md:95-105`（`AR-5`）で「実装しなくてよいであって実装してはならないではない」と明示的に線引きを言語化している。1.2 節の対象外（お気に入り・通知・課金・独自スコアリング）を実際に避けている点も確認できた（`AR-5` の自己制約が実際に守られている）
- マイナス材料: 採用課題という文脈では「読解力・スコープ判断力」も評価対象になりうる。Gem Index・OAuth・i18n・日次ダイジェスト・LP・AI ハーネス一式（`.claude/`・`docs/rules/` 全体）は与件の 11 項目の相対的な視認性を下げ、レビュアーが「どこまでが課題への回答か」を判別するコストを増やす。README・ADR がこの追跡を助けてはいるが、コスト自体はゼロにならない
- 「主体性」の評価は文脈次第で、与件が明示的に対象外とした認証（OAuth）を追加したことは、要件の境界線を尊重する姿勢としては評価できる反面、課題の指示範囲を厳密に守ることを求める企業文化では減点要因になりうる

## 採点

| 軸 | 点数/満点 | 根拠 |
|---|---|---|
| A. 機能・技術要件充足 | 28/30 | FR-1〜7・状態表示 5 種すべて実コードで確認、404 も実際に HTTP 404。減点 2 は「過剰実装が要件充足の視認性を下げている」観点（争点 2）を軽く反映 |
| B. コード品質・アーキテクチャ | 18/20 | ACL（`mapper.ts`）・zod DTO 検証・値オブジェクトによる境界防御が実装として機能している。詳細評価は `senior_arch` に譲る |
| C. テスト | 16/20 | 908 テスト自分で実行し全通過を確認。ただし GitHub Actions が存在せず「CI で自動実行できる状態」の字面要件は自前スクリプト（`tools/run_checks.sh`）での代替に留まる（詳細は `senior_arch`/`senior_prod` と合議） |
| D. 非機能 | 12/15 | a11y・レスポンシブ・URL 状態は良好。ただし `npx prettier --check .` を自分で実行したところ 125 ファイルで FAIL し `tools/run_checks.sh` に未接続（Lint は接続済みだが Format は未接続）。「Lint/フォーマッタを導入し規約を機械的に検証できる状態にする」の後半が字面上未達 |
| E. ドキュメント | 9/10 | README が要求 3 点（セットアップ・設計判断・AI 利用範囲）を全て具体的に記載。ADR 15 本 |
| F. プロセス | 4/5 | 51 コミット全て `feat:`/`fix:`/`docs:` 等の規約付き squash マージ、PR 番号と Issue 番号が対応 |

**合計: 87/100 → 判定バンド: Hire**

## 他レビュアーへの論点提起

1. `senior_arch` へ: C 軸のテスト評価で「CI 不在」をどこまで減点すべきか。テスト自体の質・網羅性（79 ファイル・E2E 21 本・axe 込み）は高いが、「コマンド一つで実行でき CI で自動実行できる状態」を字面通り読むと GitHub Actions ワークフローの不在は要件未達とも読める。私は 16/20 に留めたが、テストの質を重視してもっと高くすべきか、CI 不在をより重く見るべきか判断を仰ぎたい。
2. `senior_prod` へ: Prettier が `run_checks.sh` に未接続かつ 125 ファイルで実際に FAIL している事実（`npx prettier --check .` を自分で実行して確認済み）は、「品質ゲートの実効性」（争点 3）としてどの程度の減点が妥当か。私は D 軸で 3 点減点したが、これは F 軸（プロセスの質）にも波及すべきという見方もあると思う。
3. 全員へ: スコープ拡張（争点 2）を A 軸の減点要因として扱うのが適切か、それとも A 軸は純粋に「11 項目を満たしているか」だけで判定し、スコープ論はコメント（strengths/concerns）に留め点数化しない方が公正か。

### `senior_prod` — 主張
<sub>2026-08-23T09:37:54+09:00</sub>

## セキュリティ・本番適格性

- ✅ 秘匿情報のクライアント露出なし: `grep -rn "NEXT_PUBLIC" src app` はヒット 0 件。
- ✅ OAuth（`src/infrastructure/github/oauth.ts`）: `readCredentials()`（24-32行）で client secret を1ファイルに閉じ込め。CSRF は `state`（`app/api/auth/login/route.ts:26` `crypto.randomUUID()`）+ callback 側 `timingSafeEqualString`（`app/api/auth/callback/route.ts:41-49`）でタイミング攻撃を回避しつつ照合。PKCE は無し（confidential client・secret を持つサーバー実装のため必須ではない・妥当）。
- ✅ オープンリダイレクト対策: `callback/route.ts:56` `resolveLandingHost()` が `GITHUB_OAUTH_CALLBACK_URL` 由来の許可ホストと突き合わせ、`Host` ヘッダをそのまま信頼しない（PR #141 指摘を踏まえた実装、コメントに実測の脅威モデルが明記されている）。
- ✅ セッション Cookie（`src/infrastructure/platform/session-cookie.ts`）: `jose` の `EncryptJWT`（`alg:'dir'`, `enc:'A256GCM'`、17-21行 32byte 鍵）で access token を JWE 暗号化。復号失敗は理由問わず `null`（77-91行、fail-safe）。発行側（`app/api/auth/callback/route.ts:79-85`）は `httpOnly:true` `secure: isSecureConnection(...)` `sameSite:'lax'` `path:'/'` `maxAge` を明示。テスト（`callback/route.test.ts`）で `HttpOnly`/`Secure`/`SameSite=Lax` の実ヘッダ文字列まで検証している。
- ✅ レート制限キーの HMAC 化（`src/infrastructure/platform/rate-limit-key.ts`）: 生IP（`cf-connecting-ip` 優先・`x-forwarded-for` はフォールバックのみで唯一の識別子にしない、17-22行のコメントで明記）は `hashRateLimitKey()`（35-47行、HMAC-SHA256 + salt）で必ず変換してから利用。生IPをログ/戻り値に出さない設計がコメントで明言され、`clientIpOf` の呼び出し側も追った限り違反なし。
- ✅ README 描画の XSS 対策（`src/ui/readme-html.ts`）: `sanitize-html` を許可リスト方式で1パス適用。`script`/`style`/`iframe`/`on*`属性/`javascript:` スキームを除去、href/src は `http:`/`https:` のみ許可（`SAFE_URL_SCHEMES`）、`parseStyleAttributes:false` で CSS injection 経路も遮断。見出し+2シフト・外部リンクへの `rel="noopener noreferrer"` も同一パスで処理しており実装として丁寧。
- ✅ エラーハンドリング: `src/domain/errors.ts` が `network`/`rateLimitPrimary`/`rateLimitSecondary`/`auth`/`validation`/`notFound`/`upstream` の7種を型で判別。`AuthError` は「サーバー設定の問題として内部情報を出さない」と明記（108-116行）。`ErrorNotice`（`src/ui/error-notice.tsx`）は `role="alert"`・装飾イラストをライブリージョン外に配置・コントラスト検証済みトークンのみ使用と、a11y への配慮がコメントレベルで一貫。
- ✅ 404: 詳細ページは `next/navigation` の `notFound()`（実装確認、58行・189行）を使用しており HTTP ステータスも実際に 404 になる（Next.js の標準挙動どおり）。
- ⚠️ `next/image` 不使用（`ErrorNotice` 含め素の `<img>`）: ADR/設計文書（`infrastructure-design.md` INF-11・ADR 0013 T-2）でコスト（Cloudflare Workers の関数実行コスト）を理由に意図的に見送り、`width`/`height` 明示で CLS を防ぐ代替策も取っている。Star数の多い有名OSSのアバターを毎回自サーバー経由で再最適化しない判断自体は Workers 環境では合理的だが、与件の「画像最適化」を素朴に満たしているとは言い切れず、"要件を満たす代替策" として評価すべき論点（争点1・2 に関連、senior_req と要突き合わせ）。
- 🔴 CI 不在: `.github/workflows` は存在せず（Actions がプラットフォーム制限で撤去・D-23）、`tools/run_checks.sh` を grep しても `prettier`/`format` の呼び出しは1件もヒットしない（実際に確認: `grep -n "prettier\|format" tools/run_checks.sh` → 0件）。つまり `npm run format:check` はどのゲートからも呼ばれておらず、フォーマッタ違反が有れば気づけない状態のまま main に入り続ける構造的欠陥。「CI で自動実行できる状態」「Lint/フォーマッタ導入」という与件の非機能を額面通り満たしているとは言い難い（後述・争点3）。

## プロセス評価

- **PR 本文の質は極めて高い**: サンプリングした PR #293（+2350/-102, 38ファイル, 13コミット）と #440（+4386/-139, 40ファイル, 37コミット）はいずれも、目的・仕様分岐の決定根拠・層別の変更点・参照要件ID・`run_checks` 結果表・実機実測データ（例: #440 は CPU 実測 5 回計測・0 ヒット率の実測データつき）・操作レビュー手順まで揃う。取ってつけた説明ではなく実測値に基づく記述が多い。
- **セルフレビューが実際に欠陥を捕まえている**: PR #440 は Layer 1 セルフレビューで CONFIRMED 39 件を発見・全修正し、うち3件は「修正前後をプレビュー実機で確認」（トークン数無制限のCPU枯渇→HTTP 503を実際に再現、ページング上限バグを実際に再現）。指摘の捏造でなく実害を実測してから直している点は評価できる。
- ⚠️ **セルフレビューの独立性に構造的限界**: PR #293 は作成から マージまで **32分**（00:53→01:25）。同一セッション・同一AIが「実装→自分の差分をレビュー→対応→マージ」を数十分で完結させており、第三者レビューに相当する独立した目が一度も入っていない。README の AI 利用範囲節（107-116行）でも「人間が判断する領域は A-1〜A-6 と仕様解釈の分岐のみ」と明言されており、**コードの実装判断・品質判断のほぼ全てを人間が一度も見ずに AI が自己完結させている**ことが自己申告として率直に書かれている点は誠実だが、採用課題としては「候補者本人の技術判断」をどこまで読み取れるかが疑わしくなる（争点6）。
- 🔴 **スコープの逸脱が甚大**: main は 50 コミット（squash）だが Issue/PR 番号は #440 まで進んでおり、与件の11項目を満たす MVP（概ね SP-1〜SP-10 あたりで足りるはず）を大きく超えて Gem Index 独自指標・OAuth ログイン・i18n・日次ダイジェストRSS・LP・AI生成ビジュアル・自律運用ハーネス一式（.claude/ + docs/rules/ 多数）まで実装が続いている。「渡された課題の範囲を正確に実装し切る」という採用課題の基本ルールから見ると、大幅な逸脱であり、単独業務ならスコープ管理の重大な懸念に映る（争点2、senior_req と評価軸が重なる）。
- ✅ Issue 運用・ADR は 15 本、決定はほぼ全て `D-n` 番号で追跡されており、少なくとも記録の一貫性・トレーサビリティは高い。

## 争点 5 への見解

**結論: セキュリティ・本番運用の実装自体に致命的欠陥は見当たらないが、品質ゲート（CI/フォーマッタ）の不備が「本番運用として成立している」という主張のグレーゾーンになっている。**

- 秘匿情報の扱い・OAuth の CSRF/オープンリダイレクト対策・セッション Cookie の暗号化と属性・レート制限キーの HMAC 化・README サニタイズは、いずれも実コードを読んだ限り妥当な設計と実装（上記チェックリスト参照）。
- 一方で「CI で自動実行できる状態」を全面的に満たしているとは言えない: GitHub Actions が無く、`run_checks.sh`（セッション手動実行という代替ゲート）にも `format:check` が接続されていない。これはセキュリティの直接的な穴ではないが、「本番品質を機械的に担保できているか」という本番適格性の観点では減点対象。

## 争点 6 への見解

**結論: AI 全工程自律実行の申告は誠実だが、採用課題としては「候補者本人が何を判断したか」を検証する材料に乏しく、能力評価としてはむしろ割り引いて見るべき。**

- README の NFR-31 節（107-116行）は虚偽・誇張がなく、人間が関与する範囲（A-1〜A-6・仕様分岐のみ）を具体的に定義しており、記録としての信頼性は高い（「自律実行した」という主張自体は裏付けが取れる）。
- ただし採用判断の材料としては、コードの実装判断・アーキテクチャ選定・レビュー対応のほぼ全てが AI 単独で完結しており(PR #293 の32分マージがその典型)、**「この候補者がどの程度自力でコードを書き、レビューし、トレードオフを判断できるか」を直接には読み取れない**。評価すべきは「AI をどう設計・統制したか（ルール・ゲート設計者としての能力）」に軸足を移す必要があり、一般的な「実装力」を測る採用課題としては解釈がねじれる。この点は面接で本人に「どこまで自分で判断し、どこを AI に委ねたか」を直接確認すべき最重要事項として挙げたい。

## 採点

| 軸 | 点数 | 根拠 |
|---|---|---|
| A（30） | 26 | FR-4 の watcher 実装（`subscribers_count`、`mapper.ts:85`）・詳細404（`notFound()`）は実コードで確認でき妥当。画像最適化は代替策はあるが素朴には満たさない（要 senior_req 突合） |
| B（20） | 17 | 層分割・ポート/アダプタ・zod DTO 検証は一貫（未読部分は senior_arch 主担当のため推定） |
| C（20） | 15 | axe 自動検査・キーボードE2E（`e2e/sp-10.spec.ts`）は水準が高いが、CI 不在とフォーマッタ未接続で「コマンド1つ・CI 実行可能性」を額面通り満たさない |
| D（15） | 14 | セキュリティ実装（OAuth/Cookie/HMAC/sanitize-html）・a11y（axe + フォーカス管理）・レスポンシブ（横スクロール検査）・エラー種別網羅は水準が高い。CI/フォーマッタ不備を1点減点 |
| E（10） | 9 | README・ADR15本は充実。ただし NFR-31 節は「読めば分かる」が採用判断の解釈を難しくする副作用がある |
| F（5） | 2 | PR記録の質・実測ベースの自己レビューは優秀だが、スコープ逸脱が甚大かつセルフレビューの独立性に構造的限界（同一AIが数十分で自己完結）。「候補者本人の判断」を読み取る材料としては弱い |
| **合計** | **83** | **Hire 相当**（ただし F と C の構造的懸念は面接で要確認） |

## 他レビュアーへの論点提起

1. senior_req へ: FR-4 の `watcherCount = subscribers_count` は技術的に正しい判断だと思うが（`watchers_count` は star のミラーというコメントは GitHub API の実際の仕様と一致）、与件が「Watcher 数」という言葉で `watchers_count`（見た目の指標）を期待していた可能性は無いか？ 与件原文の該当箇所の文言だけで判定してほしい。
2. senior_arch へ: CI（GitHub Actions）が使えないプラットフォーム制約は事実だとしても、「セッションが手動で `run_checks.sh` を叩く」運用は与件の「CI で自動実行できる状態」の要求を満たしていると評価するか？ B/C 軸での減点幅について意見がほしい。
3. 全員へ: スコープ逸脱（Gem Index・OAuth・i18n・LP・AI生成ビジュアル・自律運用ハーネス）を「主体性・プロダクト思考」としてプラス評価するか、「指示範囲を守れない」というマイナス評価にするか。私は F 軸を厳しめに採点したが、A/B/E 軸でプラスに評価している可能性がある2人の意見を聞きたい。

### `senior_arch` — 主張
<sub>2026-08-23T09:38:06+09:00</sub>

## アーキテクチャ評価

**層と依存方向**: `src/domain`（純粋・I/O 非依存）→ `src/usecases` → `src/infrastructure` → `src/composition`（合成根）→ `app/`/`src/ui` の依存方向を実コードで確認した。ports は 7 本（`auth-port.ts` / `cache-port.ts` / `clock-port.ts` / `gem-digest-port.ts` / `gem-index-port.ts` / `rate-limit-port.ts` / `repository-query-port.ts`）で、いずれも実装詳細（Github・Cookie 等）をポート名・メソッド名に持ち込んでいない（`auth-port.ts:1-12` のコメントで命名規律を明記）。`src/composition/container.ts:26` に「DI コンテナは使わない（YAGNI）」と明記し、実際に素の factory 関数のみで束ねている — 過剰な汎化に振れていない良い判断。

**値オブジェクト**: `src/domain/model/` 配下は 14 本、ブランド型 + スマートコンストラクタの型で統一されている（`repository-full-name.ts:12-40`, `page-number.ts:19-31`, `per-page.ts:7-25`）。URL 由来の緩い入力用に `tryX`（既定値へフォールバック）と、プログラム内部用の厳格な `x`（例外送出）を両方持つ設計が一貫している。ただし 14 本のうち約半分（`gem-index.ts` / `gem-keyword.ts` / `gem-shortlist.ts` / `gem.ts` / `digest-diff.ts` / `date-seed.ts` / `locale.ts`）は与件外機能（Gem Index・日次ダイジェスト・i18n）専用であり、与件（FR-1〜7）だけに必要なのは `search-keyword` / `search-query` / `page-number` / `per-page` / `sort-order` / `repository-full-name` / `repository` の 7 本程度（争点 4 参照）。

**ACL（zod + mapper）**: `src/infrastructure/github/dto.ts` が GitHub API レスポンスを zod でスキーマ検証し、`mapper.ts:13-17,65-69` がパース失敗を握りつぶさず `UpstreamError` へ翻訳している。`private` フィールドを **必須**（optional にしない）にして fail-closed にした設計判断がコメントで明記されており（`dto.ts:39-41`）、`mapper.ts:29,72-74` で検索結果の除外・詳細の null 化の二重防御を実装、実際にそう動くことをコードで確認した。`httpsUrl`（`dto.ts:16-19`）で `javascript:` 等の擬似スキームを弾く多層防御も入っている。

**エラー型**: `src/domain/errors.ts` の `ErrorKind`（7 種）は `github-repository-query.ts:151-193` の `toDomainError` で HTTP ステータス→種別への変換が判定順序込みで実装されている。403 を一次レート制限→二次レート制限→認証エラーの順で判定する理由がコメントで明記され（`github-repository-query.ts:147-169`）、`retry-after`（delta-seconds と HTTP-date の両形式）・`x-ratelimit-reset` の壊れた値への防御（`retryAfterSeconds`/`resetAt` 関数）まで作り込まれている。

**キャッシュ**: `CachePort` は `get/set/invalidate` のみに絞られており（`cache-port.ts:1-12`)、`CachingRepositoryQuery`（`cached-repository-query.ts`）が read-through + **single-flight**（同一キーへの並行リクエストを 1 回の fetch へ集約、`readThrough`（`cached-repository-query.ts:96-131`））を実装。404 はキャッシュしない判断も one-off ではなく `search`/`findDetail`/`findReadme` で一貫している。

**過剰/不足の評価**: 層分割・ACL・エラー型・CachePort はいずれも与件の非機能要求（型定義・責務分割・エラー握りつぶし禁止・レート制限考慮）に直接紐づいており、これ自体は過剰ではない。過剰に見える部分（値オブジェクト約半分・GemIndexPort/GemDigestPort）は、実装された機能全体（Gem Index 等）に対しては適正だが、**与件単体**に対しては明確に超過している（争点 4 で詳述）。

## テスト評価

**実測**: `npx vitest run` を実行し `79 files / 908 tests passed` を確認した（自己申告チェックリストの数字と一致するが、これは私が独立に実行した結果）。`npx tsc --noEmit` はエラー 0、`npx eslint` はエラー 0（warning 3 件のみ）で通過した。

**何が保証されているか**:
- 単体テストはモックライブラリではなく手書きフェイク（`cached-repository-query.test.ts:12-71` の `fakeClock` / `fakeRepositoryQueryPort`）で ports を差し替えており、モックの過剰指定によるテストの脆さが少ない。
- インフラ境界（`github-repository-query.test.ts`）は MSW（`msw/node` の `setupServer`）でネットワーク層をインターセプトしており、fetch の実際の呼び出し・Response のパース・HTTP ステータス→ドメインエラー変換までを検証している（`fetch` を直接モックする方式より現実に近い）。
- **並行性が明示的にテストされている**: `cached-repository-query.test.ts:161,252,352` で `Promise.all` を使い、同一キーへの並行リクエストが inner を 1 回しか呼ばないこと（single-flight）を検証している。この種の並行処理の正しさをテストするプロジェクトは少なく、ここは明確な加点要素。
- E2E（`e2e/*.spec.ts` 21 本）は `sp-N.spec.ts` のファイル名で `user-story-map.md` の `SP-n` と 1:1 対応しており、SD-2「操作レビュー手順を E2E に写す」の構造的な充足が確認できる。

**保証されていないこと・ギャップ**:
- **CI 不在によりテストの「継続的な」実効性がない**（争点 3 で詳述）。ローカル/セッションで `npx vitest run` すれば通るが、push・PR のたびに自動実行される仕組みがない。
- カバレッジ数値（%）を私は生成・確認していない。908 件が「何割の分岐を通しているか」は未検証（自己申告済みの可能性はあるが、それも本来は実測で検証すべき対象）。
- `tools/run_checks.sh` は `npx eslint` のみを Lint として実行し、`format:check`（Prettier）を呼んでいない（`run_checks.sh:92,94` を実測 grep で確認）。テスト・型・Lint は機械的に守られているが、フォーマットの機械的検証は品質ゲートに接続されていない。

## 争点 3 への見解

**結論**: 与件のテスト要件「CI で自動実行できる状態」、および非機能要件「Lint/フォーマッタで機械的に検証できる状態」の **どちらも実質的に満たしていない**。

根拠:
- `.github/workflows` が存在しないことを実測確認した（`ls .github/workflows` → No such file or directory）。`tools/run_checks.sh` は Claude セッションが手動 bash 実行するスクリプトであり、push/PR をトリガに自動起動する仕組みが存在しない。「コマンド 1 つで実行できる」（`npm run check`）は満たすが、「CI で自動実行できる」は別の要件であり満たしていない。
- `npx prettier --check .` を実測すると **125 ファイルで FAIL**、うち **35 ファイルは `src/`・`app/` の実アプリコード**（`cache.ts` / `cached-repository-query.ts` / `search-query.ts` / `repository-detail.tsx` 等 — 私が上で高く評価した設計ファイル自身を含む）。`tools/run_checks.sh` は Lint（eslint）のみを実行し `format:check` を呼んでいないため、この崩れは品質ゲートを一度も通過チェックされていない。「フォーマッタで機械的に検証できる状態」の半分（フォーマッタ側）が実質未接続。
- 一方、`tsc --noEmit`・`eslint`・`vitest run` は実測でクリーンに通過する（型エラー 0・eslint 0 error/3 warning・908 test pass）。コード自体の型・テスト品質は高いが、「機械的検証が効いている」という主張は Prettier に関しては過大。

**減点幅**: C（テスト 20 点）から CI 自動実行の欠如で -4〜5 点、D（非機能）または F（プロセス）からフォーマッタ未接続で -2 点、合計で関連 2 軸から 4〜7 点程度の減点が妥当と考える（他レビュアーの配点と重複しないよう、lead には C 軸に集約することを提案する）。

## 争点 4 への見解

**結論**: 与件（FR-1〜7 のみ）に対しては軽度〜中度の過剰設計、実装された機能全体（Gem Index・日次ダイジェスト・OAuth・i18n 込み）に対しては概ね適正。**YAGNI 違反と呼べる実装は見当たらなかった**（過剰の主因は「アーキテクチャの選択」ではなく「スコープの拡張」）。

根拠:
- 層分割・ACL（zod）・エラー型・`CachePort`（single-flight 込み）は、いずれも与件の非機能要求（型定義・責務分割・エラー握りつぶし禁止・レート制限考慮）に直接紐づく実装であり、根拠のない先回り抽象化ではない。`container.ts:26` の「DI コンテナは使わない（YAGNI）」、`gem-index-port.ts` 内の「1 箇所しか使わない抽象を先回りで足さない」といったコメントから、実装者が YAGNI を意識して判断していることがコードから読み取れる。
- `CachePort` は「1 箇所しか使わないレイヤーの先回り追加」ではなく、`search`/`findDetail`/`findReadme` の複数箇所で使われ、かつ与件の非機能要件「レート制限考慮」に直接対応するため YAGNI 違反ではない。
- 値オブジェクト 14 本のうち約半分（`gem-index` / `gem-keyword` / `gem-shortlist` / `gem` / `digest-diff` / `date-seed` / `locale`）は与件外機能専用。これは「過剰設計」というより「与件で要求されていない機能の実装量」の問題であり、争点 2（スコープ拡張の是非）と同根の論点として lead に一本化を提案する。
- `GemDigestPort`（上位 N 件のスライス）と `GemIndexPort`（全量照会）が母集団の違いを理由に意図的に分離されている（`gem-digest-port.ts:16-20`, `gem-index-port.ts:60-63` の相互参照コメント）など、設計判断が場当たり的でなく一貫して文書化されている。

## 採点

| 軸 | 配点 | 点数 | 根拠 |
|---|---|---|---|
| A. 機能・技術要件充足 | 30 | 26 | 実測確認できた範囲（Watcher=subscribers_count・`notFound()` による同期 404）は正しいが、11 項目全件の一次検証は senior_req の担当領域のため保留気味に採点 |
| B. コード品質・アーキテクチャ | 20 | 18 | 層分割・ACL・エラー型・値オブジェクトの実装品質は高い。実アプリコード 35 ファイルが Prettier 未整形（`cache.ts` 等の中核ファイル含む）である点を減点 |
| C. テスト | 20 | 16 | テストの設計・網羅（single-flight の並行性テスト等）は優秀だが、CI 自動実行の不在は与件のテスト要件を直接満たしていないため大きめに減点 |
| D. 非機能 | 15 | 11 | 私のレンズ外だが、fail-closed な private 判定・URL スキーム検証など防御的実装を確認した範囲で暫定点。セキュリティ全体は senior_prod の判定に譲る |
| E. ドキュメント | 10 | 8 | ADR 15 本・README の存在は確認したが内容の精査は senior_req/senior_prod に譲る。暫定点 |
| F. エンジニアリングプロセス | 5 | 3 | `git log --oneline main` は 34 コミットのみだが、Issue/PR 番号は #440 まで進んでおり、独立ブランチ `telemetry/cost-data` に 86 件の自動コミットがあることを実測確認した。プロダクトコードと無関係な運用オーバーヘッドの比率が高い |

**合計: 82 / 100（Hire 相当）**（他 2 名との合議前の暫定値）

## 他レビュアーへの論点提起

1. **senior_req へ**: `notFound()` による同期 404 と `subscribers_count`（Watcher）は確認したが、FR-1〜7・受け入れ基準 11 項目全件の再検証結果を聞きたい。過剰実装（Gem Index 等）が与件本来の 11 項目のどれかを圧迫・複雑化させていないか（例: `app/[locale]/repos/[owner]/[repo]/page.tsx` の `gemListState`/`cameFromGemList` 分岐は Gem 一覧機能のために詳細ページのロジックが増えている）。
2. **senior_prod へ**: `main` への実マージは 34 コミットのみだが、Issue/PR 番号は #440 まで進み、うち相当数（`telemetry/cost-data` ブランチだけで 86 件）がアプリ機能と無関係な自動化・運用コミットだった。これを「エンジニアリングプロセスの質（F 軸）」としてどう評価すべきか、面接で確認すべき懸念として扱うべきか問いたい。
3. **両名へ**: 争点 3 の減点（私は C 軸に -4〜5 点、D/F のどちらかに -2 点を提案）が、それぞれの担当軸の配点と重複していないか — 合議時に一本化したい。
