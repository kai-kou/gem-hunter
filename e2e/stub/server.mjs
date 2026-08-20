// E2E 用スタブ GitHub API サーバー（node:http のみ・外部依存を足さない）。
// 固定データは ../fixtures/*.json を読むだけで、ここでは配信のためのごく薄い整形（フィールド射影・
// ページ分割・キーワード分岐）しか行わない。
//
// ルーティング:
//   GET /search/repositories?q=&page=&per_page=
//   GET /repos/{owner}/{repo}
//   GET  /__stats        （SP-5 E2E 検証専用・実 GitHub API には存在しない裏口）
//   POST /__stats/reset   同上
//
// キーワード規約（q または repo 名に部分一致で判定）:
//   通常のキーワード      → 複数件の結果（total_count は 2 ページ以上になる値）
//   zero-hits を含む      → total_count: 0 / items: []
//   upstream-error を含む → HTTP 500
//   rate-limit を含む     → HTTP 403 + x-ratelimit-remaining: 0 + x-ratelimit-reset
//   not-found を含む（repo 名 or owner）→ HTTP 404（詳細 API のみ）
//   private-mixed を含む  → AC-12 E2E 専用。上流が is:public を無視して private を混ぜて返す状況を
//                             再現する（public 1 件 + private 1 件・total_count は 2）。
//                             `octostub/octo-secret` の詳細も 200 + `private: true` で返す
//   many-hits を含む       → SP-7（ページネーション・並び替え・表示件数）E2E 専用の 60 件
//                             データセット。実 API と同様に `page` / `per_page` / `sort` を
//                             実際に反映して切り出す（他キーワードは PAGE_1_REPOS/PAGE_2_REPOS
//                             固定・既存 E2E への影響を避けるため分離）。
//
// `/__stats`: スタブへ実際に届いたリクエスト数（`searchCount` / `detailCount`）を返す。
// SP-5（キャッシュ）の E2E は「2 回目の検索でスタブへのリクエストが増えないこと」をこの値で
// 検証する（プレビュー環境の `X-Cache-Status` ヘッダはローカル Node サーバーには出ないため代替する・
// `user-story-map.md` §5.3 SP-5）。
import { readFileSync } from 'node:fs'
import http from 'node:http'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const fixturesDir = path.join(__dirname, '..', 'fixtures')

function readJson(name) {
  return JSON.parse(readFileSync(path.join(fixturesDir, name), 'utf8'))
}

const repos = readJson('repos.json')
const PAGE_1_REPOS = repos.slice(0, 3)
const PAGE_2_REPOS = repos.slice(3, 5)
// 30 件/ページ（PER_PAGE）に対して 2 ページ目が存在することを示すためだけの値。
// items の実件数（フィクスチャは 3 + 2 件）と一致させる必要はない（実 API も total_count と
// items.length は 1 ページ分では一致しない）。
const TOTAL_COUNT = 33

// SP-7 E2E 専用: `q` に `many-hits` を含む検索でのみ使う 60 件データセット
// （`e2e/sp-7.spec.ts`）。挿入順（relevance）と star 降順が一致しないよう
// `stargazers_count = n * 7`（昇順）で生成し、並び替えが実際に効いたことを
// 「先頭要素が変わる」で検証できるようにする。60 件 × per_page(20/50) で
// 複数ページに分かれるようにし、page / per_page / sort をスタブが実際に反映する。
const MANY_HITS_MARKER = 'many-hits'
const MANY_TOTAL = 60
const manyRepos = Array.from({ length: MANY_TOTAL }, (_, idx) => {
  const n = idx + 1
  const seq = String(n).padStart(2, '0')
  const day = String((n % 28) + 1).padStart(2, '0')
  return {
    id: 901000 + n,
    name: `many-${seq}`,
    full_name: `octostub/many-${seq}`,
    html_url: `https://github.com/octostub/many-${seq}`,
    description: null,
    language: null,
    stargazers_count: n * 7,
    // 詳細 API（repositoryDetailDto）が要求するフィールド（検索結果 DTO には出さない・toSearchItem で射影済み）
    watchers_count: n * 7,
    subscribers_count: n,
    forks_count: Math.max(1, Math.floor(n / 2)),
    open_issues_count: n % 5,
    updated_at: `2026-01-${day}T00:00:00Z`,
    pushed_at: `2026-01-${day}T00:00:00Z`,
    private: false,
    topics: [],
    owner: {
      login: 'octostub',
      avatar_url:
        'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
    },
  }
})

// AC-12 E2E 専用: `q` に `private-mixed` を含む検索でのみ使うデータセット
// （`e2e/ac-12-private.spec.ts`）。GitHub App の installation token を使うと、
// `is:public` が効かなくなった場合に private リポジトリが検索応答へ混ざりうる。その状況を
// スタブ側で再現し、アプリの多層防御（mapper での除外・詳細の 404 化）が効くことを確認する。
// `total_count` は上流が返した値（2）のまま画面に出る（フィルタで書き換えない契約の確認用）。
const PRIVATE_MIXED_MARKER = 'private-mixed'
const PRIVATE_MIXED_AVATAR =
  'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='

function privateMixedRepo({ id, name, isPrivate, description }) {
  return {
    id,
    name,
    full_name: `octostub/${name}`,
    html_url: `https://github.com/octostub/${name}`,
    description,
    language: 'TypeScript',
    stargazers_count: 12,
    watchers_count: 12,
    subscribers_count: 3,
    forks_count: 1,
    open_issues_count: 0,
    updated_at: '2026-08-01T00:00:00Z',
    pushed_at: '2026-08-01T00:00:00Z',
    private: isPrivate,
    topics: [],
    owner: { login: 'octostub', avatar_url: PRIVATE_MIXED_AVATAR },
  }
}

const privateMixedRepos = [
  privateMixedRepo({
    id: 950001,
    name: 'octo-public-sample',
    isPrivate: false,
    description: 'Public repository used by the AC-12 E2E.',
  }),
  privateMixedRepo({
    id: 950002,
    name: 'octo-secret',
    isPrivate: true,
    description: 'PRIVATE-SECRET-DESCRIPTION',
  }),
]

/** `sort`（relevance/stars/updated）に従って並べ替える（実 API の挙動を模す）。 */
function sortManyRepos(list, sort) {
  if (sort === 'stars') {
    return [...list].sort((a, b) => b.stargazers_count - a.stargazers_count)
  }
  if (sort === 'updated') {
    return [...list].sort(
      (a, b) => new Date(b.pushed_at).getTime() - new Date(a.pushed_at).getTime(),
    )
  }
  return list // relevance: 挿入順のまま
}

const PORT = Number(process.env.E2E_STUB_PORT ?? 8788)

// SP-5 E2E 検証用のリクエストカウント（`/__stats` / `/__stats/reset` でのみ参照・更新する）。
// `lastSearchQuery` は AC-12 E2E 用（アプリが GitHub へ送った `q` に `is:public` が
// 含まれていることを画面越しに確認するため）。
const stats = { searchCount: 0, detailCount: 0, lastSearchQuery: null }

function toSearchItem(repo) {
  const {
    id,
    name,
    full_name,
    html_url,
    description,
    language,
    stargazers_count,
    updated_at,
    pushed_at,
    // 🔴 検索結果 DTO（src/infrastructure/github/dto.ts）で必須。欠落は上流異常として倒れる
    private: isPrivate,
    topics,
    owner,
  } = repo
  return {
    id,
    name,
    full_name,
    html_url,
    description,
    language,
    stargazers_count,
    updated_at,
    pushed_at,
    private: isPrivate,
    topics,
    owner,
  }
}

function searchResponse(items) {
  return { total_count: TOTAL_COUNT, incomplete_results: false, items: items.map(toSearchItem) }
}

function sendJson(res, status, body, headers = {}) {
  const payload = JSON.stringify(body)
  res.writeHead(status, { 'content-type': 'application/json; charset=utf-8', ...headers })
  res.end(payload)
}

function rateLimitBody() {
  const resetAt = Math.floor(Date.now() / 1000) + 60
  return [
    { message: 'stub: rate limit exceeded' },
    { 'x-ratelimit-remaining': '0', 'x-ratelimit-reset': String(resetAt) },
  ]
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url ?? '/', `http://127.0.0.1:${PORT}`)

  // 統計エンドポイント（GitHub API には存在しない裏口・method チェックの対象外）
  if (url.pathname === '/__stats' && req.method === 'GET') {
    return sendJson(res, 200, stats)
  }
  if (url.pathname === '/__stats/reset' && req.method === 'POST') {
    stats.searchCount = 0
    stats.detailCount = 0
    stats.lastSearchQuery = null
    return sendJson(res, 200, stats)
  }

  if (req.method !== 'GET') {
    return sendJson(res, 405, { message: 'stub: method not allowed' })
  }

  if (url.pathname === '/search/repositories') {
    stats.searchCount += 1
    const q = url.searchParams.get('q') ?? ''
    stats.lastSearchQuery = q
    const page = url.searchParams.get('page') ?? '1'

    if (q.includes('zero-hits')) {
      return sendJson(res, 200, { total_count: 0, incomplete_results: false, items: [] })
    }
    if (q.includes('upstream-error')) {
      return sendJson(res, 500, { message: 'stub: upstream error' })
    }
    if (q.includes('rate-limit')) {
      const [body, headers] = rateLimitBody()
      return sendJson(res, 403, body, headers)
    }

    if (q.includes(PRIVATE_MIXED_MARKER)) {
      return sendJson(res, 200, {
        total_count: privateMixedRepos.length,
        incomplete_results: false,
        items: privateMixedRepos.map(toSearchItem),
      })
    }

    if (q.includes(MANY_HITS_MARKER)) {
      const pageNum = Math.max(1, Number.parseInt(page, 10) || 1)
      const perPage = Math.max(
        1,
        Number.parseInt(url.searchParams.get('per_page') ?? '20', 10) || 20,
      )
      const sort = url.searchParams.get('sort')
      const sorted = sortManyRepos(manyRepos, sort)
      const start = (pageNum - 1) * perPage
      const items = sorted.slice(start, start + perPage)
      return sendJson(res, 200, {
        total_count: manyRepos.length,
        incomplete_results: false,
        items: items.map(toSearchItem),
      })
    }

    const items = page === '2' ? PAGE_2_REPOS : PAGE_1_REPOS
    return sendJson(res, 200, searchResponse(items))
  }

  const detailMatch = url.pathname.match(/^\/repos\/([^/]+)\/([^/]+)$/)
  if (detailMatch) {
    stats.detailCount += 1
    const [, owner, repoName] = detailMatch

    if (repoName.includes('not-found') || owner.includes('not-found')) {
      return sendJson(res, 404, { message: 'stub: Not Found' })
    }
    if (repoName.includes('upstream-error')) {
      return sendJson(res, 500, { message: 'stub: upstream error' })
    }
    if (repoName.includes('rate-limit')) {
      const [body, headers] = rateLimitBody()
      return sendJson(res, 403, body, headers)
    }

    const found =
      repos.find((repo) => repo.owner.login === owner && repo.name === repoName) ??
      manyRepos.find((repo) => repo.owner.login === owner && repo.name === repoName) ??
      // AC-12: private リポジトリも上流は 200 で返す（「見つからない」に倒すのはアプリ側の責務）
      privateMixedRepos.find((repo) => repo.owner.login === owner && repo.name === repoName)
    if (!found) {
      return sendJson(res, 404, { message: 'stub: Not Found (no fixture for this owner/repo)' })
    }
    return sendJson(res, 200, found)
  }

  sendJson(res, 404, { message: `stub: unknown route ${url.pathname}` })
})

server.listen(PORT, () => {
  console.log(`[e2e-stub] listening on http://127.0.0.1:${PORT}`)
})
