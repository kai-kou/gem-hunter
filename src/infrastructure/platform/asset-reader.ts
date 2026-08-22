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
  fetch(input: URL): Promise<Response>
}

/**
 * `env.ASSETS.fetch()` に渡すダミーオリジン。Static Assets はパスだけを見るため、
 * ホスト名は解決されない（実オリジンを組み立てる必要がない = `SITE_URL` に依存しない）。
 */
const ASSET_ORIGIN = 'https://assets.local'

type EnvWithAssets = {
  ASSETS?: AssetsBinding
}

/**
 * アセットパスとして受け付けてよい形か。
 *
 * 🔴 パストラバーサル防止: 先頭スラッシュ必須・`..` を含むものは拒否する（ファイルシステム経路で
 * `public/` の外へ抜けるのを入口で止める。Workers 経路でも同じ判定を通し、経路によって
 * 受理される入力が変わらないようにする）。
 */
export function isSafeAssetPath(path: string): boolean {
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

/** Workers 実行環境の `env.ASSETS` を取得する。取れなければ `undefined`（実行環境の外・binding 未宣言）。 */
export async function assetsBinding(): Promise<AssetsBinding | undefined> {
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
    if (!isSafeAssetPath(path)) {
      warn(`不正なアセットパスを拒否しました: ${path}`)
      return null
    }
    try {
      const response = await binding.fetch(new URL(path, ASSET_ORIGIN))
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
 * ファイルシステム（既定は `public/`）から読む reader。
 *
 * 🔴 **なぜ同一オリジンへの `fetch` にしないか**: `getSiteUrl()` は `SITE_URL` 未設定時に
 * **本番 URL** を返すため、`next dev` と E2E が本番のアセットを取りに行ってしまい、
 * `NFR-24`（E2E はネットワークを触らない）に反する。ローカル経路はネットワークを介さず
 * ファイルを直接読む。
 */
export function createFileSystemAssetReader(baseDir: string): AssetReader {
  return async (assetPath) => {
    if (!isSafeAssetPath(assetPath)) {
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
      const target = path.resolve(path.join(root, assetPath))
      // `isSafeAssetPath` の二重確認（シンボリックな `.` の畳み込み後も root の内側か）。
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
