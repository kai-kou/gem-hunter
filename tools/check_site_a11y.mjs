#!/usr/bin/env node
// tools/check_site_a11y.mjs — LP（site/）の axe-core a11y 検査を run_checks.sh から呼び出す判定基盤（Issue #997）。
//
// `site/README.md`「アクセシビリティの実測（LP を対象に axe を流す）」の人手手順（python3 -m
// http.server + AxeBuilder）をスクリプト化したもの。判定基準（tags・violations = 0）・4 構成
// （light/1280・dark/1280・light/390・light/320）は同 README を正本とし、本ファイルはそれを機械実行する。
// 走査対象は「ページ × 構成」の直積（Issue #996 CRITICAL 1）。ページ集合は `tools/check_site.py` の
// `PAGES` 定義と起動のたびに一致検証する（ドリフトを fail-closed で検知する。§ readCheckSitePyPages）。
//
// 終了コード（docs/rules/check-tool-design-rules.md §1 の標準 3 値をそのまま採用。逸脱なし）:
//   0 = 合格（全ページ×全構成で violations = 0）
//   1 = 違反あり（1 件以上で axe が違反を検出）
//   2 = 判定不能（静的サーバー起動失敗・ページ読み込み失敗・axe 実行失敗・Chromium 起動失敗・
//       PAGES 定義のドリフト・想定外の例外等。検査そのものが成立しなかった状態を「合格」に丸めない）
//
// 使い方:
//   node tools/check_site_a11y.mjs             # 検査（site/ を対象、既定 PAGES × 4 構成）
//   node tools/check_site_a11y.mjs --self-test  # 検査ロジック自体の自己テスト（実 Chromium + 実 axe を使う）
import { createServer } from 'node:http'
import { readFile, mkdtemp, rm, writeFile, mkdir, readdir } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, extname, relative, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { resolveChromiumExecutablePath } from './e2e-chromium-executable.mjs'

const __dirname = fileURLToPath(new URL('.', import.meta.url))
const REPO_ROOT = join(__dirname, '..')
const SITE_DIR = join(REPO_ROOT, 'site')
const CHECK_SITE_PY_PATH = join(REPO_ROOT, 'tools', 'check_site.py')

// README.md「アクセシビリティの実測」の 4 構成をそのまま踏襲する（正本は README。ここは実行するだけ）。
const CONFIGS = [
  { scheme: 'light', width: 1280 },
  { scheme: 'dark', width: 1280 },
  { scheme: 'light', width: 390 },
  { scheme: 'light', width: 320 },
]
// 走査対象ページ。正本は tools/check_site.py の PAGES（静的検査の対象と揃える）。
// 二重管理になるため、起動のたびに readCheckSitePyPages() で実際の PAGES 定義と一致検証する
// （不一致・抽出失敗はどちらも INFRA_FAIL に倒す。手で同期し続けることを前提にしない）。
const PAGES = ['index.html', '404.html']
const AXE_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']

const MIME_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.webp': 'image/webp',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.woff2': 'font/woff2',
  '.woff': 'font/woff',
  '.txt': 'text/plain; charset=utf-8',
}

function log(msg) {
  console.log(`[check_site_a11y] ${msg}`)
}

/** pages × configs の直積を組み立てる（走査対象の唯一の生成元）。 */
function buildCombos(pages, configs) {
  return pages.flatMap((page) => configs.map((c) => ({ page, ...c })))
}

/**
 * siteDir 配下を再帰的に列挙し、「URL パス（`/` 始まり・POSIX 区切り）→ 絶対パス」の Map を作る。
 *
 * CodeQL 対応（PR #1079 レビュー指摘）: 以前はリクエストパス（`req.url` 由来のユーザー入力）を
 * `normalize(join(siteDir, relPath))` してから直接 `existsSync` / `readFile` へ渡しており、
 * 文字列プレフィックス判定によるガードを足しても「ユーザー入力が fs API のパス式へ到達する」
 * taint 経路自体は残っていた（Uncontrolled data used in path expression）。
 * 本関数はサーバー起動時に実在ファイルだけを列挙して絶対パスを確定させ、リクエスト処理では
 * その Map のキー検索のみを行う（`serveFile` 参照）。fs API に渡るのは列挙時に自分で作った
 * 絶対パスだけになり、ユーザー入力はパス式に一切現れない（taint 経路を源流で切る）。
 * `site/` は 17 ファイル・576KB 程度（2026-09-07 実測）で、起動のたびに全列挙しても無視できる
 * コストのため、キャッシュや遅延列挙は導入しない。
 */
async function buildFileMap(siteDir) {
  const map = new Map()
  async function walk(currentDir) {
    const entries = await readdir(currentDir, { withFileTypes: true })
    for (const entry of entries) {
      const abs = join(currentDir, entry.name)
      if (entry.isDirectory()) {
        // eslint-disable-next-line no-await-in-loop
        await walk(abs)
      } else if (entry.isFile()) {
        const rel = relative(siteDir, abs).split(sep).join('/')
        map.set(`/${rel}`, abs)
      }
    }
  }
  await walk(siteDir)
  return map
}

/**
 * fileMap のキー検索だけでレスポンスを組み立てる純粋寄りの関数（実 HTTP サーバー無しで
 * self-test から直接検証できる）。fs へ渡すのは fileMap の値（列挙時に確定した絶対パス）のみ。
 * 例外テキストはレスポンス本文に含めない（PR #1079 CodeQL 指摘: Exception text reinterpreted as HTML）。
 */
async function serveFile(fileMap, urlPath, { readFileImpl = readFile } = {}) {
  const key = urlPath === '/' ? '/index.html' : urlPath
  const absPath = fileMap.get(key)
  if (!absPath) {
    return { status: 404, contentType: 'text/plain; charset=utf-8', body: 'not found' }
  }
  try {
    const body = await readFileImpl(absPath)
    const mime = MIME_TYPES[extname(absPath)] ?? 'application/octet-stream'
    return { status: 200, contentType: mime, body }
  } catch (err) {
    console.error(
      `[check_site_a11y] internal error while serving ${urlPath}: ${err instanceof Error ? (err.stack ?? err.message) : String(err)}`,
    )
    return { status: 500, contentType: 'text/plain; charset=utf-8', body: 'internal error' }
  }
}

/**
 * siteDir 配下だけを配信する最小の静的ファイルサーバー。
 * ポートは `listen(0)` で OS に空きポートを取らせる（並行実行中の固定ポート衝突を避ける）。
 * リクエストパスの解決は `serveFile`（fileMap 検索のみ）に一任し、fs API へユーザー入力を
 * 直接渡さない（buildFileMap の JSDoc 参照）。
 */
async function startStaticServer(siteDir) {
  const fileMap = await buildFileMap(siteDir)
  const server = createServer(async (req, res) => {
    let urlPath
    try {
      urlPath = decodeURIComponent((req.url ?? '/').split('?')[0])
    } catch {
      // 不正なパーセントエンコーディング（malformed URI）は fileMap に絶対ヒットしないキーへ倒す
      urlPath = '/__check_site_a11y_malformed_uri__'
    }
    const { status, contentType, body } = await serveFile(fileMap, urlPath)
    res.writeHead(status, { 'Content-Type': contentType })
    res.end(body)
  })
  return new Promise((resolve, reject) => {
    server.once('error', reject)
    server.listen(0, '127.0.0.1', () => {
      const address = server.address()
      const port = typeof address === 'object' && address ? address.port : null
      if (!port) {
        reject(new Error('静的サーバーのポート取得に失敗しました'))
        return
      }
      resolve({ server, baseUrl: `http://127.0.0.1:${port}` })
    })
  })
}

function closeServer(server) {
  return new Promise((resolve) => {
    server.close(() => resolve())
    // close() は既存コネクションの切断を待つため、テスト用途では即座に unref もしておく
    server.unref?.()
  })
}

/**
 * `tools/check_site.py` の `PAGES = [...]` 定義をソースから抽出する（import はできない —
 * Python と JS で言語が違うため定数を共有できず、二重管理を「一致検証」で fail-closed にする）。
 * 抽出できなければ null を返す（「抽出できなかった」を「一致した」と読み替えない）。
 */
async function readCheckSitePyPages(checkSitePyPath) {
  let text
  try {
    text = await readFile(checkSitePyPath, 'utf-8')
  } catch {
    return null
  }
  const m = text.match(/^PAGES\s*=\s*(\[[^\]\n]*\])\s*$/m)
  if (!m) return null
  try {
    const arr = JSON.parse(m[1])
    if (!Array.isArray(arr) || arr.length === 0 || arr.some((x) => typeof x !== 'string')) {
      return null
    }
    return arr
  } catch {
    return null
  }
}

/** 集合として一致するかを判定する純粋関数（順序は問わない）。抽出失敗（null）は常に不一致。 */
export function pagesInSync(extracted, own) {
  if (!Array.isArray(extracted) || extracted.length === 0) return false
  if (!Array.isArray(own) || own.length === 0) return false
  const a = [...extracted].sort()
  const b = [...own].sort()
  return a.length === b.length && a.every((v, i) => v === b[i])
}

/**
 * baseUrl で配信中の LP に対し、combos（{page, scheme, width}）ごとに axe を実行する。
 * 1 件でも例外が起きたら `ok: false` を記録して次へ進む（1 件の失敗で残りを巻き込んで
 * 打ち切らない＝失敗経路の可視化。ただし判定 evaluateA11yGate 側で INFRA_FAIL に倒す）。
 * Chromium の起動失敗（#629 のビルド番号食い違い等）は try/catch で捕捉し、ログを残して
 * 呼び出し元（main）へ再送出する（main 側で INFRA_FAIL / exitCode: 2 へ倒す・PR #1079 CRITICAL 2）。
 */
async function runA11yScan({ baseUrl, combos, log: doLog = () => {}, launchOptionOverrides = {} }) {
  // L-126: クラウドコンテナの Chromium は TLS 1.3 ハンドシェイクが決定論的に失敗するため
  // --ssl-version-max=tls1.2 を渡す（capture_lp_screenshots.mjs / playwright.config.ts と同じ作法）。
  // executablePath はプリインストール Chromium とのビルド番号食い違いに備えたフォールバック
  // （#629・playwright.config.ts と同じ共有モジュールを使う）。正常系は undefined を返す契約
  // （e2e-chromium-executable.mjs の JSDoc）なので、playwright.config.ts / capture_lp_screenshots.mjs
  // と同じく直接代入する（PR #1079 NIT 4: 条件分岐スプレッドをやめて代入形を揃える）。
  const executablePath = resolveChromiumExecutablePath()
  let browser
  try {
    browser = await chromium.launch({
      args: ['--ssl-version-max=tls1.2'],
      executablePath,
      ...launchOptionOverrides,
    })
  } catch (err) {
    doLog(
      `INFRA_FAIL: Chromium の起動に失敗しました: ${err instanceof Error ? err.message : String(err)}`,
    )
    throw err
  }
  const results = []
  try {
    for (const { page: pageName, scheme, width } of combos) {
      try {
        const context = await browser.newContext({
          viewport: { width, height: 900 },
          colorScheme: scheme,
        })
        try {
          const page = await context.newPage()
          const response = await page.goto(`${baseUrl}/${pageName}`, {
            waitUntil: 'load',
            timeout: 30_000,
          })
          if (!response || response.status() >= 400) {
            doLog(
              `INFRA_FAIL: ${pageName} ${scheme}/${width} — ページ応答 ${response ? response.status() : '(no response)'}`,
            )
            results.push({
              page: pageName,
              scheme,
              width,
              ok: false,
              violationCount: null,
              ruleIds: [],
            })
            continue
          }
          // README の人手手順と同様、詳細（<details>）を開いた状態で計測する
          await page.evaluate(() => {
            document.querySelectorAll('details').forEach((d) => {
              d.open = true
            })
          })
          const result = await new AxeBuilder({ page }).withTags(AXE_TAGS).analyze()
          const violations = Array.isArray(result?.violations) ? result.violations : null
          if (violations === null) {
            doLog(
              `INFRA_FAIL: ${pageName} ${scheme}/${width} — axe の結果に violations 配列がありません`,
            )
            results.push({
              page: pageName,
              scheme,
              width,
              ok: false,
              violationCount: null,
              ruleIds: [],
            })
            continue
          }
          doLog(`${pageName} ${scheme}/${width}: violations = ${violations.length}`)
          results.push({
            page: pageName,
            scheme,
            width,
            ok: true,
            violationCount: violations.length,
            ruleIds: violations.map((v) => v.id),
          })
        } finally {
          await context.close()
        }
      } catch (err) {
        doLog(
          `INFRA_FAIL: ${pageName} ${scheme}/${width} — 例外: ${err instanceof Error ? err.message : String(err)}`,
        )
        results.push({
          page: pageName,
          scheme,
          width,
          ok: false,
          violationCount: null,
          ruleIds: [],
        })
      }
    }
  } finally {
    await browser.close()
  }
  return results
}

/**
 * axe スキャン結果からゲート判定を下す純粋関数（Chromium 不要・self-test で検証する）。
 *
 * 失敗経路（見逃しに至りうる経路）を全て塞ぐ:
 *   - results が配列でない / 空                          → INFRA_FAIL
 *   - 1 件でも ok=false（サーバー未応答・axe 例外等）      → INFRA_FAIL（黙って除外して残りだけで判定しない）
 *   - 実行された組み合わせ（page/scheme/width）の集合が expectedCombos と一致しない → GATE_FAIL
 *     （組み合わせが足りない・重複している・想定外の組み合わせが混ざっている、のいずれも
 *     「全ページ×全構成完走」の不変条件違反として扱う。重複を「多く実行したから許容」と丸めない）
 *   - violationCount > 0 の組み合わせが 1 件でもある      → GATE_FAIL
 *   - 上記いずれにも当たらない                            → PASS
 */
export function evaluateA11yGate(results, expectedCombos) {
  if (!Array.isArray(results) || results.length === 0) {
    return { status: 'INFRA_FAIL', reason: '検査結果が空です（スキャンが実行されていません）' }
  }
  if (results.some((r) => r.ok !== true || typeof r.violationCount !== 'number')) {
    const broken = results.filter((r) => r.ok !== true)
    return {
      status: 'INFRA_FAIL',
      reason: `完走しなかった組み合わせがあります: ${broken.map((r) => `${r.page} ${r.scheme}/${r.width}`).join(', ')}`,
    }
  }
  const key = (r) => `${r.page}:${r.scheme}:${r.width}`
  const expectedKeys = [...expectedCombos.map(key)].sort()
  const actualKeys = [...results.map(key)].sort()
  if (
    actualKeys.length !== expectedKeys.length ||
    actualKeys.some((k, i) => k !== expectedKeys[i])
  ) {
    return {
      status: 'GATE_FAIL',
      reason: `実行された組み合わせが期待と一致しません（期待: ${expectedKeys.join(', ')} / 実際: ${actualKeys.join(', ')}）`,
    }
  }
  const violated = results.filter((r) => r.violationCount > 0)
  if (violated.length > 0) {
    return {
      status: 'GATE_FAIL',
      reason: violated
        .map(
          (r) =>
            `${r.page} ${r.scheme}/${r.width}: violations=${r.violationCount}（${r.ruleIds.join(', ')}）`,
        )
        .join('; '),
    }
  }
  return { status: 'PASS', reason: null }
}

/**
 * 本判定のエントリポイント。site/（または差し替え可能な siteDir）を配信し、
 * PAGES ドリフト検証 → axe スキャン → ゲート判定までを通す。self-test はこの関数を
 * 実 Chromium・実サーバーで直接呼び出す（内部関数の個別呼び出しだけで済ませない・#474 項目3）。
 * 想定外の例外（server 起動後に投げられたもの）は catch して INFRA_FAIL / exitCode: 2 へ倒す
 * （PR #1079 CRITICAL 2: chromium.launch() 失敗が未捕捉のまま unhandled rejection になるのを防ぐ）。
 */
export async function main({
  siteDir = SITE_DIR,
  pages = PAGES,
  configs = CONFIGS,
  checkSitePyPath = CHECK_SITE_PY_PATH,
  launchOptionOverrides = {},
  quiet = false,
} = {}) {
  const doLog = quiet ? () => {} : log

  const extractedPages = await readCheckSitePyPages(checkSitePyPath)
  if (!pagesInSync(extractedPages, pages)) {
    const reason =
      extractedPages === null
        ? `tools/check_site.py の PAGES 定義を抽出できませんでした（${checkSitePyPath}）`
        : `tools/check_site.py の PAGES（${extractedPages.join(', ')}）と本スクリプトの PAGES（${pages.join(', ')}）が一致しません`
    doLog(`INFRA_FAIL: ${reason}`)
    return { exitCode: 2, gate: { status: 'INFRA_FAIL', reason } }
  }

  let started
  try {
    started = await startStaticServer(siteDir)
  } catch (err) {
    doLog(
      `INFRA_FAIL: 静的サーバーの起動に失敗しました: ${err instanceof Error ? err.message : String(err)}`,
    )
    return { exitCode: 2, gate: { status: 'INFRA_FAIL', reason: 'server start failed' } }
  }
  const { server, baseUrl } = started
  const combos = buildCombos(pages, configs)
  try {
    doLog(
      `静的サーバー起動: ${baseUrl}（対象: ${siteDir}・${pages.length} ページ × ${configs.length} 構成 = ${combos.length} 件）`,
    )
    const results = await runA11yScan({ baseUrl, combos, log: doLog, launchOptionOverrides })
    const gate = evaluateA11yGate(results, combos)
    if (gate.status === 'PASS') {
      doLog(`PASS: 全 ${combos.length} 件で violations = 0 です`)
      return { exitCode: 0, gate, results }
    }
    doLog(`${gate.status}: ${gate.reason}`)
    return { exitCode: gate.status === 'GATE_FAIL' ? 1 : 2, gate, results }
  } catch (err) {
    const reason = `想定外の例外: ${err instanceof Error ? err.message : String(err)}`
    doLog(`INFRA_FAIL: ${reason}`)
    return { exitCode: 2, gate: { status: 'INFRA_FAIL', reason } }
  } finally {
    await closeServer(server)
  }
}

// ---------------------------------------------------------------------------
// self-test
// ---------------------------------------------------------------------------

function unitTestEvaluateGate() {
  const expected = buildCombos(PAGES, CONFIGS)
  const cases = [
    {
      label: `${expected.length} 件（${PAGES.length} ページ×${CONFIGS.length} 構成）すべて violations=0 → PASS`,
      results: expected.map((c) => ({ ...c, ok: true, violationCount: 0, ruleIds: [] })),
      expectStatus: 'PASS',
    },
    {
      label: '1 件でも violations>0 → GATE_FAIL',
      results: expected.map((c, i) => ({
        ...c,
        ok: true,
        violationCount: i === 1 ? 2 : 0,
        ruleIds: i === 1 ? ['color-contrast'] : [],
      })),
      expectStatus: 'GATE_FAIL',
    },
    {
      label: '1 件でも ok=false（axe が完走しなかった）→ INFRA_FAIL',
      results: expected.map((c, i) =>
        i === 0
          ? { ...c, ok: false, violationCount: null, ruleIds: [] }
          : { ...c, ok: true, violationCount: 0, ruleIds: [] },
      ),
      expectStatus: 'INFRA_FAIL',
    },
    {
      label: '結果が空配列 → INFRA_FAIL（対象0件を合格に丸めない・check-tool-design-rules §2）',
      results: [],
      expectStatus: 'INFRA_FAIL',
    },
    {
      // 反例（#996 CRITICAL 1 の核心・キーに page を含めない実装だと通ってしまう）:
      // 404.html が一度もスキャンされておらず、代わりに index.html を 4 構成×2 回（水増し）で
      // 件数だけ 8 件に合わせている。件数一致・scheme/width の多重集合も一致するため、
      // 判定キーが `page` を含まないと素通りする（page を落とす変異で実際に検知できることを確認済み）。
      label:
        '404.html が一度もスキャンされず index.html を水増しして件数だけ合わせている → GATE_FAIL',
      results: [...CONFIGS, ...CONFIGS].map((c) => ({
        page: 'index.html',
        ...c,
        ok: true,
        violationCount: 0,
        ruleIds: [],
      })),
      expectStatus: 'GATE_FAIL',
    },
    {
      // 要素間の関係性の負ケース（#996 項目6 相当）: 件数（8 件）は一致するが、
      // index.html の light/1280 が重複し dark/1280 が欠けている「不正な直積」。
      label: '件数一致だが index.html light/1280 が重複し dark/1280 が欠けている → GATE_FAIL',
      results: [
        {
          page: 'index.html',
          scheme: 'light',
          width: 1280,
          ok: true,
          violationCount: 0,
          ruleIds: [],
        },
        {
          page: 'index.html',
          scheme: 'light',
          width: 1280,
          ok: true,
          violationCount: 0,
          ruleIds: [],
        },
        {
          page: 'index.html',
          scheme: 'light',
          width: 390,
          ok: true,
          violationCount: 0,
          ruleIds: [],
        },
        {
          page: 'index.html',
          scheme: 'light',
          width: 320,
          ok: true,
          violationCount: 0,
          ruleIds: [],
        },
        {
          page: '404.html',
          scheme: 'light',
          width: 1280,
          ok: true,
          violationCount: 0,
          ruleIds: [],
        },
        { page: '404.html', scheme: 'dark', width: 1280, ok: true, violationCount: 0, ruleIds: [] },
        { page: '404.html', scheme: 'light', width: 390, ok: true, violationCount: 0, ruleIds: [] },
        { page: '404.html', scheme: 'light', width: 320, ok: true, violationCount: 0, ruleIds: [] },
      ],
      expectStatus: 'GATE_FAIL',
    },
    {
      label: '1 件欠落（実行数が期待より少ない）→ GATE_FAIL',
      results: expected
        .slice(0, expected.length - 1)
        .map((c) => ({ ...c, ok: true, violationCount: 0, ruleIds: [] })),
      expectStatus: 'GATE_FAIL',
    },
  ]
  let ok = true
  for (const c of cases) {
    const gate = evaluateA11yGate(c.results, expected)
    const pass = gate.status === c.expectStatus
    if (!pass) ok = false
    console.log(
      `[check_site_a11y --self-test] ${pass ? 'PASS' : 'FAIL'}: ${c.label}（実際: ${gate.status} / ${gate.reason ?? ''}）`,
    )
  }
  return ok
}

function unitTestPagesInSync() {
  const cases = [
    {
      label: '完全一致 → true',
      extracted: ['index.html', '404.html'],
      own: ['index.html', '404.html'],
      expect: true,
    },
    {
      label: '順序違いでも集合として一致 → true',
      extracted: ['404.html', 'index.html'],
      own: ['index.html', '404.html'],
      expect: true,
    },
    {
      label: '抽出結果が null（抽出失敗）→ false',
      extracted: null,
      own: ['index.html', '404.html'],
      expect: false,
    },
    {
      label: '要素数が違う → false',
      extracted: ['index.html'],
      own: ['index.html', '404.html'],
      expect: false,
    },
    {
      label: '要素の中身が違う（近似だが別カテゴリ）→ false',
      extracted: ['index.html', 'about.html'],
      own: ['index.html', '404.html'],
      expect: false,
    },
  ]
  let ok = true
  for (const c of cases) {
    const actual = pagesInSync(c.extracted, c.own)
    const pass = actual === c.expect
    if (!pass) ok = false
    console.log(
      `[check_site_a11y --self-test] ${pass ? 'PASS' : 'FAIL'}: pagesInSync — ${c.label}（実際: ${actual}）`,
    )
  }
  return ok
}

function unitTestServeFile() {
  const fileMap = new Map([['/index.html', '/fake/abs/index.html']])
  return (async () => {
    let ok = true

    // 404: fileMap に無いキー（存在しないパス・パストラバーサル試行のどちらも同じ経路で拒否される）
    for (const traversalPath of [
      '/does-not-exist.html',
      '/../../../../etc/passwd',
      '/%2e%2e/etc/passwd',
    ]) {
      // eslint-disable-next-line no-await-in-loop
      const res = await serveFile(fileMap, traversalPath)
      const pass =
        res.status === 404 && !res.body.includes('/etc/passwd') && !res.body.includes('root:')
      if (!pass) ok = false
      console.log(
        `[check_site_a11y --self-test] ${pass ? 'PASS' : 'FAIL'}: serveFile が未列挙パス「${traversalPath}」を 404 で拒否し本文に漏洩が無い（実際: status=${res.status}, body=${res.body}）`,
      )
    }

    // 200: fileMap にあるキーは readFileImpl 経由で本文を返す
    {
      const res = await serveFile(fileMap, '/index.html', {
        readFileImpl: async () => Buffer.from('<html></html>'),
      })
      const pass =
        res.status === 200 &&
        res.contentType.startsWith('text/html') &&
        res.body.toString() === '<html></html>'
      if (!pass) ok = false
      console.log(
        `[check_site_a11y --self-test] ${pass ? 'PASS' : 'FAIL'}: serveFile が既知キーを 200 で返す（実際: status=${res.status}, contentType=${res.contentType}）`,
      )
    }

    // 500: readFileImpl が例外を投げても、その例外テキストが本文に漏れない（PR #1079 CodeQL 指摘）
    {
      const secretMessage = 'ENOENT: secret-internal-path-detail /very/sensitive/path'
      const res = await serveFile(fileMap, '/index.html', {
        readFileImpl: async () => {
          throw new Error(secretMessage)
        },
      })
      const pass =
        res.status === 500 &&
        res.contentType === 'text/plain; charset=utf-8' &&
        !res.body.includes(secretMessage) &&
        !res.body.includes('sensitive')
      if (!pass) ok = false
      console.log(
        `[check_site_a11y --self-test] ${pass ? 'PASS' : 'FAIL'}: serveFile が readFile 例外時に本文へ例外テキストを漏らさず 500 を返す（実際: status=${res.status}, body=${res.body}）`,
      )
    }

    return ok
  })()
}

const CLEAN_HTML = `<!doctype html>
<html lang="ja">
<head><meta charset="utf-8" /><title>fixture</title>
<style>body{background:#fff;color:#111}</style>
</head>
<body>
<h1>見出し</h1>
<img src="./ok.svg" alt="装飾のない説明つき画像" width="10" height="10" />
<p>本文テキストです。</p>
</body>
</html>`

// axe の 3 ルール（image-alt / color-contrast / duplicate-id-aria）に別々にヒットさせる
// バリアント（症状のバリアント展開・#474 項目2）。
const VIOLATION_VARIANTS = {
  'image-alt': `<!doctype html>
<html lang="ja">
<head><meta charset="utf-8" /><title>fixture</title></head>
<body>
<h1>見出し</h1>
<img src="./ok.svg" width="10" height="10" />
<p>本文テキストです。</p>
</body>
</html>`,
  'color-contrast': `<!doctype html>
<html lang="ja">
<head><meta charset="utf-8" /><title>fixture</title>
<style>body{background:#fff}.low{color:#eee}</style>
</head>
<body>
<h1>見出し</h1>
<p class="low">コントラスト不足の本文テキストです。読めるはずがない薄いグレーです。</p>
</body>
</html>`,
  'aria-hidden-body': `<!doctype html>
<html lang="ja">
<head><meta charset="utf-8" /><title>fixture</title></head>
<body aria-hidden="true">
<h1>見出し</h1>
<p>本文テキストです。</p>
</body>
</html>`,
}

const SVG_FIXTURE = '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"></svg>'

/**
 * フィクスチャディレクトリを作る。`pages` は文字列（index.html/404.html の両方に同じ HTML を書く。
 * 通常の PASS/GATE_FAIL 検証はページ間の差を必要としないため）、または
 * `{ 'index.html': html, '404.html': html2 }` 形式のファイル名 → HTML マップのどちらも受け付ける。
 */
async function withFixtureDir(pages, fn) {
  const dir = await mkdtemp(join(tmpdir(), 'check-site-a11y-fixture-'))
  try {
    const pageMap = typeof pages === 'string' ? { 'index.html': pages, '404.html': pages } : pages
    for (const [filename, html] of Object.entries(pageMap)) {
      // eslint-disable-next-line no-await-in-loop
      await writeFile(join(dir, filename), html, 'utf-8')
    }
    await writeFile(join(dir, 'ok.svg'), SVG_FIXTURE, 'utf-8')
    return await fn(dir)
  } finally {
    await rm(dir, { recursive: true, force: true })
  }
}

/** `tools/check_site.py` を模した一時ファイルを作る（PAGES ドリフト検証の self-test 用）。 */
async function withTempCheckSitePy(content, fn) {
  const dir = await mkdtemp(join(tmpdir(), 'check-site-a11y-checksitepy-'))
  const path = join(dir, 'check_site.py')
  try {
    await writeFile(path, content, 'utf-8')
    return await fn(path)
  } finally {
    await rm(dir, { recursive: true, force: true })
  }
}

// self-test 用の軽量構成（実 Chromium を複数回起動するため 1 構成のみで足を軽くする）。
const SELFTEST_CONFIGS = [{ scheme: 'light', width: 1280 }]

async function integrationTestMainPass() {
  return withFixtureDir(CLEAN_HTML, async (dir) => {
    const { exitCode, gate } = await main({ siteDir: dir, configs: SELFTEST_CONFIGS, quiet: true })
    const pass = exitCode === 0 && gate.status === 'PASS'
    console.log(
      `[check_site_a11y --self-test] ${pass ? 'PASS' : 'FAIL'}: main() が違反なしフィクスチャ（index.html + 404.html）で exitCode=0 / PASS を返す（実際: exitCode=${exitCode}, status=${gate.status}）`,
    )
    return pass
  })
}

async function integrationTestMainGateFail() {
  let allOk = true
  for (const [ruleId, html] of Object.entries(VIOLATION_VARIANTS)) {
    // eslint-disable-next-line no-await-in-loop
    const pass = await withFixtureDir(html, async (dir) => {
      const { exitCode, gate } = await main({
        siteDir: dir,
        configs: SELFTEST_CONFIGS,
        quiet: true,
      })
      const ok = exitCode === 1 && gate.status === 'GATE_FAIL'
      console.log(
        `[check_site_a11y --self-test] ${ok ? 'PASS' : 'FAIL'}: main()（本番の入口）が「${ruleId}」違反フィクスチャで exitCode=1 / GATE_FAIL を返す（実際: exitCode=${exitCode}, status=${gate.status}, reason=${gate.reason}）`,
      )
      return ok
    })
    if (!pass) allOk = false
  }
  return allOk
}

async function integrationTestMainInfraFail() {
  // index.html が存在しない siteDir（サーバーは起動するが 404 になる）→ main() を本物の入口として通し、
  // exitCode=2（INFRA_FAIL）になることを実測する。
  const dir = await mkdtemp(join(tmpdir(), 'check-site-a11y-fixture-empty-'))
  await mkdir(dir, { recursive: true })
  try {
    const { exitCode, gate } = await main({ siteDir: dir, configs: SELFTEST_CONFIGS, quiet: true })
    const pass = exitCode === 2 && gate.status === 'INFRA_FAIL'
    console.log(
      `[check_site_a11y --self-test] ${pass ? 'PASS' : 'FAIL'}: main() が index.html 不在（404）で exitCode=2 / INFRA_FAIL を返す（実際: exitCode=${exitCode}, status=${gate.status}）`,
    )
    return pass
  } finally {
    await rm(dir, { recursive: true, force: true })
  }
}

async function integrationTestReadCheckSitePyPagesMatchesReal() {
  const extracted = await readCheckSitePyPages(CHECK_SITE_PY_PATH)
  const pass = pagesInSync(extracted, PAGES)
  console.log(
    `[check_site_a11y --self-test] ${pass ? 'PASS' : 'FAIL'}: tools/check_site.py の実際の PAGES と本スクリプトの PAGES が一致する（実際: ${JSON.stringify(extracted)} / 本スクリプト: ${JSON.stringify(PAGES)}）`,
  )
  return pass
}

async function integrationTestMainInfraFailPagesDrift() {
  // check_site.py 側だけ PAGES が変わった（ドリフトした）状態を模す。
  return withFixtureDir(CLEAN_HTML, async (dir) => {
    return withTempCheckSitePy(
      'PAGES = ["index.html", "about.html"]\n',
      async (checkSitePyPath) => {
        const { exitCode, gate } = await main({
          siteDir: dir,
          configs: SELFTEST_CONFIGS,
          checkSitePyPath,
          quiet: true,
        })
        const pass = exitCode === 2 && gate.status === 'INFRA_FAIL'
        console.log(
          `[check_site_a11y --self-test] ${pass ? 'PASS' : 'FAIL'}: main() が PAGES ドリフト（check_site.py 側だけ変更）で exitCode=2 / INFRA_FAIL を返す（実際: exitCode=${exitCode}, status=${gate.status}）`,
        )
        return pass
      },
    )
  })
}

async function integrationTestMainInfraFailPagesExtractFailure() {
  // PAGES 定義そのものが読み取れない check_site.py を模す（抽出失敗）。
  return withFixtureDir(CLEAN_HTML, async (dir) => {
    return withTempCheckSitePy('# PAGES 定義がここには無い\nX = 1\n', async (checkSitePyPath) => {
      const { exitCode, gate } = await main({
        siteDir: dir,
        configs: SELFTEST_CONFIGS,
        checkSitePyPath,
        quiet: true,
      })
      const pass = exitCode === 2 && gate.status === 'INFRA_FAIL'
      console.log(
        `[check_site_a11y --self-test] ${pass ? 'PASS' : 'FAIL'}: main() が PAGES 抽出失敗（定義なし）で exitCode=2 / INFRA_FAIL を返す（実際: exitCode=${exitCode}, status=${gate.status}）`,
      )
      return pass
    })
  })
}

async function integrationTestMainInfraFailChromiumLaunch() {
  // pages を index.html だけに絞り、check_site.py 側の PAGES もそれに合わせて同期させることで
  // ドリフト検知（別の INFRA_FAIL 経路）を通過させ、Chromium 起動失敗そのものを検証する。
  return withFixtureDir({ 'index.html': CLEAN_HTML }, async (dir) => {
    return withTempCheckSitePy('PAGES = ["index.html"]\n', async (checkSitePyPath) => {
      const { exitCode, gate } = await main({
        siteDir: dir,
        pages: ['index.html'],
        configs: SELFTEST_CONFIGS,
        checkSitePyPath,
        quiet: true,
        launchOptionOverrides: { executablePath: '/nonexistent/chromium-binary-for-self-test' },
      })
      const pass = exitCode === 2 && gate.status === 'INFRA_FAIL'
      console.log(
        `[check_site_a11y --self-test] ${pass ? 'PASS' : 'FAIL'}: main() が Chromium 起動失敗（不正な executablePath）で exitCode=2 / INFRA_FAIL を返す（実際: exitCode=${exitCode}, status=${gate.status}）`,
      )
      return pass
    })
  })
}

/** `node tools/check_site_a11y.mjs` として実プロセス起動したときの CLI ディスパッチ（else 分岐）
 * を子プロセスで実測する（#996 WARNING 3・SD-2「本番の主コードパスを必ず 1 つ含める」#686）。
 * main() を直接呼ぶだけでは `process.exitCode = exitCode` の配線は一度も実行されない。
 */
async function integrationTestCliDispatchExitCode() {
  const { spawnSync } = await import('node:child_process')
  const runCli = (dir) => {
    const scriptPath = fileURLToPath(import.meta.url)
    return spawnSync(
      process.execPath,
      [scriptPath, '--site-dir', dir, '--configs-light-1280-only'],
      {
        encoding: 'utf-8',
        timeout: 60_000,
      },
    )
  }

  // ① 違反なしフィクスチャ → exit 0。単独では `process.exitCode = 0` 固定という退行を検知できない
  //   （元々 0 を期待するため）。②（違反ありフィクスチャ → exit 1）と対にして初めて、
  //   「else 分岐が main() の exitCode をちゃんと配線しているか」を実測で示せる。
  const passOk = await withFixtureDir(CLEAN_HTML, (dir) => {
    const proc = runCli(dir)
    const ok = proc.status === 0
    console.log(
      `[check_site_a11y --self-test] ${ok ? 'PASS' : 'FAIL'}: 子プロセス起動（else 分岐・実 CLI）が違反なしフィクスチャで exit 0 を返す（実際: status=${proc.status}, stderr末尾=${(proc.stderr || '').slice(-300)}）`,
    )
    return ok
  })

  // ② 違反ありフィクスチャ → exit 1。`process.exitCode = 0` 固定等の退行はここで検知する。
  const gateFailOk = await withFixtureDir(VIOLATION_VARIANTS['image-alt'], (dir) => {
    const proc = runCli(dir)
    const ok = proc.status === 1
    console.log(
      `[check_site_a11y --self-test] ${ok ? 'PASS' : 'FAIL'}: 子プロセス起動（else 分岐・実 CLI）が違反ありフィクスチャで exit 1 を返す（実際: status=${proc.status}, stderr末尾=${(proc.stderr || '').slice(-300)}）`,
    )
    return ok
  })

  return passOk && gateFailOk
}

async function selfTest() {
  const unitOk = unitTestEvaluateGate()
  const pagesInSyncOk = unitTestPagesInSync()
  const serveFileOk = await unitTestServeFile()
  // 実 Chromium・実 axe・実 http サーバーを使う統合テスト（main() を直接呼ぶ＝本番の主コードパス）。
  const passOk = await integrationTestMainPass()
  const gateFailOk = await integrationTestMainGateFail()
  const infraFailOk = await integrationTestMainInfraFail()
  const readPagesOk = await integrationTestReadCheckSitePyPagesMatchesReal()
  const pagesDriftOk = await integrationTestMainInfraFailPagesDrift()
  const pagesExtractFailOk = await integrationTestMainInfraFailPagesExtractFailure()
  const chromiumLaunchFailOk = await integrationTestMainInfraFailChromiumLaunch()
  const cliDispatchOk = await integrationTestCliDispatchExitCode()
  return (
    unitOk &&
    pagesInSyncOk &&
    serveFileOk &&
    passOk &&
    gateFailOk &&
    infraFailOk &&
    readPagesOk &&
    pagesDriftOk &&
    pagesExtractFailOk &&
    chromiumLaunchFailOk &&
    cliDispatchOk
  )
}

// ---------------------------------------------------------------------------
// CLI ディスパッチ
// ---------------------------------------------------------------------------

function parseCliOverrides(argv) {
  const overrides = {}
  const siteDirIdx = argv.indexOf('--site-dir')
  if (siteDirIdx !== -1 && argv[siteDirIdx + 1]) {
    overrides.siteDir = argv[siteDirIdx + 1]
  }
  // integrationTestCliDispatchExitCode 専用の軽量フラグ（実 Chromium 起動回数を 1 構成に絞る）。
  // pages はここでは上書きしない（既定 PAGES のままにし、tools/check_site.py 側の実物 PAGES との
  // ドリフト検証を子プロセス経路でも自然に通す。フィクスチャ siteDir は index.html + 404.html の
  // 両方を持つ withFixtureDir(CLEAN_HTML, ...) で作るため、既定 PAGES のままで完走する）。
  if (argv.includes('--configs-light-1280-only')) {
    overrides.configs = SELFTEST_CONFIGS
  }
  return overrides
}

if (process.argv.includes('--self-test')) {
  selfTest()
    .then((ok) => {
      process.exitCode = ok ? 0 : 1
    })
    .catch((err) => {
      console.error(
        '[check_site_a11y --self-test] 想定外の例外で自己テストが完走しませんでした:',
        err,
      )
      process.exitCode = 2
    })
} else {
  main(parseCliOverrides(process.argv.slice(2)))
    .then(({ exitCode }) => {
      process.exitCode = exitCode
    })
    .catch((err) => {
      console.error('[check_site_a11y] 想定外の例外で検査が完走しませんでした:', err)
      process.exitCode = 2
    })
}
