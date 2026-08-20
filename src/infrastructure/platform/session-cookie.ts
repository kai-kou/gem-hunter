import { EncryptJWT, jwtDecrypt } from 'jose'
import { cookies } from 'next/headers'

/**
 * セッション Cookie（本ログイン確立後の本体のみ・AR-5 / NFR-9）。
 * 🔴 秘匿情報（セッション暗号鍵）を読んでよいのはこのファイルだけ（ARCH-5 / NFR-22）。
 * CSRF `state` Cookie はここでは扱わない（暗号化・署名不要・route handler が直書きする。
 * whiteboard `sp8-auth-i18n-20260819` 争点 B/C 決定）。
 *
 * 方式（争点 B 決定）: `jose` の `EncryptJWT`（`alg: "dir"`, `enc: "A256GCM"`）で
 * GitHub アクセストークンを暗号化する。対称鍵は 32 バイトを base64url エンコードして
 * 環境変数 `SESSION_ENCRYPTION_KEY` に格納する運用（`installation-token.ts` の
 * `readCredentials()` パターンを踏襲し、未設定なら機能を静かに無効化する）。
 */

/** TTL 7〜14 日のうち下限（`exp` に設定する秒数）。 */
export const SESSION_COOKIE_TTL_SECONDS = 7 * 24 * 60 * 60

export const SESSION_COOKIE_NAME = 'gem_hunter_session'

const SESSION_KEY_BYTE_LENGTH = 32

/** Node / Cloudflare Workers の両方で使える base64url デコード（`Buffer` に依存しない）。 */
function base64UrlToBytes(value: string): Uint8Array | null {
  try {
    const normalized = value.replace(/-/g, '+').replace(/_/g, '/')
    const padLength = (4 - (normalized.length % 4)) % 4
    const padded = normalized + '='.repeat(padLength)
    const binary = atob(padded)
    const bytes = new Uint8Array(binary.length)
    for (let i = 0; i < binary.length; i += 1) {
      bytes[i] = binary.charCodeAt(i)
    }
    return bytes
  } catch {
    return null
  }
}

function readKey(): Uint8Array | null {
  const raw = process.env.SESSION_ENCRYPTION_KEY
  if (!raw) {
    return null
  }
  const bytes = base64UrlToBytes(raw)
  if (!bytes || bytes.byteLength !== SESSION_KEY_BYTE_LENGTH) {
    return null
  }
  return bytes
}

/** セッション暗号鍵が設定されているか。composition root の表示ゲート用（値は返さない）。 */
export function sessionEncryptionConfigured(): boolean {
  return readKey() !== null
}

export type SessionPayload = { accessToken: string }

/** GitHub アクセストークンを JWE 暗号化した文字列にする（httpOnly Cookie の値に使う）。 */
export async function encodeSessionCookie(payload: SessionPayload): Promise<string> {
  const key = readKey()
  if (!key) {
    throw new Error('SESSION_ENCRYPTION_KEY が設定されていません')
  }

  return new EncryptJWT({ accessToken: payload.accessToken })
    .setProtectedHeader({ alg: 'dir', enc: 'A256GCM' })
    .setIssuedAt()
    .setExpirationTime(`${SESSION_COOKIE_TTL_SECONDS}s`)
    .encrypt(key)
}

/**
 * セッション Cookie を復号する。鍵未設定・改ざん・期限切れなど、理由を問わず
 * 復号できない場合は必ず `null` を返す（未ログイン扱いへ安全側に倒す）。
 */
export async function decodeSessionCookie(raw: string): Promise<SessionPayload | null> {
  const key = readKey()
  if (!key) {
    return null
  }

  try {
    const { payload } = await jwtDecrypt(raw, key)
    if (typeof payload.accessToken !== 'string' || payload.accessToken.length === 0) {
      return null
    }
    return { accessToken: payload.accessToken }
  } catch {
    return null
  }
}

/**
 * Server Component（`app/[locale]/layout.tsx` 等）向けの Cookie ストア読み取り。
 * 外部世界（HTTP Cookie ストア）への I/O は composition root ではなくここに閉じ込める
 * （`architecture-rules.md` §1「外部世界に触るか？→ infrastructure/」・PR #141 レビュー指摘）。
 * Route handler 側は `NextRequest.cookies`（引数経由）を使うため、こちらは
 * `next/headers` の `cookies()` を使う Server Component 専用の経路。
 */
export async function readSessionCookieFromRequestScope(): Promise<string | null> {
  const store = await cookies()
  return store.get(SESSION_COOKIE_NAME)?.value ?? null
}
