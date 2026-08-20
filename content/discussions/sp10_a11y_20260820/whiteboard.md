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
- 投稿数: 4
- 更新: 2026-08-20T11:26:19+09:00

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
- **複数回実行の中央値**は CLS・Accessibility には不適用（決定論的なため）。Performance の揺らぎ対策のみ（既に注記に記載）

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
- `document.scrollingElement`（Next.js は標準モードのため `documentElement` と同一）の `clientWidth` は **縦スクロールバー分を既に除いた値**なので、スクロールバー由来の偽陽性は原理的に発生しない（`clientWidth` と `scrollWidth` を同じ要素の同じ座標系で比較しているため）。`+1px` の許容は必要（実測せず一般論として明記・要検証: 本実装後に実測して閾値を確定する）。
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
- **R4 は R2/R3 に依存する**（brief 指摘のとおり）が、TDD の外側ループ（`testing-strategy.md` §5）に従うなら **R4 が先に Red の spec を書く**のが筋。ただし本ラウンドでは編集禁止のため、次ラウンドで R4 担当が selectors/roles だけ R2/R3 と事前合意してから contract-first で着手することを推奨（例: 結果一覧見出しを追加するなら `getByRole('heading', { name: ... , level: 2 })` を Tab 到達先にする、追加しないなら「一覧のリンクへ直接到達」を到達先にする — どちらでも `tabUntilFocused` は動くため、E2E 側はこの設計判断（§7.1 の tabIndex 実装要否）を待たずに書き始められる）。
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
4. `npm run build` は **5.3 秒**で完走（`.next` は `.gitignore:49` で無視済み・リポジトリを汚さない）。`npm start -- --port 3100` の起動は `Ready in 137ms`。playwright.config.ts のコメントにある「180 秒の起動上限」は最悪系（コールドキャッシュの共有ランナー）を見込んだ値で、このコンテナの実測とは大きく乖離している。
5. stub（`e2e/stub/server.mjs`）+ `next build && next start` を実際に起動し、`/ja`・`/ja?q=react`（一覧・検索実行後）・`/ja/repos/octostub/octo-widgets`（詳細）の 3 URL に Lighthouse を実行。**各回 11.7〜12.1 秒、3 回合計 35.5 秒**。現状のコードでは 3 画面とも `accessibility: 1`（100 点）、`performance: 0.99〜1`。
6. `check_contrast.py` は `SEMANTIC_VARS`（background/muted/foreground/muted-foreground/border/accent/accent-foreground/destructive/destructive-foreground）のみを検査しており、`--ring` は対象外（`tools/check_contrast.py:178-188` に grep 一致なし）。brief の記述どおり「ring の 3:1 判定は見ていない」ことを確認した。

### 争点A: run_checks.sh への配線案

**採る案**: 専用ラッパースクリプト（例 `tools/run_lighthouse.mjs`）を新設し、run_checks.sh から `run_check_timeout` で 1 ステップとして呼ぶ。中身は E2E ステップと同型の自前 build+start（stub + `next build && next start`）を **もう一度** 行う。

- **理由**: 実測 5 秒のビルドを 1 回増やすコストは無視できる。Playwright の `webServer` は `npx playwright test` プロセスの生存期間しか維持されないため、E2E ステップの後から「そのサーバーに相乗り」するには webServer を常駐化する設計変更（`reuseExistingServer` を恒久 true にして別プロセスで先に起動しておく等）が要る。**その複雑化に見合うほど build コストは高くない**（実測 5 秒 vs 600 秒の E2E タイムアウト予算）。まず素朴な「もう一度 build+start」で配線し、将来ビルドが重くなったら相乗り化を検討すればよい（YAGNI）。
- **依存の入れ方**: `npx lighthouse@<pin>` の都度ネットワーク取得ではなく、**`lighthouse` を devDependencies に固定バージョンで追加**（既存の `@playwright/test": "1.56.1"` と同じ流儀）。理由: ① `npx eslint` / `npx tsc` は既にローカル devDependency 前提（bare npx 自動取得ではない）で、Lighthouse だけ都度ネットワーク依存にすると挙動が非対称になる ② レジストリ到達不能な瞬間があった場合に「依存未インストール」と同じ FAIL 扱いにできる（run_checks.sh の `DEPS_MISSING` パターンを踏襲できる）。
- **CHROME_PATH**: `/opt/pw-browsers/chromium`（playwright と同一シンボリックリンク）をラッパー内でハードコード、または `PLAYWRIGHT_BROWSERS_PATH` から解決。E2E と実行系を分ける必要はない。
- **対象 URL**: 一覧（`/ja?q=react` 相当・検索実行後の状態。何もしない `/ja` は空状態で情報量が少なく axe/Lighthouse の実質的なカバレッジが薄い）と詳細（`/ja/repos/octostub/octo-widgets`）の **2 画面** で十分（brief 確認事実と一致、実測 3 画面目の `/ja` 単体は付加価値が低いので削ってよい）。
- **blocking / 記録のみの分離**: ラッパーは JSON をパースして (a) accessibility score < 1.0 → 非ゼロ exit（blocking）、(b) performance score はそのまま stdout に出力するだけで判定に使わない。run_checks.sh 側は 1 行のチェックとして追加（例 `run_check_timeout "Lighthouse a11y (一覧)" 120 node tools/run_lighthouse.mjs --url=... --page=list` を画面数ぶん）。Markdown サマリー表の PASS/FAIL 列にそのまま乗る（brief の「サマリー表への載せ方」は既存 `run_check_timeout` の枠組みをそのまま再利用すれば追加実装ゼロ）。Performance の記録は同じ行の中に `(perf=0.99)` のようにチェック名へ埋め込むか、別行 `INFO` ステータスを 1 つ新設するかは a11y_impl/e2e_verify の実装コストとの兼ね合いで決めてよいが、**新設するなら「INFO はサマリーに出るが OVERALL_EXIT に影響しない」ことをコメントで明記**すること（既存の PASS/FAIL/SKIP と混同されない設計にする）。
- **チェッカー自体の落ちた/本当に落ちた の区別**: exit code だけでは run_checks.sh 側は区別できない（既存の仕組みが FAIL 一括り）が、**メッセージ文字列で区別可能**にできる。実測した `ChromePathNotSetError` のように、Chrome 起動失敗・JSON 未生成のケースは stderr にスタックトレースが残るので、ラッパー内で「JSON ファイルが生成されなかった」ことを検出したら `[run_lighthouse] INFRA_FAIL: Chrome 起動に失敗しました（詳細は上記ログ）` のような明示メッセージを先頭に出し、JSON が生成されて score だけ足りない場合は `[run_lighthouse] GATE_FAIL: Accessibility {n}/100（しきい値 100）` を出す。これは check_contrast.py 等の既存スクリプトが「未宣言変数」と「しきい値未達」を別メッセージで出している流儀と同じで、追加のハーネス変更は不要。
- **タイムアウト**: 実測 build 5 秒 + start 3 秒 + Lighthouse 2 画面 ×12 秒 ≒ 34 秒。専用タイムアウト env（例 `RUN_CHECKS_LIGHTHOUSE_TIMEOUT`、既定 180 秒）を E2E と同じパターンで新設すれば十分な余裕がある。既定の 300 秒（`RUN_CHECKS_TIMEOUT`）を流用すると Lint/型/vitest と取り合いになる問題は E2E と同じなので、E2E の前例（`RUN_CHECKS_E2E_TIMEOUT`）に倣うのが一貫性がある。
- **採らない案**: ① **Lighthouse CI（lhci）サーバーを立てる案** — サーバー常駐・DB・設定ファイルが増える割に、ここで必要なのは「1 回叩いて score を見る」だけなので過剰実装（YAGNI）。CI という機構自体が無い前提（このセッションが直接叩く）とも整合しない。② **Actions 復旧を待つ案** — #77 は `status:blocked` で見通しが立たない。ユーザー確定事項として (a) 案を採ると決まっている以上、待ちは選択肢にならない。③ **E2E の webServer に相乗りする案（今回は採らない）** — build コストが低いことが実測でわかった以上、複雑化に見合わない。ビルド時間が将来 30 秒を超えるレベルまで悪化したら再検討でよい。

### 争点B: axe カバレッジ（infra 観点のみ）

`e2e/axe.ts` の `createAxeBuilder` は `AxeBuilder` のオプション未指定 = 既定ルールセット（WCAG 2.0/2.1 A/AA 相当が中心）で動いている。`withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])` を足すのは **`e2e/axe.ts` 1 箇所の変更で済む低コストな改善**（infra 変更は不要）。実行時間への影響も誤差レベル（axe はブラウザ内 JS 実行で、ルール数が増えても走査自体はミリ秒〜数百ミリ秒オーダー）。ただし「WCAG 2.2 AA を目標として宣言できるか」という判定基準そのもの（どのタグを足すべきか・どの画面/状態を対象にするか）は a11y_impl/docs_trace の領分と考える。Lighthouse の accessibility 監査自体も axe-core をエンジンとして使っているため、**Lighthouse の accessibility=100 と Playwright の axe 直接実行は同じエンジンの重複実行**になる点は認識しておくべき（無駄ではない。Lighthouse は「素の DOM ロード直後」を、axe.spec.ts は「検索実行後の状態」を見ており対象タイミングが違う）。

### 実行時間・フレークのコスト評価（結論）

- 3 画面 Lighthouse 実測 35.5 秒、2 画面に絞れば約 24 秒。build+start を足しても 40 秒台。**「割に合わない」水準ではない**。
- Lighthouse の accessibility カテゴリはネットワーク/CPU スロットリングの影響を受けにくい（DOM 静的解析中心）。フレークが出やすいのは performance カテゴリだが、**brief の確定事項どおり performance は非 blocking** なので、フレークがゲートを赤くすることはない。
- 唯一の実行時フレーク要因は「Chrome プロセス起動そのものの失敗」（今回 CHROME_PATH 未設定時に実際に踏んだ）。CHROME_PATH をハードコードで確実に渡す設計にしていれば再現性は高い。

### 争点E（fan-out分割・infra視点のみ）

R1（判定基盤: `tools/run_checks.sh` / 新設 `tools/run_lighthouse.mjs` / `package.json`）は他ロールと**ファイルが競合しない**ため、R2（`app/globals.css` 等）・R3（`src/ui/*`）と並行着手して問題ない。R4（`e2e/*.spec.ts`）が R1 の新設スクリプトの挙動（対象 URL・スコア閾値）に依存する場合は、R1 が先に「対象 URL と判定ロジックのインターフェース」だけ 1 行仕様として共有すれば R4 は着手できる（契約先行）。

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
1. `app/globals.css` の `:root { --ring: oklch(0.708 0 0) }` → **`oklch(0.6 0 0)`** に変更。これは既存の `--border`（ライト）と**完全に同じ値**（§2.2 の表で 3.95:1 実測済み・新規 raw 値を増やさない）。再計算: vs `--color-bg` 白 = **3.947:1**、vs `--color-bg-subtle`（カード面 0.97）= **3.619:1**。両方 3:1 を安全マージン込みで通過。
2. `.dark { --ring: oklch(0.556 0 0) }` は**変更不要**（vs bg 4.183:1 / vs card 3.194:1、既に通過）。
3. `focus-visible:ring-ring/50` → **`focus-visible:ring-ring`**（`/50` を外す）を `button.tsx` と `input.tsx` の両方に適用。
4. 見落とし: `app/globals.css:149` の `@layer base { * { @apply border-border outline-ring/50; } }` も同じ `/50` パターンを **サイト全体のネイティブ `<a>` のデフォルトフォーカス** に適用している（Button 由来でない `Link`＝一覧の詳細リンク・`back-link.tsx`・`error-notice.tsx` の再試行リンクはここが効く）。ここも `outline-ring/50` → **`outline-ring`** に揃えないと、ボタン/入力欄だけ直って主要ナビゲーションリンクは 3:1 未達のまま残る。
5. `check_contrast.py` の `CHECK_PAIRS` に `("ring", "background", 3.0, ...)` を追加できる状態にするのが (4) の効能でもある: `/50` を CSS 変数側でなく Tailwind ユーティリティ側の別ファイルで指定していると機械検査が拾えない。**opacity 修飾子を外して token 自体の値だけで 3:1 を満たす設計にすることで、初めて `check_contrast.py` が ring を機械検査できるようになる**（争点 A/B 側で `CHECK_PAIRS` 追加を推奨）。

採らない案: alpha を上げて L はそのまま、は不可能と判定済み（α=1.0 でも 2.593:1 が上限）。ring-offset の追加は根本解決にならない（色自体のコントラストは変わらない）ので採らない。

## C-2. ライブリージョンの入れ子（#180）

`app/[locale]/page.tsx:300` の `<section aria-live="polite">` の中に、`Suspense` fallback として `LoadingIndicator`（`role="status"` + `aria-live="polite"` を自前で持つ）が挿入される。`LoadingIndicator` の呼び出し箇所は **全リポジトリ中この 1 箇所のみ**（grep 確認済み）。WAI-ARIA は入れ子のライブリージョンを避けるべきと明記しており、AT/ブラウザ組み合わせにより二重読み上げ・無視のいずれも起こりうる（未定義動作）。

**是正案（採用推奨）**: `LoadingIndicator` から `role="status"` / `aria-live="polite"` を削除し、テキスト表示専用の `<p>` にする（外側の `section` が唯一のライブリージョンとして機能）。唯一の使用箇所なので**再利用時の汎用性を犠牲にしない**。`loading-indicator.test.tsx` の該当アサーション（`getByRole('status')` 等）を合わせて書き換える必要あり（Red→Green・R2 の TDD 対象）。0 件（`role="status"`, `repository-list.tsx:37`）と エラー（`role="alert"`, `error-notice.tsx:57`）は `section` の外にあるため対象外・現状のままでよい。

## C-3. ルート変更時のフォーカス移動（§7.1）— ブリーフの前提を実地検証で覆す

ブリーフは「GET フォームで全ページ再読み込みされるなら不要では」と問うが、**それは検索フォームの初回送信だけに当てはまり、E-15 の操作レビュー手順が実際に踏む遷移の大半には当てはまらない**。

- `search-form.tsx`: `<form method="get">` → 確かにネイティブフルリロード。ここは §7.1 の対象外で正しい。
- `pagination.tsx` / `sort-picker.tsx` / `per-page-picker.tsx` / `repository-list.tsx` の詳細リンク / `back-link.tsx`: **すべて `next/link`**。App Router 配下で JS ハイドレーション後はクライアント遷移になる（フルリロードしない）。
- `app/[locale]/layout.tsx:20-23` の `metadata.title` は **`'gem-hunter'` の静的 1 値のみ**。`app/[locale]/page.tsx` にも `app/[locale]/repos/[owner]/[repo]/page.tsx` にも `generateMetadata` は無い（grep 0 件）。つまり **一覧→詳細のクライアント遷移で `document.title` は一切変化しない**。ルートアナウンサー（brief引用の Next.js 既知挙動）は動きようがない。
- 決定的な先例: 同ディレクトリの `not-found.tsx` は **まさにこの問題を PR #127 で対処済み**（`src/ui/set-document-title.tsx`、コメントに「ルートアナウンサーは `document.title` の変化だけを見る」と明記）。しかし成功パス（`repos/[owner]/[repo]/page.tsx`）には同等の仕組みが**無い**（grep 0 件）。0 件成功パスの詳細ページは deep link で開いても `<title>` が `gem-hunter` のまま（SSR 段階から `generateMetadata` 自体が無い）— a11y だけでなく地味な既存バグ。
- さらに実装上の実害: `page.tsx:236` の `suspenseKey`（検索 URL 全体から生成）が `page.tsx:301`/`306` の両 `Suspense` の `key` に使われており、ページ送り・ソート・件数変更のたびに **`Pagination` を含む `SearchBody` 全体が unmount→remount される**。React の unmount はフォーカスを保持しない（ブラウザは `document.body` へ落とす）。つまり「Next page」リンクを Enter で押すと、**まさにそのリンク自体が消えてフォーカスが失われる**可能性が高い（要検証: Playwright で `document.activeElement` を押下前後で比較。`SortPicker`/`PerPagePicker` は Suspense 外にあるため対象外の可能性があるが、これも実測で確定させるべき）。

**結論（§7.1 は書き換えない・実装すべき）**:
- 対象範囲を明確化: **検索フォーム送信は対象外、ページ送り/ソート/件数切替/一覧⇄詳細のクライアント遷移が対象**（ドキュメント側にこの 1 行を足すのは docs_trace の担当範囲として提案）
- 実装: (a) 一覧⇄詳細は `SetDocumentTitle` パターンを成功パスにも拡張（詳細ページに `item.fullName` を渡す。一覧側は既存の `messages.home.title` で可）。(b) ページ送り/ソート/件数切替は結果見出しに `tabIndex={-1}` を付け、`searchParams` 変化を検知する薄いクライアントコンポーネントで `.focus()` する。新規クライアントコンポーネントが最低 1〜2 個増える（`src/ui/` 配下）ため、R2 のファイル分割（globals.css / components/*.tsx / page.tsx ライブリージョン）に**新規ファイル追加の余地**を残しておくこと（E の分割案への申し送り）。

## 採用しない案（明言）
- ring: alpha だけ上げる案 → 数学的に届かないため不採用（上記）
- LoadingIndicator: 汎用性を優先して role/aria-live を残す案 → 唯一の使用箇所であり入れ子の実害の方が大きいため不採用
- §7.1 の適用範囲を「GET フォームだから不要」に緩めて書き換える案 → 実地調査（`generateMetadata` 0 件・`suspenseKey` remount）で反証されたため不採用
