<!--entry
author: e2e_verify
round: 2
kind: rebuttal
ts: 2026-08-20T11:32:00+09:00
-->

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
