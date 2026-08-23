import { randomBytes } from 'node:crypto'
import { expect, test } from '@playwright/test'
import type { Result } from 'axe-core'
import { createAxeBuilder } from './axe'
import { searchFor } from './helpers'
import { SEARCH_PARAM_KEYS } from '../src/ui/url/search-params'

/**
 * SP-7: 大量の結果を捌ける（ページネーション・並び替え・表示件数）。
 * `docs/02_requirements/user-story-map.md` §5.3 `SP-7` の操作レビュー手順をそのまま写す
 * （`sprint-development-rules-detail.md` §2.6）。対応: `US-9` / `AR-2` / `AR-3` / `AC-7`。
 *
 * 🔴 実装手段レベルの判断（SD-3 対象外・仮定を 1 行記録）: 既存スタブ（`e2e/stub/server.mjs`）は
 * `sort` / `per_page` を無視し、キーワードに応じて固定 3 件 + 2 件（フィクスチャ計 5 件）しか
 * 返さない。ページネーション・並び替え・表示件数変更を「実際に見た目が変わる」形で検証するには
 * 20 件（既定表示件数）を超えるデータセットが要る。既存 5 件フィクスチャを増やすと `sp-1`〜`sp-3`
 * `sp-5` `a11y` が前提にしている固定 3 件/2 件の応答が崩れるため、専用キーワード
 * （`many-hits`）でのみ有効になる 60 件データセットをスタブへ追加し、`page` / `per_page` / `sort`
 * を実際に反映するようにした（既存キーワードの挙動・既存 E2E は無変更）。
 *
 * 60 件・`stargazers_count = 連番 * 7`（挿入順とは逆順の星順）にしたのは、並び替えの前後で
 * 「一覧の先頭要素が変わる」ことを目視ではなくアサーションで検知できるようにするため。
 */

/** 他ファイル・retry 試行との衝突を避けるため、実行のたびに一意なキーワードを生成する（sp-5 と同じ方針）。 */
function uniqueManyHitsKeyword(): string {
  return `many-hits-${randomBytes(4).toString('hex')}`
}

function seriousOrCritical(violations: Result[]): Result[] {
  return violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
}

test('SP-7: 並び替え・表示件数・ページネーションを操作しても、詳細往復で検索条件が保たれる', async ({
  page,
}) => {
  const keyword = uniqueManyHitsKeyword()

  await test.step('前提: 60 件ヒットする検索を実行しておく（既定: 1 ページ目 / 関連度順 / 20 件表示）', async () => {
    await page.goto('/ja')
    await searchFor(page, keyword)
    await expect(page.getByRole('list').first().locator(':scope > li')).toHaveCount(20)
    // 関連度（既定 = 挿入順）: 先頭は挿入順で最初の要素（many-01・star 最小）
    await expect(page.getByRole('link', { name: 'octostub/many-01' })).toBeVisible()
    await expect(page.getByText('60 件中 20 件を表示', { exact: true })).toBeVisible()
  })

  await test.step('1. 2 ページ目へ移動する → URL に現在ページが乗る', async () => {
    await page
      .getByRole('navigation', { name: '検索結果のページ' })
      .getByRole('link', { name: '次のページへ' })
      .click()

    await expect(page).toHaveURL(new RegExp(`[?&]${SEARCH_PARAM_KEYS.page}=2(&|$)`))
    await expect(page.getByText('2 ページ目', { exact: true })).toBeVisible()
    // 2 ページ目（21〜40 件目）の先頭要素
    await expect(page.getByRole('link', { name: 'octostub/many-21' })).toBeVisible()
  })

  await test.step('2. 並び順を star 順へ変える → 並びが変わり、URL に反映される', async () => {
    await page
      .getByRole('navigation', { name: '並び順' })
      .getByRole('link', { name: 'star 数' })
      .click()

    await expect(page).toHaveURL(new RegExp(`[?&]${SEARCH_PARAM_KEYS.sort}=stars(&|$)`))
    // 並び順切替は 1 ページ目へ戻す実装のため page パラメータは既定値（省略）に戻る
    await expect(page).not.toHaveURL(new RegExp(`[?&]${SEARCH_PARAM_KEYS.page}=`))

    // 並びが実際に変わったことの検証: 先頭要素が「star 数最大（many-60）」に変わる
    // （前提ステップの「関連度順で先頭は many-01」と異なる = 単なる URL 変化ではなく実際に並び替わった）
    const items = page.getByRole('list').first().locator(':scope > li')
    await expect(items).toHaveCount(20)
    await expect(items.first().getByRole('link')).toHaveText('octostub/many-60')

    await expect(
      page.getByRole('navigation', { name: '並び順' }).getByRole('link', { name: 'star 数' }),
    ).toHaveAttribute('aria-current', 'true')

    // star 順で 20 件目までには入らない要素（many-15・star 順位 46 位）はまだ見えない
    await expect(page.getByRole('link', { name: 'octostub/many-15' })).toHaveCount(0)
  })

  await test.step('3. 表示件数を 50 に変える → 件数が変わる', async () => {
    await page
      .getByRole('navigation', { name: '表示件数' })
      .getByRole('link', { name: '50 件' })
      .click()

    await expect(page).toHaveURL(new RegExp(`[?&]${SEARCH_PARAM_KEYS.perPage}=50(&|$)`))
    await expect(page).not.toHaveURL(new RegExp(`[?&]${SEARCH_PARAM_KEYS.page}=`))

    // 件数が実際に変わったことの検証: 一覧の項目数が 20 → 50 に増える
    const items = page.getByRole('list').first().locator(':scope > li')
    await expect(items).toHaveCount(50)
    await expect(page.getByText('60 件中 50 件を表示', { exact: true })).toBeVisible()
    // 20 件のときは見えなかった要素（many-15）が 50 件表示では見える
    await expect(page.getByRole('link', { name: 'octostub/many-15' })).toBeVisible()

    await expect(
      page.getByRole('navigation', { name: '表示件数' }).getByRole('link', { name: '50 件' }),
    ).toHaveAttribute('aria-current', 'true')
  })

  await test.step('4. 詳細へ入って戻る → キーワード・ページ・ソート・件数がすべて元のまま', async () => {
    // ページネーションは現在の並び順・表示件数を保ったまま次ページへ進む
    // （keyword=many-hits-xxx / sort=stars / per_page=50 / page=2 という非既定の組み合わせを作る）
    await page
      .getByRole('navigation', { name: '検索結果のページ' })
      .getByRole('link', { name: '次のページへ' })
      .click()

    await expect(page).toHaveURL(new RegExp(`[?&]${SEARCH_PARAM_KEYS.page}=2(&|$)`))
    await expect(page).toHaveURL(new RegExp(`[?&]${SEARCH_PARAM_KEYS.sort}=stars(&|$)`))
    await expect(page).toHaveURL(new RegExp(`[?&]${SEARCH_PARAM_KEYS.perPage}=50(&|$)`))
    // 60 件を 50 件/ページで割った 2 ページ目は残り 10 件
    await expect(page.getByRole('list').first().locator(':scope > li')).toHaveCount(10)
    await expect(page.getByRole('link', { name: 'octostub/many-10' })).toBeVisible()

    const listUrlBeforeDetail = page.url()

    await page.getByRole('link', { name: 'octostub/many-10' }).click()
    // 一覧からの遷移は検索条件（keyword/page/sort/perPage）をクエリとして継ぎ足すため、
    // パス部分の一致だけを見る（クエリの中身は「戻る」後の検証で確認する）
    await expect(page).toHaveURL(/\/ja\/repos\/octostub\/many-10(\?|$)/)
    await expect(page.getByRole('heading', { name: 'octostub/many-10' })).toBeVisible()

    await page.getByRole('link', { name: '一覧へ戻る' }).click()

    // URL（keyword・page・sort・perPage の全て）が詳細へ入る前と完全に一致する
    await expect(page).toHaveURL(listUrlBeforeDetail)
    await expect(page.getByRole('searchbox', { name: '検索キーワード' })).toHaveValue(keyword)
    await expect(page.getByText('2 ページ目', { exact: true })).toBeVisible()
    await expect(
      page.getByRole('navigation', { name: '並び順' }).getByRole('link', { name: 'star 数' }),
    ).toHaveAttribute('aria-current', 'true')
    await expect(
      page.getByRole('navigation', { name: '表示件数' }).getByRole('link', { name: '50 件' }),
    ).toHaveAttribute('aria-current', 'true')
    await expect(page.getByRole('link', { name: 'octostub/many-10' })).toBeVisible()
  })

  await test.step('5. a11y: ソート・件数切替・ページネーションに serious/critical の違反がない', async () => {
    const results = await createAxeBuilder(page).analyze()
    const violations = seriousOrCritical(results.violations)
    expect(violations, JSON.stringify(violations, null, 2)).toEqual([])
  })
})
