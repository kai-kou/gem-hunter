<!--entry
author: retro_facilitator
round: 1
kind: claim
ts: 2026-08-19T09:51:00+09:00
-->

# レトロスペクティブ（争点E担当）: SP-1 KPT

## Keep
- Vitest 4 + MSW 2 で 7 ファイル 22 テスト green・依存規則チェック PASS・Cloudflare へ実デプロイして操作レビュー手順を完走できる状態でマージ（SD-1/SD-2 の骨格は満たせた）
- ACL の ZodError 層漏れをセルフレビュー段階（マージ前）で検出し safeParse + UpstreamError へ自己修正できた（単独実行下でも一部の自己修正は機能した実例）
- check_architecture_boundaries.py の 57 秒バックトラックを同じ firing 内で発見し 58ms まで修正できた（気づいた後の対応速度は速かった）

## Problem（どの仕組みが欠けていたか。誰が悪いかではなく）
- **P1**: SD-4 の「着手時に読む順序」に `domain-model.md`（値オブジェクト＝ブランド型+スマートコンストラクタの正本）が明示されておらず、`architecture-rules.md` 経由の間接参照に留まっていた。結果、SearchQuery を最初クラスで書いてから書き直す手戻りが発生した。
- **P2**: `self_review_check.py` はチェッカーがタイムアウト（30 秒）した場合に「checker error」として非致命扱いにしており、`check_architecture_boundaries.py` の性能劣化（57 秒）が PR 前ゲートを素通りさせていた。チェッカー自体の異常とチェッカーが検出した違反を区別する仕組みが無く、前者がサイレントに握りつぶされる設計だった。
- **P3**: GitHub Actions のジョブ（deploy-preview 含む）が起動できない状態が未切り分けのまま残り、プレビュー URL 確保を `wrangler versions upload` の手動実行に依存している。SD-1（プレビュー URL 必須）の自動化経路が壊れたまま次スプリントに持ち越されるリスクがある。
- **P4**: SP-1 の残作業（p95 CPU 実測 / Cache Port の器 / シークレット投入・Rate Limiting / installation-token.ts の ClockPort 化）が Issue #26 本文の記述に留まり、後続スプリントが個別に着手・完了判定できる単位（sub-issue・sp 付与）に分解されていない。
- **P5（参考・Try は争点 B/D 側に委ねるためここでは起票しない）**: 単独実行モードでは Layer 1 セルフレビューが観点別フレッシュ文脈の並列サブエージェント（自己修正盲点 64.5% 回避が設計目的）を使えず、メインの読み直しで代替した。これはチーム編成そのものの規律なので、Try の起票は process_design / guardrail_eng の設計（争点 B/D）に委ね、本レーンでは重複起票しない。

## Try（Issue 化候補・優先度順・上位4件）

### Try-1（優先度: 高）P3 に対応
- Issue タイトル: `bug: GitHub Actions のジョブが起動しない（deploy-preview 含む）原因を切り分ける`
- ラベル: `type:retro-try`, `sp:3`
- 完了条件: Actions のジョブが起動不能な原因（org/repo の Actions 権限・runner 在庫・ワークフロー設定のいずれか）を特定し、再現手順付きで記録する。恒久修正できた場合は deploy-preview が実際に緑で走ることを確認する。A-6（アカウント設定）相当と判明した場合は、飼い主に依頼する設定変更を 1 文で明記して Issue に残す（原因調査自体はユーザー確認なしで完遂する・L-077）
- 対応する Problem: P3

### Try-2（優先度: 高）P2 に対応
- Issue タイトル: `fix: self_review_check.py のチェッカータイムアウトをサイレント通過させず Error として扱う`
- ラベル: `type:retro-try`, `sp:3`
- 完了条件: 個別チェッカー（`check_architecture_boundaries.py` 等）が self_review_check.py のタイムアウト閾値内に完了しなかった場合、非致命の「checker error」として PR 前ゲートを通過させず、非ゼロ終了で Error 扱いにする。あわせて主要チェッカーの実行時間を計測してログに残し、`python3 tools/self_review_check.py` を意図的に遅いチェッカーで実行するテストケースで Error 終了を確認する
- 対応する Problem: P2

### Try-3（優先度: 中）P1 に対応
- Issue タイトル: `improvement: SD-4 の読む順序に domain-model.md / application-architecture.md の該当節を明示する`
- ラベル: `type:retro-try`, `sp:2`
- 完了条件: `docs/rules/sprint-development-rules.md` §4 の読む順序表に「値オブジェクト・エンティティを実装する前に `domain-model.md` の該当節（ブランド型 + スマートコンストラクタ規約）を確認する」行を追加する。`architecture-rules.md` との参照が重複しないよう「入口はこちら、詳細は architecture-rules.md 経由」の形に整理し、次にドメイン層を実装するスプリントで同型の手戻りが起きないことをレビューで確認する
- 対応する Problem: P1

### Try-4（優先度: 中）P4 に対応
- Issue タイトル: `feature: SP-1 残作業（p95 CPU 実測 / Cache Port の器 / シークレット投入・Rate Limiting / installation-token.ts の ClockPort 化）を独立 Issue に分解する`
- ラベル: `type:retro-try`, `sp:2`
- 完了条件: Issue #26 に列挙されている残作業 4 件を、それぞれ検証可能な完了条件・`sp:N` 付きの sub-issue として起票し（`mcp__github__sub_issue_write` で #26 に紐付け）、sprint-cycle-router の Step 4 が拾えるバックログ状態にする。分解後、#26 自体は「SP-1 の親 Issue」として残すか、全 sub-issue 完了時にクローズするかを 1 行で明記する
- 対応する Problem: P4

## 起票しない候補
- 該当なし（争点 E のブリーフ候補 4 件すべてを Try-1〜4 として起票、P5 は他争点のレーンへ委譲）
