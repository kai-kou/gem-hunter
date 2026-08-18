# gem-hunter

star の多さでは埋もれてしまう「実際に使われている OSS」を、個人開発者が見つけられるようにする検索プラットフォーム。

> 旧称: IndieGems（[`Q-12`](./docs/02_requirements/open-questions.md) により `gem-hunter` に統一）

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
- **判断を先送りする条件も決めてある**: OAuth 経路の事前検証（プレビューは PR ごとに URL が変わるためコールバック URL を登録できない）と段階的デプロイの要否は、[`roadmap.md`](./docs/02_requirements/roadmap.md) の `M-4`（第三者へ公開するかの判断ゲート）で再判定する

長寿命の中間ブランチを増やすより、trunk-based を維持したうえで検証を CI と本番投入の制御に寄せる方が、この規模・この運用体制では変更のリードタイムと安全性を両立できると判断した。
