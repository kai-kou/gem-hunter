#!/usr/bin/env node
// tools/check_site_a11y.mjs — LP（site/）の axe-core a11y 検査を run_checks.sh から呼び出す判定基盤（Issue #997）。
//
// `site/README.md`「アクセシビリティの実測（LP を対象に axe を流す）」の人手手順（python3 -m
// http.server + AxeBuilder）をスクリプト化したもの。判定基準（tags・violations = 0）・4 構成
// （light/1280・dark/1280・light/390・light/320）は同 README を正本とし、本ファイルはそれを機械実行する。
//
// 終了コード（docs/rules/check-tool-design-rules.md §1 の標準 3 値をそのまま採用。逸脱なし）:
//   0 = 合格（4 構成すべてで violations = 0）
//   1 = 違反あり（1 構成以上で axe が違反を検出）
//   2 = 判定不能（静的サーバー起動失敗・ページ読み込み失敗・axe 実行失敗・4 構成のうち一部が
//       完走しなかった等。検査そのものが成立しなかった状態を「合格」に丸めない）
//
// 使い方:
//   node tools/check_site_a11y.mjs             # 検査（site/ を対象、既定 4 構成）
//   node tools/check_site_a11y.mjs --self-test  # 検査ロジック自体の自己テスト（実 Chromium + 実 axe を使う）
import { createServer } from 'node:http'
import { readFile, mkdtemp, rm, writeFile, mkdir } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, extname, normalize, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { resolveChromiumExecutablePath } from './e2e-chromium-executable.mjs'

const __dirname = fileURLToPath(new URL('.', import.meta.url))
const REPO_ROOT = join(__dirname, '..')
const SITE_DIR = join(REPO_ROOT, 'site')

// README.md「アクセシビリティの実測」の 4 構成をそのまま踏襲する（正本は README。ここは実行するだけ）。
const CONFIGS = [
  { scheme: 'light', width: 1280 },
  { scheme: 'dark', width: 1280 },
  { scheme: 'light', width: 390 },
  { scheme: 'light', width: 320 },
]
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

/**
 * siteDir 配下だけを配信する最小の静的ファイルサーバー。
 * ポートは `listen(0)` で OS に空きポートを取らせる（並行実行中の固定ポート衝突を避ける）。
 * siteDir の外側へのパストラバーサルは拒否する（`..` 正規化後に siteDir 配下でなければ 403）。
 */
function startStaticServer(siteDir) {
  const server = createServer(async (req, res) => {
    try {
      const urlPath = decodeURIComponent((req.url ?? '/').split('?')[0])
      let relPath = urlPath === '/' ? '/index.html' : urlPath
      const normalized = normalize(join(siteDir, relPath))
      if (!normalized.startsWith(siteDir + sep) && normalized !== siteDir) {
        res.writeHead(403)
        res.end('forbidden')
        return
      }
      if (!existsSync(normalized)) {
        res.writeHead(404)
        res.end('not found')
        return
      }
      const body = await readFile(normalized)
      const mime = MIME_TYPES[extname(normalized)] ?? 'application/octet-stream'
      res.writeHead(200, { 'Content-Type': mime })
      res.end(body)
    } catch (err) {
      res.writeHead(500)
      res.end(`internal error: ${err instanceof Error ? err.message : String(err)}`)
    }
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
 * baseUrl で配信中の LP に対し、configs で指定した各 (scheme, width) で axe を実行する。
 * 1 構成でも例外が起きたら `ok: false` を記録して次の構成へ進む（1 構成の失敗で残りを
 * 巻き込んで打ち切らない＝失敗経路の可視化。ただし判定 evaluateA11yGate 側で INFRA_FAIL に倒す）。
 */
async function runA11yScan({ baseUrl, configs, log: doLog = () => {} }) {
  // L-126: クラウドコンテナの Chromium は TLS 1.3 ハンドシェイクが決定論的に失敗するため
  // --ssl-version-max=tls1.2 を渡す（capture_lp_screenshots.mjs / playwright.config.ts と同じ作法）。
  // executablePath はプリインストール Chromium とのビルド番号食い違いに備えたフォールバック
  // （#629・playwright.config.ts と同じ共有モジュールを使う）。
  const executablePath = resolveChromiumExecutablePath()
  const browser = await chromium.launch({
    args: ['--ssl-version-max=tls1.2'],
    ...(executablePath ? { executablePath } : {}),
  })
  const results = []
  try {
    for (const { scheme, width } of configs) {
      try {
        const context = await browser.newContext({
          viewport: { width, height: 900 },
          colorScheme: scheme,
        })
        try {
          const page = await context.newPage()
          const response = await page.goto(baseUrl + '/', { waitUntil: 'load', timeout: 30_000 })
          if (!response || response.status() >= 400) {
            doLog(
              `INFRA_FAIL: ${scheme}/${width} — ページ応答 ${response ? response.status() : '(no response)'}`,
            )
            results.push({ scheme, width, ok: false, violationCount: null, ruleIds: [] })
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
            doLog(`INFRA_FAIL: ${scheme}/${width} — axe の結果に violations 配列がありません`)
            results.push({ scheme, width, ok: false, violationCount: null, ruleIds: [] })
            continue
          }
          doLog(`${scheme}/${width}: violations = ${violations.length}`)
          results.push({
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
          `INFRA_FAIL: ${scheme}/${width} — 例外: ${err instanceof Error ? err.message : String(err)}`,
        )
        results.push({ scheme, width, ok: false, violationCount: null, ruleIds: [] })
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
 *   - 実行された構成の集合が expectedConfigs と一致しない → GATE_FAIL
 *     （構成が足りない・重複している・想定外の構成が混ざっている、のいずれも「4 構成完走」の
 *     不変条件違反として扱う。重複を「多く実行したから許容」と丸めない）
 *   - violationCount > 0 の構成が 1 件でもある            → GATE_FAIL
 *   - 上記いずれにも当たらない                            → PASS
 */
export function evaluateA11yGate(results, expectedConfigs) {
  if (!Array.isArray(results) || results.length === 0) {
    return { status: 'INFRA_FAIL', reason: '検査結果が空です（スキャンが実行されていません）' }
  }
  if (results.some((r) => r.ok !== true || typeof r.violationCount !== 'number')) {
    const broken = results.filter((r) => r.ok !== true)
    return {
      status: 'INFRA_FAIL',
      reason: `完走しなかった構成があります: ${broken.map((r) => `${r.scheme}/${r.width}`).join(', ')}`,
    }
  }
  const expectedKeys = [...expectedConfigs.map(({ scheme, width }) => `${scheme}:${width}`)].sort()
  const actualKeys = [...results.map((r) => `${r.scheme}:${r.width}`)].sort()
  if (
    actualKeys.length !== expectedKeys.length ||
    actualKeys.some((k, i) => k !== expectedKeys[i])
  ) {
    return {
      status: 'GATE_FAIL',
      reason: `実行された構成が期待と一致しません（期待: ${expectedKeys.join(', ')} / 実際: ${actualKeys.join(', ')}）`,
    }
  }
  const violated = results.filter((r) => r.violationCount > 0)
  if (violated.length > 0) {
    return {
      status: 'GATE_FAIL',
      reason: violated
        .map(
          (r) =>
            `${r.scheme}/${r.width}: violations=${r.violationCount}（${r.ruleIds.join(', ')}）`,
        )
        .join('; '),
    }
  }
  return { status: 'PASS', reason: null }
}

/**
 * 本判定のエントリポイント。site/（または差し替え可能な siteDir）を配信し、axe スキャン →
 * ゲート判定までを通す。self-test はこの関数を実 Chromium・実サーバーで直接呼び出す
 * （内部関数の個別呼び出しだけで済ませない・#474 項目3）。
 */
export async function main({ siteDir = SITE_DIR, configs = CONFIGS, quiet = false } = {}) {
  const doLog = quiet ? () => {} : log
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
  try {
    doLog(`静的サーバー起動: ${baseUrl}（対象: ${siteDir}）`)
    const results = await runA11yScan({ baseUrl, configs, log: doLog })
    const gate = evaluateA11yGate(results, configs)
    if (gate.status === 'PASS') {
      doLog(`PASS: 全 ${configs.length} 構成で violations = 0 です`)
      return { exitCode: 0, gate, results }
    }
    doLog(`${gate.status}: ${gate.reason}`)
    return { exitCode: gate.status === 'GATE_FAIL' ? 1 : 2, gate, results }
  } finally {
    await closeServer(server)
  }
}

// ---------------------------------------------------------------------------
// self-test
// ---------------------------------------------------------------------------

function unitTestEvaluateGate() {
  const expected = CONFIGS
  const cases = [
    {
      label: '4 構成すべて violations=0 → PASS',
      results: expected.map((c) => ({ ...c, ok: true, violationCount: 0, ruleIds: [] })),
      expectStatus: 'PASS',
    },
    {
      label: '1 構成でも violations>0 → GATE_FAIL',
      results: expected.map((c, i) => ({
        ...c,
        ok: true,
        violationCount: i === 1 ? 2 : 0,
        ruleIds: i === 1 ? ['color-contrast'] : [],
      })),
      expectStatus: 'GATE_FAIL',
    },
    {
      label: '1 構成でも ok=false（axe が完走しなかった）→ INFRA_FAIL',
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
      // 要素間の関係性の負ケース（#996 項目6）: 各要素（1 件 1 件）は ok=true・violationCount=0 と
      // 単体では妥当だが、「4 構成」という集合としての不変条件（重複なく期待どおりの組み合わせ）を
      // 満たさない。同一構成 light/1280 を 2 回数え、dark/1280 が抜けている。
      label: '4 件あるが構成が重複し dark/1280 が欠けている → GATE_FAIL（件数一致だけで通さない）',
      results: [
        { scheme: 'light', width: 1280, ok: true, violationCount: 0, ruleIds: [] },
        { scheme: 'light', width: 1280, ok: true, violationCount: 0, ruleIds: [] },
        { scheme: 'light', width: 390, ok: true, violationCount: 0, ruleIds: [] },
        { scheme: 'light', width: 320, ok: true, violationCount: 0, ruleIds: [] },
      ],
      expectStatus: 'GATE_FAIL',
    },
    {
      label: '3 構成しか実行されていない（1 構成欠落）→ GATE_FAIL',
      results: expected
        .slice(0, 3)
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

async function withFixtureDir(html, fn) {
  const dir = await mkdtemp(join(tmpdir(), 'check-site-a11y-fixture-'))
  try {
    await writeFile(join(dir, 'index.html'), html, 'utf-8')
    await writeFile(join(dir, 'ok.svg'), SVG_FIXTURE, 'utf-8')
    return await fn(dir)
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
      `[check_site_a11y --self-test] ${pass ? 'PASS' : 'FAIL'}: main() が違反なしフィクスチャで exitCode=0 / PASS を返す（実際: exitCode=${exitCode}, status=${gate.status}）`,
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

async function selfTest() {
  const unitOk = unitTestEvaluateGate()
  // 実 Chromium・実 axe・実 http サーバーを使う統合テスト（main() を直接呼ぶ＝本番の主コードパス）。
  const passOk = await integrationTestMainPass()
  const gateFailOk = await integrationTestMainGateFail()
  const infraFailOk = await integrationTestMainInfraFail()
  return unitOk && passOk && gateFailOk && infraFailOk
}

if (process.argv.includes('--self-test')) {
  selfTest().then((ok) => {
    process.exitCode = ok ? 0 : 1
  })
} else {
  main().then(({ exitCode }) => {
    process.exitCode = exitCode
  })
}
