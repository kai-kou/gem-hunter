import { readFileSync } from 'node:fs'
import path from 'node:path'

import { expect, test, type Locator, type Page } from '@playwright/test'

import ja from '../messages/ja.json'
import en from '../messages/en.json'
import { SEARCH_PARAM_KEYS } from '../src/ui/url/search-params'
import { searchFor, uniqueGemBadgeKeyword } from './helpers'

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
 * ハードコードすると、配信データの帰属情報が変わったときに E2E が古い期待値のまま緑になる（F-37）。
 *
 * ⚠️ **これだけでは `parseMeta` の退化（`return FALLBACK_META`）は検出できない**: 現時点の実データと
 * `FALLBACK_META` は描画されない `generatedAt` 以外が一致しているため、両者を画面越しに区別できない。
 * その回帰点はインフラ層のユニットテスト（`generatedAt` の差で落ちる）が押さえており、E2E の役割は
 * 「出典表示が読める」ことの確認に留める（検証のために本番の表示項目を増やさない・親裁定 2026-08-22）。
 */
const poolMeta = JSON.parse(
  readFileSync(path.join(process.cwd(), 'public/data/gem-index/index.json'), 'utf8'),
).meta as {
  source: string
  sourceUrl: string
  license: string
  sourceLicenseUrl: string
}

/**
 * 1x1 の透明 PNG（base64）。`AR-11` の avatar が実際に `https://github.com/{owner}.png` へ
 * リクエストする分を `page.route()` でスタブし、このスペック冒頭の「ネットワークは踏まない」
 * 方針（`NFR-24`）との矛盾を解消する。
 */
const STUB_AVATAR_PNG_BASE64 =
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='

test.beforeEach(async ({ page }) => {
  // Gem 一覧カードの avatar（`src/ui/gem-list.tsx`）は `https://github.com/{owner}.png` を直接
  // 参照する（`AR-11` の詳細: 候補プールのシャードに avatar_url 相当の列が無いため）。実ネットワークを
  // 踏ませず、常に同じ 1x1 PNG を返す。
  await page.route('https://github.com/**.png**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'image/png',
      body: Buffer.from(STUB_AVATAR_PNG_BASE64, 'base64'),
    }),
  )
})

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

  await test.step('11. 各カードにオーナーの avatar が表示されている（AR-11）', async () => {
    const cards = page.locator('li[data-repository-full-name]')
    const cardCount = await cards.count()
    expect(cardCount).toBeGreaterThan(0)
    for (let i = 0; i < cardCount; i++) {
      // 🔴 カード内の `img` を素数で数えない（将来カードへ別の画像が増えても実装が正しければ
      // 落ちないよう、avatar だけを一意に特定できるセレクタで見る）。
      const avatar = cards.nth(i).locator('img[src*="github.com"]')
      await expect(avatar).toHaveCount(1)
      await expect(avatar).toHaveAttribute('alt', '')
    }
  })

  await test.step('6. 出典表示（配信データの帰属情報）が読める（GR-6 / D-29）', async () => {
    // 帰属表示は `GemList` 末尾の 1 段落。出典名とライセンス名がリンクとして読める。
    await expectAttributionFromPoolData(page)
  })

  await test.step('3-2. 2 ページ目へ進んでも Gem Index 順が破綻していない', async () => {
    await page
      .getByRole('navigation', { name: ja.home.paginationLabel })
      .getByRole('link', { name: ja.home.pageNext })
      .click()

    await expect(page).toHaveURL(new RegExp(`[?&]${SEARCH_PARAM_KEYS.page}=2(&|$)`))
    /**
     * 🔴 ページ送りの完了後、フォーカスが一覧見出しへ移る（`ui-ux-guidelines.md` §7.1 / F-04）。
     * `<title>` は固定・総件数の文言もページ間で同一なので、これが無いと「一覧が差し替わった」
     * ことがスクリーンリーダー利用者に一切伝わらない。
     */
    await expect(page.locator(`#${GEM_LIST_HEADING_ID}`)).toBeFocused()

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

  /**
   * 🔴 F-33: 詳細ページで **言語を切り替えても** 出所マーカー（`from=gems`）・検索語・ページを
   * 落とさない。落とすと切替後の戻りリンクが「Gem 一覧へ戻る」から検索結果一覧へすり替わり、
   * 操作レビュー手順 4 がそこだけ破れる（`currentPath` の組み立てを回帰させないための固定）。
   */
  await test.step('4-3. 詳細ページで言語を切り替えても Gem 一覧の該当ページへ戻れる', async () => {
    const namesBefore = await readRepositoryFullNames(page)
    const [firstFullName] = namesBefore
    await page.getByRole('link', { name: firstFullName, exact: true }).click()
    await expect(page).toHaveURL(new RegExp('/ja/repos/'))

    await page
      .getByRole('navigation', { name: ja.common.localeSwitcher.navLabel })
      .getByRole('link', { name: en.common.localeSwitcher.localeNames.en })
      .click()

    await expect(page).toHaveURL(new RegExp('/en/repos/'))
    const switchedUrl = new URL(page.url())
    expect(switchedUrl.searchParams.get('from')).toBe('gems')
    expect(switchedUrl.searchParams.get(SEARCH_PARAM_KEYS.keyword)).toBe(HIT_QUERY)
    expect(switchedUrl.searchParams.get(SEARCH_PARAM_KEYS.page)).toBe('2')

    // 英語 UI の戻りリンク（ラベルも英語）から、Gem 一覧の **同じページ** へ帰る。
    await page.getByRole('link', { name: en.detail.backToGemList }).click()
    await expect(page).toHaveURL(
      new RegExp(
        `/en/gems\\?${SEARCH_PARAM_KEYS.keyword}=${HIT_QUERY}&${SEARCH_PARAM_KEYS.page}=2$`,
      ),
    )
    // 件数を決め打ちせず「同じページの中身が戻ってきた」ことで判定する（2 ページ目は端数）。
    expect(await readRepositoryFullNames(page)).toEqual(namesBefore)
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
    await expectAttributionFromPoolData(page)
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

/**
 * 🔴 F-36: 緩和経路（`D-37` の中核挙動）とラベル対応表を **画面越しに** 通す。
 * ページが `GemList` へ渡す 10 キーのラベル対応表は手写しなので、行内ラベルを検証していないと
 * `registryLabel` と `gemIndexLabel` の取り違えのような配線ミスが全テスト緑のまま通る。
 */
test('SP-19: 全語 AND が 0 件なら 1 語へ緩め、注記と行内ラベルが読める（ja・D-37）', async ({
  page,
}) => {
  await page.goto(`/ja/gems?${SEARCH_PARAM_KEYS.keyword}=${encodeURIComponent(RELAXED_QUERY)}`)

  await test.step('緩和注記に、実際に使った 1 語（kafka）が出る', async () => {
    await expect(
      page.getByText(ja.gems.relaxedNotice.replace('{token}', HIT_QUERY), { exact: true }),
    ).toBeVisible({ timeout: FIRST_RESULT_TIMEOUT_MS })
  })

  await test.step('緩和後の一覧が Gem Index 順で出る（0 件で終わらせない）', async () => {
    await expect(gemItems(page)).toHaveCount(PER_PAGE)
    expectAscending(await readGemIndexes(page))
    // 「候補プールに載っていない」の説明とすり替わっていない。
    await expect(page.getByText(ja.gems.empty, { exact: true })).toHaveCount(0)
  })

  await test.step('行内に レジストリ / Gem Index のラベルが正しい値と組で出る', async () => {
    const rowText = await gemItems(page).first().innerText()
    // レジストリ名は英数字の識別子（`npmjs.org` 等）、Gem Index は符号つきの数値。
    // ラベルを取り違えると（`registryLabel` に `gemIndexLabel` を渡す等）この組が崩れる。
    expect(rowText).toMatch(new RegExp(`${ja.gems.registryLabel}\\s+[A-Za-z][^\\s]*`))
    expect(rowText).toMatch(new RegExp(`${ja.gems.gemIndexLabel}\\s+-?[\\d,]+\\.\\d`))
  })
})

/**
 * 🔴 F-02: 候補プールは GitHub 検索 API の 1,000 件上限とは無関係なので、50 ページで
 * 打ち切らない。範囲外のページ指定は **1 ページ目ではなく最終ページ** へ丸める。
 */
test('SP-19: 1,000 件超のヒットでも 50 ページで打ち切らず、範囲外ページは最終ページへ丸まる（ja）', async ({
  page,
}) => {
  await page.goto(`/ja/gems?${SEARCH_PARAM_KEYS.keyword}=${OVER_API_LIMIT_QUERY}`)
  await expect(gemItems(page)).toHaveCount(PER_PAGE, { timeout: FIRST_RESULT_TIMEOUT_MS })

  const totalCount = await readTotalCount(page)
  const lastPage = Math.ceil(totalCount / PER_PAGE)
  const firstPageNames = await readRepositoryFullNames(page)

  await test.step('前提: この検索語は GitHub 検索 API の到達上限（1,000 件）を超える', async () => {
    expect(
      totalCount,
      `候補プールの再生成で件数が変わった可能性がある（"${OVER_API_LIMIT_QUERY}" の実測は 1,631 件）`,
    ).toBeGreaterThan(1000)
  })

  await test.step('旧上限（50 ページ）より後ろのページが実際に開ける', async () => {
    await page.goto(
      `/ja/gems?${SEARCH_PARAM_KEYS.keyword}=${OVER_API_LIMIT_QUERY}&${SEARCH_PARAM_KEYS.page}=51`,
    )
    await expect(gemItems(page)).toHaveCount(PER_PAGE)
    expect(await readRepositoryFullNames(page)).not.toEqual(firstPageNames)
    await expect(
      page.getByText(ja.home.pageCurrent.replace('{page}', '51'), { exact: true }),
    ).toBeVisible()
    // GitHub 検索 API 由来の上限注記は、この面では出さない（存在しない制約を伝えない）。
    await expect(page.getByText(ja.home.pageLimitReached, { exact: true })).toHaveCount(0)
  })

  await test.step('最終ページより後ろを直打ちしても 1 ページ目に戻らず、最終ページが出る', async () => {
    await page.goto(
      `/ja/gems?${SEARCH_PARAM_KEYS.keyword}=${OVER_API_LIMIT_QUERY}&${SEARCH_PARAM_KEYS.page}=${lastPage + 5}`,
    )
    await expect(
      page.getByText(ja.home.pageCurrent.replace('{page}', String(lastPage)), { exact: true }),
    ).toBeVisible()
    expect(await readRepositoryFullNames(page)).not.toEqual(firstPageNames)
    // 最終ページなので「次のページへ」はリンクにならない。「前のページへ」は残る（行き止まりにしない）。
    const pagination = page.getByRole('navigation', { name: ja.home.paginationLabel })
    await expect(pagination.getByRole('link', { name: ja.home.pageNext })).toHaveCount(0)
    await expect(pagination.getByRole('link', { name: ja.home.pagePrev })).toBeVisible()
  })
})

/**
 * 🔴 F-32: 「検索結果 0 件のときは Gem 導線を出さない」分岐の固定（肯定側は手順 2 が押さえている）。
 * 出してしまうと、空の検索語で `/{locale}/gems` へ飛ぶ行き止まりのリンクになる。
 */
test('SP-19: 検索結果が 0 件のときは Gem 一覧への導線を出さない（ja）', async ({ page }) => {
  await page.goto('/ja')
  await searchFor(page, ZERO_HITS_QUERY)

  await expect(page.getByText(ja.home.empty, { exact: true })).toBeVisible({
    timeout: FIRST_RESULT_TIMEOUT_MS,
  })
  await expect(page.getByRole('link', { name: ja.home.gemListLink.label })).toHaveCount(0)
})

/**
 * Issue #453（F-1）: 案3'（scoped hybrid）の中核挙動。検索結果ページで Gem バッジが付いた候補は、
 * 名前照合（`D-37` の全語 AND 単語境界一致）に一致しなくても、`GemListLink` の導線を押した先の
 * Gem 一覧に同伴して現れる。`content/discussions/gem-list-match-20260823/whiteboard.md` lead 判定
 * （issue A・案3' 採用）を固定する。`user-story-map.md` `SP-19` 操作レビュー手順 10。
 *
 * 🔴 **`e2e/sp-18.spec.ts` の `gem-badge` データセットを流用する**: キーワードは実行のたびに
 * 変わるランダム値（`gm-badge-xxxx` 相当）なので、名前照合（AND）には通常一致しない。
 * 一方バッジが付く側のカードは候補プール実在の 1 件（`GemIndexPort#lookup` が返す）で、
 * 「バッジは付くが名前は一致しない」という F-1 の症状をそのまま再現できる。
 */
test('SP-19: 検索結果でバッジが付いた候補が、名前が一致しなくても Gem 一覧に現れる（ja・scoped hybrid）', async ({
  page,
}) => {
  const keyword = uniqueGemBadgeKeyword()
  let badgedFullName = ''

  await test.step('1. キーワード検索する（プール実在 1 件にバッジが付く）', async () => {
    await page.goto('/ja')
    await searchFor(page, keyword)
    await expect(page.getByRole('list').first().locator(':scope > li')).toHaveCount(2, {
      timeout: FIRST_RESULT_TIMEOUT_MS,
    })

    const cards = page.getByRole('list').first().locator(':scope > li')
    const names: string[] = []
    const flags: boolean[] = []
    for (let i = 0; i < 2; i++) {
      names.push((await cards.nth(i).getByRole('link').first().innerText()).trim())
      flags.push((await cards.nth(i).getByText(ja.home.gemBadge.srHint, { exact: true }).count()) > 0)
    }
    expect(flags).toEqual([false, true])
    badgedFullName = names[1]
    expect(badgedFullName).not.toBe('')
  })

  await test.step('2. 「この検索語の Gem 候補を一覧で見る」導線を押す（同伴パラメータ badged を積む）', async () => {
    const link = page.getByRole('link', { name: ja.home.gemListLink.label })
    await link.click()
    await expect(page).toHaveURL(new RegExp(`/ja/gems\\?.*${SEARCH_PARAM_KEYS.keyword}=`))
    expect(page.url(), '同伴パラメータ badged が href に積まれていない').toContain('badged=')
  })

  await test.step('3. バッジが付いていた候補（名前は不一致）が一覧に現れる', async () => {
    await expect(gemList(page)).toBeVisible({ timeout: FIRST_RESULT_TIMEOUT_MS })
    expect(await readRepositoryFullNames(page)).toContain(badgedFullName)
  })

  await test.step('4. 内訳文言（全 N 件のうち M 件が一致）に総件数と一致件数が含まれる', async () => {
    // 🔴 F-3（Issue #453）: `gems.includedFromSearch` は「全 {total} 件のうち、検索語に一致
    // したのは {matchedCount} 件です。残り {count} 件は…」の加算構文へ改訂される（実装は並行
    // 作業中）。文言の完全一致ではなく、`totalCount = matchedCount + includedCount` の関係が
    // 画面上の 1 文に現れることだけを頑健に検証する（`includedCount` 自体はこの一件のみ = 1）。
    const totalCount = await readTotalCount(page)
    const matchedCount = totalCount - 1

    const notice = page.getByText(/全\s*[\d,]+\s*件のうち/).first()
    await expect(notice).toBeVisible()
    const text = await notice.innerText()
    // 画面は `Intl.NumberFormat` の桁区切り（例: `1,631`）で描画するため、比較前にカンマを除去する
    // （4 桁以上の件数で `toContain(String(totalCount))` が恒常的に落ちるのを防ぐ）。
    const normalized = text.replace(/,/g, '')
    expect(normalized, '総件数が内訳文言に含まれていない').toContain(String(totalCount))
    expect(normalized, '一致件数が内訳文言に含まれていない').toContain(String(matchedCount))
  })
})

/**
 * 直接 `/gems?q=...` を開いた場合（検索結果ページ経由でない）は同伴パラメータが無いため、
 * 名前不一致のバッジ付き候補は一覧に現れない（lead 判定が明示した残る限界・`D-36` 追記）。
 * 同じキーワードでも「検索結果から来たか直接開いたか」で結果が変わることの回帰点。
 *
 * 🔴 **空状態（`gems.empty`）を期待しない**: `gem-badge-<hex>` は `tokenizeQuery` で
 * 複数トークンに割れるため、全語 AND が 0 件でも `D-37` の緩和（最も選択的な 1 語で絞り込む）が
 * 発火しうる。緩和で何かしらの候補が出ること自体は正しい挙動なので否定しない。本テストが
 * 固定したいのは **同伴パラメータが無ければバッジ付き候補（`badgedFullName`）は一覧に含まれず、
 * `gems.includedFromSearch` 注記も出ない** ことだけ。
 */
test('SP-19: 検索結果ページを経由せず /gems を直接開くと、名前不一致のバッジ付き候補は同伴しない（ja）', async ({
  page,
}) => {
  const keyword = uniqueGemBadgeKeyword()
  let badgedFullName = ''

  await test.step('1. 検索結果でバッジが付いた候補の fullName を控える（前段の検索）', async () => {
    await page.goto('/ja')
    await searchFor(page, keyword)
    const cards = page.getByRole('list').first().locator(':scope > li')
    await expect(cards).toHaveCount(2, { timeout: FIRST_RESULT_TIMEOUT_MS })

    const names: string[] = []
    const flags: boolean[] = []
    for (let i = 0; i < 2; i++) {
      names.push((await cards.nth(i).getByRole('link').first().innerText()).trim())
      flags.push((await cards.nth(i).getByText(ja.home.gemBadge.srHint, { exact: true }).count()) > 0)
    }
    expect(flags).toEqual([false, true])
    badgedFullName = names[1]
    expect(badgedFullName).not.toBe('')
  })

  await test.step('2. 導線を経由せず /gems を直接開く（badged パラメータなし）', async () => {
    await page.goto(`/ja/gems?${SEARCH_PARAM_KEYS.keyword}=${encodeURIComponent(keyword)}`)
    // 緩和（D-37）が発火して何らかの候補が出ることはあるので、一覧の有無そのものは問わない。
    // 見出しが検索語を含む状態まで描画が進んだことだけを待つ（0 件状態の <p> も対象に含める）。
    await expect(page.getByRole('heading', { level: 2 })).toBeVisible({
      timeout: FIRST_RESULT_TIMEOUT_MS,
    })
  })

  await test.step('3. バッジ付き候補（名前不一致）は同伴されず、一覧にも注記にも現れない', async () => {
    expect(await readRepositoryFullNames(page)).not.toContain(badgedFullName)
    await expect(
      page.getByText(ja.gems.includedFromSearch.replace('{count}', '1'), { exact: false }),
    ).toHaveCount(0)
  })
})
