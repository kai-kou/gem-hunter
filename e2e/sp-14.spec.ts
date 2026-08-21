import { expect, test } from '@playwright/test'

import { createAxeBuilder } from './axe'
import { readDigestPackageNames } from './helpers'

/**
 * SP-14: キーワードを入力しなくても、その日の Gem が一覧で出る（`ADR 0014` / `AR-9` / `US-30`〜`US-32`）。
 * `docs/02_requirements/user-story-map.md` §5.3 `SP-14` の操作レビュー手順（Issue #251）を
 * そのまま E2E に写す（`sprint-development-rules.md` `SD-2`）。対応 `AC`: 新規追加なし
 * （`AC-9`「キーボードのみで完走できる」は横断適用）。
 *
 * データ源: `public/data/daily-digest.json`（`StaticGemDigest` がバンドル取り込みで読む）。
 * 並び替えは `getDailyDigest` usecase が `?date=YYYYMMDD` をシードにして決定論的に行うため、
 * `?date=` を付ければ「翌日まで待つ」ことなく顔ぶれの入れ替わりを検証できる（`ADR 0014` §2.2）。
 */

test.describe('SP-14: キーワード非依存の発見面', () => {
  test('手順1: /ja を開いた瞬間に「今日の Gem」が見出しとして表示される（AR-9）', async ({
    page,
  }) => {
    await page.goto('/ja')
    // 検索していない状態（キーワード未入力）でも見出しが出る。
    await expect(page.getByRole('heading', { name: '今日の Gem', level: 2 })).toBeVisible()
  })

  test('手順2: Gem がちょうど 5 件、重複なく並んで見える（ADR 0014 §2.1・既定 5 件）', async ({
    page,
  }) => {
    await page.goto('/ja?date=20260820')
    const names = await readDigestPackageNames(page)
    // 🔴 候補プール（`public/data/daily-digest.json`）は 294 件あり、`DAILY_DIGEST_LIMIT = 5`
    //    なので **必ず 5 件** 出る。「1 件以上 5 件以下」だと 1 件しか出ない回帰を検出できない。
    expect(names).toHaveLength(5)
    // 同じ Gem が二重に描画されていない（重複表示の検出）。
    expect(new Set(names).size).toBe(names.length)
  })

  test('手順3: リロード（同一 URL の再取得）で同じ並びが再現される（ADR 0014 §2.2 決定論性）', async ({
    page,
  }) => {
    await page.goto('/ja?date=20260820')
    const first = await readDigestPackageNames(page)

    await page.goto('/ja?date=20260820')
    const second = await readDigestPackageNames(page)

    // 完全一致（順序込み）。「先頭 3 件が一致」でも一致するが、決定論なら全件一致するのが正。
    expect(second).toEqual(first)
  })

  test('手順4: ?date=YYYYMMDD で日付を進めると顔ぶれ / 並び順が入れ替わる（US-31 / ADR 0014 §2.2）', async ({
    page,
  }) => {
    await page.goto('/ja?date=20260820')
    const day1 = await readDigestPackageNames(page)

    await page.goto('/ja?date=20260821')
    const day2 = await readDigestPackageNames(page)

    // 決定論的シードなので日付が変われば「先頭要素の名前が違う」または「並び順が異なる」の
    // いずれかは必ず成立する（`get-daily-digest.ts` のシャッフル + gemIndex asc の 2 段）。
    // 稀に SHA-256 の衝突順序で先頭が同じでも起こりうるため、配列全体の一致で判定する。
    expect(day2).not.toEqual(day1)
  })

  test('手順5: Tab で Gem リンクへ到達でき、Enter で詳細ページへ遷移する（AC-9 / AC-4）', async ({
    page,
  }) => {
    await page.goto('/ja?date=20260820')
    const names = await readDigestPackageNames(page)
    expect(names.length).toBeGreaterThan(0)

    const firstLink = page
      .getByRole('region', { name: '今日の Gem' })
      .getByRole('link', { name: names[0] })
      .first()
    // href が /{locale}/repos/{owner}/{repo} 形式（AC-4・独立 URL）である。
    const href = await firstLink.getAttribute('href')
    expect(href).toMatch(/^\/ja\/repos\/[^/]+\/[^/]+$/)

    // Tab キーで到達できることを確認（AC-9・キーボードのみで完走）。到達したら Enter で遷移する。
    // 決定論的に何回 Tab するかは要素数で変わるため、Locator.focus() ではなく地道に押していく。
    let landed = false
    for (let i = 0; i < 40; i++) {
      const isFocused = await firstLink.evaluate((el) => el === document.activeElement)
      if (isFocused) {
        landed = true
        break
      }
      await page.keyboard.press('Tab')
    }
    expect(landed, 'Tab を 40 回押しても最初の Gem リンクへフォーカスが到達しなかった').toBe(true)

    await page.keyboard.press('Enter')
    // 詳細ページの URL 形式へ遷移したことを見る（スタブ GitHub API の応答内容自体は SP-14 の
    // スコープ外・遷移そのものだけを見る）。
    await expect(page).toHaveURL(/\/ja\/repos\/[^/]+\/[^/]+/)
  })

  test('手順6: 出典表示（Ecosyste.ms / ライセンス / 改変の明示）が表示されている（D-29）', async ({
    page,
  }) => {
    await page.goto('/ja?date=20260820')

    // ライセンスは <a> でクリック可能（改変元へ辿れる）。ラベル文言は messages/ja.json に一致。
    // 🔴 D-33（#308）で出典行を「このデータについて: …」へ刷新した。出典元（Ecosyste.ms）と
    //    ライセンスリンク、改変の明示という D-29 の 3 要件は文言が変わっても満たし続ける。
    await expect(page.getByText(/このデータについて/)).toBeVisible()
    await expect(page.getByText(/Ecosyste\.ms/)).toBeVisible()
    // 🔴 指標の表示名（`D-33`・初見フィードバック③）を実メッセージファイル経由で固定する。
    //    コンポーネントテストは labels をテストローカルで注入するため、実文言の回帰はここでしか拾えない。
    await expect(page.getByText(/利用パッケージ数/).first()).toBeVisible()
    const licenseLink = page.getByRole('link', { name: 'CC BY-SA 4.0' })
    await expect(licenseLink).toBeVisible()
    await expect(licenseLink).toHaveAttribute(
      'href',
      'https://creativecommons.org/licenses/by-sa/4.0/',
    )
    // 改変の明示（並び順を日付から毎日算出している旨・D-29）
    await expect(page.getByText(/日付をもとに毎日算出/)).toBeVisible()
  })

  test('キーワード検索中はダイジェストを表示しない（排他表示・SP-1/SP-7/SP-10 との衝突回避）', async ({
    page,
  }) => {
    // 🔴 このテストが無いと、後続セッションが `app/[locale]/page.tsx` の `hasKeyword` 分岐を
    //    消しても SP-14 のテストは緑のまま、SP-1 / SP-7 / SP-10 だけが原因不明で落ちる
    //    （検索結果一覧と Gem 一覧が同時に `<ol>` として並び、`getByRole('list').first()` が
    //    Gem 一覧を先に拾うため）。排他表示そのものを SP-14 側で固定する。
    await page.goto('/ja?q=react')

    // 検索結果が描画されていること（＝検索経路が生きている状態での検証であること）を先に確認する。
    await expect(page.getByRole('link', { name: 'octostub/octo-widgets' })).toBeVisible()

    await expect(page.getByRole('heading', { name: '今日の Gem', level: 2 })).toHaveCount(0)
    await expect(page.getByRole('region', { name: '今日の Gem' })).toHaveCount(0)
  })

  test('未検索状態（ダイジェスト表示）に serious/critical の a11y 違反がない（NFR-26）', async ({
    page,
  }) => {
    // 既存の a11y スイート（`e2e/a11y.spec.ts` / `sp-9-a11y.spec.ts`）はいずれも検索後の画面を
    // 見ており、ダイジェストが表示された状態は一度も axe に掛かっていない。ここで埋める。
    await page.goto('/ja?date=20260820')
    await expect(page.getByRole('heading', { name: '今日の Gem', level: 2 })).toBeVisible()

    const results = await createAxeBuilder(page).analyze()
    const violations = results.violations.filter(
      (v) => v.impact === 'serious' || v.impact === 'critical',
    )
    expect(violations, JSON.stringify(violations, null, 2)).toEqual([])
  })

  test('en ロケール（/en）でも英語の見出しと出典表示が出る（E-4）', async ({ page }) => {
    await page.goto('/en?date=20260820')
    await expect(page.getByRole('heading', { name: "Today's Gems", level: 2 })).toBeVisible()
    await expect(page.getByText(/About this data/)).toBeVisible()
    await expect(page.getByText(/Ecosyste\.ms/)).toBeVisible()
    await expect(page.getByText(/recomputed daily from the date/)).toBeVisible()
  })
})
