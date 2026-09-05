#!/usr/bin/env node
// tools/run_lighthouse.mjs — Lighthouse を run_checks.sh から呼び出す判定基盤（SP-10 R1・Issue #181）。
//
// SSOT: `content/discussions/sp10_a11y_20260820/whiteboard.md` ラウンド 3 の verdict（決定 A）。
// ユーザー確定事項（2026-08-20）: Accessibility = 100 は blocking ゲート、Performance は
// 計測値の記録のみでブロックしない。実装コードには「Performance N 以上」という閾値を
// 一切書かない（prd.md NFR-27 は「目安値として計測・記録する」に留まる）。
//
// 手順:
//   1. e2e/stub/server.mjs を起動（E2E とは別ポートを使い、E2E プロセスの残骸と衝突しない）
//   2. next build && next start --port 3101（E2E の 3100 と分離）
//   3. CHROME_PATH=/opt/pw-browsers/chromium を明示して Lighthouse を対象 3 画面に実行
//      - 未検索（待ち受け）: /ja
//      - 一覧（検索実行後の状態）: /ja?q=react
//      - 詳細: /ja/repos/octostub/octo-widgets
//      ⚠️ 画面を増減したら `tools/run_checks.sh` の Lighthouse ステップのコメント
//         （所要時間の見積もりと既定タイムアウトの根拠）も併せて更新すること。
//   4. categories.accessibility.score < 1.0 なら GATE_FAIL（非ゼロ exit）。
//      categories.performance.score と LCP 要素（`extractLcpElement`）は判定に使わず記録出力のみ。
//   5. JSON が生成されなかった／Chrome 起動に失敗した場合は INFRA_FAIL で区別する
//      （「チェッカー自体が落ちた」と「本当に a11y が落ちた」を混同しない）。
//
// 起動したプロセス（stub / next start）は正常終了・異常終了を問わず必ず後始末する。
//
// 🔴 起動オーケストレーションを playwright.config.ts の `webServer` へ一本化しない理由（Issue #186）
//
// 「stub 起動 → build → start → ポート待受 → 後始末」は playwright.config.ts の `webServer` と
// 概念的に重複する（実重複は main() の stub 起動 〜 waitForServer 完了まで ≒ 30 行 ↔
// playwright.config.ts の `webServer` 配列 ≒ 30 行）。一本化案（Lighthouse を Playwright の
// 別 project として書き、起動を `webServer` に委ねる）を検討したが、**採らない**。Playwright の
// `webServer` は config 単位で 1 セットしか持てず project ごとに分けられないため、寄せると以下が失われる:
//
//   1. ポート分離（stub 8799 / app 3101 ↔ E2E の 8788 / 3100）。E2E が異常終了でポートを掴んだまま
//      残っても Lighthouse は独立して走れる、という上の設計意図が消える
//   2. `--self-test`（`selfTest()`）— Chrome 不要でゲート判定ロジックだけを検証する経路
//   3. INFRA_FAIL と GATE_FAIL の区別。Playwright ではどちらも単なるテスト失敗になる
//   4. `SKIP_LIGHTHOUSE` による単独スキップと `RUN_CHECKS_LIGHTHOUSE_TIMEOUT`（既定 180 秒）の
//      独立タイムアウト。E2E（既定 600 秒）と同じ枠に丸められる
//
// ⚠️ プロセスグループ単位の後始末（`spawnTracked` の detached + `killGroup`）は **差にならない**ので
//    一本化しない理由に数えない。Playwright の `webServer` も `gracefulShutdown` 未指定時は
//    プロセスグループを強制 SIGKILL する（`@playwright/test` の型定義 `gracefulShutdown` の doc）。
//
// さらに `webServer` 側は `ensure_open_next_assets.mjs` を挟む OpenNext ビルドを計測対象にするため、
// Performance の計測基準が素の `next build` から変わる。`reuseExistingServer`（ローカル）により
// 古いビルドを計測して緑になる沈黙リスクも新たに増える。
//
// 二重実装のうち **更新漏れの実害が大きいダミー環境変数一式は `e2e/stub/e2e-env.mjs` へ共通化済み**
// （下の import）。残る重複は起動コマンドとポートだけで、両者は上記 1 のとおり意図的に異なる。
// 起動コマンドを変えるときは playwright.config.ts の `webServer`（app 側）も併せて確認すること。
import { spawn } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { buildDummyGitHubEnv } from '../e2e/stub/e2e-env.mjs'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = path.join(__dirname, '..')

const STUB_PORT = process.env.LIGHTHOUSE_STUB_PORT ?? '8799'
// 🔴 E2E（playwright.config.ts）は 3100 を使う。同一 run_checks.sh 内で逐次実行される想定だが、
//    E2E 側のプロセスが異常終了で port 3100 を掴んだまま残るケースを避けるため別ポートにする
//    （whiteboard round2 gate_infra の自己修正・round3 verdict 決定 A）。
const APP_PORT = process.env.LIGHTHOUSE_APP_PORT ?? '3101'
const CHROME_PATH = process.env.CHROME_PATH ?? '/opt/pw-browsers/chromium'
const BASE_URL = `http://127.0.0.1:${APP_PORT}`

// 🔴 未検索（待ち受け）は 2026-09-05 に追加した（Issue #355）。ファーストビューの装飾イラスト
//    `hero-idle.webp` はこの状態でしか描画されないため、それまでの 2 画面では LCP 要素も
//    Accessibility も一度も計測されていなかった（コードから LCP 要素は断定できない・ADR 0015 §5）。
const TARGETS = [
  { page: '未検索（待ち受け）', url: `${BASE_URL}/ja` },
  { page: '一覧（検索実行後）', url: `${BASE_URL}/ja?q=react` },
  { page: '詳細', url: `${BASE_URL}/ja/repos/octostub/octo-widgets` },
]

/**
 * Accessibility スコアからゲート判定を下す純粋関数（PR #183 レビュー指摘・実測で発見）。
 *
 * 🔴 なぜ丸め後の値で判定するか: `score` は浮動小数点（例 `0.9999999999999998`）で返ることがあり、
 * 生の値で `score < 1.0` を判定すると、ログ表示（`Math.round(score * 100)` = 100）と実際の判定
 * （GATE_FAIL）が食い違い、「Accessibility 100/100（しきい値 100）」と表示しながら失敗する
 * 原因不明の GATE_FAIL になる。表示と判定を同じ丸め後の値（`rounded`）に統一する。
 *
 * `--self-test` で検証する（Chrome 起動不要・`tools/check_contrast.py --self-test` と同じ流儀）。
 */
export function evaluateAccessibilityGate(score) {
  if (typeof score !== 'number' || Number.isNaN(score)) {
    return { status: 'INFRA_FAIL', rounded: null }
  }
  const rounded = Math.round(score * 100)
  return { status: rounded < 100 ? 'GATE_FAIL' : 'PASS', rounded }
}

/**
 * Lighthouse レポートから LCP 要素（`largest-contentful-paint-element` audit）を取り出す純粋関数。
 *
 * Issue #355: 「どの要素が LCP になるか」はコードからは断定できず実測でしか分からない。
 * Performance スコアと同じく **判定には使わず記録のみ**（ゲートを増やさない・ADR 0015 §5 の
 * 未確認事項を数値で閉じるための観測点）。
 *
 * 🔴 audit の ID は Lighthouse のバージョンで変わる。**本リポジトリの実測（13.4.1・2026-09-05 JST）では
 * `largest-contentful-paint-element` は存在せず**、insight 系（`lcp-breakdown-insight` /
 * `lcp-discovery-insight`）の details に LCP 要素の node が入る。旧 ID も後方互換で見る。
 * 見つからなければ握り潰さず null を返し、呼び出し側が「（audit なし）」と明示表示する。
 *
 * details.items の形も版で異なる（すべて受ける）:
 *   - 13.x : items に `{ type: 'node', snippet, selector, ... }` が直接並ぶ（実測）
 *   - 10+  : items[0] = { type: 'table', items: [{ node }] }
 *   - 旧   : items[0] = { node }
 * `--self-test` で実測構造と異常系を固定する（Chrome 起動不要）。
 */
export const LCP_ELEMENT_AUDIT_IDS = [
  'lcp-breakdown-insight',
  'lcp-discovery-insight',
  'largest-contentful-paint-element',
]

export function extractLcpElement(report) {
  for (const auditId of LCP_ELEMENT_AUDIT_IDS) {
    const items = report?.audits?.[auditId]?.details?.items
    if (!Array.isArray(items)) continue
    for (const item of items) {
      const nodes = []
      if (item?.type === 'node') nodes.push(item)
      if (item?.node) nodes.push(item.node)
      if (Array.isArray(item?.items)) {
        nodes.push(...item.items.map((inner) => inner?.node).filter(Boolean))
      }
      for (const node of nodes) {
        if (node?.snippet || node?.selector || node?.nodeLabel) {
          return {
            auditId,
            snippet: node.snippet ?? null,
            selector: node.selector ?? null,
            nodeLabel: node.nodeLabel ?? null,
          }
        }
      }
    }
  }
  return null
}

function selfTestLcpExtraction() {
  // 🔴 実測（Lighthouse 13.4.1・/ja 未検索画面）の details をそのまま縮めたもの。
  //    node は table でラップされず items に直接並ぶ。
  const measuredNode = {
    type: 'node',
    lhId: 'page-0-IMG',
    selector: 'body.min-h-full > main#main-content > img.mx-auto',
    snippet:
      '<img src="/images/hero-idle.webp" alt="" width="768" height="432" loading="eager" decoding="async" class="mx-auto mb-4 h-auto w-full max-w-xs">',
    nodeLabel: 'body.min-h-full > main#main-content > img.mx-auto',
  }
  const measured13 = (auditId) => ({
    audits: {
      [auditId]: {
        details: {
          type: 'list',
          items: [
            { type: 'table', headings: [], items: [{ subpart: 'timeToFirstByte' }] },
            measuredNode,
          ],
        },
      },
    },
  })
  const cases = [
    {
      label: '実測構造（13.x・lcp-breakdown-insight の items に node が直接並ぶ）から取り出す',
      report: measured13('lcp-breakdown-insight'),
      expect: (r) => r !== null && r.snippet.includes('hero-idle.webp'),
    },
    {
      label: 'breakdown が無くても lcp-discovery-insight から取り出す',
      report: measured13('lcp-discovery-insight'),
      expect: (r) => r !== null && r.auditId === 'lcp-discovery-insight',
    },
    {
      label: '旧 ID（largest-contentful-paint-element・table ラップ）でも取り出す',
      report: {
        audits: {
          'largest-contentful-paint-element': {
            details: { type: 'list', items: [{ type: 'table', items: [{ node: measuredNode }] }] },
          },
        },
      },
      expect: (r) => r !== null && r.auditId === 'largest-contentful-paint-element',
    },
    {
      label: '旧々 ID の非ラップ構造（items[0].node）でも取り出す',
      report: {
        audits: {
          'largest-contentful-paint-element': {
            details: { type: 'table', items: [{ node: measuredNode }] },
          },
        },
      },
      expect: (r) => r !== null && r.selector.endsWith('img.mx-auto'),
    },
    {
      label: 'LCP 要素が img でない（見出し）場合もそのまま返す',
      report: {
        audits: {
          'lcp-breakdown-insight': {
            details: {
              type: 'list',
              items: [{ type: 'node', selector: 'h1', snippet: '<h1>Gem Hunter</h1>' }],
            },
          },
        },
      },
      expect: (r) => r !== null && r.snippet === '<h1>Gem Hunter</h1>',
    },
    {
      label: 'audit 自体が無いレポートでは null',
      report: { audits: {} },
      expect: (r) => r === null,
    },
    {
      label: 'node を含まない details（table だけ）では null（空を要素ありと誤認しない）',
      report: {
        audits: {
          'lcp-breakdown-insight': {
            details: { type: 'list', items: [{ type: 'table', headings: [], items: [] }] },
          },
        },
      },
      expect: (r) => r === null,
    },
    {
      // 🔴 中身のない node を「要素あり」と誤認しないこと（node の空判定ガードの回帰ケース・#430）。
      //    ガードを常に真へ変異させると、この 1 件だけが FAIL する。
      label: 'snippet / selector / nodeLabel をすべて欠く node は要素とみなさず null',
      report: {
        audits: {
          'lcp-breakdown-insight': {
            details: { type: 'list', items: [{ type: 'node', lhId: 'page-0-IMG' }] },
          },
        },
      },
      expect: (r) => r === null,
    },
    {
      label: '空 node の後ろに実 node があればそちらを返す（空で打ち切らない）',
      report: {
        audits: {
          'lcp-breakdown-insight': {
            details: { type: 'list', items: [{ type: 'node' }, measuredNode] },
          },
        },
      },
      expect: (r) => r !== null && r.snippet.includes('hero-idle.webp'),
    },
    {
      label: 'report が undefined でも例外を投げず null',
      report: undefined,
      expect: (r) => r === null,
    },
  ]
  let ok = true
  for (const c of cases) {
    let actual
    try {
      actual = extractLcpElement(c.report)
    } catch (err) {
      actual = null
      console.log(`[run_lighthouse --self-test] 例外: ${err.message}`)
    }
    const pass = c.expect(actual)
    if (!pass) ok = false
    console.log(
      `[run_lighthouse --self-test] ${pass ? 'PASS' : 'FAIL'}: ${c.label}（実際: ${JSON.stringify(actual)}）`,
    )
  }
  return ok
}

function selfTest() {
  const cases = [
    { label: 'score=1.0 → PASS', input: 1.0, expectedStatus: 'PASS' },
    {
      label: '丸め誤差 score=0.9999999999999998（実質100点）→ PASS',
      input: 0.9999999999999998,
      expectedStatus: 'PASS',
    },
    { label: 'score=0.99 → GATE_FAIL', input: 0.99, expectedStatus: 'GATE_FAIL' },
    { label: 'score=undefined → INFRA_FAIL', input: undefined, expectedStatus: 'INFRA_FAIL' },
    { label: 'score=NaN → INFRA_FAIL', input: NaN, expectedStatus: 'INFRA_FAIL' },
  ]
  let ok = true
  for (const c of cases) {
    const result = evaluateAccessibilityGate(c.input)
    const pass = result.status === c.expectedStatus
    if (!pass) ok = false
    console.log(
      `[run_lighthouse --self-test] ${pass ? 'PASS' : 'FAIL'}: ${c.label}（実際: ${result.status}, rounded: ${result.rounded}）`,
    )
  }
  return ok
}

/** @type {Array<{proc: import('node:child_process').ChildProcess, name: string}>} */
const spawned = []

function log(msg) {
  console.log(`[run_lighthouse] ${msg}`)
}

function spawnTracked(name, command, args, opts) {
  // 🔴 `npx next start` は自身が「next-server」孫プロセスを spawn する（next のラッパー構造）。
  //    detached: true にせず親プロセスだけへ SIGTERM を送ると、孫プロセスは親から切り離されて
  //    init（pid 1）に再親化され、ポートを掴んだまま生き残ってしまう（実測で確認済みの実害）。
  //    detached: true でプロセスグループを分け、cleanup では process.kill(-pid, sig) で
  //    グループごと（孫プロセスまで含めて）終了させる。
  const proc = spawn(command, args, { cwd: REPO_ROOT, detached: true, ...opts })
  spawned.push({ proc, name })
  return proc
}

function killGroup(pid, signal) {
  try {
    process.kill(-pid, signal)
  } catch {
    // グループ kill が使えない/既に全滅している場合は単体 kill にフォールバック
    try {
      process.kill(pid, signal)
    } catch {
      // すでに終了している場合は無視
    }
  }
}

async function cleanup() {
  const pending = spawned.splice(0)
  for (const { proc, name } of pending) {
    if (proc.exitCode === null && proc.signalCode === null && proc.pid) {
      log(`後始末: ${name}（pid=${proc.pid}）のプロセスグループを終了します`)
      killGroup(proc.pid, 'SIGTERM')
    }
  }
  // SIGTERM で終わらないプロセスに時間を与える
  await new Promise((resolve) => setTimeout(resolve, 1000))
  for (const { proc, name } of pending) {
    if (proc.exitCode === null && proc.signalCode === null && proc.pid) {
      log(`後始末: ${name}（pid=${proc.pid}）のプロセスグループに SIGKILL を送ります`)
      killGroup(proc.pid, 'SIGKILL')
    }
  }
}

function waitForServer(url, timeoutMs) {
  const deadline = Date.now() + timeoutMs
  return new Promise((resolve, reject) => {
    const tick = async () => {
      try {
        const res = await fetch(url)
        if (res.status < 500) {
          resolve()
          return
        }
      } catch {
        // まだ起動していない
      }
      if (Date.now() > deadline) {
        reject(new Error(`${url} が ${timeoutMs}ms 以内に応答しませんでした`))
        return
      }
      setTimeout(tick, 300)
    }
    tick()
  })
}

function runCommand(name, command, args, opts) {
  return new Promise((resolve, reject) => {
    const proc = spawn(command, args, { cwd: REPO_ROOT, stdio: 'inherit', ...opts })
    proc.on('error', reject)
    proc.on('exit', (code) => {
      if (code === 0) {
        resolve()
      } else {
        reject(new Error(`${name} が exit ${code} で終了しました`))
      }
    })
  })
}

function runLighthouse(url) {
  return new Promise((resolve) => {
    const lighthouseBin = path.join(REPO_ROOT, 'node_modules', '.bin', 'lighthouse')
    const args = [
      url,
      '--output=json',
      '--output-path=stdout',
      '--only-categories=accessibility,performance',
      '--chrome-flags=--headless=new --no-sandbox --ssl-version-max=tls1.2',
      '--quiet',
    ]
    const proc = spawn(lighthouseBin, args, {
      cwd: REPO_ROOT,
      env: { ...process.env, CHROME_PATH },
    })
    let stdout = ''
    let stderr = ''
    proc.stdout.on('data', (chunk) => {
      stdout += chunk
    })
    proc.stderr.on('data', (chunk) => {
      stderr += chunk
    })
    proc.on('error', (err) => {
      resolve({ ok: false, stderr: `${stderr}\n${err.message}` })
    })
    proc.on('exit', () => {
      const trimmed = stdout.trim()
      if (!trimmed) {
        resolve({ ok: false, stderr })
        return
      }
      try {
        const parsed = JSON.parse(trimmed)
        resolve({ ok: true, report: parsed })
      } catch (err) {
        resolve({ ok: false, stderr: `JSON パースに失敗しました: ${err.message}\n${stderr}` })
      }
    })
  })
}

async function main() {
  let stubReady = false
  let appReady = false

  try {
    log(`スタブ GitHub API サーバーを起動します（port ${STUB_PORT}）`)
    spawnTracked('stub server', 'node', ['e2e/stub/server.mjs'], {
      env: { ...process.env, E2E_STUB_PORT: STUB_PORT },
      stdio: 'inherit',
    })
    await waitForServer(`http://127.0.0.1:${STUB_PORT}/search/repositories?q=x`, 15_000)
    stubReady = true
    log('スタブサーバーの起動を確認しました')

    log('next build を実行します')
    await runCommand('next build', 'npx', ['next', 'build'])

    log(`next start --port ${APP_PORT} を起動します`)
    spawnTracked('next start', 'npx', ['next', 'start', '--port', APP_PORT], {
      env: {
        ...process.env,
        // ダミー GitHub OAuth 環境変数一式は e2e/stub/e2e-env.mjs（共有モジュール）に集約済み。
        // playwright.config.ts（E2E: stub 8788 / app 3100）と同じ値セットを個別に複製しない
        // （SP-10・GitGuardian 誤検知の再発防止）。
        ...buildDummyGitHubEnv({ stubPort: STUB_PORT, appUrl: BASE_URL }),
        PORT: APP_PORT,
      },
      stdio: 'inherit',
    })
    await waitForServer(BASE_URL, 60_000)
    appReady = true
    log('アプリサーバーの起動を確認しました')

    let hasInfraFail = false
    let hasGateFail = false
    const summaryLines = []

    for (const target of TARGETS) {
      log(`Lighthouse 実行中: ${target.page}（${target.url}）`)
      const result = await runLighthouse(target.url)
      if (!result.ok) {
        hasInfraFail = true
        console.error(
          `[run_lighthouse] INFRA_FAIL: ${target.page} の Lighthouse 実行に失敗しました（JSON が生成されませんでした）`,
        )
        if (result.stderr) {
          console.error(result.stderr)
        }
        continue
      }
      const a11yScore = result.report?.categories?.accessibility?.score
      const perfScore = result.report?.categories?.performance?.score
      if (typeof a11yScore !== 'number' || typeof perfScore !== 'number') {
        hasInfraFail = true
        console.error(
          `[run_lighthouse] INFRA_FAIL: ${target.page} のレポートに categories.accessibility/performance が含まれていません`,
        )
        continue
      }
      const perf100 = Math.round(perfScore * 100)
      const gate = evaluateAccessibilityGate(a11yScore)
      if (gate.status !== 'PASS') {
        hasGateFail = true
        console.error(
          `[run_lighthouse] GATE_FAIL: ${target.page} Accessibility ${gate.rounded}/100（しきい値 100） (perf=${perf100})`,
        )
      } else {
        summaryLines.push(`${target.page}: Accessibility ${gate.rounded}/100 (perf=${perf100})`)
      }
      // LCP 要素は判定に使わず記録のみ（Performance と同じ扱い・Issue #355）。
      const lcp = extractLcpElement(result.report)
      summaryLines.push(
        `${target.page}: LCP 要素 = ${lcp ? (lcp.snippet ?? lcp.selector ?? lcp.nodeLabel) : '（audit なし）'}`,
      )
    }

    for (const line of summaryLines) {
      log(line)
    }

    if (hasInfraFail) {
      console.error('[run_lighthouse] INFRA_FAIL: 1 画面以上で Lighthouse 自体が完走しませんでした')
      process.exitCode = 1
      return
    }
    if (hasGateFail) {
      process.exitCode = 1
      return
    }
    log('PASS: 全対象画面で Accessibility = 100/100 です')
    process.exitCode = 0
  } catch (err) {
    console.error(
      `[run_lighthouse] INFRA_FAIL: ${err instanceof Error ? err.message : String(err)}`,
    )
    process.exitCode = 1
  } finally {
    if (!stubReady) {
      log('スタブサーバーの起動確認前に終了しました')
    }
    if (!appReady) {
      log('アプリサーバーの起動確認前に終了しました')
    }
    await cleanup()
  }
}

if (process.argv.includes('--self-test')) {
  const gateOk = selfTest()
  const lcpOk = selfTestLcpExtraction()
  process.exitCode = gateOk && lcpOk ? 0 : 1
} else {
  main()
}
