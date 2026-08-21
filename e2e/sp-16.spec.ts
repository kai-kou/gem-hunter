import { randomBytes } from 'node:crypto'
import { expect, test } from '@playwright/test'
import { SEARCH_PARAM_KEYS } from '../src/ui/url/search-params'

/**
 * SP-16: キーワード検索の結果も「過小評価度」の順に並べられる。
 * `docs/02_requirements/user-story-map.md` §5.3 `SP-16` の操作レビュー手順 1〜6 をそのまま写す
 * （`sprint-development-rules.md` `SD-2`）。対応 `AC`: なし（上乗せ要件 `AR-2` の拡張 + `GR-4`）。
 *
 * 🔴 **決定論性の前提（whiteboard `content/discussions/sp16-gem-index-sort-20260821/whiteboard.md`
 * round3 lead 判定「E2E の決定論性」）**: 候補プール（本番は `public/data/daily-digest.json`・npm 由来
 * 実データ 227 件）と検索スタブ（`e2e/fixtures/repos.json` / `e2e/stub/server.mjs` の合成データ）は
 * `repositoryFullName` で 1 件も重ならない。素のまま E2E を回すと gemIndex 付きの結果が常に 0 件になり、
 * 手順 3（なぜ上位かのバッジ表示）・手順 5（Index なしが末尾に残る）を検証できない。
 *
 * このため、本ファイルは `composition/container.ts` の `makeGemDigestPort()`（候補プールの読み込み元を
 * 環境変数 `GEM_DIGEST_SOURCE_PATH` で差し替えられる口・usecase 役が実装確定済み）を前提にしている。
 * 未設定時は本番同様 `public/data/daily-digest.json` を使い、読み込み失敗時は例外を投げず既定プールへ
 * フォールバックする（`GemDigestPort` の fail-soft 契約）。
 *
 * 🔴 **本ファイル単独では Red のまま**（`sprint-development-rules.md` `SD-2` は正しい順序としてこれを
 * 許容する）。以下 2 点が揃うまでは手順 3・4・5 のアサーションが失敗する（`container.ts` 側は実装済み）:
 *   1. `playwright.config.ts`（or `e2e/stub/e2e-env.mjs`）: E2E の `webServer.env` に
 *      `GEM_DIGEST_SOURCE_PATH: path.join(__dirname, 'e2e/fixtures/gem-digest-pool.json')` を追加する。
 *   2. `e2e/fixtures/gem-digest-pool.json`: 下記 `EXPECTED_CANDIDATE_POOL` と同じ内容
 *      （`GemDigestPort#listCandidates()` が返す `{ candidates: Gem[], meta: DigestMeta }` の
 *      JSON 表現。`Gem` の形は `src/domain/model/gem.ts`）を用意し、`repositoryFullName` を
 *      検索スタブの `many-hits` データセット（`octostub/many-01`〜`many-60`・`e2e/stub/server.mjs`）
 *      の一部と **意図的に一致させる**。
 *
 * `many-hits` を含むキーワードはスタブ側で無改修のまま `page` / `per_page` / `sort` を実際に反映する
 * 60 件データセットを返す（`e2e/sp-7.spec.ts` が既に検証済み）ため、本ファイルはスタブ自体の変更を
 * 必要としない。内部の全件取得ループ（usecase 層・`sort: 'relevance', perPage: 100`）は 60 件を
 * 1 回のリクエストで取り切れる（`60 < per_page=100` のため 2 ページ目は発火しない）。
 */

/** 他ファイル・retry 試行との衝突を避けるため、実行のたびに一意なキーワードを生成する（`sp-7` と同じ方針）。 */
function uniqueGemIndexKeyword(): string {
  return `many-hits-gem-${randomBytes(4).toString('hex')}`
}

/**
 * 本テストが前提とする候補プール（`e2e/fixtures/gem-digest-pool.json` に用意されるべき内容）。
 * `octostub/many-30` を最上位（最も小さい gemIndex 値）に、`octostub/many-01` を Index 保持群の
 * 最下位に置き、「並べ替えで先頭要素が変わる」ことをアサーションで検証できるようにする。
 * `octostub/many-05` `many-10` `many-20` は中間順位。それ以外の 55 件（`many-02`〜`many-60` の
 * 上記 5 件を除く全て）は候補プールに存在しない＝ Index なし群として末尾に残る。
 */
const EXPECTED_CANDIDATE_POOL = [
  { fullName: 'octostub/many-30', gemIndex: -50, dependentCount: 900, rank: 1 },
  { fullName: 'octostub/many-20', gemIndex: -30, dependentCount: 700, rank: 2 },
  { fullName: 'octostub/many-10', gemIndex: -10, dependentCount: 500, rank: 3 },
  { fullName: 'octostub/many-05', gemIndex: 0, dependentCount: 300, rank: 4 },
  { fullName: 'octostub/many-01', gemIndex: 10, dependentCount: 100, rank: 5 },
] as const

test.describe('SP-16: 検索結果の Gem Index 順並べ替え', () => {
  test('手順1〜6: 検索 → Gem Index 順 → カード表示 → 2 ページ目でも破綻なし → Index なしは末尾 → 詳細往復', async ({
    page,
  }) => {
    const keyword = uniqueGemIndexKeyword()

    await test.step('手順1: プレビュー URL でキーワード検索する（既定: 関連度順・1 ページ目）', async () => {
      await page.goto('/ja')
      await page.getByRole('searchbox', { name: '検索キーワード' }).fill(keyword)
      await page.getByRole('button', { name: '検索' }).click()
      await expect(page).toHaveURL(new RegExp(`[?&]${SEARCH_PARAM_KEYS.keyword}=`))
      await expect(page.getByRole('list').first().locator(':scope > li')).toHaveCount(20)
      await expect(
        page.getByText('60 件中 20 件を表示', { exact: true }),
      ).toBeVisible()
    })

    await test.step('手順2: 並び順に「Gem Index 順」を選ぶ → 並びが変わり URL に反映される', async () => {
      await page
        .getByRole('navigation', { name: '並び順' })
        .getByRole('link', { name: 'Gem Index 順' })
        .click()

      await expect(page).toHaveURL(
        new RegExp(`[?&]${SEARCH_PARAM_KEYS.sort}=gemIndex(&|$)`),
      )
      await expect(
        page
          .getByRole('navigation', { name: '並び順' })
          .getByRole('link', { name: 'Gem Index 順' }),
      ).toHaveAttribute('aria-current', 'true')

      // 関連度順の先頭（many-01）とは異なる要素（gemIndex 最上位の many-30）が先頭になる
      // ＝ 単なる URL 変化ではなく実際に並び替わったことの検証。
      const items = page.getByRole('list').first().locator(':scope > li')
      await expect(items.first().getByRole('link')).toHaveText('octostub/many-30')
    })

    await test.step('手順3: 各カードで、なぜ上位なのか（被依存数と star の乖離）がわかる', async () => {
      const items = page.getByRole('list').first().locator(':scope > li')

      // `daily-digest.tsx` と同じパターン（被依存数・star・Gem Index の 3 数値を並置・
      // `repository-list.tsx` の `item.gemIndex !== undefined` 分岐）。
      // gemIndex 昇順で並ぶため、`EXPECTED_CANDIDATE_POOL` の rank 順（先頭が最上位）と
      // カードの表示順が一致することも同時に検証する。
      for (const candidate of EXPECTED_CANDIDATE_POOL) {
        const card = items.nth(candidate.rank - 1)
        await expect(card.getByRole('link')).toHaveText(candidate.fullName)
        await expect(card.getByText('被依存数', { exact: false })).toBeVisible()
        await expect(card.getByText(new RegExp(String(candidate.dependentCount)))).toBeVisible()
        await expect(card.getByText('Gem Index', { exact: false })).toBeVisible()
        await expect(card.getByText(new RegExp(String(candidate.gemIndex)))).toBeVisible()
      }

      // 候補プールに存在しない項目（Index なし群・1 ページ目の 6 件目以降）にはバッジが出ない。
      const firstNonCandidateCard = items.nth(EXPECTED_CANDIDATE_POOL.length)
      await expect(firstNonCandidateCard.getByText('Gem Index', { exact: false })).toHaveCount(0)
    })

    await test.step('手順4: 2 ページ目へ進んでも、Gem Index の大小関係が破綻していない', async () => {
      await page
        .getByRole('navigation', { name: '検索結果のページ' })
        .getByRole('link', { name: '次のページへ' })
        .click()

      await expect(page).toHaveURL(new RegExp(`[?&]${SEARCH_PARAM_KEYS.page}=2(&|$)`))
      await expect(page).toHaveURL(new RegExp(`[?&]${SEARCH_PARAM_KEYS.sort}=gemIndex(&|$)`))

      // Index を持つ 5 件は 1 ページ目（gemIndex 昇順で先頭に集約）に収まる設計のため、
      // 2 ページ目（21〜40 件目相当）には Index 付きカードが 1 件も現れない
      // （＝順位が「壊れて」2 ページ目にはみ出していないことの検証）。
      const items = page.getByRole('list').first().locator(':scope > li')
      const count = await items.count()
      for (let i = 0; i < count; i++) {
        await expect(items.nth(i).getByText('Gem Index', { exact: false })).toHaveCount(0)
      }
    })

    await test.step('手順5: Gem Index を持たない結果が末尾に残っている（件数が減っていない）', async () => {
      // 総件数表記は他ソートと同じ（絞り込んでいない・`totalCount` は GitHub 生値のまま）。
      await expect(
        page.getByText(/60 件中/, { exact: false }),
      ).toBeVisible()

      // 候補プールに存在しない項目（例: many-02）は除外されず、どこかのページに残っている
      // （3 ページ・20 件/ページで 60 件全てを走査する）。
      const page1Url = new URL(page.url())
      page1Url.searchParams.delete(SEARCH_PARAM_KEYS.page)

      const namesSeen = new Set<string>()
      for (const pageNum of [1, 2, 3] as const) {
        const url = new URL(page1Url)
        if (pageNum > 1) {
          url.searchParams.set(SEARCH_PARAM_KEYS.page, String(pageNum))
        }
        await page.goto(url.pathname + url.search)
        const items = page.getByRole('list').first().locator(':scope > li')
        const count = await items.count()
        for (let i = 0; i < count; i++) {
          namesSeen.add(await items.nth(i).getByRole('link').innerText())
        }
      }
      // Index を持たない代表例（候補プール外）が絞り込まれず出現している。
      expect(namesSeen.has('octostub/many-02')).toBe(true)
      // 60 件全てが（ページをまたいでも）どこかに存在する＝件数が減っていない。
      expect(namesSeen.size).toBe(60)
    })

    await test.step('手順6: 詳細へ入って戻る → キーワード・ページ・ソートがすべて元のまま', async () => {
      const gemIndexUrl = new URL(page.url())
      gemIndexUrl.searchParams.set(SEARCH_PARAM_KEYS.sort, 'gemIndex')
      gemIndexUrl.searchParams.delete(SEARCH_PARAM_KEYS.page)
      await page.goto(gemIndexUrl.pathname + gemIndexUrl.search)

      const listUrlBeforeDetail = page.url()
      await page.getByRole('link', { name: 'octostub/many-30' }).click()
      await expect(page).toHaveURL(/\/ja\/repos\/octostub\/many-30(\?|$)/)
      await expect(page.getByRole('heading', { name: 'octostub/many-30' })).toBeVisible()

      await page.getByRole('link', { name: '一覧へ戻る' }).click()

      await expect(page).toHaveURL(listUrlBeforeDetail)
      await expect(page.getByRole('searchbox', { name: '検索キーワード' })).toHaveValue(keyword)
      await expect(
        page
          .getByRole('navigation', { name: '並び順' })
          .getByRole('link', { name: 'Gem Index 順' }),
      ).toHaveAttribute('aria-current', 'true')
    })
  })
})
