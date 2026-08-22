import { readFileSync } from 'node:fs'
import path from 'node:path'

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

/**
 * 日本語だけの検索語。`tokenizeQuery`（`D-37`）は ASCII 英数字以外を区切りとして扱うため
 * トークンが 1 つも取れない。🔴 **ここで全件（実測 62,483 件）が出る回帰を止めるための語**
 * （「『画像処理』の Gem」と名乗って候補プール全件を並べるのは端的な誤表示）。
 */
const UNMATCHABLE_QUERY = '画像処理'

/**
 * 全語 AND では 0 件だが 1 語なら当たる検索語（`D-37` の緩和経路）。実データで
 * `kafka` 33 件 / `zzgemhunterzz` 0 件・AND 0 件を実測しているため、必ず `kafka` へ緩和される。
 */
const RELAXED_QUERY = `${HIT_QUERY} ${MISS_QUERY}`

/**
 * 1,000 件（GitHub 検索 API の到達上限）を超えるヒット数になる検索語。実データを実装と同じ
 * `tokenizeIdentifier` で数え直すと `core` は 1,631 件で、旧実装（`tryPageNumber` の 50 ページ
 * 上限）では 631 件が到達不能だった（F-02）。
 */
const OVER_API_LIMIT_QUERY = 'core'

/** スタブ（`e2e/stub/server.mjs`）が検索結果 0 件を返すキーワード。 */
const ZERO_HITS_QUERY = 'zero-hits'

/** Gem 一覧の 1 ページあたり表示件数（`app/[locale]/gems/page.tsx` が `DEFAULT_PER_PAGE` 固定）。 */
const PER_PAGE = 20

/**
 * ページ送り後にフォーカスを受け取る見出しの `id`（正本は `src/ui/gem-list.tsx` の
 * `GEM_LIST_HEADING_ID`）。E2E は Node 側で動くため、`next/link` を持つコンポーネント
 * モジュールを読み込まずに済むよう値だけを写す。
 */
const GEM_LIST_HEADING_ID = 'gems-heading'

/**
 * 🔴 出典表示の期待値は **配信データそのもの**（`public/data/gem-index/index.json`）から作る。
 * ハードコードすると `parseMeta` を `return FALLBACK_META` に退化させても（＝配信データの帰属
 * 情報を一切読まなくても）E2E が緑のままになる（F-37）。
 */
const poolMeta = JSON.parse(
  readFileSync(path.join(process.cwd(), 'public/data/gem-index/index.json'), 'utf8'),
).meta as {
  source: string
  sourceUrl: string
  license: string
  sourceLicenseUrl: string
}

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

/**
 * 総件数表示（`gems.totalCount` = `{count} 件`）から件数を読む。ロケール桁区切りを外して数値化する。
 */
async function readTotalCount(page: Page): Promise<number> {
  const text = await page
    .getByText(/^[\d,]+ 件$/)
    .first()
    .innerText()
  const parsed = Number(text.replace(/[^\d]/g, ''))
  expect(Number.isFinite(parsed), `総件数を読めなかった: ${JSON.stringify(text)}`).toBe(true)
  return parsed
}

/**
 * 出典表示（`D-29` / `GR-6`）が **配信データの帰属情報** で描画されていることを見る（F-37）。
 * リンクのテキストだけでなく `href` も配信データと突き合わせる。
 */
async function expectAttributionFromPoolData(page: Page): Promise<void> {
  const sourceLink = page.getByRole('link', { name: poolMeta.source })
  await expect(sourceLink).toBeVisible()
  await expect(sourceLink).toHaveAttribute('href', poolMeta.sourceUrl)

  const licenseLink = page.getByRole('link', { name: poolMeta.license })
  await expect(licenseLink).toBeVisible()
  await expect(licenseLink).toHaveAttribute('href', poolMeta.sourceLicenseUrl)
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

  await test.step('2. 検索結果の上部にある「この検索語の Gem 候補を一覧で見る」導線を押す', async () => {
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

  await test.step('4. 一覧から詳細へ入り、画面の「戻る」で一覧の状態（検索語・ページ）が保たれている', async () => {
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

    // 🔴 主経路は **画面上の戻るリンク**（`SD-1`: レビュワーはリンクを開くだけで完走できる）。
    //    Gem 一覧から来たときはラベルも「Gem 一覧へ戻る」に変わる（検索結果一覧と区別できる）。
    await page.getByRole('link', { name: ja.detail.backToGemList }).click()

    await expect(page).toHaveURL(listUrl)
    await expect(page.getByRole('heading', { level: 2 })).toContainText(HIT_QUERY)
    expect(await readRepositoryFullNames(page)).toContain(firstFullName)
    expectAscending(await readGemIndexes(page))
  })

  await test.step('4-2. ブラウザバックでも同じ一覧・同じページに戻る（副経路の回帰）', async () => {
    const listUrl = page.url()
    const [firstFullName] = await readRepositoryFullNames(page)

    await page.getByRole('link', { name: firstFullName, exact: true }).click()
    await expect(page).toHaveURL(new RegExp('/ja/repos/'))

    await page.goBack()

    await expect(page).toHaveURL(listUrl)
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
    await expect(page).toHaveURL(new RegExp(`/ja\\?${SEARCH_PARAM_KEYS.keyword}=${MISS_QUERY}$`))
  })
})

test('SP-19: 日本語だけの検索語では全件を出さず、照合できなかったことを案内する（ja・D-37）', async ({
  page,
}) => {
  await page.goto(`/ja/gems?${SEARCH_PARAM_KEYS.keyword}=${encodeURIComponent(UNMATCHABLE_QUERY)}`)

  await test.step('照合規則と次の行動を示す案内が読める（母集団の説明とは別の文言）', async () => {
    await expect(page.getByText(ja.gems.unmatchableQuery, { exact: true })).toBeVisible({
      timeout: FIRST_RESULT_TIMEOUT_MS,
    })
    // 候補プールに載っていない場合の説明（`gems.empty`）とすり替わっていない。
    await expect(page.getByText(ja.gems.empty, { exact: true })).toHaveCount(0)
  })

  await test.step('🔴 一覧項目は 0 件（候補プール全件を「この検索語の Gem」として出さない）', async () => {
    await expect(gemList(page)).toHaveCount(0)
    await expect(gemItems(page)).toHaveCount(0)
    // 総件数（`gems.totalCount` = `{count} 件`）も出ない＝全件が母数になっていない。
    await expect(page.getByText(/^[\d,]+ 件$/)).toHaveCount(0)
    // ページネーションも出ない（全件のページ送りが生えない）。
    await expect(page.getByRole('navigation', { name: ja.home.paginationLabel })).toHaveCount(0)
  })

  await test.step('検索へ戻る導線がある', async () => {
    await page.getByRole('link', { name: ja.gems.backToSearch }).click()
    await expect(page).toHaveURL(
      new RegExp(`/ja\\?${SEARCH_PARAM_KEYS.keyword}=${encodeURIComponent(UNMATCHABLE_QUERY)}$`),
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

test('SP-19: from が無い / 未知の値のときは従来どおり検索結果一覧へ戻る（既定の挙動の回帰）', async ({
  page,
}) => {
  const detailPath = '/ja/repos/octostub/octo-widgets'
  const query = `${SEARCH_PARAM_KEYS.keyword}=octo&${SEARCH_PARAM_KEYS.page}=2`

  await test.step('from が無い詳細ページ: ラベルは「一覧へ戻る」で、行き先は検索結果一覧', async () => {
    await page.goto(`${detailPath}?${query}`)
    await expect(page.getByRole('link', { name: ja.detail.backToGemList })).toHaveCount(0)
    await page.getByRole('link', { name: ja.detail.backLink }).first().click()
    await expect(page).toHaveURL(new RegExp(`/ja\\?.*${SEARCH_PARAM_KEYS.page}=2`))
  })

  await test.step('from が未知の値の詳細ページ: 許可リスト外なので既定（検索結果一覧）へ倒れる', async () => {
    await page.goto(`${detailPath}?${query}&from=evil`)
    await expect(page.getByRole('link', { name: ja.detail.backToGemList })).toHaveCount(0)
    await page.getByRole('link', { name: ja.detail.backLink }).first().click()
    await expect(page).toHaveURL(new RegExp(`/ja\\?.*${SEARCH_PARAM_KEYS.page}=2`))
  })
})
