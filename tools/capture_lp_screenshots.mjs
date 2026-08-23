/**
 * site/（ランディングページ）に載せるアプリ実画面のスクリーンショットを撮り直す。
 *
 * 前提: アプリを本番ビルドしてローカルで起動しておく（dev サーバーは CSS の
 * パース差でスタイルが当たらないことがあるため使わない）。
 *
 *   npx next build
 *   npx next start -p 3100
 *   node tools/capture_lp_screenshots.mjs
 *
 * 別ポートで起動した場合は `LP_SHOT_BASE=http://localhost:PORT node tools/capture_lp_screenshots.mjs`。
 *
 * 出力: site/assets/img/shot-search.webp / shot-digest.webp / shot-mobile.webp
 * 出力後に site/index.html の該当 <img> の width / height と実寸を突き合わせ、
 * 食い違っていれば非ゼロ終了する（撮り直し後の属性更新漏れ = CLS の原因を機械で止める）。
 *
 * 注意:
 * - アバターは avatars.githubusercontent.com から取得する。**取得できない環境では撮影を中断する**
 *   （壊れた画像のまま LP に載せないため）。取得は `curl` 経由なので HTTPS プロキシ配下でも動く。
 * - 日本語グリフを持たない Geist のフォールバックが明朝になる環境があるため、
 *   撮影時だけサンセリフの CJK フォールバックを注入する（表示は実利用環境と同等）。
 *
 * 🔴 `LP_SHOT_FETCH_VIA_CURL=1`（既定 off）はこのクラウドサンドボックス固有の回避策であり、
 * 恒久のベストプラクティスではない。このコンテナの Chromium は外部 HTTPS への直接接続・
 * プロキシ経由の両方が `ERR_CONNECTION_RESET` になる（`--ssl-version-max=tls1.2`（L-126）を
 * 足しても解消しない）。一方 `curl` は `HTTPS_PROXY` と CA バンドルが設定済みで通るため、
 * on にすると全リクエストを `curl` 経由で取得して差し替える。既定を本番直叩きにしない理由:
 * ① 本番の共有 API レート枠を実ユーザーと食い合う ② コードとデータの両方が撮影のたびに
 * 変わり再現性が壊れる。
 */
import { chromium } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const BASE = process.env.LP_SHOT_BASE ?? 'http://localhost:3100'
const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const IMG_DIR = join(ROOT, 'site/assets/img')
const AVATAR_HOST = 'avatars.githubusercontent.com'
// このサンドボックス固有の回避策（ファイル冒頭コメント参照）。既定 off。
const FETCH_VIA_CURL = process.env.LP_SHOT_FETCH_VIA_CURL === '1'

const FONT_FIX = `
  body, body * { font-family: var(--font-geist-sans), "IPAPGothic", "IPAGothic", "Noto Sans JP", sans-serif !important; }
  code, pre, .font-mono { font-family: var(--font-geist-mono), monospace !important; }
`

/**
 * `width` は **出力 WebP の横幅**。撮影実寸（clip 幅 or viewport 幅 × deviceScaleFactor 2）からの
 * 縮小率がそのまま図版内の文字サイズになるため、viewport / clip を変えたら width も見直すこと。
 */
const SHOTS = [
  {
    name: 'shot-search',
    path: '/ja?q=react',
    viewport: { width: 1280, height: 820 },
    width: 1600,
  },
  {
    // 「今日の Gem」の見出し〜2 位までを拡大トリミングする（俯瞰だと文字が実効 6〜7px で読めない）
    name: 'shot-digest',
    path: '/ja',
    viewport: { width: 1280, height: 1500 },
    width: 1100,
    clipFrom: () => {
      const heading = Array.from(document.querySelectorAll('h2')).find((h) =>
        h.textContent.includes('今日の Gem'),
      )
      const items = document.querySelectorAll('ol > li')
      if (!heading || items.length < 2) return null
      const top = heading.getBoundingClientRect().top + window.scrollY - 18
      const bottom = items[1].getBoundingClientRect().bottom + window.scrollY + 10
      const main = document.querySelector('main').getBoundingClientRect()
      return {
        x: Math.round(main.left - 16),
        y: Math.round(top),
        width: Math.round(main.width + 32),
        height: Math.round(bottom - top),
      }
    },
  },
  {
    // ヒーローの主役。`shot-search` と同じキーワードで撮り、PC 版との対比が成立するようにする
    name: 'shot-mobile',
    path: '/ja?q=react',
    viewport: { width: 390, height: 780 },
    width: 640,
  },
  {
    name: 'shot-gems',
    path: '/ja/gems?q=react',
    viewport: { width: 1280, height: 760 },
    width: 1600,
  },
]

const avatarCache = new Map()
function fetchAvatar(url) {
  if (avatarCache.has(url)) return avatarCache.get(url)
  try {
    const buf = execFileSync(
      'curl',
      ['-sSfL', '--proto', '=https', '--proto-redir', '=https', '--max-redirs', '3', '--max-time', '20', url],
      { maxBuffer: 20e6 },
    )
    avatarCache.set(url, buf)
    return buf
  } catch {
    return null
  }
}

// FETCH_VIA_CURL 用: 任意 URL を curl 経由で取得して { status, contentType, body } を返す。
// このコンテナは Chromium からの外部 HTTPS が直接/プロキシ経由とも ERR_CONNECTION_RESET になるため
// （ファイル冒頭コメント参照）、代わりに HTTPS_PROXY / CA バンドルが設定済みの curl で取得する。
//
// 🔴 このサンドボックスの GitHub API プロキシは `github.com` 宛のリクエストを
// 「repo スコープの REST パスのみ許可」に制限しており、`github.com/{user}.png?size=N`
// （GitHub のアバター短縮 URL）は 403 になる。同じ画像を配信する
// `avatars.githubusercontent.com` はプロキシの制限対象外で通るため、curl 前にそちらへ書き換える。
function rewriteForProxy(url) {
  try {
    const parsed = new URL(url)
    const match = parsed.hostname === 'github.com' && parsed.pathname.match(/^\/([^/]+)\.png$/)
    if (!match) return url
    const rewritten = new URL(`https://avatars.githubusercontent.com/${match[1]}`)
    rewritten.search = parsed.search
    return rewritten.href
  } catch {
    return url
  }
}

let curlSeq = 0
function curlFetch(url) {
  const n = curlSeq++
  const headerPath = join(tempDir, `curl-h-${n}`)
  const bodyPath = join(tempDir, `curl-b-${n}`)
  try {
    execFileSync(
      'curl',
      ['-sS', '-L', '--max-time', '40', '-D', headerPath, '-o', bodyPath, rewriteForProxy(url)],
      { maxBuffer: 60e6 },
    )
  } catch {
    return null
  }
  const blocks = readFileSync(headerPath, 'utf8').split(/\r?\n\r?\n/).filter((block) => block.trim())
  const last = blocks[blocks.length - 1]
  return {
    status: Number(last.match(/HTTP\/[\d.]+ (\d+)/)?.[1] ?? 200),
    contentType: last.match(/^content-type:\s*(.+)$/im)?.[1]?.trim() ?? 'application/octet-stream',
    body: readFileSync(bodyPath),
  }
}

const tempDir = mkdtempSync(join(tmpdir(), 'lp-shot-'))
// `--ssl-version-max=tls1.2`: このサンドボックスの Chromium は既定の TLS 設定だと外部 HTTPS への
// 接続が ERR_CONNECTION_RESET になるための回避策（L-126・`playwright.config.ts` と同じ理由）。
const browser = await chromium.launch({ args: ['--ssl-version-max=tls1.2'] })
const written = []

try {
  for (const shot of SHOTS) {
    const context = await browser.newContext({
      viewport: shot.viewport,
      deviceScaleFactor: 2,
      locale: 'ja-JP',
    })
    if (FETCH_VIA_CURL) {
      // 全リクエストを curl 経由で取得する（ファイル冒頭コメント参照）。data: と localhost 宛は
      // Chromium にそのまま任せる（アプリ自身への同一プロセス内リクエストは接続リセットの対象外）。
      await context.route('**', async (route) => {
        const requested = route.request().url()
        if (
          requested.startsWith('data:') ||
          requested.startsWith('http://localhost') ||
          requested.startsWith('http://127.0.0.1')
        ) {
          await route.continue()
          return
        }
        const fetched = curlFetch(requested)
        if (fetched === null) {
          await route.abort()
          return
        }
        await route.fulfill({ status: fetched.status, contentType: fetched.contentType, body: fetched.body })
      })
    } else {
      // glob だけではホスト名を保証できない（部分一致で任意ホストが通る）ため URL で厳密に判定する
      await context.route(`**://${AVATAR_HOST}/**`, async (route) => {
        const requested = new URL(route.request().url())
        if (requested.protocol !== 'https:' || requested.hostname !== AVATAR_HOST) {
          await route.abort()
          return
        }
        const body = fetchAvatar(requested.href)
        if (body) await route.fulfill({ status: 200, contentType: 'image/png', body })
        else await route.abort()
      })
    }

    const page = await context.newPage()
    const response = await page.goto(BASE + shot.path, { waitUntil: 'load', timeout: 60_000 })
    // 再ナビゲーション等では response が null になりうる（それ自体は異常ではない）
    if (response && !response.ok()) throw new Error(`${shot.path} が ${response.status()} を返した`)
    await page.addStyleTag({ content: FONT_FIX })
    await page.waitForTimeout(2000)

    const broken = await page.evaluate(() =>
      Array.from(document.images)
        .filter((image) => !image.complete || image.naturalWidth === 0)
        .map((image) => image.src),
    )
    if (broken.length > 0) throw new Error(`画像が読めていない: ${broken.join(', ')}`)

    const clip = shot.clipFrom ? await page.evaluate(shot.clipFrom) : undefined
    if (shot.clipFrom && !clip) throw new Error(`${shot.name}: クリップ範囲を特定できなかった`)

    const pngPath = join(tempDir, `${shot.name}.png`)
    await page.screenshot({ path: pngPath, ...(clip ? { clip } : {}) })
    await context.close()

    // WebP へ変換（sharp / cwebp が無い環境でも動くよう Chromium の canvas を使う）
    const converter = await browser.newPage()
    await converter.setContent('<canvas id="c"></canvas>')
    const converted = await converter.evaluate(
      async ({ base64, width }) => {
        const image = new Image()
        image.src = `data:image/png;base64,${base64}`
        await image.decode()
        const scale = width / image.naturalWidth
        const canvas = document.getElementById('c')
        canvas.width = Math.round(image.naturalWidth * scale)
        canvas.height = Math.round(image.naturalHeight * scale)
        const context2d = canvas.getContext('2d')
        context2d.imageSmoothingQuality = 'high'
        context2d.drawImage(image, 0, 0, canvas.width, canvas.height)
        return { dataUrl: canvas.toDataURL('image/webp', 0.86), width: canvas.width, height: canvas.height }
      },
      { base64: readFileSync(pngPath).toString('base64'), width: shot.width },
    )
    const webp = Buffer.from(converted.dataUrl.split(',')[1], 'base64')
    writeFileSync(join(IMG_DIR, `${shot.name}.webp`), webp)
    await converter.close()

    written.push({ name: shot.name, width: converted.width, height: converted.height })
    console.log(`${shot.name}.webp を更新した（${converted.width}×${converted.height} / ${webp.length} bytes）`)
  }
} finally {
  await browser.close()
  rmSync(tempDir, { recursive: true, force: true })
}

// index.html の width / height と実寸を突き合わせる（更新漏れは CLS になるので終了コードで止める）
const html = readFileSync(join(ROOT, 'site/index.html'), 'utf8')
const mismatches = []
for (const shot of written) {
  const pattern = new RegExp(
    `src="\\./assets/img/${shot.name}\\.webp"[^>]*?width="(\\d+)"[^>]*?height="(\\d+)"`,
    's',
  )
  const found = html.match(pattern)
  if (!found) {
    mismatches.push(`${shot.name}: site/index.html に width / height 付きの参照が見つからない`)
    continue
  }
  if (Number(found[1]) !== shot.width || Number(found[2]) !== shot.height) {
    mismatches.push(
      `${shot.name}: site/index.html は ${found[1]}×${found[2]} だが実寸は ${shot.width}×${shot.height}`,
    )
  }
}

if (mismatches.length > 0) {
  console.error('🔴 site/index.html の width / height を更新すること:')
  for (const line of mismatches) console.error(`  - ${line}`)
  process.exitCode = 1
} else {
  console.log('✅ site/index.html の width / height は実寸と一致している')
}
