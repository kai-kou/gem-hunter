# gem-hunter

star の多さでは埋もれてしまう「実際に使われている OSS」を、個人開発者が見つけられるようにする検索プラットフォーム。

> 旧称: IndieGems（[`Q-12`](./docs/02_requirements/open-questions.md) により `gem-hunter` に統一）

## 開発（ローカル）

Node.js 22 以上が必要（wrangler 4.x の要件）。

```bash
npm ci
npm run dev          # http://localhost:3000 で検索画面が開く
npm test             # ユニット・結合テスト（Vitest）
npm run lint         # ESLint
npm run format       # Prettier
```

GitHub App の資格情報（[`.env.example`](./.env.example)）を設定しなくても動作する（その場合 GitHub API を未認証で叩くためレート枠が狭くなる）。

### 技術スタック

| 領域 | 採用 |
|---|---|
| フレームワーク | Next.js 16（App Router・React Server Components） |
| UI | Tailwind CSS v4 + shadcn/ui（Radix UI・[ADR 0001](./docs/adr/0001-ui-stack.md)） |
| 実行環境 | Cloudflare Workers（`@opennextjs/cloudflare`・[ADR 0002](./docs/adr/0002-cloudflare-workers-infrastructure.md)） |
| テスト | Vitest 4 + Testing Library + MSW 2（[テスト戦略](./docs/04_development/testing-strategy.md)） |

層と依存規則は [アプリケーションアーキテクチャ](./docs/03_design/architecture/application-architecture.md) が正本（`python3 tools/check_architecture_boundaries.py` で機械検証する）。

## ドキュメント

プロジェクトのドキュメントは [`docs/`](./docs) 配下で管理する。構成の詳細は [`docs/README.md`](./docs/README.md) を参照。

- **要件定義書（正本）**: [`docs/02_requirements/prd.md`](./docs/02_requirements/prd.md)
- 決定ログ・論点リスト: [`docs/02_requirements/open-questions.md`](./docs/02_requirements/open-questions.md)
- 与件（最低要件定義）: [`docs/02_requirements/minimum-requirements.md`](./docs/02_requirements/minimum-requirements.md)
- ミッション・KPI: [`docs/project-mission.md`](./docs/project-mission.md)
- 初期コンセプト: [`docs/00_concept/initial-concept.md`](./docs/00_concept/initial-concept.md)

## 設計上の判断

> 与件（[`minimum-requirements.md`](./docs/02_requirements/minimum-requirements.md) §6）が求める「設計上の判断・工夫した点」を記載する。各項目の全文と経緯は [決定ログ](./docs/02_requirements/open-questions.md)（`D-n`）を参照。

### リリースサイクル: 常設の dev 環境を持たない（`D-21`）

デプロイは **PR ごとのプレビュー環境**（Cloudflare Workers の version + preview alias）と **`main` = 本番** の 2 つだけで構成し、「dev ブランチ = 常設プレビュー環境」を **意図的に置いていない**。

- **dev を置いても検証が増えない**: 本プロジェクトは単一開発者 + AI の自律ルーティンで開発が自走するため、dev を確認する人間がいない。dev には実トラフィックも通らないため、PR 時点で通過済みの CI と同じ検証をもう一度走らせるだけの環境になる。得られるのはリードタイムの増加と、「誰が・いつ dev → `main` へ昇格させるか」という新しい判断点だけになる
- **本番直結のリスクは別の手段で塞ぐ**: 複数 PR を積み上げた「合成状態」が本番で初めて動くリスクは実在する。これは dev を挟んでも（昇格の判断主体が未定義な限り）同じ問いが 1 段上に移動するだけなので、**`main` マージ後にテストを走らせ、失敗したら本番デプロイに進ませない CI ゲート** で塞ぐ
- **将来の追加を判断する条件も決めてある**: 方針そのものは確定済みで、`M-4`（第三者へ公開するかの判断ゲート・[`roadmap.md`](./docs/02_requirements/roadmap.md)）の時点で **追加導入の要否だけ** を判断する。対象は OAuth 経路の事前検証用環境（プレビューは PR ごとに URL が変わりコールバック URL を登録できない）と、段階的デプロイの 2 つ

以上の理由から、長寿命の中間ブランチを増やすより、trunk-based を維持したうえで検証を CI と本番投入の制御に寄せる方が、この規模・この運用体制では変更のリードタイムと安全性を両立できると判断した。**検討した代替案（`[env.dev]` 別 Worker・GitFlow・2 段マージの自動昇格など）と却下理由は [ADR 0004](./docs/adr/0004-release-cycle-trunk-based.md) に記録している。**
