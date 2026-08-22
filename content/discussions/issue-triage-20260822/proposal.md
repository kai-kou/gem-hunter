# 棚卸し判断の提案（open 182 件・機能追加を除く）

並行検証 7 役の実測結果を統合した提案。**この提案の妥当性を敵対的に検証してほしい**。

## 全体像

- verdict 分布: OPEN 151 / PARTIAL 17 / DONE 8 / OBSOLETE 6
- カテゴリ分布: CHECK 39 / RULE 30 / HARNESS 26 / APP 22 / TEST 17 / BACKLOG 16 / INFRA 11 / REVIEW 11 / UI 10
- ラベル欠損: priority 43 件 / status 34 件 / 表記ゆれ `priority:P2` 2 件

## 提案 A: 対応済みとしてクローズ（state_reason=completed）

- **#55** [type:improvement,sp:2,status:waiting-claude] improvement: Hot 層予算の増減ログと実測値の差分（+1,509 B）を突合して正本を一本化する
  - 根拠: docs/rules/token-optimization-rules.md:83 の2026-08-19エントリで+1,509Bの発生源特定と増減ログ追記が完了済み（91,960Bで一本化）。以降2026-08-20エントリ(98,265B)も整合して継続記録されている。
- **#85** [type:improvement,type:retro-try,sp:1,status:waiting-claude,priority:medium] improvement: 一括整形ツールが並行編集中のファイルを巻き込まないようにする
  - 根拠: tools/check_cjk_markdown.py:371-375 に --under オプションが実装済み(コメントでIssue #85と明記)。self-testにも --under のケースが追加されている(:325)。
- **#108** [type:improvement,sp:2,status:waiting-claude,priority:medium] improvement: 共通ヘッダー（アプリケーションタイトル・ロケール切替・ログイン導線の器）を layout に置く
  - 根拠: src/ui/site-header.tsx が共通ヘッダーとしてapp/[locale]/page.tsx・repos/[owner]/[repo]/page.tsx・not-found.tsxで使用済み(Issue #347)。e2e/sp-347-header.spec.tsで検証済み。layout.tsx直置きではなくpage単位の共有コンポーネントという実装形態だが、要求(両ページでアプリタイトル表示・ロケール切替/ログイン導線の器)は満たされている。
- **#144** [type:improvement,sp:1,priority:low] improvement: logout エンドポイントを POST 化し CSRF トークンで保護する
  - 根拠: app/api/auth/logout/route.ts:30 は POST ハンドラのみでGETハンドラが存在せず、同ファイル12-13行目コメントの通りセッションCookieは sameSite:'lax'（発行元 callback/route.ts:83, login/route.ts:35）でクロスサイトPOSTが成立しない。完了条件『POST化 or 同等のCSRF対策』は現状で満たされている
- **#182** [sp:2,type:bug,status:waiting-claude,priority:high] fix: LoadingIndicator の text-muted-foreground が 4.5:1 未達（14px・animate-pulse でさらに悪化しフレーク化）
  - 根拠: app/globals.css:87 --muted-foreground: oklch(0.5 0 0)（コミット f53bbbf, PR #183）で不透明時6.00:1（python3 tools/check_contrast.py 実行結果でPASS確認済み）。src/ui/loading-indicator.tsx に animate-pulse 無し（コメントで明示的に「文言にも animate-pulse を付けない（Issue #364 の E2E で実測）」と記載・#362/#367で除去）。e2e/sp-9-a11y.spec.ts:74 のテストは現存
- **#288** [sp:3,type:bug,status:waiting-claude,priority:high] fix: 本番デプロイ（npm run deploy）が auto mode classifier にブロックされ、マージしても本番へ出ない
  - 根拠: docs/02_requirements/open-questions.md:342-343 D-31/D-32（2026-08-21決定）でWorkers Builds経由のデプロイに移行完了。docs/03_design/infrastructure/cloudflare-infrastructure.md:630-745に接続手順と実際に踏んだ罠（2026-08-21実測・#290）が記録済み。package.json:24 に npm run deploy:ci（=tools/workers_build_deploy.sh）が配線済み
- **#292** [sp:2,type:bug,status:waiting-claude,priority:medium] fix: 読み込み中インジケータの axe コントラスト検査が、点滅アニメーションの途中を測って落ちる
  - 根拠: src/ui/loading-indicator.tsx:19-25 のコメントで『文言にもanimate-pulseを付けない（Issue #364のE2Eで実測）』と明記。実装(36-54行)にanimate-pulseは存在せず静止イラスト+テキストのみ
- **#346** [type:improvement,sp:2] improvement: 言語切替の nav を main の外へ出してランドマーク構造を整える
  - 根拠: src/ui/site-header.tsx:39 で <header> が LocaleSwitcher（nav含む）を包み、app/[locale]/page.tsx:290-299 で SiteHeader は <main> の直前（兄弟要素）としてレンダリングされている。nav は main の外に出ている

### A の争点
- **#144**: `logout/route.ts` は POST 限定 + `sameSite:lax` で完了条件を満たすが、**同ファイルのコメントが「専用 CSRF トークン導入は本 Issue へ先送り」と明記** している。クローズすると意図が消えるのではないか？
- **#182 / #292**: 両方 DONE かつ同一事象。両方 completed で閉じるか、#292 を duplicate で閉じるか。
- **#108**: 実装形態が提案（layout.tsx 直置き）と異なり page 単位の共有コンポーネント。目的は達成だが「完了」と言い切ってよいか。

## 提案 B: 前提消滅としてクローズ（state_reason=not_planned）

- **#63** [sp:2,type:bug,status:waiting-claude] bug: deploy-preview ワークフローが全実行で開始 4 秒後に失敗し、SD-1 のプレビュー URL が出せない
  - 根拠: .github/workflows/ ディレクトリ自体が現存しない(ls: No such file or directory)。cloudflare-infrastructure.md:472,506 が『deploy-preview.yml/deploy-production.ymlは撤去済み(D-23)』と明記し、本番/プレビューデプロイはD-31/D-32でWorkers Builds + wranglerセッション実行へ全面移行済み。
- **#77** [type:bug,sp:1,status:blocked] fix: GitHub Actions のワークフローが 1 度も実行されずに失敗している（A-6: 課金・実行枠の確認が必要）
  - 根拠: 同上。.github/workflows/ が存在せず、D-23/D-31/D-32でGitHub Actions経由デプロイ自体が廃止された。A-6として依頼していたActions課金確認の前提ごと消滅している。
- **#282** [type:improvement,sp:2,type:retro-try,status:waiting-claude,priority:medium] improvement: RSS の item link をロケール非依存にする（現在 /ja 固定）
  - 根拠: RSS配信機能自体が撤去済み。src/infrastructure/feed/ ディレクトリが存在せず、docs/02_requirements/open-questions.md:345 のD-34（2026-08-21）が『app/api/digest/rss/・src/infrastructure/feed/を撤去』と明記。コミット e0f3d7b（PR #337）で digest-rss.ts/route.ts を削除済み
- **#283** [type:improvement,sp:2,type:retro-try,status:waiting-claude,priority:medium] improvement: 「トップと RSS で同じ内容」を機械検査する（共有定数のコメント頼みを解消）
  - 根拠: 同上D-34によりRSS配信自体が撤去済み（src/composition/digest-feed.ts も削除・DAILY_DIGEST_LIMITはsrc/composition/container.ts:47へ移設）。『トップとRSSで同じ内容』という不変条件の対象（RSS側）が存在しない
- **#295** [sp:2,type:bug,status:waiting-claude,priority:medium] fix: SP-16 の E2E が本番の daily-digest.json に依存していて、日次再生成で壊れうる
  - 根拠: 対象ファイル e2e/sp-16.spec.ts が存在しない（`git log --diff-filter=D` でコミット4a8e113/PR#312にて削除確認）。D-33によりsort=gem-index機能自体が撤去されテストごと削除された
- **#305** [sp:2,type:bug,status:waiting-claude,priority:medium] fix: GemDigestPort が例外を投げると sort=gem-index の検索全体が 500 になる
  - 根拠: src/usecases/search-repositories.ts にGemDigestPort/listCandidates/gem-index/gemIndexへの参照が0件（grep確認）。D-33（open-questions.md:344）によりsort=gem-index経路がsearch-repositories.tsから撤去済み。GemDigestPortは現在src/usecases/get-daily-digest.tsからのみ使用される

### B の争点
- **#305**: `sort=gem-index` 経路は D-33 で撤去済みだが、検証役が「`get-daily-digest.ts` 側の例外安全性は別途要確認」と留保している。単純クローズでよいか、後継 Issue を起票すべきか。
- **#63 / #77**: 同一症状の重複でもある。両方 not_planned で閉じるか、#63 を duplicate にするか。

## 提案 C: 重複としてクローズ（state_reason=duplicate）

- keep **#322**（improvement: サブエージェント並行稼働中は Stop フックのコミット要求を抑制する）← dup #94, #341
  - 理由: 3件とも「並行サブエージェント実行中にStopフックのWIP自動コミットが発火して履歴を汚す」を問題とし、mutation_guard.sh型のTTL付きマーカーで抑制する対応方針・完了条件が同一。#322が最も具体的な実装案（parallel_agents_guard.sh・self-test要件）を持つため残す。
- keep **#321**（improvement: messages/ja.json と en.json の対一致を機械検査す）← dup #104
  - 理由: messages/ja.json と en.json のキー・プレースホルダ対称性を機械検査するという要求が同一。#321はtools/check_i18n_parity.pyの具体設計（キー集合一致・プレースホルダ一致・空文字検知）まで踏み込んでおり完了条件がより明確。
- keep **#221**（improvement: tools/check_*.py の TypeScript ソース走査ロジ）← dup #81
  - 理由: static検査ツール群のstrip_comments/lineno_at等TypeScriptレキサ処理を共通モジュールへ切り出すという要求が同一。#221は#81が対象とした2ファイルに加え3ファイル目（check_prefetchable_side_effects.py）まで含む上位互換のスコープ。
- keep **#319**（improvement: 議論ホワイトボードへの「投稿した」報告と実ファイルの乖離を機械検知する）← dup #344
  - 理由: discussion-reviewの参加者が「投稿した」と報告したのに議論ホワイトボードにファイルが実在しない、という事象を機械検知する要求が同一。#319はdiscussion_whiteboard.py verifyサブコマンドという具体設計・完了条件を持つ。
- keep **#350**（improvement: 検査ツールが「何を見て、何を見ていないか」を一覧化して穴を洗い出す）← dup #201
  - 理由: 各品質ゲート層（check_*.py・E2E・axe・Lighthouse）が「何を見て何を見ないか」をカタログ化するという要求が同一。#350は対象検査ツールの列挙・置き場所の判断基準・洗い出した穴のIssue化までを完了条件に含み範囲がより明確。
- keep **#357**（improvement: デプロイ済み URL への疎通確認を機械化する（run_checks は ）← dup #100
  - 理由: デプロイ/プレビュー済みURLへの疎通確認を機械化し、ローカルのrun_checks.shでは検出できないWorkersランタイム固有の障害を捕まえるという要求が同一。#357はスモークスクリプトの検証対象パス・pr-review-watcherへの配線先まで具体化しており#100の完了条件を包含する。
- keep **#182**（fix: LoadingIndicator の text-muted-foreground が 4.）← dup #292
  - 理由: LoadingIndicatorのtext-muted-foregroundがanimate-pulseとの併用でaxeのcolor-contrast検査に落ちる（フレーク化）という同一事象の報告。#182は不透明時点で既に4.41:1と閾値未達である根本原因まで特定しており、#292（点滅の谷での実測のみ）より完了条件が広く深い。
- keep **#159**（fix: pr-review-flow-summary.md の PR フロー記述を実装と一致させる）← dup #258
  - 理由: pr-review-flow-summary.md等が実在しないtools/check_publish_drift.pyとpublish-syncスキルへの実行を必須として指示している、というルール記述と実装の乖離指摘が完全に重複。#159はこの問題に加えrun_checks見出し要件の欠落も扱っており#258の完了条件（該当参照の解消）を包含する。
- keep **#77**（fix: GitHub Actions のワークフローが 1 度も実行されずに失敗している（A-6:）← dup #63
  - 理由: GitHub Actionsのdeploy-previewワークフローが開始数秒で失敗しSD-1のプレビューURLが出せない、という同一症状の報告。#63はアクションのバージョン不整合という未検証仮説に基づくが、#77はdeploy-production含む全11回の失敗を実測し課金枠（A-6）が原因と特定済みで、後の運用ルール（GitHub Actions制限中・ワークフロー撤去済み）とも整合す

### C の争点
- **#94 vs #322**: 検証役は #322 を keep と提案。しかし **#94 はコメント 13 件の議論履歴と `priority:high` を持つ最古の起票**。keep を #94 に変えるべきではないか（履歴の保全 vs 記述の具体性）。
- **#104↔#321 / #81↔#221 / #344↔#319 / #201↔#350 / #100↔#357**: いずれも「後発のほうが具体的」を理由に後発を keep している。**古い Issue のコメント履歴を捨てる判断が一律で正しいか**。
- 検証役の所見: `[Retro][SP-n]` 形式はレキシカル類似度が高いが実際は別事象。**重複判定が過剰になっていないか** を疑ってほしい。

## 提案 D: Epic への集約

- 既存 #151: #321, #256, #257, #299, #320, #178, #191, #206, #207
  - 理由: いずれも「ドキュメント正本と実装/挙動のずれ、または規約違反を検知する検査スクリプトを新設しrun_checks.shへ配線する」という機械検査追加パターンで、Epic #151の趣旨（配線まで含めて揃える）に直接合致する。#321は重複統合によりクローズした#104の後継として追加。
- 既存 #152: #322, #319, #260, #215, #216, #200, #314
  - 理由: 並行サブエージェント実行・議論型レビューにおける安全性（作業ツリーの巻き込み・委譲の契約不足・役割境界の実行時強制・報告の真正性）という同根の問題。#322は#94の後継、#319は#344の後継として追加。#200自身が本文でEpic #152との関連を明記している。
- 新規「プレビュー/デプロイ済みURLの疎通・実測パイプライン整備」: #357, #110, #117, #124, #340
  - 理由: run_checks.shがWorkersランタイム実行時の挙動を見ていないという共通の穴に対し、プレビュー/本番URLへの疎通確認・挙動実測・アップロード運用（レート制限対策・1コマンド化）・バンドルサイズ検査を束ねる。#357/#110/#124はいずれも相互参照し統合可否を着手時判断すると明記している。
- 新規「check_deploy_gate.py と GitHub API フォールバックの堅牢化」: #236, #237, #238, #246, #313, #315
  - 理由: PR #235前後のセルフレビュー・レトロで検出された、本番デプロイゲート（Sprint Review判定・fail-closed設計）とその基盤（gh/urllibフォールバック）の欠陥群。投稿者権限検証・フォールバックのself-test固定・未捕捉例外の扱い・判定循環の設計整理という近接テーマ。
- 新規「Workersランタイム依存機能（レート制限・binding）の自動テスト整備」: #187, #188, #190, #192, #365
  - 理由: PR #184のRateLimitPort配線を機に発覚した「Workersランタイムでしか観測できない振る舞いを現行テストが1つも守れない」という共通課題（secret供給ギャップ・自動テスト不在・適用範囲の穴・フェイルオープンの不可視性・エラー文言の不整合）。
- 新規「制作系パイプライン（画像・スライド生成）の品質検証強化」: #326, #327, #329, #381, #382, #383, #384
  - 理由: インフォグラフィック/スライド生成のレトロスペクティブ（#316/#318・#363/#378）から出た、生成前検証の前倒し・自己検証・プロンプト規則の初版確定・依存管理・量パラメータの事前確定という同根の「生成コストを浪費する前に机上で防ぐ」テーマ。
- 新規「tools/ 検査基盤の棚卸しとテスト強化」: #221, #222, #224, #229, #278
  - 理由: TypeScriptレキサ処理の共通化(#221)・self-testの収集からexit codeまでのカバレッジ拡大(#222)・run_checks.shでのself-test実行必須化(#224)・60+スクリプトの責務棚卸し(#229)・バッチスクリプトのテスト可能化(#278)という、tools/配下の検査・実行基盤そのものの健全性を扱う一連の改善

### D の争点
- **#377 が「type:retro-try は自走ルーティンのどのブランチからも拾われず open 107 件が構造的に滞留する」と指摘済み**。この状態で新規 Epic を 5 本増やすことは、**滞留の解消ではなく滞留の階層化に過ぎない** のではないか。
- Epic 化より先に **#153（棚卸しレーンの担当決定）と #377（ルーティンの拾い漏れ修正）を解消すべき** という順序論が成り立つか。

## 提案 E: 優先度・見積もりの改訂（主なもの）

- #27: priority (なし) → **low** … 実害はワークアラウンドで既に緩和されているため恒久対応の優先度は低い。
- #29: priority (なし) → **medium** … sprint-cycle-router Step3.5が毎firing呼ぶ経路のリグレッションが自己テストで検知できない。
- #40: priority (なし) → **low** … M-4（第三者公開ゲート）未到達のため意図的に据え置き中。急ぐ理由なし。
- #50: priority (なし) → **low** … T-4(デプロイスキル)は別資産で実質代替済み。残るT-3の防御的チェックツールのみが未着手で、見積もりも縮小すべき。
- #51: priority (なし) → **low** … 開発が進み恩恵は減っているが害もないニッチな開発体験改善。
- #52: priority (なし) → **medium** … SP-4想定だったが19+SP経過後も未着手。テスト基盤強化の構造的な穴。
- #53: priority (なし) → **medium** … #52(check_a11y.py新設)完了が前提。
- #55: priority (なし) → **low** … 完了条件3点(発生源特定・数値一致・実測コマンド明記)を満たしている。
- #56: priority (なし) → **high** … クラウドでsandbox network allowlistが無効という前提と直結するセキュリティ上の穴。
- #60: priority (なし) → **medium** … 次回apply-base実行時に同種の上書き喪失が再発しうる。
- #63: priority (なし) → **low** … 前提のワークフロー自体が撤去され別アーキテクチャに置き換わったためクローズ推奨。
- #73: priority (なし) → **medium** … 大部分は完了済み。残りはコントロール高さの実測検証のみで元のsp:5は過大。
- #77: priority (なし) → **low** … クローズ推奨。status:blockedのまま放置されている。
- #81: priority (なし) → **medium** … #221が『tools/check_*.pyのTypeScriptソース走査ロジック共通化』を要求しており本Issueと実質同一。
- #83: priority (なし) → **medium** … check_ui_dimensions.pyの登録漏れとしてそのまま検出されない既知の限界も継続。
- #89: priority (なし) → **medium** … 手書きキーがコンパイルを通る状態が継続している。
- #108: priority medium → **low** … 実装場所は元の提案(layout.tsx)と異なるが目的は達成済み。
- #129: priority medium → **low** … 残作業はドキュメント整備のみで軽い。priority medium→low, sp 3→1を提案（実害は既に別Issue経由で解消済みのため）
- #150: priority (なし) → **medium** … labelsにpriorityが付与されていない（欠落）。防御の深さ改善であり緊急性は本文が『現時点で危険ではない』と明記するためmediumを提案（priority追加のためch
- #182: priority high → **medium** … 完了条件（4.5:1確保・animate-pulse除去）は既に満たされている。実装済みのためクローズ候補。priorityはverdict確定後は不要だが形式上維持。
- #190: priority medium → **high** … priority medium→high。詳細取得経路は無防備のままでGitHub App installation token（5,000req/時）を消費するDoS/コスト増大
- #196: priority medium → **low** … priority medium→low、sp 2→1。中核バグ（gh依存によるFileNotFoundError）は既に別経路で解消済みで運用への実害は小さい。残作業は--self
- #202: priority high → **medium** … priority high→medium。現時点で汎用化不足が原因の実障害は未観測（提案型の先回りリファクタ）で、#201（死角カタログ・実障害あり）より優先度は下と判断。
- #205: priority high → **medium** … priority high→medium。既存のハードコードフォールバックで現状は動作しており緊急性は低い（今後別ツールがLighthouseを使う際の再発防止が主目的）。
- #227: priority medium → **high** … priority medium→high。唯一の機械ゲート(run_checks.sh)がバックグラウンド実行で1コマンド完走しない状態が放置されており開発ワークフロー(tier2
- #236: priority medium → **high** … priority medium→high。リポジトリが#241で既に公開済み（visibility:public確認済み）となり、Issue本文が前提とした『実質単独運用で攻撃面限
- #245: priority medium → **high** … priority medium→high。session-concurrency-rules.mdがR-1ルーティン稼働のためHot化済み＝多セッション並行運用が常態であることが確
- #247: priority medium → **high** … priority medium→high。D-19で確定したPaid運用の唯一の後追い防御が未実装のまま公開済み（#241）でトラフィックに晒されている状態
- #259: priority medium → **high** … priority medium→high。SP-14〜16が既に存在し実際に同期対象から漏れている実害が発生中（想定リスクではなく現在進行中の不具合）
- #272: priority medium → **high** … priority medium→high。URL直書きだけでGitHub検索APIへ到達不能な範囲(page=40&per_page=100等)の要求が素通りする実装バグで、ユーザ
- #278: priority medium → **high** … priority medium→high。本Issueが指摘する構造的欠陥（star取得先バグの実データ生成まで露見しなかった件）は既に一度実害化しており再発防止が急務
- #287: priority medium → **high** … §7.4a必須要件への違反が実装に残存。他のa11y必須要件違反(#320)がhigh運用なので整合を取りmedium→highを提案
- #310: priority P2 → **medium** … priorityラベルが非標準の'P2'（high/medium/lowでない）。優先度体系に合わせmediumへ修正を提案
- #317: priority P2 → **medium** … priorityラベルが非標準の'P2'。#380（D-33再導入条件の実測検証）と実質同一の検証要求のため統合を推奨。medium相当に修正
- #324: priority (なし) → **low** … priorityラベル未設定。§5.1のみ未修正の軽微な整合作業のためlowを提案
- #326: priority (なし) → **low** … priorityラベル未設定。制作系ツールの品質向上（非ブロッキング）としてlowを提案
- #327: priority (なし) → **medium** … priorityラベル未設定。画像1枚$0.037の再生成コスト実損が既に発生した実例があるためmediumを提案
- #328: priority (なし) → **low** … priorityラベル未設定。実害は出ていない（Issue本文にも明記）ためlowを提案
- #335: priority (なし) → **medium** … priorityラベル未設定。ADR改訂を伴う可能性のある構造課題だが緊急のユーザー影響はないためmediumを提案
- #338: priority (なし) → **high** … priorityラベル未設定。上流の不正応答で一覧・詳細が500になるユーザー可視の実障害のためhighを提案
- #340: priority (なし) → **medium** … priorityラベル未設定。Workers Freeのバンドル3MB上限に対する予防的検査のためmediumを提案
- #341: priority (なし) → **high** … #94・#322・#341 は同一要求の三重起票（並行サブエージェント実行中の Stop フック WIP コミット抑止）。1 本へ統合し優先度を上げて着手すべき
- #342: priority (なし) → **medium** … #245（マージ直前の再検証）と目的は近いが発火タイミングが別（PR作成前 vs マージ直前）のため別Issue扱いが妥当
- #343: priority (なし) → **high** … サニタイズ本体は単体テストのみで配線ミスを検知できないというセキュリティ寄りの穴。優先度を上げる価値あり
- #344: priority (なし) → **low** … #319「議論ホワイトボードへの『投稿した』報告と実ファイルの乖離を機械検知する」とほぼ同一要求。#319 へ統合推奨のため優先度は下げる
- #345: priority (なし) → **low** … 3件中1件のみ完了。残り2件は軽微なドキュメント追随
- #346: priority (なし) → **low** … Issue #347/#353 のヘッダー共通化で既に解消済み。クローズ推奨
- #349: priority (なし) → **high** … #154（変異テストのspot check・priority:high）・#225（SD-2に回帰テストの赤化確認を追加・priority:high）と要求が重複。3本纏めて1本化
- #350: priority (なし) → **medium** … #201「品質ゲート各層の『見張る範囲』と死角をカタログ化する」とほぼ同一要求（#201は既にpriority:high）。統合推奨
- #351: priority (なし) → **low** … #375 の lessons化サブ項目（ポート3100の使い回し）と同根の『開発サーバー使い回しの罠』だが具体症状が異なるため別Issueのまま。ただし同時に対処すると効率的
- #352: priority (なし) → **high** … /en でもmeta description・og:description・titleが日本語のまま出る実害バグ。SEO/OG共有に直結するためpriority:highへ引き上げ
- #354: priority (なし) → **high** … WCAG 2.4.1（レベルA）はNFR-10のAA適合の前提。機械ゲート未検出の穴でもあるためpriority:highへ引き上げ推奨
- #355: priority (なし) → **medium** … 実害未確認（実測待ち）のため急ぎではないが、ADR上の未確認事項として残置されたまま
- #356: priority (なし) → **low** … 実測済みの有用な知見だが記録のみのdocsタスク
- #357: priority (なし) → **high** … #100「プレビューURLの疎通・ステータスを自動検証する」とほぼ同一要求（#100は現priority:medium）。#187（secret未配線でプレビュー認証が機能しない実
- #365: priority (なし) → **high** … 本番の実測（curl）で再現済みの実害バグ。存在しないログイン導線を案内する誤ったUXでpriority:high相当
- #366: priority (なし) → **medium** … ライセンス帰属表示の欠落は法務・コンプライアンス上の軽微リスク
- #371: priority (なし) → **medium** … GitHub利用規約上のリスク判定が未完了のまま放置されている
- #372: priority (なし) → **medium** … 4項目セットのIssueで見積もりが大きい。分割起票も検討余地あり
- #380: priority (なし) → **high** … status:in-progress済みで着手中と思われるが、成果物（議論記録・D-33更新）は本チェックアウト時点では未反映。GR-4（差別化の中核）に関わるためpriority

### E の争点
- chunk4 担当が **medium→high を 7 件** 提案している（#227 #236 #245 #247 #259 #272 #278）。既に `priority:high` は 41 件ある。**high をさらに増やすと優先度が機能しなくなる** のではないか。high の総数に上限（例: 20 件）を設けるべきか。
- 逆に「priority 欠損 43 件」をすべて medium で埋めると **medium が 120 件超になり同じく機能しなくなる**。欠損の埋め方の方針が要る。

## 検証してほしい問い

1. A/B のクローズ判断で、**根拠が実測として不十分なもの** はどれか（file:line や commit が示されていない、あるいは完了条件の一部しか満たしていない）。
2. C の重複判定で、**別物なのに重複扱いされているもの** はどれか。keep の選択（新しい方 vs 履歴のある方）の基準は何にすべきか。
3. D の Epic 化は、この状況で **本当に有効か**。代案は何か。
4. E の優先度改訂で、**priority が機能する分布** をどう定義すべきか（high/medium/low の目安件数・判定軸）。
5. 上記以外に、この棚卸しが **見落としている構造的問題** はあるか。