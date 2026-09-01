// tools/e2e-chromium-executable.mjs — クラウド実行環境のプリインストール Chromium への
// フォールバック実行ファイル解決（Issue #629）。
//
// クラウドコンテナは `PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers` にプリインストール済みの
// Chromium を持つが、`@playwright/test` が要求するビルド番号とプリインストール版のビルド番号が
// 食い違うことがあり、その場合 `chromium.executablePath()` は存在しないパスを返す
// （実測: `/opt/pw-browsers/chromium-1234/chrome-linux64/chrome` は存在せず、実体は
// `/opt/pw-browsers/chromium-1194/chrome-linux/chrome`）。本モジュールは `playwright.config.ts` /
// `playwright.workers.config.ts` の両方から呼び出す共有のフォールバック解決ロジックを 1 箇所に
// 集約する（`e2e/stub/e2e-env.mjs` と同じ「2 config が個別に複製しない」方針）。
//
// 置き場所を `tools/` にした理由: `vitest.config.mts` の `tools` project が
// `tools/**/*.{test,spec}.mjs` を Node 環境で自動収集する（`e2e/stub/` はどの project の
// `include` にも入っておらず、`vitest.config.mts` の編集は本タスクの変更許可範囲外のため、
// 既存の収集対象に収まる `tools/` を選んだ）。

import fs from 'node:fs'
import path from 'node:path'
import { chromium } from '@playwright/test'

/**
 * プリインストール Chromium 実行ファイルへのフォールバックパスを解決する。
 *
 * 🔴 劣化の向き（フォールバック順・#793）— 上から順に評価し、最初に確定した結果を返す:
 *
 *   1. `env.E2E_CHROMIUM_EXECUTABLE` が設定されていれば、それを無条件で最優先返却する
 *      （明示上書き。実在チェックはしない — 利用者の明示指定を尊重する）。
 *   2. 既定解決（`getDefaultExecutablePath`、通常は `chromium.executablePath()`）が指す
 *      パスが実在する「通常ファイル」であれば `undefined` を返す（＝呼び出し側は
 *      `launchOptions.executablePath` に何も代入せず Playwright の既定解決に任せる。
 *      ローカル・CI の正常系はここで抜け、本フォールバックは介入しない）。
 *   3. `env.PLAYWRIGHT_BROWSERS_PATH` が未設定なら、それ以上探索せず `undefined` を返す
 *      （未設定環境で `/opt/...` 等を推測探索しない）。
 *   4. 設定されていれば、以下の優先順で「実在する通常ファイル」を探して最初に見つかった
 *      ものの絶対パスを返す（ディレクトリや壊れた symlink はスキップする・#750）:
 *        a. `<PLAYWRIGHT_BROWSERS_PATH>/chromium`（プリインストール環境の symlink。
 *           実行ファイルを直接指す）
 *        b. `<PLAYWRIGHT_BROWSERS_PATH>/chromium-{version}/chrome-linux/chrome`
 *           （`chromium-` 始まりのディレクトリ名降順で走査）
 *        c. `<PLAYWRIGHT_BROWSERS_PATH>/chromium-{version}/chrome-linux64/chrome`
 *   5. どれも見つからなければ `undefined` を返す（Playwright 本来の「ブラウザが見つからない」
 *      エラーメッセージを消さない fail-open にはしない — 呼び出し側は `undefined` のとき
 *      `launchOptions.executablePath` を省略し、Playwright 既定のエラーに任せること）。
 *
 * @param {object} [options]
 * @param {NodeJS.ProcessEnv} [options.env] - 参照する環境変数（既定 `process.env`）。
 * @param {() => string} [options.getDefaultExecutablePath] - 既定解決を返す関数
 *   （既定は `() => chromium.executablePath()`）。この関数が例外を投げた場合、本関数は
 *   その例外をそのまま再送出する（既定解決自体が壊れている＝Playwright インストールが
 *   壊れているシグナルを握り潰さないため）。
 * @returns {string | undefined} 実在するプリインストール実行ファイルの絶対パス。
 *   解決できない・介入不要な場合は `undefined`。
 */
export function resolveChromiumExecutablePath({
  env = process.env,
  getDefaultExecutablePath,
} = {}) {
  const explicit = env.E2E_CHROMIUM_EXECUTABLE
  if (explicit) {
    return explicit
  }

  const resolveDefault = getDefaultExecutablePath ?? (() => chromium.executablePath())
  const defaultPath = resolveDefault()
  if (isExecutableFile(defaultPath)) {
    return undefined
  }

  const browsersPath = env.PLAYWRIGHT_BROWSERS_PATH
  if (!browsersPath) {
    return undefined
  }

  const directCandidate = path.join(browsersPath, 'chromium')
  if (isExecutableFile(directCandidate)) {
    return directCandidate
  }

  for (const versionedDir of listVersionedChromiumDirs(browsersPath)) {
    for (const relativeExecutable of ['chrome-linux/chrome', 'chrome-linux64/chrome']) {
      const candidate = path.join(browsersPath, versionedDir, relativeExecutable)
      if (isExecutableFile(candidate)) {
        return candidate
      }
    }
  }

  return undefined
}

/** @param {string | undefined} candidatePath @returns {boolean} */
function isExecutableFile(candidatePath) {
  if (!candidatePath) {
    return false
  }
  try {
    return fs.statSync(candidatePath).isFile()
  } catch {
    return false
  }
}

/** @param {string} browsersPath @returns {string[]} バージョンディレクトリ名の降順一覧 */
function listVersionedChromiumDirs(browsersPath) {
  try {
    return fs
      .readdirSync(browsersPath)
      .filter((name) => name.startsWith('chromium-'))
      .sort()
      .reverse()
  } catch {
    return []
  }
}
