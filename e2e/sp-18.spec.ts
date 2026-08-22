import { randomBytes } from 'node:crypto'
import { expect, test, type Locator, type Page } from '@playwright/test'

import ja from '../messages/ja.json'
import en from '../messages/en.json'
import { SEARCH_PARAM_KEYS } from '../src/ui/url/search-params'
import { searchFor } from './helpers'

/**
 * SP-18: 検索結果カードに Gem バッジが出る（`D-36` / `D-38`）。
 * `docs/02_requirements/user-story-map.md` §5.3 `SP-18` の操作レビュー手順をそのまま写す
 * （`sprint-development-rules.md` `SD-2`）。対応 `AC`: なし（上乗せ要件 `GR-4`）。
 *
 * 🔴 **ネットワークは踏まない**（`NFR-24`）。GitHub API は `e2e/stub/server.mjs` のスタブへ
 * 向いており、Gem 候補プールは `public/data/gem-index/`（`D-38` のレジストリ別シャード）を
 * アプリ側がファイルシステムから読む。
 *
 * ⚠️ **バッジが 1 件も出ないことは失敗ではない**（本スイートの中核前提）。スタブが返すのは
 * 架空のリポジトリ（`octostub/*`）で、実在の候補プール（Ecosyste.ms 由来）には載らない。
 * そこで本スイートは **バッジの有無に依存しない不変条件** を固定する:
 *
 *   ① 並び順がスタブの返却順（= 関連度順）のまま変わっていない（`D-36` の中核制約。
 *      バッジは注釈であって並び替え軸ではない）
 *   ② 注記（バッジが付かないことが低評価を意味しない旨）の出現回数は
 *      `min(バッジ件数, 1)` に等しい（バッジが出れば一覧に 1 回だけ出る / 出なければ 0 回）
 *   ③ バッジ件数はカード件数を超えない
 *
 * ②③ は「バッジが出る」「出ない」の **どちらの状態でも成立する**（`if` で分岐しない）ため、
 * 将来スタブのフィクスチャへ実在の候補プール所属リポジトリが加われば、テストを書き換えずに
 * そのままバッジ経路の検証として機能する。
 */

/**
 * 🔴 **サーバー起動後の最初の検索だけ待ち時間が長い**（既定の 5 秒では足りない）。
 * `StaticGemIndex` は候補プールのレジストリ別シャード（`public/data/gem-index/` 計 3.5MB 弱・
 * `D-38`）を最初の照会で読み込み、以降は isolate 内メモリキャッシュに載せる。ローカル実測で
 * **初回 2.8 秒 / 2 回目以降 0.04 秒**（`?q=zero-hits`（照会なし）の初回は 0.24 秒だったので、
 * この差はシャード読み込みそのもの）。ブラウザ経由の実行はさらに上振れするため、
 * 「最初に結果一覧が出るまで」の待ちだけ明示的に延ばす。
 *
 * ⚠️ これは**テストを緑にするための緩和ではなく、初回コストの計測値をテストに固定したもの**。
 * 読み込み方式（分割読み・軽量な照会用インデックス等）で初回コストが下がったらこの値も下げる。
 */
const FIRST_RESULT_TIMEOUT_MS = 30_000

/** 他ファイル・retry 試行との衝突を避けるため、実行のたびに一意なキーワードを生成する（`sp-7` と同じ方針）。 */
function uniqueManyHitsKeyword(): string {
  return `many-hits-${randomBytes(4).toString('hex')}`
}

/** 検索結果一覧（トップレベルの `ul`。カード内の topics `ul` ではない）。 */
function resultList(page: Page): Locator {
  return page.getByRole('list').first()
}

/** 検索結果カードを表示順のまま取り出す。 */
function resultCards(page: Page): Locator {
  return resultList(page).locator(':scope > li')
}

/** 表示順のままリポジトリ名（`owner/repo`）を読み出す。 */
async function readResultFullNames(page: Page): Promise<string[]> {
  const cards = resultCards(page)
  const count = await cards.count()
  const names: string[] = []
  for (let i = 0; i < count; i++) {
    names.push((await cards.nth(i).getByRole('link').first().innerText()).trim())
  }
  return names
}

/**
 * 「Gem バッジと注記の整合」を検証する（上記 ②③）。バッジは可視ラベル（例「Gem」）だけでは
 * 他の短い語と衝突しうるため、バッジ内の `sr-only` ヒント文（カードごとに 1 つ）を数える。
 */
async function expectGemBadgeInvariants(
  page: Page,
  labels: { srHint: string; note: string },
): Promise<number> {
  await expect(resultList(page)).toBeVisible()

  const cardCount = await resultCards(page).count()
  const badgeCount = await resultList(page).getByText(labels.srHint, { exact: true }).count()
  const noteCount = await page.getByText(labels.note, { exact: true }).count()

  // ③ バッジはカードに対して 1 枚まで（同じカードへ二重に出ない・カード数を超えない）
  expect(badgeCount).toBeLessThanOrEqual(cardCount)
  // ② 注記はバッジが 1 件以上あるときちょうど 1 回、無ければ 0 回（分岐せず 1 本の式で表す）
  expect(noteCount).toBe(Math.min(badgeCount, 1))

  return badgeCount
}

test('SP-18: 検索結果に Gem バッジが出ても並び順は関連度順のまま変わらない（ja）', async ({
  page,
}) => {
  const keyword = uniqueManyHitsKeyword()
  const labels = { srHint: ja.home.gemBadge.srHint, note: ja.home.gemBadge.note }

  await test.step('1. キーワード検索する（60 件ヒット・既定 = 1 ページ目 / 関連度順 / 20 件表示）', async () => {
    await page.goto('/ja')
    await searchFor(page, keyword)
    await expect(resultCards(page)).toHaveCount(20, { timeout: FIRST_RESULT_TIMEOUT_MS })
  })

  await test.step('2. 並び順がスタブの返却順（関連度順）のまま変わっていない（D-36 の中核制約）', async () => {
    const names = await readResultFullNames(page)
    // スタブは挿入順（many-01 … many-60）で返す。Gem バッジが並び替えに使われていれば
    // ここが崩れる（`D-36`: `sort=gem-index` は復活させない）。
    expect(names).toEqual(
      Array.from({ length: 20 }, (_, i) => `octostub/many-${String(i + 1).padStart(2, '0')}`),
    )
  })

  await test.step('3. バッジと注記が整合している（バッジが出るなら注記も 1 回だけ読める）', async () => {
    await expectGemBadgeInvariants(page, labels)
  })

  await test.step('4. 2 ページ目へ進んでもバッジの判定が同じ基準で効いている', async () => {
    await page
      .getByRole('navigation', { name: '検索結果のページ' })
      .getByRole('link', { name: '次のページへ' })
      .click()

    await expect(page).toHaveURL(new RegExp(`[?&]${SEARCH_PARAM_KEYS.page}=2(&|$)`))
    await expect(resultCards(page)).toHaveCount(20)

    // 2 ページ目でも並び順は返却順のまま（21〜40 件目）
    const names = await readResultFullNames(page)
    expect(names).toEqual(
      Array.from({ length: 20 }, (_, i) => `octostub/many-${String(i + 21).padStart(2, '0')}`),
    )
    // 同じ不変条件が 2 ページ目でも成立する（1 ページ目だけの特別扱いをしていない）
    await expectGemBadgeInvariants(page, labels)
  })

  await test.step('5. 詳細へ入って戻る → キーワード・ページ・ソートがすべて元のまま', async () => {
    const listUrlBeforeDetail = page.url()

    await page.getByRole('link', { name: 'octostub/many-21' }).click()
    await expect(page).toHaveURL(/\/ja\/repos\/octostub\/many-21(\?|$)/)
    await expect(page.getByRole('heading', { name: 'octostub/many-21' })).toBeVisible()

    await page.getByRole('link', { name: '一覧へ戻る' }).click()

    await expect(page).toHaveURL(listUrlBeforeDetail)
    await expect(page.getByRole('searchbox', { name: '検索キーワード' })).toHaveValue(keyword)
    await expect(resultCards(page)).toHaveCount(20)
    // 戻った先でも並び順・バッジ判定の基準は変わらない
    expect(await readResultFullNames(page)).toEqual(
      Array.from({ length: 20 }, (_, i) => `octostub/many-${String(i + 21).padStart(2, '0')}`),
    )
    await expectGemBadgeInvariants(page, labels)
  })
})

test('SP-18: 英語 UI でも同じ基準で判定され、注記は英語で読める（en・D-36 の i18n 要件）', async ({
  page,
}) => {
  const keyword = uniqueManyHitsKeyword()
  const labels = { srHint: en.home.gemBadge.srHint, note: en.home.gemBadge.note }

  await test.step('1. 英語 UI でキーワード検索する', async () => {
    // 英語 UI の検索欄は日本語 UI とアクセシブルネームが違うため、URL 直接指定で検索する
    // （本テストの関心は言語切替 UI ではなくバッジ・注記の i18n）。
    await page.goto(`/en?${SEARCH_PARAM_KEYS.keyword}=${encodeURIComponent(keyword)}`)
    await expect(resultCards(page)).toHaveCount(20, { timeout: FIRST_RESULT_TIMEOUT_MS })
  })

  await test.step('2. 並び順は英語 UI でも返却順のまま', async () => {
    expect(await readResultFullNames(page)).toEqual(
      Array.from({ length: 20 }, (_, i) => `octostub/many-${String(i + 1).padStart(2, '0')}`),
    )
  })

  await test.step('3. 注記が英語で読める（バッジが出るなら 1 回だけ・日本語文言は出ない）', async () => {
    await expectGemBadgeInvariants(page, labels)
    // 英語 UI に日本語の注記が混ざっていないこと（文言の取り違えの検出）
    await expect(page.getByText(ja.home.gemBadge.note, { exact: true })).toHaveCount(0)
  })
})
