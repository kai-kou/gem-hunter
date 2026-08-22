# 与件（最低要件定義）充足チェックリスト

> **目的**: [`minimum-requirements.md`](./minimum-requirements.md)（第三者提供の与件・原文）に対して、現時点の実装が **最低限の与件をすべて満たしているか** を、実際のコード・テスト実行結果で 1 項目ずつ事実確認した記録。
>
> **検証日時**: 2026-08-22 08:47 JST（`npm test` 実行時刻を起点とする一連の検証） / **検証コミット**: `c310e1f`（`main` 相当）/ **ブランチ**: `claude/minimum-requirements-checklist-98diee`
>
> **判定記号**: ✅ 充足（実物で確認）/ ⚠️ 充足だが注記あり・または部分的 / ❌ 未充足
>
> 🔴 **本ファイルは与件の再掲ではない**。与件の本文は原著者に権利が帰属するため（[`NOTICE`](../../NOTICE)）、ここでは **要件 ID と短い要約** のみを参照キーとして用い、原文は引用しない。原文は上記リンク先を参照する。

---

## 0. 総括

| 区分 | ✅ | ⚠️ | ❌ |
|---|---|---|---|
| 2. 技術要件 | 5 | 0 | 0 |
| 3. 機能要件（FR-1〜FR-7） | 7 | 0 | 0 |
| 3.1 画面構成 | 8 | 0 | 0 |
| 3.2 状態ごとの表示 | 4 | 1 | 0 |
| 4. 非機能要件 | 11 | 2 | 0 |
| 5. テスト要件 | 3 | 1 | 0 |
| 6. ドキュメント要件 | 4 | 0 | 0 |
| **合計** | **42** | **4** | **0** |

**結論: 与件の機能要件・技術要件は全件充足しており、未充足（❌）はゼロ。** ただし以下 4 件に注記がある（詳細は各項）。

1. ⚠️ **初期状態（未検索）の文言**: 「検索を促す」明示文言は撤去済みで、プレースホルダ + 説明文 + ヒーロー画像が担う（与件 §3.1.1 の「プレースホルダで入力を促す」は満たす）
2. ⚠️ **Prettier の機械検証が現状 red**: `npm run format:check` が 110 ファイル（うち `src` 26 / `app` 10 / `e2e` 11）で失敗し、`npm run check` にも未接続
3. ⚠️ **画像最適化は `next/image` を使わない**（`INF-11` の意図的判断。GitHub の `?s=N` + 明示寸法 + `loading="lazy"` で代替）
4. ⚠️ **CI でのテスト自動実行が現状ない**: GitHub Actions が制限中で撤去済み（`D-23`）。テスト自体はコマンド 1 つで実行でき環境変数に依存しないため「CI で自動実行できる状態」ではある

---

## 2. 技術要件

| # | 要件 | 判定 | 事実確認の根拠 |
|---|---|---|---|
| T-1 | Next.js v16 以降 | ✅ | `node -p "require('next/package.json').version"` → **16.3.1**（`package.json:33` も `"next": "16.3.1"`） |
| T-2 | App Router を使用（Pages Router を使わない） | ✅ | `app/[locale]/` 配下に `layout.tsx` / `page.tsx` が存在。`pages/` `src/pages/` ともに **不在**（`ls` で確認） |
| T-3 | データソースは `GET /search/repositories` | ✅ | [`src/infrastructure/github/github-repository-query.ts:43`](../../src/infrastructure/github/github-repository-query.ts) `new URL('/search/repositories', apiOrigin())`。詳細は `GET /repos/{owner}/{repo}` |
| T-4 | UI ライブラリ（任意） | ✅ | Tailwind CSS v4 + shadcn/ui（Radix UI）。[ADR 0001](../adr/0001-ui-stack.md) |
| T-5 | TypeScript（推奨） | ✅ | 全ソースが `.ts` / `.tsx`。`tsconfig.json` は `"strict": true`。`npx tsc --noEmit` **PASS** |

---

## 3. 機能要件

| ID | 要件（要約） | 判定 | 事実確認の根拠 |
|---|---|---|---|
| FR-1 | キーワード入力による検索 | ✅ | [`src/ui/search-form.tsx`](../../src/ui/search-form.tsx) は `<form method="get" role="search">` + `<label>` + `<Input>` + submit ボタン。ネイティブ GET フォームなので Enter でも送信できる（E2E `e2e/sp-10.spec.ts:48-49` が `keyboard.type` → `press('Enter')` で検証） |
| FR-2 | 検索結果の一覧表示（オーナーアイコン + リポジトリ名） | ✅ | [`src/ui/repository-list.tsx`](../../src/ui/repository-list.tsx) が `<ul>` → `<li>` で 1 件 1 カード。`<img src={avatarUrl}?s=80>` と `item.fullName`（`owner/repo`）を表示 |
| FR-3 | 一覧項目から詳細へ遷移 | ✅ | 同ファイルの `<Link href={/${locale}/repos/{owner}/{repo}}>`。`after:absolute after:inset-0` でカード全体がクリック領域 |
| FR-4 | 詳細に 名前・アイコン・言語・Star・Watcher・Fork・Issue 数 | ✅ | [`src/ui/repository-detail.tsx`](../../src/ui/repository-detail.tsx) の `numericStats`（stars / watcherCount / forkCount / openIssueCount）+ アバター `<img>` + `fullName` + `primaryLanguage`。🔴 Watcher は `watchers_count`（star のミラー）ではなく **`subscribers_count`** を採用（`src/infrastructure/github/mapper.ts:85`・`dto.ts:70`） |
| FR-5 | 詳細は独立ページ（モーダルでない・固有 URL） | ✅ | [`app/[locale]/repos/[owner]/[repo]/page.tsx`](../../app/%5Blocale%5D/repos/%5Bowner%5D/%5Brepo%5D/page.tsx) が実ルート。モーダル実装・Parallel/Intercepting Routes は存在しない |
| FR-6 | 詳細から一覧へ戻る導線 | ✅ | `RepositoryDetail` 冒頭の `<BackLink>`（[`src/ui/back-link.tsx`](../../src/ui/back-link.tsx)）。加えて共通ヘッダー（`SiteHeader`）からもトップへ戻れる。検索条件（keyword/page/sort/per_page）を保持して戻る（`buildSearchUrl`） |
| FR-7 | 大量結果への対応（ページネーション or 無限スクロール） | ✅ | [`src/ui/pagination.tsx`](../../src/ui/pagination.tsx)（前後ページの GET リンク + `aria-current="page"`）。ページネーションを選び無限スクロールを採らない判断は [ADR 0008](../adr/0008-pagination-over-infinite-scroll.md) |

### 3.1. 画面構成

| # | 要件（要約） | 判定 | 事実確認の根拠 |
|---|---|---|---|
| S-1 | トップ: ヘッダーにアプリタイトル | ✅ | `app/[locale]/page.tsx` が `<SiteHeader title={messages.home.title}>` を描画（`messages/ja.json` → `home.title = "gem-hunter"`） |
| S-2 | トップ: キーワード入力欄・未入力時はプレースホルダで促す | ✅ | `SearchForm` の `placeholder={labels.placeholder}` → `home.searchPlaceholder = "キーワードで GitHub を検索(例: react)"` |
| S-3 | トップ: 検索ボタン + Enter で実行 | ✅ | `<Button type="submit">` + ネイティブ GET フォーム。E2E で Enter 実行を検証（上記 FR-1） |
| S-4 | トップ: 1 件 1 カードを縦に並べ、カード全体が遷移対象 | ✅ | `repository-list.tsx` の `<li className="relative flex gap-3 py-4">` + リンクの `after:inset-0`（見出しだけをリンクにして読み上げの冗長化を避ける設計） |
| S-5 | トップ: 2 ページ目以降の取得 | ✅ | `Pagination` が `?page=N` を組み立て、`maxPageFor(perPage)`（GitHub 検索 API の 1,000 件上限由来）を超えるリンクを出さない |
| S-6 | 詳細: ヘッダーにアプリタイトル + トップへの導線 | ✅ | 詳細ページも `SiteHeader` を共有（`app/[locale]/repos/[owner]/[repo]/page.tsx` の `header`）。`BackLink` が一覧への戻り導線 |
| S-7 | 詳細: アイコン・リポジトリ名・言語 | ✅ | `repository-detail.tsx`（アバター `?s=128` / `<h2>` の `fullName` / `primaryLanguage`） |
| S-8 | 詳細: 統計を項目名と数値の対で表示 | ✅ | `<dl>` + `<dt>`（ラベル + アイコン）/ `<dd>`（`Intl.NumberFormat` 整形値）。Star / Watcher / Fork / Issue の 4 項目 + 最終更新 |

### 3.2. 状態ごとの表示要件

| 状態 | 判定 | 事実確認の根拠 |
|---|---|---|
| 初期状態（未検索） | ⚠️ | 検索フォーム（プレースホルダ）+ 説明文（`home.description`）+ ヒーロー画像 + 日次ダイジェストを表示する。**「キーワードを入力して検索してください。」という明示文言は意図的に撤去済み**（`app/[locale]/page.tsx` のコメント・初見フィードバック⑥に基づく飼い主決定）。与件 §3.1.1 の「未入力時はプレースホルダで入力を促す」は満たすが、§3.2 の「検索を促すことがわかる表示」を **文言で** 明示してはいない |
| 読み込み中 | ✅ | `<Suspense key={suspenseKey} fallback={<LoadingIndicator/>}>`（`app/[locale]/page.tsx`）。条件変更のたびに key が変わるため、ページング・ソート変更でも fallback が再表示される。E2E `e2e/sp-9-loading-empty.spec.ts` |
| 結果 0 件 | ✅ | `repository-list.tsx` が `items.length === 0` で `role="status"` の文言（`home.empty`）+ 専用イラストを表示。E2E `e2e/sp-9-loading-empty.spec.ts` |
| エラー（通信 / API / レート制限を区別 + 再試行手段） | ✅ | `ErrorKind` は **7 種**（`network` / `rateLimitPrimary` / `rateLimitSecondary` / `auth` / `validation` / `notFound` / `upstream`・[`src/domain/errors.ts`](../../src/domain/errors.ts)）。文言は `messages/*.json` の `errors` に 1:1 で用意。`ErrorNotice` が `retryHref`（失敗した URL の開き直し）を提供。レート制限時は復帰時刻 / 再試行秒数 / ログイン導線まで出し分ける。E2E `e2e/sp-9-errors.spec.ts` |
| 該当リポジトリなし（詳細） | ✅ | `page.tsx` が `repository === null` で `notFound()` → [`not-found.tsx`](../../app/%5Blocale%5D/repos/%5Bowner%5D/%5Brepo%5D/not-found.tsx)（HTTP 404 + 専用 UI + 一覧へ戻る導線）。🔴 `<Suspense>` を `notFound()` より後にのみ置き、404 ステータスを返せる構造を保っている。E2E `e2e/sp-6-notfound.spec.ts` |

---

## 4. 非機能要件

### 4.1. 信頼性・エラーハンドリング

| # | 要件（要約） | 判定 | 事実確認の根拠 |
|---|---|---|---|
| N-1 | API 失敗を握りつぶさず伝え、継続利用可能に保つ | ✅ | `runSearch()` は `DomainError` を捕捉して `{status:'error', kind}` に変換し、`ErrorNotice` + 再試行リンクを描画（アプリは落ちない）。想定外の例外は再 throw して隠蔽しない |
| N-2 | レート制限超過時に適切なメッセージ / 認証済みリクエストを利用できる構成 | ✅ | 一次（`x-ratelimit-reset` → 復帰時刻）と二次（`retry-after` → 秒数）を別 kind で判別。サーバー側は GitHub App installation token（[ADR 0003](../adr/0003-github-app-authentication.md)）、利用者側は任意 OAuth ログイン（[ADR 0012](../adr/0012-optional-github-oauth.md)）でレート枠を切り替えられる |
| N-3 | 秘匿情報をクライアントへ露出させない（環境変数 + サーバーサイド） | ✅ | `grep -rn "NEXT_PUBLIC" src app next.config.ts wrangler.jsonc` → **0 件**。`process.env` の参照は `src/infrastructure/**` と `src/composition/**` のみ（`session-cookie` / `oauth` / `installation-token` / `rate-limit` / `site-url`）で、`"use client"` を持つ 8 ファイルには 1 つも無い |

### 4.2. パフォーマンス

| # | 要件（要約） | 判定 | 事実確認の根拠 |
|---|---|---|---|
| N-4 | 入力のたびに無条件で API を呼ばない | ✅ | 検索は **ネイティブ GET フォームの明示的な送信** で発火する（`onChange` ハンドラも fetch も存在しない）。デバウンス以前に、そもそも打鍵で API を呼ぶ経路が無い |
| N-5 | サーバーコンポーネント / キャッシュ機構の活用、クライアントバンドルの抑制 | ✅ | 一覧・詳細とも Server Component。`"use client"` は 8 ファイルのみ（フォーカス制御・言語切替アナウンス・既読バッジ等の必要最小）。キャッシュは `CachingRepositoryQuery`（TTL + single-flight による上流二重呼び出しの抑止）。[ADR 0005](../adr/0005-cache-port-yagni-exception-and-ttl.md) |
| N-6 | 画像（オーナーアイコン）を最適化して配信 | ⚠️ | **`next/image` の最適化は意図的に使わない**（`INF-11`・Cloudflare Images の変換枠が検索結果の大量アバターで膨らむため）。代替として GitHub 側のサイズパラメータ（一覧 `?s=80` / 詳細 `?s=128`）+ `width`/`height` の明示（CLS 対策・`NFR-6`）+ 一覧は `loading="lazy"` を適用。**最適化の実体はあるが手段が `next/image` ではない** 点を注記する |

### 4.3. ユーザビリティ・アクセシビリティ

| # | 要件（要約） | 判定 | 事実確認の根拠 |
|---|---|---|---|
| N-7 | スマートフォン〜デスクトップのレスポンシブ対応 | ✅ | Tailwind のレスポンシブユーティリティ（`sm:grid-cols-4` / `flex-wrap` / `max-w-3xl` 等）。E2E `e2e/sp-10.spec.ts` が複数ビューポートで横スクロール非発生を検証し、`<meta name="viewport">` が `width=device-width` かつ拡大禁止でないことも検証 |
| N-8 | キーボードのみで検索から詳細閲覧まで操作できる | ✅ | E2E `e2e/sp-10.spec.ts` / `e2e/sp-14.spec.ts` が Tab / Enter だけで検索実行・遷移を通す。フォーカスリングは `focus-visible:ring-3` で全インタラクティブ要素に統一 |
| N-9 | フォーム・ボタン・画像に適切なラベル / 代替テキスト | ✅ | 検索入力は `<label class="sr-only">` + `htmlFor`。装飾アイコンは `aria-hidden="true"`。アバターはリポジトリ名が隣接するため `alt=""`（装飾扱い・`NFR-14` で明文化）。axe 検査を E2E（`e2e/a11y.spec.ts` / `e2e/sp-9-a11y.spec.ts`）と Lighthouse ゲート（`tools/run_lighthouse.mjs`）で自動化 |
| N-10 | 検索条件（キーワード・ページ）を URL に反映し再現可能に | ✅ | すべての条件が GET クエリ（`q` / `page` / `sort` / `per_page`）。`buildSearchUrl` / `parseSearchParams` が唯一の正本。詳細ページへも条件を継ぎ足し、戻るときに復元する |

### 4.4. 保守性

| # | 要件（要約） | 判定 | 事実確認の根拠 |
|---|---|---|---|
| N-11 | ディレクトリ構成・命名・責務分割の一貫性（API 呼び出し / 表示ロジック / UI の分離） | ✅ | `src/domain`（モデル・ポート）→ `src/usecases` → `src/infrastructure`（GitHub ACL・プラットフォーム）→ `src/ui` / `app`、配線は `src/composition`。依存規則は `python3 tools/check_architecture_boundaries.py` が機械検証し `npm run check` に組み込み済み（**PASS**） |
| N-12 | API レスポンスの型定義と型安全な取り扱い | ✅ | `src/infrastructure/github/dto.ts` が **zod スキーマ** で上流レスポンスを検証し、`mapper.ts` がドメインモデルへ変換（スキーマ不一致は `upstream` エラーへ）。`tsc --noEmit` **PASS** |
| N-13 | Lint / フォーマッタを導入し機械的に検証できる状態 | ⚠️ | **Lint は充足**（`eslint.config.mjs` + `npm run lint`、`npm run check` の 1 番目で **PASS**）。**フォーマッタは導入済みだが検証が red**: `npm run format:check`（`prettier --check .`）が **110 ファイルで失敗**（内訳: `.claude` 33 / `src` 26 / `tools` 19 / `e2e` 11 / `app` 10 ほか）。実差分も確認済み（例: `src/ui/repository-detail.tsx:55` が `printWidth: 100` 超過）。さらに `tools/run_checks.sh` に Prettier のチェックが **含まれていない** ため、PR ゲートでも検出されない |

---

## 5. テスト要件

| # | 要件（要約） | 判定 | 事実確認の根拠 |
|---|---|---|---|
| TS-1 | テストコードを記述する | ✅ | `npm test`（Vitest）→ **Test Files 67 passed / Tests 593 passed**（実行時間 35.84s・実行結果を確認済み）。E2E は `npm run test:e2e`（Playwright・21 spec ファイル / 89 テスト。件数は `npx playwright test --list` の実測）→ `npm run check` 内で **PASS**（218 秒） |
| TS-2 | 主要フロー（検索→一覧 / 一覧→詳細 / 読み込み中・0 件・エラー）を対象 | ✅ | 検索→一覧: `e2e/sp-1.spec.ts`（「SP-1: 検索して一覧が出る」）/ 一覧→詳細→戻る: `e2e/sp-3.spec.ts`（「SP-3: 詳細まで往復できる」）・`e2e/sp-7.spec.ts`（検索条件を保持した往復）/ 読み込み中・0 件: `e2e/sp-9-loading-empty.spec.ts` / エラー種別 5 ケース: `e2e/sp-9-errors.spec.ts` / 404: `e2e/sp-6-notfound.spec.ts`。ユニットでも `search-repositories.test.ts` `get-repository-detail.test.ts` `repository-list.test.tsx` `error-notice.test.tsx` 等が対応 |
| TS-3 | 外部 API をモック化し、ネットワークに依存せず再現可能 | ✅ | ユニット・結合は **MSW 2**（`http.get('https://api.github.com/search/repositories', …)`）。E2E は Playwright がスタブ API + アプリを自動起動し外部ネットワークに出ない（README も明記）。`npm test` は環境変数ゼロで通る |
| TS-4 | コマンド一つで実行でき、CI で自動実行できる状態 | ⚠️ | **コマンド一つは充足**（`npm test` / `npm run test:e2e` / まとめて `npm run check`）。**ただし現在この規模の CI が稼働していない**: `.github/workflows/` は **存在しない**（GitHub Actions がプラットフォーム側の制限で起動できず 2 本とも撤去・`D-23`）。代替の Workers Builds（`D-31`・`tools/workers_build_deploy.sh`）は **デプロイゲート + デプロイのみでテストを実行しない**。現状は各セッションが `npm run check` を実行し、結果表を PR 本文へ貼ることで機械的証跡としている |

---

## 6. ドキュメント要件

| # | 要件（要約） | 判定 | 事実確認の根拠 |
|---|---|---|---|
| D-1 | README にセットアップ手順（依存インストール・環境変数・起動 / テスト実行コマンド） | ✅ | [`README.md`](../../README.md)「開発（ローカル）」に `npm ci` / `npm run dev` / `npm test` / `npm run test:e2e` / `npm run lint` / `npm run check`。「環境変数」節に 8 変数の用途と **未設定時の挙動** を表で明記（すべて任意で、無設定でも動作する旨も明記） |
| D-2 | README に設計上の判断・工夫した点 | ✅ | 「設計上の判断」節（常設 dev 環境を持たない `D-21` / 与件が対象外とした認証を上乗せした理由 `AR-5`）。各項に却下した代替案と ADR へのリンクを併記 |
| D-3 | README に AI 利用の方法と範囲 | ✅ | 「AI を利用した範囲と方法（`NFR-31`）」節。スプリント自走・TDD 主体・セルフレビュー・PR 自律化・人間が判断する領域（`A-1`〜`A-6`）・定期運用の 6 点 |
| D-4 | 重要な技術的意思決定を `docs/adr/` に ADR として記録 | ✅ | `docs/adr/` に **0001〜0015 の 15 本**。README の索引と PRD §12 の突合を `python3 tools/check_adr_coverage.py` が機械検査し `npm run check` に組み込み済み（**PASS**） |

---

## 7. 与件 §7「受け入れ基準チェックリスト」への回答

| 与件の受け入れ基準（要約） | 判定 | 参照 |
|---|---|---|
| Next.js v16 以降 + App Router | ✅ | T-1 / T-2 |
| キーワード検索で GitHub API の結果が一覧表示される | ✅ | FR-1 / FR-2 / T-3 |
| 一覧項目にオーナーアイコンとリポジトリ名 | ✅ | FR-2 |
| 一覧項目の選択で独立 URL の詳細ページへ遷移（モーダルでない） | ✅ | FR-3 / FR-5 |
| 詳細に 名前・アイコン・言語・Star・Watcher・Fork・Issue 数 | ✅ | FR-4 |
| 詳細からトップページへ戻れる | ✅ | FR-6 |
| ページネーション / 無限スクロールで 2 ページ目以降 | ✅ | FR-7 / S-5 |
| 読み込み中・0 件・エラーの各状態が判別できる | ✅ | §3.2 |
| レスポンシブ対応およびキーボード操作 | ✅ | N-7 / N-8 |
| 主要フローのテストが存在し、実行して成功する | ✅ | TS-1 / TS-2（593 tests passed を実行確認） |
| README にセットアップ手順と設計上の判断 | ✅ | D-1 / D-2 |

**与件 §7 の 11 項目はすべて ✅。**

---

## 8. 検証に使った実コマンドと結果

| コマンド | 結果 |
|---|---|
| `node -p "require('./node_modules/next/package.json').version"` | `16.3.1` |
| `npm test` | Test Files **67 passed** / Tests **593 passed**（35.84s） |
| `npx playwright test`（`npm run check` 内） | **PASS**（218 秒・21 spec ファイル / 89 テスト） |
| `npx eslint`（`npm run check` 内） | **PASS**（8 秒） |
| `npx tsc --noEmit`（同上） | **PASS**（8 秒） |
| `python3 tools/check_architecture_boundaries.py`（同上） | **PASS** |
| `npm run check`（`tools/run_checks.sh`・全 20 チェック） | **全 PASS**（上記に加え Lighthouse a11y ゲート・ADR 記載検査・配色コントラスト検査・CJK Markdown 検査・各 self-test を含む） |
| `npm run format:check` | **FAIL**（110 ファイル。`src` 26 / `app` 10 / `e2e` 11 を含む） |
| `grep -rn "NEXT_PUBLIC" src app next.config.ts wrangler.jsonc` | **0 件**（秘匿情報のクライアント露出なし） |
| `ls .github/workflows` | **存在しない**（`D-23` により撤去済み） |

---

## 9. フォローアップ候補（与件の未充足ではない）

いずれも与件の ❌ ではないが、注記 ⚠️ の解消として Issue 化を検討する。

1. **Prettier の是正と PR ゲートへの接続**: `npx prettier --write .` で 110 ファイルを整形し、`tools/run_checks.sh` に `prettier --check` を 1 チェックとして追加する（`N-13`）
2. **CI でのテスト自動実行の回復**: GitHub Actions の制限解除時に撤去済みワークフローを復帰させる（復帰手順は `cloudflare-infrastructure.md` §8.4）。それまでの間、Workers Builds のビルドコマンド側でテストを走らせられるかを検証する（`TS-4`）
3. **初期状態の文言**: 「検索を促す」意図を文言でも明示するか、現状（プレースホルダ + 説明文 + ビジュアル）で十分とするかを判断し、決定ログへ残す（§3.2）
