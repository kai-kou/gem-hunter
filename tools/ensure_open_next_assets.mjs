// tools/ensure_open_next_assets.mjs — `.open-next/assets` の鮮度チェックと不足時の自動ビルド
// （Issue #454 / #455 / #457 の再発防止）。
//
// 【背景】
// E2E は Playwright webServer から `next build && next start`（Node.js ランタイム）でアプリを
// 起動する（`playwright.config.ts`）。ところが `getCloudflareContext({ async: true })`
// （`@opennextjs/cloudflare`）は `NEXT_RUNTIME=nodejs`（= `next start` の既定ランタイム）でも
// wrangler の `getPlatformProxy()` を実際に呼び出し、`wrangler.jsonc` の `assets.directory`
// （`.open-next/assets`）を指す `env.ASSETS` バインディングを用意してしまう
// （`node_modules/@opennextjs/cloudflare/dist/api/cloudflare-context.js` `getCloudflareContextAsync`）。
// つまり `opennextjs-cloudflare build` を一度も実行していない状態で `next build && next start` だけを
// 行っても、Gem Index の読み取り（`src/infrastructure/platform/asset-reader.ts` の
// `createWorkersAssetReader`）は `public/` ではなく `.open-next/assets/data/gem-index/*` を
// 実際に読みに行く。このディレクトリが存在しないと 404 になり、Gem バッジ・Gem 一覧が
// 静かに空になって E2E が「実装は正しいのに落ちる」形で失敗する。
//
// 【本ツールの役割】
// `AssetReader` が実際に配信する唯一の内容である `public/` の mtime と、
// `.open-next/assets/data/gem-index/index.json`（マーカー）の mtime を比較し、
// マーカーが無い・`public/` の方が新しい場合だけ `npx opennextjs-cloudflare build` を実行する。
// 毎回フルビルドし直すとローカル/CI のビルド時間を不必要に伸ばすため、鮮度チェックで
// 不要な再ビルドを避ける（ビルド失敗はそのまま非ゼロ終了で伝播し、黙って緑にしない）。
//
// 【呼び出し元（2 か所・ロジックを二重実装しない）】
//   1. tools/run_checks.sh（E2E ステップの直前・run_checks サマリー表に可視化するため）
//   2. playwright.config.ts の webServer command（run_checks.sh を経由しない直接の
//      `npx playwright test` 実行でも黙って 404 に落ちないための安全網）
//
// 使い方:
//   node tools/ensure_open_next_assets.mjs
//   node tools/ensure_open_next_assets.mjs --self-test   # ネットワーク・実ビルド非依存のユニットテスト

import { execFileSync } from 'node:child_process'
import {
  existsSync,
  mkdirSync,
  readdirSync,
  rmSync,
  statSync,
  utimesSync,
  writeFileSync,
} from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

/** `AssetReader`（`resolveAssetReader()`）が実際に配信する唯一のディレクトリ。 */
const PUBLIC_DIR_NAME = 'public'
/** `wrangler.jsonc` の `assets.directory` が指す先（`.open-next/assets`）配下のマーカー。 */
const MARKER_RELATIVE_PATH = path.join('.open-next', 'assets', 'data', 'gem-index', 'index.json')

/**
 * `dir` 配下の全ファイル（再帰）のうち最も新しい mtime（ms）。ファイルが 1 つも無ければ 0。
 * ディレクトリ自体が存在しない場合も 0（呼び出し側で「比較材料なし」として扱う）。
 */
export function newestMtimeMs(dir) {
  if (!existsSync(dir)) {
    return 0
  }
  let newest = 0
  for (const entry of readdirSync(dir, { withFileTypes: true, recursive: true })) {
    if (!entry.isFile()) {
      continue
    }
    // `Dirent.parentPath`（Node 20.12+ / 21.4+）。無い実行環境向けに旧 `path` へフォールバックする。
    const parent = entry.parentPath ?? entry.path
    const mtime = statSync(path.join(parent, entry.name)).mtimeMs
    if (mtime > newest) {
      newest = mtime
    }
  }
  return newest
}

/**
 * `.open-next/assets` の再ビルドが必要かを判定する（純関数・`--self-test` の対象）。
 *
 * @param {string} publicDir `public/` の絶対パス
 * @param {string} markerPath マーカーファイルの絶対パス
 * @returns {{ stale: boolean, reason: string }}
 */
export function checkStaleness(publicDir, markerPath) {
  if (!existsSync(markerPath)) {
    return {
      stale: true,
      reason: `${path.relative(REPO_ROOT, markerPath)} が存在しません（opennextjs-cloudflare build 未実行）`,
    }
  }
  const markerMtime = statSync(markerPath).mtimeMs
  const publicMtime = newestMtimeMs(publicDir)
  if (publicMtime > markerMtime) {
    return {
      stale: true,
      reason: `${path.relative(REPO_ROOT, publicDir)}/ 配下に .open-next/assets より新しいファイルがあります`,
    }
  }
  return { stale: false, reason: '' }
}

function main() {
  const publicDir = path.join(REPO_ROOT, PUBLIC_DIR_NAME)
  const markerPath = path.join(REPO_ROOT, MARKER_RELATIVE_PATH)

  const { stale, reason } = checkStaleness(publicDir, markerPath)
  if (!stale) {
    console.log(
      '[ensure_open_next_assets] .open-next/assets は最新のため opennextjs-cloudflare build をスキップしました',
    )
    return
  }

  console.log(`[ensure_open_next_assets] ${reason}。npx opennextjs-cloudflare build を実行します`)
  execFileSync('npx', ['opennextjs-cloudflare', 'build'], {
    cwd: REPO_ROOT,
    stdio: 'inherit',
  })
  console.log('[ensure_open_next_assets] opennextjs-cloudflare build が完了しました')
}

// ============================================================
// self-test（ネットワーク・実ビルド非依存。一時ディレクトリだけで完結する）
// ============================================================

function selfTest() {
  const failures = []
  const assert = (label, cond) => {
    if (!cond) {
      failures.push(label)
    }
  }

  const workDir = path.join(tmpdir(), `ensure-open-next-assets-selftest-${process.pid}-${Date.now()}`)
  const publicDir = path.join(workDir, 'public')
  const markerDir = path.join(workDir, '.open-next', 'assets', 'data', 'gem-index')
  const markerPath = path.join(markerDir, 'index.json')

  try {
    mkdirSync(publicDir, { recursive: true })

    // --- マーカー不在 = stale ---
    assert(
      'checkStaleness: マーカーが存在しなければ stale',
      checkStaleness(publicDir, markerPath).stale === true,
    )

    // --- マーカーだけ作る（public/ は空） ---
    mkdirSync(markerDir, { recursive: true })
    writeFileSync(markerPath, '{}')
    assert(
      'checkStaleness: public/ が空でマーカーがあれば stale ではない',
      checkStaleness(publicDir, markerPath).stale === false,
    )

    // --- public/ にマーカーより新しいファイルを置く = stale ---
    const publicFile = path.join(publicDir, 'data', 'gem-index', 'npmjs-org.json')
    mkdirSync(path.dirname(publicFile), { recursive: true })
    // mtime を明示的に未来へずらす（同一ティックでの実行でも確実に「新しい」と判定させるため）。
    const future = new Date(Date.now() + 10_000)
    writeFileSync(publicFile, '{}')
    utimesSync(publicFile, future, future)
    assert(
      'checkStaleness: public/ にマーカーより新しいファイルがあれば stale',
      checkStaleness(publicDir, markerPath).stale === true,
    )

    // --- マーカーを public/ より新しく更新し直すと stale が解消する ---
    writeFileSync(markerPath, '{}')
    const laterMtime = new Date(future.getTime() + 10_000)
    utimesSync(markerPath, laterMtime, laterMtime)
    assert(
      'checkStaleness: マーカーを public/ より新しくすると stale ではない',
      checkStaleness(publicDir, markerPath).stale === false,
    )

    // --- newestMtimeMs: 存在しないディレクトリは 0 ---
    assert(
      'newestMtimeMs: 存在しないディレクトリは 0',
      newestMtimeMs(path.join(workDir, 'no-such-dir')) === 0,
    )

    // --- newestMtimeMs: 空ディレクトリは 0 ---
    const emptyDir = path.join(workDir, 'empty')
    mkdirSync(emptyDir, { recursive: true })
    assert('newestMtimeMs: 空ディレクトリは 0', newestMtimeMs(emptyDir) === 0)
  } finally {
    rmSync(workDir, { recursive: true, force: true })
  }

  if (failures.length > 0) {
    console.error(`FAIL: ensure_open_next_assets.mjs --self-test（${failures.length} 件失敗）`)
    for (const f of failures) {
      console.error(`  - ${f}`)
    }
    process.exit(1)
  }
  console.log('PASS: ensure_open_next_assets.mjs --self-test')
}

const isMainModule =
  typeof process.argv[1] === 'string' &&
  path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url))

if (isMainModule) {
  const argv = process.argv.slice(2)
  if (argv.includes('--self-test')) {
    selfTest()
  } else {
    main()
  }
}
