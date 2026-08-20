import { randomBytes } from 'node:crypto'
import { expect, test } from '@playwright/test'
import ja from '../messages/ja.json'
import { searchFor } from './helpers'

/**
 * `AC-12`: 認証済みでもプライベートリポジトリが表示されない（`prd.md` §6 `AC-12` / `NFR-33`）。
 *
 * サーバーは GitHub App の installation token（`D-20`）で動くため、トークンから見える private
 * リポジトリが API 応答に現れうる。アプリ側は 3 層で公開に閉じる:
 *   ① 検索クエリへ `is:public` を AND 付与（`github-repository-query.ts`）
 *   ② 検索結果のマッピングで `private: true` を除外（`mapper.ts`）
 *   ③ 詳細応答が `private: true` なら「見つからない」として扱う（`mapper.ts` / §7 の 404 と同じ提示）
 *
 * 本テストはスタブ（`e2e/stub/server.mjs`）に **`is:public` を無視して private を混ぜて返させる**
 * ことで ① が破れた状況を作り、② ③ が単独でも私有データを露出させないことを画面で確認する。
 * 「名前・説明・統計のいずれも表示されない」は描画結果なので E2E でしか検証できない（`AC-12` 後半）。
 */

const STUB_ORIGIN = `http://127.0.0.1:${process.env.E2E_STUB_PORT ?? '8788'}`

/** スタブが private 混在データセットを返すキーワード（接頭辞は `server.mjs` の分岐と対応）。 */
const PRIVATE_MIXED_PREFIX = 'private-mixed'
/** スタブが private として返すリポジトリ（`server.mjs` の `privateMixedRepos`）。 */
const PRIVATE_REPO = 'octostub/octo-secret'
const PUBLIC_REPO = 'octostub/octo-public-sample'
/** private リポジトリの説明文（画面のどこにも出ないことを確認するための目印）。 */
const PRIVATE_DESCRIPTION = 'PRIVATE-SECRET-DESCRIPTION'

/**
 * 実行のたびに一意な検索キーワードを生成する（`sp-5.spec.ts` と同じ理由・同じ手口）。
 * キャッシュ（プロセス内共有・TTL あり）に前回試行の結果が残っていると、スタブへ実際に
 * リクエストが飛ばず `lastSearchQuery` を観測できないため、構造的にキャッシュミスにする。
 */
function uniqueKeyword(): string {
  return `${PRIVATE_MIXED_PREFIX}-${randomBytes(4).toString('hex')}`
}

test('AC-12: 認証済みでも private リポジトリが検索結果にも詳細にも出ない', async ({ page }) => {
  await test.step('1. private が混ざる結果を返すキーワードで検索する', async () => {
    await page.goto('/ja')
    await searchFor(page, uniqueKeyword())
    await expect(page.getByRole('link', { name: PUBLIC_REPO })).toBeVisible()
  })

  await test.step('2. GitHub へ送る検索クエリに公開限定条件（is:public）が含まれている', async () => {
    const response = await fetch(`${STUB_ORIGIN}/__stats`)
    expect(response.ok).toBe(true)
    const stats = (await response.json()) as { lastSearchQuery: string | null }
    expect(stats.lastSearchQuery).toContain('is:public')
  })

  await test.step('3. 検索結果に private: true のリポジトリが 1 件も含まれない', async () => {
    await expect(page.getByRole('link', { name: PRIVATE_REPO })).toHaveCount(0)
    await expect(page.getByText('octo-secret')).toHaveCount(0)
    await expect(page.getByText(PRIVATE_DESCRIPTION)).toHaveCount(0)
    // 総件数は上流の値（2 件）のまま・表示は公開の 1 件だけ（フィルタで総件数を書き換えない）
    await expect(page.getByText('2 件中 1 件を表示')).toBeVisible()
  })

  await test.step('4. private リポジトリの詳細 URL を直接開くと「見つからない」になる', async () => {
    const response = await page.goto(`/ja/repos/${PRIVATE_REPO}`)
    expect(response?.status()).toBe(404)
    await expect(page.getByText(ja.detail.notFound, { exact: true })).toBeVisible()
  })

  await test.step('5. その画面にリポジトリ名・説明・統計のいずれも表示されていない', async () => {
    await expect(page.getByText('octo-secret')).toHaveCount(0)
    await expect(page.getByText(PRIVATE_DESCRIPTION)).toHaveCount(0)
    for (const label of [
      ja.detail.starCount,
      ja.detail.watcherCount,
      ja.detail.forkCount,
      ja.detail.openIssueCount,
    ]) {
      await expect(page.getByText(label, { exact: true })).toHaveCount(0)
    }
  })
})
