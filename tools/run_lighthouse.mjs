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
//   3. CHROME_PATH=/opt/pw-browsers/chromium を明示して Lighthouse を対象 2 画面に実行
//      - 一覧（検索実行後の状態）: /ja?q=react
//      - 詳細: /ja/repos/octostub/octo-widgets
//   4. categories.accessibility.score < 1.0 なら GATE_FAIL（非ゼロ exit）。
//      categories.performance.score は判定に使わず記録出力のみ。
//   5. JSON が生成されなかった／Chrome 起動に失敗した場合は INFRA_FAIL で区別する
//      （「チェッカー自体が落ちた」と「本当に a11y が落ちた」を混同しない）。
//
// 起動したプロセス（stub / next start）は正常終了・異常終了を問わず必ず後始末する。
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

const TARGETS = [
  { page: '一覧（検索実行後）', url: `${BASE_URL}/ja?q=react` },
  { page: '詳細', url: `${BASE_URL}/ja/repos/octostub/octo-widgets` },
]

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
        console.error(`[run_lighthouse] INFRA_FAIL: ${target.page} の Lighthouse 実行に失敗しました（JSON が生成されませんでした）`)
        if (result.stderr) {
          console.error(result.stderr)
        }
        continue
      }
      const a11yScore = result.report?.categories?.accessibility?.score
      const perfScore = result.report?.categories?.performance?.score
      if (typeof a11yScore !== 'number' || typeof perfScore !== 'number') {
        hasInfraFail = true
        console.error(`[run_lighthouse] INFRA_FAIL: ${target.page} のレポートに categories.accessibility/performance が含まれていません`)
        continue
      }
      const a11y100 = Math.round(a11yScore * 100)
      const perf100 = Math.round(perfScore * 100)
      if (a11yScore < 1.0) {
        hasGateFail = true
        console.error(`[run_lighthouse] GATE_FAIL: ${target.page} Accessibility ${a11y100}/100（しきい値 100） (perf=${perf100})`)
      } else {
        summaryLines.push(`${target.page}: Accessibility ${a11y100}/100 (perf=${perf100})`)
      }
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
    console.error(`[run_lighthouse] INFRA_FAIL: ${err instanceof Error ? err.message : String(err)}`)
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

main()
