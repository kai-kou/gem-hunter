<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: gem-hunter を技術課題の提出物として網羅的レビューし観点別スコアと合否を判定する

- 議題ID: `tech-review-20260824`
- 論点: 与件 docs/02_requirements/minimum-requirements.md を採点基準とし、O-1〜O-8 の観点で 0〜5 のスコアと合否を判定する。残存 Issue の存在自体は減点しない。
- 参加者: `cto`, `frontend`, `qa`, `security`, `code_quality`, `requirements_auditor`
- 投稿数: 14
- 更新: 2026-08-24T12:15:24+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

## ラウンド 1

### `frontend` — 主張
<sub>2026-08-24T12:04:47+09:00</sub>

# frontend レンズ Round 1: O-1（与件充足）/ O-5（非機能）

## スコア

| 観点 | スコア | rationale（1行） |
|---|---|---|
| O-1 与件充足 | **5** | FR-1〜FR-7・§3.1画面構成・§3.2状態表示（idle/loading/0件/エラー3区別/404）を全項目実コードで裏取り、未充足なし。エラー種別は要件を上回る7種に細分化 |
| O-5 非機能 | **4** | a11y・エラーハンドリング・URL 状態反映・キャッシュ設計は水準が高いが、画像最適化は `next/image` 不使用（代替措置ありだが要件文言との厳密一致はグレー）、レスポンシブの実機検証は未実施 |

## よい点

1. **状態設計が極めて緻密**: `app/[locale]/page.tsx` は `<Suspense key={suspenseKey}>` で検索条件が変わるたびに fallback を再表示させ、`aria-live="polite"` の `#search-status` を「初期 DOM に常設・中身だけ書き換える」設計にしてスクリーンリーダーへの通知漏れを防いでいる（41-52, 481-534 行）。0件表示は `role="status"`（`src/ui/repository-list.tsx` 61-79 行）、エラーは `role="alert"`（`src/ui/error-notice.tsx` 84-91 行）と使い分けている。
2. **Server Component 中心**: `'use client'` は 8 ファイルのみ（`focus-on-navigate.tsx` / `site-header.tsx` / `set-document-title.tsx` / `locale-switch-announcer.tsx` / `readme-section.tsx` / `seen-digest/*` 2 本）で、いずれも document.title 操作・localStorage・フォーカス制御など Client 化が必然なものに限定。乱用は見つからなかった。
3. **URL への検索条件反映が徹底**: `src/ui/url/build-search-url.ts` / `search-params.ts` 経由で keyword/page/sort/perPage を URL に載せ、`buildSearchUrl` で一覧⇄詳細の往復・言語切替・再試行後も条件を保持する導線を作っている（`app/[locale]/repos/[owner]/[repo]/page.tsx` 60-119 行）。§4.3 の「URL反映・リロード/共有時の再現」を満たす。
4. **エラー種別の細分化**: `ErrorKind` = network / rateLimitPrimary / rateLimitSecondary / auth / upstream / validation / notFound の7種（`src/domain/errors.ts` 相当・`error-notice.tsx` 25-35 行の `ERROR_ILLUSTRATION` で網羅性を型で保証）。§3.2 が要求する「通信失敗・APIエラー・レート制限超過の区別」を上回る粒度。
5. **キャッシュ機構の設計判断が実機検証込みで文書化**（ADR 0005）: `AsyncLocalStorage` 経由の SSR ヘッダ付与を実際に `wrangler dev --local` で試して不成立と確認した記録があり（37行）、代替として Route Handler 方式・`CachingRepositoryQuery` デコレータ + single-flight coalescing を採用。ドキュメントの主張を鵜呑みにせず実装（`src/composition/container.ts` 22-24行のシングルトン `sharedCache`）でも整合を確認した。
6. **画像の法務判断が誠実**: `next/image` 不使用（INF-11）は ADR 0013（GitHub ToS「再配信禁止」への配慮）に基づく意図的選択で、代替に GitHub 側 `?s=N` パラメータ + `width`/`height` 明示（CLS対策）+ 一覧は `loading="lazy"` を適用。`minimum-requirements-checklist.md` で「⚠️」を付けて自己申告している点は誠実。

## 課題点（重要度順）

1. **【medium】画像最適化の要件充足はグレー**: 与件 §4.2「画像（オーナーアイコン）は最適化して配信する」に対し `next/image` は意図的に不使用（`src/ui/repository-list.tsx` 116-128行 / `repository-detail.tsx` 69-77行 / `site-header.tsx` 62-70行 いずれも生 `<img>`）。代替措置（GitHub側リサイズ・明示寸法・lazy）で実質的な配慮はあるが、「最適化して配信」を Next.js の機構で行うことを期待する審査基準だと部分充足と判定されうる。ADR 0013 の法務的正当化（再配信禁止 T-2）自体は妥当な判断で、独自の合理的トレードオフとして評価すべきだが、要件文言との厳密一致では引っかかる。
2. **【low】独自 `InMemoryCache` は Cloudflare Workers の isolate をまたいで永続しない**（ADR 0005 §5「受け入れる代償」に明記）。コールドスタートのたびに空になるため、本番運用下でのキャッシュヒット率は実測されていない（`R-5` 逆算は行われているが実運用トラフィックでの検証ではない）。設計上の欠陥ではなく承知の上のトレードオフで、再決定条件も明記されているため大きな減点対象ではない。
3. **【low】レスポンシブの実機検証は自分では未実施**: コード上は `flex-wrap` を多用しシンプルなレイアウトで基本的な折り返しは機能する設計だが、`sm:`/`md:` 等ブレークポイント指定は 12 箇所のみ（`grep` 実測）で、実ビューポート（スマートフォン〜デスクトップ）でのスクリーンショット確認はしていない。視覚的崩れの有無はコードレビューだけでは断定できない（QA/Lighthouse 領域と重複するため O-5 では減点幅を小さくした）。
4. **【info・指摘ではない】デバウンス未実装**だが `SearchForm` は `method="get"` のネイティブフォーム送信のみ（`src/ui/search-form.tsx`）でクライアント JS を持たず、入力のたびに API を呼ぶ経路が存在しない。要件は「デバウンス、明示的な検索実行等」のどちらでも可としており、これは充足の一形態。

## §7 受け入れ基準チェックリスト該当項目の実コード裏取り（frontend 担当範囲: 項目 1〜9）

| # | 項目 | 判定 | 根拠 |
|---|---|---|---|
| 1 | Next.js v16以降 + App Router | 充足 | `package.json` `"next": "16.3.1"`。`find` で `pages/` ディレクトリ不在確認。全ルートは `app/[locale]/*` |
| 2 | キーワード検索で GitHub API 検索結果が一覧表示 | 充足 | `app/api/search/route.ts` / `src/infrastructure/github/github-repository-query.ts`（`https://api.github.com/search/repositories` を実際に叩く実装をテストで確認）、`app/[locale]/page.tsx` の `runSearch()` → `RepositoryList` |
| 3 | 一覧項目にオーナーアイコンとリポジトリ名 | 充足 | `src/ui/repository-list.tsx` 116-155行（`item.owner.avatarUrl` の `<img>` + `item.fullName` の `<Link>`） |
| 4 | 一覧項目選択で独立URL詳細ページへ遷移（モーダルでない） | 充足 | `src/ui/repository-list.tsx` 138行 `<Link href="/${locale}/repos/${owner}/${repo}...">`。`app/[locale]/repos/[owner]/[repo]/page.tsx` が独立ページとして存在し固有URLを持つ |
| 5 | 詳細ページにリポジトリ名・アイコン・言語・Star・Watcher・Fork・Issue数 | 充足 | `src/ui/repository-detail.tsx` 51-60行（`numericStats` 配列に stars/watchers/forks/openIssues の4項目 + fullName・primaryLanguage・avatarUrl） |
| 6 | 詳細ページからトップページへ戻れる | 充足 | `src/ui/repository-detail.tsx` 65行 `<BackLink>`。`app/[locale]/repos/[owner]/[repo]/page.tsx` 95-99行で `backHref` を検索条件付きで生成 |
| 7 | ページネーションまたは無限スクロールで2ページ目以降 | 充足（ページネーション方式） | `src/ui/pagination.tsx`（`<nav aria-label>` + GET リンク方式、`maxPageFor` で GitHub API の1,000件上限を尊重）。方式選択は ADR 0008 で正当化 |
| 8 | 読み込み中・0件・エラーの各状態が画面上で判別できる | 充足 | 読み込み中: `LoadingIndicator`（Suspense fallback）。0件: `repository-list.tsx` 61-79行 `role="status"`。エラー: `error-notice.tsx` `role="alert"` + `ErrorKind` 7種別 |
| 9 | レスポンシブ対応およびキーボード操作が可能 | 部分充足（コード上は妥当だが実機未検証） | GET フォーム・`<Link>`・`<nav>` は全てネイティブ要素でキーボード到達可能。`focus-visible:ring-3` を一貫使用（`repository-list.tsx` 141行 等）。スキップリンクあり（`site-header.tsx` 42-47行）。レスポンシブは `flex-wrap` 中心の設計で機能する見込みだが、実ビューポートでの目視確認は未実施 |

（項目10「テストコード存在し実行して成功する」・11「READMEの記載」は QA / requirements_auditor の担当観点のため本レンズでは判定しない）

## 争点(1)についての自分の立場

**与件11項目の受け入れ基準のうち、frontend 担当範囲（1〜9）はすべて実コードで充足を確認できた。** 唯一グレーな点は項目9の「レスポンシブ」を実機で確認していないことと、§4.2「画像の最適化」を `next/image` を使わない代替策で満たしていると解釈できるかどうかの一点。後者は ADR 0013 で法務的理由により意図的に選択されており、単なる手抜きではなく検討された設計判断であるため、O-1（機能要件充足）ではなく O-5（非機能の実装品質）側の減点として扱うのが妥当と判断した。

## 最終合否についての自分の立場

**条件付き合格（frontend 観点からは合格に近い）**。FR-1〜FR-7・状態表示要件は完全実装、a11y・URL状態管理は商用水準に近い作り込み。減点材料は画像最適化の解釈グレーとレスポンシブ実機未検証のみで、いずれも致命的欠陥ではない。他レンズ（セキュリティ・アーキテクチャ）の指摘次第で全体判定は変わりうるが、フロントエンド実装単体としては与件を明確に上回っている。

### `requirements_auditor` — 主張
<sub>2026-08-24T12:04:56+09:00</sub>

## requirements_auditor round1 判定

方法: 全判定は自分で開いた実ファイル・実行したコマンド結果のみを根拠とする。未実行のコマンド結果は書かない。

### ① 与件 §7 受け入れ基準 11 項目

| # | 項目 | 判定 | 根拠 |
|---|---|---|---|
| 1 | Next.js v16 以降 + App Router で構築 | 充足 | `package.json` L: `"next": "16.3.1"`。`find . -iname pages -maxdepth 2` は該当なし（Pages Router 不在）。`app/[locale]/` 配下に `page.tsx` 群あり |
| 2 | キーワード検索で GitHub API のリポジトリ検索結果が一覧表示される | 充足 | `src/infrastructure/github/github-repository-query.ts:43` `new URL('/search/repositories', apiOrigin())`。`app/[locale]/page.tsx` の `runSearch()` → `searchRepositoriesUseCase` → `RepositoryList` 描画。e2e `sp-1.spec.ts:10` `'SP-1: 検索して一覧が出る'` |
| 3 | 一覧項目にオーナーアイコンとリポジトリ名が表示される | 充足 | `src/ui/repository-list.tsx:116-146`（`<img src={owner.avatarUrl}...>` と `<Link>{item.fullName}</Link>`） |
| 4 | 一覧項目選択で独立 URL の詳細ページへ遷移（モーダルでない） | 充足 | `src/ui/repository-list.tsx:138-146` の `Link href="/${locale}/repos/${owner}/${repo}..."`。`app/[locale]/repos/[owner]/[repo]/page.tsx` は独立した `page.tsx`（モーダル実装なし） |
| 5 | 詳細ページに名前・アイコン・言語・Star・Watcher・Fork・Issue 数 | 充足 | `src/ui/repository-detail.tsx:71-137`（`fullName`・avatar・`primaryLanguage`・`numericStats`=[stars, watchers, forks, openIssues]） |
| 6 | 詳細ページからトップページへ戻れる | 充足 | `src/ui/repository-detail.tsx:66` `<BackLink locale={locale} labels={labels} href={backHref} />`。既定 `href` は `/${locale}`（`src/ui/back-link.tsx` 未読だが detail page の JSDoc L38 に明記、かつ `back-link.test.tsx` 存在） |
| 7 | ページネーションまたは無限スクロールで 2 ページ目以降を閲覧 | 充足 | `src/ui/pagination.tsx` 全体（prev/next リンク・`aria-current`・`maxPageFor` 上限考慮）。無限スクロールではなくページネーション方式（与件は「または」なので可） |
| 8 | 読み込み中・0 件・エラーの各状態が画面上で判別できる | 充足 | 読み込み中: `src/ui/loading-indicator.tsx`（`<Suspense fallback>`、`app/[locale]/page.tsx:514`）。0 件: `repository-list.tsx:55-80`（`role="status"` + 空状態イラスト）。エラー: `src/ui/error-notice.tsx`（`role="alert"`、`ErrorKind` 7 種を種別ごとに `ERROR_ILLUSTRATION` で出し分け）。e2e `sp-9-loading-empty.spec.ts` / `sp-9-errors.spec.ts` で実際に検証 |
| 9 | レスポンシブ対応およびキーボード操作が可能 | 充足 | レスポンシブ: `repository-detail.tsx:116` `grid-cols-2 sm:grid-cols-4` 等 Tailwind ブレークポイント使用（他コンポーネントにも散在）。キーボード: `search-form.tsx` は `<form method="get">`（JS 不要、Enter 送信可）、`repository-list.tsx:143` `focus-visible:ring-3` でフォーカス可視化、`pagination.tsx` もネイティブ `<Link>`（`<a>`）でキーボード到達可能 |
| 10 | 主要フローのテストコードが存在し、実行して成功する | 充足 | 存在: e2e `sp-1.spec.ts`（検索→一覧）・`sp-7.spec.ts`（詳細遷移）・`sp-9-loading-empty.spec.ts`（読込中/0件）・`sp-9-errors.spec.ts`（エラー種別）・`sp-6-notfound.spec.ts`（詳細 404）。実行: `npx vitest run src/ui/repository-list.test.tsx src/ui/search-form.test.tsx src/ui/pagination.test.tsx` を実際に実行し `Test Files 3 passed (3) / Tests 42 passed (42)`（実行結果、捏造ではない）。e2e (`npx playwright test`) はタイムアウト制約により本ラウンドでは自分では実行していない（QA 担当が §5 全体で検証予定と認識） |
| 11 | README にセットアップ手順と設計上の判断が記載されている | 充足 | `README.md:28-99`（開発コマンド・環境変数表・技術スタック）、`README.md:111-189`（設計上の判断、ADR リンク付き） |

**11 項目中 11 項目充足**（未充足 0・部分充足 0）。

### ② §2 技術要件

| 項目 | 判定 | 根拠 |
|---|---|---|
| Next.js v16 以降（必須） | 充足 | `package.json`: `"next": "16.3.1"` |
| App Router のみ・Pages Router 不使用（必須） | 充足 | `find /home/user/gem-hunter -maxdepth 2 -iname pages -not -path "*/node_modules/*"` → 該当なし。`app/` 配下のみ |
| データソース `GET /search/repositories`（必須） | 充足 | `src/infrastructure/github/github-repository-query.ts:43` |
| UI コンポーネントライブラリ（任意） | 該当（任意要件） | README L93: Tailwind CSS v4 + shadcn/ui 採用（`ADR 0001`） |
| TypeScript（推奨） | 充足 | 全ソース `.ts`/`.tsx`。`package.json` に `"typescript": "^5"`、`tsconfig.json` 存在 |

**技術要件: 全項目充足**。

### ③ §6 ドキュメント要件

| 項目 | 判定 | 根拠 |
|---|---|---|
| セットアップ手順（依存インストール・環境変数・起動/テスト実行コマンド） | 充足 | `README.md:28-43`（`npm ci` / `npm run dev` / `npm test` / `npm run test:e2e` 等のコマンド一覧）、`README.md:68-86`（環境変数表・全 8 変数の用途と未設定時挙動） |
| 設計上の判断・工夫した点・こだわったポイント | 充足 | `README.md:111-189`（8 項目の設計判断。例: Hidden Gem 定義・DB を持たない設計・エラー7種判別・i18n 自前実装 など、各 ADR へのリンク付き） |
| AI 利用の方法と範囲（利用した場合） | 充足 | `README.md:191-200`（「AI を利用した範囲と方法（NFR-31）」節。スプリント運用・TDD・セルフレビュー・PR 自律化・人間判断領域を明記） |
| 重要な技術的意思決定を `docs/adr/` に ADR として記録 | 充足 | `ls docs/adr/` で 0001〜0015 の 15 件を実際に確認。README §202-204 で ADR 索引と `prd.md §12` への参照あり |

**ドキュメント要件: 全項目充足**。

### ④ 与件に書かれていないのに実装された機能一覧と、与件侵食の判定

与件 §1.2 の対象外リスト: 「ユーザー認証、お気に入り・リスト管理、独自スコアリング、通知、課金」。

| 追加機能 | 該当箇所 | 与件対象外リストとの関係 | 判定 |
|---|---|---|---|
| GitHub OAuth ログイン | `app/api/auth/{login,callback,logout}/route.ts`、`src/composition/auth.ts` | §1.2 対象外「ユーザー認証」に**文言上は抵触**。ただし実装は「未ログインでも全機能が使える」任意機能で、目的はレート枠の切替（`README.md:84` 「公開中の本番環境には OAuth の 4 変数を供給していないため、現在ログイン導線は表示されない」）。認証がないと使えない機能は存在しない | **与件必達項目は侵食していない**が、対象外リストの文言には反する追加スコープ |
| Gem Index / Hidden Gem スコア（`gem-badge` / `/gems` 一覧 / daily-digest） | `docs/adr/0009-hidden-gem-score-definition.md`、`src/ui/gem-badge.tsx`、`app/[locale]/gems/page.tsx` | §1.2 対象外「独自スコアリング」に**文言上は抵触**（ADR 0009 は「合成スコアは作らない」としつつ `Gem Index`＝被依存数パーセンタイル−star パーセンタイルという独自算出値を新設しており、実質は独自スコアリングの一種） | 検索結果の並び順（`sort`）には使っておらず（ADR 0009: 「`sort=gem-index` は復活させていない」）、必須の FR-1〜FR-7・§3.1・§3.2 の挙動を変更・妨害してはいない。**与件必達項目は侵食していない**が、スコープ外機能として作り込みの規模が大きい |
| i18n（`/{locale}/` ルーティング・`next-intl` 不使用の自前実装） | `app/[locale]/`、`docs/adr/0011-i18n-routing-and-default-locale.md` | 与件に記載なし（禁止もされていない） | 与件必達項目を侵食せず、むしろ FR 系の実装はロケール非依存に成立している |
| Cloudflare Workers 本番運用・OG 画像生成・日次ダイジェスト | `wrangler.jsonc`、`app/[locale]/opengraph-image.tsx`、`daily-digest.tsx` | 与件に記載なし | 必達項目を侵食していない（付加機能） |

**総括**: 対象外リストの文言（「ユーザー認証」「独自スコアリング」）に字面上は抵触する 2 機能があるが、いずれも① MVP の必須動線（FR-1〜FR-7・§3.1・§3.2）を代替・変更しておらず、②未ログイン・バッジ非表示でも全機能が成立する任意拡張であるため、**与件必達項目そのものへの侵食は確認できなかった**。ただし「対象外」と明記された領域に本格的な設計判断（ADR・専用画面）まで投じている点は、スコープ管理上の争点として CTO レンズ・O-2/O-7 で扱うべき事実として提示する。

### ⑤ O-1・O-7 スコアと rationale

- **O-1（与件充足）: 5/5**。§7 の 11 項目すべて実コードで充足を確認。§2 技術要件も全項目充足。§3.1/§3.2 の画面・状態要件も実コンポーネントで裏取り済み。減点要素（対象外領域への拡張）は §1.2 の「対象外」記載であって「禁止」ではなく、かつ必須動線を破壊していないため O-1 の直接減点対象にはしない（O-2 の設計判断の妥当性論点として切り出す）。
- **O-7（ドキュメント・README 要件面）: 5/5**。README にセットアップ手順・環境変数・設計判断・AI 利用範囲が具体的根拠（ファイルパス・ADR 番号）付きで記載されており、`docs/adr/` に 15 件の ADR が実在する。要件が求める記載項目はすべて充足している（説明可能性の質は cto レンズの O-7 判定と合わせて最終決定してよい）。

### ⑥ 最終合否についての自分の立場

**合格**。与件 §7 の受け入れ基準 11 項目・§2 技術要件・§6 ドキュメント要件のいずれも、自分で開いた実装ファイルおよび実行した `vitest run` の結果で充足を確認した。未充足・部分充足の項目は 1 つも見つからなかった。唯一の留保点は、§1.2 で明示的に「対象外」とされた「ユーザー認証」「独自スコアリング」に該当しうる機能（OAuth ログイン・Gem Index）が実装されていることで、これは要件監査役の観点では「必達項目の未充足」ではなく「スコープ管理・過剰実装」の論点として他レンズ（cto の O-2 等）に委ねる。

### `security` — 主張
<sub>2026-08-24T12:05:17+09:00</sub>

## O-6 セキュリティ: スコア 4 / 5

**rationale**: 実コード（OAuth・セッション・README サニタイズ・レート制限・入力検証）を一通り読み、実際に `npm audit` を実行した結果、**実害のある critical/high 欠陥は発見できなかった**。むしろ PR #141 のレビュー指摘（オープンリダイレクト・prefetch による誤ログアウト・flaky Secure Cookie）が実装コメントに残っており、過去に見つかった脆弱性クラスがきちんと修正・文書化されている形跡が複数見える。5 にしない理由は、① セキュリティヘッダ（CSP・X-Frame-Options・HSTS 等）が一切設定されておらず defense-in-depth が薄い点、② レート制限が複数条件でフェイルオープンする設計（意図的だが本番運用の落とし穴になりうる）を medium として減点したため。

**O-5（信頼性面）所見**: レート制限のフェイルオープン条件（IP 不明 / binding 未提供 / salt 未設定）は `src/composition/rate-limit.ts:30-79` に明記されており、"サービスを止めない" ための意図的判断として文書化されている。ただし `RATE_LIMIT_SALT` が本番で未設定になった場合、429 も出さず黙って通す（`rate-limit.ts:59-64`）ため、GitHub API 上流のレート制限保護という NFR-7 の目的が **設定ミス 1 つで無効化される**。警告ログ (`console.warn`) はあるが、アラート・監視に接続されている証跡はコード上確認できない。

---

### よい点

1. **セッション実装が堅牢**: `SESSION_ENCRYPTION_KEY` による JWE 暗号化（`EncryptJWT`, `alg: dir`, `enc: A256GCM`）でアクセストークンを暗号化して Cookie に保存している（`src/infrastructure/platform/session-cookie.ts:60-71`）。復号失敗時は理由を問わず必ず `null`（未ログイン扱い）に倒しており（`decodeSessionCookie:77-92`）、フェイルクローズ側に倒れている。
2. **オープンリダイレクト対策が実装済み**: `callback` / `logout` の両ルートで `Host` ヘッダをそのまま信用せず、`GITHUB_OAUTH_CALLBACK_URL` から導出した許可ホストと突き合わせてから使う（`src/composition/auth.ts:55-62`、`app/api/auth/callback/route.ts:37-41`、`app/api/auth/logout/route.ts:24-27`）。PR #141 のレビュー指摘に対する修正が反映されている。
3. **CSRF state のタイミングセーフ比較**: `app/api/auth/callback/route.ts:47-56` で `timingSafeEqualString` を自前実装し、state 比較を単純な `===` にしていない。
4. **README HTML サニタイズが許可リスト方式で堅実**: `src/ui/readme-html.ts` は `sanitize-html` を許可タグ・許可属性の allowlist で使い、`allowedSchemes: ['http', 'https']`（`javascript:` / `data:` を許可しない）、`parseStyleAttributes: false`（style 属性の CSS 解析経路を丸ごと切断）、`a`/`img` の href・src を `resolveUrl()` で個別に安全なスキームへ検証してから許可している（`readme-html.ts:124-140, 168-207`）。href が無い `a` タグ・スキームが安全でない `a`/`img` は素のテキストへ落とすか丸ごと破棄する設計で、XSS ベクタとして機能する箇所は見つからなかった。
5. **GitHub トークンのクライアント露出なし**: `NEXT_PUBLIC_` プレフィックスの誤用を `grep -rn "NEXT_PUBLIC_" src app` で確認したが該当ゼロ。installation token・OAuth client secret・セッション暗号鍵は `src/infrastructure/github/*.ts` と `session-cookie.ts` の各 1 ファイルに閉じ込められ（`ARCH-5`/`NFR-22` の宣言どおり）、API エラーレスポンスも `error.message`（内部詳細）を外に出さず `ErrorKind` だけを返す設計（`app/api/search/route.ts:96-98`）。
6. **レート制限キーが HMAC 化・偽装耐性のあるヘッダを優先**: `cf-connecting-ip`（Cloudflare が付与し、Worker 実行環境ではクライアントから偽装不能）を最優先し、`x-forwarded-for` は補助のみに位置づけている（`src/infrastructure/platform/rate-limit-key.ts:21-32`）。生 IP は必ず HMAC-SHA256（salt 付き）でハッシュ化してからキーに使う。
7. **owner/repo の入力検証と URL エンコード**: `src/domain/model/repository-full-name.ts` が GitHub の命名規則に準拠した正規表現でホワイトリスト検証し、`github-repository-query.ts:67,92` で `encodeURIComponent` を通してから固定オリジン（`https://api.github.com`）配下のパスに埋め込んでいる。SSRF・パストラバーサルの成立を確認できなかった。
8. **検索クエリインジェクション対策**: `src/domain/model/search-keyword.ts` が GitHub 検索構文の修飾子（`名前:値`）と大文字ブール演算子（`NOT`/`OR`/`AND`）を正規表現で拒否し、加えて `is:public` 修飾子をクエリ文字列の**先頭**に置くことで、キーワード末尾のトークンによる演算子ハイジャック（多層防御 2 層目）まで想定している（`github-repository-query.ts:44-50`）。
9. **ログアウトの GET/POST 分離**: `next/link` の自動プリフェッチにより GET ログアウトが誤爆する実機バグを発見し、POST 限定 + `sameSite: 'lax'` の CSRF 防御に切り替えている（`app/api/auth/logout/route.ts` 冒頭コメント）。実際に Playwright トレースで確認した旨が明記されている。
10. **秘匿情報の環境変数上書き先をループバックに限定**: `src/infrastructure/github/loopback-origin.ts` は `GITHUB_API_ORIGIN` / `GITHUB_OAUTH_ORIGIN` の上書き先を `127.0.0.1` / `localhost` / `[::1]` のみに制限しており、誤設定や環境変数汚染で認証情報の送信先が任意ホストへ切り替わることを防いでいる。

---

### 発見した欠陥

| 深刻度 | 内容 | 該当箇所 |
|---|---|---|
| **medium** | セキュリティヘッダ（`Content-Security-Policy` / `X-Frame-Options` / `X-Content-Type-Options` / `Referrer-Policy` / HSTS）が一切設定されていない。`next.config.ts` に `headers()` の定義がなく、`_headers` ファイルも存在しない。README サニタイズは堅牢だが、CSP という多層防御の 1 層が丸ごと欠けている。加えて `X-Frame-Options`/`frame-ancestors` が無いため、ログイン導線（`/api/auth/login`）を含むページが理論上 iframe に埋め込み可能（clickjacking の土台。実害は GitHub 側の認可画面確認が挟まるため限定的だが、UI redressing 自体は成立しうる）。 | `next.config.ts`（`headers()` 未定義）、`_headers` ファイル不在 |
| **medium** | `RATE_LIMIT_SALT` 未設定時、検索・Gem 一覧の自リクエスト間引きが **429 を一切返さず黙って無効化**される（フェイルオープン）。設定ミス・シークレットのロールアウト漏れが起きた場合、NFR-7（上流 GitHub API 枠の保護）が気づかれないまま失効するリスクがある。`console.warn` は出るが監視・アラート連携の証跡はコード上確認できなかった。 | `src/composition/rate-limit.ts:59-64` |
| **low** | 専用 CSRF トークンが未導入で、CSRF 対策を `sameSite: 'lax'` Cookie 属性のみに依存している。ドキュメント（`app/api/auth/logout/route.ts` コメント）自身が「CSRF トークン導入は Issue #144 に残る」と認めており、既知の残課題として認識済み。`sameSite: 'lax'` は GET のトップレベルナビゲーションでは Cookie を送るため、理論上は影響範囲が限定的（POST 専用にしたログアウト等では実害なし）だが、将来 GET で状態変更するエンドポイントが増えると危険になりうる設計上の負債。 | `app/api/auth/logout/route.ts` コメント、Issue #144（存在は自己申告のみで本セッションでは Issue 内容未確認） |

critical / high は発見できなかった。

---

### 検証したが問題なかった項目（安全側の証跡）

- **秘匿情報のリポジトリ混入**: `git log --all -p` で `BEGIN * PRIVATE KEY` を全履歴走査したが、ヒットしたのはいずれもドキュメント内の「PKCS#1 形式の説明文」であり実鍵ではない。作業ツリーの `gh[pousr]_` / `github_pat_` 等のパターン走査でヒットしたのも全てテストの固定ダミー値（`gho_token` 等）とプレースホルダ（`.env.example`・`docs/rules/env-vars.md` の `ghp_...`）のみ。`.env.example` は全変数が空欄。`.gitignore` は `.env` / `.env*.local` を正しく除外し、`.gitguardian.yaml` の除外設定も対象を 2 ファイルに限定（`playwright.config.ts` の E2E スタブ用ダミー鍵と `session-cookie.test.ts` のテスト用鍵）しており、除外理由がコメントで明記されている。
- **`npm audit` 実行結果**: `npm audit`（本番・全体とも）を実際に実行し、**0 vulnerabilities**。
- **NEXT_PUBLIC_ の誤用**: `grep -rn "NEXT_PUBLIC_" src app` で該当ゼロ。GitHub トークン類のクライアントバンドル露出は確認できなかった。
- **OAuth redirect_uri / SSRF**: `buildAuthorizeUrl` / `exchangeAuthorizationCode` の `redirect_uri` は環境変数 `GITHUB_OAUTH_CALLBACK_URL`（固定値）のみを使い、リクエストパラメータ由来の値を使わない（`src/infrastructure/github/oauth.ts:64-75, 86-131`）。API 到達先オリジンも `resolveLoopbackOverridableOrigin` によりループバックのみへの上書きに制限。owner/repo もホワイトリスト検証 + URL エンコード済み。SSRF・オープンリダイレクトの実害経路は見つからなかった。
- **CI/CD の secrets 露出経路**: `.github/workflows/*.yml` に `pull_request_target` トリガーは無く、参照している secrets も `GITHUB_TOKEN` のみ。フォーク PR からのシークレット窃取経路は確認できなかった。
- **dangerouslySetInnerHTML の使用箇所**: リポジトリ全体で `src/ui/readme-section.tsx` の 1 箇所のみ。サニタイズ済み文字列のみを渡している。

---

### 最終合否についての自分の立場

**O-6 単体では条件付き合格**。critical/high のセキュリティ欠陥は発見できず、OAuth・セッション・XSS・SSRF・インジェクションという主要な攻撃面には実装レベルで具体的な対策と PR レビュー履歴に基づく反証コメントが残っている。ただし CSP を含むセキュリティヘッダの完全な欠如は、コーディング課題としての完成度を「模範的（5）」まで押し上げるには足りない一段の緩さであり、レート制限のフェイルオープン設計も本番運用リスクとして残る。総合の合否判定（全観点横断）は synthesizer の統合に委ねるが、O-6 のみを理由に不合格とすべき材料はない。

### `code_quality` — 主張
<sub>2026-08-24T12:05:32+09:00</sub>

## O-3 コード品質・保守性 — スコア: 4 / rationale

**根拠**: `any` 0 件・非 null アサーション `!` 0 件・`tsc --noEmit` 0 エラー・`eslint --max-warnings 3` 0 エラー（警告 3 件は許容枠ちょうど）。層分離は徹底され domain → infrastructure の逆依存は grep で確認できず、値オブジェクト（ブランド型 + スマートコンストラクタ）が全域で一貫運用されている。5 に届かない理由は「動くコード」としては模範的でも、「初見の人間が読める形」としてはコメント密度と内部ジャーゴンの漏出（`SP-14` `D-36` `whiteboard round3` 等、リポジトリ外からは参照不能な記法がコード本文に直書きされている）がハンドオフ負荷を上げているため。29 ファイル + 一部を実読、`tsc`/`eslint` 実行済み。

---

### よい点

1. **型安全性が実測で徹底している**（後述の grep 参照）。`any` ゼロ・非 null アサーションゼロは同規模の実サービスコードでもほぼ見ない水準。
2. **値オブジェクトパターンの一貫適用**: `PageNumber`（`src/domain/model/page-number.ts:19`）・`PerPage`・`SearchKeyword`（`src/domain/model/search-keyword.ts:29`）・`Locale`・`SortOrder`・`DateSeed`・`RepositoryFullName`・`CacheKey`・`GemIndex` すべてが同じ「ブランド型 + `xxx()`（throw する厳格版）+ `tryXxx()`（既定値へ倒す寛容版）」の対を持つ。命名規約が完全に統一されており、境界（URL パース）と内部（ドメイン検証）の責務分離が明確。
3. **エラー処理の一貫性**: `DomainError` 階層（`src/domain/errors.ts`）の `kind: ErrorKind` が usecases → route handler（`app/api/search/route.ts:86`）→ ページ（`app/[locale]/page.tsx:93-106`）まで途切れず伝播し、`error.message`（開発者向け）を画面へ絶対に出さないという規律がコード上でも徹底されている（握りつぶし・`console.error` での揉み消しは 1 箇所も見なかった）。
4. **抽象化の自制（YAGNI 判断が実装で裏取りできる）**: `src/composition/container.ts:168-177` の `lookupGemIndexes` は「ドメイン判断が 1 つも無いので usecase 層を新設しない」と明示し、実際にポートを素通しするだけの実装になっている。争点 (3) への反対材料として重要（後述）。
5. **防御的プログラミングの質**: `mapper.ts` の `lastPushedAtOf`（不正日付を握って epoch へ丸める）、`cache-key.ts`・`static-gem-digest.ts`（フィールド単位フォールバック）、`readme-html.ts` のサロゲートペア分割回避（`sliceWithoutSplittingSurrogatePair`）など、実運用で踏みうる境界値への配慮が具体的コードとして存在する（口だけの品質主張ではない）。

### 課題点（重要度順）

1. **【中】コメント密度が異常に高く、可読性を逆に損なう箇所がある**。`grep -c '🔴\|🔵\|🟡'` で `search-gems.ts`（298 行）が 11 件、`app/[locale]/page.tsx`（549 行）が 22 件。1 ファイルの過半がコメントという箇所も珍しくない。個々のコメントの質自体は高い（「なぜ」を書けている）が、**社内限定の識別子**（`SP-14` `D-36` `D-37` `F-01` `Issue #453` `whiteboard round3 裁定` 等）がコード本文に直書きされ、それらのドキュメントを読まない第三者には文脈不明のノイズになる。技術課題の提出物としては「引き継げるコード」の観点でやや過剰。
2. **【中】ファイル・関数の肥大化**: `app/[locale]/page.tsx` 549 行・`src/ui/gem-list.tsx` 325 行・`src/usecases/search-gems.ts` 298 行。`page.tsx` は 1 ファイルに `SearchStatusText` / `SearchBody`（Gem バッジ取得・URL 組み立て・ページネーション・a11y 制御まで内包）/ `LocaleHome` の 3 コンポーネントと複数の横断的関心事が同居しており、単一責務の観点では分割余地がある（ドキュメント化はされているが複雑度自体は下がらない）。
3. **【低〜中】意図的に残された重複（3 実装）**: `owner/repo` 形式判定が `src/usecases/search-gems.ts:124`（`INCLUDE_FULL_NAME_PATTERN`）・`src/infrastructure/platform/static-gem-index.ts:95`（`isSafeRepositoryFullName`）・`src/domain/model/repository-full-name.ts` の 3 箇所に並存する。コード自身が「前提が違うため共有モジュール化はしない（別 Issue）」と JSDoc で認めている。判断の妥当性は認めるが、実装としては重複コードであり、Issue へ先送りにした状態で提出されている点は事実として指摘する。
4. **【低】検証方式の不統一**: GitHub API の DTO は `zod`（`src/infrastructure/github/dto.ts`）で検証する一方、静的 JSON（`static-gem-digest.ts`）は手書きの `typeof` ガードで検証している。信頼度が異なる入力源なので使い分け自体は合理的説明が可能だが、「1 つの検証基盤に統一されていない」という事実は残る。
5. **【低】eslint 警告が上限ぎりぎり**: `--max-warnings 3` に対し実測 3 件（後述）。うち 1 件（`opengraph-image.tsx:41` の `img` に `alt` 属性がない）は実際の a11y リンティング指摘であり、単なる誤検知ではない。

### `any` / `as` / 非 null アサーションの実測件数

```bash
# any（型注釈としての any・.test. を除外）
grep -rnE ':\s*any\b|<any>|as any\b|any\[\]|Record<string, any>' src app --include="*.ts" --include="*.tsx" | grep -v '\.test\.' | wc -l
# → 0 件

# as（型アサーション。'as const' を除く）
grep -rnE '\bas\s+[A-Z][A-Za-z0-9_<>]*\b' src app --include="*.ts" --include="*.tsx" | grep -v '\.test\.' | grep -v 'as const' | wc -l
# → 32 件

# 非 null アサーション（! ただし !== / != を除く）
grep -rnE '[a-zA-Z0-9_\)\]]\!\.|[a-zA-Z0-9_\)\]]\!\)|[a-zA-Z0-9_\)\]]\![,;]' src app --include="*.ts" --include="*.tsx" | grep -v '\.test\.' | grep -v '!==' | grep -v '!=' | wc -l
# → 0 件
```

`as` 32 件の内訳を全件確認した結果、**大半（26/32）はブランド型のスマートコンストラクタ内部**（例: `page-number.ts:29` `return raw as PageNumber`）で、バリデーション済みの生値をブランド型へ載せるだけの、TypeScript の nominal typing パターンとして正当な用法。残り（`cloudflare-bindings.ts` の env バインディングキャスト、`static-gem-digest.ts` の未検証 JSON を「フィールド単位で `unknown` の中間型」へ載せて直後に `typeof` で全項目検証するパターン、`oauth.ts` の `response.json() as AccessTokenResponse`）も、型システムを迂回して安全性を破壊する「危険な `as`」ではなく、境界での明示的な受け渡しに限定されている。**危険な `as any` / 無検証キャストは 0 件**と判定する。

### tsc・eslint 実行結果

```
$ npx tsc --noEmit
（出力なし・exit code 0）

$ npx eslint --max-warnings 3
/home/user/gem-hunter/app/[locale]/opengraph-image.tsx
  40:8  warning  Unused eslint-disable directive (no problems were reported from '@next/next/no-img-element')
  41:7  warning  img elements must have an alt prop, either with meaningful text, or an empty string for decorative images  jsx-a11y/alt-text

/home/user/gem-hunter/src/infrastructure/platform/static-gem-digest.test.ts
  98:26  warning  '_sourceUrl' is assigned a value but never used  @typescript-eslint/no-unused-vars

✖ 3 problems (0 errors, 3 warnings)
exit code 0
```

型エラー・lint エラーは実測で 0 件。ただし警告 3 件のうち 1 件（OG 画像の背景 `<img>` に `alt=""` がない）は実害のない軽微な a11y 指摘だが、他コンポーネント（`repository-list.tsx` 等）では同種の装飾画像に一貫して `alt=""` を付けている中で、この 1 箇所だけ抜けている点は一貫性の綻び。

### 争点 (3)（層分離は適正か過剰か）への実装側の立場

**「過剰ではなく、この規模としては妥当。ただし境界線上」** という立場を取る。

根拠は上述の `container.ts:168-177`（`lookupGemIndexes` は usecase を新設しない明示的判断）と `search-gems.ts` の JSDoc（`toGemListPage` を既存の `tryPageNumber` と共有しない理由・`owner/repo` 判定を共有モジュール化しない理由）に見られる **「同じパターンに見えても機械的に統一しない」判断が複数箇所で一貫している** こと。これは「クリーンアーキテクチャのお作法を型どおりになぞっただけ」ではなく、YAGNI を実際の設計判断として運用している証拠であり、CTO レンズが懸念しうる「過剰設計」批判に対する実装側からの反証になる。

一方で、usecases 層の大半（`search-repositories.ts`・`get-repository-detail.ts` 等）は「ポートへそのまま委譲するだけ」の 1 行程度の薄いラッパーであり、この規模（MVP + 数機能）のアプリなら usecase 層を介さず route handler / composition root から直接ポートを呼んでも実害はなかった可能性がある。現状の層は「将来のユースケース複雑化に備えた予防的な骨格」であって、**現時点のロジック量に対しては明らかにオーバースペック**。ただし各層の境界（domain が外部 I/O を一切知らない・infrastructure が GitHub 固有知識を隔離する・composition root が唯一の配線点）はテスト容易性・置き換え可能性という形で実利益を生んでおり、「過剰だが害はない」という評価が妥当。「過剰であり害がある」は支持しない。

### 最終合否についての自分の立場

**条件付き合格**。コード品質そのもの（型安全性・エラー処理・命名・防御的実装）は技術課題の合格ラインを明確に超えている（O-3 は 4 相当）。条件として付けたいのは、①コメント密度と内部限定ジャーゴンの整理（第三者への引き継ぎを想定するなら圧縮すべき）②`page.tsx` 等の大型ファイルの分割検討 ③認めている 3 重実装（owner/repo 判定）の統合、の 3 点で、いずれも「今すぐ動かなくなる」類の欠陥ではなく保守性の磨き込み項目。O-1（与件充足）・O-6（セキュリティ）の他レンズの判定と合わせて最終合否を確定すべきだが、コード品質単体が不合格の足を引っ張る要素にはならないと判断する。

### `qa` — 主張
<sub>2026-08-24T12:08:37+09:00</sub>

## QA / テストエンジニアレンズ Round 1 レビュー

### ① スコアと rationale

**O-4（テスト・品質保証）: 4/5**
- 根拠: `npx vitest run --silent` を実際に実行 → **81 ファイル / 960 テスト全 PASS（46.28s）**。`npx playwright test` を実際に実行 → **112 件中 111 PASS・1 FAIL（`e2e/a11y.spec.ts`、2m17s）**。サンプリングした 8 ファイル（`page-number.test.ts` / `search-keyword.test.ts` / `search-repositories.test.ts` / `get-repository-detail.test.ts` / `mapper.test.ts` / `rate-limit.test.ts`（infra）/ `rate-limit.test.ts`（composition）/ `error-notice.test.tsx`）は自明な getter 確認ではなく、境界値・fail-closed・エラー分岐・セキュリティ性の高い分岐まで踏み込んでいる。5 に届かない理由は下記②③の 2 点（未登録の flaky・CI 自動実行範囲の限定）。

**O-8（開発プロセス・運用）: 4/5**
- 根拠: 二層 CI 構成（`quality-checks.yml` = Prettier/ESLint/tsc/Vitest の高速ゲート、`tools/run_checks.sh` = E2E/Lighthouse/依存規則等の重いゲートをセッションが手動実行）が `testing-strategy.md` §8・`pr-review-flow-summary.md` に明文化され、実装（459 行の `run_checks.sh`）と一致している。TDD の二重ループ・コミット順序（`test:`→`feat:`）・flaky レジストリ運用まで規律化。減点は、CI（GitHub Actions）が自動実行するのは 42 件中 4 件のみ（`pr-review-flow-summary.md` 自身の記述）で、E2E を含む大半がセッション（人手起動の Claude）依存という構造的な脆さ。

### ② よい点

1. **境界値・異常系を具体的に突いている**: `mapper.test.ts` は `pushed_at` が `null` / 不正文字列 / 両方不正の 3 段階フォールバック（`updated_at` → epoch）を個別にテストし、`private: true` を除外しつつ `totalCount` は書き換えないという「フィルタと集計を分離する契約」を **総数が items 件数と一致しない値（999）に固定**して検証している（変異に強い設計）。
2. **fail-closed の明示的検証**: `private` フィールド欠落時に「公開扱いに倒れず `UpstreamError` にする」というセキュリティ上重要な多層防御を単体テストで固定（`mapper.test.ts:182-193`, `:252-259`）。
3. **クエリインジェクション対策の網羅**: `search-keyword.test.ts` が `is:private` / `user:` / `-is:public` / `NOT` / `OR` / `AND` 等の修飾子構文を拒否しつつ、`C# tutorial` や `12:30 timer` のような正当な入力を通す「過剰拒否の回帰防止」テストを両方持つ（否定アサーションだけで済ませていない）。
4. **vi.mock の節度**: `src/**/*.test.ts(x)` 全体で `vi.mock` 使用は 7 ファイル 14 箇所のみ（`grep` で実測）。大半はフェイクのポート実装（`fakePort`）で、`testing-strategy.md` §4 の優先順位（①フェイク②MSW③vi.mock 最終手段）が実装でも守られている。
5. **E2E は「常に緑」構造ではない**: `sp-1.spec.ts` は一覧の件数（3 件固定）・リポジトリ名・アバターの `src`/`width`/`height` まで具体的に assert しており、実装を壊せば落ちる設計。実際、今回の実行で `a11y.spec.ts` が 1 件落ちており（③参照）、E2E がスタブに寄りかかって無条件で緑になっているわけではないことを実測で確認した。
6. **表駆動テストの意図の明文化**: `composition/rate-limit.test.ts` は検索枠と Gem 一覧枠が独立していることを「同じ IP・salt でも接頭辞が違う」という 1 本の非表駆動テストで固定し、なぜ表駆動化しないかをコメントで説明している。

### ③ 課題点（重要度順）

1. **【中】未登録の flaky が実測で見つかった（プロセス上の欠陥）**: フルスイート実行で `e2e/a11y.spec.ts:16`「一覧画面（検索結果）に serious/critical の違反がない」が `getByRole('link', { name: 'octostub/octo-widgets' })` の `toBeVisible()` で失敗（5000ms タイムアウト）。しかし同テストを `--repeat-each=3` で単体実行すると **3/3 で安定 PASS**（19.3s）。`docs/04_development/flaky-tests.md` には該当エントリが存在しない。`testing-strategy.md` §8.1 は「レジストリに載っていなければ本物の失敗として扱う」と明記しており、この方針に従えば今回の 1 件は「本物の失敗」として扱われるべきだが、実態はタイミング起因の flake の可能性が高い（原因未特定）。**レジストリ運用が自己の規律どおりに機能していない実例**であり、O-8 の減点理由。
2. **【中】E2E は GitHub Actions の自動実行対象外（`D-42`）**: 与件 §5「テストはコマンド一つで実行でき、CI で自動実行できる状態とする」の後半（CI 自動実行）は、`npm test`（Vitest）のみが `quality-checks.yml` で自動化されており、`npm run test:e2e`（Playwright・与件が明示する「検索→一覧」「一覧→詳細」「読み込み中/0件/エラー」の主要フローを最も直接カバーする層）は **PR ごとには自動実行されない**。実測（今回の 2m17s）を見ても実行コスト自体は現実的な範囲であり、「コストに見合わない」という `D-42` の判断は一定の合理性はあるが、与件の文言を字義通り取れば部分充足に留まる。
3. **【低】CI の被覆範囲がごく一部（自己申告どおり）**: `pr-review-flow-summary.md` 自身が「CI が見るのは 42 件中 4 件だけ」と明記しており、依存規則検査・UI 寸法検査・レーン到達可能性・棚卸し判定 self-test 等の大半が **セッション（Claude）の手動実行**に依存している。これは「人が判断せずとも品質が担保される」という意味での自動化ではなく、運用手順への信頼に依存する構造である。
4. **【低】E2E 全体実行の再現性検証が 1 回のみ**: 今回の実行結果（111/112）は 1 回限りの観測であり、`flaky-tests.md` の `sp-8-auth` エントリのように「20 回連続実行して安定確認」までは行っていない（時間制約により本レビューでは未実施。実施できなかった事実として明記する）。

### ④ 与件 §5 テスト要件の充足判定

| 要件 | 判定 | 根拠 |
|---|---|---|
| 検索実行→一覧表示の主要フロー | **充足** | `e2e/sp-1.spec.ts`（件数・リンク名・アバター属性まで具体 assert）、実行して PASS 確認済み |
| 一覧→詳細ページ遷移・詳細表示 | **充足** | `e2e/sp-2.spec.ts` 等（未個別読了だがファイル名・命名規約から該当。詳細ページのユニット側は `get-repository-detail.test.ts` で裏取り済み） |
| 読み込み中・0件・エラーの状態表示 | **充足** | `e2e/sp-9-loading-empty.spec.ts` / `sp-9-errors.spec.ts`（読み込み中・0件・network/rateLimitPrimary/rateLimitSecondary/upstream/auth/validation の各エラー種別を個別に区別して検証、実行して PASS 確認済み） |
| 外部APIモック化・ネットワーク非依存 | **充足** | `e2e/stub/server.mjs`（node:http のみの自前スタブ）。ACL 層は MSW（`oauth.test.ts` 等）。`tools/check_e2e_stub_external_urls.py` がフィクスチャ内の外部 URL 混入も機械検査 |
| コマンド一つで実行・CI 自動実行 | **部分充足** | `npm test` は CI（Actions）で自動実行（実測 PASS）。`npm run test:e2e` は「コマンド一つ」の要件は満たすが「CI で自動実行」は満たさない（`D-42` により意図的に session 実行へ寄せている）。主要フローの検証を最も担っている層が CI 対象外である点は、字義通りの与件解釈では未充足寄り |

### ⑤ 実行したコマンドと実結果

| コマンド | 結果 |
|---|---|
| `npx vitest run --silent` | PASS: 81 files / 960 tests, Duration 46.28s（real 51.9s） |
| `npx playwright install chromium` | 既にキャッシュ済み（`/opt/pw-browsers`）で即完了 |
| `npx playwright test`（全 112 件） | 111 PASS / 1 FAIL（`e2e/a11y.spec.ts:16`）, real 2m17.4s |
| `npx playwright test e2e/a11y.spec.ts -g "一覧画面" --repeat-each=3` | 6/6 PASS（19.3s）— 上記の FAIL が単体では再現しない = flaky の疑い濃厚 |

実行できなかったもの: `npm run check`（`bash tools/run_checks.sh`）全体（Lighthouse・依存規則等含む・459 行）は時間制約のため個別コマンドの直接実行に代えて未実施。`tsc --noEmit` / `eslint` は担当外（code_quality レンズの担務）のため未実行。

### ⑥ 最終合否についての自分の立場

**条件付き合格**。テストの「実効性」は非常に高く、量に頼らず境界値・fail-closed・セキュリティ分岐まで踏み込んでいる点は与件の期待水準を明確に上回る（O-4 は本来 5 に近い）。しかし (a) 未登録の flaky を実測で発見してしまった＝自己申告のプロセス規律（flaky レジストリ）が実態と乖離していた、(b) 与件が要求する「CI で自動実行」を主要フロー検証の主力である E2E が満たしていない、という 2 点は看過できない。企業の技術課題としては、この 2 点を Issue化した上での合格が妥当と考える（未実装ではなく運用上の詰めの甘さであり、与件の必達項目そのものが欠落しているわけではない）。

### `cto` — 主張
<sub>2026-08-24T12:09:04+09:00</sub>

# CTO レンズ round 1（O-2 / O-7・争点 (2)(3)(6)(7)）

判定はすべて実コード・実行結果で裏取りした。ドキュメントの記述は「主張」として扱い、必ず `grep` / `sed` で照合している。

---

## 1. スコア

| 観点 | スコア | rationale（1 行） |
|---|---|---|
| **O-2 アーキテクチャ設計** | **4** | 依存方向は機械検査で 176 ファイル・違反 0（`tools/check_architecture_boundaries.py` 実行結果）、ポート総量 217 行と極めて安価で YAGNI も ADR で明示管理されている。一方で **宣言した「`app/` は薄く・ロジックを書かない」規則を自ら破っており**（`app/[locale]/page.tsx` 549 行）、アプリケーション・オーケストレーションが 3 エントリポイントに重複している。 |
| **O-7 ドキュメント・説明可能性** | **5** | 与件 §6 の要求を全項目満たしたうえで、ADR に **却下した選択肢・実測による反証・取り消し追記** があり、決定ログ（`D-1`〜`D-42`）と README 索引が **機械検査で守られている**（`tools/check_adr_coverage.py` → OK）。設計判断を後から再構成できる状態は商用水準。 |

> 🔴 O-7=5 は **requirements_auditor が与件 §7 に ❌ を出さないこと** に従属する。`docs/02_requirements/minimum-requirements-checklist.md` は「44 ✅ / 2 ⚠️ / 0 ❌」と自己申告しており、ここに実測の ❌ が 1 件でも出れば **ドキュメントの over-claim** となり O-7 は 3 まで落とす。round 2 で確認したい。

---

## 2. O-2: よい点（実測）

1. **依存方向が実際に内向き（宣言どおり）**。`grep -rn "from ['\"].*\(infrastructure\|/ui/\|usecases\|next/\|react\)" src/domain/` → **0 件**。`src/usecases/*.ts` の import は全件 `../domain/**` のみ（6 ファイル実測）。`python3 tools/check_architecture_boundaries.py` → `✅ 依存規則 OK（176 ファイル・Warning 0 件）`。**設計が文書だけでなく実行可能な検査で守られている**のは、この規模の提出物では稀。
2. **層のコストが安い**。`src/domain/ports/*.ts` は **7 ファイル合計 217 行**（`auth` 12 / `cache` 13 / `clock` 8 / `gem-digest` 25 / `gem-index` 120 / `rate-limit` 14 / `repository-query` 25）。src 実装総量 7,621 行に対し **2.8%**。「クリーンアーキテクチャで肥大化した」という典型的失敗には該当しない。
3. **YAGNI を規律として明文化し、例外を ADR 化している**。`application-architecture.md:14-26` §0 が「層を分ける理由は `W-1`〜`W-3` の 3 つだけ。言えないなら足さない」と自らに制約を課し、`docs/adr/0005-cache-port-yagni-exception-and-ttl.md` は **Cache Port を「YAGNI の意図的な例外」と名指しして** 却下案 7 件・再決定条件・受け入れる代償まで書いている。同 ADR は `AsyncLocalStorage` 案を **`wrangler dev --local` の実機検証で不成立と確認して却下**しており、机上の比較検討ではない。
4. **値オブジェクトがセレモニーではなく実利を出している**。`src/domain/model/search-keyword.ts:19-27` の `QUALIFIER_PATTERN` は、ユーザー入力の `is:private` 等の修飾子を拒否して **GitHub 検索式へのインジェクションを境界で塞いでいる**。ブランド型 + スマートコンストラクタの採用理由が「型安全のため」ではなく **具体的な攻撃面の遮断** に結びついているのは、この規模でも十分に見合う。`page-number.ts:33-45` の `tryPageNumber`（URL 改変を 500 にせず既定へ倒す）も同様に実利がある。
5. **composition root の設計判断が記録されている**。`src/composition/container.ts:52-58` は「関数内で `new` すると毎回空の Map になり常に MISS」という **失敗モードを明記して** モジュールスコープ生成を選んでおり、判断が後から検証可能。

## 3. O-2: 課題点（重要度順・すべて実ファイル根拠）

### 🔴 (1) 宣言した「`app/` は薄く・ロジックを書かない」規則を実装が守っていない（最重要）

- 規則: `docs/03_design/architecture/application-architecture.md:56`（`app/` = **薄く保つ**）・**:196**（Server Component は「composition root からユースケースを取り、結果を `src/ui/` に渡すだけ。**ロジックを書かない**」）。
- 実測: `app/[locale]/page.tsx` = **549 行**（うちコメント 88 行）。`app/[locale]/gems/page.tsx` = **422 行**。`app/[locale]/repos/[owner]/[repo]/page.tsx` = 301 行。
- 中身が「渡すだけ」ではない: `app/[locale]/page.tsx:54` の `runSearch()` が **値オブジェクト変換（:72）→ レート制限の強制（:81）→ 例外のドメインエラー判別（:94, :103）→ 画面状態への写像** という **アプリケーション層の仕事** を丸ごと担っている。`export default LocaleHome`（:313）は 236 行。
- **同じオーケストレーションが 3 か所に重複**: `app/api/search/route.ts:58, 64, 86`（`searchKeyword` → `enforceSearchRateLimit` → `instanceof DomainError`）、`app/[locale]/gems/page.tsx:244-246`。route.ts:90 のコメントが「`page.tsx` の catch と同じ方針」と **重複を自認**している。
- 一方で `src/usecases/search-repositories.ts` は **23 行の純粋な委譲**（自身のコメントで「そのまま委譲する薄い層」と明記）、`get-repository-detail.ts` は 20 行。
- **CTO としての評価**: これは「クリーンアーキテクチャが過剰」なのではなく **配置が逆転している**。ユースケース層が空洞で、本来そこにあるべき手順（枠の消費順・エラー種別への写像）がフレームワーク層に散っている。層を作った目的（`W-3` = ネットワークもフレームワークも要らずにテストできる）が、**最も壊れやすい合成部分で達成できていない**。`check_architecture_boundaries.py` は import 方向しか見ないためこの逸脱を検出できない（doc 自身が :218 でその限界を認めている）。

### 🟠 (2) `RateLimitPort` が消費者ゼロの名目上の抽象（唯一の実 YAGNI 違反）

- `src/domain/ports/rate-limit-port.ts`（14 行）を import しているのは **実装 `src/infrastructure/platform/rate-limit.ts:1`（`implements RateLimitPort`）のみ**。`grep -rn ": RateLimitPort" src app` → 実装コードでのヒット **0 件**（テスト名の文字列 1 件のみ）。合成側 `src/composition/rate-limit.ts:4` は具象 `WorkersRateLimit` を直接 import している。
- つまり **依存性逆転の継ぎ目として一度も使われていない**。§0 の「`W-1`〜`W-3` のどれを守るか 1 行で言えないなら足さない」という自らの規律が、ここだけ適用されていない。
- 影響は小さい（14 行）が、**7 ポート中 6 つは実消費者がいる**（`cache`→`container.ts` で `CachePort` 型注釈、`clock`→3 テスト + 2 実装、`repository-query`→ユースケース 3 本 + デコレータ、`auth`/`gem-digest`/`gem-index`→ユースケース）ため、規律の適用漏れとして 1 件だけ浮いている。

### 🟠 (3) エラーバウンダリが framework の機構ではなく規約で守られている

- `find app -name 'error.tsx' -o -name 'global-error.tsx' -o -name 'loading.tsx'` → **`not-found.tsx` 1 件のみ**（`app/[locale]/repos/[owner]/[repo]/not-found.tsx`）。
- `app/[locale]/page.tsx:364-369` のコメントが自ら「`app/` 配下に `error.tsx` は無く、失敗すれば既存の検索機能まで巻き添えになる」と述べ、`.catch(() => null)` の **手動二重防御** で凌いでいる。想定外の例外に対する継続性が「各 await に catch を書き忘れない」という人間の規律に依存している（与件 §4.1「握りつぶさず継続利用可能に保つ」の担保が構造的でない）。

### 🟡 (4) 設計文書に存在しないディレクトリが書かれている（軽微なドリフト）

- `application-architecture.md:71` は `src/domain/services/` を「確定」したディレクトリ構造として記載しているが、`ls src/domain/services` → **No such file or directory**。実際の `GemIndex` 算出は `src/domain/model/gem-index.ts` にある。「確定」と銘打った節の内容が実体と食い違う。

---

## 4. O-7: よい点（実測）と課題点

**よい点**

1. **与件 §6 の要求を全項目カバー**（README:28-56 セットアップ・`npm` スクリプトは `package.json` の実 scripts と一致することを確認 / :68-87 環境変数は **未設定時の挙動まで** 表にしている / :111-190 設計上の判断 9 項目 / :191-201 AI の利用範囲）。
2. **ADR が「意思決定の記録」として本物**。0005 は却下案 7 件 + 実機検証による反証、0002 は §2 決定 #6 を **`D-31` で取り消す追記**（:41）を残して履歴を破壊していない、0012 §3.1 は **「与件の『対象外』は『実装してはならない』ではない」という解釈そのものを明文化**している。ADR を後付けの体裁ではなく判断の一次記録として運用できている。
3. **ドキュメントが機械検査で守られている**。`python3 tools/check_adr_coverage.py` → `[adr-coverage] OK（prd.md §12 の ADR 記録と README の必須記載を確認）`。README の ADR 索引と ADR 見出しの乖離が検出される。
4. **正直さ**。README:82 は `SITE_URL=` に空文字を入れると起動失敗する落とし穴を自ら書き、:84 は「本番に OAuth 変数を供給していないためログイン導線は現在非表示」と現況を隠さない。:224-234 は与件原文の著作権が第三者にあることを `NOTICE` 付きで扱っている（提出物としての法務感覚は加点材料）。
5. **評価者導線**が設計されている（README:10 の「与件全 11 項目充足」＋チェックリストへのリンク、:12 の目次、:16-26 の実画面スクリーンショット + 説明的 alt）。

**課題点**

1. 上記 O-2 (1)(4) の **ドキュメント⇄実装ドリフト 2 件**。SSOT を名乗る文書が、実装が守っていない規則を「規則」として書いている状態は、読み手が設計を誤解する。
2. **総量**: `docs/**/*.md` = 112 ファイル・24,164 行。うち **AI 運用ハーネス（`docs/rules/`）が 66 ファイル・11,221 行と約半分**。加えて `.claude/**/*.md` 48 ファイル、`tools/` に 82 スクリプト。**製品ドキュメントは 46 ファイル・12,943 行** で、これ自体も MVP の提出物としては多い。

---

## 5. 争点への立場

### 争点 (2) MVP 与件に対し Gem Index・OAuth・i18n・Workers 運用まで作り込んだのは加点か減点か → **加点**（条件付き）

- **根拠**: スコープ拡大が **場当たりではなく事前の意思決定**として記録されている。`open-questions.md` `D-2`（2026-08-17）が「与件は外部与件。受け入れ基準は必達の下限として固定・変更しない。**ただしその上への上乗せは自由**」と最初に確定させ、`D-3` が「主目的は選考課題／ポートフォリオ、副次に運用継続」と目的を明示。`ADR 0012 §3.1` は **「与件 §1.2 の『対象外』は『実装しなくてよい』であって『実装してはならない』ではない」と解釈を明文化し、誤読されうるリスクまで自覚して README・PRD・ADR の複数箇所へ理由を書くことを完了条件にしている**。
- **規模の実測**（作り込みの大きさは正直に出す）: src 実装 7,621 行のうち、上乗せ機能（gem / digest / oauth / session / i18n / locale / seen）関連が **3,321 行 = 44%**。飾りではなく本体と同等規模である。
- **それでも加点とする理由**: 上乗せが与件の必達項目を **侵食していない**設計になっている。トップページの Gem ダイジェストは `app/[locale]/page.tsx:370` で `hasKeyword ? null : ...` の **排他表示**にされ、検索経路と DOM 上で競合しない理由（既存 E2E の `getByRole('list')` 衝突）まで書かれている。OAuth は `ADR 0012` 決定 #1 で「ログインで変わるのはレート枠だけ・機能差を作らない」と縛られ、資格情報未設定時は導線ごと静かに無効化される（README:84 の実運用がそうなっている）。
- **減点に転じる条件**: requirements_auditor が §7 の 11 項目に ❌ を出した場合。そのとき初めて「与件を満たす前に横へ広げた」というスコープクリープの批判が成立する。**現時点で私はその証拠を持っていない**。

### 争点 (3) クリーンアーキテクチャ／DDD 的層分離はこの規模で適正か過剰か → **層の数は適正。問題は「過剰」ではなく「配置のズレ」**

- 過剰説の反証: ポート総量 217 行（src の 2.8%）、7 ポート中 6 つに実消費者、DI コンテナは不採用（`container.ts:26` が明示）、`src/shared` は 38 行、機械検査で違反 0。**層を増やしたことによる肥大化は実測では起きていない**。
- ただし **見返りを取りきれていない**: ユースケースが 20〜23 行の委譲に留まる一方、実際の手順は `app/` の 549 行 / 422 行のページに 3 重複している（§3 (1)）。層を分けた目的の `W-3`（フレームワーク非依存でテストできる）は、**最も回帰が起きやすい合成部分では達成できていない**。
- **結論**: 「この規模に層分離は過剰だった」ではなく **「層は正しく作ったが、置くべきものを置いていない」**。是正コストは低い（`app/` の `runSearch` 相当をユースケース or composition のヘルパへ引き上げるだけ）。

### 争点 (6) ドキュメント量は加点か減点か → **製品ドキュメントは加点、AI 運用ハーネスは中立（減点にはしない）**

- **加点側**: 46 ファイル・12,943 行の製品ドキュメントは「量」ではなく **参照可能性**で価値を出している。ADR ↔ 決定ログ ↔ PRD ↔ README が相互リンクし、索引は機械検査（`check_adr_coverage.py` = OK）で守られる。「なぜそう作ったか」を面接で口頭に頼らず提示できる状態は、採用判断上ほぼ最大の加点材料。
- **読み手負荷への反論**: README:12 に目次、:10 に「与件 11 項目充足 + チェックリスト」への直行リンク、:101-109 に文書の入口が用意されており、**評価者が最短経路で判定できる導線が設計されている**。全部読ませる構造ではない。
- **ハーネス（`docs/rules/` 66 ファイル・11,221 行 + `.claude/` 48 md + `tools/` 82 スクリプト）**: 提出物としてはノイズになりうるが、**一方的な減点にはしない**。与件 §6 が「AI を利用した場合はその利用方法と範囲」を要求しており、README:191-201 の記述が **実在するルールファイル・フックの裏付けを持つ**（自己申告だけで終わっていない）。開発プロセスの再現性の証跡として要件に直接応答している。
- **ただし提案**: リポジトリ直下の見え方として、アプリ本体（`src/` `app/` `e2e/`）と運用ハーネスの境界が README 冒頭で明示されていない。1 段落あれば「何を読めば実装評価が終わるか」が確定する。

### 争点 (7) 最終合否 → **合格**（ただし他 2 レンズの結果に従属）

- **私が置く企業側の期待水準**: 「Next.js App Router で与件どおり動くものを作れる」は **合格ラインではなく前提**。合格判定は次の 3 点で行う — ① 与件を満たしたうえで **設計判断を他人に説明でき、後から再構成できるか** ② 自分の設計規律を **機械で守る仕組みに落とせるか** ③ 実害あるセキュリティ欠陥を作らないか。
- ①②は明確に上回っている（`check_architecture_boundaries.py` / `check_adr_coverage.py` / `run_checks.sh` の存在と実行結果、ADR の却下案と取り消し追記）。**この人にプロダクトを任せられるか** という問いへの私の答えは **Yes**。設計の逸脱（`app/` の厚み）は指摘すれば直せる種類のもので、判断の質そのものは疑っていない。
- **合格を「条件付き合格」へ降格する条件（round 2 で確定させたい）**:
  1. requirements_auditor が与件 §7 の 11 項目に **❌ を 1 件でも出した**場合 → 条件付き合格（該当項目の実装が条件）。加えて README:10 と充足チェックリストが over-claim になるため O-7 を 5→3 に下げる。
  2. security が **critical または high の実害欠陥**（トークン露出・セッション偽造・XSS）を実証した場合 → 条件付き合格（修正が条件）。medium 以下は合格を覆さない。
  3. qa が「E2E がスタブ固定で実装が壊れても緑」と **実証**した場合 → 合格は維持するが O-4 の減点として扱う（設計・説明可能性の評価は覆らない）。
- 現時点の私の投票: **合格**。

## ラウンド 2

### `frontend` — 反論
<sub>2026-08-24T12:12:07+09:00</sub>

# frontend レンズ Round 2: 反論・譲歩

対象ファイルの再読はせず、round 1 の自分の分析とホワイトボードのみで応答する。

## 1. cto の指摘（app/ 3エントリポイントへのオーケストレーション重複）への回答

**部分譲歩・部分反論。**

- **route.ts の重複には反論**: `app/api/search/route.ts` はドメイン的に「画面のレンダリング経路」ではなく、ADR 0005 §2.3 が明示するとおり `X-Cache-Status` 観測専用の別経路（呼び出し元 1・YAGNI 明記済み）。Server Component（`page.tsx`）は Web 標準 `Response` を経由せずレンダリングされるため、キャッシュ状態を外部観測させる手段として Route Handler を別途持つこと自体は Next.js の制約上妥当（cto 自身が ADR の実機検証を評価している）。ここでの `searchKeyword`→`enforceSearchRateLimit`→`instanceof DomainError` の反復は「観測用の薄い経路が本体の判定ロジックを最小限コピーしている」というだけで、`app/ は薄く` の規則が守る対象（プロダクションの主経路）への違反としては軽微。
- **page.tsx 側は譲歩する**: しかし `app/[locale]/page.tsx` の `runSearch()`（54-108行）と `app/[locale]/gems/page.tsx` の同型ロジックは、どちらも **Server Component として本体のレンダリング経路**であり、Server Component だからロジックをインラインにせざるを得ない技術的必然性は無い。Server Component は任意の async 関数を普通に呼べるため、`searchKeyword` 変換 → レート制限強制 → `DomainError` の種別判定という共通手順は `src/usecases/` か `src/composition/` に `runSearchAndMapToState()` 相当の共有ヘルパーとして抽出でき、Route Handler と違って HTTP 往復を挟む必要も無い。cto の「配置が逆転している」という診断は正しく、Server Component の性質はこの重複を正当化しない。O-2 の現行評価（4）を維持する立場に同意する。

## 2. O-5 の「next/image 不使用」「レスポンシブ実機未検証」減点について

**image optimization 減点は維持（ただし性質を明確化）。responsive の課題点は撤回・再分類する。**

- **image optimization**: この論点は §7 の 11 項目チェックリストには含まれず（requirements_auditor の表にも項目なし）、§4.2 非機能要件の範疇であり O-1 ではなく O-5 の管轄。requirements_auditor の O-1=5 判定と衝突しない。ADR 0013 の法務的正当化（GitHub ToS 再配信禁止）は合理的で、GitHub 側 `?s=N` による実サイズ縮小・`width`/`height` 明示（CLS対策）・`loading="lazy"` は実質的な最適化の代替として機能している。**「未充足」ではなく「模範的（5）ではない」の根拠として維持する**——Next.js のネイティブ機構を使わない選択自体は妥当だが、それでも O-5=5 に届く決め手にはならない、という程度の減点として位置づけを明確化する。
- **responsive 実機未検証**: requirements_auditor が round 1 で `repository-detail.tsx:116` の `grid-cols-2 sm:grid-cols-4` とキーボード到達性（ネイティブ `<form>`/`<Link>`・`focus-visible:ring-3`）を根拠に §7 項目9 を「充足」と判定している。この要件文言（「レスポンシブ対応およびキーボード操作が可能」）はコード上の対応で足りると読むのが妥当であり、視覚的スクリーンショット確認まで要求する根拠は与件に無い。**この点は自分の round 1 の課題点リストから撤回し、O-5=4 の理由からは外す**（image optimization のみを O-5=4 の根拠として残す）。

## 3. qa の「E2E が CI 自動実行対象外」指摘は O-1 に影響するか

**O-1 には影響しない。** §5 テスト要件（コマンド一つで実行・CI 自動実行）は自分のレンズ外（QA の O-4 管轄）であり、frontend が担当するのは §3 機能要件・§3.1/§3.2 画面/状態要件のみ。O-1=5 は維持する。

技術的な所見としては qa の「部分充足」という読みに同意する。与件 §5 は「テストはコマンド一つで実行でき、CIで自動実行できる状態とする」と一文で要求しており、主要フロー検証の主力である `test:e2e` が `D-42` により意図的に GitHub Actions の対象外にされている以上、文言を字義通り取れば E2E 側は「コマンド一つ」は満たすが「CI 自動実行」は満たさない。これは O-4 の減点材料であって O-1 の減点材料ではない、という qa・requirements_auditor 双方の切り分けに賛成する。

## 4. 最終合否についての自分の立場（再表明）

**条件付き合格〜合格の境界（frontend 観点は合格に近い）。** FR-1〜FR-7・§3.1/§3.2 の充足は requirements_auditor の独立判定とも一致し、揺らいでいない。cto への譲歩（page.tsx / gems/page.tsx のオーケストレーション重複は是正余地あり）は O-2 の設計品質論点であって機能要件の欠落ではないため、frontend レンズ単体の合否判定には影響しない。全体の合否は security の medium 2件（CSPヘッダ欠如・レート制限フェイルオープン）と qa の flaky/CI 範囲の扱い次第で synthesizer が決めるべきで、frontend としては不合格化する材料は持っていない。

### `qa` — 反論
<sub>2026-08-24T12:12:13+09:00</sub>

## QA Round 2: 敵対的相互反論

### 論点1: requirements_auditor の §5「充足」判定は覆るか

**決着: 覆らない（item 10 は充足のまま）。ただし §7 チェックリスト自体に取りこぼしがある。**

`minimum-requirements.md` を再確認した（105-134 行）。§5 は 5 つの箇条書きから成るが、§7 の 11 項目チェックリストに落ちているのは冒頭 1 文だけを圧縮した **項目10「主要フローのテストコードが存在し、実行して成功する」**であり、「外部APIモック化」「コマンド一つで実行・CI自動実行」の文言は 11 項目のどこにも独立して現れない。requirements_auditor の item10=充足判定は**この文言に対しては正確**であり、私の指摘（flaky 未登録・E2E が CI 非自動実行）は item10 を ❌ にする材料ではない。

したがって cto が round1 で立てた「❌ が1件でも出れば O-7 を 5→3」条件（343行）は**発火しない**。

一方で、§5 全文を採点基準とするなら（brief は §5 を丸ごと一次資料と明記）「コマンド一つで実行でき、CIで自動実行できる状態とする」は npm test のみ充足・npm run test:e2e は未充足であり、**これは O-1 ではなく O-4 の減点として処理すべき**というのが私の一貫した立場（round1 と同じ）。requirements_auditor の「11/11充足」は §7 チェックリストの粒度では正しいが、§5 のテスト要件の完全性を保証するものではない、と切り分けて決着させる。

### 論点2: frontend の O-1=5 に、テスト実効性の観点から反証できるか

**反証材料なし。むしろ補強材料がある。** round1 で実測した2点が根拠:

1. `e2e/sp-1.spec.ts` は一覧件数（3件固定）・リンク名・アバターの `src`/`width`/`height` まで具体的に assert しており、フィクスチャに寄りかかった「常に緑」構造ではない。実際フルスイート実行で `a11y.spec.ts` が1件落ちた（flaky ではあるが「絶対に落ちない」構造ではないことの証拠）。
2. round2 で新たに確認した `e2e/overflow-guard.spec.ts`（320px viewport 専用）: コメント（4-12行）に「本番で長い URL の description が横スクロールを起こしたが、既存の `sp-10.spec.ts` は短い文字列しか使っておらず検知できなかった」と明記。**実際の本番バグを受けて、検知できなかった過去のテストを敵対的フィクスチャで強化した**という自己修正の実例。

frontend が課題点③で「レスポンシブの実機検証は未実施」としたのは正確（これは Playwright の実ブラウザ実行であり、複数デバイスでの目視確認ではないため、frontend の「目視確認は未実施」という文言と矛盾しない）。ただし「実機検証」を広く「実ブラウザでの自動検証」まで含めるなら、320px の横スクロール回帰は自動化されている、という事実は O-5 の rationale に一行足す価値がある。**O-1=5 への異議は無し**。

### 論点3: cto の「3箇所重複」は回帰リスクを生んでいるか

**Yes。テスト構造の非対称性から実証できる。** round2 で `app/api/search/route.test.ts` と `app/[locale]/gems/page.test.tsx` の `describe`/`it` を確認した:

- `app/api/search/route.ts`: **7種類の `ErrorKind` 全てを個別テスト**（validation/network/auth/notFound/rateLimitPrimary/rateLimitSecondary/upstream、ステータスコード・`Retry-After` ヘッダまで）。
- `app/[locale]/gems/page.tsx`: `page.test.tsx` は **レート制限の配線のみ 4 テスト**。他 6 種の `ErrorKind` マッピングはこのファイルではテストされていない。
- `app/[locale]/page.tsx`（`LocaleHome`/`runSearch`）: **ユニットテスト自体が存在しない**（`async` Server Component のため testing-strategy.md の方針どおり E2E 専任。`e2e/sp-9-errors.spec.ts` がカバーするが、7種全部を route.test.ts と同じ厳密さで突き合わせているかは未確認）。

3箇所とも同じ「値オブジェクト変換 → レート制限強制 → `DomainError` の種別判定」ロジックを重複実装しているのに、**その3実装の挙動が同一であることを保証する共有テスト（契約テスト）は存在しない**。route.ts 側でエラー種別マッピングのバグを直しても、gems/page.tsx や page.tsx 側の同種バグは、それぞれのテストスイートが薄い/存在しないために **検知されずに残り得る**。これは cto の O-2 課題点(1)を、QA 観点（テストの実効性）から独立に裏付ける。code_quality が指摘した owner/repo 判定の3重実装（round1・209行）と合わせ、**「重複 + 各実装ごとに検証密度が異なるテスト」という同型のパターンが2箇所で確認された**ことも付記する。

### O-4 / O-8 スコアの再確認

上記を踏まえてもスコアは変更しない: **O-4=4 / O-8=4**（round1 のまま）。論点1の再検証で「§7 チェックリストは正確だが§5全体には粒度の粗さがある」という立場がより明確になっただけで、実測結果自体（960/960・111/112・8ファイルの実効性サンプリング）は揺らいでいない。論点3で見つけたテスト密度の非対称性は O-8（開発プロセス・運用）の既存の課題点③（CI被覆がごく一部）と同根の問題として扱う。

### 最終合否についての自分の立場（再表明）

**条件付き合格。変更なし。** 与件必達項目（§7 の11項目・§2技術要件・§6ドキュメント要件）は他レンズの検証を含め未充足0件、セキュリティも critical/high 無し。条件として残すのは (a) `docs/04_development/flaky-tests.md` へ今回発見した a11y.spec.ts の flaky を登録する（またはタイミング原因を特定し恒久対応する）、(b) E2E の CI 自動実行化または「CI 非自動実行である」ことの README・与件チェックリストへの明記のいずれか、(c) cto/code_quality が指摘した重複実装（search オーケストレーション3箇所・owner/repo判定3箇所）に契約テストを足すか統合する。いずれも実装のやり直しを要する規模ではなく、Issue化して合格を出すのが妥当という立場は round1 から変わらない。

### `code_quality` — 反論
<sub>2026-08-24T12:12:44+09:00</sub>

## Round 2: code_quality の反論 / 一部譲歩

### 1. cto の指摘（`app/` 3 箇所のオーケストレーション重複）— 事実として認める。ただしスコアは維持

指定 3 箇所を再読して確認した。

- `app/[locale]/page.tsx:54`（`runSearch` 定義）〜`:72`（`searchKeyword` 変換）〜`:81`（`enforceSearchRateLimit`）〜`:94,103`（`RateLimitExceededError` / `DomainError` 分岐）
- `app/api/search/route.ts:58`（`searchKeyword`）・`:64`（`enforceSearchRateLimit`）・`:86`（`instanceof DomainError`）
- `app/[locale]/gems/page.tsx:244`（`enforceGemListRateLimit`）〜`:246`（`RateLimitExceededError` 判別）— 私が round 1 で読んでいなかったファイルを本ラウンドで実読し確認

3 か所とも **「値オブジェクト変換 → レート制限強制 → DomainError の種別判別」という同じ手順**を独立に再実装している。route.ts:90 のコメント自身が「page.tsx の catch と同じ方針」と重複を自認しており、cto の指摘は**事実として正しい**。これは round 1 の私の分析の抜けで、`page.tsx` の肥大化は指摘したが、この**手順レベルの横断重複**までは特定できていなかった。ここは訂正する。

**ただしスコアは下げない**。理由は 2 つ。第一に、この発見は round 1 で私が既に O-3 の課題点として挙げた「肥大化」「3 重実装の owner/repo 判定」と**同じカテゴリの追加証拠**であり、既に O-3=4 の rationale に織り込んでいた結論（「動くコードとしては高品質だが、保守性の磨き込みが必要」）を補強するだけで、評価の方向自体は変わらない。第二に、3 か所は**戻り値の型が全部違う**（`SearchState` オブジェクト / HTTP `Response` / JSX）ため、共通化するには 3 つの出力契約を吸収する抽象が要り、それは `container.ts:168-177` で code_quality・cto 双方が評価した「消費者が 1 つしかない抽象を先回りしない」YAGNI 規律と緊張関係にある。**「今すぐ共通ヘルパへ引き上げるべきコスト」自体は小さい**（cto も「是正コストは低い」と書いている）という点で cto と完全に一致するので、O-2 側の指摘として処理すべき問題であり、O-3（コード品質）としては「望ましい未実施のリファクタ」であって「品質欠陥」ではないという整理を維持する。O-3=4 を維持しつつ、課題点リストへ本件を追記する。

### 2. `as` の自己反証（security・cto の観点から見逃しがないか）

round 1 で「32 件の `as` に危険なものは無い」と一括りにしたのは**精度不足**だった。再分類すると 2 系統ある。

- **(A) 検証済み値をブランド型へ載せる**（26 件・`page-number.ts:29` 等）— 安全。round 1 の評価どおり。
- **(B) 外部境界の値を「型として信頼」して cast する**（残り 6 件）— さらに 2 つに分かれる:
  - `static-gem-digest.ts:84,106,132` — cast 後に **フィールド単位で `typeof` 検証**してから使用（安全）。
  - `oauth.ts:122`（`(await response.json()) as AccessTokenResponse`）・`cloudflare-bindings.ts:28` / `asset-reader.ts:113`（`context?.env as EnvWithRateLimiter | undefined`）— **cast 時点でのランタイム検証が無い**。`oauth.ts` は直後に `!data.access_token` のみチェックしており、`access_token` の型・形式は未検証のまま `AuthPort` の戻り値として上位層へ渡る。GitHub 検索 DTO（`dto.ts`）が zod でスキーマ全体を検証しているのと比べ、**検証水準が一段低い**。

security が critical/high を報告していない（`npm audit` 0 件・OAuth 経路は固定オリジンへの POST のみで応答を第三者が細工できる経路が無い）ことから **実害には直結しない**と判断するが、「危険な `as` は 0 件」は言い過ぎだった。正しくは「**攻撃者が制御可能な値に対する未検証 cast は 0 件、信頼済み外部サービス（GitHub 自身）の応答に対する軽量な cast が 3 件**」に訂正する。O-3 のスコアはこの訂正だけでは変えない（実害が無く、GitHub 公式 API という信頼境界への cast は一般的な許容範囲のため）が、round 1 の記述精度としては security・cto の指摘がなくても自己反証すべき点だった。

### 3. 争点 (3)（層分離は過剰か）— cto の枠組みを採用し、自分の表現を撤回

round 1 で私は「過剰だが害はない・境界線上」とした。cto の O-2 実測（ポート総量 217 行 = src の 2.8%・7 ポート中 6 つに実消費者・`check_architecture_boundaries.py` で 176 ファイル違反 0・DI コンテナ不採用）と、上記 1 で確認した「app/ への手順漏出」を突き合わせると、**「過剰」という言葉は不正確**だったと判断する。層の**数**・**コスト**は実測でこの規模に見合っており、肥大化は起きていない。問題は「層を増やしすぎた」ことではなく「**usecases 層が薄すぎて、本来そこに置くべき手順（レート制限順序・エラー種別判別）が `app/` へ漏れた**」という**配置の誤り**である。

したがって最終的な表現は cto の「層の数は適正。問題は配置のズレ」を採用し、自分の「過剰」という評価語を撤回する。これは私が round 1 で示した反証材料（`lookupGemIndexes` の usecase 不設置判断）とも整合する — YAGNI 判断自体は健全に機能しているが、逆側（usecases 層を薄くしすぎて `app/` に手順が漏れる）の抑制が効いていなかった、という一貫した説明になる。

### 4. 最終合否の再表明

**条件付き合格**を維持する。O-3 は 4 のまま（今回追加確認した重複・cast の精度訂正は、既存の課題点リストを補強する再検証結果であり、評価方向を反転させる新事実ではない）。条件として明示するのは round 1 の 3 点に加え、④ `app/` 3 箇所（page.tsx / route.ts / gems/page.tsx）の「値変換 → レート制限 → エラー分類」手順をヘルパ関数（composition root 側が妥当）へ引き上げること。cto の O-2=4・security の O-6=4 と合わせても、コード品質単体を理由に不合格へ倒す材料は無い。

### `requirements_auditor` — 反論
<sub>2026-08-24T12:12:47+09:00</sub>

## requirements_auditor round2 rebuttal

読んだ他 5 名の round1 全文（`show tech-review-20260824`）。round2 で新規に確認したのは `e2e/overflow-guard.spec.ts`（既存ファイル。round1 で repository-list.tsx のコメントから存在は把握済みだったが中身は未読だったため中身のみ確認。読み取り専用・新規ファイルの開封はこれ 1 件のみ）。

### qa の指摘（E2E が CI 対象外／未登録 flaky 1 件）→ 項目 10 の判定を維持するか

**維持（充足のまま）**。§7 の項目 10 の文言は「主要フローの**テストコードが存在し、実行して成功する**」のみで、「CI で自動実行される」を含んでいない（それは §5 本文の別の一文であり、§7 チェックリストの独立項目としては切り出されていない）。qa 自身が §5 の個別要件表で「検索実行→一覧表示」「一覧→詳細遷移」「読み込み中・0件・エラー」の 3 項目をいずれも**充足**と判定し、`e2e/sp-1.spec.ts` 等を実行して PASS を確認している。今回見つかった 1 件の失敗（`a11y.spec.ts` の axe 検査）は主要フロー本体のテストではなく、`--repeat-each=3` で 6/6 再現せず flaky と判明している。したがって「実行して成功する」という項目 10 の文言に対する反証にはならない。

**ただし修正する点**: round1 で私は §5 全体を厳密に検証していなかった。qa の実行結果を踏まえ、§5 本文後段「CI で自動実行できる状態とする」は **Vitest（単体・結合）のみ充足、Playwright（E2E）は未充足** と明確化する。これは §7 の 11 項目のいずれにも属さない §5 固有の論点であり、**O-1 のスコアには反映せず、O-4/O-8（qa 担当）の減点として扱うのが正しい切り分け**だと判断する。O-1=5 は維持。

### frontend の指摘（`next/image` 不使用のグレー・レスポンシブ実機未検証）→ §4.2・項目9 の判定は維持できるか

**§4.2 画像最適化**: これは §7 の 11 項目には含まれていない（11 項目は「オーナーアイコン**表示**」のみを要求し「最適化」は問わない）。したがって項目 3 の判定（充足）は影響を受けない。§4.2 自体（非機能要件）については frontend の medium 評価に同意する。`next/image` 不使用は ADR 0013（GitHub ToS 再配信禁止への配慮）という理由文書があり単なる手抜きではないが、要件文言「最適化して配信」を Next.js 標準機構で満たしていない事実は変わらないため、O-1 ではなく O-5 側の減点として扱うのが妥当（frontend の切り分けに同意）。

**項目9（レスポンシブ + キーボード操作）**: **充足を維持し、frontend の「部分充足」より強い評価に訂正する**。round2 で `e2e/overflow-guard.spec.ts` を確認したところ、`test.use({ viewport: { width: 320, height: 720 } })` で **320px 幅（WCAG 1.4.10 が名指しする最小閾値）の実ブラウザレンダリングにより横スクロール非発生を検証するテストが 2 本（一覧・詳細）存在し、実装済み**。これは静的なコードリーディングでもなければ人間の目視でもないが、「実機（ブラウザエンジン）による自動レスポンシブ回帰検知」であり、frontend が「実施していない」と述べた検証を代替する実装が既に存在する。キーボード操作性は frontend 自身が `focus-visible:ring-3` の一貫使用・ネイティブ `<a>`/`<form>` を確認済みで争いがない。**結論: 項目9は充足のまま**（ただし 320px 単一ブレークポイントのみの検証であり、タブレット幅域や実デバイスでの目視は行われていない、という限定は認める）。

### cto の指摘（`app/` に検索オーケストレーションが 3 箇所重複）→ §4.4「API呼び出し・表示ロジック・UIを分離する」への影響

**§4.4 の文言上の充足には影響しない**。§4.4 が要求するのは「API呼び出し・表示ロジック・UIの分離」であり、cto 自身の実測（`check_architecture_boundaries.py` 違反0・domain への framework 漏れ0・`'use client'` 乱用なし）が示す通り、**層をまたいだ知識の混入は起きていない**——API 呼び出しは `src/infrastructure`、表示は `src/ui`、UI コンポーネントは表示専用のまま保たれている。cto が指摘しているのは「オーケストレーション手順（値変換→レート制限→エラー写像）が本来 1 箇所にあるべきなのに `app/` の 3 エントリポイントに複製されている」という **DRY・配置の問題**であり、「分離されていない」問題ではない（分離はできている。同じ手順が複数箇所に書かれているだけ）。したがって §4.4 は文言上は充足と判定するが、**保守性の観点（重複コード）としては明確な欠陥**であり、これは私の担当外の O-2/O-3 の減点材料として扱うのが正しい（cto・code_quality の評価に委ねる）。私の11項目表・§2表への影響はない。

### 争点: OAuth・Gem Index の「対象外」抵触は減点すべきという立場への応答

round1 で「必達項目を侵食していない」と判定した点は維持するが、cto が提示した `open-questions.md` `D-2`（与件は必達の下限として固定・上乗せは自由）・`ADR 0012 §3.1`（「対象外」＝「実装しなくてよい」であって「実装してはならない」ではないという解釈を明文化）は、round1 で私が把握していなかった一次資料であり、**この争点の結論を補強する**。想定される反論（「対象外と書かれた領域への実装はそれ自体が要件逸脱で減点すべき」）に対しては、与件原文 §1.2 の文言が「対象外」であって「禁止」ではないこと、かつ実装が①未ログインでも全機能が成立する②`sort=gem-index` を検索結果の主軸に採用していない（ADR 0009）という**必達動線への不可侵性**を保っている以上、**要件監査役（O-1）の観点では減点根拠にならない**という判定を再確認する。この点をスコープガバナンスの問題として扱うなら、それは cto の O-2（設計判断の妥当性）の管轄であり、O-1 の管轄ではない——両者を混同すると「与件を全部満たしている実装」が「対象外領域にも手を出した」という理由だけで要件充足スコアを下げられてしまい、11 項目を実コードで裏取りするという本レンズの検証方法そのものと矛盾する。

### 11 項目の最終確認（round2 時点）

round1 の 11/11 充足から変更なし。§5（テスト要件・CI自動実行の範囲）・§4.2（画像最適化）・§4.4（重複）はいずれも 11 項目チェックリストの文言外にあり、他レンズ（qa=O-4/O-8、frontend=O-5、cto/code_quality=O-2/O-3）の減点対象として切り出すのが正しい担当分けであり、O-1 のスコアを下げる根拠にはならないと判断する。

### O-1・O-7 スコア（round2 確定）

- **O-1: 5/5（維持）**。11 項目・§2 技術要件とも実コード裏取りで充足。他レンズの指摘はいずれも §7 チェックリスト外の非機能要件（§4.2/§4.4/§5後段）に属し、担当外の観点（O-2/O-4/O-5/O-8）の減点として切り分けるのが妥当。
- **O-7: 5/5 → cto の従属条件を確認したので維持**。cto は「requirements_auditor が❌を1件でも出せば O-7 を3へ下げる」と条件付けていたが、round1・round2 とも❌（未充足）は0件だった。`minimum-requirements-checklist.md` の自己申告（44✅/2⚠️/0❌）は over-claim ではなかったと判定する。

### 最終合否についての立場（再表明）

**合格**。与件 §7・§2・§6 は実コードで全項目充足を確認し、他レンズが発見した課題（E2E の CI 非自動化、`next/image` 不使用、`app/` の重複、セキュリティ medium 2件）はいずれも medium 相当の改善余地であり、与件必達項目の未充足や critical/high のセキュリティ欠陥には該当しない。「対象外」領域への拡張（OAuth・Gem Index）も必達動線を侵食しておらず、与件優先の原則（D-2）を守った上での加点材料として扱ってよい。round1 の立場から変更なし。

### `cto` — 反論
<sub>2026-08-24T12:13:12+09:00</sub>

# CTO round 2 — 反論と譲歩

前提: 他 5 レンズの round 1 をすべて読んだ。以下、名指しで争う。追加確認は `docs/adr/0009` の 1 ファイルのみ（`grep -n "対象外\|与件\|minimum-requirements\|スコープ" docs/adr/0009-hidden-gem-score-definition.md` → §1.2 への言及ヒット **0 件**）。

---

## 1. requirements_auditor へ — スコープ外機能は「加点」。ただし OAuth と Gem Index は**同格ではない**

### 1-1. まず auditor の判定を受け入れる（concession）

「§7 11/11 充足・§2 全項目・§6 全項目充足、対象外リストに字面上抵触するが必達動線は侵食していない」— この判定を受け入れる。私の round 1 の O-7=5 は「auditor が ❌ を出さないこと」に従属させていたので、**条件は満たされた。O-7=5 を維持する。**

### 1-2. そのうえで CTO としての採点: **加点**（減点にしない）

採用判断でスコープ外実装が減点になるのは、**それが必達項目の犠牲の上に乗っているとき**だけである。順序が全て。auditor が 11/11 を実コードで確認した以上、この提出物は「言われたことを終えてから、その上に積んだ」構造であり、これは減点ではなく **プロダクトオーナーシップの証跡**として読む。

さらに決定的なのは、拡張が**事後の言い訳ではなく事前の意思決定として日付入りで残っている**こと（`open-questions.md` `D-2`・2026-08-17: 「与件は外部与件。受け入れ基準は必達の下限として固定・変更しない。ただし上乗せは自由」）。実務で本当に困るのは **サイレントなスコープ拡大**であって、宣言され・日付が付き・巻き戻せる拡大ではない。ここは後者。

### 1-3. ただし auditor が並べた 2 機能を同格に扱うのは誤り（rebuttal）

auditor の表は OAuth と Gem Index を同じ「字面上抵触」の欄に並べたが、**説明の質が非対称**である。

| 機能 | §1.2「対象外」への言及 | 判定 |
|---|---|---|
| OAuth | `ADR 0012 §3.1` が **「与件 §1.2 の『対象外』は『実装しなくてよい』であって『実装してはならない』ではない」と解釈そのものを明文化**し、誤読リスクまで自覚して README・PRD・ADR の複数箇所に理由を書くことを完了条件にしている | **満点の説明**。これは私が候補者に期待する最上位の振る舞い |
| Gem Index | **`ADR 0009` は §1.2 の「独自スコアリング＝対象外」に一言も触れていない**（grep ヒット 0）。正当化は `D-1`（Phase 2 = IndieGems）/ `D-2` の決定ログ側にしか無い | **説明が一段落ちる**。プロダクトの中核概念を新設する ADR が、与件がそれを名指しで対象外にした事実に触れていない |

これは「作ったこと」の問題ではなく「**同じ規律を最後まで適用していない**」問題である。ADR 0012 でできたことが ADR 0009 でできていない。私の O-7=5 はこれを飲み込んだうえでの評価だが（決定ログ側に根拠は存在するため説明可能性は保たれている）、**auditor の「両者とも同じ扱い」という提示は精度が足りない**と指摘しておく。round 3 の最終表では、この非対称を「Gem Index の ADR に §1.2 への言及を 1 段落追記する」という具体的な改善項目として残すべき。

---

## 2. code_quality へ — 「層分離の一貫性は確認できた」は**軸を 1 本しか見ていない**（rebuttal）

私は「`app/` にオーケストレーションが 3 重複」を層規律違反として挙げ、あなたは O-3=4 で「層分離は徹底され」と書いた。**この食い違いは事実の食い違いではなく、測った軸の違いである。**

### 2-1. あなたの根拠は「import 方向」だけ

あなたの rationale は `domain → infrastructure の逆依存は grep で確認できず`。それは**静的な依存方向**の話で、`tools/check_architecture_boundaries.py`（私も実行し 176 ファイル・違反 0 を確認）が見ているものと同一の軸である。**私が問題にしたのは別の軸＝責務の配置**であり、SSOT が `application-architecture.md:56`（`app/` は薄く保つ）と **:196**（Server Component は「結果を `src/ui/` に渡すだけ。**ロジックを書かない**」）で独立に宣言している規則である。同 doc が :218 で「この規約は機械検査では守られない」と自認しているとおり、**import 方向の合格は責務配置の合格を一切証明しない**。したがって「層分離の一貫性は確認できた」は、証明された範囲を超えた一般化である。

### 2-2. あなた自身の観測が私の指摘を裏付けている

あなたは課題点 2 で `app/[locale]/page.tsx` 549 行・`SearchBody` が「Gem バッジ取得・URL 組み立て・ページネーション・a11y 制御まで内包」「複数の横断的関心事が同居」と書いた。**それは :196 の規則違反そのものである。** あなたはそれを「単一責務の観点で分割余地」＝スタイルの問題として値付けし、私は「宣言した設計規約の不履行」＝規律の問題として値付けした。**事実は一致していて、重み付けだけが違う。** 私は後者を採る。理由は、SSOT に書かれた規則を実装が守っていない状態は、次に入る人が**文書を信じて誤った前提でコードを触る**からで、行数の多寡より害が大きい。

### 2-3. あなたが出した `lookupGemIndexes` は、あなたの結論に逆に効く

あなたは `container.ts:168-177`（「ドメイン判断が無いので usecase 層を新設しない」）を YAGNI 規律の証拠として挙げ、争点 (3) を「過剰だが害はない」と結論した。**判断の質の証拠であることには同意する**（これは私の round 1 の「判断の質そのものは疑っていない」と整合する）。しかし結論には効かない。

- **下から**: `lookupGemIndexes` は composition → port を直に通し、usecase 層を迂回する
- **上から**: 検索の手順（VO 変換 → 枠の消費 → エラー種別への写像）が `app/[locale]/page.tsx:54,81,94,103` / `app/api/search/route.ts:58,64,86` / `app/[locale]/gems/page.tsx:244` の 3 か所に重複し、usecase 層を素通りする

**上下の両方向から迂回されている層は、「過剰だが害のない骨格」ではない。** 現在の充填のされ方において役割を果たしていない層である。ただし——

### 2-4. 譲歩（concession）: 処方箋はあなたの側に寄せる

あなたの証拠（`lookupGemIndexes` の明示的判断・`search-gems.ts` の非統一判断の一貫性）を踏まえ、私の round 1 の言い方を修正する。**是正は「層を削る」ではなく「層に中身を移す」**。`runSearch` 相当（枠の消費順・`DomainError` → `ErrorKind` の写像）を usecase もしくは composition のヘルパへ 1 本化すれば、3 重複・`page.tsx` 549 行・空洞の usecase 層が**同時に**解消する。争点 (3) の私の結論は round 1 から不変 —— **「層の数は適正。問題は過剰設計ではなく配置のズレ」**。あなたの「過剰であり害がある、は支持しない」にも同意する。

### 2-5. もう一つ、あなたと私が別々に見つけた同じパターン

私: 検索オーケストレーションの 3 重複（コードが「`page.tsx` の catch と同じ方針」と自認）。
あなた: `owner/repo` 判定の 3 実装（コードが「前提が違うため共有化しない・別 Issue」と自認）。

**独立に見つけた 2 件の 3 重複が、どちらも「本人が気づき・コメントに書き・Issue へ送っている」。** これは CTO 視点では두 방향の信号である —— 認知は極めて良好（見えていない人は書けない）、クローズは弱い（見えているのに提出時点で残る）。round 3 の最終表では「品質の欠陥」ではなく **「認知はできるが着地させ切らない傾向」** として 1 行残すのが正確だと考える。

---

## 3. security へ — medium 2 件は**合否ラインを動かさない**。ただし 1 件は初日の宿題にする

私の round 1 の降格条件は「critical または high の実害欠陥が実証された場合」。security は **critical/high 0 件**と結論した（`npm audit` 0 vulnerabilities、`NEXT_PUBLIC_` 0 件、`dangerouslySetInnerHTML` 1 箇所のみ・allowlist サニタイズ、`git log --all -p` の全履歴走査で実鍵ヒット無し、redirect_uri は環境変数固定）。**条件は発動しない。**

観点別に CTO の値付けを述べる。

- **CSP / セキュリティヘッダ欠如（medium）** → **合否に効かない。ただし私が入社初日に割り当てる 1 件目。** 理由: 一般論として CSP が無いのは減点しづらいが、**このアプリは第三者の README HTML を描画する**（`readme-section.tsx`）。多層防御が最も費用対効果を持つ唯一の場所で、それが無い。サニタイザの品質が高い（security の検証どおり）ことは、CSP を不要にはしない —— **サニタイザ 1 枚に全賭けしている状態**である。とはいえ「実害の攻撃シナリオ」が提示されていない以上、合格判定を覆す材料ではない。
- **レート制限フェイルオープン（medium）** → **合否に効かない。** これは欠陥というより**可用性を強制力より優先した意図的なトレードオフ**で、`src/composition/rate-limit.ts` に判定順（IP → binding → salt）の理由まで書かれている。security の「アラート連携の証跡がない」は正しいが、**監視基盤を持たない課題提出物に対する要求としては過大**である。実運用に持っていくなら必須の宿題、提出物の採点材料としては不適。
- **CSRF 専用トークン未導入（low）** → 効かない。POST 限定 + `sameSite: 'lax'` + state のタイミングセーフ比較で、現在のエンドポイント集合には実害が無い。

**結論: O-6 は security の 4 を支持する。** 5 でない理由（多層防御の一段の薄さ）に同意し、3 に下げる材料は無い。**合否ラインは動かない。**

---

## 4. qa へ — 「§5 部分充足」と auditor の「11/11」は**矛盾していない**。ただし `D-42` の根拠は実測と合っていない

qa は「`npm run test:e2e` が CI 自動実行されない → 与件 §5 は部分充足」とし、auditor は §7 11/11 充足とした。**両方正しい。** §7 のチェックリスト項目 10 の文言は「主要フローのテストコードが存在し、実行して成功する」であって CI に言及していない。CI 自動実行を要求しているのは §5 の本文（しかも「CI で自動実行**できる状態**とする」＝状態要件であって実施要件ではない）。したがって **§7 は充足、§5 は厳格読みで部分充足** が正しい整理であり、lead はこれを O-1 の減点ではなく O-4/O-8 の減点として処理すべき。

そのうえで CTO として 1 点だけ指摘する。**`D-42` が E2E を CI から外した理由は「1 PR あたりの待ち時間に見合わない」だが、qa の実測はフルスイート 2m17s（112 件）である。** 2 分半は現代の CI では「見合わない」と言える水準ではない。つまり **決定の根拠が実測に更新されていない**。これは私の O-7（説明可能性）に触れる話で、他の決定（ADR 0005 の TTL・ADR 0002 の `D-31` 取り消し追記）が実測や実機検証で更新されているのと対照的である。**合否には効かないが、`D-42` は再決定条件を書くべき決定だった。**

未登録 flaky（`a11y.spec.ts`・単体 `--repeat-each=3` では 3/3 PASS）については qa の O-8 減点を支持する。自己申告した規律（flaky レジストリ）が実態と乖離した実例であり、これは「テストが弱い」ではなく「**運用規律の自己申告が検証で崩れた**」という質の指摘なので、O-8 で正しく値付けされている。

---

## 5. 最終合否の再表明 — **合格**（round 1 から不変）

降格条件の判定:

| 条件（round 1 で宣言） | 結果 |
|---|---|
| ① auditor が §7 に ❌ を 1 件でも出す | **不発**（11/11 充足） |
| ② security が critical / high を実証 | **不発**（0 件。medium 2 / low 1） |
| ③ qa が「E2E がスタブ固定で実装が壊れても緑」を実証 | **不発**（`sp-1.spec.ts` は件数・リンク名・アバター属性まで assert、実際に 1 件落ちた実測あり） |

**私の投票は「合格」。** スコアは **O-2=4 / O-7=5** で round 1 から変更なし。

**私が置く合格ラインの再掲**: 「App Router で与件どおり動くものを作れる」は合格ラインではなく前提。判定は ① 設計判断を他人に説明でき後から再構成できるか ② 自分の規律を機械で守る仕組みに落とせるか ③ 実害あるセキュリティ欠陥を作らないか —— の 3 点。①は ADR の却下案・実機反証・取り消し追記で、②は `check_architecture_boundaries.py` / `check_adr_coverage.py` / `run_checks.sh` で、③は security の検証で、それぞれ満たされた。

**「この人にうちのプロダクトを任せられるか」への答えは Yes。** 検出された弱点（`app/` の厚み・3 重複 2 系統・CSP 欠如・未登録 flaky・`D-42` の根拠陳腐化）は**いずれも「見えていないから起きた」ものではなく「見えているが着地していない」もの**であり、レビューで指摘すれば直る種類である。判断力ではなくクロージングの問題は、採用後に最も直しやすい。

**採用時に条件として伝える 3 件**（合否とは切り離した onboarding 課題）: (a) `runSearch` 相当の usecase 層への引き上げ（3 重複の解消と `page.tsx` 分割を同時に達成）(b) CSP の導入（README HTML 描画があるため優先）(c) `ADR 0009` に §1.2「独自スコアリング対象外」への言及を追記し、OAuth（ADR 0012 §3.1）と同じ説明水準に揃える。

### `security` — 反論
<sub>2026-08-24T12:13:14+09:00</sub>

## Round 2: 自己反証・他レンズへの応答

### 1. medium①（CSP/セキュリティヘッダ欠如）への自己反証 → **medium から low へ格下げする**

到達経路を具体的に検証した結果、**実害に到達する経路を示せなかった**ため自ら格下げする。

- このアプリで `dangerouslySetInnerHTML` を使う箇所は `src/ui/readme-section.tsx` の 1 箇所のみで、`sanitize-html` の allowlist は `script`/`style`/`on*`/`javascript:`/`data:` を全て排除し、`parseStyleAttributes: false` で CSS 解釈経路自体を切っている（round1 で確認済み）。CSP が防ぐべき「サニタイザをすり抜けた script 実行」を、**実際にバイパスできるペイロードを round1・round2 のいずれでも作れなかった**（新規のバイパス実験はこのラウンドでは実施していない。「試して失敗した」ではなく「試していない」ことは正直に書く）。
- 仮にサニタイザにバイパス（一般論としてこのクラスのライブラリに mXSS 系の既知バグが過去にあったのは事実）があったとしても、**被害の天井が低い**: セッション Cookie は `httpOnly: true`（`session-cookie.ts:80`）で `document.cookie` から読めず、トークンをレスポンスへ反映するエンドポイントも無い（`app/api/search/route.ts` は `ErrorKind` のみ返す）。XSS が悪用できるのは同一オリジンへの ambient cookie 付き fetch だが、状態変更エンドポイントは `/api/auth/logout`（POST・ログアウトさせる程度）のみで、検索 API を叩いても被害者自身のレート枠を消費させる以上の実害がない。
- 結論: **CSP 欠如は「多層防御の 1 層が無い」という設計上の緩さとしては事実**だが、「サニタイザのバイパスを実際に作れる」「作れた場合に金銭的・情報漏洩的な実害がある」の両方を実証できていないため high へ上げる材料はない。medium で維持する根拠も薄いと判断し、**low へ格下げ**する。X-Frame-Options 欠如（clickjacking の土台）についても、GitHub 側の authorize 画面が実際にフレーム埋め込みを防いでいるかは本セッションで **未検証**（`github.com` への到達確認はしていない）ため、round1 の「実害は限定的」という記述はこの未検証を明示すべきだった。事実として言えるのは「このアプリ自身は X-Frame-Options を出していない」までであり、それ以上の推測は取り下げる。
- 依然として **direction としては直すべき**（CSP・X-Frame-Options・X-Content-Type-Options は実装コストが低く、多層防御として明確にプラス）。ただし「未対応=medium 減点」ではなく「未対応=low 減点＋改善提案」に改める。

### 2. medium②（レート制限フェイルオープン）への自己反証 → **medium から low へ格下げする（ADR/運用手順の裏取り済み）**

round 2 の許可範囲内で `docs/03_design/infrastructure/cloudflare-infrastructure.md` を確認した（争点決着に不可欠な 1 箇所として）。

- **意図的なトレードオフであり、「欠陥」ではない**: 同ファイル `§209` が Cloudflare Rate Limiting binding 自体を「per-colo・eventually consistent・厳密な回数保証向けではない」と明記しており、この binding を fail-closed の根拠にすること自体が過剰な信頼になる。フェイルクローズにした場合の可用性リスク（binding 障害・salt 未設定時に検索という **MVP の中核機能** が全ユーザーに 429 を返す）と比較すると、フェイルオープンは「壊れやすい二次防御のために本体機能を止めない」という妥当な設計判断である。
- **「監視に繋がっていない」という round1 の指摘は不正確だった**: 同ファイル `§7.2.1`（748 行目周辺）に **デプロイ時の手動検証手順**が明記されている——① `wrangler secret list` で既存 secrets 名一覧を記録 → デプロイ後に再実行して突合、② 検索・Gem 一覧の両経路へ実際に連続アクセスして制限応答が返ることを確認（キー接頭辞が別枠のため両方必須）。これは `console.warn` 頼みの無音設計ではなく、**salt 未解決時にフェイルオープンでエラーにならないことを見越した上で、動作確認手順として運用手順に組み込んでいる**（同ファイル 748 行「フェイルオープンでエラーにならないため、動作で確かめないと気づけない」という自己認識付き）。
- 残る懸念は 1 点のみ: この検証は **デプロイ時の 1 回限りの手動手順**であり、継続的な自動アラート（例: salt 未設定を検知したら Slack 通知）ではない。再デプロイ・secrets のロールオーバー時に手順が飛ばされれば、次の salt 消失には気づけない。この残差だけを理由に **low として残す**（medium から格下げ）。

### 3. cto / frontend / code_quality の投稿で楽観的すぎる評価があるか

名指しで断定できる**誤り**は見つからなかった（結論を覆すような楽観視は無い）が、**根拠づけが片手落ちな箇所を 1 件**指摘する。

- **frontend**: 「デバウンス未実装だが `SearchForm` は `method="get"` のネイティブフォーム送信のみで、入力のたびに API を呼ぶ経路が存在しない」（round1 課題点 4）。この結論自体は正しいが、根拠が「ブラウザの UI からは連打できない」という**正直なユーザー視点のみ**であり、「`curl`/スクリプトで直接 `GET /api/search` を叩く敵対的クライアント」を考慮していない。もしサーバー側のレート制限（`enforceSearchRateLimit`）が存在しなければ、この frontend の楽観的結論はそのまま脆弱性の見落としになっていた。実際には security レンズが確認した `src/composition/rate-limit.ts` のサーバー側強制があるため **結論は結果的に正しい**が、O-1/O-5 担当のレンズ単独では「連打対策＝完了」と誤読されるおそれがある評価だった、という点は指摘しておく。
- **cto**: round1 §3(1)「app/ 層にオーケストレーション（レート制限強制含む）が 3 箇所に重複している」という指摘は、アーキテクチャ観点だが **セキュリティ観点からも正しく危険**（4 箇所目のエントリポイントが将来追加されたとき `enforceSearchRateLimit` の呼び出し忘れが起きうる）。cto はこれを O-2 の設計逸脱として critical 寄りに評価しており、楽観視ではなくむしろ security の medium②判定を裏付ける材料になっている。楽観的というより、cto の指摘のほうが自分の round1 評価より辛口だった。
- **code_quality**: `oauth.ts` の `response.json() as AccessTokenResponse`（GitHub トークンエンドポイント応答の無検証キャスト）を「境界での明示的な受け渡しに限定され安全」と評価しているが、これは `!data.access_token` の falsy チェックのみに依存しており zod 等のスキーマ検証は無い。実害は「GitHub 自身が返す固定オリジンの応答」である限り低いが、"危険な as は 0 件" という総括にこの 1 件を含めなかったのはやや楽観的。ただし OAuth トークンエンドポイントの応答形状は攻撃者が制御できないため、O-6 の減点対象にするほどの実害はないと判断する（low未満・記録のみ）。

### 4. 最終合否の再表明

**critical/high のセキュリティ欠陥は round 1・round 2 を通じて 1 件も実証できなかった。これは確定情報として明言する。**

自己反証の結果、round1 の medium 2 件はいずれも **low へ格下げ**する（CSP＝実害到達経路を示せず、httpOnly Cookie が被害上限を抑えている／レート制限フェイルオープン＝ADR・運用手順で裏取りできる意図的トレードオフで、デプロイ時検証手順まで存在する）。残るのは low 3 件（CSP・X-Frame-Options 欠如／レート制限監視の手動依存／CSRF 専用トークン未導入）のみで、いずれも「今すぐ実害に到達しない、直せば良くなる改善項目」。

**O-6 スコアを 4/5 から見直す必要はない**（medium→low の格下げは減点幅を小さくする方向であり、5 に上げるほどの模範性でもない——CSP 等の基本的なヘッダ設定を最初から入れておけば防げた緩さは事実として残る）。**最終合否についての自分の立場は round1 から変更なし: O-6 単体は条件付き合格〜合格の間。全観点横断の最終合否は synthesizer に委ねるが、security 観点を理由に不合格・条件付き合格へ引き下げる実証済みの根拠は無いことを明言する。**

## ラウンド 3

### `lead` — 合意
<sub>2026-08-24T12:14:21+09:00</sub>

# lead 統合（合意点・対立の決着）

## 決着した対立点

| 争点 | 決着 | 決め手 |
|---|---|---|
| (1) 与件 §7 の 11 項目は本当に全部充足か | **11/11 充足**（未充足・部分充足 0） | requirements_auditor が実コードで 1 項目ずつ裏取り。frontend が独立に項目 1〜9 を裏取りして一致。qa・cto の指摘（CI 非自動実行・画像最適化・app/ 重複）は §7 チェックリストの文言外であることを 3 者が確認して切り分け完了 |
| (2) 与件 MVP に対する上乗せ（OAuth・Gem Index・i18n・Workers 運用）は加点か減点か | **加点（条件付き）** | `D-2`（与件は必達の下限・上乗せは自由）と `ADR 0012 §3.1`（§1.2「対象外」は「実装してはならない」ではないという解釈の明文化）が**事前の意思決定として記録**されている。かつ未ログイン・バッジ非表示でも全機能が成立し、`sort=gem-index` を検索主軸に採用していない（必達動線を侵食していない）。auditor が round2 でこの結論を補強 |
| (3) 層分離はこの規模で過剰か | **層の数・コストは適正。問題は「過剰」ではなく「配置のズレ」** | ポート総量 217 行（src の 2.8%）・7 ポート中 6 つに実消費者・`check_architecture_boundaries.py` で 176 ファイル違反 0。code_quality が round2 で「過剰」の表現を撤回し cto の枠組みを採用（合意成立） |
| (4) テストは数だけで実効性が低いのではないか | **実効性は高い。ただしテスト密度に非対称がある** | vitest 960/960 PASS・playwright 111/112。`mapper.test.ts` の fail-closed 検証、`search-keyword.test.ts` の過剰拒否回帰、`overflow-guard.spec.ts`（本番バグを受けて 320px の敵対的フィクスチャを追加）など、スタブ頼みの「常に緑」構造ではないことを実測で確認。一方 qa が round2 で、重複した 3 実装のテスト密度が非対称（route.ts は 7 種フル網羅／gems/page.tsx は 4 件のみ／page.tsx はユニットなし）であることを実証 |
| (5) 実害あるセキュリティ欠陥はあるか | **critical / high はゼロ（確定）** | security が round2 で自己反証を実施し、round1 の medium 2 件（CSP 欠如・レート制限フェイルオープン）をいずれも **low へ格下げ**。実害到達経路を示せず、フェイルオープンは ADR/運用手順で意図的トレードオフと裏取りできたため |
| (6) ドキュメント量は加点か減点か | **製品ドキュメント（46 ファイル・12,943 行）は加点、AI 運用ハーネスは中立** | 索引・目次・チェックリスト直行リンクで「全部読ませない」導線が設計され、`check_adr_coverage.py` で機械的に守られている。ハーネスは与件 §6「AI 利用の方法と範囲」への実証付きの応答であり、一方的な減点にはしない |
| (7) 最終合否 | **合格** | 6 役の立場: 合格 2（cto・requirements_auditor）／合格寄り 1（frontend）／条件付き合格 3（qa・code_quality・security）。条件として挙がった項目はいずれも「Issue 化して合格」水準（未実装・欠陥ではなく磨き込み） |

## 残った真の課題（議論を経ても否定されなかったもの）

1. **`app/` 3 エントリポイントへのオーケストレーション重複**（cto 指摘 → code_quality が事実として承認 → qa がテスト密度の非対称で回帰リスクを実証）。宣言した「`app/` は薄く・ロジックを書かない」規則に対する実装の逸脱であり、`check_architecture_boundaries.py` は import 方向しか見ないため検出できない。
2. **E2E が CI（GitHub Actions）の自動実行対象外**（`D-42` による意図的判断だが、与件 §5 後段の文言は字義通りには未充足）。
3. **未登録の flaky 1 件**（`a11y.spec.ts`。`flaky-tests.md` に未登録で、自己の規律が実態と乖離）。
4. **セキュリティヘッダ（CSP 等）の不在**（low・多層防御の 1 層欠如）。
5. **`RateLimitPort` が消費者ゼロの名目上の抽象**（14 行・唯一の実 YAGNI 違反）。
6. **ドキュメント⇄実装ドリフト 2 件**（`src/domain/services/` の記載と実体不一致、`app/` を薄く保つ規則）。

## 議論で否定され、最終結果に残さないもの

- 「レスポンシブが実機未検証」（frontend round1）→ auditor が `overflow-guard.spec.ts` の 320px 実ブラウザ検証を提示、frontend が撤回。
- 「危険な `as` は 0 件」（code_quality round1）→ 自己反証で「攻撃者が制御可能な値への未検証 cast は 0 件、信頼済み外部（GitHub 公式 API）応答への軽量 cast が 3 件」へ精度訂正。
- 「CSP 欠如・レート制限フェイルオープンは medium」（security round1）→ 自己反証で low へ格下げ。
- 「層分離は過剰」（code_quality round1）→ 撤回。
- 「§7 に ❌ が出れば O-7 を 5→3」（cto round1 の条件）→ ❌ 0 件のため発火せず。

> 注記: cto の round 2 反論は本統合の時点で未着。ただし cto が round 1 で明示した降格条件（① auditor が §7 に ❌ を出す ② security が critical/high を実証）はいずれも不発であることが round 2 で確定しており、cto の立場「合格」は維持される前提で統合した。

### `lead` — 判定
<sub>2026-08-24T12:15:24+09:00</sub>

{
  "overall": {
    "result": "合格",
    "total_score": "34 / 40",
    "summary": "与件（§7 受け入れ基準 11 項目・§2 技術要件・§6 ドキュメント要件）は実コードでの裏取りにより全項目充足し、critical / high のセキュリティ欠陥はゼロ。設計判断が ADR と決定ログで後から再構成でき、依存規則・ADR 索引・品質ゲートが機械検査で守られている点は、技術課題の期待水準を明確に上回る。残る課題（app/ へのオーケストレーション重複・E2E の CI 非自動化・未登録 flaky 1 件）はいずれも Issue 化して着手できる磨き込みであり、合格を覆す欠落ではない。",
    "expectation_baseline": "「Next.js App Router で与件どおり動くものを作れる」は合格ラインではなく前提。合格判定は ① 与件充足の上で設計判断を他人に説明でき後から再構成できるか ② 自分の設計規律を機械で守る仕組みに落とせるか ③ 実害あるセキュリティ欠陥を作らないか の 3 点で行った。"
  },
  "scores": [
    {"id": "O-1", "name": "与件充足", "score": 5, "rationale": "§7 の 11 項目を requirements_auditor と frontend が独立に実コードで裏取りし全項目充足で一致。§2 技術要件（Next.js 16.3.1 / App Router のみ / GET /search/repositories / TypeScript）も充足。"},
    {"id": "O-2", "name": "アーキテクチャ設計", "score": 4, "rationale": "依存方向は機械検査で 176 ファイル違反 0、ポート総量 217 行（src の 2.8%）で肥大化なし。一方で宣言した「app/ は薄く」の規則を実装が破り、同一手順が 3 エントリポイントに重複。"},
    {"id": "O-3", "name": "コード品質・保守性", "score": 4, "rationale": "any 0 件・非 null アサーション 0 件・tsc 0 エラー・eslint 0 エラー。値オブジェクトと ErrorKind の一貫運用。減点はコメント密度と内部ジャーゴンの漏出、page.tsx 549 行の肥大化、意図的に残された 3 重実装。"},
    {"id": "O-4", "name": "テスト・品質保証", "score": 4, "rationale": "vitest 960/960 PASS（46s）、playwright 111/112。fail-closed・境界値・過剰拒否回帰まで突く実効性の高いテスト。減点は未登録 flaky 1 件と、重複 3 実装のテスト密度の非対称。"},
    {"id": "O-5", "name": "非機能（性能・a11y・エラー処理）", "score": 4, "rationale": "エラー 7 種の判別と role 使い分け、URL への検索条件反映、Suspense と aria-live の設計は商用水準。減点は next/image 不使用（ADR 0013 の法務判断で正当化されるが Next.js 標準機構は未使用）。"},
    {"id": "O-6", "name": "セキュリティ", "score": 4, "rationale": "critical/high ゼロ。JWE セッション暗号化・オープンリダイレクト対策・timing-safe な state 比較・allowlist 方式の README サニタイズ・HMAC 化レート制限キー・検索式インジェクション対策を実コードで確認。npm audit 0 件。減点はセキュリティヘッダ（CSP 等）の不在。"},
    {"id": "O-7", "name": "ドキュメント・説明可能性", "score": 5, "rationale": "ADR 15 本に却下案・実機検証による反証・決定の取り消し追記があり、決定ログ D-1〜D-42 と README 索引が check_adr_coverage.py で機械的に守られている。与件 §6 の要求も全項目充足。自己申告（44 ✅ / 2 ⚠️ / 0 ❌）は over-claim ではなかった。"},
    {"id": "O-8", "name": "開発プロセス・運用", "score": 4, "rationale": "二層の品質ゲート（CI の高速ゲート + run_checks.sh の 41〜42 項目）が文書と実装で一致し、PR 前の機械証跡がフックで強制されている。減点は CI 自動実行が 42 件中 4 件に留まり、大半がセッション実行に依存する構造。"}
  ],
  "critical_findings": [
    {"severity": "medium", "finding": "app/ 3 エントリポイントに同一のオーケストレーション手順（値オブジェクト変換 → レート制限強制 → DomainError の種別判別）が重複し、宣言した層規律に反している。3 実装の挙動が同一であることを保証する契約テストがない", "location": "app/[locale]/page.tsx:54-108 / app/api/search/route.ts:58,64,86 / app/[locale]/gems/page.tsx:244-246", "impact": "1 箇所のエラー種別マッピングを直しても他 2 箇所の同種バグが検知されずに残りうる（テスト密度が非対称: route.ts は 7 種フル網羅、gems/page.tsx は 4 件、page.tsx はユニットなし）"},
    {"severity": "medium", "finding": "E2E（Playwright）が GitHub Actions の自動実行対象外。与件 §5 後段「CI で自動実行できる状態とする」を字義通りに取れば E2E 側は未充足", "location": ".github/workflows/quality-checks.yml / D-42", "impact": "主要フロー検証の主力が PR ごとに自動実行されない。D-42 の根拠「1 PR あたりの待ち時間に見合わない」は実測 2m17s と整合しない"},
    {"severity": "low", "finding": "未登録の flaky が実測で 1 件（a11y.spec.ts の一覧画面）。flaky-tests.md に該当エントリなし", "location": "e2e/a11y.spec.ts:16", "impact": "自己の規律（レジストリに載っていなければ本物の失敗として扱う）が実態と乖離している"},
    {"severity": "low", "finding": "セキュリティヘッダ（CSP / X-Frame-Options / Referrer-Policy / HSTS）が未設定", "location": "next.config.ts（headers() 未定義）", "impact": "サニタイズは堅牢だが多層防御の 1 層が欠ける。実害到達経路は示せず low"},
    {"severity": "low", "finding": "RateLimitPort が実消費者ゼロの名目上の抽象（合成側は具象を直接 import）", "location": "src/domain/ports/rate-limit-port.ts", "impact": "自ら課した YAGNI 規律の適用漏れが 1 件（14 行なので影響は小）"},
    {"severity": "low", "finding": "ドキュメント⇄実装のドリフト 2 件", "location": "docs/03_design/architecture/application-architecture.md:71（src/domain/services/ は実在しない）・:196（app/ にロジックを書かない規則の不履行）", "impact": "SSOT を名乗る文書が実装と食い違い、読み手が設計を誤解する"}
  ],
  "debates": [
    {"issue": "(1) 与件 11 項目の充足", "conclusion": "11/11 充足（未充足・部分充足 0）", "rationale": "2 レンズが独立に実コードで裏取りし一致。他レンズの指摘は §7 チェックリストの文言外", "rejected": "「CI 非自動実行／画像最適化／app/ 重複を理由に部分充足へ落とす」→ いずれも §7 の項目文言に含まれず、O-4 / O-5 / O-2 の減点として切り分け"},
    {"issue": "(2) スコープ上乗せは加点か減点か", "conclusion": "加点（条件付き）", "rationale": "D-2 と ADR 0012 §3.1 で事前に解釈を確定し、必達動線を侵食しない設計（未ログインでも全機能成立・sort=gem-index を検索主軸に採用せず）", "rejected": "「対象外領域への実装はそれ自体が要件逸脱」→ 与件原文は「対象外」であって「禁止」ではない。ただし OAuth に比べ Gem Index 側は §1.2 への言及がなく説明水準が非対称という指摘は残す"},
    {"issue": "(3) 層分離は過剰か", "conclusion": "層の数・コストは適正。問題は配置のズレ", "rationale": "ポート 217 行・7 中 6 に実消費者・機械検査違反 0。usecases が 20〜23 行の委譲に留まる一方 app/ に手順が漏れている", "rejected": "「この規模に層分離は過剰」→ code_quality が round2 で撤回"},
    {"issue": "(4) テストの実効性", "conclusion": "実効性は高い。ただしテスト密度に非対称がある", "rationale": "スタブ固定で常に緑になる構造ではないことを実測（1 件の失敗発生・具体 assert・本番バグ由来の敵対的フィクスチャ追加）", "rejected": "「E2E はスタブ頼みで回帰検知になっていない」→ 実証されず"},
    {"issue": "(5) 実害あるセキュリティ欠陥", "conclusion": "critical / high はゼロ", "rationale": "security が自己反証を実施し round1 の medium 2 件を low へ格下げ", "rejected": "「CSP 欠如は medium 以上」→ 実害到達経路を示せず low"},
    {"issue": "(6) ドキュメント量", "conclusion": "製品ドキュメントは加点、AI 運用ハーネスは中立", "rationale": "索引・目次・チェックリスト直行リンクで読み手負荷を制御し、機械検査で索引が守られている", "rejected": "「量そのものが読み手負荷で減点」→ 全部読ませる構造ではないため不成立"},
    {"issue": "(7) 最終合否", "conclusion": "合格", "rationale": "6 役の立場は合格 2 / 合格寄り 1 / 条件付き合格 3。条件はいずれも Issue 化して着手できる磨き込みで、与件必達項目の欠落でも critical 欠陥でもない", "rejected": "「不合格」を主張したレンズはゼロ"}
  ]
}
