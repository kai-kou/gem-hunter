import { describe, expect, it } from 'vitest'

import type { DigestMeta } from '../domain/model/gem'
import { gemIndex } from '../domain/model/gem-index'
import type {
  GemIndexPort,
  GemPoolSearchInput,
  GemPoolSearchResult,
} from '../domain/ports/gem-index-port'
import { DEFAULT_PAGE, MAX_PAGE } from '../domain/model/page-number'
import { DEFAULT_PER_PAGE } from '../domain/model/per-page'
import { MAX_INCLUDE_FULL_NAMES, makeSearchGems, toGemListPage } from './search-gems'

const meta: DigestMeta = {
  source: 'Ecosyste.ms',
  sourceUrl: 'https://ecosyste.ms/',
  license: 'CC BY-SA 4.0',
  sourceLicenseUrl: 'https://creativecommons.org/licenses/by-sa/4.0/',
  generatedAt: '2026-08-22T06:04:21.791Z',
}

const entry = {
  packageName: 'left-pad',
  repositoryFullName: 'stevemao/left-pad',
  dependentCount: 12345,
  stars: 1234,
  gemIndex: gemIndex(-42.5),
  registry: 'npmjs.org',
}

/** 実データの候補プール件数（絞り込みなしのときの母数）。健全なプールの目印に使う。 */
const POOL_SIZE = 62483

function makeResult(overrides: Partial<GemPoolSearchResult> = {}): GemPoolSearchResult {
  return {
    items: [],
    totalCount: 0,
    effectivePage: DEFAULT_PAGE,
    usedTokens: [],
    relaxed: false,
    includedCount: 0,
    meta,
    ...overrides,
  }
}

/**
 * 「絞り込みなし＝全件」でポートが返してくる結果の縮小版（`tokens: []` のときの契約）。
 * 実データでは 62,483 件が返る。ここでは 1 件で「全件が素通しされていないこと」を見る。
 */
const allEntriesResult: GemPoolSearchResult = makeResult({
  items: [entry],
  totalCount: POOL_SIZE,
})

/** 絞り込みが 1 件当たったときの結果。 */
const oneHitResult: GemPoolSearchResult = makeResult({
  items: [entry],
  totalCount: 1,
  usedTokens: ['kafka'],
})

/** 取得失敗（`GemIndexPort#search` は例外を投げず空の結果を返す契約）。 */
const failureResult: GemPoolSearchResult = makeResult()

/**
 * `GemIndexPort` のフェイク。`vi.mock` は使わない（`architecture-rules.md` §4:
 * 上位層のテストでモックしたくなったら設計を直す＝フェイクのポート実装を渡す）。
 *
 * 既定は **健全なプール**（絞り込みなしなら全件・絞り込めば 1 件）。取得失敗を再現したいときは
 * `respond` に常に空結果を返す関数を渡す（プールが空なら絞り込みなしでも 0 件になる）。
 */
function fakePort(
  received: GemPoolSearchInput[],
  respond: (input: GemPoolSearchInput) => GemPoolSearchResult = (input) =>
    input.tokens.length === 0 ? allEntriesResult : oneHitResult,
): GemIndexPort {
  return {
    async lookup() {
      return new Map()
    },
    async search(input) {
      received.push(input)
      return respond(input)
    },
  }
}

/** 常に同じ結果を返すフェイク（従来の `fakePort(received, result)` と同じ使い勝手）。 */
function fixedPort(received: GemPoolSearchInput[], result: GemPoolSearchResult): GemIndexPort {
  return fakePort(received, () => result)
}

/** `status: 'ok'` を型で絞り込む（テスト本体を読みやすくする）。 */
function expectOk(result: Awaited<ReturnType<ReturnType<typeof makeSearchGems>>>) {
  if (result.status !== 'ok') {
    throw new Error(`status: 'ok' を期待したが ${result.status} だった`)
  }
  return result
}

describe('toGemListPage', () => {
  /**
   * 🔴 F-02: Gem 一覧のページ番号は **GitHub 検索 API の上限（`MAX_PAGE` = 50）に縛られない**。
   * 候補プールは実測で 1 語 8,913 件（`com`）に達するため、50 ページで打ち切ると残りが
   * 到達不能になる（`tryPageNumber` を使わない理由）。
   */
  it('GitHub 検索 API の上限（50 ページ）を超える指定もそのまま通す', () => {
    expect(toGemListPage(String(MAX_PAGE + 1))).toBe(MAX_PAGE + 1)
    expect(toGemListPage(447)).toBe(447)
  })

  it('未指定・空文字は既定ページへ倒す', () => {
    expect(toGemListPage(undefined)).toBe(DEFAULT_PAGE)
    expect(toGemListPage(null)).toBe(DEFAULT_PAGE)
    expect(toGemListPage('')).toBe(DEFAULT_PAGE)
  })

  it('正整数でない値は例外にせず既定ページへ倒す（URL 改変で 500 にしない）', () => {
    expect(toGemListPage('0')).toBe(DEFAULT_PAGE)
    expect(toGemListPage('-3')).toBe(DEFAULT_PAGE)
    expect(toGemListPage('1.5')).toBe(DEFAULT_PAGE)
    expect(toGemListPage('abc')).toBe(DEFAULT_PAGE)
    expect(toGemListPage('Infinity')).toBe(DEFAULT_PAGE)
    expect(toGemListPage(Number.MAX_VALUE)).toBe(DEFAULT_PAGE)
  })

  it('同名クエリが重複していたら先頭の値を採る（`searchParams` は配列で届く）', () => {
    expect(toGemListPage(['3', '9'])).toBe(3)
    expect(toGemListPage([])).toBe(DEFAULT_PAGE)
  })
})

describe('searchGems', () => {
  it('検索語をトークン列へ正規化してポートへ渡す（単語境界で分割・小文字化）', async () => {
    const received: GemPoolSearchInput[] = []
    const searchGems = makeSearchGems({ gems: fakePort(received) })

    await searchGems({ query: '  Kafka-Client  ' })

    expect(received).toHaveLength(1)
    expect(received[0].tokens).toEqual(['kafka', 'client'])
  })

  it('ページ・表示件数を省略すると既定値でポートを呼ぶ', async () => {
    const received: GemPoolSearchInput[] = []
    const searchGems = makeSearchGems({ gems: fakePort(received) })

    await searchGems({ query: 'kafka' })

    expect(received[0].page).toBe(DEFAULT_PAGE)
    expect(received[0].perPage).toBe(DEFAULT_PER_PAGE)
  })

  it('URL 由来の生値（文字列）を受け取り、値オブジェクトへ変換してから渡す', async () => {
    const received: GemPoolSearchInput[] = []
    const searchGems = makeSearchGems({ gems: fakePort(received) })

    await searchGems({ query: 'kafka', page: '3', perPage: '50' })

    expect(received[0].page).toBe(3)
    expect(received[0].perPage).toBe(50)
  })

  it('不正なページ・表示件数は例外にせず既定値へ倒す（URL 改変で 500 にしない）', async () => {
    const received: GemPoolSearchInput[] = []
    const searchGems = makeSearchGems({ gems: fakePort(received) })

    await searchGems({ query: 'kafka', page: '-1', perPage: '7' })

    expect(received[0].page).toBe(DEFAULT_PAGE)
    expect(received[0].perPage).toBe(DEFAULT_PER_PAGE)
  })

  /**
   * 🔴 F-02: 到達可能な最終ページへのクランプは **ポートの実装（候補プールの母数を知る側）**
   * の責務で、ここでは切り詰めない（`tryPageNumber` の GitHub API 上限を持ち込まない）。
   */
  it('GitHub 検索 API の上限を超えるページもそのままポートへ渡す（クランプは実装側）', async () => {
    const received: GemPoolSearchInput[] = []
    const searchGems = makeSearchGems({ gems: fakePort(received) })

    await searchGems({ query: 'kafka', page: MAX_PAGE + 1 })

    expect(received[0].page).toBe(MAX_PAGE + 1)
  })

  it('実際に返したページ（`effectivePage`）をそのまま返す（URL とズレても画面が真を出せる）', async () => {
    const received: GemPoolSearchInput[] = []
    const searchGems = makeSearchGems({
      gems: fakePort(received, () =>
        makeResult({ items: [entry], totalCount: 1, effectivePage: 82 }),
      ),
    })

    const result = expectOk(await searchGems({ query: 'core', page: '51' }))

    expect(received[0].page).toBe(51)
    expect(result.effectivePage).toBe(82)
  })

  it('検索語が空・記号だけならトークン空配列（＝絞り込みなし）で渡す', async () => {
    const received: GemPoolSearchInput[] = []
    const searchGems = makeSearchGems({ gems: fakePort(received) })

    await searchGems({ query: '  --  ' })

    expect(received[0].tokens).toEqual([])
  })

  it('ポートの結果をそのまま返す（並べ替え・絞り込みを二重に行わない）', async () => {
    const searchGems = makeSearchGems({ gems: fixedPort([], oneHitResult) })

    const result = await searchGems({ query: 'kafka' })

    // 照合可否のフラグだけを積み増し、items は同一参照のまま（並べ替え直していない）。
    expect(result).toEqual({ ...oneHitResult, status: 'ok', unmatchableQuery: false })
    expect(expectOk(result).items).toBe(oneHitResult.items)
  })

  /**
   * 🔴 日本語だけの検索語は `tokenizeQuery` が空配列を返すため、ポートの契約では
   * 「絞り込みなし＝全件」になる。画面が「『画像処理』の Gem」と名乗って候補プール全件
   * （実測 62,483 件）を出すのは端的な誤表示なので、ユースケースが 0 件へ倒す。
   */
  it('日本語だけの検索語は全件ではなく 0 件へ倒し、照合不能として識別できる', async () => {
    const received: GemPoolSearchInput[] = []
    const searchGems = makeSearchGems({ gems: fakePort(received) })

    const result = expectOk(await searchGems({ query: '画像処理' }))

    expect(result.unmatchableQuery).toBe(true)
    expect(result.totalCount).toBe(0)
    expect(result.items).toEqual([])
    expect(result.usedTokens).toEqual([])
    expect(result.relaxed).toBe(false)
    // 出典表示は 0 件の画面でも出す（`D-29` / `GR-6`）ため、メタデータは捨てない。
    expect(result.meta).toEqual(meta)
  })

  /**
   * 🔴 F-14: 照合不能の判定は **ポートを呼ぶ前** に行う。判定を後ろに置くと、返さない結果の
   * ために検索インデックス構築（実測 tokenize 約 91ms + 並べ替え約 31ms）と全件走査を払う。
   * 出典メタデータ（`D-29`）だけは 0 件の画面でも要るため、絞り込みなしの 1 回だけ呼ぶ。
   */
  it('照合不能な検索語では、トークン付きの絞り込みを 1 回も実行しない（F-14）', async () => {
    const received: GemPoolSearchInput[] = []
    const searchGems = makeSearchGems({ gems: fakePort(received) })

    await searchGems({ query: '画像処理', page: '4' })

    expect(received).toHaveLength(1)
    expect(received[0].tokens).toEqual([])
    // 母数を持たない 0 件なので、要求ページは持ち込まない（1 ページ目のメタだけを取る）。
    expect(received[0].page).toBe(DEFAULT_PAGE)
  })

  it('ASCII を含む検索語は従来どおり絞り込む（照合不能にしない）', async () => {
    const received: GemPoolSearchInput[] = []
    const searchGems = makeSearchGems({ gems: fakePort(received) })

    const result = expectOk(await searchGems({ query: 'JSON パーサー' }))

    expect(received[0].tokens).toEqual(['json'])
    expect(result.unmatchableQuery).toBe(false)
    expect(result.totalCount).toBe(oneHitResult.totalCount)
    expect(result.items).toBe(oneHitResult.items)
  })

  it('空文字・空白だけの検索語は従来どおりの扱い（照合不能にしない・呼び出し側が先に弾く）', async () => {
    const received: GemPoolSearchInput[] = []
    const searchGems = makeSearchGems({ gems: fakePort(received) })

    const blank = expectOk(await searchGems({ query: '   ' }))
    const empty = expectOk(await searchGems({ query: '' }))

    expect(received[0].tokens).toEqual([])
    expect(blank.unmatchableQuery).toBe(false)
    expect(blank.totalCount).toBe(allEntriesResult.totalCount)
    expect(empty.unmatchableQuery).toBe(false)
  })

  it('記号だけの検索語は照合不能として扱う（英数字の識別子を 1 語も取り出せない）', async () => {
    const searchGems = makeSearchGems({ gems: fakePort([]) })

    const result = expectOk(await searchGems({ query: '--' }))

    expect(result.unmatchableQuery).toBe(true)
    expect(result.totalCount).toBe(0)
  })

  /**
   * 🔴 F-05: **取得失敗と 0 件は別物**。`GemIndexPort#search` は失敗時に例外を投げず空の結果を
   * 返す契約なので、`totalCount === 0` だけでは区別できない。絞り込みなしの母数（＝候補プールの
   * 件数）が 0 なら「プールを読めていない」と判定する（一致が無いだけならプールは健全）。
   */
  it('候補プールを読めていないとき（契約どおりの空結果）は取得失敗として返す', async () => {
    const received: GemPoolSearchInput[] = []
    const searchGems = makeSearchGems({ gems: fixedPort(received, failureResult) })

    const result = await searchGems({ query: 'kafka' })

    expect(result.status).toBe('failed')
  })

  it('照合不能な検索語でも、候補プールを読めていなければ取得失敗として返す', async () => {
    const searchGems = makeSearchGems({ gems: fixedPort([], failureResult) })

    const result = await searchGems({ query: '画像処理' })

    expect(result.status).toBe('failed')
  })

  it('ポートが例外を投げたときも 500 にせず取得失敗として返す（二重防御）', async () => {
    const searchGems = makeSearchGems({
      gems: {
        async lookup() {
          return new Map()
        },
        async search() {
          throw new Error('shard fetch failed')
        },
      },
    })

    const result = await searchGems({ query: 'kafka' })

    expect(result.status).toBe('failed')
  })

  /** 一致が無いだけ（プールは健全）は取得失敗ではない。母集団の限界の説明を出す側の状態。 */
  it('プールは健全で一致だけが 0 件のときは、取得失敗にせず 0 件として返す', async () => {
    const received: GemPoolSearchInput[] = []
    const searchGems = makeSearchGems({
      gems: fakePort(received, (input) =>
        input.tokens.length === 0 ? allEntriesResult : makeResult(),
      ),
    })

    const result = expectOk(await searchGems({ query: 'zzgemhunterzz' }))

    expect(result.totalCount).toBe(0)
    expect(result.unmatchableQuery).toBe(false)
    // 0 件のときだけ母数を確かめる 2 回目の呼び出しが入る（ヒット時は 1 回のまま）。
    expect(received).toHaveLength(2)
    expect(received[1].tokens).toEqual([])
  })

  it('ヒットしたときは母数の確認を行わない（ポート呼び出しは 1 回）', async () => {
    const received: GemPoolSearchInput[] = []
    const searchGems = makeSearchGems({ gems: fakePort(received) })

    await searchGems({ query: 'kafka' })

    expect(received).toHaveLength(1)
  })
})

/**
 * `includeFullNames`（URL 由来の同伴指定）の正規化（`SP-19` 追補・案3'・Issue #453）。
 * 生値 → プールへ渡す `repositoryFullName` の集合への変換はこのユースケース層の責務。
 */
describe('searchGems: includeFullNames の正規化', () => {
  it('カンマ区切り・配列・前後空白を正規化してポートへ渡す', async () => {
    const received: GemPoolSearchInput[] = []
    const searchGems = makeSearchGems({ gems: fakePort(received) })

    await searchGems({
      query: 'kafka',
      includeFullNames: '  owner/repo1 , owner2/repo2  ',
    })

    expect(received[0].includeFullNames).toEqual(['owner/repo1', 'owner2/repo2'])
  })

  it('配列で届いた値も、要素ごとのカンマ区切りも合わせて正規化する（`searchParams` の素の形）', async () => {
    const received: GemPoolSearchInput[] = []
    const searchGems = makeSearchGems({ gems: fakePort(received) })

    await searchGems({
      query: 'kafka',
      includeFullNames: ['ownerA/repoA', 'ownerB/repoB,ownerC/repoC'],
    })

    expect(received[0].includeFullNames).toEqual(['ownerA/repoA', 'ownerB/repoB', 'ownerC/repoC'])
  })

  it('`owner/repo` 形式でないもの・長すぎるものは捨てる', async () => {
    const received: GemPoolSearchInput[] = []
    const searchGems = makeSearchGems({ gems: fakePort(received) })
    const tooLong = `${'x'.repeat(201)}/repo`

    await searchGems({
      query: 'kafka',
      includeFullNames: [
        'owner/repo1',
        'not-a-fullname',
        '../traversal/x',
        'a/b/c',
        tooLong,
        'owner2/repo2',
      ],
    })

    expect(received[0].includeFullNames).toEqual(['owner/repo1', 'owner2/repo2'])
  })

  /**
   * 🟡 WARNING（`search-gems.ts:101` 相当）: `INCLUDE_FULL_NAME_PATTERN` は 1 スラッシュのみを
   * 要求するだけで、セグメントがドットだけ（`.` / `..`）であることまでは弾かない。
   * `'../evil'` は 2 セグメント（`..` と `evil`）で **パターン自体には一致する**ため、
   * 3 セグメントの `'../traversal/x'`（上のテストでパターン不一致により弾かれる）とは
   * 別に、ドットだけのセグメント防御そのものを固定する。
   */
  it('2 セグメントのドットトラバーサル（`../evil`）はパターンに一致しても捨てる', async () => {
    const received: GemPoolSearchInput[] = []
    const searchGems = makeSearchGems({ gems: fakePort(received) })

    await searchGems({
      query: 'kafka',
      includeFullNames: ['owner/repo1', '../evil', 'owner/..', 'owner2/repo2'],
    })

    expect(received[0].includeFullNames).toEqual(['owner/repo1', 'owner2/repo2'])
  })

  /**
   * 🟡 WARNING（`search-gems.ts:129` 相当）: `split(',')` の前に生値の文字数で切っていないと、
   * 区切り文字だけを大量に並べた入力（20 件上限は分割後にしか効かない）で走査量が青天井になる
   * （`tokenizeQuery` の `F-01` と同じ問題）。分割前の切り詰めにより、上限文字数を超えた位置に
   * ある正当な値は最初から候補に入らないことを固定する。
   */
  it('カンマだけを大量に並べた入力は、分割前に上限文字数で切り捨てる（F-01 相当）', async () => {
    const received: GemPoolSearchInput[] = []
    const searchGems = makeSearchGems({ gems: fakePort(received) })
    // 上限文字数をはるかに超える位置に正当な値を置く。分割前に切り詰められていれば
    // この値は候補にすら現れない。
    const raw = `${','.repeat(100_000)}owner/repo`

    await searchGems({ query: 'kafka', includeFullNames: raw })

    // 空配列に切り詰められた結果は「同伴指定なし」と同じ扱いになり、ポートへは渡さない
    // （`makeSearchGems` は `includeFullNames.length > 0` のときだけフィールドを積む）。
    expect(received[0].includeFullNames).toBeUndefined()
  })

  it(`先頭 ${MAX_INCLUDE_FULL_NAMES} 件までに切り詰める（超過分は例外にせず捨てる）`, async () => {
    const received: GemPoolSearchInput[] = []
    const searchGems = makeSearchGems({ gems: fakePort(received) })
    const many = Array.from({ length: MAX_INCLUDE_FULL_NAMES + 5 }, (_, i) => `owner${i}/repo${i}`)

    await searchGems({ query: 'kafka', includeFullNames: many })

    expect(received[0].includeFullNames).toHaveLength(MAX_INCLUDE_FULL_NAMES)
    expect(received[0].includeFullNames).toEqual(many.slice(0, MAX_INCLUDE_FULL_NAMES))
  })

  it('大文字小文字を無視して重複を畳み、最初に現れた綴りを残す', async () => {
    const received: GemPoolSearchInput[] = []
    const searchGems = makeSearchGems({ gems: fakePort(received) })

    await searchGems({
      query: 'kafka',
      includeFullNames: 'Owner/Repo, owner/repo, OWNER/REPO',
    })

    expect(received[0].includeFullNames).toEqual(['Owner/Repo'])
  })

  /**
   * 🔴 照合不能クエリ（日本語だけの検索語等）では同伴しない。この経路は「絞り込みなし」を
   * 案内する 0 件 + `unmatchableQuery` 契約を維持するためのメタ取得専用呼び出しで、
   * 同伴を混ぜると「該当なし」の案内と実際に返す件数が食い違う。
   */
  it('照合不能クエリでは includeFullNames を同伴させない', async () => {
    const received: GemPoolSearchInput[] = []
    const searchGems = makeSearchGems({ gems: fakePort(received) })

    await searchGems({ query: '画像処理', includeFullNames: 'owner/repo' })

    expect(received).toHaveLength(1)
    expect(received[0].includeFullNames).toBeUndefined()
  })
})
