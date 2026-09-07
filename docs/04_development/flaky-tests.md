# 既知の Flaky テスト レジストリ

> **目的**: `bash tools/run_checks.sh`（`npm run check`）が赤くなったとき、それが **自分の変更が壊した本物の失敗**
> なのか **既知の flaky** なのかを判断する材料をここに集約する。テストファイルを開かないと分からない状態を解消する
> （背景: Issue #158・PR #143 マージ統合作業中に `e2e/sp-8-auth.spec.ts` の既知の flaky を本物の失敗と誤認しかけた）。
>
> **判断手順**（[`testing-strategy.md`](./testing-strategy.md) から誘導）: 赤くなったテストが本表に **載っていれば**
> 既知の flaky として扱ってよい（緩和策・恒久対応の状況を見て判断する）。**載っていなければ本物の失敗として扱う**
> （推測で「flaky だろう」と片付けない・`sprint-development-rules.md` `SD-2`）。

🔴 **本レジストリを「リトライで流してよいテストの一覧」にしない。** 各エントリには **恒久対応の Issue 番号**
または **対応しない理由** を必ず書く。どちらも書けないものはここに載せず、本物の失敗として扱う。

## 登録要件（#223・「調査省略の正当化装置」化の防止）

新規エントリは以下を **全て** 満たさない限り登録を認めない（1 つでも欠けたら本物の失敗として扱い、
`problem-investigation-protocol.md` の 5 ステップで原因を特定してから改めて登録を検討する）。

- **再現条件の切り分け** 列に、最低限「単体実行 / ファイル単位実行 / フルスイート実行」の 3 通りの結果と、
  `--repeat-each=5` の結果を書く（推測で「flaky だろう」と登録しない）
- **登録日** と **最終確認日**（YYYY-MM-DD）を記載する。恒久対応が未完了のまま **登録日から 7 日以上**
  経過したエントリは `tools/check_flaky_registry.py` が Warning として検出する（放置の可視化）

## 既知の flaky 一覧

| 対象 | 症状 | 原因 | 再現条件の切り分け | 現在の緩和策 | 恒久対応 | 登録日 | 最終確認日 |
|---|---|---|---|---|---|---|---|
| `e2e/sp-8-auth.spec.ts`「SP-8: 未ログインで全機能が使える／ログインでレート枠が切り替わる／ログアウトで元に戻る」の Step 2（`Step 2: ログイン中に検索すると、レート枠がユーザー自身のものに切り替わる`） | **解決済み**。1 回目の全体実行で `userAuthSearchCount` が増えず失敗し、その後の再試行（同一テスト内リトライ、または再実行）では 2 回連続で成功していた | 当初は PR #141（`SP-8`）が持ち込んだ「クロスオリジンのリダイレクト連鎖直後、サーバー側で `request.headers.get('cookie')` が空で届くタイミング揺らぎ」と推測していたが、これは誤りだった。真の原因は `next/link` の `<Link href="/api/auth/logout">` が本番ビルドでビューポート内リンクを自動プリフェッチし、`GET /api/auth/logout` が意図せず実行されてセッション Cookie が破棄されていたこと（Playwright トレースで `set-cookie` 空文字化を実測）。ログアウト導線を `<form method="post" action="/api/auth/logout">` に変更し、`route.ts` から `GET` ハンドラを撤去したことで解消した | `npx playwright test e2e/sp-8-auth.spec.ts --repeat-each=5` を実行し **20 passed** で安定を確認済み。さらに旧実装（`<Link href="/api/auth/logout">`）へ戻すと当該テストが実際に失敗することも実測しており、回帰テストが退行を捕まえられることを確認済み | リトライループは **撤去済み**（原因が解消されたため不要になった。旧・最大 3 回のリトライ実装は削除） | **解決済み**（Issue #145 はこの修正でクローズ。プロダクトコード修正はログアウト導線の POST 化コミット） | 2026-08-24 | 2026-08-24 |
| `e2e/search-wait-guard.spec.ts`「高速応答の検索でも待ち受けを取りこぼさず、戻った時点で結果が描画済みである」 | **解決済み**。`ALREADY_RENDERED_BUDGET_MS`（250ms）以内に検索結果リンクが可視であることを要求するアサーションが稀に満たされず、`getByRole('link', { name: 'octostub/octo-widgets' })` が `element(s) not found` で FAIL していた（Issue #978） | フルスイート実行: FAIL（1 failed / 121 passed・125 秒）。ファイル単位実行（`npx playwright test e2e/search-wait-guard.spec.ts`）: PASS（2 passed）。単体 `-g "高速応答"` × `--repeat-each=5`: 4 passed / 1 failed。単体でも約 20% の確率で再現しており、負荷非依存の欠陥と判定していた（Issue #978） | `searchFor()`（`waitForLoadState('domcontentloaded')`）は正しく機能しており、Suspense の解決済みコンテンツを含む HTML 本文は domcontentloaded の時点で常に到達済みだった。真の原因は React（`react-dom/server` の Fizz ストリーミング）が持つ Suspense 境界の reveal バッチ化: `app/[locale]/page.tsx` は同じ `statePromise` を 2 つの独立した `<Suspense>`（`SearchStatusText` = B:0 / `SearchBody` = B:1）で待つ構成のため、応答が速いと 2 つ目の境界の DOM 反映が React 内蔵の `$RC`/`$RB`/`$RV`/`$RT` 機構（`setTimeout($RT + 300 - performance.now())`）により最大 300ms 遅延する（実測失敗時の追加待ち時間は 295〜301ms）。応答が遅い（`sp9-slow` の 1.5 秒）場合はこの 300ms 窓を既に過ぎているため影響しない | ローカル 80 回試行の直接原因特定用アドホックスクリプトで再現・確定させ、`ALREADY_RENDERED_BUDGET_MS` を 250ms → 500ms（React の 300ms 上限 + 安全マージン）へ引き上げた。変異テスト: 値を 250ms に戻すと `--repeat-each=40` で 1 件 FAIL を再現、500ms に戻すと `--repeat-each=40` で 40 passed | **解決済み**（Issue #978。`ALREADY_RENDERED_BUDGET_MS` の根拠付き引き上げで恒久対応。将来 React のバッチ化タイマー定数が変わる場合は本コメントを更新すること） | 2026-09-07 | 2026-09-07 |

## 完了条件

- [x] `e2e/sp-8-auth.spec.ts` の Cookie タイミング問題 1 件が上記の項目で記録されている（解決済み）
- [x] 全エントリに恒久対応 Issue 番号または対応しない理由がある
- [x] 登録要件（再現条件の切り分け・登録日・最終確認日）が明記され、既存エントリに適用可能な形になっている

## 参照

| ドキュメント | 関係 |
|---|---|
| [テスト戦略](./testing-strategy.md) | 赤くなったときの判断手順（本ファイルへの導線） |
| [`sprint-development-rules.md`](../rules/sprint-development-rules.md) `SD-2` | テストのスキップ・無効化で緑にしない規律（本レジストリの濫用防止と表裏） |
| Issue #145 | `sp-8-auth.spec.ts` の Cookie タイミング問題の恒久対応（**解決済み・本 PR でクローズ**） |
| Issue #158 | 本レジストリを作成した Issue（背景） |
| Issue #223 | 登録要件の厳格化・`tools/check_flaky_registry.py` による賞味期限切れ検知（本更新） |
| `tools/check_flaky_registry.py` | 登録要件違反・賞味期限切れの機械検査（`run_checks.sh` 配線済み） |
