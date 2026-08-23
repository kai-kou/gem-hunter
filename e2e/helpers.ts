import { randomBytes } from 'node:crypto'

import { expect } from '@playwright/test'
import type { Locator, Page } from '@playwright/test'

/**
 * スタブ（`e2e/stub/server.mjs`）のデータセットマーカーに、他ファイル・retry 試行との
 * キャッシュ衝突を避ける接尾辞を足した一意キーワード（マーカーの判定は部分一致なので足してよい）。
 * 衝突回避の手段（バイト数・エンコーディング）をここ 1 箇所に閉じ込める。
 */
export function uniqueKeyword(marker: string): string {
  return `${marker}-${randomBytes(4).toString('hex')}`
}

/**
 * `gem-badge` データセット用の一意キーワード。`e2e/sp-18.spec.ts`（バッジ経路の検証）と
 * `e2e/sp-19.spec.ts`（Issue #453 scoped hybrid の検証）の両方が同じデータセットを使うため
 * 共有する（`e2e/` の外へは出さない・`searchFor` と同じ置き方）。
 */
export function uniqueGemBadgeKeyword(): string {
  return uniqueKeyword('gem-badge')
}

/**
 * 「破綻しない」の述語: 横スクロールが発生しない（`NFR-15` / WCAG 2.2 SC 1.4.10 Reflow）。
 * `document.scrollingElement` の `clientWidth` は縦スクロールバー分を既に除いた値なので、
 * スクロールバー由来の偽陽性は原理的に発生しない。
 *
 * 🔴 `body` / `html` に `overflow-x: hidden` / `clip` を足すと、`body` 自身がスクロール
 * コンテナになって viewport への伝播が止まり、**この述語は恒久的に成立してしまう**
 * （溢れが復活しても検知できなくなる）。塞ぐのは常に折り返し指定の側で行う。
 *
 * @param label 失敗時にどの画面での測定かを示す短い語（省略時は測定値だけを出す）
 */
export async function expectNoHorizontalScroll(page: Page, label?: string): Promise<void> {
  const overflow = await page.evaluate(() => {
    const el = document.scrollingElement ?? document.documentElement
    return { scrollWidth: el.scrollWidth, clientWidth: el.clientWidth }
  })
  const detail = JSON.stringify(overflow)
  // +1px は sub-pixel 丸め対策
  expect(
    overflow.scrollWidth,
    label === undefined ? detail : `${label}: ${detail}`,
  ).toBeLessThanOrEqual(overflow.clientWidth + 1)
}

/**
 * 検索欄にキーワードを入力し、検索を実行する（SP-1 の操作レビュー手順 2. の共通化）。
 * `sp-1` / `sp-2` / `sp-3` / `a11y` の 4 ファイルで同じ 2 行が重複していたため切り出した
 * （`e2e/axe.ts` と同じ薄いヘルパーの置き方）。URL への反映やその後の検証は
 * 各 `test.step()` の意図が読めることを優先し、呼び出し側に委ねる（ここに `expect` は入れない）。
 */
export async function searchFor(page: Page, keyword: string): Promise<void> {
  await page.getByRole('searchbox', { name: '検索キーワード' }).fill(keyword)
  await page.getByRole('button', { name: '検索' }).click()
}

/**
 * `target` にフォーカスが乗るまで `Tab` を押し続ける（`SP-10` 操作レビュー手順 1.
 * キーボード完走のための共通化）。固定 Tab 回数の決め打ちは、中間に要素が 1 つ
 * 増減しただけで全テストが壊れるため避ける。
 *
 * 🔴 判定は `page.locator(':focus').and(target).count()`（`.count()` 版）を採る。
 * `target.evaluate((el) => el === document.activeElement)` 版は Playwright の
 * actionability 待機を内包するため、`target` のロケータが一度も要素にマッチしない
 * （ロール名の誤り等）場合に 1 回の呼び出しが外側のテストタイムアウト（60 秒）近くまで
 * ブロックし、下記の診断メッセージが一度も出ないまま Playwright の汎用タイムアウトで
 * 落ちる（原因が分かりにくい失敗になる）。`.count()` は actionability 待機を伴わない
 * 即時 DOM 照会なので、ロケータ誤りでも数秒で自前のエラーメッセージにより速く失敗する
 * （`content/discussions/sp10_a11y_20260820/whiteboard.md` round2 e2e_verify 自己批判・
 * round3 lead 判定 D-2 で確定）。
 */
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

/** `measureFocusIndicator` の返り値。`kind: 'none'` はリング・アウトラインのどちらも検出できなかったことを表す。 */
export type FocusIndicatorMeasurement = {
  kind: 'box-shadow' | 'outline' | 'none'
  /** 実効コントラスト比（背景に対して alpha 合成した後の値）。`kind: 'none'` のときは 1。 */
  contrastRatio: number
  /** リング/アウトラインの太さ（CSS px）。 */
  widthPx: number
  /** デバッグ用の生値（宣言値ではなく `getComputedStyle` の実効値）。 */
  raw: { boxShadow: string; outlineStyle: string; outlineWidth: string; outlineColor: string }
}

/**
 * フォーカスインジケータ（`box-shadow` のリング、無ければネイティブ `outline`）の
 * **実描画** コントラスト比と太さを計測する（SP-10・PR #183 の欠陥是正）。
 *
 * 🔴 なぜ必要か: `tools/check_contrast.py` は `app/globals.css` の CSS **宣言値**
 * （例 `--ring: oklch(0.6 0 0)`）しか読めない。Tailwind ユーティリティ側の `/NN`
 * 不透明度修飾子（例 `ring-ring/50`）や `transition-all` の遷移途中の値は宣言値に
 * 現れないため、静的検査を素通りする（`ui-ux-guidelines.md` §7 の三層防御・層 3）。
 * 本関数は `getComputedStyle` が返す **実効値**（カスケード・トランジション適用後）を読み、
 * `<canvas>` の 2 点サンプリング（不透明背景 1 回・黒背景 1 回に同じ色を重ね描きし、差分から
 * alpha とアルファ抜き RGB を逆算する）で `oklch()` / `lab()` / `color-mix()` など
 * 任意の CSS 色関数を実際のブラウザ変換で RGB へ解決する（自前の oklch 変換式を二重実装しない）。
 *
 * @param page Playwright の Page（`waitForTimeout` に使う）
 * @param target フォーカス対象（呼び出し側で `tabUntilFocused` 済みであること）
 */
export async function measureFocusIndicator(
  page: Page,
  target: Locator,
): Promise<FocusIndicatorMeasurement> {
  // `transition-all`（button.tsx 等・150ms）がある要素は遷移完了を待たないと
  // 遷移途中の低 alpha / 極細幅を実効値として拾ってしまう（SP-10 実測で判明）。
  await page.waitForTimeout(300)

  return target.evaluate(
    (el): FocusIndicatorMeasurement => {
      // --- 色解決: 任意の CSS 色文字列 -> {r,g,b,a}（0-255 / 0-1）。canvas の実合成結果から逆算する。
      function resolveColor(colorStr: string): { r: number; g: number; b: number; a: number } {
        const canvas = document.createElement('canvas')
        canvas.width = 1
        canvas.height = 1
        const ctx = canvas.getContext('2d', { willReadFrequently: true })!
        ctx.clearRect(0, 0, 1, 1)
        ctx.fillStyle = '#ffffff'
        ctx.fillRect(0, 0, 1, 1)
        ctx.fillStyle = colorStr
        ctx.fillRect(0, 0, 1, 1)
        const overWhite = ctx.getImageData(0, 0, 1, 1).data
        ctx.clearRect(0, 0, 1, 1)
        ctx.fillStyle = '#000000'
        ctx.fillRect(0, 0, 1, 1)
        ctx.fillStyle = colorStr
        ctx.fillRect(0, 0, 1, 1)
        const overBlack = ctx.getImageData(0, 0, 1, 1).data
        const aPerChannel = [0, 1, 2].map((i) => 1 - (overWhite[i] - overBlack[i]) / 255)
        const a = Math.max(0, Math.min(1, (aPerChannel[0] + aPerChannel[1] + aPerChannel[2]) / 3))
        const rgb = [0, 1, 2].map((i) => (a > 0.001 ? overBlack[i] / a : overWhite[i]))
        return { r: rgb[0], g: rgb[1], b: rgb[2], a }
      }

      function relLuminance(r: number, g: number, b: number): number {
        const chan = (c: number) => {
          const v = c / 255
          return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4
        }
        return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)
      }

      function contrastRatio(
        c1: { r: number; g: number; b: number },
        c2: { r: number; g: number; b: number },
      ): number {
        const l1 = relLuminance(c1.r, c1.g, c1.b)
        const l2 = relLuminance(c2.r, c2.g, c2.b)
        const [hi, lo] = l1 >= l2 ? [l1, l2] : [l2, l1]
        return (hi + 0.05) / (lo + 0.05)
      }

      function blendOver(
        fg: { r: number; g: number; b: number; a: number },
        bg: { r: number; g: number; b: number },
      ): { r: number; g: number; b: number } {
        return {
          r: fg.a * fg.r + (1 - fg.a) * bg.r,
          g: fg.a * fg.g + (1 - fg.a) * bg.g,
          b: fg.a * fg.b + (1 - fg.a) * bg.b,
        }
      }

      // box-shadow の値をトップレベルのカンマで分割する（rgba(0, 0, 0, 0) 等 関数内のカンマは無視）。
      function splitTopLevel(value: string): string[] {
        const layers: string[] = []
        let depth = 0
        let current = ''
        for (const ch of value) {
          if (ch === '(') depth++
          if (ch === ')') depth--
          if (ch === ',' && depth === 0) {
            layers.push(current.trim())
            current = ''
          } else {
            current += ch
          }
        }
        if (current.trim()) layers.push(current.trim())
        return layers
      }

      function parseLayer(layer: string): { color: string; spread: number } {
        const lengths = [...layer.matchAll(/(-?[\d.]+)px/g)].map((m) => parseFloat(m[1]))
        const color = layer
          .replace(/-?[\d.]+px/g, '')
          .replace(/\binset\b/g, '')
          .trim()
        // box-shadow は [x, y, blur, spread] の順（inset の有無・順序は無視して良い。
        // このプロジェクトの ring ユーティリティは常に 4 値 + spread のみで幅を作るため）。
        return { color, spread: lengths[3] ?? 0 }
      }

      // 背景色: 最初に非透明な background-color を持つ祖先を採用する（無ければ body）。
      function resolveBackground(start: Element): { r: number; g: number; b: number } {
        let node: Element | null = start
        while (node) {
          const bg = getComputedStyle(node).backgroundColor
          const resolved = resolveColor(bg)
          if (resolved.a > 0.99) return resolved
          node = node.parentElement
        }
        return resolveColor(getComputedStyle(document.body).backgroundColor)
      }

      const cs = getComputedStyle(el)
      const bg = resolveBackground(el)

      const boxShadow = cs.boxShadow
      const raw = {
        boxShadow,
        outlineStyle: cs.outlineStyle,
        outlineWidth: cs.outlineWidth,
        outlineColor: cs.outlineColor,
      }

      if (boxShadow && boxShadow !== 'none') {
        const layers = splitTopLevel(boxShadow).map(parseLayer)
        // 実際に見えるリング = alpha > 0 かつ spread が最大のレイヤー。
        let best: { color: string; spread: number; a: number } | null = null
        for (const layer of layers) {
          const resolved = resolveColor(layer.color)
          if (resolved.a <= 0.001) continue
          if (best === null || layer.spread > best.spread) {
            best = { color: layer.color, spread: layer.spread, a: resolved.a }
          }
        }
        if (best !== null && best.spread > 0) {
          const resolved = resolveColor(best.color)
          const blended = blendOver(resolved, bg)
          return {
            kind: 'box-shadow',
            contrastRatio: contrastRatio(blended, bg),
            widthPx: best.spread,
            raw,
          }
        }
      }

      if (cs.outlineStyle !== 'none') {
        const resolved = resolveColor(cs.outlineColor)
        const blended = blendOver(resolved, bg)
        return {
          kind: 'outline',
          contrastRatio: contrastRatio(blended, bg),
          widthPx: parseFloat(cs.outlineWidth) || 0,
          raw,
        }
      }

      return { kind: 'none', contrastRatio: 1, widthPx: 0, raw }
    },
  )
}

/**
 * 「今日の Gem」セクション内の、順序どおりの packageName 一覧を取り出す（`SP-14` / `SP-15` の
 * 操作レビューで共通に使う）。セクション直下の `<ol> > <li>` だけを対象にし、各 `<li>` の
 * 1 本目の `<a>`（詳細ページへのリンク）のテキストを packageName とみなす。
 * `sp-14.spec.ts` / `sp-15.spec.ts` で同一実装が重複していたため切り出した（`searchFor` と同じ方針）。
 * `expect` は入れない（呼び出し側の `test.step()` の意図を優先する）。
 */
export async function readDigestPackageNames(page: Page): Promise<string[]> {
  const section = page.getByRole('region', { name: '今日の Gem' })
  // 🔴 `locator.count()` は要素出現を自動リトライしないため、先にセクションの出現を待つ
  //    （抽出元 `sp-14.spec.ts` が持っていた待機。SSR の現状では実害がないが、将来
  //     クライアント側描画へ変わったときのフレークを防ぐ）。
  await section.waitFor({ state: 'visible' })
  const items = section.locator('ol > li')
  const count = await items.count()
  const names: string[] = []
  for (let i = 0; i < count; i++) {
    const link = items.nth(i).getByRole('link').first()
    names.push((await link.innerText()).trim())
  }
  return names
}
