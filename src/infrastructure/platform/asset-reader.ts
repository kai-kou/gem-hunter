/**
 * 静的アセット（`public/` 配下）の読み取り経路を隠す薄い層（`SP-18` / `D-38`）。
 *
 * Gem 候補プールのシャードは Cloudflare Workers Static Assets（`env.ASSETS`）で配信されるが、
 * `npm test` / `next dev` / E2E ではその binding が存在しない。両者の差をここだけに閉じ込め、
 * 上位（`StaticGemIndex`）は「パスを渡すと本文か null が返る関数」だけを知る。
 *
 * 🔴 **どちらの経路も例外を投げない**（読めなければ `null`）。バッジ用データの取得失敗で
 * 検索そのものを落とさないという `D-28` の SPOF 方針に合わせる。
 */

/**
 * `/data/gem-index/index.json` のような **絶対パス**（`public/` からの相対 + 先頭スラッシュ）を
 * 受け取り、本文を返す。見つからない・読めないときは `null`。
 */
export type AssetReader = (path: string) => Promise<string | null>

/** Workers Static Assets の binding（`env.ASSETS`）のうち本層が使う最小の shape。 */
export type AssetsBinding = {
  fetch(input: URL, init?: { signal?: AbortSignal }): Promise<Response>
}

/**
 * `env.ASSETS.fetch()` に渡すダミーオリジン。Static Assets はパスだけを見るため、
 * ホスト名は解決されない（実オリジンを組み立てる必要がない = `SITE_URL` に依存しない）。
 */
const ASSET_ORIGIN = 'https://assets.local'

/**
 * Workers 経路の 1 アセットあたりの取得上限（ミリ秒）。
 *
 * 🔴 **なぜ上限が要るか**: バッジ照会は検索結果の描画をブロックする位置にあり、呼び出し側の
 * `.catch()` は **reject は拾えてもハングは拾えない**。1 本が応答を返さないだけで
 * `Promise.all` が解決せず、検索結果が 1 件も出ないままゲートウェイタイムアウトに落ちる。
 * 🔵 **2,000ms の根拠**: 同一 Worker から同一エッジの Static Assets を引くだけの取得で、
 * 正常時は数十 ms で返る。cold start の揺らぎを数十倍見ても十分な余裕がありつつ、
 * 全滅しても検索描画の待ち時間が体感を壊さない（バッジなしで即座に続行できる）範囲に収める。
 */
const ASSET_FETCH_TIMEOUT_MS = 2_000

type EnvWithAssets = {
  ASSETS?: AssetsBinding
}

/**
 * アセットパスとして受け付けてよい形か（**正規化済みのパスに対して** 使う）。
 *
 * 🔴 パストラバーサル防止: 先頭スラッシュ必須・`..` を含むものは拒否する。
 */
function isSafeAssetPath(path: string): boolean {
  if (typeof path !== 'string' || path.length === 0) {
    return false
  }
  if (!path.startsWith('/')) {
    return false
  }
  if (path.includes('..') || path.includes('\0') || path.includes('\\')) {
    return false
  }
  return true
}

/**
 * アセットパスを検証し、取得先の `URL` を返す。受け付けられない形なら `null`。
 *
 * 🔴 **なぜ「解決してから」判定するか**: Workers 経路は `new URL(path, ASSET_ORIGIN)` でパスを
 * 解決するため、生文字列に `..` が無くても WHATWG URL の正規化でディレクトリ脱出が起きる。
 *
 * ```
 * new URL('/data/gem-index/%2e%2e/%2e%2e/secret.json', ASSET_ORIGIN).pathname // → '/secret.json'
 * new URL('/data/gem-index/%2E%2E/etc.json',           ASSET_ORIGIN).pathname // → '/data/etc.json'
 * new URL('//evil.com/x.json',                         ASSET_ORIGIN).origin   // → 'https://evil.com'
 * ```
 *
 * 生文字列だけを見る判定では **経路によって受理される入力が変わってしまう** ため、
 * ファイルシステム経路の `path.resolve` + 接頭辞チェックと同じく「正規化してから判定する」形に
 * 揃える。両 reader がこの関数を通すことで同値性を保つ。
 */
function resolveAssetUrl(rawPath: string): URL | null {
  if (typeof rawPath !== 'string' || !rawPath.startsWith('/')) {
    return null
  }

  let url: URL
  try {
    url = new URL(rawPath, ASSET_ORIGIN)
  } catch {
    return null
  }

  // `//evil.com/x.json` のように別オリジンへ化けるものを拒否する。
  if (url.origin !== ASSET_ORIGIN) {
    return null
  }
  // 正規化でパスが動いた（`%2e%2e` 等で階層を移動した・クエリや素片が付いていた）ものを拒否する。
  if (url.pathname !== rawPath) {
    return null
  }
  if (!isSafeAssetPath(url.pathname)) {
    return null
  }
  return url
}

/** Workers 実行環境の `env.ASSETS` を取得する。取れなければ `undefined`（実行環境の外・binding 未宣言）。 */
async function assetsBinding(): Promise<AssetsBinding | undefined> {
  try {
    // 🔴 動的 import にする理由は `cloudflare-bindings.ts`（`rateLimiterBinding()`）と同じ。
    //    `@opennextjs/cloudflare` は Workers 実行環境を前提としており、その外（`npm test` の
    //    Node/jsdom 等）ではモジュール解決自体が失敗しうるため、呼び出し時にのみ読み込む。
    const { getCloudflareContext } = await import('@opennextjs/cloudflare')
    const context = await getCloudflareContext({ async: true })
    const env = context?.env as EnvWithAssets | undefined
    return env?.ASSETS
  } catch {
    return undefined
  }
}

/** Workers Static Assets（`env.ASSETS.fetch()`）から読む reader。 */
export function createWorkersAssetReader(binding: AssetsBinding): AssetReader {
  return async (path) => {
    const url = resolveAssetUrl(path)
    if (url === null) {
      warn(`不正なアセットパスを拒否しました: ${path}`)
      return null
    }
    try {
      const response = await fetchWithTimeout(binding, url)
      if (response === null) {
        warn(`アセットの取得が ${ASSET_FETCH_TIMEOUT_MS}ms で応答しませんでした: ${path}`)
        return null
      }
      if (!response.ok) {
        warn(`アセットを取得できませんでした（HTTP ${response.status}）: ${path}`)
        return null
      }
      return await response.text()
    } catch (error) {
      warn(`アセットの取得に失敗しました: ${path}（${describe(error)}）`)
      return null
    }
  }
}

/**
 * `binding.fetch()` に上限時間を課す。時間切れは例外ではなく `null`（= そのアセットは
 * 読めなかった扱い）に倒す。
 *
 * 🔵 `AbortSignal` を渡すだけにしないのは、**binding が signal を尊重するとは限らない** ため。
 * 実際のキャンセル（無駄な通信の打ち切り）は signal に任せつつ、**呼び出し側が必ず解決する保証**
 * はタイマーとの race で持つ。`AbortSignal.timeout` が無い実行環境ではタイマーだけが働く。
 */
async function fetchWithTimeout(binding: AssetsBinding, url: URL): Promise<Response | null> {
  const signal =
    typeof AbortSignal !== 'undefined' && typeof AbortSignal.timeout === 'function'
      ? AbortSignal.timeout(ASSET_FETCH_TIMEOUT_MS)
      : undefined

  const fetched = binding.fetch(url, signal === undefined ? undefined : { signal })
  // 時間切れで race を降りた後に遅れて reject しても unhandled rejection にしない。
  fetched.catch(() => undefined)

  let timer: ReturnType<typeof setTimeout> | undefined
  const timedOut = new Promise<null>((resolve) => {
    timer = setTimeout(() => resolve(null), ASSET_FETCH_TIMEOUT_MS)
  })

  try {
    return await Promise.race([fetched, timedOut])
  } finally {
    clearTimeout(timer)
  }
}

/**
 * ファイルシステム（既定は `public/`）から読む reader。
 *
 * 🔴 **なぜ同一オリジンへの `fetch` にしないか**: `getSiteUrl()` は `SITE_URL` 未設定時に
 * **本番 URL** を返すため、`next dev` と E2E が本番のアセットを取りに行ってしまい、
 * `NFR-24`（E2E はネットワークを触らない）に反する。ローカル経路はネットワークを介さず
 * ファイルを直接読む。
 *
 * 🔵 タイムアウトは設けない（ローカルディスクの読み取りはネットワークのようにハングしない）。
 */
export function createFileSystemAssetReader(baseDir: string): AssetReader {
  return async (assetPath) => {
    // 🔴 Workers 経路と同じ判定を通す（経路によって受理される入力が変わらないようにする）。
    const url = resolveAssetUrl(assetPath)
    if (url === null) {
      warn(`不正なアセットパスを拒否しました: ${assetPath}`)
      return null
    }
    try {
      // 🔴 動的 import にする理由: このモジュールは Workers ランタイム（`node:fs` が無い経路）
      //    からも読み込まれる。トップレベル import にすると、その経路のバンドルまで
      //    `node:fs/promises` を要求してしまう。
      const [{ readFile }, path] = await Promise.all([
        import('node:fs/promises'),
        import('node:path'),
      ])
      const root = path.resolve(baseDir)
      const target = path.resolve(path.join(root, url.pathname))
      // `resolveAssetUrl` の二重確認（シンボリックな `.` の畳み込み後も root の内側か）。
      if (target !== root && !target.startsWith(root + path.sep)) {
        warn(`ベースディレクトリの外を指すパスを拒否しました: ${assetPath}`)
        return null
      }
      return await readFile(target, 'utf8')
    } catch (error) {
      warn(`アセットを読めませんでした: ${assetPath}（${describe(error)}）`)
      return null
    }
  }
}

/**
 * Workers 実行環境なら `env.ASSETS.fetch()`、そうでなければ `public/` をファイルシステムから
 * 読む reader を返す。
 */
export async function resolveAssetReader(): Promise<AssetReader> {
  const binding = await assetsBinding()
  if (binding !== undefined) {
    return createWorkersAssetReader(binding)
  }
  return createFileSystemAssetReader(defaultPublicDir())
}

/** ファイルシステム経路の既定ベースディレクトリ（プロジェクトルートの `public/`）。 */
function defaultPublicDir(): string {
  // `path.join` を使わないのは、この関数が同期であり `node:path` を動的 import できないため。
  // 実際の結合・正規化は `createFileSystemAssetReader` 側の `path.resolve` が行う。
  return `${process.cwd()}/public`
}

function describe(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function warn(message: string): void {
  console.warn(`[AssetReader] ${message}`)
}
