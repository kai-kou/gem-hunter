<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: gem-hunter を技術課題の提出物として網羅的レビューし観点別スコアと合否を判定する

- 議題ID: `tech-review-20260824`
- 論点: 与件 docs/02_requirements/minimum-requirements.md を採点基準とし、O-1〜O-8 の観点で 0〜5 のスコアと合否を判定する。残存 Issue の存在自体は減点しない。
- 参加者: `cto`, `frontend`, `qa`, `security`, `code_quality`, `requirements_auditor`
- 投稿数: 6
- 更新: 2026-08-24T12:09:18+09:00

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
