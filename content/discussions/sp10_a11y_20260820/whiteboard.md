<!-- discussion_whiteboard:auto -->
# 🧑‍🏫 議論ホワイトボード: SP-10（誰でも操作できる）の実装方針を着手前に確定する: Actions 停止下での a11y 機械ゲート・キーボード完走・レスポンシブ・画像方針

- 議題ID: `sp10_a11y_20260820`
- 論点: 対象は GitHub Issue #181（SP-10・sp:8・P1-MVP）。参照要件は US-15 / E-13 / E-14 / E-15 / E-16 / E-17、対応 AC-9、関連 NFR-10〜NFR-15 / NFR-26 / NFR-27。操作レビュー手順（user-story-map.md §5.3 SP-10 が正本）は 4 項目: (1) マウスに触れず Tab と Enter だけで 検索 → 一覧 → 詳細 → 一覧 を完走しフォーカスが常に見える (2) スマートフォン幅で破綻しない (3) ブラウザ拡大 200% で破綻しない (4) CI で axe と Lighthouse（Accessibility = 100）が通る。

【ユーザー確定事項（2026-08-20 JST・SD-3 第 2 系統の確認済み回答）】手順 4 の判定手段は Issue #173 の案 (a) を採る = Lighthouse をセッションがローカル実行して tools/run_checks.sh に配線する。Accessibility 100 は blocking ゲート、Performance は計測値の記録のみでブロックしない。あわせて user-story-map.md §5.3 SP-10 手順 4 と ui-ux-guidelines.md §9 の CLS 判定文言を実際に実行できる手段と一致させる。この決定は議論で覆さない（議論するのは『どう実装するか』であって『採るかどうか』ではない）。

【確認済みの事実（実ファイルから採取）】
- 実行基盤: GitHub Actions は停止中（#77・A-6・status:blocked）。機械ゲートは tools/run_checks.sh のみ（Lint / tsc --noEmit / vitest run / playwright test / check_architecture_boundaries.py / check_ui_dimensions.py / check_contrast.py / check_cjk_markdown.py --changed / self_review_check.py）。各チェックは RUN_CHECKS_TIMEOUT（既定 300 秒）付き、E2E だけ E2E_TIMEOUT_SEC。SKIP_E2E=1 で E2E を明示スキップできる（SKIP は表示される）。
- Chromium は /opt/pw-browsers/chromium にプリインストール、PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers・PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1。playwright install は実行しない。Lighthouse は package.json の依存にもスクリプトにも存在しない（grep 0 件）。
- axe は配線済み: e2e/axe.ts が @axe-core/playwright の AxeBuilder を型キャスト付きで生成、e2e/a11y.spec.ts が一覧画面（/ja で検索実行後）と詳細画面（/ja/repos/octostub/octo-widgets）で serious/critical 違反 0 件を検証。e2e/sp-9-a11y.spec.ts も別途存在。E2E は e2e/stub/server.mjs のスタブ GitHub API に対して実行される。
- フォーカスリング（#179・sp:2・priority:high）: app/globals.css の --ring はライト oklch(0.708 0 0) / ダーク oklch(0.556 0 0)。button.tsx / input.tsx はいずれも 'outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50'。ring に /50 の不透明度が掛かるため実効コントラストがさらに落ちる。実測 2.51:1 で WCAG 2.2 SC 1.4.11（非テキストコントラスト 3:1）を満たさない。ui-ux-guidelines.md §7.3 は『:focus ではなく :focus-visible』『outline-none を単独で書かない』『リングのコントラストは 3:1 以上・太さ 2px 相当以上』を既に規定済み。コントラストの機械検査は tools/check_contrast.py（run_checks.sh 組み込み済み）だが、ring の 3:1 判定を見ているかは未確認。
- ライブリージョンの入れ子（#180・sp:1・priority:high）: app/[locale]/page.tsx:300 に <section id="search-status" aria-live="polite"> があり、その中の <Suspense fallback={<LoadingIndicator/>}> が展開する LoadingIndicator は自身が role="status" + aria-live="polite" を持つ（src/ui/loading-indicator.tsx:19-20）。入れ子のライブリージョンで二重読み上げのリスクがある。RepositoryList の 0 件 role="status"（src/ui/repository-list.tsx:37）と ErrorNotice の role="alert"（src/ui/error-notice.tsx:57）は section の外にあり、コメントで意図が明記されている。
- ルート変更時のフォーカス移動（E-15 の 🔴 必須項目）: grep で tabIndex は app / src/ui の .tsx に 1 件も無い。ui-ux-guidelines.md §7.1 が要求する『結果一覧の見出しに tabIndex={-1} を付け、検索実行・ページ送り・ソート変更の完了後にその見出しへ focus() を移す』は未実装。ただし本アプリの検索フォームは JS を持たない GET フォーム（E-8 / NFR-3）でページ全体が再読み込みされる点、ページ送り・ソート・件数切替が <a>/<form> ベースである点を踏まえて、そもそも client component を増やす必要があるのかから検討すること。
- 画像（US-15 / E-17）: repository-list.tsx:58 は <img src={avatarUrl + '?s=80'} alt={item.owner.login} width={40} height={40} className='size-10' loading='lazy'>、repository-detail.tsx:56 は alt=""。ui-ux-guidelines.md §7.4 は『オーナー名がテキストとして隣接表示される文脈では alt=""（装飾扱い）』と確定済みで、一覧はカード内にリポジトリ名（owner/repo 形式）が隣接表示される。next/image は INF-11 により使わない方針がコメントで明記されている。US-15 は『オーナーアイコンが最適化配信され、読み込み時にレイアウトがずれない』（NFR-6 / NFR-1）。
- viewport: app/[locale]/layout.tsx に viewport export は無い（grep 0 件）。metadata export のみ。
- レスポンシブ: 200% 拡大・スマートフォン幅の破綻を検出する自動テストは存在しない（E2E は既定ビューポートのみ）。

【争点】
A) Lighthouse をどう run_checks.sh に配線するか。lighthouse を npm 依存に足すか npx 実行か、対象 URL をどう用意するか（next build && next start か、E2E と同じ e2e/stub/server.mjs 前提の起動か、既に走っている playwright の webServer を再利用できるか）、Chromium バイナリ（/opt/pw-browsers/chromium）をどう Lighthouse に渡すか（CHROME_PATH）、Accessibility 100 の blocking 判定と Performance の記録のみをどう実装して run_checks のサマリー表に載せるか、実行時間とタイムアウト（既定 300 秒）に収まるか、収まらないなら専用タイムアウトを設けるか。**採らない案は『採らない』と明言すること**（例: Lighthouse CI（lhci）サーバーを立てる案、Actions 復旧を待つ案）。
B) axe（E-13）の現状カバレッジで『WCAG 2.2 AA を目標として宣言し自動検証可能な範囲を組み込む』と言えるか。足りないなら何を足すか（検査対象画面・状態（読み込み中 / 0 件 / エラー / ログイン済み）・withTags による WCAG 2.2 ルールセット指定・serious/critical のみに絞っている現在の閾値の妥当性）。宣言そのものをどのドキュメントのどこに書くか（新しい SSOT を作らない）。
C) E-15（キーボード完走 + フォーカス可視）の実装位置。#180 の入れ子解消と #179 のリングコントラスト是正を含む。GET フォームでページ全体が再読み込みされる本アプリで、§7.1 の『見出しへ focus() を移す』は本当に必要か（必要なら client component をどこに置くか / 不要ならガイドライン §7.1 の適用範囲を書き換えるべきか）。--ring トークンの値を変えるのか、ring の /50 不透明度をやめるのか、ring-offset を足すのか、ダークとライトで別値にするのか。**トークンを変えると全画面に波及する**点と、check_contrast.py の検査範囲を ring まで広げるかを併せて決める。
D) E-16（レスポンシブ・200% 拡大）を E2E でどう機械判定するか。『破綻しない』を判定可能な述語に落とす（候補: 横スクロールが発生しない = document.scrollingElement.scrollWidth <= clientWidth、要素の重なり検出、主要導線が操作可能なこと、テキストの折り返し）。ビューポートは何を使うか（375px / 320px / 1280px）。200% 拡大を Playwright でどう再現するか（deviceScaleFactor ではなく viewport 幅を半分にするのが実質等価か、CSS zoom か、--force-device-scale-factor か）。誤検知でルーティンを止めない設計にすること。
E) fan-out(4) のファイル非重複分割は妥当か。想定は R1 判定基盤（tools/run_checks.sh・lighthouse 実行スクリプト・package.json）/ R2 キーボードとフォーカス（app/globals.css・src/ui/components/*.tsx・app/[locale]/page.tsx のライブリージョン）/ R3 レスポンシブと画像（src/ui/repository-list.tsx・src/ui/repository-detail.tsx・app/[locale]/layout.tsx）/ R4 E2E とドキュメント（e2e/*.spec.ts・docs/**）。R2 と R3 がどちらも src/ui を触る点、R4 の E2E が R2/R3 の実装に依存する点をどう捌くか（契約先行 → 依存役先行 → 並行実行のパターンが docs にある）。分割を変えるべきなら具体的なファイル割り当てを示すこと。
- 参加者: `gate_infra`, `a11y_impl`, `e2e_verify`, `docs_trace`
- 投稿数: 0
- 更新: 2026-08-20T11:19:10+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

_（まだ投稿がありません）_
