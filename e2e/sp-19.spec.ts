import { expect, test, type Locator, type Page } from '@playwright/test'

import ja from '../messages/ja.json'
import en from '../messages/en.json'
import { SEARCH_PARAM_KEYS } from '../src/ui/url/search-params'
import { searchFor } from './helpers'

/**
 * SP-19: 検索語を引き継いで Gem だけを一覧できる（`US-34` / `GR-4` / `D-37`）。
 * `docs/02_requirements/user-story-map.md` §5.3 `SP-19` の操作レビュー手順をそのまま写す
 * （`sprint-development-rules.md` `SD-2`）。対応 `AC`: なし（上乗せ要件 `GR-4`）。
 *
 * 🔴 **ネットワークは踏まない**（`NFR-24`）。検索（GitHub API）は `e2e/stub/server.mjs` の
 * スタブへ向き、Gem 一覧は `public/data/gem-index/`（`D-38` のレジストリ別シャード）を
 * アプリ側がファイルシステムから読む。
 *
 * 🔵 **検索語は実データから選んでいる**（下記 `HIT_QUERY` / `MISS_QUERY` の JSDoc 参照）。
 * スタブが返す架空リポジトリ（`octostub/*`）は候補プールに 1 件も載らないため、
 * Gem 一覧側は「実在プールに当たる語」で叩かないと 1 件も出ない。
 */

/**
 * 🔴 **サーバー起動後の最初の照会だけ待ち時間が長い**（既定の 5 秒では足りない）。
 * `StaticGemIndex` は候補プールのレジストリ別シャード（計 3.5MB 弱・`D-38`）を最初の照会で
 * 読み込み、以降は isolate 内メモリキャッシュに載せる（`e2e/sp-18.spec.ts` と同じ理由・同じ値）。
 */
const FIRST_RESULT_TIMEOUT_MS = 30_000

/**
 * ヒットする検索語。`public/data/gem-index/` の全シャードを走査して選んだ
 * （`repositoryFullName` / `packageName` を `tokenizeIdentifier` と同じ規則で分割し、
 * `kafka` を含むユニークリポジトリが **33 件** あることを実測。1 ページ 20 件なので
 * 2 ページ目が 13 件になり、ページングと「戻ってもページが保たれる」を同時に検証できる）。
 *
 * 🔵 件数そのものはプール再生成で変わるため **テストでは件数を決め打ちしない**。
 * 「1 ページ目が満杯（`PER_PAGE` 件）」「2 ページ目に 1 件以上ある」という関係だけを見る。
 */
const HIT_QUERY = 'kafka'

/**
 * 0 件になる検索語。実データの全トークン集合に存在しないことを確認済み（同じ走査で 0 件）。
 * 実在しそうな綴りを避けるため、プロジェクト名を混ぜた無意味語にしている。
 */
const MISS_QUERY = 'zzgemhunterzz'

/** Gem 一覧の 1 ページあたり表示件数（`app/[locale]/gems/page.tsx` が `DEFAULT_PER_PAGE` 固定）。 */
const PER_PAGE = 20

/** Gem 一覧（ページ内で唯一の list ロール。ヘッダー・ページネーションは `nav`）。 */
function gemList(page: Page): Locator {
  return page.getByRole('list')
}

/** Gem 一覧のアイテムを表示順のまま取り出す。 */
function gemItems(page: Page): Locator {
  return gemList(page).locator(':scope > li')
}

/**
 * 表示順のまま Gem Index の **生値** を読み出す。可視テキスト（小数 1 桁へ丸め・ロケール桁区切り）
 * をパースすると表記に依存して壊れるため、`gem-list.tsx` が出す `data-gem-index` を読む。
 */
async function readGemIndexes(page: Page): Promise<number[]> {
  const values = await gemItems(page).evaluateAll((nodes) =>
    nodes.map((node) => (node as HTMLElement).dataset.gemIndex ?? ''),
  )
  return values.map((value) => {
    const parsed = Number(value)
    expect(Number.isFinite(parsed), `data-gem-index が数値でない: ${JSON.stringify(value)}`).toBe(
      true,
    )
    return parsed
  })
}

/** 表示順のままリポジトリ名（`owner/repo`）を読み出す。 */
function readRepositoryFullNames(page: Page): Promise<string[]> {
  return gemItems(page).evaluateAll((nodes) =>
    nodes.map((node) => (node as HTMLElement).dataset.repositoryFullName ?? ''),
  )
}

/**
 * 手順 3「Gem 一覧が **Gem Index 順**（上にあるものほど過小評価度が高い）で出る」の検証。
 * 値が小さいほど過小評価度が高いので、**昇順（先頭の値 ≦ 次の値）** であることを見る。
 */
function expectAscending(values: readonly number[]): void {
  expect(values.length).toBeGreaterThan(0)
  for (let i = 1; i < values.length; i++) {
    expect(
      values[i - 1],
      `Gem Index が昇順でない: index ${i - 1}=${values[i - 1]} > index ${i}=${values[i]}`,
    ).toBeLessThanOrEqual(values[i])
  }
}

test('SP-19: 検索 → Gem 一覧 → 詳細 → 戻る（ja・操作レビュー手順 1〜4 / 6）', async ({ page }) => {
  await test.step('1. キーワード検索する', async () => {
    await page.goto('/ja')
    await searchFor(page, HIT_QUERY)
    // 検索結果一覧が出るまで待つ（初回はシャード読み込みのぶんだけ遅い）。
    await expect(page.getByRole('heading', { name: ja.home.resultsHeading })).toBeVisible({
      timeout: FIRST_RESULT_TIMEOUT_MS,
    })
  })

  await test.step('2. 検索結果の上部にある「この検索語の Gem を見る」導線を押す', async () => {
    const link = page.getByRole('link', { name: ja.home.gemListLink.label })
    await expect(link).toBeVisible()

    // 🔴 導線は結果一覧より **前（上部）** にある（手順 2 の逐語）。DOM 順で検証する。
    const linkIsBeforeList = await page.evaluate(
      ({ label }) => {
        const anchor = [...document.querySelectorAll('a')].find(
          (a) => a.textContent?.trim() === label,
        )
        const list = document.querySelector('main ul, main ol')
        if (!anchor || !list) return null
        // Node.DOCUMENT_POSITION_FOLLOWING = 4（anchor から見て list が後ろにある）
        return (anchor.compareDocumentPosition(list) & 4) !== 0
      },
      { label: ja.home.gemListLink.label },
    )
    expect(linkIsBeforeList, '導線が検索結果一覧より前に無い').toBe(true)

    await link.click()
    await expect(page).toHaveURL(
      new RegExp(`/ja/gems\\?${SEARCH_PARAM_KEYS.keyword}=${HIT_QUERY}$`),
    )
  })

  let firstPageIndexes: number[] = []

  await test.step('3. Gem 一覧が Gem Index 順（昇順 = 上ほど過小評価度が高い）で出る', async () => {
    await expect(page.getByRole('heading', { level: 2 })).toContainText(HIT_QUERY, {
      timeout: FIRST_RESULT_TIMEOUT_MS,
    })
    await expect(gemItems(page)).toHaveCount(PER_PAGE)

    firstPageIndexes = await readGemIndexes(page)
    expectAscending(firstPageIndexes)
  })

  await test.step('6. 出典表示（Ecosyste.ms / CC BY-SA 4.0）が読める（GR-6 / D-29）', async () => {
    // 帰属表示は `GemList` 末尾の 1 段落。出典名とライセンス名がリンクとして読める。
    await expect(page.getByRole('link', { name: 'Ecosyste.ms' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'CC BY-SA 4.0' })).toBeVisible()
  })

  await test.step('3-2. 2 ページ目へ進んでも Gem Index 順が破綻していない', async () => {
    await page
      .getByRole('navigation', { name: ja.home.paginationLabel })
      .getByRole('link', { name: ja.home.pageNext })
      .click()

    await expect(page).toHaveURL(new RegExp(`[?&]${SEARCH_PARAM_KEYS.page}=2(&|$)`))
    const secondPageIndexes = await readGemIndexes(page)
    expectAscending(secondPageIndexes)
    // ページを跨いでも大小関係が保たれている（ページ内だけの局所ソートになっていない）。
    expect(firstPageIndexes[firstPageIndexes.length - 1]).toBeLessThanOrEqual(secondPageIndexes[0])
  })

  await test.step('4. 一覧から詳細へ入り、戻ると一覧の状態（検索語・ページ）が保たれている', async () => {
    const listUrl = page.url()
    const [firstFullName] = await readRepositoryFullNames(page)
    expect(firstFullName).not.toBe('')

    await page.getByRole('link', { name: firstFullName, exact: true }).click()

    // 詳細 URL に一覧への復帰情報（出所マーカー・検索語・ページ）が載っている。
    await expect(page).toHaveURL(new RegExp('/ja/repos/'))
    const detailUrl = new URL(page.url())
    expect(detailUrl.searchParams.get('from')).toBe('gems')
    expect(detailUrl.searchParams.get(SEARCH_PARAM_KEYS.keyword)).toBe(HIT_QUERY)
    expect(detailUrl.searchParams.get(SEARCH_PARAM_KEYS.page)).toBe('2')

    // 🔵 「戻る」はブラウザバック。詳細画面の「一覧へ戻る」は **検索結果一覧**（`/{locale}`）
    //    への導線であり、Gem 一覧へは戻らない（`from=gems` を解釈する詳細画面側の対応は
    //    本スプリントのスコープ外・返り値で申し送り済み）。
    await page.goBack()

    // 検索語（`q`）とページ（`page=2`）が保たれたまま同じ一覧に戻っている。
    await expect(page).toHaveURL(listUrl)
    await expect(page.getByRole('heading', { level: 2 })).toContainText(HIT_QUERY)
    expect(await readRepositoryFullNames(page)).toContain(firstFullName)
    expectAscending(await readGemIndexes(page))
  })
})

test('SP-19: ヒットしない検索語では母集団を明示した空状態が出る（ja・操作レビュー手順 5）', async ({
  page,
}) => {
  await page.goto(`/ja/gems?${SEARCH_PARAM_KEYS.keyword}=${MISS_QUERY}`)

  await test.step('母集団（12 レジストリ・被依存数上位）を明示した空状態が読める', async () => {
    await expect(page.getByText(ja.gems.empty, { exact: true })).toBeVisible({
      timeout: FIRST_RESULT_TIMEOUT_MS,
    })
    await expect(gemList(page)).toHaveCount(0)
  })

  await test.step('緩和注記は出ない（1 語も単独ヒットしないので緩和は起きていない）', async () => {
    // `relaxedNotice` は `{token}` を含むテンプレート。プレースホルダを外した前後の断片が
    // 画面に出ていないことで「緩和注記が描画されていない」を判定する。
    const [beforeToken] = ja.gems.relaxedNotice.split('{token}')
    await expect(page.getByText(beforeToken.trim(), { exact: false })).toHaveCount(0)
  })

  await test.step('0 件でも出典表示は読める（GR-6 / D-29）', async () => {
    await expect(page.getByRole('link', { name: 'Ecosyste.ms' })).toBeVisible()
  })

  await test.step('検索へ戻る導線がある', async () => {
    await page.getByRole('link', { name: ja.gems.backToSearch }).click()
    await expect(page).toHaveURL(
      new RegExp(`/ja\\?${SEARCH_PARAM_KEYS.keyword}=${MISS_QUERY}$`),
    )
  })
})

test('SP-19: 検索語なしで開くと 500 にせず、何が要るかと戻り先を示す（ja）', async ({ page }) => {
  await page.goto('/ja/gems')

  await expect(page.getByText(ja.gems.queryRequired, { exact: true })).toBeVisible()
  await expect(gemList(page)).toHaveCount(0)

  await page.getByRole('link', { name: ja.gems.backToSearch }).click()
  await expect(page).toHaveURL(/\/ja$/)
})

test('SP-19: 英語 UI でも同じ一覧が英語の文言で読める（en・E-4）', async ({ page }) => {
  await page.goto(`/en/gems?${SEARCH_PARAM_KEYS.keyword}=${HIT_QUERY}`)

  await expect(page.getByRole('heading', { level: 2 })).toContainText(HIT_QUERY, {
    timeout: FIRST_RESULT_TIMEOUT_MS,
  })
  await expect(gemItems(page)).toHaveCount(PER_PAGE)
  expectAscending(await readGemIndexes(page))

  // 英語 UI に日本語の文言が混ざっていないこと（文言の取り違えの検出）。
  await expect(page.getByRole('link', { name: en.gems.backToSearch })).toBeVisible()
  await expect(page.getByText(ja.gems.backToSearch, { exact: true })).toHaveCount(0)
})
