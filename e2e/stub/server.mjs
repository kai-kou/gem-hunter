// E2E 用スタブ GitHub API サーバー（node:http のみ・外部依存を足さない）。
// 固定データは ../fixtures/*.json を読むだけで、ここでは配信のためのごく薄い整形（フィールド射影・
// ページ分割・キーワード分岐）しか行わない。
//
// ルーティング:
//   GET /search/repositories?q=&page=&per_page=
//   GET /repos/{owner}/{repo}
//   GET /repos/{owner}/{repo}/readme   （Issue #334 F-4・Accept: application/vnd.github.html+json でレンダリング済み HTML を返す）
//   GET  /__stats        （SP-5 E2E 検証専用・実 GitHub API には存在しない裏口）
//   POST /__stats/reset   同上
//   GET  /login/oauth/authorize?client_id=&redirect_uri=&state=   （SP-8 OAuth モック）
//   POST /login/oauth/access_token                                 同上
//
// キーワード規約（q または repo 名に部分一致で判定）:
//   通常のキーワード      → 複数件の結果（total_count は 2 ページ以上になる値）
//   zero-hits を含む      → total_count: 0 / items: []
//   upstream-error を含む → HTTP 500
//   rate-limit を含む     → HTTP 403 + x-ratelimit-remaining: 0 + x-ratelimit-reset
//   not-found を含む（repo 名 or owner）→ HTTP 404（詳細 API のみ）
//   sp9-network-down を含む       → 応答を書かずに接続を切る（fetch 自体の失敗＝到達不可を再現）
//   sp9-secondary-rate-limit を含む → HTTP 403 + retry-after（二次レート制限）
//   sp9-slow を含む                → 1.5 秒待ってから通常の結果（読み込み中表示の観測用）
//   sp9-forbidden を含む           → HTTP 403 + x-ratelimit-remaining: 42（レート制限でない 403 = auth）
//   readme-missing を含む（repo 名）→ README エンドポイントのみ HTTP 404（README 不在の再現。詳細本体は 200 のまま）
//   readme-rich を含む（repo 名）    → Issue #339（README の書式反映）E2E 専用。書式要素
//                             （見出し・段落・ネストした箇条書き・番号付きリスト・引用・列が多く
//                             横に長い表・長い行を含むコードブロック・インラインコード・長い URL・
//                             バッジ画像。バッジは data: URI 固定で外部ネットワークに依存しない）
//                             を網羅した README HTML を返す（`octostub/octo-readme-rich`）
//   private-mixed を含む  → AC-12 E2E 専用。上流が is:public を無視して private を混ぜて返す状況を
//                             再現する（public 1 件 + private 1 件・total_count は 2）。
//                             `octostub/octo-secret` の詳細も 200 + `private: true` で返す
//   many-hits を含む       → SP-7（ページネーション・並び替え・表示件数）E2E 専用の 60 件
//                             データセット。実 API と同様に `page` / `per_page` / `sort` を
//                             実際に反映して切り出す（他キーワードは PAGE_1_REPOS/PAGE_2_REPOS
//                             固定・既存 E2E への影響を避けるため分離）。
//   gem-badge を含む       → SP-18（Gem バッジ）E2E 専用の 2 件データセット。1 件目は候補プールに
//                             載っていない `octostub/not-a-gem`（バッジなし）、2 件目は
//                             `public/data/gem-index/` の実在プールから取り出したリポジトリ
//                             （バッジあり）。返却順は「バッジなし → バッジあり」に固定し、
//                             バッジが並び替えに使われていないこと（`D-36`）を検証できるようにする。
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

// SP-9 E2E 専用マーカー（`e2e/sp-9-*.spec.ts`）。`prd.md` §7 の種別判別を画面越しに確認するため、
// 「fetch 自体の失敗」「二次レート制限」「遅い応答」をスタブ側で再現する（NFR-24: 外部 API はモック化）。
// 🔴 `sp9-secondary-rate-limit` は既存マーカー `rate-limit` を部分文字列として含むため、
//    ハンドラ内では **既存の `rate-limit` 判定より前** に評価すること。
const SP9_NETWORK_DOWN_MARKER = 'sp9-network-down'
const SP9_SECONDARY_RATE_LIMIT_MARKER = 'sp9-secondary-rate-limit'
const SP9_SLOW_MARKER = 'sp9-slow'
/**
 * レート制限ではない 403（`x-ratelimit-remaining` が残っていて `retry-after` も無い）。
 * `prd.md` §7 の判別順序で `auth` に落ちる経路を画面越しに確認するために使う。
 */
const SP9_FORBIDDEN_MARKER = 'sp9-forbidden'
/** 読み込み中表示（US-22）を E2E から観測できる長さ。長すぎると 60 秒のテスト時間を圧迫する。 */
const SP9_SLOW_DELAY_MS = 1500

// E2E フィクスチャの画像は外部ネットワークに依存させないため、実体を持たない 1x1 透明 PNG の
// data URI に統一する。描画サイズは呼び出し側の `<img>` が持つ width/height 属性で決まるため、
// アバターでもバッジでも実ピクセルが 1x1 のままで用途ごとの見た目を再現できる。
// 用途別の定数（PRIVATE_MIXED_AVATAR / GEM_BADGE_AVATAR / README_BADGE_IMAGE）は全てこれを参照し、
// 同じ base64 文字列を複数箇所に重複定義しない（1 か所を差し替えれば全用途に伝播する誤りを防ぐため、
// 用途ごとに独立した定数として持たせたうえで実体だけをここに一本化している）。
const TRANSPARENT_1PX_PNG =
  'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='

// AC-12 E2E 専用: `q` に `private-mixed` を含む検索でのみ使うデータセット
// （`e2e/ac-12-private.spec.ts`）。GitHub App の installation token を使うと、
// `is:public` が効かなくなった場合に private リポジトリが検索応答へ混ざりうる。その状況を
// スタブ側で再現し、アプリの多層防御（mapper での除外・詳細の 404 化）が効くことを確認する。
// `total_count` は上流が返した値（2）のまま画面に出る（フィルタで書き換えない契約の確認用）。
const PRIVATE_MIXED_MARKER = 'private-mixed'
const PRIVATE_MIXED_AVATAR = TRANSPARENT_1PX_PNG

// readmeRichHtml() のバッジ画像用。実体は TRANSPARENT_1PX_PNG（共有定数）を参照するため、
// PRIVATE_MIXED_AVATAR / GEM_BADGE_AVATAR とは独立した定数でありながら重複定義は増えない。
// バッジは <img> の width/height 属性で 120×20・98×20 の描画サイズが確定するため、
// 実ピクセルが 1x1 でも横長要素としてのレイアウト検証は成立する。
const README_BADGE_IMAGE = TRANSPARENT_1PX_PNG

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

// Issue #334 F-4 E2E 専用: README の有無を再現するための追加リポジトリ（既存 repos.json は変更しない・
// `e2e/feedback-334.spec.ts` からのみ使う）。詳細本体（/repos/{owner}/{repo}）は 200 を返しつつ、
// README エンドポイントだけを 404 にすることで「README 不在」の代替表示を検証できるようにする。
const README_MISSING_MARKER = 'readme-missing'
const readmeExtraRepos = [
  {
    id: 960001,
    name: 'octo-readme-missing',
    full_name: 'octostub/octo-readme-missing',
    html_url: 'https://github.com/octostub/octo-readme-missing',
    description: 'Repository without a README (Issue #334 F-4 E2E).',
    language: 'TypeScript',
    stargazers_count: 5,
    watchers_count: 5,
    subscribers_count: 2,
    forks_count: 1,
    open_issues_count: 0,
    updated_at: '2026-08-01T00:00:00Z',
    pushed_at: '2026-08-01T00:00:00Z',
    private: false,
    topics: [],
    owner: {
      login: 'octostub',
      avatar_url:
        'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
    },
  },
]

// Issue #339 E2E 専用: 書式要素を網羅したリッチな README を返すための追加リポジトリ
// （`e2e/readme-typography.spec.ts` からのみ使う）。詳細本体は他の追加リポジトリと同じ最小限の
// フィールドを持ち、README エンドポイントだけが `readmeRichHtml()` の生成物を返す。
const README_RICH_MARKER = 'readme-rich'
const readmeRichExtraRepos = [
  {
    id: 960002,
    name: 'octo-readme-rich',
    full_name: 'octostub/octo-readme-rich',
    html_url: 'https://github.com/octostub/octo-readme-rich',
    description: 'Repository with a formatting-rich README (Issue #339 E2E).',
    language: 'TypeScript',
    stargazers_count: 8,
    watchers_count: 8,
    subscribers_count: 3,
    forks_count: 2,
    open_issues_count: 0,
    updated_at: '2026-08-20T00:00:00Z',
    pushed_at: '2026-08-20T00:00:00Z',
    private: false,
    topics: [],
    owner: {
      login: 'octostub',
      avatar_url:
        'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
    },
  },
]

/**
 * Issue #339 E2E 専用: 書式要素を網羅した README HTML を返す（GitHub の README エンドポイント
 * が返す「レンダリング済み HTML 断片」を模す）。`readme-html.ts` が許可しているタグのみを使う
 * （`h1`〜`h4` は見出し降格変換で `h3`〜`h6` になる・`ALLOWED_TAGS` を超えるタグは使わない）。
 *
 * 意図的に含めた要素:
 *   - h1 / h2（+2 降格後の h3 が本文 p より大きく、ページの h2「README」を超えないことの検証用）
 *   - h3 / h4（+2 降格後の h5 / h6・見出しレベル間の単調減少を検証するため。Layer 1 指摘対応で
 *     追加。これが無いと raw README は h1/h2 しか持たず、レンダリング後も h3/h4 しか出現しないため
 *     h5/h6 のスケール退行を検知できなかった）
 *   - インラインコード（`<code>`）と段落
 *   - ネストした箇条書き（`<ul>` の入れ子・リストマーカーとインデントの検証用）
 *   - 番号付きリスト（`<ol>`）
 *   - 引用（`<blockquote>`）
 *   - 列数が多く横に長い `<table>`（コンテナの overflow-x:auto 検証用）。セルにリンクと
 *     `<strong>` を含める（Layer 1 指摘対応。--tw-prose-links / --tw-prose-th-borders /
 *     --tw-prose-td-borders が実際の表の文脈で描画されることを検証するため）
 *   - 長い 1 行を含む `<pre><code>`（コードブロックの背景色・横スクロール検証用）
 *   - 折り返されない長い URL（body に横スクロールが出ないことの検証用）
 *   - バッジ画像（`<img>` 複数・`max-width: 100%` で崩れないことの検証用）
 */
function readmeRichHtml(owner, repoName) {
  return (
    '<article>' +
    `<h1>${repoName} book format demo</h1>` +
    '<p>This README exercises every prose element the sanitizer allows, ' +
    'so the readme-typography E2E can assert computed styles instead of class names alone.</p>' +
    '<h2>Getting started</h2>' +
    '<p>Install the package and read the <code>CHANGELOG.md</code> before upgrading. ' +
    'Inline <code>code spans</code> should render monospace without a block background.</p>' +
    // Layer 1 指摘対応（CRITICAL）: raw h3/h4（+2 シフト後は h5/h6）を持つ見出しがフィクスチャに
    // 無かったため、見出しレベル間の単調減少を E2E で検証できなかった。raw h1〜h4 の 4 段を
    // 揃えることで、レンダリング後の h3/h4/h5/h6 が隣接して現れるようにする。
    '<h3>Advanced configuration</h3>' +
    '<p>Optional settings for advanced users who need finer control over the client.</p>' +
    '<h4>Debug flags</h4>' +
    '<p>Set <code>DEBUG=1</code> to enable verbose logging output.</p>' +
    '<h2>Nested feature list</h2>' +
    '<ul>' +
    '<li>Top-level feature' +
    '<ul>' +
    '<li>Nested detail one</li>' +
    '<li>Nested detail two' +
    '<ul><li>Deeply nested detail</li></ul>' +
    '</li>' +
    '</ul>' +
    '</li>' +
    '<li>Second top-level feature</li>' +
    '</ul>' +
    '<h2>Install steps</h2>' +
    '<ol>' +
    '<li>Clone the repository</li>' +
    '<li>Run <code>npm install</code></li>' +
    '<li>Run <code>npm run build</code></li>' +
    '</ol>' +
    '<blockquote><p>Note: this project targets Node 20 or later and is tested ' +
    'against the latest two LTS releases.</p></blockquote>' +
    '<h2>Benchmark matrix</h2>' +
    '<table>' +
    '<thead><tr>' +
    '<th>Runtime</th><th>OS</th><th>Node</th><th>Build time (ms)</th>' +
    '<th>Bundle size (KB)</th><th>Gzip size (KB)</th><th>Lighthouse score</th><th>Notes</th>' +
    '</tr></thead>' +
    '<tbody>' +
    // Layer 1 指摘対応（WARNING）: 表のセルが plain text のみだったため、リンク（--tw-prose-links）
    // や強調（<strong>）が README 内の表という現実的な文脈で描画されることを検証できなかった。
    '<tr><td>Cloudflare Workers</td><td>linux</td><td>20.x</td><td>842</td>' +
    '<td>1372</td><td>412</td><td>100</td><td><strong>baseline</strong> configuration</td></tr>' +
    '<tr><td>Node.js server</td><td>linux</td><td>22.x</td><td>910</td>' +
    '<td>1420</td><td>430</td><td>98</td>' +
    '<td>with source maps enabled (see <a href="https://github.com/octostub/octo-readme-rich/' +
    'blob/main/docs/build.md">build docs</a>)</td></tr>' +
    '</tbody>' +
    '</table>' +
    '<h2>Example usage</h2>' +
    "<pre><code>import { createClient } from 'octo-readme-rich'\n\n" +
    'const client = createClient({ token: process.env.OCTO_TOKEN, ' +
    "baseUrl: 'https://api.example.com/v1/octo-readme-rich/really/long/endpoint/path/" +
    "that/keeps/going/and/going/without/ever/wrapping/to/the/next/line' })\n" +
    "const result = await client.search({ query: 'gem-hunter', perPage: 50, sort: 'stars' })\n" +
    "console.log(result.items.map((item) =&gt; item.fullName).join(', '))</code></pre>" +
    '<p>Full docs: <a href="https://github.com/octostub/octo-readme-rich/blob/main/docs/' +
    'very/long/nested/path/that/should/not/force/horizontal/scroll/on/the/page/README.md">' +
    'https://github.com/octostub/octo-readme-rich/blob/main/docs/very/long/nested/path/' +
    'that/should/not/force/horizontal/scroll/on/the/page/README.md</a></p>' +
    '<p>' +
    // 🔴 外部 URL（img.shields.io 等）を画像 src に置かない: テスト用 Chromium からは到達不可のため
    // page.goto() が 1 リクエストあたり約 12.6 秒ブロックする（`readme-typography` / `a11y` の
    // README 系テストで実測・NFR-24 違反）。data: URI に固定してネットワークを完全に遮断する。
    `<img src="${README_BADGE_IMAGE}" alt="Build status badge" width="120" height="20" /> ` +
    `<img src="${README_BADGE_IMAGE}" alt="License badge" width="98" height="20" />` +
    '</p>' +
    '</article>'
  )
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

// SP-18 E2E 専用: `q` に `gem-badge` を含む検索でのみ使う 2 件データセット
// （`e2e/sp-18.spec.ts`）。Gem バッジは「候補プール（`public/data/gem-index/`）に載っているか」
// だけで決まるため、架空の `octostub/*` しか返さない既存データセットではバッジ経路を 1 度も
// 通せなかった。そこで **プール実在のリポジトリ 1 件 + 非実在 1 件** を返し、
// 「一部のカードにだけバッジが出る」（`user-story-map.md` §5.3 `SP-18` 手順 2）を検証可能にする。
//
// 🔴 **プール側のリポジトリ名をハードコードしない**。候補プールは定期再生成されるため、
//    名前を固定すると将来のプール更新でテストが落ちる。起動時に `index.json` →
//    `shards[0].fileName` → そのシャードの `entries[0]` から `repositoryFullName` を引く
//    （`columns` の位置は決め打ちしない・`static-gem-index.ts` と同じ作法）。
// 🔴 **読み込みに失敗してもスタブ起動は失敗させない**（他の spec を巻き添えにしない）。
//    その場合は 1 件だけ返し、`console.warn` で理由を出す。テスト側は「2 件返ること」を
//    `expect` して失敗する（静かに素通りさせない）。
const GEM_BADGE_MARKER = 'gem-badge'
const GEM_BADGE_AVATAR = TRANSPARENT_1PX_PNG
const gemIndexDir = path.join(__dirname, '..', '..', 'public', 'data', 'gem-index')

/**
 * 候補プールの先頭リポジトリ（`owner/repo`）を返す。読めなければ `null`。
 * `static-gem-index.ts` と同じく `columns.indexOf('repositoryFullName')` で列位置を引く。
 */
function readFirstPoolRepositoryFullName() {
  try {
    const index = JSON.parse(readFileSync(path.join(gemIndexDir, 'index.json'), 'utf8'))
    const fileName = Array.isArray(index?.shards) ? index.shards[0]?.fileName : undefined
    if (typeof fileName !== 'string' || fileName.length === 0) {
      throw new Error('index.json の shards[0].fileName が読めない')
    }
    const shard = JSON.parse(readFileSync(path.join(gemIndexDir, fileName), 'utf8'))
    const nameIndex = Array.isArray(shard?.columns)
      ? shard.columns.indexOf('repositoryFullName')
      : -1
    if (nameIndex < 0) {
      throw new Error(`${fileName} の columns に repositoryFullName が無い`)
    }
    const entry = Array.isArray(shard?.entries) ? shard.entries[0] : undefined
    const fullName = Array.isArray(entry) ? entry[nameIndex] : undefined
    if (typeof fullName !== 'string' || !fullName.includes('/')) {
      throw new Error(`${fileName} の entries[0] から repositoryFullName を取り出せない`)
    }
    return fullName
  } catch (error) {
    console.warn(
      `[e2e-stub] 候補プールの先頭リポジトリを読めませんでした（gem-badge データセットは 1 件のみ）: ${
        error instanceof Error ? error.message : String(error)
      }`,
    )
    return null
  }
}

/** `owner/repo` から詳細 API でもそのまま返せる 1 件を組み立てる（既存データセットと同じ形）。 */
function gemBadgeRepo({ id, fullName, description }) {
  const [login, name] = fullName.split('/')
  return {
    id,
    name,
    full_name: fullName,
    html_url: `https://github.com/${fullName}`,
    description,
    language: 'TypeScript',
    stargazers_count: 7,
    watchers_count: 7,
    subscribers_count: 2,
    forks_count: 1,
    open_issues_count: 0,
    updated_at: '2026-08-01T00:00:00Z',
    pushed_at: '2026-08-01T00:00:00Z',
    private: false,
    topics: [],
    owner: { login, avatar_url: GEM_BADGE_AVATAR },
  }
}

const gemBadgePoolFullName = readFirstPoolRepositoryFullName()
// 🔴 返却順は「バッジなし → バッジあり」。バッジ付きが先頭へ繰り上がっていないことを
//    テストが検出できるようにするため（バッジは注釈であって並び替え軸ではない・`D-36`）。
const gemBadgeRepos = [
  gemBadgeRepo({
    id: 970001,
    fullName: 'octostub/not-a-gem',
    description: 'Repository absent from the Gem candidate pool (SP-18 E2E).',
  }),
  ...(gemBadgePoolFullName === null
    ? []
    : [
        gemBadgeRepo({
          id: 970002,
          fullName: gemBadgePoolFullName,
          description: 'Repository present in the Gem candidate pool (SP-18 E2E).',
        }),
      ]),
]

// 横スクロール退行ガード専用データセット（`e2e/overflow-guard.spec.ts`）。
//
// 🔴 既存 5 データセットが今回の退行（第三者テキストが折り返されず body に横スクロールが出る）を
//    検知できなかった原因は述語ではなく **データ** にある: 既定フィクスチャの文字列はどれも短く、
//    空白やハイフンで改行機会が入るため、折り返し指定が無くてもたまたま収まっていた。
//    ここでは「改行機会がゼロの連続長文字列」を 3 種類（description の URL / 単一 topic /
//    リポジトリ名）そろえて、320px 幅で必ず溢れる入力を用意する。
// 🔴 マーカーは既存マーカーのいずれとも部分一致しない（`rate-limit` 等を含まない）。
const OVERFLOW_GUARD_MARKER = 'overflow-guard'
const OVERFLOW_GUARD_AVATAR =
  'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='

/**
 * 実運用で観測された破綻パターンをそのまま写した description。
 * 末尾の YouTube チャンネル URL は空白・ハイフンを含まない連続 60 字超で、
 * `overflow-wrap` の既定（`normal`）では 1 文字も割れない。
 */
const OVERFLOW_GUARD_LONG_URL_DESCRIPTION =
  '30 Days of React challenge is a step by step guide to learn React in 30 days. ' +
  'These videos may help too: https://www.youtube.com/channel/UC7PNRuno1rzYPb1xQEDDNBgAAAAAAAA'

/** GitHub の topic は空白なしの単一トークンで最大 50 文字まで許容される（改行機会ゼロ）。 */
const OVERFLOW_GUARD_LONG_TOPIC = 'a'.repeat(50)

function overflowGuardRepo({ id, name, description, topics }) {
  return {
    id,
    name,
    full_name: `octostub/${name}`,
    html_url: `https://github.com/octostub/${name}`,
    description,
    language: 'JavaScript',
    stargazers_count: 27475,
    watchers_count: 27475,
    subscribers_count: 900,
    forks_count: 6000,
    open_issues_count: 3,
    updated_at: '2026-08-01T00:00:00Z',
    pushed_at: '2026-08-01T00:00:00Z',
    private: false,
    topics,
    owner: { login: 'octostub', avatar_url: OVERFLOW_GUARD_AVATAR },
  }
}

const overflowGuardRepos = [
  // (a) description に改行機会ゼロの長い URL（本件の再現データ）。
  overflowGuardRepo({
    id: 980001,
    name: 'overflow-guard-description',
    description: OVERFLOW_GUARD_LONG_URL_DESCRIPTION,
    topics: [],
  }),
  // (b) 空白・ハイフンなしの長い単一 topic。topic の `<li>` は `ul.flex.flex-wrap` の
  //     flex アイテムなので、祖先から継承した `overflow-wrap: break-word` では
  //     automatic minimum size（自身の min-content）が floor として残り閉じない。
  overflowGuardRepo({
    id: 980002,
    name: 'overflow-guard-topic',
    description: 'Repository whose topic is a single unbreakable token (overflow guard E2E).',
    topics: [OVERFLOW_GUARD_LONG_TOPIC],
  }),
  // (c) リポジトリ名自体が長い連続文字列。
  overflowGuardRepo({
    id: 980003,
    name: `overflow-guard-${'n'.repeat(48)}`,
    description: 'Repository whose name is a single unbreakable token (overflow guard E2E).',
    topics: [],
  }),
]

// SP-19 E2E 追記: Gem 一覧（`/{locale}/gems`）から詳細へ入る経路を通せるようにする。
//
// Gem 一覧に並ぶのは **候補プール（`public/data/gem-index/`）の実在リポジトリ** であり、
// `octostub/*` のフィクスチャには 1 件も存在しない。そのため詳細 API がすべて 404 になり、
// `user-story-map.md` §5.3 `SP-19` 操作レビュー手順 4（一覧 → 詳細 → 戻る）を画面越しに
// なぞれなかった。そこで **既存フィクスチャを一切変えず**、どのフィクスチャにも該当しない
// owner/repo が候補プールに載っている場合にだけ、詳細 API が 200 を返すようにする。
//
// 🔴 既存の挙動を壊さない: この判定は既存 5 データセットの検索・詳細をすべて素通りした
//    最後のフォールバックで、しかも「プールに載っている名前」に限る（`octostub/*` は載らない）。
//    `not-found` / `upstream-error` / `rate-limit` の分岐はこれより前段にあるため影響しない。
// 🔴 読み込みに失敗しても起動は続ける（空 Set になり従来どおり 404 に倒れる）。
const gemPoolFullNames = readPoolRepositoryFullNames()

/** 候補プール全シャードの `repositoryFullName` を小文字で集めた Set（読めなければ空）。 */
function readPoolRepositoryFullNames() {
  const names = new Set()
  try {
    const index = JSON.parse(readFileSync(path.join(gemIndexDir, 'index.json'), 'utf8'))
    const shards = Array.isArray(index?.shards) ? index.shards : []
    for (const shard of shards) {
      const fileName = shard?.fileName
      if (typeof fileName !== 'string' || fileName.length === 0) continue
      const parsed = JSON.parse(readFileSync(path.join(gemIndexDir, fileName), 'utf8'))
      const nameIndex = Array.isArray(parsed?.columns)
        ? parsed.columns.indexOf('repositoryFullName')
        : -1
      if (nameIndex < 0 || !Array.isArray(parsed?.entries)) continue
      for (const entry of parsed.entries) {
        const fullName = Array.isArray(entry) ? entry[nameIndex] : undefined
        if (typeof fullName === 'string' && fullName.includes('/')) {
          names.add(fullName.toLowerCase())
        }
      }
    }
  } catch (error) {
    console.warn(
      `[e2e-stub] 候補プールの一覧を読めませんでした（Gem 一覧からの詳細遷移は 404 になります）: ${
        error instanceof Error ? error.message : String(error)
      }`,
    )
  }
  return names
}

/** 候補プール実在リポジトリの詳細（フィクスチャに無い owner/repo 用のフォールバック）。 */
function gemPoolRepo(owner, repoName) {
  return gemBadgeRepo({
    // フィクスチャの id 帯（90 万台）と衝突しない固定値。詳細画面は id を表示しない。
    id: 980001,
    fullName: `${owner}/${repoName}`,
    description: 'Repository present in the Gem candidate pool (SP-19 E2E fallback).',
  })
}

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

// SP-8: OAuth token 交換が返す固定アクセストークン。実 GitHub と同様この値を
// `Authorization: Bearer <token>` で送ってきたリクエストだけを「ユーザー自身のレート枠」と
// みなす（`userAuthSearchCount` / `userAuthDetailCount`）。未ログイン時も installation token の
// Authorization ヘッダが既に付いていることがあるため、「値の一致」で判定する
// （whiteboard `sp8-auth-i18n-20260819` 争点 D round2 決定）。
const OAUTH_ACCESS_TOKEN = 'stub-access-token'
const OAUTH_AUTHZ_CODE = 'stub-authz-code'
const OAUTH_USER_AUTH_HEADER = `Bearer ${OAUTH_ACCESS_TOKEN}`

// SP-5 / SP-8 E2E 検証用のリクエストカウント（`/__stats` / `/__stats/reset` でのみ参照・更新する）。
// `lastSearchQuery` は AC-12 E2E 用（アプリが GitHub へ送った `q` に `is:public` が
// 含まれていることを画面越しに確認するため）。
const stats = {
  searchCount: 0,
  detailCount: 0,
  userAuthSearchCount: 0,
  userAuthDetailCount: 0,
  lastSearchQuery: null,
}

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
    stats.userAuthSearchCount = 0
    stats.userAuthDetailCount = 0
    stats.lastSearchQuery = null
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

  if (url.pathname === '/search/repositories') {
    stats.searchCount += 1
    if (isUserAuthRequest(req)) {
      stats.userAuthSearchCount += 1
    }
    const q = url.searchParams.get('q') ?? ''
    stats.lastSearchQuery = q
    const page = url.searchParams.get('page') ?? '1'

    // SP-9: fetch 自体を失敗させる（到達不可の再現）。応答を書かずにソケットを切る。
    if (q.includes(SP9_NETWORK_DOWN_MARKER)) {
      req.socket.destroy()
      return
    }
    // SP-9: 二次レート制限（`retry-after` あり・`x-ratelimit-remaining` は出さない）。
    // 🔴 既存の `rate-limit` 判定より前に置く（部分一致で先に食われるため）。
    if (q.includes(SP9_SECONDARY_RATE_LIMIT_MARKER)) {
      return sendJson(res, 403, { message: 'stub: secondary rate limit' }, { 'retry-after': '30' })
    }
    // SP-9: レート制限ではない 403（枠は残っている）→ auth 種別。
    if (q.includes(SP9_FORBIDDEN_MARKER)) {
      return sendJson(res, 403, { message: 'stub: forbidden' }, { 'x-ratelimit-remaining': '42' })
    }
    // SP-9: 遅い応答（読み込み中表示の観測用）。
    // 🔴 テスト中断・ナビゲーション破棄でソケットが閉じた後に書き込むと
    //    `ERR_STREAM_WRITE_AFTER_END` でスタブプロセスごと落ち、後続の spec が全滅する。
    //    送信前に生存を確認し、切断時はタイマーを掃除する。
    if (q.includes(SP9_SLOW_MARKER)) {
      const timer = setTimeout(() => {
        if (res.writableEnded || res.destroyed) {
          return
        }
        sendJson(res, 200, searchResponse(PAGE_1_REPOS))
      }, SP9_SLOW_DELAY_MS)
      res.on('close', () => clearTimeout(timer))
      return
    }
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

    // SP-18: Gem バッジ経路（プール実在 1 件 + 非実在 1 件）。`page` / `sort` は反映しない
    // （本データセットは 1 ページに収まる 2 件しかないため）。
    if (q.includes(GEM_BADGE_MARKER)) {
      return sendJson(res, 200, {
        total_count: gemBadgeRepos.length,
        incomplete_results: false,
        items: gemBadgeRepos.map(toSearchItem),
      })
    }

    // 横スクロール退行ガード（`e2e/overflow-guard.spec.ts`）。3 件とも 1 ページに収まるため
    // `page` / `sort` は反映しない（`GEM_BADGE_MARKER` と同じ扱い）。
    if (q.includes(OVERFLOW_GUARD_MARKER)) {
      return sendJson(res, 200, {
        total_count: overflowGuardRepos.length,
        incomplete_results: false,
        items: overflowGuardRepos.map(toSearchItem),
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

  // Issue #334 F-4: README（GitHub がレンダリング済み HTML を返すエンドポイントを模す）。
  // `detailMatch` より前に置く（3 セグメントの path は 2 セグメント用の正規表現に一致しないため
  // 実害はないが、専用ルートであることを明示するため先に評価する）。
  const readmeMatch = url.pathname.match(/^\/repos\/([^/]+)\/([^/]+)\/readme$/)
  if (readmeMatch) {
    const [, owner, repoName] = readmeMatch
    if (
      repoName.includes(README_MISSING_MARKER) ||
      repoName.includes('not-found') ||
      owner.includes('not-found')
    ) {
      return sendJson(res, 404, { message: 'stub: Not Found' })
    }
    if (repoName.includes('upstream-error')) {
      return sendJson(res, 500, { message: 'stub: upstream error' })
    }
    // Issue #339: 書式要素を網羅したリッチな README（readme-typography E2E 専用）。
    // README_MISSING_MARKER 等より後・通常テンプレートより前に置く（部分一致で早取りされないため）。
    if (repoName.includes(README_RICH_MARKER)) {
      const richHtml = readmeRichHtml(owner, repoName)
      res.writeHead(200, { 'content-type': 'text/html; charset=utf-8' })
      return res.end(richHtml)
    }
    // 実 GitHub と同様に `Accept: application/vnd.github.html+json` で
    // 「そのまま埋め込める HTML 断片」を返す（`readme_render` 側でサニタイズ・見出し降格する）。
    const html = `<article><h1>${repoName}</h1><p>README-STUB-CONTENT for ${owner}/${repoName}.</p><ul><li>feature one</li><li>feature two</li></ul></article>`
    res.writeHead(200, { 'content-type': 'text/html; charset=utf-8' })
    return res.end(html)
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
      manyRepos.find((repo) => repo.owner.login === owner && repo.name === repoName) ??
      // AC-12: private リポジトリも上流は 200 で返す（「見つからない」に倒すのはアプリ側の責務）
      privateMixedRepos.find((repo) => repo.owner.login === owner && repo.name === repoName) ??
      // Issue #334 F-4: README 不在の再現用（詳細本体は 200・README エンドポイントのみ 404）
      readmeExtraRepos.find((repo) => repo.owner.login === owner && repo.name === repoName) ??
      // Issue #339: 書式要素を網羅したリッチな README の再現用
      readmeRichExtraRepos.find((repo) => repo.owner.login === owner && repo.name === repoName) ??
      // SP-18: Gem バッジ経路の 2 件（詳細へ遷移しても 404 にならないようにする）
      gemBadgeRepos.find((repo) => repo.owner.login === owner && repo.name === repoName) ??
      // 横スクロール退行ガードの 3 件（一覧 → 詳細の経路も 320px で検証するため）
      overflowGuardRepos.find((repo) => repo.owner.login === owner && repo.name === repoName) ??
      // SP-19: 候補プール実在のリポジトリ（Gem 一覧 → 詳細の経路）。上記のどれにも当たらず、
      // かつプールに載っている名前のときだけ 200 を合成する（上記の追記コメント参照）。
      (gemPoolFullNames.has(`${owner}/${repoName}`.toLowerCase())
        ? gemPoolRepo(owner, repoName)
        : undefined)
    if (!found) {
      return sendJson(res, 404, { message: 'stub: Not Found (no fixture for this owner/repo)' })
    }
    return sendJson(res, 200, found)
  }

  sendJson(res, 404, { message: `stub: unknown route ${url.pathname}` })
})

server.listen(PORT, () => {
  console.log(`[e2e-stub] listening on http://127.0.0.1:${PORT}`)
  // SP-18: どのリポジトリを「プール実在」として使ったかを起動ログに残す（プール再生成で
  // 変わるため、失敗時の切り分けに要る）。
  console.log(`[e2e-stub] gem-badge pool repository: ${gemBadgePoolFullName ?? '(読み込み失敗)'}`)
})
