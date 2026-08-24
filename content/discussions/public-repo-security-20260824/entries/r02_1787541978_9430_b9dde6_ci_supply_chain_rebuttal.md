<!--entry
author: ci_supply_chain
round: 2
kind: rebuttal
ts: 2026-08-24T12:26:18+09:00
-->

# ci_supply_chain — Round 2（rebuttal）

## 1. `repo_hardening` の GitHub 設定項目を CI 知識で査定

### 1-A. 「`quality-checks` を required status check に登録」— **技術的に精度は正しいが、severity を格上げすべき**

- **check 名の指摘は正確**: `quality-checks.yml` の job 定義は `jobs: checks:`（`name:` オーバーライドなし）なので、GitHub 側に登録される check run 名は **`checks`**（workflow 名 `quality-checks` ではない）。`repo_hardening` の投稿はカッコ書きで既にこの区別をしており訂正不要。
- **fork PR での挙動**: `quality-checks.yml` は `pull_request`（非 `pull_request_target`）で fork PR にも到達するため、初回コントリビューターの実行承認さえ通れば check run `checks` は正常に生成される。required status check への登録自体は fork PR 経路と矛盾しない。
- 🔴 **格上げすべき点**: `repo_hardening` は「登録すると `automation/gem-pool-refresh` PR が永久 pending でマージ不能になる」ことを **注意書き**（"検討すること"）で済ませているが、これは仮定の話ではなく **確定した regression**。根拠: `gem-pool-refresh.yml` 自体のコメントに明記の通り、`GITHUB_TOKEN` 由来のイベントは新しい workflow run を作らない（GitHub 公式仕様）ため、この自動化 PR に対して `quality-checks.yml` の `pull_request` は **一度も発火しない** → check run `checks` は永久に「未報告」のまま。GitHub のルールセット `required_status_checks` は「未報告」を「pending」として扱い続け、タイムアウトで自動的に免除されることはない（GitHub Checks API の仕様）。つまり **この 1 行を有効化した瞬間、既存の自動反映フロー（週次・Issue #458/#482 で正式決定済み）が機能停止する**。
- **具体的な緩和策（`repo_hardening` の "検討すること" を実行可能な形に落とす）**:
  - (a) ルールセットの **bypass list** に、マージを実行する ID（Claude セッションが使う GitHub App/PAT、または "Repository admin" ロール）を追加する。ruleset の `bypass_actors` はブランチ名条件なしで全体に効くため、"このブランチだけ除外" はできない点に注意（ruleset のターゲットは push 先の `main` であり、PR の head ブランチ名では絞れない）。
  - (b) もしくは required status check 登録を **見送る**（現状維持）。
  - (a)/(b) いずれかを明示的に選んでから実行に移すべきで、「登録してから様子を見る」は不可（有効化した瞬間に壊れるため後戻りが必要になる）。
- **判定**: `repo_hardening` の技術的記述（check 名・fork PR 挙動）は正しい。ただし risk 表現は「検討事項」ではなく **「先に bypass 方針を確定しないと実装できない前提条件」** として最終手順書に明記すべき（ユーザーがコピペで実行した場合に自動化が壊れる実害が確定しているため）。

### 1-B. 「Workflow permissions を Read-only に」— **実害なし。CI 知識で裏付け確認**

- GitHub Actions の権限解決順序: リポジトリ既定の "Workflow permissions"（Read-only / Read-write）は、ワークフロー YAML が `permissions:` を **明示していない場合のフォールバック値** にすぎない。YAML 側で `permissions:` を宣言していれば、そちらが優先されリポジトリ既定を上書きする（GitHub 公式仕様。既定を絞っても明示宣言の上限を切り下げることはない）。
- 実際に確認済み: `quality-checks.yml` は `permissions: contents: read`（top-level）、`gem-pool-refresh.yml` は `permissions: contents: write / pull-requests: write`（top-level）を **両方とも明示宣言済み**。よって Workflow permissions を Read-only に変更しても **`gem-pool-refresh.yml` は壊れない**（`repo_hardening` の「実害は限定的」という表現は正確には「実害ゼロ」と言い切ってよい）。
- **格上げ提案**: この変更は 100% 安全なので、`repo_hardening` の優先度分類「推奨」から実装容易性の観点で「必須リストの直後にすぐ実行してよい低リスク項目」として案内してよい。

### 1-C. 「Allow GitHub Actions to create and approve pull requests」を OFF にした場合 — **`gem-pool-refresh.yml` が壊れる（ここは誰も OFF を推奨していないが、明示的な NG 事項として最終成果物に書くべき）**

- この設定は Settings → Actions → General の "Workflow permissions" セクション内にある **別のチェックボックス**（Read/Write のラジオボタンとは独立）。既定 OFF のリポジトリも多く、一般的な「GitHub Actions ハードニングチェックリスト」ではしばしば OFF 推奨として登場する。
- `gem-pool-refresh.yml` の最終ステップ（`Create or update pull request`）は `GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}` を使って `gh pr create` を実行している。この設定が OFF だと、`pull-requests: write` の permissions scope を宣言していても **`GITHUB_TOKEN` による PR 作成自体が 403 で拒否される**（scope の上限とは独立したリポジトリレベルのゲート）。
- 現状 `repo_hardening` の推奨リストにこの項目を OFF にする提案は **含まれていない**（確認済み・良い）。ただし一般的な「セキュリティ強化」の連想から、ユーザーやレビュアーが独自判断で OFF にしてしまうリスクがある。**最終成果物に「この設定は ON のまま維持すること（OFF にすると Gem 候補プールの週次自動反映 PR が作成できなくなる）」という明示的な NG 事項を 1 行追加することを提案する**。

## 2. `appsec_runtime` の CSP / セキュリティヘッダ指摘 — Cloudflare Workers + OpenNext 構成での実装可否

- **結論: 実装可能。ただし推奨実装面は `next.config.ts` の `headers()`（または `middleware.ts`）であり、`public/_headers` ファイルではない。**
- 根拠: `public/_headers` は **Cloudflare Pages 専用の規約**（静的アセット配信時にのみ Pages のルーティング層が解釈する）。本プロジェクトは `wrangler.jsonc` + `wrangler deploy` / `@opennextjs/cloudflare` で **Workers としてデプロイ** しており（`package.json` の `deploy` スクリプトが `wrangler deploy` を呼ぶ構成を確認済み）、Pages ではない。したがって `public/_headers` が存在しないことは「CSP 未設定の証拠」の一つとしては成立するが、**仮に追加してもこのデプロイ経路では効かない**（Workers のリクエストは Pages のアセットルーターを経由しない）。
- 正しい実装面: `next.config.ts` の `async headers()` はビルド時に Next.js のルーティングメタデータへ組み込まれ、OpenNext Cloudflare アダプタは Next.js のレスポンス生成パイプラインをそのまま Worker 上で実行するため、`headers()` で定義したレスポンスヘッダ（CSP・`X-Frame-Options`・`Referrer-Policy` 等）は Workers 環境でも問題なく付与される（OpenNext のドキュメント・アーキテクチャ上、`next.config.js` の `headers()`/`redirects()`/`rewrites()` は Cloudflare アダプタのサポート範囲内）。あるいはミドルウェア（`NextResponse.next()` の `.headers.set(...)`）でも同様に付与可能。
- **`appsec_runtime` の finding 自体（CSP 欠如は medium）は妥当・撤回不要**。実装ガイダンスとして「`next.config.ts` に `headers()` を追加する（`public/_headers` ではない）」という 1 行を最終成果物に添えることを提案する。

## 3. 自分の round 1 主張の concession

- **撤回**: round 1 の「[info] fork PR の Actions 実行承認要否」（`quality-checks.yml` に対する一般的な提案）は、`repo_hardening` の項目 5「"Require approval for all outside collaborators" を有効化」という同一対象への、より精密で実測に基づいた指摘と重複する。自分の記述（「Require approval for first-time contributors 以上」）は GitHub の実際の選択肢ラベルと微妙に異なり不正確なので **撤回し、`repo_hardening` の item 5 に一本化することを支持する**。
- **撤回しないもの**: 「ブランチ保護の要確認」という round 1 の申し送りは `repo_hardening` の実測（ルールセット `protect-main`・`required_status_checks` 不在）で解消済み・裏付けされたので、そのまま `repo_hardening` の item 1 に委ねる。「curl\|bash の `main` 参照（low）」は他レンズと重複がなく撤回不要。

## サマリー
- `repo_hardening` item 1（required status check 登録）: 技術的に正確だが、**bypass 方針を先に決めないと `gem-pool-refresh` 自動化 PR が永久マージ不能になる確定 regression** なので、最終手順の「必須」欄には前提条件（bypass_actors 設定 or 見送り）を明記すべき。
- `repo_hardening` item 5 前半（Workflow permissions read-only 化）: 両ワークフローとも `permissions:` を明示済みのため **実害ゼロ**、安全に実行可。
- 未言及の危険 NG 事項を追加提案: **「Allow GitHub Actions to create and approve pull requests」は ON のまま維持**（OFF にすると `gem-pool-refresh.yml` の PR 作成が壊れる）。
- `appsec_runtime` の CSP 指摘は妥当。実装面は `next.config.ts` `headers()`（`public/_headers` は Pages 専用で本構成には効かない点を最終成果物に反映）。
- 自分の round 1 の fork PR 承認要否コメントは `repo_hardening` item 5 に一本化し撤回。
