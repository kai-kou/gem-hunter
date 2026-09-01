import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import { resolveChromiumExecutablePath } from './e2e-chromium-executable.mjs'

/** @type {string[]} 各テストで作った一時ディレクトリ（afterEach で確実に掃除する）。 */
const tmpDirs = []

function makeTmpDir() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'e2e-chromium-executable-'))
  tmpDirs.push(dir)
  return dir
}

/** 実在する「実行ファイル」を tmp 配下に作る（中身は空でよい・statSync().isFile() だけが問われる）。 */
function makeExecutableFile(...segments) {
  const filePath = path.join(...segments)
  fs.mkdirSync(path.dirname(filePath), { recursive: true })
  fs.writeFileSync(filePath, '')
  return filePath
}

afterEach(() => {
  while (tmpDirs.length > 0) {
    const dir = tmpDirs.pop()
    fs.rmSync(dir, { recursive: true, force: true })
  }
})

describe('resolveChromiumExecutablePath', () => {
  it('分岐1: E2E_CHROMIUM_EXECUTABLE が設定されていれば無条件で最優先返却する', () => {
    const result = resolveChromiumExecutablePath({
      env: { E2E_CHROMIUM_EXECUTABLE: '/explicit/override/chrome' },
      // 他の分岐が評価されていないことも兼ねて確認する（呼ばれたら即エラー）。
      getDefaultExecutablePath: () => {
        throw new Error(
          'getDefaultExecutablePath should not be called when explicit override is set',
        )
      },
    })
    expect(result).toBe('/explicit/override/chrome')
  })

  it('分岐2: 既定解決の実行ファイルが実在すれば undefined を返す（介入しない）', () => {
    const tmpDir = makeTmpDir()
    const defaultPath = makeExecutableFile(tmpDir, 'default-chrome')

    const result = resolveChromiumExecutablePath({
      env: {},
      getDefaultExecutablePath: () => defaultPath,
    })
    expect(result).toBeUndefined()
  })

  it('分岐3: PLAYWRIGHT_BROWSERS_PATH 未設定なら探索せず undefined を返す', () => {
    const result = resolveChromiumExecutablePath({
      env: {},
      getDefaultExecutablePath: () => '/nonexistent/default/chrome',
    })
    expect(result).toBeUndefined()
  })

  it('分岐4a: 既定解決が不在でも <PLAYWRIGHT_BROWSERS_PATH>/chromium（直指し）が実在すれば返す', () => {
    const tmpDir = makeTmpDir()
    const directChromium = makeExecutableFile(tmpDir, 'chromium')

    const result = resolveChromiumExecutablePath({
      env: { PLAYWRIGHT_BROWSERS_PATH: tmpDir },
      getDefaultExecutablePath: () =>
        path.join(tmpDir, 'chromium-1234', 'chrome-linux64', 'chrome'),
    })
    expect(result).toBe(directChromium)
  })

  it('分岐4b: 直指し chromium が無ければ chromium-*/chrome-linux/chrome を探す', () => {
    const tmpDir = makeTmpDir()
    const versioned = makeExecutableFile(tmpDir, 'chromium-1194', 'chrome-linux', 'chrome')

    const result = resolveChromiumExecutablePath({
      env: { PLAYWRIGHT_BROWSERS_PATH: tmpDir },
      getDefaultExecutablePath: () =>
        path.join(tmpDir, 'chromium-1234', 'chrome-linux64', 'chrome'),
    })
    expect(result).toBe(versioned)
  })

  it('分岐4c: chrome-linux/chrome も無ければ chromium-*/chrome-linux64/chrome を探す', () => {
    const tmpDir = makeTmpDir()
    const versioned64 = makeExecutableFile(tmpDir, 'chromium-1234', 'chrome-linux64', 'chrome')

    const result = resolveChromiumExecutablePath({
      env: { PLAYWRIGHT_BROWSERS_PATH: tmpDir },
      getDefaultExecutablePath: () => '/nonexistent/default/chrome',
    })
    expect(result).toBe(versioned64)
  })

  it('分岐5: PLAYWRIGHT_BROWSERS_PATH 配下に候補が何も無ければ undefined を返す', () => {
    const tmpDir = makeTmpDir()

    const result = resolveChromiumExecutablePath({
      env: { PLAYWRIGHT_BROWSERS_PATH: tmpDir },
      getDefaultExecutablePath: () => '/nonexistent/default/chrome',
    })
    expect(result).toBeUndefined()
  })

  it('負ケース(#750): 候補パスが実行ファイルではなくディレクトリの場合はスキップして続行する', () => {
    const tmpDir = makeTmpDir()
    // <PLAYWRIGHT_BROWSERS_PATH>/chromium がディレクトリ（壊れたインストール等）でも
    // isFile() で弾かれ、次の候補（chrome-linux/chrome）まで探索が続くことを確認する。
    fs.mkdirSync(path.join(tmpDir, 'chromium'))
    const versioned = makeExecutableFile(tmpDir, 'chromium-1194', 'chrome-linux', 'chrome')

    const result = resolveChromiumExecutablePath({
      env: { PLAYWRIGHT_BROWSERS_PATH: tmpDir },
      getDefaultExecutablePath: () => '/nonexistent/default/chrome',
    })
    expect(result).toBe(versioned)
  })

  it('symlink 実例: <PLAYWRIGHT_BROWSERS_PATH>/chromium が実行ファイルへの symlink でも実在扱いになる', () => {
    const tmpDir = makeTmpDir()
    const realExecutable = makeExecutableFile(tmpDir, 'chromium-1194', 'chrome-linux', 'chrome')
    const symlinkPath = path.join(tmpDir, 'chromium')
    fs.symlinkSync(realExecutable, symlinkPath)

    const result = resolveChromiumExecutablePath({
      env: { PLAYWRIGHT_BROWSERS_PATH: tmpDir },
      getDefaultExecutablePath: () => '/nonexistent/default/chrome',
    })
    expect(result).toBe(symlinkPath)
  })
})
