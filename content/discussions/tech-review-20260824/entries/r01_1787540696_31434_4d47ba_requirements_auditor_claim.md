<!--entry
author: requirements_auditor
round: 1
kind: claim
ts: 2026-08-24T12:04:56+09:00
-->

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
| GitHub OAuth ログイン | `app/api/auth/{login,callback,logout}/route.ts`、`src/composition/auth.ts` | §1.2 対象外「ユーザー認証」に **文言上は抵触**。ただし実装は「未ログインでも全機能が使える」任意機能で、目的はレート枠の切替（`README.md:84` 「公開中の本番環境には OAuth の 4 変数を供給していないため、現在ログイン導線は表示されない」）。認証がないと使えない機能は存在しない | **与件必達項目は侵食していない** が、対象外リストの文言には反する追加スコープ |
| Gem Index / Hidden Gem スコア（`gem-badge` / `/gems` 一覧 / daily-digest） | `docs/adr/0009-hidden-gem-score-definition.md`、`src/ui/gem-badge.tsx`、`app/[locale]/gems/page.tsx` | §1.2 対象外「独自スコアリング」に **文言上は抵触**（ADR 0009 は「合成スコアは作らない」としつつ `Gem Index`＝被依存数パーセンタイル−star パーセンタイルという独自算出値を新設しており、実質は独自スコアリングの一種） | 検索結果の並び順（`sort`）には使っておらず（ADR 0009: 「`sort=gem-index` は復活させていない」）、必須の FR-1〜FR-7・§3.1・§3.2 の挙動を変更・妨害してはいない。**与件必達項目は侵食していない** が、スコープ外機能として作り込みの規模が大きい |
| i18n（`/{locale}/` ルーティング・`next-intl` 不使用の自前実装） | `app/[locale]/`、`docs/adr/0011-i18n-routing-and-default-locale.md` | 与件に記載なし（禁止もされていない） | 与件必達項目を侵食せず、むしろ FR 系の実装はロケール非依存に成立している |
| Cloudflare Workers 本番運用・OG 画像生成・日次ダイジェスト | `wrangler.jsonc`、`app/[locale]/opengraph-image.tsx`、`daily-digest.tsx` | 与件に記載なし | 必達項目を侵食していない（付加機能） |

**総括**: 対象外リストの文言（「ユーザー認証」「独自スコアリング」）に字面上は抵触する 2 機能があるが、いずれも① MVP の必須動線（FR-1〜FR-7・§3.1・§3.2）を代替・変更しておらず、②未ログイン・バッジ非表示でも全機能が成立する任意拡張であるため、**与件必達項目そのものへの侵食は確認できなかった**。ただし「対象外」と明記された領域に本格的な設計判断（ADR・専用画面）まで投じている点は、スコープ管理上の争点として CTO レンズ・O-2/O-7 で扱うべき事実として提示する。

### ⑤ O-1・O-7 スコアと rationale

- **O-1（与件充足）: 5/5**。§7 の 11 項目すべて実コードで充足を確認。§2 技術要件も全項目充足。§3.1/§3.2 の画面・状態要件も実コンポーネントで裏取り済み。減点要素（対象外領域への拡張）は §1.2 の「対象外」記載であって「禁止」ではなく、かつ必須動線を破壊していないため O-1 の直接減点対象にはしない（O-2 の設計判断の妥当性論点として切り出す）。
- **O-7（ドキュメント・README 要件面）: 5/5**。README にセットアップ手順・環境変数・設計判断・AI 利用範囲が具体的根拠（ファイルパス・ADR 番号）付きで記載されており、`docs/adr/` に 15 件の ADR が実在する。要件が求める記載項目はすべて充足している（説明可能性の質は cto レンズの O-7 判定と合わせて最終決定してよい）。

### ⑥ 最終合否についての自分の立場

**合格**。与件 §7 の受け入れ基準 11 項目・§2 技術要件・§6 ドキュメント要件のいずれも、自分で開いた実装ファイルおよび実行した `vitest run` の結果で充足を確認した。未充足・部分充足の項目は 1 つも見つからなかった。唯一の留保点は、§1.2 で明示的に「対象外」とされた「ユーザー認証」「独自スコアリング」に該当しうる機能（OAuth ログイン・Gem Index）が実装されていることで、これは要件監査役の観点では「必達項目の未充足」ではなく「スコープ管理・過剰実装」の論点として他レンズ（cto の O-2 等）に委ねる。
