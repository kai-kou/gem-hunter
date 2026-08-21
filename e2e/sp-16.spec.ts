import { randomBytes } from 'node:crypto'
import { expect, test, type Page } from '@playwright/test'
import type { Result } from 'axe-core'
import { createAxeBuilder } from './axe'
import { searchFor } from './helpers'
import { SEARCH_PARAM_KEYS } from '../src/ui/url/search-params'

/**
 * SP-16: 検索結果を Gem Index（過小評価度）順に並べ替えられる。
 * `docs/02_requirements/user-story-map.md` §5.3 `SP-16` の操作レビュー手順をそのまま写す
 * （`sprint-development-rules.md` `SD-2`）。設計判断の正本は
 * `content/discussions/sp16-gem-index-sort-20260821/whiteboard.md` の `lead` 判定（`D-A`〜`D-N`）。
 *
 * 飼い主決定（変更不可・Issue #285）:
 *   ① Gem Index を持たない結果は絞り込まず末尾に残す（件数は変わらない）
 *   ② 最大 1,000 件を取得してから並べ替える（ページをまたいでも大小関係が破綻しない）
 *
 * 🔴 実装手段レベルの判断（SD-3 対象外・仮定を 1 行記録）: `listGemFacetsUseCase` の候補プールは
 * `public/data/daily-digest.json`（本番と同一の静的ファイル）を直接読む（`src/composition/container.ts`
 * の `sharedGemDigestPort`）。そのためスタブ（`gem-sort-hits` マーカー）は検索結果の一部に
 * **実際にそのファイルへ存在する `repositoryFullName`** を混ぜて「facet あり」グループを作り、
 * 残りは実在しない合成名で「facet なし」グループを作る（`e2e/stub/server.mjs` 参照）。
 * 本番データが再生成されて中身が変わっても壊れないよう、期待する並び順は数値として
 * ハードコードせず、画面から読み取った値の単調性（非減少）で検証する。
 */

/** 他ファイル・retry 試行との衝突を避けるため、実行のたびに一意なキーワードを生成する。 */
function uniqueGemSortKeyword(): string {
  return `gem-sort-hits-${randomBytes(4).toString('hex')}`
}

function seriousOrCritical(violations: Result[]): Result[] {
  return violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
}

type ResultRow =
  | { kind: 'ranked'; fullName: string; gemIndexValue: number; hasDependentCount: boolean }
  | { kind: 'unranked'; fullName: string }
  | { kind: 'divider' }

/**
 * 検索結果一覧（`<ul> > <li>`）を先頭から読み取り、各行が「Gem Index を持つカード」
 * 「持たないカード」「区切り見出し」のいずれかを判定する。区切り見出しはリンクを持たない
 * `<li>` として実装されている（`repository-list.tsx`）ため、リンクの有無で判別できる。
 */
async function readResultRows(page: Page): Promise<ResultRow[]> {
  const items = page.getByRole('list').first().locator(':scope > li')
  const count = await items.count()
  const rows: ResultRow[] = []

  for (let i = 0; i < count; i++) {
    const li = items.nth(i)
    const link = li.getByRole('link')
    const hasLink = (await link.count()) > 0

    if (!hasLink) {
      rows.push({ kind: 'divider' })
      continue
    }

    const fullName = (await link.first().innerText()).trim()
    const text = (await li.innerText()).trim()
    // ラベル文言（ja: 「Gem Index」「被依存数」）は本番と同じ messages/ja.json 由来。
    const match = text.match(/Gem Index\s+(-?[\d,]+(?:\.\d+)?)/)

    if (match) {
      rows.push({
        kind: 'ranked',
        fullName,
        gemIndexValue: Number(match[1].replace(/,/g, '')),
        hasDependentCount: /被依存数/.test(text),
      })
    } else {
      rows.push({ kind: 'unranked', fullName })
    }
  }

  return rows
}

test('SP-16: 検索結果を Gem Index 順に並べ替えても、非保有分は末尾に残り、ページをまたいでも大小関係が破綻しない', async ({
  page,
}) => {
  const keyword = uniqueGemSortKeyword()

  await test.step('前提: 36 件ヒットする検索を実行しておく（既定: 関連度順 / 20 件表示）', async () => {
    await page.goto('/ja')
    await searchFor(page, keyword)
    await expect(page.getByRole('list').first().locator(':scope > li')).toHaveCount(20)
    await expect(page.getByText('36 件中 20 件を表示', { exact: true })).toBeVisible()
    // 並び替え前は Gem Index 情報を一切表示しない（回帰なし・並び順ピッカーのリンク文言は対象外）。
    await expect(
      page.getByRole('list').first().getByText('Gem Index', { exact: false }),
    ).toHaveCount(0)
  })

  await test.step('1. 並び順を「Gem Index 順」へ変える → URL に sort=gem-index が乗り、並びが変わる', async () => {
    await page
      .getByRole('navigation', { name: '並び順' })
      .getByRole('link', { name: 'Gem Index 順' })
      .click()

    await expect(page).toHaveURL(new RegExp(`[?&]${SEARCH_PARAM_KEYS.sort}=gem-index(&|$)`))
    // 並び順切替は 1 ページ目へ戻す（既存の SortPicker と同じ挙動）。
    await expect(page).not.toHaveURL(new RegExp(`[?&]${SEARCH_PARAM_KEYS.page}=`))

    await expect(
      page.getByRole('navigation', { name: '並び順' }).getByRole('link', { name: 'Gem Index 順' }),
    ).toHaveAttribute('aria-current', 'true')

    // 件数表示は並べ替え前後で変わらない（飼い主決定①・絞り込まない）。
    await expect(page.getByText('36 件中 20 件を表示', { exact: true })).toBeVisible()
    // 🔴 件数表示（SearchStatusText）と一覧本体（SearchBody）は別々の Suspense 境界で、
    //    後者は `gemFacets` の取得も待つため後から描画が完了する。カード読み取りの前に
    //    実際に 20 件描画されるまで待つ（`toHaveCount` の自動リトライで待機する）。
    await expect(page.getByRole('list').first().locator(':scope > li')).toHaveCount(20)
  })

  let page1LastValue = Number.NaN

  await test.step('2. 1 ページ目のカードに Gem Index（と被依存数）が出ていて、なぜ上位かが分かる', async () => {
    const rows = await readResultRows(page)
    expect(rows).toHaveLength(20)

    // 候補プール由来の facet を持つ結果が 20 件を超える設定（gem-sort-hits スタブ）のため、
    // 1 ページ目は「持たない」結果もまだ現れず、全件ランクあり（区切りも出ない）。
    for (const row of rows) {
      expect(row.kind).toBe('ranked')
    }
    const ranked = rows.filter(
      (r): r is Extract<ResultRow, { kind: 'ranked' }> => r.kind === 'ranked',
    )
    // 「なぜ上位か」= Gem Index 値と被依存数が並んで見える。
    expect(ranked.every((r) => r.hasDependentCount)).toBe(true)

    // 単調非減少（Gem Index 昇順 = 値が小さいほど上位）。
    const values = ranked.map((r) => r.gemIndexValue)
    for (let i = 1; i < values.length; i++) {
      expect(values[i]).toBeGreaterThanOrEqual(values[i - 1])
    }
    page1LastValue = values[values.length - 1]
  })

  await test.step('3. 2 ページ目へ進んでも Gem Index の大小関係が破綻していない', async () => {
    await page
      .getByRole('navigation', { name: '検索結果のページ' })
      .getByRole('link', { name: '次のページへ' })
      .click()

    await expect(page).toHaveURL(new RegExp(`[?&]${SEARCH_PARAM_KEYS.page}=2(&|$)`))
    await expect(page).toHaveURL(new RegExp(`[?&]${SEARCH_PARAM_KEYS.sort}=gem-index(&|$)`))
    // 4. 非保有分の総数（36 - 20 = 16 件）が末尾に残っている（総件数表示は変わらない）。
    await expect(page.getByText('36 件中 16 件を表示', { exact: true })).toBeVisible()
    // データ 16 件 + 区切り見出し 1 本 = 17 要素（両グループが存在する設計・描画完了を待つ）。
    await expect(page.getByRole('list').first().locator(':scope > li')).toHaveCount(17)

    const rows = await readResultRows(page)
    const rankedRows = rows.filter(
      (r): r is Extract<ResultRow, { kind: 'ranked' }> => r.kind === 'ranked',
    )
    const dividerRows = rows.filter((r) => r.kind === 'divider')
    const unrankedRows = rows.filter((r) => r.kind === 'unranked')

    // 1 ページ目からの続き（ランクあり）が先頭に来て、その後に区切り、その後に非保有分が続く。
    expect(rankedRows.length).toBeGreaterThan(0)
    expect(dividerRows).toHaveLength(1)
    expect(unrankedRows.length).toBeGreaterThan(0)
    expect(rows.map((r) => r.kind)).toEqual([
      ...Array<'ranked'>(rankedRows.length).fill('ranked'),
      'divider',
      ...Array<'unranked'>(unrankedRows.length).fill('unranked'),
    ])

    // ページをまたいでも大小関係が破綻しない: 2 ページ目内でも単調非減少、かつ
    // 1 ページ目の最後の値 <= 2 ページ目の最初の値（飼い主決定②の検証）。
    const values = rankedRows.map((r) => r.gemIndexValue)
    for (let i = 1; i < values.length; i++) {
      expect(values[i]).toBeGreaterThanOrEqual(values[i - 1])
    }
    expect(Number.isNaN(page1LastValue)).toBe(false)
    expect(values[0]).toBeGreaterThanOrEqual(page1LastValue)
  })

  await test.step('5. 詳細へ入って戻る → キーワード・ページ・ソートがすべて元のまま（AC-6 / AC-7）', async () => {
    const rows = await readResultRows(page)
    const firstUnranked = rows.find(
      (r): r is Extract<ResultRow, { kind: 'unranked' }> => r.kind === 'unranked',
    )
    expect(firstUnranked).toBeDefined()
    const targetName = firstUnranked!.fullName

    const listUrlBeforeDetail = page.url()

    await page.getByRole('link', { name: new RegExp(targetName.replace('/', '\\/')) }).click()
    await expect(page).toHaveURL(/\/ja\/repos\/[^/]+\/[^/]+(\?|$)/)

    await page.getByRole('link', { name: '一覧へ戻る' }).click()

    await expect(page).toHaveURL(listUrlBeforeDetail)
    await expect(page.getByRole('searchbox', { name: '検索キーワード' })).toHaveValue(keyword)
    await expect(page.getByText('2 ページ目', { exact: true })).toBeVisible()
    await expect(
      page.getByRole('navigation', { name: '並び順' }).getByRole('link', { name: 'Gem Index 順' }),
    ).toHaveAttribute('aria-current', 'true')
  })

  await test.step('a11y: Gem Index 順の一覧・区切り見出しに serious/critical の違反がない', async () => {
    const results = await createAxeBuilder(page).analyze()
    const violations = seriousOrCritical(results.violations)
    expect(violations, JSON.stringify(violations, null, 2)).toEqual([])
  })
})
