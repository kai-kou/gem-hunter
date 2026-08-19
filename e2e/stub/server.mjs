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

const PORT = Number(process.env.E2E_STUB_PORT ?? 8788)

// SP-5 E2E 検証用のリクエストカウント（`/__stats` / `/__stats/reset` でのみ参照・更新する）。
const stats = { searchCount: 0, detailCount: 0 }

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
    topics,
    owner,
  } = repo
  return { id, name, full_name, html_url, description, language, stargazers_count, updated_at, topics, owner }
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
    return sendJson(res, 200, stats)
  }

  if (req.method !== 'GET') {
    return sendJson(res, 405, { message: 'stub: method not allowed' })
  }

  if (url.pathname === '/search/repositories') {
    stats.searchCount += 1
    const q = url.searchParams.get('q') ?? ''
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

    const found = repos.find((repo) => repo.owner.login === owner && repo.name === repoName)
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
