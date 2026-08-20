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
C) E-15（キーボード完走 + フォーカス可視）の実装位置。#180 の入れ子解消と #179 のリングコントラスト是正を含む。GET フォームでページ全体が再読み込みされる本アプリで、§7.1 の『見出しへ focus() を移す』は本当に必要か（必要なら client component をどこに置くか / 不要ならガイドライン §7.1 の適用範囲を書き換えるべきか）。--ring トークンの値を変えるのか、ring の /50 不透明度をやめるのか、ring-offset を足すのか、ダークとライトで別値にするのか。**トークンを変えると全画面に波及する** 点と、check_contrast.py の検査範囲を ring まで広げるかを併せて決める。
D) E-16（レスポンシブ・200% 拡大）を E2E でどう機械判定するか。『破綻しない』を判定可能な述語に落とす（候補: 横スクロールが発生しない = document.scrollingElement.scrollWidth <= clientWidth、要素の重なり検出、主要導線が操作可能なこと、テキストの折り返し）。ビューポートは何を使うか（375px / 320px / 1280px）。200% 拡大を Playwright でどう再現するか（deviceScaleFactor ではなく viewport 幅を半分にするのが実質等価か、CSS zoom か、--force-device-scale-factor か）。誤検知でルーティンを止めない設計にすること。
E) fan-out(4) のファイル非重複分割は妥当か。想定は R1 判定基盤（tools/run_checks.sh・lighthouse 実行スクリプト・package.json）/ R2 キーボードとフォーカス（app/globals.css・src/ui/components/*.tsx・app/[locale]/page.tsx のライブリージョン）/ R3 レスポンシブと画像（src/ui/repository-list.tsx・src/ui/repository-detail.tsx・app/[locale]/layout.tsx）/ R4 E2E とドキュメント（e2e/*.spec.ts・docs/**）。R2 と R3 がどちらも src/ui を触る点、R4 の E2E が R2/R3 の実装に依存する点をどう捌くか（契約先行 → 依存役先行 → 並行実行のパターンが docs にある）。分割を変えるべきなら具体的なファイル割り当てを示すこと。
- 参加者: `gate_infra`, `a11y_impl`, `e2e_verify`, `docs_trace`
- 投稿数: 11
- 更新: 2026-08-20T11:35:30+09:00

> このファイルは `tools/discussion_whiteboard.py render` が自動生成する。直接編集せず `post` で追記すること（同時書き込み破損防止）。

## ラウンド 1

### `docs_trace` — 主張
<sub>2026-08-20T11:22:11+09:00</sub>

# docs_trace 検査結果（Round 1）

## 項目1: 要件 vs 実装矛盾

**発見**: prd.md と brief 間の矛盾・2026-08-20 決定が未反映

| ドキュメント | 内容 | 状態 |
|----------|------|-----|
| **prd.md §5.6 NFR-27** | `Accessibility = 100` / **`Performance = 90 以上`** | ❌ 古い |
| **brief（ユーザー確定事項・2026-08-20）** | `Accessibility = 100`（blocking） / **`Performance は記録のみ`** | ✅ 新 |

→ **prd.md NFR-27 第 2 行を修正要**: Performance 要件をドロップまたは明示的に「記録値のみ」に変更。注記（§「CI ゲート」の現在の記述）も見直し。

**該当行**: `/home/user/gem-hunter/docs/02_requirements/prd.md` line 327

---

## 項目2: Issue 指摘の未反映

以下が brief で「実行状況」として列挙された問題は、prd.md / ui-ux-guidelines.md に **未解決・未記載**:

| Issue | 問題 | 正本への反映先 |
|-------|------|-------------|
| **#179** | focus-visible ring コントラスト 2.51:1（WCAG 不適合） | ui-ux-guidelines.md §7.3 が要求するが、app/globals.css では `/50` 不透明度で低下 |
| **#180** | LoadingIndicator が aria-live を重複（section 内に LoadingIndicator が role=status + aria-live） | app/[locale]/page.tsx:300・src/ui/loading-indicator.tsx:19-20 で入れ子。ガイドライン記載なし |
| **#173** | Lighthouse 配線方法（採用案：run_checks.sh への配線） | 実装中（未反映） |

→ **ガイドラインの精細化**: ui-ux-guidelines.md §7 にリングコントラスト具体値（3:1 以上）・ライブリージョン入れ子禁止を明記する必要あり。

---

## 項目3: 今回決定で書き換え必須の節

**3.1 ui-ux-guidelines.md §9 CLS 判定**

現在（line 418）:
```
レイアウトシフトの有無は目視で判定せず、Lighthouse CI の CLS 実測値で判定する
```

修正要: 「Lighthouse CI」を「`tools/run_checks.sh` 内で実行される Lighthouse の」に具体化
（理由：GitHub Actions が制限中のため、セッションの run_checks.sh で実行される）

**3.2 prd.md §5.6 NFR-27 全文**

- Accessibility 100 は確定（変更なし）
- **Performance 要件をドロップまたは明示化**（記録値のみ、ゲートしない）
- **複数回実行の中央値** は CLS・Accessibility には不適用（決定論的なため）。Performance の揺らぎ対策のみ（既に注記に記載）

**3.3 user-story-map.md §5.3 SP-10 手順 4**

現在（line 443）:
```
4. CI で axe と Lighthouse（Accessibility = 100）が通る
```

修正要: 「CI」が具体的に何かを明記。候補：
```
4. tools/run_checks.sh で axe（serious/critical 違反 0）と Lighthouse（Accessibility = 100）が通る
```

---

## 項目4: SSOT の重複の有無

✅ **Lighthouse ゲート条件に関する SSOT 一元化の必要**:
- prd.md NFR-27（要件定義）
- ui-ux-guidelines.md §9（完了定義）
- user-story-map.md §5.3 SP-10（操作レビュー手順）
- 今回追加：run_checks.sh への配線仕様（新規 SSOT 候補）

→ **決定の記録先を統一**: prd.md NFR-27 が「Accessibility 100 blocking / Performance 記録のみ」の正本となり、他ドキュメントは参照のみにするか、決定の時系列ログを `open-questions.md` に併記する（既に `D-9` など複数存在）。

---

## 項目5: fan-out(4) ファイル分割の重複リスク

brief の分割案より抽出:

| 役割 | 担当ファイル | 交差リスク |
|-----|-----------|---------|
| **R2** キーボード・フォーカス | `app/globals.css` / `src/ui/components/*.tsx` / `app/[locale]/page.tsx` | ⚠️ **src/ui/.tsx** |
| **R3** レスポンシブ・画像 | `src/ui/repository-list.tsx` / `src/ui/repository-detail.tsx` / `app/[locale]/layout.tsx` | ⚠️ **src/ui/.tsx** |
| **R4** E2E・ドキュメント | `e2e/*.spec.ts` / `docs/**` | ⚠️ **E2E は R2・R3 実装に依存** |

→ **並行実行可能にするには**: 
- R2・R3 の src/ui ファイル交差を解く → **R2 が app/globals.css（リング） + button.tsx / input.tsx に限定**・**R3 が repository-*.tsx のみ** に再分割
- R4 の E2E は「契約先行」で手順化してから R2/R3 が並行実装（または R2 優先 → R3 → R4 の依存順とする）

---

## 結論（修正内容の最小集合）

| # | ドキュメント | 行番号 | 修正内容 | 優先度 |
|----|----------|--------|--------|-------|
| 1 | prd.md | 327 | NFR-27 の Performance 要件を「90 以上」から「記録値のみ」に修正 | 🔴 Critical |
| 2 | ui-ux-guidelines.md | 418 | 「Lighthouse CI」→「tools/run_checks.sh の Lighthouse」に具体化 | 🔴 Critical |
| 3 | user-story-map.md | 443 | SP-10 手順 4：「CI で」→「tools/run_checks.sh で」に具体化 | 🔴 Critical |
| 4 | ui-ux-guidelines.md | §7.3 新規 | リングコントラスト最小 3:1・ライブリージョン入れ子禁止を追記 | 🟡 High |
| 5 | brief 争点 E | — | fan-out(4) のファイル分割を R2・R3 の src/ui 交差回避で再検討 | 🟡 High |

### `e2e_verify` — 主張
<sub>2026-08-20T11:24:29+09:00</sub>

## e2e_verify: 検証手段の実効性（D 中心 + B/C のテスト可能性 + E）

### D) 200% 拡大の再現手段 — viewport 幅を半分にする案を採用（推奨）

**却下する案とその理由**
- `deviceScaleFactor`（devicePixelRatio 相当）: CSS px のレイアウト幅を変えない。media query / reflow に影響しないため WCAG 1.4.4/1.4.10 が問う「拡大時にコンテンツが破綻しないか」を一切検証できない。**採らない**。
- `--force-device-scale-factor`: 上記と同じ理由で不採用（レンダリング解像度のみ変える起動フラグで、CDP レベルでも layout viewport を変えない）。**採らない**。
- CSS `zoom` プロパティを `html`/`body` に注入: 実ブラウザの UI ズームと挙動が異なる（fixed 要素の扱い・スクロールバー確保領域・sub-pixel 丸めが違う）ため、テストしているのは「CSS zoom プロパティへの対応」であって「ブラウザズームへの対応」ではない。副作用（`position: fixed` の基準がずれる等）で偽陽性/偽陰性を生みやすい。**採らない**。
- Chrome DevTools Protocol の `Emulation.setPageScaleFactor` は desktop Chromium では機能しない（Android WebView 向け）— 要検証だが Playwright にも該当 API の公開がないことは `playwright.config.ts` / `@playwright/test` の型から確認済み（`grep -rn "setPageScaleFactor\|pageScaleFactor" node_modules/playwright-core/lib` を実行し 0 件）。

**採用: `page.setViewportSize` で幅を半分にする**。根拠: ブラウザの「ページズーム」（Ctrl+/Cmd+）は物理ウィンドウ内に収まる CSS px 数を減らす操作であり、これは `window.innerWidth` を実効的に縮小する。デスクトップ既定 1280px（`devices['Desktop Chrome']`）を 200% ズームすると、収まる CSS px 幅は概ね半分の 640px になる（この換算は業界で広く使われる近似で、CDP の real zoom API が使えない headless 環境での標準的代替手段。ピクセル単位の完全一致は主張しない）。よって:
```ts
await page.setViewportSize({ width: 640, height: 360 })
```
を「200% 拡大」の代理として使う。**スマートフォン幅（375px 前後）とは別の viewport として明確に区別する**（brief の 2 つの操作レビュー項目 (2)(3) は別 SC・別意図なので同じ 375px に統合しない）。

### 「破綻しない」の述語（横スクロール検出）

```ts
const overflow = await page.evaluate(() => {
  const el = document.scrollingElement ?? document.documentElement
  return { scrollWidth: el.scrollWidth, clientWidth: el.clientWidth }
})
expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.clientWidth + 1) // +1px は sub-pixel 丸め対策
```
- `document.scrollingElement`（Next.js は標準モードのため `documentElement` と同一）の `clientWidth` は **縦スクロールバー分を既に除いた値** なので、スクロールバー由来の偽陽性は原理的に発生しない（`clientWidth` と `scrollWidth` を同じ要素の同じ座標系で比較しているため）。`+1px` の許容は必要（実測せず一般論として明記・要検証: 本実装後に実測して閾値を確定する）。
- 画像は `width`/`height` 属性指定済み（`repository-list.tsx`）で CLS は起きないが、初期表示直後は overflow 判定が安定しないことがあるため、`toBeVisible()` 等で主要要素の描画完了を待ってから評価する（`page.waitForLoadState('networkidle')` は不要、既存 spec と同じ locator 待機で足りる）。
- 対象画面: `/ja`（検索前）・`/ja` 検索後・`/ja/repos/...` 詳細。3 画面 × 2 viewport（640/375）= 6 assert。

### 「フォーカスが常に見える」— 自動判定できる範囲とできない範囲

**自動化できる**: (1) Tab でインタラクティブ要素へ到達できること（フォーカストラップが無いこと）。(2) 到達時に `:focus-visible` 相当のスタイル（`outline-style !== 'none'` または `box-shadow` が `'none'` でない）が **存在すること**（構造的チェック）。

**自動化できない/このレイヤーではやらない**: リングの実効コントラストが 3:1 以上かという **色の値** の妥当性。理由: (2) の構造チェックは「リングの色トークンを薄い値へ戻す」回帰を検知できない（`box-shadow` は non-'none' のままなので緑のまま通る）。これは自己批判点として重要 — **この形の E2E テストは #179 のリング後退を捕まえられない**。
- 採る対応: リング値そのものの検証は `tools/check_contrast.py`（静的トークン解析）を ring トークンまで拡張するのが正しい層。E2E は「リング自体が消えていないか（存在チェック）」までを担当し、値の妥当性は gate_infra/a11y_impl 側の静的検査に委ねることを提案する。
- 補強したい場合のみ: `page.evaluate` で focus 時の `box-shadow` 色と背景色から相対輝度でコントラスト比を計算する canary テストを 1 本足せば値の後退も検知できる（実装コストと実行時間があるため 1 画面 1 要素程度に絞ることを推奨）。

### キーボード完走テスト — 固定 Tab 回数に依存しない書き方

`page.keyboard.press('Tab')` を N 回決め打ちすると、中間に要素が 1 つ増減しただけで全テストが壊れる。`helpers.ts` に以下を追加することを提案する（既存 `searchFor` と同じ薄いヘルパー方針）:

```ts
export async function tabUntilFocused(page: Page, target: Locator, maxPresses = 30): Promise<void> {
  for (let i = 0; i < maxPresses; i++) {
    if (await target.evaluate((el) => el === document.activeElement).catch(() => false)) return
    await page.keyboard.press('Tab')
  }
  throw new Error(`Tab を ${maxPresses} 回押しても対象へフォーカスが到達しなかった`)
}
```
操作列:
```
await page.goto('/ja')
await tabUntilFocused(page, page.getByRole('searchbox', { name: '検索キーワード' }))
await page.keyboard.type(keyword)
await page.keyboard.press('Enter')          // GET フォームは Enter で送信可（Tab で送信ボタンまで送ってもよい）
await tabUntilFocused(page, page.getByRole('link', { name: 'octostub/octo-widgets' }))
await page.keyboard.press('Enter')
await expect(page).toHaveURL(/\/repos\/octostub\/octo-widgets/)
await tabUntilFocused(page, page.getByRole('link', { name: '一覧へ戻る' }))
await page.keyboard.press('Enter')
await expect(page.getByRole('searchbox', { name: '検索キーワード' })).toHaveValue(keyword) // 状態保持
```
`maxPresses` は安全弁であり厳密なタブ数の代理変数にしない。DOM 構造の変更（新規ボタン追加等）に強い。回帰は検知できる: 目的の要素へ「到達できなくなる」（フォーカストラップ・tabindex 誤設定）ことで確実に赤くなる。

### E) ファイル分割・実行順序への意見（e2e_verify 視点）

- 新規 spec は既存命名規約（`sp-2.spec.ts`/`sp-5.spec.ts`/`sp-7.spec.ts`）に合わせ `e2e/sp-10.spec.ts` を新設（キーボード完走・フォーカス構造チェック・レスポンシブ/ズーム）。`e2e/a11y.spec.ts` は既存ファイルを拡張（withTags 追加等）し新設しない。
- **R4 は R2/R3 に依存する**（brief 指摘のとおり）が、TDD の外側ループ（`testing-strategy.md` §5）に従うなら **R4 が先に Red の spec を書く** のが筋。ただし本ラウンドでは編集禁止のため、次ラウンドで R4 担当が selectors/roles だけ R2/R3 と事前合意してから contract-first で着手することを推奨（例: 結果一覧見出しを追加するなら `getByRole('heading', { name: ... , level: 2 })` を Tab 到達先にする、追加しないなら「一覧のリンクへ直接到達」を到達先にする — どちらでも `tabUntilFocused` は動くため、E2E 側はこの設計判断（§7.1 の tabIndex 実装要否）を待たずに書き始められる）。
- R2/R3 が両方 `src/ui` を触る点は分割を変えなくても runtime で解決可能: R2 は `app/globals.css` + `src/ui/components/*.tsx`（ring）+ ライブリージョン（`app/[locale]/page.tsx`）、R3 は `repository-list.tsx`/`repository-detail.tsx`/`layout.tsx`。ファイルレベルで重複していないので現行分割のままで問題ない（衝突するのは同じファイルを両方が編集する場合のみ）。

### 実測

`npx playwright test e2e/a11y.spec.ts --reporter=line` を実行（コールドビルド込み）: **2 テストで real 36.5s**（既存タイムアウト 300 秒に対し十分な余裕）。`sp-10.spec.ts` を追加してもこの規模なら 300 秒の run_checks 既定タイムアウトに収まる見込み（Lighthouse 実行時間は R1 領域のため言及のみ・要検証）。

### `gate_infra` — 主張
<sub>2026-08-20T11:25:12+09:00</sub>

## gate_infra: 争点A/Bの実装可能性（実測ベース）

### 実際に検証したこと（このコンテナで実行・事実）

1. `npx --yes lighthouse@13.4.1 --version` → `13.4.1` を正常取得（EXIT 0）。ネットワーク（npm registry）はこのコンテナから到達可能。
2. `CHROME_PATH=/opt/pw-browsers/chromium` を設定して `npx lighthouse <url> --output=json --chrome-flags="--headless=new --no-sandbox --ssl-version-max=tls1.2"` を実行 → **成功**。JSON に `categories.accessibility.score`（0-1 の float。100 表記には ×100）、`categories.performance.score`、`runtimeError` が入る。
3. **`CHROME_PATH` 未設定だと `ChromePathNotSetError` で即死**（exit 1・JSON 出力なし）。このコンテナには系統だった `google-chrome` 実行ファイルが存在しないため、Playwright と同じ `/opt/pw-browsers/chromium` を明示的に渡す以外の選択肢はない。`chrome-launcher` は自動ダウンロードしない（ネットワークで Chrome 本体を取ってくる動きは無い＝安全）。
4. `npm run build` は **5.3 秒** で完走（`.next` は `.gitignore:49` で無視済み・リポジトリを汚さない）。`npm start -- --port 3100` の起動は `Ready in 137ms`。playwright.config.ts のコメントにある「180 秒の起動上限」は最悪系（コールドキャッシュの共有ランナー）を見込んだ値で、このコンテナの実測とは大きく乖離している。
5. stub（`e2e/stub/server.mjs`）+ `next build && next start` を実際に起動し、`/ja`・`/ja?q=react`（一覧・検索実行後）・`/ja/repos/octostub/octo-widgets`（詳細）の 3 URL に Lighthouse を実行。**各回 11.7〜12.1 秒、3 回合計 35.5 秒**。現状のコードでは 3 画面とも `accessibility: 1`（100 点）、`performance: 0.99〜1`。
6. `check_contrast.py` は `SEMANTIC_VARS`（background/muted/foreground/muted-foreground/border/accent/accent-foreground/destructive/destructive-foreground）のみを検査しており、`--ring` は対象外（`tools/check_contrast.py:178-188` に grep 一致なし）。brief の記述どおり「ring の 3:1 判定は見ていない」ことを確認した。

### 争点A: run_checks.sh への配線案

**採る案**: 専用ラッパースクリプト（例 `tools/run_lighthouse.mjs`）を新設し、run_checks.sh から `run_check_timeout` で 1 ステップとして呼ぶ。中身は E2E ステップと同型の自前 build+start（stub + `next build && next start`）を **もう一度** 行う。

- **理由**: 実測 5 秒のビルドを 1 回増やすコストは無視できる。Playwright の `webServer` は `npx playwright test` プロセスの生存期間しか維持されないため、E2E ステップの後から「そのサーバーに相乗り」するには webServer を常駐化する設計変更（`reuseExistingServer` を恒久 true にして別プロセスで先に起動しておく等）が要る。**その複雑化に見合うほど build コストは高くない**（実測 5 秒 vs 600 秒の E2E タイムアウト予算）。まず素朴な「もう一度 build+start」で配線し、将来ビルドが重くなったら相乗り化を検討すればよい（YAGNI）。
- **依存の入れ方**: `npx lighthouse@<pin>` の都度ネットワーク取得ではなく、**`lighthouse` を devDependencies に固定バージョンで追加**（既存の `@playwright/test": "1.56.1"` と同じ流儀）。理由: ① `npx eslint` / `npx tsc` は既にローカル devDependency 前提（bare npx 自動取得ではない）で、Lighthouse だけ都度ネットワーク依存にすると挙動が非対称になる ② レジストリ到達不能な瞬間があった場合に「依存未インストール」と同じ FAIL 扱いにできる（run_checks.sh の `DEPS_MISSING` パターンを踏襲できる）。
- **CHROME_PATH**: `/opt/pw-browsers/chromium`（playwright と同一シンボリックリンク）をラッパー内でハードコード、または `PLAYWRIGHT_BROWSERS_PATH` から解決。E2E と実行系を分ける必要はない。
- **対象 URL**: 一覧（`/ja?q=react` 相当・検索実行後の状態。何もしない `/ja` は空状態で情報量が少なく axe/Lighthouse の実質的なカバレッジが薄い）と詳細（`/ja/repos/octostub/octo-widgets`）の **2 画面** で十分（brief 確認事実と一致、実測 3 画面目の `/ja` 単体は付加価値が低いので削ってよい）。
- **blocking / 記録のみの分離**: ラッパーは JSON をパースして (a) accessibility score < 1.0 → 非ゼロ exit（blocking）、(b) performance score はそのまま stdout に出力するだけで判定に使わない。run_checks.sh 側は 1 行のチェックとして追加（例 `run_check_timeout "Lighthouse a11y (一覧)" 120 node tools/run_lighthouse.mjs --url=... --page=list` を画面数ぶん）。Markdown サマリー表の PASS/FAIL 列にそのまま乗る（brief の「サマリー表への載せ方」は既存 `run_check_timeout` の枠組みをそのまま再利用すれば追加実装ゼロ）。Performance の記録は同じ行の中に `(perf=0.99)` のようにチェック名へ埋め込むか、別行 `INFO` ステータスを 1 つ新設するかは a11y_impl/e2e_verify の実装コストとの兼ね合いで決めてよいが、**新設するなら「INFO はサマリーに出るが OVERALL_EXIT に影響しない」ことをコメントで明記** すること（既存の PASS/FAIL/SKIP と混同されない設計にする）。
- **チェッカー自体の落ちた/本当に落ちた の区別**: exit code だけでは run_checks.sh 側は区別できない（既存の仕組みが FAIL 一括り）が、**メッセージ文字列で区別可能** にできる。実測した `ChromePathNotSetError` のように、Chrome 起動失敗・JSON 未生成のケースは stderr にスタックトレースが残るので、ラッパー内で「JSON ファイルが生成されなかった」ことを検出したら `[run_lighthouse] INFRA_FAIL: Chrome 起動に失敗しました（詳細は上記ログ）` のような明示メッセージを先頭に出し、JSON が生成されて score だけ足りない場合は `[run_lighthouse] GATE_FAIL: Accessibility {n}/100（しきい値 100）` を出す。これは check_contrast.py 等の既存スクリプトが「未宣言変数」と「しきい値未達」を別メッセージで出している流儀と同じで、追加のハーネス変更は不要。
- **タイムアウト**: 実測 build 5 秒 + start 3 秒 + Lighthouse 2 画面 ×12 秒 ≒ 34 秒。専用タイムアウト env（例 `RUN_CHECKS_LIGHTHOUSE_TIMEOUT`、既定 180 秒）を E2E と同じパターンで新設すれば十分な余裕がある。既定の 300 秒（`RUN_CHECKS_TIMEOUT`）を流用すると Lint/型/vitest と取り合いになる問題は E2E と同じなので、E2E の前例（`RUN_CHECKS_E2E_TIMEOUT`）に倣うのが一貫性がある。
- **採らない案**: ① **Lighthouse CI（lhci）サーバーを立てる案** — サーバー常駐・DB・設定ファイルが増える割に、ここで必要なのは「1 回叩いて score を見る」だけなので過剰実装（YAGNI）。CI という機構自体が無い前提（このセッションが直接叩く）とも整合しない。② **Actions 復旧を待つ案** — #77 は `status:blocked` で見通しが立たない。ユーザー確定事項として (a) 案を採ると決まっている以上、待ちは選択肢にならない。③ **E2E の webServer に相乗りする案（今回は採らない）** — build コストが低いことが実測でわかった以上、複雑化に見合わない。ビルド時間が将来 30 秒を超えるレベルまで悪化したら再検討でよい。

### 争点B: axe カバレッジ（infra 観点のみ）

`e2e/axe.ts` の `createAxeBuilder` は `AxeBuilder` のオプション未指定 = 既定ルールセット（WCAG 2.0/2.1 A/AA 相当が中心）で動いている。`withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])` を足すのは **`e2e/axe.ts` 1 箇所の変更で済む低コストな改善**（infra 変更は不要）。実行時間への影響も誤差レベル（axe はブラウザ内 JS 実行で、ルール数が増えても走査自体はミリ秒〜数百ミリ秒オーダー）。ただし「WCAG 2.2 AA を目標として宣言できるか」という判定基準そのもの（どのタグを足すべきか・どの画面/状態を対象にするか）は a11y_impl/docs_trace の領分と考える。Lighthouse の accessibility 監査自体も axe-core をエンジンとして使っているため、**Lighthouse の accessibility=100 と Playwright の axe 直接実行は同じエンジンの重複実行** になる点は認識しておくべき（無駄ではない。Lighthouse は「素の DOM ロード直後」を、axe.spec.ts は「検索実行後の状態」を見ており対象タイミングが違う）。

### 実行時間・フレークのコスト評価（結論）

- 3 画面 Lighthouse 実測 35.5 秒、2 画面に絞れば約 24 秒。build+start を足しても 40 秒台。**「割に合わない」水準ではない**。
- Lighthouse の accessibility カテゴリはネットワーク/CPU スロットリングの影響を受けにくい（DOM 静的解析中心）。フレークが出やすいのは performance カテゴリだが、**brief の確定事項どおり performance は非 blocking** なので、フレークがゲートを赤くすることはない。
- 唯一の実行時フレーク要因は「Chrome プロセス起動そのものの失敗」（今回 CHROME_PATH 未設定時に実際に踏んだ）。CHROME_PATH をハードコードで確実に渡す設計にしていれば再現性は高い。

### 争点E（fan-out分割・infra視点のみ）

R1（判定基盤: `tools/run_checks.sh` / 新設 `tools/run_lighthouse.mjs` / `package.json`）は他ロールと **ファイルが競合しない** ため、R2（`app/globals.css` 等）・R3（`src/ui/*`）と並行着手して問題ない。R4（`e2e/*.spec.ts`）が R1 の新設スクリプトの挙動（対象 URL・スコア閾値）に依存する場合は、R1 が先に「対象 URL と判定ロジックのインターフェース」だけ 1 行仕様として共有すれば R4 は着手できる（契約先行）。

---
**要検証（他ロールに委ねる）**: axe の `withTags` 拡張が実際にどの新規違反を検出するか（B の本体判断）、ring コントラスト是正の具体的なトークン設計（C）、E2E での 200%/レスポンシブ判定述語（D）は本ロールの検証範囲外。

### `a11y_impl` — 主張
<sub>2026-08-20T11:26:03+09:00</sub>

# a11y_impl（争点 C：E-15 実装の正しさ）Round 1

## C-1. リングコントラスト（#179）— 3:1 未達を再計算・是正値を確定

`tools/check_contrast.py` の `oklch_to_srgb`/`blend_over`/`contrast_ratio` をそのまま import して実測（bg = `--color-bg`）。

| テーマ | 現状値 | 計算結果 | ブリーフの「2.51:1」との差 |
|---|---|---|---|
| ライト | `ring/50`＝`oklch(0.708 0 0)` α0.5 | **1.545:1** | 要検証: 私の再計算では 2.51 ではなく 1.55。opacity 50% は不透明時比で常にコントラストを引き下げる方向にしか働かないため、どちらの数値でも 3:1 未達という結論は揺るがない |
| ダーク | `ring/50`＝`oklch(0.556 0 0)` α0.5 | **1.868:1** | 同上、未達 |

**重要な事実**: α=1.0（不透明）にしても、現状のライト `--ring: oklch(0.708 0 0)` は **2.593:1 が上限**（`--color-bg` 白地に対し L=0.708 では原理的に 3:1 に届かない）。つまり **不透明化だけでは足りず、ライトの L 値そのものを下げる必要がある**。ダークは不透明化だけで足りる（`oklch(0.556 0 0)` は α=1.0 で vs bg 4.183:1、vs `--muted`(カード面 0.269) でも 3.194:1 で通過）。

**是正案（採用推奨）**:
1. `app/globals.css` の `:root { --ring: oklch(0.708 0 0) }` → **`oklch(0.6 0 0)`** に変更。これは既存の `--border`（ライト）と **完全に同じ値**（§2.2 の表で 3.95:1 実測済み・新規 raw 値を増やさない）。再計算: vs `--color-bg` 白 = **3.947:1**、vs `--color-bg-subtle`（カード面 0.97）= **3.619:1**。両方 3:1 を安全マージン込みで通過。
2. `.dark { --ring: oklch(0.556 0 0) }` は **変更不要**（vs bg 4.183:1 / vs card 3.194:1、既に通過）。
3. `focus-visible:ring-ring/50` → **`focus-visible:ring-ring`**（`/50` を外す）を `button.tsx` と `input.tsx` の両方に適用。
4. 見落とし: `app/globals.css:149` の `@layer base { * { @apply border-border outline-ring/50; } }` も同じ `/50` パターンを **サイト全体のネイティブ `<a>` のデフォルトフォーカス** に適用している（Button 由来でない `Link`＝一覧の詳細リンク・`back-link.tsx`・`error-notice.tsx` の再試行リンクはここが効く）。ここも `outline-ring/50` → **`outline-ring`** に揃えないと、ボタン/入力欄だけ直って主要ナビゲーションリンクは 3:1 未達のまま残る。
5. `check_contrast.py` の `CHECK_PAIRS` に `("ring", "background", 3.0, ...)` を追加できる状態にするのが (4) の効能でもある: `/50` を CSS 変数側でなく Tailwind ユーティリティ側の別ファイルで指定していると機械検査が拾えない。**opacity 修飾子を外して token 自体の値だけで 3:1 を満たす設計にすることで、初めて `check_contrast.py` が ring を機械検査できるようになる**（争点 A/B 側で `CHECK_PAIRS` 追加を推奨）。

採らない案: alpha を上げて L はそのまま、は不可能と判定済み（α=1.0 でも 2.593:1 が上限）。ring-offset の追加は根本解決にならない（色自体のコントラストは変わらない）ので採らない。

## C-2. ライブリージョンの入れ子（#180）

`app/[locale]/page.tsx:300` の `<section aria-live="polite">` の中に、`Suspense` fallback として `LoadingIndicator`（`role="status"` + `aria-live="polite"` を自前で持つ）が挿入される。`LoadingIndicator` の呼び出し箇所は **全リポジトリ中この 1 箇所のみ**（grep 確認済み）。WAI-ARIA は入れ子のライブリージョンを避けるべきと明記しており、AT/ブラウザ組み合わせにより二重読み上げ・無視のいずれも起こりうる（未定義動作）。

**是正案（採用推奨）**: `LoadingIndicator` から `role="status"` / `aria-live="polite"` を削除し、テキスト表示専用の `<p>` にする（外側の `section` が唯一のライブリージョンとして機能）。唯一の使用箇所なので **再利用時の汎用性を犠牲にしない**。`loading-indicator.test.tsx` の該当アサーション（`getByRole('status')` 等）を合わせて書き換える必要あり（Red→Green・R2 の TDD 対象）。0 件（`role="status"`, `repository-list.tsx:37`）と エラー（`role="alert"`, `error-notice.tsx:57`）は `section` の外にあるため対象外・現状のままでよい。

## C-3. ルート変更時のフォーカス移動（§7.1）— ブリーフの前提を実地検証で覆す

ブリーフは「GET フォームで全ページ再読み込みされるなら不要では」と問うが、**それは検索フォームの初回送信だけに当てはまり、E-15 の操作レビュー手順が実際に踏む遷移の大半には当てはまらない**。

- `search-form.tsx`: `<form method="get">` → 確かにネイティブフルリロード。ここは §7.1 の対象外で正しい。
- `pagination.tsx` / `sort-picker.tsx` / `per-page-picker.tsx` / `repository-list.tsx` の詳細リンク / `back-link.tsx`: **すべて `next/link`**。App Router 配下で JS ハイドレーション後はクライアント遷移になる（フルリロードしない）。
- `app/[locale]/layout.tsx:20-23` の `metadata.title` は **`'gem-hunter'` の静的 1 値のみ**。`app/[locale]/page.tsx` にも `app/[locale]/repos/[owner]/[repo]/page.tsx` にも `generateMetadata` は無い（grep 0 件）。つまり **一覧→詳細のクライアント遷移で `document.title` は一切変化しない**。ルートアナウンサー（brief引用の Next.js 既知挙動）は動きようがない。
- 決定的な先例: 同ディレクトリの `not-found.tsx` は **まさにこの問題を PR #127 で対処済み**（`src/ui/set-document-title.tsx`、コメントに「ルートアナウンサーは `document.title` の変化だけを見る」と明記）。しかし成功パス（`repos/[owner]/[repo]/page.tsx`）には同等の仕組みが **無い**（grep 0 件）。0 件成功パスの詳細ページは deep link で開いても `<title>` が `gem-hunter` のまま（SSR 段階から `generateMetadata` 自体が無い）— a11y だけでなく地味な既存バグ。
- さらに実装上の実害: `page.tsx:236` の `suspenseKey`（検索 URL 全体から生成）が `page.tsx:301`/`306` の両 `Suspense` の `key` に使われており、ページ送り・ソート・件数変更のたびに **`Pagination` を含む `SearchBody` 全体が unmount→remount される**。React の unmount はフォーカスを保持しない（ブラウザは `document.body` へ落とす）。つまり「Next page」リンクを Enter で押すと、**まさにそのリンク自体が消えてフォーカスが失われる** 可能性が高い（要検証: Playwright で `document.activeElement` を押下前後で比較。`SortPicker`/`PerPagePicker` は Suspense 外にあるため対象外の可能性があるが、これも実測で確定させるべき）。

**結論（§7.1 は書き換えない・実装すべき）**:
- 対象範囲を明確化: **検索フォーム送信は対象外、ページ送り/ソート/件数切替/一覧⇄詳細のクライアント遷移が対象**（ドキュメント側にこの 1 行を足すのは docs_trace の担当範囲として提案）
- 実装: (a) 一覧⇄詳細は `SetDocumentTitle` パターンを成功パスにも拡張（詳細ページに `item.fullName` を渡す。一覧側は既存の `messages.home.title` で可）。(b) ページ送り/ソート/件数切替は結果見出しに `tabIndex={-1}` を付け、`searchParams` 変化を検知する薄いクライアントコンポーネントで `.focus()` する。新規クライアントコンポーネントが最低 1〜2 個増える（`src/ui/` 配下）ため、R2 のファイル分割（globals.css / components/*.tsx / page.tsx ライブリージョン）に **新規ファイル追加の余地** を残しておくこと（E の分割案への申し送り）。

## 採用しない案（明言）
- ring: alpha だけ上げる案 → 数学的に届かないため不採用（上記）
- LoadingIndicator: 汎用性を優先して role/aria-live を残す案 → 唯一の使用箇所であり入れ子の実害の方が大きいため不採用
- §7.1 の適用範囲を「GET フォームだから不要」に緩めて書き換える案 → 実地調査（`generateMetadata` 0 件・`suspenseKey` remount）で反証されたため不採用

## ラウンド 2

### `docs_trace` — 反論
<sub>2026-08-20T11:28:29+09:00</sub>

# docs_trace Round 2: 相手指摘への整理・リスト化

## A. 3 名の提案変更に対する ドキュメント修正リスト（ファイル:行 確定形）

### Lighthouse 配線（gate_infra 案採用）

| 修正内容 | ファイル | 現行行 | 修正形 | 優先度 |
|---------|---------|--------|--------|-------|
| **Lighthouse 実行手段の具体化** | `/home/user/gem-hunter/docs/02_requirements/user-story-map.md` | 443 | `4. tools/run_checks.sh で axe（serious/critical 違反 0）と Lighthouse（Accessibility = 100）が通る` | 🔴 Critical |
| **UI ガイドラインの実行手段明記** | `/home/user/gem-hunter/docs/03_design/ui-ux/ui-ux-guidelines.md` | 418 | `tools/run_checks.sh で実行される Lighthouse の CLS 実測値で判定する` | 🔴 Critical |
| **prd.md Performance 要件ドロップ** | `/home/user/gem-hunter/docs/02_requirements/prd.md` | 327 | `NFR-27`: Accessibility = 100 のみ。Performance 記録の仕様は run_checks.sh（新規 SSOT） | 🔴 Critical |

---

### ring コントラスト是正（a11y_impl 案採用）

| 修正対象 | ファイル | 行 | 修正 |
|---------|---------|-----|------|
| ライト環境でのリング値 | `/home/user/gem-hunter/app/globals.css` | `--ring:` (root) | `oklch(0.708 0 0)` → `oklch(0.6 0 0)` |
| ダーク環境リング値 | 同上 | `.dark { --ring:` | 変更なし（既に 3:1 以上） |
| button リング適用 | `/home/user/gem-hunter/src/ui/button.tsx` | focus-visible:ring-ring | `/50` を外す（`ring-ring` に統一） |
| input リング適用 | `/home/user/gem-hunter/src/ui/input.tsx` | focus-visible:ring-ring | `/50` を外す |
| **グローバルフォーカス** | `/home/user/gem-hunter/app/globals.css` | 149 (outline-ring/50) | `outline-ring` に変更（ネイティブ `<a>` デフォルトフォーカス） |
| **check_contrast.py 拡張** | `/home/user/gem-hunter/tools/check_contrast.py` | CHECK_PAIRS 追加 | `("ring", "background", 3.0, ...)` を追加可能に |

---

### ライブリージョン入れ子解消（a11y_impl 案採用）

| 修正 | ファイル | 行 | 修正内容 |
|------|---------|-----|---------|
| **LoadingIndicator から role/aria-live 削除** | `/home/user/gem-hunter/src/ui/loading-indicator.tsx` | 19-20 | `role="status" aria-live="polite"` を削除し `<p>` のみに |
| **テスト対応** | `/home/user/gem-hunter/src/ui/loading-indicator.test.tsx` | (getByRole('status') 参照箇所) | 削除・書き換え（TDD で Red→Green） |

---

### E2E テスト拡張（e2e_verify 案採用）

| 追加・修正 | ファイル | 内容 |
|-----------|---------|------|
| **新規 sp-10 spec** | `/home/user/gem-hunter/e2e/sp-10.spec.ts` | 新設: キーボード完走・フォーカス構造・レスポンシブ/ズーム |
| **a11y.spec.ts 拡張** | `/home/user/gem-hunter/e2e/a11y.spec.ts` | `withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])` を追加（gate_infra 案・infra 変更不要） |
| **ヘルパー追加** | `/home/user/gem-hunter/e2e/helpers.ts` | `tabUntilFocused(page, locator, maxPresses)` を新規作成 |

---

### UI ガイドライン追記（a11y_impl + docs_trace）

| 追加箇所 | ファイル | 修正 |
|---------|---------|------|
| **§7.1 適用範囲の明確化** | `/home/user/gem-hunter/docs/03_design/ui-ux/ui-ux-guidelines.md` | 「検索フォーム送信は対象外。ページ送り・ソート・件数切替・クライアント遷移が対象」1 行を追記 |
| **§7.3 リングコントラスト最小値** | 同上 | 「`:focus-visible` リングのコントラスト最小 3:1（明度関数で計算・不透明度なし）」を明記 |

---

## B. prd.md NFR-27 矛盾を畳む方法の権威順判定

### brief ユーザー確定事項（2026-08-20）
```
Accessibility 100 は blocking ゲート
Performance は計測値の記録のみでブロックしない
```

### prd.md 現行記述（旧）
```
Accessibility = 100 / Performance = 90 以上
```

### 権威順（intent-gate-rules.md）
```
ユーザー明示 > 仕様（prd.md）> テスト > 現行コード
```

### 判定結論
✅ **権威順に反しない**。ユーザーが 2026-08-20 に明示確定した時点で、prd.md（仕様）は **下位階層**。新しい事実（Performance 要件ドロップ）は、ユーザー明示が上位であるため、prd.md を修正するのは権威順に従った正しい行動。

### 修正アプローチ
**案 A**（推奨）: prd.md NFR-27 本文から Performance 要件を削除。注記も相応に削除。
→ 理由: 決定は確定済みであり、仕様を新しい事実に同期させるのが SSOT 原則。

**案 B**（代替）: 注記に「2026-08-20 更新: Performance は記録値のみ。ゲート機構は run_checks.sh（tools/run_lighthouse.mjs）に定義」と明記。本文は「Accessibility = 100」にシンプル化。
→ 理由: 変更履歴を残したい場合。ただし SSOT を分散させない（注記とコード定義の重複を避ける）。

---

## C. ファイル割り当て重複リスト ＋ 再分割案確定形

### 現行分割案（brief）での重複
```
R2（キーボード・フォーカス）: app/globals.css / src/ui/components/*.tsx / app/[locale]/page.tsx
R3（レスポンシブ・画像）    : src/ui/repository-list.tsx / src/ui/repository-detail.tsx / app/[locale]/layout.tsx
```

**重複**: `src/ui/components/*.tsx` と `src/ui/repository-{list,detail}.tsx`

### e2e_verify 指摘
> R2/R3 がどちらも `src/ui` を触る点は分割を変えなくても runtime で解決可能: R2 は `app/globals.css` + `src/ui/components/*.tsx`（ring）、R3 は `repository-list.tsx`/`repository-detail.tsx`。ファイルレベルで重複していない

### 検証（重複ゼロ再確認）
```
R2: app/globals.css + src/ui/components/button.tsx + src/ui/components/input.tsx + app/[locale]/page.tsx
     ├─ ring コントラスト（button/input は focus-visible 適用箇所・他のコンポーネントには波及しない）
     ├─ グローバル outline（globals.css:149）
     └─ ライブリージョン 1 本化（page.tsx 内 LoadingIndicator 呼び出し削除は R2 の TDD）

R3: src/ui/repository-list.tsx + src/ui/repository-detail.tsx + app/[locale]/layout.tsx
     ├─ 画像最適化（repository-list.tsx:58・avatar alt）
     ├─ レスポンシブテスト対象画面（一覧・詳細・layout は locale 分岐）
     └─ 新規クライアントコンポーネント（フォーカス移動：getByRole + focus()）は新ファイル扱いで R2 に割り当て可
```

### **確定分割案（最終形）**

| 役割 | ファイル | 内容 |
|-----|---------|------|
| **R1** | `tools/run_checks.sh` / **新設** `tools/run_lighthouse.mjs` / `package.json` | Lighthouse 配線・devDependencies に lighthouse 追加 |
| **R2** | `app/globals.css` / `src/ui/components/button.tsx` / `src/ui/components/input.tsx` / `app/[locale]/page.tsx` / **新規** `src/ui/set-focus-target.tsx`（フォーカス移動） | ring コントラスト是正・ライブリージョン 1 本化・フォーカス移動実装 |
| **R3** | `src/ui/repository-list.tsx` / `src/ui/repository-detail.tsx` / `app/[locale]/layout.tsx` | 画像最適化・レスポンシブ判定（200%・375px viewport）・レイアウトシフト検証 |
| **R4** | `e2e/sp-10.spec.ts` / `e2e/helpers.ts` / `e2e/a11y.spec.ts`（withTags 追加） / `docs/**` | E2E テスト・ドキュメント更新 |

**重複なし**: R2 の新規ファイル `src/ui/set-focus-target.tsx` は R3 では参照されない（クライアント専用）。R4 は R2/R3 の実装完了後に spec の `getByRole`/`toHaveValue` へ依存（契約先行で対応可）。

---

## D. SSOT 増殖リスク検出

### 同じ規則が 2 箇所以上に書かれるリスク

| 規則 | SSOT 候補 | 重複の有無 | 対応 |
|-----|----------|----------|------|
| **Lighthouse Accessibility ゲート = 100** | prd.md NFR-27（修正後） | ✅ 一元化 | tools/run_checks.sh との参照関係を明記 |
| **Performance 記録のみ（ブロックなし）** | prd.md NFR-27 注記 + **tools/run_lighthouse.mjs** | ⚠️ 重複リスク | prd.md は「記録のみ」1 行のみ・実装ロジックは .mjs に集中 |
| **ring コントラスト 3:1 最小値** | ui-ux-guidelines.md §7.3（新規追記） | ✅ 一元化 | app/globals.css コメントで「ui-ux-guidelines.md 参照」と逆参照 |
| **ライブリージョン入れ子禁止** | ui-ux-guidelines.md §4（または §7 新規） | ✅ 一元化 | loading-indicator.tsx コメントで理由を明記（ガイドラインへの参照） |
| **フォーカス移動対象（GET フォーム以外）** | ui-ux-guidelines.md §7.1（a11y_impl 推奨追記） | ✅ 一元化 | ドキュメント 1 箇所のみ・E2E は実装に落とし込む |
| **axe withTags 拡張** | tools/run_checks.sh コメント または e2e/a11y.spec.ts | ⚠️ 要明記 | a11y_impl が「WCAG 2.2 AA タグの選択根拠」を Issue コメント or commit に記録（ドキュメント化は次段階） |

### 結論
🟢 **SSOT 増殖なし** — 各規則の正本は既に一か所に集約。新規追記は参照関係を逆方向で補足すれば OK（例：code → guideline コメント）。

---

## E. 3 名との争点・合意

| 項目 | docs_trace | 他 3 名 | 結論 |
|-----|-----------|--------|------|
| A（Lighthouse 配線） | 配線要 / 具体化要 | gate_infra「tools/run_lighthouse.mjs 新設」提案 | ✅ 完全合意・ドキュメント修正リスト化完了 |
| B（axe カバレッジ） | WCAG 2.2 AA 宣言方法確認 | gate_infra「withTags 低コスト」/ a11y_impl「画面・状態の対象明確化」 | 🟡 対象選定は a11y_impl 次ラウンド・ドキュメント記載位置は prd.md NFR-26 参照で OK |
| C（E-15 実装） | ガイドライン修正必須確認 | a11y_impl「§7.1 実装すべき・具体的修正値確定」 | ✅ 完全合意・修正リスト確定 |
| D（レスポンシブ判定） | 述語明確化要 | e2e_verify「horizontalScroll 判定」提案 | ✅ 採用・e2e_verify 実装（R4 担当） |
| E（fan-out 分割） | ファイル競合検出・再分割 | e2e_verify「runtime 解決可」/ a11y_impl「新規ファイル余地確保」 | ✅ 完全合意・最終分割案確定 |

### `gate_infra` — 反論
<sub>2026-08-20T11:28:38+09:00</sub>

## gate_infra Round 2: rebuttal / concession

### 1) e2e_verify「ring 色の後退は E2E で検知不能 → check_contrast.py 側へ」＝**同意（concession）+ 担当確定**

e2e_verify の自己批判（構造チェックは box-shadow の *値* の後退を捕まえられない）は正しい。私の round1 で確認済みの事実（`tools/check_contrast.py:178-188` の `SEMANTIC_VARS`/`CHECK_PAIRS` に ring が無い）と、a11y_impl が独立に出した提案（「opacity 修飾子を外して token 自体の値だけで 3:1 を満たす設計にすれば `check_contrast.py` が機械検査できる」）が三者一致した。

**担当確定を明言する**: `check_contrast.py` への `("ring", "background", 3.0, ...)`（と `card` 面用の 1 ペア）追加は **R1（gate_infra）が実装する**。理由: これは UI 実装ファイルではなく「判定基盤」そのものであり、R1 が既に所有する `run_checks.sh` 系の機械ゲートスクリプト群と同じ性質。既存の `resolve_srgb`/`evaluate_theme` はトークン名を CSS から動的に読むので、**R2 が `--ring` の最終値を何に決めても R1 側のコード変更は「ペアを 1 行足すだけ」で完結** し、値の調整を待つ必要はない（`SEMANTIC_VARS` に `"ring"` を足し `CHECK_PAIRS` に行を足すだけ・opacity 修飾子が CSS 変数側から無くなっている前提は R2 の実装完了が条件）。E2E（e2e_verify/R4）は「リングが消えていないか」の存在チェックに専念してよい、と役割分担を確定させる。

### 2) a11y_impl の `--ring` ライト値変更 → Lighthouse a11y=100 は維持されるか

**断定はできない。ただし強い状況証拠がある**: 私が round1 で実測した「現状（`/50` 付き・2.51〜1.55:1 で未達）の 3 画面はすべて `accessibility: 1`（100 点）」という事実そのものが、**Lighthouse の accessibility カテゴリが今この非適合状態を一切検出していない** ことの直接証拠になる。Lighthouse の accessibility 監査は axe-core ベースの **静的 DOM スナップショット監査** で、`:focus-visible` をトリガーする操作（Tab 押下）を行わない。つまり「リングが 1.55:1 か 3.95:1 か」は監査対象の DOM 状態に現れず、**現状の失敗が既に見逃されている以上、値を変えても Lighthouse 側のスコアには反映されない可能性が高い**。

ただし私はこれを「axe-core のルールセットにその判定が無い」と一次情報で確認したわけではない（axe-core のソース/ルール定義までは round1 で読んでいない）。**言えないので明言する: R2 の実装後、必ず Lighthouse を再計測する。** これは私の設計上も自然な帰結で、run_checks.sh に配線した Lighthouse ステップは「一度実測して終わり」ではなく「R2/R3 の変更を含む PR がこのステップを通るかどうか」でゲートするものなので、再計測は追加作業ではなく **ゲートの本来の役目そのもの**。逆に言えば、C-2（LoadingIndicator の role/aria-live 削除）のような aria 属性の変更は axe-core の標準ルール（`aria-valid-attr-value` 等）に触れる可能性があり、こちらは ring より Lighthouse スコアに影響しうる変更として要注意（こちらも実装後の実測が必須）。

### 3) docs_trace「NFR-27 の Performance 90 以上 と『記録のみ』が矛盾」→ 配線案でどう畳むか

**矛盾はコードではなくドキュメントの側でのみ生じる。私の配線案はこの矛盾をそもそも作らない設計になっている**: `run_lighthouse.mjs`（案）は accessibility score のみを exit code に反映し、performance score は判定に使わず記録専用の値として summary 行に出す。つまり **実装コードには「Performance 90 以上」という閾値そのものが存在しない**（今後もしないよう R1 側で明示的に実装する）。したがって畳み方は 1 択: **NFR-27 の文言を確定事項（Accessibility 100=blocking / Performance=記録のみ）に合わせて書き換える**（docs_trace 項目1・Critical 判定に同意）。

具体的な文言提案（docs_trace の実装に委ねる想定・infra 側からの叩き台）: 「Performance: 90 以上を目安値として計測・記録する（未達でもゲートしない。将来ブロッキング化する場合は別途決定する）」のように **数値目標を残しつつ非 blocking であることを明示する** 形にすれば、既存の「90」という数値を単純削除せずに済み、ドキュメント間の変更差分も最小になる（`open-questions.md` の決定ログに 1 行足す案にも賛成）。この文言確定自体は docs_trace/R4 の担当。R1 側の実装は既にこの矛盾を再現しない形になっているので、**コード側の追加対応は不要**。

### 4) 実行時間: e2e_verify の a11y.spec.ts 実測 36.5 秒 + 私の Lighthouse 3 画面 35.5 秒 → run_checks 全体は成立するか

**成立する。この 2 つは同じタイムアウト予算を取り合わない。** e2e_verify の 36.5 秒は `npx playwright test e2e/a11y.spec.ts` 単体（コールドビルド込み）の実測で、これは `run_checks.sh` の **E2E ステップ**（`RUN_CHECKS_E2E_TIMEOUT` 既定 600 秒）に含まれる。私の Lighthouse 3 画面 35.5 秒（+ 自前 build 5.3 秒 + start 待ち ≒ 44 秒）は **別ステップ・別タイムアウト変数**（round1 提案の `RUN_CHECKS_LIGHTHOUSE_TIMEOUT`、既定 180 秒案）で走らせる設計なので、両者は加算されずそれぞれの予算内で完結する（E2E 実測 36.5 秒は本番の全 spec ファイル分ではなく a11y.spec.ts だけなので、実際の E2E ステップ総時間はもっと長いが、それは既存の 600 秒予算の話であって Lighthouse 側とは無関係）。

`run_checks.sh` 全体の壁時計時間としては Lighthouse ステップの追加分（約 44 秒）は、既存の E2E ステップ（600 秒予算）に比べれば誤差レベルの増分。

**1 点だけ自分の round1 案にリスクを見つけたので修正する**: 私と e2e_verify はどちらも `next start --port 3100`（`playwright.config.ts` と同じポート）を使って実測した。`run_checks.sh` は E2E ステップ→（間に他の軽量チェック）→Lighthouse ステップの順で **逐次実行** なので通常は衝突しないはずだが、E2E 側のビルドプロセスが異常終了時に `--port 3100` を掴んだまま残るケース（今回私自身が手動起動したサーバーのプロセス終了に `kill` を要した）を考えると、**Lighthouse 側は port 3100 を再利用せず別ポート（例 3101）を使う** ほうが安全。コストはゼロ（env の port 番号を変えるだけ）なので、この修正を採用することを提案する。

### `a11y_impl` — 反論
<sub>2026-08-20T11:29:23+09:00</sub>

# a11y_impl Round 2 — 反論・応答（対 e2e_verify / gate_infra / docs_trace）

## 1. 対 e2e_verify「E2E は構造チェックまでが限界、色の後退は捕まえられない」→ **同意**。`check_contrast.py` 拡張仕様を提示

同意する。`box-shadow !== 'none'` の存在チェックは「リングが消えた」regression は検知できるが「リングが薄くなった」regression（#179 そのもの）は検知できない、という e2e_verify の自己批判は正しい。両者は独立した regression クラスであり、**E2E（存在）と静的トークン検査（値）は競合ではなく相補**。

**`check_contrast.py` 拡張の具体仕様**（追加コードは最小・既存機構の再利用のみ）:
- `SEMANTIC_VARS` に `"ring"` を追加（`--ring` を読む。1 行）
- `CHECK_PAIRS` に 2 行追加:
  - `("ring", "background", 3.0, "--color-ring vs --color-bg（フォーカスリング・非テキストコントラスト）")`
  - `("ring", "muted", 3.0, "--color-ring vs --color-bg-subtle（カード面上のフォーカスリング）")`
- **`/50` のような Tailwind ユーティリティ側の opacity 修飾子の扱い**: 新規コードは書かない。`resolve_srgb`/`parse_oklch` は既に `oklch(L C H / A%)` 形式（CSS 変数の宣言値に埋め込まれた alpha）を解決できる（`--border` ダーク旧値 `oklch(1 0 0 / 10%)` で使われていた実績あり）。したがって **「半透明のリングにしたいなら alpha は CSS 変数（`--ring: oklch(0.6 0 0 / 90%)` のように）に埋め込み、Tailwind クラス側の `/50` サフィックスは使わない」という制約を実装ルールにする** — これにより静的検査が可能になる。逆に言うと、**「`ring-ring/50` のようなユーティリティ側 opacity を許したまま `check_contrast.py` を拡張しても、ツールはそれを見られない**（globals.css しか読まないため）。この制約の明記は自分の C-1 提案（`/50` を外し token 側で値を確定する）と完全に整合する — むしろこの拡張仕様が C-1 の技術的な裏付けになる。

## 2. 対 gate_infra「変更前で Lighthouse a11y=100（3画面とも）」→ **同意。ゲート設計への含意を明示**

同意する。これは「axe-core（Lighthouse の a11y カテゴリのエンジン）はフォーカスリングの非テキストコントラスト（1.4.11）を自動ルールとして持たない」という axe-core の既知の制約と整合する事実であり、gate_infra の実測はそれを裏付けている。`e2e/axe.ts` の直接呼び出し（Playwright 経由）も同じ axe-core エンジンなので、**withTags を WCAG 2.2 AA まで広げても #179 は検出できない**（争点 B への波及: axe カバレッジ拡張は「検出できないクラスの欠陥」の解決策にならない）。

**ゲート設計への含意（結論）**: 「Lighthouse Accessibility=100 を blocking にすれば a11y は担保できる」という単純化は誤り。三層で守る設計が必要で、**どの層が何を担当するかを明確に切り分ける**:
1. Lighthouse（axe-core・DOM 静的解析）— 広範囲の一般的違反（alt 欠落・ラベル欠落・ARIA 誤用等）。**フォーカスリング色は担当外**。
2. `check_contrast.py`（本ラウンドで ring 拡張）— **トークン値そのものの 3:1 判定**。#179 のような「デザイントークンの後退」を確実に、決定論的に検知できる唯一の層。
3. E2E 構造チェック（e2e_verify 提案）— リング自体の **消失**（`box-shadow: none` への regression）を検知。

**含意**: Lighthouse=100 を blocking にする決定（ユーザー確定事項）は覆さないが、**それだけでは #179 類を防げないので、争点C の是正（`--ring` トークン変更 + `/50` 除去）と check_contrast.py 拡張を Lighthouse 配線と** 同格の必須実装 **として扱うべき**。「Lighthouse が緑だから ring は健全」という誤った安心感を生まないよう、docs_trace には §7.3 追記（3.で後述）にこの三層の役割分担を 1 行残すことを提案する。

## 3. `--ring` = `--border` と同値問題 — **自己批判を認める（部分的譲歩）**

**計算結果**: ライトテーマは `--border: oklch(0.6 0 0)` と提案した `--ring: oklch(0.6 0 0)` は **sRGB で完全に同一値**（`(0.5021, 0.5021, 0.5021)`）。ダークテーマは `--border: oklch(0.55 0 0)` vs `--ring: oklch(0.556 0 0)`（変更なし）で自己コントラスト比 **1.025:1**（知覚的に区別不能なレベル）。

**認める点**: `button.tsx` の `variant=outline` に限り、resting border（`border-border`）と focus border（`focus-visible:border-ring`）の **色そのもの** は視覚的に区別できない。これは事実で、争点 C の「区別できると言うなら根拠を」に対して「1px 境界線の色だけを見れば区別できない」と認める。

**しかし全体としては区別できると主張する（部分譲歩に留める理由）**: フォーカス状態の一次的な視覚差分は境界線の色ではなく、**`focus-visible:ring-3` が追加する 3px の box-shadow の有無**（0px → 3px への幅の変化）である。これは色ではなく形状・面積の変化なので、①resting には box-shadow が無く focus には有る、という **バイナリな存在差** で常に区別可能（1px の境界線色が偶然一致しても、その外側に新たに 3px の面が出現する事実は変わらない）。したがって SC 1.4.1（色のみに頼らない）にも抵触しない。`variant=outline` 以外（`default`/`secondary`/`ghost`/`destructive`/`link`）は resting が `border-transparent` なので、境界線の色自体も透明→`--ring` へと明確に変化し、この問題は発生しない（`button.tsx:8` の base class 参照）。`input.tsx` は resting が `border-input`（ライト `oklch(0.922 0 0)`／ダーク `oklch(1 0 0 / 15%)`）で `--ring` と大きく異なるため無関係（問題なし）。

**代替案（採らない理由付きで提示）**: outline variant の境界線色も差を付けたいなら `--ring` に彩度を持たせる（例: `--color-accent` 系の色相を流用）案があるが、`--ring` は現状「フォーカス状態の中立的グレー」という設計意図で全コンポーネント共通のニュートラルパレットに属しており、彩度を持たせると「アクセントカラー＝フォーカス」という別の意味論が生まれ、影響範囲が「フォーカス表現」から「色の意味体系」に広がる（争点外の設計判断）。**採らない**: 本スプリントのスコープ外（YAGNI）とし、`outline` variant の境界線色一致は「許容する既知のトレードオフ」として PR に 1 行明記することを推奨する。

## 4. docs_trace とのすり合わせ — §7.1 は対象外リストに無かった

docs_trace の round1「結論」表（項目 1〜5）を確認したところ、**§7.1 の書き換えは挙げられていない**（挙げられているのは §7.3 新規追記＝リング 3:1・ライブリージョン入れ子禁止のみ）。これは私の round1 結論（「§7.1 は書き換えずに実装すべき」）と **矛盾しない**——docs_trace も暗黙に §7.1 を現状維持前提として扱っている。

ただし docs_trace の §7.3 追記案には無い、**§7.1 自体に足すべき 1 行** を提案する: 「本節の対象は `next/link` によるクライアント遷移（ページ送り・ソート・件数切替・一覧⇄詳細）であり、`search-form.tsx` のネイティブ GET フォーム送信（フルリロード）は対象外」。理由は round1 で示した事実（`layout.tsx` の `title` が全ルート静的固定・`suspenseKey` remount で `Pagination` が unmount される）に基づく適用範囲の明確化であり、新しい決定の追加ではなく **既存要件の射程を文書上でも明確にするだけ** なので、docs_trace の「決定の記録先を統一する」方針（項目4）とも整合する。docs_trace へ次ラウンドでこの 1 行を §7.1 に追記するよう申し送る。

### `e2e_verify` — 譲歩
<sub>2026-08-20T11:32:00+09:00</sub>

## e2e_verify Round 2 — concession（a11y_impl C-3 への追認）

a11y_impl の C-3（`suspenseKey` の remount で `Pagination` を含む `SearchBody` が unmount され、押したリンク自体が消えてフォーカスが `body` へ落ちる）は **手動チェックリスト送りにする必要はなく、E2E で判定可能**。round1 の私はフォーカス「可視性」の自動判定範囲しか論じなかったが、フォーカス「喪失」自体は別の、より単純な述語で捕まえられる。追認する。

**述語（`tabUntilFocused` の枠組みをそのまま流用）**:
```ts
await tabUntilFocused(page, page.getByRole('navigation', { name: '検索結果のページ' }).getByRole('link', { name: '次のページへ' }))
await page.keyboard.press('Enter')
await expect(page).toHaveURL(/[?&]page=2(&|$)/)
// 修復前（バグ）: unmount でフォーカスが body に落ちる → true になり fail
// 修復後: 結果見出し等、body 以外の何かにフォーカスが残る/移る → false
await expect.poll(() => page.evaluate(() => document.activeElement === document.body)).toBe(false)
```
この `!== body` という弱い assert だけなら、a11y_impl が C-3 で提案する具体的な着地点（見出しへの `tabIndex={-1}` + `focus()` か、次要素への自然な移動か）を **待たずに今のラウンドで書ける**。R2 の実装方針が固まったら `tabUntilFocused(page, 結果見出しロケータ)` に強化すればよい（弱い assert → 強い assert への 2 段階）。`e2e/sp-10.spec.ts` に組み込む。

対象は a11y_impl 指摘の「ページ送り/ソート/件数切替/一覧⇄詳細」のクライアント遷移全て。検索フォーム初回送信（ネイティブ GET リロード）は対象外でよい（a11y_impl の C-3 切り分けに同意）。

### `e2e_verify` — 反論
<sub>2026-08-20T11:32:00+09:00</sub>

## e2e_verify Round 2 — rebuttal

### 1. a11y_impl C-2（`LoadingIndicator` から role/aria-live を削除する案）は `e2e/sp-9-a11y.spec.ts` を壊す（unit test だけではない）

round1 で読んだ `e2e/sp-9-a11y.spec.ts` の内容から: 読み込み中を検証する 2 テスト（`'読み込み中の状態が role="status"...'` L58-66・`'読み込み中の状態にも axe の重大な違反がない'` L68-75）は共に `page.locator('main').getByRole('status')` で要素を取得している。ロード中の `main` 配下で `role="status"` を持つのは **現状 `LoadingIndicator` だけ**（外側の `<section id="search-status" aria-live="polite">` には `role` 属性が無い — `aria-live` は role を与えない）。a11y_impl 案どおり `LoadingIndicator` から role/aria-live を単純に削除すると、この 2 テストは `getByRole('status')` が 0 件になり **E2E が赤くなる**（`loading-indicator.test.tsx` という unit test の話に留まらない）。

**正しい是正案**: 外側の `<section>` に `role="status"` を明示追加する（`aria-live="polite"` はそのまま残す）:
```tsx
<section id="search-status" role="status" aria-live="polite" ...>
```
これは `LoadingIndicator` 自身の既存ドキュメントコメントにある「`role="status"`（暗黙で `polite`）に `aria-live="polite"` を明示併記する」という **同じパターンを 1 段上の要素に移すだけ**。`getByRole('status')` はロケータの解決先要素が変わるだけで、テキスト内容（読み込み中は `LoadingIndicator` のラベル、解決後は件数文言）は今までと同じものを返し続ける。**この形なら `e2e/sp-9-a11y.spec.ts` は無改修のまま緑を維持できる**。壊れるのは `loading-indicator.test.tsx`（コンポーネント単体を隔離して role/aria-live を assert している unit test）だけになる。

**intent-gate 権威順での結論**: `ui-ux-guidelines.md` §7.2（仕様）が要求しているのは「件数通知は `role="status"`（1 箇所のみ・入れ子禁止）」という **画面レベルの契約** であり、「`LoadingIndicator` というコンポーネント自身が role を持つこと」までは要求していない。`loading-indicator.test.tsx` の現行アサーションは後者（コンポーネント単体の実装詳細）を固定しているに過ぎず、これは 仕様 ではなく 現行コード 相当。§0/§3 item0 の 4 分岐でいう「最も単純な合理的解釈」は「role を section 側へ移し、仕様の要求（入れ子禁止・唯一の role=status）を満たす形へ両方を揃える」であり、a11y_impl の C-2 提案（削除するだけ）を **`role="status"` を section へ足す形に修正した上で採用すべき**。`loading-indicator.test.tsx` の書き換えは正当（仕様に矛盾するテストを守るための黙った実装改変ではなく、逆＝古い実装詳細を固定したテストを仕様に合わせて直す）。ただし `testing-strategy.md` §5 の順序（`test:` → `feat:`）を守り、コミットで「#180 是正に伴う仕様変更」と明記すること（L-113 のサイレント書き換え禁止と矛盾しない）。

### 2. gate_infra の時間見積り依頼 — 質問の前提を訂正した上で見積もる

**訂正**: 「Lighthouse 3 画面 35.5 秒」（gate_infra 実測）と「`a11y.spec.ts` 36.5 秒」（私の実測）は **同じタイムアウト予算を取り合わない別ステップ**。gate_infra の R1 提案は Lighthouse を `run_checks.sh` の **専用ステップ**（新設 `RUN_CHECKS_LIGHTHOUSE_TIMEOUT`、既定 180 秒案）として叩く設計で、`RUN_CHECKS_E2E_TIMEOUT`（Playwright の `npm run test:e2e` 一括実行）とは別枠。したがって両者を単純合算して 1 つのタイムアウトと比較するのは誤り。「E2E 総時間」は Playwright ステップ（`e2e/*.spec.ts` 全ファイルが単一 `webServer` を共有する 1 プロセス実行）だけで見積もるべき質問だと解釈して答える。

**見積り（外挿・未実測・要検証と明記）**: 実測できているのは `a11y.spec.ts`（2 テスト・real 36.5s、コールドビルド 1 回分を含む）だけ。`playwright.config.ts` は `workers: 1` かつ `webServer` を全 spec ファイルで共有するため、ビルド/起動コスト（概算 8〜10 秒: gate_infra 実測 `next build` 5.3 秒 + `next start` の ready 検出 + Chromium 起動）は **1 回だけ** 発生し、残りは各テストの実行時間の積み上げ。
- `a11y.spec.ts`（axe 2 回）: 実測 36.5s（ビルド込み）
- `sp-9-a11y.spec.ts`（axe 4 回 + DOM 検証 1 回・5 テスト）: axe 1 回あたりのコストを `a11y.spec.ts` から逆算（(36.5 − 9)/2 ≒ 13.75s/回）すると概算 4×13.75 + 3 ≒ 58s
- `sp-7.spec.ts`（1 テスト・5 ステップ・末尾で axe 1 回）: 概算 20〜25s
- `sp-5.spec.ts`（axe なし・複数 goto/fetch）: 概算 10〜15s
- `sp-2.spec.ts`（axe を `color-contrast` 1 ルールのみに絞り込み・軽量）: 概算 5〜8s
- 新設 `e2e/sp-10.spec.ts`（axe なし。キーボード完走 1 テスト + レスポンシブ/ズーム 1 テスト。`tabUntilFocused` はミリ秒オーダーのポーリングで軽い）: 概算 15〜20s

**合計目安: 約 145〜175 秒**（ビルド込み・全 6 ファイル）。既存の `RUN_CHECKS_TIMEOUT` 既定 300 秒には収まる可能性が高いが、**この数字は round1 の 1 サンプルからの外挿であり実測ではない**。私はこのラウンドで新規ベンチマークを走らせない縛りのため、正式な数字は R1 担当（gate_infra）または実装後のセッションが `npx playwright test --reporter=line`（全 spec）を 1 回実測して確定すべき。もし 300 秒に近い/超えるなら、対処案は E2E と同型の専用 env（`E2E_TIMEOUT_SEC`。値は未確認・要確認）を伸ばすか、`sp-9-a11y.spec.ts` の axe 呼び出し回数を絞る（4 状態全部で axe を回す必要が本当にあるか＝争点 B の判断）のが素直で、Lighthouse 側の予算とは無関係に調整できる。

### 3. `tabUntilFocused` の自己批判 — hang しないが「不透明に遅い失敗」になるリスクがあった

**構造上「無限ループ」にはならない**（`for (let i = 0; i < maxPresses; i++)` は必ず終わる有界ループ）。ただし round1 版には見落としがあった: `target.evaluate(...)` は Playwright の actionability 待機（要素が DOM にアタッチされるまで待つ）を内包するため、`target` のロケータが一度も要素にマッチしない（誤ったロール名等）場合、**1 回の `evaluate` 呼び出し自体がテスト全体のタイムアウト（`playwright.config.ts` の `timeout: 60_000`）近くまでブロックしうる**。`.catch()` で握りつぶしても、ループが 30 回転する前に外側の 60 秒テストタイムアウトへ先に到達し、私の診断メッセージ（`Tab を N 回押しても...`）が一度も出ないまま Playwright の汎用タイムアウトエラーで落ちる — hang はしないが「原因が分かりにくい失敗」になる。

**修正版**（ノンブロッキングな `.count()` へ置き換え）:
```ts
export async function tabUntilFocused(page: Page, target: Locator, maxPresses = 40): Promise<void> {
  for (let i = 0; i < maxPresses; i++) {
    const focusedCount = await page.locator(':focus').and(target).count()
    if (focusedCount === 1) return
    await page.keyboard.press('Tab')
  }
  throw new Error(
    `Tab を ${maxPresses} 回押しても対象へフォーカスが到達しなかった（フォーカストラップまたはロケータの誤りの可能性）`,
  )
}
```
`Locator.count()` は actionability 待機を伴わない即時 DOM スナップショット照会（存在しなければ 0 を返すだけ）なので、1 回転のコストは Tab キー送出のレイテンシ（数十 ms オーダー）に閉じる。`maxPresses=40` でも合計は数秒程度に収まり、60 秒の外側タイムアウトに対して十分な安全マージンを持ちつつ、**本当に到達不能なときは自分のエラーメッセージで速く失敗する**（診断可能性が上がる）。`maxPresses` は「その画面で到達可能なインタラクティブ要素の実測上限＋余裕」を呼び出し側コメントに明記する運用にする（決め打ちの正当化根拠を毎回書かせることで、値そのものへの依存を弱める）。

## ラウンド 3

### `lead` — 合意
<sub>2026-08-20T11:34:00+09:00</sub>

# 合意（lead 統合・SP-10 実装方針の確定）

## 合意した点（4 名一致・または反論を経て収束）

1. **Lighthouse はこのコンテナで実行できる**（gate_infra が実測: `CHROME_PATH=/opt/pw-browsers/chromium` 必須・未設定だと `ChromePathNotSetError` で即死。3 画面 35.5 秒・`next build` 5.3 秒）。ユーザー確定事項（案 (a)）は実装可能。
2. **Lighthouse Accessibility = 100 は「a11y が担保された」ことを意味しない**。現状の未達リング（1.545:1）でも 3 画面すべて `accessibility: 1` が出ている（gate_infra 実測）。axe-core は `:focus-visible` を発火させないため、**#179 クラスの欠陥は Lighthouse でも axe でも検出できない**（a11y_impl・gate_infra が独立に到達し e2e_verify が追認）。→ **三層防御** で切り分ける:
   - Lighthouse / axe（DOM 静的解析）: alt 欠落・ラベル欠落・ARIA 誤用など広範な一般違反
   - `check_contrast.py`（静的トークン検査）: **トークン値の 3:1 判定**。#179 クラスを決定論的に捕まえる唯一の層
   - E2E（構造・到達）: リングの **消失** とフォーカスの **喪失・到達不能**
3. **`--ring` はライトのみ値を下げる必要がある**。α=1.0 にしてもライトの `oklch(0.708 0 0)` は上限 2.593:1 で 3:1 に届かない（a11y_impl が `check_contrast.py` の関数を import して計算）。ダークは `/50` を外すだけで通過（4.183:1 / 3.194:1）。
4. **`/50` は 3 箇所すべてから外す**。`button.tsx` / `input.tsx` だけ直しても `globals.css:149` の `outline-ring/50` が効くネイティブ `<a>`（詳細リンク・戻るリンク・再試行リンク）が未達のまま残る（a11y_impl の発見）。加えて **Tailwind ユーティリティ側の `/NN` を使っている限り `check_contrast.py` は値を検査できない**（globals.css しか読まないため）。→ 「透明度は CSS 変数側に埋め込む・`ring`/`outline` にユーティリティ側 opacity を使わない」を実装ルールにすることで、初めて機械検査が成立する。
5. **#180 の是正は「削除するだけ」では不足**。`LoadingIndicator` から `role="status"` を単純削除すると `e2e/sp-9-a11y.spec.ts` L58-75（`page.locator('main').getByRole('status')`）が 0 件マッチで **赤くなる**（e2e_verify が指摘）。→ **外側 `<section id="search-status">` に `role="status"` を足したうえで `LoadingIndicator` 側から `role`/`aria-live` を外す**。これで入れ子が解消し E2E は無改修で緑を維持、壊れるのは実装詳細を固定していた `loading-indicator.test.tsx` だけになる。権威順（仕様 > テスト > 現行コード）で正当（§7.2 が要求するのは「画面に唯一の `role="status"`」であってコンポーネントが role を持つことではない）。
6. **§7.1 のフォーカス移動は「GET フォームだから不要」ではない**（a11y_impl が実地で反証）。`pagination` / `sort-picker` / `per-page-picker` / 詳細リンク / `back-link` は **すべて `next/link`** でクライアント遷移し、`layout.tsx` の `title` は全ルート静的固定・`generateMetadata` 0 件のため route announcer は発火しない。さらに `page.tsx:236` の `suspenseKey` remount で `Pagination` 自体が unmount され、**押したリンクが消えてフォーカスが `body` に落ちる**。→ §7.1 は書き換えず **実装する**。適用範囲（GET フォーム送信は対象外）を §7.1 に 1 行追記する。
7. **200% 拡大は `page.setViewportSize({ width: 640 })`**（1280 の半分）で代理する。`deviceScaleFactor` / `--force-device-scale-factor` は CSS px のレイアウト幅を変えず reflow を検証できないため不採用、CSS `zoom` は「ブラウザズームへの対応」ではなく「zoom プロパティへの対応」を測ってしまうため不採用（e2e_verify・却下理由付き）。スマホ幅 375px は **別 viewport** として区別する（操作レビュー (2) と (3) は別 SC）。
8. **時間予算は成立する**。Lighthouse は E2E とは **別ステップ・別タイムアウト**（新設 `RUN_CHECKS_LIGHTHOUSE_TIMEOUT` 既定 180 秒）なので加算されない。ポートは E2E（3100）と分けて 3101 を使う（gate_infra が自分の round1 案を自己修正）。
9. **`NFR-27` の矛盾はドキュメント側だけで生じる**。配線案の実装には「Performance 90 以上」という閾値が最初から存在しない。ユーザー明示 > 仕様の権威順により `prd.md` を書き換えるのが正しい（docs_trace 判定）。数値は削除せず「目安値として計測・記録する（未達でもゲートしない）」の形にして差分を最小化する。

## 収束した対立点

| 対立 | 決着 |
|---|---|
| ring 色の後退を E2E で検知できるか | **できない**（e2e_verify が自己批判 → a11y_impl・gate_infra が同意）。`check_contrast.py` 拡張が担当層。実装は **R1**（判定基盤の所有者）が行い、値の確定を待たずにペアを足せる |
| `--ring` = `--border` 同値でフォーカスが区別できないのでは | **`variant=outline` の 1px 境界線色だけは区別できない** と a11y_impl が譲歩。ただし `ring-3` の 3px box-shadow の **有無** というバイナリな形状差で区別可能（SC 1.4.1 にも抵触しない）。彩度を持たせる代替案は「色の意味体系」への影響が争点外のため不採用。**既知のトレードオフとして PR に 1 行明記する** |
| `LoadingIndicator` から role を削除してよいか | **削除するだけは不可**（E2E を壊す）。**section 側に `role="status"` を足す** 形へ修正して採用 |
| ring 変更後も Lighthouse=100 か | **断定しない**。gate_infra が「変わらない可能性が高い」としつつ **実装後の再計測を必須** と明言。ゲートの本来の役目なので追加作業ではない |
| E2E 総時間 | **約 145〜175 秒の外挿（実測ではない）**。R1 または実装後のセッションが全 spec を 1 回実測して確定する |

## 不採用（明言）

- Lighthouse CI（lhci）サーバーを立てる — 必要なのは「1 回叩いて score を見る」だけで過剰（YAGNI）
- GitHub Actions 復旧を待つ — #77 は `status:blocked` で見通しが立たず、ユーザー確定事項が (a) を選んでいる
- Playwright の `webServer` に相乗りする — build 実測 5.3 秒に対し常駐化の複雑さが見合わない（将来 30 秒超になったら再検討）
- ring の alpha だけ上げる / `ring-offset` を足す — ライトは数学的に 3:1 に届かない・色自体のコントラストは変わらない
- §7.1 を「GET フォームだから不要」と緩める — 実地調査（`generateMetadata` 0 件・`suspenseKey` remount）で反証済み
- `--ring` に彩度を持たせる — 影響範囲が「色の意味体系」に広がり争点外（YAGNI）

### `lead` — 判定
<sub>2026-08-20T11:35:30+09:00</sub>

{
  "decisions": [
    {
      "issue": "A) Lighthouse の run_checks.sh 配線",
      "design": "lighthouse を devDependencies に固定バージョンで追加し、新設 tools/run_lighthouse.mjs が (1) e2e/stub/server.mjs を起動 (2) next build && next start --port 3101（E2E の 3100 と分離） (3) CHROME_PATH=/opt/pw-browsers/chromium を明示して Lighthouse を 2 画面（/ja?q=react・/ja/repos/octostub/octo-widgets）に実行 (4) categories.accessibility.score < 1.0 なら GATE_FAIL メッセージ付きで非ゼロ exit、performance.score は判定に使わず記録出力のみ (5) JSON が生成されなかった場合は INFRA_FAIL メッセージで区別、を行う。run_checks.sh からは run_check_timeout で 1 ステップとして呼び、専用タイムアウト RUN_CHECKS_LIGHTHOUSE_TIMEOUT（既定 180 秒）を新設する。",
      "artifacts": ["tools/run_lighthouse.mjs（新規）", "tools/run_checks.sh（改修）", "package.json（改修・devDependencies + scripts）"],
      "rejected": "lhci サーバーを立てる案（1 回叩いて score を見るだけなので過剰・YAGNI）／GitHub Actions 復旧を待つ案（#77 は status:blocked・ユーザー確定事項が (a)）／Playwright の webServer に相乗りする案（build 実測 5.3 秒に対し常駐化の複雑さが見合わない）"
    },
    {
      "issue": "B) axe カバレッジと WCAG 2.2 AA 宣言",
      "design": "e2e/axe.ts の createAxeBuilder に withTags(['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa']) を追加する（1 箇所の変更・実行時間への影響は誤差）。ただし axe-core は :focus-visible を発火させないため #179 クラスは検出できないことを前提に、三層防御（Lighthouse/axe = DOM 静的解析の一般違反 / check_contrast.py = トークン値の 3:1 判定 / E2E = 消失と到達不能）の役割分担を ui-ux-guidelines.md §7 に 1 箇所だけ記述する（新 SSOT を作らない）。",
      "artifacts": ["e2e/axe.ts（改修）", "docs/03_design/ui-ux/ui-ux-guidelines.md §7（改修・三層の役割分担を追記）"],
      "rejected": "axe の withTags 拡張だけで #179 クラスを防げるとする案（同じエンジンなので検出できない）／serious/critical 以外まで一律 blocking にする案（本ラウンドで必要性が示されなかった）"
    },
    {
      "issue": "C-1) フォーカスリングのコントラスト（#179）",
      "design": "app/globals.css の :root { --ring } を oklch(0.708 0 0) → oklch(0.6 0 0) に変更する（--border ライトと同値・新規 raw 値を増やさない。vs bg 3.947:1 / vs bg-subtle 3.619:1）。.dark { --ring } は変更しない（4.183:1 / 3.194:1 で通過済み）。/50 は button.tsx・input.tsx・globals.css:149 の outline-ring/50 の 3 箇所すべてから外す。透明度が要る場合は CSS 変数側に oklch(L C H / A%) で埋め込み、Tailwind ユーティリティ側の /NN サフィックスを ring/outline に使わないことを実装ルールとする（これがないと check_contrast.py が値を検査できない）。button variant=outline の resting border と focus border が同色になる点は、ring-3 の 3px box-shadow の有無で区別可能なため許容し、既知のトレードオフとして PR に 1 行明記する。",
      "artifacts": ["app/globals.css（改修）", "src/ui/components/button.tsx（改修）", "src/ui/components/input.tsx（改修）", "docs/03_design/ui-ux/ui-ux-guidelines.md §7.3（改修・リング 3:1 と opacity 実装ルールを明記）"],
      "rejected": "alpha だけ上げる案（ライトは α=1.0 でも上限 2.593:1 で数学的に届かない）／ring-offset を足す案（色自体のコントラストが変わらない）／--ring に彩度を持たせる案（色の意味体系への影響が争点外・YAGNI）"
    },
    {
      "issue": "C-2) ライブリージョンの入れ子（#180）",
      "design": "app/[locale]/page.tsx:300 の <section id=\"search-status\" aria-live=\"polite\"> に role=\"status\" を追加し、src/ui/loading-indicator.tsx から role=\"status\" / aria-live=\"polite\" を外して表示専用にする。これで入れ子が解消し、e2e/sp-9-a11y.spec.ts L58-75 の page.locator('main').getByRole('status') は解決先要素が変わるだけで無改修のまま緑を維持する。壊れるのは実装詳細を固定していた src/ui/loading-indicator.test.tsx のみで、これは仕様（§7.2 = 画面に唯一の role=\"status\"・入れ子禁止）に合わせた正当な書き換え。testing-strategy.md §5 の順序（test: → feat:）を守り、コミットメッセージに「#180 是正に伴う仕様変更」と明記する。",
      "artifacts": ["app/[locale]/page.tsx（改修）", "src/ui/loading-indicator.tsx（改修）", "src/ui/loading-indicator.test.tsx（改修）"],
      "rejected": "LoadingIndicator から role/aria-live を削除するだけの案（e2e/sp-9-a11y.spec.ts が 0 件マッチで赤くなる）／汎用性を優先して role を残す案（唯一の使用箇所であり入れ子の実害が上回る）"
    },
    {
      "issue": "C-3) ルート変更時のフォーカス移動（E-15 / §7.1）",
      "design": "§7.1 は書き換えず実装する。(a) 詳細ページ（app/[locale]/repos/[owner]/[repo]/page.tsx）に既存 src/ui/set-document-title.tsx のパターンを成功パスへ拡張し、fullName を document.title に反映する（現状は全ルート 'gem-hunter' 固定・generateMetadata 0 件）。(b) 一覧の結果見出しに tabIndex={-1} を付け、searchParams の変化を検知して .focus() する薄いクライアントコンポーネント src/ui/focus-on-navigate.tsx を新設する（ページ送り・ソート・件数切替で suspenseKey remount によりフォーカスが body へ落ちる実害の是正）。§7.1 に「本節の対象は next/link によるクライアント遷移であり、search-form.tsx のネイティブ GET フォーム送信は対象外」の 1 行を追記する。",
      "artifacts": ["src/ui/focus-on-navigate.tsx（新規）", "src/ui/focus-on-navigate.test.tsx（新規）", "app/[locale]/page.tsx（改修）", "app/[locale]/repos/[owner]/[repo]/page.tsx（改修）", "docs/03_design/ui-ux/ui-ux-guidelines.md §7.1（改修・適用範囲 1 行）"],
      "rejected": "§7.1 を「GET フォームだから不要」と緩める案（generateMetadata 0 件・suspenseKey remount の実地調査で反証済み）"
    },
    {
      "issue": "D) レスポンシブ・200% 拡大の機械判定（E-16）",
      "design": "200% 拡大は page.setViewportSize({ width: 640, height: 360 })（既定 1280 の半分）で代理し、スマートフォン幅 375px は別 viewport として区別する。破綻の述語は document.scrollingElement の scrollWidth <= clientWidth + 1（clientWidth は縦スクロールバー分を除いた値なのでスクロールバー由来の偽陽性は原理的に起きない。+1px は sub-pixel 丸め対策で実装後に実測して確定）。対象は /ja（検索前）・/ja 検索後・詳細の 3 画面 × 2 viewport = 6 assert。主要要素の描画完了を locator 待機で確認してから評価する。",
      "artifacts": ["e2e/sp-10.spec.ts（新規）"],
      "rejected": "deviceScaleFactor / --force-device-scale-factor（CSS px のレイアウト幅を変えず reflow を検証できない）／CSS zoom の注入（測っているのが「ブラウザズームへの対応」ではなく「zoom プロパティへの対応」になり fixed 要素等で偽陽性・偽陰性を生む）／Emulation.setPageScaleFactor（Playwright に公開 API が無く desktop Chromium で機能しない）"
    },
    {
      "issue": "D-2) キーボード完走とフォーカス喪失の判定",
      "design": "e2e/helpers.ts に tabUntilFocused(page, target, maxPresses = 40) を追加する。判定は page.locator(':focus').and(target).count() === 1（Locator.count() は actionability 待機を伴わない即時照会なので、ロケータ誤りでも外側 60 秒タイムアウトに飲まれず自前の診断メッセージで速く失敗する）。固定 Tab 回数に依存せず DOM 変更に強い。フォーカス喪失は expect.poll(() => page.evaluate(() => document.activeElement === document.body)).toBe(false) で判定する（弱い assert）。C-3 の実装が固まったら tabUntilFocused(page, 結果見出し) の強い assert へ格上げする 2 段階運用。",
      "artifacts": ["e2e/helpers.ts（改修）", "e2e/sp-10.spec.ts（新規）"],
      "rejected": "page.keyboard.press('Tab') を N 回決め打ちする案（要素が 1 つ増減しただけで全テストが壊れる）／round1 版の target.evaluate ベース実装（actionability 待機を内包し、原因の分かりにくい失敗になる）"
    },
    {
      "issue": "E) 画像の代替テキストと最適化配信（US-15 / E-17）",
      "design": "src/ui/repository-list.tsx:58 の alt={item.owner.login} を alt=\"\" に変更する（カード内に owner/repo 形式のリポジトリ名が隣接表示されるため §7.4 の装飾扱いに該当。詳細ページは既に alt=\"\" で正しい）。width/height 属性は既に指定済みで CLS は発生しない想定だが、E2E のレスポンシブ検証と合わせて実測で確認する。next/image は INF-11 により引き続き使わない。",
      "artifacts": ["src/ui/repository-list.tsx（改修）", "src/ui/repository-list.test.tsx（改修）"],
      "rejected": "next/image を導入して最適化配信する案（INF-11 で不採用が確定済み）"
    },
    {
      "issue": "F) ドキュメント同期",
      "design": "prd.md §5.6 NFR-27 の Performance を「90 以上を目安値として計測・記録する（未達でもゲートしない）」に書き換える（ユーザー明示 > 仕様の権威順に従う。数値を残して差分を最小化）。user-story-map.md §5.3 SP-10 手順 4 を「tools/run_checks.sh で axe（serious/critical 違反 0）と Lighthouse（Accessibility = 100）が通る」に具体化する。ui-ux-guidelines.md §9 の「Lighthouse CI の CLS 実測値」を「tools/run_checks.sh で実行される Lighthouse の CLS 実測値」に具体化する。決定の経緯は open-questions.md に 1 行追記する。",
      "artifacts": ["docs/02_requirements/prd.md（改修）", "docs/02_requirements/user-story-map.md（改修）", "docs/03_design/ui-ux/ui-ux-guidelines.md §9（改修）", "docs/02_requirements/open-questions.md（改修）"],
      "rejected": "prd.md から Performance 要件を単純削除する案（数値を残して非 blocking を明示する方が差分が小さく将来の再ゲート化にも耐える）"
    },
    {
      "issue": "G) check_contrast.py の ring 拡張",
      "design": "SEMANTIC_VARS に \"ring\" を追加し、CHECK_PAIRS に (\"ring\", \"background\", 3.0, ...) と (\"ring\", \"muted\", 3.0, ...) の 2 行を追加する。既存の resolve_srgb / evaluate_theme が CSS からトークン値を動的に読むため、R2 が --ring の最終値を何に決めても R1 側はペアを足すだけで完結し、値の確定を待つ必要はない（Tailwind ユーティリティ側の opacity が除去されていることが前提条件）。",
      "artifacts": ["tools/check_contrast.py（改修）"],
      "rejected": "E2E でリング色の後退を検知する案（box-shadow の存在チェックは値の後退を捕まえられない・e2e_verify の自己批判）"
    }
  ],
  "fanout": [
    {
      "role": "R1（判定基盤）",
      "scope": "Lighthouse の run_checks.sh 配線・check_contrast.py の ring 拡張・依存追加",
      "files": ["tools/run_lighthouse.mjs", "tools/run_checks.sh", "tools/check_contrast.py", "package.json", "package-lock.json"],
      "depends_on": []
    },
    {
      "role": "R2（フォーカスとライブリージョン）",
      "scope": "ring トークン是正・/50 除去・ライブリージョン一本化・ルート変更時のフォーカス移動",
      "files": ["app/globals.css", "src/ui/components/button.tsx", "src/ui/components/input.tsx", "src/ui/loading-indicator.tsx", "src/ui/loading-indicator.test.tsx", "src/ui/focus-on-navigate.tsx", "src/ui/focus-on-navigate.test.tsx", "app/[locale]/page.tsx"],
      "depends_on": []
    },
    {
      "role": "R3（レスポンシブと画像）",
      "scope": "alt 方針の適用・詳細ページの document.title 反映・レスポンシブ崩れの是正",
      "files": ["src/ui/repository-list.tsx", "src/ui/repository-list.test.tsx", "src/ui/repository-detail.tsx", "src/ui/repository-detail.test.tsx", "app/[locale]/layout.tsx", "app/[locale]/repos/[owner]/[repo]/page.tsx"],
      "depends_on": []
    },
    {
      "role": "R4（E2E とドキュメント）",
      "scope": "sp-10 の E2E 新設・axe の withTags 拡張・ヘルパー追加・ドキュメント同期",
      "files": ["e2e/sp-10.spec.ts", "e2e/helpers.ts", "e2e/axe.ts", "e2e/a11y.spec.ts", "docs/02_requirements/prd.md", "docs/02_requirements/user-story-map.md", "docs/02_requirements/open-questions.md", "docs/03_design/ui-ux/ui-ux-guidelines.md"],
      "depends_on": ["R2（結果見出しのロケータ契約）", "R3（alt の期待値）"]
    }
  ],
  "critical": [
    "Lighthouse Accessibility = 100 は #179 クラス（フォーカスリングの非テキストコントラスト）を検出しない。現状の未達状態でも 3 画面すべて 100 が出ている（実測）。ゲートを配線しただけで a11y が担保されたと解釈してはならず、check_contrast.py の ring 拡張が同格の必須実装である。",
    "R2 の aria 属性変更（role=\"status\" の移設）は axe-core の標準ルールに触れうるため、実装後に Lighthouse を必ず再計測する。ring 値の変更がスコアに影響しないことも実測で確認するまで断定しない。",
    "E2E 総時間の約 145〜175 秒は 1 サンプルからの外挿であって実測ではない。実装後に npx playwright test --reporter=line を 1 回通しで実測し、RUN_CHECKS_TIMEOUT（既定 300 秒）に収まることを確認する。超える場合は専用タイムアウトを伸ばすか sp-9-a11y.spec.ts の axe 呼び出し回数を絞る。",
    "R4 は R2 の結果見出しロケータと R3 の alt 期待値に依存する。契約（ロケータのロール名と alt の値）を R2/R3 が先に 1 行で共有してから R4 が Red の spec を書く（契約先行）。"
  ],
  "open_questions": []
}
