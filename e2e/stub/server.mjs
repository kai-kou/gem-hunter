// E2E 用スタブ GitHub API サーバー（node:http のみ・外部依存を足さない）。
// 固定データは ../fixtures/*.json を読むだけで、ここでは配信のためのごく薄い整形（フィールド射影・
// ページ分割・キーワード分岐）しか行わない。
//
// ルーティング:
//   GET /search/repositories?q=&page=&per_page=
//   GET /repos/{owner}/{repo}
//   GET  /__stats        （SP-5 E2E 検証専用・実 GitHub API には存在しない裏口）
//   POST /__stats/reset   同上
//   GET  /login/oauth/authorize?client_id=&redirect_uri=&state=   （SP-8 OAuth モック）
//   POST /login/oauth/access_token                                 同上
//   GET  /user                                                      同上（AuthPort からは未使用）
//
// キーワード規約（q または repo 名に部分一致で判定）:
//   通常のキーワード      → 複数件の結果（total_count は 2 ページ以上になる値）
//   zero-hits を含む      → total_count: 0 / items: []
//   upstream-error を含む → HTTP 500
//   rate-limit を含む     → HTTP 403 + x-ratelimit-remaining: 0 + x-ratelimit-reset
//   not-found を含む（repo 名 or owner）→ HTTP 404（詳細 API のみ）
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
    topics: [],
    owner: {
      login: 'octostub',
      avatar_url:
        'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
    },
  }
})

/** `sort`（relevance/stars/updated）に従って並べ替える（実 API の挙動を模す）。 */
function sortManyRepos(list, sort) {
  if (sort === 'stars') {
    return [...list].sort((a, b) => b.stargazers_count - a.stargazers_count)
  }
  if (sort === 'updated') {
    return [...list].sort((a, b) => new Date(b.pushed_at).getTime() - new Date(a.pushed_at).getTime())
  }
  return list // relevance: 挿入順のまま
}

const PORT = Number(process.env.E2E_STUB_PORT ?? 8788)

// SP-8: OAuth token 交換が返す固定アクセストークン。実 GitHub と同様この値を
// `Authorization: Bearer <token>` で送ってきたリクエストだけを「ユーザー自身のレート枠」と
// みなす（`userAuthSearchCount` / `userAuthDetailCount`）。未ログイン時も installation token の
// Authorization ヘッダが既に付いていることがあるため、「値の一致」で判定する
// （whiteboard `sp8-auth-i18n-20260819` 争点 D round2 決定）。
const OAUTH_ACCESS_TOKEN = 'stub-access-token'
const OAUTH_AUTHZ_CODE = 'stub-authz-code'
const OAUTH_USER_AUTH_HEADER = `Bearer ${OAUTH_ACCESS_TOKEN}`

// SP-5 / SP-8 E2E 検証用のリクエストカウント（`/__stats` / `/__stats/reset` でのみ参照・更新する）。
const stats = { searchCount: 0, detailCount: 0, userAuthSearchCount: 0, userAuthDetailCount: 0 }

function isUserAuthRequest(req) {
  return req.headers.authorization === OAUTH_USER_AUTH_HEADER
}

/** リクエストボディを読み切る（`node:http` は自動でバッファしない）。 */
function readRequestBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = []
    req.on('data', (chunk) => chunks.push(chunk))
    req.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')))
    req.on('error', reject)
  })
}

/** `POST /login/oauth/access_token` は form-urlencoded / JSON のどちらでも受け付ける。 */
function parseAccessTokenRequestBody(contentType, raw) {
  if (contentType && contentType.includes('application/json')) {
    try {
      return JSON.parse(raw || '{}')
    } catch {
      return {}
    }
  }
  return Object.fromEntries(new URLSearchParams(raw))
}

async function handleAccessTokenExchange(req, res) {
  const raw = await readRequestBody(req)
  const body = parseAccessTokenRequestBody(req.headers['content-type'], raw)

  if (!body.code) {
    return sendJson(res, 400, { error: 'bad_verification_code' })
  }
  return sendJson(res, 200, { access_token: OAUTH_ACCESS_TOKEN, token_type: 'bearer', scope: '' })
}

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
    stats.userAuthSearchCount = 0
    stats.userAuthDetailCount = 0
    return sendJson(res, 200, stats)
  }

  // SP-8: OAuth token 交換（POST）。405 判定より前に置く（実装漏れると全 OAuth E2E が 405 で落ちる）。
  if (url.pathname === '/login/oauth/access_token' && req.method === 'POST') {
    return handleAccessTokenExchange(req, res)
  }

  if (req.method !== 'GET') {
    return sendJson(res, 405, { message: 'stub: method not allowed' })
  }

  // SP-8: OAuth authorize。同意済みユーザーとして即座に 302 で redirect_uri へ返す
  // （stub はレジストリを持たないため client_id/redirect_uri の値検証はしない）。
  if (url.pathname === '/login/oauth/authorize') {
    const state = url.searchParams.get('state') ?? ''
    const redirectUri = url.searchParams.get('redirect_uri')
    if (!redirectUri) {
      return sendJson(res, 400, { message: 'stub: redirect_uri is required' })
    }
    const location = new URL(redirectUri)
    location.searchParams.set('code', OAUTH_AUTHZ_CODE)
    location.searchParams.set('state', state)
    res.writeHead(302, { location: location.toString() })
    return res.end()
  }

  // SP-8: `/user`（実装だけ用意する。AuthPort からは呼ばれない・将来の fetchViewer 拡張に備える）。
  if (url.pathname === '/user') {
    const auth = req.headers.authorization ?? ''
    if (auth === OAUTH_USER_AUTH_HEADER || auth === `token ${OAUTH_ACCESS_TOKEN}`) {
      return sendJson(res, 200, {
        login: 'octostub-user',
        id: 999001,
        avatar_url:
          'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
      })
    }
    return sendJson(res, 401, { message: 'stub: Unauthorized' })
  }

  if (url.pathname === '/search/repositories') {
    stats.searchCount += 1
    if (isUserAuthRequest(req)) {
      stats.userAuthSearchCount += 1
    }
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

    if (q.includes(MANY_HITS_MARKER)) {
      const pageNum = Math.max(1, Number.parseInt(page, 10) || 1)
      const perPage = Math.max(1, Number.parseInt(url.searchParams.get('per_page') ?? '20', 10) || 20)
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
    if (isUserAuthRequest(req)) {
      stats.userAuthDetailCount += 1
    }
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
      manyRepos.find((repo) => repo.owner.login === owner && repo.name === repoName)
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
