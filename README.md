# gem-hunter

star の多さでは埋もれてしまう「実際に使われている OSS」を、個人開発者が見つけられるようにする検索プラットフォーム。

キーワードで GitHub のリポジトリを検索して詳細（統計・README）を読める。トップページのキーワード未入力の状態では、検索結果の代わりに **star の数のわりに多くのパッケージから使われている** リポジトリを日次で入れ替わるダイジェスト「今日の Gem」として並べる。日本語・英語に対応し、アカウント登録なしで全機能を使える。

- **使ってみる**: <https://gem-hunter.kinamocchi-tech.workers.dev/ja>（[English](https://gem-hunter.kinamocchi-tech.workers.dev/en)）
- **紹介ページ**（スクリーンショット・できること・FAQ）: <https://kai-kou.github.io/gem-hunter/>（ソースは [`site/`](./site)）

> **この README で分かること**: [動かし方](#開発ローカル) / [環境変数](#環境変数) / [設計上の判断](#設計上の判断) / [AI の利用範囲](#ai-を利用した範囲と方法nfr-31) / [ADR 一覧](#技術的意思決定の記録adr)

> 旧称: IndieGems（[`Q-12`](./docs/02_requirements/open-questions.md) により `gem-hunter` に統一）

## 開発（ローカル）

Node.js 22 以上が必要（wrangler 4.x の要件）。

```bash
npm ci
npm run dev          # http://localhost:3000 で検索画面が開く
npm test             # ユニット・結合テスト（Vitest）
npm run test:e2e     # E2E テスト（Playwright。スタブ API + アプリを自動起動、外部ネットワーク非依存）
npm run lint         # ESLint
npm run format       # Prettier
npm run check        # Lint/型/vitest/E2E 等をまとめて実行（tools/run_checks.sh）
```

`npm test` / `npm run test:e2e` は環境変数を一切設定しなくても通る（外部 API はモック化されている）。

本リポジトリでは品質チェック・デプロイに GitHub Actions を使わない（[`D-23`](./docs/02_requirements/open-questions.md)）ため、上記を走らせる CI は動いていない。代わりに `npm run check` を実行し、出力される結果表を PR 本文に貼ることが PR 前の唯一の機械的証跡になっている。GitHub Actions は Gem 候補プールの **日次実行 + 週次反映**（[`.github/workflows/gem-pool-refresh.yml`](./.github/workflows/gem-pool-refresh.yml)）にのみ使う。毎日生成・機械 QA まで走らせてパイプラインの健全性を検証し、`main` への反映（PR 作成）は生成物が 7 日以上前のときだけ行う（マージ頻度を抑えて git 履歴コストを避けるため）。

### 環境変数

すべて **任意**。1 つも設定しなくても `npm run dev` は起動し、検索・詳細表示は動作する（その場合 GitHub API を未認証で叩くためレート枠が狭くなる）。本リポジトリに `.env.example` は用意していない。以下の表を参照して `.env.local`（Next.js の規約どおり）に必要な分だけ設定する。

| 変数 | 用途 | 未設定時の挙動 |
|---|---|---|
| `GITHUB_APP_CLIENT_ID` | GitHub App の installation token 取得（[ADR 0003](./docs/adr/0003-github-app-authentication.md)） | 3 変数が揃わない限り未認証で GitHub API を叩く（レート枠が狭い） |
| `GITHUB_APP_INSTALLATION_ID` | 同上 | 同上 |
| `GITHUB_APP_PRIVATE_KEY_PKCS8` | 同上（**PKCS#8 形式** で注入する必要がある） | 同上 |
| `GITHUB_OAUTH_CLIENT_ID` | 任意ログイン（[ADR 0012](./docs/adr/0012-optional-github-oauth.md)） | 下記 `SESSION_ENCRYPTION_KEY` を含む **4 変数が揃わない限り** ログイン導線が静かに無効化される（未ログイン相当の機能はすべて動く） |
| `GITHUB_OAUTH_CLIENT_SECRET` | 同上 | 同上 |
| `GITHUB_OAUTH_CALLBACK_URL` | 同上（デプロイ先ごとに異なる。オープンリダイレクト対策の検証にも使う） | 同上 |
| `SESSION_ENCRYPTION_KEY` | ログイン後のセッション Cookie 暗号化鍵（32 バイトを base64url エンコードした値） | 同上（**本行だけが欠けても** ログイン導線ごと無効化される。表示可否は `src/composition/auth.ts` の `isAuthConfigured()` が 4 変数の AND で判定する） |
| `RATE_LIMIT_SALT` | 自リクエスト間引き（`NFR-7`）でクライアント IP を HMAC 化する際の salt。適用範囲は検索（`/{locale}` / `GET /api/search`）と Gem 一覧（`/{locale}/gems`）。適用経路の正本は [Cloudflare インフラ設計](./docs/03_design/infrastructure/cloudflare-infrastructure.md) §3.3 の表 | **適用経路すべてで** 間引きをしない（フェイルオープン。エラーにも `429` にもならず黙って通る） |

🔵 公開中の本番環境には OAuth の 4 変数を供給していないため、現在ログイン導線は表示されない（未ログインで全機能が使える状態）。

上記はいずれも `src/infrastructure/` 配下の各ファイルが `process.env` から直接読む（秘匿情報を読んでよい層を 1 ファイルに限定する設計・`ARCH-5` / `NFR-22`）。`GITHUB_API_ORIGIN` と `GITHUB_OAUTH_ORIGIN` はテスト専用のスタブ切替であり（ループバック宛てのみ有効）、アプリの実行時には使わない。

### 技術スタック

| 領域 | 採用 |
|---|---|
| フレームワーク | Next.js 16（App Router・React Server Components） |
| UI | Tailwind CSS v4 + shadcn/ui（Radix UI・[ADR 0001](./docs/adr/0001-ui-stack.md)） |
| 実行環境 | Cloudflare Workers（`@opennextjs/cloudflare`。本番・プレビュー配信の詳細は [ADR 0002](./docs/adr/0002-cloudflare-workers-infrastructure.md)） |
| テスト | Vitest 4 + Testing Library + MSW 2（ユニット・結合）/ Playwright + axe（E2E）（[テスト戦略](./docs/04_development/testing-strategy.md)） |

層と依存規則は [アプリケーションアーキテクチャ](./docs/03_design/architecture/application-architecture.md) が正本（`python3 tools/check_architecture_boundaries.py` で機械検証する）。ドメインの用語（ユビキタス言語）は [ドメインモデル](./docs/03_design/data-model/domain-model.md) が正本。

## ドキュメント

プロジェクトのドキュメントは [`docs/`](./docs) 配下で管理する。構成の詳細は [`docs/README.md`](./docs/README.md) を参照。

- **要件定義書（正本）**: [`docs/02_requirements/prd.md`](./docs/02_requirements/prd.md)
- 決定ログ・論点リスト: [`docs/02_requirements/open-questions.md`](./docs/02_requirements/open-questions.md)
- 与件（最低要件定義）: [`docs/02_requirements/minimum-requirements.md`](./docs/02_requirements/minimum-requirements.md)
- ミッション・KPI: [`docs/project-mission.md`](./docs/project-mission.md)
- 初期コンセプト: [`docs/00_concept/initial-concept.md`](./docs/00_concept/initial-concept.md)

## 設計上の判断

> 与件（[`minimum-requirements.md`](./docs/02_requirements/minimum-requirements.md) §6）が求める「設計上の判断・工夫した点」を記載する。各項目の全文と経緯は [決定ログ](./docs/02_requirements/open-questions.md)（`D-n`）を参照。

### Hidden Gem を「被依存数に対する star の残差」と定義した（`ADR 0009`）

「知られざる良質な OSS」を測るために独自の合成スコア（保守性・ドキュメント品質・依存シグナルの加重和）を作る構想から出発したが、**作らない** ことにした。

- **1 行で言える定義に絞った**: Gem とは「実際に使われている度合い（被依存数）に対して、注目度（star 数）が不釣り合いに小さいリポジトリ」。`Gem Index` は **被依存数のパーセンタイル順位 − star のパーセンタイル順位** という残差で、重みを持たないぶん「なぜこの順位なのか」を利用者に説明できる
- **健全性は自作しない**: 保守されているかの判定は OpenSSF `criticality_score` / Scorecard に委ね、被依存数は Ecosyste.ms のオープンデータに委ねる。自作すると既存スコアの再実装になり、重み・正規化・再計算頻度が未定のままでは受け入れ条件が書けなかった
- **2 軸を合算しない**: 過小評価度は「並び順」、健全性は「足切り」と役割を分け、1 つの数値に混ぜない
- **効いている範囲を広げない**: 検索結果への適用は一度 **撤去した**（候補プールの被覆率が足りなかった・[`D-33`](./docs/02_requirements/open-questions.md)）が、母集団を 12 レジストリ・62,483 リポジトリへ拡大した実測を受けて [`D-36`](./docs/02_requirements/open-questions.md) で **再導入した**。現在この指標が効くのは ① 日次ダイジェスト「今日の Gem」の並び順 ② 検索結果カードの **Gem バッジ**（並び順は変えない注釈・`SP-18`） ③ 検索語を引き継いだ **Gem 候補の一覧**（`/{locale}/gems` の並び順・`SP-19`）の 3 経路。🔴 **`sort=gem-index`（検索結果そのものの主ソート軸）は復活させていない** — 実測で検索上位 100 件中 68 件に値が無く、値の無い結果に順位を与えられないため（`D-36`）。パーセンタイルの母集団定義・しきい値・配信件数は **意図的に未確定のまま** で、実データを見てから決める（[ADR 0009](./docs/adr/0009-hidden-gem-score-definition.md) §2.3）

検討した代替案と却下理由は [ADR 0009](./docs/adr/0009-hidden-gem-score-definition.md) に記録している。

### リリースサイクル: 常設の dev 環境を持たない（`D-21`）

デプロイは **PR ごとのプレビュー環境**（Cloudflare Workers の version + preview alias）と **`main` = 本番** の 2 つだけで構成し、「dev ブランチ = 常設プレビュー環境」を **意図的に置いていない**。

- **dev を置いても検証が増えない**: 本プロジェクトは単一開発者 + AI の自律ルーティンで開発が自走するため、dev を確認する人間がいない。dev には実トラフィックも通らないため、PR 時点で通過済みの CI と同じ検証をもう一度走らせるだけの環境になる。得られるのはリードタイムの増加と、「誰が・いつ dev → `main` へ昇格させるか」という新しい判断点だけになる
- **本番直結のリスクは別の手段で塞ぐ**: 複数 PR を積み上げた「合成状態」が本番で初めて動くリスクは実在する。これは dev を挟んでも（昇格の判断主体が未定義な限り）同じ問いが 1 段上に移動するだけなので、**`main` マージ後にテストを走らせ、失敗したら本番デプロイに進ませない CI ゲート** で塞ぐ
- **将来の追加を判断する条件も決めてある**: 方針そのものは確定済みで、`M-4`（第三者へ公開するかの判断ゲート・[`roadmap.md`](./docs/02_requirements/roadmap.md)）の時点で **追加導入の要否だけ** を判断する。対象は OAuth 経路の事前検証用環境（プレビューは PR ごとに URL が変わりコールバック URL を登録できない）と、段階的デプロイの 2 つ

以上の理由から、長寿命の中間ブランチを増やすより、trunk-based を維持したうえで検証を CI と本番投入の制御に寄せる方が、この規模・この運用体制では変更のリードタイムと安全性を両立できると判断した。**検討した代替案（`[env.dev]` 別 Worker・GitFlow・2 段マージの自動昇格など）と却下理由は [ADR 0004](./docs/adr/0004-release-cycle-trunk-based.md) に記録している。**

## AI を利用した範囲と方法（`NFR-31`）

本プロダクトは Claude Code（クラウド実行環境）による **自律スプリント運用** で開発している。実際の運用は本リポジトリの `CLAUDE.md` と `docs/rules/` 配下のルール群が正本であり、以下はその要約。

- **スプリント単位の自走**: 1 セッション = 1 スプリントとして、要件ドキュメント（`docs/02_requirements/user-story-map.md` 等）を読んで実装対象を決定し、実装・テスト・PR 作成・レビュー対応・マージまでを自律実行する（`docs/rules/session-sprint-rules.md` / `docs/rules/sprint-development-rules.md`）
- **TDD 主体**: Red（失敗するテストを書く）→ Green（通す最小の実装）→ Refactor の順で実装する。手動での操作確認手順は E2E テスト（Playwright）に写す（`docs/rules/sprint-development-rules.md` `SD-2`）
- **セルフレビュー**: 外部 AI レビュアー（Copilot/Gemini 等）には依頼せず、観点別のフレッシュ文脈セルフレビュー（`.claude/skills/code-review/`）を PR 作成後に必ず実行し、指摘は PR の行単位インラインコメントで記録する
- **PR 作成・マージの自律化**: 実装完了後、確認を挟まずに PR 作成 → セルフレビュー対応 → 自動マージまで進める（本リポジトリの恒久委任・`CLAUDE.md`「PR 作成の完全自律化」）
- **人間が判断する領域**: `main` への直接 push・課金/アカウント設定の変更・新規マイルストーンの追加など、ユーザーの操作・権限が物理的に必要なもの（`docs/rules/user-confirmation-minimization.md` の既約境界 `A-1`〜`A-6`）と、仕様解釈が複数通りあり成果物が変わる分岐（`docs/rules/sprint-development-rules.md` `SD-3`）に限る。それ以外は AI が自律的に判断・実行する
- **定期運用**: PR レビュー監視・リポジトリ衛生（Stale Issue・Orphan PR の解消）・改善提案の起票と実装などを、スケジュール実行（`docs/routines/`）で継続する

## 技術的意思決定の記録（ADR）

`NFR-32` に対応。技術的意思決定は「なぜその選択をしたか / 何を捨てたか」を [`docs/adr/`](./docs/adr) に ADR として記録する。記録すべき主題の一覧は [PRD §12](./docs/02_requirements/prd.md#12-記録すべき-adr) が正本であり、下表はそこへの索引として、各 ADR の見出しから `ADR NNNN: ` を除いたタイトルを転記したもの（転記漏れ・言い換えによる食い違いは `tools/check_adr_coverage.py` が機械検査する）。

| ADR | タイトル（各 ADR の見出しから `ADR NNNN: ` を除いて転記） |
|---|---|
| [0001](./docs/adr/0001-ui-stack.md) | UI スタックに Tailwind CSS v4 + shadcn/ui（Radix UI 明示指定）を採用する |
| [0002](./docs/adr/0002-cloudflare-workers-infrastructure.md) | インフラを Cloudflare Workers（`@opennextjs/cloudflare`）に確定し、wrangler CLI を運用の一次経路にする |
| [0003](./docs/adr/0003-github-app-authentication.md) | サーバー側の GitHub 認証を GitHub App の installation token にする |
| [0004](./docs/adr/0004-release-cycle-trunk-based.md) | リリースサイクルを trunk-based（PR プレビュー + `main` = 本番）に確定し、常設の dev 環境を持たない |
| [0005](./docs/adr/0005-cache-port-yagni-exception-and-ttl.md) | Cache Port を YAGNI の意図的な例外として維持し、TTL 暫定値を確定する |
| [0006](./docs/adr/0006-nextjs16-app-router.md) | Next.js 16 + App Router を採用する |
| [0007](./docs/adr/0007-no-database-client-side-state.md) | DB を持たない設計原則と、状態をクライアント側へ寄せる判断 |
| [0008](./docs/adr/0008-pagination-over-infinite-scroll.md) | `FR-7` でページネーションを選び、無限スクロールを採らない |
| [0009](./docs/adr/0009-hidden-gem-score-definition.md) | Hidden Gem を「被依存数に対する star の残差」と定義し、既存スコアを再実装しない |
| [0010](./docs/adr/0010-no-token-rotation.md) | 複数トークンのローテーションを採用しない |
| [0011](./docs/adr/0011-i18n-routing-and-default-locale.md) | i18n のルーティング設計と既定ロケールを、`next-intl` を不採用として自前実装で確定する |
| [0012](./docs/adr/0012-optional-github-oauth.md) | 任意の GitHub OAuth ログインを、与件が対象外とした認証に上乗せする |
| [0013](./docs/adr/0013-public-operation-under-github-terms.md) | 第三者へ公開して運用する際の GitHub 利用規約上の立場を確定する |
| [0014](./docs/adr/0014-zero-query-daily-digest.md) | キーワード非依存の発見面を日次の有限ダイジェストとして実装する |
| [0015](./docs/adr/0015-ai-generated-visual-assets.md) | AI 生成ビジュアルアセットを透過 WebP のまま配信する |

## ライセンスと権利表示

本リポジトリのコードとドキュメントは [MIT License](./LICENSE) で公開している。

ただし以下は **第三者に権利が帰属し、MIT License の対象外** である（詳細は [`NOTICE`](./NOTICE)）。

| 対象 | 帰属 |
|---|---|
| [`docs/02_requirements/minimum-requirements.md`](./docs/02_requirements/minimum-requirements.md) | 本プロジェクトの **与件（要件定義）**。第三者が作成・提供したもので、設計判断の追跡のために原文のまま収録している。再利用・改変・再配布の許諾は与えていない |
| [`.claude/skills/skill-creator/`](./.claude/skills/skill-creator) | Apache License 2.0（`LICENSE.txt` を同梱） |

`package.json` の `"private": true` は npm レジストリへの誤公開を防ぐためのもので、本リポジトリの公開範囲とは無関係である（本プロダクトはアプリケーションであり、npm パッケージとして配布しない）。
