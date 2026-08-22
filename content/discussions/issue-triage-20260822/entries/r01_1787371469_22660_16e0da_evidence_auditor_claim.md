<!--entry
author: evidence_auditor
round: 1
kind: claim
ts: 2026-08-22T13:04:28+09:00
-->

# evidence_auditor: A/B クローズ根拠の実測監査（Round 1）

全 14 件をリポジトリ実測で再確認した。**うち 3 件が CLOSE 不可、1 件が要再スコープ**。残り 10 件は根拠を確認できた。

## 提案 A（対応済みクローズ）

### #55 — **CLOSE 不可**（提案書の根拠が誤り。むしろ問題が再発中）
- 確認箇所: `docs/rules/token-optimization-rules.md:75-86`、実測 `wc -c .claude/rules/*.md`
- 提案書は「2026-08-19 エントリ (91,960B) で一本化・2026-08-20 エントリ (98,265B) も整合して継続記録」と書くが、**実際には整合していない**。増減ログの最新行（:84, 2026-08-20, **98,265 B**）の直後にある本文要約（:86）は依然「現行の実測は **~92.0KB**（+12,888B, +16%）」＝ 2026-08-19 の 91,960B を指したまま更新されていない。さらに **今この場で `wc -c .claude/rules/*.md` を実測すると 100,890 B**（14 ファイル）で、ログ最新値 98,265B とも +2,625B 乖離している。
- つまり現在「増減ログ最新（98,265B）」「本文要約（~92.0KB=91,960B 相当）」「実測（100,890B）」の **3つの異なる数値が併存**しており、これは #55 の完了条件②「増減ログ最新 = 本文要約 = 実測」に**正面から違反**する状態。Issue が懸念していた「未記録の増分が溜まる」構造的問題が、まさに一度目の対応後に再発している。
- 判定: CLOSE 不可。再オープンするか、この再発を扱う後継 Issue が要る。

### #85 — **CLOSE 不可**（完了条件 3 項目中 1 項目が未達）
- 確認箇所: `tools/check_cjk_markdown.py:197-213,321-335,369-389`（`--under` 実装・self-test あり、確認）
- しかし完了条件「委譲プロンプトの定型（`agent-team-summary.md` 等）に必要な注意が入っている」は**未達**。`docs/rules/agent-team-summary.md` / `agent-team.md` を grep しても `--under` への言及は一切ない。さらに `CLAUDE.md:246` 自身が模範コマンドとして今も `python3 tools/check_cjk_markdown.py --fix --changed`（`--under` なし）を掲げており、並行委譲時に「担当ファイルだけを整形する」運用は明文化されていない。ツールの機能は追加されたが、再発防止の運用側の手当てが欠落している。
- 判定: CLOSE 不可（または完了条件を「ツール実装のみ」に縮小した上で別 Issue へ運用手当てを切り出すなら再スコープ可）。

### #108 — CLOSE 可
- 確認箇所: `src/ui/site-header.tsx:1-60`、`app/[locale]/page.tsx:290-299`、`app/[locale]/repos/[owner]/[repo]/page.tsx:78,101,111`、`app/[locale]/repos/[owner]/[repo]/not-found.tsx:40,49`
- 一覧・詳細・404 の 3 ページ全てで `SiteHeader` 使用を確認。`h1`（アプリタイトル）は `SiteHeader` にのみ存在し、詳細ページの `h2`（`${owner}/${repo}`）と重複しない見出し階層を確認。`site-header.test.tsx` あり。
- 提案書の「実装形態は layout.tsx 直置きでなく page 単位の共有コンポーネント」は事実だが、完了条件（両ページでタイトル表示・見出し階層に重複なし・テストあり）は実測で全て満たされている。争点として残すのは妥当だが CLOSE 判断自体は支持できる。

### #144 — **CLOSE 不可**（コードが明示的に本 Issue への先送りを宣言している）
- 確認箇所: `app/api/auth/logout/route.ts:12-15`、`git log --oneline -- app/api/auth/logout/route.ts`（コメント追加コミット `ae6c195`, PR #219, 2026-08-20）
- コメント原文: 「CSRF 対策: セッション Cookie は `sameSite: 'lax'`...のため、クロスサイトからの POST 送信では Cookie が付与されず攻撃は成立しない。**専用の CSRF トークン導入は Issue #144 に残る。**」
- 重要なのは、この一文は #144 が起票された**後**（PR #219, 2026-08-20）に追記されたということ。つまり当時のセッションは `sameSite:lax` の防御効果を認識した上で、なお「専用トークン導入」を #144 に意図的に残す判断をしている（同 PR は #145/#213/#82 を close したが #144 は close していない）。完了条件の文言（「POST化 or 同等のCSRF対策」）は字面上満たせるが、コードの一次情報（コメント）は Issue の作者自身が「まだ残作業がある」と明記しており、これを覆す新しい判断根拠が提案書にはない。
- 判定: CLOSE 不可。close するなら、先にこのコメントを更新して #144 への forward reference を外す（さもないと closed issue を指す dangling reference が残る）か、"sameSite:lax で十分と判断し直した" 旨をコメントと Issue 両方に記録すること。

### #182 — CLOSE 可
- 確認箇所: `app/globals.css:87`（`--muted-foreground: oklch(0.5 0 0)`）、`python3 tools/check_contrast.py` 実行 → 全 22 判定 PASS（`--color-fg-muted` ライト 6.00:1 / ダーク 7.63:1）、`src/ui/loading-indicator.tsx:21-25,49` に `animate-pulse` 不使用を確認、`e2e/sp-9-a11y.spec.ts:74-80` 現存。
- 完了条件を実測で満たしている。

### #288 — CLOSE 可（ただし残存する未確認点あり）
- 確認箇所: `docs/02_requirements/open-questions.md:342-343`（D-31/D-32, 2026-08-21）、`docs/03_design/infrastructure/cloudflare-infrastructure.md:600-783`（接続手順・実際に踏んだ罠 4 件・API 実測込みで詳細に記録）、`package.json:23-24`（`deploy` / `deploy:ci` 配線確認）、`tools/workers_build_deploy.sh`（fail-closed 設計を確認）。
- 罠 3・罠 4 の記述（ダッシュボード実機での警告・初回ビルドボタン不在の観測）から、Cloudflare 側の実接続が実際に行われたことは強く裏付けられる。
- ただし、ドキュメント内に「接続後の初回本番デプロイが実際に成功した」という直接的な確認文（ビルド ID・成功ログ等）は見当たらなかった（§8.2.3 は設定・罠・検証すべき 3 点の記述までで終わっている）。「デプロイ経路が完走する状態が整った」は支持できるが、「本当に完走することを確認した」は一次証跡が薄い。CLOSE は支持するが、Issue コメントに「初回実デプロイの成否」を一言残すことを推奨。

### #292 — CLOSE 可（#182 と同一事象・根拠は #182 と同じ）
- 確認箇所は #182 と同一。`animate-pulse` 除去とコントラスト改善で、点滅の谷による瞬間的な閾値割れという#292固有の原因も解消されている。

### #346 — CLOSE 可
- 確認箇所: `src/ui/site-header.tsx:39`（`<header>` が `LocaleSwitcher` を内包）、`app/[locale]/page.tsx:290,299`（`SiteHeader` → `<main>` の順で兄弟配置）、詳細ページ・404 ページも同型を確認（`SiteHeader` → `<main>` の順）。`nav`（`locale-switcher.tsx:38`）は `main` の外にある。

## 提案 B（前提消滅クローズ）

### #63 — CLOSE 可
- 確認箇所: `.github/workflows/` ディレクトリ不在を実機確認（`ls` → No such file or directory）、`docs/03_design/infrastructure/cloudflare-infrastructure.md:472,506`「撤去済み（D-23）」を確認、`open-questions.md:333`（D-23）で GitHub Actions 撤去の飼い主指示を確認。前提が構造的に消滅している。

### #77 — CLOSE 可
- 確認箇所: 同上 + `open-questions.md:342-343`（D-31/D-32）。A-6 として依頼していた課金確認自体、GitHub Actions 経由デプロイをそもそも採らない方針に切り替わったため意味を失っている。

### #282 — CLOSE 可
- 確認箇所: `src/infrastructure/feed/`・`app/api/digest/rss/`・`src/composition/digest-feed.ts` いずれも実機で不在確認。`open-questions.md:345`（D-34, 2026-08-21）が撤去範囲・理由・`DAILY_DIGEST_LIMIT` の移設先（`container.ts:47`）まで明記し、実ファイル状態と完全一致。

### #283 — CLOSE 可（#282 と同根拠）
- 確認箇所は #282 と同一。「トップと RSS で同じ内容」という不変条件の対象（RSS 側）自体が消滅している。

### #295 — CLOSE 可
- 確認箇所: `e2e/sp-16.spec.ts` 不在を実機確認、`open-questions.md:344`（D-33, 2026-08-21）で `sort=gem-index` 撤去を確認。

### #305 — **要再スコープ**（撤去は事実だが、指摘していた設計欠陥は別経路で現存する）
- 確認箇所: `src/usecases/search-repositories.ts` に `GemDigestPort`/`listCandidates`/`gem-index`/`gemIndex` の参照 0 件（grep 確認・提案書の記述どおり）。
- ただし唯一の呼び出し元になった `src/usecases/get-daily-digest.ts:46` は今も `await deps.port.listCandidates()` を **try/catch なし**で呼んでいる。Issue が問題視した「ポートが throw すると呼び出し側に何の防御もない」という設計欠陥そのものは、search-repositories.ts から get-daily-digest.ts へ**場所を変えて現存**している。
- 実際には `app/[locale]/page.tsx:278-284` が `.catch(() => null)` で二重防御しており（コメントで「二重防御」と明記）、500 化という最悪の実害は現状回避されている。しかし完了条件②「その分岐の単体テストがある（例外を投げるフェイクポートで検証）」・③「テストが修正前なら落ちる」は**どこにも実装されていない**（`get-daily-digest.test.ts` に throw/catch のテストケースなし、page.tsx 側にも該当テストなし）。`.catch` は page.tsx 側の作法に依存した防御であり、将来誰かがこの1行を消しても機械的に検知できない。
- 判定: 提案書の争点（「単純クローズか後継 Issue か」）の答えは **後継 Issue が必要**。「sort=gem-index の 500 化」という当初の症状は消えたので not_planned で閉じてよいが、「GemDigestPort の例外安全性が構造的に担保されていない」という本質的懸念は別 Issue として残すべき（closeする場合はその旨をコメントに明記）。

## 提案書の根拠が誤り・不十分だった箇所（名指し）

1. **#55**: 「2026-08-20 エントリも整合して継続記録されている」は誤り。実際は本文要約が最新ログ行に追随しておらず、かつ実測値がログよりさらに +2,625B 進んでいる（3 値不一致が現在進行形）。
2. **#85**: 完了条件 3 項目のうち「委譲プロンプトへの注意追記」を未検証のまま「完了済み」と判定していた（ツール機能の実装だけを見て運用面を見ていない）。
3. **#144**: 争点として認識はしていたが、コメントが「Issue #144 に残る」と明記した**時期**（#144 起票後）まで確認しておらず、「意図が消えるのでは」という疑問止まりだった。実際は当時の担当者が意図的に close しなかった記録であり、疑問ではなく明確な反証。
4. **#305**: 争点で「留保している」とは書いていたが、get-daily-digest.ts 側に実際に try/catch が無いこと・page.tsx 側の `.catch` がテストで担保されていないことまでは踏み込んでいなかった。
