# スライド構成: gem-hunter プロジェクト解説

対象読者: 開発者・エンジニア
想定尺: 15〜20 分（17 枚 / 1 枚あたり 60〜70 秒。スライド 13 のみ 90〜100 秒）
作成日: 2026-08-22

> 本ファイルは `content/slides_plan.json`（議論 `project-slides-20260822` の verdict）から
> `scripts/build_outline.py` が生成する。**構成を変えるときは JSON 側を直して再生成する。**

## Slide 1: gem-hunter

- 見出し: gem-hunter
- 本文:
  - gem-hunter
  - star では埋もれる「実際に使われている OSS」を見つける
  - 開発者向け解説 / 2026-08-22
- ビジュアル: 新規生成 new-01（表紙）
- 伝えたい 1 メッセージ: プロダクト名と 1 行の主題を示す
- 出典: docs/project-mission.md ミッションステートメント

## Slide 2: star 順では出てこない OSS を、検索できる

- 見出し: star 順では出てこない OSS を、検索できる
- 本文:
  - キーワードを入れると一覧が出て、カードから詳細ページへ進める
  - 検索条件は URL に乗るので、共有しても戻っても同じ結果が出る
  - 未ログインで全機能が使える（ログインで変わるのはレート枠だけ）
- ビジュアル: 実 UI スクリーンショット shot-01（検索結果一覧）
- 伝えたい 1 メッセージ: まず動くものを見せる（アウトカム先出し）
- 出典: docs/02_requirements/user-story-map.md SP-1〜SP-11 / ADR 0012

## Slide 3: 検索しなくても、その日の Gem が並ぶ

- 見出し: 検索しなくても、その日の Gem が並ぶ
- 本文:
  - トップページの「今日の Gem」は日付をシードに決定論的に選ばれる
  - 出典と鮮度を添えて出す
  - Gem Index を使うのはこのダイジェストだけで、検索結果の並び順には効かない
- ビジュアル: 実 UI スクリーンショット shot-02（今日の Gem ダイジェスト）
- 伝えたい 1 メッセージ: ゼロクエリの日次ダイジェストが独立した機能として存在する
- 出典: ADR 0014 / open-questions.md D-33

## Slide 4: star の多さは、使われている証拠ではない

- 見出し: star の多さは、使われている証拠ではない
- 本文:
  - 約 600 万個の偽 star が観測されている（He et al., ICSE 2026）
  - debug_inspector は 25 star で 111,000 以上のプロジェクトから依存されている
  - star 順に並べるほど「役立つが無名」なものは沈む
  - 被依存数に対して star が不釣り合いに小さいものを Gem と定義する
- ビジュアル: 新規生成 new-02（課題の対比図）
- 伝えたい 1 メッセージ: なぜ作ったのか（課題認識）
- 出典: docs/00_concept/lean-canvas.md P-1 / P-2 / docs/project-mission.md

## Slide 5: 構想を、辿れるドキュメントに分解した

- 見出し: 構想を、辿れるドキュメントに分解した
- 本文:
  - 初期コンセプト（IndieGems）が先にあり、外部与件の下限要件でスコープをくるみ直した
  - コンセプト → 要件（prd.md が正本）→ 設計 → 開発 の順に積み上げる
  - 決定の経緯は open-questions.md に D-n として残す
  - 技術的意思決定は ADR 15 本
- ビジュアル: 既存流用 docs/infographics/08-doc-relations.webp
- 伝えたい 1 メッセージ: どういう検討をして何を作ったか（全体像）
- 出典: docs/README.md / docs/00_concept/inception-deck.md Q1 / docs/02_requirements/minimum-requirements.md

## Slide 6: 層を分けるのは W-1〜W-3 を守るときだけ

- 見出し: 層を分けるのは W-1〜W-3 を守るときだけ
- 本文:
  - W-1 データ源を差し替えられる
  - W-2 事業者（Cloudflare）固有 API をアプリ全体に染み出させない
  - W-3 ネットワークもフレームワークも要らずにテストできる
  - 「クリーンアーキテクチャだから」は層を足す理由にならない
  - 唯一の意図的な例外が TTL 付きキャッシュ層（ADR 0005）
- ビジュアル: 既存流用 docs/infographics/07-design.webp
- 伝えたい 1 メッセージ: アーキテクチャの規律
- 出典: docs/03_design/architecture/application-architecture.md L20-24 / ADR 0005

## Slide 7: Next.js 16 を Cloudflare Workers の上で動かす

- 見出し: Next.js 16 を Cloudflare Workers の上で動かす
- 本文:
  - Next.js 16（App Router・React Server Components）
  - Tailwind CSS v4 + shadcn/ui（Radix UI）
  - Cloudflare Workers（@opennextjs/cloudflare）
  - Vitest 4 + Testing Library + MSW 2（単体・結合）
  - Playwright + axe（E2E）
- ビジュアル: 既存流用 docs/infographics/12-cloudflare.webp
- 伝えたい 1 メッセージ: 技術スタックの実体
- 出典: README.md 技術スタック表 / ADR 0001 / ADR 0002 / ADR 0006

## Slide 8: 同じコードでも、プレビューでだけ壊れる

- 見出し: 同じコードでも、プレビューでだけ壊れる
- 本文:
  - redirects の destination に :path を書くとプレビューでだけ 500 になる（OpenNext が path-to-regexp を validate: true で呼ぶ）
  - 拡張子付きパスは /repos/angular/angular.js が 404、/ja を付けると 200
  - wrangler deploy がブロックされることがある（実測 5 回失敗・2 回成功の非決定的挙動）
  - ローカルの next start では再現しないので、プレビューで踏むまで気づけない
- ビジュアル: 新規生成 new-03（罠の実測表）
- 伝えたい 1 メッセージ: 実際に踏んだ罠（環境固有の破れ）
- 出典: docs/rules/lessons/cloud-environment.md L-129 / L-130 / ADR 0002

## Slide 9: Gem Index ＝ 被依存数と star の残差

- 見出し: Gem Index ＝ 被依存数と star の残差
- 本文:
  - 被依存数のパーセンタイル順位 − star のパーセンタイル順位
  - star を水増しすると値は下がるので、偽 star に構造的に頑健
  - 健全性（criticality_score）は合算せず、足切りにだけ使う
  - 合算すると「健全だが有名」が上位に戻り star 追随に退化する
- ビジュアル: 既存流用 docs/infographics/10-gem-score.webp
- 伝えたい 1 メッセージ: 差別化ロジックの中身
- 出典: ADR 0009 §2.1 / §3.1 / §3.2

## Slide 10: 1 セッションを 1 スプリントとして回す

- 見出し: 1 セッションを 1 スプリントとして回す
- 本文:
  - 着手時に Issue を status:in-progress にして論理ロックを取る
  - スプリントゴールと編成を Issue に記録してから実装に入る
  - 確認してよいのは A-1〜A-6 と、仕様解釈が 2 通り以上ある分岐だけ
  - それ以外は実装からマージまで確認なしで進む
- ビジュアル: 新規生成 new-04（セッション = スプリントの流れ）
- 伝えたい 1 メッセージ: AI エージェントの自律運用（規範の記述であって効果の断定ではない）
- 出典: docs/rules/session-sprint-rules.md §1-2 / user-confirmation-minimization.md §1 / sprint-development-rules.md SD-3

## Slide 11: テストを先に書き、緑でなければ進めない

- 見出し: テストを先に書き、緑でなければ進めない
- 本文:
  - Red → Green → Refactor の順を崩さない
  - 単体・結合は Vitest + MSW、E2E は Playwright + axe
  - 操作レビューの手順をそのまま E2E テストに写す
  - テストのスキップ・無効化で緑にしない
- ビジュアル: 既存流用 docs/infographics/11-testing-strategy.webp
- 伝えたい 1 メッセージ: TDD と品質担保
- 出典: docs/04_development/testing-strategy.md / sprint-development-rules.md SD-2

## Slide 12: PR 前に 20 項目を機械検証してからマージする

- 見出し: PR 前に 20 項目を機械検証してからマージする
- 本文:
  - npm run check が lint・型・単体/結合・E2E・a11y・アーキテクチャ境界など 20 項目を検証する
  - 観点別セルフレビュー → 行単位インラインコメント → 対応 → squash マージ
  - 同じ箇所の修正サイクルが 2 回を超えたら止めて報告する
  - この運用でマージ済み PR は 90 件（2026-08-22 時点）
- ビジュアル: 新規生成 new-05（PR 自律フロー）
- 伝えたい 1 メッセージ: PR 運用の自律化（実績値つき）
- 出典: docs/rules/pr-review-flow-summary.md / PR #361 の check 結果表 / GitHub 検索実測 2026-08-22

## Slide 13: 作った差別化機能を、実測で撤去した

- 見出し: 作った差別化機能を、実測で撤去した
- 本文:
  - 却下: 候補プールはユニーク 227 リポジトリ、検索上位 100 件との一致は一般語でほぼ 0 件
  - 却下: 候補を拡大するとバンドルが Workers Free の 3MB 上限を超える
  - 採用: sort=gem-index を検索結果から撤去した
  - 採用: 1 検索あたり最大 10 リクエスト（体感 3〜8 秒）が常に 1 リクエスト（0.5〜1 秒）になった
  - 採用: Gem Index の定義は撤回せず「今日の Gem」で使い続ける
- ビジュアル: 新規生成 new-06（採用 vs 却下）
- 伝えたい 1 メッセージ: 技術的課題 1: 測って自分で殺す
- 出典: ADR 0009 D-33 追記 / open-questions.md D-33

## Slide 14: 認証方式は 6 つの軸で選ぶ

- 見出し: 認証方式は 6 つの軸で選ぶ
- 本文:
  - 却下: Fine-grained PAT（有効期限の更新が人手に残る）
  - 却下: 未認証のまま叩く（レート枠が狭い）
  - 採用: GitHub App の installation token
  - 軸 2「トークン取得の往復コストを払えるか」と軸 4「実装コストを払えるか」が拒否権を持つ
  - 決め手は軸 3（有効期限更新を人手でやらない）で、枠の拡大は付随した利点
- ビジュアル: 新規生成 new-07（採用 vs 却下）
- 伝えたい 1 メッセージ: 技術的課題 2: 次に同じ選定をするときの判断軸
- 出典: ADR 0003 §6.1 の 6 軸表 / §3.2

## Slide 15: Web アプリだが、DB を 1 つも持たない

- 見出し: Web アプリだが、DB を 1 つも持たない
- 本文:
  - 却下: 自前 ETL + DB（単一開発者 + AI の運用では定常運用コストが見合わない）
  - 却下: お気に入りのサーバー保存（端末間同期の利便性より DB レス原則を優先）
  - 採用: 検索状態は URL、ロケールはパス、セッションは暗号化 httpOnly Cookie、お気に入りは localStorage
  - 唯一の例外は TTL 付きの CachePort（ADR 0005）
- ビジュアル: 新規生成 new-08（採用 vs 却下）
- 伝えたい 1 メッセージ: 技術的課題 3: 状態をどこに置くか
- 出典: ADR 0007 §2 / §6

## Slide 16: 持ち帰れる 3 つの考え方

- 見出し: 持ち帰れる 3 つの考え方
- 本文:
  - 指標は絶対値ではなく残差で作ると、水増しに構造的に強くなる
  - 層を足す前に「どの規律を守るためか」を 1 行で言えるかを問う
  - 作った機能を実測で殺せるように、判断の根拠を記録に残しておく
- ビジュアル: 新規生成 new-09（まとめ）
- 伝えたい 1 メッセージ: 聴衆が自分の現場で使えるもの
- 出典: ADR 0009 / application-architecture.md W-1〜W-3 / open-questions.md D-33

## Slide 17: リポジトリとドキュメントの入口

- 見出し: リポジトリとドキュメントの入口
- 本文:
  - github.com/kai-kou/gem-hunter
  - 要件の正本: docs/02_requirements/prd.md
  - 決定の経緯: docs/02_requirements/open-questions.md
  - 技術的意思決定: docs/adr/（15 本）
- ビジュアル: 新規生成 new-10（クロージング）
- 伝えたい 1 メッセージ: 次に読むもの
- 出典: README.md / docs/README.md

